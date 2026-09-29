"""ZCode held to a fence: what it enforces itself, and what is put around it from outside.

ZCode has no sandbox of its own, so the whole fence is the wrapper's -- with the install tree
its launcher runs added to read, which nothing found from the command alone leads to. What it
does natively is narrower and on top: an approval to write outside the fence is refused where
this client answers it. Read off objects in this process; nothing is spawned.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import dataclasses
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import ZcodeAgent, ZcodeAgentConfig
from hmz.coganchor.agents.zcode import _outside
from hmz.coganchor.fence import ALL, NONE, READ, Fence

if TYPE_CHECKING:
    from pathlib import Path


def _able(*, net: bool) -> bool:
    del net
    return True


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A machine that can fence a process, with a home and a ZCode install of the test's own."""
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    install = tmp_path / "opt" / "ZCode"
    install.mkdir(parents=True)
    monkeypatch.setattr("hmz.coganchor.agents.zcode._INSTALL", str(install))
    return install


def _fence(tmp_path: Path, *, online: bool = False) -> Fence:
    return dataclasses.replace(
        Fence.of(
            local=ALL,
            user=READ,
            system=NONE,
            online=online,
            workdir=tmp_path / "work",
            home=tmp_path / "home",
        ),
        tmp=str(tmp_path / "scratch"),
    )


def _agent(fence: Fence | None) -> ZcodeAgent:
    return ZcodeAgent(ZcodeAgentConfig(model="zai/glm-5.1", effort="high", fence=fence))


def test_zcode_enforces_none_of_its_fence_itself(tmp_path: Path) -> None:
    fence = _fence(tmp_path)
    assert _agent(fence).natively(fence) is fence


def test_a_fenced_server_is_spawned_inside_the_wrapper_with_its_install_to_read(
    installed: Path, tmp_path: Path
) -> None:
    argv = _agent(_fence(tmp_path)).spawned(["zcode", "app-server", "--stdio"])

    assert argv[:5] == [sys.executable, "-m", "hmz", "internal", "fence"]
    assert argv[-3:] == ["zcode", "app-server", "--stdio"]
    policy = Fence.loads(argv[5].removeprefix("--policy="))
    assert not policy.online
    assert "api.z.ai" in policy.hosts
    assert policy.allows(installed / "resources" / "glm" / "zcode.cjs")
    assert not policy.allows(installed / "zcode", write=True)
    assert policy.allows(tmp_path / "home" / ".zcode" / "cli" / "db", write=True)


def test_an_install_that_is_not_there_is_not_granted(
    installed: Path, tmp_path: Path
) -> None:
    installed.rmdir()
    fenced = _agent(_fence(tmp_path)).fenced()

    assert fenced is not None
    assert not fenced.allows(installed)


def test_an_agent_with_no_fence_is_given_none(installed: Path) -> None:
    assert _agent(None).fenced() is None


@pytest.mark.usefixtures("installed")
def test_an_approval_to_write_outside_the_fence_names_the_path(tmp_path: Path) -> None:
    agent = _agent(_fence(tmp_path))
    home = tmp_path / "home" / "probe"
    work = tmp_path / "work" / "ok.txt"

    def asked(tool: str, path: object) -> str:
        return _outside([agent], {"toolName": tool, "input": {"file_path": path}})

    assert asked("Write", str(home)) == str(home)
    assert asked("Edit", "/etc/hosts") == "/etc/hosts"
    assert asked("Write", str(work)) == ""
    # Only a write, only an absolute path, and only for a fenced agent.
    assert asked("Read", str(home)) == ""
    assert asked("Write", "relative.txt") == ""
    assert asked("Write", None) == ""
    assert (
        _outside(
            [_agent(None)], {"toolName": "Write", "input": {"file_path": str(home)}}
        )
        == ""
    )
    assert _outside([], {"toolName": "Write", "input": {"file_path": str(home)}}) == ""
