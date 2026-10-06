"""How the flow API is read into coganchor's words and back: rungs, hooks, faults, answers."""

from __future__ import annotations

import subprocess
from typing import Any

import pydantic
import pytest

from hmz.coganchor import backends
from hmz.coganchor import fence as coganchor_fence
from hmz.coganchor.agents import (
    Failed,
    Occasion,
    Stopped,
    Unfenced,
    Unrecoverable,
    Verdict,
)
from hmz.coganchor.agents.hooks import Moment
from hmz.coganchor.anchor import NotInstalled
from hmz.flows import (
    AskUserHookResult,
    HarnessContended,
    HarnessDropped,
    HarnessError,
    HarnessKilled,
    HarnessKind,
    HarnessMissing,
    HarnessNotInstalled,
    HarnessRefused,
    HarnessSandboxed,
    HarnessThrottled,
    HarnessUnrecoverable,
    HookKind,
    ModelUnavailable,
    NotificationHookResult,
    OutputSchemaError,
    Permission,
    PermissionKind,
    PermissionRequestHookResult,
    PreToolUseHookResult,
    SessionError,
    StopHookResult,
)
from hmz.runtime.flowing.harnessing import (
    ASKING,
    ASKING_FEATURE,
    ASKS,
    BYPASS,
    FAULTS,
    MOMENTS,
    READ_ONLY,
    UNTRUSTED,
    WORKSPACE_WRITE,
    answer,
    approvals,
    asking,
    fenced,
    fields,
    harness_error,
    prompting,
    read_shape,
    rung,
    searching,
    verdict,
)

READ = Permission(local=PermissionKind.READ)
NONE = Permission(
    local=PermissionKind.NONE,
    user=PermissionKind.NONE,
    system=PermissionKind.NONE,
    online=PermissionKind.NONE,
)
ALL = Permission()
LADDER = (READ_ONLY, WORKSPACE_WRITE, ASKING, BYPASS)

# ---------------------------------------------------------------------------- permission


@pytest.mark.parametrize(
    ("harness", "permission", "rungs", "hung", "said"),
    [
        (HarnessKind.CLAUDE, ALL, LADDER, frozenset[HookKind](), BYPASS),
        (HarnessKind.CLAUDE, READ, LADDER, frozenset[HookKind](), READ_ONLY),
        (HarnessKind.CLAUDE, NONE, LADDER, frozenset[HookKind](), READ_ONLY),
        (HarnessKind.DSH, READ, (BYPASS,), frozenset[HookKind](), BYPASS),
        (HarnessKind.KIMI, ALL, LADDER, frozenset({HookKind.ASK_USER}), ASKING),
        (
            HarnessKind.KIMI,
            ALL,
            LADDER,
            frozenset({HookKind.PERMISSION_REQUEST}),
            ASKING,
        ),
        (HarnessKind.KIMI, ALL, LADDER, frozenset({HookKind.STOP}), BYPASS),
        (HarnessKind.KIMI, READ, LADDER, frozenset({HookKind.ASK_USER}), READ_ONLY),
        (HarnessKind.CODEX, ALL, LADDER, frozenset({HookKind.ASK_USER}), BYPASS),
    ],
    ids=[
        "all-is-bypass",
        "read-is-read-only",
        "none-is-read-only",
        "a-cli-with-one-rung",
        "kimi-asks-for-a-question",
        "kimi-asks-for-a-permission",
        "kimi-other-hooks",
        "kimi-reading",
        "codex-never-auto",
    ],
)
def test_a_session_runs_at_the_rung_the_table_says(
    harness: HarnessKind,
    permission: Permission,
    rungs: tuple[str, ...],
    hung: frozenset[HookKind],
    said: str,
) -> None:
    assert rung(harness, permission, rungs=rungs, hung=hung) == said


def test_only_kimi_is_run_asking_and_only_for_the_hooks_asking_reaches() -> None:
    assert set(ASKS) == {HarnessKind.KIMI}
    assert asking(HarnessKind.KIMI, frozenset({HookKind.ASK_USER}))
    assert not asking(HarnessKind.KIMI, frozenset())
    assert not asking(HarnessKind.CLAUDE, frozenset({HookKind.PERMISSION_REQUEST}))


@pytest.mark.parametrize(
    ("harness", "hung", "said"),
    [
        (HarnessKind.CODEX, frozenset({HookKind.PERMISSION_REQUEST}), UNTRUSTED),
        (HarnessKind.CODEX, frozenset({HookKind.ASK_USER}), ""),
        (HarnessKind.CLAUDE, frozenset({HookKind.PERMISSION_REQUEST}), ""),
    ],
)
def test_codex_asks_about_everything_while_a_permission_hook_is_hung(
    harness: HarnessKind, hung: frozenset[HookKind], said: str
) -> None:
    assert approvals(harness, hung) == said


