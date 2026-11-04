"""DeepSeek Harness, driven through `DshAgent` and its SDK against a loopback endpoint.

The harness is the SDK's own bundled runtime, started by the driver as it would be anywhere;
what it calls is the model, which here is an `Endpoint` on the loopback that
`DEEPSEEK_BASE_URL` points it at. So a turn is the whole path -- the driver composing the
runtime, the SDK's JSON-RPC to it, the runtime's chat completion -- with only the model
standing in. Under an account a local LiteLLM gateway holds, the gateway is run for real
between the two.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import providers
from hmz.coganchor.agents import DshAgent, DshAgentConfig, Failed, Unrecoverable
from hmz.coganchor.agents.skills import Loaded, skills
from hmz.coganchor.gateway import gatewayable
from tests.integration.doubles_agents import Endpoint, harnessed, kinds, serving

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.coganchor.agents import DshSession

CONFIG = DshAgentConfig(model="deepseek-stand-in", effort="high")


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


def _conversation(asked: dict[str, Any]) -> list[tuple[str, str]]:
    """What one request carried of the conversation, leaving out what the harness wrote."""
    return [
        (str(one["role"]), str(one.get("content") or ""))
        for one in asked["messages"]
        if one["role"] != "system" and not harnessed(one)
    ]


def test_a_turn_says_what_it_thought_said_and_spent(endpoint: Endpoint) -> None:
    said = list(DshAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["reasoning", "text", "result"]
    assert said[0].text == "thinking about hello"
    assert said[-1].text == "hello"
    assert dict(said[-1].tokens) == {"deepseek-stand-in": 18}
    assert said[-1].spent.output == 7
    (asked,) = endpoint.asked
    assert asked["model"] == "deepseek-stand-in"
    assert asked["reasoning_effort"] == "high"
    assert _conversation(asked) == [("user", "hello")]


def test_a_second_turn_carries_the_session_on(endpoint: Endpoint) -> None:
    agent = DshAgent(CONFIG)
    session = agent.new()

    assert session("one") == "one"
    assert session("two") == "two"

    assert _conversation(endpoint.asked[-1]) == [
        ("user", "one"),
        ("assistant", "one"),
        ("user", "two"),
    ]
    assert agent.opened == [session.id]


def test_a_refused_request_is_a_failed_turn_leaving_nothing_open(
    endpoint: Endpoint,
) -> None:
    agent = DshAgent(CONFIG)
    session = agent.new()

    with pytest.raises(Failed):
        session("unfinished")
    assert agent.opened == []


def test_a_model_gone_silent_is_given_up_on_by_the_watchdog(
    endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        DshAgent(CONFIG).new()("hang")


@pytest.mark.skipif(not gatewayable(), reason="the [litellm] extra is not installed")
@pytest.mark.timeout(240)
def test_a_turn_under_an_account_a_gateway_holds_reaches_its_endpoint_through_it(
    endpoint: Endpoint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "hmz"))
    monkeypatch.setenv("LITELLM_GATEWAY_KEY", "lying-about")
    providers.add(
        "dsh",
        "gw",
        way="litellm-openai-gateway",
        env={
            "LITELLM_GATEWAY_URL": endpoint.url,
            "LITELLM_GATEWAY_KEY": "upstream-secret",
            "LITELLM_GATEWAY_API": "openai",
        },
    )
    agent = DshAgent(DshAgentConfig(model="stand-in", effort="high", provider="gw"))
    try:
        said = list(agent.new().stream("hello"))
        through = agent.gateway
        assert through is not None
        env = agent.environment()
        hushed = agent.hushed()
    finally:
        agent.stop()

    assert said[-1].text == "hello"
    (asked,) = endpoint.asked
    assert asked["model"] == "stand-in"
    assert _conversation(asked) == [("user", "hello")]
    assert env["DEEPSEEK_BASE_URL"] == through.url
    assert env["DEEPSEEK_API_KEY"] == through.key
    assert "upstream-secret" not in env.values()
    assert "LITELLM_GATEWAY_KEY" in hushed
    assert not through.running


def test_a_callback_offered_is_run_here_when_the_model_reaches_for_it(
    endpoint: Endpoint,
) -> None:
    from pydantic import BaseModel

    from hmz.coganchor.agents import FakeTool

    class Asked(BaseModel):
        word: str

    heard: list[str] = []

    def shout(asked: Asked) -> str:
        heard.append(asked.word)
        return asked.word.upper()

    session = DshAgent(CONFIG).new()
    session.offers([FakeTool("shout", "Says a word louder.", shout, Asked)])

    said = session('use shout {"word": "hi"}')

    assert heard == ["hi"]
    assert said == "the tool said HI"
    offered = [one["function"]["name"] for one in endpoint.asked[0]["tools"]]
    assert "mcp__humanize__shout" in offered


def test_a_new_effort_after_a_turn_is_refused_before_the_runtime_is(
    endpoint: Endpoint,
) -> None:
    session = DshAgent(CONFIG).new()
    assert session("one") == "one"

    session.effort = "low"
    with pytest.raises(Unrecoverable, match="cannot carry") as refused:
        session("two")

    assert "already exists" not in str(refused.value)
    assert len(endpoint.asked) == 1


def test_other_tools_after_a_turn_are_refused_before_the_runtime_is(
    endpoint: Endpoint,
) -> None:
    from pydantic import BaseModel

    from hmz.coganchor.agents import FakeTool

    class Asked(BaseModel):
        word: str

    def shout(asked: Asked) -> str:
        return asked.word.upper()

    session = DshAgent(CONFIG).new()
    assert session("one") == "one"

    session.offers([FakeTool("shout", "Says a word louder.", shout, Asked)])
    with pytest.raises(Unrecoverable, match="cannot carry") as refused:
        session("two")

    assert "already exists" not in str(refused.value)
    assert len(endpoint.asked) == 1


def test_a_fresh_session_takes_its_first_turn_at_a_new_effort(
    endpoint: Endpoint,
) -> None:
    session = DshAgent(CONFIG).new()

    session.effort = "low"

    assert session("one") == "one"
    (asked,) = endpoint.asked
    assert asked["reasoning_effort"] == "low"


def _skill(root: Path, name: str, body: str, *resources: str) -> Path:
    """One skill, as `<root>/<name>/SKILL.md` with what else its directory holds."""
    (root / name).mkdir(parents=True)
    (root / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Unique {name} probe.\n---\n{body}\n",
        encoding="utf-8",
    )
    for one in resources:
        (root / name / one).write_text(one, encoding="utf-8")
    return root / name


def _loaded(session: DshSession, name: str) -> str:
    """What the runtime's own `skill` tool answers the model asking for `name`."""
    return session("use skill " + json.dumps({"name": name}))


