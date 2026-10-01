"""Every call that names a path, handed a CLI's credentials under a provider with no anchor.

`hmz internal cred` answers what a CLI names with the provider's file, and the calls it stops
for that are the ones the anchored supervisor stops: :data:`hmz.coganchor.pathcalls.PATHS`.
It used to keep a table of its own, which fell behind -- `statfs`, the extended attributes, a
watch, a change of owner or of times by `utime` were run against the path as named, which is
this machine's own account. The probe the anchored suite runs (`_spellings_probe.py`) makes
each of them here, by number, at a directory that only the provider has.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from tests.supervising import WITHOUT_BINDINGS, cred, traced

if (
    WITHOUT_BINDINGS
):  # what is imported below is the binding itself, so it is asked first
    pytest.skip(WITHOUT_BINDINGS, allow_module_level=True)

from tests.system.coganchor.probing import NUMBERS, PROBE, check, seed

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [traced, pytest.mark.timeout(120)]


def test_every_call_that_names_a_credential_is_answered_with_the_providers(
    tmp_path: Path,
) -> None:
    """The directory the CLI looks in is not there at all, so a call left unanswered fails."""
    named = tmp_path / "machine" / ".claude"
    instead = tmp_path / "provider" / "home"
    instead.mkdir(parents=True)
    seed(instead)

    result = cred(
        [
            f"--map={named}={instead}",
            "--",
            "python3",
            "-c",
            PROBE,
            str(named),
            NUMBERS,
            "--no-programs",
        ]
    )

    assert result.returncode == 0, result.stderr
    check(result.stdout)
    assert (instead / "watched.txt").read_text() == "seen\n"
    assert not named.exists()


def test_a_lookup_a_copy_cannot_answer_is_given_the_providers_own_file(
    tmp_path: Path,
) -> None:
    """An attribute is kept on the file, and a copy in memory has none of them."""
    named = tmp_path / "machine" / ".claude" / ".credentials.json"
    instead = tmp_path / "provider" / "home" / ".credentials.json"
    instead.parent.mkdir(parents=True)
    instead.write_text("the provider\n")
    try:
        os.setxattr(instead, "user.hmz", b"kept")
    except OSError:
        pytest.skip(f"{instead.parent} keeps no user attributes")
    program = (
        "import os, sys\n"
        "path = sys.argv[1]\n"
        "assert open(path).read() == 'the provider\\n'\n"
        "print(os.getxattr(path, 'user.hmz').decode())\n"
    )

    result = cred(
        [f"--map={named}={instead}", "--", "python3", "-c", program, str(named)]
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "kept"
