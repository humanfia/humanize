"""Hosts a real `ssh` reaches without a password, for the system tests that need one.

Three of them, for three questions.

`ssh_host` is this machine: `localhost` where ssh already answers there without a password, and
otherwise an `sshd` of the test's own on a loopback port. It is what the ssh environment driver's
contract is held to in `tests/system/flows/test_ssh_envs.py` -- commands, files, worktrees over a
real connection -- which no second machine is needed for.

`ssh_box` is another machine: an `sshd` in a container of its own, with a filesystem of its own.
It is what the regression matrix in `tests/system/matrix` runs an agent's turn on. An agent
given a host works in a copy of the host's directory kept here *at the same path*, so on a
loopback host the copy and the host's directory are one directory, and every write the agent
makes is replayed onto the file it was read from -- which truncates it. Only a host that is
really somewhere else can say where the work landed.

`docker_box` is another machine with a docker daemon of its own: docker's daemon in a container
(`docker:dind`), with an sshd beside it for docker's own ssh transport to reach it by. It is what
the matrix puts an agent's container on when the daemon is somewhere else -- a daemon whose
directories are not this machine's, so a workdir that turns up here was never mounted there.

Each is reached through an `ssh` told about keys made for the test alone: nothing of the user's
`~/.ssh` is read or written. A machine that can give none of them skips, saying why.

What lands in humanize's home on the far side goes, for `localhost`, into the real
`~/.humanize` -- ssh carries none of this process's environment there -- so a test that derives
anything there removes it. The sshd of the test's own is told to take the test's
`HUMANIZE_HOME` instead, and a container's is the container's.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from hmz import home

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = [
    "ALIAS",
    "BOX",
    "BOXED",
    "DOCKED",
    "Box",
    "Docked",
    "docker_box",
    "ssh_box",
    "ssh_host",
]

#: The name the sshd of the test's own is reached by.
ALIAS = "hmz-sshd-test"

#: The name the container's sshd is reached by.
BOX = "hmz-sshd-box"

#: The image a container host is run from: Python, which humanize's serving half needs on the
#: far side, and an sshd. Built from `_BASE` the first time it is asked for and kept.
BOXED = "hmz-test-sshd:3.12"

#: What it is built from, pulled by hand rather than by the test: a machine without it skips.
_BASE = "python:3.12-slim"

#: How it is built.
_RECIPE = (
    f"FROM {_BASE}\n"
    "RUN apt-get update && apt-get install -y --no-install-recommends openssh-server"
    " && rm -rf /var/lib/apt/lists/* && mkdir -p /run/sshd\n"
)

#: What a container host is labelled with, so that one a killed run left is found by name.
_LABEL = "humanize-test-sshd"

#: The image a docker host is run from: docker's own daemon in a container, and an sshd for
#: docker's ssh transport to reach it by. Built from `_DIND` the first time it is asked for.
DOCKED = "hmz-test-dind-sshd:1"

#: What it is built from, pulled by hand as `_BASE` is.
_DIND = "docker:dind"

#: How it is built.
_DOCKED_RECIPE = (
    f"FROM {_DIND}\n"
    "RUN apk add --no-cache openssh-server && mkdir -p /root/.ssh && chmod 700 /root/.ssh\n"
)


def _unreachable() -> str | None:
    """Why `ssh localhost` does not answer without a password, or None when it does."""
    try:
        said = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                "localhost",
                "true",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"`ssh localhost` could not be run: {error}"
    if said.returncode:
        why = said.stderr.strip() or f"exit {said.returncode}"
        return f"passwordless ssh to localhost is not available ({why})"
    return None


def _free_port() -> int:
    with socket.socket() as probing:
        probing.bind(("127.0.0.1", 0))
        return int(probing.getsockname()[1])


def _keyed(at: Path) -> Path:
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(at)],
        check=True,
        capture_output=True,
    )
    return at


def _told(at: Path, config: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Puts an `ssh` that reads `config` first on PATH, for everything this test starts."""
    (at / "ssh_config").write_text(config)
    ssh = shutil.which("ssh")
    assert ssh is not None
    wrapper = at / "bin" / "ssh"
    wrapper.parent.mkdir()
    wrapper.write_text(f'#!/bin/sh\nexec {ssh} -F {at / "ssh_config"} "$@"\n')
    wrapper.chmod(0o755)
    monkeypatch.setenv("PATH", f"{wrapper.parent}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def ssh_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A host a real `ssh` reaches without a password: localhost, or an sshd of our own."""
    why = _unreachable()
    if why is None:
        yield "localhost"
        return
    sshd = shutil.which("sshd") or shutil.which(
        "sshd", path="/usr/sbin:/usr/local/sbin"
    )
    if sshd is None or shutil.which("ssh-keygen") is None:
        pytest.skip(f"{why}, and there is no sshd here to start one of the test's own")
    at = tmp_path / "sshd"
    at.mkdir()
    host_key, client_key = _keyed(at / "host_key"), _keyed(at / "client_key")
    shutil.copy(f"{client_key}.pub", at / "authorized_keys")
    port = _free_port()
    (at / "sshd_config").write_text(
        f"Port {port}\nListenAddress 127.0.0.1\nHostKey {host_key}\n"
        f"AuthorizedKeysFile {at / 'authorized_keys'}\nPidFile {at / 'sshd.pid'}\n"
        "UsePAM no\nStrictModes no\nPasswordAuthentication no\n"
        "KbdInteractiveAuthentication no\nPubkeyAuthentication yes\n"
        "AcceptEnv HUMANIZE_HOME\n"
    )
    server = subprocess.Popen(
        [sshd, "-D", "-e", "-f", str(at / "sshd_config")],
        stdout=subprocess.DEVNULL,
        stderr=(at / "sshd.log").open("w"),
    )
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    said = (at / "sshd.log").read_text().strip()
                    pytest.skip(
                        f"{why}, and an sshd of the test's own would not start: {said}"
                    )
                time.sleep(0.1)
        _told(
            at,
            f"Host {ALIAS}\n  HostName 127.0.0.1\n  Port {port}\n"
            f"  IdentityFile {client_key}\n  IdentitiesOnly yes\n"
            f"  UserKnownHostsFile {at / 'known_hosts'}\n  StrictHostKeyChecking no\n"
            f"  SetEnv HUMANIZE_HOME={home()}\n  LogLevel ERROR\n",
            monkeypatch,
        )
        yield ALIAS
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


@dataclass(frozen=True)
class Box:
    """Another machine: a container `ssh` reaches as `alias`, and what runs a command there.

    Attributes:
      alias: What `ssh` and `-e box=ssh@<alias>/...` call it.
      container: The container's id.
      config: The ssh config naming `alias`, which the `ssh` first on `PATH` reads -- and
        which is what an ssh provider is imported from.
    """

    alias: str
    container: str
    config: Path

    def run(self, script: str) -> str:
        """Runs a shell script on the host, as whoever ssh logs in as, and answers its stdout.

        Raises:
          AssertionError: If it failed, with what it said.
        """
        return _run(self.container, script)

    def unlisted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Takes the `ssh` that knows this host off `PATH`, for the rest of the test.

        What reaches it then is only what something saved says: a provider imported from
        :attr:`config`, say, rather than the `ssh` this fixture put first.
        """
        told = str(self.config.parent / "bin")
        monkeypatch.setenv(
            "PATH",
            os.pathsep.join(
                one for one in os.environ["PATH"].split(os.pathsep) if one != told
            ),
        )


def _run(container: str, script: str) -> str:
    """Runs a shell script in a container host, and answers its stdout."""
    done = _docker("exec", container, "sh", "-c", script)
    assert done.returncode == 0, f"{script!r} on the host: {done.stderr.strip()}"
    return done.stdout


def _docker(*argv: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """One docker command, and what it came to -- a timeout included, as a failure."""
    try:
        return subprocess.run(
            ["docker", *argv],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            ["docker", *argv], 124, "", "docker took longer than ten minutes"
        )


def _built(image: str = BOXED, base: str = _BASE, recipe: str = _RECIPE) -> str:
    """Why there is no image to run a container host from, or "" once there is one."""
    if shutil.which("docker") is None:
        return "needs the docker command to run another machine"
    if _docker("image", "inspect", image).returncode == 0:
        return ""
    if _docker("image", "inspect", base).returncode != 0:
        return f"needs a docker daemon holding {base} to build a host from"
    made = _docker("build", "--quiet", "-t", image, "-", stdin=recipe)
    if made.returncode != 0:
        return f"could not build {image}: {made.stderr.strip()[-400:]}"
    return ""


def _answers(alias: str) -> bool:
    """Whether `ssh` gets a command run on a host yet: an sshd still starting may hang."""
    try:
        done = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", alias, "true"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


@pytest.fixture
def ssh_box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Box]:
    """Another machine a real `ssh` reaches without a password: an sshd in a container."""
    why = _built()
    if why:
        pytest.skip(why)
    if shutil.which("ssh-keygen") is None:
        pytest.skip("needs ssh-keygen to make the test's own keys")
    at = tmp_path / "sshd-box"
    at.mkdir()
    client_key = _keyed(at / "client_key")
    started = _docker(
        "run",
        "--detach",
        "--rm",
        "--label",
        _LABEL,
        "--publish",
        "127.0.0.1::22",
        "--env",
        f"KEY={(at / 'client_key.pub').read_text().strip()}",
        BOXED,
        "sh",
        "-c",
        'mkdir -p /root/.ssh && printf "%s\\n" "$KEY" > /root/.ssh/authorized_keys'
        " && chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys"
        " && ssh-keygen -A >/dev/null && exec /usr/sbin/sshd -D -e",
    )
    if started.returncode != 0:
        pytest.skip(f"a container host would not start: {started.stderr.strip()}")
    container = started.stdout.strip()
    try:
        port = _docker("port", container, "22/tcp").stdout.strip().rpartition(":")[2]
        _told(
            at,
            f"Host {BOX}\n  HostName 127.0.0.1\n  Port {port}\n  User root\n"
            f"  IdentityFile {client_key}\n  IdentitiesOnly yes\n"
            f"  UserKnownHostsFile {at / 'known_hosts'}\n  StrictHostKeyChecking no\n"
            "  LogLevel ERROR\n",
            monkeypatch,
        )
        deadline = time.monotonic() + 60
        while not _answers(BOX):
            if time.monotonic() > deadline:
                said = _docker("logs", container).stderr.strip()[-400:]
                pytest.skip(f"a container host never answered ssh: {said}")
            time.sleep(0.5)
        yield Box(BOX, container, at / "ssh_config")
    finally:
        _docker("rm", "--force", container)


@dataclass(frozen=True)
class Docked:
    """Another machine with a docker daemon of its own, which a real `ssh` reaches.

    Attributes:
      container: The container the machine is, on this machine's own daemon.
      port: The loopback port its sshd is published on.
      key: The key it takes, which nothing but the test holds.
      known: The known-hosts file its host key goes in, the test's own.
    """

    container: str
    port: int
    key: Path
    known: Path

    def ssh(self) -> dict[str, Any]:
        """Everything `ssh` has to be told to reach it, as an ssh provider's fields."""
        return {
            "host": "127.0.0.1",
            "port": self.port,
            "user": "root",
            "identity_file": str(self.key),
            "options": {
                "IdentitiesOnly": "yes",
                "UserKnownHostsFile": str(self.known),
                "StrictHostKeyChecking": "no",
                "LogLevel": "ERROR",
            },
        }

    def run(self, script: str) -> str:
        """Runs a shell script on the machine, as root, and answers its stdout.

        Raises:
          AssertionError: If it failed, with what it said.
        """
        return _run(self.container, script)


def _reached(docked: Docked) -> bool:
    """Whether `ssh`, told everything it needs and nothing of the user's, reaches its daemon."""
    said = docked.ssh()
    argv = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    for keyword, value in said["options"].items():
        argv += ["-o", f"{keyword}={value}"]
    argv += ["-i", said["identity_file"], "-p", str(said["port"]), "root@127.0.0.1"]
    try:
        done = subprocess.run(
            [*argv, "docker", "info"], capture_output=True, timeout=30, check=False
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


@pytest.fixture
def docker_box(tmp_path: Path) -> Iterator[Docked]:
    """Another machine with a docker daemon of its own, holding the image a container needs.

    Docker's daemon in a privileged container, with an sshd beside it, and `python:3.12-slim`
    loaded into it from this machine's daemon -- so nothing is fetched. Nothing is put on
    `PATH`: whatever reaches it is told everything it needs, which is what an ssh provider is.
    """
    why = _built(DOCKED, _DIND, _DOCKED_RECIPE)
    if why:
        pytest.skip(why)
    if _docker("image", "inspect", _BASE).returncode != 0:
        pytest.skip(f"needs a docker daemon holding {_BASE} to hand the far daemon")
    if shutil.which("ssh-keygen") is None:
        pytest.skip("needs ssh-keygen to make the test's own keys")
    at = tmp_path / "docker-box"
    at.mkdir()
    key = _keyed(at / "client_key")
    started = _docker(
        "run",
        "--detach",
        "--rm",
        "--privileged",
        "--label",
        _LABEL,
        "--publish",
        "127.0.0.1::22",
        # A daemon listening on its socket alone, which is what docker's ssh transport dials.
        "--env",
        "DOCKER_TLS_CERTDIR=",
        "--env",
        f"KEY={(at / 'client_key.pub').read_text().strip()}",
        "--entrypoint",
        "sh",
        DOCKED,
        "-c",
        'printf "%s\\n" "$KEY" > /root/.ssh/authorized_keys'
        " && chmod 600 /root/.ssh/authorized_keys && ssh-keygen -A >/dev/null"
        " && /usr/sbin/sshd -e && exec dockerd-entrypoint.sh dockerd",
    )
    if started.returncode != 0:
        pytest.skip(f"a docker host would not start: {started.stderr.strip()}")
    container = started.stdout.strip()
    try:
        port = _docker("port", container, "22/tcp").stdout.strip().rpartition(":")[2]
        if not port.isdigit():
            # Gone already: a daemon that will not run in a container takes it with it.
            said = _docker("logs", container).stderr.strip()[-400:]
            pytest.skip(f"a docker host would not stay up: {said or 'it is gone'}")
        docked = Docked(container, int(port), key, at / "known_hosts")
        deadline = time.monotonic() + 90
        while not _reached(docked):
            if time.monotonic() > deadline:
                said = _docker("logs", container).stderr.strip()[-400:]
                pytest.skip(f"a docker host never answered over ssh: {said}")
            time.sleep(0.5)
        saving = subprocess.Popen(["docker", "save", _BASE], stdout=subprocess.PIPE)
        try:
            loaded = subprocess.run(
                ["docker", "exec", "-i", container, "docker", "load"],
                stdin=saving.stdout,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        finally:
            if saving.stdout is not None:
                saving.stdout.close()
            saving.wait()
        assert loaded.returncode == 0, f"{_BASE} would not load: {loaded.stderr}"
        yield docked
    finally:
        # Its daemon keeps its images in an anonymous volume, which goes only when asked.
        _docker("rm", "--force", "--volumes", container)
