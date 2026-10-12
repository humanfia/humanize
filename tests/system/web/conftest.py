"""The page drawn in a real browser: slow, so never in CI, but on stand-ins as integration's are.

Run it by naming it, e.g. `uv run pytest tests/system/web/test_web_page.py`. Unlike the rest
of `tests/system`, no real agent runs here: every agent is hidden as the root's conftest hides
it, and nothing is fetched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import hide_agents

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _no_real_agents(_temporary: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Overrides `tests/system`'s: the agents here are stand-ins, as in `tests/integration`."""
    hide_agents(_temporary, monkeypatch)


@pytest.fixture(autouse=True)
def _asks_its_cli() -> None:
    """Overrides `tests/system`'s: a test that asks a backend asks for `asking` itself."""


@pytest.fixture(autouse=True)
def _priced() -> None:
    """Overrides `tests/system`'s: no price list is fetched."""
