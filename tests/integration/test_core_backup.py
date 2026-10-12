"""Epics backed up to a git repository on this machine, as their targets' policies say, and back.

Each target here is a bare repository in the test's own directory, reached by the git on this
machine as any remote is; each run is the stand-in `claude` driven by a real `hmz exec`, or by
the runtime in this process where what is waited on has to be held.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from hmz import home
from hmz.cli import main
from hmz.runtime import Hmz, backing
from hmz.runtime.epic import logs, read
from tests.integration.doubles_core import AGENT, hmz_exec, install, write_flow

#: A flow whose one turn is followed by long enough a wait for `interval` to come due.
SLOW = """
import asyncio

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def slow(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    said = await worker.run(task, session=await worker.spawn())
    await asyncio.sleep(1.5)
    return said
"""


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return install(tmp_path, monkeypatch)


@pytest.fixture
def bare(tmp_path: Path) -> Path:
    at = tmp_path / "epics.git"
    subprocess.run(["git", "init", "-q", "--bare", str(at)], check=True)
    return at


def _targets(*targets: dict[str, object], defaults: tuple[str, ...] = ()) -> None:
    home().mkdir(parents=True, exist_ok=True)
    (home() / "settings.yaml").write_text(
        yaml.safe_dump(
            {"backup": {"targets": list(targets), "defaults": list(defaults)}}
        )
    )


def _log(bare: Path) -> list[str]:
    done = subprocess.run(
        ["git", "--git-dir", str(bare), "log", "--format=%s", "main"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.splitlines()


def _show(bare: Path, path: str) -> str:
    return subprocess.run(
        ["git", "--git-dir", str(bare), "show", f"main:{path}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _epic(project: Path) -> Path:
    return Hmz(project).epics.all()[-1]


def test_an_epic_is_backed_up_once_it_ends_with_no_credential_in_it(
    bare: Path, project: Path
) -> None:
    _targets({"name": "t", "url": str(bare), "policies": ["end"]})

    ran = hmz_exec(
        "-f",
        "chat",
        "-a",
        f"assistant={AGENT}",
        "--backup",
        "t",
        "say sk-abcdefghijklmnopqrstuv",
    )

    assert ran.returncode == 0, ran.stderr
    epic = _epic(project)
    assert _log(bare) == [f"Back up epic {epic.name} (end)"]
    under = backing.where(epic)
    journal = _show(bare, f"{under}/epic.jsonl")
    assert '"flow": "chat"' in journal
    assert "sk-abcdefghijklmnopqrstuv" not in journal
    assert "[redacted]" in journal
    assert _show(bare, f"{under}/manifest.json")
    said = read(epic)
    assert said is not None
    assert said.backup == ("t",)
    assert said.backed["t"]["ok"] is True


def test_an_epic_goes_to_the_default_targets_as_its_sessions_close(
    bare: Path, project: Path
) -> None:
    _targets(
        {"name": "t", "url": str(bare), "branch": "epics", "policies": ["session"]},
        defaults=("t",),
    )

    ran = hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", "hello")

    assert ran.returncode == 0, ran.stderr
    done = subprocess.run(
        ["git", "--git-dir", str(bare), "log", "--format=%s", "epics"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.splitlines() == [f"Back up epic {_epic(project).name} (session)"]


def test_no_backup_is_made_where_none_is_asked_for(bare: Path, project: Path) -> None:
    _targets({"name": "t", "url": str(bare), "policies": ["end"]}, defaults=("t",))

    ran = hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", "--backup", "none", "hi")

    assert ran.returncode == 0, ran.stderr
    assert _log(bare) == []
    said = read(_epic(project))
    assert said is not None
    assert said.backup == ()


def test_a_running_epic_is_backed_up_every_so_often(
    bare: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _targets({"name": "t", "url": str(bare), "policies": ["interval"], "every": 1})
    monkeypatch.setattr(backing, "_MINUTE", 0.4)
    flow = write_flow(project.parent, "slow", SLOW)

    Hmz(project).run(
        flow, "hi", agents={"worker": AGENT}, budget={"cost": 1}, backup=["t"]
    ).run()

    assert backing.wait(60)
    assert f"Back up epic {_epic(project).name} (interval)" in _log(bare)


def test_an_epic_is_backed_up_by_hand_and_once_for_what_it_holds(
    bare: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _targets({"name": "t", "url": str(bare)}, defaults=("t",))
    assert hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", "hi").returncode == 0
    epic = _epic(project)
    assert _log(bare) == []

    assert main(["backup", epic.name]) == 0
    assert capsys.readouterr().out == f"t: backed up to {bare}\n"
    assert main(["backup", str(epic), "--to", "t"]) == 0

    # The second holds nothing the first did not: how the first went is the epic's alone.
    assert _log(bare) == [f"Back up epic {epic.name} (manual)"]
    assert '"backed"' not in _show(bare, f"{backing.where(epic)}/epic.jsonl")
    said = read(epic)
    assert said is not None
    assert said.backed["t"]["ok"] is True


def test_an_unreachable_remote_holds_up_nothing_and_says_why(
    tmp_path: Path, project: Path
) -> None:
    _targets({"name": "t", "url": str(tmp_path / "nowhere.git"), "policies": ["end"]})

    began = time.monotonic()
    ran = hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", "--backup", "t", "hi")

    assert ran.returncode == 0, ran.stderr
    assert time.monotonic() - began < 60
    said = read(_epic(project))
    assert said is not None
    assert said.backed["t"]["ok"] is False
    assert said.backed["t"]["error"]


def test_a_backup_never_holds_the_run_up(
    bare: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _targets({"name": "t", "url": str(bare), "policies": ["session", "end"]})
    held = threading.Event()
    real = backing.unpacked

    def slow(epic: Path, into: Path) -> dict[str, Any]:
        # A remote that takes its time, as one across the world does.
        assert held.wait(60)
        return real(epic, into)

    monkeypatch.setattr(backing, "unpacked", slow)

    Hmz(project).run("chat", "hi", agents={"assistant": AGENT}, backup=["t"]).run()

    assert backing.wait(0) is False
    held.set()
    assert backing.wait(60)
    assert _log(bare)


def test_an_epic_backed_up_on_one_machine_is_downloaded_on_another(
    bare: Path,
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target: dict[str, object] = {"name": "t", "url": str(bare), "policies": ["end"]}
    _targets(target)
    assert (
        hmz_exec(
            "-f", "chat", "-a", f"assistant={AGENT}", "--backup", "t", "hi"
        ).returncode
        == 0
    )
    epics = Hmz(project).epics
    (first,) = epics.all()
    before = epics.read(first)
    assert before is not None

    # Another machine: a home of its own, the same workspace, the same repository.
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "elsewhere"))
    _targets(target)
    assert epics.all() == []
    (held,) = Hmz().backups.listed("t")
    assert (held.key, held.epic, held.flow, held.task, held.how) == (
        backing.where(first),
        first.name,
        "chat",
        "hi",
        "done",
    )
    assert held.workspace == before.workspace
    assert main(["backup", "--list", "--to", "t"]) == 0
    assert first.name in capsys.readouterr().out

    assert main(["backup", "--pull", first.name, "--to", "t"]) == 0
    back = Path(capsys.readouterr().out.strip())

    assert epics.all() == [back]
    # As it ran, its sessions kept in the epic since the stand-in's home is the other
    # machine's, and none of that machine's targets or backups.
    assert epics.read(back) == before._replace(
        at=back,
        sessions=tuple(
            one._replace(where=f"sessions/{one.backend}") for one in before.sessions
        ),
        backup=(),
        backed={},
    )
    for was, now in zip(before.sessions, epics.sessions(back), strict=True):
        assert set(logs(back, now)) == set(logs(first, was))
    assert epics.foreign(back) == ""
    with pytest.raises(ValueError, match="already here"):
        Hmz().backups.pulled("t", held.key)
    assert main(["backup", "--pull", held.key, "--to", "t"]) == 1
    assert "already here" in capsys.readouterr().err

    project.rename(tmp_path / "moved")
    assert "not on this machine" in epics.foreign(back)


def test_an_epic_this_machine_backed_up_and_still_has_is_not_downloaded(
    bare: Path, project: Path
) -> None:
    _targets({"name": "t", "url": str(bare), "policies": ["end"]}, defaults=("t",))
    assert hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", "hi").returncode == 0

    with pytest.raises(ValueError, match="already here"):
        Hmz().backups.pulled("t", backing.where(_epic(project)))


def test_epics_of_two_runs_share_one_repository(bare: Path, project: Path) -> None:
    _targets({"name": "t", "url": str(bare), "policies": ["end"]}, defaults=("t",))

    for said in ("one", "two"):
        assert hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", said).returncode == 0

    first, second = Hmz(project).epics.all()
    listed = subprocess.run(
        [
            "git",
            "--git-dir",
            str(bare),
            "ls-tree",
            "-d",
            "--name-only",
            "main:" + backing.where(first).rpartition("/")[0],
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert listed == [first.name, second.name]
