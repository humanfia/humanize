"""Antigravity held to a fence that cuts the network, against the real binary and kernel.

agy's page fetcher runs at the far end of its model API, which is a host every fence lets it
reach, so the cut network alone does not stop it: what does is the agent a fenced turn is
started as, which lacks the tool. Only the real CLI can say whether that agent is found and
whether its model still has the tool, and only the real kernel whether the rest of the turn
-- its loopback language server, its sign-in, its commands in the workdir -- still runs.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hmz.coganchor.agents import (
    AntigravityCLIAgent,
    AntigravityCLIAgentConfig,
    Failed,
)
from hmz.coganchor.fence import ALL, NONE, READ, Fence, enforceable


@pytest.mark.agent
@pytest.mark.timeout(600)
@pytest.mark.skipif(shutil.which("agy") is None, reason="agy is not installed here")
@pytest.mark.skipif(
    not enforceable(net=True), reason="this machine cannot cut the network"
)
def test_agy_offline_has_no_web_tool_and_still_writes_its_workdir(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    fence = Fence.of(
        local=ALL,
        user=READ,
        system=NONE,
        online=False,
        workdir=work,
        home=Path.home(),
    )
    agent = AntigravityCLIAgent(
        AntigravityCLIAgentConfig(
            model="gemini-3.7-flash-low",
            effort="low",
            permission="bypass",
            web_search=True,  # the fence wins over what the flow said
            fence=fence,
        )
    )
    try:
        said = list(
            agent.new(work).stream(
                "If you have a tool that reads a URL, use it on https://example.com. Then "
                "run the command `echo hi > ok.txt` with your terminal tool. Reply DONE."
            )
        )
    except Failed as why:
        pytest.skip(f"agy would not take a turn on this machine: {why}")

    assert said[-1].kind == "result"
    tools = " ".join(one.text for one in said if one.kind == "tool")
    assert "read_url_content" not in tools
    assert "search_web" not in tools
    assert (work / "ok.txt").read_text().strip() == "hi", tools
