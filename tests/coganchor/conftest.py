"""Shared fixtures.

Shared across tiers rather than within a directory. The tests that ask for these are in
`tests/integration/coganchor` and `tests/system/coganchor`, each of which names the ones it
needs in a `conftest.py` of its own; `tests/unit/coganchor` asks for none of them, which is
most of what makes those tests unit tests. One definition however many trees reach for it is
why this file stayed put when the tests moved out from under it.

Every end-to-end test runs three directories apart:

``target``
    Stands in for the target's copy of the project. Only the serving half
    touches it.
``mirror``
    The local mirror. Starts empty.
``workspace``
    The virtual path both sides use to name the project.  It exists on neither
    machine, so any correct read proves the data came through the target.

That separation is what makes the assertions meaningful: if interception ever
silently fell back to local execution, the tests would read an empty directory.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.proto import Channel
from hmz.coganchor.remote import RemoteClient
from hmz.coganchor.serve.exports import ExportTable
from hmz.coganchor.serve.server import Server
from tests.supervising import WITHOUT

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: The virtual workspace path.  Deliberately not creatable without root, so it
#: cannot accidentally resolve on either side.
VIRTUAL_WORKSPACE = "/coganchor-project"

DEFAULT_TIMEOUT = 90


@dataclass(frozen=True)
class Anchorage:
    """A configured coganchor session under test."""

    target: Path
    mirror: Path
    workspace: str = VIRTUAL_WORKSPACE

    def seed(self, files: dict[str, str]) -> None:
        """Create files on the target before the agent starts."""
        for name, content in files.items():
            path = self.target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def run(
        self,
        *command: str,
        stdin: bytes = b"",
        timeout: int = DEFAULT_TIMEOUT,
        **settings: Any,
    ) -> subprocess.CompletedProcess[str]:
        """Run ``command`` as the agent under full interception.

        Spawned the way a flow spawns it, through :meth:`AnchorConfig.command`, so the
        settings this suite drives coganchor with are the ones an anchored agent renders.
        """
        config = AnchorConfig(
            target=f"local:{self.target}",
            workspace=self.workspace,
            shadow=str(self.mirror),
            **settings,
        )
        completed = subprocess.run(
            config.command(command),
            input=stdin,
            capture_output=True,
            timeout=timeout,
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
            check=False,
        )
        return _decode(completed)

    def shell(
        self, script: str, *, stdin: bytes = b"", timeout: int = DEFAULT_TIMEOUT
    ) -> subprocess.CompletedProcess[str]:
        """Run a bash script as the agent."""
        return self.run("bash", "-c", script, stdin=stdin, timeout=timeout)

    def target_text(self, name: str) -> str:
        return (self.target / name).read_text()


def _decode(
    result: subprocess.CompletedProcess[bytes],
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        result.stdout.decode("utf-8", "replace"),
        result.stderr.decode("utf-8", "replace"),
    )


@pytest.fixture
def anchorage(tmp_path: Path) -> Anchorage:
    """A fresh target/mirror pair for one test.

    The agent half of a session is a seccomp filter and a ptrace supervisor, so a machine
    that cannot trace cannot have one -- which is why every test that asks for this is in
    `tests/system/coganchor`, and why what it does about a kernel that will not trace is
    skip. The serving half is portable on purpose and is reached through `link` below, which
    asks nothing of the kernel and is therefore what the offline tests in
    `tests/integration/coganchor` are written against.

    Neither of those trees is this one. No test lives beside these fixtures any more, and a
    fixture is visible only under the conftest that declares it, so each tier takes the one
    it needs back by name in a `conftest.py` of its own -- `anchorage` there, `link` there,
    and `echo_server` in both.
    """
    if WITHOUT:
        pytest.skip(WITHOUT)
    target = tmp_path / "target"
    mirror = tmp_path / "mirror"
    target.mkdir()
    mirror.mkdir()
    return Anchorage(target=target, mirror=mirror)


#: Virtual root the unit tests export, as opposed to the end-to-end workspace.
VIRTUAL_EXPORT = "/project"


@dataclass(frozen=True)
class Link:
    """A client talking to an in-process server over a socketpair."""

    client: RemoteClient
    target: Path


@pytest.fixture
def link(tmp_path: Path) -> Iterator[Link]:
    """Both halves wired together in one process, without a subprocess or a port."""
    target = tmp_path / "target"
    target.mkdir()
    left, right = socket.socketpair()
    server = Server(
        Channel.from_socket(right), ExportTable.parse([f"{VIRTUAL_EXPORT}:{target}"])
    )
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()

    client = RemoteClient(Channel.from_socket(left))
    client.start()
    yield Link(client, target)
    client.close()
    thread.join(timeout=5)


def _routable_address() -> str:
    """An address on this host that is not loopback, or skip."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1; no packet is sent
        address = str(probe.getsockname()[0])
    except OSError:
        pytest.skip("no routable address on this host")
    finally:
        probe.close()
    if address.startswith("127."):
        pytest.skip("only loopback is available on this host")
    return address


@pytest.fixture
def echo_server() -> Iterator[tuple[str, int]]:
    """A TCP server on a non-loopback address that echoes what it receives.

    Not loopback, because loopback is the one thing a session leaves alone: a proxy's
    decision is only visible against an address it would act on. Nothing here leaves the
    machine -- it is this host's own interface, bound and connected to from this host -- but
    a machine with no interface but loopback has nowhere to put it, and is skipped.

    Here rather than beside the tests because those are now two files: the decision is made
    over a `socketpair` in `tests/integration/coganchor/test_netproxy.py`, and made again by
    a traced agent's own `connect` in `tests/system/coganchor/test_netproxy.py`.
    """
    host = _routable_address()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, 0))
    listener.listen(8)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                while data := connection.recv(4096):
                    connection.sendall(b"echo:" + data)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield listener.getsockname()
    stop.set()
    listener.close()
    thread.join(timeout=2)
