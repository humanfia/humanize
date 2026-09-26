"""What `-a`, `-e`, `-p` and `-b` say, read the way `hmz exec` reads them."""

from __future__ import annotations

import datetime
import math
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends
from hmz.flows import Budget, EnvBackendKind, HarnessKind
from hmz.runtime.flowing.specs import (
    AgentSpec,
    AgentSpecError,
    BudgetSpecError,
    EnvSpec,
    EnvSpecError,
    ParamSpecError,
    SpecError,
    parse_agents,
    parse_budget,
    parse_duration,
    parse_envs,
    parse_params,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# ------------------------------------------------------------------------------------ -a


def test_an_agent_is_a_role_a_harness_a_model_and_an_effort() -> None:
    assert parse_agents(["coder=claude/opus:high"]) == [
        AgentSpec("coder", HarnessKind.CLAUDE, "", "opus", "high", "claude")
    ]


def test_an_agent_may_run_as_an_account() -> None:
    (spec,) = parse_agents(["reviewer=codex@work/gpt-5:medium"])
    assert (spec.harness, spec.provider, spec.model, spec.effort) == (
        HarnessKind.CODEX,
        "work",
        "gpt-5",
        "medium",
    )


def test_a_model_may_hold_slashes_and_auto_is_no_effort() -> None:
    (spec,) = parse_agents(["coder=opencode/openrouter/qwen/qwen3-coder:auto"])
    assert (spec.harness, spec.model, spec.effort) == (
        HarnessKind.OPENCODE,
        "openrouter/qwen/qwen3-coder",
        "",
    )


@pytest.mark.parametrize(
    "kind", [one for one in HarnessKind if one is not HarnessKind.ACP]
)
def test_every_harness_is_read_as_its_own_kind(kind: HarnessKind) -> None:
    (spec,) = parse_agents([f"worker={kind.value}/model:high"])
    assert spec.harness is kind
    assert spec.cli == kind.value


def test_a_cli_added_by_hand_is_acp_and_keeps_its_name() -> None:
    backends.remember("my-agent", ["my-agent", "--acp"])
    (spec,) = parse_agents(["worker=my-agent/some-model:auto"])
    assert (spec.harness, spec.cli, spec.model) == (
        HarnessKind.ACP,
        "my-agent",
        "some-model",
    )


def test_agents_come_in_lists_and_in_repeated_flags_in_the_order_written() -> None:
    specs = parse_agents(
        [
            "coder=claude/opus:high,reviewer=codex/gpt-5:low",
            "planner=kimi/k2:high",
        ]
    )
    assert [spec.role for spec in specs] == ["coder", "reviewer", "planner"]


def test_no_flags_is_no_agents() -> None:
    assert parse_agents([]) == []


@pytest.mark.parametrize(
    ("written", "says"),
    [
        ("claude/opus:high", "expected <role>="),
        ("=claude/opus:high", "expected <role>="),
        ("coder=nothing/opus:high", "expected"),
        ("coder=claude/opus", "expected"),
        ("coder=claude@/opus:high", "account"),
        ("my-role=claude/opus:high", "identifier"),
        ("coder=claude/opus:high,codex/gpt-5:high", "expected one agent"),
        ("coder=claude/opus:high,", "expected one agent"),
    ],
)
def test_what_is_not_an_agent_is_refused_saying_why(written: str, says: str) -> None:
    with pytest.raises(AgentSpecError, match=says) as raised:
        parse_agents([written])
    assert written in str(raised.value) or "-a" in str(raised.value)


def test_a_role_given_twice_is_refused() -> None:
    with pytest.raises(AgentSpecError, match="twice"):
        parse_agents(["coder=claude/opus:high", "coder=codex/gpt-5:high"])


@pytest.mark.parametrize(
    ("parse", "refused", "written"),
    [
        (parse_agents, AgentSpecError, ""),
        (parse_envs, EnvSpecError, " "),
        (parse_params, ParamSpecError, ""),
        (parse_budget, BudgetSpecError, ",cost=1"),
    ],
    ids=["-a", "-e", "-p", "-b"],
)
def test_an_empty_item_is_refused_as_that_flag(
    parse: Callable[[list[str]], object], refused: type[SpecError], written: str
) -> None:
    with pytest.raises(refused, match="empty"):
        parse([written])


def test_a_space_after_a_comma_still_separates_two_items() -> None:
    assert parse_params(["a=1, b=2"]) == {"a": "1", "b": "2"}
    assert [spec.role for spec in parse_envs(["a=local@/x,  b=local@/y"])] == ["a", "b"]
    assert [spec.role for spec in parse_agents(["a=claude/m:high, b=codex/m:low"])] == [
        "a",
        "b",
    ]


@pytest.mark.parametrize(
    "written",
    [
        "coder=claude/opus:high",
        "coder=claude@work/opus:auto",
        "coder=opencode/openrouter/qwen/qwen3-coder:high",
    ],
)
def test_an_agent_is_written_back_as_it_is_read(written: str) -> None:
    (spec,) = parse_agents([written])
    assert parse_agents([str(spec)]) == [spec]


# ------------------------------------------------------------------------------------ -e


@pytest.mark.parametrize(
    ("written", "spec"),
    [
        (
            "repo=local@/home/me/repo",
            EnvSpec("repo", EnvBackendKind.LOCAL, "", PurePosixPath("/home/me/repo")),
        ),
        (
            "repo=local/home/me/repo",
            EnvSpec("repo", EnvBackendKind.LOCAL, "", PurePosixPath("/home/me/repo")),
        ),
        (
            "repo=ssh@gpu-box/home/me/repo",
            EnvSpec(
                "repo", EnvBackendKind.SSH, "gpu-box", PurePosixPath("/home/me/repo")
            ),
        ),
        (
            "repo=ssh@me@gpu-box/srv/x",
            EnvSpec("repo", EnvBackendKind.SSH, "me@gpu-box", PurePosixPath("/srv/x")),
        ),
        (
            "repo=ssh@gpu-box/~/repo",
            EnvSpec("repo", EnvBackendKind.SSH, "gpu-box", PurePosixPath("~/repo")),
        ),
        (
            "home=ssh@gpu-box/~",
            EnvSpec("home", EnvBackendKind.SSH, "gpu-box", PurePosixPath("~")),
        ),
        ("root=local@/", EnvSpec("root", EnvBackendKind.LOCAL, "", PurePosixPath("/"))),
        (
            " spaced = local@/tmp/x ",
            EnvSpec("spaced", EnvBackendKind.LOCAL, "", PurePosixPath("/tmp/x")),
        ),
    ],
)
def test_an_environment_is_a_role_a_backend_a_host_and_a_workdir(
    written: str, spec: EnvSpec
) -> None:
    assert parse_envs([written]) == [spec]


def test_environments_come_in_lists_and_in_repeated_flags() -> None:
    specs = parse_envs(["a=local@/x,b=ssh@h/y", "c=local@/z"])
    assert [spec.role for spec in specs] == ["a", "b", "c"]


def test_a_workdir_may_hold_commas_where_no_key_follows() -> None:
    (spec,) = parse_envs(["repo=local@/data/a,b,c"])
    assert spec.workdir == PurePosixPath("/data/a,b,c")


@pytest.mark.parametrize(
    ("written", "says"),
    [
        ("local@/x", "expected"),
        ("repo=local", "expected"),
        ("repo=ssh@host", "expected"),
        ("repo=docker@/x", "not a backend"),
        ("repo=ssh@/x", "needs a host"),
        ("repo=ssh/x", "needs a host"),
        ("repo=local@box/x", "takes no provider"),
        ("my-repo=local@/x", "identifier"),
        ("=local@/x", "identifier"),
    ],
)
def test_what_is_not_an_environment_is_refused_saying_why(
    written: str, says: str
) -> None:
    with pytest.raises(EnvSpecError, match=says):
        parse_envs([written])


def test_an_environment_role_given_twice_is_refused() -> None:
    with pytest.raises(EnvSpecError, match="twice"):
        parse_envs(["repo=local@/x", "repo=local@/y"])


@pytest.mark.parametrize(
    "written",
    ["repo=local@/home/me", "repo=ssh@h/srv/x", "repo=ssh@me@h/~/x", "repo=local@/"],
)
def test_an_environment_is_written_back_as_it_is_read(written: str) -> None:
    (spec,) = parse_envs([written])
    assert str(spec) == written
    assert parse_envs([str(spec)]) == [spec]


# ------------------------------------------------------------------------------------ -p


def test_params_are_keys_and_the_values_as_written() -> None:
    assert parse_params(["rounds=3", "name= spaced out ", "empty="]) == {
        "rounds": "3",
        "name": " spaced out ",
        "empty": "",
    }


def test_a_value_keeps_its_commas_and_equals_signs_until_a_key_follows() -> None:
    assert parse_params(["tags=a,b,c,query=x=y,dashed-key=1"]) == {
        "tags": "a,b,c",
        "query": "x=y",
        "dashed-key": "1",
    }


@pytest.mark.parametrize("written", ["rounds", "=3", "9lives=1", "a b=1"])
def test_what_is_not_a_param_is_refused(written: str) -> None:
    with pytest.raises(ParamSpecError, match="expected <key>=<value>"):
        parse_params([written])


def test_a_param_given_twice_is_refused() -> None:
    with pytest.raises(ParamSpecError, match="twice"):
        parse_params(["rounds=3,rounds=4"])


# ------------------------------------------------------------------------------------ -b


@pytest.mark.parametrize(
    ("written", "seconds"),
    [
        ("90", 90),
        ("1.5", 1.5),
        ("0", 0),
        ("90s", 90),
        ("30m", 1800),
        ("1h30m", 5400),
        ("1H30M", 5400),
        ("2d", 172800),
        ("1w", 604800),
        ("1.5h", 5400),
        ("1d2h3m4s", 93784),
        ("PT1H30M", 5400),
        ("P2D", 172800),
        ("P1DT2H", 93600),
        ("01:30:00", 5400),
    ],
)
def test_a_duration_is_written_however_a_person_writes_one(
    written: str, seconds: float
) -> None:
    assert parse_duration(written) == datetime.timedelta(seconds=seconds)


@pytest.mark.parametrize(
    "written",
    ["", "soon", "1h1h", "-5", "-PT1H", "inf", "nan", "1e400", "h", "1x", "1h 30m"],
)
def test_what_is_not_a_duration_is_refused(written: str) -> None:
    with pytest.raises(ValueError, match=r"\w"):
        parse_duration(written)


def test_a_budget_is_every_limit_across_every_flag() -> None:
    assert parse_budget(["duration=1h30m,cost=5", "output_tokens=200k"]) == Budget(
        duration=datetime.timedelta(hours=1, minutes=30),
        cost=5,
        output_tokens=200_000,
    )


@pytest.mark.parametrize(
    ("written", "budget"),
    [
        ("cost=$2.50", Budget(cost=2.5)),
        ("cost=inf", Budget(cost=math.inf)),
        ("cost=0", Budget(cost=0)),
        ("output_tokens=1_000", Budget(output_tokens=1000)),
        ("output_tokens=1.5M", Budget(output_tokens=1_500_000)),
        ("output_tokens=2K", Budget(output_tokens=2000)),
        ("output_tokens=1.001k", Budget(output_tokens=1001)),
        ("output_tokens=1.015k", Budget(output_tokens=1015)),
        (
            "output_tokens=12345678901234567",
            Budget(output_tokens=12345678901234567),
        ),
        ("cost=1,graceful=false", Budget(cost=1, graceful=False)),
        ("cost=1,graceful=yes", Budget(cost=1, graceful=True)),
        ("duration=90", Budget(duration=datetime.timedelta(seconds=90))),
    ],
)
def test_each_limit_is_read_as_a_person_writes_it(written: str, budget: Budget) -> None:
    assert parse_budget([written]) == budget


@pytest.mark.parametrize(
    ("written", "says"),
    [
        (["graceful=false"], "at least one"),
        (["hours=2"], "expected one of"),
        (["cost"], "expected one of"),
        (["cost=1", "cost=2"], "twice"),
        (["cost=-1"], "cost"),
        (["cost=nan"], "cost"),
        (["cost=free"], "cost"),
        (["output_tokens=1.5"], "whole number"),
        (["output_tokens=lots"], "tokens"),
        (["duration=soon"], "duration"),
        (["cost=1,graceful=maybe"], "true or false"),
    ],
)
def test_what_is_not_a_budget_is_refused_saying_why(
    written: list[str], says: str
) -> None:
    with pytest.raises(BudgetSpecError, match=says):
        parse_budget(written)


def test_every_spec_error_is_a_value_error() -> None:
    for kind in (AgentSpecError, EnvSpecError, ParamSpecError, BudgetSpecError):
        assert issubclass(kind, SpecError)
        assert issubclass(kind, ValueError)
