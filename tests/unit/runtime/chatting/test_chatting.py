"""A chat: one assistant, one conversation, every line the person says the next turn of it."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, cast

import pytest

import hmz.coganchor.fence
from hmz.coganchor import prices, providers
from hmz.coganchor.agents.native import NativeCommand
from hmz.flows import (
    AskUserHookAgentMixin,
    AskUserHookResult,
    EnvBackendKind,
    HarnessKind,
    HarnessRefused,
    HookKind,
    SessionError,
    UnsupportedOperation,
    Usage,
)
from hmz.runtime import epic, flowing
from hmz.runtime.chatting import Chat, ChatEnd, ChatSpec, resolve
from hmz.runtime.flowing import harnesses
from hmz.runtime.flowing.spi import HookTable, Kept, Placement, TurnRequest
from hmz.runtime.runner import Refused
from hmz.runtime.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from hmz.runtime.flowing import SessionHandle
    from hmz.runtime.flowing.specs import AgentSpec


# ------------------------------------------------------------------------------- doubles


@dataclass
class Person:
    """Says each of `says` in turn, then nothing, which ends the chat."""

    says: list[str] = field(default_factory=list[str])
    answers: list[str | None] = field(default_factory=list[str | None])
    shown: list[str] = field(default_factory=list[str])
    asked: list[tuple[str, tuple[str, ...]]] = field(
        default_factory=list[tuple[str, tuple[str, ...]]]
    )
    shells: list[tuple[str, str, str, int]] = field(
        default_factory=list[tuple[str, str, str, int]]
    )

    async def next(self, answered: str) -> str:
        self.shown.append(answered)
        return self.says.pop(0) if self.says else ""

    async def ask(self, question: str, options: Sequence[str]) -> str | None:
        self.asked.append((question, tuple(options)))
        return self.answers.pop(0) if self.answers else None

    def shell(self, command: str, out: str, err: str, status: int) -> None:
        self.shells.append((command, out, err, status))


@dataclass
class Fence:
    open: bool = False


@dataclass
class Agent:
    """What a driver's session has behind it, as far as a chat asks: its fence."""

    fence: Fence | None
    epic: object = None

    def fenced(self) -> Fence | None:
        return self.fence


type Reply = Callable[[Session, TurnRequest], Awaitable[str]]


async def _did(session: Session, request: TurnRequest) -> str:
    return f"did: {request.prompt}"


@dataclass
class Session:
    driver: Driver
    ident: str
    carried: Kept | None
    hooks: HookTable
    agent: Agent | None = None
    requests: list[TurnRequest] = field(default_factory=list[TurnRequest])
    closed: bool = False

    @property
    def id(self) -> str | None:
        return self.ident if self.requests else None

    @property
    def usage(self) -> Usage:
        return Usage()

    def natives(self) -> list[NativeCommand]:
        return list(self.driver.catalog)

    async def turn(self, request: TurnRequest, sink: Any) -> str:
        self.requests.append(request)
        sink.add(cost=0.5, output_tokens=2, duration=1.0)
        return await self.driver.reply(self, request)

    def keep(self, sessions: Path) -> Kept:
        raise NotImplementedError

    async def move(self, placement: Placement) -> bool:
        return False

    async def steer(self, prompt: str, *, queued: bool) -> None:
        return

    def interrupt(self) -> None:
        return

    async def close(self) -> None:
        self.closed = True


@dataclass
class Driver:
    reply: Reply = _did
    catalog: list[NativeCommand] = field(default_factory=list[NativeCommand])
    capabilities: frozenset[type] = frozenset({AskUserHookAgentMixin})
    refuses_carrying: Exception | None = None
    fence: Fence | None = None
    sessions: list[Session] = field(default_factory=list[Session])
    opened: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    closes: int = 0
    name: str = "NeiKos496"
    harness: HarnessKind = HarnessKind.CLAUDE
    model: str = "haiku"
    effort: str = "low"
    provider: str = ""

    async def open(self, placement: Placement, **said: Any) -> Session:
        self.opened.append({"placement": placement, **said})
        carried: Kept | None = said.get("carry_on")
        if carried is not None and self.refuses_carrying is not None:
            raise self.refuses_carrying
        session = Session(
            self,
            f"s{len(self.sessions) + 1}",
            carried,
            said["hooks"],
            None if self.fence is None else Agent(self.fence),
        )
        self.sessions.append(session)
        return session

    async def close(self) -> None:
        self.closes += 1

    @property
    def requests(self) -> list[TurnRequest]:
        return [one for session in self.sessions for one in session.requests]

    @property
    def prompts(self) -> list[str]:
        return [one.prompt for one in self.requests]


