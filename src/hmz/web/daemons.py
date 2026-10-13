"""The daemons a page may switch between: this machine's, and each ssh host written down.

What they are, how they are written down and how each is checked is the runtime's
(`Hmz.daemons`), which the terminal interface switches between as well; this is that, as a
page asks for it. How each stands is the remote reach's to say, where this site has one;
without one, Local is up and every other daemon is idle.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from .routing import Refusal, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["LOCAL", "ROUTES", "found", "listed", "saved"]

#: The daemon of this machine, which is always there and never written down.
LOCAL = "local"

#: What a write of one takes.
_TAKES = frozenset({"name", "fields", "replace"})


def _daemons() -> Any:
    """The daemons written down, as the runtime keeps them."""
    from hmz.daemon import Hmz

    return Hmz().daemons


def saved() -> list[dict[str, Any]]:
    """Every ssh daemon written down, in order; one that cannot be one is left out."""
    return _daemons().all()


def found(name: str) -> dict[str, Any] | None:
    """The ssh daemon written down under a name, or None where there is none."""
    return _daemons().find(name)


def listed(site: Any) -> dict[str, Any]:
    """Local, then every ssh daemon, each with how it stands."""
    from hmz.coganchor import __version__

    remotes = getattr(site, "remotes", None)
    local: dict[str, Any] = {
        "name": LOCAL,
        "host": "",
        "user": "",
        "port": 0,
        "identity_file": "",
        "proxy_jump": "",
        "options": [],
        "alias": "",
        "config": "",
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


def _write(asked: Asked) -> dict[str, Any]:
    if extra := sorted(set(asked.body) - _TAKES):
        raise Refusal(f"A daemon is written with no {', '.join(extra)}.")
    name = asked.text("name")
    replacing = asked.body.get("replace", False)
    if not isinstance(replacing, bool):
        raise Refusal("Say replace as true or false.")
    try:
        _daemons().write(name, asked.named("fields"), replace=replacing)
    except FileExistsError as why:
        raise Refusal(str(why), 409) from why
    except ValueError as why:
        raise Refusal(str(why)) from why
    except OSError as why:
        raise Refusal(f"The daemons could not be written: {why}", 500) from why
    return listed(asked.site)


def _remove(asked: Asked) -> dict[str, Any]:
    if extra := sorted(set(asked.body) - {"name"}):
        raise Refusal(f"A daemon is removed with no {', '.join(extra)}.")
    try:
        _daemons().remove(asked.text("name"))
    except ValueError as why:
        raise Refusal(str(why)) from why
    except LookupError as why:
        raise Refusal(str(why), 404) from why
    except OSError as why:
        raise Refusal(f"The daemons could not be written: {why}", 500) from why
    return listed(asked.site)


def _hosts(_asked: Asked) -> dict[str, Any]:
    from hmz.coganchor.machines import sshconfig

    try:
        return {
            "hosts": [
                dataclasses.asdict(sshconfig.resolve(alias)) | {"name": one["name"]}
                for alias, one in _daemons().offered().items()
            ]
        }
    except OSError as why:
        raise Refusal(f"The ssh config could not be read: {why}", 503) from why


def _imports(asked: Asked) -> dict[str, Any]:
    if extra := sorted(set(asked.body) - {"aliases"}):
        raise Refusal(f"An import takes no {', '.join(extra)}.")
    try:
        added = _daemons().imported(asked.texts("aliases"))
    except ValueError as why:
        raise Refusal(str(why)) from why
    except LookupError as why:
        raise Refusal(str(why), 404) from why
    except OSError as why:
        raise Refusal(f"The daemons could not be written: {why}", 500) from why
    return listed(asked.site) | {"added": added}


#: What a page reads of the daemons, and does to them.
ROUTES = routes(
    ("GET", "/api/daemons", lambda asked: listed(asked.site)),
    ("POST", "/api/daemons", _write),
    ("POST", "/api/daemons/remove", _remove),
    ("GET", "/api/daemons/hosts", _hosts),
    ("POST", "/api/daemons/import", _imports),
)
