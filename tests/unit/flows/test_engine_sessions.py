"""How long a session lives: until its flow call ends, or until the flow lets go of it.

The flow API gives a flow no way to close a session, so the engine closes it: when the flow
call that opened it ends, whoever holds it by then, or as soon as nothing can reach it any
more -- whichever comes first. A flow opening a fresh session a round holds a few open however
many rounds it runs, and every session is closed once, on the run's loop, whichever thread let
go of it.
"""

from __future__ import annotations

import asyncio
import gc
import math
import threading
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    Env,
    EnvCollection,
    FlowContext,
    FlowParams,
    NotificationHookParams,
    NotificationHookResult,
    SessionEndHookParams,
    SessionEndHookResult,
    SessionError,
    UserPromptSubmitHookParams,
    UserPromptSubmitHookResult,
    flow,
    load,
)
from hmz.runtime.flowing.engine import run_flow
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, run_fake
from tests.flows.kit import flowverse

if TYPE_CHECKING:
    from pathlib import Path


class Solo(AgentCollection):
    agent: Agent


class Place(EnvCollection):
    env: Env


class Rounds(FlowParams):
    rounds: int = 0
    fanout: int = 1


def _driver(agent: object) -> FakeAgentDriver:
    """The fake under an agent view."""
    return cast("Any", agent).driver


def _handle(session: object) -> Any:
    """The fake session under a session view."""
    return cast("Any", session)._handle


def _echo(prompt: str, **_: Any) -> str:
    return prompt


async def _yielding(prompt: str, **_: Any) -> str:
    """Answers after letting the loop go on, as every real turn does."""
    await asyncio.sleep(0)
    return prompt


