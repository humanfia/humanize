"""The command lines a container machine hands `docker`, read off a stand-in that writes them down.

The stand-in is a `docker` on `PATH` written here. It records every argv it is given and the
`DOCKER_HOST` it was run under, and does just enough of what docker does for a machine to come
up through it: `run` writes the id a real one would into the file it was told to, and `exec`
runs what it was handed on this machine, with the container's `/tmp/humanize` moved into the
test's own directory -- so the bundle is installed, the serving half starts, and the handshake
a machine is observed with is a real one. What cannot be stood in for -- a real daemon on each
kind of endpoint, a real GPU, a real cgroup -- is `tests/system/machines/`.

Every explicit endpoint is run with `DOCKER_HOST` pointing somewhere else, and the stand-in is
asked whether it ever saw it: an endpoint that the environment could redirect is one whose
container a later command might not find.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import transport
from hmz.coganchor.machines import DockerConfig, Mapped, allocations
from hmz.coganchor.transport import Endpoint, Road, Target
from tests.machines.fixtures import IMAGE

if TYPE_CHECKING:
    from pathlib import Path

#: The stand-in itself. Global flags are skipped the way docker's parser reads them -- every
#: one of them takes a value but `--tlsverify` -- so the subcommand is found wherever it is.
_STANDIN = """\
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["STANDIN_LOG"], "a") as log:
    log.write(json.dumps({"argv": argv, "DOCKER_HOST": os.environ.get("DOCKER_HOST")}))
    log.write("\\n")
at = 0
while argv[at].startswith("-"):
    at += 1 if argv[at] == "--tlsverify" else 2
command, rest = argv[at], argv[at + 1 :]
if command == "run" and "--rm" in rest:
    if "STANDIN_UNPULLED" in os.environ:
        sys.exit(
            "docker: Error response from daemon: pull access denied for typo, "
            "repository does not exist or may require 'docker login'"
        )
    if "STANDIN_OWNER" not in os.environ:
        sys.exit(
            'docker: Error response from daemon: invalid mount config for type "bind": '
            "bind source path does not exist: " + rest[-1]
        )
    print(os.environ["STANDIN_OWNER"])
elif command == "run":
    if "STANDIN_TAKEN" in os.environ:
        sys.exit("docker: Error response from daemon: Conflict. The name is in use")
    with open(rest[rest.index("--cidfile") + 1], "w") as made:
        made.write("c0ffee\\n")
    if "STANDIN_REFUSE" in os.environ:
        sys.exit("docker: Error response from daemon: failed to create task")
    print("c0ffee")
elif command == "info":
    print(json.dumps({
        "DiscoveredDevices": json.loads(os.environ.get("STANDIN_DEVICES", "null")),
        "SecurityOptions": json.loads(os.environ.get("STANDIN_SECURITY", "[]")),
    }))
elif command == "exec":
    if "STANDIN_STOPPED" in os.environ:
        sys.exit("Error response from daemon: container c0ffee is not running")
    moved = os.environ["STANDIN_ROOT"]
    words = [word.replace("/tmp/humanize", moved) for word in rest[2:]]
    os.execvp(words[0], words)
elif command == "logs":
    print("humanize: no python 3.12 or newer on this machine")
elif command == "ps":
    print(os.environ.get("STANDIN_PS", ""))
elif command == "inspect":
    print(os.environ.get("STANDIN_INSPECT", "[]"))
    if "STANDIN_INSPECT_SAYS" in os.environ:
        sys.exit(os.environ["STANDIN_INSPECT_SAYS"])
"""


@dataclass
class Standin:
    """The stand-in on `PATH`, and what it was asked."""

    log: Path
    monkeypatch: pytest.MonkeyPatch

    def said(self) -> list[dict[str, Any]]:
        """Every call so far, in order."""
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def subcommands(self, endpoint: Endpoint) -> list[list[str]]:
        """Every call's words after the global flags, each checked to have carried them."""
        flags = endpoint.docker()[endpoint.docker().index("docker") + 1 :]
        answered: list[list[str]] = []
        for one in self.said():
            argv: list[str] = one["argv"]
            assert argv[: len(flags)] == flags, argv
            answered.append(argv[len(flags) :])
        return answered

    def set(self, name: str, value: str) -> None:
        self.monkeypatch.setenv(name, value)


