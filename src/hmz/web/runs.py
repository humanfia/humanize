"""The runs of this workspace as their epics wrote them down: the list, one run, its trace.

What a page reads of a run that is over, or of the one going, as far as the epic says it:
which flow, on what, with which agents, how it ended and what it spent, the tree of flows it
called and the sessions it opened -- and, read back out of the logs those sessions kept, what
each of them said and did. The run going now is also followed live (`held`); this is what is
written down of it.
"""

from __future__ import annotations

import contextlib
import datetime
import shutil
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .routing import Download, Refusal, routes

if TYPE_CHECKING:
    from hmz.runtime.epic import Called, Ran

    from .routing import Asked

__all__ = ["ROUTES", "Runs"]

#: How a run that has not ended is said, where it is not the run going now: one killed where
#: it stood, which no record says the end of.
UNFINISHED = "unfinished"

#: How the run going now is said, before its epic says how it ended.
RUNNING = "running"

#: The most rows one page of the list holds.
_PAGE = 200

#: How many runs' traces are kept read, for a page that reads one again.
_TRACES = 4

#: How far apart a run's start may be from the start of the epic it wrote, in seconds, for the
#: two to be one run: the run says when it started, and the epic is opened as it does.
_SAME = 120.0

#: How long a task is said in the list before it is cut: the first line, and as much of it.
_TOLD = 240


class Runs:
    """The runs of one workspace, read off the disk and kept until they change there.

    Args:
      hmz: humanize, for the workspace.
    """

    def __init__(self, hmz: Any) -> None:
        self._epics = hmz.epics
        self._lock = threading.Lock()
        self._read: dict[Path, tuple[tuple[int, int], Ran | None]] = {}
        self._traced: dict[Path, tuple[tuple[int, int], list[dict[str, Any]]]] = {}

    def all(self) -> list[Ran]:
        """Every run of the workspace that reads as one, newest first."""
        held = [one for at in reversed(self._epics.all()) if (one := self.read(at))]
        with self._lock:
            # What the disk no longer has is not kept either.
            for gone in set(self._read) - {one.at for one in held}:
                del self._read[gone]
        return held

    def read(self, epic: Path) -> Ran | None:
        """One run, read again only where its record has changed since it was last read."""
        stamp = _stamp(epic)
        with self._lock:
            kept = self._read.get(epic)
        if kept is not None and kept[0] == stamp:
            return kept[1]
        ran = self._epics.read(epic)
        with self._lock:
            self._read[epic] = (stamp, ran)
        return ran

    def named(self, name: str) -> Ran:
        """One run, by the name of its epic.

        Raises:
          Refusal: If this workspace has no run of that name.
        """
        epic = self._epics.under() / name
        if "/" in name or name.startswith(".") or not epic.is_dir():
            raise Refusal(f"There is no run {name} here.", 404)
        ran = self.read(epic)
        if ran is None:
            raise Refusal(f"There is no run {name} here.", 404)
        return ran

    def traced(self, ran: Ran) -> list[dict[str, Any]]:
        """What each session of a run said and did, read back out of the logs it kept.

        Slow -- every log the run kept is read -- so kept until the run's record changes.

        Returns:
          Each session, with what it did in the order it did it.
        """
        stamp = _stamp(ran.at)
        with self._lock:
            kept = self._traced.get(ran.at)
        if kept is not None and kept[0] == stamp:
            return kept[1]
        from hmz import machine

        # Gathered where nothing keeps it: reading a run must not leave a file in it.
        with tempfile.TemporaryDirectory(dir=machine()) as scratch:
            _, document = self._epics.traced(
                ran.at, output=Path(scratch) / "trace.json"
            )
        said = sessions_of(document)
        # Kept only for a run that has ended, whose logs are done being written, and only the
        # last few: what a page reads it holds itself.
        if ran.ended:
            with self._lock:
                self._traced[ran.at] = (stamp, said)
                while len(self._traced) > _TRACES:
                    del self._traced[next(iter(self._traced))]
        return said

    def bundled(self, ran: Ran) -> Download:
        """One run as one archive, struck of credentials, for the browser to save."""
        from hmz import machine

        scratch = Path(tempfile.mkdtemp(dir=machine()))
        try:
            at, _ = self._epics.bundled(ran.at, output=scratch)
        except Exception:
            shutil.rmtree(scratch, ignore_errors=True)
            raise
        return Download(at, at.name, "application/gzip", gone=True)


def held_by(runs: list[Ran], standing: dict[str, Any] | None) -> Ran | None:
    """Which of the runs written down is the run the host is going with now, if any is.

    The host says what it started and when, and the epic says what it was opened for and when
    it was opened: the newest run of that flow, on that task, opened within a moment of that
    start and not yet ended, is it.

    Args:
      runs: The runs, newest first.
      standing: The `run` the host last said.

    Returns:
      The run, or None where nothing is going.
    """
    if not standing or standing.get("state") not in ("running", "stopping"):
        return None
    started = float(standing.get("at") or 0.0)
    for ran in runs:
        if ran.ended or ran.flow != standing.get("flow"):
            continue
        if ran.task != standing.get("task"):
            continue
        if abs(_epoch(ran.began) - started) <= _SAME:
            return ran
    return None


