"""Every run on this machine as its epic wrote it down: the list, one run, its trace, its timeline.

What a page reads of a run that is over, or of the one going, as far as the epic says it:
which flow, on what, with which agents, how it ended and what it spent, the tree of flows it
called and the sessions it opened -- and, read back out of the logs those sessions kept, what
each of them said and did -- of every workspace, since the daemon holds every workspace's runs.
The run going in a workspace is also followed live (`held`); this is what is written down of it.
"""

from __future__ import annotations

import contextlib
import datetime
import functools
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .routing import Download, Made, Refusal, Route, routes

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.runtime.epic import Called, Ran

    from .places import Places
    from .routing import Asked

__all__ = ["BUNDLE", "ROUTES", "Runs", "local", "refused"]

#: What an epic's archive is sent as.
BUNDLE = "application/vnd.hmz.epic+gzip"

#: A Windows path: a drive's, or a share's such as `\\wsl$\...`.
_WINDOWS = re.compile(r"[A-Za-z]:[\\/]|\\\\")

#: How a chat is said between its turns, and once it is over however it ended but failing.
DONE = "done"

#: The flow that is a conversation, said a turn at a time rather than as one run.
CHAT = "chat"

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
    """The runs of every workspace, read off the disk and kept until they change there.

    Args:
      places: Every workspace, for Humanize in the one a run was run in.
    """

    def __init__(self, places: Places) -> None:
        self._places = places
        self._lock = threading.Lock()
        self._read: dict[Path, tuple[tuple[int, int], Ran | None]] = {}
        self._traced: dict[Path, tuple[tuple[int, int], list[dict[str, Any]]]] = {}
        # Each an Exomyth timeline as `runtime/tracing` lays one out, which this does not import.
        self._timelines: dict[Path, tuple[tuple[int, int], Any]] = {}

    def all(self, workspace: str = "") -> list[Ran]:
        """Every run that reads as one, newest first: of every workspace, or of one.

        Args:
          workspace: Only the runs of this workspace, by its path, or "" for every one's.
        """
        from hmz.runtime.epic import every

        wanted = _resolved(workspace) if workspace else ""
        held = [
            one
            for at in reversed(every())
            if (one := self.read(at))
            and (not wanted or _resolved(one.workspace) == wanted)
        ]
        if not wanted:
            with self._lock:
                # What the disk no longer has is not kept either.
                for gone in set(self._read) - {one.at for one in held}:
                    del self._read[gone]
        return held

    def workspaces(self) -> list[dict[str, Any]]:
        """Every workspace there is to offer, with how many runs it has and when it last ran."""
        runs = self.all()
        running = {one["workspace"] for one in self._places.running()}
        mine: dict[str, list[Ran]] = {}
        for ran in runs:
            mine.setdefault(_resolved(ran.workspace), []).append(ran)
        return [
            {
                "path": where,
                "name": Path(where).name or where,
                "epics": len(mine.get(where, [])),
                "last": mine[where][0].began if mine.get(where) else "",
                "running": where in running,
                "here": where == str(self._places.here),
                "there": Path(where).is_dir(),
            }
            for where in self._places.known(list(mine))
        ]

    def read(self, epic: Path) -> Ran | None:
        """One run, read again only where its record has changed since it was last read."""
        from hmz.runtime.epic import read

        stamp = _stamp(epic)
        with self._lock:
            kept = self._read.get(epic)
        if kept is not None and kept[0] == stamp:
            return kept[1]
        ran = read(epic)
        with self._lock:
            self._read[epic] = (stamp, ran)
        return ran

    def named(self, name: str) -> Ran:
        """One run, by the name of its epic, of whichever workspace it was run in.

        Raises:
          Refusal: If no workspace has a run of that name.
        """
        from hmz.runtime.epic import every

        if "/" in name or name.startswith(".") or not name:
            raise Refusal(f"There is no epic {name}.", 404)
        for epic in every():
            if epic.name == name and (ran := self.read(epic)) is not None:
                return ran
        raise Refusal(f"There is no epic {name}.", 404)

    def going(self, ran: Ran) -> bool:
        """Whether a run with no end written down is still going, in whatever process holds it.

        The host says which run it holds; a run another process holds -- `hmz exec`, a
        terminal interface holding its runs itself -- says so only by holding its epic.
        """
        from hmz.runtime.epic import going

        return not ran.how and going(ran.at)

    def hmz(self, ran: Ran) -> Any:
        """Humanize, for the workspace a run was run in -- there still or not."""
        return self._places.of(ran.workspace or str(self._places.here), made=True).hmz

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
        said = self.hmz(ran).epics.transcripts(ran.at)
        # Kept only for a run that has ended, whose logs are done being written, and only the
        # last few: what a page reads it holds itself.
        if ran.ended:
            with self._lock:
                self._traced[ran.at] = (stamp, said)
                while len(self._traced) > _TRACES:
                    del self._traced[next(iter(self._traced))]
        return said

    def timeline(self, ran: Ran) -> Any:
        """A run laid out as an Exomyth timeline, read back out of the logs it kept.

        Kept for a run that has ended until its record changes, the last few of them; laid
        out again on every reading of a run still going, whose logs are still being written.
        Either way the last one laid out is kept, which is what a slice's id is an id in.
        """
        stamp = _stamp(ran.at)
        with self._lock:
            kept = self._timelines.get(ran.at)
        if kept is not None and ran.ended and kept[0] == stamp:
            return kept[1]
        laid = self.hmz(ran).epics.timeline(ran.at)
        with self._lock:
            self._timelines.pop(ran.at, None)
            self._timelines[ran.at] = (stamp, laid)
            while len(self._timelines) > _TRACES:
                del self._timelines[next(iter(self._timelines))]
        return laid

    def span(self, ran: Ran, ident: str, layout: str = "") -> dict[str, Any]:
        """One slice of a run's timeline, whole: the last one laid out, or one laid out now.

        Args:
          ran: The run.
          ident: The slice, by its id.
          layout: The `layout` of the timeline the id was read in, or "" for whichever.

        Raises:
          Refusal: If that timeline has no slice of that id, or it is not the one the id was
            read in -- a run still going has been laid out again since, and ids moved.
        """
        with self._lock:
            kept = self._timelines.get(ran.at)
        laid = kept[1] if kept is not None else self.timeline(ran)
        if layout and laid.document["layout"] != layout:
            raise Refusal(
                f"Epic {ran.name} has been laid out again; read it again.", 409
            )
        try:
            return laid.span(int(ident))
        except (KeyError, ValueError) as why:
            raise Refusal(f"Epic {ran.name} has no span {ident}.", 404) from why

    def bundled(self, ran: Ran) -> Download:
        """One run as one archive, struck of credentials, for the browser to save."""
        from hmz import machine

        scratch = Path(tempfile.mkdtemp(dir=machine()))
        try:
            at, _ = self.hmz(ran).epics.bundled(ran.at, output=scratch)
        except Exception:
            shutil.rmtree(scratch, ignore_errors=True)
            raise
        return Download(at, at.name, BUNDLE, gone=True)

    def imported(self, archive: Path) -> dict[str, Any]:
        """One archive read back in as an epic, and whether it can be picked up here.

        Raises:
          Refusal: If it is not an archive Humanize can read, or its epic is here already.
        """
        # Asked of this workspace's Humanize, which reads the epic alone: the one it ran in
        # may be nowhere here.
        epics = self._places.hmz.epics
        try:
            at = epics.imported(archive)
        except ValueError as why:
            raise refused(why) from why
        ran = self.read(at)
        return {
            "name": at.name,
            "workspace": _resolved(ran.workspace) if ran is not None else "",
            "resumable": epics.picks_up(at),
            "why": epics.foreign(at),
        }


