"""Hooks as a driver reaches them: the table an agent's hooks hang on, and the bridge onto the loop.

A CLI reaches a moment on whatever thread is reading it; the hook is a coroutine on the
engine's loop. The bridge carries the call across and waits -- and answers the default
instead whenever waiting would hang a thread on a loop that is gone, or deadlock the loop on
itself.
"""

from __future__ import annotations

import asyncio
import dataclasses
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import (
    HOOK_TYPES,
    HookKind,
    HookResult,
    PreToolUseHookResult,
    SessionStartHookResult,
    StopHookResult,
)
from hmz.runtime.flowing import spi
from hmz.runtime.flowing.spi import HookBridge, HookTable, default_result

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.runtime.flowing.spi import SessionHandle


def _on_a_thread[R](call: Callable[[], R]) -> R:
    """Runs a call on a thread of its own, as a driver's reader would, and waits for it."""
    said: list[R] = []
    thread = threading.Thread(target=lambda: said.append(call()))
    thread.start()
    thread.join(30)
    assert not thread.is_alive(), "the call never came back"
    return said[0]


async def _answer(value: str = "answered") -> str:
    await asyncio.sleep(0)
    return value


# ---------------------------------------------------------------------------- the table


@pytest.mark.parametrize(
    "kind", [one for one in HookKind if one is not HookKind.OUTWORLDER_RUN]
)
def test_a_moment_with_nothing_hung_on_it_changes_nothing(kind: HookKind) -> None:
    result = default_result(kind)
    assert type(result) is HOOK_TYPES[kind][1]
    assert all(
        getattr(result, field.name) in ("", None, False, True, 0, ())
        for field in dataclasses.fields(result)
    )


def test_an_outworlder_run_has_no_default_answer() -> None:
    with pytest.raises(ValueError, match="no answer"):
        default_result(HookKind.OUTWORLDER_RUN)


def test_every_moment_has_its_params_and_its_result() -> None:
    assert set(HOOK_TYPES) == set(HookKind)
    for kind, (params, result) in HOOK_TYPES.items():
        assert params.__name__.removesuffix(
            "HookParams"
        ) == result.__name__.removesuffix("HookResult"), kind
        assert {"ctx", "session"} <= {one.name for one in dataclasses.fields(params)}


async def test_a_table_fires_what_is_hung_and_defaults_what_is_not() -> None:
    table = HookTable()
    heard: list[tuple[object, dict[str, Any]]] = []

    async def stop(handle: SessionHandle, fields: dict[str, Any]) -> HookResult:
        heard.append((handle, fields))
        return StopHookResult(block=True, reason="again")

    handle: Any = object()
    assert HookKind.STOP not in table
    assert (
        await table.fire(HookKind.STOP, handle, said="done", again=0)
        == StopHookResult()
    )

    table.set(HookKind.STOP, stop)
    assert HookKind.STOP in table
    assert table.get(HookKind.STOP) is stop
    said = await table.fire(HookKind.STOP, handle, said="done", again=2)
    assert said == StopHookResult(block=True, reason="again")
    assert heard == [(handle, {"said": "done", "again": 2})]

    table.set(HookKind.STOP, None)
    table.set(HookKind.PRE_TOOL_USE, None)
    assert HookKind.STOP not in table
    assert table.get(HookKind.STOP) is None
    assert await table.fire(HookKind.PRE_TOOL_USE, handle, tool="Bash") == (
        PreToolUseHookResult()
    )


# --------------------------------------------------------------------------- the bridge


async def test_a_thread_waits_for_the_hook_on_the_loop() -> None:
    bridge = HookBridge.here()
    loop = asyncio.get_running_loop()
    ran_on: list[asyncio.AbstractEventLoop] = []

    async def hook() -> str:
        ran_on.append(asyncio.get_running_loop())
        return await _answer()

    said = await asyncio.to_thread(bridge.call, hook, default="default")
    assert said == "answered"
    assert ran_on == [loop]


async def test_many_threads_at_once_each_get_their_own_answer() -> None:
    bridge = HookBridge.here()

    def ask(number: int) -> str:
        return bridge.call(lambda: _answer(f"answer {number}"), default="default")

    said = await asyncio.gather(*(asyncio.to_thread(ask, one) for one in range(16)))
    assert said == [f"answer {one}" for one in range(16)]


async def test_the_loop_own_thread_is_answered_the_default_rather_than_deadlocked() -> (
    None
):
    bridge = HookBridge.here()
    made: list[int] = []

    def make() -> Any:
        made.append(1)
        return _answer()

    assert bridge.call(make, default="default") == "default"
    assert made == [], "a coroutine was made that nothing would run"


async def test_a_hook_that_takes_too_long_is_given_up_on_and_cancelled() -> None:
    bridge = HookBridge.here(timeout=0.05)
    cancelled = asyncio.Event()

    async def forever() -> str:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "never"

    started = time.monotonic()
    assert await asyncio.to_thread(bridge.call, forever, default="default") == "default"
    assert time.monotonic() - started < 5
    await asyncio.wait_for(cancelled.wait(), 5)


