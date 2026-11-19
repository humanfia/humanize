"""A flow that is running -- or a chat -- and the handful of things there are to do to one.

:class:`hmz.runtime.runner.Runner` is a flow loaded and handed its drivers; running it is a
coroutine that returns when the flow does, which for a loop meant to run for a week is not a
call anything holding a terminal can make. This is that coroutine put on a loop of its own --
here, or on a thread of its own -- with the things somebody watching a run asks for: what it
has opened, what it has spent, whether it is still going, and to stop it.

A chat is no flow (Section 8 of core.md), but a host holds one as it holds a run: what it
opened, what it said and spent, and how it ended. :class:`Chatting` is a chat held so, the one
kind of epic answering what the other does, and saying which it is by `kind`.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hmz.coganchor.agents import AgentBase, SessionBase
    from hmz.flows import Budget, Usage
    from hmz.runtime.chatting import Chat, ChatEnd, HeldWorkspace
    from hmz.runtime.epic import Epic
    from hmz.runtime.flowing import Declaration, OutworlderDriver
    from hmz.runtime.flowing.engine import Run as EngineRun
    from hmz.runtime.flowing.harnesses import Listener
    from hmz.runtime.flowing.spi import Placement
    from hmz.runtime.runner import Opened, Runner

__all__ = ["Chatting", "Run"]


class Run:
    """One run of one flow: what it opened, what it spent, and how it ends."""

    def __init__(
        self, runner: Runner, task: str, *, outworlder: OutworlderDriver | None = None
    ) -> None:
        """Holds a loaded flow and what it is to do.

        Nothing is started here: a run is started by :meth:`start`, or run to its return by
        :meth:`run`, so that whoever made one chooses which of the two they are holding.

        Args:
          runner: The flow, loaded and handed its drivers.
          task: What it is to do.
          outworlder: Whoever is outside the run, or None for nobody -- an outworlder that is
            always away, which is what a command line is.
        """
        self._runner = runner
        self._task = task
        self._outworlder = outworlder
        self._opened: list[Opened] = []
        self._noticed: list[Callable[[str], None]] = []
        self._epic: Path | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running: asyncio.Task[Any] | None = None
        self._stopping = False
        self._raised: BaseException | None = None
        self._result: Any = None
        self._lock = threading.Lock()

    # ----------------------------------------------------------------------- what it is

    @property
    def flow(self) -> str:
        """The flow, as it was named."""
        return self._runner.flow

    @property
    def ref(self) -> str:
        """The flow's canonical ref, which is what the running tree names it by."""
        return self._runner.impl.ref

    @property
    def kind(self) -> Literal["flow"]:
        """What it is an epic of (Section 3.2.13 of core.md): a flow, whatever it is named."""
        return "flow"

    @property
    def task(self) -> str:
        """What it was asked to do."""
        return self._task

    @property
    def declaration(self) -> Declaration:
        """What the flow declares."""
        return self._runner.declaration

    @property
    def budget(self) -> Budget:
        """What the run may spend."""
        return self._runner.budget

    @property
    def profile_flow(self) -> bool:
        """Whether the run samples the flow's own Python while it runs."""
        return self._runner.profile_flow

    @property
    def profile_environment(self) -> bool:
        """Whether the run profiles the programs its agents start, as well as tracing them."""
        return self._runner.profile_environment

    @property
    def backup(self) -> tuple[str, ...]:
        """The backup targets the epic goes to, by name."""
        return self._runner.backup

    @property
    def usage(self) -> Usage:
        """What every session of the run has spent so far."""
        from hmz.flows import Usage

        recorder = self._runner.recorder
        return Usage() if recorder is None else recorder.usage()

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """The coganchor agent behind each session of the run still open, oldest first.

        Each is called by its own name, which is what its events say. Only the
        open ones: a run that opens a session a round for a week holds no more than one that
        opened one, and a session that closed has no agent left to reach.
        """
        recorder = self._runner.recorder
        if recorder is None:
            return ()
        held = (getattr(one, "agent", None) for one in recorder.sessions)
        return tuple(one for one in held if one is not None)

    @property
    def names(self) -> dict[str, str]:
        """What the agent filling each agent role is called, by role.

        Which is what its sessions are keyed by: the role is only the parameter it is taken as.
        """
        return {role: one.name for role, one in self._runner.agents.items()}

    @property
    def envs(self) -> EngineRun | None:
        """The run as its engine holds it, once it has started and until it ends.

        What lists the environments it holds (`held_envs`) and the loop their drivers live
        on (`loop`): every one a role was given, the run's own workspace, and every one a
        flow derived and has not destroyed.
        """
        from hmz.runtime.flowing.engine import held_by

        recorder = self._runner.recorder
        return None if recorder is None else held_by(recorder)

    @property
    def epic(self) -> Path | None:
        """The epic the run is written into, once it has started."""
        return self._epic

    def unreadable(self) -> str:
        """Which cap of the run nothing it drives can read, in words, or "" for none.

        For a run held to a cost, a missing or stale price list is fetched first -- waited on
        for no longer than the fetch's own timeout, and not at all once the run is stopped.
        """
        return self._runner.unreadable(self._stopped)

    def _stopped(self) -> bool:
        with self._lock:
            return self._stopping

    def watch(self, listener: Listener) -> None:
        """Has everything every session of the run says reach `listener`, as it is said.

        Args:
          listener: What to tell -- the agent, the conversation and the event -- from
            whichever thread a CLI is read on.
        """
        self._runner.watch(listener)

    def opened(self, callback: Opened) -> None:
        """Has each session the run opens told to `callback` as it opens.

        Args:
          callback: What to tell: the role, the coganchor agent, its conversation and where
            it works. Told on the run's own loop, before the session's first turn.
        """
        self._opened.append(callback)

    def noticed(self, callback: Callable[[str], None]) -> None:
        """Has Humanize's own word about the run told to `callback`, a line at a time.

        Which is an environment moved off the runtime its `-e` named, and why: said before
        the flow is called, on the run's own loop.

        Args:
          callback: What to tell.
        """
        self._noticed.append(callback)

    @property
    def running(self) -> bool:
        """Whether the flow is still going, which is False before it is started."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def raised(self) -> BaseException | None:
        """Whatever the flow raised, once the run is over."""
        return self._raised

    @property
    def result(self) -> Any:
        """What the flow returned, once the run is over."""
        return self._result

    # ------------------------------------------------------------------------- running

    async def _main(self) -> Any:
        """The run, on whichever loop is running it."""
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._running = asyncio.current_task()
            stopping = self._stopping
        if stopping:
            # Stopped before it began: nothing ran, and what it was given goes all the same.
            await self._runner.aclose()
            raise asyncio.CancelledError
        return await self._runner.arun(
            self._task,
            outworlder=self._outworlder,
            opened=self._told,
            started=self._began,
            noticed=self._notices,
        )

    def _told(
        self,
        role: str,
        agent: AgentBase,
        session: SessionBase,
        where: Placement | None,
    ) -> None:
        for callback in tuple(self._opened):
            callback(role, agent, session, where)

    def _notices(self, said: str) -> None:
        for callback in tuple(self._noticed):
            callback(said)

    def _began(self, epic: Epic) -> None:
        self._epic = epic.path

    def run(self) -> Any:
        """Runs the flow here, until it returns.

        On a loop of its own in this thread, which is where a signal reaches it; from a
        thread already running a loop -- an interface, a test -- on a thread of its own, the
        flow's turns being waited on by a loop this one must not hold.

        Returns:
          What the flow returned.

        Raises:
          BaseException: Whatever the flow raised, as it raised it.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._drives()
        else:
            self.start()
        self.wait()
        if self._raised is not None:
            raise self._raised
        return self._result

    def start(self) -> None:
        """Starts the flow on a thread of its own, and returns at once.

        Raises:
          RuntimeError: If it has already been started.
        """
        if self._thread is not None:
            raise RuntimeError("this run has already been started")
        self._thread = threading.Thread(
            target=self._drives, name="humanize-run", daemon=True
        )
        self._thread.start()

    def _drives(self) -> None:
        """Runs the flow, keeping what it returned or raised for whoever asks afterwards."""
        try:
            self._result = asyncio.run(self._main())
        except BaseException as why:  # noqa: BLE001 -- kept rather than swallowed
            self._raised = why

    def wait(self, timeout: float | None = None) -> bool:
        """Waits for the flow to end.

        Args:
          timeout: How long to wait, or None for as long as it takes.

        Returns:
          Whether it has ended.
        """
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def stop(self) -> None:
        """Stops the flow: the turn under way is interrupted, and the flow unwinds.

        Every call of it raises where it stands, every session it opened is closed and every
        temporary directory it made is taken away -- in its own time, which :meth:`close` does
        not wait for. From any thread.
        """
        with self._lock:
            self._stopping = True
            loop, running = self._loop, self._running
        if loop is None or running is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(running.cancel)
        except RuntimeError:  # the loop closed between the two
            return

    def close(self) -> None:
        """Stops the flow and ends every conversation still open, without waiting for it.

        What the flow gets back is a turn that failed, the same thing it would have got had
        the agent fallen over by itself. The last thing there is to do about a run.
        """
        import contextlib

        self.stop()
        recorder = self._runner.recorder
        for handle in () if recorder is None else recorder.sessions:
            with contextlib.suppress(Exception):
                handle.interrupt()
        for agent in self.agents:
            with contextlib.suppress(Exception):
                agent.stop()


