"""What one run of one flow was, written down as it runs.

A flow drives several agents through many sessions, and every one of those sessions is written
down by the backend that ran it -- under an id of its own, in a directory of its own, saying
nothing about whose it was or what it was part of. The run itself is written nowhere. This is
that: which flow was run, on what, by which agents, and which sessions each of them opened as
it went -- each under the account it ran as. Enough to gather a trace of the run afterwards
out of the ids alone, and enough to find the sessions a run left behind.

Not what the sessions said. A backend's own log is the turn-by-turn record and this is not a
second copy of it: what is kept here is the shape of the run, one line per thing that happened
to it, and beside the lines a link per session pointing at the log the backend is writing. A
link rather than a copy, and read by whoever is looking rather than by humanize: a run is
written and read through the paths the backends themselves keep, so that nothing here can be
the reason a log is written twice or read from the wrong place.

One epic is one run, and one directory::

    ~/.humanize/epics/<workspace>/<when>-<which>/
        epic.jsonl                      what happened, a line at a time
        epic.<flow>_<which>.jsonl       the same, for one flow the run called
        resume.jsonl                    the engine's journal, for a flow that can be picked up
        profile.jsonl                   the programs it ran, for a run that was profiled
        sessions/<session>/…            a link per file the backend logged it to
        traces/<when>.trace.json        what was gathered of it afterwards, to be read

A flow may call another, and a called flow opens sessions exactly as the flow that called it
does. So each call gets a record of its own beside the run's own, and the record of whatever
called it says what it called and which file to read it in. Still one run
and still one directory: a called flow is part of the run that called it, not another run.

One directory and one tree. A call made from inside a called flow is written under *that*
flow's record rather than under the run's, and says which one it was under, so a run five
flows deep with two of every level going at once reads back as the shape it ran in rather
than as thirty-one things one run did -- which is what :func:`tree` reads it as.

It opens when the flow starts and closes when the flow stops, however it stops -- finished,
failed, or interrupted. A closed epic is never reopened: running the flow again is another
run, with sessions of its own, and so another epic -- which is what a flow that says it can
be picked up again is picked up as. What a resumable flow keeps is the engine's journal
(:mod:`hmz.runtime.flowing.journaling`), written into the epic of the run keeping it; a run
picking it up is handed a copy of it in an epic of its own, which the engine compacts and goes
on appending to.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import re
import shutil
import threading
import uuid
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Self, cast

from hmz import home
from hmz.coganchor import backends

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from hmz.coganchor.agents import AgentBase

    from .tracing.profile import Profiler

__all__ = [
    "JOURNAL",
    "LOCAL",
    "RECORD",
    "RECORDS",
    "RESUME",
    "SESSIONS",
    "TRACES",
    "Called",
    "Drove",
    "Epic",
    "Ran",
    "Session",
    "Sub",
    "called",
    "epics",
    "linked",
    "opened",
    "picks_up",
    "read",
    "records",
    "resumed",
    "sessions",
    "state",
    "tree",
    "under",
    "where",
]

#: What a directory may be called after: everything else in a path is flattened, the way the
#: agents themselves flatten a workspace into the folder they log it under.
_PLAIN = re.compile(r"[^A-Za-z0-9]")

#: What a session may be named with. Wider than the above, because this name is read as well
#: as written -- the backend, the account and the id are meant to be legible in it -- and
#: narrower than a path, because it is one directory name on somebody's filesystem.
_LEGIBLE = re.compile(r"[^A-Za-z0-9._@-]+")

#: The file an epic's own record is written to, inside the epic's directory.
JOURNAL = "epic.jsonl"

#: What the record of a flow another flow called is called, beside the run's own: which
#: flow it is of, and an id of that call rather than of the flow -- a flow called twice is
#: two records, since it is two runs of it and each opened its own sessions.
RECORD = "epic.{flow}_{ident}.jsonl"

#: Every such record of one epic, as a glob over its directory. It does not match the
#: run's own, which is the record of the flow nothing called.
RECORDS = "epic.*.jsonl"

#: Where the links to the sessions' own logs go, a directory per session.
SESSIONS = "sessions"

#: The engine's journal of a resumable run: what each flow call kept, and which calls ended.
#: What `--resume` and `/resume` pick a run up from, kept beside the run it was written by.
RESUME = "resume.jsonl"

#: Where the traces gathered of one run go, inside that run's own directory. A trace of a run
#: belongs with the run: the sessions it points at and the state it left are already there.
TRACES = "traces"

#: What a session opened as the account this machine is already signed into is written under.
#: A word rather than the empty string it is configured as: this goes in a directory name and
#: in a listing, and both of those read better saying which account than saying nothing.
LOCAL = "local"


def _now() -> str:
    """This moment, as every file humanize writes spells one."""
    return (
        datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    )


def _stamp() -> str:
    """This moment, as a name that sorts the way the moments do: to the millisecond."""
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S.%f")[:-3] + "Z"


class Session(NamedTuple):
    """One session a run opened, as the run wrote it down.

    Attributes:
      agent: Whose it was, by the name the flow calls that agent.
      backend: The coding agent CLI that took its turns, which is what logged it.
      provider: The account those turns ran as, or `local` for the one this machine is
        already signed into.
      ident: The id the backend gave it, which is what a trace of the run is gathered by.
      name: What the run calls it -- which agent, which CLI, which account and which session,
        in one name -- and the directory its links are under.
      at: When it was opened.
      flow: The flow it was opened inside, as that flow was asked for: the run's own, or one
        the run called. "" for a session written down before a run said.
      parent: The id of the conversation this one was forked from, for a session a flow
        branched, and "" for one that started from nothing -- which is most of them. Written
        down because the backend does not: its log shows a session that began knowing things,
        and only the run can say which conversation it got them from. Which is what makes two
        branches of one conversation readable afterwards as the branches they were.
      record: The record of this epic it was written into, which is which *call* of that flow
        opened it. A flow called five times in one run is five records, and the name alone
        would make one flow of the five.
    """

    agent: str
    backend: str
    provider: str
    ident: str
    name: str
    at: str = ""
    flow: str = ""
    parent: str = ""
    record: str = ""


class Drove(NamedTuple):
    """One agent a run was given, as the run wrote it down.

    Attributes:
      agent: The role the flow calls it by.
      backend: The CLI it drives.
      model: What that CLI was asked to run.
      effort: How hard it was asked to think, "" for the CLI's own default.
      provider: The account it was configured to run as, or "" for this machine's own.
    """

    agent: str
    backend: str
    model: str
    effort: str
    provider: str = ""

    @property
    def spec(self) -> str:
        """What it runs, spelled the way `-a` spells one after the role."""
        cli = f"{self.backend}@{self.provider}" if self.provider else self.backend
        return f"{cli}/{self.model}:{self.effort or 'auto'}"


class Called(NamedTuple):
    """One flow a run called, as the run that called it wrote it down.

    Attributes:
      flow: The flow, as it was asked for.
      task: What it was called with.
      record: The file inside the epic it was written to, which is where its own sessions
        are and where whatever it called in turn is written down.
      began: When it was called.
      ended: When it returned, or "" for a call that never did -- a run killed under it.
      how: How the call ended -- done, failed or stopped -- read out of its own record, and
        "" for one that has not ended or was not read as a tree. A call that raised inside a
        run that carried on is a call that failed and a run that did not, so it is the
        call's own record that says it rather than the run's.
      calls: What that call called in turn, read out of its own record: a run of flows
        calling flows is a tree, and reading it as a list would say a flow ran under the
        wrong one. Empty unless it was read as one -- :func:`tree`.
    """

    flow: str
    task: str
    record: str
    began: str = ""
    ended: str = ""
    how: str = ""
    calls: tuple[Called, ...] = ()


class Ran(NamedTuple):
    """What one epic was, read back off its own record.

    Attributes:
      at: The epic's directory, which is what everything about it is under.
      flow: The flow that was run, as it was named.
      task: What its agents were asked to do.
      workspace: Where it ran.
      began: When it started.
      ended: When it stopped, or "" for one still running or abandoned where it stood.
      how: How it stopped -- done, failed or stopped -- and "" while it has not.
      agents: What it was given for each agent role, in the order the flow declares them.
      sessions: Every session it opened, oldest first, the ones opened inside a flow it
        called among them -- one run is one run, however many flows it took to run it.
      called: Every flow this run called, in the order it called them. What each of those
        called in turn is written in its own record rather than here.
      resumable: Whether the flow said it could be picked up again when this run happened.
        Whether it says so now is asked of the flow: this is what the run recorded, which is
        what it was rather than what can be done with it today.
      ref: The flow's canonical ref, which is what a run is picked up by whatever it was
        named as; "" for a run written before there was one.
      envs: What it was given for each environment role, each as `-e` spells one.
      params: What the flow was set up with, as JSON.
      budget: What the run was allowed to spend, as JSON, or None where it said nothing.
      picked_up: The epic this run was picked up from, by name, or "".
    """

    at: Path
    flow: str = ""
    task: str = ""
    workspace: str = ""
    began: str = ""
    ended: str = ""
    how: str = ""
    agents: tuple[Drove, ...] = ()
    sessions: tuple[Session, ...] = ()
    called: tuple[Called, ...] = ()
    resumable: bool = False
    ref: str = ""
    envs: tuple[str, ...] = ()
    params: dict[str, Any] = {}  # noqa: RUF012 -- a NamedTuple's default, never written to
    budget: dict[str, Any] | None = None
    picked_up: str = ""

    @property
    def name(self) -> str:
        """What this epic is called, which is the directory it is written in."""
        return self.at.name


def called(agent: str, backend: str, provider: str, ident: str) -> str:
    """What a run calls one session, which is a name rather than an id.

    A backend names a session with a UUID and nothing else, which says nothing about whose it
    was, what took its turns or which account they were taken as -- and a directory of forty
    of those is a directory nobody can read. So a session is named here for the four things
    somebody looking at a run wants to tell one from another by, the id among them: the id
    alone is what a trace is gathered by, and a name without it would name two.

    Args:
      agent: Whose session it is, by the name the flow calls that agent.
      backend: The CLI that took its turns.
      provider: The account they ran as, or "" for this machine's own.
      ident: The backend's own id for it.

    Returns:
      The name, as one directory name: `<agent>-<cli>@<account>-<id>`.
    """
    parts = (
        agent or "agent",
        backend or "cli",
        provider or LOCAL,
        ident or uuid.uuid4().hex[:8],
    )
    agent_at, cli, account, said = (
        _LEGIBLE.sub("-", part).strip("-") for part in parts
    )
    return f"{agent_at}-{cli}@{account}-{said}"


def _record(flow: str, ident: str) -> str:
    """What the record of one called flow is called, inside the epic that called it.

    Args:
      flow: The flow, as it was asked for -- which may be a path, and is flattened the way
        everything else humanize writes a name into a filename is.
      ident: What tells this call of it from the next one.

    Returns:
      The filename, beside the run's own record.
    """
    return RECORD.format(flow=_LEGIBLE.sub("-", flow).strip("-") or "flow", ident=ident)


def _provider(agent: AgentBase) -> str:
    """Which account an agent's turns are running as, as a name to write down.

    Asked of the agent rather than read off its config, so that a turn that fell over onto
    the account the first one falls back to is written down under the account it actually ran
    as. An agent configured with an account that is not there says so the first time a turn
    needs one, and this is not that moment: what it was configured with is what is written.

    Args:
      agent: The agent.

    Returns:
      The account's name, or "" for the one this machine is already signed into.
    """
    try:
        at = agent.provider
    except ValueError:
        return agent.config.provider
    return at.name if at is not None else ""


def _logs(backend: str, ident: str) -> list[Path]:
    """Every file one session was logged to by the backend that ran it.

    Args:
      backend: The CLI, by the name `hmz.coganchor.backends` knows it under.
      ident: The id it gave the session.

    Returns:
      The files, oldest path first, and nothing at all for a backend humanize has no logs
      written down for or one that has never run on this machine.
    """
    profile = backends.named(backend)
    if profile is None or not profile.logs:
        return []
    where = profile.directory()
    if not where.is_dir():
        return []
    found: list[Path] = []
    for pattern in profile.logs:
        try:
            found += sorted(where.glob(pattern.format(ident=ident)))
        except (OSError, ValueError):
            continue  # a home that cannot be read is a session with no links, not a failure
    return [one for one in found if one.is_file()]


def _link(at: Path, backend: str, ident: str) -> list[str]:
    """Points a directory of the epic's own at the logs one session is being written to.

    Made for whoever is reading the run afterwards, and for nothing else: humanize reads and
    writes a log where the backend keeps it, so a link that is broken, refused by the
    filesystem or pointing at a file that has since been rolled over costs the run nothing.

    Args:
      at: The directory to make them in, which is the session's own under `sessions/`.
      backend: The CLI that logged it.
      ident: The id it logged it under.

    Returns:
      What each link is called, which is the log's own name where that is unambiguous and the
      path under the backend's home flattened where two of them share one.
    """
    found = _logs(backend, ident)
    if not found:
        return []
    profile = backends.named(backend)
    where = profile.directory() if profile is not None else Path()
    shared = Counter(one.name for one in found)
    made: list[str] = []
    try:
        at.mkdir(parents=True, exist_ok=True)
        # The links this made last time go first: a session gains files as it runs -- a
        # sub-agent's transcript, a second day's log -- and a name that was unambiguous when
        # there was one file is a name two files want once there are two.
        for old in at.iterdir():
            if old.is_symlink():
                old.unlink()
        for one in found:
            name = one.name
            if shared[name] > 1:
                with_root = one.relative_to(where) if one.is_relative_to(where) else one
                name = _LEGIBLE.sub("-", str(with_root)).strip("-")
            (at / name).symlink_to(one)
            made.append(name)
    except OSError:
        # A filesystem that will not make one -- Windows without the privilege, a mount that
        # has gone -- is a run without links rather than a run that stops.
        return made
    return made


def _journal(epic: Path) -> Iterator[dict[str, Any]]:
    """Every record of one epic's resume journal, skipping what a killed run left half-written.

    Args:
      epic: The epic's directory.

    Yields:
      One record apiece, and nothing at all for an epic that keeps no journal.
    """
    try:
        lines = (epic / RESUME).read_bytes().splitlines()
    except OSError:
        return
    for line in lines:
        try:
            said = json.loads(line)
        except ValueError:
            continue
        if isinstance(said, dict):
            yield cast("dict[str, Any]", said)


def picks_up(epic: Path) -> bool:
    """Whether a run can be picked up from one epic: whether its journal holds a flow call.

    Args:
      epic: The epic's directory.

    Returns:
      True where the run was of a resumable flow and got as far as writing its first call
      down; False for any other run, and for one killed before it wrote anything.
    """
    return any(one.get("t") == "call" for one in _journal(epic))


def state(epic: Path, flow: str = "") -> dict[str, Any]:
    """What a resumable flow kept in one run, as the run left it.

    Args:
      epic: The epic's directory.
      flow: Which flow's, by its canonical ref -- the last call of it the run made -- or ""
        for the flow the run was of.

    Returns:
      What it kept, key by key, and nothing at all where that flow kept nothing or the run
      kept no journal.
    """
    calls: dict[int, str] = {}
    held: dict[int, dict[str, Any]] = {}
    which: int | None = None
    for said in _journal(epic):
        kind = said.get("t")
        try:
            ident = int(said["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if kind == "call":
            calls[ident] = str(said.get("ref") or "")
            held[ident] = {}
            if (not flow and said.get("parent") == 0 and which is None) or (
                flow and calls[ident] == flow
            ):
                which = ident
        elif kind == "set" and ident in held:
            held[ident][str(said.get("key"))] = said.get("value")
        elif kind == "del" and ident in held:
            held[ident].pop(str(said.get("key")), None)
    return held.get(which, {}) if which is not None else {}


def resumed(flow: str, workspace: Path | str | None = None) -> Path | None:
    """The epic a resumable flow's next run picks up from: the newest one it can be.

    Args:
      flow: The flow, by its canonical ref or as it was named when it was run.
      workspace: Where it runs, defaulting to this directory.

    Returns:
      The newest epic of that flow here whose run was resumable and wrote its journal, or
      None where there is none -- a flow that never ran here, ran as something that could
      not be picked up, or was killed before it wrote anything down.
    """
    for epic in reversed(epics(workspace)):
        began = next(
            (one for one in _events(epic) if one.get("event") == "began"), None
        )
        if began is None or not began.get("resumable"):
            continue
        if flow not in (began.get("ref"), began.get("flow")):
            continue
        if picks_up(epic):
            return epic
    return None


class Epic:
    """One run of one flow: the directory it is written to, and what has happened to it."""

    def __init__(
        self,
        flow: str,
        task: str,
        workspace: Path | None = None,
        *,
        ref: str = "",
        agents: Sequence[Drove] = (),
        envs: Sequence[str] = (),
        params: Mapping[str, Any] | None = None,
        budget: Mapping[str, Any] | None = None,
        resumable: bool = False,
        picked_up: Path | None = None,
        profile: bool = False,
    ) -> None:
        """Opens an epic, and writes down what it is a run of.

        Args:
          flow: The flow being run, as it was named.
          task: What its agents were asked to do.
          workspace: Where the run happens, defaulting to this directory. Epics are kept
            under the workspace they ran in, since that is what anyone looking for one has.
          ref: The flow's canonical ref, which is what a run is picked up by.
          agents: What each agent role was given, in the order the flow declares them.
          envs: What each environment role was given, as `-e` spells one.
          params: What the flow was set up with, as JSON.
          budget: What the run may spend, as JSON, or None.
          resumable: Whether the flow says it can be picked up again, which is what makes
            the journal it keeps something to run it on rather than something to read.
          picked_up: The epic this run is picked up from, whose journal is copied into this
            one for the run to go on from, or None for a run starting from nothing.
          profile: Whether to sample the programs the agents start while the run goes, so
            that what a turn spent its minutes on is in the run's trace beside the turn. A
            setting of the workspace, asked of it by whoever opens the epic.
        """
        self._begin(
            home()
            / "epics"
            / _PLAIN.sub("-", str((workspace or Path.cwd()).resolve()))
            # The moment names it and six hex say which, since two flows may be started in
            # one millisecond and neither is the other's run. To the millisecond rather than
            # to the second because these are read back in the order they sort in: which run
            # a flow is picked up from is the last of them, and two started inside one second
            # would otherwise be ordered by the hex, which is to say at random.
            / f"{_stamp()}-{uuid.uuid4().hex[:6]}",
            JOURNAL,
            (workspace or Path.cwd()).resolve(),
            flow,
        )
        if picked_up is not None:
            # A copy rather than the file itself: the run it came from is closed, and the
            # engine compacts what it picks up before it appends to it.
            self._at.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(OSError):
                shutil.copyfile(picked_up / RESUME, self._at / RESUME)
        #: The programs this run starts, sampled while it runs, or None for a run nobody
        #: asked to profile -- which is every run until somebody says otherwise.
        self._profiler = self._profiling() if profile else None
        self.write(
            "began",
            flow=flow,
            task=task,
            workspace=str(self._where),
            resumable=resumable,
            **({"ref": ref} if ref else {}),
            **({"picked_up": picked_up.name} if picked_up is not None else {}),
            agents=[one._asdict() for one in agents],
            envs=list(envs),
            params=dict(params or {}),
            **({"budget": dict(budget)} if budget is not None else {}),
        )

    def _begin(self, at: Path, journal: str, workspace: Path, flow: str) -> None:
        """Settles what is written down, and where.

        Shared with the record of a flow this one called, which is the same thing written
        into a file of its own beside this one: a called flow opens sessions exactly as the
        flow that called it does, and neither writes the other's.

        Args:
          at: The epic's directory.
          journal: The file inside it these lines go to.
          workspace: Where the run is happening.
          flow: The flow this is a record of, as it was named.
        """
        self._at = at
        self._journal = journal
        self._writing = (
            threading.Lock()
        )  # sessions open on whichever thread a turn runs on
        #: Every session this run has opened, by the name it was written down under, so that
        #: the links can be made again as the backends go on writing to them.
        self._sessions: dict[str, tuple[str, str]] = {}
        self._flow = flow
        self._where = workspace
        self._profiler: Profiler | None = None
        #: How it ended, where whoever is running it has said: "stopped" for a run stopped
        #: by hand or by what it was allowed to spend, rather than one that failed.
        self._how = ""

    @property
    def path(self) -> Path:
        """The directory this epic is written in."""
        return self._at

    @property
    def journal(self) -> Path:
        """The file this record is written to, a line per thing that happened to it."""
        return self._at / self._journal

    @property
    def record(self) -> str:
        """What that file is called inside the epic, which is what a call refers to."""
        return self._journal

    @property
    def workspace(self) -> Path:
        """Where this run is happening, which is what its epics are kept under."""
        return self._where

    @property
    def resume(self) -> Path:
        """Where the engine keeps this run's journal, for a flow that can be picked up."""
        return self._at / RESUME

    def stopped(self) -> None:
        """Says the run was stopped rather than failed, for the line it ends with.

        A run stopped by hand, or by the budget it was given, is the ordinary end of a run
        nothing else ends; what raised out of it is still what stopped it, and is not a
        failure to report.
        """
        self._how = "stopped"

    def _profiling(self) -> Profiler | None:
        """The sampler this run is profiled by, started, or None where there is none.

        Nothing here MUST be able to stop a run: a machine whose processes cannot be read is
        a run with no profile rather than a run that will not start.

        Returns:
          The profiler, already running.
        """
        try:
            from .tracing.profile import PROFILE, Profiler
        except (
            ImportError
        ):  # pragma: no cover -- an install missing what it was built with
            return None
        one = Profiler(self._at / PROFILE)
        try:
            one.start()
        except (OSError, RuntimeError):
            return None
        return one

    def __enter__(self) -> Self:
        """Hands the epic to whatever is running the flow inside it."""
        return self

    def __exit__(
        self, kind: type[BaseException] | None, why: object, traceback: object
    ) -> None:
        """Closes the epic, saying how the run ended: an epic closes once and for all.

        Args:
          kind: What was raised out of the run, if anything.
          why: The exception itself, unread.
          traceback: Where it was raised, unread.
        """
        self._close(kind)

    def _close(self, kind: type[BaseException] | None) -> None:
        """Writes down that what this is a record of has ended, and how it ended.

        Shared with the record of a flow this one called, which ends when the call returns
        rather than when the run does: a record closes once and for all either way.

        Args:
          kind: What was raised out of it, if anything.
        """
        # The sampler first, so that what it saw is written down before anything reads it,
        # and so that a run which is over stops costing anything.
        if self._profiler is not None:
            self._profiler.stop()
        # The links again, now that the run is over: a backend writes a session's log while
        # the session runs and finishes writing it after the last turn, and a sub-agent's
        # transcript appears whenever that sub-agent was started.
        self.links()
        # A run interrupted from outside is a run that was stopped, however the turn under
        # way made of it: the process goes out from under that turn, and from inside one
        # that reads as a turn that could not finish.
        stopped = kind is not None and issubclass(
            kind, KeyboardInterrupt | asyncio.CancelledError
        )
        self.write(
            "ended",
            how=self._how
            or ("stopped" if stopped else "failed" if kind is not None else "done"),
        )

    def called(self, flow: str, task: str = "", *, resumable: bool = False) -> Sub:
        """Opens the record of a flow this one called, beside this one's own.

        A flow that called another is two flows, and each of them opened sessions and may
        have called a third. So each gets a record of its own -- one file per call, in the
        directory of the run that started it -- and this one is left saying what it called,
        when, and which file to read it in. One run, written down as the shape it actually
        ran in rather than as one flat list nothing can be attributed to.

        Args:
          flow: The flow being called, by its canonical ref.
          task: What it was called with, where that is known.
          resumable: Whether it says it can be picked up again.

        Returns:
          The record, to be written to while the call runs and ended when it returns.
        """
        # Named for the flow and for this call of it: a flow called twice in one run is two
        # runs of it, each with its own sessions, and one file for both would say neither.
        record = _record(flow, uuid.uuid4().hex[:6])
        self.write("called", flow=flow, task=task, epic=record)
        return Sub(self, record, flow, task, resumable=resumable)

    def opened(self, agent: AgentBase, session: str, parent: str = "") -> None:
        """Writes down a session one of the agents has just opened.

        Which agent it was, which CLI took its turns and which account they were taken as:
        the backend's own log says none of those, and two agents at one configuration are one
        agent to anything reading the logs alone. And which conversation it was cut from,
        where it was cut from one: a fork's log opens on an agent that already knows things,
        and nothing but the run can say where it knew them from.

        Args:
          agent: Whose session it is.
          session: The backend's id for it, which is what a trace of the run is gathered by.
          parent: The id of the conversation it was forked from, or "" for one that
            started from nothing.
        """
        self.session(agent.id, agent.backend, _provider(agent), session, parent)

    def session(
        self, agent: str, backend: str, provider: str, ident: str, parent: str = ""
    ) -> None:
        """Writes down a session, as :meth:`opened` does, for one no coganchor agent opened.

        Args:
          agent: Whose it is, by the role the flow calls that agent.
          backend: What took its turns.
          provider: The account they ran as, or "" for this machine's own.
          ident: Its id.
          parent: The id of the conversation it was forked from, or "".
        """
        name = called(agent, backend, provider, ident)
        with self._writing:
            self._sessions[name] = (backend, ident)
        self.write(
            "opened",
            agent=agent,
            backend=backend,
            provider=provider or LOCAL,
            session=ident,
            name=name,
            # Where to look for it inside this epic, which is a link and not the log itself.
            where=f"{SESSIONS}/{name}",
            # Said only where there is one, so that the ordinary line stays the line it was.
            **({"parent": parent} if parent else {}),
        )
        self.links(name)

    def links(self, only: str = "") -> None:
        """Points this epic's `sessions/` at the logs its sessions are being written to.

        Args:
          only: One session, by the name it was written down under, or "" for every session
            this run has opened.
        """
        with self._writing:
            if not only:
                held = dict(self._sessions)
            elif only in self._sessions:
                held = {only: self._sessions[only]}
            else:
                return
        for name, (backend, ident) in held.items():
            _link(self._at / SESSIONS / name, backend, ident)

    def write(self, event: str, **said: Any) -> None:
        """Appends one line to the epic.

        Appended and flushed apiece rather than held: a flow runs for hours and is watched
        while it does, and a run that died is a run whose epic has to say what it got to.

        Args:
          event: What happened.
          said: What is worth saying about it.
        """
        with self._writing:
            self._at.mkdir(parents=True, exist_ok=True)
            with (self._at / self._journal).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": event, "at": _now(), **said}) + "\n")


