"""Every epic on this machine as it wrote itself down: `runs.*` (Section 4.16 of daemon.md).

What a client reads of an epic that is over, or of the one going, as far as the epic says it:
which flow, on what, with which agents, how it ended and what it spent, the tree of flows it
called and the sessions it opened -- and, read back out of the logs those sessions kept, what
each of them said and did -- of every workspace, since the daemon holds every workspace's
epics. An epic is also carried away whole as an archive (`runs.bundle`, read through
`files.read`) and read back in from one (`runs.import`).

The epics read and laid out are kept in one :class:`Runs` until they change on disk, which is
also what remembers the timeline a span's id is an id in.
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

from hmz.daemon import reach
from hmz.daemon.api import files, workspaces
from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Mapping, Sequence

    from hmz.rpc import Call, Handler
    from hmz.runtime.epic import Called, Ran

__all__ = [
    "BUNDLE",
    "METHODS",
    "RUNS",
    "Runs",
    "backup",
    "calls",
    "detail",
    "held_by",
    "kind",
    "labelled",
    "listed",
    "local",
    "one",
    "reason",
    "refused",
    "resolved",
    "row",
    "running",
    "usage",
]

#: What an epic's archive is sent as.
BUNDLE = "application/vnd.hmz.epic+gzip"

#: A Windows path: a drive's, or a share's such as `\\wsl$\...`.
_WINDOWS = re.compile(r"[A-Za-z]:[\\/]|\\\\")

#: Where a chat is in its turn between its turns, as its host says it.
DONE = "done"

#: The most rows one page of the list holds.
_PAGE = 200

#: The fewest and the most days `runs.usage` sums.
_DAYS = (1, 365)

#: How many runs' traces are kept read, for a client that reads one again.
_TRACES = 4

#: How far apart a run's start may be from the start of the epic it wrote, in seconds, for the
#: two to be one run: the run says when it started, and the epic is opened as it does.
_SAME = 120.0

#: How long a task is said in the list before it is cut: the first line, and as much of it.
_TOLD = 240

#: The longest file name, in bytes, an archive handed in may have.
_NAME = 255


class Runs:
    """The runs of every workspace, read off the disk and kept until they change there.

    Args:
      hmz: Humanize for a workspace, by its path -- there still or not -- or "" for the one
        an epic that says no workspace, or an archive read back in, is read by.
    """

    def __init__(self, hmz: Callable[[str], Any]) -> None:
        self._hmz = hmz
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

        wanted = resolved(workspace) if workspace else ""
        held = [
            one
            for at in reversed(every())
            if (one := self.read(at))
            and (not wanted or resolved(one.workspace) == wanted)
        ]
        if not wanted:
            with self._lock:
                # What the disk no longer has is not kept either.
                for gone in set(self._read) - {one.at for one in held}:
                    del self._read[gone]
        return held

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
          RpcError: 404 if no workspace has a run of that name.
        """
        from hmz.runtime.epic import every

        if "/" in name or name.startswith(".") or not name:
            raise RpcError(Code.NOT_FOUND, f"There is no epic {name}.")
        for epic in every():
            if epic.name == name and (ran := self.read(epic)) is not None:
                return ran
        raise RpcError(Code.NOT_FOUND, f"There is no epic {name}.")

    def going(self, ran: Ran) -> bool:
        """Whether a run with no end written down is still going, in whatever process holds it.

        The host says which run it holds; a run another process holds -- `hmz exec`, a
        terminal interface holding its runs itself -- says so only by holding its epic.
        """
        from hmz.runtime.epic import going

        return not ran.how and going(ran.at)

    def hmz(self, ran: Ran | None = None) -> Any:
        """Humanize, for the workspace a run was run in -- there still or not -- or for none."""
        return self._hmz(ran.workspace if ran is not None else "")

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
        # last few: what a client reads it holds itself.
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
        Either way the last one laid out is kept, which is what a span's id is an id in.
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

    def span(self, ran: Ran, ident: str | int, layout: str = "") -> dict[str, Any]:
        """One span of a run's timeline, whole: the last one laid out, or one laid out now.

        Args:
          ran: The run.
          ident: The span, by its id.
          layout: The `layout` of the timeline the id was read in, or "" for whichever.

        Raises:
          RpcError: 404 if that timeline has no span of that id; 409 if it is not the one
            the id was read in -- a run still going has been laid out again since, and ids
            moved.
        """
        with self._lock:
            kept = self._timelines.get(ran.at)
        laid = kept[1] if kept is not None else self.timeline(ran)
        if layout and str(laid.document["layout"]) != layout:
            raise RpcError(
                Code.CONFLICT,
                f"Epic {ran.name} has been laid out again; read it again.",
            )
        try:
            return laid.span(int(ident))
        except (KeyError, ValueError) as why:
            raise RpcError(
                Code.NOT_FOUND, f"Epic {ran.name} has no span {ident}."
            ) from why

    def bundled(self, ran: Ran) -> Path:
        """One run as one archive, struck of credentials, in a directory of its own.

        Returns:
          The archive, `<name>.hmzepic`; whoever asked removes its directory once done.
        """
        from hmz import machine

        scratch = Path(tempfile.mkdtemp(dir=machine()))
        try:
            at, _ = self.hmz(ran).epics.bundled(ran.at, output=scratch)
        except Exception:
            shutil.rmtree(scratch, ignore_errors=True)
            raise
        return at

    def imported(self, archive: Path) -> dict[str, Any]:
        """One archive read back in as an epic, and whether it can be picked up here.

        Raises:
          RpcError: If it is not an archive Humanize can read, or its epic is here already.
        """
        # Asked of no workspace's Humanize in particular, which reads the epic alone: the one
        # it ran in may be nowhere here.
        epics = self.hmz().epics
        try:
            at = epics.imported(archive)
        except ValueError as why:
            raise refused(why) from why
        ran = self.read(at)
        return {
            "name": at.name,
            "workspace": resolved(ran.workspace) if ran is not None else "",
            "resumable": epics.picks_up(at),
            "why": epics.foreign(at),
        }


