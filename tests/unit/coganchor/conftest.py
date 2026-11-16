"""What every unit test of the anchor starts from."""

from __future__ import annotations

import pytest

from hmz.coganchor import binary


@pytest.fixture(autouse=True)
def _python_halves(monkeypatch: pytest.MonkeyPatch) -> None:
    """The anchor launched as the Python halves, whatever `HUMANIZE_COGANCHOR` says outside.

    The variable is how the Rust port is run against the integration suites; a unit test says
    for itself which of the two it is about.
    """
    monkeypatch.delenv(binary.VARIABLE, raising=False)
