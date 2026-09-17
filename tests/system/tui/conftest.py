"""The same carrying-across, for the interface test that drives a real runtime.

Only the two autouse fixtures: this tier holds one test, and what it needs is somewhere
temporary to run in with nothing installed (`_elsewhere`) and no git remote reached
(`_fetches_nothing`). Driving a real DeepSeek runtime is what puts it here; cloning a
flowverse on the way is not part of that, and would be a fetch nobody asked for.

The two non-autouse ones are left out because nothing here asks for them, and an unused
re-export is a name with nothing behind it. An autouse fixture added to
`tests/tui/fixtures.py` is added here as well: one that is not would apply to the interface
tests that stayed and silently not to this one.
"""

from __future__ import annotations

from tests.tui.fixtures import _elsewhere, _fetches_nothing

__all__ = ["_elsewhere", "_fetches_nothing"]
