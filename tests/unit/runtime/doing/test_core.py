"""humanize as one object: a workspace, and everything it hands out, made when asked for."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import backends
from hmz.runtime import (
    Accounts,
    Epics,
    Fallbacks,
    Flows,
    Flowverses,
    Hmz,
    Host,
    Run,
    Runtimes,
    runner,
    telemetry,
)
from hmz.runtime.doing import running
from hmz.runtime.settings import Settings
from tests.unit.runtime import doubles_u12 as doubles

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.unit.runtime.doubles_u12 import Stands


def test_the_workspace_is_the_one_named_or_wherever_humanize_is_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert Hmz().workspace == Path.cwd()
    assert Hmz(str(tmp_path / "x")).workspace == tmp_path / "x"
    assert Hmz(tmp_path).home == Path(os.environ["HUMANIZE_HOME"])


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("flows", Flows),
        ("accounts", Accounts),
        ("runtimes", Runtimes),
        ("fallbacks", Fallbacks),
        ("epics", Epics),
    ],
)
def test_each_part_is_made_once_and_kept(name: str, kind: type, tmp_path: Path) -> None:
    hmz = Hmz(tmp_path)

    made = getattr(hmz, name)

    assert isinstance(made, kind)
    assert getattr(hmz, name) is made
    assert getattr(Hmz(tmp_path), name) is not made


def test_the_places_flows_come_from_are_the_flows_own(tmp_path: Path) -> None:
    hmz = Hmz(tmp_path)

    assert isinstance(hmz.verses, Flowverses)
    assert hmz.verses is hmz.flows.verses


def test_the_settings_are_this_workspaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doubles.store(monkeypatch)
    Settings(tmp_path).remember("ralph", {})
    hmz = Hmz(tmp_path)

    assert isinstance(hmz.settings, Settings)
    assert hmz.settings is hmz.settings
    assert hmz.settings.flow == "ralph"


def test_the_settings_of_no_workspace_named_are_this_directorys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doubles.store(monkeypatch)
    monkeypatch.chdir(tmp_path)
    Settings(tmp_path).remember("aot", {})

    assert Hmz().settings.flow == "aot"


def test_the_runs_are_this_workspaces(tmp_path: Path) -> None:
    assert Hmz(tmp_path).epics.under() == Epics(tmp_path).under()


def test_every_backend_is_listed_installed_or_not(stand: Stands) -> None:
    profiles = stand(backends, "profiles", ("claude", "codex"))

    assert Hmz().backends() == ("claude", "codex")
    assert profiles.calls == [((), {})]


@pytest.mark.parametrize("answer", [True, False])
def test_reporting_starts_where_it_was_answered_yes(
    answer: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telemetry, "start", lambda: answer)

    assert Hmz().reports() is answer


def test_a_line_is_read_without_loading_anything() -> None:
    line = Hmz().read(["-f", "chat", "hello"])

    assert (line.flow, line.task) == ("chat", "hello")


@dataclass
class Made:
    """A runner stood in for: what it was made with."""

    flow: object
    said: dict[str, Any]


@dataclass
class Making:
    made: list[Made] = field(default_factory=list[Made])

    def __call__(self, flow: object, **said: Any) -> Made:
        self.made.append(Made(flow, said))
        return self.made[-1]


@pytest.fixture
def making(monkeypatch: pytest.MonkeyPatch) -> Making:
    made = Making()
    monkeypatch.setattr(runner, "Runner", made)
    return made


def test_a_runner_is_made_in_this_workspace(making: Making, tmp_path: Path) -> None:
    made: Any = Hmz(tmp_path).runner(
        "ralph",
        agents={"builder": "claude/opus"},
        envs={"box": "local/x"},
        params={"rounds": 2},
        budget={"cost": 1},
        profile=True,
        resume=True,
    )

    assert made is making.made[0]
    assert made.flow == "ralph"
    assert made.said == {
        "agents": {"builder": "claude/opus"},
        "envs": {"box": "local/x"},
        "params": {"rounds": 2},
        "budget": {"cost": 1},
        "profile": True,
        "resume": True,
        "workspace": tmp_path,
    }


def test_a_runner_of_no_workspace_named_runs_wherever_humanize_is(
    making: Making,
) -> None:
    Hmz().runner("chat")

    assert making.made[0].said == {
        "agents": (),
        "envs": (),
        "params": None,
        "budget": None,
        "profile": False,
        "resume": False,
        "workspace": None,
    }


def test_a_run_is_a_runner_and_its_task_with_nothing_started(
    making: Making, tmp_path: Path
) -> None:
    someone: Any = object()

    run = Hmz(tmp_path).run("ralph", "fix it", budget={"cost": 1}, outworlder=someone)

    assert isinstance(run, Run)
    assert run.task == "fix it"
    assert run.flow is making.made[0].flow
    assert making.made[0].said["budget"] == {"cost": 1}
    assert run.running is False


@dataclass
class Ran:
    """A run stood in for: what it was made with, and what running it returns."""

    held: list[Ran] = field(default_factory=list["Ran"])
    runner: Any = None
    task: str = ""
    outworlder: Any = None

    def __call__(self, runner: Any, task: str, *, outworlder: Any = None) -> Ran:
        made = Ran(runner=runner, task=task, outworlder=outworlder)
        self.held.append(made)
        return made

    def run(self) -> str:
        return f"ran {self.task}"


def test_a_line_is_run_to_its_return_on_what_it_names(
    making: Making, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ran = Ran()
    monkeypatch.setattr(running, "Run", ran)

    said = Hmz(tmp_path).exec(
        [
            "-f",
            "ralph",
            "-a",
            "builder=claude/opus:high",
            "-e",
            "box=local/srv",
            "-p",
            "rounds=2,budget.cost=3",
            "--profile",
            "--resume",
            "fix it",
        ]
    )

    assert said == "ran fix it"
    (made,) = making.made
    assert made.flow == "ralph"
    assert [str(one) for one in made.said["agents"]] == ["builder=claude/opus:high"]
    assert [str(one) for one in made.said["envs"]] == ["box=local/srv"]
    assert made.said["params"] == {"rounds": "2"}
    assert made.said["budget"].cost == 3.0
    assert (made.said["profile"], made.said["resume"]) == (True, True)
    assert made.said["workspace"] == tmp_path
    assert ran.held[0].runner is made
    assert ran.held[0].outworlder is None


def test_a_line_that_is_not_one_runs_nothing(making: Making) -> None:
    with pytest.raises(SystemExit):
        Hmz().exec(["--nope"])
    assert making.made == []


@pytest.fixture
def hmz(tmp_path: Path) -> Iterator[Hmz]:
    made = Hmz(tmp_path)
    yield made
    made.host().close()


def test_the_host_is_one_however_often_asked(hmz: Hmz) -> None:
    host = hmz.host()

    assert isinstance(host, Host)
    assert hmz.host() is host
