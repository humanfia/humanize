"""In-memory stand-ins for every driver, to run a flow with no coding agent and no machine.

A flow is tested the way it is run -- through :func:`~hmz.runtime.flowing.engine.run_flow`,
granted what it declared -- with the drivers underneath swapped for these::

    from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, run_fake

    async def test_fix_stops_when_the_tests_pass():
        coder = FakeAgentDriver(reply=["patched", "patched again"])
        repo = FakeEnvDriver({"README.md": b"hi"}, run={("make", "test"): (0, "ok", "")})
        result = await run_fake("fix", "make it green", agents={"coder": coder},
                                envs={"repo": repo}, params={"rounds": 3})
        assert coder.prompts == ["make it green", ...]

- :class:`FakeAgentDriver` answers every turn from a script: a function of the prompt, a
  list of answers taken in order, or one answer for every turn. A turn costs what it is told
  to -- reported through the engine's sink, so budgets and usage behave as they would --
  and takes no time. It fires the hooks a real session would: `SESSION_START`,
  `USER_PROMPT_SUBMIT` and `STOP` on every turn, `SESSION_END` on close, and whichever
  others a scripted answer reaches for through its session -- :meth:`FakeSession.tool`,
  :meth:`~FakeSession.ask`, :meth:`~FakeSession.notify`, :meth:`~FakeSession.subagent` --
  so that a flow's hooks are exercised too. A `STOP` hook that blocks keeps the turn going
  with its reason as the next prompt, as a real one does, and a hard deadline cuts off a turn
  its answer holds open -- one waiting on :meth:`FakeSession.until_steered` -- as a real
  driver's does.
- :class:`FakeEnvDriver` is a dictionary of files under a workdir, with worktrees,
  temporary copies and scratch directories as copies of it, and `exec` answered by a
  function or a table, with a few commands -- `true`, `false`, `echo`, `cat`, `ls`, `sleep`
  and `git rev-parse` -- answered by default. A temporary copy is its holder's until the
  run that took it closes, and a run resumed on the same fake takes it again as it was
  left.
- :class:`FakeOutworlder` answers as the person outside the run would, or is away.
- :func:`run_fake` runs a flow with a fake for every role nobody gave one for.

Every fake here keeps the promises :mod:`~hmz.runtime.flowing.spi` makes for a driver, and
the engine's own tests hold them to it.
"""

from __future__ import annotations

import asyncio
import datetime
import inspect
import itertools
import json
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, cast

import pydantic

from hmz.flows import (
    AskUserHookAgentMixin,
    Budget,
    CostExceeded,
    DurationExceeded,
    EnvBackendKind,
    EnvCommandTimeout,
    EnvFileNotFound,
    HarnessKind,
    HookKind,
    OutputSchemaError,
    OutputTokensExceeded,
    PermissionRequestHookAgentMixin,
    SessionError,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    TempCloneBusy,
    UnsupportedOperation,
    Usage,
    WorktreeError,
)

from .spi import ENV_CAPABILITIES, HARNESS_CAPABILITIES, Placement

if TYPE_CHECKING:
    from collections.abc import Awaitable, Sequence
    from pathlib import Path

    from hmz.flows import (
        AskUserHookResult,
        Flow,
        FlowParams,
        HookResult,
        Permission,
        PermissionRequestHookResult,
        PreToolUseHookResult,
        SessionStartHookResult,
        StopHookResult,
        SubagentStartHookResult,
        SubagentStopHookResult,
        UserPromptSubmitHookResult,
    )

    from .engine import Recorder
    from .spi import (
        AgentDriver,
        EnvDriver,
        HookTable,
        OutworlderDriver,
        Skill,
        TurnRequest,
        UsageSink,
    )

__all__ = [
    "Answer",
    "Command",
    "FakeAgentDriver",
    "FakeEnvDriver",
    "FakeOutworlder",
    "FakeSession",
    "Handler",
    "Reply",
    "run_fake",
]

#: One answer: text, a model instance, or a mapping or JSON text a schema is read from.
type Answer = str | pydantic.BaseModel | Mapping[str, Any]

#: What a fake agent answers with: a function of the prompt -- given the session and the
#: schema asked for, sync or async -- a list of answers taken one per turn, or one answer
#: for every turn. None answers "ok", or the schema built with its defaults.
type Reply = (
    Callable[..., Answer | Awaitable[Answer | None] | None]
    | Iterable[Answer]
    | Answer
    | None
)