def row(ran: Ran, *, held: bool) -> dict[str, Any]:
    """One run as the list says it."""
    first = ran.task.strip().splitlines()[0] if ran.task.strip() else ""
    return {
        "name": ran.name,
        "flow": ran.flow,
        "task": first[:_TOLD] + ("…" if len(first) > _TOLD else ""),
        "began": ran.began,
        "ended": ran.ended,
        "how": ran.how or (RUNNING if held else UNFINISHED),
        "agents": [{"role": one.agent, "runs": one.spec} for one in ran.agents],
        "sessions": len(ran.sessions),
        "resumable": ran.resumable,
        "spent": labelled(ran.spent),
        "held": held,
    }


def labelled(spent: dict[str, Any] | None) -> dict[str, Any] | None:
    """What a run spent, with each figure also said as the terminal interface says it."""
    if spent is None:
        return None
    from hmz.coganchor.prices import money
    from hmz.runtime.watching.monitor import lasting, thousands

    cost = spent.get("cost")
    tokens = spent.get("output_tokens")
    seconds = spent.get("seconds")
    return spent | {
        "money": money(float(cost)) if isinstance(cost, (int, float)) else "",
        "tokens": thousands(float(tokens)) if isinstance(tokens, (int, float)) else "",
        "worked": lasting(float(seconds)) if isinstance(seconds, (int, float)) else "",
    }


def detail(ran: Ran, *, held: bool, picks_up: bool) -> dict[str, Any]:
    """One run, whole, as its own page says it."""
    return row(ran, held=held) | {
        "at": str(ran.at),
        "task": ran.task,
        "ref": ran.ref,
        "agents": [
            {
                "role": one.agent,
                "runs": one.spec,
                "backend": one.backend,
                "model": one.model,
                "effort": one.effort,
                "provider": one.provider,
            }
            for one in ran.agents
        ],
        "sessions": [
            {
                "role": one.agent,
                "backend": one.backend,
                "provider": one.provider,
                "ident": one.ident,
                "name": one.name,
                "at": one.at,
                "flow": one.flow,
                "parent": one.parent,
                "harness": one.harness,
            }
            for one in ran.sessions
        ],
        "envs": list(ran.envs),
        "used": list(ran.used),
        "params": ran.params,
        "budget": ran.budget,
        "picked_up": ran.picked_up,
        "profile": ran.profile,
        "picks_up": picks_up,
    }


def calls(called: tuple[Called, ...]) -> list[dict[str, Any]]:
    """The tree of flows a run called, each call with what it called under it."""
    return [
        {
            "flow": one.flow,
            "task": one.task,
            "began": one.began,
            "ended": one.ended,
            "how": one.how,
            "calls": calls(one.calls),
        }
        for one in called
    ]


def sessions_of(document: dict[str, Any]) -> list[dict[str, Any]]:
    """What each session of a trace said and did, in the order it did it.

    Args:
      document: The trace, as `Epics.traced` gathers one.

    Returns:
      Each session that did anything: its key, the agent it was of as the trace names
      agents, and its actions -- turns, model calls, tools, words and the rest -- each with
      when it started, how long it took, and what it carried.
    """
    agents: dict[int, str] = {}
    held: dict[str, dict[str, Any]] = {}
    acted: dict[str, list[dict[str, Any]]] = {}
    events: list[dict[str, Any]] = list(document.get("traceEvents") or ())
    for event in events:
        if event.get("ph") == "M" and event.get("name") == "process_name":
            named: dict[str, Any] = event.get("args") or {}
            agents[int(event.get("pid") or 0)] = str(named.get("name") or "")
    for event in events:
        args: dict[str, Any] = dict(event.get("args") or {})
        if event.get("ph") != "X" or event.get("cat") in ("session", "process"):
            continue
        key = str(args.pop("session", "") or "")
        if not key:
            continue
        if key not in held:
            held[key] = {
                "key": key,
                "agent": agents.get(int(event.get("pid") or 0), ""),
            }
        acted.setdefault(key, []).append(
            {
                "category": str(event.get("cat") or ""),
                "name": str(event.get("name") or ""),
                "at": str(args.pop("at", "") or ""),
                "start": float(event.get("ts") or 0) / 1e6,
                "seconds": float(event.get("dur") or 0) / 1e6,
                "args": args,
            }
        )
    for key, actions in acted.items():
        actions.sort(key=lambda action: float(action["start"]))
        held[key]["actions"] = actions
    return sorted(held.values(), key=lambda one: one["actions"][0]["start"])


