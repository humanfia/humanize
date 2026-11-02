"""`hmz.coganchor.easytier`: the secret, the download, and what `easytier-core` is told.

Never the network and never a process: `urllib.request.urlopen` answers with a zip made here,
and `subprocess.Popen` is a recorder.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import io
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
    assert started.argv[started.argv.index("--peers") + 1 :] == list(easytier.PEERS)


def test_serving_lets_only_its_port_through(started: _Started) -> None:
    easytier.serving(SECRET, 4321)
    _common(started)
    assert started.argv[started.argv.index("--tcp-whitelist") + 1] == "4321"
    assert started.argv[started.argv.index("--udp-whitelist") + 1] == "0"
    assert "--ipv4" in started.argv
    assert "--port-forward" not in started.argv


def test_joining_forwards_a_local_port_to_the_served_one(started: _Started) -> None:
    easytier.serving(SECRET)
    served = started.argv[started.argv.index("--ipv4") + 1]
    easytier.joining(SECRET, 5678)
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
    easytier.joining(SECRET, 5678)
    assert "ET_NO_TUN" not in started.env
    assert started.env["ET_NETWORK_SECRET"] == easytier.network(SECRET)[1]


def test_no_peers_are_none_told(started: _Started) -> None:
    easytier.joining(SECRET, 5678, peers=())
    assert "--peers" not in started.argv


@pytest.mark.usefixtures("started")
def test_a_short_secret_starts_nothing() -> None:
    with pytest.raises(ValueError, match="at least 16 bytes"):
        easytier.serving("short")
