"""`hmz.coganchor.prices`: unit prices read from a kept copy, refreshed from a local file.

Never the network: `prices.WHENCE` points every refresh at a file under `tmp_path`.
"""

from __future__ import annotations

import itertools
import json
import os
import time
import types
from typing import TYPE_CHECKING, Any

import pytest

from hmz import machine
from hmz.coganchor import prices

if TYPE_CHECKING:
    from pathlib import Path

#: Each test's clock starts this far past the last one's, so that the once-an-hour limit on
#: refreshing a process holds between the refreshes of one test and never across two.
_EPOCHS = itertools.count(1)


def _later(monkeypatch: pytest.MonkeyPatch) -> None:
    """Moves the module's monotonic clock on past any refresh tried so far."""
    start = next(_EPOCHS) * 10 * prices.STALE
    monkeypatch.setattr(
        prices,
        "time",
        types.SimpleNamespace(
            time=time.time, monotonic=lambda: start + time.monotonic()
        ),
    )


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    _later(monkeypatch)


def _model(
    ident: str, name: str, provider: str = "anthropic", **per: float
) -> dict[str, Any]:
    return {
        "id": ident,
        "name": name,
        "provider": provider,
        "pricingItems": [
            {"category": f"{kind}_tokens", "price": rate} for kind, rate in per.items()
        ],
    }


def _listing(**overrides: Any) -> dict[str, Any]:
    newest = {
        "date": "2026-09-01",
        "models": [
            {
                **_model("claude-sonnet-5", "Claude Sonnet 5", input=3, output=15),
                "pricingItems": [
                    {"category": "input_tokens", "price": 3},
                    {"category": "input_tokens", "price": 6},  # a longer-context tier
                    {"category": "output_tokens", "price": 15},
                    {"category": "cache_read_tokens", "price": 0.3},
                    {"category": "cache_write_tokens", "price": 3.75},
                    {"category": "cache_storage", "price": 4.5},
                ],
            },
            _model("claude-haiku-4.5", "Claude Haiku 4.5", input=1, output=5),
            _model("claude-opus-5", "Claude Opus 5", input=5, output=25),
            _model("gpt-5.6-sol", "GPT-5.6 Sol", "openai", input=2, output=8),
            _model("nameless-out", "", "x", output=2),
            _model("unpriced", "Unpriced", "x"),
            {"id": "", "pricingItems": [{"category": "input_tokens", "price": 1}]},
            {
                "id": "odd",
                "pricingItems": [
                    {"category": "input_tokens", "price": True},
                    {"category": "output_tokens", "price": -1},
                    {"category": "input_tokens", "price": "1"},
                    "junk",
                ],
            },
            "junk",
        ],
    }
    older = {"date": "2024-01-01", "models": [_model("claude-sonnet-5", "", input=99)]}
    return {
        "currency": "USD",
        "unit": "per 1M tokens",
        "versions": [older, newest, "junk"],
        **overrides,
    }


def _source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, said: object) -> Path:
    at = tmp_path / "prices-source.json"
    at.write_text(json.dumps(said), encoding="utf-8")
    monkeypatch.setenv(prices.WHENCE, str(at))
    return at


@pytest.fixture
def listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _source(tmp_path, monkeypatch, _listing())
    assert prices.refresh(wait=True)
    return prices.where()


def test_where_is_this_machines_own() -> None:
    assert prices.where() == machine() / "prices.json"


@pytest.mark.parametrize(
    ("dollars", "shown"),
    [
        (0, "$0.00"),
        (-1, "$0.00"),
        (0.00012, "$0.0001"),
        (0.0099, "$0.0099"),
        (0.01, "$0.01"),
        (1.234, "$1.23"),
        (99.99, "$99.99"),
        (100, "$100"),
        (12345.6, "$12,346"),
    ],
)
def test_money(dollars: float, shown: str) -> None:
    assert prices.money(dollars) == shown


def test_nothing_is_priced_before_anything_is_kept() -> None:
    assert prices.price("claude-sonnet-5") is None
    assert prices.cost({"input": 1000}, "claude-sonnet-5") is None


