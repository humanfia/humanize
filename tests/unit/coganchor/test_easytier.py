"""`hmz.coganchor.easytier`: the secret, the download, and what `easytier-core` is told.

Never the network and never a process: `urllib.request.urlopen` answers with a zip or a status
page made here, and `subprocess.Popen` is a recorder.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import io
import json
import os
import platform
import stat
import subprocess
import urllib.error
import urllib.request
import zipfile
from typing import TYPE_CHECKING, Any

import pytest

from hmz import home
from hmz.coganchor import easytier

if TYPE_CHECKING:
    from pathlib import Path

SECRET = "correct horse battery staple"
CORE = b"#!/bin/sh\necho easytier-core\n"
PEERS = ("tcp://node.example:11010", "udp://other.example:11010")


def _zipped(*members: tuple[str, bytes]) -> bytes:
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w") as zipping:
        for name, body in members:
            zipping.writestr(name, body)
    return held.getvalue()


class _Answer(io.BytesIO):
    """What `urlopen` answers with: bytes, as a context manager."""


@pytest.fixture
def linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(easytier.WHICH, raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")


@pytest.fixture
def release(linux: None, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A release for this platform that is the one pinned; what was asked for, by URL."""
    del linux
    body = _zipped(
        ("easytier-linux-x86_64/easytier-core", CORE),
        ("easytier-linux-x86_64/easytier-cli", b"cli"),
    )
    monkeypatch.setitem(
        easytier.SHA256, "linux-x86_64", hashlib.sha256(body).hexdigest()
    )
    asked: list[str] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> _Answer:
        del timeout
        asked.append(request.full_url)
        return _Answer(body)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return asked


def test_a_secret_is_at_least_16_bytes() -> None:
    assert easytier.checked("x" * 16) == "x" * 16
    assert (
        easytier.checked("密钥密钥密钥") == "密钥密钥密钥"
    )  # six characters, 18 bytes
    for short in ("", "x" * 15, "密钥密钥密"):
        with pytest.raises(ValueError, match=r"A secret must be at least 16 bytes\."):
            easytier.checked(short)


def test_the_network_is_derived_and_the_secret_is_not_in_it() -> None:
    name, hidden = easytier.network(SECRET)
    assert (name, hidden) == easytier.network(SECRET)
    assert name != hidden
    for said in (name, hidden):
        assert len(said) == 64
        int(said, 16)
        assert SECRET not in said
    other = easytier.network(SECRET + "!")
    assert other[0] != name
    assert other[1] != hidden


def test_the_key_is_an_hmac_of_the_secret() -> None:
    assert (
        easytier.key(SECRET)
        == hmac.new(SECRET.encode(), b"hmz-web-key", hashlib.sha256).hexdigest()
    )
    assert easytier.key(SECRET) not in easytier.network(SECRET)


def test_a_named_binary_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = tmp_path / "easytier-core"
    named.write_bytes(CORE)
    monkeypatch.setenv(easytier.WHICH, str(named))
    assert easytier.binary() == named


def test_a_named_binary_that_is_not_there_is_ignored(
    release: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(easytier.WHICH, str(tmp_path / "missing"))
    assert easytier.binary() == home() / "easytier" / easytier.VERSION / "easytier-core"
    assert release


def test_the_release_is_downloaded_once(release: list[str]) -> None:
    said: list[str] = []
    core = easytier.binary(said.append)
    assert core == home() / "easytier" / easytier.VERSION / "easytier-core"
    assert core.read_bytes() == CORE
    assert core.stat().st_mode & stat.S_IXUSR
    assert sorted(path.name for path in core.parent.iterdir()) == ["easytier-core"]
    assert said == [f"Downloading EasyTier {easytier.VERSION}"]
    v = easytier.VERSION
    assert release == [
        (
            "https://github.com/EasyTier/EasyTier/releases/download/"
            f"v{v}/easytier-linux-x86_64-v{v}.zip"
        )
    ]
    assert easytier.binary(said.append) == core
    assert len(release) == 1
    assert len(said) == 1


@pytest.mark.usefixtures("linux")
def test_a_release_that_is_not_the_one_pinned_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def urlopen(*_: object, **__: object) -> _Answer:
        return _Answer(_zipped(("x/easytier-core", b"tampered")))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(OSError, match="SHA-256"):
        easytier.binary()
    assert not (home() / "easytier" / easytier.VERSION / "easytier-core").exists()


@pytest.mark.usefixtures("linux")
def test_a_failed_download_is_an_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(*_: object, **__: object) -> Any:
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(OSError, match=r"cannot download EasyTier.*no route to host"):
        easytier.binary()


@pytest.mark.usefixtures("linux")
def test_a_download_cut_short_is_an_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Cut(_Answer):
        def read(self, size: int | None = -1, /) -> bytes:
            raise http.client.IncompleteRead(b"", size)

    def urlopen(*_: object, **__: object) -> _Answer:
        return Cut()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(OSError, match="cannot download EasyTier"):
        easytier.binary()


def test_a_named_binary_may_start_at_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "easytier-core").write_bytes(CORE)
    monkeypatch.setenv(easytier.WHICH, "~/easytier-core")
    assert easytier.binary() == tmp_path / "easytier-core"


