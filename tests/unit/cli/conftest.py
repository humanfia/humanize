"""What every test of the command line starts from: nothing said about colour.

Help is drawn bold where `FORCE_COLOR` says so, and a workflow sets it for every step; a test
that reads help reads it plain unless it says otherwise itself.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def colourless(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("FORCE_COLOR", "NO_COLOR"):
        monkeypatch.delenv(name, raising=False)
