"""`/flow`: the flows there are to run, where more come from, and what each one runs on.

Drawn and worked as every menu is (:class:`hmz.tui.pick.Sheet`), `/settings` among them: a
screen of its own, the way here across the top with each step of it a way back, a list in a box
with a block cursor, and what is done about the list rather than to one row of it --
installing, updating, searching, saving -- a bar of buttons under it. What is here is what is
this menu's own: its pages, and what each does.

Two pages under the first screen. **Installed** is what there is to run: the flows built into
humanize, the ones installed out of a flowverse with the release each is at and a mark where a
newer one is listed, and the flows of your own. Enter on one goes into what it runs on -- an
agent or an environment per role it declares, what it takes, what a run of it may spend and
whether it is profiled -- which is held until the menu is saved, as everything a menu holds
is. **Flowverses** is where more come from: each index, the flows it lists, and each flow's
releases newest first, any one of which is installed, switched to or taken away there and then.
What runs git is done as it is asked for rather than held -- something already cloned is not a
draft -- and said under the list and, once the menu is left, in the transcript.

Nothing reaches a network to draw a page. An index is read off the clone the last fetch left,
and fetching one is a button.
"""

# The chrome is every sheet's own, and so are the pieces it is drawn with.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

import semver
from rich.markup import escape
from textual import on, work
from textual.message import Message
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from hmz.runtime import telemetry
from hmz.runtime.kept import Runs, read_back

