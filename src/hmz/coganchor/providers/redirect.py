"""Running a coding agent whose credentials are somewhere other than where it looks.

Every one of these CLIs keeps its account in one place under a home directory of its own,
found by a path it decides for itself. Moving that home moves the sessions, the settings and
the skills with it; asking the CLI nicely is not a thing any of them offers. So the paths are
answered rather than moved: the agent is run under a seccomp-filtered ptrace supervisor -- the
same technique :mod:`hmz.coganchor` runs a whole session under -- and the handful of
syscalls that name one of its credential files are handed a path inside the provider's
directory instead.

Only those paths. Everything else the agent does is untouched and runs at native speed, and
the agent is told none of it: what it reads back is a credentials file at the name it wrote,
and what it writes when a token is refreshed lands where it read from.

Where it reads it back from is memory. These CLIs ask about a credential hundreds of times a turn
and change it once in a while, so a read is answered with a copy on tmpfs that is made once --
:mod:`hmz.coganchor.providers._staging` -- and a write with the provider's own file, which is where
a refreshed token has to be durable the moment it is written.

Two supervisors cannot be nested -- a process has one tracer -- so a turn that is also
anchored is not wrapped in this: the anchor is told the same swaps and its own supervisor
makes them. This is the case where the agent runs on this machine, which is most of them.

The same supervisor keeps a CLI's sessions where humanize keeps them, which is the other half of
what a turn is pointed elsewhere for: the transcripts and the indexes of them, answered with a
directory of the run's own, while the settings, the skills and the credentials stay the CLI's.
Those are *kept* rather than swapped, and differ in one thing: a read of one is never answered
with a copy. A transcript is appended to as it is read back, and a database is locked and
written under the reader; neither is a token that changes once in a while.
"""

from __future__ import annotations

import errno
import os
import signal
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

# The one rule both halves of a supervised turn answer a path by: the anchor's supervisor ships
# to machines this package's accounts never reach, so the rule lives with it and is named here.
from hmz.coganchor.policy import answered, head

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "Swaps",
    "answered",
    "command",
    "head",
    "read",
    "run",
    "supervises",
    "swept",
]

#: `AT_FDCWD`, the directory descriptor that means "wherever the process is".
_AT_FDCWD = -100


