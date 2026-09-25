"""What every driver promises the flow engine, as checks any driver can be run through.

The engine is written against :mod:`hmz.runtime.flowing.spi` and nothing else, so a driver
is correct when it keeps the promises written there -- whichever harness or machine it drives,
and whether it is real or a fake. These are those promises as runnable checks, one per kind of
driver: a harness driver's tests run :func:`check_agent_driver` against it, an environment
driver's run :func:`check_env_driver`, and the engine's fakes run both, so that what the engine
is tested against is what it will be run against.

A helper rather than a test module: it is imported by path from any tier, so the same checks
run against a stand-in CLI in `tests/integration` and a real one in `tests/system`. Every
assertion says what it expected, since pytest does not rewrite the asserts of a helper.

What a check sends is written down here -- :data:`ANSWERS`, :data:`SLOW_ARGV`,
:data:`SLOW_SCRIPT` -- so that a fake with no shell behind it can be scripted to answer it.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import threading
from typing import TYPE_CHECKING, Any

import pydantic
import pytest

from hmz.flows import (
    BashEnvMixin,
    EnvBackendKind,
    EnvCommandTimeout,
    EnvFileNotFound,
    FilesEnvMixin,
    GitWorktreeEnvMixin,
    HarnessKind,
    HookKind,
    HookResult,
    Permission,
    ScratchDirEnvMixin,
    SessionError,
    ShellEnvMixin,
    SteeringAgentMixin,
    StopHookResult,
    TempCloneBusy,
    TemporaryClonedDirEnvMixin,
    UnsupportedOperation,
    Usage,
    UserPromptSubmitHookResult,
    WorktreeError,
)
from hmz.runtime.flowing.spi import (
    AGENT_CAPABILITIES,
    ENV_CAPABILITIES,
    HARNESS_CAPABILITIES,
    HookTable,
    Placement,
    TurnRequest,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.runtime.flowing.spi import AgentDriver, EnvDriver, SessionHandle

__all__ = [
    "ANSWERS",
    "SLOW_ARGV",
    "SLOW_SCRIPT",
    "Answer",
    "RecordingSink",
    "check_agent_driver",
    "check_env_driver",
]

#: The prompt a plain turn is asked, which any model answers in a word.
PROMPT = "Reply with the single word: ok"

#: The prompt a schema turn is asked, alongside :class:`Answer`.
SCHEMA_PROMPT = 'Reply with a JSON object whose "answer" is "ok".'

#: The commands the environment checks run, and what each must come to: exit status, stdout
#: and stderr. A tuple is an argv, a string is a bash script.
ANSWERS: Mapping[tuple[str, ...] | str, tuple[int, str, str]] = {
    ("sh", "-c", "printf out; printf err >&2; exit 3"): (3, "out", "err"),
    ("printf", "%s", "a b"): (0, "a b", ""),
    "printf '%s' $((1 + 2)) | tr 3 x": (0, "x", ""),
}

#: A program that runs far longer than any timeout a check gives it.
SLOW_ARGV = ("sleep", "30")

#: The same, as a script.
SLOW_SCRIPT = "sleep 30"

#: How long a check waits for a turn or command it started to be under way.
SETTLE = 0.5


class Answer(pydantic.BaseModel):
    """What a schema turn is asked for."""

    answer: str = ""


class RecordingSink:
    """A usage sink that adds up what it is told, from whichever thread tells it."""

    def __init__(self) -> None:
        """Initializes a sink that has been told nothing."""
        self._lock = threading.Lock()
        self.cost = 0.0
        self.output_tokens = 0
        self.duration = 0.0
        self.calls = 0

    def add(self, *, cost: float, output_tokens: int, duration: float) -> None:
        with self._lock:
            self.cost += cost
            self.output_tokens += output_tokens
            self.duration += duration
            self.calls += 1


# ----------------------------------------------------------------------------------- agents


async def check_agent_driver(
    driver: AgentDriver,
    placement: Placement,
    *,
    permission: Permission | None = None,
    slow_prompt: str | None = None,
    moments: bool = True,
    settle: float = SETTLE,
) -> None:
    """Holds an agent driver to what :mod:`hmz.runtime.flowing.spi` promises.

    Opens a session, takes a plain turn and a schema turn, and checks that usage is reported
    through the sink and adds up, that `interrupt` is idempotent from any thread, that
    `steer` is refused with no turn in flight where the driver steers at all, that a fork is
    either a session that takes turns or `UnsupportedOperation`, and that `close` is
    idempotent and final. Closes the driver at the end, whether or not it passed.

    Args:
      driver: The driver, which the check closes.
      placement: Where its sessions work.
      permission: What they may touch, or None for the default.
      slow_prompt: A prompt that keeps a turn busy for well over a second, to check that
        interrupting, cancelling and steering a turn in flight behave; None to skip those.
      moments: Whether to check that `USER_PROMPT_SUBMIT` and `STOP` reach hooks, which
        every harness does.
      settle: How many seconds a turn is given to be under way before it is interrupted.
    """
    try:
        await _takes_turns(
            driver,
            placement,
            permission=permission,
            slow_prompt=slow_prompt,
            moments=moments,
            settle=settle,
        )
    finally:
        await driver.close()
        await driver.close()


async def _takes_turns(
    driver: AgentDriver,
    placement: Placement,
    *,
    permission: Permission | None,
    slow_prompt: str | None,
    moments: bool,
    settle: float,
) -> None:
    """Everything :func:`check_agent_driver` checks, bar closing the driver."""
    assert isinstance(driver.harness, HarnessKind), driver.harness
    assert driver.capabilities <= AGENT_CAPABILITIES, driver.capabilities
    assert driver.capabilities == HARNESS_CAPABILITIES[driver.harness], (
        f"{driver.harness} serves exactly {HARNESS_CAPABILITIES[driver.harness]}, "
        f"not {driver.capabilities}"
    )
    for said in (driver.model, driver.effort, driver.provider):
        assert isinstance(said, str), said

    heard: list[tuple[HookKind, dict[str, Any]]] = []
    hooks = HookTable()

    def hears(kind: HookKind, answer: HookResult) -> None:
        async def bound(handle: SessionHandle, fields: dict[str, Any]) -> HookResult:
            del handle
            heard.append((kind, fields))
            return answer

        hooks.set(kind, bound)

    hears(HookKind.USER_PROMPT_SUBMIT, UserPromptSubmitHookResult())
    hears(HookKind.STOP, StopHookResult())
    handle = await driver.open(
        placement, permission=permission or Permission(), skills=(), hooks=hooks
    )
    sink = RecordingSink()
    try:
        said = await handle.turn(TurnRequest(PROMPT), sink)
        assert isinstance(said, str), f"a plain turn answered {said!r}"
        first = handle.usage
        assert isinstance(first, Usage), first
        answered = await handle.turn(TurnRequest(SCHEMA_PROMPT, Answer), sink)
        assert isinstance(answered, Answer), f"a schema turn answered {answered!r}"
        second = handle.usage
        assert second.output_tokens >= first.output_tokens, (first, second)
        assert second.cost >= first.cost, (first, second)
        assert second.duration >= first.duration, (first, second)
        assert second.output_tokens > 0, f"two turns wrote no tokens: {second}"
        _agrees(sink, second)
        if moments:
            kinds = {kind for kind, _ in heard}
            assert kinds >= {HookKind.USER_PROMPT_SUBMIT, HookKind.STOP}, heard
            prompts = [
                fields.get("prompt")
                for kind, fields in heard
                if kind is HookKind.USER_PROMPT_SUBMIT
            ]
            assert PROMPT in prompts, prompts

        handle.interrupt()
        handle.interrupt()
        await asyncio.to_thread(handle.interrupt)
        again = await handle.turn(TurnRequest(PROMPT), sink)
        assert isinstance(again, str), (
            "a session interrupted at rest took no more turns"
        )

        steers = SteeringAgentMixin in driver.capabilities
        if steers:
            with pytest.raises(SessionError):
                await handle.steer("nobody is listening", queued=True)
        if slow_prompt is not None:
            await _in_flight(handle, slow_prompt, sink, steers=steers, settle=settle)
            _agrees(sink, handle.usage)
        await _forks(driver, placement, handle, permission)
    finally:
        await handle.close()
    await handle.close()
    with pytest.raises(SessionError):
        await handle.turn(TurnRequest(PROMPT), RecordingSink())


def _agrees(sink: RecordingSink, usage: Usage) -> None:
    """Checks that a session's usage is what its turns reported through their sinks."""
    assert sink.output_tokens == usage.output_tokens, (sink.output_tokens, usage)
    assert math.isclose(sink.cost, usage.cost, rel_tol=1e-6, abs_tol=1e-9), (
        sink.cost,
        usage,
    )
    assert math.isclose(
        sink.duration, usage.duration.total_seconds(), rel_tol=1e-3, abs_tol=1e-3
    ), (sink.duration, usage)


