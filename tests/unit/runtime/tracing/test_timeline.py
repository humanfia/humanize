from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Any

import pytest

from hmz.runtime.epic import Called, Ran
from hmz.runtime.epic import Session as Opened
from hmz.runtime.tracing.profile import Process, Thread
from hmz.runtime.tracing.session import Action, Session
from hmz.runtime.tracing.timeline import VERSION, build

T0 = 1_767_225_600.0


def iso(seconds: float) -> str:
    return datetime.datetime.fromtimestamp(T0 + seconds, datetime.UTC).isoformat()


def ran(*, ended: float | None = 100.0, opened: tuple[Opened, ...] = ()) -> Ran:
    return Ran(
        at=Path("/epics/20260101T000000.000Z"),
        flow="ralph",
        task="fix it",
        began=iso(0),
        ended=iso(ended) if ended is not None else "",
        how="done" if ended is not None else "",
        sessions=opened,
    )


def columns(document: dict[str, Any], track: int) -> list[dict[str, Any]]:
    """One track's spans, a row apiece, with every string read back."""
    held = document["tracks"][track]["spans"]
    strings = document["strings"]
    return [
        {
            "start": held["start"][at],
            "dur": held["dur"][at],
            "depth": held["depth"][at],
            "cat": strings[held["cat"][at]],
            "name": strings[held["name"][at]],
            "model": strings[held["model"][at]],
            "in": held["in"][at],
            "out": held["out"][at],
        }
        for at in range(document["tracks"][track]["count"])
    ]


def text(document: dict[str, Any], index: int) -> str:
    return document["strings"][index]


def epic_with_everything() -> tuple[dict[str, Any], Any]:
    root = Session(
        key="claude:r",
        backend="claude",
        ident="r",
        label="main",
        title="r · hello",
        agent="builder · opus",
        args={"model": "opus"},
        actions=[
            Action("turn", "turn", T0 + 10, T0 + 40, {"prompt": "hello"}),
            Action(
                "think",
                "llm",
                T0 + 11,
                T0 + 15,
                {"model": "opus", "usage": {"input_tokens": 70, "output_tokens": 30}},
            ),
            Action(
                "Task: look", "tool", T0 + 16, T0 + 30, {"in": "x"}, spawn="claude:c"
            ),
        ],
    )
    child = Session(
        key="claude:c",
        backend="claude",
        ident="r",
        label="Explore · look",
        title="c",
        parent="claude:r",
        agent="builder · opus",
        actions=[Action("Read: a", "tool", T0 + 17, T0 + 20)],
    )
    program = Process(
        pid=42,
        ppid=1,
        name="pytest",
        argv=("pytest", "-q"),
        began=T0 + 18,
        ended=T0 + 25,
        threads=(Thread(42, T0 + 18, T0 + 25, 1.5), Thread(43, T0 + 19, T0 + 21)),
    )
    worker = Process(42 + 1000, 42, "node", ("node",), T0 + 19, T0 + 20)
    opened = (
        Opened("builder", "claude", "local", "r", "n", record="epic.ralph_1.jsonl"),
    )
    calls = (
        Called(
            "official/review",
            "look again",
            "epic.ralph_1.jsonl",
            began=iso(5),
            ended=iso(50),
            how="done",
        ),
    )
    laid = build(
        [child, root],
        ran=ran(opened=opened),
        calls=calls,
        profiled=[worker, program],
    )
    return laid.document, laid


