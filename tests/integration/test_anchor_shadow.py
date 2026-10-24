"""The local mirror of a target's workspace, filled and pushed through a real serving half."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.policy import Layout, Router
from hmz.coganchor.providers import redirect
from hmz.coganchor.shadow import ShadowTree, prepare_shadow_root
from tests.integration.doubles_anchor import VIRTUAL, linked

if TYPE_CHECKING:
    from collections.abc import Iterator

#: Whether a turn can be supervised here, in a mirror of its own target's work.
SUPERVISED = sys.platform == "linux" and redirect.supervises()


@dataclass(frozen=True)
class Mirrored:
    """A target directory, its mirror here, and the tree keeping the two in step."""

    target: Path
    mirror: Path
    tree: ShadowTree

    def here(self, name: str) -> Path:
        return self.mirror / name


@pytest.fixture
def mirrored(tmp_path: Path) -> Iterator[Mirrored]:
    """A mirror of a target directory served over a socketpair."""
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    router = Router(layouts=(Layout.create(str(mirror), VIRTUAL),))
    with linked(tmp_path / "target") as link:
        yield Mirrored(link.real, mirror, ShadowTree(link.client, router))


def test_a_directory_is_materialised_with_the_targets_metadata(
    mirrored: Mirrored,
) -> None:
    (mirrored.target / "readme.md").write_text("x" * 1234)
    (mirrored.target / "src").mkdir()
    (mirrored.target / "link").symlink_to("readme.md")

    mirrored.tree.ensure_directory(str(mirrored.mirror))

    assert mirrored.here("readme.md").stat().st_size == 1234
    assert mirrored.here("src").is_dir()
    assert mirrored.here("link").readlink() == Path("readme.md")


def test_a_placeholder_holds_nothing_until_its_content_is_asked_for(
    mirrored: Mirrored,
) -> None:
    (mirrored.target / "big.txt").write_text("real content here")

    mirrored.tree.ensure_directory(str(mirrored.mirror))
    assert mirrored.here("big.txt").read_bytes() == b"\x00" * 17

    mirrored.tree.ensure_content(str(mirrored.here("big.txt")))
    assert mirrored.here("big.txt").read_text() == "real content here"


def test_an_edit_here_reaches_the_target_once_on_flush(mirrored: Mirrored) -> None:
    (mirrored.target / "edit.txt").write_text("before")
    mirrored.tree.ensure_content(str(mirrored.here("edit.txt")))

    mirrored.tree.note_write(str(mirrored.here("edit.txt")))
    mirrored.here("edit.txt").write_text("after")

    assert mirrored.tree.flush() == 1
    assert (mirrored.target / "edit.txt").read_text() == "after"
    assert mirrored.tree.flush() == 0


def test_a_file_made_here_reaches_the_target(mirrored: Mirrored) -> None:
    mirrored.tree.ensure_directory(str(mirrored.mirror))
    mirrored.tree.note_write(str(mirrored.here("made.txt")))
    mirrored.here("made.txt").write_text("made locally")

    mirrored.tree.flush()

    assert (mirrored.target / "made.txt").read_text() == "made locally"


def test_what_changed_on_the_target_is_seen_once_invalidated(
    mirrored: Mirrored,
) -> None:
    (mirrored.target / "shared.txt").write_text("v1")
    (mirrored.target / "doomed.txt").write_text("bye")
    mirrored.tree.ensure_content(str(mirrored.here("shared.txt")))

    (mirrored.target / "shared.txt").write_text("v2 is longer")
    (mirrored.target / "doomed.txt").unlink()
    mirrored.tree.invalidate()
    mirrored.tree.ensure_directory(str(mirrored.mirror))
    mirrored.tree.ensure_content(str(mirrored.here("shared.txt")))

    assert mirrored.here("shared.txt").read_text() == "v2 is longer"
    assert not mirrored.here("doomed.txt").exists()


def test_a_rename_keeps_what_the_file_is(mirrored: Mirrored) -> None:
    (mirrored.target / "old.txt").write_text("contents")
    mirrored.tree.ensure_directory(str(mirrored.mirror))

    (mirrored.target / "old.txt").rename(mirrored.target / "new.txt")
    mirrored.here("old.txt").rename(mirrored.here("new.txt"))
    mirrored.tree.rename(str(mirrored.here("old.txt")), str(mirrored.here("new.txt")))
    mirrored.tree.ensure_content(str(mirrored.here("new.txt")))

    assert mirrored.here("new.txt").read_text() == "contents"


def test_a_second_name_made_for_a_placeholder_reads_the_file(
    mirrored: Mirrored,
) -> None:
    (mirrored.target / "one.txt").write_text("real content here")
    mirrored.tree.ensure_directory(str(mirrored.mirror))
    (mirrored.target / "two.txt").hardlink_to(mirrored.target / "one.txt")
    mirrored.here("two.txt").hardlink_to(mirrored.here("one.txt"))

    mirrored.tree.duplicate(
        str(mirrored.here("one.txt")), str(mirrored.here("two.txt"))
    )
    mirrored.tree.ensure_content(str(mirrored.here("two.txt")))

    assert mirrored.here("two.txt").read_text() == "real content here"


def test_a_symlink_opened_fetches_what_it_leads_to(mirrored: Mirrored) -> None:
    (mirrored.target / "real.txt").write_text("what the link leads to")
    (mirrored.target / "alias").symlink_to("real.txt")
    mirrored.tree.ensure_directory(str(mirrored.mirror))

    mirrored.tree.ensure_content(str(mirrored.here("alias")))

    assert mirrored.here("real.txt").read_text() == "what the link leads to"


def test_nothing_outside_the_mirror_or_not_a_file_is_pushed(
    mirrored: Mirrored, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("this machine's own")
    mirrored.here("made").mkdir()
    (mirrored.target / "gone.txt").write_text("here for now")
    mirrored.tree.ensure_directory(str(mirrored.mirror))
    mirrored.here("gone.txt").write_text("edited")

    for one in (elsewhere, mirrored.here("made"), mirrored.here("gone.txt")):
        mirrored.tree.note_write(str(one))
    mirrored.here("gone.txt").unlink()

    assert mirrored.tree.flush() == 0
    assert not (mirrored.target / "made").exists()


def test_turns_sharing_a_mirror_lose_nothing_either_wrote(tmp_path: Path) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    router = Router(layouts=(Layout.create(str(mirror), VIRTUAL),))
    with linked(tmp_path / "target") as link:
        (link.real / "read.txt").write_text("read by one turn")
        one, other = (ShadowTree(link.client, router, mirror=str(mirror)) for _ in "12")
        one.ensure_content(str(mirror / "read.txt"))
        one.note_write(str(mirror / "pushed.txt"))
        (mirror / "pushed.txt").write_text("pushed by one turn")
        one.flush()

        other.ensure_directory(str(mirror))
        other.note_write(str(mirror / "pending.txt"))
        (mirror / "pending.txt").write_text("not pushed yet by the other")
        # One reads the directory again, as a turn does once a command of its own has run.
        one.invalidate()
        one.ensure_directory(str(mirror))
        one.flush()
        other.flush()

        for name, said in (
            ("read.txt", "read by one turn"),
            ("pushed.txt", "pushed by one turn"),
            ("pending.txt", "not pushed yet by the other"),
        ):
            assert (mirror / name).read_text() == said
            assert (link.real / name).read_text() == said


@pytest.mark.skipif(not SUPERVISED, reason="no turn can be supervised here")
@pytest.mark.parametrize("round_", range(3))
def test_turns_working_in_one_mirror_at_once_push_all_each_wrote(
    tmp_path: Path, round_: int
) -> None:
    target, mirror = tmp_path / "target", tmp_path / "mirror"
    target.mkdir()
    mirror.mkdir()

    def turn(n: int) -> subprocess.Popen[str]:
        # Writes a file, runs a command on the target, writes another and runs one again:
        # each command reads the directory back, with the other turns' files in it. Each
        # goes on past its first file only once every turn has written one, so that all
        # three are in the mirror at once: a turn is over in milliseconds, and one starting
        # after the others have gone begins knowing nothing, making placeholders of the
        # files they left -- as a turn alone in a mirror is meant to.
        wait = " && ".join(f"[ -e one{k} ]" for k in range(3))
        return subprocess.Popen(
            [
                *(sys.executable, "-Pm", "hmz", "internal", "anchor"),
                *("--target", "local:", "--workspace", str(target)),
                *("--shadow", str(mirror), "/bin/sh", "-c"),
                (
                    f"printf 'one {n}' > one{n}; until {wait}; do sleep 0.01; done; "
                    "ls > /dev/null; "
                    f"printf 'two {n}' > two{n}; ls > /dev/null"
                ),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    # Three turns of one run on one environment, as a flow's sessions are. Each knowing only
    # what it did itself, every round of this lost or zeroed some of the six files.
    turns = [turn(n) for n in range(3)]
    for one in turns:
        _, err = one.communicate(timeout=60)
        assert one.returncode == 0, err

    for n in range(3):
        for name, said in ((f"one{n}", f"one {n}"), (f"two{n}", f"two {n}")):
            assert (target / name).read_text() == said
            assert (mirror / name).read_text() == said


def test_a_directory_the_target_lacks_is_left_unmade(mirrored: Mirrored) -> None:
    mirrored.tree.ensure_directory(str(mirrored.mirror / "absent"))

    assert not (mirrored.mirror / "absent").exists()


def test_a_new_root_is_made_and_holds_no_bookkeeping(tmp_path: Path) -> None:
    root = tmp_path / "fresh"

    prepare_shadow_root(str(root))

    assert list(root.iterdir()) == []


def test_a_root_holding_files_nobody_mirrored_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "occupied"
    root.mkdir()
    (root / "important.txt").write_text("keep me")

    with pytest.raises(FileExistsError, match="not a Humanize mirror"):
        prepare_shadow_root(str(root))
    assert (root / "important.txt").exists()
    prepare_shadow_root(str(root), force=True)


def test_a_mirror_of_one_target_is_not_taken_for_another(tmp_path: Path) -> None:
    root = tmp_path / "reused"
    prepare_shadow_root(str(root), target="ssh://one")
    (root / "from-one.txt").write_text("only the first has this")

    prepare_shadow_root(str(root), target="ssh://one")
    with pytest.raises(FileExistsError, match="mirrors ssh://one"):
        prepare_shadow_root(str(root), target="ssh://two")
    assert (root / "from-one.txt").exists()
