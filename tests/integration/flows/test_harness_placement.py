"""Asking an environment's machine whether it has a CLI, down the road a native turn takes.

A `local:` target stands in for the machine: the question is humanize's own `hmz internal
anchor` driving the target's shell natively, exactly as a turn there would be driven, and what
is checked is that a CLI that is there is found and one that is not is said to be missing.
"""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import AnchoredConfig
from hmz.flows import EnvBackendKind, HarnessKind, HarnessNotInstalled
from hmz.runtime.flowing.harnesses import HarnessDriver, open_agent
from hmz.runtime.flowing.specs import AgentSpec
from hmz.runtime.flowing.spi import Placement

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.flows import HarnessError


def _asked(
    tmp_path: Path, program: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[type[HarnessError], str] | None:
    """What asking a stand-in machine about `program` answers."""
    anchor = AnchorConfig(target=f"local:{tmp_path}", workspace=str(tmp_path))
    placement = Placement(
        EnvBackendKind.SSH,
        "stand-in",
        PurePosixPath(tmp_path),
        AnchoredConfig(anchor=anchor),
    )
    driver = open_agent(
        AgentSpec("coder", HarnessKind.CLAUDE, "", "m", "", "claude"), "env"
    )

    def named(self: HarnessDriver) -> str:
        del self
        return program

    monkeypatch.setattr(HarnessDriver, "_program", named)
    return asyncio.run(driver._native_on(anchor, None, placement))


@pytest.mark.timeout(120)
def test_a_cli_the_machine_has_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _asked(tmp_path, "sh", monkeypatch) is None


@pytest.mark.timeout(120)
def test_a_cli_the_machine_has_not_is_missing_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    said = _asked(tmp_path, "/opt/nowhere/no-such-cli", monkeypatch)
    assert said is not None
    kind, why = said
    assert kind is HarnessNotInstalled
    assert "is not installed on ssh@stand-in" in why
    assert "-H local" in why