class Sub(Epic):
    """One flow another flow called, written down in a record of its own.

    Everything a run writes down, a flow the run called writes down too: the sessions it
    opened, and whatever it called in turn. What it does not have is a
    directory: it is part of the run that called it, so its record sits beside that run's own
    in the same epic, and its sessions link into the same `sessions/`.

    It ends when the call returns rather than when the run does, and says so at both ends --
    here, and in the record of whatever called it. Closed by :meth:`ended` rather than as a
    block, since what ends a call is the flow returning and the agents are the run's own
    afterwards.
    """

    def __init__(
        self,
        under: Epic,
        record: str,
        flow: str,
        task: str = "",
        *,
        resumable: bool = False,
    ) -> None:
        """Opens the record, and writes down what it is a record of.

        Args:
          under: What called it, which is where the call itself is written down.
          record: What this record is called, inside the epic they share.
          flow: The flow being called, by its canonical ref.
          task: What it was called with, where that is known.
          resumable: Whether it says it can be picked up again.
        """
        self._under = under
        self._begin(under.path, record, under.workspace, flow)
        self.write(
            "began",
            flow=flow,
            task=task,
            workspace=str(under.workspace),
            resumable=resumable,
            # Which record called this one, so that a flow that called a flow that called a
            # flow reads back as what it was rather than as three things one run did.
            under=under.record,
        )

    def ended(self, kind: type[BaseException] | None = None, how: str = "") -> None:
        """Closes this record, and writes the call's other end where the call was written.

        Args:
          kind: What was raised out of the called flow, if anything.
          how: How it ended where the caller knows better than `kind` says -- "stopped"
            for a call stopped rather than failed -- or "" to read it off `kind`.
        """
        if how:
            self._how = how
        self._close(kind)
        self._under.write("returned", flow=self._flow, epic=self._journal)


