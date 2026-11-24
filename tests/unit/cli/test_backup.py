"""`hmz backup`: an epic uploaded now, the targets and what one holds listed, and one pulled."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

import pytest

from hmz.cli import main, tree
from hmz.sdk import Refused

EPIC = "20261012T000000.000Z-abcdef"


@dataclass(frozen=True)
class Held:
    """One epic or chat a target holds, as the backups family answers it."""

    key: str
    epic: str
    task: str = "fix the parser"
    how: str = "done"
    flow: str = "ralph"
    chat: bool = False
    here: bool = False


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The client the command reaches."""
    held = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=held))
    return held


def _went(ok: bool, error: str = "") -> dict[str, object]:
    return {"at": "2026-10-12T09:15:00Z", "ok": ok, "error": error, "why": "manual"}


def test_an_epic_is_uploaded_and_each_target_says_it_took_it(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.runs.backup.return_value = {"lab": _went(ok=True), "home": _went(ok=True)}

    assert main(["backup", "run", EPIC, "--to", "lab", "--to", "home"]) == 0

    assert capsys.readouterr().out == (
        "lab: uploaded 2026-10-12T09:15:00Z\nhome: uploaded 2026-10-12T09:15:00Z\n"
    )
    client.runs.backup.assert_called_once_with(EPIC, to=["lab", "home"], wait=600)


def test_a_target_that_did_not_take_it_is_the_commands_error(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.runs.backup.return_value = {
        "lab": _went(ok=True),
        "home": _went(ok=False, error="rejected"),
    }

    assert main(["backup", "run", EPIC]) == 1
    said = capsys.readouterr()
    assert said.out == "lab: uploaded 2026-10-12T09:15:00Z\n"
    assert said.err == ("hmz backup run: home: failed, rejected 2026-10-12T09:15:00Z\n")
    client.runs.backup.assert_called_once_with(EPIC, to=None, wait=600)

    assert main(["backup", "run", EPIC, "--json"]) == 1
    said = capsys.readouterr()
    assert json.loads(said.out) == {
        "error": {
            "code": 0,
            "message": "home: failed, rejected 2026-10-12T09:15:00Z",
        }
    }
    assert said.err == ""


def test_the_document_says_what_was_queued_and_how_each_went(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.runs.backup.return_value = {"lab": _went(ok=True)}

    assert main(["backup", "run", EPIC, "--timeout", "5", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "queued": ["lab"],
        "backed": {"lab": _went(ok=True)},
    }
    client.runs.backup.assert_called_once_with(EPIC, to=None, wait=5)


def test_an_upload_not_waited_for_says_only_where_it_is_going(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.runs.backup.return_value = {"lab": {}, "home": {}}

    assert main(["backup", "run", EPIC, "--no-wait"]) == 0
    assert capsys.readouterr().out == "Uploading to lab, home\n"
    client.runs.backup.assert_called_once_with(EPIC, to=None, wait=0)

    assert main(["backup", "run", EPIC, "--no-wait", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "queued": ["lab", "home"],
        "backed": {},
    }
    # No time to wait is not waiting.
    assert main(["backup", "run", EPIC, "--timeout", "0"]) == 0
    assert capsys.readouterr().out == "Uploading to lab, home\n"
    client.runs.backup.assert_called_with(EPIC, to=None, wait=0)


def test_an_upload_not_done_in_time_is_left_to_the_daemon(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.runs.backup.side_effect = TimeoutError("no backup of it in 2s")

    assert main(["backup", "run", EPIC, "--timeout", "2"]) == 3

    assert capsys.readouterr().err == (
        f"hmz backup run: The backup of {EPIC} did not finish within 2 seconds, "
        "and carries on in the daemon.\n"
    )


def test_a_refusal_is_said_in_the_daemons_words(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.runs.backup.side_effect = Refused(
        "There is no backup target: add one in Settings.", code=409
    )

    assert main(["backup", "run", EPIC]) == 1

    assert capsys.readouterr().err == (
        "hmz backup run: There is no backup target: add one in Settings.\n"
    )


def test_the_targets_are_listed_where_none_is_named(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.backups.targets.return_value = [
        SimpleNamespace(
            name="lab",
            url="https://***@host/e.git",
            branch="main",
            policies=("session", "end"),
            every=30,
            default=False,
        ),
        SimpleNamespace(
            name="home",
            url="/srv/e",
            branch="epics",
            policies=(),
            every=5,
            default=True,
        ),
    ]

    assert main(["backup", "list"]) == 0
    assert capsys.readouterr().out == (
        "lab   https://***@host/e.git  main   session,end\n"
        "home  /srv/e                  epics               default\n"
    )

    assert main(["backup", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "targets": [
            {
                "name": "lab",
                "url": "https://***@host/e.git",
                "branch": "main",
                "policies": ["session", "end"],
                "every": 30,
            },
            {
                "name": "home",
                "url": "/srv/e",
                "branch": "epics",
                "policies": [],
                "every": 5,
            },
        ],
        "defaults": ["home"],
    }
    client.backups.epics.assert_not_called()


def test_no_target_at_all_is_said_beside_an_empty_listing(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.backups.targets.return_value = []

    assert main(["backup", "list"]) == 0
    said = capsys.readouterr()
    assert (said.out, said.err) == ("", "No backup target.\n")

    assert main(["backup", "list", "--json"]) == 0
    said = capsys.readouterr()
    assert (json.loads(said.out), said.err) == ({"targets": [], "defaults": []}, "")


def test_what_a_target_holds_is_listed_a_line_each(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    held = [
        Held(
            "laptop/project/e2", "e2", task="fix   the\nparser " + "x" * 80, here=True
        ),
        Held("ci/project/e1", "e1", how=""),
        Held("laptop/project/c1", "c1", task="hello", flow="", chat=True),
    ]
    client.backups.epics.return_value = held

    assert main(["backup", "list", "--target", "lab"]) == 0
    assert capsys.readouterr().out == (
        f"laptop/project/e2  done        ralph  here  fix the parser {'x' * 44}…\n"
        "ci/project/e1      unfinished  ralph        fix the parser\n"
        "laptop/project/c1  done        chat         hello\n"
    )
    client.backups.epics.assert_called_once_with("lab")

    assert main(["backup", "list", "--target", "lab", "--json"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert [one["key"] for one in said["epics"]] == [one.key for one in held]
    assert said["epics"][2] == {
        "key": "laptop/project/c1",
        "epic": "c1",
        "task": "hello",
        "how": "done",
        "flow": "",
        "chat": True,
        "here": False,
    }


def test_one_is_pulled_by_its_key(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.backups.pull.return_value = "e1"

    assert main(["backup", "pull", "ci/project/e1", "--target", "lab"]) == 0
    assert capsys.readouterr().out == "e1\n"
    client.backups.pull.assert_called_once_with("lab", "ci/project/e1")
    client.backups.epics.assert_not_called()

    assert main(["backup", "pull", "ci/project/e1", "--target", "lab", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"name": "e1"}


def test_one_is_pulled_by_its_name_where_the_target_holds_one_of_it(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.backups.epics.return_value = [
        Held("laptop/project/e2", "e2"),
        Held("ci/project/e1", "e1"),
        Held("laptop/project/e1", "e1"),
    ]
    client.backups.pull.return_value = "e2"

    assert main(["backup", "pull", "e2", "--target", "lab"]) == 0
    client.backups.pull.assert_called_once_with("lab", "laptop/project/e2")
    capsys.readouterr()

    assert main(["backup", "pull", "e1", "--target", "lab"]) == 1
    assert capsys.readouterr().err == (
        "hmz backup pull: lab holds e1 from more than one machine, name one of: "
        "ci/project/e1, laptop/project/e1.\n"
    )
    assert main(["backup", "pull", "e9", "--target", "lab"]) == 1
    assert capsys.readouterr().err == "hmz backup pull: lab holds no epic or chat e9.\n"
    client.backups.pull.assert_called_once()


def test_a_pull_names_the_target_it_is_from(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(["backup", "pull", "e1"])

    assert exit_.value.code == 2
    assert "--target" in capsys.readouterr().err
    client.backups.pull.assert_not_called()


def test_the_old_spellings_are_lines_that_cannot_be_read(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    for line in (["backup", EPIC], ["backup", "--list"], ["backup", "--pull", EPIC]):
        with pytest.raises(SystemExit) as exit_:
            main(line)
        assert exit_.value.code == 2
        assert "hmz backup --help" in capsys.readouterr().err
    assert client.mock_calls == []
