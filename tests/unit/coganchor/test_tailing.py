"""Copying what a CLI on another machine logs, against a road that answers from memory."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any, cast

from hmz.coganchor.anchor import AnchorConfig
from hmz.coganchor.backends import named
from hmz.coganchor.tailing import Tail, road, roots
from hmz.coganchor.transport import Target

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from hmz.coganchor.backends import Profile
    from hmz.coganchor.transport import Road


class Far:
    """A machine whose CLI home is `files`, reached by the two commands a tail runs."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.asked: list[list[str]] = []
        self.failing = False
        self.target = Target.parse("ssh://far")

    def run(
        self, argv: Sequence[str], feeding: bytes = b"", timeout: float | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        del feeding, timeout
        self.asked.append(list(argv))
        if self.failing:
            return subprocess.CompletedProcess(argv, 255, b"", b"no route")
        args = list(argv[8:])
        if "find" in argv[2]:
            said = b"".join(
                f"{len(body)} {path}\n".encode() for path, body in self.files.items()
            )
        else:
            said = b""
            while len(args) >= 3:
                path, start, end = args[0], int(args[1]), int(args[2])
                said += self.files[path][start:end]
                args = args[3:]
        return subprocess.CompletedProcess(argv, 0, said, b"")


def _claude() -> Profile:
    profile = named("claude")
    assert profile is not None
    return profile


def _tail(far: Far, into: Path, home: str = "") -> Tail:
    return Tail(cast("Road", far), _claude(), into, home)


def test_a_road_is_to_where_the_cli_keeps_its_sessions() -> None:
    native = road(AnchorConfig(target="ssh://box", native=True))
    afar = road(AnchorConfig(target="ssh://box", harness="ssh://gpu"))
    assert native is not None
    assert native.target.host == "box"
    assert afar is not None
    assert afar.target.host == "gpu"
    assert road(AnchorConfig(target="ssh://box")) is None
    assert road(AnchorConfig(target="tcp://box:9", native=True)) is None


def test_whole_lines_are_copied_as_they_land_and_the_rest_at_the_end(
    tmp_path: Path,
) -> None:
    far = Far({"projects/-w/s1.jsonl": b"one\ntw"})
    tail = _tail(far, tmp_path)
    copy = tmp_path / "projects" / "-w" / "s1.jsonl"

    tail.copy(["s1"])
    assert copy.read_bytes() == b"one\n"
    far.files["projects/-w/s1.jsonl"] += b"o\nthr"
    tail.copy(["s1"])
    assert copy.read_bytes() == b"one\ntwo\n"
    assert far.asked[-1][8:] == ["projects/-w/s1.jsonl", "4", "11"]
    tail.copy(["s1"], whole=True)
    assert copy.read_bytes() == b"one\ntwo\nthr"


def test_the_home_the_turn_was_given_is_the_one_read(tmp_path: Path) -> None:
    far = Far({})
    _tail(far, tmp_path, "/there/claude").copy(["s1"])
    (asked,) = far.asked
    assert asked[4:8] == ["CLAUDE_CONFIG_DIR", ".claude", "", "/there/claude"]
    assert "projects/*/s1.jsonl" in asked


def test_a_file_written_again_is_copied_again_from_the_start(tmp_path: Path) -> None:
    far = Far({"projects/-w/s1.jsonl": b"one\ntwo\n"})
    tail = _tail(far, tmp_path)
    tail.copy(["s1"])
    far.files["projects/-w/s1.jsonl"] = b"new\n"
    tail.copy(["s1"])
    assert (tmp_path / "projects" / "-w" / "s1.jsonl").read_bytes() == b"new\n"


def test_nothing_outside_the_home_is_written(tmp_path: Path) -> None:
    far = Far({"../escaped.jsonl": b"x\n", "/abs.jsonl": b"x\n"})
    _tail(far, tmp_path / "in").copy(["s1"])
    assert not list(tmp_path.rglob("*.jsonl"))


def test_a_copy_that_fails_is_said_and_never_raised(
    tmp_path: Path, caplog: Any
) -> None:
    far = Far({"projects/-w/s1.jsonl": b"one\n"})
    far.failing = True
    tail = _tail(far, tmp_path)
    tail.copy(["s1"])
    tail.copy(["s1"])
    assert [one.levelname for one in caplog.records] == ["WARNING"]
    assert not (tmp_path / "projects").exists()


def test_a_log_written_in_place_is_copied_whole_and_only_at_the_end(
    tmp_path: Path,
) -> None:
    profile = named("agy")
    assert profile is not None
    far = Far({"conversations/s1.db": b"\x00page"})
    tail = Tail(cast("Road", far), profile, tmp_path)
    tail.copy(["s1"])
    assert not (tmp_path / "conversations").exists()
    tail.copy(["s1"], whole=True)
    assert (tmp_path / "conversations" / "s1.db").read_bytes() == b"\x00page"


def test_a_session_not_followed_is_not_copied_as_it_is_forgotten(
    tmp_path: Path,
) -> None:
    far = Far({"projects/-w/s1.jsonl": b"one\n"})
    _tail(far, tmp_path).forget("s1")
    assert not far.asked


def test_every_home_the_turns_told_of_is_followed_and_none_before(
    tmp_path: Path,
) -> None:
    far = Far({})
    told = tmp_path / "homes"
    told.mkdir()
    tail = Tail(cast("Road", far), _claude(), tmp_path / "in", "/ignored", told)
    tail.copy(["s1"])
    assert not far.asked
    (told / "t1").write_text("CLAUDE_CONFIG_DIR=/tmp/a\nCODEX_HOME=/tmp/b\n")
    (told / "t2").write_text("CLAUDE_CONFIG_DIR=/tmp/c\n")
    tail.copy(["s1"])
    assert [one[7] for one in far.asked] == ["/tmp/a", "/tmp/c"]


def test_a_copy_written_meanwhile_by_something_else_is_left_as_it_is(
    tmp_path: Path,
) -> None:
    far = Far({"projects/-w/s1.jsonl": b"one\n"})
    copy = tmp_path / "projects" / "-w" / "s1.jsonl"
    real = far.run

    def bringing(
        argv: Sequence[str], feeding: bytes = b"", timeout: float | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        if "find" not in argv[2]:
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(b"one\ntwo\n")
        return real(argv, feeding, timeout)

    far.run = bringing
    _tail(far, tmp_path).copy(["s1"])
    assert copy.read_bytes() == b"one\ntwo\n"


def test_the_directories_a_cli_logs_under_are_its_roots() -> None:
    assert roots(_claude()) == ("projects",)
