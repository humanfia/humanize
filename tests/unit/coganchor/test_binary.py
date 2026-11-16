"""Where `coganchor` is found, and the line that does what an internal command does."""

from __future__ import annotations

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
