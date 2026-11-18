"""A session one `hmz exec` kept in its flow's state, carried on by a later run picking it up.

Each run is a real `python -m hmz exec` driving the stand-in `claude`, which resumes a
conversation only from where Claude keeps one for the directory it is started in, and copies
the whole of it into a fork. So the later run's session answers from the conversation as it
stood when the state kept it only where Humanize copied it out then, brought the copy in
where the later run keeps its sessions, and carried it to the directory that turn works in.
Where a run keeps no sessions of its own (`HUMANIZE_SESSIONS=off`), that is the CLI's home, whose
conversation is never put back to a copy of it.

A chat (`hmz.runtime.chatting.Chat`) keeps its conversation the same way and nothing else: a
chat carried on is the same epic opened again, its conversation carried on from the files of it
the epic already holds.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import HarnessError
from hmz.runtime.chatting import Chat, ChatEnd, ChatSpec
from hmz.runtime.epic import SESSIONS, read
from hmz.runtime.epic import epics as held_in
from hmz.sdk import Hmz
from tests.integration.doubles_core import (
    AGENT,
    MODEL,
    hmz_exec,
    install,
    started,
    write_flow,
)

if TYPE_CHECKING:
    import subprocess
    from collections.abc import Sequence
    from pathlib import Path

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon")

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


# ------------------------------------------------------------------------------------ chats


class Person:
    """Says each line in turn, then nothing; shows nothing, asked nothing."""

    def __init__(self, *says: str) -> None:
        self.says = list(says)
        self.shown: list[str] = []

    async def next(self, answered: str) -> str:
        self.shown.append(answered)
        return self.says.pop(0) if self.says else ""

    async def ask(self, question: str, options: Sequence[str]) -> str | None:
        return None

    def shell(self, command: str, out: str, err: str, status: int) -> None:
        return


def _chat(
    project: Path, person: Person, task: str, agent: str = AGENT, **said: object
) -> ChatEnd:
    spec = ChatSpec(workspace=project, agent=agent, task=task, **said)  # pyright: ignore[reportArgumentType]
    return asyncio.run(Chat(spec, person=person).run())


def test_a_chat_talks_in_the_project_and_is_written_down_as_one(
    tmp_path: Path, project: Path
) -> None:
    person = Person("and then?")

    ended = _chat(project, person, "hello there", f"{AGENT}:high")

    assert person.shown == ["did: hello there", "did: and then?"]
    assert (project / "landed.txt").read_text() == "hello there\nand then?\n"
    (start,) = started(tmp_path)
    assert start["cwd"] == str(project.resolve())
    assert start["argv"][start["argv"].index("--model") + 1] == MODEL
    assert start["argv"][start["argv"].index("--effort") + 1] == "high"
    ran = read(ended.epic)
    assert ran is not None
    assert (ran.kind, ran.flow, ran.task, ran.how) == (
        "chat",
        "",
        "hello there",
        "stopped",
    )
    (drove,) = ran.agents
    assert drove.spec == f"{AGENT}:high"
    (session,) = ran.sessions
    assert (drove.agent, drove.name) == ("assistant", session.agent)
    assert session.ident == start["session"]
    assert ran.spent is not None
    assert ran.spent["output_tokens"] == 14


def test_a_chat_whose_first_turn_fails_ends_failed_with_what_the_cli_said(
    project: Path,
) -> None:
    with pytest.raises(HarnessError, match="it broke"):
        _chat(project, Person(), "fail: it broke")

    (at,) = held_in(project)
    ran = read(at)
    assert ran is not None
    assert ran.how == "failed"


def test_a_later_turn_that_fails_is_shown_as_failed_to_whoever_watches_the_chat(
    project: Path,
) -> None:
    first = _chat(project, Person(), "hello there")
    person = Person()
    spec = ChatSpec(
        workspace=project, agent=AGENT, task="fail: it broke", resume=first.epic
    )
    chat = Chat(spec, person=person)
    failed: list[str] = []
    chat.watch(
        lambda _agent, _session, event: (
            failed.append(event.text) if event.kind == "failed" else None
        )
    )

    asyncio.run(chat.run())

    # Said in the conversation, the chat going on, and shown once as the failure it is:
    # which is what `hmz chat` exits 1 on.
    (said,) = person.shown
    assert said.startswith("That turn could not be taken: ")
    (why,) = failed
    assert "it broke" in why
    assert said.endswith(why)


def test_a_chat_carried_on_is_the_same_epic_and_the_same_conversation(
    tmp_path: Path, project: Path
) -> None:
    first = _chat(project, Person(), "the word is papaya")
    (told,) = started(tmp_path)
    person = Person()

    again = _chat(project, person, "what was the word?", resume=first.epic)

    assert again.epic == first.epic
    assert held_in(project) == [first.epic]
    assert person.shown == ["did: what was the word?"]
    _, carried = started(tmp_path)
    argv = carried["argv"]
    assert argv[argv.index("--resume") + 1] == told["session"]
    assert "--fork-session" in argv
    ran = read(first.epic)
    assert ran is not None
    assert (ran.how, ran.task) == ("stopped", "the word is papaya")
    assert ran.reopened
    before, after = ran.sessions
    assert (before.ident, after.parent) == (told["session"], told["session"])
    (transcript,) = (first.epic / SESSIONS / "claude").glob(
        f"projects/*/{after.ident}.jsonl"
    )
    assert b"papaya" in transcript.read_bytes()
    assert ran.spent is not None
    assert ran.spent["output_tokens"] == 14


# ------------------------------------------------------------------- a chat's permission


def _withheld(start: dict[str, Any]) -> bool:
    """Whether a start of the stand-in was withheld its file-writing tools."""
    argv: list[str] = start["argv"]
    return "--disallowedTools" in argv and "Write" in " ".join(
        argv[argv.index("--disallowedTools") + 1 :]
    )


@pytest.mark.parametrize(
    ("permission", "writes"),
    [
        (None, True),
        ("read-only", False),
        ("workspace-write", True),
        ("danger-full-access", True),
    ],
)
def test_a_chat_tells_its_harness_what_its_permission_grants(
    permission: str | None, writes: bool, tmp_path: Path, project: Path
) -> None:
    said = {} if permission is None else {"permission": permission}
    # The user's own home, as one who has signed in has it: an assistant held to nothing is
    # put in no fence, which is what makes it for the stand-in to log its start in.
    (tmp_path / "claude").mkdir(exist_ok=True)

    ended = _chat(project, Person(), "hello there", **said)

    (start,) = started(tmp_path)
    assert _withheld(start) is not writes
    assert (project / "landed.txt").exists() is writes
    ran = read(ended.epic)
    assert ran is not None
    recorded = "" if permission in (None, "workspace-write") else permission
    assert ran.permission == recorded


def test_a_chat_set_to_another_permission_goes_on_under_it_in_its_conversation(
    tmp_path: Path, project: Path
) -> None:
    class Sets(Person):
        async def next(self, answered: str) -> str:
            if not self.shown:
                chat.permits("read-only")
            return await super().next(answered)

    person = Sets("what was the word?")
    chat = Chat(
        ChatSpec(workspace=project, agent=AGENT, task="the word is papaya"),
        person=person,
    )

    ended = asyncio.run(chat.run())

    assert person.shown == ["did: the word is papaya", "did: what was the word?"]
    first, second = started(tmp_path)
    assert (_withheld(first), _withheld(second)) == (False, True)
    argv = second["argv"]
    assert argv[argv.index("--resume") + 1] == first["session"]
    # Only what was said while it could write landed.
    assert (project / "landed.txt").read_text() == "the word is papaya\n"
    ran = read(ended.epic)
    assert ran is not None
    assert (ran.permission, len(ran.sessions)) == ("read-only", 2)
