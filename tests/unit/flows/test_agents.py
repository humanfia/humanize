"""`hmz.flows.agents`: harnesses, permissions, budgets, usage and what each harness grants."""

from __future__ import annotations

import dataclasses
import datetime
import inspect
import math
import operator
from typing import Any

import pydantic
import pytest

from hmz.flows import (
    HARNESS_AGENTS,
    Agent,
    AntigravityAgent,
    AskUserHookAgentMixin,
    Budget,
    ClaudeCodeAgent,
    CodexAgent,
    CursorAgent,
    DeepSeekHarnessAgent,
    GoalCommandAgentMixin,
    GrokBuildAgent,
    HarnessKind,
    KimiCodeAgent,
    LiteLLMAgent,
    LoopCommandAgentMixin,
    MiMoCodeAgent,
    MiniMaxCodeAgent,
    OpenCodeAgent,
    Outworlder,
    Permission,
    PermissionKind,
    PermissionRequestHookAgentMixin,
    PiAgent,
    QwenCodeAgent,
    SteeringAgentMixin,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    Usage,
)

NONE, READ, ALL = PermissionKind.NONE, PermissionKind.READ, PermissionKind.ALL

# ---------------------------------------------------------------------------- HarnessKind


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        (HarnessKind.CLAUDE, "claude"),
        (HarnessKind.CODEX, "codex"),
        (HarnessKind.CURSOR_AGENT, "cursor-agent"),
        (HarnessKind.OPENCODE, "opencode"),
        (HarnessKind.MIMO, "mimo"),
        (HarnessKind.MCODE, "mcode"),
        (HarnessKind.QWEN, "qwen"),
        (HarnessKind.KIMI, "kimi"),
        (HarnessKind.GROK, "grok"),
        (HarnessKind.PI, "pi"),
        (HarnessKind.AGY, "agy"),
        (HarnessKind.DSH, "dsh"),
        (HarnessKind.LITELLM, "litellm"),
        (HarnessKind.ACP, "acp"),
    ],
)
def test_a_harness_is_named_as_dash_a_names_it(kind: HarnessKind, name: str) -> None:
    assert kind == name
    assert HarnessKind(name) is kind


def test_an_unknown_harness_is_refused() -> None:
    with pytest.raises(ValueError, match="nope"):
        HarnessKind("nope")


# ------------------------------------------------------------------------- PermissionKind


def test_permission_kinds_order_as_they_widen() -> None:
    assert NONE < READ < ALL
    assert ALL > READ > NONE
    assert sorted([ALL, NONE, READ]) == [NONE, READ, ALL]


@pytest.mark.parametrize(
    ("left", "right", "lt", "le", "gt", "ge"),
    [
        (NONE, NONE, False, True, False, True),
        (NONE, READ, True, True, False, False),
        (READ, ALL, True, True, False, False),
        (ALL, NONE, False, False, True, True),
        (READ, "read", False, True, False, True),
        (READ, "all", True, True, False, False),
    ],
)
def test_permission_kinds_compare_with_kinds_and_their_names(
    left: PermissionKind, right: str, lt: bool, le: bool, gt: bool, ge: bool
) -> None:
    assert (left < right, left <= right, left > right, left >= right) == (
        lt,
        le,
        gt,
        ge,
    )


@pytest.mark.parametrize("other", ["most", 1, None])
def test_a_permission_kind_does_not_compare_with_anything_else(other: Any) -> None:
    with pytest.raises(TypeError, match="is not a permission kind"):
        operator.lt(READ, other)


# ----------------------------------------------------------------------------- Permission


def test_a_permission_left_alone_changes_the_workdir_reads_the_rest_and_goes_online() -> (
    None
):
    granted = Permission()
    assert (granted.local, granted.user, granted.system, granted.online) == (
        ALL,
        READ,
        READ,
        ALL,
    )


def test_a_permission_takes_kinds_by_name() -> None:
    granted = Permission(local="read", user="none", system="none", online="none")  # pyright: ignore[reportArgumentType]
    assert granted == Permission(local=READ, user=NONE, system=NONE, online=NONE)
    assert type(granted.local) is PermissionKind


@pytest.mark.parametrize(
    ("given", "says"),
    [
        ({"local": "most"}, "local='most' is not a permission kind"),
        ({"online": 1}, "online=1 is not a permission kind"),
        ({"local": NONE}, "a wider scope may not be granted more than a narrower one"),
        ({"local": READ, "user": ALL}, "a wider scope"),
        ({"system": ALL}, "a wider scope"),
        ({"online": READ}, "online is all or nothing"),
    ],
)
def test_a_permission_refuses_what_is_not_one(given: dict[str, Any], says: str) -> None:
    with pytest.raises(ValueError, match=says):
        Permission(**given)


@pytest.mark.parametrize(
    "granted",
    [
        Permission(local=NONE, user=NONE, system=NONE, online=NONE),
        Permission(local=ALL, user=ALL, system=ALL, online=ALL),
        Permission(local=READ, user=READ, system=NONE, online=ALL),
    ],
)
def test_a_permission_that_nests_is_made(granted: Permission) -> None:
    assert granted.covers(granted)


