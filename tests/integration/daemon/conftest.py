"""The held-workspace fixtures, brought to where the tests that drive one now live.

They stay declared in `tests/daemon/fixtures.py`, which is not a test and so belongs under no
tier. Re-exported rather than copied because a daemon is one per workspace: two copies of
`held` would be two places to fix the day one of them stops letting go of the host it started,
and the test after it would find a host it never began.
"""

from __future__ import annotations

from tests.daemon.fixtures import held, older, workspace
from tests.machines.fixtures import standin

__all__ = ["held", "older", "standin", "workspace"]
