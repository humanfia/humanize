"""Collector for ZCode model-io rollouts.

ZCode writes down the model rather than the turn. Every other log read here is a stream of
what an agent did -- a prompt, a step, a tool call, a result -- while this one is a line per
request the CLI made to a provider: what was sent, what came back, how long it took and what
it cost. So a turn is read back off the requests it took. What somebody asked for is the
message a request carries that the request before it did not; what the agent thought and said
is that request's answer; what it reached for is that answer's tool calls, and how each of
those turned out is a message of the request after it.

Which makes the counts the straightforward half. Every line carries the usage its provider
stated, under the names the driver already reads off the wire -- `inputTokens` and
`outputTokens`, whose sum is the `totalTokens` beside them -- and the log names two more the
wire does not: `reasoningTokens` and `cacheReadTokens`, each counted *inside* one of the first
two rather than beside it. All five are kept as ZCode wrote them, since a reader that added
them up would be adding some tokens twice.

Three things the CLI does to its own rollouts are read here rather than guessed at, off
`resources/glm/zcode.cjs` of ZCode 0.16.5:

- A request replays the conversation, and the replay is not always whole. `messagesKind` says
  which it is -- `full`, `delta` for the messages since the line before, `tail` for the last
  sixty-four of a long one -- and `messageOffset` says where what is there begins. So a
  message is placed by where the log says it is rather than by where it sits in the list.
- Every query of a session shares that session's file, and `querySource` says which is which:
  the agent's own steps, and ZCode's own errands beside them -- naming the session, compacting
  it, fetching a page. Both cost tokens and only the first is the conversation.
- The directory a session ran in is in the prompt and nowhere else, and it is the one thing a
  workspace narrows a trace by. ZCode words it one way for an agent and another for a
  sub-agent, so both wordings are looked for.

A sub-agent is a session of its own in a file of its own, called `sess_subagent_<agent id>`
and carrying the trace id of the session that started it -- which is what hangs it off its
parent. The `Agent` call that started it names that agent id in what it answered with, which
is what points the one at the other.

At most three of these files survive: opening a session when three are already there deletes
the oldest. So a trace of a run that drove ZCode four times over holds the last three of them,
and there is nothing here that can be done about that.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
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

#: The query sources whose messages are the conversation and whose answers are the agent
#: speaking. Everything else on ZCode 0.16.5 -- `session_title`, `compact`, `web_search_tool`,
#: `project_memory_recall` and the rest -- is the CLI asking a model something on the session's
#: behalf, which is spent tokens and is not the turn.
_STEPS = ("main_turn", "subagent", "workflow_child")

#: What names the id of a session started by the `Agent` tool, its own file among them.
_UNDER = "sess_subagent_"

#: Where ZCode tells a session which directory it is working in, in both of the wordings it
#: has: `- Primary working directory: <path>` in an agent's own prompt, and `Working
#: directory: <path>` inside the `<env>` block a sub-agent gets instead.
_CWD = re.compile(
    r"^-?\s*(?:Primary working|Working) directory:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE
)

#: How the `Agent` tool names the sub-agent it ran, at the end of what it answers with. Read
#: while the answer is whole, because it is the last line of one that may be thousands of
#: characters long and what is kept on the slice is clipped.
_AGENT = re.compile(r"agentId:\s*(agent_[\w-]+)")

#: What ZCode wraps the context it adds to a conversation in -- the skills a session may load,
#: today's date. It arrives as a user message like a prompt does, and a turn named after the
#: skill list rather than after what was asked would be a turn nobody could find. Cut out of a
#: message rather than used to throw the message away, since where it sits inside one is
#: ZCode's to change: on 0.16.5 each is a message of its own.
_ASIDE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the ZCode sessions and sub-agent sessions asked for.

    Args:
        home: ZCode home directory holding the command line's rollout folder.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Session ids to keep, or None to keep every session. A kept
            session pulls in the sub-agents it started.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per rollout, with sub-agents linked to their parent.
    """
    # Read before anything is narrowed, unlike the readers whose logs say in their first line
    # which workspace they are of. ZCode's says it in the prompt of whichever request first
    # carried one -- a session named before its first turn puts that request second -- so
    # what a rollout is of is only known once it has been read. Which costs nothing: three
    # of these files exist at most.
    read: dict[str, tuple[pathlib.Path, list[Action], dict[str, Any]]] = {}
    for path in sorted((home / "cli" / "rollout").glob("model-io-*.jsonl")):
        actions, info = _parse(path, window)
        ident = str(info.pop("session", "") or path.stem.removeprefix("model-io-"))
        read[ident] = (path, actions, info)

    kept = {
        ident
        for ident, (_, _, info) in read.items()
        if wanted(sessions, f"zcode:{ident}", _short(ident))
        and (workspace is None or pathlib.Path(str(info.get("cwd"))) == workspace)
    }
    # A sub-agent is neither asked for by name nor recorded against a workspace of its own,
    # so it is kept for the trace id it shares with whoever started it.
    traces = {
        read[ident][2].get("trace") for ident in kept if not ident.startswith(_UNDER)
    } - {None}
    kept |= {
        ident
        for ident, (_, _, info) in read.items()
        if ident.startswith(_UNDER) and info.get("trace") in traces
    }

    collected: list[Session] = []
    for ident in sorted(kept):
        path, actions, info = read[ident]
        short = _short(ident)
        named = info.pop("title", "")
        collected.append(
            Session(
                key=f"zcode:{ident}",
                backend="zcode",
                ident=ident,
                label="subagent" if ident.startswith(_UNDER) else "main",
                title=f"{short} · {named}" if named else title_of(short, actions),
                args={"log": str(path), **info},
                actions=actions,
            )
        )
    _hang(collected)
    return collected