def test_a_platform_without_a_release_is_an_os_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(easytier.WHICH, raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Plan9")
    with pytest.raises(OSError, match="no release for Plan9"):
        easytier.binary()


def test_every_platform_has_a_pinned_digest() -> None:
    assert set(easytier.SHA256) == {
        "macos-aarch64",
        "macos-x86_64",
        "linux-x86_64",
        "linux-aarch64",
        "windows-x86_64",
    }
    assert all(len(digest) == 64 for digest in easytier.SHA256.values())


class _Started:
    """`subprocess.Popen`, recording what it was asked to start."""

    def __init__(self) -> None:
        self.argv: list[str] = []
        self.env: dict[str, str] = {}

    def __call__(self, argv: list[str], **said: Any) -> object:
        self.argv = argv
        self.env = said["env"]
        return self


@pytest.fixture
def started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Started:
    named = tmp_path / "easytier-core"
    named.write_bytes(CORE)
    monkeypatch.setenv(easytier.WHICH, str(named))
    recorder = _Started()
    monkeypatch.setattr(subprocess, "Popen", recorder)
    return recorder


def _common(started: _Started) -> None:
    name, hidden = easytier.network(SECRET)
    assert started.argv[0] == os.environ[easytier.WHICH]
    assert "--no-tun" in started.argv
    assert started.argv[started.argv.index("--network-name") + 1] == name
    assert started.env["ET_NETWORK_SECRET"] == hidden
    assert hidden not in started.argv
    assert SECRET not in " ".join(started.argv)
    assert started.argv[started.argv.index("--peers") + 1 :] == list(PEERS)


def test_serving_lets_only_its_port_through(started: _Started) -> None:
    easytier.serving(SECRET, 4321, peers=PEERS)
    _common(started)
    assert started.argv[started.argv.index("--tcp-whitelist") + 1] == "4321"
    assert started.argv[started.argv.index("--udp-whitelist") + 1] == "0"
    assert "--ipv4" in started.argv
    assert "--port-forward" not in started.argv


def test_joining_forwards_a_local_port_to_the_served_one(started: _Started) -> None:
    easytier.serving(SECRET, peers=PEERS)
    served = started.argv[started.argv.index("--ipv4") + 1]
    easytier.joining(SECRET, 5678, peers=PEERS)
    _common(started)
    forward = started.argv[started.argv.index("--port-forward") + 1]
    assert forward == f"tcp://127.0.0.1:5678/{served}:{easytier.PORT}"
    assert "--ipv4" not in started.argv
    assert started.argv[started.argv.index("--tcp-whitelist") + 1] == "0"
    assert started.argv[started.argv.index("--udp-whitelist") + 1] == "0"


def test_no_easytier_variable_of_ours_is_passed_on(
    started: _Started, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ET_NO_TUN", "false")
    monkeypatch.setenv("ET_NETWORK_SECRET", "someone else's")
    easytier.joining(SECRET, 5678, peers=PEERS)
    assert "ET_NO_TUN" not in started.env
    assert started.env["ET_NETWORK_SECRET"] == easytier.network(SECRET)[1]


def test_no_node_starts_nothing(started: _Started) -> None:
    assert easytier.PEERS == ()
    for starting in (
        lambda: easytier.serving(SECRET, peers=easytier.PEERS),
        lambda: easytier.joining(SECRET, 5678, peers=()),
    ):
        with pytest.raises(
            ValueError, match=r"An EasyTier daemon needs at least one node\."
        ):
            starting()
    assert started.argv == []


def test_a_node_is_a_url_of_a_protocol_easytier_reaches_it_over(
    started: _Started,
) -> None:
    for url in (
        "tcp://node.example:11010",
        "udp://1.2.3.4:11010",
        "ws://a.b:80",
        "wss://a.b:443/path",
        "quic://[::1]:11012",
        "wg://a.b:11011",
    ):
        assert easytier.node(url) == url
    for nope in (
        "",
        "node.example:11010",
        "http://node.example:11010",
        "tcp://node.example",
        "tcp://:11010",
        "tcp://node.example:99999",
        " tcp://node.example:11010",
        "--rpc-portal=0.0.0.0:15888",
    ):
        with pytest.raises(ValueError, match="is not an EasyTier node"):
            easytier.node(nope)
    with pytest.raises(ValueError, match="is not an EasyTier node"):
        easytier.serving(SECRET, peers=[*PEERS, "--rpc-portal=0.0.0.0:15888"])
    assert started.argv == []


@pytest.mark.usefixtures("started")
def test_a_short_secret_starts_nothing() -> None:
    with pytest.raises(ValueError, match="at least 16 bytes"):
        easytier.serving("short", peers=PEERS)


_PAGE: dict[str, Any] = {
    "publicGroupList": [
        {"name": "Services", "monitorList": []},
        {
            "name": "Shared",
            "monitorList": [
                {"id": 1, "name": "Guangzhou/Alice/v2.4.5/TCP/1.2.3.4:11010"},
                {"id": 2, "name": "Shanghai/Bob/2.6.4/et.example.com:11010/UDP"},
                {"id": 3, "name": "Tokyo/Carol/2.6.0/wss://w.example:443"},
                {"id": 4, "name": "Nowhere/Dan/2.6.0"},
                {"id": 5},
                "not a monitor",
                {"id": 6, "name": "Again/Alice/v2.4.5/1.2.3.4:11010"},
                {"id": 7, "name": "Twice/Eve/WSS://W.Example:443"},
                {"id": 8, "name": "Paris/Fay/5.6.7.8:11010/2.6.4"},
            ],
        },
        "not a group",
    ]
}

_BEATS = {
    "heartbeatList": {
        "1": [{"status": 0}, {"status": 1}],
        "2": [{"status": 0}],
        "3": [],
    },
    "uptimeList": {"1_24": 0.98, "2_24": 1.5, "3_24": "high"},
}


def _kuma(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, bytes | Exception]
) -> list[str]:
    """`urlopen` answering each URL with its bytes or raising its error; what was asked."""
    asked: list[str] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> _Answer:
        del timeout
        asked.append(request.full_url)
        answer = answers[request.full_url]
        if isinstance(answer, Exception):
            raise answer
        return _Answer(answer)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return asked


def _answers(
    base: str, page: bytes | Exception, beats: bytes | Exception
) -> dict[str, bytes | Exception]:
    return {
        f"{base}/api/status-page/easytier": page,
        f"{base}/api/status-page/heartbeat/easytier": beats,
    }


def test_the_community_nodes_are_read_from_the_status_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(easytier.NODES, "http://kuma.test/")
    _kuma(
        monkeypatch,
        _answers(
            "http://kuma.test",
            json.dumps(_PAGE).encode(),
            json.dumps(_BEATS).encode(),
        ),
    )

    assert easytier.community() == [
        easytier.Node(
            "tcp://1.2.3.4:11010",
            "Guangzhou/Alice/v2.4.5/TCP/1.2.3.4:11010",
            "v2.4.5",
            True,
            0.98,
        ),
        easytier.Node(
            "udp://et.example.com:11010",
            "Shanghai/Bob/2.6.4/et.example.com:11010/UDP",
            "2.6.4",
            False,
            1.0,
        ),
        easytier.Node(
            "wss://w.example:443",
            "Tokyo/Carol/2.6.0/wss://w.example:443",
            "2.6.0",
            None,
            None,
        ),
        easytier.Node(
            "tcp://5.6.7.8:11010", "Paris/Fay/5.6.7.8:11010/2.6.4", "2.6.4", None, None
        ),
    ]


def test_nodes_whose_heartbeats_cannot_be_read_are_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(easytier.NODES, "http://kuma.test")
    _kuma(
        monkeypatch,
        _answers(
            "http://kuma.test",
            json.dumps(_PAGE).encode(),
            urllib.error.URLError("refused"),
        ),
    )

    nodes = easytier.community()
    assert [one.url for one in nodes][:1] == ["tcp://1.2.3.4:11010"]
    assert {(one.up, one.uptime) for one in nodes} == {(None, None)}


def test_the_status_page_is_easytiers_own_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(easytier.NODES, raising=False)
    base = "https://easytier.gd.nkbpal.cn"
    asked = _kuma(monkeypatch, _answers(base, b'{"publicGroupList": []}', b"{}"))
    assert easytier.community() == []
    assert asked == list(_answers(base, b"", b""))


@pytest.mark.parametrize(
    ("page", "said"),
    [
        (urllib.error.URLError("no such host"), "no such host"),
        (http.client.IncompleteRead(b""), "cannot read"),
        (b"<html>", "cannot read"),
        (b'{"ok": true}', "has no status page easytier"),
    ],
)
def test_a_page_that_cannot_be_read_says_why(
    monkeypatch: pytest.MonkeyPatch, page: bytes | Exception, said: str
) -> None:
    monkeypatch.setenv(easytier.NODES, "http://kuma.test")
    _kuma(monkeypatch, _answers("http://kuma.test", page, b"{}"))
    with pytest.raises(OSError, match=said):
        easytier.community()


def test_only_an_http_status_page_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(easytier.NODES, "file:///etc")
    asked = _kuma(monkeypatch, {})
    with pytest.raises(OSError, match="is not an http URL"):
        easytier.community()
    assert asked == []
