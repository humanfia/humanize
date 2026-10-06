"""The seam between the engine and its drivers: capabilities, hooks, and the bridge to the loop."""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
from typing import Any

import pytest

from hmz.flows import (
    HARNESS_AGENTS,
    HOOK_TYPES,
    Agent,
    BashEnvMixin,
    ClaudeCodeAgent,
    EnvBackendKind,
    GitWorktreeEnvMixin,
    GoalCommandAgentMixin,
    HarnessKind,
    HookKind,
    HookResult,
    ImageEnvMixin,
    ShellEnvMixin,
    SteeringAgentMixin,
    StopHookResult,
)
from hmz.runtime.flowing.spi import (
    AGENT_CAPABILITIES,
    ENV_CAPABILITIES,
    ENV_TOOLS,
    HARNESS_CAPABILITIES,
    HookBridge,
    HookTable,
    Limits,
    Placement,
    SessionHandle,
    TurnRequest,
    capabilities_of,
    default_result,
)

# --------------------------------------------------------------------------- capabilities


def test_agent_and_env_capabilities_are_apart() -> None:
    assert AGENT_CAPABILITIES.isdisjoint(ENV_CAPABILITIES)
    assert ImageEnvMixin not in ENV_CAPABILITIES, "a value, not a behaviour"
    assert set(ENV_TOOLS) <= ENV_CAPABILITIES
    assert set(ENV_TOOLS.values()) == {"git", "bash"}


def test_a_roles_capabilities_are_read_off_its_bases_with_theirs() -> None:
    class Coder(Agent, SteeringAgentMixin): ...

    class Shell(BashEnvMixin): ...

    assert capabilities_of(Coder) == {SteeringAgentMixin}
    assert capabilities_of(Shell) == {BashEnvMixin, ShellEnvMixin}
    assert capabilities_of(Agent) == frozenset()
    assert capabilities_of(GitWorktreeEnvMixin) >= {GitWorktreeEnvMixin}


def test_every_harness_serves_exactly_what_its_protocol_declares() -> None:
    assert set(HARNESS_CAPABILITIES) == set(HARNESS_AGENTS)
    for kind, protocol in HARNESS_AGENTS.items():
        assert HARNESS_CAPABILITIES[kind] == capabilities_of(protocol)
        assert HARNESS_CAPABILITIES[kind] <= AGENT_CAPABILITIES
    assert GoalCommandAgentMixin in capabilities_of(ClaudeCodeAgent)
    assert HARNESS_CAPABILITIES[HarnessKind.ACP] == frozenset()


# ------------------------------------------------------------------------------ one turn


def test_a_turn_asks_for_text_with_no_limit_by_default() -> None:
    request = TurnRequest("hi")

    assert request.output_schema is None
    assert request.limits == Limits(None, None, None, graceful=True)


def test_a_placement_is_this_machines_workspace_unless_told_otherwise() -> None:
    placement = Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/w"))

    assert (placement.machine, placement.env) == (None, "")
    assert placement == Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/w"))
    assert hash(placement) == hash(
        Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/w"))
    )


# ---------------------------------------------------------------------------------- hooks


@pytest.mark.parametrize(
    "kind", [one for one in HookKind if one is not HookKind.OUTWORLDER_RUN]
)
def test_a_moment_with_no_hook_comes_to_its_result_built_with_nothing(
    kind: HookKind,
) -> None:
    said = default_result(kind)

    assert type(said) is HOOK_TYPES[kind][1]


def test_an_outworlders_run_has_no_answer_to_default_to() -> None:
    with pytest.raises(ValueError, match="no answer"):
        default_result(HookKind.OUTWORLDER_RUN)


