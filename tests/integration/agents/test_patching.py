"""Reaching a CLI by patching the bundle it ships, on a copy that is ours.

The layer is brittle on purpose -- it rewrites a minified single-file executable -- so what is
checked here is mostly the ways it refuses. A bundle it does not recognise, a fingerprint that
does not match, a site that has moved between the fingerprint and the edit: every one of them
returns nothing and leaves the run to reach the CLI a shallower way, and none of them raises.

The bundles themselves are 200 MB binaries that are not in the tree, so the parser and the
patcher are exercised against a hand-built stand-in with the same shape -- a `---- Bun! ----`
trailer, a module table, and a module carrying source and a bytecode pointer -- small enough to
assert every byte of. Nothing here leaves this process but to read files it wrote itself, so CI
runs the lot.

The other half is `tests/system/agents/test_patching.py`, which reads whichever real `claude` or
`opencode` is installed to keep the fingerprints in `hmz.coganchor.backends` honest against the
releases actually shipping. That needs a coding-agent CLI on the machine, which CI has not got,
and a check that silently skips on every run is no check -- so it lives where nothing pretends
otherwise.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents.patching import Patch, Patched, located, patched
from hmz.coganchor.backends import Bundled, Profile

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
