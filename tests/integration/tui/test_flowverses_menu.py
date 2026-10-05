"""The flowverses of `/flow`: the indexes flows are installed from, and installing out of one.

A flowverse is an index -- a repository of `flows/<flow>/<version>/flow.yaml`, one manifest per
release -- so what this side of the menu offers is a walk down it: the flowverses, the flows
one lists, the releases of one, and installing, switching to or taking away a release. What runs
git is done as it is asked for and said under the list, and in the transcript once the menu is
left; nothing here is held until the menu is saved.

Every repository is one a test made under its own temporary directory and reaches as
`file://`, which is what the index's `repo:` takes as well as `owner/repo`. Driven headlessly,
as every test of the interface is, so what is checked is where a keystroke or a click lands
rather than how it is drawn.
"""

from __future__ import annotations

import subprocess
import textwrap
from typing import TYPE_CHECKING, NamedTuple, cast

import pytest
from textual.widgets import Button, Input, Label, OptionList

from hmz.runtime.flowing import OFFICIAL
from hmz.runtime.flowing import index as shelf
from hmz.runtime.flowing import verses as store
from hmz.tui import Humanize
from hmz.tui.flows import (
    HOME,
    INSTALLED,
    RELEASES,
    VERSE,
    VERSES,
    Fetches,
    Flows,
    Removes,
)
from hmz.tui.pick import _ACT_ADD, _ACT_DONE, _ACT_SEARCH
from tests.integration.tui.test_app import bar, changes, ids, leaves, onto, rows
from tests.tui.fixtures import transcript, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow, as short as one can be: what is installed is the directory, not what it does.
FLOW = '''"""Somebody else's demo, RELEASE."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def demo(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
               ctx: FlowContext) -> None:
    """Somebody else's demo, RELEASE."""
    worker = agents["worker"]
    await worker.run(task, session=await worker.spawn(), env=envs["workspace"])
'''


#: What the steps of the way here across the top are separated by.
SEP = " \N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK} "


