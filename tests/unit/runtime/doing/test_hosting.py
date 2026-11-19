"""One workspace's runs, shared by every frontend attached to them."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pytest

from hmz.flows import Budget, BudgetExceeded, FlowNotFound, Usage
from hmz.runtime import Host, Refused, flowing
from hmz.runtime.chatting import ChatEnd
from hmz.runtime.doing import hosting
from hmz.runtime.doing.hosting import record

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

#: How long a test waits for something another thread is doing.
PATIENCE = 10.0


# ------------------------------------------------------------------ the record


@dataclass
class Config:
    model: str = "opus"
    machine: object = None


@dataclass(eq=False)
class Session:
    """One conversation, as far as the host reads one."""

    named: str | None = None
    forks: bool = False
    said: list[str] = field(default_factory=list[str])
    refuses: BaseException | None = None
    given: threading.Event = field(default_factory=threading.Event)

    def interject(self, text: str) -> None:
        self.said.append(text)
        self.given.set()
        if self.refuses is not None:
            raise self.refuses

    def close(self) -> None:
        pass


@dataclass(eq=False)
class Agent:
    """A coganchor agent, as far as the host reads one."""

    counts: frozenset[str] = frozenset({"turns"})

    #: Its own name, not the role it fills.
    id: str = "NeiKos496"
    backend: str = "claude"
    config: Config = field(default_factory=Config)
    sessions: list[Session] = field(default_factory=list[Session])
    waiting: object = None

    def kept(self) -> Path | None:
        return None


@dataclass
class Event:
    kind: str = "text"
    text: str = ""
    whose: str = "agent"
    tokens: dict[str, int] = field(default_factory=dict[str, int])
    spent: dict[str, float] = field(default_factory=dict[str, float])


def _record(
    agent: Agent, session: Session | None, event: Event, **said: Any
) -> dict[str, Any]:
    return record(cast("Any", agent), cast("Any", session), cast("Any", event), **said)


def test_an_event_is_written_down_the_one_way_every_frontend_reads_it() -> None:
    said = _record(
        Agent(),
        Session(named="abc"),
        Event("result", "done", tokens={"out": 3}, spent={"cost": 0.5}),
        key="NeiKos496/2",
        run=3,
    )

    assert set(said) == {
        "type",
        "run",
        "key",
        "session",
        "agent",
        "cli",
        "model",
        "ident",
        "kind",
        "text",
        "whose",
        "tokens",
        "spent",
        "at",
        "mono",
    }
    assert said["type"] == "event"
    assert (said["run"], said["key"], said["session"]) == (
        3,
        "NeiKos496/2",
        "NeiKos496/2",
    )
    assert (said["agent"], said["cli"], said["model"]) == (
        "NeiKos496",
        "claude",
        "opus",
    )
    assert (said["ident"], said["kind"], said["text"]) == ("abc", "result", "done")
    assert (said["tokens"], said["spent"]) == ({"out": 3}, {"cost": 0.5})


def test_what_the_agent_said_for_every_conversation_names_none() -> None:
    said = _record(Agent(), None, Event(), key="NeiKos496")

    assert (said["session"], said["ident"], said["run"]) == ("", "", 0)
    assert _record(Agent(), Session(), Event())["ident"] == ""


# ------------------------------------------------------------------ doubles


@dataclass(frozen=True)
class Role:
    name: str
    auto: bool = False


@dataclass
class Declaration:
    agents: tuple[Role, ...] = (Role("builder"), Role("outworlder", auto=True))


@dataclass(eq=False)
class FakeRun:
    """A run the host drives, held going until it is let go of or stopped."""

    flow: str = "ralph"
    ref: str = "official/ralph"
    kind: str = "flow"
    declaration: Declaration = field(default_factory=Declaration)
    budget: Budget = field(default_factory=lambda: Budget(cost=2.0))
    usage: Usage = field(default_factory=lambda: Usage(cost=0.5))
    profile_flow: bool = False
    profile_environment: bool = False
    backup: tuple[str, ...] = ()
    epic: Path | None = None
    blind: str = ""
    raises: BaseException | None = None
    agents: list[Agent] = field(default_factory=list[Agent])
    names: dict[str, str] = field(default_factory=lambda: {"builder": "NeiKos496"})
    listener: Callable[..., None] | None = None
    opener: Callable[..., None] | None = None
    noticer: Callable[[str], None] | None = None
    going: threading.Event = field(default_factory=threading.Event)
    released: threading.Event = field(default_factory=threading.Event)
    stopped: bool = False
    lingers: bool = False
    #: What the run holds, as its engine lists it: None for nothing yet.
    envs: Any = None
    closed: int = 0

    def watch(self, listener: Callable[..., None]) -> None:
        self.listener = listener

    def opened(self, callback: Callable[..., None]) -> None:
        self.opener = callback

    def noticed(self, callback: Callable[[str], None]) -> None:
        self.noticer = callback

    def unreadable(self) -> str:
        return self.blind

    def run(self) -> None:
        self.going.set()
        assert self.released.wait(PATIENCE), "the test never let the run go"
        if self.stopped:
            raise asyncio.CancelledError
        if self.raises is not None:
            raise self.raises

    def stop(self) -> None:
        self.stopped = True
        if not self.lingers:
            self.released.set()

    def close(self) -> None:
        self.closed += 1
        self.stopped = True
        self.released.set()


@dataclass(frozen=True)
class Native:
    """One entry of a harness's native catalogue, as far as a chat's host reads one."""

    sigil: str
    name: str
    about: str
    how: str


@dataclass(frozen=True)
class Offered:
    """One flow on offer, as far as a chat's host reads one."""

    name: str
    about: str = ""


@dataclass(eq=False)
class FakeChat:
    """The chat a host has, as far as the host reads one: its preference and catalogue."""

    prefer: str | None = None
    permission: str | None = "workspace-write"
    catalog: list[Native] = field(default_factory=list[Native])
    listed: bool = True
    #: Whether it is between turns, where it says so before it asks what to say next.
    between: bool = False

    def prefers(self, prefer: str) -> None:
        self.prefer = prefer

    def permits(self, permission: str) -> None:
        self.permission = permission

    def natives(self) -> list[Native]:
        return list(self.catalog)


@dataclass(eq=False)
class FakeChatting:
    """A chat held as a run is, talking to its person: each line said answered by an echo.

    Before a turn it asks what `asks` holds, one question a turn; it ends on an empty line,
    or fails as `fails` says before it has an epic.
    """

    agent: str
    task: str
    person: Any
    resume: Path | None = None
    prefer: str | None = None
    kind: str = "chat"
    flow: str = ""
    ref: str = ""
    budget: None = None
    usage: Usage = field(default_factory=Usage)
    profile_flow: bool = False
    profile_environment: bool = False
    backup: tuple[str, ...] = ()
    agents: list[Agent] = field(default_factory=list[Agent])
    epic: Path | None = None
    names_epic: bool = True
    chat: FakeChat = field(default_factory=FakeChat)
    asks: list[tuple[str, tuple[str, ...]]] = field(
        default_factory=list[tuple[str, tuple[str, ...]]]
    )
    answers: list[str | None] = field(default_factory=list[str | None])
    lines: list[str] = field(default_factory=list[str])
    fails: BaseException | None = None
    going: threading.Event = field(default_factory=threading.Event)
    stopped: bool = False
    #: Whether a turn is going, which `interrupt` stops; and how many it stopped.
    turning: bool = False
    interrupted: int = 0

    def interrupt(self) -> bool:
        if not self.turning:
            return False
        self.turning = False
        self.interrupted += 1
        return True

    def watch(self, listener: Callable[..., None]) -> None:
        del listener

    def opened(self, callback: Callable[..., None]) -> None:
        del callback

    def noticed(self, callback: Callable[[str], None]) -> None:
        del callback

    def unreadable(self) -> str:
        return ""

    def run(self) -> ChatEnd:
        self.going.set()
        if self.fails is not None:
            raise self.fails
        self.epic = self.epic or Path("/epics/20260101-chat")
        return asyncio.run(self._talks())

    async def _talks(self) -> ChatEnd:
        said = self.task
        while said:
            if self.asks:
                question, options = self.asks.pop(0)
                self.answers.append(await self.person.ask(question, options))
            said = await self.person.next(f"you said {said}")
            self.lines.append(said)
        assert self.epic is not None
        return ChatEnd(self.epic, "stopped")

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.stopped = True


@dataclass
class Flows:
    calls: tuple[Any, ...] = ()
    broken: bool = False
    offered: tuple[Offered, ...] = ()

    def all(self) -> tuple[Offered, ...]:
        return self.offered

    def running(self) -> tuple[Any, ...]:
        if self.broken:
            raise RuntimeError("no tree")
        return self.calls


@dataclass
class Epics:
    """The epics of a workspace, as far as starting a chat reads them: its chats, by name."""

    kept: dict[str, Path] = field(default_factory=dict[str, Path])

    def chat(self, said: str) -> Path | None:
        return self.kept.get(said)

    def read(self, epic: Path) -> Any:
        from types import SimpleNamespace

        del epic
        return SimpleNamespace(
            agents=[SimpleNamespace(spec="claude/opus:high")], permission="read-only"
        )


