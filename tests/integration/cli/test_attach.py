"""`hmz attach`: one more frontend of the runs a host is holding in this directory.

Each run here is of a flow that drives no agent -- two people outside it, asked in turn -- held
by a real `daemon.host()`, started by the test's own link as a program written against the SDK
would start it, and read by `hmz attach` in a process of its own: once as a program, stdout
every message and stdin one request a line, and once as a person, a line typed answering
whatever this frontend may answer.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli, daemon
from tests.stubs import written

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from hmz.daemon import Link

#: How long a test waits for something another process is doing.
PATIENCE = 30.0

#: Two people outside the run, asked one after the other, until `go` says to finish.
ASKS = """
import asyncio
import json
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    planner: Outworlder
    reviewer: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="asks")
async def asks(task, *, agents, envs, params, ctx):
    here = envs["workspace"]
    planner = await agents["planner"].spawn(env=here)
    reviewer = await agents["reviewer"].spawn(env=here)
    plan = await agents["planner"].run(f"what is the plan for {task}?", session=planner)
    review = await agents["reviewer"].run(f"is {plan!r} good?", session=reviewer)
    while not Path("go").exists():
        await asyncio.sleep(0.02)
    Path("result.json").write_text(json.dumps({"plan": plan, "review": review}))
"""


def until(what: Callable[[], object], seconds: float = PATIENCE) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if what():
            return True
        time.sleep(0.05)
    return bool(what())


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    where = tmp_path / "project"
    where.mkdir()
    written(where, "asks", ASKS)
    monkeypatch.chdir(where)
    return where


@pytest.fixture
def hosted(workspace: Path) -> Iterator[daemon.Daemon]:
    one = daemon.host()
    try:
        yield one
    finally:
        (workspace / "go").write_text("")
        if one.alive:
            one.kill()


class Starter:
    """The frontend that starts the run, as a program written against the SDK does."""

    def __init__(self, link: Link) -> None:
        self.link = link
        self.seen: list[dict[str, Any]] = []
        link.heard(self.seen.append)

    def asked(self, role: str) -> dict[str, Any]:
        found: list[dict[str, Any]] = []

        def asking() -> bool:
            for said in list(self.seen):
                if said["type"] == "pending":
                    found[:] = [one for one in said["pending"] if one["role"] == role]
            return bool(found)

        assert until(asking), f"{role} was never asked"
        return found[0]


@pytest.fixture
def starter(hosted: daemon.Daemon) -> Iterator[Starter]:
    with hosted.link(name="starter") as link:
        yield Starter(link)


def _attaching(*argv: str) -> subprocess.Popen[str]:
    import os

    # Read as a pipe is read, whatever the terminal running the suite asks for.
    plain = {name: said for name, said in os.environ.items() if name != "FORCE_COLOR"}
    return subprocess.Popen(
        [sys.executable, "-m", "hmz", "attach", *argv],
        env=plain,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _next(
    process: subprocess.Popen[str], what: Callable[[dict[str, Any]], bool]
) -> dict[str, Any]:
    """The next object `hmz attach --json` writes that `what` says yes to."""
    assert process.stdout is not None
    for line in process.stdout:
        said: dict[str, Any] = json.loads(line)
        if what(said):
            return said
    raise AssertionError(f"hmz attach ended first: {process.wait()}")


def test_nothing_held_here_is_said_and_nothing_is_started(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["attach"]) == 1

    assert "nothing to attach to in this directory" in capsys.readouterr().err
    assert daemon.running() is None


@pytest.mark.timeout(90)
def test_a_role_somebody_else_holds_is_a_usage_error(
    starter: Starter, capsys: pytest.CaptureFixture[str]
) -> None:
    starter.link.claim("planner")

    assert cli.main(["attach", "-c", "planner"]) == 2

    assert "planner is starter's" in capsys.readouterr().err


@pytest.mark.timeout(90)
def test_a_program_reads_every_message_and_asks_a_request_a_line(
    starter: Starter, workspace: Path
) -> None:
    attaching = _attaching("--json", "-c", "planner")
    assert attaching.stdin is not None
    welcome = _next(attaching, lambda said: said["type"] == "welcome")
    assert welcome["kind"] == "cli"
    _next(attaching, lambda said: said["type"] == "live")

    starter.link.start("asks", "the parser", budget={"cost": 1})
    asked = _next(
        attaching,
        lambda said: (
            said["type"] == "pending"
            and any(one["role"] == "planner" for one in said["pending"])
        ),
    )["pending"][0]
    assert asked["owner"] == welcome["client"]
    attaching.stdin.write("not a request\n")
    assert _next(attaching, lambda said: said["type"] == "reply") == {
        "type": "reply",
        "to": "",
        "ok": False,
        "why": "not a request object",
    }
    attaching.stdin.write(
        json.dumps(
            {
                "id": "a1",
                "do": "answer",
                "question": asked["question"],
                "text": "the plan",
            }
        )
        + "\n"
    )
    assert _next(attaching, lambda said: said["type"] == "reply") == {
        "type": "reply",
        "to": "a1",
        "ok": True,
    }
    # The end of what it is told to say is not the end of what it reads.
    attaching.stdin.close()
    reviewing = starter.asked("reviewer")
    starter.link.answer(reviewing["question"], "fine")
    (workspace / "go").write_text("")

    ended = _next(attaching, lambda said: said["type"] == "ended")
    assert ended["how"] == "done"
    assert attaching.wait(PATIENCE) == 0
    assert json.loads((workspace / "result.json").read_text()) == {
        "plan": "the plan",
        "review": "fine",
    }


@pytest.mark.timeout(90)
def test_a_person_answers_what_is_theirs_by_typing_it(
    starter: Starter, workspace: Path
) -> None:
    starter.link.start("asks", "the parser", budget={"cost": 1})
    attaching = _attaching("-c", "planner")
    assert attaching.stdin is not None
    starter.asked("planner")
    assert until(
        lambda: any(
            said["type"] == "claims" and "planner" in said["claims"]
            for said in list(starter.seen)
        )
    )

    attaching.stdin.write("a typed plan\n")
    attaching.stdin.flush()
    reviewing = starter.asked("reviewer")
    starter.link.answer(reviewing["question"], "fine")
    (workspace / "go").write_text("")

    out, err = attaching.communicate(timeout=PATIENCE)
    assert attaching.returncode == 0, err
    assert json.loads((workspace / "result.json").read_text())["plan"] == "a typed plan"
    assert "planner: what is the plan for the parser?" in err
    assert "hmz attach: planner is claimed by you" in err
    assert "❯ a typed plan · " in err
    assert "❯ fine · starter for reviewer" in err
    assert "— the flow is done —" in err
    assert out == ""


@pytest.mark.timeout(90)
def test_a_person_stops_the_run_they_are_reading(starter: Starter) -> None:
    starter.link.start("asks", "the parser", budget={"cost": 1})
    starter.asked("planner")
    attaching = _attaching()
    assert attaching.stdin is not None

    # A line that is no command is said to be none, and what is typed after it still reads.
    attaching.stdin.write("/\n")
    attaching.stdin.write("/stop\n")
    attaching.stdin.flush()

    _, err = attaching.communicate(timeout=PATIENCE)
    assert attaching.returncode == 0, err
    assert "unknown command: /;" in err
    assert "is stopping the flow" in err
    assert "— the flow stopped —" in err
