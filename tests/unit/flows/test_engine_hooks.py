"""Hooks a flow hangs on its agents, and the outworlder a flow is handed.

A hook is called with the context of the flow the agent belongs to and the session the moment
arrived in, runs as that flow -- it may load and call flows of its own -- and is heard only by
that flow's sessions: a callee's hooks are not its caller's. What a hook raises fails the turn
it arrived in, as the flow's own code would.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pydantic
import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    CapabilityNotGranted,
    ClaudeCodeAgent,
    Env,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessKind,
    NotificationHookParams,
    NotificationHookResult,
    OutputSchemaError,
    Outworlder,
    OutworlderAway,
    OutworlderRunHookParams,
    OutworlderRunHookResult,
    SessionEndHookParams,
    SessionEndHookResult,
    SessionError,
    SessionStartHookParams,
    SessionStartHookResult,
    StopHookParams,
    StopHookResult,
    SubagentStartHookParams,
    SubagentStartHookResult,
    SubagentStopHookParams,
    SubagentStopHookResult,
    UnsupportedOperation,
    UserPromptSubmitHookParams,
    UserPromptSubmitHookResult,
    flow,
    load,
)
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeOutworlder, run_fake


class Claude(AgentCollection):
    agent: ClaudeCodeAgent


class Place(EnvCollection):
    env: Env


class Nothing(FlowParams):
    pass


def _echo(prompt: str, **_: Any) -> str:
    return prompt


class BoomError(Exception):
    pass


async def test_every_moment_reaches_its_hook_with_what_it_says() -> None:
    heard: list[tuple[str, Any]] = []

    async def start(params: SessionStartHookParams) -> SessionStartHookResult:
        heard.append(("start", params.ctx))
        return SessionStartHookResult(context="be brief")

    async def submit(params: UserPromptSubmitHookParams) -> UserPromptSubmitHookResult:
        heard.append(("submit", params.prompt))
        return UserPromptSubmitHookResult(context="and careful")

    async def notified(params: NotificationHookParams) -> NotificationHookResult:
        heard.append(("notification", params.message))
        return NotificationHookResult()

    async def sub_start(params: SubagentStartHookParams) -> SubagentStartHookResult:
        heard.append(("subagent start", (params.subagent, params.task)))
        return SubagentStartHookResult()

    async def sub_stop(params: SubagentStopHookParams) -> SubagentStopHookResult:
        heard.append(("subagent stop", (params.subagent, params.said)))
        return SubagentStopHookResult(block=True, reason="keep at it")

    async def stop(params: StopHookParams) -> StopHookResult:
        heard.append(("stop", (params.said, params.again)))
        return StopHookResult(block=params.again < 2, reason=f"again {params.again}")

    async def end(params: SessionEndHookParams) -> SessionEndHookResult:
        heard.append(("end", params.session))
        return SessionEndHookResult()

    @flow(agents=Claude, envs=Place, params=Nothing)
    async def hooked(
        task: str, *, agents: Claude, envs: Place, params: Nothing, ctx: FlowContext
    ) -> tuple[Any, Any, str]:
        agent = agents["agent"]
        agent.on_session_start(start)
        agent.on_user_prompt_submit(submit)
        agent.on_notification(notified)
        agent.on_subagent_start(sub_start)
        agent.on_subagent_stop(sub_stop)
        agent.on_stop(stop)
        agent.on_session_end(end)
        session = await agent.spawn(env=envs["env"])
        said = await agent.run("go", session=session)
        return ctx, session, said

    async def reply(prompt: str, *, session: Any, output_schema: Any) -> str:
        del output_schema
        await session.notify("working")
        kept = await session.subagent("helper", task="look", said="found it")
        return f"{prompt} | {kept}"

    driver = FakeAgentDriver(reply=reply)
    ctx, session, said = await run_fake(hooked, agents={"agent": driver})
    assert said == "again 1 | keep at it"
    assert heard[0] == ("start", ctx)
    assert heard[1] == ("submit", "be brief\n\ngo")
    kinds = [kind for kind, _ in heard]
    assert kinds.count("stop") == 3
    assert [said for kind, said in heard if kind == "stop"] == [
        ("be brief\n\ngo\n\nand careful | keep at it", 0),
        ("again 0 | keep at it", 1),
        ("again 1 | keep at it", 2),
    ]
    assert ("notification", "working") in heard
    assert ("subagent start", ("helper", "look")) in heard
    assert heard[-1] == ("end", session)
    assert driver.sessions[0].prompts[0] == "be brief\n\ngo\n\nand careful"


async def test_a_hook_taken_down_is_not_heard() -> None:
    heard: list[str] = []

    async def stop(params: StopHookParams) -> StopHookResult:
        heard.append(params.said)
        return StopHookResult()

    @flow(agents=Claude, envs=Place, params=Nothing)
    async def unhooking(
        task: str, *, agents: Claude, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        agent.on_stop(stop)
        await agent.run("heard", session=session)
        agent.on_stop(None)
        await agent.run("not heard", session=session)

    await run_fake(unhooking, agents={"agent": FakeAgentDriver(reply=_echo)})
    assert heard == ["heard"]


async def test_a_prompt_a_hook_blocks_is_not_taken() -> None:
    async def refuse(params: UserPromptSubmitHookParams) -> UserPromptSubmitHookResult:
        return UserPromptSubmitHookResult(block="secret" in params.prompt, reason="no")

    @flow(agents=Claude, envs=Place, params=Nothing)
    async def blocked(
        task: str, *, agents: Claude, envs: Place, params: Nothing, ctx: FlowContext
    ) -> str:
        agent = agents["agent"]
        agent.on_user_prompt_submit(refuse)
        session = await agent.spawn(env=envs["env"])
        with pytest.raises(SessionError, match="no"):
            await agent.run("the secret", session=session)
        return await agent.run("fine", session=session)

    driver = FakeAgentDriver()
    assert await run_fake(blocked, agents={"agent": driver}) == "ok"
    assert driver.prompts == ["fine"]


async def test_a_hook_that_raises_fails_the_turn_with_what_it_raised() -> None:
    async def failing(params: StopHookParams) -> StopHookResult:
        raise BoomError(params.said)

    @flow(agents=Claude, envs=Place, params=Nothing)
    async def failing_flow(
        task: str, *, agents: Claude, envs: Place, params: Nothing, ctx: FlowContext
    ) -> str:
        agent = agents["agent"]
        agent.on_stop(failing)
        session = await agent.spawn(env=envs["env"])
        with pytest.raises(BoomError, match="first"):
            await agent.run("x", session=session)
        agent.on_stop(None)
        return await agent.run("y", session=session)

    driver = FakeAgentDriver(reply=["first", "second"])
    assert await run_fake(failing_flow, agents={"agent": driver}) == "second"


async def test_a_hook_that_raises_while_a_turn_waits_interrupts_it() -> None:
    async def failing(params: NotificationHookParams) -> NotificationHookResult:
        raise BoomError(params.message)

    async def reply(prompt: str, *, session: Any, output_schema: Any) -> str:
        del prompt, output_schema
        await session.notify("now")
        return await session.until_steered()

    @flow(agents=Claude, envs=Place, params=Nothing)
    async def waiting(
        task: str, *, agents: Claude, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        agent.on_notification(failing)
        session = await agent.spawn(env=envs["env"])
        await agent.run("x", session=session)

    with pytest.raises(BoomError, match="now"):
        await run_fake(waiting, agents={"agent": FakeAgentDriver(reply=reply)})


class Worker(AgentCollection):
    agent: Agent


@flow(agents=Worker, envs=Place, params=Nothing)
async def callee(
    task: str, *, agents: Worker, envs: Place, params: Nothing, ctx: FlowContext
) -> None:
    heard = _CALLEE_HEARD

    async def mine(params: StopHookParams) -> StopHookResult:
        heard.append(f"callee heard {params.said}")
        return StopHookResult()

    agent = agents["agent"]
    agent.on_stop(mine)
    session = await agent.spawn(env=envs["env"])
    await agent.run("in the callee", session=session)


_CALLEE_HEARD: list[str] = []


async def test_a_hook_is_its_flow_s_alone() -> None:
    heard = _CALLEE_HEARD
    heard.clear()

    async def theirs(params: StopHookParams) -> StopHookResult:
        heard.append(f"caller heard {params.said}")
        return StopHookResult()

    @flow(agents=Claude, envs=Place, params=Nothing)
    async def caller(
        task: str, *, agents: Claude, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        agent.on_stop(theirs)
        session = await agent.spawn(env=envs["env"])
        await callee(task, agents={"agent": agent}, envs=envs, params=params)
        await agent.run("in the caller", session=session)

    await run_fake(caller, agents={"agent": FakeAgentDriver(reply=_echo)})
    assert heard == ["callee heard in the callee", "caller heard in the caller"]


async def test_a_hook_runs_as_its_flow_and_may_call_flows() -> None:
    @flow(agents=AgentCollection, envs=EnvCollection, params=Nothing)
    async def helper(
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: Nothing,
        ctx: FlowContext,
    ) -> str:
        return f"helped {task}"

    said: list[str] = []

    async def stop(params: StopHookParams) -> StopHookResult:
        said.append(
            await load(":helper")(params.said, agents={}, envs={}, params=Nothing())
        )
        return StopHookResult()

    @flow(agents=Claude, envs=Place, params=Nothing)
    async def hooked(
        task: str, *, agents: Claude, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        agent.on_stop(stop)
        session = await agent.spawn(env=envs["env"])
        await agent.run("x", session=session)

    await run_fake(hooked, agents={"agent": FakeAgentDriver(reply="done")})
    assert said == ["helped done"]


# ------------------------------------------------------------------------ outworlders


class Human(AgentCollection):
    human: Outworlder


class Form(pydantic.BaseModel):
    ok: bool = True
    why: str = ""


class Required(pydantic.BaseModel):
    answer: str


@flow(agents=Human, envs=Place, params=Nothing)
async def ask_human(
    task: str, *, agents: Human, envs: Place, params: Nothing, ctx: FlowContext
) -> list[Any]:
    human = agents["human"]
    session = await human.spawn(env=envs["env"])
    said: list[Any] = [
        human.away,
        await human.run(task, session=session),
        await human.run(task, session=session, output_schema=Form),
    ]
    try:
        said.append(await human.run(task, session=session, output_schema=Required))
    except OutworlderAway as error:
        said.append(type(error).__name__)
    return said


async def test_an_away_outworlder_answers_what_it_can_default() -> None:
    assert await run_fake(ask_human, "hi?") == [True, "", Form(), "OutworlderAway"]
    person = FakeOutworlder(reply="yes", away=True)
    assert await run_fake(ask_human, "hi?", outworlder=person) == [
        True,
        "",
        Form(),
        "OutworlderAway",
    ]
    assert person.asked == []


async def test_an_outworlder_there_answers() -> None:
    person = FakeOutworlder(reply=["yes", {"ok": False, "why": "no"}, {"answer": "42"}])
    assert await run_fake(ask_human, "hi?", outworlder=person) == [
        False,
        "yes",
        Form(ok=False, why="no"),
        Required(answer="42"),
    ]
    assert person.asked == ["hi?"] * 3


async def test_an_outworlder_who_goes_away_while_asked_is_answered_for() -> None:
    class Leaving(FakeOutworlder):
        async def run(self, prompt: str, output_schema: Any) -> Any:
            raise OutworlderAway("gone")

    assert await run_fake(ask_human, "hi?", outworlder=Leaving()) == [
        False,
        "",
        Form(),
        "OutworlderAway",
    ]


async def test_an_outworlder_s_wrong_answer_is_refused() -> None:
    @flow(agents=Human, envs=Place, params=Nothing)
    async def asking(
        task: str, *, agents: Human, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        human = agents["human"]
        session = await human.spawn(env=envs["env"])
        with pytest.raises(OutputSchemaError):
            await human.run(task, session=session)
        with pytest.raises(OutputSchemaError):
            await human.run(task, session=session, output_schema=Required)

    class Wrong:
        away = False

        async def run(self, prompt: str, output_schema: Any) -> Any:
            del prompt, output_schema
            return {"x": 1}

    await run_fake(asking, outworlder=Wrong())


async def test_an_outworlder_is_what_it_is() -> None:
    @flow(agents=Human, envs=Place, params=Nothing)
    async def looking(
        task: str, *, agents: Human, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        human = agents["human"]
        assert human.role == "human"
        assert human.harness is HarnessKind.ACP
        assert (human.model, human.effort, human.provider) == ("", "", "")
        assert human.derive() is human
        with pytest.raises(CapabilityNotGranted):
            human.derive(skills=("x",))
        with pytest.raises(TypeError):
            human.derive(permission="all")  # pyright: ignore[reportArgumentType]
        session = await human.spawn(env=envs["env"])
        assert session.usage.cost == 0
        with pytest.raises(UnsupportedOperation):
            await human.fork(session, env=envs["env"])
        with pytest.raises(CapabilityNotGranted):
            human.on_outworlder_run(None)
        human.on_stop(None)
        with pytest.raises(SessionError):
            await human.run("x", session=object())  # pyright: ignore[reportArgumentType]
        with pytest.raises(TypeError):
            await human.spawn(env=object())  # pyright: ignore[reportArgumentType]

    await run_fake(looking)


async def test_an_outworlder_made_by_a_flow_answers_through_its_hook() -> None:
    asked: list[tuple[str, Any]] = []

    async def answering(params: OutworlderRunHookParams) -> OutworlderRunHookResult:
        asked.append((params.prompt, params.output_schema))
        if params.output_schema is None:
            return OutworlderRunHookResult(output="typed")
        if params.output_schema is Form:
            return OutworlderRunHookResult(output=Form(ok=False))
        return OutworlderRunHookResult(output=Required(answer="made"))

    @flow(agents=AgentCollection, envs=Place, params=Nothing)
    async def making(
        task: str,
        *,
        agents: AgentCollection,
        envs: Place,
        params: Nothing,
        ctx: FlowContext,
    ) -> list[Any]:
        stand_in = Outworlder.new()
        assert stand_in.away
        stand_in.on_outworlder_run(answering)
        assert not stand_in.away
        said = await ask_human(
            task, agents={"human": stand_in}, envs=envs, params=params
        )
        stand_in.on_outworlder_run(None)
        return [*said, stand_in.away]

    said = await run_fake(making, "hi?")
    assert said == [False, "typed", Form(ok=False), Required(answer="made"), True]
    assert asked == [("hi?", None), ("hi?", Form), ("hi?", Required)]


async def test_an_outworlder_made_outside_a_run_answers_too() -> None:
    stand_in = Outworlder.new()

    async def answering(params: OutworlderRunHookParams) -> OutworlderRunHookResult:
        if params.output_schema is not None:
            return OutworlderRunHookResult(output=params.output_schema(answer="a"))
        return OutworlderRunHookResult(output=f"said {params.prompt}")

    stand_in.on_outworlder_run(answering)

    @flow(agents=AgentCollection, envs=Place, params=Nothing)
    async def passing(
        task: str,
        *,
        agents: AgentCollection,
        envs: Place,
        params: Nothing,
        ctx: FlowContext,
    ) -> list[Any]:
        return await ask_human(
            task, agents={"human": stand_in}, envs=envs, params=params
        )

    said = await run_fake(passing, "hi?")
    assert said == [False, "said hi?", Form(), Required(answer="a")]


async def test_turns_of_an_outworlder_wait_on_it() -> None:
    gate = asyncio.Event()

    async def slow(prompt: str, *, output_schema: Any) -> Any:
        await gate.wait()
        return prompt.upper() if output_schema is None else {"answer": prompt}

    async def open_gate() -> None:
        await asyncio.sleep(0.01)
        gate.set()

    opening = asyncio.ensure_future(open_gate())
    said = await run_fake(ask_human, "hi?", outworlder=FakeOutworlder(reply=slow))
    await opening
    assert said == [False, "HI?", Form(), Required(answer="hi?")]
