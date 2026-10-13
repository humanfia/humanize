"""The web interface: every workspace's runs on this machine, drawn in a browser.

    hmz web

One more frontend of the runs the daemon holds, beside every terminal interface opened on them
-- not of one directory, as the terminal interface is, but of the machine, as the daemon is:
every epic of every workspace, each going as it happens, the flows there are to start and where,
what they have spent, and what humanize remembers -- read and acted on in a browser rather than a
terminal. It reaches each workspace's runs as the terminal interface does, through
`hmz.daemon`, and works out what it draws of a run with the same `hmz.runtime.watching`.
"""

from __future__ import annotations

import contextlib
import html
import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from .site import Site

__all__ = ["listening", "serve"]

#: The page a browser is opened on, which goes on to the address: the key is in a file only
#: this account can read rather than on the command line of the browser, which every account
#: on the machine can.
_FORWARD = (
    '<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
    '<meta http-equiv="refresh" content="0;url={0}"><title>humanize</title>'
    '<a href="{0}">Open humanize</a>'
)


@contextlib.contextmanager
def listening(*, port: int = 0, apart: bool = True) -> Generator[Site]:
    """The web interface, listening on this machine's loopback for as long as the block runs.

    Listening is not answering: what answers is :meth:`Site.serve_forever`, on whichever
    thread calls it, until :meth:`Site.shutdown`.

    Args:
      port: The port to listen on, or 0 for any free one.
      apart: Whether the runs are held apart from this process, by each workspace's host --
        which is what lets them outlive it -- or in it.

    Yields:
      The server. Leaving the block lets go of every workspace's runs it reached, and of the
      runs themselves where they were held in this process.

    Raises:
      OSError: If the port cannot be listened on.
    """
    from pathlib import Path

    from hmz.coganchor import releases
    from hmz.runtime.watching.notices import Notices

    from .notifications import Notifications
    from .places import Places
    from .remote import Remotes
    from .runs import Runs
    from .site import Site
    from .verses import fetches

    with contextlib.ExitStack() as held_open:
        places = Places(Path.cwd(), apart=apart)
        held_open.callback(places.close)
        notices = Notices(places.statuses)
        site = Site(port, places=places, runs=Runs(places), notices=notices)
        # What each index lists now, fetched once in the background as the interface starts.
        fetches(places.hmz)
        # And which release of humanize is the newest, where what is kept has got old.
        releases.refresh()
        held_open.callback(site.server_close)
        # Every daemon on another machine let go of as the block ends, and what reached it.
        site.remotes = Remotes()
        held_open.callback(site.remotes.close)
        # Every daemon's notices, as this machine's interface tells them.
        site.notifications = Notifications(site)
        held_open.callback(site.notifications.close)
        # Set first as the block ends, which is what ends every stream being sent.
        held_open.callback(site.going.set)
        # And before it, what ends the notices' streams at once rather than once they wake.
        held_open.callback(notices.close)
        # What stands as it starts to answer is where the notices start from.
        notices.start()
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
      OSError: If the port cannot be listened on.
    """
    with listening(port=port, apart=apart) as site, contextlib.ExitStack() as made:
        shown(site.address)
        if opened is not None:
            from hmz import machine

            page = machine() / f"web-{site.port}.html"
            # Before it is written: one stopped while writing it leaves none behind either.
            made.callback(page.unlink, missing_ok=True)
            _forwarding(site, page)
            # Off the thread that serves: a browser slow to start is no page slow to load.
            threading.Thread(
                target=opened, args=(page.as_uri(),), daemon=True, name="hmz-web-open"
            ).start()
        with contextlib.suppress(KeyboardInterrupt):
            site.serve_forever(poll_interval=0.5)


def _forwarding(site: Site, page: Path) -> None:
    """Writes the page that sends a browser on to the address, where only this account reads.

    Args:
      site: The server, listening.
      page: Where, in this machine's own directory, which is this account's alone.
    """
    page.unlink(missing_ok=True)
    held = os.open(page, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(held, "w", encoding="utf-8") as written:
        written.write(_FORWARD.format(html.escape(site.address)))
