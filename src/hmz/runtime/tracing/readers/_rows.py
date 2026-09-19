"""The session store opencode and mimocode share, read as sessions.

Two of the CLIs humanize drives keep everything they record in one SQLite database
rather than a file per session, and they keep it in the same three tables, because
one is a fork of the other: `session` is the conversation, `message` is a turn of
it, and `part` is what a turn was made of, each holding its own JSON in a text
column. `part` is identical between them; `message` differs by a column neither
reader reads; and `session` differs by a handful the fork dropped, which is why
every column past the two that identify a conversation is read only where it is
there.

Read-only and as a snapshot. The database belongs to whatever process is running,
which may be writing to it while this reads; opened `mode=ro` so nothing here can
touch it, and queried rather than tailed, since a row that is rewritten in place is
not something a byte offset could have followed anyway.

A turn's parts say what it was: `reasoning` is what the model thought, `text` is
what it said, and `tool` carries the call, its input, its output and the moments it
ran between, all in the one row -- so a tool slice here is closed by the part that
opened it rather than by a later record answering it. `step-start` and `step-finish`
bracket a model call inside a turn; on the 25080 messages of this corpus none ever
held more than one of them, so what a message was billed is what the message's own
`tokens` says, read once per message rather than once per step.

`input + output + cache.read + cache.write` is `total` across 24826 of those, so a
cached read sits beside what was read rather than inside it -- Pi's arrangement
rather than Grok Build's, and the difference between a bill and one several times
it. The cache is nested under a key of its own, which is what whoever prices these
has to reach into rather than read off the top.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from typing import Any, cast

from hmz.runtime.tracing.session import (
    Action,
    Session,
    label,
    mapping,
    summarize,
    title_of,
    truncate,
    wanted,
)

#: What opencode times everything in: milliseconds since the epoch.
_MILLIS = 1000.0

#: The parts that bracket a model call rather than holding any of it. Kept out of
#: the slices, since a turn is already one slice and these would be two more
#: saying nothing a reader could show.
_BRACKETS = frozenset({"step-start", "step-finish"})


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
    *,
    backend: str,
    database: str,
) -> list[Session]:
    """Collects the sessions asked for out of one of these databases.

    Args:
        home: The share directory holding the database.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Session ids to keep, or None to keep every session. A kept
            session pulls in the sub-sessions it started.
        window: Inclusive epoch second bounds used to cut off records.
        backend: Which of them this is, as a session names its backend.
        database: What the database is called under ``home``.

    Returns:
        One session per conversation, with sub-sessions linked to their parent.
    """
    path = home / database
    if not path.is_file():
        return []
    try:
        # `mode=ro` rather than a copy: the database is opencode's own and may be
        # being written to, and nothing here may be what alters it.
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        # A database half-written, or one this build of SQLite will not open, is
        # a backend with nothing to say rather than a trace that stops.
        return []
    connection.row_factory = sqlite3.Row
    try:
        rows = _rows(connection)
        collected = [
            _session(connection, row, window, backend=backend, database=database)
            for row in rows
            if _kept(row, workspace, sessions, backend=backend)
        ]
    except sqlite3.Error:
        return []
    finally:
        connection.close()
    held = {session.key for session in collected}
    for session in collected:
        if session.parent not in held:
            session.parent = None
    return collected


def _rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every session the database holds, oldest first.

    Every column rather than the ones wanted by name: the fork dropped a handful
    of them, and a query naming one of those is a backend that reads back as
    having no sessions at all rather than one missing a field.
    """
    return list(connection.execute("select * from session order by time_created"))


def _kept(
    row: sqlite3.Row,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    *,
    backend: str,
) -> bool:
    """Whether this session is one of the workspace's, and one that was asked for."""
    if not wanted(sessions, f"{backend}:{row['id']}"):
        return False
    directory = row["directory"]
    if workspace is None:
        return True
    return isinstance(directory, str) and pathlib.Path(directory) == workspace


def _session(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    window: tuple[float, float],
    *,
    backend: str,
    database: str,
) -> Session:
    """One conversation, as the rows that make it up."""
    ident = str(row["id"])
    actions = _actions(connection, ident, window)
    held = row.keys()
    info: dict[str, Any] = {"database": database, "cwd": _held(row, "directory")}
    for name in ("version", "agent"):
        if name in held and row[name] is not None:
            info[name] = row[name]
    model = mapping(_json(_held(row, "model")))
    if model.get("modelID"):
        info["model"] = model["modelID"]
        info["provider"] = model.get("providerID")
    else:
        # The fork keeps no model on the conversation, so what it ran at is what
        # its answers say they ran at -- taken from the first of them, which is
        # what the session opened at.
        info.update(_opened(actions))
    parent = _held(row, "parent_id")
    title = str(_held(row, "title") or "") or None
    return Session(
        key=f"{backend}:{ident}",
        backend=backend,
        ident=ident,
        label="main" if not parent else "subagent",
        title=f"{ident[:12]} · {summarize(title, 60)}"
        if title
        else title_of(ident[:12], actions),
        parent=f"{backend}:{parent}" if parent else None,
        args=info,
        actions=actions,
    )


