"""Everything under here is an integration test, and is one by being here.

An integration test drives more than one part at once, but everything it talks to is a fake
this repo wrote: a stand-in CLI written onto PATH, a fake app server, a fake websocket, a
loopback HTTP or unix socket, `ShellAgent`, the interface driven by a Textual pilot. It is
deterministic and offline, so CI runs it -- a loopback socket needs nothing a runner lacks, and
a test that needs a real coding agent, a real docker or a real ptrace belongs in `tests/system`
instead.

The marker is put on from here rather than written on each file, so that moving a test into
this directory is all there is to filing it: see `tests/tiers.py` for why a tier is a directory,
and `tests/test_tiers.py` for the check that the two never disagree.
"""

from __future__ import annotations

import pytest

from hmz.coganchor.agents import KEEPING
from tests import fencing, tiers


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    tiers.applied("integration", items)


@pytest.fixture(autouse=True)
def _keeps_no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs every turn with its sessions where its CLI keeps them, as `HUMANIZE_SESSIONS=off`.

    Keeping a session is answering a CLI's paths from a ptrace supervisor, and this tier
    must not need a kernel that will hand one a tracee: a stand-in run under one here would
    be a system test that CI runs. So every stand-in keeps its sessions where it always
    has, and `tests/system` is where they are kept in the run.
    """
    monkeypatch.setenv(KEEPING, "off")


@pytest.fixture(autouse=True)
def _fences_with_a_stand_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spawns every fenced turn under a stand-in for `hmz internal fence`, on any machine.

    For the reason sessions are kept nowhere: a fence is Landlock and seccomp, which this
    tier must not need -- a stand-in CLI walled in by a real kernel here would be a system
    test that CI runs. The stand-in writes down what the turn would have been held to and
    runs it unfenced; `tests/system/coganchor/test_fence.py` is where the wall goes up.
    """
    fencing.standing_in(monkeypatch)


@pytest.fixture(autouse=True)
def _asks_codex_nothing_of_its_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Takes bubblewrap to start, rather than asking whatever `codex` is on `PATH`.

    The answer is cached for the process, so a probe that ran here would pin every later
    test's command line to this machine's kernel and to whichever test asked first.
    """
    monkeypatch.setattr("hmz.coganchor.agents.codex._landlocked", lambda: False)
    # And knows none of the features it is switched off by name only where it knows them.
    monkeypatch.setattr("hmz.coganchor.agents.codex._offered", _knows_none)


def _knows_none(feature: str) -> bool:
    del feature
    return False
