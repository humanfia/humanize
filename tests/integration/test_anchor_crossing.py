"""A project whose configuration starts programs, opened by a CLI apart from it and beside it.

The target is a `local:` one standing in for another machine, served for real by a child of
this process: what the project holds is read over the protocol, out of the target's copy of
the workspace. No CLI is started -- a session starts its CLI at its first turn, and these are
refused, or not, as they open.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from hmz.coganchor import AnchorConfig, backends
from hmz.coganchor.machines import AnchoredConfig
from hmz.flows import (
    EnvBackendKind,
    HarnessKind,
    Permission,
    PermissionKind,
    UnsupportedOperation,
)
from hmz.runtime.flowing.harnesses import open_agent
from hmz.runtime.flowing.specs import AgentSpec
from hmz.runtime.flowing.spi import HookTable, Placement

#: Everything granted, so that nothing is fenced: a fence is another refusal than this one.
_ALL = Permission(
    local=PermissionKind.ALL, user=PermissionKind.ALL, system=PermissionKind.ALL
)


class _Here:
    """A run whose harness, on any machine, stays where the machine put it."""

    def setting(self, placement: Placement) -> str:
        del placement
        return "local"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace, its far copy beside it, and claude taken to be installed here."""

    def program(command: str) -> str:
        return f"/usr/bin/{command}"

    monkeypatch.setattr(backends, "program", program)
    for side in ("workspace", "real"):
        (tmp_path / side).mkdir()
    return tmp_path


def _spec() -> AgentSpec:
    return AgentSpec("coder", HarnessKind.CLAUDE, "", "", "", "claude")


async def _open(placement: Placement) -> Any:
    harbors: Any = _Here()
    driver = open_agent(_spec(), harbors)
    try:
        return await driver.open(
            placement, permission=_ALL, skills=(), hooks=HookTable()
        )
    finally:
        await driver.close()


def _supervised(project: Path) -> Placement:
    anchor = AnchorConfig(
        target=f"local:{project / 'real'}", workspace=str(project / "workspace")
    )
    return Placement(
        EnvBackendKind.SSH,
        "box",
        PurePosixPath(project / "workspace"),
        machine=AnchoredConfig(anchor=anchor),
    )


@pytest.mark.parametrize(
    ("path", "content", "named"),
    [
        (
            ".claude/settings.json",
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}},
            ".claude/settings.json: hooks",
        ),
        (
            ".mcp.json",
            {"mcpServers": {"db": {"command": "db-mcp", "args": []}}},
            ".mcp.json: mcpServers.*.command",
        ),
    ],
    ids=["hooks", "stdio-mcp"],
)
async def test_a_supervised_cli_is_refused_a_project_that_would_start_programs_here(
    project: Path, path: str, content: dict[str, Any], named: str
) -> None:
    written = project / "real" / path
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(json.dumps(content))

    with pytest.raises(
        UnsupportedOperation, match="would have it start programs"
    ) as no:
        await _open(_supervised(project))

    assert named in str(no.value)


async def test_a_supervised_cli_opens_on_a_project_that_starts_nothing(
    project: Path,
) -> None:
    (project / "real" / ".claude").mkdir()
    (project / "real" / ".claude" / "settings.json").write_text('{"model": "opus"}')
    (project / "real" / ".mcp.json").write_text(
        '{"mcpServers": {"web": {"type": "http", "url": "https://example.com"}}}'
    )

    session = await _open(_supervised(project))

    assert session.id is None, "opened, its CLI started by nothing yet"


async def test_the_same_project_here_opens(project: Path) -> None:
    here = project / "workspace"
    (here / ".claude").mkdir()
    (here / ".claude" / "settings.json").write_text('{"hooks": {"Stop": [1]}}')

    session = await _open(Placement(EnvBackendKind.LOCAL, "", PurePosixPath(here)))

    assert session.id is None
