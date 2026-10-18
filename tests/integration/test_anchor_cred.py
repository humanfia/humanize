"""Running an agent with its credentials pointed elsewhere, as far as that goes without ptrace.

`hmz internal cred` is spawned as `redirect.command` renders it. Answering the paths is a
ptrace supervisor's, which is a system test's to check; what is checked here is the line,
the refusal of a machine that cannot supervise, the arguments the command takes, and -- where
this machine can supervise -- what of a turn's processes outlives it.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.providers import redirect

if TYPE_CHECKING:
    from collections.abc import Callable

PATIENCE = 60


def _run(line: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        line, capture_output=True, text=True, timeout=PATIENCE, check=False
    )


def test_a_turn_with_nothing_to_point_elsewhere_runs_as_itself(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    line = redirect.command([], ["/bin/sh", "-c", f": > {marker}"])

    assert line == ["/bin/sh", "-c", f": > {marker}"]
    assert _run(line).returncode == 0
    assert marker.exists()


def test_swaps_are_named_on_the_line_the_turn_is_spawned_as() -> None:
    line = redirect.command(
        [("/home/me/.claude/.credentials.json", "/p/creds.json")],
        ["claude", "--print"],
        kept=[("/home/me/.claude/projects", "/runs/r1/projects")],
    )

    assert line[1:5] == ["-Pm", "hmz", "internal", "cred"]
    assert "--map=/home/me/.claude/.credentials.json=/p/creds.json" in line
    assert "--keep=/home/me/.claude/projects=/runs/r1/projects" in line
    assert line[-3:] == ["--", "claude", "--print"]


@pytest.mark.skipif(
    sys.platform == "linux" and redirect.supervises(),
    reason="this machine can supervise, so the turn would run redirected",
)
def test_a_machine_that_cannot_supervise_refuses_the_turn_rather_than_run_it_unswapped(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "ran"
    line = redirect.command(
        [(str(tmp_path / "theirs.json"), str(tmp_path / "mine.json"))],
        ["/bin/sh", "-c", f": > {marker}"],
    )

    said = _run(line)

    assert said.returncode != 0
    assert "hmz internal cred" in said.stderr
    assert not marker.exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["--", "true"],
        ["--map=relative=/abs", "--", "true"],
        ["--map=/abs/only", "--", "true"],
        ["--map=/a=/b"],
    ],
)
def test_a_cred_line_that_names_nothing_usable_is_a_usage_error(
    argv: list[str],
) -> None:
    said = _run([sys.executable, "-Pm", "hmz", "internal", "cred", *argv])

    assert said.returncode == 2
    assert "usage: hmz internal cred" in said.stderr


supervised = pytest.mark.skipif(
    not (sys.platform == "linux" and redirect.supervises()),
    reason="this machine cannot supervise a turn",
)


def _line(tmp_path: Path, script: str) -> list[str]:
    return redirect.command(
        [(str(tmp_path / "theirs.json"), str(tmp_path / "mine.json"))],
        ["/bin/sh", "-c", script],
    )


def _running(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except OSError:
        return False
    return stat.rpartition(")")[2].split()[0] != "Z"


def _until(check: Callable[[], bool], within: float = 15) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.1)
    return check()


def _detaching(marker: Path) -> str:
    # The subshell is gone the moment it has started the job, which leaves the job its own.
    return f'(setsid sh -c "sleep 2; echo ok > {marker}" </dev/null >/dev/null 2>&1 &)'


@supervised
def test_a_job_the_turn_left_running_on_its_own_outlives_it_and_still_opens_files(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "done"

    began = time.monotonic()
    said = _run(_line(tmp_path, f"{_detaching(marker)}; sleep 0.5"))

    assert said.returncode == 0, said.stderr
    assert time.monotonic() - began < 2, "the turn waited on the job it left"
    assert not marker.exists()
    assert _until(lambda: marker.exists() and marker.read_text() == "ok\n")


@supervised
def test_what_the_program_still_runs_when_it_ends_goes_with_it_even_in_a_session_of_its_own(
    tmp_path: Path,
) -> None:
    pidfile = tmp_path / "pid"

    said = _run(_line(tmp_path, f"setsid sleep 300 & echo $! > {pidfile}; sleep 0.5"))

    assert said.returncode == 0, said.stderr
    pid = int(pidfile.read_text())
    assert _until(lambda: not _running(pid))


@supervised
def test_the_program_is_the_turns_own_child_as_it_would_be_unsupervised(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    turn = subprocess.Popen(
        _line(tmp_path, f"echo $PPID > {parent}"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    assert turn.wait(timeout=PATIENCE) == 0
    assert int(parent.read_text()) == turn.pid


@supervised
def test_a_turn_that_is_killed_takes_its_program_but_not_what_left_it(
    tmp_path: Path,
) -> None:
    marker, pidfile = tmp_path / "done", tmp_path / "pid"
    script = f"{_detaching(marker)}; setsid sleep 300 & echo $! > {pidfile}; wait"
    turn = subprocess.Popen(
        _line(tmp_path, script),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert _until(pidfile.exists)
    time.sleep(0.5)

    turn.kill()
    turn.wait(timeout=PATIENCE)

    pid = int(pidfile.read_text())
    assert _until(lambda: not _running(pid))
    assert _until(lambda: marker.exists() and marker.read_text() == "ok\n")
