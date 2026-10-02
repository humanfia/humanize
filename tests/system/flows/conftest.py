"""The fixtures this directory's tests name, re-exported from where they are written.

The docker fixtures are `tests/machines/fixtures.py`'s, re-exported rather than copied, as
`tests/system/machines/conftest.py` does and for its reason: the skip a machine without docker
gets is worded once there. `ssh_host` is `tests.flows.sshd`'s, which the regression matrix in
`tests/system/matrix` takes back by name too: one sshd of the test's own, started one way, for
both suites that need a host a real `ssh` reaches. And `home_kept_here`, the matrix's, for
humanize's home where the default one is.
"""

from __future__ import annotations

from tests.flows.sshd import ssh_host
from tests.machines.fixtures import daemon, forwarded, ssh_runtime
from tests.matrix.fixtures import home_kept_here

__all__ = ["daemon", "forwarded", "home_kept_here", "ssh_host", "ssh_runtime"]
