"""`hmz.tui.pick`: the ways into a CLI, as the form an account is made on drops them."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

import hmz.daemon
from hmz.coganchor import backends
from hmz.tui import pick
from hmz.tui.dropdown import Value


def _way(name: str) -> Any:
    return SimpleNamespace(name=name, about=name, asks=(), argv=("login",), sets=())


@dataclass
class _Accounts:
    """The ways into claude: its own, then those through the gateway, then variables."""

    GATEWAY = "LiteLLM"
    names: tuple[str, ...] = ("login", "via-openai", "via-bedrock", "env")
    wanted: str = ""
    asked: list[str] = field(default_factory=list[str])

    def all(self) -> list[Any]:
        return []

    def ways(self, cli: str) -> tuple[Any, ...]:
        return tuple(_way(one) for one in self.names)

    def way(self, cli: str, name: str) -> Any:
        return _way(name) if name in self.names else None

    def serves(self, one: Any) -> tuple[str, ...]:
        return ()

    def wants(self, cli: str) -> str:
        self.asked.append(cli)
        return self.wanted


@pytest.fixture
def accounts(monkeypatch: pytest.MonkeyPatch) -> _Accounts:
    held = _Accounts()
    here = SimpleNamespace(
        accounts=held,
        installed=lambda: {"claude": ()},
        backends=lambda: (SimpleNamespace(name="claude"),),
    )
    monkeypatch.setattr(hmz.daemon, "Hmz", lambda: here)

    # A way through the gateway is one called `via-` something, as far as the form is told.
    def upstream(way: str) -> str:
        return way.removeprefix("via-") if way.startswith("via-") else ""

    monkeypatch.setattr(backends, "upstream", upstream)
    return held


def test_the_ways_through_the_gateway_are_dropped_last_under_one_heading(
    accounts: _Accounts,
) -> None:
    dropped = pick.Signing("claude").dropping("way")

    assert [(one.value, one.group) for one in dropped.values] == [
        ("login", ""),
        ("env", ""),
        ("via-openai", "LiteLLM"),
        ("via-bedrock", "LiteLLM"),
    ]


def test_a_cli_wanting_the_extra_has_the_line_that_adds_it_said_under_the_heading(
    accounts: _Accounts,
) -> None:
    accounts.names = ("login", "env")
    accounts.wanted = "litellm is not installed; run: it"

    dropped = pick.Signing("claude").dropping("way")

    assert dropped.values[-1] == Value(
        "", "litellm is not installed; run: it", group="LiteLLM", inert=True
    )
    assert accounts.asked == ["claude"]


def test_a_cli_with_no_ways_through_the_gateway_has_no_heading(
    accounts: _Accounts,
) -> None:
    accounts.names = ("login", "env")

    dropped = pick.Signing("claude").dropping("way")

    assert {one.group for one in dropped.values} == {""}
