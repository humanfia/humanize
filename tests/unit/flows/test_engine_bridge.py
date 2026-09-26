"""The hook bridge keeps an answer that arrives as it is about to give up.

A driver thread waiting on a hook is woken by the hook finishing and by the call being given
up on alike. One that finishes between the bridge's two looks -- still running at the first,
waking the thread by the second -- is an answer, and a flow's `block` must not be dropped for
the default because of when it arrived.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from typing import Any

from hmz.runtime.flowing.spi import HookBridge


class _Late(concurrent.futures.Future[Any]):
    """A future that says it is not done the first time it is asked, and is."""

    def __init__(self) -> None:
        super().__init__()
        self.asked = 0

    def done(self) -> bool:
        self.asked += 1
        return self.asked > 1 and super().done()


async def test_an_answer_that_lands_between_the_bridge_s_looks_is_kept() -> None:
    bridge = HookBridge.here(timeout=5)
    loop = asyncio.get_running_loop()
    flying = _Late()
    flying.set_result("block it")
    woke = threading.Event()
    woke.set()

    def wait() -> Any:
        return bridge._waited(loop, flying, woke, "the default")

    assert await asyncio.to_thread(wait) == "block it"


async def test_a_call_given_up_on_still_answers_its_default() -> None:
    bridge = HookBridge.here(timeout=5)
    loop = asyncio.get_running_loop()
    flying: concurrent.futures.Future[Any] = concurrent.futures.Future()
    woke = threading.Event()
    woke.set()

    def wait() -> Any:
        return bridge._waited(loop, flying, woke, "the default")

    assert await asyncio.to_thread(wait) == "the default"
    assert flying.cancelled()
