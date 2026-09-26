"""The driver contract checks, run against the smallest drivers that keep the contract.

`tests/flows/contracts.py` is what every real driver and every fake is held to, and nothing
else runs it until there are drivers. These stubs keep every promise in the fewest lines --
in memory, with no process and no socket -- so that the checks themselves are exercised: a
check that cannot pass is found here rather than by the first driver written against it.
And a stub that breaks one promise is refused, so a check that cannot fail is found too.
"""

from __future__ import annotations

import asyncio
import datetime
import itertools
import threading
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import pytest

from hmz.flows import (
    EnvBackendKind,
    EnvCommandTimeout,
    EnvFileNotFound,
    HarnessKind,
    HookKind,
    LoopCommandAgentMixin,
    SessionError,
    TempCloneBusy,
    UnsupportedOperation,
    Usage,
    WorktreeError,
)
from hmz.runtime.flowing.spi import (
    AGENT_CAPABILITIES,
    ENV_CAPABILITIES,
    HARNESS_CAPABILITIES,
    HookTable,
    Placement,
    Skill,
    TurnRequest,
    UsageSink,
)
from tests.flows.contracts import (
    ANSWERS,
    SLOW_ARGV,
    SLOW_SCRIPT,
    Answer,
    check_agent_driver,
    check_env_driver,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pydantic

    from hmz.flows import Permission
    from hmz.runtime.flowing.spi import SessionHandle

#: The prompt the stub agent keeps busy on until it is interrupted or steered.
SLOW = "count to a million, slowly"


class StubSession:
    """A session whose every turn costs a cent and writes five tokens, instantly."""

    def __init__(self, hooks: HookTable) -> None:
        self._hooks = hooks
        self._spent = [0.0, 0, 0.0]
        self._closed = False
        self._turning = False
        self._interrupted = threading.Event()
        self._steered: str | None = None

    @property
    def id(self) -> str | None:
        return "stub"

    @property
    def usage(self) -> Usage:
        cost, tokens, seconds = self._spent
        return Usage(
            cost=float(cost),
            output_tokens=int(tokens),
            duration=datetime.timedelta(seconds=seconds),
        )

    async def turn(
        self, request: TurnRequest, sink: UsageSink
    ) -> str | pydantic.BaseModel:
        if self._closed:
            raise SessionError("the session is closed")
        await self._hooks.fire(HookKind.USER_PROMPT_SUBMIT, self, prompt=request.prompt)
        self._interrupted.clear()
        self._steered = None
        self._turning = True
        try:
            said = "ok"
            if request.prompt == SLOW:
                while self._steered is None:
                    if self._interrupted.is_set():
                        raise SessionError("interrupted")
                    await asyncio.sleep(0.01)
                said = "steered"
            self._spend(sink)
            await self._hooks.fire(HookKind.STOP, self, said=said, again=0)
        finally:
            self._turning = False
        if request.output_schema is not None:
            return Answer(answer=said)
        return said

    def _spend(self, sink: UsageSink) -> None:
        sink.add(cost=0.01, output_tokens=5, duration=0.25)
        self._spent[0] += 0.01
        self._spent[1] += 5
        self._spent[2] += 0.25

    async def steer(self, prompt: str, *, queued: bool) -> None:
        del queued
        if not self._turning:
            raise SessionError("no turn is in flight")
        self._steered = prompt

    def interrupt(self) -> None:
        self._interrupted.set()

    async def close(self) -> None:
        self._closed = True
        self.interrupt()


class StubAgent:
    """A driver of stub sessions of one harness, serving its capabilities unless told others."""

    def __init__(
        self,
        harness: HarnessKind,
        *,
        capabilities: frozenset[type] | None = None,
        forks: bool = True,
    ) -> None:
        self.harness = harness
        self.capabilities = (
            HARNESS_CAPABILITIES[harness] if capabilities is None else capabilities
        )
        self.forks = forks
        self.closed = 0

    model = "stub"
    effort = ""
    provider = ""

    async def open(
        self,
        placement: Placement,
        *,
        permission: Permission,
        skills: tuple[Skill, ...],
        hooks: HookTable,
        fork_of: SessionHandle | None = None,
    ) -> StubSession:
        del placement, permission, skills
        if fork_of is not None and not self.forks:
            raise UnsupportedOperation("the stub cannot fork")
        return StubSession(hooks)

    async def close(self) -> None:
        self.closed += 1


class StubEnv:
    """A driver over a dictionary of files, answering exactly the commands the checks send."""

    _numbers = itertools.count()

    def __init__(
        self,
        workdir: PurePosixPath,
        files: dict[PurePosixPath, bytes],
        capabilities: frozenset[type],
    ) -> None:
        self.workdir = workdir
        self.files = files
        self.capabilities = capabilities
        self._held: dict[str, tuple[object, StubEnv]] = {}
        self._scratch: dict[str, StubEnv] = {}
        self.closed = 0

    backend = EnvBackendKind.LOCAL
    provider = ""
    cpu_count = 4
    memory = 1 << 30
    gpu_count = 0
    gpu_memory = 0
    available = True

    def placement(self) -> Placement:
        return Placement(self.backend, self.provider, self.workdir)

    def _at(self, path: str | PurePosixPath) -> PurePosixPath:
        return self.workdir / path

    def _elsewhere(self, where: PurePosixPath, *, copy: bool) -> StubEnv:
        if copy:
            for path, data in list(self.files.items()):
                if path.is_relative_to(self.workdir):
                    self.files[where / path.relative_to(self.workdir)] = data
        return StubEnv(where, self.files, self.capabilities)

    async def derive_subdir(self, subdir: PurePosixPath | str) -> StubEnv:
        under = PurePosixPath(subdir)
        if under.is_absolute() or ".." in under.parts:
            raise ValueError(f"{subdir} is not under the workdir")
        return StubEnv(self.workdir / under, self.files, self.capabilities)

    async def exec(
        self,
        argv: Sequence[str] | str,
        *,
        timeout: float,  # noqa: ASYNC109 -- the contract's
    ) -> tuple[int, str, str]:
        command = argv if isinstance(argv, str) else tuple(argv)
        if command in ANSWERS:
            return ANSWERS[command]
        if command in (SLOW_ARGV, SLOW_SCRIPT):
            try:
                async with asyncio.timeout(timeout or None):
                    await asyncio.sleep(30)
            except TimeoutError:
                raise EnvCommandTimeout(f"{command!r} ran past {timeout}s") from None
            return 0, "", ""
        if command == ("git", "rev-parse", "--is-inside-work-tree"):
            return 0, "true\n", ""
        return 127, "", f"stub: {command!r}: command not found\n"

    async def read(self, path: str) -> bytes:
        try:
            return self.files[self._at(path)]
        except KeyError:
            raise EnvFileNotFound(path) from None

    async def write(self, path: str, data: bytes) -> None:
        self.files[self._at(path)] = data

    async def derive_worktree(
        self,
        *,
        ref: str | None,
        dir: PurePosixPath | str | None,  # noqa: A002 -- the contract's
    ) -> StubEnv:
        if ref == "no-such-ref-anywhere":
            raise WorktreeError(f"unknown ref {ref}")
        where = self._at(dir) if dir else PurePosixPath(f"/trees/{next(self._numbers)}")
        return self._elsewhere(where, copy=True)

    async def derive_temp_clone(
        self,
        id: str,  # noqa: A002 -- the contract's
        *,
        holder: object,
    ) -> StubEnv:
        held = self._held.get(id)
        if held is not None:
            if held[0] != holder:
                raise TempCloneBusy(f"{id} is held")
            return held[1]
        copy = self._elsewhere(
            PurePosixPath(f"/clones/{next(self._numbers)}"), copy=True
        )
        self._held[id] = (holder, copy)
        return copy

    async def destroy_temp_clone(self, id: str) -> None:  # noqa: A002 -- the contract's
        self._held.pop(id, None)

    async def derive_scratch(self, id: str) -> StubEnv:  # noqa: A002 -- the contract's
        if id not in self._scratch:
            where = PurePosixPath(f"/scratch/{next(self._numbers)}")
            self._scratch[id] = self._elsewhere(where, copy=False)
        return self._scratch[id]

    async def destroy_scratch(self, id: str) -> None:  # noqa: A002 -- the contract's
        self._scratch.pop(id, None)

    async def close(self) -> None:
        self.closed += 1


def _env(capabilities: frozenset[type] = ENV_CAPABILITIES) -> StubEnv:
    return StubEnv(PurePosixPath("/work"), {}, capabilities)


PLACED = Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/work"))


#: How long the checks give a stub to be under way, which is no time at all.
QUICK = 0.02


@pytest.mark.parametrize("harness", sorted(HARNESS_CAPABILITIES))
async def test_a_driver_serving_a_harness_passes_the_agent_check(
    harness: HarnessKind,
) -> None:
    agent = StubAgent(harness)
    await check_agent_driver(agent, PLACED, settle=QUICK)
    assert agent.closed == 2


@pytest.mark.parametrize(
    "harness", [HarnessKind.CLAUDE, HarnessKind.OPENCODE], ids=["steers", "does-not"]
)
async def test_a_turn_in_flight_is_interrupted_cancelled_and_steered(
    harness: HarnessKind,
) -> None:
    await check_agent_driver(StubAgent(harness), PLACED, slow_prompt=SLOW, settle=QUICK)


async def test_a_driver_that_cannot_fork_says_so_and_still_passes() -> None:
    await check_agent_driver(
        StubAgent(HarnessKind.CLAUDE, forks=False), PLACED, settle=QUICK
    )


@pytest.mark.parametrize(
    "capabilities",
    [
        frozenset({object}),
        AGENT_CAPABILITIES - {LoopCommandAgentMixin},
        frozenset[type](),
    ],
    ids=["no-mixin", "less", "nothing"],
)
async def test_the_agent_check_refuses_capabilities_other_than_the_harness_own(
    capabilities: frozenset[type],
) -> None:
    agent = StubAgent(HarnessKind.CLAUDE, capabilities=capabilities)
    with pytest.raises(AssertionError):
        await check_agent_driver(agent, PLACED, settle=QUICK)
    assert agent.closed == 2, "a driver that failed the check was left open"


async def test_the_agent_check_refuses_usage_the_sink_never_heard_of() -> None:
    class Unreported(StubSession):
        def _spend(self, sink: UsageSink) -> None:
            del sink
            self._spent[1] += 5

    class Agent(StubAgent):
        async def open(
            self,
            placement: Placement,
            *,
            permission: Permission,
            skills: tuple[Skill, ...],
            hooks: HookTable,
            fork_of: SessionHandle | None = None,
        ) -> StubSession:
            return Unreported(hooks)

    with pytest.raises(AssertionError):
        await check_agent_driver(Agent(HarnessKind.OPENCODE), PLACED, settle=QUICK)


@pytest.mark.parametrize(
    "capabilities",
    [ENV_CAPABILITIES, frozenset[type]()],
    ids=["everything", "nothing"],
)
async def test_a_driver_that_keeps_the_contract_passes_the_env_check(
    capabilities: frozenset[type],
) -> None:
    await check_env_driver(_env(capabilities), repo=True, settle=QUICK)


async def test_the_env_check_refuses_a_temporary_copy_anyone_can_take() -> None:
    class Shared(StubEnv):
        async def derive_temp_clone(
            self,
            id: str,  # noqa: A002 -- the contract's
            *,
            holder: object,
        ) -> StubEnv:
            return await super().derive_temp_clone(id, holder=None)

    shared = Shared(PurePosixPath("/work"), {}, ENV_CAPABILITIES)
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        await check_env_driver(shared, settle=QUICK)
    assert shared.closed == 2, "a driver that failed the check was left open"


async def test_a_driver_that_connects_lazily_is_available_once_it_has_been_used() -> (
    None
):
    class Lazy(StubEnv):
        seen = False

        @property
        def available(self) -> bool:
            return self.seen

        async def exec(
            self,
            argv: Sequence[str] | str,
            *,
            timeout: float,  # noqa: ASYNC109 -- the contract's
        ) -> tuple[int, str, str]:
            self.seen = True
            return await super().exec(argv, timeout=timeout)

    await check_env_driver(
        Lazy(PurePosixPath("/work"), {}, ENV_CAPABILITIES), settle=QUICK
    )
