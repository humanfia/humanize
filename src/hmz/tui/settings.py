"""`/settings`: every setting humanize has, on a screen of its own, one level at a time.

What opens is the five places settings are kept and nothing else -- this machine's own, the
accounts, the fallbacks, the runtimes and this workspace's -- each a card saying what is in it,
as a phone's settings or VS Code's open on their categories. They stand from the broadest to
the nearest: what is true wherever humanize runs, who its agents are and what takes over when
one fails, where their work goes, and last the one directory open now. Where flows come from
is `/flow`'s (:mod:`hmz.tui.flows`), drawn the same way. Enter or a
click goes into one and esc or backspace comes back out, as k9s and ranger walk in and out of
what they list; the line across the top says where you are, and its first word is a way back.

Inside one is a list, and what is done about the list rather than to one thing on it --
searching it, adding to it, bringing more into it, saving -- is a bar of buttons under it,
as lazygit and gh-dash put what a panel does beside the panel rather than among its rows. Tab
moves between the two. A value is changed by picking it out of every value it can take,
dropped under its row (:mod:`hmz.tui.dropdown`), as Textual's `Select` and Charm's `huh` do,
rather than stepped along with the arrows. And every one of those is a click as well. All of
that is how every sheet of :mod:`hmz.tui.pick` is drawn and worked, this one first among them;
what is here is what is this menu's own: its pages, and its first screen of them.

What is changed is still held until it is saved, from the bar or from the question leaving
asks: the pages that are lists of things are the classes of :mod:`hmz.tui.pick` this is made
of, which say what a list of accounts or machines does, and this is where they are drawn.
"""

# The pages are the mixins of `pick`, and what they share is that module's own.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, cast

from rich.markup import escape
from textual import on, work
from textual.message import Message
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

from hmz.runtime import telemetry
from hmz.runtime.kept import Runs, read_back, written
from hmz.runtime.telemetry import KEPT, SAYS, SENT

