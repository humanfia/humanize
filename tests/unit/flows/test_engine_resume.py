"""Picking a run back up: the journal a resumable run writes, and what a resumed run reads.

The flow at the top of a resumed run picks up unconditionally. A call under a call that
picked up picks up the earlier call made with the same flow, task, agents, environments and
params -- the first nobody has claimed yet, so repeated and concurrent identical calls each
get one of their own -- and starts afresh otherwise. What it picks up is its state, and
`ctx.resumed`.
"""

from __future__ import annotations

import asyncio
import datetime
import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    Env,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    StateNotSerializable,
    TemporaryClonedDirEnvMixin,
    flow,
)
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, run_fake

if TYPE_CHECKING:
    from pathlib import Path


class Solo(AgentCollection):
    agent: Agent


class Clonable(Env, TemporaryClonedDirEnvMixin): ...


class Place(EnvCollection):
    env: Clonable


class Step(FlowParams):
    n: int = 0
    fail_at: int = -1


class CrashError(Exception):
    pass


def _records(journal: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in journal.read_bytes().splitlines()]


@flow(agents=Solo, envs=Place, params=Step, resumable=True)
async def leaf(
    task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
) -> dict[str, Any]:
    state = ctx.state
    assert state is not None
    runs = state["runs"] + 1 if "runs" in state else 1
    state["runs"] = runs
    return {"n": params.n, "runs": runs, "resumed": ctx.resumed}


@flow(agents=Solo, envs=Place, params=Step, resumable=True)
async def root(
    task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
) -> list[dict[str, Any]]:
    state = ctx.state
    assert state is not None
    said: list[dict[str, Any]] = []
    for n in range(3):
        if n == params.fail_at:
            raise CrashError(n)
        said.append(await leaf(task, agents=agents, envs=envs, params=Step(n=n)))
    state["done"] = True
    return said


async def _run(flow_: Any, journal: Path, *, resume: bool, **said: Any) -> Any:
    return await run_fake(flow_, "task", journal=journal, resume=resume, **said)


async def test_a_resumed_run_picks_up_the_calls_it_made(tmp_path: Path) -> None:
    journal = tmp_path / "run.jsonl"
    with pytest.raises(CrashError):
        await _run(root, journal, resume=False, params={"fail_at": 2})
    said = await _run(root, journal, resume=True)
    assert said == [
        {"n": 0, "runs": 2, "resumed": True},
        {"n": 1, "runs": 2, "resumed": True},
        {"n": 2, "runs": 1, "resumed": False},
    ]


async def test_a_run_that_is_not_resumed_starts_over(tmp_path: Path) -> None:
    journal = tmp_path / "run.jsonl"
    await _run(root, journal, resume=False)
    said = await _run(root, journal, resume=False)
    assert [one["runs"] for one in said] == [1, 1, 1]
    assert not any(one["resumed"] for one in said)


async def test_a_run_resumed_with_no_journal_starts_over(tmp_path: Path) -> None:
    said = await _run(root, tmp_path / "nothing.jsonl", resume=True)
    assert [one["runs"] for one in said] == [1, 1, 1]


