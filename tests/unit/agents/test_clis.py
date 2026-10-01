"""What the command-line backends settle before there is a command line to run.

Each of these backends refuses, where its configuration is written, a setting its CLI has no
way of hearing -- an option that is blank, a cap below zero, a rung its own flags would undo
-- because the alternative is a turn spent finding out. That refusal is the constructor's, so
it is checked by making a configuration and catching what it raises; nothing is installed,
nothing is started, and each of these is over in a millisecond.

The same backends driven against stand-ins that print what the real ones print are next door,
in `tests/integration/agents/test_clis.py`.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
import yaml

from hmz.coganchor.agents import (
    UNSAID,
    AntigravityCLIAgent,
    AntigravityCLIAgentConfig,
    GrokBuildAgentConfig,
    MimoCodeAgent,
    MimoCodeAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
)
from hmz.coganchor.fence import ALL, NONE, READ, Fence

if TYPE_CHECKING:
    from pathlib import Path

PI = PiAgentConfig(model="openai-codex/gpt-5.5", effort="high")
OPENCODE = OpencodeAgentConfig(model="opencode/big-pickle", effort="high")
MIMO = MimoCodeAgentConfig(model="xiaomi/mimo-v2.5", effort="low")
GROK = GrokBuildAgentConfig(model="grok-4.6", effort="xhigh")


def test_a_pi_option_with_nothing_in_it_is_refused_where_it_is_written() -> None:
    """Pi would take the flag and the blank after it and load nothing at all."""
    with pytest.raises(ValueError, match="append_system_prompt"):
        PiAgentConfig(
            model="openai-codex/gpt-5.5", effort="high", append_system_prompt=("  ",)
        )
    with pytest.raises(ValueError, match="skill_paths"):
        PiAgentConfig(model="openai-codex/gpt-5.5", effort="high", skill_paths=("",))


def test_a_pi_option_written_as_one_entry_is_refused_rather_than_spelled_out() -> None:
    """A string is a sequence of strings: `--skill` per character, and pi takes each one."""
    with pytest.raises(TypeError, match="skill_paths"):
        PiAgentConfig(
            model="openai-codex/gpt-5.5",
            effort="high",
            skill_paths="/flow/skills/review",  # pyright: ignore[reportArgumentType]
        )


def test_pi_that_never_opened_cannot_be_talked_to() -> None:
    with pytest.raises(RuntimeError, match="no turn is running"):
        PiAgent(PI).new().interject("hello?")


def test_the_new_backends_name_themselves_as_a_command_line_names_them() -> None:
    """`AgentBase.backend` is read off the class, so a mismatch is a backend nobody finds."""
    from hmz.coganchor import backends

    for agent, config in (
        (PiAgent, PI),
        (OpencodeAgent, OPENCODE),
        (MimoCodeAgent, MIMO),
    ):
        named = agent(config).backend
        assert backends.named(named) is not None, named


@pytest.mark.parametrize(
    "narrowed", [{"permission": "read-only"}, {"web_search": False}]
)
def test_the_table_is_refused_off_beside_what_it_was_the_only_way_of_saying(
    narrowed: dict[str, object],
) -> None:
    """A setting the CLI never hears is a setting that lies, so it is refused up front."""
    with pytest.raises(ValueError, match="permission_table"):
        OpencodeAgentConfig(
            model="m",
            effort="high",
            permission_table=False,
            **narrowed,  # pyright: ignore[reportArgumentType]
        )


def test_the_table_off_beside_nothing_at_all_takes_nothing_away() -> None:
    """A config that said neither of the two is the one that is asking for exactly this."""
    config = OpencodeAgentConfig(
        model="m", effort="high", permission="", web_search=None, permission_table=False
    )

    assert config.permission_table is False


def test_an_agent_name_the_cli_would_not_find_is_refused() -> None:
    """It warns and runs the default for one, which is a setting that quietly did nothing."""
    with pytest.raises(ValueError, match="cli_agent must be"):
        OpencodeAgentConfig(model="m", effort="high", cli_agent="the planner")


def test_grok_refuses_a_cap_of_less_than_nothing_where_it_is_written() -> None:
    """Rather than by a CLI refusing the argv, which is a turn that never started."""
    with pytest.raises(ValueError, match="max_turns"):
        replace(GROK, max_turns=-1)


def test_agy_refuses_a_read_only_rung_its_own_flag_would_undo() -> None:
    """Agy says plan mode has no effect while expansion is off, and goes on writing.

    Said where the config arrives rather than where it is written: the rung is the flow's, and
    a place declaring `read-only` settles it onto whatever agent it was handed.
    """
    told = AntigravityCLIAgentConfig(
        model="m", effort="high", disable_slash_commands=True
    )
    agent = AntigravityCLIAgent(told)
    with pytest.raises(ValueError, match="plan mode has no effect"):
        agent.reconfigure(replace(told, permission="read-only"))
    with pytest.raises(ValueError, match="plan mode has no effect"):
        AntigravityCLIAgent(replace(told, permission="read-only"))
    # And the rung is still what it was -- none at all: a refusal is not half a
    # reconfiguration.
    assert agent.config.permission == UNSAID


def test_agy_refuses_to_read_only_on_another_machine() -> None:
    """What holds it to reading is a file here, and an agent agy cannot find is its default.

    Which is every tool there is, and a turn that would say nothing about it.
    """
    from hmz.coganchor import AnchorConfig
    from hmz.coganchor.machines import AnchoredConfig

    elsewhere = AnchoredConfig(anchor=AnchorConfig(target="ssh://gpu-box"))
    told = AntigravityCLIAgentConfig(model="m", effort="high", machine=elsewhere)

    with pytest.raises(ValueError, match="on another machine"):
        AntigravityCLIAgent(replace(told, permission="read-only"))
    # Kept off the web is the same: what takes its web tools away is an agent here too.
    with pytest.raises(ValueError, match="on another machine"):
        AntigravityCLIAgent(replace(told, permission="bypass", web_search=False))
    assert AntigravityCLIAgent(replace(told, permission="bypass"))
    assert AntigravityCLIAgent(replace(told, permission="bypass", web_search=True))


@pytest.fixture
def agy_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home of the test's own, where agy's own home and humanize's agents in it are."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _started_as(config: AntigravityCLIAgentConfig) -> str | None:
    """The agent a turn at this config is started as, or None for agy's own default."""
    argv = AntigravityCLIAgent(config).new()._turn("hi")[0]
    return argv[argv.index("--agent") + 1] if "--agent" in argv else None


