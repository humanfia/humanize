"""`hmz` with no command: where the runs it opens on are held, and what it opens on them.

A line naming no command opens the interface in this process, as one more frontend of the runs
a host holds for this directory -- the host already there, or one started now -- so that
closing the terminal is not what ends a day's work. With no terminal to walk away from --
output going to a file, this suite driving the interface itself -- the runs are held in this
process instead, exactly as they always were.
"""

from __future__ import annotations

import os
import unittest.mock
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli, daemon
from hmz.daemon import Link

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class Stands:
    """The interface as `opens` makes it: what it was handed, and what it was reading."""

    made: dict[str, Any]
    status: dict[str, Any]
    return_code = 0

    def __init__(self, **said: Any) -> None:
        type(self).made = said

    def run(self) -> None:
        link = type(self).made.get("link")
        if isinstance(link, Link):
            found = daemon.running()
            type(self).status = found.status() if found is not None else {}
            link.close()


@pytest.fixture
def terminal(_humanize_home: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Says runs may be held here, which this suite otherwise says of nothing.

    Both halves of the question: the suite turns the holding off outright, and there is no
    terminal on either end of a process pytest is capturing. Named after the fixture that
    turned it off, so that this runs after rather than before it.
    """
    monkeypatch.delenv(cli.APART, raising=False)
    monkeypatch.setattr(cli, "_at_a_terminal", lambda: True)


@pytest.fixture
def standing(monkeypatch: pytest.MonkeyPatch) -> type[Stands]:
    """The interface, stood in for by one that says what it was opened on."""
    Stands.made, Stands.status = {}, {}
    monkeypatch.setattr("hmz.tui.Humanize", Stands)
    return Stands


@pytest.fixture
def hosts(workspace: Path) -> Iterator[None]:
    """Whatever host a test started here, gone again however the test ended."""
    del workspace
    try:
        yield
    finally:
        found = daemon.running()
        if found is not None and found.protocol and found.alive:
            found.kill()


def test_with_no_terminal_the_interface_opens_on_runs_held_here(
    workspace: Path,
) -> None:
    """Which is what a suite driving it is, and what output going to a file is."""
    with unittest.mock.patch("hmz.tui.Humanize.run") as opened:
        assert cli.main([]) == 0

    assert opened.called
    assert daemon.running() is None


def test_the_environment_says_the_same_thing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, standing: type[Stands]
) -> None:
    """For a scripted install and for this suite, which is what sets it."""
    monkeypatch.setattr(cli, "_at_a_terminal", lambda: True)
    monkeypatch.setenv(cli.APART, "off")
    assert not cli._apart_is_wanted()
    assert cli.opens() == 0
    assert standing.made == {}  # opened on runs of its own, with no link handed over
    assert daemon.running() is None

    monkeypatch.setenv(cli.APART, "")
    assert cli._apart_is_wanted()


@pytest.mark.timeout(90)
def test_with_a_terminal_a_host_is_started_and_read_as_one_more_frontend(
    workspace: Path, terminal: None, standing: type[Stands], hosts: None
) -> None:
    """In this process: the runs are the host's, and the interface is a frontend of them."""
    assert cli.main([]) == 0

    assert set(standing.made) == {
        "link"
    }  # and nothing else: a line cannot name the rest
    assert isinstance(standing.made["link"], Link)
    clients = standing.status["clients"]
    assert [one["kind"] for one in clients] == ["tui"]
    assert standing.status["kind"] == "host"


@pytest.mark.timeout(90)
def test_a_host_already_holding_the_runs_here_is_the_one_read(
    held: daemon.Daemon, terminal: None, standing: type[Stands]
) -> None:
    """Rather than a second host of the same directory, which is two runs over one epic."""
    with unittest.mock.patch.object(
        daemon, "host", side_effect=AssertionError("started again")
    ):
        assert cli.main([]) == 0

    assert standing.status["pid"] == held.pid


def test_runs_held_by_an_older_humanize_are_said_to_be_and_left_alone(
    older: daemon.Daemon,
    terminal: None,
    standing: type[Stands],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing here can read them, and a host beside them would fight over the directory."""
    with unittest.mock.patch.object(
        daemon, "host", side_effect=AssertionError("started beside it")
    ):
        assert cli.main([]) == 1

    assert standing.made == {}
    said = capsys.readouterr().err
    assert "older humanize" in said
    assert "stop it with that version" in said


def test_runs_that_cannot_be_held_apart_are_held_here_instead(
    workspace: Path,
    terminal: None,
    standing: type[Stands],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """What is lost is walking away from them, which is not a reason to refuse to open."""
    with unittest.mock.patch.object(
        daemon, "host", side_effect=OSError("no forking here")
    ):
        assert cli.main([]) == 0

    assert standing.made == {}  # opened on runs of its own, in this process
    said = capsys.readouterr().err
    assert "cannot be held apart from the terminal" in said
    assert "no forking here" in said


def test_the_interface_is_opened_on_a_terminal_prepared_for_it(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, standing: type[Stands]
) -> None:
    """The iTerm2 opt-out is read by Textual as it is imported, so it is set before that.

    An interface opened without it pushes the keyboard protocol that loses IME-composed text
    at the very terminal that cannot take it.
    """
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TEXTUAL_DISABLE_KITTY_KEY", raising=False)

    assert cli.main([]) == 0

    assert os.environ["TEXTUAL_DISABLE_KITTY_KEY"] == "1"
