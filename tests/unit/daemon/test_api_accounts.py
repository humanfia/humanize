"""`hmz.daemon.api.accounts`: accounts made, corrected and asked, and what each is refused."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from hmz.daemon.api import accounts
from hmz.rpc import RpcError

#: A key, which a client must never be handed.
_SECRET = "sk-live-0123456789"

_ASKED = SimpleNamespace(env="KEY", about="the key", secret=True, fixed="")


@dataclass(frozen=True)
class _Account:
    cli: str
    name: str
    way: str = "key"
    env: dict[str, str] = field(default_factory=dict[str, str])
    made: str = "2026-10-08T10:00:00Z"


class _Accounts:
    GATEWAY = "LiteLLM"

    def __init__(self) -> None:
        self.held = {
            ("claude", "work"): _Account("claude", "work", env={"KEY": _SECRET})
        }

    def all(self) -> list[_Account]:
        return list(self.held.values())

    def find(self, cli: str, name: str) -> _Account | None:
        return self.held.get((cli, name)) or (_Account(cli, "") if not name else None)

    def way(self, cli: str, name: str) -> Any:
        ways = {
            "login": SimpleNamespace(argv=("claude", "login"), asks=()),
            "key": SimpleNamespace(argv=(), asks=(_ASKED,)),
        }
        return ways.get(name)

    def ways(self, cli: str) -> list[Any]:
        return []

    def asks(self, way: Any, said: dict[str, str]) -> list[str]:
        return [one.env for one in way.asks if one.env not in said]

    def make(self, cli: str, name: str, way: Any, said: dict[str, str]) -> None:
        self.held[cli, name] = _Account(cli, name, env=said)

    def write(self, cli: str, name: str, way: str, env: dict[str, str]) -> None:
        self.held[cli, name] = _Account(cli, name, way, env)

    def ask(self, cli: str, name: str) -> None:
        raise subprocess.TimeoutExpired(cli, 1)

    def wants(self, cli: str) -> str:
        return ""

    def models(self, cli: str, name: str) -> tuple[Any, ...]:
        return ()

    def asked(self, cli: str, name: str) -> str:
        return ""

    def serves(self, one: _Account) -> tuple[str, ...]:
        return ()


def _hmz() -> Any:
    return SimpleNamespace(
        accounts=_Accounts(), backends=lambda: (SimpleNamespace(name="claude"),)
    )


def _refused(code: int, call: Any, *args: Any) -> str:
    with pytest.raises(RpcError) as refused:
        call(*args)
    assert refused.value.code == code, refused.value.message
    return refused.value.message


def test_an_account_is_made_out_of_answers_and_listed_without_them() -> None:
    hmz = _hmz()

    said = accounts.create(hmz, "claude", "home", "key", {"KEY": "sk-home"})

    assert "sk-home" not in json.dumps(said)
    assert _SECRET not in json.dumps(said)
    assert [(one["name"], one["sets"]) for one in said["accounts"]] == [
        ("home", ["KEY"]),
        ("work", ["KEY"]),
        ("", []),
    ]


def test_what_making_an_account_is_refused() -> None:
    hmz = _hmz()

    assert "needs a terminal" in _refused(
        400, accounts.create, hmz, "claude", "a", "login", {}
    )
    assert _refused(400, accounts.create, hmz, "claude", "a", "key", {"KEY": ""}) == (
        "key still needs KEY."
    )
    assert _refused(400, accounts.create, hmz, "claude", "a", "nope", {}) == (
        "claude has no way in called nope."
    )
    assert _refused(400, accounts.create, hmz, "claude", "a", "key", {"KEY": 1}) == (
        "Say each answer as text."
    )
    _refused(409, accounts.create, hmz, "claude", "work", "key", {"KEY": "k"})


def test_correcting_keeps_what_is_not_answered_and_refuses_what_is_not_asked() -> None:
    hmz = _hmz()

    accounts.correct(hmz, "claude", "work", {"KEY": ""})
    assert hmz.accounts.held["claude", "work"].env == {"KEY": _SECRET}
    _refused(400, accounts.correct, hmz, "claude", "work", {"OTHER": "x"})
    _refused(404, accounts.correct, hmz, "claude", "nobody", {})


def test_a_cli_that_will_not_say_what_it_runs_is_upstream() -> None:
    assert "would not say" in _refused(502, accounts.models, _hmz(), "claude", "")
    _refused(404, accounts.models, _hmz(), "claude", "nobody")