@pytest.fixture
def standin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standin:
    """A `docker` of the test's own, first on `PATH`."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    docker = bin_ / "docker"
    docker.write_text(f"#!{sys.executable}\n{_STANDIN}")
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STANDIN_LOG", str(tmp_path / "docker.log"))
    monkeypatch.setenv("STANDIN_ROOT", str(tmp_path / "container-tmp"))
    # Docker's default here is this machine's, whatever the machine running the tests says.
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    # And a fresh memo of which machines hold the bundle, so each test pays for its own.
    monkeypatch.setattr(transport, "_PUSHED", set[tuple[str, str]]())
    return Standin(tmp_path / "docker.log", monkeypatch)


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "here.txt").write_text("written here\n")
    return workspace


def _value(argv: list[str], flag: str) -> list[str]:
    """Every value `flag` was given in one argv."""
    return [argv[at + 1] for at, word in enumerate(argv[:-1]) if word == flag]


@pytest.mark.parametrize(
    ("endpoint", "flags"),
    [
        ("local", []),
        (
            "unix:///run/user/1000/docker.sock",
            ["--host", "unix:///run/user/1000/docker.sock"],
        ),
        (
            "tcp://10.0.0.5:2376?tls=/etc/docker-certs",
            [
                "--host",
                "tcp://10.0.0.5:2376",
                "--tlsverify",
                "--tlscacert",
                "/etc/docker-certs/ca.pem",
                "--tlscert",
                "/etc/docker-certs/cert.pem",
                "--tlskey",
                "/etc/docker-certs/key.pem",
            ],
        ),
        ("ssh://me@gpu-box:2222", ["--host", "ssh://me@gpu-box:2222"]),
        ("context:gpu-box", ["--context", "gpu-box"]),
    ],
)
def test_every_command_for_a_container_goes_to_its_daemon(
    standin: Standin, tmp_path: Path, endpoint: str, flags: list[str]
) -> None:
    """Started, reached, served and taken down, and each of those said to the one daemon."""
    where = Endpoint.parse(endpoint)
    assert where.docker()[-len(flags) - 1 :] == ["docker", *flags]
    if endpoint != "local":
        # A daemon somewhere else entirely, which no explicit endpoint may be sent to.
        standin.set("DOCKER_HOST", "tcp://elsewhere.invalid:2375")
    standin.set("STANDIN_OWNER", "4242 4343")
    workspace = _workspace(tmp_path)
    machine = DockerConfig(
        image=IMAGE, workspace=str(workspace), endpoint=endpoint
    ).create()

    anchor = machine.start()
    try:
        # The target names the daemon, so whatever reaches the container later reaches it
        # there -- and names none for the default, which is what `docker://NAME` always was.
        assert anchor.target == (
            f"docker://{Target.parse(anchor.target).host}"
            + ("" if endpoint == "local" else f"@{endpoint}")
        )
        with Mapped(anchor) as held:
            assert held.read_text("here.txt") == "written here\n"
            held.write_text("there.txt", "written through the stand-in\n")
            assert held.run(["/bin/sh", "-c", "exit 0"]).ok
    finally:
        machine.stop()

    assert (workspace / "there.txt").read_text() == "written through the stand-in\n"
    assert all(one["DOCKER_HOST"] is None for one in standin.said())
    asked = standin.subcommands(where)
    started = [argv for argv in asked if argv[0] == "run" and "--detach" in argv]
    (run,) = started
    # This user where the daemon is this machine's; the workspace's owner, asked of the
    # daemon's own host, where it is not.
    probed = [argv for argv in asked if argv[:2] == ["run", "--rm"]]
    if where.here:
        assert probed == []
        assert _value(run, "--user") == [f"{os.getuid()}:{os.getgid()}"]
    else:
        assert _value(probed[0], "--mount") == [
            f"type=bind,source={workspace},target={workspace}"
        ]
        assert _value(run, "--user") == ["4242:4343"]
    assert _value(run, "--mount") == [
        f"type=bind,source={workspace},target={workspace}"
    ]
    assert _value(run, "--workdir") == [str(workspace)]
    assert any(argv[:2] == ["exec", "-i"] for argv in asked)
    # And what is removed is what docker said it made, by its id.
    assert asked[-1] == ["rm", "--force", "c0ffee"]


@pytest.mark.parametrize(
    ("gpus", "devices", "said"),
    [
        (
            ("0", "1"),
            ["nvidia.com/gpu=0", "nvidia.com/gpu=1"],
            ["--device", "nvidia.com/gpu=0", "--device", "nvidia.com/gpu=1"],
        ),
        (("0", "1"), [], ["--gpus", '"device=0,1"']),
        ("all", ["nvidia.com/gpu=all"], ["--device", "nvidia.com/gpu=all"]),
        ("all", None, ["--gpus", "all"]),
        (("3",), ["nvidia.com/gpu=0"], ["--gpus", '"device=3"']),
    ],
)
def test_resources_and_gpus_are_said_the_way_docker_takes_them(
    standin: Standin,
    tmp_path: Path,
    gpus: tuple[str, ...] | str,
    devices: list[str] | None,
    said: list[str],
) -> None:
    """GPUs by CDI name where the daemon lists every one asked for, and `--gpus` otherwise."""
    if devices is not None:
        standin.set(
            "STANDIN_DEVICES",
            json.dumps([{"Source": "cdi", "ID": one} for one in devices]),
        )
    machine = DockerConfig(
        image=IMAGE,
        workspace=str(_workspace(tmp_path)),
        cpus=2.5,
        memory=1 << 30,
        shm_size=1 << 28,
        runtime="runc",
        network="bridge",
        gpus=gpus,  # pyright: ignore[reportArgumentType] -- `all` as a flow writes it
        env={"CUDA_CACHE_PATH": "/tmp/cuda"},
        labels={"humanize.provider": "gpu-box", "humanize.cpus": "a lie"},
    ).create()
    machine.start()
    machine.stop()

    (run,) = [
        one["argv"] for one in standin.said() if one["argv"][:2] == ["run", "--detach"]
    ]
    assert _value(run, "--cpus") == ["2.5"]
    assert _value(run, "--memory") == [str(1 << 30)]
    assert _value(run, "--shm-size") == [str(1 << 28)]
    assert _value(run, "--runtime") == ["runc"]
    assert _value(run, "--network") == ["bridge"]
    gpu_flags = [
        word
        for at, word in enumerate(run)
        if word in ("--device", "--gpus") or run[at - 1] in ("--device", "--gpus")
    ]
    assert gpu_flags == said
    # And the runtime told to add none of its own beside the devices named, but not beside
    # `--gpus`, which says which ones in that same variable.
    by_name = said[0] == "--device"
    assert _value(run, "--env") == [
        "HOME=/tmp",
        "CUDA_CACHE_PATH=/tmp/cuda",
        *(["NVIDIA_VISIBLE_DEVICES=void"] if by_name else []),
    ]
    # humanize's own labels over the caller's, since they are what an allocation is read from.
    labels = dict(one.split("=", 1) for one in _value(run, "--label"))
    assert labels == {
        "humanize": str(os.getuid()),
        "humanize.provider": "gpu-box",
        "humanize.cpus": "2.5",
        "humanize.memory": str(1 << 30),
        "humanize.gpus": "all" if gpus == "all" else ",".join(gpus),
    }


def test_a_container_given_no_gpu_is_told_so_last(
    standin: Standin, tmp_path: Path
) -> None:
    """After the caller's variables, so neither an image nor a caller asking for all is heeded.

    And with no label saying it holds what it was not given, whatever the caller wrote.
    """
    machine = DockerConfig(
        image=IMAGE,
        workspace=str(_workspace(tmp_path)),
        env={"NVIDIA_VISIBLE_DEVICES": "all"},
        labels={"humanize.gpus": "0", "humanize.memory": "1", "humanize": "someone"},
    ).create()
    machine.start()
    machine.stop()

    (run,) = [
        one["argv"] for one in standin.said() if one["argv"][:2] == ["run", "--detach"]
    ]
    assert _value(run, "--env")[-1] == "NVIDIA_VISIBLE_DEVICES=void"
    assert _value(run, "--label") == [f"humanize={os.getuid()}"]
    assert not {"--device", "--gpus"} & set(run)


def test_a_container_that_would_not_start_is_removed_by_the_id_docker_gave_it(
    standin: Standin, tmp_path: Path
) -> None:
    standin.set("STANDIN_REFUSE", "1")
    machine = DockerConfig(image=IMAGE, workspace=str(_workspace(tmp_path))).create()

    with pytest.raises(RuntimeError, match="failed to create task"):
        machine.start()

    assert standin.said()[-1]["argv"] == ["rm", "--force", "c0ffee"]


def test_a_name_somebody_else_holds_is_never_removed(
    standin: Standin, tmp_path: Path
) -> None:
    """Docker made nothing, so there is nothing of this machine's to take down."""
    standin.set("STANDIN_TAKEN", "1")
    machine = DockerConfig(
        image=IMAGE, workspace=str(_workspace(tmp_path)), name="somebody-elses"
    ).create()

    with pytest.raises(RuntimeError, match="in use"):
        machine.start()

    assert "rm" not in [one["argv"][0] for one in standin.said()]