async def test_a_table_fires_the_hook_hung_on_a_moment_or_answers_the_default() -> None:
    table = HookTable()
    told: list[tuple[object, dict[str, Any]]] = []
    session: Any = object()

    async def stop(handle: SessionHandle, fields: dict[str, Any]) -> HookResult:
        told.append((handle, fields))
        return StopHookResult(block=True, reason="again")

    assert HookKind.STOP not in table
    assert await table.fire(HookKind.STOP, session, said="x") == StopHookResult()

    table.set(HookKind.STOP, stop)
    said = await table.fire(HookKind.STOP, session, said="x", again=0)

    assert HookKind.STOP in table
    assert table.get(HookKind.STOP) is stop
    assert said == StopHookResult(block=True, reason="again")
    assert told == [(session, {"said": "x", "again": 0})]

    table.set(HookKind.STOP, None)
    table.set(HookKind.STOP, None)
    assert HookKind.STOP not in table
    assert table.get(HookKind.STOP) is None


# --------------------------------------------------------------------------------- bridge


async def _answer(value: str) -> str:
    return value


async def test_a_call_from_another_thread_runs_on_the_loop_and_answers() -> None:
    bridge = HookBridge.here()
    loop = asyncio.get_running_loop()
    ran_on: list[asyncio.AbstractEventLoop] = []

    async def where() -> str:
        ran_on.append(asyncio.get_running_loop())
        return "answered"

    said = await asyncio.to_thread(bridge.call, where, default="default")

    assert said == "answered"
    assert ran_on == [loop]


async def test_a_call_from_the_loops_own_thread_answers_its_default_without_waiting() -> (
    None
):
    bridge = HookBridge.here()
    made: list[int] = []

    def make() -> Any:
        made.append(1)
        return _answer("never")

    assert bridge.call(make, default="default") == "default"
    assert made == [], "no coroutine was made to be left unawaited"


async def test_a_call_that_raises_answers_its_default(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = HookBridge.here()

    async def broken() -> str:
        raise RuntimeError("hook bug")

    said = await asyncio.to_thread(bridge.call, broken, default="default")

    assert said == "default"
    assert "raised" in caplog.text


async def test_a_call_that_outlives_its_timeout_is_cancelled_and_answers_its_default() -> (
    None
):
    bridge = HookBridge.here(timeout=0.01)
    cancelled = asyncio.Event()

    async def forever() -> str:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "never"

    said = await asyncio.to_thread(bridge.call, forever, default="default")

    assert said == "default"
    await asyncio.wait_for(cancelled.wait(), 5)


async def test_an_abandoned_call_answers_its_default_at_once() -> None:
    bridge = HookBridge.here()
    started = asyncio.Event()

    async def forever() -> str:
        started.set()
        await asyncio.Event().wait()
        return "never"

    waiting = asyncio.ensure_future(
        asyncio.to_thread(bridge.call, forever, default="gave up")
    )
    await started.wait()
    bridge.abandon()

    assert await waiting == "gave up"
    assert (
        await asyncio.to_thread(bridge.call, lambda: _answer("again"), default="d")
        == "again"
    )


async def test_a_closed_bridge_answers_every_call_with_its_default() -> None:
    bridge = HookBridge.here()
    bridge.close()

    assert (
        await asyncio.to_thread(bridge.call, lambda: _answer("x"), default="d") == "d"
    )


def test_a_bridge_onto_no_loop_or_a_stopped_one_answers_its_default() -> None:
    stopped = asyncio.new_event_loop()
    try:
        assert HookBridge(None).call(lambda: _answer("x"), default="d") == "d"
        assert HookBridge(stopped).call(lambda: _answer("x"), default="d") == "d"
    finally:
        stopped.close()
    assert HookBridge(stopped).call(lambda: _answer("x"), default="d") == "d"


def test_a_bridge_here_needs_a_running_loop() -> None:
    with pytest.raises(RuntimeError):
        HookBridge.here()


async def test_a_call_made_inside_a_bridged_call_does_not_wait_on_itself() -> None:
    bridge = HookBridge.here()

    def nested() -> Any:
        inner = bridge.call(lambda: _answer("inner"), default="inner default")
        return _answer(f"outer saw {inner}")

    said = await asyncio.to_thread(bridge.call, nested, default="outer default")

    assert said == "outer saw inner default"
