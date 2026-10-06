from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor.machines import Allocation, AppleContainer, AppleContainerConfig
from hmz.coganchor.machines.apple_container import (
    allocations,
    capacity,
    mounted,
    status,
)
from hmz.coganchor.machines.docker import CPUS, MEMORY
from hmz.coganchor.places import ISOLATED, MANAGED, REMOTE, SUPERVISED

if TYPE_CHECKING:
    from tests.unit.coganchor.machines.conftest import Handshake, Runs

MIB = 1 << 20


def after(argv: list[str], flag: str) -> list[str]:
    return [argv[at + 1] for at, one in enumerate(argv[:-1]) if one == flag]


def cidfile(cid: str) -> Any:
    def write(argv: list[str]) -> None:
        Path(after(argv, "--cidfile")[0]).write_text(cid)

    return write


def listed(*containers: object) -> str:
    return json.dumps(list(containers))


def container(ident: str, labels: object, resources: object = None) -> dict[str, Any]:
    config: dict[str, Any] = {"id": ident, "labels": labels}
    if resources is not None:
        config["resources"] = resources
    return {"configuration": config}


# ------------------------------------------------------------------------------ config


def test_a_container_is_remote_isolated_managed_linux_and_supervised() -> None:
    assert AppleContainerConfig().capabilities == {
        REMOTE,
        ISOLATED,
        MANAGED,
        "linux",
        SUPERVISED,
    }


@pytest.mark.parametrize(
    "said",
    [
        {"name": "-x"},
        {"cpus": 0},
        {"cpus": 1.5},
        {"cpus": "2"},
        {"memory": 0},
        {"env": {"": "1"}},
        {"labels": {"a=b": "1"}},
    ],
)
def test_what_container_would_refuse_is_refused_where_it_is_written(
    said: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match=r"unsupported|must be"):
        AppleContainerConfig(**said)


def test_whole_cpus_and_memory_in_whole_mib_are_taken() -> None:
    config = AppleContainerConfig(cpus=cast("Any", 2.0), memory=MIB + 1)

    assert config.cpus == 2
    assert isinstance(config.cpus, int)
    assert config.memory == 2 * MIB


def test_a_setting_builds_a_machine_that_has_started_nothing(runs: Runs) -> None:
    machine = AppleContainerConfig().create()

    assert isinstance(machine, AppleContainer)
    machine.stop()
    assert runs.calls == []


# ------------------------------------------------------------------------- allocations


def test_only_humanizes_containers_carrying_the_labels_asked_for_are_counted(
    runs: Runs,
) -> None:
    runs.on(
        "list",
        out=listed(
            container(
                "mine",
                {"humanize": "501", "team": "a"},
                {"cpus": 4, "memoryInBytes": 2048},
            ),
            container("other-team", {"humanize": "501", "team": "b"}),
            container("not-ours", {"team": "a"}),
            container("labels-not-a-map", ["x"]),
            "junk",
        ),
    )

    found = allocations({"team": "a"})

    assert found == [
        Allocation(
            name="mine",
            cpus=4.0,
            memory=2048,
            gpus=(),
            labels={"humanize": "501", "team": "a"},
        )
    ]
    assert runs.calls == [["container", "list", "--format", "json"]]


def test_a_size_container_does_not_say_is_read_off_the_labels(runs: Runs) -> None:
    labels = {"humanize": "1", CPUS: "3", MEMORY: "oops"}
    runs.on("list", out=listed(container("c", labels, {"cpus": True})))

    (found,) = allocations()

    assert (found.cpus, found.memory) == (3.0, None)


@pytest.mark.parametrize(
    ("status_", "out", "err", "why"),
    [
        (1, "", "XPC connection error", "XPC connection error"),
        (0, "not json", "", "not json"),
        (0, "{}", "", "{}"),
        (2, "", "", "exit 2"),
    ],
)
def test_containers_that_could_not_be_listed_are_an_error(
    runs: Runs, status_: int, out: str, err: str, why: str
) -> None:
    runs.on("list", status=status_, out=out, err=err)

    with pytest.raises(OSError, match=why):
        allocations()


def test_a_list_that_does_not_come_in_time_is_an_error(runs: Runs) -> None:
    runs.on("list", timeout=True)

    with pytest.raises(OSError, match="did not answer within 1s"):
        allocations(seconds=1)


# ------------------------------------------------------------------ status / capacity


def test_a_running_system_says_what_it_has(runs: Runs) -> None:
    runs.on("system", "status", out=json.dumps({"status": "running", "host": {}}))

    assert status()["status"] == "running"


