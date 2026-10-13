"""One epic laid out as an Exomyth timeline: compact, columnar, and drawn by any client.

A Chrome trace is one event per slice, each carrying its whole payload, which is what a
general-purpose viewer wants and what a viewer of fifty thousand slices does not: it is read
whole before anything is drawn. This is the same epic laid out for drawing instead. Every
string is said once, in one table, and referred to by its place in it; every track is a set
of columns of whole microseconds since the epic began, sorted by start, so a viewer can
binary-search what is on screen; and what each slice carried -- the prompt, the tool's input,
what it gave back -- is left out, to be asked for by the slice's id when somebody selects it.

Where a Chrome trace makes one process of an agent and everything it drove, this makes one
of each session, under the session that started it: the flows the epic called are a process
of their own, at the top, with the flow's own Python under them where that was profiled --
a lane of the frames it was in, each nested in the one that called it -- and a profiled
epic's programs are one apiece beside them.
"""

from __future__ import annotations

import array
import bisect
import dataclasses
import datetime
import hashlib
import math
from typing import TYPE_CHECKING, Any, Protocol, cast

from .packing import stacked
from .session import stamp, summarize

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .profile import Process, Sample
    from .session import Session

__all__ = ["VERSION", "Call", "Epic", "Opened", "Timeline", "build"]

#: Which shape of document this is: bumped whenever a client of an older one would misread it.
VERSION = 1

#: What a slice's tokens in are called, across every backend whose reader keeps its `usage`.
_IN = (
    "input_tokens",
    "input",
    "prompt_tokens",
    "promptTokens",
    "promptTokenCount",
    "inputTokens",
    "inputOther",
)

#: And its tokens out.
_OUT = (
    "output_tokens",
    "output",
    "completion_tokens",
    "outputTokens",
    "candidatesTokenCount",
)

#: Which of two slices that start and end together holds the other: a session its turn, and
#: a turn whatever it did -- which a backend that times all three alike would leave to chance.
_OUTER = {"session": 0, "turn": 1}


class Opened(Protocol):
    """One session an epic says it opened: `hmz.runtime.epic.Session` is one."""

    @property
    def ident(self) -> str: ...
    @property
    def agent(self) -> str: ...
    @property
    def record(self) -> str: ...


class Drove(Protocol):
    """One agent role of an epic, and the agent that filled it: `hmz.runtime.epic.Drove` is one."""

    @property
    def agent(self) -> str: ...
    @property
    def name(self) -> str: ...


class Call(Protocol):
    """One flow an epic called, and what it called in turn: `hmz.runtime.epic.Called` is one."""

    @property
    def flow(self) -> str: ...
    @property
    def task(self) -> str: ...
    @property
    def record(self) -> str: ...
    @property
    def began(self) -> str: ...
    @property
    def ended(self) -> str: ...
    @property
    def how(self) -> str: ...
    @property
    def calls(self) -> Sequence[Call]: ...


class Epic(Protocol):
    """One epic as it reads back: `hmz.runtime.epic.Ran` is one."""

    @property
    def name(self) -> str: ...
    @property
    def flow(self) -> str: ...
    @property
    def task(self) -> str: ...
    @property
    def began(self) -> str: ...
    @property
    def ended(self) -> str: ...
    @property
    def how(self) -> str: ...
    @property
    def sessions(self) -> Sequence[Opened]: ...
    @property
    def agents(self) -> Sequence[Drove]: ...


@dataclasses.dataclass(frozen=True, slots=True)
class Timeline:
    """One epic, laid out.

    Attributes:
      document: What a viewer draws, ready to be serialized as JSON.
      details: What each slice carried, by its id, which the document leaves out.
    """

    document: dict[str, Any]
    details: Sequence[dict[str, Any]]
    _firsts: list[int] = dataclasses.field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        firsts = [int(one["first"]) for one in self.document["tracks"]]
        object.__setattr__(self, "_firsts", firsts)

    def span(self, ident: int) -> dict[str, Any]:
        """One slice, whole: where it is, what it is and everything it carried.

        Args:
          ident: The slice, by its id in the document.

        Returns:
          Its `id`, `process`, `track`, `start`, `dur` and `depth`, its `cat` and `name` as
          text, `at` as an ISO 8601 UTC moment, and its `args`.

        Raises:
          KeyError: If the document has no slice of that id.
        """
        if not 0 <= ident < len(self.details):
            raise KeyError(ident)
        tracks: list[dict[str, Any]] = self.document["tracks"]
        index = bisect.bisect_right(self._firsts, ident) - 1
        track = tracks[index]
        at = ident - int(track["first"])
        columns: dict[str, list[int]] = track["spans"]
        strings: list[str] = self.document["strings"]
        start = columns["start"][at]
        return {
            "id": ident,
            "process": track["process"],
            "track": index,
            "start": start,
            "dur": columns["dur"][at],
            "depth": columns["depth"][at],
            "cat": strings[columns["cat"][at]],
            "name": strings[columns["name"][at]],
            "at": stamp(self.document["origin"] + start / 1e6),
            "args": self.details[ident],
        }


