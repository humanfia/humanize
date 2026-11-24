"""`/settings`: every setting Humanize has, on a screen of its own, one level at a time.

What opens is the places settings are kept, each a card saying what is in it, in the groups
the web page's Settings has them in -- because the first thing somebody looking for a setting
asks is whether it is about their screen or about the machine doing the work. **App** is what
is kept on this machine for this person: how the interface is drawn, the daemons it reaches,
what it tells of them, and the language it is written in. **Daemon** is what the daemon
keeps: what is true wherever Humanize runs, who its agents are and what takes over when one
fails, where their work goes, where epics are backed up, and what all of it spent. And
**Workspace** is the one directory open now. Where flows come from is `/flow`'s
(:mod:`hmz.tui.flows`), drawn the same way. Enter or a click goes into a page and esc or
backspace comes back out, as k9s and ranger walk in and out of what they list; the line
across the top says where you are, and its first word is a way back.

Inside one is a list, and what is done about the list rather than to one thing on it --
searching it, adding to it, bringing more into it, saving -- is a bar of buttons under it,
as lazygit and gh-dash put what a panel does beside the panel rather than among its rows. Tab
moves between the two. A value is changed by picking it out of every value it can take,
dropped under its row (:mod:`hmz.tui.dropdown`), as Textual's `Select` and Charm's `huh` do,
rather than stepped along with the arrows. And every one of those is a click as well. All of
that is how every sheet of :mod:`hmz.tui.pick` is drawn and worked, this one first among them;
what is here is what is this menu's own: its pages, and its first screen of them.

What is changed is held until it is saved, from the bar or from the question leaving asks:
the pages that are lists of things are the classes of :mod:`hmz.tui.pick` this is made of,
which say what a list of accounts or machines does, and this is where they are drawn. A theme
and a language are the two that are not held: each is shown as the cursor moves over it, so
that what it comes to is seen before it is chosen, kept by enter and put back by esc
(:mod:`hmz.tui.own`).

Every text here is one of :mod:`hmz.words`, said as it is drawn rather than as this module is
read, so that a language chosen is the language of the next thing drawn.
"""

# The pages are the mixins of `pick`, and what they share is that module's own.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

from rich.cells import cell_len
from rich.markup import escape
from textual import on, work
from textual.message import Message
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

from hmz.runtime import telemetry
from hmz.runtime.kept import Runs, written
from hmz.runtime.telemetry import KEPT, SAYS, SENT
from hmz.runtime.watching.notices import KINDS, prefer, preferences
from hmz.words import LANGUAGES, speak, t

from . import humanfia, own
from .chats import Archived
from .dropdown import Value
from .pick import (
    _ACCOUNTS,
    _BACKUP,
    _DAEMONS,
    _DIRECTORY,
    _DOT,
    _DROPS,
    _EVERYWHERE,
    _MACHINES,
    _NO,
    _NOTIFICATIONS,
    _NOUS,
    _OPENS,
    _YES,
    Action,
    Adjusted,
    Agent,
    Backups,
    Daemons,
    Drop,
    Key,
    Machines,
    NousPage,
    Providers,
    _chip,
    _hmz,
    _shade,
    _shortly,
    complete,
    switched,
)
from .usage import Spends

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from textual.app import App
    from textual.await_complete import AwaitComplete

    from hmz.coganchor.backends import Model


__all__ = ["GROUPS", "MOVED", "PAGES", "Adjusts", "menu", "page_of"]


#: The groups the pages stand in, as the web page's Settings has them, each with the pages
#: in it by the word that opens each: what is this person's on this machine, what the daemon
#: keeps, and the directory open now.
GROUPS: Final = (
    ("App", ("themes", "daemons", "notifications", "language")),
    ("Daemon", ("general", "accounts", "nous", "runtimes", "backup", "usage")),
    ("Workspace", ("workspace",)),
)

#: What `/settings` is told to open each page by, in the order they are listed: the word on
#: its card, lower case, so that the word typed is the word read.
PAGES: Final = tuple(page for _, pages in GROUPS for page in pages)

#: The pages that are this module's own to count: what the epics spent, how the interface is
#: drawn and what it is written in. The rest are counted where the classes they are made of
#: are (:mod:`hmz.tui.pick`).
_USAGE, _THEMES, _LANGUAGE = 8, 9, 10

#: Which page each word opens, as the pages are counted -- which is not the order they are
#: listed in: a page keeps its number wherever it is moved to on the screen.
_TABS: Final = {
    "general": _EVERYWHERE,
    "notifications": _NOTIFICATIONS,
    "daemons": _DAEMONS,
    "accounts": _ACCOUNTS,
    "nous": _NOUS,
    "runtimes": _MACHINES,
    "backup": _BACKUP,
    "workspace": _DIRECTORY,
    "usage": _USAGE,
    "themes": _THEMES,
    "language": _LANGUAGE,
}
_NAMES: Final = {tab: name for name, tab in _TABS.items()}

#: The page that moved to `/flow`, still taken by `/settings` so that it can say where it went.
MOVED = "flowverses"

