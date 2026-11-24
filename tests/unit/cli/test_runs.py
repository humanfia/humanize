"""`hmz runs`: the epics written down listed, read back, exported, imported and totalled."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from hmz.cli import main, tree
from hmz.cli.commands.runs import fields, folder, local
from hmz.sdk import Refused


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The runs family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    return client.runs


def _row(name: str, **more: Any) -> dict[str, Any]:
    return {
        "name": name,
        "how": "done",
        "flow": "ralph",
        "began": "2026-10-12T09:15:00Z",
        "task": "fix the parser",
    } | more


def _listing(*rows: dict[str, Any], total: int, offset: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        runs=list(rows),
        total=total,
        offset=offset,
        limit=50,
        counts={"done": total},
        flows=["ralph"],
    )


def test_epics_are_listed_in_columns_by_what_the_line_filters(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runs.list.return_value = _listing(_row("e2"), _row("e1", how="failed"), total=2)

    line = "runs list --workspace /w --status failed --flow ralph -q parser --offset 0"
    assert main(list(line.split())) == 0

    said = capsys.readouterr()
    assert said.out == (
        "e2  done    ralph  2026-10-12T09:15:00Z  fix the parser\n"
        "e1  failed  ralph  2026-10-12T09:15:00Z  fix the parser\n"
    )
    assert said.err == ""
    runs.list.assert_called_once_with(
        workspace="/w",
        status="failed",
        flow="ralph",
        query="parser",
        offset=0,
        limit=50,
    )


def test_a_listing_says_where_more_epics_match_than_it_listed(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runs.list.return_value = _listing(_row("e2"), total=5, offset=2)

    assert main(["runs", "list", "--limit", "1", "--offset", "2"]) == 0
    assert capsys.readouterr().err == (
        "1 of 5 epics listed; pass `--offset 3` for the next ones.\n"
    )

    assert main(["runs", "list", "--json"]) == 0
    said = capsys.readouterr()
    assert json.loads(said.out) == {
        "runs": [_row("e2")],
        "total": 5,
        "offset": 2,
        "limit": 50,
        "counts": {"done": 5},
        "flows": ["ralph"],
    }
    assert said.err == ""


def test_a_status_that_is_none_is_a_line_that_cannot_be_read(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(["runs", "list", "--status", "lost"])

    assert exit_.value.code == 2
    assert "hmz runs list --help" in capsys.readouterr().err
    runs.list.assert_not_called()


def test_an_epic_is_shown_a_field_a_line_with_its_whole_task_last(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    one = {
        "name": "e1",
        "task": "fix the parser\nand its tests",
        "resumable": True,
        "spent": None,
        "backup": ["lab"],
        "sessions": 2,
    }
    runs.get.return_value = one

    assert main(["runs", "show", "e1"]) == 0
    assert capsys.readouterr().out == (
        "name       e1\n"
        "resumable  yes\n"
        "spent\n"
        'backup     ["lab"]\n'
        "sessions   2\n"
        "task\n"
        "  fix the parser\n"
        "  and its tests\n"
    )
    runs.get.assert_called_once_with("e1")

    assert main(["runs", "show", "e1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == one


def test_an_epic_that_is_not_there_is_refused_in_the_daemons_words(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runs.get.side_effect = Refused("There is no epic e9.", code=404)

    assert main(["runs", "show", "e9"]) == 1
    assert capsys.readouterr().err == "hmz runs show: There is no epic e9.\n"

    assert main(["runs", "show", "e9", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": 404, "message": "There is no epic e9."}
    }


def test_a_trace_is_each_session_and_what_it_did_under_it(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    sessions: list[dict[str, Any]] = [
        {
            "key": "claude:s1",
            "agent": "coder",
            "actions": [
                {
                    "at": "09:15:00",
                    "seconds": 2.5,
                    "category": "turn",
                    "name": "turn 1",
                },
                {"at": "09:15:01", "seconds": 0.25, "category": "tool", "name": "Bash"},
            ],
        },
        {"key": "codex:s2", "agent": "", "actions": []},
    ]
    runs.trace.return_value = sessions

    assert main(["runs", "trace", "e1"]) == 0
    assert capsys.readouterr().out == (
        "claude:s1  coder\n"
        "  09:15:00  2.500  turn  turn 1\n"
        "  09:15:01  0.250  tool  Bash\n"
        "codex:s2\n"
    )

    assert main(["runs", "trace", "e1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"sessions": sessions}


TIMELINE = {
    "version": 1,
    "layout": "L1",
    "epic": "e1",
    "strings": ["", "flow", "ralph", "main", "claude", "coder", "turn", "Bash", "tool"],
    "processes": [
        {"id": 0, "kind": "flow", "name": 2, "label": 0, "start": 0, "end": 3_000_000,
         "tracks": [0]},
        {"id": 1, "kind": "session", "name": 4, "label": 5, "start": 500_000,
         "end": 2_500_000, "tracks": [1]},
    ],
    "tracks": [
        {"process": 0, "name": 3, "first": 0, "count": 1,
         "spans": {"start": [0], "dur": [3_000_000], "cat": [1], "name": [2]}},
        {"process": 1, "name": 3, "first": 1, "count": 2,
         "spans": {"start": [500_000, 750_000], "dur": [2_000_000, 250_000],
                   "cat": [6, 8], "name": [6, 7]}},
    ],
}  # fmt: skip


def test_a_timeline_is_its_processes_and_their_tracks(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runs.timeline.return_value = TIMELINE

    assert main(["runs", "timeline", "e1"]) == 0
    assert capsys.readouterr().out == (
        "0  flow  ralph  0.000  3.000\n"
        "  main  1 span\n"
        "1  session  claude  coder  0.500  2.500\n"
        "  main  2 spans\n"
    )

    assert main(["runs", "timeline", "e1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == TIMELINE


def test_a_timeline_with_its_spans_gives_each_the_id_a_span_is_read_by(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runs.timeline.return_value = TIMELINE

    assert main(["runs", "timeline", "e1", "--spans"]) == 0

    assert capsys.readouterr().out == (
        "0  flow  ralph  0.000  3.000\n"
        "  main  1 span\n"
        "    0  0.000  3.000  flow  ralph\n"
        "1  session  claude  coder  0.500  2.500\n"
        "  main  2 spans\n"
        "    1  0.500  2.000  turn  turn\n"
        "    2  0.750  0.250  tool  Bash\n"
    )


def test_a_span_is_shown_a_field_a_line_with_what_it_carried_last(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    span = {"id": 2, "cat": "tool", "name": "Bash", "args": {"input": "ls"}}
    runs.span.return_value = span

    assert main(["runs", "span", "e1", "2"]) == 0
    assert capsys.readouterr().out == (
        'id    2\ncat   tool\nname  Bash\nargs\n  {\n    "input": "ls"\n  }\n'
    )
    runs.span.assert_called_once_with("e1", 2, None)

    assert main(["runs", "span", "e1", "2", "--layout", "L1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == span
    runs.span.assert_called_with("e1", 2, "L1")


def test_an_export_prints_where_the_file_went(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runs.export.return_value = SimpleNamespace(
        path=Path("/here/e1.hmzepic"), filename="e1.hmzepic", size=12
    )

    assert main(["runs", "export", "e1"]) == 0
    assert capsys.readouterr().out == "/here/e1.hmzepic\n"
    runs.export.assert_called_once_with("e1", None)

    assert main(["runs", "export", "e1", "-o", "/there", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "path": "/here/e1.hmzepic",
        "filename": "e1.hmzepic",
        "size": 12,
    }
    runs.export.assert_called_with("e1", "/there")


def test_a_file_that_cannot_be_written_is_refused_and_no_daemon_blamed(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runs.export.side_effect = PermissionError(13, "Permission denied", "/there")
    runs.import_.side_effect = FileNotFoundError(2, "No such file", "gone.hmzepic")

    assert main(["runs", "export", "e1", "-o", "/there"]) == 1
    assert capsys.readouterr().err == (
        "hmz runs export: [Errno 13] Permission denied: '/there'\n"
    )
    assert main(["runs", "import", "gone.hmzepic"]) == 1
    assert capsys.readouterr().err == (
        "hmz runs import: [Errno 2] No such file: 'gone.hmzepic'\n"
    )


def test_an_import_sends_the_file_and_says_what_it_became(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    # Not resumable for no reason of this machine's: its flow never was.
    runs.import_.return_value = SimpleNamespace(
        name="e1", workspace="/w", resumable=False, why=""
    )

    assert main(["runs", "import", "e1.hmzepic"]) == 0
    assert capsys.readouterr().out == "Imported e1\n"
    runs.import_.assert_called_once_with("e1.hmzepic")

    assert main(["runs", "import", "e1.hmzepic", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "name": "e1",
        "workspace": "/w",
        "resumable": False,
        "why": "",
    }


def test_an_import_of_a_file_on_the_daemons_machine_sends_only_its_path(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runs.imported.return_value = SimpleNamespace(
        name="e1", workspace="/w", resumable=False, why="it ran on another machine"
    )

    assert main(["runs", "import", "/srv/e1.hmzepic", "--there"]) == 0

    assert capsys.readouterr().out == (
        "Imported e1\nImported · not resumable here: it ran on another machine\n"
    )
    runs.imported.assert_called_once_with(path="/srv/e1.hmzepic")
    runs.import_.assert_not_called()


def test_usage_is_the_flows_then_the_days_something_ran_then_the_total(
    runs: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def spent(n: int, **named: str) -> dict[str, Any]:
        return named | {
            "runs": n,
            "cost": n * 1.5,
            "output_tokens": n * 1000,
            "seconds": n * 60.0,
            "money": f"${n * 1.5:.2f}",
            "tokens": f"{n}.0k",
            "worked": f"{n}m",
        }

    said = {
        "days_back": 2,
        "days": [spent(0, day="2026-10-11"), spent(3, day="2026-10-12")],
        "flows": [spent(2, flow="ralph"), spent(1, flow="chat")],
        "ended": {"done": 3},
        "whole": spent(3),
    }
    runs.usage.return_value = said

    assert main(["runs", "usage", "--days", "2", "--workspace", str(tmp_path)]) == 0
    assert capsys.readouterr().out == (
        "Flow        Epics  Cost   Output tokens  Time working\n"
        "ralph       2      $3.00  2.0k           2m\n"
        "chat        1      $1.50  1.0k           1m\n"
        "Day         Epics  Cost   Output tokens  Time working\n"
        "2026-10-12  3      $4.50  3.0k           3m\n"
        "Total       3      $4.50  3.0k           3m\n"
    )
    runs.usage.assert_called_once_with(days=2, workspace=str(tmp_path))

    assert main(["runs", "usage", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == said
    runs.usage.assert_called_with(days=30, workspace=None)


def test_a_workspace_is_told_as_its_folders_whole_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert folder(None) is None
    assert folder(".") == str(tmp_path)
    assert folder("sub/../project") == str(tmp_path / "project")


def test_fields_are_a_line_each_and_one_is_kept_whole_for_last() -> None:
    document = {"a": 1, "long": "two\nlines", "on": False, "b": [1], "none": None}

    assert fields(document, "long") == [
        "a     1",
        "on    no",
        "b     [1]",
        "none",
        "long",
        "  two",
        "  lines",
    ]
    assert fields({"a": "x  y"}, "missing") == ["a  x y"]


def test_only_a_file_of_this_machine_is_refused_for_what_the_system_said() -> None:
    with pytest.raises(Refused, match="No such file"), local():
        raise FileNotFoundError(2, "No such file", "x")
    with pytest.raises(TimeoutError), local():
        raise TimeoutError
