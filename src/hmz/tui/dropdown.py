"""The list a value is picked out of, dropped under the row it is the value of.

What `/settings` and the forms it opens change a value with. Stepping one along with the
arrows across was the older way, and it hid what the row could be: a value nobody has seen
listed is a value nobody knows is there until they have stepped past it. So enter or a click
on the row drops every value it can take under it, the one in force ticked, and enter or a
click on one takes it -- as Textual's own `Select`, a web page's `<select>` and Charm's `huh`
select all do. Esc, or a click anywhere off the list, takes nothing.

A screen of its own rather than a widget inside the menu, so that while it is open the keys
are its own and a click off it is a click on nothing: the menu under it is still drawn, and
is what it goes back to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NamedTuple

from rich.cells import cell_len
from rich.markup import escape
from textual.binding import Binding
from textual.geometry import Offset
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

if TYPE_CHECKING:
    from collections.abc import Sequence

    from textual import events
    from textual.app import ComposeResult


__all__ = ["Dropdown", "Value", "anchor"]


class Value(NamedTuple):
    """One value a row can take, as the list dropped under it says it.

    Attributes:
      value: What picking it answers with.
      label: What it is called on the list.
      about: A few words on what it means, said quietly beside it, or "".
    """

    value: str
    label: str
    about: str = ""


#: The mark against the value in force, as every list here marks it.
_INFORCE = "✔"

#: The narrowest the list is drawn, as its stylesheet says.
_NARROWEST = 24

#: The most values shown before the list scrolls.
_TALLEST = 12


def anchor(listing: OptionList) -> Offset:
    """Where on the screen the row under a list's cursor starts, for a list dropped under it.

    Args:
      listing: The list.

    Returns:
      The row's first cell, in screen cells.
    """
    at = listing.highlighted or 0
    # Textual keeps no public map from an option to the line it starts on.
    lines = listing._index_to_line  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    line = lines.get(at, 0)
    region = listing.content_region
    return Offset(region.x, region.y + line - round(listing.scroll_offset.y))


class Dropdown(ModalScreen[str | None]):
    """Every value one row can take, dropped under it, the one in force ticked.

    Answered with the value picked, or None for none: esc, and a click off the list.
    """

    CSS = """
    Dropdown { background: transparent; }
    Dropdown > OptionList {
        width: auto; min-width: 24; max-width: 90%;
        height: auto; max-height: 14;
        border: round $primary; background: $surface; padding: 0;
        border-title-color: $primary; border-title-style: bold;
    }
    Dropdown > OptionList > .option-list--option { padding: 0 1; }
    """

    BINDINGS: ClassVar = [Binding("escape", "dismiss(None)", "cancel", show=False)]

    def __init__(
        self,
        title: str,
        values: Sequence[Value],
        current: str,
        *,
        at: Offset | None = None,
        cursor: str | None = None,
    ) -> None:
        """Initializes the list.

        Args:
          title: What the row is called, which the list is headed with.
          values: Every value it can take, in order.
          current: The one in force, which is ticked and, unless `cursor` says otherwise,
            where the cursor opens.
          at: Where the row starts on the screen, which the list is dropped under -- or
            None to put it in the middle.
          cursor: Which value the cursor opens on, where not the one in force: a switch
            opens on the other one, so that enter twice turns it round.
        """
        super().__init__()
        self._title = title
        self._values = tuple(values)
        self._current = current
        self._at = at
        self._cursor = current if cursor is None else cursor
        #: Which row is drawn in the cursor's colours, or None before any is.
        self._lit: int | None = None

    def _prompt(self, one: Value, *, here: bool) -> str:
        """One value as its row says it: its name, a tick if it is in force, what it means.

        Drawn without colours of its own on the row under the cursor, which is drawn in the
        cursor's own pair: grey words on it are words on blue.

        Args:
          one: The value.
          here: Whether the cursor is on it.

        Returns:
          The row, as markup.
        """
        tick = (
            ""
            if one.value != self._current
            else f" {_INFORCE}"
            if here
            else f" [$success]{_INFORCE}[/]"
        )
        about = (
            ""
            if not one.about
            else f"  {escape(one.about)}"
            if here
            else f"  [$text-muted]{escape(one.about)}[/]"
        )
        return f"{escape(one.label)}{tick}{about}"

    def compose(self) -> ComposeResult:
        """The values, a row apiece."""
        listing = OptionList(
            *(
                Option(self._prompt(one, here=False), id=f"={one.value}")
                for one in self._values
            )
        )
        listing.border_title = escape(self._title)
        yield listing

    def on_mount(self) -> None:
        """Opens on the value in force, dropped under the row, and inside the screen."""
        listing = self.query_one(OptionList)
        values = [one.value for one in self._values]
        listing.highlighted = (
            values.index(self._cursor) if self._cursor in values else 0
        )
        listing.focus()
        if self._at is None:
            self.styles.align = ("center", "middle")
            return
        # Under the row where there is room, and over it where there is not: a list that
        # ran off the bottom of the terminal would be values nobody can reach. And in from
        # the right edge as far as it is wide, for a value at the far end of its row.
        tall = min(len(values), _TALLEST) + 2
        wide = (
            max(
                cell_len(one.label)
                + len(_INFORCE)
                + 1
                + (cell_len(one.about) + 2 if one.about else 0)
                for one in self._values
            )
            + 4
        )
        # No narrower than the stylesheet lets it be, which is what it is drawn at.
        wide = max(wide, _NARROWEST)
        below = self._at.y + 1
        y = below if below + tall <= self.size.height else max(0, self._at.y - tall)
        x = max(0, min(self._at.x, self.size.width - wide))
        listing.styles.offset = (x, y)

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        """Draws the row under the cursor in the cursor's colours, and the rest in their own.

        Args:
          event: Where the cursor is now.
        """
        # Only the row the cursor left and the one it is on: the rest are drawn as they were.
        for at in {self._lit, event.option_index} - {None}:
            if at is not None and 0 <= at < len(self._values):
                event.option_list.replace_option_prompt_at_index(
                    at, self._prompt(self._values[at], here=at == event.option_index)
                )
        self._lit = event.option_index

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Answers with the value picked.

        Args:
          event: What was picked.
        """
        event.stop()
        self.dismiss(str(event.option.id or "").removeprefix("="))

    def on_click(self, event: events.Click) -> None:
        """Takes a click off the list as taking nothing, as a dropped list anywhere does.

        Args:
          event: The click.
        """
        if event.widget is self:
            self.dismiss(None)
