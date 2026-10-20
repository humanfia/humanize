"""`hmz backup`: one epic backed up by hand, with the runtime mocked."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest import mock

import pytest

import hmz.cli.output
import hmz.runtime
from hmz.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable

EPIC = Path("/epics/w/20261012T000000.000Z-abcdef")


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`hmz.runtime.Hmz`, mocked: one epic here, backed up to `lab` and `home`."""
    held = mock.Mock()
    ran = SimpleNamespace(at=EPIC)
    held.epics.all.return_value = [EPIC]
    held.epics.read.side_effect = {EPIC: ran}.get
    held.backups.push.return_value = ("lab", "home")
    held.verses.plain.side_effect = {
        "https://me:pw@host/epics": "https://***@host/epics"
    }.get
    held.backups.targets.return_value = [
        SimpleNamespace(name="lab", url="https://me:pw@host/epics"),
        SimpleNamespace(name="home", url="/srv/epics"),
    ]
    held.backups.state.side_effect = [
        {},
        {"lab": {"ok": True, "error": ""}, "home": {"ok": False, "error": "rejected"}},
    ]
    monkeypatch.setattr(hmz.runtime, "Hmz", mock.Mock(return_value=held))
    return held


def test_an_epic_is_backed_up_and_each_target_says_how_it_went(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["backup", EPIC.name, "--to", "lab", "--to", "home"]) == 1

    runtime.backups.push.assert_called_once_with(
        runtime.epics.read(EPIC), ["lab", "home"]
    )
    runtime.backups.wait.assert_called_once_with()
    said = capsys.readouterr()
    assert said.out == "lab: backed up to https://***@host/epics\n"
    assert said.err == "home: failed: rejected\n"


def test_no_targets_named_are_the_epics_own(runtime: mock.Mock) -> None:
    runtime.backups.state.side_effect = [
        {},
        {"lab": {"ok": True}, "home": {"ok": True}},
    ]

    assert main(["backup", str(EPIC)]) == 0
    runtime.backups.push.assert_called_once_with(runtime.epics.read(EPIC), None)


def test_an_outcome_the_epic_does_not_say_anew_is_a_failure(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    was = {"lab": {"ok": True, "at": "then"}, "home": {"ok": True, "at": "then"}}
    runtime.backups.state.side_effect = [was, was]

    assert main(["backup", EPIC.name]) == 1
    assert "the epic could not be written to" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "why"),
    [
        (["nothing"], "no epic nothing here"),
        ([EPIC.name, "--to", "x"], "no backup target is named x"),
    ],
)
def test_a_line_naming_nothing_to_back_up_is_refused(
    runtime: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    why: str,
) -> None:
    runtime.backups.push.side_effect = ValueError("no backup target is named x")

    with pytest.raises(SystemExit) as stopped:
        main(["backup", *argv])
    assert stopped.value.code == 2
    assert why in capsys.readouterr().err


def test_an_epic_with_no_target_anywhere_is_refused(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.backups.push.return_value = ()

    with pytest.raises(SystemExit):
        main(["backup", EPIC.name])
    assert "no backup target" in capsys.readouterr().err


def _stored(machine: str, epic: str, how: str = "done") -> SimpleNamespace:
    return SimpleNamespace(
        key=f"{machine}/-w/{epic}",
        machine=machine,
        workspace="/w",
        epic=epic,
        task="fix\nit",
        how=how,
    )


def test_each_target_lists_the_epics_it_holds(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.backups.listed.side_effect = {
        "lab": [_stored("a", "e1"), _stored("b", "e2", "")],
        "home": [],
    }.get

    assert main(["backup", "--list"]) == 0

    assert capsys.readouterr().out == (
        "lab: 2 epics\n"
        "  a  /w  e1  done  fix it\n"
        "  b  /w  e2  unfinished  fix it\n"
        "home: 0 epics\n"
    )


def test_a_target_that_cannot_be_reached_is_said_and_the_rest_listed(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    def listed(name: str) -> list[SimpleNamespace]:
        if name == "lab":
            raise OSError("unreachable")
        return []

    runtime.backups.listed.side_effect = listed

    assert main(["backup", "--list"]) == 1
    said = capsys.readouterr()
    assert said.err == "lab: failed: unreachable\n"
    assert said.out == "home: 0 epics\n"


def test_an_epic_is_pulled_by_name_and_its_path_printed(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.backups.listed.return_value = [_stored("a", "e1")]
    runtime.backups.pulled.return_value = Path("/home/epics/-w/e1")

    assert main(["backup", "--pull", "e1", "--to", "home"]) == 0

    runtime.backups.pulled.assert_called_once_with("home", "a/-w/e1")
    assert capsys.readouterr().out == "/home/epics/-w/e1\n"


def test_an_epic_already_here_is_not_pulled(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.backups.listed.return_value = [_stored("a", "e1")]
    runtime.backups.pulled.side_effect = ValueError("e1 is already here, at /x")

    assert main(["backup", "--pull", "a/-w/e1", "--to", "lab"]) == 1
    assert "already here" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "why"),
    [
        (["--pull", "e9"], "no target holds an epic e9"),
        (["--pull", ""], "no target holds an epic"),
        (["--pull", "e1"], "from more than one machine"),
        (["--list", "--to", "x"], "no backup target is named x"),
        (["--list", EPIC.name], "goes without --list"),
        ([], "required: epic"),
    ],
)
def test_a_line_naming_nothing_to_list_or_pull_is_refused(
    runtime: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    why: str,
) -> None:
    runtime.backups.listed.return_value = [_stored("a", "e1"), _stored("b", "e1")]

    with pytest.raises(SystemExit) as stopped:
        main(["backup", *argv])
    assert stopped.value.code == 2
    assert why in capsys.readouterr().err


def test_a_pull_past_a_target_that_did_not_answer_says_both(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    def listed(name: str) -> list[SimpleNamespace]:
        if name == "lab":
            raise OSError("unreachable")
        return [_stored("a", "e1")]

    runtime.backups.listed.side_effect = listed
    runtime.backups.pulled.return_value = Path("/here/e1")

    assert main(["backup", "--pull", "e1"]) == 0
    assert capsys.readouterr().out == "/here/e1\n"
    assert main(["backup", "--pull", "e9"]) == 1
    assert capsys.readouterr().err == (
        "lab: failed: unreachable\nhmz backup: no target that answered holds e9\n"
    )


class _Spinner:
    """`Out.spins`, as what it would say now, rather than drawn."""

    def __init__(self) -> None:
        self.says = ""
        self.seen: list[str] = []

    def spins(self, says: Callable[[], str] | None) -> None:
        self.says = says() if says else ""

    def saw(self, *_: object) -> list[SimpleNamespace]:
        self.seen.append(self.says)
        return [_stored("a", "e1")]


def test_a_spinner_says_what_git_is_doing_until_it_answers(
    runtime: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown = _Spinner()
    # Set on the class, a bound method is not bound again: `out.spins(f)` is `shown.spins(f)`.
    monkeypatch.setattr(hmz.cli.output.Out, "spins", shown.spins)
    runtime.backups.wait.side_effect = shown.saw
    runtime.backups.listed.side_effect = shown.saw
    runtime.backups.pulled.side_effect = shown.saw

    main(["backup", EPIC.name])
    main(["backup", "--list", "--to", "lab"])
    main(["backup", "--pull", "e1", "--to", "home"])

    assert shown.seen == [
        "backing up to lab, home",
        "asking lab what it holds",
        "asking home what it holds",
        "downloading a/-w/e1 from home",
    ]
    assert shown.says == ""
