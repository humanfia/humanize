"""The runs of one workspace, and what is gathered out of one of them."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime import Epics, exporting
from hmz.runtime.epic import RESUME, SESSIONS, TRACES, Epic
from hmz.runtime.tracing import collector, profile

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
        "kept": [run / SESSIONS],
    }


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

    Epics().trace(kept=None, profile="p", agents={"a": ["x"]})

    ((args, kwargs),) = collected.calls
    assert args == (None,)
    assert kwargs["kept"] == [run / SESSIONS]
    assert kwargs["profile"] == "p"
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


def test_a_journal_nobody_wrote_cannot_be_picked_up(workspace: Path) -> None:
    run = _run(workspace)
    (run / RESUME).write_text("not json\n")

    assert Epics(workspace).picks_up(run) is False
    assert Epics(workspace).resumed("ralph") is None
