"""Everything under here is a unit test, and is one by being here.

A unit test imports `hmz`, calls it and asserts. No subprocess, no socket, no network, nothing
written anywhere but `tmp_path`. It runs in milliseconds on any machine that can import the
package, which is what lets CI run this tree on every push, before anything slower -- and, once a
change is headed for `main`, on every Python and both systems the package claims.

The marker is put on from here rather than written on each file, so that moving a test into
this directory is all there is to filing it: see `tests/tiers.py` for why a tier is a directory,
and `tests/test_tiers.py` for the check that the two never disagree.
"""

from __future__ import annotations

import pytest

from hmz.coganchor.agents import KEEPING
from tests import tiers


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    tiers.applied("unit", items)


@pytest.fixture(autouse=True)
def _keeps_no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs every turn with its sessions where its CLI keeps them, as `HUMANIZE_SESSIONS=off`.

    A unit test asks what a turn would be spawned as and reads the answer; on a machine
    that can supervise one, every turn humanize keeps the sessions of is wrapped in the
    supervisor that keeps them, and an answer that differs by machine is not one to pin.
    The tests about keeping them take it back for themselves.
    """
    monkeypatch.setenv(KEEPING, "off")


@pytest.fixture(autouse=True)
def _asks_codex_nothing_of_its_features(monkeypatch: pytest.MonkeyPatch) -> None:
    """Takes Codex to know none of the features it is switched off by name only if it knows.

    Rather than asking whatever `codex` is on `PATH`: a unit test calls `hmz` and nothing else,
    and the answer is cached for the process besides.
    """
    monkeypatch.setattr("hmz.coganchor.agents.codex._offered", _knows_none)


def _knows_none(feature: str) -> bool:
    del feature
    return False
