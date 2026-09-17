"""A CLI of your own, driven over the Agent Client Protocol against a real ACP server.

The other half of this backend's tests lives in `tests/integration/agents/test_acp.py`, where
the conversation is held with a stand-in agent that speaks the protocol back. A stand-in can
be made to say anything, so it can never say what the handshake actually negotiates with a
peer nobody here wrote. That is what is checked here, against `opencode acp` installed on
this machine: the handshake, a turn through the catch-all driver, and a conversation picked
back up rather than opened again. It wants a real ACP server on PATH, so CI never runs it.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import AcpAgent, AcpAgentConfig

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.agent
@pytest.mark.timeout(900)
def test_a_real_acp_server_is_added_and_driven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One real ACP server, added as a CLI of your own and taken a turn on.

    The stand-in in the integration half prints the protocol; this is the protocol. What only
    the real thing can confirm is what the handshake actually negotiates, that a turn lands
    through the catch-all driver, and that the conversation is still there for the turn after
    it -- which for this backend means the session was picked back up rather than opened again.
    """
    if shutil.which("opencode") is None:
        pytest.skip("opencode is not installed here")
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    # Under a command of its own, because `opencode` is a backend humanize drives and an
    # added CLI answers to what it runs: what is being driven here is the protocol, and a
    # real server behind a name of its own is a CLI of your own in every way that matters.
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "zen-acp").write_text("#!/bin/sh\nexec opencode acp\n")
    (binaries / "zen-acp").chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    assert backends.remember("", ["zen-acp"]) == "zen-acp"

    # What the integration half builds through a helper of its own, written out here instead:
    # the two words are the ACP driver's own, for a backend whose model and effort are the
    # server's to choose, and the helper is four lines that would otherwise reach across the
    # tier boundary for no other reason.
    agent = AcpAgent(
        AcpAgentConfig(cli="zen-acp", model="as configured", effort="as configured")
    )
    # In a `finally`, because ACP holds the server up between turns: a failed assertion here
    # without it is a real `opencode acp` left running for as long as the suite is.
    try:
        session = agent.new()
        said = list(session.stream("Remember the number 4711. Reply with exactly: OK"))

        assert said[-1].kind == "result"
        assert "OK" in said[-1].text
        assert session.id  # and names the session the turn landed in
        assert "4711" in session("What number did I ask you to remember? Digits only.")
        # And it outlives the process that held it: the agent is put down as a watchdog puts
        # one down, and the next turn picks the same conversation back up rather than
        # starting one.
        session._shut()
        assert "4711" in session("Say that number again. Digits only.")
    finally:
        agent.stop()
