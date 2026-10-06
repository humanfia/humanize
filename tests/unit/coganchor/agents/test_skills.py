"""`hmz.coganchor.agents.skills`: the skills a CLI installs, and the ones a flow mounts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents.skills import (
    CARD,
    SKILLS,
    Loaded,
    Mounted,
    Skill,
    carried,
    mount,
    skills,
    unmount,
)
from hmz.runtime import telemetry

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def snags(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What was reported, in place of reporting it."""
    said: list[str] = []
    monkeypatch.setattr(telemetry, "snag", said.append)
    return said


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Claude Code's home, the config directory and the user's home, all under the test."""
    held = {
        "claude": tmp_path / "claude-home",
        "config": tmp_path / "xdg",
        "home": tmp_path / "home",
        "project": tmp_path / "project",
    }
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(held["claude"]))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(held["config"]))
    monkeypatch.setenv("HOME", str(held["home"]))
    return held


def _card(at: Path, text: str) -> Path:
    at.mkdir(parents=True, exist_ok=True)
    (at / CARD).write_text(text, encoding="utf-8")
    return at


def test_the_names_of_things() -> None:
    assert (SKILLS, CARD) == ("skills", "SKILL.md")


def test_skills_of_an_unknown_backend_are_none(tmp_path: Path) -> None:
    assert skills("no-such-cli", tmp_path) == []


def test_skills_reads_yours_then_the_projects(homes: dict[str, Path]) -> None:
    _card(
        homes["claude"] / "skills" / "b-dir",
        "---\nname: beta\ndescription: |\n  the second\n  one\n---\nbody",
    )
    _card(homes["claude"] / "skills" / "a-dir", "no front matter at all")
    _card(homes["project"] / ".claude" / "skills" / "beta", "---\nname: beta\n---\n")
    _card(
        homes["project"] / ".claude" / "skills" / "gamma",
        "---\ndescription: " + "x" * 200 + "\n---\n",
    )
    found = skills("claude", homes["project"])
    assert [(one.name, one.whose) for one in found] == [
        ("a-dir", "yours"),
        ("beta", "yours"),
        ("gamma", "this project"),
    ]
    assert found[0].about == ""
    assert found[1] == Skill(name="beta", about="the second one", whose="yours")
    assert found[2].about == "x" * 90 + "…"


@pytest.mark.parametrize(
    "card",
    ["---\n[unclosed\n---\n", "---\n- a list\n---\n", "---\nname: ''\n---\n"],
)
def test_unreadable_front_matter_names_the_skill_by_its_directory(
    homes: dict[str, Path], card: str
) -> None:
    _card(homes["project"] / ".claude" / "skills" / "dir-name", card)
    found = skills("claude", homes["project"])
    assert [one.name for one in found] == ["dir-name"]


def test_carried_says_where_each_skill_goes(tmp_path: Path) -> None:
    loaded = [Loaded("one", tmp_path / "one"), Loaded("", tmp_path / "unnamed")]
    assert carried("claude", loaded) == ((str(tmp_path / "one"), ".claude/skills/one"),)
    assert carried("codex", loaded) == ((str(tmp_path / "one"), ".agents/skills/one"),)
    assert carried("no-such-cli", loaded) == ()


def test_mount_with_nothing_to_mount(tmp_path: Path) -> None:
    assert mount("no-such-cli", tmp_path, [Loaded("x", tmp_path)]) == Mounted()
    assert mount("claude", tmp_path, []) == Mounted()


def test_mount_copies_and_unmount_takes_away_what_it_made(tmp_path: Path) -> None:
    source = _card(tmp_path / "flow" / "review", "---\nname: review\n---\n")
    workspace = tmp_path / "work"
    workspace.mkdir()
    mounted = mount("claude", workspace, [Loaded("review", source, "flow")])
    at = workspace / ".claude" / "skills" / "review"
    assert mounted == Mounted((at,))
    assert (at / CARD).read_text(encoding="utf-8") == "---\nname: review\n---\n"
    unmount(mounted)
    assert not at.exists()
    assert not (workspace / ".claude").exists()  # the directories it made go too
    unmount(mounted)  # twice is harmless


def test_two_sessions_share_a_mount_until_the_last_lets_go(tmp_path: Path) -> None:
    source = _card(tmp_path / "flow" / "review", "x")
    loaded = [Loaded("review", source)]
    first = mount("claude", tmp_path / "work", loaded)
    second = mount("claude", tmp_path / "work", loaded)
    assert first == second
    unmount(first)
    assert first.at[0].exists()
    unmount(second)
    assert not first.at[0].exists()


def test_a_skill_already_there_is_left_alone(tmp_path: Path, snags: list[str]) -> None:
    source = _card(tmp_path / "flow" / "review", "flow's")
    theirs = _card(tmp_path / "work" / ".claude" / "skills" / "review", "project's")
    assert mount("claude", tmp_path / "work", [Loaded("review", source)]) == Mounted()
    assert (theirs / CARD).read_text(encoding="utf-8") == "project's"
    assert snags == ["skill-name-taken"]


def test_another_flows_skill_of_the_same_name_is_left_alone(
    tmp_path: Path, snags: list[str]
) -> None:
    one = _card(tmp_path / "a" / "review", "a")
    other = _card(tmp_path / "b" / "review", "b")
    first = mount("claude", tmp_path / "work", [Loaded("review", one)])
    assert mount("claude", tmp_path / "work", [Loaded("review", other)]) == Mounted()
    assert snags == ["skill-name-taken"]
    unmount(first)


def test_a_skill_that_cannot_be_copied_leaves_nothing(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    mounted = mount("claude", workspace, [Loaded("gone", tmp_path / "missing")])
    assert mounted == Mounted()
    skills_dir = workspace / ".claude" / "skills"
    assert list(skills_dir.iterdir()) == []