def _offline(home: Path, *, online: bool = False) -> Fence:
    return Fence.of(
        local=ALL,
        user=READ,
        system=NONE,
        online=online,
        workdir=home / "work",
        home=home,
    )


@pytest.mark.usefixtures("agy_home")
@pytest.mark.parametrize(
    ("permission", "web_search", "agent"),
    [
        ("bypass", None, None),
        ("bypass", True, None),
        ("bypass", False, "hmz-offline"),
        ("workspace-write", False, "hmz-offline"),
        ("read-only", None, "hmz-read-only"),
        ("read-only", False, "hmz-read-only"),
        ("read-only", True, "hmz-read-only-web"),
    ],
)
def test_agy_is_told_about_the_web_by_the_agent_it_is_started_as(
    permission: str, web_search: bool | None, agent: str | None
) -> None:
    """Agy has no flag that takes a tool away, so its web tools go with an agent that lacks them.

    And nothing is said where nothing was: an agent nobody asked about the web is agy's own.
    """
    config = AntigravityCLIAgentConfig(
        model="m", effort="high", permission=permission, web_search=web_search
    )
    assert _started_as(config) == agent


def test_agy_fenced_off_the_network_is_started_without_its_web_tools(
    agy_home: Path,
) -> None:
    """Its page fetcher runs at the far end of its model API, which no fence here can hold.

    So a fence that cuts the network takes the tools away whatever web search was said to be.
    """
    config = AntigravityCLIAgentConfig(
        model="m", effort="high", permission="bypass", web_search=True
    )
    assert _started_as(replace(config, fence=_offline(agy_home))) == "hmz-offline"
    assert _started_as(replace(config, fence=_offline(agy_home, online=True))) is None
    read_only = replace(config, permission="read-only", fence=_offline(agy_home))
    assert _started_as(read_only) == "hmz-read-only"


def test_agy_offline_agent_has_no_tool_that_reaches_the_web(agy_home: Path) -> None:
    """Nor one that starts an agent of its own, which would be one with the web's tools.

    Put where agy finds its own agents rather than in a directory added to the turn, which
    agy would run the agent's commands in whenever it sorted before the session's own.
    """
    argv = (
        AntigravityCLIAgent(
            AntigravityCLIAgentConfig(model="m", effort="high", web_search=False)
        )
        .new()
        ._turn("hi")[0]
    )
    assert "--add-dir" not in argv[: argv.index("--agent")]
    defined = agy_home / ".gemini" / "antigravity-cli" / "agents" / "hmz-offline.md"
    front = yaml.safe_load(defined.read_text().split("---")[1])
    assert front["name"] == "hmz-offline"
    assert "run_command" in front["tools"]
    assert "write_to_file" in front["tools"]
    assert not set(front["tools"]) & {
        "read_url_content",
        "search_web",
        "invoke_subagent",
        "define_subagent",
    }
    # Its own prompt kept: the tools are all this takes away.
    assert "excludeDefaultComponents" not in front


def _able(*, net: bool) -> bool:
    del net
    return True


def test_agy_enforces_none_of_its_fence_itself(
    agy_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--sandbox` holds its terminal alone, and does not start where user namespaces are shut.

    So the whole fence is put around it from outside, and humanize's agents are where every
    fence already lets agy read: its own home.
    """
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setattr("hmz.coganchor.fence.landlocked", _able)
    fence = _offline(agy_home)
    agent = AntigravityCLIAgent(
        AntigravityCLIAgentConfig(model="m", effort="high", fence=fence)
    )

    assert agent.natively(fence) is fence

    argv = agent.spawned(["agy", "--print", "hi"])
    assert argv[:5] == [sys.executable, "-Pm", "hmz", "internal", "fence"]
    policy = Fence.loads(argv[5].removeprefix("--policy="))
    assert not policy.online
    assert "cloudcode-pa.googleapis.com" in policy.hosts
    native = agy_home / ".gemini" / "antigravity-cli"
    assert policy.allows(native / "agents" / "hmz-offline.md")
    assert policy.allows(native, write=True)


@pytest.mark.parametrize("waiting", [0.0, -1.0, float("nan"), float("inf"), 1e16])
def test_agy_refuses_a_print_clock_that_cannot_be_written_as_a_duration(
    waiting: float,
) -> None:
    with pytest.raises(ValueError, match="positive number of seconds"):
        AntigravityCLIAgentConfig(model="m", effort="high", print_timeout=waiting)
