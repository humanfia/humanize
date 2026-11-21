"""Chats: one person talking to one coding agent, in one conversation, with no flow around it.

A chat is a session of its own (Section 8 of [CORE]), beside the epics flows run and none of
them. It has one assistant agent, one conversation, one workspace on this machine, and nothing
else: no params, no budget, no outworlder. What the person says is the next turn; what the
assistant answers is shown to them; a question it stops to ask mid-turn is put to them and
their next line answers it. The first turn is the one allowed to fail out loud, and ends the
chat failed; a later one that fails is said in the conversation and the chat goes on.

A chat takes the input its harness takes natively (Section 8.9 of [CORE]): what a line typed in
a chat means is :func:`resolve`'s answer, from the harness's catalog
(:class:`hmz.coganchor.agents.native.NativeCommand`), the names hmz keeps for itself
(:data:`RESERVED`), the flows installed here, and the chat's preference for a `$` name that is
both a native skill and a flow.

What a chat runs on is what a flow's run runs on, and nothing of the flow: the assistant is
opened as :class:`hmz.runtime.runner.Runner` opens an agent, in the workspace a run would call
its own -- or in a git worktree of it, where the chat was started in one -- and the chat is
written down in a record of its own, as a run's epic is (:mod:`hmz.runtime.epic`), and backed
up as a run's is -- with no engine, no budget and no journal between them. The assistant is
given every capability its harness has and the web besides, since a person talking to a coding
agent expects what they would get at its own prompt.

A chat is kept as it stands without anything being kept for it: the conversation's own files
are in the chat's directory already, where every session a run opens keeps them in its epic,
and the chat's record says which one was opened last. So a chat carried on is the same record
opened again, and the same conversation carried on from those files -- or, where that cannot
be, a new one in the same chat, which says why.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Sequence

    from hmz.coganchor.agents import Event
    from hmz.coganchor.agents.base import AgentBase, SessionBase
    from hmz.coganchor.agents.native import NativeCommand
    from hmz.flows import AskUserHookResult, FakeCli, FakeTool, Permission, Usage
    from hmz.runtime.backing import Keeping
    from hmz.runtime.epic import Drove, Epic, Ran
    from hmz.runtime.flowing import AgentDriver, EnvDriver, SessionHandle
    from hmz.runtime.flowing.harbors import Harbors
    from hmz.runtime.flowing.harnesses import Listener
    from hmz.runtime.flowing.specs import AgentSpec
    from hmz.runtime.flowing.spi import HookTable, Kept, Placement
    from hmz.runtime.flowing.viewing import HeldEnv
    from hmz.runtime.runner import Opened

#: What `$<name>` means where it names both a native skill and a flow.
Prefer = Literal["native", "flow"]

#: What a chat's assistant may touch unless it is said otherwise: its workspace to write in.
PERMISSION = "workspace-write"

#: The `/` commands every frontend keeps for hmz in a chat (Section 8.9 of [CORE]). Those the
#: harnesses also have -- `clear`, `resume`, `exit`, `quit`, `btw` -- do in a chat what the
#: harness's own command of that name does.
RESERVED: frozenset[str] = frozenset(
    {
        "btw",
        "chat",
        "clear",
        "epics",
        "exit",
        "flow",
        "prefer",
        "quit",
        "resume",
        "settings",
    }
)


@dataclass(frozen=True, slots=True)
class Resolved:
    """What one line typed in a chat is.

    Attributes:
      kind: `reserved`, an hmz command (`name` is which); `flow`, a flow to start (`name`
        is which, `rest` its task); `native`, the harness's own input, served as `entry`
        says; `refused`, input the chat cannot take, `why` saying why; `prose`, words said
        to the assistant.
      name: The command, flow or native name, where there is one.
      rest: What follows the name.
      entry: The catalog entry a `native` line is served by.
      why: Why a `refused` line was refused.
    """

    kind: Literal["reserved", "flow", "native", "refused", "prose"]
    name: str = ""
    rest: str = ""
    entry: NativeCommand | None = None
    why: str = ""


def resolve(
    line: str,
    *,
    catalog: Sequence[NativeCommand],
    flows: Collection[str],
    prefer: Prefer,
    listed: bool = True,
) -> Resolved:
    """Reads one line typed in a chat as Section 8.9 of [CORE] says to.

    Args:
      line: The line, stripped.
      catalog: The harness's native catalog for the conversation, empty for none.
      flows: The names a flow can be named by here, as a `$` line names one.
      prefer: The chat's preference, which decides a `$` name that is both.
      listed: Whether the catalog is all the harness lists, which it is once its conversation
        has taken a turn (:attr:`Chat.listed`). Until then a `/` name it does not hold yet is
        said to the harness, which may list it later, rather than refused.

    Returns:
      What the line is.
    """
    if not line or line[0] not in "/$!@":
        return Resolved("prose")
    sigil, body = line[0], line[1:]
    name, _, rest = body.partition(" ")
    rest = rest.strip()
    if sigil == "/" and name in RESERVED:
        return Resolved("reserved", name, rest)
    if sigil in "!@":
        entry = next((e for e in catalog if e.sigil == sigil), None)
        if entry is None:
            return Resolved("prose")
        if entry.how == "refuse":
            return Resolved("refused", "", body, entry, entry.about)
        return Resolved("native", "", body, entry)
    entry = next((e for e in catalog if e.sigil == sigil and e.name == name), None)
    if sigil == "$":
        flow = name in flows
        if entry is not None and (not flow or prefer == "native"):
            return Resolved("native", name, rest, entry)
        if flow:
            return Resolved("flow", name, rest)
        return Resolved("prose")
    if entry is not None:
        if entry.how == "refuse":
            return Resolved(
                "refused",
                name,
                rest,
                entry,
                f"/{name} is served only by the harness's own interactive interface",
            )
        return Resolved("native", name, rest, entry)
    if listed and any(e.sigil == "/" for e in catalog):
        return Resolved("refused", name, rest, None, f"no such command: /{name}")
    return Resolved("prose")


@dataclass(frozen=True, slots=True)
class Role:
    """What the assistant of a chat is beyond its agent: Ai-chan's, for her conversations.

    Attributes:
      workdir: Where its harness works, in place of the workspace.
      permission: What it may touch, in place of the workspace and the web.
      briefing: What it is told ahead of the first message of each new conversation.
      tools: The tools it is offered.
      clis: The command lines put on its PATH.
      close: What is done once the chat has ended.
    """

    workdir: Path
    permission: Permission
    briefing: str
    tools: tuple[FakeTool, ...] = ()
    clis: tuple[FakeCli, ...] = ()
    close: Callable[[], object] | None = None


@dataclass(frozen=True, slots=True)
class ChatSpec:
    """What a chat is started with.

    Attributes:
      workspace: The workspace it is had in, on this machine.
      agent: The assistant, as `-a` spells an agent (`claude/MODEL:high`).
      task: The first message; "" for a chat carried on that waits for the person's.
      resume: The directory of a chat to carry on, or None for a new one.
      prefer: This chat's own preference, or None to go by the person's setting.
      role: What the assistant is beyond its agent, or None for a plain chat's.
      permission: The preset of what the assistant may touch (Section 8.3.9 of [CORE]), or
        None for the one a chat carried on had, and `workspace-write` for a new one.
      worktree: Whether a new chat's assistant works in a new git worktree of the workspace
        (Section 8.3.13 of [CORE]); a chat carried on works where it worked.
      env: The env its assistant works in, as `-e` spells one after `<role>=` (Section
        8.3.15 of [CORE]), or "" for its workspace on this machine, and for a chat carried
        on where it worked.
    """

    workspace: Path
    agent: str
    task: str
    resume: Path | None = None
    prefer: Prefer | None = None
    role: Role | None = None
    permission: str | None = None
    worktree: bool = False
    env: str = ""


@dataclass(frozen=True, slots=True)
class ChatEnd:
    """How a chat ended.

    Attributes:
      at: Its directory.
      state: `stopped`, or `failed` where its first turn failed.
      why: What the harness said, for a chat that failed.
    """

    at: Path
    state: Literal["stopped", "failed"]
    why: str = ""


class Person(Protocol):
    """The person a chat is had with, as the host that holds it reaches them."""

    async def next(self, answered: str) -> str:
        """Shows the assistant's answer and waits for the next message; "" ends the chat."""
        ...

    async def ask(self, question: str, options: Sequence[str]) -> str | None:
        """Puts a question the assistant asked mid-turn; None where nobody answers it."""
        ...

    def shell(self, command: str, out: str, err: str, status: int) -> None:
        """Shows a `!` command run for the chat, with what it printed."""
        ...


