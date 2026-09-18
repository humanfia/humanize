"""The session updates a Grok Build conversation writes down, read back as slices.

`updates.jsonl` is the protocol's own notification stream persisted, so the vocabulary is the
one :mod:`hmz.coganchor.agents.grok` drives a turn on: a prompt, a model call speaking in
thoughts and answers, a tool announced and then updated twice, and Grok Build's own
`turn_completed` carrying what the whole turn cost. Each is written here against a log built
for it, so that a reader which quietly stopped recognising one is a failing test rather than a
trace with a hole in it -- and the counts have a test of their own, a turn nothing can read a
cost off being a cell nothing can meter.

Every record below is shaped after a real one: the turns of `grok 1.0.24 (68e414c661e3)` this
machine ran while the reader was written, down to the camel case its usage is spelled in and
the double wrapping of a tool's answer.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime import tracing
from hmz.runtime.tracing.readers import grok

if TYPE_CHECKING:
    import pathlib

    from hmz.runtime.tracing.session import Action, Session

#: The session every log below is written under, as Grok Build mints one.
SESSION = "01a0b3c8-d383-7081-98d6-5a8b7437bcc1"

#: The sub-agent one of them spawns.
CHILD = "01a09af1-1318-7440-99ff-a224526572c3"

#: The moment a conversation starts, in epoch seconds.
_BEGAN = 1_789_722_678.0

#: Every moment either side of the window a test narrows to.
_EVER = (float("-inf"), float("inf"))


def _said(
    at: float, update: dict[str, Any], *, told: str = "session/update", **meta: Any
) -> dict[str, Any]:
    """One notification, as a line of `updates.jsonl`.

    Args:
      at: When the agent said it, as seconds from the start of the conversation.
      update: The `session/update` itself.
      told: The method, which is Grok Build's own for what the protocol has no word for.
      meta: What `params._meta` carries beside the times every record has.

    Returns:
      The record.
    """
    return {
        "timestamp": int(_BEGAN + at),
        "method": told,
        "params": {
            "sessionId": SESSION,
            "update": update,
            "_meta": {
                "eventId": f"{SESSION}-{int(at * 1000)}",
                "agentTimestampMs": int((_BEGAN + at) * 1000),
                **meta,
            },
        },
    }


def _prompt(at: float = 0.0, body: str = "reply with OK", index: int = 0) -> Any:
    """The chunk a turn opens on, which is the only record naming the model."""
    return _said(
        at,
        {
            "sessionUpdate": "user_message_chunk",
            "content": {"type": "text", "text": body},
            "_meta": {"modelId": "grok-4.6", "promptIndex": index},
        },
    )


def _completed(at: float = 4.0, **usage: Any) -> Any:
    """The turn ending, with the counts the whole of it is billed by."""
    return _said(
        at,
        {
            "sessionUpdate": "turn_completed",
            "prompt_id": "a0a6bb0a-7a5c-40d8-9324-b826bf4bb45d",
            "stop_reason": "end_turn",
            "usage": {
                "inputTokens": 16506,
                "outputTokens": 27,
                "totalTokens": 16533,
                "cachedReadTokens": 128,
                "cacheCreationTokens": 0,
                "reasoningTokens": 26,
                "modelCalls": 1,
                "modelUsage": {"grok-4.6-build": {"totalTokens": 16533}},
                **usage,
            },
            "elapsed_ms": 2172,
        },
        told="_x.ai/session/update",
    )


def _streamed(at: float, began: float = 1.0) -> dict[str, Any]:
    """What a record of a model call carries about the call it came out of."""
    return {
        "promptId": "a0a6bb0a-7a5c-40d8-9324-b826bf4bb45d",
        "streamStartMs": int((_BEGAN + began) * 1000),
        "turnStartMs": int(_BEGAN * 1000),
        "chunkId": int(at * 100),
    }


@pytest.fixture
def written(tmp_path: pathlib.Path) -> Any:
    """Writes one session out of the records handed in, and reads it back.

    Returns:
      A callable taking the records of `updates.jsonl` and answering with the one session
      that came of them.
    """
    home = tmp_path / "grok"
    workspace = tmp_path / "project"
    workspace.mkdir()

    def wrote(*records: dict[str, Any], ident: str = SESSION) -> Session:
        under = urllib.parse.quote(str(workspace), safe="")
        at = home / "sessions" / under / ident
        at.mkdir(parents=True, exist_ok=True)
        (at / "updates.jsonl").write_text(
            "".join(json.dumps(one) + "\n" for one in records), encoding="utf-8"
        )
        (one,) = grok.collect(home, workspace, None, _EVER)
        return one

    return wrote


def _named(session: Session, starting: str) -> Action:
    """The one action whose name starts like this, for a test about that action."""
    found = [one for one in session.actions if one.name.startswith(starting)]
    assert len(found) == 1, [one.name for one in session.actions]
    return found[0]


# ------------------------------------------------------------------- the whole of a turn


def test_a_turn_is_the_prompt_it_opened_on(written: Any) -> None:
    said = written(_prompt(body="map the repo"), _completed())

    turn = _named(said, "turn:")
    assert turn.category == "turn"
    assert turn.args["prompt"] == "map the repo"
    assert said.title == f"{SESSION[:8]} · map the repo"
    assert said.args["cwd"].endswith("/project")
    assert said.args["model"] == "grok-4.6"


def test_a_turn_carries_the_counts_it_was_billed_by(written: Any) -> None:
    """The whole point of reading this log: a cell nobody can count is a cell nobody can meter.

    Grok Build states a cost once a turn rather than once a model call -- the live stream's
    `response_completed` is not written down -- so the counts hang on the turn.
    """
    said = written(_prompt(), _completed())

    turn = _named(said, "turn:")
    assert turn.args["usage"]["inputTokens"] == 16506
    assert turn.args["usage"]["outputTokens"] == 27
    assert turn.args["usage"]["cachedReadTokens"] == 128
    assert turn.args["usage"]["totalTokens"] == 16533
    assert turn.args["stop_reason"] == "end_turn"
    assert turn.args["elapsed_ms"] == 2172


def test_a_turn_runs_from_its_prompt_to_the_counts_that_ended_it(written: Any) -> None:
    said = written(_prompt(0.0), _completed(6.0))

    turn = _named(said, "turn:")
    assert (turn.start, turn.end) == (_BEGAN, _BEGAN + 6.0)


def test_a_turn_nothing_ever_ended_runs_to_the_last_thing_said(written: Any) -> None:
    said = written(
        _prompt(0.0),
        _said(
            3.0,
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "OK"},
            },
            **_streamed(3.0),
        ),
    )

    turn = _named(said, "turn:")
    assert turn.end == _BEGAN + 3.0


# --------------------------------------------------------------------- what the model said


def test_a_model_call_is_timed_from_when_it_opened(written: Any) -> None:
    """`streamStartMs` is a real moment, so the slice starts where the model did."""
    said = written(
        _prompt(0.0),
        _said(
            2.5,
            {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "read it first"},
            },
            **_streamed(2.5, began=1.0),
        ),
        _completed(),
    )

    think = _named(said, "think:")
    assert think.category == "llm"
    assert (think.start, think.end) == (_BEGAN + 1.0, _BEGAN + 2.5)
    assert think.args["thinking"] == "read it first"


def test_the_two_answers_of_one_turn_are_two_model_calls(written: Any) -> None:
    said = written(
        _prompt(0.0),
        _said(
            2.0,
            {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "read it first"},
            },
            **_streamed(2.0, began=1.0),
        ),
        _said(
            5.0,
            {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "now answer"},
            },
            **_streamed(5.0, began=4.0),
        ),
        _completed(6.0),
    )

    assert [one.start for one in said.actions if one.category == "llm"] == [
        _BEGAN + 1.0,
        _BEGAN + 4.0,
    ]


def test_no_slice_runs_backwards_when_two_records_of_one_moment_do(
    written: Any,
) -> None:
    """These are timed by the agent's own clock, which two records of one millisecond share.

    Read back over every `updates.jsonl` this machine had -- 5506 sessions, 65 thousand
    slices -- exactly one pair came back in the other order.
    """
    said = written(
        _prompt(0.0),
        _said(
            2.0,
            {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "answer it"},
            },
            **_streamed(2.0),
        ),
        _said(
            1.9,
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "OK"},
            },
            **_streamed(1.9),
        ),
        _completed(),
    )

    spoken = _named(said, "say:")
    assert spoken.start <= spoken.end


def test_what_the_agent_said_is_a_slice_of_its_own(written: Any) -> None:
    said = written(
        _prompt(0.0),
        _said(
            2.0,
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "the repo is mapped"},
            },
            **_streamed(2.0),
        ),
        _completed(),
    )

    spoken = _named(said, "say:")
    assert spoken.category == "message"
    assert spoken.args["text"] == "the repo is mapped"


# ------------------------------------------------------------------------ what it reached for


def _call(at: float, **extra: Any) -> dict[str, Any]:
    """A tool being announced, with the tool's own facts where Grok Build hangs them."""
    return _said(
        at,
        {
            "sessionUpdate": "tool_call",
            "toolCallId": "call-1",
            "title": "run_terminal_command",
            "rawInput": {"command": "echo hi", "description": "Say hello"},
            "_meta": {
                "x.ai/tool": {
                    "name": "run_terminal_command",
                    "kind": "execute",
                    "namespace": "grok_build",
                }
            },
            **extra,
        },
        **_streamed(at),
    )


