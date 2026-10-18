"""A session one `hmz exec` kept in its flow's state, carried on by a later run picking it up.

Each run is a real `python -m hmz exec` driving the stand-in `claude`, which resumes a
conversation only from where Claude keeps one for the directory it is started in, and copies
the whole of it into a fork. So the later run's session answers from the conversation as it
stood when the state kept it only where humanize copied it out then, brought the copy in
where the later run keeps its sessions, and carried it to the directory that turn works in.
Where a run keeps no sessions of its own, that is the CLI's home, whose conversation is never
put back to a copy of it.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.providers import redirect
from hmz.sdk import Hmz
from tests.integration.doubles_core import AGENT, hmz_exec, install, started, write_flow

if TYPE_CHECKING:
    from pathlib import Path

#: A flow that keeps its session in its state, and goes on with it as `then` says; a run picking
#: it up carries the session on from where it was kept, in the environment it is given.
REMEMBERS = """
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowParams, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    there: Env


class Params(FlowParams):
    step: str = "keep"
    then: str = ""


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def remembers(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    if params.step == "keep":
        session = await worker.spawn()
        said = await worker.run("the word is papaya", session=session)
        ctx.state["boundary"] = session
        if params.then:
            said = await worker.run(params.then, session=session)
        return said
    again = ctx.state["boundary"]
    return await worker.run(f"{params.step}: what was the word?", session=again, env=envs["there"])
"""

#: Whether a run here keeps its sessions itself, rather than in the CLI's home.
SUPERVISED = sys.platform == "linux" and redirect.supervises()


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = install(tmp_path, monkeypatch)
    write_flow(tmp_path / "flows", "remembers", REMEMBERS)
    (tmp_path / "there").mkdir()
    return path


def _remembers(tmp_path: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return hmz_exec(
        "-f",
        str(tmp_path / "flows" / "remembers"),
        "-a",
        f"worker={AGENT}",
        "-e",
        f"there=local/{tmp_path / 'there'}",
        "-p",
        "budget.cost=1",
        *argv,
        "go",
    )


def _said(ran: subprocess.CompletedProcess[str]) -> str:
    assert ran.returncode == 0, ran.stderr
    return ran.stdout.strip().splitlines()[-1]


def _carried_on(tmp_path: Path, project: Path, then: str) -> None:
    """Keeps a session, goes on as `then` says, and carries the kept one on twice."""
    _said(_remembers(tmp_path, "-p", f"then={then}"))
    told = started(tmp_path)[0]

    for arm in ("continue", "again"):
        said = _said(_remembers(tmp_path, "-p", f"step={arm}", "--resume"))
        assert said == f"did: {arm}: what was the word?"

    carried = started(tmp_path)[-2:]
    for one in carried:
        argv = one["argv"]
        assert argv[argv.index("--resume") + 1] == told["session"]
        assert "--fork-session" in argv
        assert one["cwd"] == str((tmp_path / "there").resolve())
        assert one["session"] != told["session"]
    epics = Hmz(project).epics
    kept, *picked = epics.all()
    (conversation,) = (kept / "sessions" / "claude" / ".kept").iterdir()
    (transcript,) = conversation.glob(f"projects/*/{told['session']}.jsonl")
    assert b"papaya" in transcript.read_bytes()
    if then:
        assert then.encode() not in transcript.read_bytes(), "kept as it stood then"
    for epic, one in zip(picked, carried, strict=True):
        ran = epics.read(epic)
        assert ran is not None
        (session,) = ran.sessions
        assert (session.ident, session.parent) == (one["session"], told["session"])


def test_a_session_kept_in_state_is_carried_on_by_every_later_run_picking_it_up(
    tmp_path: Path, project: Path
) -> None:
    _carried_on(tmp_path, project, then="")


@pytest.mark.skipif(not SUPERVISED, reason="a run keeps no sessions of its own here")
def test_a_session_is_carried_on_from_where_it_stood_when_its_state_kept_it(
    tmp_path: Path, project: Path
) -> None:
    _carried_on(tmp_path, project, then="the word is mango")


def test_a_kept_session_the_clis_home_went_on_with_is_not_put_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_SESSIONS", "off")
    _said(_remembers(tmp_path, "-p", "then=the word is mango"))
    (told,) = started(tmp_path)
    (held,) = (tmp_path / "claude").glob(f"projects/*/{told['session']}.jsonl")
    went_on = held.read_bytes()
    assert b"mango" in went_on

    later = _remembers(tmp_path, "-p", "step=continue", "--resume")

    assert later.returncode != 0
    assert f"another copy of conversation {told['session']} is kept at" in later.stderr
    assert held.read_bytes() == went_on
    assert len(started(tmp_path)) == 1


#: A flow that only talks, keeping nothing; a run given a conversation of an earlier one to
#: carry on (`--carry-on earlier=...`) reads it from its state and goes on with it there.
CARRIES = """
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowParams, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    there: Env


class Params(FlowParams):
    then: str = ""
    fail: bool = False


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def carries(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    if "earlier" in ctx.state:
        again = ctx.state["earlier"]
        return await worker.run(f"{task}: what was the word?", session=again, env=envs["there"])
    session = await worker.spawn()
    said = await worker.run("the word is papaya", session=session)
    if params.then:
        said = await worker.run(params.then, session=session)
    if params.fail:
        raise RuntimeError("gave up")
    return said
"""

#: The same, but a flow that keeps no state to be handed a conversation in.
FORGETS = CARRIES.replace("resumable=True", "resumable=False")


def _carries(tmp_path: Path, task: str, *argv: str) -> subprocess.CompletedProcess[str]:
    return hmz_exec(
        "-f",
        str(tmp_path / "flows" / "carries"),
        "-a",
        f"worker={AGENT}",
        "-e",
        f"there=local/{tmp_path / 'there'}",
        "-p",
        "budget.cost=1",
        *argv,
        task,
    )


def _talked(tmp_path: Path, project: Path, *argv: str) -> tuple[Path, str, str]:
    """Has a run talk, and answers with its epic, its conversation's name and its id."""
    write_flow(tmp_path / "flows", "carries", CARRIES)
    _carries(tmp_path, "talk", *argv)
    epics = Hmz(project).epics
    epic = epics.all()[-1]
    ran = epics.read(epic)
    assert ran is not None
    (session,) = ran.sessions
    return epic, f"{session.agent}/1", session.ident


def _went_on(tmp_path: Path, told: str) -> None:
    """The last start of the stand-in carried conversation `told` on, as a fork, `there`."""
    one = started(tmp_path)[-1]
    argv = one["argv"]
    assert argv[argv.index("--resume") + 1] == told
    assert "--fork-session" in argv
    assert one["cwd"] == str((tmp_path / "there").resolve())
    assert one["session"] != told


def test_a_conversation_an_earlier_epic_had_is_carried_on_by_a_later_one_naming_it(
    tmp_path: Path, project: Path
) -> None:
    earlier, name, told = _talked(tmp_path, project, "-p", "then=the word is mango")

    said = _said(
        _carries(tmp_path, "continue", "--carry-on", f"earlier={earlier.name}/{name}")
    )

    assert said == "did: continue: what was the word?"
    _went_on(tmp_path, told)
    epics = Hmz(project).epics
    later = epics.all()[-1]
    (copy,) = (later / "sessions" / "claude" / ".kept").iterdir()
    (transcript,) = copy.glob(f"projects/*/{told}.jsonl")
    assert b"papaya" in transcript.read_bytes()
    assert b"mango" in transcript.read_bytes(), "as the earlier epic left it"
    ran = epics.read(later)
    assert ran is not None
    (session,) = ran.sessions
    assert session.parent == told
    assert not (earlier / "sessions" / "claude" / ".kept").exists(), (
        "the earlier is left"
    )


def test_a_conversation_carried_on_is_carried_on_again_by_a_run_picking_that_one_up(
    tmp_path: Path, project: Path
) -> None:
    earlier, name, told = _talked(tmp_path, project)
    _said(
        _carries(tmp_path, "continue", "--carry-on", f"earlier={earlier.name}/{name}")
    )

    said = _said(_carries(tmp_path, "again", "--resume"))

    assert said == "did: again: what was the word?"
    _went_on(tmp_path, told)


def test_a_conversation_carried_on_is_carried_on_again_by_an_epic_naming_that_one(
    tmp_path: Path, project: Path
) -> None:
    earlier, name, _ = _talked(tmp_path, project)
    _said(_carries(tmp_path, "second", "--carry-on", f"earlier={earlier.name}/{name}"))
    epics = Hmz(project).epics
    middle = epics.all()[-1]
    ran = epics.read(middle)
    assert ran is not None
    (session,) = ran.sessions

    said = _said(
        _carries(
            tmp_path,
            "third",
            "--carry-on",
            f"earlier={middle.name}/{session.agent}/1",
        )
    )

    assert said == "did: third: what was the word?"
    _went_on(tmp_path, session.ident)


#: The same, but a flow whose second turn never ends, for its epic to be killed in.
HANGS = CARRIES.replace(
    'said = await worker.run("the word is papaya", session=session)',
    'said = await worker.run("the word is papaya", session=session)\n'
    '    said = await worker.run(\'run: [["sleep", "300"]]\', session=session)',
)


def test_a_conversation_is_carried_on_from_an_epic_killed_in_the_middle_of_a_turn(
    tmp_path: Path, project: Path
) -> None:
    write_flow(tmp_path / "flows", "carries", HANGS)
    killed = subprocess.Popen(
        [
            *(sys.executable, "-m", "hmz", "exec"),
            *("-f", str(tmp_path / "flows" / "carries"), "-a", f"worker={AGENT}"),
            *("-e", f"there=local/{tmp_path / 'there'}", "-p", "budget.cost=1"),
            "talk",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 90
        while not any(
            b"sleep" in one.read_bytes()
            for one in tmp_path.rglob("*.jsonl")
            if one.is_file()
        ):
            assert time.monotonic() < deadline, "the turn that never ends never began"
            time.sleep(0.5)
        # hmz alone, as a machine going down or an OOM kill takes it: no exit of its own.
        os.kill(killed.pid, signal.SIGKILL)
        killed.wait()
        epics = Hmz(project).epics
        earlier = epics.all()[-1]
        ran = epics.read(earlier)
        assert ran is not None
        (session,) = ran.sessions

        said = _said(
            _carries(
                tmp_path,
                "continue",
                "--carry-on",
                f"earlier={earlier.name}/{session.agent}/1",
            )
        )
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(killed.pid, signal.SIGKILL)

    assert said == "did: continue: what was the word?"
    _went_on(tmp_path, session.ident)


def test_a_conversation_is_carried_on_from_an_epic_whose_flow_failed(
    tmp_path: Path, project: Path
) -> None:
    earlier, name, told = _talked(tmp_path, project, "-p", "fail=true")

    said = _said(
        _carries(tmp_path, "continue", "--carry-on", f"earlier={earlier}/{name}")
    )

    assert said == "did: continue: what was the word?"
    _went_on(tmp_path, told)


def test_a_conversation_is_carried_on_where_no_epic_keeps_sessions_of_its_own(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_SESSIONS", "off")
    earlier, name, told = _talked(tmp_path, project)
    (held,) = (tmp_path / "claude").glob(f"projects/*/{told}.jsonl")
    before = held.read_bytes()

    said = _said(
        _carries(tmp_path, "continue", "--carry-on", f"earlier={earlier.name}/{name}")
    )

    assert said == "did: continue: what was the word?"
    _went_on(tmp_path, told)
    assert held.read_bytes() == before


@pytest.mark.parametrize(
    ("spelled", "refused"),
    [
        ("earlier=nope/{agent}/1", "no epic nope here"),
        ("earlier={epic}/{agent}/2", "opened no session {agent}/2"),
        ("earlier={epic}/nobody/1", "opened no session nobody/1"),
        ("earlier={epic}", "expected EPIC/AGENT/N"),
        ("earlier={epic}/{agent}/0", "expected EPIC/AGENT/N"),
        ("earlier={epic}/{agent}/\u00b2", "expected EPIC/AGENT/N"),
        ("earlier", "expected KEY=EPIC/AGENT/N"),
    ],
)
def test_a_conversation_that_cannot_be_carried_on_is_refused_before_the_flow_runs(
    tmp_path: Path, project: Path, spelled: str, refused: str
) -> None:
    earlier, name, _ = _talked(tmp_path, project)
    agent = name.partition("/")[0]
    asked = spelled.format(epic=earlier.name, agent=agent)

    ran = _carries(tmp_path, "continue", "--carry-on", asked)

    assert ran.returncode == 2
    assert refused.format(agent=agent) in ran.stderr
    assert len(started(tmp_path)) == 1
    assert len(Hmz(project).epics.all()) == 1


def test_a_key_given_twice_or_a_flow_keeping_no_state_is_refused(
    tmp_path: Path, project: Path
) -> None:
    earlier, name, _ = _talked(tmp_path, project)
    asked = f"earlier={earlier.name}/{name}"

    twice = _carries(tmp_path, "continue", "--carry-on", asked, "--carry-on", asked)
    write_flow(tmp_path / "flows", "forgets", FORGETS)
    stateless = hmz_exec(
        "-f",
        str(tmp_path / "flows" / "forgets"),
        "-a",
        f"worker={AGENT}",
        "-e",
        f"there=local/{tmp_path / 'there'}",
        "-p",
        "budget.cost=1",
        "--carry-on",
        asked,
        "continue",
    )

    assert twice.returncode == 2
    assert "--carry-on earlier: given twice" in twice.stderr
    assert stateless.returncode == 2
    assert (
        "keeps no state, so it has nowhere to carry a conversation on"
        in stateless.stderr
    )
    assert len(started(tmp_path)) == 1
