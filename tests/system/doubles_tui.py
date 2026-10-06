"""The interface as somebody at a terminal has it: keys in, the screen read back.

`Screen` drives a `Humanize` opened with Textual's `run_test` -- the real interface on the
real runtime, drawn into a headless terminal of a fixed size -- and reads back what that
terminal shows as plain text, laid out by row and column. Nothing of the interface's own is
read: only what it drew.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from hmz.runtime import Hmz
from tests.system.real import needs

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from hmz.tui import Humanize

__all__ = ["CHEAPEST", "TASK", "Screen", "cheapest"]

#: What the agent is asked to do in the sample project.
TASK = "implement median and mode so the tests pass"

#: The CLIs a run may take its turns on, each with what its cheapest model's name holds.
CHEAPEST = (("claude", "haiku"), ("codex", "luna"))

#: How long a screen is waited on for something that is not a turn.
PATIENCE = 60.0

#: One run of text Rich drew into the screenshot: its column, its width and its row.
_DRAWN = re.compile(
    r'<text [^>]*?x="([\d.]+)"[^>]*?textLength="([\d.]+)"'
    r'[^>]*?clip-path="url\(#[^)]*-line-(\d+)\)"[^>]*>(.*?)</text>',
    re.DOTALL,
)


def _signed_in(cli: str, program: str) -> bool:
    """Whether `cli` says it is signed in, asked the way a person would ask it."""
    argv = {
        "claude": [program, "auth", "status"],
        "codex": [program, "login", "status"],
    }
    try:
        said = subprocess.run(
            argv[cli], capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if cli == "claude":
        try:
            return bool(json.loads(said.stdout).get("loggedIn"))
        except ValueError:
            return False
    return said.returncode == 0


def cheapest() -> tuple[str, str]:
    """The first CLI here that is installed and signed in, and its cheapest model's name.

    Asked what it runs before the interface opens, as a machine that has used it has been:
    the agent sheet offers efforts from what was known as `/flow` opened.

    Skips the test where there is none.
    """
    for cli, model in CHEAPEST:
        try:
            program = needs(cli)
        except pytest.skip.Exception:
            continue
        if _signed_in(cli, program):
            Hmz().accounts.ask(cli)
            return cli, model
    pytest.skip(
        "none of "
        + ", ".join(cli for cli, _ in CHEAPEST)
        + " is installed and signed in"
    )


class Screen:
    """One interface, typed at and read back."""

    def __init__(self, app: Humanize, pilot: Pilot[None]) -> None:
        self.app = app
        self.pilot = pilot

    def text(self) -> str:
        """What the terminal shows, a line per row."""
        rows: dict[int, list[tuple[int, str]]] = {}
        for x, width, row, said in _DRAWN.findall(self.app.export_screenshot()):
            text = html.unescape(said).replace("\xa0", " ")
            if text:
                column = round(float(x) / (float(width) / len(text)))
                rows.setdefault(int(row), []).append((column, text))
        lines: list[str] = []
        for row in range(max(rows, default=-1) + 1):
            line = ""
            for column, text in sorted(rows.get(row, [])):
                line = line.ljust(column) + text
            lines.append(line.rstrip())
        return "\n".join(lines)

    async def press(self, *keys: str) -> None:
        """Presses each key in turn, letting the screen settle after each."""
        for key in keys:
            await self.pilot.press(key)
            await self.pilot.pause(0.1)

    async def types(self, line: str) -> None:
        """Types a line, without sending it."""
        await self.pilot.press(*line)
        await self.pilot.pause(0.1)

    async def click(self, selector: str) -> None:
        """Clicks what `selector` names on the screen in front."""
        await self.pilot.click(selector)
        await self.pilot.pause(0.1)

    async def waits(self, *texts: str, seconds: float = PATIENCE) -> str:
        """Waits until the screen shows every one of `texts`, and answers what it showed."""
        deadline = time.monotonic() + seconds
        while True:
            shown = self.text()
            if all(text in shown for text in texts):
                return shown
            if time.monotonic() > deadline:
                raise AssertionError(f"the screen never showed {texts!r}:\n{shown}")
            await asyncio.sleep(0.5)
            await self.pilot.pause()

    async def chooses(self, row: str, choice: str) -> None:
        """Picks `choice` in the list dropped under `row`, which opens on the one in force."""
        shown = await self.waits(f"╭─ {row} ")
        lines = shown.splitlines()
        top = next(n for n, line in enumerate(lines) if f"╭─ {row} " in line)
        column = lines[top].index("╭")
        offered: list[str] = []
        for line in lines[top + 1 :]:
            inside = line[column:]
            if not inside.startswith("│"):
                break
            offered.append(inside.strip("│ "))
        names = [one.removesuffix("✔").strip() for one in offered]
        current = next((n for n, one in enumerate(offered) if one.endswith("✔")), 0)
        steps = names.index(choice) - current
        await self.press(*["down" if steps > 0 else "up"] * abs(steps), "enter")

    async def sets_up(self, flow: str, cli: str, model: str, budget: str) -> None:
        """Chooses `flow` in `/flow`, its one role `cli` on `model` at low effort, and saves.

        Args:
          flow: The builtin flow, by name.
          cli: The CLI its agent runs on.
          model: What the model's name holds, searched for in the model picker.
          budget: How long a run may take, as the budget page takes it.
        """
        await self.types("/flow")
        await self.press("enter")
        await self.waits("/flow", "Installed", flow)
        # Searched for, and then set up: its roles come first.
        await self.press("slash")
        await self.types(flow)
        await self.press("enter", "enter")
        await self.waits("Configure each role", "budget")

        # The role, then its CLI, its model and its effort, each from its own list.
        await self.press("enter")
        await self.waits("Set up agent", "coding agent CLI to use")
        await self.press("enter")
        await self.waits("Select a coding agent")
        await self.press("slash")
        await self.types(cli)
        await self.press("enter", "enter")
        await self.waits("Set up agent")
        await self.press("down", "down", "enter")
        await self.waits(f"Select a model for {cli}", model)
        await self.press("slash")
        await self.types(model)
        await self.press("enter", "enter")
        await self.waits("Set up agent", model)
        await self.press("down", "enter")
        await self.chooses("effort", "low")
        await self.click("#act-save")
        await self.waits(f"{cli}/", f"{model}", ":low ▸")

        # A run needs a budget: a time and a few dollars, whichever comes first.
        await self.press("down", "enter")
        await self.waits(f"Set budget for {flow}")
        await self.press("enter")
        await self.types(budget)
        await self.press("enter", "down", "enter")
        await self.types("1")
        await self.press("enter")
        await self.click("#act-done")
        await self.waits(f"stops at {budget}, $1.00")
        await self.click("#act-save")
        await self.waits(f"◉ {flow}", "enter a task to start the flow")

    async def starts(self, task: str) -> None:
        """Says the task, which is what starts the flow set up."""
        await self.types(task)
        await self.press("enter")