@dataclass
class Env:
    workdir: Path
    ran: list[object] = field(default_factory=list[object])
    prints: tuple[int, str, str] = (0, "hello\n", "")
    closes: int = 0

    def placement(self) -> Placement:
        return Placement(EnvBackendKind.LOCAL, "", PurePosixPath(str(self.workdir)))

    async def exec(
        self,
        argv: object,
        *,
        timeout: float,  # noqa: ASYNC109 -- the env's own
    ) -> tuple[int, str, str]:
        self.ran.append(argv)
        return self.prints

    async def close(self) -> None:
        self.closes += 1


@dataclass
class Wired:
    driver: Driver
    env: Env
    workspace: Path
    flows: set[str] = field(default_factory=set[str])
    specs: list[AgentSpec] = field(default_factory=list["AgentSpec"])
    accounts: set[str] = field(default_factory=set[str])


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Wired:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    made = Wired(Driver(), Env(workspace.resolve()), workspace)

    def open_agent(spec: AgentSpec, harbors: object) -> Driver:
        made.specs.append(spec)
        return made.driver

    def local_env(at: Path) -> Env:
        return made.env

    def find(name: str) -> str:
        return "/flow" if name in made.flows else ""

    def refresh(*, wait: bool = False) -> bool:
        return False

    def account(cli: str, name: str) -> object:
        return object() if name in made.accounts else None

    monkeypatch.setattr(harnesses, "open_agent", open_agent)
    monkeypatch.setattr(flowing, "local_env", local_env, raising=False)
    monkeypatch.setattr(flowing, "find", find)
    monkeypatch.setattr(prices, "refresh", refresh)
    monkeypatch.setattr(providers, "find", account)
    return made


def _chat(wired: Wired, person: Person, **said: Any) -> Chat:
    spec = ChatSpec(
        workspace=wired.workspace,
        agent=said.pop("agent", "claude/haiku:low"),
        task=said.pop("task", "hi"),
        **said,
    )
    return Chat(spec, person=person)


def _had(wired: Wired, person: Person, **said: Any) -> ChatEnd:
    return asyncio.run(_chat(wired, person, **said).run())


def _events(at: Path) -> list[dict[str, Any]]:
    return [json.loads(one) for one in (at / epic.JOURNAL).read_text().splitlines()]


def _ran(at: Path) -> epic.Ran:
    ran = epic.read(at)
    assert ran is not None
    return ran


COMPACT = NativeCommand("/", "compact", "Compacts the conversation.", "call")
CONFIG = NativeCommand("/", "config", "Opens the settings.", "refuse")
SKILL = NativeCommand("$", "review", "Reviews the change.", "call")
BANG = NativeCommand("!", "", "Runs a shell command.", "emulate")
MENTION = NativeCommand("@", "", "Mentions a file.", "pass")


# --------------------------------------------------------------------------------- turns


def test_each_answer_is_shown_and_the_next_message_is_the_next_turn(
    wired: Wired,
) -> None:
    person = Person(["how are you?"])

    ended = _had(wired, person)

    assert wired.driver.prompts == ["hi", "how are you?"]
    assert person.shown == ["did: hi", "did: how are you?"]
    # One conversation, opened in the workspace, allowed the web, given no skill.
    (session,) = wired.driver.sessions
    (opened,) = wired.driver.opened
    assert opened["placement"].workdir == PurePosixPath(str(wired.env.workdir))
    assert opened["permission"].network is True
    assert opened["permission"].preset == "workspace-write"
    assert opened["skills"] == ()
    assert "carry_on" not in opened
    assert session.closed
    assert (wired.driver.closes, wired.env.closes) == (1, 1)
    assert ended == ChatEnd(ended.epic, "stopped")
    assert [str(one) for one in wired.specs] == ["assistant=claude/haiku:low"]