def git(*said: str, at: Path) -> str:
    """Runs one git command in a directory, failing the test if it fails."""
    return subprocess.run(
        [
            "git",
            "-C",
            str(at),
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            *said,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class Shelf(NamedTuple):
    """A repository a flow is released from, and an index that lists its releases.

    Attributes:
      repo: Where the flow lives, in a directory named after it.
      listed: The flowverse: `flows/<flow>/<version>/flow.yaml`, one per release.
    """

    repo: Path
    listed: Path

    def releases(self, version: str, name: str = "demo") -> str:
        """Cuts one release of a flow and lists it in the index.

        Args:
          version: The release, as SemVer.
          name: The flow.

        Returns:
          The commit it was cut at.
        """
        at = self.repo / name
        at.mkdir(parents=True, exist_ok=True)
        (at / "__init__.py").write_text(
            FLOW.replace("demo", name).replace("RELEASE", version)
        )
        git("add", "-A", at=self.repo)
        git("commit", "-m", f"{name} {version}", at=self.repo)
        git("tag", f"{name}-v{version}", at=self.repo)
        commit = git("rev-parse", "HEAD", at=self.repo)
        manifest = self.listed / store.FLOWS / name / version / shelf.RELEASE
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            textwrap.dedent(f"""\
                name: {name}
                version: {version}
                description: Somebody else's {name}.
                repo: file://{self.repo}
                ref: {name}-v{version}
                commit: {commit}
                subdir: {name}
                license: Apache-2.0
                """)
        )
        git("add", "-A", at=self.listed)
        git("commit", "-m", f"list {name} {version}", at=self.listed)
        return commit


@pytest.fixture
def mine(tmp_path: Path) -> Shelf:
    """A flow with one release, and an index listing it -- not yet added as a flowverse."""
    repo, index = tmp_path / "flows-repo", tmp_path / "index"
    for one in (repo, index):
        one.mkdir()
        git("init", "-b", "main", at=one)
    (index / "README.md").write_text("An index of flows.\n")
    git("add", "-A", at=index)
    git("commit", "-m", "an index", at=index)
    made = Shelf(repo, index)
    made.releases("0.1.0")
    return made


async def into_verses(app: Humanize, driver: Pilot[None]) -> Flows:
    """Opens `/flow` and goes up to its first screen and into the flowverses, by the keys."""
    await driver.press(*"/flow")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    sheet = cast("Flows", app.screen)
    await until(lambda: bool(ids(app)), driver)
    await driver.press("left")
    await until(lambda: sheet._page == HOME, driver)
    await onto(app, driver, VERSES)
    await driver.press("enter")
    await until(lambda: sheet._page == VERSES, driver)
    return sheet


async def clicks(app: Humanize, driver: Pilot[None], held: str) -> None:
    """Clicks the row of the list on top put up under one id, on its first line.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The row, by its id.
    """
    listing = app.screen.query_one("#choices", OptionList)
    at = ids(app).index(held)
    # Which line of the list each option starts on, as the list itself lays them out.
    line = next(y for y, (option, _) in enumerate(listing._lines) if option == at)
    await driver.click("#choices", offset=(4, 1 + line - round(listing.scroll_y)))
    await driver.pause()


def under(sheet: Flows) -> str:
    """What is said under the list, which is where what was done reports itself."""
    return str(sheet.query_one("#tuning", Label).content)


def crumbs(sheet: Flows) -> str:
    """The way here across the top, as it reads: each step back, then the page open."""
    steps = [
        str(one.content) for one in sheet.query(".crumb").results(Label) if one.display
    ]
    return SEP.join([*steps, str(sheet.query_one("#asked", Label).content)])


@pytest.mark.timeout(60)
async def test_the_flowverses_are_a_page_of_the_flow_menu(mine: Shelf) -> None:
    """Every index there is, humanize's own first whether or not it was fetched."""
    store.add(f"file://{mine.listed}", "mine")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await into_verses(app, driver)

        # Indexes only: your own two directories are places flows are, not indexes.
        assert rows(app) == [OFFICIAL, "mine"]
        assert crumbs(sheet) == SEP.join(["hmz", "/flow", "Flowverses"])
        drawn = str(
            sheet.query_one("#choices", OptionList).get_option(f"={OFFICIAL}").prompt
        )
        assert "not fetched" in drawn
        # Doing things to them is a bar of buttons under the list, saving being none of them:
        # nothing here is held.
        assert bar(app) == [_ACT_ADD, "fetch", "remove", _ACT_SEARCH]
        # And humanize's own is not one to take away.
        assert app.screen.query_one("#act-remove", Button).disabled


@pytest.mark.timeout(90)
async def test_a_release_is_installed_by_walking_down_to_it_with_the_keys(
    mine: Shelf,
) -> None:
    """Flowverse, flow, release: enter on each, and the release installs on the last."""
    store.add(f"file://{mine.listed}", "mine")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await into_verses(app, driver)
        await onto(app, driver, "mine")
        await driver.press("enter")
        await until(lambda: sheet._page == VERSE, driver)

        assert rows(app) == ["demo"]
        assert crumbs(sheet) == SEP.join(["hmz", "/flow", "Flowverses", "mine"])
        # Listed at its newest release, and not installed: not one of the flows to run yet.
        assert "0.1.0" in str(
            sheet.query_one("#choices", OptionList).get_option("=demo").prompt
        )
        assert not any(one.name == "@mine/demo" for one in sheet._all())

        await driver.press("enter")
        await until(lambda: sheet._page == RELEASES, driver)
        assert rows(app) == ["0.1.0"]
        assert crumbs(sheet) == SEP.join(["hmz", "/flow", "Flowverses", "mine", "demo"])

        await driver.press("enter")
        await until(lambda: "is installed" in under(sheet), driver)

        assert "@mine/demo 0.1.0 is installed" in under(sheet)
        drawn = str(sheet.query_one("#choices", OptionList).get_option("=0.1.0").prompt)
        assert "installed" in drawn
        # Installed is nothing to install again.
        assert app.screen.query_one("#act-install", Button).disabled
        assert [one.version for one in shelf.installed("mine")] == ["0.1.0"]

        # And it is a flow to run, under the name of the flowverse it came from.
        await driver.press("escape", "escape", "escape")
        await until(lambda: sheet._page == HOME, driver)
        await onto(app, driver, INSTALLED)
        await driver.press("enter")
        await until(lambda: "@mine/demo" in rows(app), driver)
        drawn = str(
            sheet.query_one("#choices", OptionList).get_option("=@mine/demo").prompt
        )
        assert "0.1.0" in drawn

        await leaves(app, driver)
        assert "@mine/demo 0.1.0 is installed" in transcript(app)


@pytest.mark.timeout(90)
async def test_a_newer_release_is_marked_and_updated_to(mine: Shelf) -> None:
    """Fetched, a newer release in the index is an update to offer rather than one to take."""
    store.add(f"file://{mine.listed}", "mine")
    shelf.install("mine", "demo")
    mine.releases("0.2.0")
    store.fetch("mine")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        await until(lambda: "@mine/demo" in rows(app), driver)

        drawn = str(
            sheet.query_one("#choices", OptionList).get_option("=@mine/demo").prompt
        )
        assert "0.1.0" in drawn
        assert "↑ 0.2.0" in drawn
        # Still the release that was installed: a fetch offers an update, it does not take one.
        assert [one.version for one in shelf.installed("mine")] == ["0.1.0"]

        await onto(app, driver, "@mine/demo")
        await onto(app, driver, "update")
        await driver.press("enter")
        await until(lambda: "is installed" in under(sheet), driver)

        assert [one.version for one in shelf.installed("mine")] == ["0.2.0"]
        drawn = str(
            sheet.query_one("#choices", OptionList).get_option("=@mine/demo").prompt
        )
        assert "0.2.0" in drawn
        assert "↑" not in drawn
        assert app.screen.query_one("#act-update", Button).disabled


@pytest.mark.timeout(90)
async def test_another_release_is_switched_to_and_one_is_uninstalled(
    mine: Shelf,
) -> None:
    """A release is picked from every release, newest first, and the installed one ticked."""
    mine.releases("0.2.0")
    mine.releases("1.0.0-rc.1")
    store.add(f"file://{mine.listed}", "mine")
    shelf.install("mine", "demo", "0.2.0")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await into_verses(app, driver)
        await onto(app, driver, "mine")
        await driver.press("enter")
        await until(lambda: sheet._page == VERSE, driver)
        await driver.press("enter")
        await until(lambda: sheet._page == RELEASES, driver)

        assert rows(app) == ["1.0.0-rc.1", "0.2.0", "0.1.0"]
        listing = sheet.query_one("#choices", OptionList)
        assert "prerelease" in str(listing.get_option("=1.0.0-rc.1").prompt)
        assert "installed" in str(listing.get_option("=0.2.0").prompt)
        # The cursor opens on the one installed, which is what somebody is moving from.
        assert sheet.under() == "0.2.0"

        await onto(app, driver, "0.1.0")
        await driver.pause()
        assert (
            str(app.screen.query_one("#act-install", Button).label) == "Switch to 0.1.0"
        )
        await onto(app, driver, "install")
        await driver.press("enter")
        await until(lambda: "is installed" in under(sheet), driver)
        assert [one.version for one in shelf.installed("mine")] == ["0.1.0"]

        await onto(app, driver, "uninstall")
        await driver.press("enter")
        await until(lambda: "uninstalled" in under(sheet), driver)
        assert shelf.installed("mine") == []
        assert app.screen.query_one("#act-uninstall", Button).disabled


@pytest.mark.timeout(90)
async def test_the_whole_walk_is_a_click_apiece(mine: Shelf) -> None:
    """Every card, row, button and step of the way here answers to the mouse as well."""
    store.add(f"file://{mine.listed}", "mine")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        await until(lambda: bool(ids(app)), driver)

        # Up to the first screen by its step across the top, and into the flowverses.
        await driver.click("#crumb-1")
        await until(lambda: sheet._page == HOME, driver)
        await clicks(app, driver, VERSES)
        await until(lambda: sheet._page == VERSES, driver)
        await clicks(app, driver, "mine")
        await until(lambda: sheet._page == VERSE, driver)
        await clicks(app, driver, "demo")
        await until(lambda: sheet._page == RELEASES, driver)
        await driver.click("#act-install")
        await until(lambda: "is installed" in under(sheet), driver)
        assert [one.version for one in shelf.installed("mine")] == ["0.1.0"]

        # A step of the way here is a way back to it: `hmz`, `/flow`, the flowverses, and
        # the flowverse, before the flow open.
        await driver.click("#crumb-3")
        await until(lambda: sheet._page == VERSE, driver)
        await driver.click("#crumb-2")
        await until(lambda: sheet._page == VERSES, driver)
        await driver.click("#crumb-1")
        await until(lambda: sheet._page == HOME, driver)
        await clicks(app, driver, INSTALLED)
        await until(lambda: sheet._page == INSTALLED, driver)
        assert "@mine/demo" in rows(app)


@pytest.mark.timeout(90)
async def test_a_flowverse_is_added_from_a_form_and_removed_with_what_it_installed(
    mine: Shelf,
) -> None:
    """Typed in, cloned, and its flows offered to install; taken away, flows and all."""
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await into_verses(app, driver)
        await onto(app, driver, _ACT_ADD)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fetches), driver)
        await changes(app, driver, "repository", *f"file://{mine.listed}")
        await changes(app, driver, "name", *"mine")
        await onto(app, driver, _ACT_DONE)
        await driver.press("enter")
        await until(
            lambda: app.screen is sheet and "mine is fetched" in under(sheet), driver
        )

        assert rows(app) == [OFFICIAL, "mine"]
        assert sheet.under() == "mine"  # on what was just added
        shelf.install("mine", "demo")
        sheet.reread()  # installed behind the menu's back, which a fetch landing tells it

        await onto(app, driver, "remove")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Removes), driver)
        assert "1 installed flow" in str(app.screen.query_one("#about", Label).content)
        await driver.press("enter")
        await until(lambda: "mine was removed" in under(sheet), driver)

        assert rows(app) == [OFFICIAL]
        assert store.named("mine") is None
        assert shelf.installed("mine") == []


