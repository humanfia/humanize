"""Epics backed up to git repositories, with git itself stood in for."""

from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from hmz import machine
from hmz.runtime import backing
from hmz.runtime.epic import Epic, read
from hmz.runtime.exporting import REDACTED
from hmz.runtime.settings import Target

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

LAB = Target("lab", "ssh://me:pw@host/epics", policies=("session", "end"))
HOME = Target("home", "/srv/epics", policies=("interval",), every=60)


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backing, "configured", lambda: ((LAB, HOME), ("lab",)))
    monkeypatch.setattr(socket, "gethostname", lambda: "box.example.com")


@dataclass
class Git:
    """What git was asked, and what it answers: everything goes, the branch is new."""

    asked: list[list[str]] = field(default_factory=list[list[str]])
    refuses: str = ""

    def __call__(self, argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        said = argv[3:] if argv[:2] == ["git", "-C"] else argv[1:]
        self.asked.append(said)
        failed = (
            said[:1] == ["rev-parse"]
            or said[:3] == ["diff", "--cached", "--quiet"]
            or said == ["config", "user.email"]
            or (said[:1] == ["push"] and bool(self.refuses))
        )
        return subprocess.CompletedProcess(argv, int(failed), "", self.refuses)


@pytest.fixture
def git(monkeypatch: pytest.MonkeyPatch) -> Git:
    made = Git()
    monkeypatch.setattr(subprocess, "run", made)
    return made


@pytest.fixture
def ran(tmp_path: Path) -> Path:
    workspace = tmp_path / "project"
    workspace.mkdir()
    with Epic("ralph", "fix it with sk-ant-abcdefghijklmnopq", workspace) as one:
        pass
    return one.path


def test_no_names_are_the_defaults_and_names_are_checked() -> None:
    assert backing.chosen(None) == ("lab",)
    assert backing.chosen(["home", "lab", "home"]) == ("home", "lab")
    assert backing.chosen([]) == ()
    with pytest.raises(ValueError, match="no backup target is named x, y"):
        backing.chosen(["lab", "x", "y"])


def test_an_epic_goes_under_this_machine_and_its_workspace(ran: Path) -> None:
    assert backing.where(ran) == f"box/{ran.parent.name}/{ran.name}"


def test_an_epic_is_committed_and_pushed_and_says_so(git: Git, ran: Path) -> None:
    backing.push(ran, ["lab"], "manual")

    assert backing.wait(10)
    clone = machine() / "backup" / "lab"
    into = backing.where(ran)
    assert (clone / into / "epic.jsonl").is_file()
    assert "sk-ant-" not in (clone / into / "epic.jsonl").read_text()
    assert (clone / into / "manifest.json").is_file()
    assert ["config", "remote.origin.url", LAB.url] in git.asked
    assert ["symbolic-ref", "HEAD", "refs/heads/main"] in git.asked
    assert ["commit", "-q", "-m", f"Back up epic {ran.name} (manual)"] in git.asked
    assert ["push", "-q", "origin", "HEAD:refs/heads/main"] in git.asked
    said = read(ran)
    assert said is not None
    assert said.backed["lab"]["ok"] is True
    assert said.backed["lab"]["why"] == "manual"


def test_a_push_refused_twice_is_said_with_no_credential_in_it(
    git: Git, ran: Path
) -> None:
    git.refuses = "rejected by https://me:pw@host/epics"

    backing.push(ran, ["lab"], "end")

    assert backing.wait(10)
    assert sum(one[:1] == ["push"] for one in git.asked) == 2
    said = read(ran)
    assert said is not None
    assert said.backed["lab"]["ok"] is False
    assert said.backed["lab"]["error"] == f"rejected by https://{REDACTED}@host/epics"


def test_a_target_since_gone_from_settings_is_said(git: Git, ran: Path) -> None:
    backing.push(ran, ["gone"], "manual")

    assert backing.wait(10)
    said = read(ran)
    assert said is not None
    assert said.backed["gone"]["error"] == "no backup target is named gone"
    assert git.asked == []


def test_nothing_queued_is_nothing_to_wait_for() -> None:
    assert backing.wait(0)


def test_each_policy_backs_up_to_the_targets_that_hold_it(
    monkeypatch: pytest.MonkeyPatch, ran: Path
) -> None:
    pushed: list[tuple[Any, ...]] = []

    def push(epic: Path, names: Iterable[str], why: str) -> None:
        pushed.append((epic, tuple(names), why))

    monkeypatch.setattr(backing, "push", push)

    keeping = backing.Keeping(ran, ["lab", "home"])
    keeping.closed()
    keeping.ended()

    assert pushed == [(ran, ("lab",), "session"), (ran, ("lab",), "end")]


def test_an_epic_backed_up_nowhere_asks_nothing_of_settings(
    monkeypatch: pytest.MonkeyPatch, ran: Path
) -> None:
    def asked() -> None:
        raise AssertionError

    monkeypatch.setattr(backing, "configured", asked)

    backing.Keeping(ran, ()).ended()
