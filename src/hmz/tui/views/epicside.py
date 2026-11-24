"""Epic: the epic that is open, beside its log -- its details, board, people and side questions.

The panel the web page draws beside an epic (`src/hmz/web/static/views/epic.js`), in the
context zone, with the page's four tabs. **Details** is how the epic stands: its flow and
task, what runs each role, and its budget against what has gone. **Board** is the handful of
named lines the flow and a person both write: read, added, changed and removed. **People** is
who holds each role a person fills, and whether anybody is there for it. **Side questions**
are asked beside the epic rather than of it, each of one session's read-only copy.

`left` and `right`, or `1` to `4`, turn the tabs; what each tab does besides is on the hint
line while the view has the keys. The tab that was open and the row its cursor was on are
kept for as long as the interface is, so that leaving the view and coming back finds it as
it was left.

What it draws is what the monitor draws its page of the epic from, and what it changes it
asks the runs to change, as `/afk`, `/claim` and the monitor's board do; side questions are
the daemon's (`btw.*`), as the page's are.
"""

# The pieces it opens are every sheet's own.
# pyright: reportPrivateUsage=false
# And the view is the interface's own: it reads what the monitor is drawn from.
# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast
from weakref import WeakKeyDictionary

from rich.markup import escape
from textual import on, work
from textual.actions import SkipAction
from textual.containers import Vertical
from textual.content import Content
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from hmz.coganchor.agents import FLOW
from hmz.tui import humanfia
from hmz.tui.dropdown import Value
from hmz.tui.monitoring import BoardSeen, Entry, details
from hmz.tui.pick import (
    _APART_MARK,
    _STEPS,
    LOCAL_DAEMON,
    Action,
    Drop,
    Form,
    Popup,
    Question,
    _popup,
    _rpc,
    chatting,
)
from hmz.tui.shell import View, hinting
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from textual import events
    from textual.app import App, ComposeResult

    from hmz.tui.app import Humanize

__all__ = ["TABS", "VIEWS", "Epic", "Kept", "People", "Side"]

#: The tabs, in the page's order, by what the page calls each.
TABS = ("Details", "Board", "People", "Side questions")
_DETAILS, _BOARD, _PEOPLE, _ASIDES = range(4)

#: How often what is drawn is read again, in seconds: an epic is read while it runs.
_LIVE = 0.5

#: How often the side questions are asked of the daemon again, in seconds.
_WATCHED = 1.0

#: The letters a tab takes, each as the hint line names it.
_LETTERS = ("a", "d", "w")

#: What a call of the daemon raises where it was not reached or refused it.
_FAILS = (LookupError, OSError, RuntimeError, ValueError)

#: What the headings of the monitor's page of an epic are called on the web page's panel.
_HEADINGS = {"Set up": "Setup"}

type Sections = list[tuple[str, list[tuple[str, str]]]]
"""What Details says: each heading, and under it each field with its value as markup."""


class People(NamedTuple):
    """The roles a person fills, and who is there for each.

    Attributes:
      roles: The roles, in the order the flow declares them.
      claims: The frontend holding each role held, by role.
      me: This frontend, as the runs name it.
      names: What each frontend is called, by the name the runs give it.
      away: Whether nobody is there for any role.
      away_of: Whether nobody is there for one role, where that was said of it alone.
    """

    roles: Sequence[str] = ()
    claims: Mapping[str, str] = {}
    me: str = ""
    names: Mapping[str, str] = {}
    away: bool = False
    away_of: Mapping[str, bool] = {}


@dataclass(frozen=True)
class Epic:
    """What the view reads of the epic that is open, and what it asks to change it by.

    Attributes:
      details: How the epic stands, heading by heading; nothing where no epic is open.
      state: `running`, `stopping`, or "" once it is over.
      named: The epic's name, as it is written down, or "" before it is.
      board: Its board, or None for a flow that keeps none.
      people: The roles a person fills, and who holds each.
      sessions: Every conversation of the epic, as `<agent>/<n>`: what a side question is
        asked of.
      asks: Asks the runs one thing: `claim`, `release` or `afk`, and what that takes.
      daemon: One call of the daemon that holds the epic: the method, and what it takes.
      workspace: The workspace the epic runs in, as the daemon names it.
    """

    details: Callable[[], Sections]
    state: Callable[[], str]
    named: Callable[[], str]
    board: Callable[[], BoardSeen | None]
    people: Callable[[], People]
    sessions: Callable[[], Sequence[str]]
    asks: Callable[..., None]
    daemon: Callable[[str, Mapping[str, Any]], Any]
    workspace: Callable[[], str]


