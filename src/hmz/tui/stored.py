"""Downloading an epic out of a backup target: every epic it holds, and one brought here.

Opened from the backup page of `/settings`, as the web's Download is: what the target holds is
fetched afresh as it opens, off the event loop since that is a `git fetch`, and listed by the
machine it was backed up from and then by the directory it ran in, newest first, those already
here marked. Enter downloads the one under the cursor as an import would land it.
"""

# The sheet is one of `pick`'s, and what it shares is that module's own.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol

from rich.markup import escape
from textual import on, work
from textual.widgets import Button, Label, OptionList
from textual.widgets.option_list import Option

from .dropdown import Dropdown, Value
from .pick import (
    _ACT_AGAIN,
    _DOT,
    Action,
    Key,
    Sheet,
    _act,
    _asked_for,
    _hmz,
    _homed,
    _when,
    bad,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = ["Stored"]


class Held(Protocol):
    """One epic a target holds, as `Hmz().backups.listed` answers: what this reads of it."""

    @property
    def key(self) -> str: ...
    @property
    def machine(self) -> str: ...
    @property
    def workspace(self) -> str: ...
    @property
    def epic(self) -> str: ...
    @property
    def flow(self) -> str: ...
    @property
    def task(self) -> str: ...
    @property
    def began(self) -> str: ...
    @property
    def how(self) -> str: ...


#: The button another target is picked from, where there is more than one.
_ACT_TARGET = "target"


class Stored(Sheet[tuple[str, ...]]):
    """Every epic one backup target holds, and downloading one: answered with what to say."""

    #: Searched as the epics are: by flow, task and directory.
    SEARCHES: ClassVar = True

    def __init__(self, targets: Sequence[str]) -> None:
        """Opens on the first target.

        Args:
          targets: Every target there is, by name.
        """
        super().__init__()
        self._targets = list(targets)
        self._target = self._targets[0]
        #: What the target holds, newest first, or None while it is fetched.
        self._held: list[Held] | None = None
        #: The epics this machine has, by key.
        self._here: set[str] = set()
        self._was = ""
        self._said = ""
        self._told: list[str] = []

    def crumb(self) -> str:
        """Where it was opened from."""
        return "Download"

    def _ask(self) -> None:
        """Says what this is, and fetches the target."""
        self.query_one("#about", Label).update(
            "Every epic the target holds, by machine and directory, newest first; "
            "enter downloads one here, as an import does."
        )
        self._fetches()

    @work(group="stored", exclusive=True)
    async def _fetches(self) -> None:
        """Fetches what the target holds and which epics are here, off the event loop."""
        import asyncio

        target, self._held, self._said = self._target, None, f"fetching {self._target}…"
        self._fill()

        def fetched() -> tuple[Sequence[Held], set[str]]:
            from hmz.runtime.epic import under

            held = _hmz().backups.listed(target)
            # Here as a download would land it: that epic, under the directory it ran in.
            return held, {
                one.key for one in held if (under(one.workspace) / one.epic).is_dir()
            }

        try:
            held, here = await asyncio.to_thread(fetched)
        except (OSError, ValueError) as why:
            said = _hmz().verses.plain(str(why))
            self._held, self._said = [], bad(escape(f"{target}: {said}"))
        else:
            # Each machine, then each directory on it, in the order their newest epic came.
            newest = held[::-1]
            first: dict[object, int] = {}
            for at, one in enumerate(newest):
                first.setdefault(one.machine, at)
                first.setdefault((one.machine, one.workspace), at)
            self._held = sorted(
                newest,
                key=lambda one: (first[one.machine], first[one.machine, one.workspace]),
            )
            self._here, self._said = here, ""
        self._fill()

    def actions(self) -> list[Action]:
        """Searching, fetching again, and another target where there is one."""
        acts = [
            self._searches(),
            Action(_ACT_AGAIN, "fetch", f"fetch {self._target} again", self._fetches),
        ]
        if len(self._targets) > 1:
            acts.append(
                Action(_ACT_TARGET, "target…", "another backup target", self._picks)
            )
        return acts

    @work
    async def _picks(self) -> None:
        """Drops the targets under the button, and fetches the one picked."""
        if self.opening():
            return
        button = self.query_one(f"#{_act(_ACT_TARGET)}", Button)
        try:
            picked = await self._interface().push_screen_wait(
                Dropdown(
                    "target",
                    [Value(one, one) for one in self._targets],
                    self._target,
                    at=button.region.offset,
                )
            )
        finally:
            self.opened()
        if picked and picked != self._target:
            self._target, self._was = picked, ""
            self._fetches()

    def _fill(self) -> None:
        """Puts each machine up, each directory under it, and each epic under that."""
        self.query_one("#asked", Label).update(f"Download from {escape(self._target)}")
        listing = self.query_one("#choices", OptionList)
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            self._was = str(listing.get_option_at_index(at).id or self._was)
        shown = [
            one
            for one in self._held or []
            if self.fits(one.flow, one.task, one.workspace, one.machine)
        ]
        ids = [f"={one.key}" for one in shown]
        sought = self._sought(ids)
        landing = (
            sought
            if sought is not None
            else self._was
            if self._was in ids
            else ids[0]
            if ids
            else ""
        )
        options: list[Option] = []
        place = ("", "")
        for one in shown:
            if (one.machine, one.workspace) != place:
                if one.machine != place[0]:
                    options.append(
                        Option(f" [$primary]{escape(one.machine)}[/]", disabled=True)
                    )
                options.append(
                    Option(
                        f"   [$text-muted]{escape(_homed(one.workspace))}[/]",
                        disabled=True,
                    )
                )
                place = (one.machine, one.workspace)
            about = _asked_for(one.task) if one.task else "no task"
            about += f"{_DOT}{one.how or 'unfinished'}"
            if one.key in self._here:
                about += f"{_DOT}here"
            options.append(
                Option(
                    self._row(
                        0,
                        f"{_when(one.began)}{_DOT}{one.flow}",
                        about,
                        here=f"={one.key}" == landing,
                        inforce=one.key in self._here,
                    ),
                    id=f"={one.key}",
                )
            )
        listing.set_options(options)
        listing.highlighted = next(
            (n for n, one in enumerate(options) if one.id == landing), None
        )
        self._was = landing
        self._drawn = listing.highlighted
        said = self._said or (
            ""
            if self._held is None or shown
            else f"{escape(self._target)} holds no epic"
        )
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "download"), Key("esc", "back"))

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Downloads the epic chosen, unless it is here already."""
        key = str(event.option.id or "").removeprefix("=")
        one = next((each for each in self._held or [] if each.key == key), None)
        if one is None:
            return
        if one.key in self._here:
            self._said = f"{escape(one.epic)} is here already: open it on /epics"
            self._fill()
            return
        self._pulls(one)

    @work(group="pull")
    async def _pulls(self, one: Held) -> None:
        """Downloads one epic off the event loop, one at a time, and says where it landed."""
        import asyncio

        if self.opening():
            return
        target = self._target
        try:
            self._said = f"downloading {escape(one.epic)}…"
            self._fill()
            hmz = _hmz()

            def pulled() -> tuple[Path, str]:
                at = hmz.backups.pulled(target, one.key)
                return at, hmz.epics.foreign(at)

            at, why = await asyncio.to_thread(pulled)
        except (OSError, ValueError) as why:
            self._said = bad(escape(_hmz().verses.plain(str(why))))
            self._fill()
            return
        finally:
            self.opened()
        self._here.add(one.key)
        said = f"downloaded {at.name} into {_homed(one.workspace)}; open it on /epics"
        if why:
            said += f"; it cannot be resumed here: {why}"
        self._said = escape(said)
        self._told.append(f"[dim]{escape(said)}[/dim]")
        self._fill()

    def leaving(self) -> None:
        """Leaves, answering with what is worth saying in the transcript."""
        self.dismiss(tuple(self._told))
