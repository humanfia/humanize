"""Ai-chan end to end: a daemon of the test's own has her chat, the stand-in playing her role.

`aichan.create` starts her host, which has her conversation's chat with the stand-in `claude`
as her nous, confined as her conversation is. The stand-in reaches for one of her tools through
the MCP server Humanize gives it; the tool calls the daemon over her scoped link, as `ai-chan`,
and what it was answered -- or refused -- is what she says, and what her chat then waits on.
"""

from __future__ import annotations

import json
import socket
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.fence import BWRAP, able
from hmz.daemon import where
from hmz.reach.pipes import SocketPipe
from hmz.rpc import PROTOCOL, Peer
from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_daemon import hosting, until

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [pytest.mark.timeout(180)]


def _fenced() -> bool:
    """Whether her confinement can be held here: Seatbelt, or a bubblewrap that starts."""
    if sys.platform == "darwin":
        return True
    try:
        return sys.platform == "linux" and able(BWRAP)[0]
    except OSError:
        return False


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    if not _fenced():
        pytest.skip("Ai-chan is held by Seatbelt or bubblewrap, and neither is here")
    at = install(tmp_path, monkeypatch)
    if sys.platform == "linux":
        # Landlock cannot keep her off the daemon's socket (Section 14.5.5 of core.md).
        (tmp_path / "humanize-home").mkdir(exist_ok=True)
        (tmp_path / "humanize-home" / "settings.yaml").write_text(
            "sandbox:\n  backend: bwrap\n"
        )
    with hosting():
        yield at


def _session() -> Peer:
    one = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    one.connect(str(where.at() / where.SOCKET))
    peer = Peer(SocketPipe(one, trusted=True), name="test-session")
    peer.call(
        "session.hello",
        {"protocol": PROTOCOL, "client": {"name": "test", "kind": "cli"}},
        timeout=10,
    )
    return peer


def _pending(user: Peer, made: dict[str, Any]) -> list[dict[str, Any]]:
    """What her conversation waits on you with: what she said last, nothing before she has."""
    status = user.call(
        "hosts.status",
        {"workspace": made["workspace"], "slot": made["slot"]},
        timeout=30,
    )
    return list(status.get("pending") or [])


def _said(user: Peer, made: dict[str, Any]) -> str:
    return "\n".join(str(one.get("text", "")) for one in _pending(user, made))


def test_ai_chan_calls_the_daemon_through_her_tools_over_her_link(
    project: Path,
) -> None:
    from hmz import daemon

    del project
    daemon.start()
    user = _session()
    made = user.call(
        "aichan.create", {"scope": "daemon", "nous": AGENT, "task": "hello"}, timeout=60
    )
    # Her first turn, which the stand-in answers; she waits on you after it.
    assert until(lambda: _pending(user, made), 120), _said(user, made)
    sub = user.call(
        "epic.attach",
        {"workspace": made["workspace"], "slot": made["slot"], "replay": False},
        timeout=30,
    )["sub"]
    asked = json.dumps({"method": "workspaces.list", "params": {}})

    def says(text: str) -> str:
        """Answers what she waits on with `text`, and what she says to it."""
        (waiting,) = _pending(user, made)
        user.call(
            "epic.answer",
            {"sub": sub, "question": waiting["question"], "text": text},
            timeout=30,
        )
        assert until(
            lambda: any(
                one["question"] != waiting["question"] for one in _pending(user, made)
            ),
            120,
        ), _said(user, made)
        return _said(user, made)

    # Briefed with what she was made with, which the stand-in did.
    assert "did: You are Ai-chan" in _said(user, made)
    names, _, answered = says(f"tool: hmz_call {asked}").partition("said:")
    assert "hmz_call" in names
    assert "hmz_methods" in names
    assert "workspaces" in answered
    # A write is refused her, read-only as she is, and said to her as the tool failing.
    refused = says('tool: settings_set {"values": {"details": true}}')
    assert "Ai-chan is read-only, and settings.set changes things." in refused

    def listed() -> tuple[int, bool]:
        """How many epics the user is listed, and whether her directory is among the workspaces."""
        workspaces = user.call("workspaces.list", {}, timeout=30)["workspaces"]
        return (
            user.call("runs.list", {}, timeout=30)["total"],
            made["workspace"] in [one["path"] for one in workspaces],
        )

    # Her chat is an epic, and nothing of it is on the user's lists, kept or forgotten.
    assert listed() == (0, False)
    assert user.call("aichan.forget", {"id": made["id"]}, timeout=30) == {}
    assert listed() == (0, False)


def test_ai_chans_conversation_is_not_carried_on_as_a_chat_of_its_workspace(
    project: Path,
) -> None:
    from hmz import daemon
    from hmz.rpc import RpcError

    daemon.start()
    user = _session()
    made = user.call(
        "aichan.create",
        {"scope": "workspace", "workspace": str(project), "nous": AGENT, "task": "hi"},
        timeout=60,
    )
    assert until(lambda: _pending(user, made), 120), _said(user, made)
    status = user.call(
        "hosts.status",
        {"workspace": made["workspace"], "slot": made["slot"]},
        timeout=30,
    )
    carried = {
        "workspace": made["workspace"],
        "slot": "chat:",
        "task": "as a chat",
        "resume": status["epic"],
    }

    def refused() -> str:
        with pytest.raises(RpcError) as why:
            user.call("chat.start", carried, timeout=60)
        return why.value.message

    # Her epic is a chat's and of this workspace, and no chat of it to carry on: neither
    # while her host holds it, nor once her conversation is forgotten and its host gone.
    no = f"{status['epic']} is not a chat of {made['workspace']}."
    assert refused() == no
    assert user.call("aichan.forget", {"id": made["id"]}, timeout=30) == {}
    assert refused() == no
