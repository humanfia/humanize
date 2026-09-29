"""Qwen Code held to a fence: what its driver leaves to the wrapper, and what it adds to it.

Qwen Code enforces none of a fence itself -- its permission rules hold its own tools and not
what its commands go on to do, and its sandbox is a container -- so the whole fence is put
around it from outside. What the driver adds is the one grant the wrapper cannot know of:
the settings files it wrote for the CLI to read.
"""

from __future__ import annotations

import dataclasses
import sys
from typing import TYPE_CHECKING

from hmz.coganchor.agents import QwenCodeAgent, QwenCodeAgentConfig
from hmz.coganchor.agents import qwen as backend
from hmz.coganchor.fence import ALL, NONE, READ, Fence

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _able(*, net: bool) -> bool:
    del net
    return True


def _fence(tmp_path: Path, *, system: str = READ, online: bool = True) -> Fence:
    return Fence.of(
        local=ALL,
        user=READ,
        system=system,
        online=online,
        workdir=tmp_path / "work",
        home=tmp_path / "home",
    )


def _agent(fence: Fence | None) -> QwenCodeAgent:
    return QwenCodeAgent(QwenCodeAgentConfig(model="m", effort="low", fence=fence))


def test_qwen_enforces_none_of_its_fence_and_is_let_read_its_settings(
    tmp_path: Path,
) -> None:
    fence = _fence(tmp_path, system=NONE, online=False)

    rest = _agent(fence).natively(fence)

    assert rest.allows(backend._root())
    assert not rest.allows(backend._root(), write=True)
    assert dataclasses.replace(rest, read=fence.read) == fence


def test_a_fence_that_grants_everything_is_left_as_it_is(tmp_path: Path) -> None:
    fence = Fence.of(
        local=ALL,
        user=ALL,
        system=ALL,
        online=True,
        workdir=tmp_path / "work",
        home=tmp_path / "home",
    )

    assert _agent(fence).natively(fence) == fence


def test_a_fenced_turn_is_spawned_inside_the_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    argv = _agent(_fence(tmp_path, system=NONE, online=False)).spawned(["qwen"])

    assert argv[:7] == [sys.executable, "-m", "hmz", "internal", "fence", argv[5], "--"]
    policy = Fence.loads(argv[5].removeprefix("--policy="))
    assert not policy.online
    assert policy.allows(backend._root())
    assert argv[-1] == "qwen"


def test_every_settings_file_is_kept_where_the_fence_lets_it_be_read() -> None:
    assert backend._thinking("low").is_relative_to(backend._root())