@pytest.mark.parametrize(
    ("status_", "out", "err", "why"),
    [
        (0, json.dumps({"status": "stopped"}), "", "it is stopped"),
        (1, "", "not installed", "not installed"),
        (0, "", "", "it is not running"),
        (0, "plain words", "", "plain words"),
    ],
)
def test_a_system_that_is_not_running_says_so(
    runs: Runs, status_: int, out: str, err: str, why: str
) -> None:
    runs.on("system", "status", status=status_, out=out, err=err)

    with pytest.raises(OSError, match=why):
        status()


def test_capacity_is_the_cpus_counted_and_the_macs_own_memory() -> None:
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")

    assert capacity({"host": {"cpus": 6}}) == (6.0, memory)
    assert capacity({}) == (float(os.cpu_count() or 0), memory)


# ----------------------------------------------------------------------------- mounted


def test_a_workspace_is_mounted_under_every_name_it_has() -> None:
    assert mounted("/Users/me/w") == [
        "--mount",
        "type=bind,source=/Users/me/w,target=/Users/me/w",
    ]
    assert mounted("/tmp/w") == [
        "--mount",
        "type=bind,source=/tmp/w,target=/tmp/w",
        "--mount",
        "type=bind,source=/tmp/w,target=/private/tmp/w",
    ]


# ------------------------------------------------------------------------------- start


def test_with_no_container_command_nothing_starts(runs: Runs) -> None:
    runs.absent.add("container")

    with pytest.raises(FileNotFoundError, match="no container command"):
        AppleContainerConfig().create().start()


def test_a_workspace_that_is_not_there_is_not_given(runs: Runs, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no directory"):
        AppleContainerConfig(workspace=str(tmp_path / "gone")).create().start()
    assert runs.calls == []


def test_a_workspace_holding_a_comma_cannot_be_mounted(
    runs: Runs, tmp_path: Path
) -> None:
    odd = tmp_path / "a,b"
    odd.mkdir()

    with pytest.raises(ValueError, match="comma"):
        AppleContainerConfig(workspace=str(odd)).create().start()
    assert runs.calls == []


def test_a_container_is_started_holding_the_workspace(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on("run", then=cidfile("cid-1"))
    config = AppleContainerConfig(
        image="img:1",
        workspace=str(tmp_path),
        name="box",
        cpus=2,
        memory=MIB,
        run_args=("--ssh",),
        env={"A": "1"},
        labels={"team": "a", "humanize": "spoofed"},
    )

    anchor = config.create().start()

    (started,) = runs.called("container", "run")
    assert after(started, "--name") == ["box"]
    assert after(started, "--progress") == ["none"]
    assert after(started, "--user") == [f"{os.getuid()}:{os.getgid()}"]
    assert after(started, "--workdir") == [str(tmp_path)]
    assert after(started, "--env") == ["HOME=/tmp", "A=1"]
    assert after(started, "--label") == [
        "team=a",
        f"humanize={os.getuid()}",
        f"{CPUS}=2",
        f"{MEMORY}={MIB}",
    ]
    assert after(started, "--cpus") == ["2"]
    assert after(started, "--memory") == [str(MIB)]
    assert started.index("--ssh") < started.index("--cpus")
    assert started[started.index("img:1") + 1] == "/bin/sh"
    assert anchor.target == "apple-container://box"
    assert anchor.workspace == str(tmp_path)
    assert handshake.asked == [anchor]


def test_a_container_that_would_not_start_says_why(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on("run", status=1, err="image not found")

    with pytest.raises(RuntimeError, match="image not found"):
        AppleContainerConfig(workspace=str(tmp_path)).create().start()
    assert runs.called("delete") == []


def test_a_container_that_is_not_what_was_promised_is_taken_down(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on("run", then=cidfile("cid-2"))
    handshake.platform = "darwin"

    with pytest.raises(RuntimeError, match="cannot serve linux"):
        AppleContainerConfig(workspace=str(tmp_path)).create().start()
    assert runs.called("container", "delete", "--force", "cid-2")


def test_stopping_takes_down_only_the_container_it_made(
    runs: Runs, handshake: Handshake, tmp_path: Path
) -> None:
    runs.on("run", then=cidfile("cid-3"))
    machine = AppleContainerConfig(workspace=str(tmp_path)).create()
    anchor = machine.start()

    machine.stop()

    assert runs.called("container", "delete", "--force", "cid-3")
    assert not Path(anchor.shadow or "").parent.exists()