#: The role the assistant is written down as, in the chat and to whatever is told of its sessions.
ASSISTANT = "assistant"

#: What a turn stopped by the person is answered with, the conversation going on.
STOPPED = "That turn was stopped."
#: What a `/model` or `/effort` said to a chat playing a role is answered.
_KEPT_NOUS = (
    "Ai-chan's nous does not change while the conversation lasts; "
    "to change it, make another conversation."
)

#: Why a chat is not carried on with an agent of another harness (Section 8.3.18 of [CORE]).
_KEPT_HARNESS = (
    "a chat keeps its harness, and this one is had with {had}; "
    "start a new chat to talk to {wanted}"
)
#: Why it is not carried on as another account.
_KEPT_ACCOUNT = (
    "a chat keeps the account it runs as, {had}; start a new chat to run as {wanted}"
)
#: Why one whose harness carries no conversation on keeps its model and effort.
_KEPT_MODEL = (
    "{harness} cannot carry a conversation on with another model or effort; "
    "start a new chat for another"
)
#: Why one whose harness is told neither keeps them.
_UNTOLD_MODEL = (
    "{harness} is told no model and no effort, so this chat keeps its own; "
    "start a new chat for another"
)

#: Why a chat with a turn open is not moved (Section 8.3.16 of [CORE]).
TURN_OPEN = "a turn is open; move the chat once it is done"
#: Why a chat whose assistant plays a role is not moved.
_KEPT_PLACE = "an Ai-chan conversation works where it was made"

#: How long a `!` command may run before it is killed: long enough for a build or a test run, not
#: so long that a command waiting on input it will never get holds the chat for good.
SHELL_TIMEOUT = 600.0


class KeptAs(ValueError):  # noqa: N818 -- named for what happened, as Refused is
    """A chat is not carried on as the agent named: it keeps what the message says."""


