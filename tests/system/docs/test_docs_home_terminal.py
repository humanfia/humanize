"""The home page's Terminal scene: the same task, handed to the same flow, in `hmz`.

Two reels of the terminal interface (`home.py` says what the home page's scenes share), each
opening in the flow's second round -- the actor has worked, the reviewer has sent it back, and
the actor is working again -- and going on to the end. Their agents run a virtual nous with a
short name, `haiku`, so that what each runs fits its row of the log and of the monitor:

- `home-terminal`, for a desk: the log of the actor at work, which is where it opens and
  rests, then the monitor's graph, a box an agent, as the actor hands over, the reviewer
  takes its turn and the flow is done. The terminal is 87 columns by 28 rows, which is as
  near as a terminal comes to the shape of Humanize Desktop's window;
- `home-terminal-phone`, for a phone: a terminal 60 columns by 38 rows, the narrowest whose
  rows above the prompt and status line under it are each drawn on one line, where the log
  is what reads -- the monitor's table of tokens wraps at that width -- from the same round
  to done.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_home_terminal.py`.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from hmz.runtime.kept import Runs
from tests.integration.doubles_tui import screen, shows, until
from tests.system.docs import home, shots
from tests.system.docs.conftest import AGENT, MODEL

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from hmz.tui import Humanize
    from tests.system.docs.conftest import World

#: A terminal the shape of the desk's window, and one the shape of the phone's page.
_DESK = (87, 28)
_PHONE = (60, 38)

#: The virtual nous the agents run: the stand-in's model, by a name a row has room for.
_NOUS = "haiku"

#: What the reviewer hands back after the first round, which is what the actor is told next.
_NOTES = "An expired coupon still works. Reject it, with a test."

_CODE = "shop/checkout.py"
_TESTS = "tests/test_checkout.py"


def _read(path: str) -> dict[str, object]:
    return {
        "name": "Read",
        "input": {"file_path": path},
        "result": "def charge(items): ...",
        "takes": 0.2,
    }


def _edit(path: str, takes: float = 0.2) -> dict[str, object]:
    return {
        "name": "Edit",
        "input": {"file_path": path},
        "result": "edited",
        "takes": takes,
    }


def _test(passed: int, takes: float = 0.2) -> dict[str, object]:
    return {
        "name": "Bash",
        "input": {"command": "pytest -q"},
        "result": f"{passed} passed in 0.19s",
        "takes": takes,
    }


def _staged(
    world: World,
    *,
    first: list[dict[str, object]],
    again: list[dict[str, object]],
    thinks: float,
) -> None:
    """Scripts two rounds of `rlar`: the actor works, is sent back once, and works again.

    The first key found in what an agent is told answers it, so the order here is the order
    they are tried in: the second review (it alone is told what the actor said last), the
    first review, the actor's second turn (it is told the first review's notes), its first.
    The second round is slow, so that each step of it stands long enough to be taken. Both
    roles are to run `_NOUS`, which is set up here too.

    Args:
      world: The world, whose agent is scripted.
      first: What the actor does on its first turn, a line of the log each.
      again: What it does on its second, each as slow as a frame of it takes.
      thinks: How long it then takes to answer, in seconds.
    """
    world.says(
        {
            "are refused": {
                "json": {"done": True, "notes": "Done: both are tested."},
                "after": 3.5,
            },
            "meticulous reviewer": {
                "json": {"done": False, "notes": _NOTES},
                "after": 0.4,
            },
            "still works": {
                "text": "Expired coupons are refused. 7 passed.",
                "tools": again,
                "after": thinks,
            },
            "coupon": {
                "text": "WELCOME10 takes 10% off. 6 passed.",
                "tools": first,
                "after": 0.4,
            },
        }
    )
    # The log shows what an agent does -- its tool calls -- and not only what it answers.
    world.call("settings.set", details=True)
    world.call(
        "nous.set",
        name=_NOUS,
        tries=1,
        policy="exponential-jitter",
        timeout=0,
        graph={"start": "n1", "nodes": {"n1": {"use": AGENT}}},
        then=None,
    )


async def _sent_back(pilot: Pilot[None], app: Humanize) -> None:
    """Hands the flow the task and waits for its second round: the actor working again."""
    await shows(pilot, MODEL)
    # Set up as its `/flow rlar` page would leave it: an agent a role, and a budget.
    app.settings.remember(
        home.FLOW,
        {"actor": Runs(_NOUS), "reviewer": Runs(_NOUS)},
        {},
        None,
        {"cost": 5},
    )
    await pilot.press(*f"/flow {home.FLOW} {home.TASK}", "enter")
    await _said(pilot, app, "is working", 2)


async def _said(pilot: Pilot[None], app: Humanize, text: str, times: int = 1) -> None:
    """Waits until the screen says `text` as many times, and has drawn it."""
    await until(pilot, lambda: screen(app).count(text) >= times, f"{times} {text!r}")
    await pilot.pause(0.2)


async def _onto(pilot: Pilot[None], app: Humanize, role: str) -> None:
    """Moves the monitor's cursor down to the box of the agent filling `role`."""

    def there() -> bool:
        rows = screen(app).splitlines()
        return any(
            row.lstrip().startswith("❯") and f"{role} ·" in under
            for row, under in itertools.pairwise(rows)
        )

    for _ in range(4):
        if there():
            break
        await pilot.press("down")
        await pilot.pause(0.1)
    assert there(), f"no box of the {role}'s to be on:\n{screen(app)}"
    await pilot.pause(0.2)


