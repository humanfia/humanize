"""`hmz.tui.own`: what the interface keeps of its own, and how it tells the system of a notice."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.tui import own
from hmz.tui.own import Kept

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import App


class _Settings:
    """`hmz.coganchor.settings`, as much of it as is asked: one mapping, read and changed."""

    def __init__(self) -> None:
        self.held: dict[str, Any] = {}
        self.fails = False

    def read(self) -> dict[str, Any]:
        return dict(self.held)

    def changes(self, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        if self.fails:
            raise OSError("read-only")
        change(self.held)
        return dict(self.held)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> _Settings:
    held = _Settings()
    monkeypatch.setattr(own, "settings", held)
    return held


@pytest.mark.parametrize(
    ("kept", "looks"),
    [
        (Kept(), "humanize"),
        (Kept(appearance="light"), "humanfia-light"),
        (Kept(appearance="dark"), "humanfia-dark"),
        (Kept(appearance="terminal"), "terminal"),
        (Kept(theme="critical-teal"), "critical-teal"),
        (Kept(theme="critical-teal", appearance="dark"), "critical-teal-dark"),
        (Kept(theme="critical-teal", appearance="terminal"), "terminal"),
    ],
)
def test_what_is_kept_is_said_as_the_theme_chooser_takes_it(
    kept: Kept, looks: str
) -> None:
    assert kept.looks() == looks


@pytest.mark.parametrize(
    ("language", "environ", "speaks"),
    [
        ("", {}, "en"),
        ("", {"LANG": "zh_CN.UTF-8"}, "zh_CN.UTF-8"),
        ("", {"LANG": "en_US.UTF-8", "LC_MESSAGES": "zh_TW"}, "zh_TW"),
        ("", {"LANG": "zh_CN", "LC_MESSAGES": "zh_TW", "LC_ALL": "C"}, "C"),
        ("", {"LC_ALL": "", "LANG": "zh_CN"}, "zh_CN"),
        ("zh-Hant", {"LC_ALL": "en_US.UTF-8"}, "zh-Hant"),
    ],
)
def test_the_language_is_the_one_kept_or_else_the_systems(
    language: str, environ: dict[str, str], speaks: str
) -> None:
    assert Kept(language=language).speaks(environ) == speaks


def test_nothing_written_is_every_default(settings: _Settings) -> None:
    del settings
    assert own.read() == Kept("humanize", "auto", "")


def test_what_is_chosen_is_kept_under_tui_and_the_rest_left(
    settings: _Settings,
) -> None:
    settings.held["details"] = True

    assert own.keep(theme="devoted-pink") == Kept("devoted-pink", "auto", "")
    assert own.keep(language="zh-Hans") == Kept("devoted-pink", "auto", "zh-Hans")
    assert own.keep(appearance="light", language="") == Kept(
        "devoted-pink", "light", ""
    )

    assert settings.held == {
        "details": True,
        "tui": {"theme": "devoted-pink", "appearance": "light", "language": ""},
    }
    assert own.read() == Kept("devoted-pink", "light", "")


def test_what_else_is_under_the_key_is_left_beside_what_is_kept(
    settings: _Settings,
) -> None:
    settings.held["tui"] = {"theme": "devoted-pink", "somebody": "else's"}

    assert own.keep(appearance="dark") == Kept("devoted-pink", "dark", "")

    assert settings.held["tui"] == {
        "theme": "devoted-pink",
        "appearance": "dark",
        "language": "",
        "somebody": "else's",
    }


def test_what_is_kept_and_not_known_is_read_as_not_there(settings: _Settings) -> None:
    settings.held["tui"] = {"theme": "gone", "appearance": 3, "language": "tlh"}
    assert own.read() == Kept()

    settings.held["tui"] = "dark"
    assert own.read() == Kept()


def test_what_cannot_be_written_is_kept_for_as_long_as_this_runs(
    settings: _Settings,
) -> None:
    settings.fails = True

    assert own.keep(theme="surviving-jade") == Kept(theme="surviving-jade")
    assert own.keep(language="zh-Hans") == Kept("surviving-jade", "auto", "zh-Hans")

    assert settings.held == {}
    assert own.read() == Kept("surviving-jade", "auto", "zh-Hans")

    # Written once it can be, with what was only held until then.
    settings.fails = False
    assert own.keep(appearance="dark") == Kept("surviving-jade", "dark", "zh-Hans")
    assert own.read() == Kept("surviving-jade", "dark", "zh-Hans")
    assert settings.held["tui"]["theme"] == "surviving-jade"


@pytest.mark.parametrize(
    ("environ", "name"),
    [
        ({}, ""),
        ({"TEXTUAL_THEME": "nord"}, "TEXTUAL_THEME"),
        ({"TEXTUAL_THEME": "gone"}, ""),
        ({"NO_COLOR": "1"}, "NO_COLOR"),
        ({"NO_COLOR": ""}, ""),
        ({"TEXTUAL_THEME": "nord", "NO_COLOR": "1"}, "TEXTUAL_THEME"),
        ({"TEXTUAL_THEME": "gone", "NO_COLOR": "1"}, "NO_COLOR"),
    ],
)
def test_which_variable_decides_the_theme(environ: dict[str, str], name: str) -> None:
    assert own.overridden(environ, {"nord": 0}) == name
    assert set(own.OVERRIDES) == {"TEXTUAL_THEME", "NO_COLOR"}


@pytest.mark.parametrize(
    ("reports", "focused", "told"),
    [(False, True, True), (True, True, False), (True, False, True)],
)
def test_the_system_is_told_unless_the_terminal_says_it_is_looked_at(
    *, reports: bool, focused: bool, told: bool
) -> None:
    assert own.wanted(reports=reports, focused=focused) is told


@pytest.mark.parametrize(
    "environ",
    [
        {"TERM_PROGRAM": "iTerm.app"},
        {"TERM_PROGRAM": "ghostty"},
        {"TERM_PROGRAM": "WezTerm"},
        {"TERM": "xterm-kitty"},
        {"WT_SESSION": "0a1b"},
    ],
)
def test_a_terminal_that_shows_osc_9_is_written_it_alone(
    environ: dict[str, str],
) -> None:
    assert own.sequence(environ, "hmz: Done", "chat") == "\x1b]9;hmz: Done: chat\x07"


@pytest.mark.parametrize(
    "environ", [{"VTE_VERSION": "7600"}, {"TERM": "foot"}, {"TERM": "rxvt-unicode"}]
)
def test_a_terminal_that_takes_osc_777_is_written_it_alone(
    environ: dict[str, str],
) -> None:
    said = own.sequence(environ, "hmz: Done", "ralph; elsewhere")

    assert said == "\x1b]777;notify;hmz: Done;ralph, elsewhere\x07"


def test_any_other_terminal_is_rung_and_written_osc_9_which_it_may_ignore() -> None:
    said = own.sequence({"TERM": "xterm-256color"}, "hmz: Failed", "")

    assert said == "\x07\x1b]9;hmz: Failed\x07"


@pytest.mark.parametrize(
    "within", [{"TMUX": "/tmp/tmux-0/default,1,0"}, {"STY": "1.pts"}, {"TERM": "tmux"}]
)
def test_inside_tmux_or_screen_the_bell_is_rung_whatever_is_outside(
    within: dict[str, str],
) -> None:
    environ = {"VTE_VERSION": "7600", "TERM_PROGRAM": "iTerm.app", **within}

    assert own.sequence(environ, "hmz: Done", "") == "\x07\x1b]9;hmz: Done\x07"


def test_nothing_an_agent_wrote_ends_the_sequence_early() -> None:
    said = own.sequence(
        {"TERM_PROGRAM": "ghostty"}, "hmz: Done", "a\x07b\x1b]0;c\n\x9cd"
    )

    assert said == "\x1b]9;hmz: Done: a b ]0;c  d\x07"


class _Driver:
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, said: str) -> None:
        self.written.append(said)


class _Interface:
    """As much of an interface as telling asks of one, and what its terminal was written."""

    def __init__(self, *, headless: bool = False) -> None:
        self._driver = _Driver()
        self.is_headless = headless
        self.app_focus = True
        self.watched: list[Callable[[], None]] = []

    def watch(
        self, _obj: object, name: str, callback: Callable[[], None], *, init: bool
    ) -> None:
        assert (name, init) == ("app_focus", False)
        self.watched.append(callback)

    def says(self, *, focused: bool) -> None:
        """The terminal says whether it is looked at, as it does when that changes."""
        self.app_focus = focused
        for callback in self.watched:
            callback()

    @property
    def written(self) -> list[str]:
        return self._driver.written


def test_a_notice_is_written_to_the_terminal() -> None:
    app = _Interface()

    told = own.tells(
        cast("App[Any]", app), {"TERM_PROGRAM": "ghostty"}, "hmz: Done", "x"
    )

    assert told
    assert app.written == ["\x1b]9;hmz: Done: x\x07"]


def test_no_notice_is_written_with_no_terminal_to_write_to() -> None:
    app = _Interface(headless=True)

    assert not own.tells(cast("App[Any]", app), {}, "hmz: Done", "x")
    assert app.written == []


def test_no_notice_is_written_while_the_terminal_says_it_is_looked_at() -> None:
    app = _Interface()
    showing = cast("App[Any]", app)
    own.hears_focus(showing)
    environ = {"TERM_PROGRAM": "ghostty"}

    # It has said nothing yet: one that never does is told every notice.
    assert own.tells(showing, environ, "hmz: Done", "one")
    app.says(focused=False)
    assert own.tells(showing, environ, "hmz: Done", "two")
    app.says(focused=True)
    assert not own.tells(showing, environ, "hmz: Done", "three")

    assert app.written == ["\x1b]9;hmz: Done: one\x07", "\x1b]9;hmz: Done: two\x07"]
