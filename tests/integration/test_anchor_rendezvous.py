"""Two halves of a session meeting through a real `coganchor broker` on loopback.

Both halves are this machine, so whether they end up punched through to each other or carried
by the broker depends on whether the kernel lends one port to two sockets; what is checked is
that they are joined either way, and that a broker given no window to punch in carries them.
The serving half is `coganchor anchor --peer`, and the other half `coganchor cog --check`,
which meets it and asks it what it is. Two machines that genuinely cannot reach each other are
a system test's.
"""

from __future__ import annotations

import socket
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import binary, rendezvous
from hmz.coganchor.rendezvous import Meeting, ticket
from tests.integration.doubles_anchor import announced, stopped

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

PATIENCE = 60.0


def _broker(*, punching: float) -> Iterator[tuple[str, int]]:
    process, host, port = announced(
        [
            str(binary.here()),
            "broker",
            "--listen",
            "127.0.0.1:0",
            "--punching",
            str(punching),
        ]
    )
    try:
        yield host, port
    finally:
        stopped(process)


@pytest.fixture
def broker() -> Iterator[tuple[str, int]]:
    """A broker on loopback with a short window to punch in."""
    yield from _broker(punching=0.5)


@pytest.fixture
def carrying() -> Iterator[tuple[str, int]]:
    """A broker with no window at all, which carries every pair it is given."""
    yield from _broker(punching=0.0)


def _met(meeting: Meeting, real: Path) -> subprocess.CompletedProcess[str]:
    """Leaves a serving half of `real` at a meeting, and has a cog meet it and ask after it."""
    real.mkdir(exist_ok=True)
    (real / "note").write_text("on the target\n")
    serving = subprocess.Popen(
        [
            str(binary.here()),
            "anchor",
            "--peer",
            str(meeting),
            "--export",
            f"/w:{real}",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    try:
        return subprocess.run(
            [
                str(binary.here()),
                "cog",
                f"--target=peer://{meeting}",
                "--workspace=/w",
                "--check",
            ],
            capture_output=True,
            text=True,
            timeout=PATIENCE,
            check=False,
        )
    finally:
        stopped(serving)


def test_two_halves_are_joined_and_talk_both_ways(
    broker: tuple[str, int], tmp_path: Path
) -> None:
    said = _met(Meeting(ticket(), *broker), tmp_path / "target")

    assert said.returncode == 0, said.stderr
    assert "workspace   /w (1 entries)" in said.stdout


def test_a_pair_given_no_window_is_carried_whole(
    carrying: tuple[str, int], tmp_path: Path
) -> None:
    said = _met(Meeting(ticket(), *carrying), tmp_path / "target")

    assert said.returncode == 0, said.stderr
    assert "workspace   /w (1 entries)" in said.stdout


def test_a_meeting_is_keyed_by_its_ticket_whatever_token_is_about(
    broker: tuple[str, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both halves inherit it; neither asks the other for it.
    monkeypatch.setenv("HUMANIZE_TOKEN", "stray")

    said = _met(Meeting(ticket(), *broker), tmp_path / "target")

    assert said.returncode == 0, said.stderr


@pytest.mark.parametrize(
    "given", [["--token", "s3cret"], ["--token-file", "/dev/null"]]
)
def test_a_serving_half_at_a_meeting_takes_no_token(
    given: list[str], tmp_path: Path
) -> None:
    said = subprocess.run(
        [
            str(binary.here()),
            "anchor",
            "--peer",
            "T@127.0.0.1:9",
            *given,
            "--export",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=PATIENCE,
        check=False,
    )

    assert said.returncode == 2
    assert "--token cannot be given with --peer" in said.stderr


def test_two_meetings_at_one_broker_stay_two_sessions(
    broker: tuple[str, int], tmp_path: Path
) -> None:
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "more").write_text("")

    one = _met(Meeting(ticket(), *broker), tmp_path / "one")
    other = _met(Meeting(ticket(), *broker), tmp_path / "other")

    assert "workspace   /w (1 entries)" in one.stdout, one.stderr
    assert "workspace   /w (2 entries)" in other.stdout, other.stderr


def test_a_broker_nobody_runs_cannot_be_met(tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    said = subprocess.run(
        [
            str(binary.here()),
            "cog",
            f"--target=peer://{ticket()}@127.0.0.1:{port}",
            f"--workspace={tmp_path}",
            "--check",
        ],
        capture_output=True,
        text=True,
        timeout=PATIENCE,
        check=False,
    )

    assert said.returncode != 0


def test_the_broker_this_process_holds_is_started_once_and_said_as_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HUMANIZE_RENDEZVOUS", raising=False)
    monkeypatch.delenv("HUMANIZE_RENDEZVOUS_PORT", raising=False)

    host, port = rendezvous.shared("127.0.0.1")
    again, same = rendezvous.shared("broker.example")

    assert (host, again) == ("127.0.0.1", "broker.example")
    assert same == port
    with socket.create_connection(("127.0.0.1", port), timeout=PATIENCE):
        pass