#: The words pages were opened by before they were called what they are, still taken: a word
#: somebody's fingers know is a word they will type.
_ALIASES = {
    "settings": "general",
    "everywhere": "general",
    "directory": "workspace",
    "environments": "runtimes",
}


def page_of(said: str) -> int | None:
    """Which page a word opens, by its name or the name it had.

    Args:
      said: The word, in any case.

    Returns:
      The page, counting from the first of :data:`PAGES`, or None for a word that is no page.
    """
    said = said.lower()
    said = _ALIASES.get(said, said)
    return PAGES.index(said) if said in PAGES else None


def _cards() -> dict[str, tuple[str, str]]:
    """What each page is called, and what is kept there in a line: the web page's words.

    Three of them are this interface's own, where the page's speak of a browser.
    """
    return {
        "themes": (t("Themes"), t("Colours of this terminal")),
        "daemons": (
            t("Daemons"),
            t("Machines this terminal reaches, and the one it shows"),
        ),
        "notifications": (t("Notifications"), t("What every daemon tells you")),
        "language": (t("Language"), t("What this terminal is written in")),
        "general": (t("General"), t("Display and reporting")),
        "accounts": (t("Accounts"), t("Credentials agents run as")),
        "nous": (
            t("Nous"),
            t("Who takes a turn, and where it goes once it fails"),
        ),
        "runtimes": (t("Runtimes"), t("Machines environments run on")),
        "backup": (t("Backup"), t("Git repositories epics go to")),
        "usage": (
            t("Usage"),
            t("What everything on this daemon spent, by day and flow"),
        ),
        "workspace": (t("Workspace"), t("What this folder was last set up with")),
    }


def _groups() -> dict[str, str]:
    """What each group is headed, by the name it has in :data:`GROUPS`."""
    return {"App": t("App"), "Daemon": t("Daemon"), "Workspace": t("Workspace")}


#: The rows the general and workspace pages are made of, by the id each is put up under.
_SENTRY = "reports"
_SENT = "sent"
_DETAILS = "details"
_PREFER = "prefer"
_HARNESS = "harness_sessions"
_RUNS = "flow"
_CHAT_AGENT = "chat-agent"
_ARCHIVED = "archived"
_FORGET = "forget"
_SYSTEM = "system"

#: The rows of the themes and language pages, by what their ids start with: which side is
#: drawn, which preset, and which language.
_MODE, _PAIR, _LANG = "mode:", "pair:", "lang:"


def _kinds() -> dict[str, str]:
    """What the notifications page calls each kind of notice, as the web page's does."""
    return {
        "done": t("Done"),
        "failed": t("Failed"),
        "stopped": t("Stopped"),
        "asked": t("Questions"),
        "listening": t("Waiting"),
    }


#: The kinds of row those are: a switch, turned on or off from the two dropped under it; a
#: value picked out of a list; one that says something when it is opened; one that opens a
#: sheet to set it up on; and one that is only read -- a directory and the flow last set up
#: in it are what is remembered, not set here.
_SWITCH, _PICK, _SAYS, _SETS, _READ = "switch", "pick", "says", "sets", "read"


def _prefers() -> dict[Literal["native", "flow"], str]:
    """What a chat's `$<name>` can mean where a native skill and a flow are both called that.

    Section 8.9.10 of [CORE]: each with what it comes to, said beside it on the list dropped
    under the row.
    """
    return {
        "native": t("The harness's own skill of that name runs"),
        "flow": t("The flow of that name starts, and the skill stays $ in the harness"),
    }


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
    """What a switch says it is on its row, where the dot beside it is filled or is not."""
    return t("Not set") if on is None else _YES if on else _NO


def _said(on: bool | None) -> str:  # noqa: FBT001 -- a switch is one
    """What a switch says it is on a card, in the page's words."""
    return t("Not set") if on is None else t("On") if on else t("Off")


#: The rows that are switches, whose two values are dropped under them.
_SWITCHES: Final = frozenset({_SENTRY, _DETAILS, _HARNESS, _FORGET, _SYSTEM, *KINDS})


def _unsaved(named: str, why: OSError) -> str:
    """What the transcript says of a setting that could not be written, as markup."""
    return "hmz: " + escape(t("Could not save {name}: {why}", name=named, why=str(why)))


def menu(page: int | None = None) -> Adjusts:
    """`/settings`, made on what is installed here, for whoever opens it.

    Args:
      page: Which page to open inside, counting from the first of :data:`PAGES`, or None
        for the screen of them all.

    Returns:
      The menu, to be put on the screen.
    """
    agents = _hmz().installed()
    unavailable = _hmz().installable()
    agents.update(unavailable)
    return Adjusts(agents, page=page, unavailable=frozenset(unavailable))


