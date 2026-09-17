"""Bundle fingerprints, checked against the two-hundred-megabyte binaries on this machine.

The other half of this file is `tests/integration/agents/test_patching.py`, which exercises the
parser and the patcher against a hand-built Bun stand-in -- a `---- Bun! ----` trailer, a module
table and a module carrying source and a bytecode pointer, small enough to assert every byte of.
Everything there is offline and hermetic, so CI runs it.

What is here cannot be: it reads whichever real `claude` or `opencode` is installed, once per
backend that has a bundle written down, to keep the fingerprints in `hmz.coganchor.backends`
honest against the releases actually shipping. A CI runner has no coding-agent CLI on it, and the
failure that would follow from pretending otherwise is the one the split exists to prevent -- a
skip that nobody reads, standing in for a check nobody is doing. The two below drive no model and
spend no tokens; they are gated with the rest of the agent-driving suite because what they read
is a binary this machine happens to have.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents.patching import located, patched
from hmz.coganchor.backends import PROFILES, Profile, program

if TYPE_CHECKING:
    from pathlib import Path

#: Every backend `hmz.coganchor.backends` wrote a bundle fingerprint down for. Read off the
#: catalogue rather than listed here, so a backend that gains a bundle is a backend this checks
#: without anybody remembering to add it -- which is the failure this whole file guards against,
#: one fact written in two places and right in only one of them.
BUNDLED = [one for one in PROFILES if one.bundles]


def _installed(where: Path) -> str:
    """What version the CLI at this path says it is, for a message about it having moved on.

    Asked of the program rather than read out of the bundle, because a fingerprint that stopped
    matching is one that can say nothing about the file it did not recognise.

    Args:
      where: The program to ask.

    Returns:
      What it said, on one line, or a note that it would not say -- which is itself worth
      reading, a CLI that cannot answer `--version` being a stranger sort of failure.
    """
    import subprocess

    try:
        done = subprocess.run(
            [str(where), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "would not run"
    return (
        done.stdout.strip().splitlines()[0] if done.stdout.strip() else "said nothing"
    )


def _drifted(profile: Profile, where: Path) -> str:
    """What to say to whoever meets a fingerprint that no longer names the installed bundle.

    Everything read off this machine rather than looked up afterwards: which backend it was,
    what version of it is actually installed, which file that resolved to, and what was being
    looked for inside it. The failure this test exists for is a silent one -- a reach that
    closed and a run that went on down the shallower road saying nothing -- so the loud version
    of it has to leave nobody anything to go digging for.

    Args:
      profile: The backend whose fingerprint did not match.
      where: The program its command resolved to.

    Returns:
      The message to fail with.
    """
    wanted = "\n".join(
        f"    {one.path!r} matching {one.says!r}"
        + (f" with digest {one.digest}" if one.digest else "")
        for one in profile.bundles
    )
    return (
        f"the {profile.name} bundle installed on this machine no longer answers to the"
        f" fingerprint written down for it in hmz.coganchor.backends.\n"
        f"  installed: {_installed(where)}\n"
        f"  resolved:  {where.resolve()}\n"
        f"  expected:  a Bun bundle picking out one module -- the one it matches in, or the"
        f" entry where the bundler inlined it into several -- by\n{wanted}\n"
        f"A release that moved the bundle closes the patched reach and leaves the run on the"
        f" shallower layer, so this is the place to notice it. Fix the fingerprint rather than"
        f" this test."
    )


@pytest.mark.agent
@pytest.mark.parametrize("profile", BUNDLED, ids=lambda one: one.name)
def test_the_written_down_fingerprint_still_names_the_installed_bundle(
    profile: Profile,
) -> None:
    """Every bundle fingerprint in `hmz.coganchor.backends` still names what is installed here.

    The fingerprint is the one fact this layer keeps about somebody else's release, and it fails
    quietly when it goes wrong: `patching` reaches nothing, the run takes the shallower way in,
    and no capability disappears from the catalogue to say so -- because `bundles` names no
    capability. So the drift has to be caught by somebody looking, and this is where they look.

    Skipped only where the CLI is not installed at all. It is gated behind the same flag the
    rest of the agent-driving suite is, since what it reads is a two-hundred-megabyte binary
    this machine happens to have.
    """
    from pathlib import Path

    where = program(profile.runs())
    if where is None:
        pytest.skip(f"{profile.runs()} is not installed on this machine")
    found = located(profile, Path(where))
    assert found is not None, _drifted(profile, Path(where))
    assert found.bundle.exists()


@pytest.mark.agent
@pytest.mark.timeout(600)
@pytest.mark.parametrize("profile", BUNDLED, ids=lambda one: one.name)
def test_a_copy_of_the_installed_bundle_is_re_embedded_and_still_starts(
    profile: Profile,
) -> None:
    """The patched road up to the edit, on the real thing rather than on a stand-in.

    A fingerprint that matches says a patch could be found, which is not yet a turn reached that
    way: the two-hundred-megabyte file still has to copy, answer to its fingerprint a second time
    as the copy, and start. Patched with nothing, so the substitution and the bytecode clearing
    are not what is exercised here -- those are asserted byte for byte against the stand-in in
    the integration half's `test_a_patched_copy_has_the_edit_and_its_bytecode_cleared`, which is
    where a rewrite can be read. What only the real binary can say is that a copy of it still
    runs.
    """
    from pathlib import Path

    where = program(profile.runs())
    if where is None:
        pytest.skip(f"{profile.runs()} is not installed on this machine")
    copy = patched(profile, Path(where), probe=True)
    # Not `_drifted`: `patched` also answers None for a directory it could not make, a copy that
    # would not fit, and a copy that would not start, and sending somebody to edit a fingerprint
    # over a full disk is the wrong errand.
    assert copy is not None, (
        f"no patched copy of {profile.name} could be made from {Path(where).resolve()};"
        f" run with logging at INFO for which step refused -- if it was the fingerprint,"
        f" test_the_written_down_fingerprint_still_names_the_installed_bundle says so plainly"
    )
    with copy:
        assert copy.path.exists()
