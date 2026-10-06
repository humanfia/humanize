"""`hmz.flows.errors`: one tree under `FlowException`, each leaf crossing processes intact."""

from __future__ import annotations

import copy
import pickle

import pytest

import hmz.flows.errors
from hmz.flows import (
    BudgetExceeded,
    CapabilityMissing,
    CapabilityNotGranted,
    CostExceeded,
    DurationExceeded,
    EnvCommandTimeout,
    EnvConnectionError,
    EnvError,
    EnvFileNotFound,
    EnvPermissionDenied,
    EnvUnavailable,
    FlowCancelled,
    FlowDefinitionError,
    FlowDepthExceeded,
    FlowException,
    FlowLoadConflict,
    FlowNotFound,
    FlowRefError,
    FlowRuntimeError,
    HarnessContended,
    HarnessDropped,
    HarnessError,
    HarnessKilled,
    HarnessMismatch,
    HarnessMissing,
    HarnessNotInstalled,
    HarnessRefused,
    HarnessSandboxed,
    HarnessThrottled,
    HarnessUnrecoverable,
    MissingRole,
    ModelUnavailable,
    OutputSchemaError,
    OutputTokensExceeded,
    OutworlderAway,
    ParamsError,
    PermissionTooNarrow,
    RequirementError,
    ResourceUnmet,
    RewindError,
    ScratchError,
    SessionError,
    StateNotSerializable,
    TempCloneBusy,
    UnsupportedOperation,
    WorktreeError,
)

#: Each error, and the classes it is directly made of.
PARENTS: dict[type[Exception], tuple[type[Exception], ...]] = {
    FlowRuntimeError: (FlowException,),
    FlowNotFound: (FlowRuntimeError,),
    FlowRefError: (FlowRuntimeError, ValueError),
    FlowDefinitionError: (FlowRuntimeError,),
    FlowLoadConflict: (FlowRuntimeError,),
    RequirementError: (FlowRuntimeError,),
    MissingRole: (RequirementError,),
    CapabilityMissing: (RequirementError,),
    PermissionTooNarrow: (RequirementError,),
    ResourceUnmet: (RequirementError,),
    HarnessMismatch: (RequirementError,),
    CapabilityNotGranted: (FlowRuntimeError,),
    ParamsError: (FlowRuntimeError, ValueError),
    FlowDepthExceeded: (FlowRuntimeError, RecursionError),
    BudgetExceeded: (FlowRuntimeError,),
    DurationExceeded: (BudgetExceeded, TimeoutError),
    CostExceeded: (BudgetExceeded,),
    OutputTokensExceeded: (BudgetExceeded,),
    FlowCancelled: (FlowRuntimeError,),
    StateNotSerializable: (FlowRuntimeError, TypeError),
    OutworlderAway: (FlowRuntimeError,),
    HarnessError: (FlowException,),
    HarnessNotInstalled: (HarnessError,),
    HarnessContended: (HarnessError,),
    HarnessThrottled: (HarnessError,),
    HarnessRefused: (HarnessError,),
    ModelUnavailable: (HarnessError,),
    HarnessMissing: (HarnessError,),
    HarnessSandboxed: (HarnessError,),
    HarnessKilled: (HarnessError,),
    HarnessDropped: (HarnessError,),
    HarnessUnrecoverable: (HarnessError,),
    OutputSchemaError: (HarnessError, ValueError),
    SessionError: (HarnessError,),
    UnsupportedOperation: (HarnessError,),
    EnvError: (FlowException,),
    EnvUnavailable: (EnvError,),
    EnvConnectionError: (EnvError, ConnectionError),
    EnvCommandTimeout: (EnvError, TimeoutError),
    EnvFileNotFound: (EnvError, FileNotFoundError),
    EnvPermissionDenied: (EnvError, PermissionError),
    WorktreeError: (EnvError,),
    TempCloneBusy: (EnvError,),
    ScratchError: (EnvError,),
    RewindError: (EnvError,),
}

EVERY = [FlowException, *PARENTS]


def test_every_error_the_module_offers_is_in_the_tree() -> None:
    offered = {getattr(hmz.flows.errors, name) for name in hmz.flows.errors.__all__}
    assert offered == set(EVERY)


@pytest.mark.parametrize(("error", "parents"), PARENTS.items())
def test_each_error_is_made_of_its_parents(
    error: type[Exception], parents: tuple[type[Exception], ...]
) -> None:
    assert error.__bases__ == parents
    assert issubclass(error, FlowException)


def test_the_root_is_an_exception_and_nothing_more() -> None:
    assert FlowException.__bases__ == (Exception,)
    assert not issubclass(KeyError, FlowException)


@pytest.mark.parametrize(
    ("error", "builtin"),
    [
        (DurationExceeded, TimeoutError),
        (EnvCommandTimeout, TimeoutError),
        (EnvFileNotFound, FileNotFoundError),
        (EnvPermissionDenied, PermissionError),
        (EnvConnectionError, ConnectionError),
        (FlowRefError, ValueError),
        (ParamsError, ValueError),
        (OutputSchemaError, ValueError),
        (StateNotSerializable, TypeError),
        (FlowDepthExceeded, RecursionError),
    ],
)
def test_a_builtin_catches_the_error_it_names(
    error: type[Exception], builtin: type[Exception]
) -> None:
    with pytest.raises(builtin, match="ran out"):
        raise error("ran out")


@pytest.mark.parametrize("error", EVERY)
def test_each_error_says_its_message(error: type[Exception]) -> None:
    raised = error("what went wrong")
    assert str(raised) == "what went wrong"
    assert raised.args == ("what went wrong",)


@pytest.mark.parametrize("error", EVERY)
def test_each_error_pickles_and_copies_as_itself(error: type[Exception]) -> None:
    raised = error("what went wrong")
    for again in (
        pickle.loads(pickle.dumps(raised)),  # noqa: S301 -- what this test pickled itself
        copy.copy(raised),
        copy.deepcopy(raised),
    ):
        assert type(again) is error
        assert again.args == raised.args
