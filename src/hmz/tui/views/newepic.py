"""New epic: everything an epic is started with, on one page, and one button that starts it.

The web page's New epic page (`src/hmz/web/static/views/new.js`, Section 3.8 of web.md) in a
terminal: a form read top to bottom and seen whole -- the flow, the folder it works in, the
task, an agent and a place for each role the flow declares, the flow's own params as its
schema asks them, what it may spend, where it is backed up, whether it is profiled, and the
epic it picks up. Nothing is a step behind another: a row is written where it stands, or
drops what it can be under it, and what a row is for is said under the list while the cursor
is on it.

What the folder last set the flow up with is what the page opens holding -- the daemon keeps
it (`flows.get`) -- so that starting the same flow again is typing the task and pressing
Start. Start asks the daemon to check the set-up first (`flows.check`), and what it refuses
is said on the row it is about; then the epic starts the way `/flow` starts one.

The form is :class:`hmz.tui.pick.Form`, its params are read by :func:`hmz.tui.asking.fields`,
and what a dropped list does not offer -- an account, an effort, a machine not saved -- is
picked on the sheets `/flow` picks them on.
"""

# The form is every sheet's own, and so are the pieces it is drawn with.
# pyright: reportPrivateUsage=false
# And the page is the interface's own: it starts an epic through what `/flow` starts one.
# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast
from weakref import WeakKeyDictionary

from rich.markup import escape
from textual import work
from textual.actions import SkipAction
from textual.binding import Binding
from textual.widgets import Button, Label, OptionList
from textual.widgets.option_list import Option

from hmz.tui import humanfia
from hmz.tui.asking import Field, _read, _typed, fields, valued
from hmz.tui.dropdown import Value
from hmz.tui.pick import (
    _APART_MARK,
    _CHORD,
    _FINISH,
    _NO,
    _STEPS,
    _WRITES,
    _YES,
    LOCAL_DAEMON,
    Action,
    Drop,
    Form,
    Key,
    Question,
    _rpc,
)
from hmz.tui.shell import View
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from textual.app import App

    from hmz.tui.app import Humanize

__all__ = ["VIEWS", "Draft", "NewEpic"]

#: The rows that are the page's own, each under a mark no role and no param can be named with.
_FLOW = f"{_APART_MARK}flow"
_FOLDER = f"{_APART_MARK}folder"
_TASK = f"{_APART_MARK}task"
_COST = f"{_APART_MARK}cost"
_MINUTES = f"{_APART_MARK}minutes"
_TOKENS = f"{_APART_MARK}tokens"
_PROFILE_FLOW = f"{_APART_MARK}profile-flow"
_PROFILE_ENVIRONMENT = f"{_APART_MARK}profile-environment"
_RESUME = f"{_APART_MARK}resume"

#: What the rows a flow brings are put up under, before the name of what each is about: an
#: agent role, an environment role, a param, a backup target.
_AGENT = f"{_APART_MARK}agent{_APART_MARK}"
_ENV = f"{_APART_MARK}env{_APART_MARK}"
_PARAM = f"{_APART_MARK}param{_APART_MARK}"
_BACKUP = f"{_APART_MARK}backup{_APART_MARK}"

#: The three limits of a budget: the row each is written on, what `epic.start` calls it, the
#: row that says whether the turn under way may finish once it is reached, and what each row
#: is called.
_LIMITS = (
    (_COST, "cost", f"{_APART_MARK}grace-cost", "Cost, $", "Cost graceful"),
    (_MINUTES, "duration", f"{_APART_MARK}grace-time", "Time, min", "Time graceful"),
    (
        _TOKENS,
        "output_tokens",
        f"{_APART_MARK}grace-tokens",
        "Output tokens",
        "Tokens graceful",
    ),
)

#: The value of a dropped list that is no value: the way on to the sheet that picks any.
_MORE = f"{_APART_MARK}more"

#: How many models of one harness a dropped list offers before the sheet that lists them all.
_MODELS = 6

#: How many epics the Resume row offers: the latest of the flow in the folder.
_RUNS = 12

#: What a call of the daemon raises where it was not reached or refused it.
_FAILS = (LookupError, OSError, RuntimeError, ValueError)

#: A duration as a budget is written down: seconds, or ISO 8601.
_ISO = re.compile(
    r"P(?:(?P<d>[\d.]+)D)?(?:T(?:(?P<h>[\d.]+)H)?(?:(?P<m>[\d.]+)M)?(?:(?P<s>[\d.]+)S)?)?"
)

type Asks = Callable[..., Any]
"""One call of the daemon: `asks(method, params)`, raising one of `_FAILS` where refused."""

type Starts = Callable[[str, dict[str, Any]], Awaitable[None]]
"""Starts the epic: the folder ("" for none) and what `epic.start` takes, but its `sub`."""

type Picks = Callable[[str, str, str, str], Awaitable[str | None]]
"""Picks an `agent` or an `env` on a sheet of its own: the kind, the flow, the role, and
what it is now; None for one walked out of."""


class Draft(NamedTuple):
    """What the page held when it was left without starting, for it to be opened on again.

    Attributes:
      flow: The flow picked.
      typed: What each row held, by row.
      cursor: The row the cursor was on.
    """

    flow: str
    typed: dict[str, str]
    cursor: str


def _minutes(duration: object) -> str:
    """A duration a budget kept, in minutes as the row writes it, or "" for none."""
    seconds: float | None = None
    if isinstance(duration, int | float) and not isinstance(duration, bool):
        seconds = float(duration)
    elif isinstance(duration, str) and (said := _ISO.fullmatch(duration.strip())):
        parts = {name: float(one) for name, one in said.groupdict().items() if one}
        if parts:
            seconds = (
                parts.get("d", 0) * 86400
                + parts.get("h", 0) * 3600
                + parts.get("m", 0) * 60
                + parts.get("s", 0)
            )
    if seconds is None or not math.isfinite(seconds):
        return ""
    return _figure(round(seconds / 60, 2))


