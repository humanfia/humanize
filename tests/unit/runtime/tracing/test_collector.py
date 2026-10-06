from __future__ import annotations

import json
import os
import types
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing import collect, collector
from hmz.runtime.tracing.profile import PROFILE, Process
from tests.unit.runtime.tracing.logs import jsonl

if TYPE_CHECKING:
    from pathlib import Path

T0 = 1_767_225_600
WORKSPACE = "/work/repo"


class Backend:
    """What `hmz.coganchor.backends` says about one CLI: its name and its home."""

    def __init__(self, name: str, home: Path) -> None:
        self.name = name
        self.home = home

    def directory(self) -> Path:
        return self.home


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A litellm home, and a backend nobody reads, in place of every real CLI's."""
    root = tmp_path / "homes"
    profiles = (
        Backend("unreadable", root / "unreadable"),
        Backend("litellm", root / "litellm"),
        Backend("claude", root / "absent"),
    )
    (root / "unreadable").mkdir(parents=True)
    monkeypatch.setattr(collector, "backends", types.SimpleNamespace(PROFILES=profiles))
    return root


def conversation(
    home: Path, ident: str, *, at: float = 1, cwd: str = WORKSPACE, **header: Any
) -> None:
    jsonl(
        home / "sessions" / f"{ident}.jsonl",
        [
            {"type": "session", "id": ident, "cwd": cwd, "model": "gpt-x", **header},
            {
                "type": "message",
                "timestamp": T0 + at,
                "message": {"role": "user", "content": f"hi from {ident}"},
            },
        ],
    )


def sessions_of(document: dict[str, Any]) -> set[str]:
    return {
        e["args"]["session"]
        for e in document["traceEvents"]
        if e["ph"] == "X" and e["cat"] == "session"
    }


def processes(document: dict[str, Any]) -> list[str]:
    return [
        e["args"]["name"]
        for e in document["traceEvents"]
        if e["name"] == "process_name"
    ]


def test_reads_every_home_and_every_kept_place(homes: Path, tmp_path: Path) -> None:
    conversation(homes / "litellm", "own")
    kept = tmp_path / "epic" / "sessions"
    conversation(kept / "litellm", "kept")
    document = collect(WORKSPACE, kept=[kept, tmp_path / "nothing-here"])
    assert sessions_of(document) == {"litellm:own", "litellm:kept"}
    assert document["otherData"]["workspace"] == WORKSPACE
    assert document["otherData"]["backends"] == "litellm"


def test_workspace_defaults_to_where_it_is_run(
    homes: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    conversation(homes / "litellm", "local", cwd=os.path.abspath(here))  # noqa: PTH100
    conversation(homes / "litellm", "far")
    document = collect()
    assert sessions_of(document) == {"litellm:local"}
    assert document["otherData"]["workspace"] == str(here)


@pytest.mark.parametrize("named", ["a,b", ["a", " b "], ("a,b",)])
def test_named_sessions_are_found_wherever_they_were_run(
    homes: Path, named: Any
) -> None:
    conversation(homes / "litellm", "a")
    conversation(homes / "litellm", "b", cwd="/else")
    conversation(homes / "litellm", "c")
    document = collect(sessions=named)
    assert sessions_of(document) == {"litellm:a", "litellm:b"}
    assert document["otherData"]["selected"] == "a, b"
    assert "workspace" not in document["otherData"]


def test_a_workspace_and_sessions_narrow_together(homes: Path) -> None:
    conversation(homes / "litellm", "a")
    conversation(homes / "litellm", "b", cwd="/else")
    assert sessions_of(collect(WORKSPACE, sessions="a,b")) == {"litellm:a"}


def test_no_sessions_named_is_an_empty_trace(homes: Path) -> None:
    conversation(homes / "litellm", "a")
    document = collect(WORKSPACE, sessions=[])
    assert document["traceEvents"] == []


@pytest.mark.parametrize("named", ["a,,b", "", [" "]])
def test_an_empty_session_id_is_refused(homes: Path, named: Any) -> None:
    with pytest.raises(ValueError, match="session id cannot be empty"):
        collect(sessions=named)


@pytest.mark.parametrize(
    ("start", "end"), [("not a time at all", None), (None, "gibberish xyz")]
)
def test_an_unreadable_time_is_refused(
    homes: Path, start: str | None, end: str | None
) -> None:
    with pytest.raises(ValueError, match="cannot parse time"):
        collect(WORKSPACE, start=start, end=end)


def test_start_and_end_narrow_the_window(homes: Path) -> None:
    conversation(homes / "litellm", "early", at=1)
    conversation(homes / "litellm", "late", at=100)
    document = collect(
        WORKSPACE, start="2026-01-01T00:00:50+00:00", end="2026-01-01T00:10:00Z"
    )
    events = [e for e in document["traceEvents"] if e["ph"] == "X"]
    assert sessions_of(document) == {"litellm:late"}
    assert all(e["args"]["session"] == "litellm:late" for e in events)


def test_agents_are_named_after_the_root_session(homes: Path) -> None:
    conversation(homes / "litellm", "root")
    conversation(homes / "litellm", "fork", parent="root", model="other-model")
    conversation(homes / "litellm", "alone", model=None)
    conversation(homes / "litellm", "claimed")
    document = collect(WORKSPACE, agents={"reviewer": ["claimed"]})
    assert sorted(processes(document)) == [
        "litellm · 1 session",
        "litellm · gpt-x · 2 sessions",
        "reviewer · gpt-x · 1 session",
    ]


def test_output_is_written_where_asked(homes: Path, tmp_path: Path) -> None:
    conversation(homes / "litellm", "a")
    output = tmp_path / "deep" / "er" / "trace.json"
    document = collect(WORKSPACE, output=output)
    assert json.loads(output.read_text(encoding="utf-8")) == document


def test_a_profile_is_drawn_inside_the_window(homes: Path, tmp_path: Path) -> None:
    conversation(homes / "litellm", "a")
    inside = Process(10, 1, "pytest", (), T0 + 1, T0 + 2)
    outside = Process(11, 1, "old", (), T0 - 100, T0 - 90)
    start = "2026-01-01T00:00:00Z"
    document = collect(WORKSPACE, profile=[inside, outside], start=start)
    assert "pytest · 10" in processes(document)
    assert "old · 11" not in processes(document)
    assert document["otherData"]["programs"] == "1"

    jsonl(
        tmp_path / "epic" / PROFILE,
        [{"pid": 12, "ppid": 1, "name": "make", "began": T0 + 1, "ended": T0 + 3}],
    )
    by_path = collect(WORKSPACE, profile=tmp_path / "epic")
    assert "make · 12" in processes(by_path)
    assert "programs" not in collect(WORKSPACE)["otherData"]
