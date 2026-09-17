"""What the interface's integration tests keep when they leave the directory they were in.

What is here drives a textual pilot -- the interface itself, running in a headless terminal
this repo asked for -- and talks to nothing that is not also this repo's. That is the rule for
this directory, and slowness is not part of it: a pilot waits on real time, so several of
these take tens of seconds, and none of them needs anything CI cannot be relied on to have.

The first two fixtures below are what makes that second half true, and both are autouse, which
means they reach a test through the conftest of the directory it is collected from. A file
that moved out of `tests/tui/` without them would not fail -- it would pass differently.
`_fetches_nothing` is the only thing stopping the flow menu cloning humanize's own flowverse
from GitHub as a test opens it: taking it off this directory and running the tier again is 116
tests passing and 138 clones of `github.com/humanfia/flowverse`, which is a suite that is slow
on a network and fails without one, and that says nothing either way. `_elsewhere` is the same
shape: it runs each test somewhere temporary with no backend installed, so a test that lost it
reads the developer's own PATH.

`catching_up` and `freshening` are the other half of that pair: they hand the fetch back to a
test that is about the fetching. Nothing here asks for either yet -- the tests that do are
still in `tests/tui/` -- and they are re-exported now so that those arrive to a directory that
has them rather than to four errors at collection.

Imported rather than rewritten so that there is one copy of each, in `tests/tui/conftest.py`
where the interface's tests have always kept them. `__all__` is load-bearing: it is what says
these names are re-exported rather than unused, and deleting it -- or the import -- takes both
autouse fixtures off every test here without failing anything.

The tests here name their shared helpers from the root -- `tests.tui.test_app` -- rather than
`.test_app` as a sibling, because that is where those helpers still are. A sibling import
would resolve inside this directory and find nothing, which is an import error at collection
rather than a test that fails; name them from the root again if the module holding them moves.
"""

from __future__ import annotations

from tests.tui.conftest import _elsewhere, _fetches_nothing, catching_up, freshening

__all__ = ["_elsewhere", "_fetches_nothing", "catching_up", "freshening"]
