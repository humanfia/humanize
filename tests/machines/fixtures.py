"""What a machine test needs and cannot make for itself: a daemon holding the image, and ways in.

The tests are under `tests/integration/machines/` and `tests/system/machines/`; this stays
here, outside both, because the image's name is wanted on either side of that line -- a system
test starts a container of it, and an integration test names it in a setting it never brings
up. Shared rather than written out twice so that the skip a machine without docker gets is
worded once: a second copy that drifted would be a container test reporting failure on a
machine that simply has no daemon running. `tests/system/machines/conftest.py` re-exports the
fixtures to the tests that want them.

The rest are the other roads to that same daemon, each made by the test and taken down with
it: a TCP port forwarded to its socket, an sshd of the test's own on a loopback port, and a
docker context kept in a configuration directory of the test's own. Nothing of the user's
`~/.ssh` or `~/.docker` is read or written by any of them.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import socket
import subprocess
import threading
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: Small, and has the `python3` a target needs. Pulled by hand rather than by the test, so a
#: machine without it skips instead of spending a minute on a download.
IMAGE = "python:3.12-slim"

#: What the sshd of the test's own is reached by, through the `ssh` told about it.
SSH_ALIAS = "hmz-docker-sshd"


@pytest.fixture
def daemon() -> None:
    """A docker daemon holding the image, or a skip: these tests run a container for real."""
    try:
        ready = subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, check=False
        )
    except OSError as reason:
        pytest.skip(f"needs the docker command: {reason}")
    if ready.returncode != 0:
        pytest.skip(f"needs a docker daemon holding {IMAGE}")


def socket_of_the_daemon() -> str:
    """The socket docker's default here listens on, as `unix:///PATH`, or a skip."""
    said = subprocess.run(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    host = said.stdout.strip()
    if said.returncode != 0 or not host.startswith("unix:///"):
        pytest.skip(f"docker's default here is not a socket: {host or said.stderr}")
    return host


def _pump(source: socket.socket, sink: socket.socket) -> None:
    """Carries one direction until it ends, then says so to the other side."""
    with contextlib.suppress(OSError):
        while said := source.recv(1 << 16):
            sink.sendall(said)
    with contextlib.suppress(OSError):
        sink.shutdown(socket.SHUT_WR)


@pytest.fixture
def forwarded(daemon: None) -> Iterator[str]:
    """`tcp://127.0.0.1:PORT`, carried byte for byte to the daemon's own socket.

    A thread of the test's own rather than `socat`, which is not on every machine; and plain
    TCP on loopback, which is what a daemon told to listen on a port answers with.
    """
    path = socket_of_the_daemon().removeprefix("unix://")
    listener = socket.create_server(("127.0.0.1", 0))
    held: list[socket.socket] = [listener]

    def accepting() -> None:
        while True:
            try:
                near, _ = listener.accept()
            except OSError:
                return  # the listener was closed, which is the fixture ending
            far = socket.socket(socket.AF_UNIX)
            try:
                far.connect(path)
            except OSError:
                near.close()
                far.close()
                continue
            held.extend((near, far))
            for source, sink in ((near, far), (far, near)):
                threading.Thread(target=_pump, args=(source, sink), daemon=True).start()

    threading.Thread(target=accepting, daemon=True).start()
    try:
        yield f"tcp://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        for one in held:
            with contextlib.suppress(OSError):
                one.close()


def _keyed(at: Path) -> Path:
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(at)],
        check=True,
        capture_output=True,
    )
    return at


@pytest.fixture
def sshd(
    daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """`ssh://ALIAS`: this machine's daemon, reached by docker's own ssh transport.

    An sshd of the test's own on a loopback port, with keys made for it, and an `ssh` put first
    on `PATH` that is told about them -- which is the `ssh` docker runs, docker having no way of
    its own to be handed a configuration. The far side runs `docker system dial-stdio` as this
    user, so what it reaches is the daemon the other tests reach.
    """
    sshd = shutil.which("sshd") or shutil.which(
        "sshd", path="/usr/sbin:/usr/local/sbin"
    )
    ssh = shutil.which("ssh")
    if sshd is None or ssh is None or shutil.which("ssh-keygen") is None:
        pytest.skip("needs ssh, ssh-keygen and an sshd to start one of the test's own")
    at = tmp_path / "sshd"
    at.mkdir()
    host_key, client_key = _keyed(at / "host_key"), _keyed(at / "client_key")
    shutil.copy(f"{client_key}.pub", at / "authorized_keys")
    with socket.socket() as probing:
        probing.bind(("127.0.0.1", 0))
        port = int(probing.getsockname()[1])
    (at / "sshd_config").write_text(
        f"Port {port}\nListenAddress 127.0.0.1\nHostKey {host_key}\n"
        f"AuthorizedKeysFile {at / 'authorized_keys'}\nPidFile {at / 'sshd.pid'}\n"
        "UsePAM no\nStrictModes no\nPasswordAuthentication no\n"
        "KbdInteractiveAuthentication no\nPubkeyAuthentication yes\n"
    )
    (at / "ssh_config").write_text(
        f"Host {SSH_ALIAS}\n  HostName 127.0.0.1\n  Port {port}\n"
        f"  IdentityFile {client_key}\n  IdentitiesOnly yes\n"
        f"  UserKnownHostsFile {at / 'known_hosts'}\n  StrictHostKeyChecking no\n"
        "  LogLevel ERROR\n"
    )
    wrapper = at / "bin" / "ssh"
    wrapper.parent.mkdir()
    wrapper.write_text(f'#!/bin/sh\nexec {ssh} -F {at / "ssh_config"} "$@"\n')
    wrapper.chmod(0o755)
    server = subprocess.Popen(
        [sshd, "-D", "-e", "-f", str(at / "sshd_config")],
        stdout=subprocess.DEVNULL,
        stderr=(at / "sshd.log").open("w"),
    )
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    said = (at / "sshd.log").read_text().strip()
                    pytest.skip(f"an sshd of the test's own would not start: {said}")
                time.sleep(0.1)
        monkeypatch.setenv("PATH", f"{wrapper.parent}{os.pathsep}{os.environ['PATH']}")
        yield f"ssh://{SSH_ALIAS}"
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


@pytest.fixture
def context(daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """`context:NAME`, a docker context for this machine's daemon, kept where the test says.

    In a `DOCKER_CONFIG` of the test's own, so the user's own contexts are neither read nor
    added to, and gone with the directory.
    """
    host = socket_of_the_daemon()
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path / "docker-config"))
    made = subprocess.run(
        ["docker", "context", "create", "hmz-machines", "--docker", f"host={host}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if made.returncode != 0:
        pytest.skip(f"docker would not make a context: {made.stderr.strip()}")
    return "context:hmz-machines"
