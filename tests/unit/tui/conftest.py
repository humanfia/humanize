"""What the interface's unit tests keep when they leave the directory they were in.

What is here imports `hmz`, calls it and asserts: no subprocess, no socket, nothing off this
machine. That is the whole of the rule for this directory, and it is a rule about what a test
may reach rather than about what it is testing -- `test_discover` asks what backends and what
machines are installed, which sounds like the opposite, and answers it with `shutil.which`,
`subprocess.run` and `HOME` all pointed somewhere by the test itself.

The two fixtures below are what keeps that true as this directory grows. Both are autouse, and
an autouse fixture reaches a test through the conftest of the directory it is collected from,
so a file that moved out of `tests/tui/` without them would be running on different ground and
nothing would say so. `_elsewhere` runs each test somewhere temporary with no backend
installed, so a test that lost it reads the developer's own PATH and passes here and nowhere
else. `_fetches_nothing` takes the flow menu's first fetch away; nothing in this directory
opens one today, and it is here so that the first test which does cannot quietly make this the
tier that clones humanize's own flowverse from GitHub.

Imported rather than rewritten so that there is one copy of each, in `tests/tui/conftest.py`
where the interface's tests have always kept them. `__all__` is load-bearing: it is what says
these two names are re-exported rather than unused, and deleting it -- or the import -- takes
both fixtures off every test here without failing anything.
"""

from __future__ import annotations

from tests.tui.conftest import _elsewhere, _fetches_nothing

__all__ = ["_elsewhere", "_fetches_nothing"]
