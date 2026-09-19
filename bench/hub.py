"""`hmz internal anchor`, with the mocked machines in place of a docker daemon.

Used in place of `python -m hmz` for the one arrangement whose harness runs on the hub: that
process derives its own road to the target, so the mock has to be inside it. Nothing below it
is touched -- the CLI it supervises is the real CLI, which matters, since anything imported
into that process would be imported one traced syscall at a time.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mocked import mock

mock()

from hmz.cli import main  # noqa: E402

raise SystemExit(main())
