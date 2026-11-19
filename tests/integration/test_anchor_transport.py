"""Reaching a target: `coganchor` shipped down the road to it, and answering on it.

Every target here is this machine. `ssh`, `docker` and `container` are the fakes in
`doubles_anchor`, which run what they are sent locally -- so a target reached through one is
given `coganchor` and served for real, and what is checked is what came back over the protocol.
"""

from __future__ import annotations

import os
import shlex
import socket
import stat
import subprocess
import sys
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig, anchor, binary
from hmz.coganchor.proto import Frame, Op
from hmz.coganchor.rendezvous import Meeting, ticket
from hmz.coganchor.transport import Road, Target
from tests.integration.doubles_anchor import Fakes, announced, fakes, stopped

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: The serving half, as a command line starts it: `hmz`, which becomes `coganchor anchor`.
SERVE = [sys.executable, "-Pm", "hmz", "internal", "anchor", "serve"]

#: What a far side's shell is sent `coganchor` with: nothing else says this.
SHIPPING = "coganchor did not arrive whole"


@pytest.fixture
def far(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """Fake `ssh`, `docker` and `container` on `PATH`."""
    return fakes(tmp_path, monkeypatch)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A project with two files in it, which only the serving half reads."""
    held = tmp_path / "project"
    held.mkdir()
    (held / "a.txt").write_text("a\n")
    (held / "b.txt").write_text("b\n")
    return held


def _unique(tmp_path: Path) -> str:
    """A host name no other test in this process has bootstrapped."""
    return f"box-{tmp_path.name}"


def test_coganchor_runs_the_serving_half_with_nothing_of_this_repo_on_its_path() -> (
    None
):
    said = subprocess.run(
        [str(binary.here()), "anchor", "--help"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
        cwd="/",
        check=False,
    )

    assert said.returncode == 0, said.stderr
    assert "--export" in said.stdout


def test_a_local_target_is_served_by_a_child_of_this_process(
    tmp_path: Path, workspace: Path
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "only-there.txt").write_text("x")

    found = anchor.check(AnchorConfig(target=f"local:{real}", workspace=str(workspace)))

    assert found["target"] == f"local:{real}"
    assert found["workspace"] == str(workspace)
    # One entry: the listing came from the target's directory, not the workspace here.
    assert found["entries"] == 1
    assert found["exports"] == [{"virtual": str(workspace), "real": str(real)}]


def test_a_local_target_asks_for_no_secret_this_process_was_not_given(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exported for some `tcp://` target: the child would take it as its own `--token`.
    monkeypatch.setenv("HUMANIZE_TOKEN", "stray")

    assert anchor.check(AnchorConfig(workspace=str(workspace)))["entries"] == 2


def test_a_target_over_ssh_is_bootstrapped_once_and_served(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    config = AnchorConfig(target=f"ssh://{_unique(tmp_path)}", workspace=str(workspace))

    first = anchor.check(config)
    second = anchor.check(config)

    assert first["entries"] == second["entries"] == 2
    shipped = list((far.home / ".cache" / "humanize").glob("coganchor-*"))
    assert len(shipped) == 1
    # Asked what it is, given the program and served, then served alone: `coganchor` is
    # shipped once per machine.
    ships = [c for c in far.calls("ssh") if SHIPPING in c[-1]]
    assert len(ships) == 1
    assert len(far.calls("ssh")) == 4


def test_ssh_is_told_the_port_the_options_and_to_share_its_connection(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    host = f"me@{_unique(tmp_path)}"
    config = AnchorConfig(
        target=f"ssh://{host}:2222?IdentityFile=/keys/id", workspace=str(workspace)
    )

    anchor.check(config)

    for argv in far.calls("ssh"):
        assert argv[argv.index("-p") + 1] == "2222"
        assert "IdentityFile=/keys/id" in argv
        assert "ControlMaster=auto" in argv
        assert "-T" in argv
        assert host in argv


def test_a_target_ssh_cannot_install_on_says_what_ssh_said(
    far: Fakes, workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    far.fail(monkeypatch, "ssh", "Permission denied (publickey)")

    with pytest.raises(ConnectionError, match=r"Permission denied \(publickey\)"):
        anchor.check(
            AnchorConfig(target=f"ssh://{_unique(tmp_path)}", workspace=str(workspace))
        )


def test_a_docker_container_is_bootstrapped_in_its_own_temp_and_served(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    name = _unique(tmp_path)

    found = anchor.check(
        AnchorConfig(target=f"docker://{name}", workspace=str(workspace))
    )

    assert found["entries"] == 2
    assert list((far.root / "tmp" / "humanize").glob("coganchor-*"))
    assert all(argv[:3] == ["exec", "-i", name] for argv in far.calls("docker"))


def test_a_container_target_naming_a_user_runs_all_as_it_with_its_variables_wrapped(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    name = _unique(tmp_path)
    user = f"{os.getuid()}:{os.getgid()}"
    marks = tmp_path / "wrapped"
    wrapper = tmp_path / "wrapper"
    wrapper.write_text(
        "#!/bin/sh\n"
        "tag=$1; shift\n"
        f'printf "%s %s\\n" "$tag" "$HZ_PROBE" >> {shlex.quote(str(marks))}\n'
        'exec "$@"\n'
    )
    wrapper.chmod(0o755)
    target = f"docker://{name}?user={user}&env=HZ_PROBE=a%20b&exec={wrapper}&exec=t1"

    found = anchor.check(AnchorConfig(target=target, workspace=str(workspace)))

    assert found["entries"] == 2
    cache = far.root / "tmp" / f"humanize-{os.getuid()}"
    assert list(cache.glob("coganchor-*"))
    assert stat.S_IMODE(cache.lstat().st_mode) == 0o700
    assert not list((far.root / "tmp" / "humanize").glob("*"))
    calls = far.calls("docker")
    assert len(calls) == 3  # asked what it is, shipped, then served
    for argv in calls:
        assert argv[:9] == [
            "exec",
            "-i",
            "-u",
            user,
            "-e",
            "HZ_PROBE=a b",
            name,
            str(wrapper),
            "t1",
        ]
    assert marks.read_text().splitlines() == ["t1 a b"] * len(calls)


def test_a_container_users_directory_that_another_could_change_is_refused(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    planted = tmp_path / "planted"
    planted.mkdir()
    (far.root / "tmp" / f"humanize-{os.getuid()}").symlink_to(planted)
    target = f"docker://{_unique(tmp_path)}?user={os.getuid()}"

    with pytest.raises(
        ConnectionError,
        match=rf"humanize-{os.getuid()} is not a directory this user owns",
    ):
        anchor.check(AnchorConfig(target=target, workspace=str(workspace)))

    assert not list(planted.iterdir())


def test_a_container_on_another_daemon_is_reached_there_whatever_the_environment_says(
    far: Fakes, workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix:///somewhere/else.sock")

    anchor.check(
        AnchorConfig(
            target=f"docker://{_unique(tmp_path)}@tcp://10.0.0.5:2376",
            workspace=str(workspace),
        )
    )

    records = [one for one in far.records() if one["tool"] == "docker"]
    assert records
    for one in records:
        assert one["argv"][:2] == ["--host", "tcp://10.0.0.5:2376"]
        assert "DOCKER_HOST" not in one["env"]


def test_a_container_that_cannot_take_coganchor_says_what_its_log_said(
    far: Fakes, workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    far.fail(monkeypatch, "docker", "container is not running")
    monkeypatch.setenv("FAKE_LOGS", "no space left on device")

    with pytest.raises(ConnectionError) as failed:
        anchor.check(
            AnchorConfig(
                target=f"docker://{_unique(tmp_path)}", workspace=str(workspace)
            )
        )

    assert "container is not running" in str(failed.value)
    assert "the container said: no space left on device" in str(failed.value)


def test_an_apple_container_is_reached_through_container_exec(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    name = _unique(tmp_path)

    found = anchor.check(
        AnchorConfig(target=f"apple-container://{name}", workspace=str(workspace))
    )

    assert found["entries"] == 2
    assert far.calls("container")
    assert all(argv[:3] == ["exec", "-i", name] for argv in far.calls("container"))
    assert not far.calls("docker")


def test_a_road_forgotten_ships_coganchor_again(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    target = f"docker://{_unique(tmp_path)}"
    config = AnchorConfig(target=target, workspace=str(workspace))
    anchor.check(config)

    Road.to(Target.parse(target)).forget()
    anchor.check(config)

    ships = [c for c in far.calls("docker") if SHIPPING in " ".join(c)]
    assert len(ships) == 2


@pytest.fixture
def listening(workspace: Path) -> Iterator[tuple[str, int]]:
    """A serving half left listening on a loopback port, holding a secret."""
    process, host, port = announced(
        [
            *SERVE,
            "--listen",
            "127.0.0.1:0",
            "--token",
            "s3cret",
            "--export",
            str(workspace),
        ]
    )
    try:
        yield host, port
    finally:
        stopped(process)


def test_a_listening_target_serves_a_client_holding_its_secret(
    listening: tuple[str, int], workspace: Path
) -> None:
    host, port = listening
    config = AnchorConfig(
        target=f"tcp://{host}:{port}", workspace=str(workspace), token="s3cret"
    )

    assert anchor.check(config)["entries"] == 2
    # And again, a port being for more than one session.
    assert anchor.check(config)["entries"] == 2


def test_a_listening_target_refuses_a_client_with_the_wrong_secret(
    listening: tuple[str, int], workspace: Path
) -> None:
    host, port = listening

    with pytest.raises(OSError, match="invalid token"):
        anchor.check(
            AnchorConfig(
                target=f"tcp://{host}:{port}", workspace=str(workspace), token="wrong"
            )
        )


def test_a_listening_target_refuses_a_client_with_no_secret(
    listening: tuple[str, int], workspace: Path
) -> None:
    host, port = listening

    with pytest.raises(OSError, match="invalid token"):
        anchor.check(
            AnchorConfig(target=f"tcp://{host}:{port}", workspace=str(workspace))
        )


def test_a_listening_target_speaks_tls_and_nothing_else(
    listening: tuple[str, int],
) -> None:
    # A frame in the clear, as a HELLO crossed before: no frame comes back, at most an alert.
    with socket.create_connection(listening, timeout=30) as sock:
        sock.sendall(Frame.request(1, Op.HELLO, version=1, token="s3cret").encode())
        said = b""
        while chunk := sock.recv(4096):
            said += chunk

    assert not said or said[0] == 0x15  # a TLS alert record


def test_a_client_refuses_a_listener_that_cannot_prove_its_secret(
    workspace: Path,
) -> None:
    # One that lets anybody in, never having been told the secret, as an impostor would.
    process, host, port = announced(
        [*SERVE, "--listen", "127.0.0.1:0", "--export", str(workspace)]
    )
    target = f"tcp://{host}:{port}"
    try:
        with pytest.raises(
            ConnectionError,
            match=f"^the serving half at {target} did not prove the token$",
        ):
            anchor.check(
                AnchorConfig(target=target, workspace=str(workspace), token="s3cret")
            )
        # And through `coganchor cog`, which says so and exits 1.
        said = subprocess.run(
            [str(binary.here()), "cog", "--check", "--target", target],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "HUMANIZE_TOKEN": "s3cret"},
            cwd=workspace,
            check=False,
        )
    finally:
        stopped(process)

    assert said.returncode == 1, said.stderr
    assert f"the serving half at {target} did not prove the token" in said.stderr


def test_a_serving_half_will_not_listen_beyond_loopback_without_a_secret(
    workspace: Path,
) -> None:
    said = subprocess.run(
        [*SERVE, "--listen", "0.0.0.0:0", "--export", str(workspace)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert said.returncode == 2
    assert "without --token" in said.stderr


def test_a_meeting_is_not_met_from_this_process_but_by_coganchor_cog(
    workspace: Path,
) -> None:
    meeting = Meeting(ticket(), "127.0.0.1", 9)

    with pytest.raises(ConnectionError, match="a meeting for one session"):
        anchor.check(AnchorConfig(target=f"peer://{meeting}", workspace=str(workspace)))


def test_a_broker_run_as_a_command_line_introduces_two_halves(workspace: Path) -> None:
    process, host, port = announced(
        [
            sys.executable,
            *("-Pm", "hmz", "internal", "anchor", "rendezvous"),
            *("--listen", "127.0.0.1:0", "--punching", "0.2"),
        ]
    )
    meeting = Meeting(ticket(), host, port)
    serving = subprocess.Popen(
        [*SERVE, "--peer", str(meeting), "--export", str(workspace)],
        stdin=subprocess.DEVNULL,
    )
    try:
        found = subprocess.run(
            [
                sys.executable,
                *("-Pm", "hmz", "internal", "anchor", "--check"),
                f"--target=peer://{meeting}",
                f"--workspace={workspace}",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        stopped(serving)
        stopped(process)

    assert found.returncode == 0, found.stderr
    assert f"workspace   {workspace} (2 entries)" in found.stdout


def test_many_sessions_reach_one_ssh_target_at_once(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    config = AnchorConfig(target=f"ssh://{_unique(tmp_path)}", workspace=str(workspace))
    said: list[int] = []

    def one() -> None:
        said.append(anchor.check(config)["entries"])

    many = [threading.Thread(target=one) for _ in range(4)]
    for each in many:
        each.start()
    for each in many:
        each.join(timeout=60)

    assert said == [2, 2, 2, 2]
    assert len(list((far.home / ".cache" / "humanize").glob("coganchor-*"))) == 1
