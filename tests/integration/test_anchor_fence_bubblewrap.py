"""A fence put up with bubblewrap, around a real program, by `hmz internal fence`.

Where this machine has a `bwrap` that starts, a program is run under `--sandbox=bwrap` and is
held to what the fence grants -- its network included, where the one way out is the proxy,
reached through the relay `coganchor` carries loopback across the namespace's edge with, and a
port the program listens on is reached from outside it the same way.
"""

from __future__ import annotations

import contextlib
import json
import os
import select
import signal
import socket
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.fence import BWRAP, NONE, READ, WRITE, Fence, able

if TYPE_CHECKING:
    from pathlib import Path


def _free() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _echoed(sock: socket.socket) -> bytes:
    with sock:
        sock.settimeout(10)
        sock.sendall(b"ping")
        sock.shutdown(socket.SHUT_WR)
        held = b""
        while chunk := sock.recv(4096):
            held += chunk
        return held


# ------------------------------------------------------------------- for real, under bwrap


def _bwraps() -> bool:
    try:
        return sys.platform == "linux" and able(BWRAP)[1]
    except OSError:
        return False


_bwrapped = pytest.mark.skipif(
    not _bwraps(), reason="this machine has no bwrap that starts"
)

#: What the program inside tries, and says it could: each path it reads and writes, and a
#: tunnel through the proxy it was handed to a host the fence does not name.
_SCRIPT = r"""
import json, os, socket, sys
work, outside, secret = sys.argv[1:4]
said = {}
def tried(name, act):
    try:
        act()
        said[name] = True
    except OSError:
        said[name] = False
tried("write scratch", lambda: open(os.path.join(work, "scratch", "made"), "w").close())
tried("write work", lambda: open(os.path.join(work, "made"), "w").close())
tried("read work", lambda: os.listdir(work))
tried("write outside", lambda: open(os.path.join(outside, "made"), "w").close())
tried("read outside", lambda: open(os.path.join(outside, "kept")).read())
tried("read secret", lambda: open(os.path.join(secret, "key")).read())
tried("write secret", lambda: open(os.path.join(secret, "new"), "w").close())
proxy = os.environ.get("HTTPS_PROXY", "")
port = int(proxy.rsplit(":", 1)[1]) if proxy else 0
def ask():
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
        said["proxy said"] = sock.recv(12).decode()
tried("reach proxy", ask)
def direct():
    socket.create_connection(("1.1.1.1", 443), timeout=3).close()
tried("reach internet", direct)
print(json.dumps(said))
"""


