"""The accounts an agent may be run as: listed, made out of answers, asked again, taken away.

The accounts page `/settings` opens in the terminal interface, read from the same store
through the same object. What a page is handed of an account is what that page draws: its
name, the way it was made by and the names of the variables it sets -- never a value, since
this is drawn where somebody can read it. A way in that runs the backend's own sign-in hands
that command the terminal, which a page has not got, so a page makes an account only out of a
way that is answers alone, and says where the others are made.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .routing import Refusal, routes

if TYPE_CHECKING:
    from hmz.coganchor.backends import Way
    from hmz.coganchor.providers import Provider

    from .routing import Asked

__all__ = ["ROUTES", "listed"]


def listed(hmz: Any) -> dict[str, Any]:
    """Every account, by the backend it is for, and how each backend can be signed into.

    The account this machine is already signed into is listed under each backend that has
    accounts of its own, last of them, as the terminal interface lists it: it is what an
    agent nobody gave an account runs as.
    """
    from hmz.coganchor.providers import LOCAL

    accounts = hmz.accounts
    held: list[Provider] = accounts.all()
    whose = {one.cli for one in held}
    mine = [
        one
        for profile in hmz.backends()
        if profile.name in whose
        and (one := accounts.find(profile.name, LOCAL)) is not None
    ]
    return {
        "accounts": [
            _account(accounts, one)
            for one in sorted(
                [*held, *mine], key=lambda one: (one.cli, not one.name, one.name)
            )
        ],
        "backends": [
            {
                "cli": profile.name,
                "ways": [_way(one) for one in accounts.ways(profile.name)],
            }
            for profile in hmz.backends()
        ],
    }


def _account(accounts: Any, one: Provider) -> dict[str, Any]:
    return {
        "cli": one.cli,
        "name": one.name,
        "way": one.way,
        "sets": sorted(one.env),
        "made": one.made,
        "models": [model.name for model in accounts.models(one.cli, one.name)],
        "asked": accounts.asked(one.cli, one.name),
        "serves": list(accounts.serves(one)) if one.name else [],
    }


def _way(way: Way) -> dict[str, Any]:
    return {
        "name": way.name,
        "about": way.about,
        "terminal": bool(way.argv),
        "asks": [
            {
                "env": one.env,
                "about": one.about,
                "secret": one.secret,
                "fixed": one.fixed,
            }
            for one in way.asks
        ],
    }


def _make(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    cli, name, named = asked.text("cli"), asked.text("name"), asked.text("way")
    try:
        way = hmz.accounts.way(cli, named)
    except ValueError as why:
        raise Refusal(str(why)) from why
    if way is None:
        raise Refusal(f"{cli} has no way in called {named}.")
    if way.argv:
        raise Refusal(
            f"{named} runs {cli}'s own sign-in, which needs a terminal: make it from "
            "/settings in hmz."
        )
    answers = asked.named("answers")
    if not all(isinstance(one, str) for one in answers.values()):
        raise Refusal("Say each answer as text.")
    said = {key: value for key, value in answers.items() if value}
    if missing := hmz.accounts.asks(way, said):
        raise Refusal(f"{named} still needs {', '.join(missing)}.")
    try:
        if hmz.accounts.find(cli, name) is not None:
            raise Refusal(f"{cli} has an account called {name} already.", 409)
        hmz.accounts.make(cli, name, way, said)
    except (ValueError, OSError) as why:
        raise Refusal(str(why)) from why
    return listed(hmz)


def _remove(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    cli, name = asked.text("cli"), asked.text("name")
    try:
        if not hmz.accounts.remove(cli, name):
            raise Refusal(f"{cli} has no account called {name}.", 404)
    except ValueError as why:
        raise Refusal(str(why)) from why
    return listed(hmz)


def _models(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    cli, name = asked.text("cli"), asked.text("name", required=False)
    try:
        found = hmz.accounts.find(cli, name)
    except ValueError as why:
        raise Refusal(str(why)) from why
    if found is None:
        raise Refusal(f"{cli} has no account called {name or 'of this machine'}.", 404)
    hmz.accounts.ask(cli, name)
    return listed(hmz)


def _copy(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    cli, name, into = asked.text("cli"), asked.text("name"), asked.text("into")
    try:
        one = hmz.accounts.find(cli, name)
        if one is None:
            raise Refusal(f"{cli} has no account called {name}.", 404)
        hmz.accounts.copies(one, into)
    except (ValueError, OSError) as why:
        raise Refusal(str(why)) from why
    return listed(hmz)


#: What a page reads of the accounts, and does to them.
ROUTES = routes(
    ("GET", "/api/accounts", lambda asked: listed(asked.site.hmz)),
    ("POST", "/api/accounts", _make),
    ("POST", "/api/accounts/remove", _remove),
    ("POST", "/api/accounts/models", _models),
    ("POST", "/api/accounts/copy", _copy),
)
