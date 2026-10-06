"""One workspace's runs, shared by every frontend attached to them."""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import Budget, BudgetExceeded, FlowNotFound, Usage
from hmz.runtime import Host, Refused, flowing
from hmz.runtime.doing.hosting import PROTOCOL, record

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

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

    id: str = "builder"
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
        key="builder/2",
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
    assert (said["run"], said["key"], said["session"]) == (3, "builder/2", "builder/2")
    assert (said["agent"], said["cli"], said["model"]) == ("builder", "claude", "opus")
    assert (said["ident"], said["kind"], said["text"]) == ("abc", "result", "done")
    assert (said["tokens"], said["spent"]) == ({"out": 3}, {"cost": 0.5})


def test_what_the_agent_said_for_every_conversation_names_none() -> None:
    said = _record(Agent(), None, Event(), key="builder")

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
    declaration: Declaration = field(default_factory=Declaration)
    budget: Budget = field(default_factory=lambda: Budget(cost=2.0))
    usage: Usage = field(default_factory=lambda: Usage(cost=0.5))
    profile: bool = False
    epic: Path | None = None
    blind: str = ""
    raises: BaseException | None = None
    agents: list[Agent] = field(default_factory=list[Agent])
    listener: Callable[..., None] | None = None
    opener: Callable[..., None] | None = None
    noticer: Callable[[str], None] | None = None
    going: threading.Event = field(default_factory=threading.Event)
    released: threading.Event = field(default_factory=threading.Event)
    stopped: bool = False
    lingers: bool = False
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


@dataclass
class Flows:
    calls: tuple[Any, ...] = ()
    broken: bool = False

    def running(self) -> tuple[Any, ...]:
        if self.broken:
            raise RuntimeError("no tree")
        return self.calls


@dataclass
class Workspace:
    """The `Hmz` a host is made for, as far as the host reads one."""

    workspace: Path
    flows: Flows = field(default_factory=Flows)
    runs: list[FakeRun] = field(default_factory=list[FakeRun])
    asked: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    refuses: BaseException | None = None
    next_run: FakeRun | None = None

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
    """What the host hands a run for whoever is outside it: its `ask` and its `away`."""

    ask: Callable[[Any], str | None] | None = None
    away: Callable[[str], bool] | None = None

    def __call__(
        self,
        *,
        ask: Callable[[Any], str | None],
        away: Callable[[str], bool],
    ) -> str:
        self.ask, self.away = ask, away
        return "outworlder"


class Told:
    """One frontend's end: everything it has been told, in the order it was told."""

    def __init__(self, host: Host, name: str = "", *, replay: bool = True) -> None:
        self.seen: list[dict[str, Any]] = []
        self._landed = threading.Condition()
        self.host = host
        self.client = host.attach(name, "sdk", self._told, replay=replay)

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
    assert welcome["protocol"] == PROTOCOL
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
        profile=True,
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
    assert started["outworlders"] == ["outworlder"]
    assert started["agents"] == {"builder": "claude/opus"}
    assert started["envs"] == {"box": "local/x"}
    assert started["params"] == {"rounds": 2}
    assert started["budget"]["cost"] == 2.0
    assert started["resume"] == "True"
    asked = where.asked[0]
    assert asked["budget"] == {"cost": 2}
    assert asked["profile"] is True
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

    assert alice.asks("say", text="also tests", to="builder") == {"ok": True}

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


def test_a_session_opened_is_numbered_for_its_role(
    host: Host, where: Workspace
) -> None:
    alice = Told(host, "alice")
    run = _started(alice, where)
    agent = Agent()

    _opened(run, agent, Session(forks=True))
    _opened(run, agent, Session())

    first = alice.told("opened", key="builder/1")
    assert (first["role"], first["agent"], first["cli"], first["model"]) == (
        "builder",
        "builder",
        "claude",
        "opus",
    )
    assert (first["forks"], first["person"], first["counts"]) == (
        True,
        False,
        ["turns"],
    )
    assert (first["kept"], first["env"], first["harness"]) == ("", None, "")
    alice.told("opened", key="builder/2")
    alice.waits(
        lambda one: (
            one["type"] == "sessions" and one["open"] == ["builder/1", "builder/2"]
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
        "builder/1",
        "builder/1",
        "abc",
        1,
    )
    alice.waits(
        lambda one: one["type"] == "sessions" and one["working"] == ["builder/1"]
    )
    # What no one conversation said goes on the one working.
    assert alice.told("event", text="for all of them")["key"] == "builder/1"
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
    assert (said["key"], said["by"]) == ("builder/1", "alice")
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

    alice.asks("say", text="late word", to="builder/1")

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
    alice.asks("say", text="next time", to="builder")

    waiting = cast("Callable[[], list[str]]", agent.waiting)

    assert waiting() == ["next time"]
    assert waiting() == []
    assert alice.told("said", text="next time")["key"] == "builder/1"
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

    assert alice.told("unheld", agent="builder")["texts"] == ["held word"]
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
        ({"key": "builder/9"}, "builder/9 has no conversation to ask"),
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
