"""A run of a flow that never stops on its own, stopped by the budget it was given.

End to end and out of process: `hmz exec` on a flow whose loop has no exit of its own, under
a stand-in CLI, with the budget `-b` says. What is proved is the whole of what a budget is for
-- that the process exits rather than looping for a week, that the epic says the run was
stopped rather than done, and that each of the three dimensions does it on its own. The
engine's own tests prove the reckoning; only this can prove the loop actually ends. And a run
given no budget at all is not started: `-b` is required, so there is no run nothing will stop.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

#: How long one round of the stand-in CLI takes, and what it says it cost. Slow enough that a
#: budget in hours can be spelled without the test taking one, and dear enough that a budget
#: in tokens is reached in a handful of rounds.
PAUSE = 0.05
EACH = 4000

#: An `opencode run` that answers every prompt the same way and says what the answer cost, so
#: that a loop under it spends a known amount per round. Chosen for being the shortest of the
#: backends to stand in for: one command a turn, and the whole turn on stdout.
_OPENCODE = f"""
import json, sys, time

said = sys.stdin.read()
print(json.dumps({{"type": "text", "sessionID": "ses_one",
                  "part": {{"id": "prt_1", "type": "text", "text": "ok"}}}}), flush=True)
print(json.dumps({{"type": "step_finish", "sessionID": "ses_one",
                  "part": {{"id": "stp_1", "type": "step-finish",
                           "tokens": {{"input": 1, "output": {EACH}, "reasoning": 0,
                                      "cache": {{"read": 0, "write": 0}}}}}}}}), flush=True)
time.sleep({PAUSE})
"""

#: A flow whose loop has no way out at all. Every exit it could have had is deliberately
#: absent, so that anything which ends this run is the run's allowance and nothing else.
FOREVER = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def forever(task, *, agents, envs, params, ctx):
    session = await agents["worker"].spawn(env=envs["here"])
    at = 0
    while True:
        at += 1
        said = await agents["worker"].run(task, session=session)
        print(f"round {at}: {said}", flush=True)
"""


@pytest.fixture
def stand_in(tmp_path: Path) -> dict[str, str]:
    """The environment a run of this gets: a stand-in CLI, and a home of its own."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "opencode"
    fake.write_text(f"#!{sys.executable}\n{_OPENCODE}")
    fake.chmod(0o755)
    flows = tmp_path / "flows" / "forever"
    flows.mkdir(parents=True)
    (flows / "__init__.py").write_text(FOREVER, encoding="utf-8")
    # One model, priced, put straight where a fetch would have left it: what a token costs is
    # somebody else's list, and a suite must never go and ask them for it. `m` at five dollars
    # a million out makes one round of the stand-in worth a known amount of money.
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "prices.json").write_text(
        json.dumps(
            {
                "models": {
                    "m": {
                        "provider": "nobody",
                        "per_million": {"input": 1, "output": 5},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return {
        **os.environ,
        "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
        "HUMANIZE_HOME": str(home),
        # The list is already here, so nothing fetches one, and nothing here reports.
        "HUMANIZE_PRICES": "off",
        "HUMANIZE_TELEMETRY": "off",
    }


def _ran(
    tmp_path: Path,
    said: dict[str, str],
    budget: str,
    *,
    model: str = "m",
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    """One `hmz exec` of the endless flow, under the budget `-b` says.

    Args:
      tmp_path: Where the flow goes.
      said: The environment, out of the `stand_in` fixture.
      budget: What `-b` says the run may spend, or "" for no `-b` at all.
      model: What the stand-in CLI is told to run -- `m`, which the list beside it prices,
        unless a test wants one nobody prices.
      timeout: How long to give it before it is killed, for a run that never ends.

    Returns:
      What the process did.
    """
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "hmz",
            "exec",
            "-f",
            str(tmp_path / "flows" / "forever"),
            "-a",
            f"worker=opencode/{model}:high",
            *(["-b", budget] if budget else []),
            "go",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=said,
        timeout=timeout,
    )


def _how(said: dict[str, str]) -> list[str]:
    """How every run written down under this home ended, oldest first."""
    from hmz.runtime.epic import JOURNAL

    epics = sorted((Path(said["HUMANIZE_HOME"]) / "epics").rglob(JOURNAL))
    ended: list[str] = []
    for at in epics:
        for line in at.read_text(encoding="utf-8").splitlines():
            held = json.loads(line)
            if held.get("event") == "ended":
                ended.append(str(held.get("how")))
    return ended


@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    ("budget", "why"),
    [
        # A twentieth of a second, which a loop of fifty-millisecond rounds reaches at once.
        ("duration=0.05", "duration"),
        # Two rounds' worth of output tokens.
        (f"output_tokens={2 * EACH}", "output tokens"),
        # And two rounds' worth of money, at the five dollars a million the list above says.
        (f"cost={2 * EACH * 5 / 1_000_000}", "cost"),
    ],
)
def test_a_loop_with_no_exit_of_its_own_is_stopped_by_its_budget(
    tmp_path: Path, stand_in: dict[str, str], budget: str, why: str
) -> None:
    """The whole of what this is for: a flow that would otherwise run until somebody killed it.

    Out of process on purpose. A loop that ends because a unit test asserted it would is not
    the same claim as a loop whose process exits.
    """
    ran = _ran(tmp_path, stand_in, budget)

    assert ran.returncode == 0, ran.stderr
    assert "hmz exec: stopped --" in ran.stderr
    assert why in ran.stderr, ran.stderr
    # And the run is written down as stopped rather than as having finished what it set out
    # to do, because a run that ran out of money did not do what it was asked.
    assert _how(stand_in) == ["stopped"]


@pytest.mark.timeout(120)
def test_a_run_given_no_budget_is_not_started(
    tmp_path: Path, stand_in: dict[str, str]
) -> None:
    """A line with no `-b` is a line to correct, before any agent has taken a turn."""
    ran = _ran(tmp_path, stand_in, "")

    assert ran.returncode == 2
    assert "is given a budget" in ran.stderr
    assert _how(stand_in) == []  # nothing ran at all


@pytest.mark.timeout(300)
def test_a_cap_nothing_can_price_is_said_and_the_run_goes_on_anyway(
    tmp_path: Path, stand_in: dict[str, str]
) -> None:
    """Fifty dollars on a model nobody lists, which is the run a benchmark actually made.

    Bounded on the line and unbounded on the machine: nothing here can price the money, so
    the cap cannot stop the run. A command line has nobody to ask, so it says so -- and goes.
    That it goes is the other half of the claim: a cell in a container must not sit waiting
    on a question, so the rounds have to be on stdout by the time it is killed.
    """
    with pytest.raises(subprocess.TimeoutExpired) as went_on:
        _ran(tmp_path, stand_in, "cost=50", model="nobody-lists-this", timeout=10.0)

    said = (went_on.value.stderr or b"").decode(errors="replace")

    assert "nobody lists a price for nobody-lists-this" in said
    assert "round 1" in (went_on.value.stdout or b"").decode(errors="replace")


@pytest.mark.timeout(120)
@pytest.mark.parametrize("budget", ["25", "cost=-1", "tokens=5", "duration=soon"])
def test_a_budget_that_cannot_be_read_stops_the_line_before_anything_runs(
    tmp_path: Path, stand_in: dict[str, str], budget: str
) -> None:
    """A bare number says nothing about which of the three it meant; the rest are typos."""
    ran = _ran(tmp_path, stand_in, budget)

    assert ran.returncode == 2
    assert "-b" in ran.stderr
    assert _how(stand_in) == []  # nothing ran at all
