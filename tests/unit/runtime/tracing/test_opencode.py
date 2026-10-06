"""opencode and mimocode, which keep the same three tables in databases of their own name."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing.readers import mimo, opencode
from tests.unit.runtime.tracing.logs import ALL

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.runtime.tracing.session import Session

T0 = 1_767_225_600
WORKSPACE = "/work/repo"

#: The session columns opencode has and its fork dropped.
FULL = "id, directory, title, parent_id, version, agent, model, time_created"
FORK = "id, directory, title, parent_id, time_created"

READERS = [
    pytest.param(opencode.collect, opencode.DATABASE, "opencode", FULL, id="opencode"),
    pytest.param(mimo.collect, mimo.DATABASE, "mimo", FORK, id="mimo"),
]


def ms(offset: float) -> int:
    return round((T0 + offset) * 1000)


class Store:
    """One of these databases, written the way the CLI writes it."""

    def __init__(self, path: Path, columns: str) -> None:
        self.connection = sqlite3.connect(path)
        self.columns = columns.split(", ")
        self.connection.execute(f"create table session ({columns})")
        self.connection.execute(
            "create table message (id, session_id, time_created, time_updated, data)"
        )
        self.connection.execute(
            "create table part (id, message_id, session_id, time_created, data)"
        )

    def session(self, ident: str, at: float = 0, **fields: Any) -> None:
        row = {"id": ident, "directory": WORKSPACE, "time_created": ms(at), **fields}
        held = {k: v for k, v in row.items() if k in self.columns}
        names = ", ".join(held)
        marks = ", ".join("?" for _ in held)
        self.connection.execute(
            f"insert into session ({names}) values ({marks})",  # noqa: S608
            list(held.values()),
        )

    def message(
        self, ident: str, session: str, at: float, ended: float | None, **data: Any
    ) -> None:
        self.connection.execute(
            "insert into message values (?, ?, ?, ?, ?)",
            (
                ident,
                session,
                ms(at),
                None if ended is None else ms(ended),
                json.dumps(data),
            ),
        )

    def part(self, message: str, session: str, at: float, **data: Any) -> None:
        self.connection.execute(
            "insert into part values (?, ?, ?, ?, ?)",
            (f"p{at}", message, session, ms(at), json.dumps(data)),
        )

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()


def conversation(store: Store, sid: str) -> None:
    store.message("m1", sid, 1, 1.5, role="user")
    store.part("m1", sid, 1, type="text", text="fix")
    store.part("m1", sid, 1.1, type="text", text="it")
    store.part("m1", sid, 1.2, type="file")
    store.message(
        "m2",
        sid,
        2,
        9,
        role="assistant",
        modelID="answered-by",
        providerID="prov",
        tokens={"input": 3, "cache": {"read": 1}},
    )
    store.part("m2", sid, 2, type="step-start")
    store.part("m2", sid, 2.1, type="reasoning", text="plan")
    store.part(
        "m2", sid, 2.2, type="text", text="ok", time={"start": ms(2.2), "end": ms(2.4)}
    )
    store.part(
        "m2",
        sid,
        3,
        type="tool",
        tool="bash",
        state={
            "status": "completed",
            "input": {"command": "ls"},
            "output": "a b",
            "time": {"start": ms(3), "end": ms(4)},
        },
    )
    store.part(
        "m2",
        sid,
        5,
        type="tool",
        tool="edit",
        state={"status": "error", "input": {}, "error": "denied"},
    )
    store.part("m2", sid, 6, type="tool", state={"status": "running"})
    store.part("m2", sid, 7, type="step-finish")
    store.connection.execute(
        "insert into message values ('m3', ?, 'late', null, '{}')", (sid,)
    )


@pytest.mark.parametrize(("collect", "database", "backend", "columns"), READERS)
def test_reads_a_conversation(
    tmp_path: Path,
    collect: Callable[..., list[Session]],
    database: str,
    backend: str,
    columns: str,
) -> None:
    store = Store(tmp_path / database, columns)
    store.session(
        "s1-abcdefghijk",
        title="Fixing it",
        version="1.0",
        agent="build",
        model=json.dumps({"modelID": "configured", "providerID": "cfg"}),
    )
    conversation(store, "s1-abcdefghijk")
    store.close()

    [session] = collect(tmp_path, None, None, ALL)
    assert (session.key, session.backend, session.label, session.parent) == (
        f"{backend}:s1-abcdefghijk",
        backend,
        "main",
        None,
    )
    assert session.title == "s1-abcdefghi · Fixing it"
    assert session.args["cwd"] == WORKSPACE
    assert session.args["database"] == database
    if backend == "opencode":
        assert session.args["model"] == "configured"
        assert session.args["provider"] == "cfg"
        assert (session.args["version"], session.args["agent"]) == ("1.0", "build")
    else:
        assert session.args["model"] == "answered-by"
        assert session.args["provider"] == "prov"
        assert "version" not in session.args

    shape = [
        (a.category, a.name, round(a.start - T0, 3), round(a.end - T0, 3))
        for a in session.actions
    ]
    assert shape == [
        ("turn", "turn: fix it", 1, 1.5),
        ("llm", "think: plan", 2, 9),
        ("message", "say: ok", 2.2, 2.4),
        ("tool", "bash: ls", 3, 4),
        ("tool", "edit", 5, 9),
        ("tool", "tool", 6, 9),
    ]
    think, bash, edit, running = session.actions[1], *session.actions[3:]
    assert think.args["usage"] == {"input": 3, "cache": {"read": 1}}
    assert bash.args == {
        "tool": "bash",
        "input": {"command": "ls"},
        "status": "completed",
        "output": "a b",
    }
    assert edit.args["error"] == "denied"
    assert "unfinished" not in edit.args
    assert running.args["unfinished"] is True


@pytest.mark.parametrize(("collect", "database", "backend", "columns"), READERS)
def test_subsessions_workspaces_and_selection(
    tmp_path: Path,
    collect: Callable[..., list[Session]],
    database: str,
    backend: str,
    columns: str,
) -> None:
    store = Store(tmp_path / database, columns)
    store.session("root", 0)
    store.session("child", 1, parent_id="root")
    store.session("orphan", 2, parent_id="gone")
    store.session("far", 3, directory="/else")
    store.session("nodir", 4, directory=None)
    store.close()

    found = {s.ident: s for s in collect(tmp_path, Path(WORKSPACE), None, ALL)}
    assert set(found) == {"root", "child", "orphan"}
    assert (found["child"].label, found["child"].parent) == (
        "subagent",
        f"{backend}:root",
    )
    assert (found["orphan"].label, found["orphan"].parent) == ("subagent", None)
    assert found["root"].title == "root"
    everything = [s.ident for s in collect(tmp_path, None, None, ALL)]
    assert everything == ["root", "child", "orphan", "far", "nodir"]
    [only] = collect(tmp_path, None, ("chi",), ALL)
    assert only.parent is None  # its parent was not collected


@pytest.mark.parametrize(("collect", "database", "backend", "columns"), READERS)
def test_missing_or_unreadable_database_is_no_sessions(
    tmp_path: Path,
    collect: Callable[..., list[Session]],
    database: str,
    backend: str,
    columns: str,
) -> None:
    assert collect(tmp_path, None, None, ALL) == []
    (tmp_path / database).write_bytes(b"this is not a sqlite database, not at all.....")
    assert collect(tmp_path, None, None, ALL) == []
    (tmp_path / database).unlink()
    sqlite3.connect(tmp_path / database).close()  # a database with no tables
    assert collect(tmp_path, None, None, ALL) == []


def test_window_cuts_messages(tmp_path: Path) -> None:
    store = Store(tmp_path / opencode.DATABASE, FULL)
    store.session("s")
    store.message("a", "s", 1, None, role="user")
    store.message("b", "s", 50, None, role="user")
    store.close()
    [session] = opencode.collect(tmp_path, None, None, (T0, T0 + 10))
    assert [(a.name, a.start, a.end) for a in session.actions] == [
        ("turn: ", T0 + 1, T0 + 1)
    ]