@dataclass
class Kept:
    """Where the view was left: the tab open, and the row each tab's cursor was on."""

    tab: int = 0
    cursors: dict[int, str] = field(default_factory=dict[int, str])


class _Removes(Popup):
    """Whether to take something away, asked before it goes."""

    CSS = _popup("_Removes")
    PRIMARY: ClassVar = "no"

    def __init__(self, asked: str, about: str, yes: str) -> None:
        """Asks about one thing.

        Args:
          asked: The question, naming what goes.
          about: What taking it away comes to.
          yes: What the answer that takes it away is called.
        """
        super().__init__()
        self.asked = asked
        self.about = about
        self._yes = yes

    def rows(self) -> list[tuple[str, str, str]]:
        """Taking it away, or leaving it."""
        return [("yes", self._yes, ""), ("no", t("Cancel"), "")]


#: The rows of the form a side question is asked on.
_TO = f"{_APART_MARK}to"
_QUESTION = f"{_APART_MARK}question"


class _Asking(Form[tuple[str, str]]):
    """A side question, written: which session it is asked of, and what is asked."""

    def __init__(self, sessions: Sequence[str], to: str = "") -> None:
        """Opens the question.

        Args:
          sessions: The sessions there are to ask, as `<agent>/<n>`.
          to: The session a side conversation already open asks, or "" to pick one.
        """
        super().__init__()
        self._sessions = list(sessions)
        self._fixed = bool(to)
        self._typed_in = {_TO: to, _QUESTION: ""}

    def _ask(self) -> None:
        """Says what a side question is."""
        self.query_one("#asked", Label).update(t("Side question"))
        self.query_one("#about", Label).update(
            t(
                "A read-only copy of the chosen harness session answers this, and it "
                "never reaches the epic."
            )
        )
        self._fill()

    def asked(self) -> list[Question]:
        """Whom to ask, where that is still to pick, and the question."""
        typed = self._typed_in
        rows = [
            Question(
                _QUESTION,
                t("Side question"),
                t("Ask about the epic"),
                needed=not typed[_QUESTION].strip(),
            )
        ]
        if not self._fixed:
            rows.insert(
                0,
                Question(
                    _TO,
                    t("Ask it of"),
                    t("Pick a conversation"),
                    _STEPS,
                    not typed[_TO],
                ),
            )
        return rows

    def choices(self, held: str) -> Sequence[str]:
        """The sessions there are to ask."""
        return self._sessions if held == _TO else ()

    def dropping(self, row: str) -> Drop:
        """Every session, the newest first."""
        del row  # the one row that drops
        return Drop(
            t("Ask it of"),
            [Value(one, one) for one in reversed(self._sessions)],
            self._typed_in[_TO],
        )

    def lines(self, held: str) -> bool:
        """The question may run to several lines."""
        return held == _QUESTION

    def actions(self) -> list[Action]:
        """Asking it."""
        return [Action("done", t("Ask"), "", self.action_done, variant="primary")]

    def _holding(self) -> bool:
        """A question not asked is not a change to keep."""
        return False

    def action_done(self) -> None:
        """Asks, or says what is still to be said."""
        if self._editing:
            self._keeps_writing()
        to, question = self._typed_in[_TO], self._typed_in[_QUESTION].strip()
        if not to:
            self._wrong = t("Pick the conversation to ask first.")
        elif not question:
            self._wrong = t("Ask a side question")
        else:
            self.dismiss((to, question))
            return
        self._fill()


class _Tabs(Static):
    """The tabs across the top of the view: a click on one turns to it."""

    def on_click(self, event: events.Click) -> None:
        """Turns to the tab clicked."""
        side = self.parent
        if isinstance(side, Side):
            side.turns_at(event.x)


class _Row(NamedTuple):
    """One row of a tab: what it is known by, what it says, and whether the cursor lands on it."""

    held: str
    said: str
    lands: bool = True


