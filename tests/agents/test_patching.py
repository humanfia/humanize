"""Reaching a CLI by patching the bundle it ships, on a copy that is ours.

The layer is brittle on purpose -- it rewrites a minified single-file executable -- so what is
checked here is mostly the ways it refuses. A bundle it does not recognise, a fingerprint that
does not match, a site that has moved between the fingerprint and the edit: every one of them
returns nothing and leaves the run to reach the CLI a shallower way, and none of them raises.

The bundles themselves are 200 MB binaries that are not in the tree, so the parser and the
patcher are exercised against a hand-built stand-in with the same shape -- a `---- Bun! ----`
trailer, a module table, and a module carrying source and a bytecode pointer -- small enough to
assert every byte of. The two tests at the end reach for the real binaries instead, once per
backend that has a bundle written down, to keep the fingerprints in `hmz.coganchor.backends` honest
against the releases actually installed -- and skip where a backend is not installed here.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents.patching import Patch, Patched, located, patched
from hmz.coganchor.backends import PROFILES, Bundled, Profile, program

if TYPE_CHECKING:
    from pathlib import Path

_TRAILER = b"\n---- Bun! ----\n"


def _bun(modules: list[tuple[str, bytes, bool]], entry: int) -> bytes:
    """A file shaped like a Bun standalone executable, small enough to reason about.

    Args:
      modules: One `(name, source, carries_bytecode)` per module, in graph order.
      entry: Which of them the graph names as its entry point.

    Returns:
      The bytes: every module's name and source packed at the front, a fixed-size record
      apiece behind them, then the 32-byte header and the trailer the loader reads back from.
    """
    blob = bytearray()
    spans: list[tuple[int, int, int, int, bool]] = []
    for name, source, has_bytecode in modules:
        raw_name = name.encode()
        name_off = len(blob)
        blob += raw_name
        cont_off = len(blob)
        blob += source
        spans.append((name_off, len(raw_name), cont_off, len(source), has_bytecode))
    table_off = len(blob)
    for name_off, name_len, cont_off, cont_len, has_bytecode in spans:
        record = bytearray(52)
        struct.pack_into("<IIII", record, 0, name_off, name_len, cont_off, cont_len)
        if has_bytecode:
            # Anywhere real and a non-zero length is enough: what is checked is that the
            # patcher zeroes it, not where it pointed.
            struct.pack_into("<II", record, 24, cont_off, cont_len)
        blob += record
    table_len = 52 * len(modules)
    header_at = len(blob)
    # The graph blob is everything up to the header; the loader reads its length back to find
    # where, from the file's end, the blob began -- so with the blob at the front the length is
    # exactly its own size and the base works out to zero.
    byte_count = header_at
    header = struct.pack("<QIIIIII", byte_count, table_off, table_len, entry, 0, 0, 0)
    return bytes(blob) + header + _TRAILER


def _bundled(where: Path, name: str, source: bytes, *, says: bytes) -> Profile:
    """A profile whose one bundle is a stand-in written to disk under the given name.

    Args:
      where: The directory to write the file in, which is the CLI's install directory.
      name: What the file is called, which is what the profile globs for and runs as.
      source: The source of the module the fingerprint matches in.
      says: The pattern the fingerprint says the bundle must match.

    Returns:
      A profile carrying that one bundle and nothing else that matters here.
    """
    (where / name).write_bytes(_bun([("/$bunfs/root/cli", source, True)], entry=0))
    return Profile(
        name="stub",
        aliases=("stub",),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(),
        bundles=(Bundled(path=name, says=says.decode()),),
    )


def test_a_patch_must_be_the_same_length_on_both_sides() -> None:
    """A packed bundle cannot take an insertion, so the shorter grammar is refused up front."""
    with pytest.raises(ValueError, match="same length"):
        Patch(find=b"/bin/bash", into=b"/bin/sh")


def test_a_file_that_is_not_a_bundle_is_recognised_as_one_and_left_alone(
    tmp_path: Path,
) -> None:
    """No trailer means nothing here made it, so there is nothing here to patch."""
    (tmp_path / "cli").write_bytes(b"just an ordinary file, no trailer in sight")
    profile = Profile(
        name="stub",
        aliases=("stub",),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(),
        bundles=(Bundled(path="cli", says="anything"),),
    )
    assert located(profile, tmp_path / "cli") is None
    assert patched(profile, tmp_path / "cli", probe=False) is None


def test_a_backend_with_no_bundle_written_down_is_not_reached_here(
    tmp_path: Path,
) -> None:
    """The layer only reaches a CLI something wrote a bundle down for."""
    (tmp_path / "cli").write_bytes(_bun([("/$bunfs/root/cli", b"x", True)], entry=0))
    bare = Profile(
        name="bare", aliases=("bare",), home_var="", home_dir="", logs=(), efforts=()
    )
    assert located(bare, tmp_path / "cli") is None
    assert patched(bare, tmp_path / "cli", probe=False) is None


def test_an_empty_file_falls_back_rather_than_raising(tmp_path: Path) -> None:
    """A half-written install leaves a zero-byte program, which is left alone, not crashed on."""
    (tmp_path / "cli").write_bytes(b"")
    profile = Profile(
        name="stub",
        aliases=("stub",),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(),
        bundles=(Bundled(path="cli", says="anything"),),
    )
    # mmap of an empty file raises rather than returning nothing, so this is the ValueError that
    # would otherwise reach the run: it must be an ordinary fall back.
    assert located(profile, tmp_path / "cli") is None
    assert patched(profile, tmp_path / "cli", probe=False) is None


def test_a_bundle_that_answers_to_its_fingerprint_says_where_a_patch_lands(
    tmp_path: Path,
) -> None:
    """A located bundle names the file and the module a patch is written into."""
    profile = _bundled(
        tmp_path, "cli", b'VERSION:"1.2.3"; run();', says=b'VERSION:"1.2.3"'
    )
    where = located(profile, tmp_path / "cli")
    assert where is not None
    assert where.bundle == tmp_path / "cli"
    assert where.module == 0
    # No digest was recorded to compare against, so none was computed -- a whole-file hash on
    # every start is a cost the pattern already saves.
    assert where.digest == ""


def test_a_recorded_digest_is_computed_and_a_matching_one_is_accepted(
    tmp_path: Path,
) -> None:
    """Where a digest is written down it is read back, and the file it matches is located."""
    import hashlib

    body = _bun([("/$bunfs/root/cli", b'VERSION:"1.2.3"', True)], entry=0)
    (tmp_path / "cli").write_bytes(body)
    profile = Profile(
        name="stub",
        aliases=("stub",),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(),
        bundles=(
            Bundled(
                path="cli",
                says='VERSION:"1.2.3"',
                digest=hashlib.sha256(body).hexdigest(),
            ),
        ),
    )
    where = located(profile, tmp_path / "cli")
    assert where is not None
    assert where.digest == hashlib.sha256(body).hexdigest()


def test_a_fingerprint_that_does_not_match_falls_back_rather_than_patching(
    tmp_path: Path,
) -> None:
    """A version the bundle does not say is a bundle nobody here has seen."""
    profile = _bundled(
        tmp_path, "cli", b'VERSION:"1.2.3"; run();', says=b'VERSION:"9.9.9"'
    )
    assert located(profile, tmp_path / "cli") is None
    assert patched(profile, tmp_path / "cli", probe=False) is None


def test_a_fingerprint_written_to_a_shape_survives_the_release_that_moves_it(
    tmp_path: Path,
) -> None:
    """The point of the whole thing: a bundle whose version moved on still answers.

    A fingerprint spelled as one release's bytes is one that stops matching on the next release
    and says nothing about having stopped -- the patched reach closes, the run goes on down the
    shallower road, and no test anywhere is redder for it. Written to the shape the constant
    keeps instead, the same pattern names the same module across every release that keeps
    shipping a version there.
    """
    shape = rb'VERSION:"\d+\.\d+\.\d+"'
    for release in (b'VERSION:"2.1.269"', b'VERSION:"2.1.272"', b'VERSION:"3.0.0"'):
        profile = _bundled(tmp_path, "cli", release + b"; run();", says=shape)
        where = located(profile, tmp_path / "cli")
        assert where is not None, release
        assert where.module == 0
    # And still refuses a file with no version constant where the patch expects one, which is
    # what a fingerprint is for: a shape is not the same as no fingerprint at all.
    profile = _bundled(tmp_path, "cli", b"the bundler moved it; run();", says=shape)
    assert located(profile, tmp_path / "cli") is None


def test_a_fingerprint_that_is_not_a_pattern_is_refused_where_it_is_written_down() -> (
    None
):
    """A pattern that will not compile must fail at the catalogue, not at the run.

    The layer that matches it promises never to raise, so an unparseable pattern reaching it
    would be a run that fell back for a reason nothing could name.
    """
    with pytest.raises(ValueError, match="must be a pattern"):
        Bundled(path="cli", says='VERSION:"[2.1')


def test_a_recorded_digest_that_has_changed_falls_back(tmp_path: Path) -> None:
    """A digest is the whole bundle pinned, so a byte anywhere in it that changed falls back."""
    (tmp_path / "cli").write_bytes(
        _bun([("/$bunfs/root/cli", b'VERSION:"1.2.3"', True)], entry=0)
    )
    profile = Profile(
        name="stub",
        aliases=("stub",),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(),
        bundles=(Bundled(path="cli", says='VERSION:"1.2.3"', digest="0" * 64),),
    )
    assert located(profile, tmp_path / "cli") is None


def test_a_line_inlined_into_several_modules_is_taken_to_mean_the_entry(
    tmp_path: Path,
) -> None:
    """A constant Bun copies into every module means the entry, which is what a patch targets."""
    said = b'VERSION:"1.2.3"'
    (tmp_path / "cli").write_bytes(
        _bun(
            [
                ("/$bunfs/root/a", said, True),
                ("/$bunfs/root/cli", said + b";main", True),
            ],
            entry=1,
        )
    )
    profile = Profile(
        name="stub",
        aliases=("stub",),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(),
        bundles=(Bundled(path="cli", says='VERSION:"1.2.3"'),),
    )
    where = located(profile, tmp_path / "cli")
    assert where is not None
    assert where.module == 1


def test_a_line_in_one_module_that_is_not_the_entry_still_names_that_module(
    tmp_path: Path,
) -> None:
    """A fingerprint unique to one module -- opencode's version is -- names that one."""
    (tmp_path / "cli").write_bytes(
        _bun(
            [
                ("/$bunfs/root/cli", b"the entry, no marker here", True),
                ("/$bunfs/root/v", b'var n="1.2.3"', False),
            ],
            entry=0,
        )
    )
    profile = Profile(
        name="stub",
        aliases=("stub",),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(),
        bundles=(Bundled(path="cli", says='var n="1.2.3"'),),
    )
    where = located(profile, tmp_path / "cli")
    assert where is not None
    assert where.module == 1


