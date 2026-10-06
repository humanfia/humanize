"""`hmz.coganchor.agents.hooks`: the moments of a turn, and what a flow says at them."""

from __future__ import annotations

import json
import sys
import tempfile
from typing import Any, NoReturn

import pytest

from hmz.coganchor.agents.event import Stopped
from hmz.coganchor.agents.hooks import (
    EVERYWHERE,
    SUBAGENTS,
    WAITING,
    Gate,
    Hooks,
    Hung,
    Moment,
    Occasion,
    Unhooked,
    Verdict,
    about,
    answers,
    arriving,
)


def _hooks(*moments: Moment) -> Hooks:
    return Hooks(frozenset(moments or Moment), "agent-1")


def test_moments_are_named_as_the_clis_name_them() -> None:
    assert Moment.PRE_TOOL_USE == "PreToolUse"
    assert Moment("Stop") is Moment.STOP


def test_everywhere_leaves_out_what_only_some_backends_run() -> None:
    assert Moment.PERMISSION_REQUEST not in EVERYWHERE
    assert not (SUBAGENTS & EVERYWHERE)
    assert EVERYWHERE | SUBAGENTS | {Moment.PERMISSION_REQUEST} == frozenset(Moment)


def test_a_verdict_says_nothing_by_default() -> None:
    assert Verdict() == Verdict(refused=False, because="", adds="")


def test_an_occasion_leaves_unfilled_fields_empty() -> None:
    one = Occasion(moment=Moment.STOP, agent="a")
    assert (one.session, one.tool, one.input, one.again) == ("", "", {}, 0)


def test_hooks_say_which_agent_and_moments() -> None:
    hooks = Hooks(frozenset({Moment.STOP}), "named")
    assert hooks.agent == "named"
    assert hooks.moments == {Moment.STOP}


def test_hanging_on_a_moment_the_agent_does_not_run_is_refused() -> None:
    with pytest.raises(Unhooked, match="agent-1 does not run PreToolUse"):
        _hooks(Moment.STOP).on(Moment.PRE_TOOL_USE, lambda _: None)
    assert issubclass(Unhooked, ValueError)


def test_on_and_off() -> None:
    hooks = _hooks()
    assert not hooks.hooked(Moment.STOP)
    hung = hooks.on(Moment.STOP, lambda _: None, tool="Bash")
    assert isinstance(hung, Hung)
    assert (hung.moment, hung.tool) == (Moment.STOP, "Bash")
    assert hooks.hooked(Moment.STOP)
    hung.off()
    assert not hooks.hooked(Moment.STOP)
    hung.off()  # twice is fine
    hooks.off(hung)


def test_hung_is_a_context_manager() -> None:
    hooks = _hooks()
    with hooks.on(Moment.STOP, lambda _: None) as hung:
        assert isinstance(hung, Hung)
        assert hooks.hooked(Moment.STOP)
    assert not hooks.hooked(Moment.STOP)


def test_fire_with_nothing_hung_is_an_empty_verdict() -> None:
    assert _hooks().fire(Occasion(Moment.STOP, "a")) == Verdict()


def test_fire_gathers_every_verdict_in_order() -> None:
    hooks = _hooks()
    told: list[Occasion] = []

    def first(occasion: Occasion) -> Verdict:
        told.append(occasion)
        return Verdict(adds="one")

    def broken(_: Occasion) -> NoReturn:
        raise RuntimeError

    hooks.on(Moment.STOP, first)
    hooks.on(Moment.STOP, broken)
    hooks.on(Moment.STOP, lambda _: None)
    hooks.on(Moment.STOP, lambda _: Verdict(refused=True, because="no", adds="two"))
    hooks.on(Moment.STOP, lambda _: Verdict(refused=True, because="later"))
    occasion = Occasion(Moment.STOP, "a", said="done")
    assert hooks.fire(occasion) == Verdict(
        refused=True, because="no", adds="one\n\ntwo"
    )
    assert told == [occasion]


def test_fire_only_tells_a_tool_hook_about_its_tool() -> None:
    hooks = _hooks()
    hooks.on(Moment.PRE_TOOL_USE, lambda _: Verdict(refused=True), tool="Bash")
    assert not hooks.fire(Occasion(Moment.PRE_TOOL_USE, "a", tool="Read")).refused
    assert hooks.fire(Occasion(Moment.PRE_TOOL_USE, "a", tool="Bash")).refused


def test_fire_lets_a_stop_through() -> None:
    hooks = _hooks()

    def stopping(_: Occasion) -> NoReturn:
        raise Stopped("stopped")

    hooks.on(Moment.STOP, stopping)
    with pytest.raises(Stopped):
        hooks.fire(Occasion(Moment.STOP, "a"))


