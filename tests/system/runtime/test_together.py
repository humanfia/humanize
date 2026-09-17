"""The layers composed on a machine that can supervise a turn, which is the half CI cannot run.

The other half is `tests/integration/runtime/test_together.py`: one flow, two agents, a fake
`claude` on PATH, and the trace gathered back off what they opened. Everything below runs that
same fake CLI through a layer the plain one does not reach -- an anchor, which puts the work on
another machine, and a provider, which answers the paths a turn reads with somebody else's.
Both are a seccomp filter and a ptrace supervisor around a real process, and a container
without `CAP_SYS_PTRACE` has every module here and can supervise nothing, so these are a tier
of their own rather than a skip inside a file CI runs.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.coganchor.machines import AnchoredConfig
from hmz.runtime import tracing
from tests.coganchor.fixtures import VIRTUAL_WORKSPACE
from tests.stubs import written
from tests.supervising import traced
from tests.tracing.fixtures import labels

if TYPE_CHECKING:
    from pathlib import Path

#: The fake `claude`, answering with whichever credentials it found rather than with "done":
#: what an agent run under a provider must come back with is that provider's own account.
WHOEVER = """
import json, pathlib, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
taken = flags.get("--session-id") or flags["--resume"]
print(json.dumps({"type": "system", "session_id": taken}), flush=True)
where = pathlib.Path.home() / ".claude" / ".credentials.json"
for line in sys.stdin:
    said = where.read_text().strip() if where.exists() else "nobody"
    print(json.dumps({"type": "result", "result": said}), flush=True)
"""


@traced
@pytest.mark.timeout(180)
def test_an_anchored_flow_leaves_its_work_there_and_its_trajectory_here(
    sandbox: Path, tmp_path: Path
) -> None:
    """An anchor moves the work, not the conversation, so the flow reads back the same way.

    The agent runs on this machine whatever the anchor says, keeping its credentials and the
    transcript a trace is built from; the file it writes is checked on the target, where the
    workspace it was given only ever existed.
    """
    target, mirror = tmp_path / "target", tmp_path / "mirror"
    target.mkdir()
    mirror.mkdir()
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="claude-opus-4-8",
            effort="high",
            machine=AnchoredConfig(
                anchor=AnchorConfig(
                    target=f"local:{target}",
                    workspace=VIRTUAL_WORKSPACE,
                    shadow=str(mirror),
                )
            ),
        ),
        name="actor",
    )
    session = agent.new()

    assert session("do the task") == "done"  # the turn is the flow's, as it always was
    # A second turn resumes the conversation and reaches the target through the mirror the
    # first one left behind, which is the shape every flow humanize comes with runs in.
    assert session("keep going") == "done"

    assert (target / "landed.txt").read_text() == session.id * 2
    assert not (
        sandbox / "landed.txt"
    ).exists()  # nothing landed where the flow was started

    document = tracing.collect(sessions=session.id, agents={agent.id: agent.opened})

    assert document["otherData"]["sessions"] == "1"
    assert labels(document, "process_name") == {
        "actor · claude-opus-4-8 · high · 1 sessions"
    }


@traced
@pytest.mark.timeout(180)
def test_one_flow_runs_two_agents_of_one_cli_as_two_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole errand of a provider, through every layer at once.

    One flow, one CLI, two agents, two accounts: each turn reads the credentials of the
    provider its agent was configured with, neither reads the other's, and neither reads the
    ones this machine is signed in with -- which is what a flame chase between a subscription
    and somebody's gateway comes down to.
    """
    import json as reading

    from hmz.coganchor import providers
    from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
    from hmz.runtime.runner import Runner

    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{WHOEVER}")
    fake.chmod(0o755)
    house = tmp_path / "home"
    (house / ".claude").mkdir(parents=True)
    (house / ".claude" / ".credentials.json").write_text('"this machine"')
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(house))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.chdir(workspace)
    for named in ("subscription", "gateway"):
        provider = providers.add("claude", named, way="login")
        (provider.at / "home" / ".credentials.json").write_text(f'"{named}"')

    written(
        workspace,
        "flow",
        """
import json
from pathlib import Path

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    Path("said.json").write_text(json.dumps([agent(task) for agent in agents]))
""",
    )
    agents = [
        ClaudeCodeAgent(
            ClaudeCodeAgentConfig(model="m", effort="high", provider=named), name=named
        )
        for named in ("subscription", "gateway")
    ]

    Runner(workspace / "flow", agents).run("who are you")

    assert reading.loads((workspace / "said.json").read_text()) == [
        '"subscription"',
        '"gateway"',
    ]
    # And what this machine is signed in as was neither read nor written.
    assert (house / ".claude" / ".credentials.json").read_text() == '"this machine"'
