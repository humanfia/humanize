"""`hmz` with no command: the interface opened as one more frontend of the runs held here.

The line reaches the workspace's host through the machine's daemon -- started where none is --
and hands the interface a link to it, whatever the terminal: nothing holds the runs in the
process. The interface is stood in for by one that says what it was opened on; the daemon and
the host are real.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from hmz import cli, daemon
from hmz.daemon import Link, where
from tests.integration.doubles_daemon import hosting, project, standing, until

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(90),
]


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
def test_a_host_is_started_and_read_as_one_more_frontend() -> None:
    assert cli.opens() == 0

    (said,) = Stands.opened
    assert isinstance(said["link"], Link)
    assert [one["kind"] for one in Stands.status["clients"]] == ["tui"]
    # The interface was its last frontend, and nothing runs: the host goes with it.
    assert until(lambda: daemon.running() is None)


@pytest.mark.usefixtures("workspace")
def test_a_host_already_holding_the_runs_here_is_the_one_read() -> None:
    held = daemon.host()
    with held.link(name="keeping"):
        assert cli.opens() == 0

        assert Stands.status["pid"] == held.pid
        assert sorted(one["kind"] for one in Stands.status["clients"]) == ["sdk", "tui"]


@pytest.mark.usefixtures("workspace")
def test_runs_held_by_an_older_humanize_are_said_to_be_and_left_alone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with standing(where.at(), {}):
        assert cli.opens() == 1

    assert "older Humanize" in capsys.readouterr().err
    assert Stands.opened == []


@pytest.mark.usefixtures("workspace")
def test_update_says_of_a_daemon_holding_no_host_that_it_runs_the_old_release(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import os
    import sys

    from hmz.cli import update
    from hmz.coganchor import __version__, releases
    from hmz.rpc import PROTOCOL

    monkeypatch.setattr(update, "_how", lambda: [sys.executable, "-c", "pass"])
    monkeypatch.setattr(update, "_installed", lambda: "999.0.0")
    monkeypatch.setattr(releases, "fetch", lambda: "999.0.0")

    with standing(where.at(), {"kind": "daemon", "protocol": PROTOCOL}):
        assert daemon.daemons() == []
        assert cli.main(["update"]) == 0

    assert (
        f"Epics held on this machine (pid {os.getpid()}) run hmz {__version__} "
        "until that daemon stops"
    ) in capsys.readouterr().out
