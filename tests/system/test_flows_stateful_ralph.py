"""`stateful_ralph`: one session re-sent the task every round, until its budget is spent.

It has no exit of its own short of three empty rounds, so the run is stopped by its clock;
what is checked is what the rounds left in the repository, all from one session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.system.doubles_flows import assert_done, harness, ran, run

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.timeout(1200)
def test_stateful_ralph_makes_the_tests_pass_in_one_session(workspace: Path) -> None:
    run(workspace, "stateful_ralph", {"agent": harness()}, minutes=8)

    assert_done(workspace)
    record = ran(workspace)
    assert record.flow == "stateful_ralph"
    assert record.how in {"done", "stopped"}
    assert len(record.sessions) == 1
