"""What `-a`, `-e` and `-p` say: `hmz.runtime.flowing.specs`, with coganchor's store mocked."""

from __future__ import annotations

import datetime
import math
from pathlib import PurePosixPath
from types import SimpleNamespace
from typing import Any

import pytest

from hmz.coganchor import backends
from hmz.coganchor.machines import store
from hmz.flows import Budget, EnvBackendKind, HarnessKind
from hmz.runtime.flowing.specs import (
    AgentSpec,
    AgentSpecError,
    BudgetSpecError,
    EnvSpec,
    EnvSpecError,
    ParamSpecError,
    SpecError,
    fallbacks,
    parse_agents,
    parse_budget,
    parse_duration,
    parse_envs,
    parse_params,
    spelled,
    where,
)


class Saved:
    """The runtimes coganchor's store holds, as a test writes them down."""

    def __init__(self) -> None:
        self.runtimes: dict[tuple[str, str], Any] = {}
        self.lists: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}

    def save(self, backend: str, name: str, workdir: str = "") -> None:
        self.runtimes[backend, name] = SimpleNamespace(workdir=workdir)


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> Saved:
    held = Saved()

    def is_saved(backend: str, name: str) -> bool:
        if name.startswith("!"):
            raise ValueError(name)
        return (backend, name) in held.runtimes

    monkeypatch.setattr(store, "saved", is_saved)

    def find(backend: str, name: str) -> Any:
        return held.runtimes.get((backend, name))

    def fallbacks(backend: str, name: str) -> tuple[tuple[str, str], ...]:
        return held.lists.get((backend, name), ())

    def respelled(spec: str) -> str:
        return f"<{spec}>"

    monkeypatch.setattr(store, "find", find)
    monkeypatch.setattr(store, "fallbacks", fallbacks)
    monkeypatch.setattr(store, "respelled", respelled)
    return held


# ------------------------------------------------------------------------------ -p


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], {}),
        (["rounds=3"], {"rounds": "3"}),
        (["rounds=3", "name=x"], {"rounds": "3", "name": "x"}),
        (["rounds=3,name=x"], {"rounds": "3", "name": "x"}),
        (["rounds=3, name=x"], {"rounds": "3", "name": "x"}),
        (["tags=a,b,c"], {"tags": "a,b,c"}),
        (["empty="], {"empty": ""}),
        (["eq=a=b"], {"eq": "a=b"}),
        (["rounds=3,budget.cost=5"], {"rounds": "3"}),
        (["my-key=1"], {"my-key": "1"}),
    ],
)
def test_parse_params_reads_each_key(
    values: list[str], expected: dict[str, str]
) -> None:
    assert parse_params(values) == expected


@pytest.mark.parametrize(
    ("values", "says"),
    [
        (["rounds"], "expected <key>=<value>"),
        (["=3"], "expected <key>=<value>"),
        (["1x=3"], "expected <key>=<value>"),
        ([""], "an item is empty"),
        (["budget=5"], "a limit at a time"),
        (["a=1", "a=2"], "given twice"),
    ],
)
def test_parse_params_refuses(values: list[str], says: str) -> None:
    with pytest.raises(ParamSpecError, match=says):
        parse_params(values)


def test_spec_errors_are_value_errors() -> None:
    for kind in (AgentSpecError, EnvSpecError, ParamSpecError, BudgetSpecError):
        assert issubclass(kind, SpecError)
    assert issubclass(SpecError, ValueError)
    assert issubclass(BudgetSpecError, ParamSpecError)


# ------------------------------------------------------------------------ durations


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("90", 90),
        ("1.5", 1.5),
        (" 0 ", 0),
        ("1h30m", 5400),
        ("2d", 172800),
        ("1w", 604800),
        ("90s", 90),
        ("1.5h", 5400),
        ("1H", 3600),
        ("PT1H30M", 5400),
        ("01:00:00", 3600),
    ],
)
def test_parse_duration_reads(text: str, seconds: float) -> None:
    assert parse_duration(text) == datetime.timedelta(seconds=seconds)


@pytest.mark.parametrize(
    ("text", "says"),
    [
        ("-5", "not a valid duration"),
        ("nan", "not a valid duration"),
        ("inf", "not a valid duration"),
        ("1h1h", "names a unit twice"),
        ("soon", "is not a duration"),
        ("-PT1H", "negative"),
        ("1e300", "too long"),
    ],
)
def test_parse_duration_refuses(text: str, says: str) -> None:
    with pytest.raises(ValueError, match=says):
        parse_duration(text)


# --------------------------------------------------------------------------- budget


