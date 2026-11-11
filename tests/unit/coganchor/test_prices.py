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
        (float("nan"), "$?"),
        (float("inf"), "$?"),
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


def _in_yuan(**overrides: Any) -> dict[str, Any]:
    """The listing with a model priced in yuan, the first input item of it in dollars."""
    listing = _listing(**overrides)
    listing["versions"][1]["models"].append(
        {
            "id": "glm-5.3",
            "name": "GLM-5.3",
            "provider": "zhipu",
            "pricingItems": [
                {"category": "input_tokens", "price": 8, "currency": "CNY"},
                {"category": "input_tokens", "price": 1.5},
                {"category": "output_tokens", "price": 28, "currency": "CNY"},
            ],
        }
    )
    listing["versions"][1]["models"].append(
        {
            "id": "yuan-only",
            "pricingItems": [
                {"category": "output_tokens", "price": 4, "currency": "CNY"}
            ],
        }
    )
    return listing


def test_a_price_in_yuan_is_turned_into_dollars_at_the_lists_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(
        tmp_path, monkeypatch, _in_yuan(exchangeRate={"pair": "USD/CNY", "usdCny": 8})
    )
    assert prices.refresh(wait=True)
    priced = prices.price("glm-5.3")
    assert priced is not None
    assert priced.per_million == {"input": 1.0, "output": 3.5}
    yuan = prices.price("yuan-only")
    assert yuan is not None
    assert yuan.per_million == {"output": 0.5}
    # An item that names no currency is in dollars.
    sonnet = prices.price("claude-sonnet-5")
    assert sonnet is not None
    assert sonnet.per_million["input"] == 3.0


@pytest.mark.parametrize(
    "rate",
    [
        None,
        {"pair": "USD/EUR", "usdCny": 8},
        {"pair": "USD/CNY", "usdCny": 0},
        {"pair": "USD/CNY", "usdCny": -8},
        {"pair": "USD/CNY", "usdCny": float("nan")},
        {"pair": "USD/CNY", "usdCny": True},
        {"pair": "USD/CNY", "usdCny": "8"},
        {"pair": "USD/CNY"},
        "8",
    ],
)
def test_a_price_in_yuan_without_a_usable_rate_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rate: object
) -> None:
    said = _in_yuan() if rate is None else _in_yuan(exchangeRate=rate)
    _source(tmp_path, monkeypatch, said)
    assert prices.refresh(wait=True)
    priced = prices.price("glm-5.3")
    assert priced is not None
    # The dollar item behind it is taken instead; the yuan never lands as dollars.
    assert priced.per_million == {"input": 1.5}
    assert prices.price("yuan-only") is None


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


def _bad(rate: str) -> str:
    """A listing whose one odd model is priced at `rate`, as JSON spells it."""
    listing = _listing()
    listing["versions"][1]["models"].append(
        _model("bad-model", "Bad Model", output=12345)
    )
    return json.dumps(listing).replace("12345", rate)


@pytest.mark.parametrize(
    "rate", ["NaN", "Infinity", "-Infinity", "1e400", "1" + "0" * 400]
)
def test_a_fetched_price_that_is_not_a_number_refuses_every_price(
    listed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rate: str
) -> None:
    before = listed.read_bytes()
    source = _source(tmp_path, monkeypatch, None)
    source.write_text(_bad(rate), encoding="utf-8")
    _later(monkeypatch)
    assert not prices.refresh(wait=True)
    assert listed.read_bytes() == before  # not kept over a list of numbers
    for model in ("bad-model", "claude-sonnet-5", "never-heard-of-it"):
        with pytest.raises(prices.PriceError, match=r"bad-model's output.*HUMANIZE_"):
            prices.cost({"output": 1000}, model)
    with pytest.raises(prices.PriceError):
        prices.ready()


def test_a_fetch_of_a_good_list_lifts_the_refusal_within_the_hour(
    listed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch, None)
    source.write_text(_bad("NaN"), encoding="utf-8")
    _later(monkeypatch)
    prices.refresh(wait=True)
    _source(tmp_path, monkeypatch, _listing())
    assert prices.refresh(wait=True)
    assert prices.cost({"output": 1_000_000}, "claude-sonnet-5") == 15


def test_a_refusal_is_of_its_source_alone(
    listed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch, None)
    source.write_text(_bad("NaN"), encoding="utf-8")
    _later(monkeypatch)
    prices.refresh(wait=True)
    monkeypatch.setenv(prices.WHENCE, "off")
    assert prices.price("claude-sonnet-5") is not None


