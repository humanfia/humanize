"""The text that names one carrier to one daemon: a route, read and written.

A client keeps, for each daemon, the routes it may be reached by, in the order they are tried,
and a pairing code carries a daemon's routes to a client that has never reached it. Both keep
them as text, so the text is the contract: Section 3.3 of the wire protocol gives it as a
grammar, and a route that does not match it is refused whole rather than read as far as it
goes. What is read is a :class:`Route`, its parts percent-decoded; written back, it is the same
route, spelled the one way this module spells it.
"""

from __future__ import annotations

import contextlib
import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

__all__ = ["KINDS", "TRUSTED", "Route"]

#: Every kind of route there is, as :attr:`Route.kind` names it.
KINDS = frozenset(
    {"unix", "local", "ssh", "wsl", "tcp", "ws", "easytier", "relay", "webrtc"}
)

#: The kinds whose carrier is trusted: reaching the far end of one already took the operating
#: system, `ssh` or WSL admitting the client as the daemon's user (Section 3.5.1).
TRUSTED = frozenset({"unix", "local", "ssh", "wsl"})

# The pieces of RFC 3986 the grammar is made of.
_UNRESERVED = r"[A-Za-z0-9\-._~]"
_PCT = r"%[0-9A-Fa-f]{2}"
_SUB = r"[!$&'()*+,;=]"
_USERINFO = rf"(?:{_UNRESERVED}|{_PCT}|{_SUB}|:)*"
_HOST = rf"(?:\[[^\[\]/?#@]*\]|(?:{_UNRESERVED}|{_PCT}|{_SUB})*)"
_PORT = r"[0-9]*"
_PCHAR = rf"(?:{_UNRESERVED}|{_PCT}|{_SUB}|[:@])"
_WS = rf"(?P<scheme>wss?)://(?P<host>{_HOST})(?::(?P<port>{_PORT}))?(?:/{_PCHAR}*)*"
_PARAM = rf"(?:identity|jump|option)=(?:{_UNRESERVED}|{_PCT}|=)+"

_UNIX = re.compile(rf"unix:(?P<path>/(?:{_UNRESERVED}|{_PCT}|/)*)?")
_SSH = re.compile(
    rf"stdio:ssh://(?:(?P<user>{_USERINFO})@)?(?P<host>{_HOST})(?::(?P<port>{_PORT}))?"
    rf"(?:\?(?P<params>{_PARAM}(?:&{_PARAM})*))?"
)
_WSL = re.compile(rf"stdio:wsl(?::(?P<distro>(?:{_UNRESERVED}|{_PCT})+))?")
_TCP = re.compile(rf"tcp://(?P<host>{_HOST}):(?P<port>{_PORT})")
_WS_URL = re.compile(_WS)
_EASYTIER = re.compile(r"easytier:(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)")
_THROUGH = re.compile(rf"(?P<kind>relay|webrtc):(?P<url>{_WS})")

#: An IPvFuture literal, the one thing between brackets that is not an IPv6 address.
_FUTURE = re.compile(rf"v[0-9A-Fa-f]+\.(?:{_UNRESERVED}|{_SUB}|:)+")

#: What an ssh option may be called, as `ssh_config` names its keywords.
_KEYWORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")

#: What no value handed to `ssh` may hold: a second line, a NUL, or the quote it reads a
#: value's quoting by.
_UNSAYABLE = frozenset('\n\r\0"')

#: What a percent-decoded part keeps unencoded when it is written back.
_KEPT = "-._~"

#: The ssh parameters a route may carry, and the keyword each is handed to `ssh` as.
_SSH_KEYWORDS = {"identity": "IdentityFile", "jump": "ProxyJump"}


