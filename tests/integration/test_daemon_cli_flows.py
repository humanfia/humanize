"""`hmz flows`, `hmz flowverses` and `hmz workspaces`, asked of a real daemon over its socket.

A flow the test writes into its project, and a flowverse that is a git repository on this
disk listing two releases of a flow kept in another: listed, shown, checked, set up, forked,
installed, updated, uninstalled and removed, each change read back by the command that reads
it, and the same asked through the SDK's families.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli
from hmz.sdk import Client, Refused
from tests.integration.doubles_daemon import hosting, project

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [pytest.mark.timeout(120)]

#: A flow of the project's own: one person, the folder, a param with a default and one without.
TELLS = '''
"""Tells a story, a round at a time."""

from pydantic import Field

from hmz.flows import (
    AgentCollection,
    EnvCollection,
    FlowParams,
    LocalEnv,
    Outworlder,
    flow,
)


class Agents(AgentCollection):
    teller: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = Field(3, description="How many rounds it tells")
    about: str


@flow(agents=Agents, envs=Envs, params=Params, name="tells")
async def tells(task, *, agents, envs, params, ctx):
    """Tells a story, a round at a time."""
    return task
'''

#: A flow kept in a repository of its own, which a flowverse lists releases of.
REVIEW = '''
"""Reviews what it is given."""

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, name="review")
async def review(task, *, agents, envs, params, ctx):
    """Reviews what it is given."""
    return task
'''


def _committed(at: Path, message: str) -> str:
    """Commits everything in a directory, a repository from then on, and answers the commit."""
    git = ["git", "-C", str(at), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    if not (at / ".git").exists():
        subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", message], check=True)
    said = subprocess.run(
        [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return said.stdout.strip()


@pytest.fixture
def team(tmp_path: Path) -> Path:
    """A flowverse on this disk: an index listing releases 1.0.0 and 1.1.0 of `review`."""
    flow = tmp_path / "review.git"
    flow.mkdir()
    (flow / "review.py").write_text(REVIEW)
    commits = {"1.0.0": _committed(flow, "one")}
    (flow / "review.py").write_text(REVIEW + "\n# two\n")
    commits["1.1.0"] = _committed(flow, "two")
    index = tmp_path / "team.git"
    for version, commit in commits.items():
        release = index / "flows" / "review" / version
        release.mkdir(parents=True)
        (release / "flow.yaml").write_text(
            f"name: review\nversion: {version}\nrepo: file://{flow}\n"
            f"commit: {commit}\ndescription: Reviews what it is given\nlicense: MIT\n"
        )
    _committed(index, "index")
    return index


@pytest.fixture(autouse=True)
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    (at / ".hmz" / "flows").mkdir(parents=True)
    (at / ".hmz" / "flows" / "tells.py").write_text(TELLS)
    with hosting():
        yield at.resolve()


def _json(capsys: pytest.CaptureFixture[str], *line: str, status: int = 0) -> Any:
    """What one command answers under `--json`, having ended as it should."""
    capsys.readouterr()
    assert cli.main([*line, "--json"]) == status
    said = capsys.readouterr()
    assert said.err == ""
    return json.loads(said.out)


def _text(capsys: pytest.CaptureFixture[str], *line: str, status: int = 0) -> str:
    """What one command prints, having ended as it should."""
    capsys.readouterr()
    assert cli.main([*line]) == status
    return capsys.readouterr().out


def test_a_flow_of_the_project_is_listed_and_shown_well_enough_to_start_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _text(capsys, "flows", "list") == (
        "@local/tells  local  Tells a story, a round at a time.\n"
    )
    assert _json(capsys, "flows", "list") == {
        "flows": [
            {
                "whose": "local",
                "name": "@local/tells",
                "about": "Tells a story, a round at a time.",
            }
        ],
        "flow": "",
        "running": [],
    }

    shown = _text(capsys, "flows", "show", "@local/tells").splitlines()

    assert shown[:4] == [
        "@local/tells",
        "Tells a story, a round at a time.",
        "ref        tells:tells",
        "resumable  no",
    ]
    assert "  teller (a person, answering here)" in shown
    assert "  workspace (the folder the epic runs in)" in shown
    assert "  rounds  integer  3         How many rounds it tells" in shown
    assert "  about   string   required" in shown
    assert shown[-2:] == [
        "Start the flow",
        "  hmz exec -f @local/tells -p about=VALUE -p budget.cost=USD TASK",
    ]

    declared = _json(capsys, "flows", "show", "@local/tells")

    assert declared["name"] == "@local/tells"
    assert [one["name"] for one in declared["agents"]] == ["teller"]
    assert declared["params"]["required"] == ["about"]
    assert declared["remembered"]["budget"] == {}


def test_another_folder_has_no_flow_of_this_one_and_an_unknown_flow_is_refused(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    assert _json(capsys, "flows", "list", "-w", str(elsewhere))["flows"] == []
    assert cli.main(["flows", "show", "nothing"]) == 1
    assert capsys.readouterr().err == (
        "hmz flows show: nothing is not a flow on offer here.\n"
    )
    assert _json(capsys, "flows", "show", "nothing", status=1) == {
        "error": {"code": 404, "message": "nothing is not a flow on offer here."}
    }


def test_the_backends_name_what_an_environment_can_be_put_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    backends = _json(capsys, "flows", "backends")

    assert set(backends) == {"clis", "installable", "envs"}
    assert backends["envs"][:2] == ["local", "ssh"]
    assert "environments\n  local\n  ssh\n" in _text(capsys, "flows", "backends")


def test_an_epic_is_checked_as_exec_checks_it_and_starts_nothing(
    capsys: pytest.CaptureFixture[str], workspace: Path
) -> None:
    line = ("flows", "check", "@local/tells", "-p", "about=cats")

    assert _text(capsys, *line, "-p", "budget.cost=5").splitlines() == [
        "An epic set up like this can start.",
        "ref     tells:tells",
        "agents  none",
        "budget  -p budget.cost=5.0",
        "Backup  none",
    ]
    checked = _json(capsys, *line, "-p", "budget.duration=1h,budget.cost=5")
    assert checked["flow"] == "@local/tells"
    assert checked["budget"]["cost"] == 5.0
    assert checked["budget"]["duration"] == "PT1H"
    assert checked["declared"]["name"] == "@local/tells"
    assert checked["backup"] == []

    assert cli.main([*line]) == 1
    assert "requires a budget" in capsys.readouterr().err
    refused = _json(capsys, "flows", "check", "@local/tells", "-p", "x=1", status=1)
    assert refused["error"]["code"] == 400
    assert not list((workspace / ".hmz").glob("epics/*"))


def test_a_set_up_is_saved_shown_again_and_forgotten_with_the_workspace(
    capsys: pytest.CaptureFixture[str], workspace: Path
) -> None:
    line = ("flows", "setup", "@local/tells", "-p", "about=cats", "-p", "rounds=4")

    assert cli.main([*line]) == 1
    assert "needs at least one limit" in capsys.readouterr().err
    assert _text(capsys, *line, "-p", "budget.cost=5", "--profile-flow") == (
        f"The set-up of the flow @local/tells was saved for the folder {workspace}.\n"
    )

    assert _json(capsys, "flows", "list")["flow"] == "@local/tells"
    remembered = _json(capsys, "flows", "show", "@local/tells")["remembered"]
    assert remembered["params"] == {"about": "cats", "rounds": 4}
    assert remembered["budget"]["cost"] == 5.0
    assert remembered["profile_flow"] is True
    shown = _text(capsys, "flows", "show", "@local/tells").splitlines()
    assert shown[-4:-2] == [
        "What this folder was last set up with",
        "  -p about=cats -p rounds=4 -p budget.cost=5.0 --profile-flow",
    ]

    assert _text(capsys, "workspaces", "forget", ".") == "Forgotten\n"
    assert _json(capsys, "flows", "list")["flow"] == ""
    assert _json(capsys, "flows", "show", "@local/tells")["remembered"]["budget"] == {}


def test_a_flowverse_is_added_and_a_flow_installed_updated_forked_and_removed(
    capsys: pytest.CaptureFixture[str], team: Path, workspace: Path
) -> None:
    assert _json(capsys, "flowverses", "list")["installed"] == []
    assert _text(capsys, "flowverses", "add", str(team), "--name", "team") == (
        "added team\n"
    )
    assert _text(capsys, "flowverses", "show", "team").splitlines() == [
        f"team  {team}",
        "@team/review  1.1.0  -  Reviews what it is given",
        "@team/review  1.0.0  -  Reviews what it is given",
    ]
    index = _json(capsys, "flowverses", "show", "team")
    assert index["flows"][0]["flow"] == "@team/review"
    assert [one["version"] for one in index["flows"][0]["releases"]] == [
        "1.1.0",
        "1.0.0",
    ]

    line = ("flowverses", "install", "@team/review")
    assert _text(capsys, *line, "--version", "1.0.0") == "@team/review 1.0.0\n"
    listed = _text(capsys, "flowverses", "list").splitlines()
    assert listed[-2:] == ["Installed", "  @team/review  1.0.0  team  1.1.0 out"]
    assert _json(capsys, "flowverses", "list")["updates"] == [
        {"flow": "@team/review", "from": "1.0.0", "to": "1.1.0"}
    ]
    assert "@team/review  team   Reviews what it is given." in _text(
        capsys, "flows", "list"
    )

    updated = _json(capsys, *line)
    assert updated["said"] == "@team/review 1.1.0"
    assert updated["updates"] == []
    assert _text(capsys, "flowverses", "show", "team").splitlines()[1] == (
        "@team/review  1.1.0  Installed  Reviews what it is given"
    )

    forked = _json(capsys, "flows", "fork", "@team/review")
    assert forked["at"].startswith(str(workspace / ".hmz" / "flows"))
    assert forked["said"] == f"copied @team/review to {forked['at']}"
    assert cli.main(["flows", "fork", "nothing"]) == 1
    assert capsys.readouterr().err == (
        "hmz flows fork: there is no flow called nothing to copy\n"
    )

    assert _text(capsys, "flowverses", "fetch", "team") == "fetched team\n"
    assert cli.main(["flowverses", "uninstall", "@team/review"]) == 1
    assert "run it again with `-y`" in capsys.readouterr().err
    assert _json(capsys, "flowverses", "list")["verses"][-1]["installed"] == 1
    assert _text(capsys, "flowverses", "uninstall", "@team/review", "-y") == (
        "uninstalled @team/review\n"
    )
    assert _json(capsys, "flowverses", "list")["installed"] == []

    assert _text(capsys, *line) == "@team/review 1.1.0\n"
    removed = _json(capsys, "flowverses", "remove", "team", "-y")
    assert removed["said"] == "removed team"
    assert [one["name"] for one in removed["verses"]] == ["official"]
    assert removed["installed"] == []
    assert _json(capsys, "flowverses", "show", "team", status=1) == {
        "error": {"code": 404, "message": "There is no flowverse team."}
    }
    assert cli.main(["flowverses", "remove", "official", "-y"]) == 1
    assert capsys.readouterr().err.startswith("hmz flowverses remove: official is")


def test_a_workspace_is_added_listed_and_forgotten_and_a_folder_browsed_to(
    capsys: pytest.CaptureFixture[str], workspace: Path, tmp_path: Path
) -> None:
    other = (tmp_path / "other").resolve()
    (other / "inner").mkdir(parents=True)
    (other / ".hidden").mkdir()
    (other / "notes.txt").write_text("")

    assert _text(capsys, "workspaces", "list") == f"{workspace}  0  0  -\n"
    assert _text(capsys, "workspaces", "add", str(other)) == f"{other}\n"
    known = _json(capsys, "workspaces", "list")
    assert known["here"] == str(workspace)
    assert [(one["path"], one["here"]) for one in known["workspaces"]] == [
        (str(workspace), True),
        (str(other), False),
    ]
    assert cli.main(["workspaces", "add", str(tmp_path / "nowhere")]) == 1
    assert capsys.readouterr().err.startswith(
        "hmz workspaces add: There is no directory "
    )

    left = _json(capsys, "workspaces", "forget", str(other))
    assert [one["path"] for one in left["workspaces"]] == [str(workspace)]

    assert _text(capsys, "workspaces", "browse", str(other)) == f"{other}/inner/\n"
    assert _text(
        capsys, "workspaces", "browse", str(other), "--files", "--hidden"
    ).splitlines() == [f"{other}/.hidden/", f"{other}/inner/", f"{other}/notes.txt"]
    found = _json(capsys, "workspaces", "browse", str(other))
    assert found["whole"] == str(other)
    assert found["entries"] == [{"name": "inner", "dir": True}]
    assert found["more"] == 0
    assert cli.main(["workspaces", "browse", str(tmp_path / "nowhere")]) == 1
    assert "cannot be read" in capsys.readouterr().err

    assert _text(capsys, "workspaces", "complete", f"{other}/in") == (
        f"{other}/inner/\n"
    )
    assert _json(capsys, "workspaces", "complete", f"{other}/") == {
        "paths": [f"{other}/inner/"]
    }


def test_the_same_is_asked_through_the_sdk(team: Path, workspace: Path) -> None:
    here = str(workspace)
    with Client.local() as client:
        offered = client.flows.list(here)
        assert [(one.name, one.whose) for one in offered.flows] == [
            ("@local/tells", "local")
        ]
        assert client.flows.list().flows == ()

        flow = client.flows.get("@local/tells", here)
        assert flow.agents[0].name == "teller"
        assert flow.agents[0].auto
        assert flow.envs[0].auto
        assert flow.params["properties"]["rounds"]["default"] == 3
        with pytest.raises(Refused, match="not a flow on offer") as refused:
            client.flows.get("nothing", here)
        assert refused.value.code == 404

        assert "local" in client.flows.backends().envs
        set_up: dict[str, Any] = {"params": {"about": "cats"}, "budget": {"cost": 5}}
        checked = client.flows.check(here, "@local/tells", **set_up)
        assert checked.declared.name == "@local/tells"
        assert checked.budget is not None
        assert checked.budget["cost"] == 5.0
        with pytest.raises(Refused, match="requires a budget"):
            client.flows.check(here, "@local/tells", params={"about": "cats"})
        saved = client.flows.setup(here, "@local/tells", idem="once", **set_up)
        assert saved.remembered["params"] == {"about": "cats"}
        assert client.flows.list(here).flow == "@local/tells"

        assert client.flowverses.add(str(team), "team").said == "added team"
        index = client.flowverses.get("team")
        assert [one.flow for one in index.flows] == ["@team/review"]
        assert [each.version for each in index.flows[0].releases] == ["1.1.0", "1.0.0"]
        kept = client.flowverses.install("@team/review", "1.0.0")
        assert [(one.flow, one.version) for one in kept.installed] == [
            ("@team/review", "1.0.0")
        ]
        assert [(one.flow, one.was, one.to) for one in kept.updates] == [
            ("@team/review", "1.0.0", "1.1.0")
        ]
        assert client.flowverses.install("@team/review").updates == ()
        forked = client.flows.fork(here, "@team/review")
        assert forked.at.startswith(here)
        assert client.flowverses.fetch("team").said == "fetched team"
        assert client.flowverses.uninstall("@team/review").installed == ()
        assert [one.name for one in client.flowverses.remove("team").verses] == [
            "official"
        ]
        with pytest.raises(Refused, match="There is no flowverse team") as refused:
            client.flowverses.get("team")
        assert refused.value.code == 404

        added = client.workspaces.add(str(team.parent), here)
        assert added.kept == str(team.parent.resolve())
        assert [one.path for one in added.workspaces] == [here, added.kept]
        assert added.workspaces[0].here
        assert [
            one.path for one in client.workspaces.forget(added.kept).workspaces
        ] == [here]
        assert [one.path for one in client.workspaces.list(here).workspaces] == [here]

        found = client.paths.list(here, hidden=True)
        assert found.whole == here
        assert [(one.name, one.dir) for one in found.entries] == [(".hmz", True)]
        assert client.paths.complete(f"{here}/.h") == [f"{here}/.hmz/"]
