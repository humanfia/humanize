"""`hmz.coganchor.agents.patching`: a same-length patch on a copy of a Bun bundle."""

from __future__ import annotations

import dataclasses
import hashlib
import os
import struct
import subprocess
from typing import TYPE_CHECKING

import pytest

import hmz
from hmz.coganchor.agents.patching import Located, Patch, Patched, located, patched
from hmz.coganchor.backends import Bundled, Profile, named

if TYPE_CHECKING:
    from pathlib import Path

_TRAILER = b"\n---- Bun! ----\n"
_RECORD = 52


def _bundle(
    modules: list[tuple[str, bytes, bool]], *, entry: int = 0, prefix: bytes = b"ELF"
) -> bytes:
    """A Bun standalone executable as far as the patcher reads one.

    Args:
      modules: Each module's name, source and whether it carries bytecode.
      entry: The entry module's index.
      prefix: What the runtime would be, ahead of the graph.

    Returns:
      The file's bytes.
    """
    blob = bytearray(prefix)
    spans: list[tuple[int, int, int, int, int]] = []
    for name, source, bytecode in modules:
        name_at = len(blob)
        blob += name.encode()
        source_at = len(blob)
        blob += source
        spans.append((name_at, len(name), source_at, len(source), 4 if bytecode else 0))
    table_at = len(blob)
    for name_at, name_len, source_at, source_len, bc_len in spans:
        record = struct.pack("<IIII", name_at, name_len, source_at, source_len)
        record += b"\0" * 8 + struct.pack("<II", 0, bc_len)
        blob += record.ljust(_RECORD, b"\0")
    header = struct.pack("<QIII", len(blob), table_at, len(blob) - table_at, entry)
    return bytes(blob + header.ljust(32, b"\0") + _TRAILER)


def _profile(
    says: str = r'VERSION:"\d+"', digest: str = "", path: str = "*"
) -> Profile:
    claude = named("claude")
    assert claude is not None
    return dataclasses.replace(
        claude, bundles=(Bundled(path=path, says=says, digest=digest),)
    )


@pytest.fixture
def machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This machine's own directory, under the test."""
    at = tmp_path / "machine"
    at.mkdir()
    monkeypatch.setattr(hmz, "machine", lambda: at)
    return at


def _program(tmp_path: Path, data: bytes) -> Path:
    at = tmp_path / "install" / "claude"
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_bytes(data)
    return at


_TWO = [
    ("entry.js", b'let VERSION:"2";call(a)', True),
    ("other.js", b"call(a);call(a)", True),
]


def test_a_patch_is_the_same_length_on_both_sides() -> None:
    assert Patch(b"abc", b"xyz").into == b"xyz"
    with pytest.raises(ValueError, match="same length"):
        Patch(b"abc", b"ab")


def test_located_finds_the_module_the_fingerprint_names(tmp_path: Path) -> None:
    program = _program(tmp_path, _bundle(_TWO))
    assert located(_profile(), program) == Located(
        bundle=program.resolve(), module=0, digest=""
    )


def test_located_prefers_the_entry_where_several_match(tmp_path: Path) -> None:
    program = _program(tmp_path, _bundle(_TWO, entry=1))
    assert located(_profile(r"call\(a\)"), program) == Located(
        bundle=program.resolve(), module=1, digest=""
    )


def test_located_checks_a_recorded_digest(tmp_path: Path) -> None:
    data = _bundle(_TWO)
    program = _program(tmp_path, data)
    digest = hashlib.sha256(data).hexdigest()
    found = located(_profile(digest=digest), program)
    assert found is not None
    assert found.digest == digest
    assert located(_profile(digest="0" * 64), program) is None


@pytest.mark.parametrize(
    ("data", "says"),
    [
        (b"not a bundle at all", r"x"),
        (b"short" + _TRAILER, r"x"),
        (_bundle(_TWO), r"nowhere"),
        (
            _bundle(
                [("a", b"hit", False), ("b", b"hit", False), ("c", b"", False)], entry=2
            ),
            r"hit",
        ),
        (_bundle([]), r"x"),
        (_bundle(_TWO, entry=5), r"x"),
    ],
)
def test_located_leaves_alone_what_it_cannot_name(
    tmp_path: Path, data: bytes, says: str
) -> None:
    assert located(_profile(says), _program(tmp_path, data)) is None


