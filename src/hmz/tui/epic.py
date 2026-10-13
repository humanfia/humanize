"""One epic read back: its graph, the flows it called, its sessions, and what each one said.

What the monitor draws of the run going, drawn of any epic -- one that ended last week, or one
going now -- out of what it wrote down and the logs its sessions kept: a box per agent in the
order it was given them, the handovers between neighbours as the arrows the monitor draws, the
tree of flows it called, and under each agent the sessions it opened, each read whole on a
sheet of its own. Reached from the epic's own sheet in `/epics`, as the rest of what there is
to do with one is.
"""

# The sheets' own module, split along the two sheets of it that read an epic back: they draw
# with the marks the monitor and the sheets draw with, so they read what those keep to
# themselves.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING, Any, ClassVar

from rich.markup import escape
from textual import on, work
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from .monitoring import _across, _boxed, _joins, _Said
from .pick import (
    _DOT,
    _INDENT,
    _LABEL,
    Action,
    Key,
    Sheet,
    _figures,
    _hmz,
    _many,
    _shade,
    _when,
    bad,
    chatting,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hmz.runtime.epic import Called, Ran, Session

__all__ = ["Graph", "SessionRead"]

#: The button an epic is opened in Exomyth from, as the graph of the run going is.
_ACT_EXOMYTH = "exomyth"

#: How much of one thing a session did a row says, before it is opened to say all of it: so
#: many characters, on so many lines.
_ENOUGH, _LINES = 400, 6


class Graph(Sheet[None]):
    """One epic as its graph: its agents and their handovers, its called flows, its sessions.

    Read off the screen -- every log the epic's sessions kept is read -- so it opens on the
    agents and sessions the epic wrote down, and the turns and handovers come in once read.
    Enter on a session reads it whole; the button under the list opens the epic in Exomyth,
    as the graph of the run going does.
    """

    SEARCHES: ClassVar = False

    def __init__(self, ran: Ran) -> None:
        """Opens on one epic, which is read once the sheet is up.

        Args:
          ran: The epic.
        """
        super().__init__()
        self._ran = ran
        #: Each session, by its key in the trace -- `<cli>:<id>` -- as `<agent>/<n>`, in the
        #: order opened: once, however many of the epic's records wrote it down.
        self._sessions: dict[str, tuple[str, Session]] = {}
        counted: dict[str, int] = {}
        for one in ran.sessions:
            key = f"{one.backend}:{one.ident}"
            if key not in self._sessions:
                counted[one.agent] = counted.get(one.agent, 0) + 1
                self._sessions[key] = (f"{one.agent}/{counted[one.agent]}", one)
        #: Each session's transcript, by its key in the trace, or None until read.
        self._said: dict[str, dict[str, Any]] | None = None
        #: The flows it called, as a tree, once read.
        self._calls: tuple[Called, ...] = ()
        #: What is worth saying under the list.
        self._told = "reading its logs…"

    def _ask(self) -> None:
        """Says which epic this is, and reads it."""
        ran = self._ran
        # Named as its own sheet was, which is put away while this is up.
        self.query_one("#asked", Label).update(
            escape(f"{_when(ran.began)}{_DOT}{ran.flow}")
        )
        self.query_one("#about", Label).update(
            escape(_DOT.join([*_figures(ran), _many(len(ran.sessions), "session")]))
        )
        self._fill()
        self._reads()

    @work(group="graph", exclusive=True)
    async def _reads(self) -> None:
        """Reads every session's transcript and the tree of calls, off the event loop."""
        import asyncio

        epics = _hmz().epics
        try:
            said, calls = await asyncio.to_thread(
                lambda: (epics.transcripts(self._ran.at), epics.tree(self._ran.at))
            )
        except Exception as why:  # noqa: BLE001 -- a log is a file some CLI wrote
            self._told = bad(escape(str(why) or type(why).__name__))
        else:
            self._said = {one["key"]: one for one in said}
            self._calls = calls
            self._told = "" if said else "its logs held nothing said"
        self._fill()

    def actions(self) -> list[Action]:
        """Opening the epic in Exomyth, which a chat has no timeline for."""
        if chatting(self._ran.flow):
            return []
        return [
            Action(
                _ACT_EXOMYTH,
                "Exomyth",
                "the epic as a timeline of its sessions",
                self._exomyth,
            )
        ]

    def enters(self, row: str) -> bool:
        """Every row that can be landed on is a session, which the arrow right reads."""
        return bool(row)

    def _fill(self) -> None:
        """Puts the agents up as boxes, each with its sessions under it, and the calls."""
        ran = self._ran
        listing = self.query_one("#choices", OptionList)
        was = self.under()
        names = list(
            dict.fromkeys(
                [one.name or one.agent for one in ran.agents]
                + [one.agent for one in ran.sessions]
            )
        )
        runs = {one.name or one.agent: one.spec for one in ran.agents}
        owner = {key: one.agent for key, (_, one) in self._sessions.items()}
        turns, handovers = _handed(self._said or {}, owner)
        width = _across(self._width_of(listing))
        rows: list[Option] = []
        for at, name in enumerate(names):
            mine = [
                (key, said)
                for key, (said, one) in self._sessions.items()
                if one.agent == name
            ]
            arrows = (
                _joins(
                    handovers.get((names[at - 1], name), 0),
                    handovers.get((name, names[at - 1]), 0),
                )
                if at
                else []
            )
            taken = turns.get(name, 0)
            box = _boxed(
                [
                    _Said("$foreground", name),
                    _Said(
                        "$text-muted",
                        _DOT.join(
                            part
                            for part in (
                                runs.get(name, ""),
                                _many(taken, "turn") if self._said is not None else "",
                                _many(len(mine), "session"),
                            )
                            if part
                        ),
                    ),
                ],
                width,
            )
            rows.append(
                Option(
                    "\n".join(_INDENT + line for line in arrows + box), disabled=True
                )
            )
            rows.extend(
                Option(
                    self._row(
                        0,
                        said,
                        self._session(key),
                        here=key == was,
                        inforce=False,
                    ),
                    id=f"={key}",
                )
                for key, said in mine
            )
        if self._calls:
            rows.append(Option(" [$primary]called flows[/]", disabled=True))
            rows.extend(
                Option(line, disabled=True) for line in _tree(self._calls, depth=0)
            )
        listing.set_options(rows)
        ids = [str(one.id or "").removeprefix("=") for one in rows]
        landing = was if was and was in ids else next((one for one in ids if one), "")
        listing.highlighted = ids.index(landing) if landing else None
        self._drawn = listing.highlighted
        if landing != was and landing:
            # Drawn against the row the cursor landed on, which it was not drawn against.
            self._fill()
            return
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{self._told}[/]" if self._told else ""
        )
        self._footed(Key("enter", "read"), Key("esc", "back"))

    def _session(self, key: str) -> str:
        """What a session's row says about it: which CLI and account, and how much it did."""
        _, one = self._sessions[key]
        where = "@".join(part for part in (one.backend, one.provider) if part)
        if self._said is None:
            return where
        actions = (self._said.get(key) or {}).get("actions") or ()
        return f"{where}{_DOT}{_many(len(actions), 'action')}"

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Reads the session under the cursor whole.

        Args:
          event: What was chosen.
        """
        key = str(event.option.id or "").removeprefix("=")
        if key not in self._sessions or self._said is None:
            return
        self._interface().push_screen(
            SessionRead(
                self._sessions[key][0], (self._said.get(key) or {}).get("actions") or []
            )
        )

    def _exomyth(self) -> None:
        """Opens the epic in Exomyth."""
        from .exomyth import Exomyth

        self._interface().push_screen(Exomyth(self._ran))


def _handed(
    said: dict[str, dict[str, Any]], owner: dict[str, str]
) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    """How many turns each agent took, and how often each handed on to each other.

    Read as the web reads them off an epic written down: every turn of every session, in the
    order they were taken, and a handover wherever one agent's turn follows another's.

    Args:
      said: Each session's transcript, by its key in the trace.
      owner: The agent each session is of, by its key in the trace.

    Returns:
      The turns, by agent, and the handovers, by the agent handing and the one handed to.
    """
    taken = sorted(
        (float(action["start"]), owner.get(key) or one.get("agent") or key)
        for key, one in said.items()
        for action in one.get("actions") or ()
        if action.get("category") == "turn"
    )
    turns: dict[str, int] = {}
    handovers: dict[tuple[str, str], int] = {}
    for at, (_, agent) in enumerate(taken):
        turns[agent] = turns.get(agent, 0) + 1
        if at and taken[at - 1][1] != agent:
            pair = (taken[at - 1][1], agent)
            handovers[pair] = handovers.get(pair, 0) + 1
    return turns, handovers


def _tree(calls: Sequence[Called], *, depth: int) -> list[str]:
    """The flows an epic called, one line apiece, each call indented under its caller."""
    lines: list[str] = []
    for one in calls:
        how = f"{_DOT}{one.how}" if one.how else ""
        task = f"{_DOT}{' '.join(one.task.split())[:80]}" if one.task.strip() else ""
        lines.append(
            f"{_INDENT}{'  ' * depth}[b]{escape(one.flow)}[/]"
            f"[$text-muted]{escape(how + task)}[/]"
        )
        lines.extend(_tree(one.calls, depth=depth + 1))
    return lines


class SessionRead(Sheet[None]):
    """One session of an epic, read back out of its log: each thing it did, in order.

    A row per thing -- a turn and what it was asked, a model call and its thinking, a tool and
    what went in and came out, what it said -- each cut to a few lines and said whole with
    enter. Searched with `/`, as a transcript somebody is looking for one line in is.
    """

    def __init__(self, named: str, actions: Sequence[dict[str, Any]]) -> None:
        """Opens on one session's actions.

        Args:
          named: The session, as `<agent>/<n>`.
          actions: What it did, as :meth:`hmz.runtime.Epics.transcripts` says it.
        """
        super().__init__()
        self._named = named
        #: Each action as its row says it, worked out once: a tool's JSON is laid out again
        #: on every keystroke otherwise.
        self._actions = [_action(one) for one in actions]
        #: The rows said whole, by index.
        self._whole: set[int] = set()

    def _ask(self) -> None:
        """Says which session this is, and puts what it did up."""
        self.query_one("#asked", Label).update(escape(self._named))
        self.query_one("#about", Label).update(
            f"{_many(len(self._actions), 'action')}, oldest first, read back from its log."
        )
        self._fill()

    def actions(self) -> list[Action]:
        """Searching what it did."""
        return [self._searches()]

    def _fill(self) -> None:
        """Puts each action up, the cursor where it was."""
        listing = self.query_one("#choices", OptionList)
        was = self.under()
        shown = [
            (str(at), label, about)
            for at, (label, about) in enumerate(self._actions)
            if self.fits(label, about)
        ]
        ids = [one for one, _, _ in shown]
        sought = self._sought(ids)
        landing = sought if sought is not None else was
        landing = landing if landing in ids else (ids[0] if ids else "")
        listing.set_options(
            [
                Option(
                    self._said(
                        label,
                        about if int(at) in self._whole else _cut(about),
                        here=at == landing,
                    ),
                    id=f"={at}",
                )
                for at, label, about in shown
            ]
        )
        listing.highlighted = ids.index(landing) if landing else None
        self._drawn = listing.highlighted
        said = "" if self._actions else "its log held nothing it did"
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "whole"), Key("esc", "back"))

    def _said(self, label: str, about: str, *, here: bool) -> str:
        """One action as a row, as a row of `/settings` lays one out but with its lines kept.

        What a session did is text with lines -- a command, its output, a diff -- and a row
        that ran them together would be one nobody could read.

        Args:
          label: What kind of thing it was.
          about: What it carried.
          here: Whether the cursor is on it.

        Returns:
          The row, as markup.
        """
        starts = 1 + max(_LABEL, len(label) + 1)
        room = max(self._width_of(self.query_one("#choices", OptionList)) - starts, 20)
        lines = [
            cut
            for line in about.splitlines() or [""]
            for cut in textwrap.wrap(line, room, break_on_hyphens=False) or [""]
        ]
        return f" [b]{escape(label)}[/]{' ' * (starts - 1 - len(label))}" + (
            f"\n{' ' * starts}".join(
                _shade("$text-muted", line, here=here) for line in lines
            )
        )

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Says the action under the cursor whole, or cut again.

        Args:
          event: What was chosen.
        """
        at = int(str(event.option.id or "=0").removeprefix("="))
        self._whole ^= {at}
        self._fill()


