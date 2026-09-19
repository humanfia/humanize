"""Collector for Pi coding agent sessions.

One `sessions/<workspace>/<started>_<id>.jsonl` per session. The directory is named
after the workspace and the file after the moment it opened and the id it was given,
and neither has to be decoded: the first line of every log is a `session` record
stating the `cwd` outright, so which workspace a session belongs to is read rather
than inferred. Checked against `pi 0.14.2` (`"version": 3`), over the 3503 sessions
on the machine this was written against.

Four kinds of record, and three of them are one line each at the head: `session`
opens it, `model_change` says what answered and `thinking_level_change` how hard it
was asked to think. Pi states both as events rather than on each answer, so a
session that was switched mid-conversation says so where it was switched, and what
the session is named by is the first of them.

The rest are `message`, whose `message.role` is `user`, `assistant` or `toolResult`
-- a vocabulary of its own, where every other backend here answers a tool call with
a user turn carrying a result block. So a `toolResult` is not a turn and must not
open one: read as a prompt it would be a session whose every tool output looked like
something the person asked for.

What a request cost hangs on the assistant message, under names of Pi's own, and
with a `cost` in dollars beside it that Pi worked out itself. Across all 6326 usages
on this machine `input + output + cacheRead + cacheWrite` is exactly `totalTokens`,
so the cached read sits beside what was read rather than inside it -- the opposite of
Grok Build and ZCode, and the difference between a bill and one several times it.
`reasoning` never exceeds `output`, so the thinking is part of what was written.
"""

from __future__ import annotations

import datetime
import pathlib
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

#: What the head of a log says about the session as a whole.
_INFO_FIELDS = ("cwd", "version")


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the Pi sessions asked for.

    Args:
        home: Pi agent directory holding the sessions folder.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Session ids to keep, or None to keep every session.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per log. Pi spawns no sub-agents, so each stands alone.
    """
    collected: list[Session] = []
    for path in sorted((home / "sessions").glob("*/*.jsonl")):
        # The id is the file's own, past the moment it opened: `<started>_<id>`.
        ident = path.stem.partition("_")[2] or path.stem
        if not wanted(sessions, f"pi:{ident}"):
            continue
        actions, info = _parse(path, window)
        # Stated by the log rather than decoded out of the directory it sits in,
        # so a workspace whose name Pi escapes and this does not is a session
        # found rather than one quietly missing from a trace.
        said = info.get("cwd")
        if workspace is not None and (
            not isinstance(said, str) or pathlib.Path(said) != workspace
        ):
            continue
        collected.append(
            Session(
                key=f"pi:{ident}",
                backend="pi",
                ident=ident,
                label="main",
                title=title_of(ident[:8], actions),
                args={"log": str(path), **info},
                actions=actions,
            )
        )
    return collected


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
        kind = record.get("type")
        # The head of the log is read whatever the window says: what a session was
        # run at is not a thing that happened at a moment, and a trace narrowed to
        # the middle of one would otherwise name no model at all.
        if kind == "session":
            for field in _INFO_FIELDS:
                if record.get(field) is not None:
                    info[field] = record[field]
            continue
        if kind == "model_change":
            info.setdefault("provider", record.get("provider"))
            info.setdefault("model", record.get("modelId"))
            continue
        if kind == "thinking_level_change":
            info.setdefault("effort", record.get("thinkingLevel"))
            continue
        stamp = record.get("timestamp")
        if not isinstance(stamp, str):
            continue
        try:
            at = datetime.datetime.fromisoformat(stamp).timestamp()
        except ValueError:
            continue
        if not window[0] <= at <= window[1]:
            continue
        prev = prev or at
        message = mapping(record.get("message"))
        role = message.get("role")

        if role == "user":
            if turn is not None:
                turn.end = max(turn.end, prev, at)
                actions.append(turn)
            prompt = text_of(message.get("content"))
            turn = Action(
                f"turn: {summarize(prompt)}",
                "turn",
                at,
                at,
                {"prompt": truncate(prompt)},
            )
            prev = max(prev, at)
        elif role == "assistant":
            prev = _answered(actions, message, at, prev, pending)
        elif role == "toolResult":
            # Pi's own word for it, and not a turn: read as one, every tool
            # output would look like something the person at the prompt asked.
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
    prev = at
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
            continue
        if kind == "text":
            body = str(block.get("text") or "")
            actions.append(
                Action(
                    f"say: {summarize(body)}",
                    "message",
                    prev,
                    at,
                    {"text": truncate(body)},
                )
            )
            continue
        if kind == "toolCall":
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
    return prev