class Chat:
    """One chat, as the host that holds it runs it.

    - :meth:`run` takes the first turn from `spec.task` and every later one from
      :meth:`Person.next`, until that answers "" or the host goes away.
    - A line the person says is read by :func:`resolve`; a `native` one is taken as a turn
      marked native (`TurnRequest(native=True)`), except a `!` line the catalog says to
      emulate, which is run in the workspace under the assistant's confinement, shown with
      :meth:`Person.shell`, and carried into the next turn as `<bash-input>`,
      `<bash-stdout>` and `<bash-stderr>` blocks ahead of its message -- not a turn, so the
      person is asked for their next line with nothing to show. A `refused` line is said back
      in the conversation. A `reserved` or `flow` one is a frontend's to serve and never
      reaches a chat; one that does is said to the assistant as words.
    - The conversation is kept in the chat's directory as it stands when the chat ends, and
      a chat carried on (`spec.resume`) goes on in the same record and the same conversation,
      or says why it cannot and goes on in a new one.
    - A chat carried on with nothing said (`spec.resume` and no `spec.task`) holds its
      workspace and waits, between turns, for the first thing said: nothing is opened and
      nothing written into its record until then, and an empty message ends it as it was.
    - The chat's record says `prefer` where this chat has its own, `permission` where it is
      not `workspace-write`, and `workdir` where its assistant works in a worktree.
    - The assistant is held to the chat's permission, a preset with the web besides. One set
      while the chat goes on (:meth:`permits`) is taken up ahead of the next turn: the
      conversation is closed and carried on in one opened under it, as a chat carried on is.
    - The assistant works in the chat's env: its workspace on this machine, a worktree of it,
      or the env the chat was started in or last moved to (:meth:`move`), which its record
      says as `env`. Moved between turns, the conversation is closed and carried on in one
      opened there, or in a new one that says why (Section 8.3.15 of [CORE]).

    Raises:
      ValueError: For a permission that is no preset.
    """

    def __init__(self, spec: ChatSpec, *, person: Person) -> None:
        """Sets a chat up; nothing is started until :meth:`run`.

        Args:
          spec: What it is started with.
          person: Who it is had with.
        """
        self.spec = spec
        self.person = person
        self._prefer: Prefer | None = spec.prefer
        #: The preset the assistant is held to, or None until one is said or carried on.
        self._permission = None if spec.permission is None else preset(spec.permission)
        #: Held while the preference is set and the record opened: the host may set one from
        #: any thread while the chat runs on its own.
        self._lock = threading.Lock()
        self._epic: Epic | None = None
        #: Whether the chat has ended, after which nothing more is written into its record.
        self._ended = False
        self._talk: _Talk | None = None
        #: The chat carried on with nothing said yet, and its workspace: held, with nothing
        #: written of it, until something is said.
        self._stood: tuple[Path, HeldWorkspace] | None = None
        #: The env the assistant works in now, every env opened for the chat, which are
        #: closed as it ends, and what its record says of where it works, "" for nothing.
        self._local: EnvDriver | None = None
        self._owned: list[EnvDriver] = []
        self._env = ""
        #: The assistant, once :meth:`run` has made it, and the loop the chat runs on.
        self._driver: AgentDriver | None = None
        #: What the assistant is written down as now, and the harness runtimes it is put on.
        self._runs: Drove | None = None
        self._harbors: Harbors | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._listeners: list[Listener] = []
        self._opened: list[Opened] = []
        self._spending: _Spending | None = None

    @property
    def prefer(self) -> Prefer | None:
        """This chat's own preference, or None where it goes by the person's setting."""
        return self._prefer

    @property
    def at(self) -> Path | None:
        """The chat's directory once :meth:`run` has opened it, and None before.

        One carried on with nothing said is in the directory it is to go on in, unopened.
        """
        epic, stood = self._epic, self._stood
        if epic is not None:
            return epic.path
        return None if stood is None else stood[0]

    def prefers(self, prefer: Prefer) -> None:
        """Sets this chat's own preference, recorded in the chat.

        Written as a `set` of its record once the chat is under way, and in its `began` where it
        is set before then, so that a chat carried on goes on preferring what it did.

        Args:
          prefer: What `$<name>` means here where it names both.

        Raises:
          ValueError: For a preference that is neither `native` nor `flow`.
        """
        if prefer not in ("native", "flow"):
            raise ValueError(f"a chat prefers native or flow, not {prefer!r}")
        with self._lock:
            self._prefer = prefer
            # Not once it has ended, whose record says so last: a chat carried on is told
            # its preference again as it is opened.
            if self._epic is not None and not self._ended:
                self._epic.write("set", prefer=prefer)

    @property
    def permission(self) -> str | None:
        """The preset its assistant is held to, or None where it is held to its role's."""
        return None if self.spec.role is not None else self._permission or PERMISSION

    def permits(self, permission: str) -> None:
        """Sets what the assistant may touch from its next turn on, recorded in the chat.

        Args:
          permission: A preset: `read-only`, `workspace-write` or `danger-full-access`.

        Raises:
          ValueError: For anything else, and for a chat whose assistant plays a role, which
            is held to its role's.
        """
        if self.spec.role is not None:
            raise ValueError("this chat keeps the permission it was made with")
        permission = preset(permission)
        with self._lock:
            # One set before a chat carried on has read what it had is not that one unsaid.
            if permission == self._permission:
                return
            self._permission = permission
            if self._epic is not None and not self._ended:
                self._epic.write("set", permission=permission)

    @property
    def driven(self) -> Drove | None:
        """The assistant as the chat's record says it now; None before :meth:`run` makes it."""
        return self._runs

    def runs(self, agent: str) -> None:
        """Carries the chat on with another model, another effort, or both, from its next turn.

        Recorded in the chat at once, a chat carried on with nothing said among them, and
        taken up ahead of the next turn: by the conversation's own `/model` and `/effort`
        where its harness calls them, and else by closing the conversation and carrying it on
        in one opened by the same harness, as the same account, at that model and effort
        (Section 8.3.18 of [CORE]).

        Args:
          agent: The agent, as `-a` spells one after `<role>=`: of the chat's own harness and
            account.

        Raises:
          KeptAs: For an agent of another harness or account, a harness that carries no
            conversation on or is told no model, an Ai-chan conversation, and a chat not
            going.
          ValueError: For an agent that is not one.
        """
        from hmz.runtime.epic import note

        if self.spec.role is not None:
            raise KeptAs(_KEPT_NOUS)
        with self._lock:
            now = self._runs
            if self._ended or now is None:
                raise KeptAs("no chat is going here")
            wanted = carried_as(now, agent)
            if _at(wanted) == _at(now):
                return
            self._runs = wanted
            self.spec = replace(self.spec, agent=wanted.spec)
            if self._epic is not None:
                self._epic.write("set", agents=[wanted._asdict()])
            elif self._stood is not None:
                # Carried on with nothing said: its record is not open, and says so itself.
                note(self._stood[0], "set", agents=[wanted._asdict()])

    def ran_as(self, now: Drove, *, written: bool = False) -> None:
        """Holds what the assistant runs as now, written in the chat's record where asked."""
        with self._lock:
            self._runs = now
            self.spec = replace(self.spec, agent=now.spec)
            if written and self._epic is not None and not self._ended:
                self._epic.write("set", agents=[now._asdict()])

    async def drives(self, wanted: Drove) -> AgentDriver:
        """A driver of the assistant at another model or effort, settled for where it works.

        Raises:
          ValueError: For one its CLI cannot be configured at.
          HarnessError: For one that cannot be put where the chat works.
        """
        from hmz.runtime.runner import agent_drivers

        harbors, local = self._harbors, self._local
        if harbors is None or local is None:
            raise ValueError("no chat is going here")
        said = _assistant(wanted.spec)
        driver = agent_drivers({ASSISTANT: said}, harbors, wanted.name)[ASSISTANT]
        try:
            watch = getattr(driver, "watch", None)
            if callable(watch):
                for listener in self._listeners:
                    watch(listener)
            await _placeable(driver, local, self.granted())
        except BaseException:
            with contextlib.suppress(Exception):
                await driver.close()
            raise
        return driver

    async def driven_by(self, driver: AgentDriver) -> None:
        """Has `driver` be the assistant's from now on, the one before it closed."""
        with self._lock:
            had, self._driver = self._driver, driver
        if had is not None and had is not driver:
            with contextlib.suppress(Exception):
                await had.close()

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """The loop the chat runs on, which :meth:`move` is awaited on; None before it runs."""
        return None if self._ended else self._loop

    async def move(self, env: str) -> str:
        """Moves the chat to another env, between turns; awaited on the chat's own loop.

        The env is opened and reached, and the assistant's harness settled for it, before
        anything of the chat changes: one that cannot take the chat leaves it where it was.
        Then the conversation is closed and carried on in one opened there, as a chat carried
        on is; where it cannot be carried on there, a new one says why ahead of its first
        answer (Section 8.7.6 of [CORE]). The move is recorded in the chat as `env`, once
        something has been said in a chat carried on with nothing said.

        Args:
          env: Where to, as `-e` spells an env after `<role>=`: `local/<dir>`,
            `ssh@<runtime>/<dir>`, `docker[@<runtime>]/<dir>` and so on.

        Returns:
          Where the chat now works, spelled likewise.

        Raises:
          Busy: While a turn is open.
          ValueError: For an env that cannot be read, reached or made, one the assistant's
            harness cannot be put in, an Ai-chan conversation, and a chat not going.
        """
        from hmz.flows import FlowException

        if self.spec.role is not None:
            raise ValueError(_KEPT_PLACE)
        driver, talk = self._driver, self._talk
        if self._ended or driver is None or self._local is None:
            raise ValueError("no chat is going here")
        if talk is not None and talk.busy:
            raise Busy(TURN_OPEN)
        try:
            local = await _env_at(env)
        except FlowException as why:
            raise ValueError(str(why)) from why
        try:
            await _placeable(driver, local, self.granted())
            if talk is not None:
                await talk.moved(local)
        except FlowException as why:
            with contextlib.suppress(Exception):
                await local.close()
            raise ValueError(str(why)) from why
        except BaseException:
            with contextlib.suppress(Exception):
                await local.close()
            raise
        said = _spelt(local)
        with self._lock:
            self._owned.append(local)
            self._local, self._env = local, said
            if self._stood is not None and talk is None:
                # Nothing is written of a chat carried on with nothing said (Section 8.7.4
                # of [CORE]): its record says so once something is.
                self._stood = (
                    self._stood[0],
                    HeldWorkspace(local, asyncio.get_running_loop()),
                )
            elif self._epic is not None and not self._ended:
                self._epic.write("set", env=said)
        return said

    @property
    def env(self) -> str:
        """The env its assistant works in now, as `-e` spells one after `<role>=`.

        "" where it was given none and moved to none, and so works where its record says. One
        moved while it is carried on with nothing said is said here before its record says it.
        """
        return self._env

    def granted(self) -> Permission:
        """What the assistant may touch now: its role's, else its preset and the web."""
        from hmz.flows import Permission

        role = self.spec.role
        if role is not None:
            return role.permission
        return Permission(preset=self._permission or PERMISSION, network=True)

    @property
    def listed(self) -> bool:
        """Whether its catalog is all the harness lists: once its conversation took a turn.

        Some harnesses list their commands only as a conversation opens, and some only when
        asked once one is open, so before a turn the catalog may hold some of them and not the
        rest (Section 8.9.13 of [CORE]).
        """
        talk = self._talk
        return talk is not None and talk.taken

    @property
    def between(self) -> bool:
        """Whether it is between turns: no turn of its assistant is being taken.

        So it is while the person is waited on and while a `!` command of theirs runs, which
        opens no turn (Section 8.9.6 of [CORE]); not from a message given it to its answer.
        """
        talk = self._talk
        return not self.spec.task if talk is None else talk.between

    def natives(self) -> list[NativeCommand]:
        """The assistant's native catalog, as its conversation stands; empty before it opens."""
        talk = self._talk
        handle = None if talk is None else talk.handle
        return [] if handle is None else list(handle.natives())

    def watch(self, listener: Listener) -> None:
        """Has everything the assistant says, as it says it, reach `listener`.

        As :meth:`hmz.runtime.runner.Runner.watch` has it for a run's agents; asked before
        :meth:`run`, which is where the assistant is made.

        Args:
          listener: What to tell, from whichever thread its CLI is read on.
        """
        self._listeners.append(listener)

    def opened(self, callback: Opened) -> None:
        """Has each conversation of the assistant told to `callback` as it is opened.

        As :meth:`hmz.runtime.doing.running.Run.opened` has it for a run; asked before
        :meth:`run`, and told beside what :meth:`run` is handed as `opened`.

        Args:
          callback: What to tell: the role, the agent, its session and where it works.
        """
        self._opened.append(callback)

    @property
    def usage(self) -> Usage:
        """What the conversation has spent so far: nothing before :meth:`run` opens it."""
        from hmz.flows import Usage

        spending = self._spending
        return Usage() if spending is None else spending.usage()

    @property
    def envs(self) -> HeldWorkspace | None:
        """The workspace the chat works in, listed as a run's environments are for env panels.

        None before the chat has opened it, and once it has ended. One carried on with
        nothing said holds it from then, before anything is said.
        """
        talk, stood = self._talk, self._stood
        if self._ended:
            return None
        if talk is not None:
            return talk.held
        return None if stood is None else stood[1]

    def interrupt(self) -> bool:
        """Stops the turn going, if one is, leaving the chat between turns; from any thread.

        Returns:
          Whether a turn was going.
        """
        talk = self._talk
        return talk is not None and talk.interrupt()

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """The coganchor agent behind the conversation open now, where one is behind it."""
        talk = self._talk
        handle = None if talk is None else talk.handle
        agent = getattr(handle, "agent", None)
        return () if agent is None else (agent,)

    async def run(
        self,
        *,
        opened: Opened | None = None,
        started: Callable[[Path], None] | None = None,
    ) -> ChatEnd:
        """Has the chat, from its first message to its last.

        Args:
          opened: What is told of each conversation of the assistant as it is opened, as
            :meth:`hmz.runtime.runner.Runner.arun` tells it, or None.
          started: What is handed the chat's directory once the chat is written down in it.

        Returns:
          How it ended.

        Raises:
          Refused: Before anything is written down, for an agent that cannot be read, names
            an account nobody saved, cannot be configured, or cannot be put where the
            workspace is, or in a worktree where none can be added; and for a chat to carry
            on that is not one, is going on already, or cannot be continued here (Section
            8.7.7 of [CORE]).
          HarnessError: Where the first turn of a chat that is not carried on fails, with what
            the harness said; the chat is ended failed first.
        """
        from hmz.flows import FlowException
        from hmz.runtime.backing import Keeping, chosen
        from hmz.runtime.epic import Epic
        from hmz.runtime.flowing import local_env
        from hmz.runtime.runner import Refused, agent_drivers, closed, harbors, spent

        spec = self.spec
        workspace = spec.workspace.resolve()
        said = _assistant(spec.agent)
        carried, before = _carried(spec.resume, workspace)
        try:
            backup = chosen(None)
        except ValueError as why:
            raise Refused(str(why)) from why
        self._harbors = held = harbors()
        driver: AgentDriver | None = None
        #: Where the assistant works, where that is a worktree rather than the workspace.
        workdir = "" if before is None else before.workdir
        #: The env it works in, where that was said: now, or as its record last gave it.
        env = spec.env or ("" if before is None else before.env)
        self._loop = asyncio.get_running_loop()
        try:
            # A chat carried on is the one assistant still, so its sessions go on being
            # written down under the name its record gave it.
            named = before.agents[-1].name if before and before.agents else ""
            driver = agent_drivers({ASSISTANT: said}, held, named)[ASSISTANT]
            for listener in self._listeners:
                watch = getattr(driver, "watch", None)
                if callable(watch):
                    watch(listener)
            if spec.role is not None or not env:
                local = local_env(
                    spec.role.workdir if spec.role else Path(workdir or workspace)
                )
                env = ""
            else:
                local = await _env_at(env)
            self._owned.append(local)
            _priced()
            with self._lock:
                if self._permission is None:
                    # What a chat carried on had, where its record gives a preset still.
                    self._permission = (
                        PERMISSION if before is None else _recorded(before)
                    )
            await _placeable(driver, local, self.granted())
            if spec.worktree and before is None:
                # Last, once nothing else refuses the chat: a worktree made is never removed.
                local = await local.derive_worktree(ref=None, dir=None)
                workdir = str(local.placement().workdir)
            if env:
                # As its record says it: the worktree made there, where one was.
                env = _spelt(local)
            with self._lock:
                self._driver, self._local, self._env = driver, local, env
                self._runs = _drove(said, driver.name)
        except BaseException as why:
            # Refused before the chat began: what it was given goes either way.
            await asyncio.shield(closed((driver, *self._owned), held))
            if isinstance(why, FlowException):
                raise Refused(str(why)) from why
            raise
        try:
            if carried is not None and not spec.task and spec.role is None:
                # Carried on with nothing said: its workspace is held, and nothing of it is
                # opened or written down, until something is said, which carries it on.
                self._stood = carried, HeldWorkspace(local, asyncio.get_running_loop())
                said_next = await self.person.next("")
                if not said_next:
                    with self._lock:
                        self._ended = True
                    await asyncio.shield(closed((driver, *self._owned), held))
                    return ChatEnd(carried, "stopped")
                self.spec = spec = replace(self.spec, task=said_next)
                # Read again: it may have been written in, or carried on elsewhere, since.
                carried, before = _carried(spec.resume, workspace)
                wanted = self._runs
                if _at(wanted) != _at(_drove(said, driver.name)):
                    # Given another model or effort while nothing was said: carried on at it.
                    said = _assistant(spec.agent)
                    try:
                        await self.driven_by(await self.drives(wanted))
                    except FlowException as why:
                        raise Refused(str(why)) from why
                    driver = self._driver or driver
            with self._lock:
                # Where it stands now: it may have been moved while nothing was said.
                local, env = self._local or local, self._env
                if self._prefer is None and before is not None and before.prefer:
                    self._prefer = "flow" if before.prefer == "flow" else "native"
                self._epic = epic = Epic(
                    "",
                    spec.task,
                    workspace,
                    kind="chat",
                    agents=[_drove(said, driver.name)],
                    backup=backup,
                    picked_up=carried,
                    reopened=carried is not None,
                    prefer=self._prefer,
                    permission=None
                    if self.permission in (None, PERMISSION)
                    else self.permission,
                    workdir="" if env else workdir,
                    env=env,
                )
        except BaseException:
            await asyncio.shield(closed((driver, *self._owned), held))
            raise
        keeping: Keeping | None = None
        try:
            with epic:
                keeping = Keeping(epic.path, backup)
                if before is not None:
                    with self._lock:
                        _set_again(
                            epic,
                            before,
                            _drove(said, driver.name),
                            self._prefer,
                            self.permission,
                            env,
                        )
                if started is not None:
                    started(epic.path)
                self._spending = spending = _Spending()
                told = [*self._opened, *(() if opened is None else (opened,))]

                def telling(
                    role: str,
                    agent: AgentBase,
                    session: SessionBase,
                    where: Placement | None,
                ) -> None:
                    for callback in told:
                        callback(role, agent, session, where)

                self._talk = talk = _Talk(
                    self,
                    driver,
                    local,
                    epic,
                    keeping,
                    spending,
                    telling,
                    tuple(self._listeners),
                )
                try:
                    await talk.had(before)
                finally:
                    spent(epic, spending.usage())
                # Ended because the person stopped talking, which is how every chat that does
                # not fail ends: never `done` (Section 8.5.3 of [CORE]).
                epic.stopped()
        finally:
            with self._lock:
                self._ended = True
            try:
                # The one it has now: carried on at another model, it was given another.
                await asyncio.shield(closed((self._driver, *self._owned), held))
            finally:
                if keeping is not None:
                    keeping.ended()
                if spec.role is not None and spec.role.close is not None:
                    spec.role.close()
        return ChatEnd(epic.path, "stopped")


