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
    PRESETS,
    Access,
    Agent,
    AntigravityAgent,
    AskUserHookAgentMixin,
    Budget,
    ClaudeCodeAgent,
    CodexAgent,
    CursorAgent,
    DeepSeekHarnessAgent,
    GoalCommandAgentMixin,
    Graceful,
    GrokBuildAgent,
    HarnessKind,
    KimiCodeAgent,
    LiteLLMAgent,
    LoopCommandAgentMixin,
    MiMoCodeAgent,
    MiniMaxCodeAgent,
    OhMyPiAgent,
    OpenCodeAgent,
    Outworlder,
    Permission,
    PermissionRequestHookAgentMixin,
    PiAgent,
    QwenCodeAgent,
    Rule,
    SteeringAgentMixin,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    Usage,
    allow,
    deny,
    read_only,
)

NONE, READ, WRITE = Access.NONE, Access.READ, Access.WRITE

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
        (HarnessKind.OMP, "omp"),
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


# --------------------------------------------------------------------------------- Access


def test_accesses_order_as_they_widen() -> None:
    assert NONE < READ < WRITE
    assert WRITE > READ > NONE
    assert sorted([WRITE, NONE, READ]) == [NONE, READ, WRITE]


@pytest.mark.parametrize(
    ("left", "right", "lt", "le", "gt", "ge"),
    [
        (NONE, NONE, False, True, False, True),
        (NONE, READ, True, True, False, False),
        (READ, WRITE, True, True, False, False),
        (WRITE, NONE, False, False, True, True),
        (READ, "read", False, True, False, True),
        (READ, "write", True, True, False, False),
    ],
)
def test_accesses_compare_with_accesses_and_their_names(
    left: Access, right: str, lt: bool, le: bool, gt: bool, ge: bool
) -> None:
    assert (left < right, left <= right, left > right, left >= right) == (
        lt,
        le,
        gt,
        ge,
    )


@pytest.mark.parametrize("other", ["all", 1, None])
def test_an_access_does_not_compare_with_anything_else(other: Any) -> None:
    with pytest.raises(TypeError, match="is not an access"):
        operator.lt(READ, other)


# ------------------------------------------------------------------------------- Rule


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("/", "/"),
        ("/srv//data/", "/srv/data"),
        ("/./srv/./x", "/srv/x"),
        ("~", "~"),
        ("~/", "~"),
        ("~/a//b/", "~/a/b"),
        (".", "."),
        ("./", "."),
        ("./src/./x/", "./src/x"),
    ],
)
def test_a_rule_keeps_its_path_tidied(given: str, kept: str) -> None:
    assert Rule(given, READ).path == kept


@pytest.mark.parametrize(
    "path",
    [
        "",
        "src",
        "~other",
        "~/../x",
        "./a/../b",
        "/a/..",
        "/a*",
        "./?",
        "~/[ab]",
        "/a\0b",
        "$HOME",
    ],
)
def test_a_rule_refuses_a_path_anchored_nowhere_climbing_out_or_globbed(
    path: str,
) -> None:
    with pytest.raises(ValueError, match="a rule's path is"):
        Rule(path, READ)


def test_a_rule_takes_its_access_by_name_and_refuses_anything_else() -> None:
    made = Rule("/srv", "write")  # pyright: ignore[reportArgumentType]
    assert made == allow("/srv")
    assert type(made.access) is Access
    with pytest.raises(ValueError, match="all"):
        Rule("/srv", "all")  # pyright: ignore[reportArgumentType]


def test_the_three_makers_say_the_three_accesses() -> None:
    assert allow("~/x") == Rule("~/x", WRITE)
    assert read_only("~/x") == Rule("~/x", READ)
    assert deny("~/x") == Rule("~/x", NONE)


# ----------------------------------------------------------------------------- Permission


def test_a_permission_left_alone_changes_the_workdir_reads_the_rest_and_goes_online() -> (
    None
):
    granted = Permission()
    assert (granted.preset, granted.network, granted.granular) == (
        "workspace-write",
        True,
        (),
    )
    assert granted.rules == (read_only("/"), allow("."))
    assert PRESETS == ("read-only", "workspace-write", "danger-full-access")


