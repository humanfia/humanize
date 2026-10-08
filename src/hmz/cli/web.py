"""``hmz web`` -- this directory's runs, in a browser on this machine.

The web interface is one more frontend of the runs a host holds here, as the terminal interface
is: what this line does is serve it, say where, and open a browser on it, until it is
interrupted. The runs go on without it, as they go on without a terminal.
"""

from __future__ import annotations

import sys

__all__ = ["web"]


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
        type=int,
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
            opened=None if line.no_open else webbrowser.open,
        )
    except daemon.Older as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    except OSError as why:
        print(f"hmz: the web interface cannot be served: {why}", file=sys.stderr)
        return 1
    return 0