def _figure(value: object) -> str:
    """A limit a budget kept, as its row writes it: nothing for none, and for no limit."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return ""
    if not math.isfinite(value):
        return ""
    return str(int(value)) if float(value).is_integer() else str(value)


def _held(value: object) -> dict[str, Any]:
    """What the daemon answered as an object, or nothing where it answered none."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _accounts(clis: Mapping[str, Any], cli: str) -> list[dict[str, Any]]:
    """The accounts of one harness, as `flows.backends` has them: this machine's own first."""
    return [_held(one) for one in _held(clis.get(cli)).get("accounts") or ()]


class NewEpic(Form[None]):
    """The New epic page: a form of everything an epic starts with, answered by Start."""

    BINDINGS: ClassVar = [
        Binding("ctrl+s", "done", "start", show=False, priority=True),
    ]

    # Square and heavy, as the zones are ruled, with the one thing to press in pink.
    CSS: ClassVar[str] = """
    NewEpic #sheet { padding: 1 2 0 2; }
    NewEpic #asked { color: $primary; text-style: bold; }
    NewEpic #choices { border: heavy $hmz-line-strong; }
    NewEpic #choices:focus { border: heavy $primary; }
    NewEpic #actions Button.-primary { background: $accent; color: $background; }
    NewEpic #actions Button.-primary:focus { text-style: bold reverse; }
    """

    def __init__(
        self,
        asks: Asks,
        starts: Starts,
        *,
        folder: str,
        picks: Picks | None = None,
        refuses: Callable[[], str] = lambda: "",
        draft: Draft | None = None,
        keep: Callable[[Draft | None], None] = lambda _: None,
    ) -> None:
        """Opens the page on a folder.

        Args:
          asks: One call of the daemon: the method and what it takes.
          starts: What Start does once the set-up has been checked.
          folder: The folder the interface is open in, which the page opens on.
          picks: What picks an agent or an environment a dropped list does not offer, or None
            where there is no such sheet -- the lists then offer what they offer.
          refuses: Why an epic cannot be started now, in words, or "" where it can.
          draft: What the page held when it was last left, or None to open as set up.
          keep: What leaving the page does with what it holds, and starting with None.
        """
        super().__init__()
        self._asks = asks
        self._starts = starts
        self._picks = picks
        self._refuses = refuses
        self._draft = draft
        self._keep = keep
        kept = draft.typed.get(_FOLDER) if draft is not None else None
        self._typed_in = {_FOLDER: folder if kept is None else kept, _TASK: ""}
        #: The folder what is drawn was read for, which a folder written since is not.
        self._read_for: str | None = None
        self._flows: list[dict[str, Any]] = []
        self._declared: dict[str, Any] | None = None
        self._backends: dict[str, Any] = {}
        self._runtimes: list[dict[str, Any]] = []
        self._nous: list[str] = []
        self._targets: list[dict[str, Any]] = []
        self._defaults: list[str] = []
        #: Whether the folder never said where this flow is backed up, and so follows the
        #: defaults for as long as the page leaves them be.
        self._follows = True
        self._fields: list[Field] = []
        #: The epics there are to pick up, and the one picked, as `runs.get` answers it.
        self._runs: list[dict[str, Any]] = []
        self._resumed: dict[str, Any] | None = None
        #: What is wrong with each row, by row, as the page or the daemon found it.
        self._problems: dict[str, str] = {}
        #: What is being waited on, said under the list, or "" for nothing.
        self._busy = ""
        self._sending = False
        #: The row the cursor goes to the next time the rows are put up, or "" to stay.
        self._aim = draft.cursor if draft is not None else _TASK
        #: Whether the row just kept is stayed on, a sheet having opened from it.
        self._stays = False

    # -- What is asked --------------------------------------------------------------------------

    def _ask(self) -> None:
        """Says what the page is, and reads what there is to start."""
        self.query_one("#asked", Label).update(t("New epic"))
        self._fill()
        self._reads()

    def crumb(self) -> str:
        """What the page is called across the top of a sheet opened from it."""
        return t("New epic")

    def _roles(self, kind: str) -> list[dict[str, Any]]:
        """The roles of a kind somebody answers for: not those the flow fills itself."""
        declared = self._declared or {}
        return [
            cast("dict[str, Any]", one)
            for one in declared.get(kind) or ()
            if not one.get("auto")
        ]

    def _flow(self) -> str:
        """The flow picked, by name, or "" for none."""
        return self._typed_in.get(_FLOW, "")

    def _layout(self) -> list[str | Question]:
        """Every row in reading order, each group of them under its heading."""
        typed = self._typed_in
        flow = self._flow()
        declared = self._declared or {}
        rows: list[str | Question] = [
            Question(
                _FLOW,
                t("Flow"),
                str(declared.get("description") or ""),
                _STEPS,
                needed=not flow,
            ),
            t("Environment"),
            Question(
                _FOLDER,
                t("Folder"),
                t(
                    "Left empty, the epic works in a temporary directory made for it "
                    "as it starts."
                ),
                path=True,
            ),
        ]
        rows += [
            Question(
                f"{_ENV}{one['name']}",
                str(one["name"]),
                t(
                    "Where this role works; left as Folder, it works in the epic's "
                    "folder."
                ),
                _STEPS,
            )
            for one in self._roles("envs")
        ]
        rows.append(
            Question(
                _TASK,
                t("Task"),
                t("What should {name} do?", name=flow)
                if flow
                else t("Describe the task"),
                needed=not typed.get(_TASK, "").strip(),
            )
        )
        agents = self._roles("agents")
        if agents:
            rows.append(t("Agents"))
        for one in agents:
            row = f"{_AGENT}{one['name']}"
            skills = [str(skill) for skill in one.get("skills") or ()]
            about = " · ".join(
                part
                for part in (
                    "" if one.get("required") else t("Optional"),
                    str(one.get("harness") or ""),
                    str(_held(one.get("permission")).get("preset") or ""),
                    t("skills: {names}", names=", ".join(skills)) if skills else "",
                )
                if part
            )
            rows.append(
                Question(
                    row,
                    str(one["name"]),
                    about,
                    _STEPS,
                    needed=bool(one.get("required")) and not typed.get(row),
                )
            )
        if self._fields:
            rows.append(t("Parameters"))
        for field in self._fields:
            row = f"{_PARAM}{field.name}"
            rows.append(
                Question(
                    row,
                    field.title,
                    field.about,
                    _STEPS if field.kind == "choice" else _WRITES,
                    secret=field.secret,
                    needed=field.required
                    and not field.nullable
                    and not typed.get(row, "").strip(),
                )
            )
        unbounded = not any(typed.get(row, "").strip() for row, *_ in _LIMITS)
        rows.append(t("Budget"))
        rows += [
            Question(
                row, t(named), t("At least one limit."), needed=unbounded and not at
            )
            for at, (row, _, _, named, _) in enumerate(_LIMITS)
        ]
        rows += [
            Question(grace, t(named), "", _STEPS) for _, _, grace, _, named in _LIMITS
        ]
        if self._targets:
            rows.append(t("Backup"))
        rows += [
            Question(
                f"{_BACKUP}{one['name']}",
                str(one["name"]),
                str(one.get("url") or ""),
                _STEPS,
            )
            for one in self._targets
        ]
        rows += [
            t("Options"),
            Question(_PROFILE_FLOW, t("Profile flow"), "", _STEPS),
            Question(_PROFILE_ENVIRONMENT, t("Profile environment"), "", _STEPS),
        ]
        if declared.get("resumable"):
            rows.append(
                Question(
                    _RESUME,
                    t("Resume"),
                    t(
                        "Picks up {name}, carrying on from where it stopped.",
                        name=typed.get(_RESUME, ""),
                    )
                    if typed.get(_RESUME)
                    else t(
                        "Pick an earlier epic of this flow to carry on from where "
                        "it stopped."
                    ),
                    _STEPS,
                )
            )
        return rows

    def asked(self) -> list[Question]:
        """Every row, in reading order."""
        return [one for one in self._layout() if isinstance(one, Question)]

    def _switches(self, held: str) -> bool:
        """Whether a row is a switch: a grace, a backup target, a profiling."""
        return (
            held in (_PROFILE_FLOW, _PROFILE_ENVIRONMENT)
            or held.startswith(_BACKUP)
            or any(held == grace for _, _, grace, _, _ in _LIMITS)
        )

    def _field(self, held: str) -> Field | None:
        """The param a row asks, or None for a row that asks none."""
        if not held.startswith(_PARAM):
            return None
        name = held.removeprefix(_PARAM)
        return next((one for one in self._fields if one.name == name), None)

    def choices(self, held: str) -> Sequence[str]:
        """What a stepped row is picked from: on and off, a param's choices, or its own list."""
        if self._switches(held):
            return (_YES, _NO)
        field = self._field(held)
        if field is not None:
            return [said for said, _ in field.choices]
        # Something, so that the row drops: what it drops is said by `dropping`.
        return (held,)

    def lines(self, held: str) -> bool:
        """Whether a row takes several lines: the task, and a param of long text, a list or JSON."""
        field = self._field(held)
        return held == _TASK or (
            field is not None and field.kind in ("lines", "list", "json")
        )

    def shown(self, one: Question) -> str:
        """What a row says it holds, on one line, with what an empty one comes to."""
        value = self._typed_in.get(one.held, "")
        if one.kind != _WRITES:
            if one.held == _FLOW:
                return value or t("None")
            if one.held == _RESUME:
                return value or t("None")
            if one.held.startswith(_ENV):
                return value or t("Folder")
            if one.held.startswith(_AGENT):
                return value or t("Pick a nous")
            return value
        if one.secret:
            return "•" * len(value)
        writing = self._editing == one.held
        if one.held == _FOLDER and not value and not writing:
            return t("No folder")
        flat = value.replace("\n", " ⏎ ")
        listing = self.query_one("#choices", OptionList)
        room = max(self._width_of(listing) - len(one.named) - 8, 12)
        if len(flat) <= room:
            return flat
        # The end of it while it is written, which is where the next letter lands.
        return f"…{flat[-(room - 1) :]}" if writing else f"{flat[: room - 1]}…"

    # -- Drawing --------------------------------------------------------------------------------

    def _fill(self) -> None:
        """Puts the rows up under their headings, and says what the row under the cursor is for."""
        listing = self.query_one("#choices", OptionList)
        layout = self._layout()
        rows = self._now = [one for one in layout if isinstance(one, Question)]
        ids = [one.held for one in rows]
        here = self._aim if self._aim in ids else self.under()
        if here not in ids:
            here = ids[0]
        self._aim = ""
        width = self._width_of(listing)
        options: list[Option] = []
        at = 0
        for one in layout:
            if isinstance(one, str):
                rule = humanfia.RULE * max(width - len(one) - 3, 0)
                options.append(
                    Option(f" [b]{escape(one.upper())}[/b] {rule}", disabled=True)
                )
                continue
            if one.held == here:
                at = len(options)
            options.append(
                Option(self._line(one, here=one.held == here), id=f"={one.held}")
            )
        listing.set_options(options)
        listing.highlighted = at
        self._drawn = listing.highlighted
        finishing = bool(self._editing) and self._path(self._editing)
        about = next((one.about for one in rows if one.held == here), "")
        note = self._could_be() if finishing else escape(self._busy or about)
        self.query_one("#tuning", Label).update(
            f"[$error]{escape(self._wrong)}[/]"
            if self._wrong
            else f"[$text-muted]{note}[/]"
            if note
            else ""
        )
        self._footed(
            *(
                (Key(_CHORD, "new line"),)
                if self._editing and self.lines(self._editing)
                else ()
            ),
            *((Key(_FINISH, "complete"),) if finishing else ()),
            Key("ctrl+s", t("start")),
            Key("esc", "back"),
        )

    def _line(self, one: Question, *, here: bool) -> str:
        """One row on one line, what it is for being said under the list, and what is wrong."""
        line = super()._line(one._replace(about=""), here=here)
        problem = self._problems.get(one.held)
        if not problem:
            return line
        # Plain on the row under the cursor, whose own colours a red would sink into.
        said = f"✗ {escape(problem)}"
        return f"{line}\n   {said if here else f'[$error]{said}[/]'}"

    def actions(self) -> list[Action]:
        """Start, the one thing the page does."""
        return [
            Action(
                "done",
                t("Starting…") if self._sending else t("Start"),
                t("Starts the flow"),
                self.action_done,
                variant="primary",
            )
        ]

    def _lands(self, row: str) -> None:
        """Puts the cursor on a row, and the keys on the list."""
        self._aim = row
        self.query_one("#choices", OptionList).focus()
        self._fill()

    # -- Reading what there is ------------------------------------------------------------------

    def _folder(self) -> str:
        """The folder written, as a whole path, or "" for none."""
        typed = self._typed_in.get(_FOLDER, "").strip()
        return str(Path(typed).expanduser().resolve()) if typed else ""

    def _waits(self, on: str) -> None:
        """Says what is being waited on under the list, or nothing once it has come."""
        self._busy = on
        if self._up():
            self._fill()

    def _fails(self, why: BaseException) -> None:
        """Says a call of the daemon failed, in the daemon's words."""
        self._busy = ""
        self._sending = False
        self._wrong = str(why) or type(why).__name__
        if self._up():
            self._fill()

    async def _asked(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        """One call of the daemon, off the screen's own thread."""
        return await asyncio.to_thread(self._asks, method, dict(params or {}))

    async def _tried(
        self, method: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """One call of the daemon the page does without: nothing where it fails."""
        try:
            return cast("dict[str, Any]", await self._asked(method, params) or {})
        except _FAILS:
            return {}

    @work(exclusive=True, group="reads")
    async def _reads(self) -> None:
        """Reads what the folder offers: its flows, the harnesses, the runtimes, the targets."""
        folder = self._folder()
        within = {"workspace": folder} if folder else {}
        self._waits(t("Reading…"))
        try:
            found, backends, runtimes, settings, nous = await asyncio.gather(
                self._asked("flows.list", within),
                self._asked("flows.backends"),
                self._tried("runtimes.list"),
                self._tried("settings.get", within),
                self._tried("nous.list"),
            )
        except _FAILS as why:
            self._fails(why)
            return
        self._read_for = folder
        self._flows = list(found.get("flows") or ())
        self._backends = dict(backends or {})
        self._runtimes = list(runtimes.get("runtimes") or ())
        backup = cast("dict[str, Any]", settings.get("backup") or {})
        self._targets = list(backup.get("targets") or ())
        self._defaults = [str(one) for one in backup.get("defaults") or ()]
        self._nous = [
            str(one["name"]) for one in nous.get("nous") or () if one.get("virtual")
        ]
        names = [str(one.get("name")) for one in self._flows]
        draft = self._draft
        wanted = next(
            (
                one
                for one in (
                    draft.flow if draft is not None else "",
                    str(found.get("flow") or ""),
                    self._flow(),
                    names[0] if names else "",
                )
                if one in names
            ),
            "",
        )
        if not wanted:
            self._declared = None
            self._fields = []
            self._typed_in.pop(_FLOW, None)
            self._busy = ""
            self._wrong = t("No flow installed yet.")
            if self._up():
                self._fill()
            return
        await self._chooses(wanted)
        self._asks_models()

    async def _chooses(self, name: str) -> None:
        """Takes a flow as the one to start, set up as the folder last set it up."""
        folder = self._folder()
        within = {"workspace": folder} if folder else {}
        self._waits(t("Reading…"))
        try:
            declared = await self._asked("flows.get", {"name": name, **within})
        except _FAILS as why:
            self._fails(why)
            return
        self._declared = dict(declared)
        self._typed_in[_FLOW] = name
        self._resumed = None
        self._runs = []
        self._problems = {}
        self._wrong = ""
        self._sets_up(cast("dict[str, Any]", declared.get("remembered") or {}))
        draft, self._draft = self._draft, None
        if draft is not None and draft.flow == name:
            # What was left unsaid when the page was last left, over what the folder kept.
            rows = {one.held for one in self.asked()}
            held = {
                row: said
                for row, said in draft.typed.items()
                if row in rows and row not in (_FLOW, _FOLDER, _RESUME)
            }
            if any(
                said != self._typed_in.get(row)
                for row, said in held.items()
                if row.startswith(_BACKUP)
            ):
                self._follows = False
            self._typed_in.update(held)
            if draft.cursor in rows:
                self._aim = draft.cursor
        if declared.get("resumable"):
            listed = await self._tried(
                "runs.list", {**within, "flow": name, "limit": _RUNS}
            )
            self._runs = [
                cast("dict[str, Any]", one)
                for one in listed.get("runs") or ()
                if one.get("resumable") and not one.get("held")
            ]
        self._waits("")

    def _sets_up(self, kept: Mapping[str, Any]) -> None:
        """Fills the rows a flow brings with what was kept for it: a folder's, or an epic's."""
        typed = self._typed_in
        for row in [
            one for one in typed if one.startswith((_AGENT, _ENV, _PARAM, _BACKUP))
        ]:
            del typed[row]
        self._fresh.clear()
        declared = self._declared or {}
        agents = cast("dict[str, Any]", kept.get("agents") or {})
        for one in self._roles("agents"):
            typed[f"{_AGENT}{one['name']}"] = str(agents.get(one["name"]) or "")
        envs = cast("dict[str, Any]", kept.get("envs") or {})
        for one in self._roles("envs"):
            typed[f"{_ENV}{one['name']}"] = str(envs.get(one["name"]) or "")
        self._fields = [
            one
            for one in fields(cast("Mapping[str, Any] | None", declared.get("params")))
            if one.name
        ]
        params = cast("dict[str, Any]", kept.get("params") or {})
        for field in self._fields:
            row = f"{_PARAM}{field.name}"
            if field.name in params:
                typed[row] = _typed(field, params[field.name])
            elif field.has_default:
                typed[row] = _typed(field, field.default)
                if field.kind != "choice":
                    self._fresh.add(row)
            else:
                typed[row] = ""
        budget = cast("dict[str, Any]", kept.get("budget") or {})
        typed[_COST] = _figure(budget.get("cost"))
        typed[_MINUTES] = _minutes(budget.get("duration"))
        typed[_TOKENS] = _figure(budget.get("output_tokens"))
        graceful: object = budget.get("graceful")
        for _, limit, grace, _, _ in _LIMITS:
            lets = _held(graceful).get(limit, True) if _held(graceful) else graceful
            typed[grace] = _NO if lets is False else _YES
        backup: Any = kept.get("backup")
        self._follows = backup is None
        goes = self._defaults if backup is None else [str(one) for one in backup]
        for one in self._targets:
            typed[f"{_BACKUP}{one['name']}"] = _YES if one["name"] in goes else _NO
        typed[_PROFILE_FLOW] = _YES if kept.get("profile_flow") else _NO
        typed[_PROFILE_ENVIRONMENT] = _YES if kept.get("profile_environment") else _NO
        typed[_RESUME] = ""

    @work(exclusive=True, group="models")
    async def _asks_models(self) -> None:
        """Asks each harness nobody has asked yet what it runs, so its models can be offered."""
        clis = cast("dict[str, Any]", self._backends.get("clis") or {})
        wanted = {
            str(cli) for role in self._roles("agents") for cli in role.get("clis") or ()
        }
        unasked = [
            cli
            for cli in sorted(wanted)
            for own in _accounts(clis, cli)[:1]
            if not own.get("name") and not own.get("models") and not own.get("asked")
        ]
        if not unasked:
            return
        for cli in unasked:
            try:
                await asyncio.to_thread(
                    self._asks, "accounts.models", {"cli": cli, "name": ""}, writes=True
                )
            except _FAILS:
                continue
        self._backends = await self._tried("flows.backends") or self._backends
        if self._up():
            self._fill()

    # -- Picking --------------------------------------------------------------------------------

    def _agents_for(self, role: Mapping[str, Any], now: str) -> list[Value]:
        """What an agent role's list offers: every virtual nous, then each harness's models."""
        values = [Value(name, name, group=t("Virtual")) for name in self._nous]
        clis = cast("dict[str, Any]", self._backends.get("clis") or {})
        for cli in role.get("clis") or ():
            own = next(
                (one for one in _accounts(clis, str(cli)) if not one.get("name")),
                _held(None),
            )
            values += [
                Value(spec, spec, group=str(cli))
                for one in list(own.get("models") or ())[:_MODELS]
                # No effort is written `auto`: the harness's own.
                for spec in [f"{cli}/{one['name']}:auto"]
            ]
        if now and all(one.value != now for one in values):
            values.insert(0, Value(now, now))
        if not values:
            values.append(
                Value("", t("No harness installed here can fill it."), inert=True)
            )
        if self._picks is not None:
            values.append(Value(_MORE, t("More options")))
        return values

    def _envs_for(self, now: str) -> list[Value]:
        """What an environment role's list offers: the folder, then each runtime saved."""
        values = [Value("", t("Folder"))]
        values += [
            Value(spec, spec, group=str(one.get("backend") or ""))
            for one in self._runtimes
            if one.get("backend") and one.get("name")
            for spec in [f"{one['backend']}@{one['name']}"]
        ]
        if now and all(one.value != now for one in values):
            values.insert(1, Value(now, now))
        if self._picks is not None:
            values.append(Value(_MORE, t("More options")))
        return values

    def dropping(self, row: str) -> Drop:
        """What a row drops: the flows, a role's agents or places, the epics to pick up."""
        now = self._typed_in.get(row, "")
        named = next((one.named for one in self.asked() if one.held == row), "")
        if row == _FLOW:
            return Drop(
                named,
                [
                    Value(
                        str(one.get("name")),
                        str(one.get("name")),
                        str(one.get("about") or ""),
                        str(one.get("whose") or ""),
                    )
                    for one in self._flows
                ],
                now,
            )
        if row.startswith(_AGENT):
            role = next(
                one
                for one in self._roles("agents")
                if one["name"] == row.removeprefix(_AGENT)
            )
            return Drop(named, self._agents_for(role, now), now)
        if row.startswith(_ENV):
            return Drop(named, self._envs_for(now), now)
        if row == _RESUME:
            return Drop(
                named,
                [
                    Value("", t("None")),
                    *(
                        Value(
                            str(one.get("name")),
                            str(one.get("name")),
                            str(one.get("task") or ""),
                        )
                        for one in self._runs
                    ),
                ],
                now,
            )
        return super().dropping(row)

    def dropped(self, row: str, picked: str) -> None:
        """Holds what was picked, and lets what follows from it follow."""
        self._problems.pop(row, None)
        self._wrong = ""
        if picked == _MORE:
            self._stays = True
            self._more(row)
        elif row == _FLOW:
            self._stays = True
            self._turns_to(picked)
        elif row == _RESUME:
            self._picks_up(picked)
        else:
            if row.startswith(_BACKUP):
                self._follows = False
            self._typed_in[row] = picked

    @work(exclusive=True, group="reads")
    async def _turns_to(self, name: str) -> None:
        """Turns the page to another flow."""
        await self._chooses(name)
        self._asks_models()

    @work
    async def _more(self, row: str) -> None:
        """Picks what a role is on the sheet `/flow` picks it on, and holds what it answers."""
        if self._picks is None or self.opening():
            return
        kind = "agent" if row.startswith(_AGENT) else "env"
        role = row.removeprefix(_AGENT if kind == "agent" else _ENV)
        try:
            said = await self._picks(
                kind, self._flow(), role, self._typed_in.get(row, "")
            )
        finally:
            self.opened()
        if said is not None:
            self._typed_in[row] = said
            self._problems.pop(row, None)
        if self._up():
            self._lands(row)

    @work(exclusive=True, group="resumes")
    async def _picks_up(self, name: str) -> None:
        """Takes an epic as the one to pick up, set up as it ran, or lets go of the one taken."""
        self._typed_in[_RESUME] = ""
        self._resumed = None
        if not name:
            self._waits("")
            return
        self._waits(t("Reading…"))
        try:
            ran = cast("dict[str, Any]", await self._asked("runs.get", {"name": name}))
        except _FAILS as why:
            self._fails(why)
            return
        task = self._typed_in.get(_TASK, "")
        self._sets_up(
            {
                "agents": {
                    one.get("role"): one.get("runs") for one in ran.get("agents") or ()
                },
                "envs": dict(
                    str(one).split("=", 1)
                    for one in ran.get("envs") or ()
                    if "=" in str(one)
                ),
                "params": ran.get("params"),
                "budget": ran.get("budget"),
                "profile_flow": ran.get("profile_flow"),
                "profile_environment": ran.get("profile_environment"),
                "backup": ran.get("backup"),
            }
        )
        self._resumed = ran
        self._typed_in[_RESUME] = name
        self._typed_in[_TASK] = task or str(ran.get("task") or "")
        self._waits("")

    def writes(self, row: str, event: Any) -> bool:
        """Types into a written row, and lets go of what was wrong with it."""
        taken = super().writes(row, event)
        if taken:
            self._problems.pop(row, None)
        return taken

    def kept(self, row: str) -> None:
        """Moves on from a row just kept: to what is still to be answered, else to Start.

        A folder written is a folder to read: its flows, and what it last set them up with.
        """
        if row == _FOLDER and self._folder() != self._read_for:
            self._reads()
        self._fill()
        if self._stays:
            self._stays = False
            return
        rows = self._now or []
        at = next((seen for seen, one in enumerate(rows) if one.held == row), None)
        if at is None:
            return
        onward = next((one.held for one in rows[at + 1 :] if one.needed), None)
        if onward is None and rows[at].kind == _STEPS and at + 1 < len(rows):
            onward = rows[at + 1].held
        if onward is not None:
            self._lands(onward)
            return
        for done in self.query("#act-done").results(Button):
            done.focus()

    # -- Starting -------------------------------------------------------------------------------

    def _budget(self, problems: dict[str, str]) -> dict[str, Any] | None:
        """The budget the rows come to, or None where none of them sets a limit."""
        typed = self._typed_in
        said: dict[str, Any] = {}
        for row, limit, _, _, _ in _LIMITS:
            written = typed.get(row, "").strip()
            if not written:
                continue
            value, wrong = _read("integer" if row == _TOKENS else "number", written)
            if wrong:
                problems[row] = wrong
            elif value > 0:
                said[limit] = value * 60 if row == _MINUTES else value
        if not said:
            if not any(row in problems for row, *_ in _LIMITS):
                problems[_COST] = t("Set at least one limit of the budget.")
            return None
        flags = {limit: typed.get(grace) != _NO for _, limit, grace, _, _ in _LIMITS}
        every = set(flags.values())
        said["graceful"] = every.pop() if len(every) == 1 else flags
        return said

    def _read_all(self) -> tuple[dict[str, Any], dict[str, str]]:
        """What the page holds, as `epic.start` takes it, and what is wrong with it, by row."""
        typed = self._typed_in
        problems: dict[str, str] = {}
        flow = self._flow()
        if not flow or self._declared is None:
            problems[_FLOW] = (
                t("Pick a flow first.")
                if self._flows
                else t("Install a flow first, from Flows.")
            )
        task = typed.get(_TASK, "").strip()
        if not task:
            problems[_TASK] = t("Describe the task")
        agents: dict[str, str] = {}
        for one in self._roles("agents"):
            said = typed.get(f"{_AGENT}{one['name']}", "")
            if said:
                agents[str(one["name"])] = said
            elif one.get("required"):
                problems[f"{_AGENT}{one['name']}"] = t(
                    "Pick an agent for {role}.", role=one["name"]
                )
        envs = {
            str(one["name"]): said
            for one in self._roles("envs")
            if (said := typed.get(f"{_ENV}{one['name']}", ""))
        }
        params, wrong = valued(
            self._fields,
            {one.name: typed.get(f"{_PARAM}{one.name}", "") for one in self._fields},
        )
        problems.update({f"{_PARAM}{name}": said for name, said in wrong.items()})
        budget = self._budget(problems)
        backup = [
            str(one["name"])
            for one in self._targets
            if typed.get(f"{_BACKUP}{one['name']}") == _YES
        ]
        ran = self._resumed
        return (
            {
                "flow": flow,
                "task": task,
                "agents": agents,
                "envs": envs,
                "params": params if self._fields else None,
                "budget": budget,
                "profile_flow": typed.get(_PROFILE_FLOW) == _YES,
                "profile_environment": typed.get(_PROFILE_ENVIRONMENT) == _YES,
                # The defaults left as they are go on following the defaults.
                "backup": None if self._follows or not self._targets else backup,
                "resume": str(ran.get("at") or ran.get("name"))
                if ran is not None
                else False,
            },
            problems,
        )

    def action_done(self) -> None:
        """Starts the epic, or says what is still to be answered and goes to it."""
        if self._sending:
            return
        if self._editing:
            self._keeps_writing()
        if self._folder() != self._read_for:
            # Written and not kept: what is drawn is another folder's, so it is read first.
            self._reads()
            return
        if self._busy:
            return  # still reading, and what is read is what would be started
        start, problems = self._read_all()
        self._problems = problems
        self._wrong = ""
        if problems:
            self._lands(next(one.held for one in self.asked() if one.held in problems))
            return
        if why := self._refuses():
            self._wrong = why
            self._fill()
            return
        self._sending = True
        self._waits(t("Checking…"))
        self._checks(start)

    @work
    async def _checks(self, start: dict[str, Any]) -> None:
        """Has the daemon check the set-up, and starts the epic where it finds nothing."""
        folder = self._folder()
        checked = {key: value for key, value in start.items() if key != "task"}
        try:
            await self._asked(
                "flows.check",
                {"workspace": folder or self._home(), **checked},
            )
        except _FAILS as why:
            self.refused(str(why) or type(why).__name__)
            return
        self._waits(t("Starting…"))
        try:
            await self._starts(folder, start)
        except _FAILS as why:
            self._problems = {}
            self._fails(why)
            return
        self._keep(None)
        self.dismiss(None)

    @staticmethod
    def _home() -> str:
        """Where an epic of no folder is checked: the home, whose flows are everybody's."""
        return str(Path.home())

    def refused(self, why: str) -> None:
        """Says what the daemon refused, on the row it is about where it names one.

        Args:
          why: The refusal, in its words.
        """
        self._sending = False
        self._busy = ""
        said = why.casefold()

        def names(word: str) -> bool:
            return bool(
                re.search(rf"(?<![\w-]){re.escape(word.casefold())}(?![\w-])", said)
            )

        about = [
            *(
                f"{_AGENT}{one['name']}"
                for one in self._roles("agents")
                if names(str(one["name"]))
            ),
            *(
                f"{_ENV}{one['name']}"
                for one in self._roles("envs")
                if names(str(one["name"]))
            ),
            *(f"{_PARAM}{one.name}" for one in self._fields if names(one.name)),
            *([_COST] if "budget" in said else []),
            *([_RESUME] if "resum" in said and self._resumed is not None else []),
        ]
        rows = [one.held for one in self.asked()]
        about = [row for row in about if row in rows]
        if not about:
            self._problems = {}
            self._wrong = why
            if self._up():
                self._fill()
            return
        self._problems = {about[0]: why}
        self._wrong = ""
        if self._up():
            self._lands(about[0])

    # -- Leaving --------------------------------------------------------------------------------

    def _holding(self) -> bool:
        """Nothing here is lost to leaving it, so nothing is said to be unsaved."""
        return False

    def closes(self) -> None:
        """Leaves, keeping what was written for the next time the page is opened."""
        if self._sending:
            return  # on its way: it either starts, or says what refused it
        if self._editing:
            self._keeps_writing()
        self._keep(Draft(self._flow(), dict(self._typed_in), self.under()))
        self.dismiss(None)


# -- The page in the interface --------------------------------------------------------------------

#: What each interface's page held when it was last left.
_DRAFTS: WeakKeyDictionary[App[Any], Draft] = WeakKeyDictionary()

#: The flow and the folder each interface's page is to open on the next time it is made.
_ON: WeakKeyDictionary[App[Any], tuple[str, str]] = WeakKeyDictionary()


async def opens(app: App[Any], *, flow: str = "", folder: str = "") -> None:
    """Opens the New epic page of an interface on a flow and a folder.

    Args:
      app: The interface, which has the shell the page is opened by.
      flow: The flow to start, by name, or "" for the one the page would open on.
      folder: The folder the epic is to be of, or "" for the one the page would open on.
    """
    if flow or folder:
        _ON[app] = (flow, folder)
    await cast("Any", app).shell.opens("newepic")


def _opening(app: App[Any]) -> Draft | None:
    """What the page opens holding: what it last held, turned to what was asked for."""
    draft = _DRAFTS.get(app)
    flow, folder = _ON.pop(app, ("", ""))
    if not flow and not folder:
        return draft
    typed = dict(draft.typed) if draft is not None else {}
    if flow and draft is not None and flow != draft.flow:
        # Another flow's rows are not this one's: what every flow has is carried over.
        typed = {row: said for row, said in typed.items() if row in (_FOLDER, _TASK)}
    if folder:
        typed[_FOLDER] = folder
    return Draft(
        flow or (draft.flow if draft is not None else ""),
        typed,
        draft.cursor if draft is not None else _TASK,
    )


def _asks(method: str, params: Mapping[str, Any], *, writes: bool = False) -> Any:
    """One call of this machine's daemon."""
    return _rpc(LOCAL_DAEMON, method, params, writes=writes)


def _started_there(folder: str, start: Mapping[str, Any]) -> str:
    """Starts an epic on the host of another folder, or of none, and lets go of it.

    Args:
      folder: The folder, or "" for a directory of the epic's own.
      start: What `epic.start` takes, but its `sub`.

    Returns:
      The directory it works in.

    Raises:
      OSError: If the host was not reached, or refused it, saying why.
    """
    import secrets

    from hmz import daemon
    from hmz.daemon import where
    from hmz.daemon.link import dialed
    from hmz.rpc import Closed, RpcError

    daemon.start()
    peer, _ = dialed(where.at(), kind="tui")
    try:
        attached = peer.call(
            "epic.attach",
            {"workspace": folder, "slot": "", "replay": False, "scratch": not folder},
            timeout=_PATIENCE,
        )
        peer.call(
            "epic.start",
            {
                **start,
                "sub": attached["sub"],
                "remember": True,
                "idem": secrets.token_urlsafe(12),
            },
            timeout=_PATIENCE,
        )
        return str(attached.get("workspace") or folder)
    except RpcError as why:
        raise OSError(why.message) from why
    except (Closed, TimeoutError) as why:
        raise OSError(str(why) or "the daemon went away") from why
    finally:
        peer.close()


#: How long a host is given to come up and to start an epic: a fork, and a flow imported.
_PATIENCE = 120.0


def _made(app: App[None]) -> NewEpic:
    """The page for an interface: the daemon asked, and the epic started as `/flow` starts one.

    From the log alone: over a sheet, the monitor or an environment the key is theirs, and on
    the page itself it closes it.
    """
    if len(app.screen_stack) > 1:
        _ON.pop(app, None)
        raise SkipAction
    host = cast("Humanize", app)
    here = str(Path(host.hmz.workspace).resolve())

    def refuses() -> str:
        if host._afar is not None:
            return t(
                "Press esc to leave the remote daemon before starting an epic here."
            )
        return ""

    async def starts(folder: str, start: dict[str, Any]) -> None:
        if folder != here:
            there = await asyncio.to_thread(_started_there, folder, start)
            text = (
                "Started the epic in {folder}. It is listed under `/epics`."
                if folder
                else "Started the epic in its own directory, {folder}. It is listed "
                "under `/epics`."
            )
            host.show(f"[dim]{escape(t(text, folder=there))}[/dim]")
            return
        if host.flow_running() or host._starting:
            raise OSError(
                t(
                    "An epic is already running here; stop it or wait for it to end "
                    "first."
                )
            )
        _starts_here(host, start)

    async def picks(kind: str, flow: str, role: str, now: str) -> str | None:
        return await _picked(host, kind, flow, role, now)

    return NewEpic(
        _asks,
        starts,
        folder=here,
        picks=picks,
        refuses=refuses,
        draft=_opening(app),
        keep=lambda draft: _kept(app, draft),
    )


def _kept(app: App[Any], draft: Draft | None) -> None:
    """Keeps what an interface's page held, or lets go of it once it has started."""
    if draft is None:
        _DRAFTS.pop(app, None)
    else:
        _DRAFTS[app] = draft


def _starts_here(host: Humanize, start: Mapping[str, Any]) -> None:
    """Starts an epic in the interface's own folder, the way `/flow` starts one.

    Set up through what `/flow` is saved through, which is what writes down what the folder
    runs the flow with, and started on the task as a `$` line starts it.
    """
    from hmz.flows import Budget
    from hmz.runtime.kept import Runs, read_back
    from hmz.tui.pick import Chosen, params_of

    flow = str(start["flow"])
    backup = start.get("backup")
    chosen = Chosen(
        flow,
        {
            role: read_back(said) or Runs(str(said))
            for role, said in dict(start.get("agents") or {}).items()
        },
        dict(start.get("envs") or {}),
        params_of(flow, start.get("params") or {}),
        Budget.model_validate(start["budget"]),
        bool(start.get("profile_flow")),
        bool(start.get("profile_environment")),
        None if backup is None else tuple(backup),
    )
    task, resume = str(start["task"]), start.get("resume")
    if resume:
        # Set up as the page holds it, then carried on as `/resume` carries one on.
        host._took_flow(chosen, running=False)
        host._flow(task, resume=Path(str(resume)))
        return
    host._took_flow(chosen, running=False, starting=task)


async def _picked(
    host: Humanize, kind: str, flow: str, role: str, now: str
) -> str | None:
    """Picks an agent or an environment on the sheet `/flow` picks it on.

    Returns:
      What was picked, as `-a` or `-e` spells it, or None for a sheet walked out of.
    """
    from hmz.runtime.kept import Runs, read_back, written
    from hmz.tui.pick import Agent, Placing, _hmz, declared_of

    if kind == "env":
        return await host.push_screen_wait(Placing(role, now))
    agents = _hmz().installed()
    unavailable = _hmz().installable()
    agents.update(unavailable)
    declared = declared_of(flow)
    chosen = await host.push_screen_wait(
        Agent(
            role,
            read_back(now) or Runs(now),
            agents,
            role=next((one for one in declared.agents if one.name == role), None)
            if declared is not None
            else None,
            unavailable=frozenset(unavailable),
        )
    )
    return written(chosen) if chosen is not None else None


VIEWS = (View("newepic", "page", "New epic", _made, key="ctrl+e", hint="New epic"),)
