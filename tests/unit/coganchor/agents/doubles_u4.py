"""A coding agent's process that is never started, for the drivers' unit tests.

Every driver starts its CLI through `subprocess.Popen` and reads it as text, a line at a time.
:class:`Spawner` stands in for that one call: it records what was asked for -- the command,
the environment, the directory -- and hands back a :class:`Process` whose stdout is whatever
the test scripts it to say, at start or in answer to each line the driver writes to its stdin.
Nothing is spawned, nothing is slept on, and no file outside the test's own is touched.
"""

from __future__ import annotations

import itertools
import json
import os
import queue
import subprocess
from typing import TYPE_CHECKING, Any, Self

from hmz.runtime import telemetry

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    import pytest

    from hmz.coganchor.backends import Model

#: How long a read waits for a line before reading it as the end of the stream. Long enough
#: that a CLI held open between turns is never read as gone while a test is between two of
#: them, however loaded the machine; short enough that a test which forgot to script a line
#: fails well inside the suite's own timeout rather than at it.
_PATIENCE = 30.0

#: Pids nothing on any machine holds: past every kernel's `pid_max`, so a driver ending the
#: process tree of one signals nobody.
_PIDS = itertools.count(1 << 30)

type Line = str | dict[str, Any]


def _line(said: Line) -> str:
    """One line of output, a JSON object written compactly and anything else as it is."""
    text = json.dumps(said) if isinstance(said, dict) else said
    return text if text.endswith("\n") else text + "\n"


class Outlet:
    """A process's stdout or stderr: lines the test put there, then the end of them."""

    def __init__(self) -> None:
        self._lines: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        self.closed = False

    def put(self, said: Line) -> None:
        """Writes one line."""
        self._lines.put(_line(said))

    def end(self) -> None:
        """Ends the stream: whoever reads it reads everything put before, and then the end."""
        self._lines.put(None)

    def __iter__(self) -> Outlet:
        return self

    def __next__(self) -> str:
        if self.closed:
            raise StopIteration
        try:
            line = self._lines.get(timeout=_PATIENCE)
        except queue.Empty:
            raise StopIteration from None
        if line is None:
            self._lines.put(None)  # so that every later read finds it ended too
            raise StopIteration
        return line

    def readline(self) -> str:
        """The next line, or "" at the end."""
        return next(self, "")

    def read(self) -> str:
        """Everything left."""
        return "".join(self)

    def close(self) -> None:
        """Closes it, which ends any read waiting on it."""
        self.closed = True
        self._lines.put(None)


class Inlet:
    """A process's stdin: what the driver wrote, a line at a time, each one heard."""

    def __init__(
        self, heard: Callable[[str], None], closed: Callable[[], None]
    ) -> None:
        self._heard = heard
        self._closed = closed
        self._held = ""
        self.lines: list[str] = []
        self.closed = False

    def write(self, text: str) -> int:
        """Takes what was written, and hands each whole line on as it completes."""
        if self.closed:
            raise ValueError("I/O operation on closed file")
        self._held += text
        while "\n" in self._held:
            line, self._held = self._held.split("\n", 1)
            self.lines.append(line)
            self._heard(line)
        return len(text)

    def flush(self) -> None:
        """Nothing to flush: every write is heard as it is made."""

    def close(self) -> None:
        """Closes it, which a CLI reading its stdin takes as the end of the conversation."""
        if self.closed:
            return
        self.closed = True
        if self._held:
            self.lines.append(self._held)
            self._heard(self._held)
            self._held = ""
        self._closed()

    @property
    def said(self) -> list[Any]:
        """Every line written that was JSON, decoded."""
        decoded: list[Any] = []
        for line in self.lines:
            try:
                decoded.append(json.loads(line))
            except ValueError:
                continue
        return decoded

    @property
    def text(self) -> str:
        """Everything written, whole."""
        return "".join(f"{one}\n" for one in self.lines) + self._held