def test_an_epic_is_laid_out_as_processes_tracks_and_columns() -> None:
    document, _ = epic_with_everything()

    assert document["version"] == VERSION
    assert document["epic"] == "20260101T000000.000Z"
    assert document["origin"] == T0
    assert document["live"] is False
    assert document["strings"][0] == ""
    flow, root, child, program, worker = document["processes"]
    assert [one["kind"] for one in document["processes"]] == [
        "flow",
        "session",
        "session",
        "os",
        "os",
    ]
    assert [one["id"] for one in document["processes"]] == [0, 1, 2, 3, 4]
    # The epic's own sessions hang from the flows, sub-agents from what spawned them, and a
    # program from the program that started it.
    assert [one["parent"] for one in document["processes"]] == [-1, 0, 1, -1, 3]
    assert text(document, root["key"]) == "claude:r"
    assert text(document, root["role"]) == "builder"
    assert text(document, root["model"]) == "opus"
    assert text(document, root["record"]) == "epic.ralph_1.jsonl"
    assert text(document, child["label"]) == "Explore · look"
    assert (root["start"], root["end"]) == (10_000_000, 40_000_000)
    assert (program["pid"], worker["pid"]) == (42, 1042)
    assert text(document, flow["name"]) == "ralph"

    flows = columns(document, flow["tracks"][0])
    assert [(one["name"], one["depth"], one["start"], one["dur"]) for one in flows] == [
        ("ralph", 0, 0, 100_000_000),
        ("official/review", 1, 5_000_000, 45_000_000),
    ]
    (track,) = root["tracks"]
    assert text(document, document["tracks"][track]["name"]) == "main"
    spans = columns(document, track)
    assert [(one["cat"], one["depth"]) for one in spans] == [
        ("session", 0),
        ("turn", 1),
        ("llm", 2),
        ("tool", 2),
    ]
    assert (spans[2]["model"], spans[2]["in"], spans[2]["out"]) == ("opus", 70, 30)
    assert document["tracks"][track]["depths"] == 3
    threads = columns(document, program["tracks"][0])
    assert [one["name"] for one in threads] == ["pytest · 42", "thread 43"]


def test_spans_are_numbered_by_track_and_spawns_point_at_processes() -> None:
    document, laid = epic_with_everything()

    tracks = document["tracks"]
    assert [one["first"] for one in tracks] == [
        sum(one["count"] for one in tracks[:at]) for at in range(len(tracks))
    ]
    assert (
        document["summary"]["spans"]
        == len(laid.details)
        == sum(one["count"] for one in tracks)
    )
    root_track = document["processes"][1]["tracks"][0]
    first = tracks[root_track]["first"]
    tool, call = first + 3, tracks[document["processes"][0]["tracks"][0]]["first"] + 1
    spawns = document["spawns"]
    assert list(zip(spawns["span"], spawns["process"], strict=True)) == [
        (call, 1),
        (tool, 2),
    ]


def test_a_span_is_read_whole_by_its_id() -> None:
    document, laid = epic_with_everything()
    tool = document["tracks"][document["processes"][1]["tracks"][0]]["first"] + 3

    said = laid.span(tool)

    assert said == {
        "id": tool,
        "process": 1,
        "track": document["processes"][1]["tracks"][0],
        "start": 16_000_000,
        "dur": 14_000_000,
        "depth": 2,
        "cat": "tool",
        "name": "Task: look",
        "at": iso(16),
        "args": {"in": "x", "session": "claude:r"},
    }
    for missing in (-1, len(laid.details)):
        with pytest.raises(KeyError):
            laid.span(missing)


def test_the_summary_totals_each_category() -> None:
    document, _ = epic_with_everything()

    summary = document["summary"]
    assert (summary["start"], summary["end"]) == (0, 100_000_000)
    assert (summary["processes"], summary["tracks"]) == (5, len(document["tracks"]))
    assert summary["categories"]["llm"] == {
        "count": 1,
        "time": 4_000_000,
        "in": 70,
        "out": 30,
    }
    assert summary["categories"]["tool"]["count"] == 2
    assert summary["categories"]["process"]["count"] == 3


def test_overlap_that_does_not_nest_spills_into_another_track() -> None:
    one = Session(
        "codex:a",
        "codex",
        "a",
        "main",
        "a",
        actions=[
            Action("x", "tool", T0, T0 + 10),
            Action("y", "tool", T0 + 5, T0 + 15),
        ],
    )

    document = build([one]).document

    (process,) = document["processes"]
    assert len(process["tracks"]) == 2
    names = [text(document, document["tracks"][at]["name"]) for at in process["tracks"]]
    assert names == ["main", "main ~2"]
    assert process["parent"] == -1


