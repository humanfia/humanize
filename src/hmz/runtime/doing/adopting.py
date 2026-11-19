"""The sessions a harness had of its own in a workspace: listed, read, and adopted as a chat.

A harness run by hand keeps its sessions in its own home, where Humanize wrote none of them
down. Each is found here by where its CLI lays it out (:mod:`hmz.coganchor.backends`) and
read only at its head and its tail, so that listing a workspace's costs a bounded read per
session and never a transcript; one is read whole only to be shown, by the readers a trace is
gathered with (:mod:`hmz.runtime.tracing`). Adopting one copies its files into a chat of
Humanize's own (Section 8.11 of core.md): nothing here writes under a harness's home.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import urllib.parse
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from hmz import home
from hmz.coganchor import backends
from hmz.runtime.tracing.session import mapping

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterator
    from pathlib import Path

__all__ = ["HARNESSES", "Found", "adopt", "files", "listed", "said"]

#: How much of a session's log is read at its head, and at its tail, to list it.
_READ = 128 * 1024

#: How long a title is, at most.
_TITLE = 240

#: How many sessions are remembered as they were last read.
_KEPT = 20_000

_CWD = re.compile(r'"cwd"\s*:\s*("(?:[^"\\]|\\.)*")')
_AT = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')
_MODEL = re.compile(r'"model(?:Id)?"\s*:\s*"([^"<][^"]*)"')
#: A thread another one started or was cut from, as Codex says it on its first line.
_CHILD = re.compile(r'"(?:parent_thread_id|forked_from_id)"\s*:\s*"')
_ROLLOUT = re.compile(r"rollout-\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-(.+)")


class Found(NamedTuple):
    """One session a harness had of its own.

    Attributes:
      harness: The CLI that had it.
      ident: What that CLI calls it.
      title: The first line it was told, or "" where its head says none.
      began: When it began, as its log first says, else when its log was last written.
      updated: When its log was last written.
      cwd: Where it worked.
      model: The model it last ran on, or "" where its log says none.
      log: Its log.
    """

    harness: str
    ident: str
    title: str
    began: str
    updated: str
    cwd: str
    model: str
    log: Path


def _plain(at: str) -> str:
    """A directory as Claude Code and Qwen Code name the one they keep its sessions in."""
    return re.sub(r"[^a-zA-Z0-9]", "-", at)


def _stemmed(path: Path) -> str:
    return path.stem


def _dated(path: Path) -> str:
    """The id of a log named `<started>_<id>`, as pi and omp name one."""
    return path.stem.partition("_")[2] or path.stem


def _rolled(path: Path) -> str:
    """The id of a Codex rollout, named for the moment it opened and then the id."""
    named = _ROLLOUT.fullmatch(path.stem)
    return named[1] if named else ""


def _within(path: Path) -> str:
    return path.parent.name


#: Each harness whose own sessions are listed: the globs its logs are found by under its
#: home, taking `{plain}` and `{quoted}` -- the workspace as that harness names a directory
#: after it -- and what reads a session's id off its log's path. Exactly the harnesses that
#: keep a session as files of its own, name them by its id, and can carry one on from a copy.
_LAID: dict[str, tuple[tuple[str, ...], Callable[[Path], str]]] = {
    "claude": (("projects/{plain}/*.jsonl",), _stemmed),
    "codex": (
        ("sessions/**/rollout-*.jsonl", "archived_sessions/**/rollout-*.jsonl"),
        _rolled,
    ),
    "grok": (("sessions/{quoted}/*/updates.jsonl",), _within),
    "pi": (("sessions/*/*.jsonl",), _dated),
    "omp": (("sessions/*/*.jsonl",), _dated),
    "qwen": (("projects/{plain}/chats/*.jsonl",), _stemmed),
}

#: The harnesses whose own sessions are listed, and so can be read and adopted.
HARNESSES = tuple(_LAID)

#: Each log as it was last read, by its path: its size and when it was written, and what
#: was read of it. A log that has not changed is not opened again.
_seen: dict[Path, tuple[tuple[int, int], Found | None]] = {}


def listed(workspace: Path, owned: Collection[tuple[str, str]] = ()) -> list[Found]:
    """The sessions each harness installed here had of its own in one workspace.

    Args:
      workspace: The workspace, by its path.
      owned: Every session a chat or an epic opened, as `(harness, id)`: those are left out.

    Returns:
      Each, last written first. A harness that is not installed, one whose home is under
      Humanize's own, and one whose home cannot be read list nothing.
    """
    # As it was named and as it resolves: a harness writes down whichever it was run under.
    spelled = {os.path.abspath(workspace), str(workspace.resolve())}  # noqa: PTH100
    found: list[Found] = []
    for harness in HARNESSES:
        try:
            found += [
                one
                for one in _of(harness, spelled)
                if (harness, one.ident) not in owned
            ]
        except (OSError, ValueError):
            continue  # one harness that cannot be read is not every harness unread
    if len(_seen) > _KEPT:
        _seen.clear()
    return sorted(found, key=lambda one: one.updated, reverse=True)


def _of(harness: str, spelled: Collection[str]) -> Iterator[Found]:
    """One harness's sessions that worked in a workspace, by either spelling of its path."""
    profile = backends.named(harness)
    if profile is None or backends.program(profile.name) is None:
        return
    under = profile.directory()
    if under.is_relative_to(home()):
        return
    globs, ident = _LAID[harness]
    logs = {
        path
        for glob in globs
        for at in spelled
        for path in under.glob(
            glob.format(plain=_plain(at), quoted=urllib.parse.quote(at, safe=""))
        )
    }
    for path in logs:
        one = _read(harness, ident(path), path)
        if one is not None and one.cwd in spelled:
            yield one


