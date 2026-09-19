"""What a Qwen Code chat log holds, and what a reader has to make of each of it.

Qwen Code descends from Gemini CLI and keeps a turn as Gemini's `parts`, inside the
same record envelope Claude Code writes. Both halves of that are worth a test: the
envelope, because a reader that took it for Claude's would look right until it read a
part; and the parts, because `functionCall`, `text` and a `text` marked `thought` are
three different things wearing one key.
"""

from __future__ import annotations

import datetime
import json
import math
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing.readers import qwen

if TYPE_CHECKING:
    import pathlib

    from hmz.runtime.tracing.session import Action, Session

SESSION = "db705a59-1559-4af5-9753-1f6d3d761000"

#: The moment a chat starts, as a fixture counts from.
_BEGAN = datetime.datetime(2026, 9, 10, 11, 41, 41, tzinfo=datetime.UTC)

#: The whole of time, for a test that is not about the window.
_EVER = (-math.inf, math.inf)


def _stamp(seconds: float) -> str:
    """One moment, as Qwen Code spells it."""
    return (
        (_BEGAN + datetime.timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _record(at: float, kind: str, **held: Any) -> dict[str, Any]:
    """One record of a chat log, with the envelope every one of them carries."""
    return {
        "uuid": f"uuid-{at}",
        "parentUuid": None,
        "sessionId": SESSION,
        "timestamp": _stamp(at),
        "type": kind,
        "cwd": "/work",
        "version": "0.23.1",
        **held,
    }


def _usage(**held: int) -> dict[str, int]:
    """One `usageMetadata`, under Gemini's names for the kinds of token."""
    return {
        "promptTokenCount": 1000,
        "candidatesTokenCount": 40,
        "thoughtsTokenCount": 0,
        "totalTokenCount": 1040,
        "cachedContentTokenCount": 0,
        **held,
    }


def _written(home: pathlib.Path, workspace: str, records: list[dict[str, Any]]) -> None:
    """One chat log, under the directory Qwen Code names that workspace by."""
    import re

    folder = home / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", workspace) / "chats"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{SESSION}.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


@pytest.fixture
def chat(tmp_path: pathlib.Path) -> pathlib.Path:
    """A home holding one session that asks, thinks, calls a tool and answers."""
    home = tmp_path / "qwen"
    _written(
        home,
        "/work",
        [
            _record(
                0,
                "user",
                message={"role": "user", "parts": [{"text": "cut the cycle count"}]},
            ),
            _record(
                1,
                "assistant",
                model="qwen3-coder",
                usageMetadata=_usage(),
                message={
                    "role": "model",
                    "parts": [
                        {"text": "read the kernel first", "thought": True},
                        {
                            "functionCall": {
                                "id": "call-1",
                                "name": "run_shell_command",
                                "args": {"command": "cat perf_takehome.py"},
                            }
                        },
                    ],
                },
            ),
            _record(
                2,
                "tool_result",
                toolCallResult={"callId": "call-1", "status": "success"},
                message={
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "id": "call-1",
                                "name": "run_shell_command",
                                "response": {"output": "def kernel(): ..."},
                            }
                        }
                    ],
                },
            ),
            _record(
                3,
                "assistant",
                model="qwen3-coder",
                usageMetadata=_usage(candidatesTokenCount=7, totalTokenCount=1007),
                message={"role": "model", "parts": [{"text": "done"}]},
            ),
            _record(4, "system", subtype="ui_telemetry", systemPayload={"uiEvent": {}}),
        ],
    )
    return home


def _collected(home: pathlib.Path, **held: Any) -> list[Session]:
    """Every session of ``home``, over the whole of time unless told otherwise."""
    return qwen.collect(
        home, held.get("workspace"), held.get("sessions"), held.get("window", _EVER)
    )


def _of(session: Session, category: str) -> list[Action]:
    """Every slice of one kind, in the order the log put them."""
    return [action for action in session.actions if action.category == category]


