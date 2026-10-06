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
        "ralph_loop",
        "-a",
        f"agent={AGENT}",
        "-p",
        "budget.duration=2s",
        *more,
        "work",
    )
    assert ran.returncode == 0, ran.stderr


def test_resume_carries_on_counting_the_rounds_of_the_newest_run(project: Path) -> None:
    epics = Hmz(project).epics
    _loop()
    (first,) = epics.all()
    assert epics.picks_up(first)
    assert epics.state(first) == {"rounds": 1}
    assert epics.resumed("ralph_loop") == first

    _loop("--resume")

    second = epics.all()[-1]
    assert second != first
    ran = epics.read(second)
    assert ran is not None
    assert ran.picked_up == first.name
    assert epics.state(second) == {"rounds": 2}


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
    assert landed == out / f"{epic.name}.epic.tar.gz"
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