def _action(one: dict[str, Any]) -> tuple[str, str]:
    """One thing a session did, as its row says it: what kind of thing, and what it carried.

    Args:
      one: The action, as a transcript says it.

    Returns:
      Its label -- `turn`, `said`, `model`, or the tool's name -- and the rest, in words.
    """
    args: dict[str, Any] = one.get("args") or {}
    name = str(one.get("name") or "")
    match one.get("category"):
        case "turn":
            return "turn", _text(args.get("prompt")) or name
        case "message":
            return "said", _text(args.get("text")) or name
        case "tool":
            said = [_text(args.get("input")) or name]
            out = args.get("output", args.get("result"))
            if out is not None:
                said.append(f"⎿ {_text(out)}")
            if args.get("error"):
                said.append("✕ failed")
            return name.partition(":")[0] or "tool", "\n".join(said)
        case "llm":
            return "model", _DOT.join(
                part
                for part in (str(args.get("model") or ""), _text(args.get("thinking")))
                if part
            ) or name
        case _:
            return str(one.get("category") or "event"), name


def _text(said: object) -> str:
    """Something an action carried, in words: a string as it is, anything else as JSON."""
    if said is None:
        return ""
    return said if isinstance(said, str) else json.dumps(said, indent=1)


def _cut(said: str) -> str:
    """As much of something as a row says before it is opened."""
    cut = "\n".join(said.splitlines()[:_LINES])[: _ENOUGH - 1]
    return cut if cut == said else f"{cut}…"
