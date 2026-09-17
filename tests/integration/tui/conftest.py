"""What the interface's integration tests keep when they leave the directory they were in.

What is here drives a textual pilot -- the interface itself, running in a headless terminal
this repo asked for -- and talks to nothing that is not also this repo's. That is the rule for
this directory, and slowness is not part of it: a pilot waits on real time, so several of
these take tens of seconds, and none of them needs anything CI cannot be relied on to have.

The two fixtures below are what makes that second half true, and both are autouse, which means
they reach a test through the conftest of the directory it is collected from. A file that
moved out of `tests/tui/` without them would not fail -- it would pass differently.
`_fetches_nothing` is the only thing stopping the flow menu cloning humanize's own flowverse
from GitHub as a test opens it, so a test that lost it still passes, by going to the network:
slowly on a machine that has one, and not at all on a machine that does not. `_elsewhere` is
the same shape of quiet: it runs each test somewhere temporary with no backend installed, so a
test that lost it reads the developer's own PATH and passes here and nowhere else.

Imported rather than rewritten so that there is one copy of each, in `tests/tui/conftest.py`
where the interface's tests have always kept them. `__all__` is load-bearing: it is what says
these two names are re-exported rather than unused, and deleting it -- or the import -- takes
both fixtures off every test here without failing anything.

Two more live beside them there and have not been brought over, because nothing here asks for
them: `catching_up` and `freshening`, which hand back the fetch the pair above took away. They
are for tests that are about the fetching, and the file holding those has not moved yet; bring
them the same way when it does, or those tests arrive here with no such fixture.

The tests here name their shared helpers from the root -- `tests.tui.test_app` -- rather than
`.test_app` as a sibling, because that is where those helpers still are. A sibling import
would resolve inside this directory and find nothing, which is an import error at collection
rather than a test that fails; name them from the root again if the module holding them moves.
"""

from __future__ import annotations

from tests.tui.conftest import _elsewhere, _fetches_nothing

__all__ = ["_elsewhere", "_fetches_nothing"]