def _tree(root: Path) -> list[str]:
    return sorted(str(one.relative_to(root)) for one in root.rglob("*"))


def test_catalog_and_runtime_agree_on_yaml_string_skill_names(
    endpoint: Endpoint, tmp_path: Path
) -> None:
    names = ("yes", "on", "no", "2026-11-04")
    for name in names:
        _skill(tmp_path / "dsh" / "skills", name, f"BODY-{name}")
    assert {one.name for one in skills("dsh", tmp_path)} == set(names)
    agent = DshAgent(CONFIG)
    try:
        session = agent.new()
        for name in names:
            assert f"BODY-{name}" in _loaded(session, name)
    finally:
        agent.stop()


@pytest.mark.timeout(240)
@pytest.mark.parametrize("kept", [False, True])
def test_a_session_loads_the_users_the_projects_and_the_flows_skills(
    endpoint: Endpoint, tmp_path: Path, kept: bool
) -> None:
    """Of one name, the project's before the flow's, and the flow's before the user's.

    The same whether its sessions are kept in the epic -- its runtime handed the epic's home
    -- or not: the user's home read as the harness reads it, passing over `.system`, and
    before `$DSH_AGENTS_HOME`.
    """
    work = tmp_path / "repo" / "nested"
    work.mkdir(parents=True)
    (tmp_path / "repo" / ".git").mkdir()
    user, shared = tmp_path / "dsh" / "skills", tmp_path / "agents" / "skills"
    project = tmp_path / "repo" / ".dsh" / "skills"
    flow = tmp_path / "flow" / "skills"
    _skill(user, "mine", "BODY-mine")
    _skill(user, "clash", "BODY-clash-user")
    _skill(user, "flowed", "BODY-flowed-user")
    _skill(user, "homes", "BODY-homes-dsh")
    _skill(shared, "homes", "BODY-homes-shared")
    (user / ".system").mkdir()
    (user / ".system" / "SKILL.md").write_text(
        "---\nname: system\ndescription: The harness's own.\n---\nBODY-system\n",
        encoding="utf-8",
    )
    _skill(shared, "shared", "BODY-shared")
    _skill(project, "clash", "BODY-clash-project")
    _skill(tmp_path / "repo" / ".agents" / "skills", "agents", "BODY-agents")
    brought = [
        Loaded("clash", _skill(flow, "clash", "BODY-clash-flow"), "flow"),
        Loaded(
            "flowed", _skill(flow, "flowed", "BODY-flowed-flow", "notes.md"), "flow"
        ),
    ]
    before = {one: _tree(one) for one in (user, shared, tmp_path / "repo")}
    agent = DshAgent(CONFIG)
    if kept:
        agent.keeps = tmp_path / "epic" / "sessions"
    agent.loads(brought)
    session = agent.new(work)
    try:
        said = {
            name: _loaded(session, name)
            for name in (
                *("mine", "shared", "agents", "clash", "flowed", "homes", "system"),
                "nowhere",
            )
        }
        # The flow's whole directory came with it, put where the session alone reads it.
        based = Path(said["flowed"].split("skill: ")[1].split("\n")[0])
        assert (based / "notes.md").read_text(encoding="utf-8") == "notes.md"
    finally:
        agent.stop()

    assert [one.name for one in skills("dsh", work)] == [
        "clash",
        "agents",
        "flowed",
        "homes",
        "mine",
        "shared",
    ]
    assert "BODY-mine" in said["mine"]
    assert "BODY-shared" in said["shared"]
    assert "BODY-agents" in said["agents"]
    assert "BODY-clash-project" in said["clash"]
    assert "BODY-flowed-flow" in said["flowed"]
    assert "BODY-homes-dsh" in said["homes"]
    assert "unknown or no longer available" in said["system"]
    assert "unknown or no longer available" in said["nowhere"]
    assert not based.exists()
    assert not based.is_relative_to(tmp_path / "repo")
    assert (tmp_path / "epic" / "sessions" / "dsh").is_dir() is kept
    assert {one: _tree(one) for one in before} == before


