"""The runtimes -- the machines a flow's environments may be put on: listed, written, asked.

An ssh host, a docker daemon, a docker swarm or this Mac's Apple containers, written down
under a name an `-e` names. The runtimes page `/settings` opens in the terminal interface,
through the same object and into the same store: what a page writes is a runtime the next
run offers, and what a check says is what a run reaching it would find.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, cast

from .routing import Refusal, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "listed"]

#: What a runtime is written down with that is not its own to say: what it is, what it is
#: called, and how it came to be written down.
_OWN = ("backend", "name", "made")


def listed(hmz: Any) -> dict[str, Any]:
    """Every runtime as it is written down, and what a new one of each backend is made of."""
    return {
        "runtimes": [one.held() for one in hmz.runtimes.all()],
        "blanks": _blanks(),
    }


def _blanks() -> dict[str, dict[str, Any]]:
    """Each backend's fields, by name, as a runtime of it holds them with nothing said."""
    from hmz.coganchor.machines.store import (
        AppleContainerRuntime,
        DockerRuntime,
        SSHRuntime,
        SwarmRuntime,
    )

    blanks: dict[str, dict[str, Any]] = {}
    for kind in (SSHRuntime, DockerRuntime, SwarmRuntime, AppleContainerRuntime):
        held: dict[str, Any] = {}
        for one in dataclasses.fields(kind):
            if one.name in _OWN:
                continue
            value: object = ""
            if one.default is not dataclasses.MISSING:
                value = one.default
            elif one.default_factory is not dataclasses.MISSING:
                value = one.default_factory()
            held[one.name] = (
                list(cast("tuple[object, ...]", value))
                if isinstance(value, tuple)
                else value
            )
        blanks[kind.backend] = held
    return blanks


def _found(asked: Asked) -> Any:
    hmz = asked.site.hmz
    backend, name = asked.text("backend"), asked.text("name")
    try:
        one = hmz.runtimes.find(backend, name)
    except ValueError as why:
        raise Refusal(str(why)) from why
    if one is None:
        raise Refusal(f"There is no {backend} runtime called {name}.", 404)
    return one


def _write(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    backend, name = asked.text("backend"), asked.text("name")
    fields = asked.named("fields")
    replacing = asked.body.get("replace") is True
    try:
        made = hmz.runtimes.new(backend, name, **fields)
        if replacing:
            hmz.runtimes.write(made)
        else:
            hmz.runtimes.add(made)
    except ValueError as why:
        raise Refusal(str(why)) from why
    except OSError as why:
        raise Refusal(f"{name} could not be written: {why}", 500) from why
    return listed(hmz)


def _remove(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    one = _found(asked)
    hmz.runtimes.remove(one.backend, one.name)
    return listed(hmz)


def _check(asked: Asked) -> dict[str, Any]:
    said = asked.site.hmz.runtimes.check(_found(asked))
    return dataclasses.asdict(said)


def _hosts(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    try:
        hosts = hmz.runtimes.hosts()
    except OSError as why:
        raise Refusal(f"The ssh config could not be read: {why}", 503) from why
    saved = {one.name for one in hmz.runtimes.all("ssh")}
    return {
        "hosts": [
            dataclasses.asdict(one) | {"saved": one.alias in saved} for one in hosts
        ]
    }


def _imports(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    names = asked.texts("names")
    if not names:
        raise Refusal("Say names as the hosts to bring in, by their Host.")
    try:
        hmz.runtimes.import_ssh(names=names, update=asked.body.get("update") is True)
    except ValueError as why:
        raise Refusal(str(why)) from why
    except OSError as why:
        raise Refusal(f"They could not be written: {why}", 500) from why
    return listed(hmz)


#: What a page reads of the runtimes, and does to them.
ROUTES = routes(
    ("GET", "/api/runtimes", lambda asked: listed(asked.site.hmz)),
    ("POST", "/api/runtimes", _write),
    ("POST", "/api/runtimes/remove", _remove),
    ("POST", "/api/runtimes/check", _check),
    ("GET", "/api/runtimes/hosts", _hosts),
    ("POST", "/api/runtimes/import", _imports),
)
