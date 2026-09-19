"""Collector for Qwen Code chat logs.

One `chats/<id>.jsonl` per session, under a directory per workspace named after it
the way Claude Code names one -- every character that is not a letter or a digit
replaced by a dash -- so `/home/me/repo` is kept as `-home-me-repo`. Each line is
one record with a `uuid`, the `parentUuid` it answered, the `sessionId` it belongs
to and an ISO `timestamp`, which is the same envelope Claude Code writes; what sits
inside it is not. Qwen Code descends from Gemini CLI and keeps a turn as Gemini's
own `parts`: an assistant record carries `functionCall` or `text` (with `thought`
true for the reasoning it is willing to show), and the `tool_result` that answers
one carries a `functionResponse` naming the call it closes. Checked against
`qwen 0.23.1`, over the 4926 sessions on the machine this was written against.

What a request cost is stated twice and this reads the first: `usageMetadata` on the
assistant record that was billed for it, beside the `model` that answered. The other
is a `ui_telemetry` system record carrying a `qwen-code.api_response` event, which
says the same counts a second time -- read here as the event it is, so that a session
still says what it did where the telemetry was switched off, and so that nothing is
billed twice for one answer.

Gemini's vocabulary rather than Anthropic's, and the two do not line up: across all
11771 usages on this machine `promptTokenCount + candidatesTokenCount` is exactly
`totalTokenCount` and `cachedContentTokenCount` never exceeds the prompt -- so the
cached read is part of what was read rather than beside it, and the thoughts are
part of what was written rather than beside it. Whoever prices these is told the
counts as they are written; what they mean is said where they are priced.
"""

from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING, Any, cast

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

if TYPE_CHECKING:
    import pathlib

#: What a record says about the session as a whole rather than about itself. Taken
#: wherever one states it, since only some kinds of record carry each.
_INFO_FIELDS = ("cwd", "version", "gitBranch", "sessionId", "contextWindowSize")

#: What a `system` record carries beside its subtype, which is the whole of what one
#: is: Qwen Code puts the event under `systemPayload` and nothing else of it matters
#: to a reader.
_SYSTEM_FIELDS = ("subtype", "systemPayload")


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the Qwen Code sessions asked for.

    Args:
        home: Qwen Code configuration directory holding the projects folder.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Session ids to keep, or None to keep every session.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per chat log. Qwen Code spawns no sub-agents, so each stands
        alone and none has a parent.
    """
    projects = home / "projects"
    folder = "*" if workspace is None else re.sub(r"[^a-zA-Z0-9]", "-", str(workspace))
    collected: list[Session] = []
    for path in sorted(projects.glob(f"{folder}/chats/*.jsonl")):
        key = f"qwen:{path.stem}"
        if not wanted(sessions, key):
            continue
        actions, info = _parse(path, window)
        collected.append(
            Session(
                key=key,
                backend="qwen",
                ident=path.stem,
                label="main",
                title=title_of(path.stem[:8], actions),
                args={"log": str(path), **info},
                actions=actions,
            )
        )
    return collected


def _parse(
    path: pathlib.Path, window: tuple[float, float]
) -> tuple[list[Action], dict[str, Any]]:
    """Turns one chat log into prompt, reasoning, tool and message slices."""
    actions: list[Action] = []
    info: dict[str, Any] = {}
    pending: dict[str, Action] = {}
    turn: Action | None = None
    prev = 0.0
    for record in records(path):
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
        for field in _INFO_FIELDS:
            if record.get(field) is not None:
                info[field] = record[field]
        parts = _parts(record)
        kind = record.get("type")

        if kind == "user":
            if turn is not None:
                turn.end = max(turn.end, prev, at)
                actions.append(turn)
            prompt = "\n".join(
                str(part["text"]) for part in parts if isinstance(part.get("text"), str)
            )
            turn = Action(
                f"turn: {summarize(prompt)}",
                "turn",
                at,
                at,
                {"prompt": truncate(prompt)},
            )
            prev = max(prev, at)
        elif kind == "assistant":
            prev = _answered(actions, record, parts, at, prev, pending, info)
        elif kind == "tool_result":
            for part in parts:
                answer = mapping(part.get("functionResponse"))
                call = pending.pop(str(answer.get("id")), None)
                if call is None:
                    continue
                call.end = at
                # Wrapped in a list so that the shared reader looks inside it
                # the way it looks inside a content block: Gemini answers a call
                # with `{"output": ...}` or `{"error": ...}`, and a mapping read
                # as a whole is a tool whose every output came back empty.
                call.args["output"] = truncate(text_of([answer.get("response")]))
                result = mapping(record.get("toolCallResult"))
                if result:
                    call.args["result"] = truncate(result, 512)
                    call.args["error"] = bool(result.get("error"))
            prev = max(prev, at)
        elif kind == "system":
            details = {key: record[key] for key in _SYSTEM_FIELDS if key in record}
            actions.append(
                Action(
                    f"system: {record.get('subtype')}",
                    "event",
                    at,
                    at,
                    truncate(details, 512),
                )
            )
            prev = max(prev, at)

    closing = max((action.end for action in actions), default=prev)
    for call in pending.values():
        call.end = max(call.start, closing)
        call.args["unfinished"] = True
    if turn is not None:
        turn.end = max(turn.end, closing)
        actions.append(turn)
    return actions, info


def _parts(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The `parts` of a record's message, which is where Gemini keeps a turn."""
    held = mapping(record.get("message")).get("parts")
    if not isinstance(held, list):
        return []
    return [
        cast("dict[str, Any]", part)
        for part in cast("list[Any]", held)
        if isinstance(part, dict)
    ]


def _answered(
    actions: list[Action],
    record: dict[str, Any],
    parts: list[dict[str, Any]],
    at: float,
    prev: float,
    pending: dict[str, Action],
    info: dict[str, Any],
) -> float:
    """Records one assistant record, which is one model call and what it emitted.

    One slice per record rather than per response id: Qwen Code writes a
    `usageMetadata` on each of these and that is the smallest thing it states a
    cost for, so a record is a call and two of them are two calls.
    """
    model = record.get("model")
    # The first answer is what the session opened at, which is what a session that
    # was switched to another model mid-conversation is still named by.
    if "model" not in info and isinstance(model, str):
        info["model"] = model
    think = Action(
        "think",
        "llm",
        prev,
        at,
        {"model": model, "usage": record.get("usageMetadata")},
    )
    actions.append(think)
    prev = at
    for part in parts:
        body = part.get("text")
        if isinstance(body, str) and body:
            if part.get("thought"):
                think.args["thinking"] = truncate(
                    f"{think.args.get('thinking', '')}\n{body}".strip()
                )
                think.name = f"think: {summarize(body)}"
                continue
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
        call = mapping(part.get("functionCall"))
        if not call:
            continue
        named = str(call.get("name"))
        slice_ = Action(
            label(named, call.get("args")),
            "tool",
            at,
            at,
            {"tool": named, "input": truncate(call.get("args"))},
        )
        pending[str(call.get("id"))] = slice_
        actions.append(slice_)
    return prev
