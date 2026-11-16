"""`hmz.sdk.Client`: the runtime's client, with this machine's daemon reached, mocked."""

from __future__ import annotations

from unittest import mock

import pytest

import hmz.daemon
import hmz.reach.pipes
import hmz.runtime.doing.daemons
from hmz.daemon import where
from hmz.sdk import Client


def test_the_client_is_the_runtimes() -> None:
    assert issubclass(Client, hmz.runtime.doing.daemons.Client)


@pytest.fixture
def reached(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """Starting the daemon, its socket and a session over it, each a stand-in."""
    held = mock.Mock()
    monkeypatch.setattr(hmz.daemon, "start", held.start)
    monkeypatch.setattr(where, "at", held.at)
    monkeypatch.setattr(where, "connects", held.connects)
    monkeypatch.setattr(hmz.reach.pipes, "SocketPipe", held.pipe)
    monkeypatch.setattr(Client, "over", held.over)
    return held


def test_local_starts_the_daemon_and_holds_a_session_of_its_own(
    reached: mock.Mock,
) -> None:
    made = Client.local(name="ci", kind="cli")

    assert made is reached.over.return_value
    reached.start.assert_called_once_with()
    reached.connects.assert_called_once_with(reached.at.return_value, 10.0)
    reached.connects.return_value.settimeout.assert_called_once_with(None)
    reached.pipe.assert_called_once_with(reached.connects.return_value, trusted=True)
    reached.over.assert_called_once_with(
        reached.pipe.return_value, name="ci", kind="cli"
    )


def test_local_cannot_reach_a_daemon_that_will_not_start(reached: mock.Mock) -> None:
    reached.start.side_effect = OSError("no fork")

    with pytest.raises(OSError, match="no fork"):
        Client.local()
    reached.over.assert_not_called()
