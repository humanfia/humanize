"""What a run leaves behind -- its epic -- picked up by `hmz exec --resume` and exported.

Each run is a real `python -m hmz exec` driving the stand-in `claude`; what it wrote down is
read back through `hmz.sdk.Hmz.epics`, which is how every tool outside reads a run.
"""

from __future__ import annotations

import json
import tarfile
from typing import TYPE_CHECKING

import pytest

from hmz.cli import main
from hmz.runtime.epic import logs
from hmz.sdk import Hmz
from tests.integration.doubles_core import AGENT, hmz_exec, install, started

if TYPE_CHECKING:
    from pathlib import Path

#: Not a key anybody has: a value an account holds, long enough to be struck as one.
SECRET = "sk-ant-standin-0123456789abcdef"


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return install(tmp_path, monkeypatch)


def _loop(*more: str) -> None:
    ran = hmz_exec(
        "-f",
        "flame_chase",
        "-a",
        f"first_chaser={AGENT}",
        "-a",
        f"second_chaser={AGENT}",
        "-p",
        "budget.duration=2s",
        *more,
        "work",
    )
    assert ran.returncode == 0, ran.stderr


def test_resume_carries_on_from_what_the_newest_run_kept(project: Path) -> None:
    epics = Hmz(project).epics
    _loop()
    (first,) = epics.all()
    assert epics.picks_up(first)
    assert set(epics.state(first)) == {"turn"}
    assert epics.resumed("flame_chase") == first

    _loop("--resume")

    second = epics.all()[-1]
    assert second != first
    ran = epics.read(second)
    assert ran is not None
    assert ran.picked_up == first.name
    assert set(epics.state(second)) == {"turn"}


def test_resume_of_a_flow_that_cannot_be_picked_up_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(
            [
                "exec",
                "-f",
                "goal",
                "-a",
                f"worker={AGENT}",
                "-p",
                "budget.cost=1",
                "--resume",
                "win",
            ]
        )

    assert stopped.value.code == 2
    assert "resum" in capsys.readouterr().err
    assert not started(tmp_path)


def test_an_epic_exports_whole_with_an_accounts_values_struck_out(
    tmp_path: Path, project: Path
) -> None:
    hmz = Hmz(project)
    hmz.accounts.write("claude", "work", env={"ANTHROPIC_API_KEY": SECRET})
    ran = hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", f"use {SECRET} please")
    assert ran.returncode == 0, ran.stderr
    (epic,) = hmz.epics.all()
    (session,) = hmz.epics.sessions(epic)

    out = tmp_path / "out"
    out.mkdir()

    landed, manifest = hmz.epics.bundled(epic, output=out)

    # A directory is written into, under the run's own name.
    assert landed == out / f"{epic.name}.hmzepic"
    with tarfile.open(landed) as bundle:
        names = bundle.getnames()
        said = b"".join(
            got.read()
            for member in bundle.getmembers()
            if member.isfile() and (got := bundle.extractfile(member)) is not None
        )
    assert f"{epic.name}/manifest.json" in names
    assert f"{epic.name}/epic.jsonl" in names
    # The session's own log goes in under the session it is a log of.
    assert any(
        name.startswith(f"{epic.name}/sessions/{session.name}/") for name in names
    )
    assert SECRET.encode() not in said
    assert b"[redacted]" in said
    assert manifest["run"]["flow"] == "chat"
    assert manifest["run"]["how"] == "done"
    assert [one["runs"] for one in manifest["agents"]] == [f"{AGENT}:auto"]
    assert SECRET not in json.dumps(manifest)
    assert "[redacted]" in manifest["run"]["task"]


def test_an_exported_epic_imports_on_another_machine_and_picks_up_where_it_can(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epics = Hmz(project).epics
    _loop()
    (first,) = epics.all()
    before = epics.read(first)
    landed, _ = epics.bundled(first, output=tmp_path)

    # Another machine: a home of its own, the same workspace.
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "elsewhere"))
    assert epics.all() == []
    back = Hmz().epics.imported(landed)

    assert epics.all() == [back]
    assert back.name == first.name
    assert before is not None
    # The stand-in keeps its sessions in its own home, which is the other machine's: here
    # they are kept in the epic, as a session a turn kept would be.
    assert epics.read(back) == before._replace(
        at=back,
        sessions=tuple(
            one._replace(where=f"sessions/{one.backend}") for one in before.sessions
        ),
    )
    for was, now in zip(before.sessions, epics.sessions(back), strict=True):
        assert set(logs(back, now)) == set(logs(first, was))
        assert logs(back, now)
    assert epics.picks_up(back)
    assert epics.resumed("flame_chase") == back
    with pytest.raises(ValueError, match="already here"):
        epics.imported(landed)

    project.rename(tmp_path / "moved")
    assert "not on this machine" in epics.foreign(back)
    assert not epics.picks_up(back)
