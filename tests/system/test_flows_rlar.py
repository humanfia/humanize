"""`rlar`: an actor works and a fresh reviewer reads it, until the reviewer says it is done."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.system.doubles_flows import assert_done, harness, ran, run

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.timeout(1800)
def test_rlar_ends_when_the_reviewer_finds_the_tests_pass(workspace: Path) -> None:
    spec = harness()
    run(workspace, "rlar", {"actor": spec, "reviewer": spec})

    assert_done(workspace)
    record = ran(workspace)
    assert record.flow == "rlar"
    # The reviewer said done: a run its budget stopped would say so instead.
    assert record.how == "done"
    assert {one.agent for one in record.sessions} == {"actor", "reviewer"}