#: A command as a fake environment is asked it: an argv as a tuple, or a script.
type Command = tuple[str, ...] | str

#: What answers a fake environment's commands: a function of the command and the
#: environment -- sync or async, answering None to leave it to the defaults -- or a table.
type Handler = (
    Callable[
        [Command, FakeEnvDriver],
        tuple[int, str, str] | Awaitable[tuple[int, str, str] | None] | None,
    ]
    | Mapping[Command, tuple[int, str, str]]
    | None
)

#: How many times a `STOP` hook may keep one turn going before the fake ends it anyway.
_AGAIN = 100


def _as(said: object, schema: type[pydantic.BaseModel] | None, who: str) -> Any:
    """An answer as what a turn asked for: text, or an instance of its schema."""
    if schema is None:
        if isinstance(said, str):
            return said
        if isinstance(said, pydantic.BaseModel):
            return said.model_dump_json()
        return json.dumps(said)
    if isinstance(said, schema):
        return said
    try:
        if isinstance(said, str):
            return schema.model_validate_json(said)
        if isinstance(said, pydantic.BaseModel):
            return schema.model_validate(said.model_dump())
        return schema.model_validate(said)
    except pydantic.ValidationError as error:
        raise OutputSchemaError(
            f"{who} answered no {schema.__name__}: {error}"
        ) from error


def _default(schema: type[pydantic.BaseModel] | None, who: str) -> Any:
    if schema is None:
        return "ok"
    try:
        return schema()
    except pydantic.ValidationError:
        raise OutputSchemaError(
            f"{who} was asked for a {schema.__name__}, which has fields with no default, "
            "and has no answer scripted for it"
        ) from None


class _Script:
    """A reply, as something to ask for the next answer."""

    def __init__(self, reply: Reply) -> None:
        self.call: Callable[..., Any] | None = None
        self.queue: deque[Any] | None = None
        self.constant: Any = None
        said: Any = reply
        if said is None:
            return
        if callable(said) and not isinstance(said, type):
            self.call = said
        elif isinstance(said, (str, pydantic.BaseModel, Mapping)):
            self.constant = said
        else:
            self.queue = deque(cast("Iterable[Any]", said))

    async def next(
        self,
        prompt: str,
        schema: type[pydantic.BaseModel] | None,
        who: str,
        **context: Any,
    ) -> Any:
        if self.call is not None:
            said = self.call(prompt, output_schema=schema, **context)
            if inspect.isawaitable(said):
                said = await said
        elif self.queue is not None:
            said = self.queue.popleft() if self.queue else None
        else:
            said = self.constant
        if said is None:
            return _default(schema, who)
        return _as(said, schema, who)


# --------------------------------------------------------------------------------- agents