@pytest.mark.parametrize("off", ["off", "", " OFF ", "0", "no", "none"])
def test_refresh_turned_off_reaches_for_nothing(
    off: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(prices.WHENCE, off)
    assert not prices.refresh(wait=True)
    assert not prices.where().exists()
    assert not prices.ready()


def test_refresh_keeps_the_newest_version_trimmed(listed: Path) -> None:
    kept = json.loads(listed.read_text(encoding="utf-8"))
    assert kept["date"] == "2026-09-01"
    assert kept["source"] == os.environ[prices.WHENCE]
    assert set(kept["models"]) == {
        "claude-sonnet-5",
        "claude-haiku-4.5",
        "claude-opus-5",
        "gpt-5.6-sol",
        "nameless-out",
    }
    # The first tier of each kind wins, and what is charged by the hour is left out.
    assert kept["models"]["claude-sonnet-5"]["per_million"] == {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    }


@pytest.mark.parametrize(
    ("asked", "found"),
    [
        ("claude-sonnet-5", "claude-sonnet-5"),
        ("anthropic/claude-sonnet-5", "claude-sonnet-5"),
        ("us.anthropic.claude-sonnet-5-v1:0", "claude-sonnet-5"),
        ("Claude Sonnet 5", "claude-sonnet-5"),
        ("claude-sonnet-5@latest", "claude-sonnet-5"),
        ("claude-haiku-4-5-20251001", "claude-haiku-4.5"),
        ("claude-haiku-4-5", "claude-haiku-4.5"),
        ("aws/anthropic/bedrock-claude-opus-5", "claude-opus-5"),
        ("vertex-claude-opus-5", "claude-opus-5"),
        ("openai/GPT-5.6-SOL", "gpt-5.6-sol"),
    ],
)
def test_price_matches_spellings_of_one_model(
    listed: Path, asked: str, found: str
) -> None:
    priced = prices.price(asked)
    assert priced is not None
    assert priced.model == found


@pytest.mark.parametrize("asked", ["gpt-5", "claude-sonnet", "unpriced", "", "odd"])
def test_price_never_guesses(listed: Path, asked: str) -> None:
    assert prices.price(asked) is None


def test_price_carries_the_provider(listed: Path) -> None:
    priced = prices.price("gpt-5.6-sol")
    assert priced is not None
    assert priced.provider == "openai"
    assert priced.per_million == {"input": 2.0, "output": 8.0}


@pytest.mark.parametrize(
    ("usage", "dollars"),
    [
        ({"input": 1_000_000, "output": 1_000_000}, 18.0),
        ({"input": 500_000}, 1.5),
        # Reasoning is billed as output.
        ({"reasoning": 1_000_000}, 15.0),
        ({"cache_read": 1_000_000}, 0.3),
        # A kind nobody prices adds nothing, but the rest still count.
        ({"input": 1_000_000, "mystery": 10**9}, 3.0),
    ],
)
def test_cost(listed: Path, usage: dict[str, float], dollars: float) -> None:
    assert prices.cost(usage, "claude-sonnet-5") == pytest.approx(dollars)


def test_a_cache_write_falls_back_to_the_input_price(listed: Path) -> None:
    assert prices.cost({"cache_write": 1_000_000}, "gpt-5.6-sol") == pytest.approx(2.0)


def test_a_cache_read_never_falls_back_to_the_input_price(listed: Path) -> None:
    assert prices.cost({"cache_read": 1_000_000}, "gpt-5.6-sol") is None


@pytest.mark.parametrize(
    "usage", [{}, {"input": 0, "output": 0}, {"mystery": 100}, {"input": -5}]
)
def test_cost_of_nothing_priced_is_no_answer_rather_than_free(
    listed: Path, usage: dict[str, float]
) -> None:
    assert prices.cost(usage, "claude-sonnet-5") is None


def test_cost_of_an_unlisted_model_is_no_answer(listed: Path) -> None:
    assert prices.cost({"input": 1000}, "nobody-lists-me") is None


@pytest.mark.parametrize(
    "said",
    [
        _listing(currency="EUR"),
        _listing(unit="per 1K tokens"),
        _listing(versions=[]),
        _listing(versions="not a list"),
        _listing(versions=[{"date": "2026-01-01", "models": []}]),
        _listing(versions=[{"date": "2026-01-01", "models": [_model("x", "X")]}]),
        ["not", "an", "object"],
    ],
)
def test_refresh_refuses_what_it_cannot_read_as_dollars_a_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, said: object
) -> None:
    _source(tmp_path, monkeypatch, said)
    assert not prices.refresh(wait=True)
    assert not prices.where().exists()


def test_refresh_from_a_file_that_is_not_json_keeps_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = tmp_path / "broken.json"
    at.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(prices.WHENCE, str(at))
    assert not prices.refresh(wait=True)


@pytest.mark.parametrize(
    "whence", ["/nowhere/prices.json", "ftp://example.invalid/p.json"]
)
def test_a_source_that_cannot_be_read_leaves_what_was_kept(
    listed: Path, monkeypatch: pytest.MonkeyPatch, whence: str
) -> None:
    before = listed.read_bytes()
    _later(monkeypatch)
    monkeypatch.setenv(prices.WHENCE, whence)
    assert not prices.refresh(wait=True)
    assert listed.read_bytes() == before
    assert prices.price("claude-sonnet-5") is not None


def test_refresh_is_tried_at_most_once_an_hour(
    listed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(tmp_path, monkeypatch, _listing(currency="USD"))
    assert not prices.refresh(wait=True)


def test_refresh_without_waiting_leaves_a_fresh_list_alone(listed: Path) -> None:
    assert not prices.refresh()


def test_a_refresh_landing_is_read_without_a_restart(
    listed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert prices.price("claude-sonnet-5") is not None
    newer = _listing()
    newer["versions"][1]["models"] = [_model("brand-new", "Brand New", input=1)]
    _source(tmp_path, monkeypatch, newer)
    _later(monkeypatch)
    assert prices.refresh(wait=True)
    assert prices.price("claude-sonnet-5") is None
    assert prices.price("brand-new") is not None


def test_a_kept_list_that_is_not_json_prices_nothing(listed: Path) -> None:
    listed.write_text("garbage", encoding="utf-8")
    assert prices.price("claude-sonnet-5") is None


def test_ready_fetches_a_missing_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(tmp_path, monkeypatch, _listing())
    assert prices.ready()
    assert prices.price("claude-sonnet-5") is not None


def test_ready_with_a_fresh_list_fetches_nothing(
    listed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(prices.WHENCE, "/nowhere/prices.json")
    assert prices.ready()


def test_ready_serves_a_stale_list_when_the_fetch_fails(
    listed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    long_ago = time.time() - 2 * prices.STALE
    os.utime(listed, (long_ago, long_ago))
    monkeypatch.setenv(prices.WHENCE, "/nowhere/prices.json")
    assert prices.ready(stopped=lambda: False)


def test_refresh_sweeps_copies_abandoned_beside_the_list(
    listed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    long_ago = time.time() - 3600
    old = listed.with_name(f".{listed.name}.abc.new")
    recent = listed.with_name(f"{listed.name}.123")
    for one in (old, recent):
        one.write_text("half", encoding="utf-8")
    os.utime(old, (long_ago, long_ago))
    _later(monkeypatch)
    assert prices.refresh(wait=True)
    assert not old.exists()
    assert recent.exists()
