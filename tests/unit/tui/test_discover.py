from __future__ import annotations

import importlib.machinery
import importlib.util
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.coganchor import backends
from hmz.tui import discover

if TYPE_CHECKING:
    import pytest


def test_dsh_is_installed_when_its_python_sdk_is_importable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_executable(_name: str) -> None:
        return None

    def found_module(name: str) -> importlib.machinery.ModuleSpec | None:
        return (
            importlib.machinery.ModuleSpec(name, loader=None)
            if name in ("deepseek_harness", "dotenv")
            else None
        )

    monkeypatch.setattr(shutil, "which", missing_executable)
    # And nothing where an installer would have left one either: what is installed here is
    # what this test says it is, rather than what the developer's own machine has.
    monkeypatch.setattr(backends, "_INSTALLED_AT", ())
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        found_module,
    )

    found = discover.installed()

    assert list(found) == ["dsh"]
    assert [model.name for model in found["dsh"]] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]
    assert discover.installable() == {}


def test_a_missing_dsh_sdk_is_installable_but_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_executable(_name: str) -> None:
        return None

    def missing_module(_name: str) -> None:
        return None

    monkeypatch.setattr(shutil, "which", missing_executable)
    monkeypatch.setattr(backends, "_INSTALLED_AT", ())
    monkeypatch.setattr(importlib.util, "find_spec", missing_module)

    assert discover.installed() == {}
    assert [model.name for model in discover.installable()["dsh"]] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]
    # And nothing else: kimi is behind an extra too, but its CLI is not here either, so what
    # it is missing is not a package and a line naming one would be half an answer.
    assert list(discover.installable()) == ["dsh"]


def test_kimi_without_its_websocket_client_is_installable_rather_than_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI is here and the package it is driven over is not, which is a line to run."""

    def only_kimi(name: str) -> str | None:
        return "/usr/bin/kimi" if name == "kimi" else None

    def missing_module(_name: str) -> None:
        return None

    monkeypatch.setattr(shutil, "which", only_kimi)
    monkeypatch.setattr(backends, "_INSTALLED_AT", ())
    monkeypatch.setattr(importlib.util, "find_spec", missing_module)

    assert discover.installed() == {}
    assert "kimi" in discover.installable()


def test_a_backend_somebody_added_is_installed_if_the_command_they_gave_is_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One humanize drives is started by its own name; one somebody added, by their command."""

    def added() -> dict[str, tuple[str, ...]]:
        return {"theirs": ("a-cli-of-theirs",)}

    def looked_up(said: str) -> str | None:
        return "/usr/bin/it" if said == "a-cli-of-theirs" else None

    monkeypatch.setattr(backends, "_INSTALLED_AT", ())
    monkeypatch.setattr(discover, "speaking", added)
    monkeypatch.setattr(discover, "program", looked_up)

    assert discover._is_installed("theirs")


def test_a_backend_somebody_added_with_no_command_at_all_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def added() -> dict[str, tuple[str, ...]]:
        return {"theirs": ()}

    monkeypatch.setattr(discover, "speaking", added)

    assert not discover._is_installed("theirs")


def test_an_ordinary_cli_may_be_chosen_without_anybody_choosing_it() -> None:
    """A CLI on PATH is there because somebody installed it, which is the choosing."""
    assert discover.ready_to_open("claude", Path("/somewhere"))


def test_the_backend_that_arrives_with_humanize_is_asked_whether_it_is_set_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Its SDK arrives whatever happens, so being installed says nothing about being usable."""
    from hmz.coganchor.agents import dsh

    def set_up(where: Path) -> bool:
        return where == tmp_path

    monkeypatch.setattr(dsh, "native_ready", set_up)

    assert discover.ready_to_open("dsh", tmp_path)
    assert not discover.ready_to_open("dsh", tmp_path / "elsewhere")
