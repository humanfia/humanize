"""The web interface: a workspace's runs, drawn in a browser on this machine.

    hmz web

One more frontend of the runs a host holds for this directory, beside every terminal
interface opened here: the run going now as it happens, the runs written down before it, the
flows there are to start, what they have spent, and what humanize remembers -- read and acted
on in a browser rather than a terminal. It reaches the runs as the terminal interface does,
through `hmz.daemon`, and works out what it draws of a run with the same `hmz.runtime.watching`.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from .site import Site

__all__ = ["listening", "serve"]


@contextlib.contextmanager
def listening(*, port: int = 0, apart: bool = True) -> Generator[Site]:
    """The web interface, listening on this machine's loopback for as long as the block runs.

    Listening is not answering: what answers is :meth:`Site.serve_forever`, on whichever
    thread calls it, until :meth:`Site.shutdown`.

    Args:
      port: The port to listen on, or 0 for any free one.
      apart: Whether the runs are held apart from this process, by the host of this
        workspace -- which is what lets them outlive it -- or in it.

    Yields:
      The server, attached to the runs. Leaving the block lets go of them, and of the runs
      themselves where they were held in this process.

    Raises:
      hmz.daemon.Older: If this workspace's runs are held by an older humanize.
      OSError: If the runs cannot be reached, or the port cannot be listened on.
    """
    from hmz import daemon

    from .held import Held
    from .runs import Runs
    from .site import Site

    hmz = daemon.Hmz()
    hosting = None if apart else hmz.host()

    def linking() -> daemon.Link:
        if hosting is None:
            return daemon.attach("web", "browser")
        return daemon.linked(hosting, "browser", kind="web")

    with contextlib.ExitStack() as held_open:
        if hosting is not None:
            held_open.callback(hosting.close)
        held = Held(linking)
        held_open.callback(held.close)
        site = Site(port, hmz=hmz, held=held, runs=Runs(hmz))
        held_open.callback(site.server_close)
        # Set first as the block ends, which is what ends every stream being sent.
        held_open.callback(site.going.set)
        yield site


def serve(
    *,
    port: int = 0,
    apart: bool = True,
    shown: Callable[[str], object] = print,
    opened: Callable[[str], object] | None = None,
) -> None:
    """Serves the web interface on this machine's loopback, until it is interrupted.

    Args:
      port: The port to listen on, or 0 for any free one.
      apart: Whether the runs are held apart from this process, or in it.
      shown: What the address is said through, once the server is listening. The address
        carries the key a browser is let in with.
      opened: What opens that address in a browser, or None to leave that to whoever reads it.

    Raises:
      hmz.daemon.Older: If this workspace's runs are held by an older humanize.
      OSError: If the runs cannot be reached, or the port cannot be listened on.
    """
    with listening(port=port, apart=apart) as site:
        shown(site.address)
        if opened is not None:
            opened(site.address)
        with contextlib.suppress(KeyboardInterrupt):
            site.serve_forever(poll_interval=0.5)