class Side(Vertical, can_focus=True, can_focus_children=False):
    """The epic that is open, in four tabs: Details, Board, People and Side questions."""

    DEFAULT_CSS = """
    Side { height: 1fr; }
    Side > _Tabs { height: auto; padding: 0 1; color: $text-muted; }
    Side > .side-rule { height: 1; color: $hmz-line; }
    Side > OptionList {
        height: 1fr; border: none; padding: 0; background: $surface;
        scrollbar-size: 1 1; }
    Side > OptionList > .option-list--option { padding: 0 1; }
    Side > OptionList > .option-list--option-highlighted {
        background: $block-cursor-blurred-background;
        color: $block-cursor-blurred-foreground; text-style: none; }
    Side:focus > OptionList > .option-list--option-highlighted {
        background: $block-cursor-background; color: $block-cursor-foreground;
        text-style: bold; }
    Side > .side-note { height: auto; padding: 0 1; color: $text-muted; }
    """

    def __init__(self, epic: Epic, kept: Kept | None = None) -> None:
        """Opens the view on an epic.

        Args:
          epic: What it reads of the epic, and what it asks to change it by.
          kept: Where it was left, which it opens on and keeps up to date, or None to open
            on the first tab.
        """
        super().__init__()
        self._epic = epic
        self._kept = kept if kept is not None else Kept()
        #: The side conversations, as `btw.list` last answered them.
        self._asides: list[dict[str, Any]] = []
        #: The questions asked from here and not answered yet, by side conversation.
        self._asking: dict[str, tuple[str, str]] = {}
        #: What became of the last thing done, said under the list until the tab is left.
        self._said = ""
        #: The rows as last drawn, and where each tab's starts are on the tab strip.
        self._rows: list[_Row] = []
        self._starts: list[int] = []
        #: The tab the rows drawn are of, or None before any is.
        self._drawn: int | None = None
        #: When the side questions were last read, by this machine's clock.
        self._read_at = 0.0

    @property
    def tab(self) -> int:
        """The tab that is open, counting from zero."""
        return self._kept.tab

    def compose(self) -> ComposeResult:
        """The tabs, a rule, the rows of the tab that is open, and what is said of it."""
        yield _Tabs()
        yield Static(classes="side-rule")
        yield OptionList()
        yield Static(classes="side-note")

    def on_mount(self) -> None:
        """Draws the tab it was left on, and keeps drawing it as the epic goes."""
        self._draws()
        if self.tab == _ASIDES:
            self._reads()
        self.set_interval(_LIVE, self._ticks)

    def on_resize(self, event: events.Resize) -> None:
        """Rules under the tabs across however wide the zone is now."""
        self.query_one(".side-rule", Static).update(humanfia.RULE * event.size.width)
        self._draws()

    def on_focus(self) -> None:
        """Says this tab's keys on the hint line, now that the view has them."""
        self.call_after_refresh(self._hints)

    def _interface(self) -> App[None]:
        """The interface the view is part of."""
        return cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )

    # -- The keys -------------------------------------------------------------------------------

    def hint_keys(self) -> list[tuple[str, str]]:
        """Every key the tab that is open takes, each with what it does there now."""
        pairs = [("←→", "Tab"), ("↑↓", "Move")]
        row = self._under()
        if self.tab == _BOARD and self._epic.board() is not None:
            if row:
                pairs += [("enter", "Edit"), ("d", "Remove")]
            pairs.append(("a", "Add"))
        elif self.tab == _PEOPLE and row:
            people = self._epic.people()
            holder = people.claims.get(row)
            pairs += [
                (
                    "enter",
                    "Release"
                    if holder == people.me
                    else "Take over"
                    if holder
                    else "Claim",
                ),
                ("w", "Back@@present" if self._away(people, row) else "Away"),
                ("shift+w", "Back for all" if people.away else "Away for all"),
            ]
        elif self.tab == _ASIDES and self._going():
            if row:
                pairs += [("enter", "Ask"), ("d", "Close")]
            pairs.append(("a", "New aside"))
        return pairs

    def _hints(self) -> None:
        """Has the hint line say this tab's keys, which the shell asks for as it draws."""
        if self.has_focus:
            hinting(self)

    def on_key(self, event: events.Key) -> None:
        """Takes a key the hint line shows, and leaves every other to whoever has it next."""
        typed = event.character or ""
        key = "shift+w" if typed == "W" else typed if typed in _LETTERS else event.key
        listing = self.query_one(OptionList)
        if key in ("left", "right"):
            self.turns(self.tab + (1 if key == "right" else -1))
        elif key in ("1", "2", "3", "4"):
            self.turns(int(key) - 1)
        elif key == "up":
            listing.action_cursor_up()
        elif key == "down":
            listing.action_cursor_down()
        elif key in dict(self.hint_keys()):
            self._does(key)
        else:
            return
        event.stop()
        event.prevent_default()

    def turns(self, to: int) -> None:
        """Turns to a tab, round the ends, keeping where the one left was."""
        self._kept.tab = to % len(TABS)
        self._said = ""
        if self.tab == _ASIDES:
            self._reads()
        self._draws()
        self._hints()

    def turns_at(self, x: int) -> None:
        """Turns to the tab drawn at a column of the tab strip."""
        at = [seen for seen, start in enumerate(self._starts) if start <= x]
        if at:
            self.turns(at[-1])
            self.focus()

    def _does(self, key: str) -> None:
        """Does what a key of the tab that is open does."""
        row = self._under()
        if self.tab == _BOARD:
            if key == "a":
                self._writes("")
            elif key == "d":
                self._removes(row)
            else:
                self._writes(row)
        elif self.tab == _PEOPLE:
            people = self._epic.people()
            if key == "enter":
                holder = people.claims.get(row)
                if holder == people.me:
                    self._epic.asks("release", role=row)
                else:
                    self._epic.asks("claim", role=row, take=bool(holder))
            elif key == "w":
                self._epic.asks("afk", on=not self._away(people, row), role=row)
            else:
                self._epic.asks("afk", on=not people.away)
        elif self.tab == _ASIDES:
            if key == "d":
                self._leaves(row)
            else:
                self._puts("" if key == "a" else row)

    # -- Drawing --------------------------------------------------------------------------------

    def _under(self) -> str:
        """The row the cursor is on, by what it is known by, or "" for none."""
        listing = self.query_one(OptionList)
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return ""
        return str(listing.get_option_at_index(at).id or "")

    def _going(self) -> bool:
        """Whether an epic is open at all."""
        return bool(self._epic.details())

    def _ticks(self) -> None:
        """Reads the epic again, and the side questions where they are what is read."""
        if self.tab == _ASIDES and time.monotonic() - self._read_at >= _WATCHED:
            self._reads()
        self._draws()
        self._hints()

    def _draws(self) -> None:
        """Draws the tabs and the rows of the one that is open, the cursor where it was."""
        if not self.is_mounted:
            return
        strip: list[str] = []
        starts: list[int] = []
        at = 1
        for seen, name in enumerate(TABS):
            # Held together, so that a strip too wide for the zone breaks between tabs.
            said = f"{seen + 1} {t(name).upper()}".replace(" ", "\xa0")
            starts.append(at)
            at += len(said) + 1
            strip.append(
                f"[b $primary]{said}[/]"
                if seen == self.tab
                else f"[$text-muted]{said}[/]"
            )
        self._starts = starts
        self.query_one(_Tabs).update(" ".join(strip))
        listing = self.query_one(OptionList)
        # The list still holds the tab turned from until it is drawn: its cursor is not this one's.
        kept = self._kept.cursors.get(self.tab, "")
        was = (self._under() if self._drawn == self.tab else "") or kept
        rows, note = self._tab_rows()
        ids = [one.held for one in rows]
        landing = [seen for seen, one in enumerate(rows) if one.lands]
        here = ids.index(was) if was in ids and rows[ids.index(was)].lands else None
        if here is None and landing:
            here = landing[0]
        drawn = [
            Option(
                one.said if seen != here else _plain(one.said),
                id=one.held or None,
                disabled=not one.lands,
            )
            for seen, one in enumerate(rows)
        ]
        if self._drawn != self.tab or ids != [one.held for one in self._rows]:
            listing.set_options(drawn)
        else:
            for seen, one in enumerate(drawn):
                if str(listing.get_option_at_index(seen).prompt) != str(one.prompt):
                    listing.replace_option_prompt_at_index(seen, one.prompt)
        self._rows = rows
        self._drawn = self.tab
        if listing.highlighted != here:
            listing.highlighted = here
        if here is not None:
            self._kept.cursors[self.tab] = ids[here]
        self.query_one(".side-note", Static).update(
            f"[$warning]{escape(self._said)}[/]" if self._said else escape(note)
        )

    @on(OptionList.OptionHighlighted)
    def _moved(self, event: OptionList.OptionHighlighted) -> None:
        """Keeps where the cursor is, and says the keys of the row it is on now."""
        held = str(event.option.id or "")
        if self._drawn != self.tab:
            return  # the tab turned from, on its way out
        if held and self._kept.cursors.get(self.tab) != held:
            self._kept.cursors[self.tab] = held
            self._draws()
            self._hints()

    @on(OptionList.OptionSelected)
    def _picked(self, event: OptionList.OptionSelected) -> None:
        """Takes a click on a row as enter on it."""
        event.stop()
        self.focus()
        if "enter" in dict(self.hint_keys()):
            self._does("enter")

    def _tab_rows(self) -> tuple[list[_Row], str]:
        """The rows of the tab that is open, and what is said under them."""
        if not self._going():
            return [_Row("", f"{escape(t('No epic is going here.'))}", lands=False)], ""
        return (self._details, self._board, self._people, self._sides)[self.tab]()

    def _details(self) -> tuple[list[_Row], str]:
        """How the epic stands: its state, then each heading the monitor's page has."""
        state = self._epic.state()
        stands = {"running": "Running", "stopping": "Stopping"}.get(state, "Ended")
        rows = [
            _Row(
                "\x1fstate",
                f"[b]{escape(t(stands))}[/b]  {escape(self._epic.named())}",
            )
        ]
        for heading, said in self._epic.details():
            rows.append(_Row("", "", lands=False))
            rows.append(_headed(t(_HEADINGS.get(heading, heading))))
            rows += [
                _Row(
                    f"{heading}\x1f{at}",
                    f"[$text-muted]{escape(t(named)):<9}[/] {value}"
                    if named
                    else f"{'':<9} {value}",
                )
                for at, (named, value) in enumerate(said)
            ]
        return rows, ""

    def _board(self) -> tuple[list[_Row], str]:
        """The board: each line with what it says, and whose it is."""
        board = self._epic.board()
        if board is None:
            return [
                _Row("", f"{escape(t('This flow keeps no board.'))}", lands=False)
            ], ""
        lines = board.items()
        if not lines:
            return [
                _Row("", f"{escape(t('Nothing is on the board yet.'))}", lands=False)
            ], ""
        rows: list[_Row] = []
        for one in lines:
            whose = " · ".join(part for part in (one.by, one.whose) if part)
            about = " · ".join(part for part in (one.about, whose) if part)
            rows.append(
                _Row(
                    one.key,
                    f"[b]{escape(one.key)}[/b]  {escape(one.value)}"
                    + (f"\n  [$text-muted]{escape(about)}[/]" if about else ""),
                )
            )
        return rows, ""

    @staticmethod
    def _away(people: People, role: str) -> bool:
        """Whether nobody is there for a role: said of it alone, else of every one."""
        return bool(people.away_of.get(role, people.away))

    def _people(self) -> tuple[list[_Row], str]:
        """Each role a person fills: who holds it, and whether anybody is there for it."""
        people = self._epic.people()
        if not people.roles:
            return [
                _Row(
                    "",
                    f"{escape(t('This flow has no role for a person.'))}",
                    lands=False,
                )
            ], ""
        rows: list[_Row] = []
        for role in people.roles:
            holder = people.claims.get(role)
            who = (
                t("You")
                if holder and holder == people.me
                else people.names.get(holder, holder)
                if holder
                else t("Anyone")
            )
            away = (
                f"  [$warning]{escape(t('Away'))}[/]"
                if self._away(people, role)
                else ""
            )
            rows.append(
                _Row(
                    role,
                    f"[b]{escape(role)}[/b]  [$text-muted]{escape(who)}[/]{away}",
                )
            )
        return rows, t(
            "Away, a question a person is asked is answered at once with nothing, "
            "and the epic carries on."
        )

    def _sides(self) -> tuple[list[_Row], str]:
        """Each side conversation: whom it asks, and what was asked and answered in it."""
        note = t("Side questions never reach the epic.")
        if not self._epic.sessions() and not self._asides:
            return [
                _Row(
                    "",
                    f"{escape(t('No harness session is open in this epic yet.'))}",
                    lands=False,
                )
            ], note
        if not self._asides and not self._asking:
            return [
                _Row(
                    "",
                    f"{escape(t('No side question yet; press `a` to ask one.'))}",
                    lands=False,
                )
            ], note
        rows: list[_Row] = []
        seen: set[str] = set()
        for one in self._asides:
            name = str(one.get("aside") or "")
            seen.add(name)
            going = (
                str(one.get("question") or "") or self._asking.get(name, ("", ""))[1]
            )
            rows.append(
                _Row(name, f"[b $primary]btw · {escape(str(one.get('to') or ''))}[/]")
            )
            for said in one.get("said") or ():
                rows.append(_asked(name, len(rows), str(said.get("question") or "")))
                rows.append(
                    _Row(
                        f"{name}\x1f{len(rows)}",
                        f"  {escape(str(said.get('answer') or ''))}",
                        lands=False,
                    )
                )
            if going:
                rows.append(_asked(name, len(rows), going))
                rows.append(
                    _Row(
                        f"{name}\x1f{len(rows)}",
                        f"  [$text-muted]{escape(t('Answering…'))}[/]",
                        lands=False,
                    )
                )
        for name, (to, question) in self._asking.items():
            if name in seen:
                continue
            # Asked, and not yet a side conversation the daemon lists.
            rows.append(_Row(name, f"[b $primary]btw · {escape(to)}[/]"))
            rows.append(_asked(name, len(rows), question))
            rows.append(
                _Row(
                    f"{name}\x1f{len(rows)}",
                    f"  [$text-muted]{escape(t('Answering…'))}[/]",
                    lands=False,
                )
            )
        return rows, note

    # -- Board ----------------------------------------------------------------------------------

    def _writes(self, key: str) -> None:
        """Writes a line of the board: a new one, or what one there says."""
        board = self._epic.board()
        if board is None:
            return
        held = board.held(key) if key else None
        if held is not None and held.whose == FLOW:
            self._says(t("Only the flow changes this line"))
            return

        def took(answer: tuple[str, str] | None) -> None:
            if answer is None:
                return
            named, value = answer
            if value:
                board.put(named, value)
            elif board.held(named) is not None:
                # Emptied, which is taking it off: asked first, as taking one off is.
                self._removes(named)

        self._interface().push_screen(
            Entry(key, held.value if held is not None else "", board), took
        )

    def _removes(self, key: str) -> None:
        """Takes a line off the board, once asked."""
        board = self._epic.board()
        held = board.held(key) if board is not None and key else None
        if board is None or held is None:
            return
        if held.whose == FLOW:
            self._says(t("Only the flow changes this line"))
            return

        def took(answer: str | None) -> None:
            if answer == "yes":
                board.drop(key)

        self._interface().push_screen(
            _Removes(
                t("Remove {name}?", name=key),
                t("The flow no longer reads this line."),
                t("Remove"),
            ),
            took,
        )

    def _says(self, said: str) -> None:
        """Says what became of something, under the list."""
        self._said = said
        self._draws()

    # -- Side questions -------------------------------------------------------------------------

    def _about(self) -> dict[str, Any]:
        """What a call about this epic's side questions names: its workspace, and the epic."""
        return {"workspace": self._epic.workspace(), "epic": self._epic.named()}

    @work(exclusive=True, group="btw-reads")
    async def _reads(self) -> None:
        """Reads the side conversations the daemon holds about the epic."""
        self._read_at = time.monotonic()
        try:
            listed = await asyncio.to_thread(
                self._epic.daemon, "btw.list", self._about()
            )
        except _FAILS:
            return
        self._asides = [
            cast("dict[str, Any]", one) for one in listed.get("asides") or ()
        ]
        if self.is_mounted:
            self._draws()

    def _aside(self, row: str) -> str:
        """The side conversation a row is of."""
        return row.partition("\x1f")[0]

    def _puts(self, row: str) -> None:
        """Asks a side question: in the side conversation under the cursor, or in a new one."""
        sessions = list(self._epic.sessions())
        name = self._aside(row)
        to = next(
            (
                str(one.get("to") or "")
                for one in self._asides
                if one.get("aside") == name
            ),
            "",
        )
        if not name or not to:
            name, to = f"tui-{secrets.token_hex(4)}", ""
        if not to and not sessions:
            self._says(t("No harness session is open in this epic yet."))
            return
        if name in self._asking:
            return  # still answering the last one asked of it

        def took(answer: tuple[str, str] | None) -> None:
            if answer is not None:
                self._asks_aside(name, *answer)

        self._interface().push_screen(_Asking(sessions, to), took)

    @work(group="btw-asks")
    async def _asks_aside(self, name: str, to: str, question: str) -> None:
        """Puts one question to a side conversation, and says what refused it."""
        self._asking[name] = (to, question)
        self._kept.cursors[_ASIDES] = name
        self._said = ""
        self._draws()
        try:
            await asyncio.to_thread(
                self._epic.daemon,
                "btw.ask",
                {**self._about(), "question": question, "aside": name, "to": to},
            )
        except _FAILS as why:
            self._said = str(why) or type(why).__name__
        finally:
            self._asking.pop(name, None)
        if self.is_mounted:
            self._reads()
            self._draws()

    def _leaves(self, row: str) -> None:
        """Closes the side conversation under the cursor, once asked."""
        name = self._aside(row)
        to = next(
            (
                str(one.get("to") or "")
                for one in self._asides
                if one.get("aside") == name
            ),
            "",
        )
        if not name or not to:
            return

        def took(answer: str | None) -> None:
            if answer == "yes":
                self._closes_aside(name)

        self._interface().push_screen(
            _Removes(
                t("Close the side question with {name}?", name=to),
                t(
                    "What was asked and answered in it leaves this list; the epic is "
                    "untouched."
                ),
                t("Close"),
            ),
            took,
        )

    @work(group="btw-asks")
    async def _closes_aside(self, name: str) -> None:
        """Has the daemon close one side conversation."""
        try:
            await asyncio.to_thread(
                self._epic.daemon,
                "btw.leave",
                {"workspace": self._epic.workspace(), "aside": name},
            )
        except _FAILS as why:
            self._said = str(why) or type(why).__name__
        self._asides = [one for one in self._asides if one.get("aside") != name]
        if self.is_mounted:
            self._reads()
            self._draws()


