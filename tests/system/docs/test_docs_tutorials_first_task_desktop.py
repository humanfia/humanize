"""The pictures of `docs/tutorials/first-task-desktop.md`: a first task, in Humanize Desktop.

One journey in the app's window, as the page tells it: the app opens on a new chat, the
Accounts settings say what agents run as, a folder is opened and a question asked, a flow is
installed out of the official flowverse, started on a task under a budget, watched, and read
once it is done. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_first_task_desktop.py`.

The official flowverse is staged here, since the world comes with its flows already installed
and nothing is fetched: an index and a repository per flow, made up on this machine where the
suite tells git GitHub is, so that the page lists, fetches and installs them as it would the
real ones, under the real names.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import TYPE_CHECKING

import yaml
from playwright.sync_api import expect

from tests.integration.conftest import FLOWS
from tests.system.docs import shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-first-task-desktop"

#: The flow the page installs and runs, the question it asks first, and the task it sets.
_FLOW = "rlar"
_QUESTION = "Where is checkout handled?"
_TASK = "Add a discount code to checkout"

_WHERE = (
    "Checkout is in shop/checkout.py: charge() takes a cart and returns what to charge,"
    " in cents. It calls total() in shop/cart.py, which adds up the prices in"
    " shop/catalogue.py."
)

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

#: What an agent of the flow does when told the task: the actor's words, and the reviewer's
#: verdict, each after reading, editing and testing.
_WORK = {
    "text": (
        "Added a discount code to checkout: charge() takes a code now, and WELCOME10"
        " takes 10% off the total. Two new tests cover it, and all three pass."
    ),
    "json": {"done": True, "notes": "The discount code works and its tests pass."},
    "tools": [
        {
            "name": "Read",
            "input": {"file_path": "shop/checkout.py"},
            "result": "def charge(items): ...",
            "takes": 1.0,
        },
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 1.0,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "3 passed in 0.14s",
            "takes": 1.5,
        },
    ],
    "writes": {"shop/checkout.py": _CHECKOUT},
    "after": 1.5,
}

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


def _ready(page: Page) -> Locator:
    """The box of a new chat, once the agent it would start is on offer under it."""
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    return page.get_by_role("textbox", name="First message")


def _sidebar(page: Page) -> Locator:
    """The sidebar, whose rows say where each chat and epic stands."""
    return page.locator("[data-hmz=sidebar]")


def _installs(page: Page) -> Locator:
    """The button that installs the flow, on the official flowverse's list."""
    row = page.locator("[data-hmz=index] > *").filter(
        has=page.get_by_text(_FLOW, exact=True)
    )
    return row.get_by_role("button", name="Install")


def test_the_app_opens_on_a_new_chat(world: World) -> None:
    reel = shots.Reel(f"{_PAGE}-open", window="desktop")
    reel.splash("starting", hold=1.6)
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        _ready(page)
        reel.web(page, hold=4, poster=True)
    reel.save()


def test_windows_installs_the_cli_first() -> None:
    shots.splash(
        "installing",
        {"updating": False, "step": "hmz", "line": "Resolved 61 packages in 1.02s"},
        f"{_PAGE}-installing",
        window=None,
    )


