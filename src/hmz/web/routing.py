"""What one request to the web interface is, and the forms an answer to one takes.

Every route the interface answers is written once, as a method, a path and what answers it:
the server dispatches by that table and nothing else, and a route that is not in it is not
there. What a route answers is JSON, a file to download, or a stream of events; what it
refuses, it refuses with a sentence the page shows as it is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path
    from threading import Event

__all__ = ["Asked", "Download", "Refusal", "Route", "Stream", "routes"]


class Refusal(Exception):  # noqa: N818 -- what the page is told, not what went wrong here
    """A request this interface will not do, with the sentence the page shows for it.

    Attributes:
      status: The HTTP status it is answered with.
    """

    def __init__(self, sentence: str, status: int = 400) -> None:
        super().__init__(sentence)
        self.status = status


@dataclass(frozen=True, slots=True)
class Asked:
    """One request, as a route is handed it.

    Attributes:
      site: The interface it reached, which holds the workspace and the runs.
      matched: What the route's path took out of the request's, by name.
      query: The query string, a value per name -- the last, where one was given twice.
      body: What a write sent, which is JSON; empty for a read.
    """

    site: Any
    matched: dict[str, str] = field(default_factory=dict[str, str])
    query: dict[str, str] = field(default_factory=dict[str, str])
    body: dict[str, Any] = field(default_factory=dict[str, Any])

    def text(self, name: str, *, required: bool = True) -> str:
        """One string the body sent.

        Args:
          name: Which.
          required: Whether a request missing it is refused, rather than read as "".

        Returns:
          It.

        Raises:
          Refusal: If it is missing where it is required, or is not a string.
        """
        said = self.body.get(name, None if required else "")
        if not isinstance(said, str) or (required and not said):
            raise Refusal(f"Say {name}, as text.")
        return said

    def texts(self, name: str) -> list[str]:
        """A list of strings the body sent, or none where it sent nothing.

        Raises:
          Refusal: If it sent something else.
        """
        said: object = self.body.get(name, [])
        if not isinstance(said, list) or not all(
            isinstance(one, str) for one in cast("list[object]", said)
        ):
            raise Refusal(f"Say {name} as a list of text.")
        return cast("list[str]", said)

    def named(self, name: str) -> dict[str, Any]:
        """An object the body sent, by name, or an empty one where it sent nothing.

        Raises:
          Refusal: If it sent something else.
        """
        said: object = self.body.get(name) or {}
        if not isinstance(said, dict):
            raise Refusal(f"Say {name} as values by name.")
        return cast("dict[str, Any]", said)


@dataclass(frozen=True, slots=True)
class Download:
    """A file to hand the browser to save, rather than JSON to read.

    Attributes:
      path: Where the file is.
      name: What the browser saves it as.
      kind: Its media type.
      gone: Whether the file is this answer's own, to be removed once it has been sent.
    """

    path: Path
    name: str
    kind: str = "application/octet-stream"
    gone: bool = False


@dataclass(frozen=True, slots=True)
class Stream:
    """Events to send for as long as the browser listens, as a server-sent event stream.

    Attributes:
      events: Made with where to carry on from -- what the browser last heard, or "" -- and
        an event set once the server is going; yields each event as its id (or ""), its
        name and its data, and a `None` whenever nothing has happened for a while.
    """

    events: Callable[[str, Event], Iterator[tuple[str, str, Any] | None]]


@dataclass(frozen=True, slots=True)
class Route:
    """One thing the interface answers.

    Attributes:
      method: `GET` for a read, `POST` for a write.
      path: The path, with `{name}` where a part of it is taken out by name.
      answers: What answers it, handed the request.
    """

    method: str
    path: str
    answers: Callable[[Asked], Any]

    def match(self, method: str, path: str) -> dict[str, str] | None:
        """What this route takes out of a request's path, or None where it is not this route.

        Args:
          method: The request's method.
          path: The request's path, without its query.

        Returns:
          Each part named in the route's path, as it was written in the request's.
        """
        if method != self.method:
            return None
        found = re.fullmatch(
            re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>[^/]+)", re.escape(self.path)), path
        )
        return found.groupdict() if found else None


def routes(*held: tuple[str, str, Callable[[Asked], Any]]) -> tuple[Route, ...]:
    """A table of routes, each written as its method, its path and what answers it.

    Args:
      held: The routes.

    Returns:
      Them, as `Route`s.
    """
    return tuple(Route(method, path, answers) for method, path, answers in held)