def test_parse_budget_is_none_without_a_limit() -> None:
    assert parse_budget(["rounds=3"]) is None
    assert parse_budget([]) is None


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["budget.cost=5"], Budget(cost=5)),
        (["budget.cost=$2.5"], Budget(cost=2.5)),
        (["budget.cost=inf"], Budget(cost=math.inf)),
        (["budget.duration=1h"], Budget(duration=datetime.timedelta(hours=1))),
        (["budget.output_tokens=200k"], Budget(output_tokens=200_000)),
        (["budget.output_tokens=1.5m"], Budget(output_tokens=1_500_000)),
        (["budget.output_tokens=1_000"], Budget(output_tokens=1000)),
        (["budget.cost=1,budget.graceful=no"], Budget(cost=1, graceful=False)),
        (["budget.cost=1", "budget.graceful=ON"], Budget(cost=1, graceful=True)),
        (["rounds=3,budget.cost=1"], Budget(cost=1)),
    ],
)
def test_parse_budget_reads(values: list[str], expected: Budget) -> None:
    assert parse_budget(values) == expected


@pytest.mark.parametrize(
    ("values", "says"),
    [
        (["budget.speed=1"], "not a limit"),
        (["budget.cost=free"], "not a valid USD cost"),
        (["budget.cost=-1"], "not a valid USD cost"),
        (["budget.cost=nan"], "not a valid USD cost"),
        (["budget.output_tokens=lots"], "not a valid token count"),
        (["budget.output_tokens=1.0001k"], "whole number of tokens"),
        (["budget.graceful=maybe"], "true or false"),
        (["budget.duration=soon"], "budget.duration"),
        (["budget.graceful=yes"], "at least one of"),
    ],
)
def test_parse_budget_refuses(values: list[str], says: str) -> None:
    with pytest.raises(BudgetSpecError, match=says):
        parse_budget(values)


def test_parse_budget_refuses_an_unreadable_param_as_a_param() -> None:
    with pytest.raises(ParamSpecError):
        parse_budget(["nothing"])


# ------------------------------------------------------------------------------- -e


@pytest.mark.parametrize(
    ("value", "backend", "provider", "workdir"),
    [
        ("repo=local/tmp/x", EnvBackendKind.LOCAL, "", "/tmp/x"),
        ("box=docker/srv/x", EnvBackendKind.DOCKER, "", "/srv/x"),
        (
            "far=ssh@[me@far.host:2222]/srv/x",
            EnvBackendKind.SSH,
            "[me@far.host:2222]",
            "/srv/x",
        ),
        ("far=ssh@[alias]/~/repo", EnvBackendKind.SSH, "[alias]", "~/repo"),
        (" r = local/x ", EnvBackendKind.LOCAL, "", "/x"),
    ],
)
def test_parse_envs_reads_places_nobody_saved(
    saved: Saved, value: str, backend: EnvBackendKind, provider: str, workdir: str
) -> None:
    del saved
    (spec,) = parse_envs([value])
    assert (spec.backend, spec.provider, spec.workdir) == (
        backend,
        provider,
        PurePosixPath(workdir),
    )


def test_parse_envs_reads_a_saved_runtime_and_its_workdir(saved: Saved) -> None:
    saved.save("ssh", "gpu", "/home/me/repo")
    saved.save("docker", "box", "srv")
    specs = parse_envs(["a=ssh@gpu", "b=ssh@gpu/elsewhere,c=docker@box"])
    assert [(one.role, one.provider, str(one.workdir)) for one in specs] == [
        ("a", "gpu", "/home/me/repo"),
        ("b", "gpu", "/elsewhere"),
        ("c", "box", "/srv"),
    ]


def test_an_env_spec_is_written_back_as_it_was_read(saved: Saved) -> None:
    del saved
    (spec,) = parse_envs(["far=ssh@[me@host]/srv/x"])
    assert str(spec) == "far=ssh@[me@host]/srv/x"
    assert str(EnvSpec("r", EnvBackendKind.LOCAL, "", PurePosixPath("/x"))) == (
        "r=local/x"
    )


@pytest.mark.parametrize(
    ("value", "says"),
    [
        ("nothing", "expected"),
        ("1x=local/x", "not an identifier"),
        ("r=cloud/x", "not a backend"),
        ("r=local@/x", "local takes no provider"),
        ("r=docker@/x", "only before a provider"),
        ("r=docker@[host]/x", "only ssh takes a host nobody saved"),
        ("r=ssh@[-oProxy]/x", "not an ssh host"),
        ("r=ssh/x", "ssh needs a host"),
        ("r=ssh@gpu/x", "no ssh host is saved"),
        ("r=ssh@!bad/x", "no ssh host is saved"),
        ("r=docker@local/x", "names no provider"),
        ("r=docker@other/x", "no docker runtime is saved"),
        ("r=docker@a]b/x", "expected"),
        ("r=local", "may be left off"),
        ("r=local/x,r=local/y", "given twice"),
    ],
)
def test_parse_envs_refuses(saved: Saved, value: str, says: str) -> None:
    del saved
    with pytest.raises(EnvSpecError, match=says):
        parse_envs([value])


