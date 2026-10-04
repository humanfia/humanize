"""What every test of a held workspace needs: a project of its own, and its runs held there.

A host is one per workspace, so a test that holds one has to be standing somewhere no other
test is -- and has to let go of it however it ended, or the next test finds a host it did not
start. The daemon every host is reached through is one per machine, and each test has a
temporary directory, and so a machine, of its own (see `tests/conftest.py`).

The tests themselves are under `tests/unit/daemon/` and `tests/integration/daemon/`, and these
fixtures stay here because they are what the tests are written against rather than tests,
and there is one copy of each because a second that drifted would be a second answer to where
this workspace's host is. `tests/integration/daemon/conftest.py` re-exports what it needs
from here.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project of its own to hold runs in, which is what a daemon is one of."""
    where = tmp_path / "project"
    where.mkdir()
    monkeypatch.chdir(where)
    return where


@pytest.fixture
def held(workspace: Path) -> Iterator[daemon.Daemon]:
    """This workspace's runs, held by a host, and gone again however the test ended."""
    one = daemon.host()
    try:
        yield one
    finally:
        if one.alive:
            one.kill()


@pytest.fixture
def older(workspace: Path) -> Iterator[daemon.Daemon]:
    """This machine's runs held by a daemon of an older humanize, which no frontend reaches.

    What such a one leaves beside its socket says nothing of a protocol, and what it answers
    a frontend with is nothing at all: a note written with no `protocol`, and a socket that
    takes each connection and closes it again, in this process and gone again afterwards.
    """
    with _standing(where.at(), {}):
        found = daemon.running()
        assert found is not None
        assert not found.protocol
        yield found


@pytest.fixture
def left(workspace: Path) -> Iterator[daemon.Daemon]:
    """This workspace held by a host an older humanize left, where each was kept then.

    One per workspace, under humanize's home, speaking the protocol before this one: what an
    upgrade finds still running in a directory.
    """
    from hmz import home

    at = home() / "daemons" / "project-0123456789ab"
    at.mkdir(parents=True)
    with _standing(
        at, {"workspace": where.workspace(workspace), "kind": "host", "protocol": 1}
    ):
        found = daemon.running()
        assert found is not None
        assert found.protocol == 1
        yield found


@contextlib.contextmanager
def _standing(at: Path, said: dict[str, object]) -> Generator[None]:
    """A daemon nobody here reaches, standing at `at` for as long as the block runs."""
    import os
    import socket
    import threading

    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with where.reached(at) as reaching:
        listening.bind(reaching)
    listening.listen(8)
    where.wrote(at, {"pid": os.getpid(), "started": "2026-01-01T00:00:00Z", **said})

    def closes() -> None:
        while True:
            try:
                one, _ = listening.accept()
            except OSError:
                return
            one.close()

    threading.Thread(target=closes, daemon=True, name="older-daemon").start()
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            listening.shutdown(socket.SHUT_RDWR)
        listening.close()
        for name in (where.SOCKET, where.RECORD):
            with contextlib.suppress(OSError):
                (at / name).unlink()
