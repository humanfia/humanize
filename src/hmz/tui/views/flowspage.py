"""Flows: the flows installed here, and the flowverses more are installed from.

The page the web interface calls Flows, over the whole screen: two tabs, **Installed** and
**Flowverses**. Installed is a toolbox -- every flow there is to run, the ones whose flowverse
lists a newer release first and marked, each opened for what it declares, started as a new
epic, updated, switched to another release or uninstalled. Flowverses is where more come
from: each index with when it was fetched, added, fetched and removed here, and under each the
flows it lists and their releases, any one of which is installed or switched to.

What is read and what is done are `/flow`'s own (:mod:`hmz.tui.flows`), so the menu and the
page list the same flows and say the same of what was done to them. Nothing is installed,
updated or uninstalled while an epic is going (Section 3.9 of tui.md): the page says so where
it would have been done. Taking anything away asks first, by name.
"""

from __future__ import annotations

import asyncio
import datetime
from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar, cast

from rich.markup import escape
from textual import on, work
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from hmz.tui import flows, humanfia
from hmz.tui.pick import bad, declared_of, iffy, why_not
from hmz.tui.shell import Hints, View, views
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual import events
    from textual.app import App, ComposeResult

    from hmz.runtime.flowing import Flowverse, Installed, Offer, Release

__all__ = ["VIEWS", "FlowsPage"]

#: The lists of the page: the two tabs, one flowverse's flows, one flow's releases, and what
#: one installed flow declares.
INSTALLED, VERSES, VERSE, RELEASES, ABOUT = (
    flows.INSTALLED,
    flows.VERSES,
    "verse",
    "releases",
    "about",
)

#: What says a flow is behind what its flowverse lists, as `/flow` and the status line say it.
_NEWER = "↑"

#: How wide a name is drawn at most before what is said of it.
_NAMED = 34

#: The keys of each list, in the order the hint line says them, each with what it does.
_KEYS: dict[str, tuple[tuple[str, str], ...]] = {
    INSTALLED: (
        ("enter", "Open"),
        ("n", "New epic"),
        ("u", "Update"),
        ("s", "Switch"),
        ("x", "Uninstall"),
        ("tab", "Flowverses"),
    ),
    ABOUT: (("n", "New epic"), ("u", "Update"), ("s", "Switch"), ("x", "Uninstall")),
    VERSES: (
        ("enter", "Open"),
        ("a", "Add flowverse"),
        ("f", "Fetch"),
        ("x", "Remove"),
        ("tab", "Installed"),
    ),
    VERSE: (
        ("enter", "Releases"),
        ("i", "Install"),
        ("x", "Uninstall"),
        ("f", "Fetch"),
    ),
    RELEASES: (("enter", "Install"), ("x", "Uninstall")),
}


def _shade(style: str, said: str, *, here: bool) -> str:
    """Something said in a colour of its own, except under the cursor, which is one plane."""
    return said if here or not said else f"[{style}]{said}[/]"


def _fetched(one: Flowverse) -> str:
    """When a flowverse's index was last fetched, to the minute, or "" for one never fetched."""
    for stamped in ("FETCH_HEAD", "HEAD"):
        try:
            moment = (one.at / ".git" / stamped).stat().st_mtime
        except OSError:
            continue
        return datetime.datetime.fromtimestamp(moment).strftime("%Y-%m-%d %H:%M")  # noqa: DTZ006 -- said in the terminal's own time
    return ""


