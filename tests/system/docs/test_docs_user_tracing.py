"""The pictures of `docs/user/tracing.md`: an epic profiled, and read in Exomyth.

One epic of the project, started with both profiling switches on, as the page tells it: the
switches where an epic is set up (the app's New epic form, the terminal's `/flow` page, a line
of `hmz exec`), then its Exomyth in the app -- opened from the epic, a span picked on the
timeline, a stretch of time picked, the flame graph and its table of slices -- and in the
terminal, view by view. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_tracing.py`.

`World.epic` starts no epic profiled, so the one here is started as it does, with the two
switches said: `_profiled` below.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.exomyth import Exomyth
from hmz.tui.flows import Flows
from tests.integration.doubles_tui import on, onto, screen, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-tracing"

#: The epic the page traces.
_TASK = "Add a discount code to checkout"

#: The page's own lines of Python, which gather the newest epic's Chrome trace.
_PYTHON = """
from hmz.sdk import Hmz

epics = Hmz().epics
where, trace = epics.traced(epics.all()[-1])
print(where)
"""

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

#: What the actor does when told the task: reads, edits, tests, and says so.
_WORK = {
    "text": (
        "Checkout takes a discount code now: charge() looks the code up and takes its"
        " discount off the total. WELCOME10 is 10% off. Two new tests cover it, and all"
        " six pass."
    ),
    "tools": [
        {
            "name": "Read",
            "input": {"file_path": "shop/checkout.py"},
            "result": "def charge(items): ...",
            "takes": 0.7,
        },
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 1.1,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "6 passed in 0.21s",
            "takes": 1.6,
        },
    ],
    "writes": {"shop/checkout.py": _CHECKOUT},
    "after": 0.9,
}

#: What the reviewer does with it: reads the diff, runs the tests, and passes it.
_REVIEW = {
    "json": {
        "done": True,
        "notes": "charge() takes a code and WELCOME10 takes 10% off. All six tests pass.",
    },
    "tools": [
        {
            "name": "Bash",
            "input": {"command": "git diff"},
            "result": "shop/checkout.py | 7 +++++--",
            "takes": 0.6,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "6 passed in 0.21s",
            "takes": 1.2,
        },
    ],
    "after": 0.5,
}


def _scripted(world: World) -> None:
    """Scripts the two agents of `rlar` for the task."""
    world.says({"meticulous reviewer": _REVIEW, "discount": _WORK})


def _profiled(world: World, *, flow: bool = True) -> str:
    """Runs `rlar` on the task to its end with profiling on, as New epic starts it.

    Args:
      world: The world.
      flow: Whether the flow's own Python is profiled beside the programs its agents start.
        Its frames are named by file, and the files are this checkout's: an epic whose
        every frame a picture would show is profiled without it.

    Returns:
      The epic's name.
    """
    _scripted(world)
    here = str(world.workspace)
    with world.session() as session:
        sub = session.call("epic.attach", workspace=here)["sub"]

        def ended() -> bool:
            with session.heard:
                return any(
                    method == "epic.event"
                    and said.get("sub") == sub
                    and said["message"].get("type") == "ended"
                    for method, said in session.told
                )

        session.call(
            "epic.start",
            sub=sub,
            flow="rlar",
            task=_TASK,
            budget={"cost": 5},
            agents={"actor": AGENT, "reviewer": AGENT},
            profile_flow=flow,
            profile_environment=True,
            idem=uuid.uuid4().hex,
        )
        deadline = time.monotonic() + 180
        while not ended():
            assert time.monotonic() < deadline, f"the epic never ended: {session.told}"
            with session.heard:
                session.heard.wait(0.1)
        name = next(
            str(one["name"])
            for one in session.call("runs.list", workspace=here)["runs"]
            if one["task"] == _TASK
        )
        session.call("epic.detach", sub=sub)
    return name


def _open(page: Page, name: str) -> None:
    """Opens the epic's own page, drawn as an ended epic is."""
    go(page, f"/epics/{name}")
    expect(page.get_by_role("link", name="Resume").first).to_be_visible()
    expect(page.get_by_text("Reading handovers")).to_have_count(0)
    expect(page.locator(".side-scroll").get_by_text("Running")).to_have_count(0)


