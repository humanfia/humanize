"""Codex with its harness on a machine other than the one it was told to work at.

A harness elsewhere keeps its mirror under that machine's own mirror cache, and the driver
here tells Codex where to work by the workspace's own path -- `thread/start` takes a `cwd`, and
nothing here can know where a machine it has not reached yet put its mirror. Every command of
such a turn used to fail `Failed to create unified exec process: No such file or directory`:
Codex starts a shell in that `cwd`, and the harness's machine has no such directory. Only the
real CLI can say it now starts them, and only a real anchor that the command then lands where
the work is.

As `-H standalone` has it: the harness in one container, the work in another, which needs a
docker daemon and an image this suite builds out of the Codex installed here.

Costs tokens and needs network access, so it only runs with ``pytest --run-agents``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.agents import CodexAgent, CodexAgentConfig, Failed
from hmz.coganchor.machines import AnchoredConfig
from hmz.runtime.flowing.environing_docker import TRACING
from tests.machines.fixtures import IMAGE
from tests.supervising import traced

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [
    pytest.mark.agent,
    traced,
    pytest.mark.timeout(900),
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed"),
]

#: What the agent is asked to run: a read of the workspace, a write to it, and where it ran.
ASKED = (
    "Use your shell tool to run exactly this one command in your working directory and "
    "show its output: cat hello.txt; hostname > where.txt; echo x > made.txt; "
    "echo WROTE=$?   Then reply DONE."
)

#: What the containers are labelled with, so that a run killed outright leaves something
#: anybody can sweep up by name.
LABEL = "humanize-codex-afar"


def _turn(anchor: AnchorConfig) -> str:
    """One turn of Codex under this anchor, granted everything, and what it said."""
    agent = CodexAgent(
        CodexAgentConfig(
            model="gpt-5.5",
            effort="low",
            permission="bypass",
            machine=AnchoredConfig(anchor=anchor),
        )
    )
    try:
        said = list(agent.new().stream(ASKED))
    except Failed as why:
        # Signed in, as the caller made sure: a turn that fails is what this is here to see.
        pytest.fail(f"codex would not take a turn: {why}")
    finally:
        agent.stop()
    return " ".join(one.text for one in said)


def _docker(*argv: str) -> str:
    """One docker command, with what it said, for a test that needs it to have worked."""
    done = subprocess.run(
        ["docker", *argv], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, f"docker {' '.join(argv)}: {done.stderr.strip()}"
    return done.stdout.strip()


def _codex_image(tmp_path: Path) -> str:
    """An image of the base one with the Codex installed here in it, built once per Codex.

    Its whole package where it is one -- the standalone install keeps the code-mode host, a
    `ripgrep` and a `bwrap` beside the binary -- and the binary and its code-mode host
    otherwise. Named for every file it holds, so a Codex updated in place is built again.
    """
    program = Path(os.path.realpath(shutil.which("codex") or ""))
    with program.open("rb") as handle:
        if handle.read(4) != b"\x7fELF":
            pytest.skip(f"{program} is not a native Codex this test can put in an image")
    package = program.parent.parent
    if (package / "codex-package.json").is_file():
        files = [one for one in package.rglob("*") if one.is_file()]
    else:
        package = program.parent
        host = package / "codex-code-mode-host"
        files = [program, *([host] if host.is_file() else [])]
    digest = hashlib.sha256()
    for one in sorted(files):
        said = one.stat()
        digest.update(f"{one}\0{said.st_size}\0{said.st_mtime_ns}\0".encode())
    image = f"hmz-codex-afar:{digest.hexdigest()[:12]}"
    if (
        subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, check=False
        ).returncode
        == 0
    ):
        return image
    context = tmp_path / "image"
    for one in files:
        placed = context / "codex" / one.relative_to(package)
        placed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(one, placed)
    (context / "Dockerfile").write_text(
        f"FROM {IMAGE}\n"
        "COPY codex /opt/codex\n"
        f"RUN ln -s /opt/codex/{program.relative_to(package)} /usr/local/bin/codex\n"
    )
    _docker("build", "--quiet", "--tag", image, str(context))
    return image


@pytest.fixture
def containers(daemon: None) -> Iterator[list[str]]:
    """The names of the containers a test starts, every one of them taken down after it."""
    del daemon
    made: list[str] = []
    try:
        yield made
    finally:
        for name in made:
            subprocess.run(
                ["docker", "rm", "--force", name], capture_output=True, check=False
            )


def _machine(
    made: list[str], image: str, *mounted: str, env: str = "", given: tuple[str, ...] = ()
) -> str:
    """One container, idling as this user, holding each directory at the path it has here.

    With a home it may write to, which a user the image has no entry for has not got: `/`,
    where the serving half's cache cannot be made. As humanize's own containers are.
    """
    name = f"hmz-{uuid.uuid4().hex[:10]}"
    mounts = [f"--volume={path}:{path}" for path in mounted]
    _docker(
        "run",
        "--detach",
        f"--name={name}",
        f"--hostname={name}",
        f"--label={LABEL}={os.getuid()}",
        f"--user={os.getuid()}:{os.getgid()}",
        *mounts,
        "--env=HOME=/tmp",
        *([f"--env={env}"] if env else []),
        *given,
        image,
        "sleep",
        "infinity",
    )
    made.append(name)
    return name


def test_codex_with_its_harness_in_one_container_runs_commands_in_another(
    tmp_path: Path, containers: list[str]
) -> None:
    """`-H standalone`: the harness in a container of its own, the work in another.

    Signed in with a copy of this machine's own sign-in, in a directory of the test's, so the
    one Codex here is using is never written to by the one in the container.
    """
    signed = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"
    if not signed.is_file():
        pytest.skip("codex is not signed in with a file this test can copy")
    image = _codex_image(tmp_path)
    home = tmp_path / "codex-home"
    home.mkdir(mode=0o700)
    shutil.copy2(signed, home / "auth.json")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("HELLO-FROM-THE-TARGET\n")
    # Given what humanize gives the container of a standalone harness.
    harness = _machine(
        containers, image, str(home), env=f"CODEX_HOME={home}", given=TRACING
    )
    work = _machine(containers, IMAGE, str(workspace))

    heard = _turn(
        AnchorConfig(
            harness=f"docker://{harness}",
            target=f"docker://{work}",
            workspace=str(workspace),
        )
    )

    assert "unified exec" not in heard, heard
    assert "HELLO-FROM-THE-TARGET" in heard, heard
    assert (workspace / "made.txt").read_text() == "x\n", heard
    # The command ran where the work is, the harness being the thing that supervises it.
    assert (workspace / "where.txt").read_text().strip() == work, heard