#: What an import is refused with for an epic here already: its name, then where it is, which
#: ends in it.
_HERE = re.compile(r"(?P<name>[^/]+) is already here, at .*/(?P=name)")


def refused(why: ValueError) -> Refusal:
    """What a page is told of an archive that could not be imported, as the runtime said it.

    Args:
      why: What importing it raised.

    Returns:
      A conflict naming the epic, for one here already; otherwise a bad request.
    """
    said = str(why)
    # As it was said: it begins with a file's or an epic's name, which is not to be respelled.
    sentence = f"{said}."
    if found := _HERE.fullmatch(said):
        return Refusal(sentence, 409, name=found["name"])
    return Refusal(sentence)


def held_by(
    runs: list[Ran], running: list[dict[str, Any]]
) -> dict[Path, dict[str, str]]:
    """Which of the runs written down are the runs the hosts are going with now.

    A host says which epic it writes, once it writes one. Before then it says what it started
    and when -- or, asked from outside, which flow -- and the epic says what it was opened
    for, where and when: the newest run of that flow, in that workspace, on that task and
    opened within a moment of that start where those are said, and not yet ended, is it.

    Args:
      runs: The runs, newest first.
      running: What each host says runs, with its `workspace` and its `slot`.

    Returns:
      Each run going, by its epic: where it is in its turn where it is a chat, or "", and the
      slot of the host going with it.
    """
    held: dict[Path, dict[str, str]] = {}
    for standing in running:
        workspace, epic = standing["workspace"], standing.get("epic")
        started = float(standing.get("at") or 0.0)
        for ran in runs:
            if ran.ended or _resolved(ran.workspace) != workspace or ran.at in held:
                continue
            if epic and ran.name != epic:
                continue
            if not epic and ran.flow != standing.get("flow"):
                continue
            if not epic and standing.get("task") and ran.task != standing.get("task"):
                continue
            if not epic and started and abs(_epoch(ran.began) - started) > _SAME:
                continue
            held[ran.at] = {
                "turn": str(standing.get("turn") or ""),
                "slot": str(standing.get("slot") or ""),
            }
            break
    return held


