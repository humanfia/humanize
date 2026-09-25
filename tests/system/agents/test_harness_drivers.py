"""The harness drivers against the real CLIs installed here, as the account signed in on them.

Each installed CLI is run through :func:`tests.flows.contracts.check_agent_driver` on its
cheapest model -- a plain turn, a schema turn, an interrupt, a cancel, a steer where it steers,
and a fork where it forks -- and then through what only the real thing can show: a `/goal`
where the harness has one, a fork into another workdir, a permission request and a question
reaching the flow's hooks.

A CLI that is installed but refuses the account -- signed out, a model it may not name -- is
skipped, saying so, rather than failed: that is the account's, and the stand-ins in
`tests/integration/flows/test_harness_drivers.py` hold the driver itself.

These cost tokens and need network access, so they only run with ``pytest --run-agents``.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import (
    AskUserHookResult,
    EnvBackendKind,
    HarnessError,
    HarnessKind,
    HookKind,
    HookResult,
    Permission,
    PermissionRequestHookAgentMixin,
    PermissionRequestHookResult,
    UnsupportedOperation,
)
from hmz.runtime.flowing.harnesses import open_agent
from hmz.runtime.flowing.specs import AgentSpec
from hmz.runtime.flowing.spi import (
    HARNESS_CAPABILITIES,
    HookTable,
    Placement,
    TurnRequest,
)
from tests.flows.contracts import RecordingSink, check_agent_driver

if TYPE_CHECKING:
    from hmz.runtime.flowing.harnesses import HarnessDriver
    from hmz.runtime.flowing.spi import SessionHandle

pytestmark = [pytest.mark.agent, pytest.mark.timeout(900)]

#: What each harness is run at: the model it is cheapest to ask, and the least effort it takes.
#: A harness whose CLI has said nothing about what it runs here is looked up in what it did
#: say, in `~/.humanize/models`.
CHEAPEST: dict[HarnessKind, tuple[str, str]] = {
    HarnessKind.CLAUDE: ("claude-haiku-4-5-20251001", "low"),
    HarnessKind.CODEX: ("gpt-5.5", "low"),
    HarnessKind.CURSOR_AGENT: ("auto", ""),
    HarnessKind.OPENCODE: ("opencode/nemotron-3.5-lightning-free", ""),
    HarnessKind.MIMO: ("xiaomi/mimo-v2.5", "low"),
    HarnessKind.QWEN: ("qwen3-coder-flash", "low"),
    HarnessKind.GROK: ("grok-4.5", "low"),
    HarnessKind.AGY: ("gemini-3.8-flash-low", "low"),
    HarnessKind.DSH: ("deepseek-v4-flash", "off"),
}

#: A prompt that keeps a turn going long enough to be interrupted, cancelled and steered.
SLOW = (
    "Count from 1 to 400, writing each number on its own line, and nothing else. Do not "
    "use any tools."
)

#: How long a real CLI is given to be under way before its turn is interrupted.
SETTLE = 4.0


def _model(harness: HarnessKind) -> tuple[str, str]:
    """The model and effort to run a harness at here, or a skip saying why there is none."""
    if harness in CHEAPEST:
        return CHEAPEST[harness]
    kept = Path.home() / ".humanize" / "models" / f"{harness.value}.json"
    try:
        said = json.loads(kept.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.skip(f"nothing has asked {harness} what it runs on this machine")
    models = cast(
        "list[dict[str, Any]]", cast("dict[str, Any]", said).get("models") or []
    )
    if not models:
        pytest.skip(f"{harness} has said nothing about what it runs on this machine")
    efforts = cast("list[str]", models[0].get("efforts") or [])
    return str(models[0]["name"]), efforts[-1] if efforts else ""


def _driver(harness: HarnessKind) -> HarnessDriver:
    """A driver of the real CLI, or a skip where it is not installed here."""
    if harness is HarnessKind.DSH:
        import importlib.util

        if importlib.util.find_spec("deepseek_harness") is None:
            pytest.skip("the DeepSeek Harness SDK is not installed here")
    elif shutil.which(harness.value) is None:
        pytest.skip(f"{harness} is not installed here")
    model, effort = _model(harness)
    return open_agent(AgentSpec("coder", harness, "", model, effort, harness.value))


def _placement(where: Path) -> Placement:
    where.mkdir(parents=True, exist_ok=True)
    return Placement(EnvBackendKind.LOCAL, "", PurePosixPath(str(where)))


async def _answers(driver: HarnessDriver, placement: Placement) -> None:
    """Skips a harness whose account will not take a turn here at all."""
    handle = await driver.open(
        placement, permission=Permission(), skills=(), hooks=HookTable()
    )
    try:
        await handle.turn(
            TurnRequest("Reply with the single word: ok"), RecordingSink()
        )
    except HarnessError as refused:
        await driver.close()
        pytest.skip(f"{driver.harness} will not take a turn here: {refused}")
    finally:
        await handle.close()


@pytest.mark.parametrize(
    "harness", [one for one in HarnessKind if one is not HarnessKind.ACP], ids=str
)
async def test_the_real_cli_keeps_the_driver_contract(
    harness: HarnessKind, tmp_path: Path
) -> None:
    driver = _driver(harness)
    placement = _placement(tmp_path / "work")
    await _answers(driver, placement)
    await check_agent_driver(driver, placement, slow_prompt=SLOW, settle=SETTLE)


@pytest.mark.parametrize(
    "harness",
    [HarnessKind.CLAUDE, HarnessKind.CODEX, HarnessKind.KIMI, HarnessKind.ZCODE],
    ids=str,
)
async def test_a_goal_is_met_through_the_harness_own_goal(
    harness: HarnessKind, tmp_path: Path
) -> None:
    driver = _driver(harness)
    placement = _placement(tmp_path / "work")
    await _answers(driver, placement)
    try:
        handle = await driver.open(
            placement, permission=Permission(), skills=(), hooks=HookTable()
        )
        done = tmp_path / "work" / "DONE.txt"
        said = await handle.turn(
            TurnRequest(f"/goal Create the file {done} whose only content is: done"),
            RecordingSink(),
        )
    finally:
        await driver.close()
    assert isinstance(said, str)
    assert done.read_text().strip() == "done"


@pytest.mark.parametrize(
    "harness",
    [HarnessKind.CLAUDE, HarnessKind.CODEX, HarnessKind.KIMI, HarnessKind.ZCODE],
    ids=str,
)
async def test_a_fork_carries_on_in_another_workdir(
    harness: HarnessKind, tmp_path: Path
) -> None:
    driver = _driver(harness)
    here, there = _placement(tmp_path / "here"), _placement(tmp_path / "there")
    await _answers(driver, here)
    word = uuid.uuid4().hex[:6]
    try:
        parent = await driver.open(
            here, permission=Permission(), skills=(), hooks=HookTable()
        )
        await parent.turn(
            TurnRequest(
                f"Remember the code word {word}. Reply with the single word: ok"
            ),
            RecordingSink(),
        )
        try:
            child = await driver.open(
                there,
                permission=Permission(),
                skills=(),
                hooks=HookTable(),
                fork_of=parent,
            )
        except UnsupportedOperation as refused:
            pytest.fail(f"{harness} is said to fork into another workdir: {refused}")
        said = await child.turn(
            TurnRequest(
                "What was the code word? Reply with it alone, then run `pwd` and reply "
                "with its output on a second line."
            ),
            RecordingSink(),
        )
    finally:
        await driver.close()
    assert isinstance(said, str)
    assert word in said
    assert str(there.workdir) in said


def _recording(table: HookTable, kind: HookKind, answer: HookResult) -> list[Any]:
    heard: list[Any] = []

    async def bound(handle: SessionHandle, fields: dict[str, Any]) -> HookResult:
        del handle
        heard.append(fields)
        return answer

    table.set(kind, bound)
    return heard


@pytest.mark.parametrize(
    "harness",
    [
        one
        for one in HarnessKind
        if PermissionRequestHookAgentMixin in HARNESS_CAPABILITIES[one]
    ],
    ids=str,
)
async def test_a_permission_request_reaches_the_hook_and_its_no_holds(
    harness: HarnessKind, tmp_path: Path
) -> None:
    driver = _driver(harness)
    placement = _placement(tmp_path / "work")
    await _answers(driver, placement)
    hooks = HookTable()
    heard = _recording(
        hooks,
        HookKind.PERMISSION_REQUEST,
        PermissionRequestHookResult(allow=False, reason="not allowed in this test"),
    )
    probe = Path.home() / f".hmz-harness-probe-{uuid.uuid4().hex[:8]}"
    try:
        handle = await driver.open(
            placement, permission=Permission(), skills=(), hooks=hooks
        )
        await handle.turn(
            TurnRequest(
                f"Use your shell tool to run exactly: touch {probe} -- and if you are not "
                "allowed to, reply with the single word: refused"
            ),
            RecordingSink(),
        )
    finally:
        await driver.close()
        existed = probe.exists()
        probe.unlink(missing_ok=True)
    assert heard, f"{harness} never asked the hook"
    assert not existed, "the tool ran although the hook refused it"


@pytest.mark.parametrize(
    "harness", [HarnessKind.CLAUDE, HarnessKind.CODEX, HarnessKind.KIMI], ids=str
)
async def test_a_question_reaches_the_ask_user_hook(
    harness: HarnessKind, tmp_path: Path
) -> None:
    driver = _driver(harness)
    placement = _placement(tmp_path / "work")
    await _answers(driver, placement)
    hooks = HookTable()
    heard = _recording(hooks, HookKind.ASK_USER, AskUserHookResult(answer="blue"))
    try:
        handle = await driver.open(
            placement, permission=Permission(), skills=(), hooks=hooks
        )
        said = await handle.turn(
            TurnRequest(
                "Use your tool for asking the user a question to ask me which colour I "
                "prefer, offering exactly the options red and blue. Then reply with just "
                "the colour I picked, one word."
            ),
            RecordingSink(),
        )
    finally:
        await driver.close()
    assert heard, f"{harness} never asked the user"
    assert isinstance(said, str)
    assert "blue" in said.lower()