class HeldWorkspace:
    """The one environment a chat holds, its workspace, as a run's are listed for env panels.

    Attributes:
      loop: The loop its driver lives on.
    """

    def __init__(self, local: EnvDriver, loop: asyncio.AbstractEventLoop) -> None:
        """Holds the chat's workspace and the loop it was opened on."""
        from hmz.runtime.flowing.viewing import HeldEnv

        self.loop = loop
        where = local.placement()
        chain = f"{where.backend}@{where.provider}{where.workdir}"
        self._held = (HeldEnv("workspace", chain, None, local, frozenset()),)

    def held_envs(self) -> tuple[HeldEnv, ...]:
        """The chat's workspace, alone. From any thread."""
        return self._held

    def env_roles(self) -> dict[str, EnvDriver]:
        """The chat's workspace, by the name `hosts.env.*` know it by. From any thread."""
        return {one.role: one.driver for one in self._held}


class _Talk:
    """One opening of a chat: its turns, its `!` commands and its conversations."""

    def __init__(
        self,
        chat: Chat,
        driver: AgentDriver,
        local: EnvDriver,
        epic: Epic,
        keeping: Keeping,
        spending: _Spending,
        opened: Opened | None,
        watching: Sequence[Listener] = (),
    ) -> None:
        """Holds what the conversation is had with, and who watches it."""
        self._chat = chat
        self._driver = driver
        self._local = local
        self.held = HeldWorkspace(local, asyncio.get_running_loop())
        self._epic = epic
        self._keeping = keeping
        self._spending = spending
        self._opened = opened
        self._watching = watching
        self._hooks = self._hung()
        #: The preset the conversation open now is held to: the chat's, as it was opened.
        self._preset: str | None = None
        #: The conversation last written down for a driver that does not write its own down.
        self._noted = ""
        #: The conversation open now, once one is: what the chat's catalog is asked of.
        self.handle: SessionHandle | None = None
        #: Whether a turn of it has been taken, by when its harness has listed its catalog.
        self.taken = False
        #: Whether a turn is going, and whether the person stopped the one that was.
        self.turning = False
        #: Whether it is between turns: until its first where it was opened with nothing said,
        #: and after each, through every `!` command and line refused, until the next.
        self.between = not chat.spec.task
        self._interrupted = False
        #: Held from each message said to the answer shown for it, and while the chat is
        #: moved: a chat is moved between turns alone, and no turn opens under a move.
        self._busy = asyncio.Lock()
        #: The conversation a move opened, what it says ahead of its first answer, and whether
        #: it carries the one before on: taken up ahead of the next turn.
        self._moved: tuple[SessionHandle, str, bool] | None = None
        #: Whether the turn going was shown as failed by its own harness.
        self._failed = False
        watch = getattr(driver, "watch", None)
        if callable(watch):
            watch(self._heard)
        #: The assistant as last written down: its CLI, model and effort.
        self._as = _at(chat.driven or _drove(_assistant(chat.spec.agent), driver.name))

    @property
    def busy(self) -> bool:
        """Whether a message is being served, or the chat moved: not between turns."""
        return self._busy.locked()

    async def _next(self, answered: str) -> str:
        """Shows an answer and waits for the next message, between turns meanwhile."""
        self._busy.release()
        try:
            return await self._chat.person.next(answered)
        finally:
            await self._busy.acquire()

    async def moved(self, local: EnvDriver) -> None:
        """Carries the conversation on in another env, or in a new one there that says why.

        Args:
          local: The env, reached, which the assistant's harness is settled for.

        Raises:
          Busy: While a message is being served.
          FlowException: Where no conversation can be opened there at all: the chat then
            goes on where it was, in a conversation opened there again.
        """
        from hmz.runtime.epic import read

        if self._busy.locked():
            raise Busy(TURN_OPEN)
        async with self._busy:
            was, held = self._local, self.held
            handle = self.handle
            if handle is not None:
                await self._close(handle)
            # Off the loop, which is the turns': the whole record is read off disk.
            ran = await asyncio.to_thread(read, self._epic.path)
            kept, why = (
                _conversation(ran) if ran is not None and ran.sessions else (None, "")
            )
            self._local = local
            self.held = HeldWorkspace(local, asyncio.get_running_loop())
            try:
                self._moved = await self._carried(kept, why)
            except BaseException:
                self._local, self.held = was, held
                # Where it was, as it was: what refuses that too is said by its next turn.
                with contextlib.suppress(Exception):
                    self._moved = await self._carried(kept, why)
                raise

    async def had(self, before: Ran | None) -> None:
        """Has every turn of the conversation, from the first message to the empty one.

        Args:
          before: The chat this carries on, as its record read before it was opened again,
            or None for a new one.

        Raises:
          HarnessError: Where the first turn of a chat that is not carried on fails, or a
            conversation cannot be opened at all.
        """
        from hmz.flows import HarnessError, SessionError

        chat = self._chat
        person = chat.person
        kept, unkept = (None, "") if before is None else _conversation(before)
        await self._busy.acquire()
        try:
            handle, unkept, carrying = await self._carried(kept, unkept)
        except BaseException:
            self._busy.release()
            raise
        opening = before is None
        #: The `!` commands run since the last turn, carried into the next as blocks.
        ran: list[str] = []
        message = chat.spec.task
        role = chat.spec.role
        #: Whether the conversation open now was told its role's briefing.
        briefed = role is None or carrying
        if not message and role is not None:
            # Her conversation, with nothing said yet: between turns, waiting on the person.
            message = await self._next(unkept)
            unkept = ""
        try:
            while message:
                if self._moved is not None:
                    # Moved since the last turn: the conversation opened where it went.
                    (handle, moved, carrying), self._moved = self._moved, None
                    unkept = _said(unkept, moved)
                    briefed = role is None or carrying
                if self._lags():
                    # Given another model or effort since this conversation was opened: its
                    # harness's own commands move it to them, where it has them.
                    await self._shift()
                if chat.permission != self._preset or self._lags():
                    # Set since this conversation was opened: carried on in one held to it,
                    # opened at the model and effort given.
                    handle, unkept, carrying = await self._reopened(handle, unkept)
                line = message.strip()
                flows, prefer = (
                    # Off the loop: both are read off disk, and the loop is the turns'.
                    await asyncio.to_thread(self._dollar, line)
                    if line.startswith("$")
                    else (frozenset[str](), "native")
                )
                read = resolve(
                    line,
                    catalog=chat.natives(),
                    flows=flows,
                    prefer=prefer,
                    listed=chat.listed,
                )
                entry = read.entry
                if (why := _refused(read, line, role)) is not None:
                    message = await self._next(_said(unkept, why))
                    unkept = ""
                    continue
                if (
                    read.kind == "native"
                    and entry is not None
                    and entry.sigil == "!"
                    and entry.how == "emulate"
                ):
                    status, out, err = await self._shell(handle, read.rest)
                    person.shell(read.rest, out, err, status)
                    ran.append(_blocks(read.rest, out, err))
                    message = await self._next("")
                    continue
                native = read.kind == "native"
                # A `/` or `$` line is the harness's own command only where it starts the
                # turn, so what `!` ran waits for the turn after it.
                ahead = bool(ran) and not (native and line[:1] in "/$")
                prompt = "\n".join([*ran, line]) if ahead else line
                # Ahead of words alone: a native command starts its turn, or is no command.
                telling = not briefed and role is not None and not native
                if telling and role is not None:
                    prompt = f"{role.briefing}\n\n{prompt}"
                # Called of the driver, and answered by it: the harness may be asked nothing.
                set_ = native and line.split(maxsplit=1)[0] in ("/model", "/effort")
                try:
                    answered = await self._turn(handle, prompt, native=native)
                    if set_:
                        self._changed(handle)
                except HarnessError as failed:
                    if self._interrupted:
                        # Stopped by the person: the conversation goes on between turns.
                        self._interrupted = False
                        opening = carrying = False
                        message = await self._next(_said(unkept, STOPPED))
                        unkept = ""
                        continue
                    if opening:
                        raise
                    if carrying and isinstance(failed, SessionError):
                        # Only a conversation that cannot be carried on is put down for a new
                        # one: a turn that failed -- a limit, the network -- is said instead.
                        unkept = _restarted(str(failed))
                        handle = await self._renewed(handle)
                        briefed = role is None
                        carrying = False
                        continue
                    self._fails(handle, str(failed))
                    answered = f"That turn could not be taken: {failed}"
                else:
                    # Not by a `/model` or `/effort`, which a harness lists nothing for: what
                    # it has not listed yet is still passed as text (`core.md` 8.9.13).
                    self.taken = self.taken or not set_
                    briefed = briefed or telling
                    if ahead:
                        ran.clear()
                opening = carrying = False
                message = await self._next(_said(unkept, answered))
                unkept = ""
        finally:
            if self._busy.locked():
                self._busy.release()
            # The one open now: a move since the last turn opened another.
            await asyncio.shield(self._close(self.handle or handle))

    def _heard(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Notes a failure the harness showed itself, from the thread its CLI is read on."""
        del agent, session
        if event.kind == "failed":
            self._failed = True

    def _fails(self, handle: SessionHandle, why: str) -> None:
        """Shows a later turn's failure to whoever watches the chat, once.

        Said in the conversation too (Section 8.4.10 of [CORE]), which goes on; but a
        frontend that follows one turn, as `hmz chat` does (Section 15.3.3 of [CLI]), tells
        a turn that failed from one that answered by this. Most harnesses raise without
        showing it; one that showed it is not shown again.
        """
        from hmz.coganchor.agents import Event

        agent = getattr(handle, "agent", None)
        if self._failed or agent is None:
            return
        session = getattr(handle, "coganchor", None)
        for listener in self._watching:
            listener(agent, session, Event(kind="failed", text=why))

    def _changed(self, handle: SessionHandle) -> None:
        """Writes the assistant down again where a `/model` or `/effort` changed it.

        As the chat's agent from then on: recorded in the chat as a `set` (Section 6.12.6 of
        [FILES]) and remembered for the workspace's next chat (Section 8.9.5 of [CORE]).
        """
        from hmz.coganchor.backends import AUTO
        from hmz.runtime.epic import Drove
        from hmz.runtime.kept import Runs
        from hmz.runtime.settings import Settings

        running = _running(handle)
        if running is None:
            return
        model, effort = running
        cli = self._as[0]
        if (cli, model, effort) == self._as:
            return
        self._as = (cli, model, effort)
        provider = self._driver.provider
        now = Drove(ASSISTANT, cli, model, effort, provider, self._driver.name)
        self._chat.ran_as(now, written=True)
        spec = f"{cli}/{model}" + (f":{effort}" if effort != AUTO else "")
        with contextlib.suppress(Exception):
            Settings(self._chat.spec.workspace).chat_agent = Runs(spec, provider)

    def _dollar(self, line: str) -> tuple[frozenset[str], Prefer]:
        """What a `$` line is read against: the flow it names, if any, and the preference.

        The chat's own preference, else the person's setting, read as it is now.
        """
        own = self._chat.prefer
        if own is None:
            from hmz.runtime.settings import Settings

            own = Settings(self._chat.spec.workspace).chat_prefer
        return _flows(line), own

    def _hung(self) -> HookTable:
        """The hooks hung on the assistant: a question it asks mid-turn, put to the person."""
        from hmz.flows import AskUserHookAgentMixin, AskUserHookResult, HookKind
        from hmz.runtime.flowing.spi import HookTable

        hooks = HookTable()
        if AskUserHookAgentMixin not in self._driver.capabilities:
            # A harness that cannot stop to ask has nothing to hang it on.
            return hooks
        person = self._chat.person

        async def asked(
            handle: SessionHandle, fields: dict[str, Any]
        ) -> AskUserHookResult:
            del handle
            options = tuple(str(one) for one in fields.get("options") or ())
            answer = await person.ask(str(fields.get("question") or ""), options)
            return AskUserHookResult(answer=answer or None)

        hooks.set(HookKind.ASK_USER, asked)
        return hooks

    async def _open(self, kept: Kept | None) -> SessionHandle:
        """Opens a conversation of the assistant in the workspace, carrying `kept` on.

        Raises:
          HarnessError: The leaf for why it could not be opened.
        """
        placement = self._local.placement()
        role = self._chat.spec.role
        self._preset = self._chat.permission
        permission = self._chat.granted()
        offered: dict[str, Any] = (
            {} if role is None else {"tools": role.tools, "clis": role.clis}
        )
        # Given only where there is one, as the driver's contract has it.
        handle = await (
            self._driver.open(
                placement,
                permission=permission,
                skills=(),
                hooks=self._hooks,
                **offered,
            )
            if kept is None
            else self._driver.open(
                placement,
                permission=permission,
                skills=(),
                hooks=self._hooks,
                carry_on=kept,
                **offered,
            )
        )
        self.handle = handle
        agent = getattr(handle, "agent", None)
        if agent is not None:
            # Written down by the agent itself as its CLI names the conversation, into the
            # chat's record, and kept there: which is what carrying the chat on finds it by.
            agent.epic = self._epic
            conversation = getattr(handle, "coganchor", None)
            if self._opened is not None and conversation is not None:
                self._opened(
                    ASSISTANT, agent, conversation, getattr(handle, "placement", None)
                )
        return handle

    async def _carried(
        self, kept: Kept | None, unkept: str
    ) -> tuple[SessionHandle, str, bool]:
        """Opens a conversation carrying `kept` on, or a new one where that cannot be.

        Returns:
          The conversation, what the person is told of it ahead of its first answer, and
          whether it carries `kept` on.

        Raises:
          HarnessError: Where no conversation can be opened at all.
        """
        from hmz.flows import HarnessError

        try:
            return await self._open(kept), unkept, kept is not None
        except HarnessError as why:
            if kept is None:
                raise
            # Said ahead of the first answer, which a new conversation gives.
            return await self._open(None), _said(unkept, _restarted(str(why))), False

    async def _permitted(
        self, handle: SessionHandle, unkept: str
    ) -> tuple[SessionHandle, str, bool]:
        """The conversation carried on in one opened under the permission the chat was set.

        A permission that cannot be held here leaves the chat with the one it had, and says
        so. As :meth:`_carried` returns.
        """
        from hmz.runtime.epic import read

        had = self._preset
        await self._close(handle)
        # Off the loop, which is the turns': the whole record is read off disk.
        ran = await asyncio.to_thread(read, self._epic.path)
        # A chat that has opened no conversation yet has none to carry on, and none lost.
        kept, why = (
            _conversation(ran) if ran is not None and ran.sessions else (None, "")
        )
        unkept = _said(unkept, why)
        try:
            return await self._carried(kept, unkept)
        except Exception as refused:
            if had is None:
                raise
            self._chat.permits(had)
            stays = f"The permission stays {had}: {refused}"
            return await self._carried(kept, _said(unkept, stays))

    def _lags(self) -> bool:
        """Whether the chat was given another model or effort than its conversation runs at."""
        wanted = self._chat.driven
        return wanted is not None and _at(wanted) != self._as

    async def _shift(self) -> None:
        """Has the harness's own commands move the conversation open to what the chat was given."""
        wanted, handle = self._chat.driven, self.handle
        if wanted is not None and handle is not None:
            await self._shifted(handle, wanted)

    async def _reopened(
        self, handle: SessionHandle, unkept: str
    ) -> tuple[SessionHandle, str, bool]:
        """The conversation carried on in one opened as the chat now stands.

        At the model and effort it was given, where its conversation does not run at them,
        and under the permission it was set, where that one was not opened under it. As
        :meth:`_carried` returns.
        """
        taken = (handle, unkept, False)
        if self._lags():
            taken = await self._driven(handle, unkept)
        if self._chat.permission != self._preset:
            taken = await self._permitted(taken[0], taken[1])
        return taken

    async def _shifted(self, handle: SessionHandle, wanted: Drove) -> bool:
        """Moves the conversation open to another model or effort by its harness's own commands.

        By its `/model` and `/effort`, where its catalogue calls each one that is needed
        (Section 8.9.5 of [CORE]), which close nothing; no rung at all is not one `/effort`
        can be told.

        Returns:
          Whether it now runs as `wanted`; where not, it is left as it ran.
        """
        from hmz.coganchor.backends import AUTO
        from hmz.flows import HarnessError

        _, model, effort = _at(wanted)
        lines = [f"/model {model}"] if model != self._as[1] else []
        if effort != self._as[2]:
            lines.append(f"/effort {effort}")
        called = {
            f"/{one.name}"
            for one in handle.natives()
            if one.sigil == "/" and one.how == "call"
        }
        if effort == AUTO or not {line.split()[0] for line in lines} <= called:
            return False
        try:
            for line in lines:
                await self._turn(handle, line, native=True)
        except HarnessError:
            return False
        if _running(handle) != (model, effort):
            return False
        self._as = _at(wanted)
        return True

    async def _driven(
        self, handle: SessionHandle, unkept: str
    ) -> tuple[SessionHandle, str, bool]:
        """The conversation carried on in one opened at the model and effort the chat was given.

        By the same harness, as the same account. One that cannot be opened so leaves the
        chat with the model and effort it had, its record saying so again, and says why. As
        :meth:`_carried` returns.
        """
        from hmz.runtime.epic import Drove, read

        chat, had = self._chat, self._driver
        cli, model, effort = self._as
        wanted = chat.driven
        if wanted is None:
            return handle, unkept, False
        await self._close(handle)
        # Off the loop, which is the turns': the whole record is read off disk.
        ran = await asyncio.to_thread(read, self._epic.path)
        # A chat that has opened no conversation yet has none to carry on, and none lost.
        kept, why = (
            _conversation(ran) if ran is not None and ran.sessions else (None, "")
        )
        unkept = _said(unkept, why)
        made: AgentDriver | None = None
        try:
            self._driver = made = await chat.drives(wanted)
            watch = getattr(made, "watch", None)
            if callable(watch):
                watch(self._heard)
            # Never in a new one where it cannot be carried on: it keeps what it ran as.
            opened = await self._open(kept)
        except Exception as refused:  # noqa: BLE001 -- whatever refuses it, the chat goes on
            self._driver = had
            if made is not None:
                with contextlib.suppress(Exception):
                    await made.close()
            now = Drove(ASSISTANT, cli, model, effort, had.provider, had.name)
            chat.ran_as(now, written=True)
            stays = f"This chat goes on with {model} at {effort}: {refused}"
            return await self._carried(kept, _said(unkept, stays))
        await chat.driven_by(made)
        self._as = _at(wanted)
        return opened, unkept, kept is not None

    async def _renewed(self, handle: SessionHandle) -> SessionHandle:
        """A new conversation in place of one that could not be carried on."""
        await self._close(handle)
        return await self._open(None)

    async def _close(self, handle: SessionHandle) -> None:
        """Closes a conversation, which is a session closed for the chat's backups."""
        with contextlib.suppress(Exception):
            await handle.close()
        self._keeping.closed()

    async def _turn(self, handle: SessionHandle, prompt: str, *, native: bool) -> str:
        """Takes one turn of the conversation, with no limit on what it spends."""
        from hmz.runtime.flowing.spi import TurnRequest

        self.turning = True
        self.between = False
        # One that landed as the last turn ended stopped nothing, and stops nothing now.
        self._failed = self._interrupted = False
        try:
            answered = await handle.turn(
                TurnRequest(prompt, native=native), self._spending
            )
        finally:
            self.turning = False
            self.between = True
            self._noting(handle)
        return str(answered)

    def interrupt(self) -> bool:
        """Stops the turn going, from any thread, and says whether one was."""
        handle = self.handle
        if not self.turning or handle is None:
            return False
        self._interrupted = True
        handle.interrupt()
        return True

    def _noting(self, handle: SessionHandle) -> None:
        """Writes down a conversation a driver with no coganchor agent behind it named."""
        if getattr(handle, "agent", None) is not None:
            return
        ident = handle.id
        if ident is None or ident == self._noted:
            return
        self._noted = ident
        driver = self._driver
        self._epic.session(driver.name, str(driver.harness), driver.provider, ident)

    async def _shell(self, handle: SessionHandle, command: str) -> tuple[int, str, str]:
        """Runs a `!` command in the workspace, held to what the assistant's commands are.

        Returns:
          Its exit status, stdout and stderr; a command that could not be run, or was killed,
          is said as one that failed, with why on its stderr.
        """
        from hmz.flows import EnvCommandTimeout, EnvError

        try:
            argv = _confined(handle, command)
        except (OSError, ValueError) as why:
            # Never run wider than the assistant's own commands (Section 4.6.4.15 of
            # [CORE]): one that cannot be confined is not run.
            return 126, "", f"{command}: it could not be confined: {why}"
        try:
            return await self._local.exec(argv, timeout=SHELL_TIMEOUT)
        except EnvCommandTimeout as why:
            return 124, "", str(why)
        except EnvError as why:
            return 126, "", str(why)