def test_a_chat_is_written_down_as_one_spending_without_a_budget(
    wired: Wired,
) -> None:
    ended = _had(wired, Person(["again"]))

    events = _events(ended.epic)
    began = events[0]
    assert began["kind"] == "chat"
    assert began["task"] == "hi"
    assert [one["agent"] for one in began["agents"]] == ["assistant"]
    for absent in ("flow", "params", "budget", "envs", "ref", "prefer"):
        assert absent not in began
    ran = _ran(ended.epic)
    assert (ran.chat, ran.how) == (True, "stopped")
    assert ran.spent == {"cost": 1.0, "output_tokens": 4, "seconds": 2.0}
    assert [one.ident for one in ran.sessions] == ["s1"]
    assert [one["event"] for one in events][-2:] == ["usage", "ended"]


def test_an_empty_first_message_ends_the_chat_with_no_turn(wired: Wired) -> None:
    person = Person()

    ended = _had(wired, person, task="")

    assert wired.driver.requests == []
    assert person.shown == []
    assert _ran(ended.epic).how == "stopped"


def test_a_first_turn_that_fails_ends_the_chat_failed_with_what_the_harness_said(
    wired: Wired,
) -> None:
    async def refuses(session: Session, request: TurnRequest) -> str:
        raise HarnessRefused("this account may not run haiku")

    wired.driver.reply = refuses
    person = Person(["never"])

    with pytest.raises(HarnessRefused, match="may not run haiku"):
        _had(wired, person)

    (at,) = epic.epics(wired.workspace)
    assert _ran(at).how == "failed"
    assert person.shown == []
    assert wired.driver.closes == 1


def test_a_later_turn_that_fails_is_said_and_the_chat_goes_on(wired: Wired) -> None:
    async def once(session: Session, request: TurnRequest) -> str:
        if request.prompt == "break":
            raise HarnessRefused("rate limited")
        return f"did: {request.prompt}"

    wired.driver.reply = once
    person = Person(["break", "again"])

    ended = _had(wired, person)

    assert person.shown == [
        "did: hi",
        "That turn could not be taken: rate limited",
        "did: again",
    ]
    assert _ran(ended.epic).how == "stopped"


def test_a_chat_the_host_lets_go_of_ends_stopped(wired: Wired) -> None:
    class Gone(Person):
        async def next(self, answered: str) -> str:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        _had(wired, Gone())

    (at,) = epic.epics(wired.workspace)
    assert _ran(at).how == "stopped"


def test_a_question_asked_mid_turn_is_put_to_the_person(wired: Wired) -> None:
    async def asks(session: Session, request: TurnRequest) -> str:
        said = await session.hooks.fire(
            HookKind.ASK_USER,
            cast("SessionHandle", session),
            question="Which?",
            options=("a", "b"),
        )
        assert isinstance(said, AskUserHookResult)
        return f"took {said.answer}"

    wired.driver.reply = asks
    person = Person(answers=["b"])

    _had(wired, person)

    assert person.asked == [("Which?", ("a", "b"))]
    assert person.shown == ["took b"]


def test_a_harness_that_cannot_ask_has_nothing_hung_on_it(wired: Wired) -> None:
    wired.driver.capabilities = frozenset()

    _had(wired, Person())

    (session,) = wired.driver.sessions
    assert HookKind.ASK_USER not in session.hooks


# ---------------------------------------------------------------------------- native input


def test_a_line_the_catalog_serves_is_a_native_turn_and_prose_is_not(
    wired: Wired,
) -> None:
    wired.driver.catalog = [COMPACT, MENTION]

    _had(wired, Person(["/compact now", "@README.md read it", "/clear", "plain"]))

    assert [(one.prompt, one.native) for one in wired.driver.requests] == [
        ("hi", False),
        ("/compact now", True),
        ("@README.md read it", True),
        # Kept for hmz, and served by a frontend: one that arrives is only words.
        ("/clear", False),
        ("plain", False),
    ]


