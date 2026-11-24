"""`/flow`: the flows there are to run, where more come from, and what each one runs on.

Drawn and worked as every menu is (:class:`hmz.tui.pick.Sheet`), `/settings` among them: a
screen of its own, the way here across the top with each step of it a way back, a list in a box
with a block cursor, and what is done about the list rather than to one row of it --
installing, updating, searching, saving -- a bar of buttons under it. What is here is what is
this menu's own: its pages, and what each does.

Two pages under the first screen. **Installed** is what there is to run: the flows installed
out of a flowverse with the release each is at and a mark where a newer one is listed, and the
flows of your own. Enter on one goes into what it runs on -- an
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
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

import semver
from rich.markup import escape
from textual import on, work
from textual.message import Message
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from hmz.runtime.kept import Runs, read_back
from hmz.words import t

from . import humanfia
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
    Targets,
    _chip,
    _hmz,
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


__all__ = [
    "HOME",
    "INSTALLED",
    "VERSES",
    "Fetches",
    "Flows",
    "Lists",
    "Removes",
    "Shelf",
    "Uninstalls",
    "add",
    "fetch",
    "install",
    "offered",
    "remove",
    "uninstall",
]

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
#: itself takes, what a run may spend, whether its flow and its environment are each profiled
#: as well as traced, and where it is backed up. Each under
#: a mark no name has, since a row id is otherwise an agent's place among the roles or an
#: environment's name.
_PARAMS = f"{_APART_MARK}params"
_BUDGET = f"{_APART_MARK}budget"
_PROFILING_FLOW = f"{_APART_MARK}profile-flow"
_PROFILING_ENVIRONMENT = f"{_APART_MARK}profile-environment"

#: The two profiling switches: what each row is called, and what it means on.
_PROFILING = {
    _PROFILING_FLOW: ("Profile flow", "samples the flow's own Python"),
    _PROFILING_ENVIRONMENT: (
        "Profile environment",
        "samples the programs agents start",
    ),
}
_BACKING = f"{_APART_MARK}backup"

#: What each button under a page is known by, beside the ones `/settings` has.
_ACT_MORE, _ACT_UPDATE, _ACT_UNINSTALL, _ACT_COPY = (
    "more",
    "update",
    "uninstall",
    "copy",
)
_ACT_INSTALL, _ACT_FETCH = "install", "fetch"

#: What the menu of a flow or a flowverse opens it with, and copies of it.
_ACT_OPEN, _ACT_NAME = "open", "copy-name"

#: What says a row's flow is behind what its index lists.
_NEWER = "↑"

#: The cards of the first screen: what each page is called, its mark -- a point for what
#: runs, a square for what is kept -- and what it is for.
_CARDS = (
    (
        INSTALLED,
        "Installed",
        humanfia.POINT,
        "flows ready to run, those installed and your own",
    ),
    (
        VERSES,
        "Flowverses",
        humanfia.SQUARE,
        "indexes of flows to install, update and add to",
    ),
)

#: How a flowverse's index stands, by what its row says of it.
_FETCHED, _UNFETCHED, _EDITED, _NO_ORIGIN = (
    "fetched",
    "not fetched",
    "edited",
    "no origin",
)


class Shelf:
    """What the disk holds about flows, read once and read again after anything lands.

    What `/flow` lists and what the Flows page lists are one reading: the flows there are to
    run, the installs they are of, the newer release each index lists, the flowverses and
    what each index lists. Reading what is installed means importing every flow of it, so
    each is read the first time it is asked for and held until :meth:`forgets`.
    """

    def __init__(self) -> None:
        """Holds nothing until it is asked."""
        self._offers: list[Offer] | None = None
        self._records: dict[tuple[str, str], Installed] | None = None
        self._newer: dict[tuple[str, str], str] | None = None
        self._indexes: dict[str, Index] = {}
        self._verses: list[Flowverse] | None = None

    def all(self) -> list[Offer]:
        """Every flow there is to run."""
        if self._offers is None:
            self._offers = _hmz().flows.all()
        return self._offers

    def installs(self) -> dict[tuple[str, str], Installed]:
        """Every flow installed out of an index, by flowverse and what it lists."""
        if self._records is None:
            self._records = {
                (one.verse, one.listed): one for one in _hmz().verses.installed()
            }
        return self._records

    def updates(self) -> dict[tuple[str, str], str]:
        """The newer release each installed flow's index lists, by flowverse and flow."""
        if self._newer is None:
            self._newer = {
                (one.installed.verse, one.installed.listed): one.version
                for one in _hmz().verses.updates()
            }
        return self._newer

    def index(self, verse: str) -> Index:
        """What one flowverse's index lists."""
        held = self._indexes.get(verse)
        if held is None:
            held = self._indexes[verse] = _hmz().verses.index(verse)
        return held

    def verses(self) -> list[Flowverse]:
        """Every flowverse but your own two, which are places rather than indexes.

        A directory under the flowverses home that is not a clone of anything -- what a clone
        killed partway leaves -- is one of them, with nothing to fetch: listed, so that it can
        be removed.
        """
        from hmz.runtime.flowing import MINE

        if self._verses is None:
            self._verses = [one for one in _hmz().verses.all() if one.name not in MINE]
        return self._verses

    def forgets(self) -> None:
        """Drops everything read, which something landing has made wrong."""
        self._offers = self._records = self._newer = self._verses = None
        self._indexes = {}

    @staticmethod
    def module(offer: Offer) -> tuple[str, str]:
        """Which installed flow an offer is of: its flowverse, and the flow's own name.

        A module that holds several flows offers `<flow>:<inside>` for each but the one named
        after it, and all of them are the one install.
        """
        from hmz.runtime.flowing.verses import split

        return split(offer.name.partition(":")[0])

    def held(self, offer: Offer) -> Installed | None:
        """The install an offer is of, or None for a flow of your own."""
        return self.installs().get(self.module(offer))

    def newer(self, offer: Offer) -> str | None:
        """The newer release an offer's index lists, or None for none."""
        return self.updates().get(self.module(offer))


