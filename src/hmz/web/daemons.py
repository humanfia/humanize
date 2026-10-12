"""The daemons a page may switch between: this machine's, and each ssh host written down.

`Local` is always there and never written down. Every other daemon is an ssh host, kept in
humanize's one settings file under `daemons` with what `ssh` is told to reach it -- the same
fields an ssh runtime has, checked as one is, but for its workdir and fallback -- typed in a
part at a time or brought in from the ssh config. How each stands is the remote reach's to
say, where this site has one; without one, Local is up and every other daemon is idle.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

from .routing import Refusal, routes

if TYPE_CHECKING:
    from collections.abc import Callable

    from .routing import Asked

__all__ = ["LOCAL", "ROUTES", "found", "listed", "saved"]

#: The daemon of this machine, which is always there and never written down.
LOCAL = "local"

#: The key of the settings file the daemons are kept under.
_KEY = "daemons"

#: What a daemon's name is spelled with: never starting with a dot, so never `.` or `..`.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: What a daemon holds beside its name, as `ssh` is told it.
_FIELDS = (
    "host",
    "user",
    "port",
    "identity_file",
    "proxy_jump",
    "options",
    "alias",
    "config",
)

#: What a write of one takes.
_TAKES = frozenset({"name", "fields", "replace"})


def _checked(name: str, fields: dict[str, Any]) -> dict[str, Any]:
    """One daemon as it is written down, checked as an ssh runtime is.

    Args:
      name: What it is called.
      fields: The rest of it, `options` as `[[KEYWORD, VALUE], ...]` or by keyword.

    Returns:
      It, `options` as pairs.

    Raises:
      ValueError: If it cannot be one.
    """
    from hmz.coganchor.machines.store import SSH, SSHRuntime, new

    if not _NAMED.fullmatch(name) or name.lower() == LOCAL:
        raise ValueError(
            f"A daemon cannot be called {name!r}: say a letter or digit, then letters, "
            f"digits, dots, dashes and underscores, and not {LOCAL}."
        )
    if extra := sorted(set(fields) - set(_FIELDS)):
        raise ValueError(f"A daemon takes no {', '.join(extra)}.")
    given = dict(fields)
    options: object = given.get("options", [])
    if isinstance(options, list):
        pairs = cast("list[object]", options)
        if not all(
            isinstance(one, list) and len(cast("list[object]", one)) == 2  # noqa: PLR2004
            for one in pairs
        ):
            raise ValueError("Say options as pairs of a keyword and its value.")
        given["options"] = {
            str(key): str(value) for key, value in cast("list[list[object]]", pairs)
        }
    one = cast("SSHRuntime", new(SSH, name, **given))
    return {
        "name": one.name,
        **{field: getattr(one, field) for field in _FIELDS if field != "options"},
        "options": [[key, value] for key, value in one.options.items()],
    }


def _valid(held: dict[str, Any]) -> list[dict[str, Any]]:
    """Every ssh daemon a reading of the settings file holds, in order, each checked.

    One that cannot be one -- written wrong by hand, or under a name taken before it -- is
    left out, and so is gone the next time the daemons are written.
    """
    there: object = held.get(_KEY)
    kept: list[dict[str, Any]] = []
    for one in cast("list[object]", there) if isinstance(there, list) else []:
        fields = dict(cast("dict[str, Any]", one)) if isinstance(one, dict) else {}
        name = fields.pop("name", None)
        if not isinstance(name, str):
            continue
        try:
            entry = _checked(name, fields)
        except ValueError:
            continue
        if all(entry["name"] != each["name"] for each in kept):
            kept.append(entry)
    return kept


def saved() -> list[dict[str, Any]]:
    """Every ssh daemon written down, in order; one that cannot be one is left out."""
    from hmz.coganchor import settings

    return _valid(settings.read())


def found(name: str) -> dict[str, Any] | None:
    """The ssh daemon written down under a name, or None where there is none."""
    return next((one for one in saved() if one["name"] == name), None)


def listed(site: Any) -> dict[str, Any]:
    """Local, then every ssh daemon, each with how it stands."""
    from hmz.coganchor import __version__

    remotes = getattr(site, "remotes", None)
    local: dict[str, Any] = {
        "name": LOCAL,
        **dict.fromkeys(_FIELDS, ""),
        "port": 0,
        "options": [],
        "label": "Local",
        "state": "up",
        "detail": "",
        "version": __version__,
    }
    daemons = [local]
    for one in saved():
        stands = (
            dict(remotes.state(one["name"]))
            if remotes is not None
            else {"state": "idle", "detail": "", "version": ""}
        )
        daemons.append(one | {"label": one["name"]} | stands)
    return {"daemons": daemons}


def _changes(change: Callable[[list[dict[str, Any]]], None]) -> None:
    """Makes one change to the daemons written down, and to nothing else in the file.

    Raises:
      Refusal: If the file cannot be written.
    """
    from hmz.coganchor import settings

    def changing(held: dict[str, Any]) -> None:
        daemons = _valid(held)
        change(daemons)
        held[_KEY] = daemons

    try:
        settings.changes(changing)
    except OSError as why:
        raise Refusal(f"The daemons could not be written: {why}", 500) from why


def _write(asked: Asked) -> dict[str, Any]:
    if extra := sorted(set(asked.body) - _TAKES):
        raise Refusal(f"A daemon is written with no {', '.join(extra)}.")
    name = asked.text("name")
    replacing = asked.body.get("replace", False)
    if not isinstance(replacing, bool):
        raise Refusal("Say replace as true or false.")
    try:
        entry = _checked(name, asked.named("fields"))
    except ValueError as why:
        raise Refusal(str(why)) from why

    def change(daemons: list[dict[str, Any]]) -> None:
        at = next((i for i, one in enumerate(daemons) if one.get("name") == name), -1)
        if at < 0:
            daemons.append(entry)
        elif replacing:
            daemons[at] = entry
        else:
            raise Refusal(f"There is a daemon called {name} already.", 409)

    _changes(change)
    return listed(asked.site)


def _remove(asked: Asked) -> dict[str, Any]:
    if extra := sorted(set(asked.body) - {"name"}):
        raise Refusal(f"A daemon is removed with no {', '.join(extra)}.")
    name = asked.text("name")
    if name.lower() == LOCAL:
        raise Refusal("Local is always there, and cannot be removed.")

    def change(daemons: list[dict[str, Any]]) -> None:
        kept = [one for one in daemons if one.get("name") != name]
        if len(kept) == len(daemons):
            raise Refusal(f"There is no daemon called {name}.", 404)
        daemons[:] = kept

    _changes(change)
    return listed(asked.site)


def _named(alias: str) -> str:
    """What a host of the ssh config is called as a daemon: anything no name holds a dash."""
    return re.sub(r"[^A-Za-z0-9._-]", "-", alias).lstrip("._-")


def _offered(aliases: list[str]) -> dict[str, dict[str, Any]]:
    """Each alias that can be brought in as a daemon not written down yet, as it would be.

    Of two aliases that would be called the same, the first is offered.
    """
    daemons = saved()
    names = {one["name"] for one in daemons}
    taken = {one["alias"] for one in daemons}
    offered: dict[str, dict[str, Any]] = {}
    for alias in aliases:
        if alias in taken:
            continue
        try:
            one = _checked(_named(alias), {"alias": alias})
        except ValueError:
            continue
        if one["name"] not in names:
            names.add(one["name"])
            offered[alias] = one
    return offered


def _hosts(_asked: Asked) -> dict[str, Any]:
    import dataclasses

    from hmz.coganchor.machines import sshconfig

    try:
        return {
            "hosts": [
                dataclasses.asdict(sshconfig.resolve(alias)) | {"name": one["name"]}
                for alias, one in _offered(sshconfig.aliases()).items()
            ]
        }
    except OSError as why:
        raise Refusal(f"The ssh config could not be read: {why}", 503) from why


def _imports(asked: Asked) -> dict[str, Any]:
    from hmz.coganchor.machines import sshconfig

    if extra := sorted(set(asked.body) - {"aliases"}):
        raise Refusal(f"An import takes no {', '.join(extra)}.")
    wanted = asked.texts("aliases")
    if not wanted:
        raise Refusal("Say aliases as the hosts to bring in, by their Host.")
    there = sshconfig.aliases()
    if missing := [one for one in wanted if one not in there]:
        raise Refusal(f"Your ssh config has no host {', '.join(missing)}.", 404)
    for alias in wanted:
        try:
            _checked(_named(alias), {"alias": alias})
        except ValueError as why:
            raise Refusal(f"{alias} cannot be a daemon: {why}") from why
    added: list[str] = []

    def change(daemons: list[dict[str, Any]]) -> None:
        names = {one["name"] for one in daemons}
        taken = {one["alias"] for one in daemons}
        for alias in dict.fromkeys(wanted):
            one = _checked(_named(alias), {"alias": alias})
            if alias not in taken and one["name"] not in names:
                daemons.append(one)
                names.add(one["name"])
                added.append(one["name"])

    _changes(change)
    return listed(asked.site) | {"added": added}


#: What a page reads of the daemons, and does to them.
ROUTES = routes(
    ("GET", "/api/daemons", lambda asked: listed(asked.site)),
    ("POST", "/api/daemons", _write),
    ("POST", "/api/daemons/remove", _remove),
    ("GET", "/api/daemons/hosts", _hosts),
    ("POST", "/api/daemons/import", _imports),
)
