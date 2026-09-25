"""Flows calling flows at scale: deep, wide, long, resumable -- the flow layer alone.

Nothing here reaches a harness or an environment backend: every agent and environment is an
in-memory fake, and most of the flows never touch theirs. What is measured is what the engine
adds to a call.

What is timed is timed so it survives a machine running the whole suite on every core: CPU
time of this thread (`time.thread_time`), the best of five runs after a collection, and every
limit a ratio against the same work done in plain asyncio in the same test -- a slow machine
is slow at both -- with a generous absolute ceiling behind it that only a regression of an
order of magnitude trips. What can be counted rather than timed is counted: tasks started,
frames per level, journal records per call, bytes kept.

`uv run pytest tests/unit/flows/test_engine_scale.py -n0 -s` prints the timings.
"""

from __future__ import annotations

import asyncio
import gc
import itertools
import math
import sys
import time
import tracemalloc
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import (
    AgentCollection,
    Budget,
    EnvCollection,
    FlowContext,
    FlowDepthExceeded,
    FlowParams,
    flow,
)
from hmz.runtime.flowing import journaling
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, run_fake
from tests.flows.kit import Everything, Pair

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

#: What each measurement came to, for the table printed at the end.
TIMINGS: dict[str, str] = {}

#: How many times each measurement is taken; the best of them counts.
BEST_OF = 5


class Envs(EnvCollection):
    repo: Everything


class Shape(FlowParams):
    depth: int = 0
    fanout: int = 1
    level: int = 0
    gather: bool = False
    calls: int = 0


#: The params each level of a tree is called with, made once so that neither the engine nor
#: the plain-asyncio baseline spends a tree's time validating them.
LEVELS: dict[tuple[int, int, bool], list[Shape]] = {}


def _levels(depth: int, fanout: int, gather: bool) -> list[Shape]:
    key = (depth, fanout, gather)
    if key not in LEVELS:
        LEVELS[key] = [
            Shape(depth=depth, fanout=fanout, level=level, gather=gather)
            for level in range(depth + 1)
        ]
    return LEVELS[key]


def _fanout(params: Shape) -> int:
    """Three children apiece, but one each for the last level: 10 levels, 16,402 nodes."""
    if params.fanout != 0:
        return params.fanout
    return 3 if params.level < params.depth - 1 else 1


@flow(agents=Pair, envs=Envs, params=Shape)
async def tree(
    task: str, *, agents: Pair, envs: Envs, params: Shape, ctx: FlowContext
) -> int:
    """A tree of calls to itself, `depth` levels below this one."""
    if params.level == params.depth:
        return 1
    below = _levels(params.depth, params.fanout, params.gather)[params.level + 1]
    children: Pair = {"a": agents["a"], "b": agents["b"]}
    places: Envs = {"repo": envs["repo"]}
    if params.gather:
        counted = await asyncio.gather(
            *(
                tree(task, agents=children, envs=places, params=below)
                for _ in range(_fanout(params))
            )
        )
        return 1 + sum(counted)
    total = 1
    for _ in range(_fanout(params)):
        total += await tree(task, agents=children, envs=places, params=below)
    return total


async def raw_tree(
    task: str, *, agents: dict[str, Any], envs: dict[str, Any], params: Shape, ctx: Any
) -> int:
    """The same tree in plain asyncio: the same body, and no engine under it."""
    if params.level == params.depth:
        return 1
    below = _levels(params.depth, params.fanout, params.gather)[params.level + 1]
    children = {"a": agents["a"], "b": agents["b"]}
    places = {"repo": envs["repo"]}
    if params.gather:
        counted = await asyncio.gather(
            *(
                raw_tree(task, agents=children, envs=places, params=below, ctx=ctx)
                for _ in range(_fanout(params))
            )
        )
        return 1 + sum(counted)
    total = 1
    for _ in range(_fanout(params)):
        total += await raw_tree(
            task, agents=children, envs=places, params=below, ctx=ctx
        )
    return total


@flow(agents=Pair, envs=Envs, params=Shape)
async def leaf(
    task: str, *, agents: Pair, envs: Envs, params: Shape, ctx: FlowContext
) -> None:
    """Does nothing: what calling it costs is the engine's alone."""


@flow(agents=Pair, envs=Envs, params=Shape, resumable=True)
async def looping(
    task: str, *, agents: Pair, envs: Envs, params: Shape, ctx: FlowContext
) -> float:
    """Calls `leaf` `calls` times in a row, and answers how long that took, per call."""
    below = Shape()
    started = time.thread_time()
    for _ in range(params.calls):
        await leaf(task, agents=agents, envs=envs, params=below)
    return (time.thread_time() - started) / max(params.calls, 1)


@flow(agents=Pair, envs=Envs, params=Shape, resumable=True)
async def resumable_leaf(
    task: str, *, agents: Pair, envs: Envs, params: Shape, ctx: FlowContext
) -> None:
    """Does nothing, as a flow a resumed run picks up."""


