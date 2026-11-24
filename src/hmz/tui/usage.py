"""The usage page of `/settings`: what the epics spent, by day and by flow.

As the web's Usage reads it, out of one reckoning (:func:`hmz.runtime.epic.spending`): of this
directory or of every one on this machine, looking back a few days. Nothing on it is held or
saved -- how far back and whose are how it is read -- so it has no save button.

Its texts are the web page's (:mod:`hmz.words`), and its rows are laid out by the cells they
take rather than the letters they are, so that a language whose letters are two cells wide
keeps the column of values a column.
"""

# The page is a mixin of `pick`'s, and what it shares is that module's own.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, Any

from rich.cells import cell_len
from rich.markup import escape
from textual import work
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from hmz.coganchor.prices import money
from hmz.runtime.watching.monitor import lasting, thousands
from hmz.words import t

from . import humanfia
from .dropdown import Value
from .pick import _DOT, _DROPS, Action, Drop, Key, Pages, _chip, _hmz, _shade, bad

if TYPE_CHECKING:
    from hmz.runtime.epic import Ran

__all__ = ["Spends"]

#: How far back the page can look, in days, picked from.
_RANGES = (7, 30, 90, 365)

#: Its two rows that are set rather than read.
_RANGE, _SCOPE = "range", "scope"

#: Whose epics: this directory's, or every directory's on this machine.
_HERE, _EVERY = "here", "every"

#: How many cells the longest day's bar takes.
_BAR = 16

#: How wide the names of things listed are drawn, before what is said about each.
_LABEL = 18


def _wrapped(said: str, room: int) -> list[str]:
    """Words broken into lines of at most `room` cells, or near it.

    `textwrap` counts letters, so the room is given to it in letters of the width these are
    on the whole: half as many of a script whose letters take two cells.
    """
    letters = room * len(said) // max(cell_len(said), 1)
    return textwrap.wrap(said, max(letters, 8), break_on_hyphens=False)


def _days(count: int) -> str:
    return t("{n}d", n=count)


def _whose(*, every: bool) -> str:
    return t("Every folder") if every else t("This folder")


def _figures(one: dict[str, Any]) -> str:
    """What some epics spent besides the money: how many, output tokens, agent time."""
    return (
        f"{t('over {n} epics', n=one['runs'])}{_DOT}"
        f"{thousands(one['output_tokens'])} {t('output tokens')}{_DOT}"
        f"{lasting(one['seconds'])} {t('agent time')}"
    )


