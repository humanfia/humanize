"""The loopback supervisor answers seccomp notifications, which only Linux has."""

from __future__ import annotations

import sys

collect_ignore = [] if sys.platform == "linux" else ["test_loopback.py"]
