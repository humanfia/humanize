"""Official Kimi event notifications accelerate polling, and carry the one figure REST will not.

Turn state stays REST's: what has been said, what is being asked, whether the turn is still
running. Spending does not, because on 0.42.0 REST has none -- the session route answers four
literal zeros for the life of a session, and the step frames read here are the only place the
daemon says what a request cost.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import textwrap
import threading
from collections import Counter
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from hmz.coganchor.agents import kimi

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import ModuleType

    from websockets.sync.server import ServerConnection


@contextmanager
def server(handler: Callable[[ServerConnection], None]) -> Generator[str]:
    with serve(handler, "127.0.0.1", 0) as running:
        reader = threading.Thread(target=running.serve_forever, daemon=True)
        reader.start()
        yield f"http://127.0.0.1:{running.socket.getsockname()[1]}/api/v1"
        running.shutdown()
        reader.join(timeout=2)


def acknowledge(socket: ServerConnection, code: int = 0) -> None:
    assert socket.request is not None
    assert socket.request.headers["Authorization"] == "Bearer test-token"
    assert json.loads(socket.recv())["payload"] == {"session_ids": ["ours"]}
    socket.send(json.dumps({"type": "ack", "id": "hmz", "code": code}))


def test_notifications_are_isolated_and_completion_removes_settle_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for session, kind in (
            ("theirs", "turn.ended"),
            ("ours", "tool.call.started"),
            ("ours", "turn.ended"),
        ):
            socket.send(json.dumps({"type": kind, "session_id": session}))
        socket.recv()  # keep the stream open until the reader closes it

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            updates.wait(settled=False)
            assert not updates.ended
            updates.wait(settled=False)
            assert updates.ended
            slept: list[float] = []
            monkeypatch.setattr(kimi.time, "sleep", slept.append)
            updates.wait(settled=True)
            assert not slept
        finally:
            updates.close()


def test_heartbeats_echo_the_nonce_and_keep_notifications_flowing() -> None:
    replies: list[object] = []

    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for nonce, kind in (("one", "tool.call.started"), ("two", "turn.ended")):
            # Official application heartbeats have no session_id. Progress is withheld
            # until the client answers, so automatic WebSocket control pongs cannot pass.
            socket.send(json.dumps({"type": "ping", "payload": {"nonce": nonce}}))
            replies.append(json.loads(socket.recv(timeout=1)))
            socket.send(json.dumps({"type": kind, "session_id": "ours"}))
        socket.recv()

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            updates.wait(settled=False)
            assert not updates.ended
            updates.wait(settled=False)
            assert updates.ended
            assert updates._socket is not None
            assert replies == [
                {"type": "pong", "payload": {"nonce": "one"}},
                {"type": "pong", "payload": {"nonce": "two"}},
            ]
        finally:
            updates.close()


def test_saturated_notification_queue_does_not_delay_cleanup() -> None:
    sent = threading.Event()

    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for _ in range(64):
            socket.send(
                json.dumps(
                    {"type": "assistant.delta", "session_id": "ours", "payload": {}}
                )
            )
        sent.set()
        with suppress(ConnectionClosed):
            socket.recv(timeout=2)

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            socket = updates._socket
            assert socket is not None
            assert sent.wait(timeout=2)
            deadline = kimi.time.monotonic() + 2
            while not socket.recv_messages.paused and kimi.time.monotonic() < deadline:
                kimi.time.sleep(0.001)
            # Reproduce the actual failure: flow control prevents the receive thread
            # from reading the peer's close reply until the closing timeout expires.
            assert socket.recv_messages.paused
            assert socket.recv_messages.frames.qsize() > 16
            began = kimi.time.monotonic()
            updates.close()
            assert kimi.time.monotonic() - began < 0.5
            assert updates._socket is None
            assert socket.state.name == "CLOSED"
            assert not socket.recv_events_thread.is_alive()
        finally:
            updates.close()


def test_failed_heartbeat_reply_returns_to_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(json.dumps({"type": "ping", "payload": {"nonce": "one"}}))
        socket.recv()

    def fail_send(_message: object) -> None:
        raise OSError("connection lost while replying")

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        assert updates._socket is not None
        monkeypatch.setattr(updates._socket, "send", fail_send)
        updates.wait(settled=False)
        assert updates._socket is None
        slept: list[float] = []
        monkeypatch.setattr(kimi.time, "sleep", slept.append)
        updates.wait(settled=False)
        assert slept == [kimi._POLL_SECONDS]


def test_refused_subscription_returns_to_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket, code=40001)

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        slept: list[float] = []
        monkeypatch.setattr(kimi.time, "sleep", slept.append)
        updates.wait(settled=False)
        assert slept == [kimi._POLL_SECONDS]
        assert updates._socket is None


def test_lost_event_stream_returns_to_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        updates.wait(settled=False)
        assert updates._socket is None
        slept: list[float] = []
        monkeypatch.setattr(kimi.time, "sleep", slept.append)
        updates.wait(settled=False)
        assert slept == [kimi._POLL_SECONDS]


def test_quiet_event_stream_still_allows_recovery_polls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.recv()

    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 0.01)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            updates.wait(settled=False)
            assert updates._socket is not None
            assert not updates.ended
        finally:
            updates.close()


@pytest.mark.parametrize(
    "message",
    [
        "[]",
        json.dumps({"type": "turn.ended", "session_id": "ours", "payload": []}),
        json.dumps({"type": "ping", "payload": {"nonce": 1}}),
    ],
)
def test_malformed_notification_returns_to_polling(message: str) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(message)
        socket.recv()

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        updates.wait(settled=False)
        assert updates._socket is None


def test_streaming_text_wakes_a_recovery_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(json.dumps({"type": "assistant.delta", "session_id": "ours"}))
        socket.recv()

    # Without a text wakeup this would wait the ten-second recovery interval instead.
    monkeypatch.setattr(kimi, "_POLL_SECONDS", 0.01)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            started = kimi.time.monotonic()
            updates.wait(settled=False)
            assert kimi.time.monotonic() - started < 1
        finally:
            updates.close()


def test_subagent_completion_does_not_settle_the_main_turn() -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for agent, kind in (
            ("main", "turn.started"),
            ("worker", "turn.ended"),
            ("main", "turn.ended"),
            ("worker", "turn.started"),
            ("worker", "turn.ended"),
            ("main", "turn.started"),
            ("main", "event.approval.requested"),
        ):
            socket.send(
                json.dumps(
                    {"type": kind, "session_id": "ours", "payload": {"agentId": agent}}
                )
            )
        socket.recv()

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            updates.wait(settled=False)
            assert not updates.ended
            updates.wait(settled=False)
            assert updates.ended
            updates.wait(settled=False)
            assert updates.ended
            updates.wait(settled=False)
            assert not updates.ended
        finally:
            updates.close()


def test_notifications_say_when_a_question_may_be_waiting() -> None:
    """Only a question is something a turn stops on, so only it is worth bringing forward.

    Whether a turn is still running, and what it has spent, are read a second apart whatever
    the daemon says: one is a reading a turn cannot end without and the other is a meter. A
    step that landed carries the spending and still raises no question, which is the one
    frame here that does something and brings nothing forward.
    """

    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for kind in (
            "tool.call.started",
            "turn.step.completed",
            "event.approval.requested",
            "event.question.requested",
            "error",
        ):
            socket.send(json.dumps({"type": kind, "session_id": "ours"}))
        socket.recv()

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            # A listener that has been told nothing yet asks the daemon anyway.
            assert updates.questioned
            for expected in (
                False,  # a tool starting is not a turn stopping to ask
                False,  # nor is a step that landed
                True,  # an approval is a question by another name
                True,
                True,  # and one the daemon could not finish is asked about too
            ):
                updates.questioned = False
                updates.wait(settled=False)
                assert updates.questioned is expected
        finally:
            updates.close()


def test_a_frame_under_an_unknown_name_still_wakes_the_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(json.dumps({"type": "event.consent.wanted", "session_id": "ours"}))
        socket.recv()

    # Without this the reader would wait out the whole recovery interval for a question
    # the daemon had named something this table has never heard of. Waking is the whole
    # of it: the reader then makes its ordinary second's reads, which is where a question
    # under a name nobody wrote down is found -- and where it was found before there were
    # notifications at all.
    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 30)
    monkeypatch.setattr(kimi, "_POLL_SECONDS", 0.05)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            updates.questioned = False
            started = kimi.time.monotonic()
            updates.wait(settled=False)
            assert kimi.time.monotonic() - started < 5
            assert not updates.questioned  # coalesced, not brought forward
        finally:
            updates.close()


def test_streamed_chunks_are_coalesced_rather_than_woken_for_one_by_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = threading.Event()

    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for kind in ("shell.output", "tool.call.delta", "tool.progress"):
            for _ in range(8):
                socket.send(json.dumps({"type": kind, "session_id": "ours"}))
        sent.set()
        socket.recv()

    # The daemon streams a running command's output a chunk at a time. One wake per chunk
    # would be four calls per chunk on the daemon every session of the agent shares. The
    # recovery interval is only wanted longer than the poll interval, so that a wake is a
    # frame rather than a deadline; the wait after the last chunk is spent waiting it out.
    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 1.0)
    monkeypatch.setattr(kimi, "_POLL_SECONDS", 0.2)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            assert sent.wait(timeout=2)
            wakes: list[
                bool
            ] = []  # and whether each of them said to ask about a question
            deadline = kimi.time.monotonic() + 1.5
            while kimi.time.monotonic() < deadline:
                updates.questioned = False
                updates.wait(settled=False)
                wakes.append(updates.questioned)
            assert len(wakes) <= 12  # two dozen chunks, at most one wake per interval
            # None of the chunks is a turn stopping to ask. The silence after the last of
            # them is a listener that may have missed one, and does ask.
            assert not wakes[0]
        finally:
            updates.close()


def test_streaming_text_alone_does_not_re_arm_the_authoritative_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for _ in range(4):
            socket.send(json.dumps({"type": "assistant.delta", "session_id": "ours"}))
        socket.recv()

    # A deadline reached with text still arriving is the coalescing above, not silence:
    # nothing about it says a question is waiting or that spending has moved. Silence is
    # covered separately, and does ask the daemon everything.
    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 30)
    monkeypatch.setattr(kimi, "_POLL_SECONDS", 0.05)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            updates.questioned = False
            updates.wait(settled=False)
            assert not updates.questioned
        finally:
            updates.close()


def test_a_listener_that_stops_carrying_events_asks_for_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(json.dumps({"type": "turn.step.completed", "session_id": "ours"}))
        socket.recv()

    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 0.01)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", Counter())
        try:
            updates.wait(settled=False)
            updates.questioned = False
            # Silence for a whole recovery interval is a listener that may have missed
            # something, so the reader goes back to asking the daemon anyway.
            updates.wait(settled=False)
            assert updates.questioned
            updates.questioned = False
            updates.close()
            assert updates.questioned
            updates.questioned = False
            slept: list[float] = []
            monkeypatch.setattr(kimi.time, "sleep", slept.append)
            updates.wait(settled=False)
            assert slept == [kimi._POLL_SECONDS]
            assert updates.questioned
        finally:
            updates.close()


def test_a_missing_websocket_client_says_which_extra_carries_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kimi Code is an extra, so the line that adds it is what a session without it says."""
    real_import = importlib.import_module

    def missing(name: str) -> ModuleType:
        if name.partition(".")[0] == "websockets":
            raise ModuleNotFoundError(name="websockets")
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", missing)

    with pytest.raises(ModuleNotFoundError, match=r"\[kimi\] extra"):
        kimi._Updates("http://127.0.0.1:1/api/v1", "test-token", "ours", Counter())


