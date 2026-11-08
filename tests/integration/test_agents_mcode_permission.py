"""A flow's Permission reaching MiniMax Code: the rung it runs at and the fence that holds it.

MiniMax Code has no rung that changes nothing, so a READ grant on the workdir comes to
`bypass` -- `--permission full` -- and it is the fence alone that keeps the workdir from being
written. The fence itself is not put up here, only what MiniMax Code is told inside it.
"""

from __future__ import annotations

import dataclasses
import os
from typing import TYPE_CHECKING

from hmz.coganchor.agents import MiniMaxCodeAgent, MiniMaxCodeAgentConfig
from hmz.flows import HarnessKind, Permission, PermissionKind
from hmz.runtime.flowing.harnessing import fenced, rung
from tests.integration.doubles_agents import standins
from tests.integration.test_agents_mcode import CONFIG, MCODE

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from hmz.coganchor.fence import Fence


def _within(path: str, roots: tuple[str, ...]) -> bool:
    return any(
        path == root or path.startswith(root.rstrip(os.sep) + os.sep) for root in roots
    )


def test_a_read_grant_runs_mcode_at_full_inside_a_fence_that_keeps_the_workdir_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def enforceable(*, net: bool) -> bool:
        del net
        return True

    def wrapper(fence: Fence) -> list[str]:
        del fence
        return []

    monkeypatch.setattr("hmz.coganchor.fence.enforceable", enforceable)
    monkeypatch.setattr("hmz.coganchor.fence.wrapper", wrapper)
    mcode = standins(tmp_path, monkeypatch)
    mcode.install("mcode", MCODE)
    work = (tmp_path / "work").resolve()
    work.mkdir()
    permission = Permission(local=PermissionKind.READ)

    said = rung(HarnessKind.MCODE, permission, rungs=MiniMaxCodeAgent.rungs)
    fence = fenced(
        permission,
        workdir=str(work),
        home=str(tmp_path / "home"),
        profile=None,
        environ={},
    )
    config: MiniMaxCodeAgentConfig = dataclasses.replace(
        CONFIG, permission=said, fence=fence
    )
    agent = MiniMaxCodeAgent(config)
    try:
        assert agent.new(str(work))("hello") == "hello"
        held = agent.fenced()
    finally:
        agent.stop()

    assert said == "bypass"
    (call,) = mcode.calls("mcode")
    assert call.flag("--permission") == "full"
    assert held is not None
    assert _within(str(work), held.read)
    assert not _within(str(work), held.write)
