"""`hmz exec` stopped by an interrupt, whenever in the run it comes.

An interrupt stops a run the way a terminate or a hangup does: the run unwinds, lets go of
what it made, and the process exits `130` -- with a line of its own at most, and never a
traceback. It is checked arriving before the run has begun, before its first turn, in the
middle of a turn, and again while the run is already letting go -- where a second terminate or
hangup is ignored and a second interrupt ends the process there and then; and sent both to the
process alone, as `kill -INT` and `timeout -s INT` send it, and to its whole process group, as
a terminal's ctrl+c does. The turn is taken by the stand-in `claude` of
:mod:`tests.flows.standins`.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from tests.flows import standins
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: A flow that says it is going and then waits, and says so again once it has unwound. With
#: `AGAIN`, it is interrupted a second time while it unwinds, and takes its time about it.
_WAITS = """
import asyncio
import os
import signal
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow

HERE = Path(__file__).parent


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def waits(task, *, agents, envs, params, ctx):
    (HERE / "up").touch()
    try:
        await asyncio.sleep(240)
    finally:
        if AGAIN:
            os.kill(os.getpid(), AGAIN)
            await asyncio.sleep(1)
        (HERE / "unwound").touch()
"""

#: A flow that is interrupted before it takes its one turn, which it waits to be stopped in.
_FIRST = """
import asyncio
import os
import signal

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, flow


class Agents(AgentCollection):
    coder: Agent


@flow(agents=Agents, envs=EnvCollection, params=FlowParams)
async def first(task, *, agents, envs, params, ctx):
    os.kill(os.getpid(), signal.SIGINT)
    await asyncio.sleep(30)
    session = await agents["coder"].spawn()
    await agents["coder"].run("Reply with the single word: late", session=session)
"""

#: A flow interrupted while it is still being loaded, before there is a run to stop.
_LOADING = """
import os
import signal
import time

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow

os.kill(os.getpid(), signal.SIGINT)
time.sleep(30)


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def loading(task, *, agents, envs, params, ctx):
    pass
"""

#: What a stand-in CLI is started with to die of an interrupt as a program that does not
#: handle one does.
_DIES = "import signal\nsignal.signal(signal.SIGINT, signal.SIG_DFL)\n"


def _exec(where: Path, *line: str) -> subprocess.Popen[str]:
    """`hmz exec` in a process group of its own, as a job at a terminal is."""
    return subprocess.Popen(
        [sys.executable, "-Pm", "hmz", "exec", *line],
        cwd=where,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )


def _once(where: Path, run: subprocess.Popen[str]) -> None:
    """Waits for `where` to be there, which the run it is waiting on says it has reached."""
    deadline = time.monotonic() + 60
    while not where.exists():
        assert run.poll() is None, run.communicate()
        assert time.monotonic() < deadline, f"the run never reached {where.name}"
        time.sleep(0.05)


def _ended(run: subprocess.Popen[str]) -> str:
    """Waits for the run to end, and answers with what it said on stderr."""
    try:
        _, err = run.communicate(timeout=60)
    finally:
        if run.poll() is None:
            os.killpg(run.pid, signal.SIGKILL)
    return err


@pytest.mark.timeout(120)
def test_an_interrupt_before_the_run_began_exits_130(tmp_path: Path) -> None:
    """Nothing has been made yet, so there is nothing to let go of -- nor any traceback."""
    flow = written(tmp_path / "flows", "loading", _LOADING)
    run = _exec(tmp_path, "-f", str(flow), "-b", "cost=1", "go")

    err = _ended(run)

    assert run.returncode == 130, err
    assert "Traceback" not in err, err


@pytest.mark.timeout(120)
def test_an_interrupt_before_the_first_turn_stops_the_run_before_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = standins.install(tmp_path / "bin", "claude", standins.CLAUDE)
    monkeypatch.setenv("PATH", standins.path_with(tmp_path / "bin"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    flow = written(tmp_path / "flows", "first", _FIRST)
    run = _exec(
        tmp_path,
        *("-f", str(flow), "-a", "coder=claude/claude-haiku-4-5:low"),
        *("-b", "cost=1", "go"),
    )

    err = _ended(run)

    assert run.returncode == 130, err
    assert "Traceback" not in err, err
    said = log.read_text().splitlines() if log.exists() else []
    assert not [one for one in said if "said" in json.loads(one)]


@pytest.mark.timeout(120)
@pytest.mark.parametrize("to", ["process", "group"])
def test_an_interrupt_mid_turn_stops_the_run_and_exits_130(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, to: str
) -> None:
    """`kill -INT` reaches `hmz exec` alone; ctrl+c reaches the CLI it runs as well."""
    # Which ends the stand-in there and then, as it ends a real CLI, rather than as an
    # interrupted Python script with a traceback of its own on the stderr it shares.
    log = standins.install(tmp_path / "bin", "claude", _DIES + standins.CLAUDE)
    monkeypatch.setenv("PATH", standins.path_with(tmp_path / "bin"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    run = _exec(
        tmp_path,
        *("-f", "chat", "-a", "assistant=claude/claude-haiku-4-5:low"),
        "slow, and then say done",
    )
    deadline = time.monotonic() + 60
    while not (log.exists() and '"said"' in log.read_text()):
        assert run.poll() is None, run.communicate()
        assert time.monotonic() < deadline, "the turn never started"
        time.sleep(0.05)
    time.sleep(0.5)

    if to == "group":
        os.killpg(run.pid, signal.SIGINT)
    else:
        run.send_signal(signal.SIGINT)
    err = _ended(run)

    assert run.returncode == 130, err
    assert "Traceback" not in err, err


@pytest.mark.timeout(120)
@pytest.mark.parametrize(
    ("first", "then"),
    [
        (signal.SIGINT, signal.SIGTERM),
        (signal.SIGINT, signal.SIGHUP),
        (signal.SIGTERM, signal.SIGHUP),
    ],
)
def test_a_terminate_or_a_hangup_while_the_run_unwinds_does_not_cut_it_short(
    tmp_path: Path, first: signal.Signals, then: signal.Signals
) -> None:
    """The run lets go of what it made, and exits as the first signal would have had it."""
    flow = written(tmp_path / "flows", "waits", _WAITS.replace("AGAIN", str(int(then))))
    here = tmp_path / "flows" / "waits"
    run = _exec(tmp_path, "-f", str(flow), "-b", "cost=1", "go")
    _once(here / "up", run)

    run.send_signal(first)
    err = _ended(run)

    assert run.returncode == 128 + first, err
    assert "Traceback" not in err, err
    assert (here / "unwound").exists()


@pytest.mark.timeout(120)
@pytest.mark.parametrize("first", [signal.SIGINT, signal.SIGTERM])
def test_a_second_interrupt_while_the_run_unwinds_ends_it_there_and_then(
    tmp_path: Path, first: signal.Signals
) -> None:
    """The way out of an unwinding that hangs, as ctrl+c twice is out of most programs."""
    flow = written(
        tmp_path / "flows", "waits", _WAITS.replace("AGAIN", str(int(signal.SIGINT)))
    )
    here = tmp_path / "flows" / "waits"
    run = _exec(tmp_path, "-f", str(flow), "-b", "cost=1", "go")
    _once(here / "up", run)

    run.send_signal(first)
    err = _ended(run)

    # Ended by the interrupt itself, which a shell reports as 130.
    assert run.returncode == -signal.SIGINT, err
    assert "Traceback" not in err, err
    assert not (here / "unwound").exists()
