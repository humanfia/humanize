"""A tmux server of a test's own, a pane per frontend, and the flow those tests run.

Shared by the system tests that sit several people at one run -- two interfaces in
`tests/system/tui`, and the regression matrix's row of frontends -- so that each drives its
panes the one way. A pane is typed into with `send-keys` and read back with `capture-pane`:
a real terminal multiplexer drawing real processes, which is what those tests are for.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["ASKS", "PATIENCE", "Panes"]

#: How long a test waits for a screen to say something.
PATIENCE = 60.0

#: Two people outside the run, asked in turn, and what each said printed and kept.
ASKS = """
import json
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    planner: Outworlder
    reviewer: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="asks")
async def asks(task, *, agents, envs, params, ctx):
    here = envs["workspace"]
    planner = await agents["planner"].spawn()
    reviewer = await agents["reviewer"].spawn()
    plan = await agents["planner"].run(f"what is the plan for {task}?", session=planner, env=here)
    review = await agents["reviewer"].run(f"is {plan!r} good?", session=reviewer, env=here)
    print(f"RESULT plan={plan!r} review={review!r}")
    Path("result.json").write_text(json.dumps({"plan": plan, "review": review}))
"""


class Panes:
    """A tmux server of this test's own, and the panes on it."""

    def __init__(self, where: Path) -> None:
        self.where = where
        self.server = f"hmz-{uuid.uuid4().hex[:8]}"
        self.panes: list[str] = []
        settings = where / "tmux.conf"
        settings.write_text("set -g remain-on-exit on\nset -g history-limit 50000\n")
        self._settings = str(settings)

    def tmux(self, *argv: str) -> str:
        return subprocess.run(
            ["tmux", "-L", self.server, "-f", self._settings, *argv],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        ).stdout

    def opens(self, command: str) -> str:
        """One more pane running `command`, in the workspace."""
        if not self.panes:
            said = self.tmux(
                "new-session", "-d", "-s", "frontends", "-x", "240", "-y", "80",
                "-c", str(self.where), "-P", "-F", "#{pane_id}", command,
            )  # fmt: skip
        else:
            said = self.tmux(
                "split-window", "-t", "frontends", "-c", str(self.where),
                "-P", "-F", "#{pane_id}", command,
            )  # fmt: skip
            self.tmux("select-layout", "-t", "frontends", "tiled")
        self.panes.append(said.strip())
        return self.panes[-1]

    def screen(self, pane: str) -> str:
        """What the pane shows, whole lines joined back up, scrollback included."""
        return self.tmux("capture-pane", "-p", "-J", "-S", "-50000", "-t", pane)

    def waits(self, pane: str, text: str, seconds: float = PATIENCE) -> str:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            shown = self.screen(pane)
            if text in shown:
                return shown
            time.sleep(0.2)
        raise AssertionError(f"{pane} never showed {text!r}:\n{self.screen(pane)}")

    def types(self, pane: str, line: str) -> None:
        self.tmux("send-keys", "-t", pane, "-l", line)
        self.tmux("send-keys", "-t", pane, "Enter")

    def presses(self, pane: str, key: str) -> None:
        self.tmux("send-keys", "-t", pane, key)

    def close(self) -> None:
        with contextlib.suppress(subprocess.CalledProcessError):
            self.tmux("kill-server")