async def _in_flight(
    handle: SessionHandle,
    slow: str,
    sink: RecordingSink,
    *,
    steers: bool,
    settle: float,
) -> None:
    """Interrupts, cancels and steers a turn while it is under way."""
    turning = asyncio.create_task(handle.turn(TurnRequest(slow), sink))
    await asyncio.sleep(settle)
    assert not turning.done(), "the slow prompt was over before it could be interrupted"
    await asyncio.to_thread(handle.interrupt)
    with pytest.raises(SessionError):
        await asyncio.wait_for(turning, 60)

    turning = asyncio.create_task(handle.turn(TurnRequest(slow), sink))
    await asyncio.sleep(settle)
    turning.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(turning, 60)

    if steers:
        turning = asyncio.create_task(handle.turn(TurnRequest(slow), sink))
        await asyncio.sleep(settle)
        await handle.steer(
            "stop now and reply with the single word: steered", queued=False
        )
        said = await asyncio.wait_for(turning, 120)
        assert isinstance(said, str), f"a steered turn answered {said!r}"

    again = await handle.turn(TurnRequest(PROMPT), sink)
    assert isinstance(again, str), (
        "a session took no more turns after one was interrupted"
    )


async def _forks(
    driver: AgentDriver,
    placement: Placement,
    handle: SessionHandle,
    permission: Permission | None,
) -> None:
    """Forks a session where the harness can, and checks the fork takes turns."""
    try:
        forked = await driver.open(
            placement,
            permission=permission or Permission(),
            skills=(),
            hooks=HookTable(),
            fork_of=handle,
        )
    except UnsupportedOperation:
        return
    try:
        sink = RecordingSink()
        said = await forked.turn(TurnRequest(PROMPT), sink)
        assert isinstance(said, str), f"a forked session answered {said!r}"
        _agrees(sink, forked.usage)
    finally:
        await forked.close()