class Counting(FakeAgentDriver):
    """A fake whose sessions write down every close asked of them, and where it was asked.

    Args:
      delay: How long a close takes, after it is asked.
    """

    def __init__(self, *, delay: float = 0.0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.delay = delay
        self.closes: list[tuple[str | None, int]] = []

    async def open(self, *args: Any, **kwargs: Any) -> Any:
        session = await super().open(*args, **kwargs)
        real = session.close

        async def close() -> None:
            self.closes.append((session.id, threading.get_ident()))
            if self.delay:
                await asyncio.sleep(self.delay)
            await real()

        session.close = close
        return session


# ------------------------------------------------------------------------ a round apiece


@flow(agents=Solo, envs=Place, params=Rounds)
async def rounds(
    task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
) -> tuple[int, int, int]:
    """A fresh session a round, a turn in it, and nothing kept."""
    agent, env = agents["agent"], envs["env"]
    driver = _driver(agent)
    live = kept = hooked = 0
    for _ in range(params.rounds):
        session = await agent.spawn(env=env)
        await agent.run(task, session=session)
        live = max(live, driver.live)
        kept = max(kept, len(cast("Any", ctx).res or ()))
        hooked = max(hooked, len(cast("Any", agent)._line.sessions))
    return live, kept, hooked


@pytest.mark.parametrize("reply", [None, _yielding], ids=["instant", "yielding"])
async def test_ten_thousand_rounds_hold_two_sessions_open_at_most(reply: Any) -> None:
    driver = FakeAgentDriver(reply=reply)
    live, kept, hooked = await run_fake(
        rounds, "go", agents={"agent": driver}, params={"rounds": 10_000}
    )
    assert len(driver.sessions) == 10_000
    assert max(live, driver.peak) <= 2, "sessions let go of were left open"
    assert kept <= 2, f"the call kept {kept} sessions it had closed"
    assert hooked <= 2, f"the agent kept {hooked} sessions it had closed"
    assert driver.live == 0
    assert all(one.closed for one in driver.sessions)


@flow(agents=Solo, envs=Place, params=Rounds)
async def fanned(
    task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
) -> int:
    """Rounds in batches of `fanout` gathered at once, each in a session of its own."""
    agent, env = agents["agent"], envs["env"]
    driver = _driver(agent)
    live = 0

    async def one() -> str:
        session = await agent.spawn(env=env)
        return await agent.run(task, session=session)

    for _ in range(params.rounds // params.fanout):
        said = await asyncio.gather(*(one() for _ in range(params.fanout)))
        assert said == [task] * params.fanout
        live = max(live, driver.live)
    return live


@flow(agents=Solo, envs=Place, params=Rounds)
async def workers(
    task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
) -> None:
    """`fanout` loops at once, each opening a fresh session a round."""
    agent, env = agents["agent"], envs["env"]

    async def worker(rounds: int) -> None:
        for _ in range(rounds):
            session = await agent.spawn(env=env)
            await agent.run(task, session=session)

    await asyncio.gather(
        *(worker(params.rounds // params.fanout) for _ in range(params.fanout))
    )


async def test_gathered_rounds_hold_a_batch_open_at_most() -> None:
    driver = FakeAgentDriver(reply=_yielding)
    live = await run_fake(
        fanned,
        "go",
        agents={"agent": driver},
        params={"rounds": 10_000, "fanout": 100},
    )
    assert len(driver.sessions) == 10_000
    assert live <= 100
    assert driver.peak <= 100 + 2, f"{driver.peak} open at once, in batches of 100"
    assert driver.live == 0
    assert all(one.closed for one in driver.sessions)


async def test_loops_gathered_hold_two_sessions_apiece_at_most() -> None:
    driver = FakeAgentDriver(reply=_yielding)
    await run_fake(
        workers, "go", agents={"agent": driver}, params={"rounds": 10_000, "fanout": 10}
    )
    assert len(driver.sessions) == 10_000
    assert driver.peak <= 2 * 10, f"{driver.peak} open at once, by 10 loops"
    assert driver.live == 0


async def test_an_on_disk_flow_run_over_drivers_holds_few_open(tmp_path: Path) -> None:
    flows = flowverse(
        tmp_path,
        {
            "churn": """
                from hmz.flows import Agent, AgentCollection, Env, EnvCollection
                from hmz.flows import FlowContext, FlowParams, flow

                class Solo(AgentCollection):
                    agent: Agent

                class Place(EnvCollection):
                    env: Env

                class Rounds(FlowParams):
                    rounds: int = 0

                @flow(agents=Solo, envs=Place, params=Rounds)
                async def churn(task, *, agents, envs, params, ctx: FlowContext) -> int:
                    agent = agents["agent"]
                    for _ in range(params.rounds):
                        session = await agent.spawn(env=envs["env"])
                        await agent.run(task, session=session)
                    return params.rounds
            """
        },
    )
    driver = FakeAgentDriver()
    said = await run_flow(
        load(str(flows / "churn")),
        "go",
        agents={"agent": driver},
        envs={"env": FakeEnvDriver()},
        params={"rounds": "1000"},
        budget=Budget(cost=math.inf),
    )
    assert said == 1_000
    assert len(driver.sessions) == 1_000
    assert driver.peak <= 2
    assert driver.live == 0


# ------------------------------------------------------------------------- what is kept


async def test_a_session_the_flow_still_holds_stays_open() -> None:
    @flow(agents=Solo, envs=Place, params=Rounds)
    async def holding(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> tuple[list[bool], list[bool]]:
        agent, env = agents["agent"], envs["env"]
        kept = await agent.spawn(env=env)
        await agent.run("one", session=kept)
        listed = [await agent.spawn(env=env)]
        mapped = {"s": await agent.spawn(env=env)}
        handles = [_handle(one) for one in (kept, listed[0], mapped["s"])]
        for _ in range(50):
            await agent.run("churn", session=await agent.spawn(env=env))
            gc.collect()
            await asyncio.sleep(0)
        for one in (kept, listed[0], mapped["s"]):
            await agent.run("still here", session=one)
        del one
        before = [one.closed for one in handles]
        listed.clear()
        del mapped["s"]
        await asyncio.sleep(0)
        return before, [one.closed for one in handles]

    before, after = await run_fake(holding)
    assert before == [False, False, False]
    assert after == [False, True, True]


async def test_a_fork_outlives_the_session_it_was_cut_from() -> None:
    @flow(agents=Solo, envs=Place, params=Rounds)
    async def forking(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> tuple[list[bool], str, str, bool]:
        agent, env = agents["agent"], envs["env"]
        parent = await agent.spawn(env=env)
        await agent.run("a", session=parent)
        child = await agent.fork(parent, env=env)
        cut = _handle(parent)
        del parent
        await asyncio.sleep(0)
        # A harness cuts the fork as its first turn goes, so the parent is kept till then.
        closed = [cut.closed]
        said = await agent.run("b", session=child)
        await asyncio.sleep(0)
        closed.append(cut.closed)
        orphan = await agent.fork(await agent.spawn(env=env), env=env)
        await asyncio.sleep(0)
        again = await agent.run("c", session=orphan)
        return closed, said, again, _handle(child).closed

    driver = FakeAgentDriver(reply=_echo)
    assert await run_fake(forking, agents={"agent": driver}) == (
        [False, True],
        "b",
        "c",
        False,
    )
    assert driver.sessions[1].prompts == ["a", "b"]
    assert [one.closed for one in driver.sessions] == [True] * 4


async def test_a_fork_whose_first_turn_failed_still_holds_its_parent() -> None:
    refused: list[bool] = [True]

    async def refusing(
        params: UserPromptSubmitHookParams,
    ) -> UserPromptSubmitHookResult:
        del params
        return UserPromptSubmitHookResult(block=refused.pop(), reason="not yet")

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def forking(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> list[bool]:
        agent, env = agents["agent"], envs["env"]
        parent = await agent.spawn(env=env)
        await agent.run("a", session=parent)
        child = await agent.fork(parent, env=env)
        cut = _handle(parent)
        del parent
        agent.on_user_prompt_submit(refusing)
        with pytest.raises(SessionError):
            await agent.run("b", session=child)
        await asyncio.sleep(0)
        closed = [cut.closed]
        agent.on_user_prompt_submit(None)
        await agent.run("b", session=child)
        await asyncio.sleep(0)
        return [*closed, cut.closed]

    assert await run_fake(forking) == [False, True]


async def test_a_chain_of_forks_holds_few_open() -> None:
    @flow(agents=Solo, envs=Place, params=Rounds)
    async def chaining(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> int:
        agent, env = agents["agent"], envs["env"]
        driver = _driver(agent)
        live = 0
        session = await agent.spawn(env=env)
        for _ in range(params.rounds):
            await agent.run(task, session=session)
            session = await agent.fork(session, env=env)
            live = max(live, driver.live)
        return live

    driver = FakeAgentDriver()
    live = await run_fake(
        chaining, "go", agents={"agent": driver}, params={"rounds": 1_000}
    )
    assert len(driver.sessions) == 1_001
    assert max(live, driver.peak) <= 3
    assert driver.live == 0


async def test_a_session_handed_up_closes_with_the_call_that_opened_it() -> None:
    driver = Counting()

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def opening(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> Any:
        session = await agents["agent"].spawn(env=envs["env"])
        await agents["agent"].run("go", session=session)
        return session

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def caller(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> tuple[bool, int, int]:
        session = await opening(task, agents=agents, envs=envs, params=params)
        closed = _handle(session).closed
        with pytest.raises(SessionError):
            await agents["agent"].run("more", session=session)
        closes = len(driver.closes)
        del session
        await asyncio.sleep(0)
        return closed, closes, len(driver.closes)

    assert await run_fake(caller, agents={"agent": driver}) == (True, 1, 1)
    assert len(driver.closes) == 1


# ---------------------------------------------------------------------- closed, once


async def test_a_session_let_go_of_as_its_call_ends_is_closed_once() -> None:
    driver = Counting()

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def leaving(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> None:
        session = await agents["agent"].spawn(env=envs["env"])
        await agents["agent"].run("go", session=session)

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def caller(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> list[int]:
        counted: list[int] = []
        for _ in range(20):
            await leaving(task, agents=agents, envs=envs, params=params)
            counted.append(len(driver.closes))
            await asyncio.sleep(0)
        return counted

    assert await run_fake(caller, agents={"agent": driver}) == list(range(1, 21))
    assert sorted(set(driver.closes)) == sorted(driver.closes)


async def test_a_close_under_way_as_its_call_ends_is_waited_for() -> None:
    driver = Counting(delay=0.05)

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def dropping(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> int:
        session = await agents["agent"].spawn(env=envs["env"])
        await agents["agent"].run("go", session=session)
        del session
        await asyncio.sleep(0)
        return len(driver.closes)

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def caller(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> tuple[int, bool]:
        started = await dropping(task, agents=agents, envs=envs, params=params)
        return started, driver.sessions[0].closed

    assert await run_fake(caller, agents={"agent": driver}) == (1, True)
    assert len(driver.closes) == 1


@pytest.mark.parametrize("how", ["released", "collected"])
async def test_a_session_let_go_of_on_another_thread_is_closed_on_the_loop(
    how: str,
) -> None:
    driver = Counting()
    loop = asyncio.get_running_loop()
    debug = loop.get_debug()

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def elsewhere(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> tuple[list[tuple[str | None, int]], str | None]:
        session = await agents["agent"].spawn(env=envs["env"])
        await agents["agent"].run("go", session=session)
        name = _handle(session).id
        knot: list[Any] = [session]
        del session
        if how == "released":
            await asyncio.to_thread(knot.clear)
        else:
            knot.append(knot)
            del knot
            await asyncio.to_thread(gc.collect)
        for _ in range(10):
            if driver.closes:
                break
            await asyncio.sleep(0)
        return list(driver.closes), name

    # A loop in debug mode refuses a call from another thread that is not thread-safe.
    loop.set_debug(True)
    gc.disable()
    try:
        closes, name = await run_fake(elsewhere, agents={"agent": driver})
    finally:
        gc.enable()
        loop.set_debug(debug)
    assert closes == [(name, threading.get_ident())]
    assert len(driver.closes) == 1


# ------------------------------------------------------------------------------- hooks


async def test_a_hook_heard_once_a_session_is_let_go_of_gets_one_that_is_over() -> None:
    heard: list[tuple[Any, Any, type[BaseException] | None]] = []

    async def ending(params: SessionEndHookParams) -> SessionEndHookResult:
        session = params.session
        refused: type[BaseException] | None = None
        try:
            await cast("Any", session).agent.run("more", session=session)
        except SessionError as error:
            refused = type(error)
        heard.append((session, cast("Any", session).id, refused))
        return SessionEndHookResult()

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def dropping(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> tuple[Any, str]:
        agent = agents["agent"]
        agent.on_session_end(ending)
        session = await agent.spawn(env=envs["env"])
        await agent.run("go", session=session)
        name = _handle(session).id
        del session
        await asyncio.sleep(0)
        return agent, name

    driver = FakeAgentDriver()
    agent, name = await run_fake(dropping, agents={"agent": driver})
    assert len(heard) == 1
    session, said, refused = heard[0]
    assert (said, refused) == (name, SessionError)
    assert session.agent is agent
    assert driver.sessions[0].closed


class BoomError(Exception):
    pass


async def test_a_hook_failing_between_turns_keeps_no_session_open() -> None:
    async def notified(params: NotificationHookParams) -> NotificationHookResult:
        raise BoomError(params.message)

    @flow(agents=Solo, envs=Place, params=Rounds)
    async def failing(
        task: str, *, agents: Solo, envs: Place, params: Rounds, ctx: FlowContext
    ) -> bool:
        agent = agents["agent"]
        agent.on_notification(notified)
        session = await agent.spawn(env=envs["env"])
        handle = _handle(session)
        await handle.notify("between turns")
        del session
        await asyncio.sleep(0)
        return handle.closed

    # Nothing collected: the session is to close for being let go of, not for a collection.
    gc.disable()
    try:
        assert await run_fake(failing)
    finally:
        gc.enable()
