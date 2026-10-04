"""Which humanize this is: written once, in `pyproject.toml`, and read everywhere else."""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from hmz import coganchor

if TYPE_CHECKING:
    import pytest

PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"


def test_the_version_an_agent_is_told_is_the_one_released() -> None:
    """A release is tagged with what `pyproject.toml` says, and published from it.

    An anchored agent is told `coganchor.__version__` as `HUMANIZE`, and `hmz --version` reads
    the installed package's: all three have to be one number, or one of them names a release
    that was never cut.
    """
    said = tomllib.loads(PYPROJECT.read_text())["project"]["version"]

    assert coganchor.__version__ == importlib.metadata.version("hmz") == said


def test_a_source_tree_nobody_installed_still_has_a_version_to_say(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no metadata to read, the version is said to be unknown rather than raised.

    An attribute a module offers answers `getattr` and `hasattr` like any other, and a turn
    started from a bare checkout is not refused for want of a number.
    """

    def uninstalled(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.delattr(coganchor, "__version__", raising=False)
    monkeypatch.setattr(importlib.metadata, "version", uninstalled)

    assert coganchor.__version__ == "unknown"
