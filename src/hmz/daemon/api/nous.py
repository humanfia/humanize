"""`nous.*`: every nous, concrete and virtual, written, renamed and cleared.

A concrete nous is `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`, a virtual one a name standing for a
graph of other nous; each has its tries, its wait, its limit and the graph a turn goes to once
those are spent (Section 4.18.3 of the daemon protocol). The nous page `/settings` opens in the
terminal interface writes through the same object and into the same file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.coganchor.nous import Nous
    from hmz.rpc import Handler

__all__ = ["METHODS", "clear", "listed", "rename", "write"]


def _shown(one: Nous) -> dict[str, Any]:
    from hmz.coganchor import nous

    return {
        "name": one.name,
        "virtual": one.virtual,
        "tries": one.tries,
        "policy": one.policy,
        "timeout": one.timeout,
        "graph": nous.shown(one.graph),
        "then": nous.shown(one.then),
    }


def listed(hmz: Any) -> dict[str, Any]:
    """Every nous, the ways of waiting and picking there are, and the nous to name."""
    from hmz.coganchor import backends, nous

    book = hmz.nous
    return {
        "nous": [_shown(one) for one in book.all()],
        "policies": [{"name": one.name, "about": one.about} for one in book.policies()],
        "default": book.default,
        "strategies": [
            {"name": one.name, "about": one.about} for one in book.strategies()
        ],
        "faults": [*backends.FAULTS, nous.ANY],
        "concrete": _concrete(hmz),
    }


def _concrete(hmz: Any) -> list[str]:
    """Every concrete nous a graph could name: each model of each account, at no effort."""
    accounts, spec = hmz.accounts, hmz.nous.spec
    found = {
        spec(cli, model.name)
        for cli, models in hmz.installed().items()
        for model in models
    }
    found |= {
        spec(one.cli, model.name, one.name)
        for one in accounts.all()
        for model in accounts.models(one.cli, one.name)
    }
    return sorted(found)


def write(hmz: Any, said: Mapping[str, Any]) -> dict[str, Any]:
    """Writes one nous, whole.

    Args:
      hmz: Humanize.
      said: `name`, and `tries`, `policy`, `timeout`, `graph` and `then` as `nous.list`
        answers them; a graph may also be a nous or a list of them tried in turn.

    Returns:
      What :func:`listed` answers afterwards.

    Raises:
      RpcError: 400 for a value `NousBook` refuses.
    """
    from hmz.coganchor import nous

    book = hmz.nous
    name, tries = said.get("name"), said.get("tries", 0)
    policy, timeout = said.get("policy") or book.default, said.get("timeout", 0)
    if not isinstance(name, str) or not book.reads(name):
        raise _refused(
            f"{name} is not a nous: say it as HARNESS[@ACCOUNT]/MODEL[:EFFORT] or a name."
        )
    if not isinstance(tries, int) or isinstance(tries, bool) or tries < 0:
        raise _refused("Say tries as how many more goes, 0 or more.")
    if not isinstance(policy, str) or book.named(policy) is None:
        raise _refused(f"{policy} is no way of waiting.")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout < 0
    ):
        raise _refused("Say timeout in seconds, or 0 for no limit.")
    try:
        book.put(
            nous.Nous(
                name,
                tries,
                policy,
                float(timeout),
                book.graph(said.get("graph")),
                book.graph(said.get("then")),
            )
        )
    except (TypeError, ValueError) as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def rename(hmz: Any, said: str, name: str) -> dict[str, Any]:
    """Gives a virtual nous another name.

    Raises:
      RpcError: 400 for a name that cannot be given.
    """
    try:
        hmz.nous.renamed(said, name)
    except ValueError as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def clear(hmz: Any, said: str) -> dict[str, Any]:
    """Removes one nous.

    Raises:
      RpcError: 404 for a nous nothing is written against; 400 for one still named.
    """
    try:
        gone = hmz.nous.clear(said)
    except ValueError as why:
        raise _refused(str(why)) from why
    if not gone:
        raise RpcError(Code.NOT_FOUND, f"Nothing is written down against {said}.")
    return listed(hmz)


def _refused(message: str) -> RpcError:
    return RpcError(Code.REFUSED, message)


def _hmz() -> Any:
    from hmz.runtime import Hmz

    return Hmz()


#: Every method of `nous.*`, by name.
METHODS: Mapping[str, Handler] = {
    "nous.list": lambda _: listed(_hmz()),
    "nous.set": lambda call: write(_hmz(), call.params),
    "nous.rename": lambda call: rename(_hmz(), call.params["name"], call.params["to"]),
    "nous.clear": lambda call: clear(_hmz(), call.params["name"]),
}