@pytest.mark.parametrize(
    ("preset", "rules"),
    [
        ("read-only", (read_only("/"),)),
        ("workspace-write", (read_only("/"), allow("."))),
        ("danger-full-access", (allow("/"),)),
    ],
)
def test_a_preset_comes_to_its_rules_ahead_of_the_granular_ones(
    preset: str, rules: tuple[Rule, ...]
) -> None:
    granted = Permission(preset=preset, granular=[deny("~/.ssh")])  # pyright: ignore[reportArgumentType]
    assert granted.granular == (deny("~/.ssh"),)
    assert granted.rules == (*rules, deny("~/.ssh"))


@pytest.mark.parametrize(
    ("given", "error", "says"),
    [
        ({"preset": "workspace"}, ValueError, "preset is one of"),
        ({"network": 1}, TypeError, "network is a bool"),
        ({"network": "yes"}, TypeError, "network is a bool"),
        ({"granular": (("~/.ssh", "none"),)}, TypeError, "is not a Rule"),
    ],
)
def test_a_permission_refuses_what_is_not_one(
    given: dict[str, Any], error: type[Exception], says: str
) -> None:
    with pytest.raises(error, match=says):
        Permission(**given)


def test_a_permission_cannot_be_changed() -> None:
    granted = Permission()
    with pytest.raises(dataclasses.FrozenInstanceError):
        granted.network = False  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize(
    ("granted", "path", "access"),
    [
        (Permission(), ".", WRITE),
        (Permission(), "./src/x", WRITE),
        (Permission(), "~", READ),
        (Permission(), "/etc", READ),
        (Permission(preset="read-only"), ".", READ),
        (Permission(preset="danger-full-access"), "~/x", WRITE),
        # The last rule that matches decides, deeper or not.
        (Permission(granular=(deny("~/.ssh"),)), "~/.ssh/id", NONE),
        (Permission(granular=(deny("~/.ssh"),)), "~/.sshx", READ),
        (Permission(granular=(deny("~/a/b"), read_only("~/a"))), "~/a/b", READ),
        (Permission(granular=(read_only("./out"),)), "./out", READ),
        (Permission(preset="read-only", granular=(allow("./"),)), ".", WRITE),
        # `~` and `.` are not resolved: an absolute rule does not reach them.
        (Permission(preset="read-only", granular=(deny("/home"),)), "~", READ),
        (Permission(preset="read-only", granular=(deny("/srv"),)), "/srv//x/", NONE),
    ],
)
def test_a_permission_gives_a_path_the_access_of_the_last_rule_matching_it(
    granted: Permission, path: str, access: Access
) -> None:
    assert granted.access(path) is access


def test_a_path_no_rule_matches_is_not_touched_and_one_no_rule_could_name_is_refused() -> (
    None
):
    granted = Permission(preset="read-only", granular=(deny("/"), read_only("~")))
    assert granted.access("/etc") is NONE
    assert granted.access("~/x") is READ
    with pytest.raises(ValueError, match="a rule's path is"):
        granted.access("src")


@pytest.mark.parametrize(
    "granted",
    [
        Permission(),
        Permission(preset="read-only", network=False),
        Permission(
            preset="danger-full-access", granular=(deny("~/.ssh"), allow("~/.ssh/x"))
        ),
        Permission(granular=(deny("/tmp"), read_only("./out"), allow("/srv"))),
    ],
)
def test_a_permission_covers_itself(granted: Permission) -> None:
    assert granted.covers(granted)


