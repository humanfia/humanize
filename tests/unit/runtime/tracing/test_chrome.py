from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hmz.runtime.tracing.chrome import build
from hmz.runtime.tracing.profile import Process, Thread
from hmz.runtime.tracing.session import Action, Session

T0 = 1_767_225_600.0


def session(
    key: str,
    spans: list[tuple[float, float]],
    *,
    agent: str = "claude · opus",
    parent: str | None = None,
    label: str = "main",
    spawn: str | None = None,
) -> Session:
    actions = [
        Action(f"a{n}", "tool", T0 + s, T0 + e) for n, (s, e) in enumerate(spans)
    ]
    if spawn is not None:
        actions[0].spawn = spawn
    return Session(
        key=key,
        backend=key.split(":", maxsplit=1)[0],
        ident=key,
        label=label,
        title=f"title of {key}",
        parent=parent,
        agent=agent,
        args={"model": "m"},
        actions=actions,
    )


def named(events: list[dict[str, Any]], kind: str) -> dict[tuple[int, int], str]:
    return {
        (e["pid"], e["tid"]): e["args"]["name"]
        for e in events
        if e["ph"] == "M" and e["name"] == kind
    }


def slices(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if e["ph"] == "X"]


@pytest.mark.parametrize(
    ("workspace", "names", "expected"),
    [
        (None, None, {}),
        (Path("/w"), None, {"workspace": "/w"}),
        (None, ("a", "b"), {"selected": "a, b"}),
        (None, ("a", "b", "c", "d", "e"), {"selected": "5 sessions"}),
        (Path("/w"), (), {"workspace": "/w"}),
    ],
)
def test_nothing_to_draw_is_an_empty_trace(
    workspace: Path | None, names: tuple[str, ...] | None, expected: dict[str, str]
) -> None:
    empty = Session("k", "claude", "k", "main", "t")
    document = build([empty], workspace, names)
    assert document == {
        "traceEvents": [],
        "displayTimeUnit": "ms",
        "otherData": expected,
    }


def test_an_agent_and_its_subagent_with_a_spawn_arrow() -> None:
    root = session("claude:r", [(0, 10), (1, 2)], spawn="claude:c")
    child = session("claude:c", [(1, 3)], parent="claude:r", label="Explore · look")
    document = build([child, root], Path("/w"), ("r",))
    events = document["traceEvents"]
    json.dumps(document)  # it is a JSON document

    assert named(events, "process_name") == {(1, 0): "claude · opus · 2 sessions"}
    labels = [e["args"]["labels"] for e in events if e["name"] == "process_labels"]
    assert labels == ["/w · r"]
    threads = named(events, "thread_name")
    assert threads == {(1, 100): "main", (1, 200): "subagent · Explore"}

    banners = [e for e in slices(events) if e["cat"] == "session"]
    assert {(e["tid"], e["name"]) for e in banners} == {
        (100, "main · title of claude:r"),
        (200, "Explore · look · title of claude:c"),
    }
    banner = next(e for e in banners if e["tid"] == 100)
    assert banner["ts"] == round(T0 * 1e6)
    assert banner["dur"] == 10_000_000
    assert banner["args"]["agent"] == "claude · opus"
    assert banner["args"]["model"] == "m"
    assert banner["args"]["at"] == "2026-01-01T00:00:00+00:00"

    tools = [e for e in slices(events) if e["cat"] == "tool"]
    assert {(e["name"], e["args"]["session"]) for e in tools} == {
        ("a0", "claude:r"),
        ("a1", "claude:r"),
        ("a0", "claude:c"),
    }
    start, finish = (e for e in events if e.get("cat") == "spawn")
    assert (start["ph"], start["tid"], start["ts"]) == ("s", 100, round(T0 * 1e6))
    assert (finish["ph"], finish["bp"], finish["tid"]) == ("f", "e", 200)
    assert finish["ts"] == round((T0 + 1) * 1e6)
    assert start["id"] == finish["id"]

    other = document["otherData"]
    assert other["workspace"] == "/w"
    assert other["selected"] == "r"
    assert other["agents"] == "claude · opus"
    assert other["backends"] == "claude"
    assert (other["sessions"], other["slices"], other["tracks"]) == ("2", "3", "2")
    assert other["start"] == "2026-01-01T00:00:00+00:00"
    assert other["end"] == "2026-01-01T00:00:10+00:00"
    assert "programs" not in other


