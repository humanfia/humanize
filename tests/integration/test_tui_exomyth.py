"""Exomyth: an epic gone into from `/epics`, drawn as a timeline of its sessions and a flame."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest
from textual.widgets import OptionList

from hmz.runtime.doing.epics import Epics as Kept
from hmz.runtime.epic import Epic
from hmz.runtime.tracing.timeline import VERSION, Timeline
from hmz.tui import Humanize
from hmz.tui.exomyth import Exomyth
from hmz.tui.pick import Does, Epics
from tests.integration.doubles_tui import (
    SIZE,
    claude_logged,
    on,
    opened,
    opens,
    screen,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, and an epic of one session Claude Code logged."""
    del asking
    workspace = stand_in(tmp_path, monkeypatch)
    began = time.time()
    with Epic("ralph_loop", "fix the bug", workspace) as epic:
        epic.session("NeiKos496", "claude", "", "sess-1")
    claude_logged(tmp_path / "claude-home", workspace, "sess-1", began)
    return workspace


async def _exomyth(pilot: Pilot[None]) -> Exomyth:
    """Goes into the one epic from `/epics`, and opens it in Exomyth."""
    await opened(pilot)
    await typed(pilot, "/epics")
    await on(pilot, Epics)
    await shows(pilot, "· ralph_loop")
    await pilot.press("enter")
    await on(pilot, Does)
    await shows(pilot, "Exomyth", "the epic as a timeline of its sessions")
    await opens(pilot, "exomyth")
    return await on(pilot, Exomyth)


def _ruler(app: Humanize) -> str:
    """The line of the screen the ticks of time are on."""
    return next(line for line in screen(app).splitlines() if "│" in line)