def test_claude_prompts_while_a_permission_hook_is_hung() -> None:
    assert prompting(HarnessKind.CLAUDE, frozenset({HookKind.PERMISSION_REQUEST}))
    assert not prompting(HarnessKind.CLAUDE, frozenset({HookKind.PRE_TOOL_USE}))
    assert not prompting(HarnessKind.CODEX, frozenset({HookKind.PERMISSION_REQUEST}))
    assert ASKING_FEATURE == "default_mode_request_user_input"


@pytest.mark.parametrize(
    ("permission", "tellable", "said"),
    [(ALL, True, True), (NONE, True, False), (ALL, False, None), (NONE, False, None)],
)
def test_the_web_is_on_for_all_off_for_none_and_left_where_it_cannot_be_told(
    permission: Permission, tellable: bool, said: bool | None
) -> None:
    assert searching(permission, tellable=tellable) is said


def test_the_fence_is_the_permissions_scopes_around_the_workdir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drawn: list[dict[str, Any]] = []
    asked: list[tuple[object, object]] = []

    def of(**said: Any) -> str:
        drawn.append(said)
        return "the fence"

    def reachable(profile: object, environ: object) -> tuple[str, ...]:
        asked.append((profile, environ))
        return ("api.example.com",)

    monkeypatch.setattr(coganchor_fence.Fence, "of", of)
    monkeypatch.setattr(backends, "reachable", reachable)
    profile: Any = object()

    known = fenced(NONE, workdir="/w", home="/h", profile=profile, environ={"K": "V"})
    unknown = fenced(ALL, workdir="/w", home="/h", profile=None, environ={})

    assert (known, unknown) == ("the fence", "the fence")
    assert drawn == [
        {
            "local": PermissionKind.NONE,
            "user": PermissionKind.NONE,
            "system": PermissionKind.NONE,
            "online": False,
            "workdir": "/w",
            "home": "/h",
            "hosts": ("api.example.com",),
        },
        {
            "local": PermissionKind.ALL,
            "user": PermissionKind.READ,
            "system": PermissionKind.READ,
            "online": True,
            "workdir": "/w",
            "home": "/h",
            "hosts": (),
        },
    ]
    assert asked == [(profile, {"K": "V"})]


# ---------------------------------------------------------------------------------- hooks


def _occasion(moment: Moment, **said: Any) -> Occasion:
    return Occasion(moment=moment, agent="coder", **said)


def test_every_moment_coganchor_fires_is_a_hook_kind() -> None:
    assert set(MOMENTS) == {one.value for one in Moment} & set(MOMENTS)
    for moment, kind in MOMENTS.items():
        assert Moment(moment).value == moment
        assert isinstance(kind, HookKind)


@pytest.mark.parametrize(
    ("kind", "occasion", "said"),
    [
        (
            HookKind.PRE_TOOL_USE,
            _occasion(Moment.PRE_TOOL_USE, tool="Bash", input={"command": "ls"}),
            {"tool": "Bash", "input": {"command": "ls"}},
        ),
        (
            HookKind.PERMISSION_REQUEST,
            _occasion(Moment.PERMISSION_REQUEST, tool="Bash", about="ls -la"),
            {"tool": "Bash", "input": {"about": "ls -la"}},
        ),
        (
            HookKind.PRE_TOOL_USE,
            _occasion(Moment.PRE_TOOL_USE, tool="Read"),
            {"tool": "Read", "input": {}},
        ),
        (
            HookKind.NOTIFICATION,
            _occasion(Moment.NOTIFICATION, said="done soon"),
            {"message": "done soon"},
        ),
        (
            HookKind.SUBAGENT_START,
            _occasion(Moment.SUBAGENT_START, tool="explorer", about="find it"),
            {"subagent": "explorer", "task": "find it"},
        ),
        (
            HookKind.SUBAGENT_STOP,
            _occasion(Moment.SUBAGENT_STOP, tool="explorer", said="found"),
            {"subagent": "explorer", "said": "found"},
        ),
        (HookKind.STOP, _occasion(Moment.STOP, said="x"), {}),
    ],
    ids=[
        "tool",
        "tool-seen-in-a-transcript",
        "tool-with-nothing",
        "note",
        "sub-in",
        "sub-out",
        "rest",
    ],
)
def test_a_hook_is_told_what_its_kind_reads_off_the_moment(
    kind: HookKind, occasion: Occasion, said: dict[str, Any]
) -> None:
    assert fields(kind, occasion) == said


