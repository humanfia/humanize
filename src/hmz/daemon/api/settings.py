"""`settings.*`: what Humanize remembers, read and changed by any client of the daemon.

The same settings the terminal interface's `/settings` reads and writes, through the same
object: what a workspace was last set up to run, which agent a side question goes to,
whether a turn's working is shown, whether Humanize reports its own failures, the git
repositories epics are backed up to, the listeners the daemon opens and the STUN and TURN
servers it answers WebRTC through (Section 4.18.1 of the daemon protocol). Nothing signed in
comes out: a backup URL is shown with its credentials struck, and one sent back as it was
shown is kept as it is written; a TURN server's credential is shown as `true`, and one sent
back as `true` is kept the same way.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.reach.routes import Route
    from hmz.rpc import Call, Handler

__all__ = ["METHODS", "forget", "listening", "read", "write"]

#: The schemes a STUN or TURN server's URL is written with (Section 3.4.9 of the files).
_ICE = ("stun:", "turn:", "turns:")

#: The kinds of route a listener may be (Section 3.9.2 of the daemon protocol).
_LISTENERS = frozenset({"tcp", "ws", "relay", "webrtc", "easytier"})


def read(hmz: Any) -> dict[str, Any]:
    """What a client is shown of Humanize's own settings and of one workspace's.

    Args:
      hmz: Humanize, for the workspace.

    Returns:
      `workspace`, `flow`, `chat` (the chat agent remembered there, or ""), `prefer`, `ai_chan`,
      `details`, `harness_sessions`, `reports`, `flows`, `backup`, `listen` and
      `ice_servers`, with nothing signed in.
    """
    from hmz.coganchor import settings as kept
    from hmz.runtime.kept import written

    settings, held = hmz.settings, kept.read()
    chat = settings.chat_agent
    return {
        "workspace": str(hmz.workspace),
        "flow": settings.flow,
        "chat": written(chat) if chat is not None else "",
        "prefer": settings.chat_prefer,
        "ai_chan": settings.ai_chan,
        "details": settings.details,
        "harness_sessions": settings.harness_sessions,
        "reports": settings.enable_sentry,
        "flows": sorted(settings.flows()),
        "backup": {
            "targets": [
                {
                    "name": one.name,
                    "url": hmz.verses.plain(one.url),
                    "branch": one.branch,
                    "policies": list(one.policies),
                    "every": one.every,
                }
                for one in hmz.backups.targets()
            ],
            "defaults": list(hmz.backups.defaults()),
        },
        "listen": listening(held),
        "ice_servers": [
            one | {"credential": True}
            if isinstance(one.get("credential"), str)
            else one
            for one in _ice_servers(held)
        ],
    }


def write(hmz: Any, said: Mapping[str, Any]) -> dict[str, Any]:
    """Writes what a client sent of the settings, all of it or, where any is refused, none.

    Args:
      hmz: Humanize, for the workspace.
      said: Any of `chat`, `prefer`, `details`, `harness_sessions`, `reports`, `backup`,
        `listen` and `ice_servers`; anything else is not read.

    Returns:
      What :func:`read` answers afterwards.

    Raises:
      RpcError: 400 for a value of another type, a chat agent or a listener that is not
        one, a backup target that is not one, or a credential still struck.
    """
    from hmz.coganchor import settings as kept
    from hmz.runtime.doing.hosting import assistant

    # All of it read before any of it is written: a request refused changes nothing.
    chat = None
    if "chat" in said:
        try:
            chat = assistant(str(said["chat"] or ""))
        except ValueError as why:
            raise _refused(f"chat is an agent as -a spells one: {why}") from why
    if "prefer" in said and said["prefer"] not in ("native", "flow"):
        raise _refused("prefer is native or flow.")
    if "details" in said and not isinstance(said["details"], bool):
        raise _refused("details is true or false.")
    if "harness_sessions" in said and not isinstance(said["harness_sessions"], bool):
        raise _refused("harness_sessions is true or false.")
    if "reports" in said and not isinstance(said["reports"], bool):
        raise _refused("reports is true or false.")
    held = kept.read()
    machine: dict[str, Any] = {}
    if "listen" in said:
        machine["listen"] = _listen(said["listen"], held)
    if "ice_servers" in said:
        machine["ice_servers"] = _ice(said["ice_servers"], _ice_servers(held))
    # First of what is written, as it is refused without writing anything.
    if "backup" in said:
        _back_up_to(hmz, said["backup"])
    if machine:
        kept.changes(lambda now: now.update(machine))
    if chat is not None:
        hmz.settings.chat_agent = chat
    if "prefer" in said:
        hmz.settings.chat_prefer = said["prefer"]
    if "details" in said:
        hmz.settings.detailing(on=said["details"])
    if "harness_sessions" in said:
        hmz.settings.harness_sessions = said["harness_sessions"]
    if "reports" in said:
        hmz.settings.answers(enable_sentry=said["reports"])
    return read(hmz)


def forget(hmz: Any) -> dict[str, Any]:
    """Forgets what one workspace was set up with.

    Returns:
      `forgot`, whether there was anything, beside what :func:`read` answers.
    """
    return {"forgot": hmz.settings.forget()} | read(hmz)


def listening(held: Mapping[str, Any]) -> list[str]:
    """The listeners one reading of the settings file names, as it names them.

    Args:
      held: The file, as `hmz.coganchor.settings.read` reads it.
    """
    said: object = held.get("listen")
    if not isinstance(said, list):
        return []
    return [one for one in cast("list[object]", said) if isinstance(one, str)]


def _back_up_to(hmz: Any, said: object) -> None:
    """Writes down every backup target and the defaults, or nothing where one is not one."""
    if not isinstance(said, dict):
        raise _refused("backup is an object of targets and defaults.")
    backup = cast("dict[str, Any]", said)
    targets: object = backup.get("targets", [])
    defaults: object = backup.get("defaults", [])
    if not isinstance(targets, list) or not all(
        isinstance(one, dict) for one in cast("list[Any]", targets)
    ):
        raise _refused("backup's targets are a list of objects.")
    if not isinstance(defaults, list):
        raise _refused("backup's defaults are a list of target names.")
    # A URL sent back as it was shown, struck of what was signed into it, is the one written.
    written = {one.name: one.url for one in hmz.backups.targets()}
    kept: list[dict[str, Any]] = []
    for one in cast("list[dict[str, Any]]", targets):
        url = written.get(str(one.get("name")))
        if url is not None and one.get("url") == hmz.verses.plain(url):
            kept.append(one | {"url": url})
        elif "***@" in str(one.get("url")):
            raise _refused(f"Type {one.get('name')}'s URL whole, signed in again.")
        else:
            kept.append(one)
    try:
        hmz.settings.back_up_to(kept, [str(one) for one in cast("list[Any]", defaults)])
    except ValueError as why:
        raise _refused(f"{str(why)[:1].upper()}{str(why)[1:]}.") from why


def _listen(said: object, held: Mapping[str, Any]) -> list[str]:
    """The listeners sent, each a listener spec, the EasyTier entry it names written down."""
    from hmz.reach.routes import Route

    if not isinstance(said, list):
        raise _refused("listen is a list of listener specs.")
    specs = cast("list[object]", said)
    entries: object = held.get("easytier")
    for one in specs:
        try:
            route = Route.parse(_any_port(one)) if isinstance(one, str) else None
        except ValueError:
            route = None
        if route is None or not _listener(route):
            raise _refused(f"{one} is not a listener.")
        if route.kind == "easytier" and not (
            isinstance(entries, dict) and route.name in entries
        ):
            raise _refused(f"There is no EasyTier entry {route.name}.")
    return cast("list[str]", specs)


def _any_port(spec: str) -> str:
    """A listener spec read as the route it otherwise is, its port `0` read as any port.

    A route names a port from 1 to 65535 (Section 3.3.4 of [WIRE]), but a listener spec may
    name `0` for any free port (Section 3.9.2 of [DAEMON]); in the one place the two differ,
    the spec is checked as the route it becomes once a port is taken.
    """
    scheme, _, rest = spec.partition("://")
    if scheme not in {"tcp", "ws"}:
        return spec
    address, slash, path = rest.partition("/")
    host, colon, port = address.rpartition(":")
    if colon and port == "0":
        return f"{scheme}://{host}:1{slash}{path}"
    return spec


def _listener(route: Route) -> bool:
    """Whether a route is one a daemon listens on: a `tcp` or `ws` one naming its port."""
    from urllib.parse import urlsplit

    if route.kind not in _LISTENERS:
        return False
    if route.kind == "tcp":
        return route.port is not None
    if route.kind == "ws":
        parts = urlsplit(route.url)
        try:
            port = parts.port
        except ValueError:
            return False
        return parts.scheme == "ws" and not parts.path and port is not None
    return True


def _ice_servers(held: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The STUN and TURN servers one reading of the settings file names, credentials and all."""
    said: object = held.get("ice_servers")
    if not isinstance(said, list):
        return []
    return [
        dict(cast("dict[str, Any]", one))
        for one in cast("list[object]", said)
        if isinstance(one, dict)
    ]


