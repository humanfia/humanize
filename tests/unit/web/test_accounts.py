"""`hmz.web.accounts`: what a page is handed of the accounts there are."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from hmz.web.accounts import listed

#: A key, which a page must never be handed.
_SECRET = "sk-live-0123456789"


@dataclass(frozen=True)
class _Account:
    cli: str
    name: str
    way: str = "key"
    env: dict[str, str] = field(default_factory=dict[str, str])
    made: str = "2026-10-08T10:00:00Z"


class _Accounts:
    """The accounts: one made for claude, and each CLI's own sign-in."""

    def all(self) -> list[_Account]:
        return [_Account("claude", "work", env={"ANTHROPIC_API_KEY": _SECRET})]

    def find(self, cli: str, name: str) -> _Account | None:
        return _Account(cli, name, way="") if not name else None

    def ways(self, cli: str) -> list[Any]:
        asked = SimpleNamespace(
            env="ANTHROPIC_API_KEY", about="the key", secret=True, fixed=""
        )
        return [
            SimpleNamespace(
                name="login", about="sign in", argv=("claude", "login"), asks=()
            ),
            SimpleNamespace(name="key", about="an API key", argv=(), asks=(asked,)),
        ]

    def models(self, cli: str, name: str) -> tuple[Any, ...]:
        return (SimpleNamespace(name="opus"),)

    def asked(self, cli: str, name: str) -> str:
        return ""

    def serves(self, one: _Account) -> tuple[str, ...]:
        return ("pi",)


def _hmz() -> Any:
    return SimpleNamespace(
        accounts=_Accounts(),
        backends=lambda: (
            SimpleNamespace(name="claude"),
            SimpleNamespace(name="codex"),
        ),
    )


def test_an_account_is_listed_by_what_it_sets_and_never_by_a_value() -> None:
    said = listed(_hmz())

    assert _SECRET not in json.dumps(said)
    work, mine = said["accounts"]
    assert (work["cli"], work["name"], work["sets"]) == (
        "claude",
        "work",
        ["ANTHROPIC_API_KEY"],
    )
    assert work["serves"] == ["pi"]
    # The machine's own sign-in, last, and only for a CLI somebody made an account of.
    assert (mine["cli"], mine["name"], mine["serves"]) == ("claude", "", [])


def test_a_way_in_that_runs_the_clis_own_sign_in_is_said_to_need_a_terminal() -> None:
    backends = {one["cli"]: one["ways"] for one in listed(_hmz())["backends"]}

    login, key = backends["claude"]
    assert (login["name"], login["terminal"]) == ("login", True)
    assert (key["name"], key["terminal"]) == ("key", False)
    assert key["asks"] == [
        {"env": "ANTHROPIC_API_KEY", "about": "the key", "secret": True, "fixed": ""}
    ]
