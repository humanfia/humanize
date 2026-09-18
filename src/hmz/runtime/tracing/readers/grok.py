"""Collector for Grok Build session updates.

What `updates.jsonl` holds is the protocol's own notification stream, written down. Every line
is one `session/update` -- `method`, `params.sessionId`, `params.update` -- exactly as the
Agent Client Protocol sends it to a client, with Grok Build's own additions carried on
`_x.ai/session/update` beside it and a `params._meta` bolted onto each. That is the same
stream :mod:`hmz.coganchor.agents.grok` reads to drive a turn, which is why the record kinds
here are the kinds its `_told` already names, and why the two transports read alike: `grok
agent … stdio` is handed these notifications and `grok --output-format streaming-json` prints
them flattened, and both write this file for the session they are taking a turn in. Checked
against `grok 1.0.24 (68e414c661e3)`, on a held-open turn and a one-shot turn of the same
conversation.

Written down is not the same as streamed, in two ways that matter. The words arrive live a
fragment at a time and land here whole -- across 1500 logs on this machine no two
`agent_message_chunk` records ever shared a model call, so a response is one record rather
than one record a word. And `response_completed`, which is the live stream's per-response
count, is not written at all: what says what a turn cost is Grok Build's own
`turn_completed`, once per turn, whose `usage` counts the whole of it. So a turn slice is
where the tokens hang here, rather than the model call, because a turn is the smallest thing
this log states a cost for.
"""

from __future__ import annotations

import pathlib
import urllib.parse
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

#: The tool's own facts, which Grok Build hangs off the update rather than putting beside its
#: input: what the tool is called, which family it belongs to and whether running it can
#: change anything. `title` on a `tool_call` is the tool's name too, and this is what says so
#: when a later update has rewritten that title into a sentence about the call.
_TOOL = "x.ai/tool"

#: The statuses that end a tool call, out of the four the protocol has words for. `pending` and
#: `in_progress` are the other two, and a call is still running under either -- so they are not
#: taken as an answer, whose text and moment would otherwise be the call's description and the
#: moment it started. Grok Build 1.0.24 states neither, sending the call's status only on the
#: update it finishes on; the protocol defines them, and a reader that read one as an ending
#: would be wrong quietly rather than loudly.
_ENDED = ("completed", "failed")