from .dropdown import Dropdown, Value
from .pick import (
    _ACCOUNTS,
    _APART_MARK,
    _DIRECTORY,
    _DOT,
    _DROPS,
    _EVERYWHERE,
    _FALLBACK,
    _MACHINES,
    _NO,
    _OPENS,
    _YES,
    Action,
    Adjusted,
    Agent,
    Drop,
    Fallbacks,
    Key,
    Machines,
    Providers,
    _chip,
    _hmz,
    _many,
    _shade,
    _shortly,
    complete,
    switched,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from textual.app import App
    from textual.await_complete import AwaitComplete

    from hmz.coganchor.backends import Model


__all__ = ["MOVED", "PAGES", "Adjusts", "page_of"]


#: What `/settings` is told to open each page by, in the order they are listed: the word on
#: its card, lower case, so that the word typed is the word read.
PAGES = (
    "general",
    "accounts",
    "fallback",
    "runtimes",
    "workspace",
)

#: The page that moved to `/flow`, still taken by `/settings` so that it can say where it went.
MOVED = "flowverses"

#: The words pages were opened by before they were called what they are, still taken: a word
#: somebody's fingers know is a word they will type.
_ALIASES = {
    "settings": _EVERYWHERE,
    "everywhere": _EVERYWHERE,
    "directory": _DIRECTORY,
    "environments": PAGES.index("runtimes"),
}


def page_of(said: str) -> int | None:
    """Which page a word opens, by its name or the name it had.

    Args:
      said: The word, in any case.

    Returns:
      The page, counting from the first, or None for a word that is no page.
    """
    said = said.lower()
    return PAGES.index(said) if said in PAGES else _ALIASES.get(said)


class _Page(NamedTuple):
    """One card of the first screen: what the page is called, its mark, and what is in it.

    Attributes:
      title: What it is called, on its card and across the top once inside it.
      icon: One cell that tells it from the others at a glance.
      blurb: What is kept there, in a line.
    """

    title: str
    icon: str
    blurb: str


#: The pages, in the order of :data:`PAGES`.
_PAGES = (
    _Page(
        "General", "⚙", "this machine: what runs show, the /btw agent, error reports"
    ),
    _Page("Accounts", "◉", "what agents sign in as, under each CLI"),
    _Page("Fallback", "↻", "where a turn goes when its agent fails"),
    _Page("Runtimes", "▦", "ssh hosts, docker daemons, swarms and Apple containers"),
    _Page("Workspace", "⌂", "this directory: its flow, and forgetting it"),
)

#: What the first screen says it is.
_HOME_ABOUT = "Every setting humanize keeps. What you change is held until you save it."

#: The rows the general and workspace pages are made of, by the id each is put up under.
_SENTRY = "reports"
_SENT = "sent"
_DETAILS = "details"
_BTW = "btw"
_RUNS = "flow"
_FORGET = "forget"

#: The kinds of row those are: a switch, turned on or off from the two dropped under it; a
#: value picked out of a list; one that says something when it is opened; and one that is
#: only read -- a directory and the flow it opens on are what is remembered, not set here.
_SWITCH, _PICK, _SAYS, _READ = "switch", "pick", "says", "read"

#: What the /btw agent's list offers beside the agents it can already be: setting one up.
_ANOTHER = f"{_APART_MARK}another"

#: When a setting that cannot land at once does land, said beside its row while it is held
#: and in the transcript once it is saved.
_NEXT_LAUNCH = "takes effect on next launch"
_NEXT_BTW = "takes effect on next /btw"


class _Setting(NamedTuple):
    """One row of the general or the workspace page.

    Attributes:
      held: Its id.
      named: What it is called.
      value: What it is set to, in words.
      about: What it means.
      kind: Which of the four kinds of row it is -- see :data:`_SWITCH`.
      note: When a change held on it lands, or "" for one that lands at once.
      group: The heading it stands under, which the rows before it share or do not.
    """

    held: str
    named: str
    value: str
    about: str
    kind: str
    note: str = ""
    group: str = ""


def _word(on: bool | None) -> str:  # noqa: FBT001 -- a switch is one
    """What a switch says it is."""
    return {True: _YES, False: _NO, None: "not set"}[on]


#: What each switch's two values mean, said beside them on the list dropped under it.
_MEANS = {
    _SENTRY: ("send error reports", "send nothing"),
    _DETAILS: ("show tool calls and thinking", "show turn responses only"),
    _FORGET: ("clear saved settings here", "keep them"),
}


class Adjusts(Providers, Machines, Fallbacks):
    """Every setting humanize has: `/settings`, five pages opened from one screen of them.

    General is what is true of this machine however many projects are driven from it; the
    accounts, the fallbacks and the runtimes are what agents run as, where turns go when they
    cannot, and the machines their work goes on; the workspace is one directory's. One menu
    because they are one question -- what does humanize remember -- and a command apiece was
    five things to learn the names of.

    A menu rather than a file to edit, for the reason every other menu here is one: what is
    written down is written down in humanize's own words, and a person should not have to know
    the shape of a YAML file to turn a thing off. What is held lands together when it is saved,
    from the bar or from the question leaving asks, and each setting takes effect at once where
    it can; where it cannot, the row says when it will while it is held and the transcript says
    so once it is saved. What runs a command of its own -- making an account, signing one in,
    saving or checking a machine -- happens as it is asked for.
    """

    class Settled(Message):
        """Says what the settings menu was answered with, to whoever applies it.

        Posted to the interface rather than only answered to whoever opened the menu: what
        was changed is the interface's to apply -- the details it shows, the directory it
        remembers -- whoever was waiting on the answer.
        """

        def __init__(self, said: Adjusted) -> None:
            """Carries the answer.

            Args:
              said: What the menu was answered with.
            """
            super().__init__()
            self.said = said

    def __init__(
        self,
        agents: Mapping[str, tuple[Model, ...]],
        *,
        page: int | None = None,
        unavailable: frozenset[str] = frozenset(),
    ) -> None:
        """Initializes the menu on what is remembered now.

        What is written down rather than what is happening: the environment may answer the
        reporting question for one run, and a menu that showed that would be a menu offering
        to change a thing it cannot. The page says so under the list where the two differ.

        Args:
          agents: The backends offered here, and what each of them says it runs, which is
            what the fallback page chooses a place out of.
          page: Which page to open inside, or None for the screen of them all.
          unavailable: The optional backends that still need installing, which the btw agent
            is offered as it is anywhere else an agent is set up.
        """
        super().__init__()
        settings = _hmz().settings
        self._sentry = self._sentry_was = settings.enable_sentry
        self._overridden = telemetry.enabled() is not self._sentry
        self._details = self._details_was = settings.details
        #: The agent `/btw` talks to outside a session, or "" for the flow's first.
        self._btw = self._btw_was = settings.btw
        self._unavailable = unavailable
        self._workspace = str(Path.cwd())
        self._flow = settings.flow
        self._roles = len(settings.agents(settings.flow))
        self._flows = len(settings.flows())
        self._forget = False
        self._offered = dict(agents)
        self._steps = list(_hmz().fallbacks.all())
        #: The steps as they were read, so the card can say the page is holding a change.
        self._steps_was = list(self._steps)
        #: Whether the screen of pages is what is drawn, rather than one of them.
        self._home = page is None
        self._tab = page or 0
        #: The row each page's cursor was last on, by id, for when it is gone back into.
        self._cursors: dict[int, str] = {}

    def _ask(self) -> None:
        """Reads the pages that are lists, and puts up whichever is open."""
        self._read_accounts()
        self._read_machines()
        self._fill()

    # -- Going in and out ----------------------------------------------------------------------

    def _opens(self, page: int | None) -> None:
        """Goes into one page, or back out to the screen of them all.

        What was said on the page left, and where its cursor was, are kept for when it is gone
        back into: what became of something done on a page is still true of it after a look at
        another. A search goes with the page it was typed into.

        Args:
          page: The page, or None for the screen of them all.
        """
        listing = self.query_one("#choices", OptionList)
        if not self._home:
            self._saids[self._tab] = self._said
            self._cursors[self._tab] = self._was
        self._said = ""
        self._typed = ""
        self._searching = False
        seek = self.query_one("#seek", Input)
        seek.display = False
        with seek.prevent(Input.Changed):
            seek.value = ""
        listing.clear_options()
        self._drawn = None
        if page is None:
            self._home = True
        else:
            self._home = False
            self._tab = page
            self._said = self._saids.pop(page, "")
            self._was = self._cursors.get(page, "")
        self._fill()
        self._settles_focus()

    def _tell(self, page: int, said: str) -> None:
        """Says what became of something done on one page, whichever is open now.

        Args:
          page: The page it was done on.
          said: What to say, as markup.
        """
        if self._home or self._tab != page:
            self._saids[page] = said
        else:
            self._said = said

    def action_up(self) -> None:
        """Goes back out to the screen of pages, from inside one -- or up out of the menu."""
        if not self._home:
            self._opens(None)
            return
        super().action_up()

    def action_back(self) -> None:
        """Comes out of a search, or out of the page, or leaves.

        Leaving asks first whether to save what is held, as every menu holding changes does.
        """
        if not (self._searching or self._home):
            self._opens(None)
            return
        super().action_back()

    def enters(self, row: str) -> bool:
        """Whether the arrow right goes into a row: a card, or a thing a page lists.

        Not a setting of the general or workspace page, whose values are dropped under it.

        Args:
          row: The row, by id.

        Returns:
          True for a card, and for a row of a page that is a list.
        """
        return bool(row) and (
            self._home or self._tab in (_ACCOUNTS, _MACHINES, _FALLBACK)
        )

    # -- The way across the top -----------------------------------------------------------

    def crumb(self) -> str:
        """`/settings`, or the page open in it, which is what a menu opened from it is in."""
        return "/settings" if self._home else escape(_PAGES[self._tab].title)

    def crumbs(self) -> list[str]:
        """`/settings`, while a page of it is open."""
        return [] if self._home else ["/settings"]

    def climbs_to(self, depth: int) -> None:
        """Goes back out to the screen of pages, from a click on `/settings` across the top.

        Args:
          depth: Which level: the first is the screen of pages.
        """
        if not depth and not self._home:
            self._opens(None)

    # -- Drawing -----------------------------------------------------------------------------

    def _fill(self) -> None:
        """Puts up the screen of pages, or the page that is open, and the bar under it."""
        self.query_one("#asked", Label).update(self.crumb())
        self.query_one("#about", Label).update(
            _HOME_ABOUT
            if self._home
            else {
                _EVERYWHERE: "How humanize behaves on this machine, in every directory.",
                _DIRECTORY: f"What {_shortly(self._workspace)} remembers: the flow it "
                "opens on and how it was last configured.",
                _ACCOUNTS: self.ACCOUNTS_ABOUT,
                _MACHINES: self.MACHINES_ABOUT,
                _FALLBACK: self.STEPS_ABOUT,
            }[self._tab]
        )
        if self._home:
            self._fill_home()
        elif self._tab == _ACCOUNTS:
            self._fill_accounts()
        elif self._tab == _MACHINES:
            self._fill_machines()
        elif self._tab == _FALLBACK:
            self._fill_steps()
        else:
            self._fill_own()

    def _summary(self, page: int) -> str:
        """What one page's card says is in it, in a few words."""
        if page == _EVERYWHERE:
            return f"details {_word(self._details)}{_DOT}reports {_word(self._sentry)}"
        if page == _DIRECTORY:
            return f"{_shortly(self._workspace)}{_DOT}flow {self._flow or 'none'}"
        if page == _ACCOUNTS:
            return _many(len([one for one in self._accounts if one.name]), "account")
        if page == _MACHINES:
            return _many(len(self._saved_machines), "machine")
        return _many(len(self._steps), "rule")

    def _pending(self, page: int) -> bool:
        """Whether one page is holding a change that saving would land."""
        if page == _EVERYWHERE:
            return (self._sentry, self._details, self._btw) != (
                self._sentry_was,
                self._details_was,
                self._btw_was,
            )
        if page == _DIRECTORY:
            return self._forget
        if page == _ACCOUNTS:
            return bool(self._gone or self._edits)
        if page == _FALLBACK:
            return self._steps != self._steps_was
        return False

    def _holding(self) -> bool:
        """Whether any page is holding a change that saving would land.

        Read off what each page holds rather than off whether anything was ever changed: a
        switch turned on and back off again is nothing to save, and nothing to be asked about
        on the way out.
        """
        return any(self._pending(page) for page in range(len(PAGES)))

    def leaving(self) -> None:
        """Asks whether to save what is held, where anything still is, and leaves."""
        if not self._holding():
            self.dismiss(None)
            return
        self.asks_to_save()

    def _fill_home(self) -> None:
        """Puts up a card per page: its mark, its name, what is in it, and what it is for."""
        listing = self.query_one("#choices", OptionList)
        at = (
            listing.highlighted
            if listing.option_count == len(PAGES) and listing.highlighted is not None
            else self._tab
        )
        cards: list[Option | None] = []
        for page, card in enumerate(_PAGES):
            cards.append(
                Option(
                    self._card(
                        card.icon,
                        card.title,
                        self._summary(page),
                        card.blurb,
                        here=page == at,
                        pending=self._pending(page),
                    ),
                    id=f"={PAGES[page]}",
                )
            )
            # A rule between two cards, which the cursor steps over.
            cards.append(None)
        listing.set_options(cards[:-1])
        listing.highlighted = at
        self._drawn = at
        self.query_one("#tuning", Label).update("")
        self._footed(Key("enter", "open"), Key("esc", "close"))

    def _settings(self) -> list[_Setting]:
        """The rows of the general or the workspace page, as they are held now.

        Under a heading per thing they are about, the one changed most first: details are
        turned round while a run is read, the reporting once, if ever. The directory itself is
        no row: it is not set here, and the page says it across the top. Forgetting goes last,
        apart, as what undoes the rest does in any settings.
        """
        if self._tab == _DIRECTORY:
            return [
                _Setting(
                    _RUNS,
                    "Default flow",
                    self._flow or "none",
                    f"configured with {_many(self._roles, 'agent')}; chosen with /flow",
                    _READ,
                    group="Flow",
                ),
                _Setting(
                    _FORGET,
                    "Forget",
                    _word(self._forget),
                    f"clear saved settings here, across {_many(self._flows, 'flow')}",
                    _SWITCH,
                    _NEXT_LAUNCH if self._forget else "",
                    group="Reset",
                ),
            ]
        return [
            _Setting(
                _DETAILS,
                "Details",
                _word(self._details),
                "show every tool call and all of the thinking",
                _SWITCH,
                group="Display",
            ),
            _Setting(
                _BTW,
                "/btw agent",
                self._btw or "the flow's first agent",
                "the agent /btw uses outside a session",
                _PICK,
                _NEXT_BTW if self._btw != self._btw_was else "",
                group="Agents",
            ),
            _Setting(
                _SENTRY,
                "Error reports",
                _word(self._sentry),
                "send error reports to humanize",
                _SWITCH,
                group="Privacy",
            ),
            _Setting(
                _SENT,
                "What is sent",
                "",
                "what error reports include and exclude",
                _SAYS,
                group="Privacy",
            ),
        ]

    @staticmethod
    def _chip(one: _Setting, *, here: bool) -> tuple[str, int]:
        """What a row says it is set to, as markup, and how many cells that takes.

        A switch and a value picked from a list are drawn as on any sheet; a row that opens
        says so; one that is only read is only its value, quietly.

        Args:
          one: The row.
          here: Whether it is the one under the cursor.

        Returns:
          The markup, and its width.
        """
        if one.kind in (_SWITCH, _PICK):
            return _chip(one.value, _DROPS, here=here, toggles=one.kind == _SWITCH)
        if one.kind == _SAYS:
            return _chip("", _OPENS, here=here)
        return _shade("$text-muted", one.value, here=here), len(one.value)

    def _fill_own(self) -> None:
        """Puts up the general or workspace page: a row per setting under its heading.

        Its value at the far end, and a rule between two rows of one heading; a heading, as
        the accounts' are, is a row the arrows step over.
        """
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        rows = self._settings()
        held = [one.held for one in rows]
        landing = self._was if self._was in held else held[0]
        width = self._width_of(listing)
        options: list[Option | None] = []
        group = ""
        for one in rows:
            if one.group != group:
                if options:
                    # Not the rule after the last row: a blank line before the next heading.
                    options[-1] = Option("", disabled=True)
                group = one.group
                options.append(Option(f" [$primary]{escape(group)}[/]", disabled=True))
            here = one.held == landing
            chip, cells = self._chip(one, here=here)
            pad = max(2, width - 2 - len(one.named) - cells)
            if here:
                self._values_at = 1 + len(one.named) + pad
            note = (
                f"{_DOT}{_shade('$warning', one.note, here=here)}" if one.note else ""
            )
            options.append(
                Option(
                    f" [b]{escape(one.named)}[/]{' ' * pad}{chip}\n"
                    f"   {_shade('$text-muted', one.about, here=here)}{note}",
                    id=f"={one.held}",
                )
            )
            options.append(None)
        listing.set_options(options[:-1])
        listing.highlighted = next(
            at
            for at in range(listing.option_count)
            if listing.get_option_at_index(at).id == f"={landing}"
        )
        self._was = landing
        self._drawn = listing.highlighted
        said = self._said
        if (
            not said
            and self._tab == _EVERYWHERE
            and self._overridden
            and self._sentry == self._sentry_was
        ):
            said = f"{SAYS} is set, overriding this setting for this run"
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        kind = next((one.kind for one in rows if one.held == landing), _READ)
        does = {_SWITCH: "choose", _PICK: "choose", _SAYS: "read"}.get(kind)
        self._footed(*((Key("enter", does),) if does else ()), Key("esc", "back"))

    def _lands(self, items: Sequence[str]) -> str:
        """Lands the cursor as a page does, and the focus with it on something just added.

        Something added from a button is what somebody wants to look at next, so the focus
        goes back to the list it landed on rather than staying on the button that made it.

        Args:
          items: The things listed, by id.

        Returns:
          The id of the row the cursor goes on.
        """
        aimed = self._aim
        landing = super()._lands(items)
        if aimed and landing == aimed:
            self.call_after_refresh(self.query_one("#choices", OptionList).focus)
        return landing

    def actions(self) -> list[Action]:
        """What the screen of pages, or the page open, does about its list, in the order it stands.

        Saving on the screen of pages and on every page that holds anything, and nothing else
        on the general and workspace pages, whose rows are each a setting of their own.
        """
        if self._home:
            return [self._saves_all()]
        return {
            _ACCOUNTS: self._account_actions,
            _MACHINES: self._machine_actions,
            _FALLBACK: self._step_actions,
        }.get(self._tab, lambda: [self._saves_all()])()

    def _footed(self, *keys: Key) -> None:
        """Says the keys, with esc saying whether it closes the menu or comes out of a page.

        Args:
          keys: The page's keys, for its list.
        """
        back = Key("esc", "close" if self._home else "back")
        super()._footed(*(one for one in keys if one.key != "esc"), back)

    # -- Doing -------------------------------------------------------------------------------

    @on(OptionList.OptionSelected, "#choices")
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Goes into the card chosen, or does what enter does on the row chosen.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id or "").removeprefix("=")
        if self._home:
            self._opens(PAGES.index(held))
            return
        self._takes(held)

    def _takes(self, held: str) -> None:
        """Does what one row is for, which each page says for itself.

        Args:
          held: The row, by the id it answers with.
        """
        if self._tab == _ACCOUNTS:
            self._took_account(held)
        elif self._tab == _MACHINES:
            self._took_machine(held)
        elif self._tab == _FALLBACK:
            self._took_step(held)
        elif held == _SENT:
            sent, kept = "; ".join(SENT), "; ".join(KEPT)
            self._said = f"Sent: {sent}. Never sent: {kept}."
            self._fill()
        elif held == _BTW:
            self._chooses_btw()

    def drops(self, row: str) -> bool:
        """Whether a row is a switch of the general or workspace page, its two values dropped.

        Args:
          row: The row, by id.

        Returns:
          True for a switch.
        """
        return (
            not self._home and self._tab in (_EVERYWHERE, _DIRECTORY) and row in _MEANS
        )

    def dropping(self, row: str) -> Drop:
        """A switch's two values, what each means, and which it is held at.

        Args:
          row: The switch, by id.

        Returns:
          The list, opening on the answer it is not, so that enter twice turns it round.
        """
        now = self._switched(row)
        named = next(one.named for one in self._settings() if one.held == row)
        return switched(named, _word(now) if now is not None else "", _MEANS[row])

    def dropped(self, row: str, picked: str) -> None:
        """Holds a switch at the value picked.

        Args:
          row: The switch, by id.
          picked: `on` or `off`.
        """
        on_ = picked == _YES
        if row == _SENTRY:
            self._sentry = on_
        elif row == _DETAILS:
            self._details = on_
        else:
            self._forget = on_
        self._said = ""

    def _switched(self, held: str) -> bool | None:
        """What one switch is held at now."""
        return {
            _SENTRY: self._sentry,
            _DETAILS: self._details,
            _FORGET: self._forget,
        }[held]

    @work
    async def _chooses_btw(self) -> None:
        """Asks which agent /btw talks to, from the list dropped under its row, and holds it.

        The flow's first agent, the one chosen already where one is, or another -- set up on
        the sheet every agent is set up on.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            values = [Value("", "the flow's first agent", "whichever it names first")]
            if self._btw:
                values.append(Value(self._btw, self._btw, "chosen"))
            values.append(Value(_ANOTHER, "another…", "set one up"))
            picked = await showing.push_screen_wait(
                Dropdown("/btw agent", values, self._btw, at=self.dropped_at())
            )
            if picked == _ANOTHER:
                chosen = await showing.push_screen_wait(
                    Agent(
                        "btw agent",
                        read_back(self._btw) or Runs(""),
                        self._offered,
                        unavailable=self._unavailable,
                    )
                )
                picked = (
                    written(chosen) if chosen is not None and complete(chosen) else None
                )
        finally:
            self.opened()
        if picked is None or picked == self._btw:
            return
        self._btw, self._said = picked, ""
        self.changed()
        self._fill()

    def applied(self) -> None:
        """Lands what every page was holding, and answers with what was changed."""
        told = list(self._told)
        self._applies_accounts(told)
        self._applies_steps(told)
        self.dismiss(
            Adjusted(
                enable_sentry=self._sentry
                if self._sentry is not None and self._sentry != self._sentry_was
                else None,
                details=self._details if self._details != self._details_was else None,
                forget=self._forget,
                btw=self._btw if self._btw != self._btw_was else None,
                told=tuple(told),
                corrected=tuple(self._corrected),
            )
        )

    def dismiss(self, result: Adjusted | None = None) -> AwaitComplete:
        """Answers, saying what happened even where nothing held was saved.

        Making an account and saving a machine happen as they are asked for, so a menu
        walked out of without saving -- or with what it held thrown
        away -- still has something to say about them. And it is said to the interface as
        well as answered, since the interface is what applies the rest.

        Args:
          result: What the menu is answered with, or None for nothing held.

        Returns:
          The waiting, as a sheet's own is.
        """
        said = result or (Adjusted(told=tuple(self._told)) if self._told else None)
        if said is not None and not self._answered:
            showing = cast(
                "App[None]",
                self.app,  # pyright: ignore[reportUnknownMemberType]
            )
            showing.post_message(self.Settled(said))
        return super().dismiss(said)
