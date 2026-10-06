"""`goal`: the task set once as the harness's own `/goal`, pursued until it says it is met."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.system.doubles_flows import assert_done, harness, ran, run

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.timeout(1800)
def test_goal_is_pursued_until_the_tests_pass(workspace: Path) -> None:
    run(workspace, "goal", {"worker": harness()})

    assert_done(workspace)
    record = ran(workspace)
    assert record.flow == "goal"
    assert record.how == "done"
    (session,) = record.sessions
    assert session.agent == "worker"