def test_a_patched_copy_has_the_edit_and_its_bytecode_cleared(tmp_path: Path) -> None:
    """The copy carries the rewrite, and the module's bytecode pointer is zeroed so it runs."""
    profile = _bundled(
        tmp_path, "cli", b'VERSION:"1.2.3"; run();', says=b'VERSION:"1.2.3"'
    )
    held = patched(
        profile,
        tmp_path / "cli",
        [Patch(b'VERSION:"1.2.3"', b'VERSION:"1.2.4"')],
        probe=False,
    )
    assert held is not None
    assert held.path.exists()
    copy = held.path.read_bytes()
    assert b'VERSION:"1.2.4"' in copy
    assert b'VERSION:"1.2.3"' not in copy
    # The one module's bytecode pointer -- the eight bytes at record+24 -- is now zero.
    end = copy.rfind(_TRAILER)
    byte_count, table_off, _table_len, _entry, *_ = struct.unpack_from(
        "<QIIIIII", copy, end - 32
    )
    base = end + len(_TRAILER) - 48 - byte_count
    assert struct.unpack_from("<II", copy, base + table_off + 24) == (0, 0)
    held.close()


def test_a_patch_whose_site_has_moved_leaves_no_copy_behind(tmp_path: Path) -> None:
    """A site the fingerprint found but the patch cannot is a bundle to leave whole."""
    from hmz import home

    profile = _bundled(
        tmp_path, "cli", b'VERSION:"1.2.3"; run();', says=b'VERSION:"1.2.3"'
    )
    held = patched(
        profile,
        tmp_path / "cli",
        [Patch(b"gone-from-here!", b"still-not-here!")],
        probe=False,
    )
    assert held is None
    # Nothing was left in the directory patches are made in -- the copy that could not be
    # patched is removed rather than handed back half-done.
    made = home() / "patched"
    assert not made.exists() or not any(made.iterdir())