def offered(release: Release, held: Installed | None) -> str:
    """What installing a release is called, beside what is installed of its flow.

    Args:
      release: The release.
      held: What is installed of its flow, or None.

    Returns:
      `Install 1.2.0` for a flow not installed, `Installed` for the release that is, and
      `Update to` or `Switch to` it as it is newer or not than the one that is.
    """
    if held is None:
        return t("Install {version}", version=release.version)
    if held.version == release.version:
        return t("Installed")
    if release.semver > semver.Version.parse(held.version):
        return t("Update to {version}", version=release.version)
    return t("Switch to {version}", version=release.version)


def install(verse: str, flow: str, version: str) -> tuple[str, set[str]]:
    """Installs one release of a flow, and what it needs: seconds of git, so off the loop.

    Args:
      verse: The flowverse.
      flow: The flow, as its index lists it.
      version: The release.

    Returns:
      What to say of it, and every flow the install came to -- the ones it needs as well as
      the one asked for -- as each is called.

    Raises:
      OSError, ValueError: If it could not be installed, saying why.
    """
    from hmz.runtime.flowing.verses import called

    done = _hmz().verses.install(called(verse, flow), version)
    asked, *needs = reversed(done)
    touched = {one.called for one in done}
    if not needs:
        said = t("{name} {version} is installed.", name=asked.called, version=version)
        return said, touched
    return (
        t(
            "{name} {version} is installed, with {needs}.",
            name=asked.called,
            version=asked.version,
            needs=", ".join(f"{one.called} {one.version}" for one in needs),
        ),
        touched,
    )


def uninstall(verse: str, flow: str) -> str:
    """Takes one installed flow away, and answers what to say of it.

    Raises:
      OSError, ValueError: If it could not be, saying why -- another flow needs it.
    """
    from hmz.runtime.flowing.verses import called

    named = called(verse, flow)
    _hmz().verses.uninstall(named)
    return t("{name} is uninstalled.", name=named)


def fetch(name: str) -> str:
    """Fetches one flowverse's index again, or for the first time, and answers what to say.

    Raises:
      OSError, ValueError: If it could not be fetched, saying why.
    """
    _hmz().verses.fetch(name)
    return t("Fetched {name}.", name=name)


def add(url: str, name: str = "") -> tuple[str, str]:
    """Clones a flowverse's index, and answers what to say and what it is called here.

    Raises:
      OSError, ValueError: If it could not be cloned, saying why.
    """
    added = _hmz().verses.add(url, name).name
    return t("Fetched {name}.", name=added), added


