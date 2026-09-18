"""The rollout lines a ZCode session can hold that the shared fixture does not.

`test_collect.py` reads one realistic session end to end, which covers the spine -- a turn,
its reasoning, a tool call answered by the request after it, the naming of the session and the
sub-agent it started. What it does not hold is what a long or an unlucky session writes: a
conversation replayed as its tail rather than whole, a conversation replaced by a summary of
itself, and a request that came back as nothing at all.

Each is written here on its own, against a rollout built for it, so that a reader which
quietly stopped recognising one of them is a failing test rather than a trace with a hole in
it -- or, for the two that decide what a session *is* rather than what it did, a session
missing from a workspace's trace altogether.
"""

from __future__ import annotations

import datetime
import json
import math
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing.readers import zcode

if TYPE_CHECKING:
    import pathlib

    from hmz.runtime.tracing.session import Action, Session

#: The session every rollout below is written under.
SESSION = "sess_01998f1a-0000-7000-8000-00000000beef"

#: The moment a rollout starts, as ZCode writes one.
_BEGAN = 1_780_000_000.0

#: The whole of time, for a test that is not about the window.
_EVER = (-math.inf, math.inf)


def _stamp(seconds: float) -> str:
    """One moment, as a ZCode rollout spells it."""
    return (
        datetime.datetime.fromtimestamp(_BEGAN + seconds, tz=datetime.UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _line(
    at: float,
    turn: str,
    messages: list[dict[str, Any]],
    kind: str = "full",
    offset: int = 0,
    **held: Any,
) -> dict[str, Any]:
    """One model-io line of the session, as ZCode 0.16.5 writes one.

    Args:
        at: When the request was sent, as an offset from the rollout's start.
        turn: Which turn of the session it was a request of.
        messages: The conversation as that request replayed it.
        kind: Whether that replay is the whole of it, what is new since the
            line before, or its tail.
        offset: Where the replay begins, as an index into the conversation.
        held: What is particular to this line -- its `response`, or the
            `error` it came back as instead.

    Returns:
        The line, ready to be written.
    """
    return {
        "type": "model_io",
        "sessionId": SESSION,
        "traceId": "trace-1",
        "turnId": turn,
        "querySource": "main_turn",
        "requestId": f"request-{at:g}",
        "attempt": 1,
        "startedAt": _stamp(at),
        "completedAt": _stamp(at + 1),
        "durationMs": 1000,
        "model": {
            "modelId": "glm-5.3-flash",
            "providerId": "gw",
            "role": "main",
            "source": "session",
            "variant": "high",
        },
        "request": {
            "messages": messages,
            "messagesKind": kind,
            "messageCount": offset + len(messages),
            "messageOffset": offset,
        },
        **held,
    }


def _said(text: str) -> dict[str, Any]:
    """What one request answered with, for a line that is about something else."""
    return {
        "text": text,
        "finishReason": "stop",
        "toolCalls": [],
        "usage": {"inputTokens": 10, "outputTokens": 2, "totalTokens": 12},
    }


@pytest.fixture
def rollout(tmp_path: pathlib.Path, workspace: pathlib.Path) -> Any:
    """Writes the lines handed in as one session's rollout, and reads it back.

    Returns:
        A callable taking the lines of a rollout -- and the window and the
        workspace, for the tests that are about those -- and answering with the
        sessions that came of them.
    """
    home = tmp_path / "zcode"

    def written(
        *records: dict[str, Any],
        window: tuple[float, float] = _EVER,
        under: pathlib.Path | None = None,
    ) -> list[Session]:
        at = home / "cli" / "rollout"
        at.mkdir(parents=True, exist_ok=True)
        (at / f"model-io-{SESSION}.jsonl").write_text(
            "".join(json.dumps(one) + "\n" for one in records), encoding="utf-8"
        )
        return zcode.collect(home, under, None, window)

    return written


def _environment(workspace: pathlib.Path) -> dict[str, Any]:
    """The system message ZCode says which directory a session is working in."""
    return {
        "role": "system",
        "content": (
            "# Environment\nYou have been invoked in the following environment:\n"
            f"- Primary working directory: {workspace}\n- Is a git repository: no\n"
        ),
    }


def _turns(session: Session) -> list[Action]:
    """Every turn of a session, oldest first."""
    return [one for one in session.actions if one.category == "turn"]


def test_a_conversation_replayed_as_its_tail_is_placed_where_it_says_it_is(
    rollout: Any, workspace: pathlib.Path
) -> None:
    """Past sixty-four messages ZCode replays the last of them, and says where they start."""
    (session,) = rollout(
        _line(
            0, "turn-1", [_environment(workspace), {"role": "user", "content": "one"}]
        ),
        _line(
            4,
            "turn-2",
            [{"role": "user", "content": "two"}],
            kind="tail",
            offset=64,
            response=_said("and two"),
        ),
    )

    assert [one.args["prompt"] for one in _turns(session)] == ["one", "two"]


def test_a_conversation_replaced_by_a_summary_of_itself_is_read_on(
    rollout: Any, workspace: pathlib.Path
) -> None:
    """Compacting a session starts its conversation again, shorter than what was read.

    Counting alone would have every index of the new one below what has already been read,
    and so would drop every prompt after the first compaction -- which on a long session is
    most of them.
    """
    (session,) = rollout(
        _line(
            0,
            "turn-1",
            [
                _environment(workspace),
                {"role": "user", "content": "the first ask"},
                {"role": "assistant", "content": "done"},
                {"role": "user", "content": "the second ask"},
            ],
        ),
        _line(
            4,
            "turn-2",
            [
                _environment(workspace),
                {"role": "user", "content": "what came after the compaction"},
            ],
            response=_said("read"),
        ),
    )

    assert [one.args["prompt"] for one in _turns(session)] == [
        "the first ask\nthe second ask",
        "what came after the compaction",
    ]


def test_what_a_session_is_survives_the_window_the_trace_was_narrowed_to(
    rollout: Any, workspace: pathlib.Path
) -> None:
    """ZCode says the workspace in the first prompt that carried one, and only there.

    So a window that starts after it is a window with no workspace to match -- and a session
    dropped for that is a session gone from the trace rather than a session narrowed.
    """
    kept = rollout(
        _line(
            0, "turn-1", [_environment(workspace), {"role": "user", "content": "one"}]
        ),
        _line(
            40,
            "turn-2",
            [{"role": "user", "content": "two"}],
            kind="delta",
            offset=2,
            response=_said("and two"),
        ),
        window=(_BEGAN + 30, math.inf),
        under=workspace,
    )

    assert [one.ident for one in kept] == [SESSION]
    assert kept[0].args["cwd"] == str(workspace)
    assert kept[0].args["model"] == "glm-5.3-flash"
    assert kept[0].args["effort"] == "high"
    assert [one.args["prompt"] for one in _turns(kept[0])] == ["two"]


@pytest.mark.parametrize(
    "error",
    [
        {"name": "APICallError", "message": "upstream 529 overloaded", "stack": "…"},
        "upstream 529 overloaded",
    ],
    ids=["thrown", "said"],
)
def test_a_request_that_came_back_as_nothing_is_named_after_why(
    rollout: Any, workspace: pathlib.Path, error: Any
) -> None:
    """ZCode writes an error as the object it was thrown as, or as itself where it was not.

    Named after the failure rather than after the thinking that arrived before it: a retry is
    the one thing on a timeline somebody is looking for.
    """
    (session,) = rollout(
        _line(
            0,
            "turn-1",
            [_environment(workspace), {"role": "user", "content": "one"}],
            error=error,
            response={"reasoningText": "let me try that", "toolCalls": []},
        )
    )

    (failed,) = [one for one in session.actions if one.category == "llm"]
    assert failed.name == "failed: upstream 529 overloaded"
    assert failed.args["error"] == error


@pytest.mark.parametrize(
    "content",
    [
        "<system-reminder>\nskills\n</system-reminder>\nthe real ask",
        "the real ask\n<system-reminder>\ntoday is a Tuesday\n</system-reminder>",
    ],
    ids=["before", "after"],
)
def test_what_zcode_added_to_a_message_is_cut_out_of_it_rather_than_taking_it(
    rollout: Any, workspace: pathlib.Path, content: str
) -> None:
    """On 0.16.5 each aside is a message of its own, which is ZCode's to change."""
    (session,) = rollout(
        _line(
            0,
            "turn-1",
            [_environment(workspace), {"role": "user", "content": content}],
            response=_said("read"),
        )
    )

    assert [one.args["prompt"] for one in _turns(session)] == ["the real ask"]