def spending(runs: list[Ran], days: int, now: datetime.datetime) -> dict[str, Any]:
    """What the runs of the last few days spent, by day and by flow, as the epics say.

    Args:
      runs: The runs, newest first.
      days: How many days back, counting today.
      now: When today is, in UTC.

    Returns:
      The days, oldest first, each with what its runs spent; the flows, the costliest
      first; how the runs ended; and the whole of it. A run that has not said what it spent
      -- still going, or killed before it could -- is counted as a run and nothing else.
    """
    first = (now - datetime.timedelta(days=days - 1)).date()
    by_day: dict[str, dict[str, Any]] = {
        (first + datetime.timedelta(days=step)).isoformat(): _nothing()
        for step in range(days)
    }
    by_flow: dict[str, dict[str, Any]] = {}
    ended: dict[str, int] = {}
    whole = _nothing()
    for ran in runs:
        when = _when(ran.began)
        if when is None or when.date() < first:
            continue
        for into in (
            by_day.setdefault(when.date().isoformat(), _nothing()),
            by_flow.setdefault(ran.flow, _nothing()),
            whole,
        ):
            _add(into, ran)
        how = ran.how or UNFINISHED
        ended[how] = ended.get(how, 0) + 1
    return {
        "days": [{"day": day} | _said(one) for day, one in sorted(by_day.items())],
        "flows": [
            {"flow": flow} | _said(one)
            for flow, one in sorted(
                by_flow.items(), key=lambda item: (-item[1]["cost"], item[0])
            )
        ],
        "ended": ended,
        "whole": _said(whole),
    }


def _said(one: dict[str, Any]) -> dict[str, Any]:
    """What some runs spent, with each figure also said as the terminal interface says it."""
    return one | {
        key: value
        for key, value in (labelled(one) or {}).items()
        if key in ("money", "tokens", "worked")
    }


def _nothing() -> dict[str, Any]:
    return {"runs": 0, "cost": 0.0, "output_tokens": 0, "seconds": 0.0}


def _add(into: dict[str, Any], ran: Ran) -> None:
    into["runs"] += 1
    spent = ran.spent or {}
    into["cost"] += float(spent.get("cost") or 0.0)
    into["output_tokens"] += int(spent.get("output_tokens") or 0)
    into["seconds"] += float(spent.get("seconds") or 0.0)


def _stamp(epic: Path) -> tuple[int, int]:
    """What says a run's record has changed: its size and when it was last written."""
    from hmz.runtime.epic import JOURNAL

    with contextlib.suppress(OSError):
        said = (epic / JOURNAL).stat()
        return said.st_mtime_ns, said.st_size
    return 0, 0


def _when(stamp: str) -> datetime.datetime | None:
    """A moment an epic wrote down, as a time in UTC, or None for one that is not one."""
    try:
        return datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return None


def _epoch(stamp: str) -> float:
    """A moment an epic wrote down, in seconds since the epoch, or 0 for one that is not one."""
    when = _when(stamp)
    return when.timestamp() if when is not None else 0.0


def _listed(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs.all()
    held = held_by(runs, asked.site.held.standing("run"))
    status = asked.query.get("status", "")
    flow = asked.query.get("flow", "")
    wanted = asked.query.get("q", "").casefold()
    rows = [row(ran, held=ran is held) for ran in runs]
    counts: dict[str, int] = {}
    for one in rows:
        counts[one["how"]] = counts.get(one["how"], 0) + 1
    shown = [
        one
        for one in rows
        if (not status or one["how"] == status)
        and (not flow or one["flow"] == flow)
        and (
            not wanted
            or any(
                wanted in str(one[part]).casefold() for part in ("task", "flow", "name")
            )
        )
    ]
    try:
        offset = max(0, int(asked.query.get("offset", "0")))
        limit = min(_PAGE, max(1, int(asked.query.get("limit", "50"))))
    except ValueError as why:
        raise Refusal("offset and limit are whole numbers.") from why
    return {
        "runs": shown[offset : offset + limit],
        "total": len(shown),
        "offset": offset,
        "limit": limit,
        "counts": counts,
        "flows": sorted({one["flow"] for one in rows}),
    }


def _one(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    ran = runs.named(asked.matched["name"])
    held = held_by(runs.all(), asked.site.held.standing("run"))
    picks_up = asked.site.hmz.epics.picks_up(ran.at)
    return detail(ran, held=ran == held, picks_up=picks_up) | {
        "calls": calls(asked.site.hmz.epics.tree(ran.at))
    }


def _trace(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    return {"sessions": runs.traced(runs.named(asked.matched["name"]))}


def _bundle(asked: Asked) -> Download:
    runs = asked.site.runs
    return runs.bundled(runs.named(asked.matched["name"]))


def _usage(asked: Asked) -> dict[str, Any]:
    try:
        days = min(365, max(1, int(asked.query.get("days", "30"))))
    except ValueError as why:
        raise Refusal("days is a whole number.") from why
    now = datetime.datetime.now(datetime.UTC)
    return {"days_back": days} | spending(asked.site.runs.all(), days, now)


#: What a page reads of the runs written down here.
ROUTES = routes(
    ("GET", "/api/runs", _listed),
    ("GET", "/api/runs/{name}", _one),
    ("GET", "/api/runs/{name}/trace", _trace),
    ("GET", "/api/runs/{name}/bundle", _bundle),
    ("GET", "/api/usage", _usage),
)
