"""A process :func:`hmz.daemon.detaching.spawns` started: this machine's daemon, or one host.

Run as `python -Pm hmz.daemon.detached <telling> daemon` or `... <telling> host <workspace>
<slot> <link>`, `telling` the descriptor to say it is listening on and `link` the end of the
socket pair the daemon reaches the host through. Never imported: it is a process's first frame.
"""

from __future__ import annotations

import contextlib
import os
import signal
import sys
import threading

#: How long a host process that is done is given to finish backing its epics up before it
#: goes: within what a stop waits for it, so that a stop is never taken for one that failed.
BACKING = 15.0


class _Terminated(BaseException):
    """A detached process told to end, on its way out."""


def _terminated(_signal: int, _frame: object) -> None:
    """Ends a detached process by unwinding it."""
    raise _Terminated


def _hosts_in(workspace: str, telling: int, link: int, slot: str) -> None:
    """The runs of a workspace, or of one slot of it, hosted in the process that holds them.

    Args:
      workspace: The workspace.
      telling: The descriptor to say it is listening on.
      link: This end of the socket pair the daemon reaches it through.
      slot: Which of the workspace's hosts.
    """
    import socket

    from hmz.daemon.carrying import Printed, keeps, serves
    from hmz.runtime import Holding, Host

    os.chdir(workspace)
    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    # Named, not wherever the process stands: a workspace removed under its host is still
    # the one it holds, and a directory that has gone has no name to ask for.
    hmz = Holding(workspace)
    # If it has been answered yes, and never otherwise: nobody is here to ask.
    hmz.reports()
    held = Host(hmz, slot)
    # What a CLI a run starts writes straight to a descriptor goes into that run's epic, and
    # what is printed in Python is said to every frontend. Only now, with something reading
    # the pipe: a failure before this goes into the daemon's log as it is.
    reading, writing = os.pipe()
    threading.Thread(
        target=keeps, args=(reading, held), daemon=True, name="humanize-kept"
    ).start()
    for fd in (1, 2):
        os.dup2(writing, fd)
    os.close(writing)
    sys.stdout = sys.stderr = Printed(held)

    def closes(_signal: int, _frame: object) -> None:
        # Off the signal's frame: closing waits on threads the frame may be holding up.
        threading.Thread(target=held.close, daemon=True).start()

    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGTERM, closes)
    serves(held, workspace, socket.socket(fileno=link), telling, slot=slot)
    # A backup of the last epic still going is let finish, for so long: nothing waits on it.
    hmz.backups.wait(BACKING)


def _main(argv: list[str]) -> None:
    """The process, from the line it was started with, until it goes."""
    # Started leading a session of its own; a fork of it -- while it has no thread but this
    # one -- leads none, and so can never take a controlling terminal again.
    if os.fork() != 0:
        os._exit(0)
    telling = int(argv[0])
    # The daemon's log, kept to put back where a host's failure is written down.
    log = os.dup(2)
    status = 0
    try:
        # A hangup cannot reach a process with no controlling terminal, and this one has
        # none; refusing it as well costs nothing and says what is meant.
        with contextlib.suppress(OSError, ValueError):
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            # A terminate is this process's own to take, whatever the one that started it
            # made of one -- ignored, or its own way out: unwound, so that what it holds is
            # let go.
            signal.signal(signal.SIGTERM, _terminated)
        if argv[1] == "host":
            _hosts_in(argv[2], telling, int(argv[4]), argv[3])
        else:
            from hmz.daemon import routing

            # The daemon is this machine's, not of the directory whoever started it stood
            # in: it outlives that one, and a CLI it asks cannot start in one that has gone.
            for there in (os.path.expanduser("~"), os.sep):  # noqa: PTH111 -- never raises
                with contextlib.suppress(OSError):
                    os.chdir(there)
                    break
            routing.serves(telling)
    except _Terminated:
        pass
    except BaseException as why:  # noqa: BLE001 -- the last frame of a process nobody reads
        status = 1
        # Said back down the pipe as well as written down: whoever asked is still waiting,
        # and `could not be held` on its own is a line nobody can act on.
        with contextlib.suppress(OSError):
            os.write(telling, f"the run could not be held: {why}\n".encode())
            os.close(telling)
        from hmz.daemon.carrying import logged

        with contextlib.suppress(OSError):
            os.dup2(log, 1)
            os.dup2(log, 2)
        logged("these runs could not be held apart from the terminal")
    finally:
        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        os._exit(status)  # nothing of this process is anybody's to unwind


if __name__ == "__main__":
    _main(sys.argv[1:])