class Process:
    """One process a driver asked for, as `subprocess.Popen` would have handed it back."""

    def __init__(
        self,
        argv: list[str],
        kwargs: dict[str, Any],
        heard: Callable[[Process, str], None] | None,
    ) -> None:
        self.args = list(argv)
        self.env: dict[str, str] | None = kwargs.get("env")
        self.cwd: str | None = kwargs.get("cwd")
        self.pid = next(_PIDS)
        self.stdout = Outlet()
        self.stderr = Outlet()
        self.returncode: int | None = None
        self._code = 0
        self._heard = heard
        self.stdin: Inlet | None = (
            Inlet(self._hear, lambda: self.exit(self._code))
            if kwargs.get("stdin") == subprocess.PIPE
            else None
        )

    @property
    def environ(self) -> dict[str, str]:
        """The environment it was started in: its own where given, and ours where inherited."""
        return dict(os.environ) if self.env is None else dict(self.env)

    def _hear(self, line: str) -> None:
        if self._heard is not None:
            self._heard(self, line)

    def say(self, *lines: Line) -> None:
        """Writes lines on stdout."""
        for one in lines:
            self.stdout.put(one)

    def complain(self, *lines: Line) -> None:
        """Writes lines on stderr."""
        for one in lines:
            self.stderr.put(one)

    def exit(self, code: int = 0) -> None:
        """Ends both streams, and exits with `code` once waited on."""
        self._code = code
        self.stdout.end()
        self.stderr.end()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        if self.stdin is not None:
            self.stdin.close()

    def poll(self) -> int | None:
        """Its status, or None while it is running."""
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        """Ends it, if it had not, and answers with its status."""
        del timeout
        if self.returncode is None:
            self.exit(self._code)
            self.returncode = self._code
        return self.returncode

    def communicate(
        self,
        input: str | None = None,  # noqa: A002 -- `Popen.communicate`'s own name
        timeout: float | None = None,
    ) -> tuple[str, str]:
        """Everything it wrote, once it has ended, as `subprocess.run` reads it."""
        del input, timeout
        self.wait()
        return self.stdout.read(), self.stderr.read()

    def terminate(self) -> None:
        """Stops it, as a term signal would."""
        self._signalled(-15)

    def kill(self) -> None:
        """Stops it, as a kill signal would."""
        self._signalled(-9)

    def send_signal(self, signal: int) -> None:
        """Stops it, whatever the signal."""
        self._signalled(-int(signal))

    def _signalled(self, code: int) -> None:
        if self.returncode is None:
            self.exit(code)
            self.returncode = code


class Spawner:
    """`subprocess.Popen`, answered by scripted processes rather than by starting anything.

    `script` is called with each process as it starts, and `heard` with each line the driver
    writes to one: either says what the process answers, through :meth:`Process.say` and
    :meth:`Process.exit`. A process nobody scripted exits 127 at once having said nothing, as
    a command that is not installed would.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.started: list[Process] = []
        self.script: Callable[[Process], None] = lambda proc: proc.exit(127)
        self.heard: Callable[[Process, str], None] | None = None
        #: What `hmz.runtime.telemetry` was asked to report, by name.
        self.snags: list[str] = []
        monkeypatch.setattr(subprocess, "Popen", self._popen)
        monkeypatch.setattr(telemetry, "snag", self._snag)

    def _snag(self, name: str, **said: object) -> None:
        del said
        self.snags.append(name)

    def _popen(self, argv: list[str], **kwargs: Any) -> Process:
        proc = Process(argv, kwargs, self.heard)
        self.started.append(proc)
        self.script(proc)
        return proc

    def answering(self, lines: Iterable[Line], *, err: str = "", code: int = 0) -> None:
        """Has every process say these lines, complain `err` and exit `code`: a one-shot CLI."""
        held = list(lines)

        def script(proc: Process) -> None:
            proc.say(*held)
            if err:
                proc.complain(err)
            proc.exit(code)

        self.script = script

    def replying(self, reply: Callable[[Process, Any], None]) -> None:
        """Has every process answer each JSON line it is told with `reply`: a held-open CLI.

        It stays up until its stdin is closed or it is stopped, as one reading its stdin does.
        """
        self.script = lambda proc: None

        def heard(proc: Process, line: str) -> None:
            try:
                said: Any = json.loads(line)
            except ValueError:
                return
            reply(proc, said)

        self.heard = heard

    @property
    def last(self) -> Process:
        """The process started last."""
        assert self.started, "nothing was started"
        return self.started[-1]


def fenceable(*, net: bool) -> bool:
    """`hmz.coganchor.fence.enforceable` on a machine that can fence anything."""
    del net
    return True


def offering(*listed: Model) -> Callable[..., tuple[Model, ...]]:
    """`hmz.coganchor.models.offered` for an account whose catalogue lists these."""

    def offered(cli: str, provider: str = "") -> tuple[Model, ...]:
        del cli, provider
        return listed

    return offered