@pytest.mark.timeout(240)
def test_a_sessions_skills_changed_between_turns_change_in_the_same_conversation(
    endpoint: Endpoint, tmp_path: Path
) -> None:
    """Told the runtime's catalog by the plugin humanize mounts, and by no file watcher."""
    flow = tmp_path / "flow" / "skills"
    agent = DshAgent(CONFIG)
    agent.loads(
        [
            Loaded("first", _skill(flow, "first", "BODY-first"), "flow"),
            Loaded("second", _skill(flow, "second", "BODY-second"), "flow"),
        ]
    )
    session = agent.new()
    session.loads(["first"])
    try:
        assert "BODY-first" in _loaded(session, "first")
        session.loads(["second"])
        took = _loaded(session, "first")
        assert "unknown or no longer available" in took
        assert "BODY-second" in _loaded(session, "second")
    finally:
        agent.stop()

    assert agent.opened == [session.id]
    catalogs = json.dumps(endpoint.asked[-1]["messages"]).split("<available_skills>")
    assert len(catalogs) == 3
    assert "The available skill catalog changed" in catalogs[1]
    assert "second" in catalogs[-1]
    assert "`first`" not in catalogs[-1]


@pytest.mark.timeout(240)
def test_two_sessions_carry_their_own_skills_and_leave_nothing_behind(
    endpoint: Endpoint, tmp_path: Path
) -> None:
    flow = tmp_path / "flow" / "skills"
    agent = DshAgent(CONFIG)
    agent.loads(
        [
            Loaded("first", _skill(flow, "first", "BODY-first"), "flow"),
            Loaded("second", _skill(flow, "second", "BODY-second"), "flow"),
        ]
    )
    one, other = agent.new(), agent.new()
    one.loads(["first"])
    other.loads(["second"])
    try:
        mine = _loaded(one, "first")
        theirs = _loaded(one, "second")
        held = _loaded(other, "second")
    finally:
        agent.stop()

    assert "BODY-first" in mine
    assert "unknown or no longer available" in theirs
    assert "BODY-second" in held
    for said in (mine, held):
        based = said.split("Base directory for this skill: ")[1].split("\n")[0]
        assert not Path(based).exists()
    assert _tree(flow) == ["first", "first/SKILL.md", "second", "second/SKILL.md"]
    assert not (tmp_path / "dsh" / "skills").exists()
