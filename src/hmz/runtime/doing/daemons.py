"""The daemons a frontend may switch between: this machine's, and each other one written down.

`Local` is always there and never written down. Every other daemon is kept in Humanize's one
settings file under `daemons` (Section 3.4.6 of the files): its name, the daemon id this
machine pins, `""` until it is first reached over a trusted carrier, and its routes, in the
order they are tried. An entry an earlier release wrote -- an ssh host, or an EasyTier secret
and its nodes -- is read as the `stdio:ssh` or `easytier:` route it reached, and written so at
the next write.

A daemon is reached when it is first asked for, or is told to connect, by racing its routes
(`hmz.reach`), mutual TLS on an untrusted one (`hmz.trust`), and `session.hello` (`hmz.rpc`);
and reached again, waiting longer each time, whenever it is lost. Over `stdio:ssh` the host is
asked first what `hmz` it has, and an `hmz` missing there, or of another version than this
one, is installed at this version with `uv tool install`, uv itself fetched first where the
host has none -- but never in place of one the host's daemon may be running epics under, which
keep running the release they started with. A development build, `0.0.0`, installs nothing:
it uses whatever `hmz` is there.
"""

from __future__ import annotations

import contextlib
import queue
import re
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from hmz.runtime.runner import Refused

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence
    from types import TracebackType

    from hmz.coganchor.transport import Road
    from hmz.reach import EasyTier, Route
    from hmz.rpc import Call, Kind, Pipe

__all__ = [
    "ASKING",
    "CARRIED",
    "CONNECTING",
    "FAILED",
    "IDLE",
    "INSTALLING",
    "LOCAL",
    "UP",
    "Client",
    "Daemons",
    "Dialing",
    "Remotes",
    "Unreached",
    "carried",
    "said",
]

#: The daemon of this machine, which is always there and never written down.
LOCAL = "local"

#: The key of the settings file the daemons are kept under.
_KEY = "daemons"

#: What a daemon's name is spelled with: never starting with a dot, so never `.` or `..`.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: What an entry holds beside its name (Section 3.4.6.2 of the files).
_FIELDS = frozenset({"id", "routes"})

#: What an entry an earlier release wrote holds beside its name (Section 3.4.6.8 of the files).
_EARLIER = frozenset(
    {
        "via",
        "host",
        "user",
        "port",
        "identity_file",
        "proxy_jump",
        "options",
        "alias",
        "config",
        "secret",
        "peers",
    }
)

#: The settings a batch apply carries from one daemon to others, by the page each is set on:
#: never the accounts, which only a secret sets.
CARRIED = ("general", "nous", "runtimes", "backup")


def _named_first(every: Sequence[Any]) -> list[Any]:
    """Every nous, each after the virtual nous its graph and its `then` name."""
    held = {one.name: one for one in every}
    done: list[Any] = []
    seen: set[str] = set()

    def names(graph: Any) -> list[str]:
        nodes = graph.nodes if graph is not None else ()
        return [
            name for node in nodes for name in (node.use, *(n for n, _ in node.among))
        ]

    def visit(one: Any) -> None:
        if one.name in seen:
            return
        seen.add(one.name)
        for name in [*names(one.graph), *names(one.then)]:
            if name in held:
                visit(held[name])
        done.append(one)

    for one in every:
        visit(one)
    return done


def carried(hmz: Any, pages: Sequence[str]) -> list[tuple[str, dict[str, Any]]]:
    """The RPC calls that write one daemon's settings to another, of the pages asked for.

    A backup target's URL goes with nothing signed into it, so that a target that signs in is
    refused there rather than its secret carried.

    Args:
      hmz: The daemon's own Humanize, whose settings are carried.
      pages: Which of :data:`CARRIED`.

    Returns:
      Each method and its parameters, in the order they are called (Section 4.18 of daemon.md).
    """
    settings = hmz.settings
    sent: list[tuple[str, dict[str, Any]]] = []
    if "general" in pages:
        general: dict[str, Any] = {"details": settings.details}
        if settings.enable_sentry is not None:
            general["reports"] = settings.enable_sentry
        sent.append(("settings.set", general))
    if "nous" in pages:
        book = hmz.nous
        sent += [
            (
                "nous.set",
                {
                    "name": one.name,
                    "tries": one.tries,
                    "policy": one.policy,
                    "timeout": one.timeout,
                    "graph": book.shown(one.graph),
                    "then": book.shown(one.then),
                },
            )
            # Each nous after every virtual one its graphs name, so that each write names
            # only nous the daemon already has.
            for one in _named_first(book.all())
        ]
    if "runtimes" in pages:
        for one in hmz.runtimes.all():
            fields = dict(one.held())
            backend, name = fields.pop("backend"), fields.pop("name")
            fields.pop("made", None)
            sent.append(
                (
                    "runtimes.set",
                    {
                        "backend": backend,
                        "name": name,
                        "fields": fields,
                        "replace": True,
                    },
                )
            )
    if "backup" in pages:
        targets = [
            {
                "name": one.name,
                "url": hmz.verses.plain(one.url),
                "branch": one.branch,
                "policies": list(one.policies),
                "every": one.every,
            }
            for one in hmz.backups.targets()
        ]
        sent.append(
            (
                "settings.set",
                {
                    "backup": {
                        "targets": targets,
                        "defaults": list(hmz.backups.defaults()),
                    }
                },
            )
        )
    return sent


class Unreached(RuntimeError):  # noqa: N818 -- what it is, as `Refused` is named
    """A daemon that is not up, or that refused what it was asked.

    Attributes:
      seen: How it stands, `{state, detail, version}`, where it is not up; else empty.
      status: The error code it refused with, or 503 where it was not reached.
    """

    def __init__(
        self, sentence: str, seen: dict[str, str] | None = None, status: int = 503
    ) -> None:
        super().__init__(sentence)
        self.seen = seen or {}
        self.status = status


