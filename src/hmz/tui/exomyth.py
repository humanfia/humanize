"""Exomyth: one epic drawn across the terminal as a timeline of its sessions, and as a flame.

What the web draws on a canvas, drawn in cells. Every session is a process of its own, under
the session that started it, and every lane of a process is a row; a span is a bar across its
row, cut to the eighth of a cell at either end with the block characters a terminal has for
that, coloured by what it is in the colours of the interface's theme. Zoomed and panned around
the span under the cursor, searched by name, and read whole in a pane under the chart -- a span,
its process, or a stretch of time picked from one span to another, summed by category. The
other views weigh that stretch, or the window: where it went, each agent, flow or program, its
sessions merged or apart, then its spans as they nest, as nested bars over a list of the totals;
and every name its spans go by, summed, in a table sorted by any column.

Drawn a row at a time, and only the rows on screen: each row is a lane of spans sorted by
start, so what falls inside the window is found by bisection, and spans narrower than a cell
are merged into the cell they share -- fifty thousand spans are a screen of rows, not fifty
thousand bars.
"""

from __future__ import annotations

import bisect
import dataclasses
import json
import math
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Protocol, cast
from weakref import WeakKeyDictionary

from rich.cells import get_character_cell_size, set_cell_size
from rich.markup import escape
from rich.segment import Segment
from rich.style import Style
from textual import on, work
from textual.binding import Binding
from textual.color import Color
from textual.containers import Horizontal, Vertical
from textual.geometry import Size
from textual.screen import ModalScreen
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import ContentSwitcher, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from hmz.runtime.watching.monitor import thousands

from .pick import Crumbed, Key, bad

if TYPE_CHECKING:
    from pathlib import Path

    from rich.color import Color as RichColor
    from textual.app import App, ComposeResult
    from textual.timer import Timer

    from hmz.runtime.epic import Ran

__all__ = [
    "Cell",
    "Exomyth",
    "Flamed",
    "Laid",
    "Lane",
    "Row",
    "Slice",
    "bar",
    "described",
    "flamed",
    "icicle",
    "listed",
    "portrayed",
    "ruler",
    "sliced",
    "spaced",
    "summed",
]

#: The version of the timeline document this draws (`hmz.runtime.tracing.timeline.VERSION`,
#: which the interface does not import: it reads the runs through `hmz.daemon`).
_VERSION = 1


class _Timeline(Protocol):
    """One epic laid out: `hmz.runtime.tracing.timeline.Timeline` is one."""

    @property
    def document(self) -> dict[str, Any]: ...
    def span(self, ident: int) -> dict[str, Any]: ...


#: A cell filled from the left by none to eight eighths of itself.
_EIGHTHS = " ▏▎▍▌▋▊▉█"

#: What a cell holding only spans narrower than itself is drawn as.
_TINY = "▌"

#: How wide the column of process names is, at most.
_GUTTER = 28

#: The dot the interface separates the parts of a line with.
_DOT = " · "

#: How long a live epic is left before it is read again, in seconds.
_LIVE = 3.0

#: How far one press zooms, and how much of the screen one press pans.
_ZOOM = 2.0
_PAN = 0.25

#: The narrowest a cell gets: an eighth of a microsecond, so a microsecond is a whole cell.
_FINEST = 0.125

#: How many cells apart the ruler's ticks are, at least.
_TICKS = 12

#: How many levels of the flame are drawn, at most.
_LEVELS = 6

#: What the flame can be weighed by, and what each is called.
_WEIGHTS = {"time": "time", "in": "tokens in", "out": "tokens out", "count": "count"}

#: The categories, in the order a stretch of time sums them; any other after, by name.
_CATEGORIES = ("flow", "session", "turn", "llm", "tool", "message", "event", "process")

#: How many stacks the list under the flame holds, at most.
_LISTED = 400

#: How many of a span's args its pane says, and how much of each.
_ARGS = 12
_ARG = 200

#: What each category and kind of process is coloured as, by the theme's own name for a colour.
#: A kind is said with a `~` before it: `flow` and `session` are both.
_HUES = {
    "flow": "primary",
    "session": "accent",
    "turn": "secondary",
    "llm": "success",
    "tool": "warning",
    "message": "primary",
    "event": "accent",
    "process": "secondary",
    "~flow": "primary",
    "~session": "secondary",
    "~os": "warning",
}

#: What a span's name is written in, on its bar: the theme's ink for the cursor's fill.
_INK = "block-cursor-foreground"


def spaced(us: float) -> str:
    """A stretch of time, as short as it reads.

    Args:
      us: Microseconds.

    Returns:
      `0s`, `12µs`, `3.5ms`, `1.25s`, `2m05s`, `1h04m`.
    """
    if us < 0:
        return f"-{spaced(-us)}"
    if not us:
        return "0s"
    # Each unit up to what would round to a thousand of it, or sixty: `1s`, not `1000ms`.
    if us < 999.5:  # noqa: PLR2004
        return f"{us:.0f}µs"
    if us < 999.5e3:  # noqa: PLR2004
        return f"{_figures(us / 1e3)}ms"
    if us < 59.95e6:  # noqa: PLR2004
        return f"{_figures(us / 1e6)}s"
    seconds = round(us / 1e6)
    if seconds < 3600:  # noqa: PLR2004
        return f"{seconds // 60}m{seconds % 60:02d}s"
    minutes = round(seconds / 60)
    return f"{minutes // 60}h{minutes % 60:02d}m"


def _figures(value: float) -> str:
    """A number of three figures or so, without the zeros that say nothing."""
    places = 0 if value >= 100 else 1 if value >= 10 else 2  # noqa: PLR2004
    return f"{value:.{places}f}".rstrip("0").rstrip(".") if places else f"{value:.0f}"


class Lane(NamedTuple):
    """One depth of one track: spans that never overlap, sorted by start.

    Attributes:
      process: Whose.
      track: Which track of the document.
      depth: How deep.
      ids: The spans, by id, in order.
      starts: Where each starts, µs.
      ends: Where each ends, µs; sorted too, since none overlaps the next.
    """

    process: int
    track: int
    depth: int
    ids: list[int]
    starts: list[int]
    ends: list[int]


class Row(NamedTuple):
    """One row of the chart: a lane, and what the column of names says beside it.

    Attributes:
      process: Whose.
      lane: The lane, by index, or -1 for a process with nothing in it.
      label: What the column of names says, indented as deep as the process is.
      head: Whether it is its process's first row.
    """

    process: int
    lane: int
    label: str
    head: bool