@pytest.mark.timeout(60)
async def test_a_flowverse_is_fetched_from_its_button(
    mine: Shelf, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Somebody who finds it is not downloaded fixes that where they found out."""
    monkeypatch.setattr(store, "OFFICIAL_URL", f"file://{mine.listed}")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await into_verses(app, driver)
        await onto(app, driver, OFFICIAL)
        await driver.press("enter")
        await until(lambda: sheet._page == VERSE, driver)
        assert "not fetched yet" in under(sheet)
        # With nothing listed, the focus is on what there is to do: the button that fetches.
        assert app.screen.focused is app.screen.query_one("#act-fetch")

        await driver.press("enter")
        await until(lambda: "official is fetched" in under(sheet), driver)
        await until(lambda: rows(app) == ["demo"], driver)


@pytest.mark.timeout(60)
async def test_a_manifest_that_does_not_read_is_said_and_the_rest_listed(
    mine: Shelf,
) -> None:
    """One bad file in somebody's index is no reason the rest of it cannot be installed from."""
    bad = mine.listed / store.FLOWS / "broken" / "0.1.0" / shelf.RELEASE
    bad.parent.mkdir(parents=True)
    bad.write_text("name: broken\nversion: one\n")
    git("add", "-A", at=mine.listed)
    git("commit", "-m", "a broken manifest", at=mine.listed)
    store.add(f"file://{mine.listed}", "mine")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await into_verses(app, driver)
        await onto(app, driver, "mine")
        await driver.press("enter")
        await until(lambda: sheet._page == VERSE, driver)

        assert rows(app) == ["demo"]
        assert "skipped broken/0.1.0" in under(sheet)


@pytest.mark.timeout(60)
async def test_a_search_narrows_the_page_it_is_typed_into(mine: Shelf) -> None:
    """The box above the list, and esc empties it before it leaves the page."""
    store.add(f"file://{mine.listed}", "mine")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await into_verses(app, driver)
        seek = sheet.query_one("#seek", Input)

        await driver.press("slash")
        await until(lambda: seek.has_focus, driver)
        await driver.press(*"min")
        await until(lambda: rows(app) == ["mine"], driver)

        await driver.press("escape")
        await until(lambda: not seek.display, driver)
        assert rows(app) == [OFFICIAL, "mine"]
        assert sheet._page == VERSES


@pytest.mark.timeout(60)
async def test_a_failed_fetch_is_said_under_the_list(tmp_path: Path) -> None:
    """Rather than raised at whoever opened the menu, which would lose the menu."""
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await into_verses(app, driver)
        await onto(app, driver, _ACT_ADD)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fetches), driver)
        await changes(app, driver, "repository", *f"file://{tmp_path}/nowhere")
        await onto(app, driver, _ACT_DONE)
        await driver.press("enter")
        await until(lambda: app.screen is sheet and bool(under(sheet)), driver)
        await until(lambda: "fetching" not in under(sheet), driver)

        assert rows(app) == [OFFICIAL]
        assert "nowhere" in under(sheet)