class _Spending:
    """What a chat's turns spent, added up as they spend it: the sink every turn reports to."""

    def __init__(self) -> None:
        """Nothing spent."""
        self._lock = threading.Lock()
        self._cost = 0.0
        self._output_tokens = 0
        self._seconds = 0.0

    def add(self, *, cost: float, output_tokens: int, duration: float) -> None:
        """Adds what a turn spent since it last said, from whichever thread it says it on."""
        with self._lock:
            self._cost += cost
            self._output_tokens += output_tokens
            self._seconds += duration

    def usage(self) -> Usage:
        """Everything spent so far."""
        from hmz.flows import Usage

        with self._lock:
            return Usage(
                cost=self._cost,
                output_tokens=self._output_tokens,
                duration=datetime.timedelta(seconds=self._seconds),
            )


def _assistant(agent: str) -> AgentSpec:
    """The chat's agent, read and checked before anything is written (8.3.7 of [CORE]).

    Raises:
      Refused: For a spec that cannot be read, or that names an account nobody saved.
    """
    from hmz.runtime.flowing.specs import SpecError, parse_agents
    from hmz.runtime.runner import Refused, saved

    try:
        said = parse_agents([f"{ASSISTANT}={agent}"])[0]
    except SpecError as why:
        raise Refused(str(why)) from why
    saved(said, "the chat")
    return said


