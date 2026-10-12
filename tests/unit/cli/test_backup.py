"""`hmz backup`: one epic backed up by hand, with the runtime mocked."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

import hmz.runtime
from hmz.cli import main

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
