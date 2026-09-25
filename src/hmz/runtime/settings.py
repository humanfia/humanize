"""What humanize remembers: what was set up to run here, and what is true everywhere.

One file under humanize's own home. Most of it is one entry per workspace -- the flow that was
last run there, and for each flow the workspace has run, what each of its roles was given, what
it was set up with and what a run of it may spend -- so a project driven by one flow on two
agents is driven by them again tomorrow, rather than falling back to the default every time it
is opened. Beside those is the handful of settings
that are not a workspace's at all, which is what `enable_sentry` is: whether humanize reports
its own failures, answered once and true wherever it is run from.

A leaf rather than part of the interface, for the reason the agents kept under a name are one:
the interface writes these and a command line has to be able to read them without loading the
interface to do it. `hmz exec` reports a crash or does not according to the same answer the
menu wrote.

Kept per flow rather than per workspace alone, because what an agent runs is only meaningful
against the flow that drives it: a flow's `reviewer` is its own, and the flow before it had no
reviewer at all. And keyed by the role each fills, so that a flow which grows a role in the
middle does not silently hand the reviewer's model to the builder.

There is nowhere else an agent is written down. What an agent is -- a CLI, an account, a model
at an effort -- is short enough now that a template kept under a name was more to hold in step
than it saved, and an agent belongs to the flow that drives it: it is set up where the flow is
set up, and remembered here against that flow's own name for it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

from hmz import home
from hmz.runtime.kept import Runs, read_back, written

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Settings"]


class Settings:
    """What one workspace was last set up to run, read once and written as it changes."""

    def __init__(self, workspace: Path | None = None) -> None:
        """Reads what was kept, if anything was.

        Args:
          workspace: Which project this is for, defaulting to this directory.
        """
        self._where = str(Path(workspace or Path.cwd()).resolve())
        self._file = home() / "settings.yaml"
        self._held = self._read()
        #: What was in the file when this read it: which workspaces, and what every setting
        #: beside them was. A write merges against this rather than against what it holds, so
        #: that an instance which has been open all session cannot put back a setting somebody
        #: has changed since -- and an absence, which is the one thing a merge cannot see for
        #: itself, is told from a value another instance has written.
        self._knew = frozenset(self._workspaces(self._held))
        self._read_as = {
            name: value for name, value in self._held.items() if name != "workspaces"
        }

    @property
    def flow(self) -> str:
        """The flow this workspace was last run with, or "" if it never has been."""
        return str(self._mine().get("flow") or "")

    @property
    def enable_sentry(self) -> bool | None:
        """Whether humanize reports its own failures, and None while nobody has been asked.

        Three answers rather than two, and the third is the one the question turns on: a
        setting that is not there is a machine nobody has put the question to yet, which is
        what makes the first start the first start. It is never written by being read, so a
        run that only ever looked at it leaves the question still to ask.

        Not a workspace's: it is about this machine and whoever is at it, so it is asked once
        and answered for every project.
        """
        said = self._held.get("enable_sentry")
        return said if isinstance(said, bool) else None

    @property
    def profiling(self) -> bool:
        """Whether a run here profiles the programs its agents start, as well as tracing them.

        A workspace's rather than this machine's: what a run costs in processes is a thing
        about the project being worked on -- a repository whose tests take a minute is a
        different question from one whose tests take an hour -- and off unless somebody says
        otherwise, since it is a sampler running for as long as the flow does.
        """
        return bool(self._mine().get("profile"))

    def profiles(self, *, on: bool) -> None:
        """Writes down whether a run here is profiled as well as traced.

        Args:
          on: What was answered.
        """
        self._mine()["profile"] = on
        self._write()

    def answers(self, *, enable_sentry: bool) -> None:
        """Writes down whether humanize reports its own failures.

        Args:
          enable_sentry: What was answered.
        """
        self._held["enable_sentry"] = enable_sentry
        self._write()

    def forget(self, workspace: str = "") -> bool:
        """Forgets what one workspace was set up to run, leaving everything else as it is.

        Args:
          workspace: Which one, defaulting to this one.

        Returns:
          Whether there was anything written down about it.
        """
        where = workspace or self._where
        workspaces = self._held.get("workspaces")
        if not isinstance(workspaces, dict) or where not in workspaces:
            return False
        del cast("dict[str, Any]", workspaces)[where]
        self._write()
        return True

    def agents(self, flow: str) -> dict[str, Runs]:
        """What each agent role of one flow was last given here.

        Args:
          flow: The flow they were driving.

        Returns:
          One agent per role, in the order they were written down, and nothing at all for a
          flow this workspace has not run -- or one whose entry this did not write, which
          reads as nothing remembered rather than as half of something.
        """
        said: dict[str, Runs] = {}
        for role, raw in self._kept(flow, "agents").items():
            runs = read_back(raw)
            if runs is None:
                return {}
            said[role] = runs
        return said

    def envs(self, flow: str) -> dict[str, str]:
        """What each environment role of one flow was last given here, as `-e` spells one.

        Args:
          flow: The flow they were for.

        Returns:
          One `<backend>@<provider>/<workdir>` per role, and nothing at all for a flow that
          was given none here -- one whose environments are the workspace it runs in.
        """
        held = self._kept(flow, "envs")
        if not all(isinstance(one, str) for one in held.values()):
            return {}
        return {role: str(one) for role, one in held.items()}

    def flows(self) -> dict[str, Any]:
        """What every flow this workspace has run was last set up with, by flow.

        Read whole rather than a flow at a time because the menu that reads it turns between
        flows: what was remembered for the one being turned to is what that page shows, and
        going back to the file for each of them would be reading it once per keypress.

        Returns:
          One entry per flow, as it was written down, and nothing at all for a workspace that
          has run none.
        """
        held = self._mine().get("flows")
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def params(self, flow: str) -> dict[str, Any]:
        """How one flow was last set up here, as its params.

        Kept beside what its roles were given and for the same reason: a flow of forty params
        is not one to answer again every morning. Read back through the flow's own model
        rather than trusted, so a param the flow has since dropped or renamed is one the model
        refuses rather than one that quietly comes back.

        Args:
          flow: The flow it was set up for.

        Returns:
          What was set, field by field, and nothing at all for a flow this workspace has
          never set up.
        """
        return self._kept(flow, "params")

    def budget(self, flow: str) -> dict[str, Any]:
        """What a run of one flow here was last said to be allowed to spend.

        Beside what the flow was set up with rather than inside it, because it is not one of
        the flow's params: it is what the person running it here decided a run of it is worth.

        Args:
          flow: The flow it was set for.

        Returns:
          The budget as JSON -- `duration`, `cost`, `output_tokens`, `graceful` -- and
          nothing at all for a flow nobody has set one for here.
        """
        return self._kept(flow, "budget")

    def _kept(self, flow: str, under: str) -> dict[str, Any]:
        """One of the things remembered about a flow here, as a mapping.

        Args:
          flow: The flow.
          under: Which of them.

        Returns:
          What was written down, and nothing at all where it was not or is not a mapping.
        """
        flows: dict[str, Any] = self._mine().get("flows") or {}
        kept = flows.get(flow)
        if not isinstance(kept, dict):
            return {}
        held = cast("dict[str, Any]", kept).get(under)
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def remember(
        self,
        flow: str,
        agents: Mapping[str, Runs],
        envs: Mapping[str, str] | None = None,
        params: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
    ) -> None:
        """Writes down what this workspace is set up to run, so that it opens that way.

        Args:
          flow: The flow to run.
          agents: What each of its agent roles runs, by role.
          envs: What each of its environment roles is given, as `-e` spells one, or None to
            leave whatever was kept for it as it was -- choosing the agents again is not a
            way of forgetting where they work.
          params: What the flow itself was set up with, or None to leave whatever was kept.
          budget: What a run of it here may spend, as JSON, or None to leave whatever was
            kept. The same asymmetry as the rest and for the same reason: the flow's whole
            entry is replaced below, so what is not handed in has to be read back or it is
            forgotten. A value that is empty erases it.
        """
        mine = self._mine()
        mine["flow"] = flow
        kept: dict[str, Any] = {
            "agents": {role: written(runs) for role, runs in agents.items()}
        }
        for under, given in (("envs", envs), ("params", params), ("budget", budget)):
            held = dict(given) if given is not None else self._kept(flow, under)
            if held:
                kept[under] = held
        mine.setdefault("flows", {})[flow] = kept
        self._write()

    def _mine(self) -> dict[str, Any]:
        """This workspace's entry, made if it is not there and replaced if it is not one."""
        if not isinstance(self._held.get("workspaces"), dict):
            self._held["workspaces"] = {}
        workspaces = cast("dict[str, Any]", self._held["workspaces"])
        if not isinstance(workspaces.get(self._where), dict):
            workspaces[self._where] = {}
        return cast("dict[str, Any]", workspaces[self._where])

    @staticmethod
    def _workspaces(held: dict[str, Any]) -> dict[str, Any]:
        """The workspaces one reading of the file holds, which is nothing where it holds none."""
        found = held.get("workspaces")
        return cast("dict[str, Any]", found) if isinstance(found, dict) else {}

    def _read(self) -> dict[str, Any]:
        """Everything the file holds, which is nothing at all when it cannot be read.

        A settings file that is missing, unreadable, or not what this writes is a workspace
        with nothing remembered about it -- never a reason not to open.
        """
        try:
            held = yaml.safe_load(self._file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return {}
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def _write(self) -> None:
        """Puts the file back, keeping what this one was not holding.

        Read again and merged rather than dumped over: this holds what it read when it was
        made, and two of these are alive at once wherever a menu writes a setting while the
        interface goes on remembering flows -- so a plain dump would put back a file missing
        whatever the other one had written since. What this one is holding wins for the
        workspace it is about and for the settings it has answered; everything else is
        whatever is on disk now.

        Whole and then moved into place, as every other file humanize writes is: one read
        while it is being written is the old one or the new one and never half of each.

        A file nobody can write is not a reason to stop: what it holds is a convenience, and
        an interface that refused to run because it could not remember would be worse than
        one that forgets.
        """
        held = self._read()
        for name, value in self._held.items():
            # Only what this instance has actually changed: one that read `enable_sentry` as
            # true an hour ago and has been remembering flows ever since must not put that
            # back over the no somebody answered in the meantime.
            if name != "workspaces" and value != self._read_as.get(name):
                held[name] = value
        workspaces = self._workspaces(held)
        held["workspaces"] = workspaces
        mine = self._workspaces(self._held)
        workspaces.update(mine)
        # And what this one has forgotten goes from the file too, which is the one thing a
        # merge cannot see for itself: an absence here is either a workspace this instance
        # took away or one another instance has written since, and only what this instance
        # read when it opened tells them apart.
        for gone in self._knew - set(mine):
            workspaces.pop(gone, None)
        self._held = held
        self._knew = frozenset(workspaces)
        self._read_as = {
            name: value for name, value in held.items() if name != "workspaces"
        }
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            said = yaml.safe_dump(held, sort_keys=False, allow_unicode=True)
            # Beside it under a name nothing else will pick: two `hmz` running at once both
            # write this file, and a fixed `.new` between them is one of them finding its own
            # half-written file moved away underneath it.
            handle, beside = tempfile.mkstemp(
                dir=self._file.parent, prefix=f".{self._file.name}.", suffix=".new"
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as writing:
                    writing.write(said)
                Path(beside).replace(self._file)
            except OSError:
                Path(beside).unlink(missing_ok=True)
                raise
        except (OSError, yaml.YAMLError):
            return