class Laid:
    """One timeline document, read for drawing: columns by span id, and lanes.

    Attributes:
      strings: The document's string table.
      processes: Its processes.
      tracks: Its tracks.
      layout: Its layout digest.
      live: Whether the epic is still going.
      end: The last moment anything did, µs, and at least 1.
      starts: Every span's start, by id; likewise `durs`, `depths`, `cats`, `names`,
        `models`, `ins` and `outs`.
      lanes: Every lane, a track's in depth order.
    """

    def __init__(self, document: dict[str, Any]) -> None:
        """Reads one document.

        Args:
          document: `Timeline.document`.

        Raises:
          ValueError: If it is of a version this does not know.
        """
        if document.get("version") != _VERSION:
            raise ValueError(
                f"timeline version {document.get('version')} is not {_VERSION}"
            )
        self.strings: list[str] = document["strings"]
        self.processes: list[dict[str, Any]] = document["processes"]
        self.tracks: list[dict[str, Any]] = document["tracks"]
        self.layout = str(document["layout"])
        self.live = bool(document["live"])
        self.end = max(int(document["summary"]["end"]), 1)
        self.starts: list[int] = []
        self.durs: list[int] = []
        self.depths: list[int] = []
        self.cats: list[int] = []
        self.names: list[int] = []
        self.models: list[int] = []
        self.ins: list[int] = []
        self.outs: list[int] = []
        self.lanes: list[Lane] = []
        self._firsts: list[int] = []
        #: Each track's lanes, by depth.
        self._lanes: list[list[int]] = []
        for at, track in enumerate(self.tracks):
            columns: dict[str, list[int]] = track["spans"]
            first = len(self.starts)
            self._firsts.append(first)
            self.starts += columns["start"]
            self.durs += columns["dur"]
            self.depths += columns["depth"]
            self.cats += columns["cat"]
            self.names += columns["name"]
            self.models += columns["model"]
            self.ins += columns["in"]
            self.outs += columns["out"]
            deep = [
                Lane(int(track["process"]), at, depth, [], [], [])
                for depth in range(int(track["depths"]))
            ]
            for index, (start, dur, depth) in enumerate(
                zip(columns["start"], columns["dur"], columns["depth"], strict=True)
            ):
                lane = deep[depth]
                lane.ids.append(first + index)
                lane.starts.append(start)
                lane.ends.append(start + dur)
            self._lanes.append(
                list(range(len(self.lanes), len(self.lanes) + len(deep)))
            )
            self.lanes += deep
        #: Each process's children, in id order.
        self._children: dict[int, list[int]] = {}
        for one in self.processes:
            self._children.setdefault(int(one["parent"]), []).append(int(one["id"]))
        #: Each process, by its key.
        self._keyed = {self.key(at): at for at in range(len(self.processes))}

    def key(self, process: int) -> str:
        """What one process is called in every layout of the epic: its session key."""
        return str(self.processes[process]["key"])

    def place(self, ident: int) -> tuple[str, int, int, int]:
        """Where one span is, in a way that outlasts laying the epic out again.

        Args:
          ident: The span.

        Returns:
          Its process's key, which of that process's tracks, its depth and its start.
        """
        track = self.track_of(ident)
        process = int(self.tracks[track]["process"])
        tracks: list[int] = self.processes[process]["tracks"]
        return (
            self.key(process),
            tracks.index(track),
            self.depths[ident],
            self.starts[ident],
        )

    def placed(self, place: tuple[str, int, int, int]) -> int:
        """The span at a place :meth:`place` said, or -1 where there is none now."""
        key, nth, depth, start = place
        process = self._keyed.get(key)
        tracks: list[int] = [] if process is None else self.processes[process]["tracks"]
        if nth >= len(tracks) or depth >= len(self._lanes[tracks[nth]]):
            return -1
        lane = self.lanes[self._lanes[tracks[nth]][depth]]
        at = bisect.bisect_left(lane.starts, start)
        return lane.ids[at] if at < len(lane.ids) and lane.starts[at] == start else -1

    def track_of(self, ident: int) -> int:
        """The track one span is in."""
        return bisect.bisect_right(self._firsts, ident) - 1

    def lane_of(self, ident: int) -> int:
        """The lane one span is in, by index."""
        return self._lanes[self.track_of(ident)][self.depths[ident]]

    def above(self, lane: int) -> int:
        """The lane over one in its track, or -1 for one at depth 0."""
        held = self.lanes[lane]
        return self._lanes[held.track][held.depth - 1] if held.depth else -1

    def process_of(self, ident: int) -> int:
        """The process one span is in."""
        return int(self.tracks[self.track_of(ident)]["process"])

    def parents(self, process: int) -> list[int]:
        """Every process one hangs from, nearest first."""
        held: list[int] = []
        at = int(self.processes[process]["parent"])
        while 0 <= at < len(self.processes) and at not in held:
            held.append(at)
            at = int(self.processes[at]["parent"])
        return held

    def folds(self, process: int) -> bool:
        """Whether one process has anything to fold away: a second lane, or a process under it."""
        tracks: list[int] = self.processes[process]["tracks"]
        lanes = sum(len(self._lanes[one]) for one in tracks)
        return lanes > 1 or bool(self._children.get(process))

    def rows(self, folded: set[int]) -> list[Row]:
        """The rows of the chart: every process under the one it hangs from, a lane apiece.

        Args:
          folded: The processes folded to a row, which hides what hangs from them too.

        Returns:
          The rows, top first.
        """
        held: list[Row] = []
        roots = [
            at
            for at, one in enumerate(self.processes)
            if not 0 <= int(one["parent"]) < len(self.processes)
        ]
        waiting = [(one, 0) for one in reversed(roots)]
        seen: set[int] = set()
        while waiting:
            process, level = waiting.pop()
            if process in seen:
                continue
            seen.add(process)
            one = self.processes[process]
            tracks: list[int] = one["tracks"]
            lanes = [lane for track in tracks for lane in self._lanes[track]]
            mark = (
                ("▸ " if process in folded else "▾ ") if self.folds(process) else "  "
            )
            name = f"{'  ' * level}{mark}{self.strings[int(one['name'])]}"
            if process in folded:
                held.append(Row(process, lanes[0] if lanes else -1, name, head=True))
                continue
            if not lanes:
                held.append(Row(process, -1, name, head=True))
            for at, lane in enumerate(lanes):
                track = self.lanes[lane].track
                label = name if not at else ""
                if at and not self.lanes[lane].depth and track != tracks[0]:
                    label = (
                        f"{'  ' * level}  {self.strings[self.tracks[track]['name']]}"
                    )
                held.append(Row(process, lane, label, head=not at))
            waiting += [
                (child, level + 1)
                for child in reversed(self._children.get(process, []))
            ]
        return held

    def found(self, sought: str) -> list[int]:
        """Every span whose name holds some words, ignoring case, by start.

        Args:
          sought: The words.

        Returns:
          Their ids.
        """
        sought = sought.casefold()
        named = {at for at, one in enumerate(self.strings) if sought in one.casefold()}
        held = [at for at, name in enumerate(self.names) if name in named]
        return sorted(held, key=self.starts.__getitem__)


class Cell(NamedTuple):
    """One cell of a row as drawn: what it says, and how it is coloured.

    Attributes:
      text: What it says: one cell's worth, or "" behind a character two cells wide.
      hue: What it is coloured as -- a category, or `~` and a kind of process -- or "".
      span: What it is part of -- a span's id, a stack's place in the list -- or -1.
      how: `fill` for a cell the span covers, with its name written on it; `start` for one
        it covers from part way in, whose character is the gap before it; `end` for one it
        covers up to part way, whose character is the part covered; `tiny` for one holding
        spans narrower than itself; "" for none.
    """

    text: str
    hue: str = ""
    span: int = -1
    how: str = ""


_NOTHING = Cell(" ")


def _spread(text: str, width: int) -> list[str]:
    """Some words cut to a width with an ellipsis, a string per cell they take.

    Args:
      text: The words.
      width: How many cells.

    Returns:
      `width` strings: a character two cells wide is followed by "".
    """
    said = f" {text}"
    if sum(map(get_character_cell_size, said)) > width:
        said = f"{set_cell_size(said, width - 1)}…" if width > 2 else ""  # noqa: PLR2004
    held: list[str] = []
    for one in said:
        size = get_character_cell_size(one)
        if not size:
            if held:
                held[-1] += one
            continue
        if len(held) + size > width:
            break
        held += [one, ""] if size > 1 else [one]
    return held + [" "] * (width - len(held))


def bar(
    laid: Laid, lane: Lane, t0: float, scale: float, width: int, chosen: int = -1
) -> list[Cell]:
    """One lane across a window of time, a cell apiece.

    Args:
      laid: The timeline.
      lane: The lane.
      t0: Where the window starts, µs.
      scale: How many µs a cell is.
      width: How many cells.
      chosen: The span under the cursor, which a cell of spans narrower than itself says it
        holds where it does.

    Returns:
      `width` cells.
    """
    cells = [_NOTHING] * width
    starts, ends, ids = lane.starts, lane.ends, lane.ids
    t1 = t0 + width * scale
    # From the first span ending at the window or after: one of no length at its very start
    # is a span too.
    at = bisect.bisect_left(ends, t0)
    while at < len(ids) and starts[at] < t1:
        ident = ids[at]
        hue = laid.strings[laid.cats[ident]]
        x0, x1 = (starts[at] - t0) / scale, (ends[at] - t0) / scale
        first = math.floor(x0)
        if x1 <= first + 1:
            # Inside one cell, with every span after it that ends inside that cell too.
            after = bisect.bisect_right(ends, t0 + (first + 1) * scale, at + 1)
            if 0 <= first < width and not cells[first].how:
                held = chosen if ident <= chosen <= ids[after - 1] else ident
                cells[first] = Cell(_TINY, hue, held, "tiny")
            at = after
            continue
        body = first
        if x0 > first >= 0:
            gap = round((x0 - first) * 8)
            if gap < 8:  # noqa: PLR2004
                body = first + 1
                if not cells[first].how:
                    cells[first] = Cell(
                        _EIGHTHS[gap], hue, ident, "start" if gap else "fill"
                    )
            else:
                body = first + 1
        last = math.floor(x1)
        covered = round((x1 - last) * 8)
        if covered >= 8:  # noqa: PLR2004
            last += 1
        elif covered and last < width:
            cells[last] = Cell(_EIGHTHS[covered], hue, ident, "end")
        body, last = max(body, 0), min(last, width)
        if last > body:
            name = laid.strings[laid.names[ident]]
            cells[body:last] = [
                Cell(one, hue, ident, "fill") for one in _spread(name, last - body)
            ]
            before = cells[body - 1] if body else _NOTHING
            if (
                last - body > 1
                and before.how in ("fill", "end")
                and before.span != ident
            ):
                # Hard against the span before: the space its name starts with is an
                # eighth of a gap instead, so that two bars are not read as one.
                cells[body] = Cell(_EIGHTHS[1], hue, ident, "start")
        at += 1
    return cells


