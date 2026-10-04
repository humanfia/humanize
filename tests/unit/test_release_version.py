"""The version a release tag stamps into pyproject.toml.

Driven the way the release drives it -- by path, as a program -- since that is the only way
anything reaches it, and what a tag it refuses prints is the whole of what somebody who
pushed one is told.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "release_version.py"


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("tag", "version"),
    [
        ("v0.1.0", "0.1.0"),
        ("v1.2.3", "1.2.3"),
        ("v10.20.30", "10.20.30"),
        ("v1.2.3-rc.1", "1.2.3rc1"),
        ("v1.2.3-beta.2", "1.2.3b2"),
        ("v1.2.3-alpha.1", "1.2.3a1"),
        ("v1.2.3-rc.0", "1.2.3rc0"),
    ],
)
def test_a_release_tag_is_its_pep_440_version(tag: str, version: str) -> None:
    ran = _run(tag)

    assert (ran.returncode, ran.stdout, ran.stderr) == (0, f"{version}\n", "")


@pytest.mark.parametrize(
    "tag",
    [
        "1.2.3",  # no v
        "v1.2",  # no patch
        "v1.2.3.4",
        "v01.2.3",  # a leading zero SemVer forbids
        "v1.2.3-rc",  # a pre-release with no number
        "v1.2.3-rc.01",
        "v1.2.3-preview.1",  # a label PEP 440 has no word for
        "v1.2.3-rc.1.2",
        "v1.2.3+build.5",  # a local version, which PyPI refuses
        "v1.2.3-rc.1+build.5",
        "",
    ],
)
def test_a_tag_no_release_is_cut_from_is_refused_with_what_one_looks_like(
    tag: str,
) -> None:
    ran = _run(tag)

    assert ran.returncode == 1
    assert ran.stdout == ""
    assert f"{tag!r} is not a release tag" in ran.stderr
    assert "vX.Y.Z-rc.N" in ran.stderr


@pytest.mark.parametrize("argv", [(), ("v1.2.3", "v1.2.4")])
def test_it_wants_exactly_one_tag(argv: tuple[str, ...]) -> None:
    ran = _run(*argv)

    assert ran.returncode == 2
    assert ran.stdout == ""
    assert ran.stderr.startswith("usage:")
