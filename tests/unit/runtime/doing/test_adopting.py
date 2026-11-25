"""The sessions a harness had of its own: listed off made-up homes, and adopted as a chat.

Every home here is made up under the test's own directory, and what is known of each CLI
(`hmz.coganchor.backends`) is stood in for: no harness of whoever runs this is read.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import sqlite3
import urllib.parse
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from hmz import data
from hmz.runtime.doing import adopting
from hmz.runtime.epic import CHATTED, SESSIONS, read

if TYPE_CHECKING:
    from pathlib import Path

#: What each CLI keeps a session in, as its profile says it.
KEEPS = {
    "claude": ("projects", "file-history"),
    "codex": ("sessions", "archived_sessions"),
    "grok": ("sessions",),
    "pi": ("sessions",),
    "omp": ("sessions",),
    "qwen": ("projects",),
    "opencode": ("opencode.db*",),
    "mimo": ("mimocode.db*",),
    "agy": ("conversations",),
    "kimi": ("sessions",),
    "mcode": ("v2/sessions",),
    "dsh": ("sessions",),
}


class Backends:
    """What `hmz.coganchor.backends` says of each CLI, of homes under one directory."""

    def __init__(self, homes: Path) -> None:
        self.homes = homes
        self.installed = set(KEEPS)
        self.forks = set(KEEPS) - {"qwen", "agy", "mcode", "dsh"}
        self.unread: set[str] = set()

    def named(self, name: str) -> Any:
        if name not in KEEPS:
            return None

        def directory() -> Path:
            if name in self.unread:
                raise OSError("unreadable")
            return self.homes / name

        return SimpleNamespace(
            name=name,
            sessions=KEEPS[name],
            forks=name in self.forks,
            directory=directory,
        )

    def program(self, name: str) -> str | None:
        return f"/bin/{name}" if name in self.installed else None


@pytest.fixture
def clis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Backends:
    stood = Backends(tmp_path / "homes")
    monkeypatch.setattr(adopting, "backends", stood)
    return stood


@pytest.fixture
def packaged(monkeypatch: pytest.MonkeyPatch) -> set[str]:
    """The packages said to be installed in this Python, which dsh is and no program."""
    held = {"deepseek_harness"}
    find = importlib.util.find_spec

    def found(name: str, package: str | None = None) -> object:
        if name == "deepseek_harness":
            return name in held or None
        return find(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", found)
    return held


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    at = tmp_path / "project"
    at.mkdir()
    return at.resolve()


def _written(path: Path, rows: list[dict[str, Any]], at: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(one) + "\n" for one in rows))
    if at:
        os.utime(path, (at, at))
    return path


def _plain(at: Path) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", str(at))


def _claude(
    clis: Backends, cwd: Path, ident: str, said: str, at: float = 0, model: str = "m1"
) -> Path:
    return _written(
        clis.homes / "claude" / "projects" / _plain(cwd) / f"{ident}.jsonl",
        [
            {
                "type": "user",
                "isMeta": True,
                "cwd": str(cwd),
                "message": {"content": "x"},
            },
            {
                "type": "user",
                "cwd": str(cwd),
                "timestamp": "2026-01-01T00:00:01Z",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": said}],
                },
            },
            {
                "type": "assistant",
                "cwd": str(cwd),
                "timestamp": "2026-01-01T00:00:02Z",
                "message": {"role": "assistant", "model": model, "content": []},
            },
        ],
        at,
    )


def _codex(
    clis: Backends, cwd: Path, ident: str, said: str, at: float = 0, **meta: str
) -> Path:
    return _written(
        clis.homes
        / "codex"
        / "sessions"
        / "2026"
        / "01"
        / "02"
        / f"rollout-2026-01-02T03-04-05-{ident}.jsonl",
        [
            {
                "timestamp": "2026-01-02T03:04:05Z",
                "type": "session_meta",
                "payload": {"id": ident, "cwd": str(cwd), **meta},
            },
            {"type": "turn_context", "payload": {"model": "g1"}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "<environment_context>"},
            },
            {"type": "event_msg", "payload": {"type": "user_message", "message": said}},
        ],
        at,
    )


def test_each_harness_lists_its_own_sessions_of_the_workspace_newest_first(
    clis: Backends, workspace: Path, tmp_path: Path
) -> None:
    _claude(clis, workspace, "c-1", "tidy the parser\nand the tests", 100)
    _codex(clis, workspace, "x-1", "sketch a changelog", 300)
    _written(
        clis.homes / "pi" / "sessions" / "--project--" / "2026_p-1.jsonl",
        [
            {
                "type": "session",
                "cwd": str(workspace),
                "timestamp": "2026-01-03T00:00:00Z",
            },
            {"type": "model_change", "modelId": "p1"},
            {"message": {"role": "user", "content": "ask pi"}},
        ],
        200,
    )
    _written(
        clis.homes / "qwen" / "projects" / _plain(workspace) / "chats" / "q-1.jsonl",
        [
            {
                "type": "user",
                "cwd": str(workspace),
                "message": {"parts": [{"text": "ask qwen"}]},
            }
        ],
        50,
    )
    quoted = urllib.parse.quote(str(workspace), safe="")
    _written(
        clis.homes / "grok" / "sessions" / quoted / "g-1" / "updates.jsonl",
        [
            {
                "params": {
                    "update": {
                        "sessionUpdate": "user_message_chunk",
                        "_meta": {"modelId": "k1"},
                        "content": {"type": "text", "text": "ask grok"},
                    }
                }
            }
        ],
        25,
    )
    # Another directory's, which are none of this workspace's.
    other = tmp_path / "other"
    _claude(clis, other, "c-2", "elsewhere", 400)
    _codex(clis, other, "x-2", "elsewhere", 400)

    found = adopting.listed(workspace)

    assert [(one.harness, one.ident, one.title, one.model) for one in found] == [
        ("codex", "x-1", "sketch a changelog", "g1"),
        ("pi", "p-1", "ask pi", "p1"),
        ("claude", "c-1", "tidy the parser", "m1"),
        ("qwen", "q-1", "ask qwen", ""),
        ("grok", "g-1", "ask grok", "k1"),
    ]
    assert {one.cwd for one in found} == {str(workspace)}
    assert found[0].began == "2026-01-02T03:04:05Z"
    assert found[2].began == "2026-01-01T00:00:01Z"
    assert found[2].updated.startswith("1970-01-01T00:01:40")


def test_a_session_a_chat_or_an_epic_opened_is_left_out(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    _claude(clis, workspace, "c-2", "two")
    _codex(clis, workspace, "c-1", "the same id, of another harness")

    found = adopting.listed(workspace, {("claude", "c-1")})

    assert sorted((one.harness, one.ident) for one in found) == [
        ("claude", "c-2"),
        ("codex", "c-1"),
    ]


def test_a_thread_another_started_or_was_cut_from_is_no_session_of_its_own(
    clis: Backends, workspace: Path
) -> None:
    _codex(clis, workspace, "x-1", "the thread")
    _codex(clis, workspace, "x-2", "its sub-agent", parent_thread_id="x-1")
    _codex(clis, workspace, "x-3", "its fork", forked_from_id="x-1")

    assert [one.ident for one in adopting.listed(workspace)] == ["x-1"]


def test_only_a_harness_installed_here_and_kept_outside_humanize_is_listed(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    _codex(clis, workspace, "x-1", "two")

    clis.installed.discard("codex")
    assert [one.harness for one in adopting.listed(workspace)] == ["claude"]

    # One whose home is Humanize's own keeps what Humanize ran, which is no harness session.
    clis.homes = data() / "kept"
    _claude(clis, workspace, "c-9", "kept by humanize")
    assert adopting.listed(workspace) == []


def test_a_harness_that_cannot_be_read_does_not_fail_the_listing(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    _codex(clis, workspace, "x-1", "two")
    clis.unread.add("claude")

    assert [one.harness for one in adopting.listed(workspace)] == ["codex"]


def test_only_the_head_and_the_tail_of_a_log_are_read(
    clis: Backends, workspace: Path
) -> None:
    padding = {"type": "progress", "cwd": str(workspace), "data": "x" * 1024}
    said = {"type": "user", "message": {"role": "user", "content": "said too late"}}
    last: dict[str, Any] = {"type": "assistant", "message": {"model": "m9"}}
    _written(
        clis.homes / "claude" / "projects" / _plain(workspace) / "c-1.jsonl",
        [*[padding] * 600, said, *[padding] * 600, last],
    )

    (one,) = adopting.listed(workspace)

    # What is said past the head is not what it is titled by; its tail says its model.
    assert (one.title, one.model) == ("", "m9")


def test_a_log_changed_is_read_again(clis: Backends, workspace: Path) -> None:
    log = _claude(clis, workspace, "c-1", "first", 100)
    assert adopting.listed(workspace)[0].title == "first"

    _claude(clis, workspace, "c-1", "second, and longer", 200)

    assert log.is_file()
    assert adopting.listed(workspace)[0].title == "second, and longer"


def test_the_files_of_a_session_are_those_its_cli_keeps_that_name_it(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    _claude(clis, workspace, "c-2", "two")
    under = clis.homes / "claude"
    project = under / "projects" / _plain(workspace)
    _written(project / "c-1" / "subagents" / "agent-a.jsonl", [{}])
    _written(under / "file-history" / "c-1" / "a@v1", [{}])
    _written(under / "settings" / "c-1.json", [{}])
    (one,) = [each for each in adopting.listed(workspace) if each.ident == "c-1"]

    assert sorted(adopting.files(one)) == [
        "file-history/c-1/a@v1",
        f"projects/{project.name}/c-1.jsonl",
        f"projects/{project.name}/c-1/subagents/agent-a.jsonl",
    ]


def test_adopting_copies_a_session_into_a_chat_that_rests_and_leaves_it_as_it_was(
    clis: Backends, workspace: Path
) -> None:
    log = _claude(clis, workspace, "c-1", "tidy the parser", 100, model="opus-9")
    before = (log.read_bytes(), log.stat().st_mtime_ns)
    (one,) = adopting.listed(workspace)

    at = adopting.adopt(one, workspace)

    assert (log.read_bytes(), log.stat().st_mtime_ns) == before
    assert at.parent.parent == data() / "chats"
    copy = at / SESSIONS / "claude" / "projects" / log.parent.name / "c-1.jsonl"
    assert copy.read_bytes() == before[0]
    ran = read(at)
    assert ran is not None
    assert (ran.chat, ran.adopted, ran.title, ran.task, ran.how, ran.forked) == (
        True,
        "claude:c-1",
        "tidy the parser",
        "tidy the parser",
        "stopped",
        "",
    )
    assert ran.workspace == str(workspace)
    assert [one.spec for one in ran.agents] == ["claude/opus-9:auto"]
    assert [(s.backend, s.ident, s.where) for s in ran.sessions] == [
        ("claude", "c-1", f"{SESSIONS}/claude")
    ]
    assert sorted(one.name for one in at.iterdir()) == [CHATTED, SESSIONS]
    # Opened by a chat now, it is no harness session any more.
    owned = {(s.backend, s.ident) for s in ran.sessions}
    assert adopting.listed(workspace, owned) == []


def test_adopting_takes_another_agent_of_the_same_harness(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    (one,) = adopting.listed(workspace)

    ran = read(adopting.adopt(one, workspace, "claude/sonnet-9:high"))

    assert ran is not None
    assert [each.spec for each in ran.agents] == ["claude/sonnet-9:high"]
    with pytest.raises(ValueError, match="c-1 is a session of claude, not of codex/g1"):
        adopting.adopt(one, workspace, "codex/g1")


def test_a_session_that_says_no_line_is_titled_by_its_id(
    clis: Backends, workspace: Path
) -> None:
    _written(
        clis.homes / "claude" / "projects" / _plain(workspace) / "c-1.jsonl",
        [{"type": "summary", "cwd": str(workspace), "message": {"model": "m1"}}],
    )
    (one,) = adopting.listed(workspace)
    assert one.title == ""

    ran = read(adopting.adopt(one, workspace))

    assert ran is not None
    assert (ran.title, ran.task) == ("c-1", "c-1")


def test_adopting_is_refused_where_a_copy_could_not_be_carried_on(
    clis: Backends, workspace: Path
) -> None:
    _written(
        clis.homes / "qwen" / "projects" / _plain(workspace) / "chats" / "q-1.jsonl",
        [
            {
                "type": "user",
                "cwd": str(workspace),
                "message": {"parts": [{"text": "q"}]},
            }
        ],
    )
    _written(
        clis.homes / "claude" / "projects" / _plain(workspace) / "c-1.jsonl",
        [{"type": "user", "cwd": str(workspace), "message": {"content": "no model"}}],
    )
    qwen, claude = sorted(adopting.listed(workspace), key=lambda one: one.harness)[::-1]

    with pytest.raises(ValueError, match="qwen cannot carry a session of its own on"):
        adopting.adopt(qwen, workspace)
    with pytest.raises(ValueError, match="c-1 does not say the model it ran on"):
        adopting.adopt(claude, workspace)
    gone = claude._replace(ident="c-0", model="m1")
    with pytest.raises(ValueError, match="c-0 cannot be continued: its files are gone"):
        adopting.adopt(gone, workspace)
    assert not (data() / "chats").exists()


# ------------------------------------------- the harnesses that are listed and not carried on


def _database(
    path: Path, table: str, rows: list[dict[str, Any]], at: float = 0
) -> Path:
    """One table of a database a harness keeps, of the columns its first row names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    columns = list(dict.fromkeys(name for one in rows for name in one))
    with sqlite3.connect(path) as connection:
        connection.execute(f"create table {table} ({', '.join(columns)})")
        connection.executemany(
            f"insert into {table} values ({', '.join('?' * len(columns))})",  # noqa: S608 -- names this test wrote
            [tuple(one.get(name) for name in columns) for one in rows],
        )
    connection.close()
    if at:
        os.utime(path, (at, at))
    return path


