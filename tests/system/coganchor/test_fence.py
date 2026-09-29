"""`hmz internal fence`, walling a real shell in with this kernel's Landlock and seccomp.

Each test builds a fence the way a flow's permission does, runs `sh -c` inside it through the
real command, and reads back what the shell could and could not do. A system test because the
other side is the kernel: `tests/tiers.py` puts real Landlock and seccomp in this tree, and a
kernel too old for what a test needs skips it aloud. The network is a loopback server of the
test's own, so that nothing here depends on the internet being there -- except the one test
that asks a host nobody listed, which the proxy refuses before anything leaves the machine.
"""

from __future__ import annotations

import dataclasses
import http.server
import os
import subprocess
import sys
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.fence import ALL, NONE, READ, Fence
from hmz.coganchor.linux import landlock
from hmz.flows import Permission, PermissionKind
from hmz.runtime.flowing import harnessing

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    not landlock.available(), reason="this kernel has no Landlock"
)
networked = pytest.mark.skipif(
    not landlock.available(net=True),
    reason=f"this kernel speaks Landlock ABI {landlock.abi()}; cutting TCP needs 4",
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A home of the test's own, with a workdir in it and a file outside both."""
    (tmp_path / "home" / "work").mkdir(parents=True)
    (tmp_path / "home" / "notes").write_text("mine\n")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret").write_text("theirs\n")
    return tmp_path / "home"


def _fence(home: Path, local: str, user: str, system: str, *, online: bool) -> Fence:
    return Fence.of(
        local=local,
        user=user,
        system=system,
        online=online,
        workdir=home / "work",
        home=home,
    )


def _run(fence: Fence, script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "hmz",
            "internal",
            "fence",
            f"--policy={fence.dumps()}",
            "--",
            "sh",
            "-c",
            script,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_a_home_that_may_only_be_read_is_not_written(home: Path) -> None:
    fence = _fence(home, ALL, READ, READ, online=True)
    done = _run(
        fence, f"cat {home}/notes; touch {home}/new || echo refused", home / "work"
    )
    assert done.stdout.splitlines() == ["mine", "refused"], done.stderr
    assert not (home / "new").exists()


def test_the_system_that_may_not_be_touched_is_not_read(home: Path) -> None:
    fence = _fence(home, ALL, READ, NONE, online=True)
    secret = home.parent / "outside" / "secret"
    done = _run(
        fence,
        f"cat {secret} || echo refused; cat /etc/machine-id >/dev/null || echo refused;"
        " ls /usr/bin >/dev/null && echo ran",
        home / "work",
    )
    # The shell still runs, and reads what any program needs, and nothing else of the system.
    assert done.stdout.splitlines() == ["refused", "refused", "ran"], done.stderr


def test_the_default_permission_writes_the_workdir_and_the_scratch(home: Path) -> None:
    fence = harnessing.fenced(
        Permission(),
        workdir=str(home / "work"),
        home=str(home),
        profile=None,
        environ={},
    )
    done = _run(
        fence,
        'echo ok > ./probe && echo x > "$TMPDIR/x" && cat ./probe "$TMPDIR/x";'
        f" touch {home}/nope || echo refused; touch /etc/nope || echo refused",
        home / "work",
    )
    assert done.stdout.splitlines() == ["ok", "x", "refused", "refused"], done.stderr
    assert (home / "work" / "probe").read_text() == "ok\n"


def test_humanize_itself_runs_inside_the_narrowest_fence(home: Path) -> None:
    # Its supervisors -- `hmz internal cred`, `hook`, `tools` -- run inside the fence too.
    fence = _fence(home, NONE, NONE, NONE, online=True)
    done = _run(
        fence,
        f"{sys.executable} -m hmz internal cred --help >/dev/null && echo ok",
        home,
    )
    assert done.stdout.strip() == "ok", done.stderr


def test_the_program_exits_with_its_own_status(home: Path) -> None:
    fence = _fence(home, ALL, READ, READ, online=True)
    assert _run(fence, "exit 3", home / "work").returncode == 3
    assert _run(fence, "kill -TERM $$", home / "work").returncode == 128 + 15


class _Hello(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"hello")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args


@pytest.fixture
def server() -> Iterator[int]:
    """A loopback HTTP server, and the port it is on."""
    held = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Hello)
    threading.Thread(target=held.serve_forever, daemon=True).start()
    try:
        yield held.server_address[1]
    finally:
        held.shutdown()
        held.server_close()


#: A client inside the fence: through the proxy it was handed, or around it.
CLIENT = """
import socket, sys, urllib.request
how, url = sys.argv[1], sys.argv[2]
try:
    if how == "udp":
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print("opened")
    else:
        opener = urllib.request.build_opener(
            *([urllib.request.ProxyHandler({})] if how == "direct" else [])
        )
        print(opener.open(url, timeout=10).read().decode())
except Exception as why:
    print("refused", type(why).__name__)
"""


@networked
def test_a_cut_network_reaches_only_the_hosts_it_was_left(
    home: Path, server: int
) -> None:
    fence = dataclasses.replace(
        _fence(home, ALL, READ, READ, online=False), hosts=(f"localhost:{server}",)
    )
    client = home / "work" / "client.py"
    client.write_text(CLIENT)
    python = sys.executable
    done = _run(
        fence,
        f"{python} client.py proxied http://localhost:{server}/;"
        f" {python} client.py direct http://127.0.0.1:{server}/;"
        f" {python} client.py proxied http://example.com/;"
        f" {python} client.py udp x",
        home / "work",
    )
    said = done.stdout.splitlines()
    assert said[0] == "hello", done.stderr
    # Around the proxy, the loopback server is a port Landlock does not let be connected to.
    assert said[1].startswith("refused"), said
    # Through it, a host nobody listed is refused by the proxy.
    assert said[2] == "refused HTTPError", said
    # And a protocol Landlock cannot see is not let open a socket at all.
    assert said[3].startswith("refused PermissionError"), said


@networked
def test_offline_a_real_host_that_is_not_listed_is_refused(home: Path) -> None:
    fence = harnessing.fenced(
        Permission(online=PermissionKind.NONE),
        workdir=str(home / "work"),
        home=str(home),
        profile=None,
        environ={},
    )
    done = _run(
        fence,
        "curl -sS -m 10 -o /dev/null https://example.com && echo reached || echo refused",
        home / "work",
    )
    if "curl: not found" in done.stderr:
        pytest.skip("no curl here")
    assert done.stdout.strip() == "refused", done.stderr


def test_a_fence_this_kernel_cannot_hold_runs_nothing(home: Path) -> None:
    if landlock.available(net=True):
        pytest.skip(
            "this kernel can cut the network, so the refusal cannot be seen here"
        )
    fence = _fence(home, ALL, READ, READ, online=False)
    done = _run(fence, "touch ran", home / "work")
    assert done.returncode == 126
    assert not (home / "work" / "ran").exists()


def test_the_wrapper_needs_a_program(home: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "hmz", "internal", "fence", "--policy={}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=home,
        env=os.environ,
    )
    assert done.returncode == 2
    assert "no program given" in done.stderr
