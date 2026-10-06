"""Every harness installed here does one real coding task, start to finish, through `hmz exec`.

The task is the sample project's: write `median` and `mode` so that its tests pass. Each
harness runs it under the `ralph_loop` builtin on its cheapest model with a capped budget,
and the outcome is read off the workspace -- its tests pass and git sees what changed -- not
off anything the agent said.

A harness that is not installed, or whose account will not take a turn here, is skipped
saying why. `HMZ_SYSTEM_MODEL_<HARNESS>` (`HMZ_SYSTEM_MODEL_CURSOR_AGENT=auto`) swaps the
model a harness runs at, as `MODEL[:EFFORT]`, for when a vendor retires the one below.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.flows import HarnessKind
from tests.system.real import needs

if TYPE_CHECKING:
    from pathlib import Path

#: Each harness at the model it is cheapest to ask and the least effort it takes.
CHEAPEST: dict[HarnessKind, str] = {
    HarnessKind.CLAUDE: "claude-haiku-4-5-20251001:low",
    HarnessKind.CODEX: "gpt-5.5:low",
    HarnessKind.CURSOR_AGENT: "auto",
    HarnessKind.OPENCODE: "opencode/nemotron-3.5-lightning-free",
    HarnessKind.MIMO: "xiaomi/mimo-v2.5:low",
    HarnessKind.MCODE: "minimax/MiniMax-M2.7-highspeed",
    HarnessKind.QWEN: "qwen3-coder-flash:low",
    HarnessKind.KIMI: "kimi-code/k3",
    HarnessKind.GROK: "grok-4.7:low",
    HarnessKind.PI: "openai-codex/gpt-5.4-mini",
    HarnessKind.AGY: "gemini-3.8-flash-low:low",
    HarnessKind.DSH: "deepseek-v4-flash:off",
}

#: Why a harness cannot take this task at all, whatever is installed.
CANNOT = {
    HarnessKind.LITELLM: "litellm is a model called directly, with no tools to edit files",
    HarnessKind.ACP: "acp runs a CLI added by hand to settings; none is added in a test home",
}

#: What the run may spend: `ralph_loop` goes on until it is spent, so this is its length.
BUDGET = "budget.duration=600,budget.cost=2"

TASK = (
    "Implement `median` and `mode` in stats.py so that every test in tests/test_stats.py "
    "passes. Check with `python -m pytest`. Change nothing under tests/."
)

#: What `ralph_loop` prints for a round whose turn failed.
FAILED = re.compile(r"round \d+ failed: (.*)")


def _model(harness: HarnessKind) -> str:
    """The `MODEL[:EFFORT]` to run `harness` at, or a skip where it cannot run here."""
    if harness in CANNOT:
        pytest.skip(CANNOT[harness])
    if harness is HarnessKind.DSH:
        if importlib.util.find_spec("deepseek_harness") is None:
            pytest.skip("the DeepSeek Harness SDK is not installed here")
        if not os.environ.get("DEEPSEEK_API_KEY"):
            pytest.skip("DEEPSEEK_API_KEY is not set")
    else:
        needs(harness.value)
    override = f"HMZ_SYSTEM_MODEL_{harness.name}"
    return os.environ.get(override) or CHEAPEST[harness]


def _run(argv: list[str], at: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=at, capture_output=True, text=True, check=False)


@pytest.mark.timeout(1800)
@pytest.mark.parametrize(
    "harness",
    [
        pytest.param(one, marks=pytest.mark.xdist_group(one.value))
        for one in HarnessKind
    ],
    ids=str,
)
def test_the_harness_does_a_real_task(harness: HarnessKind, workspace: Path) -> None:
    model = _model(harness)
    start = _run(["git", "rev-parse", "HEAD"], workspace).stdout.strip()

    ran = _run(
        [
            *(sys.executable, "-m", "hmz", "exec", "-f", "ralph_loop"),
            *("-a", f"agent={harness}/{model}", "-p", BUDGET, TASK),
        ],
        workspace,
    )
    said = ran.stdout + ran.stderr
    assert ran.returncode == 0, said

    checked = _run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], workspace
    )
    if checked.returncode != 0:
        rounds = len(re.findall(r"^round \d+$", said, re.MULTILINE))
        failures = FAILED.findall(said)
        if rounds and len(failures) == rounds:
            pytest.skip(f"{harness} took no turn here at {model}: {failures[0]}")
    assert checked.returncode == 0, f"{checked.stdout}\n--- hmz exec said ---\n{said}"

    changed = _run(["git", "diff", "--name-only", start], workspace).stdout.split()
    assert "stats.py" in changed, changed
    assert not [one for one in changed if one.startswith("tests/")], changed