def _answered(
    at: float, status: str = "completed", body: str = "hi\n"
) -> dict[str, Any]:
    """The update a tool call ends on, its answer wrapped the way the protocol wraps one."""
    return _said(
        at,
        {
            "sessionUpdate": "tool_call_update",
            "toolCallId": "call-1",
            "status": status,
            "content": [{"type": "content", "content": {"type": "text", "text": body}}],
            "rawOutput": {"exit_code": 0, "output": body},
        },
        **_streamed(at),
    )


def test_a_call_and_both_of_its_updates_are_one_slice(written: Any) -> None:
    said = written(
        _prompt(0.0),
        _call(2.0),
        _said(
            2.0,
            {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call-1",
                "kind": "execute",
                "title": "Execute `echo hi`",
                "rawInput": {"command": "echo hi"},
            },
            **_streamed(2.0),
        ),
        _answered(3.0),
        _completed(),
    )

    call = _named(said, "run_terminal_command")
    assert call.category == "tool"
    assert call.name == "run_terminal_command: Say hello"
    assert call.args["namespace"] == "grok_build"
    assert call.args["kind"] == "execute"
    assert call.args["input"] == {"command": "echo hi", "description": "Say hello"}
    assert call.args["output"] == "hi\n"
    assert call.args["error"] is False
    assert (call.start, call.end) == (_BEGAN + 2.0, _BEGAN + 3.0)