class FakeSession:
    """One session of a :class:`FakeAgentDriver`: a conversation with nobody.

    What a scripted answer is given as `session`, to look at and to reach the moments a real
    agent would: the tools it calls, the questions it asks.

    Attributes:
      driver: The driver that opened it.
      placement: Where it was opened.
      permission: What it runs under.
      skills: What it was given.
      forked_from: The session it carries on from, or None.
      prompts: Every prompt it was given, hooks' context included, and every reason a `STOP`
        hook kept a turn going with.
      requests: Every turn it was asked for, limits and all.
      steered: Every prompt it was steered with, and whether it was queued.
      tools: Every tool its answers reached for, what with, and whether it was let run.
      closed: Whether it is over.
    """

    _numbers = itertools.count(1)

    def __init__(
        self,
        driver: FakeAgentDriver,
        placement: Placement,
        permission: Permission,
        skills: tuple[Skill, ...],
        hooks: HookTable,
        forked_from: FakeSession | None,
    ) -> None:
        self.driver = driver
        self.placement = placement
        self.permission = permission
        self.skills = skills
        self.hooks = hooks
        self.forked_from = forked_from
        self._id = f"fake-{next(self._numbers)}"
        self.prompts: list[str] = list(forked_from.prompts) if forked_from else []
        self.requests: list[TurnRequest] = []
        self.steered: list[tuple[str, bool]] = []
        self.tools: list[tuple[str, dict[str, Any], bool]] = []
        self.closed = False
        self._spent = [0.0, 0, 0.0]
        self._lock = threading.Lock()
        self._turning = False
        self._started = False
        self._interrupted = threading.Event()
        self._expired = False
        self._steers: deque[str] = deque()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None

    def __repr__(self) -> str:
        return f"<fake session {self._id} of {self.driver.harness}>"

    @property
    def id(self) -> str | None:
        if self.driver.names_late and not self._started:
            return None
        return self._id

    @property
    def usage(self) -> Usage:
        with self._lock:
            cost, tokens, seconds = self._spent
        return Usage(
            cost=cost,
            output_tokens=int(tokens),
            duration=datetime.timedelta(seconds=seconds),
        )

    async def turn(self, request: TurnRequest, sink: UsageSink) -> Any:
        if self.closed:
            raise SessionError(f"{self._id} is closed")
        if self._turning:
            raise SessionError(f"{self._id} is taking a turn already")
        driver = self.driver
        loop = self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._interrupted.clear()
        self._expired = False
        self._steers.clear()
        prompt = request.prompt
        limits = request.limits
        # A hard deadline stops the turn where it has got to, as a real driver's does.
        timer = (
            None
            if limits.graceful or limits.deadline is None
            else loop.call_later(
                max(limits.deadline - time.monotonic(), 0.0), self._expire
            )
        )
        self._turning = True
        try:
            if not self._started:
                self._started = True
                started: SessionStartHookResult = await self._fire(
                    HookKind.SESSION_START
                )  # pyright: ignore[reportAssignmentType]
                if started.context:
                    prompt = f"{started.context}\n\n{prompt}"
            submitted: UserPromptSubmitHookResult = await self._fire(
                HookKind.USER_PROMPT_SUBMIT, prompt=prompt
            )  # pyright: ignore[reportAssignmentType]
            if submitted.block:
                raise SessionError(f"a hook refused the prompt: {submitted.reason}")
            if submitted.context:
                prompt = f"{prompt}\n\n{submitted.context}"
            self.requests.append(request)
            again = 0
            while True:
                self.prompts.append(prompt)
                try:
                    said = await driver.script.next(
                        prompt, request.output_schema, driver.harness, session=self
                    )
                except SessionError as error:
                    if self._expired:
                        raise DurationExceeded(
                            f"{self._id} reached the deadline of its turn"
                        ) from error
                    raise
                if self._interrupted.is_set():
                    if self._expired:
                        raise DurationExceeded(
                            f"{self._id} reached the deadline of its turn"
                        )
                    raise SessionError(f"{self._id} was interrupted")
                self._spend(request, sink)
                text = said if isinstance(said, str) else _as(said, None, "")
                stopped: StopHookResult = await self._fire(
                    HookKind.STOP, said=text, again=again
                )  # pyright: ignore[reportAssignmentType]
                if not (stopped.block and stopped.reason) or again >= _AGAIN:
                    return said
                again += 1
                prompt = stopped.reason
        finally:
            self._turning = False
            if timer is not None:
                timer.cancel()

    def _expire(self) -> None:
        """The turn's hard deadline has come: it stops."""
        self._expired = True
        self.interrupt()

    def _spend(self, request: TurnRequest, sink: UsageSink) -> None:
        """Spends one answer's worth, or what the limits leave where they are hard."""
        driver = self.driver
        cost, tokens, seconds = driver.cost, driver.output_tokens, driver.seconds
        limits = request.limits
        exceeded: type[Exception] | None = None
        if not limits.graceful:
            if limits.deadline is not None and time.monotonic() >= limits.deadline:
                exceeded = DurationExceeded
                cost = tokens = seconds = 0
            if limits.cost is not None and cost > limits.cost:
                cost, exceeded = limits.cost, CostExceeded
            if limits.output_tokens is not None and tokens > limits.output_tokens:
                tokens, exceeded = limits.output_tokens, OutputTokensExceeded
        with self._lock:
            self._spent[0] += cost
            self._spent[1] += tokens
            self._spent[2] += seconds
        sink.add(cost=cost, output_tokens=int(tokens), duration=seconds)
        if exceeded is not None:
            raise exceeded(f"{self._id} reached a limit of its turn")

    async def _fire(self, kind: HookKind, **fields: Any) -> HookResult:
        return await self.hooks.fire(kind, self, **fields)

    async def steer(self, prompt: str, *, queued: bool) -> None:
        if not self._turning:
            raise SessionError(f"{self._id} is not taking a turn")
        self.steered.append((prompt, queued))
        self._steers.append(prompt)
        if self._wake is not None:
            self._wake.set()

    def interrupt(self) -> None:
        self._interrupted.set()
        loop, wake = self._loop, self._wake
        if loop is not None and wake is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(wake.set)
            except RuntimeError:
                return

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.driver.live -= 1
        self.interrupt()
        await self._fire(HookKind.SESSION_END)

    # ----------------------------------------------------- what a scripted answer reaches

    async def until_steered(self) -> str:
        """Waits, as a turn that goes on until somebody says something, for a steer.

        Returns:
          What it was steered with.

        Raises:
          SessionError: If it is interrupted first.
        """
        wake = self._wake
        if wake is None:
            raise SessionError(f"{self._id} is not taking a turn")
        while True:
            if self._interrupted.is_set():
                raise SessionError(f"{self._id} was interrupted")
            if self._steers:
                return self._steers.popleft()
            wake.clear()
            await wake.wait()

    async def tool(self, name: str, input: Mapping[str, Any] | None = None) -> bool:  # noqa: A002
        """Reaches for a tool: `PRE_TOOL_USE`, then `PERMISSION_REQUEST` where it is served.

        Returns:
          Whether the tool would run.
        """
        said = dict(input or {})
        pre: PreToolUseHookResult = await self._fire(
            HookKind.PRE_TOOL_USE, tool=name, input=said
        )  # pyright: ignore[reportAssignmentType]
        allowed = not pre.block
        if allowed and PermissionRequestHookAgentMixin in self.driver.capabilities:
            asked: PermissionRequestHookResult = await self._fire(
                HookKind.PERMISSION_REQUEST, tool=name, input=said
            )  # pyright: ignore[reportAssignmentType]
            allowed = asked.allow
        self.tools.append((name, said, allowed))
        return allowed

    async def ask(self, question: str, options: Sequence[str] = ()) -> str | None:
        """Asks the user a question, where the harness can.

        Returns:
          The answer, or None.
        """
        if AskUserHookAgentMixin not in self.driver.capabilities:
            raise UnsupportedOperation(f"{self.driver.harness} does not ask its user")
        answered: AskUserHookResult = await self._fire(
            HookKind.ASK_USER, question=question, options=tuple(options)
        )  # pyright: ignore[reportAssignmentType]
        return answered.answer

    async def notify(self, message: str) -> None:
        """Stops to tell the user something."""
        await self._fire(HookKind.NOTIFICATION, message=message)

    async def subagent(self, name: str, task: str = "", said: str = "") -> str:
        """Runs a subagent of its own, where the harness can.

        Returns:
          What the subagent was told to go on with by a `SUBAGENT_STOP` hook that kept it
          going, or `said`.
        """
        capabilities = self.driver.capabilities
        if SubagentStartHookAgentMixin in capabilities:
            started: SubagentStartHookResult = await self._fire(
                HookKind.SUBAGENT_START, subagent=name, task=task
            )  # pyright: ignore[reportAssignmentType]
            del started
        if SubagentStopHookAgentMixin in capabilities:
            stopped: SubagentStopHookResult = await self._fire(
                HookKind.SUBAGENT_STOP, subagent=name, said=said
            )  # pyright: ignore[reportAssignmentType]
            if stopped.block and stopped.reason:
                return stopped.reason
        return said