def test_a_running_epic_runs_until_the_last_thing_in_it() -> None:
    one = Session(
        "claude:r",
        "claude",
        "r",
        "main",
        "r",
        actions=[Action("t", "turn", T0 + 1, T0 + 30)],
    )
    calls = (Called("child", "t", "epic.child_1.jsonl", began=iso(2)),)

    document = build([one], ran=ran(ended=None), calls=calls).document

    assert document["live"] is True
    flows = columns(document, document["processes"][0]["tracks"][0])
    assert [(one["start"], one["dur"]) for one in flows] == [
        (0, 30_000_000),
        (2_000_000, 28_000_000),
    ]


def test_the_layout_says_whether_span_ids_moved() -> None:
    def laid(*spans: tuple[float, float]) -> str:
        actions = [Action("x", "tool", T0 + s, T0 + e) for s, e in spans]
        one = Session("claude:a", "claude", "a", "main", "a", actions=actions)
        return build([one]).document["layout"]

    assert laid((0, 1), (2, 3)) == laid((0, 1), (2, 3))
    # Still going: what it is doing grows, and every id stays where it was.
    assert laid((0, 1), (2, 3)) == laid((0, 1), (2, 9))
    assert laid((0, 1), (2, 3)) != laid((0, 1), (1.5, 1.7), (2, 3))


def test_a_sub_agent_whose_starter_did_nothing_hangs_from_the_epic() -> None:
    orphan = Session(
        "claude:c",
        "claude",
        "c",
        "Explore",
        "c",
        parent="claude:gone",
        actions=[Action("x", "tool", T0 + 1, T0 + 2)],
    )

    document = build([orphan], ran=ran()).document

    assert document["processes"][1]["parent"] == 0
    assert document["spawns"] == {"span": [0], "process": [1]}


def test_a_program_hangs_from_whichever_held_its_parents_pid_then() -> None:
    first = Process(7, 1, "a", (), T0, T0 + 1)
    again = Process(7, 1, "b", (), T0 + 5, T0 + 9)
    child = Process(8, 7, "c", (), T0 + 6, T0 + 7)

    document = build([], profiled=[first, again, child]).document

    assert [one["parent"] for one in document["processes"]] == [-1, -1, 1]


def test_nothing_is_an_empty_timeline() -> None:
    document = build([Session("k", "claude", "k", "main", "t")]).document

    assert document["processes"] == []
    assert document["tracks"] == []
    assert document["strings"] == [""]
    assert document["summary"]["spans"] == 0


def test_fifty_thousand_spans_are_laid_out_quickly_and_compactly() -> None:
    sessions: list[Session] = []
    for n in range(100):
        actions: list[Action] = []
        base = T0 + n * 600
        for turn in range(50):
            at = base + turn * 10
            actions.append(Action("turn", "turn", at, at + 9, {"prompt": "p" * 200}))
            actions.extend(
                Action(
                    f"tool {step}",
                    "llm" if step % 2 else "tool",
                    at + step,
                    at + step + 0.9,
                    {"model": "m", "usage": {"input_tokens": 9, "output_tokens": 3}},
                )
                for step in range(9)
            )
        sessions.append(
            Session(f"claude:{n}", "claude", str(n), "main", str(n), actions=actions)
        )

    began = time.perf_counter()
    laid = build(sessions)
    body = json.dumps(laid.document, separators=(",", ":"))
    took = time.perf_counter() - began

    assert laid.document["summary"]["spans"] == 50_100
    # Generous: it takes a fraction of this, and a busy machine running tests is slow.
    assert took < 5.0
    assert len(body) < 5_000_000
    for track in laid.document["tracks"]:
        spans = track["spans"]
        assert all(len(column) == track["count"] for column in spans.values())
        assert spans["start"] == sorted(spans["start"])
