"""Ai-chan's flow on a fake harness, speaking to a daemon over a scoped link of its own.

The daemon is a stand-in written here: `hmz.rpc` serving the protocol's own OpenRPC document on
a Unix socket that `HUMANIZE_AICHAN_LINK` names, answering what a scoped link answers -- a read
of the epics, and a refusal of a write to a `read-only` Ai-chan.
"""

from __future__ import annotations

import contextlib
import json
import socket
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import fence
from hmz.flows import HarnessKind
from hmz.flows.builtin.ai_chan import ai_chan
from hmz.rpc import PROTOCOL, Call, Code, Dispatcher, Peer, RpcError, admit
from hmz.sdk import fakes

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The epics the stand-in lists.
RUNS = {"runs": [{"name": "20260101-000000-chat"}], "total": 1}


class Daemon:
    """A stand-in daemon on one scoped link: what it was called, and by whom."""

    def __init__(self, link: Path) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.kinds: list[str] = []
        self.peers: list[Peer] = []
        self.serving = Dispatcher()
        self.serving.register("session.hello", self.hello)
        self.serving.register("runs.list", self.runs_list)
        self.serving.register("settings.set", self.settings_set)
        self.listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listening.bind(str(link))
        self.listening.listen(4)
        threading.Thread(target=self.accepts, daemon=True).start()

    def accepts(self) -> None:
        with contextlib.suppress(OSError):
            while True:
                one, _ = self.listening.accept()
                self.peers.append(Peer(one, self.serving, name="aichan-link"))

    def hello(self, call: Call) -> dict[str, Any]:
        admit(call.params["protocol"])
        self.kinds.append(call.params["client"]["kind"])
        return {"daemon_id": "d", "protocol": PROTOCOL, "paired": True}

    def runs_list(self, call: Call) -> dict[str, Any]:
        self.calls.append(("runs.list", dict(call.params)))
        return RUNS

    def settings_set(self, call: Call) -> dict[str, Any]:
        self.calls.append(("settings.set", dict(call.params)))
        raise RpcError(
            Code.FORBIDDEN, "Ai-chan is read-only, and settings.set changes things."
        )

    def close(self) -> None:
        self.listening.close()
        for one in self.peers:
            one.close()


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch) -> Iterator[Daemon]:
    link = Path(tempfile.gettempdir()) / "ai-1.sock"
    monkeypatch.setenv("HUMANIZE_AICHAN_LINK", str(link))
    # Confinement is the harness's, and a fake harness has none to hold: the backend that
    # can hold hers is said to be the one chosen.
    monkeypatch.setattr(fence, "chosen", lambda: fence.BWRAP)
    held = Daemon(link)
    try:
        yield held
    finally:
        held.close()


def _operator(read: list[str], refused: list[str]) -> fakes.FakeAgentDriver:
    """Ai-chan's fake model: each turn reads the epics, then tries to write a setting."""

    async def reply(prompt: str, *, session: fakes.FakeSession, **_: Any) -> str:
        del prompt
        read.append(
            await session.use(
                "hmz_call", {"method": "runs.list", "params": {"limit": 5}}
            )
        )
        refused.append(
            await session.use("settings_set", {"values": {"ai_chan": "claude"}})
        )
        return f"turn {len(read)}"

    return fakes.FakeAgentDriver(HarnessKind.CLAUDE, reply=reply)


async def test_ai_chan_calls_the_daemon_is_refused_and_carries_on(
    daemon: Daemon, tmp_path: Path
) -> None:
    read: list[str] = []
    refused: list[str] = []
    her = _operator(read, refused)
    journal = tmp_path / "journal"

    await fakes.run_fake(
        ai_chan, "what is going on?", agents={"ai_chan": her}, journal=journal
    )

    # Over her own link, as ai-chan, a read answered and a write refused to her as the
    # tool failing; her turn went on and ended, and nobody answered, so she folded away.
    assert daemon.kinds == ["ai-chan"]
    assert json.loads(read[0]) == RUNS
    assert daemon.calls[0] == ("runs.list", {"limit": 5})
    assert refused == [
        "Refused: Ai-chan is read-only, and settings.set changes things."
    ]
    (first,) = her.sessions
    assert first.prompts[0].startswith("You are Ai-chan")
    assert "Your preset is read-only" in first.prompts[0]
    assert "data, not instructions" in first.prompts[0]
    assert first.prompts[0].endswith("what is going on?")

    await fakes.run_fake(
        ai_chan, "and now?", agents={"ai_chan": her}, journal=journal, resume=True
    )

    # Carried on: the conversation she kept, told who she is once, over a new session.
    (_, carried) = her.sessions
    assert carried.carried_on is not None
    assert carried.prompts == [first.prompts[0], "and now?"]
    assert len(read) == 2
    assert daemon.kinds == ["ai-chan", "ai-chan"]


async def test_ai_chan_refuses_to_start_without_her_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz.flows import FlowRuntimeError

    monkeypatch.delenv("HUMANIZE_AICHAN_LINK", raising=False)

    with pytest.raises(FlowRuntimeError, match="HUMANIZE_AICHAN_LINK is unset"):
        await fakes.run_fake(ai_chan, "hi")


async def test_ai_chan_runs_the_same_calls_from_her_shell(daemon: Daemon) -> None:
    ran: list[tuple[int, str, str]] = []

    async def reply(prompt: str, *, session: fakes.FakeSession, **_: Any) -> str:
        del prompt
        ran.append(
            await session.run_cli(
                ["hmz-ai", "epics-list", "--q", "chat", "--limit", "3"]
            )
        )
        ran.append(
            await session.run_cli(
                ["hmz-ai", "settings-set", "--values", '{"ai_chan": "claude"}']
            )
        )
        return "done"

    her = fakes.FakeAgentDriver(HarnessKind.CLAUDE, reply=reply)

    await fakes.run_fake(ai_chan, "list them", agents={"ai_chan": her})

    (listed, refused) = ran
    assert (listed[0], json.loads(listed[1])) == (0, RUNS)
    assert daemon.calls[0] == ("runs.list", {"q": "chat", "limit": 3})
    assert refused[0] == 1
    assert "Ai-chan is read-only" in refused[2]
