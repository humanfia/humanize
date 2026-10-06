"""What the tests of `hmz.runtime.doing` share: a stand-in for any function they hand on to."""

from __future__ import annotations

import pytest

from tests.unit.runtime.doubles_u12 import Stands


@pytest.fixture
def stand(monkeypatch: pytest.MonkeyPatch) -> Stands:
    return Stands(monkeypatch)
