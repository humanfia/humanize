"""`hmz.coganchor.agents.skills`: the skills a CLI installs, and the ones a flow brings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents.skills import CARD, SKILLS, Skill, skills

if TYPE_CHECKING:
    from pathlib import Path


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
