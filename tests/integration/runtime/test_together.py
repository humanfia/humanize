"""The layers composed, which is the only place their fit is checked.

tracing imports none of the others and none imports it: a flow is what joins them, by handing
tracing what the agents report -- so nothing but this checks that an agent's `opened` really
names the sessions tracing files under that agent. An agent does read coganchor's settings, but only
as settings; that they still describe a session it can drive is checked here too.

The flow is run for real against a fake `claude` that records a transcript where the real one
would, which is the whole path: the id an agent pins, the transcript that id names, the agent
that says it opened it. A stand-in CLI on PATH and a process of its own is all it asks for,
which is why this half is the one CI runs. The other half --
`tests/system/runtime/test_together.py` -- puts that same flow through an anchor and through
two accounts of one CLI, and both of those are supervised turns: a seccomp filter and a ptrace
supervisor, which CI cannot be relied on to hand over.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.runtime import tracing
from tests.tracing.fixtures import labels

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")


@pytest.fixture
def flow(sandbox: Path) -> tuple[Path, dict[str, list[str]]]:
    """Runs a flow's two agents for real, and reports its workspace and what each opened."""
    # The rlar shape, at one model and one effort: what nothing in a transcript tells apart.
    actor = ClaudeCodeAgent(CONFIG, name="actor")
    reviewer = ClaudeCodeAgent(CONFIG, name="reviewer")
    actor.new()("do the task")
    reviewer.new()("review the work")
    return sandbox, {agent.id: agent.opened for agent in (actor, reviewer)}


def test_a_flow_is_traced_as_the_agents_it_ran(
    flow: tuple[Path, dict[str, list[str]]],
) -> None:
    workspace, agents = flow

    document = tracing.collect(workspace, agents=agents)

    assert document["otherData"]["sessions"] == "2"
    assert labels(document, "process_name") == {
        "actor · claude-opus-4-8 · high · 1 sessions",
        "reviewer · claude-opus-4-8 · high · 1 sessions",
    }