class FakeAgentDriver:
    """A coding agent that answers from a script, instantly, as any harness.

    Args:
      harness: Which harness it is; its capabilities are that harness's unless given.
      reply: What it answers with; see :data:`Reply`.
      model: What it says its model is.
      effort: What it says its effort is.
      provider: What it says its account is.
      capabilities: The mixins it serves, where not its harness's own.
      cost: What each answer costs, in USD.
      output_tokens: How many tokens each answer writes.
      seconds: How long each answer is reported to take; nothing actually waits.
      forks: Whether it can fork a session.
      names_late: Whether a session says its id only once its first turn has started, as a
        real CLI's does, rather than as it opens.

    Attributes:
      sessions: Every session it opened, in order.
      live: How many of them are open now.
      peak: The most of them that were open at once.
      closed: How many times it was closed.
    """

    def __init__(
        self,
        harness: HarnessKind | str = HarnessKind.CLAUDE,
        *,
        reply: Reply = None,
        model: str = "fake",
        effort: str = "",
        provider: str = "",
        capabilities: Iterable[type] | None = None,
        cost: float = 0.0,
        output_tokens: int = 1,
        seconds: float = 0.0,
        forks: bool = True,
        names_late: bool = False,
    ) -> None:
        self.harness = HarnessKind(harness)
        self.capabilities = (
            HARNESS_CAPABILITIES[self.harness]
            if capabilities is None
            else frozenset(capabilities)
        )
        self.script = _Script(reply)
        self.model = model
        self.effort = effort
        self.provider = provider
        self.cost = cost
        self.output_tokens = output_tokens
        self.seconds = seconds
        self.forks = forks
        self.names_late = names_late
        self.sessions: list[FakeSession] = []
        self.live = 0
        self.peak = 0
        self.closed = 0

    def __repr__(self) -> str:
        return f"<fake agent {self.harness}/{self.model}>"

    @property
    def prompts(self) -> list[str]:
        """Every prompt any of its sessions was given, in the order they were opened."""
        return [prompt for session in self.sessions for prompt in session.prompts]

    async def open(
        self,
        placement: Placement,
        *,
        permission: Permission,
        skills: tuple[Skill, ...],
        hooks: HookTable,
        fork_of: Any = None,
    ) -> FakeSession:
        forked: FakeSession | None = None
        if fork_of is not None:
            if not self.forks:
                raise UnsupportedOperation(f"{self.harness} cannot fork a session")
            if not isinstance(fork_of, FakeSession) or fork_of.driver is not self:
                raise SessionError(f"{fork_of!r} is not a session of this agent")
            if fork_of.closed:
                raise SessionError(f"{fork_of!r} is over")
            forked = fork_of
        session = FakeSession(self, placement, permission, skills, hooks, forked)
        self.sessions.append(session)
        self.live += 1
        self.peak = max(self.peak, self.live)
        return session

    async def close(self) -> None:
        self.closed += 1
        for session in self.sessions:
            await session.close()