def test_a_chat_log_is_read_as_the_session_it_is(chat: pathlib.Path) -> None:
    (session,) = _collected(chat)

    assert session.key == f"qwen:{SESSION}"
    assert session.backend == "qwen"
    assert session.ident == SESSION
    assert session.label == "main"
    assert session.parent is None
    assert session.args["cwd"] == "/work"
    assert session.args["version"] == "0.23.1"
    assert "cut the cycle count" in session.title


def test_the_model_a_session_opened_at_is_what_names_it(chat: pathlib.Path) -> None:
    """Read off the answers, since only they say what answered them."""
    (session,) = _collected(chat)

    assert session.args["model"] == "qwen3-coder"


def test_every_answer_is_a_call_with_the_usage_it_was_billed(
    chat: pathlib.Path,
) -> None:
    """Qwen Code writes a `usageMetadata` per assistant record, so each is a call."""
    (session,) = _collected(chat)

    calls = _of(session, "llm")

    assert [call.args["usage"]["candidatesTokenCount"] for call in calls] == [40, 7]
    assert {call.args["model"] for call in calls} == {"qwen3-coder"}


def test_a_thought_is_reasoning_and_a_text_is_something_said(
    chat: pathlib.Path,
) -> None:
    """One key, `text`, and `thought` is the whole of what tells them apart.

    Read alike, a session would say out loud everything it only thought.
    """
    (session,) = _collected(chat)

    (thinking,) = [call for call in _of(session, "llm") if "thinking" in call.args]
    assert thinking.args["thinking"] == "read the kernel first"
    assert [said.args["text"] for said in _of(session, "message")] == ["done"]


def test_a_tool_call_is_closed_by_the_response_that_names_it(
    chat: pathlib.Path,
) -> None:
    (session,) = _collected(chat)

    (call,) = _of(session, "tool")

    assert call.args["tool"] == "run_shell_command"
    assert call.args["input"] == {"command": "cat perf_takehome.py"}
    assert call.args["output"] == "def kernel(): ..."
    assert call.args["result"]["status"] == "success"
    assert "unfinished" not in call.args
    assert call.end > call.start


def test_a_call_nothing_answered_is_said_to_be_unfinished(
    tmp_path: pathlib.Path,
) -> None:
    """A session cut off mid-call is a call that never came back, and says so."""
    home = tmp_path / "qwen"
    _written(
        home,
        "/work",
        [
            _record(
                0,
                "assistant",
                model="qwen3-coder",
                usageMetadata=_usage(),
                message={
                    "role": "model",
                    "parts": [
                        {"functionCall": {"id": "call-1", "name": "run_shell_command"}}
                    ],
                },
            )
        ],
    )

    (session,) = _collected(home)

    (call,) = _of(session, "tool")
    assert call.args["unfinished"] is True


def test_a_session_of_another_workspace_is_not_this_workspace(
    chat: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The directory names the workspace, so asking for one asks for its own."""
    assert _collected(chat, workspace=tmp_path / "nowhere") == []
    assert len(_collected(chat, workspace=None)) == 1


def test_only_the_sessions_asked_for_are_read(chat: pathlib.Path) -> None:
    assert len(_collected(chat, sessions=(SESSION[:8],))) == 1
    assert _collected(chat, sessions=("no-such-session",)) == []


def test_nothing_outside_the_window_is_read(chat: pathlib.Path) -> None:
    """A trace of a moment holds what happened in it and not the rest."""
    began = _BEGAN.timestamp()

    (session,) = _collected(chat, window=(began + 2.5, began + 3.5))

    assert [call.args["usage"]["candidatesTokenCount"] for call in _of(session, "llm")]
    assert len(_of(session, "llm")) == 1


def test_a_torn_line_is_skipped_rather_than_fatal(chat: pathlib.Path) -> None:
    """Every log here is read while the CLI may still be appending to it."""
    log = next(chat.rglob("*.jsonl"))
    with log.open("a", encoding="utf-8") as file:
        file.write('{"type": "assistant", "timest')

    (session,) = _collected(chat)

    assert len(_of(session, "llm")) == 2