def test_a_call_that_failed_says_so(written: Any) -> None:
    said = written(
        _prompt(0.0), _call(2.0), _answered(3.0, "failed", "no"), _completed()
    )

    call = _named(said, "run_terminal_command")
    assert call.args["status"] == "failed"
    assert call.args["error"] is True


def test_a_call_nothing_ever_answered_is_left_open(written: Any) -> None:
    said = written(_prompt(0.0), _call(2.0), _completed(5.0))

    call = _named(said, "run_terminal_command")
    assert call.args["unfinished"] is True
    assert call.end == _BEGAN + 5.0


def test_the_model_call_ends_where_it_reached_for_something(written: Any) -> None:
    said = written(
        _prompt(0.0),
        _said(
            1.5,
            {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "run it"},
            },
            **_streamed(1.5, began=1.0),
        ),
        _call(2.0),
        _answered(3.0),
        _completed(),
    )

    assert _named(said, "think:").end == _BEGAN + 2.0


# ------------------------------------------------------------------ what it said about itself


def test_a_sub_agent_is_named_and_owned_by_the_session_that_spawned_it(
    tmp_path: pathlib.Path,
) -> None:
    home = tmp_path / "grok"
    workspace = tmp_path / "project"
    workspace.mkdir()
    under = home / "sessions" / urllib.parse.quote(str(workspace), safe="")
    for ident, lines in (
        (
            SESSION,
            [
                _prompt(0.0),
                _said(
                    1.0,
                    {
                        "sessionUpdate": "subagent_spawned",
                        "child_session_id": CHILD,
                        "subagent_type": "general-purpose",
                        "description": "goal plan writer",
                    },
                    told="_x.ai/session/update",
                ),
                _completed(),
            ],
        ),
        (CHILD, [_prompt(1.0, body="write the plan"), _completed(3.0)]),
    ):
        (under / ident).mkdir(parents=True)
        (under / ident / "updates.jsonl").write_text(
            "".join(json.dumps(one) + "\n" for one in lines), encoding="utf-8"
        )

    collected = {one.key: one for one in grok.collect(home, workspace, None, _EVER)}

    assert collected[f"grok:{SESSION}"].label == "main"
    child = collected[f"grok:{CHILD}"]
    assert child.parent == f"grok:{SESSION}"
    assert child.label == "general-purpose · goal plan writer"
    assert _named(collected[f"grok:{SESSION}"], "subagent_spawned").spawn == child.key


