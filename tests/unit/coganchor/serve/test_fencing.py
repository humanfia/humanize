"""Running a command here inside the fence its turn was drawn with -- the fence itself mocked."""

from __future__ import annotations

import errno
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import fence
from hmz.coganchor.fence import abroad
from hmz.coganchor.serve import fencing
from hmz.coganchor.serve.exports import ExportTable

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path


@pytest.mark.parametrize(("fs", "cuts"), [(True, True), (True, False), (False, False)])
def test_the_handshake_says_what_can_be_fenced(
    fs: bool, cuts: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    def enforceable(*, net: bool) -> bool:
        return cuts if net else fs

    monkeypatch.setattr(fence, "enforceable", enforceable)
    assert fencing.able() == {"fs": fs, "net": cuts}


@dataclass
class Fake:
    """The fence and its drawing abroad, recording what they were asked."""

    able: bool = True
    drawn: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    looked_up: list[tuple[str, str | None]] = field(
        default_factory=list[tuple[str, str | None]]
    )
    readied: list[str] = field(default_factory=list[str])
    tmp: str = ""
    write: tuple[str, ...] = ()
    wrapped: list[fence.Fence] = field(default_factory=list[fence.Fence])


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Fake:
    held = Fake()

    def drawn(
        said: Mapping[str, Any],
        *,
        workdirs: Sequence[str],
        home: str,
        read: Sequence[str],
    ) -> fence.Fence:
        held.drawn.append(
            {"workdirs": list(workdirs), "home": home, "read": list(read)}
        )
        return fence.Fence(write=held.write, tmp=held.tmp)

    def installed(program: str, path: str | None = None) -> list[str]:
        held.looked_up.append((program, path))
        return [f"/install/{program}"]

    def enforceable(*, net: bool) -> bool:
        return held.able

    def wrapper(fenced: fence.Fence) -> list[str]:
        held.wrapped.append(fenced)
        return ["hmz", "internal", "fence", "--"]

    def ready(fenced: object, home: str) -> None:
        held.readied.append(home)

    monkeypatch.setattr(fence, "enforceable", enforceable)
    monkeypatch.setattr(fence, "wrapper", wrapper)
    monkeypatch.setattr(abroad, "drawn", drawn)
    monkeypatch.setattr(abroad, "installed", installed)
    monkeypatch.setattr(abroad, "ready", ready)
    return held


@pytest.fixture
def table(tmp_path: Path) -> ExportTable:
    return ExportTable.parse([f"/w:{tmp_path}"], insensitive=False)


@pytest.mark.parametrize("online", [True, False])
def test_a_machine_that_cannot_fence_refuses(
    fake: Fake, table: ExportTable, online: bool
) -> None:
    fake.able = False
    with pytest.raises(PermissionError) as raised:
        fencing.fenced({"online": online}, table, ["ls", "-l"], None, {})
    assert raised.value.errno == errno.EPERM
    assert raised.value.filename == "ls"
    said = str(raised.value)
    if sys.platform == "darwin":
        assert "Seatbelt" in said
    else:
        assert ("ABI 4" in said) is (not online)


def test_the_command_is_run_behind_the_fence_drawn_around_the_exports(
    fake: Fake, table: ExportTable, tmp_path: Path
) -> None:
    line = fencing.fenced({"online": True}, table, ["ls", "-l"], None, {"PATH": "/bin"})
    assert line == ["hmz", "internal", "fence", "--", "ls", "-l"]
    assert fake.drawn[0]["workdirs"] == [str(tmp_path)]
    assert fake.drawn[0]["read"] == []
    assert fake.readied == []


def test_a_program_this_machine_has_not_got_is_looked_up_by_name(
    fake: Fake, table: ExportTable, tmp_path: Path
) -> None:
    here = tmp_path / "tool"
    here.write_text("")
    assert fencing.fenced({}, table, ["t"], str(here), {})[-1] == str(here)
    assert fencing.fenced({}, table, ["t"], "/nowhere/bin/tool", {})[-1] == "tool"


def test_a_program_named_behind_env_is_the_one_read(
    fake: Fake, table: ExportTable
) -> None:
    argv = ["env", "-u", "KEY", "A=b", "claude", "-p"]
    fencing.fenced({"programs": True}, table, argv, None, {"PATH": "/usr/bin"})
    assert fake.looked_up == [("claude", "/usr/bin")]
    assert fake.drawn[0]["read"] == ["/install/claude"]


def test_a_writable_fence_has_its_home_readied(fake: Fake, table: ExportTable) -> None:
    fencing.fenced({"write": ["~/.cache"]}, table, ["ls"], None, {})
    assert len(fake.readied) == 1


def test_a_scratch_directory_is_made_where_it_is_named(
    fake: Fake, table: ExportTable, tmp_path: Path
) -> None:
    fake.tmp = str(tmp_path / "scratch")
    fencing.fenced({}, table, ["ls"], None, {})
    assert (tmp_path / "scratch").is_dir()


def test_a_scratch_reached_through_a_link_a_command_could_have_made_is_not_used(
    fake: Fake, table: ExportTable, tmp_path: Path
) -> None:
    written, elsewhere = tmp_path / "written", tmp_path / "elsewhere"
    written.mkdir()
    elsewhere.mkdir()
    (written / "scratch").symlink_to(elsewhere)
    fake.write, fake.tmp = (str(written),), str(written / "scratch")

    fencing.fenced({}, table, ["ls"], None, {})

    assert fake.wrapped[0].tmp == ""
    assert list(elsewhere.iterdir()) == []
