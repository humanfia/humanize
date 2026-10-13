"""The usage page of `/settings`: what the epics spent, by day and by flow.

As the web's Usage reads it, out of one reckoning (:func:`hmz.runtime.epic.spending`): of this
directory or of every one on this machine, looking back a few days. Nothing on it is held or
saved -- how far back and whose are how it is read -- so it has no save button.
"""

# The page is a mixin of `pick`'s, and what it shares is that module's own.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape
from textual import work
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from hmz.coganchor.prices import money
from hmz.runtime.watching.monitor import lasting, thousands

from .dropdown import Value
from .pick import _DOT, _DROPS, Action, Drop, Key, Pages, _chip, _hmz, _many, bad

if TYPE_CHECKING:
    from hmz.runtime.epic import Ran

__all__ = ["Spends"]

#: How far back the page can look, in days, picked from.
_RANGES = (7, 30, 90, 365)

#: Its two rows that are set rather than read.
_RANGE, _SCOPE = "range", "scope"

#: Whose epics: this directory's, or every directory's on this machine.
_HERE, _EVERY = "this directory", "every directory"

#: How many cells the longest day's bar takes.
_BAR = 16


def _days(count: int) -> str:
    return f"{count} days"


def _figures(one: dict[str, Any]) -> str:
    """What some epics spent besides the money: how many, output tokens, agent time."""
    return (
        f"{_many(one['runs'], 'epic')}{_DOT}"
        f"{thousands(one['output_tokens'])} output tokens{_DOT}"
        f"worked {lasting(one['seconds'])}"
    )


class Spends(Pages):
    """The usage page: the whole of what was spent, then each day's, then each flow's."""

    #: What the page says it is.
    USAGE_ABOUT = (
        "What the epics spent, as each epic says: by day, in UTC, and by flow, the "
        "costliest first."
    )

    def __init__(self) -> None:
        """Reads nothing until the page is opened."""
        super().__init__()
        self._range = 30
        self._every_spent = False
        #: What was read, for which range and scope, or None until it is.
        self._spent: dict[str, Any] | None = None
        self._spent_for: tuple[int, bool] | None = None

    def _usage_summary(self) -> str:
        """What the page's card says: how far back it looks, and how much went."""
        if self._spent is None:
            return f"last {_days(self._range)}"
        return f"{money(self._spent['whole']['cost'])} in {_days(self._range)}"

    def _usage_actions(self) -> list[Action]:
        """Nothing: the page holds nothing to save."""
        return []

    def _drops_usage(self, row: str) -> bool:
        """Whether a row is one of the two the page is read by."""
        return row in (_RANGE, _SCOPE)

    def _dropping_usage(self, row: str) -> Drop:
        """Every range, or the two scopes."""
        if row == _RANGE:
            return Drop(
                "Range",
                [Value(_days(one), _days(one)) for one in _RANGES],
                _days(self._range),
            )
        return Drop(
            "Workspace",
            [
                Value(_HERE, _HERE, "the epics run here"),
                Value(_EVERY, _EVERY, "every epic on this machine"),
            ],
            _EVERY if self._every_spent else _HERE,
        )

    def _dropped_usage(self, row: str, picked: str) -> None:
        """Reads again for the range or scope picked."""
        if row == _RANGE:
            self._range = int(picked.split(maxsplit=1)[0])
        else:
            self._every_spent = picked == _EVERY

    @work(group="usage", exclusive=True)
    async def _reads_usage(self, days: int, *, every: bool) -> None:
        """Reads what the epics spent, off the event loop: every one on the disk, maybe.

        Only the epics of those days are read: each is named for the moment it began, in UTC.
        """
        import asyncio
        import datetime

        from hmz.runtime.epic import spending

        def read() -> dict[str, Any]:
            epics = _hmz().epics
            now = datetime.datetime.now(datetime.UTC)
            since = (now - datetime.timedelta(days=days - 1)).strftime("%Y%m%d")
            found = [
                one
                for one in (epics.every() if every else epics.all())
                if one.name >= since
            ]
            ran: list[Ran] = [one for one in map(epics.read, found) if one]
            return spending(ran, days, now)

        try:
            said = await asyncio.to_thread(read)
        except OSError as why:
            said = None
            self._said = bad(escape(str(why)))
        if (days, every) == self._spent_for:
            self._spent = said
            self._fill()

    def _usage_rows(self) -> list[tuple[str, str, str, str]]:
        """The page's rows as `(id, name, value or "", about)`, a heading's id "".

        The two it is read by, set with a value; then the whole, each day with an epic in it,
        newest first, with a bar as long as its share of the costliest day, and each flow.
        """
        rows = [
            (_RANGE, "Range", _days(self._range), "how far back, counting today"),
            (
                _SCOPE,
                "Workspace",
                _EVERY if self._every_spent else _HERE,
                "this directory's epics, or every directory's",
            ),
        ]
        spent = self._spent
        if spent is None or not spent["whole"]["runs"]:
            return rows
        whole = spent["whole"]
        ended = ", ".join(f"{count} {how}" for how, count in spent["ended"].items())
        rows += [
            ("", "Spent", "", ""),
            ("whole", money(whole["cost"]), "", f"{_figures(whole)}{_DOT}{ended}"),
            ("", "By day", "", ""),
        ]
        top = max(one["cost"] for one in spent["days"]) or 1.0
        for one in reversed(spent["days"]):
            if one["runs"]:
                bar = "█" * max(bool(one["cost"]), round(_BAR * one["cost"] / top))
                rows.append(
                    (
                        f"day:{one['day']}",
                        one["day"],
                        "",
                        (
                            f"{bar}{' ' if bar else ''}{money(one['cost'])}{_DOT}"
                            f"{_figures(one)}"
                        ),
                    )
                )
        rows.append(("", "By flow", "", ""))
        total = whole["cost"] or 1.0
        rows += [
            (
                f"flow:{one['flow']}",
                one["flow"] or "unknown",
                "",
                (
                    f"{money(one['cost'])}{_DOT}{one['cost'] / total:.0%}{_DOT}"
                    f"{_figures(one)}"
                ),
            )
            for one in spent["flows"]
        ]
        return rows

    def _fill_usage(self) -> None:
        """Puts the page up, reading it again where the range or the scope moved."""
        if self._spent_for != (self._range, self._every_spent):
            self._spent, self._said = None, ""
            self._spent_for = (self._range, self._every_spent)
            self._reads_usage(self._range, every=self._every_spent)
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        rows = self._usage_rows()
        landing = self._lands([held for held, *_ in rows if held])
        options: list[Option] = []
        for held, named, value, about in rows:
            here = held == landing
            if not held:
                options.append(Option("", disabled=True))
                options.append(Option(f" [$primary]{escape(named)}[/]", disabled=True))
            elif value:
                chip = _chip(value, _DROPS, here=here)
                options.append(
                    Option(self._setting(named, chip, about, here=here), id=f"={held}")
                )
            else:
                options.append(
                    Option(
                        self._row(0, named, about, here=here, inforce=False),
                        id=f"={held}",
                    )
                )
        self._put(listing, options, landing)
        self._drawn = listing.highlighted
        said = self._said
        if not said and self._spent is None:
            said = "reading…"
        elif not said and len(rows) == 2:  # noqa: PLR2004 -- the range and the scope alone
            said = f"no epic {'on this machine' if self._every_spent else 'here'} in these days"
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        keys = (Key("enter", "choose"),) if self._drops_usage(landing) else ()
        self._footed(*keys, Key("esc", "back"))