def _headed(heading: str) -> _Row:
    """A heading over the rows under it: in capitals, which the cursor passes over."""
    return _Row("", f"[b $text-muted]{escape(heading.upper())}[/]", lands=False)


def _asked(aside: str, at: int, question: str) -> _Row:
    """One question of a side conversation, as its row says it."""
    return _Row(
        f"{aside}\x1f{at}",
        f"{humanfia.POINT} [$text-muted]{escape(question)}[/]",
        lands=False,
    )


def _plain(said: str) -> str:
    """A row without colours of its own, for the row under the cursor, which has the cursor's."""
    return escape(Content.from_markup(said).plain)


# -- The view in the interface --------------------------------------------------------------------

#: What the view is opened by.
NAME = "epic"

#: Where each interface's view was left.
_KEPT: WeakKeyDictionary[App[Any], Kept] = WeakKeyDictionary()


def _made(app: App[None]) -> Side:
    """The view for an interface: what the monitor reads, and the runs and the daemon asked.

    Beside the log alone: over a sheet or the monitor there is no zone to open it in.
    """
    if len(app.screen_stack) > 1:
        raise SkipAction
    from hmz.runtime.watching.monitor import tallied

    host = cast("Humanize", app)

    def epic() -> dict[str, Any]:
        said = host._epic()
        return said if said.get("run") and not chatting(said) else {}

    def said() -> Sections:
        now = epic()
        if not now:
            return []
        monitor = host._monitor
        return details(
            now,
            calls=host._called,
            lasted=(monitor.until or time.monotonic()) - monitor.began,
            tally=tallied(monitor),
        )

    def daemon(method: str, params: Mapping[str, Any]) -> Any:
        return _rpc(
            host._afar[0] if host._afar is not None else LOCAL_DAEMON, method, params
        )

    return Side(
        Epic(
            details=said,
            state=lambda: str(epic().get("state") or ""),
            named=lambda: host._epic_now if epic() else "",
            board=lambda: host._board() if epic() else None,
            people=lambda: People(
                list(host._outworlders),
                dict(host._claims),
                host._me,
                dict(host._frontends),
                host._afk,
                dict(host._afk_of),
            ),
            sessions=host._btw_sessions,
            asks=host._asks,
            daemon=daemon,
            workspace=lambda: (
                host._afar[1] if host._afar is not None else str(host.hmz.workspace)
            ),
        ),
        _KEPT.setdefault(app, Kept()),
    )


VIEWS = (
    View(
        NAME,
        "context",
        "Epic",
        _made,
        key="ctrl+o",
        hint="Epic panel",
        keys=(("←→", "Tab"), ("↑↓", "Move")),
    ),
)
