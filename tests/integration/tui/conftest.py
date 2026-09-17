"""Carries what every test of the interface needs into the tier these ones now sit in.

The fixtures themselves stay in `tests/tui/conftest.py`, beside the interface tests that
have not moved. A conftest reaches only the directory it is in, so without this file the
tests here would be run without them -- and two of the four are autouse, which is what
makes that loss silent rather than a failure. `_elsewhere` is what keeps a test out of the
developer's own checkout and off whatever coding agent is on their PATH; `_fetches_nothing`
is what stops each interface opened here cloning humanize's flowverse from GitHub, a fetch
`hmz.tui.app` swallows the failure of, so a suite that lost it would go to the network on
every test and still pass. Naming them here is what keeps them applying.

Which means the list is the whole of it: a fixture added over there and not added here
reaches the interface tests that stayed and not the ones that moved, and if it is autouse
that is a difference nothing reports. Anything added to `tests/tui/conftest.py` is added
here too.
"""

from __future__ import annotations

from tests.tui.conftest import _elsewhere, _fetches_nothing, catching_up, freshening

__all__ = ["_elsewhere", "_fetches_nothing", "catching_up", "freshening"]
