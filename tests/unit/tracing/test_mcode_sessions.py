"""MiniMax Code sessions, read back out of the directory a session keeps its messages in.

The records are the shapes `mcode 0.5.9` wrote for a turn that ran a command and answered: a
prompt inside the reminders it was sent with, an answer that reached for a tool, the tool's
result, and the answer after it -- each stamped in milliseconds. Which workspace the session
was in is the database's to say, so a database is written beside them saying it.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from typing import TYPE_CHECKING

from hmz.coganchor import backends
from hmz.runtime.tracing.readers import mcode

if TYPE_CHECKING:
    from pathlib import Path

#: The session, as MiniMax Code names it.
_SESSION = "mvs_cbdd52bca9344bd39afc47c4ab057b75"

#: What the reminders in front of the prompt come to, and the prompt itself.
_REMINDED = "<system-reminder>\nyou are in a terminal\n</system-reminder>\n\n"
_PROMPT = "run it"


def _usage(given: int, cached: int, written: int) -> dict[str, object]:
    return {
        "input": given,
        "output": written,
        "cacheRead": cached,
        "cacheWrite": 0,
        "totalTokens": given + cached + written,
    }


def _home(tmp_path: Path, workspace: Path) -> Path:
    """A data directory holding one session of one turn, and the record saying where it ran."""
    home = tmp_path / ".minimax"
    encoded = base64.urlsafe_b64encode(_SESSION.encode()).decode().rstrip("=")
    at = (
        home
        / "v2"
        / "sessions"
        / "2026"
        / "09"
        / "30"
        / f"01-33-02-085-session_{encoded}"
    )
    at.mkdir(parents=True)
    said = f"{_REMINDED}{_PROMPT}"
    messages = [
        {
            "role": "user",
            "timestamp": 1790731982546,
            "content": [{"type": "text", "text": said}],
            "canonicalTextRange": {
                "startOffset": len(_REMINDED),
                "endOffset": len(said),
            },
        },
        {
            "role": "assistant",
            "provider": "custom_provider:gateway",
            "model": "minimax-m3",
            "usage": _usage(60, 40, 7),
            "stopReason": "toolUse",
            "timestamp": 1790731982608,
            "content": [
                {"type": "thinking", "thinking": "list it"},
                {
                    "type": "toolCall",
                    "id": "call_1",
                    "name": "bash",
                    "arguments": {"command": "ls"},
                },
            ],
        },
        {
            "role": "toolResult",
            "toolCallId": "call_1",
            "toolName": "bash",
            "timestamp": 1790731982751,
            "content": [{"type": "text", "text": "x.py\n"}],
        },
        {
            "role": "assistant",
            "provider": "custom_provider:gateway",
            "model": "minimax-m3",
            "usage": _usage(70, 50, 5),
            "stopReason": "stop",
            "timestamp": 1790731982776,
            "content": [{"type": "text", "text": "there is x.py"}],
        },
    ]
    (at / "messages.jsonl").write_text(
        "".join(
            json.dumps({"message_id": f"m{index}", "message": one}) + "\n"
            for index, one in enumerate(messages)
        )
    )
    database = home / "v2" / "sqlite" / "runtime-state.sqlite"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE local_runtime_sessions "
            "(session_id TEXT PRIMARY KEY, record_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO local_runtime_sessions VALUES (?, ?)",
            (
                _SESSION,
                json.dumps({"sessionId": _SESSION, "workspaceDir": str(workspace)}),
            ),
        )
    connection.close()
    return home


def test_a_session_is_its_turn_its_answers_and_the_tool_between_them(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "work"
    home = _home(tmp_path, workspace)

    (session,) = mcode.collect(home, workspace, None, (0, 1e12))

    assert session.key == f"mcode:{_SESSION}"
    assert session.args["cwd"] == str(workspace)
    assert session.args["model"] == "minimax-m3"
    names = [action.name for action in session.actions]
    # The turn is named for what was typed, not for the reminders it was sent inside.
    assert names[-1] == f"turn: {_PROMPT}"
    assert "think: list it" in names
    assert "bash: ls" in names
    assert "say: there is x.py" in names
    (tool,) = (action for action in session.actions if action.name == "bash: ls")
    assert tool.args["output"] == "x.py\n"


def test_a_session_in_another_workspace_is_not_this_one(tmp_path: Path) -> None:
    home = _home(tmp_path, tmp_path / "work")

    assert mcode.collect(home, tmp_path / "elsewhere", None, (0, 1e12)) == []
    assert mcode.collect(home, None, ("mcode:nobody",), (0, 1e12)) == []


def test_the_log_is_found_under_the_session_it_is_named_for_encoded(
    tmp_path: Path,
) -> None:
    """Its directory names the session in URL-safe base64, which the profile writes in."""
    home = _home(tmp_path, tmp_path / "work")
    profile = backends.named("mcode")
    assert profile is not None

    (pattern,) = profile.logged(_SESSION)

    (found,) = home.glob(pattern)
    assert found.name == "messages.jsonl"