def remove(name: str) -> str:
    """Takes a flowverse away with everything installed out of it, and answers what to say.

    Raises:
      OSError, ValueError: If it could not be, saying why.
    """
    _hmz().verses.remove(name)
    return t("{name} is removed.", name=name)


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
        self.asked = t(
            "Remove {name} and every flow installed out of it?", name=escape(verse)
        )
        self.about = t("{n} installed flows go with it.", n=flows) if flows else ""

    def rows(self) -> list[tuple[str, str, str]]:
        """Taking it away, or keeping it."""
        return [
            ("yes", t("Remove"), t("removes the flowverse now")),
            ("no", t("Cancel"), t("keeps the flowverse")),
        ]


class Uninstalls(Popup):
    """Whether to take one installed flow away, asked by its name before it goes."""

    CSS = _popup("Uninstalls")

    def __init__(self, flow: str) -> None:
        """Initializes the question.

        Args:
          flow: The flow, as it is called.
        """
        super().__init__()
        self.asked = t("Uninstall {name}?", name=escape(flow))

    def rows(self) -> list[tuple[str, str, str]]:
        """Taking it away, or keeping it."""
        return [
            ("yes", t("Uninstall"), t("uninstalls the installed flow")),
            ("no", t("Cancel"), ""),
        ]


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
                t("URL"),
                t("owner/repo or URL"),
                needed=not self._typed_in.get("repository", "").strip(),
            ),
            Question("name", t("Name"), t("Name (optional)")),
        ]

    def done_about(self) -> str:
        """What answering it does."""
        return t("clones the flowverse's index; flows are installed from it next")

    def _ask(self) -> None:
        """Says what a flowverse is."""
        from hmz.runtime.flowing.verses import tilded, under

        self.query_one("#asked", Label).update(t("Add flowverse"))
        self.query_one("#about", Label).update(
            escape(
                t(
                    "A git repository indexing flows as "
                    "flows/[<user>/]<flow>/<version>/flow.yaml, one manifest per release. "
                    "Its index is cloned under {path}. Flows installed from it are offered "
                    "as @<name>/[<user>/]<flow>.",
                    path=tilded(under()),
                )
            )
        )
        self._fill()

    def action_done(self) -> None:
        """Answers with where it is and what to call it, once there is somewhere to fetch."""
        url = self._typed_in.get("repository", "").strip()
        name = self._typed_in.get("name", "").strip()
        if not url:
            self._wrong = t("This needs a URL.")
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
        profile_flow: bool = False,
        profile_environment: bool = False,
        backup: tuple[str, ...] | None = None,
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
          profile_flow: Whether a run of it here profiles the flow's own Python.
          profile_environment: Whether a run of it here profiles the programs its agents
            start.
          backup: The backup targets an epic of it here goes to, by name, or None for the
            defaults.
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
        #: Where an epic is backed up, or None for wherever the defaults say when it starts.
        self._backup = backup
        self._defaults = _hmz().backups.defaults()
        self._flow: str = flow
        #: What the flow declares, read once per flow rather than on every redraw: reading
        #: it means importing the flow, and the roles page is drawn on every keystroke.
        self._declared: Declared | None = declared_of(flow)
        self._runs: dict[str, Runs]
        self._envs: dict[str, str]
        self._params: BaseModel | None
        self._budget: Budget | None
        self._profiled: dict[str, bool]
        if runs:
            self._runs = self._fitted(dict(runs))
            self._envs = dict(envs or {})
            self._params = params
            self._budget = budget
            self._profiled = {
                _PROFILING_FLOW: profile_flow,
                _PROFILING_ENVIRONMENT: profile_environment,
            }
        else:
            # A flow the interface is not set up on, opened straight into: what it was last
            # set up with here is what it opens holding, exactly as turning to it would be.
            self._runs = self._fitted(self._remembered(flow))
            self._envs = self._placed(flow)
            self._params = params_of(flow, self._held(flow).get("params") or {})
            self._budget = budget_of(flow)
            self._profiled = _remembered_profiling(flow)
            self._backup = _hmz().settings.backup(flow)
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
            dict(self._profiled),
            self._backup,
        )
        #: Whether what the flow runs on is the whole of this menu, there being no list
        #: behind it to step back to: while a flow runs, and for a flow that was named.
        self._only = running or inside
        self._page = ROLES if self._only else page
        #: The flowverse and the flow of it being read, on the pages about one of them.
        self._verse = ""
        self._listed = ""
        #: What was read off the disk, once per opening and again after anything lands.
        self._shelf = Shelf()
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
        return self._shelf.all()

    def _installs(self) -> dict[tuple[str, str], Installed]:
        """Every flow installed out of an index, by flowverse and what it lists, read once."""
        return self._shelf.installs()

    def _updates(self) -> dict[tuple[str, str], str]:
        """The newer release each installed flow's index lists, by flowverse and flow."""
        return self._shelf.updates()

    def _index(self, verse: str) -> Index:
        """What one flowverse's index lists, read once."""
        return self._shelf.index(verse)

    def _places_of_flows(self) -> list[Flowverse]:
        """Every flowverse but your own two, which are places rather than indexes, read once."""
        return self._shelf.verses()

    def _forgets(self) -> None:
        """Drops everything read off the disk, which something landing has made wrong."""
        self._shelf.forgets()
        self._edited = None

    def reread(self) -> None:
        """Drops what was read before a fetch landed, and draws the page again.

        What the flow in force declares too: an update may have just changed it.
        """
        self._forgets()
        if self._flow:
            self._declared = declared_of(self._flow)
            self._runs = self._fitted(self._runs)
        self._fill()

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
            INSTALLED: t("Installed"),
            ROLES: self._flow,
            VERSES: t("Flowverses"),
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
        from hmz.runtime.flowing.verses import tilded, under

        if self._page == HOME:
            return t("Flows to run, and the flowverses more are installed from.")
        if self._page == INSTALLED:
            return t(
                "Flows ready to run here; pick one to set it up and run it, or install "
                "more from a flowverse."
            )
        if self._page == ROLES:
            return t(
                "Set up each role, an agent (CLI, account, model and effort) or an "
                "environment. Then set what the flow takes and what an epic may spend."
            )
        if self._page == VERSES:
            return t(
                "Indexes of flows to install, cloned under {path}. Fetching, adding and "
                "removing one happen at once.",
                path=escape(tilded(under())),
            )
        if self._page == VERSE:
            return t(
                "The flows {name} lists, each at its newest release. Open one for its "
                "other releases; installing happens at once.",
                name=escape(self._verse),
            )
        return t(
            "Releases of {name}, newest first. Pick one to install it or switch to it.",
            name=escape(self._listed),
        )

    def _tuned(self, said: str) -> None:
        """Says something under the list, or nothing: what is going on, else what was said."""
        if self._busy:
            said = escape(self._busy) + (f"{_DOT}{said}" if said else "")
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
                        icon,
                        t(title),
                        self._summary(page),
                        t(blurb),
                        here=page == landing,
                    ),
                    id=f"={page}",
                )
            )
            cards.append(None)
        self._put(cards[:-1], landing)
        self._tuned(self._said)
        self._footed(Key("enter", t("Open")))

    def _summary(self, page: str) -> str:
        """What one card says is in it, in a few words."""
        if page == INSTALLED:
            flows = t("{n} flows", n=len(self._all()))
            return f"{flows}{_DOT}{self._flow or t('none chosen')}"
        verses = self._places_of_flows()
        newer = len(self._updates())
        said = ", ".join(one.name for one in verses) or t("none")
        if not newer:
            return said
        return f"{said}{_DOT}{_NEWER} {t('{n} updates', n=newer)}"

    # -- Installed ----------------------------------------------------------------------------

    def _fill_installed(self) -> None:
        """Puts up every flow there is to run, under where it came from.

        The release at the far end of each installed one, with a mark where its index lists a
        newer one, and a tick against the flow in force.
        """
        offers = self._all()
        shown = [one for one in offers if self.fits(one.name, one.about)]
        landing = self._lands([one.name for one in shown], self._flow)
        rows: list[Option | None] = []
        group = None
        for one in shown:
            heading = one.whose
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
            said = said or (
                t("No flow matches.") if self._typed else t("No flows installed yet.")
            )
        self._tuned(said)
        self._footed(Key("enter", t("Set up")))

    def _release_chip(self, offer: Offer, *, here: bool) -> tuple[str, int]:
        """What a flow's row says at its far end: its release, and a newer one where listed.

        Args:
          offer: The flow.
          here: Whether the cursor is on its row.

        Returns:
          The markup, and how many cells it takes.
        """
        held = self._shelf.held(offer)
        if held is None:
            return "", 0
        newer = self._shelf.newer(offer)
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
                t("Browse Flowverses"),
                t("browse the flowverses for flows to install"),
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
                t("Update"),
                t("installs the newest release its flowverse lists"),
                self._updates_one,
                lambda: self._newer_of_cursor() is not None and not self._busy,
            ),
            Action(
                _ACT_UNINSTALL,
                t("Uninstall"),
                t("uninstalls the flow under the cursor"),
                self._uninstalls_cursor,
                lambda: self._record_of_cursor() is not None and not self._busy,
            ),
            Action(
                _ACT_COPY,
                t("Copy here"),
                t("copies the flow into this workspace to edit it"),
                self._forks,
                self._copies,
            ),
        ]

    def _record_of_cursor(self) -> Installed | None:
        """The install the flow under the cursor is of, or None for one that is not."""
        one = self._under_cursor()
        return None if one is None else self._shelf.held(one)

    def _newer_of_cursor(self) -> str | None:
        """The newer release of the flow under the cursor, or None for none."""
        one = self._under_cursor()
        return None if one is None else self._shelf.newer(one)

    def _copies(self) -> bool:
        """Whether the flow under the cursor is one to copy here: not one of this project's."""
        from hmz.runtime.flowing import LOCAL

        one = self._under_cursor()
        return one is not None and one.whose != LOCAL

    def _updates_one(self) -> None:
        """Installs the newer release of the flow under the cursor."""
        held, newer = self._record_of_cursor(), self._newer_of_cursor()
        if held is not None and newer is not None:
            self._installs_release(held.verse, held.listed, newer)

    def _uninstalls_cursor(self) -> None:
        """Takes the flow under the cursor away."""
        held = self._record_of_cursor()
        if held is not None:
            self._uninstalls(held.verse, held.listed)

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
        self._said = t(
            "Copied to {path}; edit it there, and {name} now names the copy.",
            path=escape(at),
            name=escape(named.rpartition("/")[2]),
        )
        self._told.append(f"[dim]{self._said}[/dim]")
        self._fill()

    # -- One flow's roles ----------------------------------------------------------------------

    def _fill_roles(self) -> None:
        """Puts up each role the flow declares, what it takes, its budget and profiling."""
        roles, places = self._roles(), self._places()
        unset, none = t("Not set"), t("none")
        lines: list[tuple[str, str, str, str]] = []
        for at, role in enumerate(roles):
            runs = self._runs.get(role, Runs(""))
            about = t("agent")
            if runs.provider:
                about += _DOT + t("as {name}", name=runs.provider)
            lines.append((str(at), role, runs.spec or unset, about))
        lines.extend(
            (f"@{place}", place, self._envs.get(place) or unset, t("environment"))
            for place in places
        )
        if self._declared is not None and self._declared.params.model_fields:
            changed = [" ".join(one.split()) for one in setting(self._params)]
            lines.append(
                (
                    _PARAMS,
                    t("Parameters"),
                    ", ".join(changed) or t("defaults"),
                    t("what the flow itself takes"),
                )
            )
        lines.append(
            (
                _BUDGET,
                t("Budget"),
                t("set") if self._budget is not None else none,
                t("what an epic may spend: {limits}", limits=_spending(self._budget)),
            )
        )
        # Straight under the budget, the ones about the run rather than any role: two
        # switches, each with its two values dropped under it as every switch's are.
        lines.extend(
            (
                held,
                t(named),
                _YES if self._profiled[held] else _NO,
                t(means) if self._profiled[held] else t("traced only"),
            )
            for held, (named, means) in _PROFILING.items()
        )
        backup = self._backup if self._backup is not None else self._defaults
        lines.append(
            (
                _BACKING,
                t("Backup"),
                ", ".join(backup) or none,
                t("where each epic is backed up (the defaults)")
                if self._backup is None
                else t("where each epic is backed up"),
            )
        )
        landing = self._lands([held for held, _, _, _ in lines])
        rows: list[Option | None] = []
        for held, named, value, about in lines:
            here = held == landing
            said = f"{value} {_OPENS}"
            chip = (
                _chip(value, _DROPS, here=here, toggles=True)
                if held in _PROFILING
                else (
                    _shade(
                        "$text-muted" if value in (unset, none) else "$secondary",
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
        self._footed(Key("enter", t("Open")))

    def enters(self, row: str) -> bool:
        """Whether the arrow right goes into a row: every row that opens something.

        Not a release, which enter installs, nor a profiling switch, whose values drop.

        Args:
          row: The row, by id.

        Returns:
          True for a card, a flow, a flowverse, and what a flow's roles page opens.
        """
        return bool(row) and self._page != RELEASES and not self.drops(row)

    def drops(self, row: str) -> bool:
        """Whether a row is one of the profiling switches of a flow's roles page.

        Args:
          row: The row, by id.

        Returns:
          True for either switch.
        """
        return self._page == ROLES and row in _PROFILING

    def dropping(self, row: str) -> Drop:
        """The switch's two values, what each means, and which it is held at.

        Args:
          row: The switch, by id.

        Returns:
          The list, opening on the answer it is not, so that enter twice turns it round.
        """
        named, means = _PROFILING[row]
        return switched(
            t(named),
            _YES if self._profiled[row] else _NO,
            (t(means), t("traced only")),
        )

    def dropped(self, row: str, picked: str) -> None:
        """Holds one profiling switch at the value picked.

        Args:
          row: The switch, by id.
          picked: `on` or `off`.
        """
        self._profiled[row] = picked == _YES
        self._said = ""

    def _noagents(self) -> str:
        """Why there is no role to set up, which is not always the same reason."""
        if self._declared is None:
            return _wont_load(self._flow, t("Nothing can be set up."))
        return t(
            "{name} has no roles to set up; it works only with you.",
            name=escape(self._flow),
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
            self._profiled = _remembered_profiling(name)
            self._backup = _hmz().settings.backup(name)
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
                    asked=t("Set the budget for {name}", name=self._flow),
                    about=t(
                        "An epic stops at whichever limit it reaches first. At least one "
                        "limit is required; leave a limit empty or 0 for none."
                    ),
                )
            )
        finally:
            self.opened()
        if isinstance(spends, Budgeted):
            self._budget = spends.budget()
            self.changed()
        self._fill()

    @work
    async def _backs_up(self) -> None:
        """Asks which backup targets an epic goes to, from its row on the roles page."""
        if not _hmz().backups.targets():
            self._said = iffy(t("No backup target yet; add one in /settings backup."))
            self._fill()
            return
        if self.opening():
            return
        backup = self._backup if self._backup is not None else self._defaults
        try:
            chosen = await self._shown(Targets(backup))
        finally:
            self.opened()
        if chosen is not None and set(chosen) != set(backup):
            self._backup = chosen
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
        refused before it starts, and so is a run given no budget, which no flow may be run
        without (Section 16.4.6 of [TUI]). Each is said where it would be answered.
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
            self._said = iffy(
                t("{roles} not set up yet.", roles=escape(", ".join(missing)))
            )
            self._to_roles()
            return
        if self._budget is None and declared is not None:
            self._said = iffy(t("This flow needs a budget; set the budget first."))
            self._to_roles()
            return
        self.dismiss(
            Chosen(
                self._flow,
                dict(self._runs),
                dict(self._envs),
                self._params,
                self._budget,
                self._profiled[_PROFILING_FLOW],
                self._profiled[_PROFILING_ENVIRONMENT],
                self._backup,
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
                                "$warning" if state != _FETCHED else "$text-muted",
                                t(state),
                                here=here,
                            ),
                            len(t(state)),
                        ),
                        self._verse_about(one),
                        here=here,
                    ),
                    id=f"={one.name}",
                )
            )
            rows.append(None)
        self._put(rows[:-1] if rows else [], landing)
        self._tuned(self._said or (t("No flowverse matches.") if not verses else ""))
        self._footed(Key("enter", t("Open")))

    def _standing(self, one: Flowverse) -> str:
        """Whether a flowverse's index is here, and whether anything was written into it.

        The second is git's to say, so it is asked off the drawing path (:meth:`_asks_edited`)
        and drawn once it has been answered.
        """
        if not one.url:
            return _NO_ORIGIN
        if not one.fetched:
            return _UNFETCHED
        if self._edited is None:
            self._edited = {}
            self._asks_edited()
        return _EDITED if self._edited.get(one.name) else _FETCHED

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
        said = [_hmz().verses.whence(one, t("local folder"))]
        if one.fetched:
            said.append(t("{n} flows", n=len(self._index(one.name).flows())))
        mine = [key for key in self._installs() if key[0] == one.name]
        if mine:
            said.append(t("{n} installed", n=len(mine)))
        newer = [key for key in self._updates() if key[0] == one.name]
        if newer:
            said.append(f"{_NEWER} {t('{n} updates', n=len(newer))}")
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
                t("Add flowverse"),
                t("adds a git repository indexing flows"),
                self._adds_verse,
                lambda: not self._busy,
            ),
            self._fetching(one),
            Action(
                _ACT_REMOVE,
                t("Remove"),
                t("removes it and every flow installed out of it"),
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
        del one  # fetching is called one thing, fetched before or not, as on the page
        return Action(
            _ACT_FETCH,
            t("Fetch"),
            t("takes what the flowverse's index says now"),
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
        self._footed(Key("enter", t("Releases")))

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
            said = f"{_INFORCE} {t('{version} installed', version=newest)}"
            return _shade("$success", said, here=here), len(said)
        said = f"{_INFORCE} {held.version}  {_NEWER} {newest}"
        return _shade("$warning", said, here=here), len(said)

    def _nothing_listed(self, listed: Index, shown: bool) -> str:  # noqa: FBT001
        """What to say under a flowverse's flows: why there are none, and what did not read."""
        from hmz.runtime.flowing.index import RELEASE
        from hmz.runtime.flowing.verses import FLOWS

        said: list[str] = []
        one = self._verse_under()
        if not shown:
            if self._typed:
                said.append(t("No flow matches."))
            elif one is not None and not one.fetched:
                said.append(
                    t("Not fetched yet.")
                    + t(" Fetch this flowverse to see what it lists.")
                )
            else:
                said.append(t("This flowverse lists no flow."))
        if listed.skipped:
            first = listed.skipped[0]
            # What of `flows/` it is: `<flow>/<version>`, `<user>/<flow>/<version>`, `<user>`.
            parts = first.at.parts[:-1] if first.at.name == RELEASE else first.at.parts
            where = "/".join(parts[len(parts) - parts[::-1].index(FLOWS) :])
            more = len(listed.skipped) - 1
            said.append(
                iffy(
                    escape(
                        t(
                            "Skipped {where}: {why}, and {n} more",
                            where=where,
                            why=first.why,
                            n=more,
                        )
                        if more
                        else t("Skipped {where}: {why}", where=where, why=first.why)
                    )
                )
            )
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
        held = None if one is None else self._installs().get((self._verse, one.listed))
        return Action(
            _ACT_INSTALL,
            t("Install") if one is None else offered(one, held),
            t("installs this release and the flows it needs"),
            self._installs_under,
            lambda: (
                (under := self._release_under()) is not None
                and (
                    (have := self._installs().get((self._verse, under.listed))) is None
                    or have.version != under.version
                )
                and not self._busy
            ),
        )

    def _uninstalling(self) -> Action:
        """The button that takes away what is installed of the flow under the cursor."""
        return Action(
            _ACT_UNINSTALL,
            t("Uninstall"),
            t("uninstalls the installed flow"),
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
                marks.append(t("prerelease"))
            if held is not None and held.version == one.version:
                marks.append(f"{_INFORCE} {t('Installed')}")
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
        self._tuned(self._said or (t("No release matches.") if not releases else ""))
        self._footed(Key("enter", t("Install")))

    @staticmethod
    def _release_about(one: Release) -> str:
        """What a release says about itself: where it was cut, its licence, what it needs."""
        said = [one.ref or "", one.commit[:12], one.license]
        said.extend(
            t("needs {name} {spec}", name=name, spec=spec)
            for name, spec in one.dependencies.items()
        )
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
          flow: The flow, as its index lists it.
          version: The release.
        """
        from hmz.runtime.flowing.verses import called as calling

        #: Every flow the install came to, the ones it needs as well as the one asked for.
        touched: set[str] = set()

        def installing() -> str:
            said, came_to = install(verse, flow, version)
            touched.update(came_to)
            return said

        doing = t(
            "Installing {name} {version}…", name=calling(verse, flow), version=version
        )
        if await self._off_loop(doing, installing):
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
          flow: The flow, as its index lists it.
        """
        from hmz.runtime.flowing.verses import called as calling

        called = calling(verse, flow)
        doing = t("Uninstalling {name}…", name=called)
        if not await self._off_loop(doing, partial(uninstall, verse, flow)):
            return
        if called == self._flow.partition(":")[0]:
            # The flow the menu was holding is gone, and with it the draft of it.
            flow, declared, runs, envs, params, budget, profiled, backup = self._opened
            self._flow, self._declared, self._runs = flow, declared, dict(runs)
            self._envs, self._params, self._budget = dict(envs), params, budget
            self._profiled, self._backup = dict(profiled), backup
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
            self._installs_release(self._verse, one.listed, one.version)

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
            said, self._aim = add(url, name)
            return said

        # Scrubbed, as everywhere a URL is drawn: a private index is added with a token in it.
        await self._off_loop(
            t("Fetching {name}…", name=name or _hmz().verses.plain(url)), adding
        )

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
        await self._off_loop(t("Fetching {name}…", name=name), partial(fetch, name))

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
        await self._off_loop(
            t("Removing {name}…", name=one.name), partial(remove, one.name)
        )

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
            self._said = iffy(t("Wait for the one under way to finish."))
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
            t("Save"),
            t("runs this flow, set up as it is here")
            if able()
            else t("nothing to save yet"),
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

    def menu(self) -> tuple[str, list[Action]] | None:
        """What the installed flow or the flowverse under the cursor offers, for `m`."""
        if self._page == INSTALLED and (one := self._under_cursor()) is not None:
            named = one.name
            return (
                named,
                [
                    Action(
                        _ACT_OPEN,
                        t("Open"),
                        t("sets its agents up"),
                        lambda: self._chose(named),
                    ),
                    *self._tending(),
                    Action(
                        _ACT_NAME, t("Copy name"), named, lambda: self.copies(named)
                    ),
                ],
            )
        if self._page == VERSES and (verse := self._verse_under()) is not None:
            called, url = verse.name, verse.url
            return (
                called,
                [
                    Action(
                        _ACT_OPEN,
                        t("Open"),
                        t("shows the flows it lists"),
                        lambda: self._goes(VERSE, verse=called),
                    ),
                    *(
                        one
                        for one in self._verses_actions()
                        if one.key in (_ACT_FETCH, _ACT_REMOVE)
                    ),
                    *(
                        (
                            Action(
                                _ACT_NAME, t("Copy URL"), url, lambda: self.copies(url)
                            ),
                        )
                        if url
                        else ()
                    ),
                ],
            )
        return None

    def _footed(self, *keys: Key) -> None:
        """Says the keys, with esc saying whether it closes the menu or goes up a page.

        Args:
          keys: The page's keys, for its list.
        """
        back = Key("esc", t("Close") if self._page == HOME or self._only else t("Back"))
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
        elif held == _BACKING:
            self._backs_up()
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
      also: What follows from it here, where anything does, as a sentence.

    Returns:
      The line, ready to draw.
    """
    why = why_not(flow)
    said = (
        t("The flow {name} failed to load: {why}", name=escape(flow), why=escape(why))
        if why
        else t("The flow {name} failed to load.", name=escape(flow))
    )
    if also:
        # Its own sentence, after whatever the reason ended in.
        said = f"{said.rstrip('.')}. {also}"
    return bad(said)


def _spending(held: Budget | None) -> str:
    """What a run of this flow may spend, said the way a row about it says it.

    Said on the row rather than only inside the sheet it opens, because a budget nobody can
    see without opening something is one nobody checks: the row is where a person finds out
    what the run they are about to start is held to -- or that it is held to nothing yet,
    which is a run that will not start.

    Args:
      held: What was set here, or None for none.

    Returns:
      The caps, or what having none comes to.
    """
    if held is None:
        return t("none set; an epic needs one")
    return t("stops at {limits}", limits=spent(held))


def _remembered_profiling(flow: str) -> dict[str, bool]:
    """Whether a run of a flow here was last said to profile its flow and its environment.

    Args:
      flow: The flow.

    Returns:
      Each profiling switch, by row id, as settings holds it.
    """
    settings = _hmz().settings
    return {
        _PROFILING_FLOW: settings.profile_flow(flow),
        _PROFILING_ENVIRONMENT: settings.profile_environment(flow),
    }
