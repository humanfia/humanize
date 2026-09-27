"""An environment provider on disk: written down, read back, listed, reached, taken away.

The store touches a filesystem and nothing else -- it reaches no machine and starts no process
-- so what is checked here is that a provider survives the round trip, that a listing is what
can actually be used, that what no provider could be is refused before it is a directory, and
that what is written down comes to exactly the `ssh` and `docker` command lines it says.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path, PurePosixPath

import pytest

from hmz import home
from hmz.coganchor.machines import AnchoredConfig, store
from hmz.coganchor.machines.store import DockerProvider, SSHProvider
from hmz.coganchor.transport import Endpoint, Target, ssh_flags
from hmz.flows import EnvBackendKind, EnvUnavailable
from hmz.runtime.flowing.environing import MachineEnvDriver
from hmz.runtime.flowing.environing_ssh import SSHMachine
from hmz.runtime.flowing.environments import open_env
from hmz.runtime.flowing.specs import EnvSpecError, parse_envs
from hmz.sdk import Hmz

#: Names a directory could hold and a provider may not have.
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


def test_an_ssh_provider_is_read_back_as_it_was_written_down() -> None:
    written = store.add(
        SSHProvider(
            name="gpu",
            host="10.0.0.2",
            user="me",
            port=2222,
            identity_file="~/.ssh/gpu",
            proxy_jump="jump@bastion:22",
            options={"ServerAliveInterval": "5"},
            workdir="~/proj",
        )
    )

    assert store.find("ssh", "gpu") == written
    held = json.loads((home() / "env-providers/ssh/gpu/provider.json").read_text())
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
        "made": "typed",
    }


def test_a_docker_provider_is_read_back_as_it_was_written_down() -> None:
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
        )
    )

    read = store.find("docker", "box")
    assert read == written
    assert isinstance(read, DockerProvider)
    assert (read.cpus, read.run_args, read.gpus) == (
        8.0,
        ("--shm-size", "1g"),
        ("0", "1"),
    )
    assert read.held()["gpus"] == ["0", "1"]


def test_every_level_is_this_users_alone() -> None:
    """What a provider says is where somebody's machines are, and how they are logged into."""
    store.add(SSHProvider(name="gpu", host="gpu"))

    for at in (home(), store.under(), store.under() / "ssh", store.where("ssh", "gpu")):
        assert _mode(at) == 0o700, at
    assert _mode(store.where("ssh", "gpu") / "provider.json") == 0o600


def test_every_provider_is_listed_by_backend_and_then_by_name() -> None:
    store.add(SSHProvider(name="second", host="b"))
    store.add(DockerProvider(name="only"))
    store.add(SSHProvider(name="first", host="a"))

    assert [(one.backend, one.name) for one in store.providers()] == [
        ("ssh", "first"),
        ("ssh", "second"),
        ("docker", "only"),
    ]
    assert [one.name for one in store.providers("docker")] == ["only"]
    assert store.providers("nope") == []


def test_nothing_is_listed_where_nothing_has_ever_been_written_down() -> None:
    assert not store.under().exists()
    assert store.providers() == []
    assert store.find("ssh", "gpu") is None


def test_a_directory_holding_nothing_usable_is_not_a_provider() -> None:
    folder = store.add(SSHProvider(name="usable", host="h")).at.parent
    for name, said in (
        ("broken", "{ not json"),
        ("listed", '["not", "a", "mapping"]'),
        ("wrong", json.dumps({"host": "", "alias": ""})),  # neither: no provider
        ("unknown", json.dumps({"host": "h", "colour": "red"})),
    ):
        (folder / name).mkdir()
        (folder / name / "provider.json").write_text(said)
    (folder / "empty").mkdir()
    (folder / ".hidden").mkdir()

    assert [one.name for one in store.providers()] == ["usable"]
    for name in ("broken", "listed", "wrong", "unknown", "empty", ".hidden"):
        assert store.find("ssh", name) is None


def test_where_a_provider_is_kept_is_what_it_is() -> None:
    """The place is the answer; the file only describes it, and may describe it wrongly."""
    at = store.add(SSHProvider(name="mine", host="h")).at
    (at / "provider.json").write_text(
        json.dumps({"backend": "docker", "name": "other", "host": "there"})
    )

    assert store.find("ssh", "mine") == SSHProvider(name="mine", host="there")


