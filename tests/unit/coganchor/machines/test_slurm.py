from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl

import pytest

from hmz.coganchor.machines import Slurm, SlurmConfig
from hmz.coganchor.machines.docker import CPUS, GPUS, MEMORY
from hmz.coganchor.machines.slurm import SRUN, TCP, Unplaced, jobs
from hmz.coganchor.places import ISOLATED, MANAGED, REMOTE, SUPERVISED
from hmz.coganchor.transport import Road, Target

if TYPE_CHECKING:
    from tests.unit.coganchor.machines.conftest import Handshake, Runs


def after(argv: list[str], flag: str) -> list[str]:
    return [argv[at + 1] for at, one in enumerate(argv[:-1]) if one == flag]


def queued(
    job: str, state: str, *, reason: str = "None", comment: str = "", node: str = ""
) -> str:
    return f"{job}|{state}|{reason}|{comment or '(null)'}|{node}\n"


def a_cluster(runs: Runs, *states: str, job: str = "42", node: str = "n7") -> None:
    """`sbatch` taking job `job`, and the job going through `states` on `node`."""
    runs.on("sbatch", out=f"{job}\n")
    rule = runs.on("--jobs", job)
    rule.answers = [
        (0, queued(job, one, node=node if one == "RUNNING" else ""), "")
        for one in states
    ]


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    return slept


# ------------------------------------------------------------------------------ config


def test_a_job_is_remote_managed_linux_and_supervised_but_not_isolated() -> None:
    capabilities = SlurmConfig(workspace="/w").capabilities

    assert capabilities == {REMOTE, MANAGED, "linux", SUPERVISED}
    assert ISOLATED not in capabilities