def test_located_needs_a_bundle_written_down_and_matching_the_program(
    tmp_path: Path,
) -> None:
    program = _program(tmp_path, _bundle(_TWO))
    assert located(dataclasses.replace(_profile(), bundles=()), program) is None
    assert located(_profile(path="elsewhere.js"), program) is None


def test_patched_rewrites_a_copy_and_leaves_the_install(
    tmp_path: Path, machine: Path
) -> None:
    data = _bundle(_TWO)
    program = _program(tmp_path, data)
    held = patched(_profile(), program, [Patch(b"call(a)", b"nope(b)")], probe=False)
    assert isinstance(held, Patched)
    assert held.path.parent.parent == machine / "patched"
    assert held.path.name == "claude"
    # the one module rewritten and its bytecode cleared, so its source is what runs; the
    # other module left alone, and nothing moved
    assert held.path.read_bytes() == _bundle(
        [("entry.js", b'let VERSION:"2";nope(b)', False), _TWO[1]]
    )
    assert program.read_bytes() == data
    with held:
        pass
    assert not held.path.parent.exists()
    held.close()


def test_patched_with_nothing_to_rewrite_is_a_copy(
    tmp_path: Path, machine: Path
) -> None:
    data = _bundle(_TWO)
    held = patched(_profile(), _program(tmp_path, data), probe=False)
    assert held is not None
    assert held.path.read_bytes() == data
    held.close()


def test_a_patch_site_that_moved_falls_back(tmp_path: Path, machine: Path) -> None:
    held = patched(
        _profile(),
        _program(tmp_path, _bundle(_TWO)),
        [Patch(b"gone", b"here")],
        probe=False,
    )
    assert held is None
    assert list((machine / "patched").iterdir()) == []


@pytest.mark.parametrize("data", [b"not a bundle", _bundle(_TWO)])
def test_patched_falls_back_where_located_would(
    tmp_path: Path, machine: Path, data: bytes
) -> None:
    profile = _profile(r"nowhere")
    assert patched(profile, _program(tmp_path, data), probe=False) is None
    assert patched(_profile(path="elsewhere"), tmp_path / "x", probe=False) is None


def test_patched_sweeps_copies_whose_run_is_gone(tmp_path: Path, machine: Path) -> None:
    stale = machine / "patched" / "claude-999999999-abc"
    mine = machine / "patched" / f"claude-{os.getpid()}-abc"
    odd = machine / "patched" / "claude-notapid-abc"
    for one in (stale, mine, odd):
        one.mkdir(parents=True)
    held = patched(_profile(), _program(tmp_path, _bundle(_TWO)), probe=False)
    assert held is not None
    assert not stale.exists()
    assert mine.exists()
    assert odd.exists()
    held.close()


def test_patched_falls_back_where_no_directory_can_be_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where a directory goes")
    monkeypatch.setattr(hmz, "machine", lambda: blocked)
    assert patched(_profile(), _program(tmp_path, _bundle(_TWO)), probe=False) is None


@pytest.mark.parametrize(("status", "kept"), [(0, True), (1, False)])
def test_patched_keeps_only_a_copy_that_starts(
    tmp_path: Path,
    machine: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    kept: bool,
) -> None:
    asked: list[list[str]] = []

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        asked.append(argv)
        return subprocess.CompletedProcess(argv, status)

    monkeypatch.setattr(subprocess, "run", run)
    held = patched(_profile(), _program(tmp_path, _bundle(_TWO)))
    assert (held is not None) is kept
    assert [argv[1:] for argv in asked] == [["--version"]]
    assert len(list((machine / "patched").iterdir())) == int(kept)
    if held is not None:
        held.close()


def test_a_copy_that_cannot_be_started_is_not_kept(
    tmp_path: Path, machine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(*_: object, **__: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired("claude", 30)

    monkeypatch.setattr(subprocess, "run", run)
    assert patched(_profile(), _program(tmp_path, _bundle(_TWO))) is None