def test_a_saying_nobody_has_listed_is_still_a_slice(written: Any) -> None:
    """Grok Build's own updates outnumber the protocol's and are added to release by release."""
    said = written(
        _prompt(0.0),
        _said(
            1.0,
            {
                "sessionUpdate": "retry_state",
                "type": "failed",
                "error_type": "api",
                "message": "API error (status 400 Bad Request)",
            },
            told="_x.ai/session/update",
        ),
        _completed(),
    )

    event = _named(said, "retry_state")
    assert event.category == "event"
    assert event.args["error_type"] == "api"


# ------------------------------------------------------------------- which log is whose


def test_two_prompts_are_two_turns_and_one_prompt_in_pieces_is_one(
    written: Any,
) -> None:
    said = written(
        _prompt(0.0, body="map the repo", index=0),
        _prompt(0.5, body="and the tests", index=0),
        _completed(2.0),
        _prompt(3.0, body="now port it", index=1),
        _completed(5.0),
    )

    turns = [one for one in said.actions if one.category == "turn"]
    assert [one.args["prompt"] for one in turns] == [
        "map the repo\nand the tests",
        "now port it",
    ]


def test_a_session_recorded_for_another_workspace_is_not_this_workspace(
    tmp_path: pathlib.Path,
) -> None:
    home = tmp_path / "grok"
    elsewhere = tmp_path / "other project"
    at = home / "sessions" / urllib.parse.quote(str(elsewhere), safe="") / SESSION
    at.mkdir(parents=True)
    (at / "updates.jsonl").write_text(json.dumps(_prompt()) + "\n", encoding="utf-8")

    assert grok.collect(home, tmp_path / "project", None, _EVER) == []
    (one,) = grok.collect(home, elsewhere, None, _EVER)
    assert one.args["cwd"] == str(elsewhere)


def test_only_the_sessions_asked_for_are_read(tmp_path: pathlib.Path) -> None:
    home = tmp_path / "grok"
    workspace = tmp_path / "project"
    under = home / "sessions" / urllib.parse.quote(str(workspace), safe="")
    for ident in (SESSION, CHILD):
        (under / ident).mkdir(parents=True)
        (under / ident / "updates.jsonl").write_text(
            json.dumps(_prompt()) + "\n", encoding="utf-8"
        )

    (one,) = grok.collect(home, workspace, (SESSION[:8],), _EVER)
    assert one.key == f"grok:{SESSION}"


def test_what_happened_outside_the_window_is_cut_off(tmp_path: pathlib.Path) -> None:
    home = tmp_path / "grok"
    workspace = tmp_path / "project"
    at = home / "sessions" / urllib.parse.quote(str(workspace), safe="") / SESSION
    at.mkdir(parents=True)
    (at / "updates.jsonl").write_text(
        "".join(
            json.dumps(one) + "\n"
            for one in (_prompt(0.0, body="in"), _prompt(60.0, body="out", index=1))
        ),
        encoding="utf-8",
    )

    (one,) = grok.collect(home, workspace, None, (_BEGAN - 1.0, _BEGAN + 30.0))

    assert [held.args["prompt"] for held in one.actions] == ["in"]


def test_the_counts_name_the_model_for_a_log_that_opens_on_no_prompt(
    written: Any,
) -> None:
    """A session resumed with its prompt carried in has no chunk to read a model off."""
    said = written(_completed(2.0))

    assert said.args["model"] == "grok-4.6-build"


def test_a_grok_home_is_collected_like_any_other_backend(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reader is only reachable once `collect` dispatches the backend onto it."""
    home = tmp_path / "grok"
    workspace = tmp_path / "project"
    workspace.mkdir()
    at = home / "sessions" / urllib.parse.quote(str(workspace), safe="") / SESSION
    at.mkdir(parents=True)
    (at / "updates.jsonl").write_text(
        "".join(json.dumps(one) + "\n" for one in (_prompt(), _completed())),
        encoding="utf-8",
    )
    monkeypatch.setenv("GROK_HOME", str(home))

    document = tracing.collect(workspace)

    assert document["otherData"]["backends"] == "grok"
    assert document["otherData"]["agents"] == "grok · grok-4.6"