def test_a_private_url_is_not_shown_with_what_was_signed_into_it(
    tmp_path: Path,
) -> None:
    """A token drawn on a screen is a token in a photograph, as on the command line."""
    from hmz.daemon import Hmz

    said = Hmz().verses.whence(
        store.Flowverse(
            name="mine",
            url="https://x-access-token:ghp_secret@github.com/org/flows",
            at=tmp_path,
            fetched=True,
            fixed=False,
        )
    )

    assert "ghp_secret" not in said
    assert said == "https://***@github.com/org/flows"


@pytest.mark.timeout(90)
async def test_a_flow_s_own_page_updates_and_uninstalls_it_with_a_click(
    mine: Shelf,
) -> None:
    """A click on a row is a way into it, so what is done to one flow is on its own page too.

    And a flow taken away from under the menu takes the draft of it along: what the menu
    holds goes back to what it opened holding, there being nothing left to save.
    """
    store.add(f"file://{mine.listed}", "mine")
    shelf.install("mine", "demo")
    mine.releases("0.2.0")
    store.fetch("mine")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        await until(lambda: "@mine/demo" in rows(app), driver)

        await clicks(app, driver, "@mine/demo")
        await until(lambda: sheet._inside, driver)
        assert sheet._flow == "@mine/demo"
        assert {"update", "uninstall", "copy"} <= set(bar(app))

        await driver.click("#act-update")
        await until(lambda: "is installed" in under(sheet), driver)
        assert [one.version for one in shelf.installed("mine")] == ["0.2.0"]
        assert sheet._inside  # still on the page of the flow that was updated

        await driver.click("#act-uninstall")
        await until(lambda: sheet._page == INSTALLED, driver)
        assert "@mine/demo is uninstalled" in under(sheet)
        assert "@mine/demo" not in rows(app)
        assert sheet._flow == "chat"
        assert not sheet._changed
