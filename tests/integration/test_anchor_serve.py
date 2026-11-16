"""The serving half and a client speaking to it, over the serving half's own pipes.

A `coganchor anchor --stdio` and a `RemoteClient` on its stdin and stdout: the protocol, the
filesystem operations, commands run on the target with their streams and signals, TCP opened
from the target, and the fence the target puts around a command.
"""

from __future__ import annotations

import errno
import io
import os
import signal
import stat
import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.fence import ALL, READ
from hmz.coganchor.proto import Op, RemoteOSError, Stream, hello_fences
from tests.integration.doubles_anchor import VIRTUAL, Link, echoing, linked

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from hmz.coganchor.remote import ExecHandle

#: How long anything here may take before it is a hang.
PATIENCE = 30


@pytest.fixture
def link(tmp_path: Path) -> Iterator[Link]:
    """A serving half and a client on its pipes, handshake done."""
    with linked(tmp_path / "target", timeout=PATIENCE) as held:
        yield held


@dataclass
class Ran:
    """How one command run on the target ended, and what it said."""

    result: dict[str, Any] | None
    error: OSError | None
    out: bytes
    err: bytes


def _run(
    link: Link,
    argv: list[str],
    *,
    feeding: bytes = b"",
    fence: dict[str, Any] | None = None,
    then: Callable[[ExecHandle], None] | None = None,
) -> Ran:
    """Runs `argv` on the target in the exported directory and waits for it to end."""
    ended = threading.Event()
    out: list[bytes] = []
    err: list[bytes] = []
    held: dict[str, Any] = {}

    def output(stream: Stream, data: bytes) -> None:
        (err if stream is Stream.STDERR else out).append(data)

    def over(result: dict[str, Any] | None, error: OSError | None) -> None:
        held.update(result=result, error=error)
        ended.set()

    handle = link.client.start_exec(
        argv, cwd=VIRTUAL, env={}, on_output=output, on_exit=over, fence=fence
    )
    if feeding:
        handle.send_stdin(feeding)
    handle.close_stdin()
    if then is not None:
        then(handle)
    assert ended.wait(PATIENCE)
    return Ran(held["result"], held["error"], b"".join(out), b"".join(err))


def test_the_handshake_names_the_exports_and_the_machine(link: Link) -> None:
    info = link.client.info

    assert info["exports"] == [{"virtual": VIRTUAL, "real": str(link.real)}]
    assert info["platform"] == sys.platform
    assert info["pid"] == link.pid


def test_a_file_written_through_the_link_lands_on_the_target_and_reads_back(
    link: Link,
) -> None:
    payload = os.urandom(300_000)

    link.client.write_file(f"{VIRTUAL}/blob.bin", io.BytesIO(payload), mode=0o640)
    sink = io.BytesIO()
    meta = link.client.read_file(f"{VIRTUAL}/blob.bin", sink)

    assert (link.real / "blob.bin").read_bytes() == payload
    assert sink.getvalue() == payload
    assert meta["size"] == len(payload)
    assert stat.S_IMODE((link.real / "blob.bin").stat().st_mode) == 0o640
    assert sorted(one.name for one in link.real.iterdir()) == ["blob.bin"]


def test_a_listing_says_what_each_entry_is(link: Link) -> None:
    (link.real / "dir").mkdir()
    (link.real / "file").write_text("12345")
    (link.real / "link").symlink_to("file")

    entries = {e["name"]: e for e in link.client.listdir(VIRTUAL)["entries"]}

    assert set(entries) == {"dir", "file", "link"}
    assert entries["file"]["size"] == 5
    assert {name: e["kind"] for name, e in entries.items()} == {
        "dir": "dir",
        "file": "file",
        "link": "link",
    }
    assert entries["link"]["target"] == "file"


def test_mutations_through_the_link_are_applied_on_the_target(link: Link) -> None:
    client = link.client
    client.mkdir(f"{VIRTUAL}/a/b", parents=True)
    client.write_file(f"{VIRTUAL}/a/b/f", io.BytesIO(b"hello"))
    client.rename(f"{VIRTUAL}/a/b/f", f"{VIRTUAL}/a/g")
    client.symlink("g", f"{VIRTUAL}/a/l")
    client.link(f"{VIRTUAL}/a/g", f"{VIRTUAL}/a/h")
    client.chmod(f"{VIRTUAL}/a/g", 0o600)
    client.call(Op.TRUNCATE, path=f"{VIRTUAL}/a/g", size=2)
    client.utime(f"{VIRTUAL}/a/g", 1_000_000_000, 2_000_000_000)
    client.rmdir(f"{VIRTUAL}/a/b")

    a = link.real / "a"
    assert sorted(one.name for one in a.iterdir()) == ["g", "h", "l"]
    assert (a / "g").read_bytes() == b"he"
    assert (a / "l").readlink().name == "g"
    assert client.call(Op.READLINK, path=f"{VIRTUAL}/a/l")["target"] == "g"
    assert (a / "g").stat().st_ino == (a / "h").stat().st_ino
    assert stat.S_IMODE((a / "g").stat().st_mode) == 0o600
    assert (a / "g").stat().st_mtime_ns == 2_000_000_000

    client.unlink(f"{VIRTUAL}/a/h")
    assert not (a / "h").exists()