def test_parse_envs_refuses_an_empty_item(saved: Saved) -> None:
    del saved
    with pytest.raises(EnvSpecError, match="empty"):
        parse_envs([""])


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("local", "", "/x"), "local/x"),
        (("ssh", "[h]", "~/r"), "ssh@[h]/~/r"),
        (("docker", "box", ""), "docker@box"),
        (("docker", "", ""), "docker"),
    ],
)
def test_where_spells_a_place(args: tuple[str, str, str], expected: str) -> None:
    assert where(*args) == expected


def test_spelled_is_where_as_the_store_respells_it(saved: Saved) -> None:
    del saved
    assert spelled("docker", "local", "/x") == "<docker@local/x>"


def test_fallbacks_follow_the_saved_list(saved: Saved) -> None:
    saved.save("ssh", "gpu", "/w")
    saved.save("docker", "box", "/box")
    saved.lists["ssh", "gpu"] = (
        ("docker", "box"),
        ("docker", "local"),
        ("nonsense", "x"),
        ("ssh", "spare"),
    )
    spec = EnvSpec("r", EnvBackendKind.SSH, "gpu", PurePosixPath("/given"))
    assert fallbacks(spec) == [
        EnvSpec("r", EnvBackendKind.DOCKER, "box", PurePosixPath("/box")),
        EnvSpec("r", EnvBackendKind.DOCKER, "", PurePosixPath("/given")),
        EnvSpec("r", EnvBackendKind.SSH, "spare", PurePosixPath("/given")),
    ]


def test_fallbacks_are_none_for_a_place_nobody_saved(saved: Saved) -> None:
    del saved
    spec = EnvSpec("r", EnvBackendKind.LOCAL, "", PurePosixPath("/x"))
    assert fallbacks(spec) == []


# ------------------------------------------------------------------------------- -a


@pytest.fixture
def read(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`backends.read` as a stand-in: `<role>=<cli>[@<account>]/<model>[:<effort>]`."""
    asked: list[str] = []

    def stand_in(said: str) -> tuple[str, Any, str, str, str]:
        asked.append(said)
        role, _, rest = said.partition("=")
        cli, _, rest = rest.partition("/")
        cli, _, account = cli.partition("@")
        model, _, effort = rest.partition(":")
        if not model:
            raise ValueError("no model")
        return role.strip(), SimpleNamespace(name=cli), model, effort, account

    monkeypatch.setattr(backends, "read", stand_in)
    return asked


def test_parse_agents_reads_each_agent(read: list[str]) -> None:
    specs = parse_agents(["coder=claude/opus:high,reviewer=codex@work/gpt"])
    assert specs == [
        AgentSpec("coder", HarnessKind.CLAUDE, "", "opus", "high", "claude"),
        AgentSpec("reviewer", HarnessKind.CODEX, "work", "gpt", "", "codex"),
    ]
    assert read == ["coder=claude/opus:high", "reviewer=codex@work/gpt"]


def test_parse_agents_takes_a_cli_added_by_hand_as_acp(read: list[str]) -> None:
    del read
    (spec,) = parse_agents(["x=mine/m"])
    assert (spec.harness, spec.cli) == (HarnessKind.ACP, "mine")


@pytest.mark.parametrize(
    ("values", "says"),
    [
        (["claude/opus"], "expected <role>="),
        (["=claude/opus"], "expected <role>="),
        (["a=claude"], "no model"),
        (["a=claude/x", "a=codex/y"], "given twice"),
    ],
)
def test_parse_agents_refuses(read: list[str], values: list[str], says: str) -> None:
    del read
    with pytest.raises(AgentSpecError, match=says):
        parse_agents(values)


@pytest.mark.parametrize(
    ("spec", "written"),
    [
        (
            AgentSpec("a", HarnessKind.CLAUDE, "", "opus", "high", "claude"),
            "a=claude/opus:high",
        ),
        (
            AgentSpec("a", HarnessKind.CODEX, "w", "gpt", "", "codex"),
            "a=codex@w/gpt:auto",
        ),
    ],
)
def test_an_agent_spec_is_written_back(spec: AgentSpec, written: str) -> None:
    assert str(spec) == written