@pytest.mark.parametrize(
    ("called", "said"),
    [
        ({}, ""),
        ({"n": 1, "path": "a.py"}, "a.py"),
        ({"blank": "  ", "command": "ls"}, "ls"),
        ({"nested": {"x": "y"}}, ""),
    ],
)
def test_about_is_the_first_words(called: dict[str, Any], said: str) -> None:
    assert about(called) == said


@pytest.mark.parametrize(
    ("partial", "said"),
    [
        ("", ""),
        ('{"path": "a.p', ""),
        ('{"path": "a.py"', "a.py"),
        ('{"path": "a.py", "content": "x', "a.py"),
        ('{"n": 3, "cmd": "ls -la"}', "ls -la"),
        ('{"blank": "  ", "cmd": "ls"}', "ls"),
        ('{"nested": {"deep": "no"}, "top": "yes"}', "yes"),
        ('{"list": ["no"], "top": "yes"}', "yes"),
        ('{"escaped": "a\\"b"}', 'a"b'),
        ('{"bad": "\\x"}', ""),
    ],
)
def test_arriving_reads_partial_arguments(partial: str, said: str) -> None:
    assert arriving(partial) == said


def test_arriving_agrees_with_about_on_a_whole_call() -> None:
    called = {"n": 1, "path": "src/a.py", "content": "x" * 10}
    assert arriving(json.dumps(called)) == about(called)


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        "[1]",
        "{}",
        '{"hook_event_name": "Stop"}',  # not a gated moment
        '{"hook_event_name": "PreToolUse", "tool_name": "Read"}',  # nothing hung
    ],
)
def test_answers_nothing_to_say(line: str) -> None:
    assert answers(line, _hooks()) == "{}"


def test_answers_a_refusal_and_what_was_added() -> None:
    hooks = _hooks()
    told: list[Occasion] = []

    def hook(occasion: Occasion) -> Verdict:
        told.append(occasion)
        return Verdict(refused=True, adds="careful")

    hooks.on(Moment.PRE_TOOL_USE, hook)
    line = json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "s-1",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
        }
    )
    said = json.loads(answers(line, hooks))
    assert said == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Bash was refused",
            "additionalContext": "careful",
        }
    }
    assert told == [
        Occasion(
            moment=Moment.PRE_TOOL_USE,
            agent="agent-1",
            session="s-1",
            tool="Bash",
            about="rm -rf /",
            input={"command": "rm -rf /"},
        )
    ]


def test_answers_a_stop_as_a_refusal() -> None:
    hooks = _hooks()

    def stopping(_: Occasion) -> NoReturn:
        raise Stopped("agent stopped")

    hooks.on(Moment.PRE_TOOL_USE, stopping)
    said = json.loads(answers('{"hook_event_name": "PreToolUse"}', hooks))
    assert said["hookSpecificOutput"]["permissionDecisionReason"] == "agent stopped"


def test_answers_a_non_object_input_as_none() -> None:
    hooks = _hooks()
    told: list[Occasion] = []
    hooks.on(Moment.PRE_TOOL_USE, told.append)
    answers('{"hook_event_name": "PreToolUse", "tool_input": "x"}', hooks)
    assert told[0].input == {}


def test_a_gate_is_made_once_and_serves_only_pre_tool_use() -> None:
    hooks = _hooks()
    gate = hooks.gate()
    assert hooks.gate() is gate
    assert Gate.moments == {Moment.PRE_TOOL_USE}
    assert gate.serving
    gate.close()
    gate.close()


def test_gated_needs_a_gate_and_a_hook() -> None:
    hooks = _hooks()
    hooks.on(Moment.PRE_TOOL_USE, lambda _: None)
    assert not hooks.gated(Moment.PRE_TOOL_USE)  # no gate yet
    hooks.gate()
    assert hooks.gated(Moment.PRE_TOOL_USE)
    hooks.on(Moment.STOP, lambda _: None)
    assert not hooks.gated(Moment.STOP)  # not a moment a gate serves


def test_a_gate_that_cannot_be_made_serves_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_: object, **__: object) -> NoReturn:
        raise OSError("no room")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse)
    hooks = _hooks()
    hooks.on(Moment.PRE_TOOL_USE, lambda _: None)
    gate = hooks.gate()
    assert gate.address() == ""
    assert not gate.serving
    assert gate.table(WAITING) == {}
    assert gate.command() == [
        sys.executable,
        "-Pm",
        "hmz",
        "internal",
        "hook",
        "--at",
        "",
    ]
    assert not hooks.gated(Moment.PRE_TOOL_USE)