def test_a_workspace_a_daemon_elsewhere_has_not_got_is_refused_before_anything_runs(
    standin: Standin,
) -> None:
    machine = DockerConfig(
        image=IMAGE, workspace="/srv/not-there", endpoint="ssh://gpu-box"
    ).create()

    with pytest.raises(FileNotFoundError, match="no directory"):
        machine.start()

    (only,) = standin.subcommands(Endpoint.parse("ssh://gpu-box"))
    assert only[:2] == ["run", "--rm"]


def test_a_relative_workspace_on_a_daemon_elsewhere_is_refused(
    standin: Standin,
) -> None:
    """Relative to this machine's directory, which is no directory of that one."""
    machine = DockerConfig(
        image=IMAGE, workspace="project", endpoint="tcp://10.0.0.5:2375"
    ).create()

    with pytest.raises(ValueError, match="absolute"):
        machine.start()

    assert standin.said() == []


def test_the_bundle_is_pushed_once_per_container_per_daemon(
    standin: Standin,
) -> None:
    """Two containers of one name on two daemons are two machines, each needing its own copy."""
    here = Road.to(Target.parse("docker://box"))
    far = Road.to(Target.parse("docker://box@ssh://gpu-box"))

    assert here.installed() == far.installed()
    here.installed()
    far.installed()

    installs = [one["argv"] for one in standin.said()]
    assert len(installs) == 2
    assert installs[0][:3] == ["exec", "-i", "box"]
    assert installs[1][:5] == ["--host", "ssh://gpu-box", "exec", "-i", "box"]


