"""Every trust test: a machine of a fixed id and host, and files written plainly."""

from __future__ import annotations

import socket

import pytest

from hmz.trust import identity
from tests.unit.trust.doubles_trust import plain_writes


@pytest.fixture(autouse=True)
def _machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """No `ioreg` asked what this Mac is, no real host name, no `hmz.coganchor` written."""
    monkeypatch.setattr(identity, "machine_id", lambda: "machine")
    monkeypatch.setattr(socket, "gethostname", lambda: "box.example.org")
    plain_writes(monkeypatch)
