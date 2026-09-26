"""An agent as it goes into a file and comes back out of one, and what a flow is set up with.

An agent is a CLI, an account, and a model at an effort: the word `-a` takes after its role,
and nothing else -- what it may do and where it works are the flow's to say. And what a
workspace remembers of a flow is what each of its roles was given, its params and its budget,
each left alone where it is not handed in again and erased where it is handed in empty.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.runtime.kept import Runs, read_back, written
from hmz.runtime.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


def test_an_agent_is_written_down_as_the_word_a_line_takes() -> None:
    assert written(Runs("claude/m:high")) == "claude/m:high"
    assert written(Runs("claude/m:high", "work")) == "claude@work/m:high"


@pytest.mark.parametrize(
    "runs",
    [
        Runs("claude/m:high"),
        Runs("claude/m:high", "work"),
        # A model's own punctuation stays the model's: read from both ends.
        Runs("opencode/openrouter/some:model:low"),
        Runs("codex/gpt-5.5:auto", "a@b"),
    ],
)
def test_an_agent_written_down_comes_back_as_itself(runs: Runs) -> None:
    assert read_back(written(runs)) == runs


@pytest.mark.parametrize(
    "held",
    [
        None,
        {"cli": "claude", "model": "m", "effort": "high"},  # a mapping, not a line
        "claude",
        "claude/m",
        "/m:high",
        "claude/:high",
    ],
)
def test_what_is_not_one_reads_back_as_nothing(held: object) -> None:
    assert read_back(held) is None


def test_what_a_flow_was_set_up_with_is_read_back_by_role(tmp_path: Path) -> None:
    Settings(tmp_path).remember(
        "rlar",
        {"builder": Runs("claude/m:high"), "reviewer": Runs("codex/n:low", "work")},
        envs={"remote": "ssh@box/home/me/repo"},
        params={"rounds": 3},
        budget={"cost": 5.0},
    )

    held = Settings(tmp_path)
    assert held.flow == "rlar"
    assert held.agents("rlar") == {
        "builder": Runs("claude/m:high"),
        "reviewer": Runs("codex/n:low", "work"),
    }
    assert held.envs("rlar") == {"remote": "ssh@box/home/me/repo"}
    assert held.params("rlar") == {"rounds": 3}
    assert held.budget("rlar") == {"cost": 5.0}
    assert held.agents("chat") == {}


def test_choosing_the_agents_again_leaves_the_rest_alone_and_empty_erases(
    tmp_path: Path,
) -> None:
    settings = Settings(tmp_path)
    settings.remember(
        "rlar",
        {"builder": Runs("claude/m:high")},
        envs={"remote": "ssh@box/repo"},
        params={"rounds": 3},
        budget={"cost": 5.0},
    )

    settings.remember("rlar", {"builder": Runs("codex/n:low")})
    held = Settings(tmp_path)
    assert held.agents("rlar") == {"builder": Runs("codex/n:low")}
    assert held.envs("rlar") == {"remote": "ssh@box/repo"}
    assert held.params("rlar") == {"rounds": 3}
    assert held.budget("rlar") == {"cost": 5.0}

    settings.remember("rlar", {"builder": Runs("codex/n:low")}, params={}, budget={})
    held = Settings(tmp_path)
    assert held.params("rlar") == {}
    assert held.budget("rlar") == {}
    assert held.envs("rlar") == {"remote": "ssh@box/repo"}


def test_what_humanize_did_not_write_reads_as_nothing_remembered(
    tmp_path: Path,
) -> None:
    """An agent written as a mapping of its fields is not one; neither is a numeric env."""
    import yaml

    from hmz import home

    at = home() / "settings.yaml"
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(
        yaml.safe_dump(
            {
                "workspaces": {
                    str(tmp_path.resolve()): {
                        "flow": "rlar",
                        "flows": {
                            "rlar": {
                                "agents": {
                                    "builder": {
                                        "cli": "claude",
                                        "model": "m",
                                        "effort": "high",
                                    }
                                },
                                "envs": {"remote": 3},
                            }
                        },
                    }
                }
            }
        )
    )

    held = Settings(tmp_path)
    assert held.flow == "rlar"
    assert held.agents("rlar") == {}
    assert held.envs("rlar") == {}
