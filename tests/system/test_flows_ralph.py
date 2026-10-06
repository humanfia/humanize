"""`ralph_loop`: a fresh session every round, on a real harness, until its budget is spent.

It has no exit of its own short of three empty rounds, so the run is stopped by its clock;
what is checked is what the rounds left in the repository.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.system.doubles_flows import assert_done, harness, ran, run

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.timeout(1200)
def test_ralph_loop_makes_the_tests_pass(workspace: Path) -> None:
    run(workspace, "ralph_loop", {"agent": harness()}, minutes=8)

    assert_done(workspace)
    record = ran(workspace)
    assert record.flow == "ralph_loop"
    assert record.how in {"done", "stopped"}
    assert record.sessions