def test_a_line_the_catalog_refuses_is_said_back_and_takes_no_turn(
    wired: Wired,
) -> None:
    wired.driver.catalog = [COMPACT, CONFIG]
    person = Person(["/config", "/nope", "go on"])

    _had(wired, person)

    assert wired.driver.prompts == ["hi", "go on"]
    assert person.shown[1:3] == [
        "/config is served only by the harness's own interactive interface",
        "no such command: /nope",
    ]


def test_a_bang_line_is_run_in_the_workspace_and_carried_into_the_next_turn(
    wired: Wired,
) -> None:
    wired.driver.catalog = [BANG]
    person = Person(["!echo hello", "what did it print?"])

    _had(wired, person)

    assert wired.env.ran == ["echo hello"]
    assert person.shells == [("echo hello", "hello\n", "", 0)]
    assert person.shown == ["did: hi", "", f"did: {wired.driver.prompts[-1]}"]
    assert wired.driver.prompts[1] == (
        "<bash-input>echo hello</bash-input>\n"
        "<bash-stdout>hello</bash-stdout><bash-stderr></bash-stderr>\n"
        "what did it print?"
    )
    assert len(wired.driver.requests) == 2


def test_what_a_bang_line_ran_waits_out_a_command_for_the_turn_after_it(
    wired: Wired,
) -> None:
    wired.driver.catalog = [BANG, COMPACT]

    _had(wired, Person(["!ls", "/compact", "and?"]))

    assert wired.driver.prompts[1] == "/compact"
    assert wired.driver.prompts[2].startswith("<bash-input>ls</bash-input>")
    assert wired.driver.prompts[2].endswith("\nand?")