@pytest.mark.parametrize(
    ("kind", "result", "said"),
    [
        (HookKind.PRE_TOOL_USE, PreToolUseHookResult(), None),
        (
            HookKind.PRE_TOOL_USE,
            PreToolUseHookResult(block=True, reason="no rm"),
            Verdict(refused=True, because="no rm"),
        ),
        (
            HookKind.PRE_TOOL_USE,
            PreToolUseHookResult(block=True),
            Verdict(refused=True, because="refused by a hook"),
        ),
        (HookKind.PERMISSION_REQUEST, PermissionRequestHookResult(), None),
        (
            HookKind.PERMISSION_REQUEST,
            PermissionRequestHookResult(allow=False, reason="not today"),
            Verdict(refused=True, because="not today"),
        ),
        (HookKind.NOTIFICATION, NotificationHookResult(), None),
        (HookKind.PRE_TOOL_USE, StopHookResult(block=True, reason="x"), None),
    ],
    ids=[
        "let",
        "blocked",
        "blocked-no-reason",
        "allowed",
        "denied",
        "told",
        "mismatched",
    ],
)
def test_only_a_tool_can_be_refused_by_what_a_hook_answered(
    kind: HookKind, result: Any, said: Verdict | None
) -> None:
    assert verdict(kind, result) == said


def test_a_question_is_answered_with_what_its_hook_said() -> None:
    assert answer(AskUserHookResult(answer="yes")) == "yes"
    assert answer(AskUserHookResult()) is None
    assert answer(StopHookResult()) is None


# --------------------------------------------------------------------------------- errors


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (NotInstalled("claude is not installed"), HarnessNotInstalled),
        (Unfenced("no landlock"), HarnessSandboxed),
        (Stopped("stopped"), SessionError),
        (Failed(1, ["x"], fault="throttled"), HarnessThrottled),
        (Failed(1, ["x"], fault="spent"), HarnessThrottled),
        (Failed(1, ["x"], fault="contended"), HarnessContended),
        (Failed(1, ["x"], fault="refused"), HarnessRefused),
        (Failed(1, ["x"], fault="retired"), ModelUnavailable),
        (Failed(1, ["x"], fault="sandboxed"), HarnessSandboxed),
        (Failed(1, ["x"], fault="killed"), HarnessKilled),
        (Failed(1, ["x"], fault="dropped"), HarnessDropped),
        (Failed(1, ["x"], fault="missing"), HarnessMissing),
        (Failed(127, ["x"], fault="missing"), HarnessNotInstalled),
        (Failed(1, ["x"], fault="something new"), HarnessUnrecoverable),
        (Unrecoverable(1, ["x"]), HarnessUnrecoverable),
        (ConnectionResetError("reset"), HarnessDropped),
        (RuntimeError("closed"), SessionError),
        (ValueError("bad config"), HarnessUnrecoverable),
    ],
    ids=lambda one: (
        type(one).__name__ if isinstance(one, BaseException) else one.__name__
    ),
)
def test_a_turn_that_failed_in_coganchor_comes_to_its_harness_error(
    error: BaseException, kind: type[HarnessError]
) -> None:
    said = harness_error(error, "claude")

    assert type(said) is kind
    assert str(said)


def test_a_failure_coganchor_did_not_classify_is_read_off_what_the_cli_wrote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read: list[tuple[str, str, str, int]] = []

    def trouble(backend: str, err: str, out: str, *, status: int) -> str:
        read.append((backend, err, out, status))
        return "throttled"

    monkeypatch.setattr(backends, "trouble", trouble)
    error = subprocess.CalledProcessError(2, ["claude"], output=b"o\xff", stderr="429")

    said = harness_error(error, "claude")

    assert isinstance(said, HarnessThrottled)
    assert read == [("claude", "429", "o�", 2)]


def test_a_bug_stays_the_bug_it_was() -> None:
    assert harness_error(KeyError("x"), "claude") is None
    assert harness_error(TypeError("x"), "claude") is None


def test_every_fault_is_a_harness_error() -> None:
    assert all(issubclass(one, HarnessError) for one in FAULTS.values())


# -------------------------------------------------------------------------------- answers


class Verdicts(pydantic.BaseModel):
    ok: bool
    why: str = ""


@pytest.mark.parametrize(
    "said",
    [
        '{"ok": true}',
        '  {"ok": true}\n',
        'Here you go:\n```json\n{"ok": true}\n```\nanything else?',
        'Sure ```\n{"ok": true}``` there',
        'I think {"ok": true} is right',
    ],
    ids=["bare", "padded", "fenced-json", "fenced", "talked-around"],
)
def test_an_answer_is_read_as_its_model_wherever_it_put_it(said: str) -> None:
    assert read_shape(said, Verdicts) == Verdicts(ok=True)


@pytest.mark.parametrize("said", ["", "no", '{"why": "x"}', "```{}```"])
def test_an_answer_with_no_instance_of_its_model_is_an_output_schema_error(
    said: str,
) -> None:
    with pytest.raises(OutputSchemaError, match="not a Verdicts"):
        read_shape(said, Verdicts)