def ruler(t0: float, scale: float, width: int) -> str:
    """The time across a window, a tick every so often with the time it is.

    Args:
      t0: Where the window starts, µs.
      scale: How many µs a cell is.
      width: How many cells.

    Returns:
      `width` characters.
    """
    least = _TICKS * scale
    power = 10 ** math.floor(math.log10(max(least, 1.0)))
    step = next(one * power for one in (1, 2, 5, 10) if one * power >= least)
    held = [" "] * width
    tick = math.ceil(t0 / step) * step
    while (x := round((tick - t0) / scale)) < width:
        said = f"│{spaced(tick)}"
        if x >= 0:
            # The time only where it fits whole: `80m` cut from `80ms` is another time.
            said = said if x + len(said) <= width else said[:1]
            held[x : x + len(said)] = said
        tick += step
    return "".join(held)


def _walked(laid: Laid, t0: float, t1: float) -> list[tuple[int, float, int, int]]:
    """Every span in a stretch of time, each after the one it is under.

    Args:
      laid: The timeline.
      t0: Where the stretch starts, µs.
      t1: Where it ends.

    Returns:
      `(span, how long of it is inside the stretch, the span it is under or -1, its lane)`,
      lane by lane, a track's in depth order.
    """
    held: list[tuple[int, float, int, int]] = []
    for index, lane in enumerate(laid.lanes):
        lo = bisect.bisect_right(lane.ends, t0)
        hi = bisect.bisect_left(lane.starts, t1, lo)
        over = laid.above(index)
        parents = laid.lanes[over] if over >= 0 else None
        for at in range(lo, hi):
            start, end = lane.starts[at], lane.ends[at]
            up = -1
            if parents is not None:
                under = bisect.bisect_right(parents.starts, start) - 1
                if under >= 0 and parents.ends[under] >= start:
                    up = parents.ids[under]
            held.append((lane.ids[at], min(end, t1) - max(start, t0), up, index))
    return held


@dataclasses.dataclass(slots=True)
class Flamed:
    """One stack of the flame: what is under it, and what it weighs.

    Attributes:
      name: What it is.
      hue: What it is coloured as, as :class:`Cell` says.
      weight: What it weighs: its own spans, or those under it where they weigh more -- or
        both, counting spans -- so that a span that says what its calls came to is not
        weighed twice.
      own: What its own spans weigh.
      count: How many spans, its own and those under it.
      children: What is under it, heaviest first.
    """

    name: str
    hue: str
    weight: float = 0.0
    own: float = 0.0
    count: int = 0
    children: list[Flamed] = dataclasses.field(default_factory=list["Flamed"])


def _group(laid: Laid, process: int) -> str:
    """The stack one process is weighed in: its agent and the role it fills, or its name."""
    one = laid.processes[process]
    kind, name = str(one["kind"]), laid.strings[int(one["name"])]
    if kind != "session":
        return name or kind
    agent, role, label = (
        laid.strings[int(one.get(field, 0))] for field in ("agent", "role", "label")
    )
    agent, by = agent or name, role or label
    return f"{agent} ({by})" if by and by not in agent else agent


def flamed(
    laid: Laid, t0: float, t1: float, *, weight: str = "time", apart: bool = False
) -> Flamed:
    """Where a stretch of time went: each agent, flow or program, then its spans as they nest.

    Args:
      laid: The timeline.
      t0: Where the stretch starts, µs.
      t1: Where it ends.
      weight: What a span weighs: `time` inside the stretch, tokens `in` or `out`, or `count`.
      apart: Whether each session is a stack of its own under its agent, rather than merged.

    Returns:
      The whole, whose children are the agents (with the role each fills), flows and
      programs. A session's own span, and a flow's, is its stack; what is under it is by name.
    """
    whole = Flamed("all", "")
    kept: dict[tuple[int, str, str], Flamed] = {}

    def child(up: Flamed, name: str, hue: str) -> Flamed:
        held = kept.get((id(up), name, hue))
        if held is None:
            held = kept[id(up), name, hue] = Flamed(name, hue)
            up.children.append(held)
        return held

    tops: list[Flamed] = []
    for process, one in enumerate(laid.processes):
        kind = str(one["kind"])
        top = child(whole, _group(laid, process), f"~{kind}")
        if apart and kind != "flow":
            name = laid.strings[int(one["name"])]
            said = f"{name} {one.get('pid', 0)}" if kind == "os" else name
            top.children.append(top := Flamed(said, f"~{kind}"))
        tops.append(top)
    tokens = {"in": laid.ins, "out": laid.outs}.get(weight)
    frames: dict[int, Flamed] = {}
    for ident, lasting, up, lane in _walked(laid, t0, t1):
        cat, name = laid.strings[laid.cats[ident]], laid.strings[laid.names[ident]]
        held = laid.lanes[lane]
        under = frames.get(up)
        if under is not None:
            frame = child(under, name, cat)
        elif not held.depth and (
            cat == "session"
            or name == laid.strings[int(laid.processes[held.process]["name"])]
        ):
            frame = tops[held.process]
        else:
            frame = child(tops[held.process], name, cat)
        frames[ident] = frame
        frame.own += (
            lasting if weight == "time" else 1 if tokens is None else tokens[ident]
        )
        frame.count += 1
    walked: list[Flamed] = []
    waiting = [whole]
    while waiting:
        node = waiting.pop()
        walked.append(node)
        waiting += node.children
    # Every stack after the one it is part of: weighed from the leaves up.
    for node in reversed(walked):
        under = sum(one.weight for one in node.children)
        node.weight = node.own + under if weight == "count" else max(node.own, under)
        node.count += sum(one.count for one in node.children)
        node.children = sorted(
            (one for one in node.children if one.weight > 0),
            key=lambda one: -one.weight,
        )
    return whole


def listed(whole: Flamed) -> list[tuple[int, Flamed]]:
    """The stacks under the whole, each under the one it is part of, as the list says them.

    Args:
      whole: What :func:`flamed` gave.

    Returns:
      `(level, stack)`, the first few hundred.
    """
    held: list[tuple[int, Flamed]] = []
    waiting = [(0, one) for one in reversed(whole.children)]
    while waiting and len(held) < _LISTED:
        level, node = waiting.pop()
        held.append((level, node))
        waiting += [(level + 1, one) for one in reversed(node.children)]
    return held


def _deepest(whole: Flamed) -> int:
    """How many levels of the flame are drawn: as deep as its stacks go, a few at most."""
    deep = 0
    waiting = [(0, whole)]
    while waiting:
        level, node = waiting.pop()
        deep = max(deep, level)
        if level < _LEVELS:
            waiting += [(level + 1, one) for one in node.children]
    return deep


def icicle(whole: Flamed, width: int) -> list[list[Cell]]:
    """The flame drawn: a row per level, each stack as wide as its share of the whole.

    Args:
      whole: What :func:`flamed` gave.
      width: How many cells.

    Returns:
      A row of `width` cells per level, as deep as the stacks go and a few at most; a
      cell's `span` is its stack's place in :func:`listed`, or -1 past the end of it.
    """
    rows = [[_NOTHING] * width for _ in range(_deepest(whole))]
    if whole.weight <= 0:
        return rows
    order = {id(node): at for at, (_, node) in enumerate(listed(whole))}
    waiting = [(whole, 0.0, 0)]
    while waiting:
        node, x, level = waiting.pop()
        if level >= len(rows):
            continue
        for child in node.children:
            wide = child.weight / whole.weight * width
            a, b = round(x), min(round(x + wide), width)
            mine = order.get(id(child), -1)
            if b > a:
                said = _spread(child.name, b - a)
                rows[level][a:b] = [
                    Cell(_EIGHTHS[1], child.hue, mine, "start")
                    if not at and b - a > 1
                    else Cell(one, child.hue, mine, "fill")
                    for at, one in enumerate(said)
                ]
            waiting.append((child, x, level + 1))
            x += wide
    return rows


class Slice(NamedTuple):
    """Every span of a stretch of time going by one name, summed.

    Attributes:
      name: Their name.
      cat: Their category.
      spans: How many.
      total: µs of them inside the stretch.
      own: µs of that outside the spans under them, none less than nothing.
      mean: `total` a span.
      p50: The median span's µs.
      p95: The 95th percentile's.
      longest: The longest's.
      ins: Tokens in.
      outs: Tokens out.
    """

    name: str
    cat: str
    spans: int
    total: float
    own: float
    mean: float
    p50: float
    p95: float
    longest: float
    ins: int
    outs: int


