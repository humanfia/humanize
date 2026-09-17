"""What the interface's integration tests keep when they leave the directory they were in.

The two fixtures below are autouse, and an autouse fixture reaches a test through the
conftest of the directory it is collected from. Moving a file out of `tests/tui/` without
bringing them would not fail: `_fetches_nothing` is the only thing stopping the flow menu
cloning humanize's own flowverse from GitHub as it opens, so a test that lost it would
still pass, and would pass by going to the network -- slowly on a machine that has one,
and not at all on a machine that does not. `_elsewhere` is the same shape of quiet: it
runs each test somewhere temporary with no backend installed, so a test that lost it would
read the developer's own PATH and pass here and nowhere else.

Imported rather than rewritten so that there is one copy of each, in `tests/tui/conftest.py`
where the interface's tests have always kept them.

The tests here name their shared helpers the same way -- `tests.tui.test_app`, from the root,
rather than `.test_app` as a sibling -- because that is where those helpers still are. A
sibling import would resolve inside this directory and find nothing, which is an import error
at collection rather than a test that fails; name them from the root again if the module
holding them moves.
"""

from __future__ import annotations

from tests.tui.conftest import _elsewhere, _fetches_nothing

__all__ = ["_elsewhere", "_fetches_nothing"]