def test_a_kept_price_that_is_not_a_number_refuses_every_price(listed: Path) -> None:
    kept = json.loads(listed.read_text(encoding="utf-8"))
    kept["models"]["claude-opus-5"]["per_million"]["output"] = float("nan")
    listed.write_text(json.dumps(kept), encoding="utf-8")
    with pytest.raises(prices.PriceError, match=r"kept at .*claude-opus-5.*delete it"):
        prices.price("claude-sonnet-5")


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


def _written(price: float, duration: str | None) -> dict[str, Any]:
    return {
        "category": "cache_write_tokens",
        "price": price,
        "conditions": {"contextRange": "all", "cacheDuration": duration},
    }


def _with_hours(*writes: dict[str, Any]) -> dict[str, Any]:
    """The listing with a model sold two cache writes, five-minute and one-hour (#553)."""
    listing = _listing()
    listing["versions"][1]["models"].append(
        {
            "id": "claude-opus-5-5",
            "pricingItems": [
                {"category": "input_tokens", "price": 4},
                *writes,
                {"category": "cache_read_tokens", "price": 0.2},
                {"category": "output_tokens", "price": 20},
            ],
        }
    )
    return listing


@pytest.mark.parametrize(
    "writes",
    [
        (_written(5, "5m"), _written(8, "1h")),
        (_written(8, "1h"), _written(5, "5m")),
    ],
)
def test_a_one_hour_cache_write_is_kept_beside_the_five_minute_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writes: tuple[dict[str, Any], ...]
) -> None:
    _source(tmp_path, monkeypatch, _with_hours(*writes))
    assert prices.refresh(wait=True)
    priced = prices.price("claude-opus-5-5")
    assert priced is not None
    assert priced.per_million == {
        "input": 4.0,
        "cache_write": 5.0,
        "cache_write_1h": 8.0,
        "cache_read": 0.2,
        "output": 20.0,
    }
    # The issue's row: 100,000 tokens written to the one-hour cache, at list price.
    usage = {"input": 6.0, "output": 500.0, "cache_write": 100_000.0}
    assert prices.cost(usage, "claude-opus-5-5", hour=100_000) == pytest.approx(
        0.810024
    )
    # Counted as five-minute writes where nobody says otherwise, as before.
    assert prices.cost(usage, "claude-opus-5-5") == pytest.approx(0.510024)
    # Writes counted in an earlier reckoning and only now said to be one-hour ones: what
    # they cost beyond the five-minute price they were counted at.
    assert prices.cost({}, "claude-opus-5-5", hour=100_000) == pytest.approx(0.3)


def test_one_hour_writes_of_a_model_without_a_one_hour_price_cost_a_cache_write(
    listed: Path,
) -> None:
    usage = {"cache_write": 1_000_000.0}
    assert prices.cost(usage, "claude-sonnet-5", hour=1_000_000) == pytest.approx(3.75)


def test_a_one_hour_price_that_is_not_a_number_refuses_every_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch, None)
    listing = _with_hours(_written(5, "5m"), _written(12345, "1h"))
    source.write_text(json.dumps(listing).replace("12345", "NaN"), encoding="utf-8")
    assert not prices.refresh(wait=True)
    with pytest.raises(prices.PriceError, match=r"cache_write_1h"):
        prices.cost({"input": 1000}, "claude-sonnet-5")


def _ranged(
    kind: str, price: float, within: str, currency: str = "USD"
) -> dict[str, Any]:
    return {
        "category": f"{kind}_tokens",
        "price": price,
        "currency": currency,
        "conditions": {"contextRange": within, "cacheDuration": None},
    }


def _with_tiers(*models: dict[str, Any]) -> dict[str, Any]:
    """The listing with models priced higher past a long-context line (#554)."""
    listing = _listing(exchangeRate={"pair": "USD/CNY", "usdCny": 5.0})
    listing["versions"][1]["models"].extend(models)
    return listing


#: Priced the way the list prices GPT-6 Astra: a request past 272k tokens of prompt is
#: priced at the dearer tier for the whole of it.
_LONG = {
    "id": "long-1",
    "pricingItems": [
        _ranged("input", 2, "input <= 272k tokens"),
        _ranged("cache_read", 0.1, "input <= 272k tokens"),
        _ranged("output", 10, "input <= 272k tokens"),
        _ranged("input", 4, "input > 272k tokens"),
        _ranged("cache_read", 0.2, "input > 272k tokens"),
        _ranged("output", 15, "input > 272k tokens"),
    ],
}


@pytest.fixture
def tiered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _source(
        tmp_path,
        monkeypatch,
        _with_tiers(
            _LONG,
            {
                "id": "stepped-1",
                "pricingItems": [
                    _ranged("input", 1, "input < 32k tokens", "CNY"),
                    _ranged("input", 2, "input >= 32k tokens", "CNY"),
                    _ranged("output", 4, "input <= 32k tokens"),
                    _ranged("output", 5, "32k < input <= 128k tokens"),
                    _ranged("output", 6, "128K < input <= 256k tokens"),
                    _ranged("output", 7, "256k < prompt <= 1M tokens"),
                    _ranged("output", 8, "prompt > 1.5M tokens"),
                    _ranged("output", 9, "input > some tokens"),
                ],
            },
        ),
    )
    assert prices.refresh(wait=True)
    return prices.where()


