"""`hmz.sdk.Daemons`: the daemon's runs, asked through one object."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import hmz.daemon
from hmz.sdk import Daemons


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`hmz.daemon`'s three ways of finding runs, mocked."""
    held = mock.Mock()
    for name in ("running", "daemons", "host"):
        monkeypatch.setattr(hmz.daemon, name, getattr(held, name))
    return held


@pytest.mark.parametrize("workspace", [None, "/w", Path("/w")])
def test_here_asks_for_the_runs_of_one_workspace(
    daemon: mock.Mock, workspace: str | Path | None
) -> None:
    assert Daemons().here(workspace) is daemon.running.return_value
    daemon.running.assert_called_once_with(workspace)


def test_here_is_none_where_nothing_is_held(daemon: mock.Mock) -> None:
    daemon.running.return_value = None
    assert Daemons().here() is None
    daemon.running.assert_called_once_with(None)


def test_all_is_every_run_on_the_machine(daemon: mock.Mock) -> None:
    daemon.daemons.return_value = ["a", "b"]
    assert Daemons().all() == ["a", "b"]
    daemon.daemons.assert_called_once_with()


@pytest.mark.parametrize("workspace", [None, "/w"])
def test_host_starts_or_finds_the_host_of_a_workspace(
    daemon: mock.Mock, workspace: str | None
) -> None:
    assert Daemons().host(workspace) is daemon.host.return_value
    daemon.host.assert_called_once_with(workspace)


def test_host_raises_what_the_daemon_raises(daemon: mock.Mock) -> None:
    daemon.host.side_effect = OSError("older humanize")
    with pytest.raises(OSError, match="older humanize"):
        Daemons().host()
