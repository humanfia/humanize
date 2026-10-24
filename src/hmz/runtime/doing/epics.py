"""The runs of a workspace that have already happened, and what is gathered out of them.

One run is one epic: a directory holding what happened, the sessions it opened, and the journal
of a flow that says it can be picked up. What is written down as a run happens is
:mod:`hmz.runtime.epic`; reading the backends' own logs back is :mod:`hmz.runtime.tracing`;
packaging one whole run up to send somewhere, and reading one back in, is
:mod:`hmz.runtime.exporting`. All three are asked
here, so that whatever is listing the runs -- a command line, the interface's own `/epics` -- asks
one object about the one workspace it is about.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    from collections.abc import Iterable, Mapping
    from typing import Any

    from hmz.runtime.epic import Called, Ran, Session
    from hmz.runtime.tracing.timeline import Timeline

__all__ = ["Epics"]


class Epics:
    """Every run of one workspace, newest last, and what can be read back out of one."""

    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None:
        """Holds the workspace whose runs these are.

        Args:
          workspace: The project directory the runs were run in, or None for wherever
            Humanize is being run. None is kept as None rather than filled in: naming
            sessions without a workspace collects them wherever they were recorded, and a
            workspace here would narrow that to whatever directory somebody was standing in.
        """
        self._workspace = Path(workspace) if workspace is not None else None

    def under(self) -> Path:
        """The directory this workspace's runs are kept in."""
        from hmz.runtime.epic import under

        return under(self._workspace)

    def all(self) -> list[Path]:
        """Every run of this workspace, oldest first, which is the order they are named in."""
        from hmz.runtime.epic import epics

        return epics(self._workspace)

    def every(self) -> list[Path]:
        """Every run on this machine, of every workspace, oldest first."""
        from hmz.runtime.epic import every

        return every()

    def read(self, epic: Path) -> Ran | None:
        """What one run was: when, which flow, on what, how it went, and what it opened."""
        from hmz.runtime.epic import read

        return read(epic)

    def tree(self, epic: Path) -> tuple[Called, ...]:
        """Every flow one run called, as the tree of calls it was: each call's under it."""
        from hmz.runtime.epic import tree

        return tree(epic)

    def sessions(self, epic: Path) -> list[Session]:
        """Every session one run opened, across each of the records it holds."""
        from hmz.runtime.epic import sessions

        return sessions(epic)

    def opened(self, epic: Path) -> dict[str, list[str]]:
        """What each agent of one run opened, by the name the run knew that agent as."""
        from hmz.runtime.epic import opened

        return opened(epic)

    def resumed(self, flow: str) -> Path | None:
        """The newest run of one flow here that can be picked up, which `--resume` picks up.

        Args:
          flow: The flow, by its canonical ref or as it was named when it was run.
        """
        from hmz.runtime.epic import resumed

        return resumed(flow, self._workspace)

    def picks_up(self, epic: Path) -> bool:
        """Whether a run can be picked up from one epic: it kept a journal, and wrote in it."""
        from hmz.runtime.epic import picks_up

        return picks_up(epic)

    def foreign(self, epic: Path) -> str:
        """Why a run imported from another machine cannot be picked up here, or "" for none."""
        from hmz.runtime.epic import foreign

        return foreign(epic)

    def going(self, epic: Path) -> bool:
        """Whether one epic's run is still going, in this process or any other."""
        from hmz.runtime.epic import going

        return going(epic)

    def ending(self, ran: Ran) -> str:
        """How one run went, as a list of them is found by: `running` while it is still going."""
        from hmz.runtime.epic import ending, going

        return ending(ran, going=not ran.how and going(ran.at))

    def state(self, epic: Path, flow: str = "") -> dict[str, Any]:
        """What a resumable flow kept in one run: the run's own flow, or one it called by ref."""
        from hmz.runtime.epic import state

        return state(epic, flow)

    def traced(
        self,
        epic: Path,
        *,
        output: str | os.PathLike[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        """Gathers what one run left behind into a trace of that run.

        A trace of a run holds the sessions that run opened and no others, asked for by the
        ids the run wrote down rather than by the directory it ran in: a directory is run in
        over and over, and a flow that worked in a machine's mirror logged its sessions under
        one this has never heard of. And it goes with the run: the sessions it points at and
        the state it left are already there.

        Args:
          epic: The run, by the directory it is written in.
          output: Where to write it, or None for the run's own `traces/`, named after the
            moment it was collected so that collecting twice keeps both.
          start: The earliest session time to include, in any wording dateparser understands.
          end: The latest.

        Returns:
          Where it was written, and the trace itself.
        """
        import datetime

        from hmz.runtime.epic import TRACES
        from hmz.runtime.tracing.profile import FLOW_PROFILE, PROFILE

        agents = self.opened(epic)
        where = Path(output) if output is not None else None
        if where is None:
            stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
            where = epic / TRACES / f"{stamp}.trace.json"
        where.parent.mkdir(parents=True, exist_ok=True)
        # No workspace at all: the ids are exactly this run's, wherever they were logged.
        document = Epics().trace(
            sessions=[ident for ids in agents.values() for ident in ids],
            agents=agents or None,
            output=where,
            start=start,
            end=end,
            profile=epic / PROFILE,
            flow_profile=epic / FLOW_PROFILE,
            kept=self._kept(epic),
        )
        return where, document

    def transcripts(self, epic: Path) -> list[dict[str, Any]]:
        """What each session of one run said and did, read back out of the logs it kept.

        Gathered as a trace of the run is, somewhere nothing keeps it: reading a run must not
        leave a file in it. Slow -- every log the run kept is read.

        Args:
          epic: The run, by the directory it is written in.

        Returns:
          Each session that did anything, in the order it first did: its key in the trace --
          `<cli>:<id>` -- the agent it was of as the trace names agents, and its actions --
          turns, model calls, tools, words and the rest -- each with when it started, how
          long it took, and what it carried.
        """
        import tempfile

        from hmz import machine

        with tempfile.TemporaryDirectory(dir=machine()) as scratch:
            _, document = self.traced(epic, output=Path(scratch) / "trace.json")
        return _sessions_of(document)

    def timeline(self, epic: Path) -> Timeline:
        """Lays one run out as an Exomyth timeline: its sessions, flows, Python and programs.

        Gathered from exactly what a trace of the run is gathered from, and written nowhere:
        a timeline is drawn and thrown away, where a trace is a file somebody keeps.

        Args:
          epic: The run, by the directory it is written in.

        Returns:
          The document a viewer draws, and what each of its slices carried, by id.
        """
        from hmz.runtime.tracing import collector, profile, timeline

        agents = self.opened(epic)
        # No workspace at all: the ids are exactly this run's, wherever they were logged.
        sessions = collector.gather(
            None,
            sessions=[ident for ids in agents.values() for ident in ids],
            agents=agents or None,
            kept=self._kept(epic),
        )
        return timeline.build(
            sessions,
            ran=self.read(epic),
            calls=self.tree(epic),
            profiled=profile.read(epic / profile.PROFILE),
            sampled=profile.samples(epic / profile.FLOW_PROFILE),
        )

    def _kept(self, epic: Path) -> list[Path]:
        """Where one run kept its sessions, which is where a trace of it reads them.

        Its own directory for them, and wherever else one of them says it was kept by
        Humanize -- an agent that had kept sessions in another run before this one was handed
        it goes on keeping them there. Not a CLI's own home, which is read whatever is said
        here.
        """
        from hmz import home
        from hmz.runtime.epic import SESSIONS
        from hmz.runtime.epic import where as kept_in

        return sorted(
            {epic / SESSIONS}
            | {
                at.parent
                for one in self.sessions(epic)
                if (at := kept_in(epic, one)).name == one.backend
                and at.is_relative_to(home())
            }
        )

    def bundled(
        self,
        epic: Path,
        *,
        output: str | os.PathLike[str],
        transcript: str | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        """Packages one whole run up as one archive, to send to somebody who was not there.

        Everything the run wrote and everything its sessions were logged to, which the epic
        keeps itself. Credentials are struck out of every byte of it.

        Args:
          epic: The run, by the directory it is written in.
          output: Where to write it: a file, or a directory to write it into under its own
            name.
          transcript: A screen that went with this run, for a caller that has one, or None
            -- which is what a run exported out of the list of them goes in as, that run not
            being the one on the screen.

        Returns:
          Where it was written, and the manifest as it was written there -- which is what
          says what went in, rather than a second reading of the run afterwards.
        """
        from hmz.runtime.exporting import bundle

        return bundle(epic, output, transcript=transcript)

    def imported(self, archive: str | os.PathLike[str]) -> Path:
        """Reads one bundle back in, as an epic of the workspace it says it ran in.

        Which is wherever that is, rather than this workspace: a run is kept under where it
        ran, and an import is the run it was.

        Args:
          archive: The bundle, a `.hmzepic`.

        Returns:
          Where the epic now is.

        Raises:
          ValueError: For a file that is not a bundle, or holds anything outside the one
            epic it should, and for an epic already here.
        """
        from hmz.runtime.exporting import unbundle

        return unbundle(archive)

    def trace(
        self,
        *,
        sessions: str | Iterable[str] | None = None,
        agents: Mapping[str, Iterable[str]] | None = None,
        output: str | os.PathLike[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        profile: str | os.PathLike[str] | None = None,
        flow_profile: str | os.PathLike[str] | None = None,
        kept: Iterable[str | os.PathLike[str]] | None = None,
    ) -> dict[str, Any]:
        """Gathers what a run left behind into one Chrome trace.

        Args:
          sessions: Which sessions to collect, or None for every session of the workspace.
            An empty iterable is no sessions rather than every session, which is what a trace
            of a run that opened none holds.
          agents: What each agent of a flow opened, so that a loop of one-shot sessions reads
            as one agent rather than a hundred.
          output: Where to write it, or None to gather it without writing.
          start: The earliest session time to include, in any wording dateparser understands.
          end: The latest.
          profile: Where the run's profile of its programs was written, for a run that
            profiled them.
          flow_profile: Where its profile of the flow's own Python was, likewise.
          kept: Where Humanize kept the sessions to read besides each CLI's own home, a
            directory per CLI inside each, or None for everywhere it keeps them: every
            epic's, an agent no run was driving keeping its own in its CLI's home.

        Returns:
          The trace, as the object that was written.
        """
        from hmz import home
        from hmz.runtime.epic import SESSIONS
        from hmz.runtime.tracing.collector import collect

        if kept is None:
            # Where :attr:`hmz.coganchor.agents.AgentBase.keeps` puts them: each run's own --
            # of this workspace, where there is one.
            runs = self.under() if self._workspace is not None else home() / "epics"
            within = "*" if self._workspace is not None else "*/*"
            kept = sorted(runs.glob(f"{within}/{SESSIONS}"))
        return collect(
            self._workspace,
            sessions=sessions,
            agents=agents,
            output=output,
            start=start,
            end=end,
            profile=profile,
            flow_profile=flow_profile,
            kept=kept,
        )


def _sessions_of(document: dict[str, Any]) -> list[dict[str, Any]]:
    """What each session of a trace said and did, in the order it did it.

    Args:
      document: The trace, as :meth:`Epics.traced` gathers one.

    Returns:
      Each session that did anything, as :meth:`Epics.transcripts` says them.
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
