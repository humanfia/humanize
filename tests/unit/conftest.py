"""Everything under here is a unit test, and is one by being here.

A unit test imports `hmz`, calls it and asserts. No subprocess, no socket, no network, nothing
written anywhere but `tmp_path`. It runs in milliseconds on any machine that can import the
package, which is what lets CI run this tree on every Python and both systems it claims.

The marker is put on from here rather than written on each file, so that moving a test into
this directory is all there is to filing it: see `tests/tiers.py` for why a tier is a directory,
and `tests/test_tiers.py` for the check that the two never disagree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests import tiers

if TYPE_CHECKING:
    import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    tiers.applied("unit", items)
