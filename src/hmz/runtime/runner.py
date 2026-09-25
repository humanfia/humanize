"""What starts a flow: the line naming it, the drivers it is handed, and the run written down.

The line is read here rather than beside the command that carries it out, because the terminal
interface starts a flow from the same parts: a flow, what each of its agent and environment
roles is given, its params, and what the run may spend. A reader that lived in the command line
would be one the interface had to reach up into.

A run is four steps, and the first three refuse before anything runs. The flow is loaded and
what it declares is read (:mod:`hmz.runtime.flowing.finding`); what each role is given is
checked against that declaration and opened as a driver
(:func:`~hmz.runtime.flowing.harnesses.open_agent`,
:func:`~hmz.runtime.flowing.environments.open_env`) -- which starts no CLI and reaches no
machine; each environment given is probed, which does reach it; and then the flow is run by
:func:`~hmz.runtime.flowing.engine.run_flow`, written down as it goes into an epic that also
holds the engine's journal of a flow that can be picked up. What refuses a run before it has
started is :class:`Refused`, which a command line reports as a line to correct.

What a flow is, and everything it is handed, is :mod:`hmz.flows` and the engine behind it.
Nothing a flow itself reaches for is here: a flow names one module of humanize's, and it is not
this one.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, cast

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterable, Mapping

    from hmz.coganchor.agents import AgentBase, SessionBase
    from hmz.flows import Budget, FlowParams, Usage
    from hmz.runtime.flowing import (
        AgentDriver,
        Declaration,
        EnvDriver,
        FlowImpl,
        LiveCall,
        OutworlderDriver,
        SessionHandle,
    )
    from hmz.runtime.flowing.harnesses import Listener
    from hmz.runtime.flowing.specs import AgentSpec, EnvSpec

    from .epic import Drove, Epic

__all__ = ["Line", "Refused", "Runner", "read_line"]

#: What is told of each session a run opens, as it is opened: the role it was opened for, and
#: the coganchor agent and conversation behind it.
type Opened = Callable[[str, AgentBase, SessionBase], None]


class Refused(ValueError):  # noqa: N818 -- named for what happened, as the flow API names its own
    """A run refused before anything of it ran: a line, or a setup, to correct.

    The message says what, in words; the exception it was refused for is its cause.
    """


class Line(NamedTuple):
    """An `hmz exec` line, read.

    Attributes:
      flow: The flow, as the line named it.
      task: What it is to do.
      agents: What each agent role is given, in the order the line wrote them.
      envs: What each environment role is given, likewise.
      params: Each param as the line wrote it, which the flow's own model reads.
      budget: What the run may spend, or None where the line said nothing.
      resume: Whether to pick up the newest run of the flow here that can be.
      as_json: Whether a program is reading the run rather than a person.
    """

    flow: str
    task: str
    agents: tuple[AgentSpec, ...] = ()
    envs: tuple[EnvSpec, ...] = ()
    params: dict[str, str] = {}  # noqa: RUF012 -- a NamedTuple's default, never written to
    budget: Budget | None = None
    resume: bool = False
    as_json: bool = False


def read_line(argv: list[str]) -> Line:
    """Reads an `hmz exec` line.

    Only the line: which roles the flow has, and whether it needs a budget, are asked of the
    flow by :class:`Runner`, so that `--help` loads no flow and pays for no driver.

    Args:
      argv: What followed the command name.

    Returns:
      The line.

    Raises:
      SystemExit: For a line that is not one, as argparse rejects it -- an unknown flag, no
        flow or task, or an `-a`, `-e`, `-p` or `-b` that cannot be read.
    """
    import argparse

    from hmz.coganchor import backends

    parser = argparse.ArgumentParser(
        prog="hmz exec", description="Run an agent flow in this directory."
    )
    parser.add_argument(
        "-f",
        "--flow",
        required=True,
        metavar="FLOW",
        help="the flow to run: one humanize ships or a flowverse holds, by name, a directory "
        "or file of your own, or a git+URL#flow ref; `<flow>:<name>` for another flow of "
        "the same module",
    )
    parser.add_argument(
        "-a",
        "--agents",
        action="append",
        default=[],
        metavar="ROLE=SPEC[,...]",
        help="what an agent role runs: ROLE=CLI[@PROVIDER]/MODEL:EFFORT, several to one "
        "option separated by commas, the option repeated as often as suits. CLI is one of "
        f"{', '.join(sorted(one.name for one in backends.profiles()))}",
    )
    parser.add_argument(
        "-e",
        "--envs",
        action="append",
        default=[],
        metavar="ROLE=SPEC[,...]",
        help="where an environment role is: ROLE=local@/abs/path or "
        "ROLE=ssh@[user@]host[:port]/abs/path (ssh@host/~/path under the login's home). "
        "A role the runtime fills -- the workspace -- is never named",
    )
    parser.add_argument(
        "-p",
        "--params",
        action="append",
        default=[],
        metavar="KEY=VALUE[,...]",
        help="a param of the flow; a value is read as the param's type, or as JSON",
    )
    parser.add_argument(
        "-b",
        "--budget",
        action="append",
        default=[],
        metavar="KEY=VALUE[,...]",
        help="what the run may spend: duration=1h30m, cost=5 (USD), output_tokens=200k, "
        "graceful=false to stop a turn mid-way. Required, except for chat",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="pick up the newest run of this flow here, for a flow that can be picked up",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="write the run as NDJSON on stdout -- one object per thing an agent says, "
        "flushed as it is said -- for a program to read instead of a person",
    )
    parser.add_argument(
        "task",
        help="what the flow is to do, after -- if it starts with a dash",
    )
    args = parser.parse_args(argv)

    from hmz.runtime.flowing.specs import (
        SpecError,
        parse_agents,
        parse_budget,
        parse_envs,
        parse_params,
    )

    try:
        return Line(
            flow=args.flow,
            task=args.task,
            agents=tuple(parse_agents(args.agents)),
            envs=tuple(parse_envs(args.envs)),
            params=parse_params(args.params),
            budget=parse_budget(args.budget) if args.budget else None,
            resume=args.resume,
            as_json=args.as_json,
        )
    except SpecError as bad:
        parser.error(str(bad))


class Runner:
    """A flow, loaded, with a driver for every role it was given and everything checked.

    Nothing has run once one is made, and nothing has been started: an agent's CLI is reached
    when its first session opens, and an environment's machine when it is probed, which
    :meth:`arun` does before the flow is called.
    """

    def __init__(
        self,
        flow: str | os.PathLike[str],
        *,
        agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
        envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
        params: Mapping[str, Any] | FlowParams | None = None,
        budget: Budget | Mapping[str, Any] | None = None,
        resume: bool | str | os.PathLike[str] = False,
        workspace: str | os.PathLike[str] | None = None,
    ) -> None:
        """Loads the flow and checks what it is given against what it declares.

        Args:
          flow: The flow, as `-f` names one.
          agents: What each agent role runs: an `-a` spec after `<role>=` or a driver, by
            role, or the specs a line read. A role the runtime fills -- an `Outworlder` --
            is never given.
          envs: What each environment role is: an `-e` spec after `<role>=` or a driver, by
            role, or the specs a line read. A `LocalEnv` role is never given; it is the
            workspace.
          params: The flow's params, as its model or as a mapping of values -- strings from
            `-p` among them -- or None for its defaults.
          budget: What the run may spend. Only a flow humanize ships may be run without one,
            under `Budget(cost=inf)`.
          resume: Whether to pick up the newest run of this flow in the workspace that can
            be picked up, or the epic to pick up.
          workspace: Where the run happens, defaulting to this directory.

        Raises:
          Refused: For a flow that cannot be loaded; a role given that it does not declare,
            that the runtime fills, or that is given twice; a required role left out; an
            agent that is not the harness its role names or cannot do what its role asks; a
            spec a driver cannot be made for; params the flow does not take; no budget; and a
            run to pick up that is not there or of a flow that cannot be picked up.
        """
        from hmz.flows import Budget, FlowException
        from hmz.runtime.flowing import builtin, resolved

        self._named = str(flow)
        self._workspace = Path(workspace) if workspace is not None else Path.cwd()
        try:
            impl = resolved(self._named)
            declared = impl.describe()
        except FlowException as why:
            raise Refused(str(why)) from why
        self._impl: FlowImpl = impl
        self._declared = declared
        agents_given, self._specs = self._agents_of(agents)
        envs_given, self._places = self._envs_of(envs)
        try:
            self._params = impl.params_of({} if params is None else params)
        except FlowException as why:
            raise Refused(str(why)) from why
        if budget is None:
            if not builtin(impl):
                raise Refused(
                    f"{self._named}: a run is given a budget -- -b duration=...,cost=...,"
                    "output_tokens=... -- and this one was given none"
                )
            budget = Budget(cost=math.inf)
        self._budget = budget if isinstance(budget, Budget) else _budget(budget)
        self._picked_up = self._picks_up(resume)
        # Made last, once everything that could refuse the run has had its say: a driver
        # starts nothing as it is made, and none is made for a run that is refused.
        self._agents = _agent_drivers(agents_given)
        self._envs = _env_drivers(envs_given)
        self._recorder: Recorder | None = None

    # ------------------------------------------------------------------ what is checked

    def _agents_of(
        self, given: Mapping[str, str | AgentDriver] | Iterable[AgentSpec]
    ) -> tuple[dict[str, AgentSpec | AgentDriver], dict[str, str]]:
        """What each agent role was given, checked, and the spec each was written as.

        Raises:
          Refused: For a role that cannot be given this.
        """
        from hmz.runtime.flowing.specs import AgentSpec, SpecError, parse_agents
        from hmz.runtime.flowing.spi import HARNESS_CAPABILITIES

        named = self._named
        drivers: dict[str, AgentSpec | AgentDriver] = {}
        specs: dict[str, str] = {}
        for name, given_as in _by_role(given):
            role = self._declared.agent(name)
            if role is None:
                raise Refused(
                    f"{named} has no agent role {name!r}; its agent roles are "
                    f"{_roles(one.name for one in self._declared.agents if not one.auto)}"
                )
            if role.auto:
                raise Refused(
                    f"{named}: {name!r} is filled by the runtime -- whoever is outside "
                    "the run -- and is not given with -a"
                )
            if name in drivers:
                raise Refused(f"{named}: the agent role {name!r} is given twice")
            try:
                said = (
                    parse_agents([f"{name}={given_as}"])[0]
                    if isinstance(given_as, str)
                    else given_as
                    if isinstance(given_as, AgentSpec)
                    else cast("AgentDriver", given_as)
                )
            except SpecError as why:
                raise Refused(str(why)) from why
            if isinstance(said, AgentSpec):
                harness, capabilities = said.harness, HARNESS_CAPABILITIES[said.harness]
            else:
                harness, capabilities = said.harness, said.capabilities
            if role.harness is not None and harness != role.harness:
                raise Refused(
                    f"{named}: {name!r} is {role.harness}, and {harness} was given"
                )
            if lacking := role.capabilities - capabilities:
                raise Refused(
                    f"{named}: {name!r} needs "
                    f"{', '.join(sorted(one.__name__ for one in lacking))}, which "
                    f"{harness} does not do"
                )
            drivers[name] = said
            if isinstance(said, AgentSpec):
                specs[name] = str(said).partition("=")[2]
            else:
                account = f"@{said.provider}" if said.provider else ""
                specs[name] = (
                    f"{said.harness}{account}/{said.model}:{said.effort or 'auto'}"
                )
        if missing := [
            one.name
            for one in self._declared.agents
            if one.required and not one.auto and one.name not in drivers
        ]:
            raise Refused(
                f"{named} needs an agent for {_roles(missing)}; give each with "
                "-a ROLE=CLI/MODEL:EFFORT"
            )
        return drivers, specs

    def _envs_of(
        self, given: Mapping[str, str | EnvDriver] | Iterable[EnvSpec]
    ) -> tuple[dict[str, EnvSpec | EnvDriver], dict[str, str]]:
        """What each environment role was given, checked, and the spec each was written as.

        Raises:
          Refused: For a role that cannot be given this.
        """
        from hmz.runtime.flowing.specs import EnvSpec, SpecError, parse_envs

        named = self._named
        drivers: dict[str, EnvSpec | EnvDriver] = {}
        specs: dict[str, str] = {}
        for name, given_as in _by_role(given):
            role = self._declared.env(name)
            if role is None:
                raise Refused(
                    f"{named} has no environment role {name!r}; its environment roles "
                    f"are {_roles(one.name for one in self._declared.envs if not one.auto)}"
                )
            if role.auto:
                raise Refused(
                    f"{named}: {name!r} is the workspace the run is started in, and is "
                    "not given with -e"
                )
            if name in drivers:
                raise Refused(f"{named}: the environment role {name!r} is given twice")
            try:
                said = (
                    parse_envs([f"{name}={given_as}"])[0]
                    if isinstance(given_as, str)
                    else given_as
                    if isinstance(given_as, EnvSpec)
                    else cast("EnvDriver", given_as)
                )
            except SpecError as why:
                raise Refused(str(why)) from why
            drivers[name] = said
            if isinstance(said, EnvSpec):
                specs[name] = str(said).partition("=")[2]
            else:
                # As `-e` spells one, which a run picked up is given again.
                workdir = str(said.workdir).lstrip("/")
                specs[name] = f"{said.backend}@{said.provider}/{workdir}"
        if missing := [
            one.name
            for one in self._declared.envs
            if one.required and not one.auto and one.name not in drivers
        ]:
            raise Refused(
                f"{named} needs an environment for {_roles(missing)}; give each with "
                "-e ROLE=BACKEND@PROVIDER/WORKDIR"
            )
        return drivers, specs

    def _picks_up(self, resume: bool | str | os.PathLike[str]) -> Path | None:  # noqa: FBT001
        """The epic this run picks up, or None for a run from the top.

        Raises:
          Refused: For a flow that cannot be picked up, or no run of it to pick up.
        """
        from .epic import picks_up, resumed

        if resume is False:
            return None
        if not self._impl.resumable:
            raise Refused(
                f"{self._named} does not say it can be picked up, so there is no run of "
                "it to resume"
            )
        if resume is True:
            found = resumed(self._impl.ref, self._workspace)
            if found is None:
                raise Refused(
                    f"{self._named} has no run here to pick up: none got as far as "
                    "writing anything down"
                )
            return found
        found = Path(resume)
        if not picks_up(found):
            raise Refused(f"{found.name} holds nothing a run could be picked up from")
        return found

    # ----------------------------------------------------------------------- what it is

    @property
    def flow(self) -> str:
        """The flow, as it was named."""
        return self._named

    @property
    def impl(self) -> FlowImpl:
        """The flow, loaded."""
        return self._impl

    @property
    def declaration(self) -> Declaration:
        """What the flow declares."""
        return self._declared

    @property
    def agents(self) -> dict[str, AgentDriver]:
        """The driver each agent role was given, by role."""
        return dict(self._agents)

    @property
    def envs(self) -> dict[str, EnvDriver]:
        """The driver each environment role was given, by role."""
        return dict(self._envs)

    @property
    def params(self) -> FlowParams:
        """The flow's params, validated."""
        return self._params

    @property
    def budget(self) -> Budget:
        """What the run may spend."""
        return self._budget

    @property
    def picked_up(self) -> Path | None:
        """The epic this run picks up, or None for a run from the top."""
        return self._picked_up

    @property
    def workspace(self) -> Path:
        """Where the run happens."""
        return self._workspace

    @property
    def recorder(self) -> Recorder | None:
        """What is writing the run down, once it has started, or None before."""
        return self._recorder

    def unreadable(self) -> str:
        """Which cap of the run nothing it drives can read, in words, or "" for none.

        A cost cap over an agent whose model nobody prices is a cap that cannot bite: its
        turns cost nothing anybody can count, which reads exactly like a cap that has not bitten
        yet. Answered before the first turn rather than at the end of a run that never stopped.
        """
        from hmz.coganchor.prices import price

        cost = self._budget.cost
        if cost is None or math.isinf(cost):
            return ""
        unpriced = sorted(
            {one.model for one in self._agents.values() if price(one.model) is None}
        )
        if not unpriced:
            return ""
        return (
            f"nobody lists a price for {', '.join(unpriced)}, so cost={cost:g} cannot "
            "stop what it spends"
        )

    def watch(self, listener: Listener) -> None:
        """Has everything every session of the run says reach `listener`.

        What a way in shows a run through: every session is watched for what it spends,
        which also stops a CLI writing its own progress to this process's streams.

        Args:
          listener: What to tell, from whichever thread a CLI is read on.
        """
        for driver in self._agents.values():
            watch = getattr(driver, "watch", None)
            if callable(watch):
                watch(listener)

    # ------------------------------------------------------------------------- running

    async def arun(
        self,
        task: str,
        *,
        outworlder: OutworlderDriver | None = None,
        opened: Opened | None = None,
        started: Callable[[Epic], None] | None = None,
    ) -> Any:
        """Runs the flow to its return, on the loop this is awaited on.

        Args:
          task: What it is to do.
          outworlder: Whoever is outside the run, or None for nobody -- an outworlder that is
            always away, which is what a command line is.
          opened: What is told of each session as it opens, or None.
          started: What is handed the epic the run is written into, once it is open.

        Returns:
          What the flow returned.

        Raises:
          Refused: If an environment cannot be reached, or the drivers do not meet what the
            flow declares -- before the flow has been called.
          BaseException: Whatever the flow raised, as it raised it.
        """
        from hmz.flows import (
            BudgetExceeded,
            FlowCancelled,
            FlowDefinitionError,
            FlowException,
            ParamsError,
            RequirementError,
        )
        from hmz.runtime.flowing import local_env, open_outworlder, probe, run_flow

        from .epic import Epic
        from .settings import Settings

        try:
            for driver in self._envs.values():
                await probe(driver)
            local = local_env(self._workspace)
        except BaseException as why:
            # Stopped, or refused, before the run began: what it was given goes either way.
            await asyncio.shield(self._closed(None))
            if isinstance(why, FlowException):
                raise Refused(str(why)) from why
            raise
        impl = self._impl
        epic = Epic(
            self._named,
            task,
            self._workspace,
            ref=impl.ref,
            agents=[_drove(role, spec) for role, spec in self._specs.items()],
            envs=[f"{role}={spec}" for role, spec in self._places.items()],
            # Through JSON text rather than `mode="json"`, which leaves an infinite cost a
            # float: `Budget(cost=inf)` is written as the string it reads back from.
            params=json.loads(self._params.model_dump_json()),
            budget=json.loads(self._budget.model_dump_json()),
            resumable=impl.resumable,
            picked_up=self._picked_up,
            profile=Settings(self._workspace).profiling,
        )
        recorder = Recorder(epic, opened)
        self._recorder = recorder
        try:
            with epic:
                if started is not None:
                    started(epic)
                try:
                    return await run_flow(
                        impl,
                        task,
                        agents=self._agents,
                        envs=self._envs,
                        params=self._params,
                        budget=self._budget,
                        outworlder=outworlder or open_outworlder(),
                        journal=epic.resume if impl.resumable else None,
                        resume=self._picked_up is not None,
                        local=local,
                        recorder=recorder,
                    )
                except (RequirementError, ParamsError, FlowDefinitionError) as why:
                    # Refused by the engine before the flow was called: the drivers do not
                    # meet what it declares, or a skill a role names is not to be had.
                    if not recorder.started:
                        raise Refused(str(why)) from why
                    raise
                except (asyncio.CancelledError, FlowCancelled, BudgetExceeded):
                    epic.stopped()
                    raise
                finally:
                    usage = recorder.usage()
                    epic.write(
                        "usage",
                        cost=usage.cost,
                        output_tokens=usage.output_tokens,
                        seconds=usage.duration.total_seconds(),
                    )
        finally:
            await asyncio.shield(self._closed(local))

    async def aclose(self) -> None:
        """Closes every driver the run was given, for a run that will not be run after all."""
        await self._closed(None)

    async def _closed(self, local: EnvDriver | None) -> None:
        """Closes every driver the run was given, and the workspace's, however it ended."""
        for driver in (*self._agents.values(), *self._envs.values(), local):
            if driver is None:
                continue
            with contextlib.suppress(Exception):
                await driver.close()

    def run(self, task: str, *, outworlder: OutworlderDriver | None = None) -> Any:
        """Runs the flow to its return, on a loop of its own in this thread.

        Args:
          task: What it is to do.
          outworlder: Whoever is outside the run, or None for nobody.

        Returns:
          What the flow returned.
        """
        return asyncio.run(self.arun(task, outworlder=outworlder))