async def test_an_epic_is_drawn_as_its_sessions_spans_and_read_span_by_span(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await _exomyth(pilot)
        await shows(
            pilot,
            "· ralph_loop \N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}",
            "1 session · 8 spans",
            "▾ ralph_loop",
            "▾ main · sess-1",
            "turn: fix the bug",
            "Bash: pytest",
        )

        # Folded, a session is one row, and what is under it is gone.
        await pilot.press("down", "space")
        await until(
            pilot, lambda: "turn: fix" not in screen(app), "the session to fold"
        )
        await shows(pilot, "▸ main · sess-1")
        await pilot.press("space", "up")
        await shows(pilot, "turn: fix the bug")

        whole = _ruler(app)
        await pilot.press("w", "w")
        await until(pilot, lambda: _ruler(app) != whole, "the ruler to zoom")
        zoomed = _ruler(app)
        await pilot.press("d")
        await until(pilot, lambda: _ruler(app) != zoomed, "the ruler to pan")
        await pilot.press("0")
        await until(pilot, lambda: _ruler(app) == whole, "the whole epic again")

        # The cursor opens on the epic itself: its pane says what it is.
        await pilot.press("enter")
        await shows(pilot, "flow · ralph_loop", "lasted", "task fix the bug")
        await pilot.press("escape")

        await pilot.press("slash", *"pytest", "enter")
        await shows(pilot, "1 of 1 · pytest")
        await pilot.press("enter")
        await shows(pilot, "tool · ", "command", "pytest")

        await pilot.press("tab")
        await shows(
            pilot, "weighed by time · sessions merged", "stack", "NeiKos496", "Bash"
        )
        await pilot.press("t")
        await shows(pilot, "weighed by tokens in", "think")

        await pilot.press("escape")
        await on(pilot, Does)
        await pilot.press("escape")
        await on(pilot, Epics)


async def test_a_range_is_summed_and_weighed_in_the_flame_and_the_slices(
    workspace: Path,
) -> None:
    del workspace
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await _exomyth(pilot)
        await shows(pilot, "Bash: pytest")

        # The process of the row under the cursor, whole.
        await pilot.press("down", "p")
        await shows(pilot, "session · ", "agent NeiKos496", "parent ralph_loop")
        await pilot.press("p")
        await until(pilot, lambda: "agent NeiKos" not in screen(app), "the pane shut")

        # From the first thought to the tool two spans on, held, and summed by category.
        await pilot.press("down", "down", "v", "right", "right", "v")
        await shows(pilot, "Range", "lasted 6s", "category", "llm", "tool", "v drop")
        whole = _ruler(app)
        await pilot.press("f")
        await until(pilot, lambda: _ruler(app) != whole, "the range to fill the window")

        await pilot.press("tab")
        await shows(pilot, "weighed by time · sessions merged · range", "NeiKos496")
        for weight in ("tokens in", "tokens out", "count", "time"):
            await pilot.press("t")
            await shows(pilot, f"weighed by {weight} · ")
        await pilot.press("m")
        await shows(pilot, "sessions apart", "main · sess-1")

        await pilot.press("tab")
        await shows(pilot, "sorted by total↓", "category", "Bash: pytest")
        await pilot.press("o")
        await shows(pilot, "sorted by self↓")
        await pilot.press("O")
        await shows(pilot, "sorted by self↑")

        # A slice picked is found on the timeline.
        sliced = app.screen.query_one("#sliced", OptionList)
        at = next(
            at
            for at in range(sliced.option_count)
            if "Bash: pytest" in str(sliced.get_option_at_index(at).prompt)
        )
        await pilot.press(*["down"] * (at - (sliced.highlighted or 0)), "enter")
        await shows(pilot, "1 of 1 · Bash: pytest", "v drop")
        await pilot.press("escape")
        await until(pilot, lambda: "Range" not in screen(app), "the range let go")
        await pilot.press("shift+tab")
        await shows(pilot, "sorted by self↑")
        await pilot.press("escape")
        await on(pilot, Does)


async def test_an_epic_of_fifty_thousand_spans_is_drawn_and_zoomed_at_once(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del workspace
    big = _synthetic(sessions=50, each=1000)

    def laid_out(_self: Kept, _epic: Path) -> Timeline:
        return big

    monkeypatch.setattr(Kept, "timeline", laid_out)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await _exomyth(pilot)
        await shows(pilot, "50 sessions", "50000 spans", "main · session 0")
        # Each press is drawn before the next is taken: a second apiece is a ceiling a
        # loaded machine stays under, where drawing every span would not.
        for keys in (
            ("w",) * 6,
            ("d",) * 4,
            ("s",) * 6,
            ("down",) * 45,
            ("0", "tab"),
            ("tab",),
        ):
            began = time.perf_counter()
            await pilot.press(*keys)
            screen(app)
            took = time.perf_counter() - began
            assert took < len(keys), f"{keys[0]} took {took:.2f}s"
        await shows(pilot, "sorted by total↓", "Bash: ls")
        await pilot.press("shift+tab")
        await shows(pilot, "weighed by time", "Bash: ls")
        await pilot.press("shift+tab")
        # Walked down past the bottom of the screen, which scrolled to keep up.
        await until(
            pilot,
            lambda: any(
                "❯" in line and "main · session 44" in line
                for line in screen(app).splitlines()
            ),
            "the cursor on the 45th session",
        )


def _synthetic(*, sessions: int, each: int) -> Timeline:
    """A timeline of many sessions of many spans, each a tool call a few ms long."""
    strings = ["", "flows", "chat", "session", "tool", "main", "Bash: ls", "s"]
    processes: list[dict[str, Any]] = [
        {
            "id": 0,
            "kind": "flow",
            "name": 2,
            "parent": -1,
            "tracks": [0],
            "key": "epic:e",
        }
    ]
    tracks: list[dict[str, Any]] = [
        {
            "process": 0,
            "name": 1,
            "first": 0,
            "count": 0,
            "depths": 0,
            "spans": {key: [] for key in _COLUMNS},
        }
    ]
    first = 0
    for at in range(sessions):
        strings.append(f"main · session {at}")
        processes.append(
            {
                "id": at + 1,
                "kind": "session",
                "key": f"claude:{at}",
                "name": len(strings) - 1,
                "parent": 0,
                "tracks": [at + 1],
            }
        )
        starts = [at * 1000 + one * 5000 for one in range(each)]
        tracks.append(
            {
                "process": at + 1,
                "name": 5,
                "first": first,
                "count": each,
                "depths": 1,
                "spans": {
                    "start": starts,
                    "dur": [3000] * each,
                    "depth": [0] * each,
                    "cat": [4] * each,
                    "name": [6] * each,
                    "model": [0] * each,
                    "in": [10] * each,
                    "out": [5] * each,
                },
            }
        )
        first += each
    document: dict[str, Any] = {
        "version": VERSION,
        "layout": "synthetic",
        "epic": "synthetic",
        "origin": 0.0,
        "live": False,
        "strings": strings,
        "processes": processes,
        "tracks": tracks,
        "spawns": {"span": [], "process": []},
        "summary": {"start": 0, "end": sessions * 1000 + each * 5000, "spans": first},
    }
    return Timeline(document, [{} for _ in range(first)])


_COLUMNS = ("start", "dur", "depth", "cat", "name", "model", "in", "out")
