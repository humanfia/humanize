"""Collector for Antigravity conversations, which are protobuf in a database apiece.

A directory of `conversations/<id>.db`, one SQLite file per conversation, whose
`steps` table holds a row per step with its `metadata` as a protobuf message --
and no schema anywhere on this machine to read that message against. So it is
read by field number, which is the half of the wire format that describes itself;
:mod:`hmz.runtime.tracing.readers._wire` is that reading, and what the numbers
mean is worked out here. Checked against `agy` built on go1.28, over the 21
conversations on the machine this was written against.

Which workspace a conversation belongs to is not in the conversation. It is in
`cache/last_conversations.json`, a map of workspace path to the last conversation
opened there, and `conversation_summaries.db` beside it carries the title, the
step count and which conversation a nested one hangs from.

What a step cost is field 9 of its metadata, and the numbers under it were read
off the corpus rather than off a schema:

* `2` is the prompt and `5` the part of it that was cached -- a step with a cache
  hit has `2` down by what `5` is up, so the cached read sits *beside* what was
  read rather than inside it, and both are counted.
* `3` is what was written, and is exactly `9 + 10` on every step here that has
  both -- the thinking and the answer -- so it is the whole of the output and
  needs nothing added to it.
* `1` is a stable 1300-1320 whatever the conversation, which is the tool schemas
  the model is handed every step. Counted as input, since that is what it is.

They are given names here and handed on under those, because a caller pricing a
turn cannot be asked to know that field 3 of an unnamed message is the output.
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any, cast

from hmz.runtime.tracing.readers import _wire
from hmz.runtime.tracing.session import (
    Action,
    Session,
    summarize,
    title_of,
    truncate,
    wanted,
)

if TYPE_CHECKING:
    import pathlib

#: Where the conversations are, under Antigravity's home.
CONVERSATIONS = "conversations"

#: What says which workspace a conversation was opened in, and what says the rest.
_OPENED = "cache/last_conversations.json"
_SUMMARIES = "conversation_summaries.db"

#: Field 9 of a step's metadata, by the names the corpus says they hold.
_COUNTS = {
    1: "toolPromptTokens",
    2: "promptTokens",
    3: "outputTokens",
    5: "cachedTokens",
    9: "thoughtsTokens",
    10: "answerTokens",
}

#: Where that message keeps what answered the step, and the id of the answer.
_MODEL, _RESPONSE = 7, 11

#: Where a step keeps when it began and when it was last written to.
_BEGAN, _ENDED = 1, 6


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the Antigravity conversations asked for.

    Args:
        home: Antigravity's own directory, which holds the conversations.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Session ids to keep, or None to keep every session.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per conversation, with a nested one hung off its parent.
    """
    folder = home / CONVERSATIONS
    if not folder.is_dir():
        return []
    opened = _opened(home)
    summaries = _summaries(home)
    kept = None if workspace is None else opened.get(str(workspace))
    collected: list[Session] = []
    for path in sorted(folder.glob("*.db")):
        ident = path.stem
        if not wanted(sessions, f"agy:{ident}"):
            continue
        # The map says which conversation a workspace last opened, so a
        # workspace asked for keeps that one and nothing else. A conversation
        # no workspace claims is nobody's, and is left out of a narrowed trace
        # rather than handed to whichever workspace asked.
        if workspace is not None and ident != kept:
            continue
        actions = _actions(path, window)
        held = summaries.get(ident, {})
        title = str(held.get("title") or "")
        parent = str(held.get("parent_conversation_id") or "")
        collected.append(
            Session(
                key=f"agy:{ident}",
                backend="agy",
                ident=ident,
                label="main" if not parent else "subagent",
                title=f"{ident[:8]} · {summarize(title, 60)}"
                if title
                else title_of(ident[:8], actions),
                parent=f"agy:{parent}" if parent else None,
                args=_args(path, held, actions),
                actions=actions,
            )
        )
    held = {one.key for one in collected}
    for one in collected:
        if one.parent not in held:
            one.parent = None
    return collected


def _args(
    path: pathlib.Path, summary: dict[str, Any], actions: list[Action]
) -> dict[str, Any]:
    """What the conversation says about itself, as a session banner shows it."""
    args: dict[str, Any] = {"log": str(path)}
    for name in ("project_id", "agent_name", "preview"):
        if summary.get(name):
            args[name] = summary[name]
    model = next(
        (
            action.args["model"]
            for action in actions
            if action.category == "llm" and action.args.get("model")
        ),
        None,
    )
    if model:
        args["model"] = model
    return args


def _opened(home: pathlib.Path) -> dict[str, str]:
    """Which conversation each workspace last opened, as the cache writes it."""
    try:
        held = json.loads((home / _OPENED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(held, dict):
        return {}
    opened = cast("dict[Any, Any]", held)
    return {str(where): str(which) for where, which in opened.items()}


def _summaries(home: pathlib.Path) -> dict[str, dict[str, Any]]:
    """What the summaries database says about each conversation, or nothing at all."""
    path = home / _SUMMARIES
    if not path.is_file():
        return {}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    connection.row_factory = sqlite3.Row
    try:
        return {
            str(row["conversation_id"]): dict(row)
            for row in connection.execute("select * from conversation_summaries")
        }
    except sqlite3.Error:
        return {}
    finally:
        connection.close()


def _actions(path: pathlib.Path, window: tuple[float, float]) -> list[Action]:
    """One slice per step of a conversation, in the order the steps were taken."""
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        rows = list(
            connection.execute(
                "select idx, step_type, status, metadata from steps order by idx"
            )
        )
    except sqlite3.Error:
        return []
    finally:
        connection.close()

    actions: list[Action] = []
    for idx, kind, status, held in rows:
        if not isinstance(held, (bytes, bytearray)):
            continue
        metadata = bytes(held)
        began = _wire.moment(metadata, _BEGAN)
        if began is None or not window[0] <= began <= window[1]:
            continue
        ended = _wire.moment(metadata, _ENDED) or began
        usage = _wire.message(metadata, 9)
        if usage is None:
            # A step that ran no model -- the person's own turn, a tool coming
            # back -- is an event rather than a call, and is not billed.
            actions.append(
                Action(
                    f"step {idx}",
                    "event",
                    began,
                    max(began, ended),
                    {"step_type": kind, "status": status},
                )
            )
            continue
        counted = _wire.numbers(usage)
        actions.append(
            Action(
                "think",
                "llm",
                began,
                max(began, ended),
                truncate(
                    {
                        "model": _wire.text(usage, _MODEL),
                        "response": _wire.text(usage, _RESPONSE),
                        "usage": {
                            name: counted[number]
                            for number, name in _COUNTS.items()
                            if number in counted
                        },
                        "step_type": kind,
                    }
                ),
            )
        )
    return actions
