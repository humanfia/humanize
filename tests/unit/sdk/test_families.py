"""`hmz.sdk.families`: a daemon's methods as typed calls, through a client that is mocked."""

from __future__ import annotations

import threading
from typing import Any
from unittest import mock

import pytest

from hmz.sdk import Client
from hmz.sdk.families import Family, Subscription
from hmz.sdk.families.devices import Code, Device, Devices

FAMILIES = (
    "accounts", "aichan", "backups", "btw", "chats", "devices", "easytier", "envs", "epics",
    "files", "flows", "flowverses", "hosts", "notices", "nous", "paths", "runs", "runtimes",
    "settings", "workspaces",
)  # fmt: skip


@pytest.fixture
def client() -> mock.Mock:
    return mock.Mock(spec=["call", "heard"])


def test_a_client_has_every_family_each_made_once() -> None:
    made = Client(mock.Mock())

    for name in FAMILIES:
        family = getattr(made, name)
        assert isinstance(family, Family)
        assert getattr(made, name) is family
        assert all(isinstance(method, str) for method in family.METHODS)


def test_a_call_leaves_out_what_was_not_said(client: mock.Mock) -> None:
    client.call.return_value = {"code": "hmz-1", "expires": 99}

    Devices(client).pair(seconds=60, idem="k")

    client.call.assert_called_once_with(
        "pair.create", {"seconds": 60}, idem="k", seconds=None
    )


def test_devices_are_listed_as_they_are_kept(client: mock.Mock) -> None:
    client.call.return_value = {
        "devices": [
            {
                "name": "phone",
                "fingerprint": "ab:cd",
                "added": "2026-01-01T00:00:00Z",
                "seen": None,
            }
        ]
    }

    assert Devices(client).list() == [
        Device("phone", "ab:cd", "2026-01-01T00:00:00Z", None)
    ]
    client.call.assert_called_once_with("devices.list", {}, idem=None, seconds=None)


def test_revoking_says_how_many_sessions_were_closed(client: mock.Mock) -> None:
    client.call.return_value = {"dropped": 2}

    assert Devices(client).revoke("phone") == 2
    client.call.assert_called_once_with(
        "devices.revoke", {"name": "phone"}, idem=None, seconds=None
    )


def test_a_pairing_code_is_made_and_claimed(client: mock.Mock) -> None:
    client.call.return_value = {"code": "hmz-1", "expires": 99}

    assert Devices(client).pair(routes=["tcp:host:1"]) == Code(
        "hmz-1", 99, {"code": "hmz-1", "expires": 99}
    )
    client.call.assert_called_once_with(
        "pair.create", {"routes": ["tcp:host:1"]}, idem=None, seconds=None
    )
    client.call.return_value = {"daemon_id": "d", "device": "phone"}
    assert Devices(client).claim("token", "phone") == {
        "daemon_id": "d",
        "device": "phone",
    }


def test_the_devices_family_names_the_methods_it_makes() -> None:
    assert Devices.METHODS == (
        "pair.create",
        "pair.claim",
        "devices.list",
        "devices.revoke",
    )


def _hears(client: mock.Mock) -> Any:
    """What the client was given to tell notifications to."""
    (listener,), _ = client.heard.call_args
    return listener


def test_a_subscription_is_told_what_is_said_to_it_and_nothing_else(
    client: mock.Mock,
) -> None:
    with Subscription(client, "epic.event", "s1") as heard:
        hears = _hears(client)
        hears("epic.event", {"sub": "s2", "message": "theirs"})
        hears("notices.event", {"sub": "s1", "notice": "another method"})
        hears("epic.event", {"sub": "s1", "message": "ours"})

        assert heard.sub == "s1"
        assert heard.next(1) == {"sub": "s1", "message": "ours"}
        assert heard.next(0.01) is None


def test_what_was_said_before_a_subscription_was_taken_up_is_kept_for_it(
    client: mock.Mock,
) -> None:
    first = Subscription(client, "epic.event", "s1")
    _hears(client)("epic.event", {"sub": "s2", "message": "early"})

    second = Subscription(client, "epic.event", "s2")

    assert second.next(1) == {"sub": "s2", "message": "early"}
    client.heard.assert_called_once()
    first.close()
    second.close()


def test_what_is_said_to_a_subscription_after_it_was_closed_is_kept_for_nobody(
    client: mock.Mock,
) -> None:
    hub = Subscription(client, "epic.event", "s1")
    hears = _hears(client)
    hears("epic.event", {"sub": "s1", "message": "unread"})
    hub.close()
    # What a host says to a frontend it has let go, after the call that let it go.
    hears("epic.event", {"sub": "s1", "message": {"type": "gone"}})

    with Subscription(client, "epic.event", "s1") as again:
        assert again.next(0.01) is None
        # Taken up again, it is heard again.
        hears("epic.event", {"sub": "s1", "message": "new"})
        assert again.next(1) == {"sub": "s1", "message": "new"}


def test_a_family_listens_before_the_call_that_opens_a_subscription(
    client: mock.Mock,
) -> None:
    class Opening(Family):
        def opens(self) -> Subscription:
            self._listens()
            # The daemon speaks before the call that opened the subscription is answered.
            _hears(client)("epic.event", {"sub": "s7", "message": "at once"})
            return self._heard("epic.event", "s7")

    with Opening(client).opens() as heard:
        assert heard.next(1) == {"sub": "s7", "message": "at once"}
    client.heard.assert_called_once()


def test_iterating_ends_once_it_is_closed(client: mock.Mock) -> None:
    heard = Subscription(client, "notices.event", "s1")
    _hears(client)("notices.event", {"sub": "s1", "notice": {"id": 1}})
    threading.Timer(0.05, heard.close).start()

    assert list(heard) == [{"sub": "s1", "notice": {"id": 1}}]
