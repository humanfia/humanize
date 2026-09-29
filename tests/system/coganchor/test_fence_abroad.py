"""A fence held on the machine an anchored agent's work lands on, by that machine's own kernel.

Each test runs `sh` as the agent under a real supervisor, with its commands run on a real
target -- a stand-in directory on this machine, an sshd in a container reached by a real
`ssh`, a container reached through docker -- and asks each of them for what a flow's default
permission forbids, to write the target's `$HOME`, and with the network cut, to reach a host.
What the agent's own shell does (a redirect is a builtin, and runs here) is walled in by this
machine's Landlock; what it runs (`touch`, `python3`) is walled in by the target's.

A target that cannot fence is refused: a container whose seccomp profile turns Landlock away
says so at the handshake, and a fenced session there runs nothing. So is a cut network in a
container under docker's default profile, which lets Landlock through but not the seccomp
listener and `pidfd_getfd` that cutting the network also takes.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig, check
from hmz.coganchor.fence import ALL, READ, Fence
from hmz.coganchor.linux import landlock
from hmz.coganchor.proto import hello_fences
from tests.coganchor.fixtures import DEFAULT_TIMEOUT, REPO_ROOT
from tests.machines.fixtures import IMAGE
from tests.supervising import traced

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from tests.coganchor.fixtures import Anchorage
    from tests.flows.sshd import Box

pytestmark = [
    traced,
    pytest.mark.skipif(
        not landlock.available(net=True),
        reason=f"this kernel speaks Landlock ABI {landlock.abi()}; cutting TCP needs 4",
    ),
]

#: What the agent is asked for, one line apiece: each command runs on the target and prints
#: what it came to. The single quotes keep `$HOME` for the target's shell to read -- the
#: agent's own would read this machine's.
PROBE = (
    "sh -c 'echo in > made.txt' && echo WORKDIR-WRITTEN || echo WORKDIR-REFUSED\n"
    "sh -c 'touch \"$HOME/hmz-fence-probe\"' 2>/dev/null"
    " && echo HOME-WRITTEN || echo HOME-REFUSED\n"
    'python3 -c \'import socket; s = socket.create_connection(("{host}", {port}), 5);'
    ' s.sendall(b"hi"); assert s.recv(16)\' 2>/dev/null'
    " && echo NET-REACHED || echo NET-REFUSED\n"
    "python3 -c 'import urllib.request;"
    ' urllib.request.urlopen("http://example.com", timeout=10)\' 2>/dev/null'
    " && echo WEB-REACHED || echo WEB-REFUSED\n"
)

#: And what the agent's own shell is asked, which is this machine's to refuse.
HERE = (
    'echo here > "$HOME/hmz-fence-local" 2>/dev/null'
    " && echo LOCAL-WRITTEN || echo LOCAL-REFUSED\n"
)


def _default(*, online: bool = False) -> Fence:
    """The default permission, with the network cut unless asked otherwise."""
    return Fence.of(
        local=ALL,
        user=READ,
        system=READ,
        online=online,
        workdir="/nowhere-here",
        home=os.path.expanduser("~"),  # noqa: PTH111
    )


def _everything() -> Fence:
    return Fence.of(
        local=ALL,
        user=ALL,
        system=READ,
        online=True,
        workdir="/nowhere-here",
        home=os.path.expanduser("~"),  # noqa: PTH111
    )


def _turn(config: AnchorConfig, script: str) -> subprocess.CompletedProcess[str]:
    """Runs one shell script as the agent, spawned as a flow spawns an anchored turn."""
    return subprocess.run(
        config.command(["/bin/sh", "-c", script]),
        capture_output=True,
        text=True,
        timeout=DEFAULT_TIMEOUT * 2,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        check=False,
    )


def _said(ran: subprocess.CompletedProcess[str]) -> set[str]:
    return set(ran.stdout.split())


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home of the test's own, here and on a `local:` target that stands in for one."""
    made = tmp_path / "home"
    made.mkdir()
    monkeypatch.setenv("HOME", str(made))
    return made


