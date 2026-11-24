"""`hmz flows`: the flows listed, one shown, the backends, and an epic checked and set up."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace as Said
from typing import Any
from unittest import mock

import pytest

from hmz.cli import main, tree


@pytest.fixture
def flows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> mock.Mock:
    """The flows family of the client the command reaches, asked from a directory."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    monkeypatch.chdir(tmp_path)
    return client.flows


@pytest.fixture
def specs(monkeypatch: pytest.MonkeyPatch) -> Said:
    """What reads `-p`, stood in: the params as given, and a budget of one limit."""
    budget = mock.Mock()
    budget.model_dump_json.return_value = '{"cost": 5.0}'
    read = Said(
        params=mock.Mock(return_value={"rounds": "4"}),
        budget=mock.Mock(return_value=budget),
    )
    monkeypatch.setattr("hmz.runtime.flowing.specs.parse_params", read.params)
    monkeypatch.setattr("hmz.runtime.flowing.specs.parse_budget", read.budget)
    return read


def _role(name: str, **said: Any) -> Said:
    held: dict[str, Any] = {
        "required": True,
        "auto": False,
        "harness": "",
        "permission": {"preset": "workspace-write", "network": False, "granular": []},
        "skills": (),
        "clis": ("claude", "codex"),
    }
    return Said(name=name, **(held | said))


def _env(name: str, **said: Any) -> Said:
    held: dict[str, Any] = {
        "required": True,
        "auto": False,
        "cpu": None,
        "memory": None,
        "gpu": None,
        "image": None,
    }
    return Said(name=name, **(held | said))


def _declared(**said: Any) -> Said:
    held: dict[str, Any] = {
        "name": "tells",
        "ref": "tells:tells",
        "description": "Tells a story.",
        "resumable": False,
        "agents": (),
        "envs": (),
        "params": {},
        "remembered": {},
        "answer": {"name": "tells"},
    }
    return Said(**(held | said))