def sliced(laid: Laid, t0: float, t1: float) -> list[Slice]:
    """Every name the spans of a stretch of time go by, with what they came to.

    Args:
      laid: The timeline.
      t0: Where the stretch starts, µs.
      t1: Where it ends.

    Returns:
      A slice per name and category, the most time first.
    """
    walked = _walked(laid, t0, t1)
    lasted = {ident: lasting for ident, lasting, _, _ in walked}
    own = dict(lasted)
    named: dict[tuple[int, int], list[int]] = {}
    for ident, lasting, up, _ in walked:
        if up in own:
            own[up] -= lasting
        named.setdefault((laid.names[ident], laid.cats[ident]), []).append(ident)
    held: list[Slice] = []
    for (name, cat), ids in named.items():
        times = sorted(lasted[one] for one in ids)
        total = sum(times)
        held.append(
            Slice(
                laid.strings[name],
                laid.strings[cat],
                len(ids),
                total,
                sum(max(own[one], 0) for one in ids),
                total / len(ids),
                _rank(times, 0.5),
                _rank(times, 0.95),
                times[-1],
                sum(laid.ins[one] for one in ids),
                sum(laid.outs[one] for one in ids),
            )
        )
    return sorted(held, key=lambda one: -one.total)


def _rank(times: list[float], share: float) -> float:
    """The time a share of some sorted times are no longer than."""
    return times[min(max(math.ceil(share * len(times)) - 1, 0), len(times) - 1)]


def described(laid: Laid, said: dict[str, Any]) -> str:
    """What the pane under the chart says of one span.

    Args:
      laid: The timeline.
      said: `Timeline.span` of it.

    Returns:
      Lines of markup.
    """
    ident = int(said["id"])
    process = laid.processes[int(said["process"])]
    track = laid.tracks[int(said["track"])]
    lines = [
        f"[b]{escape(str(said['name']))}[/]",
        _DOT.join(
            (
                escape(str(said["cat"])),
                escape(laid.strings[int(process["name"])]),
                escape(laid.strings[int(track["name"])]),
                f"depth {said['depth']}",
            )
        ),
        _DOT.join(
            (
                f"start {spaced(said['start'])}",
                f"lasted {spaced(said['dur'])}",
                escape(str(said["at"])),
            )
        ),
    ]
    model = laid.strings[laid.models[ident]]
    if model or laid.ins[ident] or laid.outs[ident]:
        lines.append(
            _DOT.join(
                (
                    *((escape(model),) if model else ()),
                    f"{thousands(laid.ins[ident])} in",
                    f"{thousands(laid.outs[ident])} out",
                )
            )
        )
    args: dict[str, Any] = said["args"] or {}
    for key, value in list(args.items())[:_ARGS]:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        text = " ".join(text.split())
        text = text if len(text) <= _ARG else f"{text[: _ARG - 1]}…"
        lines.append(f"[$text-muted]{escape(str(key))}[/] {escape(text)}")
    if len(args) > _ARGS:
        lines.append(f"[$text-muted]+{len(args) - _ARGS} more[/]")
    return "\n".join(lines)


def portrayed(laid: Laid, process: int) -> str:
    """What the pane under the chart says of one process.

    Args:
      laid: The timeline.
      process: The process.

    Returns:
      Lines of markup.
    """
    one = laid.processes[process]
    tracks: list[int] = one["tracks"]
    parent = int(one["parent"])
    start, end = int(one.get("start", 0)), int(one.get("end", 0))
    facts = [
        f"{field} {escape(said)}"
        for field in ("agent", "role", "backend", "model", "label")
        if (said := laid.strings[int(one.get(field, 0))])
    ]
    more = [
        *((f"pid {one['pid']}",) if one.get("pid") else ()),
        *(
            (f"parent {escape(laid.strings[int(laid.processes[parent]['name'])])}",)
            if 0 <= parent < len(laid.processes)
            else ()
        ),
        *(
            (f"record {escape(said)}",)
            if (said := laid.strings[int(one.get("record", 0))])
            else ()
        ),
    ]
    return "\n".join(
        (
            f"[b]{escape(laid.strings[int(one['name'])])}[/]",
            _DOT.join((escape(str(one["kind"])), escape(laid.key(process)))),
            *(_DOT.join(line) for line in (facts, more) if line),
            _DOT.join(
                (
                    f"start {spaced(start)}",
                    f"lasted {spaced(end - start)}",
                    _many(len(tracks), "track"),
                    _many(sum(int(laid.tracks[at]["count"]) for at in tracks), "span"),
                )
            ),
        )
    )


def summed(laid: Laid, t0: float, t1: float) -> str:
    """What the pane under the chart says of a stretch of time: what lies in it, by category.

    Args:
      laid: The timeline.
      t0: Where the stretch starts, µs.
      t1: Where it ends.

    Returns:
      Lines of markup: how long, how many spans and tokens, then each category's spans, time
      inside the stretch, and tokens in and out.
    """
    by: dict[str, list[float]] = {}
    for ident, lasting, _, _ in _walked(laid, t0, t1):
        held = by.setdefault(laid.strings[laid.cats[ident]], [0, 0, 0, 0])
        for at, value in enumerate((1, lasting, laid.ins[ident], laid.outs[ident])):
            held[at] += value
    count, _, ins, outs = (sum(one[at] for one in by.values()) for at in range(4))
    order = [one for one in _CATEGORIES if one in by]
    order += sorted(set(by) - set(order))
    return "\n".join(
        (
            "[b]Range[/]",
            _DOT.join(
                (
                    f"from {spaced(t0)}",
                    f"to {spaced(t1)}",
                    f"lasted {spaced(t1 - t0)}",
                )
            ),
            _DOT.join(
                (
                    _many(int(count), "span"),
                    f"{thousands(ins)} in",
                    f"{thousands(outs)} out",
                )
            ),
            f"[$text-muted]{'category':<10}{'spans':>7}{'time':>9}{'in':>9}{'out':>9}[/]",
            *(
                f"{escape(f'{cat:<10}')}{int(by[cat][0]):>7}{spaced(by[cat][1]):>9}"
                f"{thousands(by[cat][2]):>9}{thousands(by[cat][3]):>9}"
                for cat in order
            ),
        )
    )


def _many(count: int, thing: str) -> str:
    """How many of something, as English says it."""
    return f"{count} {thing}" if count == 1 else f"{count} {thing}s"


#: The styles cells are drawn in, by interface: the theme's colours they were made of, and the
#: styles by what they are.
_STYLES: WeakKeyDictionary[
    App[Any], tuple[dict[str, str], dict[tuple[str, str, bool], Style]]
] = WeakKeyDictionary()


def _style(app: App[Any], hue: str, how: str, *, chosen: bool) -> Style:
    """The style one kind of cell is drawn in, in the interface's theme.

    Args:
      app: The interface.
      hue: What the cell is coloured as.
      how: What part of a span it is.
      chosen: Whether the span is the one under the cursor, drawn in the pair turned round.

    Returns:
      The style.
    """
    variables = app.theme_variables
    made = _STYLES.get(app)
    if made is None or made[0] is not variables:
        made = _STYLES[app] = (variables, {})
    styles = made[1]
    key = (hue, how, chosen)
    held = styles.get(key)
    if held is None:

        def colour(name: str) -> RichColor:
            return Color.parse(variables.get(name) or variables["primary"]).rich_color

        paint, ink = colour(_HUES.get(hue, "primary")), colour(_INK)
        if chosen:
            paint, ink = ink, paint
        held = styles[key] = {
            "fill": Style(color=ink, bgcolor=paint, bold=chosen),
            "start": Style(color=paint, reverse=True),
            "end": Style(color=paint),
            "tiny": Style(color=paint),
        }.get(how, Style())
    return held


def _segments(app: App[Any], cells: list[Cell], chosen: int) -> list[Segment]:
    """Cells as segments, a run of cells drawn alike as one."""
    held: list[Segment] = []
    run: list[str] = []
    was: tuple[str, str, bool] | None = None
    for cell in cells:
        now = (cell.hue, cell.how, cell.span == chosen and cell.span >= 0)
        if now != was and run and was is not None:
            held.append(
                Segment("".join(run), _style(app, was[0], was[1], chosen=was[2]))
            )
            run = []
        was = now
        run.append(cell.text)
    if run and was is not None:
        held.append(Segment("".join(run), _style(app, was[0], was[1], chosen=was[2])))
    return held


