"""What every test of a held workspace needs: a project of its own, and its runs held there.

A daemon is one per workspace, so a test that holds one has to be standing somewhere no other
test is -- and has to let go of it however it ended, or the next test finds a host it did not
start.

The tests themselves are under `tests/unit/daemon/` and `tests/integration/daemon/`, and these
fixtures stay here because they are what the tests are written against rather than tests,
and there is one copy of each because a second that drifted would be a second answer to where
this workspace's daemon is. `tests/integration/daemon/conftest.py` re-exports what it needs
from here.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Iterator
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
    """This workspace held by a daemon of an older humanize, which no frontend reaches.

    What such a one leaves beside its socket says nothing of a protocol, and what it answers
    a frontend with is nothing at all: a note written with no `protocol`, and a socket that
    takes each connection and closes it again, in this process and gone again afterwards.
    """
    import os
    import socket
    import threading

    at = where.at()
    at.mkdir(parents=True, exist_ok=True)
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with where.reached(at) as reaching:
        listening.bind(reaching)
    listening.listen(8)
    where.wrote(
        at,
        {
            "pid": os.getpid(),
            "workspace": str(workspace),
            "started": "2026-01-01T00:00:00Z",
        },
    )

    def closes() -> None:
        while True:
            try:
                one, _ = listening.accept()
            except OSError:
                return
            one.close()

    threading.Thread(target=closes, daemon=True, name="older-daemon").start()
    found = daemon.running()
    assert found is not None
    assert not found.protocol
    try:
        yield found
    finally:
        with contextlib.suppress(OSError):
            listening.shutdown(socket.SHUT_RDWR)
        listening.close()
        for name in (where.SOCKET, where.RECORD):
            with contextlib.suppress(OSError):
                (at / name).unlink()
