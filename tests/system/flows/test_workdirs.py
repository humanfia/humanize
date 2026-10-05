"""Where an agent's shell starts on a container, for each place its CLI can run.

An agent given an environment works in that environment's workdir: the first command it runs
there is run in the workdir, whether its CLI is here under a supervisor (`local` in its
runtime's affinity) or the image's own (`self`). Asked of a real CLI, because the CLI is what
decides where a command it runs starts -- and asked to write `pwd` into the directory it ran
in, which is only in the workdir if that is where it ran.

Here with humanize's home where the default one is (`home_kept_here`): a container's mirrors
are kept under it, and a home in the system's temporary directory is the one place a mirror
answered as a directory kept here could not be seen.

`self` needs the CLI in the image and a sign-in there, so the image is built out of the CLI
installed here and the turn is run as this machine's account at a gateway, which an anchored
turn sends in for its length. The third place, another runtime, takes a CLI signed in on a
machine of its own -- no account is sent there -- so it is shown with a stand-in for the CLI
in `tests/system/coganchor/test_topologies.py` instead.

Spends real tokens, so it only runs with `pytest --run-agents`.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.machines.fixtures import IMAGE
from tests.matrix import places
from tests.stubs import written

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.agent, pytest.mark.timeout(1200)]

#: The CLIs asked: Claude Code, and one more, each a single native program an image can hold.
CLIS = ("claude", "grok")

#: The account each is run as, kept on this machine and signed in with a key at a gateway.
ACCOUNT = "nvidia"

#: What the agent is asked, so that where its shell started is written down where it started.
ASKED = (
    "Use your shell tool to run exactly this one command in your working directory, then "
    "reply with exactly one word, DONE: pwd > where.txt"
)

FLOW = '''"""One turn of an agent in a container of its own."""

from hmz.flows import (
    Agent,
    AgentCollection,
    Env,
    EnvCollection,
    FlowParams,
    ImageEnvMixin,
    ShellEnvMixin,
    flow,
)


class Box(Env, ShellEnvMixin, ImageEnvMixin):
    _image = "{image}"


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    box: Box


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def boxed(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn()
    return await worker.run(task, session=session, env=envs["box"])
'''


def _image(cli: str, tmp_path: Path) -> str:
    """The base image with the CLI installed here in it, built once per CLI binary."""
    program = Path(os.path.realpath(shutil.which(cli) or ""))
    if not program.is_file():
        pytest.skip(f"{cli} is not installed here")
    with program.open("rb") as handle:
        if handle.read(4) != b"\x7fELF":
            pytest.skip(f"{program} is not one native program an image can hold")
    said = program.stat()
    digest = hashlib.sha256(
        f"{program}\0{said.st_size}\0{said.st_mtime_ns}".encode()
    ).hexdigest()[:12]
    image = f"hmz-workdir-{cli}:{digest}"
    if (
        subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, check=False
        ).returncode
        == 0
    ):
        return image
    context = tmp_path / "image"
    context.mkdir()
    shutil.copy2(program, context / cli)
    (context / "Dockerfile").write_text(
        f"FROM {IMAGE}\nCOPY {cli} /usr/local/bin/{cli}\n"
    )
    built = subprocess.run(
        ["docker", "build", "--quiet", "--tag", image, str(context)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    return image


@pytest.fixture
def account(cli: str, home_kept_here: Path) -> Iterator[str]:
    """The CLI's account, borrowed into the test's home, as `-a` spells an agent of it."""
    del home_kept_here  # asked first, so that the account is borrowed into that home
    place = next(
        (one for one in places.CANDIDATES[cli] if one.provider == ACCOUNT), None
    )
    if place is None:
        pytest.skip(f"no {ACCOUNT} place is written down for {cli}")
    with contextlib.ExitStack() as holding:
        try:
            name = holding.enter_context(places.borrowed(cli, ACCOUNT))
        except LookupError as missing:
            pytest.skip(str(missing))
        yield place.spec(provider=name)


@pytest.mark.parametrize("harness", ["local", "self"])
@pytest.mark.parametrize("cli", CLIS)
def test_an_agents_shell_starts_in_its_environments_workdir(
    cli: str, harness: str, account: str, daemon: None, tmp_path: Path
) -> None:
    from hmz.coganchor.machines import store

    del daemon
    # A docker runtime of the daemon here, saying where an agent's harness on it runs.
    store.add(store.DockerRuntime(name="box", affinity=(harness,)))
    flow = written(
        tmp_path / "flows", "boxed", FLOW.format(image=_image(cli, tmp_path))
    )
    workdir = tmp_path / "work"
    workdir.mkdir()
    ran = subprocess.run(
        [
            sys.executable,
            "-Pm",
            "hmz",
            "exec",
            "-f",
            str(flow),
            "-a",
            f"worker={account}",
            "-e",
            f"box=docker@box{workdir}",
            "-p",
            "budget.duration=10m",
            ASKED,
        ],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )

    said = f"{ran.stdout[-2000:]}\n{ran.stderr[-2000:]}"
    assert ran.returncode == 0, said
    landed = workdir / "where.txt"
    assert landed.is_file(), f"the agent's shell was not in {workdir}\n{said}"
    assert landed.read_text().strip() == str(workdir), said
