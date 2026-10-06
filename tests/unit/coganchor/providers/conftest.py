"""Every CLI's own home under the test's temp directory, so credential paths are known."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home of the test's own, with no CLI moved anywhere by a variable."""
    home = tmp_path / "user"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    for moved in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(moved, raising=False)
    return home
