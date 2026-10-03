"""Flows on disk, run end to end on fakes: every kind of ref, real git repositories.

Two flow directories call each other through `:sub`, `<flow>:<sub>` and a bare `<flow>`, and
then a repository through `git+file://…[@<rev>][#<subdir>][:<sub>]` -- a repository this test
makes and commits to, so the ref is fetched with git, pinned to the commit it stands at, and
loaded from a checkout of that commit: out of the directory after the `#`, or out of the
repository's root where there is none, the way an index's manifest names where a release is.
The run is then checked the way a person would: what it returned, what it spent at every level,
a budget running out, and a killed run picked up again from its journal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

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
from tests.flows.indexes import committed, git
from tests.flows.kit import flowverse
from tests.stubs import written

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

#: A flow of a repository, which says what it keeps beside it -- `_<name>` -- and calls a
#: flow it hides. Written once per directory it is kept in, under the name of that directory.
GAMMA = """
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowParams, flow, load
from _NAME import VERSION


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
    return f"deep {VERSION}"
"""


def _gamma(at: Path, name: str, version: str) -> None:
    """Writes the flow above into a directory, beside what it keeps at one version."""
    written(at.parent, at.name, GAMMA.replace("_NAME", f"_{name}"))
    (at / f"_{name}.py").write_text(f"VERSION = '{version}'\n", encoding="utf-8")


class Remote(NamedTuple):
    """A repository of flows to name by URL.

    Attributes:
      url: Its `file://` URL.
      first: The commit `v1` names, where every flow in it says `one`.
      second: The commit `main` stands at, a commit past it, where they say `two`.
    """

    url: str
    first: str
    second: str


@pytest.fixture
def remote(tmp_path: Path) -> Iterator[Remote]:
    """A repository holding a flow in a directory, one deeper in, and one where they used to be.

    `gamma/` is a flow in a directory of its own; `pack/inner/` is one two directories down;
    and `flows/old/` is where a repository of flows kept one before a ref named the directory
    -- which `#old` used to mean, and no longer does.
    """
    at = tmp_path / "remote"
    for version, message in (("one", "one"), ("two", "two")):
        _gamma(at / "gamma", "gamma", version)
        _gamma(at / "pack" / "inner", "inner", version)
        _gamma(at / "flows" / "old", "old", version)
        committed(at, message)
        if version == "one":
            git(at, "tag", "v1")
    yield Remote(
        f"file://{at}", git(at, "rev-parse", "v1"), git(at, "rev-parse", "HEAD")
    )
    loading.forget()


@pytest.fixture
def rooted(tmp_path: Path) -> Iterator[Remote]:
    """A repository that is one flow: its entry point at the root, beside what it keeps."""
    at = tmp_path / "rooted"
    for version, message in (("one", "one"), ("two", "two")):
        _gamma(at, "rooted", version)
        committed(at, message)
        if version == "one":
            git(at, "tag", "v1")
    yield Remote(
        f"file://{at}", git(at, "rev-parse", "v1"), git(at, "rev-parse", "HEAD")
    )
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
    verse: Path, remote: Remote
) -> None:
    said = await run_flow(
        load_flow(str(verse / "alpha"), caller_globals={}),
        "task",
        params={"remote": f"git+{remote.url}@v1#gamma"},
        budget=Budget(cost=100),
        **_drivers(),
    )
    assert said == [
        "ok",
        "helper run 1 resumed=False",
        "beta cost 0.25",
        "beta:second",
        "gamma one -> deep one",
        # alpha 1 + beta 1 + beta:second 3 + deep 1 turns, at a quarter each.
        1.5,
    ]
    pinned = loading.pinned(remote.url, "v1")
    assert pinned.name == remote.first
    assert (pinned / "gamma" / "_gamma.py").read_text(
        encoding="utf-8"
    ) == "VERSION = 'one'\n"


@pytest.mark.parametrize(
    ("ref", "said"),
    [
        ("#gamma", "gamma two -> deep two"),
        ("#gamma:gamma", "gamma two -> deep two"),
        ("#gamma:deep", "deep two"),
        ("#pack/inner", "gamma two -> deep two"),
        ("#/pack/inner/", "gamma two -> deep two"),
        ("@v1#pack/inner:deep", "deep one"),
        ("@main#gamma", "gamma two -> deep two"),
    ],
)
async def test_a_ref_names_the_directory_of_the_repository_its_flow_is_in(
    remote: Remote, ref: str, said: str
) -> None:
    """After the `#`, as deep as it is; and a ref without a rev is the default branch."""
    assert await run_fake(f"git+{remote.url}{ref}", "task") == said


@pytest.mark.parametrize(
    ("ref", "said"),
    [
        ("", "gamma two -> deep two"),
        ("#", "gamma two -> deep two"),
        (":deep", "deep two"),
        ("#:deep", "deep two"),
        ("@v1", "gamma one -> deep one"),
        ("@v1:deep", "deep one"),
    ],
    ids=["bare", "empty fragment", "sub", "sub after #", "rev", "rev and sub"],
)
async def test_a_ref_with_no_directory_is_the_flow_at_the_root_of_the_repository(
    rooted: Remote, ref: str, said: str
) -> None:
    """A repository that is one flow is named by its URL alone, and a flow in it by `:<sub>`.

    Told from a port by what follows the colon: a name, where a port is followed by a path.
    """
    assert await run_fake(f"git+{rooted.url}{ref}", "task") == said


async def test_a_ref_without_a_rev_is_pinned_to_where_the_default_branch_stands(
    remote: Remote,
) -> None:
    await run_fake(f"git+{remote.url}#gamma", "task")

    assert loading.pinned(remote.url, None).name == remote.second


async def test_a_commit_is_fetched_once(remote: Remote) -> None:
    at = loading.pinned(remote.url, remote.first)
    stamp = at.stat().st_mtime_ns
    assert loading.pinned(remote.url, remote.first) == at
    assert loading.pinned(remote.url, "v1") == at
    assert at.stat().st_mtime_ns == stamp


async def test_a_commit_named_outright_is_the_one_loaded(remote: Remote) -> None:
    """Which is how a release an index lists is run without being installed."""
    assert (
        await run_fake(f"git+{remote.url}@{remote.first}#gamma", "t")
        == "gamma one -> deep one"
    )


async def test_two_commits_of_one_flow_conflict_in_one_run(remote: Remote) -> None:
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
    tmp_path: Path, remote: Remote
) -> None:
    url = remote.url
    with pytest.raises(FlowNotFound, match="could not be"):
        await run_fake(f"git+file://{tmp_path}/nowhere#gamma")
    with pytest.raises(FlowNotFound):
        await run_fake(f"git+{url}@no-such-ref#gamma")
    with pytest.raises(FlowNotFound, match="has no flow in delta"):
        await run_fake(f"git+{url}#delta")
    with pytest.raises(FlowNotFound, match="has no flow in its root"):
        await run_fake(f"git+{url}")
    with pytest.raises(FlowNotFound, match="holds no flow called 'nope'"):
        await run_fake(f"git+{url}#gamma:nope")
    remote_flow: Any = load(f"git+{url}#gamma")
    assert remote_flow.name == "gamma"
    assert remote_flow.description is None
    assert remote_flow.resumable is False
    assert remote_flow.expected_params.__name__ == "FlowParams"


async def test_a_ref_written_for_flows_under_flows_says_where_the_flow_is_now(
    remote: Remote,
) -> None:
    """`#old` used to mean `flows/old`; a ref names the directory now, so it says which."""
    with pytest.raises(
        FlowNotFound,
        match=r"has no flow in old, which holds no __init__\.py; there is one at #flows/old$",
    ):
        await run_fake(f"git+{remote.url}#old")
    # And that is the ref that runs it.
    assert await run_fake(f"git+{remote.url}#flows/old", "t") == "gamma two -> deep two"


async def test_a_budget_runs_out_where_it_was_set(verse: Path, remote: Remote) -> None:
    said = await run_fake(
        str(verse / "alpha"),
        "task",
        params={"remote": f"git+{remote.url}#gamma", "tight": True},
        budget=Budget(cost=100),
        **_drivers(),
    )
    assert said[4] == "beta:second ran out"
    with pytest.raises(CostExceeded):
        await run_fake(
            str(verse / "alpha"),
            "task",
            params={"remote": f"git+{remote.url}#gamma"},
            budget=Budget(cost=1.0),
            **_drivers(),
        )


async def test_a_killed_run_is_picked_up_from_its_journal(
    tmp_path: Path, verse: Path, remote: Remote
) -> None:
    journal = tmp_path / "epic" / "journal.jsonl"
    with pytest.raises(RuntimeError, match="killed"):
        await run_fake(
            str(verse / "alpha"),
            "task",
            params={"remote": f"git+{remote.url}#gamma", "crash": True},
            journal=journal,
        )
    # Picked up without the crash: the flow at the top picks up whatever it is called with.
    said = await run_fake(
        str(verse / "alpha"),
        "task",
        params={"remote": f"git+{remote.url}#gamma"},
        journal=journal,
        resume=True,
    )
    assert said[1] == "helper run 2 resumed=True"
    assert said[4] == "gamma two -> deep two"