def _whole(page: Page) -> bool:
    """Whether the Exomyth open holds the reviewer's work, and says the epic is done."""
    page.wait_for_function("() => window.__exomyth && window.__exomyth.model()")
    held = page.evaluate(
        """() => {
          const model = window.__exomyth.model()
          return model.tracks.some((track) =>
            Array.from(track.name_, (at) => model.strings[at]).includes('Bash: git diff'))
        }"""
    )
    return bool(held and page.locator("[data-hmz=bar]").get_by_text("done").count())


def _traced(page: Page, name: str) -> None:
    """Opens the epic's Exomyth once its trace holds every session's log, the reviewer's too.

    A trace read the instant the epic ended can come before its last session's log is whole,
    and still say the epic is running: it is opened again until it is whole.
    """
    _open(page, name)
    deadline = time.monotonic() + 90
    while True:
        go(page, f"/epics/{name}/exomyth")
        if _whole(page):
            return
        assert time.monotonic() < deadline, "the trace never held the reviewer's work"
        go(page, f"/epics/{name}")
        page.wait_for_timeout(1000)


def _span(page: Page, name: str) -> dict[str, float]:
    """Where on the page the first span of a name is drawn in the timeline."""
    at = page.evaluate(
        """(name) => {
          const model = window.__exomyth.model()
          for (const track of model.tracks)
            for (let i = 0; i < track.count; i++)
              if ((model.strings[track.name_[i]] || '').includes(name))
                return window.__exomyth.where(track.first + i)
          return null
        }""",
        name,
    )
    assert at, f"the timeline has no span named {name!r}"
    return at


def _folds(page: Page, process: str) -> None:
    """Folds one process of the timeline by its caret, as a click on it does."""
    at = page.evaluate(
        """(name) => {
          const model = window.__exomyth.model()
          const one = model.processes.find((it) => it.name === name)
          if (!one) return null
          const track = model.tracks[one.tracks[0]]
          const first = window.__exomyth.where(track.first)
          const box = document.querySelector('[data-hmz=exomyth-canvas]').getBoundingClientRect()
          const x = box.left + 8 + Math.min(one.level, 8) * 12 + 7
          return { x, y: first.y, depth: track.depth[0] }
        }""",
        process,
    )
    assert at, f"the timeline has no process named {process!r}"
    # Its head is the row above its first track's first depth: 18 a depth, 24 the head.
    page.mouse.click(at["x"], at["y"] - at["depth"] * 18 - 21)
    page.wait_for_timeout(300)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_the_switches_in_the_app(world: World) -> None:
    _scripted(world)
    with world.page(desktop=True) as page:
        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        picker = view.locator("[data-hmz=flow-picker]")
        expect(picker.locator("b")).not_to_have_text("…")
        picker.click()
        flow = page.get_by_text("rlar", exact=True).first
        expect(flow).to_be_visible()
        flow.click()
        expect(picker.locator("b")).to_have_text("rlar")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        view.get_by_label("Most it may cost, in dollars").fill("5")
        view.get_by_role("textbox", name="Task").fill(_TASK)
        first = view.get_by_role("checkbox", name="Profile flow")
        second = view.get_by_role("checkbox", name="Profile environment")
        first.check()
        second.check()
        expect(second).to_be_checked()
        shots.web(
            page,
            f"{_PAGE}-switches",
            window="desktop",
            pointer=second,
            most=shots.REEL,
        )