from .pick import (
    _ACT_ADD,
    _ACT_REMOVE,
    _ACT_SAVE,
    _APART_MARK,
    _DOT,
    _DROPS,
    _INFORCE,
    _NO,
    _OPENS,
    _YES,
    Action,
    Agent,
    Budgeted,
    Chosen,
    Configures,
    Declared,
    Drafts,
    Drop,
    Form,
    Key,
    Placing,
    Popup,
    Question,
    Sheet,
    _chip,
    _hmz,
    _many,
    _popup,
    _shade,
    bad,
    budget_of,
    complete,
    declared_of,
    iffy,
    params_model,
    params_of,
    setting,
    settled,
    spent,
    switched,
    why_not,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from pydantic import BaseModel
    from textual.await_complete import AwaitComplete

    from hmz.coganchor.backends import Model
    from hmz.flows import Budget
    from hmz.runtime.flowing import Flowverse, Index, Installed, Offer, Release


__all__ = ["HOME", "INSTALLED", "VERSES", "Fetches", "Flows", "Lists"]

#: The pages, by what each is called on the screen and in the code alike. The first screen of
#: the two that are lists; what is installed; what a flow runs on; the flowverses; one
#: flowverse's flows; and one flow's releases.
HOME, INSTALLED, ROLES, VERSES, VERSE, RELEASES = (
    "home",
    "installed",
    "roles",
    "verses",
    "verse",
    "releases",
)

#: The page each goes back out to.
_UP = {
    INSTALLED: HOME,
    VERSES: HOME,
    ROLES: INSTALLED,
    VERSE: VERSES,
    RELEASES: VERSE,
}

#: The rows of the roles page that are about the run rather than any role: what the flow
#: itself takes, what a run may spend, and whether it is profiled as well as traced. Each under
#: a mark no name has, since a row id is otherwise an agent's place among the roles or an
#: environment's name.
_PARAMS = f"{_APART_MARK}params"
_BUDGET = f"{_APART_MARK}budget"
_PROFILING = f"{_APART_MARK}profile"

#: What each button under a page is known by, beside the ones `/settings` has.
_ACT_MORE, _ACT_UPDATE, _ACT_UNINSTALL, _ACT_COPY = (
    "more",
    "update",
    "uninstall",
    "copy",
)
_ACT_INSTALL, _ACT_FETCH = "install", "fetch"

#: What says a row's flow is behind what its index lists, and what says a release is one.
_NEWER, _PRE = "↑", "prerelease"

#: The cards of the first screen: what each page is called, its mark, and what it is for.
_CARDS = (
    (
        INSTALLED,
        "Installed",
        "▶",
        "flows ready to run: built in, installed, or your own",
    ),
    (VERSES, "Flowverses", "⑂", "indexes of flows to install, update and add to"),
)


@runtime_checkable
class Lists(Protocol):
    """A sheet holding what it read off the disk about flows: installed, and listed.

    The one thing anything outside it needs: the list was read once, and a fetch or an install
    landing underneath makes it wrong. This is how such a sheet is told so, without whatever
    fetched having to know which sheets there are or how each keeps its list.
    """

    def reread(self) -> None:
        """Drops what was read off the disk and draws the list again."""


class Removes(Popup):
    """Whether to take a flowverse away, and everything installed out of it with it.

    A box over the flowverses rather than a sheet, as every question that arrives is: what goes
    with it said under the question, and the two answers its buttons.
    """

    CSS = _popup("Removes")

    def __init__(self, verse: str, flows: int) -> None:
        """Initializes the question.

        Args:
          verse: The flowverse.
          flows: How many flows are installed out of it, which go with it.
        """
        super().__init__()
        self.asked = f"Remove {verse}?"
        gone = f" and {_many(flows, 'installed flow')}" if flows else ""
        self.about = f"Takes its index away{gone}."

    def rows(self) -> list[tuple[str, str, str]]:
        """Taking it away, or keeping it."""
        return [("yes", "remove", "remove it now"), ("no", "keep", "keep it")]


class Fetches(Form[tuple[str, str]]):
    """Where a flowverse is, and what it is to be called here.

    A form rather than a list: there is nothing to pick, both rows being written where they
    stand. The name is second because it is the one with an answer already: a flowverse is
    called what its repository is called.
    """

    def asked(self) -> list[Question]:
        """The repository, and what to call it here."""
        return [
            Question(
                "repository",
                "repository",
                "a URL, or owner/repo for one on GitHub",
                needed=not self._typed_in.get("repository", "").strip(),
            ),
            Question(
                "name",
                "name",
                "flowverse name, or leave blank for the repository name",
            ),
        ]

    def done_about(self) -> str:
        """What answering it does."""
        return "clones its index; install flows from it next"

    def _ask(self) -> None:
        """Says what a flowverse is."""
        self.query_one("#asked", Label).update("Add a flowverse")
        self.query_one("#about", Label).update(
            "A git repository indexing flows: flows/<flow>/<version>/flow.yaml, one "
            "manifest per release. Its index is cloned under ~/.hmz/flowverses, and "
            "the flows you install from it are offered under the flowverse name."
        )
        self._fill()

    def action_done(self) -> None:
        """Answers with where it is and what to call it, once there is somewhere to fetch."""
        url = self._typed_in.get("repository", "").strip()
        name = self._typed_in.get("name", "").strip()
        if not url:
            self._wrong = "repository URL is required"
            self._fill()
            return
        if name:
            try:
                _hmz().verses.where(name)
            except ValueError as why:
                self._wrong = str(why)
                self._fill()
                return
        self.dismiss((url, name))


class Flows(Drafts[Chosen]):
    """Which flow runs, what each of its roles is, and where flows come from: `/flow`.

    Opened on what is installed, with the first screen -- the two pages, as cards -- a step
    out: what somebody types `/flow` for is a flow to run, and the flowverses are where they go
    when the one they want is not there yet. Opened straight into what a flow runs on for a
    flow that was named, and while one runs, where choosing another is not offered: a flow is
    chosen in order to be started, and there is one going. Esc then leaves rather than going
    back to a list nobody walked through.

    What it holds is a draft of the flow and its roles, landing together from the save button
    or when saving is confirmed on the way out. What is installed, updated, fetched or taken
    away lands as it is asked for.
    """

    class Told(Message):
        """What was done as it was asked for -- installed, fetched, removed -- for the transcript.

        Posted to the interface rather than answered: the menu answers with the flow it was
        saved holding, or with nothing, and what happened to the flowverses happened either way.
        """

        def __init__(self, lines: tuple[str, ...]) -> None:
            """Carries the lines.

            Args:
              lines: What to say, as markup, in the order it happened.
            """
            super().__init__()
            self.lines = lines

    def __init__(
        self,
        flow: str,
        runs: Mapping[str, Runs],
        params: BaseModel | None,
        agents: dict[str, tuple[Model, ...]],
        kept: dict[str, Any],
        *,
        envs: Mapping[str, str] | None = None,
        budget: Budget | None = None,
        profile: bool = False,
        unavailable: frozenset[str] = frozenset(),
        running: bool = False,
        inside: bool = False,
        page: str = INSTALLED,
    ) -> None:
        """Initializes the menu on what is set up now.

        Args:
          flow: The flow running now, or the one this workspace is set up to run.
          runs: What each of its agent roles runs, by role.
          params: What the flow itself is set up with, for one that takes params.
          agents: The backends offered here, and what each of them says it runs.
          kept: What each flow was last set up with here, by flow -- read when the draft flow
            changes, so that turning to a flow this workspace has run finds it as it was left.
          envs: Where each of its environment roles is, by role.
          budget: What a run of it may spend here, or None for none yet.
          profile: Whether a run of it here is profiled as well as traced.
          unavailable: The optional backends among them that still need installing.
          running: Whether a flow is running, which is what takes the other pages away.
          inside: Whether to open on what the flow runs on rather than on a list, for a menu
            opened already naming one -- a flow that was named has been chosen.
          page: Which page to open on otherwise: what is installed, or the flowverses.
        """
        super().__init__()
        self._agents = dict(agents)
        self._unavailable = unavailable
        self._kept = kept
        self._flow: str = flow
        #: What the flow declares, read once per flow rather than on every redraw: reading
        #: it means importing the flow, and the roles page is drawn on every keystroke.
        self._declared: Declared | None = declared_of(flow)
        self._runs: dict[str, Runs]
        self._envs: dict[str, str]
        self._params: BaseModel | None
        self._budget: Budget | None
        self._profile: bool
        if runs:
            self._runs = self._fitted(dict(runs))
            self._envs = dict(envs or {})
            self._params = params
            self._budget = budget
            self._profile = profile
        else:
            # A flow the interface is not set up on, opened straight into: what it was last
            # set up with here is what it opens holding, exactly as turning to it would be.
            self._runs = self._fitted(self._remembered(flow))
            self._envs = self._placed(flow)
            self._params = params_of(flow, self._held(flow).get("params") or {})
            self._budget = budget_of(flow)
            self._profile = _hmz().settings.profile(flow)
        #: What the menu opened holding, which it goes back to where the flow it is holding
        #: instead is uninstalled from under it: a draft of a flow that is gone is nothing
        #: to save.
        self._opened = (
            flow,
            self._declared,
            dict(self._runs),
            dict(self._envs),
            self._params,
            self._budget,
            self._profile,
        )
        #: Whether what the flow runs on is the whole of this menu, there being no list
        #: behind it to step back to: while a flow runs, and for a flow that was named.
        self._only = running or inside
        self._page = ROLES if self._only else page
        #: The flowverse and the flow of it being read, on the pages about one of them.
        self._verse = ""
        self._listed = ""
        #: What was read off the disk, once per opening and again after anything lands:
        #: reading what is installed means importing every flow of it.
        self._offers: list[Offer] | None = None
        self._records: dict[tuple[str, str], Installed] | None = None
        self._newer: dict[tuple[str, str], str] | None = None
        self._indexes: dict[str, Index] = {}
        self._verses: list[Flowverse] | None = None
        #: Which indexes have something written into them, as git said, or None before
        #: it has been asked.
        self._edited: dict[str, bool] | None = None
        #: The row each page's cursor was last on, by id, for when it is gone back into.
        self._cursors: dict[str, str] = {}
        #: Something just made, which the cursor goes to next time the page is drawn.
        self._aim = ""
        #: What became of the last thing done, said under the list.
        self._said = ""
        #: What is being done off the loop now -- an install, a fetch -- or "" for nothing:
        #: one at a time, and said under the list while it runs.
        self._busy = ""
        #: What is worth saying again in the transcript once the menu is done with.
        self._told: list[str] = []

    @property
    def _inside(self) -> bool:
        """Whether what is open is what one flow runs on, rather than a list."""
        return self._page == ROLES

    # -- What the draft holds ----------------------------------------------------------------

    def _fitted(self, runs: Mapping[str, Runs]) -> dict[str, Runs]:
        """One agent per agent role the flow declares, whatever there was to fill it with.

        A role nothing was remembered for and nothing falls back on still has a row: this is
        where it is set up, and a role with no row is a role nobody can answer.

        Args:
          runs: What there is, by role.

        Returns:
          One apiece, by role, in the order the flow declares them.
        """
        declared = self._declared
        if declared is None:
            return dict(runs)
        held = settled(runs, declared.agents, self._agents)
        return {role: held.get(role, Runs("")) for role in declared.roles}

    def _held(self, name: str) -> dict[str, Any]:
        """What one flow was last set up with here, which is nothing for one never run."""
        held = self._kept.get(name)
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def _remembered(self, name: str) -> dict[str, Runs]:
        """What one flow's agent roles were last set up as here, by role."""
        agents = self._held(name).get("agents")
        if not isinstance(agents, dict):
            return {}
        held: dict[str, Runs] = {}
        for role, said in cast("dict[str, Any]", agents).items():
            runs = read_back(said)
            if runs is not None:
                held[str(role)] = runs
        return held

    def _placed(self, name: str) -> dict[str, str]:
        """Where one flow's environment roles were last said to be here, by role."""
        envs = self._held(name).get("envs")
        if not isinstance(envs, dict):
            return {}
        return {
            str(role): str(said)
            for role, said in cast("dict[str, Any]", envs).items()
            if isinstance(said, str)
        }

    def _roles(self) -> tuple[str, ...]:
        """The agent roles somebody chooses an agent for, in the flow's own order."""
        return self._declared.roles if self._declared is not None else ()

    def _places(self) -> tuple[str, ...]:
        """The environment roles somebody names a place for, in the flow's own order."""
        return self._declared.places if self._declared is not None else ()

    # -- What is read off the disk -----------------------------------------------------------

    def _all(self) -> list[Offer]:
        """Every flow there is to run, read once."""
        if self._offers is None:
            self._offers = _hmz().flows.all()
        return self._offers

    def _installs(self) -> dict[tuple[str, str], Installed]:
        """Every flow installed out of an index, by flowverse and flow, read once."""
        if self._records is None:
            self._records = {
                (one.verse, one.name): one for one in _hmz().verses.installed()
            }
        return self._records

    def _updates(self) -> dict[tuple[str, str], str]:
        """The newer release each installed flow's index lists, by flowverse and flow."""
        if self._newer is None:
            self._newer = {
                (one.installed.verse, one.installed.name): one.version
                for one in _hmz().verses.updates()
            }
        return self._newer

    def _index(self, verse: str) -> Index:
        """What one flowverse's index lists, read once."""
        held = self._indexes.get(verse)
        if held is None:
            held = self._indexes[verse] = _hmz().verses.index(verse)
        return held

    def _places_of_flows(self) -> list[Flowverse]:
        """Every flowverse but your own two, which are places rather than indexes, read once.

        A directory under the flowverses home that is not a clone of anything -- what a clone
        killed partway leaves -- is one of them, with nothing to fetch: listed, so that it can
        be removed.
        """
        from hmz.runtime.flowing import MINE

        if self._verses is None:
            self._verses = [one for one in _hmz().verses.all() if one.name not in MINE]
        return self._verses

    def _forgets(self) -> None:
        """Drops everything read off the disk, which something landing has made wrong."""
        self._offers = self._records = self._newer = self._verses = None
        self._edited = None
        self._indexes = {}

    def reread(self) -> None:
        """Drops what was read before a fetch landed, and draws the page again.

        What the flow in force declares too: an update may have just changed it.
        """
        self._forgets()
        if self._flow:
            self._declared = declared_of(self._flow)
            self._runs = self._fitted(self._runs)
        self._fill()

    @staticmethod
    def _module(offer: Offer) -> tuple[str, str]:
        """Which installed flow an offer is of: its flowverse, and the flow's own name.

        A module that holds several flows offers `<flow>:<inside>` for each but the one named
        after it, and all of them are the one install.
        """
        from hmz.runtime.flowing.index import split

        return split(offer.name.partition(":")[0])

    def _builtin(self, offer: Offer) -> bool:
        """Whether an offer is one of the flows built into humanize."""
        from hmz.runtime.flowing import OFFICIAL

        return offer.whose == OFFICIAL and self._module(offer) not in self._installs()

    # -- Opening and drawing -----------------------------------------------------------------

    def _ask(self) -> None:
        """Puts up the page it opened on."""
        self._fill()

    def _key(self) -> str:
        """Which list the page drawn is, for remembering where its cursor was."""
        if self._page == VERSE:
            return f"{VERSE}:{self._verse}"
        if self._page == RELEASES:
            return f"{RELEASES}:{self._verse}/{self._listed}"
        return self._page

    def _goes(self, page: str, *, verse: str = "", listed: str = "") -> None:
        """Turns to another page, leaving what was typed and said on the one left behind.

        Args:
          page: The page.
          verse: The flowverse it is about, for the pages about one.
          listed: The flow of it, for the page of one flow's releases.
        """
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        # A search goes with the page it was typed into, and the box with it.
        self._said = self._typed = ""
        self._searching = False
        listing.clear_options()
        self._drawn = None
        self._page = page
        if verse:
            self._verse = verse
        if listed:
            self._listed = listed
        self._fill()
        self._settles_focus()

    def _follows(self, listing: OptionList) -> None:
        """Takes which row the cursor is on off the list, by its id, for the page drawn."""
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            held = str(listing.get_option_at_index(at).id or "").removeprefix("=")
            if held:
                self._cursors[self._key()] = held

    def _lands(self, items: Sequence[str], default: str = "") -> str:
        """Which row the cursor goes on as a page is put up again, by its id.

        The first thing a search found while one is narrowing the list; else something just
        made; else the row it was on; else the one the page says it opens on; else the first.

        Args:
          items: The rows that can be landed on, by id, as a search has narrowed them.
          default: The row to open on where the cursor has not been on this page yet.

        Returns:
          The id, or "" for a list with nothing in it.
        """
        sought = self._sought(items)
        if sought is not None and sought in items:
            return sought
        if self._aim in items:
            # Something just added from a button is what somebody wants to look at next, so
            # the focus comes back to the list it landed on.
            landing, self._aim = self._aim, ""
            self.call_after_refresh(self.query_one("#choices", OptionList).focus)
            return landing
        was = self._cursors.get(self._key(), "")
        if was in items:
            return was
        if default in items:
            return default
        return items[0] if items else ""

    def _put(self, rows: list[Option | None], landing: str) -> None:
        """Puts the rows up with the cursor on one of them, by its id."""
        listing = self.query_one("#choices", OptionList)
        listing.set_options(rows)
        options = listing.options
        listing.highlighted = next(
            (at for at, one in enumerate(options) if one.id == f"={landing}"),
            next((at for at, one in enumerate(options) if not one.disabled), None),
        )
        self._drawn = listing.highlighted
        if landing:
            self._cursors[self._key()] = landing

    def _fill(self) -> None:
        """Puts up the page that is open, what it is, and -- as it lands -- the bar under it.

        Where the cursor is is read first, since what the bar's buttons say and whether they
        can be pressed is about the row it is on; each page ends with :meth:`_footed`, which
        draws the bar and the way here from what the page now is.
        """
        self._follows(self.query_one("#choices", OptionList))
        self.query_one("#asked", Label).update(self.crumb())
        self.query_one("#about", Label).update(self._about())
        {
            HOME: self._fill_home,
            INSTALLED: self._fill_installed,
            ROLES: self._fill_roles,
            VERSES: self._fill_verses,
            VERSE: self._fill_verse,
            RELEASES: self._fill_releases,
        }[self._page]()

    # -- The way across the top -------------------------------------------------------------

    def _path(self) -> list[str]:
        """The pages above the one open, outermost first: none where it is the whole menu."""
        if self._only:
            return []
        path: list[str] = []
        up = _UP.get(self._page)
        while up is not None:
            path.insert(0, up)
            up = _UP.get(up)
        return path

    def _title(self, page: str) -> str:
        """What one page is called across the top."""
        return {
            HOME: "/flow",
            INSTALLED: "Installed",
            ROLES: self._flow,
            VERSES: "Flowverses",
            VERSE: self._verse,
            RELEASES: self._listed,
        }[page]

    def crumb(self) -> str:
        """The page open, which is what a sheet opened from it -- an agent, a budget -- is in."""
        return escape(self._title(self._page))

    def crumbs(self) -> list[str]:
        """The pages on the way to the one open, each a way back to it."""
        return [escape(self._title(page)) for page in self._path()]

    def climbs_to(self, depth: int) -> None:
        """Goes back to one of the pages on the way here, from a click on it across the top.

        Args:
          depth: Which, counting from the outermost.
        """
        path = self._path()
        if depth < len(path):
            self._goes(path[depth])

    def _about(self) -> str:
        """What the page open is for, in a line."""
        return {
            HOME: "Flows to run, and the flowverses more are installed from.",
            INSTALLED: "Flows ready to run here: pick one to set it up and run it, or "
            "install more from a flowverse.",
            ROLES: "Configure each role: an agent (CLI, account, model and effort) or an "
            "environment; then what the flow takes and what a run may spend.",
            VERSES: "Indexes of flows to install, cloned under ~/.hmz/flowverses. "
            "Fetching, adding and removing one happen at once.",
            VERSE: f"Flows {escape(self._verse)} lists, at their newest release. Open one "
            "for its others; installing happens at once.",
            RELEASES: f"Releases of {escape(self._listed)}, newest first. Pick one to "
            "install it, or to switch to it.",
        }[self._page]

    def _tuned(self, said: str) -> None:
        """Says something under the list, or nothing: what is going on, else what was said."""
        if self._busy:
            said = f"{escape(self._busy)}…" + (f"{_DOT}{said}" if said else "")
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )

    # -- The first screen --------------------------------------------------------------------

    def _fill_home(self) -> None:
        """Puts up a card per page: its mark, its name, what is in it, and what it is for."""
        landing = self._lands([page for page, _, _, _ in _CARDS], INSTALLED)
        cards: list[Option | None] = []
        for page, title, icon, blurb in _CARDS:
            cards.append(
                Option(
                    self._card(
                        icon, title, self._summary(page), blurb, here=page == landing
                    ),
                    id=f"={page}",
                )
            )
            cards.append(None)
        self._put(cards[:-1], landing)
        self._tuned(self._said)
        self._footed(Key("enter", "open"))

    def _summary(self, page: str) -> str:
        """What one card says is in it, in a few words."""
        if page == INSTALLED:
            return (
                f"{_many(len(self._all()), 'flow')}{_DOT}{self._flow or 'none chosen'}"
            )
        verses = self._places_of_flows()
        newer = len(self._updates())
        said = ", ".join(one.name for one in verses) or "none"
        return f"{said}{_DOT}{_NEWER} {_many(newer, 'update')}" if newer else said

    # -- Installed ----------------------------------------------------------------------------

    def _group(self, offer: Offer) -> str:
        """The heading a flow on the installed page stands under."""
        return "built in" if self._builtin(offer) else offer.whose

    def _fill_installed(self) -> None:
        """Puts up every flow there is to run, under where it came from.

        The release at the far end of each installed one, with a mark where its index lists a
        newer one, and a tick against the flow in force.
        """
        offers = self._all()
        shown = [
            one
            for one in sorted(offers, key=lambda one: self._group(one) != "built in")
            if self.fits(one.name, one.about)
        ]
        landing = self._lands([one.name for one in shown], self._flow)
        rows: list[Option | None] = []
        group = None
        for one in shown:
            heading = self._group(one)
            if heading != group:
                if rows:
                    rows[-1] = Option("", disabled=True)
                group = heading
                rows.append(Option(f" [$primary]{escape(heading)}[/]", disabled=True))
            here = one.name == landing
            rows.append(
                Option(
                    self._setting(
                        one.name,
                        self._release_chip(one, here=here),
                        one.about,
                        here=here,
                        inforce=one.name == self._flow,
                    ),
                    id=f"={one.name}",
                )
            )
            rows.append(None)
        self._put(rows[:-1] if rows else [], landing)
        said = self._said
        if not shown:
            said = said or ("no matching flows" if self._typed else "no flows yet")
        self._tuned(said)
        self._footed(Key("enter", "set up"))

    def _release_chip(self, offer: Offer, *, here: bool) -> tuple[str, int]:
        """What a flow's row says at its far end: its release, and a newer one where listed.

        Args:
          offer: The flow.
          here: Whether the cursor is on its row.

        Returns:
          The markup, and how many cells it takes.
        """
        held = self._installs().get(self._module(offer))
        if held is None:
            said = "built in" if self._builtin(offer) else ""
            return _shade("$text-muted", said, here=here), len(said)
        newer = self._updates().get(self._module(offer))
        said = held.version
        if newer is None:
            return _shade("$secondary", said, here=here), len(said)
        badge = f"{_NEWER} {newer}"
        return (
            f"{_shade('$secondary', said, here=here)}  {_shade('$warning', badge, here=here)}",
            len(said) + 2 + len(badge),
        )

    def _under_cursor(self) -> Offer | None:
        """The flow the buttons are about: the one the cursor is on, or the one open.

        On the installed page that is the row under the cursor; on a flow's own page it is
        that flow -- which is where somebody who reached it with a click finds them, a click on
        a row being a way into it rather than a way of putting the cursor on it.
        """
        held = self._flow if self._page == ROLES else self._cursors.get(INSTALLED, "")
        return next((one for one in self._all() if one.name == held), None)

    def _installed_actions(self) -> list[Action]:
        """What is done about the installed flows: install more, update, uninstall, copy."""
        return [
            Action(
                _ACT_MORE,
                "install more…",
                "browse the flowverses for flows to install",
                lambda: self._goes(VERSES),
            ),
            *self._tending(),
            self._searches(),
            self._saves_all(),
        ]

    def _tending(self) -> list[Action]:
        """What is done about one installed flow: update it, uninstall it, copy it here."""
        return [
            Action(
                _ACT_UPDATE,
                "update",
                "install the newest release its flowverse lists",
                self._updates_one,
                lambda: self._newer_of_cursor() is not None and not self._busy,
            ),
            Action(
                _ACT_UNINSTALL,
                "uninstall",
                "take the flow under the cursor away",
                self._uninstalls_cursor,
                lambda: self._record_of_cursor() is not None and not self._busy,
            ),
            Action(
                _ACT_COPY,
                "copy here",
                "copy the flow into this project to edit it",
                self._forks,
                self._copies,
            ),
        ]

    def _record_of_cursor(self) -> Installed | None:
        """The install the flow under the cursor is of, or None for one that is not."""
        one = self._under_cursor()
        return None if one is None else self._installs().get(self._module(one))

    def _newer_of_cursor(self) -> str | None:
        """The newer release of the flow under the cursor, or None for none."""
        one = self._under_cursor()
        return None if one is None else self._updates().get(self._module(one))

    def _copies(self) -> bool:
        """Whether the flow under the cursor is one to copy here: not one of this project's."""
        from hmz.runtime.flowing import LOCAL

        one = self._under_cursor()
        return one is not None and one.whose != LOCAL

    def _updates_one(self) -> None:
        """Installs the newer release of the flow under the cursor."""
        held, newer = self._record_of_cursor(), self._newer_of_cursor()
        if held is not None and newer is not None:
            self._installs_release(held.verse, held.name, newer)

    def _uninstalls_cursor(self) -> None:
        """Takes the flow under the cursor away."""
        held = self._record_of_cursor()
        if held is not None:
            self._uninstalls(held.verse, held.name)

    def _forks(self) -> None:
        """Copies the flow under the cursor into this project's own, to be changed.

        A flow is a directory, so a copy of one is a flow of yours: the entry point, what it
        imports and the skills it brings all come across, under the name it already had --
        and your own flows are looked in first, so from then on that name means your copy.
        Which is the way to change one at all: an installed flow is somebody else's release,
        installed again over whatever was written into it.
        """
        one = self._under_cursor()
        if one is None:
            return
        named = one.name
        try:
            at = _hmz().flows.fork(named)
        except (OSError, ValueError) as why:
            self._said = bad(escape(str(why)))
            self._fill()
            return
        self._forgets()
        mine = escape(named.rpartition("/")[2])
        self._said = (
            f"copied to {escape(at)} -- you can edit it, and {mine} now points to it"
        )
        self._told.append(f"[dim]{self._said}[/dim]")
        self._fill()

    # -- One flow's roles ----------------------------------------------------------------------

    def _fill_roles(self) -> None:
        """Puts up each role the flow declares, what it takes, its budget and profiling."""
        roles, places = self._roles(), self._places()
        lines: list[tuple[str, str, str, str]] = []
        for at, role in enumerate(roles):
            runs = self._runs.get(role, Runs(""))
            lines.append(
                (
                    str(at),
                    role,
                    runs.spec or "not set",
                    f"agent{_DOT}as {runs.provider}" if runs.provider else "agent",
                )
            )
        lines.extend(
            (
                f"@{place}",
                place,
                self._envs.get(place) or "not set",
                "environment",
            )
            for place in places
        )
        if self._declared is not None and self._declared.params.model_fields:
            changed = [" ".join(one.split()) for one in setting(self._params)]
            lines.append(
                (
                    _PARAMS,
                    "params",
                    ", ".join(changed) or "defaults",
                    "what the flow itself takes",
                )
            )
        unbounded = self._declared is not None and self._declared.unbounded
        lines.append(
            (
                _BUDGET,
                "budget",
                "set" if self._budget is not None else "none",
                f"what a run may spend: {_spending(self._budget, unbounded=unbounded)}",
            )
        )
        # Straight under the budget, the two of them about the run rather than any role: a
        # switch, its two values dropped under it as every switch's are.
        lines.append(
            (
                _PROFILING,
                "profiling",
                _YES if self._profile else _NO,
                "samples the programs agents start" if self._profile else "traced only",
            )
        )
        landing = self._lands([held for held, _, _, _ in lines])
        rows: list[Option | None] = []
        for held, named, value, about in lines:
            here = held == landing
            said = f"{value} {_OPENS}"
            chip = (
                _chip(value, _DROPS, here=here, toggles=True)
                if held == _PROFILING
                else (
                    _shade(
                        "$text-muted" if value in ("not set", "none") else "$secondary",
                        said,
                        here=here,
                    ),
                    len(said),
                )
            )
            rows.append(
                Option(self._setting(named, chip, about, here=here), id=f"={held}")
            )
            rows.append(None)
        self._put(rows[:-1], landing)
        said = self._said or ("" if roles or places else self._noagents())
        self._tuned(said)
        self._footed(Key("enter", "open"))

    def enters(self, row: str) -> bool:
        """Whether the arrow right goes into a row: every row that opens something.

        Not a release, which enter installs, nor the profiling switch, whose values drop.

        Args:
          row: The row, by id.

        Returns:
          True for a card, a flow, a flowverse, and what a flow's roles page opens.
        """
        return bool(row) and self._page != RELEASES and not self.drops(row)

    def drops(self, row: str) -> bool:
        """Whether a row is the profiling switch of a flow's roles page.

        Args:
          row: The row, by id.

        Returns:
          True for that switch.
        """
        return self._page == ROLES and row == _PROFILING

    def dropping(self, row: str) -> Drop:
        """The switch's two values, what each means, and which it is held at.

        Args:
          row: The switch, by id.

        Returns:
          The list, opening on the answer it is not, so that enter twice turns it round.
        """
        del row
        return switched(
            "profiling",
            _YES if self._profile else _NO,
            ("samples the programs agents start", "traced only"),
        )

    def dropped(self, row: str, picked: str) -> None:
        """Holds profiling at the value picked.

        Args:
          row: The switch, by id.
          picked: `on` or `off`.
        """
        del row
        self._profile = picked == _YES
        self._said = ""

    def _noagents(self) -> str:
        """Why there is no role to set up, which is not always the same reason."""
        if self._declared is None:
            return _wont_load(self._flow, "nothing can be configured")
        return (
            f"{escape(self._flow)} has no roles to configure; it interacts only "
            "with you"
        )

    def _chose(self, name: str) -> None:
        """Takes a flow as the one to run, and reads back what it was last set up with.

        Nothing is written down: what the menu holds is a draft, and a flow chosen and then
        walked away from must leave the interface exactly as ready as it was.

        Args:
          name: The flow, by the name it was offered under.
        """
        if name != self._flow:
            declared = declared_of(name)
            if declared is None:
                self._said = _wont_load(name)
                self._fill()
                return
            self._flow, self._declared = name, declared
            self._runs = self._fitted(self._remembered(name))
            self._envs = self._placed(name)
            self._params = params_of(name, self._held(name).get("params") or {})
            self._budget = budget_of(name)
            self._profile = _hmz().settings.profile(name)
            self._cursors.pop(ROLES, None)
            self.changed()
        # On to what the flow itself takes, where it takes anything, and then to its roles:
        # things about one flow, asked in the order they depend on nothing.
        self._configures(then=True)

    @work
    async def _configures(self, *, then: bool = False) -> None:
        """Asks what the flow itself takes, where it takes anything.

        Args:
          then: Whether to turn to the roles afterwards, which choosing a flow does.
        """
        if self.opening():
            return
        model = params_model(self._flow)
        try:
            if model is not None:
                held = await self._shown(
                    Configures(
                        self._flow,
                        model,
                        self._params if isinstance(self._params, model) else None,
                    )
                )
                if held is not None:
                    self._params = held
                    self.changed()
        finally:
            self.opened()
        if then:
            self._goes(ROLES)
        else:
            self._fill()

    @work
    async def _budgets(self) -> None:
        """Asks what a run of this flow may spend, from its row on the roles page."""
        if self.opening():
            return
        try:
            spends = await self._shown(
                Configures(
                    self._flow,
                    Budgeted,
                    Budgeted.of(self._budget) if self._budget is not None else None,
                    asked=f"Set budget for {self._flow}",
                    about="A run stops at whichever limit it reaches first; at least one "
                    "limit is required. Leave empty or 0 for no limit.",
                )
            )
        finally:
            self.opened()
        if isinstance(spends, Budgeted):
            self._budget = spends.budget()
            self.changed()
        self._fill()

    @work
    async def _placing(self, role: str) -> None:
        """Asks where one environment role is -- backend, machine, directory -- and holds it.

        Args:
          role: The environment role.
        """
        if self.opening():
            return
        was = self._envs.get(role, "")
        try:
            said = await self._shown(Placing(role, was))
        finally:
            self.opened()
        if said is None or said == was:
            return  # walked out of, or nothing moved
        if said:
            self._envs[role] = said
        else:
            self._envs.pop(role, None)
        self._said = ""
        self.changed()
        self._fill()

    @work
    async def _configuring(self, at: int) -> None:
        """Opens one agent role of the flow, and holds whatever comes back as a draft.

        Args:
          at: Which of them, counting from zero.
        """
        declared = self._declared
        if declared is None or not 0 <= at < len(declared.agents) or self.opening():
            return
        role = declared.agents[at]
        try:
            chosen = await self._shown(
                Agent(
                    role.name,
                    self._runs.get(role.name, Runs("")),
                    self._agents,
                    role=role,
                    unavailable=self._unavailable,
                )
            )
        finally:
            self.opened()
        if chosen is None:
            return  # walked out of it, which leaves that agent as the draft has it
        self._runs[role.name] = chosen
        self.changed()
        self._fill()

    async def _shown[T](self, sheet: Sheet[T]) -> T | None:
        """Puts a sheet up over this one and waits for what it answers."""
        return await self._interface().push_screen_wait(sheet)

    def applied(self) -> None:
        """Answers with the flow, its roles and how it is set up, all of it at once.

        Unless something a run needs has not been answered: an agent that names no model is
        a run that stops on its first turn, an environment nobody said the place of is a run
        refused before it starts, and so is a run given no budget -- which only `chat` may
        be. Each is said where it would be answered.
        """
        declared = self._declared
        missing = [
            role
            for role, one in self._runs.items()
            if not complete(one) and (declared is None or role in declared.roles)
        ]
        if declared is not None:
            missing.extend(
                one.name
                for one in declared.envs
                if one.required and not self._envs.get(one.name)
            )
        if missing:
            telemetry.snag("save-refused", missing=len(missing))
            self._said = iffy(f"{escape(', '.join(missing))} is not configured yet")
            self._to_roles()
            return
        if self._budget is None and declared is not None and not declared.unbounded:
            telemetry.snag("save-refused", missing=0)
            self._said = iffy("this flow requires a budget: set the budget first")
            self._to_roles()
            return
        self.dismiss(
            Chosen(
                self._flow,
                dict(self._runs),
                dict(self._envs),
                self._params,
                self._budget,
                self._profile,
            )
        )

    def _to_roles(self) -> None:
        """Turns to the roles, keeping what was just said: a refusal is about them."""
        said = self._said
        if self._page != ROLES:
            self._goes(ROLES)
        self._said = said
        self._fill()

    # -- The flowverses ------------------------------------------------------------------------

    def _fill_verses(self) -> None:
        """Puts up a card per flowverse: where it is from, what it lists, and how it stands."""
        verses = [
            one for one in self._places_of_flows() if self.fits(one.name, one.url)
        ]
        landing = self._lands([one.name for one in verses])
        rows: list[Option | None] = []
        for one in verses:
            here = one.name == landing
            state = self._standing(one)
            rows.append(
                Option(
                    self._setting(
                        one.name,
                        (
                            _shade(
                                "$warning" if state != "fetched" else "$text-muted",
                                state,
                                here=here,
                            ),
                            len(state),
                        ),
                        self._verse_about(one),
                        here=here,
                    ),
                    id=f"={one.name}",
                )
            )
            rows.append(None)
        self._put(rows[:-1] if rows else [], landing)
        self._tuned(self._said or ("no matching flowverses" if not verses else ""))
        self._footed(Key("enter", "open"))

    def _standing(self, one: Flowverse) -> str:
        """Whether a flowverse's index is here, and whether anything was written into it.

        The second is git's to say, so it is asked off the drawing path (:meth:`_asks_edited`)
        and drawn once it has been answered.
        """
        if not one.url:
            return "no git origin"
        if not one.fetched:
            return "not fetched"
        if self._edited is None:
            self._edited = {}
            self._asks_edited()
        return "edited" if self._edited.get(one.name) else "fetched"

    @work
    async def _asks_edited(self) -> None:
        """Asks git which indexes have something written into them, and draws the answer."""
        verses = _hmz().verses
        edited = {
            one.name: await asyncio.to_thread(verses.edited, one)
            for one in self._places_of_flows()
            if one.fetched
        }
        self._edited = edited
        if self._page == VERSES:
            self._fill()

    def _verse_about(self, one: Flowverse) -> str:
        """What a flowverse's card says: where it is from, what it lists, what is installed."""
        said = [_hmz().verses.whence(one, "a directory with no git origin")]
        if one.fetched:
            said.append(_many(len(self._index(one.name).flows()), "flow"))
        mine = [key for key in self._installs() if key[0] == one.name]
        if mine:
            said.append(f"{len(mine)} installed")
        newer = [key for key in self._updates() if key[0] == one.name]
        if newer:
            said.append(f"{_NEWER} {_many(len(newer), 'update')}")
        return _DOT.join(said)

    def _verse_under(self) -> Flowverse | None:
        """The flowverse the cursor is on, on the flowverses page, or the one open below it."""
        held = (
            self._verse
            if self._page in (VERSE, RELEASES)
            else self._cursors.get(VERSES, "")
        )
        return next((one for one in self._places_of_flows() if one.name == held), None)

    def _verses_actions(self) -> list[Action]:
        """What is done about the flowverses: add one, fetch one, remove one, search them."""
        one = self._verse_under()
        return [
            Action(
                _ACT_ADD,
                "add flowverse…",
                "a git repository indexing flows",
                self._adds_verse,
                lambda: not self._busy,
            ),
            self._fetching(one),
            Action(
                _ACT_REMOVE,
                "remove",
                "take it away, and every flow installed from it",
                self._removes,
                lambda: (
                    (under := self._verse_under()) is not None
                    and not under.fixed
                    and not self._busy
                ),
            ),
            self._searches(),
        ]

    def _fetching(self, one: Flowverse | None) -> Action:
        """The button that fetches the flowverse under the cursor, or the one open."""
        return Action(
            _ACT_FETCH,
            "fetch again" if one is not None and one.fetched else "fetch",
            "take what its index says now",
            self._fetches_under,
            lambda: (
                (under := self._verse_under()) is not None
                and bool(under.url)
                and not self._busy
            ),
        )

    # -- One flowverse's flows ----------------------------------------------------------------

    def _fill_verse(self) -> None:
        """Puts up the flows one index lists, the newest release of each and what is installed."""
        listed = self._index(self._verse)
        flows = [
            name
            for name in listed.flows()
            if self.fits(name, self._newest(listed, name).description)
        ]
        landing = self._lands(flows)
        rows: list[Option | None] = []
        for name in flows:
            here = name == landing
            newest = self._newest(listed, name)
            held = self._installs().get((self._verse, name))
            rows.append(
                Option(
                    self._setting(
                        name,
                        self._listed_chip(newest.version, held, here=here),
                        newest.description,
                        here=here,
                    ),
                    id=f"={name}",
                )
            )
            rows.append(None)
        self._put(rows[:-1] if rows else [], landing)
        said = self._said or self._nothing_listed(listed, bool(flows))
        self._tuned(said)
        self._footed(Key("enter", "releases"))

    @staticmethod
    def _newest(listed: Index, name: str) -> Release:
        """The release a flow of an index is shown by: the newest that is not a prerelease."""
        found = listed.newest(name)
        assert found is not None  # noqa: S101 -- the flow is one the index lists
        return found

    @staticmethod
    def _listed_chip(
        newest: str, held: Installed | None, *, here: bool
    ) -> tuple[str, int]:
        """What a flow of an index says at its far end: its newest release, and what is here.

        Args:
          newest: The newest release it lists.
          held: What is installed of it, or None.
          here: Whether the cursor is on its row.

        Returns:
          The markup, and how many cells it takes.
        """
        if held is None:
            return _shade("$secondary", newest, here=here), len(newest)
        if held.version == newest:
            said = f"{_INFORCE} {newest} installed"
            return _shade("$success", said, here=here), len(said)
        said = f"{_INFORCE} {held.version}  {_NEWER} {newest}"
        return _shade("$warning", said, here=here), len(said)

    def _nothing_listed(self, listed: Index, shown: bool) -> str:  # noqa: FBT001
        """What to say under a flowverse's flows: why there are none, and what did not read."""
        said: list[str] = []
        one = self._verse_under()
        if not shown:
            if self._typed:
                said.append("no matching flows")
            elif one is not None and not one.fetched:
                said.append("not fetched yet: press fetch to clone its index")
            else:
                said.append("this index lists no flows yet")
        if listed.skipped:
            first = listed.skipped[0]
            where = "/".join(first.at.parts[-3:-1])
            more = (
                f" and {len(listed.skipped) - 1} more"
                if len(listed.skipped) > 1
                else ""
            )
            said.append(iffy(escape(f"skipped {where}: {first.why}{more}")))
        return "\n".join(said)

    def _verse_actions(self) -> list[Action]:
        """What is done about one flowverse's flows: install, uninstall, fetch, search."""
        return [
            self._installing(),
            self._uninstalling(),
            self._fetching(self._verse_under()),
            self._searches(),
        ]

    def _flow_under(self) -> str:
        """The flow the cursor is on, on the page of one flowverse, or the one open below it."""
        if self._page == RELEASES:
            return self._listed
        return self._cursors.get(self._key(), "") if self._page == VERSE else ""

    def _release_under(self) -> Release | None:
        """The release an install would install: the one under the cursor, else the newest."""
        listed = self._index(self._verse)
        name = self._flow_under()
        if self._page == RELEASES:
            return listed.release(name, self._cursors.get(self._key(), ""))
        return listed.newest(name) if name else None

    def _installing(self) -> Action:
        """The button that installs, updates or switches to the release under the cursor."""
        one = self._release_under()
        held = None if one is None else self._installs().get((self._verse, one.name))
        if one is None or held is None:
            label = f"install {one.version}" if one is not None else "install"
        elif held.version == one.version:
            label = "installed"
        else:
            newer = one.semver > semver.Version.parse(held.version)
            label = f"{'update' if newer else 'switch'} to {one.version}"
        return Action(
            _ACT_INSTALL,
            label,
            "install this release, and whatever it needs",
            self._installs_under,
            lambda: (
                (under := self._release_under()) is not None
                and (
                    (have := self._installs().get((self._verse, under.name))) is None
                    or have.version != under.version
                )
                and not self._busy
            ),
        )

    def _uninstalling(self) -> Action:
        """The button that takes away what is installed of the flow under the cursor."""
        return Action(
            _ACT_UNINSTALL,
            "uninstall",
            "take the installed flow away",
            lambda: self._uninstalls(self._verse, self._flow_under()),
            lambda: (
                bool(self._flow_under())
                and (self._verse, self._flow_under()) in self._installs()
                and not self._busy
            ),
        )

    # -- One flow's releases -----------------------------------------------------------------

    def _fill_releases(self) -> None:
        """Puts up every release of one flow, newest first, the one installed ticked."""
        releases = [
            one
            for one in self._index(self._verse).versions(self._listed)
            if self.fits(one.version, one.ref)
        ]
        held = self._installs().get((self._verse, self._listed))
        newest = self._index(self._verse).newest(self._listed)
        landing = self._lands(
            [one.version for one in releases],
            held.version if held is not None else newest.version if newest else "",
        )
        rows: list[Option | None] = []
        for one in releases:
            here = one.version == landing
            marks: list[str] = []
            if one.semver.prerelease:
                marks.append(_PRE)
            if held is not None and held.version == one.version:
                marks.append(f"{_INFORCE} installed")
            said = "  ".join(marks)
            rows.append(
                Option(
                    self._setting(
                        one.version,
                        (
                            _shade(
                                "$success" if _INFORCE in said else "$text-muted",
                                said,
                                here=here,
                            ),
                            len(said),
                        ),
                        self._release_about(one),
                        here=here,
                    ),
                    id=f"={one.version}",
                )
            )
            rows.append(None)
        self._put(rows[:-1] if rows else [], landing)
        self._tuned(self._said or ("no matching releases" if not releases else ""))
        self._footed(Key("enter", "install"))

    @staticmethod
    def _release_about(one: Release) -> str:
        """What a release says about itself: where it was cut, its licence, what it needs."""
        said = [one.ref or "", one.commit[:12], one.license]
        said.extend(f"needs {name} {spec}" for name, spec in one.dependencies.items())
        return _DOT.join(part for part in said if part)

    def _releases_actions(self) -> list[Action]:
        """What is done about one flow's releases: install the one under the cursor, uninstall."""
        return [self._installing(), self._uninstalling(), self._searches()]

    # -- Doing it ----------------------------------------------------------------------------

    @work
    async def _installs_release(self, verse: str, flow: str, version: str) -> None:
        """Installs one release of a flow, and what it needs, off the loop.

        Args:
          verse: The flowverse.
          flow: The flow.
          version: The release.
        """
        from hmz.runtime.flowing import OFFICIAL

        called = flow if verse == OFFICIAL else f"{verse}/{flow}"
        #: Every flow the install came to, the ones it needs as well as the one asked for.
        touched: set[str] = set()

        def installing() -> str:
            done = _hmz().verses.install(called, version)
            touched.update(one.called for one in done)
            asked, *needs = reversed(done)
            also = (
                f", with {', '.join(f'{one.name} {one.version}' for one in needs)}"
                if needs
                else ""
            )
            return f"{asked.called} {asked.version} is installed{also}"

        if await self._off_loop(f"installing {called} {version}", installing):
            # The flow in force may be one of the flows of what was just installed -- asked
            # for, or needed by what was -- and what it declares is read off the release that
            # is there now.
            if self._flow.partition(":")[0] in touched:
                self._declared = declared_of(self._flow)
                self._runs = self._fitted(self._runs)
            self._fill()

    @work
    async def _uninstalls(self, verse: str, flow: str) -> None:
        """Takes one installed flow away, off the loop.

        Args:
          verse: The flowverse it was installed out of.
          flow: The flow.
        """
        from hmz.runtime.flowing import OFFICIAL

        called = flow if verse == OFFICIAL else f"{verse}/{flow}"

        def uninstalling() -> str:
            _hmz().verses.uninstall(called)
            return f"{called} is uninstalled"

        if not await self._off_loop(f"uninstalling {called}", uninstalling):
            return
        if called == self._flow.partition(":")[0]:
            # The flow the menu was holding is gone, and with it the draft of it.
            flow, declared, runs, envs, params, budget, profile = self._opened
            self._flow, self._declared, self._runs = flow, declared, dict(runs)
            self._envs, self._params, self._budget = dict(envs), params, budget
            self._profile = profile
            self._changed = False
        if self._page == ROLES:
            # And its page: back to what there is to run, saying so.
            said = self._said
            self._goes(INSTALLED)
            self._said = said
        self._fill()

    def _installs_under(self) -> None:
        """Installs the release the install button is about."""
        one = self._release_under()
        if one is not None:
            self._installs_release(self._verse, one.name, one.version)

    @work
    async def _adds_verse(self) -> None:
        """Asks where a flowverse is and what to call it here, and clones its index."""
        if self.opening():
            return
        try:
            said = await self._shown(Fetches())
        finally:
            self.opened()
        if said is None:
            return
        url, name = said

        def adding() -> str:
            added = _hmz().verses.add(url, name).name
            self._aim = added
            return f"{added} is fetched"

        # Scrubbed, as everywhere a URL is drawn: a private index is added with a token in it.
        await self._off_loop(f"fetching {name or _hmz().verses.plain(url)}", adding)

    def _fetches_under(self) -> None:
        """Fetches the flowverse the fetch button is about."""
        one = self._verse_under()
        if one is not None:
            self._fetches(one.name)

    @work
    async def _fetches(self, name: str) -> None:
        """Fetches one flowverse's index again, or for the first time, off the loop.

        Args:
          name: The flowverse.
        """

        def fetching() -> str:
            _hmz().verses.fetch(name)
            return f"{name} is fetched"

        await self._off_loop(f"fetching {name}", fetching)

    @work
    async def _removes(self) -> None:
        """Takes the flowverse under the cursor away, once asked whether to."""
        one = self._verse_under()
        if one is None or one.fixed or self.opening():
            return
        mine = len([key for key in self._installs() if key[0] == one.name])
        try:
            sure = await self._shown(Removes(one.name, mine))
        finally:
            self.opened()
        if sure != "yes":
            return
        name = one.name

        def removing() -> str:
            _hmz().verses.remove(name)
            return f"{name} was removed"

        await self._off_loop(f"removing {name}", removing)

    async def _off_loop(self, doing: str, how: Callable[[], str]) -> bool:
        """Does one thing that touches git or the disk off the event loop, and says how it went.

        Off the loop because a clone is seconds of network: an interface that stopped redrawing
        while it ran would be one that looked as though it had gone away. One at a time, so
        that two installs of one flow are never asked for from one menu.

        Args:
          doing: What is being done, said under the list while it is.
          how: What to do, answering with what to say once it is done.

        Returns:
          Whether it was done.
        """
        if self._busy:
            self._said = iffy(f"wait for {escape(self._busy)} to finish")
            self._fill()
            return False
        self._busy, self._said = doing, ""
        self._fill()
        try:
            said = await asyncio.to_thread(how)
        except (OSError, ValueError) as why:
            # Said under the list rather than raised at whoever opened the menu: the question
            # the menu is asking is still worth answering.
            self._busy = ""
            self._said = bad(escape(str(why)))
            self._fill()
            return False
        self._busy = ""
        self._said = escape(said)
        self._told.append(f"[dim]{escape(said)}[/dim]")
        self._forgets()
        if self._page == VERSE and self._verse not in {
            one.name for one in self._places_of_flows()
        }:
            # The flowverse that was open is gone: there is nothing below the list of them.
            self._page = VERSES
        self._fill()
        return True

    # -- Going in and out --------------------------------------------------------------------

    def action_up(self) -> None:
        """Goes back out to the page this one is under -- or up out of the menu."""
        up = _UP.get(self._page)
        if up is not None and not self._only:
            self._goes(up)
            return
        super().action_up()

    def action_back(self) -> None:
        """Puts back a row, or comes out of a search, or out of the page, or leaves.

        Leaving asks first whether to save what is held, as every menu holding changes does.
        """
        if not (self._editing or self._searching or self._only) and self._page in _UP:
            self._goes(_UP[self._page])
            return
        super().action_back()

    def _saves_all(self) -> Action:
        """The button the flow and its roles are saved from.

        Always pressable on a flow's roles, which is choosing that flow to run as it stands
        there -- a flow named on `/flow <name>` and saved untouched is a flow chosen -- and
        elsewhere only while something is held.
        """

        def able() -> bool:
            return self._changed or self._page == ROLES

        return Action(
            _ACT_SAVE,
            "save",
            "run this flow, set up as it is here" if able() else "nothing to save yet",
            self.applied,
            able,
            "primary",
        )

    # -- The bar and the keys ----------------------------------------------------------------

    def actions(self) -> list[Action]:
        """What the page open does about its list, in the order it stands."""
        if self._page == INSTALLED:
            return self._installed_actions()
        if self._page == ROLES:
            # Nothing is installed or taken away while a flow runs, nor from a menu that is
            # only this flow's: there is no list to go back to once it is gone.
            tends = [] if self._only else self._tending()
            return [*tends, self._saves_all()]
        if self._page == VERSES:
            return self._verses_actions()
        if self._page == VERSE:
            return self._verse_actions()
        if self._page == RELEASES:
            return self._releases_actions()
        return [self._saves_all()] if self._changed else []

    def _footed(self, *keys: Key) -> None:
        """Says the keys, with esc saying whether it closes the menu or goes up a page.

        Args:
          keys: The page's keys, for its list.
        """
        back = Key("esc", "close" if self._page == HOME or self._only else "back")
        super()._footed(*(one for one in keys if one.key != "esc"), back)

    # -- Choosing ----------------------------------------------------------------------------

    @on(OptionList.OptionSelected, "#choices")
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Does what enter does on the row chosen, which each page says.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id or "").removeprefix("=")
        if not held:
            return
        if self._page == HOME:
            self._goes(held)
        elif self._page == INSTALLED:
            self._chose(held)
        elif self._page == VERSES:
            self._goes(VERSE, verse=held)
        elif self._page == VERSE:
            self._goes(RELEASES, listed=held)
        elif self._page == RELEASES:
            act = self._acting(_ACT_INSTALL)
            if act is not None and act.able():
                act.does()
        else:
            self._takes_role(held)

    def _takes_role(self, held: str) -> None:
        """Opens what one row of the roles page is a way of setting.

        Args:
          held: The row, by its id.
        """
        if held == _BUDGET:
            self._budgets()
        elif held == _PARAMS:
            self._configures()
        elif held.startswith("@"):
            self._placing(held[1:])
        elif held.isdigit():
            self._configuring(int(held))

    def dismiss(self, result: Chosen | None = None) -> AwaitComplete:
        """Answers, telling the interface what was done as it was asked for either way.

        Args:
          result: The flow and its roles, or None for a menu walked out of.

        Returns:
          The waiting, as a sheet's own is.
        """
        if self._told and not self._answered:
            self._interface().post_message(self.Told(tuple(self._told)))
        return super().dismiss(result)