def under(workspace: Path | str | None = None) -> Path:
    """Where the runs of one workspace are kept.

    Args:
      workspace: Which workspace, defaulting to this directory.

    Returns:
      The directory. It may not exist: a workspace nothing has been run in has none, and
      whatever writes there is what makes it.
    """
    return (
        home() / "epics" / _PLAIN.sub("-", str(Path(workspace or Path.cwd()).resolve()))
    )


def epics(workspace: Path | str | None = None) -> list[Path]:
    """The epics run in one workspace, oldest first.

    Args:
      workspace: Where they ran, defaulting to this directory.

    Returns:
      One directory per epic, which is empty where nothing has been run.
    """
    try:
        return sorted(
            one for one in under(workspace).iterdir() if (one / JOURNAL).is_file()
        )
    except OSError:
        return []


def _events(epic: Path) -> list[dict[str, Any]]:
    """Every line one epic holds, in the order they were written.

    Args:
      epic: The epic's directory, or the record inside it.

    Returns:
      One record apiece, less whatever could not be read as one: a run that died mid-line
      left a line rather than an epic, and the rest of it is still what happened.
    """
    at = epic / JOURNAL if epic.is_dir() else epic
    try:
        lines = at.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    held: list[dict[str, Any]] = []
    for line in lines:
        try:
            said = json.loads(line)
        except ValueError:
            continue
        if isinstance(said, dict):
            held.append(cast("dict[str, Any]", said))
    return held


