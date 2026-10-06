from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor.machines import (
    Allocation,
    Docker,
    DockerConfig,
    allocations,
    gpus_listed,
    gpus_usable,
    info,
)
from hmz.coganchor.machines.docker import CPUS, GPUS, MEMORY, bound, whose
from hmz.coganchor.places import ISOLATED, MANAGED, REMOTE, SUPERVISED
from hmz.coganchor.transport import Endpoint

if TYPE_CHECKING:
    from tests.unit.coganchor.machines.conftest import Handshake, Runs

ME = f"{os.getuid()}:{os.getgid()}"


def after(argv: list[str], flag: str) -> list[str]:
    """Every value `flag` is given in `argv`."""
    return [argv[at + 1] for at, one in enumerate(argv[:-1]) if one == flag]


def cidfile(cid: str) -> Any:
    """Writes `cid` where `docker run --cidfile` was told to, as docker does."""

    def write(argv: list[str]) -> None:
        Path(after(argv, "--cidfile")[0]).write_text(cid)

    return write


def daemon(**said: Any) -> str:
    return json.dumps({"ServerVersion": "27.0", **said})


# ------------------------------------------------------------------------------ config


def test_a_container_is_remote_isolated_managed_linux_and_supervised() -> None:
    assert DockerConfig().capabilities == {
        REMOTE,
        ISOLATED,
        MANAGED,
        "linux",
        SUPERVISED,
    }


def test_a_setting_builds_a_machine_that_has_started_nothing(runs: Runs) -> None:
    assert isinstance(DockerConfig().create(), Docker)
    assert runs.calls == []


@pytest.mark.parametrize(
    "said",
    [
        {"endpoint": "ftp://x"},
        {"name": "-bad"},
        {"name": "a b"},
        {"name": "x"},
        {"cpus": 0},
        {"memory": -1},
        {"shm_size": 0},
        {"gpus": "0"},
        {"gpus": ("",)},
        {"gpus": ("0,1",)},
        {"env": {"": "x"}},
        {"labels": {"a=b": "x"}},
    ],
)
def test_what_docker_would_refuse_is_refused_where_it_is_written(
    said: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match=r"unsupported|must be|expected"):
        DockerConfig(**said)


def test_gpu_ids_given_as_numbers_are_taken_as_their_names() -> None:
    assert DockerConfig(gpus=cast("Any", [0, 1])).gpus == ("0", "1")
    assert DockerConfig(gpus="all").gpus == "all"


def test_a_setting_keeps_a_copy_of_what_it_was_given() -> None:
    env = {"A": "1"}
    config = DockerConfig(env=env, run_args=cast("Any", ["--x"]))
    env["B"] = "2"

    assert dict(config.env) == {"A": "1"}
    assert config.run_args == ("--x",)


# ------------------------------------------------------------------------- allocations


def test_a_daemon_running_nothing_of_ours_holds_nothing(runs: Runs) -> None:
    assert allocations(labels={"team": "a"}) == []
    (asked,) = runs.calls
    assert asked[:2] == ["docker", "ps"]
    assert after(asked, "--filter") == ["label=humanize", "label=team=a"]


def test_what_each_container_holds_is_read_off_its_labels(runs: Runs) -> None:
    runs.on("ps", out="c1\nc2\n")
    runs.on(
        "inspect",
        out=json.dumps(
            [
                {
                    "Name": "/one",
                    "Config": {
                        "Labels": {
                            "humanize": "1",
                            CPUS: "2.5",
                            MEMORY: "1024",
                            GPUS: "0,1",
                        }
                    },
                },
                {"Name": "/two", "Config": {"Labels": {CPUS: "lots", GPUS: "all"}}},
            ]
        ),
    )

    found = allocations()

    assert found == [
        Allocation(
            name="one",
            cpus=2.5,
            memory=1024,
            gpus=("0", "1"),
            labels={"humanize": "1", CPUS: "2.5", MEMORY: "1024", GPUS: "0,1"},
        ),
        Allocation(
            name="two",
            cpus=None,
            memory=None,
            gpus="all",
            labels={CPUS: "lots", GPUS: "all"},
        ),
    ]
    assert runs.called("inspect", "c1", "c2")


def test_a_container_gone_between_the_two_questions_is_passed_over(runs: Runs) -> None:
    runs.on("ps", out="c1 c2")
    runs.on(
        "inspect",
        status=1,
        out=json.dumps([{"Name": "/one"}]),
        err="Error: No such object: c2\n",
    )

    assert [one.name for one in allocations()] == ["one"]


