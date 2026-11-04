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


def _dsh_card(at: Path, name: str, about: str = "") -> None:
    at.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\nname: {name}\ndescription: {about or name}\n---\nbody"
    if at.suffix == ".md":
        at.write_text(text, encoding="utf-8")
    else:
        _card(at, text)


def test_dsh_skills_are_found_where_its_runtime_finds_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its home, the shared `.agents`, and the project's root from a directory inside it."""
    home, shared, project = tmp_path / "dsh", tmp_path / "agents", tmp_path / "repo"
    monkeypatch.setenv("DSH_HOME", str(home))
    monkeypatch.setenv("DSH_AGENTS_HOME", str(shared))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (project / ".git").mkdir(parents=True)
    nested = project / "src" / "deep"
    nested.mkdir(parents=True)
    _dsh_card(home / "skills" / "mine", "mine")
    _dsh_card(home / "skills" / "flat.md", "flat")
    _dsh_card(home / "skills" / ".system", "hidden")
    _dsh_card(home / "skills" / "both", "both", "the user's")
    _dsh_card(shared / "skills" / "shared", "shared")
    _dsh_card(project / ".dsh" / "skills" / "both", "both", "the project's")
    _dsh_card(project / ".agents" / "skills" / "agents", "agents")
    # Read nowhere: below the project's root rather than at it, and named the harness's way.
    _dsh_card(nested / ".dsh" / "skills" / "below", "below")
    _card(home / "skills" / "unnamed", "---\ndescription: no name\n---\n")
    _card(home / "skills" / "undescribed", "---\nname: undescribed\n---\n")
    _dsh_card(home / "skills" / "Upper", "Upper")

    found = skills("deepseek-harness", nested)

    assert [(one.name, one.whose) for one in found] == [
        ("both", "this project"),
        ("agents", "this project"),
        ("flat", "yours"),
        ("mine", "yours"),
        ("shared", "yours"),
    ]
    assert found[0].about == "the project's"


def test_dsh_skills_default_to_the_users_own_homes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory with no `.git` above it is its own project."""
    monkeypatch.delenv("DSH_HOME", raising=False)
    monkeypatch.delenv("DSH_AGENTS_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _dsh_card(tmp_path / "home" / ".dsh" / "skills" / "mine", "mine")
    _dsh_card(tmp_path / "home" / ".agents" / "skills" / "shared", "shared")
    _dsh_card(tmp_path / "work" / ".agents" / "skills" / "here", "here")

    found = skills("dsh", tmp_path / "work")

    assert [one.name for one in found] == ["here", "mine", "shared"]


@pytest.mark.parametrize(
    ("card", "listed"),
    [
        ("---\nname: " + "a-" * 60 + "z\ndescription: long\n---\n", True),
        ("---\nname: blank\ndescription: '   '\n---\n", True),
        ("---\nname: yes\ndescription: on\n---\n", True),
        ("---\nname: no\ndescription: 2026-11-04\n---\n", True),
        ("---\nname: 2026-11-04\ndescription: date\n---\n", True),
        ("---\nname: true\ndescription: boolean\n---\n", False),
        ("---\nname: numeric-flag\ndescription: x\nuser-invocable: 1.0\n---\n", True),
        ("---\r\nname: crlf\r\ndescription: x\r\n---\r\nbody", True),
        ("---\nname: closed\ndescription: x\n---", True),
        ("---\nname: unclosed\ndescription: x\n", False),
        ("---\nname: dashed\ndescription: x\n---more\n", False),
        ("--- \nname: spaced\ndescription: x\n---\n", False),
        ("---\nname: empty\ndescription: ''\n---\n", False),
        ("---\nname: numbered\ndescription: 5\n---\n", False),
        ("---\nname: Upper\ndescription: x\n---\n", False),
        ("---\nname: two--dashes\ndescription: x\n---\n", False),
        ("---\nname: legacy\ndescription: x\nuserInvocable: true\n---\n", False),
        ("---\nname: flagged\ndescription: x\nuser-invocable: 'Off'\n---\n", True),
        ("---\nname: unflagged\ndescription: x\nuser-invocable: maybe\n---\n", False),
        (
            "---\nname: hidden\ndescription: x\ndisable-model-invocation: true\n---\n",
            True,
        ),
    ],
)
def test_dsh_lists_a_skill_exactly_where_its_runtime_would(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, card: str, listed: bool
) -> None:
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh"))
    monkeypatch.setenv("DSH_AGENTS_HOME", str(tmp_path / "agents"))
    _card(tmp_path / "dsh" / "skills" / "one", card)

    assert bool(skills("dsh", tmp_path / "work")) is listed


def test_only_the_dsh_homes_own_root_passes_over_its_system_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared root is read as the shared root, even where it is the same directory."""
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "same"))
    monkeypatch.setenv("DSH_AGENTS_HOME", str(tmp_path / "same"))
    _dsh_card(tmp_path / "same" / "skills" / ".system", "system")
    _dsh_card(tmp_path / "work" / ".dsh" / "skills" / ".system", "projected")

    found = skills("dsh", tmp_path / "work")

    assert [(one.name, one.whose) for one in found] == [
        ("projected", "this project"),
        ("system", "yours"),
    ]
