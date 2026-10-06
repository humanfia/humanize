"""`hmz.flows.defining`: `FlowParams`, and `flow` and `load` handing their calls on."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pydantic
import pytest

from hmz.flows import (
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowDefinitionError,
    FlowNotFound,
    FlowParams,
    FlowRefError,
    Outworlder,
    flow,
    load,
)

if TYPE_CHECKING:
    from unittest import mock


class Agents(AgentCollection):
    pass


class Envs(EnvCollection):
    pass


class Params(FlowParams):
    rounds: int = 3
    cost: float = 1.0


async def body(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> str:
    """Says the task back.

    And nothing more.
    """
    return task


# --------------------------------------------------------------------------- FlowParams


def test_params_take_their_declared_fields() -> None:
    assert Params(rounds=5).rounds == 5
    assert Params.model_validate({"rounds": "7"}).rounds == 7
    assert Params().rounds == 3


@pytest.mark.parametrize("given", [{"round": 1}, {"rounds": 1, "extra": True}])
def test_params_refuse_an_undeclared_key(given: dict[str, Any]) -> None:
    with pytest.raises(pydantic.ValidationError, match="Extra inputs"):
        Params.model_validate(given)


def test_params_refuse_a_value_of_the_wrong_type() -> None:
    with pytest.raises(pydantic.ValidationError):
        Params.model_validate({"rounds": "many"})


def test_params_write_infinity_as_a_string_and_read_it_back() -> None:
    written = Params(cost=math.inf).model_dump_json()
    assert '"Infinity"' in written
    assert Params.model_validate_json(written).cost == math.inf


def test_bare_params_take_nothing() -> None:
    assert FlowParams().model_dump() == {}
    with pytest.raises(pydantic.ValidationError):
        FlowParams.model_validate({"anything": 1})


# --------------------------------------------------------------------------------- flow


def test_flow_hands_nothing_on_until_it_decorates(engine: mock.Mock) -> None:
    flow(agents=Agents, envs=Envs, params=Params)
    engine.define_flow.assert_not_called()


def test_flow_hands_the_function_and_its_declaration_to_the_runtime(
    engine: mock.Mock,
) -> None:
    flow(agents=Agents, envs=Envs, params=Params)(body)

    engine.define_flow.assert_called_once()
    (fn,), declared = engine.define_flow.call_args
    assert fn is body
    assert declared["agents"] is Agents
    assert declared["envs"] is Envs
    assert declared["params"] is Params
    assert declared["name"] is None
    assert declared["description"] is None
    assert declared["hidden"] is False
    assert declared["resumable"] is False


def test_flow_answers_what_the_runtime_made(engine: mock.Mock) -> None:
    made = object()
    engine.define_flow.side_effect = None
    engine.define_flow.return_value = made

    assert flow(agents=Agents, envs=Envs, params=Params)(body) is made


def test_flow_passes_on_what_it_was_told(engine: mock.Mock) -> None:
    flow(
        agents=Agents,
        envs=Envs,
        params=Params,
        name="echo",
        description="says it back",
        hidden=True,
        resumable=True,
    )(body)

    declared = engine.define_flow.call_args.kwargs
    assert declared["name"] == "echo"
    assert declared["description"] == "says it back"
    assert declared["hidden"] is True
    assert declared["resumable"] is True


def test_flow_hands_on_the_namespaces_it_was_written_in(engine: mock.Mock) -> None:
    nearby = "a local the flow's annotations might name"
    flow(agents=Agents, envs=Envs, params=Params)(body)

    declared = engine.define_flow.call_args.kwargs
    assert declared["caller_globals"] is globals()
    assert declared["caller_locals"]["nearby"] is nearby


def test_flow_lets_a_definition_error_through(engine: mock.Mock) -> None:
    engine.define_flow.side_effect = FlowDefinitionError("not async")

    decorate = flow(agents=Agents, envs=Envs, params=Params)
    with pytest.raises(FlowDefinitionError, match="not async"):
        decorate(body)


# --------------------------------------------------------------------------------- load


@pytest.mark.parametrize(
    "ref",
    [
        ":review",
        "humanize1",
        "humanize1:rlcr",
        "humanfia/humanize1:rlcr",
        "git+https://github.com/humanfia/humanize1-flow@v0.1.0#humanize1:rlcr",
    ],
)
def test_load_hands_the_ref_and_the_caller_to_the_runtime(
    engine: mock.Mock, ref: str
) -> None:
    loaded = load(ref)

    assert loaded is engine.load_flow.return_value
    engine.load_flow.assert_called_once_with(ref, caller_globals=globals())


@pytest.mark.parametrize("error", [FlowNotFound("none"), FlowRefError("bad ref")])
def test_load_lets_what_the_runtime_raised_through(
    engine: mock.Mock, error: Exception
) -> None:
    engine.load_flow.side_effect = error

    with pytest.raises(type(error)):
        load("anything")


# ---------------------------------------------------------------------- Outworlder.new


def test_a_new_outworlder_is_the_runtimes(engine: mock.Mock) -> None:
    made = Outworlder.new()

    assert made is engine.new_outworlder.return_value
    engine.new_outworlder.assert_called_once_with()
