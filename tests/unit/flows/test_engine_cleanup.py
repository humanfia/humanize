"""What a flow call leaves behind: nothing, once it and everything it started are over.

Sessions a call opened are closed, and the temporary copies and scratch directories it made
are removed, when the call ends -- or, where calls it started are still running, when the last
of them does. Removing them is shielded from cancellation and given a time limit. A resumable
run keeps its directories, for the run to be picked up in.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    Env,
    EnvCollection,
    FlowCancelled,
    FlowContext,
    FlowParams,
    ScratchDirEnvMixin,
    SessionEndHookParams,
    SessionEndHookResult,
    TempCloneBusy,
    TemporaryClonedDirEnvMixin,
    flow,
)
from hmz.runtime.flowing import engine
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, run_fake

if TYPE_CHECKING:
    from pathlib import Path


class Solo(AgentCollection):
    agent: Agent


class Dirs(Env, TemporaryClonedDirEnvMixin, ScratchDirEnvMixin): ...


class Place(EnvCollection):
    env: Dirs


class Nothing(FlowParams):
    wait: bool = False


class BoomError(Exception):
    pass


def _driver(env: object) -> FakeEnvDriver:
    """The fake under an environment view."""
    return cast("Any", env).driver


@flow(agents=Solo, envs=Place, params=Nothing)
async def making(
    task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
) -> Any:
    """Makes a copy, a scratch directory and a session, and hands them back."""
    env = envs["env"]
    clone = await env.derive_temp_clone("copy")
    again = await env.derive_temp_clone("copy")
    scratch = await env.derive_scratch("notes")
    session = await agents["agent"].spawn(env=clone)
    assert again.workdir == clone.workdir
    if params.wait:
        await asyncio.sleep(30)
    if task == "fail":
        raise BoomError
    return clone, scratch, session


async def test_what_a_call_made_goes_when_it_ends() -> None:
    @flow(agents=Solo, envs=Place, params=Nothing)
    async def parent(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> list[Any]:
        driver = _driver(envs["env"])
        _, _, session = await making(task, agents=agents, envs=envs, params=params)
        after = [driver.clones, driver.scratches, session._handle.closed]
        with pytest.raises(BoomError):
            await making("fail", agents=agents, envs=envs, params=params)
        after.append([driver.clones, driver.scratches])
        return after

    env = FakeEnvDriver({"a.txt": "a"})
    said = await run_fake(parent, envs={"env": env})
    assert said == [[], [], True, [[], []]]
    assert list(env.machine) == ["/work/a.txt"]


async def test_what_a_call_made_waits_for_the_calls_it_started() -> None:
    finished = asyncio.Event()
    observed: list[Any] = []

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def child(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        await finished.wait()
        await envs["env"].derive_subdir(subdir="still-here")

    started: list[asyncio.Task[Any]] = []

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def spawning(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        clone = await envs["env"].derive_temp_clone("shared")
        started.append(
            asyncio.ensure_future(
                child(task, agents=agents, envs={"env": clone}, params=params)
            )
        )
        await asyncio.sleep(0)

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def parent(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        driver = _driver(envs["env"])
        await spawning(task, agents=agents, envs=envs, params=params)
        observed.append(list(driver.clones))
        finished.set()
        with pytest.raises(FlowCancelled):
            await started[0]
        observed.append(list(driver.clones))

    await run_fake(parent)
    assert observed == [["shared"], []]


async def test_what_a_cancelled_call_made_goes_before_the_cancel_leaves_it() -> None:
    opened = asyncio.Event()

    class Opening(FakeAgentDriver):
        async def open(self, *args: Any, **kwargs: Any) -> Any:
            said = await super().open(*args, **kwargs)
            opened.set()
            return said

    env = FakeEnvDriver()
    driver = Opening()
    running = asyncio.ensure_future(
        run_fake(
            making,
            params={"wait": True},
            agents={"agent": driver},
            envs={"env": env},
        )
    )
    await asyncio.wait_for(opened.wait(), 5)
    await asyncio.sleep(0)
    assert env.clones == ["copy"]
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert env.clones == []
    assert env.scratches == []
    assert driver.sessions[0].closed


async def test_a_copy_is_its_holder_s_alone() -> None:
    @flow(agents=Solo, envs=Place, params=Nothing)
    async def taking(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        await envs["env"].derive_temp_clone("mine")

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def holding(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> list[str]:
        env = envs["env"]
        driver = _driver(env)
        await env.derive_temp_clone("mine")
        with pytest.raises(TempCloneBusy):
            await taking(task, agents=agents, envs=envs, params=params)
        await env.destroy_temp_clone("mine")
        gone = list(driver.clones)
        await taking(task, agents=agents, envs=envs, params=params)
        return [*gone, *driver.clones]

    assert await run_fake(holding) == []


async def test_removing_is_limited_and_shielded(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class Stuck(FakeEnvDriver):
        async def destroy_scratch(self, id: str) -> None:  # noqa: A002
            await asyncio.sleep(30)

    monkeypatch.setattr(engine, "REAP", 0.05)

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def stuck(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> str:
        await envs["env"].derive_scratch("stuck")
        return "done"

    with caplog.at_level(logging.WARNING):
        assert await run_fake(stuck, envs={"env": Stuck()}) == "done"
    assert any("took longer" in one.message for one in caplog.records)


async def test_a_hook_failing_as_a_session_closes_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    heard: list[Any] = []

    async def ending(params: SessionEndHookParams) -> SessionEndHookResult:
        heard.append(params.ctx)
        raise BoomError

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def closing(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> Any:
        agents["agent"].on_session_end(ending)
        await agents["agent"].spawn(env=envs["env"])
        return ctx

    with caplog.at_level(logging.ERROR):
        ctx = await run_fake(closing)
    assert heard == [ctx]
    assert any(one.exc_info and one.exc_info[0] is BoomError for one in caplog.records)


async def test_the_run_closes_what_it_derived_and_nothing_it_was_given(
    tmp_path: Path,
) -> None:
    derived: list[FakeEnvDriver] = []

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def deriving(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        sub = await envs["env"].derive_subdir(subdir="sub")
        derived.append(_driver(sub))

    env = FakeEnvDriver()
    agent = FakeAgentDriver()
    local = FakeEnvDriver()
    await run_fake(deriving, envs={"env": env}, agents={"agent": agent}, local=local)
    assert [one.closed for one in derived] == [1]
    assert (env.closed, agent.closed, local.closed) == (0, 0, 0)


async def test_a_resumable_run_keeps_its_copies(tmp_path: Path) -> None:
    @flow(agents=Solo, envs=Place, params=Nothing, resumable=True)
    async def keeping(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        await making(task, agents=agents, envs=envs, params=params)

    env = FakeEnvDriver()
    await run_fake(keeping, envs={"env": env}, journal=tmp_path / "run.jsonl")
    assert (env.clones, env.scratches) == (["copy"], ["notes"])
    env_again = FakeEnvDriver()
    await run_fake(keeping, envs={"env": env_again})
    assert (env_again.clones, env_again.scratches) == ([], [])


async def test_a_cancel_during_a_callee_s_cleanup_still_releases_the_caller_s() -> None:
    closing = asyncio.Event()

    class SlowToClose(FakeAgentDriver):
        async def open(self, *args: Any, **kwargs: Any) -> Any:
            session = await super().open(*args, **kwargs)
            if len(self.sessions) == 2:
                real = session.close

                async def slow() -> None:
                    closing.set()
                    await asyncio.sleep(0.2)
                    await real()

                session.close = slow
            return session

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def child(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        await agents["agent"].spawn(env=envs["env"])

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def parent(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        await agents["agent"].spawn(env=envs["env"])
        await child(task, agents=agents, envs=envs, params=params)
        await asyncio.sleep(30)

    driver = SlowToClose()
    running = asyncio.ensure_future(run_fake(parent, agents={"agent": driver}))
    await asyncio.wait_for(closing.wait(), 5)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert [one.closed for one in driver.sessions] == [True, True]


async def test_the_run_releases_what_calls_it_never_waited_for_made() -> None:
    started = asyncio.Event()
    driver = FakeAgentDriver()

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def lingering(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        await agents["agent"].spawn(env=envs["env"])
        started.set()
        await asyncio.sleep(30)

    detached: list[asyncio.Future[Any]] = []

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def leaving(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        detached.append(
            asyncio.ensure_future(
                lingering(task, agents=agents, envs=envs, params=params)
            )
        )
        await started.wait()

    await run_fake(leaving, agents={"agent": driver})
    assert driver.sessions[0].closed
    detached[0].cancel()
    with pytest.raises(asyncio.CancelledError):
        await detached[0]
