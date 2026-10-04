"""What `-a`, `-e` and `-p` say -- a budget among the last --, read as `hmz exec` reads them."""

from __future__ import annotations

import datetime
import math
import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends
from hmz.coganchor.machines import store
from hmz.coganchor.machines.store import DockerRuntime, SSHRuntime, SwarmRuntime
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
        ("coder=claude/:high", "expected"),
        ("coder=claude", "expected"),
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
        (parse_budget, ParamSpecError, ",budget.cost=1"),
    ],
    ids=["-a", "-e", "-p", "-p budget"],
)
def test_an_empty_item_is_refused_as_that_flag(
    parse: Callable[[list[str]], object], refused: type[SpecError], written: str
) -> None:
    with pytest.raises(refused, match="empty"):
        parse([written])


def test_a_space_after_a_comma_still_separates_two_items() -> None:
    assert parse_params(["a=1, b=2"]) == {"a": "1", "b": "2"}
    assert [spec.role for spec in parse_envs(["a=local/x,  b=local/y"])] == ["a", "b"]
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
        "coder=claude/opus",
        "coder=mcode@loopback/custom_provider:gateway/mock/first-model",
        "coder=mcode/custom_provider:gateway/mock/first-model:high",
        "coder=opencode/ollama/qwen3:latest:auto",
    ],
)
def test_an_agent_is_written_back_as_it_is_read(written: str) -> None:
    (spec,) = parse_agents([written])
    assert parse_agents([str(spec)]) == [spec]
    assert str(parse_agents([str(spec)])[0]) == str(spec)


@pytest.mark.parametrize(
    ("written", "model", "effort"),
    [
        # MiniMax Code's own spelling of a model a provider of its config serves.
        (
            "mcode@loopback/custom_provider:gateway/mock/first-model",
            "custom_provider:gateway/mock/first-model",
            "",
        ),
        (
            "mcode/custom_provider:gateway/mock/first-model:xhigh",
            "custom_provider:gateway/mock/first-model",
            "xhigh",
        ),
        ("opencode/ollama/qwen3:8b", "ollama/qwen3:8b", ""),
        ("opencode/ollama/qwen3:latest:auto", "ollama/qwen3:latest", ""),
        ("opencode/openrouter/some:model:low", "openrouter/some:model", "low"),
        ("claude/claude-haiku-4-5", "claude-haiku-4-5", ""),
        ("claude/claude-haiku-4-5:", "claude-haiku-4-5", ""),
        ("kimi/kimi-code/k3:swarmmax", "kimi-code/k3", "swarmmax"),
        ("cursor-agent/gpt-5.2:extra-high", "gpt-5.2", "extra-high"),
    ],
)
def test_an_effort_is_only_what_is_spelled_as_one(
    written: str, model: str, effort: str
) -> None:
    """The last `:` sets an effort off only where a word follows it; a model keeps the rest."""
    (spec,) = parse_agents([f"coder={written}"])
    assert (spec.model, spec.effort) == (model, effort)


# ------------------------------------------------------------------------------------ -e


@pytest.fixture
def saved() -> None:
    """A runtime of each backend saved here, each under a name an `-e` may name it by."""
    store.add(SSHRuntime(name="gpu-box", host="10.0.0.2"))
    store.add(DockerRuntime(name="gpubox"))
    store.add(SwarmRuntime(name="cluster"))


@pytest.mark.usefixtures("saved")
@pytest.mark.parametrize(
    ("written", "spec"),
    [
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
            "repo=ssh@[me@gpu-box:2222]/srv/x",
            EnvSpec(
                "repo",
                EnvBackendKind.SSH,
                "[me@gpu-box:2222]",
                PurePosixPath("/srv/x"),
            ),
        ),
        (
            "repo=ssh@gpu-box/~/repo",
            EnvSpec("repo", EnvBackendKind.SSH, "gpu-box", PurePosixPath("~/repo")),
        ),
        (
            "home=ssh@[gpu-box]/~",
            EnvSpec("home", EnvBackendKind.SSH, "[gpu-box]", PurePosixPath("~")),
        ),
        ("root=local/", EnvSpec("root", EnvBackendKind.LOCAL, "", PurePosixPath("/"))),
        (
            "box=docker@gpubox/srv/x",
            EnvSpec("box", EnvBackendKind.DOCKER, "gpubox", PurePosixPath("/srv/x")),
        ),
        (
            "box=docker/tmp/x",
            EnvSpec("box", EnvBackendKind.DOCKER, "", PurePosixPath("/tmp/x")),
        ),
        (
            "box=swarm@cluster/srv/x",
            EnvSpec("box", EnvBackendKind.SWARM, "cluster", PurePosixPath("/srv/x")),
        ),
        (
            "box=swarm/tmp/x",
            EnvSpec("box", EnvBackendKind.SWARM, "", PurePosixPath("/tmp/x")),
        ),
        (
            " spaced = local/tmp/x ",
            EnvSpec("spaced", EnvBackendKind.LOCAL, "", PurePosixPath("/tmp/x")),
        ),
    ],
)
def test_an_environment_is_a_role_a_backend_a_provider_and_a_workdir(
    written: str, spec: EnvSpec
) -> None:
    assert parse_envs([written]) == [spec]


