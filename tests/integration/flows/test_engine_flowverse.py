"""A flowverse on disk, run end to end on fakes: every kind of ref, a real git repository.

Three flow directories call each other through `:sub`, `<flow>:<sub>`, a bare `<flow>`, and
`git+file://…@<ref>#<flow>:<sub>` -- the last a repository this test makes and commits to, so
the ref is fetched with git, pinned to the commit it stands at, and loaded from a checkout of
that commit. The run is then checked the way a person would: what it returned, what it spent
at every level, a budget running out, and a killed run picked up again from its journal.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import (
    Budget,
    CostExceeded,
    FlowLoadConflict,
    FlowNotFound,
    load,
)
from hmz.runtime.flowing import loading
from hmz.runtime.flowing.engine import load_flow, run_flow
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, run_fake
from tests.flows.kit import flowverse

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

ALPHA = """
from hmz.flows import (
    Agent, AgentCollection, CostExceeded, Env, EnvCollection, FlowParams, flow, load,
)


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    repo: Env


class Params(FlowParams):
    crash: bool = False
    remote: str = ""
    tight: bool = False


async def turn(agents, envs, prompt):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["repo"])
    return await worker.run(prompt, session=session)


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def alpha(task, *, agents, envs, params, ctx):
    said = [await turn(agents, envs, "alpha")]
    said.append(await load(":helper")(task, agents=agents, envs=envs, params=Params()))
    said.append(await load("beta")(task, agents=agents, envs=envs, params={}))
    said.append(await load("beta:second")(task, agents=agents, envs=envs, params={}))
    if params.tight:
        try:
            await load("beta:second")(
                "spend", agents=agents, envs=envs, params={}, budget=Budget(cost=0.5)
            )
        except CostExceeded:
            said.append("beta:second ran out")
    if params.crash:
        raise RuntimeError("killed")
    remote = load(params.remote)
    said.append(await remote(task, agents=agents, envs=envs, params={}))
    said.append(ctx.usage.cost)
    return said


@flow(agents=Agents, envs=Envs, params=Params, hidden=True, resumable=True)
async def helper(task, *, agents, envs, params, ctx):
    state = ctx.state
    state["runs"] = state["runs"] + 1 if "runs" in state else 1
    return f"helper run {state['runs']} resumed={ctx.resumed}"


from hmz.flows import Budget  # noqa: E402 -- used above, at call time
"""

BETA = """
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowParams, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    repo: Env


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def beta(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["repo"])
    await worker.run("beta", session=session)
    return f"beta cost {ctx.usage.cost}"


@flow(agents=Agents, envs=Envs, params=FlowParams, name="second", hidden=True)
async def second_flow(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["repo"])
    for _ in range(3):
        await worker.run("second", session=session)
    return "beta:second"
"""

GAMMA = """
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowParams, flow, load
from _gamma import VERSION


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    repo: Env


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def gamma(task, *, agents, envs, params, ctx):
    deep = await load(":deep")(task, agents=agents, envs=envs, params={})
    return f"gamma {VERSION} -> {deep}"


@flow(agents=Agents, envs=Envs, params=FlowParams, hidden=True)
async def deep(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["repo"])
    await worker.run("deep", session=session)
    return f"deep {ctx.flow.ref}"
