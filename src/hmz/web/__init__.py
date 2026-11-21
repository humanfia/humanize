"""The web interface: every daemon the page reaches, drawn in a browser.

    hmz web

One more client of the daemons, as the terminal interface is: the page `hmz web` serves is a
client of this machine's daemon and of every other the user adds, over JSON-RPC (protocol/
wire.md), and this process holds no epic itself. What it serves is the page's own files, the
directory it started in (`/here`), the WebSocket `/rpc` carried to this machine's daemon's
socket, and the WebSocket `/dial` carried to another machine's daemon over a carrier a browser
cannot open (Section 4 of protocol/web.md).
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

__all__ = ["is_origin", "kept_port", "listening", "serve"]

#: The page a browser is opened on, which goes on to the address: the key is in a file only
#: this account can read rather than on the command line of the browser, which every account
#: on the machine can.
_FORWARD = (
    '<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
    '<meta http-equiv="refresh" content="0;url={0}"><title>Humanize</title>'
    '<a href="{0}">Open Humanize</a>'
)

#: The ports there are, but 0.
_PORTS = range(1, 65536)


def _port_file() -> Path:
    """`<home>/web-port`, the port the last `hmz web` of this home listened on."""
    from hmz import home

    return home() / "web-port"


def kept_port() -> int:
    """The port the last `hmz web` of this home listened on, or 0 where none is kept.

    A file that does not hold a port from 1 to 65535 is read as none (Section 4.15 of
    files.md).
    """
    try:
        said = _port_file().read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError):
        return 0
    if not said.isdigit() or int(said) not in _PORTS:
        return 0
    return int(said)


def is_origin(said: str) -> bool:
    """Whether a text is an origin a page can be served at, as `--origin` takes one.

    Args:
      said: The text.

    Returns:
      True for `<scheme>://<host>[:<port>]` over `http` or `https` with nothing after it.
    """
    from .site import _origin  # pyright: ignore[reportPrivateUsage]

    return _origin(said) is not None


def _keeps(port: int) -> None:
    """Writes the port listened on, by atomic replacement, where it has changed."""
    if kept_port() == port:
        return
    at = _port_file()
    with contextlib.suppress(OSError):
        at.parent.mkdir(parents=True, exist_ok=True)
        beside = at.with_name(f".web-port.{os.getpid()}")
        beside.write_text(str(port), encoding="ascii")
        beside.replace(at)


@contextlib.contextmanager
def listening(*, port: int = 0, origin: str = "") -> Generator[Site]:
    """The web interface, listening on this machine's loopback for as long as the block runs.

    This machine's daemon is reached first, started where none runs. Listening is not
    answering: what answers is :meth:`Site.serve_forever`, on whichever thread calls it, until
    :meth:`Site.shutdown`.

    Args:
      port: The port to listen on, or 0 for any free one.
      origin: The origin a proxy that rewrites `Host` serves the page at, or "" for none.

    Yields:
      The server.

    Raises:
      hmz.daemon.Older: If this machine's daemon is one of an older Humanize.
      OSError: If the daemon cannot be reached, or the port cannot be listened on.
      ValueError: If the origin is not one.
    """
    from .site import Site

    _reaches()
    site = Site(port, origin)
    try:
        yield site
    finally:
        site.server_close()


def _reaches() -> None:
    """Reaches this machine's daemon, starting it where none runs (Section 8.2.3 of cli.md).

    Raises:
      hmz.daemon.Older: If it is one of an older Humanize.
      OSError: If it cannot be reached.
    """
    import errno

    from hmz import daemon

    try:
        daemon.start()
    except OSError as why:
        if why.errno == errno.EADDRINUSE:
            raise daemon.Older(why.strerror or str(why)) from why
        raise


@contextlib.contextmanager
def _held_back() -> Generator[None]:
    """Keeps the signals that stop the server from arriving until this is left.

    Where the platform cannot hold a signal back -- Windows -- nothing is held.
    """
    import signal

    if not hasattr(signal, "pthread_sigmask"):
        yield
        return
    stopping = {signal.SIGINT, signal.SIGTERM, signal.SIGHUP}
    before = signal.pthread_sigmask(signal.SIG_BLOCK, stopping)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, before)


def serve(
    *,
    port: int | None = None,
    origin: str = "",
    shown: Callable[[str], object] = print,
    opened: Callable[[str], object] | None = None,
) -> None:
    """Serves the web interface on this machine's loopback, until it is interrupted.

    Args:
      port: The port to listen on, 0 for any free one, or None for the one the last `hmz web`
        of this home listened on -- any free one where that cannot be listened on.
      origin: The origin a proxy that rewrites `Host` serves the page at, as
        `<scheme>://<host>[:<port>]`, or "" for none (Section 4.4.6 of web.md).
      shown: What the address is said through, once the server is listening. The address
        carries the key a browser is let in with.
      opened: What opens that address in a browser, or None to leave that to whoever reads it.

    Raises:
      hmz.daemon.Older: If this machine's daemon is one of an older Humanize.
      OSError: If the daemon cannot be reached, or the port cannot be listened on.
      ValueError: If the origin is not one.
    """
    from .site import Site

    _reaches()
    if port is None:
        try:
            site = Site(kept_port(), origin)
        except OSError:
            # The port kept is taken now: any free one (Section 8.1.2 of cli.md).
            site = Site(0, origin)
    else:
        site = Site(port, origin)
    with contextlib.ExitStack() as made:
        made.callback(site.server_close)
        _keeps(site.port)
        shown(site.address)
        if opened is not None:
            from hmz import machine

            page = machine() / f"web-{site.port}.html"
            # Before it is written: one stopped while writing it leaves none behind either.
            made.callback(page.unlink, missing_ok=True)
            _forwarding(site, page)
            # Off the thread that serves: a browser slow to start is no page slow to load.
            opening = threading.Thread(
                target=opened, args=(page.as_uri(),), daemon=True, name="hmz-web-open"
            )
            # A signal that stops this raises here; raised while the thread is being
            # started it would leave a lock of `threading` half let go, and end this with
            # that error rather than stopped. So it waits until the server is serving.
            with _held_back():
                opening.start()
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
