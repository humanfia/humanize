"""Every trust test: a machine of a fixed id, and files written plainly rather than atomically."""

from __future__ import annotations

import pytest

from hmz.trust import identity
from tests.unit.trust.doubles_trust import plain_writes


@pytest.fixture(autouse=True)
def _machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """No `ioreg` asked what this Mac is, and no `hmz.coganchor` written through."""
    monkeypatch.setattr(identity, "machine_id", lambda: "machine")
    plain_writes(monkeypatch)