def _short(ident: str) -> str:
    """The head of a session id, which is what its slice is named after.

    Args:
        ident: The id ZCode gave the session.

    Returns:
        The first eight characters of what is left once the prefixes ZCode
        builds an id out of are off it, so that a sub-agent is named after
        itself rather than after the word `subagent` it shares with every
        other one.
    """
    return (
        ident.removeprefix("sess_").removeprefix("subagent_").removeprefix("agent_")[:8]
    )


def _hang(collected: list[Session]) -> None:
    """Hangs each sub-agent off the session that started it, and names it after the call.

    Args:
        collected: Every session read, which is where both halves of each link
            are. Changed in place.
    """
    # Keyed on a trace id there is, rather than on whatever `get` answers: a rollout too
    # narrowly windowed to have said which trace it was would otherwise be everyone's parent.
    parents = {
        item.args["trace"]: item
        for item in collected
        if not item.ident.startswith(_UNDER) and item.args.get("trace")
    }
    for item in collected:
        if not item.ident.startswith(_UNDER):
            continue
        owner = parents.get(str(item.args.get("trace") or ""))
        if owner is None:
            continue
        item.parent = owner.key
        agent = item.ident.removeprefix(_UNDER)
        for action in owner.actions:
            if action.args.get("agent") != agent:
                continue
            action.spawn = item.key
            given = mapping(action.args.get("input"))
            kind = str(given.get("subagent_type") or "subagent")
            about = given.get("description")
            item.label = f"{kind} · {about}" if about else kind


def _at(said: Any) -> float | None:
    """One of ZCode's timestamps as epoch seconds, or None for anything that is not one."""
    if not isinstance(said, str):
        return None
    try:
        return datetime.datetime.fromisoformat(said).timestamp()
    except ValueError:
        return None


