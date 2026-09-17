"""A real `claude`, connecting to a flow's own tool server and listing what it found.

The other half of this file is `tests/integration/agents/test_tools.py`: the protocol answered a
message at a time, the socket a toolbox serves it on, the bridge driven from a client script
written here, and each backend's command line read back off a stand-in CLI on PATH. All of that
is this process and scripts this repo wrote, so CI runs it.

What is left is the one claim none of that can make. The inline `--mcp-config` humanize writes is
a shape *Claude* has to agree with, and a stand-in agrees with whatever it is handed -- so a flag
that quietly stopped being read would look exactly like a flag that works. Only the real CLI can
say otherwise, and a CI runner has not got one. No model is asked anything: the key is
deliberately wrong and the turn fails at the door, so this spends nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, Field

from hmz.coganchor.agents import Tool, Toolbox

if TYPE_CHECKING:
    from pathlib import Path


class Asked(BaseModel):
    """What the tool under test is called with."""

    task: str = Field(description="what to have it do")
    times: int = 1


def _tool(seen: list[Asked]) -> Tool:
    """A callback that writes down what it was called with and answers."""

    def called(said: Asked) -> str:
        seen.append(said)
        return f"did {said.task} {said.times}x"

    return Tool(
        name="delegate",
        about="hand a task to another flow and wait for what it comes to",
        takes=Asked,
        call=called,
    )


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_a_real_claude_connects_to_the_flow_and_lists_its_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole road against the real CLI: it connects, and our callback is on its list.

    No model is asked anything -- the key is deliberately wrong, and the turn fails at the
    door -- so this costs nothing. What it pins is the half a stand-in cannot: that the
    inline `--mcp-config` humanize writes is the shape Claude actually reads, and that what
    it starts talks to this process.
    """
    import shutil

    if shutil.which("claude") is None:
        pytest.skip("claude is not installed here")
    monkeypatch.chdir(tmp_path)
    box = Toolbox()
    box.offers(1, [_tool([])])
    try:
        done = subprocess.run(
            [
                "claude",
                "--print",
                "--output-format",
                "stream-json",
                "--verbose",
                "--mcp-config",
                json.dumps(box.config()),
                "--model",
                "claude-opus-5",
                "say ok",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            # A home of its own and a key that is not one: nothing of this machine's account
            # is read, and no turn of any model is taken.
            env=dict(os.environ)
            | {"ANTHROPIC_API_KEY": "not-a-key", "HOME": str(tmp_path)},
            check=False,
        )
    finally:
        box.close()

    said = json.loads((done.stdout or "{}").splitlines()[0])
    assert said.get("mcp_servers") == [{"name": "humanize", "status": "connected"}]
    assert "mcp__humanize__delegate" in said.get("tools", [])
