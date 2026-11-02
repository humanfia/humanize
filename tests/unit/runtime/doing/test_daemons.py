"""`hmz.runtime.doing.daemons`: what a host says it has, and what reaching its interface carries."""

from __future__ import annotations

import copy
import threading
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.doing.daemons import (
    CARRIED,
    EASYTIER,
    FAILED,
    LOCAL,
    SSH,
    UP,
    Daemons,
    Remotes,
    carried,
    headers,
    said,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The settings file, as a dict that `read` and `changes` read and write."""
    from hmz.coganchor import settings

    file: dict[str, Any] = {"other": {"kept": True}}

    def changes(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        working = copy.deepcopy(file)
        change(working)
        file.clear()
        file.update(working)
        return file

    monkeypatch.setattr(settings, "read", lambda: copy.deepcopy(file))
    monkeypatch.setattr(settings, "changes", changes)
    return file


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ssh config naming `gpu` and `box.one`."""
    from hmz.coganchor.machines import sshconfig

    def aliases(*_: object) -> list[str]:
        return ["gpu", "box.one", "local"]

    monkeypatch.setattr(sshconfig, "aliases", aliases)


def test_a_daemon_is_written_replaced_only_when_asked_and_removed(
    held: dict[str, Any],
) -> None:
    daemons = Daemons()

    written = daemons.write("gpu", {"host": "a", "options": [["Compression", "yes"]]})
    with pytest.raises(FileExistsError):
        daemons.write("gpu", {"host": "b"})
    daemons.write("gpu", {"host": "b"}, replace=True)

    assert written["options"] == [["Compression", "yes"]]
    assert daemons.find("gpu") == daemons.all()[0]
    assert daemons.all()[0]["host"] == "b"
    assert held["other"] == {"kept": True}
    with pytest.raises(ValueError, match="Local is always there"):
        daemons.remove(LOCAL)
    with pytest.raises(LookupError):
        daemons.remove("nope")
    daemons.remove("gpu")
    assert daemons.all() == []


@pytest.mark.parametrize(
    ("name", "fields"),
    [("Local", {"host": "a"}), ("..", {"host": "a"}), ("gpu", {"workdir": "/w"})],
)
def test_what_cannot_be_a_daemon_is_refused(
    held: dict[str, Any], name: str, fields: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="daemon"):
        Daemons().write(name, fields)

    assert "daemons" not in held


def test_hosts_of_the_ssh_config_are_offered_and_brought_in_once(
    held: dict[str, Any], config: None
) -> None:
    daemons = Daemons()

    assert list(daemons.offered()) == ["gpu", "box.one"]
    assert daemons.imported(["gpu", "gpu"]) == ["gpu"]
    assert list(daemons.offered()) == ["box.one"]
    with pytest.raises(LookupError):
        daemons.imported(["elsewhere"])
    with pytest.raises(ValueError, match="Say aliases"):
        daemons.imported([])


def test_local_stands_up_and_nothing_else_is_reached_unasked() -> None:
    remotes = Remotes(version="1.2.3")
    try:
        assert remotes.state(LOCAL)["state"] == UP
        assert remotes.state("gpu") == {"state": "idle", "detail": "", "version": ""}
    finally:
        remotes.close()


def test_a_probe_is_read_by_what_each_line_says() -> None:
    assert said(
        [
            "Warning: Permanently added 'box' to the list of known hosts.",
            "hmz: 0.5.0rc1",
            "daemon: running",
            "something: else",
        ]
    ) == {"hmz": "0.5.0rc1", "daemon": "running"}
    assert said(["hmz: ", "daemon: none"]) == {"hmz": "", "daemon": "none"}
    assert said([]) == {}


def test_a_request_there_is_its_own_page_s() -> None:
    assert headers(8123, "k3y") == {
        "Host": "127.0.0.1:8123",
        "Origin": "http://127.0.0.1:8123",
        "Sec-Fetch-Site": "same-origin",
        "Cookie": "hmz-8123=k3y",
    }


def _plain(url: str) -> str:
    """A URL with nothing signed into it, as the flowverses strike one."""
    return url.replace("me:secret@", "***@")


def test_a_batch_carries_the_pages_asked_for_as_each_page_saves_them() -> None:
    target = SimpleNamespace(
        name="lab",
        url="https://me:secret@example.com/epics.git",
        branch="main",
        policies=("manual",),
        every=30,
    )
    runtime = SimpleNamespace(
        held=lambda: {"backend": "ssh", "name": "gpu", "made": "typed", "host": "g"}
    )
    step = SimpleNamespace(spec="claude", to=("codex",), tries=2, policy="p", timeout=5)
    hmz = SimpleNamespace(
        settings=SimpleNamespace(btw="", details=True, enable_sentry=None),
        fallbacks=SimpleNamespace(all=lambda: [step]),
        runtimes=SimpleNamespace(all=lambda: [runtime]),
        backups=SimpleNamespace(targets=lambda: [target], defaults=lambda: ["lab"]),
        verses=SimpleNamespace(plain=_plain),
    )

    sent = carried(hmz, CARRIED)

    assert sent == [
        ("/api/settings", {"btw": "", "details": True}),
        (
            "/api/fallbacks",
            {
                "spec": "claude",
                "to": ["codex"],
                "tries": 2,
                "policy": "p",
                "timeout": 5,
            },
        ),
        (
            "/api/runtimes",
            {"backend": "ssh", "name": "gpu", "fields": {"host": "g"}, "replace": True},
        ),
        (
            "/api/settings",
            {
                "backup": {
                    "targets": [
                        {
                            "name": "lab",
                            "url": "https://***@example.com/epics.git",
                            "branch": "main",
                            "policies": ["manual"],
                            "every": 30,
                        }
                    ],
                    "defaults": ["lab"],
                }
            },
        ),
    ]
    assert carried(hmz, ["general"]) == sent[:1]


_SECRET = "sixteen-bytes-ok"

#: The EasyTier nodes a P2P daemon meets its server through.
_PEERS = ["tcp://node.example:11010", "wss://[::1]:11012/"]

#: A P2P daemon as it is written.
_P2P = {"via": EASYTIER, "secret": _SECRET, "peers": _PEERS}


def test_an_easytier_daemon_holds_its_secret_and_its_nodes(
    held: dict[str, Any],
) -> None:
    daemons = Daemons()

    written = daemons.write("et", _P2P)

    assert written == {"name": "et", **_P2P}
    assert daemons.find("et") == written
    assert held["daemons"] == [written]


@pytest.mark.parametrize(
    "fields",
    [
        _P2P | {"secret": "fifteen-bytes!!"},
        {"via": EASYTIER, "peers": _PEERS},
        _P2P | {"secret": 1234567890123456789},
        _P2P | {"host": "a"},
        {"via": SSH, "host": "a", "secret": _SECRET},
        {"via": SSH, "host": "a", "peers": _PEERS},
        {"via": "p2p", "secret": _SECRET},
    ],
)
def test_what_cannot_be_an_easytier_daemon_is_refused_never_saying_its_secret(
    held: dict[str, Any], fields: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match=r"secret|takes no|via") as refused:
        Daemons().write("et", fields)

    assert _SECRET not in str(refused.value)
    assert "daemons" not in held


@pytest.mark.parametrize("peers", [None, [], "tcp://node.example:11010"])
def test_an_easytier_daemon_needs_a_node(held: dict[str, Any], peers: object) -> None:
    with pytest.raises(ValueError, match="at least one node"):
        Daemons().write("et", _P2P | {"peers": peers})

    assert "daemons" not in held


@pytest.mark.parametrize(
    "node",
    [
        "http://node.example:11010",
        "tcp://node.example",
        "tcp://:11010",
        "tcp://node.example:99999",
        "tcp://node.example:11010/path",
        "tcp://me@node.example:11010",
        "tcp://:pw@node.example:11010",
        "tcp://node.example:0",
        "tcp://node example:11010",
        "node.example:11010",
        11010,
    ],
)
def test_a_node_that_is_not_one_is_refused_by_name(
    held: dict[str, Any], node: object
) -> None:
    with pytest.raises(ValueError, match="is not an EasyTier node") as refused:
        Daemons().write("et", _P2P | {"peers": [_PEERS[0], node]})

    assert repr(node) in str(refused.value)
    assert "daemons" not in held


def test_a_secret_is_counted_in_bytes(held: dict[str, Any]) -> None:
    # Five characters of three bytes each are fifteen bytes; six are eighteen.
    with pytest.raises(ValueError, match="at least 16 bytes"):
        Daemons().write("et", _P2P | {"secret": "€" * 5})

    assert Daemons().write("et", _P2P | {"secret": "€" * 6})["secret"]


def test_a_replacement_saying_no_secret_keeps_the_one_written(
    held: dict[str, Any],
) -> None:
    daemons = Daemons()
    daemons.write("et", _P2P)
    unsaid = {"via": EASYTIER, "peers": _PEERS[:1]}

    daemons.write("et", unsaid, replace=True)
    daemons.write("et", unsaid | {"secret": True}, replace=True)
    daemons.write("et", unsaid | {"secret": ""}, replace=True)
    assert daemons.find("et") == {"name": "et", **unsaid, "secret": _SECRET}
    with pytest.raises(ValueError, match="16 bytes"):
        daemons.write("et", unsaid | {"secret": False}, replace=True)
    daemons.write("et", unsaid | {"secret": "another-sixteen!"}, replace=True)
    assert held["daemons"][0]["secret"] == "another-sixteen!"
    with pytest.raises(ValueError, match="16 bytes"):
        daemons.write("new", unsaid, replace=True)


def test_an_ssh_daemon_is_a_host_of_the_ssh_config_or_one_typed_in(
    held: dict[str, Any],
) -> None:
    daemons = Daemons()
    held["daemons"] = [
        {"name": "old", "alias": "gpu", "host": "10.0.0.1"},
        {"name": "hand", "via": "nope", "host": "a"},
        {"name": "bare", "via": EASYTIER, "secret": _SECRET},
    ]

    alias = daemons.write("gpu", {"alias": "gpu", "config": "~/.ssh/other"})
    typed = daemons.write("box", {"via": SSH, "host": "box", "user": "me"})

    assert (alias["via"], alias["alias"], alias["host"]) == (SSH, "gpu", "")
    assert (typed["via"], typed["alias"], typed["host"]) == (SSH, "", "box")
    # Written before there were ways, with both: still there; written wrong: left out.
    assert [one["name"] for one in daemons.all()] == ["old", "gpu", "box"]


def _stands(remotes: Remotes, name: str, state: str) -> dict[str, str]:
    """How a daemon stands, once it stands so."""
    ending = time.monotonic() + 5
    while remotes.state(name)["state"] != state:
        assert time.monotonic() < ending, remotes.state(name)
        time.sleep(0.01)
    return remotes.state(name)


def test_an_easytier_daemon_is_installing_while_easytier_downloads(
    held: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.coganchor import easytier

    downloaded = threading.Event()

    def binary(say: Callable[[str], object] | None = None) -> Any:
        assert say is not None
        say("Downloading EasyTier 9.9.9")
        downloaded.wait(5)
        raise OSError("cannot download EasyTier 9.9.9 for this machine")

    monkeypatch.setattr(easytier, "binary", binary)
    monkeypatch.setattr(easytier, "joining", _never)
    Daemons().write("et", _P2P)
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("et")
        assert _stands(remotes, "et", "installing") == {
            "state": "installing",
            "detail": "Downloading EasyTier 9.9.9",
            "version": "",
        }
        downloaded.set()
        failed = _stands(remotes, "et", FAILED)
        assert failed["detail"] == "cannot download EasyTier 9.9.9 for this machine"
        assert _SECRET not in str(failed)
    finally:
        remotes.close()
    assert remotes.state("et")["state"] == "idle"


def _never(*_: object, **__: object) -> Any:
    """`easytier.joining`, which nothing here may come to."""
    raise AssertionError
