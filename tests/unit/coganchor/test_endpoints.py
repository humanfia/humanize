"""Which docker daemon a container is reached through, as a spelling and as a command line.

All of it is reading and writing: an endpoint spelled, the `docker` argv that reaches it, the
target a container on it is named by, and the settings a container is refused for -- nothing
here runs `docker`. What the argv does to a daemon is `tests/integration/machines/test_docker.py`
against a stand-in, and `tests/system/machines/` against the real one.
"""

from __future__ import annotations

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import DockerConfig
from hmz.coganchor.transport import Endpoint, Road, Target

#: What takes a `docker` off to another daemon, taken off every one sent to an explicit one.
_UNSET = [
    "-u",
    "DOCKER_HOST",
    "-u",
    "DOCKER_CONTEXT",
    "-u",
    "DOCKER_TLS",
    "-u",
    "DOCKER_TLS_VERIFY",
    "-u",
    "DOCKER_CERT_PATH",
]


@pytest.mark.parametrize(
    ("spec", "argv", "here"),
    [
        ("local", ["docker", "ps"], True),
        (
            "unix:///var/run/docker.sock",
            ["env", *_UNSET, "docker", "--host", "unix:///var/run/docker.sock", "ps"],
            True,
        ),
        (
            "tcp://10.0.0.5:2375",
            ["env", *_UNSET, "docker", "--host", "tcp://10.0.0.5:2375", "ps"],
            False,
        ),
        (
            "tcp://[::1]:2376?tls=/certs",
            [
                "env",
                *_UNSET,
                "docker",
                "--host",
                "tcp://[::1]:2376",
                "--tlsverify",
                "--tlscacert",
                "/certs/ca.pem",
                "--tlscert",
                "/certs/cert.pem",
                "--tlskey",
                "/certs/key.pem",
                "ps",
            ],
            False,
        ),
        (
            "ssh://me@gpu-box:2222",
            ["env", *_UNSET, "docker", "--host", "ssh://me@gpu-box:2222", "ps"],
            False,
        ),
        (
            "context:gpu-box",
            ["env", *_UNSET, "docker", "--context", "gpu-box", "ps"],
            False,
        ),
    ],
)
def test_an_endpoint_is_said_to_docker_and_to_nothing_else(
    spec: str, argv: list[str], here: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    endpoint = Endpoint.parse(spec)

    assert endpoint.docker("ps") == argv
    assert endpoint.here is here
    assert str(endpoint) == spec
    assert Endpoint.parse(str(endpoint)) == endpoint


def test_the_default_is_spelled_local_or_not_at_all() -> None:
    assert Endpoint.parse("") == Endpoint.parse("local") == Endpoint()
    assert str(Endpoint()) == "local"


@pytest.mark.parametrize(
    "spec",
    [
        "docker",
        "unix://relative.sock",
        "tcp://10.0.0.5",
        "tcp://10.0.0.5:port",
        "tcp://10.0.0.5:2376?tls=relative/certs",
        "tcp://10.0.0.5:2376?verify=1",
        "ssh://",
        "ssh://me@",
        "ssh://gpu-box/path",
        "context:",
        "npipe:////./pipe/docker_engine",
    ],
)
def test_an_endpoint_docker_could_not_read_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match="docker endpoint"):
        Endpoint.parse(spec)


def test_a_container_target_carries_its_daemon() -> None:
    far = Target.parse("docker://janus@ssh://me@gpu-box:2222")

    assert far == Target("docker", host="janus", path="ssh://me@gpu-box:2222")
    assert far.endpoint == Endpoint(host="ssh://me@gpu-box:2222")
    assert far.describe() == "docker://janus@ssh://me@gpu-box:2222"
    # And a container on the default names none, however the default was written.
    assert Target.parse("docker://janus@local") == Target.parse("docker://janus")
    assert Target.parse("docker://janus").endpoint == Endpoint()
    assert Target.parse("docker://janus").describe() == "docker://janus"


def test_only_a_container_has_a_daemon() -> None:
    with pytest.raises(ValueError, match="not a container"):
        _ = Target.parse("ssh://gpu-box").endpoint


def test_the_road_to_a_container_goes_to_its_daemon() -> None:
    road = Road.to(Target.parse("docker://janus@context:gpu-box"))

    assert road.line(["true"]) == [
        "env",
        *_UNSET,
        "docker",
        "--context",
        "gpu-box",
        "exec",
        "-i",
        "janus",
        "true",
    ]
    assert Road.to(Target.parse("docker://janus")).line(["true"]) == [
        "docker",
        "exec",
        "-i",
        "janus",
        "true",
    ]


def test_a_containers_daemon_is_no_part_of_the_workspace_it_exports() -> None:
    """The workspace is at the same path on both sides; the daemon is not a directory."""
    anchor = AnchorConfig(
        target="docker://janus@unix:///run/docker.sock", workspace="/srv/project"
    )

    assert anchor.mount()[2] == "/srv/project"


def test_docker_host_sending_the_default_elsewhere_makes_it_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "tcp://gpu-box:2375")
    assert not Endpoint().here
    # Where the default goes and where an explicit endpoint goes are two questions.
    assert Endpoint.parse("unix:///var/run/docker.sock").here
    monkeypatch.setenv("DOCKER_HOST", "unix:///run/user/1000/docker.sock")
    assert Endpoint().here


def test_a_container_setting_is_a_value_that_holds_still() -> None:
    """Hashable like any frozen setting, and deaf to the caller's dictionary changing."""
    asked = {"A": "b"}
    setting = DockerConfig(env=asked, labels={"humanize.provider": "gpu-box"})
    asked["A"] = "changed"

    assert setting.env == {"A": "b"}
    assert hash(setting) == hash(DockerConfig(env={"A": "b"}))
    assert setting == DockerConfig(
        env={"A": "b"}, labels={"humanize.provider": "gpu-box"}
    )
    assert setting != DockerConfig(
        env={"A": "c"}, labels={"humanize.provider": "gpu-box"}
    )


def test_a_container_setting_reads_its_gpus_as_ids() -> None:
    assert DockerConfig(gpus=(0, 1)).gpus == ("0", "1")  # pyright: ignore[reportArgumentType]
    assert DockerConfig(gpus="all").gpus == "all"
    assert DockerConfig().gpus == ()


@pytest.mark.parametrize(
    "setting",
    [
        {"endpoint": "tcp://nowhere"},
        {"name": "-leading-dash"},
        {"cpus": 0},
        {"memory": -1},
        {"shm_size": 0},
        {"gpus": "0"},
        {"gpus": ("0,1",)},
        {"gpus": ("",)},
        {"env": {"A=B": "c"}},
        {"labels": {"": "c"}},
    ],
)
def test_a_container_setting_docker_would_refuse_is_refused_where_it_is_written(
    setting: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match=r"endpoint|name|more than nothing|gpus"):
        DockerConfig(**setting)  # pyright: ignore[reportArgumentType]
