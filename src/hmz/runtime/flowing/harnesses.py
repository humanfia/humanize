"""The agent drivers: one :class:`~hmz.runtime.flowing.spi.AgentDriver` per coding agent CLI.

Each is coganchor's own driver for its CLI, held so that it keeps what
:mod:`hmz.runtime.flowing.spi` promises. What a harness can be asked for is
:data:`~hmz.runtime.flowing.spi.HARNESS_CAPABILITIES`; how a
:class:`~hmz.flows.Permission` reaches its CLI, and what a hook's answer does there, is
:mod:`hmz.runtime.flowing.harnessing`.

A session is a coganchor agent of its own and one conversation of it. The agent is what
coganchor settles everything a session runs by on -- the rung, the web, the skills, the
machine, the hooks and the person a question goes to -- and two sessions of one flow agent may
differ in every one of those, so each has its own; they share the CLI, the account and the
model, which is the driver.

A turn is a coganchor turn on a thread of its own, so the engine's loop is never held by one.
Around it, on the loop, the driver fires the hooks that bracket a turn -- SESSION_START before
the first, USER_PROMPT_SUBMIT before each, STOP after each, SESSION_END as the session closes
-- and takes the turn again where a STOP hook or a steer sends the agent on. The moments that
arrive from inside the CLI -- a tool, a permission, a notification, a subagent, a question --
come on coganchor's threads and reach the engine's hooks through a
:class:`~hmz.runtime.flowing.spi.HookBridge`, which answers as if nothing were hung once a
hook has kept one waiting for :data:`HOOK_TIMEOUT` -- a question excepted, which waits for a
person. A hook hung while a turn is running reaches the moments of that turn that come later,
except the few that decide how a CLI is started, which take hold from the next turn:
PRE_TOOL_USE on a CLI that gates its tools with a hook table of its own, and the hooks
:mod:`~hmz.runtime.flowing.harnessing` starts a CLI asking for -- Codex's `untrusted`
approvals and its asking feature, whose app server is started again between two turns for
it, and Kimi Code's asking rung.

What a hook answers is done where the CLI waits for it. A PRE_TOOL_USE hook refuses a tool on
a CLI that gates its tools (Claude Code, Qwen Code) and watches one already reached for on
the rest; a PERMISSION_REQUEST refusal is the tool refused, its reason told to the agent -- on
Codex, whose refusals carry none, as a steer into the turn; SUBAGENT_START and SUBAGENT_STOP
are told, no CLI waiting on either, so what their hooks answer changes nothing.

A prompt that is `/goal <objective>` is the harness's own goal, on a harness that has one; every
other prompt, `/loop` included, goes to the CLI as it is. A turn's
:class:`~hmz.runtime.flowing.spi.Limits` are held by the driver: what it spends is read as the
CLI reports it, priced with :func:`hmz.coganchor.prices.cost` -- a model nobody prices costs
nothing there. A graceful turn runs to its end and answers as usual, whatever it spends, the
engine refusing the next; one that is not graceful is cut off the moment a limit is reached --
the CLI stops spending -- and raises the :class:`~hmz.flows.errors.BudgetExceeded` leaf.

A fork is the CLI's own: Claude Code, Codex and Kimi Code fork into another workdir,
every other harness that forks does so only into the workdir it is in, and cursor-agent,
MiniMax Code, Antigravity and dsh do not fork. A fork is cut where its first turn is taken, so
it is refused then if the session it came from has taken a turn since. A session whose next
turn works in another workdir moves there the same way: it carries on as a fork of itself,
cut by that turn from a coganchor agent of its own there, on the harnesses that fork
elsewhere, and is refused on every other -- as is one whose turn works on another machine,
on any harness. A session may also carry on a conversation a session kept, in this run or an
earlier one: its first turn cuts it as a fork of that conversation, recalled from where it was
kept, on the harness that kept it, where that harness forks, and on this machine -- and not
where the run holds another copy of it, which is never replaced.

:func:`open_outworlder` is the driver for whoever is outside the run.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime
import os
import threading
import time
from typing import TYPE_CHECKING, Any, Final

from hmz.flows import (
    AskUserHookAgentMixin,
    CostExceeded,
    DurationExceeded,
    GoalCommandAgentMixin,
    HarnessKind,
    HarnessNotInstalled,
    HarnessSandboxed,
    HarnessUnrecoverable,
    HookKind,
    OutputTokensExceeded,
    OutworlderAway,
    PermissionRequestHookAgentMixin,
    SessionError,
    SessionStartHookResult,
    SteeringAgentMixin,
    StopHookResult,
    SubagentStartHookAgentMixin,
    UnsupportedOperation,
    Usage,
    UserPromptSubmitHookResult,
)

from . import harnessing
from .specs import spelled
from .spi import HARNESS_CAPABILITIES, HookBridge, Kept

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path

    import pydantic

    from hmz.coganchor import AnchorConfig
    from hmz.coganchor.agents import (
        AgentBase,
        AgentConfig,
        Event,
        HumanAgent,
        Hung,
        Occasion,
        Question,
        SessionBase,
        Verdict,
    )
    from hmz.coganchor.backends import Profile
    from hmz.coganchor.fence import Fence
    from hmz.coganchor.machines import AnchoredConfig, MachineConfig
    from hmz.flows import BudgetExceeded, HarnessError, HookResult, Permission

    from .affinity import Harbors
    from .specs import AgentSpec
    from .spi import (
        HookTable,
        Limits,
        OutworlderDriver,
        Placement,
        SessionHandle,
        Skill,
        TurnRequest,
        UsageSink,
    )

__all__ = [
    "HarnessDriver",
    "HarnessSession",
    "HumanOutworlder",
    "Listener",
    "open_agent",
    "open_outworlder",
]

#: What is told everything a session's CLI says, as coganchor says it: the agent, the
#: conversation, and the event. How a way in shows a run.
type Listener = Callable[[AgentBase, SessionBase | None, Event], None]

#: The prefix of a prompt that is the harness's own goal.
_GOAL: Final = "/goal "

#: How often a turn's spending is read while nothing it says has been heard.
_POLL: Final = 1.0

#: How often a turn that was cut off is cut again while it has not ended.
_RECUT: Final = 1.0

#: How long a cancelled turn is waited for to end before `CancelledError` leaves it.
_DRAIN: Final = 30.0

#: The harnesses driven as a package of this Python rather than as a program, by the module
#: that says the package is installed.
_PACKAGES: Final = {"dsh": "deepseek_harness", "litellm": "litellm"}

#: The harnesses whose turns work nowhere: a model called from this process, with no CLI to
#: put on a machine and no workdir for it to work in. Their sessions are opened here whatever
#: the placement says, which is the run's own workspace -- a turn of one is given no env.
_NOWHERE: Final = frozenset({HarnessKind.LITELLM})

#: The CLIs whose answer to a permission request carries no reason, which a refusal's reason
#: is steered into the turn for instead: Codex's approvals are a decision and nothing else.
_REASONLESS: Final = frozenset({HarnessKind.CODEX})

#: What asks an environment's machine whether a CLI is there, by its name and then by the
#: last part of its path -- the two a native turn looks for -- exiting with :data:`_NOT_FOUND`
#: where it is not.
_HAS: Final = 'command -v -- "$1" >/dev/null 2>&1 || command -v -- "$2" >/dev/null 2>&1 || exit 69'

#: What that exits with for a CLI that is not there: `EX_UNAVAILABLE`, and not the 127 a
#: shell uses, which is also what reaching the machine at all exits with where it has no
#: Python to serve a turn -- a machine that could not be asked is not one without the CLI.
_NOT_FOUND: Final = 69

#: How long a machine is given to say whether it has a CLI: long enough to put humanize there
#: the first time, which is most of what asking costs.
_ASKING: Final = 300.0

#: The moments whose hook decides whether a tool runs.
_GATES: Final = frozenset({HookKind.PRE_TOOL_USE, HookKind.PERMISSION_REQUEST})

#: The hooks whose being hung decides how a session's CLI is started or its rung.
_STARTING: Final = frozenset(
    {HookKind.PRE_TOOL_USE, HookKind.PERMISSION_REQUEST, HookKind.ASK_USER}
)

#: How long a moment from inside a CLI -- a tool, a permission, a notification, a subagent --
#: waits on the flow's hook before it is answered as if nothing were hung: as long as a CLI's
#: own hook table waits on one, so that a hook that never answers cannot hold a turn for
#: good. A question to the user waits for as long as the loop runs; a person is its answer.
HOOK_TIMEOUT: float = 900.0


def open_agent(spec: AgentSpec, harbors: Harbors | None = None) -> HarnessDriver:
    """Makes the driver for one `-a`.

    Starts nothing and looks for nothing: the CLI is reached when the first session opens,
    which is also where one not installed where the session works is refused -- this does not
    know yet which machine that is, nor so where its harness runs.

    Args:
      spec: The agent.
      harbors: The run's harness runtimes, which say where the harness of a session working
        on a runtime goes, or None to put it where its CLI is wherever the work is.

    Returns:
      A driver of `spec.harness` whose capabilities are exactly that harness's in
      :data:`~hmz.runtime.flowing.spi.HARNESS_CAPABILITIES`.

    Raises:
      HarnessNotInstalled: For a CLI added by hand that nobody has added on this machine.
      HarnessUnrecoverable: For a model, effort or account the CLI cannot be configured at.
    """
    from hmz.coganchor import backends
    from hmz.coganchor.agents import driver
    from hmz.coganchor.agents.base import identifying

    try:
        kind, made = driver(spec.cli)
    except KeyError:
        raise HarnessNotInstalled(
            f"{spec.cli}: no such CLI has been added on this machine"
        ) from None
    profile = backends.named(spec.cli)
    try:
        config = made(
            model=spec.model,
            effort=spec.effort,
            provider=spec.provider,
            **identifying(made, spec.cli),
        )
        # Built once and let go, which is where coganchor refuses an effort, a rung or a
        # tier the CLI has no word for -- said here rather than at the first session.
        kind(config)
    except ValueError as refused:
        raise HarnessUnrecoverable(f"{spec}: {refused}") from refused
    return HarnessDriver(spec, kind, config, profile, harbors=harbors)


class HarnessDriver:
    """The driver of one CLI at one account, model and effort; see the module docstring."""

    __slots__ = (
        "_asking",
        "_capabilities",
        "_closed",
        "_config",
        "_fences",
        "_harbors",
        "_has",
        "_installed",
        "_kind",
        "_listeners",
        "_profile",
        "_sessions",
        "_spec",
    )

    def __init__(
        self,
        spec: AgentSpec,
        kind: type[AgentBase],
        config: AgentConfig,
        profile: Profile | None,
        *,
        harbors: Harbors | None = None,
    ) -> None:
        """Initializes a driver that has opened nothing.

        Args:
          spec: The agent, as `-a` named it.
          kind: coganchor's agent class for the CLI.
          config: What every session's agent is configured with before its own settings.
          profile: What coganchor knows of the CLI, or None for one it knows nothing of.
          harbors: The run's harness runtimes, or None for no affinity anywhere.
        """
        self._spec = spec
        self._kind = kind
        self._config = config
        self._profile = profile
        self._harbors = harbors
        self._capabilities = HARNESS_CAPABILITIES[spec.harness]
        self._listeners: list[Listener] = []
        self._sessions: set[HarnessSession] = set()
        self._closed = False
        self._installed = False
        #: Whether each machine an environment put a session on has the CLI, by its target,
        #: and why not where it has not; and whether it can hold each kind of fence, by its
        #: target and whether the fence leaves the network on. Asked once apiece, since asking
        #: is reaching the machine, and one at a time.
        self._has: dict[str, tuple[type[HarnessError], str] | None] = {}
        self._fences: dict[tuple[str, bool], tuple[type[HarnessError], str] | None] = {}
        self._asking = asyncio.Lock()

    @property
    def harness(self) -> HarnessKind:
        """Which CLI it is."""
        return self._spec.harness

    @property
    def model(self) -> str:
        """The model its sessions run."""
        return self._spec.model

    @property
    def effort(self) -> str:
        """The effort, in the harness's own words; "" for the harness's default."""
        return self._spec.effort

    @property
    def provider(self) -> str:
        """The account turns run as, or "" for whoever this machine's CLI is logged in as."""
        return self._spec.provider

    @property
    def capabilities(self) -> frozenset[type]:
        """The agent mixins of :mod:`hmz.flows` this driver serves."""
        return self._capabilities

    @property
    def spec(self) -> AgentSpec:
        """The agent, as `-a` named it."""
        return self._spec

    @property
    def profile(self) -> Profile | None:
        """What coganchor knows of the CLI, or None for one it knows nothing of."""
        return self._profile

    @property
    def tellable(self) -> bool:
        """Whether the CLI can be told whether its agent may use the web."""
        return self._profile is not None and self._profile.searches

    def watch(self, listener: Listener) -> None:
        """Has everything the CLI says in every session opened from now on reach `listener`.

        coganchor stops writing a watched agent's words to this process's own stdout and
        stderr, and every session here is watched for what it spends -- so a way in that
        shows a run shows it through this.

        Args:
          listener: What to tell, from whichever thread the CLI is read on.
        """
        self._listeners.append(listener)

    async def open(
        self,
        placement: Placement,
        *,
        permission: Permission,
        skills: tuple[Skill, ...],
        hooks: HookTable,
        fork_of: SessionHandle | None = None,
        carry_on: Kept | None = None,
    ) -> HarnessSession:
        """Opens a session, which starts no CLI until its first turn.

        Args:
          placement: Where it works.
          permission: What it may touch, as :mod:`hmz.runtime.flowing.harnessing` maps it.
          skills: What skills it is given, mounted where its CLI reads them.
          hooks: What is hung on the agent.
          fork_of: A session of this driver to carry on from, or None for a fresh one.
          carry_on: A conversation a session kept to carry on from, as a fork of it, or
            None.

        Returns:
          The session.

        Raises:
          SessionError: If the driver is closed, `fork_of` is not an open session of it that
            has taken a turn, `carry_on` is not where it says, or the workdir is not a
            directory here.
          UnsupportedOperation: If the harness cannot fork, or not into `placement`; or
            `carry_on` was kept by another harness, or `placement` is on another machine.
          HarnessNotInstalled: If the CLI is not installed on the machine its harness runs
            on: this one, or the environment's where its affinity has nowhere else.
          HarnessUnrecoverable: If the CLI cannot be configured as the session asks, or the
            environment's machine cannot be asked whether it has the CLI.
          HarnessSandboxed: If its permission can be held neither by the CLI nor here, or
            nowhere its affinity names can hold it.
          EnvError: If no runtime its affinity names, and nothing after them, has room.
          ResourceUnmet: Likewise, where the last of them had no share left to give.
        """
        if self._closed:
            raise SessionError("the agent's driver is closed")
        parent = None
        if fork_of is not None:
            if not isinstance(fork_of, HarnessSession) or fork_of.driver is not self:
                raise SessionError(
                    "a session is forked only by the agent it is a session of"
                )
            parent = self.cut_from(fork_of, placement, doing="fork")
        agent, session = await self.build(
            placement,
            permission=permission,
            skills=skills,
            hooks=hooks,
            parent=parent,
            carry_on=carry_on,
        )
        handle = HarnessSession(
            self,
            agent,
            session,
            hooks=hooks,
            placement=placement,
            permission=permission,
            skills=skills,
            bridge=HookBridge.here(timeout=HOOK_TIMEOUT),
            carry_on=carry_on,
        )
        if self._closed:
            # Closed while the session was being made, so it is closed with the rest.
            await handle.close()
            raise SessionError("the agent's driver is closed")
        self._sessions.add(handle)
        return handle

    async def build(
        self,
        placement: Placement,
        *,
        permission: Permission,
        skills: tuple[Skill, ...],
        hooks: HookTable,
        parent: HarnessSession | None,
        carry_on: Kept | None = None,
    ) -> tuple[AgentBase, SessionBase]:
        """A session's own coganchor agent at `placement`, and its conversation there.

        Args:
          placement: Where it works.
          permission: What it may touch.
          skills: What skills it is given.
          hooks: What is hung on the agent now.
          parent: The session whose conversation it carries on, checked by :meth:`cut_from`,
            or None for a fresh one.
          carry_on: A kept conversation it carries on instead, or None.

        Returns:
          The agent, and the conversation: a fork of `parent`'s or of the kept one, cut by its
          first turn.

        Raises:
          See :meth:`open`.
        """
        if carry_on is not None:
            if carry_on.harness != self.harness:
                raise UnsupportedOperation(
                    f"{self.harness} cannot carry on a conversation {carry_on.harness} kept"
                )
            if self._profile is None or not self._profile.forks:
                raise UnsupportedOperation(f"{self.harness} cannot fork a session")
            if placement.machine is not None:
                raise UnsupportedOperation(
                    f"{self.harness} cannot carry a kept conversation onto another machine"
                )
        cwd = self._where(placement)
        hung = frozenset(kind for kind in _STARTING if kind in hooks)
        config = self._configured(permission, placement, hung)
        machine = (
            None
            if self.harness in _NOWHERE
            else await self._harnessed(placement, config, hung=hung)
        )
        if machine is None:
            self._check_installed()
        config = dataclasses.replace(config, machine=machine)
        return await asyncio.to_thread(
            self._made, config, skills, parent, cwd, carry_on
        )

    async def placeable(
        self, placements: Iterable[Placement], permission: Permission
    ) -> None:
        """Settles, before any session opens, where the harness goes on every runtime.

        What a run asks of every machine it was given before its flow is called, so that an
        affinity with no room anywhere is a runtime to correct rather than a flow that fails
        at its first session, and every runtime a harness goes to is opened and probed with
        the run's own. For each machine whose runtime has an affinity, the entries are walked
        as a session's would be: whether the machine has the CLI and can hold the role's
        fence, for `self`; whether a runtime can be reached and has room, and the role's
        permission fences nothing -- which a harness on another machine cannot be held to --
        for a runtime. Nothing for a machine with no affinity, whose harness goes wherever it
        can. The answers are remembered, and are the ones the sessions are given as they open.

        Args:
          placements: Where the role's sessions may work: every environment of the run.
          permission: What the role's sessions run under.

        Raises:
          HarnessNotInstalled: If the affinity ends on a machine without the CLI.
          HarnessSandboxed: If it ends on one that cannot hold the role's fence.
          HarnessUnrecoverable: If a machine cannot be asked.
          EnvError: If it ends on a runtime that cannot be reached.
          ResourceUnmet: If it ends on one with no share left.
        """
        if self._harbors is None or self.harness in _NOWHERE:
            return
        for placement in placements:
            if not self._harbors.affinity(placement):
                continue
            config = self._configured(permission, placement, frozenset())
            machine = await self._harnessed(placement, config)
            if machine is not None:
                # Built and let go, as `open_agent` builds one: where coganchor refuses a
                # fence it could not hold there, before any machine is reached for a turn.
                self._made_as(dataclasses.replace(config, machine=machine))

    def _made_as(self, config: AgentConfig) -> AgentBase:
        """The agent a session is built as, refused as `open` refuses it.

        Raises:
          HarnessUnrecoverable: If the agent cannot be built as configured.
          HarnessSandboxed: If its fence can be held neither by the CLI nor here.
        """
        from hmz.coganchor.agents import Unfenced

        try:
            return self._kind(config)
        except Unfenced as refused:
            raise HarnessSandboxed(f"{self._spec}: {refused}") from refused
        except ValueError as refused:
            raise HarnessUnrecoverable(f"{self._spec}: {refused}") from refused

    def cut_from(
        self, session: HarnessSession, placement: Placement, *, doing: str
    ) -> HarnessSession:
        """A session of this driver, checked as one to carry on from at `placement`.

        Args:
          session: The session whose conversation is carried on.
          placement: Where it is carried on.
          doing: What carrying it is, in words: "fork", or "move".

        Raises:
          SessionError: If it is closed, or has taken no turn to carry on from.
          UnsupportedOperation: If the harness cannot carry it there.
        """
        if session.closed:
            raise SessionError(f"the session to {doing} is closed")
        if session.id is None:
            raise SessionError(
                f"the session to {doing} has taken no turn to carry on from"
            )
        if self._profile is None or not self._profile.forks:
            raise UnsupportedOperation(f"{self.harness} cannot {doing} a session")
        was = session.placement
        if was.machine != placement.machine:
            raise UnsupportedOperation(
                f"{self.harness} cannot {doing} a session onto another machine"
            )
        if (
            was.workdir != placement.workdir
            and not type(session.coganchor).forks_elsewhere
        ):
            raise UnsupportedOperation(
                f"{self.harness} cannot {doing} a session into another workdir"
            )
        return session

    @staticmethod
    def _where(placement: Placement) -> str | None:
        """The directory a session's conversation is opened at, as coganchor takes it.

        Raises:
          SessionError: If it is on this machine and is not a directory.
        """
        workdir = str(placement.workdir)
        if placement.machine is not None:
            # A remote workdir under the login's home is the anchor's own workspace, which is
            # where a session opened at no directory works.
            return workdir if placement.workdir.is_absolute() else None
        where = os.path.expanduser(workdir)  # noqa: PTH111 -- a string path, as coganchor takes
        if not os.path.isdir(where):  # noqa: PTH112
            raise SessionError(f"{where} is not a directory to open a session in")
        return where

    def _check_installed(self) -> None:
        """Refuses a CLI that is not installed on this machine, looked for once.

        Raises:
          HarnessNotInstalled: If it is not.
        """
        if self._installed:
            return
        import importlib.util

        from hmz.coganchor import backends

        # DeepSeek Harness and litellm are packages rather than programs: what each installs
        # is a module of this Python, and no program on any PATH. Looked for as a program,
        # neither was ever here, and every agent of them was refused.
        package = _PACKAGES.get(self._named())
        if (
            importlib.util.find_spec(package) is None
            if package is not None
            else backends.program(self._program()) is None
        ):
            raise HarnessNotInstalled(
                f"{self._named()} is not installed here: "
                f"{backends.installing(self._spec.cli)}"
            )
        self._installed = True

    def _named(self) -> str:
        """What the CLI is called."""
        return self._profile.name if self._profile is not None else self._spec.cli

    def _program(self) -> str:
        """The program the CLI is run as."""
        from hmz.coganchor import backends

        command = self._named()
        # A CLI somebody added runs the command it was added with -- the one its config was
        # given, or the one written down when it was added -- which may be a path PATH does
        # not name: `/opt/mimo/bin/mimo` is mimo, and is installed.
        added = tuple(getattr(self._config, "command", ()) or ()) or (
            backends.speaking().get(command) or ()
        )
        return added[0] if added else command

    async def _harnessed(
        self,
        placement: Placement,
        config: AgentConfig,
        *,
        hung: frozenset[HookKind] = frozenset(),
    ) -> MachineConfig | None:
        """The machine a session's turns land on, told where its harness runs.

        Settled per machine rather than per session: every session of the role that an
        environment puts on one machine has its harness put in the same place, and what that
        place is was asked of the machine once. Work on this machine has its harness here.
        Work on a runtime with an affinity has it on the first entry with room
        (:mod:`~hmz.runtime.flowing.affinity`); work anywhere else has it natively where the
        machine has the CLI and can hold its fence, and here otherwise.

        Args:
          placement: Where the session works.
          config: What its agent is configured with, for the fence it is held to.
          hung: The hooks among :data:`_STARTING` hung on it. One that decides whether a
            tool runs is served by the CLI's own hook table, which names a program on this
            machine, so a CLI driven on another one can only watch what it would have
            decided -- which is not chosen for anybody, and keeps the harness of work with
            no affinity here instead. A question the agent asks its user is not one of
            them: it comes back down the CLI's own stream, wherever the CLI runs.

        Returns:
          The machine, None for this one with the harness here as well.

        Raises:
          HarnessNotInstalled: If the affinity ends on the environment's machine and the CLI
            is not installed there.
          HarnessSandboxed: If it ends where the session's fence cannot be held.
          HarnessUnrecoverable: If the environment's machine cannot be asked.
          EnvError: If it ends on a runtime that cannot be reached or opened.
          ResourceUnmet: If it ends on a runtime with no share left.
        """
        from hmz.coganchor.machines import AnchoredConfig, store

        machine = placement.machine
        if not isinstance(machine, AnchoredConfig):
            return machine
        harbors = self._harbors
        affinity = harbors.affinity(placement) if harbors is not None else ()
        if harbors is None or not affinity:
            if hung & _GATES:
                return machine
            why = await self._native_on(machine.anchor, config.fence, placement)
            return machine if why is not None else _native(machine)
        refused: Exception | None = None
        for entry in affinity:
            if entry == store.HERE:
                return machine
            if entry == store.SELF:
                why = await self._native_on(machine.anchor, config.fence, placement)
                if why is None:
                    return _native(machine)
                kind, said = why
                if kind is HarnessUnrecoverable:
                    raise kind(said)
                refused = kind(said)
                continue
            on = await harbors.machine(entry)
            if isinstance(on, Exception):
                refused = on
                continue
            there = on.placement().machine
            if not isinstance(there, AnchoredConfig):
                return machine  # a runtime that is this machine, which is `local`
            # No mirror of this machine's named for it: a harness elsewhere keeps its own,
            # under that machine's cache, between turns.
            put = dataclasses.replace(
                machine,
                anchor=dataclasses.replace(
                    machine.anchor, harness=there.anchor.target, shadow=None
                ),
            )
            try:
                # Built and let go: a fence is drawn around this machine's paths, and a
                # role held to one cannot have its harness on a machine of its own.
                self._made_as(dataclasses.replace(config, machine=put))
            except HarnessSandboxed as why:
                refused = why
                continue
            return put
        if refused is None:  # nothing was asked, which an affinity of no entries asks
            return machine
        raise type(refused)(
            f"{spelled(placement.backend, placement.provider)}: nowhere its affinity "
            f"({', '.join(affinity)}) names has room for {self._named()}'s harness; "
            f"the last: {refused}"
        ) from refused

    async def _native_on(
        self, anchor: AnchorConfig, fence: Fence | None, placement: Placement
    ) -> tuple[type[HarnessError], str] | None:
        """Why the CLI cannot run natively on the machine an anchor reaches, or None if it can.

        Two questions, each asked of a machine once and remembered: whether the CLI is there,
        and -- for a session held to a fence -- whether the machine can hold one, a CLI there
        that could not be fenced being a CLI that would not start. The second is asked per
        kind of fence rather than per session, since two sessions of a role may be held to
        different permissions and one of them to none. Asked one at a time, so that sessions
        opened together on a machine wait for one answer rather than asking it each.

        Args:
          anchor: What reaches the machine.
          fence: What the session is held to, or None for nothing.
          placement: Where it works, for what the machine is called.

        Returns:
          None where it can; otherwise what a session to be put there anyway is refused
          with, and why, in words.
        """
        at = spelled(placement.backend, placement.provider)
        async with self._asking:
            if anchor.target not in self._has:
                self._has[anchor.target] = await self._has_cli(anchor, at)
            why = self._has[anchor.target]
            if why is not None or fence is None or fence.open:
                return why
            key = (anchor.target, fence.online)
            if key not in self._fences:
                self._fences[key] = await self._fenceable(anchor, fence, at)
            return self._fences[key]

    async def _has_cli(
        self, anchor: AnchorConfig, where: str
    ) -> tuple[type[HarnessError], str] | None:
        """Whether the machine has the CLI, asked by driving its shell as a native turn would.

        Exactly what a turn there would find: the same road, the same `PATH`, the same login.
        A process of its own, in a session of its own, so that a run stopped while it asks
        takes it down with everything it started rather than waiting for it.

        Returns:
          None where it is there; otherwise what refuses it, and why.
        """
        import posixpath
        import signal
        import subprocess

        from hmz.coganchor import backends

        program = self._program()
        asking = dataclasses.replace(anchor, native=True, shadow=None, fence=None)
        argv = asking.command(
            ["/bin/sh", "-c", _HAS, "humanize", program, posixpath.basename(program)]
        )
        try:
            asked = await asyncio.create_subprocess_exec(
                *argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as why:
            return (
                HarnessUnrecoverable,
                f"{where} could not be asked whether {self._named()} is there: {why}",
            )
        try:
            _, err = await asyncio.wait_for(asked.communicate(), _ASKING)
        except BaseException as why:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(asked.pid, signal.SIGKILL)
            await asked.wait()
            if not isinstance(why, TimeoutError):
                raise
            return (
                HarnessUnrecoverable,
                (
                    f"{where} did not say within {_ASKING:.0f}s whether "
                    f"{self._named()} is there"
                ),
            )
        if asked.returncode == _NOT_FOUND:
            return (
                HarnessNotInstalled,
                (
                    f"{self._named()} is not installed on {where}: "
                    f"{backends.installing(self._spec.cli)} there, or put local in the "
                    "affinity of the runtime it is on"
                ),
            )
        if asked.returncode:
            said = err.decode(errors="replace").strip().splitlines()
            return (
                HarnessUnrecoverable,
                (
                    f"{where} could not be asked whether {self._named()} is there: "
                    f"{said[-1] if said else f'exit status {asked.returncode}'}"
                ),
            )
        return None

    @staticmethod
    async def _fenceable(
        anchor: AnchorConfig, fence: Fence, where: str
    ) -> tuple[type[HarnessError], str] | None:
        """Whether the machine can hold a fence of this kind, as it says at the handshake.

        Returns:
          None where it can; otherwise what refuses it, and why.
        """
        from hmz.coganchor import check
        from hmz.coganchor.proto import hello_fences

        try:
            said = await asyncio.to_thread(check, anchor)
        except (OSError, ValueError) as why:
            return (
                HarnessUnrecoverable,
                f"{where} could not be asked whether it can fence: {why}",
            )
        if hello_fences(said, net=not fence.online):
            return None
        return (
            HarnessSandboxed,
            (
                f"{where} cannot fence the agent to its permission: it needs Landlock; "
                "grant the agent everything, or put local in the affinity of the runtime "
                "it is on"
            ),
        )

    def _configured(
        self, permission: Permission, placement: Placement, hung: frozenset[HookKind]
    ) -> AgentConfig:
        """What a session's own agent is configured with.

        Raises:
          HarnessUnrecoverable: If the CLI cannot be configured so.
        """
        return settled(
            self._config,
            self.harness,
            self._kind,
            permission,
            hung,
            tellable=self.tellable,
            machine=placement.machine,
            workdir=str(placement.workdir),
            profile=self._profile,
        )

    def _made(
        self,
        config: AgentConfig,
        skills: tuple[Skill, ...],
        parent: HarnessSession | None,
        cwd: str | None,
        carry_on: Kept | None,
    ) -> tuple[AgentBase, SessionBase]:
        """Builds a session's own agent and its conversation, on a thread of its own.

        Raises:
          HarnessUnrecoverable: If the agent cannot be built as configured.
          HarnessSandboxed: If its fence can be held neither by the CLI nor here.
          UnsupportedOperation: If the CLI will not fork into `cwd`.
          SessionError: If the session to fork cannot be carried on from, or the kept
            conversation is not where it says.
        """
        from hmz.coganchor.agents.skills import Loaded

        agent = self._made_as(config)
        agent.loads(Loaded(name=one.name, at=one.at) for one in skills)
        for listener in self._listeners:
            agent.watch(listener)
        try:
            if carry_on is not None:
                return agent, agent.recall(carry_on.id, carry_on.at, cwd).fork()
            if parent is not None:
                return agent, parent.coganchor.fork(into=agent, cwd=cwd)
        except NotImplementedError as refused:
            raise UnsupportedOperation(str(refused)) from refused
        except (RuntimeError, ValueError, OSError) as refused:
            raise SessionError(f"the session cannot be forked: {refused}") from refused
        return agent, agent.new(cwd)

    def forget(self, session: HarnessSession) -> None:
        """Drops a session that has closed from those the driver closes."""
        self._sessions.discard(session)

    async def close(self) -> None:
        """Closes every session still open, and opens no more. Idempotent."""
        self._closed = True
        sessions, self._sessions = list(self._sessions), set()
        await asyncio.gather(*(one.close() for one in sessions))


def _native(machine: AnchoredConfig) -> AnchoredConfig:
    """The machine an anchor reaches, with the CLI there driven natively: no mirror here."""
    native = dataclasses.replace(machine.anchor, native=True, shadow=None)
    return dataclasses.replace(machine, anchor=native)


def settled(
    config: AgentConfig,
    harness: HarnessKind,
    kind: type[AgentBase],
    permission: Permission,
    hung: frozenset[HookKind],
    *,
    tellable: bool,
    machine: MachineConfig | None = None,
    workdir: str = "",
    profile: Profile | None = None,
) -> AgentConfig:
    """A driver's config, set up for one session given the hooks hung on it now.

    Args:
      config: The driver's own config.
      harness: The CLI.
      kind: coganchor's agent class for it, whose rungs the rung is one of.
      permission: What the session may touch.
      hung: The hooks among :data:`_STARTING` hung on the agent.
      tellable: Whether the CLI can be told about the web.
      machine: The machine its turns land on, or None for this one.
      workdir: Where the session works, which the fence is drawn around: `~/...` is the
        home of whoever runs the CLI. "" for the directory this process is in.
      profile: What coganchor knows of the CLI, for the hosts a fence lets it reach.

    Returns:
      The config.

    Raises:
      HarnessUnrecoverable: If the CLI cannot be configured so.
    """
    from hmz.coganchor.agents import ClaudeCodeAgentConfig, CodexAgentConfig

    try:
        fence = harnessing.fenced(
            permission,
            workdir=os.path.expanduser(workdir or os.getcwd()),  # noqa: PTH109, PTH111
            home=os.path.expanduser("~"),  # noqa: PTH111
            profile=profile,
            environ=_environ(config, profile),
        )
    except ValueError as refused:
        raise HarnessUnrecoverable(str(refused)) from refused
    changes: dict[str, Any] = {
        "permission": harnessing.rung(harness, permission, rungs=kind.rungs, hung=hung),
        "web_search": harnessing.searching(permission, tellable=tellable),
        "machine": machine,
        "fence": fence,
    }
    if isinstance(config, CodexAgentConfig):
        feature = harnessing.ASKING_FEATURE
        rest = tuple(one for one in config.features if one[0] != feature)
        asks = ((feature, True),) if HookKind.ASK_USER in hung else ()
        changes["features"] = rest + asks
        changes["approvals"] = harnessing.approvals(harness, hung)
    if isinstance(config, ClaudeCodeAgentConfig):
        changes["asks"] = harnessing.prompting(harness, hung)
    try:
        return dataclasses.replace(config, **changes)
    except ValueError as refused:
        raise HarnessUnrecoverable(str(refused)) from refused


def _environ(config: AgentConfig, profile: Profile | None) -> Mapping[str, str]:
    """The environment a session's turns run under, its account's variables included.

    What says where an account points its CLI's model, which the fence has to let through: a
    gateway's endpoint is a variable its account sets. Less what the account hushes, and read
    by the one function the agent reads its own hosts with (`providers.composed`), so the hosts
    the fence lets through here are the hosts it lets through there. An account that is not
    there is this process's own environment here, and is refused where the agent is made.
    """
    from hmz.coganchor import providers

    if profile is None or not config.provider:
        return os.environ
    return providers.composed(providers.find(profile.name, config.provider), profile)


class HarnessSession:
    """One session of a :class:`HarnessDriver`: one conversation with its CLI.

    Every method may be called from the engine's loop, and :meth:`interrupt` from any thread.
    """

    __slots__ = (
        "_agent",
        "_asking",
        "_bridge",
        "_carry_on",
        "_closed",
        "_cost",
        "_driver",
        "_duration",
        "_flying",
        "_hooks",
        "_hung",
        "_interrupted",
        "_last",
        "_left",
        "_limits",
        "_lock",
        "_loop",
        "_over",
        "_permission",
        "_placement",
        "_pre",
        "_returned",
        "_rose",
        "_running",
        "_seen",
        "_session",
        "_sink",
        "_skills",
        "_started",
        "_steer_cut",
        "_steers",
        "_take",
        "_timers",
        "_tokens",
        "_turn_cost",
        "_turn_tokens",
        "_written",
    )

    def __init__(
        self,
        driver: HarnessDriver,
        agent: AgentBase,
        session: SessionBase,
        *,
        hooks: HookTable,
        placement: Placement,
        permission: Permission,
        skills: tuple[Skill, ...],
        bridge: HookBridge,
        carry_on: Kept | None = None,
    ) -> None:
        """Initializes a session that has taken no turn.

        Args:
          driver: The driver it is a session of.
          agent: Its own coganchor agent.
          session: Its conversation.
          hooks: What is hung on the flow agent it belongs to.
          placement: Where it works.
          permission: What it may touch.
          skills: What skills it is given.
          bridge: What carries moments from the CLI's threads to the engine's loop.
          carry_on: The kept conversation `session` is a fork of, or None.
        """
        self._driver = driver
        self._loop = asyncio.get_running_loop()
        self._agent = agent
        self._session = session
        #: The agents and conversations it has moved on from, kept until it closes: a
        #: conversation moved is a fork, cut from the one before by the turn after.
        self._left: list[tuple[AgentBase, SessionBase]] = []
        self._hooks = hooks
        self._placement = placement
        self._permission = permission
        self._skills = skills
        self._bridge = bridge
        #: The kept conversation it carries on, until a turn has cut a conversation of its own
        #: from it: one moved before that is cut from it again, wherever it moves to.
        self._carry_on = carry_on
        # A question waits on a person, for as long as the loop runs.
        self._asking = HookBridge(self._loop, timeout=None)
        self._lock = threading.Lock()
        # What the session has spent, and what of the CLI's own count has been read.
        self._cost = 0.0
        self._tokens = 0
        self._duration = 0.0
        self._written = 0.0
        self._seen: dict[str, float] = {}
        #: What the meter rose by in the coganchor turn now running, against which what its
        #: answer says it spent is read.
        self._rose: dict[str, float] = {}
        # The turn in flight, if one is.
        self._flying = False
        self._sink: UsageSink | None = None
        self._limits: Limits | None = None
        self._last = 0.0
        self._turn_cost = 0.0
        self._turn_tokens = 0
        self._over: type[BudgetExceeded] | None = None
        self._timers: list[asyncio.TimerHandle] = []
        self._interrupted = False
        self._steers: list[str] = []
        self._steer_cut = False
        # The coganchor call the turn is taking, and whether it is running.
        self._take = 0
        self._running = False
        self._returned = threading.Event()
        self._started = False
        self._closed = False
        self._pre: Hung | None = None
        self._hung = frozenset(kind for kind in _STARTING if kind in hooks)
        self._listen()

    # ---------------------------------------------------------------------- what it is

    @property
    def id(self) -> str | None:
        """The CLI's own id for the conversation, or None before it has said one."""
        return self._session.named

    @property
    def usage(self) -> Usage:
        """Everything this session's turns have spent, up to the moment it is read."""
        with self._lock:
            return Usage(
                duration=datetime.timedelta(seconds=self._duration),
                cost=self._cost,
                output_tokens=self._tokens,
            )

    def keep(self, sessions: Path) -> Kept:
        """Copies its conversation, as it stands; see the SPI's `SessionHandle.keep`."""
        import shutil
        import uuid

        from hmz.coganchor.agents.base import KEPT

        harness = self._driver.harness
        if self._agent.config.machine is not None:
            raise UnsupportedOperation(
                f"{harness} keeps a conversation on another machine, not here"
            )
        named = self.id
        if named is None:
            raise SessionError(f"{harness}: the session has not been named yet")
        profile = self._driver.profile
        cli = self._agent.backend if profile is None else profile.name
        into = sessions / cli / KEPT / uuid.uuid4().hex
        try:
            self._session.keep(into)
        except NotImplementedError as refused:
            raise UnsupportedOperation(str(refused)) from refused
        except (RuntimeError, OSError) as refused:
            shutil.rmtree(into, ignore_errors=True)
            raise SessionError(f"the session cannot be kept: {refused}") from refused
        return Kept(harness, named, into)

    @property
    def driver(self) -> HarnessDriver:
        """The driver it is a session of."""
        return self._driver

    @property
    def placement(self) -> Placement:
        """Where its last turn worked, or where it was opened before any has."""
        return self._placement

    @property
    def closed(self) -> bool:
        """Whether it has been closed."""
        return self._closed

    @property
    def coganchor(self) -> SessionBase:
        """Its conversation, as coganchor holds it."""
        return self._session

    @property
    def agent(self) -> AgentBase:
        """Its own coganchor agent."""
        return self._agent

    # ------------------------------------------------------------------------- moments

    def _listen(self) -> None:
        """Hangs what reaches the engine's hooks on the moments the CLI fires itself."""
        capabilities = self._driver.capabilities
        allowed = {
            HookKind.NOTIFICATION,
            *(
                (HookKind.PERMISSION_REQUEST,)
                if PermissionRequestHookAgentMixin in capabilities
                else ()
            ),
            *(
                (HookKind.SUBAGENT_START, HookKind.SUBAGENT_STOP)
                if SubagentStartHookAgentMixin in capabilities
                else ()
            ),
        }
        hooks = self._agent.hooks
        for moment in hooks.moments:
            kind = harnessing.MOMENTS.get(moment.value)
            if kind in allowed:
                hooks.on(moment, self._moment)
        if AskUserHookAgentMixin in capabilities:
            self._agent.ask = self._ask
        self._agent.watch(self._heard)
        self._settle_pre_tool_use()

    def _settle_pre_tool_use(self) -> None:
        """Hangs PRE_TOOL_USE on the CLI only while a hook is hung on it.

        A CLI that gates its tools with a hook table of its own is started with one only
        while something is hung there, since the table is a program it runs before every tool.
        """
        from hmz.coganchor.agents import Moment

        wanted = HookKind.PRE_TOOL_USE in self._hooks
        if wanted and self._pre is None:
            self._pre = self._agent.hooks.on(Moment.PRE_TOOL_USE, self._moment)
        elif not wanted and self._pre is not None:
            self._pre.off()
            self._pre = None

    def _moment(self, occasion: Occasion) -> Verdict | None:
        """Carries a moment the CLI fired to the engine's hook for it, on the CLI's thread."""
        kind = harnessing.MOMENTS[occasion.moment.value]
        if kind not in self._hooks:
            return None
        fields = harnessing.fields(kind, occasion)
        result = self._bridge.call(
            lambda: self._hooks.fire(kind, self, **fields),
            default=_default(kind),
        )
        said = harnessing.verdict(kind, result)
        if said is None and kind in _GATES and (self._closed or self._cut_off()):
            # The hook was given up on because the turn is being cut off: its tool is not
            # to run meanwhile, whatever the hook would have said.
            from hmz.coganchor.agents import Verdict

            return Verdict(refused=True, because="the turn was cut off")
        if (
            said is not None
            and kind is HookKind.PERMISSION_REQUEST
            and self._driver.harness in _REASONLESS
        ):
            # The CLI takes a refusal with no reason, so the reason is put into the turn.
            with contextlib.suppress(Exception):
                self._session.interject(
                    f"Using {occasion.tool or 'that tool'} was refused: {said.because}"
                )
        return said

    def _ask(self, question: Question) -> str | None:
        """Carries a question the agent stopped to ask to the engine's ASK_USER hook."""
        if HookKind.ASK_USER not in self._hooks:
            return None
        result = self._asking.call(
            lambda: self._hooks.fire(
                HookKind.ASK_USER,
                self,
                question=question.text,
                options=question.options,
            ),
            default=_default(HookKind.ASK_USER),
        )
        return harnessing.answer(result)

    async def _fire(self, kind: HookKind, **fields: Any) -> HookResult | None:
        """Fires a moment the driver brackets a turn with, on the loop, where one is hung."""
        if kind not in self._hooks:
            return None
        return await self._hooks.fire(kind, self, **fields)

    # -------------------------------------------------------------------------- a turn

    async def turn(
        self, request: TurnRequest, sink: UsageSink
    ) -> str | pydantic.BaseModel:
        """Takes one turn; see :meth:`hmz.runtime.flowing.spi.SessionHandle.turn`."""
        self._check_open()
        with self._lock:
            if self._flying:
                raise SessionError("a turn is already in flight in this session")
        limits = request.limits
        _refuse_spent(limits)
        goal = (
            request.prompt.startswith(_GOAL)
            and GoalCommandAgentMixin in self._driver.capabilities
        )
        body = request.prompt.removeprefix(_GOAL) if goal else request.prompt
        self._begin(sink, limits)
        try:
            if not self._started:
                self._started = True
                started = await self._fire(HookKind.SESSION_START)
                if isinstance(started, SessionStartHookResult) and started.context:
                    body = f"{started.context}\n\n{body}"
            submitted = await self._fire(
                HookKind.USER_PROMPT_SUBMIT, prompt=request.prompt
            )
            if isinstance(submitted, UserPromptSubmitHookResult):
                if submitted.block:
                    raise SessionError(submitted.reason or "a hook refused the prompt")
                if submitted.context:
                    body = f"{body}\n\n{submitted.context}"
            again = 0
            while True:
                said = await self._taken(body, request.output_schema, goal=goal)
                if self._over is not None:
                    break
                if self._interrupted:
                    raise SessionError("the turn was interrupted")
                if not self._steers:
                    stopping = await self._fire(HookKind.STOP, said=said, again=again)
                    if (
                        isinstance(stopping, StopHookResult)
                        and stopping.block
                        and stopping.reason
                    ):
                        body, goal, again = stopping.reason, False, again + 1
                        continue
                with self._lock:
                    steered, self._steers = self._steers, []
                if steered:
                    body, goal = "\n\n".join(steered), False
                    continue
                break
        finally:
            self._end()
        if self._over is not None and not limits.graceful:
            raise self._exceeded(self._over, limits)
        if self._interrupted:
            # Interrupted between two of the CLI's turns -- while a STOP hook was deciding --
            # which is the turn interrupted all the same.
            raise SessionError("the turn was interrupted")
        if request.output_schema is not None:
            return harnessing.read_shape(said, request.output_schema)
        return said

    def _begin(self, sink: UsageSink, limits: Limits) -> None:
        """Starts counting a turn: its sink, its limits and its clocks."""
        with self._lock:
            self._flying = True
            self._sink = sink
            self._limits = limits
            self._last = time.monotonic()
            self._turn_cost = 0.0
            self._turn_tokens = 0
            self._over = None
            self._interrupted = False
            self._steers = []
            self._steer_cut = False
        loop = self._loop
        if limits.deadline is not None and not limits.graceful:
            self._timers.append(
                loop.call_at(
                    loop.time() + (limits.deadline - time.monotonic()), self._deadline
                )
            )
        self._timers.append(loop.call_later(_POLL, self._poll))

    def _end(self) -> None:
        """Stops counting a turn: its clocks, and the last of what it spent."""
        for timer in self._timers:
            timer.cancel()
        self._timers = []
        self._account()
        with self._lock:
            sink, self._sink = self._sink, None
            now = time.monotonic()
            duration = now - self._last
            self._last = now
            self._duration += duration
            self._flying = False
        if sink is not None:
            sink.add(cost=0.0, output_tokens=0, duration=duration)

    async def _taken(
        self, body: str, schema: type[pydantic.BaseModel] | None, *, goal: bool
    ) -> str:
        """Takes one coganchor turn or goal on a thread of its own, and answers with its text.

        Returns:
          What the agent said, or "" for a turn cut off by an interrupt, a limit or a steer.

        Raises:
          SessionError: If the session was interrupted before the turn began.
          HarnessError: The leaf for why the CLI could not take the turn.
          asyncio.CancelledError: If the awaiting task was cancelled; the CLI has stopped.
        """
        loop = self._loop
        landed: asyncio.Future[str] = loop.create_future()
        # Retrieved whatever happens to it, so that a turn given up on leaves no warning.
        landed.add_done_callback(_retrieved)
        settle = self._settling()
        with self._lock:
            if self._interrupted:
                raise SessionError("the turn was interrupted")
            if self._over is not None:
                return ""
            self._take += 1
            take = self._take
            self._steer_cut = False
            returned = self._returned = threading.Event()
            steered, self._steers = self._steers, []
        if steered:
            body = "\n\n".join([body, *steered])
        threading.Thread(
            target=self._call,
            args=(loop, landed, take, returned, settle, body, schema, goal),
            name=f"{self._agent.id}-turn",
            daemon=True,
        ).start()
        try:
            return await asyncio.shield(landed)
        except asyncio.CancelledError:
            self.interrupt()
            await asyncio.wait({landed}, timeout=_DRAIN)
            raise
        except Exception as error:
            if self._cut_off():
                return ""
            leaf = harnessing.harness_error(error, self._agent.backend)
            if leaf is None:
                raise
            raise leaf from error

    def _call(
        self,
        loop: asyncio.AbstractEventLoop,
        landed: asyncio.Future[str],
        take: int,
        returned: threading.Event,
        settle: Callable[[], None] | None,
        body: str,
        schema: type[pydantic.BaseModel] | None,
        goal: bool,  # noqa: FBT001 -- positional, as a thread's arguments are
    ) -> None:
        """The coganchor call one turn is, on the thread it runs on."""
        try:
            said = self._called(take, settle, body, schema, goal=goal)
        except BaseException as why:  # noqa: BLE001 -- carried to the loop, not handled
            _posted(loop, _failed, landed, why)
        else:
            _posted(loop, _landed, landed, said)
        finally:
            with self._lock:
                if self._take == take:
                    self._running = False
            returned.set()

    def _called(
        self,
        take: int,
        settle: Callable[[], None] | None,
        body: str,
        schema: type[pydantic.BaseModel] | None,
        *,
        goal: bool,
    ) -> str:
        """Takes the turn, unless it was cut off before it could begin."""
        if settle is not None:
            settle()
        with self._lock:
            if self._take != take or self._cutting():
                return ""
            self._running = True
            self._rose = {}
        if goal:
            return self._session.pursue(body)
        said = ""
        for event in self._session.stream(body, schema=schema):
            if event.kind == "result":
                said = event.text
        return said.strip()

    def _settling(self) -> Callable[[], None] | None:
        """What to change about the CLI before the next turn, given the hooks hung now.

        Returns:
          What sets it up again, run on the turn's thread, or None where nothing changes.
        """
        self._settle_pre_tool_use()
        hung = frozenset(kind for kind in _STARTING if kind in self._hooks)
        if hung == self._hung:
            return None
        driver = self._driver
        was = self._agent.config
        now = settled(
            was,
            driver.harness,
            type(self._agent),
            self._permission,
            hung,
            tellable=driver.tellable,
            machine=self._placement.machine,
            workdir=str(self._placement.workdir),
            profile=driver.profile,
        )
        if now == was:
            self._hung = hung
            return None
        restart = getattr(now, "features", ()) != getattr(was, "features", ())
        agent, session = self._agent, self._session

        def settle() -> None:
            if restart:
                # The feature is an argument of the server, which is put down to start again.
                # Between two turns of this session, whose agent holds no other: nothing is
                # in flight on the server, and the next turn picks the conversation back up
                # on the one it starts.
                session.cut(why="started again to be asked what it asks")
            agent.reconfigure(now)
            # Written down only once it has been done, so that a turn which never got as far
            # as this leaves the next one to do it.
            self._hung = hung

        return settle

    # --------------------------------------------------------------------- what it spends

    def _heard(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Reads what the turn has spent whenever the CLI says anything."""
        del agent, session
        self._account(event.spent if event.kind == "result" else None)

    def _poll(self) -> None:
        """Reads what the turn has spent, and again in a while, while one is in flight."""
        if not self._flying:
            return
        self._account()
        self._timers.append(self._loop.call_later(_POLL, self._poll))

    def _account(self, answered: Mapping[str, float] | None = None) -> None:
        """Reports what the CLI has said was spent since the last time, and checks limits.

        Read off the conversation's meter, which most of coganchor's drivers feed as each
        request lands, and off the answer a turn ends on, which states the whole turn: what
        the answer states beyond what the meter rose by in that turn is counted then, which
        is all of it for a driver that feeds no meter and nothing for one that feeds it all.

        Args:
          answered: What the answer a turn just ended on says it spent, or None.
        """
        from hmz.coganchor import prices
        from hmz.coganchor.agents import Usage as Tokens

        spent = self._session.spent()
        with self._lock:
            sink, limits = self._sink, self._limits
            if sink is None or limits is None:
                return
            rose = {
                kind: tokens - self._seen.get(kind, 0.0)
                for kind, tokens in spent.items()
                if tokens > self._seen.get(kind, 0.0)
            }
            if rose:
                self._seen = dict(spent)
                for kind, tokens in rose.items():
                    self._rose[kind] = self._rose.get(kind, 0.0) + tokens
            if answered is not None:
                for kind, tokens in answered.items():
                    if (beyond := tokens - self._rose.get(kind, 0.0)) > 0:
                        rose[kind] = rose.get(kind, 0.0) + beyond
                self._rose = {}
            if not rose:
                return
            cost = prices.cost(Tokens(rose), self._agent.config.model) or 0.0
            written = (
                self._written + rose.get("output", 0.0) + rose.get("reasoning", 0.0)
            )
            tokens = int(written) - int(self._written)
            self._written = written
            now = time.monotonic()
            duration = now - self._last
            self._last = now
            self._cost += cost
            self._tokens += tokens
            self._duration += duration
            self._turn_cost += cost
            self._turn_tokens += tokens
            over: type[BudgetExceeded] | None = None
            if limits.graceful:
                pass  # the turn runs to its end, and the engine refuses the next one
            elif limits.cost is not None and self._turn_cost >= limits.cost:
                over = CostExceeded
            elif (
                limits.output_tokens is not None
                and self._turn_tokens >= limits.output_tokens
            ):
                over = OutputTokensExceeded
        sink.add(cost=cost, output_tokens=tokens, duration=duration)
        if over is not None:
            self._overrun(over)

    def _deadline(self) -> None:
        """The deadline of a turn that is not graceful, on the loop: ends it now."""
        if self._flying:
            self._overrun(DurationExceeded)

    def _overrun(self, kind: type[BudgetExceeded]) -> None:
        """Ends the turn for a limit it reached, from whichever thread noticed."""
        with self._lock:
            if self._over is not None or not self._flying:
                return
            self._over = kind
        self._cut("its budget is spent")

    def _exceeded(self, kind: type[BudgetExceeded], limits: Limits) -> BudgetExceeded:
        """The error for a limit the turn reached."""
        if kind is CostExceeded:
            return CostExceeded(
                f"the turn spent ${self._turn_cost:.4f} of ${limits.cost or 0.0:.4f}"
            )
        if kind is OutputTokensExceeded:
            return OutputTokensExceeded(
                f"the turn wrote {self._turn_tokens} of {limits.output_tokens or 0} "
                "output tokens"
            )
        return DurationExceeded("the turn ran past its deadline")

    # ------------------------------------------------------------------------- moving

    async def move(self, placement: Placement) -> bool:
        """Has the next turn work at `placement`; see the SPI's `SessionHandle.move`.

        On the same machine, in the same workdir, nothing moves. Anywhere else the
        conversation carries on as a fork of itself, from an agent of its own built there,
        refused where a fork there would be: the agent and conversation it leaves are kept
        until it closes, the fork being cut from them by the next turn. One that has taken
        no turn the CLI named has nothing to carry, and starts afresh there -- or, carrying
        on a kept conversation, as a fork of that one there.
        """
        self._check_open()
        was = self._placement
        if was.machine == placement.machine and was.workdir == placement.workdir:
            self._placement = placement
            return False
        driver = self._driver
        parent = None
        if self.id is not None:
            parent = driver.cut_from(self, placement, doing="move")
            self._carry_on = None
        agent, session = await driver.build(
            placement,
            permission=self._permission,
            skills=self._skills,
            hooks=self._hooks,
            parent=parent,
            carry_on=self._carry_on,
        )
        if self._closed:
            await asyncio.to_thread(_stopped, agent, session)
            raise SessionError("the session is closed")
        self._left.append((self._agent, self._session))
        if self._pre is not None:
            self._pre.off()
            self._pre = None
        self._agent, self._session = agent, session
        self._placement = placement
        # The conversation's own meter, which starts at nothing.
        with self._lock:
            self._seen = {}
            self._rose = {}
        self._hung = frozenset(kind for kind in _STARTING if kind in self._hooks)
        self._listen()
        return True

    # ------------------------------------------------------------ steering and stopping

    async def steer(self, prompt: str, *, queued: bool) -> None:
        """Puts a prompt into the turn in flight; see the SPI's `SessionHandle.steer`."""
        self._check_open()
        if SteeringAgentMixin not in self._driver.capabilities:
            raise UnsupportedOperation(f"{self._driver.harness} cannot be steered")
        with self._lock:
            if not self._flying:
                raise SessionError("no turn is in flight to steer")
            running = self._running
            if not (queued and running):
                self._steers.append(prompt)
                if not queued:
                    self._steer_cut = True
        if not queued:
            self._cut("steered")
            return
        if not running:
            return
        try:
            await asyncio.to_thread(self._session.interject, prompt)
        except Exception as missed:
            # No turn of the CLI's to put it into after all: it is taken as the next, while
            # this turn is still in flight to take one.
            with self._lock:
                if self._flying:
                    self._steers.append(prompt)
                    return
            raise SessionError("the turn ended before it could be steered") from missed

    def interrupt(self) -> None:
        """Stops the turn in flight, if any, from any thread. Idempotent."""
        with self._lock:
            if not self._flying or self._interrupted:
                return
            self._interrupted = True
        self._bridge.abandon()
        self._asking.abandon()
        self._cut("interrupted")

    def _cutting(self) -> bool:
        """Whether the coganchor call now starting is to be cut off. Held with the lock."""
        return self._interrupted or self._over is not None or self._steer_cut

    def _cut_off(self) -> bool:
        """Whether the coganchor call that just ended was cut off by the driver."""
        with self._lock:
            return self._cutting()

    def _cut(self, why: str) -> None:
        """Cuts the coganchor call off, and again until it has ended, from a thread."""
        with self._lock:
            if not self._running:
                return
            returned = self._returned
        threading.Thread(target=self._cutter, args=(returned, why), daemon=True).start()

    def _cutter(self, returned: threading.Event, why: str) -> None:
        """Cuts one coganchor call off until it has ended, which one cut may not do.

        Held to the call rather than to the turn: a call a cancelled turn stopped waiting for
        is cut again for as long as it runs, the turn after it having started behind it.
        """
        while True:
            with contextlib.suppress(Exception):
                self._session.cut(why=why)
            if returned.wait(_RECUT):
                return

    # ----------------------------------------------------------------------- closing

    def _check_open(self) -> None:
        """Refuses a session that has been closed.

        Raises:
          SessionError: If it has.
        """
        if self._closed:
            raise SessionError("the session is closed")

    async def close(self) -> None:
        """Ends the session, interrupting a turn in flight. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self._driver.forget(self)
        self.interrupt()
        if self._started:
            with contextlib.suppress(Exception):
                await self._fire(HookKind.SESSION_END)
        self._bridge.close()
        self._asking.close()
        await asyncio.to_thread(self._shut)

    def _shut(self) -> None:
        """Lets go of the conversations and of the CLIs serving them, on a thread."""
        _stopped(self._agent, self._session)
        for agent, session in self._left:
            _stopped(agent, session)
        self._left = []


def _stopped(agent: AgentBase, session: SessionBase) -> None:
    """Lets go of one conversation and of the CLI serving it, whatever either raises."""
    with contextlib.suppress(Exception):
        session.close()
    with contextlib.suppress(Exception):
        agent.stop()


def _default(kind: HookKind) -> HookResult:
    """What a moment comes to with no hook answering it."""
    from .spi import default_result

    return default_result(kind)


def _refuse_spent(limits: Limits) -> None:
    """Refuses a turn given nothing to spend.

    Raises:
      BudgetExceeded: The leaf for a limit already reached.
    """
    if limits.deadline is not None and limits.deadline <= time.monotonic():
        raise DurationExceeded("the turn's deadline has passed")
    if limits.cost is not None and limits.cost <= 0:
        raise CostExceeded("the turn has no money left to spend")
    if limits.output_tokens is not None and limits.output_tokens <= 0:
        raise OutputTokensExceeded("the turn has no output tokens left to write")


def _posted(
    loop: asyncio.AbstractEventLoop, what: Callable[..., None], *said: Any
) -> None:
    """Calls something on the loop from a thread, unless the loop has gone."""
    with contextlib.suppress(RuntimeError):
        loop.call_soon_threadsafe(what, *said)


def _landed[T](landed: asyncio.Future[T], answered: T) -> None:
    """Hands a thread's answer to whoever awaits it, unless nobody does any more."""
    if not landed.done():
        landed.set_result(answered)


def _failed(landed: asyncio.Future[Any], why: BaseException) -> None:
    """Raises a thread's failure where it is awaited, unless nobody awaits it any more."""
    if not landed.done():
        landed.set_exception(why)


def _retrieved(landed: asyncio.Future[Any]) -> None:
    """Takes a finished future's exception, so that one nobody awaited says nothing."""
    if not landed.cancelled():
        landed.exception()


# ----------------------------------------------------------------------------- outworlder


def open_outworlder(
    *,
    ask: Callable[[Question], str | None] | None = None,
    away: Callable[[str], bool] | None = None,
) -> HumanOutworlder:
    """Makes the driver for whoever is outside the run.

    Args:
      ask: Asks the person one question and waits for the answer, on a thread of its own:
        the question's text, the answers it offers where it offers any, and the `Outworlder`
        role asking as its `asker`. Answers None when nobody answered -- they walked away, or
        the interface closed. A text turn is one question; a turn asked for a schema is one
        question per field, as :class:`hmz.coganchor.agents.HumanAgent` asks them. None for
        nobody at all, which is `hmz exec`.
      away: Whether nobody is there now for one `Outworlder` role -- `/afk` -- asked whenever
        it matters. None for away exactly when there is nobody to `ask`.

    Returns:
      The driver.
    """
    return HumanOutworlder(ask=ask, away=away)


class HumanOutworlder:
    """Whoever is outside the run, asked through the person-shaped agent coganchor has.

    One person per `Outworlder` role, each stamping what it asks with the role, so that an
    interface holding several can say which of them is asking and take each one's answer.

    Implements :class:`~hmz.runtime.flowing.spi.OutworlderDriver`.
    """

    __slots__ = ("_ask", "_away", "_lock", "_people")

    def __init__(
        self,
        *,
        ask: Callable[[Question], str | None] | None,
        away: Callable[[str], bool] | None,
    ) -> None:
        """Initializes the driver; see :func:`open_outworlder`."""
        self._ask = ask
        self._away = away
        self._people: dict[str, HumanAgent] = {}
        self._lock = threading.Lock()

    def away_for(self, role: str) -> bool:
        """Whether nobody is there to answer as one role. It may change at any time."""
        if self._ask is None:
            return True
        return self._away(role) if self._away is not None else False

    async def run(
        self, prompt: str, output_schema: type[pydantic.BaseModel] | None, role: str
    ) -> str | pydantic.BaseModel:
        """Asks, and waits for the answer.

        Returns:
          The answer. An away outworlder answers at once: "" for text, and the schema built
          with no arguments where every field has a default.

        Raises:
          OutworlderAway: If it is away and the schema cannot be answered by default, or went
            away -- answered nothing -- while this was waiting.
        """
        if self.away_for(role):
            return away_answer(output_schema)
        said = await _threaded(lambda: self._asked(prompt, output_schema, role))
        if said is None:
            raise OutworlderAway("nobody answered")
        return said

    def _person(self, role: str) -> HumanAgent:
        """The person asked as one role, made the first time that role asks."""
        from hmz.coganchor.agents import HumanAgent

        ask = self._ask
        with self._lock:
            person = self._people.get(role)
            if person is None:
                person = self._people[role] = HumanAgent(name="outworlder")
                person.ask = (
                    None
                    if ask is None
                    else lambda question: ask(dataclasses.replace(question, asker=role))
                )
            return person

    def _asked(
        self, prompt: str, output_schema: type[pydantic.BaseModel] | None, role: str
    ) -> str | pydantic.BaseModel | None:
        """Puts the prompt to the person, on a thread of its own."""
        from hmz.coganchor.agents import Question

        person = self._person(role)
        if output_schema is None:
            return person.asked(Question(text=prompt))
        return person.new()(prompt, suppress=True, schema=output_schema)


def away_answer(
    output_schema: type[pydantic.BaseModel] | None,
) -> str | pydantic.BaseModel:
    """What an outworlder that is away answers.

    Args:
      output_schema: The model asked for, or None for text.

    Returns:
      "" for text, and the model built with no arguments where every field has a default.

    Raises:
      OutworlderAway: For a model some field of which has no default.
    """
    if output_schema is None:
        return ""
    if any(field.is_required() for field in output_schema.model_fields.values()):
        raise OutworlderAway(
            f"nobody is there to answer a {output_schema.__name__}, and it has no default"
        )
    return output_schema()


async def _threaded[T](work: Callable[[], T]) -> T:
    """Runs blocking work on a thread of its own, and answers with its result."""
    loop = asyncio.get_running_loop()
    landed: asyncio.Future[T] = loop.create_future()
    landed.add_done_callback(_retrieved)

    def carry() -> None:
        try:
            answered = work()
        except BaseException as why:  # noqa: BLE001 -- carried to the loop, not handled
            _posted(loop, _failed, landed, why)
        else:
            _posted(loop, _landed, landed, answered)

    threading.Thread(target=carry, name="outworlder", daemon=True).start()
    return await landed


if TYPE_CHECKING:
    from .spi import AgentDriver

    _: type[AgentDriver] = HarnessDriver
    __: type[SessionHandle] = HarnessSession
    ___: type[OutworlderDriver] = HumanOutworlder
