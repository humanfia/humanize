"""The pictures of `docs/user/reporting.md`: error reports, and what goes with an issue.

The switch on the General page of the app's settings, set and saved; the question the
terminal interface asks the first time it opens, its row on `/settings general` and the two
lists `What is sent` reads out; the version a command prints, and the button that exports an
epic to attach. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_reporting.py`.

Nothing is reported from here: every scene but the first-start question runs under
`HUMANIZE_SENTRY=off`, as the whole suite does, and that one leaves the question unanswered
with the reporter's start taken away as well.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import onto, shows
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    import pytest
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after, and the terminal they are taken in.
_PAGE = "user-reporting"
_SIZE = (96, 34)

#: The epic the page exports to attach to an issue.
_TASK = "Add a discount code to checkout"
_WORK = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off. All six tests pass."
)
_REVIEW = {
    "json": {"done": True, "notes": "WELCOME10 takes 10% off. All six tests pass."},
    "after": 0.3,
}


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


# -- in the app -----------------------------------------------------------------------


def test_the_switch_in_the_app(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/settings/general")
        dialog = page.get_by_role("dialog", name="Settings")
        reports = dialog.get_by_label("Report Humanize\u2019s own failures")
        expect(reports).to_be_visible()
        expect(reports).to_have_value("")
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-app", window="desktop", pointer=reports)

        reel = shots.Reel(f"{_PAGE}-app-on", clip=dialog, pad=0)
        reel.web(page, hold=2.2, pointer=reports, click=True)
        reports.select_option("yes")
        save = dialog.get_by_role("button", name="Save", exact=True)
        page.wait_for_timeout(300)
        reel.web(page, hold=2.0, pointer=save, click=True)
        save.click()
        expect(dialog.get_by_role("button", name="Saved")).to_be_visible()
        page.wait_for_timeout(300)
        reel.web(page, hold=3.2, poster=True)
        reel.save()


def test_an_epic_is_exported_to_attach(world: World) -> None:
    world.says({"meticulous reviewer": _REVIEW, "discount": _WORK})
    name = world.epic("rlar", _TASK)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("link", name="Resume").first).to_be_visible()
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        bar = page.locator("[data-hmz=bar]")
        export = bar.get_by_role("button", name="Export")
        export.hover()
        page.wait_for_timeout(500)
        shots.web(page, f"{_PAGE}-export", clip=bar, pad=40, pointer=export)


# -- in the terminal ------------------------------------------------------------------


async def test_the_question_at_first_start(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.runtime import telemetry
    from hmz.runtime.settings import Settings

    # A machine nobody has asked: no answer in the environment and none written down. And
    # nothing can start reporting from here, whatever a key does.
    monkeypatch.delenv("HUMANIZE_SENTRY")
    monkeypatch.setattr(telemetry, "start", lambda: False)
    telemetry.again()
    try:
        async with world.tui(_SIZE) as (app, pilot):
            await shows(pilot, "Report errors to Humanize?")
            await _settled(pilot)
            shots.tui(app, f"{_PAGE}-question")
            # Esc answers nothing; the arrow and enter answer no, which is written down.
            await pilot.press("escape")
            await _settled(pilot)
            assert Settings(world.home).enable_sentry is None
        async with world.tui(_SIZE) as (app, pilot):
            await shows(pilot, "Report errors to Humanize?")
            await _settled(pilot)
            await pilot.press("right", "enter")
            await shows(pilot, "error reporting disabled")
    finally:
        monkeypatch.setenv("HUMANIZE_SENTRY", "off")
        telemetry.again()
    assert Settings(world.home).enable_sentry is False


async def test_the_switch_in_the_terminal(world: World) -> None:
    from hmz.runtime import telemetry
    from hmz.runtime.settings import Settings

    # Answered no, as the run's own environment says: the row reads `off` with nothing
    # overriding it.
    Settings(world.home).answers(enable_sentry=False)
    telemetry.again()
    async with world.tui(_SIZE) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press(*"/settings general", "enter")
        await shows(pilot, "Error reports", "What is sent")
        await _settled(pilot)
        await onto(pilot, "reports")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal")
        await onto(pilot, "sent")
        await pilot.press("enter")
        await shows(pilot, "nothing you typed")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-sent")


# -- from the command line ------------------------------------------------------------


def test_the_version_for_an_issue(world: World) -> None:
    del world
    shots.cli(["hmz", "--version"], f"{_PAGE}-version", columns=60)