def _drove(said: AgentSpec, name: str) -> Drove:
    """The assistant as the chat's record writes it down."""
    from hmz.runtime.runner import drove

    # At its concrete nous, which is what the record states of one named by a virtual one.
    return drove(ASSISTANT, str(replace(said, nous="")).partition("=")[2], name)


def _at(runs: Drove) -> tuple[str, str, str]:
    """An assistant's CLI, model and effort, the effort spelt as a line names it."""
    from hmz.coganchor.backends import written

    return runs.backend, runs.model, written(runs.effort)


def _running(handle: SessionHandle) -> tuple[str, str] | None:
    """The model and the effort a conversation runs at, or None where no agent is behind it.

    What the conversation runs at, which is the agent's only where the CLI's command moved
    the agent: Codex's moves the conversation alone.
    """
    from hmz.coganchor.backends import written

    agent = getattr(handle, "agent", None)
    if agent is None:
        return None
    conversation = getattr(handle, "coganchor", None)
    model = str(getattr(conversation, "model", None) or agent.config.model)
    # Spelt as `began` gives it: an agent holds no rung as "", which is written `auto`.
    return model, written(str(getattr(conversation, "effort", agent.effort)))


def carried_as(now: Drove, agent: str) -> Drove:
    """What a chat's assistant is written down as, carried on with another model or effort.

    A chat is carried on by the harness that had it, as the account it ran as (Section
    8.3.18 of [CORE]): only its model and its effort are given anew.

    Args:
      now: The assistant as the chat's record says it.
      agent: The agent to carry it on with, as `-a` spells one after `<role>=`.

    Returns:
      The assistant as the record is to say it, under the name it had.

    Raises:
      KeptAs: For an agent of another harness or another account, and, where the model or
        the effort differs, a harness that carries no conversation on or is told neither.
      ValueError: For an agent that is not one.
    """
    from hmz.coganchor import backends
    from hmz.flows import HarnessKind

    said = _assistant(agent)
    wanted = _drove(said, now.name)
    if wanted.backend != now.backend:
        raise KeptAs(_KEPT_HARNESS.format(had=now.backend, wanted=wanted.backend))
    if wanted.provider != now.provider:
        raise KeptAs(
            _KEPT_ACCOUNT.format(
                had=now.provider or "this machine's own",
                wanted=wanted.provider or "this machine's own",
            )
        )
    if _at(wanted) == _at(now):
        return wanted
    profile = backends.named(now.backend)
    if profile is None or not profile.forks:
        raise KeptAs(_KEPT_MODEL.format(harness=now.backend))
    if said.harness is HarnessKind.ACP:
        raise KeptAs(_UNTOLD_MODEL.format(harness=now.backend))
    return wanted