def row(
    ran: Ran, *, held: bool, going: bool = False, turn: str = "", slot: str = ""
) -> dict[str, Any]:
    """One run as the list says it.

    Args:
      ran: The run.
      held: Whether it is the run a host is going with, which the page follows live.
      going: Whether it is going at all, held by a host or by any other process.
      turn: Of a chat a host is going with, where it is in its turn, or "" where unknown.
      slot: Of a run a host is going with, which of its workspace's hosts that is: "" for
        the workspace's own, `chat:<hex>` for a chat's.
    """
    from hmz.runtime.epic import RUNNING, UNFINISHED, ending

    first = ran.task.strip().splitlines()[0] if ran.task.strip() else ""
    how = ending(ran, going=held or going)
    if ran.flow == CHAT and how in (RUNNING, UNFINISHED, "stopped"):
        # A chat is going while its agent answers, and done between turns or once over.
        how = RUNNING if how == RUNNING and turn != DONE else DONE
    return {
        "name": ran.name,
        "workspace": _resolved(ran.workspace),
        "flow": ran.flow,
        "task": first[:_TOLD] + ("…" if len(first) > _TOLD else ""),
        "began": ran.began,
        "ended": ran.ended,
        "how": how,
        "agents": [
            {"name": one.name or one.agent, "role": one.agent, "runs": one.spec}
            for one in ran.agents
        ],
        "sessions": len(ran.sessions),
        "resumable": ran.resumable,
        "spent": labelled(ran.spent),
        "held": held,
        "slot": slot,
        "backup": list(ran.backup),
        "backed": ran.backed,
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


def detail(
    ran: Ran,
    *,
    held: bool,
    picks_up: bool,
    foreign: str = "",
    going: bool = False,
    turn: str = "",
    slot: str = "",
) -> dict[str, Any]:
    """One run, whole, as its own page says it.

    Args:
      ran: The run.
      held: Whether it is the run a host is going with.
      going: Whether it is going at all, held by a host or by any other process.
      picks_up: Whether it can be picked up.
      foreign: Why one imported cannot be picked up here, or "".
      turn: Of a chat a host is going with, where it is in its turn, or "" where unknown.
      slot: Of a run a host is going with, which of its workspace's hosts that is.
    """
    return row(ran, held=held, going=going, turn=turn, slot=slot) | {
        "at": str(ran.at),
        "task": ran.task,
        "ref": ran.ref,
        "agents": [
            {
                "name": one.name or one.agent,
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
                "agent": one.agent,
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
        # The sessions it opened before it was last carried on, which are its earlier ones.
        "earlier": sum(1 for one in ran.sessions if one.at < ran.reopened),
        "profile_flow": ran.profile_flow,
        "profile_environment": ran.profile_environment,
        "picks_up": picks_up,
        "foreign": foreign,
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


def _said(one: dict[str, Any]) -> dict[str, Any]:
    """What some runs spent, with each figure also said as the terminal interface says it."""
    return one | {
        key: value
        for key, value in (labelled(one) or {}).items()
        if key in ("money", "tokens", "worked")
    }


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
    from hmz.runtime.epic import found

    runs = asked.site.runs.all(asked.query.get("workspace", ""))
    held = held_by(runs, asked.site.places.running())
    went = [
        (
            ran,
            row(
                ran,
                held=ran.at in held,
                going=asked.site.runs.going(ran),
                **held.get(ran.at, {}),
            ),
        )
        for ran in runs
    ]
    counts: dict[str, int] = {}
    for _, one in went:
        counts[one["how"]] = counts.get(one["how"], 0) + 1
    shown = [
        one
        for ran, one in went
        if found(
            ran,
            one["how"],
            how=asked.query.get("status", ""),
            flow=asked.query.get("flow", ""),
            text=asked.query.get("q", ""),
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
        "flows": sorted({ran.flow for ran in runs}),
    }


def _one(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    ran = runs.named(asked.matched["name"])
    held = held_by(runs.all(ran.workspace), asked.site.places.running())
    hmz = runs.hmz(ran)
    picks_up = hmz.epics.picks_up(ran.at)
    foreign = hmz.epics.foreign(ran.at)
    return detail(
        ran,
        held=ran.at in held,
        picks_up=picks_up,
        foreign=foreign,
        going=runs.going(ran),
        **held.get(ran.at, {}),
    ) | {"calls": calls(hmz.epics.tree(ran.at))}


def _trace(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    return {"sessions": runs.traced(runs.named(asked.matched["name"]))}


def _timeline(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    return runs.timeline(runs.named(asked.matched["name"])).document


def _span(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    return runs.span(
        runs.named(asked.matched["name"]),
        asked.matched["id"],
        asked.query.get("layout", ""),
    )


def _bundle(asked: Asked) -> Download:
    runs = asked.site.runs
    return runs.bundled(runs.named(asked.matched["name"]))


def _backup(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    ran = runs.named(asked.matched["name"])
    to: object = asked.body.get("to")
    if to is not None and not (
        isinstance(to, list)
        and all(isinstance(one, str) for one in cast("list[Any]", to))
    ):
        raise Refusal("to is a list of backup target names.")
    try:
        # Queued, never waited on: how it went is read back off the epic as it is polled.
        queued = runs.hmz(ran).backups.push(ran, cast("list[str] | None", to))
    except ValueError as why:
        raise Refusal(_reason(str(why))) from why
    if not queued:
        raise Refusal("There is no backup target: add one in Settings.", 409)
    return {"queued": list(queued)}


def _stored(asked: Asked) -> dict[str, Any]:
    target = asked.matched["target"]
    hmz = asked.site.hmz
    # Fetched afresh, which can take a while: on this request's own thread, holding up no other.
    held = _fetched(hmz, target, lambda: hmz.backups.listed(target))
    # Here is an epic of that name run in that workspace, as a download would land it.
    here = {(_resolved(one.workspace), one.name) for one in asked.site.runs.all()}
    return {
        "epics": [
            one._asdict() | {"here": (_resolved(one.workspace), one.epic) in here}
            for one in reversed(held)
        ]
    }


def _pull(asked: Asked) -> dict[str, Any]:
    target = asked.matched["target"]
    key = asked.text("key")
    hmz = asked.site.hmz
    at = _fetched(hmz, target, lambda: hmz.backups.pulled(target, key))
    return {"name": at.name}


def _fetched[T](hmz: Any, target: str, fetch: Callable[[], T]) -> T:
    """What a backup target answered, or a refusal saying why not, with nothing signed in."""
    try:
        return fetch()
    except ValueError as why:
        raise Refusal(_reason(hmz.verses.plain(str(why)))) from why
    except OSError as why:
        said = hmz.verses.plain(str(why))
        raise Refusal(_reason(f"{target}: {said}"), 502) from why


def _reason(why: str) -> str:
    """A reason as a refusal says it: a sentence."""
    return f"{why[:1].upper()}{why[1:]}."


def local(said: str) -> Path:
    """A path said on this machine, as hmz reads it: in WSL, a Windows one as WSL names it.

    Args:
      said: The path, as the user or the desktop app said it.

    Returns:
      The path; a Windows one in WSL translated by `wslpath -u`, or as said where it cannot be.
    """
    if os.environ.get("WSL_DISTRO_NAME") and _WINDOWS.match(said):
        with contextlib.suppress(OSError, subprocess.CalledProcessError):
            said = subprocess.run(
                ["wslpath", "-u", said], capture_output=True, text=True, check=True
            ).stdout.rstrip("\n")
    return Path(said)


def _import(asked: Asked) -> Made:
    archive = asked.file
    if archive is None:
        said = local(asked.text("path"))
        if not said.is_absolute():
            raise Refusal("Say path as a whole path on this machine.")
        archive = said
    return Made(asked.site.runs.imported(archive))


def _usage(asked: Asked) -> dict[str, Any]:
    try:
        days = min(365, max(1, int(asked.query.get("days", "30"))))
    except ValueError as why:
        raise Refusal("days is a whole number.") from why
    from hmz.runtime.epic import spending

    said = spending(asked.site.runs.all(asked.query.get("workspace", "")), days)
    return {
        "days_back": days,
        "days": [_said(one) for one in said["days"]],
        "flows": [_said(one) for one in said["flows"]],
        "ended": said["ended"],
        "whole": _said(said["whole"]),
    }


#: What a page reads of the runs written down here.
ROUTES = (
    *routes(
        ("GET", "/api/runs", _listed),
        ("GET", "/api/runs/{name}", _one),
        ("GET", "/api/runs/{name}/trace", _trace),
        ("GET", "/api/runs/{name}/timeline", _timeline),
        ("GET", "/api/runs/{name}/timeline/span/{id}", _span),
        ("GET", "/api/runs/{name}/bundle", _bundle),
        ("POST", "/api/runs/{name}/backup", _backup),
        ("GET", "/api/usage", _usage),
        ("GET", "/api/backups/{target}/epics", _stored),
        ("POST", "/api/backups/{target}/pull", _pull),
    ),
    Route("POST", "/api/runs/import", _import, file=BUNDLE),
)


@functools.cache
def _resolved(workspace: str) -> str:
    """A workspace's path as one is compared with another: whole, with every link followed."""
    return str(Path(workspace).expanduser().resolve()) if workspace else ""