@pytest.mark.parametrize(
    ("words", "status", "out", "err"),
    [
        (("ps",), 1, "", "cannot connect"),
        (("inspect",), 1, "", "permission denied"),
        (("inspect",), 0, "not json", ""),
    ],
)
def test_a_daemon_that_could_not_be_asked_is_not_one_with_nothing_on_it(
    runs: Runs, words: tuple[str, ...], status: int, out: str, err: str
) -> None:
    runs.on("ps", out="c1")
    runs.on(*words, status=status, out=out, err=err)

    with pytest.raises(OSError, match="could not ask local what it runs"):
        allocations()


def test_a_daemon_that_does_not_answer_in_time_is_an_error(runs: Runs) -> None:
    runs.on("ps", timeout=True)

    with pytest.raises(OSError, match=r"did not answer within 2s") as raised:
        allocations(seconds=2)
    assert raised.value.errno == errno.ETIMEDOUT


def test_a_daemon_elsewhere_is_asked_and_nothing_else_is(runs: Runs) -> None:
    allocations("tcp://box:2376")

    (asked,) = runs.calls
    assert asked[0] == "env"
    assert "DOCKER_HOST" in asked
    assert asked[asked.index("docker") :][:3] == ["docker", "--host", "tcp://box:2376"]


def test_an_endpoint_that_does_not_read_is_refused(runs: Runs) -> None:
    with pytest.raises(ValueError, match="unsupported docker endpoint"):
        allocations("nowhere")
    assert runs.calls == []


# -------------------------------------------------------------------------------- info


def test_what_a_daemon_says_of_itself_is_answered(runs: Runs) -> None:
    runs.on("info", out=daemon(Name="box"))

    assert info()["Name"] == "box"
    assert runs.calls == [["docker", "info", "--format", "{{json .}}"]]


@pytest.mark.parametrize(
    ("status", "out", "err", "why"),
    [
        (0, json.dumps({"ServerErrors": ["no daemon"]}), "", "no daemon"),
        (1, "", "Cannot connect", "Cannot connect"),
        (0, "garbage", "", "exit 0"),
        (3, "", "", "exit 3"),
    ],
)
def test_a_daemon_that_would_not_say_is_an_error_in_its_own_words(
    runs: Runs, status: int, out: str, err: str, why: str
) -> None:
    runs.on("info", status=status, out=out, err=err)

    with pytest.raises(OSError, match=why):
        info()


# ------------------------------------------------------------------------- gpus_listed


@pytest.mark.parametrize(
    ("devices", "kind", "said"),
    [
        ([], "", ()),
        (
            [
                {"ID": "nvidia.com/gpu=1"},
                {"ID": "nvidia.com/gpu=GPU-abc"},
                {"ID": "nvidia.com/gpu=0"},
                {"ID": "nvidia.com/gpu=all"},
                {"ID": "nvidia.com/gpu=10"},
            ],
            "",
            ("0", "1", "10"),
        ),
        (
            [{"ID": "nvidia.com/gpu=GPU-a"}, {"ID": "nvidia.com/gpu=GPU-a"}],
            "",
            ("GPU-a",),
        ),
        (
            [{"ID": "amd.com/gpu=0"}, {"ID": "nvidia.com/gpu=3"}],
            "nvidia.com/gpu",
            ("3",),
        ),
        ([{"ID": "amd.com/gpu=0"}, "junk", {"ID": "x.com/fpga=1"}], "", ("0",)),
    ],
)
def test_the_gpus_a_daemon_lists_are_named_by_index_where_it_can(
    devices: list[Any], kind: str, said: tuple[str, ...]
) -> None:
    assert gpus_listed(devices, kind) == said


# ------------------------------------------------------------------------- gpus_usable


def endpoint_of(tmp_path: Path) -> str:
    """A daemon nobody else's test asks after, so no answer kept for another is read."""
    return f"unix://{tmp_path}/docker.sock"


CDI = [{"ID": "nvidia.com/gpu=0"}, {"ID": "nvidia.com/gpu=1"}]


def test_each_listed_gpu_is_asked_of_a_container_given_it_alone(
    runs: Runs, tmp_path: Path
) -> None:
    runs.on("nvidia.com/gpu=0", out="0, GPU-aaa\n")
    runs.on("nvidia.com/gpu=1", status=0, out="")

    said = gpus_usable(endpoint_of(tmp_path), "img", CDI, fresh=True)

    assert said == (("0", "GPU-aaa"),)
    for one in runs.called("run"):
        assert "NVIDIA_VISIBLE_DEVICES=void" in one
        assert after(one, "--network") == ["none"]
        assert after(one, "--entrypoint") == ["nvidia-smi"]


def test_a_daemon_listing_no_gpus_is_asked_once_for_all_of_them(
    runs: Runs, tmp_path: Path
) -> None:
    runs.on("run", out="0, GPU-a\n1, GPU-b\nnoise\n")

    said = gpus_usable(endpoint_of(tmp_path), "img", [], fresh=True)

    assert said == (("0", "GPU-a"), ("1", "GPU-b"))
    (asked,) = runs.calls
    assert after(asked, "--gpus") == ["all"]