"""


def _git(at: Path, *said: str) -> str:
    return subprocess.run(
        ["git", "-C", str(at), *said],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    ).stdout.strip()


@pytest.fixture
def remote(tmp_path: Path) -> Iterator[tuple[str, str, str]]:
    """A flowverse repository with two commits: `v1`, and the branch `main` past it.

    Yields:
      Its `file://` URL, and the two commits.
    """
    at = tmp_path / "remote"
    flowverse(
        at,
        {"gamma": {"__init__.py": GAMMA, "_gamma/__init__.py": "VERSION = 'one'\n"}},
    )
    _git(at.parent, "init", "--quiet", "--initial-branch=main", str(at))
    _git(at, "add", ".")
    _git(at, "commit", "--quiet", "-m", "one")
    _git(at, "tag", "v1")
    first = _git(at, "rev-parse", "HEAD")
    (at / "flows" / "gamma" / "_gamma" / "__init__.py").write_text(
        "VERSION = 'two'\n", encoding="utf-8"
    )
    _git(at, "commit", "--quiet", "-am", "two")
    second = _git(at, "rev-parse", "HEAD")
    yield f"file://{at}", first, second
    loading.forget()


@pytest.fixture
def verse(tmp_path: Path) -> Path:
    return flowverse(tmp_path / "verse", {"alpha": ALPHA, "beta": BETA})


def _drivers(cost: float = 0.25) -> dict[str, Any]:
    return {
        "agents": {"worker": FakeAgentDriver(cost=cost, output_tokens=10)},
        "envs": {"repo": FakeEnvDriver()},
    }


async def test_every_kind_of_ref_resolves_and_usage_rolls_up(
    verse: Path, remote: tuple[str, str, str]
) -> None:
    url, first, _ = remote
    said = await run_flow(
        load_flow(str(verse / "alpha"), caller_globals={}),
        "task",
        params={"remote": f"git+{url}@v1#gamma"},
        budget=Budget(cost=100),
        **_drivers(),
    )
    assert said == [
        "ok",
        "helper run 1 resumed=False",
        "beta cost 0.25",
        "beta:second",
        "gamma one -> deep gamma:deep",
        # alpha 1 + beta 1 + beta:second 3 + deep 1 turns, at a quarter each.
        1.5,
    ]
    pinned = loading.pinned(url, "v1")
    assert pinned.name == first
    assert (pinned / "flows" / "gamma" / "_gamma" / "__init__.py").read_text(
        encoding="utf-8"
    ) == "VERSION = 'one'\n"


async def test_a_ref_without_a_rev_is_the_default_branch(
    verse: Path, remote: tuple[str, str, str]
) -> None:
    url, _, second = remote
    said = await run_fake(
        str(verse / "alpha"), "task", params={"remote": f"git+{url}#gamma:gamma"}
    )
    assert said[4] == "gamma two -> deep gamma:deep"
    assert loading.pinned(url, None).name == second


async def test_a_commit_is_fetched_once(remote: tuple[str, str, str]) -> None:
    url, first, _ = remote
    at = loading.pinned(url, first)
    stamp = at.stat().st_mtime_ns
    assert loading.pinned(url, first) == at
    assert loading.pinned(url, "v1") == at
    assert at.stat().st_mtime_ns == stamp


async def test_two_commits_of_one_flow_conflict_in_one_run(
    verse: Path, remote: tuple[str, str, str]
) -> None:
    url, first, second = remote
    one = load(f"git+{url}@{first}#gamma")
    await run_fake(one)
    two = load(f"git+{url}@{second}#gamma")
    await run_fake(two)

    from hmz.flows import AgentCollection, EnvCollection, FlowContext, FlowParams, flow

    @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
    async def both(
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: FlowParams,
        ctx: FlowContext,
    ) -> None:
        pinned: Any = load(f"git+{url}@{first}#gamma")
        await pinned.fetched()
        later: Any = load(f"git+{url}@{second}#gamma")
        with pytest.raises(FlowLoadConflict):
            await later.fetched()

    await run_fake(both)


async def test_what_cannot_be_fetched_is_not_found(
    tmp_path: Path, remote: tuple[str, str, str]
) -> None:
    url, _, _ = remote
    with pytest.raises(FlowNotFound):
        await run_fake(f"git+file://{tmp_path}/nowhere#gamma")
    with pytest.raises(FlowNotFound):
        await run_fake(f"git+{url}@no-such-ref#gamma")
    with pytest.raises(FlowNotFound, match="no flow called 'delta'"):
        await run_fake(f"git+{url}#delta")
    remote_flow: Any = load(f"git+{url}#gamma")
    assert remote_flow.name == "gamma"
    assert remote_flow.description is None
    assert remote_flow.resumable is False
    assert remote_flow.expected_params.__name__ == "FlowParams"


async def test_a_budget_runs_out_where_it_was_set(
    verse: Path, remote: tuple[str, str, str]
) -> None:
    url, _, _ = remote
    said = await run_fake(
        str(verse / "alpha"),
        "task",
        params={"remote": f"git+{url}#gamma", "tight": True},
        budget=Budget(cost=100),
        **_drivers(),
    )
    assert said[4] == "beta:second ran out"
    with pytest.raises(CostExceeded):
        await run_fake(
            str(verse / "alpha"),
            "task",
            params={"remote": f"git+{url}#gamma"},
            budget=Budget(cost=1.0),
            **_drivers(),
        )


async def test_a_killed_run_is_picked_up_from_its_journal(
    tmp_path: Path, verse: Path, remote: tuple[str, str, str]
) -> None:
    url, _, _ = remote
    journal = tmp_path / "epic" / "journal.jsonl"
    with pytest.raises(RuntimeError, match="killed"):
        await run_fake(
            str(verse / "alpha"),
            "task",
            params={"remote": f"git+{url}#gamma", "crash": True},
            journal=journal,
        )
    # Picked up without the crash: the flow at the top picks up whatever it is called with.
    said = await run_fake(
        str(verse / "alpha"),
        "task",
        params={"remote": f"git+{url}#gamma"},
        journal=journal,
        resume=True,
    )
    assert said[1] == "helper run 2 resumed=True"
    assert said[4] == "gamma two -> deep gamma:deep"