def _opencode(
    cwd: Path, ident: str, title: str, at: int, **more: Any
) -> dict[str, Any]:
    return {
        "id": ident,
        "parent_id": None,
        "directory": str(cwd),
        "title": title,
        "time_created": at * 1000,
        "time_updated": (at + 60) * 1000,
        "model": json.dumps({"modelID": "o1", "providerID": "zen"}),
    } | more


def _agy(clis: Backends, rows: list[tuple[str, str, list[str], str]]) -> Path:
    for at, (ident, *_) in enumerate(rows, 1):
        log = clis.homes / "agy" / "conversations" / f"{ident}.db"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_bytes(b"")
        os.utime(log, (at * 1000, at * 1000))
    return _database(
        clis.homes / "agy" / "conversation_summaries.db",
        "conversation_summaries",
        [
            {
                "conversation_id": ident,
                "title": title,
                "workspace_uris": json.dumps(
                    [f"file://{urllib.parse.quote(one)}" for one in places]
                ),
                "parent_conversation_id": parent,
            }
            for ident, title, places, parent in rows
        ],
    )


def _kimi(clis: Backends, cwd: Path, ident: str, said: str, at: float = 0) -> Path:
    folder = clis.homes / "kimi" / "sessions" / "proj" / ident
    _written(folder / "state.json", [{"workDir": str(cwd), "agents": {"main": {}}}])
    _written(folder / "agents" / "sub" / "wire.jsonl", [{"type": "turn.prompt"}])
    return _written(
        folder / "agents" / "main" / "wire.jsonl",
        [
            {"type": "llm.request", "modelAlias": "k3"},
            {"type": "turn.prompt", "input": "said by an agent", "origin": "agent"},
            {"type": "turn.prompt", "input": said, "origin": "user"},
        ],
        at,
    )


