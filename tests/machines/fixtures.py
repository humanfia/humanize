"""What a machine test needs and cannot make for itself: a daemon holding the image, and ways in.

The tests are under `tests/{integration,system}/machines/` and `tests/{integration,system}/
flows/`; this stays here, outside all of them, because the image's name is wanted on either
side of that line -- a system test starts a container of it, and an integration test names it
in a setting it never brings up. Shared rather than written out twice so that the skip a machine
without docker gets is worded once: a second copy that drifted would be a container test
reporting failure on a machine that simply has no daemon running. The `conftest.py` beside
those tests re-exports the fixtures to the tests that want them.

The rest are the other roads to that same daemon, each made by the test and taken down with
it: a TCP port forwarded to its socket, an sshd of the test's own on a loopback port -- reached
by an `ssh` put first on `PATH`, or by an ssh provider written down with everything it takes --
and a docker context kept in a configuration directory of the test's own. Nothing of the user's
`~/.ssh` or `~/.docker` is read or written by any of them. And a `docker` of the test's own that
writes down what it is asked, for the integration tests, which never reach a daemon at all.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import transport

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path

    from hmz.coganchor.transport import Endpoint

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


@dataclass(frozen=True)
class Served:
    """An sshd of the test's own on a loopback port, and what reaches it.

    Attributes:
      port: The port it listens on, on 127.0.0.1.
      key: The key it takes, which nothing but the test holds.
      known: The known-hosts file its host key goes in, the test's own.
    """

    port: int
    key: Path
    known: Path


@contextlib.contextmanager
def _served(tmp_path: Path) -> Generator[Served]:
    """Runs an sshd of the test's own for as long as the block does, or skips saying why."""
    sshd = shutil.which("sshd") or shutil.which(
        "sshd", path="/usr/sbin:/usr/local/sbin"
    )
    if (
        sshd is None
        or shutil.which("ssh") is None
        or shutil.which("ssh-keygen") is None
    ):
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
        yield Served(port, client_key, at / "known_hosts")
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


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
    with _served(tmp_path) as served:
        at = served.key.parent
        ssh = shutil.which("ssh")
        (at / "ssh_config").write_text(
            f"Host {SSH_ALIAS}\n  HostName 127.0.0.1\n  Port {served.port}\n"
            f"  IdentityFile {served.key}\n  IdentitiesOnly yes\n"
            f"  UserKnownHostsFile {served.known}\n  StrictHostKeyChecking no\n"
            "  LogLevel ERROR\n"
        )
        wrapper = at / "bin" / "ssh"
        wrapper.parent.mkdir()
        wrapper.write_text(f'#!/bin/sh\nexec {ssh} -F {at / "ssh_config"} "$@"\n')
        wrapper.chmod(0o755)
        monkeypatch.setenv("PATH", f"{wrapper.parent}{os.pathsep}{os.environ['PATH']}")
        yield f"ssh://{SSH_ALIAS}"


@pytest.fixture
def ssh_provider(daemon: None, tmp_path: Path) -> Iterator[str]:
    """`ssh:NAME`: this machine's daemon, behind an ssh provider written down under NAME.

    The same sshd of the test's own, and nothing put on `PATH`: everything `ssh` has to be told
    to reach it -- the port, the key, the known hosts -- is the provider's, which is what a
    daemon reached as `ssh:<provider>` has to be dialled with.
    """
    from hmz.coganchor.machines import store

    with _served(tmp_path) as served:
        store.write(
            store.SSHProvider(
                name=SSH_ALIAS,
                host="127.0.0.1",
                port=served.port,
                identity_file=str(served.key),
                options={
                    "IdentitiesOnly": "yes",
                    "UserKnownHostsFile": str(served.known),
                    "StrictHostKeyChecking": "no",
                    "LogLevel": "ERROR",
                },
            )
        )
        yield f"ssh:{SSH_ALIAS}"


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


