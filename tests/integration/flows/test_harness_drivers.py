"""The harness drivers, held to their contract against stand-in CLIs on PATH.

Every driver is run through :func:`tests.flows.contracts.check_agent_driver` against a stand-in
for Claude Code (a process held open), Codex (an app server) and opencode (a command a turn),
and then through what the contract does not reach: hooks carried from the CLI's threads to the
loop and back, steering, forks across workdirs, a turn's limits, a failed turn's error, and the
outworlder. The stand-ins are :mod:`tests.flows.standins`.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import pydantic
import pytest

from hmz.flows import (
    AskUserHookResult,
    CostExceeded,
    DurationExceeded,
    EnvBackendKind,
    HarnessKind,
    HarnessNotInstalled,
    HarnessRefused,
    HookKind,
    HookResult,
    ModelUnavailable,
    NotificationHookResult,
    OutputSchemaError,
    OutputTokensExceeded,
    OutworlderAway,
    Permission,
    PermissionKind,
    PermissionRequestHookResult,
    PreToolUseHookResult,
    SessionEndHookResult,
    SessionError,
    SessionStartHookResult,
    StopHookResult,
    SubagentStartHookResult,
    SubagentStopHookResult,
    UnsupportedOperation,
    UserPromptSubmitHookResult,
)
from hmz.runtime.flowing import harnesses
from hmz.runtime.flowing.harnesses import HarnessSession, open_agent, open_outworlder
from hmz.runtime.flowing.specs import AgentSpec
from hmz.runtime.flowing.spi import HookTable, Limits, Placement, Skill, TurnRequest
from tests.flows import standins
from tests.flows.contracts import RecordingSink, check_agent_driver

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from hmz.coganchor.agents import Question
    from hmz.runtime.flowing.harnesses import HarnessDriver
    from hmz.runtime.flowing.spi import SessionHandle

pytestmark = pytest.mark.timeout(120)

#: What each stand-in is driven as, at a model the price list in `priced` names.
SPECS = {
    HarnessKind.CLAUDE: AgentSpec(
        "coder", HarnessKind.CLAUDE, "", "claude-haiku-4-5", "low", "claude"
    ),
    HarnessKind.CODEX: AgentSpec(
        "coder", HarnessKind.CODEX, "", "gpt-5.5", "low", "codex"
    ),
    HarnessKind.OPENCODE: AgentSpec(
        "coder", HarnessKind.OPENCODE, "", "opencode/big-pickle", "high", "opencode"
    ),
}


class Logs:
    """Where the stand-ins are, and what they were asked."""

    def __init__(self, binaries: Path) -> None:
        self.binaries = binaries

    def of(self, cli: str) -> list[dict[str, Any]]:
        """Everything one stand-in wrote down, oldest first."""
        at = self.binaries / f"{cli}.log"
        if not at.exists():
            return []
        return [json.loads(line) for line in at.read_text().splitlines()]


@pytest.fixture
def clis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Logs:
    """Puts the three stand-ins on PATH, with a home of their own."""
    binaries = tmp_path / "bin"
    standins.install(binaries, "claude", standins.CLAUDE)
    standins.install(binaries, "codex", standins.CODEX)
    standins.install(binaries, "opencode", standins.OPENCODE)
    monkeypatch.setenv("PATH", standins.path_with(binaries))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    return Logs(binaries)


def _placement(where: Path) -> Placement:
    where.mkdir(parents=True, exist_ok=True)
    return Placement(EnvBackendKind.LOCAL, "", PurePosixPath(str(where)))


@pytest.fixture
def work(tmp_path: Path) -> Placement:
    """A workdir on this machine."""
    return _placement(tmp_path / "work")


def _hears(
    table: HookTable, kind: HookKind, answer: HookResult
) -> list[dict[str, Any]]:
    """Hangs a hook that answers `answer` and writes down what it was told."""
    heard: list[dict[str, Any]] = []

    async def bound(handle: SessionHandle, fields: dict[str, Any]) -> HookResult:
        del handle
        heard.append(fields)
        return answer

    table.set(kind, bound)
    return heard


@pytest.fixture
async def claude(clis: Logs) -> AsyncIterator[HarnessDriver]:
    """A driver of the Claude Code stand-in, closed afterwards."""
    del clis
    driver = open_agent(SPECS[HarnessKind.CLAUDE])
    yield driver
    await driver.close()


@pytest.fixture
async def codex(clis: Logs) -> AsyncIterator[HarnessDriver]:
    """A driver of the Codex stand-in, closed afterwards."""
    del clis
    driver = open_agent(SPECS[HarnessKind.CODEX])
    yield driver
    await driver.close()


async def _open(
    driver: HarnessDriver,
    placement: Placement,
    hooks: HookTable | None = None,
    permission: Permission | None = None,
) -> HarnessSession:
    return await driver.open(
        placement,
        permission=permission or Permission(),
        skills=(),
        hooks=hooks or HookTable(),
    )


# ------------------------------------------------------------------------------ the contract


@pytest.mark.parametrize("harness", sorted(SPECS), ids=str)
async def test_every_stand_in_keeps_the_driver_contract(
    clis: Logs, work: Placement, harness: HarnessKind
) -> None:
    del clis
    await check_agent_driver(
        open_agent(SPECS[harness]), work, slow_prompt="slow, please", settle=0.5
    )


async def test_a_priced_model_reports_what_it_cost(
    claude: HarnessDriver, work: Placement, priced: str
) -> None:
    del priced
    handle = await _open(claude, work)
    sink = RecordingSink()
    await handle.turn(TurnRequest("Reply with the single word: ok"), sink)
    assert sink.cost > 0
    assert handle.usage.cost == pytest.approx(sink.cost)
    assert handle.usage.output_tokens == sink.output_tokens > 0


# --------------------------------------------------------------------------------- the hooks


async def test_moments_around_a_turn_reach_their_hooks_on_the_loop(
    claude: HarnessDriver, work: Placement, clis: Logs
) -> None:
    hooks = HookTable()
    started = _hears(
        hooks, HookKind.SESSION_START, SessionStartHookResult(context="be brief")
    )
    submitted = _hears(
        hooks, HookKind.USER_PROMPT_SUBMIT, UserPromptSubmitHookResult(context="thanks")
    )
    ended = _hears(hooks, HookKind.SESSION_END, SessionEndHookResult())
    handle = await _open(claude, work, hooks)
    said = await handle.turn(
        TurnRequest("Reply with the single word: ok"), RecordingSink()
    )
    assert said == "ok"
    await handle.turn(TurnRequest("Reply with the single word: two"), RecordingSink())
    assert started == [{}]
    assert [one["prompt"] for one in submitted] == [
        "Reply with the single word: ok",
        "Reply with the single word: two",
    ]
    told = [one["said"] for one in clis.of("claude") if "said" in one]
    assert told[0] == "be brief\n\nReply with the single word: ok\n\nthanks"
    assert told[1] == "Reply with the single word: two\n\nthanks"
    await handle.close()
    assert ended == [{}]


async def test_a_blocked_prompt_is_refused_without_a_turn(
    claude: HarnessDriver, work: Placement, clis: Logs
) -> None:
    hooks = HookTable()
    _hears(
        hooks,
        HookKind.USER_PROMPT_SUBMIT,
        UserPromptSubmitHookResult(block=True, reason="not today"),
    )
    handle = await _open(claude, work, hooks)
    with pytest.raises(SessionError, match="not today"):
        await handle.turn(TurnRequest("anything"), RecordingSink())
    assert clis.of("claude") == []


async def test_a_stop_hook_sends_the_agent_on_until_it_lets_it_stop(
    claude: HarnessDriver, work: Placement
) -> None:
    hooks = HookTable()
    stops: list[dict[str, Any]] = []

    async def keep_going(handle: SessionHandle, fields: dict[str, Any]) -> HookResult:
        del handle
        stops.append(fields)
        if fields["again"] < 2:
            return StopHookResult(block=True, reason="Reply with the single word: more")
        return StopHookResult()

    hooks.set(HookKind.STOP, keep_going)
    handle = await _open(claude, work, hooks)
    said = await handle.turn(
        TurnRequest("Reply with the single word: first"), RecordingSink()
    )
    assert said == "more"
    assert [(one["said"], one["again"]) for one in stops] == [
        ("first", 0),
        ("more", 1),
        ("more", 2),
    ]


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (PermissionRequestHookResult(), "allowed"),
        (
            PermissionRequestHookResult(allow=False, reason="no shell"),
            "denied: no shell",
        ),
    ],
)
async def test_claude_asks_a_permission_hook_and_does_what_it_says(
    claude: HarnessDriver,
    work: Placement,
    answer: PermissionRequestHookResult,
    said: str,
) -> None:
    hooks = HookTable()
    heard = _hears(hooks, HookKind.PERMISSION_REQUEST, answer)
    handle = await _open(claude, work, hooks)
    assert await handle.turn(TurnRequest("use a tool"), RecordingSink()) == said
    assert heard == [{"tool": "Bash", "input": {"command": "echo hi"}}]


async def test_with_no_permission_hook_every_request_is_approved(
    claude: HarnessDriver, work: Placement, clis: Logs
) -> None:
    handle = await _open(claude, work)
    assert await handle.turn(TurnRequest("use a tool"), RecordingSink()) == "allowed"
    argv = clis.of("claude")[0]["argv"]
    assert argv[argv.index("--permission-mode") + 1] == "manual"
    assert "--permission-prompt-tool" in argv


async def test_a_pre_tool_use_hook_gates_the_tool_before_it_runs(
    claude: HarnessDriver, work: Placement
) -> None:
    hooks = HookTable()
    heard = _hears(
        hooks,
        HookKind.PRE_TOOL_USE,
        PreToolUseHookResult(block=True, reason="not that"),
    )
    handle = await _open(claude, work, hooks)
    assert await handle.turn(TurnRequest("use a tool"), RecordingSink()) == (
        "blocked: not that"
    )
    assert heard == [{"tool": "Bash", "input": {"command": "echo hi"}}]


async def test_a_pre_tool_use_hook_hung_later_takes_hold_from_the_next_turn(
    claude: HarnessDriver, work: Placement
) -> None:
    hooks = HookTable()
    handle = await _open(claude, work, hooks)
    assert await handle.turn(TurnRequest("use a tool"), RecordingSink()) == "allowed"
    _hears(hooks, HookKind.PRE_TOOL_USE, PreToolUseHookResult(block=True, reason="no"))
    assert (
        await handle.turn(TurnRequest("use a tool"), RecordingSink()) == "blocked: no"
    )


async def test_a_question_goes_to_the_ask_user_hook_and_notification(
    claude: HarnessDriver, work: Placement
) -> None:
    hooks = HookTable()
    asked = _hears(hooks, HookKind.ASK_USER, AskUserHookResult(answer="left"))
    told = _hears(hooks, HookKind.NOTIFICATION, NotificationHookResult())
    handle = await _open(claude, work, hooks)
    assert await handle.turn(TurnRequest("ask me"), RecordingSink()) == "left"
    assert asked == [{"question": "Which way?", "options": ("left", "right")}]
    assert told == [{"message": "Which way?"}]


async def test_with_no_ask_user_hook_the_question_goes_unanswered(
    claude: HarnessDriver, work: Placement
) -> None:
    handle = await _open(claude, work)
    assert await handle.turn(TurnRequest("ask me"), RecordingSink()) == "nobody"


async def test_subagents_starting_and_stopping_reach_their_hooks(
    claude: HarnessDriver, work: Placement
) -> None:
    hooks = HookTable()
    starts = _hears(hooks, HookKind.SUBAGENT_START, SubagentStartHookResult())
    stops = _hears(hooks, HookKind.SUBAGENT_STOP, SubagentStopHookResult())
    handle = await _open(claude, work, hooks)
    assert await handle.turn(TurnRequest("delegate"), RecordingSink()) == "delegated"
    assert [one["subagent"] for one in starts] == ["Task"]
    assert [one["subagent"] for one in stops] == ["Task"]


async def test_codex_asks_permission_only_while_a_hook_is_hung_on_it(
    codex: HarnessDriver, work: Placement, clis: Logs
) -> None:
    hooks = HookTable()
    handle = await _open(codex, work, hooks)
    assert await handle.turn(
        TurnRequest("Reply with the single word: a"), RecordingSink()
    )
    heard = _hears(
        hooks,
        HookKind.PERMISSION_REQUEST,
        PermissionRequestHookResult(allow=False, reason="not in this repo"),
    )
    assert await handle.turn(TurnRequest("use a tool"), RecordingSink()) == "denied"
    hooks.set(HookKind.PERMISSION_REQUEST, None)
    await handle.turn(TurnRequest("use a tool"), RecordingSink())
    said = clis.of("codex")
    started = [one["params"] for one in said if one.get("method") == "turn/start"]
    # Every command asked about only while the hook is hung, and never by a model.
    assert [one["approvalPolicy"] for one in started] == ["never", "untrusted", "never"]
    assert [one["tool"] for one in heard] == ["commandExecution"]
    # Codex takes a refusal with no reason, so the reason reaches the model as a steer.
    steered = [
        one["params"]["input"][0]["text"]
        for one in said
        if one.get("method") == "turn/steer"
    ]
    assert steered == ["Using commandExecution was refused: not in this repo"]


async def test_a_hook_that_never_answers_is_given_up_on_and_the_tool_allowed(
    clis: Logs, work: Placement, monkeypatch: pytest.MonkeyPatch
) -> None:
    del clis
    monkeypatch.setattr(harnesses, "HOOK_TIMEOUT", 0.5)
    stuck = asyncio.Event()

    async def never(handle: SessionHandle, fields: dict[str, Any]) -> HookResult:
        del handle, fields
        await stuck.wait()
        return PermissionRequestHookResult(allow=False)

    for harness in (HarnessKind.CLAUDE, HarnessKind.CODEX):
        hooks = HookTable()
        hooks.set(HookKind.PERMISSION_REQUEST, never)
        driver = open_agent(SPECS[harness])
        try:
            handle = await _open(driver, work, hooks)
            said = await asyncio.wait_for(
                handle.turn(TurnRequest("use a tool"), RecordingSink()), 30
            )
        finally:
            await driver.close()
        assert said == "allowed", harness


async def test_codex_is_started_able_to_ask_once_an_ask_user_hook_is_hung(
    codex: HarnessDriver, work: Placement, clis: Logs
) -> None:
    hooks = HookTable()
    handle = await _open(codex, work, hooks)
    assert await handle.turn(TurnRequest("ask me"), RecordingSink()) == "nobody"
    _hears(hooks, HookKind.ASK_USER, AskUserHookResult(answer="right"))
    assert await handle.turn(TurnRequest("ask me"), RecordingSink()) == "right"
    said = clis.of("codex")
    started = [one["argv"] for one in said if "argv" in one]
    assert len(started) == 2
    assert "default_mode_request_user_input" not in started[0]
    assert started[1][started[1].index("--enable") + 1] == (
        "default_mode_request_user_input"
    )
    # Started again between two turns, with nothing in flight, and the conversation picked
    # back up on the new server rather than begun again.
    threads = {
        one["params"]["threadId"] for one in said if one.get("method") == "turn/start"
    }
    resumed = [
        one["params"]["threadId"]
        for one in said
        if one.get("method") == "thread/resume"
    ]
    assert len(threads) == 1
    assert resumed == list(threads)


# ------------------------------------------------------------------------ steering and goals


@pytest.mark.parametrize("harness", [HarnessKind.CLAUDE, HarnessKind.CODEX], ids=str)
async def test_a_queued_steer_is_taken_into_the_turn_in_flight(
    clis: Logs, work: Placement, harness: HarnessKind
) -> None:
    del clis
    driver = open_agent(SPECS[harness])
    try:
        handle = await _open(driver, work)
        turning = asyncio.create_task(
            handle.turn(TurnRequest("slow, please"), RecordingSink())
        )
        await asyncio.sleep(0.5)
        await handle.steer("Reply with the single word: turned", queued=True)
        assert await asyncio.wait_for(turning, 30) == "turned"
    finally:
        await driver.close()


@pytest.mark.parametrize("harness", [HarnessKind.CLAUDE, HarnessKind.CODEX], ids=str)
async def test_a_goal_is_the_harness_own(
    clis: Logs, work: Placement, harness: HarnessKind
) -> None:
    driver = open_agent(SPECS[harness])
    try:
        handle = await _open(driver, work)
        said = await handle.turn(
            TurnRequest("/goal Reply with the single word: done"), RecordingSink()
        )
    finally:
        await driver.close()
    if harness is HarnessKind.CLAUDE:
        assert said == "goal met: Reply with the single word: done"
    else:
        assert said == "done"
        goals = [
            one for one in clis.of("codex") if one.get("method") == "thread/goal/set"
        ]
        assert [one["params"]["objective"] for one in goals] == [
            "Reply with the single word: done"
        ]


async def test_a_session_that_cannot_steer_says_so(clis: Logs, work: Placement) -> None:
    del clis
    driver = open_agent(SPECS[HarnessKind.OPENCODE])
    try:
        handle = await _open(driver, work)
        with pytest.raises(UnsupportedOperation):
            await handle.steer("hello", queued=True)
    finally:
        await driver.close()


# ------------------------------------------------------------------------------------ forks


@pytest.mark.parametrize("harness", [HarnessKind.CLAUDE, HarnessKind.CODEX], ids=str)
async def test_a_fork_carries_on_in_another_workdir(
    clis: Logs, tmp_path: Path, harness: HarnessKind
) -> None:
    driver = open_agent(SPECS[harness])
    here, there = _placement(tmp_path / "here"), _placement(tmp_path / "there")
    try:
        parent = await _open(driver, here)
        await parent.turn(
            TurnRequest("Reply with the single word: one"), RecordingSink()
        )
        child = await driver.open(
            there,
            permission=Permission(),
            skills=(),
            hooks=HookTable(),
            fork_of=parent,
        )
        said = await child.turn(
            TurnRequest("Reply with the single word: two"), RecordingSink()
        )
        assert said == "two"
        assert child.id not in (None, parent.id)
    finally:
        await driver.close()
    if harness is HarnessKind.CLAUDE:
        started = [one for one in clis.of("claude") if "argv" in one]
        assert started[-1]["cwd"] == str(there.workdir)
        assert "--fork-session" in started[-1]["argv"]
    else:
        forked = [one for one in clis.of("codex") if one.get("method") == "thread/fork"]
        assert [one["params"]["cwd"] for one in forked] == [str(there.workdir)]


async def test_a_harness_that_forks_only_where_it_is_refuses_another_workdir(
    clis: Logs, tmp_path: Path
) -> None:
    del clis
    driver = open_agent(SPECS[HarnessKind.OPENCODE])
    try:
        parent = await _open(driver, _placement(tmp_path / "here"))
        await parent.turn(
            TurnRequest("Reply with the single word: one"), RecordingSink()
        )
        with pytest.raises(UnsupportedOperation):
            await driver.open(
                _placement(tmp_path / "there"),
                permission=Permission(),
                skills=(),
                hooks=HookTable(),
                fork_of=parent,
            )
    finally:
        await driver.close()


async def test_a_second_fork_elsewhere_carries_the_conversation_as_it_is_now(
    claude: HarnessDriver, tmp_path: Path
) -> None:
    here = _placement(tmp_path / "here")
    parent = await _open(claude, here)
    await parent.turn(TurnRequest("Reply with the single word: one"), RecordingSink())
    await claude.open(
        _placement(tmp_path / "b"),
        permission=Permission(),
        skills=(),
        hooks=HookTable(),
        fork_of=parent,
    )
    await parent.turn(TurnRequest("Reply with the single word: two"), RecordingSink())
    later = await claude.open(
        _placement(tmp_path / "c"),
        permission=Permission(),
        skills=(),
        hooks=HookTable(),
        fork_of=parent,
    )
    await later.turn(TurnRequest("Reply with the single word: three"), RecordingSink())
    projects = tmp_path / "claude-home" / "projects"
    (carried,) = projects.glob(f"*c/{later.id}.jsonl")
    said = [json.loads(line)["user"] for line in carried.read_text().splitlines()]
    assert said == [
        "Reply with the single word: one",
        "Reply with the single word: two",
        "Reply with the single word: three",
    ]


async def test_codex_counts_a_thread_picked_up_on_a_new_server_from_where_it_was(
    codex: HarnessDriver, work: Placement
) -> None:
    handle = await _open(codex, work)
    sink = RecordingSink()
    await handle.turn(TurnRequest("Reply with the single word: one"), sink)
    turning = asyncio.create_task(handle.turn(TurnRequest("slow, please"), sink))
    await asyncio.sleep(0.5)
    handle.interrupt()
    with pytest.raises(SessionError):
        await turning
    before = handle.usage.output_tokens
    # The interrupt put the server down, so this is the thread picked up on a new one, whose
    # first word states the thread's whole total: only what this turn cost is counted.
    await handle.turn(TurnRequest("Reply with the single word: two"), sink)
    assert handle.usage.output_tokens - before == 2


async def test_a_session_with_no_turn_has_nothing_to_fork(
    claude: HarnessDriver, work: Placement
) -> None:
    parent = await _open(claude, work)
    with pytest.raises(SessionError):
        await claude.open(
            work, permission=Permission(), skills=(), hooks=HookTable(), fork_of=parent
        )


async def test_a_fork_is_refused_once_its_parent_has_moved_on(
    claude: HarnessDriver, work: Placement
) -> None:
    parent = await _open(claude, work)
    await parent.turn(TurnRequest("Reply with the single word: one"), RecordingSink())
    child = await claude.open(
        work, permission=Permission(), skills=(), hooks=HookTable(), fork_of=parent
    )
    await parent.turn(TurnRequest("Reply with the single word: two"), RecordingSink())
    with pytest.raises(SessionError):
        await child.turn(
            TurnRequest("Reply with the single word: three"), RecordingSink()
        )


# ------------------------------------------------------------------------ schemas and limits


class Counted(pydantic.BaseModel):
    """A shape the stand-ins never answer in."""

    number: int


async def test_an_answer_not_in_the_shape_is_an_output_schema_error(
    claude: HarnessDriver, work: Placement
) -> None:
    handle = await _open(claude, work)
    with pytest.raises(OutputSchemaError) as raised:
        await handle.turn(TurnRequest("count", Counted), RecordingSink())
    assert isinstance(raised.value, ValueError)


async def test_a_turn_past_its_output_tokens_is_stopped_and_raises(
    claude: HarnessDriver, work: Placement, clis: Logs
) -> None:
    handle = await _open(claude, work)
    sink = RecordingSink()
    with pytest.raises(OutputTokensExceeded):
        await handle.turn(
            TurnRequest("slow, please", limits=Limits(output_tokens=5, graceful=False)),
            sink,
        )
    assert sink.output_tokens >= 5
    said = await handle.turn(TurnRequest("Reply with the single word: next"), sink)
    assert said == "next"
    assert len([one for one in clis.of("claude") if "argv" in one]) == 2


@pytest.mark.parametrize(
    "limits",
    [
        Limits(output_tokens=1, graceful=True),
        Limits(cost=1e-9, graceful=True),
        Limits(deadline=time.monotonic() + 3600, graceful=True),
    ],
)
async def test_a_graceful_turn_runs_to_its_end_whatever_it_spends(
    claude: HarnessDriver, work: Placement, priced: str, limits: Limits
) -> None:
    del priced
    handle = await _open(claude, work)
    sink = RecordingSink()
    said = await handle.turn(
        TurnRequest("Reply with the single word: finished", limits=limits), sink
    )
    assert said == "finished"
    assert sink.output_tokens > 1


async def test_a_graceful_deadline_lets_the_turn_finish_past_it(
    codex: HarnessDriver, work: Placement
) -> None:
    handle = await _open(codex, work)
    turning = asyncio.create_task(
        handle.turn(
            TurnRequest(
                "slow, please",
                limits=Limits(deadline=time.monotonic() + 0.3, graceful=True),
            ),
            RecordingSink(),
        )
    )
    await asyncio.sleep(1.0)
    assert not turning.done(), "a graceful turn was stopped at its deadline"
    await handle.steer("Reply with the single word: late", queued=True)
    assert await asyncio.wait_for(turning, 30) == "late"


async def test_a_turn_past_its_deadline_is_stopped_and_raises(
    codex: HarnessDriver, work: Placement
) -> None:
    handle = await _open(codex, work)
    with pytest.raises(DurationExceeded) as raised:
        await handle.turn(
            TurnRequest(
                "slow, please",
                limits=Limits(deadline=time.monotonic() + 0.5, graceful=False),
            ),
            RecordingSink(),
        )
    assert isinstance(raised.value, TimeoutError)


async def test_a_turn_past_its_cost_is_stopped_and_raises(
    claude: HarnessDriver, work: Placement, priced: str
) -> None:
    del priced
    handle = await _open(claude, work)
    with pytest.raises(CostExceeded):
        await handle.turn(
            TurnRequest("slow, please", limits=Limits(cost=1e-5, graceful=False)),
            RecordingSink(),
        )


async def test_a_turn_with_nothing_left_to_spend_starts_nothing(
    claude: HarnessDriver, work: Placement, clis: Logs
) -> None:
    handle = await _open(claude, work)
    with pytest.raises(OutputTokensExceeded):
        await handle.turn(
            TurnRequest("anything", limits=Limits(output_tokens=0)), RecordingSink()
        )
    assert clis.of("claude") == []


# ----------------------------------------------------------------------------------- errors


@pytest.mark.parametrize(
    ("words", "leaf"),
    [
        ("401 Unauthorized: invalid api key", HarnessRefused),
        ("model not found", ModelUnavailable),
    ],
)
async def test_a_failed_turn_is_the_leaf_for_why(
    claude: HarnessDriver,
    work: Placement,
    words: str,
    leaf: type[Exception],
) -> None:
    handle = await _open(claude, work)
    with pytest.raises(leaf) as raised:
        await handle.turn(TurnRequest(f"fail: {words}"), RecordingSink())
    assert raised.value.__cause__ is not None


async def test_a_cli_that_is_not_installed_is_refused_at_open(
    work: Placement, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    driver = open_agent(SPECS[HarnessKind.CLAUDE])
    with pytest.raises(HarnessNotInstalled):
        await _open(driver, work)


async def test_a_read_only_session_runs_at_the_read_only_rung(
    claude: HarnessDriver, work: Placement, clis: Logs
) -> None:
    handle = await _open(
        claude,
        work,
        permission=Permission(local=PermissionKind.READ, user=PermissionKind.READ),
    )
    await handle.turn(TurnRequest("Reply with the single word: ok"), RecordingSink())
    argv = clis.of("claude")[0]["argv"]
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert argv[argv.index("--disallowedTools") + 1] == "WebSearch,WebFetch"


# ------------------------------------------------------------------------------ outworlder


class Choice(pydantic.BaseModel):
    """What an outworlder is asked to fill in."""

    way: str = pydantic.Field(description="Which way to go")
    far: int = 1


async def test_an_outworlder_answers_through_the_callback_it_was_given() -> None:
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        return "3" if question.text.startswith("far") else "north"

    outworlder = open_outworlder(ask=ask)
    assert not outworlder.away
    assert await outworlder.run("Where now?", None) == "north"
    chosen = await outworlder.run("Choose.", Choice)
    assert chosen == Choice(way="north", far=3)
    assert asked[0].text == "Where now?"


async def test_an_outworlder_nobody_answers_is_away() -> None:
    outworlder = open_outworlder(ask=lambda question: None)
    with pytest.raises(OutworlderAway):
        await outworlder.run("Anyone?", None)


async def test_an_away_outworlder_answers_what_it_can_by_default() -> None:
    outworlder = open_outworlder()
    assert outworlder.away
    assert await outworlder.run("Anyone?", None) == ""

    class Defaulted(pydantic.BaseModel):
        far: int = 2

    assert await outworlder.run("Anyone?", Defaulted) == Defaulted()
    with pytest.raises(OutworlderAway):
        await outworlder.run("Anyone?", Choice)
    here = open_outworlder(ask=lambda question: "x", away=lambda: True)
    assert here.away
    assert await here.run("Anyone?", None) == ""


async def test_a_session_carries_its_skills_where_its_cli_reads_them(
    claude: HarnessDriver, work: Placement, tmp_path: Path
) -> None:
    kept = tmp_path / "skills" / "tidy"
    kept.mkdir(parents=True)
    (kept / "SKILL.md").write_text(
        "---\nname: tidy\ndescription: Tidy up.\n---\nTidy.\n"
    )
    handle = await claude.open(
        work,
        permission=Permission(),
        skills=(Skill("tidy", kept),),
        hooks=HookTable(),
    )
    await handle.turn(TurnRequest("Reply with the single word: ok"), RecordingSink())
    mounted = Path(str(work.workdir)) / ".claude" / "skills" / "tidy" / "SKILL.md"
    assert mounted.read_text().endswith("Tidy.\n")
    await handle.close()
    assert not mounted.exists()
