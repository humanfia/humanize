"""One end of a JSON-RPC 2.0 session over an in-memory pipe (Section 6.4 of wire.md)."""

import errno
import json
import struct
import threading
from collections.abc import Callable
from typing import Any

import pytest

from hmz.rpc import LONGEST, Call, Closed, Code, Peer, Pipe, RpcError, encode

type Pipes = Callable[[], tuple[Pipe, Pipe]]
type Received = Callable[[Pipe], dict[str, Any]]


def echo(call: Call) -> None:
    if call.id is not None:
        call.answer({"method": call.method, "params": call.params})


def test_a_call_is_answered_with_its_result(pipes: Pipes) -> None:
    near, far = pipes()
    Peer(far, echo)
    peer = Peer(near)
    assert peer.call("a.b", {"x": 1}, timeout=5) == {
        "method": "a.b",
        "params": {"x": 1},
    }
    assert peer.call("a.c", timeout=5) == {"method": "a.c", "params": {}}


def test_a_call_carries_a_fresh_integer_id_and_params_by_name(
    pipes: Pipes, received: Received
) -> None:
    near, far = pipes()
    peer = Peer(near)
    peer.request("a.b", {"x": 1})
    peer.request("a.b")
    first, second = received(far), received(far)
    assert first == {"jsonrpc": "2.0", "id": 1, "method": "a.b", "params": {"x": 1}}
    assert second == {"jsonrpc": "2.0", "id": 2, "method": "a.b"}


def test_answers_settle_the_calls_they_name_in_any_order(
    pipes: Pipes, received: Received
) -> None:
    near, far = pipes()
    peer = Peer(near)
    one, two = peer.request("a"), peer.request("b")
    received(far)
    received(far)
    far.sendall(encode({"jsonrpc": "2.0", "id": two.id, "result": "two"}))
    far.sendall(encode({"jsonrpc": "2.0", "id": 999, "result": "nobody's"}))
    far.sendall(encode({"jsonrpc": "2.0", "id": one.id, "result": "one"}))
    assert one.result(5) == "one"
    assert two.result(5) == "two"


def test_an_error_answer_is_raised_with_its_code_message_and_data(
    pipes: Pipes,
) -> None:
    def refuse(call: Call) -> None:
        call.fail(RpcError(Code.CONFLICT, "Not now.", {"why": "busy"}))

    near, far = pipes()
    Peer(far, refuse)
    with pytest.raises(RpcError) as refused:
        Peer(near).call("a.b", timeout=5)
    assert (refused.value.code, refused.value.message) == (409, "Not now.")
    assert refused.value.data == {"why": "busy"}


def test_either_end_calls_and_notifies(pipes: Pipes) -> None:
    told: list[tuple[str, dict[str, Any]]] = []
    arrived = threading.Event()

    def serve(call: Call) -> None:
        if call.id is None:
            told.append((call.method, call.params))
            arrived.set()
        else:
            call.answer(call.method)

    near, far = pipes()
    one, two = Peer(near, serve), Peer(far, serve)
    assert one.call("to.two", timeout=5) == "to.two"
    assert two.call("to.one", timeout=5) == "to.one"
    two.notify("x.event", {"n": 1})
    assert arrived.wait(5)
    assert told == [("x.event", {"n": 1})]


def test_a_notification_is_sent_without_an_id(pipes: Pipes, received: Received) -> None:
    near, far = pipes()
    Peer(near).notify("x.event", {"n": 1})
    assert received(far) == {"jsonrpc": "2.0", "method": "x.event", "params": {"n": 1}}


def test_a_call_with_no_serve_is_no_method(pipes: Pipes, received: Received) -> None:
    near, far = pipes()
    Peer(near)
    far.sendall(encode({"jsonrpc": "2.0", "id": "q", "method": "nope"}))
    assert received(far) == {
        "jsonrpc": "2.0",
        "id": "q",
        "error": {"code": -32601, "message": "There is no method nope."},
    }


def test_a_call_is_answered_once(pipes: Pipes, received: Received) -> None:
    def twice(call: Call) -> None:
        call.answer(1)
        call.answer(2)
        call.fail(RpcError(400, "No."))

    near, far = pipes()
    Peer(near, twice)
    far.sendall(encode({"jsonrpc": "2.0", "id": 7, "method": "a"}))
    far.sendall(encode({"jsonrpc": "2.0", "id": 8, "method": "a"}))
    assert received(far)["result"] == 1
    assert received(far) == {"jsonrpc": "2.0", "id": 8, "result": 1}


def frame(payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + payload


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"{not json", -32700),
        (b"\xff\xfe", -32700),
        (b"[]", -32600),
        (b'[{"jsonrpc": "2.0", "id": 1, "method": "a"}]', -32600),
        (b"3", -32600),
        (b'{"id": 1, "method": "a"}', -32600),
        (b'{"jsonrpc": "2.0", "id": true, "method": "a"}', -32600),
        (b'{"jsonrpc": "2.0", "id": 1.5, "method": "a"}', -32600),
        (b'{"jsonrpc": "2.0"}', -32600),
    ],
)
def test_what_is_not_a_request_is_refused_with_no_id(
    pipes: Pipes, received: Received, payload: bytes, code: int
) -> None:
    near, far = pipes()
    Peer(near, echo)
    far.sendall(frame(payload))
    answer = received(far)
    assert answer["id"] is None
    assert answer["error"]["code"] == code
    if code == -32700:
        assert answer["error"]["message"] == "Send JSON."