def test_the_flows_are_listed_in_columns_for_the_directory_stood_in(
    flows: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    flows.list.return_value = Said(
        flows=(
            Said(name="tells", whose="local", about="Tells a story."),
            Said(name="@team/review", whose="team", about="Reviews."),
        ),
        answer={"flows": [], "flow": "tells", "running": []},
    )

    assert main(["flows", "list"]) == 0

    assert capsys.readouterr().out == (
        "tells         local  Tells a story.\n@team/review  team   Reviews.\n"
    )
    flows.list.assert_called_once_with(str(tmp_path))

    assert main(["flows", "list", "-w", "~/app", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "flows": [],
        "flow": "tells",
        "running": [],
    }
    flows.list.assert_called_with("~/app")


def test_no_flow_on_offer_is_said_beside_the_empty_list(
    flows: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    flows.list.return_value = Said(flows=(), answer={"flows": []})

    assert main(["flows", "list"]) == 0
    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == (
        "No flows installed yet. A flow is what an epic runs. "
        "Install one from a flowverse.\n"
    )

    assert main(["flows", "list", "--json"]) == 0
    said = capsys.readouterr()
    assert json.loads(said.out) == {"flows": []}
    assert said.err == ""


def test_a_flow_is_shown_with_a_line_that_starts_it(
    flows: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    flows.get.return_value = _declared(
        resumable=True,
        agents=(
            _role(
                "coder",
                skills=("plot",),
                permission={
                    "preset": "read-only",
                    "network": True,
                    "granular": [{"path": "/srv", "access": "write"}],
                },
            ),
            _role("helper", required=False, clis=()),
            _role("boss", auto=True),
        ),
        envs=(
            _env("workspace", auto=True),
            _env("box", cpu=2, image="py"),
            _env("spare", required=False),
        ),
        params={
            "required": ["about"],
            "properties": {
                "rounds": {
                    "type": "integer",
                    "default": 3,
                    "title": "Rounds",
                    "description": "How many",
                },
                "about": {"type": "string"},
                "mode": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                },
            },
        },
        remembered={
            "agents": {"coder": "claude/opus:high"},
            "envs": {},
            "params": {"rounds": 4, "about": "two cats", "mode": None},
            "budget": {
                "duration": "PT1H",
                "cost": 5.0,
                "output_tokens": None,
                "graceful": {"duration": True, "cost": False, "output_tokens": True},
            },
            "profile_flow": True,
            "profile_environment": False,
            "backup": [],
        },
    )

    assert main(["flows", "show", "tells"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "tells",
        "Tells a story.",
        "ref        tells:tells",
        "resumable  yes",
        "agents",
        (
            "  coder   required  claude, codex                           "
            "read-only · writes /srv · goes online  skills: plot"
        ),
        (
            "  helper  optional  No harness installed here can fill it.  "
            "workspace-write · stays offline"
        ),
        "  boss (a person, answering here)",
        "environments",
        "  workspace (the folder the epic runs in)",
        "  box    required  cpu=2 image=py",
        "  spare  optional",
        "params",
        "  rounds  integer      3         Rounds — How many",
        "  about   string       required",
        "  mode    string|null  null",
        "What this folder was last set up with",
        (
            "  -a coder=claude/opus:high -p rounds=4 -p 'about=two cats' "
            "-p budget.duration=PT1H -p budget.cost=5.0 -p budget.graceful.cost=false "
            "--profile-flow --backup none"
        ),
        "Start the flow",
        (
            "  hmz exec -f tells -a coder=HARNESS/MODEL -e box=ENV -p about=VALUE "
            "-p budget.cost=USD TASK"
        ),
    ]
    flows.get.assert_called_once_with("tells", str(tmp_path))


def test_a_flow_that_declares_nothing_says_none_and_answers_whole_as_json(
    flows: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    flows.get.return_value = _declared(description="")

    assert main(["flows", "show", "tells", "-w", "/w"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "tells",
        "ref        tells:tells",
        "resumable  no",
        "agents",
        "  none",
        "environments",
        "  none",
        "params",
        "  none",
        "Start the flow",
        "  hmz exec -f tells -p budget.cost=USD TASK",
    ]
    flows.get.assert_called_once_with("tells", "/w")

    assert main(["flows", "show", "tells", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"name": "tells"}


def test_the_backends_are_written_as_an_agent_is(
    flows: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    opus = Said(name="opus", efforts=("low", "high"))
    flows.backends.return_value = Said(
        clis={
            "claude": (
                Said(name="", models=(opus,)),
                Said(name="work", models=(Said(name="haiku", efforts=()),)),
            ),
            "codex": (Said(name="", models=()),),
        },
        installable={"grok": (Said(name="grok-4", efforts=("high",)),), "pi": ()},
        envs=("local", "ssh"),
        answer={"clis": {}, "installable": {}, "envs": []},
    )

    assert main(["flows", "backends"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "Installed",
        "  claude/opus        low, high",
        "  claude@work/haiku",
        "  codex              No models listed",
        "Not installed",
        "  grok/grok-4  high",
        "  pi",
        "environments",
        "  local",
        "  ssh",
    ]

    assert main(["flows", "backends", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "clis": {},
        "installable": {},
        "envs": [],
    }


def test_no_harness_installed_is_said_where_they_would_be_listed(
    flows: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    flows.backends.return_value = Said(clis={}, installable={}, envs=(), answer={})

    assert main(["flows", "backends"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "Installed",
        "  No harness is installed on this daemon.",
        "environments",
    ]


def test_an_epic_is_checked_with_what_the_line_sets_it_up_with(
    flows: mock.Mock, specs: Said, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    flows.check.return_value = Said(
        ref="tells:tells",
        names={"coder": "claude-opus", "rev": "codex-gpt"},
        budget={"cost": 5.0, "duration": None, "graceful": False},
        backup=("origin",),
        unreadable="No price is known for it.",
        answer={"flow": "tells"},
    )
    line = [
        "flows", "check", "tells", "-a", "coder=claude/opus:high, rev=codex/gpt",
        "-e", "box=ssh@box/srv", "-p", "rounds=4", "-p", "budget.cost=5",
        "--profile-flow", "--resume", "--backup", "origin",
    ]  # fmt: skip

    assert main(line) == 0

    assert capsys.readouterr().out.splitlines() == [
        "An epic set up like this can start.",
        "ref     tells:tells",
        "agents  coder=claude-opus, rev=codex-gpt",
        "budget  -p budget.cost=5.0 -p budget.graceful=false",
        "Backup  origin",
        "No price is known for it.",
    ]
    flows.check.assert_called_once_with(
        str(tmp_path),
        "tells",
        resume=True,
        agents={"coder": "claude/opus:high", "rev": "codex/gpt"},
        envs={"box": "ssh@box/srv"},
        params={"rounds": "4"},
        budget={"cost": 5.0},
        profile_flow=True,
        profile_environment=None,
        backup=["origin"],
    )
    specs.params.assert_called_once_with(("rounds=4", "budget.cost=5"))
    specs.budget.assert_called_once_with(("rounds=4", "budget.cost=5"))


def test_a_line_that_says_nothing_leaves_everything_to_the_daemon(
    flows: mock.Mock, specs: Said, capsys: pytest.CaptureFixture[str]
) -> None:
    specs.params.return_value = {}
    specs.budget.return_value = None
    flows.check.return_value = Said(
        ref="r", names={}, budget=None, backup=(), unreadable="", answer={"flow": "x"}
    )

    assert main(["flows", "check", "x", "-w", "/w", "--backup", "none"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "An epic set up like this can start.",
        "ref     r",
        "agents  none",
        "budget  none",
        "Backup  none",
    ]
    flows.check.assert_called_once_with(
        "/w",
        "x",
        resume=None,
        agents=None,
        envs=None,
        params=None,
        budget=None,
        profile_flow=None,
        profile_environment=None,
        backup=[],
    )

    assert main(["flows", "check", "x", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"flow": "x"}


@pytest.mark.parametrize(
    ("options", "wrong"),
    [
        (["-a", "coder"], "-a coder: expected `ROLE=VALUE`"),
        (["-e", "=local"], "-e =local: expected `ROLE=VALUE`"),
        (["-a", "a=x/m", "-a", "a=y/n"], "-a: the role a is given twice"),
        (
            ["--backup", "none", "--backup", "origin"],
            "`--backup none` cannot be given with another backup target",
        ),
    ],
)
def test_a_line_that_cannot_be_read_is_a_usage_error_and_asks_nothing(
    flows: mock.Mock,
    specs: Said,
    capsys: pytest.CaptureFixture[str],
    options: list[str],
    wrong: str,
) -> None:
    assert main(["flows", "check", "tells", *options]) == 2

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == (
        f"hmz flows check: {wrong}\nRun `hmz flows check --help` for help.\n"
    )
    flows.check.assert_not_called()

    assert main(["flows", "setup", "tells", *options, "--json"]) == 2

    said = capsys.readouterr()
    assert json.loads(said.out) == {"error": {"code": 400, "message": wrong}}
    assert said.err == ""
    flows.setup.assert_not_called()


def test_a_param_that_cannot_be_read_is_said_as_its_reader_says_it(
    flows: mock.Mock, specs: Said, capsys: pytest.CaptureFixture[str]
) -> None:
    from hmz.runtime.flowing.specs import SpecError

    specs.budget.side_effect = SpecError("-p budget.cost: not a number")

    assert main(["flows", "check", "tells", "-p", "budget.cost=lots"]) == 2

    assert capsys.readouterr().err.splitlines()[0] == (
        "hmz flows check: -p budget.cost: not a number"
    )
    flows.check.assert_not_called()


def test_a_set_up_is_saved_for_the_folder_named(
    flows: mock.Mock, specs: Said, capsys: pytest.CaptureFixture[str]
) -> None:
    flows.setup.return_value = _declared()
    flows.get.return_value = _declared(
        params={
            "properties": {
                "rounds": {"type": "integer"},
                "loud": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                "ratio": {"type": "number"},
                "about": {"type": "string"},
            }
        }
    )
    specs.params.return_value = {
        "rounds": "4",
        "loud": "False",
        "ratio": "half",
        "about": "7",
        "unknown": "1",
    }

    line = ["flows", "setup", "tells", "-w", "/w", "-a", "coder=claude/opus"]
    assert main([*line, "-p", "budget.cost=5", "--profile-environment"]) == 0

    assert capsys.readouterr().out == (
        "The set-up of the flow tells was saved for the folder /w.\n"
    )
    flows.setup.assert_called_once_with(
        "/w",
        "tells",
        agents={"coder": "claude/opus"},
        envs={},
        params={
            "rounds": 4,
            "loud": False,
            "ratio": "half",
            "about": "7",
            "unknown": "1",
        },
        budget={"cost": 5.0},
        profile_flow=False,
        profile_environment=True,
        backup=None,
    )
    flows.get.assert_called_once_with("tells", "/w")

    assert main([*line, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"name": "tells"}


def test_a_flow_is_forked_into_the_folder_and_says_where(
    flows: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    flows.fork.return_value = Said(said="copied tells to /w/x", at="/w/x")

    assert main(["flows", "fork", "tells"]) == 0
    assert capsys.readouterr().out == "copied tells to /w/x\n"
    flows.fork.assert_called_once_with(str(tmp_path), "tells")

    (tmp_path / "sub").mkdir()
    assert main(["flows", "fork", "tells", "-w", "sub", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "said": "copied tells to /w/x",
        "at": "/w/x",
    }
    flows.fork.assert_called_with(str(Path.cwd() / "sub"), "tells")