def _checked(
    name: str, fields: Mapping[str, Any], *, earlier: bool = False
) -> dict[str, Any]:
    """One daemon as it is written down: its name, the id it is pinned to, and its routes.

    Args:
      name: What it is called.
      fields: `id`, `""` where absent, and `routes`.
      earlier: Whether it may be an EasyTier daemon an earlier release wrote, which pinned no
        id (Section 3.4.6.8 of the files): kept, though it is reached only once paired.

    Returns:
      It, as it is written.

    Raises:
      ValueError: If it cannot be one.
    """
    from hmz.reach import Route
    from hmz.trust.identity import is_fingerprint

    if not _NAMED.fullmatch(name) or name.lower() == LOCAL:
        raise ValueError(
            f"A daemon cannot be called {name!r}: say a letter or digit, then letters, "
            f"digits, dots, dashes and underscores, and not {LOCAL}."
        )
    if extra := sorted(set(fields) - _FIELDS):
        raise ValueError(f"A daemon takes no {', '.join(extra)}.")
    pinned: object = fields.get("id", "")
    if pinned != "" and not is_fingerprint(pinned):
        raise ValueError('Say id as a daemon id, 52 base32 characters, or "".')
    routes: object = fields.get("routes")
    if (
        not isinstance(routes, list)
        or not routes
        or not all(isinstance(one, str) for one in cast("list[object]", routes))
    ):
        raise ValueError("Say routes as a list of at least one route.")
    said = cast("list[str]", routes)
    parsed = [Route.parse(one) for one in said]
    if pinned == "" and not (
        parsed[0].trusted or (earlier and parsed[0].kind == "easytier")
    ):
        raise ValueError(f"{parsed[0]} needs the id of the daemon it reaches.")
    return {"name": name, "id": pinned, "routes": list(said)}


