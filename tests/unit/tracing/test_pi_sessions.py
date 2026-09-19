"""What a Pi session log holds, and what a reader has to make of each of it.

Pi keeps a vocabulary of its own in two places that matter. What a session was run
at is stated once at the head, as `model_change` and `thinking_level_change` events
rather than on each answer; and a tool's output comes back as a message whose role is
`toolResult`, where every other backend here answers a call with a user turn. Both
are things a reader written for another backend would get quietly wrong, so both are
written down here.
"""

from __future__ import annotations

import datetime
import json
import math
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing.readers import pi

if TYPE_CHECKING:
    import pathlib

    from hmz.runtime.tracing.session import Action, Session

SESSION = "0156a340-74ea-4613-b650-1a1b30a6ba4c"

#: The moment a session opens, as a fixture counts from.
_BEGAN = datetime.datetime(2026, 9, 9, 17, 24, 26, tzinfo=datetime.UTC)

#: The whole of time, for a test that is not about the window.
_EVER = (-math.inf, math.inf)


def _stamp(seconds: float) -> str:
    """One moment, as Pi spells it."""
    return (
        (_BEGAN + datetime.timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _usage(**held: int) -> dict[str, Any]:
    """One usage, under Pi's own names, with the cost it worked out beside it."""
    return {
        "input": 1000,
        "output": 40,
        "cacheRead": 0,
        "cacheWrite": 0,
        "reasoning": 0,
        "totalTokens": 1040,
        "cost": {"total": 0},
        **held,
    }


def _message(at: float, message: dict[str, Any]) -> dict[str, Any]:
    """One `message` record, with the envelope every one of them carries."""
    return {
        "type": "message",
        "id": f"id-{at}",
        "parentId": None,
        "timestamp": _stamp(at),
        "message": message,
    }


def _written(
    home: pathlib.Path, cwd: str, records: list[dict[str, Any]], *, folder: str = "-w-"
) -> None:
    """One session log, under a directory named however Pi named that workspace."""
    where = home / "sessions" / folder
    where.mkdir(parents=True, exist_ok=True)
    head = [
        {"type": "session", "version": 3, "id": SESSION, "timestamp": _stamp(0), "cwd": cwd},
        {
            "type": "model_change",
            "id": "m1",
            "timestamp": _stamp(0.1),
            "provider": "nvgw",
            "modelId": "pi-coder-1",
        },
        {
            "type": "thinking_level_change",
            "id": "t1",
            "timestamp": _stamp(0.1),
            "thinkingLevel": "high",
        },
    ]
    (where / f"2026-09-09T17-24-26-979Z_{SESSION}.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in head + records),
        encoding="utf-8",
    )


@pytest.fixture
def session_log(tmp_path: pathlib.Path) -> pathlib.Path:
    """A home holding one session that asks, thinks, calls a tool and answers."""
    home = tmp_path / "pi"
    _written(
        home,
        "/work",
        [
            _message(
                1,
                {"role": "user", "content": [{"type": "text", "text": "cut the cycles"}]},
            ),
            _message(
                2,
                {
                    "role": "assistant",
                    "model": "pi-coder-1",
                    "provider": "nvgw",
                    "stopReason": "toolUse",
                    "usage": _usage(),
                    "content": [
                        {"type": "thinking", "thinking": "read the kernel first"},
                        {
                            "type": "toolCall",
                            "id": "call-1",
                            "name": "bash",
                            "arguments": {"command": "cat perf_takehome.py"},
                        },
                    ],
                },
            ),
            _message(
                3,
                {
                    "role": "toolResult",
                    "toolCallId": "call-1",
                    "toolName": "bash",
                    "content": [{"type": "text", "text": "def kernel(): ..."}],
                },
            ),
            _message(
                4,
                {
                    "role": "assistant",
                    "model": "pi-coder-1",
                    "usage": _usage(output=7, totalTokens=1007),
                    "content": [{"type": "text", "text": "done"}],
                },
            ),
        ],
    )
    return home


def _collected(home: pathlib.Path, **held: Any) -> list[Session]:
    """Every session of ``home``, over the whole of time unless told otherwise."""
    return pi.collect(
        home, held.get("workspace"), held.get("sessions"), held.get("window", _EVER)
    )


def _of(session: Session, category: str) -> list[Action]:
    """Every slice of one kind, in the order the log put them."""
    return [action for action in session.actions if action.category == category]


def test_a_session_log_is_read_as_the_session_it_is(session_log: pathlib.Path) -> None:
    (session,) = _collected(session_log)

    assert session.key == f"pi:{SESSION}"
    assert session.backend == "pi"
    assert session.ident == SESSION
    assert session.label == "main"
    assert session.parent is None
    assert "cut the cycles" in session.title


def test_what_a_session_ran_at_is_read_off_the_head_of_the_log(
    session_log: pathlib.Path,
) -> None:
    """Pi states these once, as events, rather than on each answer it got back."""
    (session,) = _collected(session_log)

    assert session.args["model"] == "pi-coder-1"
    assert session.args["provider"] == "nvgw"
    assert session.args["effort"] == "high"
    assert session.args["cwd"] == "/work"
    assert session.args["version"] == 3


def test_a_tool_result_is_not_a_turn(session_log: pathlib.Path) -> None:
    """Pi answers a call with a role of its own rather than with a user turn.

    Read as a turn, every tool output would look like something the person at
    the prompt asked for.
    """
    (session,) = _collected(session_log)

    (turn,) = _of(session, "turn")
    assert turn.args["prompt"] == "cut the cycles"
    (call,) = _of(session, "tool")
    assert call.args["tool"] == "bash"
    assert call.args["output"] == "def kernel(): ..."
    assert "unfinished" not in call.args


def test_every_answer_is_a_call_with_the_usage_it_was_billed(
    session_log: pathlib.Path,
) -> None:
    (session,) = _collected(session_log)

    calls = _of(session, "llm")

    assert [call.args["usage"]["output"] for call in calls] == [40, 7]
    assert calls[0].args["stop"] == "toolUse"


def test_thinking_is_reasoning_and_text_is_something_said(
    session_log: pathlib.Path,
) -> None:
    (session,) = _collected(session_log)

    (thinking,) = [call for call in _of(session, "llm") if "thinking" in call.args]
    assert thinking.args["thinking"] == "read the kernel first"
    assert [said.args["text"] for said in _of(session, "message")] == ["done"]


def test_which_workspace_a_session_belongs_to_is_read_rather_than_decoded(
    tmp_path: pathlib.Path,
) -> None:
    """The log says its `cwd`, so the directory's name never has to be undone.

    Pi's own name for a workspace is not one this reproduces, and a session
    found by reproducing it would be a session missed the day that changed.
    """
    home = tmp_path / "pi"
    workspace = tmp_path / "work"
    workspace.mkdir()
    _written(home, str(workspace), [], folder="whatever-pi-called-it")

    assert len(_collected(home, workspace=workspace)) == 1
    assert _collected(home, workspace=tmp_path / "nowhere") == []


def test_a_call_nothing_answered_is_said_to_be_unfinished(
    tmp_path: pathlib.Path,
) -> None:
    home = tmp_path / "pi"
    _written(
        home,
        "/work",
        [
            _message(
                1,
                {
                    "role": "assistant",
                    "model": "pi-coder-1",
                    "usage": _usage(),
                    "content": [
                        {"type": "toolCall", "id": "call-1", "name": "bash"},
                    ],
                },
            )
        ],
    )

    (session,) = _collected(home)

    (call,) = _of(session, "tool")
    assert call.args["unfinished"] is True


def test_only_the_sessions_asked_for_are_read(session_log: pathlib.Path) -> None:
    assert len(_collected(session_log, sessions=(SESSION[:8],))) == 1
    assert _collected(session_log, sessions=("no-such-session",)) == []


def test_what_a_session_ran_at_outlives_a_window_it_falls_outside(
    session_log: pathlib.Path,
) -> None:
    """The head of the log is not a thing that happened at a moment.

    A trace narrowed to the middle of a session would otherwise name no model.
    """
    began = _BEGAN.timestamp()

    (session,) = _collected(session_log, window=(began + 3.5, began + 4.5))

    assert session.args["model"] == "pi-coder-1"
    assert len(_of(session, "llm")) == 1


def test_a_torn_line_is_skipped_rather_than_fatal(session_log: pathlib.Path) -> None:
    log = next(session_log.rglob("*.jsonl"))
    with log.open("a", encoding="utf-8") as file:
        file.write('{"type": "message", "timest')

    (session,) = _collected(session_log)

    assert len(_of(session, "llm")) == 2
