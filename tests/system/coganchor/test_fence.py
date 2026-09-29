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
import socket
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
            "-Pm",
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


#: A listener inside the fence: on a port the kernel picks, and on one it was told.
LISTENER = """
import socket, sys
held = socket.socket()
try:
    held.bind(("127.0.0.1", int(sys.argv[1])))
    held.listen()
    print("listening")
except OSError as why:
    print("refused", type(why).__name__)
"""


@networked
def test_a_cut_network_still_lets_a_program_listen_where_the_kernel_says(
    home: Path,
) -> None:
    """A CLI that serves itself on loopback -- agy's language server -- starts offline.

    A port the kernel picks is a listener and reaches nothing. A port the program names is
    still refused, being one somebody outside could be waiting to be served on.
    """
    listener = home / "work" / "listener.py"
    listener.write_text(LISTENER)
    python = sys.executable
    done = _run(
        _fence(home, ALL, READ, READ, online=False),
        f"{python} listener.py 0; {python} listener.py 45679",
        home / "work",
    )
    assert done.stdout.splitlines() == ["listening", "refused PermissionError"], (
        done.stderr
    )


#: Binds and listens on each address it is given as `family,host,port`, one line apiece.
BINDER = """
import errno, socket, sys
for said in sys.argv[1:]:
    family, host, port = said.split(",")
    held = socket.socket(socket.AF_INET6 if family == "6" else socket.AF_INET)
    try:
        held.bind((host, int(port)))
        held.listen()
        print("listening")
    except OSError as why:
        print("refused", errno.errorcode.get(why.errno, why.errno))
    finally:
        held.close()
unbound = socket.socket()
try:
    unbound.listen()
    print("listening")
except OSError as why:
    print("refused", errno.errorcode.get(why.errno, why.errno))
unix = socket.socket(socket.AF_UNIX)
unix.bind("unix.sock")
unix.listen()
print("listening")
"""


def _lan() -> str | None:
    """An address of this machine's that is not loopback, where it has one."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(
            ("192.0.2.1", 9)
        )  # routed, never sent: a datagram socket only chooses
        host = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return None if host.startswith("127.") else host


def _ipv6() -> bool:
    try:
        with socket.socket(socket.AF_INET6) as probe:
            probe.bind(("::1", 0))
    except OSError:
        return False
    return True


@networked
def test_a_cut_network_lets_a_program_listen_on_loopback_and_nowhere_else(
    home: Path,
) -> None:
    """Every address but loopback is refused at `bind`, and a socket bound to none at `listen`.

    kimi's daemon is the port named in `listen`, which is bound on loopback like any other.
    """
    named = _free()
    lan = _lan()
    six = _ipv6()
    asked = [
        ("4,127.0.0.1,0", "listening"),
        ("4,0.0.0.0,0", "refused EACCES"),
        (f"4,127.0.0.1,{named}", "listening"),
        (f"4,0.0.0.0,{named}", "refused EACCES"),
        *([(f"4,{lan},0", "refused EACCES")] if lan else []),
        *(
            [
                ("6,::1,0", "listening"),
                ("6,::ffff:127.0.0.1,0", "listening"),
                ("6,::,0", "refused EACCES"),
            ]
            if six
            else []
        ),
    ]
    (home / "work" / "binder.py").write_text(BINDER)
    fence = _fence(home, ALL, READ, READ, online=False).granting(listen=[named])
    done = _run(
        fence,
        f"{sys.executable} binder.py {' '.join(said for said, _ in asked)}",
        home / "work",
    )
    assert done.stdout.splitlines() == [
        *(then for _, then in asked),
        "refused EACCES",  # listening unbound, which is listening on every address
        "listening",  # a Unix socket, which is not the network
    ], done.stderr


#: Races a thread rewriting the address a `bind` reads, then one swapping the descriptor a
#: `listen` names, and says how many sockets ended up listening off loopback.
RACER = """
import ctypes, os, socket, sys, threading

libc = ctypes.CDLL(None, use_errno=True)
def sin(host):
    family = socket.AF_INET.to_bytes(2, sys.byteorder)
    return family + bytes(2) + socket.inet_aton(host) + bytes(8)
NEAR, WIDE = sin("127.0.0.1"), sin("0.0.0.0")
address = ctypes.create_string_buffer(NEAR, 16)
stop = threading.Event()

def rewrite():
    while not stop.is_set():
        ctypes.memmove(address, WIDE, 16)
        ctypes.memmove(address, NEAR, 16)

def racing(target):
    stop.clear()
    thread = threading.Thread(target=target)
    thread.start()
    return thread

def wide(held):
    return held.getsockname()[0] != "127.0.0.1"

def listening(held):
    return held.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)

escaped, raced = 0, None
thread = racing(rewrite)
for _ in range(int(sys.argv[1])):
    held = socket.socket()
    if libc.bind(held.fileno(), address, 16) == 0:
        libc.listen(held.fileno(), 1)
        if wide(held) and raced is None:
            raced = held
            continue
    escaped += wide(held) and listening(held)
    held.close()
stop.set()
thread.join()

if raced is not None:
    near = socket.socket()
    near.bind(("127.0.0.1", 0))
    slot = os.dup(near.fileno())
    def swap():
        while not stop.is_set():
            os.dup2(raced.fileno(), slot)
            os.dup2(near.fileno(), slot)
    thread = racing(swap)
    for _ in range(int(sys.argv[1])):
        libc.listen(slot, 1)
    stop.set()
    thread.join()
    escaped += listening(raced)
print("raced" if raced is not None else "not raced", escaped)
"""


@networked
def test_no_race_gets_a_listener_off_loopback(home: Path) -> None:
    """`bind` is let run once checked, so a rewrite may slip through it; `listen` may not."""
    (home / "work" / "racer.py").write_text(RACER)
    done = _run(
        _fence(home, ALL, READ, READ, online=False),
        f"{sys.executable} racer.py 3000",
        home / "work",
    )
    assert done.stdout.split()[-1:] == ["0"], (done.stdout, done.stderr)


def _free() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


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
        [sys.executable, "-Pm", "hmz", "internal", "fence", "--policy={}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=home,
        env=os.environ,
    )
    assert done.returncode == 2
    assert "no program given" in done.stderr