@pytest.mark.parametrize("name", _NOT_NAMES)
def test_a_name_that_is_not_a_name_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="is not an environment provider name"):
        store.where("ssh", name)
    with pytest.raises(ValueError, match="is not an environment provider name"):
        SSHProvider(name=name, host="h")
    with pytest.raises(ValueError, match="is not an environment provider name"):
        store.remove("docker", name)
    assert store.find("ssh", name) is None
    assert not store.under().exists()


def test_a_backend_that_is_not_one_is_refused() -> None:
    for doing in (store.where, store.new, store.remove):
        with pytest.raises(ValueError, match="not an environment backend"):
            doing("local", "mine")
    assert store.find("local", "mine") is None


def test_adding_one_already_there_is_refused_and_writing_one_replaces_it() -> None:
    store.add(SSHProvider(name="gpu", host="a", workdir="/srv"))

    with pytest.raises(ValueError, match="already has a provider called 'gpu'"):
        store.add(SSHProvider(name="gpu", host="b"))
    assert store.write(SSHProvider(name="gpu", host="b")) == store.find("ssh", "gpu")
    assert store.find("ssh", "gpu") == SSHProvider(name="gpu", host="b")


def test_one_is_taken_away_whole() -> None:
    at = store.add(SSHProvider(name="gpu", host="a")).at

    assert store.remove("ssh", "gpu")
    assert not at.exists()
    assert not store.remove("ssh", "gpu")