def test_each_long_context_tier_is_kept_by_the_line_it_is_above(tiered: Path) -> None:
    priced = prices.price("stepped-1")
    assert priced is not None
    # The standard price is `per_million`, whatever order the list gives the tiers in.
    assert priced.per_million == {"input": 0.2, "output": 4.0}
    assert priced.tiers == {
        31_999: {"input": 0.4},
        32_000: {"output": 5.0},
        128_000: {"output": 6.0},
        256_000: {"output": 7.0},
        1_500_000: {"output": 8.0},
    }
    kept = json.loads(tiered.read_text(encoding="utf-8"))["models"]
    assert kept["long-1"]["per_million"] == {
        "input": 2.0,
        "cache_read": 0.1,
        "output": 10.0,
    }
    assert kept["long-1"]["tiers"] == {
        "272000": {"input": 4.0, "cache_read": 0.2, "output": 15.0}
    }
    # A model with no tier is kept in the shape it always was.
    assert "tiers" not in kept["claude-opus-5"]


@pytest.mark.parametrize(
    ("prompt", "line"),
    [(271_999, 0), (272_000, 0), (272_001, 272_000)],
)
def test_a_request_is_tiered_by_how_long_its_prompt_was(
    tiered: Path, prompt: int, line: int
) -> None:
    request = {"input": 1.0, "cache_read": prompt - 1.0, "output": 10.0}
    expected = {
        f"input>{line}": 1.0,
        f"cache_read>{line}": prompt - 1.0,
        f"output>{line}": 10.0,
    }
    assert prices.tiered(request, "long-1") == (expected if line else {})


def test_the_highest_line_a_prompt_is_past_is_its_tier(tiered: Path) -> None:
    assert prices.tiered({"input": 200_000.0, "output": 1.0}, "stepped-1") == {
        "input>128000": 200_000.0,
        "output>128000": 1.0,
    }
    assert prices.tiered({"input": 1e9}, "unlisted") == {}
    assert prices.tiered({"input": 1e9}, "claude-opus-5") == {}


def test_a_request_past_the_line_is_priced_at_its_tier_and_a_total_is_not(
    tiered: Path,
) -> None:
    # One request of 300k tokens of prompt costs what the list says past the line.
    one = {"input": 300_000.0, "output": 1000.0}
    marked = prices.tiered(one, "long-1")
    assert prices.cost(one, "long-1", tiered=marked) == pytest.approx(
        0.3 * 4 + 0.001 * 15
    )
    # Two of 150k each, the same tokens added up, are both under it.
    assert prices.tiered({"input": 150_000.0, "output": 500.0}, "long-1") == {}
    assert prices.cost(one, "long-1") == pytest.approx(0.3 * 2 + 0.001 * 10)


def test_a_tier_that_does_not_price_a_kind_leaves_it_at_the_standard_price(
    tiered: Path,
) -> None:
    usage = {"input": 1_000_000.0, "output": 1_000_000.0}
    # `stepped-1` past 31,999 prices input alone: its output there is the standard price.
    marked = {"input>31999": 1_000_000.0, "output>31999": 1_000_000.0, "odd": 1.0}
    assert prices.cost(usage, "stepped-1", tiered=marked) == pytest.approx(0.4 + 4)


def test_a_tier_price_that_is_not_a_number_refuses_every_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch, None)
    listing = _with_tiers(
        {
            "id": "long-2",
            "pricingItems": [
                _ranged("input", 2, "input <= 272k tokens"),
                _ranged("input", 12345, "input > 272k tokens"),
            ],
        }
    )
    source.write_text(json.dumps(listing).replace("12345", "NaN"), encoding="utf-8")
    assert not prices.refresh(wait=True)
    with pytest.raises(prices.PriceError, match=r"long-2"):
        prices.cost({"input": 1000}, "claude-sonnet-5")


def test_a_kept_tier_that_is_not_a_number_refuses_every_price(tiered: Path) -> None:
    kept = json.loads(tiered.read_text(encoding="utf-8"))
    kept["models"]["long-1"]["tiers"]["272000"]["input"] = 12345
    tiered.write_text(json.dumps(kept).replace("12345", "Infinity"), encoding="utf-8")
    os.utime(tiered, (time.time() + 5, time.time() + 5))
    with pytest.raises(prices.PriceError, match=r"long-1"):
        prices.price("long-1")
