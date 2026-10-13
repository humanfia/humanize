"""A request of this interface's page, asked of another machine's interface instead.

What a page asks of a daemon on another machine, under `/d/<name>/api/...`, is asked of that
machine's own interface at `/api/...`, through the port forwarded to it, and its answer handed
back as it comes -- a stream of events as each event comes, a file sent or downloaded a piece
at a time. The request is let in there as that interface's own page's: with its key, and saying
it comes from its own origin. Nothing of this interface's own key or cookies goes with it, and
nothing of what that one sets comes back.
"""

from __future__ import annotations

import contextlib
import http.client
from typing import TYPE_CHECKING

from .routing import Refusal

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler

__all__ = ["forwards"]

#: What a request carries on: what it sends and what it asks for, never who it is.
_ASKED = (
    "Accept",
    "Content-Type",
    "Content-Length",
    "If-None-Match",
    "Last-Event-ID",
    "X-Hmz-Filename",
)

#: What an answer does not carry back: what is the connection's own, and the other's cookies.
_KEPT = frozenset(
    {
        "connection",
        "keep-alive",
        "transfer-encoding",
        "set-cookie",
        "server",
        "date",
    }
)

#: What would end a header's line early, and so start another the other side never sent.
_SPLITS = frozenset("\r\n")

#: How much is carried at a time.
_CHUNK = 1 << 16

#: How long, in seconds, the other side may say nothing before it is let go. A stream of
#: events says something more often than this.
_PATIENCE = 300.0


def forwards(
    handler: BaseHTTPRequestHandler,
    port: int,
    said: dict[str, str],
    method: str,
    path: str,
) -> None:
    """Asks the interface on a port what a request asked, and answers the request with it.

    Args:
      handler: The request, not yet answered.
      port: Where the other interface is reached, on this machine's loopback.
      said: What a request to it carries to be let in, by header.
      method: The request's method.
      path: What to ask for there: its path and query.

    Raises:
      Refusal: If it could not be asked, before anything of an answer was sent.
    """
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_PATIENCE)
    try:
        try:
            answer = _asks(handler, connection, said, method, path)
        except (OSError, http.client.HTTPException) as why:
            raise Refusal("The daemon did not answer.", 502) from why
        handler.send_response(answer.status, answer.reason)
        for name, value in answer.getheaders():
            # A header that would break a line of this answer is not carried, whoever sent it.
            if name.lower() not in _KEPT and not _SPLITS.intersection(name + value):
                handler.send_header(name, value)
        if answer.getheader("Content-Length") is None:
            # Without a length, the answer ends where the connection does.
            handler.close_connection = True
        handler.end_headers()
        while chunk := answer.read1(_CHUNK):
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except (OSError, http.client.HTTPException):
        # Cut off once answering had begun: nothing is left to say but to stop.
        handler.close_connection = True
    finally:
        connection.close()


def _asks(
    handler: BaseHTTPRequestHandler,
    connection: http.client.HTTPConnection,
    said: dict[str, str],
    method: str,
    path: str,
) -> http.client.HTTPResponse:
    """Sends the request on, what it sends a piece at a time, and reads how it is answered."""
    if handler.headers.get("Transfer-Encoding") is not None:
        raise Refusal("Say how long what is sent is.", 411)
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError as why:
        raise Refusal("Say how long what is sent is.", 411) from why
    if length < 0:
        raise Refusal("Say how long what is sent is.", 411)
    connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for name in _ASKED:
        value = handler.headers.get(name)
        if value is not None:
            connection.putheader(name, value)
    for name, value in said.items():
        connection.putheader(name, value)
    connection.endheaders()
    left = length
    # An answer given before everything was sent -- a refusal -- is still the answer.
    with contextlib.suppress(BrokenPipeError, ConnectionResetError):
        while left:
            chunk = handler.rfile.read(min(left, _CHUNK))
            if not chunk:
                raise Refusal("What was sent was cut short.", 400)
            connection.send(chunk)
            left -= len(chunk)
    if left:
        # What was not read of what was sent is no next request.
        handler.close_connection = True
    return connection.getresponse()
