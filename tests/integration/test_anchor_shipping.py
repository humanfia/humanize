"""Shipping `coganchor` to a target, and starting it there, where it is what runs the anchor.

Every target here is this machine, through the fakes of `doubles_anchor`, so this machine's
`uname -sm` is what the far side answers and this machine's build is what lands there. The
program shipped is a stand-in that writes down how it was started, so the road is exercised for
real whatever the Rust anchor can do yet; the last test ships the real build, where there is
one, and runs it.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import binary
from hmz.coganchor.transport import Road, Target, serve_line
from tests.integration.doubles_anchor import Fakes, fakes

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def far(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """Fake `ssh`, `docker` and `container` on `PATH`."""
    return fakes(tmp_path, monkeypatch)


@pytest.fixture
def started(tmp_path: Path) -> Path:
    """Where the stand-in writes each line it was started with."""
    return tmp_path / "started.txt"


@pytest.fixture
def program(tmp_path: Path, started: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in for `coganchor`, chosen, that writes down its arguments and exits."""
    made = tmp_path / "built" / "coganchor"
    made.parent.mkdir()
    made.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{started}"\n')
    made.chmod(0o755)
    monkeypatch.setenv(binary.VARIABLE, str(made))
    return made


def _shipped(program: Path) -> str:
    return f"coganchor-{hashlib.sha256(program.read_bytes()).hexdigest()[:16]}"


def test_coganchor_is_shipped_over_ssh_once_and_started_as_the_anchor(
    far: Fakes, program: Path, started: Path, tmp_path: Path
) -> None:
    target = Target.parse(f"ssh://ship-{tmp_path.name}")

    first = serve_line(target, ["/w"])
    subprocess.run(first, check=True, stdin=subprocess.DEVNULL)
    second = serve_line(target, ["/w"])
    subprocess.run(second, check=True, stdin=subprocess.DEVNULL)

    cache = far.home / ".cache" / "humanize"
    landed = cache / _shipped(program)
    assert landed.read_bytes() == program.read_bytes()
    assert stat.S_IMODE(landed.stat().st_mode) == 0o700
    assert [one.name for one in cache.iterdir()] == [landed.name]
    assert started.read_text().splitlines() == ["anchor --stdio --export /w"] * 2
    # Asked what it is, given the program, and started twice: nothing a second time.
    asked = [argv[-1] for argv in far.calls("ssh")]
    assert len(asked) == 4
    assert asked[0] == "exec /bin/sh -c 'exec uname -sm'"
    assert asked[2].endswith("coganchor anchor --stdio --export /w")
    assert f"/{landed.name}" in asked[2]


def test_coganchor_in_a_container_lands_in_its_own_temp_as_its_user(
    far: Fakes, program: Path, started: Path, tmp_path: Path
) -> None:
    name = f"ship-{tmp_path.name}"
    target = Target.parse(f"docker://{name}?user={os.getuid()}")

    subprocess.run(serve_line(target, ["/w"]), check=True, stdin=subprocess.DEVNULL)

    cache = far.root / "tmp" / f"humanize-{os.getuid()}"
    assert (cache / _shipped(program)).is_file()
    assert stat.S_IMODE(cache.lstat().st_mode) == 0o700
    assert started.read_text() == "anchor --stdio --export /w\n"
    assert all(argv[:5] == ["exec", "-i", "-u", str(os.getuid()), name]
               for argv in far.calls("docker"))  # fmt: skip


def test_coganchor_is_shipped_again_to_a_machine_that_has_lost_it(
    far: Fakes, program: Path, tmp_path: Path
) -> None:
    road = Road.to(Target.parse(f"ssh://lost-{tmp_path.name}"))
    landed = far.home / ".cache" / "humanize" / _shipped(program)
    road.installed()
    landed.unlink()

    road.forget()
    road.installed()

    assert landed.is_file()


def test_shipping_coganchor_sweeps_what_nobody_has_run_for_a_fortnight(
    far: Fakes, program: Path, tmp_path: Path
) -> None:
    cache = far.home / ".cache" / "humanize"
    cache.mkdir(parents=True)
    old, half, recent, other = (
        cache / "coganchor-0000000000000000",
        cache / "coganchor-1111111111111111.4242",
        cache / "coganchor-2222222222222222",
        cache / "humanize-3333333333333333.pyz",
    )
    weeks = time.time() - 15 * 24 * 3600
    for one in (old, half, recent, other):
        one.write_text("")
    for one in (old, half, other):
        os.utime(one, (weeks, weeks))

    Road.to(Target.parse(f"ssh://swept-{tmp_path.name}")).installed()

    assert sorted(one.name for one in cache.iterdir()) == sorted(
        [_shipped(program), recent.name, other.name]
    )


def test_a_harness_elsewhere_is_coganchor_cog(
    far: Fakes, program: Path, started: Path, tmp_path: Path
) -> None:
    road = Road.to(Target.parse(f"ssh://cog-{tmp_path.name}"))

    line = road.hmz(["internal", "anchor", "--target=local:/w", "claude"])
    subprocess.run(line, check=True, stdin=subprocess.DEVNULL)

    assert started.read_text() == "cog --target=local:/w claude\n"


def test_the_real_coganchor_runs_where_it_was_shipped(
    far: Fakes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = binary.found()
    if built is None:
        pytest.skip("no coganchor is built for this machine")
    monkeypatch.setenv(binary.VARIABLE, str(built))
    road = Road.to(Target.parse(f"ssh://real-{tmp_path.name}"))

    said = subprocess.run(
        road.hmz(["internal", "anchor", "serve", "--help"]),
        capture_output=True,
        text=True,
        check=False,
    )

    assert said.returncode == 0, said.stderr
    assert "--export" in said.stdout
    landed = far.home / ".cache" / "humanize" / _shipped(built)
    assert landed.is_file()
