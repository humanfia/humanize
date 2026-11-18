"""The loops the integration tests run: stand-ins for the ones the official index lists.

Humanize keeps no flow in the package, so a home nothing was installed into has no flow to
run. The loops in `flows/` beside this file are written by this repository in the shape of
the ones `official` lists, and `loops` puts them where an install out of that index would,
so `-f goal` names one in a test as it does on a machine that installed it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

#: The stand-in loops, one directory apiece.
FLOWS = Path(__file__).parent / "flows"


@pytest.fixture
def loops(_humanize_home: None) -> None:
    """Puts the stand-in loops where the flows installed out of `official` are kept."""
    from hmz.runtime.flowing.index import kept
    from hmz.runtime.flowing.verses import OFFICIAL

    shutil.copytree(FLOWS, kept(OFFICIAL), ignore=shutil.ignore_patterns("__pycache__"))
