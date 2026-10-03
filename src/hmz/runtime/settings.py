"""What humanize remembers: what was set up to run here, and what is true everywhere.

One file under humanize's own home. Most of it is one entry per workspace -- the flow that was
last run there, and for each flow the workspace has run, what each of its roles was given, what
it was set up with, what a run of it may spend and whether that run is profiled -- so a project
driven by one flow on two agents is driven by them again tomorrow, rather than falling back to
the default every time it is opened. Beside those is the handful of settings
that are not a workspace's at all, which is what `enable_sentry` is: whether humanize reports
its own failures, answered once and true wherever it is run from -- and `details`, whether the
interface shows the working of each turn.

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

import contextlib
import copy
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

from hmz import home
from hmz.runtime.kept import Runs, read_back, written

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping

__all__ = ["Settings"]

#: Where the file says how it spells an environment, which every write writes: see
#: :data:`hmz.coganchor.machines.store.SPELLING`.
_SPELLING = "spelling"

#: How long, in seconds, a write waits for another writer to be done before going ahead
#: without it. A write takes milliseconds, and seconds on a disk busy enough that fsync
#: queues; this is for a writer that has stopped, not for one that is slow.
_PATIENCE = 30.0


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
        if _SPELLING not in self._held and _respelled(copy.deepcopy(self._held)):
            # Once, for every workspace, and marked so as every write is: `ssh@gpu/x` kept
            # from here on is the runtime `gpu`, never read again as a host nobody saved.
            self._write(_respell)

    @property
    def flow(self) -> str:
        """The flow this workspace was last run with, or "" if it never has been."""
        return str(self._here().get("flow") or "")

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
    def details(self) -> bool:
        """Whether the interface shows the working of each turn: its tool calls and thinking.

        This machine's rather than a workspace's, as the reporting question is: it is how
        whoever is at it likes to watch a flow, whichever project the flow is in. Off unless
        somebody says otherwise, since what a flow is watched for is where it has got to.
        """
        return self._held.get("details") is True

    def detailing(self, *, on: bool) -> None:
        """Writes down whether the interface shows the working of each turn.

        Args:
          on: What was answered.
        """
        self._sets("details", on)

    @property
    def btw(self) -> str:
        """The agent `/btw` asks about a whole flow, as `cli@provider/model:effort`.

        This machine's rather than a workspace's, as `enable_sentry` is: which agent answers a
        side question is a matter of taste and of accounts, and neither changes between
        projects. "" while nobody has chosen one, which is the flow's first agent.
        """
        said = self._held.get("btw")
        return said if isinstance(said, str) else ""

    @btw.setter
    def btw(self, spec: str) -> None:
        """Writes down which agent `/btw` asks, or "" to go back to the flow's first."""
        self._sets("btw", spec)

    def answers(self, *, enable_sentry: bool) -> None:
        """Writes down whether humanize reports its own failures.

        Args:
          enable_sentry: What was answered.
        """
        self._sets("enable_sentry", enable_sentry)

    def forget(self, workspace: str = "") -> bool:
        """Forgets what one workspace was set up to run, leaving everything else as it is.

        Args:
          workspace: Which one, defaulting to this one.

        Returns:
          Whether there was anything written down about it.
        """
        where = workspace or self._where
        found: list[bool] = []

        def change(held: dict[str, Any]) -> None:
            workspaces = self._workspaces(held)
            found.append(where in workspaces)
            workspaces.pop(where, None)

        self._write(change)
        return any(found)

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
          One `<backend>[@<provider>][/<workdir>]` per role, and nothing at all for a flow
          that was given none here -- one whose environments are the workspace it runs in.
          One kept the way `-e` spelled it before an `@` was a provider's alone was written
          again as it is spelled now when the file was first read.
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
        held = self._here().get("flows")
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

    def profile(self, flow: str) -> bool:
        """Whether a run of one flow here was last said to be profiled as well as traced.

        Kept beside the budget and for the reason it is kept: it is a thing about a run of the
        flow rather than one of the flow's params, decided by whoever runs it here -- a flow
        whose tests take an hour is one somebody wants to see the processes of every time.

        Args:
          flow: The flow it was said for.

        Returns:
          Whether it was, and False for a flow nobody has said it of here.
        """
        return self._flow(self._here(), flow).get("profile") is True

    def _kept(
        self, flow: str, under: str, entry: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """One of the things remembered about a flow here, as a mapping.

        Args:
          flow: The flow.
          under: Which of them.
          entry: The workspace's entry to look in, defaulting to the one this holds.

        Returns:
          What was written down, and nothing at all where it was not or is not a mapping.
        """
        held = self._flow(self._here() if entry is None else entry, flow).get(under)
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    @staticmethod
    def _flow(entry: dict[str, Any], flow: str) -> dict[str, Any]:
        """What one workspace's entry holds about one flow, and nothing where it holds none."""
        flows = entry.get("flows")
        kept = (
            cast("dict[str, Any]", flows).get(flow) if isinstance(flows, dict) else None
        )
        return cast("dict[str, Any]", kept) if isinstance(kept, dict) else {}

    def remember(
        self,
        flow: str,
        agents: Mapping[str, Runs],
        envs: Mapping[str, str] | None = None,
        params: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        *,
        profile: bool | None = None,
    ) -> None:
        """Writes down what this workspace is set up to run, so that it opens that way.

        What is not handed in is read back out of the file as it is when this writes, not out
        of what this read when it was made: another `hmz` in this workspace may have set the
        flow's params since, and choosing the agents here is not a way of putting back the
        ones it replaced.

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
          profile: Whether a run of it here is profiled as well as traced, or None to leave
            whatever was kept, for the same reason. Written down only where it is on: off is
            what a flow nobody has said anything of is.
        """

        def change(held: dict[str, Any]) -> None:
            mine = self._mine(held)
            mine["flow"] = flow
            kept: dict[str, Any] = {
                "agents": {role: written(runs) for role, runs in agents.items()}
            }
            for under, given in (
                ("envs", envs),
                ("params", params),
                ("budget", budget),
            ):
                one = (
                    dict(given) if given is not None else self._kept(flow, under, mine)
                )
                if one:
                    kept[under] = one
            profiled = (
                profile
                if profile is not None
                else self._flow(mine, flow).get("profile") is True
            )
            if profiled:
                kept["profile"] = True
            flows = mine.get("flows")
            if not isinstance(flows, dict):
                flows = mine["flows"] = {}
            cast("dict[str, Any]", flows)[flow] = kept

        self._write(change)

    def _here(self) -> dict[str, Any]:
        """This workspace's entry as this holds it, and nothing where it has none."""
        found = self._workspaces(self._held).get(self._where)
        return cast("dict[str, Any]", found) if isinstance(found, dict) else {}

    def _mine(self, held: dict[str, Any]) -> dict[str, Any]:
        """This workspace's entry in one reading of the file, made if it is not there.

        Args:
          held: The reading, which is changed where it has no entry or one that is not one.
        """
        if not isinstance(held.get("workspaces"), dict):
            held["workspaces"] = {}
        workspaces = cast("dict[str, Any]", held["workspaces"])
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
        held = self._reading()
        return {} if held is None else held

    def _reading(self) -> dict[str, Any] | None:
        """Everything the file holds, and None where there is one that cannot be read as one.

        Told apart from a file that is not there, which holds nothing, because a write makes
        its change to what the file holds: one somebody left half-edited is not a reason to
        write it back as nothing but that change.
        """
        try:
            said = self._file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError:
            return None
        try:
            held = yaml.safe_load(said)
        except yaml.YAMLError:
            return None
        if held is None:
            return {}
        return cast("dict[str, Any]", held) if isinstance(held, dict) else None

    def _sets(self, name: str, value: object) -> None:
        """Writes down one of the settings that are not a workspace's.

        Args:
          name: Which.
          value: What it is now.
        """

        def change(held: dict[str, Any]) -> None:
            held[name] = value

        self._write(change)

    def _write(self, change: Callable[[dict[str, Any]], None]) -> None:
        """Makes one change to the file, and to nothing else in it.

        Two of these are alive at once wherever a menu writes a setting while the interface
        goes on remembering flows, and wherever two `hmz` share a home -- so what this holds
        is never written back. The file is read again under a lock, the change is made to
        what it holds now, and that is what goes back: a setting, a workspace or a flow some
        other holder wrote since this one read the file is still there afterwards, and one
        this holder did not touch is never put back as it was an hour ago. What this holds
        from then on is the file as it wrote it.

        The lock is a `flock` on a file beside it, which the kernel lets go of however the
        process ends. Where the file cannot be written the change is made to what this holds
        instead, so that it is remembered for as long as this is.

        Whole and then moved into place, as every other file humanize writes is: one read
        while it is being written is the old one or the new one and never half of each.

        A file nobody can write is not a reason to stop: what it holds is a convenience, and
        an interface that refused to run because it could not remember would be worse than
        one that forgets.

        Args:
          change: What to do to a reading of the file, in place. It may be made twice: to
            the file as it is now, and -- where that could not be written -- to what this
            holds.
        """
        with self._locked():
            fresh = self._reading()
            # One that cannot be read is written over, as it always was -- with what this
            # holds rather than with nothing but the change.
            held = copy.deepcopy(self._held) if fresh is None else fresh
            change(held)
            held[_SPELLING] = _spelling()
            try:
                self._writes(yaml.safe_dump(held, sort_keys=False, allow_unicode=True))
            except (OSError, yaml.YAMLError):
                # Remembered for as long as this is, which is all it can be.
                change(self._held)
                return
            self._held = held

    @contextlib.contextmanager
    def _locked(self) -> Generator[None]:
        """Holds the lock every writer of the file takes, for as long as the block runs.

        Where it cannot be had the block runs anyway, which is a write that might meet
        another rather than one that never happens: a home that cannot be written, a lock
        file somebody else made that this cannot open, a filesystem that has no `flock`, or
        a writer that has held it for longer than anybody at an interface should wait -- one
        stopped with ctrl-z halfway through a write is holding it for as long as it is
        stopped.
        """
        import fcntl

        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            # Read-only, which `flock` needs no more than, so that one another user made is
            # still one this can take.
            fd = os.open(
                self._file.with_name(f".{self._file.name}.lock"),
                os.O_CREAT | os.O_RDONLY | os.O_CLOEXEC,
                0o600,
            )
        except OSError:
            yield
            return
        try:
            waited = time.monotonic() + _PATIENCE
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    if time.monotonic() < waited:
                        time.sleep(0.01)
                        continue
                except OSError:
                    pass
                break
            yield
        finally:
            os.close(fd)  # which lets go of the lock too

    def _writes(self, said: str) -> None:
        """Puts the file in place whole, keeping the mode it already has.

        Args:
          said: What it is to hold.

        Raises:
          OSError: If it cannot be written, with nothing of the attempt left beside it.
        """
        # Beside it under a name nothing else will pick: a fixed `.new` between two writers
        # is one of them finding its own half-written file moved away underneath it.
        # `mkstemp` makes it `0600`, which is what a new one is left at.
        handle, beside = tempfile.mkstemp(
            dir=self._file.parent, prefix=f".{self._file.name}.", suffix=".new"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as writing:
                with contextlib.suppress(FileNotFoundError):
                    os.fchmod(handle, stat.S_IMODE(self._file.stat().st_mode))
                writing.write(said)
                writing.flush()
                os.fsync(handle)
            Path(beside).replace(self._file)
        except BaseException:
            Path(beside).unlink(missing_ok=True)
            raise


def _spelling() -> int:
    """How an environment written now is spelled."""
    from hmz.coganchor.machines.store import SPELLING

    return SPELLING


def _respelled(held: dict[str, Any]) -> bool:
    """Spells every environment in one reading of the file as `-e` spells one now.

    What was kept before an `@` was a provider's alone -- `local@/x`, `docker@local/x`, an ssh
    host nobody saved out of brackets -- in every workspace, and nothing else.

    Args:
      held: The reading, which is changed in place.

    Returns:
      Whether anything was.
    """
    kept = [
        envs
        for entry in _mapping(held.get("workspaces")).values()
        for flow in _mapping(_mapping(entry).get("flows")).values()
        if (envs := _mapping(_mapping(flow).get("envs")))
    ]
    if not kept:
        return False  # nothing to read, and nothing of `-e` to load to read it
    from hmz.coganchor.machines.store import respelled

    changed = False
    for envs in kept:
        for role, spec in envs.items():
            if isinstance(spec, str) and (now := respelled(spec)) != spec:
                envs[role] = now
                changed = True
    return changed


def _respell(held: dict[str, Any]) -> None:
    """:func:`_respelled`, as a change :meth:`Settings._write` makes."""
    _respelled(held)


def _mapping(held: object) -> dict[str, Any]:
    """One value of the file as the mapping it is, and an empty one where it is not one."""
    return cast("dict[str, Any]", held) if isinstance(held, dict) else {}
