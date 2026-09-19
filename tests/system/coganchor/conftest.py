"""The fixtures an anchored system test runs on, brought into this directory.

A fixture is visible to the tests under the conftest that declares it and nowhere else, so
moving these tests out of `tests/coganchor/` left them with no `anchorage` at all -- which
pytest reports as an error per test rather than as a missing import. The definitions stay
where they are, beside the serving half they were written for and beside the tests of the
other tiers that share them; this names the ones the anchored tier needs.

`daemon` comes from the other direction and for the same reason: the containers the topology
tests put a harness and its work into need a docker daemon holding the image, which is the
skip `tests/machines/fixtures.py` words once for every test in this repository that wants one.
"""

from __future__ import annotations

from tests.coganchor.fixtures import anchorage, echo_server
from tests.machines.fixtures import daemon

__all__ = ["anchorage", "daemon", "echo_server"]
