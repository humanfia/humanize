"""The runs of one workspace, and what is gathered out of one of them."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime import Epics, exporting
from hmz.runtime.epic import RESUME, SESSIONS, TRACES, Epic
from hmz.runtime.tracing import collector, profile, timeline

if TYPE_CHECKING:
    from tests.unit.runtime.doubles_u12 import Stands


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    at = tmp_path / "project"
    at.mkdir()
    return at


def _run(workspace: Path, flow: str = "ralph", *, resumable: bool = False) -> Path:
    with Epic(flow, "t", workspace, ref=f"official/{flow}", resumable=resumable) as one:
        one.session("builder", "claude", "", "s1")
        one.session("builder", "claude", "", "s2")
        one.session("reviewer", "codex", "", "s3")
        if resumable:
            one.resume.write_text(
                "\n".join(
                    json.dumps(said)
                    for said in (
                        {"t": "call", "id": 1, "parent": 0, "ref": f"official/{flow}"},
                        {"t": "set", "id": 1, "key": "round", "value": 4},
                    )
                )
                + "\n"
            )
    return one.path


def test_the_runs_of_a_workspace_are_read_back(workspace: Path) -> None:
    epics = Epics(workspace)
    assert epics.all() == []

    first = _run(workspace)
    second = _run(workspace, resumable=True)

    assert epics.under() == first.parent
    # Oldest first, by name: two made in one millisecond are told apart by name alone.
    assert epics.all() == sorted([first, second])
    ran = epics.read(second)
    assert ran is not None
    assert ran.flow == "ralph"
    assert [one.ident for one in epics.sessions(first)] == ["s1", "s2", "s3"]
    assert epics.opened(first) == {"builder": ["s1", "s2"], "reviewer": ["s3"]}
    assert epics.picks_up(first) is False
    assert epics.picks_up(second) is True
    assert epics.resumed("ralph") == second
    assert epics.resumed("official/ralph") == second
    assert epics.state(second) == {"round": 4}
    assert epics.state(second, "official/other") == {}


def test_a_run_reads_as_going_only_while_it_is_held(workspace: Path) -> None:
    epics = Epics(workspace)
    with Epic("ralph", "t", workspace) as held:
        assert epics.going(held.path) is True

    assert epics.going(held.path) is False


def test_every_run_on_this_machine_is_read_back_oldest_first(
    workspace: Path, tmp_path: Path
) -> None:
    assert Epics().every() == []
    first = _run(workspace)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    second = _run(elsewhere)

    assert Epics(workspace).every() == [first, second]
    assert Epics(workspace).all() == [first]


def test_a_workspace_nobody_named_is_this_directory(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace)
    _run(workspace)

    assert Epics().all() == Epics(str(workspace)).all()
    assert Epics().under() == Epics(workspace).under()


def test_a_trace_of_a_run_is_of_that_runs_sessions_and_kept_with_it(
    workspace: Path, stand: Stands
) -> None:
    collected = stand(collector, "collect", {"traceEvents": []})
    run = _run(workspace)

    where, document = Epics(workspace).traced(run, start="yesterday", end="now")

    assert document == {"traceEvents": []}
    assert where.parent == run / TRACES
    assert where.name.endswith(".trace.json")
    assert where.parent.is_dir()
    ((args, kwargs),) = collected.calls
    # No workspace at all: the ids alone are this run's, wherever they were logged.
    assert args == (None,)
    assert kwargs == {
        "sessions": ["s1", "s2", "s3"],
        "agents": {"builder": ["s1", "s2"], "reviewer": ["s3"]},
        "output": where,
        "start": "yesterday",
        "end": "now",
        "profile": run / profile.PROFILE,
        "flow_profile": run / profile.FLOW_PROFILE,
        "kept": [run / SESSIONS],
    }


def test_a_runs_transcripts_are_each_sessions_actions_in_the_order_they_happened(
    workspace: Path, stand: Stands
) -> None:
    document: dict[str, Any] = {
        "traceEvents": [
            {"ph": "M", "name": "process_name", "pid": 7, "args": {"name": "builder"}},
            {"ph": "X", "cat": "session", "pid": 7, "ts": 0, "dur": 9e6},
            {
                "ph": "X",
                "cat": "tool",
                "name": "Bash",
                "pid": 7,
                "ts": 3e6,
                "dur": 1e6,
                "args": {"session": "claude:s1", "at": "t3", "command": "ls"},
            },
            {
                "ph": "X",
                "cat": "turn",
                "name": "turn 1",
                "pid": 7,
                "ts": 1e6,
                "dur": 5e6,
                "args": {"session": "claude:s1"},
            },
            {
                "ph": "X",
                "cat": "turn",
                "name": "turn 1",
                "pid": 8,
                "ts": 2e6,
                "dur": 1e6,
                "args": {"session": "codex:s2"},
            },
            {"ph": "X", "cat": "turn", "pid": 7, "ts": 0, "dur": 1, "args": {}},
        ]
    }

    stand(collector, "collect", document)

    sessions = Epics(workspace).transcripts(_run(workspace))

    assert [(one["key"], one["agent"]) for one in sessions] == [
        ("claude:s1", "builder"),
        ("codex:s2", ""),
    ]
    first = sessions[0]["actions"]
    assert [(one["category"], one["start"], one["seconds"]) for one in first] == [
        ("turn", 1.0, 5.0),
        ("tool", 3.0, 1.0),
    ]
    assert first[1]["at"] == "t3"
    assert first[1]["args"] == {"command": "ls"}


def test_a_timeline_of_a_run_is_laid_out_of_what_its_trace_is_gathered_from(
    workspace: Path, stand: Stands
) -> None:
    gathered = stand(collector, "gather", ["session"])
    laid = stand(timeline, "build", "laid out")
    run = _run(workspace)

    said: Any = Epics(workspace).timeline(run)

    assert said == "laid out"
    ((args, kwargs),) = gathered.calls
    assert args == (None,)
    assert kwargs == {
        "sessions": ["s1", "s2", "s3"],
        "agents": {"builder": ["s1", "s2"], "reviewer": ["s3"]},
        "kept": [run / SESSIONS],
    }
    ((args, kwargs),) = laid.calls
    assert args == (["session"],)
    assert kwargs["ran"] == Epics(workspace).read(run)
    assert kwargs["calls"] == ()
    assert kwargs["profiled"] == []
    assert kwargs["sampled"] == []
    # Written nowhere: a timeline is drawn and thrown away.
    assert not (run / TRACES).exists()


def test_a_trace_goes_where_it_is_told(
    workspace: Path, tmp_path: Path, stand: Stands
) -> None:
    collected = stand(collector, "collect", {})
    with Epic("chat", "t", workspace) as one:
        pass

    where, _ = Epics(workspace).traced(one.path, output=tmp_path / "out" / "t.json")

    assert where == tmp_path / "out" / "t.json"
    assert where.parent.is_dir()
    ((_, kwargs),) = collected.calls
    assert kwargs["sessions"] == []
    assert kwargs["agents"] is None


def test_sessions_another_run_kept_are_read_from_where_they_were_kept(
    workspace: Path, stand: Stands
) -> None:
    collected = stand(collector, "collect", {})
    home = Path(os.environ["HUMANIZE_HOME"])
    elsewhere = home / "epics" / "other" / "run" / SESSIONS / "claude"
    with Epic("chat", "t", workspace) as one:
        one.session("builder", "claude", "", "s1", where=elsewhere)
        one.session("builder", "codex", "", "s2", where=Path("/somewhere/codex"))

    Epics(workspace).traced(one.path)

    ((_, kwargs),) = collected.calls
    assert kwargs["kept"] == sorted([one.path / SESSIONS, elsewhere.parent])


def test_a_trace_of_a_workspace_reads_every_run_of_it(
    workspace: Path, stand: Stands
) -> None:
    collected = stand(collector, "collect", {})
    first, second = _run(workspace), _run(workspace)
    for one in (first, second):
        (one / SESSIONS).mkdir()

    Epics(workspace).trace(sessions="s1")

    ((args, kwargs),) = collected.calls
    assert args == (workspace,)
    assert kwargs["sessions"] == "s1"
    assert kwargs["kept"] == sorted([first / SESSIONS, second / SESSIONS])


def test_a_trace_of_no_workspace_reads_every_run_there_is(
    workspace: Path, stand: Stands
) -> None:
    collected = stand(collector, "collect", {})
    run = _run(workspace)
    (run / SESSIONS).mkdir()

    Epics().trace(kept=None, profile="p", flow_profile="f", agents={"a": ["x"]})

    ((args, kwargs),) = collected.calls
    assert args == (None,)
    assert kwargs["kept"] == [run / SESSIONS]
    assert kwargs["profile"] == "p"
    assert kwargs["flow_profile"] == "f"
    assert kwargs["agents"] == {"a": ["x"]}


def test_where_sessions_are_kept_can_be_said(workspace: Path, stand: Stands) -> None:
    collected = stand(collector, "collect", {})

    Epics(workspace).trace(kept=["/x"])

    assert collected.calls[0][1]["kept"] == ["/x"]


def test_a_run_is_bundled_by_the_exporter(workspace: Path, stand: Stands) -> None:
    bundled = stand(exporting, "bundle", ("where", {"m": 1}))
    run = _run(workspace)

    said: Any = Epics(workspace).bundled(run, output="out", transcript="screen")

    assert said == ("where", {"m": 1})
    assert bundled.calls == [((run, "out"), {"transcript": "screen"})]


def test_a_bundle_is_imported_by_the_exporter(workspace: Path, stand: Stands) -> None:
    unbundled = stand(exporting, "unbundle", Path("where"))

    assert Epics(workspace).imported("x.hmzepic") == Path("where")
    assert unbundled.calls == [(("x.hmzepic",), {})]


def test_a_run_imported_from_a_workspace_not_here_is_foreign(workspace: Path) -> None:
    run = _run(workspace, resumable=True)
    (run / RESUME).write_text('{"t": "call", "id": 1}\n')
    with (run / "epic.jsonl").open("a") as stream:
        stream.write('{"event": "imported", "from": "x.hmzepic"}\n')
    workspace.rename(workspace.with_name("gone"))

    assert "not on this machine" in Epics(workspace).foreign(run)
    assert Epics(workspace).picks_up(run) is False


def test_a_journal_nobody_wrote_cannot_be_picked_up(workspace: Path) -> None:
    run = _run(workspace)
    (run / RESUME).write_text("not json\n")

    assert Epics(workspace).picks_up(run) is False
    assert Epics(workspace).resumed("ralph") is None


def test_a_run_went_running_while_it_is_held_and_unfinished_after(
    workspace: Path,
) -> None:
    epics = Epics(workspace)
    with Epic("ralph", "t", workspace) as held:
        ran = epics.read(held.path)
        assert ran is not None
        assert epics.ending(ran) == "running"

    assert epics.ending(ran) == "unfinished"
    after = epics.read(held.path)
    assert after is not None
    assert epics.ending(after) == "done"
