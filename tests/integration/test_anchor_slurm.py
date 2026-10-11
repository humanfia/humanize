"""A job of a Slurm cluster held for the agent, reached by `srun` or over TCP, end to end.

Against the fake `sbatch`, `squeue`, `scancel` and `srun` in `doubles_anchor`, whose one node
is this machine: the job really runs here, the serving half's archive is really put in the far
home and the serving half really answers -- down an `srun` per connection, or listening for
connections that present the job's secret.
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig, transport
from hmz.coganchor.machines import Mapped, SlurmConfig
from hmz.coganchor.machines.slurm import TCP, jobs
from hmz.coganchor.remote import RemoteClient
from tests.integration.doubles_anchor import Fakes, slurm

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="a job's node is linux, which this machine is not"
)


@pytest.fixture
def cluster(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    return slurm(tmp_path, monkeypatch)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    held = tmp_path / "project"
    held.mkdir()
    (held / "a.txt").write_text("a")
    return held


def _gone(within: float = 10.0) -> bool:
    began = time.monotonic()
    while time.monotonic() - began < within:
        if not jobs():
            return True
        time.sleep(0.1)
    return False


def _config(workspace: Path, via: str = "srun") -> SlurmConfig:
    return SlurmConfig(
        workspace=str(workspace),
        partition="cpu",
        cpus=2,
        memory=1 << 30,
        python=sys.executable,
        via=via,
        labels={"humanize.provider": "hpc"},
    )


def test_a_job_is_submitted_reached_by_srun_and_cancelled(
    cluster: Fakes, workspace: Path
) -> None:
    machine = _config(workspace).create()

    anchor = machine.start()
    job = machine.job
    try:
        assert anchor.target == f"slurm://{job}?python={sys.executable}"
        (held,) = jobs({"humanize.provider": "hpc"})
        assert (held.name, held.cpus, held.memory) == (machine.job, 2.0, 1 << 30)
        with Mapped(anchor) as there:
            ran = there.run(["/bin/sh", "-c", "echo made > b.txt; cat a.txt"])
        assert ran.ok
        assert ran.output == "a"
        assert (workspace / "b.txt").read_text() == "made\n"
        assert any(
            argv[:2] == [f"--jobid={job}", "--overlap"]
            for argv in cluster.calls("srun")
        )
        (submitted,) = cluster.calls("sbatch")
        assert submitted[submitted.index("--partition") + 1] == "cpu"
        assert submitted[submitted.index("--wrap") + 1] == "exec sleep 2147483647"
    finally:
        machine.stop()

    assert _gone()
    assert cluster.calls("scancel") == [[job]]


def test_a_job_reached_over_tcp_serves_every_connection_that_has_its_secret(
    cluster: Fakes, workspace: Path
) -> None:
    machine = _config(workspace, via=TCP).create()

    anchor = machine.start()
    try:
        assert anchor.target.startswith("tcp://localhost:")
        assert anchor.token
        for one in range(
            3
        ):  # one listener, many connections, and no `srun` held for any
            with Mapped(anchor) as there:
                assert there.run(["/bin/sh", "-c", f"echo {one} > c{one}.txt"]).ok
        assert sorted(one.name for one in workspace.glob("c*.txt")) == [
            "c0.txt",
            "c1.txt",
            "c2.txt",
        ]
        srun = len(cluster.calls("srun"))
        with Mapped(anchor) as there:
            there.run(["/bin/true"])
        assert len(cluster.calls("srun")) == srun

        forged = AnchorConfig(
            target=anchor.target, workspace=anchor.workspace, token="forged"
        )
        link = transport.connect(transport.Target.parse(forged.target), ["/"])
        try:
            with pytest.raises(Exception, match="token"):
                RemoteClient(link.channel).start("forged")
        finally:
            link.close()
    finally:
        machine.stop()

    assert _gone()


def test_a_job_whose_node_lacks_the_workspace_is_refused_and_cancelled(
    cluster: Fakes, tmp_path: Path
) -> None:
    machine = _config(tmp_path / "nowhere").create()

    with pytest.raises(OSError, match="nowhere"):
        machine.start()

    assert _gone()
    assert list((tmp_path / "fake-slurm").iterdir())