@flow(agents=Pair, envs=Envs, params=Shape, resumable=True)
async def looping_resumable(
    task: str, *, agents: Pair, envs: Envs, params: Shape, ctx: FlowContext
) -> float:
    """Calls `resumable_leaf` `calls` times in a row, journaled."""
    below = Shape()
    started = time.thread_time()
    for _ in range(params.calls):
        await resumable_leaf(task, agents=agents, envs=envs, params=below)
    return (time.thread_time() - started) / max(params.calls, 1)


async def _fake(flow_: Any, **said: Any) -> Any:
    return await run_fake(
        flow_,
        "scale",
        agents={"a": FakeAgentDriver(), "b": FakeAgentDriver()},
        envs={"repo": FakeEnvDriver()},
        budget=Budget(cost=math.inf),
        **said,
    )


async def _best(measure: Callable[[], Awaitable[float]]) -> float:
    """The least of several measurements, each after a collection."""
    best = math.inf
    for _ in range(BEST_OF):
        gc.collect()
        best = min(best, await measure())
    return best


async def _timed_tree(*, depth: int, fanout: int, gather: bool) -> tuple[float, int]:
    started = time.thread_time()
    nodes = await _fake(tree, params=_levels(depth, fanout, gather)[0])
    return time.thread_time() - started, nodes


async def _timed_raw(*, depth: int, fanout: int, gather: bool) -> tuple[float, int]:
    agents = {"a": object(), "b": object()}
    envs = {"repo": object()}
    started = time.thread_time()
    nodes = await raw_tree(
        "scale",
        agents=agents,
        envs=envs,
        params=_levels(depth, fanout, gather)[0],
        ctx=None,
    )
    return time.thread_time() - started, nodes


def _us(seconds: float) -> str:
    return f"{seconds * 1e6:.2f} µs"


# ----------------------------------------------------------------------------- scale


async def test_a_call_ten_levels_deep_is_ten_calls() -> None:
    assert await _fake(tree, params=_levels(9, 1, False)[0]) == 10


async def test_ten_flows_call_each_other_in_a_chain() -> None:
    assert await _fake(CHAIN[0]) == [f"link{n}" for n in range(10)]


def _link(n: int) -> Any:
    async def link(
        task: str, *, agents: Pair, envs: Envs, params: Shape, ctx: FlowContext
    ) -> list[str]:
        name: str = cast("Any", ctx.flow).name
        if n == len(CHAIN) - 1:
            return [name]
        rest = await CHAIN[n + 1](task, agents=agents, envs=envs, params=params)
        return [name, *rest]

    return flow(agents=Pair, envs=Envs, params=Shape, name=f"link{n}")(link)


CHAIN: list[Any] = []
CHAIN.extend(_link(n) for n in range(10))


@pytest.mark.parametrize("gather", [False, True], ids=["sequential", "gathered"])
async def test_a_tree_of_29524_calls_runs_whole(gather: bool) -> None:
    elapsed, nodes = await _timed_tree(depth=9, fanout=3, gather=gather)
    assert nodes == 29_524
    raw, raw_nodes = await _timed_raw(depth=9, fanout=3, gather=gather)
    assert raw_nodes == nodes
    TIMINGS[
        f"29,524-node tree, fan-out 3, {'gathered' if gather else 'sequential'}"
    ] = f"{elapsed:.3f} s  ({_us(elapsed / nodes)}/node, {elapsed / raw:.1f}x asyncio)"
    assert elapsed < 15, f"{nodes} calls took {elapsed:.1f}s of CPU"


async def test_a_ten_level_tree_of_ten_thousand_calls_takes_under_half_a_second() -> (
    None
):
    async def measured() -> float:
        elapsed, nodes = await _timed_tree(depth=9, fanout=0, gather=False)
        assert nodes == 16_402
        return elapsed

    async def raw() -> float:
        elapsed, _ = await _timed_raw(depth=9, fanout=0, gather=False)
        return elapsed

    best = await _best(measured)
    baseline = await _best(raw)
    TIMINGS["16,402-node tree, 10 levels, sequential"] = (
        f"{best:.3f} s  ({_us(best / 16_402)}/node, {best / baseline:.1f}x asyncio)"
    )
    assert best / baseline <= 25, f"{best / baseline:.1f}x a plain asyncio tree"
    assert best < 0.5 * 2.5, f"{best:.3f}s of CPU for 16,402 calls"


async def test_a_gathered_tree_costs_little_more_than_asyncio_s_own() -> None:
    async def measured() -> float:
        return (await _timed_tree(depth=7, fanout=3, gather=True))[0]

    async def raw() -> float:
        return (await _timed_raw(depth=7, fanout=3, gather=True))[0]

    best, baseline = await _best(measured), await _best(raw)
    TIMINGS["3,280-node tree, fan-out 3, gathered"] = (
        f"{best:.3f} s  ({best / baseline:.1f}x asyncio)"
    )
    assert best / baseline <= 25


# -------------------------------------------------------------------------- per call