def test_a_permission_cannot_be_changed() -> None:
    granted = Permission()
    with pytest.raises(dataclasses.FrozenInstanceError):
        granted.local = NONE  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize(
    ("wide", "narrow", "covers"),
    [
        (Permission(), Permission(), True),
        (Permission(), Permission(local=READ, user=NONE, system=NONE), True),
        (Permission(local=READ, user=NONE, system=NONE), Permission(), False),
        (Permission(online=NONE), Permission(), False),
        (Permission(), Permission(online=NONE), True),
        (Permission(system=NONE), Permission(), False),
        (Permission(user=ALL), Permission(user=READ), True),
    ],
)
def test_a_permission_covers_another_only_in_every_scope(
    wide: Permission, narrow: Permission, covers: bool
) -> None:
    assert wide.covers(narrow) is covers


# --------------------------------------------------------------------------------- Budget


@pytest.mark.parametrize(
    "limits",
    [
        {"duration": datetime.timedelta(minutes=5)},
        {"cost": 1.5},
        {"output_tokens": 0},
        {"cost": math.inf, "graceful": False},
    ],
)
def test_a_budget_sets_at_least_one_limit(limits: dict[str, Any]) -> None:
    budget = Budget(**limits)
    assert budget.model_dump(exclude_unset=True) == limits


def test_a_budget_finishes_its_turn_unless_told_otherwise() -> None:
    assert Budget(cost=1).graceful is True


@pytest.mark.parametrize(
    "limits",
    [
        {},
        {"graceful": False},
        {"cost": -1},
        {"output_tokens": -1},
        {"duration": datetime.timedelta(seconds=-1)},
        {"cost": 1, "turns": 3},
    ],
)
def test_a_budget_refuses_no_limit_or_a_negative_one(limits: dict[str, Any]) -> None:
    with pytest.raises(pydantic.ValidationError):
        Budget(**limits)


def test_a_budget_cannot_be_changed() -> None:
    budget = Budget(cost=1)
    with pytest.raises(pydantic.ValidationError):
        budget.cost = 2


def test_an_unlimited_budget_survives_json() -> None:
    written = Budget(cost=math.inf).model_dump_json()
    assert '"Infinity"' in written
    assert Budget.model_validate_json(written).cost == math.inf


# ---------------------------------------------------------------------------------- Usage


def test_usage_starts_at_nothing() -> None:
    assert Usage() == Usage(duration=datetime.timedelta(0), cost=0.0, output_tokens=0)


def test_usage_cannot_be_changed_nor_take_more() -> None:
    usage = Usage(cost=1.0)
    with pytest.raises(pydantic.ValidationError):
        usage.cost = 2.0
    with pytest.raises(pydantic.ValidationError):
        Usage.model_validate({"turns": 1})


def test_usage_survives_json() -> None:
    usage = Usage(
        duration=datetime.timedelta(seconds=3), cost=math.inf, output_tokens=9
    )
    assert Usage.model_validate_json(usage.model_dump_json()) == usage


# ------------------------------------------------------------------- the harness protocols

EVERY_MIXIN = (
    GoalCommandAgentMixin,
    LoopCommandAgentMixin,
    SteeringAgentMixin,
    PermissionRequestHookAgentMixin,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    AskUserHookAgentMixin,
)

NOTHING: set[type] = set()
SUBAGENTS: set[type] = {SubagentStartHookAgentMixin, SubagentStopHookAgentMixin}


@pytest.mark.parametrize(
    ("kind", "protocol", "mixins"),
    [
        (HarnessKind.CLAUDE, ClaudeCodeAgent, set(EVERY_MIXIN)),
        (
            HarnessKind.CODEX,
            CodexAgent,
            set(EVERY_MIXIN) - {LoopCommandAgentMixin},
        ),
        (HarnessKind.CURSOR_AGENT, CursorAgent, SUBAGENTS),
        (HarnessKind.OPENCODE, OpenCodeAgent, NOTHING),
        (HarnessKind.MIMO, MiMoCodeAgent, NOTHING),
        (HarnessKind.MCODE, MiniMaxCodeAgent, SUBAGENTS),
        (HarnessKind.QWEN, QwenCodeAgent, NOTHING),
        (
            HarnessKind.KIMI,
            KimiCodeAgent,
            {
                GoalCommandAgentMixin,
                SteeringAgentMixin,
                PermissionRequestHookAgentMixin,
                AskUserHookAgentMixin,
            },
        ),
        (HarnessKind.GROK, GrokBuildAgent, NOTHING),
        (HarnessKind.PI, PiAgent, {SteeringAgentMixin, AskUserHookAgentMixin}),
        (HarnessKind.AGY, AntigravityAgent, NOTHING),
        (HarnessKind.DSH, DeepSeekHarnessAgent, {GoalCommandAgentMixin}),
        (HarnessKind.LITELLM, LiteLLMAgent, NOTHING),
        (HarnessKind.ACP, Agent, NOTHING),
    ],
)
def test_each_harness_asks_for_what_it_can_do(
    kind: HarnessKind, protocol: type, mixins: set[type]
) -> None:
    assert HARNESS_AGENTS[kind] is protocol
    assert Agent in protocol.__mro__
    assert {one for one in EVERY_MIXIN if one in protocol.__mro__} == mixins


def test_every_harness_has_a_protocol() -> None:
    assert set(HARNESS_AGENTS) == set(HarnessKind)


def test_the_harness_protocols_cannot_be_changed() -> None:
    with pytest.raises(TypeError):
        HARNESS_AGENTS[HarnessKind.CLAUDE] = Agent  # pyright: ignore[reportIndexIssue]


def test_an_outworlder_is_an_agent() -> None:
    assert Agent in inspect.getmro(Outworlder)