# -------------------------------------------------------------------------- environments


class _Disk:
    """The files of one fake machine, shared by every environment on it.

    Its temporary copies are the machine's too, by the workdir copied and the id, as a real
    machine's are by where they are made -- so that an environment derived again, as a
    resumed run derives it, finds the copies made from it.
    """

    def __init__(self) -> None:
        self.files: dict[PurePosixPath, bytes] = {}
        self.commands: list[tuple[PurePosixPath, Command]] = []
        self.numbers = itertools.count(1)
        self.clones: dict[tuple[PurePosixPath, str], FakeEnvDriver] = {}
        #: Who holds each copy, until the run that took it closes.
        self.holders: dict[tuple[PurePosixPath, str], object] = {}


class FakeEnvDriver:
    """A working directory in a dictionary: files, commands and copies, all in memory.

    Args:
      files: What is in the workdir to start with, by path relative to it; text is written
        as UTF-8.
      workdir: Where it is on the fake machine.
      backend: What kind of machine it says it is.
      provider: Which one.
      capabilities: The mixins it serves; every one by default.
      cpu_count: The CPUs it reports.
      memory: The memory it reports, in bytes.
      gpu_count: The GPUs it reports.
      gpu_memory: The memory it reports for each GPU, in bytes.
      run: What answers `exec`; see :data:`Handler`. Commands it leaves are answered by
        the defaults.
      refs: The git refs `derive_worktree` knows.
      repo: Whether the workdir is a git repository, as `git rev-parse` answers.

    Closing one lets go of the holds on the temporary copies taken through it, leaving the
    copies where they are, as a real driver does: a copy's own as the run that derived it
    closes it, and every copy's on the machine as the fake they were made from is closed.

    Attributes:
      closed: How many times it was closed.
    """

    def __init__(
        self,
        files: Mapping[str, bytes | str] | None = None,
        *,
        workdir: str | PurePosixPath = "/work",
        backend: EnvBackendKind | str = EnvBackendKind.LOCAL,
        provider: str = "",
        capabilities: Iterable[type] | None = None,
        cpu_count: int = 8,
        memory: int = 64 << 30,
        gpu_count: int = 0,
        gpu_memory: int = 0,
        run: Handler = None,
        refs: Iterable[str] = ("HEAD", "main"),
        repo: bool = True,
        _disk: _Disk | None = None,
        _clone: tuple[PurePosixPath, str] | None = None,
    ) -> None:
        self.workdir = PurePosixPath(workdir)
        self.backend = EnvBackendKind(backend)
        self.provider = provider
        self.capabilities = (
            ENV_CAPABILITIES if capabilities is None else frozenset(capabilities)
        )
        self.cpu_count = cpu_count
        self.memory = memory
        self.gpu_count = gpu_count
        self.gpu_memory = gpu_memory
        self.handler = run
        self.refs = frozenset(refs)
        self.repo = repo
        self.available = True
        self.closed = 0
        self._root = _disk is None
        self._disk = _Disk() if _disk is None else _disk
        self._clone = _clone
        self._scratch: dict[str, FakeEnvDriver] = {}
        for path, data in (files or {}).items():
            self._disk.files[self._at(path)] = (
                data.encode() if isinstance(data, str) else data
            )

    def __repr__(self) -> str:
        return f"<fake env {self.backend}@{self.provider}{self.workdir}>"

    # ------------------------------------------------------------------ what a test reads

    @property
    def files(self) -> dict[str, bytes]:
        """What is under the workdir now, by path relative to it."""
        return {
            str(path.relative_to(self.workdir)): data
            for path, data in self._disk.files.items()
            if path.is_relative_to(self.workdir) and path != self.workdir
        }

    @property
    def machine(self) -> dict[str, bytes]:
        """Every file on the fake machine -- copies, worktrees, scratch -- by absolute path."""
        return {str(path): data for path, data in self._disk.files.items()}

    @property
    def commands(self) -> list[Command]:
        """Every command run in this workdir, in order."""
        return [command for at, command in self._disk.commands if at == self.workdir]

    def text(self, path: str) -> str:
        """What a file holds, as text."""
        return self._disk.files[self._at(path)].decode()

    # ----------------------------------------------------------------------- the driver

    def placement(self) -> Placement:
        return Placement(self.backend, self.provider, self.workdir)

    def _at(self, path: str | PurePosixPath) -> PurePosixPath:
        return self.workdir / path

    def _there(
        self,
        workdir: PurePosixPath,
        *,
        copy: bool,
        clone: tuple[PurePosixPath, str] | None = None,
    ) -> FakeEnvDriver:
        if copy:
            files = self._disk.files
            for path, data in list(files.items()):
                if path.is_relative_to(self.workdir) and not path.is_relative_to(
                    workdir
                ):
                    files[workdir / path.relative_to(self.workdir)] = data
        return FakeEnvDriver(
            workdir=workdir,
            backend=self.backend,
            provider=self.provider,
            capabilities=self.capabilities,
            cpu_count=self.cpu_count,
            memory=self.memory,
            gpu_count=self.gpu_count,
            gpu_memory=self.gpu_memory,
            run=self.handler,
            refs=self.refs,
            repo=self.repo,
            _disk=self._disk,
            _clone=clone,
        )

    def _gone(self, workdir: PurePosixPath) -> None:
        files = self._disk.files
        for path in [path for path in files if path.is_relative_to(workdir)]:
            del files[path]

    async def derive_subdir(self, subdir: PurePosixPath | str) -> FakeEnvDriver:
        under = PurePosixPath(subdir)
        if under.is_absolute() or ".." in under.parts:
            raise ValueError(f"{subdir} is not under {self.workdir}")
        return self._there(self.workdir / under, copy=False)

    async def exec(
        self,
        argv: Sequence[str] | str,
        *,
        timeout: float,  # noqa: ASYNC109 -- the driver's to enforce
    ) -> tuple[int, str, str]:
        command: Command = argv if isinstance(argv, str) else tuple(argv)
        self._disk.commands.append((self.workdir, command))
        try:
            async with asyncio.timeout(timeout or None):
                return await self._answer(command)
        except TimeoutError:
            raise EnvCommandTimeout(f"{command!r} ran past {timeout}s") from None

    async def _answer(self, command: Command) -> tuple[int, str, str]:
        handler: Any = self.handler
        said: Any = None
        if isinstance(handler, Mapping):
            table: Mapping[Command, tuple[int, str, str]] = handler  # pyright: ignore[reportUnknownVariableType]
            said = table.get(command)
        elif handler is not None:
            said = handler(command, self)
            if inspect.isawaitable(said):
                said = await said
        if said is not None:
            return said
        return await self._default(command)

    async def _default(self, command: Command) -> tuple[int, str, str]:
        argv = tuple(command.split()) if isinstance(command, str) else command
        name = argv[0] if argv else ""
        if name == "sleep" and len(argv) == 2:  # noqa: PLR2004 -- `sleep N`
            await asyncio.sleep(float(argv[1]))
            return 0, "", ""
        if isinstance(command, str):
            return 127, "", "fake: scripts are answered by `run=`, not interpreted\n"
        if name in ("true", ":"):
            return 0, "", ""
        if name == "false":
            return 1, "", ""
        if name == "echo":
            return 0, " ".join(argv[1:]) + "\n", ""
        if name == "cat":
            out: list[str] = []
            for path in argv[1:]:
                data = self._disk.files.get(self._at(path))
                if data is None:
                    return 1, "".join(out), f"cat: {path}: No such file or directory\n"
                out.append(data.decode(errors="replace"))
            return 0, "".join(out), ""
        if name == "ls":
            under = self._at(argv[1]) if len(argv) > 1 else self.workdir
            names = sorted(
                {
                    path.relative_to(under).parts[0]
                    for path in self._disk.files
                    if path.is_relative_to(under) and path != under
                }
            )
            return 0, "".join(f"{one}\n" for one in names), ""
        if argv == ("git", "rev-parse", "--is-inside-work-tree"):
            return (
                (0, "true\n", "")
                if self.repo
                else (128, "", "fatal: not a git repository\n")
            )
        return 127, "", f"fake: {name}: command not found\n"

    async def read(self, path: str) -> bytes:
        try:
            return self._disk.files[self._at(path)]
        except KeyError:
            raise EnvFileNotFound(f"{self._at(path)}: no such file") from None

    async def write(self, path: str, data: bytes) -> None:
        self._disk.files[self._at(path)] = bytes(data)

    async def derive_worktree(
        self,
        *,
        ref: str | None,
        dir: PurePosixPath | str | None,  # noqa: A002 -- the driver's name for it
    ) -> FakeEnvDriver:
        if not self.repo:
            raise WorktreeError(f"{self.workdir} is not a git repository")
        if ref is not None and ref not in self.refs:
            raise WorktreeError(f"no ref called {ref!r}")
        where = (
            self._at(dir)
            if dir is not None
            else PurePosixPath(f"/worktrees/{next(self._disk.numbers)}")
        )
        if any(path.is_relative_to(where) for path in self._disk.files):
            raise WorktreeError(f"{where} is taken")
        return self._there(where, copy=True)

    async def derive_temp_clone(
        self,
        id: str,  # noqa: A002 -- the driver's name for it
        *,
        holder: object,
    ) -> FakeEnvDriver:
        disk = self._disk
        key = (self.workdir, id)
        copy = disk.clones.get(key)
        if copy is None:
            copy = self._there(
                PurePosixPath(f"/clones/{next(disk.numbers)}-{id}"),
                copy=True,
                clone=key,
            )
        elif key in disk.holders:
            if disk.holders[key] != holder:
                raise TempCloneBusy(f"the copy {id!r} is somebody else's")
            return copy
        else:
            # Let go of as the run that took it closed, and taken again as it was left --
            # which is how a resumed run finds its copies.
            copy = self._there(copy.workdir, copy=False, clone=key)
        disk.clones[key] = copy
        disk.holders[key] = holder
        return copy

    async def destroy_temp_clone(self, id: str) -> None:  # noqa: A002 -- the driver's
        key = (self.workdir, id)
        copy = self._disk.clones.pop(key, None)
        self._disk.holders.pop(key, None)
        if copy is not None:
            self._gone(copy.workdir)

    async def derive_scratch(self, id: str) -> FakeEnvDriver:  # noqa: A002 -- the driver's
        scratch = self._scratch.get(id)
        if scratch is None:
            scratch = self._scratch[id] = self._there(
                PurePosixPath(f"/scratch/{next(self._disk.numbers)}-{id}"), copy=False
            )
        return scratch

    async def destroy_scratch(self, id: str) -> None:  # noqa: A002 -- the driver's
        scratch = self._scratch.pop(id, None)
        if scratch is not None:
            self._gone(scratch.workdir)

    @property
    def clones(self) -> list[str]:
        """The ids of the temporary copies made here and not yet removed."""
        return sorted(name for at, name in self._disk.clones if at == self.workdir)

    @property
    def scratches(self) -> list[str]:
        """The ids of the scratch directories made here and not yet removed."""
        return sorted(self._scratch)

    async def close(self) -> None:
        self.closed += 1
        # Holds on copies are let go of, and the copies left where they are, as a real
        # driver's are -- so that a run resumed on this machine takes them again. A copy is
        # closed by the run that derived it as it ends; the driver it was derived from, by
        # whoever made it.
        disk = self._disk
        if self._root:
            disk.holders.clear()
        elif self._clone is not None and disk.clones.get(self._clone) is self:
            disk.holders.pop(self._clone, None)


