"""What the machine system tests share: one coding task, set on a machine an `-e` names.

Each test runs the same flow -- one agent, one environment -- with the environment on another
machine: a docker container, a swarm task, an Apple container or a host reached over ssh. A
container holds no CLI and no sign-in: the agent's CLI is supervised here, signed in as it is
on this machine, and every command it runs lands in the container. The flow then asks the
machine what it is and, in a container, for any sign-in file anywhere in it; whether the task
was done is read back here, in the workspace the machine was given.

Supervising a CLI takes ptrace and Landlock, which is Linux: :func:`supervisable` skips the
container tests elsewhere. On a Mac humanize would run a CLI found in the container natively
instead, which is signed in only under a humanize account, never with this machine's own.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from hmz.flows import HarnessRefused, HarnessThrottled, ModelUnavailable
from hmz.runtime.flowing.environing_docker import IMAGE
from hmz.sdk import Hmz
from tests.system.doubles_flows import CHEAPEST, COST, MINUTES, TASK, harness

if TYPE_CHECKING:
    from pathlib import Path

#: The files the CLIs keep a sign-in that refreshes itself in, wherever their home is put.
SIGN_INS = ("auth.json", ".credentials.json")

#: What the flow asks the machine once the turn is over: its kernel and name, whether it was
#: reached over ssh, and in a container, every sign-in file holding a refresh token anywhere
#: in it -- a lent one goes in a directory of the turn's own, not the home -- but under the
#: workspace, which is this machine's and which the suite's own check reads.
_SEEN = 'uname -s; hostname; echo "ssh=${SSH_CONNECTION:+yes}"'
_FOUND = (
    "; find / \\( -path /proc -o -path /sys -o -path {workspace} \\) -prune -o \\( "
    + " -o ".join(f"-name {one}" for one in SIGN_INS)
    + " \\) -type f -exec grep -liE 'refresh_?token' {{}} + 2>/dev/null; true"
)

#: The flow, with the environment's mixins and body left to fill.
_FLOW = """
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowParams, flow
from hmz.flows import ImageEnvMixin, ShellEnvMixin


class Box(Env, ShellEnvMixin{mixins}):
    {box}


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    box: Box


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def boxed(task, *, agents, envs, params, ctx):
    box = envs["box"]
    coder = agents["coder"]
    session = await coder.spawn()
    await coder.run(task, session=session, env=box)
    status, seen, err = await box.exec(["sh", "-c", {seen!r}], timeout=300)
    assert status == 0, err
    return seen
"""


@dataclass(frozen=True)
class Seen:
    """What the machine said of itself once the agent's turn was over.

    Attributes:
      kernel: `uname -s` there.
      hostname: Its host name.
      ssh: Whether the commands run there came over an ssh connection.
      sign_ins: Every sign-in file found in it, in a container; nothing looked for elsewhere.
    """

    kernel: str
    hostname: str
    ssh: bool
    sign_ins: tuple[str, ...]


def hmz(at: Path) -> Hmz:
    """Humanize, run from a directory of its own beside the workspace."""
    at.mkdir(parents=True, exist_ok=True)
    return Hmz(at)


def _agents() -> list[str]:
    """The `-a` of every signed-in CLI here, each on its cheapest model, or a skip."""
    found: list[str] = []
    missing: list[str] = []
    for cli, _ in CHEAPEST:
        try:
            found.append(f"coder={harness(cli)}")
        except pytest.skip.Exception as why:
            missing.append(str(why))
    if not found:
        pytest.skip("; ".join(missing))
    return found


def _git(workspace: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv], cwd=workspace, capture_output=True, text=True, check=True
    ).stdout


def run(tmp_path: Path, workspace: Path, env: str) -> Seen:
    """Runs the task once, its agent working in the environment `env` names.

    The next CLI is tried, on a workspace put back as it was, where one's account will not
    take the turn or its model is not served to it.

    Args:
      tmp_path: The test's own directory, where the flow and the run's own directory go.
      workspace: The workspace, which `env` is a machine's view of.
      env: The `-e` after `box=`: a container, started from :data:`IMAGE`, but for `ssh@`.

    Returns:
      What the machine said of itself after the turn.
    """
    image = not env.startswith("ssh@")
    flow = tmp_path / "flows" / "boxed"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(
        _FLOW.format(
            mixins=", ImageEnvMixin" if image else "",
            box=f"_image = {IMAGE!r}" if image else "pass",
            seen=_SEEN + (_FOUND.format(workspace=workspace) if image else ""),
        )
    )
    budget = f"budget.cost={COST},budget.duration={MINUTES * 60}"
    refused: list[str] = []
    for one in _agents():
        try:
            said = hmz(tmp_path / "here").exec(
                ["-f", str(flow), "-a", one, "-e", f"box={env}", "-p", budget, TASK]
            )
            break
        except (HarnessThrottled, HarnessRefused, ModelUnavailable) as spent:
            refused.append(f"{one}: {spent}")
            _git(workspace, "reset", "-q", "--hard")
            _git(workspace, "clean", "-q", "-fdx")
    else:
        pytest.skip(f"no account here would take the turn: {'; '.join(refused)}")
    lines = str(said).splitlines()
    assert len(lines) >= 3, f"the machine said: {said!r}"
    kernel, hostname, ssh, *found = lines
    return Seen(kernel, hostname, ssh == "ssh=yes", tuple(filter(None, found)))


def done(workspace: Path) -> None:
    """Fails unless the task was done in `workspace`: its tests pass, only `stats.py` changed."""
    tested = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        cwd=workspace,
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")},
        check=False,
        timeout=300,
    )
    assert tested.returncode == 0, tested.stdout[-4000:] + tested.stderr[-2000:]
    assert _git(workspace, "diff", "--name-only").split() == ["stats.py"]


def contained(seen: Seen) -> None:
    """Fails unless `seen` is a container's: not this machine, and holding no sign-in."""
    assert seen.kernel == "Linux", seen
    assert seen.hostname != os.uname().nodename, seen
    assert seen.sign_ins == (), f"a sign-in was left in the container: {seen.sign_ins}"


def supervisable() -> None:
    """Skips where an agent cannot be supervised here with its commands landing elsewhere."""
    if sys.platform != "linux":
        pytest.skip(
            "an agent working in a container is supervised on this machine, which takes "
            f"Linux (ptrace and Landlock), not {sys.platform}"
        )


def answers(*argv: str) -> str:
    """Why `argv` fails here, or "" where it succeeds."""
    try:
        said = subprocess.run(
            argv, capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    if said.returncode:
        return said.stderr.strip() or f"exit {said.returncode}"
    return ""
