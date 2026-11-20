"""An Ai-chan conversation an earlier hmz kept as an epic, left where it was as the daemon started.

The daemon moves such an epic among the chats as it starts (Section 8.7.10 of core.md). One a
process still holds is left for a later start, and until then it is neither an epic nor a chat:
her conversation is not carried on in it, and nothing is written beside its record, so the
next start moves it whole.
"""

from __future__ import annotations

import fcntl
import json
import os
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from hmz import home
from hmz.daemon.reach import Conversations, Links, epic_at, ran_in
from hmz.rpc import Code, RpcError
from hmz.runtime import epic

if TYPE_CHECKING:
    from pathlib import Path


def test_a_conversation_left_as_an_epic_is_not_carried_on_until_it_is_moved(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    at = epic.under(workspace) / "20260101T000000.000Z-0ldc4a"
    at.mkdir(parents=True)
    began = {
        "event": "began",
        "kind": "chat",
        "task": "hi",
        "workspace": str(workspace.resolve()),
        "agents": [],
    }
    (at / epic.JOURNAL).write_text(
        json.dumps(began) + "\n" + json.dumps({"event": "ended", "how": "stopped"}) + "\n"
    )
    kept = Conversations()
    made = kept.made(
        {
            "slot": "ai:1",
            "scope": "daemon",
            "workspace": str(workspace),
            "epic": "",
            "nous": "claude/opus",
            "preset": "read-only",
            "network": False,
        }
    )
    kept.changed(made["id"], record=at.name)
    links = Links(mock.Mock(), mock.Mock())
    links.kept = kept
    hosted = mock.Mock(slot="ai:1")

    # Its earlier host holds it yet, as the daemon starts.
    held = os.open(at / ".held", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert epic.migrated() == ([], {at.name: "it is going"})
    finally:
        os.close(held)

    # That host gone, it is still neither an epic nor a chat to the daemon.
    assert epic_at(at.name) is None
    assert ran_in(at.name) == ""
    with pytest.raises(RpcError, match=f"There is no chat {at.name}") as refused:
        links.after(hosted)
    assert refused.value.code == Code.NOT_FOUND
    hosted.chat.assert_not_called()
    assert sorted(one.name for one in at.iterdir()) == [".held", epic.JOURNAL]

    # So the next start moves it, and her conversation is carried on in the chat it is.
    assert epic.migrated() == ([at.name], {})
    into = home() / "chats" / at.parent.name / at.name
    assert epic_at(at.name) == into
    assert ran_in(at.name) == str(workspace.resolve())
    hosted.chat.return_value = {"ok": False, "why": "enough for this test"}
    with pytest.raises(RpcError, match="enough for this test"):
        links.after(hosted)
    assert hosted.chat.call_args.args[0]["resume"] == str(into)
