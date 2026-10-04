"""A runtime on disk: written down, read back, listed, reached, taken away.

The store touches a filesystem and nothing else -- it reaches no machine and starts no process
-- so what is checked here is that a runtime survives the round trip, that a listing is what
can actually be used, that what no runtime could be is refused before it is a directory, and
that what is written down comes to exactly the `ssh` and `docker` command lines it says.
"""

from __future__ import annotations

import dataclasses
import json
import stat
from pathlib import Path, PurePosixPath

import pytest

from hmz import home, machine
from hmz.coganchor.machines import AnchoredConfig, store
from hmz.coganchor.machines.store import DockerRuntime, SSHRuntime, SwarmRuntime
from hmz.coganchor.transport import Endpoint, Target, ssh_flags
from hmz.flows import EnvBackendKind, EnvUnavailable
from hmz.runtime.flowing.environing import MachineEnvDriver
from hmz.runtime.flowing.environing_ssh import SSHMachine
from hmz.runtime.flowing.environments import open_env
from hmz.runtime.flowing.specs import EnvSpec, EnvSpecError, parse_envs
from hmz.sdk import Hmz

#: Names a directory could hold and a runtime may not have.
_NOT_NAMES = [
    "",
    ".",
    "..",
    "/",
    "sub/name",
    "../evil",
    ".hidden",
    "-dash",
    "two words",
]


#: A home no user has, which `Path.expanduser` raises for rather than answers.
_NOBODY = "~hmz-no-such-user"


def _mode(at: Path) -> int:
    return stat.S_IMODE(at.stat().st_mode)


def test_an_ssh_runtime_is_read_back_as_it_was_written_down() -> None:
    written = store.add(
        SSHRuntime(
            name="gpu",
            host="10.0.0.2",
            user="me",
            port=2222,
            identity_file="~/.ssh/gpu",
            proxy_jump="jump@bastion:22",
            options={"ServerAliveInterval": "5"},
            workdir="~/proj",
            fallback=("docker:box", "ssh:gpu2"),
        )
    )

    assert store.find("ssh", "gpu") == written
    held = json.loads((home() / "runtimes/ssh/gpu/runtime.json").read_text())
    assert held == {
        "backend": "ssh",
        "name": "gpu",
        "host": "10.0.0.2",
        "user": "me",
        "port": 2222,
        "identity_file": "~/.ssh/gpu",
        "proxy_jump": "jump@bastion:22",
        "options": {"ServerAliveInterval": "5"},
        "alias": "",
        "config": "",
        "workdir": "~/proj",
        "fallback": ["docker:box", "ssh:gpu2"],
        "made": "typed",
        "affinity": [],
    }


def test_a_docker_runtime_is_read_back_as_it_was_written_down() -> None:
    written = store.write(
        store.new(
            "docker",
            "box",
            endpoint="tcp://10.0.0.3:2376",
            tls_dir="/certs",
            image="python:3.12",
            runtime="nvidia",
            run_args=["--shm-size", "1g"],
            cpus=8,
            memory=1 << 34,
            gpus=["0", "1"],
            gpu_memory=80 << 30,
            max_containers=4,
            fallback=["ssh:gpu"],
        )
    )

    read = store.find("docker", "box")
    assert read == written
    assert isinstance(read, DockerRuntime)
    assert (read.cpus, read.run_args, read.gpus, read.fallback) == (
        8.0,
        ("--shm-size", "1g"),
        ("0", "1"),
        ("ssh:gpu",),
    )
    assert read.held()["gpus"] == ["0", "1"]
    assert read.held()["fallback"] == ["ssh:gpu"]


def test_a_swarm_runtime_is_read_back_as_it_was_written_down() -> None:
    written = store.write(
        store.new(
            "swarm",
            "cluster",
            endpoint="ssh://me@manager:2222",
            image="python:3.12",
            run_args=["--no-resolve-image"],
            cpus=32,
            memory=1 << 36,
            gpu_resource="NVIDIA-GPU",
            constraints=["node.labels.gpu==true", "node.role != manager"],
            max_tasks=8,
            nodes={"worker1": "gpu1", "worker2": "me@10.0.0.7:2222"},
            workdir="/srv/shared",
        )
    )

    read = store.find("swarm", "cluster")
    assert read == written
    assert isinstance(read, SwarmRuntime)
    assert (read.cpus, read.constraints, read.max_tasks) == (
        32.0,
        ("node.labels.gpu==true", "node.role != manager"),
        8,
    )
    assert read.held()["nodes"] == {"worker1": "gpu1", "worker2": "me@10.0.0.7:2222"}
    assert read.held()["backend"] == "swarm"
    assert read.at == store.under() / "swarm" / "cluster"


