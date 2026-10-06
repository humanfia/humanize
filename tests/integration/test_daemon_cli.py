"""`hmz` with no command: the interface opened as one more frontend of the runs held here.

With a terminal on both ends the line reaches the workspace's host through the machine's
daemon -- started where none is -- and hands the interface a link to it; without one, or with
`HUMANIZE_DAEMON=off`, the runs are held in the process. The interface is stood in for by one
that says what it was opened on; the daemon and the host are real.
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest.mock
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from hmz import cli, daemon
from hmz.daemon import Link, where
from tests.integration.doubles_daemon import hosting, project, standing, until

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(90),
    pytest.mark.filterwarnings("ignore:.*use of fork.*:DeprecationWarning"),
]


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@contextlib.contextmanager
def at_a_terminal() -> Generator[None]:
    """A terminal on both ends of the line, for as long as the block runs.

    Put in place inside the test rather than by a fixture: pytest puts its own capture back
    on `sys` between setting a test up and calling it.
    """
    with (
        unittest.mock.patch.object(sys, "stdin", _Terminal()),
        unittest.mock.patch.object(sys, "stdout", _Terminal()),
    ):
        yield


class Stands:
    """The interface: what it was opened with, and who was reading the runs while it ran."""

    opened: ClassVar[list[dict[str, Any]]] = []
    status: ClassVar[dict[str, Any]] = {}
    return_code = 0

    def __init__(self, **said: Any) -> None:
        self.link = said.get("link")
        Stands.opened.append(said)

    def run(self) -> None:
        if isinstance(self.link, Link):
            found = daemon.running()
            Stands.status.update(found.status() if found is not None else {})
            self.link.close()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    Stands.opened.clear()
    Stands.status.clear()
    monkeypatch.setattr("hmz.tui.Humanize", Stands)
    with hosting():
        yield at


@pytest.mark.usefixtures("workspace")
def test_at_a_terminal_a_host_is_started_and_read_as_one_more_frontend() -> None:
    with at_a_terminal():
        assert cli.opens() == 0

    (said,) = Stands.opened
    assert isinstance(said["link"], Link)
    assert [one["kind"] for one in Stands.status["clients"]] == ["tui"]
    # The interface was its last frontend, and nothing runs: the host goes with it.
    assert until(lambda: daemon.running() is None)


@pytest.mark.usefixtures("workspace")
def test_a_host_already_holding_the_runs_here_is_the_one_read() -> None:
    held = daemon.host()
    with held.link(name="keeping"), at_a_terminal():
        assert cli.opens() == 0

        assert Stands.status["pid"] == held.pid
        assert sorted(one["kind"] for one in Stands.status["clients"]) == ["sdk", "tui"]


@pytest.mark.usefixtures("workspace")
def test_runs_held_by_an_older_humanize_are_said_to_be_and_left_alone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with standing(where.at(), {}), at_a_terminal():
        assert cli.opens() == 1

    assert "older humanize" in capsys.readouterr().err
    assert Stands.opened == []


@pytest.mark.usefixtures("workspace")
def test_with_the_daemon_turned_off_the_runs_are_held_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(cli.APART, "off")

    with at_a_terminal():
        assert cli.opens() == 0

    assert Stands.opened == [{}]
    assert daemon.daemons() == []


@pytest.mark.usefixtures("workspace")
def test_without_a_terminal_the_runs_are_held_here() -> None:
    assert cli.opens() == 0

    assert Stands.opened == [{}]
    assert daemon.daemons() == []
