"""`hmz.tui.app`: the interface as it stands before it is mounted, with nothing running."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from unittest import mock

import pytest
from textual.app import App
from textual.binding import Binding

from hmz.tui import app
from hmz.tui.app import Editor, Humanize
from hmz.tui.history import History

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class _Opened:
    """What the interface asked of everything around it while it opened."""

    settings: mock.MagicMock
    declared: list[str] = field(default_factory=list[str])


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> _Opened:
    """`hmz.daemon`, the flows and the agents, as the interface finds them, all stood in for."""
    settings = mock.MagicMock(details=False, flow="", btw="")
    settings.agents.return_value = {}
    settings.envs.return_value = {}
    settings.params.return_value = {}
    settings.profile.return_value = False
    held = _Opened(settings)

    def declared_of(flow: str) -> None:
        held.declared.append(flow)

    # Nothing installed here, and nothing to add.
    hmz = mock.MagicMock(settings=settings)
    hmz.installed.return_value = {}
    hmz.installable.return_value = {}
    monkeypatch.setattr(app, "Hmz", lambda: hmz)
    monkeypatch.setattr(app, "declared_of", declared_of)

    def nothing(*_: object) -> None:
        """No params and no budget, as a flow that takes neither has."""

    monkeypatch.setattr(app, "params_of", nothing)
    monkeypatch.setattr(app, "budget_of", nothing)
    monkeypatch.delenv("TEXTUAL_THEME", raising=False)
    return held


@pytest.fixture
def humanize(opened: _Opened) -> Humanize:
    return Humanize()


def test_the_interface_is_an_app_without_a_command_palette() -> None:
    assert issubclass(Humanize, App)
    assert Humanize.ENABLE_COMMAND_PALETTE is False


@pytest.mark.parametrize(
    ("key", "action"),
    [("ctrl+c", "interrupt"), ("ctrl+q", "exit"), ("left", "monitor")],
)
def test_its_own_keys_are_bound(key: str, action: str) -> None:
    bound = [one for one in Humanize.BINDINGS if isinstance(one, Binding)]

    assert any((one.key, one.action) == (key, action) for one in bound)


def test_it_opens_on_what_this_workspace_was_last_set_up_to_run(
    opened: _Opened,
) -> None:
    opened.settings.flow = "rlar"

    humanize = Humanize()

    assert opened.declared == ["rlar"]
    opened.settings.agents.assert_called_once_with("rlar")
    assert humanize.settings is opened.settings


def test_with_nothing_remembered_it_opens_on_chat(opened: _Opened) -> None:
    Humanize()

    assert opened.declared == ["chat"]


def test_a_flow_and_agents_handed_over_win_over_what_was_remembered(
    opened: _Opened,
) -> None:
    opened.settings.flow = "rlar"

    Humanize(flow="review", agents={})

    assert opened.declared == ["review"]
    opened.settings.agents.assert_not_called()
    opened.settings.envs.assert_called_once_with("review")


def test_it_keeps_what_was_typed_here_before(humanize: Humanize) -> None:
    assert isinstance(humanize.history, History)


@pytest.mark.parametrize(
    ("asked", "theme"),
    [(None, "terminal"), ("nord", "nord"), ("no-such-theme", "terminal")],
)
def test_it_is_drawn_in_the_terminals_colours_unless_asked_otherwise(
    opened: _Opened, monkeypatch: pytest.MonkeyPatch, asked: str | None, theme: str
) -> None:
    if asked is not None:
        monkeypatch.setenv("TEXTUAL_THEME", asked)

    assert Humanize().theme == theme


@pytest.mark.parametrize(
    ("ask", "answer"),
    [
        (Humanize.flow_running, False),
        (Humanize.held_apart, True),
        (Humanize.nothing_to_resume, False),
        (Humanize.in_btw, False),
        (Humanize.leaves_btw, False),
        (Humanize.refused_stop, "no flow is running"),
        (Humanize.refused_resume, ""),
    ],
)
def test_with_nothing_running_the_command_table_reads_as_much(
    humanize: Humanize, ask: Callable[[Humanize], object], answer: object
) -> None:
    assert ask(humanize) == answer


@pytest.mark.parametrize("action", ["flow", "settings", "stop", "interrupt"])
def test_keys_that_mean_the_same_anywhere_are_always_live(
    humanize: Humanize, action: str
) -> None:
    assert humanize.check_action(action, ()) is True


def test_what_was_sent_is_carried_by_the_message() -> None:
    assert Editor.Sent("fix the bug").text == "fix the bug"


def test_the_editor_sends_on_enter_and_breaks_the_line_on_shift_enter() -> None:
    bound = {
        (one.key, one.action) for one in Editor.BINDINGS if isinstance(one, Binding)
    }

    assert ("enter", "send") in bound
    assert ("shift+enter", "newline") in bound
    assert ("ctrl+j", "newline") in bound
