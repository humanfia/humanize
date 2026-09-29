"""Codex at a rung with a sandbox, its commands run on another machine by a real anchor.

Codex holds a sandboxed command by wrapping it in a helper -- `bwrap`, or itself as
`codex-linux-sandbox` -- and under an anchor that helper is a command like any other, sent to
the target: every command of such a turn used to come back `bwrap: setting up uid map:
Permission denied` without running. Only the real CLI can say that it runs the command
unwrapped when told its sandbox is an external one, and only a real anchor and kernel that the
fence the anchor holds on the target is what then keeps the rung.

Costs tokens and needs network access, so it only runs with ``pytest --run-agents``.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.agents import CodexAgent, CodexAgentConfig, Failed
from hmz.coganchor.fence import ALL, READ, Fence
from hmz.coganchor.linux import landlock
from hmz.coganchor.machines import AnchoredConfig
from tests.supervising import traced

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.agent,
    traced,
    pytest.mark.timeout(600),
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed"),
    pytest.mark.skipif(not landlock.available(net=False), reason="no Landlock here"),
]

#: What the agent is asked to run, as one command: a read and a write of the workdir.
ASKED = (
    "Run exactly this one shell command in your working directory and show its output: "
    "cat hello.txt; echo x > made.txt; echo WROTE=$?   Then reply DONE."
)


@pytest.mark.parametrize(
    ("permission", "local", "written"),
    [("read-only", READ, False), ("workspace-write", ALL, True)],
)
def test_a_sandboxed_rung_runs_its_commands_on_the_target_held_by_the_fence(
    tmp_path: Path, permission: str, local: str, *, written: bool
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "hello.txt").write_text("HELLO-FROM-THE-TARGET\n")
    workspace = "/coganchor-project"
    agent = CodexAgent(
        CodexAgentConfig(
            model="gpt-5.5",
            effort="low",
            permission=permission,
            fence=Fence.of(
                local=local,
                user=READ,
                system=READ,
                online=True,
                workdir=workspace,
                home=os.path.expanduser("~"),  # noqa: PTH111
            ),
            machine=AnchoredConfig(
                anchor=AnchorConfig(
                    target=f"local:{target}",
                    workspace=workspace,
                    shadow=str(tmp_path / "mirror"),
                )
            ),
        )
    )
    try:
        said = list(agent.new().stream(ASKED))
    except Failed as why:
        pytest.skip(f"codex would not take a turn on this machine: {why}")

    heard = " ".join(one.text for one in said)
    assert "bwrap" not in heard, heard
    assert "HELLO-FROM-THE-TARGET" in heard, heard
    assert (target / "made.txt").exists() is written, heard
