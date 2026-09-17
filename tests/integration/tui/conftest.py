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
test that is about the fetching.

Imported rather than rewritten so that there is one copy of each, in `tests/tui/fixtures.py`
where the interface's tests have always kept them. `__all__` is load-bearing: it is what says
these names are re-exported rather than unused, and deleting it -- or the import -- takes both
autouse fixtures off every test here without failing anything. Which also means this list is
the whole of it: a fixture added over there and not added here reaches the interface tests
that stayed and not the ones that moved, and if it is autouse that is a difference nothing
reports. Anything added to `tests/tui/fixtures.py` is added here too.

The tests here name their shared helpers by their whole path -- `tests.integration.tui.test_app`
-- rather than `.test_app` as a sibling. Both resolve today, now that `test_app.py` is in this
directory too, but only the first keeps resolving if either module moves again, and a sibling
import that stops resolving is an error at collection rather than a test that fails.

Two of those helpers are not `test_app`'s, though several files here once kept a copy as if they
were: `until` pumps the pilot until something is true, and `transcript` reads back everything the
interface has shown. Both live in `tests/tui/fixtures.py` beside the fixtures above, because the
system tier's one interface test wants them as much as this tier does and a file in `tests/tui`
is the only place both can reach. `test_app` is for what only this tier has -- `rows`, `onto`,
`into_agent` and the rest, which are about sheets no system test opens.
"""

from __future__ import annotations

from tests.tui.fixtures import _elsewhere, _fetches_nothing, catching_up, freshening

__all__ = ["_elsewhere", "_fetches_nothing", "catching_up", "freshening"]
