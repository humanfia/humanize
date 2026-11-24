"""`client.runtimes`, `client.easytier` and `Client.named`: typed calls through a mocked client."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

import hmz.runtime.doing.daemons
from hmz.sdk import Client
from hmz.sdk.families.easytier import EasyTier, Network, Node
from hmz.sdk.families.runtimes import Checked, Host, Listed, Runtime, Runtimes

SAID: dict[str, Any] = {
    "local": {"host": "here", "cpus": 8},
    "runtimes": [
        {"backend": "ssh", "name": "box", "made": "typed", "host": "h", "port": 22}
    ],
    "blanks": {"ssh": {"host": "", "port": 0}},
}

LISTED = Listed(
    {"host": "here", "cpus": 8},
    (Runtime("ssh", "box", "typed", {"host": "h", "port": 22}),),
    {"ssh": {"host": "", "port": 0}},
)


@pytest.fixture
def client() -> mock.Mock:
    return mock.Mock(spec=["call", "heard"])


def test_the_two_families_cover_their_methods() -> None:
    assert Runtimes.METHODS == (
        "runtimes.list",
        "runtimes.set",
        "runtimes.remove",
        "runtimes.check",
        "runtimes.hosts",
        "runtimes.import",
    )
    assert EasyTier.METHODS == (
        "easytier.list",
        "easytier.set",
        "easytier.remove",
        "easytier.nodes",
    )


def test_runtimes_are_listed_with_their_own_fields_apart(client: mock.Mock) -> None:
    client.call.return_value = SAID

    assert Runtimes(client).list() == LISTED
    client.call.assert_called_once_with("runtimes.list", {}, idem=None, seconds=None)


def test_a_runtime_is_written_and_replaced(client: mock.Mock) -> None:
    client.call.return_value = SAID

    assert Runtimes(client).set("ssh", "box", {"host": "h"}) == LISTED
    client.call.assert_called_once_with(
        "runtimes.set",
        {"backend": "ssh", "name": "box", "fields": {"host": "h"}},
        idem=None,
        seconds=None,
    )

    client.call.reset_mock()
    Runtimes(client).set("ssh", "box", replace=True, idem="k")
    client.call.assert_called_once_with(
        "runtimes.set",
        {"backend": "ssh", "name": "box", "fields": {}, "replace": True},
        idem="k",
        seconds=None,
    )


def test_a_runtime_is_removed(client: mock.Mock) -> None:
    client.call.return_value = SAID

    assert Runtimes(client).remove("ssh", "box", idem="k") == LISTED
    client.call.assert_called_once_with(
        "runtimes.remove", {"backend": "ssh", "name": "box"}, idem="k", seconds=None
    )


def test_a_check_says_what_the_runtime_has(client: mock.Mock) -> None:
    said = {
        "reached": False,
        "said": "no route to host",
        "home": "",
        "cpus": 0.0,
        "memory": 0,
        "gpus": ["0"],
        "usable": None,
        "gpu_memory": 0,
        "runtimes": [],
        "version": "",
        "short": ["gpus"],
        "nodes": [],
    }
    client.call.return_value = said

    assert Runtimes(client).check("ssh", "box", wait=5) == Checked(
        False, "no route to host", 0.0, 0, ("0",), ("gpus",), said
    )
    client.call.assert_called_once_with(
        "runtimes.check", {"backend": "ssh", "name": "box"}, idem=None, seconds=5
    )


def test_the_hosts_of_the_ssh_config_are_listed(client: mock.Mock) -> None:
    one: dict[str, Any] = {
        "alias": "box",
        "host": "10.0.0.7",
        "user": "me",
        "port": 22,
        "identity_files": [],
        "proxy_jump": "",
        "saved": True,
    }
    client.call.return_value = {"hosts": [one]}

    assert Runtimes(client).hosts() == (Host("box", "10.0.0.7", "me", 22, True, one),)
    client.call.assert_called_once_with("runtimes.hosts", {}, idem=None, seconds=None)


def test_hosts_are_imported_by_name(client: mock.Mock) -> None:
    client.call.return_value = SAID

    assert Runtimes(client).import_(("box",)) == LISTED
    client.call.assert_called_once_with(
        "runtimes.import", {"names": ["box"]}, idem=None, seconds=None
    )

    client.call.reset_mock()
    Runtimes(client).import_(["box"], update=True)
    client.call.assert_called_once_with(
        "runtimes.import", {"names": ["box"], "update": True}, idem=None, seconds=None
    )


def test_easytier_entries_are_listed_written_and_removed(client: mock.Mock) -> None:
    client.call.return_value = {
        "networks": [{"name": "lab", "nodes": ["tcp://n:1"], "secret": True}]
    }
    networks = (Network("lab", ("tcp://n:1",), keyed=True),)

    assert EasyTier(client).list() == networks
    client.call.assert_called_once_with("easytier.list", {}, idem=None, seconds=None)

    client.call.reset_mock()
    assert EasyTier(client).set("lab", ("tcp://n:1",), secret="s" * 16) == networks
    client.call.assert_called_once_with(
        "easytier.set",
        {"name": "lab", "secret": "s" * 16, "nodes": ["tcp://n:1"]},
        idem=None,
        seconds=None,
    )

    client.call.reset_mock()
    EasyTier(client).set("lab", ["tcp://n:1"])
    client.call.assert_called_once_with(
        "easytier.set", {"name": "lab", "nodes": ["tcp://n:1"]}, idem=None, seconds=None
    )

    client.call.reset_mock()
    assert EasyTier(client).remove("lab", idem="k") == networks
    client.call.assert_called_once_with(
        "easytier.remove", {"name": "lab"}, idem="k", seconds=None
    )


def test_the_shared_nodes_are_listed_as_they_stand(client: mock.Mock) -> None:
    client.call.return_value = {
        "nodes": [
            {"url": "tcp://a:1", "name": "A", "version": "2", "up": True, "uptime": 1},
            {"url": "tcp://b:1", "name": "", "version": "", "up": None, "uptime": None},
        ]
    }

    assert EasyTier(client).nodes() == (
        Node("tcp://a:1", "A", "2", up=True, uptime=1),
        Node("tcp://b:1", "", "", up=None, uptime=None),
    )
    client.call.assert_called_once_with("easytier.nodes", {}, idem=None, seconds=None)


@pytest.fixture
def remotes(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """What reaches the daemons of the registry, stood in."""
    held = mock.Mock()
    registry = mock.Mock()
    registry.return_value.remotes.return_value = held
    monkeypatch.setattr(hmz.runtime.doing.daemons, "Daemons", registry)
    return held


def test_a_daemon_of_the_registry_is_reached_by_name_and_let_go_of_whole(
    remotes: mock.Mock,
) -> None:
    session = mock.Mock()
    session.said = {"daemon_id": "abc", "version": "1.2.3"}
    session.peer.closed = False
    session.peer.call.return_value = {"devices": []}
    remotes.client.return_value = Client(session)

    client = Client.named("gpu", kind="cli")

    # Reached as what it is, and handed out as the SDK's own client: nothing of the
    # runtime's is reached into.
    registry = hmz.runtime.doing.daemons.Daemons
    registry.return_value.remotes.assert_called_once_with(kind="cli")  # pyright: ignore[reportFunctionMemberAccess]
    remotes.client.assert_called_once_with("gpu", Client)
    assert client is remotes.client.return_value
    assert (client.daemon_id, client.version) == ("abc", "1.2.3")
    assert client.devices.list() == []
    remotes.close.assert_not_called()
    client.close()
    client.close()
    remotes.close.assert_called_once_with()


def test_a_daemon_on_its_way_up_is_waited_for(
    remotes: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    unreached = hmz.runtime.doing.daemons.Unreached
    session = mock.Mock()
    session.peer.closed = False
    remotes.client.side_effect = [
        unreached("Installing hmz.", {"state": "installing"}),
        unreached("gpu is not reached yet.", {"state": "connecting"}),
        Client(session),
    ]
    monkeypatch.setattr("time.sleep", mock.Mock())

    client = Client.named("gpu")

    assert remotes.client.call_count == 3
    remotes.close.assert_not_called()
    client.close()
    remotes.close.assert_called_once_with()


def test_a_daemon_that_is_not_reached_or_not_kept_lets_go_of_what_reached_for_it(
    remotes: mock.Mock,
) -> None:
    remotes.client.side_effect = hmz.runtime.doing.daemons.Unreached(
        "gpu is down.", {"state": "failed"}
    )
    with pytest.raises(OSError, match=r"gpu is down\."):
        Client.named("gpu")
    remotes.close.assert_called_once_with()

    remotes.client.side_effect = LookupError("There is no daemon by that name.")
    with pytest.raises(LookupError):
        Client.named("far")
    assert remotes.close.call_count == 2
