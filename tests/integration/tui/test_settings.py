"""What a workspace was set up to run, kept so that opening it again finds it that way."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml
from textual.widgets import Label, OptionList

from hmz import home
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from tests.tui.fixtures import transcript, until

if TYPE_CHECKING:
    from pathlib import Path


def test_a_workspace_that_has_run_nothing_remembers_nothing(tmp_path: Path) -> None:
    kept = Settings(tmp_path)

    assert kept.flow == ""
    assert kept.agents("chat") == {}


def test_what_was_set_up_is_what_is_read_back(tmp_path: Path) -> None:
    """The whole point: a project driven by two agents is driven by them again tomorrow."""
    Settings(tmp_path).remember(
        "rlar",
        {
            "actor": Runs("claude/claude-opus-5:high"),
            "reviewer": Runs("codex/gpt-5.6-sol:xhigh"),
        },
    )

    # A second one, as opening the interface again is.
    again = Settings(tmp_path)
    assert again.flow == "rlar"
    assert again.agents("rlar") == {
        "actor": Runs("claude/claude-opus-5:high"),
        "reviewer": Runs("codex/gpt-5.6-sol:xhigh"),
    }


def test_an_agent_is_kept_under_its_role_as_the_word_a_command_line_takes(
    tmp_path: Path,
) -> None:
    """So that a flow which grows a role does not hand the reviewer's model to the builder.

    And written as `-a` writes it after the role, so what the menu keeps and what a command
    line says are one word: the account after an `@`, and a model holding slashes of its own
    surviving the round trip.
    """
    Settings(tmp_path).remember(
        "rlar",
        {"actor": Runs("claude/m:high", "work"), "reviewer": Runs("codex/n:low")},
    )
    Settings(tmp_path).remember("chat", {"assistant": Runs("kimi/kimi-code/k3:max")})

    held = yaml.safe_load((home() / "settings.yaml").read_text())
    flows = held["workspaces"][str(tmp_path.resolve())]["flows"]

    assert flows["rlar"]["agents"] == {
        "actor": "claude@work/m:high",
        "reviewer": "codex/n:low",
    }
    assert flows["chat"]["agents"] == {"assistant": "kimi/kimi-code/k3:max"}
    assert Settings(tmp_path).agents("chat") == {
        "assistant": Runs("kimi/kimi-code/k3:max")
    }
    assert Settings(tmp_path).agents("rlar")["actor"] == Runs("claude/m:high", "work")


def test_each_flow_of_a_workspace_is_kept_beside_the_others(tmp_path: Path) -> None:
    """What an agent runs only means anything against the flow that drives it."""
    kept = Settings(tmp_path)
    kept.remember("chat", {"assistant": Runs("claude/m:high")})
    kept.remember("ralph_loop", {"coder": Runs("codex/n:low")})

    again = Settings(tmp_path)
    assert again.flow == "ralph_loop"  # the one it was last run with
    # And the other is still there.
    assert again.agents("chat") == {"assistant": Runs("claude/m:high")}
    assert again.agents("ralph_loop") == {"coder": Runs("codex/n:low")}


def test_one_workspace_does_not_take_anothers(tmp_path: Path) -> None:
    (mine := tmp_path / "mine").mkdir()
    (theirs := tmp_path / "theirs").mkdir()
    Settings(mine).remember("chat", {"assistant": Runs("claude/m:high")})

    Settings(theirs).remember(
        "rlar", {"a": Runs("codex/n:low"), "b": Runs("codex/n:low")}
    )

    assert Settings(mine).flow == "chat"
    assert Settings(mine).agents("chat") == {"assistant": Runs("claude/m:high")}


@pytest.mark.parametrize(
    "written",
    ["", "not: a mapping of workspaces\n", "[]\n", ": : :\n", "workspaces: 3\n"],
)
def test_a_file_that_is_not_one_is_a_workspace_with_nothing_remembered(
    tmp_path: Path, written: str
) -> None:
    """Never a reason not to open: what it holds is a convenience and not a requirement."""
    home().mkdir(parents=True, exist_ok=True)
    (home() / "settings.yaml").write_text(written)

    kept = Settings(tmp_path)

    assert kept.flow == ""
    assert kept.agents("chat") == {}
    # And it is written over rather than kept.
    kept.remember("chat", {"assistant": Runs("claude/m:high")})
    assert Settings(tmp_path).agents("chat") == {"assistant": Runs("claude/m:high")}


def test_an_agent_an_older_humanize_wrote_down_reads_as_nothing_remembered(
    tmp_path: Path,
) -> None:
    """One written as the fields it had then is a flow to be asked about again.

    Rather than half an answer -- which role it was for is the half this cannot guess.
    """
    Settings(tmp_path).remember("rlar", {"actor": Runs("claude/m:high")})
    where = home() / "settings.yaml"
    held = yaml.safe_load(where.read_text())
    held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"] = {
        "actor": {"cli": "claude", "model": "m", "effort": "high", "goals": True}
    }
    where.write_text(yaml.safe_dump(held, sort_keys=False))

    assert Settings(tmp_path).agents("rlar") == {}


def test_a_home_that_cannot_be_written_is_not_a_reason_to_stop(tmp_path: Path) -> None:
    """An interface that refused to run because it could not remember would be worse."""
    home().mkdir(parents=True, exist_ok=True)
    home().chmod(0o500)
    try:
        Settings(tmp_path).remember("chat", {"assistant": Runs("claude/m:high")})
    finally:
        home().chmod(0o700)


def test_where_an_environment_is_kept_beside_what_the_agents_run(
    tmp_path: Path,
) -> None:
    """So that a project driven on a machine of its own is driven on it again tomorrow."""
    Settings(tmp_path).remember(
        "rlar",
        {"actor": Runs("claude/m:high")},
        {"repo": "ssh@box/home/me/repo"},
    )

    held = yaml.safe_load((home() / "settings.yaml").read_text())
    flows = held["workspaces"][str(tmp_path.resolve())]["flows"]
    assert flows["rlar"]["envs"] == {"repo": "ssh@box/home/me/repo"}
    assert Settings(tmp_path).envs("rlar") == {"repo": "ssh@box/home/me/repo"}

    # Choosing the agents again says nothing about where they work, so it changes nothing.
    Settings(tmp_path).remember("rlar", {"actor": Runs("codex/n:low")})
    assert Settings(tmp_path).envs("rlar") == {"repo": "ssh@box/home/me/repo"}

    # And an empty one is the way to say none, which erases it.
    Settings(tmp_path).remember("rlar", {"actor": Runs("codex/n:low")}, {})
    assert Settings(tmp_path).envs("rlar") == {}


def test_how_a_flow_was_set_up_is_kept_beside_what_its_agents_run(
    tmp_path: Path,
) -> None:
    """A flow of twenty params is not one to answer again every morning."""
    Settings(tmp_path).remember(
        "humanize1",
        {"builder": Runs("claude/m:high")},
        params={"max": 12, "rlcr": True},
    )

    again = Settings(tmp_path)
    assert again.params("humanize1") == {"max": 12, "rlcr": True}
    held = yaml.safe_load((home() / "settings.yaml").read_text())
    flows = held["workspaces"][str(tmp_path.resolve())]["flows"]
    assert flows["humanize1"]["params"] == {"max": 12, "rlcr": True}


def test_choosing_the_agents_again_is_not_a_way_of_forgetting_the_params(
    tmp_path: Path,
) -> None:
    """Choosing the agents says nothing about how the flow itself was set up."""
    Settings(tmp_path).remember(
        "humanize1", {"builder": Runs("claude/m:high")}, params={"max": 12}
    )

    Settings(tmp_path).remember("humanize1", {"builder": Runs("codex/n:low")})

    assert Settings(tmp_path).params("humanize1") == {"max": 12}


def test_a_flow_that_takes_no_setting_up_keeps_nothing(tmp_path: Path) -> None:
    """Which is most of them, and is what a settings file written before this also says."""
    Settings(tmp_path).remember("chat", {"assistant": Runs("claude/m:high")})

    assert Settings(tmp_path).params("chat") == {}
    assert Settings(tmp_path).envs("chat") == {}
    assert Settings(tmp_path).budget("chat") == {}


def test_what_a_run_of_a_flow_may_spend_is_kept_beside_how_it_was_set_up(
    tmp_path: Path,
) -> None:
    """Beside the params and not inside them: it is a setting of the run, not of the flow."""
    spends = {
        "duration": "PT6H",
        "cost": None,
        "output_tokens": 10_000,
        "graceful": True,
    }
    Settings(tmp_path).remember(
        "ralph_loop",
        {"coder": Runs("claude/m:high")},
        params={"rounds": 12},
        budget=spends,
    )

    again = Settings(tmp_path)
    assert again.budget("ralph_loop") == spends
    assert again.params("ralph_loop") == {"rounds": 12}
    held = yaml.safe_load((home() / "settings.yaml").read_text())
    flows = held["workspaces"][str(tmp_path.resolve())]["flows"]
    assert flows["ralph_loop"]["budget"]["duration"] == "PT6H"


def test_choosing_the_agents_again_is_not_a_way_of_forgetting_the_budget(
    tmp_path: Path,
) -> None:
    """The flow's whole entry is replaced, so what is not handed in has to be read back."""
    Settings(tmp_path).remember(
        "ralph_loop", {"coder": Runs("claude/m:high")}, budget={"cost": 6.0}
    )

    Settings(tmp_path).remember("ralph_loop", {"coder": Runs("codex/n:low")})

    assert Settings(tmp_path).budget("ralph_loop") == {"cost": 6.0}


