"""A flow running: here or on a thread of its own, watched, and stopped."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import Budget, Usage
from hmz.runtime import Run
from hmz.runtime.chatting import ChatEnd, ChatSpec
from hmz.runtime.doing.running import Chatting

if TYPE_CHECKING:
    from collections.abc import Callable

#: How long a test waits for what a thread of the run's own is doing.
PATIENCE = 10.0


@dataclass(eq=False)
class Handle:
    agent: object = None
    interrupted: int = 0
    refuses: bool = False

    def interrupt(self) -> None:
        self.interrupted += 1
        if self.refuses:
            raise RuntimeError("already gone")


@dataclass(eq=False)
class Agent:
    stopped: int = 0
    refuses: bool = False

    def stop(self) -> None:
        self.stopped += 1
        if self.refuses:
            raise RuntimeError("already gone")


@dataclass
class Recorder:
    sessions: tuple[Handle, ...] = ()
    spent: Usage = field(default_factory=Usage)

    def usage(self) -> Usage:
        return self.spent


@dataclass
class Epic:
    path: Path


@dataclass
class Impl:
    ref: str = "official/ralph"


@dataclass
class Runner:
    """A flow loaded, as far as a run drives one: what it does is `flow`, on the run's loop."""

    flow: str = "ralph"
    impl: Impl = field(default_factory=Impl)
    declaration: object = field(default_factory=object)
    budget: Budget = field(default_factory=lambda: Budget(cost=1.0))
    profile_flow: bool = True
    profile_environment: bool = True
    recorder: Recorder | None = None
    agents: dict[str, object] = field(default_factory=dict[str, object])
    does: Callable[[dict[str, Any]], Any] | None = None
    blocks: bool = False
    entered: threading.Event = field(default_factory=threading.Event)
    asked: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    closed: int = 0
    watched: list[object] = field(default_factory=list[object])
    stopped: list[Callable[[], bool]] = field(
        default_factory=list["Callable[[], bool]"]
    )

    async def arun(self, task: str, **said: Any) -> Any:
        said["task"] = task
        self.asked.append(said)
        said["started"](Epic(Path("/epics/one")))
        self.entered.set()
        if self.blocks:
            await asyncio.Future[None]()
        return self.does(said) if self.does is not None else "returned"

    async def aclose(self) -> None:
        self.closed += 1

    def unreadable(self, stopped: Callable[[], bool]) -> str:
        self.stopped.append(stopped)
        return "unpriced"

    def watch(self, listener: object) -> None:
        self.watched.append(listener)


def _run(runner: Runner, task: str = "fix it", **said: Any) -> Run:
    return Run(cast("Any", runner), task, **said)


def test_a_run_says_what_it_is_a_run_of() -> None:
    runner = Runner(recorder=Recorder(spent=Usage(cost=2.0)))
    run = _run(runner, outworlder=cast("Any", "someone"))

    assert run.flow == "ralph"
    assert run.ref == "official/ralph"
    assert run.task == "fix it"
    assert run.declaration is runner.declaration
    assert run.budget == Budget(cost=1.0)
    assert (run.profile_flow, run.profile_environment) == (True, True)
    assert run.usage == Usage(cost=2.0)
    assert run.epic is None
    assert (run.running, run.raised, run.result) == (False, None, None)


def test_a_run_not_yet_going_has_spent_nothing_and_opened_nothing() -> None:
    run = _run(Runner())

    assert run.usage == Usage()
    assert run.agents == ()


def test_the_agents_are_those_behind_the_sessions_still_open() -> None:
    first, second = Agent(), Agent()
    run = _run(Runner(recorder=Recorder((Handle(first), Handle(), Handle(second)))))

    assert run.agents == (first, second)


@dataclass
class Driver:
    name: str


def test_each_agent_role_says_what_the_agent_filling_it_is_called() -> None:
    runner = Runner(
        agents={"builder": Driver("NeiKos496"), "critic": Driver("Golem99")}
    )

    assert _run(runner).names == {"builder": "NeiKos496", "critic": "Golem99"}