def _table(pairs: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """`(what the agent names, what it gets)` pairs, tidied, longest first."""
    held = tuple(
        (os.path.normpath(one), os.path.normpath(other))
        for one, other in pairs
        if one and other
    )
    return tuple(sorted(held, key=lambda pair: -len(pair[0])))


@dataclass(frozen=True, slots=True)
class Swaps:
    """Which paths a traced process is given instead of the ones it named.

    A prefix apiece: a credential kept in a directory -- kimi keeps one file per endpoint it
    has signed into -- is a directory that moves whole, and one kept in a file is that file.
    Longest first, so a path under two of them takes the one that says most about it.

    Two tables. `pairs` are credentials, whose reads may be answered with a copy held in
    memory; `kept` are sessions, whose every call is answered with the file itself.
    """

    pairs: tuple[tuple[str, str], ...] = ()
    kept: tuple[tuple[str, str], ...] = ()

    @classmethod
    def of(
        cls,
        pairs: Iterable[tuple[str, str]],
        kept: Iterable[tuple[str, str]] = (),
    ) -> Swaps:
        """Builds a table from `(what the agent names, what it gets)` pairs.

        Args:
          pairs: The credentials.
          kept: The sessions.

        Returns:
          The table.
        """
        return cls(_table(pairs), _table(kept))

    def __bool__(self) -> bool:
        """Whether anything is pointed anywhere else at all."""
        return bool(self.pairs or self.kept)

    def swap(self, path: str) -> str | None:
        """What one path is answered with.

        Args:
          path: The absolute, normalised path the process named.

        Returns:
          The path to give it instead, or None for a path that is its own -- which is nearly
          all of them.
        """
        found = self.answer(path)
        return found[0] if found is not None else None

    def answer(self, path: str) -> tuple[str, bool] | None:
        """What one path is answered with, and whether it is a session's.

        Longest entry first across both tables, as :func:`answered` reads each.

        Args:
          path: The absolute, normalised path the process named.

        Returns:
          The path to give it instead and whether it is kept -- a session's, whose reads are
          never answered with a copy -- or None for a path that is its own.
        """
        best: tuple[int, str, bool] | None = None
        for held, kept in ((self.pairs, False), (self.kept, True)):
            for named, instead in held:
                if best is not None and len(named) <= best[0]:
                    break
                found = answered(named, instead, path)
                if found is not None:
                    best = (len(named), found, kept)
                    break
        return (best[1], best[2]) if best is not None else None


def read(said: Iterable[str], kept: Iterable[str] = ()) -> Swaps:
    """Reads the swaps off a command line that named them.

    Args:
      said: One `FROM=TO` per swap, as `--map` took them.
      kept: The same, as `--keep` took them.

    Returns:
      The table.

    Raises:
      ValueError: If one of them is not two absolute paths with an `=` between.
    """

    def pairs(of: Iterable[str]) -> list[tuple[str, str]]:
        held: list[tuple[str, str]] = []
        for one in of:
            named, sep, instead = one.partition("=")
            if not sep or not named.startswith("/") or not instead.startswith("/"):
                raise ValueError(f"{one!r} is not FROM=TO, of two absolute paths")
            held.append((named, instead))
        return held

    return Swaps.of(pairs(said), pairs(kept))


def supervises() -> bool:
    """Whether a turn can be supervised on this machine at all.

    Linux, on an architecture there is a register map for, with the C library the bindings
    load -- asked of the bindings themselves, which refuse to be imported anywhere else -- and
    a kernel that will hand this process a tracee, which only starting one answers: a
    container without `CAP_SYS_PTRACE`, or a Yama that forbids tracing outright, has every
    module and supervises nothing. Asked by supervising a program that does nothing, and a
    yes kept for the life of the process; a no for a minute and then asked again, since a
    supervisor that could not start once under a machine's load is not a machine that cannot
    trace -- and a turn, a tally and a trace each asking where sessions are would otherwise
    start one apiece.

    Returns:
      Whether it can.
    """
    import time

    if _SUPERVISES:
        said, when = _SUPERVISES[-1]
        if said or time.monotonic() - when < _AGAIN:
            return said
    import importlib
    import shutil
    import subprocess

    try:
        for binding in ("procfs", "ptrace", "seccomp"):
            importlib.import_module(f"hmz.coganchor.linux.{binding}")
    except (ImportError, OSError, RuntimeError):
        _SUPERVISES.append((False, float("inf")))
        return False
    nothing = shutil.which("true")
    try:
        done = subprocess.run(
            command(
                [],
                [nothing] if nothing else [sys.executable, "-c", ""],
                [("/nonexistent/hmz-probe", "/nonexistent/hmz-probed")],
            ),
            capture_output=True,
            # Somewhere that is there whatever this process is standing in, since a program
            # started in a directory that has gone away fails before it is supervised.
            cwd="/",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        done = None
    answer = done is not None and done.returncode == 0
    _SUPERVISES.append((answer, time.monotonic()))
    return answer


#: What :func:`supervises` last answered in this process, and when: a machine that cannot
#: supervise at all is answered once and for good, which the moment `inf` says.
_SUPERVISES: list[tuple[bool, float]] = []

#: How long a no is taken as the answer before the kernel is asked again.
_AGAIN = 60.0


def command(
    swaps: Iterable[tuple[str, str]],
    argv: Sequence[str] | list[str],
    kept: Iterable[tuple[str, str]] = (),
) -> list[str]:
    """Renders the invocation that runs `argv` with those paths pointed elsewhere.

    A method of its own rather than the loop it starts, for the reason
    :meth:`hmz.coganchor.AnchorConfig.command` is one: a turn is pumped from threads of
    its own, and a supervisor that forks the agent and takes the process's signal handling
    cannot be given those.

    Args:
      swaps: What to point where: the credentials.
      argv: The backend to run and its own arguments.
      kept: What to point where and never answer with a copy: the sessions.

    Returns:
      The command to spawn, which exits with the backend's own status -- or `argv` itself
      when there is nothing to point anywhere, so that a provider which is only variables
      costs no supervisor and no ptrace at all.
    """
    held = Swaps.of(swaps, kept)
    if not held:
        return list(argv)
    mapped = [f"--map={named}={instead}" for named, instead in held.pairs]
    mapped += [f"--keep={named}={instead}" for named, instead in held.kept]
    return [sys.executable, "-m", "hmz", "internal", "cred", *mapped, "--", *argv]


def run(swaps: Swaps, argv: Sequence[str]) -> int:
    """Runs a program with those paths answered by others, and waits for it.

    Args:
      swaps: What to point where.
      argv: The program and its arguments.

    Returns:
      Its exit status, or 128 plus the signal that killed it.

    Raises:
      OSError: If the supervisor cannot be started, which is a turn that must not run: an
        agent whose credentials were not pointed anywhere would sign in as somebody else.
    """
    # Imported here rather than above: this half needs ptrace and an x86-64 register map,
    # which reading a provider and rendering a command line do not.
    from hmz.coganchor.linux import ptrace, seccomp

    from ._trace import Tracing

    if not argv:
        raise ValueError("no program to run")
    tracing = Tracing(swaps)
    pid = os.fork()
    if not pid:
        try:
            ptrace.traceme()
            seccomp.install(tracing.trapped())
            os.kill(os.getpid(), signal.SIGSTOP)
            # Becoming the program is the whole errand of this fork, and it is an argv
            # rather than a command line, so there is no shell for one to go through.
            os.execvp(argv[0], list(argv))  # noqa: S606
        # Everything, deliberately: this is the forked child, and anything that escapes here
        # would run the parent's code a second time rather than report a failed launch.
        except BaseException as why:  # noqa: BLE001
            os.write(2, f"hmz: cannot run {argv[0]}: {why}\n".encode())
        os._exit(127)
    try:
        return tracing.watch(pid)
    finally:
        # The copies this run answered reads with, which are a secret in memory that belongs
        # to nothing once the program is over. A signal aimed here is passed on to the
        # program rather than acted on, so this runs for every way a run ends but the one
        # that runs nothing at all -- and what that leaves is swept up by the next run.
        tracing.close()


def swept(pid: int) -> None:
    """Takes away what a supervisor that was killed left of a credential in memory.

    A turn is ended by killing the process it ran in, and `SIGKILL` runs no teardown of its
    own, so whoever ended one says so here: the copies it was answering reads from are a
    secret that belongs to nothing the moment that process is gone.

    Nothing at all for a turn that ran without a supervisor, which is most of them, and
    nothing for a process id that is somebody's again -- one still running is one still
    reading what is in there.

    Args:
      pid: The process the turn ran in, after it has been waited on.
    """
    from ._staging import swept as sweep

    sweep(pid)


def failed(status: int) -> int:
    """What a program's wait status comes to as an exit status."""
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return 128 + os.WTERMSIG(status) if os.WIFSIGNALED(status) else 1


#: What a syscall that could not be given its new path is answered with. A visible failure,
#: because the alternative is the agent quietly reading the credentials of whoever is at this
#: machine -- a turn that ran as the wrong account is worse than a turn that did not run.
UNSWAPPABLE = errno.EIO
