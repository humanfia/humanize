"""What a MiniMax Code turn costs, read out of the messages its session keeps as it goes.

Every answer in a session's `messages.jsonl` carries what the request it came back on cost,
under pi's names, and the provider and model that answered -- which is what it is counted
against. The session's directory is named for its id in URL-safe base64, and the tally finds
it by the id the backend stated.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

from hmz.coganchor.agents import MiniMaxCodeAgent, MiniMaxCodeAgentConfig
from hmz.tui.monitor import Monitor
from hmz.tui.tally import Seen, Tally, reported

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_a_session_is_counted_from_the_answers_it_keeps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "minimax"
    monkeypatch.setenv("MINIMAX_DATA_DIR", str(home))
    session = "mvs_0123456789abcdef0123456789abcdef"
    encoded = base64.urlsafe_b64encode(session.encode()).decode().rstrip("=")
    log = home / "v2/sessions/2026/09/30" / f"01-33-02-085-session_{encoded}"
    log.mkdir(parents=True)
    usage = {"input": 60, "output": 7, "cacheRead": 40, "cacheWrite": 0}
    rows = [
        {"message": {"role": "user", "content": "hi", "timestamp": 1}},
        {
            "message": {
                "role": "assistant",
                "provider": "custom_provider:gateway",
                "model": "minimax-m3",
                "usage": {**usage, "totalTokens": 107},
                "timestamp": 2,
            }
        },
        {"message": {"role": "toolResult", "toolCallId": "c", "timestamp": 3}},
    ]
    (log / "messages.jsonl").write_text("".join(json.dumps(one) + "\n" for one in rows))
    agent = MiniMaxCodeAgent(MiniMaxCodeAgentConfig(model="", effort=""))
    monitor = Monitor()

    Tally(
        [Seen(agent.id, agent.backend, "", type(agent).counts, frozenset({session}))],
        monitor,
    ).read()

    assert monitor.spent == {"custom_provider:gateway/minimax-m3": 107}
    assert reported("mcode") == {"input", "output", "cache_read", "cache_write"}