@dataclasses.dataclass(slots=True)
class _Slice:
    """One slice, before it is laid out."""

    start: float
    end: float
    cat: str
    name: str
    args: dict[str, Any]
    spawn: str | None = None
    record: str | None = None


@dataclasses.dataclass(slots=True)
class _Process:
    """One process, before it is laid out."""

    kind: str
    name: str
    slices: list[_Slice]
    track: str
    fields: dict[str, str] = dataclasses.field(default_factory=dict[str, str])
    key: str = ""
    parent: str = ""
    pid: int = 0


class _Strings:
    """The table every string of a document is said once in."""

    def __init__(self) -> None:
        self.held: list[str] = [""]
        self._at: dict[str, int] = {"": 0}

    def __call__(self, text: str) -> int:
        at = self._at.get(text)
        if at is None:
            at = self._at[text] = len(self.held)
            self.held.append(text)
        return at


def build(
    sessions: Iterable[Session],
    *,
    ran: Epic | None = None,
    calls: Sequence[Call] = (),
    profiled: Iterable[Process] = (),
    sampled: Iterable[Sample] = (),
) -> Timeline:
    """Lays one epic out as an Exomyth timeline.

    Args:
      sessions: The sessions it opened, as the collector read them.
      ran: The epic, as it reads back, or None for sessions that were no epic's.
      calls: The tree of flows it called.
      profiled: The programs it started, where it was profiled.
      sampled: Where its flow's own Python was, where that was profiled.

    Returns:
      The document and what each of its slices carried.
    """
    opened = {one.ident: one for one in (ran.sessions if ran is not None else ())}
    # What role each agent filled, by its name: a session is written down under its agent's
    # name, the role being only the parameter it was taken as -- and an epic written before
    # an agent had a name of its own wrote its role down as its name.
    roles = {
        one.name or one.agent: one.agent
        for one in (ran.agents if ran is not None else ())
    }
    held = [
        _session(one, opened, roles)
        for one in sorted(
            (one for one in sessions if one.actions),
            key=lambda one: (min(action.start for action in one.actions), one.key),
        )
    ]
    held += [
        _program(one) for one in sorted(profiled, key=lambda one: (one.began, one.pid))
    ]
    if (python := _python(ran, sampled)).slices:
        held.insert(0, python)
    if ran is not None:
        held.insert(0, _flow(ran, calls))
    moments = [
        edge
        for one in held
        for item in one.slices
        for edge in (item.start, item.end)
        if math.isfinite(edge)
    ]
    origin = min(moments, default=0.0)
    last = max(moments, default=0.0)
    # A call that never returned -- an epic still going, or one killed under it -- ran
    # until the last thing that happened in it.
    for one in held[:1] if ran is not None else ():
        for item in one.slices:
            if not math.isfinite(item.end):
                item.end = max(last, item.start)
    return _laid_out(held, ran, origin, last)


