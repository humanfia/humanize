"""`hmz.sdk.Client`: one session with a daemon, its session a stand-in."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from hmz.rpc import Closed, RpcError
from hmz.sdk import Client, Refused

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.rpc import Call

#: What a daemon says back to `session.hello`.
_HELLO = {
    "daemon_id": "d1",
    "version": "1.2.3",
    "protocol": "2.0.0",
    "capabilities": ["webrtc"],
    "device": "local",
}


class _Peer:
    """A session: each call answered as `answers` says, closed when told."""

    def __init__(self, answers: Callable[[str, dict[str, Any]], Any]) -> None:
        self.answers = answers
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self._closed = threading.Event()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._closed.wait(timeout)

    def close(self) -> None:
        self._closed.set()

    def request(self, method: str, params: dict[str, Any]) -> mock.Mock:
        if self.closed:
            raise Closed("closed")
        self.asked.append((method, params))
        pending = mock.Mock()
        try:
            answer = self.answers(method, params)
        except BaseException as why:  # noqa: BLE001 -- raised again as the answer
            pending.result.side_effect = why
        else:
            pending.result.return_value = answer
        return pending


def _client(
    answers: Callable[[str, dict[str, Any]], Any] = lambda method, params: {},
) -> tuple[Client, _Peer, list[Callable[[Call], None]]]:
    peer = _Peer(answers)
    served: list[Callable[[Call], None]] = []

    def dial(serve: Callable[[Call], None]) -> tuple[Any, dict[str, Any]]:
        served.append(serve)
        return peer, _HELLO

    return Client(dial), peer, served


def test_the_client_is_what_hello_answered() -> None:
    client, _, _ = _client()

    assert (client.daemon_id, client.version, client.protocol) == (
        "d1",
        "1.2.3",
        "2.0.0",
    )
    assert client.capabilities == ("webrtc",)
    assert client.device == "local"


def test_a_call_answers_its_result_with_its_idem_added() -> None:
    client, peer, _ = _client(lambda method, params: {"said": method})

    assert client.call("hosts.list", {"x": 1}, idem="k") == {"said": "hosts.list"}
    assert peer.asked == [("hosts.list", {"x": 1, "idem": "k"})]


def test_an_error_is_refused_with_its_message_code_and_data() -> None:
    def refuses(method: str, params: dict[str, Any]) -> Any:
        raise RpcError(409, "a flow is already running", {"run": 3})

    client, _, _ = _client(refuses)

    with pytest.raises(Refused, match="a flow is already running") as refused:
        client.call("epic.start")
    assert (refused.value.code, refused.value.data) == (409, {"run": 3})


def test_a_call_on_a_session_that_ended_is_refused_503() -> None:
    client, _, _ = _client()
    client.close()

    with pytest.raises(Refused, match="the daemon went away") as refused:
        client.call("hosts.list")
    assert refused.value.code == 503


def test_a_call_not_answered_in_time_says_so() -> None:
    def waits(method: str, params: dict[str, Any]) -> Any:
        raise TimeoutError

    client, _, _ = _client(waits)

    with pytest.raises(TimeoutError, match=r"no answer to 'epic\.status' in 0\.5s"):
        client.call("epic.status", seconds=0.5)


def test_every_notification_goes_to_the_listener_in_order() -> None:
    client, peer, (serve,) = _client()
    heard: list[tuple[str, dict[str, Any]]] = []
    done = threading.Event()
    serve(mock.Mock(id=None, method="epic.event", params={"n": 1}))
    serve(mock.Mock(id=7, method="not.a.notification", params={}))

    def listens(method: str, params: dict[str, Any]) -> None:
        heard.append((method, params))
        if len(heard) == 2:
            done.set()

    client.heard(listens)
    serve(mock.Mock(id=None, method="notices.event", params={"n": 2}))

    assert done.wait(5)
    assert heard == [("epic.event", {"n": 1}), ("notices.event", {"n": 2})]
    with pytest.raises(RuntimeError):
        client.heard(listens)
    peer.close()


def test_closing_twice_is_closing_once_and_a_with_block_closes() -> None:
    client, peer, _ = _client()

    with client:
        pass

    assert peer.closed
    client.close()