def _ice(said: object, written: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The STUN and TURN servers sent, each credential sent back as `true` the one written."""
    wrong = "ice_servers is a list of {urls, username, credential}."
    if not isinstance(said, list):
        raise _refused(wrong)
    servers: list[dict[str, Any]] = []
    for raw in cast("list[object]", said):
        if not isinstance(raw, dict):
            raise _refused(wrong)
        one = cast("dict[str, Any]", raw)
        urls: object = one.get("urls")
        listed = cast("list[object]", urls) if isinstance(urls, list) else [urls]
        if (
            set(one) - {"urls", "username", "credential"}
            or not listed
            or not all(isinstance(u, str) and u.startswith(_ICE) for u in listed)
            or not isinstance(one.get("username", ""), str)
            or not isinstance(one.get("credential", ""), str | bool)
            or one.get("credential") is False
        ):
            raise _refused(wrong)
        if one.get("credential") is True:
            kept = next(
                (
                    each["credential"]
                    for each in written
                    if (each.get("urls"), each.get("username"))
                    == (urls, one.get("username"))
                    and isinstance(each.get("credential"), str)
                ),
                None,
            )
            if kept is None:
                raise _refused(f"Type the credential of {urls} whole.")
            one = one | {"credential": kept}
        servers.append(dict(one))
    return servers


def _refused(message: str) -> RpcError:
    return RpcError(Code.REFUSED, message)


def _hmz(call: Call, *, made: bool) -> Any:
    """Humanize, for the workspace a call names (Section 4.5.2 of the daemon protocol).

    Args:
      call: The call, which names it or, where it may, leaves it to the user's home.
      made: Whether a directory that is not there may still be named.

    Raises:
      RpcError: 400 for a path that is not whole, and 404 for no directory where there must be
        one.
    """
    from hmz.runtime import Hmz

    said = str(call.params.get("workspace", "~"))
    at = Path(said).expanduser()
    if not at.is_absolute():
        raise _refused(f"Say the workspace as a whole path, not {said}.")
    if not made and not at.is_dir():
        raise RpcError(Code.NOT_FOUND, f"There is no directory {at}.")
    return Hmz(at.resolve())


#: Every method of `settings.*`, by name.
METHODS: Mapping[str, Handler] = {
    "settings.get": lambda call: read(_hmz(call, made=True)),
    "settings.set": lambda call: write(_hmz(call, made=False), call.params),
    "settings.forget": lambda call: forget(_hmz(call, made=True)),
}
