"""A flow that is running, and the handful of things there are to do to one.

:class:`hmz.runtime.runner.Runner` is a flow loaded and handed its drivers; running it is a
coroutine that returns when the flow does, which for a loop meant to run for a week is not a
call anything holding a terminal can make. This is that coroutine put on a loop of its own --
here, or on a thread of its own -- with the things somebody watching a run asks for: what it
has opened, what it has spent, whether it is still going, and to stop it.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hmz.coganchor.agents import AgentBase, SessionBase
    from hmz.flows import Budget, Usage
    from hmz.runtime.epic import Epic
    from hmz.runtime.flowing import Declaration, OutworlderDriver
    from hmz.runtime.flowing.harnesses import Listener
    from hmz.runtime.runner import Runner

__all__ = ["Run"]


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
        self._opened: list[Callable[[str, AgentBase, SessionBase], None]] = []
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
    def usage(self) -> Usage:
        """What every session of the run has spent so far."""
        from hmz.flows import Usage

        recorder = self._runner.recorder
        return Usage() if recorder is None else recorder.usage()

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """The coganchor agent behind each session of the run still open, oldest first.

        Each is named for the role it was opened for, which is what its events say. Only the
        open ones: a run that opens a session a round for a week holds no more than one that
        opened one, and a session that closed has no agent left to reach.
        """
        recorder = self._runner.recorder
        if recorder is None:
            return ()
        held = (getattr(one, "agent", None) for one in recorder.sessions)
        return tuple(one for one in held if one is not None)

    @property
    def epic(self) -> Path | None:
        """The epic the run is written into, once it has started."""
        return self._epic

    def unreadable(self) -> str:
        """Which cap of the run nothing it drives can read, in words, or "" for none."""
        return self._runner.unreadable()

    def watch(self, listener: Listener) -> None:
        """Has everything every session of the run says reach `listener`, as it is said.

        Args:
          listener: What to tell -- the agent, the conversation and the event -- from
            whichever thread a CLI is read on.
        """
        self._runner.watch(listener)

    def opened(self, callback: Callable[[str, AgentBase, SessionBase], None]) -> None:
        """Has each session the run opens told to `callback` as it opens.

        Args:
          callback: What to tell: the role, the coganchor agent and its conversation. Told
            on the run's own loop, before the session's first turn.
        """
        self._opened.append(callback)

    @property
    def running(self) -> bool:
        """Whether the flow is still going, which is False before it is started."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def raised(self) -> BaseException | None:
        """Whatever the flow raised, for a run started on a thread of its own and now over."""
        return self._raised

    @property
    def result(self) -> Any:
        """What the flow returned, for a run started on a thread of its own and now over."""
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
        )

    def _told(self, role: str, agent: AgentBase, session: SessionBase) -> None:
        for callback in tuple(self._opened):
            callback(role, agent, session)

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
            return asyncio.run(self._main())
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
