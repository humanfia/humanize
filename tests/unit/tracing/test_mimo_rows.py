"""What mimocode's database holds that opencode's does not, and the other way round.

mimocode is a fork of opencode and keeps the same three tables, so the reading is
shared and `test_opencode_rows.py` is where the reading itself is held to account.
What is here is the divergence, which is the part a shared reader can get wrong: the
fork dropped the two columns that say what a conversation ran at, so a query naming
them reads back no sessions at all, and what the conversation was answered by has to
come from its first answer instead.
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing.readers import mimo

if TYPE_CHECKING:
    import pathlib

SESSION = "ses_-ffe5f4c4d4f5fffeVggl0vZYz"

_BEGAN = 1_789_721_227_000
_EVER = (-math.inf, math.inf)

#: mimocode's own `session`, which is opencode's without `model` and `agent` and
#: with five of its own, and its `message`, which adds `agent_id`.
_SCHEMA = """
create table session (
  id text primary key, project_id text, workspace_id text, parent_id text,
  slug text, directory text, title text, version text, share_url text,
  summary_additions int, summary_deletions int, summary_files int,
  summary_diffs text, revert text, permission text, time_created int,
  time_updated int, time_compacting int, time_archived int,
  context_from text, context_watermark int, last_checkpoint_message_id text,
  prompt text, auto_worktree_hint_sent int
);
create table message (
  id text primary key, session_id text, agent_id text, time_created int,
  time_updated int, data text
);
create table part (
  id text primary key, message_id text, session_id text, time_created int,
  time_updated int, data text
);
"""


def _database(home: pathlib.Path, *, directory: str = "/work") -> None:
    """A mimocode database holding one answered conversation."""
    home.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(home / mimo.DATABASE)
    connection.executescript(_SCHEMA)
    connection.execute(
        "insert into session (id, parent_id, directory, title, version, "
        "time_created) values (?,?,?,?,?,?)",
        (SESSION, None, directory, "reply with ok", "0.1.14", _BEGAN),
    )
    connection.execute(
        "insert into message (id, session_id, agent_id, time_created, "
        "time_updated, data) values (?,?,?,?,?,?)",
        (
            "msg_1",
            SESSION,
            "agent-1",
            _BEGAN + 1000,
            _BEGAN + 1200,
            json.dumps(
                {
                    "role": "assistant",
                    "modelID": "claude-sonnet-4-5",
                    "providerID": "anthropic",
                    "tokens": {
                        "input": 120,
                        "output": 9,
                        "reasoning": 0,
                        "cache": {"read": 0, "write": 0},
                    },
                }
            ),
        ),
    )
    connection.execute(
        "insert into part (id, message_id, session_id, time_created, data) "
        "values (?,?,?,?,?)",
        (
            "prt_1",
            "msg_1",
            SESSION,
            _BEGAN + 1100,
            json.dumps({"type": "text", "text": "ok"}),
        ),
    )
    connection.commit()
    connection.close()


@pytest.fixture
def home(tmp_path: pathlib.Path) -> pathlib.Path:
    """A share directory whose mimocode database holds one conversation."""
    where = tmp_path / "mimocode"
    _database(where)
    return where


def _collected(home: pathlib.Path, **held: Any) -> list[Any]:
    return mimo.collect(
        home, held.get("workspace"), held.get("sessions"), held.get("window", _EVER)
    )


def test_a_schema_missing_the_columns_the_original_has_still_reads(
    home: pathlib.Path,
) -> None:
    """The fork has no `model` and no `agent`, and a query naming them reads none.

    Which is the whole reason the session row is asked for by `*` rather than by
    the names the original happens to carry.
    """
    (session,) = _collected(home)

    assert session.key == f"mimo:{SESSION}"
    assert session.backend == "mimo"
    assert session.args["cwd"] == "/work"
    assert session.args["version"] == "0.1.14"
    assert session.args["database"] == mimo.DATABASE


def test_what_a_conversation_ran_at_comes_off_its_first_answer(
    home: pathlib.Path,
) -> None:
    """The fork keeps no model on the conversation, so its answers are asked."""
    (session,) = _collected(home)

    assert session.args["model"] == "claude-sonnet-4-5"
    assert session.args["provider"] == "anthropic"


def test_a_turn_is_billed_by_what_the_message_says(home: pathlib.Path) -> None:
    (session,) = _collected(home)

    (call,) = [action for action in session.actions if action.category == "llm"]

    assert call.args["usage"]["output"] == 9
    assert call.args["usage"]["cache"] == {"read": 0, "write": 0}


def test_a_session_of_another_workspace_is_not_this_workspace(
    home: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    assert len(_collected(home, workspace=None)) == 1
    assert _collected(home, workspace=tmp_path / "nowhere") == []


def test_a_home_with_no_database_is_a_backend_with_nothing_to_say(
    tmp_path: pathlib.Path,
) -> None:
    assert mimo.collect(tmp_path / "nowhere", None, None, _EVER) == []
