"""`fallbacks.*`: where a turn goes when the place taking it cannot take it, written and cleared.

A place is `CLI[@ACCOUNT]/MODEL`, and a step is written against one: how many times over a
failed turn is taken again there, how long it waits between, and the places that take it
after (Section 4.18.3 of the daemon protocol). The fallback page `/settings` opens in the
terminal interface, through the same object and into the same file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hmz.rpc import Handler

__all__ = ["METHODS", "clear", "listed", "write"]


def listed(hmz: Any) -> dict[str, Any]:
    """Every step written down, the ways of waiting there are, and the places to name."""
    fallbacks = hmz.fallbacks
    return {
        "steps": [
            {
                "spec": one.spec,
                "to": list(one.to),
                "tries": one.tries,
                "policy": one.policy,
                "timeout": one.timeout,
            }
            for one in fallbacks.all()
        ],
        "policies": [
            {"name": one.name, "about": one.about} for one in fallbacks.policies()
        ],
        "default": fallbacks.default,
        "places": _places(hmz),
    }


def _places(hmz: Any) -> list[str]:
    """Every place a step could name: each model of each account, this machine's included."""
    accounts, spec = hmz.accounts, hmz.fallbacks.spec
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


def write(
    hmz: Any,
    said: str,
    to: Sequence[object] = (),
    tries: object = 0,
    policy: object = "",
    timeout: object = 0,
) -> dict[str, Any]:
    """Writes the step of one place.

    Args:
      hmz: Humanize.
      said: The place, as `CLI[@ACCOUNT]/MODEL`.
      to: The places a failed turn goes to after it, in order.
      tries: How many more goes it is given there, 0 or more.
      policy: How it waits between them, or "" for the default.
      timeout: How many seconds a turn there may take, 0 for no limit.

    Returns:
      What :func:`listed` answers afterwards.

    Raises:
      RpcError: 400 for a value `Fallbacks` refuses.
    """
    fallbacks = hmz.fallbacks
    place = fallbacks.reads(said)
    if not place:
        raise _refused(f"{said} is not a place: say it as CLI[@ACCOUNT]/MODEL.")
    if not all(isinstance(one, str) for one in to):
        raise _refused("Say to as a list of text.")
    policy = policy or fallbacks.default
    if not isinstance(tries, int) or isinstance(tries, bool) or tries < 0:
        raise _refused("Say tries as how many more goes, 0 or more.")
    if not isinstance(policy, str) or fallbacks.named(policy) is None:
        raise _refused(f"{policy} is no way of waiting.")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout < 0
    ):
        raise _refused("Say timeout in seconds, or 0 for no limit.")
    try:
        fallbacks.points(place, [fallbacks.reads(one) or one for one in map(str, to)])
        fallbacks.retrying(place, tries, policy, float(timeout))
    except ValueError as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def clear(hmz: Any, said: str) -> dict[str, Any]:
    """Removes the step of one place.

    Raises:
      RpcError: 404 for a place with no step.
    """
    if not hmz.fallbacks.clear(hmz.fallbacks.reads(said) or said):
        raise RpcError(Code.NOT_FOUND, f"Nothing is written down against {said}.")
    return listed(hmz)


def _refused(message: str) -> RpcError:
    return RpcError(Code.REFUSED, message)


def _hmz() -> Any:
    from hmz.runtime import Hmz

    return Hmz()


def _write(said: Mapping[str, Any]) -> dict[str, Any]:
    return write(
        _hmz(),
        said["spec"],
        said.get("to", []),
        said.get("tries", 0),
        said.get("policy", ""),
        said.get("timeout", 0),
    )


#: Every method of `fallbacks.*`, by name.
METHODS: Mapping[str, Handler] = {
    "fallbacks.list": lambda _: listed(_hmz()),
    "fallbacks.set": lambda call: _write(call.params),
    "fallbacks.clear": lambda call: clear(_hmz(), call.params["spec"]),
}
