"""The local mirror of a target's workspace, kept against a target held in a dict."""

from __future__ import annotations

import errno
import json
import os
import stat
import threading
from pathlib import Path
from typing import Any

import pytest

from hmz.coganchor.shadow import SHADOWS, FileRecord, ShadowTree, prepare_shadow_root
from tests.unit.coganchor.doubles_u8 import Entry, Layout, Router, Target, names


class Mirror:
    """A shadow tree at `<tmp>/mirror`, of a workspace the target calls `/w`."""

    def __init__(self, root: Path) -> None:
        self.root = root / "mirror"
        self.target = Target(
            {
                "/w": Entry("dir", mode=0o40755),
                "/w/a.txt": Entry("file", b"hello", 0o100640, 5_000_000_000),
                "/w/empty": Entry("file"),
                "/w/sub": Entry("dir", mode=0o40755),
                "/w/sub/deep.txt": Entry("file", b"deep"),
                "/w/link": Entry("link", target="a.txt", mode=0o120777),
            }
        )
        router: Any = Router(Layout(str(self.root), "/w"))
        client: Any = self.target
        self.tree = ShadowTree(client, router)

    def path(self, name: str = "") -> str:
        return str(self.root / name) if name else str(self.root)


@pytest.fixture
def mirror(tmp_path: Path) -> Mirror:
    return Mirror(tmp_path)


def test_a_directory_is_mirrored_as_placeholders(mirror: Mirror) -> None:
    mirror.tree.ensure_directory(mirror.path())
    held = Path(mirror.path())
    assert sorted(one.name for one in held.iterdir()) == [
        "a.txt",
        "empty",
        "link",
        "sub",
    ]
    placeholder = (held / "a.txt").lstat()
    assert placeholder.st_size == 5
    assert stat.S_IMODE(placeholder.st_mode) == 0o640
    assert placeholder.st_mtime_ns == 5_000_000_000
    assert (held / "sub").is_dir()
    assert (held / "link").readlink() == Path("a.txt")
    assert mirror.target.listed == ["/w"]


def test_a_directory_is_listed_once_per_generation(mirror: Mirror) -> None:
    mirror.tree.ensure_directory(mirror.path())
    mirror.tree.ensure_directory(mirror.path())
    assert mirror.target.listed == ["/w"]
    mirror.tree.invalidate()
    mirror.tree.ensure_directory(mirror.path())
    assert mirror.target.listed == ["/w", "/w"]


def test_a_path_mirrors_the_directory_holding_it(mirror: Mirror) -> None:
    mirror.tree.ensure_path(mirror.path("sub/deep.txt"))
    assert mirror.target.listed == ["/w/sub"]
    assert Path(mirror.path("sub/deep.txt")).stat().st_size == 4


def test_a_path_outside_the_workspace_is_left_alone(
    mirror: Mirror, tmp_path: Path
) -> None:
    mirror.tree.ensure_directory(str(tmp_path / "elsewhere"))
    mirror.tree.ensure_content(str(tmp_path / "elsewhere" / "f"))
    mirror.tree.note_write(str(tmp_path / "elsewhere" / "f"))
    assert mirror.target.listed == []
    assert mirror.tree.flush() == 0


def test_what_vanished_on_the_target_vanishes_here(mirror: Mirror) -> None:
    mirror.tree.ensure_directory(mirror.path())
    del mirror.target.tree["/w/a.txt"]
    mirror.tree.invalidate()
    mirror.tree.ensure_directory(mirror.path())
    assert not Path(mirror.path("a.txt")).exists()


def test_a_kind_changed_on_the_target_is_changed_here(mirror: Mirror) -> None:
    mirror.tree.ensure_directory(mirror.path())
    mirror.target.tree["/w/a.txt"] = Entry("dir", mode=0o40755)
    mirror.target.tree["/w/sub"] = Entry("file", b"now a file")
    mirror.target.tree["/w/link"] = Entry("link", target="empty", mode=0o120777)
    mirror.tree.invalidate()
    mirror.tree.ensure_directory(mirror.path())
    assert Path(mirror.path("a.txt")).is_dir()
    assert Path(mirror.path("sub")).is_file()
    assert Path(mirror.path("link")).readlink() == Path("empty")