def test_a_budget_of_nothing_is_forgotten(tmp_path: Path) -> None:
    """Which is how the menu says a run is no longer held to what was set here."""
    Settings(tmp_path).remember(
        "ralph_loop", {"coder": Runs("claude/m:high")}, budget={"cost": 6.0}
    )

    Settings(tmp_path).remember(
        "ralph_loop", {"coder": Runs("claude/m:high")}, budget={}
    )

    assert Settings(tmp_path).budget("ralph_loop") == {}


def test_two_flows_of_one_name_are_two_entries(tmp_path: Path) -> None:
    """A flow of yours is called by its path, so it cannot inherit a built-in's setup."""
    Settings(tmp_path).remember(
        "rlar", {"actor": Runs("claude/m:high")}, params={"deep": True}
    )
    Settings(tmp_path).remember(
        ".humanize/flows/rlar.py",
        {"actor": Runs("codex/n:low")},
        params={"deep": False},
    )

    kept = Settings(tmp_path)
    assert kept.params("rlar") == {"deep": True}
    assert kept.params(".humanize/flows/rlar.py") == {"deep": False}
    assert kept.agents("rlar") == {"actor": Runs("claude/m:high")}


@pytest.mark.timeout(60)
async def test_the_first_start_asks_whether_humanize_reports_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asked once, with what it means beside it, and answered for every project after that."""
    from hmz.runtime import telemetry
    from hmz.tui import Humanize
    from hmz.tui.pick import Reports

    monkeypatch.delenv(telemetry.SAYS, raising=False)
    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        await until(lambda: isinstance(app.screen, Reports), driver)
        said = str(app.screen.query_one("#about", Label).content)
        # What goes and what does not, both, where the question is asked.
        assert "reports to help fix bugs" in said
        assert "nothing you typed" in said
        # The answer that helps is the one the cursor opens on.
        listing = app.screen.query_one("#choices", OptionList)
        assert [str(one.id) for one in listing.options] == ["=on", "=off"]

        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Reports), driver)

    assert Settings(tmp_path).enable_sentry is True


@pytest.mark.timeout(60)
async def test_walking_away_from_the_question_is_being_asked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silence is not a no and is not a yes: it is a question still to ask."""
    from hmz.runtime import telemetry
    from hmz.tui import Humanize
    from hmz.tui.pick import Reports

    monkeypatch.delenv(telemetry.SAYS, raising=False)
    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        await until(lambda: isinstance(app.screen, Reports), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Reports), driver)

    assert Settings(tmp_path).enable_sentry is None


