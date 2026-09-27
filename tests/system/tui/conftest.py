"""The same carrying-across, for the interface tests that drive a real runtime.

The autouse fixtures: somewhere temporary to run in with nothing installed (`_elsewhere`), no
git remote reached (`_fetches_nothing`), and an interface opened on a fake end of the runs
(`_linked_to_nothing`) -- which `hosting` gives back to the test that drives a real DeepSeek
runtime through runs held in its own process. Driving that runtime is what puts it here;
cloning a flowverse on the way is not part of that, and would be a fetch nobody asked for.
The interfaces `hmz` opens in a terminal of their own are other processes, which none of
these reach.

The fetching ones are left out because nothing here asks for them, and an unused re-export is
a name with nothing behind it. An autouse fixture added to
`tests/tui/fixtures.py` is added here as well: one that is not would apply to the interface
tests that stayed and silently not to this one.
"""

from __future__ import annotations

from tests.tui.fixtures import _elsewhere, _fetches_nothing, _linked_to_nothing, hosting

__all__ = ["_elsewhere", "_fetches_nothing", "_linked_to_nothing", "hosting"]