@pytest.mark.parametrize("missing", [errno.ENOENT, errno.ENOTDIR, errno.EACCES])
def test_a_directory_gone_on_the_target_is_dropped_here(
    mirror: Mirror, missing: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    mirror.tree.ensure_directory(mirror.path("sub"))
    assert Path(mirror.path("sub")).is_dir()

    def refuse(path: str) -> dict[str, Any]:
        raise OSError(missing, "gone", path)

    monkeypatch.setattr(mirror.target, "listdir", refuse)
    mirror.tree.invalidate()
    mirror.tree.ensure_directory(mirror.path("sub"))
    assert not Path(mirror.path("sub")).exists()


def test_any_other_failure_to_list_is_raised(
    mirror: Mirror, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: str) -> dict[str, Any]:
        raise OSError(errno.EIO, "disk")

    monkeypatch.setattr(mirror.target, "listdir", broken)
    with pytest.raises(OSError, match="disk"):
        mirror.tree.ensure_directory(mirror.path())


def test_content_is_fetched_once(mirror: Mirror) -> None:
    mirror.tree.ensure_content(mirror.path("a.txt"))
    mirror.tree.ensure_content(mirror.path("a.txt"))
    assert Path(mirror.path("a.txt")).read_bytes() == b"hello"
    assert mirror.target.read == ["/w/a.txt"]
    fetched = Path(mirror.path("a.txt")).stat()
    assert fetched.st_mtime_ns == 5_000_000_000
    assert stat.S_IMODE(fetched.st_mode) == 0o640
    assert not any(name.endswith(".humanize-fetch") for name in names(mirror.path()))


def test_an_empty_file_needs_nothing_fetched(mirror: Mirror) -> None:
    mirror.tree.ensure_content(mirror.path("empty"))
    assert mirror.target.read == []


def test_a_link_is_followed_to_the_file_it_names(mirror: Mirror) -> None:
    mirror.tree.ensure_content(mirror.path("link"))
    assert mirror.target.read == ["/w/a.txt"]
    assert Path(mirror.path("link")).read_bytes() == b"hello"


def test_a_failed_fetch_leaves_the_placeholder_and_no_scratch(
    mirror: Mirror, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: str, sink: Any) -> dict[str, Any]:
        sink.write(b"hal")
        raise OSError(errno.EIO, "torn")

    monkeypatch.setattr(mirror.target, "read_file", broken)
    with pytest.raises(OSError, match="torn"):
        mirror.tree.ensure_content(mirror.path("a.txt"))
    assert names(mirror.path()) == ["a.txt", "empty", "link", "sub"]
    assert Path(mirror.path("a.txt")).read_bytes() == b"\0" * 5


def test_a_local_write_is_pushed_on_flush(mirror: Mirror) -> None:
    mirror.tree.ensure_content(mirror.path("a.txt"))
    mirror.tree.note_write(mirror.path("a.txt"))
    assert mirror.tree.flush() == 0  # nothing changed yet
    Path(mirror.path("a.txt")).write_bytes(b"changed")
    assert mirror.tree.flush() == 1
    assert mirror.target.written == {"/w/a.txt": b"changed"}
    assert mirror.tree.flush() == 0


def test_a_new_file_is_pushed_and_a_removed_one_is_not(mirror: Mirror) -> None:
    mirror.tree.ensure_directory(mirror.path())
    Path(mirror.path("new.txt")).write_bytes(b"fresh")
    mirror.tree.note_write(mirror.path("new.txt"))
    mirror.tree.note_write(mirror.path("never-made"))
    mirror.tree.note_write(mirror.path("sub"))
    assert mirror.tree.flush() == 1
    assert mirror.target.written == {"/w/new.txt": b"fresh"}


def test_a_forgotten_path_is_not_pushed(mirror: Mirror) -> None:
    mirror.tree.ensure_directory(mirror.path())
    Path(mirror.path("new.txt")).write_bytes(b"x")
    mirror.tree.note_write(mirror.path("new.txt"))
    mirror.tree.forget(mirror.path("new.txt"))
    assert mirror.tree.flush() == 0


def test_a_renamed_placeholder_is_fetched_under_its_new_name(mirror: Mirror) -> None:
    mirror.tree.ensure_directory(mirror.path())
    Path(mirror.path("a.txt")).rename(mirror.path("b.txt"))
    mirror.tree.rename(mirror.path("a.txt"), mirror.path("b.txt"))
    mirror.target.tree["/w/b.txt"] = mirror.target.tree["/w/a.txt"]
    mirror.tree.ensure_content(mirror.path("b.txt"))
    assert Path(mirror.path("b.txt")).read_bytes() == b"hello"
    assert mirror.target.read == ["/w/b.txt"]


def test_a_duplicated_placeholder_is_fetched_through_the_new_name(
    mirror: Mirror,
) -> None:
    mirror.tree.ensure_directory(mirror.path())
    os.link(mirror.path("a.txt"), mirror.path("hard.txt"))
    mirror.tree.duplicate(mirror.path("a.txt"), mirror.path("hard.txt"))
    mirror.tree.duplicate(mirror.path("unknown"), mirror.path("nothing"))
    mirror.target.tree["/w/hard.txt"] = mirror.target.tree["/w/a.txt"]
    mirror.tree.ensure_content(mirror.path("hard.txt"))
    assert mirror.target.read == ["/w/hard.txt"]


@pytest.mark.parametrize(
    ("entry", "matches"),
    [
        ({"kind": "file", "size": 5, "mtime_ns": 9}, True),
        ({"kind": "file", "size": 6, "mtime_ns": 9}, False),
        ({"kind": "file", "size": 5, "mtime_ns": 8}, False),
        ({"kind": "link", "size": 5, "mtime_ns": 9}, False),
    ],
)
def test_a_record_matches_the_target_by_kind_size_and_time(
    entry: dict[str, Any], matches: bool
) -> None:
    assert FileRecord("file", 0o100644, 5, 9).matches_remote(entry) is matches


def test_a_file_written_while_its_directory_is_listed_waits_for_the_next_flush(
    mirror: Mirror, monkeypatch: pytest.MonkeyPatch
) -> None:
    mirror.tree.ensure_content(mirror.path("a.txt"))
    mirror.tree.note_write(mirror.path("a.txt"))
    mirror.tree.note_write(mirror.path("late.txt"))
    listing = mirror.target.listdir

    def landing(path: str) -> dict[str, Any]:
        # Another turn's writes, landing between the flush and the listing it was for.
        Path(mirror.path("a.txt")).write_bytes(b"edited")
        Path(mirror.path("late.txt")).write_bytes(b"late")
        return listing(path)

    monkeypatch.setattr(mirror.target, "listdir", landing)
    mirror.tree.invalidate()
    mirror.tree.ensure_directory(mirror.path())

    assert Path(mirror.path("a.txt")).read_bytes() == b"edited"
    assert Path(mirror.path("late.txt")).read_bytes() == b"late"
    assert mirror.tree.flush() == 2
    assert mirror.target.written == {"/w/a.txt": b"edited", "/w/late.txt": b"late"}


def test_a_placeholder_written_over_is_not_fetched_over(mirror: Mirror) -> None:
    mirror.tree.ensure_directory(mirror.path())
    mirror.tree.note_write(mirror.path("a.txt"))
    Path(mirror.path("a.txt")).write_bytes(b"new")  # opened to truncate, so not fetched

    mirror.tree.ensure_content(mirror.path("a.txt"))

    assert Path(mirror.path("a.txt")).read_bytes() == b"new"
    assert mirror.target.read == []


def test_a_write_landing_while_its_file_is_pushed_is_pushed_too(
    mirror: Mirror, monkeypatch: pytest.MonkeyPatch
) -> None:
    mirror.tree.ensure_directory(mirror.path())
    mirror.tree.note_write(mirror.path("new.txt"))
    Path(mirror.path("new.txt")).write_bytes(b"half")
    sending = mirror.target.write_file
    racing = [b"half and the rest"]

    def landing(path: str, source: Any, mode: int | None = None) -> dict[str, Any]:
        said = sending(path, source, mode)
        while racing:
            Path(mirror.path("new.txt")).write_bytes(racing.pop())
        return said

    monkeypatch.setattr(mirror.target, "write_file", landing)
    assert mirror.tree.flush() == 1
    assert mirror.tree.flush() == 1
    assert mirror.target.written == {"/w/new.txt": b"half and the rest"}


# ---------------------------------------------------------- turns sharing one mirror


@pytest.fixture
def turns(mirror: Mirror) -> tuple[ShadowTree, ShadowTree]:
    """Two turns working in the one mirror at once, each a tree of its own."""
    router: Any = Router(Layout(mirror.path(), "/w"))
    client: Any = mirror.target
    return (
        ShadowTree(client, router, mirror=mirror.path()),
        ShadowTree(client, router, mirror=mirror.path()),
    )


def test_a_file_another_turn_has_not_pushed_yet_is_pushed_not_swept(
    mirror: Mirror, turns: tuple[ShadowTree, ShadowTree]
) -> None:
    one, other = turns
    one.ensure_directory(mirror.path())
    one.note_write(mirror.path("made.txt"))
    Path(mirror.path("made.txt")).write_bytes(b"MARK")

    other.ensure_directory(mirror.path())

    assert Path(mirror.path("made.txt")).read_bytes() == b"MARK"
    assert mirror.target.written == {"/w/made.txt": b"MARK"}
    assert one.flush() == 0


def test_a_file_another_turn_pushed_is_not_made_a_placeholder_again(
    mirror: Mirror, turns: tuple[ShadowTree, ShadowTree]
) -> None:
    one, other = turns
    one.ensure_directory(mirror.path())
    one.note_write(mirror.path("made.txt"))
    Path(mirror.path("made.txt")).write_bytes(b"MARK")
    assert one.flush() == 1

    other.ensure_directory(mirror.path())

    assert Path(mirror.path("made.txt")).read_bytes() == b"MARK"
    assert (one.flush(), other.flush()) == (0, 0)
    assert mirror.target.tree["/w/made.txt"].body == b"MARK"


def test_what_one_turn_fetched_another_reads_as_it_is(
    mirror: Mirror, turns: tuple[ShadowTree, ShadowTree]
) -> None:
    one, other = turns
    one.ensure_content(mirror.path("a.txt"))

    other.ensure_directory(mirror.path())
    assert Path(mirror.path("a.txt")).read_bytes() == b"hello"
    other.ensure_content(mirror.path("a.txt"))

    assert Path(mirror.path("a.txt")).read_bytes() == b"hello"
    assert mirror.target.read == ["/w/a.txt"]


def test_a_rename_one_turn_makes_is_known_to_the_others(
    mirror: Mirror, turns: tuple[ShadowTree, ShadowTree]
) -> None:
    one, other = turns
    one.ensure_directory(mirror.path())
    other.ensure_directory(mirror.path())
    mirror.target.tree["/w/b.txt"] = mirror.target.tree.pop("/w/a.txt")
    Path(mirror.path("a.txt")).rename(mirror.path("b.txt"))
    one.rename(mirror.path("a.txt"), mirror.path("b.txt"))

    other.ensure_content(mirror.path("b.txt"))

    assert Path(mirror.path("b.txt")).read_bytes() == b"hello"


def test_a_turn_alone_in_a_mirror_knows_nothing_of_turns_gone(
    mirror: Mirror, turns: tuple[ShadowTree, ShadowTree]
) -> None:
    one, other = turns
    one.ensure_content(mirror.path("a.txt"))
    one.close()
    other.close()
    # Changed while nobody worked in it, keeping the size and time it had.
    Path(mirror.path("a.txt")).write_bytes(b"\0" * 5)
    os.utime(mirror.path("a.txt"), ns=(5_000_000_000, 5_000_000_000))
    router: Any = Router(Layout(mirror.path(), "/w"))
    client: Any = mirror.target

    ShadowTree(client, router, mirror=mirror.path()).ensure_content(
        mirror.path("a.txt")
    )

    assert Path(mirror.path("a.txt")).read_bytes() == b"hello"


def test_a_mirror_that_cannot_be_shared_is_kept_alone(
    mirror: Mirror, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "blocked").write_text("not a directory")
    monkeypatch.setenv(SHADOWS, str(tmp_path / "blocked"))
    router: Any = Router(Layout(mirror.path(), "/w"))
    client: Any = mirror.target

    tree = ShadowTree(client, router, mirror=mirror.path())
    tree.ensure_content(mirror.path("a.txt"))

    assert Path(mirror.path("a.txt")).read_bytes() == b"hello"
    tree.close()


# ------------------------------------------------------------------- the mirror's root


def test_the_registry_lives_where_the_environment_says(tmp_path: Path) -> None:
    assert os.environ[SHADOWS].startswith(str(tmp_path))
    prepare_shadow_root(str(tmp_path / "m"), target="ssh://a")
    records = list(Path(os.environ[SHADOWS]).iterdir())
    assert len(records) == 1
    assert json.loads(records[0].read_text()) == {
        "shadow": str(tmp_path / "m"),
        "target": "ssh://a",
    }


def test_a_new_root_is_made(tmp_path: Path) -> None:
    prepare_shadow_root(str(tmp_path / "a" / "b"), target="ssh://a")
    assert (tmp_path / "a" / "b").is_dir()


def test_an_empty_directory_is_taken(tmp_path: Path) -> None:
    (tmp_path / "m").mkdir()
    prepare_shadow_root(str(tmp_path / "m"), target="ssh://a")


def test_a_directory_of_somebody_elses_files_is_refused(tmp_path: Path) -> None:
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "precious").write_text("x")
    with pytest.raises(FileExistsError, match="not a Humanize mirror"):
        prepare_shadow_root(str(tmp_path / "m"), target="ssh://a")
    prepare_shadow_root(str(tmp_path / "m"), target="ssh://a", force=True)


