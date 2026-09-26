"""Which harnesses there are, and what each one's protocol says it can do.

The harness kinds are coganchor's own names for the CLIs it drives, and each harness's
protocol carries exactly the mixins its driver serves -- one table, read by the flow a role is
typed with and by the driver that fills the role. Written out here once more, by hand, so that
a change to either is a change somebody meant.
"""

from __future__ import annotations

from typing import Protocol

import pytest

import hmz.flows
from hmz.coganchor import backends
from hmz.coganchor.agents import DRIVEN
from hmz.flows import (
    HARNESS_AGENTS,
    Agent,
    AskUserHookAgentMixin,
    BashEnvMixin,
    CPUEnvMixin,
    Env,
    FilesEnvMixin,
    GoalCommandAgentMixin,
    HarnessKind,
    LocalEnv,
    LoopCommandAgentMixin,
    PermissionRequestHookAgentMixin,
    ShellEnvMixin,
    SteeringAgentMixin,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
)
from hmz.runtime.flowing.spi import (
    AGENT_CAPABILITIES,
    ENV_CAPABILITIES,
    HARNESS_CAPABILITIES,
    capabilities_of,
)

GOAL, LOOP, STEER = GoalCommandAgentMixin, LoopCommandAgentMixin, SteeringAgentMixin
PERMISSION, ASK = PermissionRequestHookAgentMixin, AskUserHookAgentMixin
SUBAGENTS = {SubagentStartHookAgentMixin, SubagentStopHookAgentMixin}

#: The capability table, as the plan for this API wrote it down.
TABLE: dict[HarnessKind, tuple[str, set[type]]] = {
    HarnessKind.CLAUDE: (
        "ClaudeCodeAgent",
        {GOAL, LOOP, STEER, PERMISSION, *SUBAGENTS, ASK},
    ),
    HarnessKind.CODEX: ("CodexAgent", {GOAL, STEER, PERMISSION, *SUBAGENTS, ASK}),
    HarnessKind.CURSOR_AGENT: ("CursorAgent", SUBAGENTS),
    HarnessKind.KIMI: ("KimiCodeAgent", {GOAL, STEER, PERMISSION, ASK}),
    HarnessKind.ZCODE: ("ZCodeAgent", {GOAL, PERMISSION, ASK}),
    HarnessKind.GROK: ("GrokBuildAgent", set()),
    HarnessKind.PI: ("PiAgent", {STEER, ASK}),
    HarnessKind.DSH: ("DeepSeekHarnessAgent", {GOAL}),
    HarnessKind.OPENCODE: ("OpenCodeAgent", set()),
    HarnessKind.MIMO: ("MiMoCodeAgent", set()),
    HarnessKind.QWEN: ("QwenCodeAgent", set()),
    HarnessKind.AGY: ("AntigravityAgent", set()),
    HarnessKind.ACP: ("Agent", set()),
}


def test_the_harness_kinds_are_the_clis_coganchor_drives_and_acp() -> None:
    assert {kind.value for kind in HarnessKind} == {*DRIVEN, "acp"}


@pytest.mark.parametrize("name", sorted(DRIVEN))
def test_each_kind_is_the_name_coganchor_itself_calls_the_cli(name: str) -> None:
    profile = backends.named(name)
    assert profile is not None
    assert profile.name == HarnessKind(name).value


def test_every_harness_has_a_protocol_and_every_protocol_is_in_the_table() -> None:
    assert set(HARNESS_AGENTS) == set(HarnessKind) == set(TABLE)
    assert set(HARNESS_CAPABILITIES) == set(HarnessKind)


@pytest.mark.parametrize("kind", sorted(TABLE), ids=str)
def test_each_harness_protocol_carries_exactly_its_capabilities(
    kind: HarnessKind,
) -> None:
    name, capabilities = TABLE[kind]
    protocol = HARNESS_AGENTS[kind]
    assert protocol is getattr(hmz.flows, name)
    assert Agent in protocol.__mro__
    assert capabilities_of(protocol) == capabilities
    assert HARNESS_CAPABILITIES[kind] == capabilities


@pytest.mark.parametrize(
    "protocol",
    sorted({*HARNESS_AGENTS.values(), *AGENT_CAPABILITIES, *ENV_CAPABILITIES}, key=str),
    ids=lambda one: one.__name__,
)
def test_every_protocol_is_for_a_type_checker_and_not_for_isinstance(
    protocol: type,
) -> None:
    assert Protocol in protocol.__mro__
    assert not getattr(protocol, "_is_runtime_protocol", False)
    with pytest.raises(TypeError):
        isinstance(object(), protocol)


def test_a_role_asks_for_the_mixins_among_its_bases() -> None:
    class Coder(Agent, SteeringAgentMixin, GoalCommandAgentMixin):
        pass

    class Picky(Coder, AskUserHookAgentMixin):
        pass

    assert capabilities_of(Agent) == frozenset()
    assert capabilities_of(Coder) == {STEER, GOAL}
    assert capabilities_of(Picky) == {STEER, GOAL, ASK}


def test_an_environment_asks_for_behaviours_and_the_ones_they_imply() -> None:
    class Workspace(LocalEnv, BashEnvMixin, FilesEnvMixin, CPUEnvMixin):
        _cpu_count = 8

    assert capabilities_of(Env) == frozenset()
    assert capabilities_of(Workspace) == {BashEnvMixin, ShellEnvMixin, FilesEnvMixin}
    assert Workspace._cpu_count == 8


def test_a_role_left_to_the_defaults_reads_them_off_the_protocol() -> None:
    class Plain(Agent):
        pass

    assert Plain._permission == hmz.flows.Permission()
    assert Plain._skills == ()
    assert CPUEnvMixin._cpu_count == 1