def test_params_by_position_are_refused_with_the_calls_id(
    pipes: Pipes, received: Received
) -> None:
    near, far = pipes()
    Peer(near, echo)
    far.sendall(encode({"jsonrpc": "2.0", "id": 3, "method": "a", "params": [1]}))
    answer = received(far)
    assert (answer["id"], answer["error"]["code"]) == (3, -32600)


def test_an_id_still_in_use_is_refused(pipes: Pipes, received: Received) -> None:
    held: list[Call] = []
    near, far = pipes()
    Peer(near, held.append)
    far.sendall(encode({"jsonrpc": "2.0", "id": 1, "method": "a"}))
    far.sendall(encode({"jsonrpc": "2.0", "id": 1, "method": "b"}))
    answer = received(far)
    assert (answer["id"], answer["error"]["code"]) == (None, -32600)
    held[0].answer("first")
    assert received(far) == {"jsonrpc": "2.0", "id": 1, "result": "first"}


def test_a_failing_serve_still_answers(pipes: Pipes, received: Received) -> None:
    def broken(call: Call) -> None:
        raise KeyError("x")

    near, far = pipes()
    Peer(near, broken)
    far.sendall(encode({"jsonrpc": "2.0", "id": 1, "method": "a"}))
    error = received(far)["error"]
    assert error["code"] == -32603
    assert error["message"].startswith("Something went wrong here: ")


def test_an_unknown_notification_is_ignored(pipes: Pipes) -> None:
    near, far = pipes()
    Peer(near)
    peer = Peer(far)
    peer.notify("never.heard.of")
    with pytest.raises(RpcError) as refused:
        peer.call("a", timeout=5)
    assert refused.value.code == Code.METHOD_NOT_FOUND


def test_a_timeout_gives_the_call_up_and_asks_the_far_end_to(
    pipes: Pipes, received: Received
) -> None:
    near, far = pipes()
    peer = Peer(near)
    with pytest.raises(TimeoutError):
        peer.call("slow", timeout=0.05)
    call, cancel = received(far), received(far)
    assert cancel == {
        "jsonrpc": "2.0",
        "method": "session.cancel",
        "params": {"id": call["id"]},
    }
    far.sendall(encode({"jsonrpc": "2.0", "id": call["id"], "result": "late"}))
    again = peer.request("again")
    assert received(far)["id"] == again.id != call["id"]
    far.sendall(encode({"jsonrpc": "2.0", "id": again.id, "result": "now"}))
    assert again.result(5) == "now"


def test_cancel_marks_the_call_and_its_handler_answers_cancelled(
    pipes: Pipes,
) -> None:
    def patient(call: Call) -> None:
        def wait() -> None:
            if call.cancelled.wait(5):
                call.fail(RpcError(Code.CANCELLED, "The call was cancelled."))

        threading.Thread(target=wait).start()

    near, far = pipes()
    Peer(far, patient)
    pending = Peer(near).request("slow")
    pending.cancel()
    with pytest.raises(RpcError) as given_up:
        pending.result(5)
    assert given_up.value.code == Code.CANCELLED == -32800


def test_close_fails_every_waiting_call_and_cancels_every_call_served(
    pipes: Pipes,
) -> None:
    held: list[Call] = []
    arrived, closed = threading.Event(), threading.Event()

    def hold(call: Call) -> None:
        held.append(call)
        arrived.set()

    near, far = pipes()
    server = Peer(far, hold, on_close=closed.set)
    client = Peer(near)
    pending = client.request("slow")
    assert arrived.wait(5)
    client.close()
    with pytest.raises(Closed):
        pending.result(5)
    assert server.wait(5)
    assert closed.is_set()
    assert held[0].cancelled.is_set()
    with pytest.raises(Closed):
        client.call("a")
    with pytest.raises(Closed):
        client.notify("a")
    held[0].answer("nobody hears this")


def test_a_frame_of_a_length_no_frame_has_closes_the_session(pipes: Pipes) -> None:
    near, far = pipes()
    peer = Peer(near)
    pending = peer.request("a")
    far.sendall(struct.pack(">I", LONGEST + 1))
    assert peer.wait(5)
    with pytest.raises(Closed):
        pending.result(5)


def test_a_result_too_large_to_carry_is_answered_413(
    pipes: Pipes, received: Received
) -> None:
    near, far = pipes()
    Peer(near, lambda call: call.answer("x" * LONGEST))
    far.sendall(encode({"jsonrpc": "2.0", "id": 1, "method": "a"}))
    assert received(far) == {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {
            "code": 413,
            "message": "That is more than an answer here may carry.",
        },
    }