#: What an import is refused with for an epic here already: its name, then where it is, which
#: ends in it.
_HERE = re.compile(r"(?P<name>[^/]+) is already here, at .*/(?P=name)")


def refused(why: ValueError) -> RpcError:
    """What a client is told of an archive that could not be imported, as the runtime said it.

    Args:
      why: What importing it raised.

    Returns:
      409 naming the epic in `data`, for one here already; otherwise 400.
    """
    said = str(why)
    # As it was said: it begins with a file's or an epic's name, which is not to be respelled.
    sentence = f"{said}."
    if found := _HERE.fullmatch(said):
        return RpcError(Code.CONFLICT, sentence, {"name": found["name"]})
    return RpcError(Code.REFUSED, sentence)


def held_by(
    runs: list[Ran], running: list[dict[str, Any]]
) -> dict[Path, dict[str, Any]]:
    """Which of the runs written down are the runs the hosts are going with now.

    A host says which epic it writes, once it writes one. Before then it says what it started
    and when -- or, asked from outside, which flow -- and the epic says what it was opened
    for, where and when: the newest run of that flow, in that workspace, on that task and
    opened within a moment of that start where those are said, and not yet ended, is it.

    Args:
      runs: The runs, newest first.
      running: What each host says runs, with its `workspace` and its `slot`.

    Returns:
      Each run going, by its epic: where it is in its turn where it is a chat, or "", the
      slot of the host going with it, and the questions it waits on, as `asking`.
    """
    held: dict[Path, dict[str, Any]] = {}
    for standing in running:
        workspace, epic = standing["workspace"], standing.get("epic")
        started = float(standing.get("at") or 0.0)
        for ran in runs:
            if ran.ended or resolved(ran.workspace) != workspace or ran.at in held:
                continue
            if epic and ran.name != epic:
                continue
            if not epic and (
                ran.flow != standing.get("flow")
                or (standing.get("kind") or kind(ran)) != kind(ran)
            ):
                continue
            if not epic and standing.get("task") and ran.task != standing.get("task"):
                continue
            if not epic and started and abs(_epoch(ran.began) - started) > _SAME:
                continue
            held[ran.at] = {
                "turn": str(standing.get("turn") or ""),
                "slot": str(standing.get("slot") or ""),
                "asking": list(standing.get("asking") or ()),
            }
            break
    return held


