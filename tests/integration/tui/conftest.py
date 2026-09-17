"""What a test of the interface needs from `tests/tui`, taken back by name.

A fixture is inherited down a directory tree, so a test that moved out of `tests/tui` left
`tests/tui/conftest.py` behind it -- and the two autouse fixtures there are what keep the
interface honest in a suite: one runs it in a temporary directory with no backend installed, so
that a test passes or fails the same on a machine with a coding agent on its PATH and one
without; the other stops the flow menu and the interface fetching from a git remote as they
open, which is what makes the tui tests offline at all. Without the import below they would be
a suite that clones humanize's flowverse once per test.

Imported rather than copied: the definition stays in `tests/tui/conftest.py`, where the tests
that have not moved yet still read it, and this directory borrows it. The other two are here
for a test that is about the fetching itself: each gives back what the autouse pair took away,
and a fixture nothing under here asks for yet costs a line rather than a failure that says only
"fixture not found".

`__all__` rather than a `# noqa`, because the two gates disagree about what a re-export looks
like: an unused import is an error to pyright, the `import x as x` spelling that would answer
that is an error to ruff, and a name in `__all__` is deliberate to both.
"""

from __future__ import annotations

from tests.tui.conftest import (
    _elsewhere,
    _fetches_nothing,
    catching_up,
    freshening,
)

__all__ = ["_elsewhere", "_fetches_nothing", "catching_up", "freshening"]