def test_a_call_too_large_to_carry_is_not_sent(pipes: Pipes) -> None:
    near, _ = pipes()
    with pytest.raises(RpcError) as refused:
        Peer(near).request("a", {"x": "x" * LONGEST})
    assert refused.value.code == 413


def test_a_notification_too_large_to_carry_is_dropped(
    pipes: Pipes, received: Received
) -> None:
    near, far = pipes()
    peer = Peer(near)
    peer.notify("big", {"x": "x" * LONGEST})
    peer.notify("small")
    assert received(far)["method"] == "small"


def test_an_error_answer_out_of_shape_is_still_an_error(
    pipes: Pipes, received: Received
) -> None:
    near, far = pipes()
    pending = Peer(near).request("a")
    received(far)
    far.sendall(encode({"jsonrpc": "2.0", "id": pending.id, "error": "bad"}))
    with pytest.raises(RpcError) as refused:
        pending.result(5)
    assert refused.value.code == Code.INTERNAL_ERROR


def test_the_far_end_closing_closes_the_session(pipes: Pipes) -> None:
    near, far = pipes()
    peer = Peer(near)
    far.close()
    assert peer.wait(5)
    assert peer.closed


def test_a_pipe_that_fails_is_why_the_calls_waiting_closed(pipes: Pipes) -> None:
    near, _ = pipes()
    reading = threading.Event()

    class Failing:
        """A pipe whose carrier ends badly, saying why, once a call waits on it."""

        def recv(self, size: int) -> bytes:
            del size
            reading.wait(5)
            raise ConnectionError("ssh: Could not resolve hostname box")

        sendall = near.sendall
        close = near.close

    peer = Peer(Failing())
    pending = peer.request("a")
    reading.set()
    with pytest.raises(Closed) as closed:
        pending.result(5)
    assert str(closed.value.__cause__) == "ssh: Could not resolve hostname box"
    # A call made once it has closed is told the same.
    assert peer.wait(5)
    with pytest.raises(Closed) as later:
        peer.request("b")
    assert str(later.value.__cause__) == "ssh: Could not resolve hostname box"


def test_a_pipe_that_failed_is_why_it_takes_no_more() -> None:
    writing, closed = threading.Event(), threading.Event()

    class Failing:
        """A pipe whose carrier ends badly while a frame is being written to it."""

        def recv(self, size: int) -> bytes:
            del size
            writing.wait(5)
            raise ConnectionError("ssh: Could not resolve hostname box")

        def sendall(self, data: bytes) -> None:
            del data
            writing.set()
            closed.wait(5)
            raise BrokenPipeError(errno.EPIPE, "Broken pipe")

        def close(self) -> None:
            closed.set()

    peer = Peer(Failing())
    with pytest.raises(Closed) as refused:
        peer.request("a")
    assert str(refused.value.__cause__) == "ssh: Could not resolve hostname box"


def test_closing_is_told_once_to_each_callback_and_at_once_after_it(
    pipes: Pipes,
) -> None:
    near, _ = pipes()
    told: list[str] = []
    peer = Peer(near, on_close=lambda: told.append("on_close"))
    peer.closing(lambda: told.append("first"))
    peer.close()
    peer.close()
    peer.closing(lambda: told.append("late"))
    assert told == ["on_close", "first", "late"]


def test_json_written_is_utf8_without_escapes(pipes: Pipes) -> None:
    near, far = pipes()
    Peer(near).notify("x", {"name": "日本"})
    data = far.recv(1 << 16)
    assert json.loads(data[4:]) == {
        "jsonrpc": "2.0",
        "method": "x",
        "params": {"name": "日本"},
    }
    assert "日本".encode() in data


def test_nan_is_read_as_no_json_and_written_as_its_text(
    pipes: Pipes, received: Received
) -> None:
    near, far = pipes()
    Peer(near, lambda call: call.answer(float("nan")))
    far.sendall(
        frame(b'{"jsonrpc": "2.0", "id": 1, "method": "a", "params": {"n": NaN}}')
    )
    assert received(far)["error"]["code"] == -32700
    far.sendall(encode({"jsonrpc": "2.0", "id": 2, "method": "a"}))
    assert received(far)["result"] == "NaN"


def test_a_result_json_cannot_hold_is_still_answered(
    pipes: Pipes, received: Received
) -> None:
    near, far = pipes()
    Peer(near, lambda call: call.answer({(1, 2): "tuple key"}))
    far.sendall(encode({"jsonrpc": "2.0", "id": 1, "method": "a"}))
    answer = received(far)
    assert (answer["id"], answer["error"]["code"]) == (1, -32603)


def test_frames_whole_ahead_of_a_bad_length_are_still_handed_out(
    pipes: Pipes,
) -> None:
    served: list[str] = []
    near, far = pipes()
    peer = Peer(near, lambda call: served.append(call.method))
    far.sendall(encode({"jsonrpc": "2.0", "method": "first"}) + struct.pack(">I", 0))
    assert peer.wait(5)
    assert served == ["first"]
