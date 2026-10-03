"""Everything under here is a system test, and is one by being here.

A system test needs the real thing: a coding-agent CLI installed on this machine and driven `as
local`, real ptrace and seccomp, real docker, real ssh, a real daemon fork, a real `node`. CI
runs this tree once, on Linux, before a change reaches `main`, with docker, a swarm and `ssh
localhost` set up for it and no coding agent installed. What a machine has not got is a skip
that says so rather than a failure, there and anywhere else: a gate that goes red for what the
machine is missing is a gate people learn to ignore.

`agent` is a second gate inside this tree rather than a tier of its own: a system test that
spends real tokens is skipped until somebody asks for it with `--run-agents`, while one that
only needs a real `node` runs here as soon as a developer does. That option and the marker it
keys on live in `tests/conftest.py`, because `pytest_addoption` is honoured only in a root
conftest.

The marker is put on from here rather than written on each file, so that moving a test into
this directory is all there is to filing it: see `tests/tiers.py` for why a tier is a directory,
and `tests/test_tiers.py` for the check that the two never disagree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests import tiers

if TYPE_CHECKING:
    import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    tiers.applied("system", items)