@dataclass
class Workspace:
    """The `Hmz` a host is made for, as far as the host reads one."""

    workspace: Path
    flows: Flows = field(default_factory=Flows)
    epics: Epics = field(default_factory=Epics)
    runs: list[FakeRun] = field(default_factory=list[FakeRun])
    asked: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    refuses: BaseException | None = None
    next_run: FakeRun | None = None
    chats: list[FakeChatting] = field(default_factory=list[FakeChatting])
    asked_chats: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    failing: BaseException | None = None

    def chat(
        self,
        agent: str,
        task: str,
        *,
        person: Any,
        resume: str | None = None,
        prefer: str | None = None,
        role: Any = None,
        permission: str | None = None,
    ) -> FakeChatting:
        self.asked_chats.append(
            {"agent": agent, "task": task, "resume": resume, "prefer": prefer}
            | ({} if role is None else {"role": role})
            | ({} if permission is None else {"permission": permission})
        )
        made = FakeChatting(
            agent,
            task,
            person,
            resume=Path(resume) if resume else None,
            prefer=prefer,
            epic=Path(resume) if resume else None,
            fails=self.failing,
        )
        self.chats.append(made)
        return made

    def run(self, flow: str, task: str, **said: Any) -> FakeRun:
        if self.refuses is not None:
            raise self.refuses
        self.asked.append({"flow": flow, "task": task, **said})
        made = self.next_run or FakeRun(flow=flow)
        self.next_run = None
        self.runs.append(made)
        return made


@dataclass
class Outworlders:
    """What the host hands a run for whoever is outside it: `ask`, `away`, `show`, `faces`."""

    ask: Callable[[Any], str | None] | None = None
    away: Callable[[str], bool] | None = None
    show: Callable[[str, str, tuple[dict[str, Any], ...]], None] | None = None
    faces: Callable[[Any], None] | None = None

    def __call__(
        self,
        *,
        ask: Callable[[Any], str | None],
        away: Callable[[str], bool],
        show: Callable[[str, str, tuple[dict[str, Any], ...]], None],
        faces: Callable[[Any], None],
    ) -> str:
        self.ask, self.away, self.show, self.faces = ask, away, show, faces
        return "outworlder"