def test_an_account_is_added(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/settings/accounts")
        page.get_by_label("Sign-in method").select_option("key")
        page.get_by_label("Name", exact=True).fill("work")
        key = page.locator("[data-hmz=make-account] input[type=password]").first
        key.fill("not-a-real-key")
        create = page.get_by_role("button", name="Create")
        shots.web(page, f"{_PAGE}-account", window="desktop", pointer=create)


def test_a_folder_is_opened_and_a_question_asked(world: World) -> None:
    world.says({"Where is checkout": {"text": _WHERE, "after": 1.5}})
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        _ready(page)
        start = page.locator("[data-hmz=start]")
        start.get_by_role("button").filter(has_text="shop").first.click()
        page.get_by_text("No folder", exact=True).click()
        chip = start.get_by_role("button").filter(has_text="No folder").first
        expect(chip).to_be_visible()
        chip.click()
        page.get_by_text("Open folder…").click()
        page.keyboard.type("~/shop")
        opens = page.get_by_role("button", name="Open", exact=True)
        expect(opens).to_be_visible()
        shots.web(page, f"{_PAGE}-folder", clip=start, pad=110, pointer=opens)
        opens.click()
        expect(
            start.get_by_role("button").filter(has_text="shop").first
        ).to_be_visible()
        box = _ready(page)

        reel = shots.Reel(f"{_PAGE}-chat", window="desktop")
        reel.web(page, hold=1.0, pointer=box, click=True)
        reel.type(page, box, _QUESTION, per=9)
        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        expect(page.get_by_role("log")).to_contain_text(_QUESTION)
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        reel.web(page, hold=1.4, caption="the agent is working")
        expect(page.get_by_role("log")).to_contain_text("shop/catalogue.py")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        expect(_sidebar(page).get_by_text("Running")).to_have_count(0)
        reel.web(page, hold=4, poster=True)
        reel.save()


def test_a_flow_is_installed_out_of_the_official_flowverse(
    world: World, tmp_path: Path
) -> None:
    _official(tmp_path)
    shutil.rmtree(world.workspace / ".hmz" / "flows")
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        _ready(page)
        reel = shots.Reel(f"{_PAGE}-install", window="desktop")
        flows = page.get_by_role("link", name="Flows", exact=True)
        reel.web(page, hold=1.0, pointer=flows, click=True)
        flows.click()
        browse = page.locator("[data-hmz=flows-browse]")
        expect(browse).to_be_visible()
        reel.web(page, hold=1.4, pointer=browse, click=True)
        browse.click()
        install = _installs(page)
        expect(install).to_be_visible()
        reel.web(page, hold=1.6, pointer=install, click=True)
        install.click()
        installed = page.get_by_text("1.0.0 installed")
        expect(installed).to_be_visible()
        installed.hover()
        reel.web(page, hold=4, pointer=installed, poster=True)
        reel.save()


def test_the_flow_is_started_watched_and_done(world: World, tmp_path: Path) -> None:
    _official(tmp_path)
    shutil.rmtree(world.workspace / ".hmz" / "flows")
    world.says({"discount": _WORK})
    with world.page(desktop=True) as page:
        go(page, "/flows?tab=verses")
        _installs(page).click()
        expect(page.get_by_text("1.0.0 installed")).to_be_visible()

        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        expect(view.locator("[data-hmz=flow-picker] b")).to_have_text(_FLOW)
        expect(view.get_by_text("reviewer", exact=True)).to_be_visible()
        expect(view.get_by_text("Asking…")).to_have_count(0)
        view.get_by_label("Longest it may take, in minutes").fill("10")
        box = view.get_by_placeholder(re.compile("What should"))
        box.click()
        box.press_sequentially(_TASK)
        shots.web(page, f"{_PAGE}-new-epic", window="desktop")

        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/epics/[^/?]+$"))
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        graph = page.locator("[data-hmz=graph]")
        expect(graph.get_by_text(re.compile(r"^working"))).to_have_count(1)
        expect(graph.get_by_text("not started")).to_have_count(1)
        page.wait_for_timeout(2500)
        shots.web(page, f"{_PAGE}-running", window="desktop", most=shots.REEL)

        expect(page.get_by_role("link", name="Resume").first).to_be_visible()
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        expect(_sidebar(page).get_by_text("Done", exact=True)).to_be_visible()
        shots.web(page, f"{_PAGE}-done", window="desktop", most=shots.REEL)

        graph.locator("[data-hmz=graph-session]").first.click()
        expect(page.locator("[data-hmz=thread]")).to_contain_text("WELCOME10")
        shots.web(page, f"{_PAGE}-session", window="desktop", most=shots.REEL)