def _parse(
    path: pathlib.Path, window: tuple[float, float]
) -> tuple[list[Action], dict[str, Any]]:
    """Turns one rollout into turn, reasoning, tool and message slices."""
    actions: list[Action] = []
    info: dict[str, Any] = {}
    pending: dict[str, Action] = {}
    # How much of each conversation has been replayed already, by the query source it
    # belongs to: a session's own steps and the errands run beside them are two different
    # conversations written to one file, and they are counted apart.
    seen: dict[str, int] = {}
    turn: Action | None = None
    for record in records(path):
        source = str(record.get("querySource") or "")
        _about(record, source, info)
        started = _at(record.get("startedAt"))
        if started is None or not window[0] <= started <= window[1]:
            continue
        ended = max(started, _at(record.get("completedAt")) or started)
        if source not in _STEPS:
            actions.append(_errand(record, source, started, ended, info))
            continue

        if turn is None or turn.args.get("turn") != record.get("turnId"):
            if turn is not None:
                turn.end = max(turn.end, started)
                actions.append(turn)
            turn = Action(
                "turn", "turn", started, started, {"turn": record.get("turnId")}
            )

        request = mapping(record.get("request"))
        messages = cast("list[Any]", request.get("messages") or [])
        offset = int(request.get("messageOffset") or 0)
        already = seen.get(source, 0)
        if request.get("messagesKind") == "full" and offset + len(messages) < already:
            # A whole replay shorter than what has already been read is not the same
            # conversation shortened, it is another one: compacting a session replaces it
            # with a summary of itself, and everything after that is new however far in it
            # sits. Only `full` is read this way -- `delta` and `tail` are both offsets into
            # a conversation that is still going.
            already = 0
        for index, raw in enumerate(messages, start=offset):
            if index >= already:
                _replay(mapping(raw), turn, started, pending)
        if messages:
            seen[source] = offset + len(messages)
        _answered(actions, record, source, started, ended, pending)

    closing = max((action.end for action in actions), default=0.0)
    for call in pending.values():
        call.end = max(call.start, closing)
        call.args["unfinished"] = True
    if turn is not None:
        turn.end = max(turn.end, closing)
        actions.append(turn)
    return actions, info


def _about(record: dict[str, Any], source: str, info: dict[str, Any]) -> None:
    """Reads what one line says about the session rather than about the turn.

    Read whatever window the trace was narrowed to, unlike everything else here. Whose
    session a rollout is, which trace it belongs to, what it ran on and which directory it
    ran in are true of the whole of it and are said only where ZCode happened to say them --
    the workspace in the prompt of the first request that carried one, which a session named
    before its first turn puts second. A session dropped from a workspace's trace because the
    line that said which workspace fell outside the window is a session gone rather than a
    session narrowed.

    Args:
        record: The line, as ZCode wrote it.
        source: Which query of the session it was.
        info: What is known about the session so far, added to.
    """
    for field, key in (("sessionId", "session"), ("traceId", "trace")):
        if isinstance(record.get(field), str):
            info.setdefault(key, record[field])
    if source not in _STEPS:
        return  # an errand runs on the lite model, which is not what the session runs on
    held = mapping(record.get("model"))
    for field, key in (
        ("modelId", "model"),
        ("variant", "effort"),
        ("providerId", "provider"),
    ):
        if held.get(field) is not None:
            info.setdefault(key, held[field])
    if "cwd" in info:
        return
    for raw in cast("list[Any]", mapping(record.get("request")).get("messages") or []):
        message = mapping(raw)
        if message.get("role") != "system":
            continue
        found = _CWD.search(text_of(message.get("content")))
        if found is not None:
            info["cwd"] = found.group(1)
            return


def _replay(
    message: dict[str, Any],
    turn: Action,
    at: float,
    pending: dict[str, Action],
) -> None:
    """Records one message a request carried that no earlier request did.

    Args:
        message: The message, as ZCode replayed it.
        turn: The turn under way, which a prompt names.
        at: When the request carrying it was sent, which is the moment
            everything in it was already true by.
        pending: Tool calls waiting on a result, by the id they were made
            under.
    """
    role = message.get("role")
    if role == "tool":
        call = pending.pop(str(message.get("toolCallId")), None)
        if call is None:
            return
        body = text_of(message.get("content"))
        call.end = max(call.start, at)
        call.args["output"] = truncate(body)
        call.args["error"] = bool(message.get("isError"))
        started = _AGENT.search(body)
        if started is not None:
            call.args["agent"] = started.group(1)
        return
    # An assistant message is what the request before it already answered with, read there
    # instead: that record says when it was said and what it cost, and this one says neither.
    if role != "user":
        return
    body = _ASIDE.sub("", text_of(message.get("content"))).strip()
    if not body:
        return
    prompt = str(turn.args.get("prompt") or "")
    turn.args["prompt"] = truncate(f"{prompt}\n{body}".strip())
    turn.name = f"turn: {summarize(str(turn.args['prompt']))}"


