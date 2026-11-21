"""`runtimes.*`: the machines a flow's environments may be put on, listed, written, asked.

An ssh host, a docker daemon, a docker swarm, this Mac's Apple containers or the Slurm
cluster this machine submits to, written down under a name an `-e` names (Section 4.18.4 of
the daemon protocol). The runtimes page `/settings` opens in the terminal interface, through
the same object and into the same store: what a client writes is a runtime the next run
offers, and what a check says is what a run reaching it would find.
"""

from __future__ import annotations

import dataclasses
import os
import platform
import socket
from typing import TYPE_CHECKING, Any, cast

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hmz.rpc import Handler

__all__ = ["METHODS", "check", "hosts", "imports", "listed", "remove", "write"]

#: What a runtime is written down with that is not its own to say: what it is, what it is
#: called, and how it came to be written down.
_OWN = ("backend", "name", "made")


def listed(hmz: Any) -> dict[str, Any]:
    """Every runtime as it is written down, this machine, and what a new one is made of."""
    return {
        "local": _local(),
        "runtimes": [one.held() for one in hmz.runtimes.all()],
        "blanks": _blanks(),
    }


def _local() -> dict[str, Any]:
    """The daemon's own machine, where work runs that names no runtime: never written down."""
    import psutil

    return {
        "host": socket.gethostname(),
        "system": platform.system(),
        "machine": platform.machine(),
        "cpus": os.cpu_count() or 0,
        "memory": psutil.virtual_memory().total,
    }


def _blanks() -> dict[str, dict[str, Any]]:
    """Each backend's fields, by name, as a runtime of it holds them with nothing said."""
    from hmz.coganchor.machines.store import (
        AppleContainerRuntime,
        DockerRuntime,
        SlurmRuntime,
        SSHRuntime,
        SwarmRuntime,
    )

    blanks: dict[str, dict[str, Any]] = {}
    for kind in (
        SSHRuntime,
        DockerRuntime,
        SwarmRuntime,
        AppleContainerRuntime,
        SlurmRuntime,
    ):
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


def _found(hmz: Any, backend: str, name: str) -> Any:
    try:
        one = hmz.runtimes.find(backend, name)
    except ValueError as why:
        raise _refused(str(why)) from why
    if one is None:
        raise RpcError(Code.NOT_FOUND, f"There is no {backend} runtime called {name}.")
    return one


def write(
    hmz: Any,
    backend: str,
    name: str,
    fields: Mapping[str, Any],
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Writes a runtime down, in place of one of its name where it replaces one.

    Returns:
      What :func:`listed` answers afterwards.

    Raises:
      RpcError: 400 for `backend` or `name` among the fields, or a runtime that is not one.
    """
    if taken := sorted({"backend", "name"} & set(fields)):
        raise _refused(f"Say {', '.join(taken)} beside fields, not among them.")
    try:
        made = hmz.runtimes.new(backend, name, **fields)
        if replace:
            hmz.runtimes.write(made)
        else:
            hmz.runtimes.add(made)
    except ValueError as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def remove(hmz: Any, backend: str, name: str) -> dict[str, Any]:
    """Removes a runtime.

    Raises:
      RpcError: 404 for no such runtime.
    """
    one = _found(hmz, backend, name)
    hmz.runtimes.remove(one.backend, one.name)
    return listed(hmz)


def check(hmz: Any, backend: str, name: str) -> dict[str, Any]:
    """Reaches a runtime and says what it has, each field by name.

    Raises:
      RpcError: 404 for no such runtime.
    """
    return dataclasses.asdict(hmz.runtimes.check(_found(hmz, backend, name)))


def hosts(hmz: Any) -> dict[str, Any]:
    """Every `Host` of this machine's ssh configuration, and whether a runtime is saved of it.

    Raises:
      RpcError: 503 for an ssh configuration that cannot be read.
    """
    try:
        found = hmz.runtimes.hosts()
    except OSError as why:
        raise RpcError(
            Code.UNAVAILABLE, f"The ssh config could not be read: {why}"
        ) from why
    saved = {one.name for one in hmz.runtimes.all("ssh")}
    return {
        "hosts": [
            dataclasses.asdict(one) | {"saved": one.alias in saved} for one in found
        ]
    }


def imports(
    hmz: Any, names: Sequence[object], *, update: bool = False
) -> dict[str, Any]:
    """Saves an ssh runtime for each `Host` named.

    Returns:
      What :func:`listed` answers afterwards.

    Raises:
      RpcError: 400 for no names or a host the ssh configuration has not got.
    """
    if not names:
        raise _refused("Say names as the hosts to bring in, by their Host.")
    if not all(isinstance(one, str) for one in names):
        raise _refused("Say names as a list of text.")
    try:
        hmz.runtimes.import_ssh(names=[str(one) for one in names], update=update)
    except ValueError as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def _refused(message: str) -> RpcError:
    return RpcError(Code.REFUSED, message)


def _hmz() -> Any:
    from hmz.runtime import Hmz

    return Hmz()


#: Every method of `runtimes.*`, by name.
METHODS: Mapping[str, Handler] = {
    "runtimes.list": lambda _: listed(_hmz()),
    "runtimes.set": lambda call: write(
        _hmz(),
        call.params["backend"],
        call.params["name"],
        call.params["fields"],
        replace=call.params.get("replace") is True,
    ),
    "runtimes.remove": lambda call: remove(
        _hmz(), call.params["backend"], call.params["name"]
    ),
    "runtimes.check": lambda call: check(
        _hmz(), call.params["backend"], call.params["name"]
    ),
    "runtimes.hosts": lambda _: hosts(_hmz()),
    "runtimes.import": lambda call: imports(
        _hmz(), call.params["names"], update=call.params.get("update") is True
    ),
}