def _wont_load(flow: str, also: str = "") -> str:
    """What to say about a flow that will not load: which flow, why, and what follows.

    In red, that being what it is: a flow that will not load is the one thing on this menu
    that is wrong rather than merely unset, and a line about it in the same grey as the rest
    is a line that reads as description.

    Args:
      flow: The flow, by the name it was offered under.
      also: What follows from it here, where anything does.

    Returns:
      The line, ready to draw.
    """
    said = f"{escape(flow)} failed to load"
    why = why_not(flow)
    if why:
        said += f": {escape(why)}"
    if also:
        said += f"; {also}"
    return bad(said)


def _spending(held: Budget | None, *, unbounded: bool) -> str:
    """What a run of this flow may spend, said the way a row about it says it.

    Said on the row rather than only inside the sheet it opens, because a budget nobody can
    see without opening something is one nobody checks: the row is where a person finds out
    what the run they are about to start is held to -- or that it is held to nothing yet,
    which is a run that will not start.

    Args:
      held: What was set here, or None for none.
      unbounded: Whether the flow needs none: a conversation, which stops when you do.

    Returns:
      The caps, or what having none comes to.
    """
    if held is None:
        return (
            "none needed; runs until you stop it"
            if unbounded
            else "none set; a run needs one"
        )
    return f"stops at {spent(held)}"
