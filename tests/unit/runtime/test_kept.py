"""An agent as it goes into a file and comes back out of one, and what a flow is set up with.

An agent is a CLI, an account, and a model at an effort: the word `-a` takes after its role,
and nothing else -- what it may do and where it works are the flow's to say. And what a
workspace remembers of a flow is what each of its roles was given, its params and its budget,
each left alone where it is not handed in again and erased where it is handed in empty.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.backends import AUTO
from hmz.coganchor.spelling import parted
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
        Runs("mcode/custom_provider:gateway/mock/first-model:auto", "loopback"),
        Runs("opencode/ollama/qwen3:latest:high"),
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
        "/m:high",
        "claude/:high",
    ],
)
def test_what_is_not_one_reads_back_as_nothing(held: object) -> None:
    assert read_back(held) is None


@pytest.mark.parametrize(
    ("held", "runs"),
    [
        ("claude/m", Runs("claude/m:auto")),
        ("claude/m:", Runs("claude/m:auto")),
        (
            "mcode@loopback/custom_provider:gateway/mock/first-model",
            Runs("mcode/custom_provider:gateway/mock/first-model:auto", "loopback"),
        ),
        ("opencode/ollama/qwen3:8b", Runs("opencode/ollama/qwen3:8b:auto")),
    ],
)
def test_one_written_with_no_effort_reads_back_at_none(held: str, runs: Runs) -> None:
    """A model's own `:` is the model's, and no effort is written `auto`, as a line writes it."""
    assert read_back(held) == runs
    assert AUTO == "auto"


@pytest.mark.parametrize(
    ("said", "model", "effort"),
    [
        ("m:high", "m", "high"),
        ("m", "m", ""),
        ("m:", "m", ""),
        ("custom_provider:gateway/m", "custom_provider:gateway/m", ""),
        ("custom_provider:gateway/m:max", "custom_provider:gateway/m", "max"),
        ("some:model:as configured", "some:model", "as configured"),
        ("qwen3:8b", "qwen3:8b", ""),
        ("llama3:q4_0", "llama3:q4_0", ""),
        # A word off every ladder is still an effort, refused as one, not a model's.
        ("opus:High", "opus", "High"),
        ("gpt-5:x_high", "gpt-5", "x_high"),
    ],
)
def test_an_effort_is_what_follows_the_last_colon_only_where_it_is_a_word(
    said: str, model: str, effort: str
) -> None:
    assert parted(said) == (model, effort)


def test_what_a_flow_was_set_up_with_is_read_back_by_role(tmp_path: Path) -> None:
    Settings(tmp_path).remember(
        "rlar",
        {"builder": Runs("claude/m:high"), "reviewer": Runs("codex/n:low", "work")},
        envs={"remote": "ssh@[box]/home/me/repo"},
        params={"rounds": 3},
        budget={"cost": 5.0},
    )

    held = Settings(tmp_path)
    assert held.flow == "rlar"
    assert held.agents("rlar") == {
        "builder": Runs("claude/m:high"),
        "reviewer": Runs("codex/n:low", "work"),
    }
    assert held.envs("rlar") == {"remote": "ssh@[box]/home/me/repo"}
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
        envs={"remote": "ssh@[box]/repo"},
        params={"rounds": 3},
        budget={"cost": 5.0},
    )

    settings.remember("rlar", {"builder": Runs("codex/n:low")})
    held = Settings(tmp_path)
    assert held.agents("rlar") == {"builder": Runs("codex/n:low")}
    assert held.envs("rlar") == {"remote": "ssh@[box]/repo"}
    assert held.params("rlar") == {"rounds": 3}
    assert held.budget("rlar") == {"cost": 5.0}

    settings.remember("rlar", {"builder": Runs("codex/n:low")}, params={}, budget={})
    held = Settings(tmp_path)
    assert held.params("rlar") == {}
    assert held.budget("rlar") == {}
    assert held.envs("rlar") == {"remote": "ssh@[box]/repo"}


def test_an_environment_kept_the_old_way_is_read_and_written_as_e_spells_it_now(
    tmp_path: Path,
) -> None:
    """Every workspace's, once, the first time the file is read; and nothing else of it."""
    import yaml

    from hmz import home
    from hmz.coganchor.machines import store
    from hmz.coganchor.machines.store import SSHRuntime

    store.add(SSHRuntime(name="gpu", host="10.0.0.2"))
    kept = {
        "workspaces": {
            str(tmp_path.resolve()): {
                "flow": "rlar",
                "flows": {
                    "rlar": {
                        "agents": {"builder": "claude/m:high"},
                        "envs": {
                            "here": "local@/srv/x",
                            "far": "ssh@me@box:2222/~/x",
                            "saved": "ssh@gpu/srv",
                            "box": "docker@local/srv",
                            "swarm": "swarm@local/srv",
                        },
                    }
                },
            },
            "/elsewhere": {"flows": {"chat": {"envs": {"a": "local@/a"}}}},
        },
        "enable_sentry": False,
    }
    file = home() / "settings.yaml"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(yaml.safe_dump(kept))

    now = {
        "here": "local/srv/x",
        "far": "ssh@[me@box:2222]/~/x",
        "saved": "ssh@gpu/srv",
        "box": "docker/srv",
        "swarm": "swarm/srv",
    }
    assert Settings(tmp_path).envs("rlar") == now
    written_down = yaml.safe_load(file.read_text())
    assert (
        written_down["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["envs"]
        == now
    )
    assert written_down["workspaces"]["/elsewhere"]["flows"]["chat"]["envs"] == {
        "a": "local/a"
    }
    assert written_down["enable_sentry"] is False


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