def test_a_stand_in_target_holds_the_agents_commands_to_the_default(
    anchorage: Anchorage, home: Path, echo_server: tuple[str, int]
) -> None:
    host, port = echo_server
    ran = anchorage.run(
        "/bin/sh",
        "-c",
        HERE + PROBE.format(host=host, port=port),
        fence=_default(),
    )

    said = _said(ran)
    assert ran.returncode == 0, ran.stderr
    assert {"WORKDIR-WRITTEN", "HOME-REFUSED", "NET-REFUSED", "WEB-REFUSED"} <= said, (
        ran.stdout + ran.stderr
    )
    assert "LOCAL-REFUSED" in said, ran.stdout
    assert anchorage.target_text("made.txt") == "in\n"
    assert not (home / "hmz-fence-probe").exists()
    assert not (home / "hmz-fence-local").exists()


def test_a_stand_in_target_granted_more_lets_the_agent_have_it(
    anchorage: Anchorage, home: Path, echo_server: tuple[str, int]
) -> None:
    """The same probe, granted the home and the network: nothing refused but the system.

    Which proves the refusals above are the fence's and not the probe's.
    """
    host, port = echo_server
    ran = anchorage.run(
        "/bin/sh", "-c", HERE + PROBE.format(host=host, port=port), fence=_everything()
    )

    said = _said(ran)
    assert {
        "WORKDIR-WRITTEN",
        "HOME-WRITTEN",
        "NET-REACHED",
        "LOCAL-WRITTEN",
    } <= said, ran.stdout + ran.stderr
    assert (home / "hmz-fence-probe").exists()


def test_a_native_cli_is_walled_in_on_the_target(
    anchorage: Anchorage, home: Path, echo_server: tuple[str, int]
) -> None:
    """The whole CLI on the target, which a `local:` target is: every line is the target's."""
    host, port = echo_server
    config = AnchorConfig(
        target=f"local:{anchorage.target}",
        workspace=anchorage.workspace,
        native=True,
        fence=_default(),
    )

    ran = _turn(config, HERE + PROBE.format(host=host, port=port))

    said = _said(ran)
    assert {
        "WORKDIR-WRITTEN",
        "HOME-REFUSED",
        "NET-REFUSED",
        "LOCAL-REFUSED",
    } <= said, ran.stdout + ran.stderr
    assert not (home / "hmz-fence-probe").exists()


def test_a_command_on_another_machine_over_ssh_is_held_there(
    ssh_box: Box, tmp_path: Path, echo_server: tuple[str, int]
) -> None:
    """At the default permission the host's home is read-only to what the agent runs there.

    The host is a container under docker's default seccomp profile, which holds a fence but
    not one that cuts the network (see `test_a_default_container_refuses_a_cut_network`), so
    the network is left as the default leaves it.
    """
    host, port = echo_server
    there = tmp_path / "box"
    ssh_box.run(f"mkdir -p {there} && rm -f /root/hmz-fence-probe")
    config = AnchorConfig(
        target=f"ssh://{ssh_box.alias}",
        workspace=str(there),
        fence=_default(online=True),
    )

    ran = _turn(config, PROBE.format(host=host, port=port))

    said = _said(ran)
    assert {"WORKDIR-WRITTEN", "HOME-REFUSED", "NET-REACHED"} <= said, (
        ran.stdout + ran.stderr
    )
    assert ssh_box.run(f"cat {there}/made.txt").strip() == "in"
    assert ssh_box.run("ls /root/hmz-fence-probe 2>/dev/null || true").strip() == ""

    # And the same host, granted the home, lets the same commands have it.
    config = AnchorConfig(
        target=f"ssh://{ssh_box.alias}", workspace=str(there), fence=_everything()
    )
    said = _said(_turn(config, PROBE.format(host=host, port=port)))
    assert {"HOME-WRITTEN", "NET-REACHED"} <= said, said
    ssh_box.run("rm -f /root/hmz-fence-probe")


def _container(tmp_path: Path, *extra: str) -> Iterator[str]:
    """One container of the image, idling, holding a workspace at the path it has here."""
    name = f"hmz-fence-{secrets.token_hex(5)}"
    started = subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            *extra,
            "--volume",
            f"{tmp_path}:{tmp_path}",
            IMAGE,
            "sleep",
            "infinity",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert started.returncode == 0, started.stderr
    try:
        yield name
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name], capture_output=True, check=False
        )