def running() -> list[dict[str, Any]]:
    """What each host of this machine runs, as `held_by` reads it; one running nothing is left out.

    Each its state, the run's number, its kind, flow, task and epic, of a chat its turn, and
    its `workspace`, its `slot` and the questions it waits on, each `<run>:<question>`, as
    `asking`: as each host says it of itself.
    """
    said: list[dict[str, Any]] = []
    for status in workspaces.statuses().values():
        if status.get("state") not in ("running", "stopping"):
            continue
        run = status.get("run") or 0
        pending: list[dict[str, Any]] = status.get("pending") or []
        said.append(
            {
                "state": status["state"],
                "run": run,
                "kind": status.get("epic_kind") or "",
                "flow": status.get("flow") or "",
                "epic": status.get("epic") or "",
                "task": status.get("task") or "",
                "workspace": status["workspace"],
                "slot": status["slot"],
                **({"turn": status["turn"]} if "turn" in status else {}),
                "asking": [
                    f"{ask.get('run') or run}:{ask.get('question', '')}"
                    for ask in pending
                ],
            }
        )
    return said


def row(
    ran: Ran,
    *,
    held: bool,
    going: bool = False,
    turn: str = "",
    slot: str = "",
    asking: Sequence[str] = (),
) -> dict[str, Any]:
    """One run as an epic row (Section 4.16.2 of daemon.md).

    Args:
      ran: The run.
      held: Whether it is the run a host is going with, which a client follows live.
      going: Whether it is going at all, held by a host or by any other process.
      turn: Of a chat a host is going with, where it is in its turn, or "" where unknown.
      slot: Of a run a host is going with, which of its workspace's hosts that is: "" for
        the workspace's own, `chat:<hex>` for a chat's.
      asking: Of a run a host is going with, the questions it waits on, each
        `<run>:<question>`.
    """
    from hmz.runtime.epic import RUNNING, ending

    first = ran.task.strip().splitlines()[0] if ran.task.strip() else ""
    how = ending(ran, going=held or going)
    chat = kind(ran) == "chat"
    if chat and how != "failed":
        # A chat is going while its agent answers, and stopped between turns or once over,
        # short of failing (Section 8.5 of core.md).
        how = RUNNING if how == RUNNING and turn != DONE else "stopped"
    return {
        "name": ran.name,
        "workspace": resolved(ran.workspace),
        "kind": "chat" if chat else "flow",
        "flow": "" if chat else ran.flow,
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
        "asking": list(asking),
        "backup": list(ran.backup),
        "backed": ran.backed,
    }


