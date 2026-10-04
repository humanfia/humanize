"""This Mac's Apple containers as a runtime, a target and a machine -- nothing started.

A runtime of them is written down and read back like any other, under its own backend; its
containers are reached by an `apple-container://` target, whose road is `container exec`; and
what a container is started with, and what `container` says of the ones running, is read here
from what `container` would say -- the answers stood in for, since a unit test runs nothing.
The integration tier runs a stand-in `container`; the system tier, Apple's.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import PurePosixPath
from typing import Any

import pytest

from hmz import home
from hmz.coganchor.machines import AppleContainerConfig, apple_container, store
from hmz.coganchor.machines.store import AppleContainerRuntime, DockerRuntime
from hmz.coganchor.transport import CONTAINER_CACHE, Road, Target
from hmz.flows import EnvBackendKind
from hmz.runtime.flowing.specs import fallbacks, parse_envs


def test_a_runtime_of_apple_containers_is_read_back_as_it_was_written_down() -> None:
    written = AppleContainerRuntime(
        name="mac",
        image="debian:13",
        run_args=("--dns", "1.1.1.1"),
        cpus=6,
        memory=16 << 30,
        max_containers=3,
        workdir="~/work",
        fallback=("docker:box",),
        affinity=("self", "local"),
    )

    store.add(written)

    assert store.find("apple-container", "mac") == written
    assert written.at == home() / "runtimes" / "apple-container" / "mac"
    assert written.held()["backend"] == "apple-container"
    assert store.runtimes("apple-container") == [written]
    held = {k: v for k, v in written.held().items() if k not in ("backend", "name")}
    assert store.new("apple-container", "mac", **held) == written


@pytest.mark.parametrize(
    ("fields", "why"),
    [
        ({"cpus": -1}, "CPUs cannot be negative"),
        ({"memory": -1}, "memory cannot be negative"),
        ({"max_containers": -1}, "containers cannot be negative"),
        ({"image": "two words"}, "invalid image"),
        ({"run_args": ["a\nb"]}, "cannot contain newlines"),
        ({"workdir": "work"}, "must be absolute or under ~/"),
        ({"fallback": ["apple-container:mac"]}, "cannot fall back to itself"),
        ({"affinity": ["apple-container:mac"]}, "its affinity names itself"),
        ({"made": "imported"}, "made must be typed"),
        ({"endpoint": "tcp://h:1"}, "unknown apple-container host setting"),
        ({"gpus": ["0"]}, "unknown apple-container host setting"),
    ],
)
def test_what_no_runtime_of_apple_containers_could_be_is_refused(
    fields: dict[str, Any], why: str
) -> None:
    with pytest.raises(ValueError, match=why):
        store.new("apple-container", "mac", **fields)


def test_any_runtime_may_fall_back_to_apple_containers_or_put_a_harness_on_them() -> (
    None
):
    store.write(AppleContainerRuntime(name="mac", workdir="/Users/me/work"))
    store.write(
        DockerRuntime(
            name="main",
            fallback=("apple-container:mac",),
            affinity=("apple-container:mac",),
        )
    )
    (spec,) = parse_envs(["work=docker@main/srv/x"])

    assert store.affine("apple-container:mac") == ("apple-container", "mac")
    (onward,) = fallbacks(spec)
    assert onward.backend is EnvBackendKind.APPLE_CONTAINER
    assert str(onward) == "work=apple-container@mac/Users/me/work"


def test_a_list_falling_back_to_apple_container_local_falls_back_to_this_macs() -> None:
    """The one name a list has for this Mac's with nothing saved, unless one is saved so."""
    store.write(DockerRuntime(name="main", fallback=("apple-container:local",)))
    (spec,) = parse_envs(["work=docker@main/srv/x"])

    assert [str(one) for one in fallbacks(spec)] == ["work=apple-container/srv/x"]
    store.write(AppleContainerRuntime(name="local"))
    assert [str(one) for one in fallbacks(spec)] == ["work=apple-container@local/srv/x"]


# ------------------------------------------------------------------------------- the road


def test_an_apple_container_is_a_target_of_its_own_reached_by_container_exec() -> None:
    target = Target.parse("apple-container://humanize-box")

    assert (target.scheme, target.host) == ("apple-container", "humanize-box")
    assert target.describe() == "apple-container://humanize-box"
    road = Road.to(target)
    assert road.line(["python3", "-V"]) == [
        "container",
        "exec",
        "-i",
        "humanize-box",
        "python3",
        "-V",
    ]
    assert road.cache == CONTAINER_CACHE
    # It names no daemon: `container` reaches this Mac's containers and no other's.
    with pytest.raises(ValueError, match="is not a container"):
        _ = target.endpoint


@pytest.mark.parametrize(
    "spec",
    ["apple-container://", "apple-container://a@b", "apple-container://a/b"],
)
def test_an_apple_container_target_that_names_no_one_container_is_refused(
    spec: str,
) -> None:
    with pytest.raises(ValueError, match="unsupported target"):
        Target.parse(spec)


# ------------------------------------------------------------------------------ a machine


def test_a_container_setting_says_it_is_an_isolated_linux_machine() -> None:
    config = AppleContainerConfig(
        image="debian:13",
        cpus=2.0,  # pyright: ignore[reportArgumentType] -- as a JSON number is read
        memory=1 << 30,
    )

    assert {"isolated", "linux", "managed", "remote"} <= config.capabilities
    assert config.cpus == 2
    assert isinstance(config.cpus, int)


