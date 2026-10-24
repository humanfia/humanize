"""Unix sockets under a temporary directory too long to hold them: a Mac's, or a fence's.

A socket path has 104 bytes on macOS, its NUL included. A Mac's `TMPDIR` spends 49 of them and
a fenced process's more, so every socket humanize makes is checked here under one long enough
that nothing under it would fit -- and is bound, which is what refuses a path too long.
"""

from __future__ import annotations

import ast
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from hmz.coganchor.agents.clis import Shelf
from hmz.coganchor.agents.hooks import Hooks, Moment
from hmz.coganchor.agents.preload import Watch
from hmz.coganchor.agents.tools import Toolbox
from hmz.coganchor.faking import FakeCli, FakeCommand
from hmz.coganchor.unix import LONGEST


@pytest.fixture
def long() -> Path:
    """A temporary directory with no room under it for any socket."""
    at = Path(tempfile.gettempdir()) / ("t" * LONGEST)
    at.mkdir()
    return at


def _binds(path: str) -> None:
    assert len(path.encode()) <= LONGEST
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as held:
        held.bind(path)
    Path(path).unlink()


def test_each_socket_of_a_harness_fits(
    long: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(long))
    hooks = Hooks(frozenset(Moment), "a")
    gate = hooks.gate()
    watch = Watch(hooks)
    box = Toolbox()
    shelf = Shelf()
    shelf.shelves(1, (FakeCli("one", "One.", (FakeCommand("go", "Go.", print),)),))
    try:
        for at in (gate.address(), watch.address(), box.address()):
            assert at
            assert not at.startswith(str(long))
            assert len(at.encode()) <= LONGEST
            assert Path(at).is_socket()
        sock = os.path.join(shelf.where(), "cli.sock")  # noqa: PTH118
        assert not sock.startswith(str(long))
        assert len(sock.encode()) <= LONGEST
        assert Path(sock).is_socket()
    finally:
        gate.close()
        watch.close()
        box.close()
        shelf.close()


def _prefix(environ: dict[str, str]) -> list[str]:
    """What `ssh` to a target with options of its own is started with, in a fresh process."""
    said = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from hmz.coganchor.transport import Road, Target\n"
                "print(list(Road.to(Target.parse('ssh://me@box?IdentityFile=/k')).prefix))"
            ),
        ],
        env=environ,
        capture_output=True,
        text=True,
        check=True,
    )
    return ast.literal_eval(said.stdout)


def test_an_ssh_control_socket_fits(long: Path) -> None:
    environ = {k: v for k, v in os.environ.items() if k != "XDG_RUNTIME_DIR"}
    environ |= {"TMPDIR": str(long), "HUMANIZE_SSH_REUSE": "on"}
    prefix = _prefix(environ)
    path = next(one for one in prefix if one.startswith("ControlPath="))
    path = path.removeprefix("ControlPath=")
    control = Path(path).parent
    assert control.name == f"humanize-ssh-{os.getuid()}"
    assert not str(control).startswith(str(long))
    assert control.stat().st_mode & 0o777 == 0o700
    # What ssh binds first, before renaming it to the path it was told: `%C` and 16 digits.
    _binds(path.replace("%C", "c" * 40) + "." + "0" * 16)


def test_an_ssh_control_directory_not_this_users_alone_is_not_shared() -> None:
    # Short enough to be used rather than passed over for `/tmp`, which this test leaves alone.
    with tempfile.TemporaryDirectory(dir="/tmp") as under:
        control = Path(under) / f"humanize-ssh-{os.getuid()}"
        control.mkdir()
        control.chmod(0o755)
        environ = os.environ | {"XDG_RUNTIME_DIR": under, "HUMANIZE_SSH_REUSE": "on"}
        prefix = _prefix(environ)
    assert not any(one.startswith("ControlPath=") for one in prefix)
    assert "ControlMaster=auto" not in prefix