@pytest.mark.parametrize(
    ("fields", "said"),
    [
        ({"endpoint": "ftp://x"}, "is not a docker endpoint"),
        ({"tls_dir": "/certs"}, "TLS certificates require a tcp:// endpoint"),
        ({"cpus": -1}, "CPUs cannot be negative"),
        ({"max_tasks": -1}, "tasks cannot be negative"),
        ({"gpu_resource": "NVIDIA GPU"}, "invalid generic resource"),
        ({"constraints": ["node.labels.gpu"]}, "invalid constraint"),
        ({"constraints": ["==x"]}, "invalid constraint"),
        ({"nodes": {"-x": "h"}}, "invalid node host name"),
        ({"nodes": {"w": "me@-oProxyCommand=x"}}, "neither a saved ssh host"),
        ({"nodes": ["w"]}, "nodes cannot be"),
        ({"runtime": "nvidia"}, "unknown swarm host setting 'runtime'"),
        ({"made": "imported"}, "made must be typed for a docker swarm"),
    ],
)
def test_what_no_swarm_runtime_could_be_is_refused(
    fields: dict[str, object], said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        store.new("swarm", "mine", **fields)


def test_a_swarm_node_is_reached_as_a_saved_ssh_host_says_or_as_its_destination() -> (
    None
):
    store.add(SSHRuntime(name="gpu1", host="10.0.0.2", user="me", port=2222))

    assert store.node_of("gpu1") == "ssh:gpu1"
    assert store.node_of("gpu2") == "ssh://gpu2"
    assert store.node_of("me@gpu3:22") == "ssh://me@gpu3:22"
    assert str(store.daemon_of(store.node_of("gpu1"))) == "ssh://me@10.0.0.2:2222"
    with pytest.raises(ValueError, match="neither a saved ssh host"):
        store.node_of("-oProxyCommand=x")


def test_every_level_is_this_users_alone() -> None:
    """What a runtime says is where somebody's machines are, and how they are logged into."""
    store.add(SSHRuntime(name="gpu", host="gpu"))

    for at in (home(), store.under(), store.under() / "ssh", store.where("ssh", "gpu")):
        assert _mode(at) == 0o700, at
    assert _mode(store.where("ssh", "gpu") / "runtime.json") == 0o600


def test_every_runtime_is_listed_by_backend_and_then_by_name() -> None:
    store.add(SSHRuntime(name="second", host="b"))
    store.add(DockerRuntime(name="only"))
    store.add(SSHRuntime(name="first", host="a"))

    assert [(one.backend, one.name) for one in store.runtimes()] == [
        ("ssh", "first"),
        ("ssh", "second"),
        ("docker", "only"),
    ]
    assert [one.name for one in store.runtimes("docker")] == ["only"]
    assert store.runtimes("nope") == []


def test_nothing_is_listed_where_nothing_has_ever_been_written_down() -> None:
    assert not store.under().exists()
    assert store.runtimes() == []
    assert store.find("ssh", "gpu") is None


def test_what_was_kept_as_environment_providers_is_moved_and_read() -> None:
    """The directory they were kept in moves in one piece, and an old file is read as it is."""
    old = home() / "env-providers"
    (old / "docker" / "foo").mkdir(parents=True)
    (old / "docker" / "foo" / "provider.json").write_text(
        json.dumps({"backend": "docker", "name": "foo", "cpus": 2})
    )
    (old / "docker" / ".foo.lock").write_text("")

    assert store.runtimes() == [DockerRuntime(name="foo", cpus=2.0)]
    assert not old.exists()
    assert (home() / "runtimes" / "docker" / ".foo.lock").exists()
    at = store.where("docker", "foo")
    assert (at / "provider.json").exists()

    store.write(DockerRuntime(name="foo", cpus=4))
    assert sorted(one.name for one in at.iterdir()) == ["runtime.json"]
    assert store.find("docker", "foo") == DockerRuntime(name="foo", cpus=4.0)


def test_what_is_kept_now_is_not_written_over_by_what_was_kept_before() -> None:
    store.add(SSHRuntime(name="new", host="h"))
    (home() / "env-providers" / "ssh" / "old").mkdir(parents=True)

    assert [one.name for one in store.runtimes()] == ["new"]
    assert (home() / "env-providers").exists()


def test_a_directory_holding_nothing_usable_is_not_a_runtime() -> None:
    folder = store.add(SSHRuntime(name="usable", host="h")).at.parent
    for name, said in (
        ("broken", "{ not json"),
        ("listed", '["not", "a", "mapping"]'),
        ("wrong", json.dumps({"host": "", "alias": ""})),  # neither: no runtime
        ("unknown", json.dumps({"host": "h", "colour": "red"})),
    ):
        (folder / name).mkdir()
        (folder / name / "runtime.json").write_text(said)
    (folder / "empty").mkdir()
    (folder / ".hidden").mkdir()

    assert [one.name for one in store.runtimes()] == ["usable"]
    for name in ("broken", "listed", "wrong", "unknown", "empty", ".hidden"):
        assert store.find("ssh", name) is None


def test_where_a_runtime_is_kept_is_what_it_is() -> None:
    """The place is the answer; the file only describes it, and may describe it wrongly."""
    at = store.add(SSHRuntime(name="mine", host="h")).at
    (at / "runtime.json").write_text(
        json.dumps({"backend": "docker", "name": "other", "host": "there"})
    )

    assert store.find("ssh", "mine") == SSHRuntime(name="mine", host="there")


@pytest.mark.parametrize("name", _NOT_NAMES)
def test_a_name_that_is_not_a_name_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="invalid runtime name"):
        store.where("ssh", name)
    with pytest.raises(ValueError, match="invalid runtime name"):
        SSHRuntime(name=name, host="h")
    with pytest.raises(ValueError, match="invalid runtime name"):
        store.remove("docker", name)
    assert store.find("ssh", name) is None
    assert not store.under().exists()


