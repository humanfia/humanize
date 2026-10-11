"""``hmz web`` -- every workspace's runs on this machine, in a browser on it.

The web interface is one more frontend of the runs the daemon holds, as the terminal interface
is -- of every workspace's, as the daemon holds every workspace's: what this line does is serve
it, say where, and open a browser on it, until it is interrupted, terminated or hung up on --
or, attached, until whatever started it lets go of its standard input. The runs go on without
it, as they go on without a terminal. Where it is started is only where a new epic is offered first.
"""

from __future__ import annotations

import contextlib
import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = ["web"]

#: The ports there are.
_PORTS = range(65536)


def _port(said: str) -> int:
    """A port, as `--port` takes one.

    Raises:
      argparse.ArgumentTypeError: For anything that is not a port.
    """
    import argparse

    try:
        port = int(said)
    except ValueError:
        port = -1
    if port not in _PORTS:
        raise argparse.ArgumentTypeError(f"{said} is not a port: 0 to 65535")
    return port


def _shows_a_browser() -> bool:
    """Whether a browser opened here would be one somebody sees, rather than one in this terminal.

    Where there is no desktop to open one on -- a machine reached over ssh -- `webbrowser`
    falls back to a browser in the terminal, which would take the terminal over and never let
    go; the address is printed for whoever reads it instead.
    """
    return sys.platform == "darwin" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )


@contextlib.contextmanager
def _ending(*, attached: bool) -> Generator[None]:
    """Stops `hmz web` on a terminate or a hangup as on an interrupt, and on its stdin closing.

    Left to themselves a terminate or a hangup would end the process where it stood, leaving
    the page that forwards a browser behind and every stream cut rather than ended. Raised as
    an interrupt instead, the server unwinds as it does at a terminal. Whichever came first,
    a terminate or a hangup after it is ignored while it does; a second interrupt is not.

    Attached, standard input is whatever started it, which holds the other end for as long as
    it lives: that end closing -- however that went, a crash or a kill included -- is the word
    to stop, which nothing has to remember to send.

    Args:
      attached: Whether the end of standard input stops it too.
    """
    import _thread
    import select
    import signal
    import threading

    stopping = threading.Event()

    def ends(signum: int, _frame: object) -> None:
        # Once: a second is the server already letting go, which raising again would cut
        # short -- but for an interrupt, which is somebody asking to cut it short.
        if stopping.is_set() and signum != signal.SIGINT:
            return
        stopping.set()
        raise KeyboardInterrupt

    def reads() -> None:
        # Waited on before each read, which a stdin left non-blocking would otherwise end; and
        # one that is not there at all is one that has closed.
        with contextlib.suppress(OSError):
            while True:
                select.select([0], [], [])
                with contextlib.suppress(BlockingIOError):
                    if not os.read(0, 1 << 16):
                        break
        # Raised as a signal is, on the thread that serves -- the first one handled here, as
        # one that is ignored would not be.
        if was and not stopping.is_set():
            _thread.interrupt_main(next(iter(was)))

    was: dict[signal.Signals, Any] = {}
    for one in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        with contextlib.suppress(ValueError):  # off the main thread, where none reaches
            # A signal somebody chose to have ignored -- a hangup under `nohup`, an interrupt
            # to a job a script put in the background -- stays so.
            if signal.getsignal(one) != signal.SIG_IGN:
                was[one] = signal.signal(one, ends)
    if attached:
        threading.Thread(target=reads, daemon=True, name="hmz-web-attached").start()
    try:
        yield
    finally:
        stopping.set()
        for one, before in was.items():
            signal.signal(one, signal.SIG_DFL if before is None else before)


def web(argv: list[str], *, apart: bool) -> int:
    """Serves the web interface until it is interrupted, terminated or hung up on.

    Args:
      argv: What followed the command name.
      apart: Whether this machine wants runs held apart from the process that started them.

    Returns:
      Zero once it has been stopped; one where the runs or the port could not be had.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz web",
        description="Serve every workspace's epics on this machine to a browser on it, until "
        "interrupted; a new epic is offered this directory first. The runs carry on without it.",
    )
    parser.add_argument(
        "--port",
        type=_port,
        default=0,
        help="the port to listen on, on this machine's loopback; 0 picks any free one",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="print the address rather than open a browser on it",
    )
    parser.add_argument(
        "--attached",
        action="store_true",
        help="stop once standard input closes",
    )
    line = parser.parse_args(argv)

    import webbrowser

    from hmz import daemon
    from hmz.web import serve

    def shown(address: str) -> None:
        print(f"hmz web: {address}", flush=True)

    opened = webbrowser.open if not line.no_open and _shows_a_browser() else None
    try:
        with _ending(attached=line.attached):
            serve(port=line.port, apart=apart, shown=shown, opened=opened)
    except KeyboardInterrupt:
        # Stopped before it was serving, or while it let go: nothing is left to unwind.
        return 0
    except daemon.Older as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    except OSError as why:
        print(f"hmz: the web interface cannot be served: {why}", file=sys.stderr)
        return 1
    return 0
