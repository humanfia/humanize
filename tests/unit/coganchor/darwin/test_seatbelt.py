"""The Seatbelt profile a fence comes to on a Mac, and the line that runs a program in it.

Profiles are text, so they are read on every host; nothing here applies one. Whether a profile
can be applied is asked of a `sandbox-exec` replaced by a stand-in.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.darwin.seatbelt import SANDBOX_EXEC, Profile, available

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def test_an_empty_profile_denies_every_path_and_leaves_the_network() -> None:
    profile, params = Profile().rules()

    lines = profile.splitlines()
    assert lines[:3] == [
        "(version 1)",
        "(allow default)",
        "(deny file-read* file-write* process-exec)",
    ]
    assert "(allow file-read-metadata)" in lines
    assert '(allow file-read-data (literal "/"))' in lines
    assert not any("network" in line for line in lines)
    assert params == {}


def test_paths_are_named_by_parameter_as_given_and_as_resolved(tmp_path: Path) -> None:
    real = tmp_path.resolve() / "real"
    real.mkdir()
    link = tmp_path.resolve() / "link"
    link.symlink_to(real)

    profile, params = Profile(read=(str(link),), write=(str(real),)).rules()

    assert params == {"R0": str(link), "R1": str(real), "W0": str(real)}
    assert (
        '(allow file-read* process-exec (subpath (param "R0")) (subpath (param "R1")))'
        in profile.splitlines()
    )
    assert (
        '(allow file-read* file-write* process-exec (subpath (param "W0")))'
        in profile.splitlines()
    )


def test_a_path_given_twice_is_named_once(tmp_path: Path) -> None:
    here = str(tmp_path.resolve())

    _, params = Profile(read=(here, f"{here}/", here)).rules()

    assert params == {"R0": here}


def test_a_path_with_quotes_never_reaches_the_profile_text() -> None:
    odd = '/srv/a "quoted" \\ path'

    profile, params = Profile(write=(odd,)).rules()

    assert odd not in profile
    assert odd in params.values()


def test_a_port_cuts_the_network_to_loopback_on_that_port() -> None:
    profile, _ = Profile(port=8123).rules()

    lines = profile.splitlines()
    assert "(deny network*)" in lines
    assert '(allow network-outbound (remote tcp "localhost:8123"))' in lines
    assert '(allow network-inbound (local tcp "localhost:*"))' in lines
    assert any("mDNSResponder" in line and "deny" in line for line in lines)


def test_the_terminals_stay_writable() -> None:
    profile, _ = Profile().rules()

    assert any(
        "/dev/ttys" in line and "file-write*" in line for line in profile.splitlines()
    )


def test_command_runs_the_program_under_sandbox_exec(tmp_path: Path) -> None:
    here = str(tmp_path.resolve())
    profile = Profile(read=(here,), port=1)

    command = profile.command(["prog", "--flag", "-p"])

    text, _ = profile.rules()
    assert command == [
        SANDBOX_EXEC,
        f"-DR0={here}",
        "-p",
        text,
        "--",
        "prog",
        "--flag",
        "-p",
    ]


def sandbox_exec(monkeypatch: pytest.MonkeyPatch, *, there: bool) -> None:
    """Says whether `sandbox-exec` is there, and asks the real machine about anything else."""
    access = os.access

    def accessing(path: Any, mode: int, **kwargs: Any) -> bool:
        return there if path == SANDBOX_EXEC else access(path, mode, **kwargs)

    monkeypatch.setattr(os, "access", accessing)


@pytest.fixture
def asking() -> Iterator[None]:
    """Asks afresh, and leaves no answer of a stand-in behind for a later test."""
    available.cache_clear()
    yield
    available.cache_clear()


def test_available_is_never_so_off_a_mac(
    asking: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("ran sandbox-exec off a Mac")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", never)

    assert not available()


@pytest.mark.parametrize(
    ("runs", "able"),
    [
        (0, True),
        (1, False),
        (OSError("gone"), False),
        (subprocess.TimeoutExpired("x", 30), False),
    ],
)
def test_available_is_whether_sandbox_exec_ran_a_program(
    asking: None,
    monkeypatch: pytest.MonkeyPatch,
    runs: int | Exception,
    able: bool,
) -> None:
    ran: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        ran.append(argv)
        if isinstance(runs, Exception):
            raise runs
        return subprocess.CompletedProcess(argv, runs)

    monkeypatch.setattr(sys, "platform", "darwin")
    sandbox_exec(monkeypatch, there=True)
    monkeypatch.setattr(subprocess, "run", run)

    assert available() is able
    assert available() is able
    assert len(ran) == 1
    assert ran[0][0] == SANDBOX_EXEC


def test_available_is_not_so_without_sandbox_exec(
    asking: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("ran a sandbox-exec that is not there")

    monkeypatch.setattr(sys, "platform", "darwin")
    sandbox_exec(monkeypatch, there=False)
    monkeypatch.setattr(subprocess, "run", never)

    assert not available()
