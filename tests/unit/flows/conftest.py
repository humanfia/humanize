"""The runtime `hmz.flows` hands its calls to, stood in for by a mock in every test here."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.unit.flows import doubles_flows as doubles

if TYPE_CHECKING:
    from unittest import mock


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`hmz.runtime.flowing.engine`, as a mock whose `define_flow` answers a `Defined`."""
    return doubles.engine(monkeypatch)