async def test_a_hook_that_raises_is_answered_the_default() -> None:
    bridge = HookBridge.here()

    async def broken() -> str:
        raise RuntimeError("the hook fell over")

    assert await asyncio.to_thread(bridge.call, broken, default="default") == "default"


async def test_a_hook_that_times_out_itself_is_not_taken_for_the_wait_timing_out() -> (
    None
):
    bridge = HookBridge.here()

    async def impatient() -> str:
        async with asyncio.timeout(0):
            await asyncio.sleep(1)
        return "never"

    call = asyncio.to_thread(bridge.call, impatient, default="default")
    assert await asyncio.wait_for(call, 5) == "default"


async def test_abandoning_answers_every_waiting_call_at_once() -> None:
    bridge = HookBridge.here()
    waiting = asyncio.Event()

    async def forever() -> str:
        waiting.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # A hook slow to let go must not hold the thread that gave up on it.
            await asyncio.shield(asyncio.sleep(2))
            raise
        return "never"

    call = asyncio.create_task(
        asyncio.to_thread(bridge.call, forever, default="default")
    )
    await asyncio.wait_for(waiting.wait(), 5)
    started = time.monotonic()
    bridge.abandon()
    assert await asyncio.wait_for(call, 5) == "default"
    assert time.monotonic() - started < 1, "the thread waited for the hook to let go"
    assert (
        await asyncio.to_thread(bridge.call, _answer, default="default") == "answered"
    )


async def test_a_closed_bridge_answers_every_call_with_the_default() -> None:
    bridge = HookBridge.here()
    waiting = asyncio.Event()

    async def forever() -> str:
        waiting.set()
        await asyncio.sleep(3600)
        return "never"

    call = asyncio.create_task(
        asyncio.to_thread(bridge.call, forever, default="default")
    )
    await asyncio.wait_for(waiting.wait(), 5)
    bridge.close()
    bridge.close()
    assert await asyncio.wait_for(call, 5) == "default"
    made: list[int] = []

    def make() -> Any:
        made.append(1)
        return _answer()

    assert await asyncio.to_thread(bridge.call, make, default="default") == "default"
    assert made == []


def test_no_loop_is_the_default() -> None:
    assert HookBridge(None).call(_answer, default="default") == "default"


def test_a_loop_that_is_closed_or_not_running_is_the_default() -> None:
    loop = asyncio.new_event_loop()
    try:
        bridge = HookBridge(loop)
        assert (
            _on_a_thread(lambda: bridge.call(_answer, default="default")) == "default"
        )
    finally:
        loop.close()
    assert _on_a_thread(lambda: bridge.call(_answer, default="default")) == "default"


def test_a_loop_that_stops_while_a_thread_waits_lets_the_thread_go() -> None:
    loop = asyncio.new_event_loop()
    bridge = HookBridge(loop)
    waiting = threading.Event()

    async def forever() -> str:
        waiting.set()
        await asyncio.sleep(3600)
        return "never"

    said: list[str] = []
    running = threading.Thread(target=loop.run_forever)
    running.start()
    try:
        asking = threading.Thread(
            target=lambda: said.append(bridge.call(forever, default="default"))
        )
        asking.start()
        assert waiting.wait(5)
        loop.call_soon_threadsafe(loop.stop)
        asking.join(10)
        assert not asking.is_alive(), "the thread waited on a loop that had stopped"
        assert said == ["default"]
    finally:
        if running.is_alive():
            loop.call_soon_threadsafe(loop.stop)
            running.join(10)
        left = asyncio.all_tasks(loop)
        for task in left:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*left, return_exceptions=True))
        loop.close()


async def test_a_call_made_while_making_a_call_is_answered_its_default() -> None:
    bridge = HookBridge.here(timeout=10)
    inner: list[str] = []

    def make() -> Any:
        inner.append(bridge.call(_answer, default="inner default"))
        return _answer("outer")

    said = await asyncio.wait_for(
        asyncio.to_thread(bridge.call, make, default="default"), 5
    )
    assert (said, inner) == ("outer", ["inner default"])


async def test_a_thread_already_inside_a_bridged_call_is_not_carried_again() -> None:
    bridge = HookBridge.here()

    def nested() -> str:
        spi._INSIDE.on = True
        try:
            return bridge.call(_answer, default="default")
        finally:
            spi._INSIDE.on = False

    assert await asyncio.to_thread(nested) == "default"


async def test_what_a_bridged_table_fires_comes_back_to_the_driver_thread() -> None:
    table = HookTable()

    async def start(handle: SessionHandle, fields: dict[str, Any]) -> HookResult:
        del handle, fields
        return SessionStartHookResult(context="read AGENTS.md first")

    table.set(HookKind.SESSION_START, start)
    bridge = HookBridge.here(timeout=10)
    handle: Any = object()
    said = await asyncio.to_thread(
        bridge.call,
        lambda: table.fire(HookKind.SESSION_START, handle),
        default=default_result(HookKind.SESSION_START),
    )
    assert said == SessionStartHookResult(context="read AGENTS.md first")