def test_a_host_whose_gpus_all_failed_has_none(runs: Runs, tmp_path: Path) -> None:
    runs.on("run", status=6, out="No devices were found\n")

    assert gpus_usable(endpoint_of(tmp_path), "img", [], fresh=True) == ()


@pytest.mark.parametrize(("status", "out"), [(125, "no runtime"), (0, "nothing")])
def test_no_answer_is_none(runs: Runs, tmp_path: Path, status: int, out: str) -> None:
    runs.on("run", status=status, out=out)

    assert gpus_usable(endpoint_of(tmp_path), "img", CDI, fresh=True) is None


def test_a_container_that_does_not_answer_in_time_is_taken_down(
    runs: Runs, tmp_path: Path
) -> None:
    runs.on("run", timeout=True)

    assert gpus_usable(endpoint_of(tmp_path), "img", [], seconds=1) is None
    (named,) = after(runs.called("run")[0], "--name")
    assert runs.called("rm", "--force", named)


def test_an_answer_is_kept_and_asked_again_only_when_fresh(
    runs: Runs, tmp_path: Path
) -> None:
    runs.on("run", out="0, GPU-a\n")
    endpoint = endpoint_of(tmp_path)

    first = gpus_usable(endpoint, "img", [])
    again = gpus_usable(endpoint, "img", [])
    assert first == again == (("0", "GPU-a"),)
    assert len(runs.calls) == 1

    gpus_usable(endpoint, "img", [], fresh=True)
    assert len(runs.calls) == 2


def test_no_answer_is_not_kept(runs: Runs, tmp_path: Path) -> None:
    runs.on("run", status=1)
    endpoint = endpoint_of(tmp_path)

    gpus_usable(endpoint, "img", [])
    gpus_usable(endpoint, "img", [])

    assert len(runs.calls) == 2


# -------------------------------------------------------------------- bound and whose


def test_a_workspace_is_mounted_at_the_path_it_already_has() -> None:
    assert bound("/w") == "type=bind,source=/w,target=/w"
    assert bound("/a,b") == 'type=bind,"source=/a,b","target=/a,b"'


@pytest.mark.parametrize(
    ("security", "user"),
    [([], ME), (["name=seccomp", "name=rootless"], "0:0")],
)
def test_a_container_on_this_machine_runs_as_this_user(
    runs: Runs, security: list[str], user: str
) -> None:
    told = {"SecurityOptions": security}

    assert whose(Endpoint.parse("local"), "img", "/w", lambda: told) == user
    assert runs.calls == []


def test_a_container_elsewhere_runs_as_whoever_owns_the_workspace_there(
    runs: Runs,
) -> None:
    runs.on("run", out="entrypoint says hi\n1000 1001\n")

    said = whose(Endpoint.parse("ssh://box"), "img", "/w", dict)

    assert said == "1000:1001"
    (asked,) = runs.calls
    assert after(asked, "--mount") == ["type=bind,source=/w,target=/w"]
    assert asked[-1] == "/w"


@pytest.mark.parametrize(
    ("err", "raised"),
    [
        ("bind source path does not exist: /w", FileNotFoundError),
        ("pull access denied", RuntimeError),
    ],
)
def test_a_workspace_that_cannot_be_asked_after_elsewhere_is_an_error(
    runs: Runs, err: str, raised: type[Exception]
) -> None:
    runs.on("run", status=125, err=err)

    with pytest.raises(raised):
        whose(Endpoint.parse("ssh://box"), "img", "/w", dict)


# ------------------------------------------------------------------------------- start


def test_with_no_docker_nothing_starts(runs: Runs) -> None:
    runs.absent.add("docker")

    with pytest.raises(FileNotFoundError, match="no docker"):
        DockerConfig().create().start()
    assert runs.calls == []