def _laid_out(
    held: list[_Process], ran: Epic | None, origin: float, last: float
) -> Timeline:
    """Every process, its tracks and their columns, its spawns and what it all came to."""
    strings = _Strings()
    processes: list[dict[str, Any]] = []
    tracks: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    owner: dict[str, int] = {}
    pids: dict[int, list[tuple[float, int]]] = {}
    spawning: list[tuple[int, str]] = []
    records: dict[str, int] = {}
    totals: dict[str, dict[str, int]] = {}

    def micro(at: float) -> int:
        return round((at - origin) * 1e6)

    for ident, process in enumerate(held):
        owner.setdefault(process.key, ident)
        if process.kind == "os":
            pids.setdefault(process.pid, []).append((process.slices[0].start, ident))
        ordered = sorted(
            process.slices,
            key=lambda item: (item.start, -item.end, _OUTER.get(item.cat, len(_OUTER))),
        )
        placed = stacked((item.start, item.end) for item in ordered)
        lanes: list[list[tuple[_Slice, int]]] = []
        for item, (lane, depth) in zip(ordered, placed, strict=True):
            while len(lanes) <= lane:
                lanes.append([])
            lanes[lane].append((item, depth))
        own: list[int] = []
        for lane, members in enumerate(lanes):
            columns: dict[str, list[int]] = {
                name: []
                for name in (
                    "start",
                    "dur",
                    "depth",
                    "cat",
                    "name",
                    "model",
                    "in",
                    "out",
                )
            }
            first = len(details)
            for item, depth in members:
                span = len(details)
                start, end = micro(item.start), micro(item.end)
                model, tokens_in, tokens_out = _hints(item.args)
                columns["start"].append(start)
                columns["dur"].append(max(end - start, 0))
                columns["depth"].append(depth)
                columns["cat"].append(strings(item.cat))
                columns["name"].append(strings(item.name))
                columns["model"].append(strings(model))
                columns["in"].append(tokens_in)
                columns["out"].append(tokens_out)
                details.append(item.args)
                total = totals.setdefault(
                    item.cat, {"count": 0, "time": 0, "in": 0, "out": 0}
                )
                total["count"] += 1
                total["time"] += max(end - start, 0)
                total["in"] += tokens_in
                total["out"] += tokens_out
                if item.spawn:
                    spawning.append((span, item.spawn))
                if item.record is not None:
                    records.setdefault(item.record, span)
            own.append(len(tracks))
            tracks.append(
                {
                    "process": ident,
                    "name": strings(
                        process.track if lane == 0 else f"{process.track} ~{lane + 1}"
                    ),
                    "first": first,
                    "count": len(members),
                    "depths": max(depth for _, depth in members) + 1,
                    "spans": columns,
                }
            )
        starts = [item.start for item in process.slices]
        ends = [item.end for item in process.slices]
        processes.append(
            {
                "id": ident,
                "kind": process.kind,
                "name": strings(process.name),
                "key": strings(process.key),
                "pid": process.pid,
                "start": micro(min(starts)) if starts else 0,
                "end": micro(max(ends)) if ends else 0,
                "tracks": own,
            }
            | {field: strings(value) for field, value in process.fields.items()}
        )

    edges = {(span, owner[key]) for span, key in spawning if key in owner}
    for ident, process in enumerate(held):
        processes[ident]["parent"] = _parent(ident, process, owner, pids, ran)
        if process.kind != "session" or process.parent in owner:
            continue
        # A session the epic opened itself starts from the call that opened it, or from the
        # epic -- whose own span is the one that names no record.
        opened = records.get(process.fields["record"], records.get(""))
        if opened is not None:
            edges.add((opened, ident))
    spawns: dict[str, list[int]] = {"span": [], "process": []}
    for span, process_id in sorted(edges):
        spawns["span"].append(span)
        spawns["process"].append(process_id)

    document: dict[str, Any] = {
        "version": VERSION,
        "layout": _layout(tracks),
        "epic": ran.name if ran is not None else "",
        "origin": origin,
        "live": ran is not None and not ran.ended,
        "strings": strings.held,
        "processes": processes,
        "tracks": tracks,
        "spawns": spawns,
        "summary": {
            "start": 0,
            "end": micro(last),
            "processes": len(processes),
            "tracks": len(tracks),
            "spans": len(details),
            "categories": totals,
        },
    }
    return Timeline(document, details)


def _parent(
    ident: int,
    process: _Process,
    owner: dict[str, int],
    pids: dict[int, list[tuple[float, int]]],
    ran: Epic | None,
) -> int:
    """Which process one hangs from, or -1.

    A sub-agent from the session that started it, and one whose starter did nothing it could
    be drawn by from the epic, like every session the epic opened; a program from the latest
    program to hold its parent's pid by the time it started, a pid being given out again.
    """
    if process.kind == "os":
        held = pids.get(int(process.parent or 0), [])
        before = [at for began, at in held if began <= process.slices[0].start]
        parent = before[-1] if before else -1
    elif process.parent in owner:
        parent = owner[process.parent]
    else:
        parent = 0 if ran is not None and process.kind == "session" else -1
    return parent if parent != ident else -1


def _layout(tracks: list[dict[str, Any]]) -> str:
    """What says two documents number their spans alike: where each span is, and what."""
    digest = hashlib.blake2b(digest_size=8)
    for track in tracks:
        columns: dict[str, list[int]] = track["spans"]
        digest.update(array.array("q", (track["process"], track["count"])).tobytes())
        digest.update(array.array("q", columns["start"]).tobytes())
        digest.update(array.array("q", columns["cat"]).tobytes())
    return digest.hexdigest()


