"""What a workspace was set up to run, and the settings that hold everywhere."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import yaml

from hmz.coganchor.machines import store as machines
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from tests.unit.runtime import doubles_u12 as doubles

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> doubles.Store:
    return doubles.store(monkeypatch)


def _respelled(spec: str) -> str:
    """An environment kept the old way, as `-e` spells it now."""
    return spec.replace("@local", "")


def _entry(held: doubles.Store, workspace: Path) -> dict[str, Any]:
    return held.held["workspaces"][str(workspace.resolve())]


def test_a_workspace_nothing_was_run_in_remembers_nothing(
    held: doubles.Store, tmp_path: Path
) -> None:
    said = Settings(tmp_path)

    assert said.flow == ""
    assert said.agents("ralph") == {}
    assert said.envs("ralph") == {}
    assert said.params("ralph") == {}
    assert said.budget("ralph") == {}
    assert said.profile("ralph") is False
    assert said.flows() == {}
    # Reading writes nothing.
    assert held.writes == 0


def test_what_was_remembered_reads_back_in_another_reading(
    held: doubles.Store, tmp_path: Path
) -> None:
    Settings(tmp_path).remember(
        "ralph",
        {"builder": Runs("claude/opus:high", "work"), "reviewer": Runs("codex/o3:low")},
        envs={"box": "docker/srv"},
        params={"rounds": 3},
        budget={"cost": 5.0},
        profile=True,
    )

    again = Settings(tmp_path)
    assert again.flow == "ralph"
    assert again.agents("ralph") == {
        "builder": Runs("claude/opus:high", "work"),
        "reviewer": Runs("codex/o3:low"),
    }
    assert list(again.agents("ralph")) == ["builder", "reviewer"]
    assert again.envs("ralph") == {"box": "docker/srv"}
    assert again.params("ralph") == {"rounds": 3}
    assert again.budget("ralph") == {"cost": 5.0}
    assert again.profile("ralph") is True
    assert set(again.flows()) == {"ralph"}
    assert _entry(held, tmp_path)["flows"]["ralph"]["agents"] == {
        "builder": "claude@work/opus:high",
        "reviewer": "codex/o3:low",
    }


def test_choosing_agents_again_keeps_what_else_was_kept(
    held: doubles.Store, tmp_path: Path
) -> None:
    Settings(tmp_path).remember(
        "ralph",
        {"builder": Runs("claude/opus:high")},
        envs={"box": "local/x"},
        params={"rounds": 3},
        budget={"cost": 1.0},
        profile=True,
    )

    Settings(tmp_path).remember("ralph", {"builder": Runs("codex/o3:low")})

    again = Settings(tmp_path)
    assert again.agents("ralph") == {"builder": Runs("codex/o3:low")}
    assert again.envs("ralph") == {"box": "local/x"}
    assert again.params("ralph") == {"rounds": 3}
    assert again.budget("ralph") == {"cost": 1.0}
    assert again.profile("ralph") is True


def test_what_another_writer_set_meanwhile_is_kept_rather_than_written_over(
    held: doubles.Store, tmp_path: Path
) -> None:
    mine = Settings(tmp_path)
    Settings(tmp_path).remember("ralph", {}, params={"rounds": 9})

    mine.remember("ralph", {"builder": Runs("claude/opus:high")})

    assert Settings(tmp_path).params("ralph") == {"rounds": 9}


def test_an_empty_value_or_profile_off_erases_it(
    held: doubles.Store, tmp_path: Path
) -> None:
    Settings(tmp_path).remember(
        "ralph", {}, envs={"box": "local/x"}, budget={"cost": 1.0}, profile=True
    )

    Settings(tmp_path).remember("ralph", {}, envs={}, budget={}, profile=False)

    again = Settings(tmp_path)
    assert again.envs("ralph") == {}
    assert again.budget("ralph") == {}
    assert again.profile("ralph") is False
    assert set(_entry(held, tmp_path)["flows"]["ralph"]) == {"agents"}


def test_each_flow_and_each_workspace_is_remembered_apart(
    held: doubles.Store, tmp_path: Path
) -> None:
    one, other = tmp_path / "one", tmp_path / "other"
    one.mkdir()
    other.mkdir()
    Settings(one).remember("ralph", {"builder": Runs("claude/opus:high")})
    Settings(one).remember("chat", {"assistant": Runs("codex/o3:low")})
    Settings(other).remember("aot", {})

    assert Settings(one).flow == "chat"
    assert set(Settings(one).flows()) == {"ralph", "chat"}
    assert Settings(one).agents("ralph") == {"builder": Runs("claude/opus:high")}
    assert Settings(other).flow == "aot"
    assert Settings(other).agents("ralph") == {}


def test_a_workspace_is_this_directory_unless_named(
    held: doubles.Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Settings().remember("ralph", {})

    assert Settings(tmp_path).flow == "ralph"


def test_an_agent_written_by_hand_wrong_forgets_the_flows_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    where = str(tmp_path.resolve())
    doubles.store(
        monkeypatch,
        {
            "workspaces": {
                where: {
                    "flows": {
                        "ralph": {
                            "agents": {"builder": "claude/opus:high", "reviewer": 3},
                            "envs": {"box": ["not", "one"]},
                        }
                    }
                }
            }
        },
    )

    assert Settings(tmp_path).agents("ralph") == {}
    assert Settings(tmp_path).envs("ralph") == {}


@pytest.mark.parametrize(
    "entry",
    [
        {"workspaces": "nothing"},
        {"workspaces": {"WHERE": "nothing"}},
        {"workspaces": {"WHERE": {"flows": ["ralph"]}}},
        {"workspaces": {"WHERE": {"flows": {"ralph": "x"}}}},
        {"workspaces": {"WHERE": {"flows": {"ralph": {"params": [1], "budget": 2}}}}},
    ],
)
def test_a_file_of_the_wrong_shape_reads_as_nothing_and_is_written_over(
    entry: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    where = str(tmp_path.resolve())
    held = doubles.store(
        monkeypatch, json.loads(json.dumps(entry).replace("WHERE", where))
    )
    said = Settings(tmp_path)

    assert said.params("ralph") == {}
    assert said.budget("ralph") == {}
    assert said.agents("ralph") == {}

    said.remember("ralph", {"builder": Runs("claude/opus:high")})

    assert Settings(tmp_path).agents("ralph") == {"builder": Runs("claude/opus:high")}
    assert held.writes == 1


@pytest.mark.parametrize(
    ("stored", "answer"),
    [
        ({}, None),
        ({"enable_sentry": "yes"}, None),
        ({"enable_sentry": True}, True),
        ({"enable_sentry": False}, False),
    ],
)
def test_whether_failures_are_reported_is_three_answers(
    stored: dict[str, Any], answer: bool | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    doubles.store(monkeypatch, stored)

    assert Settings().enable_sentry is answer


def test_the_answer_about_reporting_holds_for_every_workspace(
    held: doubles.Store, tmp_path: Path
) -> None:
    Settings(tmp_path / "a").answers(enable_sentry=False)

    assert held.held["enable_sentry"] is False
    assert Settings(tmp_path / "b").enable_sentry is False


def test_details_are_off_until_turned_on(held: doubles.Store) -> None:
    said = Settings()
    assert said.details is False

    said.detailing(on=True)
    assert said.details is True
    assert Settings().details is True

    said.detailing(on=False)
    assert Settings().details is False


def test_btw_is_nobodys_until_chosen(held: doubles.Store) -> None:
    said = Settings()
    assert said.btw == ""

    said.btw = "claude/haiku:low"
    assert Settings().btw == "claude/haiku:low"

    said.btw = ""
    assert Settings().btw == ""


def test_btw_that_is_not_a_word_reads_as_unchosen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doubles.store(monkeypatch, {"btw": 7})

    assert Settings().btw == ""


def test_forgetting_a_workspace_leaves_the_others_and_says_whether_it_was_there(
    held: doubles.Store, tmp_path: Path
) -> None:
    one, other = tmp_path / "one", tmp_path / "other"
    one.mkdir()
    other.mkdir()
    Settings(one).remember("ralph", {})
    Settings(other).remember("aot", {})
    Settings().answers(enable_sentry=True)

    assert Settings(one).forget() is True
    assert Settings(one).forget() is False
    assert Settings(one).flow == ""
    assert Settings(other).flow == "aot"
    assert Settings().enable_sentry is True


def test_another_workspace_is_forgotten_by_name(
    held: doubles.Store, tmp_path: Path
) -> None:
    Settings(tmp_path).remember("ralph", {})

    assert Settings(tmp_path / "elsewhere").forget(str(tmp_path.resolve())) is True
    assert Settings(tmp_path).flow == ""


def test_every_write_says_how_it_spells_an_environment(
    held: doubles.Store, tmp_path: Path
) -> None:
    Settings(tmp_path).detailing(on=True)

    assert held.held["spelling"] == machines.SPELLING


@pytest.mark.parametrize("why", [OSError("read-only"), yaml.YAMLError("garbled")])
def test_a_file_that_cannot_be_written_is_remembered_for_as_long_as_this_is(
    why: Exception, held: doubles.Store, tmp_path: Path
) -> None:
    held.fails = why
    said = Settings(tmp_path)

    said.remember("ralph", {"builder": Runs("claude/opus:high")})
    said.detailing(on=True)

    assert said.flow == "ralph"
    assert said.agents("ralph") == {"builder": Runs("claude/opus:high")}
    assert said.details is True
    assert held.held == {}


def test_environments_kept_the_old_way_are_respelled_once_on_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    where = str(tmp_path.resolve())
    held = doubles.store(
        monkeypatch,
        {
            "workspaces": {
                where: {
                    "flows": {
                        "ralph": {"envs": {"box": "docker@local/srv", "x": "local/y"}}
                    }
                }
            }
        },
    )
    monkeypatch.setattr(machines, "respelled", _respelled)

    said = Settings(tmp_path)

    assert said.envs("ralph") == {"box": "docker/srv", "x": "local/y"}
    assert held.held["spelling"] == machines.SPELLING
    assert held.writes == 1
    # Marked, so it is never respelled again.
    Settings(tmp_path)
    assert held.writes == 1


def test_a_file_with_nothing_to_respell_is_not_written_on_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    where = str(tmp_path.resolve())
    held = doubles.store(
        monkeypatch,
        {"workspaces": {where: {"flows": {"ralph": {"envs": {"x": "local/y"}}}}}},
    )
    monkeypatch.setattr(machines, "respelled", str)

    Settings(tmp_path)

    assert held.writes == 0