def _read(harness: str, ident: str, path: Path) -> Found | None:
    """One session, read off the head and the tail of its log, or None for what is none."""
    try:
        stat = path.stat()
    except OSError:
        return None
    stamp = (stat.st_mtime_ns, stat.st_size)
    kept = _seen.get(path)
    if kept is not None and kept[0] == stamp:
        return kept[1]
    one: Found | None = None
    try:
        with path.open("rb") as log:
            head = log.read(_READ).decode("utf-8", errors="replace")
            log.seek(max(stat.st_size - _READ, 0))
            tail = log.read(_READ).decode("utf-8", errors="replace")
    except OSError:
        head = tail = ""
    cwd = _CWD.search(head)
    # Grok Build says where a session worked by the directory its log is in, and nowhere else.
    worked = (
        urllib.parse.unquote(path.parent.parent.name)
        if harness == "grok"
        else str(json.loads(cwd[1]))
        if cwd
        else ""
    )
    if ident and worked and not _CHILD.search(head.partition("\n")[0]):
        written = datetime.datetime.fromtimestamp(
            stat.st_mtime, datetime.UTC
        ).isoformat()
        began = _AT.search(head)
        models = _MODEL.findall(tail) or _MODEL.findall(head)
        one = Found(
            harness=harness,
            ident=ident,
            title=_title(head),
            began=began[1] if began else written,
            updated=written,
            cwd=worked,
            model=models[-1] if models else "",
            log=path,
        )
    _seen[path] = (stamp, one)
    return one


def _title(head: str) -> str:
    """The first line a session was told, off the head of its log, or ""."""
    for line in head.splitlines():
        try:
            record: object = json.loads(line)
        except ValueError:
            continue
        told = _told(mapping(record))
        first = next((one.strip() for one in told.splitlines() if one.strip()), "")
        # What a harness tells its own model ahead of the person -- the environment, a
        # command's output -- is written as a tag, and is nothing the person said.
        if first and not first.startswith("<"):
            return first[:_TITLE]
    return ""


def _told(record: dict[str, Any]) -> str:
    """What one record of a log says the person said, or "" for any other record."""
    if record.get("isMeta") or record.get("isSidechain"):
        return ""
    message = mapping(record.get("message"))
    payload = mapping(record.get("payload"))
    update = mapping(mapping(record.get("params")).get("update"))
    content: object = None
    if record.get("type") == "user" or message.get("role") == "user":
        # Claude Code and pi under `content`, Qwen Code under `parts`.
        content = message.get("content", message.get("parts"))
    elif payload.get("type") == "user_message":
        content = payload.get("message")
    elif mapping(payload.get("item")).get("type") == "UserMessage":
        content = mapping(payload.get("item")).get("content")
    elif update.get("sessionUpdate") == "user_message_chunk":
        content = update.get("content")
    if isinstance(content, str):
        return content
    blocks = cast("list[Any]", content if isinstance(content, list) else [content])
    return "\n".join(
        text for block in blocks if isinstance(text := mapping(block).get("text"), str)
    )


def said(one: Found) -> list[dict[str, Any]]:
    """What one session said and did, read whole out of the logs its harness kept.

    Returns:
      As :meth:`hmz.runtime.Epics.transcripts` says the sessions of a run: the session and
      every sub-agent it started.
    """
    from hmz.runtime.doing.epics import transcribed
    from hmz.runtime.tracing.collector import collect

    return [
        each
        for each in transcribed(collect(None, sessions=[one.ident]))
        if str(each["key"]).startswith(f"{one.harness}:")
    ]


def files(one: Found) -> dict[str, Path]:
    """Every file of one session, by where it is under its harness's home.

    Those under what its CLI keeps a session in whose path names the session, which is what
    carrying a copy on reads back (:meth:`hmz.coganchor.agents.AgentBase.recall`).
    """
    profile = backends.named(one.harness)
    if profile is None:
        return {}
    under = profile.directory()
    held: dict[str, Path] = {}
    for kept in profile.sessions:
        for at in under.glob(kept):
            for path in (at, *at.rglob("*")) if at.is_dir() else (at,):
                where = path.relative_to(under).as_posix()
                if one.ident in where and path.is_file():
                    held[where] = path
    return held


def adopt(one: Found, workspace: Path, agent: str = "") -> Path:
    """Makes a chat of one workspace that goes on from a copy of one session.

    Args:
      one: The session.
      workspace: The workspace it worked in.
      agent: The chat's assistant as `-a` spells one, of the session's harness, or "" for
        that harness at the model the session last ran on.

    Returns:
      The new chat's directory.

    Raises:
      ValueError: Saying why, for a harness that cannot carry a copy of a session on, an
        agent of another harness, a session that says no model where no agent is given, and
        a session whose files cannot be copied.
    """
    from hmz.runtime.epic import adopted
    from hmz.runtime.runner import drove

    profile = backends.named(one.harness)
    if profile is None or not profile.forks or one.harness not in HARNESSES:
        raise ValueError(
            f"{one.harness} cannot carry a session of its own on in a chat"
        )
    if not agent and not one.model:
        raise ValueError(
            f"{one.ident} does not say the model it ran on: name an agent for the chat"
        )
    assistant = drove("assistant", agent or f"{one.harness}/{one.model}", "assistant")
    if assistant.backend != one.harness:
        raise ValueError(f"{one.ident} is a session of {one.harness}, not of {agent}")
    copied = files(one)
    if not copied:
        raise ValueError(f"{one.ident} cannot be continued: its files are gone")
    # Titled by its id where the head of its log gave no line said in it.
    return adopted(
        workspace, assistant, one.ident, copied, title=one.title or one.ident
    )
