"""Where `coganchor` is found, and the line that does what an internal command does."""

from __future__ import annotations

import hashlib
import os
import platform
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import binary

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("system", "machine", "where"),
    [
        ("Linux", "x86_64", "linux-x86_64"),
        ("linux", "aarch64", "linux-aarch64"),
        ("Darwin", "arm64", "darwin-aarch64"),
        ("Darwin", "x86_64", "darwin-x86_64"),
        ("Linux", "AMD64", "linux-x86_64"),
        ("Linux", "riscv64", None),
        ("FreeBSD", "amd64", None),
    ],
)
def test_names_the_build_for_a_machine(
    system: str, machine: str, where: str | None
) -> None:
    assert binary.named(system, machine) == where


def test_the_variable_chooses_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = tmp_path / "coganchor"
    program.write_text("")
    monkeypatch.setenv(binary.VARIABLE, str(program))
    assert binary.chosen() == program
    assert binary.found() == program


def test_the_variable_naming_nothing_chooses_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(binary.VARIABLE, str(tmp_path / "absent"))
    assert binary.chosen() is None
    monkeypatch.setenv(binary.VARIABLE, "  ")
    assert binary.chosen() is None
    monkeypatch.delenv(binary.VARIABLE)
    assert binary.chosen() is None


@pytest.mark.parametrize(
    ("command", "argv", "line"),
    [
        ("anchor", ["--target=local", "claude"], ["cog", "--target=local", "claude"]),
        ("anchor", ["serve", "--stdio"], ["anchor", "--stdio"]),
        ("anchor", ["rendezvous", "--listen", "0"], ["broker", "--listen", "0"]),
        (
            "fence",
            ["--policy={}", "--", "ls"],
            ["internal", "fence", "--policy={}", "--", "ls"],
        ),
        (
            "cred",
            ["--map", "a=b", "--", "ls"],
            ["internal", "cred", "--map", "a=b", "--", "ls"],
        ),
    ],
)
def test_translates_internal_commands(
    command: str, argv: list[str], line: list[str]
) -> None:
    assert binary.translated(command, argv) == line


def test_refuses_a_command_it_does_not_run() -> None:
    with pytest.raises(ValueError, match="hook"):
        binary.translated("hook", [])


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A build the variable names, on a machine that is Linux on x86-64."""
    program = tmp_path / "coganchor"
    program.write_bytes(b"\x7fELF built")
    monkeypatch.setenv(binary.VARIABLE, str(program))
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    # Set, so that what `here` sets is taken off again after.
    monkeypatch.setenv(binary.BINARIES, "")
    monkeypatch.delenv(binary.BINARIES)
    return program


def test_it_is_active_while_the_variable_names_a_build(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert binary.active()
    monkeypatch.delenv(binary.VARIABLE)
    assert not binary.active()


def test_here_is_the_build_and_tells_its_children_where_the_others_are(
    built: Path,
) -> None:
    assert binary.here() == built
    assert os.environ[binary.BINARIES] == str(binary.shelf())
    assert binary.shelf().name == "bin"


def test_here_leaves_a_shelf_somebody_named(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(binary.BINARIES, "/elsewhere")
    binary.here()
    assert os.environ[binary.BINARIES] == "/elsewhere"


def test_here_without_a_build_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(binary, "found", lambda: None)
    with pytest.raises(FileNotFoundError, match="no coganchor is built"):
        binary.here()


def test_a_machine_like_this_one_is_shipped_this_ones_build(
    built: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    other = tmp_path / "linux-aarch64"

    def packaged(system: str, machine: str) -> Path | None:
        return other if binary.named(system, machine) else None

    monkeypatch.setattr(binary, "packaged", packaged)
    assert binary.shipped("Linux", "amd64") == built
    assert binary.shipped("Linux", "arm64") == other
    assert binary.shipped("Linux", "riscv64") is None


def test_a_build_is_named_by_the_start_of_its_sha256(built: Path) -> None:
    assert binary.digest(built) == hashlib.sha256(b"\x7fELF built").hexdigest()[:16]
    built.write_bytes(b"rebuilt, and longer")
    assert (
        binary.digest(built) == hashlib.sha256(b"rebuilt, and longer").hexdigest()[:16]
    )