def _migrated(
    name: str, fields: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """An entry an earlier release wrote, as the entry its keys reached and its EasyTier entry.

    Raises:
      ValueError: If it reached nothing.
    """
    from hmz.coganchor import easytier
    from hmz.reach import Route

    if fields.get("via") == "easytier":
        secret: object = fields.get("secret")
        peers: object = fields.get("peers")
        if not isinstance(secret, str) or not isinstance(peers, list) or not peers:
            raise ValueError(f"{name} names no EasyTier network.")
        network = {
            "secret": easytier.checked(secret),
            "nodes": [easytier.node(str(one)) for one in cast("list[object]", peers)],
        }
        routes = [f"easytier:{name}"]
        return _checked(name, {"id": "", "routes": routes}, earlier=True), network
    options: Any = fields.get("options") or []
    pairs = (
        cast("dict[Any, Any]", options).items()
        if isinstance(options, dict)
        else options
    )
    said = [
        (keyword, str(fields.get(field) or ""))
        for keyword, field in (
            ("IdentityFile", "identity_file"),
            ("ProxyJump", "proxy_jump"),
        )
    ]
    try:
        route = Route(
            "ssh",
            host=str(fields.get("alias") or fields.get("host") or ""),
            port=int(fields.get("port") or 0) or None,
            user="" if fields.get("alias") else str(fields.get("user") or ""),
            options=tuple(
                (str(keyword), str(value))
                for keyword, value in [*said, *pairs]
                if value
            ),
        )
    except (TypeError, ValueError) as why:
        raise ValueError(f"{name} names no ssh host.") from why
    return _checked(name, {"id": "", "routes": [str(route)]}), None


def _read(held: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every daemon a reading of the settings file holds, in order, each checked.

    One that cannot be one -- written wrong by hand, or under a name taken before it -- is
    left out, and so is gone the next time the daemons are written.

    Returns:
      The daemons, and the EasyTier entry of each an earlier release wrote one of, by name.
    """
    there: object = held.get(_KEY)
    kept: list[dict[str, Any]] = []
    networks: dict[str, Any] = {}
    for one in cast("list[object]", there) if isinstance(there, list) else []:
        fields = dict(cast("dict[str, Any]", one)) if isinstance(one, dict) else {}
        name = fields.pop("name", None)
        if not isinstance(name, str) or any(name == each["name"] for each in kept):
            continue
        try:
            if set(fields) <= _EARLIER:
                entry, network = _migrated(name, fields)
            elif frozenset(fields) == _FIELDS:
                entry, network = _checked(name, fields, earlier=True), None
            else:
                continue
        except ValueError:
            continue
        kept.append(entry)
        if network is not None:
            networks[name] = network
    return kept, networks


def _changes(change: Callable[[list[dict[str, Any]]], None]) -> None:
    """Makes one change to the daemons written down, and to nothing else in the file.

    An entry an earlier release wrote is written as it is read, its EasyTier entry beside it.

    Raises:
      OSError: If the file cannot be written.
    """
    from hmz.coganchor import settings

    def changing(held: dict[str, Any]) -> None:
        daemons, networks = _read(held)
        change(daemons)
        held[_KEY] = daemons
        if networks:
            written: object = held.get("easytier")
            ours = cast("dict[str, Any]", written) if isinstance(written, dict) else {}
            held["easytier"] = networks | ours

    settings.changes(changing)


def _named(alias: str) -> str:
    """What a host of the ssh config is called as a daemon: anything no name holds a dash."""
    return re.sub(r"[^A-Za-z0-9._-]", "-", alias).lstrip("._-")


def _offers(alias: str) -> dict[str, Any]:
    """The daemon a host of the ssh config would be: reached by `ssh` resolving its `Host`.

    Raises:
      ValueError: If it cannot be one.
    """
    from hmz.reach import Route

    return _checked(
        _named(alias), {"id": "", "routes": [str(Route("ssh", host=alias))]}
    )


class Daemons:
    """The daemons written down, and reaching them: what every frontend switches between."""

    #: What a batch apply carries to them, as :data:`CARRIED`.
    CARRIED: ClassVar = CARRIED

    def all(self) -> list[dict[str, Any]]:
        """Every daemon written down, `{name, id, routes}`, in order."""
        from hmz.coganchor import settings

        return _read(settings.read())[0]

    def find(self, name: str) -> dict[str, Any] | None:
        """The daemon written down under a name, or None where there is none."""
        return next((one for one in self.all() if one["name"] == name), None)

    def write(
        self, name: str, fields: dict[str, Any], *, replace: bool = False
    ) -> dict[str, Any]:
        """Writes one daemon down, or over the one of its name where it is to `replace` it.

        Returns:
          It, as it is written.

        Raises:
          ValueError: If it cannot be one.
          FileExistsError: If one is called that already and it is not to be replaced.
          OSError: If the file cannot be written.
        """
        entry = _checked(name, fields)

        def change(daemons: list[dict[str, Any]]) -> None:
            at = next((i for i, one in enumerate(daemons) if one["name"] == name), -1)
            if at < 0:
                daemons.append(entry)
            elif replace:
                daemons[at] = entry
            else:
                raise FileExistsError(f"There is a daemon called {name} already.")

        _changes(change)
        return entry

    def remove(self, name: str) -> None:
        """Forgets how to reach one daemon; what is on its machine stays as it is.

        Raises:
          ValueError: For Local, which is always there.
          LookupError: If none is called that.
          OSError: If the file cannot be written.
        """
        if name.lower() == LOCAL:
            raise ValueError("Local is always there, and cannot be removed.")

        def change(daemons: list[dict[str, Any]]) -> None:
            kept = [one for one in daemons if one["name"] != name]
            if len(kept) == len(daemons):
                raise LookupError(f"There is no daemon called {name}.")
            daemons[:] = kept

        _changes(change)

    def offered(self) -> dict[str, dict[str, Any]]:
        """Each host of the ssh config not written down yet, as the daemon it would be.

        Of two that would be called the same, the first is offered.

        Raises:
          OSError: If the ssh config cannot be read.
        """
        from hmz.coganchor.machines import sshconfig

        daemons = self.all()
        names = {one["name"] for one in daemons}
        taken = {route for one in daemons for route in one["routes"]}
        offered: dict[str, dict[str, Any]] = {}
        for alias in sshconfig.aliases():
            try:
                one = _offers(alias)
            except ValueError:
                continue
            if one["name"] not in names and one["routes"][0] not in taken:
                names.add(one["name"])
                offered[alias] = one
        return offered

    def imported(self, wanted: Sequence[str]) -> list[str]:
        """Brings hosts of the ssh config in as daemons, by their Host, skipping any there.

        Returns:
          What each one brought in is called.

        Raises:
          ValueError: For none, or for a host that cannot be one.
          LookupError: For a host the ssh config does not name.
          OSError: If the ssh config cannot be read, or the file written.
        """
        from hmz.coganchor.machines import sshconfig

        if not wanted:
            raise ValueError("Say aliases as the hosts to bring in, by their Host.")
        there = sshconfig.aliases()
        if missing := [one for one in wanted if one not in there]:
            raise LookupError(f"Your ssh config has no host {', '.join(missing)}.")
        offers: list[dict[str, Any]] = []
        for alias in dict.fromkeys(wanted):
            try:
                offers.append(_offers(alias))
            except ValueError as why:
                raise ValueError(f"{alias} cannot be a daemon: {why}") from why
        added: list[str] = []

        def change(daemons: list[dict[str, Any]]) -> None:
            names = {one["name"] for one in daemons}
            taken = {route for one in daemons for route in one["routes"]}
            for one in offers:
                if one["name"] not in names and one["routes"][0] not in taken:
                    daemons.append(one)
                    names.add(one["name"])
                    added.append(one["name"])

        _changes(change)
        return added

    def remotes(
        self,
        version: str | None = None,
        *,
        install: bool | None = False,
        kind: Kind = "sdk",
    ) -> Remotes:
        """Every daemon written down, each reached as it is first asked for, until closed.

        Args:
          version: The version of `hmz` installed over `stdio:ssh` where another is found;
            this one's by default.
          install: What is done where no `hmz` is found there: `False` installs nothing,
            `True` installs unasked, and `None` has the daemon `asking` until
            :meth:`Remotes.answer` answers it.
          kind: What whoever reaches them is, as each session's `session.hello` says it.
        """
        return Remotes(version, install=install, kind=kind)


def _pins(name: str, daemon: str) -> None:
    """Pins the id a daemon first answered over a trusted carrier, where none is pinned yet.

    Raises:
      OSError: If the file cannot be written.
    """

    def change(daemons: list[dict[str, Any]]) -> None:
        for one in daemons:
            if one["name"] == name and one["id"] == "":
                one["id"] = daemon

    _changes(change)


def _networks() -> dict[str, EasyTier]:
    """This machine's EasyTier entries, by name, an earlier release's daemons' among them."""
    from hmz.coganchor import settings
    from hmz.reach import EasyTier

    held = settings.read()
    written: object = held.get("easytier")
    entries = _read(held)[1] | (
        cast("dict[str, Any]", written) if isinstance(written, dict) else {}
    )
    networks: dict[str, EasyTier] = {}
    for name, one in entries.items():
        entry = cast("dict[str, Any]", one) if isinstance(one, dict) else {}
        secret, nodes = entry.get("secret"), entry.get("nodes")
        if isinstance(secret, str) and isinstance(nodes, list):
            networks[name] = EasyTier(
                secret, tuple(str(node) for node in cast("list[object]", nodes))
            )
    return networks


#: The release of uv fetched onto a host that has none, through astral's installer for it:
#: the one Humanize Desktop pins.
UV = "0.12.24"

#: What a daemon's state may be (Section 3.8.2.2 of daemon.md).
IDLE, CONNECTING, ASKING, INSTALLING, UP, FAILED = (
    "idle",
    "connecting",
    "asking",
    "installing",
    "up",
    "failed",
)

#: What every command there runs with: where `uv tool` and astral's installer put what they
#: install, which a shell that is not a login one may not have on its `PATH`.
_PATH = 'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"; '

#: What is asked of a host before anything is started there: the version of its `hmz`,
#: whether that has `hmz daemon connect`, and whether its daemon is running -- by the process
#: `daemon.json` names in `humanize-<uid>` of any temporary directory one may have been
#: started with, as Humanize Desktop tells -- `unknown` where that cannot be read.
_PROBE = (
    _PATH
    + r"""
echo "hmz: $(hmz --version 2>/dev/null | sed -n 's/^hmz //p' | tail -n 1)"
echo "connect: $(hmz daemon connect --help >/dev/null 2>&1 && echo yes || echo no)"
daemon=none
for under in "$TMPDIR" "$TEMP" "$TMP" "$(getconf DARWIN_USER_TEMP_DIR 2>/dev/null)" \
    /tmp /var/tmp; do
  [ -n "$under" ] || continue
  record="${under%/}/humanize-$(id -u)/daemon.json"
  [ -e "$record" ] || continue
  if [ ! -r "$record" ]; then daemon=unknown; continue; fi
  pid=$(sed -n 's/.*"pid": *\([0-9][0-9]*\).*/\1/p' "$record" | head -n 1)
  if [ -z "$pid" ]; then daemon=unknown
  elif kill -0 "$pid" 2>/dev/null || ps -p "$pid" >/dev/null 2>&1; then
    daemon=running; break
  fi
done
echo "daemon: $daemon"
"""
)

#: Installs `hmz` as `{wanted}` names it, `hmz==<version>` or the bare `hmz` of the latest
#: release, fetching uv first where there is none; `{checked}` is what follows the install.
_INSTALL = _PATH + (
    "export UV_NO_MODIFY_PATH=1; "
    "if ! command -v uv >/dev/null 2>&1; then "
    f"echo 'Getting uv {UV}'; "
    "if command -v curl >/dev/null 2>&1; "
    f"then curl -LsSf https://astral.sh/uv/{UV}/install.sh | sh; "
    f"else wget -qO- https://astral.sh/uv/{UV}/install.sh | sh; fi; "
    "command -v uv >/dev/null 2>&1 || exit 1; fi; "
    "uv tool install --force --python '>=3.12' '{wanted}'{checked}"
)

#: What follows the install of a release this build did not pick: one with no `hmz daemon
#: connect` is removed again, and said to be too old (Section 3.8.3.12 of daemon.md).
_CHECKED = (
    " && { hmz daemon connect --help >/dev/null 2>&1 || "
    "{ uv tool uninstall hmz >/dev/null 2>&1; "
    "echo 'The latest release of hmz is too old to be reached: it has no daemon command.'; "
    "exit 1; }; }"
)

#: What `ssh` is told for the probe and the install before what the route says, since ssh
#: keeps the first value it is given: nothing is asked of anybody, since nobody is at a
#: terminal to answer (Section 3.8.2.6 of daemon.md).
_UNASKED = (("BatchMode", "yes"), ("ConnectTimeout", "20"))

#: How long, in seconds, asking a host what it has may take.
_PROBING = 60.0

#: How long installing `hmz` there may take.
_INSTALLING = 900.0

#: How long whoever asks for a daemon not yet reached waits for it.
_WAITING = 30.0

#: How long one question to a daemon reached may go unanswered.
_ASKING = 120.0

#: How long a process is given to stop before it is killed.
_STOPPING = 3.0

#: What a call on a session that has ended is refused with (Section 4.21.7 of python.md).
_WENT = "the daemon went away"


class _Failed(Exception):  # noqa: N818 -- the sentence a daemon's state says
    """Reaching a daemon went wrong, as its state says it."""


def _here_version() -> str:
    """This Humanize's version, as PyPI has it."""
    from importlib.metadata import version

    return version("hmz")


def _entry(name: str) -> dict[str, Any] | None:
    """The daemon written down by that name, or None."""
    if name == LOCAL:  # This machine, whatever is written down.
        return None
    return Daemons().find(name)


def said(lines: Sequence[str]) -> dict[str, str]:
    """What a host answered the probe with, by what each line says it is."""
    found: dict[str, str] = {}
    for line in lines:
        key, colon, value = line.partition(":")
        if colon and key in ("hmz", "connect", "daemon"):
            found[key] = value.strip()
    return found


def _last(lines: Sequence[str], otherwise: str) -> str:
    """The last line said, or what is said otherwise."""
    return next((line for line in reversed(lines) if line.strip()), otherwise).strip()


def _road(route: Route) -> Road:
    """How a command is run on the host of a `stdio:ssh` route, asking nobody anything.

    Raises:
      ValueError: For a destination `ssh` would read as an option or as more than one.
    """
    from hmz.coganchor.transport import Road, Target
    from hmz.reach import command

    command(route)
    login = f"{route.user}@{route.host}" if route.user else route.host
    return Road.to(
        Target(
            "ssh", host=login, port=route.port or 0, options=(*_UNASKED, *route.options)
        )
    )


#: Where a client's notifications wait for its listener: each `(method, params)`, then None.
type _Inbox = queue.SimpleQueue[tuple[str, dict[str, Any]] | None]


class _Session:
    """One session with a daemon, `session.hello` said, shared by every client of it.

    Attributes:
      peer: Its end of the session.
      said: What `session.hello` answered.
    """

    def __init__(
        self,
        pipe: Pipe,
        route: Route,
        pinned: str,
        name: str,
        *,
        client: str = "",
        kind: Kind = "sdk",
        until: float | None = None,
    ) -> None:
        """Opens the session over a carrier secured, and holds it to the id pinned.

        Args:
          pipe: The carrier, secured where it is untrusted.
          route: The route it was reached by.
          pinned: The daemon id pinned, `""` for none.
          name: What the daemon is called.
          client: What this client is called in `session.hello`; this machine's host name
            where it is `""`.
          kind: What this client is.
          until: When, on the monotonic clock, the 30 seconds its carrier was started with
            end (Section 3.4.9 of wire.md); 30 seconds from now where it is `None`.

        Raises:
          _Failed: If the daemon refused hello, did not answer it by then, or
            answered as another daemon than the one pinned, or the carrier ended first:
            with what the carrier said as it ended, where it said anything.
        """
        from hmz.reach import OPENING
        from hmz.rpc import Closed, Peer, RpcError, hello
        from hmz.trust.identity import host

        self._lock = threading.Lock()
        self._inboxes: list[_Inbox] = []
        self.peer = Peer(pipe, self._serves, name=f"hmz-remote-{name}")
        self.peer.closing(self._ended)
        try:
            left = OPENING if until is None else max(until - time.monotonic(), 0)
            self.said = hello(self.peer, client or host(), kind, timeout=left)
        except RpcError as why:
            self.peer.close()
            raise _Failed(why.message) from why
        except Closed as why:
            # What the carrier said as it ended, which an error of the system's is not.
            said = why.__cause__
            told = str(said) if isinstance(said, OSError) and not said.errno else ""
            raise _Failed(told or f"{route} closed before it said hello.") from why
        except TimeoutError as why:
            self.peer.close()
            raise _Failed(f"{route} did not open within {OPENING:g} seconds.") from why
        if pinned and self.said.get("daemon_id") != pinned:
            self.peer.close()
            raise _Failed(f"{name} is not the daemon it was paired with.")

    def hears(self, inbox: _Inbox) -> None:
        """Puts every notification from here on in `inbox` too, then None once it ends."""
        with self._lock:
            if not self.peer.closed:
                self._inboxes.append(inbox)
                return
        inbox.put(None)

    def forgets(self, inbox: _Inbox) -> None:
        """Puts no more notifications in `inbox`."""
        with self._lock, contextlib.suppress(ValueError):
            self._inboxes.remove(inbox)

    def _serves(self, call: Call) -> None:
        from hmz.rpc import Code, RpcError

        if call.id is not None:
            call.fail(
                RpcError(Code.METHOD_NOT_FOUND, f"There is no method {call.method}.")
            )
            return
        with self._lock:
            inboxes = list(self._inboxes)
        for inbox in inboxes:
            inbox.put((call.method, call.params))

    def _ended(self) -> None:
        with self._lock:
            inboxes, self._inboxes = self._inboxes, []
        for inbox in inboxes:
            inbox.put(None)

    def close(self) -> None:
        self.peer.close()


class Client:
    """One session of the wire protocol with one daemon (Section 4.21 of python.md).

    What :meth:`Remotes.client` hands out: the one session the `Remotes` holds to that daemon,
    which closing a client leaves open for the others, and closing the `Remotes` closes. One
    made :meth:`over` a pipe of its own holds its session alone, and closing it ends it.
    """

    def __init__(self, session: _Session, *, owned: bool = False) -> None:
        """Holds a session reached. Made by :meth:`Remotes.client` and :meth:`over`.

        Args:
          session: The session.
          owned: Whether closing this ends the session, which is this client's alone.
        """
        self._session = session
        self._owned = owned
        self._lock = threading.Lock()
        self._listening = False
        self._inbox: _Inbox = queue.SimpleQueue()
        self._closed = False

    @classmethod
    def over(cls, pipe: Pipe, *, name: str = "", kind: Kind = "sdk") -> Self:
        """A client of a session of its own, over a trusted pipe to a daemon: hello said.

        Args:
          pipe: The pipe: this machine's daemon's socket, or a socket pair to a private one.
          name: What this client is called, `""` for this machine's host name.
          kind: What it is: `sdk`, `cli`, `tui`.

        Raises:
          OSError: If the daemon refused hello or did not answer it -- `EADDRINUSE`, saying
            why, where it speaks another protocol.
        """
        import errno

        from hmz.reach import Route
        from hmz.rpc import Code, RpcError

        try:
            session = _Session(
                pipe, Route.parse("unix:"), "", "this daemon", client=name, kind=kind
            )
        except _Failed as why:
            cause = why.__cause__
            if isinstance(cause, RpcError) and cause.code == Code.PROTOCOL_MISMATCH:
                raise OSError(errno.EADDRINUSE, str(why)) from why
            raise OSError(str(why)) from why
        return cls(session, owned=True)

    @property
    def daemon_id(self) -> str:
        """The daemon's id, as `session.hello` answered it."""
        return str(self._session.said.get("daemon_id", ""))

    @property
    def version(self) -> str:
        """The daemon's hmz version."""
        return str(self._session.said.get("version", ""))

    @property
    def protocol(self) -> str:
        """The daemon's protocol version."""
        return str(self._session.said.get("protocol", ""))

    @property
    def capabilities(self) -> tuple[str, ...]:
        """The optional features the daemon offers."""
        return tuple(self._session.said.get("capabilities") or ())

    @property
    def device(self) -> str:
        """The name this device is paired under there, `local` over a trusted carrier."""
        return str(self._session.said.get("device", ""))

    def call(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        idem: str | None = None,
        seconds: float | None = None,
    ) -> Any:
        """Makes one call, and returns its result.

        Raises:
          Refused: With the error's message, `code` and `data` where the daemon answers one,
            and `code` 503 where the session has ended.
          TimeoutError: If no answer came within `seconds`.
        """
        from hmz.rpc import Closed, RpcError

        if self._closed or self._session.peer.closed:
            raise Refused(_WENT, code=503)
        given = dict(params or {})
        if idem is not None:
            given["idem"] = idem
        try:
            return self._session.peer.call(method, given, timeout=seconds)
        except RpcError as why:
            raise Refused(why.message, code=why.code, data=why.data) from why
        except Closed as why:
            raise Refused(_WENT, code=503) from why
        except TimeoutError:
            raise TimeoutError(f"no answer to {method!r} in {seconds}s") from None

    def heard(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        """Calls `listener(method, params)` with every notification, in order, on a thread.

        Raises:
          RuntimeError: If this client already has one.
        """
        with self._lock:
            if self._listening:
                raise RuntimeError("this client already has a listener")
            self._listening = True
        self._session.hears(self._inbox)

        def pumps() -> None:
            while (one := self._inbox.get()) is not None:
                with contextlib.suppress(Exception):
                    listener(*one)

        threading.Thread(target=pumps, daemon=True, name="hmz-client").start()

    def wait(self, timeout: float | None = None) -> bool:
        """Waits for the session to end, and says whether it has."""
        return self._session.peer.wait(timeout)

    def close(self) -> None:
        """Lets go of the session; every epic goes on."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._session.forgets(self._inbox)
        self._inbox.put(None)
        if self._owned:
            self._session.close()

    def __enter__(self) -> Self:
        """Holds the client for as long as the block runs."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Lets go of it, however the block ended."""
        self.close()


def _secured(
    route: Route,
    pinned: str,
    name: str,
    networks: Mapping[str, EasyTier],
    opened: Callable[[Pipe], None],
) -> tuple[Pipe, float]:
    """The carrier a route names, inside mutual TLS pinned to the daemon where it is untrusted.

    Args:
      route: It.
      pinned: The daemon id pinned, `""` for none.
      name: What the daemon is called, for a refusal.
      networks: This machine's EasyTier entries.
      opened: Told each carrier as it opens, for closing it however reaching it ends.

    Returns:
      It, and when, on the monotonic clock, the 30 seconds it was started with end: what
      `session.hello` over it has left (Section 3.4.9 of wire.md).

    Raises:
      ValueError, OSError: If it cannot be opened or secured, saying why.
      TimeoutError: `<route> did not open within 30 seconds.`
    """
    from hmz.reach import OPENING, dial
    from hmz.trust import identity, tls

    until = time.monotonic() + OPENING
    pipe = dial(route, daemon=pinned, easytier=networks)
    opened(pipe)
    if route.trusted:
        return pipe, until
    # Its 30 seconds include the handshake (Section 3.4.9 of wire.md).
    late = threading.Event()

    def gives_up() -> None:
        late.set()
        pipe.close()

    timer = threading.Timer(max(until - time.monotonic(), 0), gives_up)
    timer.start()
    try:
        return tls.dial(pipe, identity.device(), pinned, name), until
    except Exception as why:
        if late.is_set():
            # Closed from this side: the far one refused nothing.
            msg = f"{route} did not open within {OPENING:g} seconds."
            raise TimeoutError(msg) from why
        raise
    finally:
        timer.cancel()


class _Remote:
    """One daemon, reached and reached again on a thread of its own until it is closed."""

    def __init__(
        self,
        name: str,
        version: str,
        changed: threading.Condition,
        *,
        install: bool | None = False,
        kind: Kind = "sdk",
    ) -> None:
        self.name = name
        self._version = version
        self._kind: Kind = kind
        self._changed = changed
        #: Whether `hmz` is installed where none is found: None while nobody has said, which
        #: asks; a yes is kept for as long as this is and its routes are those the yes was
        #: said of (Section 3.8.3.8 of daemon.md), after which it is as was said beforehand.
        self._install = install
        self._beforehand = install
        self._routes: list[str] = []
        #: Set by a no, or where nobody is asked: it is not reached again by itself.
        self._declined = False
        #: What `hmz is not installed on <name>.` calls the machine.
        self._where = name
        self.state = IDLE
        self.detail = ""
        self.there = ""
        self.entry: dict[str, Any] | None = None
        self.session: _Session | None = None
        #: What is said of it while it is up: why its hmz is not this one's, where it is not.
        self._note = ""
        self._children: set[subprocess.Popen[Any]] = set()
        self._pipes: list[Pipe] = []
        self._closed = threading.Event()
        self._again = threading.Event()
        #: Set while its routes race: what a route that lost says after is said to nobody.
        self._racing = threading.Event()
        self._thread: threading.Thread | None = None

    def seen(self) -> dict[str, str]:
        return {"state": self.state, "detail": self.detail, "version": self.there}

    def starts(self, said: dict[str, Any], *, now: bool) -> None:
        """Reaches it, as `said` is its entry.

        Again at once where that has changed, or where it failed and is wanted `now` rather
        than after its wait.
        """
        if self._thread is None or not self._thread.is_alive():
            self._closed.clear()
            self._thread = threading.Thread(
                target=self._keeps, daemon=True, name=f"hmz-remote-{self.name}"
            )
            self._thread.start()
        elif (now and self.state == FAILED) or _moved(said, self.entry):
            self._again.set()

    def close(self) -> None:
        self._closed.set()
        self._again.set()
        self._ends()
        if self._thread is not None:
            self._thread.join(timeout=_STOPPING * 3)

    def answer(self, install: bool) -> None:  # noqa: FBT001 -- the answer is one
        """Answers whether to install `hmz` there, where `asking` was said; else nothing.

        A no fails the route that asked with `hmz is not installed on <name>.`
        """
        with self._changed:
            if self.state != ASKING:
                return
            if install:
                self._install = True
            else:
                self._declined = True
            self._says(CONNECTING)

    def _says(self, state: str, detail: str = "") -> None:
        with self._changed:
            self.state, self.detail = state, detail
            self._changed.notify_all()

    def _tells(self, state: str, detail: str = "") -> None:
        """Says how it stands from a route racing, where the race is not over.

        Nothing while the user is asked, which is how it stands until the answer.
        """
        with self._changed:
            if self._racing.is_set() and self.state != ASKING:
                self._says(state, detail)

    def _keeps(self) -> None:
        """Reaches it, holds it while it lasts, and reaches it again after a wait."""
        from hmz.reach import Backoff

        backoff = Backoff()
        while not self._closed.is_set():
            self._again.clear()
            self._declined = False
            self._says(CONNECTING)
            try:
                session = self._reaches()
            except Exception as why:  # noqa: BLE001 -- whatever it was is what it says
                self._ends()
                if self._closed.is_set():
                    break
                self._says(FAILED, str(why) or type(why).__name__)
                if self._declined:
                    # Not again by itself: when the user next asks to connect (3.8.3.9).
                    self._again.wait()
                    continue
            else:
                with self._changed:
                    self.session = session
                self._says(UP, self._note)
                backoff.reset()
                while not (session.peer.wait(0.25) or self._again.is_set()):
                    pass
                self._ends()
                if self._closed.is_set():
                    break
                if self._again.is_set():
                    continue
                self._says(CONNECTING, "Lost")
            self._again.wait(backoff.next())
        self._says(IDLE)

    def _reaches(self) -> _Session:
        """Races its routes, and holds the first whose daemon says hello as the one pinned.

        Pins the id it answered where none was pinned and the route that won is trusted.

        Raises:
          _Failed, ValueError, OSError: Saying what went wrong; of the last route to fail,
            where every one did.
        """
        from hmz.reach import Route, race

        self.entry = _entry(self.name)
        if self.entry is None:
            raise _Failed(f"No daemon is called {self.name}.")
        if self.entry["routes"] != self._routes:
            # A yes was to the machine its routes reached then, not to the one these do.
            self._routes, self._install = self.entry["routes"], self._beforehand
        pinned: str = self.entry["id"]
        networks = _networks()
        routed: dict[int, tuple[Route, float]] = {}
        notes: dict[Route, str] = {}

        def opening(route: Route) -> Pipe:
            if not (pinned or route.trusted):
                # Refused before anything is fetched for it, as before its carrier opens: an
                # EasyTier daemon an earlier release wrote is reached once paired.
                raise ValueError(f"{route} needs the id of the daemon it reaches.")
            if route.kind == "ssh":
                notes[route] = self._installed(route)
            elif route.kind == "easytier":
                self._downloads()
            pipe, until = _secured(route, pinned, self.name, networks, self._opened)
            routed[id(pipe)] = route, until
            return pipe

        def handshake(pipe: Pipe) -> _Session:
            route, until = routed[id(pipe)]
            return _Session(
                pipe, route, pinned, self.name, kind=self._kind, until=until
            )

        self._racing.set()
        try:
            routes = [Route.parse(one) for one in self.entry["routes"]]
            won = race(routes, opening, handshake)
        finally:
            with self._changed:
                self._racing.clear()
                self._changed.notify_all()
                children = list(self._children)
                self._children.clear()
            # What a route that lost was probing or installing with.
            for child in children:
                _stops(child)
        self._note = notes.get(won.route, "")
        if self._closed.is_set():
            won.answer.close()
            raise _Failed("Closed.")
        if not pinned and won.route.trusted:
            _pins(self.name, str(won.answer.said.get("daemon_id", "")))
            self.entry = _entry(self.name)
        self.there = str(won.answer.said.get("version", ""))
        return won.answer

    def _opened(self, pipe: Pipe) -> None:
        """Holds a carrier opened for it, closing it at once where it is closing."""
        with self._changed:
            closed = self._closed.is_set()
            if not closed:
                self._pipes.append(pipe)
        if closed:
            pipe.close()
            raise _Failed("Closed.")

    def _downloads(self) -> None:
        """Downloads EasyTier where there is none, `installing` while it does."""
        from hmz.coganchor import easytier

        try:
            easytier.binary(lambda said: self._tells(INSTALLING, said))
        except OSError as why:
            raise _Failed(str(why)) from why
        self._tells(CONNECTING)

    def _installed(self, route: Route) -> str:
        """Has the `hmz` there be this one's version, where it may be made so.

        A development build, version `0.0.0`, replaces none, and installs the latest release
        where none is. None is installed where none is before the user has said to.

        Returns:
          Why the `hmz` there is not this one's, where it is not; else "".

        Raises:
          _Failed: If there is none it can use, saying why.
        """
        try:
            on = _road(route)
        except ValueError as why:
            raise _Failed(str(why)) from why
        found = self._probed(on)
        there = found.get("hmz", "")
        pinned = self._version != "0.0.0"
        wanted = f"hmz {self._version}" if pinned else "hmz"
        named = f"hmz=={self._version}" if pinned else "hmz"
        if not there:
            self._asked()
        elif not pinned or there == self._version:
            if found.get("connect") != "yes":
                raise _Failed(
                    f"hmz {there} on {self._where} is too old to be reached: "
                    "it has no daemon command."
                )
            return ""
        elif found.get("daemon") == "running":
            return f"hmz {there} there holds running epics; {wanted} waits"
        elif found.get("daemon") != "none":
            return f"Whether hmz {there} there runs epics is unknown; not replaced"
        self._tells(INSTALLING, wanted)
        lines: list[str] = []
        script = _INSTALL.format(wanted=named, checked="" if pinned else _CHECKED)
        installing = self._started(on.line(["sh", "-c", script]))
        for line in _lines(installing, _INSTALLING):
            lines.append(line)
            if line.strip():
                self._tells(INSTALLING, line.strip())
        if installing.wait() != 0:
            raise _Failed(_last(lines, f"{wanted} could not be installed."))
        there = self._probed(on).get("hmz", "")
        if not pinned and not there:
            raise _Failed("hmz could not be installed.")
        if pinned and there != self._version:
            raise _Failed(f"{wanted} was installed, and hmz {there} answers.")
        self._tells(CONNECTING)
        return ""

    def _asked(self) -> None:
        """Returns once `hmz` may be installed there, where none is.

        At once where that was said beforehand or answered before; else the daemon is
        `asking` until it is answered (Section 3.8.3.7 of daemon.md).

        Raises:
          _Failed: `hmz is not installed on <name>.` on a no, or where nobody is asked;
            `Closed.` where it was let go of, or another route won, before an answer.
        """
        missing = f"hmz is not installed on {self._where}."
        with self._changed:
            if self._install is None and not self._declined:
                if self._racing.is_set():
                    self._says(ASKING, missing)
                self._changed.wait_for(
                    lambda: (
                        self._install
                        or self._declined
                        or self._closed.is_set()
                        or not self._racing.is_set()
                    )
                )
                if self._closed.is_set() or not self._racing.is_set():
                    raise _Failed("Closed.")
            if not self._install:
                self._declined = True
                raise _Failed(missing)

    def _probed(self, on: Road) -> dict[str, str]:
        probing = self._started(on.line(["sh", "-c", _PROBE]))
        lines = list(_lines(probing, _PROBING))
        if probing.wait() != 0 or "daemon" not in said(lines):
            raise _Failed(_last(lines, f"{self.name} did not answer."))
        return said(lines)

    def _started(self, argv: list[str]) -> subprocess.Popen[str]:
        """A process, which is stopped as this daemon is closed or lost."""
        with self._changed:
            if not self._racing.is_set():
                raise _Failed("Closed.")
            try:
                child = subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    errors="replace",
                    start_new_session=True,
                )
            except OSError as why:
                raise _Failed(f"ssh could not be run: {why}") from why
            self._children.add(child)
        return child

    def _ends(self) -> None:
        """Closes its session and every carrier, and stops and reaps every process started."""
        with self._changed:
            session, self.session = self.session, None
            pipes, self._pipes = self._pipes, []
            children = list(self._children)
            self._children.clear()
            # Whoever waits for an answer sees that it is closed.
            self._changed.notify_all()
        if session is not None:
            session.close()
        for pipe in pipes:
            with contextlib.suppress(OSError):
                pipe.close()
        for child in children:
            _stops(child)


class Dialing(_Remote):
    """One route opened for a client of its own, `hmz web`'s `/dial` (Section 4.8 of web.md).

    Opened as a remote daemon's route is -- hmz installed over `stdio:ssh`, EasyTier downloaded
    for `easytier:`, mutual TLS as this machine's device on an untrusted carrier, pinning the
    id given -- with each state told as it goes. Closing it closes the carrier and stops every
    process started for it.

    Args:
      route: The route.
      pinned: The daemon id pinned, `""` for none.
      told: Told each state, `connecting`, `asking`, `installing` or `failed`, and what was
        said last.
      version: The version of `hmz` installed where another is found; this one's by default.
    """

    def __init__(
        self,
        route: Route,
        pinned: str,
        told: Callable[[str, str], None],
        version: str | None = None,
    ) -> None:
        super().__init__(
            str(route), version or _here_version(), threading.Condition(), install=None
        )
        self._where = route.host
        self._route = route
        self._pinned = pinned
        self._told = told

    def opens(self) -> tuple[Pipe, str]:
        """Opens the carrier, secured where it is untrusted.

        Returns:
          It, and why the `hmz` there is not this one's, where it is not; else "".

        Raises:
          Exception: Whatever went wrong, saying it.
        """
        self._racing.set()
        try:
            self._says(CONNECTING)
            note = ""
            if self._route.kind == "ssh":
                note = self._installed(self._route)
            elif self._route.kind == "easytier":
                self._downloads()
            pipe, _ = _secured(
                self._route, self._pinned, self.name, _networks(), self._opened
            )
        except BaseException:
            self._ends()
            raise
        finally:
            with self._changed:
                self._racing.clear()
                self._changed.notify_all()
                children = list(self._children)
                self._children.clear()
            # What probed or installed: the carrier is what is kept.
            for child in children:
                _stops(child)
        return pipe, note

    def close(self) -> None:
        """Closes the carrier and stops every process started for it, opening or open."""
        self._closed.set()
        self._ends()

    def _says(self, state: str, detail: str = "") -> None:
        super()._says(state, detail)
        self._told(state, detail)


def _moved(said: dict[str, Any], entry: dict[str, Any] | None) -> bool:
    """Whether a daemon's entry says to reach it otherwise than as it was reached.

    Never where it has only had the id it was reached at pinned since.
    """
    return (
        entry is None
        or said["routes"] != entry["routes"]
        or said["id"] not in ("", entry["id"])
    )


def _lines(child: subprocess.Popen[str], patience: float) -> Iterator[str]:
    """Each line a process says, until it ends or has taken longer than `patience`."""
    assert child.stdout is not None  # noqa: S101 -- it was started with one
    timer = threading.Timer(patience, child.kill)
    timer.start()
    try:
        with child.stdout:
            yield from (line.rstrip("\n") for line in child.stdout)
    finally:
        timer.cancel()


def _stops(child: subprocess.Popen[Any]) -> None:
    """Stops a process and reaps it: its standard input closed, then terminated, then killed."""
    if child.stdin is not None:
        with contextlib.suppress(OSError):
            child.stdin.close()
        with contextlib.suppress(subprocess.TimeoutExpired):
            child.wait(timeout=1.0)
    if child.poll() is None:
        with contextlib.suppress(OSError):
            child.terminate()
        try:
            child.wait(timeout=_STOPPING)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


class Remotes:
    """Every daemon on another machine, as each is reached.

    Args:
      version: The version of `hmz` installed where another is found; this one's by default.
      install: What is done where no `hmz` is found over `stdio:ssh`: `False` installs
        nothing, as nobody is there to ask; `True` installs unasked; `None` has the daemon
        `asking` until :meth:`answer` answers it.
      kind: What whoever reaches them is: `sdk`, `cli`, `tui`, as `session.hello` says it
        of every session these open.
    """

    def __init__(
        self,
        version: str | None = None,
        *,
        install: bool | None = False,
        kind: Kind = "sdk",
    ) -> None:
        self._version = version or _here_version()
        self._install = install
        self._kind: Kind = kind
        self._changed = threading.Condition()
        self._held: dict[str, _Remote] = {}
        self._closed = False

    def state(self, name: str) -> dict[str, str]:
        """How a daemon stands: `{state, detail, version}`.

        Its state is `idle` where it has not been asked for, then `connecting`, `asking`,
        `installing`, `up` or `failed`; Local's is `up` at this version.
        """
        if name == LOCAL:
            return {"state": UP, "detail": "", "version": _here_version()}
        with self._changed:
            held = self._held.get(name)
            return held.seen() if held else {"state": IDLE, "detail": "", "version": ""}

    def connect(self, name: str) -> dict[str, str]:
        """Starts reaching a daemon, or reaches it again at once where it failed.

        Returns:
          How it stands.

        Raises:
          LookupError: If no daemon is written down by that name.
          Unreached: If these are closing.
        """
        self._starts(name, now=True)
        return self.state(name)

    def answer(
        self,
        name: str,
        install: bool,  # noqa: FBT001 -- as Section 4.14 of python.md has it
    ) -> dict[str, str]:
        """Answers a daemon that is `asking` whether to install `hmz` on its machine.

        A yes is kept for as long as these are; a no fails it with `hmz is not installed on
        <name>.` until :meth:`connect` reaches it again. Nothing to one that is not asking.

        Returns:
          How it stands.
        """
        with self._changed:
            held = self._held.get(name)
        if held is not None:
            held.answer(install)
        return self.state(name)

    def client[Made: Client](self, name: str, made: type[Made] = Client) -> Made:
        """The client of the session to a daemon, reached first where it was not.

        Never waited for where it is `asking`.

        Args:
          name: What the daemon is written down as.
          made: The class the client is made as, for a caller whose clients do more than
            this module's: the SDK's, which has the families.

        Raises:
          Unreached: If it cannot be reached, with its state.
          LookupError: If none is called that.
        """
        held = self._up(name)
        with self._changed:
            session = held.session
        if session is None or session.peer.closed:
            raise Unreached(f"{name} is not reached yet.", held.seen())
        return made(session)

    def pair(
        self, name: str, code: str, *, device: str | None = None
    ) -> dict[str, Any]:
        """Claims a pairing code over its routes, and writes the daemon down under `name`.

        Args:
          name: What the daemon is to be called here.
          code: The pairing code, `hmz-pair:...`.
          device: What this device is to be called there; this machine's host name by default.

        Returns:
          The daemon, as it is written.

        Raises:
          ValueError: For a code that is not one, or a name that cannot be one.
          Unreached: If the claim is refused, with its error code, or no route opens, 503.
          OSError: If the daemon cannot be written down.
        """
        from hmz.reach import Route, race
        from hmz.rpc import Closed, RpcError
        from hmz.trust import identity, pairing

        given = pairing.read(code)
        entry = _checked(name, {"id": given.id, "routes": list(given.routes)})
        routes = [Route.parse(one) for one in given.routes]
        with self._changed:
            if self._closed:
                raise Unreached("Reaching daemons is stopping.")
        networks = _networks()
        routed: dict[int, tuple[Route, float]] = {}

        def opening(route: Route) -> Pipe:
            pipe, until = _secured(route, given.id, name, networks, lambda _: None)
            routed[id(pipe)] = route, until
            return pipe

        def handshake(pipe: Pipe) -> _Session:
            route, until = routed[id(pipe)]
            session = _Session(pipe, route, given.id, name, until=until)
            try:
                session.peer.call(
                    "pair.claim",
                    {"token": given.token, "name": device or identity.host()},
                    timeout=_ASKING,
                )
            except BaseException:
                session.close()
                raise
            return session

        try:
            won = race(routes, opening, handshake)
        except RpcError as why:
            raise Unreached(why.message, status=why.code) from why
        except (_Failed, Closed, OSError, ValueError) as why:
            raise Unreached(str(why) or type(why).__name__) from why
        won.answer.close()
        return Daemons().write(
            name, {"id": entry["id"], "routes": entry["routes"]}, replace=True
        )

    def close(self) -> None:
        """Stops reaching every daemon: every session closed, every process stopped and reaped."""
        with self._changed:
            self._closed = True
            held = list(self._held.values())
        stopping = [threading.Thread(target=one.close) for one in held]
        for one in stopping:
            one.start()
        for one in stopping:
            one.join()

    def _starts(self, name: str, *, now: bool) -> _Remote:
        """A daemon, being reached: again where what reaches it has changed.

        Raises:
          LookupError: If none is written down by that name -- one that was is let go of.
          Unreached: If these are closing.
        """
        said = _entry(name)
        with self._changed:
            if self._closed:
                raise Unreached("Reaching daemons is stopping.")
            if said is None:
                gone = self._held.pop(name, None)
                if gone is not None:
                    threading.Thread(target=gone.close, daemon=True).start()
                raise LookupError("There is no daemon by that name.")
            held = self._held.setdefault(
                name,
                _Remote(
                    name,
                    self._version,
                    self._changed,
                    install=self._install,
                    kind=self._kind,
                ),
            )
        held.starts(said, now=now)
        return held

    def _up(self, name: str) -> _Remote:
        """A daemon once it is up, waiting a while for one being reached.

        Raises:
          Unreached: If it is not up, with its state.
          LookupError: If none is called that.
        """
        held = self._starts(name, now=False)
        with self._changed:
            # Not past a failure, which is reached again after its wait rather than at once.
            self._changed.wait_for(
                lambda: held.state in (UP, FAILED, ASKING, INSTALLING),
                timeout=_WAITING,
            )
            if held.state == UP:
                return held
            raise Unreached(held.detail or f"{name} is not reached yet.", held.seen())
