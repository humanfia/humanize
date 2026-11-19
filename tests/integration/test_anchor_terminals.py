"""Terminals and file browsing, as a person beside a run uses an environment, for real.

A directory here runs its terminal on a pty this process forks; an ssh host is reached
through the fake `ssh` in `doubles_anchor`, which runs coganchor's serving half on this
machine, so the terminal there is a pty that half opens, resized over the wire.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import time
from typing import TYPE_CHECKING

import pytest

from hmz.flows import EnvError, EnvFileNotFound
from hmz.runtime.flowing.environing import MachineEnvDriver
from hmz.runtime.flowing.environments import local_env, open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from tests.integration.doubles_anchor import fakes

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from hmz.runtime.flowing.spi import EnvPty

PATIENCE = 30.0

#: Python warns of any fork in a process with threads, as this one has; the child a pty is
#: forked into runs only `ptyprocess`'s few steps to its `exec`.
pytestmark = pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded, use of forkpty:DeprecationWarning"
)


@pytest.fixture
def work(tmp_path: Path) -> Path:
    held = tmp_path / "work"
    held.mkdir()
    return held.resolve()


@pytest.fixture(params=["local", "ssh"])
async def driver(
    request: pytest.FixtureRequest,
    work: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[MachineEnvDriver]:
    if request.param == "local":
        made = local_env(work)
    else:
        fakes(tmp_path, monkeypatch)
        (spec,) = parse_envs([f"work=ssh@[box-{tmp_path.name}]{work}"])
        made = open_env(spec)
        await probe(made)
    assert isinstance(made, MachineEnvDriver)
    try:
        yield made
    finally:
        await made.close()


async def _until(pty: EnvPty, seen: bytearray, pattern: bytes) -> re.Match[bytes]:
    """Reads what the terminal writes until `pattern` turns up in it, keeping all of it."""
    async with asyncio.timeout(PATIENCE):
        while (found := re.search(pattern, seen)) is None:
            piece = await pty.read()
            if not piece:
                pytest.fail(f"the terminal ended before {pattern!r}: {bytes(seen)!r}")
            seen += piece
    del seen[: found.end()]
    return found


async def _drained(pty: EnvPty) -> bytes:
    """Everything the terminal writes until it ends."""
    said = b""
    async with asyncio.timeout(PATIENCE):
        while piece := await pty.read():
            said += piece
    return said


async def test_a_terminal_is_typed_at_resized_and_exits(
    driver: MachineEnvDriver, work: Path
) -> None:
    pty = await driver.pty(["/bin/sh"], cols=80, rows=24)
    seen = bytearray()

    await pty.write(b"stty size; pwd -P; echo $TERM\n")
    await _until(pty, seen, rb"24 80\r\n")
    await _until(pty, seen, re.escape(str(work).encode()) + rb"\r\n")
    await _until(pty, seen, rb"xterm-256color\r\n")
    await pty.resize(132, 50)
    await pty.write(b"stty size\n")
    await _until(pty, seen, rb"50 132\r\n")
    await pty.write(b"echo $((6 * 7))\n")
    await _until(pty, seen, rb"42\r\n")
    await pty.write(b"exit 5\n")
    await _drained(pty)

    assert await pty.wait() == 5
    await pty.kill()


async def test_what_a_terminal_prints_and_nobody_reads_waits_in_the_terminal(
    driver: MachineEnvDriver,
) -> None:
    # About 10 MiB, which is more than is kept unread of a terminal anywhere.
    most = 1_500_000
    counting = f"awk 'BEGIN {{ for (n = 1; n <= {most}; n++) print n }}'"
    pty = await driver.pty(
        ["/bin/sh", "-c", f"stty -echo; echo ready; {counting}; echo E-N-D"],
        cols=80,
        rows=24,
    )
    seen = bytearray()
    await _until(pty, seen, rb"ready\r\n")

    await asyncio.sleep(3.0)  # nobody reads, as when every viewer is far behind
    # However long all of it takes a slow machine to read, as long as it keeps coming.
    while piece := await asyncio.wait_for(pty.read(), PATIENCE):
        seen += piece
    said = bytes(seen)

    # A line whose writing a full terminal held up may be ended `\r\r\n`, as macOS ends it.
    lines = re.split(rb"\r+\n", said)
    assert lines[-2:] == [b"E-N-D", b""]
    assert len(lines) == most + 2, "some of what it printed was let go of"
    assert lines[:most] == [b"%d" % n for n in range(1, most + 1)]
    assert await pty.wait() == 0


async def test_the_login_shell_is_opened_with_no_program(
    driver: MachineEnvDriver,
) -> None:
    pty = await driver.pty(None, cols=80, rows=24)
    seen = bytearray()

    await pty.write(b"echo login-$((40 + 2))\n")
    await _until(pty, seen, rb"login-42")
    await pty.kill()

    assert await pty.wait() > 128


async def test_killing_a_terminal_kills_what_runs_in_its_foreground(
    driver: MachineEnvDriver, work: Path
) -> None:
    pty = await driver.pty(["/bin/sh"], cols=80, rows=24)
    seen = bytearray()
    await pty.write(b"sh -c 'echo $$ > held; echo started; exec sleep 300'\n")
    await _until(pty, seen, rb"started\r\n")
    held = int((work / "held").read_text())

    await pty.kill()

    assert await pty.wait() == 128 + 9
    assert await asyncio.to_thread(_gone, held)


async def test_killing_a_terminal_here_kills_its_background_jobs_too(
    work: Path,
) -> None:
    driver = local_env(work)
    try:
        pty = await driver.pty(["/bin/sh", "-i"], cols=80, rows=24)
        seen = bytearray()
        await pty.write(b"set -m; sleep 300 & echo $! > held; echo st''arted\n")
        await _until(pty, seen, rb"started\r\n")
        held = int((work / "held").read_text())

        await pty.kill()

        assert await pty.wait() == 128 + 9
        assert await asyncio.to_thread(_gone, held)
    finally:
        await driver.close()


async def test_closing_the_environment_kills_its_terminals(
    driver: MachineEnvDriver,
) -> None:
    pty = await driver.pty(
        ["/bin/sh", "-c", "echo up; exec sleep 300"], cols=80, rows=24
    )
    await _until(pty, bytearray(), rb"up")

    await driver.close()

    async with asyncio.timeout(PATIENCE):
        assert await pty.wait() == 128 + 9
    with pytest.raises(EnvError, match="closed"):
        await driver.pty(None, cols=80, rows=24)


async def test_a_program_that_is_not_there_is_said_so(
    driver: MachineEnvDriver,
) -> None:
    try:
        pty = await driver.pty(["no-such-program-anywhere"], cols=80, rows=24)
    except EnvFileNotFound:
        return  # here, where it is looked for before it is started
    assert b"no-such-program-anywhere" in await _drained(pty)
    assert await pty.wait() == 127


async def test_files_are_listed_looked_at_moved_and_removed(
    driver: MachineEnvDriver, work: Path
) -> None:
    (work / "src").mkdir()
    (work / "src" / "main.py").write_text("print(1)\n")
    (work / "b.txt").write_text("bee")
    (work / "link").symlink_to("b.txt")

    listed = await driver.list(".")

    assert [(one.name, one.kind) for one in listed] == [
        ("src", "dir"),
        ("b.txt", "file"),
        ("link", "link"),
    ]
    assert listed[2].target == "b.txt"
    seen = await driver.stat("b.txt")
    assert (seen.size, seen.kind) == (3, "file")
    assert abs(seen.mtime - (work / "b.txt").stat().st_mtime) < 1e-3

    await driver.mkdir("made/deeper")
    await driver.rename("b.txt", "made/c.txt")
    with pytest.raises(EnvError, match="already there"):
        await driver.rename("src", "made")
    await driver.remove("src")
    await driver.remove("link")
    await driver.remove(str(work / "made" / "c.txt"))

    left = await asyncio.to_thread(lambda: sorted(one.name for one in work.iterdir()))
    assert left == ["made"]
    assert [one.name for one in await driver.list("made")] == ["deeper"]
    with pytest.raises(EnvFileNotFound):
        await driver.stat("src")
    with pytest.raises(EnvFileNotFound):
        await driver.remove("src")
    with pytest.raises(EnvError, match="will not remove"):
        await driver.remove(".")


def _gone(pid: int) -> bool:
    """Whether a process is gone within our patience, looking every 50ms."""
    deadline = time.monotonic() + PATIENCE
    while _alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    with contextlib.suppress(ChildProcessError):
        # Ours to reap where this process started it, as a terminal here is.
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    return True