def test_a_patched_copy_is_removed_when_the_handle_is_dropped(tmp_path: Path) -> None:
    """A 200 MB copy is session-scoped, so dropping the handle leaves nothing behind."""
    import gc

    profile = _bundled(
        tmp_path, "cli", b'VERSION:"1.2.3"; run();', says=b'VERSION:"1.2.3"'
    )
    held = patched(profile, tmp_path / "cli", probe=False)
    assert held is not None
    where = held.path.parent
    assert where.exists()
    del held
    gc.collect()
    assert not where.exists()


def test_a_patched_copy_can_be_used_as_a_context_manager(tmp_path: Path) -> None:
    """Leaving the block removes the copy, which is what a session-scoped thing does."""
    profile = _bundled(
        tmp_path, "cli", b'VERSION:"1.2.3"; run();', says=b'VERSION:"1.2.3"'
    )
    held = patched(profile, tmp_path / "cli", probe=False)
    assert held is not None
    assert isinstance(held, Patched)
    with held as open_copy:
        where = open_copy.path.parent
        assert where.exists()
    assert not where.exists()


def test_a_copy_left_by_a_process_that_is_gone_is_swept_before_a_new_one(
    tmp_path: Path,
) -> None:
    """A run killed outright collects nothing, so the next one reaps what its dead pid left."""
    from hmz import home

    made = home() / "patched"
    made.mkdir(parents=True)
    # A copy named for a process id nothing is running under -- a run that was killed.
    dead = made / "claude-2147483646-abcdef"
    dead.mkdir()
    (dead / "claude").write_bytes(b"an orphaned copy")
    profile = _bundled(
        tmp_path, "cli", b'VERSION:"1.2.3"; run();', says=b'VERSION:"1.2.3"'
    )
    held = patched(profile, tmp_path / "cli", probe=False)
    assert held is not None
    # The orphan is gone; the copy this run made is not.
    assert not dead.exists()
    assert held.path.exists()
    held.close()


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
    `test_a_patched_copy_has_the_edit_and_its_bytecode_cleared`, which is where a rewrite can be
    read. What only the real binary can say is that a copy of it still runs.
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