class Spends(Pages):
    """The usage page: the whole of what was spent, then each day's, then each flow's."""

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
            return _days(self._range)
        return f"{money(self._spent['whole']['cost'])}{_DOT}{_days(self._range)}"

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
                t("Range"),
                [Value(str(one), _days(one)) for one in _RANGES],
                str(self._range),
            )
        return Drop(
            t("Folder"),
            [
                Value(_HERE, _whose(every=False)),
                Value(_EVERY, _whose(every=True)),
            ],
            _EVERY if self._every_spent else _HERE,
        )

    def _dropped_usage(self, row: str, picked: str) -> None:
        """Reads again for the range or scope picked."""
        if row == _RANGE:
            self._range = int(picked)
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
            (_RANGE, t("Range"), _days(self._range), t("How far back")),
            (_SCOPE, t("Folder"), _whose(every=self._every_spent), ""),
        ]
        spent = self._spent
        if spent is None or not spent["whole"]["runs"]:
            return rows
        whole = spent["whole"]
        ended = ", ".join(f"{count} {how}" for how, count in spent["ended"].items())
        rows += [
            ("", t("Spent"), "", ""),
            ("whole", money(whole["cost"]), "", f"{_figures(whole)}{_DOT}{ended}"),
            ("", t("Cost by day"), "", ""),
        ]
        top = max(one["cost"] for one in spent["days"]) or 1.0
        for one in reversed(spent["days"]):
            if one["runs"]:
                bar = humanfia.BLOCK * max(
                    bool(one["cost"]), round(_BAR * one["cost"] / top)
                )
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
        rows.append(("", t("By flow"), "", ""))
        total = whole["cost"] or 1.0
        rows += [
            (
                f"flow:{one['flow']}",
                one["flow"] or t("unknown"),
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
                options.append(self._heading(named))
            elif value:
                said, cells = _chip(value, _DROPS, here=here)
                # Counted there in letters: a value two cells a letter is as much wider.
                chip = (said, cells + cell_len(value) - len(value))
                options.append(
                    Option(self._set_to(named, chip, about, here=here), id=f"={held}")
                )
            else:
                options.append(
                    Option(self._listed(named, about, here=here), id=f"={held}")
                )
        self._put(listing, options, landing)
        self._drawn = listing.highlighted
        said = self._said
        if not said and self._spent is None:
            said = t("Reading what the epics spent…")
        elif not said and len(rows) == 2:  # noqa: PLR2004 -- the range and the scope alone
            said = t("Nothing ran in this range.")
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        keys = (Key("enter", t("Choose")),) if self._drops_usage(landing) else ()
        self._footed(*keys, Key("esc", t("Back")))

    # -- Drawing a row, by the cells it takes --------------------------------------------------

    def _across(self) -> int:
        """How many cells across the list has to lay its rows out in."""
        return self._width_of(self.query_one("#choices", OptionList))

    def _heading(self, said: str) -> Option:
        """A heading the arrows step over: its words in capitals, ruled out to the far end."""
        title = said.upper()
        rule = humanfia.RULE * max(self._across() - cell_len(title) - 3, 0)
        return Option(
            f" [b $text-muted]{escape(title)}[/] [$hmz-line-strong]{rule}[/]",
            disabled=True,
        )

    def _set_to(
        self,
        named: str,
        chip: tuple[str, int],
        about: str,
        *,
        here: bool,
        note: str = "",
    ) -> str:
        """One row that is set to something: its name, its value at the far end, what it is.

        Args:
          named: What it is called.
          chip: What it is set to, as markup, and how many cells that takes.
          about: The line about it, unescaped, or "" for none.
          here: Whether the cursor is on it, which is the row its values are dropped under.
          note: What is said after the line about it, in the colour of a warning, or "".

        Returns:
          The row, as markup.
        """
        width = self._across()
        said, cells = chip
        pad = max(2, width - 2 - cell_len(named) - cells)
        if here:
            self._values_at = 1 + cell_len(named) + pad
        first = f" [b]{escape(named)}[/]{' ' * pad}{said}"
        if not (about or note):
            return first
        lines = _wrapped(about, max(width - 4, 20))
        under = [f"   {_shade('$text-muted', line, here=here)}" for line in lines]
        if note:
            noted = _shade("$warning", note, here=here)
            under = (
                [*under[:-1], f"{under[-1]}{_DOT}{noted}"] if under else [f"   {noted}"]
            )
        return "\n".join([first, *under])

    def _listed(
        self, named: str, about: str, *, here: bool, mark: str = "", tail: str = ""
    ) -> str:
        """One thing on a list: a mark, its name, what is said of it, and a word at the far end.

        Args:
          named: What it is called.
          about: What is said of it, unescaped; "" for nothing.
          here: Whether the cursor is on it.
          mark: What stands before its name, as markup one cell wide; "" for a space.
          tail: What stands at the far end, unescaped; "" for nothing.

        Returns:
          The row, as markup.
        """
        width = self._across()
        gap = " " * max(1, _LABEL - cell_len(named))
        used = 3 + cell_len(named) + len(gap)
        room = max(width - used - (cell_len(tail) + 2 if tail else 0) - 1, 16)
        lines = _wrapped(about, room) or [""]
        last = ""
        if tail:
            fill = " " * max(2, width - used - cell_len(lines[0]) - cell_len(tail) - 1)
            last = f"{fill}{_shade('$text-muted', tail, here=here)}"
        said = f"\n{' ' * used}".join(
            _shade("$text-muted", line, here=here) + (last if at == 0 else "")
            for at, line in enumerate(lines)
        )
        return f" {mark or ' '} [b]{escape(named)}[/]{gap}{said}"