class FlowsPage(Screen[None]):
    """The Flows page: Installed and Flowverses, and what is done to a flow from each."""

    DEFAULT_CSS = """
    FlowsPage { background: $background; }
    FlowsPage > #title { height: 1; padding: 0 2; color: $primary; text-style: bold; }
    FlowsPage > #rule { height: 1; color: $primary; }
    FlowsPage > #tabs { height: 1; padding: 0 2; margin: 1 0 0 0; }
    FlowsPage > #about { height: auto; padding: 0 2; margin: 1 0 0 0; color: $text-muted; }
    FlowsPage > #held { display: none; height: auto; padding: 0 2; color: $warning; }
    FlowsPage > #held.going { display: block; }
    FlowsPage > #rows { height: 1fr; margin: 1 0 0 0; padding: 0 1; border: none;
                        background: $background; }
    FlowsPage > #rows:focus { border: none; }
    FlowsPage > #detail { display: none; height: 1fr; margin: 1 0 0 0; padding: 0 2;
                          color: $foreground; }
    FlowsPage.reading > #rows { display: none; }
    FlowsPage.reading > #detail { display: block; }
    FlowsPage > #said { height: auto; padding: 0 2; }
    FlowsPage > Hints { padding: 0 2; }
    """

    #: Every key any of the lists takes; which of them the list open takes is `_KEYS`, and
    #: only those are acted on (:meth:`check_action`), which are the ones its hint line says.
    BINDINGS: ClassVar = [
        Binding(key, f"key('{key}')", show=False)
        for key in ("escape", "tab", "n", "u", "s", "x", "a", "f", "i")
    ]

    def __init__(self, page: str = INSTALLED) -> None:
        """Opens on one of the two tabs.

        Args:
          page: `installed` or `verses`.
        """
        super().__init__()
        self._page = page if page in (INSTALLED, VERSES) else INSTALLED
        self._shelf = flows.Shelf()
        #: The flowverse and the flow of it being read, on the lists about one of them, and
        #: the installed flow opened.
        self._verse = ""
        self._listed = ""
        self._flow = ""
        #: Where a flow's releases were opened from, which is where `esc` goes back to.
        self._from = VERSE
        #: The row each list's cursor was last on, by id.
        self._cursors: dict[str, str] = {}
        #: What is being done off the loop now, or "" for nothing: one at a time.
        self._busy = ""
        #: What became of the last thing done, as markup.
        self._said = ""
        #: When each flowverse was fetched and where from, read once per reading of the disk.
        self._stands: dict[str, tuple[str, str]] = {}

    def compose(self) -> ComposeResult:
        """A title over a heavy rule, the tabs, the list, what was said, and the keys."""
        yield Static(t("Flows").upper(), id="title")
        yield Static(id="rule")
        yield Static(id="tabs")
        yield Static(id="about")
        yield Static(id="held")
        yield OptionList(id="rows")
        yield Static(id="detail")
        yield Static(id="said")
        yield Hints()

    def on_mount(self) -> None:
        """Puts the tab it opened on up, and gives its list the keys."""
        self._fill()
        self.query_one("#rows", OptionList).focus()

    def on_resize(self, event: events.Resize) -> None:
        """Rules the title across however wide the screen is now."""
        self.query_one("#rule", Static).update(humanfia.RULE * event.size.width)

    # -- What a sheet opened over this is told it is in -------------------------------------

    def crumb(self) -> str:
        """What the page is called on the way across the top of a sheet opened over it."""
        return t("Flows")

    def crumbs(self) -> list[str]:
        """Nothing: the page is one step, whichever of its lists is open."""
        return []

    def reread(self) -> None:
        """Drops what was read before a fetch landed elsewhere, and draws the list again."""
        self._shelf.forgets()
        self._stands.clear()
        self._fill()

    # -- What is read -----------------------------------------------------------------------

    def _interface(self) -> App[None]:
        """The interface this page is drawn over."""
        return cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )

    def _going(self) -> bool:
        """Whether an epic is going, which is when nothing is installed or taken away."""
        asked = getattr(self._interface(), "flow_running", None)
        return bool(asked()) if callable(asked) else False

    def _offers(self) -> list[Offer]:
        """Every flow there is to run, the ones with a newer release listed first."""
        offers = self._shelf.all()
        return sorted(offers, key=lambda one: self._shelf.newer(one) is None)

    def _offer(self, name: str) -> Offer | None:
        """One flow there is to run, by what it is called."""
        return next((one for one in self._shelf.all() if one.name == name), None)

    def _flowverse(self, name: str) -> Flowverse | None:
        """One flowverse, by name."""
        return next((one for one in self._shelf.verses() if one.name == name), None)

    def _key(self) -> str:
        """Which list is drawn, for remembering where its cursor was."""
        if self._page == VERSE:
            return f"{VERSE}:{self._verse}"
        if self._page == RELEASES:
            return f"{RELEASES}:{self._verse}/{self._listed}"
        return self._page

    def _row(self) -> str:
        """The row under the cursor, by id, or "" for a list with nothing in it."""
        listing = self.query_one("#rows", OptionList)
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return ""
        return str(listing.get_option_at_index(at).id or "")

    def _held_of_cursor(self) -> tuple[Offer | None, Installed | None]:
        """The installed flow the keys are about: the one opened, else the one under the cursor."""
        name = self._flow if self._page == ABOUT else self._row()
        one = self._offer(name) if name else None
        return one, (self._shelf.held(one) if one is not None else None)

    # -- Drawing ----------------------------------------------------------------------------

    def _fill(self) -> None:
        """Draws the list that is open, the way to it, and the keys it takes."""
        self.set_class(self._page == ABOUT, "reading")
        self.query_one("#tabs", Static).update(self._tabs())
        held = self.query_one("#held", Static)
        held.set_class(self._going(), "going")
        held.update(
            t(
                "An epic is going; flows are installed, updated and uninstalled once "
                "it ends."
            )
        )
        if self._page == ABOUT:
            self.query_one("#about", Static).update("")
            self.query_one("#detail", Static).update(self._about())
        else:
            rows, about = {
                INSTALLED: self._installed,
                VERSES: self._verses,
                VERSE: self._verse_flows,
                RELEASES: self._releases,
            }[self._page]()
            self.query_one("#about", Static).update(about)
            self._put(rows)
        said = self._said
        if self._busy:
            said = escape(self._busy) + (f" · {said}" if said else "")
        self.query_one("#said", Static).update(said)
        keys = _KEYS[self._page]
        if self._page == INSTALLED and not self._shelf.all():
            keys = (("tab", "Browse Flowverses"),)
        self.query_one(Hints).says([*keys, ("esc", "Back")])

    def _tabs(self) -> str:
        """The two tabs, the open one cyan, and under it the way down to the list drawn."""
        on_installed = self._page in (INSTALLED, ABOUT) or (
            self._page == RELEASES and self._from != VERSE
        )
        below = {
            ABOUT: [self._flow],
            VERSE: [self._verse],
            RELEASES: [self._verse, self._listed],
        }.get(self._page, [])
        cut = f" [$hmz-line-strong]{humanfia.CUT}[/] "
        down = "".join(f"{cut}{escape(one)}" for one in below)
        return "   ".join(
            _tab(said, here=here) + (down if here else "")
            for said, here in (
                (t("Installed"), on_installed),
                (t("Flowverses"), not on_installed),
            )
        )

    def _put(self, rows: list[tuple[str, Callable[[bool], str]]]) -> None:
        """Puts the rows up with the cursor where it was on this list, else on the first."""
        listing = self.query_one("#rows", OptionList)
        ids = [held for held, _ in rows]
        was = self._cursors.get(self._key(), "")
        landing = was if was in ids else ids[0] if ids else ""
        listing.set_options(
            [Option(draws(held == landing), id=held) for held, draws in rows]
        )
        listing.highlighted = ids.index(landing) if landing else None
        if landing:
            self._cursors[self._key()] = landing

    @on(OptionList.OptionHighlighted, "#rows")
    def _moved(self, event: OptionList.OptionHighlighted) -> None:
        """Draws the list again with the cursor's row as one plane, once it has moved."""
        held = str(event.option.id or "")
        if held and self._cursors.get(self._key()) != held:
            self._cursors[self._key()] = held
            self._fill()

    def _installed(self) -> tuple[list[tuple[str, Callable[[bool], str]]], str]:
        """Every flow there is to run, and how many of them have a newer release."""
        offers = self._offers()
        wide = min(max((len(one.name) for one in offers), default=0), _NAMED)

        def drawn(one: Offer, here: bool) -> str:  # noqa: FBT001 -- drawn per row
            held, newer = self._shelf.held(one), self._shelf.newer(one)
            mark = _shade("$warning", humanfia.SQUARE, here=here) if newer else " "
            release = held.version if held is not None else t("your own")
            said = _shade("$secondary", escape(release), here=here)
            if newer:
                said += "  " + _shade("$warning", f"{_NEWER} {newer}", here=here)
            about = _shade("$text-muted", escape(one.about), here=here)
            return f"{mark} [b]{escape(one.name.ljust(wide))}[/]  {said}  {about}"

        rows = [(one.name, partial(drawn, one)) for one in offers]
        if not offers:
            return rows, t("No flows installed yet.") + t(
                " A flow is what an epic runs. Install one from a flowverse."
            )
        behind = len(self._shelf.updates())
        about = t("{n} flows", n=len(offers))
        if behind:
            newer = t("{n} flows have a newer release", n=behind)
            about += f" · [$warning]{humanfia.SQUARE} {newer}[/]"
        return rows, about

    def _verses(self) -> tuple[list[tuple[str, Callable[[bool], str]]], str]:
        """Every flowverse: how it stands, when it was fetched, and what it holds."""
        from hmz.daemon import Hmz
        from hmz.runtime.flowing.verses import tilded, under

        verses = self._shelf.verses()
        wide = min(max((len(one.name) for one in verses), default=0), _NAMED)
        installs, updates = self._shelf.installs(), self._shelf.updates()

        for one in verses:
            if one.name not in self._stands:
                whence = Hmz().verses.whence(one, t("local folder"))
                self._stands[one.name] = (_fetched(one), whence)

        def drawn(one: Flowverse, here: bool) -> str:  # noqa: FBT001 -- drawn per row
            said: list[str] = []
            when, whence = self._stands[one.name]
            if one.fetched:
                said.append(f"{t('fetched')} {when}".rstrip())
            else:
                state = t("not fetched") if one.url else t("no origin")
                said.append(_shade("$warning", state, here=here))
            said.append(escape(whence))
            if one.fetched:
                said.append(t("{n} flows", n=len(self._shelf.index(one.name).flows())))
            mine = sum(1 for key in installs if key[0] == one.name)
            if mine:
                said.append(t("{n} installed", n=mine))
            newer = sum(1 for key in updates if key[0] == one.name)
            if newer:
                counted = f"{_NEWER} {t('{n} updates', n=newer)}"
                said.append(_shade("$warning", counted, here=here))
            about = _shade("$text-muted", " · ", here=here).join(said)
            mark = _shade("$warning", humanfia.SQUARE, here=here) if newer else " "
            return f"{mark} [b]{escape(one.name.ljust(wide))}[/]  {about}"

        rows = [(one.name, partial(drawn, one)) for one in verses]
        if not verses:
            return rows, t("No flowverse yet.")
        return rows, t(
            "Indexes of flows to install, cloned under {path}. Fetching, adding and "
            "removing one happen at once.",
            path=escape(tilded(under())),
        )

    def _verse_flows(self) -> tuple[list[tuple[str, Callable[[bool], str]]], str]:
        """The flows one flowverse lists, each at its newest release, and what is installed."""
        listed = self._shelf.index(self._verse)
        names = listed.flows()
        wide = min(max((len(one) for one in names), default=0), _NAMED)
        installs = self._shelf.installs()

        def drawn(name: str, here: bool) -> str:  # noqa: FBT001 -- drawn per row
            newest = listed.newest(name)
            held = installs.get((self._verse, name))
            version = newest.version if newest is not None else ""
            if held is None:
                said = _shade("$secondary", escape(version), here=here)
            elif held.version == version:
                said = _shade(
                    "$primary", t("{version} installed", version=version), here=here
                )
            else:
                said = _shade(
                    "$warning", f"{held.version}  {_NEWER} {version}", here=here
                )
            about = newest.description if newest is not None else ""
            mark = " " if held is None or held.version == version else humanfia.SQUARE
            return (
                f"{_shade('$warning', mark, here=here)} "
                f"[b]{escape(name.ljust(wide))}[/]  {said}  "
                f"{_shade('$text-muted', escape(about), here=here)}"
            )

        rows = [(name, partial(drawn, name)) for name in names]
        said: list[str] = []
        one = self._flowverse(self._verse)
        if not names:
            if one is not None and not one.fetched:
                said.append(
                    t("Not fetched yet.")
                    + t(" Fetch this flowverse to see what it lists.")
                )
            else:
                said.append(t("This flowverse lists no flow."))
        else:
            said.append(
                t(
                    "The flows {name} lists, each at its newest release. Open one for "
                    "its other releases; installing happens at once.",
                    name=escape(self._verse),
                )
            )
        said.extend(
            iffy(escape(t("Skipped {where}: {why}", where=str(each.at), why=each.why)))
            for each in listed.skipped
        )
        return rows, "\n".join(said)

    def _releases(self) -> tuple[list[tuple[str, Callable[[bool], str]]], str]:
        """Every release of one flow, newest first, the installed one marked."""
        releases = self._shelf.index(self._verse).versions(self._listed)
        held = self._shelf.installs().get((self._verse, self._listed))
        wide = max((len(one.version) for one in releases), default=0)

        def drawn(one: Release, here: bool) -> str:  # noqa: FBT001 -- drawn per row
            marks: list[str] = []
            if held is not None and held.version == one.version:
                marks.append(_shade("$primary", t("Installed"), here=here))
            if one.semver.prerelease:
                marks.append(t("prerelease"))
            said = [one.ref or "", one.commit[:12], one.license]
            said.extend(
                t("needs {name} {spec}", name=name, spec=spec)
                for name, spec in one.dependencies.items()
            )
            about = escape(" · ".join(part for part in said if part))
            return (
                f"  [b]{escape(one.version.ljust(wide))}[/]  {'  '.join(marks)}  "
                f"{_shade('$text-muted', about, here=here)}"
            )

        rows = [(one.version, partial(drawn, one)) for one in releases]
        if held is not None:
            self._cursors.setdefault(self._key(), held.version)
        return rows, t(
            "Releases of {name}, newest first. Pick one to install it or switch to it.",
            name=escape(self._listed),
        )

    def _about(self) -> str:
        """What one installed flow is: its release, what it says of itself, and what it declares."""
        one, held = self._held_of_cursor()
        if one is None:
            return ""
        lines = [f"[b]{escape(one.name)}[/]"]
        if held is not None:
            newer = self._shelf.newer(one)
            said = f"[$secondary]{escape(held.version)}[/]"
            if newer:
                said += f"  [$warning]{humanfia.SQUARE} {_NEWER} {escape(newer)}[/]"
            lines[0] += f"  {said}"
        if one.about:
            lines.append(escape(one.about))
        declared = declared_of(one.name)
        if declared is None:
            why = why_not(one.name)
            lines.append(
                bad(
                    t(
                        "The flow {name} failed to load: {why}",
                        name=escape(one.name),
                        why=escape(why),
                    )
                    if why
                    else t("The flow {name} failed to load.", name=escape(one.name))
                )
            )
            return "\n".join(lines)
        person = t(" (a person, answering here)")
        agents = [*declared.roles, *(f"{who}{person}" for who in declared.outworlders)]
        fields = declared.params.model_fields
        params = [
            name if field.is_required() else f"{name} = {field.default!r}"
            for name, field in fields.items()
        ]
        for heading, held_in in (
            (t("agents"), agents),
            (t("environments"), list(declared.places)),
            (t("params"), params or [t("takes no parameters")]),
        ):
            if held_in:
                lines += ["", f"[b $text-muted]{heading.upper()}[/]"]
                lines += [f"  {escape(each)}" for each in held_in]
        return "\n".join(lines)

    # -- The keys ---------------------------------------------------------------------------

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        """Whether a key does anything on the list that is open: only what its hints say."""
        if action != "key":
            return True
        return parameters[0] == "escape" or parameters[0] in {
            held for held, _ in _KEYS[self._page]
        }

    def action_key(self, key: str) -> None:
        """Does what the hint line says the key does on the list that is open."""
        {
            "escape": self._back,
            "tab": self._turns,
            "n": self._starts,
            "u": self._updates,
            "s": self._switches,
            "x": self._takes_away,
            "a": self._adds,
            "f": self._fetches,
            "i": self._installs_newest,
        }[key]()

    @on(OptionList.OptionSelected, "#rows")
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Does what `enter` does on the row chosen, which each list says."""
        held = str(event.option.id or "")
        if not held:
            return
        if self._page == INSTALLED:
            self._flow = held
            self._goes(ABOUT)
        elif self._page == VERSES:
            self._verse = held
            self._goes(VERSE)
        elif self._page == VERSE:
            self._listed, self._from = held, VERSE
            self._goes(RELEASES)
        elif self._page == RELEASES:
            self._installs(self._verse, self._listed, held)

    def _goes(self, page: str) -> None:
        """Turns to another list, leaving what was said on the one left behind."""
        if page == ABOUT and self._offer(self._flow) is None:
            page = INSTALLED  # uninstalled from its releases: there is nothing to open
        self._page, self._said = page, ""
        self._fill()
        if page != ABOUT:
            self.query_one("#rows", OptionList).focus()

    def _back(self) -> None:
        """One step back: out of a list to the one it was opened from, or out of the page."""
        up = {
            ABOUT: INSTALLED,
            VERSE: VERSES,
            RELEASES: self._from,
        }.get(self._page)
        if up is None:
            self.dismiss()
        else:
            self._goes(up)

    def _turns(self) -> None:
        """Turns to the other tab."""
        self._goes(VERSES if self._page == INSTALLED else INSTALLED)

    def _refused(self) -> bool:
        """Whether nothing may be installed or taken away now, saying why where it is."""
        if not self._going():
            return False
        self._said = iffy(
            t(
                "An epic is going; flows are installed, updated and uninstalled once "
                "it ends."
            )
        )
        self._fill()
        return True

    def _starts(self) -> None:
        """Starts a new epic of the flow: on the New epic page, else by setting it up.

        The page closes first, and what follows is the interface's to do rather than the
        page's: anything a page starts stops with it.
        """
        one, _ = self._held_of_cursor()
        if one is None:
            return
        app, name = cast("Any", self._interface()), one.name

        async def starts() -> None:
            if "newepic" in views():
                await app.shell.opens("newepic")
                takes = getattr(app.screen, "takes_flow", None)
                if callable(takes):
                    takes(name)
            else:
                app.action_flow(name)

        self.dismiss()
        app.call_later(starts)

    def _updates(self) -> None:
        """Installs the newest release the flow's flowverse lists."""
        one, held = self._held_of_cursor()
        newer = self._shelf.newer(one) if one is not None else None
        if held is not None and newer is not None:
            self._installs(held.verse, held.listed, newer)

    def _switches(self) -> None:
        """Opens the releases of the installed flow, to switch to one."""
        _, held = self._held_of_cursor()
        if held is None:
            return
        self._verse, self._listed, self._from = held.verse, held.listed, self._page
        self._goes(RELEASES)

    def _installs_newest(self) -> None:
        """Installs the newest release of the flow under the cursor of a flowverse's list."""
        name = self._row()
        newest = self._shelf.index(self._verse).newest(name) if name else None
        if newest is not None:
            self._installs(self._verse, name, newest.version)

    def _installs(self, verse: str, flow: str, version: str) -> None:
        """Installs one release, unless it is the one installed or an epic is going."""
        held = self._shelf.installs().get((verse, flow))
        if (held is not None and held.version == version) or self._refused():
            return
        from hmz.runtime.flowing.verses import called

        self._does(
            t(
                "Installing {name} {version}…",
                name=called(verse, flow),
                version=version,
            ),
            lambda: flows.install(verse, flow, version)[0],
        )

    @work
    async def _takes_away(self) -> None:
        """Uninstalls a flow or removes a flowverse, once asked whether to, by name."""
        from hmz.runtime.flowing.verses import called

        if self._page == VERSES:
            one = self._flowverse(self._row())
            if one is None or one.fixed:
                return
            mine = sum(1 for key in self._shelf.installs() if key[0] == one.name)
            if mine and self._refused():
                return
            sure = await self._interface().push_screen_wait(
                flows.Removes(one.name, mine)
            )
            if sure == "yes":
                self._does(
                    t("Removing {name}…", name=one.name),
                    partial(flows.remove, one.name),
                )
            return
        if self._page in (VERSE, RELEASES):
            listed = self._listed if self._page == RELEASES else self._row()
            held = self._shelf.installs().get((self._verse, listed))
        else:
            _, held = self._held_of_cursor()
        if held is None or self._refused():
            return
        named = called(held.verse, held.listed)
        sure = await self._interface().push_screen_wait(flows.Uninstalls(named))
        if sure == "yes":
            self._does(
                t("Uninstalling {name}…", name=named),
                partial(flows.uninstall, held.verse, held.listed),
            )

    @work
    async def _adds(self) -> None:
        """Asks where a flowverse is and what to call it here, and clones its index."""
        from hmz.daemon import Hmz

        said = await self._interface().push_screen_wait(flows.Fetches())
        if said is None:
            return
        url, name = said

        def adding() -> str:
            done, added = flows.add(url, name)
            self._cursors[VERSES] = added
            return done

        # Scrubbed, as everywhere a URL is drawn: a private index is added with a token in it.
        self._does(t("Fetching {name}…", name=name or Hmz().verses.plain(url)), adding)

    def _fetches(self) -> None:
        """Fetches the flowverse under the cursor, or the one open."""
        one = self._flowverse(self._verse if self._page == VERSE else self._row())
        if one is not None and one.url:
            self._does(
                t("Fetching {name}…", name=one.name), partial(flows.fetch, one.name)
            )

    def _does(self, doing: str, how: Callable[[], str]) -> None:
        """Does one thing that runs git off the event loop, and says how it went.

        One at a time, as `/flow` does them, and said in the transcript too: what was
        installed is worth reading once the page is closed. Run by the interface rather than
        by the page, so that a page closed while git runs still says what came of it.

        Args:
          doing: What is being done, said under the list while it is.
          how: What to do, answering with what to say once it is done.
        """
        if self._busy:
            self._said = iffy(t("Wait for the one under way to finish."))
            self._fill()
            return
        self._busy, self._said = doing, ""
        self._fill()
        self._interface().run_worker(self._done(how), exit_on_error=False)

    async def _done(self, how: Callable[[], str]) -> None:
        """Waits for what :meth:`_does` started, and says what came of it."""
        from hmz.daemon import Hmz

        app = self._interface()
        try:
            said = await asyncio.to_thread(how)
        except (OSError, ValueError) as why:
            self._busy = ""
            self._said = bad(escape(Hmz().verses.plain(str(why))))
            if self.is_attached:
                self._fill()
            return
        self._busy, self._said = "", escape(said)
        self._shelf.forgets()
        self._stands.clear()
        app.post_message(flows.Flows.Told((f"[dim]{escape(said)}[/dim]",)))
        if not self.is_attached:
            return
        if self._page == ABOUT and self._offer(self._flow) is None:
            self._page = INSTALLED
        if self._page in (VERSE, RELEASES) and self._flowverse(self._verse) is None:
            self._page = VERSES
        self._fill()


def _tab(said: str, *, here: bool) -> str:
    """One tab: cyan under a point where it is the one open, quiet where it is not."""
    if here:
        return f"[b $primary]{humanfia.POINT} {said.upper()}[/]"
    return f"[$text-muted]  {said.upper()}[/]"


def _made(_app: App[None]) -> FlowsPage:
    return FlowsPage()


VIEWS = (View("flows", "page", "Flows", _made, key="ctrl+l", hint="Flows"),)
