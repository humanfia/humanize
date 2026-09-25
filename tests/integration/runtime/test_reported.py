"""What a report of humanize's own failure says of the run that was going when it happened.

`telemetry.SENT` promises a report says which flow was running and what each of its agents was
set up to run, and nothing a person typed: this is that promise held to a run on the engine's
fakes, a flow calling a flow, asked mid-run exactly as a report being made would ask it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from hmz.runtime import telemetry
from hmz.runtime.flowing.fakes import FakeAgentDriver
from hmz.runtime.runner import Runner
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

#: A flow that calls another, which reads what a report would say while both are going.
FLOW = """
from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, Permission,
    PermissionKind, flow,
)
from hmz.runtime import telemetry

SEEN = []


class Reader(Agent):
    _permission = Permission(online=PermissionKind.ALL)
    _skills = ()


class Agents(AgentCollection):
    reader: Reader


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, hidden=True)
async def inner(task, *, agents, envs, params, ctx):
    SEEN.append(telemetry.held()["flow"])


@flow(agents=Agents, envs=Envs, params=FlowParams, name="flow")
async def outer(task, *, agents, envs, params, ctx):
    await inner("a secret task", agents=agents, envs=envs, params=params)
    return SEEN
"""


def test_a_report_says_which_flows_were_going_and_what_each_role_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", FLOW)
    driver = FakeAgentDriver(model="m", effort="high", provider="work")

    (said,) = Runner(
        tmp_path / "flow", agents={"reader": driver}, budget={"cost": 1}
    ).run("a secret task")

    about = cast("dict[str, Any]", said)
    assert about["flow"] == "flow:flow"
    assert about["calls"] == 2
    assert [(one["flow"], one["deep"], one["under"]) for one in about["running"]] == [
        ("flow:flow", 1, ""),
        ("flow:inner", 2, "flow:flow"),
    ]
    assert about["agents"] == [
        {
            "flow": "flow:flow",
            "called": "reader",
            "cli": "claude",
            "model": "m",
            "effort": "high",
            "account": "work",
            "may": "local=all user=read system=read online=all",
            "skills": [],
        }
    ]
    # What the flow was asked to do is nowhere in it.
    assert "secret" not in repr(about)
    # And once the run is over, nothing of it is left to say.
    assert telemetry.held()["flow"] == {
        "flow": "",
        "calls": 0,
        "running": [],
        "agents": [],
    }
