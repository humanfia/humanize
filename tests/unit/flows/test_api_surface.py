"""The one import a flow writes: what it offers, what it costs, and the three calls that run.

`hmz.flows` is types, bar `flow`, `load` and `Outworlder.new`, which hand their calls to the
engine -- with enough of the caller's frame for the engine to resolve what the flow declared
and where a relative ref is relative to. Importing it must cost pydantic and nothing else of
consequence: it is what every flow imports, and what a command line reads before it knows
whether it names a flow at all.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import sys
from typing import TYPE_CHECKING, Any

import pytest

import hmz.flows
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    Outworlder,
    agents,
    defining,
    envs,
    errors,
    flow,
    hooks,
    load,
)
from hmz.runtime.flowing import engine

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


#: What importing the flow API may bring with it besides the standard library.
THIRD_PARTY = {
    "annotated_types",
    "pydantic",
    "pydantic_core",
    "typing_extensions",
    "typing_inspection",
}


def test_everything_it_offers_is_there() -> None:
    for name in hmz.flows.__all__:
        assert getattr(hmz.flows, name, None) is not None, name


@pytest.mark.parametrize("module", [agents, defining, envs, errors, hooks])
def test_everything_its_modules_offer_it_offers(module: object) -> None:
    offered: list[str] = getattr(module, "__all__", [])
    assert offered
    assert set(offered) <= set(hmz.flows.__all__)
    for name in offered:
        assert getattr(hmz.flows, name) is getattr(module, name)


def test_a_name_it_does_not_offer_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError):
        _ = importlib.import_module("hmz.flows").load_flow


@pytest.fixture
def fresh() -> Iterator[None]:
    """Takes the flow API out of `sys.modules` for a test, and puts the same one back after.

    So that the test can import it afresh and see what that costs, without leaving a second
    copy of every class behind for the tests after it to compare against the first.
    """
    held = {name: sys.modules.pop(name) for name in list(sys.modules) if _ours(name)}
    was = hmz.flows
    try:
        yield
    finally:
        for name in [name for name in sys.modules if _ours(name)]:
            del sys.modules[name]
        sys.modules.update(held)
        hmz.flows = was


def _ours(name: str) -> bool:
    return name == "hmz.flows" or name.startswith("hmz.flows.")


def test_importing_it_asks_for_nothing_of_humanize_and_nothing_heavy(
    fresh: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every import statement the package runs, recorded as it runs, cached or not."""
    asked: set[str] = set()
    importing = builtins.__import__

    def recorded(
        name: str,
        globals: Mapping[str, object] | None = None,  # noqa: A002 -- __import__'s own
        locals: Mapping[str, object] | None = None,  # noqa: A002 -- __import__'s own
        fromlist: tuple[str, ...] | list[str] | None = (),
        level: int = 0,
    ) -> Any:
        package = (globals or {}).get("__package__")
        if level and isinstance(package, str):
            asked.add(importlib.util.resolve_name("." * level + name, package))
        else:
            asked.add(name)
        return importing(name, globals, locals, fromlist or (), level)

    monkeypatch.setattr(builtins, "__import__", recorded)
    importlib.import_module("hmz.flows")
    monkeypatch.undo()

    humanize = {
        name
        for name in asked
        if name.split(".")[0] == "hmz" and not _ours(name) and name != "hmz"
    }
    assert not humanize, humanize
    theirs = {name.split(".")[0] for name in asked} - {"hmz"}
    heavy = theirs - sys.stdlib_module_names - THIRD_PARTY
    assert not heavy, heavy


def test_a_decorated_flow_is_what_the_engine_makes_of_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    made: dict[str, Any] = {}
    sentinel: Any = object()

    def define_flow(fn: object, **said: Any) -> Any:
        made.update(said, fn=fn)
        return sentinel

    monkeypatch.setattr(engine, "define_flow", define_flow)

    class Agents(AgentCollection):
        coder: Agent

    class Envs(EnvCollection):
        pass

    class Params(FlowParams):
        rounds: int = 1

    async def fix(
        task: str,
        *,
        agents: Agents,
        envs: Envs,
        params: Params,
        ctx: FlowContext,
    ) -> None:
        del task, agents, envs, params, ctx

    decorated = flow(
        agents=Agents,
        envs=Envs,
        params=Params,
        name="fixing",
        description="fixes",
        hidden=True,
        resumable=True,
    )(fix)
    assert decorated is sentinel
    assert made["fn"] is fix
    assert (made["agents"], made["envs"], made["params"]) == (Agents, Envs, Params)
    assert (made["name"], made["description"], made["hidden"], made["resumable"]) == (
        "fixing",
        "fixes",
        True,
        True,
    )
    assert made["caller_globals"] is globals()
    assert made["caller_locals"]["Agents"] is Agents


def test_a_decorator_with_nothing_said_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    made: dict[str, Any] = {}

    def define_flow(fn: object, **said: Any) -> None:
        del fn
        made.update(said)

    monkeypatch.setattr(engine, "define_flow", define_flow)

    async def bare(
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: FlowParams,
        ctx: FlowContext,
    ) -> None:
        del task, agents, envs, params, ctx

    flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)(bare)
    assert (made["name"], made["description"], made["hidden"], made["resumable"]) == (
        None,
        None,
        False,
        False,
    )


def test_load_hands_the_engine_the_ref_and_where_it_was_asked_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, Mapping[str, Any]]] = []
    sentinel: Any = object()

    def load_flow(ref: str, *, caller_globals: Mapping[str, Any]) -> Any:
        asked.append((ref, caller_globals))
        return sentinel

    monkeypatch.setattr(engine, "load_flow", load_flow)
    assert load(":review") is sentinel
    assert asked == [(":review", globals())]


def test_a_new_outworlder_is_the_engine_s(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel: Any = object()
    monkeypatch.setattr(engine, "new_outworlder", lambda: sentinel)
    assert Outworlder.new() is sentinel

    class Human(Outworlder):
        pass

    assert Human.new() is sentinel