@pytest.fixture
def box(daemon: None, tmp_path: Path) -> Iterator[str]:
    """A container on docker's default here, under docker's own seccomp profile."""
    del daemon
    (tmp_path / "work").mkdir()
    yield from _container(tmp_path / "work")


@pytest.fixture
def unconfined(daemon: None, tmp_path: Path) -> Iterator[str]:
    """A container with no seccomp profile, which can cut the network as this machine can."""
    del daemon
    (tmp_path / "work").mkdir()
    yield from _container(tmp_path / "work", "--security-opt", "seccomp=unconfined")


@pytest.fixture
def unlandlocked(daemon: None, tmp_path: Path) -> Iterator[str]:
    """A container whose seccomp profile turns every Landlock call away, as a strict one may."""
    del daemon
    (tmp_path / "work").mkdir()
    profile = tmp_path / "seccomp.json"
    profile.write_text(
        json.dumps(
            {
                "defaultAction": "SCMP_ACT_ALLOW",
                "syscalls": [
                    {
                        "names": [
                            "landlock_create_ruleset",
                            "landlock_add_rule",
                            "landlock_restrict_self",
                        ],
                        "action": "SCMP_ACT_ERRNO",
                        "errnoRet": 38,
                    }
                ],
            }
        )
    )
    yield from _container(tmp_path / "work", "--security-opt", f"seccomp={profile}")


def _in(container: str, tmp_path: Path, fence: Fence) -> AnchorConfig:
    return AnchorConfig(
        target=f"docker://{container}",
        workspace=str(tmp_path / "work"),
        shadow=str(tmp_path / "mirror"),
        fence=fence,
    )