def test_sessions_that_never_overlap_share_a_track() -> None:
    one = session("codex:a", [(0, 1)])
    two = session("codex:b", [(2, 3)])
    three = session("codex:c", [(2.5, 4)])
    events = build([one, two, three], None, None)["traceEvents"]
    assert named(events, "process_name") == {(1, 0): "claude · opus · 3 sessions"}
    assert sorted(named(events, "thread_name").values()) == ["main", "main #2"]
    tids = {
        e["args"]["session"]: e["tid"] for e in slices(events) if e["cat"] == "session"
    }
    assert tids["codex:a"] == tids["codex:b"] != tids["codex:c"]


def test_overlapping_actions_spill_into_lanes() -> None:
    lone = session("claude:a", [(0, 2), (1, 3)])
    events = build([lone], None, None)["traceEvents"]
    assert named(events, "thread_name") == {(1, 100): "main", (1, 101): "main ~2"}
    tids = {e["name"]: e["tid"] for e in slices(events)}
    # the banner holds the whole session, the first action nests inside it, the second
    # starts before the first ends and ends after it, so it gets a lane of its own
    assert tids["a0"] == 100
    assert tids["a1"] == 101


def test_agents_are_processes_in_the_order_they_started() -> None:
    late = session("codex:x", [(5, 6)], agent="codex")
    early = session("claude:y", [(0, 1)], agent="claude")
    events = build([late, early], None, None)["traceEvents"]
    assert named(events, "process_name") == {
        (1, 0): "claude · 1 session",
        (2, 0): "codex · 1 session",
    }


def test_deeper_and_mixed_subagents_are_named_by_depth() -> None:
    root = session("k:r", [(0, 10)])
    one = session("k:a", [(1, 2)], parent="k:r", label="explore · x")
    other = session("k:b", [(3, 4)], parent="k:r", label="plan")
    deep = session("k:d", [(1, 2)], parent="k:a", label="leaf")
    stray = session("k:s", [(1, 2)], parent="k:missing", label="stray")
    events = build([root, one, other, deep, stray], None, None)["traceEvents"]
    assert sorted(named(events, "thread_name").values()) == [
        "main",
        "subagent",
        "subagent 2 · leaf",
        "subagent · stray #2",
    ]


def test_profiled_programs_are_processes_with_a_track_per_thread() -> None:
    agent = session("claude:a", [(0, 10)])
    threaded = Process(
        pid=42,
        ppid=1,
        name="pytest",
        argv=("pytest", "-q"),
        began=T0 + 1,
        ended=T0 + 5,
        threads=(Thread(42, T0 + 1, T0 + 5, 1.23456), Thread(43, T0 + 2, T0 + 2)),
    )
    bare = Process(pid=7, ppid=42, name="ls", argv=(), began=T0 + 11, ended=T0 + 12)
    document = build([agent], None, None, [bare, threaded])
    events = document["traceEvents"]
    assert named(events, "process_name") == {
        (1, 0): "claude · opus · 1 session",
        (2, 0): "pytest · 42",
        (3, 0): "ls · 7",
    }
    assert named(events, "thread_name") == {
        (1, 100): "main",
        (2, 100): "main",
        (2, 200): "thread 43",
        (3, 100): "main",
    }
    work = [e for e in slices(events) if e["cat"] == "process"]
    first = next(e for e in work if e["pid"] == 2 and e["tid"] == 100)
    assert first["name"] == "pytest · 42"
    assert first["args"] == {
        "pid": 42,
        "ppid": 1,
        "argv": "pytest -q",
        "cpu": 1.235,
        "at": "2026-01-01T00:00:01+00:00",
    }
    instant = next(e for e in work if e["tid"] == 200)
    assert (instant["name"], instant["dur"]) == ("thread 43", 1)
    other = document["otherData"]
    assert other["programs"] == "2"
    assert other["end"] == "2026-01-01T00:00:12+00:00"


def test_programs_alone_still_make_a_trace() -> None:
    ran = [Process(pid=1, ppid=0, name="make", argv=("make",), began=T0, ended=T0 + 1)]
    document = build([], None, None, ran)
    assert named(document["traceEvents"], "process_name") == {(1, 0): "make · 1"}
    assert document["otherData"]["sessions"] == "0"
    assert document["otherData"]["agents"] == ""
