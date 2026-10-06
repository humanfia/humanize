"""Stand-ins for the processes the agent drivers spawn: what a CLI says, and what it was told.

A driver turns a prompt into a command line and the CLI's output into events. Both ends are
observable without running anything: `spawning` puts a `Process` where `subprocess.Popen` was,
which records the command, environment and stdin it is given and answers with lines recorded
from the real CLI.
"""

from __future__ import annotations

import io
import json
import queue
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    import pytest

    from hmz.coganchor.agents import AgentBase
    from hmz.coganchor.agents.event import Event

#: A process id no kernel hands out, so that a signal sent to one of these reaches nobody.
UNREAL_PID = 1 << 30


def line(said: dict[str, Any]) -> str:
    """One line of JSON, as a CLI speaking a protocol writes it."""
    return json.dumps(said) + "\n"


class _Out:
    """A stdout fed a line at a time, which ends when the process does."""

    def __init__(self) -> None:
        self._lines: queue.Queue[str | None] = queue.Queue()
        self.closed = False

    def put(self, said: str | None) -> None:
        self._lines.put(said)

    def __iter__(self) -> Iterator[str]:
        while not self.closed:
            said = self._lines.get(timeout=10)
            if said is None:
                self.closed = True
                return
            yield said

    def close(self) -> None:
        self.closed = True
        self._lines.put(None)


class _In:
    """A stdin that hands every whole line written to it to the process it belongs to."""

    def __init__(self, process: Process) -> None:
        self._process = process
        self._partial = ""
        self.closed = False

    def write(self, said: str) -> int:
        if self.closed:
            raise ValueError("write to closed file")
        self._partial += said
        while "\n" in self._partial:
            one, self._partial = self._partial.split("\n", 1)
            self._process.hears(one)
        return len(said)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._partial:
            self._process.hears(self._partial)
            self._partial = ""
        self._process.ends()


def nothing(said: str) -> Iterable[str]:
    """Answers nothing to anything, as a CLI handed its whole prompt at once does."""
    del said
    return ()


@dataclass(frozen=True)
class Script:
    """What a stand-in says: before it is told anything, to each line it is told, at exit."""

    answers: Callable[[str], Iterable[str] | None] = nothing
    opening: tuple[str, ...] = ()
    status: int = 0
    stderr: str = ""


class Process:
    """What `subprocess.Popen` returns, for a CLI that is never started."""

    def __init__(
        self,
        argv: list[str],
        script: Script,
        *,
        stdin: object = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        **_: object,
    ) -> None:
        self.args = list(argv)
        self.env = env
        self.cwd = cwd
        self.pid = UNREAL_PID
        self.told: list[str] = []
        self.returncode: int | None = None
        self._status = script.status
        self._answers = script.answers
        self.stdout = _Out()
        self.stderr = io.StringIO(script.stderr)
        self.stdin = _In(self) if stdin == subprocess.PIPE else None
        for said in script.opening:
            self.stdout.put(said)
        if self.stdin is None:
            self.ends()

    def hears(self, said: str) -> None:
        self.told.append(said)
        answered = self._answers(said)
        if answered is None:
            self.ends()
            return
        for one in answered:
            self.stdout.put(one)

    def ends(self) -> None:
        if self.returncode is None:
            self.returncode = self._status
            self.stdout.put(None)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.ends()

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        self.ends()
        assert self.returncode is not None
        return self.returncode

    def terminate(self) -> None:
        self.ends()

    def kill(self) -> None:
        self.ends()


def spawning(
    monkeypatch: pytest.MonkeyPatch,
    *,
    answers: Callable[[str], Iterable[str] | None] = nothing,
    opening: Iterable[str] = (),
    status: int = 0,
    stderr: str = "",
) -> list[Process]:
    """Puts stand-ins where `subprocess.Popen` was, and returns the ones spawned as they are.

    Args:
      monkeypatch: The test's own, which puts `subprocess.Popen` back afterwards.
      answers: What each process says back to each line written to its stdin, or None for
        a process that exits on hearing it.
      opening: What each process says before it has been told anything.
      status: What each process exits with.
      stderr: What each process says on stderr.

    Returns:
      Every process spawned, in the order spawned.
    """
    spawned: list[Process] = []
    script = Script(answers, tuple(opening), status, stderr)

    def popen(argv: list[str], **kwargs: Any) -> Process:
        process = Process(argv, script, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", popen)
    return spawned


def configured(model: str, said: dict[str, Any]) -> dict[str, Any]:
    """An agent config's fields: at `model` and no effort, but for what `said` says."""
    return {"model": model, "effort": ""} | said


def heard(agent: AgentBase) -> list[Event]:
    """Watches an agent, so that its turns are told to a list rather than to the terminal."""
    told: list[Event] = []
    agent.watch(lambda _agent, _session, event: told.append(event))
    return told


def option(argv: list[str], flag: str) -> str | None:
    """The value a command line gives one of its flags, or None where it has no such flag."""
    return argv[argv.index(flag) + 1] if flag in argv else None