def test_a_run_here_returns_what_the_flow_did_and_tells_everyone_listening() -> None:
    runner = Runner()
    run = _run(runner, outworlder=cast("Any", "someone"))
    opened: list[tuple[object, ...]] = []
    noticed: list[str] = []

    def opens(said: dict[str, Any]) -> str:
        said["opened"]("builder", "agent", "session", None)
        said["noticed"]("box moved")
        return "done"

    def first(*said: object) -> None:
        opened.append(said)

    def second(*said: object) -> None:
        opened.append(("again", *said))

    runner.does = opens
    run.opened(first)
    run.opened(second)
    run.noticed(noticed.append)

    assert run.run() == "done"
    assert run.epic == Path("/epics/one")
    assert runner.asked[0]["task"] == "fix it"
    assert runner.asked[0]["outworlder"] == "someone"
    assert opened == [
        ("builder", "agent", "session", None),
        ("again", "builder", "agent", "session", None),
    ]
    assert noticed == ["box moved"]


def test_a_run_here_raises_what_the_flow_raised() -> None:
    def fails(said: dict[str, Any]) -> Any:
        raise ValueError("bug")

    with pytest.raises(ValueError, match="bug"):
        _run(Runner(does=fails)).run()


def test_a_run_on_a_thread_keeps_what_it_returned() -> None:
    run = _run(Runner())

    run.start()

    assert run.wait(PATIENCE) is True
    assert run.running is False
    assert run.result == "returned"
    assert run.raised is None


def test_a_run_on_a_thread_keeps_what_it_raised() -> None:
    why = ValueError("bug")

    def fails(said: dict[str, Any]) -> Any:
        raise why

    run = _run(Runner(does=fails))
    run.start()

    assert run.wait(PATIENCE) is True
    assert run.raised is why


def test_a_run_is_started_once() -> None:
    run = _run(Runner())
    run.start()

    with pytest.raises(RuntimeError, match="already been started"):
        run.start()
    run.wait(PATIENCE)


def test_waiting_on_a_run_never_started_is_waiting_on_nothing() -> None:
    assert _run(Runner()).wait(0) is True


async def test_a_run_asked_for_from_a_loop_runs_on_a_thread_of_its_own() -> None:
    runner = Runner()

    assert _run(runner).run() == "returned"


async def test_a_run_from_a_loop_raises_what_the_flow_raised() -> None:
    def fails(said: dict[str, Any]) -> Any:
        raise ValueError("bug")

    with pytest.raises(ValueError, match="bug"):
        _run(Runner(does=fails)).run()


def test_a_run_stopped_before_it_began_runs_nothing_and_lets_its_drivers_go() -> None:
    runner = Runner()
    run = _run(runner)

    run.stop()

    with pytest.raises(asyncio.CancelledError):
        run.run()
    assert runner.asked == []
    assert runner.closed == 1


def test_a_run_going_is_stopped_from_another_thread() -> None:
    runner = Runner(blocks=True)
    run = _run(runner)
    run.start()
    assert runner.entered.wait(PATIENCE)
    assert run.running is True

    run.stop()

    assert run.wait(PATIENCE) is True
    assert isinstance(run.raised, asyncio.CancelledError)


def test_stopping_a_run_that_is_over_does_nothing() -> None:
    run = _run(Runner())
    run.start()
    run.wait(PATIENCE)

    run.stop()

    assert run.result == "returned"


def test_closing_a_run_ends_every_conversation_still_open() -> None:
    gone, here = Agent(refuses=True), Agent()
    handles = (Handle(gone, refuses=True), Handle(here))
    run = _run(Runner(recorder=Recorder(handles)))

    run.close()

    assert [one.interrupted for one in handles] == [1, 1]
    assert (gone.stopped, here.stopped) == (1, 1)
    # And it is stopped: nothing of it runs from here on.
    with pytest.raises(asyncio.CancelledError):
        run.run()


def test_closing_a_run_with_nothing_open_only_stops_it() -> None:
    run = _run(Runner())

    run.close()

    assert run.agents == ()


def test_what_nothing_can_price_is_asked_until_the_run_is_stopped() -> None:
    runner = Runner()
    run = _run(runner)

    assert run.unreadable() == "unpriced"
    (stopped,) = runner.stopped
    assert stopped() is False
    run.stop()
    assert stopped() is True


def test_watching_a_run_watches_every_session_of_it() -> None:
    runner = Runner()

    _run(runner).watch(print)

    assert runner.watched == [print]


def test_a_run_is_an_epic_of_a_flow() -> None:
    assert _run(Runner()).kind == "flow"


# ------------------------------------------------------------------ a chat held as a run