def test_a_mirror_is_reused_for_its_own_target_only(tmp_path: Path) -> None:
    prepare_shadow_root(str(tmp_path / "m"), target="ssh://a")
    (tmp_path / "m" / "f").write_text("mirrored")
    prepare_shadow_root(str(tmp_path / "m"), target="ssh://a")
    with pytest.raises(FileExistsError, match="mirrors ssh://a, not ssh://b"):
        prepare_shadow_root(str(tmp_path / "m"), target="ssh://b")
    prepare_shadow_root(str(tmp_path / "m"), target="ssh://b", force=True)
    prepare_shadow_root(str(tmp_path / "m"), target="ssh://b")


def test_a_turn_starting_while_another_records_the_mirror_finds_it_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "m"
    prepare_shadow_root(str(root), target="ssh://a")
    (root / "kept.txt").write_text("what the target has")
    turns: list[str] = []

    def starting(dumping: Any) -> Any:
        def dumped(*args: Any, **kwargs: Any) -> Any:
            if not turns:
                turns.append("another")
                prepare_shadow_root(str(root), target="ssh://a")
            return dumping(*args, **kwargs)

        return dumped

    # Another turn starts in the mirror just as this one writes its record.
    monkeypatch.setattr(json, "dump", starting(json.dump))
    monkeypatch.setattr(json, "dumps", starting(json.dumps))
    prepare_shadow_root(str(root), target="ssh://a")

    assert turns == ["another"]
    assert (root / "kept.txt").read_text() == "what the target has"


def test_turns_starting_in_one_mirror_at_once_are_none_refused(tmp_path: Path) -> None:
    root = tmp_path / "m"
    prepare_shadow_root(str(root), target="ssh://a")
    (root / "kept.txt").write_text("what the target has")
    refused: list[OSError] = []
    together = threading.Barrier(3)

    def turn() -> None:
        together.wait()
        for _ in range(20):
            try:
                prepare_shadow_root(str(root), target="ssh://a")
            except OSError as why:
                refused.append(why)

    # Three turns of one run starting in their mirror at once, again and again: with the
    # record truncated and then filled, one or another of them read it empty.
    turns = [threading.Thread(target=turn) for _ in range(3)]
    for one in turns:
        one.start()
    for one in turns:
        one.join()

    assert refused == []
    # The record alone: nothing written beside it is left there.
    assert len(list(Path(os.environ[SHADOWS]).iterdir())) == 1


def test_a_file_is_no_root(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x")
    with pytest.raises(NotADirectoryError):
        prepare_shadow_root(str(tmp_path / "f"))
