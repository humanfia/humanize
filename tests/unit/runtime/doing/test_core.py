"""Humanize as one object: a workspace, and everything it hands out, made when asked for."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import backends
from hmz.runtime import (
    Accounts,
    Epics,
    Flows,
    Flowverses,
    Hmz,
    Holding,
    NousBook,
    Run,
    Runtimes,
    runner,
    telemetry,
)
from hmz.runtime.settings import Settings
from tests.unit.runtime import doubles_u12 as doubles

if TYPE_CHECKING:
    from tests.unit.runtime.doubles_u12 import Stands


def test_the_workspace_is_the_one_named_or_wherever_humanize_is_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert Hmz().workspace == Path.cwd()
    assert Hmz(str(tmp_path / "x")).workspace == tmp_path / "x"


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("flows", Flows),
        ("accounts", Accounts),
        ("runtimes", Runtimes),
        ("nous", NousBook),
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


def test_what_a_batch_carries_is_this_machines_own_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.runtime.doing import daemons

    hmz = Hmz(tmp_path)
    seen: list[tuple[object, tuple[str, ...]]] = []

    def carried(by: object, pages: tuple[str, ...]) -> list[tuple[str, dict[str, Any]]]:
        seen.append((by, pages))
        return [("/api/settings", {"details": True})]

    monkeypatch.setattr(daemons, "carried", carried)

    assert hmz.carried(("general",)) == [("/api/settings", {"details": True})]
    assert seen == [(hmz, ("general",))]
    assert hmz.daemons.CARRIED == ("general", "nous", "runtimes", "backup")


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
    made: Any = Holding(tmp_path).runner(
        "ralph",
        agents={"builder": "claude/opus"},
        envs={"box": "local/x"},
        params={"rounds": 2},
        budget={"cost": 1},
        profile_flow=True,
        profile_environment=True,
        resume=True,
    )

    assert made is making.made[0]
    assert made.flow == "ralph"
    assert made.said == {
        "agents": {"builder": "claude/opus"},
        "envs": {"box": "local/x"},
        "params": {"rounds": 2},
        "budget": {"cost": 1},
        "profile_flow": True,
        "profile_environment": True,
        "resume": True,
        "workspace": tmp_path,
        "backup": None,
    }


def test_a_runner_of_no_workspace_named_runs_wherever_humanize_is(
    making: Making,
) -> None:
    Holding().runner("chat")

    assert making.made[0].said == {
        "agents": (),
        "envs": (),
        "params": None,
        "budget": None,
        "profile_flow": False,
        "profile_environment": False,
        "resume": False,
        "workspace": None,
        "backup": None,
    }


def test_a_run_is_a_runner_and_its_task_with_nothing_started(
    making: Making, tmp_path: Path
) -> None:
    someone: Any = object()

    run = Holding(tmp_path).run(
        "ralph", "fix it", budget={"cost": 1}, outworlder=someone
    )

    assert isinstance(run, Run)
    assert run.task == "fix it"
    assert run.flow is making.made[0].flow
    assert making.made[0].said["budget"] == {"cost": 1}
    assert run.running is False


def test_a_chat_is_set_up_in_this_workspace_with_nothing_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from hmz.runtime import chatting
    from hmz.runtime.doing.running import Chatting

    made: list[tuple[Any, Any]] = []

    def chat(spec: Any, *, person: Any) -> Any:
        made.append((spec, person))
        return SimpleNamespace(spec=spec)

    monkeypatch.setattr(chatting, "Chat", chat)
    person: Any = object()

    held = Holding(tmp_path).chat(
        "claude/opus", "hello", person=person, resume="/epics/e1", prefer="flow"
    )

    assert isinstance(held, Chatting)
    ((spec, given),) = made
    assert given is person
    assert spec == chatting.ChatSpec(
        tmp_path, "claude/opus", "hello", resume=Path("/epics/e1"), prefer="flow"
    )
    assert Holding(tmp_path).chat("claude/opus", "hi", person=person).task == "hi"
    assert made[-1][0].resume is None
    Holding(tmp_path).chat("claude/opus", "hi", person=person, permission="read-only")
    assert made[-1][0].permission == "read-only"


def test_the_workspace_itself_neither_runs_nor_holds_an_epic() -> None:
    for name in ("run", "runner", "exec", "host", "chat"):
        assert not hasattr(Hmz, name)


def test_the_line_adding_an_extra_is_the_one_installed_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.runtime.doing import installed

    def adding(backend: str) -> str:
        return f"add {backend}"

    monkeypatch.setattr(installed, "adding", adding)

    assert Hmz(tmp_path).adding("litellm") == "add litellm"