#: The stand-in itself. Global flags are skipped the way docker's parser reads them -- every
#: one of them takes a value but `--tlsverify` -- so the subcommand is found wherever it is.
STANDIN = """\
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["STANDIN_LOG"], "a") as log:
    log.write(json.dumps({"argv": argv, "DOCKER_HOST": os.environ.get("DOCKER_HOST")}))
    log.write("\\n")
at = 0
while argv[at].startswith("-"):
    at += 1 if argv[at] == "--tlsverify" else 2
command, rest = argv[at], argv[at + 1 :]
if command == "run" and "--rm" in rest:
    if "STANDIN_UNPULLED" in os.environ:
        sys.exit(
            "docker: Error response from daemon: pull access denied for typo, "
            "repository does not exist or may require 'docker login'"
        )
    if "STANDIN_OWNER" not in os.environ:
        sys.exit(
            'docker: Error response from daemon: invalid mount config for type "bind": '
            "bind source path does not exist: " + rest[-1]
        )
    print(os.environ["STANDIN_OWNER"])
elif command == "run":
    if "STANDIN_TAKEN" in os.environ:
        sys.exit("docker: Error response from daemon: Conflict. The name is in use")
    with open(rest[rest.index("--cidfile") + 1], "w") as made:
        made.write("c0ffee\\n")
    if "STANDIN_REFUSE" in os.environ:
        sys.exit("docker: Error response from daemon: failed to create task")
    print("c0ffee")
elif command == "info":
    print(json.dumps({
        "ServerVersion": "stand-in",
        "NCPU": int(os.environ.get("STANDIN_NCPU", "8")),
        "MemTotal": int(os.environ.get("STANDIN_MEMORY", str(16 << 30))),
        "DiscoveredDevices": json.loads(os.environ.get("STANDIN_DEVICES", "null")),
        "SecurityOptions": json.loads(os.environ.get("STANDIN_SECURITY", "[]")),
    }))
elif command == "exec":
    if "STANDIN_STOPPED" in os.environ:
        sys.exit("Error response from daemon: container c0ffee is not running")
    moved = os.environ["STANDIN_ROOT"]
    words = [word.replace("/tmp/humanize", moved) for word in rest[2:]]
    os.execvp(words[0], words)
elif command == "logs":
    print("humanize: no python 3.12 or newer on this machine")
elif command == "ps":
    print(os.environ.get("STANDIN_PS", ""))
elif command == "inspect":
    print(os.environ.get("STANDIN_INSPECT", "[]"))
    if "STANDIN_INSPECT_SAYS" in os.environ:
        sys.exit(os.environ["STANDIN_INSPECT_SAYS"])
"""


@dataclass
class Standin:
    """The stand-in on `PATH`, and what it was asked."""

    log: Path
    monkeypatch: pytest.MonkeyPatch

    def said(self) -> list[dict[str, Any]]:
        """Every call so far, in order."""
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def subcommands(self, endpoint: Endpoint) -> list[list[str]]:
        """Every call's words after the global flags, each checked to have carried them."""
        flags = endpoint.docker()[endpoint.docker().index("docker") + 1 :]
        answered: list[list[str]] = []
        for one in self.said():
            argv: list[str] = one["argv"]
            assert argv[: len(flags)] == flags, argv
            answered.append(argv[len(flags) :])
        return answered

    def set(self, name: str, value: str) -> None:
        self.monkeypatch.setenv(name, value)


@pytest.fixture
def standin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standin:
    """A `docker` of the test's own, first on `PATH`."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    docker = bin_ / "docker"
    docker.write_text(f"#!{sys.executable}\n{STANDIN}")
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STANDIN_LOG", str(tmp_path / "docker.log"))
    monkeypatch.setenv("STANDIN_ROOT", str(tmp_path / "container-tmp"))
    # Docker's default here is this machine's, whatever the machine running the tests says.
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    # And a fresh memo of which machines hold the bundle, so each test pays for its own.
    monkeypatch.setattr(transport, "_PUSHED", set[tuple[str, str]]())
    return Standin(tmp_path / "docker.log", monkeypatch)