def records(epic: Path) -> list[Path]:
    """Every record one epic holds: the run's own, and one per flow the run called.

    Args:
      epic: The epic's directory.

    Returns:
      The files, the run's own first and the rest by name. Not the order they were opened
      in: a name says which flow before it says which call of it, and what happened in what
      order is what the lines themselves say.
    """
    at = epic / JOURNAL
    held = [at] if at.is_file() else []
    # A directory that went while it was being read is the records that were read, the way
    # a record that cannot be read at all is an epic with nothing in it.
    with contextlib.suppress(OSError):
        held += sorted(one for one in epic.glob(RECORDS) if one.is_file())
    return held


def opened(epic: Path) -> dict[str, list[str]]:
    """What each agent of one epic opened, as the ids the backends gave those sessions.

    Which is what a trace is gathered by: the backends log a session under an id and never
    say whose it was, so the run has to say it instead. Every record of the epic, since a
    session opened inside a flow the run called is one of the run's own -- what a trace of it
    is is what the whole run did.

    Args:
      epic: The epic to read.

    Returns:
      One entry per agent that opened anything, oldest session first.
    """
    held: dict[str, list[str]] = {}
    for one in sessions(epic):
        held.setdefault(one.agent, []).append(one.ident)
    return held


def sessions(epic: Path) -> list[Session]:
    """Every session one epic opened, oldest first.

    Read across every record it holds, and each session says which flow opened it: one run
    is one run, however many flows it took to run it, and which of them a session was opened
    inside is what a record of its own is for.

    Args:
      epic: The epic to read.

    Returns:
      One apiece, saying whose it was, what took its turns, which account they ran as, what
      the run calls it, which flow it was opened in, and which conversation it was cut from
      where it was cut from one.
    """
    held: list[Session] = []
    for at in records(epic):
        events = _events(at)
        flow = next(
            (
                str(one.get("flow") or "")
                for one in events
                if one.get("event") == "began"
            ),
            "",
        )
        for said in events:
            if said.get("event") != "opened" or not said.get("session"):
                continue
            agent, backend = (
                str(said.get("agent") or ""),
                str(said.get("backend") or ""),
            )
            ident = str(said["session"])
            provider = str(said.get("provider") or LOCAL)
            held.append(
                Session(
                    agent=agent,
                    backend=backend,
                    provider=provider,
                    ident=ident,
                    name=str(said.get("name") or ""),
                    at=str(said.get("at") or ""),
                    flow=flow,
                    parent=str(said.get("parent") or ""),
                    record=at.name,
                )
            )
    # By when each was opened rather than by which record it is in: the records are one run,
    # and a run happened in one order.
    return sorted(held, key=lambda one: one.at)