class Adjusts(Providers, Machines, NousPage, Backups, Daemons, Spends):
    """Every setting Humanize has: `/settings`, eleven pages opened from one screen of them.

    The themes and the language are how this person's interface is drawn and what it is
    written in, the daemons this machine's and the others reached from it, and the
    notifications which of their epics it tells of. General is what is true of this machine
    however many projects are driven from it; the accounts, the nous
    and the runtimes are what agents run as, what they think with and where turns go, and the
    machines their work goes on; the backups are where epics are copied to; the usage is what
    the epics spent; and the workspace is one directory's. One menu because they
    are one question -- what does Humanize remember -- and a command apiece was eleven things
    to learn the names of.

    A menu rather than a file to edit, for the reason every other menu here is one: what is
    written down is written down in Humanize's own words, and a person should not have to know
    the shape of a TOML file to turn a thing off. What is held lands together when it is saved,
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
            what the nous page chooses a concrete nous out of.
          page: Which page to open inside, counting from the first of :data:`PAGES`, or
            None for the screen of them all.
          unavailable: The optional backends that still need installing, which Ai-chan's
            is offered as it is anywhere else an agent is set up.
        """
        super().__init__()
        settings = _hmz().settings
        self._sentry = self._sentry_was = settings.enable_sentry
        self._overridden = telemetry.enabled() is not self._sentry
        self._details = self._details_was = settings.details
        #: What a chat's `$<name>` means where it names both a native skill and a flow, for
        #: every chat that does not say for itself.
        self._prefer: Literal["native", "flow"] = settings.chat_prefer
        self._prefer_was = self._prefer
        #: Whether `/resume` in a chat lists the sessions each harness had of its own here.
        self._harness = self._harness_was = settings.harness_sessions
        #: The agent a new chat in this directory talks to, or None where none was chosen.
        self._chat_agent = self._chat_agent_was = settings.chat_agent
        #: Which kinds of notice are told, and whether the system shows them too: kept with the
        #: web interface's, under `notifications` in this machine's `settings.toml`.
        wanted = preferences()
        self._kinds: dict[str, bool] = dict(wanted["kinds"])
        self._kinds_was = dict(self._kinds)
        self._system: bool = wanted["system"]
        self._system_was = self._system
        self._unavailable = unavailable
        self._workspace = str(Path.cwd())
        self._flow = settings.flow
        self._roles = len(settings.agents(settings.flow))
        self._flows = len(settings.flows())
        self._forget = False
        self._offered = dict(agents)
        self._read_nous()
        self._read_backups()
        #: Whether the screen of pages is what is drawn, rather than one of them.
        self._home = page is None
        self._tab = _TABS[PAGES[page or 0]]
        #: The row each page's cursor was last on, by id, for when it is gone back into.
        self._cursors: dict[int, str] = {}
        #: How this person's interface is drawn and what it is written in, as it is kept:
        #: what the cursor is on is shown, and this is what is put back.
        self._kept = own.read()
        self._was = self._arrives(self._tab)

    def _ask(self) -> None:
        """Reads the pages that are lists, and puts up whichever is open."""
        self._read_accounts()
        self._read_machines()
        self._read_daemons()
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
            self._puts_back()
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
            self._was = self._arrives(page) or self._cursors.get(page, "")
        self._fill()
        self._settles_focus()

    def _arrives(self, page: int) -> str:
        """Where the cursor lands on a page not yet walked: on what is in use, where it lists that.

        Which is what keeps opening the themes from changing anything: what is under the
        cursor is what is shown, and what is shown first is what was already there.

        Args:
          page: The page.

        Returns:
          The row, by id, or "" for the first of a page that has no row in use.
        """
        if page == _THEMES:
            # Not on a preset while the terminal's own colours are drawn: a preset under the
            # cursor is a preset shown.
            if self._kept.appearance == "terminal":
                return f"{_MODE}terminal"
            return f"{_PAIR}{self._kept.theme}"
        if page == _LANGUAGE:
            return f"{_LANG}{self._kept.language}"
        return ""

    # -- What is shown before it is chosen -----------------------------------------------------

    def _candidate(self, row: str) -> own.Kept:
        """What would be kept were one row of the themes or the language chosen.

        A preset chosen while the terminal's own colours are drawn is chosen to be seen, so
        it goes back to following the terminal.

        Args:
          row: The row, by id; any other is what is kept now.
        """
        kept = self._kept
        if row.startswith(_MODE):
            return replace(kept, appearance=row.removeprefix(_MODE))
        if row.startswith(_PAIR):
            side = "auto" if kept.appearance == "terminal" else kept.appearance
            return replace(kept, theme=row.removeprefix(_PAIR), appearance=side)
        if row.startswith(_LANG):
            return replace(kept, language=row.removeprefix(_LANG))
        return kept

    def _shows_as(self, kept: own.Kept) -> None:
        """Draws the interface as it would be with something kept, and says its texts so.

        Not its theme where `TEXTUAL_THEME` or `NO_COLOR` says what that is: the page says so
        instead, and what is chosen is still kept for when neither is set.

        Args:
          kept: What to show: what is kept, or what the cursor is on.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        themes = showing.available_themes
        if not own.overridden(os.environ, themes):
            theme = humanfia.chosen(os.environ, themes, kept.looks())
            if showing.theme != theme:
                showing.theme = theme
        speak(kept.speaks(os.environ))

    def _puts_back(self) -> None:
        """Draws the interface as kept again, on the way out of the themes or the language.

        What the cursor was on when the page was left is not what was chosen. Nothing is done
        on the way out of any other page: nothing there was shown.
        """
        if not self._home and self._tab in (_THEMES, _LANGUAGE):
            self._shows_as(self._kept)

    def _keeps(self, row: str) -> None:
        """Keeps the theme, the side or the language of one row, at once: nothing of it is held.

        Args:
          row: The row, by id.
        """
        chosen = self._candidate(row)
        self._kept = own.keep(
            theme=chosen.theme, appearance=chosen.appearance, language=chosen.language
        )
        self._said = escape(t("Saved"))
        self._fill()

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
            self._home or self._tab in (_DAEMONS, _ACCOUNTS, _MACHINES, _NOUS, _BACKUP)
        )

    def _page_title(self) -> tuple[str, str]:
        """What the page open is called, and what is kept there in a line."""
        return _cards()[_NAMES[self._tab]]

    # -- The way across the top -----------------------------------------------------------

    def crumb(self) -> str:
        """`/settings`, or the page open in it, which is what a menu opened from it is in."""
        return "/settings" if self._home else escape(self._page_title()[0])

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

    def _about(self) -> str:
        """What the screen of pages, or the page open, says it is, as markup."""
        if self._home:
            return escape(
                t(
                    "Every setting is here. A change to a daemon or workspace setting "
                    "is held until saved, while a theme or language is kept as soon as "
                    "it is chosen."
                )
            )
        listed = {
            _DAEMONS: self.DAEMONS_ABOUT,
            _ACCOUNTS: self.ACCOUNTS_ABOUT,
            _MACHINES: self.MACHINES_ABOUT,
            _NOUS: self.NOUS_ABOUT,
            _BACKUP: self.BACKUP_ABOUT,
        }
        if self._tab in listed:
            return t(listed[self._tab], spec="cli@account/model")
        if self._tab == _THEMES:
            said = t(
                "The theme under the cursor is shown as you move through the list and "
                "kept once chosen. Auto follows the terminal's background, light or dark."
            )
        elif self._tab == _LANGUAGE:
            said = t(
                "System follows the language this terminal is set to. What a daemon, "
                "a flow or an agent wrote stays as it was written."
            )
        elif self._tab == _NOTIFICATIONS:
            said = t("Of every daemon, as they happen.")
        elif self._tab == _DIRECTORY:
            said = f"{_shortly(self._workspace)}{_DOT}{self._page_title()[1]}"
        else:
            said = self._page_title()[1]
        return escape(said)

    def _fill(self) -> None:
        """Puts up the screen of pages, or the page that is open, and the bar under it.

        On the themes and the language, what the cursor is on is shown first, so that the
        page itself is drawn in it.
        """
        if not self._home and self._tab in (_THEMES, _LANGUAGE):
            # The row the cursor is on, or the one it is about to be put on.
            self._shows_as(self._candidate(self.under() or self._was))
        self.query_one("#asked", Label).update(self.crumb())
        self.query_one("#about", Label).update(self._about())
        if self._home:
            self._fill_home()
        elif self._tab == _DAEMONS:
            self._fill_daemons()
        elif self._tab == _ACCOUNTS:
            self._fill_accounts()
        elif self._tab == _MACHINES:
            self._fill_machines()
        elif self._tab == _NOUS:
            self._fill_nous()
        elif self._tab == _BACKUP:
            self._fill_backups()
        elif self._tab == _USAGE:
            self._fill_usage()
        elif self._tab == _THEMES:
            self._fill_themes()
        elif self._tab == _LANGUAGE:
            self._fill_language()
        else:
            self._fill_own()

    def _summary(self, page: int) -> str:
        """What one page's card says is in it, in a few words."""
        kept = self._kept
        if page == _THEMES:
            return (
                f"{t(humanfia.PRESETS[kept.theme].name)}{_DOT}"
                f"{self._modes()[kept.appearance][0]}"
            )
        if page == _LANGUAGE:
            return LANGUAGES[kept.language] if kept.language else t("System")
        if page == _EVERYWHERE:
            return (
                f"{t('Details')} {_said(self._details)}{_DOT}"
                f"{t('Error reports')} {_said(self._sentry)}"
            )
        if page == _NOTIFICATIONS:
            told = t("{n} of {total} on", n=sum(self._kinds.values()), total=len(KINDS))
            return f"{told}{_DOT}{t('System@@notifications')} {_said(self._system)}"
        if page == _DIRECTORY:
            return (
                f"{_shortly(self._workspace)}{_DOT}{t('Flow')} "
                f"{self._flow or t('none')}"
            )
        if page == _DAEMONS:
            return t("{n} daemons", n=len(self._daemons) + 1)
        if page == _ACCOUNTS:
            return t("{n} accounts", n=len([one for one in self._accounts if one.name]))
        if page == _MACHINES:
            return t("{n} runtimes", n=len(self._saved_machines))
        if page == _BACKUP:
            return t("{n} targets", n=len(self._repos))
        if page == _USAGE:
            return self._usage_summary()
        return t("{n} nous", n=len(self._nous))

    def _pending(self, page: int) -> bool:
        """Whether one page is holding a change that saving would land."""
        if page == _EVERYWHERE:
            return (
                self._sentry,
                self._details,
                self._prefer,
                self._harness,
            ) != (
                self._sentry_was,
                self._details_was,
                self._prefer_was,
                self._harness_was,
            )
        if page == _NOTIFICATIONS:
            return (self._kinds, self._system) != (self._kinds_was, self._system_was)
        if page == _DIRECTORY:
            return self._forget or self._chat_agent != self._chat_agent_was
        if page == _ACCOUNTS:
            return bool(self._gone or self._edits)
        if page == _NOUS:
            return self._nous != self._nous_was
        if page == _BACKUP:
            return self._repos != self._repos_was
        return False

    def _holding(self) -> bool:
        """Whether any page is holding a change that saving would land.

        Read off what each page holds rather than off whether anything was ever changed: a
        switch turned on and back off again is nothing to save, and nothing to be asked about
        on the way out.
        """
        return any(self._pending(page) for page in _NAMES)

    def leaving(self) -> None:
        """Asks whether to save what is held, where anything still is, and leaves."""
        if not self._holding():
            self.dismiss(None)
            return
        self.asks_to_save()

    def _fill_home(self) -> None:
        """Puts up a card per page, under the group it is in: its name and what is in it.

        The groups are headings the arrows step over, and the cursor comes back to the card of
        the page it was last inside.
        """
        listing = self.query_one("#choices", OptionList)
        under = self.under()
        landing = under if under in PAGES else _NAMES[self._tab]
        cards, headed = _cards(), _groups()
        options: list[Option] = []
        for group, pages in GROUPS:
            if options:
                options.append(Option("", disabled=True))
            options.append(self._heading(headed[group]))
            for page in pages:
                title, blurb = cards[page]
                options.append(
                    Option(
                        self._carded(
                            title,
                            self._summary(_TABS[page]),
                            blurb,
                            here=page == landing,
                            pending=self._pending(_TABS[page]),
                        ),
                        id=f"={page}",
                    )
                )
        self._put(listing, options, landing)
        self._drawn = listing.highlighted
        self.query_one("#tuning", Label).update("")
        self._footed(Key("enter", t("Open")), Key("esc", t("Close")))

    def _carded(
        self, title: str, summary: str, blurb: str, *, here: bool, pending: bool
    ) -> str:
        """One card of the first screen: a square, the page's name, what is in it, what it is for.

        Args:
          title: What the page is called.
          summary: What is in it, in a few words, at the far end.
          blurb: What it is for, in a line under.
          here: Whether the cursor is on it.
          pending: Whether the page is holding a change that saving would land.

        Returns:
          The card, as markup.
        """
        unsaved = f"{humanfia.SQUARE} {t('Unsaved')}"
        taken = cell_len(summary) + (cell_len(unsaved) + 2 if pending else 0)
        pad = " " * max(2, self._across() - 5 - cell_len(title) - taken)
        right = _shade("$text-muted", summary, here=here) + (
            f"  {_shade('$warning', unsaved, here=here)}" if pending else ""
        )
        return (
            f" {_shade('$primary', humanfia.SQUARE, here=here)}  "
            f"[b]{escape(title)}[/]{pad}{right}\n"
            f"    {_shade('$text-muted', blurb, here=here)}"
        )

    # -- Themes and language -------------------------------------------------------------------

    @staticmethod
    def _modes() -> dict[str, tuple[str, str]]:
        """Which side of the theme in use is drawn: what each is called, and what it means."""
        return {
            "auto": (
                t("Auto"),
                t("Light or dark, whichever the terminal's background asks for"),
            ),
            "light": (t("Light"), ""),
            "dark": (t("Dark"), ""),
            "terminal": (
                t("Terminal"),
                t(
                    "The terminal's own sixteen colours on its own background, "
                    "whatever theme is in use"
                ),
            ),
        }

    def _side(self) -> str:
        """Which side of a preset its row is drawn a sample of: the one that would be shown."""
        side = self._kept.appearance
        if side in ("light", "dark"):
            return side
        return humanfia.side(os.environ)

    @staticmethod
    def _sample(pair: str, side: str) -> str:
        """One side of a preset drawn small: its text on its paper, and its three accents."""
        theme = humanfia.THEMES[humanfia.named(pair, side)]
        paper = theme.background
        accents = "".join(
            f"[{one} on {paper}]{humanfia.SQUARE}[/]"
            for one in (theme.primary, theme.accent, theme.variables["hmz-green"])
        )
        return f"[{theme.foreground} on {paper}] Aa [/]{accents}[on {paper}] [/]"

    def _in_use(self, *, used: bool, here: bool) -> str:
        """The mark before the row that is the one in use: a square, or the room for one."""
        return _shade("$primary", humanfia.SQUARE, here=here) if used else " "

    def _decided(self) -> str:
        """What the themes page says under its list where a variable decides the theme."""
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        name = own.overridden(os.environ, showing.available_themes)
        if not name:
            return ""
        return escape(
            t(
                "{name} is set in the environment and decides this while it is set.",
                name=name,
            )
        )

    def _fill_themes(self) -> None:
        """Puts up which side is drawn, then every preset, the ones in use marked.

        A preset's row carries a sample of it, in its own colours, of the side that would be
        shown; the whole interface is the larger sample, drawn as the cursor moves.
        """
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        kept, used = self._kept, t("In use")
        rows = [f"{_MODE}{one}" for one in own.APPEARANCES]
        rows += [f"{_PAIR}{one}" for one in humanfia.PRESETS]
        landing = self._lands(rows)
        options = [self._heading(t("Appearance"))]
        for mode, (named, about) in self._modes().items():
            held, on_ = f"{_MODE}{mode}", kept.appearance == mode
            here = held == landing
            options.append(
                Option(
                    self._listed(
                        named,
                        about,
                        here=here,
                        mark=self._in_use(used=on_, here=here),
                        tail=used if on_ else "",
                    ),
                    id=f"={held}",
                )
            )
        options += [Option("", disabled=True), self._heading(t("Presets"))]
        side, width = self._side(), self._across()
        for key, pair in humanfia.PRESETS.items():
            held, on_ = f"{_PAIR}{key}", kept.theme == key
            here, named = held == landing, t(pair.name)
            gap = " " * max(2, 24 - cell_len(named))
            tail = ""
            if on_:
                fill = " " * max(
                    2, width - 12 - cell_len(named) - len(gap) - cell_len(used)
                )
                tail = f"{fill}{_shade('$text-muted', used, here=here)}"
            options.append(
                Option(
                    f" {self._in_use(used=on_, here=here)} [b]{escape(named)}[/]{gap}"
                    f"{self._sample(key, side)}{tail}",
                    id=f"={held}",
                )
            )
        self._put(listing, options, landing)
        self._drawn = listing.highlighted
        said = self._said or self._decided()
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", t("Use")), Key("esc", t("Back")))

    def _fill_language(self) -> None:
        """Puts up the system's language and each the texts are written in, the one in use marked.

        A language is called what it calls itself, whatever the page is written in.
        """
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        kept, used = self._kept, t("In use")
        named = {"": t("System"), **LANGUAGES}
        landing = self._lands([f"{_LANG}{one}" for one in named])
        options: list[Option] = []
        for code, says in named.items():
            held, on_ = f"{_LANG}{code}", kept.language == code
            here = held == landing
            options.append(
                Option(
                    self._listed(
                        says,
                        "",
                        here=here,
                        mark=self._in_use(used=on_, here=here),
                        tail=used if on_ else "",
                    ),
                    id=f"={held}",
                )
            )
        self._put(listing, options, landing)
        self._drawn = listing.highlighted
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{self._said}[/]" if self._said else ""
        )
        self._footed(Key("enter", t("Use")), Key("esc", t("Back")))

    def _settings(self) -> list[_Setting]:
        """The rows of the general or the workspace page, as they are held now.

        Under a heading per thing they are about, the one changed most first: details are
        turned round while a run is read, the reporting once, if ever. The directory itself is
        no row: it is not set here, and the page says it across the top. Forgetting goes last,
        apart, as what undoes the rest does in any settings.
        """
        if self._tab == _NOTIFICATIONS:
            return [
                *(
                    _Setting(
                        kind,
                        named,
                        _word(self._kinds[kind]),
                        "",
                        _SWITCH,
                        group=t("Kinds"),
                    )
                    for kind, named in _kinds().items()
                ),
                _Setting(
                    _SYSTEM,
                    t("System@@notifications"),
                    _word(self._system),
                    t(
                        "Shows a system notification while the terminal is not in "
                        "front, or rings the bell where it cannot"
                    ),
                    _SWITCH,
                ),
            ]
        if self._tab == _DIRECTORY:
            return [
                _Setting(
                    _RUNS,
                    t("Flow"),
                    self._flow or t("none"),
                    t("{n} agents", n=self._roles),
                    _READ,
                ),
                _Setting(
                    _CHAT_AGENT,
                    t("Default agent"),
                    written(self._chat_agent) if self._chat_agent else t("Not set"),
                    t("The agent a new chat in this folder talks to"),
                    _SETS,
                    t("in the next chat")
                    if self._chat_agent != self._chat_agent_was
                    else "",
                ),
                _Setting(
                    _ARCHIVED,
                    t("Archived chats"),
                    "",
                    t("Chats of this folder that were put away"),
                    _SAYS,
                ),
                _Setting(
                    _FORGET,
                    t("Forget"),
                    _word(self._forget),
                    t("Forget how {n} flows were set up here?", n=self._flows),
                    _SWITCH,
                    t("on next launch") if self._forget else "",
                ),
            ]
        return [
            _Setting(
                _DETAILS,
                t("Details"),
                _word(self._details),
                t("Tool calls and thinking"),
                _SWITCH,
            ),
            _Setting(
                _PREFER,
                t("When $name is both"),
                self._prefer,
                t(
                    "What $name starts in a chat where a native skill and a flow "
                    "share the name"
                ),
                _PICK,
            ),
            _Setting(
                _HARNESS,
                t("Harness sessions"),
                _word(self._harness),
                t(
                    "/resume in a chat lists the sessions each harness had of its own "
                    "in this folder, to continue as chats"
                ),
                _SWITCH,
            ),
            _Setting(
                _SENTRY,
                t("Error reports"),
                _word(self._sentry),
                t("Report Humanize’s own failures"),  # noqa: RUF001 -- the page's
                _SWITCH,
            ),
            _Setting(
                _SENT,
                t("What is sent"),
                "",
                t("What error reports include and what they leave out"),
                _SAYS,
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
        if one.kind == _READ:
            return _shade("$text-muted", one.value, here=here), cell_len(one.value)
        if one.kind in (_SWITCH, _PICK):
            said, cells = _chip(
                one.value, _DROPS, here=here, toggles=one.kind == _SWITCH
            )
        else:
            said, cells = _chip(
                one.value if one.kind == _SETS else "", _OPENS, here=here
            )
        # Counted there in letters: a value in a script two cells wide is as much wider.
        return said, cells + cell_len(one.value) - len(one.value)

    def _fill_own(self) -> None:
        """Puts up the general, notifications or workspace page: a row per setting.

        Its value at the far end and what it is under it; a heading, where the rows have one,
        is a row the arrows step over.
        """
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        rows = self._settings()
        held = [one.held for one in rows]
        landing = self._was if self._was in held else held[0]
        options: list[Option] = []
        group = ""
        for one in rows:
            if one.group != group:
                if options:
                    options.append(Option("", disabled=True))
                group = one.group
                if group:
                    options.append(self._heading(group))
            here = one.held == landing
            options.append(
                Option(
                    self._set_to(
                        one.named,
                        self._chip(one, here=here),
                        one.about,
                        here=here,
                        note=one.note,
                    ),
                    id=f"={one.held}",
                )
            )
        self._put(listing, options, landing)
        self._was = landing
        self._drawn = listing.highlighted
        said = self._said
        if (
            not said
            and self._tab == _EVERYWHERE
            and self._overridden
            and self._sentry == self._sentry_was
        ):
            said = escape(
                t(
                    "{name} is set in the environment and decides this while it is set.",
                    name=SAYS,
                )
            )
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        kind = next((one.kind for one in rows if one.held == landing), _READ)
        does = {
            _SWITCH: t("Choose"),
            _PICK: t("Choose"),
            _SAYS: t("Open"),
            _SETS: t("Open"),
        }.get(kind)
        self._footed(*((Key("enter", does),) if does else ()), Key("esc", t("Back")))

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
            _DAEMONS: self._daemon_actions,
            _ACCOUNTS: self._account_actions,
            _MACHINES: self._machine_actions,
            _NOUS: self._nous_actions,
            _BACKUP: self._backup_actions,
            _USAGE: self._usage_actions,
            # Nor do the themes and the language hold anything: each is kept as chosen.
            _THEMES: self._usage_actions,
            _LANGUAGE: self._usage_actions,
        }.get(self._tab, lambda: [self._saves_all()])()

    def _footed(self, *keys: Key) -> None:
        """Says the keys, with esc saying whether it closes the menu or comes out of a page.

        Args:
          keys: The page's keys, for its list.
        """
        back = Key("esc", t("Close") if self._home else t("Back"))
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
            self._opens(_TABS[held])
            return
        self._takes(held)

    def _takes(self, held: str) -> None:
        """Does what one row is for, which each page says for itself.

        Args:
          held: The row, by the id it answers with.
        """
        if self._tab == _DAEMONS:
            self._took_daemon(held)
        elif self._tab == _ACCOUNTS:
            self._took_account(held)
        elif self._tab == _MACHINES:
            self._took_machine(held)
        elif self._tab == _NOUS:
            self._took_nous(held)
        elif self._tab == _BACKUP:
            self._took_backup(held)
        elif self._tab in (_THEMES, _LANGUAGE):
            self._keeps(held)
        elif held == _SENT:
            self._said = escape(
                t(
                    "Sent: {sent}. Never sent: {kept}.",
                    sent="; ".join(SENT),
                    kept="; ".join(KEPT),
                )
            )
            self._fill()
        elif held == _CHAT_AGENT:
            self._sets_chat_agent()
        elif held == _ARCHIVED:
            self._opens_archived()

    def drops(self, row: str) -> bool:
        """Whether a row of the general or workspace page has its values dropped under it.

        Args:
          row: The row, by id.

        Returns:
          True for a switch, and for what a chat's `$` prefers.
        """
        if not self._home and self._tab == _USAGE:
            return self._drops_usage(row)
        return (
            not self._home
            and self._tab in (_EVERYWHERE, _NOTIFICATIONS, _DIRECTORY)
            and (row in _SWITCHES or row == _PREFER)
        )

    def dropping(self, row: str) -> Drop:
        """A row's values, what each means, and which it is held at.

        Args:
          row: The row, by id.

        Returns:
          The list, opening on the answer it is not, so that enter twice turns it round.
        """
        if self._tab == _USAGE:
            return self._dropping_usage(row)
        named = next(one.named for one in self._settings() if one.held == row)
        if row == _PREFER:
            means = _prefers()
            return Drop(
                named,
                [Value(one, one, meant) for one, meant in means.items()],
                self._prefer,
                cursor=next(one for one in means if one != self._prefer),
            )
        now = self._switched(row)
        return switched(named, _word(now) if now is not None else "")

    def dropped(self, row: str, picked: str) -> None:
        """Holds a row at the value picked.

        Args:
          row: The row, by id.
          picked: `on` or `off`, or what a chat's `$` prefers.
        """
        on_ = picked == _YES
        if self._tab == _USAGE:
            self._dropped_usage(row, picked)
        elif row == _PREFER:
            self._prefer = "flow" if picked == "flow" else "native"
        elif row in self._kinds:
            self._kinds[row] = on_
        elif row == _SYSTEM:
            self._system = on_
        elif row == _SENTRY:
            self._sentry = on_
        elif row == _DETAILS:
            self._details = on_
        elif row == _HARNESS:
            self._harness = on_
        else:
            self._forget = on_
        self._said = ""

    def _switched(self, held: str) -> bool | None:
        """What one switch is held at now."""
        return {
            _SENTRY: self._sentry,
            _DETAILS: self._details,
            _HARNESS: self._harness,
            _FORGET: self._forget,
            _SYSTEM: self._system,
            **self._kinds,
        }[held]

    @work
    async def _sets_chat_agent(self) -> None:
        """Sets up the agent a new chat here talks to, part by part, on the agent sheet.

        As a flow's agent role is set up (Section 16.5 of [TUI]): a chat's agent is one more
        agent this directory remembers, but no flow's, so no role rules a CLI out.
        """
        if self.opening():
            return
        try:
            chosen = await self._agent_set_up(
                "the chat's agent", self._chat_agent or Runs("")
            )
        finally:
            self.opened()
        if chosen is None or chosen == self._chat_agent:
            return
        self._chat_agent, self._said = chosen, ""
        self.changed()
        self._fill()

    @work
    async def _opens_archived(self) -> None:
        """Opens the archived chats of this directory, where one picked is put back.

        Written by the daemon as each is picked (Section 19.11.2 of [TUI]): nothing of it is
        held for the save.
        """
        if self.opening():
            return
        try:
            await cast(
                "App[None]",
                self.app,  # pyright: ignore[reportUnknownMemberType]
            ).push_screen_wait(Archived(self._workspace))
        finally:
            self.opened()

    async def _agent_set_up(self, named: str, runs: Runs) -> Runs | None:
        """Sets one agent up on the sheet every agent is set up on, and answers it.

        Args:
          named: Whose agent it is, which the sheet is titled `Set up` with.
          runs: What it runs now, which the sheet opens on.

        Returns:
          The agent, or None where the sheet was walked out of or left without a model:
          what was there before stays.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        chosen = await showing.push_screen_wait(
            Agent(named, runs, self._offered, unavailable=self._unavailable)
        )
        return chosen if chosen is not None and complete(chosen) else None

    def _applies_chat(self, told: list[str]) -> None:
        """Writes down what a chat's `$` prefers and this directory's chat agent, if changed.

        Written here rather than answered for the interface to write: neither changes what
        the interface has on the screen, only what the next chat, or the next `$` line in one,
        reads. The chat agent is not written where this directory is being forgotten in the
        same save: forgetting is everything it remembers, that agent among it.

        Args:
          told: What happened, for the transcript; a write that failed is said there.
        """
        settings = _hmz().settings
        if self._prefer != self._prefer_was:
            try:
                settings.chat_prefer = self._prefer
            except OSError as why:
                told.append(_unsaved(t("When $name is both"), why))
        if self._harness != self._harness_was:
            try:
                settings.harness_sessions = self._harness
            except OSError as why:
                told.append(_unsaved(t("Harness sessions"), why))
        agent = self._chat_agent
        if agent is not None and agent != self._chat_agent_was and not self._forget:
            try:
                settings.chat_agent = agent
            except OSError as why:
                told.append(_unsaved(t("Default agent"), why))

    def applied(self) -> None:
        """Lands what every page was holding, and answers with what was changed."""
        told = list(self._told)
        self._applies_accounts(told)
        self._applies_nous(told)
        self._applies_backups(told)
        self._applies_chat(told)
        if self._pending(_NOTIFICATIONS):
            try:
                # What was changed here alone: the web interface may have changed the rest.
                prefer(
                    {
                        kind: on
                        for kind, on in self._kinds.items()
                        if on != self._kinds_was[kind]
                    },
                    system=self._system if self._system != self._system_was else None,
                )
            except OSError as why:
                told.append(_unsaved(t("Notifications"), why))
        self.dismiss(
            Adjusted(
                enable_sentry=self._sentry
                if self._sentry is not None and self._sentry != self._sentry_was
                else None,
                details=self._details if self._details != self._details_was else None,
                forget=self._forget,
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
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        self._puts_back()
        # The line of keys under the log is said in whatever language was just kept.
        hints = getattr(getattr(showing, "shell", None), "hints", None)
        if callable(hints):
            hints()
        if said is not None and not self._answered:
            showing.post_message(self.Settled(said))
        return super().dismiss(said)
