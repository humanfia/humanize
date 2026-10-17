"""Reaching a target: the bundle, the road to it, and the serving half answering on it.

Every target here is this machine. `ssh`, `docker` and `container` are the fakes in
`doubles_anchor`, which run what they are sent locally -- so a target reached through one is
bootstrapped and served for real, and what is checked is what came back over the protocol.
"""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
import sys
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig, anchor, transport
from hmz.coganchor.remote import RemoteClient
from hmz.coganchor.rendezvous import Broker, Meeting, ticket
from hmz.coganchor.transport import Road, Target, build_bundle
from tests.integration.doubles_anchor import Fakes, announced, fakes, stopped

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: The serving half, as a command line starts it.
SERVE = [sys.executable, "-Pm", "hmz", "internal", "anchor", "serve"]


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


def test_a_bundle_runs_the_serving_half_with_nothing_of_this_repo_on_its_path(
    tmp_path: Path,
) -> None:
    bundle = build_bundle(tmp_path / "coganchor.pyz")

    said = subprocess.run(
        [sys.executable, str(bundle), "internal", "anchor", "serve", "--help"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
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


def test_a_target_over_ssh_is_bootstrapped_once_and_served(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    config = AnchorConfig(target=f"ssh://{_unique(tmp_path)}", workspace=str(workspace))

    first = anchor.check(config)
    second = anchor.check(config)

    assert first["entries"] == second["entries"] == 2
    archives = list((far.home / ".cache" / "humanize").glob("humanize-*.pyz"))
    assert len(archives) == 1
    # Install and serve, then serve alone: the bundle is pushed once per machine.
    installs = [c for c in far.calls("ssh") if "HUMANIZE_BUNDLES" in c[-1]]
    assert len(installs) == 1
    assert len(far.calls("ssh")) == 3


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
    assert list((far.root / "tmp" / "humanize").glob("humanize-*.pyz"))
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
    assert list(cache.glob("humanize-*.pyz"))
    assert stat.S_IMODE(cache.lstat().st_mode) == 0o700
    assert not list((far.root / "tmp" / "humanize").glob("*"))
    calls = far.calls("docker")
    assert len(calls) == 2  # install, then serve
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


def test_a_container_that_cannot_take_the_bundle_says_what_its_log_said(
    far: Fakes, workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    far.fail(monkeypatch, "docker", "container is not running")
    monkeypatch.setenv("FAKE_LOGS", "no python 3.12 or newer on this machine")

    with pytest.raises(ConnectionError) as failed:
        anchor.check(
            AnchorConfig(
                target=f"docker://{_unique(tmp_path)}", workspace=str(workspace)
            )
        )

    assert "container is not running" in str(failed.value)
    assert "the container said: no python 3.12" in str(failed.value)


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


def test_a_road_forgotten_pushes_the_bundle_again(
    far: Fakes, workspace: Path, tmp_path: Path
) -> None:
    target = f"docker://{_unique(tmp_path)}"
    config = AnchorConfig(target=target, workspace=str(workspace))
    anchor.check(config)

    Road.to(Target.parse(target)).forget()
    anchor.check(config)

    installs = [c for c in far.calls("docker") if "HUMANIZE_BUNDLES" in " ".join(c)]
    assert len(installs) == 2


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


@pytest.fixture
def broker() -> Iterator[Broker]:
    """A broker on loopback that carries a pair at once rather than waiting on a punch."""
    made = Broker("127.0.0.1", 0, punching=0.2)
    made.start()
    yield made
    made.close()


def test_two_halves_met_through_a_broker_serve_a_session(
    broker: Broker, workspace: Path
) -> None:
    meeting = Meeting(ticket(), *broker.address)
    serving = subprocess.Popen(
        [*SERVE, "--peer", str(meeting), "--export", str(workspace)],
        stdin=subprocess.DEVNULL,
    )
    try:
        found = anchor.check(
            AnchorConfig(target=f"peer://{meeting}", workspace=str(workspace))
        )
    finally:
        stopped(serving)

    assert found["entries"] == 2
    assert found["target"] == f"peer://{meeting}"


def test_a_standing_serving_half_serves_session_after_session(
    broker: Broker, workspace: Path, tmp_path: Path
) -> None:
    meeting = Meeting(ticket(), *broker.address)
    peer = tmp_path / "peer"
    peer.write_text(f"{meeting}\n")
    serving = subprocess.Popen(
        [*SERVE, "--peer-file", str(peer), "--export", "/"],
        stdin=subprocess.DEVNULL,
    )
    config = AnchorConfig(target=f"peer://{meeting}", workspace=str(workspace))
    said: list[int] = []

    def one() -> None:
        said.append(anchor.check(config)["entries"])

    try:
        one()
        many = [threading.Thread(target=one) for _ in range(4)]
        for each in many:
            each.start()
        for each in many:
            each.join(timeout=120)
    finally:
        stopped(serving)

    assert said == [2, 2, 2, 2, 2]


def test_a_standing_serving_half_at_a_booked_meeting_serves_what_each_session_asks(
    workspace: Path, tmp_path: Path
) -> None:
    booking = Broker("127.0.0.1", 0, punching=0.2, booked=True)
    host, port = booking.start()
    serving_ticket, anchoring = booking.stand()
    peer = tmp_path / "peer"
    peer.write_text(f"{Meeting(serving_ticket, host, port)}\n")
    serving = subprocess.Popen(
        [*SERVE, "--peer-file", str(peer), "--export", "/"],
        stdin=subprocess.DEVNULL,
    )
    target = Target.parse(f"peer://{Meeting(anchoring, host, port)}")
    try:
        found = anchor.check(
            AnchorConfig(target=target.describe(), workspace=str(workspace))
        )
        # An agent's session is served its workspace -- the bound of its files, and the
        # workdir its fenced commands are held to -- and not the `/` the task was left with.
        assert found["entries"] == 2
        [export] = found["exports"]
        assert export["virtual"] == str(workspace)
        # The real path is built onto the export's own spelling, so on a Mac it may come
        # back as /var/... for /private/var/...: the same directory either way.
        assert workspace.samefile(export["real"])
        link = transport.connect(target, [str(workspace)])
        client = RemoteClient(link.channel)
        try:
            client.start()
            with pytest.raises(OSError, match="outside every export"):
                client.listdir(str(tmp_path))
        finally:
            client.close()
            link.close()
        # The flow's own link asks for `/`, as it does of a serving half it starts.
        link = transport.connect(target, ["/"])
        client = RemoteClient(link.channel)
        try:
            assert client.start()["exports"] == [{"virtual": "/", "real": "/"}]
        finally:
            client.close()
            link.close()
        # And the ticket the task was handed reaches nothing.
        with pytest.raises(OSError, match="no meeting here lets that half in"):
            anchor.check(
                AnchorConfig(
                    target=f"peer://{Meeting(serving_ticket, host, port)}",
                    workspace=str(workspace),
                )
            )
    finally:
        stopped(serving)
        booking.close()


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
        found = anchor.check(
            AnchorConfig(target=f"peer://{meeting}", workspace=str(workspace))
        )
    finally:
        stopped(serving)
        stopped(process)

    assert found["entries"] == 2


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
    assert len(list((far.home / ".cache" / "humanize").glob("humanize-*.pyz"))) == 1