def read(epic: Path) -> Ran | None:
    """What one epic was, read back off its own record.

    Args:
      epic: The epic's directory.

    Returns:
      The run, or None for a directory holding nothing this wrote -- which is a directory
      somebody put there rather than a run to report.
    """
    events = _events(epic)
    began = next((one for one in events if one.get("event") == "began"), None)
    if began is None:
        return None
    ended = next((one for one in reversed(events) if one.get("event") == "ended"), None)
    agents: list[Drove] = []
    for one in began.get("agents") or ():
        if not isinstance(one, dict):
            continue
        said = cast("dict[str, Any]", one)
        agents.append(
            Drove(
                agent=str(said.get("agent") or ""),
                backend=str(said.get("backend") or ""),
                model=str(said.get("model") or ""),
                effort=str(said.get("effort") or ""),
                provider=str(said.get("provider") or ""),
            )
        )
    envs = began.get("envs")
    params = began.get("params")
    budget = began.get("budget")
    return Ran(
        at=epic,
        flow=str(began.get("flow") or ""),
        task=str(began.get("task") or ""),
        workspace=str(began.get("workspace") or ""),
        began=str(began.get("at") or ""),
        ended=str(ended.get("at") or "") if ended else "",
        how=str(ended.get("how") or "") if ended else "",
        agents=tuple(agents),
        sessions=tuple(sessions(epic)),
        called=tuple(_calls(events)),
        resumable=bool(began.get("resumable")),
        ref=str(began.get("ref") or ""),
        envs=tuple(
            str(one)
            for one in cast("list[Any]", envs if isinstance(envs, list) else [])
        ),
        params=cast("dict[str, Any]", params) if isinstance(params, dict) else {},
        budget=cast("dict[str, Any]", budget) if isinstance(budget, dict) else None,
        picked_up=str(began.get("picked_up") or ""),
    )


