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

from dataclasses import replace

import pytest

from hmz.coganchor.agents import (
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
    # And the rung is still what it was: a refusal is not half a reconfiguration.
    assert agent.config.permission == "bypass"


@pytest.mark.parametrize("waiting", [0.0, -1.0, float("nan"), float("inf"), 1e16])
def test_agy_refuses_a_print_clock_that_cannot_be_written_as_a_duration(
    waiting: float,
) -> None:
    with pytest.raises(ValueError, match="positive number of seconds"):
        AntigravityCLIAgentConfig(model="m", effort="high", print_timeout=waiting)
