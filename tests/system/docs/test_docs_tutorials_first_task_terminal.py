"""The pictures of `docs/tutorials/first-task-terminal.md`: a first task, in the terminal.

One journey in one terminal, as the page tells it: `hmz` opens on a chat, a flow is installed
out of the official flowverse, given a budget and a task, watched in the monitor, stopped, and
read back from `/epics`, down to what one session did. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_first_task_terminal.py`.

The official flowverse is staged here, since the world comes with its flows already installed
and nothing is fetched: an index and a repository per flow, made up on this machine where the
suite tells git GitHub is, so that the interface lists, fetches and installs them as it would
the real ones, under the real names.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import yaml

from hmz.tui.flows import Flows
from hmz.tui.pick import Configures, Confirms
from tests.integration.conftest import FLOWS
from tests.integration.doubles_tui import on, onto, shows, until
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-first-task-terminal"

#: The flows the official index lists, and what it says of each.
_ABOUT = {
    "continue_loop": (
        'Send the task once, then keep nudging "continue" until the budget is spent.'
    ),
    "flame_chase": "Two agents take turns on the same task until the budget is spent.",
    "goal": "The task set once as the agent's own goal.",
    "ralph_loop": "The task again and again, a fresh session every round.",
    "rlar": "An actor works in one session until a fresh reviewer says the task is done.",
    "stateful_ralph": "The task again and again, in one session that remembers.",
}

#: The flow the page installs and runs, the question it asks first, and the task it sets.
_FLOW = "ralph_loop"
_QUESTION = "Where is checkout handled?"
_TASK = "Add a discount code to checkout"


def _git(at: Path, *argv: str) -> str:
    said = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Humanfia",
            "-c",
            "user.email=flows@example.com",
            *argv,
        ],
        cwd=at,
        check=True,
        capture_output=True,
        text=True,
    )
    return said.stdout.strip()


def _official(tmp_path: Path) -> None:
    """Stages the official flowverse with nothing installed out of it: its index, fetched.

    The suite tells git that `https://github.com/` is `<tmp_path>/no-github/`: a repository
    made there is the one a flow's `humanfia/<name>` is fetched from.
    """
    from hmz.runtime.flowing import verses
    from hmz.runtime.flowing.index import kept

    shutil.rmtree(kept(verses.OFFICIAL), ignore_errors=True)
    github = tmp_path / "no-github" / "humanfia"
    listing = github / "flowverse"
    for name, about in _ABOUT.items():
        repo = github / f"{name.replace('_', '-')}-flow"
        shutil.copytree(
            FLOWS / name, repo, ignore=shutil.ignore_patterns("__pycache__")
        )
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", name)
        at = listing / "flows" / name / "1.0.0"
        at.mkdir(parents=True)
        (at / "flow.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": name,
                    "version": "1.0.0",
                    "description": about,
                    "repo": f"humanfia/{repo.name}",
                    "ref": "v1.0.0",
                    "commit": _git(repo, "rev-parse", "HEAD"),
                    "license": "MIT",
                }
            )
        )
    _git(listing, "init", "-q", "-b", "main")
    _git(listing, "add", "-A")
    _git(listing, "commit", "-q", "-m", "index")
    at = verses.where(verses.OFFICIAL) / verses.INDEX
    at.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", str(listing), str(at)], check=True)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def _types(
    pilot: Pilot[None], reel: shots.Reel, line: str, *, per: int = 6
) -> None:
    """Types a line at the prompt, a frame every few characters."""
    for start in range(0, len(line), per):
        await pilot.press(*line[start : start + per])
        await pilot.pause()
        last = start + per >= len(line)
        reel.tui(
            pilot.app, hold=0.7 if last else 0.12, keys=line[: start + per], cut=True
        )


def test_the_version_is_printed(world: World) -> None:
    shots.cli(["hmz", "--version"], f"{_PAGE}-version", columns=64)


async def test_a_first_task_from_a_chat_to_its_result(
    world: World, tmp_path: Path
) -> None:
    _official(tmp_path)
    # A project with no flow of its own: nothing is there to run until one is installed.
    shutil.rmtree(world.workspace / ".hmz" / "flows")
    world.says(
        {
            "Where is checkout": {
                "text": (
                    "Checkout is in shop/checkout.py: charge() takes a cart and"
                    " returns what to charge, in cents. It calls total() in"
                    " shop/cart.py."
                ),
                "after": 1.5,
            },
            "discount": {
                "text": [
                    (
                        "Added a discount code to checkout: charge() takes a code,"
                        " and WELCOME10 takes 10% off."
                    ),
                    (
                        "Covered the discount code with tests: an unknown code"
                        " changes nothing. 3 passed."
                    ),
                    (
                        "Read it through again: the discount code works and its"
                        " tests pass. Nothing left to change."
                    ),
                ],
                "tools": [
                    {
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                        "result": "3 passed in 0.12s",
                        "takes": 1.2,
                    }
                ],
                "after": 2.0,
            },
        }
    )
    async with world.tui() as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-home")

        # -- a chat: a question, and its answer ---------------------------------------
        reel = shots.Reel(f"{_PAGE}-chat")
        reel.tui(app, hold=1.0)
        await _types(pilot, reel, _QUESTION)
        await pilot.press("enter")
        await shows(pilot, "is working")
        reel.tui(app, hold=1.2, keys="enter")
        await shows(pilot, "shop/cart.py", "done")
        await _settled(pilot)
        reel.tui(app, hold=3.5, poster=True)
        reel.save()

        # -- a flow, installed out of the official flowverse ------------------------
        reel = shots.Reel(f"{_PAGE}-install")
        await _types(pilot, reel, "/flow", per=2)
        await pilot.press("enter")
        await on(pilot, Flows)
        await shows(pilot, "No flows installed yet.")
        reel.tui(app, hold=1.6, keys="enter", caption="nothing installed yet")
        await pilot.press("enter")
        await shows(pilot, "humanfia/flowverse")
        reel.tui(app, hold=1.4, keys="enter", caption="on Install more…")
        await pilot.press("enter")
        await shows(pilot, "stateful_ralph")
        reel.tui(app, hold=1.2, keys="enter", caption="on official")
        await onto(pilot, _FLOW)
        await pilot.pause()
        reel.tui(app, hold=1.2, keys="down down down", caption="to ralph_loop")
        await pilot.press("enter")
        await shows(pilot, "Releases of ralph_loop")
        reel.tui(app, hold=1.2, keys="enter", caption="on ralph_loop")
        await pilot.press("enter")
        await shows(pilot, "ralph_loop 1.0.0 is installed")
        await _settled(pilot)
        reel.tui(app, hold=3.5, keys="enter", caption="on 1.0.0", poster=True)
        reel.save()
        for _ in range(4):
            await pilot.press("escape")
            await pilot.pause(0.3)
        await until(pilot, lambda: len(app.screen_stack) == 1, "the menu to close")

        # -- its budget, and saving it ----------------------------------------------
        reel = shots.Reel(f"{_PAGE}-budget")
        await pilot.press(*f"/flow {_FLOW}", "enter")
        await on(pilot, Flows)
        await shows(pilot, "an epic needs one")
        await onto(pilot, "\x1ebudget")
        await pilot.pause()
        reel.tui(app, hold=1.8, keys="down", caption="to budget")
        await pilot.press("enter")
        await on(pilot, Configures)
        await shows(pilot, "Set budget for ralph_loop")
        reel.tui(app, hold=1.4, keys="enter")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press(*"10m")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.2, keys="enter 10m", caption="ten minutes")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press("tab")
        await shows(pilot, "enter Set")
        reel.tui(app, hold=1.2, keys="enter tab", caption="to Set")
        await pilot.press("enter")
        await on(pilot, Flows)
        await shows(pilot, "stops at 10m")
        reel.tui(app, hold=1.8, keys="enter")
        await pilot.press("escape")
        await on(pilot, Confirms)
        reel.tui(app, hold=1.6, keys="esc", caption="it asks before leaving")
        await pilot.press("enter")
        await shows(pilot, "set up: /flow ralph_loop <task> starts it")
        await _settled(pilot)
        reel.tui(app, hold=3.5, keys="enter", caption="saved", poster=True)
        reel.save()

        # -- the task, and the flow at work on it -----------------------------------
        await pilot.press(*f"/flow {_FLOW} {_TASK}", "enter")
        await shows(pilot, "WELCOME10", "ctrl+c twice to stop")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-running")

        await pilot.press("left")
        await shows(pilot, "monitor · graph", "time ")
        await shows(pilot, "3 turns")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-monitor")

        # -- stopped, by ctrl+c twice ---------------------------------------------
        await pilot.press("right")
        await shows(pilot, "ctrl+c stop")
        await pilot.press("ctrl+c")
        await shows(pilot, "press ctrl+c again to stop the flow")
        await pilot.press("ctrl+c")
        await shows(pilot, "stopping the flow", "ctrl+c exit")
        await _settled(pilot, 1.0)
        shots.tui(app, f"{_PAGE}-stopped")

        # -- and read back ----------------------------------------------------------
        await pilot.press(*"/epics", "enter")
        await shows(pilot, "Every epic in this folder", "stopped")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-epics")
        await pilot.press("enter")
        await shows(pilot, "its agents, called flows and sessions, read back")
        await pilot.press("enter")
        await shows(pilot, "actions")
        await _settled(pilot, 1.0)
        await pilot.press("down", "enter")
        await shows(pilot, "read back from its log", "3 passed.")
        await _settled(pilot, 1.5)
        shots.tui(app, f"{_PAGE}-session")