def _calls(events: Sequence[dict[str, Any]]) -> list[Called]:
    """Every flow one record says it called, in the order it called them.

    Paired by the record each call was written to rather than by the order the lines are in:
    a flow written as a coroutine may have two calls going at once, and their two ends
    interleave.

    Args:
      events: The lines of one record.

    Returns:
      One apiece. A call with no end is a call that never returned -- a run killed under it
      -- and is one of them all the same.
    """
    held: list[Called] = []
    where: dict[str, int] = {}
    for said in events:
        record, flow = str(said.get("epic") or ""), str(said.get("flow") or "")
        if said.get("event") == "called":
            # Kept by the record and not by the flow: one flow called twice is two calls,
            # and each wrote to a file of its own.
            where[record] = len(held)
            held.append(
                Called(
                    flow=flow,
                    task=str(said.get("task") or ""),
                    record=record,
                    began=str(said.get("at") or ""),
                )
            )
        elif said.get("event") == "returned":
            at = where.get(record)
            if at is not None:
                held[at] = held[at]._replace(ended=str(said.get("at") or ""))
    return held


def tree(epic: Path) -> tuple[Called, ...]:
    """Every flow one run called, as the tree of calls it actually was.

    A run is one directory of records and each record says which one called it, so what a run
    was is a tree however deep it went: a flow that called a flow that called a flow, five
    of them gathered at once, the same flow called again from inside itself. Read as a list
    it would be five things one run did, and nothing would say which of them ran under which.

    Args:
      epic: The epic's directory.

    Returns:
      The calls the run itself made, in the order it made them, each carrying what it called
      in turn under `calls`. Two calls going at once are two of these, with times that
      overlap and a record apiece -- which is what tells them from one another.
    """
    return _tree(epic, _events(epic / JOURNAL), JOURNAL, frozenset())


