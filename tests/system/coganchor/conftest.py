"""The fixtures an anchored system test runs on, brought into this directory.

A fixture is visible to the tests under the conftest that declares it and nowhere else, so
moving these tests out of `tests/coganchor/` left them with no `anchorage` at all -- which
pytest reports as an error per test rather than as a missing import. The definitions stay
where they are, beside the serving half they were written for and beside the tests of the
other tiers that share them; this names the ones the anchored tier needs.
"""

from __future__ import annotations

from tests.coganchor.fixtures import anchorage, echo_server

__all__ = ["anchorage", "echo_server"]
