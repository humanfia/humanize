"""The runtimes written down in humanize's settings: `hmz.coganchor.machines.store`."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from hmz.coganchor import settings
from hmz.coganchor.machines.store import (
    APPLE_CONTAINER,
    BACKENDS,
    DOCKER,
    HERE,
    IMPORTED,
    SELF,
    SSH,
    SWARM,
    AppleContainerRuntime,
    DockerRuntime,
    SSHRuntime,
    SwarmRuntime,
    add,
    affine,
    daemon_of,
    fallbacks,
    find,
    imports,
    new,
    node_of,
    remove,
    respelled,
    runtimes,
    saved,
    write,
)
from hmz.coganchor.transport import Endpoint

if TYPE_CHECKING:
    from pathlib import Path


def written() -> dict[str, Any]:
    return yaml.safe_load(settings.where().read_text())


# ------------------------------------------------------------------------------ affine


@pytest.mark.parametrize(
    ("entry", "said"),
    [
        (SELF, None),
        (HERE, None),
        ("ssh:gpu", (SSH, "gpu")),
        ("swarm:s.1", (SWARM, "s.1")),
    ],
)
def test_an_affinity_entry_names_a_runtime_or_one_of_the_two_places(
    entry: str, said: tuple[str, str] | None
) -> None:
    assert affine(entry) == said


@pytest.mark.parametrize("entry", ["", "ssh", "ftp:x", "ssh:", "ssh:-x", "docker:a/b"])
def test_an_affinity_entry_that_does_not_read_is_refused(entry: str) -> None:
    with pytest.raises(ValueError, match="is not where a harness runs"):
        affine(entry)


# ------------------------------------------------------------------------- SSHRuntime


def test_an_ssh_runtime_is_reached_with_everything_it_says() -> None:
    runtime = SSHRuntime(
        name="gpu",
        host="10.0.0.1",
        user="me",
        port=2222,
        identity_file="/keys/id",
        proxy_jump="jump@bastion:22",
        options={"ServerAliveInterval": "30"},
        alias="gpu-alias",
        config="/etc/ssh/other",
    )

    assert runtime.destination() == "gpu-alias"
    assert runtime.login() == "me@gpu-alias"
    assert runtime.settings() == (
        ("F", "/etc/ssh/other"),
        ("HostName", "10.0.0.1"),
        ("IdentityFile", "/keys/id"),
        ("ProxyJump", "jump@bastion:22"),
        ("ServerAliveInterval", "30"),
    )
    assert runtime.target().startswith("ssh://me@gpu-alias:2222?")
    assert runtime.at == settings.where()


def test_a_bare_ssh_runtime_is_its_host() -> None:
    runtime = SSHRuntime(name="box", host="box.example")

    assert runtime.login() == "box.example"
    assert runtime.settings() == ()
    assert runtime.target() == "ssh://box.example"


@pytest.mark.parametrize(
    ("said", "why"),
    [
        ({"name": "-x", "host": "h"}, "invalid runtime name"),
        ({"name": "x"}, "requires a hostname or an alias"),
        ({"name": "x", "host": "-oProxyCommand=evil"}, "invalid ssh host"),
        ({"name": "x", "host": "h", "user": "a b"}, "invalid ssh user"),
        ({"name": "x", "host": "h", "port": 70000}, "invalid port"),
        ({"name": "x", "host": "h", "proxy_jump": "a b"}, "invalid jump host"),
        ({"name": "x", "host": "h", "identity_file": 'a"b'}, "newlines or quotes"),
        ({"name": "x", "host": "h", "config": "a\nb"}, "newlines or quotes"),
        (
            {"name": "x", "host": "h", "workdir": "relative"},
            "must be absolute or under",
        ),
        ({"name": "x", "host": "h", "made": "guessed"}, "made must be"),
        ({"name": "x", "host": "h", "options": {"F": "/x"}}, "invalid ssh option"),
        ({"name": "x", "host": "h", "options": {"1bad": "v"}}, "invalid ssh option"),
        (
            {"name": "x", "host": "h", "options": {"Port": "22"}},
            "must be set with port",
        ),
        ({"name": "x", "host": "h", "options": {"Compression": ""}}, "cannot be empty"),
        (
            {"name": "x", "host": "h", "fallback": ("ssh:x",)},
            "cannot fall back to itself",
        ),
        ({"name": "x", "host": "h", "fallback": ("ssh:y", "ssh:y")}, "is named twice"),
        (
            {"name": "x", "host": "h", "fallback": ("nowhere",)},
            "must be <backend>:<name>",
        ),
        ({"name": "x", "host": "h", "affinity": ("ssh:x",)}, "names itself"),
        ({"name": "x", "host": "h", "affinity": (SELF, SELF)}, "in its affinity twice"),
        (
            {"name": "x", "host": "h", "affinity": ("ftp:y",)},
            "is not where a harness runs",
        ),
    ],
)
def test_what_ssh_could_not_be_told_is_refused(said: dict[str, Any], why: str) -> None:
    with pytest.raises(ValueError, match=re.escape(why)):
        SSHRuntime(**said)


@pytest.mark.parametrize("workdir", ["", "~", "~/w", "/abs"])
def test_a_workdir_is_absolute_or_under_home(workdir: str) -> None:
    assert SSHRuntime(name="x", host="h", workdir=workdir).workdir == workdir


# --------------------------------------------------------------- Docker and the rest


@pytest.mark.parametrize(
    ("said", "why"),
    [
        ({"endpoint": "nowhere"}, "is not a docker endpoint"),
        ({"endpoint": "tcp://h:99999"}, "is not a docker endpoint"),
        ({"endpoint": "ssh://h?x=1"}, "is not a docker endpoint"),
        ({"endpoint": "unix:///s?x=1"}, "is not a docker endpoint"),
        ({"endpoint": "context:-bad"}, "is not a docker endpoint"),
        ({"tls_dir": "/certs"}, "require a tcp:// endpoint"),
        ({"image": "two words"}, "invalid image"),
        ({"runtime": "-x"}, "invalid OCI runtime"),
        ({"run_args": ("a\nb",)}, "cannot contain newlines"),
        ({"gpus": ("bad id",)}, "invalid GPU id"),
        ({"gpus": ("0", "0")}, "duplicate GPU"),
        ({"cpus": -1.0}, "cannot be negative"),
        ({"memory": -1}, "cannot be negative"),
        ({"gpu_memory": -1}, "cannot be negative"),
        ({"max_containers": -1}, "cannot be negative"),
        ({"made": IMPORTED}, "made must be typed"),
    ],
)
def test_what_a_docker_daemon_could_not_be_told_is_refused(
    said: dict[str, Any], why: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(why)):
        DockerRuntime(name="box", **said)


@pytest.mark.parametrize(
    "endpoint",
    [
        "local",
        "unix:///var/run/docker.sock",
        "tcp://h:2376",
        "ssh://me@h:22",
        "ssh:gpu",
        "context:prod",
    ],
)
def test_every_spelling_of_a_daemon_is_taken(endpoint: str) -> None:
    assert DockerRuntime(name="box", endpoint=endpoint).endpoint == endpoint


@pytest.mark.parametrize(
    ("said", "why"),
    [
        ({"endpoint": "nowhere"}, "is not a docker endpoint"),
        ({"tls_dir": "/certs"}, "require a tcp:// endpoint"),
        ({"image": "a b"}, "invalid image"),
        ({"run_args": ("\0",)}, "cannot contain newlines"),
        ({"cpus": -1.0}, "cannot be negative"),
        ({"max_tasks": -1}, "cannot be negative"),
        ({"gpu_resource": "1bad"}, "invalid generic resource"),
        ({"constraints": ("node.role",)}, "invalid constraint"),
        ({"constraints": ("node.role==x\ny",)}, "invalid constraint"),
        ({"nodes": {"-n": "gpu"}}, "invalid node host name"),
        ({"nodes": {"n": "not a destination"}}, "is neither a saved ssh host"),
        ({"made": IMPORTED}, "made must be typed"),
    ],
)
def test_what_a_swarm_could_not_be_told_is_refused(
    said: dict[str, Any], why: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(why)):
        SwarmRuntime(name="sw", **said)


def test_a_swarm_takes_constraints_and_nodes_it_can_reach() -> None:
    runtime = SwarmRuntime(
        name="sw",
        constraints=("node.labels.gpu == true", "node.role!=manager"),
        nodes={"n1": "gpu", "n2": "me@10.0.0.2:22"},
        gpu_resource="NVIDIA-GPU",
    )

    assert runtime.held()["nodes"] == {"n1": "gpu", "n2": "me@10.0.0.2:22"}


@pytest.mark.parametrize(
    ("said", "why"),
    [
        ({"image": "a b"}, "invalid image"),
        ({"run_args": ("\n",)}, "cannot contain newlines"),
        ({"cpus": -1.0}, "cannot be negative"),
        ({"memory": -1}, "cannot be negative"),
        ({"max_containers": -1}, "cannot be negative"),
        ({"workdir": "rel"}, "must be absolute or under"),
        ({"made": IMPORTED}, "made must be typed"),
    ],
)
def test_what_apple_containers_could_not_be_told_is_refused(
    said: dict[str, Any], why: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(why)):
        AppleContainerRuntime(name="mac", **said)


def test_a_runtime_is_written_down_with_its_backend_and_every_field() -> None:
    held = DockerRuntime(name="box", gpus=("0",), fallback=("ssh:gpu",)).held()

    assert held["backend"] == DOCKER
    assert held["gpus"] == ["0"]
    assert held["fallback"] == ["ssh:gpu"]
    assert held["name"] == "box"


# -------------------------------------------------------------------------------- new


@pytest.mark.parametrize(
    ("backend", "kind"),
    [
        (SSH, SSHRuntime),
        (DOCKER, DockerRuntime),
        (SWARM, SwarmRuntime),
        (APPLE_CONTAINER, AppleContainerRuntime),
    ],
)
def test_a_runtime_is_made_of_whichever_backend(backend: str, kind: type) -> None:
    fields = {"host": "h"} if backend == SSH else {}

    assert isinstance(new(backend, "r", **fields), kind)


def test_fields_are_taken_as_json_holds_them() -> None:
    runtime = new(DOCKER, "box", cpus=2, memory=4.0, gpus=["0", 1], run_args=("--x",))

    assert isinstance(runtime, DockerRuntime)
    assert runtime.cpus == 2.0
    assert runtime.memory == 4
    assert runtime.gpus == ("0", "1")
    assert new(SSH, "s", host="h", options={"A": 1}).held()["options"] == {"A": "1"}


@pytest.mark.parametrize(
    ("backend", "fields"),
    [
        ("ftp", {}),
        (DOCKER, {"nope": 1}),
        (DOCKER, {"cpus": "two"}),
        (DOCKER, {"cpus": True}),
        (DOCKER, {"memory": 1.5}),
        (DOCKER, {"memory": "1"}),
        (DOCKER, {"gpus": "0"}),
        (DOCKER, {"image": 3}),
        (SWARM, {"nodes": ["n"]}),
    ],
)
def test_a_field_of_another_type_is_refused(
    backend: str, fields: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match=r"runtime backend|unknown|cannot be"):
        new(backend, "r", **fields)


# ------------------------------------------------------------------------------ store


def test_nothing_is_saved_until_something_is_written() -> None:
    assert runtimes() == []
    assert find(SSH, "gpu") is None
    assert not saved(SSH, "gpu")


def test_a_runtime_written_down_is_read_back() -> None:
    made = SSHRuntime(name="gpu", host="h", fallback=("docker:box",))

    assert add(made) == made

    assert find(SSH, "gpu") == made
    assert saved(SSH, "gpu")
    assert written()["runtimes"]["ssh"]["gpu"]["host"] == "h"
    assert "backend" not in written()["runtimes"]["ssh"]["gpu"]


def test_a_runtime_cannot_be_added_twice() -> None:
    add(SSHRuntime(name="gpu", host="h"))

    with pytest.raises(ValueError, match="already exists"):
        add(SSHRuntime(name="gpu", host="other"))


def test_writing_replaces_what_was_there() -> None:
    add(SSHRuntime(name="gpu", host="h", user="a"))

    write(SSHRuntime(name="gpu", host="h2"))

    assert find(SSH, "gpu") == SSHRuntime(name="gpu", host="h2")


def test_writing_keeps_every_other_setting() -> None:
    settings.changes(lambda held: held.update(theme="dark", runtimes="junk"))

    write(DockerRuntime(name="box"))

    assert written()["theme"] == "dark"
    assert find(DOCKER, "box") == DockerRuntime(name="box")


def test_every_runtime_is_listed_by_backend_then_by_name() -> None:
    write(DockerRuntime(name="b"))
    write(DockerRuntime(name="a"))
    write(SSHRuntime(name="z", host="h"))
    write(AppleContainerRuntime(name="mac"))

    assert [(one.backend, one.name) for one in runtimes()] == [
        (SSH, "z"),
        (DOCKER, "a"),
        (DOCKER, "b"),
        (APPLE_CONTAINER, "mac"),
    ]
    assert [one.name for one in runtimes(DOCKER)] == ["a", "b"]


def test_an_entry_that_does_not_read_is_saved_but_not_a_runtime() -> None:
    settings.changes(
        lambda held: held.update(
            runtimes={
                "ssh": {"broken": {"port": "x"}, "-bad": {"host": "h"}, "list": [1]},
                "docker": "not a mapping",
            }
        )
    )

    assert runtimes() == []
    assert saved(SSH, "broken")
    assert find(SSH, "broken") is None
    assert find(SSH, "-bad") is None


@pytest.mark.parametrize(("backend", "name"), [("ftp", "x"), (SSH, "-x")])
def test_asking_after_a_runtime_there_could_not_be_is_refused(
    backend: str, name: str
) -> None:
    with pytest.raises(ValueError, match=r"runtime backend|invalid runtime name"):
        saved(backend, name)
    assert find(backend, name) is None


def test_a_runtime_taken_away_is_gone() -> None:
    write(DockerRuntime(name="box"))
    write(DockerRuntime(name="keep"))

    assert remove(DOCKER, "box") is True
    assert remove(DOCKER, "box") is False
    assert [one.name for one in runtimes()] == ["keep"]


def test_a_runtime_naming_a_home_that_is_not_there_is_not_written() -> None:
    with pytest.raises(ValueError, match="home directory not found"):
        write(SSHRuntime(name="x", host="h", config="~nobody-at-all/cfg"))
    with pytest.raises(ValueError, match="home directory not found"):
        write(DockerRuntime(name="x", endpoint="tcp://h:1", tls_dir="~nobody-at-all/c"))


# -------------------------------------------------------------------------- fallbacks


def test_a_runtime_falls_back_to_its_own_list_in_order() -> None:
    write(SSHRuntime(name="a", host="h", fallback=("docker:b", "swarm:c")))

    assert fallbacks(SSH, "a") == ((DOCKER, "b"), (SWARM, "c"))
    assert fallbacks(SSH, "missing") == ()


# ----------------------------------------------------------------- daemon_of / node_of


@pytest.mark.parametrize(
    ("endpoint", "said"),
    [
        ("local", Endpoint()),
        ("context:prod", Endpoint(context="prod")),
        ("ssh://me@h", Endpoint(host="ssh://me@h")),
    ],
)
def test_a_daemon_is_the_endpoint_it_spells(endpoint: str, said: Endpoint) -> None:
    assert daemon_of(endpoint) == said


def test_a_daemons_certificates_are_said_beside_it(tmp_path: Path) -> None:
    said = daemon_of("tcp://h:2376", str(tmp_path))

    assert said == Endpoint(host="tcp://h:2376", certs=str(tmp_path))


def test_a_daemon_on_a_saved_ssh_host_is_dialled_as_that_host_is() -> None:
    write(SSHRuntime(name="gpu", host="10.0.0.1", user="me", port=2222, proxy_jump="j"))

    said = daemon_of("ssh:gpu")

    assert said == Endpoint(
        host="ssh://me@10.0.0.1:2222", options=(("ProxyJump", "j"),)
    )
    assert DockerRuntime(name="box", endpoint="ssh:gpu").daemon() == said
    assert SwarmRuntime(name="sw", endpoint="ssh:gpu").daemon() == said


def test_a_daemon_on_an_ssh_host_that_is_not_saved_is_refused() -> None:
    with pytest.raises(ValueError, match="not found"):
        daemon_of("ssh:gpu")


@pytest.mark.parametrize("endpoint", ["nowhere", "tcp://h:0"])
def test_a_daemon_that_does_not_read_is_refused(endpoint: str) -> None:
    with pytest.raises(ValueError, match="is not a docker endpoint"):
        daemon_of(endpoint)


def test_a_node_is_reached_as_the_ssh_host_saved_under_its_name() -> None:
    write(SSHRuntime(name="gpu", host="h"))

    assert node_of("gpu") == "ssh:gpu"
    assert node_of("me@other:22") == "ssh://me@other:22"
    assert node_of("unsaved") == "ssh://unsaved"


def test_a_node_that_is_neither_is_refused() -> None:
    with pytest.raises(ValueError, match="neither a saved ssh host"):
        node_of("a b")


# -------------------------------------------------------------------------- respelled


@pytest.mark.parametrize(
    ("spec", "said"),
    [
        ("ssh/x", "ssh/x"),
        ("ssh@[box]/x", "ssh@[box]/x"),
        ("ssh@box/x", "ssh@[box]/x"),
        ("ssh@me@box/x", "ssh@[me@box]/x"),
        ("docker@local/x", "docker/x"),
        ("swarm@local", "swarm"),
        ("apple-container@local/w", "apple-container/w"),
        ("docker@other/x", "docker@other/x"),
        ("local@/x", "local/x"),
        ("ftp@box/x", "ftp@box/x"),
        ("ssh@/x", "ssh@/x"),
    ],
)
def test_an_old_spelling_is_read_as_it_is_spelled_now(spec: str, said: str) -> None:
    assert respelled(spec) == said


def test_a_saved_runtime_is_kept_as_it_was_spelled() -> None:
    write(SSHRuntime(name="box", host="h"))
    write(DockerRuntime(name="local"))

    assert respelled("ssh@box/x") == "ssh@box/x"
    assert respelled("docker@local/x") == "docker@local/x"


# ---------------------------------------------------------------- importing a config


def config_file(tmp_path: Path, said: str) -> Path:
    at = tmp_path / "ssh_config"
    at.write_text(said)
    return at


def test_every_host_of_a_config_is_imported_under_its_alias(tmp_path: Path) -> None:
    at = config_file(tmp_path, "Host gpu box.lan\n  User me\nHost *\n  Port 22\n")

    made = imports(at)

    assert [(one.name, one.alias, one.made) for one in made] == [
        ("gpu", "gpu", IMPORTED),
        ("box.lan", "box.lan", IMPORTED),
    ]
    assert made[0].config == str(at.resolve())
    assert [one.name for one in runtimes(SSH)] == ["box.lan", "gpu"]


def test_a_host_whose_alias_is_no_name_is_called_something_that_is(
    tmp_path: Path,
) -> None:
    at = config_file(tmp_path, "Host my+host _x\n")

    assert [one.name for one in imports(at)] == ["my-host", "x"]


def test_only_the_hosts_asked_for_are_imported(tmp_path: Path) -> None:
    at = config_file(tmp_path, "Host a b\n")

    assert [one.name for one in imports(at, ["b"])] == ["b"]
    assert find(SSH, "a") is None


def test_a_host_the_config_does_not_name_is_refused(tmp_path: Path) -> None:
    at = config_file(tmp_path, "Host a\n")

    with pytest.raises(ValueError, match="has no host c"):
        imports(at, ["c"])


def test_importing_again_leaves_what_is_there_unless_asked_to_update(
    tmp_path: Path,
) -> None:
    at = config_file(tmp_path, "Host a\n")
    imports(at)
    write(
        SSHRuntime(
            name="a", alias="a", made=IMPORTED, workdir="/w", fallback=("docker:d",)
        )
    )

    assert imports(at) == []
    (updated,) = imports(at, update=True)

    assert updated.workdir == "/w"
    assert updated.fallback == ("docker:d",)
    assert updated.config == str(at.resolve())


def test_an_import_never_writes_over_a_runtime_typed_in(tmp_path: Path) -> None:
    at = config_file(tmp_path, "Host a\n")
    write(SSHRuntime(name="a", host="typed"))

    assert imports(at, update=True) == []
    with pytest.raises(ValueError, match="was typed in"):
        imports(at, ["a"], update=True)
    assert find(SSH, "a") == SSHRuntime(name="a", host="typed")


def test_two_hosts_that_would_share_a_name_import_once(tmp_path: Path) -> None:
    at = config_file(tmp_path, "Host a+b a-b\n")

    assert [one.alias for one in imports(at)] == ["a+b"]
    with pytest.raises(ValueError, match="is imported as a-b"):
        imports(at, ["a+b", "a-b"])


def test_a_backends_list_is_what_an_environment_may_name() -> None:
    assert BACKENDS == (SSH, DOCKER, SWARM, APPLE_CONTAINER)