@pytest.mark.parametrize(
    ("wide", "narrow", "covers"),
    [
        (Permission(), Permission(), True),
        (Permission(), Permission(preset="read-only"), True),
        (Permission(preset="read-only"), Permission(), False),
        (Permission(network=False), Permission(), False),
        (Permission(), Permission(network=False), True),
        (Permission(preset="danger-full-access"), Permission(), True),
        (Permission(), Permission(preset="danger-full-access"), False),
        (Permission(preset="danger-full-access", network=False), Permission(), False),
        # A carve-out narrows: the wider holds the narrower, never the other way.
        (Permission(), Permission(granular=(deny("~/.ssh"),)), True),
        (Permission(granular=(deny("~/.ssh"),)), Permission(), False),
        (Permission(), Permission(granular=(allow("~/.cache"),)), False),
        (
            Permission(granular=(allow("~"),)),
            Permission(granular=(allow("~/.cache"),)),
            True,
        ),
        # The same rules said another way still cover.
        (
            Permission(preset="read-only", granular=(allow("."),)),
            Permission(),
            True,
        ),
        (
            Permission(),
            Permission(
                preset="danger-full-access", granular=(read_only("/"), allow("."))
            ),
            True,
        ),
    ],
)
def test_a_permission_covers_another_only_at_every_path_and_on_the_network(
    wide: Permission, narrow: Permission, covers: bool
) -> None:
    assert wide.covers(narrow) is covers


@pytest.mark.parametrize(
    ("wide", "narrow"),
    [
        # The workdir may lie beneath `/srv`, which the wider reads and does not write.
        (Permission(granular=(read_only("/srv"),)), Permission()),
        # ... or beneath the home, which the wider keeps out of.
        (Permission(granular=(deny("~"),)), Permission()),
        # The home may lie beneath `/home`, which the wider keeps out of.
        (
            Permission(granular=(deny("/home"),)),
            Permission(granular=(read_only("~/x"),)),
        ),
        # The home may lie inside the workdir, or the workdir inside the home: either way
        # the narrower writes what the wider only reads.
        (Permission(granular=(read_only("~"),)), Permission()),
        # The workdir may lie beneath `/tmp`, which the wider keeps out of.
        (Permission(granular=(deny("/tmp"),)), Permission()),
    ],
)
def test_a_permission_does_not_cover_one_wider_wherever_the_anchors_might_lie(
    wide: Permission, narrow: Permission
) -> None:
    assert not wide.covers(narrow)


@pytest.mark.parametrize(
    ("wide", "narrow", "covers"),
    [
        # A workdir it may write writes the temporary directories, whatever the rules say of
        # them -- but a rule beneath one still takes that much away.
        (Permission(granular=(deny("/tmp"), allow("."))), Permission(), True),
        (Permission(granular=(deny("/tmp/x"),)), Permission(), False),
        (Permission(), Permission(granular=(deny("/tmp/x"),)), True),
        # A permission that does not write its workdir writes no temporary directory.
        (
            Permission(preset="read-only"),
            Permission(preset="read-only", granular=(allow("/tmp"),)),
            False,
        ),
        (
            Permission(preset="read-only", granular=(allow("/tmp"), allow("/var/tmp"))),
            Permission(),
            False,
        ),
    ],
)
def test_the_temporary_directories_are_compared_as_the_workdir_grants_them(
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
    assert Budget(cost=1).graces == Graceful()


def test_a_budget_is_graceful_limit_by_limit() -> None:
    budget = Budget(cost=1, graceful=Graceful(cost=False))

    assert budget.graces == Graceful(duration=True, cost=False, output_tokens=True)
    assert Budget(cost=1, graceful=False).graces == Graceful(
        duration=False, cost=False, output_tokens=False
    )
    assert Budget.model_validate_json(budget.model_dump_json()) == budget
    assert Budget.model_validate({"cost": 1, "graceful": {"cost": False}}) == budget


@pytest.mark.parametrize("flag", [True, False])
def test_a_budget_reads_three_graces_that_agree_as_one(flag: bool) -> None:
    graces = Graceful(duration=flag, cost=flag, output_tokens=flag)

    assert Budget(cost=1, graceful=graces).graceful is flag


def test_graceful_refuses_a_limit_it_does_not_know() -> None:
    with pytest.raises(pydantic.ValidationError):
        Graceful.model_validate({"turns": False})


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
        (HarnessKind.OMP, OhMyPiAgent, {SteeringAgentMixin, AskUserHookAgentMixin}),
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
