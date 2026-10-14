"""A session kept on a container's work, carried on by a later run: its CLI runs here.

Each run is a real `python -m hmz exec` whose one environment is a docker container -- the
fake `docker`, which runs what it is sent on this machine, on a saved runtime whose harness
setting is `local`: the stand-in `claude` runs here, in a mirror of the container's work that
each run makes for itself, and keeping its conversations where one working here does. The
stand-in resumes a conversation only from where Claude keeps one for the directory it is
started in, so the later run's session goes on only where the kept copy was brought in where
that run keeps its sessions and carried into its own mirror.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines import store
from hmz.coganchor.providers import redirect
from tests.integration.doubles_anchor import fakes
from tests.integration.doubles_core import AGENT, hmz_exec, install, started, write_flow

if TYPE_CHECKING:
    import subprocess

#: A flow that keeps its session in its state after a turn on its one environment; a run
#: picking it up carries the session on there.
REMEMBERS = """
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowParams, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    there: Env


class Params(FlowParams):
    step: str = "keep"


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def remembers(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    if params.step == "keep":
        session = await worker.spawn()
        said = await worker.run("the word is papaya", session=session, env=envs["there"])
        ctx.state["boundary"] = session
        return said
    again = ctx.state["boundary"]
    return await worker.run(f"{params.step}: what was the word?", session=again, env=envs["there"])
"""

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not redirect.supervises(),
    reason="a CLI here working on another machine's mirror is supervised, on linux alone",
)


def _remembers(
    tmp_path: Path, work: Path, *argv: str
) -> subprocess.CompletedProcess[str]:
    return hmz_exec(
        "-f",
        str(tmp_path / "flows" / "remembers"),
        "-a",
        f"worker={AGENT}",
        "-e",
        f"there=docker@here{work}",
        "-p",
        "budget.cost=1",
        *argv,
        "go",
    )


def _said(ran: subprocess.CompletedProcess[str]) -> str:
    assert ran.returncode == 0, ran.stderr
    return ran.stdout.strip().splitlines()[-1]


def test_a_session_kept_on_another_machines_work_is_carried_on_by_a_cli_run_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(tmp_path, monkeypatch)
    store.write(store.new(store.DOCKER, "here", harness=store.HERE))
    far = fakes(tmp_path, monkeypatch)
    far.answer(
        "info", json.dumps({"ServerVersion": "27.0", "NCPU": 8, "MemTotal": 16 << 30})
    )
    write_flow(tmp_path / "flows", "remembers", REMEMBERS)
    work = tmp_path / "work"
    work.mkdir()

    _said(_remembers(tmp_path, work))
    (told,) = started(tmp_path)
    assert told["cwd"] != str(work), "run here, in a mirror of the container's work"

    said = _said(_remembers(tmp_path, work, "-p", "step=continue", "--resume"))

    assert said == "did: continue: what was the word?"
    _, carried = started(tmp_path)
    argv = carried["argv"]
    assert argv[argv.index("--resume") + 1] == told["session"]
    assert "--fork-session" in argv
    # The later run's own mirror of the same work, where nothing of the earlier one's was.
    assert carried["cwd"] != told["cwd"]
    assert Path(carried["cwd"]).name == Path(told["cwd"]).name
    assert carried["session"] != told["session"]
