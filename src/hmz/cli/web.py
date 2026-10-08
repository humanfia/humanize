"""``hmz web`` -- this directory's runs, in a browser on this machine.

The web interface is one more frontend of the runs a host holds here, as the terminal interface
is: what this line does is serve it, say where, and open a browser on it, until it is
interrupted. The runs go on without it, as they go on without a terminal.
"""

from __future__ import annotations

import os
import sys

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


def web(argv: list[str], *, apart: bool) -> int:
    """Serves the web interface until it is interrupted.

    Args:
      argv: What followed the command name.
      apart: Whether this machine wants runs held apart from the process that started them.

    Returns:
      Zero once it has been interrupted; one where the runs or the port could not be had.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz web",
        description="Serve this directory's runs to a browser on this machine, until "
        "interrupted. The runs carry on without it.",
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
    line = parser.parse_args(argv)

    import webbrowser

    from hmz import daemon
    from hmz.web import serve

    def shown(address: str) -> None:
        print(f"hmz web: {address}", flush=True)

    try:
        serve(
            port=line.port,
            apart=apart,
            shown=shown,
            opened=webbrowser.open if not line.no_open and _shows_a_browser() else None,
        )
    except daemon.Older as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    except OSError as why:
        print(f"hmz: the web interface cannot be served: {why}", file=sys.stderr)
        return 1
    return 0
