"""`hmz.tui.pick`: which CLI serves a role, which agent a role opens on, and when one is set."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import hmz.coganchor.backends
import hmz.runtime.flowing
from hmz.coganchor.backends import Model
from hmz.flows import HarnessKind
from hmz.runtime.kept import Runs
from hmz.tui import pick
from tests.unit.tui import doubles_u14 as doubles

if TYPE_CHECKING:
    from pathlib import Path


class _Shell:
    pass


class _Files:
    pass


@pytest.fixture(autouse=True)
def harnesses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Claude does shell and files; codex shell alone; every other CLI is ACP, doing nothing."""
    monkeypatch.setattr(
        hmz.runtime.flowing,
        "HARNESS_CAPABILITIES",
        {
            HarnessKind.CLAUDE: frozenset({_Shell, _Files}),
            HarnessKind.CODEX: frozenset({_Shell}),
            HarnessKind.ACP: frozenset[type](),
        },
    )


@pytest.fixture(autouse=True)
def ready(monkeypatch: pytest.MonkeyPatch) -> set[str]:
    """Which backends open without further setup here: every one, until a test says not."""
    opens = {"claude", "codex", "mine"}

    def ready_to_open(backend: str, where: Path) -> bool:
        return backend in opens

    def written(effort: str) -> str:
        return effort or "auto"

    monkeypatch.setattr(pick, "ready_to_open", ready_to_open)
    monkeypatch.setattr(hmz.coganchor.backends, "written", written)
    return opens


@pytest.mark.parametrize(
    ("backend", "role", "answer"),
    [
        ("claude", None, True),
        ("anything", None, True),
        ("claude", doubles.role("r"), True),
        ("mine", doubles.role("r"), True),
        ("claude", doubles.role("r", HarnessKind.CLAUDE), True),
        ("codex", doubles.role("r", HarnessKind.CLAUDE), False),
        ("mine", doubles.role("r", HarnessKind.ACP), True),
        ("claude", doubles.role("r", capabilities=frozenset({_Shell, _Files})), True),
        ("codex", doubles.role("r", capabilities=frozenset({_Shell, _Files})), False),
        ("codex", doubles.role("r", capabilities=frozenset({_Shell})), True),
        ("mine", doubles.role("r", capabilities=frozenset({_Shell})), False),
    ],
)
def test_serves_asks_the_harness_and_what_it_can_do(
    backend: str, role: hmz.runtime.flowing.AgentRole | None, answer: bool
) -> None:
    assert pick.serves(backend, role) is answer


@pytest.mark.parametrize(
    ("efforts", "spec"),
    [
        (("max", "high", "low"), "claude/opus:high"),
        (("max", "medium", "low"), "claude/opus:low"),
        ((), "claude/opus:auto"),
    ],
)
def test_opens_on_the_first_model_at_high_or_its_least(
    efforts: tuple[str, ...], spec: str
) -> None:
    agents = {"claude": (Model("opus", efforts), Model("sonnet", ("high",)))}

    assert pick.opens_on(agents) == [Runs(spec)]


def test_opens_on_skips_a_backend_that_said_nothing_or_will_not_open(
    ready: set[str],
) -> None:
    ready.discard("codex")
    agents = {
        "claude": (),
        "codex": (Model("gpt", ("high",)),),
        "mine": (Model("m", ("high",)),),
    }

    assert pick.opens_on(agents) == [Runs("mine/m:high")]


def test_opens_on_skips_a_backend_that_cannot_fill_the_role() -> None:
    agents = {"mine": (Model("m", ()),), "codex": (Model("gpt", ("high",)),)}

    assert pick.opens_on(
        agents, doubles.role("r", capabilities=frozenset({_Shell}))
    ) == [Runs("codex/gpt:high")]


def test_opens_on_nothing_where_nothing_will_do(ready: set[str]) -> None:
    ready.clear()

    assert pick.opens_on({"claude": (Model("opus", ("high",)),)}) == []
    assert pick.opens_on({}) == []


def test_opens_on_asks_whether_a_backend_opens_where_this_is(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[Path] = []

    def opens(backend: str, where: Path) -> bool:
        asked.append(where)
        return True

    monkeypatch.setattr(pick, "ready_to_open", opens)
    monkeypatch.chdir(tmp_path)

    pick.opens_on({"claude": (Model("opus", ("high",)),)})

    assert asked == [tmp_path]


def test_settled_keeps_what_was_remembered_in_the_flows_order() -> None:
    roles = [doubles.role("b"), doubles.role("a")]
    runs = {
        "a": Runs("codex/gpt:low"),
        "b": Runs("claude/opus:max", "work"),
        "old": Runs("x/y"),
    }

    held = pick.settled(runs, roles)

    assert list(held.items()) == [("b", runs["b"]), ("a", runs["a"])]


def test_settled_leaves_a_new_role_unanswered_with_nothing_to_fall_back_on() -> None:
    assert pick.settled({}, [doubles.role("a")]) == {}


def test_settled_falls_back_for_a_new_role_on_an_agent_that_serves_it() -> None:
    agents = {"mine": (Model("m", ("high",)),), "claude": (Model("opus", ("high",)),)}
    roles = [doubles.role("kept"), doubles.role("new", HarnessKind.CLAUDE)]

    held = pick.settled({"kept": Runs("codex/gpt:low")}, roles, agents)

    assert held == {"kept": Runs("codex/gpt:low"), "new": Runs("claude/opus:high")}


def test_settled_leaves_a_role_unanswered_where_no_agent_serves_it() -> None:
    agents = {"codex": (Model("gpt", ("high",)),)}

    assert pick.settled({}, [doubles.role("r", HarnessKind.CLAUDE)], agents) == {}


@pytest.mark.parametrize(
    ("spec", "answer"),
    [
        ("claude/opus:high", True),
        ("claude/opus", True),
        ("opencode/provider/model:low", True),
        ("claude/", False),
        ("claude/:high", False),
        ("", False),
        ("/opus:high", False),
    ],
)
def test_complete_needs_a_cli_and_a_model(spec: str, answer: bool) -> None:
    assert pick.complete(Runs(spec)) is answer
