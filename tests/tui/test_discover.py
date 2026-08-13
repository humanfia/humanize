from __future__ import annotations

import importlib.machinery
import importlib.util
import shutil
from typing import TYPE_CHECKING

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
            if name == "deepseek_harness"
            else None
        )

    monkeypatch.setattr(shutil, "which", missing_executable)
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        found_module,
    )

    assert discover.installed() == {"dsh": ()}
