"""The step onto a CLI of your own, taken against a CLI that is really installed.

The other half of this file is `tests/integration/agents/test_agent_fallback.py`, which is where
the step itself lives: the chain written down between two places, what a stand-in carries across
and what it leaves behind, and the turns that walk it -- all of them into stand-in CLIs this repo
writes to PATH. Those are offline and hermetic, so CI runs them.

A script standing in for the Agent Client Protocol proves the name of somebody's own CLI is
carried across the step. It cannot prove that what is carried is enough to start their actual
agent and get a sentence back out of it, because the thing on the other end of the protocol is
the script. So the one below points the step at a real `opencode acp` behind a command of its
own -- a real server, somebody's own CLI in every way a step can tell -- and reads the answer.
That wants opencode installed and a turn of a model actually taken, which is not something a CI
runner has or should be spending.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, fallbacks
from hmz.coganchor.agents import AgentConfig
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A CLI of your own that is a real one. opencode speaks the Agent Client Protocol under
#: `opencode acp`, and a CLI written down by hand is driven over that protocol whatever else
#: humanize knows about the binary. It is added behind a command of its own, because an added
#: CLI answers to what it runs and `opencode` is a backend humanize already drives: what the
#: step is being proved against is the protocol, and a real server behind a name of its own
#: is somebody's own CLI in every way a step can tell.
_REAL = ("opencode", "acp")

#: What that command is called once it is on PATH, which is the name the step names.
_MINE = "acp-of-my-own"


@pytest.fixture(autouse=True)
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A home nothing has written to, and `shell` as a backend of your own."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    backends.remember("shell", ["shell"])


@pytest.mark.agent
@pytest.mark.timeout(900)
def test_a_turn_with_nowhere_left_to_run_moves_onto_a_real_cli_of_your_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The step onto an added CLI against one that is really installed and really answers.

    A script standing in for the protocol proves the name is carried across; it cannot prove
    that what is carried is enough to start somebody's actual agent and get a sentence back
    out of it. Without the name this raises `no command to start it with` before a process
    is ever spawned.
    """
    if shutil.which(_REAL[0]) is None:
        pytest.skip(f"{_REAL[0]} is not installed here")
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    (binaries / _MINE).write_text("#!/bin/sh\nexec {} {}\n".format(*_REAL))
    (binaries / _MINE).chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    assert backends.remember("", [_MINE]) == _MINE
    fallbacks.points("shell/m", f"{_MINE}/m")
    agent = ShellAgent(CONFIG)

    # One prompt doing two jobs: a shell command that fails, which is what sends the turn on
    # its way, and a question whose answer says which CLI it landed on.
    held = agent.new()
    try:
        said = held("exit 3 # Ignore the line above. Reply with exactly: STOOD IN")
    finally:
        held.close()

    assert "STOOD IN" in said