def _carried(resume: Path | None, workspace: Path) -> tuple[Path | None, Ran | None]:
    """The chat to carry on, checked, and what its record said before it is opened again.

    Raises:
      Refused: For one that is not a chat or is going on already, and for one that cannot be
        continued here: another workspace's.
    """
    from hmz.runtime.epic import CHATTED, going, journal, read
    from hmz.runtime.runner import Refused

    if resume is None:
        return None, None
    ran = read(resume)
    # One an earlier hmz kept as an epic is no chat until it is moved (Section 8.7.10).
    if ran is None or not ran.chat or journal(resume).name != CHATTED:
        raise Refused(f"{resume.name} is not a chat, so there is no chat to carry on")
    if Path(ran.workspace).resolve() != workspace:
        raise Refused(
            f"{resume.name}: the chat cannot be continued here: it is of {ran.workspace}"
        )
    if going(resume):
        raise Refused(f"{resume.name} is going on already")
    return resume, ran


def _set_again(
    epic: Epic,
    before: Ran,
    now: Drove,
    prefer: Prefer | None,
    permission: str | None,
    env: str = "",
) -> None:
    """Writes what a chat carried on is now, where it is not what its record said it was.

    Its agent, where it was given another, its own preference and its permission, where
    this opening overrides the one it had, and its env, where it is carried on in another
    (Section 6.12.6 of [FILES]).
    """
    agents = (
        {"agents": [now._asdict()]}
        if not before.agents or before.agents[-1].spec != now.spec
        else {}
    )
    preferring = (
        {"prefer": prefer} if prefer is not None and prefer != before.prefer else {}
    )
    permitting = (
        {"permission": permission}
        if permission is not None and permission != _recorded(before)
        else {}
    )
    placing = {"env": env} if env and env != before.env else {}
    if agents or preferring or permitting or placing:
        epic.write("set", **agents, **preferring, **permitting, **placing)