def test_the_backends_load_without_the_websocket_client() -> None:
    """An install without the `kimi` extra still holds every backend, kimi's class included.

    Read in a Python of its own, because the only way to have none of a package is to have
    started without it: this suite drives a real server at the reader above, so websockets
    is here, and an import that moved back to module scope would pass unnoticed otherwise.
    """
    without = textwrap.dedent(
        """
        import sys

        class Absent:
            def find_spec(self, name, path=None, target=None):
                if name.partition(".")[0] == "websockets":
                    raise ModuleNotFoundError(name="websockets")
                return None

        sys.meta_path.insert(0, Absent())
        from hmz.coganchor.agents import KimiCodeCLIAgent

        assert "websockets" not in sys.modules
        print(KimiCodeCLIAgent.__name__)
        """
    )

    ran = subprocess.run(
        [sys.executable, "-c", without],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == "KimiCodeCLIAgent"


def test_what_a_step_says_it_spent_is_added_to_the_session_that_spent_it() -> None:
    """The step frame is where 0.42.0 says what a request cost, so this is the whole meter.

    And it says it in its own names, one of which does not mean what it looks like. The CLI's
    own `inputTotal` is `inputOther + inputCacheRead + inputCacheCreation`, so `inputOther` is
    the input no cache served -- which is exactly what `input` means here, the kinds being
    counted so that adding them up is the whole of what crossed the wire. Read as the whole
    input it would charge the cached part of it twice.
    """

    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for session, agent, usage in (
            ("ours", "main", {"inputOther": 3, "output": 23, "inputCacheRead": 21248}),
            (
                "theirs",
                "main",
                {"inputOther": 900, "output": 900, "inputCacheRead": 900},
            ),
            (
                "ours",
                "swarm_1",
                {"inputOther": 7, "output": 11, "inputCacheCreation": 40},
            ),
            ("ours", "main", {}),
        ):
            socket.send(
                json.dumps(
                    {
                        "type": "turn.step.completed",
                        "session_id": session,
                        "payload": {"agentId": agent, "usage": usage or None},
                    }
                )
            )
        socket.recv()

    stepped: Counter[str] = Counter()
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours", stepped)
        try:
            for _ in range(3):
                updates.wait(settled=False)
        finally:
            updates.close()

    # One daemon serves every session of its agent and publishes all of their frames down
    # every socket, so the thousands the other session spent are not on this session's bill.
    # A swarm member's are: it ran inside this session, and what it asked the model for is
    # what this session is charged. A step that carried no usage at all adds nothing, which
    # is not the same as its having cost nothing.
    assert stepped == Counter(
        {"input": 10, "output": 34, "cache_read": 21248, "cache_write": 40}
    )