async def test_a_flow_in_the_terminal_on_a_desk(world: World) -> None:
    _staged(
        world,
        first=[_read(_CODE), _edit(_CODE), _test(6)],
        again=[_edit(_CODE, 2.0), _edit(_TESTS, 2.0), _test(7, 2.5)],
        thinks=4.0,
    )
    async with world.tui(_DESK) as (app, pilot):
        await _sent_back(pilot, app)
        reel = shots.Reel("home-terminal")
        # The log: the task, the actor's first turn, and its second under way.
        await _said(pilot, app, "Edit(", 3)
        reel.tui(app, hold=2.4, poster=True)
        await _said(pilot, app, "Bash(", 2)
        reel.tui(app, hold=1.8, cut=True)
        # The monitor: a box an agent, the actor at its second turn.
        await pilot.press("left")
        await shows(pilot, "monitor · graph", "3 turns")
        await _onto(pilot, app, "actor")
        reel.tui(app, hold=1.4)
        # It hands over, and whoever watches follows it down to the reviewer.
        await shows(pilot, "4 turns")
        await _onto(pilot, app, "reviewer")
        reel.tui(app, hold=2.0)
        await shows(pilot, "the flow is done", "epic · over")
        await pilot.pause(0.2)
        reel.tui(app, hold=1.4)
        reel.save()


async def test_a_flow_in_the_terminal_on_a_phone(world: World) -> None:
    _staged(
        world,
        first=[_read(_CODE), _read(_TESTS), _edit(_CODE), _edit(_TESTS), _test(6)],
        again=[_read(_CODE), _edit(_CODE), _edit(_TESTS), _test(7, 2.0)],
        thinks=1.5,
    )
    async with world.tui(_PHONE) as (app, pilot):
        await _sent_back(pilot, app)
        reel = shots.Reel("home-terminal-phone")
        # The actor's second turn, at its last step.
        await _said(pilot, app, "Bash(", 2)
        reel.tui(app, hold=1.4)
        # It has answered, and the reviewer reads it.
        await _said(pilot, app, "are refused")
        reel.tui(app, hold=2.8, poster=True)
        await _said(pilot, app, "the flow is done")
        reel.tui(app, hold=2.4)
        reel.save()
