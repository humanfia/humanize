"""`hmz.flows.hooks`: every moment a hook hangs on, what it is told, and what it answers."""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest import mock

import pydantic
import pytest

from hmz.flows import (
    HOOK_TYPES,
    AskUserHookParams,
    AskUserHookResult,
    HookFn,
    HookKind,
    HookParams,
    HookResult,
    NotificationHookParams,
    NotificationHookResult,
    OutworlderRunHookParams,
    OutworlderRunHookResult,
    PermissionRequestHookParams,
    PermissionRequestHookResult,
    PreToolUseHookParams,
    PreToolUseHookResult,
    SessionEndHookParams,
    SessionEndHookResult,
    SessionStartHookParams,
    SessionStartHookResult,
    StopHookParams,
    StopHookResult,
    SubagentStartHookParams,
    SubagentStartHookResult,
    SubagentStopHookParams,
    SubagentStopHookResult,
    UserPromptSubmitHookParams,
    UserPromptSubmitHookResult,
)

CTX, SESSION = mock.sentinel.ctx, mock.sentinel.session


@pytest.mark.parametrize(
    ("kind", "params", "result"),
    [
        (HookKind.SESSION_START, SessionStartHookParams, SessionStartHookResult),
        (
            HookKind.USER_PROMPT_SUBMIT,
            UserPromptSubmitHookParams,
            UserPromptSubmitHookResult,
        ),
        (HookKind.PRE_TOOL_USE, PreToolUseHookParams, PreToolUseHookResult),
        (
            HookKind.PERMISSION_REQUEST,
            PermissionRequestHookParams,
            PermissionRequestHookResult,
        ),
        (HookKind.NOTIFICATION, NotificationHookParams, NotificationHookResult),
        (HookKind.STOP, StopHookParams, StopHookResult),
        (HookKind.SESSION_END, SessionEndHookParams, SessionEndHookResult),
        (HookKind.SUBAGENT_START, SubagentStartHookParams, SubagentStartHookResult),
        (HookKind.SUBAGENT_STOP, SubagentStopHookParams, SubagentStopHookResult),
        (HookKind.ASK_USER, AskUserHookParams, AskUserHookResult),
        (HookKind.OUTWORLDER_RUN, OutworlderRunHookParams, OutworlderRunHookResult),
    ],
)
def test_each_moment_has_its_params_and_result(
    kind: HookKind, params: type[HookParams], result: type[HookResult]
) -> None:
    assert HOOK_TYPES[kind] == (params, result)
    assert issubclass(params, HookParams)
    assert issubclass(result, HookResult)
    assert kind == kind.name.lower()


def test_every_moment_is_in_hook_types() -> None:
    assert set(HOOK_TYPES) == set(HookKind)


def test_hook_types_cannot_be_changed() -> None:
    with pytest.raises(TypeError):
        HOOK_TYPES[HookKind.STOP] = (HookParams, HookResult)  # pyright: ignore[reportIndexIssue]


@pytest.mark.parametrize(
    ("result", "defaults"),
    [
        (HookResult, {}),
        (SessionStartHookResult, {"context": ""}),
        (UserPromptSubmitHookResult, {"block": False, "reason": "", "context": ""}),
        (PreToolUseHookResult, {"block": False, "reason": ""}),
        (PermissionRequestHookResult, {"allow": True, "reason": ""}),
        (NotificationHookResult, {}),
        (StopHookResult, {"block": False, "reason": ""}),
        (SessionEndHookResult, {}),
        (SubagentStartHookResult, {"context": ""}),
        (SubagentStopHookResult, {"block": False, "reason": ""}),
        (AskUserHookResult, {"answer": None}),
    ],
)
def test_a_result_built_with_nothing_changes_nothing(
    result: type[HookResult], defaults: dict[str, Any]
) -> None:
    assert dataclasses.asdict(result()) == defaults


def test_an_outworlders_result_must_say_something() -> None:
    with pytest.raises(TypeError):
        OutworlderRunHookResult()  # pyright: ignore[reportCallIssue]

    class Verdict(pydantic.BaseModel):
        ok: bool

    assert OutworlderRunHookResult(output="yes").output == "yes"
    assert OutworlderRunHookResult(output=Verdict(ok=True)).output == Verdict(ok=True)


@pytest.mark.parametrize(
    ("params", "given", "defaults"),
    [
        (SessionStartHookParams, {}, {}),
        (UserPromptSubmitHookParams, {"prompt": "hi"}, {}),
        (PreToolUseHookParams, {"tool": "Bash"}, {"input": {}}),
        (PermissionRequestHookParams, {"tool": "Bash"}, {"input": {}}),
        (NotificationHookParams, {"message": "done"}, {}),
        (StopHookParams, {"said": "ok"}, {"again": 0}),
        (SessionEndHookParams, {}, {}),
        (SubagentStartHookParams, {"subagent": "explore"}, {"task": ""}),
        (SubagentStopHookParams, {"subagent": "explore"}, {"said": ""}),
        (AskUserHookParams, {"question": "which?"}, {"options": ()}),
        (OutworlderRunHookParams, {"prompt": "go on?"}, {"output_schema": None}),
    ],
)
def test_params_carry_the_context_session_and_what_the_moment_says(
    params: type[HookParams], given: dict[str, Any], defaults: dict[str, Any]
) -> None:
    told = params(ctx=CTX, session=SESSION, **given)
    assert told.ctx is CTX
    assert told.session is SESSION
    for name, value in {**given, **defaults}.items():
        assert getattr(told, name) == value


@pytest.mark.parametrize(
    "params",
    [UserPromptSubmitHookParams, PreToolUseHookParams, StopHookParams],
)
def test_params_need_what_the_moment_says(params: type[HookParams]) -> None:
    with pytest.raises(TypeError):
        params(ctx=CTX, session=SESSION)


def test_params_need_the_context_and_session_by_keyword() -> None:
    with pytest.raises(TypeError):
        SessionStartHookParams(CTX, SESSION)  # pyright: ignore[reportCallIssue]
    with pytest.raises(TypeError):
        SessionStartHookParams(ctx=CTX)  # pyright: ignore[reportCallIssue]


def test_params_cannot_be_changed() -> None:
    told = StopHookParams(ctx=CTX, session=SESSION, said="ok")
    with pytest.raises(dataclasses.FrozenInstanceError):
        told.said = "else"  # pyright: ignore[reportAttributeAccessIssue]


def test_tool_inputs_left_out_are_not_shared() -> None:
    one = PreToolUseHookParams(ctx=CTX, session=SESSION, tool="Bash")
    other = PreToolUseHookParams(ctx=CTX, session=SESSION, tool="Bash")
    assert one.input is not other.input


async def test_an_async_function_is_a_hook() -> None:
    async def no_force_push(params: PreToolUseHookParams) -> PreToolUseHookResult:
        pushing = "push --force" in str(params.input.get("command", ""))
        return PreToolUseHookResult(block=pushing, reason="no force pushes")

    hook: HookFn[PreToolUseHookParams, PreToolUseHookResult] = no_force_push
    told = PreToolUseHookParams(
        ctx=CTX, session=SESSION, tool="Bash", input={"command": "git push --force"}
    )
    assert await hook(told) == PreToolUseHookResult(
        block=True, reason="no force pushes"
    )
