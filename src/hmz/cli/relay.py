"""``hmz relay`` -- a relay daemons register with and devices reach them through, until stopped.

`hmz relay serve` is the whole of it: the relay of :mod:`hmz.relay`, on plain WebSockets at
the address `--listen` names, until an interrupt or a terminate. It is a program for a machine
both ends can reach, and it knows nothing of the machine it runs on -- no settings, no home, no
identity, no daemon -- since it holds nobody's keys and carries only what is secured end to end.
Whoever wants it behind TLS puts it behind a proxy that speaks TLS; the relay neither needs nor
knows that.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

__all__ = ["DEFAULT", "relay"]

#: Where `hmz relay serve` listens unless told otherwise.
DEFAULT = "127.0.0.1:8765"


def _address(said: str) -> tuple[str, int]:
    """An address, as `--listen` takes one: `<host>:<port>`, an IPv6 host in brackets.

    Raises:
      argparse.ArgumentTypeError: For anything else.
    """
    import argparse

    host, colon, port = said.rpartition(":")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    elif "[" in host or "]" in host or ":" in host:
        host = ""
    if colon and host and port.isascii() and port.isdigit() and int(port) <= 65535:  # noqa: PLR2004
        return host, int(port)
    msg = f"{said} is not an address: <host>:<port>, the port from 0 to 65535"
    raise argparse.ArgumentTypeError(msg)


def relay(argv: list[str]) -> int:
    """Serves the relay at the address the line names, until interrupted or terminated.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once it has been stopped; one where it could not listen.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz relay",
        description="Relay daemons and the devices that reach them, for daemons nobody can "
        "dial directly.",
    )
    doing = parser.add_subparsers(dest="doing", metavar="{serve}", required=True)
    serve = doing.add_parser(
        "serve",
        help="serve a relay until interrupted or terminated",
        description="Serve a relay on plain WebSockets until interrupted or terminated. Put "
        "it behind a TLS proxy to reach it as wss.",
    )
    serve.add_argument(
        "--listen",
        type=_address,
        default=DEFAULT,
        metavar="HOST:PORT",
        help=f"the address to listen on; {DEFAULT} unless given",
    )
    line = parser.parse_args(argv)
    return _serve(line)


def _serve(line: argparse.Namespace) -> int:
    """`hmz relay serve`, its line read."""
    import asyncio

    host, port = line.listen
    try:
        asyncio.run(_served(host, port))
    except OSError as why:
        print(f"hmz: the relay cannot listen: {why}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # An interrupt before the relay was there to stop it.
        pass
    return 0


async def _served(host: str, port: int) -> None:
    """The relay, saying where it listens, until an interrupt or a terminate."""
    import asyncio
    import signal

    from hmz.relay import listening

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for one in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(one, stopping.set)
    try:
        async with listening(host, port) as bound:
            shown = f"[{host}]" if ":" in host else host
            print(f"hmz relay: listening on ws://{shown}:{bound}", flush=True)
            await stopping.wait()
    finally:
        for one in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(one)