class Told:
    """One frontend's end: everything it has been told, in the order it was told."""

    def __init__(
        self,
        host: Host,
        name: str = "",
        *,
        replay: bool = True,
        since: tuple[str, int] | None = None,
    ) -> None:
        self.seen: list[dict[str, Any]] = []
        self._landed = threading.Condition()
        self.host = host
        self.client = host.attach(name, "sdk", self._told, replay=replay, since=since)

    def _told(self, message: dict[str, Any]) -> None:
        with self._landed:
            self.seen.append(message)
            self._landed.notify_all()

    def waits(self, what: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        """The first message it was told that `what` says yes to, waited for."""
        with self._landed:
            found = self._landed.wait_for(
                lambda: next((one for one in self.seen if what(one)), None),
                timeout=PATIENCE,
            )
        assert found is not None, f"never told: {[one['type'] for one in self.seen]}"
        return found

    def told(self, kind: str, /, **fields: Any) -> dict[str, Any]:
        """The first message of a kind saying all of `fields`, waited for."""
        return self.waits(
            lambda one: (
                one["type"] == kind
                and all(one.get(key) == value for key, value in fields.items())
            )
        )

    def snapshot(self) -> list[dict[str, Any]]:
        """What it has been told so far."""
        with self._landed:
            return list(self.seen)

    def asks(self, do: str, **said: Any) -> dict[str, Any]:
        return self.host.asked(self.client, {"do": do, **said})


@pytest.fixture
def where(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path)


@pytest.fixture
def outworlders(monkeypatch: pytest.MonkeyPatch) -> Outworlders:
    made = Outworlders()
    monkeypatch.setattr(flowing, "open_outworlder", made, raising=False)
    return made


@pytest.fixture
def host(where: Workspace, outworlders: Outworlders) -> Iterator[Host]:
    made = Host(cast("Any", where))
    try:
        yield made
    finally:
        made.close()
        for one in where.runs:
            one.released.set()


def _started(alice: Told, where: Workspace, **said: Any) -> FakeRun:
    assert alice.asks("start", flow="ralph", task="fix it", **said) == {
        "ok": True,
        "run": len(where.runs),
    }
    run = where.runs[-1]
    assert run.going.wait(PATIENCE)
    return run


# ------------------------------------------------------------------ frontends


def test_a_frontend_is_told_who_it_is_then_the_run_then_how_things_stand(
    host: Host, where: Workspace
) -> None:
    host.printed("before anybody")

    alice = Told(host, "alice")
    alice.told("live")

    seen = alice.snapshot()
    kinds = [one["type"] for one in seen]
    welcome = seen[0]
    assert welcome["type"] == "welcome"
    assert welcome["name"] == "alice"
    assert welcome["client"] == alice.client
    assert welcome["kind"] == "sdk"
    assert welcome["workspace"] == str(where.workspace)
    assert welcome["protocol"] == "3.0.0"
    assert welcome["epoch"] == host.epoch
    assert kinds[1] == "printed"
    assert seen[1]["text"] == "before anybody"
    assert kinds[-1] == "live"
    assert {
        "clients",
        "claims",
        "away",
        "run",
        "sessions",
        "waiting",
        "pending",
        "usage",
    } <= set(kinds)
    assert alice.seen[-1]["elided"] == 0


def test_a_frontend_that_wants_no_replay_is_told_only_from_here(host: Host) -> None:
    host.printed("before")

    late = Told(host, "late", replay=False)
    late.told("live")
    host.printed("after")
    late.told("printed", text="after")

    assert [one["text"] for one in late.seen if one["type"] == "printed"] == ["after"]


def test_a_frontend_attaching_again_since_a_record_is_told_only_those_after_it(
    host: Host,
) -> None:
    host.printed("one")
    host.printed("two")
    first = Told(host, "first")
    seq = first.told("printed", text="two")["seq"]
    host.printed("three")

    again = Told(host, "again", replay=False, since=(host.epoch, seq))
    again.told("live")

    assert [one["text"] for one in again.seen if one["type"] == "printed"] == ["three"]


def test_a_frontend_attaching_again_to_another_life_of_its_host_is_told_everything(
    host: Host,
) -> None:
    host.printed("one")

    again = Told(host, "again", since=("another", 1))
    again.told("live")

    assert [one["text"] for one in again.seen if one["type"] == "printed"] == ["one"]


def test_the_same_name_twice_is_told_apart(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_NAME", "dana")

    first, second, third = Told(host), Told(host), Told(host, "dana@sdk")

    assert first.told("welcome")["name"] == "dana@sdk"
    assert second.told("welcome")["name"] == "dana@sdk#2"
    assert third.told("welcome")["name"] == "dana@sdk#3"
    assert host.attached == 3


def test_everybody_hears_who_else_is_attached_and_who_went(host: Host) -> None:
    alice = Told(host, "alice")
    bob = Told(host, "bob")
    alice.waits(
        lambda one: (
            one["type"] == "clients"
            and [each["name"] for each in one["clients"]] == ["alice", "bob"]
        )
    )

    host.detach(bob.client)

    assert bob.told("gone")["why"] == "let go"
    alice.waits(
        lambda one: (
            one["type"] == "clients"
            and [each["name"] for each in one["clients"]] == ["alice"]
        )
    )
    assert host.attached == 1
    assert bob.asks("status") == {"ok": False, "why": "this frontend is not attached"}


def test_a_frontend_can_ask_to_be_let_go(host: Host) -> None:
    alice = Told(host, "alice")

    assert alice.asks("detach") == {"ok": True}
    assert host.attached == 0


def test_a_request_nobody_knows_is_refused(host: Host) -> None:
    alice = Told(host, "alice")

    assert alice.asks("dance") == {"ok": False, "why": "no such request: 'dance'"}
    assert host.asked(alice.client, {}) == {"ok": False, "why": "no such request: None"}


def test_a_host_with_nobody_and_nothing_is_idle(host: Host) -> None:
    assert host.idle is True
    alice = Told(host, "alice")
    assert host.idle is False
    host.detach(alice.client)
    assert host.idle is True


def test_what_is_too_long_to_carry_is_cut_and_counted(host: Host) -> None:
    alice = Told(host, "alice")

    host.printed("x" * (256 * 1024 + 5))

    said = alice.told("printed")["text"]
    assert said.endswith("… (5 more characters)")


# ------------------------------------------------------------------ status


def test_a_host_with_no_run_says_so(host: Host, where: Workspace) -> None:
    Told(host, "alice")

    said = host.status()

    assert said["attached"] == 1
    assert said["clients"][0]["name"] == "alice"
    assert (said["state"], said["run"], said["flow"]) == ("idle", 0, "")
    assert (said["budget"], said["usage"]) == (None, None)
    assert (said["flows"], said["calls"]) == ([], [])
    assert host.epic is None


@dataclass(eq=False)
class Live:
    ref: str
    name: str = "f"
    depth: int = 0
    since: float = 0.0
    id: int = 1
    parent: Live | None = None


def test_the_flows_running_are_said_as_a_tree(host: Host, where: Workspace) -> None:
    top = Live("official/ralph")
    where.flows.calls = (top, Live("official/inner", depth=1, id=2, parent=top))

    said = host.status()

    assert said["flows"] == ["official/ralph", "official/inner"]
    assert [one["parent"] for one in said["calls"]] == [None, 0]
    assert all("seconds" in one for one in said["calls"])


def test_a_tree_nobody_could_read_is_no_flows(host: Host, where: Workspace) -> None:
    where.flows.broken = True

    assert host.status()["flows"] == []


# ------------------------------------------------------------------ runs


def test_a_flow_started_is_said_to_every_frontend(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")

    run = _started(
        alice,
        where,
        agents={"builder": "claude/opus"},
        envs={"box": "local/x"},
        params={"rounds": 2},
        budget={"cost": 2},
        profile_flow=True,
        profile_environment=True,
        resume=True,
    )

    started = bob.told("started")
    assert started["run"] == 1
    assert (started["flow"], started["ref"], started["task"]) == (
        "ralph",
        "official/ralph",
        "fix it",
    )
    assert (started["by"], started["client"]) == ("alice", alice.client)
    assert started["roles"] == ["builder"]
    assert started["names"] == {"builder": "NeiKos496"}
    assert started["outworlders"] == ["outworlder"]
    assert started["agents"] == {"builder": "claude/opus"}
    assert started["envs"] == {"box": "local/x"}
    assert started["params"] == {"rounds": 2}
    assert started["budget"]["cost"] == 2.0
    assert started["resume"] == "True"
    asked = where.asked[0]
    assert asked["budget"] == {"cost": 2}
    assert (asked["profile_flow"], asked["profile_environment"]) == (True, True)
    assert asked["outworlder"] == "outworlder"
    bob.told("run", state="running", run=1)
    said = host.status()
    assert (said["state"], said["run"], said["flow"]) == ("running", 1, "ralph")
    assert said["budget"]["cost"] == 2.0
    assert said["usage"]["cost"] == 0.5
    assert host.idle is False
    # Whoever is outside the run is every frontend here, and nobody is away yet.
    assert outworlders.away is not None
    assert outworlders.away("outworlder") is False
    run.released.set()
    bob.told("ended", run=1, how="done", why="")


@pytest.mark.parametrize("said", [{}, {"flow": ""}, {"flow": 3}])
def test_a_start_naming_no_flow_is_refused(said: dict[str, Any], host: Host) -> None:
    assert Told(host, "alice").asks("start", **said) == {
        "ok": False,
        "why": "a flow to start is named",
    }


def test_a_flow_that_will_not_start_is_said_as_why(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    where.refuses = Refused("ralph needs an agent for 'builder'")

    assert alice.asks("start", flow="ralph") == {
        "ok": False,
        "why": "ralph needs an agent for 'builder'",
    }
    # And it is not left starting.
    where.refuses = None
    _started(alice, where).released.set()


def test_the_backup_targets_a_flow_is_started_with_go_to_the_run(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    assert alice.asks("start", flow="ralph", backup="lab") == {
        "ok": False,
        "why": "backup is a list of backup target names",
    }

    _started(alice, where, backup=["lab"]).released.set()
    _ = alice.told("ended", run=1)
    _started(alice, where).released.set()

    assert [one["backup"] for one in where.asked] == [["lab"], None]


def test_one_flow_runs_at_a_time(host: Host, where: Workspace) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)

    assert alice.asks("start", flow="other") == {
        "ok": False,
        "why": "a flow is already running",
    }
    run.released.set()
    alice.told("ended", run=1)
    second = _started(alice, where)
    alice.told("started", run=2)
    second.released.set()


def test_an_env_is_asked_of_the_run_going_attaching_nobody(
    host: Host, where: Workspace
) -> None:
    no_flow = {"ok": False, "why": "no flow is running, so no env is open", "code": 409}
    assert host.env({"do": "hosts.env.list"}) == no_flow
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert host.env({"do": "hosts.env.list"}) == no_flow

    driver = SimpleNamespace(backend="local", workdir="/w", capabilities=frozenset())
    run.envs = SimpleNamespace(loop=None, env_roles=lambda: {"box": driver})

    assert host.env({"do": "hosts.env.list"}) == {
        "ok": True,
        "envs": [{"name": "box", "kind": "local", "workdir": "/w", "can": []}],
    }
    assert host.status()["attached"] == 1
    run.released.set()


@pytest.mark.parametrize(
    ("raised", "how", "why"),
    [
        (None, "done", ""),
        (Refused("not that"), "refused", "not that"),
        (BudgetExceeded("spent"), "budget", "spent"),
        (FlowNotFound("gone"), "failed", "FlowNotFound: gone"),
    ],
)
def test_a_run_ending_says_how(
    raised: BaseException | None, how: str, why: str, host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    where.next_run = FakeRun(raises=raised)

    _started(alice, where).released.set()

    ended = alice.told("ended", run=1)
    assert (ended["how"], ended["why"]) == (how, why)
    alice.told("run", state="idle", run=1)
    # What it spent, as it stood when it ended.
    alice.waits(lambda one: one["type"] == "usage" and one["usage"] is not None)


def test_a_run_that_crashed_says_where(host: Host, where: Workspace) -> None:
    alice = Told(host, "alice")
    where.next_run = FakeRun(raises=ZeroDivisionError("oops"))

    _started(alice, where).released.set()

    ended = alice.told("ended", run=1)
    assert ended["how"] == "crashed"
    assert "ZeroDivisionError: oops" in ended["why"]


def test_a_run_whose_cap_nothing_can_read_says_so_first(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    where.next_run = FakeRun(blind="nobody prices mystery")

    run = _started(alice, where)

    assert alice.told("notice", run=1)["text"] == "nobody prices mystery"
    run.released.set()


def test_a_run_moved_off_its_runtime_says_so(host: Host, where: Workspace) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert run.noticer is not None

    run.noticer("box moved to docker")

    assert alice.told("notice", run=1)["text"] == "box moved to docker"
    run.released.set()


def _until(check: Callable[[], bool]) -> None:
    """Waits for something another thread does that nothing announces."""
    deadline = time.monotonic() + PATIENCE
    while not check():
        assert time.monotonic() < deadline, "it never happened"
        threading.Event().wait(0.002)


def test_a_run_that_ended_with_nobody_there_waits_for_somebody(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    where.next_run = FakeRun(epic=where.workspace / "epic")
    run = _started(alice, where)
    host.detach(alice.client)

    run.released.set()
    _until(lambda: host.status()["state"] == "idle")

    # Nobody saw it end, so it is held for whoever comes next.
    assert host.idle is False
    assert host.epic == where.workspace / "epic"
    late = Told(host, "late")
    late.told("ended", run=1)
    host.detach(late.client)
    assert host.idle is True


def test_stopping_a_run_says_who_and_then_how_it_ended(
    host: Host, where: Workspace
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    run = _started(alice, where)

    assert bob.asks("stop") == {"ok": True}

    assert alice.told("stopping", run=1)["by"] == "bob"
    assert run.stopped is True
    alice.told("ended", run=1, how="stopped")
    host.detach(alice.client)
    host.detach(bob.client)
    # Somebody asked for it to end, so nobody is waited for.
    assert host.idle is True


def test_stopping_nothing_is_refused(host: Host) -> None:
    alice = Told(host, "alice")
    nothing = {"ok": False, "why": "no flow is running, so there is nothing to stop"}

    assert alice.asks("stop") == nothing
    assert alice.asks("force") == nothing


def test_a_run_already_stopping_is_said_to_be_and_can_be_forced(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    # Held going after it was told to stop, as a flow closing out its turn is.
    where.next_run = FakeRun(lingers=True)
    run = _started(alice, where)

    assert alice.asks("stop") == {"ok": True}
    said = alice.asks("stop")
    assert said["ok"] is False
    assert "already stopping" in said["why"]
    assert host.status()["state"] == "stopping"

    assert alice.asks("force") == {"ok": True, "closed": 0}
    assert run.closed == 1
    assert host.status()["state"] == "idle"


def test_forcing_a_run_going_stops_and_closes_it(host: Host, where: Workspace) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)

    assert alice.asks("force") == {"ok": True, "closed": 0}

    assert run.stopped is True
    assert run.closed == 1
    alice.told("stopping", run=1)


# ------------------------------------------------------------------ lines


def test_a_line_needs_something_said_and_a_run_to_say_it_to(host: Host) -> None:
    alice = Told(host, "alice")

    assert alice.asks("say", text="") == {"ok": False, "why": "a line says something"}
    assert alice.asks("say", text="hi") == {
        "ok": False,
        "why": "no flow is running to say it to",
    }


def test_a_line_waits_and_what_never_went_is_said_when_the_run_ends(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)

    assert alice.asks("say", text="also tests", to="NeiKos496") == {"ok": True}

    alice.waits(
        lambda one: (
            one["type"] == "waiting"
            and [each["text"] for each in one["queued"]] == ["also tests"]
        )
    )
    run.released.set()
    dropped = alice.told("dropped", run=1)
    assert dropped["because"] == "ended"
    assert [one["text"] for one in dropped["queued"]] == ["also tests"]


def _opened(
    run: FakeRun, agent: Agent, session: Session, role: str = "builder"
) -> None:
    agent.sessions.append(session)
    run.agents.append(agent)
    assert run.opener is not None
    run.opener(role, agent, session, None)


def _heard(run: FakeRun, agent: Agent, session: Session | None, event: Event) -> None:
    assert run.listener is not None
    run.listener(agent, session, event)


def test_a_session_opened_is_numbered_for_its_agent_and_says_its_role(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent = Agent()

    _opened(run, agent, Session(forks=True))
    _opened(run, agent, Session())

    first = alice.told("opened", key="NeiKos496/1")
    assert (first["role"], first["agent"], first["cli"], first["model"]) == (
        "builder",
        "NeiKos496",
        "claude",
        "opus",
    )
    assert (first["forks"], first["person"], first["counts"]) == (
        True,
        False,
        ["turns"],
    )
    assert (first["kept"], first["env"], first["harness"]) == ("", None, "")
    alice.told("opened", key="NeiKos496/2")
    alice.waits(
        lambda one: (
            one["type"] == "sessions" and one["open"] == ["NeiKos496/1", "NeiKos496/2"]
        )
    )
    run.released.set()


def test_what_a_turn_says_is_told_on_its_conversations_transcript(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent, session = Agent(), Session(named="abc")
    _opened(run, agent, session)

    _heard(run, agent, session, Event("begins"))
    _heard(run, agent, session, Event("text", "working on it"))
    _heard(run, agent, None, Event("text", "for all of them"))

    said = alice.told("event", text="working on it")
    assert (said["key"], said["session"], said["ident"], said["run"]) == (
        "NeiKos496/1",
        "NeiKos496/1",
        "abc",
        1,
    )
    alice.waits(
        lambda one: one["type"] == "sessions" and one["working"] == ["NeiKos496/1"]
    )
    # What no one conversation said goes on the one working.
    assert alice.told("event", text="for all of them")["key"] == "NeiKos496/1"
    _heard(run, agent, session, Event("ends"))
    alice.waits(lambda one: one["type"] == "sessions" and one["working"] == [])
    run.released.set()


def test_a_line_goes_into_the_turn_working_and_is_said_once_the_agent_has_it(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent, session = Agent(), Session()
    _opened(run, agent, session)
    _heard(run, agent, session, Event("begins"))

    assert alice.asks("say", text="use the fixture") == {"ok": True}

    assert session.given.wait(PATIENCE)
    assert session.said == ["use the fixture"]
    alice.waits(
        lambda one: (
            one["type"] == "waiting"
            and [each["text"] for each in one["given"]] == ["use the fixture"]
        )
    )
    _heard(run, agent, session, Event("took", "use the fixture"))
    said = alice.told("said", text="use the fixture")
    assert (said["key"], said["by"]) == ("NeiKos496/1", "alice")
    run.released.set()


def test_a_line_the_agent_refused_goes_back_to_the_head_of_the_queue(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent = Agent()
    session = Session(
        refuses=subprocess.CalledProcessError(1, "x", stderr=b"turn is over")
    )
    _opened(run, agent, session)
    _heard(run, agent, session, Event("begins"))

    alice.asks("say", text="late word", to="NeiKos496/1")

    refused = alice.told("refused", text="late word")
    assert refused["because"] == "turn is over"
    alice.waits(
        lambda one: (
            one["type"] == "waiting"
            and [each["text"] for each in one["queued"]] == ["late word"]
        )
    )
    run.released.set()


def test_a_line_waiting_for_the_next_turn_is_folded_into_it(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent, session = Agent(), Session()
    _opened(run, agent, session)
    alice.asks("say", text="next time", to="NeiKos496")

    waiting = cast("Callable[[], list[str]]", agent.waiting)

    assert waiting() == ["next time"]
    assert waiting() == []
    assert alice.told("said", text="next time")["key"] == "NeiKos496/1"
    run.released.set()


def test_what_an_agent_held_when_its_turn_ended_is_said(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent, session = Agent(), Session()
    _opened(run, agent, session)
    _heard(run, agent, session, Event("begins"))
    alice.asks("say", text="held word")
    assert session.given.wait(PATIENCE)
    alice.waits(lambda one: one["type"] == "waiting" and one["given"])

    _heard(run, agent, session, Event("ends"))

    assert alice.told("unheld", agent="NeiKos496")["texts"] == ["held word"]
    run.released.set()


# ------------------------------------------------------------------ claims


def test_a_role_is_claimed_by_one_frontend_at_a_time(host: Host) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")

    assert alice.asks("claim") == {"ok": False, "why": "a role to claim is named"}
    assert alice.asks("claim", role="outworlder") == {"ok": True}
    assert bob.asks("claim", role="outworlder") == {
        "ok": False,
        "why": "outworlder is alice's",
    }
    alice.waits(
        lambda one: (
            one["type"] == "claims" and one["claims"] == {"outworlder": alice.client}
        )
    )
    assert bob.asks("release", role="outworlder") == {
        "ok": False,
        "why": "outworlder is not yours to release",
    }
    assert bob.asks("claim", role="outworlder", take=True) == {"ok": True}
    assert alice.asks("release", role="") == {
        "ok": False,
        "why": "that is not yours to release",
    }
    assert bob.asks("release", role="outworlder") == {"ok": True}


def test_a_frontend_that_goes_gives_up_what_it_claimed(host: Host) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    alice.asks("claim", role="outworlder")

    host.detach(alice.client)

    assert bob.asks("claim", role="outworlder") == {"ok": True}


def test_away_is_said_of_every_role_or_of_one(host: Host) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")

    assert alice.asks("afk", on="yes") == {"ok": False, "why": "afk is on or off"}
    assert alice.asks("afk", on=True) == {"ok": True}
    assert host.away_for("anyone") is True
    alice.told("away", all=True, of={})

    assert alice.asks("afk", on=False, role="reviewer") == {"ok": True}
    assert host.away_for("reviewer") is False
    assert host.away_for("anyone") is True

    bob.asks("claim", role="reviewer")
    assert alice.asks("afk", on=True, role="reviewer") == {
        "ok": False,
        "why": "reviewer is bob's",
    }
    # Every role alice may speak for, which leaves bob's as it was.
    assert alice.asks("afk", on=False) == {"ok": True}
    assert host.away_for("anyone") is False
    assert host.away_for("reviewer") is False
    assert bob.asks("afk", on=True) == {"ok": True}
    assert host.away_for("reviewer") is True


# ------------------------------------------------------------------ questions


@dataclass
class Question:
    text: str
    options: tuple[str, ...] = ()
    asker: str = "outworlder"
    schema: dict[str, Any] | None = None
    context: tuple[dict[str, Any], ...] = ()
    face: str = ""
    session: str = ""
    check: Callable[[Any], tuple[dict[str, Any], ...]] | None = None


@dataclass
class Asking:
    """A question put on a thread of the run's own, as the run puts one."""

    answer: str | None = None
    done: threading.Event = field(default_factory=threading.Event)

    def __call__(self, ask: Callable[[Any], str | None], question: Question) -> Asking:
        def asks() -> None:
            self.answer = ask(question)
            self.done.set()

        threading.Thread(target=asks, daemon=True).start()
        return self


def test_a_question_is_put_to_everybody_and_answered_by_number(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None

    asking = Asking()(outworlders.ask, Question("which?", ("red", "blue")))

    asked = alice.told("asked", run=1)
    assert (asked["role"], asked["text"], asked["options"], asked["mode"]) == (
        "outworlder",
        "which?",
        ["red", "blue"],
        "ask",
    )
    pending = alice.waits(lambda one: one["type"] == "pending" and one["pending"])
    assert pending["pending"][0]["question"] == asked["question"]
    assert alice.asks("answer", question=asked["question"], text="") == {
        "ok": False,
        "why": "an answer says something",
    }
    assert alice.asks("answer", question=asked["question"], text="2") == {"ok": True}
    assert asking.done.wait(PATIENCE)
    assert asking.answer == "blue"
    assert alice.told("answered", question=asked["question"])["by"] == "alice"
    assert alice.asks("answer", question=asked["question"], text="1") == {
        "ok": False,
        "why": "already answered by alice",
    }
    assert alice.asks("answer", question="q99", text="x") == {
        "ok": False,
        "why": "no question q99 is waiting",
    }
    run.released.set()


def test_the_status_says_the_questions_waited_on_and_how_the_last_run_ended(
    host: Host, where: Workspace, outworlders: Outworlders, tmp_path: Path
) -> None:
    alice = Told(host, "alice")
    where.next_run = FakeRun(epic=tmp_path / "20260101-ralph")
    run = _started(alice, where)
    assert outworlders.ask is not None
    said = host.status()
    assert (said["epic"], said["task"], said["pending"], said["ended"]) == (
        "20260101-ralph",
        "fix it",
        [],
        None,
    )

    asking = Asking()(outworlders.ask, Question("which?", ("red", "blue")))
    asked = alice.told("asked", run=1)

    assert host.status()["pending"] == [
        {
            "question": asked["question"],
            "role": "outworlder",
            "text": "which?",
            "mode": "ask",
        }
    ]
    alice.asks("answer", question=asked["question"], text="1")
    assert asking.done.wait(PATIENCE)
    run.raises = BudgetExceeded("spent")
    run.released.set()
    alice.told("ended", run=1)
    said = host.status()
    assert said["pending"] == []
    ended = said["ended"]
    assert (
        ended["how"],
        ended["epic"],
        ended["run"],
        ended["flow"],
        ended["task"],
    ) == (
        "budget",
        "20260101-ralph",
        1,
        "ralph",
        "fix it",
    )
    assert "spent" in ended["why"]
    assert ended["at"] > 0


# ------------------------------------------------------------- shaped questions


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"enum": ["approve", "reject"]},
        "notes": {"type": "string", "default": ""},
    },
    "required": ["verdict"],
}

DIFF = {"kind": "diff", "patch": "--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y\n"}


def _verdicts(value: Any) -> tuple[dict[str, Any], ...]:
    """What `Question.check` says of a value: a mapping with a verdict of the two."""
    if not isinstance(value, dict):
        return ({"path": [], "message": "an object is expected"},)
    verdict = cast("dict[str, Any]", value).get("verdict")
    if verdict not in ("approve", "reject"):
        return ({"path": ["verdict"], "message": "approve or reject"},)
    return ()


@dataclass
class Shaped:
    """A question asked for a schema whole, as `Question` asks one."""

    text: str = "review this"
    options: tuple[str, ...] = ()
    asker: str = "outworlder"
    schema: dict[str, Any] | None = field(default_factory=lambda: dict(SCHEMA))
    context: tuple[dict[str, Any], ...] = (DIFF,)
    face: str = ""
    session: str = "outworlder/1"
    check: Callable[[Any], tuple[dict[str, Any], ...]] | None = _verdicts


@dataclass(frozen=True)
class Face:
    html: str
    title: str = ""

    @property
    def hash(self) -> str:
        return f"h{len(self.html)}"


def test_a_question_asked_for_a_schema_says_it_and_what_is_shown_beside_it(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None

    Asking()(outworlders.ask, cast("Any", Shaped(options=("ignored",))))

    asked = alice.told("asked", run=1)
    assert (asked["options"], asked["mode"], asked["schema"]) == ([], "ask", SCHEMA)
    assert (asked["context"], asked["face"], asked["session"]) == (
        [DIFF],
        None,
        "outworlder/1",
    )
    pending = alice.waits(lambda one: one["type"] == "pending" and one["pending"])
    (entry,) = pending["pending"]
    assert {key: entry[key] for key in ("schema", "context", "face", "session")} == {
        "schema": SCHEMA,
        "context": [DIFF],
        "face": None,
        "session": "outworlder/1",
    }
    # And the status stays as small as it was.
    assert set(host.status()["pending"][0]) == {"question", "role", "text", "mode"}
    run.released.set()


def test_a_question_of_text_alone_says_no_schema_and_nothing_beside_it(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None

    Asking()(outworlders.ask, Question("which?", ("red", "blue")))

    asked = alice.told("asked", run=1)
    assert (asked["schema"], asked["context"], asked["face"], asked["session"]) == (
        None,
        [],
        None,
        "",
    )
    run.released.set()


def test_a_value_that_does_not_fit_is_refused_400_with_every_way_it_does_not(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, cast("Any", Shaped()))
    question = alice.told("asked", run=1)["question"]

    assert alice.asks("answer", question=question, value={"verdict": "meh"}) == {
        "ok": False,
        "why": "the answer does not fit: approve or reject",
        "code": 400,
        "data": {"errors": [{"path": ["verdict"], "message": "approve or reject"}]},
    }
    assert alice.asks("answer", question=question, text="{not json") == {
        "ok": False,
        "why": "the answer does not fit: the answer is not JSON",
        "code": 400,
        "data": {"errors": [{"path": [], "message": "the answer is not JSON"}]},
    }
    # A number picks no option of a question that has none: it is the JSON it reads as.
    refused = alice.asks("answer", question=question, text="1")
    assert refused["why"] == "the answer does not fit: an object is expected"
    assert not asking.done.is_set()

    assert alice.asks(
        "answer", question=question, value={"verdict": "approve", "notes": "LGTM"}
    ) == {"ok": True}
    assert asking.done.wait(PATIENCE)
    assert asking.answer is not None
    assert json.loads(asking.answer) == {"verdict": "approve", "notes": "LGTM"}
    answered = alice.told("answered", question=question)
    assert json.loads(answered["text"]) == {"verdict": "approve", "notes": "LGTM"}
    run.released.set()


def test_a_check_that_fails_refuses_the_value_it_could_not_read(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    def fails(value: Any) -> tuple[dict[str, Any], ...]:
        raise TypeError(f"cannot read {value!r}")

    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, cast("Any", Shaped(check=fails)))
    question = alice.told("asked", run=1)["question"]

    refused = alice.asks("answer", question=question, value=3)
    assert (refused["why"], refused["code"]) == (
        "the answer does not fit: cannot read 3",
        400,
    )
    assert not asking.done.is_set()
    run.released.set()


def test_a_secret_is_given_the_flow_whole_and_recorded_as_stars(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    schema = {
        "type": "object",
        "properties": {
            "user": {"type": "string"},
            "token": {"type": "string", "hmz:widget": "secret"},
        },
    }
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(
        outworlders.ask, cast("Any", Shaped(schema=schema, check=lambda _: ()))
    )
    question = alice.told("asked", run=1)["question"]

    said = {"user": "ann", "token": "s3cret"}
    assert alice.asks("answer", question=question, value=said) == {"ok": True}
    assert asking.done.wait(PATIENCE)
    assert asking.answer is not None
    assert json.loads(asking.answer) == said
    answered = alice.told("answered", question=question)
    assert json.loads(answered["text"]) == {"user": "ann", "token": "***"}
    run.released.set()


def test_a_schema_question_answered_in_text_reads_the_text_as_json(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, cast("Any", Shaped()))
    question = alice.told("asked", run=1)["question"]

    assert alice.asks("answer", question=question, text='{"verdict": "reject"}') == {
        "ok": True
    }
    assert asking.done.wait(PATIENCE)
    assert asking.answer is not None
    assert json.loads(asking.answer) == {"verdict": "reject"}
    run.released.set()


def test_an_answer_is_text_or_a_value_and_a_text_question_takes_text(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, Question("which?", ("red", "blue")))
    question = alice.told("asked", run=1)["question"]

    assert alice.asks("answer", question=question, text="1", value="red") == {
        "ok": False,
        "why": "an answer is text or a value, not both",
    }
    others: tuple[Any, ...] = (2, {})
    for other in others:
        assert alice.asks("answer", question=question, value=other) == {
            "ok": False,
            "why": "the answer does not fit: text is expected",
            "code": 400,
            "data": {"errors": [{"path": [], "message": "text is expected"}]},
        }
    # A value that is text is read as text, and text that is empty says nothing.
    assert alice.asks("answer", question=question, value="") == {
        "ok": False,
        "why": "an answer says something",
    }
    # A value is taken as it is, never as the number of an option.
    assert alice.asks("answer", question=question, value="green") == {"ok": True}
    assert asking.done.wait(PATIENCE)
    assert asking.answer == "green"
    run.released.set()


@pytest.mark.parametrize(
    ("put", "text", "heard"),
    [
        (Question("which?", ("red", "blue")), "red", "red"),
        (Shaped(), '{"verdict": "reject"}', {"verdict": "reject"}),
    ],
    ids=["text", "schema"],
)
def test_a_value_of_null_is_read_as_not_sent(
    host: Host,
    where: Workspace,
    outworlders: Outworlders,
    put: Any,
    text: str,
    heard: Any,
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, put)
    question = alice.told("asked", run=1)["question"]

    assert alice.asks("answer", question=question, value=None) == {
        "ok": False,
        "why": "an answer says something",
    }
    assert alice.asks("answer", question=question, text=text, value=None) == {
        "ok": True
    }
    assert asking.done.wait(PATIENCE)
    assert asking.answer is not None
    assert asking.answer == heard or json.loads(asking.answer) == heard
    run.released.set()


def test_a_face_mounted_is_named_by_the_question_and_read_by_its_hash(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    assert outworlders.faces is not None
    face = Face("<p>review</p>", "Review")
    outworlders.faces(face)

    Asking()(outworlders.ask, cast("Any", Shaped(face=face.hash)))

    asked = alice.told("asked", run=1)
    assert asked["face"] == {"hash": face.hash, "title": "Review"}
    assert alice.asks("face", hash=face.hash) == {
        "ok": True,
        "html": "<p>review</p>",
        "title": "Review",
    }
    assert alice.asks("face", hash="nothing") == {
        "ok": False,
        "why": "no face nothing",
        "code": 404,
    }
    run.released.set()


def test_what_a_run_shows_is_said_to_everybody_while_somebody_is_there(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.show is not None
    image = {"kind": "image", "mime": "image/png", "data": "A" * (300 * 1024)}

    outworlders.show("outworlder", "outworlder/1", (DIFF, image))

    shown = alice.told("shown", run=1)
    assert (shown["role"], shown["session"], shown["context"]) == (
        "outworlder",
        "outworlder/1",
        # An image is never cut short, as a text that long elsewhere would be.
        [DIFF, image],
    )
    alice.asks("afk", on=True)
    outworlders.show("outworlder", "outworlder/1", (DIFF,))
    outworlders.show("outworlder", "outworlder/1", ())
    alice.asks("afk", on=False)
    outworlders.show("outworlder", "outworlder/1", ())
    alice.waits(lambda one: one["type"] == "shown" and one["context"] == [])
    assert len([one for one in alice.snapshot() if one["type"] == "shown"]) == 2
    run.released.set()


@pytest.fixture
def chatting(where: Workspace) -> Iterator[tuple[Host, Told]]:
    """A chat's host, with one frontend attached to it."""
    made = Host(cast("Any", where), "chat:1")
    try:
        yield made, Told(made, "alice")
    finally:
        made.close()


def _chatted(host: Host, alice: Told, where: Workspace, **said: Any) -> FakeChatting:
    """A chat started on its host, which has asked for its second message."""
    answer = alice.asks("chat.start", agent="claude/opus:high", task="hello", **said)
    assert answer == {"ok": True, "run": 1, "epic": "20260101-chat", "slot": "chat:1"}
    chat = where.chats[-1]
    alice.told("asked", run=1, mode="listen", text="you said hello")
    return chat


def test_an_ai_chan_conversation_is_a_chat_whose_assistant_plays_her_role(
    where: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.runtime.doing import aichan

    reached: list[tuple[aichan.Reach, Path]] = []

    def role(reach: aichan.Reach, scratch: Path) -> object:
        reached.append((reach, scratch))
        return mock.sentinel.role

    monkeypatch.setattr(aichan, "role", role)
    host = Host(cast("Any", where), "ai:1")
    try:
        alice = Told(host, "alice")
        ai = {"id": 1, "scope": "daemon", "preset": "read-only", "network": False}
        # Hers is the daemon's to start, with the reach it keeps: no frontend's.
        assert alice.asks("chat.start", agent="claude/opus:high", task="hi", ai=ai) == {
            "ok": False,
            "why": "an Ai-chan host has her own conversation",
            "code": 409,
        }

        answer = host.chatted(
            {
                "do": "start",
                "by": "hmz",
                "agent": "claude/opus:high",
                "task": "",
                "ai": ai,
                "scratch": "/ai/m/1",
            }
        )

        assert answer["ok"], answer
        assert reached == [(aichan.Reach(id=1), Path("/ai/m/1"))]
        assert where.asked_chats[-1]["role"] is mock.sentinel.role
        chat = where.chats[-1]
        # Stopping her stops her open turn alone, and she goes on between turns.
        refused = alice.asks("stop")
        assert refused["why"] == "Ai-chan is not answering, so there is nothing to stop"
        chat.turning = True
        assert alice.asks("stop") == {"ok": True}
        assert chat.interrupted == 1
        assert host.status()["state"] == "running"
    finally:
        host.close()


def test_an_ai_chan_conversation_carried_on_needs_nothing_said(
    where: Workspace,
) -> None:
    assert hosting.chat_checked(
        cast("Any", where), {"agent": "claude/opus", "task": ""}
    ) == {"ok": False, "why": "a chat starts with something said", "code": 400}
    where.epics.kept["20260101-chat"] = where.workspace / "20260101-chat"
    checked = hosting.chat_checked(
        cast("Any", where),
        {"agent": "claude/opus", "task": "", "resume": "20260101-chat", "ai": {}},
    )
    assert (checked["ok"], checked["task"]) == (True, "")
    # Her nous may be named as a nous, which no setting keeps as a chat's agent.
    named = hosting.chat_checked(
        cast("Any", where), {"agent": "claude/opus", "task": "", "ai": {}}
    )
    assert (named["ok"], named["runs"]) == (True, None)


def test_a_chat_takes_a_virtual_nous_as_its_agent(
    where: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.coganchor import nous

    def virtual(name: str) -> bool:
        return name == "smart"

    def entry(name: str) -> str:
        return "claude@work/opus:high"

    monkeypatch.setattr(nous, "virtual", virtual)
    monkeypatch.setattr(nous, "entry", entry)

    checked = hosting.chat_checked(
        cast("Any", where), {"agent": "smart", "task": "hello"}
    )

    # The chat's agent is the nous as it was named; what a setting keeps of it is the concrete
    # nous it starts at, a remembered agent being a harness, an account, a model and an effort.
    assert (checked["ok"], checked["agent"]) == (True, "smart"), checked
    assert (checked["runs"].spec, checked["runs"].provider) == (
        "claude/opus:high",
        "work",
    )
    refused = hosting.chat_checked(
        cast("Any", where), {"agent": "nobody", "task": "hello"}
    )
    assert (refused["ok"], refused["code"]) == (False, 400), refused


def test_a_chat_starts_on_its_own_host_and_says_it_is_a_chat(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    chat = _chatted(host, alice, where, prefer="flow")

    started = alice.told("started", run=1)
    assert (started["kind"], started["flow"], started["ref"]) == ("chat", "", "")
    assert (started["task"], started["agents"]) == (
        "hello",
        {"assistant": "claude/opus:high"},
    )
    assert (started["params"], started["budget"]) == (None, None)
    assert where.asked_chats == [
        {
            "agent": "claude/opus:high",
            "task": "hello",
            "resume": None,
            "prefer": "flow",
        }
    ]
    status = host.status()
    assert (status["epic_kind"], status["flow"], status["epic"]) == (
        "chat",
        "",
        "20260101-chat",
    )
    assert (status["turn"], status["budget"]) == ("done", None)
    assert chat.person is not None


def test_a_chat_is_started_on_a_chat_host_alone_and_once(
    host: Host, chatting: tuple[Host, Told], where: Workspace
) -> None:
    alice = Told(host, "alice")
    refused = alice.asks("chat.start", agent="claude/opus", task="hi")
    assert (refused["ok"], refused["code"]) == (False, 400)
    assert refused["why"] == "the workspace is not a chat slot."

    on, bob = chatting
    _chatted(on, bob, where)
    assert bob.asks("chat.start", agent="claude/opus", task="again") == {
        "ok": False,
        "why": "a chat is already going on chat:1",
        "code": 409,
    }
    assert bob.asks("start", flow="ralph", task="fix it") == {
        "ok": False,
        "why": "a chat is started with chat.start",
    }


@pytest.mark.parametrize(
    ("said", "why"),
    [
        ({"agent": "claude/opus"}, "a chat starts with something said"),
        ({"task": "hi"}, "an agent for the chat is named"),
        (
            {"agent": "claude/opus", "task": "hi", "prefer": "both"},
            "prefer is native or flow",
        ),
        (
            {"agent": "claude/opus", "task": "hi", "permission": "ask"},
            "permission is read-only, workspace-write or danger-full-access",
        ),
    ],
)
def test_a_chat_start_missing_what_it_takes_is_refused(
    said: dict[str, Any], why: str, chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, _ = chatting

    assert host.chatted({"do": "start", **said}) == {
        "ok": False,
        "why": why,
        "code": 400,
    }
    assert where.chats == []


def test_a_chat_that_fails_before_its_epic_is_refused_with_why(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    _, alice = chatting
    where.failing = RuntimeError("no runtime named gpu is saved")

    refused = alice.asks("chat.start", agent="claude/opus", task="hi")

    assert refused == {
        "ok": False,
        "why": "RuntimeError: no runtime named gpu is saved",
        "code": 400,
    }
    alice.told("ended", run=1, how="crashed")


def test_a_chat_that_is_refused_before_its_epic_is_refused_with_why(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    _, alice = chatting
    where.failing = Refused("the chat names no claude account called 'nobody'")

    refused = alice.asks("chat.start", agent="claude@nobody/opus", task="hi")

    assert refused == {
        "ok": False,
        "why": "the chat names no claude account called 'nobody'",
        "code": 400,
    }
    alice.told("ended", run=1, how="refused")


def test_what_is_said_to_a_chat_is_its_next_message_and_its_turn_runs_until_answered(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    chat = _chatted(host, alice, where)
    assert host.status()["turn"] == "done"

    assert host.chatted({"do": "say", "text": "and more", "by": "bob"}) == {"ok": True}

    answered = alice.told("answered", run=1, text="and more")
    assert answered["by"] == "bob"
    alice.told("asked", run=1, mode="listen", text="you said and more")
    assert chat.lines == ["and more"]


def test_what_a_chats_assistant_asks_mid_turn_is_answered_by_the_next_line(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    chat = _chatted(host, alice, where)
    chat.asks.append(("which?", ("red", "blue")))
    alice.asks("chat.say", text="go on")

    asked = alice.told("asked", run=1, text="which?")
    assert (asked["mode"], asked["options"], asked["role"]) == (
        "ask",
        ["red", "blue"],
        "human",
    )
    assert host.status()["turn"] == "running"
    alice.asks("chat.say", text="2")

    alice.told("asked", run=1, mode="listen", text="you said go on")
    assert chat.answers == ["blue"]


def test_a_chat_between_turns_is_not_in_one_though_it_waits_on_no_line(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    chat = _chatted(host, alice, where)
    chat.asks.append(("which?", ()))
    alice.asks("chat.say", text="!make")
    alice.told("asked", run=1, text="which?")
    assert host.status()["turn"] == "running"

    # As a chat is while a `!` command of its person's runs: no turn is opened by one.
    chat.chat.between = True

    assert host.status()["turn"] == "done"


def test_an_empty_line_ends_a_chat_stopped(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    chat = _chatted(host, alice, where)

    assert alice.asks("chat.say", text="  ") == {"ok": True}

    ended = alice.told("ended", run=1)
    assert (ended["how"], ended["why"], ended["result"]) == ("stopped", "", None)
    assert chat.lines == [""]
    assert host.status()["ended"]["kind"] == "chat"
    assert alice.asks("chat.say", text="hello?") == {
        "ok": False,
        "why": "this chat has ended; carry it on from its epic",
        "code": 409,
    }


def test_an_empty_line_said_mid_turn_ends_the_chat_once_the_turn_is_done(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    chat = _chatted(host, alice, where)
    chat.asks.append(("which?", ("red", "blue")))
    alice.asks("chat.say", text="go on")
    alice.told("asked", run=1, text="which?")

    assert alice.asks("chat.say", text="") == {"ok": True}
    alice.asks("chat.say", text="red")

    alice.told("ended", run=1, how="stopped")
    assert (chat.lines, chat.answers) == (["go on", ""], ["red"])


def test_a_chat_started_to_be_remembered_is_the_workspaces_chat_from_then_on(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    from hmz.runtime.settings import Settings

    host, alice = chatting
    _chatted(host, alice, where, remember=True)

    remembered = Settings(where.workspace).chat_agent
    assert remembered is not None
    assert remembered.spec == "claude/opus:high"


def test_a_chat_is_not_said_to_by_epic_say_nor_answered_by_epic_answer(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    _chatted(host, alice, where)
    asked = alice.told("asked", run=1)

    to_chat = {"ok": False, "why": "say it to the chat with chat.say"}
    assert alice.asks("say", text="hello") == to_chat
    assert alice.asks("answer", question=asked["question"], text="hello") == to_chat


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("/clear", "/clear is served by the frontend, not said to the chat"),
        ("$ralph fix it", "$ralph names a flow, which the frontend starts"),
        ("/config", "/config cannot be said here: /config is served only"),
        ("/nothing", "/nothing cannot be said here: no such command: /nothing"),
    ],
)
def test_a_line_the_frontend_serves_or_the_harness_cannot_is_refused(
    line: str, why: str, chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    where.flows.offered = (Offered("ralph", "loops"),)
    chat = _chatted(host, alice, where)
    chat.chat.catalog = [
        Native("/", "compact", "compacts", "call"),
        Native("/", "config", "settings", "refuse"),
    ]

    refused = alice.asks("chat.say", text=line)

    assert (refused["ok"], refused["code"]) == (False, 400)
    assert refused["why"].startswith(why)
    assert chat.lines == []


def test_a_native_line_is_held_for_a_turn_of_its_own(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    chat = _chatted(host, alice, where)
    chat.chat.catalog = [Native("/", "compact", "compacts", "call")]

    alice.asks("chat.say", text="/compact")

    alice.told("asked", run=1, mode="listen", text="you said /compact")
    assert chat.lines == ["/compact"]


def test_a_skill_that_is_a_flow_too_goes_by_the_chats_preference(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    where.flows.offered = (Offered("review", "reviews"),)
    chat = _chatted(host, alice, where)
    chat.chat.catalog = [Native("$", "review", "a skill", "call")]

    assert alice.asks("chat.set", prefer="flow") == {"ok": True}
    assert alice.asks("chat.say", text="$review it")["code"] == 400
    assert alice.asks("chat.set", prefer="native") == {"ok": True}
    assert alice.asks("chat.say", text="$review it") == {"ok": True}

    alice.told("asked", run=1, mode="listen", text="you said $review it")


def test_a_chats_commands_are_its_catalogue_then_hmzs_then_the_flows(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    where.flows.offered = (Offered("ralph", "loops"),)
    chat = _chatted(host, alice, where)
    chat.chat.catalog = [Native("!", "", "runs a command", "emulate")]

    said = alice.asks("chat.commands")

    entries = said["entries"]
    assert entries[0] == {
        "sigil": "!",
        "name": "",
        "about": "runs a command",
        "how": "emulate",
        "source": "native",
    }
    kept = [one["name"] for one in entries if one["source"] == "hmz"]
    assert kept == sorted(kept)
    assert {"clear", "prefer", "resume", "btw"} <= set(kept)
    assert all(one["sigil"] == "/" and one["how"] == "" for one in entries[1:-1])
    assert entries[-1] == {
        "sigil": "$",
        "name": "ralph",
        "about": "loops",
        "how": "",
        "source": "flow",
    }
    assert (said["prefer"], said["prefer_from"]) == ("native", "settings")

    alice.asks("chat.set", prefer="flow")
    said = alice.asks("chat.commands")
    assert (said["prefer"], said["prefer_from"]) == ("flow", "chat")
    assert chat.chat.prefer == "flow"
    assert alice.asks("chat.set", prefer="both")["code"] == 400


def test_a_chat_is_started_with_and_set_to_a_permission(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    chat = _chatted(host, alice, where, permission="read-only")

    assert where.asked_chats[-1]["permission"] == "read-only"
    chat.chat.permission = "read-only"
    assert alice.asks("chat.commands")["permission"] == "read-only"

    assert alice.asks("chat.set", permission="danger-full-access") == {"ok": True}
    assert alice.asks("chat.commands")["permission"] == "danger-full-access"
    # Both at once, and neither.
    assert alice.asks("chat.set", prefer="flow", permission="workspace-write") == {
        "ok": True
    }
    assert (chat.chat.prefer, chat.chat.permission) == ("flow", "workspace-write")
    refused = alice.asks("chat.set", permission="ask")
    assert (refused["why"], refused["code"]) == (
        "permission is read-only, workspace-write or danger-full-access",
        400,
    )
    assert alice.asks("chat.set") == {
        "ok": False,
        "why": "chat.set takes prefer or permission",
        "code": 400,
    }
    # One held to its role's -- an Ai-chan conversation -- keeps it.
    chat.chat.permission = None
    kept = alice.asks("chat.set", permission="read-only")
    assert (kept["why"], kept["code"]) == (
        "an Ai-chan conversation keeps its permission",
        409,
    )


def test_a_command_run_for_a_chat_is_told_to_every_frontend(
    chatting: tuple[Host, Told], where: Workspace
) -> None:
    host, alice = chatting
    chat = _chatted(host, alice, where)

    chat.person.shell("ls", "a\nb\n", "", 0)

    shell = alice.told("shell", run=1)
    assert (shell["command"], shell["out"], shell["err"], shell["status"]) == (
        "ls",
        "a\nb\n",
        "",
        0,
    )


def test_a_chat_nobody_reads_between_turns_folds_away(
    chatting: tuple[Host, Told], where: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hosting, "FOLD", 0.0)
    host, alice = chatting
    chat = _chatted(host, alice, where)
    # Read by somebody, it waits for them however long they take.
    time.sleep(1.0)
    assert chat.lines == []

    host.detach(alice.client)

    # Nobody there, between turns: the wait is answered with nothing, which ends it.
    assert _waited(lambda: chat.lines == [""])
    assert _waited(lambda: host.idle)
    assert host.status()["ended"]["how"] == "stopped"
    folded = {
        "ok": False,
        "why": "this chat has folded away; carry it on from its epic",
    }
    assert host.chatted({"do": "say", "text": "again"}) == folded | {"code": 409}
    assert host.chatted(
        {"do": "start", "agent": "claude/opus", "task": "again"}
    ) == folded | {"code": 409}


def test_a_chat_carried_on_names_the_epic_it_carries_on_in(
    chatting: tuple[Host, Told], where: Workspace, tmp_path: Path
) -> None:
    _, alice = chatting
    epic = tmp_path / "20250101-chat"
    where.epics.kept[epic.name] = epic

    answer = alice.asks("chat.start", task="more", resume=epic.name)

    assert answer == {"ok": True, "run": 1, "epic": "20250101-chat", "slot": "chat:1"}
    # Its own agent and permission, as its epic says, where none is named.
    assert where.asked_chats[-1] == {
        "agent": "claude/opus:high",
        "task": "more",
        "resume": str(epic),
        "prefer": None,
        "permission": "read-only",
    }
    assert alice.told("started", run=1)["resume"] == str(epic)
    refused = alice.asks("chat.start", task="more", resume="20200101-nothing")
    assert (refused["why"], refused["code"]) == (
        f"20200101-nothing is not a chat of {where.workspace}.",
        404,
    )


def test_a_flow_listening_on_the_workspaces_own_host_never_folds(
    host: Host,
    where: Workspace,
    outworlders: Outworlders,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hosting, "FOLD", 0.0)
    alice = Told(host, "alice")
    _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, Question("what next?"))
    alice.told("asked", run=1, mode="listen")

    host.detach(alice.client)

    assert not asking.done.wait(1.0)
    assert host.status()["state"] == "running"
    assert host.status()["epic_kind"] == "flow"


def _waited(what: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline:
        if what():
            return True
        time.sleep(0.02)
    return False


def test_a_flow_that_is_no_chat_says_no_turn(host: Host, where: Workspace) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)

    assert "turn" not in host.status()
    assert "turn" not in alice.told("run", state="running")
    run.released.set()


def test_a_question_of_a_claimed_role_is_its_claimants(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    run = _started(alice, where)
    alice.asks("claim", role="outworlder")
    assert outworlders.ask is not None

    asking = Asking()(outworlders.ask, Question("ok?", ("yes", "no")))
    asked = bob.told("asked", run=1)

    assert bob.asks("answer", question=asked["question"], text="no") == {
        "ok": False,
        "why": "outworlder is alice's",
    }
    assert alice.asks("answer", question=asked["question"], text="anything else") == {
        "ok": True
    }
    assert asking.done.wait(PATIENCE)
    assert asking.answer == "anything else"
    run.released.set()


def test_what_to_say_next_is_answered_by_the_oldest_line_waiting(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    alice.asks("say", text="carry on")

    asking = Asking()(outworlders.ask, Question("what next?"))

    assert asking.done.wait(PATIENCE)
    assert asking.answer == "carry on"
    assert alice.told("asked", run=1)["mode"] == "listen"
    run.released.set()


def test_a_line_said_to_a_conversation_between_turns_of_another_flow_waits_for_its_turn(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent, session = Agent(), Session()
    _opened(run, agent, session)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, Question("which budget?"))
    alice.told("asked", run=1)

    alice.asks("say", text="next time", to="NeiKos496/1")
    alice.waits(
        lambda one: (
            one["type"] == "waiting"
            and [each["text"] for each in one["queued"]] == ["next time"]
        )
    )

    assert not asking.done.wait(0.3)
    alice.asks("say", text="two", to="outworlder:outworlder")
    assert asking.done.wait(PATIENCE)
    assert asking.answer == "two"
    assert cast("Callable[[], list[str]]", agent.waiting)() == ["next time"]
    run.released.set()


def test_a_line_said_to_a_conversation_working_is_no_answer(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent, session = Agent(), Session()
    _opened(run, agent, session)
    _heard(run, agent, session, Event("begins"))
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, Question("which?", ("a", "b")))
    asked = alice.told("asked", run=1)
    assert (asked["mode"], asked["key"]) == ("ask", "NeiKos496/1")
    pending = alice.waits(lambda one: one["type"] == "pending" and one["pending"])
    assert pending["pending"][0]["key"] == "NeiKos496/1"

    alice.asks("say", text="for the turn", to="NeiKos496/1")

    assert session.given.wait(PATIENCE)
    assert not asking.done.is_set()
    alice.asks("answer", question=asked["question"], text="a")
    assert asking.done.wait(PATIENCE)
    run.released.set()


def test_nobody_answers_for_a_role_that_is_away(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    alice.asks("afk", on=True)

    assert outworlders.ask(Question("anyone?")) is None
    run.released.set()


def test_a_question_waiting_is_withdrawn_when_its_role_goes_away(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, Question("still there?", ("y",)))
    alice.told("asked", run=1)

    alice.asks("afk", on=True)

    assert asking.done.wait(PATIENCE)
    assert asking.answer is None
    assert alice.told("withdrawn", run=1)["why"] == "away"
    run.released.set()


def test_a_question_waiting_is_withdrawn_when_its_role_goes_away_and_back(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, Question("still there?", ("y",)))
    alice.told("asked", run=1)

    # Back before the asking thread can look: it is woken, and only runs when this one lets
    # it, which it does not until both have been said.
    switching = sys.getswitchinterval()
    sys.setswitchinterval(PATIENCE)
    try:
        alice.asks("afk", on=True)
        alice.asks("afk", on=False)
    finally:
        sys.setswitchinterval(switching)

    assert asking.done.wait(PATIENCE)
    assert asking.answer is None
    assert alice.told("withdrawn", run=1)["why"] == "away"
    run.released.set()


def test_a_question_waiting_is_withdrawn_when_its_run_ends(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    assert outworlders.ask is not None
    asking = Asking()(outworlders.ask, Question("still there?", ("y",)))
    alice.told("asked", run=1)

    run.released.set()

    assert asking.done.wait(PATIENCE)
    assert asking.answer is None
    assert alice.told("withdrawn", run=1)["why"] == "over"


def test_a_run_no_longer_going_asks_nobody(
    host: Host, where: Workspace, outworlders: Outworlders
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    ask = outworlders.ask
    assert ask is not None
    run.released.set()
    alice.told("ended", run=1)

    assert ask(Question("hello?")) is None


# ------------------------------------------------------------------ board and asides


def test_a_run_with_no_board_has_nothing_to_put_on_it(host: Host) -> None:
    alice = Told(host, "alice")

    assert alice.asks("board", key="k", value="v") == {
        "ok": False,
        "why": "this run has no board",
    }


@pytest.mark.parametrize(
    ("said", "why"),
    [
        ({}, "an aside is about a conversation, or asks an agent"),
        ({"key": "NeiKos496/9"}, "NeiKos496/9 has no conversation to ask"),
        ({"side": "s9", "prompt": "hi"}, "no aside s9 is open"),
    ],
)
def test_an_aside_about_nothing_is_refused(
    said: dict[str, Any], why: str, host: Host
) -> None:
    assert Told(host, "alice").asks("aside", **said) == {"ok": False, "why": why}


def test_an_aside_nobody_opened_cannot_be_closed(host: Host) -> None:
    assert Told(host, "alice").asks("unaside", side="s1") == {
        "ok": False,
        "why": "no aside s1 is open",
    }


def test_an_aside_asking_an_agent_that_cannot_be_made_is_refused(host: Host) -> None:
    assert Told(host, "alice").asks("aside", runs="nonsense") == {
        "ok": False,
        "why": "nonsense is not an agent that can be made here",
    }


@dataclass
class Reading:
    """A fence, as far as a side conversation reads one: its twin that writes nothing."""

    writes: bool = True

    def reading(self) -> Reading:
        return Reading(writes=False)


@dataclass
class Hooked(Config):
    """A Codex agent's settings as they stand while its flow's hooks are hung on it."""

    fence: Reading = field(default_factory=Reading)
    goals: bool = True
    approvals: str = "untrusted"
    features: tuple[tuple[str, bool], ...] = (
        ("default_mode_request_user_input", True),
        ("shell_snapshot", False),
    )


@dataclass(eq=False)
class Working(Session):
    cwd: str = "/w"


@dataclass(eq=False)
class Copied(Agent):
    """An agent that can be copied, which is what a side conversation is opened on."""

    copies: list[Agent] = field(default_factory=list[Agent])

    def clone(self, *, config: Config, name: str, skills: tuple[str, ...]) -> Agent:
        del skills
        self.copies.append(Copied(id=name, backend=self.backend, config=config))
        return self.copies[-1]

    def watch(self, listener: object) -> None:
        del listener

    def new(self, cwd: str | None) -> Session:
        return Working(cwd=cwd or "")


def test_an_aside_of_a_codex_agent_is_asked_nothing_whatever_hooks_its_source_has(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent = Copied(backend="codex", config=Hooked())
    _opened(run, agent, Working())
    alice.told("opened", key="NeiKos496/1")

    assert alice.asks("aside", key="NeiKos496/1") == {
        "ok": True,
        "side": "s1",
        "forked": False,
    }

    # The source's hooks are not hung on the copy, so neither is what they were told with:
    # its thread opens at the `never` of a fence that writes nothing, and it asks no user.
    copy = cast("Hooked", agent.copies[0].config)
    assert (copy.fence.writes, copy.goals) == (False, False)
    assert copy.approvals == ""
    assert copy.features == (("shell_snapshot", False),)
    assert cast("Hooked", agent.config).approvals == "untrusted"
    run.released.set()


# ------------------------------------------------------------------ closing


def test_closing_lets_every_frontend_go_and_stops_what_runs(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    alice.asks("say", text="never sent")

    host.close()

    assert alice.told("gone")["why"] == "the host was closed"
    assert run.closed == 1
    assert host.closed is True
    assert host.idle is False
    assert host.attached == 0
    with pytest.raises(RuntimeError, match="this host has closed"):
        Told(host, "late")
    # Closing again is closing once.
    host.close()
    host.printed("after")


def test_a_frontend_may_close_the_host(host: Host) -> None:
    alice = Told(host, "alice")

    assert alice.asks("quit") == {"ok": True}

    assert host.closed is True
    alice.told("gone")
