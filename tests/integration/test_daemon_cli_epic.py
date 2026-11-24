"""`hmz epic` and `hmz hosts`, asked of a real daemon: an epic started, steered and closed."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli
from hmz.sdk import Client, Refused
from tests.integration.doubles_daemon import (
    ASKS,
    REVIEWS,
    WAITS,
    hosting,
    project,
    until,
    written,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [pytest.mark.timeout(120)]

BUDGET = ("-p", "budget.cost=1")


@pytest.fixture(autouse=True)
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    for name, source in (("asks", ASKS), ("waits", WAITS), ("reviews", REVIEWS)):
        written(at, name, source)
    with hosting():
        yield at


def _json(capsys: pytest.CaptureFixture[str], *line: str) -> Any:
    """What a command answers under `--json`, whatever it exits with."""
    capsys.readouterr()
    cli.main([*line, "--json"])
    return json.loads(capsys.readouterr().out)


def _asking(capsys: pytest.CaptureFixture[str], *where: str) -> list[str]:
    said = _json(capsys, "epic", "status", *where)
    return [one["question"] for one in said.get("pending") or ()]


def test_an_epic_is_started_answered_and_runs_to_its_end(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    started = _json(capsys, "epic", "start", "./asks", "the thing", *BUDGET)
    assert (started["run"], started["slot"]) == (1, "")

    assert until(lambda: _asking(capsys) == ["q1"])
    status = _json(capsys, "epic", "status")
    assert (status["state"], status["flow"], status["task"]) == (
        "running",
        "./asks",
        "the thing",
    )
    assert status["pending"][0]["role"] == "planner"
    (host,) = _json(capsys, "hosts", "list", "--running")["hosts"]
    assert (host["workspace"], host["asking"]) == (started["workspace"], ["1:q1"])

    assert cli.main(["epic", "answer", "plan A"]) == 0
    assert until(lambda: _asking(capsys) == ["q2"])
    assert cli.main(["epic", "answer", "-q", "q9", "no"]) == 1
    assert "no question q9 is waiting" in capsys.readouterr().err
    assert cli.main(["epic", "answer", "-q", "q2", "--value", '"fine"']) == 0

    assert until((workspace / "result.json").exists)
    assert json.loads((workspace / "result.json").read_text()) == {
        "plan": "plan A",
        "review": "fine",
    }


def test_an_epic_followed_from_its_start_is_written_until_it_is_stopped(
    capsys: pytest.CaptureFixture[str],
) -> None:
    line = ["epic", "start", "./waits", "wait", *BUDGET, "--follow", "--json"]
    # In a process of its own, as it is typed: it holds its standard output to its end.
    following = subprocess.Popen(
        [sys.executable, "-m", "hmz", *line],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert until(lambda: _json(capsys, "epic", "status").get("state") == "running")
        assert cli.main(["epic", "say", "hello"]) == 0
        assert cli.main(["epic", "afk", "reviewer"]) == 0
        assert cli.main(["epic", "afk", "--back"]) == 0
        assert cli.main(["epic", "board"]) == 0
        assert cli.main(["epic", "board", "key", "value"]) == 1
        assert "this run has no board" in capsys.readouterr().err
        assert cli.main(["epic", "stop"]) == 0
        out, err = following.communicate(timeout=60)
    finally:
        following.kill()
    said = [json.loads(one) for one in out.splitlines()]
    assert (following.returncode, err) == (0, "")
    assert (said[0]["run"], said[0]["slot"]) == (1, "")
    kinds = [one.get("type") for one in said[1:]]
    assert kinds[0] == "welcome"
    assert kinds.index("live") < kinds.index("started") < kinds.index("stopping")
    assert (kinds[-1], said[-1]["how"]) == ("ended", "stopped")


def test_an_answer_that_does_not_fit_is_refused_and_the_question_stays(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    started = _json(
        capsys, "epic", "start", "./reviews", "the change", *BUDGET, "--slot", "exec:"
    )
    where = ("--slot", started["slot"])
    assert started["slot"].startswith("exec:")
    assert until(lambda: _asking(capsys, *where) == ["q1"])

    refused = _json(capsys, "epic", "answer", *where, "--value", '{"verdict": "maybe"}')
    assert refused["error"]["code"] == 400
    assert refused["error"]["message"].startswith("the answer does not fit")
    assert _asking(capsys, *where) == ["q1"]

    assert cli.main(["epic", "answer", *where, '{"verdict": "approve"}']) == 0
    assert until((workspace / "result.json").exists)


def test_a_role_another_frontend_claims_is_released_and_then_answered(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["epic", "start", "./asks", "it", *BUDGET]) == 0
    assert until(lambda: _asking(capsys) == ["q1"])

    with (
        Client.local(name="holder") as client,
        client.epics.attach(str(workspace.resolve()), replay=False) as holder,
    ):
        holder.claim("planner")

        assert cli.main(["epic", "answer", "mine"]) == 1
        assert "planner is holder's" in capsys.readouterr().err

        assert cli.main(["epic", "release", "planner"]) == 0
        with pytest.raises(Refused, match="planner is not yours to release"):
            holder.release("planner")
        assert cli.main(["epic", "answer", "mine"]) == 0
        # What the frontend still attached was told of it.
        answered = next(one for one in holder if one["type"] == "answered")
        assert (answered["question"], answered["text"]) == ("q1", "mine")

    assert cli.main(["epic", "stop", "--force"]) == 0


def test_a_host_is_listed_while_it_is_held_and_closed_by_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _json(capsys, "hosts", "list") == {"hosts": []}
    assert cli.main(["epic", "status"]) == 1
    assert "no runs are held in" in capsys.readouterr().err

    started = _json(capsys, "epic", "start", "./waits", "wait", *BUDGET)
    assert until(lambda: _json(capsys, "epic", "status").get("state") == "running")
    (host,) = _json(capsys, "hosts", "list")["hosts"]
    assert (host["workspace"], host["slot"], host["kind"], host["flow"]) == (
        started["workspace"],
        "",
        "flow",
        "./waits",
    )

    assert cli.main(["hosts", "stop"]) == 0
    assert until(lambda: _json(capsys, "hosts", "list") == {"hosts": []})
    assert cli.main(["hosts", "stop"]) == 1


def test_what_cannot_start_is_refused_in_the_daemons_words(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No host is held yet, and steering one does not start it.
    assert cli.main(["epic", "stop"]) == 1
    assert "no runs are held in" in capsys.readouterr().err
    assert _json(capsys, "hosts", "list") == {"hosts": []}

    assert cli.main(["epic", "start", "./waits", "wait", "--away"]) == 1
    assert "requires a budget" in capsys.readouterr().err


def test_the_same_is_asked_through_the_sdk(workspace: Path) -> None:
    at = str(workspace.resolve())
    with Client.local() as client:
        assert client.hosts.list() == []
        with client.epics.attach(at, slot="exec:", replay=False) as epic:
            started = epic.start("./asks", "it", budget={"cost": 1})
            assert (started.slot, started.workspace) == (epic.slot, at)
            for said in epic:
                if said["type"] == "asked":
                    epic.answer(said["question"], f"{said['role']} says yes")
                if said["type"] == "ended":
                    assert said["how"] == "done"
                    break
            assert epic.status()["ended"]["how"] == "done"
            assert [one.slot for one in client.hosts.list()] == [epic.slot]
            assert client.hosts.status(at, epic.slot)["attached"] == 1
            assert client.hosts.detach(at, epic.slot) == 1
            assert [one["type"] for one in epic][-1] == "gone"
        client.hosts.stop(at, started.slot)
        with pytest.raises(Refused, match="no runs are held"):
            client.hosts.status(at, "exec:00")
    assert json.loads((workspace / "result.json").read_text()) == {
        "plan": "planner says yes",
        "review": "reviewer says yes",
    }