async def test_a_call_made_differently_starts_afresh(tmp_path: Path) -> None:
    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def varying(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> list[bool]:
        said: list[bool] = []
        for n in range(3):
            done = await leaf(
                f"task {n + params.n}", agents=agents, envs=envs, params=Step(n=n)
            )
            said.append(done["resumed"])
        return said

    journal = tmp_path / "run.jsonl"
    assert await _run(varying, journal, resume=False) == [False] * 3
    # One task moves along: the first call is made with what the second was, and so on.
    assert await _run(varying, journal, resume=True, params={"n": 1}) == [
        False,
        False,
        False,
    ]
    journal_again = tmp_path / "again.jsonl"
    await _run(varying, journal_again, resume=False)
    other = FakeAgentDriver(model="another")
    assert (
        await _run(varying, journal_again, resume=True, agents={"agent": other})
        == [False] * 3
    )
    assert await _run(varying, journal_again, resume=True) == [True] * 3


async def test_identical_calls_pick_up_one_earlier_call_apiece(tmp_path: Path) -> None:
    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def mark(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> tuple[bool, list[int]]:
        state = ctx.state
        assert state is not None
        try:
            seen: list[int] = state["seen"]
        except KeyError:
            seen = []
        state["seen"] = [*seen, params.n]
        return ctx.resumed, state["seen"]

    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def gathering(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> list[tuple[bool, list[int]]]:
        same = Step(n=params.n)
        concurrent = await asyncio.gather(
            *(mark(task, agents=agents, envs=envs, params=same) for _ in range(3))
        )
        in_a_row = [
            await mark(task, agents=agents, envs=envs, params=same) for _ in range(2)
        ]
        return [*concurrent, *in_a_row]

    journal = tmp_path / "run.jsonl"
    first = await _run(gathering, journal, resume=False, params={"n": 7})
    assert first == [(False, [7])] * 5
    second = await _run(gathering, journal, resume=True, params={"n": 7})
    assert second == [(True, [7, 7])] * 5
    third = await _run(gathering, journal, resume=True, params={"n": 7})
    assert third == [(True, [7, 7, 7])] * 5
    calls = [one for one in _records(journal) if one["t"] == "call"]
    assert sorted(one["seq"] for one in calls if one["parent"] != 0) == [0, 1, 2, 3, 4]


async def test_resumption_passes_through_a_flow_that_is_not_resumable(
    tmp_path: Path,
) -> None:
    @flow(agents=Solo, envs=Place, params=Step)
    async def middle(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> tuple[Any, bool, dict[str, Any]]:
        below = await leaf(task, agents=agents, envs=envs, params=params)
        return ctx.state, ctx.resumed, below

    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def top(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> tuple[Any, bool, dict[str, Any]]:
        return await middle(task, agents=agents, envs=envs, params=params)

    journal = tmp_path / "run.jsonl"
    assert await _run(top, journal, resume=False) == (
        None,
        False,
        {"n": 0, "runs": 1, "resumed": False},
    )
    assert await _run(top, journal, resume=True) == (
        None,
        True,
        {"n": 0, "runs": 2, "resumed": True},
    )


async def test_the_top_picks_up_whatever_it_was_called_with(tmp_path: Path) -> None:
    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def counting(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> tuple[bool, int]:
        state = ctx.state
        assert state is not None
        state["n"] = state["n"] + 1 if "n" in state else 1
        return ctx.resumed, state["n"]

    journal = tmp_path / "run.jsonl"
    assert await run_fake(counting, "one", journal=journal) == (False, 1)
    assert await run_fake(
        counting, "another", journal=journal, resume=True, params={"n": 3}
    ) == (True, 2)


async def test_an_environment_is_matched_by_how_it_was_derived(tmp_path: Path) -> None:
    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def cloning(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> tuple[str, dict[str, Any]]:
        env = envs["env"]
        for n in range(params.n):
            await env.derive_temp_clone(f"spare-{n}")
        clone = await env.derive_temp_clone("work")
        said = await leaf(task, agents=agents, envs={"env": clone}, params=Step())
        return str(clone.workdir), said

    journal = tmp_path / "run.jsonl"
    first, before = await _run(cloning, journal, resume=False)
    second, after = await _run(cloning, journal, resume=True, params={"n": 2})
    assert first != second
    assert (before["resumed"], after["resumed"]) == (False, True)


class Copies(Env, TemporaryClonedDirEnvMixin, FilesEnvMixin): ...


class CopyPlace(EnvCollection):
    env: Copies


async def test_a_run_resumed_on_the_same_fake_takes_its_copy_again(
    tmp_path: Path,
) -> None:
    @flow(agents=Solo, envs=CopyPlace, params=Step, resumable=True)
    async def copying(
        task: str, *, agents: Solo, envs: CopyPlace, params: Step, ctx: FlowContext
    ) -> tuple[str, bytes]:
        clone = await envs["env"].derive_temp_clone("work")
        if params.fail_at >= 0:
            await clone.write("notes.txt", b"left off here")
            raise CrashError(str(clone.workdir))
        return str(clone.workdir), await clone.read("notes.txt")

    env = FakeEnvDriver({"notes.txt": "fresh"})
    journal = tmp_path / "run.jsonl"
    with pytest.raises(CrashError) as crashed:
        await _run(
            copying, journal, resume=False, envs={"env": env}, params={"fail_at": 0}
        )
    assert env.clones == ["work"]
    workdir, notes = await _run(copying, journal, resume=True, envs={"env": env})
    assert (workdir, notes) == (str(crashed.value), b"left off here")
    assert env.clones == ["work"]


# ---------------------------------------------------------------------------- the file


async def test_the_journal_holds_every_record_a_run_makes(tmp_path: Path) -> None:
    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def recorded(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> None:
        state = ctx.state
        assert state is not None
        state["a"] = {"deep": [1, 2.5, None, True, "x"]}
        state["b"] = 1
        del state["b"]
        agent = agents["agent"]
        await agent.spawn(env=envs["env"])
        await envs["env"].derive_temp_clone("kept")
        await leaf(task, agents=agents, envs=envs, params=params)

    journal = tmp_path / "run.jsonl"
    env = FakeEnvDriver()
    await _run(recorded, journal, resume=False, envs={"env": env})
    records = _records(journal)
    assert records[0] == {"t": "journal", "v": 1}
    kinds = [one["t"] for one in records[1:]]
    assert kinds.count("call") == 2
    assert kinds.count("end") == 2
    assert {"set", "del", "session", "tmp"} <= set(kinds)
    top, child = (one for one in records if one["t"] == "call")
    assert top["parent"] == 0
    assert child["parent"] == top["id"]
    assert child["ref"].endswith(":leaf")
    assert len(child["digest"]) == 32
    sets = [one for one in records if one["t"] == "set" and one["id"] == top["id"]]
    assert sets[0]["value"] == {"deep": [1, 2.5, None, True, "x"]}
    tmp = next(one for one in records if one["t"] == "tmp")
    assert (tmp["kind"], tmp["name"], tmp["env"]) == ("temp_clone", "kept", "env")
    assert tmp["chain"].endswith("#temp_clone(kept)")
    assert env.clones == ["kept"], "a resumable run removed a temporary copy"
    ends = [one for one in records if one["t"] == "end"]
    assert all(one["ok"] for one in ends)


async def test_a_session_is_written_down_once_its_cli_has_named_it(
    tmp_path: Path,
) -> None:
    """A CLI names a session as its first turn goes: the record waits for the name."""
    driver = FakeAgentDriver(names_late=True)
    journal = tmp_path / "run.jsonl"
    unnamed: list[bool] = []

    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def named(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        idle = await agent.spawn(env=envs["env"])
        unnamed.append(driver.sessions[0].id is None)
        # Twice, and through an agent derived from the one that opened it: written down once.
        await agent.run(task, session=session)
        await agent.derive().run(task, session=session)
        del idle

    await _run(named, journal, resume=False, agents={"agent": driver})
    used, idle = driver.sessions
    assert unnamed == [True]
    assert used.id is not None
    assert idle.id is None
    records = _records(journal)
    (top,) = (one for one in records if one["t"] == "call")
    sessions = [one for one in records if one["t"] == "session"]
    # One record, for the session that took a turn, against the call that opened it, and
    # none for the one that never did: there is no conversation of it to find.
    assert sessions == [
        {
            "t": "session",
            "id": top["id"],
            "role": "agent",
            "harness": "claude",
            "model": "fake",
            "session": used.id,
        }
    ]


async def test_a_state_write_is_on_disk_before_the_call_goes_on(tmp_path: Path) -> None:
    journal = tmp_path / "run.jsonl"
    seen: list[list[dict[str, Any]]] = []

    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def writing(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> None:
        state = ctx.state
        assert state is not None
        state["now"] = 1
        seen.append(_records(journal))

    await _run(writing, journal, resume=False)
    on_disk = seen[0]
    assert [one["t"] for one in on_disk] == ["journal", "call", "set"]


async def test_a_resumed_journal_is_compacted(tmp_path: Path) -> None:
    journal = tmp_path / "run.jsonl"
    seen: list[list[dict[str, Any]]] = []

    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def churning(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> int:
        state = ctx.state
        assert state is not None
        seen.append(_records(journal))
        if params.n:
            return state["n"]
        for n in range(50):
            state["n"] = n
            state[f"gone-{n}"] = n
            del state[f"gone-{n}"]
        return state["n"]

    await _run(churning, journal, resume=False)
    long = len(_records(journal))
    with journal.open("ab") as appending:
        appending.write(b'{"t": "set", "id": 1, "key": "half')
    assert await _run(churning, journal, resume=True, params={"n": 1}) == 49
    compacted = seen[-1]
    assert [one["t"] for one in compacted] == ["journal", "call", "set", "end"]
    assert compacted[2]["value"] == 49
    assert len(compacted) < long
    assert await _run(churning, journal, resume=True, params={"n": 1}) == 49


async def test_a_flow_that_is_not_resumable_writes_no_journal(tmp_path: Path) -> None:
    @flow(agents=Solo, envs=Place, params=Step)
    async def plain(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> Any:
        return ctx.state

    journal = tmp_path / "run.jsonl"
    assert await _run(plain, journal, resume=False) is None
    assert not journal.exists()


async def test_a_resumable_flow_with_no_journal_keeps_its_state_in_memory() -> None:
    said = await run_fake(root, "task")
    assert [one["runs"] for one in said] == [1, 1, 1]


# ------------------------------------------------------------------------- the state


class Weird:
    pass


@pytest.mark.parametrize(
    "value",
    [
        {1, 2},
        Weird(),
        datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        b"bytes",
        {"k": object()},
    ],
    ids=["set", "object", "datetime", "bytes", "nested object"],
)
async def test_state_refuses_what_json_cannot_hold(value: Any, tmp_path: Path) -> None:
    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def keeping(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> bool:
        state = ctx.state
        assert state is not None
        with pytest.raises(StateNotSerializable) as raised:
            state["x"] = value
        assert isinstance(raised.value, TypeError)
        return "x" in state

    assert await _run(keeping, tmp_path / "run.jsonl", resume=False) is False


async def test_state_keeps_what_json_gives_back(tmp_path: Path) -> None:
    circular: list[Any] = []
    circular.append(circular)

    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def keeping(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> list[Any]:
        state = ctx.state
        assert state is not None
        written = [1, 2]
        state["list"] = written
        written.append(3)
        state["tuple"] = (1, "a")
        state["keys"] = {1: "one"}
        state["inf"] = float("inf")
        with pytest.raises(StateNotSerializable):
            state["circular"] = circular
        with pytest.raises(StateNotSerializable):
            state[3] = "x"  # pyright: ignore[reportArgumentType]
        with pytest.raises(KeyError):
            _ = state["missing"]
        with pytest.raises(KeyError):
            del state["missing"]
        impl: Any = state
        return [
            state["list"],
            state["tuple"],
            state["keys"],
            state["inf"],
            len(impl),
            sorted(impl),
            impl.get("missing", "default"),
            repr(impl).startswith("FlowState("),
        ]

    journal = tmp_path / "run.jsonl"
    fresh = await _run(keeping, journal, resume=False)
    assert fresh == [
        [1, 2],
        [1, "a"],
        {"1": "one"},
        float("inf"),
        4,
        ["inf", "keys", "list", "tuple"],
        "default",
        True,
    ]
    resumed = await _run(keeping, journal, resume=True)
    assert resumed == fresh


async def test_a_flow_that_failed_is_written_down_as_failed(tmp_path: Path) -> None:
    journal = tmp_path / "run.jsonl"
    with pytest.raises(CrashError):
        await _run(root, journal, resume=False, params={"fail_at": 0})
    ends = [one for one in _records(journal) if one["t"] == "end"]
    assert ends == [{"t": "end", "id": 1, "ok": False}]


async def test_a_journal_is_written_in_batches_not_per_call(tmp_path: Path) -> None:
    @flow(agents=Solo, envs=Place, params=Step, resumable=True)
    async def many(
        task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
    ) -> None:
        for n in range(200):
            await leaf_plain(task, agents=agents, envs=envs, params=Step(n=n))

    journal = tmp_path / "run.jsonl"
    from hmz.runtime.flowing import journaling

    opened: list[Any] = []
    real = journaling.Journal.opened

    def spying(*args: Any, **kwargs: Any) -> Any:
        said = real(*args, **kwargs)
        opened.append(said[0])
        return said

    journaling.Journal.opened = spying
    try:
        await _run(many, journal, resume=False, budget=Budget(cost=1))
    finally:
        journaling.Journal.opened = real
    written = opened[0]
    assert written.records == 2 * 201
    assert written.writes <= 5


@flow(agents=Solo, envs=Place, params=Step)
async def leaf_plain(
    task: str, *, agents: Solo, envs: Place, params: Step, ctx: FlowContext
) -> None:
    del task, agents, envs, params, ctx
