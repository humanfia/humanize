"""Doubles the `hmz.flows` unit tests stand in for the runtime, and for what a flow is handed.

`hmz.flows` names one thing outside itself, `hmz.runtime.flowing.engine`, and only when
`flow`, `load` or `Outworlder.new` is called. `engine` puts a mock in its place; `builtin`
imports a builtin flow afresh against that mock, so the flow's own function is what is run.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest import mock

import hmz.flows.builtin

if TYPE_CHECKING:
    import pytest

#: The module `flow`, `load` and `Outworlder.new` hand their calls to.
ENGINE = "hmz.runtime.flowing.engine"

#: The workspace every builtin flow is handed.
WORKSPACE = mock.sentinel.workspace


@dataclass
class Defined:
    """What the stand-in `define_flow` answers: the function, and what it was declared with."""

    fn: Any
    declared: dict[str, Any]


def engine(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """Puts a mock engine in the runtime's place; its `define_flow` answers a `Defined`."""
    double = mock.Mock(spec=["define_flow", "load_flow", "new_outworlder"])

    def define_flow(fn: Any, **declared: Any) -> Defined:
        return Defined(fn, declared)

    double.define_flow.side_effect = define_flow
    monkeypatch.setitem(sys.modules, ENGINE, double)
    return double


def builtin(monkeypatch: pytest.MonkeyPatch, name: str) -> Any:
    """Imports `hmz.flows.builtin.<name>` afresh against the engine in place, put back after."""
    qualified = f"hmz.flows.builtin.{name}"
    # Recorded first, so that the import's own entries are undone with the test.
    monkeypatch.setitem(sys.modules, qualified, None)
    monkeypatch.setattr(hmz.flows.builtin, name, None, raising=False)
    del sys.modules[qualified]
    return importlib.import_module(qualified)


def agent(*turns: str | BaseException) -> mock.Mock:
    """An agent whose turns answer with `turns` in order: a string is said, an error raised."""
    double = mock.Mock(name="agent")
    double.spawn = mock.AsyncMock(side_effect=object)
    double.run = mock.AsyncMock(side_effect=list(turns))
    return double


def context(state: dict[str, Any] | None = None) -> mock.Mock:
    """A flow context holding `state`: a dict reads and writes as a `FlowState` does."""
    return mock.Mock(name="ctx", state=state)


async def call(defined: Defined, task: str, *, ctx: Any, **agents: Any) -> Any:
    """Runs a builtin flow's own function with `agents`, the workspace, and its own params."""
    return await defined.fn(
        task,
        agents=agents,
        envs={"workspace": WORKSPACE},
        params=defined.declared["params"](),
        ctx=ctx,
    )


def sessions(double: mock.Mock) -> list[Any]:
    """The session each of an agent's turns was taken in, in order."""
    return [one.kwargs["session"] for one in double.run.await_args_list]


def prompts(double: mock.Mock) -> list[str]:
    """The prompt each of an agent's turns was given, in order."""
    return [one.args[0] for one in double.run.await_args_list]
