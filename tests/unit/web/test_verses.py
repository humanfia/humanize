"""`hmz.web.verses`: the flowverses a page is handed, never your own two places of flows."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from hmz.web.verses import listed


def _hmz(*names: str, fixed: tuple[str, ...] = ()) -> Any:
    """A stand-in for humanize's one object, holding a flowverse under each of `names`.

    The ones in `fixed` are always listed and cannot be removed.
    """
    held = [
        SimpleNamespace(name=one, fetched=True, fixed=one in fixed) for one in names
    ]

    def whence(one: SimpleNamespace, _: str) -> str:
        return f"https://example.com/{one.name}"

    def edited(_: SimpleNamespace) -> bool:
        return False

    verses = SimpleNamespace(
        all=lambda: held, installed=list, updates=list, whence=whence, edited=edited
    )
    return SimpleNamespace(flows=SimpleNamespace(verses=verses))


def test_this_projects_flows_and_yours_are_no_flowverse() -> None:
    hmz = _hmz(
        "official", "theirs", "local", "user", fixed=("official", "local", "user")
    )

    verses = listed(hmz)["verses"]

    assert [one["name"] for one in verses] == ["official", "theirs"]
