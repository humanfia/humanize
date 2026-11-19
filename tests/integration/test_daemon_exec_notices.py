"""Notices of epics run on exec hosts, which go as soon as their epic has ended.

Each run here is a real `python -m hmz exec` against a daemon of the test's own, in this
process, which asks its own hosts how they stand as this machine's daemon does. The host of an
`hmz exec` is gone by the time anybody next looks: what it said as it went is what its notice
is made of.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from hmz.daemon import routing
from hmz.daemon.api import notices
from tests.integration.doubles_core import hmz_exec, write_flow

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.daemon.private import Private

#: A flow of no agents, which ends done, or failed where its task says to.
QUICK = """
from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def quick(task, *, agents, envs, params, ctx):
    if task.startswith("fail"):
        raise RuntimeError("it broke")
    return "ok " + task
"""


@pytest.mark.parametrize(
    ("task", "status", "kind"), [("win", 0, "done"), ("fail it", 1, "failed")]
)
def test_an_epic_of_hmz_exec_is_noticed_though_its_host_went_as_it_ended(
    task: str,
    status: int,
    kind: str,
    daemon: Private,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(routing, "serving", daemon)
    flow = write_flow(tmp_path, "quick", QUICK)
    watched = notices.watched()
    watched.look()
    before = watched.last

    ran = hmz_exec("-f", flow, "-p", "budget.cost=1", task)

    assert ran.returncode == status, ran.stderr
    # Its host goes once it sees itself idle, a moment after: nobody is left to ask.
    until = time.monotonic() + 10
    while daemon.hosts.listed() and time.monotonic() < until:
        time.sleep(0.05)
    assert daemon.hosts.listed() == []
    watched.look()
    (made,) = watched.since(before)
    assert made["kind"] == kind
    assert made["slot"].startswith("exec:")
    assert made["task"] == task
    assert made["workspace"] == str(tmp_path.resolve())
    watched.look()
    assert len(watched.since(before)) == 1