def _mcode(clis: Backends, ident: str, said: str, at: float = 0) -> Path:
    encoded = base64.urlsafe_b64encode(ident.encode()).decode().rstrip("=")
    inside = f"<reminder>x</reminder>{said}"
    return _written(
        clis.homes
        / "mcode"
        / "v2"
        / "sessions"
        / "2026"
        / "01"
        / "01"
        / f"20260101T000000-session_{encoded}"
        / "messages.jsonl",
        [
            {
                "message": {
                    "role": "user",
                    "content": inside,
                    "canonicalTextRange": {"startOffset": 22, "endOffset": len(inside)},
                }
            },
            {"message": {"role": "assistant", "model": "m2", "content": []}},
        ],
        at,
    )


def _placed(clis: Backends, places: dict[str, Path]) -> Path:
    """Where each MiniMax Code session worked, in the database one is resumed out of."""
    return _database(
        clis.homes / "mcode" / "v2" / "sqlite" / "runtime-state.sqlite",
        "local_runtime_sessions",
        [
            {
                "session_id": ident,
                "record_json": json.dumps({"workspaceDir": str(where)}),
            }
            for ident, where in places.items()
        ],
    )


def _dsh(
    clis: Backends,
    cwd: Path,
    ident: str,
    said: str,
    at: float = 0,
    name: str = "session.v4.jsonl",
    **header: Any,
) -> Path:
    return _written(
        clis.homes / "dsh" / "sessions" / "proj" / ident / name,
        [
            {"type": "session", "id": ident, "cwd": str(cwd), **header},
            {
                "type": "request/header",
                "data": {"header": {"config": {"model": "d1"}}},
            },
            {
                "type": "user/message",
                "data": {"source": {"kind": "system"}, "content": "set up"},
            },
            {
                "type": "user/message",
                "data": {"source": {"kind": "user"}, "content": said},
            },
        ],
        at,
    )