def test_a_backend_that_is_not_one_is_refused() -> None:
    for doing in (store.where, store.new, store.remove):
        with pytest.raises(ValueError, match="not a runtime backend"):
            doing("local", "mine")
    assert store.find("local", "mine") is None


def test_adding_one_already_there_is_refused_and_writing_one_replaces_it() -> None:
    store.add(SSHRuntime(name="gpu", host="a", workdir="/srv"))

    with pytest.raises(ValueError, match="ssh host 'gpu' already exists"):
        store.add(SSHRuntime(name="gpu", host="b"))
    assert store.write(SSHRuntime(name="gpu", host="b")) == store.find("ssh", "gpu")
    assert store.find("ssh", "gpu") == SSHRuntime(name="gpu", host="b")


def test_one_is_taken_away_whole() -> None:
    at = store.add(SSHRuntime(name="gpu", host="a")).at

    assert store.remove("ssh", "gpu")
    assert not at.exists()
    assert not store.remove("ssh", "gpu")


@pytest.mark.parametrize(
    ("fields", "said"),
    [
        ({}, "requires a hostname or an alias"),
        ({"host": "-oProxyCommand=evil"}, "invalid ssh host"),
        ({"host": "a b"}, "invalid ssh host"),
        ({"host": "h", "user": "-l"}, "invalid ssh user"),
        ({"alias": "web-*"}, "invalid ssh alias"),
        ({"host": "h", "port": 70000}, "invalid port 70000"),
        ({"host": "h", "proxy_jump": "-J x"}, "invalid jump host"),
        (
            {"host": "h", "identity_file": "a\nb"},
            "identity file .* cannot contain newlines",
        ),
        ({"host": "h", "options": {"User": "root"}}, "must be set with user"),
        ({"host": "h", "options": {"F": "/x"}}, "invalid ssh option 'F'"),
        ({"host": "h", "options": {"-o": "x"}}, "invalid ssh option '-o'"),
        ({"host": "h", "options": {"LogLevel": ""}}, "LogLevel cannot be empty"),
        ({"host": "h", "options": {"SetEnv": 'A="b"'}}, "SetEnv .* newlines or quotes"),
        ({"host": "h", "workdir": "relative/path"}, "must be absolute or under"),
        ({"host": "h", "made": "guessed"}, "typed or imported, not 'guessed'"),
        (
            {"host": "h", "fallback": ["gpu2"]},
            "fallback 'gpu2' must be <backend>:<name>",
        ),
        (
            {"host": "h", "fallback": ["vm:x"]},
            "fallback 'vm:x' must be <backend>:<name>",
        ),
        ({"host": "h", "fallback": ["ssh:../x"]}, "must be <backend>:<name>"),
        ({"host": "h", "fallback": ["ssh:mine"]}, "cannot fall back to itself"),
        ({"host": "h", "fallback": ["ssh:a", "ssh:a"]}, "ssh:a is named twice"),
        ({"host": "h", "fallback": "ssh:a"}, "fallback cannot be 'ssh:a'"),
    ],
)
def test_what_no_ssh_runtime_could_be_is_refused(
    fields: dict[str, object], said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        store.new("ssh", "mine", **fields)


@pytest.mark.parametrize(
    ("fields", "said"),
    [
        ({"endpoint": "docker.sock"}, "is not a docker endpoint"),
        ({"endpoint": "unix://relative.sock"}, "is not a docker endpoint"),
        ({"endpoint": "tcp://host"}, "is not a docker endpoint"),
        ({"endpoint": "tcp://host:0"}, "is not a docker endpoint"),
        ({"endpoint": "tcp://host:99999"}, "is not a docker endpoint"),
        ({"endpoint": "tcp://host:2376?tls=/certs"}, "is not a docker endpoint"),
        ({"endpoint": "context:two words"}, "is not a docker endpoint"),
        ({"endpoint": "ssh://-oProxyCommand=x"}, "is not a docker endpoint"),
        ({"endpoint": "ssh:../x"}, "is not a docker endpoint"),
        ({"endpoint": "context:"}, "is not a docker endpoint"),
        ({"tls_dir": "/certs"}, "require a tcp:// endpoint"),
        ({"image": "two words"}, "invalid image"),
        ({"runtime": "-x"}, "invalid OCI runtime"),
        ({"gpus": ["0", "0"]}, "duplicate GPU"),
        ({"gpus": ["0,1"]}, "invalid GPU id"),
        ({"cpus": -1}, "CPUs cannot be negative"),
        ({"memory": -1}, "memory cannot be negative"),
        ({"made": "imported"}, "made must be typed for a docker host"),
        ({"cpus": "many"}, "cpus cannot be 'many'"),
        ({"memory": True}, "memory cannot be True"),
        ({"gpus": "0"}, "gpus cannot be '0'"),
        ({"host": "h"}, "unknown docker host setting 'host'"),
        ({"fallback": ["docker:mine"]}, "cannot fall back to itself"),
        ({"fallback": ["docker:"]}, "must be <backend>:<name>"),
    ],
)
def test_what_no_docker_runtime_could_be_is_refused(
    fields: dict[str, object], said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        store.new("docker", "mine", **fields)


@pytest.mark.parametrize(
    "endpoint",
    [
        "local",
        "unix:///var/run/docker.sock",
        "tcp://10.0.0.3:2376",
        "ssh://gpu",
        "ssh://me@gpu:2222",
        "ssh:gpu",
        "context:remote",
    ],
)
def test_every_kind_of_endpoint_is_taken(endpoint: str) -> None:
    assert DockerRuntime(name="d", endpoint=endpoint).endpoint == endpoint


def test_an_affinity_is_kept_in_order_and_read_back() -> None:
    written = store.add(
        store.new("docker", "a", affinity=["docker:b", "self", "ssh:gpu", "local"])
    )

    assert written.affinity == ("docker:b", "self", "ssh:gpu", "local")
    assert store.find("docker", "a") == written
    held = json.loads((home() / "runtimes/docker/a/runtime.json").read_text())
    assert held["affinity"] == ["docker:b", "self", "ssh:gpu", "local"]
    assert store.affine("docker:b") == ("docker", "b")
    assert store.affine("swarm:cluster") == ("swarm", "cluster")
    swarm = store.new("swarm", "cluster", affinity=["swarm:other", "docker:a", "local"])
    assert swarm.affinity == ("swarm:other", "docker:a", "local")
    assert store.affine("self") is None
    assert store.affine("local") is None


@pytest.mark.parametrize(
    ("backend", "affinity", "said"),
    [
        ("docker", ["here"], "'here' is not where a harness runs"),
        ("docker", ["ftp:box"], "'ftp:box' is not where a harness runs"),
        ("docker", ["docker:"], "is not where a harness runs"),
        ("docker", ["docker:../x"], "is not where a harness runs"),
        ("docker", ["local", "local"], "local is in its affinity twice"),
        ("docker", ["docker:b", "docker:b"], "docker:b is in its affinity twice"),
        ("docker", ["docker:mine"], "its affinity names itself"),
        ("ssh", ["ssh:mine"], "its affinity names itself"),
        ("swarm", ["swarm:mine"], "its affinity names itself"),
        ("ssh", "self", "affinity cannot be 'self'"),
    ],
)
def test_an_affinity_that_is_not_one_is_refused(
    backend: str, affinity: object, said: str
) -> None:
    fields: dict[str, object] = {"affinity": affinity}
    if backend == "ssh":
        fields["host"] = "h"
    with pytest.raises(ValueError, match=said):
        store.new(backend, "mine", **fields)


def test_an_import_keeps_the_affinity_it_was_given() -> None:
    config = home().parent / "ssh_config"
    config.write_text("Host gpu\n  HostName 10.0.0.2\n")
    (made,) = store.imports(config)
    store.write(dataclasses.replace(made, affinity=("local",)))

    (again,) = store.imports(config, update=True)
    assert again.affinity == ("local",)


def test_what_json_holds_is_read_as_the_field_holds_it() -> None:
    made = store.new("ssh", "gpu", host="h", port=22.0, options={"A": 1})

    assert made == SSHRuntime(name="gpu", host="h", port=22, options={"A": "1"})


# ----------------------------------------------------------------------- reaching one


def test_what_is_written_down_is_what_ssh_is_told() -> None:
    provider = SSHRuntime(
        name="gpu",
        host="10.0.0.2",
        user="me",
        port=2222,
        identity_file="~/.ssh/gpu key",
        proxy_jump="jump@bastion",
        options={"ServerAliveInterval": "5"},
    )

    target = Target.parse(provider.target())

    assert target == Target(
        "ssh",
        host="me@10.0.0.2",
        port=2222,
        options=(
            ("IdentityFile", "~/.ssh/gpu key"),
            ("ProxyJump", "jump@bastion"),
            ("ServerAliveInterval", "5"),
        ),
    )
    assert target.describe() == provider.target()
    assert ssh_flags(target.options) == (
        "-o",
        'IdentityFile="~/.ssh/gpu key"',
        "-o",
        "ProxyJump=jump@bastion",
        "-o",
        "ServerAliveInterval=5",
    )


def test_an_imported_host_is_left_for_its_config_to_resolve() -> None:
    plain = SSHRuntime(name="gpu", alias="gpu-box")
    elsewhere = SSHRuntime(name="gpu", alias="gpu-box", config="/cfg", host="10.9.9.9")

    assert plain.target() == "ssh://gpu-box"
    assert plain.destination() == "gpu-box"
    assert Target.parse(elsewhere.target()).options == (
        ("F", "/cfg"),
        ("HostName", "10.9.9.9"),
    )
    assert ssh_flags(Target.parse(elsewhere.target()).options)[:2] == ("-F", "/cfg")


@pytest.mark.parametrize(
    ("spec", "options"),
    [
        ("ssh://box?LogLevel=ERROR", (("LogLevel", "ERROR"),)),
        ("ssh://u@box:22?F=/a%20b&SetEnv=A%3D1", (("F", "/a b"), ("SetEnv", "A=1"))),
    ],
)
def test_the_options_of_an_ssh_target_round_trip(
    spec: str, options: tuple[tuple[str, str], ...]
) -> None:
    target = Target.parse(spec)

    assert target.options == options
    assert Target.parse(target.describe()) == target


@pytest.mark.parametrize(
    "spec", ["ssh://box?LogLevel", "ssh://box?-o=x", "ssh://box?A=", "ssh://box?A=%22"]
)
def test_an_ssh_target_with_what_is_no_option_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match="malformed target"):
        Target.parse(spec)


@pytest.mark.parametrize(
    ("endpoint", "args"),
    [
        ("local", ()),
        ("unix:///var/run/docker.sock", ("--host", "unix:///var/run/docker.sock")),
        ("tcp://10.0.0.3:2375", ("--host", "tcp://10.0.0.3:2375")),
        ("ssh://me@gpu:2222", ("--host", "ssh://me@gpu:2222")),
        ("context:remote", ("--context", "remote")),
    ],
)
def test_an_endpoint_is_what_docker_is_told(
    endpoint: str, args: tuple[str, ...]
) -> None:
    daemon = DockerRuntime(name="d", endpoint=endpoint).daemon()

    assert daemon == Endpoint.parse(endpoint)
    said = daemon.docker("info")
    assert said[said.index("docker") :] == ["docker", *args, "info"]
    assert not [one for one in said if one.startswith("PATH=")]


def test_a_tls_daemon_is_told_where_its_certificates_are() -> None:
    daemon = store.daemon_of("tcp://10.0.0.3:2376", "/certs")

    assert daemon == Endpoint(host="tcp://10.0.0.3:2376", certs="/certs")
    said = daemon.docker("ps")
    assert said[said.index("docker") :] == [
        "docker",
        "--host",
        "tcp://10.0.0.3:2376",
        "--tlsverify",
        "--tlscacert",
        "/certs/ca.pem",
        "--tlscert",
        "/certs/cert.pem",
        "--tlskey",
        "/certs/key.pem",
        "ps",
    ]


def test_a_path_under_no_home_there_is_is_refused_where_it_is_written_down() -> None:
    """A `~user` the machine has no user for is a runtime nothing could reach."""
    for provider in (
        SSHRuntime(name="s", host="h", config=f"{_NOBODY}/config"),
        DockerRuntime(name="d", endpoint="tcp://h:2376", tls_dir=f"{_NOBODY}/certs"),
    ):
        with pytest.raises(ValueError, match="home directory not found"):
            store.add(provider)
        with pytest.raises(ValueError, match="home directory not found"):
            store.write(provider)
    assert store.runtimes() == []


def test_a_runtime_whose_home_has_gone_is_listed_and_checked_without_raising() -> None:
    """One written down while its home was there: still listed, and asked, said why."""
    for backend, name, field, path in (
        ("docker", "d", "tls_dir", f"{_NOBODY}/certs"),
        ("ssh", "s", "config", f"{_NOBODY}/config"),
    ):
        at = store.where(backend, name)
        at.mkdir(parents=True)
        held = (
            {"endpoint": "tcp://10.0.0.3:2376"}
            if backend == "docker"
            else {"host": "h"}
        )
        (at / "runtime.json").write_text(json.dumps({**held, field: path}))

    listed = store.runtimes()

    assert [(one.backend, one.name) for one in listed] == [
        ("ssh", "s"),
        ("docker", "d"),
    ]
    for provider in listed:
        checked = Hmz().runtimes.check(provider, seconds=5)

        assert not checked.reached
        assert "home directory not found" in checked.said
    with pytest.raises(ValueError, match="home directory not found"):
        store.daemon_of("tcp://10.0.0.3:2376", f"{_NOBODY}/certs")


def test_a_daemon_behind_a_stored_ssh_host_is_dialled_as_that_host_says() -> None:
    store.add(SSHRuntime(name="plain", host="gpu", user="me", port=2222))
    store.add(SSHRuntime(name="keyed", host="gpu", identity_file="~/.ssh/k"))

    plain = store.daemon_of("ssh:plain")
    keyed = store.daemon_of("ssh:keyed")

    assert plain == Endpoint(host="ssh://me@gpu:2222")
    assert keyed == Endpoint(host="ssh://gpu", options=(("IdentityFile", "~/.ssh/k"),))
    assert Endpoint.parse(str(keyed)) == keyed
    said = keyed.docker("ps")
    (path,) = [one for one in said if one.startswith("PATH=")]
    shim = Path(path.removeprefix("PATH=").split(":")[0])
    assert shim.parent == machine() / "docker-ssh"
    assert said[said.index("docker") :] == ["docker", "--host", "ssh://gpu", "ps"]
    assert "exec ssh -o 'IdentityFile=~/.ssh/k' \"$@\"" in (shim / "ssh").read_text()
    assert _mode(shim / "ssh") == 0o700
    # The same options are the same `ssh`, written once.
    assert [one for one in store.daemon_of("ssh:keyed").docker("ps") if "PATH=" in one]
    assert len(list((machine() / "docker-ssh").iterdir())) == 1
    # And written again where a cleaner of the temporary directory took it away since.
    (shim / "ssh").unlink()
    assert store.daemon_of("ssh:keyed").docker("ps")
    assert (shim / "ssh").is_file()
    with pytest.raises(ValueError, match="ssh host 'ghost' not found"):
        store.daemon_of("ssh:ghost")


# ------------------------------------------------------------------------- what -e names


def test_an_e_naming_a_stored_runtime_reaches_it_as_it_says() -> None:
    provider = SSHRuntime(
        name="gpu", host="10.0.0.2", user="me", options={"LogLevel": "ERROR"}
    )
    store.add(provider)

    (spec,) = parse_envs(["box=ssh@gpu/srv/proj"])
    driver = open_env(spec)

    assert spec.provider == "gpu"
    assert isinstance(driver, MachineEnvDriver)
    assert driver.provider == "gpu"
    machine = driver._machine
    assert isinstance(machine, SSHMachine)
    assert machine.target == provider.target()
    placement = driver.placement()
    assert placement.provider == "gpu"
    assert isinstance(placement.machine, AnchoredConfig)
    assert placement.machine.anchor.target == provider.target()


def test_an_e_naming_a_host_in_brackets_is_the_host_ssh_is_handed() -> None:
    """Even where a runtime is saved under the same name: the brackets are the host's."""
    store.add(SSHRuntime(name="gpu-box", host="10.0.0.2"))

    (spec,) = parse_envs(["box=ssh@[gpu-box]/srv"])
    driver = open_env(spec)

    assert isinstance(driver, MachineEnvDriver)
    assert isinstance(driver._machine, SSHMachine)
    assert driver._machine.target == "ssh://gpu-box"
    (spec,) = parse_envs(["box=ssh@[me@gpu-box:22]/srv"])
    driver = open_env(spec)
    assert isinstance(driver, MachineEnvDriver)
    assert isinstance(driver._machine, SSHMachine)
    assert driver._machine.target == "ssh://me@gpu-box:22"


def test_an_ssh_runtime_nobody_saved_is_refused_where_it_is_opened() -> None:
    """A spec made by hand rather than read, which `-e` would have refused already."""
    spec = EnvSpec("box", EnvBackendKind.SSH, "ghost", PurePosixPath("/srv"))
    with pytest.raises(EnvUnavailable, match=r"ssh@\[ghost\]"):
        open_env(spec)


def test_an_e_naming_a_stored_runtime_that_cannot_be_read_is_refused() -> None:
    """Rather than taken for a host of that name, which is somewhere nobody meant."""
    at = store.add(SSHRuntime(name="gpu", host="10.0.0.2")).at
    (at / "runtime.json").write_text("{ broken")

    (spec,) = parse_envs(["box=ssh@gpu/srv"])
    with pytest.raises(EnvUnavailable, match="'gpu' cannot be read"):
        open_env(spec)


def test_an_e_naming_a_swarm_nobody_saved_is_refused_and_naming_none_is_the_one_here() -> (
    None
):
    with pytest.raises(EnvSpecError, match="no swarm runtime is saved as 'ghost'"):
        parse_envs(["box=swarm@ghost/srv"])
    named = EnvSpec("box", EnvBackendKind.SWARM, "ghost", PurePosixPath("/srv"))
    with pytest.raises(EnvUnavailable, match="docker swarm 'ghost' not found"):
        open_env(named)

    (here,) = parse_envs(["box=swarm/srv"])
    driver = open_env(here)
    assert isinstance(driver, MachineEnvDriver)
    assert driver.backend is EnvBackendKind.SWARM
    assert driver.provider == "local"


def test_an_e_naming_a_swarm_elsewhere_with_a_workdir_under_home_is_refused() -> None:
    store.add(SwarmRuntime(name="far", endpoint="ssh://manager"))

    (spec,) = parse_envs(["box=swarm@far/~/proj"])
    with pytest.raises(EnvUnavailable, match="remote docker swarm"):
        open_env(spec)
    assert parse_envs(["box=swarm/~/proj"])[0].provider == ""


def test_an_e_with_no_workdir_takes_the_one_its_runtime_was_given() -> None:
    store.add(SSHRuntime(name="home", host="h", workdir="~/proj"))
    store.add(SSHRuntime(name="root", host="h", workdir="/srv/proj"))
    store.add(SSHRuntime(name="none", host="h"))

    assert parse_envs(["a=ssh@home", "b=ssh@root"]) == parse_envs(
        ["a=ssh@home/~/proj", "b=ssh@root/srv/proj"]
    )
    assert parse_envs(["a=ssh@home"])[0].workdir == PurePosixPath("~/proj")
    assert parse_envs(["a=ssh@home"])[0].backend is EnvBackendKind.SSH
    for said, why in (
        ("a=ssh@none", "left off only for a runtime saved with one"),
        ("a=ssh@ghost", "no ssh host is saved as 'ghost'"),
        ("a=ssh", "ssh needs a host"),
    ):
        with pytest.raises(EnvSpecError, match=why):
            parse_envs([said])


# ------------------------------------------------------------------------- falling back


def test_a_runtime_falls_back_to_its_own_list_and_no_further() -> None:
    store.write(DockerRuntime(name="a", fallback=("docker:b", "ssh:gpu")))
    store.write(DockerRuntime(name="b", fallback=("docker:c",)))

    assert store.fallbacks("docker", "a") == (("docker", "b"), ("ssh", "gpu"))
    assert store.fallbacks("docker", "b") == (("docker", "c"),)
    assert store.fallbacks("docker", "c") == ()
    assert store.fallbacks("ssh", "gpu") == ()
    assert store.fallbacks("local", "") == ()


def test_a_runtime_may_fall_back_to_one_of_another_backend_under_its_own_name() -> None:
    assert SSHRuntime(name="x", host="h", fallback=("docker:x",)).fallback == (
        "docker:x",
    )


def test_what_an_e_falls_back_to_works_where_its_runtime_says_or_where_it_was_told() -> (
    None
):
    from hmz.runtime.flowing.specs import fallbacks

    store.write(SSHRuntime(name="gpu2", host="h", workdir="~/elsewhere"))
    store.write(DockerRuntime(name="box"))
    store.write(
        DockerRuntime(name="main", fallback=("ssh:gpu2", "docker:box", "docker:gone"))
    )
    (spec,) = parse_envs(["work=docker@main/srv/x"])

    assert [str(one) for one in fallbacks(spec)] == [
        "work=ssh@gpu2/~/elsewhere",
        "work=docker@box/srv/x",
        "work=docker@gone/srv/x",
    ]


def test_a_list_falling_back_to_docker_local_falls_back_to_docker_here() -> None:
    """The one name a list has for docker's default here, unless a runtime is saved so."""
    from hmz.runtime.flowing.specs import fallbacks

    store.write(DockerRuntime(name="main", fallback=("docker:local", "swarm:local")))
    (spec,) = parse_envs(["work=docker@main/srv/x"])

    assert [str(one) for one in fallbacks(spec)] == [
        "work=docker/srv/x",
        "work=swarm/srv/x",
    ]
    store.write(DockerRuntime(name="local"))
    assert str(fallbacks(spec)[0]) == "work=docker@local/srv/x"


@pytest.mark.parametrize(
    "said", ["work=local/srv/x", "work=ssh@[me@h]/srv/x", "work=docker/srv/x"]
)
def test_an_e_naming_no_saved_runtime_falls_back_to_nothing(said: str) -> None:
    from hmz.runtime.flowing.specs import fallbacks

    (spec,) = parse_envs([said])

    assert fallbacks(spec) == []


def test_an_import_updating_a_host_keeps_what_it_falls_back_to(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host gpu\n  HostName 10.0.0.2\n")
    (made,) = store.imports(config)
    store.write(
        SSHRuntime(
            name=made.name,
            alias=made.alias,
            config=made.config,
            made=made.made,
            fallback=("docker:box",),
        )
    )

    (again,) = store.imports(config, update=True)

    assert again.fallback == ("docker:box",)


def test_the_sdk_writes_and_reads_a_fallback_list() -> None:
    runtimes = Hmz().runtimes
    runtimes.write(runtimes.new("docker", "a", fallback=["docker:b", "ssh:c"]))

    found = runtimes.find("docker", "a")

    assert found is not None
    assert found.fallback == ("docker:b", "ssh:c")


def test_a_swarm_falls_back_and_is_fallen_back_to_like_any_runtime() -> None:
    from hmz.runtime.flowing.specs import fallbacks

    store.write(store.SwarmRuntime(name="cluster", fallback=("docker:box",)))
    store.write(DockerRuntime(name="main", fallback=("swarm:cluster",)))
    (spec,) = parse_envs(["work=docker@main/srv/x"])

    assert store.fallbacks("swarm", "cluster") == (("docker", "box"),)
    assert [str(one) for one in fallbacks(spec)] == ["work=swarm@cluster/srv/x"]
    with pytest.raises(ValueError, match="cannot fall back to itself"):
        store.SwarmRuntime(name="cluster", fallback=("swarm:cluster",))
