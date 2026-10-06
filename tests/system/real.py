"""What the system tests share besides fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from hmz.coganchor.backends import program

#: A tiny project whose tests fail until `median` and `mode` are written.
SAMPLE = Path(__file__).parent / "sample"


def needs(cli: str) -> str:
    """The path to `cli`, or skips the test where it is not installed."""
    found = program(cli)
    if found is None:
        pytest.skip(f"{cli} is not installed here")
    return found