def _held(row: sqlite3.Row, name: str) -> Any:
    """One column of a session row, or nothing where this one has no such column.

    Asked of the names rather than of the row: `in` on a `sqlite3.Row` tests its
    values, so a column named after one of them would answer for the wrong thing.
    """
    columns = row.keys()
    return row[name] if name in columns else None


def _opened(actions: list[Action]) -> dict[str, Any]:
    """What the first answer of a conversation says it was answered by."""
    for action in actions:
        if action.category != "llm":
            continue
        model = action.args.get("model")
        if isinstance(model, str) and model:
            return {"model": model, "provider": action.args.get("provider")}
    return {}


def _actions(
    connection: sqlite3.Connection, ident: str, window: tuple[float, float]
) -> list[Action]:
    """Every slice of one conversation, in the order its rows were written."""
    parts: dict[str, list[sqlite3.Row]] = {}
    for part in connection.execute(
        "select message_id, time_created, data from part "
        "where session_id = ? order by time_created",
        (ident,),
    ):
        parts.setdefault(str(part["message_id"]), []).append(part)

    actions: list[Action] = []
    for message in connection.execute(
        "select id, time_created, time_updated, data from message "
        "where session_id = ? order by time_created",
        (ident,),
    ):
        at = _when(message["time_created"])
        if at is None or not window[0] <= at <= window[1]:
            continue
        held = mapping(_json(message["data"]))
        ended = _when(message["time_updated"]) or at
        if held.get("role") == "user":
            prompt = _said(parts.get(str(message["id"]), []))
            actions.append(
                Action(
                    f"turn: {summarize(prompt)}",
                    "turn",
                    at,
                    ended,
                    {"prompt": truncate(prompt)},
                )
            )
            continue
        actions.extend(_answered(held, parts.get(str(message["id"]), []), at, ended))
    return actions


def _answered(
    message: dict[str, Any], parts: list[sqlite3.Row], at: float, ended: float
) -> list[Action]:
    """One assistant turn: the call it was billed for, and what it emitted."""
    think = Action(
        "think",
        "llm",
        at,
        ended,
        {
            "model": message.get("modelID"),
            "provider": message.get("providerID"),
            # What the message itself says it cost, which is what opencode bills
            # a turn by -- read once here rather than once per `step-finish`, so
            # that a turn is counted once however many steps it took.
            "usage": message.get("tokens"),
        },
    )
    actions: list[Action] = [think]
    for part in parts:
        held = mapping(_json(part["data"]))
        kind = held.get("type")
        if kind in _BRACKETS:
            continue
        started = _when(part["time_created"]) or at
        if kind == "reasoning":
            body = str(held.get("text") or "")
            if body:
                think.args["thinking"] = truncate(
                    f"{think.args.get('thinking', '')}\n{body}".strip()
                )
                think.name = f"think: {summarize(body)}"
            continue
        if kind == "text":
            body = str(held.get("text") or "")
            actions.append(
                Action(
                    f"say: {summarize(body)}",
                    "message",
                    *_between(held, started, ended),
                    {"text": truncate(body)},
                )
            )
            continue
        if kind == "tool":
            actions.append(_called(held, started, ended))
    return actions


def _called(held: dict[str, Any], started: float, ended: float) -> Action:
    """One tool call, which opencode records whole rather than in two rows."""
    state = mapping(held.get("state"))
    named = str(held.get("tool") or "tool")
    begun, done = _between(state, started, ended)
    args: dict[str, Any] = {
        "tool": named,
        "input": truncate(state.get("input")),
        "status": state.get("status"),
    }
    if state.get("output") is not None:
        args["output"] = truncate(str(state.get("output")))
    if state.get("error"):
        args["error"] = truncate(state.get("error"))
    # Written in one row, so a call with no ending is one that had not finished
    # when opencode last wrote it rather than one nothing answered.
    if state.get("status") not in ("completed", "error"):
        args["unfinished"] = True
    return Action(label(named, state.get("input")), "tool", begun, done, args)


def _between(held: dict[str, Any], started: float, ended: float) -> tuple[float, float]:
    """When a part ran, as it states it, or the message's own bounds where it does not."""
    times = mapping(held.get("time"))
    begun = _when(times.get("start")) or started
    done = _when(times.get("end")) or max(begun, ended)
    return begun, max(begun, done)


def _said(parts: list[sqlite3.Row]) -> str:
    """What a user turn asked, which its text parts hold between them."""
    texts: list[str] = []
    for part in parts:
        held = mapping(_json(part["data"]))
        if held.get("type") == "text" and isinstance(held.get("text"), str):
            texts.append(str(held["text"]))
    return "\n".join(texts)


def _when(value: object) -> float | None:
    """One of opencode's millisecond stamps as epoch seconds, or None for no stamp."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value) / _MILLIS
    except (TypeError, ValueError):
        return None


def _json(value: object) -> object:
    """One of the JSON columns, read as what it holds or as nothing at all."""
    if not isinstance(value, (str, bytes)):
        return None
    try:
        return cast("object", json.loads(value))
    except ValueError:
        return None