def kind(ran: Ran) -> str:
    """What one epic is, `flow` or `chat`, as its record says it (Section 8.3.5 of core.md)."""
    from hmz.runtime.doing.epics import kind

    return kind(ran)


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
    asking: Sequence[str] = (),
) -> dict[str, Any]:
    """One run, whole, as `runs.get` says it but for its calls.

    Args:
      ran: The run.
      held: Whether it is the run a host is going with.
      going: Whether it is going at all, held by a host or by any other process.
      picks_up: Whether it can be picked up.
      foreign: Why one imported cannot be picked up here, or "".
      turn: Of a chat a host is going with, where it is in its turn, or "" where unknown.
      slot: Of a run a host is going with, which of its workspace's hosts that is.
      asking: Of a run a host is going with, the questions it waits on.
    """
    return row(ran, held=held, going=going, turn=turn, slot=slot, asking=asking) | {
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
        # What a chat's assistant may touch, as its epic records it; "" where it does not.
        "permission": ran.permission,
        # A chat's own preference, as its epic records it; "" where it has none.
        "prefer": ran.prefer,
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


def listed(
    runs: Runs,
    going: list[dict[str, Any]],
    *,
    workspace: str = "",
    status: str = "",
    flow: str = "",
    what: str = "",
    q: str = "",
    offset: int = 0,
    limit: int = 50,
    kept: Callable[[str, str], bool] | None = None,
    hers: Collection[str] = (),
) -> dict[str, Any]:
    """One page of the runs written down, newest first, as `runs.list` answers it.

    Args:
      runs: The runs.
      going: What each host runs, as :func:`running` says it.
      workspace: Only this workspace's runs, by its path, or "" for every one's.
      status: Only those that ended so, or "" for every one.
      flow: Only those of this flow, or "" for every one.
      what: Only those of this kind, `chat` or `flow`, or "" for every one.
      q: Only those whose task, flow or epic name holds this, or "" for every one.
      offset: How many of those found to pass over.
      limit: How many to answer at most.
      kept: Whether a run is there at all, by its epic name and workspace, as though no
        other were: Ai-chan's reach (Section 4.21.4 of daemon.md); None for every one.
      hers: The epic of every Ai-chan conversation, by its name, which is left out, as is
        one a host of an `ai:` slot says it holds (Section 4.16.1.3).
    """
    from hmz.runtime.epic import found

    every = runs.all(workspace)
    if kept is not None:
        every = [ran for ran in every if kept(ran.name, ran.workspace)]
    # One her host has named and no file has yet is hers as much.
    hers = {*hers, *(one["epic"] for one in going if one["slot"].startswith("ai:"))}
    every = [ran for ran in every if ran.name not in hers]
    held = held_by(every, going)
    rows = (
        (
            ran,
            row(
                ran, held=ran.at in held, going=runs.going(ran), **held.get(ran.at, {})
            ),
        )
        for ran in every
    )
    # The kind asked for is what is counted, as it is what is listed.
    went = [(ran, said) for ran, said in rows if not what or said["kind"] == what]
    counts: dict[str, int] = {}
    for _, said in went:
        counts[said["how"]] = counts.get(said["how"], 0) + 1
    shown = [
        said
        for ran, said in went
        if found(ran, said["how"], how=status, flow=flow, text=q)
    ]
    return {
        "runs": shown[offset : offset + limit],
        "total": len(shown),
        "offset": offset,
        "limit": limit,
        "counts": counts,
        # What `flow` finds them by: a chat, of no flow, as `chat` (:func:`found`).
        "flows": sorted({"chat" if kind(ran) == "chat" else ran.flow for ran in every}),
    }


def one(runs: Runs, going: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """One run, whole, as `runs.get` answers it.

    Raises:
      RpcError: 404 for a name no epic has.
    """
    ran = runs.named(name)
    held = held_by(runs.all(ran.workspace), going)
    hmz = runs.hmz(ran)
    return detail(
        ran,
        held=ran.at in held,
        picks_up=hmz.epics.picks_up(ran.at),
        foreign=hmz.epics.foreign(ran.at),
        going=runs.going(ran),
        **held.get(ran.at, {}),
    ) | {"calls": calls(hmz.epics.tree(ran.at))}


def backup(runs: Runs, name: str, to: list[str] | None) -> dict[str, Any]:
    """Backs a run up, queued and never waited on, as `runs.backup` answers it.

    Args:
      runs: The runs.
      name: The run's epic.
      to: The targets to back it up to, or None for those it was started with.

    Raises:
      RpcError: 404 for a name no epic has, 400 for a target there is not, 409 where there
        is no target at all.
    """
    ran = runs.named(name)
    try:
        # Queued, never waited on: how it went is read back off the epic as it is polled.
        queued = runs.hmz(ran).backups.push(ran, to)
    except ValueError as why:
        raise RpcError(Code.REFUSED, reason(str(why))) from why
    if not queued:
        raise RpcError(Code.CONFLICT, "There is no backup target: add one in Settings.")
    return {"queued": list(queued)}


def usage(runs: Runs, days: int, workspace: str = "") -> dict[str, Any]:
    """What the runs spent, day by day and flow by flow, as `runs.usage` answers it.

    Args:
      runs: The runs.
      days: How many days back, today's among them.
      workspace: Only this workspace's runs, by its path, or "" for every one's.
    """
    from hmz.runtime.epic import spending

    said = spending(runs.all(workspace), days)
    return {
        "days_back": days,
        "days": [_said(one) for one in said["days"]],
        "flows": [_said(one) for one in said["flows"]],
        "ended": said["ended"],
        "whole": _said(said["whole"]),
    }


def reason(why: str) -> str:
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


@functools.cache
def resolved(workspace: str) -> str:
    """A workspace's path as one is compared with another: whole, with every link followed."""
    return str(Path(workspace).expanduser().resolve()) if workspace else ""


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


def _epoch(stamp: str) -> float:
    """A moment an epic wrote down, in seconds since the epoch, or 0 for one that is not one."""
    try:
        return datetime.datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return 0.0


def _hmz(workspace: str) -> Any:
    """Humanize for a workspace, or for the daemon's own directory for none."""
    from hmz.daemon import Hmz

    return Hmz(workspace or None)


#: The runs of every workspace, as the daemon reads them for every client.
RUNS = Runs(_hmz)


def _invalid(message: str) -> RpcError:
    return RpcError(Code.INVALID_PARAMS, message)


def _within(
    call: Call, name: str, default: int, least: int, most: int | None = None
) -> int:
    """An integer parameter, its default where absent, refused outside its range."""
    value: int = call.params.get(name, default)
    if value < least or (most is not None and value > most):
        upto = f" to {most}" if most is not None else ""
        raise _invalid(f"{call.method} takes {name} as integer from {least}{upto}.")
    return value


def _workspace_of(call: Call) -> str:
    # A workspace since removed is still filtered by: its epics are read, not its directory.
    said: str | None = call.params.get("workspace")
    return str(workspaces.place(said, made=True)) if said is not None else ""


def _list(call: Call) -> dict[str, Any]:
    params = call.params
    offset = _within(call, "offset", 0, 0)
    limit = _within(call, "limit", 50, 1, _PAGE)
    return listed(
        RUNS,
        running(),
        workspace=_workspace_of(call),
        status=params.get("status", ""),
        flow=params.get("flow", ""),
        what=params.get("kind", ""),
        q=params.get("q", ""),
        offset=offset,
        limit=limit,
        kept=reach.epics(),
        hers=reach.conversations().epics(),
    )


def _get(call: Call) -> dict[str, Any]:
    return one(RUNS, running(), call.params["name"])


def _trace(call: Call) -> dict[str, Any]:
    return {"sessions": RUNS.traced(RUNS.named(call.params["name"]))}


def _timeline(call: Call) -> dict[str, Any]:
    return RUNS.timeline(RUNS.named(call.params["name"])).document


def _span(call: Call) -> dict[str, Any]:
    params = call.params
    return RUNS.span(RUNS.named(params["name"]), params["id"], str(params["layout"]))


def _bundle(call: Call) -> dict[str, Any]:
    at = RUNS.bundled(RUNS.named(call.params["name"]))
    try:
        handle = files.reading(call.peer, at)
    except Exception:
        shutil.rmtree(at.parent, ignore_errors=True)
        raise
    return {
        "handle": handle,
        "filename": at.name,
        "size": at.stat().st_size,
        "type": BUNDLE,
    }


def _backup(call: Call) -> dict[str, Any]:
    to: list[Any] | None = call.params.get("to")
    if to is not None and not all(isinstance(one, str) for one in to):
        raise _invalid("runs.backup takes to as array of strings.")
    return backup(RUNS, call.params["name"], cast("list[str] | None", to))


def _import(call: Call) -> dict[str, Any]:
    handle: str | None = call.params.get("handle")
    path: str | None = call.params.get("path")
    if (handle is None) == (path is None):
        raise _invalid("runs.import takes handle or path, one of them.")
    if handle is not None:
        name, held = files.taken(call, handle)
        try:
            return RUNS.imported(_named(held, name))
        finally:
            shutil.rmtree(held.parent, ignore_errors=True)
    archive = local(cast("str", path))
    if not archive.is_absolute():
        raise RpcError(Code.REFUSED, "Say path as a whole path on this machine.")
    return RUNS.imported(archive)


def _named(held: Path, name: str) -> Path:
    """An archive sent, under the name it was sent as: what says it is a `.hmzepic`.

    Raises:
      RpcError: 400 for a name that is no file's.
    """
    if (
        name in ("", ".", "..")
        or any(c in name for c in "/\\\0")
        or len(name.encode()) > _NAME
    ):
        raise RpcError(Code.REFUSED, "That is not a file name.")
    return held.replace(held.parent / name)


def _usage(call: Call) -> dict[str, Any]:
    return usage(RUNS, _within(call, "days", 30, *_DAYS), _workspace_of(call))


#: The methods of `runs.*`.
METHODS: Mapping[str, Handler] = {
    "runs.list": _list,
    "runs.get": _get,
    "runs.trace": _trace,
    "runs.timeline": _timeline,
    "runs.span": _span,
    "runs.bundle": _bundle,
    "runs.backup": _backup,
    "runs.import": _import,
    "runs.usage": _usage,
}