def test_environments_come_in_lists_and_in_repeated_flags() -> None:
    specs = parse_envs(["a=local/x,b=ssh@[h]/y", "c=local/z"])
    assert [spec.role for spec in specs] == ["a", "b", "c"]


def test_a_workdir_may_hold_commas_where_no_key_follows() -> None:
    (spec,) = parse_envs(["repo=local/data/a,b,c"])
    assert spec.workdir == PurePosixPath("/data/a,b,c")


def test_a_saved_runtime_alone_is_the_workdir_it_was_saved_with() -> None:
    store.add(SSHRuntime(name="gpu", host="h", workdir="/srv/proj"))
    assert parse_envs(["repo=ssh@gpu"])[0].workdir == PurePosixPath("/srv/proj")


@pytest.mark.usefixtures("saved")
@pytest.mark.parametrize(
    ("written", "says"),
    [
        ("local/x", "expected"),
        ("repo=local", "expected"),
        ("repo=ssh@gpu-box", "left off only for a runtime saved with one"),
        ("repo=ssh@[h]", "left off only"),
        ("repo=docker", "left off only"),
        ("repo=docker@gpubox", "left off only"),
        ("repo=podman/x", "not a backend"),
        ("repo=ssh/x", "ssh needs a host"),
        ("repo=ssh@/x", "ssh needs a host"),
        ("repo=ssh@[]/x", "not an ssh host"),
        ("repo=ssh@[-oProxy=x]/x", "not an ssh host"),
        ("repo=ssh@[a b]/x", "not an ssh host"),
        ("repo=ssh@[h/x", "expected"),
        ("repo=ssh@h]/x", "expected"),
        ("repo=docker@[h]/x", "only ssh takes a host nobody saved"),
        ("repo=swarm@[h]/x", "only ssh takes a host nobody saved"),
        ("repo=apple-container@[h]/x", "only ssh takes a host nobody saved"),
        ("repo=local@[h]/x", "local takes no provider"),
        ("repo=docker@ghost/x", "no docker runtime is saved as 'ghost'"),
        ("repo=swarm@ghost/x", "no swarm runtime is saved as 'ghost'"),
        ("repo=local@box/x", "local takes no provider"),
        ("my-repo=local/x", "identifier"),
        ("=local/x", "identifier"),
    ],
)
def test_what_is_not_an_environment_is_refused_saying_why(
    written: str, says: str
) -> None:
    with pytest.raises(EnvSpecError, match=re.escape(says)):
        parse_envs([written])


@pytest.mark.parametrize(
    ("written", "hint"),
    [
        ("r=local@/tmp/x", "write r=local/tmp/x"),
        ("r=docker@local/w", "write r=docker/w"),
        ("r=docker@/w", "write r=docker/w"),
        ("r=swarm@local/w", "write r=swarm/w"),
        ("r=apple-container@local/w", "write r=apple-container/w"),
        ("r=ssh@somehost/x", "write r=ssh@[somehost]/x for a host not saved"),
        ("r=ssh@me@host:2222/~/x", "write r=ssh@[me@host:2222]/~/x"),
        ("r=ssh@somehost", "write r=ssh@[somehost]/<workdir>"),
    ],
)
def test_the_old_spelling_is_refused_saying_how_it_is_spelled_now(
    written: str, hint: str
) -> None:
    with pytest.raises(EnvSpecError, match=re.escape(hint)):
        parse_envs([written])


def test_a_runtime_saved_as_local_is_still_one_to_name() -> None:
    store.add(DockerRuntime(name="local"))
    (spec,) = parse_envs(["box=docker@local/w"])
    assert spec.provider == "local"


