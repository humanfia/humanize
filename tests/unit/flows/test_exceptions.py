"""Everything a flow can catch: one tree, the builtins where they fit, and each one portable."""

from __future__ import annotations

import copy
import pickle

import pytest

import hmz.flows
from hmz.flows import errors
from hmz.flows.errors import (
    BudgetExceeded,
    EnvError,
    FlowException,
    FlowRuntimeError,
    HarnessError,
    RequirementError,
)

#: Each exception, and the class of the tree directly above it.
TREE: dict[str, type[Exception]] = {
    "FlowRuntimeError": FlowException,
    "HarnessError": FlowException,
    "EnvError": FlowException,
    "FlowNotFound": FlowRuntimeError,
    "FlowRefError": FlowRuntimeError,
    "FlowDefinitionError": FlowRuntimeError,
    "FlowLoadConflict": FlowRuntimeError,
    "RequirementError": FlowRuntimeError,
    "MissingRole": RequirementError,
    "CapabilityMissing": RequirementError,
    "PermissionTooNarrow": RequirementError,
    "ResourceUnmet": RequirementError,
    "HarnessMismatch": RequirementError,
    "CapabilityNotGranted": FlowRuntimeError,
    "ParamsError": FlowRuntimeError,
    "FlowDepthExceeded": FlowRuntimeError,
    "BudgetExceeded": FlowRuntimeError,
    "DurationExceeded": BudgetExceeded,
    "CostExceeded": BudgetExceeded,
    "OutputTokensExceeded": BudgetExceeded,
    "FlowCancelled": FlowRuntimeError,
    "StateNotSerializable": FlowRuntimeError,
    "OutworlderAway": FlowRuntimeError,
    "HarnessNotInstalled": HarnessError,
    "HarnessContended": HarnessError,
    "HarnessThrottled": HarnessError,
    "HarnessRefused": HarnessError,
    "ModelUnavailable": HarnessError,
    "HarnessMissing": HarnessError,
    "HarnessSandboxed": HarnessError,
    "HarnessKilled": HarnessError,
    "HarnessDropped": HarnessError,
    "HarnessUnrecoverable": HarnessError,
    "OutputSchemaError": HarnessError,
    "SessionError": HarnessError,
    "UnsupportedOperation": HarnessError,
    "EnvUnavailable": EnvError,
    "EnvConnectionError": EnvError,
    "EnvCommandTimeout": EnvError,
    "EnvFileNotFound": EnvError,
    "EnvPermissionDenied": EnvError,
    "WorktreeError": EnvError,
    "TempCloneBusy": EnvError,
    "ScratchError": EnvError,
}

#: The ones that are a builtin too, so that the builtin's `except` catches them.
BUILTINS: dict[str, type[Exception]] = {
    "FlowRefError": ValueError,
    "ParamsError": ValueError,
    "FlowDepthExceeded": RecursionError,
    "DurationExceeded": TimeoutError,
    "StateNotSerializable": TypeError,
    "OutputSchemaError": ValueError,
    "EnvConnectionError": ConnectionError,
    "EnvCommandTimeout": TimeoutError,
    "EnvFileNotFound": FileNotFoundError,
    "EnvPermissionDenied": PermissionError,
}

EVERY = sorted([FlowException, *(getattr(errors, name) for name in TREE)], key=str)


def test_the_tree_is_the_whole_module_and_nothing_else() -> None:
    assert set(errors.__all__) == {"FlowException", *TREE}


@pytest.mark.parametrize(("name", "above"), sorted(TREE.items()))
def test_each_exception_sits_where_the_tree_puts_it(
    name: str, above: type[Exception]
) -> None:
    kind: type[Exception] = getattr(errors, name)
    assert above in kind.__bases__
    assert issubclass(kind, FlowException)


@pytest.mark.parametrize(("name", "builtin"), sorted(BUILTINS.items()))
def test_a_builtin_except_catches_the_leaf_that_is_one(
    name: str, builtin: type[Exception]
) -> None:
    kind: type[Exception] = getattr(errors, name)
    with pytest.raises(builtin):
        raise kind("said")


def test_no_other_leaf_is_a_builtin_it_does_not_say() -> None:
    plain = {
        name
        for name, kind in vars(errors).items()
        if isinstance(kind, type)
        and issubclass(kind, FlowException)
        and name not in BUILTINS
    }
    for name in plain:
        kind: type[Exception] = getattr(errors, name)
        for builtin in {*BUILTINS.values(), LookupError, RuntimeError}:
            assert not issubclass(kind, builtin), (name, builtin)


@pytest.mark.parametrize("kind", EVERY, ids=lambda kind: kind.__name__)
def test_each_one_pickles_and_copies_as_itself(kind: type[Exception]) -> None:
    raised = kind("what happened")
    for back in (
        pickle.loads(pickle.dumps(raised)),  # noqa: S301 -- what it wrote itself
        copy.copy(raised),
        copy.deepcopy(raised),
    ):
        assert type(back) is kind
        assert back.args == ("what happened",)
        assert str(back) == str(raised)


@pytest.mark.parametrize("kind", EVERY, ids=lambda kind: kind.__name__)
def test_each_one_says_when_it_is_raised(kind: type[Exception]) -> None:
    assert (kind.__doc__ or "").strip()


@pytest.mark.parametrize("kind", EVERY, ids=lambda kind: kind.__name__)
def test_a_flow_imports_each_one_from_the_one_place(kind: type[Exception]) -> None:
    assert getattr(hmz.flows, kind.__name__) is kind
    assert kind.__name__ in hmz.flows.__all__


def test_catching_the_root_catches_every_branch() -> None:
    for kind in EVERY:
        with pytest.raises(FlowException):
            raise kind("x")
