"""`accounts.*`: the accounts an agent may be run as, listed, made, asked again, taken away.

The accounts page `/settings` opens in the terminal interface, read from the same store
through the same object (Section 4.18.2 of the daemon protocol). What a client is handed of an
account is its name, the way it was made by and the names of the variables it sets -- never a
value, since it is drawn where somebody can read it. A way in that runs the backend's own
sign-in hands that command a terminal, which a client of the daemon has not got, so an account
is made here only out of a way that is answers alone. The ways in through the local LiteLLM
gateway are handed under a group of their own, and where the `[litellm]` extra is missing a
CLI that could have them is handed the line that adds it instead.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.coganchor.backends import Way
    from hmz.coganchor.providers import Provider
    from hmz.rpc import Handler

__all__ = ["METHODS", "copy", "correct", "create", "listed", "models", "remove"]


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
        "gateway": accounts.GATEWAY,
        "accounts": [
            _account(accounts, one)
            for one in sorted(
                [*held, *mine], key=lambda one: (one.cli, not one.name, one.name)
            )
        ],
        "backends": [
            {
                "cli": profile.name,
                "ways": [
                    _way(one, accounts.GATEWAY) for one in accounts.ways(profile.name)
                ],
                "wants": accounts.wants(profile.name),
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


def _way(way: Way, gateway: str) -> dict[str, Any]:
    from hmz.coganchor.backends import upstream

    return {
        "name": way.name,
        "about": way.about,
        "group": gateway if upstream(way.name) else "",
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


def create(
    hmz: Any, cli: str, name: str, named: str, answers: Mapping[str, object]
) -> dict[str, Any]:
    """Makes an account out of the answers to a way in.

    Args:
      hmz: Humanize.
      cli: The backend it is for.
      name: What it is called.
      named: The way in it is made by.
      answers: What each variable the way asks is, by name; one left empty is unanswered.

    Returns:
      What :func:`listed` answers afterwards.

    Raises:
      RpcError: 400 for an unknown way, one that needs a terminal, a variable unanswered or
        an invalid name, and 409 for a name taken.
    """
    try:
        way = hmz.accounts.way(cli, named)
    except ValueError as why:
        raise _refused(str(why)) from why
    if way is None:
        raise _refused(f"{cli} has no way in called {named}.")
    if way.argv:
        raise _refused(
            f"{named} runs {cli}'s own sign-in, which needs a terminal: make it from "
            "/settings in hmz."
        )
    said = {key: value for key, value in _answers(answers).items() if value}
    if missing := hmz.accounts.asks(way, said):
        raise _refused(f"{named} still needs {', '.join(missing)}.")
    try:
        if hmz.accounts.find(cli, name) is not None:
            raise RpcError(
                Code.CONFLICT, f"{cli} has an account called {name} already."
            )
        hmz.accounts.make(cli, name, way, said)
    except (ValueError, OSError) as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def correct(
    hmz: Any, cli: str, name: str, answers: Mapping[str, object]
) -> dict[str, Any]:
    """Writes an account down again with what its way in is answered with now.

    What is left blank keeps what it was: a client is never handed a value to show back, so it
    can only say what changes. A way in that runs the CLI's own sign-in is corrected at a
    terminal, which signs in again.

    Raises:
      RpcError: 404 for no such account, and 400 for a variable the way does not ask or a way
        that needs a terminal.
    """
    try:
        one = hmz.accounts.find(cli, name)
    except ValueError as why:
        raise _refused(str(why)) from why
    if one is None or not name:
        raise RpcError(
            Code.NOT_FOUND,
            f"{cli} has no account called {name or 'of this machine'} to correct.",
        )
    way = hmz.accounts.way(cli, one.way) if one.way else None
    if way is not None and way.argv:
        raise _refused(
            f"{name} runs {cli}'s own sign-in, which needs a terminal: sign in again from "
            "/settings in hmz."
        )
    said = _answers(answers)
    if way is not None and (
        unknown := sorted(set(said) - {each.env for each in way.asks})
    ):
        raise _refused(f"{one.way} asks nothing called {', '.join(unknown)}.")
    env = dict(one.env) | {key: value for key, value in said.items() if value}
    try:
        hmz.accounts.write(cli, name, one.way, env)
    except (ValueError, OSError) as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def remove(hmz: Any, cli: str, name: str) -> dict[str, Any]:
    """Removes an account.

    Raises:
      RpcError: 404 for no such account, and 400 for one that cannot be removed.
    """
    try:
        if not hmz.accounts.remove(cli, name):
            raise RpcError(Code.NOT_FOUND, f"{cli} has no account called {name}.")
    except (ValueError, OSError) as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def models(hmz: Any, cli: str, name: str) -> dict[str, Any]:
    """Asks a CLI what it runs as an account, `""` being this machine's own.

    Raises:
      RpcError: 404 for no such account, and 502 for a CLI that will not say.
    """
    try:
        found = hmz.accounts.find(cli, name)
    except ValueError as why:
        raise _refused(str(why)) from why
    if found is None:
        raise RpcError(
            Code.NOT_FOUND, f"{cli} has no account called {name or 'of this machine'}."
        )
    try:
        hmz.accounts.ask(cli, name)
    except (ValueError, OSError, subprocess.TimeoutExpired) as why:
        raise RpcError(
            Code.UPSTREAM, f"{cli} would not say what it runs: {why}"
        ) from why
    return listed(hmz)


def copy(hmz: Any, cli: str, name: str, into: str) -> dict[str, Any]:
    """Copies an account to another CLI.

    Raises:
      RpcError: 404 for no such account, and 400 for a copy that cannot be made.
    """
    try:
        one = hmz.accounts.find(cli, name)
        if one is None:
            raise RpcError(Code.NOT_FOUND, f"{cli} has no account called {name}.")
        hmz.accounts.copies(one, into)
    except (ValueError, OSError) as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def _answers(answers: Mapping[str, object]) -> dict[str, str]:
    """The answers sent, each of which must be text."""
    if not all(isinstance(one, str) for one in answers.values()):
        raise _refused("Say each answer as text.")
    return {key: str(value) for key, value in answers.items()}


def _refused(message: str) -> RpcError:
    return RpcError(Code.REFUSED, message)


def _hmz() -> Any:
    from hmz.runtime import Hmz

    return Hmz()


#: Every method of `accounts.*`, by name.
METHODS: Mapping[str, Handler] = {
    "accounts.list": lambda _: listed(_hmz()),
    "accounts.create": lambda call: create(
        _hmz(),
        call.params["cli"],
        call.params["name"],
        call.params["way"],
        call.params.get("answers", {}),
    ),
    "accounts.correct": lambda call: correct(
        _hmz(), call.params["cli"], call.params["name"], call.params.get("answers", {})
    ),
    "accounts.remove": lambda call: remove(
        _hmz(), call.params["cli"], call.params["name"]
    ),
    "accounts.models": lambda call: models(
        _hmz(), call.params["cli"], call.params["name"]
    ),
    "accounts.copy": lambda call: copy(
        _hmz(), call.params["cli"], call.params["name"], call.params["into"]
    ),
}
