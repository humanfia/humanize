"""Collector for the conversations humanize keeps for litellm.

One JSONL file a conversation, written by humanize's own driver: a `session` header naming
the conversation it was forked from, then one `message` row a message, an answer carrying the
model and what its request spent.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, cast

from hmz.runtime.tracing.session import (
    Action,
    Session,
    mapping,
    records,
    summarize,
    title_of,
    truncate,
    wanted,
)


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the litellm conversations asked for, and the forks cut from them.

    Args:
        home: A directory holding litellm's `sessions` folder.
        workspace: Absolute workspace path to keep, or None for every workspace.
        sessions: Session ids to keep, or None to keep every session.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per conversation file, a fork linked to the one it was cut from.
    """
    logs: dict[str, tuple[pathlib.Path, dict[str, Any]]] = {}
    for path in sorted((home / "sessions").glob("*.jsonl")):
        header = _header(path)
        ident = header.get("id")
        if not isinstance(ident, str) or not ident:
            continue
        cwd = header.get("cwd")
        if workspace is not None and pathlib.Path(str(cwd)) != workspace:
            continue
        logs[ident] = (path, header)

    kept = {ident for ident in logs if wanted(sessions, f"litellm:{ident}")}
    collected: list[Session] = []
    for ident in sorted(kept):
        path, header = logs[ident]
        actions = _parse(path, window)
        parent = header.get("parent")
        short = ident.removeprefix("session-")[:8]
        collected.append(
            Session(
                key=f"litellm:{ident}",
                backend="litellm",
                ident=ident,
                label="main",
                title=title_of(short, actions),
                parent=f"litellm:{parent}" if isinstance(parent, str) else None,
                args={
                    "log": str(path),
                    "model": header.get("model"),
                    "cwd": header.get("cwd"),
                },
                actions=actions,
            )
        )
    return collected


def _header(path: pathlib.Path) -> dict[str, Any]:
    """Reads a conversation's header without letting one damaged file stop collection."""
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            loaded: object = json.loads(stream.readline())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    header = cast("dict[str, Any]", loaded)
    return header if header.get("type") == "session" else {}


def _parse(path: pathlib.Path, window: tuple[float, float]) -> list[Action]:
    """Turns one conversation into a turn per prompt, with its thinking and its answer."""
    actions: list[Action] = []
    turn: Action | None = None
    for record in records(path):
        moment = record.get("timestamp")
        if not isinstance(moment, (int, float)) or isinstance(moment, bool):
            continue
        at = float(moment)
        if not window[0] <= at <= window[1] or record.get("type") != "message":
            continue
        message = mapping(record.get("message"))
        content = message.get("content")
        body = content if isinstance(content, str) else ""
        if message.get("role") == "user":
            if turn is not None:
                actions.append(turn)
            turn = Action(
                f"turn: {summarize(body)}", "turn", at, at, {"prompt": truncate(body)}
            )
            continue
        if message.get("role") != "assistant":
            continue
        start = turn.start if turn is not None else at
        think = Action("think", "llm", start, at, {"model": message.get("model")})
        if message.get("usage") is not None:
            think.args["usage"] = truncate(message["usage"])
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            think.name = f"think: {summarize(reasoning)}"
            think.args["thinking"] = truncate(reasoning)
        actions.append(think)
        actions.append(
            Action(
                f"say: {summarize(body)}", "message", at, at, {"text": truncate(body)}
            )
        )
        if turn is not None:
            turn.end = max(turn.end, at)
            actions.append(turn)
            turn = None
    if turn is not None:
        actions.append(turn)
    return actions