def _tree(
    epic: Path,
    events: Sequence[dict[str, Any]],
    record: str,
    walked: frozenset[str],
) -> tuple[Called, ...]:
    """What one record of an epic called, and what each of those called in turn.

    Each record is read the once and both answers taken off that reading: what it called, and
    how it ended. A run five flows deep is that many files, and reading each of them twice
    over is the whole of the walk paid for twice.

    Args:
      epic: The epic's directory.
      events: What that record holds, already read.
      record: The record, by its name inside that directory.
      walked: The records already read on the way here, so that an epic somebody wrote by
        hand into a ring is read once rather than forever.

    Returns:
      One apiece, in the order that record called them.
    """
    walked = walked | {record}
    held: list[Called] = []
    for one in _calls(events):
        if not one.record:
            held.append(one)
            continue
        said = _events(epic / one.record)
        held.append(
            one._replace(
                calls=()
                if one.record in walked
                else _tree(epic, said, one.record, walked),
                how=_how(said),
            )
        )
    return tuple(held)


def _how(events: Sequence[dict[str, Any]]) -> str:
    """How the call written in one record ended, off the record's own closing line.

    The callee's rather than the caller's: what the caller writes is that the call returned,
    and a call that raised inside a run which carried on is a call that failed and a run that
    did not.

    Args:
      events: What that record holds, already read.

    Returns:
      What it says it ended as, and "" for a call that never ended -- a run killed under it.
    """
    return next(
        (
            str(one.get("how") or "")
            for one in reversed(events)
            if one.get("event") == "ended"
        ),
        "",
    )


def where(epic: Path, session: Session) -> Path:
    """Where one session's links are, inside the epic that opened it.

    Args:
      epic: The epic's directory.
      session: The session.

    Returns:
      The directory, which is there once that session has been logged to anything.
    """
    return epic / SESSIONS / session.name


def linked(epic: Path) -> dict[str, list[str]]:
    """What each session of one epic is linked to, as the paths the links point at.

    Args:
      epic: The epic's directory.

    Returns:
      One entry per session that has links, by the name the run gave it.
    """
    held: dict[str, list[str]] = {}
    for one in sessions(epic):
        at = where(epic, one)
        try:
            found = sorted(at.iterdir())
        except OSError:
            continue
        held[one.name] = [str(link.readlink()) for link in found if link.is_symlink()]
    return held