def test_a_missing_path_fails_with_the_targets_own_errno(link: Link) -> None:
    with pytest.raises(RemoteOSError) as failed:
        link.client.call(Op.STAT, path=f"{VIRTUAL}/nope")

    assert failed.value.errno == errno.ENOENT


def test_a_path_outside_every_export_is_refused(link: Link) -> None:
    with pytest.raises(OSError, match=r".") as failed:
        link.client.call(Op.STAT, path="/etc/hosts")
    assert failed.value.errno in (errno.EACCES, errno.EPERM, errno.ENOENT)

    with pytest.raises(OSError, match=r"."):
        link.client.call(Op.STAT, path=f"{VIRTUAL}/../../etc/hosts")


def test_a_request_the_target_does_not_know_leaves_the_link_working(
    link: Link,
) -> None:
    with pytest.raises(OSError, match=r".") as failed:
        link.client.call(Op.STAT)
    assert failed.value.errno == errno.EINVAL

    (link.real / "still").write_text("")
    assert [e["name"] for e in link.client.listdir(VIRTUAL)["entries"]] == ["still"]


def test_a_command_runs_in_the_targets_directory_with_its_own_streams(
    link: Link,
) -> None:
    (link.real / "note").write_text("on the target\n")

    ran = _run(
        link,
        ["/bin/sh", "-c", f"pwd; cat note; cat; echo oops >&2; exit 4 # {VIRTUAL}"],
        feeding=b"from stdin\n",
    )

    assert ran.error is None
    assert ran.result == {"exit_code": 4}
    assert ran.out.decode().splitlines() == [
        str(link.real.resolve()),
        "on the target",
        "from stdin",
    ]
    assert ran.err == b"oops\n"


def test_a_program_the_target_has_not_got_fails_as_missing(link: Link) -> None:
    ran = _run(link, ["/no/such/program"])

    assert ran.result is None
    assert isinstance(ran.error, OSError)
    assert ran.error.errno == errno.ENOENT


def test_a_signal_sent_through_the_link_reaches_the_command(link: Link) -> None:
    ran = _run(
        link,
        ["/bin/sh", "-c", "echo up; exec sleep 30"],
        then=lambda handle: handle.signal(signal.SIGTERM),
    )

    assert ran.result == {"signal": signal.SIGTERM}


def test_a_command_given_a_tty_sees_one(link: Link) -> None:
    ended = threading.Event()
    said: list[bytes] = []

    link.client.start_exec(
        ["/bin/sh", "-c", "test -t 1 && echo tty"],
        cwd=VIRTUAL,
        env={},
        on_output=lambda _stream, data: said.append(data),
        on_exit=lambda _result, _error: ended.set(),
        tty=True,
        winsize=(24, 80),
    ).close_stdin()

    assert ended.wait(PATIENCE)
    assert b"tty" in b"".join(said)


def test_a_tunnel_opened_from_the_target_carries_bytes_both_ways(link: Link) -> None:
    for address in echoing("127.0.0.1"):
        closed = threading.Event()
        got: list[bytes] = []

        def on_data(_stream: Stream, data: bytes, got: list[bytes] = got) -> None:
            got.append(data)

        def on_close(
            _result: dict[str, Any] | None,
            _error: OSError | None,
            closed: threading.Event = closed,
        ) -> None:
            closed.set()

        tunnel = link.client.open_tunnel(*address, on_data, on_close)
        tunnel.send(b"ping")
        tunnel.close_write()

        assert closed.wait(PATIENCE)
        assert b"".join(got) == b"echo:ping"


def _levels(*, online: bool) -> dict[str, Any]:
    """A fence as a target is told it: the levels, drawn again around its own paths."""
    return {"local": ALL, "user": READ, "system": READ, "online": online}


def test_a_fenced_command_runs_inside_the_targets_wall(link: Link) -> None:
    if not hello_fences(link.client.info, net=False):
        pytest.skip("this machine cannot fence a command")
    outside = link.real.parent / "outside"
    outside.mkdir()

    ran = _run(
        link,
        ["/bin/sh", "-c", f"echo ran; touch inside; touch {outside}/escaped"],
        fence=_levels(online=True),
    )

    assert ran.error is None, ran.error
    assert ran.out == b"ran\n"
    assert (link.real / "inside").exists()
    assert not (outside / "escaped").exists()
    assert ran.result != {"exit_code": 0}


def test_an_unfenced_command_runs_without_the_wall(link: Link) -> None:
    outside = link.real.parent / "outside"
    outside.mkdir()

    ran = _run(link, ["/bin/sh", "-c", f"touch {outside}/reached"])

    assert ran.result == {"exit_code": 0}
    assert (outside / "reached").exists()


def test_levels_that_are_no_fences_are_refused(link: Link) -> None:
    ran_at = link.real / "ran"

    ran = _run(
        link,
        ["/bin/sh", "-c", f"touch {ran_at}"],
        fence={"local": "most", "user": READ, "system": READ, "online": True},
    )

    assert isinstance(ran.error, OSError)
    assert not ran_at.exists()