# ----------------------------------------------------------------------------- environments


async def check_env_driver(
    driver: EnvDriver, *, repo: bool = False, settle: float = SETTLE
) -> None:
    """Holds an environment driver to what :mod:`hmz.runtime.flowing.spi` promises.

    Checks what it says about itself, then each capability it lists: commands and their
    timeouts, files, subdirectories, worktrees, temporary copies and their holders, scratch
    directories. Leaves `contract/` under the workdir behind it, and closes the driver and
    everything derived from it, whether or not it passed.

    Args:
      driver: The driver, whose workdir is writable and which the check closes.
      repo: Whether the workdir is in a git repository with a commit, which is what checking
        worktrees takes. Worktrees are not checked without one.
      settle: How many seconds a command is given to be under way before it is timed out or
        cancelled.
    """
    async with contextlib.AsyncExitStack() as closing:
        closing.push_async_callback(driver.close)
        closing.push_async_callback(driver.close)
        capabilities = driver.capabilities
        assert isinstance(driver.backend, EnvBackendKind), driver.backend
        assert capabilities <= ENV_CAPABILITIES, capabilities
        assert BashEnvMixin not in capabilities or ShellEnvMixin in capabilities, (
            capabilities
        )
        assert driver.cpu_count >= 1, driver.cpu_count
        assert min(driver.memory, driver.gpu_count, driver.gpu_memory) >= 0
        placement = driver.placement()
        assert isinstance(placement, Placement), placement
        assert (placement.backend, placement.provider, placement.workdir) == (
            driver.backend,
            driver.provider,
            driver.workdir,
        ), placement

        if ShellEnvMixin in capabilities:
            await _runs(driver, scripts=BashEnvMixin in capabilities, settle=settle)
        if FilesEnvMixin in capabilities:
            await _files(driver)
        await _subdirs(driver, closing)
        if GitWorktreeEnvMixin in capabilities and repo:
            await _worktrees(driver, closing)
        if TemporaryClonedDirEnvMixin in capabilities:
            await _clones(driver, closing)
        if ScratchDirEnvMixin in capabilities:
            await _scratches(driver, closing)
        # Asked last rather than first: a driver that connects lazily has seen nothing of
        # its machine until something has been done there.
        assert driver.available, "a driver that has done all of that is not available"


async def _derived(closing: contextlib.AsyncExitStack, derived: EnvDriver) -> EnvDriver:
    """A driver derived during a check, closed when the check is over."""
    closing.push_async_callback(derived.close)
    return derived


async def _runs(driver: EnvDriver, *, scripts: bool, settle: float) -> None:
    """Runs what :data:`ANSWERS` holds, and what should time out."""
    for command, answer in ANSWERS.items():
        if isinstance(command, str) and not scripts:
            continue
        said = await driver.exec(
            command if isinstance(command, str) else list(command), timeout=30
        )
        assert said == answer, f"{command!r} answered {said!r}, not {answer!r}"
    slow: list[list[str] | str] = [list(SLOW_ARGV), *([SLOW_SCRIPT] if scripts else [])]
    for command in slow:
        with pytest.raises(EnvCommandTimeout) as raised:
            await driver.exec(command, timeout=settle)
        assert isinstance(raised.value, TimeoutError), raised.value
        running = asyncio.create_task(driver.exec(command, timeout=0))
        await asyncio.sleep(settle)
        assert not running.done(), f"{command!r} was over before it could be cancelled"
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, 30)


