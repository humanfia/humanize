"""A fence held on the machine an anchored agent's work lands on, by that machine's own kernel.

Each test runs `sh` as the agent under a real supervisor, with its commands run on a real
target -- a stand-in directory on this machine, an sshd in a container reached by a real
`ssh`, a container reached through docker -- and asks each of them for what a flow's default
permission with the network cut forbids: to write the target's `$HOME`, and to reach a host.
What the agent's own shell does (a redirect is a builtin, and runs here) is walled in by this
machine's Landlock; what it runs (`touch`, `python3`) is walled in by the target's.

A target that cannot fence is refused: a container whose seccomp profile turns Landlock away
says so at the handshake, and a fenced session there runs nothing.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
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
HERE = 'echo here > "$HOME/hmz-fence-local" 2>/dev/null && echo LOCAL-WRITTEN || echo LOCAL-REFUSED\n'


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
    """The same probe, at a permission that grants the home and the network: nothing refused
    but the system, which proves the refusals above are the fence's and not the probe's."""
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
    host, port = echo_server
    there = tmp_path / "box"
    ssh_box.run(f"mkdir -p {there} && rm -f /root/hmz-fence-probe")
    config = AnchorConfig(
        target=f"ssh://{ssh_box.alias}", workspace=str(there), fence=_default()
    )

    ran = _turn(config, PROBE.format(host=host, port=port))

    said = _said(ran)
    assert {"WORKDIR-WRITTEN", "HOME-REFUSED", "NET-REFUSED", "WEB-REFUSED"} <= said, (
        ran.stdout + ran.stderr
    )
    assert ssh_box.run(f"cat {there}/made.txt").strip() == "in"
    assert ssh_box.run("ls /root/hmz-fence-probe 2>/dev/null || true").strip() == ""

    # And the same host, granted the home and the network, lets the same commands have both.
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


def test_a_command_in_a_container_is_held_there(
    box: str, tmp_path: Path, echo_server: tuple[str, int]
) -> None:
    host, port = echo_server
    config = AnchorConfig(
        target=f"docker://{box}",
        workspace=str(tmp_path / "work"),
        shadow=str(tmp_path / "mirror"),
        fence=_default(),
    )

    ran = _turn(config, PROBE.format(host=host, port=port))

    said = _said(ran)
    assert {"WORKDIR-WRITTEN", "HOME-REFUSED", "NET-REFUSED", "WEB-REFUSED"} <= said, (
        ran.stdout + ran.stderr
    )
    assert (tmp_path / "work" / "made.txt").read_text() == "in\n"
    probe = subprocess.run(
        ["docker", "exec", box, "sh", "-c", 'ls "$HOME/hmz-fence-probe"'],
        capture_output=True,
        check=False,
    )
    assert probe.returncode != 0, "the container's home was written"


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
