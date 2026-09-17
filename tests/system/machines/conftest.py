"""The docker fixture, brought to where the tests that need a container now live.

It stays declared in `tests/machines/conftest.py`, next to the name of the image it looks for,
because that name is also imported by the tests themselves. Re-exported rather than copied so
that the skip a machine without docker gets is worded once: a second copy that drifted would
be a container test reporting failure on a laptop that simply has no daemon running.
"""

from __future__ import annotations

from tests.machines.conftest import daemon

__all__ = ["daemon"]