def _conversation(before: Ran) -> tuple[Kept | None, str]:
    """The conversation a chat carried on goes on with, or why there is none.

    The last the chat's record says was opened, from where it is kept: in the chat's
    directory, for every one a turn could keep there.

    Returns:
      What to carry on and "", or None and what the person is told of why.
    """
    from hmz.flows import HarnessKind
    from hmz.runtime.epic import where
    from hmz.runtime.flowing.spi import Kept

    if not before.sessions:
        return None, _restarted("it was not kept as it stopped")
    last = before.sessions[-1]
    try:
        harness = HarnessKind(last.backend)
    except ValueError:
        return None, _restarted(f"no harness here is called {last.backend}")
    return Kept(harness, last.ident, where(before.at, last)), ""


def _restarted(why: str) -> str:
    """What the person is told of a conversation that could not be carried on."""
    return f"This conversation could not be carried on ({why}), so this is a new one."


def _refused(read: Resolved, line: str, role: Role | None) -> str | None:
    """Why a line is refused rather than served, or None for one that is served."""
    if read.kind == "refused":
        return read.why
    if (
        role is not None
        and read.kind == "native"
        and line.split(maxsplit=1)[0] in ("/model", "/effort")
    ):
        # Her nous is hers while the conversation lasts (Section 14.3.1 of [CORE]).
        return _KEPT_NOUS
    return None


def _said(unkept: str, answered: str) -> str:
    """An answer, with what was said ahead of it about the conversation it is in."""
    return f"{unkept}\n\n{answered}" if unkept else answered


def _blocks(command: str, out: str, err: str) -> str:
    """A `!` command and what it printed, as the harness's own prompt carries them on."""
    return (
        f"<bash-input>{command}</bash-input>\n"
        f"<bash-stdout>{out.rstrip()}</bash-stdout>"
        f"<bash-stderr>{err.rstrip()}</bash-stderr>"
    )


def _flows(line: str) -> frozenset[str]:
    """The flow a `$` line names, where one answers to it here; nothing for any other line.

    Asked of the one name rather than by listing every flow, which imports them all.
    """
    if not line.startswith("$"):
        return frozenset()
    from hmz.runtime.flowing import find

    name = line[1:].partition(" ")[0]
    try:
        return frozenset({name}) if name and find(name) else frozenset()
    except (OSError, ValueError):
        return frozenset()


def preset(said: object) -> str:
    """A chat's permission, checked: one of the presets a grant starts from.

    Args:
      said: What it was said as.

    Returns:
      It, where it is `read-only`, `workspace-write` or `danger-full-access`.

    Raises:
      ValueError: For anything else, in the words a frontend is refused with.
    """
    from hmz.flows import PRESETS

    if not isinstance(said, str) or said not in PRESETS:
        raise ValueError(f"permission is {', '.join(PRESETS[:-1])} or {PRESETS[-1]}")
    return said


def _recorded(before: Ran) -> str:
    """The permission a chat carried on had: what its record gives, else a chat's own."""
    try:
        return preset(before.permission)
    except ValueError:
        return PERMISSION


def _confined(handle: SessionHandle, command: str) -> list[str] | str:
    """A `!` command, held to the confinement the assistant's own commands are held to.

    The assistant's fence (Section 4.6.4 of [CORE]) put around the command from outside, as it
    is around whatever its CLI does not hold natively -- the whole of it here, since the
    command is not the CLI's to hold. A command for an assistant held to nothing is the command
    as it is.

    Returns:
      What to run: the command as a script, or the fence around it under bash.

    Raises:
      OSError: Where there is nothing on this machine to put a fence up with.
      ValueError: Where the fence cannot be said.
    """
    agent = getattr(handle, "agent", None)
    fence = None if agent is None else agent.fenced()
    if fence is None or fence.open:
        return command
    from hmz.coganchor.fence import wrapper

    return [*wrapper(fence), "bash", "-c", command]


class Busy(Exception):  # noqa: N818 -- named for what happened, as Refused is
    """A chat asked to move while a turn of it is open (Section 8.3.16 of [CORE])."""


def env_spec(said: object) -> str:
    """An env a chat is put in, checked as `-e` reads one, and spelled as it writes it.

    Args:
      said: `<backend>[@<provider>][/<workdir>]`.

    Returns:
      It, as `-e` spells it after `<role>=`.

    Raises:
      ValueError: For what is no env, in the words `-e` refuses it with.
    """
    from hmz.runtime.flowing.specs import parse_envs

    if not isinstance(said, str) or not said.strip():
        raise ValueError("env is <backend>[@<runtime>][/<directory>]")
    (spec,) = parse_envs([f"workspace={said.strip()}"])
    return str(spec).partition("=")[2]


async def _env_at(env: str) -> EnvDriver:
    """The env a chat works in, opened and reached.

    Raises:
      FlowException: For an env that cannot be read, one whose runtime nobody saved, a
        machine that cannot be reached, and a directory that is not there.
    """
    from hmz.flows import EnvUnavailable
    from hmz.runtime.flowing import open_env, probe
    from hmz.runtime.flowing.specs import parse_envs

    try:
        (spec,) = parse_envs([f"workspace={env}"])
    except ValueError as why:
        raise EnvUnavailable(str(why)) from why
    local = open_env(spec)
    try:
        await probe(local)
    except BaseException:
        with contextlib.suppress(Exception):
            await local.close()
        raise
    return local


def _spelt(local: EnvDriver) -> str:
    """Where an env is, as `-e` spells it after `<role>=`, for the chat's record to say."""
    from hmz.runtime.flowing.specs import spelled

    where = local.placement()
    return spelled(str(where.backend), where.provider, where.workdir)


def _priced() -> None:
    """Has the price list brought up to date, on a thread of its own, for what a chat spends.

    A chat is held to no cost, so nothing waits for it: what is kept prices its turns meanwhile.
    """
    from hmz.coganchor import prices

    with contextlib.suppress(prices.PriceError):
        prices.refresh()


async def _placeable(
    driver: AgentDriver, local: EnvDriver, permission: Permission
) -> None:
    """Settles where the assistant's harness goes for the workspace, or refuses the chat.

    Raises:
      HarnessError: The refusal, as its first session there would have had it.
    """
    from hmz.runtime.flowing.harnesses import HarnessDriver

    if isinstance(driver, HarnessDriver):
        await driver.placeable([local.placement()], permission)
