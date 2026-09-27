"""The fixtures this directory's tests name, re-exported from where they are written.

`ssh_host` is `tests.flows.sshd`'s, which the regression matrix in `tests/system/matrix` takes
back by name too: one sshd of the test's own, started one way, for both suites that need a
host a real `ssh` reaches.
"""

from __future__ import annotations

from tests.flows.sshd import ssh_host

__all__ = ["ssh_host"]
