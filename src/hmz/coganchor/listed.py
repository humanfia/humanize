"""What the vendors' own pricing pages said, on the day they were read.

OpenLLMPrices is where humanize's prices come from, and it lags: a model a vendor has been
selling for months can be missing from it, and a run on that model is then a run whose dollars
cap nothing can read. This is the vendors' list prices for the models humanize drives most,
read off each vendor's pricing page and written down in the shape OpenLLMPrices publishes, so
that one reader serves both. It is consulted beside what was fetched and never instead of it:
per model the newer of the two dated lists wins, so a fetched list that has caught up replaces
every entry here.

What is written down is the standard tier only -- the short-context price, the five-minute
cache write, global rather than regional routing -- which is what the fetched list's first tier
is and what :func:`hmz.coganchor.prices.cost` takes, a floor on a longer or regional turn.

To update: read the pages in `SOURCES`, change the prices that moved, add what is new, and move
`DATE` to the day they were read.
"""

from __future__ import annotations

from typing import Any

__all__ = ["DATE", "LISTED", "SOURCES"]

#: The day the pages below were read. It dates every price here against the fetched list's
#: own date, which is how the newer of the two is told apart.
DATE = "2026-09-23"

#: Where each vendor's prices were read.
SOURCES = {
    "Anthropic": "https://platform.claude.com/docs/en/about-claude/pricing",
    "OpenAI": "https://developers.openai.com/api/docs/pricing",
}


def _model(
    provider: str, ident: str, name: str, priced: dict[str, float | None]
) -> dict[str, Any]:
    """One model, as OpenLLMPrices writes one: dollars per million tokens by category."""
    return {
        "provider": provider,
        "id": ident,
        "name": name,
        "source": {"url": SOURCES[provider]},
        "pricingItems": [
            {"category": kind, "price": price, "unit": "1M tokens"}
            for kind, price in priced.items()
            if price is not None
        ],
    }


def _categories(
    given: float, hit: float, written: float | None, out: float
) -> dict[str, float | None]:
    """The four kinds a price is given for, by the category names OpenLLMPrices uses."""
    return {
        "input_tokens": given,
        "output_tokens": out,
        "cache_read_tokens": hit,
        "cache_write_tokens": written,
    }


def _claude(ident: str, name: str, per: tuple[float, float, float, float]) -> dict[str, Any]:
    """A Claude model: base input, five-minute cache write, cache hit, output."""
    given, written, hit, out = per
    return _model("Anthropic", ident, name, _categories(given, hit, written, out))


def _gpt(ident: str, per: tuple[float, float, float | None, float]) -> dict[str, Any]:
    """An OpenAI model at short context: input, cached input, cache write, output."""
    given, hit, written, out = per
    return _model("OpenAI", ident, ident, _categories(given, hit, written, out))


#: The list, as one version of an OpenLLMPrices document.
LISTED: dict[str, Any] = {
    "currency": "USD",
    "unit": "per 1M tokens",
    "versions": [
        {
            "date": DATE,
            "models": [
                _claude("claude-fable-5.1", "Claude Fable 5.1", (10, 12.5, 0.25, 50)),
                _claude("claude-mythos-5.1", "Claude Mythos 5.1", (10, 12.5, 0.25, 50)),
                _claude("claude-fable-5", "Claude Fable 5", (10, 12.5, 1, 50)),
                _claude("claude-mythos-5", "Claude Mythos 5", (10, 12.5, 1, 50)),
                _claude("claude-opus-5.5", "Claude Opus 5.5", (4, 5, 0.2, 20)),
                _claude("claude-opus-5", "Claude Opus 5", (5, 6.25, 0.5, 25)),
                _claude("claude-opus-4.8", "Claude Opus 4.8", (5, 6.25, 0.5, 25)),
                _claude("claude-opus-4.7", "Claude Opus 4.7", (5, 6.25, 0.5, 25)),
                _claude("claude-opus-4.6", "Claude Opus 4.6", (5, 6.25, 0.5, 25)),
                _claude("claude-opus-4.5", "Claude Opus 4.5", (5, 6.25, 0.5, 25)),
                _claude("claude-opus-4.1", "Claude Opus 4.1", (15, 18.75, 1.5, 75)),
                _claude("claude-opus-4", "Claude Opus 4", (15, 18.75, 1.5, 75)),
                _claude("claude-sonnet-5", "Claude Sonnet 5", (2, 2.5, 0.2, 10)),
                _claude("claude-sonnet-4.6", "Claude Sonnet 4.6", (3, 3.75, 0.3, 15)),
                _claude("claude-sonnet-4.5", "Claude Sonnet 4.5", (3, 3.75, 0.3, 15)),
                _claude("claude-sonnet-4", "Claude Sonnet 4", (3, 3.75, 0.3, 15)),
                _claude("claude-haiku-4.5", "Claude Haiku 4.5", (1, 1.25, 0.1, 5)),
                _claude("claude-haiku-3.5", "Claude Haiku 3.5", (0.8, 1, 0.08, 4)),
                _gpt("gpt-6-astra", (10, 1, 12.5, 50)),
                _gpt("gpt-6-sol", (2, 0.2, 2.5, 10)),
                _gpt("gpt-6-luna", (0.1, 0.01, 0.125, 0.5)),
                # Promotional, "available at least through November 21, 2026".
                _gpt("gpt-5.6-sol", (4, 0.4, 5, 20)),
                _gpt("gpt-5.6-cyber", (12.5, 1.25, 15.625, 75)),
                _gpt("gpt-5.3-codex", (1.75, 0.175, None, 14)),
            ],
        }
    ],
}