async def test_a_sequential_call_costs_under_ten_microseconds() -> None:
    async def measured() -> float:
        return await _fake(looping, params=Shape(calls=20_000))

    async def raw() -> float:
        agents = {"a": object(), "b": object()}
        envs = {"repo": object()}
        below = Shape()

        async def nothing(
            task: str, *, agents: Any, envs: Any, params: Shape, ctx: Any
        ) -> None:
            del task, agents, envs, params, ctx

        started = time.thread_time()
        for _ in range(20_000):
            await nothing("scale", agents=agents, envs=envs, params=below, ctx=None)
        return (time.thread_time() - started) / 20_000

    best, baseline = await _best(measured), await _best(raw)
    TIMINGS["sequential call, 2 agents + 1 env"] = (
        f"{_us(best)}  (plain coroutine call: {_us(baseline)})"
    )
    assert best < 10e-6 * 3, f"{_us(best)} per call"
    assert best < 50e-6


async def test_a_journaled_call_costs_under_twenty_five_microseconds(
    tmp_path: Path,
) -> None:
    runs = iter(range(BEST_OF * 2))

    async def measured() -> float:
        journal = tmp_path / f"run-{next(runs)}.jsonl"
        return await _fake(
            looping_resumable, params=Shape(calls=10_000), journal=journal
        )

    best = await _best(measured)
    TIMINGS["journaled call (resumable run)"] = _us(best)
    assert best < 25e-6 * 3, f"{_us(best)} per journaled call"


async def test_calls_scale_linearly() -> None:
    async def per(calls: int) -> float:
        async def measured() -> float:
            return await _fake(looping, params=Shape(calls=calls))

        return await _best(measured) * calls

    small, large = await per(2_000), await per(8_000)
    TIMINGS["t(8,000 calls) / t(2,000 calls)"] = f"{large / small:.2f}"
    assert large / small <= 6


# ------------------------------------------------------------------------- counted


async def test_a_sequential_tree_starts_no_task_and_adds_two_frames_a_level() -> None:
    loop = asyncio.get_running_loop()
    made: list[object] = []
    factory = loop.get_task_factory()

    def counting(loop: asyncio.AbstractEventLoop, coro: Any, **kw: Any) -> Any:
        made.append(coro)
        return asyncio.Task(coro, loop=loop, **kw)

    depths: list[int] = []

    @flow(agents=Pair, envs=Envs, params=Shape)
    async def measuring(
        task: str, *, agents: Pair, envs: Envs, params: Shape, ctx: FlowContext
    ) -> None:
        frame: Any = sys._getframe()
        count = 0
        while frame is not None:
            count += 1
            frame = frame.f_back
        depths.append(count)
        if params.level < 9:
            await measuring(
                task, agents=agents, envs=envs, params=Shape(level=params.level + 1)
            )

    loop.set_task_factory(counting)
    try:
        await _fake(measuring)
    finally:
        loop.set_task_factory(factory)
    assert made == []
    assert {b - a for a, b in itertools.pairwise(depths)} == {2}


async def test_a_journal_holds_two_records_a_call_written_in_few_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[Any] = []
    real = journaling.Journal.opened

    def spying(*args: Any, **kwargs: Any) -> Any:
        said = real(*args, **kwargs)
        opened.append(said[0])
        return said

    monkeypatch.setattr(journaling.Journal, "opened", spying)
    journal = tmp_path / "run.jsonl"
    await _fake(looping_resumable, params=Shape(calls=10_000), journal=journal)
    written = opened[0]
    assert written.records == 2 * 10_001
    assert written.writes <= 50, f"{written.writes} writes for 10,001 calls"
    size = journal.stat().st_size
    assert size < 10_001 * 200, f"{size} bytes for 10,001 calls"
    TIMINGS["journal of 10,001 calls"] = (
        f"{size / 1024:.0f} KiB in {written.writes} writes, {written.records} records"
    )


async def test_a_hundred_thousand_calls_keep_nothing() -> None:
    await _fake(looping, params=Shape(calls=1_000))
    gc.collect()
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        await _fake(looping, params=Shape(calls=100_000))
        gc.collect()
        after, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    grown = after - before
    TIMINGS["memory kept after 100,000 calls"] = f"{grown / 1024:.1f} KiB"
    assert grown < 5 * 1024 * 1024, f"{grown} bytes kept"


async def test_the_depth_limit_is_a_flow_error_at_any_recursion_limit() -> None:
    @flow(agents=AgentCollection, envs=EnvCollection, params=Shape)
    async def endless(
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: Shape,
        ctx: FlowContext,
    ) -> None:
        await endless(task, agents={}, envs={}, params=params)

    started = time.thread_time()
    with pytest.raises(FlowDepthExceeded):
        await run_fake(endless)
    TIMINGS["depth limit reached (64 calls)"] = _us(time.thread_time() - started)


def test_zz_the_timings() -> None:
    """Prints what was measured, as a table; run with `-s` to see it."""
    width = max(map(len, TIMINGS), default=0)
    lines = [f"{name.ljust(width)}  {said}" for name, said in TIMINGS.items()]
    sys.stdout.write("\n" + "\n".join(lines) + "\n")