def test_a_bang_line_is_held_to_the_assistants_fence(
    wired: Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.driver.catalog = [BANG]
    wired.driver.fence = Fence(open=False)

    def wrapper(fence: object) -> list[str]:
        return ["fence", "--"]

    monkeypatch.setattr(hmz.coganchor.fence, "wrapper", wrapper)

    _had(wired, Person(["!rm -rf /"]))

    assert wired.env.ran == [["fence", "--", "bash", "-c", "rm -rf /"]]


def test_a_bang_line_that_cannot_be_fenced_is_not_run(
    wired: Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.driver.catalog = [BANG]
    wired.driver.fence = Fence(open=False)

    def nothing(fence: object) -> list[str]:
        raise FileNotFoundError("no coganchor for this machine")

    monkeypatch.setattr(hmz.coganchor.fence, "wrapper", nothing)
    person = Person(["!rm -rf /"])

    _had(wired, person)

    assert wired.env.ran == []
    ((command, out, err, status),) = person.shells
    assert (command, out, status) == ("rm -rf /", "", 126)
    assert "could not be confined" in err


def test_a_bang_line_for_an_open_fence_is_run_as_it_is(wired: Wired) -> None:
    wired.driver.catalog = [BANG]
    wired.driver.fence = Fence(open=True)

    _had(wired, Person(["!pwd"]))

    assert wired.env.ran == ["pwd"]


def test_a_dollar_name_that_is_both_goes_by_the_chats_preference(
    wired: Wired,
) -> None:
    wired.driver.catalog = [SKILL]
    wired.flows.add("review")
    chat = _chat(wired, Person(["$review it", "$review again"]))

    class Toggles(Person):
        async def next(self, answered: str) -> str:
            if len(self.shown) == 1:
                chat.prefers("flow")
            return await super().next(answered)

    chat.person = Toggles(["$review it", "$review again"])
    asyncio.run(chat.run())

    assert [(one.prompt, one.native) for one in wired.driver.requests] == [
        ("hi", False),
        # Native, as nobody said otherwise; then a flow, which a frontend serves: words.
        ("$review it", True),
        ("$review again", False),
    ]
    assert chat.prefer == "flow"
    assert chat.epic is not None
    sets = [one for one in _events(chat.epic) if one["event"] == "set"]
    assert [one["prefer"] for one in sets] == ["flow"]
    assert _ran(chat.epic).prefer == "flow"


def test_the_persons_setting_decides_where_the_chat_has_no_preference(
    wired: Wired,
) -> None:
    wired.driver.catalog = [SKILL]
    wired.flows.add("review")
    Settings(wired.workspace).chat_prefer = "flow"

    _had(wired, Person(["$review it", "$other"]))

    assert [one.native for one in wired.driver.requests] == [False, False, False]


def test_a_preference_set_before_the_chat_runs_is_where_it_began(
    wired: Wired,
) -> None:
    chat = _chat(wired, Person())
    chat.prefers("flow")

    with pytest.raises(ValueError, match="native or flow"):
        chat.prefers("both")  # pyright: ignore[reportArgumentType]
    ended = asyncio.run(chat.run())

    assert _events(ended.epic)[0]["prefer"] == "flow"


def test_the_catalog_is_the_open_conversations(wired: Wired) -> None:
    wired.driver.catalog = [COMPACT]
    chat = _chat(wired, Person())
    seen: list[list[NativeCommand]] = []

    async def looks(session: Session, request: TurnRequest) -> str:
        seen.append(chat.natives())
        return "ok"

    wired.driver.reply = looks
    assert chat.natives() == []

    asyncio.run(chat.run())

    assert seen == [[COMPACT]]


# ---------------------------------------------------------------------------- refusals


def test_an_agent_that_cannot_be_read_is_refused_before_any_epic(
    wired: Wired,
) -> None:
    with pytest.raises(Refused):
        _had(wired, Person(), agent="no such thing")
    with pytest.raises(Refused, match="no claude account called 'work'"):
        _had(wired, Person(), agent="claude@work/haiku:low")

    assert epic.epics(wired.workspace) == []
    assert wired.driver.opened == []


# ------------------------------------------------------------------------------ carrying on


def test_a_chat_carried_on_goes_on_in_its_epic_and_its_conversation(
    wired: Wired,
) -> None:
    first = _had(wired, Person(["more"]), prefer="flow")
    person = Person()

    again = _had(wired, person, task="and now?", resume=first.epic)

    assert again.epic == first.epic
    assert epic.epics(wired.workspace) == [first.epic]
    _, carried = wired.driver.sessions
    assert carried.carried == Kept(
        HarnessKind.CLAUDE, "s1", first.epic / epic.SESSIONS / "claude"
    )
    assert carried.requests[0].prompt == "and now?"
    assert person.shown == ["did: and now?"]
    events = _events(first.epic)
    assert [one["event"] for one in events].count("reopened") == 1
    assert [one["event"] for one in events].count("began") == 1
    ran = _ran(first.epic)
    assert (ran.how, ran.prefer) == ("stopped", "flow")
    assert ran.spent == {"cost": 1.5, "output_tokens": 6, "seconds": 3.0}


def test_a_chat_carried_on_with_another_agent_says_so(wired: Wired) -> None:
    first = _had(wired, Person())

    _had(wired, Person(), task="go", resume=first.epic, agent="claude/opus:high")

    sets = [one for one in _events(first.epic) if one["event"] == "set"]
    assert [one["agents"][0]["model"] for one in sets] == ["opus"]
    assert _ran(first.epic).agents[0].model == "opus"


def test_a_conversation_that_cannot_be_carried_on_is_a_new_one_that_says_why(
    wired: Wired,
) -> None:
    first = _had(wired, Person())
    wired.driver.refuses_carrying = UnsupportedOperation("cannot fork")
    person = Person()

    again = _had(wired, person, task="go", resume=first.epic)

    assert again.epic == first.epic
    assert wired.driver.sessions[-1].carried is None
    assert person.shown == [
        (
            "This conversation could not be carried on (cannot fork), so this is a new "
            "one.\n\ndid: go"
        )
    ]


def test_a_carried_conversation_whose_first_turn_cannot_go_on_is_put_down(
    wired: Wired,
) -> None:
    first = _had(wired, Person())

    async def lost(session: Session, request: TurnRequest) -> str:
        if session.carried is not None:
            raise SessionError("no conversation s1 under it")
        return f"did: {request.prompt}"

    wired.driver.reply = lost
    person = Person()

    _had(wired, person, task="go", resume=first.epic)

    assert [one.carried is None for one in wired.driver.sessions] == [
        True,
        False,
        True,
    ]
    assert person.shown == [
        (
            "This conversation could not be carried on (no conversation s1 under it), "
            "so this is a new one.\n\ndid: go"
        )
    ]
    assert _ran(first.epic).how == "stopped"


def test_a_first_turn_carried_on_that_fails_is_said(wired: Wired) -> None:
    first = _had(wired, Person())

    async def refuses(session: Session, request: TurnRequest) -> str:
        raise HarnessRefused("out of credit")

    wired.driver.reply = refuses
    person = Person()

    _had(wired, person, task="go", resume=first.epic)

    assert person.shown == ["That turn could not be taken: out of credit"]


def test_a_chat_with_no_conversation_kept_is_carried_on_in_a_new_one(
    wired: Wired,
) -> None:
    first = _had(wired, Person(), task="")
    person = Person()

    _had(wired, person, task="go", resume=first.epic)

    assert person.shown[0].startswith(
        "This conversation could not be carried on (it was not kept as it stopped)"
    )


def test_a_chat_an_earlier_humanize_wrote_as_the_flow_chat_is_carried_on(
    wired: Wired,
) -> None:
    at = epic.under(wired.workspace) / "20260101T000000.000Z-abcdef"
    at.mkdir(parents=True)
    written: list[dict[str, Any]] = [
        {
            "event": "began",
            "flow": "chat",
            "task": "hi",
            "workspace": str(wired.workspace.resolve()),
            "resumable": True,
            "agents": [],
        },
        {
            "event": "opened",
            "at": "2026-01-01T00:00:01Z",
            "agent": "x",
            "backend": "claude",
            "session": "old",
            "where": "sessions/claude",
        },
        {"event": "ended", "how": "done"},
    ]
    (at / epic.JOURNAL).write_text("".join(json.dumps(one) + "\n" for one in written))

    _had(wired, Person(), task="go", resume=at)

    assert wired.driver.sessions[0].carried == Kept(
        HarnessKind.CLAUDE, "old", at / "sessions" / "claude"
    )
    assert [one["event"] for one in _events(at)].count("reopened") == 1


def test_what_is_not_a_chat_here_is_not_carried_on(wired: Wired) -> None:
    with epic.Epic("ralph", "t", wired.workspace) as flow:
        pass
    elsewhere = wired.workspace.parent / "other"
    elsewhere.mkdir()
    with epic.Epic("", "t", elsewhere, kind="chat") as other:
        other.stopped()

    with pytest.raises(Refused, match="is not a chat"):
        _had(wired, Person(), resume=flow.path)
    with pytest.raises(Refused, match="cannot be continued here"):
        _had(wired, Person(), resume=other.path)
    with (
        epic.Epic("", "t", wired.workspace, kind="chat") as going,
        pytest.raises(Refused, match="is going on already"),
    ):
        _had(wired, Person(), resume=going.path)
    assert wired.driver.opened == []


def test_a_preference_set_once_the_chat_has_ended_writes_nothing_after_its_end(
    wired: Wired,
) -> None:
    chat = _chat(wired, Person())
    ended = asyncio.run(chat.run())

    chat.prefers("flow")

    assert chat.prefer == "flow"
    assert _events(ended.epic)[-1]["event"] == "ended"


def test_a_slash_name_is_said_until_the_harness_has_listed_its_catalogue() -> None:
    # pi lists `/compact` before it has been asked for its own commands.
    early = [NativeCommand("/", "compact", "compacts", "call")]

    before = resolve(
        "/fix-tests now", catalog=early, flows=(), prefer="native", listed=False
    )
    after = resolve("/fix-tests now", catalog=early, flows=(), prefer="native")

    assert before.kind == "prose"
    assert (after.kind, after.why) == ("refused", "no such command: /fix-tests")
    # What it does list is served either way.
    listed = resolve("/compact", catalog=early, flows=(), prefer="native", listed=False)
    assert (listed.kind, listed.entry) == ("native", early[0])
