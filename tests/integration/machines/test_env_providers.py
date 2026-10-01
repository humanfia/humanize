"""Environment providers asked about, through stand-ins for `ssh` and `docker` on `PATH`.

What `ssh -G` says a host resolves to, what an ssh host and a docker daemon say they have when
checked, and the `ssh` a docker daemon behind a stored ssh host is dialled through -- each read
off a stand-in this file writes, which says what it was asked and answers as the real one
would. `tests/system` asks the real ones.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines import store
from hmz.coganchor.machines.store import DockerProvider, SSHProvider
from hmz.sdk import Hmz

if TYPE_CHECKING:
    from pathlib import Path

#: What stands in for `ssh`: `-G` answers as ssh does, from what it was told; anything else
#: skips the options and runs the line here, as the far side of a real one would.
_SSH = r"""#!/bin/sh
printf '%s\n' "$*" >> "$STANDIN_LOG"
if [ "$1" = -G ]; then
  shift
  user=me port=22 key= host=
  while [ $# -gt 0 ]; do
    case $1 in
      -F) shift 2 ;;
      -p) port=$2; shift 2 ;;
      -o) case $2 in IdentityFile=*) key=${2#IdentityFile=} ;; esac; shift 2 ;;
      --) shift ;;
      *) host=$1; shift ;;
    esac
  done
  case $host in *@*) user=${host%@*}; host=${host#*@} ;; esac
  case $host in nowhere) echo "no such config" >&2; exit 255 ;; esac
  echo "user $user"
  echo "hostname $host.example"
  echo "port $port"
  if [ -n "$key" ]; then echo "identityfile $key"; else
    for one in id_rsa id_ecdsa id_ecdsa_sk id_ed25519 id_ed25519_sk id_xmss id_dsa; do
      echo "identityfile ~/.ssh/$one"
    done
  fi
  echo "proxyjump none"
  exit 0
fi
while [ $# -gt 0 ]; do
  case $1 in
    -[bcDEeFIiJLlmOoPpQRSWw]) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
case $1 in refusing*) echo "ssh: connect to host $1 port 22: Connection refused" >&2
                      exit 255 ;; esac
shift
exec /bin/sh -c "$*"
"""

#: What `docker info --format '{{json .}}'` said on a machine with two GPUs behind CDI.
_INFO: dict[str, object] = {
    "ServerVersion": "29.4.3",
    "NCPU": 64,
    "MemTotal": 2164112805888,
    "DefaultRuntime": "nvidia",
    "Runtimes": {"io.containerd.runc.v2": {}, "nvidia": {}, "runc": {}},
    "DiscoveredDevices": [
        {"Source": "cdi", "ID": "k8s.device-plugin.nvidia.com/gpu=GPU-1ac8"},
        {"Source": "cdi", "ID": "management.nvidia.com/gpu=all"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=1"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=0"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=GPU-1ac8"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=all"},
    ],
}

#: What stands in for `docker`: `info` answers with what the test left for it, or with the
#: error a daemon that is not there gives. Where `STANDIN_GPUS` is set, a container asking
#: `nvidia-smi` of GPU 0 is answered, a second on, and one asking of any other finds none --
#: GPU 1 failed after the daemon's CDI specs were written. Nothing else is answered.
_DOCKER = r"""#!/bin/sh
printf '%s | %s\n' "$*" "$PATH" >> "$STANDIN_LOG"
for word in "$@"; do
  if [ "$word" = info ]; then
    case "$*" in *unix:///nowhere*)
      echo "Cannot connect to the Docker daemon at unix:///nowhere." >&2; exit 1 ;;
    esac
    cat "$STANDIN_INFO"; exit 0
  fi
done
case "$*" in *nvidia-smi*)
  [ -n "$STANDIN_GPUS" ] || exit 1
  sleep 1
  case "$*" in *nvidia.com/gpu=0\ *) echo "0, GPU-1ac8"; exit 0 ;; esac
  echo "No devices were found"; exit 6 ;;