async def _files(driver: EnvDriver) -> None:
    """Writes, reads and misses a file."""
    written = b"bytes \x00\xff\n"
    await driver.write("contract/deep/a.bin", written)
    got = await driver.read("contract/deep/a.bin")
    assert got == written, got
    if driver.workdir.is_absolute():
        got = await driver.read(str(driver.workdir / "contract/deep/a.bin"))
        assert got == written, "an absolute path read something else"
    with pytest.raises(EnvFileNotFound) as raised:
        await driver.read("contract/missing")
    assert isinstance(raised.value, FileNotFoundError), raised.value


async def _subdirs(driver: EnvDriver, closing: contextlib.AsyncExitStack) -> None:
    """Derives a subdirectory, and is refused one outside the workdir."""
    sub = await _derived(closing, await driver.derive_subdir("contract/sub"))
    assert sub.workdir == driver.workdir / "contract/sub", sub.workdir
    assert sub.capabilities == driver.capabilities, sub.capabilities
    assert (sub.backend, sub.provider) == (driver.backend, driver.provider)
    if FilesEnvMixin in driver.capabilities:
        await sub.write("x.txt", b"x")
        got = await driver.read("contract/sub/x.txt")
        assert got == b"x", "a subdirectory wrote somewhere else"
    for outside in ("../outside", "/outside"):
        with pytest.raises(ValueError, match=r"."):
            await driver.derive_subdir(outside)


async def _worktrees(driver: EnvDriver, closing: contextlib.AsyncExitStack) -> None:
    """Checks out a worktree, and is refused a ref nobody has."""
    tree = await _derived(closing, await driver.derive_worktree(ref=None, dir=None))
    assert tree.workdir != driver.workdir, tree.workdir
    assert tree.capabilities == driver.capabilities, tree.capabilities
    if ShellEnvMixin in driver.capabilities:
        said = await tree.exec(
            ["git", "rev-parse", "--is-inside-work-tree"], timeout=30
        )
        assert said[:2] == (0, "true\n"), said
    with pytest.raises(WorktreeError):
        await driver.derive_worktree(ref="no-such-ref-anywhere", dir=None)


async def _clones(driver: EnvDriver, closing: contextlib.AsyncExitStack) -> None:
    """Copies the workdir, holds the copy, and frees it."""
    mine, theirs = object(), object()
    copy = await _derived(
        closing, await driver.derive_temp_clone("contract", holder=mine)
    )
    assert copy.workdir != driver.workdir, copy.workdir
    assert copy.capabilities == driver.capabilities, copy.capabilities
    again = await _derived(
        closing, await driver.derive_temp_clone("contract", holder=mine)
    )
    assert again.workdir == copy.workdir, "one holder got two copies under one id"
    with pytest.raises(TempCloneBusy):
        await driver.derive_temp_clone("contract", holder=theirs)
    if FilesEnvMixin in driver.capabilities:
        got = await copy.read("contract/deep/a.bin")
        assert got == b"bytes \x00\xff\n", "the copy is not of the workdir"
        await copy.write("contract/deep/a.bin", b"changed")
        got = await driver.read("contract/deep/a.bin")
        assert got == b"bytes \x00\xff\n", "writing the copy wrote the workdir"
    await driver.destroy_temp_clone("contract")
    await driver.destroy_temp_clone("contract")
    taken = await _derived(
        closing, await driver.derive_temp_clone("contract", holder=theirs)
    )
    assert taken.workdir != driver.workdir, taken.workdir
    await driver.destroy_temp_clone("contract")
    await driver.destroy_temp_clone("never-made")


async def _scratches(driver: EnvDriver, closing: contextlib.AsyncExitStack) -> None:
    """Makes a scratch directory twice under one id, and removes it."""
    scratch = await _derived(closing, await driver.derive_scratch("contract"))
    same = await _derived(closing, await driver.derive_scratch("contract"))
    assert same.workdir == scratch.workdir, "one id made two scratch directories"
    assert scratch.workdir != driver.workdir, scratch.workdir
    if FilesEnvMixin in driver.capabilities:
        await scratch.write("kept.txt", b"kept")
        got = await same.read("kept.txt")
        assert got == b"kept", "one scratch directory read another's file"
    await driver.destroy_scratch("contract")
    await driver.destroy_scratch("contract")