def test_what_a_stopped_container_said_is_asked_of_its_own_daemon(
    standin: Standin,
) -> None:
    standin.set("STANDIN_STOPPED", "1")
    road = Road.to(Target.parse("docker://box@context:gpu-box"))

    with pytest.raises(
        ConnectionError, match="the container said: humanize: no python"
    ):
        road.installed()

    assert [one["argv"][:3] for one in standin.said()] == [
        ["--context", "gpu-box", "exec"],
        ["--context", "gpu-box", "logs"],
    ]


def test_allocations_are_read_off_the_labels_of_the_running_containers(
    standin: Standin,
) -> None:
    standin.set("STANDIN_PS", "aaa\nbbb")
    standin.set(
        "STANDIN_INSPECT",
        json.dumps(
            [
                {
                    "Name": "/humanize-one",
                    "Config": {
                        "Labels": {
                            "humanize": "1000",
                            "humanize.provider": "gpu-box",
                            "humanize.cpus": "4",
                            "humanize.memory": str(8 << 30),
                            "humanize.gpus": "0,1",
                        }
                    },
                },
                {
                    "Name": "/humanize-two",
                    "Config": {"Labels": {"humanize": "1001", "humanize.gpus": "all"}},
                },
            ]
        ),
    )

    found = allocations("tcp://10.0.0.5:2375", {"humanize.provider": "gpu-box"})

    assert [(one.name, one.cpus, one.memory, one.gpus) for one in found] == [
        ("humanize-one", 4.0, 8 << 30, ("0", "1")),
        ("humanize-two", None, None, "all"),
    ]
    assert found[0].labels["humanize.provider"] == "gpu-box"
    listed, inspected = standin.subcommands(Endpoint.parse("tcp://10.0.0.5:2375"))
    assert listed == [
        "ps",
        "--quiet",
        "--no-trunc",
        "--filter",
        "label=humanize",
        "--filter",
        "label=humanize.provider=gpu-box",
    ]
    assert inspected == ["inspect", "aaa", "bbb"]


def test_nothing_running_is_nothing_allocated(standin: Standin) -> None:
    assert allocations() == []
    assert [one["argv"][0] for one in standin.said()] == ["ps"]


