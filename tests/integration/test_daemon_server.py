"""`hmz server`: a server started apart from the line, reached with its key, and stopped.

Every line is `hmz` run as a program, as it is typed; `easytier-core` is the stand-in, and the
daemon the server holds the runs through is real.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

import pytest

from hmz import home
from hmz.coganchor import easytier
from hmz.daemon import where
from tests.integration.doubles_daemon import hosting, project, until
from tests.integration.doubles_easytier import faked

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from tests.integration.doubles_easytier import Core

pytestmark = pytest.mark.timeout(120)

#: The secret every server here is started with.
_SECRET = "0123456789abcdef"

#: The node every server here is told to meet through; the stand-in reaches none.
_PEER = "tcp://127.0.0.1:11010"


def _hmz(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "hmz", *argv],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


@pytest.fixture
def core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Core]:
    """The stand-in for `easytier-core`, and whatever server a test leaves behind stopped."""
    project(tmp_path, monkeypatch)
    made = faked(tmp_path, monkeypatch)
    with hosting():
        try:
            yield made
        finally:
            with contextlib.suppress(OSError, ValueError, KeyError):
                pid = json.loads((home() / "server.json").read_text())["pid"]
                os.kill(pid, signal.SIGKILL)


def _asked(path: str, key: str) -> object:
    at = f"http://127.0.0.1:{easytier.PORT}"
    asked = urllib.request.Request(  # noqa: S310 -- http, to its own loopback
        at + path,
        headers={
            "Cookie": f"hmz-{easytier.PORT}={key}",
            "Origin": at,
            "Sec-Fetch-Site": "same-origin",
        },
    )
    with urllib.request.urlopen(asked, timeout=10) as answer:  # noqa: S310
        return json.loads(answer.read())


# The one test that starts a server: the port it listens on is fixed, so two would collide.
def test_a_server_serves_its_web_over_easytier_until_stopped(core: Core) -> None:
    started = _hmz(
        "server", "start", "--mode", "p2p", "--secret", _SECRET, "--peer", _PEER
    )
    assert started.returncode == 0, started.stderr
    record = home() / "server.json"
    said = json.loads(record.read_text())
    assert started.stdout == f"hmz server: started (pid {said['pid']})\n"
    assert set(said) == {"pid", "mode", "port", "version"}
    assert said["mode"] == "p2p"
    assert said["port"] == easytier.PORT
    assert record.stat().st_mode & 0o777 == 0o600
    assert _SECRET not in record.read_text()

    # Its web answers with the key its secret derives, and no other.
    assert isinstance(_asked("/api/daemons", easytier.key(_SECRET)), (dict, list))
    with pytest.raises(urllib.error.HTTPError):
        _asked("/api/daemons", easytier.key("fedcba9876543210"))
    # EasyTier serves that port, told the node and given the secret off its command line.
    assert until(core.told)
    ((argv, secret),) = core.told()
    assert secret
    assert "--ipv4" in argv
    assert argv[argv.index("--tcp-whitelist") + 1] == str(easytier.PORT)
    assert argv[argv.index("--peers") + 1] == _PEER
    assert all(_SECRET not in one for one in argv)
    # And is started again where it goes.
    os.kill(json.loads(core.log.read_text())["pid"], signal.SIGKILL)
    assert until(lambda: len(core.told()) == 2, 10)

    again = _hmz(
        "server", "start", "--mode", "p2p", "--secret", _SECRET, "--peer", _PEER
    )
    assert again.returncode == 1
    assert again.stderr == f"hmz: a server is already running (pid {said['pid']})\n"

    stopped = _hmz("server", "stop")
    assert stopped.returncode == 0, stopped.stderr
    assert stopped.stdout == "hmz server: stopped\n"
    assert not record.exists()
    assert not where.alive(said["pid"])
    # The stand-in takes its network down as it is terminated.
    assert until(lambda: not any(core.networks.iterdir()))


@pytest.mark.usefixtures("core")
def test_stopping_no_server_is_refused() -> None:
    stopped = _hmz("server", "stop")
    assert stopped.returncode == 1
    assert stopped.stderr == "hmz: no server is running\n"


@pytest.mark.usefixtures("core")
@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (
            ["--mode", "p2p", "--secret", "short", "--peer", _PEER],
            "A secret must be at least 16 bytes.",
        ),
        (["--mode", "p2p", "--secret", _SECRET], "--peer"),
        (["--mode", "stun", "--secret", _SECRET, "--peer", _PEER], "--mode"),
        (["--secret", _SECRET, "--peer", _PEER], "--mode"),
    ],
)
def test_a_start_missing_what_it_needs_is_a_usage_error(
    argv: list[str], said: str
) -> None:
    started = _hmz("server", "start", *argv)
    assert started.returncode == 2
    assert said in started.stderr
    assert not (home() / "server.json").exists()