def test_a_workspace_that_is_not_there_is_not_given(runs: Runs, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no directory"):
        DockerConfig(workspace=str(tmp_path / "missing")).create().start()
    assert runs.called("run") == []


def test_a_workspace_elsewhere_must_be_absolute(runs: Runs) -> None:
    with pytest.raises(ValueError, match="absolute"):
        DockerConfig(workspace="rel", endpoint="ssh://box").create().start()


def test_a_container_is_started_holding_the_workspace(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on("run", then=cidfile("cid-1"))
    machine = DockerConfig(
        image="img:1", workspace=str(tmp_path), name="box", env={"A": "1"}
    ).create()

    anchor = machine.start()

    (started,) = runs.called("run", "--detach")
    assert after(started, "--name") == ["box"]
    assert after(started, "--user") == [ME]
    assert after(started, "--workdir") == [str(tmp_path)]
    assert after(started, "--mount") == [bound(str(tmp_path))]
    assert after(started, "--label") == [f"humanize={os.getuid()}"]
    assert after(started, "--env") == [
        "HOME=/tmp",
        "A=1",
        "NVIDIA_VISIBLE_DEVICES=void",
    ]
    assert started[started.index("img:1") + 1] == "/bin/sh"
    assert anchor.target == "docker://box"
    assert anchor.workspace == str(tmp_path)
    assert handshake.asked == [anchor]
    assert "linux" in machine.capabilities


def test_a_container_is_given_what_its_setting_says_of_the_host(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    config = DockerConfig(
        workspace=str(tmp_path),
        cpus=1.5,
        memory=2048,
        shm_size=64,
        runtime="runc",
        network="none",
        run_args=("--privileged",),
        labels={"team": "a", "humanize": "spoofed", CPUS: "99"},
    )

    config.create().start()

    (started,) = runs.called("run", "--detach")
    assert after(started, "--label") == [
        "team=a",
        f"humanize={os.getuid()}",
        f"{CPUS}=1.5",
        f"{MEMORY}=2048",
    ]
    assert after(started, "--cpus") == ["1.5"]
    assert after(started, "--memory") == ["2048"]
    assert after(started, "--shm-size") == ["64"]
    assert after(started, "--runtime") == ["runc"]
    assert after(started, "--network") == ["none"]
    assert started.index("--privileged") < started.index("--cpus")


def test_a_rootless_daemon_runs_the_container_as_its_own_root(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on("info", out=daemon(SecurityOptions=["name=rootless"]))

    DockerConfig(workspace=str(tmp_path)).create().start()

    assert after(runs.called("run", "--detach")[0], "--user") == ["0:0"]


def test_gpus_a_daemon_lists_are_handed_out_by_name(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on(
        "info",
        out=daemon(DiscoveredDevices=[{"ID": "nvidia.com/gpu=0", "Source": "cdi"}]),
    )

    DockerConfig(workspace=str(tmp_path), gpus=("0",)).create().start()

    (started,) = runs.called("run", "--detach")
    assert after(started, "--device") == ["nvidia.com/gpu=0"]
    assert after(started, "--label")[-1] == f"{GPUS}=0"
    assert "NVIDIA_VISIBLE_DEVICES=void" in after(started, "--env")


@pytest.mark.parametrize(
    ("gpus", "flag"),
    [(("0", "1"), '"device=0,1"'), ("all", "all")],
)
def test_gpus_a_daemon_does_not_list_are_asked_of_its_runtime(
    runs: Runs,
    handshake: Handshake,
    tmp_path: Path,
    gpus: tuple[str, ...] | str,
    flag: str,
) -> None:
    DockerConfig(workspace=str(tmp_path), gpus=cast("Any", gpus)).create().start()

    (started,) = runs.called("run", "--detach")
    assert after(started, "--gpus") == [flag]
    assert "NVIDIA_VISIBLE_DEVICES=void" not in after(started, "--env")


def test_a_container_on_a_daemon_elsewhere_is_reached_through_it(
    runs: Runs, handshake: Handshake
) -> None:
    runs.on("--rm", out="1000 1000\n")

    anchor = (
        DockerConfig(workspace="/srv/w", endpoint="ssh://box", name="c1")
        .create()
        .start()
    )

    (started,) = runs.called("run", "--detach")
    assert started[:2] == ["env", "-u"]
    assert after(started, "--user") == ["1000:1000"]
    assert anchor.target.startswith("docker://c1@ssh://box")
    assert anchor.workspace == "/srv/w"


def test_a_container_that_would_not_start_says_why(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on("run", status=125, err="no such image\n")

    with pytest.raises(RuntimeError, match="no such image"):
        DockerConfig(image="nope", workspace=str(tmp_path)).create().start()
    assert runs.called("rm") == []
    assert handshake.asked == []


def test_a_container_that_is_not_what_was_promised_is_taken_down(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on("run", then=cidfile("cid-2"))
    handshake.platform = "darwin"
    machine = DockerConfig(workspace=str(tmp_path)).create()

    with pytest.raises(RuntimeError, match="cannot serve linux"):
        machine.start()
    assert runs.called("rm", "--force", "cid-2")
    assert not Path(handshake.asked[0].shadow or "").parent.exists()


def test_stopping_takes_down_only_the_container_it_made(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on("run", then=cidfile("cid-3"))
    machine = DockerConfig(workspace=str(tmp_path), name="shared").create()
    anchor = machine.start()

    machine.stop()

    assert runs.called("rm", "--force", "cid-3")
    assert runs.called("rm", "--force", "shared") == []
    assert not Path(anchor.shadow or "").parent.exists()


def test_stopping_a_container_never_started_runs_nothing(runs: Runs) -> None:
    DockerConfig().create().stop()

    assert runs.calls == []