def test_a_daemon_that_could_not_be_asked_is_not_one_with_nothing_on_it(
    standin: Standin,
) -> None:
    """A link lost between the two questions says so, rather than reading as every GPU free."""
    standin.set("STANDIN_PS", "aaa")
    standin.set("STANDIN_INSPECT", "")
    standin.set("STANDIN_INSPECT_SAYS", "error during connect: the link went down")

    with pytest.raises(OSError, match="the link went down"):
        allocations("ssh://gpu-box")


def test_a_container_gone_between_the_questions_leaves_the_rest_counted(
    standin: Standin,
) -> None:
    standin.set("STANDIN_PS", "aaa\nbbb")
    standin.set(
        "STANDIN_INSPECT",
        json.dumps([{"Name": "/one", "Config": {"Labels": {"humanize.cpus": "2"}}}]),
    )
    standin.set("STANDIN_INSPECT_SAYS", "Error: No such object: bbb")

    assert [(one.name, one.cpus) for one in allocations()] == [("one", 2.0)]


def test_a_label_written_wrong_on_somebody_elses_container_counts_as_unsaid(
    standin: Standin,
) -> None:
    standin.set("STANDIN_PS", "aaa")
    standin.set(
        "STANDIN_INSPECT",
        json.dumps(
            [
                {
                    "Name": "/forged",
                    "Config": {
                        "Labels": {"humanize.cpus": "many", "humanize.memory": "1.5e9"}
                    },
                }
            ]
        ),
    )

    (found,) = allocations()

    assert (found.cpus, found.memory) == (None, None)


def test_a_container_made_again_under_its_old_name_is_given_the_bundle_again(
    standin: Standin, tmp_path: Path
) -> None:
    """Which the memo of who holds it would otherwise answer for, from the one before."""
    setting = DockerConfig(image=IMAGE, workspace=str(_workspace(tmp_path)), name="dev")
    for _ in range(2):
        machine = setting.create()
        machine.start()
        machine.stop()

    installs = [
        one["argv"]
        for one in standin.said()
        if one["argv"][:2] == ["exec", "-i"] and "cat >" in " ".join(one["argv"])
    ]
    assert len(installs) == 2


def test_a_rootless_daemon_runs_its_container_as_its_own_root(
    standin: Standin, tmp_path: Path
) -> None:
    """Which is this user, on the host: the uid here would be one of its subordinates."""
    standin.set("STANDIN_SECURITY", json.dumps(["name=seccomp", "name=rootless"]))
    machine = DockerConfig(
        image=IMAGE,
        workspace=str(_workspace(tmp_path)),
        endpoint="unix:///run/user/1000/docker.sock",
    ).create()
    machine.start()
    machine.stop()

    (run,) = [one["argv"] for one in standin.said() if "--detach" in one["argv"]]
    assert _value(run, "--user") == ["0:0"]


def test_a_default_sent_elsewhere_by_docker_host_is_asked_for_the_workspace_there(
    standin: Standin, tmp_path: Path
) -> None:
    standin.set("DOCKER_HOST", "tcp://gpu-box:2375")
    standin.set("STANDIN_OWNER", "4242 4343")
    machine = DockerConfig(image=IMAGE, workspace=str(_workspace(tmp_path))).create()
    machine.start()
    machine.stop()

    runs = [one["argv"] for one in standin.said() if one["argv"][0] == "run"]
    assert runs[0][:2] == ["run", "--rm"]
    assert _value(runs[1], "--user") == ["4242:4343"]


def test_no_docker_here_is_said_as_no_docker_whatever_the_endpoint(
    standin: Standin, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nothing = tmp_path / "empty"
    nothing.mkdir()
    monkeypatch.setenv("PATH", str(nothing))
    machine = DockerConfig(
        image=IMAGE,
        workspace=str(_workspace(tmp_path)),
        endpoint="unix:///run/docker.sock",
    ).create()

    with pytest.raises(FileNotFoundError, match="no docker"):
        machine.start()


def test_an_image_a_daemon_elsewhere_cannot_pull_is_not_a_missing_workspace(
    standin: Standin,
) -> None:
    standin.set("STANDIN_UNPULLED", "1")
    machine = DockerConfig(
        image="typo", workspace="/srv/project", endpoint="ssh://gpu-box"
    ).create()

    with pytest.raises(RuntimeError, match="pull access denied"):
        machine.start()