@pytest.mark.usefixtures("packaged")
def test_a_harness_that_carries_no_copy_on_lists_its_sessions_all_the_same(
    clis: Backends, workspace: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other"
    _database(
        clis.homes / "opencode" / "opencode.db",
        "session",
        [
            _opencode(workspace, "o-1", "Ask opencode", 600),
            _opencode(other, "o-2", "elsewhere", 700),
        ],
    )
    # The fork keeps no model on a session.
    mimo = _opencode(workspace, "i-1", "Ask mimo", 500)
    del mimo["model"]
    _database(clis.homes / "mimo" / "mimocode.db", "session", [mimo])
    _agy(
        clis,
        [
            ("a-1", "Ask agy\nand more", [str(other), str(workspace)], ""),
            ("a-2", "elsewhere", [str(other)], ""),
        ],
    )
    _kimi(clis, workspace, "session_k1", "ask kimi\nand more", 400)
    _kimi(clis, other, "session_k2", "elsewhere", 400)
    _mcode(clis, "m-1", "ask mcode", 300)
    _mcode(clis, "m-2", "elsewhere", 300)
    _mcode(clis, "m-3", "nowhere the database says", 300)
    _placed(clis, {"m-1": workspace, "m-2": other})
    _dsh(clis, workspace, "session-d1", "an older generation", 100, "session.v3.jsonl")
    _dsh(clis, workspace, "session-d1", "ask dsh", 200)
    _dsh(clis, other, "session-d2", "elsewhere", 200)
    # Compressed, which nothing here reads: not listed.
    _dsh(clis, workspace, "session-d3", "unread", 200, "session.v4.jsonl.zstd")

    found = adopting.listed(workspace)

    assert [(one.harness, one.ident, one.title, one.model) for one in found] == [
        ("agy", "a-1", "Ask agy", ""),
        ("opencode", "o-1", "Ask opencode", "o1"),
        ("mimo", "i-1", "Ask mimo", ""),
        ("kimi", "session_k1", "ask kimi", "k3"),
        ("mcode", "m-1", "ask mcode", "m2"),
        ("dsh", "session-d1", "ask dsh", "d1"),
    ]
    assert {one.cwd for one in found} == {str(workspace)}
    assert (found[1].began, found[1].updated) == (
        "1970-01-01T00:10:00+00:00",
        "1970-01-01T00:11:00+00:00",
    )
    assert found[0].updated == "1970-01-01T00:16:40+00:00"
    assert not set(adopting.CARRIED) & {one.harness for one in found}
    assert {one.harness for one in found} <= set(adopting.HARNESSES)
    # Each is left out once a chat or an epic opened it, as any other is.
    owned = {(one.harness, one.ident) for one in found}
    assert adopting.listed(workspace, owned) == []


@pytest.mark.usefixtures("packaged")
def test_a_session_another_started_is_no_session_of_its_own_in_a_database_either(
    clis: Backends, workspace: Path
) -> None:
    _database(
        clis.homes / "opencode" / "opencode.db",
        "session",
        [
            _opencode(workspace, "o-1", "the session", 600),
            _opencode(workspace, "o-2", "its sub-agent", 700, parent_id="o-1"),
        ],
    )
    _agy(
        clis,
        [
            ("a-1", "the conversation", [str(workspace)], ""),
            ("a-2", "nested in it", [str(workspace)], "a-1"),
        ],
    )
    # Untitled by its CLI, it is titled by what it was first told, where that is kept.
    with sqlite3.connect(clis.homes / "agy" / "conversation_summaries.db") as held:
        held.execute("alter table conversation_summaries add column preview")
        held.execute("update conversation_summaries set title = '', preview = 'told'")
    held.close()
    assert [one.title for one in adopting.listed(workspace)] == ["told", "the session"]
    _dsh(clis, workspace, "session-d1", "the session")
    _dsh(clis, workspace, "session-d2", "its child", parentSession="session-d1")

    assert sorted(one.ident for one in adopting.listed(workspace)) == [
        "a-1",
        "o-1",
        "session-d1",
    ]


def test_a_database_is_only_read_and_read_again_once_it_was_written(
    clis: Backends, workspace: Path
) -> None:
    store = clis.homes / "opencode" / "opencode.db"
    _database(store, "session", [_opencode(workspace, "o-1", "first", 600)], 100)
    before = (store.read_bytes(), store.stat().st_mtime_ns)

    assert [one.title for one in adopting.listed(workspace)] == ["first"]
    assert (store.read_bytes(), store.stat().st_mtime_ns) == before
    assert sorted(one.name for one in store.parent.iterdir()) == ["opencode.db"]

    _database(store, "session", [_opencode(workspace, "o-1", "second", 600)], 200)
    assert [one.title for one in adopting.listed(workspace)] == ["second"]


@pytest.mark.usefixtures("packaged")
def test_a_database_that_cannot_be_read_lists_nothing_and_fails_nothing(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    for at in ("opencode/opencode.db", "agy/conversation_summaries.db"):
        (clis.homes / at).parent.mkdir(parents=True)
        (clis.homes / at).write_bytes(b"no database at all")
    # Rows that say too little of a session are passed over, and the rest are listed.
    _database(
        clis.homes / "mimo" / "mimocode.db",
        "session",
        [
            {"id": "i-0", "directory": str(workspace), "time_created": "soon"},
            _opencode(workspace, "i-1", "whole", 5) | {"model": "{"},
            _opencode(workspace, "i-2", "whole", 5),
        ],
    )
    _kimi(clis, workspace, "session_k1", "ask kimi")
    state = clis.homes / "kimi" / "sessions" / "proj" / "session_k1" / "state.json"
    state.write_text("{")
    _mcode(clis, "m-1", "ask mcode")
    _placed(clis, {"m-1": workspace}).write_bytes(b"no database at all")

    found = adopting.listed(workspace)

    assert sorted((one.harness, one.ident) for one in found) == [
        ("claude", "c-1"),
        ("mimo", "i-2"),
    ]


def test_dsh_is_listed_where_its_package_is_installed(
    clis: Backends, workspace: Path, packaged: set[str]
) -> None:
    # A package of this Python and no program: no program of its name says it is here.
    clis.installed.discard("dsh")
    _dsh(clis, workspace, "session-d1", "ask dsh")
    assert [one.harness for one in adopting.listed(workspace)] == ["dsh"]

    packaged.clear()
    assert adopting.listed(workspace) == []


@pytest.mark.usefixtures("packaged")
def test_adopting_is_refused_for_a_harness_that_is_listed_and_carries_none_on(
    clis: Backends, workspace: Path
) -> None:
    _database(
        clis.homes / "opencode" / "opencode.db",
        "session",
        [_opencode(workspace, "o-1", "Ask opencode", 600)],
    )
    _kimi(clis, workspace, "session_k1", "ask kimi")
    _dsh(clis, workspace, "session-d1", "ask dsh")
    found = adopting.listed(workspace)
    assert len(found) == 3

    for one in found:
        with pytest.raises(
            ValueError, match=f"{one.harness} cannot carry a session of its own on"
        ):
            adopting.adopt(one, workspace)
    assert not (data() / "chats").exists()
