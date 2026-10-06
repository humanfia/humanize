"""The tracing bindings load a Linux register map as they are imported, and refuse any other host.

So their tests are collected on Linux alone. `landlock` is importable anywhere, and says that
it is not available off Linux; its tests, and those of the refusal itself, run everywhere.
"""

from __future__ import annotations

import sys

collect_ignore = (
    []
    if sys.platform == "linux"
    else ["test_procfs.py", "test_ptrace.py", "test_seccomp.py", "test_syscalls.py"]
)