#: How much of a session id names it. Grok Build mints a UUIDv7, whose leading characters are
#: the millisecond it was minted at rather than anything about which session it is: across the
#: 5506 sessions on the machine this was written against, the first eight characters -- what
#: every other reader here shortens an id to -- came to 184 distinct names, one of them worn by
#: 204 different sessions. Eighteen reaches past the version nibble into the random part and
#: told all 5506 apart. Kept as a prefix of the id rather than as the interesting characters
#: pulled out of the middle, so that the id a session slice shows is one `--sessions` takes.
_SHORT = 18


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the Grok Build sessions and the sub-agents they spawned.

    Args:
        home: Grok Build home directory holding the sessions folder.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Session ids to keep, or None to keep every session. A kept
            session pulls in the sub-agents it spawned.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per update log, with sub-agents linked to their spawner.
    """
    logs: dict[str, tuple[pathlib.Path, str]] = {}
    for folder in sorted((home / "sessions").glob("*")):
        # A directory per workspace, named after it percent-encoded: `/home/me/repo` is kept
        # as `%2Fhome%2Fme%2Frepo`. Decoded rather than encoded back, so that a character
        # Grok Build escapes and this does not is a session found rather than one missed.
        cwd = urllib.parse.unquote(folder.name)
        if workspace is not None and pathlib.Path(cwd) != workspace:
            continue
        for path in sorted(folder.glob("*/updates.jsonl")):
            logs[path.parent.name] = (path, cwd)

    # The id names the directory, so what was asked for is known before a line is read. What
    # a session spawned is not: it is stated inside the log, so the sub-agents of a kept
    # session are reached by parsing outwards from it rather than by a pass over every log.
    parsed: dict[str, tuple[list[Action], dict[str, Any]]] = {}
    frontier = {ident for ident in logs if wanted(sessions, f"grok:{ident}")}
    while frontier:
        for ident in sorted(frontier):
            parsed[ident] = _parse(logs[ident][0], window)
        frontier = {
            str(action.spawn).removeprefix("grok:")
            for ident in frontier
            for action in parsed[ident][0]
            if action.spawn
        } & (logs.keys() - parsed.keys())

    collected = [
        Session(
            key=f"grok:{ident}",
            backend="grok",
            ident=ident,
            label="main",
            title=title_of(ident[:_SHORT], parsed[ident][0]),
            args={
                "log": str(logs[ident][0]),
                "cwd": logs[ident][1],
                **parsed[ident][1],
            },
            actions=parsed[ident][0],
        )
        for ident in sorted(parsed)
    ]
    by_key = {item.key: item for item in collected}
    for owner in collected:
        for action in owner.actions:
            child = by_key.get(action.spawn or "")
            if child is None:
                continue
            # Only the parent knows what it started one for: a spawned session's own log says
            # nothing about being a sub-agent, so its row is named off the spawn that made it.
            child.parent = owner.key
            named = str(action.args.get("subagent_type") or "subagent")
            told = action.args.get("description")
            child.label = f"{named} · {told}" if told else named
    return collected


def _parse(
    path: pathlib.Path, window: tuple[float, float]
) -> tuple[list[Action], dict[str, Any]]:
    """Turns one update log into turn, reasoning, tool and message slices.

    Args:
        path: The `updates.jsonl` of one session.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        The slices, and what the log says about the session as a whole.
    """
    actions: list[Action] = []
    info: dict[str, Any] = {}
    pending: dict[str, Action] = {}
    streams: dict[tuple[Any, Any], Action] = {}
    turn: Action | None = None
    think: Action | None = None
    prev = 0.0
    for record in records(path):
        params = mapping(record.get("params"))
        meta = mapping(params.get("_meta"))
        update = mapping(params.get("update"))
        at = _when(meta.get("agentTimestampMs"), record.get("timestamp"))
        if at is None or not window[0] <= at <= window[1]:
            continue
        prev = prev or at
        kind = str(update.get("sessionUpdate") or "")

        if kind == "user_message_chunk":
            turn, prev = _prompt(actions, update, at, prev, turn, info)
            think = None
        elif kind == "agent_thought_chunk":
            think = _thinking(actions, streams, meta, at, prev)
            body = text_of(update.get("content"))
            if body:
                think.args["thinking"] = truncate(
                    f"{think.args.get('thinking', '')}\n{body}".strip()
                )
                think.name = f"think: {summarize(body)}"
            prev = max(prev, at)
        elif kind == "agent_message_chunk":
            think = _thinking(actions, streams, meta, at, prev)
            body = text_of(update.get("content"))
            # `min` rather than `prev`: the agent's own clock is what these are timed by and
            # two records of one millisecond come back in whichever order they were written,
            # so a slice running from the cursor would now and then run backwards.
            actions.append(
                Action(
                    f"say: {summarize(body)}",
                    "message",
                    min(prev, at),
                    at,
                    {"text": truncate(body)},
                )
            )
            prev = at
        elif kind in ("tool_call", "tool_call_update"):
            # The model call ends where it reached for something: what follows is the tool
            # running, which is a slice of its own rather than more of the thinking.
            if think is not None and kind == "tool_call":
                think.end = max(think.end, at)
                think = None
            _called(actions, pending, update, at)
            prev = max(prev, at)
        elif kind == "turn_completed":
            # A turn nobody saw open is still a turn that was billed: a session resumed with
            # its prompt carried in has no chunk to open one, and a trace narrowed to a moment
            # after the prompt cuts one off. Opened here rather than let go, since dropping it
            # would drop the only statement of what that turn cost.
            if turn is None:
                turn = Action("turn", "turn", min(prev, at), at, {})
            turn.args.update(
                {
                    "stop_reason": update.get("stop_reason"),
                    "elapsed_ms": update.get("elapsed_ms"),
                    "usage": truncate(update.get("usage")),
                }
            )
            turn.end = max(turn.end, prev, at)
            actions.append(turn)
            turn, think = None, None
            if info.get("model") is None:
                info["model"] = _modelled(update)
            prev = max(prev, at)
        elif kind:
            actions.append(_event(update, kind, at))
            prev = max(prev, at)

    closing = max((action.end for action in actions), default=prev)
    for call in pending.values():
        if call.args.get("status") in _ENDED:
            continue
        call.end = max(call.start, closing)
        call.args["unfinished"] = True
    if turn is not None:
        turn.end = max(turn.end, closing)
        actions.append(turn)
    return actions, {key: value for key, value in info.items() if value is not None}


def _when(agent: Any, wrote: Any) -> float | None:
    """The moment one record stands for, by the agent's own clock where it gave one.

    Args:
        agent: `params._meta.agentTimestampMs`, in epoch milliseconds, which is when the
            thing being reported happened.
        wrote: The record's own `timestamp`, in epoch seconds, which is when the line was
            appended -- the same moment rounded down, and a second later where the writing
            queued behind something.

    Returns:
        It, in epoch seconds, or None for a record timed by neither.
    """
    if isinstance(agent, (int, float)) and not isinstance(agent, bool):
        return float(agent) / 1000.0
    if isinstance(wrote, (int, float)) and not isinstance(wrote, bool):
        return float(wrote)
    return None


def _prompt(
    actions: list[Action],
    update: dict[str, Any],
    at: float,
    prev: float,
    turn: Action | None,
    info: dict[str, Any],
) -> tuple[Action, float]:
    """Opens the turn one prompt starts, or grows the turn it is the rest of.

    Grok Build numbers the prompts of a session on the chunk itself, so a prompt that arrived
    in pieces is the pieces sharing a number rather than a guess about how close together two
    records are.

    Args:
        actions: Where a turn that has now ended is recorded.
        update: The `user_message_chunk` as read.
        at: When it was said.
        prev: The cursor, which the turn it closes runs up to.
        turn: The turn now open, if one is.
        info: What is known about the session, which the chunk names the model on.

    Returns:
        The turn now open, and the new cursor.
    """
    told = mapping(update.get("_meta"))
    # The only place a log states what answered it: the counts a turn ends on name the model
    # the vendor billed -- `grok-4.6-build` -- rather than the id a turn was asked for.
    if info.get("model") is None:
        info["model"] = told.get("modelId")
    body = text_of(update.get("content"))
    index = told.get("promptIndex")
    if (
        turn is not None
        and index is not None
        and turn.args.get("prompt_index") == index
    ):
        turn.args["prompt"] = truncate(f"{turn.args['prompt']}\n{body}".strip())
        turn.name = f"turn: {summarize(str(turn.args['prompt']))}"
        return turn, max(prev, at)
    if turn is not None:
        turn.end = max(turn.end, prev, at)
        actions.append(turn)
    return (
        Action(
            f"turn: {summarize(body)}",
            "turn",
            at,
            at,
            {"prompt_index": index, "prompt": truncate(body)},
        ),
        max(prev, at),
    )


def _thinking(
    actions: list[Action],
    streams: dict[tuple[Any, Any], Action],
    meta: dict[str, Any],
    at: float,
    prev: float,
) -> Action:
    """The model call one chunk came out of, opened where this is the first of them.

    A turn is several calls to the model with the tools it asked for run in between, and
    `_meta.streamStartMs` is what tells them apart: it is when the call that is speaking now
    opened, so every chunk of one answer carries the same one. It is also a real time rather
    than a name, so the slice starts where the model started rather than where it first
    managed to say something.

    Args:
        actions: Where a newly opened call is recorded.
        streams: The calls of this log already opened, by the turn and the call.
        meta: The record's `params._meta`.
        at: When the chunk was said.
        prev: The cursor, which an unnumbered call runs from.

    Returns:
        The call this chunk belongs to, ending no earlier than the chunk.
    """
    opened = meta.get("streamStartMs")
    began = _when(opened, None)
    # A chunk that names no call is its own call rather than one more of whatever was open:
    # every one of them sharing a key would be a single slice across the whole conversation.
    held = streams.get((meta.get("promptId"), opened)) if opened is not None else None
    if held is None:
        held = Action(
            "think", "llm", min(began if began is not None else prev, at), at, {}
        )
        if opened is not None:
            streams[meta.get("promptId"), opened] = held
        actions.append(held)
    held.end = max(held.end, at)
    return held


def _called(
    actions: list[Action],
    pending: dict[str, Action],
    update: dict[str, Any],
    at: float,
) -> None:
    """Opens the slice one tool call is, or closes the one an update is about.

    A call is announced once and updated at least twice: the first update carries what kind of
    tool it is and a title rewritten into a sentence about the call, and the last carries the
    status it ended on and what it returned. Both are folded onto the one slice, since a row
    per status is a transcript of statuses. An update for a call that was never announced
    opens the slice itself, a log cut off before the announcement being likelier than one that
    invented an id.

    Args:
        actions: Where a newly announced call is recorded.
        pending: The calls of this log, by their id, whatever became of them.
        update: The `tool_call` or `tool_call_update` as read.
        at: When it was said.
    """
    marked = str(update.get("toolCallId") or "")
    # A call the agent gave no id gets a slice of its own, as it does where the same stream is
    # read live: there is nothing to tell it from the next one, and folding every nameless call
    # onto one key would show the first and quietly overwrite it with each one after.
    call = pending.get(marked) if marked else None
    if call is None:
        tool = mapping(mapping(update.get("_meta")).get(_TOOL))
        name = str(tool.get("name") or update.get("title") or "tool")
        call = Action(
            label(name, update.get("rawInput")),
            "tool",
            at,
            at,
            {
                "tool": name,
                "namespace": tool.get("namespace"),
                "input": truncate(update.get("rawInput")),
            },
        )
        if marked:
            pending[marked] = call
        actions.append(call)
    if update.get("kind") is not None:
        call.args["kind"] = update["kind"]
    status = update.get("status")
    if status is not None:
        call.args["status"] = status
    if status not in _ENDED:
        return
    # `content` is the description of the call until the call has ended, and what it returned
    # once it has: only the ending update is read for an output.
    call.end = max(call.start, at)
    call.args["error"] = status == "failed"
    said = _said(update.get("content"))
    call.args["output"] = truncate(said)
    # An answer with no readable text is not an answer with nothing in it: an edit comes back
    # as a diff and a search as its matches, neither of which is a block of words. What the
    # tool actually returned is kept whole beside the empty text rather than lost with it.
    if not said and update.get("rawOutput") is not None:
        call.args["result"] = truncate(update["rawOutput"], 512)


def _said(content: Any) -> str:
    """The readable text of a tool's answer, out of the blocks the protocol wraps it in.

    The protocol wraps each block once more than the shared reader expects -- a block is
    `{"type": "content", "content": {"type": "text", "text": …}}` -- so the wrapper is taken
    off before the text is read out of what it held.

    Args:
        content: The `content` of a `tool_call_update`, as read.

    Returns:
        What it says, and "" for an answer carrying nothing readable.
    """
    if not isinstance(content, list):
        return text_of(content)
    blocks = cast("list[Any]", content)
    return text_of(
        [mapping(block).get("content", block) for block in blocks]
    ) or text_of(content)


def _modelled(update: dict[str, Any]) -> Any:
    """What the counts a turn ended on say answered it, for a log with no prompt of its own.

    A session resumed by a turn that only spoke -- a sub-agent, a `--resume` that carried its
    prompt in -- has no `user_message_chunk` to name a model on, and `usage.modelUsage` is
    keyed by the model the vendor billed.

    Args:
        update: The `turn_completed` as read.

    Returns:
        That model, or None where the counts named none.
    """
    return next(iter(mapping(mapping(update.get("usage")).get("modelUsage"))), None)


def _event(update: dict[str, Any], kind: str, at: float) -> Action:
    """One of Grok Build's own sayings about the session, as the slice it becomes.

    Everything on `_x.ai/session/update` other than the turn's own ending lands here: a goal's
    progress, a request being retried, a command sent to the background, a sub-agent starting
    or finishing. They are read by name rather than one by one, so a saying nobody has listed
    yet is a slice with its own words on it rather than a hole in the trace.

    Args:
        update: The update as read.
        kind: What it called itself.
        at: When it was said.

    Returns:
        The slice, carrying the session it spawned where it spawned one.
    """
    told = (
        update.get("description") or update.get("subagent_type") or update.get("type")
    )
    child = update.get("child_session_id")
    return Action(
        f"{kind}: {summarize(str(told))}" if told else kind,
        "event",
        at,
        at,
        truncate(update, 512),
        f"grok:{child}" if kind == "subagent_spawned" and child else None,
    )