def test_a_runtime_saved_under_a_hosts_name_is_that_runtime_and_brackets_are_the_host() -> (
    None
):
    store.add(SSHRuntime(name="gpu-box", host="10.0.0.2"))
    assert parse_envs(["a=ssh@gpu-box/x"])[0].provider == "gpu-box"
    assert parse_envs(["a=ssh@[gpu-box]/x"])[0].provider == "[gpu-box]"


def test_an_environment_role_given_twice_is_refused() -> None:
    with pytest.raises(EnvSpecError, match="twice"):
        parse_envs(["repo=local/x", "repo=local/y"])


@pytest.mark.usefixtures("saved")
@pytest.mark.parametrize(
    "written",
    [
        "repo=local/home/me",
        "repo=ssh@gpu-box/srv/x",
        "repo=ssh@[me@h]/~/x",
        "repo=local/",
        "repo=docker@gpubox/srv/x",
        "repo=docker/srv/x",
        "repo=swarm@cluster/srv/x",
        "repo=swarm/srv/x",
        "repo=apple-container/Users/me/x",
    ],
)
def test_an_environment_is_written_back_as_it_is_read(written: str) -> None:
    (spec,) = parse_envs([written])
    assert str(spec) == written
    assert parse_envs([str(spec)]) == [spec]


@pytest.mark.parametrize(
    ("kept", "now"),
    [
        ("local@/home/me", "local/home/me"),
        ("docker@local/srv/x", "docker/srv/x"),
        ("swarm@local/srv/x", "swarm/srv/x"),
        ("apple-container@local/srv/x", "apple-container/srv/x"),
        ("ssh@me@h:2222/~/x", "ssh@[me@h:2222]/~/x"),
        ("ssh@unsaved/srv", "ssh@[unsaved]/srv"),
        ("ssh@gpu-box/srv", "ssh@gpu-box/srv"),
        ("ssh@gpu-box", "ssh@gpu-box"),
        ("docker@gpubox/srv/x", "docker@gpubox/srv/x"),
        ("local/home/me", "local/home/me"),
        ("docker/srv/x", "docker/srv/x"),
        ("ssh@[h]/x", "ssh@[h]/x"),
        ("nonsense", "nonsense"),
    ],
)
@pytest.mark.usefixtures("saved")
def test_what_was_kept_the_old_way_is_respelled_as_e_takes_it_now(
    kept: str, now: str
) -> None:
    assert store.respelled(kept) == now


def test_docker_here_kept_the_old_way_is_a_runtime_saved_as_local_where_there_is_one() -> (
    None
):
    store.add(DockerRuntime(name="local"))
    assert store.respelled("docker@local/x") == "docker@local/x"


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


def test_the_budget_is_not_a_param_of_the_flows() -> None:
    assert parse_params(["rounds=3,budget.cost=5", "budget.duration=1h"]) == {
        "rounds": "3"
    }


@pytest.mark.parametrize(
    ("written", "says"),
    [
        (["budget=5"], "a budget is given a limit at a time"),
        (["budget.cost=1,budget.cost=2"], "'budget.cost' is given twice"),
        (["budget.cost.x=1"], "expected <key>=<value>"),
        (["a.b=1"], "expected <key>=<value>"),
    ],
)
def test_what_is_not_a_param_or_a_limit_is_refused_by_both(
    written: list[str], says: str
) -> None:
    for parse in (parse_params, parse_budget):
        with pytest.raises(ParamSpecError, match=re.escape(says)):
            parse(written)


# ---------------------------------------------------------------------- -p budget.<limit>


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
    assert parse_budget(
        ["budget.duration=1h30m,rounds=3,budget.cost=5", "budget.output_tokens=200k"]
    ) == Budget(
        duration=datetime.timedelta(hours=1, minutes=30),
        cost=5,
        output_tokens=200_000,
    )


def test_no_limit_is_no_budget() -> None:
    assert parse_budget(["rounds=3"]) is None
    assert parse_budget([]) is None


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
    assert parse_budget([re.sub(r"(^|,)", r"\1budget.", written)]) == budget


@pytest.mark.parametrize(
    ("written", "says"),
    [
        (["budget.graceful=false"], "at least one"),
        (["budget.hours=2"], "-p budget.hours: not a limit; one of budget.duration"),
        (["budget.cost=-1"], "-p budget.cost"),
        (["budget.cost=nan"], "-p budget.cost"),
        (["budget.cost=free"], "-p budget.cost"),
        (["budget.output_tokens=1.5"], "whole number"),
        (["budget.output_tokens=lots"], "tokens"),
        (["budget.duration=soon"], "-p budget.duration"),
        (["budget.cost=1,budget.graceful=maybe"], "true or false"),
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
