"""The held-run fixtures, brought to where the tests that drive one now live.

They stay declared in `tests/daemon/conftest.py`, beside `runs.py` and `terminals.py` -- what
a daemon is handed to hold, and the process that reads one back. None of those three is a
test, so none of them belongs under a tier. Re-exported rather than copied because a daemon is
one per workspace: two copies of `held` would be two places to fix the day one of them stops
letting go of the run it started, and the test after it would find a run it never began.
"""

from __future__ import annotations

from tests.daemon.conftest import held, workspace

__all__ = ["held", "workspace"]
