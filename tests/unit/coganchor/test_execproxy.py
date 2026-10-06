"""Standing in for a command run on the target, its output written into pipes of this test's."""

from __future__ import annotations

import errno
import os
import threading
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.execproxy import ExecProxy, ExecResult
from hmz.coganchor.proto import Stream
from tests.unit.coganchor.doubles_u8 import Exec

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.mark.parametrize(
    ("result", "status"),
    [
        (ExecResult(exit_code=0), 0),
        (ExecResult(exit_code=3), 3),
        (ExecResult(signal=9), 137),
        (ExecResult(exit_code=0, signal=15), 143),
        (ExecResult(), 1),
    ],
)
def test_a_result_is_reported_as_a_shell_would(result: ExecResult, status: int) -> None:
    assert result.wait_status == status


class Client:
    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse
        self.started: list[Exec] = []

    def start_exec(
        self,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        on_output: Any,
        on_exit: Any,
        **options: Any,
    ) -> Exec:
        if self.refuse:
            raise ConnectionResetError(errno.EPIPE, "gone")
        held = Exec(argv, cwd, env, on_output, on_exit, options)
        self.started.append(held)
        return held


class Stdio:
    """Two pipes standing for the tracee's stdout and stderr, and what reached them."""

    def __init__(self) -> None:
        self.out_r, self.out_w = os.pipe()
        self.err_r, self.err_w = os.pipe()

    def given(self) -> tuple[int, int, int]:
        return (-1, self.out_w, self.err_w)

    @staticmethod
    def drain(fd: int) -> bytes:
        held = b""
        while chunk := os.read(fd, 4096):
            held += chunk
        return held

    def close(self) -> None:
        for fd in (self.out_r, self.err_r):
            os.close(fd)


@pytest.fixture
def stdio() -> Iterator[Stdio]:
    held = Stdio()
    yield held
    held.close()


class Finished:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.got: list[tuple[int, ExecResult]] = []

    def __call__(self, pid: int, result: ExecResult) -> None:
        self.got.append((pid, result))
        self.done.set()


def proxy(
    client: Client, stdio: Stdio, finished: Finished, **options: Any
) -> ExecProxy:
    return ExecProxy(
        client,  # pyright: ignore[reportArgumentType]
        41,
        ["make", "all"],
        "/w",
        {"A": "b"},
        stdio.given(),
        finished,
        **options,
    )


def test_the_command_is_asked_for_as_given(stdio: Stdio) -> None:
    client, finished = Client(), Finished()
    proxy(
        client, stdio, finished, program="/usr/bin/make", fence={"online": False}
    ).start()
    asked = client.started[0]
    assert (asked.argv, asked.cwd, asked.env) == (["make", "all"], "/w", {"A": "b"})
    assert asked.options["program"] == "/usr/bin/make"
    assert asked.options["fence"] == {"online": False}
    assert asked.options["tty"] is False
    assert asked.options["winsize"] is None
    asked.answer(code=0)
    assert finished.done.wait(5)


def test_output_lands_on_the_tracees_own_descriptors(stdio: Stdio) -> None:
    client, finished = Client(), Finished()
    proxy(client, stdio, finished).start()
    running = client.started[0]
    running.on_output(Stream.STDOUT, b"built\n")
    running.on_output(Stream.STDERR, b"warned\n")
    running.on_output(Stream.DATA, b"more\n")
    running.on_exit({"exit_code": 2}, None)
    assert finished.done.wait(5)
    assert finished.got == [(41, ExecResult(exit_code=2))]
    assert stdio.drain(stdio.out_r) == b"built\nmore\n"
    assert stdio.drain(stdio.err_r) == b"warned\n"


def test_a_signalled_command_reports_its_signal(stdio: Stdio) -> None:
    client, finished = Client(), Finished()
    proxy(client, stdio, finished).start()
    client.started[0].on_exit({"signal": 15}, None)
    assert finished.done.wait(5)
    assert finished.got[0][1].wait_status == 143


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (FileNotFoundError(errno.ENOENT, "No such file"), 127),
        (PermissionError(errno.EACCES, "Permission denied"), 126),
    ],
)
def test_a_command_that_could_not_start_says_so_as_a_shell_would(
    stdio: Stdio, error: OSError, status: int
) -> None:
    client, finished = Client(), Finished()
    proxy(client, stdio, finished).start()
    client.started[0].on_exit(None, error)
    assert finished.done.wait(5)
    assert finished.got[0][1].wait_status == status
    assert stdio.drain(stdio.err_r) == f"hmz: make: {error.strerror}\n".encode()


def test_a_target_gone_before_the_start_raises_and_hands_the_descriptors_back(
    stdio: Stdio,
) -> None:
    finished = Finished()
    with pytest.raises(ConnectionResetError):
        proxy(Client(refuse=True), stdio, finished).start()
    assert stdio.drain(stdio.out_r) == b""
    assert stdio.drain(stdio.err_r) == b""
    assert finished.got == []


def test_a_signal_is_forwarded_once(stdio: Stdio) -> None:
    client, finished = Client(), Finished()
    running = proxy(client, stdio, finished)
    running.forward_signal(2)  # before the command exists: nothing to forward to
    running.start()
    running.forward_signal(15)
    running.forward_signal(15)
    running.forward_signal(1)
    assert client.started[0].signals == [15, 1]
    client.started[0].answer()
    assert finished.done.wait(5)


def test_an_abandoned_command_is_killed_and_finished(stdio: Stdio) -> None:
    client, finished = Client(), Finished()
    running = proxy(client, stdio, finished)
    running.start()
    running.abandon()
    assert finished.done.wait(5)
    assert client.started[0].signals == [9]
    assert finished.got[0][1].wait_status == 1