# ---------------------------------------------------------------------------- outworlders


class FakeOutworlder:
    """Whoever is outside the run, answering from a script, or away.

    Args:
      reply: What they answer with; see :data:`Reply`. A function of the prompt is given
        the schema asked for as `output_schema`.
      away: Whether nobody is there.

    Attributes:
      asked: Every prompt they were asked, in order.
    """

    def __init__(self, reply: Reply = None, *, away: bool = False) -> None:
        self._script = _Script(reply)
        self.away = away
        self.asked: list[str] = []

    async def run(
        self, prompt: str, output_schema: type[pydantic.BaseModel] | None
    ) -> Any:
        self.asked.append(prompt)
        return await self._script.next(prompt, output_schema, "the outworlder")


# --------------------------------------------------------------------------------- a run


async def run_fake(
    flow: Flow | str,
    task: str = "",
    *,
    agents: Mapping[str, AgentDriver | OutworlderDriver | Reply] | None = None,
    envs: Mapping[str, EnvDriver | Mapping[str, bytes | str]] | None = None,
    params: FlowParams | Mapping[str, Any] | None = None,
    budget: Budget | None = None,
    outworlder: OutworlderDriver | None = None,
    local: EnvDriver | None = None,
    journal: Path | None = None,
    resume: bool = False,
    recorder: Recorder | None = None,
) -> Any:
    """Runs a flow on fakes, with a fake for every role nobody gave one for.

    Args:
      flow: The flow, or a ref to load from where this is called.
      task: What to do.
      agents: By role: a driver, or what a :class:`FakeAgentDriver` for the role replies.
        A role left out gets a fake of the harness it asks for, or Claude Code -- which
        serves every mixin -- replying "ok". An `Outworlder` role given a reply is the
        run's outworlder, answering it.
      envs: By role: a driver, or the files a :class:`FakeEnvDriver` for it starts with. A
        role left out gets an empty one, large enough for what it asks of its machine.
      params: The params, or a mapping of them; the defaults where None.
      budget: What the run may spend; unlimited where None.
      outworlder: Whoever fills `Outworlder` roles; an away one where None.
      local: What fills `LocalEnv` roles; an empty fake where None.
      journal: Where a resumable flow's journal is written, or None.
      resume: Whether to pick up the run `journal` holds.
      recorder: What hears of every call and session, or None.

    Returns:
      What the flow returned.
    """
    from .engine import FlowImpl, load_flow, run_flow
    from .loading import Remote

    if isinstance(flow, str):
        frame = inspect.currentframe()
        asking = frame.f_back if frame is not None else None
        flow = load_flow(flow, caller_globals=asking.f_globals if asking else {})
        del frame, asking
    if isinstance(flow, Remote):
        flow = await flow.fetched()
    if not isinstance(flow, FlowImpl):
        raise TypeError(f"{flow!r} is not a flow the engine made")
    declared = flow.describe()
    # Whatever is left over once every role has taken its own is passed on as it is, for
    # `run_flow` to refuse by name.
    given: dict[str, Any] = dict(agents or {})
    drivers: dict[str, Any] = {}
    for role in declared.agents:
        said = given.pop(role.name, None)
        if role.auto:
            if said is not None and outworlder is None:
                outworlder = said if hasattr(said, "away") else FakeOutworlder(said)
            continue
        if said is None and not role.required:
            continue
        drivers[role.name] = (
            said
            if hasattr(said, "open") and hasattr(said, "capabilities")
            else FakeAgentDriver(role.harness or HarnessKind.CLAUDE, reply=said)
        )
    drivers.update(given)
    places: dict[str, Any] = dict(envs or {})
    environments: dict[str, Any] = {}
    for role in declared.envs:
        said = places.pop(role.name, None)
        if role.auto or (said is None and not role.required):
            continue
        environments[role.name] = (
            said
            if hasattr(said, "placement")
            else FakeEnvDriver(
                said,
                workdir=f"/{role.name}",
                cpu_count=max(role.cpu_count, 8),
                memory=max(role.memory, 64 << 30),
                gpu_count=role.gpu_count,
                gpu_memory=role.gpu_memory,
            )
        )
    environments.update(places)
    return await run_flow(
        flow,
        task,
        agents=drivers,
        envs=environments,
        params={} if params is None else params,
        budget=Budget(cost=math.inf) if budget is None else budget,
        outworlder=outworlder,
        journal=journal,
        resume=resume,
        local=FakeEnvDriver(workdir="/here") if local is None else local,
        recorder=recorder,
    )