@pytest.mark.parametrize(
    ("fields", "said"),
    [
        ({}, "needs a host or an alias"),
        ({"host": "-oProxyCommand=evil"}, "is not an ssh host"),
        ({"host": "a b"}, "is not an ssh host"),
        ({"host": "h", "user": "-l"}, "is not an ssh user"),
        ({"alias": "web-*"}, "is not an ssh alias"),
        ({"host": "h", "port": 70000}, "is not a port"),
        ({"host": "h", "proxy_jump": "-J x"}, "is not a jump host"),
        ({"host": "h", "identity_file": "a\nb"}, "more than one line"),
        ({"host": "h", "options": {"User": "root"}}, "is said with user"),
        ({"host": "h", "options": {"F": "/x"}}, "is not an ssh option"),
        ({"host": "h", "options": {"-o": "x"}}, "is not an ssh option"),
        ({"host": "h", "options": {"LogLevel": ""}}, "says nothing"),
        ({"host": "h", "options": {"SetEnv": 'A="b"'}}, "holds a quote"),
        ({"host": "h", "workdir": "relative/path"}, "neither absolute nor under"),
        ({"host": "h", "config": f"{_NOBODY}/config"}, "under no home"),
        ({"host": "h", "made": "guessed"}, "not typed or imported"),
    ],
)
def test_what_no_ssh_provider_could_be_is_refused(
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
        ({"tls_dir": "/certs"}, "for a tcp:// endpoint"),
        ({"endpoint": "tcp://h:2376", "tls_dir": f"{_NOBODY}/certs"}, "under no home"),
        ({"image": "two words"}, "is not an image"),
        ({"runtime": "-x"}, "is not a runtime"),
        ({"gpus": ["0", "0"]}, "named twice"),
        ({"gpus": ["0,1"]}, "is not a GPU id"),
        ({"cpus": -1}, "is not an amount of CPUs"),
        ({"memory": -1}, "is not an amount of memory"),
        ({"made": "imported"}, "only ever typed"),
        ({"cpus": "many"}, "cannot be"),
        ({"memory": True}, "cannot be"),
        ({"gpus": "0"}, "cannot be"),
        ({"host": "h"}, "has no 'host'"),
    ],
)
def test_what_no_docker_provider_could_be_is_refused(
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
    assert DockerProvider(name="d", endpoint=endpoint).endpoint == endpoint


def test_what_json_holds_is_read_as_the_field_holds_it() -> None:
    made = store.new("ssh", "gpu", host="h", port=22.0, options={"A": 1})

    assert made == SSHProvider(name="gpu", host="h", port=22, options={"A": "1"})


# ----------------------------------------------------------------------- reaching one


def test_what_is_written_down_is_what_ssh_is_told() -> None:
    provider = SSHProvider(
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
    plain = SSHProvider(name="gpu", alias="gpu-box")
    elsewhere = SSHProvider(name="gpu", alias="gpu-box", config="/cfg", host="10.9.9.9")

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
    daemon = DockerProvider(name="d", endpoint=endpoint).daemon()

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


def test_a_provider_whose_home_has_gone_is_checked_without_raising() -> None:
    """One written down while its home was there, asked after: said why, not raised."""
    docker = DockerProvider(name="d", endpoint="tcp://10.0.0.3:2376", tls_dir="~/certs")
    ssh = SSHProvider(name="s", host="h", config="~/config")
    object.__setattr__(docker, "tls_dir", f"{_NOBODY}/certs")
    object.__setattr__(ssh, "config", f"{_NOBODY}/config")

    for provider in (docker, ssh):
        checked = Hmz().environments.check(provider, seconds=5)

        assert not checked.reached
        assert "under no home there is" in checked.said
    with pytest.raises(ValueError, match="under no home there is"):
        store.daemon_of("tcp://10.0.0.3:2376", f"{_NOBODY}/certs")


def test_a_daemon_behind_a_stored_ssh_host_is_dialled_as_that_host_says() -> None:
    store.add(SSHProvider(name="plain", host="gpu", user="me", port=2222))
    store.add(SSHProvider(name="keyed", host="gpu", identity_file="~/.ssh/k"))

    plain = store.daemon_of("ssh:plain")
    keyed = store.daemon_of("ssh:keyed")

    assert plain == Endpoint(host="ssh://me@gpu:2222")
    assert keyed == Endpoint(host="ssh://gpu", options=(("IdentityFile", "~/.ssh/k"),))
    assert Endpoint.parse(str(keyed)) == keyed
    said = keyed.docker("ps")
    (path,) = [one for one in said if one.startswith("PATH=")]
    shim = Path(path.removeprefix("PATH=").split(":")[0])
    assert shim.parent == home() / "docker-ssh"
    assert said[said.index("docker") :] == ["docker", "--host", "ssh://gpu", "ps"]
    assert "exec ssh -o 'IdentityFile=~/.ssh/k' \"$@\"" in (shim / "ssh").read_text()
    assert _mode(shim / "ssh") == 0o700
    # The same options are the same `ssh`, written once.
    assert [one for one in store.daemon_of("ssh:keyed").docker("ps") if "PATH=" in one]
    assert len(list((home() / "docker-ssh").iterdir())) == 1
    with pytest.raises(ValueError, match="no ssh provider called 'ghost'"):
        store.daemon_of("ssh:ghost")


# ------------------------------------------------------------------------- what -e names


def test_an_e_naming_a_stored_provider_reaches_it_as_it_says() -> None:
    provider = SSHProvider(
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


def test_an_e_naming_no_stored_provider_is_the_host_ssh_is_handed() -> None:
    (spec,) = parse_envs(["box=ssh@me@gpu-box:22/srv"])
    driver = open_env(spec)

    assert isinstance(driver, MachineEnvDriver)
    assert isinstance(driver._machine, SSHMachine)
    assert driver._machine.target == "ssh://me@gpu-box:22"


def test_an_e_naming_a_stored_provider_that_cannot_be_read_is_refused() -> None:
    """Rather than taken for a host of that name, which is somewhere nobody meant."""
    at = store.add(SSHProvider(name="gpu", host="10.0.0.2")).at
    (at / "provider.json").write_text("{ broken")

    (spec,) = parse_envs(["box=ssh@gpu/srv"])
    with pytest.raises(EnvUnavailable, match="'gpu' cannot be read"):
        open_env(spec)


def test_an_e_with_no_workdir_takes_the_one_its_provider_was_given() -> None:
    store.add(SSHProvider(name="home", host="h", workdir="~/proj"))
    store.add(SSHProvider(name="root", host="h", workdir="/srv/proj"))
    store.add(SSHProvider(name="none", host="h"))

    assert parse_envs(["a=ssh@home", "b=ssh@root"]) == parse_envs(
        ["a=ssh@home/~/proj", "b=ssh@root/srv/proj"]
    )
    assert parse_envs(["a=ssh@home"])[0].workdir == PurePosixPath("~/proj")
    assert parse_envs(["a=ssh@home"])[0].backend is EnvBackendKind.SSH
    for said in ("a=ssh@none", "a=ssh@ghost", "a=ssh"):
        with pytest.raises(EnvSpecError, match="expected"):
            parse_envs([said])
