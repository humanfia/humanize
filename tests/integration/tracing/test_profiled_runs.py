"""A run that is profiled as well as traced, end to end.

The innovation this is here for: an agent's turns and the programs a run started are one
document at one scale, so that `what was this run doing at 09:41` has one answer. Driven as a
real run -- a flow, a workspace it starts processes in, an epic -- rather than as a profile
handed to a renderer, since what is being checked is that the two halves meet at all.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.epic import TRACES, epics, opened
from hmz.runtime.runner import Runner
from hmz.runtime.settings import Settings
from hmz.runtime.tracing.collector import collect
from hmz.runtime.tracing.profile import PROFILE, read
from tests.sampling import sampled
from tests.stubs import written

if TYPE_CHECKING:
    import pathlib

#: What the run runs: a shell running a sleep, which is two programs, and the profile has to
#: hold both of them.
#:
# : A second rather than the tenth of one it takes to say what is being checked. What reads it : is
# a sampler, taking one every :data:`hmz.runtime.tracing.profile.EVERY`, and a program that lives :
# for a handful of those is one a loaded machine can miss altogether. Twenty samples is the :
# difference between a test of the profiler and a test of the clock.
SAID = "sleep 1; echo the-session"

#: A flow that runs a program in its workspace, which is what a turn mostly is.
FLOW = f"""
from hmz.flows import AgentCollection, BashEnvMixin, EnvCollection, FlowParams, LocalEnv, flow


class Here(LocalEnv, BashEnvMixin): ...


class Envs(EnvCollection):
    here: Here


@flow(agents=AgentCollection, envs=Envs, params=FlowParams)
async def run(task, *, agents, envs, params, ctx):
    await envs["here"].exec("{SAID}")
"""


@pytest.fixture
def workspace(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A directory with the flow in it, and the agents' homes kept out of the way."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", FLOW)
    return tmp_path


@sampled
@pytest.mark.timeout(90)
def test_a_run_is_profiled_when_the_workspace_asks_for_it(
    workspace: pathlib.Path,
) -> None:
    """Off unless somebody says otherwise: it is a sampler running as long as the flow does."""
    Settings().profiles(on=True)

    Runner(workspace / "flow", budget={"cost": 1}).run("go")

    (epic,) = epics()
    ran = read(epic / PROFILE)
    assert ran, "the programs the turn ran are not in the run's profile"
    # What it ran, which is a shell running a sleep: both are programs this run started.
    # The shell is named by what it was given rather than by what it is called, one system's
    # `/bin/sh` being another's `bash`; the sleep is called the same thing everywhere.
    assert "sleep" in {one.name for one in ran}
    assert any(one.argv[-2:] == ("-c", SAID) for one in ran)


@pytest.mark.timeout(90)
def test_a_run_nobody_asked_to_profile_is_traced_and_not_profiled(
    workspace: pathlib.Path,
) -> None:
    """A sampler nobody asked for is a sampler running for the length of every run there is."""
    Runner(workspace / "flow", budget={"cost": 1}).run("go")

    (epic,) = epics()
    assert not (epic / PROFILE).exists()


@sampled
@pytest.mark.timeout(90)
def test_the_programs_and_the_sessions_are_one_document(
    workspace: pathlib.Path,
) -> None:
    """Which is the point of profiling into a trace rather than into a profile of its own."""
    Settings().profiles(on=True)
    Runner(workspace / "flow", budget={"cost": 1}).run("go")
    (epic,) = epics()

    output = epic / TRACES / "one.trace.json"
    document = collect(
        workspace,
        agents=opened(epic) or None,
        output=output,
        profile=epic / PROFILE,
    )

    assert int(document["otherData"]["programs"]) >= 2
    events = json.loads(output.read_text())["traceEvents"]
    names = [one["args"]["name"] for one in events if one["name"] == "process_name"]
    assert any(name.startswith("sleep · ") for name in names)
    # And the whole of it is one span of time: the programs are where the turns are, rather
    # than at some other point on the clock. Not a span with anything in it, though -- what
    # bounds it is a sampler, and a sampler that caught both of these programs in the one
    # sample gives an instant rather than a stretch, which is a fast machine rather than a
    # wrong answer.
    began, ended = document["otherData"]["start"], document["otherData"]["end"]
    assert began <= ended