class Recorder:
    """What writes a run down as the engine runs it: a record per flow call, and each session.

    Answers to :class:`hmz.runtime.flowing.engine.Recorder`. Every call is told on the loop
    the run is on.

    Attributes:
      started: Whether the flow the run was started with has been called, which is what
        tells a run refused before it started from one that failed.
    """

    def __init__(self, epic: Epic, opened: Opened | None = None) -> None:
        """Holds the epic to write into, and what to tell of each session opened."""
        self._epic = epic
        self._opened = opened
        self._records: dict[int, Epic] = {}
        self._sessions: list[SessionHandle] = []
        self.started = False

    def entered(self, call: LiveCall) -> None:
        """A flow call started: the run's own, or one written into a record of its own."""
        self.started = True
        if call.parent is None:
            self._records[id(call)] = self._epic
            return
        above = self._records.get(id(call.parent), self._epic)
        self._records[id(call)] = above.called(call.ref)

    def left(self, call: LiveCall, error: BaseException | None) -> None:
        """A flow call ended, which closes its record."""
        from hmz.flows import BudgetExceeded, FlowCancelled

        from .epic import Sub

        record = self._records.pop(id(call), None)
        if not isinstance(record, Sub):
            return
        stopped = isinstance(
            error, asyncio.CancelledError | FlowCancelled | BudgetExceeded
        )
        record.ended(
            None if error is None else type(error), "stopped" if stopped else ""
        )

    def spawned(
        self, call: LiveCall, role: str, session: SessionHandle, driver: AgentDriver
    ) -> None:
        """A flow call opened a session: named for its role, and written into its record."""
        self._sessions.append(session)
        record = self._records.get(id(call), self._epic)
        agent: AgentBase | None = getattr(session, "agent", None)
        if agent is None:
            # A driver with no coganchor agent behind it -- a fake -- names its session as
            # it opens it, and is written down then.
            record.session(
                role, str(driver.harness), driver.provider, session.id or "?"
            )
            return
        # Named for its role, and written down in the record of the call that opened it
        # once its CLI has said what it calls the conversation, which is its first turn.
        agent.rename(role)
        agent.epic = record
        conversation: SessionBase | None = getattr(session, "coganchor", None)
        if self._opened is not None and conversation is not None:
            self._opened(role, agent, conversation)

    @property
    def sessions(self) -> tuple[SessionHandle, ...]:
        """Every session the run has opened, oldest first."""
        return tuple(self._sessions)

    def usage(self) -> Usage:
        """Everything the run's sessions have spent, up to the moment it is read."""
        import datetime

        from hmz.flows import Usage

        cost = 0.0
        tokens = 0
        seconds = 0.0
        for session in tuple(self._sessions):
            said = session.usage
            cost += said.cost
            tokens += said.output_tokens
            seconds += said.duration.total_seconds()
        return Usage(
            duration=datetime.timedelta(seconds=seconds),
            cost=cost,
            output_tokens=tokens,
        )