@dataclass(frozen=True, slots=True)
class Route:
    """One route, read.

    Attributes:
      kind: Which carrier it names: one of :data:`KINDS`.
      host: The host of a `tcp` or `stdio:ssh` route, percent-decoded and without the brackets
        of an IP literal.
      port: Its port, or None where it names none.
      user: The user of a `stdio:ssh` route, or "" for the one `ssh` picks.
      path: The socket of a `unix:<path>` route, or "" for this machine's daemon's.
      name: The distribution of a `stdio:wsl` route, "" for the default one, or the EasyTier
        entry of an `easytier` route.
      url: The WebSocket URL of a `ws`, `relay` or `webrtc` route, as written.
      options: The parameters of a `stdio:ssh` route, in the order given, each as the ssh
        option it stands for: `(KEYWORD, VALUE)`, `identity` being `IdentityFile` and `jump`
        `ProxyJump`.
    """

    kind: str
    host: str = ""
    port: int | None = None
    user: str = ""
    path: str = ""
    name: str = ""
    url: str = ""
    options: tuple[tuple[str, str], ...] = ()

    @classmethod
    def parse(cls, text: str) -> Route:
        """Reads one route.

        Args:
          text: The route, as a client keeps it or a pairing code carries it.

        Returns:
          It.

        Raises:
          ValueError: `<route> is not a route.`, for text the grammar of Section 3.3 does not
            match, or a `stdio:ssh` parameter that is no ssh option once decoded.
        """
        try:
            route = _parsed(text)
        except (ValueError, UnicodeDecodeError):
            route = None
        if route is None:
            raise ValueError(f"{text} is not a route.")
        return route

    @property
    def trusted(self) -> bool:
        """Whether its carrier is trusted, and so carries frames with no TLS inside it."""
        return self.kind in TRUSTED

    def __str__(self) -> str:
        """The route, written: what :meth:`parse` reads back as this one."""
        if self.kind == "unix":
            return f"unix:{quote(self.path, safe=_KEPT + '/')}"
        if self.kind == "local":
            return "stdio:local"
        if self.kind == "ssh":
            user = f"{quote(self.user, safe=_KEPT)}@" if self.user else ""
            port = f":{self.port}" if self.port is not None else ""
            params = "&".join(_param(keyword, value) for keyword, value in self.options)
            return f"stdio:ssh://{user}{_host(self.host)}{port}" + (
                f"?{params}" if params else ""
            )
        if self.kind == "wsl":
            return (
                f"stdio:wsl:{quote(self.name, safe=_KEPT)}"
                if self.name
                else "stdio:wsl"
            )
        if self.kind == "tcp":
            return f"tcp://{_host(self.host)}:{'' if self.port is None else self.port}"
        if self.kind == "easytier":
            return f"easytier:{self.name}"
        if self.kind in ("relay", "webrtc"):
            return f"{self.kind}:{self.url}"
        return self.url


def _parsed(text: str) -> Route | None:
    """The route `text` is, or None where it is none."""
    if text == "stdio:local":
        return Route("local")
    if found := _UNIX.fullmatch(text):
        return Route("unix", path=unquote(found["path"] or "", errors="strict"))
    if found := _SSH.fullmatch(text):
        host = _bare(found["host"])
        options = _options(found["params"] or "")
        if host is None or options is None:
            return None
        return Route(
            "ssh",
            host=host,
            port=_port(found["port"]),
            user=unquote(found["user"] or "", errors="strict"),
            options=options,
        )
    if found := _WSL.fullmatch(text):
        return Route("wsl", name=unquote(found["distro"] or "", errors="strict"))
    if found := _TCP.fullmatch(text):
        host = _bare(found["host"])
        return (
            None if host is None else Route("tcp", host=host, port=_port(found["port"]))
        )
    if found := _EASYTIER.fullmatch(text):
        return Route("easytier", name=found["name"])
    if (found := _WS_URL.fullmatch(text)) and _bare(found["host"]) is not None:
        return Route("ws", url=text)
    if (found := _THROUGH.fullmatch(text)) and _bare(found["host"]) is not None:
        return Route(found["kind"], url=found["url"])
    return None


def _bare(host: str) -> str | None:
    """A host as it is dialed: decoded, an IP literal out of its brackets; None if it is none."""
    if not host.startswith("["):
        return unquote(host, errors="strict")
    inside = host[1:-1]
    if _FUTURE.fullmatch(inside):
        return inside
    if "%" in inside:
        # RFC 3986 has no zone in an IPv6 literal; `ipaddress` would take one.
        return None
    try:
        ipaddress.IPv6Address(inside)
    except ValueError:
        return None
    return inside


def _host(host: str) -> str:
    """A host as a route writes it: an IP literal in brackets, a name percent-encoded."""
    if _FUTURE.fullmatch(host):
        return f"[{host}]"
    with contextlib.suppress(ValueError):
        if "%" not in host:
            ipaddress.IPv6Address(host)
            return f"[{host}]"
    return quote(host, safe=_KEPT + "!$&'()*+,;=")


def _port(said: str | None) -> int | None:
    return int(said) if said else None


def _options(params: str) -> tuple[tuple[str, str], ...] | None:
    """The ssh options the parameters of a `stdio:ssh` route stand for, or None for a bad one."""
    options: list[tuple[str, str]] = []
    for param in params.split("&") if params else ():
        name, _, value = param.partition("=")
        value = unquote(value, errors="strict")
        if name == "option":
            keyword, equals, value = value.partition("=")
            if not (equals and _KEYWORD.fullmatch(keyword)):
                return None
        else:
            keyword = _SSH_KEYWORDS[name]
        if not value or _UNSAYABLE & set(value):
            return None
        options.append((keyword, value))
    return tuple(options)


def _param(keyword: str, value: str) -> str:
    """One ssh option, written as the parameter of a `stdio:ssh` route that stands for it."""
    said = quote(value, safe=_KEPT)
    for name, named in _SSH_KEYWORDS.items():
        if keyword == named:
            return f"{name}={said}"
    return f"option={quote(keyword, safe=_KEPT)}={said}"