@dataclass(eq=False)
class Chat:
    """A chat, as holding it reads one: what it was started with, what it tells, how it ends."""

    spec: ChatSpec
    ended: ChatEnd | None = None
    raises: BaseException | None = None
    going: threading.Event = field(default_factory=threading.Event)
    holds: bool = False
    at: Path | None = None
    usage: Usage = field(default_factory=Usage)
    agents: tuple[Agent, ...] = ()
    told: dict[str, Any] = field(default_factory=dict[str, Any])

    def watch(self, listener: Any) -> None:
        self.told["watch"] = listener

    def opened(self, callback: Any) -> None:
        self.told["opened"] = callback

    async def run(self) -> ChatEnd:
        self.going.set()
        if self.holds:
            await asyncio.Event().wait()
        if self.raises is not None:
            raise self.raises
        assert self.ended is not None
        return self.ended


def _spec(resume: Path | None = None) -> ChatSpec:
    return ChatSpec(Path("/w"), "claude/opus:high", "hello", resume=resume)


def test_a_chat_is_held_as_a_run_is_with_no_flow_and_no_budget() -> None:
    held = Chatting(cast("Any", Chat(_spec())))

    assert (held.kind, held.flow, held.ref, held.budget) == ("chat", "", "", None)
    assert (held.task, held.agent) == ("hello", "claude/opus:high")
    assert (held.usage, held.agents, held.unreadable()) == (Usage(), (), "")
    # Where it is written is named once it is, which is not before it has begun.
    assert (held.epic, held.names_epic) == (None, True)


def test_a_chat_carried_on_is_written_nowhere_before_it_has_opened_the_one_it_carries_on() -> (
    None
):
    chat = Chat(_spec(resume=Path("/chats/e1")))
    held = Chatting(cast("Any", chat))

    # It may yet be refused, so what it is to carry on is not its own until it opens it.
    assert (held.epic, held.names_epic) == (None, True)
    chat.at = Path("/chats/e1")
    assert held.epic == Path("/chats/e1")


def test_what_a_chat_tells_of_itself_is_handed_through() -> None:
    chat = Chat(
        _spec(), at=Path("/chats/e2"), usage=Usage(cost=0.25), agents=(Agent(),)
    )
    held = Chatting(cast("Any", chat))

    def opened(*said: Any) -> None:
        del said

    def noticed(said: str) -> None:
        del said

    held.watch(print)
    held.opened(opened)
    # A chat is never moved off where it works, so there is nothing to notice.
    held.noticed(noticed)

    assert chat.told == {"watch": print, "opened": opened}
    assert (held.epic, held.names_epic) == (Path("/chats/e2"), True)
    assert (held.usage, held.agents) == (Usage(cost=0.25), chat.agents)


def test_a_chat_had_here_says_how_it_ended_and_where() -> None:
    chat = Chat(_spec(), ended=ChatEnd(Path("/chats/e3"), "stopped"))
    held = Chatting(cast("Any", chat))

    assert held.run() == ChatEnd(Path("/chats/e3"), "stopped")
    assert held.epic == Path("/chats/e3")


def test_a_chat_whose_first_turn_failed_raises_it() -> None:
    held = Chatting(cast("Any", Chat(_spec(), raises=RuntimeError("no account"))))

    with pytest.raises(RuntimeError, match="no account"):
        held.run()


def test_a_chat_going_is_ended_from_another_thread_and_its_agents_stopped() -> None:
    chat = Chat(_spec(), holds=True, agents=(Agent(),))
    held = Chatting(cast("Any", chat))
    raised: list[BaseException] = []

    def has() -> None:
        try:
            held.run()
        except BaseException as why:  # noqa: BLE001 -- kept, to be looked at
            raised.append(why)

    thread = threading.Thread(target=has)
    thread.start()
    assert chat.going.wait(PATIENCE)
    held.close()
    thread.join(PATIENCE)

    assert [type(one) for one in raised] == [asyncio.CancelledError]
    assert chat.agents[0].stopped == 1


def test_a_chat_ended_before_it_began_has_nothing() -> None:
    chat = Chat(_spec(), ended=ChatEnd(Path("/chats/e4"), "stopped"))
    held = Chatting(cast("Any", chat))

    held.stop()

    with pytest.raises(asyncio.CancelledError):
        held.run()
    assert not chat.going.is_set()