def test_exomyth_in_the_app(world: World) -> None:
    name = _profiled(world)
    with world.page(desktop=True, height=900) as page:
        _open(page, name)
        bar = page.locator("[data-hmz=bar]")
        opener = bar.locator("[data-hmz=exomyth-open]")
        opener.hover()
        page.wait_for_timeout(700)
        shots.web(
            page, f"{_PAGE}-open", window="desktop", pointer=opener, most=shots.REEL
        )

        _traced(page, name)
        _folds(page, "python")
        at = _span(page, "Edit: shop/checkout.py")
        page.mouse.click(at["x"], at["y"])
        expect(page.locator("[data-hmz=exomyth-span-name]")).to_contain_text("Edit")
        expect(page.locator("[data-hmz=exomyth-args]")).to_be_visible()
        shots.web(page, f"{_PAGE}-timeline", window="desktop", most=shots.REEL)

        # A stretch of time, dragged across the reviewer's turn.
        page.keyboard.press("Escape")
        begin = _span(page, "Bash: git diff")
        box = page.locator("[data-hmz=exomyth-canvas]").bounding_box()
        assert box
        y = box["y"] + 60
        last = page.evaluate(
            """() => {
              const model = window.__exomyth.model()
              let at = null
              for (const track of model.tracks)
                for (let i = 0; i < track.count; i++)
                  if ((model.strings[track.name_[i]] || '') === 'Bash: pytest -q')
                    at = window.__exomyth.where(track.first + i)
              return at
            }"""
        )
        assert last, "the timeline has no test run of the reviewer's"
        page.mouse.move(begin["x"] - 30, y)
        page.mouse.down()
        page.mouse.move(begin["x"], y, steps=4)
        page.mouse.move(last["x"] + 60, y, steps=8)
        page.mouse.up()
        expect(page.locator("[data-hmz=exomyth-range]")).to_be_visible()
        shots.web(
            page,
            f"{_PAGE}-range",
            window="desktop",
            pointer=(last["x"] + 60, y),
            most=shots.REEL,
        )


def test_the_flame_graph_in_the_app(world: World) -> None:
    name = _profiled(world, flow=False)
    with world.page(desktop=True, height=900) as page:
        _traced(page, name)
        page.get_by_role("tab", name="Flame").click()
        expect(page.get_by_text("Slices")).to_be_visible()
        page.wait_for_function("() => window.__exomyth.flame()")
        page.wait_for_timeout(500)
        shots.web(page, f"{_PAGE}-flame", window="desktop", most=shots.REEL)


async def test_the_switches_in_the_terminal(world: World) -> None:
    _scripted(world)
    async with world.tui((100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow rlar", "enter")
        await on(pilot, Flows)
        await shows(pilot, "Profile flow", "Profile environment")
        for row in ("profile-flow", "profile-environment"):
            await onto(pilot, f"\x1e{row}")
            # The list opens on the answer it is not: enter twice turns it round.
            await pilot.press("enter")
            await _settled(pilot)
            await pilot.press("enter")
            await _settled(pilot)
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-switches")


async def test_exomyth_in_the_terminal(world: World) -> None:
    _profiled(world, flow=False)
    async with world.tui((110, 32)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/epics", "enter")
        await shows(pilot, "Every epic in this directory", "rlar")
        await pilot.press("enter")
        await shows(pilot, "the epic as a timeline of its sessions")
        await onto(pilot, "exomyth")
        await pilot.press("enter")
        await on(pilot, Exomyth)
        await shows(pilot, "Bash")
        await _settled(pilot, 1.0)
        reel = shots.Reel(f"{_PAGE}-terminal-views")
        reel.tui(app, hold=2.4, caption="the timeline")
        # The cursor down to the actor's tools, back to its test run, and the pane opened.
        await pilot.press("down", "down", "down", "enter")
        for _ in range(8):
            await _settled(pilot, 0.3)
            if "│ Bash: pytest -q" in screen(app):
                break
            await pilot.press("left")
        await shows(pilot, "│ Bash: pytest -q", "6 passed")
        await _settled(pilot, 0.8)
        shots.tui(app, f"{_PAGE}-terminal")
        await pilot.press("escape")
        await _settled(pilot)
        await pilot.press("tab")
        await _settled(pilot, 0.8)
        reel.tui(app, hold=2.8, keys="tab", caption="the flame view")
        await pilot.press("tab")
        await _settled(pilot, 0.8)
        reel.tui(app, hold=3.2, keys="tab", caption="the slices table", poster=True)
        reel.save()


def test_a_profiled_run_from_the_command_line(world: World) -> None:
    _scripted(world)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "rlar",
            "-a",
            f"actor={AGENT}",
            "-a",
            f"reviewer={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            "--profile-flow",
            "--profile-environment",
            _TASK,
        ],
        f"{_PAGE}-exec",
        columns=118,
    )

    # The page's lines of Python, run as written: the newest epic's trace, gathered.
    said = subprocess.run(
        [sys.executable, "-c", _PYTHON],
        check=True,
        capture_output=True,
        text=True,
        cwd=world.workspace,
    ).stdout.strip()
    assert said.endswith(".trace.json"), said
    assert "/traces/" in said, said
    held = json.loads(Path(said).read_text())
    assert held["otherData"], "the trace says nothing of what it holds"
