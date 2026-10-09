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

import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.providers import redirect
from hmz.sdk import Hmz
from tests.integration.doubles_core import AGENT, hmz_exec, install, started, write_flow

if TYPE_CHECKING:
    import subprocess
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