def _answered(
    actions: list[Action],
    record: dict[str, Any],
    source: str,
    started: float,
    ended: float,
    pending: dict[str, Action],
) -> None:
    """Records what one request of a turn cost and what came back from it.

    Args:
        actions: The slices read so far, appended to.
        record: The request, as ZCode wrote it down.
        source: Which query of the session it was.
        started: When it was sent, in epoch seconds.
        ended: When it came back.
        pending: Tool calls waiting on a result, added to.
    """
    response = mapping(record.get("response"))
    think = Action(
        "think",
        "llm",
        started,
        ended,
        {
            "query": source,
            "model": mapping(record.get("model")).get("modelId"),
            "usage": response.get("usage"),
            "finish": response.get("finishReason"),
        },
    )
    if record.get("attempt") not in (None, 1):
        think.args["attempt"] = record["attempt"]
    reasoning = str(response.get("reasoningText") or "")
    if reasoning:
        think.name = f"think: {summarize(reasoning)}"
        think.args["reasoning"] = truncate(reasoning)
    if record.get("error") is not None:
        # A request that came back as nothing still took the time it took and still says why,
        # so it is a slice like any other rather than a line quietly skipped -- and it is
        # named after the failure rather than after whatever thinking arrived before it, a
        # retry being the one thing on the timeline somebody is looking for.
        said = record["error"]
        think.args["error"] = truncate(said, 512)
        think.name = f"failed: {summarize(_failed(said))}"
    actions.append(think)

    body = str(response.get("text") or "")
    if body:
        actions.append(
            Action(
                f"say: {summarize(body)}",
                "message",
                ended,
                ended,
                {"text": truncate(body)},
            )
        )
    for raw in cast("list[Any]", response.get("toolCalls") or []):
        called = mapping(raw)
        name = str(called.get("name") or "tool")
        call = Action(
            label(name, called.get("input")),
            "tool",
            ended,
            ended,
            {"tool": name, "input": truncate(called.get("input"))},
        )
        pending[str(called.get("id"))] = call
        actions.append(call)


def _errand(
    record: dict[str, Any],
    source: str,
    started: float,
    ended: float,
    info: dict[str, Any],
) -> Action:
    """Records one query ZCode ran on the session's behalf rather than the agent's.

    Args:
        record: The request, as ZCode wrote it down.
        source: Which errand it was, in ZCode's own word for it.
        started: When it was sent, in epoch seconds.
        ended: When it came back.
        info: What is known about the session, which naming it adds a title to.

    Returns:
        The slice it becomes, which is an `llm` one because it is tokens the
        session spent however little of the conversation it was.
    """
    response = mapping(record.get("response"))
    body = str(response.get("text") or "")
    if source == "session_title" and body:
        info.setdefault("title", _titled(body))
    return Action(
        f"{source}: {summarize(body)}" if body else source or "query",
        "llm",
        started,
        ended,
        {
            "query": source,
            "model": mapping(record.get("model")).get("modelId"),
            "usage": response.get("usage"),
            "text": truncate(body),
        },
    )


def _failed(said: Any) -> str:
    """Why a request came back as nothing, out of either shape ZCode writes that down as.

    Args:
        said: The error, which is an object of a name, a message and a stack for anything
            thrown as one, and the thing itself said as a string for anything else.

    Returns:
        The line worth putting on the slice.
    """
    return str(mapping(said).get("message") or said)


def _titled(said: str) -> str:
    """The name ZCode gave a session, out of the object it asks a model to answer with."""
    try:
        held: Any = json.loads(said)
    except json.JSONDecodeError:
        return said
    return str(mapping(held).get("title") or said)