def _flow(ran: Epic, calls: Sequence[Call]) -> _Process:
    """The epic and every flow it called, as one process: each call inside its caller.

    A flow that has not returned is said to end at infinity, until the end of the epic is
    known.
    """
    slices: list[_Slice] = []
    pending: list[tuple[str, str, str, str, str, str]] = [
        (ran.flow, ran.task, ran.how, "", ran.began, ran.ended)
    ]
    walked = list(calls)
    while walked:
        one = walked.pop()
        pending.append((one.flow, one.task, one.how, one.record, one.began, one.ended))
        walked += one.calls
    for flow, task, how, record, began, ended in pending:
        start = _epoch(began)
        if start is None:
            continue
        slices.append(
            _Slice(
                start,
                _epoch(ended) or math.inf,
                "flow",
                flow,
                {"flow": flow, "task": task, "how": how, "record": record},
                record=record,
            )
        )
    return _Process(
        "flow",
        ran.flow,
        slices,
        "flows",
        _fields(label=ran.how),
        key=f"epic:{ran.name}",
    )


def _python(ran: Epic | None, sampled: Iterable[Sample]) -> _Process:
    """The flow's own Python as one process, under the epic: a slice per frame it was in."""
    from .profile import frames

    key = f"epic:{ran.name}" if ran is not None else ""
    return _Process(
        "flow",
        "python",
        [
            _Slice(one.began, one.ended, "sample", one.name, {"frame": one.name})
            for one in frames(sampled)
        ],
        "flow",
        _fields(label="python"),
        key=f"python:{key}",
        parent=key,
    )


def _session(
    one: Session, sessions: dict[str, Opened], roles: dict[str, str]
) -> _Process:
    """One session as a process: a banner over everything it did, and each thing inside it."""
    start = min(action.start for action in one.actions)
    end = max(action.end for action in one.actions)
    name = summarize(f"{one.label} · {one.title}", 120)
    banner = _Slice(
        start,
        end,
        "session",
        name,
        {**one.args, "agent": one.agent, "parent": one.parent, "session": one.key},
    )
    slices = [banner]
    slices += [
        _Slice(
            action.start,
            action.end,
            action.category,
            action.name,
            {**action.args, "session": one.key},
            action.spawn,
        )
        for action in one.actions
    ]
    opened = sessions.get(one.ident) if one.parent is None else None
    model = one.args.get("model")
    return _Process(
        "session",
        name,
        slices,
        one.label or "main",
        _fields(
            agent=one.agent,
            role=roles.get(opened.agent, "") if opened is not None else "",
            backend=one.backend,
            model=model if isinstance(model, str) else "",
            label=one.label,
            record=opened.record if opened is not None else "",
        ),
        key=one.key,
        parent=one.parent or "",
    )


def _program(one: Process) -> _Process:
    """One program a profiled epic ran, as a process with a lane per thread."""
    from .profile import Thread

    threads = one.threads or (Thread(one.pid, one.began, one.ended, 0.0),)
    slices = [
        _Slice(
            thread.began,
            thread.ended,
            "process",
            one.label if thread.tid == one.pid else f"thread {thread.tid}",
            {
                "pid": one.pid,
                "ppid": one.ppid,
                "tid": thread.tid,
                "argv": " ".join(one.argv),
                "cpu": round(thread.cpu, 3),
            },
        )
        for thread in threads
    ]
    return _Process(
        "os",
        one.label,
        slices,
        "threads",
        _fields(label=one.name),
        key=f"pid:{one.pid}:{one.began}",
        parent=str(one.ppid),
        pid=one.pid,
    )


def _fields(
    *,
    agent: str = "",
    role: str = "",
    backend: str = "",
    model: str = "",
    label: str = "",
    record: str = "",
) -> dict[str, str]:
    """What every process says of itself, as text, whichever kind it is."""
    return {
        "agent": agent,
        "role": role,
        "backend": backend,
        "model": model,
        "label": label,
        "record": record,
    }


def _hints(args: dict[str, Any]) -> tuple[str, int, int]:
    """What a slice says that a flame graph weighs it by: its model, and its tokens in and out."""
    model = args.get("model")
    usage = args.get("usage")
    tokens = cast("dict[str, Any]", usage) if isinstance(usage, dict) else {}
    return (
        model if isinstance(model, str) else "",
        _count(tokens, _IN),
        _count(tokens, _OUT),
    )


def _count(tokens: dict[str, Any], names: tuple[str, ...]) -> int:
    """The first of these counts a usage holds, or nought."""
    for name in names:
        value = tokens.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    return 0


def _epoch(stamp: str) -> float | None:
    """A moment an epic wrote down, in epoch seconds, or None for one that is not one."""
    try:
        return datetime.datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return None