class _Chart(ScrollView, can_focus=True, inherit_bindings=False):
    """The rows of the timeline, drawn a line at a time and only where they are on screen."""

    DEFAULT_CSS = """
    _Chart { height: 1fr; overflow-x: hidden; overflow-y: auto; scrollbar-size: 1 1; }
    """

    def __init__(self, *, id: str) -> None:  # noqa: A002 -- Textual's own name for it
        super().__init__(id=id)
        self.laid: Laid | None = None
        self.rows: list[Row] = []
        #: Where the window starts, µs, and how many µs a cell is.
        self.t0 = 0.0
        self.scale = 1.0
        #: The row under the cursor, and the span, or -1 for none.
        self.row = 0
        self.chosen = -1
        #: The moment the cursor is at, which zooming keeps where it is.
        self.at = 0.0
        self._strips: dict[tuple[Any, ...], Strip] = {}
        #: How wide the chart was last drawn.
        self._wide = 80

    @property
    def cells(self) -> int:
        """How many cells across the time is drawn in."""
        return max(self._wide - self.names, 1)

    @property
    def names(self) -> int:
        """How wide the column of names is."""
        return min(_GUTTER, max(self._wide // 3, 8))

    def on_resize(self) -> None:
        """Keeps how wide the chart is: the flame weighs its window while it has no width."""
        if self.size.width:
            self._wide = self.size.width

    def drawn(self, laid: Laid, rows: list[Row]) -> None:
        """Draws another timeline, or the same one laid out again."""
        self.laid, self.rows = laid, rows
        self.row = min(self.row, max(len(rows) - 1, 0))
        self.virtual_size = Size(0, len(rows))
        self.moved()

    def moved(self) -> None:
        """Draws everything again, the cursor kept on screen."""
        if len(self._strips) > 4096:  # noqa: PLR2004 -- a few screens of zooming
            self._strips.clear()
        top = self.scroll_offset.y
        if self.row < top:
            self.scroll_to(y=self.row, animate=False, immediate=True)
        elif self.row >= top + self.size.height > top:
            self.scroll_to(
                y=self.row - self.size.height + 1, animate=False, immediate=True
            )
        self.refresh()

    def forget(self) -> None:
        """Throws away every line drawn, for a timeline that changed under them."""
        self._strips.clear()

    def render_line(self, y: int) -> Strip:
        """One line of the chart: its name, and its lane across the window."""
        at = self.scroll_offset.y + y
        width = self.size.width
        laid = self.laid
        if laid is None or at >= len(self.rows):
            return Strip.blank(width)
        row = self.rows[at]
        chosen = (
            self.chosen
            if self.chosen >= 0 and laid.lane_of(self.chosen) == row.lane
            else -1
        )
        key = (
            at,
            row,
            self.t0,
            self.scale,
            width,
            chosen,
            at == self.row,
            # The theme's colours, which change as a whole when the theme does.
            id(_app(self).theme_variables),
        )
        held = self._strips.get(key)
        if held is None:
            held = self._strips[key] = self._line(
                laid, row, chosen, here=at == self.row
            )
        return held

    def _line(self, laid: Laid, row: Row, chosen: int, *, here: bool) -> Strip:
        """One line, drawn."""
        gutter = self.names
        variables = _app(self).theme_variables
        name = Style(
            color=Color.parse(
                variables[
                    "primary" if here else "foreground" if row.head else "text-muted"
                ]
            ).rich_color,
            bold=here,
        )
        mark = "❯" if here else " "
        segments = [Segment(f"{mark}{set_cell_size(row.label, gutter - 2)} ", name)]
        if row.lane >= 0:
            cells = bar(
                laid, laid.lanes[row.lane], self.t0, self.scale, self.cells, chosen
            )
            segments += _segments(_app(self), cells, chosen)
        return Strip(segments).crop_extend(0, self.size.width, None)


class _Icicle(Widget):
    """The flame, drawn: a line per level."""

    DEFAULT_CSS = "_Icicle { height: 3; }"

    def __init__(self, *, id: str) -> None:  # noqa: A002 -- Textual's own name for it
        super().__init__(id=id)
        self.whole = Flamed("all", "")
        self.chosen = -1
        self._drawn: tuple[Flamed, int, list[list[Cell]]] | None = None

    def render_line(self, y: int) -> Strip:
        """One level of the flame."""
        width = self.size.width
        if (
            self._drawn is None
            or self._drawn[0] is not self.whole
            or self._drawn[1] != width
        ):
            self._drawn = (self.whole, width, icicle(self.whole, width))
        rows = self._drawn[2]
        if y >= len(rows):
            return Strip.blank(width)
        return Strip(_segments(_app(self), rows[y], self.chosen)).crop_extend(
            0, width, None
        )


class Exomyth(ModalScreen[None]):
    """One epic, drawn: a timeline of its sessions, a flame of where its time went, its slices.

    Opened from the sheet of one epic in `/epics`, and left with esc back to it. The timeline
    is read off the screen -- it is every session log the epic opened -- and read again every
    few seconds while the epic is still going.
    """

    DEFAULT_CSS = """
    Exomyth { background: $background; }
    Exomyth #sheet { width: 100%; height: 100%; padding: 1 2 0 2; }
    Exomyth #top { height: 1; width: 100%; }
    Exomyth #trail { width: auto; color: $text-muted; }
    Exomyth #asked { width: 1fr; text-style: bold; color: $primary; }
    Exomyth #tabs { width: auto; }
    Exomyth #about { width: 100%; padding: 0 0 1 0; color: $text-muted; }
    Exomyth #views { height: 1fr; }
    Exomyth #ruler { height: 1; color: $text-muted; }
    Exomyth #detail {
        display: none; height: auto; max-height: 16; padding: 0 1;
        border: round $accent; overflow-y: auto; }
    Exomyth #heading, Exomyth #columns {
        padding: 1 0 0 0; height: 2; color: $text-muted; }
    Exomyth #stacks, Exomyth #sliced {
        height: 1fr; padding: 0; background: $background;
        border: round $accent; scrollbar-size: 1 1; }
    Exomyth #sliced { text-wrap: nowrap; text-overflow: ellipsis; }
    Exomyth #stacks:focus, Exomyth #sliced:focus {
        border: round $primary; background-tint: $background 0%; }
    Exomyth OptionList > .option-list--option-highlighted {
        background: $block-cursor-blurred-background;
        color: $block-cursor-blurred-foreground; text-style: none; }
    Exomyth OptionList:focus > .option-list--option-highlighted {
        background: $block-cursor-background; color: $block-cursor-foreground;
        text-style: bold; }
    Exomyth #seek { display: none; border: round $primary; background: $background; }
    Exomyth #tuning { width: 100%; height: auto; padding: 0 1; }
    Exomyth #keys { width: 100%; height: auto; padding: 1 0 0 0; color: $text-muted; }
    """

    BINDINGS: ClassVar = [
        Binding("escape", "back", "back", show=False, priority=True),
        Binding("tab", "turn(1)", "turn", show=False, priority=True),
        Binding("shift+tab", "turn(-1)", "turn back", show=False, priority=True),
        Binding("up", "rows(-1)", "up", show=False),
        Binding("down", "rows(1)", "down", show=False),
        Binding("pageup", "rows(-10)", "page up", show=False),
        Binding("pagedown", "rows(10)", "page down", show=False),
        Binding("left", "step(-1)", "previous", show=False),
        Binding("right", "step(1)", "next", show=False),
        Binding("a,shift+left", "pan(-1)", "pan", show=False),
        Binding("d,shift+right", "pan(1)", "pan", show=False),
        Binding("w,plus,equals_sign", "zoom(1)", "zoom in", show=False),
        Binding("s,minus", "zoom(-1)", "zoom out", show=False),
        Binding("enter", "open", "details", show=False),
        Binding("p", "process", "process", show=False),
        Binding("v", "range", "range", show=False),
        Binding("f", "fit", "fit", show=False),
        Binding("0", "whole", "whole", show=False),
        Binding("space", "fold", "fold", show=False),
        Binding("slash", "search", "search", show=False),
        Binding("n", "next(1)", "next", show=False),
        Binding("N", "next(-1)", "previous", show=False),
        Binding("r", "reread", "refresh", show=False),
        Binding("t", "weigh", "weight", show=False),
        Binding("m", "merge", "sessions", show=False),
        Binding("o", "sort", "sort", show=False),
        Binding("O", "order", "order", show=False),
    ]

    #: The views, in the order `tab` goes round them.
    _VIEWS: ClassVar = ("timeline", "flame", "slices")

    #: The keys of one view alone, by the view.
    _ONLY: ClassVar = {
        **dict.fromkeys(
            (
                "rows",
                "step",
                "pan",
                "zoom",
                "open",
                "process",
                "range",
                "fit",
                "whole",
                "fold",
                "search",
                "next",
            ),
            "timeline",
        ),
        "weigh": "flame",
        "merge": "flame",
        "sort": "slices",
        "order": "slices",
    }

    #: The columns of the slices, in the order they are drawn and `o` goes round them: what
    #: each is called, the field it says, and how wide it is.
    _COLUMNS: ClassVar = (
        ("count", "spans", 6),
        ("total", "total", 6),
        ("self", "own", 6),
        ("avg", "mean", 6),
        ("p50", "p50", 6),
        ("p95", "p95", 6),
        ("max", "longest", 6),
        ("in", "ins", 6),
        ("out", "outs", 6),
        ("category", "cat", -9),
        ("name", "name", 0),
    )

    def __init__(self, ran: Ran) -> None:
        """Opens on one epic, which is read once the screen is up.

        Args:
          ran: The epic.
        """
        super().__init__()
        self._ran = ran
        self._timeline: _Timeline | None = None
        self._laid: Laid | None = None
        self._folded: set[int] = set()
        #: Which view is up.
        self._view = "timeline"
        #: What the flame weighs, and whether it puts each session apart.
        self._weight = "time"
        self._apart = False
        self._whole = Flamed("all", "")
        #: The slices, and the field they are sorted by, the most first or the least.
        self._slices: list[Slice] = []
        self._by = "total"
        self._down = True
        #: What the pane under the chart says: `span`, `process`, `range`, or "" for nothing.
        self._pane = ""
        #: The stretch of time a range was begun at -- the span under the cursor then -- and
        #: whether it is held there, rather than following the cursor.
        self._marked: tuple[float, float] | None = None
        self._held = False
        #: What the pane last said of a range, and of which: it is summed once.
        self._summed: tuple[tuple[Laid | None, tuple[float, float] | None], str] = (
            (None, None),
            "",
        )
        #: What is worth saying under the view.
        self._said = "reading…"
        #: The spans the last search found, and which of them the cursor is on.
        self._sought = ""
        #: The category of the slice the search was picked as, or "" for words typed.
        self._exact = ""
        self._found: list[int] = []
        self._finding = -1
        self._again: Timer | None = None

    def compose(self) -> ComposeResult:
        """The way here, the view, what it says, and the keys."""
        with Vertical(id="sheet"):
            with Horizontal(id="top"):
                yield Label(id="trail")
                yield Label("Exomyth", id="asked")
                yield Label(id="tabs")
            yield Label(id="about")
            with ContentSwitcher(initial="timeline", id="views"):
                with Vertical(id="timeline"):
                    yield Static(id="ruler")
                    yield _Chart(id="chart")
                    yield Static(id="detail")
                with Vertical(id="flame"):
                    yield _Icicle(id="icicle")
                    yield Label(id="heading")
                    yield OptionList(id="stacks")
                with Vertical(id="slices"):
                    yield Label(id="columns")
                    yield OptionList(id="sliced")
            yield Input(placeholder="span name", id="seek")
            yield Label(id="tuning")
            yield Label(id="keys")

    def on_mount(self) -> None:
        """Says where this is, and reads the epic."""
        stack = _app(self).screen_stack
        steps = [
            one.crumb()
            for one in stack[1 : stack.index(self) if self in stack else len(stack)]
            if isinstance(one, Crumbed)
        ]
        # The epic's own sheet, which is put away while this is up and back once it is not.
        ran = self._ran
        named = escape(f"{ran.began[:16].replace('T', ' ')}{_DOT}{ran.flow}")
        # Or the sheet of its graph, which is named as that sheet is and is still up.
        if steps[-1:] != [named]:
            steps.append(named)
        self.query_one("#trail", Label).update(
            "".join(
                f"{one} \N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK} "
                for one in ["hmz", *steps]
            )
        )
        self._chart.focus()
        self._drawn()
        self._reads()

    @property
    def _chart(self) -> _Chart:
        return self.query_one("#chart", _Chart)

    # -- Reading -------------------------------------------------------------------------------

    @work(group="exomyth", exclusive=True)
    async def _reads(self) -> None:
        """Reads the epic's timeline off the event loop, and draws it."""
        import asyncio

        was = self._laid
        try:
            made, laid = await asyncio.to_thread(_laid_out, self._ran.at)
        except Exception as why:  # noqa: BLE001 -- every log every backend wrote is read
            self._said = bad(escape(str(why) or type(why).__name__))
            self._drawn()
            if was is not None and was.live:
                self._again = self.set_timer(_LIVE, self._reads)
            return
        chart = self._chart
        # What was folded and the span under the cursor, found again where they are now: a
        # live epic is laid out again with every span it grows, which moves every id.
        place = (
            was.place(chart.chosen) if was is not None and chart.chosen >= 0 else None
        )
        folded = (
            {was.key(one) for one in self._folded} if was is not None else set[str]()
        )
        self._folded = {
            at for at in range(len(laid.processes)) if laid.key(at) in folded
        }
        self._timeline, self._laid = made, laid
        self._said = ""
        chart.forget()
        chart.drawn(laid, laid.rows(self._folded))
        self._found = self._finds()
        self._finding = min(self._finding, len(self._found) - 1)
        if was is None:
            self._whole_view()
            if chart.rows and chart.rows[0].lane >= 0:
                lane = laid.lanes[chart.rows[0].lane]
                if lane.ids:
                    self._choose(lane.ids[0])
        else:
            chart.chosen = laid.placed(place) if place is not None else -1
            if chart.chosen >= 0:
                lane = laid.lane_of(chart.chosen)
                chart.row = next(
                    (at for at, one in enumerate(chart.rows) if one.lane == lane),
                    chart.row,
                )
            self._moved()
        self._weighs()
        self._drawn()
        if laid.live:
            self._again = self.set_timer(_LIVE, self._reads)

    def action_reread(self) -> None:
        """Reads the epic again."""
        if self._again is not None:
            self._again.stop()
        self._said = "reading…"
        self._drawn()
        self._reads()

    # -- The view ------------------------------------------------------------------------------

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002 -- the same key, whatever it carries
    ) -> bool | None:
        """Whether one of the keys is live: not while searching, and each in its own view."""
        if action in ("back", "turn", "reread"):
            return action == "back" or not isinstance(self.focused, Input)
        if isinstance(self.focused, Input) or self._laid is None:
            return False
        return self._ONLY.get(action, self._view) == self._view

    def action_back(self) -> None:
        """Comes out of the search, then the range, then the pane, then leaves."""
        seek = self.query_one("#seek", Input)
        timeline = self._view == "timeline"
        if seek.display:
            seek.display = False
            self._chart.focus()
        elif self._marked is not None and timeline:
            self.action_range(drop=True)
            return
        elif self._pane and timeline:
            self._pane = ""
        else:
            self.dismiss(None)
            return
        self._drawn()

    def action_turn(self, by: int) -> None:
        """Turns to the view after this one, or before it.

        Args:
          by: On, or back.
        """
        self._view = self._VIEWS[
            (self._VIEWS.index(self._view) + by) % len(self._VIEWS)
        ]
        self.query_one("#views", ContentSwitcher).current = self._view
        self._weighs()
        focus = {"flame": "#stacks", "slices": "#sliced"}.get(self._view)
        (self._chart if focus is None else self.query_one(focus)).focus()
        self._drawn()

    def _whole_view(self) -> None:
        """The whole epic across the screen."""
        chart = self._chart
        if self._laid is not None:
            chart.t0, chart.scale = 0.0, self._laid.end / chart.cells

    def _span(self) -> float:
        """How many µs the window is."""
        return self._chart.cells * self._chart.scale

    def _clamped(self) -> None:
        """Keeps the window on the epic, a half of it off either end at most."""
        chart = self._chart
        end = self._laid.end if self._laid is not None else 1
        chart.scale = min(max(chart.scale, _FINEST), 4 * end / chart.cells)
        lo = -self._span() / 2
        chart.t0 = min(max(chart.t0, lo), max(lo, end - self._span() / 2))

    def _moved(self) -> None:
        """Draws the view again, after the window or the cursor moved."""
        self._clamped()
        self._chart.moved()
        self._drawn()

    def action_zoom(self, by: int) -> None:
        """Zooms in or out around the moment the cursor is at.

        Args:
          by: In, or out.
        """
        chart = self._chart
        at = chart.at if chart.t0 <= chart.at <= chart.t0 + self._span() else None
        at = chart.t0 + self._span() / 2 if at is None else at
        factor = 1 / _ZOOM if by > 0 else _ZOOM
        chart.t0 = at - (at - chart.t0) * factor
        chart.scale *= factor
        self._moved()

    def action_pan(self, by: int) -> None:
        """Moves the window a quarter of itself back or on.

        Args:
          by: Back, or on.
        """
        self._chart.t0 += by * self._span() * _PAN
        self._moved()

    def action_whole(self) -> None:
        """Shows the whole epic."""
        self._whole_view()
        self._moved()

    def action_fit(self) -> None:
        """Zooms to the range, or to the span under the cursor where there is none."""
        picked = self._range()
        if picked is not None and picked[1] > picked[0]:
            self._fits(*picked)
        elif self._laid is not None and self._chart.chosen >= 0:
            self._fits(*self._here())

    def _fits(self, start: float, end: float) -> None:
        """Zooms to a stretch of time, with a little on either side."""
        chart = self._chart
        dur = max(end - start, 1)
        chart.scale = dur * 1.1 / chart.cells
        chart.t0 = start - dur * 0.05
        self._moved()

    def _choose(self, ident: int, *, follow: bool = False) -> None:
        """Puts the cursor on one span.

        Args:
          ident: The span.
          follow: Whether to bring it on to the screen where it is off it.
        """
        laid, chart = self._laid, self._chart
        if laid is None:
            return
        chart.chosen = ident
        start, end = laid.starts[ident], laid.starts[ident] + laid.durs[ident]
        chart.at = (start + end) / 2
        if follow and (end < chart.t0 or start > chart.t0 + self._span()):
            if end - start > self._span():
                self._fits(start, end)
                return
            chart.t0 = chart.at - self._span() / 2
        self._moved()

    def action_rows(self, by: int) -> None:
        """Moves the cursor up or down the rows, on to the span nearest the moment it is at.

        Args:
          by: How many rows, up for fewer than none.
        """
        laid, chart = self._laid, self._chart
        if laid is None or not chart.rows:
            return
        chart.row = min(max(chart.row + by, 0), len(chart.rows) - 1)
        lane = chart.rows[chart.row].lane
        chart.chosen = -1
        if lane >= 0:
            held = laid.lanes[lane]
            lo = bisect.bisect_left(held.ends, chart.t0)
            hi = bisect.bisect_left(held.starts, chart.t0 + self._span(), lo)
            if hi > lo:
                near = min(
                    max(bisect.bisect_right(held.starts, chart.at) - 1, lo), hi - 1
                )
                best = min(
                    range(near, min(near + 2, hi)),
                    key=lambda at: max(
                        held.starts[at] - chart.at, chart.at - held.ends[at], 0
                    ),
                )
                chart.chosen = held.ids[best]
        self._moved()

    def action_step(self, by: int) -> None:
        """Moves the cursor to the span before or after it in its row.

        Args:
          by: Before, or after.
        """
        laid, chart = self._laid, self._chart
        if laid is None or not chart.rows or chart.rows[chart.row].lane < 0:
            return
        lane = laid.lanes[chart.rows[chart.row].lane]
        if (
            chart.chosen >= 0
            and laid.lane_of(chart.chosen) == chart.rows[chart.row].lane
        ):
            at = bisect.bisect_left(lane.ids, chart.chosen) + by
        else:
            at = bisect.bisect_left(lane.starts, chart.at) - (1 if by < 0 else 0)
        if 0 <= at < len(lane.ids):
            self._choose(lane.ids[at], follow=True)

    def action_fold(self) -> None:
        """Folds the process under the cursor to one row, or opens it out again."""
        laid, chart = self._laid, self._chart
        if laid is None or not chart.rows:
            return
        process = chart.rows[chart.row].process
        if not laid.folds(process):
            return
        self._folded ^= {process}
        chart.drawn(laid, laid.rows(self._folded))
        chart.row = next(
            at
            for at, one in enumerate(chart.rows)
            if one.process == process and one.head
        )
        # On to a span of the row the cursor is left on: the one it was on may be folded away.
        self.action_rows(0)

    # -- The pane ------------------------------------------------------------------------------

    def _shows(self, pane: str) -> None:
        """Opens the pane on one thing, or shuts it where it is open on that already."""
        self._pane = "" if self._pane == pane else pane
        self._drawn()

    def action_open(self) -> None:
        """Opens the pane of the span under the cursor, or shuts it."""
        self._shows("span" if self._chart.chosen >= 0 else "")

    def action_process(self) -> None:
        """Opens the pane of the process of the row under the cursor, or shuts it."""
        self._shows("process" if self._chart.rows else "")

    def _here(self) -> tuple[float, float]:
        """The stretch of the span under the cursor, or the moment it is at."""
        laid, chart = self._laid, self._chart
        if laid is None or chart.chosen < 0:
            return (chart.at, chart.at)
        start = laid.starts[chart.chosen]
        return (start, start + laid.durs[chart.chosen])

    def _range(self) -> tuple[float, float] | None:
        """The range: from where it was begun to the span under the cursor, or where held."""
        if self._marked is None or self._held:
            return self._marked
        here = self._here()
        return (min(self._marked[0], here[0]), max(self._marked[1], here[1]))

    def action_range(self, *, drop: bool = False) -> None:
        """Begins a range at the span under the cursor, holds it, or lets it go.

        Args:
          drop: Whether to let it go, however far it has got.
        """
        if self._marked is None and not drop:
            self._marked, self._held, self._pane = self._here(), False, "range"
        elif not self._held and not drop:
            self._marked, self._held = self._range(), True
        else:
            self._marked = None
            self._pane = "" if self._pane == "range" else self._pane
        self._drawn()

    def _stretch(self) -> tuple[float, float]:
        """What the flame and the slices weigh: the range, or the window where there is none."""
        return self._range() or (self._chart.t0, self._chart.t0 + self._span())

    # -- Searching -----------------------------------------------------------------------------

    def action_search(self) -> None:
        """Opens the search."""
        seek = self.query_one("#seek", Input)
        seek.display = True
        seek.focus()
        self._drawn()

    @on(Input.Submitted, "#seek")
    def _sought_for(self, event: Input.Submitted) -> None:
        """Finds every span named what was typed, and goes to the first after the cursor."""
        event.stop()
        seek = self.query_one("#seek", Input)
        seek.display = False
        self._chart.focus()
        self._sought, self._exact = event.value.strip(), ""
        self._found = self._finds()
        self._goes()

    def _finds(self) -> list[int]:
        """The spans the search finds: named what was typed, or of the slice picked."""
        laid, sought = self._laid, self._sought
        if laid is None or not sought:
            return []
        found = laid.found(sought)
        if not self._exact:
            return found
        return [
            ident
            for ident in found
            if laid.strings[laid.names[ident]] == sought
            and laid.strings[laid.cats[ident]] == self._exact
        ]

    def _goes(self) -> None:
        """Goes to the first span found after the cursor."""
        laid = self._laid
        self._finding = -1
        if self._found and laid is not None:
            at = bisect.bisect_left(
                [laid.starts[one] for one in self._found], self._chart.at
            )
            self._finding = at - 1 if at < len(self._found) else -1
            self.action_next(1)
            return
        self._drawn()

    def action_next(self, by: int) -> None:
        """Goes to the next span the search found, or the one before.

        Args:
          by: On, or back.
        """
        laid = self._laid
        if not self._found or laid is None:
            return
        self._finding = (self._finding + by) % len(self._found)
        ident = self._found[self._finding]
        process = laid.process_of(ident)
        hidden = {process, *laid.parents(process)} & self._folded
        if hidden:
            self._folded -= hidden
        chart = self._chart
        chart.drawn(laid, laid.rows(self._folded))
        lane = laid.lane_of(ident)
        chart.row = next(
            (at for at, one in enumerate(chart.rows) if one.lane == lane), chart.row
        )
        self._choose(ident, follow=True)

    # -- The flame and the slices --------------------------------------------------------------

    def _weighs(self) -> None:
        """Weighs the range or the window, for the view up: the flame, or the slices."""
        laid = self._laid
        if laid is None or self._view == "timeline":
            return
        if self._view == "slices":
            self._slices = sliced(laid, *self._stretch())
            self._sorts()
            return
        self._whole = flamed(
            laid, *self._stretch(), weight=self._weight, apart=self._apart
        )
        icicle = self.query_one("#icicle", _Icicle)
        icicle.whole = self._whole
        icicle.styles.height = _deepest(self._whole)
        self._listed(
            "#stacks",
            [
                f"{self._weighed(node.weight):>9}  {node.count:>7}  "
                f"{'  ' * level}{escape(node.name)}"
                for level, node in listed(self._whole)
            ],
        )
        self._lights()

    def _listed(self, where: str, lines: list[str]) -> None:
        """Puts lines up in a list, its cursor kept where it was."""
        listing = self.query_one(where, OptionList)
        was = listing.highlighted or 0
        listing.set_options(Option(one) for one in lines)
        listing.highlighted = min(was, len(lines) - 1) if lines else None

    def _weighed(self, weight: float) -> str:
        """A weight, as the flame says one."""
        if self._weight == "time":
            return spaced(weight)
        return f"{weight:.0f}" if self._weight == "count" else thousands(weight)

    def action_weigh(self) -> None:
        """Weighs the flame by the next of time, tokens in, tokens out and count."""
        self._weight = _after(list(_WEIGHTS), self._weight)
        self._weighs()
        self._drawn()

    def action_merge(self) -> None:
        """Puts each session apart under its agent, or merges them again."""
        self._apart = not self._apart
        self._weighs()
        self._drawn()

    @on(OptionList.OptionHighlighted, "#stacks")
    def _lights(self) -> None:
        """Lights the stack under the cursor of the list up in the flame."""
        icicle = self.query_one("#icicle", _Icicle)
        icicle.chosen = self.query_one("#stacks", OptionList).highlighted or 0
        icicle.refresh()

    def _sorts(self) -> None:
        """Sorts the slices by their column, and puts them up."""
        by = self._by
        self._slices.sort(key=lambda one: -one.total)
        self._slices.sort(key=lambda one: getattr(one, by), reverse=self._down)
        say = {
            "spans": str,
            "ins": thousands,
            "outs": thousands,
            "cat": str,
            "name": str,
        }
        self._listed(
            "#sliced",
            [
                " ".join(
                    escape(_aligned(say.get(field, spaced)(getattr(one, field)), wide))
                    for _, field, wide in self._COLUMNS
                )
                for one in self._slices[:_LISTED]
            ],
        )

    def action_sort(self) -> None:
        """Sorts the slices by the next column: a number the most first, words from a."""
        self._by = _after([field for _, field, _ in self._COLUMNS], self._by)
        self._down = self._by not in ("cat", "name")
        self._sorts()
        self._drawn()

    def action_order(self) -> None:
        """Sorts the slices the other way round."""
        self._down = not self._down
        self._sorts()
        self._drawn()

    @on(OptionList.OptionSelected, "#sliced")
    def _shown(self, event: OptionList.OptionSelected) -> None:
        """Finds the spans of the slice picked on the timeline, the first after the cursor."""
        event.stop()
        laid = self._laid
        if laid is None or event.option_index >= len(self._slices):
            return
        one = self._slices[event.option_index]
        self._sought, self._exact = one.name, one.cat
        self._found = self._finds()
        self.action_turn(-self._VIEWS.index(self._view))
        self._goes()

    # -- Saying --------------------------------------------------------------------------------

    def _drawn(self) -> None:
        """Says what the view is, what is under the cursor, and the keys."""
        laid, chart = self._laid, self._chart
        view = self._view
        self.query_one("#tabs", Label).update(
            "   ".join(
                f"[b $primary]{one.title()}[/]"
                if one == view
                else f"[$text-muted]{one.title()}[/]"
                for one in self._VIEWS
            )
        )
        about = escape(f"{self._ran.name}")
        if laid is not None:
            sessions = sum(one["kind"] == "session" for one in laid.processes)
            about += _DOT + _DOT.join(
                (
                    _many(sessions, "session"),
                    _many(len(laid.starts), "span"),
                    spaced(laid.end),
                    *(("live",) if laid.live else ()),
                )
            )
        self.query_one("#about", Label).update(about)
        picked = self._range()
        if laid is not None:
            self.query_one("#ruler", Static).update(
                " " * chart.names + _ruled(chart.t0, chart.scale, chart.cells, picked)
            )
        said = self._said
        if not said and self._sought and view == "timeline":
            said = (
                f"{self._finding + 1} of {len(self._found)}{_DOT}{escape(self._sought)}"
                if self._found
                else f"no span named {escape(self._sought)}"
            )
        self.query_one("#heading", Label).update(
            f"{_WEIGHTS[self._weight].split()[-1]:>9}  {'spans':>7}  stack"
        )
        self.query_one("#columns", Label).update(
            escape(
                " ".join(
                    _aligned(self._heading(field), wide)
                    for _, field, wide in self._COLUMNS
                )
            )
        )
        if not said and view != "timeline":
            lo, hi = self._stretch()
            how = (
                (f"weighed by {_WEIGHTS[self._weight]}", f"sessions {self._manner}")
                if view == "flame"
                else (f"sorted by {self._heading(self._by)}",)
            )
            said = _DOT.join(
                (*how, *(("range",) if picked else ()), spaced(lo), spaced(hi))
            )
        self.query_one("#tuning", Label).update(
            said if said.startswith("[") or not said else f"[$text-muted]{said}[/]"
        )
        self._paned()
        self.query_one("#keys", Label).update(
            "   ".join(
                f"[b $accent]{escape(one.key)}[/] {escape(one.does)}"
                for one in self._keys()
            )
        )

    @property
    def _manner(self) -> str:
        """How the flame has sessions: `merged`, or `apart`."""
        return "apart" if self._apart else "merged"

    def _heading(self, field: str) -> str:
        """What a column of the slices is called, with which way it is sorted where it is."""
        name = next(said for said, one, _ in self._COLUMNS if one == field)
        return f"{name}{('↓' if self._down else '↑') if field == self._by else ''}"

    def _paned(self) -> None:
        """Says in the pane under the chart what it is open on, or shuts it."""
        laid, chart, timeline = self._laid, self._chart, self._timeline
        detail = self.query_one("#detail", Static)
        picked = self._range()
        said = ""
        if laid is not None and timeline is not None:
            if self._pane == "range" and picked is not None:
                if self._summed[0] != (laid, picked):
                    self._summed = ((laid, picked), summed(laid, *picked))
                said = self._summed[1]
            elif self._pane == "span" and chart.chosen >= 0:
                said = described(laid, timeline.span(chart.chosen))
            elif self._pane == "process" and chart.rows:
                said = portrayed(laid, chart.rows[chart.row].process)
        self._pane = self._pane if said else ""
        detail.display = bool(said)
        if said:
            detail.update(said)

    def _keys(self) -> list[Key]:
        """The keys of the view as it is."""
        if isinstance(self.focused, Input):
            return [Key("enter", "find"), Key("esc", "clear")]
        after = _after(list(self._VIEWS), self._view)
        if self._view == "flame":
            return [
                Key("↑/↓", "stack"),
                Key("t", _WEIGHTS[_after(list(_WEIGHTS), self._weight)]),
                Key("m", "merge" if self._apart else "apart"),
                Key("r", "refresh"),
                Key("tab", after),
                Key("esc", "back"),
            ]
        if self._view == "slices":
            return [
                Key("↑/↓", "slice"),
                Key("enter", "timeline"),
                Key("o", "sort"),
                Key("O", "reverse"),
                Key("r", "refresh"),
                Key("tab", after),
                Key("esc", "back"),
            ]
        found = [Key("n/N", "next")] if self._found else []
        ranging = (
            "range" if self._marked is None else "hold" if not self._held else "drop"
        )
        return [
            Key("w/s", "zoom"),
            Key("a/d", "pan"),
            Key("←/→", "span"),
            Key("enter", "details"),
            Key("p", "process"),
            Key("v", ranging),
            Key("f", "fit"),
            Key("0", "whole"),
            Key("space", "fold"),
            Key("/", "search"),
            *found,
            Key("tab", after),
            Key("esc", "back"),
        ]

    def on_resize(self) -> None:
        """Draws the ruler again across a screen that changed width."""
        self._drawn()


def _aligned(text: str, wide: int) -> str:
    """Words in a column: to the right of one so wide, to the left of one less than none."""
    return f"{text:>{wide}}" if wide > 0 else f"{text:<{-wide}}"


def _after(ones: list[str], one: str) -> str:
    """The one after one, round the end."""
    return ones[(ones.index(one) + 1) % len(ones)]


def _ruled(
    t0: float, scale: float, width: int, picked: tuple[float, float] | None
) -> str:
    """The ruler as markup, the range picked turned round on it where it is on screen."""
    said = ruler(t0, scale, width)
    if picked is None:
        return escape(said)
    a = min(max(math.floor((picked[0] - t0) / scale), 0), width)
    b = min(max(math.ceil((picked[1] - t0) / scale), a + 1), width)
    if a >= width or (picked[1] - t0) / scale < 0:
        return escape(said)
    return f"{escape(said[:a])}[reverse]{escape(said[a:b])}[/]{escape(said[b:])}"


def _app(widget: Widget) -> App[Any]:
    """The interface a widget is drawn in."""
    return cast("App[Any]", widget.app)  # pyright: ignore[reportUnknownMemberType]


def _laid_out(epic: Path) -> tuple[_Timeline, Laid]:
    """One epic's timeline, read off its session logs, and read for drawing."""
    from hmz.daemon import Hmz

    made = Hmz().epics.timeline(epic)
    return made, Laid(made.document)