@pytest.mark.parametrize(
    "said",
    [
        {"workspace": "relative"},
        {"workspace": "/w", "python": "python3"},
        {"workspace": "/w", "cpus": 0},
        {"workspace": "/w", "memory": -5},
        {"workspace": "/w", "gpus": -1},
        {"workspace": "/w", "via": "ssh"},
        {"workspace": "/w", "labels": {"a=b": "1"}},
    ],
)
def test_what_sbatch_would_refuse_is_refused_where_it_is_written(
    said: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 -- each says why in its own words
        SlurmConfig(**said)


def test_a_setting_builds_a_machine_holding_no_job(runs: Runs) -> None:
    machine = SlurmConfig(workspace="/w").create()

    assert isinstance(machine, Slurm)
    assert machine.job == ""
    assert machine.token is None
    assert runs.calls == []


# -------------------------------------------------------------------------------- jobs


def test_a_cluster_running_nothing_of_ours_holds_nothing(runs: Runs) -> None:
    runs.on("squeue", "--me", out=queued("1", "RUNNING", comment="someone else's"))

    assert jobs() == []


def test_what_each_job_holds_is_read_off_its_comment(runs: Runs) -> None:
    ours = f"humanize={os.getuid()}&humanize.provider=hpc&{CPUS}=2&{MEMORY}=1024"
    runs.on(
        "squeue",
        "--me",
        out=queued("7", "PENDING", comment=ours)
        + queued("8", "RUNNING", comment=f"{ours}&{GPUS}=gpu%3D1")
        + queued("9", "COMPLETING", comment=ours)
        + queued("10", "RUNNING", comment=f"humanize=1&{CPUS}=two")
        + queued("11", "RUNNING", comment="humanize=1&humanize.provider=other"),
    )

    held = jobs({"humanize.provider": "hpc"})

    assert [(one.name, one.cpus, one.memory, one.gpus) for one in held] == [
        ("7", 2.0, 1024, ()),
        ("8", 2.0, 1024, ("gpu=1",)),
    ]
    assert held[0].labels["humanize.provider"] == "hpc"
    assert [one.name for one in jobs()] == ["7", "8", "10", "11"]
    assert jobs()[2].cpus is None


def test_a_cluster_that_could_not_be_asked_is_an_error(runs: Runs) -> None:
    runs.on("squeue", status=1, err="slurm_load_jobs error")

    with pytest.raises(OSError, match="slurm_load_jobs error"):
        jobs()


def test_a_cluster_that_did_not_answer_in_time_is_an_error(runs: Runs) -> None:
    runs.on("squeue", timeout=True)

    with pytest.raises(OSError, match="did not answer within 5s"):
        jobs(seconds=5)


# ----------------------------------------------------------------------------- a job


def test_a_job_is_submitted_as_asked_and_reached_by_srun(
    runs: Runs, handshake: Handshake
) -> None:
    a_cluster(runs, "PENDING", "RUNNING")
    config = SlurmConfig(
        workspace="/srv/w",
        name="job-name",
        partition="cpu",
        account="team",
        qos="normal",
        time="1:00:00",
        cpus=2,
        memory=(1 << 30) + 1,
        gpus=1,
        constraint="a100",
        python="~/py/bin/python3",
        sbatch_args=("--exclusive",),
        labels={"team": "a", CPUS: "spoofed"},
    )
    machine = config.create()

    anchor = machine.start()

    (made,) = runs.called("sbatch")
    assert after(made, "--job-name") == ["job-name"]
    assert after(made, "--chdir") == ["/srv/w"]
    assert after(made, "--export") == ["HOME,USER"]
    assert after(made, "--output") == [os.devnull]
    assert after(made, "--partition") == ["cpu"]
    assert after(made, "--account") == ["team"]
    assert after(made, "--qos") == ["normal"]
    assert after(made, "--time") == ["1:00:00"]
    assert after(made, "--constraint") == ["a100"]
    assert after(made, "--cpus-per-task") == ["2"]
    assert after(made, "--mem") == ["1025M"]
    assert after(made, "--gpus") == ["1"]
    assert after(made, "--nodes") == after(made, "--ntasks") == ["1"]
    assert made.index("--exclusive") < made.index("--cpus-per-task")
    assert dict(parse_qsl(after(made, "--comment")[0])) == {
        "team": "a",
        "humanize": str(os.getuid()),
        CPUS: "2",
        MEMORY: str((1 << 30) + 1),
        GPUS: "gpu=1",
    }
    assert after(made, "--wrap") == ["exec sleep 2147483647"]
    assert machine.job == "42"
    assert anchor.target == "slurm://42?python=~/py/bin/python3"
    assert anchor.workspace == "/srv/w"
    assert anchor.token is None
    assert handshake.asked == [anchor]


def test_a_job_asking_for_nothing_takes_the_partitions_defaults(
    runs: Runs, handshake: Handshake
) -> None:
    a_cluster(runs, "RUNNING")

    anchor = SlurmConfig(workspace="/w").create().start()

    (made,) = runs.called("sbatch")
    for flag in ("--partition", "--account", "--time", "--cpus-per-task", "--mem"):
        assert flag not in made
    assert anchor.target == "slurm://42"


def test_a_job_reached_over_tcp_runs_the_serving_half_and_is_dialled_with_its_secret(
    runs: Runs, handshake: Handshake
) -> None:
    a_cluster(runs, "RUNNING", node="n7")
    runs.on("/bin/cat").answers = [
        (1, "", "No such file"),
        (0, "hmz internal anchor serve listening 0.0.0.0 40123\n", ""),
    ]
    machine = SlurmConfig(workspace="/w", via=TCP, python="/opt/py").create()

    anchor = machine.start()

    (made,) = runs.called("sbatch")
    script = after(made, "--wrap")[0]
    assert machine.token
    assert f"HUMANIZE_TOKEN={machine.token}" in script
    assert "--listen" in script
    assert "/opt/py" in script
    assert after(made, "--output") == ["/tmp/humanize-slurm-%j.out"]
    assert machine.token not in " ".join(made).replace(script, "")
    (cat, _) = runs.called("/bin/cat")
    assert cat[-1] == "/tmp/humanize-slurm-42.out"
    assert cat[:2] == ["srun", "--jobid=42"]
    assert anchor.target == "tcp://n7:40123"
    assert anchor.token == machine.token
    assert handshake.asked == [anchor]


def test_a_serving_half_that_never_listens_is_an_error_and_its_job_goes(
    runs: Runs, handshake: Handshake, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = iter(range(0, 10_000, 30))
    monkeypatch.setattr(time, "monotonic", lambda: float(next(clock)))
    a_cluster(runs, "RUNNING")
    runs.on("/bin/cat", out="Traceback: no python\n")

    with pytest.raises(RuntimeError, match="did not say it was listening"):
        SlurmConfig(workspace="/w", via=TCP).create().start()
    assert runs.called("scancel", "42")


def test_a_job_waits_in_the_queue_before_running(
    runs: Runs, handshake: Handshake, no_wait: list[float]
) -> None:
    a_cluster(runs, "PENDING", "CONFIGURING", "RUNNING")

    SlurmConfig(workspace="/w").create().start()

    assert len(no_wait) == 2


def test_a_job_is_asked_after_less_and_less_often_while_it_waits(
    runs: Runs, handshake: Handshake, no_wait: list[float]
) -> None:
    a_cluster(runs, *["PENDING"] * 7, "RUNNING")

    SlurmConfig(workspace="/w").create().start()

    assert no_wait == [1, 2, 4, 8, 10, 10, 10]


def test_a_controller_that_did_not_answer_is_asked_again(
    runs: Runs, handshake: Handshake
) -> None:
    runs.on("sbatch", out="42\n")
    runs.on("--jobs", "42").answers = [
        (1, "", "slurm_load_jobs error: Socket timed out on send/recv operation"),
        (0, queued("42", "RUNNING", node="n1"), ""),
    ]

    anchor = SlurmConfig(workspace="/w").create().start()

    assert anchor.target == "slurm://42"


def test_a_job_the_controller_no_longer_has_is_gone(
    runs: Runs, handshake: Handshake
) -> None:
    runs.on("sbatch", out="42\n")
    runs.on(
        "--jobs", "42", status=1, err="slurm_load_jobs error: Invalid job id specified"
    )

    with pytest.raises(RuntimeError, match="is gone before it ran"):
        SlurmConfig(workspace="/w").create().start()


def test_a_job_no_node_took_in_time_is_unplaced_and_cancelled(
    runs: Runs, handshake: Handshake
) -> None:
    runs.on("sbatch", out="42\n")
    runs.on("--jobs", "42", out=queued("42", "PENDING", reason="Resources"))

    with pytest.raises(Unplaced, match="pending for Resources"):
        SlurmConfig(workspace="/w", placing=0).create().start()
    assert runs.called("scancel", "42")
    assert handshake.asked == []


@pytest.mark.parametrize(
    ("said", "match"),
    [
        (queued("42", "FAILED", reason="NonZeroExitCode"), "is failed before it ran"),
        ("", "is gone before it ran"),
    ],
)
def test_a_job_that_ended_before_it_ran_is_an_error_and_cancelled(
    runs: Runs, handshake: Handshake, said: str, match: str
) -> None:
    runs.on("sbatch", out="42\n")
    runs.on("--jobs", "42", out=said)

    with pytest.raises(RuntimeError, match=match):
        SlurmConfig(workspace="/w").create().start()
    assert runs.called("scancel", "42")


def test_a_job_that_could_not_be_submitted_says_why(
    runs: Runs, handshake: Handshake
) -> None:
    runs.on("sbatch", status=1, err="Invalid account or account/partition combination")

    with pytest.raises(RuntimeError, match="Invalid account"):
        SlurmConfig(workspace="/w").create().start()
    assert runs.called("scancel") == []


def test_no_sbatch_here_submits_nothing(runs: Runs) -> None:
    runs.absent.add("sbatch")

    with pytest.raises(FileNotFoundError, match="no sbatch"):
        SlurmConfig(workspace="/w").create().start()
    assert runs.calls == []


def test_a_job_submitted_alone_is_not_waited_for_and_is_submitted_once(
    runs: Runs, handshake: Handshake
) -> None:
    a_cluster(runs, "RUNNING")
    machine = SlurmConfig(workspace="/w").create()

    assert machine.submit() == "42"
    assert runs.called("squeue") == []
    machine.start()

    assert len(runs.called("sbatch")) == 1


def test_a_node_that_is_not_what_was_promised_is_given_back(
    runs: Runs, handshake: Handshake
) -> None:
    a_cluster(runs, "RUNNING")
    handshake.platform = "darwin"

    with pytest.raises(RuntimeError, match="cannot serve linux"):
        SlurmConfig(workspace="/w").create().start()
    assert runs.called("scancel", "42")


def test_a_node_without_the_workspace_is_given_back(
    runs: Runs, handshake: Handshake
) -> None:
    a_cluster(runs, "RUNNING")
    handshake.fails = FileNotFoundError("/w")

    with pytest.raises(OSError, match="/w"):
        SlurmConfig(workspace="/w").create().start()
    assert runs.called("scancel", "42")


def test_stopping_cancels_the_job_once(runs: Runs, handshake: Handshake) -> None:
    a_cluster(runs, "RUNNING")
    machine = SlurmConfig(workspace="/w").create()
    machine.start()

    machine.stop()
    machine.stop()

    assert runs.called("scancel") == [["scancel", "42"]]
    assert machine.job == ""


def test_the_road_to_a_job_is_a_step_of_it_reached_by_srun() -> None:
    road = Road.to(Target.parse("slurm://42"))

    assert road.line(["hostname"])[:2] == ["srun", "--jobid=42"]
    assert road.line(["hostname"])[-1] == "hostname"
    assert SRUN in road.prefix[0]