@pytest.mark.parametrize(
    ("fields", "why"),
    [
        ({"cpus": 1.5}, "whole number"),
        ({"cpus": 0}, "more than nothing"),
        ({"memory": 0}, "more than nothing"),
        ({"name": "-x"}, "unsupported container name"),
        ({"env": {"A=B": "c"}}, "without '='"),
        ({"labels": {"": "c"}}, "without '='"),
    ],
)
def test_a_container_setting_container_would_refuse_is_refused_where_it_is_written(
    fields: dict[str, Any], why: str
) -> None:
    with pytest.raises(ValueError, match=why):
        AppleContainerConfig(**fields)


def test_a_workspace_a_mac_spells_two_ways_is_mounted_at_both() -> None:
    assert apple_container.mounted("/Users/me/work") == [
        "--mount",
        "type=bind,source=/Users/me/work,target=/Users/me/work",
    ]
    assert apple_container.mounted("/private/var/folders/x") == [
        "--mount",
        "type=bind,source=/private/var/folders/x,target=/private/var/folders/x",
        "--mount",
        "type=bind,source=/private/var/folders/x,target=/var/folders/x",
    ]


def _answers(
    monkeypatch: pytest.MonkeyPatch, said: str, status: int = 0, err: str = ""
) -> list[list[str]]:
    """Has `container` answer every question with this, and says what it was asked."""
    asked: list[list[str]] = []

    def answer(
        argv: list[str], seconds: float | None
    ) -> subprocess.CompletedProcess[str]:
        del seconds
        asked.append(argv)
        return subprocess.CompletedProcess(argv, status, said, err)

    monkeypatch.setattr(apple_container, "_asked", answer)
    return asked


def _listed(
    name: str, labels: dict[str, str], resources: dict[str, int] | None = None
) -> dict[str, Any]:
    config: dict[str, Any] = {"id": name, "labels": labels}
    if resources is not None:
        config["resources"] = resources
    return {"configuration": config, "id": name, "status": {"state": "running"}}


def test_allocations_are_humanize_s_running_containers_and_what_each_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _answers(
        monkeypatch,
        json.dumps(
            [
                _listed(
                    "a",
                    {
                        "humanize": "501",
                        "humanize.cpus": "2",
                        "humanize.provider": "mac",
                    },
                ),
                _listed("b", {"humanize": "501", "humanize.memory": "lots"}),
                # Its virtual machine's size is what it holds, whatever it is labelled.
                _listed(
                    "c",
                    {
                        "humanize": "0",
                        "humanize.cpus": "1",
                        "humanize.provider": "other",
                    },
                    {"cpus": 4, "memoryInBytes": 1 << 30},
                ),
                _listed("buildkit", {"com.apple.container.plugin": "builder"}),
                {"not": "a container"},
            ]
        ),
    )

    every = apple_container.allocations(seconds=5)
    mine = apple_container.allocations({"humanize.provider": "mac"})

    assert asked[0] == ["container", "list", "--format", "json"]
    assert [one.name for one in every] == ["a", "b", "c"]
    # Where `container` said no size, the labels say what it was given.
    assert (every[0].cpus, every[0].memory, every[0].gpus) == (2.0, None, ())
    # And a label written wrong on somebody's container is one saying nothing.
    assert (every[1].cpus, every[1].memory) == (None, None)
    assert (every[2].cpus, every[2].memory) == (4.0, 1 << 30)
    assert [one.name for one in mine] == ["a"]


def test_a_container_s_memory_is_a_whole_mib_at_least_what_was_asked() -> None:
    assert AppleContainerConfig(memory=1_500_000_000).memory == 1431 << 20
    assert AppleContainerConfig(memory=1 << 30).memory == 1 << 30


@pytest.mark.parametrize(
    ("said", "status"), [("", 1), ("not json", 0), ('{"a": 1}', 0)]
)
def test_a_mac_that_could_not_be_asked_is_not_one_with_nothing_on_it(
    monkeypatch: pytest.MonkeyPatch, said: str, status: int
) -> None:
    _answers(monkeypatch, said, status, "Error: apiserver is not running")

    with pytest.raises(OSError, match="could not ask Apple's container what it runs"):
        apple_container.allocations()


def test_the_container_system_says_what_the_mac_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    _answers(
        monkeypatch,
        json.dumps(
            {"status": "running", "host": {"cpus": 18}, "server": {"version": "1.5.0"}}
        ),
    )

    said = apple_container.status(5)

    cpus, memory = apple_container.capacity(said)
    assert cpus == 18.0
    assert memory == os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


@pytest.mark.parametrize(
    ("said", "status", "why"),
    [
        ("", 1, "apiserver is not running"),
        ('{"status": "stopped"}', 0, "it is stopped"),
        ("not json", 0, "not json"),
    ],
)
def test_a_container_system_that_is_not_running_says_so(
    monkeypatch: pytest.MonkeyPatch, said: str, status: int, why: str
) -> None:
    _answers(monkeypatch, said, status, "apiserver is not running" if status else "")

    with pytest.raises(OSError, match=why):
        apple_container.status()


def test_where_an_e_puts_a_role_on_apple_containers_is_this_macs_path() -> None:
    (spec,) = parse_envs(["box=apple-container/Users/me/work"])

    assert (spec.backend, spec.provider, spec.workdir) == (
        EnvBackendKind.APPLE_CONTAINER,
        "",
        PurePosixPath("/Users/me/work"),
    )
    assert str(spec) == "box=apple-container/Users/me/work"
