"""Where a turn goes when the place taking it cannot take it: every step, written and cleared.

A place is `CLI[@ACCOUNT]/MODEL`, and a step is written against one: how many times over a
failed turn is taken again there, how long it waits between, and the places that take it
after. The fallback page `/settings` opens in the terminal interface, through the same
object and into the same file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .routing import Refusal, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "listed"]


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


def _write(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    fallbacks = hmz.fallbacks
    said = asked.text("spec")
    place = fallbacks.reads(said)
    if not place:
        raise Refusal(f"{said} is not a place: say it as CLI[@ACCOUNT]/MODEL.")
    to, tries = asked.texts("to"), asked.body.get("tries", 0)
    policy = asked.body.get("policy") or fallbacks.default
    timeout = asked.body.get("timeout", 0)
    if not isinstance(tries, int) or isinstance(tries, bool) or tries < 0:
        raise Refusal("Say tries as how many more goes, 0 or more.")
    if not isinstance(policy, str) or fallbacks.named(policy) is None:
        raise Refusal(f"{policy} is no way of waiting.")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout < 0
    ):
        raise Refusal("Say timeout in seconds, or 0 for no limit.")
    try:
        fallbacks.points(place, [fallbacks.reads(one) or one for one in to])
        fallbacks.retrying(place, tries, policy, float(timeout))
    except ValueError as why:
        raise Refusal(str(why)) from why
    return listed(hmz)


def _clear(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    said = asked.text("spec")
    if not hmz.fallbacks.clear(hmz.fallbacks.reads(said) or said):
        raise Refusal(f"Nothing is written down against {said}.", 404)
    return listed(hmz)


#: What a page reads of the fallbacks, and does to them.
ROUTES = routes(
    ("GET", "/api/fallbacks", lambda asked: listed(asked.site.hmz)),
    ("POST", "/api/fallbacks", _write),
    ("POST", "/api/fallbacks/clear", _clear),
)