@pytest.mark.timeout(60)
async def test_a_machine_that_has_answered_is_not_asked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.runtime import telemetry
    from hmz.tui import Humanize
    from hmz.tui.pick import Reports

    monkeypatch.delenv(telemetry.SAYS, raising=False)
    monkeypatch.chdir(tmp_path)
    Settings(tmp_path).answers(enable_sentry=False)
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert not isinstance(app.screen, Reports)


@pytest.mark.timeout(60)
async def test_the_settings_menu_turns_the_reporting_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One page for what is true of this machine, one for what this directory is set up as."""
    from hmz.runtime.kept import Runs
    from hmz.tui import Humanize
    from hmz.tui.pick import _SAVE, Confirms
    from hmz.tui.settings import Adjusts
    from tests.integration.tui.test_app import bar, ids, into_settings, onto, picks

    monkeypatch.chdir(tmp_path)
    Settings(tmp_path).answers(enable_sentry=True)
    Settings(tmp_path).remember("chat", {"assistant": Runs("claude/m:high")})
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        listing = sheet.query_one("#choices", OptionList)
        assert ids(app) == ["reports", "sent", "details", "btw"]
        # Saved from the bar under the list rather than from a row of it.
        assert _SAVE in bar(app)
        assert "● on" in str(listing.get_option_at_index(0).prompt)

        await picks(app, driver, "reports", "off")
        assert "○ off" in str(listing.get_option_at_index(0).prompt)
        assert sheet._changed

        # The other page, by way of the screen of them all: this directory.
        await driver.press("escape")
        await until(lambda: sheet._home, driver)
        await onto(app, driver, "workspace")
        await driver.press("enter")
        await until(lambda: not sheet._home and sheet._tab == 1, driver)
        assert ids(app) == ["workspace", "flow", "profile", "forget"]
        assert "chat" in str(listing.get_option_at_index(1).prompt)

        await driver.press("escape")
        await until(lambda: sheet._home, driver)
        await driver.press("escape")
        # Nothing lands until saving is confirmed, as on every other menu.
        await until(lambda: isinstance(app.screen, Confirms), driver)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Adjusts), driver)
        await driver.pause()

    assert Settings(tmp_path).enable_sentry is False
    assert Settings(tmp_path).flow == "chat"  # and the second page was not touched


@pytest.mark.timeout(60)
async def test_a_value_is_picked_from_the_list_dropped_under_it_with_the_mouse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A click drops the values, a click picks one, and the save button lands it."""
    from hmz.tui import Humanize
    from hmz.tui.dropdown import Dropdown
    from hmz.tui.pick import _SAVE
    from hmz.tui.settings import Adjusts
    from tests.integration.tui.test_app import acts, into_settings

    monkeypatch.chdir(tmp_path)
    assert not Settings(tmp_path).details
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        await into_settings(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        listing = sheet.query_one("#choices", OptionList)

        # Details is the third row: two lines and a rule apiece, under the list's border.
        await driver.click("#choices", offset=(4, 1 + 3 * 2))
        await until(lambda: isinstance(app.screen, Dropdown), driver)
        dropped = app.screen
        values = dropped.query_one(OptionList)
        assert [str(one.id) for one in values.options] == ["=on", "=off"]
        # A switch opens on the answer it is not, so that enter twice turns it round.
        assert values.highlighted == 0

        # A click off the list takes nothing.
        await driver.click(offset=(1, 1))
        await until(lambda: app.screen is sheet, driver)
        assert not sheet._details
        assert not sheet._changed

        await driver.click("#choices", offset=(4, 1 + 3 * 2))
        await until(lambda: isinstance(app.screen, Dropdown), driver)
        await driver.click(app.screen.query_one(OptionList), offset=(2, 1))
        await until(lambda: app.screen is sheet, driver)
        assert sheet._details
        assert "● on" in str(listing.get_option_at_index(2).prompt)
        # Held, and not yet written down.
        assert not Settings(tmp_path).details

        await acts(app, driver, _SAVE)
        await until(lambda: not isinstance(app.screen, Adjusts), driver)

    assert Settings(tmp_path).details


@pytest.mark.timeout(60)
async def test_whether_a_run_here_is_profiled_is_a_row_of_this_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workspace's own: what a run costs in processes is a thing about the project.

    Off unless somebody says otherwise, since it is a sampler running for as long as the flow
    does -- and landing when the menu is saved, as everything on it does.
    """
    from hmz.tui import Humanize
    from hmz.tui.pick import Confirms
    from hmz.tui.settings import Adjusts
    from tests.integration.tui.test_app import into_settings, picks

    monkeypatch.chdir(tmp_path)
    assert not Settings(tmp_path).profiling
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, 1)
        listing = app.screen.query_one("#choices", OptionList)

        await picks(app, driver, "profile", "on")
        assert "● on" in str(listing.get_option_at_index(2).prompt)

        # Held until the menu is saved, exactly as everything else on it is.
        assert not Settings(tmp_path).profiling
        # Read as a run starts, so the row says when it lands while it is held.
        assert "takes effect on next flow run" in str(
            listing.get_option_at_index(2).prompt
        )
        await driver.press("escape", "escape")
        await until(lambda: isinstance(app.screen, Confirms), driver)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Adjusts), driver)
        await driver.pause()

        # And the transcript says it again once it is saved.
        assert "from the next flow run" in transcript(app)

    assert Settings(tmp_path).profiling


def test_whether_the_working_is_shown_is_remembered_for_the_machine(
    tmp_path: Path,
) -> None:
    """Off until somebody says otherwise, and the same answer in every workspace."""
    (mine := tmp_path / "mine").mkdir()
    (theirs := tmp_path / "theirs").mkdir()
    assert not Settings(mine).details

    Settings(mine).detailing(on=True)

    assert Settings(theirs).details
    held = yaml.safe_load((home() / "settings.yaml").read_text())
    assert held["details"] is True


def test_settings_offers_its_pages_by_name() -> None:
    """The word typed after `/settings` is the word on the card, offered as it is typed."""
    from hmz.tui.app import _BY_NAME, _COMMANDS
    from hmz.tui.complete import offered

    assert _BY_NAME["settings"].takes == "[page]"
    assert offered("/settings ", _COMMANDS) == [
        "settings",
        "workspace",
        "accounts",
        "environments",
        "fallback",
        "flowverses",
    ]
    assert offered("/settings ac", _COMMANDS) == ["accounts"]
    assert offered("/settings env", _COMMANDS) == ["environments"]
    # Written out in full, so enter over the list sends the line.
    assert offered("/settings accounts", _COMMANDS) == []
    assert offered("/settings accounts x", _COMMANDS) == []


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    ("page", "tab"),
    [
        ("settings", 0),
        ("workspace", 1),
        # And by the names they had, which fingers still know.
        ("everywhere", 0),
        ("directory", 1),
        ("Accounts", 2),
        ("environments", 3),
        ("fallback", 4),
    ],
)
async def test_settings_opens_straight_onto_the_page_it_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, page: str, tab: int
) -> None:
    """The page somebody came for is not three presses of an arrow away."""
    from hmz.tui import Humanize
    from hmz.tui.settings import Adjusts

    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*f"/settings {page}")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Adjusts), driver)

        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        assert sheet._tab == tab
        assert not sheet._home

        # And esc comes out onto the screen of them all rather than leaving.
        await driver.press("escape")
        await until(lambda: sheet._home, driver)
        assert isinstance(app.screen, Adjusts)


@pytest.mark.timeout(60)
async def test_a_page_settings_does_not_have_is_said_and_opens_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.tui import Humanize
    from hmz.tui.settings import Adjusts

    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/settings nosuch")
        await driver.press("enter")
        await until(lambda: "no page 'nosuch'" in transcript(app), driver)

        assert not isinstance(app.screen, Adjusts)
        assert "accounts" in transcript(app)


@pytest.mark.timeout(60)
async def test_what_a_page_said_is_still_said_when_it_is_turned_back_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A look at another page is not a reason to lose what became of something on this one."""
    from hmz.tui import Humanize
    from hmz.tui.settings import Adjusts

    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/settings accounts")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        sheet._said = "something happened here"
        sheet._fill()

        await driver.press("escape")
        await until(lambda: sheet._home, driver)
        await driver.press("down", "enter")
        await until(lambda: sheet._tab == 3 and not sheet._home, driver)
        assert "something happened here" not in str(
            sheet.query_one("#tuning", Label).content
        )
        await driver.press("escape")
        await until(lambda: sheet._home, driver)
        await driver.press("up", "enter")
        await until(lambda: sheet._tab == 2 and not sheet._home, driver)

        assert "something happened here" in str(
            sheet.query_one("#tuning", Label).content
        )


@pytest.mark.timeout(60)
async def test_a_switch_turned_back_to_where_it_was_holds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing to save, so no badge, no save button to press and no question on the way out."""
    from hmz.tui import Humanize
    from hmz.tui.settings import Adjusts
    from tests.integration.tui.test_app import into_settings, picks

    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        await picks(app, driver, "details", "on")
        assert "unsaved" in str(sheet.query_one("#pending", Label).content)
        await picks(app, driver, "details", "off")
        assert not str(sheet.query_one("#pending", Label).content)
        assert sheet.query_one("#act-save").disabled

        await driver.press("escape", "escape")
        await until(lambda: not isinstance(app.screen, Adjusts), driver)
