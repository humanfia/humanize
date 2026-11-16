"""The accounts an agent may be run as: listed, made out of answers, asked again, taken away.

The routes of `accounts.*` (`hmz.daemon.api.accounts`): what a page is handed of an account is
its name, the way it was made by and the names of the variables it sets -- never a value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.daemon.api import accounts
from hmz.daemon.api.accounts import listed

from .routing import refused, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "listed"]


def _make(asked: Asked) -> dict[str, Any]:
    cli, name, way = asked.text("cli"), asked.text("name"), asked.text("way")
    with refused():
        return accounts.create(asked.site.hmz, cli, name, way, asked.named("answers"))


def _correct(asked: Asked) -> dict[str, Any]:
    cli, name = asked.text("cli"), asked.text("name")
    with refused():
        return accounts.correct(asked.site.hmz, cli, name, asked.named("answers"))


def _remove(asked: Asked) -> dict[str, Any]:
    cli, name = asked.text("cli"), asked.text("name")
    with refused():
        return accounts.remove(asked.site.hmz, cli, name)


def _models(asked: Asked) -> dict[str, Any]:
    cli, name = asked.text("cli"), asked.text("name", required=False)
    with refused():
        return accounts.models(asked.site.hmz, cli, name)


def _copy(asked: Asked) -> dict[str, Any]:
    cli, name, into = asked.text("cli"), asked.text("name"), asked.text("into")
    with refused():
        return accounts.copy(asked.site.hmz, cli, name, into)


#: What a page reads of the accounts, and does to them.
ROUTES = routes(
    ("GET", "/api/accounts", lambda asked: listed(asked.site.hmz)),
    ("POST", "/api/accounts", _make),
    ("POST", "/api/accounts/correct", _correct),
    ("POST", "/api/accounts/remove", _remove),
    ("POST", "/api/accounts/models", _models),
    ("POST", "/api/accounts/copy", _copy),
)
