"""`hmz web` stopped from outside: by a signal, or by whatever started it letting go of its stdin.

Each is `hmz web` itself, a process of its own, opening its browser on a stand-in that opens
nothing -- so that the page forwarding a browser is written, and can be found gone.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from hmz import machine

from .doubles_web import PATIENCE

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _stops(tmp_path: Path, stop: Callable[[subprocess.Popen[str]], object]) -> None:
    """Starts `hmz web --attached`, stops it with `stop` once it listens, and checks it let go."""
    started = subprocess.Popen(
        [sys.executable, "-m", "hmz", "web", "--port", "0", "--attached"],
        cwd=tmp_path,
        env={**os.environ, "BROWSER": "true", "DISPLAY": ":0"},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert started.stdout is not None
        said = re.fullmatch(
            r"hmz web: http://127\.0\.0\.1:(\d+)/\?key=\S+\n", started.stdout.readline()
        )
        assert said is not None
        port = int(said[1])
        page = machine() / f"web-{port}.html"
        # Written once the address is said, as the browser is opened on it.
        waited = time.monotonic() + PATIENCE
        while not page.exists():
            assert time.monotonic() < waited, "no page forwarding a browser was written"
            time.sleep(0.05)
        stop(started)
        # Waited on rather than communicated with, which would close stdin itself -- a stop
        # of its own beside the one being tested -- and fails on one closed already.
        started.wait(timeout=PATIENCE)
        assert started.stderr is not None
        errors = started.stderr.read()
    finally:
        if started.poll() is None:
            started.kill()
            started.wait()
        for held in (started.stdin, started.stdout, started.stderr):
            if held is not None:
                held.close()
    assert started.returncode == 0, errors
    assert "Traceback" not in errors
    assert not page.exists()
    with socket.socket() as again:
        again.bind(("127.0.0.1", port))


def test_it_stops_once_its_stdin_closes(tmp_path: Path) -> None:
    def closes(started: subprocess.Popen[str]) -> None:
        assert started.stdin is not None
        started.stdin.close()

    _stops(tmp_path, closes)


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT])
def test_a_signal_stops_it_as_an_interrupt_does(
    tmp_path: Path, signum: signal.Signals
) -> None:
    _stops(tmp_path, lambda started: started.send_signal(signum))
