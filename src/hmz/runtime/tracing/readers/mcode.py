"""Collector for MiniMax Code sessions.

One directory per session under `v2/sessions/<year>/<month>/<day>/`, named for the moment it
opened and `session_` and the session's id in URL-safe base64, and in it `messages.jsonl`: the
conversation as the model was sent it, a record per message. Checked against `mcode 0.5.9`.

MiniMax Code runs the pi agent's loop, and the messages are pi's: a `message` whose `role` is
`user`, `assistant` or `toolResult`, stamped in milliseconds, a tool call being a `toolCall`
block of the assistant's and its answer a `toolResult` of its own rather than a user turn -- so
that one must not open a turn. What a request cost hangs on the assistant message under pi's
names too, the cache read beside the input rather than inside it.

Two things are its own. A prompt is sent inside the reminders the CLI puts in front of it, and
`canonicalTextRange` says where in that text what the person typed is -- which is what a turn
is named after. And what a session is does not say which workspace it was in: that is kept in
the database a session is resumed out of, as the record the session was opened with, so that
is read for it, and a session it says nothing about is one no workspace can claim.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import pathlib
import sqlite3
from typing import Any, cast

from hmz.runtime.tracing.session import (
    Action,
    Session,
    label,
    mapping,
    records,
    summarize,
    text_of,
    title_of,
    truncate,
    wanted,
)

#: Where the sessions are, under its home.
_LOGS = "v2/sessions/*/*/*/*-session_*/messages.jsonl"

#: What a session's directory calls it, in front of the id.
_NAMED = "-session_"

#: The database a session's record is kept in, under its home.
_DATABASE = "v2/sqlite/runtime-state.sqlite"


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the MiniMax Code sessions asked for.

    Args:
        home: MiniMax Code's data directory.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Session ids to keep, or None to keep every session.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per log, each standing alone: what a subagent of its did is
        in the log of the session that started it.
    """
    places = _workspaces(home)
    collected: list[Session] = []
    for path in sorted(home.glob(_LOGS)):
        ident = _ident(path.parent.name)
        if not ident or not wanted(sessions, f"mcode:{ident}"):
            continue
        said = places.get(ident)
        if workspace is not None and (said is None or pathlib.Path(said) != workspace):
            continue
        actions, info = _parse(path, window)
        if said is not None:
            info["cwd"] = said
        collected.append(
            Session(
                key=f"mcode:{ident}",
                backend="mcode",
                ident=ident,
                label="main",
                title=title_of(ident[:12], actions),
                args={"log": str(path), **info},
                actions=actions,
            )
        )
    return collected


def _ident(directory: str) -> str:
    """The session a directory is named for, or "" for one that is named for none."""
    _, found, encoded = directory.partition(_NAMED)
    if not found or not encoded:
        return ""
    try:
        return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError):
        return ""


def _workspaces(home: pathlib.Path) -> dict[str, str]:
    """Which workspace each session was opened in, as the database it is resumed out of says.

    Read only, and nothing at all where there is no database or it cannot be read: a trace is
    not worth failing over a database being written to.
    """
    held: dict[str, str] = {}
    database = home / _DATABASE
    if not database.is_file():
        return held
    with contextlib.suppress(sqlite3.Error):
        connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
        try:
            rows = connection.execute(
                "SELECT session_id, record_json FROM local_runtime_sessions"
            ).fetchall()
        finally:
            connection.close()
        for ident, record in rows:
            with contextlib.suppress(TypeError, ValueError):
                said = mapping(json.loads(record)).get("workspaceDir")
                if isinstance(said, str) and said:
                    held[str(ident)] = said
    return held


def _prompt(message: dict[str, Any]) -> str:
    """What the person typed, out of the reminders it was sent inside."""
    text = text_of(message.get("content"))
    span = mapping(message.get("canonicalTextRange"))
    start, end = span.get("startOffset"), span.get("endOffset")
    if (
        isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start < end <= len(text)
    ):
        return text[start:end]
    return text


def _parse(
    path: pathlib.Path, window: tuple[float, float]
) -> tuple[list[Action], dict[str, Any]]:
    """Turns one session log into prompt, reasoning, tool and message slices."""
    actions: list[Action] = []
    info: dict[str, Any] = {}
    pending: dict[str, Action] = {}
    turn: Action | None = None
    prev = 0.0
    for record in records(path):
        message = mapping(record.get("message"))
        stamp = message.get("timestamp")
        if not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
            continue
        at = stamp / 1000
        if not window[0] <= at <= window[1]:
            continue
        prev = prev or at
        role = message.get("role")
        if role == "user":
            if turn is not None:
                turn.end = max(turn.end, prev, at)
                actions.append(turn)
            prompt = _prompt(message)
            turn = Action(
                f"turn: {summarize(prompt)}",
                "turn",
                at,
                at,
                {"prompt": truncate(prompt)},
            )
            prev = max(prev, at)
        elif role == "assistant":
            info.setdefault("provider", message.get("provider"))
            info.setdefault("model", message.get("model"))
            prev = _answered(actions, message, at, prev, pending)
        elif role == "toolResult":
            # Not a turn: read as one, every tool output would look like something the
            # person at the prompt asked.
            call = pending.pop(str(message.get("toolCallId")), None)
            if call is not None:
                call.end = at
                call.args["output"] = truncate(text_of(message.get("content")))
            prev = max(prev, at)

    closing = max((action.end for action in actions), default=prev)
    for call in pending.values():
        call.end = max(call.start, closing)
        call.args["unfinished"] = True
    if turn is not None:
        turn.end = max(turn.end, closing)
        actions.append(turn)
    return actions, info


def _answered(
    actions: list[Action],
    message: dict[str, Any],
    at: float,
    prev: float,
    pending: dict[str, Action],
) -> float:
    """Records one assistant message, which is one model call and what it emitted."""
    think = Action(
        "think",
        "llm",
        prev,
        at,
        {
            "model": message.get("model"),
            "provider": message.get("provider"),
            "usage": message.get("usage"),
            "stop": message.get("stopReason"),
        },
    )
    actions.append(think)
    content = message.get("content")
    blocks = (
        [
            cast("dict[str, Any]", block)
            for block in cast("list[Any]", content)
            if isinstance(block, dict)
        ]
        if isinstance(content, list)
        else []
    )
    for block in blocks:
        kind = block.get("type")
        if kind == "thinking":
            reasoning = str(block.get("thinking") or "")
            if reasoning:
                think.args["thinking"] = truncate(
                    f"{think.args.get('thinking', '')}\n{reasoning}".strip()
                )
                think.name = f"think: {summarize(reasoning)}"
        elif kind == "text":
            body = str(block.get("text") or "")
            actions.append(
                Action(
                    f"say: {summarize(body)}",
                    "message",
                    at,
                    at,
                    {"text": truncate(body)},
                )
            )
        elif kind == "toolCall":
            named = str(block.get("name"))
            call = Action(
                label(named, block.get("arguments")),
                "tool",
                at,
                at,
                {"tool": named, "input": truncate(block.get("arguments"))},
            )
            pending[str(block.get("id"))] = call
            actions.append(call)
    return at
