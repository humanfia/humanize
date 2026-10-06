"""The accounts an agent may run as: each question handed to the store that answers it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import models, providers
from hmz.coganchor.providers import login
from hmz.runtime import Accounts

if TYPE_CHECKING:
    from tests.unit.runtime.doubles_u12 import Stands

WAY = cast("Any", object())
ONE = cast("Any", object())


@pytest.mark.parametrize(
    ("method", "args", "module", "name", "forwarded"),
    [
        ("all", (), providers, "providers", ("",)),
        ("all", ("claude",), providers, "providers", ("claude",)),
        ("ways", ("claude",), providers, "ways", ("claude",)),
        ("way", ("claude", "api"), login, "way_of", ("claude", "api")),
        ("find", ("claude", "work"), providers, "find", ("claude", "work")),
        ("where", ("claude", "work"), providers, "where", ("claude", "work")),
        (
            "make",
            ("claude", "w", WAY, {"K": "v"}),
            login,
            "make",
            ("claude", "w", WAY, {"K": "v"}),
        ),
        ("make", ("claude", "w", WAY), login, "make", ("claude", "w", WAY, None)),
        ("sign_in", (ONE, WAY), login, "sign_in", (ONE, WAY, None)),
        ("sign_in", (ONE, WAY, {"a": "b"}), login, "sign_in", (ONE, WAY, {"a": "b"})),
        ("asks", (WAY, {"a": "b"}), login, "asked", (WAY, {"a": "b"})),
        ("serves", (ONE,), providers, "serves", (ONE,)),
        ("copies", (ONE, "codex"), providers, "copies", (ONE, "codex", "")),
        ("copies", (ONE, "codex", "n"), providers, "copies", (ONE, "codex", "n")),
        ("remove", ("claude", "w"), providers, "remove", ("claude", "w")),
        ("env", ("A=1\nB=2",), providers, "env_of", ("A=1\nB=2",)),
        ("environ", (None,), providers, "environ", (None,)),
        ("models", ("claude",), models, "offered", ("claude", "")),
        ("models", ("claude", "w"), models, "offered", ("claude", "w")),
        ("asked", ("claude",), models, "asked", ("claude", "")),
        ("stale", ("claude", "w"), models, "stale", ("claude", "w")),
        ("ask", ("claude",), models, "ask", ("claude", "")),
        ("ask", ("claude", "w", 3.0), models, "ask", ("claude", "w", 3.0)),
    ],
)
def test_each_question_is_answered_by_the_store_that_keeps_it(
    method: str,
    args: tuple[Any, ...],
    module: object,
    name: str,
    forwarded: tuple[Any, ...],
    stand: Stands,
) -> None:
    asked = stand(module, name)

    said = getattr(Accounts(), method)(*args)

    assert said is asked.returns
    assert asked.calls == [(forwarded, {})]


def test_an_account_of_variables_alone_is_written_with_no_way(stand: Stands) -> None:
    added = stand(providers, "add")

    said = Accounts().write("claude", "work", env={"K": "v"}, args=("--x",))

    assert said is added.returns
    assert added.calls == [(("claude", "work"), {"env": {"K": "v"}, "args": ("--x",)})]


@dataclass
class Way:
    args: tuple[str, ...]


def test_an_account_made_a_way_is_given_that_ways_arguments_filled_in(
    stand: Stands, monkeypatch: pytest.MonkeyPatch
) -> None:
    added = stand(providers, "add")
    stand(login, "way_of", Way(("--url", "{URL}")))

    def filled(one: str, env: dict[str, str]) -> str:
        return one.format(**env)

    monkeypatch.setattr(providers, "filled", filled)

    Accounts().write("codex", "gw", "gateway", {"URL": "https://x"})

    assert added.calls == [
        (("codex", "gw", "gateway", {"URL": "https://x"}, ("--url", "https://x")), {})
    ]


def test_arguments_given_are_kept_as_given(stand: Stands) -> None:
    added = stand(providers, "add")
    way_of = stand(login, "way_of")

    Accounts().write("codex", "gw", "gateway", None, ("--mine",))

    assert added.calls == [(("codex", "gw", "gateway", None, ("--mine",)), {})]
    assert way_of.calls == []


def test_a_way_nobody_offers_adds_no_arguments(
    stand: Stands, monkeypatch: pytest.MonkeyPatch
) -> None:
    added = stand(providers, "add")
    stand(login, "way_of").returns = None

    Accounts().write("codex", "gw", "gone")

    assert added.calls == [(("codex", "gw", "gone", None, ()), {})]
