"""humanize as one object, which is what a command line, an interface and a daemon all hold.

Everything humanize does is done to one workspace: what was set up to run there, the runs that
have already happened there, and the flow that is running there now. The things that are not a
workspace's -- the accounts agents run as, where flows come from -- are still reached from
here, because there is one of each and one place to ask for it.

The front door of :mod:`hmz.runtime` and reached by its name: a command line names the runtime
and holds this, a daemon holding a run apart from a terminal holds it too and the interface it
holds reaches it through that daemon, and :mod:`hmz.sdk` is the same object handed to whoever
is calling humanize from outside. One list of what humanize can do rather than one per way in.

Each of them is fetched when it is asked for and not before. A command line that only lists the
places flows come from must not load the tracer, the sandbox and every coding agent driver
there is to do it, and `hmz internal anchor` must not load any of this at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import os
    from collections.abc import Iterable, Mapping

    from hmz.coganchor.backends import Profile
    from hmz.flows import Budget, FlowParams
    from hmz.runtime.doing.accounts import Accounts
    from hmz.runtime.doing.epics import Epics
    from hmz.runtime.doing.fallbacks import Fallbacks
    from hmz.runtime.doing.flows import Flows, Flowverses
    from hmz.runtime.doing.running import Run
    from hmz.runtime.flowing import AgentDriver, EnvDriver, OutworlderDriver
    from hmz.runtime.flowing.specs import AgentSpec, EnvSpec
    from hmz.runtime.runner import Line, Runner
    from hmz.runtime.settings import Settings

__all__ = ["Hmz"]


class Hmz:
    """One workspace, and everything humanize can be asked to do in it."""

    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None:
        """Holds the workspace, and nothing else until something is asked of it.

        Args:
          workspace: The project directory this is about, or None for wherever humanize is
            being run. Kept exactly as it was given: a workspace nobody named is one that
            follows a flow which changes directory, and one that was named is the directory
            it named, spelled the way it was named.
        """
        self._workspace: str | os.PathLike[str] | None = workspace
        self._settings: Settings | None = None
        self._flows: Flows | None = None
        self._accounts: Accounts | None = None
        self._fallbacks: Fallbacks | None = None
        self._epics: Epics | None = None

    @property
    def workspace(self) -> Path:
        """The project directory this is about."""
        return Path(self._workspace) if self._workspace is not None else Path.cwd()

    @property
    def home(self) -> Path:
        """Where humanize keeps what outlives one run of one flow."""
        from hmz import home

        return home()

    @property
    def settings(self) -> Settings:
        """What humanize remembers: what was set up to run here, and what is true everywhere."""
        if self._settings is None:
            from hmz.runtime.settings import Settings

            self._settings = Settings(
                Path(self._workspace) if self._workspace is not None else None
            )
        return self._settings

    @property
    def flows(self) -> Flows:
        """The flows there are to run, and the places they come from."""
        if self._flows is None:
            from hmz.runtime.doing.flows import Flows

            self._flows = Flows()
        return self._flows

    @property
    def verses(self) -> Flowverses:
        """Where flows come from, which is the same store `/flowverses` walks."""
        return self.flows.verses

    @property
    def accounts(self) -> Accounts:
        """The accounts an agent may be run as, and what each backend runs as one."""
        if self._accounts is None:
            from hmz.runtime.doing.accounts import Accounts

            self._accounts = Accounts()
        return self._accounts

    @property
    def fallbacks(self) -> Fallbacks:
        """Where a turn goes when the place taking it cannot take it at all."""
        if self._fallbacks is None:
            from hmz.runtime.doing.fallbacks import Fallbacks

            self._fallbacks = Fallbacks()
        return self._fallbacks

    @property
    def epics(self) -> Epics:
        """The runs of this workspace that have already happened."""
        if self._epics is None:
            from hmz.runtime.doing.epics import Epics

            self._epics = Epics(self._workspace)
        return self._epics

    def backends(self) -> tuple[Profile, ...]:
        """Every coding agent CLI humanize drives, whether or not it is installed here."""
        from hmz.coganchor import backends

        return backends.profiles()

    def reports(self) -> bool:
        """Starts reporting humanize's own failures, where that has been answered yes.

        Returns:
          Whether anything is being reported. Nothing is by a machine nobody has been asked
          on: a run with nobody at a terminal is a run with nobody to ask, and silence is not
          an answer.
        """
        from hmz.runtime import telemetry

        return telemetry.start()

    def read(self, argv: list[str]) -> Line:
        """Reads an `hmz exec` line: the flow, what each role is given, the params and budget.

        Args:
          argv: The line, as `hmz exec` takes it.

        Returns:
          The line, read. Nothing is loaded: whether the flow takes what it names is asked
          of it by :meth:`runner`.

        Raises:
          SystemExit: If the line is not one argparse accepts, or an `-a`, `-e`, `-p` or `-b`
            on it cannot be read.
        """
        from hmz.runtime.runner import read_line

        return read_line(argv)

    def runner(
        self,
        flow: str | os.PathLike[str],
        *,
        agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
        envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
        params: Mapping[str, Any] | FlowParams | None = None,
        budget: Budget | Mapping[str, Any] | None = None,
        resume: bool | str | os.PathLike[str] = False,
    ) -> Runner:
        """Loads a flow and opens a driver for every role it is given, checking all of it.

        Args:
          flow: The flow, by the name it is offered under, a path, or a ref.
          agents: What each agent role runs, by role -- an `-a` spec after `<role>=`, or a
            driver -- or the specs a line read.
          envs: What each environment role is, likewise with `-e`.
          params: The flow's params, or None for its defaults.
          budget: What the run may spend; only a flow humanize ships runs without one.
          resume: Whether to pick up the newest run of it here, or the epic to pick up.

        Returns:
          The flow, loaded, with its drivers in hand and nothing started.

        Raises:
          Refused: If the flow is not there, or is given what it does not declare, or is not
            given what it needs -- before anything runs.
        """
        from hmz.runtime.runner import Runner

        return Runner(
            flow,
            agents=agents,
            envs=envs,
            params=params,
            budget=budget,
            resume=resume,
            workspace=self._workspace,
        )

    def run(
        self,
        flow: str | os.PathLike[str],
        task: str,
        *,
        agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
        envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
        params: Mapping[str, Any] | FlowParams | None = None,
        budget: Budget | Mapping[str, Any] | None = None,
        resume: bool | str | os.PathLike[str] = False,
        outworlder: OutworlderDriver | None = None,
    ) -> Run:
        """A run of one flow, loaded and ready to be started.

        Args:
          flow: The flow, by the name it is offered under, a path, or a ref.
          task: What it is to do.
          agents: What each agent role runs; see :meth:`runner`.
          envs: What each environment role is; see :meth:`runner`.
          params: The flow's params, or None for its defaults.
          budget: What the run may spend; only a flow humanize ships runs without one.
          resume: Whether to pick up the newest run of it here, or the epic to pick up.
          outworlder: Whoever is outside the run, or None for nobody.

        Returns:
          The run. Nothing has started: `run()` runs it here, `start()` on a thread.

        Raises:
          Refused: If the flow is not there, or is given what it does not declare, or is not
            given what it needs -- before anything runs.
        """
        from hmz.runtime.doing.running import Run

        return Run(
            self.runner(
                flow,
                agents=agents,
                envs=envs,
                params=params,
                budget=budget,
                resume=resume,
            ),
            task,
            outworlder=outworlder,
        )

    def exec(self, argv: list[str]) -> Any:
        """Runs the flow one `hmz exec` line names, on what it names, to its return.

        Args:
          argv: The line, as `hmz exec` takes it.

        Returns:
          What the flow returned.

        Raises:
          Refused: If the line names a flow that is not there, or gives it what it does not
            take -- which is a line that was wrong before anything ran.
          SystemExit: If the line is not one argparse accepts.
        """
        line = self.read(argv)
        # Through a run, which is the one thing a flow being driven is: whoever ran a line
        # through this and whoever built a run are then holding the same thing.
        return self.run(
            line.flow,
            line.task,
            agents=line.agents,
            envs=line.envs,
            params=line.params,
            budget=line.budget,
            resume=line.resume,
        ).run()
