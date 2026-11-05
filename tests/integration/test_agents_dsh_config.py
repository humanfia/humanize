"""DSH skill configuration preserved across epic homes, against its real SDK runtime."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import DshAgent, DshAgentConfig
from hmz.coganchor.agents.skills import Loaded, skills
from tests.integration.doubles_agents import Endpoint, serving

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.coganchor.agents import DshSession


@pytest.fixture
def endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Endpoint]:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh"))
    monkeypatch.setenv("DSH_AGENTS_HOME", str(tmp_path / "agents"))
    monkeypatch.chdir(tmp_path)
    for held in serving():
        monkeypatch.setenv("DEEPSEEK_BASE_URL", held.url)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-stand-in")
        yield held


def _skill(root: Path, name: str, body: str) -> Path:
    at = root / name
    at.mkdir(parents=True)
    (at / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} probe\n---\n{body}\n", encoding="utf-8"
    )
    return at


def _patch(root: Path, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "cordis.patch.yml"
    path.write_text(text, encoding="utf-8")
    return path


def _load(session: DshSession, name: str) -> str:
    return session("use skill " + json.dumps({"name": name}))


@pytest.mark.parametrize("kept", [False, True])
def test_original_provider_roots_and_home_layer_precedence_survive_epic_storage(
    endpoint: Endpoint, tmp_path: Path, kept: bool
) -> None:
    _skill(tmp_path / "dsh" / "skills", "default-hidden", "HIDDEN")
    _skill(tmp_path / "custom", "custom-visible", "CUSTOM")
    profile = _patch(
        tmp_path / "dsh" / "profiles" / "sdk",
        "- id: skill-filesystem\n  disabled: true\n",
    )
    home = _patch(
        tmp_path / "dsh",
        "- id: skill-filesystem\n  disabled: false\n  config:\n"
        "    includeDefaultRoots: false\n    customSkillDirs: [custom]\n    watch: false\n",
    )
    before = {path: path.read_text(encoding="utf-8") for path in (profile, home)}
    agent = DshAgent(DshAgentConfig(model="deepseek-stand-in", effort="high"))
    if kept:
        agent.keeps = tmp_path / "epic"
    try:
        session = agent.new(tmp_path)
        assert "CUSTOM" in _load(session, "custom-visible")
        assert "unknown or no longer available" in _load(session, "default-hidden")
    finally:
        agent.stop()
    assert {path: path.read_text(encoding="utf-8") for path in before} == before


@pytest.mark.parametrize("key", ["dshHome", "agentsHome"])
@pytest.mark.parametrize("kept", [False, True])
def test_explicit_empty_home_uses_the_workspace_in_catalog_and_runtime(
    endpoint: Endpoint, tmp_path: Path, key: str, kept: bool
) -> None:
    _skill(tmp_path / "skills", "at-cwd", "WORKSPACE-HOME")
    _patch(tmp_path / "dsh", f'- id: skill-filesystem\n  config:\n    {key}: ""\n')
    assert [one.name for one in skills("dsh", tmp_path)] == ["at-cwd"]
    agent = DshAgent(DshAgentConfig(model="deepseek-stand-in", effort="high"))
    if kept:
        agent.keeps = tmp_path / "epic"
    try:
        assert "WORKSPACE-HOME" in _load(agent.new(tmp_path), "at-cwd")
    finally:
        agent.stop()


@pytest.mark.parametrize("kept", [False, True])
def test_configured_homes_and_custom_root_yield_to_the_flow_and_project(
    endpoint: Endpoint, tmp_path: Path, kept: bool
) -> None:
    _skill(tmp_path / "configured-dsh" / "skills", "mine", "CONFIGURED-DSH")
    _skill(tmp_path / "configured-agents" / "skills", "shared", "CONFIGURED-AGENTS")
    _skill(tmp_path / "custom", "clash", "USER-CUSTOM")
    _skill(tmp_path / "custom", "project", "USER-CUSTOM")
    _skill(tmp_path / ".dsh" / "skills", "project", "PROJECT")
    _patch(
        tmp_path / "dsh" / "profiles" / "sdk",
        "- id: skill-filesystem\n  config:\n    providerName: humanize\n"
        "    dshHome: configured-dsh\n"
        "    agentsHome: configured-agents\n    customSkillDirs: [custom]\n    watch: false\n",
    )
    agent = DshAgent(DshAgentConfig(model="deepseek-stand-in", effort="high"))
    if kept:
        agent.keeps = tmp_path / "epic"
    agent.loads(
        [
            Loaded(name, _skill(tmp_path / "flow", name, "FLOW"), "flow")
            for name in ("clash", "project")
        ]
    )
    try:
        session = agent.new(tmp_path)
        assert "CONFIGURED-DSH" in _load(session, "mine")
        assert "CONFIGURED-AGENTS" in _load(session, "shared")
        assert "FLOW" in _load(session, "clash")
        assert "PROJECT" in _load(session, "project")
        session.loads([])
        assert "USER-CUSTOM" in _load(session, "clash")
        session.loads(["clash"])
        assert "FLOW" in _load(session, "clash")
        assert agent.opened == [session.id]
    finally:
        agent.stop()


@pytest.mark.parametrize("kept", [False, True])
def test_disabled_user_provider_stays_absent_while_flow_skills_load(
    endpoint: Endpoint, tmp_path: Path, kept: bool
) -> None:
    _skill(tmp_path / "dsh" / "skills", "hidden", "HIDDEN")
    _patch(tmp_path / "dsh", "- id: skill-filesystem\n  disabled: true\n")
    agent = DshAgent(DshAgentConfig(model="deepseek-stand-in", effort="high"))
    if kept:
        agent.keeps = tmp_path / "epic"
    agent.loads(
        [Loaded("brought", _skill(tmp_path / "flow", "brought", "FLOW"), "flow")]
    )
    try:
        session = agent.new(tmp_path)
        assert "unknown or no longer available" in _load(session, "hidden")
        assert "FLOW" in _load(session, "brought")
    finally:
        agent.stop()