class Chatting:
    """One chat, held as a host holds a run: what it opened, what it spent, and how it ends.

    What a chat opens and says is told by the chat itself: :class:`hmz.runtime.chatting.Chat`'s
    `watch`, `opened`, `epic`, `usage` and `agents` are what :class:`Run`'s of those names are,
    handed through here. A chat has no flow, no ref, no params and no budget.
    """

    #: What it is, where a run is of a flow (Section 4.6.4 of daemon.md).
    kind: Literal["chat"] = "chat"
    #: The flow and its ref, which a chat has neither of.
    flow = ""
    ref = ""
    #: What a run is asked of these, which a chat never is.
    profile_flow = False
    profile_environment = False
    backup: tuple[str, ...] = ()

    def __init__(self, chat: Chat) -> None:
        """Holds a chat set up; nothing is started until :meth:`run`.

        Args:
          chat: The chat.
        """
        self._chat = chat
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running: asyncio.Task[Any] | None = None
        self._stopping = False
        self._end: ChatEnd | None = None

    @property
    def chat(self) -> Chat:
        """The chat."""
        return self._chat

    @property
    def task(self) -> str:
        """Its first message."""
        return self._chat.spec.task

    @property
    def agent(self) -> str:
        """Its assistant, as `-a` spells an agent."""
        return self._chat.spec.agent

    @property
    def budget(self) -> None:
        """What it may spend, which no limit holds (Section 8.3.3 of core.md)."""
        return None

    @property
    def usage(self) -> Usage:
        """What its conversation has spent so far."""
        return self._chat.usage

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """The coganchor agent behind its conversation, while one is open."""
        return self._chat.agents

    @property
    def epic(self) -> Path | None:
        """The directory it is written into, once it has opened it, held as a run's epic is.

        Not the one it is to carry on: a chat carried on may yet be refused -- one going on
        already, an agent it cannot open (Section 8.7.7 of core.md) -- so the chat it names
        is not its own before then.
        """
        if self._end is not None:
            return self._end.at
        return self._chat.at

    @property
    def names_epic(self) -> bool:
        """Whether its directory is known once it has one, which a chat's always is."""
        return True

    def unreadable(self) -> str:
        """Which cap nothing it drives can read, which is none: a chat has no budget."""
        return ""

    def watch(self, listener: Listener) -> None:
        """Has everything its conversation says reach `listener`."""
        self._chat.watch(listener)

    def opened(self, callback: Opened) -> None:
        """Has its conversation told to `callback` as it opens."""
        self._chat.opened(callback)

    @property
    def envs(self) -> HeldWorkspace | None:
        """The workspace the chat works in while it is had, for the host's env panels."""
        return self._chat.envs

    def noticed(self, callback: Callable[[str], None]) -> None:
        """Takes what a run tells of an environment moved, which a chat never has.

        A chat works in its workspace on this machine, or a worktree of it, and nowhere
        else (Section 8.3.2 of core.md), so there is nothing of Humanize's own to say about
        where it went.
        """
        del callback

    def run(self) -> ChatEnd:
        """Has the chat on a loop of its own on this thread, from its first message to its last.

        Returns:
          How it ended.

        Raises:
          BaseException: Whatever the chat raised -- what its first turn failed with, a chat
            stopped as `asyncio.CancelledError` -- as it raised it.
        """
        self._end = asyncio.run(self._main())
        return self._end

    async def _main(self) -> ChatEnd:
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._running = asyncio.current_task()
            stopping = self._stopping
        if stopping:
            raise asyncio.CancelledError
        return await self._chat.run()

    def stop(self) -> None:
        """Ends the chat where it stands, from any thread: what is going is cancelled."""
        with self._lock:
            self._stopping = True
            loop, running = self._loop, self._running
        if loop is None or running is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(running.cancel)
        except RuntimeError:  # the loop closed between the two
            return

    def interrupt(self) -> bool:
        """Stops the turn going, leaving the chat between turns; whether one was going."""
        return self._chat.interrupt()

    def close(self) -> None:
        """Ends the chat and its conversation, without waiting for it."""
        import contextlib

        self.stop()
        for agent in self.agents:
            with contextlib.suppress(Exception):
                agent.stop()