esac
exit 1
"""


@pytest.fixture
def standins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`ssh` and `docker` stand-ins on `PATH`, and the log both write what they were asked to."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name, said in (("ssh", _SSH), ("docker", _DOCKER)):
        (bin_ / name).write_text(said)
        (bin_ / name).chmod(0o755)
    info = tmp_path / "info.json"
    info.write_text(json.dumps(_INFO))
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STANDIN_LOG", str(tmp_path / "asked.log"))
    monkeypatch.setenv("STANDIN_INFO", str(info))
    return tmp_path / "asked.log"


def test_the_hosts_of_a_config_are_what_ssh_resolves_them_to(
    standins: Path, tmp_path: Path
) -> None:
    config = tmp_path / "config"
    config.write_text("Host gpu\n  HostName ignored-by-the-stand-in\nHost *\n")

    (gpu,) = Hmz().environments.hosts(config)

    assert (gpu.alias, gpu.host, gpu.user, gpu.port) == ("gpu", "gpu.example", "me", 22)
    assert gpu.identity_files == ()  # only ssh's own, which nobody chose
    assert gpu.proxy_jump == ""
    assert standins.read_text() == f"-G -F {config} -- gpu\n"


def test_a_stored_provider_resolves_with_everything_it_says(standins: Path) -> None:
    provider = SSHProvider(
        name="gpu", host="box", user="root", port=2200, identity_file="/k"
    )

    said = Hmz().environments.resolve(provider)

    assert (said.alias, said.host, said.user, said.port) == (
        "gpu",
        "box.example",
        "root",
        2200,
    )
    assert said.identity_files == ("/k",)


def test_one_key_of_ssh_s_own_named_for_a_host_is_one_chosen(standins: Path) -> None:
    provider = SSHProvider(name="gpu", host="box", identity_file="~/.ssh/id_ed25519")

    assert Hmz().environments.resolve(provider).identity_files == ("~/.ssh/id_ed25519",)


def test_a_config_ssh_cannot_read_is_an_error(standins: Path) -> None:
    with pytest.raises(OSError, match="no such config"):
        Hmz().environments.resolve(SSHProvider(name="x", host="nowhere"))


def test_an_ssh_host_checked_says_what_a_run_would_learn(standins: Path) -> None:
    checked = Hmz().environments.check(SSHProvider(name="here", host="here"))

    assert checked.reached, checked.said
    assert checked.home == os.environ["HOME"]
    assert checked.cpus == len(os.sched_getaffinity(0))
    assert checked.memory > 0
    asked = standins.read_text()  # one ssh, carrying the probe a run makes
    assert asked.count("-T -o BatchMode=no") == 1
    assert " here exec /bin/sh -c " in asked


def test_an_ssh_host_that_will_not_answer_says_why(standins: Path) -> None:
    checked = Hmz().environments.check(SSHProvider(name="x", host="refusing"))

    assert not checked.reached
    assert checked.said == "ssh: connect to host refusing port 22: Connection refused"


def test_a_docker_daemon_checked_says_what_it_has(standins: Path) -> None:
    checked = Hmz().environments.check(
        DockerProvider(
            name="box",
            endpoint="unix:///var/run/docker.sock",
            cpus=128,
            gpus=("0", "2"),
            runtime="kata",
        )
    )

    assert checked.reached, checked.said
    assert (checked.cpus, checked.memory, checked.version) == (
        64.0,
        2164112805888,
        "29.4.3",
    )
    assert checked.gpus == ("0", "1")
    assert checked.runtimes == ("nvidia", "io.containerd.runc.v2", "runc")
    assert checked.short == (
        "it is to hand out 128 CPUs and has 64",
        "it has no GPU 2",
        "it has no runtime kata",
    )
    asked = standins.read_text()
    assert asked.startswith(
        "--host unix:///var/run/docker.sock info --format {{json .}} |"
    )


@pytest.mark.parametrize("said", ["null", "[]", '"a string"', "not json"])
def test_a_docker_that_says_something_else_is_not_reached(
    standins: Path, tmp_path: Path, said: str
) -> None:
    (tmp_path / "info.json").write_text(said)

    checked = Hmz().environments.check(DockerProvider(name="box"))

    assert not checked.reached
    assert checked.said


def test_a_docker_daemon_that_is_not_there_says_why(standins: Path) -> None:
    checked = Hmz().environments.check(
        DockerProvider(name="box", endpoint="unix:///nowhere")
    )

    assert not checked.reached
    assert checked.said == "Cannot connect to the Docker daemon at unix:///nowhere."


def test_a_docker_daemon_behind_a_stored_ssh_host_dials_it_as_it_says(
    standins: Path,
) -> None:
    store.add(
        SSHProvider(name="gpu", host="box", identity_file="/k", options={"A": "b"})
    )
    daemon = DockerProvider(name="far", endpoint="ssh:gpu").daemon()
    (path,) = [
        one.removeprefix("PATH=")
        for one in daemon.docker("ps")
        if one.startswith("PATH=")
    ]

    # What docker's own ssh would run: the login, the port and the host, and the dial.
    ssh = path.split(os.pathsep)[0] + "/ssh"
    ran = subprocess.run(
        [ssh, "-o", "ConnectTimeout=30", "-T", "--", "box", "true"],
        env={**os.environ, "PATH": path},
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    assert standins.read_text() == (
        "-o IdentityFile=/k -o A=b -o ConnectTimeout=30 -T -- box true\n"
    )
    checked = Hmz().environments.check(DockerProvider(name="far", endpoint="ssh:gpu"))
    assert checked.reached, checked.said
    # Its GPUs asked after too, of a container each on the same daemon.
    (_, docker, *asked) = standins.read_text().splitlines()
    assert docker.startswith("--host ssh://box info ")
    assert all(one.startswith("--host ssh://box run ") for one in asked)
    assert docker.split(" | ")[1].startswith(path.split(os.pathsep)[0])
