"""A stand-in for `easytier-core`: a network that is a directory, and TCP forwarded through it.

`HUMANIZE_EASYTIER` names it, and it takes what the real one is told by
`hmz.coganchor.easytier`: `--network-name`, `--ipv4` and `--tcp-whitelist` for the serving end,
`--port-forward tcp://127.0.0.1:LOCAL/ADDRESS:PORT` for a joining one, and the network's secret
in `ET_NETWORK_SECRET`. The serving end writes down, in a directory of the test's own under a
name the network's name gives, its address, the one port it lets through and a digest of the
secret, and takes it away again when it is stopped. A joining end listens on its local port and
connects each connection to the serving end's loopback -- where the network it names is there,
its secret is the same, the address is the serving end's and the port is the one let through;
and otherwise closes it, as a network that does not reach is seen from a client. Every run
writes its pid, argv and whether it was given a secret to `easytier.log` beside the directory.

A stand-in for the community's status page, too: an Uptime Kuma server on this machine's
loopback answering its two reads of the status page `easytier` with what the test says, which
`HUMANIZE_EASYTIER_NODES` names.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import os
import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    import pytest

_CORE = """#!{python}
import hashlib, json, os, pathlib, signal, socket, sys, threading

NETWORKS, LOG = pathlib.Path({networks!r}), {log!r}
args, told = sys.argv[1:], {{}}
for at, said in enumerate(args):
    if said.startswith("--") and at + 1 < len(args) and not args[at + 1].startswith("--"):
        told[said] = args[at + 1]
secret = os.environ.get("ET_NETWORK_SECRET", "")
with open(LOG, "a") as log:
    log.write(json.dumps({{"pid": os.getpid(), "argv": args, "secret": bool(secret)}}) + "\\n")
if "--version" in args:
    print("easytier-core 0.0.0-fake")
    sys.exit(0)
name, proof = told["--network-name"], hashlib.sha256(secret.encode()).hexdigest()
held = NETWORKS / name


def pumps(source, sink):
    try:
        while chunk := source.recv(65536):
            sink.sendall(chunk)
    except OSError:
        pass
    for one in (source, sink):
        try:
            one.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def reached(address, port):
    try:
        server = json.loads(held.read_text())
    except (OSError, ValueError):
        return None
    if server["proof"] != proof or server["address"] != address or server["port"] != port:
        return None
    try:
        return socket.create_connection(("127.0.0.1", port), timeout=5)
    except OSError:
        return None


def gone(*_):
    if "--ipv4" in told:
        held.unlink(missing_ok=True)
    sys.exit(0)


signal.signal(signal.SIGTERM, gone)
signal.signal(signal.SIGINT, gone)
if "--ipv4" in told:
    port = int(told["--tcp-whitelist"])
    held.write_text(json.dumps({{"address": told["--ipv4"], "port": port, "proof": proof}}))
    threading.Event().wait()
local, _, there = told["--port-forward"].removeprefix("tcp://").partition("/")
host, _, local_port = local.rpartition(":")
address, _, port = there.rpartition(":")
listening = socket.socket()
listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listening.bind((host, int(local_port)))
listening.listen()
while True:
    near, _ = listening.accept()
    far = reached(address, int(port))
    if far is None:
        near.close()
        continue
    for pair in ((near, far), (far, near)):
        threading.Thread(target=pumps, args=pair, daemon=True).start()
"""


@dataclass(frozen=True)
class Core:
    """The stand-in, and what it has been told.

    Attributes:
      path: It, executable.
      networks: Where a serving end writes its network down.
      log: Where every run writes its pid, argv and whether it had a secret.
    """

    path: Path
    networks: Path
    log: Path

    def told(self) -> list[tuple[list[str], bool]]:
        """Every run so far: what it was told, and whether it was given a secret."""
        if not self.log.exists():
            return []
        runs = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [(run["argv"], run["secret"]) for run in runs]


def faked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Core:
    """Has `HUMANIZE_EASYTIER` name the stand-in.

    Args:
      tmp_path: The test's own directory.
      monkeypatch: What puts `HUMANIZE_EASYTIER` back.

    Returns:
      It.
    """
    made = tmp_path / "easytier"
    made.mkdir()
    core = Core(made / "easytier-core", made / "networks", made / "easytier.log")
    core.networks.mkdir()
    core.path.write_text(
        _CORE.format(
            python=sys.executable, networks=str(core.networks), log=str(core.log)
        )
    )
    core.path.chmod(0o755)
    monkeypatch.setenv("HUMANIZE_EASYTIER", os.fspath(core.path))
    return core


@contextlib.contextmanager
def kuma(
    page: dict[str, Any], beats: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> Generator[http.server.ThreadingHTTPServer]:
    """An Uptime Kuma server with the status page `easytier`, which `HUMANIZE_EASYTIER_NODES` names.

    Args:
      page: What it answers `/api/status-page/easytier` with.
      beats: What it answers `/api/status-page/heartbeat/easytier` with.
      monkeypatch: What puts `HUMANIZE_EASYTIER_NODES` back.

    Yields:
      It, answering on a thread of its own until the block ends; any other path is 404.
    """
    answers = {
        "/api/status-page/easytier": page,
        "/api/status-page/heartbeat/easytier": beats,
    }

    class Answering(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in answers:
                self.send_error(404)
                return
            body = json.dumps(answers[self.path]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 -- as http.server names it
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Answering)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv(
        "HUMANIZE_EASYTIER_NODES", f"http://127.0.0.1:{server.server_port}"
    )
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