def _agent_drivers(
    given: Mapping[str, AgentSpec | AgentDriver],
) -> dict[str, AgentDriver]:
    """A driver per agent role, made for each role given a spec.

    Raises:
      Refused: For a spec its CLI cannot be configured at.
    """
    from hmz.flows import FlowException
    from hmz.runtime.flowing.harnesses import open_agent
    from hmz.runtime.flowing.specs import AgentSpec

    try:
        return {
            role: open_agent(said) if isinstance(said, AgentSpec) else said
            for role, said in given.items()
        }
    except FlowException as why:
        raise Refused(str(why)) from why


def _env_drivers(given: Mapping[str, EnvSpec | EnvDriver]) -> dict[str, EnvDriver]:
    """A driver per environment role, made for each role given a spec.

    Raises:
      Refused: For a spec whose machine is known not to have its workdir.
    """
    from hmz.flows import FlowException
    from hmz.runtime.flowing.environments import open_env
    from hmz.runtime.flowing.specs import EnvSpec

    try:
        return {
            role: open_env(said) if isinstance(said, EnvSpec) else said
            for role, said in given.items()
        }
    except FlowException as why:
        raise Refused(str(why)) from why


def _by_role(given: object) -> list[tuple[str, object]]:
    """What each role was given, whether by role or as the specs a line read."""
    from collections.abc import Mapping

    if isinstance(given, Mapping):
        return [
            (str(role), said)
            for role, said in cast("Mapping[object, object]", given).items()
        ]
    return [
        (str(getattr(one, "role", "")), one) for one in cast("Iterable[object]", given)
    ]


def _drove(role: str, spec: str) -> Drove:
    """One agent role as the epic writes it down, off the spec it was given as."""
    from .epic import Drove
    from .kept import read_back

    runs = read_back(spec)
    cli, _, rest = (runs.spec if runs is not None else spec).partition("/")
    model, _, effort = rest.rpartition(":")
    return Drove(role, cli, model, effort, runs.provider if runs is not None else "")


def _roles(names: Iterable[str]) -> str:
    """Some roles, as a line says them."""
    said = [repr(one) for one in names]
    return ", ".join(said) if said else "none"


def _budget(said: Mapping[str, Any]) -> Budget:
    """A budget written down as JSON, read back.

    Raises:
      Refused: For one that is not a budget.
    """
    import pydantic

    from hmz.flows import Budget

    try:
        return Budget.model_validate(dict(said))
    except pydantic.ValidationError as why:
        raise Refused(f"the budget is not one: {why}") from why