def _homed(container: str) -> bool:
    """Whether the probe was written into the container's own home."""
    return (
        subprocess.run(
            ["docker", "exec", container, "sh", "-c", 'ls "$HOME/hmz-fence-probe"'],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def test_a_command_in_a_container_is_held_there(
    box: str, tmp_path: Path, echo_server: tuple[str, int]
) -> None:
    """The default permission, which leaves the network on, in a container as docker runs one."""
    host, port = echo_server

    ran = _turn(
        _in(box, tmp_path, _default(online=True)), PROBE.format(host=host, port=port)
    )

    said = _said(ran)
    assert {"WORKDIR-WRITTEN", "HOME-REFUSED", "NET-REACHED"} <= said, (
        ran.stdout + ran.stderr
    )
    assert (tmp_path / "work" / "made.txt").read_text() == "in\n"
    assert not _homed(box), "the container's home was written"


def test_a_cut_network_is_cut_in_a_container_that_can_cut_it(
    unconfined: str, tmp_path: Path, echo_server: tuple[str, int]
) -> None:
    host, port = echo_server

    ran = _turn(
        _in(unconfined, tmp_path, _default()), PROBE.format(host=host, port=port)
    )

    said = _said(ran)
    assert {"WORKDIR-WRITTEN", "HOME-REFUSED", "NET-REFUSED", "WEB-REFUSED"} <= said, (
        ran.stdout + ran.stderr
    )
    assert not _homed(unconfined), "the container's home was written"


def test_a_default_container_refuses_a_cut_network(box: str, tmp_path: Path) -> None:
    """A container under docker's default seccomp profile cannot cut the network.

    The profile lets Landlock through, and not what cutting the network also takes: the
    handshake says so, and a session that asks runs nothing.
    """
    config = _in(box, tmp_path, _default())
    said = check(config)
    assert hello_fences(said, net=False)
    assert not hello_fences(said, net=True)

    ran = _turn(config, "touch made.txt; echo RAN")

    assert ran.returncode != 0
    assert "RAN" not in ran.stdout
    assert "cannot fence" in ran.stderr, ran.stderr
    assert not (tmp_path / "work" / "made.txt").exists()


def test_a_container_that_cannot_fence_refuses_the_session(
    unlandlocked: str, tmp_path: Path
) -> None:
    config = AnchorConfig(
        target=f"docker://{unlandlocked}",
        workspace=str(tmp_path / "work"),
        shadow=str(tmp_path / "mirror"),
        fence=_default(online=True),
    )
    assert not hello_fences(check(config), net=False)

    ran = _turn(config, "touch made.txt; echo RAN")

    assert ran.returncode != 0
    assert "RAN" not in ran.stdout
    assert "cannot fence" in ran.stderr, ran.stderr
    assert not (tmp_path / "work" / "made.txt").exists()


#: Binds and listens on loopback, on every address, and on none, at a port the kernel picks
#: and at the one given, saying what each came to on a line of its own under a tag.
LISTENS = """
import errno, socket, sys
def said(host, port):
    held = socket.socket()
    try:
        if host:
            held.bind((host, port))
        held.listen()
        return "listening"
    except OSError as why:
        return "refused-" + errno.errorcode.get(why.errno, str(why.errno))
    finally:
        held.close()
tag, named = sys.argv[1], int(sys.argv[2])
for host, port in (
    ("127.0.0.1", 0), ("0.0.0.0", 0), ("", 0), ("127.0.0.1", named), ("0.0.0.0", named)
):
    print(f"{tag}:{host or 'unbound'}:{'named' if port else 0}:{said(host, port)}", flush=True)
"""

#: The agent: the probe in its own process, which is walled in here, then as a command, which
#: is run on the target and walled in there.
LISTENER = (
    LISTENS
    + "import subprocess\n"
    + f"subprocess.run(['python3', '-c', {LISTENS!r}, 'THERE', str(named)], check=False)\n"
)


def _listened(ran: subprocess.CompletedProcess[str], where: str) -> list[str]:
    return [one for one in ran.stdout.split() if one.startswith(f"{where}:")]


def _loopback(where: str, *, named: str) -> list[str]:
    """What a cut network lets a socket do: listen on loopback, at a port it may bind."""
    return [
        f"{where}:127.0.0.1:0:listening",
        f"{where}:0.0.0.0:0:refused-EACCES",
        f"{where}:unbound:0:refused-EACCES",
        f"{where}:127.0.0.1:named:{named}",
        f"{where}:0.0.0.0:named:refused-EACCES",
    ]


def _free() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _listening(config: AnchorConfig, port: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        config.command([sys.executable, "-c", LISTENER, "HERE", str(port)]),
        capture_output=True,
        text=True,
        timeout=DEFAULT_TIMEOUT * 2,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        check=False,
    )


def test_a_cut_network_lets_an_anchored_agent_listen_on_loopback_only(
    anchorage: Anchorage, home: Path
) -> None:
    """A supervised agent listens as `hmz internal fence` would let it, on both machines.

    Here, at a port the kernel picks -- agy's language server -- and at the one its fence
    names -- kimi's daemon -- on loopback and nowhere else. There, what it runs likewise, but
    for the named port: that is the CLI's own, which no command it runs is let bind.
    """
    del home
    port = _free()
    ran = _listening(
        AnchorConfig(
            target=f"local:{anchorage.target}",
            workspace=anchorage.workspace,
            shadow=str(anchorage.mirror),
            fence=_default().granting(listen=[port]),
        ),
        port,
    )

    assert _listened(ran, "HERE") == _loopback("HERE", named="listening"), (
        ran.stdout + ran.stderr
    )
    assert _listened(ran, "THERE") == _loopback("THERE", named="refused-EACCES"), (
        ran.stdout + ran.stderr
    )


def test_a_cut_network_in_a_container_lets_what_runs_there_listen_on_loopback_only(
    unconfined: str, tmp_path: Path
) -> None:
    port = _free()
    ran = _listening(
        _in(unconfined, tmp_path, _default().granting(listen=[port])), port
    )

    assert _listened(ran, "HERE") == _loopback("HERE", named="listening"), (
        ran.stdout + ran.stderr
    )
    assert _listened(ran, "THERE") == _loopback("THERE", named="refused-EACCES"), (
        ran.stdout + ran.stderr
    )