@_bwrapped
@pytest.mark.skipif(sys.platform != "linux", reason="bubblewrap is Linux's")
def test_a_program_under_bwrap_is_held_to_its_fence(tmp_path: Path) -> None:
    work, outside = tmp_path / "work", tmp_path / "outside"
    secret = work / "secret"
    secret.mkdir(parents=True)
    (secret / "key").write_text("k")
    (work / "scratch").mkdir()
    outside.mkdir()
    (outside / "kept").write_text("x")
    # The workdir read and not written, so that `/tmp` -- where the test's own directories
    # are -- is not written either.
    fence = Fence.of(
        rules=[(".", READ), ("./scratch", WRITE), ("./secret", NONE)],
        online=False,
        workdir=work,
        home=tmp_path / "nobody",
        hosts=("api.example.org",),
    ).granting(read=[str(tmp_path / "script.py")])
    (tmp_path / "script.py").write_text(_SCRIPT)
    env = dict(os.environ)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        env.pop(name, None)
        env.pop(name.lower(), None)

    done = subprocess.run(
        [
            sys.executable,
            "-Pm",
            "hmz",
            "internal",
            "fence",
            f"--policy={fence.dumps()}",
            "--sandbox=bwrap",
            "--",
            sys.executable,
            "-I",
            str(tmp_path / "script.py"),
            str(work),
            str(outside),
            str(secret),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=work,
        env=env,
    )

    assert done.returncode == 0, done.stderr
    said = json.loads(done.stdout)
    assert said == {
        "write scratch": True,
        "write work": False,
        "read work": True,
        "write outside": False,
        "read outside": False,
        "read secret": False,
        "write secret": False,
        "reach proxy": True,
        "proxy said": "HTTP/1.1 403",
        "reach internet": False,
    }
    assert (work / "scratch" / "made").exists()
    assert not (outside / "made").exists()


@_bwrapped
@pytest.mark.skipif(sys.platform != "linux", reason="bubblewrap is Linux's")
def test_a_written_root_keeps_its_devices_under_bwrap(tmp_path: Path) -> None:
    work = tmp_path / "work"
    (work / "secret").mkdir(parents=True)
    # The carve-out is what sends a fence that writes `/` to a backend at all.
    fence = Fence.of(
        rules=[("/", WRITE), ("./secret", NONE)],
        online=True,
        workdir=work,
        home=tmp_path / "nobody",
    )

    done = subprocess.run(
        [
            sys.executable,
            "-Pm",
            "hmz",
            "internal",
            "fence",
            f"--policy={fence.dumps()}",
            "--sandbox=bwrap",
            "--",
            "sh",
            "-c",
            "echo x >/dev/null && head -c 4 /dev/urandom | wc -c",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=work,
        env=os.environ,
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "4", done.stderr


@_bwrapped
@pytest.mark.skipif(sys.platform != "linux", reason="bubblewrap is Linux's")
def test_a_carve_out_that_is_not_there_is_refused_under_bwrap(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    fence = Fence.of(
        rules=[("/", READ), (".", WRITE), ("./missing", NONE)],
        online=True,
        workdir=work,
        home=tmp_path / "nobody",
    )

    done = subprocess.run(
        [
            sys.executable,
            "-Pm",
            "hmz",
            "internal",
            "fence",
            f"--policy={fence.dumps()}",
            "--sandbox=bwrap",
            "--",
            "true",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=work,
        env=os.environ,
    )

    assert done.returncode == 126
    assert "not there" in done.stderr


@_bwrapped
@pytest.mark.skipif(sys.platform != "linux", reason="bubblewrap is Linux's")
def test_a_port_the_program_listens_on_is_reached_past_a_cut_network(
    tmp_path: Path,
) -> None:
    """As a CLI that serves itself to its driver (kimi's daemon) is, under bubblewrap."""
    work = tmp_path / "work"
    work.mkdir()
    port = _free()
    fence = Fence.of(
        rules=[(".", READ)], online=False, workdir=work, home=tmp_path / "nobody"
    ).granting(listen=[port])
    serve = (
        "import socket\n"
        "s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
        f"s.bind(('127.0.0.1', {port})); s.listen()\n"
        "c, _ = s.accept(); c.sendall(c.recv(4)); c.close()\n"
    )
    held = subprocess.Popen(
        [
            sys.executable,
            "-Pm",
            "hmz",
            "internal",
            "fence",
            f"--policy={fence.dumps()}",
            "--sandbox=bwrap",
            "--",
            sys.executable,
            "-I",
            "-c",
            serve,
        ],
        cwd=work,
        env=os.environ,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # The bridge outside is up as soon as the wrapper is, and waits for the inside.
        for _ in range(100):
            try:
                answered = _echoed(socket.create_connection(("127.0.0.1", port)))
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("nothing listened at the port outside")
        assert answered == b"ping"
        assert held.wait(30) == 0, held.stderr
    finally:
        held.kill()
        held.wait()


@_bwrapped
@pytest.mark.skipif(sys.platform != "linux", reason="bubblewrap is Linux's")
def test_a_program_past_a_cut_network_goes_when_its_wrapper_is_killed(
    tmp_path: Path,
) -> None:
    """The relay the program is started beneath is no place for it to outlive the wrapper."""
    work = tmp_path / "work"
    work.mkdir()
    fence = Fence.of(
        rules=[(".", READ)], online=False, workdir=work, home=tmp_path / "nobody"
    )
    # It says its pid, then holds its output open for as long as it lives.
    stays = "import os, time\nprint(os.getpid(), flush=True)\ntime.sleep(120)\n"
    held = subprocess.Popen(
        [
            sys.executable,
            "-Pm",
            "hmz",
            "internal",
            "fence",
            f"--policy={fence.dumps()}",
            "--sandbox=bwrap",
            "--",
            sys.executable,
            "-I",
            "-c",
            stays,
        ],
        cwd=work,
        env=os.environ,
        stdout=subprocess.PIPE,
    )
    assert held.stdout is not None
    program = int(held.stdout.readline())
    try:
        held.kill()
        held.wait()
        # The output ends once nothing that held it is left: the program among them.
        ended, _, _ = select.select([held.stdout], [], [], 30)
        assert ended, "the program outlived its wrapper"
        assert held.stdout.read() == b""
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(program, signal.SIGKILL)
        held.stdout.close()
