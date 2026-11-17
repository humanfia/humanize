"""Methods served by name, held to the OpenRPC document (Section 6.6 and 6.11 of wire.md)."""

import threading
from collections.abc import Callable
from typing import Any

import pytest

from hmz.rpc import Call, Code, Dispatcher, Peer, Pipe, RpcError, document

type Pipes = Callable[[], tuple[Pipe, Pipe]]


CLIENT = {"name": "n", "kind": "tui"}
HELLO = {"protocol": "3.0.0", "client": CLIENT}


def greeting() -> Dispatcher:
    """The protocol's dispatcher, answering `session.hello` with "hi"."""
    dispatcher = Dispatcher()
    dispatcher.register("session.hello", lambda call: "hi")
    return dispatcher


def served(pipes: Pipes, dispatcher: Dispatcher, *, greet: bool = True) -> Peer:
    near, far = pipes()
    Peer(far, dispatcher)
    peer = Peer(near)
    if greet:
        assert peer.call("session.hello", HELLO, timeout=5) == "hi"
    return peer


def refusal(peer: Peer, method: str, params: dict[str, Any] | None = None) -> RpcError:
    with pytest.raises(RpcError) as refused:
        peer.call(method, params, timeout=5)
    return refused.value


def test_rpc_discover_answers_the_document(pipes: Pipes) -> None:
    assert served(pipes, greeting()).call("rpc.discover", timeout=5) == document()


def test_a_method_with_no_handler_is_no_method(pipes: Pipes) -> None:
    peer = served(pipes, greeting())
    for method in ("epic.status", "no.such", "epic.event", "session.cancel"):
        error = refusal(peer, method)
        assert (error.code, error.message) == (
            Code.METHOD_NOT_FOUND,
            f"There is no method {method}.",
        )


def test_only_what_the_document_lists_may_be_served() -> None:
    dispatcher = Dispatcher()
    with pytest.raises(ValueError, match=r"no\.such"):
        dispatcher.register("no.such", lambda call: None)
    dispatcher.register("epic.status", lambda call: None)
    dispatcher.register("epic.event", lambda call: None)


def test_a_handler_answers_with_what_it_gives_back(pipes: Pipes) -> None:
    dispatcher = greeting()
    dispatcher.register("paths.list", lambda call: {"got": call.params})
    peer = served(pipes, dispatcher)
    assert peer.call("paths.list", timeout=5) == {"got": {}}


@pytest.fixture
def hello(pipes: Pipes) -> Peer:
    return served(pipes, greeting(), greet=False)


def test_a_parameter_the_method_does_not_take_is_refused(hello: Peer) -> None:
    client = {"name": "n", "kind": "tui"}
    error = refusal(
        hello, "session.hello", {"protocol": "3.0.0", "client": client, "x": 1, "y": 2}
    )
    assert (error.code, error.message) == (-32602, "session.hello takes no x, y.")


def test_a_required_parameter_absent_is_refused(hello: Peer) -> None:
    error = refusal(hello, "session.hello", {"protocol": "3.0.0"})
    assert (error.code, error.message) == (-32602, "session.hello needs client.")


def test_a_parameter_of_another_type_is_refused(hello: Peer) -> None:
    client = {"name": "n", "kind": "tui"}
    error = refusal(hello, "session.hello", {"protocol": 3, "client": client})
    assert (error.code, error.message) == (
        -32602,
        "session.hello takes protocol as string.",
    )
    assert (
        hello.call("session.hello", {"protocol": "3", "client": client}, timeout=5)
        == "hi"
    )


@pytest.mark.parametrize(
    ("method", "params", "message"),
    [
        # Through a `$ref` to a component's schema.
        ("epic.status", {"sub": 1}, "epic.status takes sub as string."),
        (
            "files.read",
            {"handle": "h", "offset": True, "length": 1},
            "files.read takes offset as integer.",
        ),
    ],
)
def test_types_are_read_through_refs_and_lists(
    pipes: Pipes, method: str, params: dict[str, Any], message: str
) -> None:
    dispatcher = greeting()
    dispatcher.register(method, lambda call: "ok")
    peer = served(pipes, dispatcher)
    error = refusal(peer, method, params)
    assert (error.code, error.message) == (-32602, message)


def test_types_named_as_a_list_admit_each(pipes: Pipes) -> None:
    told: dict[str, Any] = {
        "openrpc": "1.3.2",
        "info": {"title": "t", "version": "1"},
        "methods": [
            {
                "name": "t.m",
                "params": [{"name": "v", "schema": {"type": ["string", "null"]}}],
                "result": {"name": "r", "schema": {}},
            }
        ],
    }
    dispatcher = Dispatcher(told)
    dispatcher.register("t.m", lambda call: call.params["v"])
    peer = served(pipes, dispatcher, greet=False)
    assert peer.call("t.m", {"v": None}, timeout=5) is None
    assert peer.call("t.m", {"v": "s"}, timeout=5) == "s"
    error = refusal(peer, "t.m", {"v": 1})
    assert error.message == "t.m takes v as string or null."


def test_a_handlers_refusal_is_the_answer(pipes: Pipes) -> None:
    def refuse(call: Call) -> None:
        raise RpcError(Code.NOT_FOUND, "There is no file h.")

    dispatcher = greeting()
    dispatcher.register("files.close", refuse)
    error = refusal(served(pipes, dispatcher), "files.close", {"handle": "h"})
    assert (error.code, error.message) == (404, "There is no file h.")


def test_a_failure_nobody_anticipated_is_answered_32603(pipes: Pipes) -> None:
    def broken(call: Call) -> None:
        raise ZeroDivisionError

    dispatcher = greeting()
    dispatcher.register("files.close", broken)
    error = refusal(served(pipes, dispatcher), "files.close", {"handle": "h"})
    assert (error.code, error.message) == (
        -32603,
        "Something went wrong here: ZeroDivisionError",
    )


def test_one_call_waits_on_no_other(pipes: Pipes) -> None:
    release = threading.Event()

    def slow(call: Call) -> str:
        release.wait(5)
        return "slow"

    dispatcher = greeting()
    dispatcher.register("files.close", slow)
    dispatcher.register("paths.list", lambda call: "fast")
    peer = served(pipes, dispatcher)
    pending = peer.request("files.close", {"handle": "h"})
    assert peer.call("paths.list", timeout=5) == "fast"
    release.set()
    assert pending.result(5) == "slow"


def test_a_cancelled_call_is_answered_cancelled_by_its_handler(pipes: Pipes) -> None:
    def patient(call: Call) -> str:
        if call.cancelled.wait(5):
            raise RpcError(Code.CANCELLED, "The call was cancelled.")
        return "done"

    dispatcher = greeting()
    dispatcher.register("files.close", patient)
    pending = served(pipes, dispatcher).request("files.close", {"handle": "h"})
    pending.cancel()
    with pytest.raises(RpcError) as given_up:
        pending.result(5)
    assert given_up.value.code == -32800


def test_a_notification_goes_to_its_handler_and_nothing_answers(pipes: Pipes) -> None:
    told: list[dict[str, Any]] = []
    arrived = threading.Event()

    def event(call: Call) -> None:
        told.append(call.params)
        arrived.set()

    dispatcher = Dispatcher()
    dispatcher.register("notices.event", event)
    near, far = pipes()
    Peer(far, dispatcher)
    peer = Peer(near)
    peer.notify("unknown.event", {"a": 1})
    peer.notify("notices.event", {"sub": "s", "unknown": 1})
    assert arrived.wait(5)
    assert told == [{"sub": "s", "unknown": 1}]


def test_the_first_call_is_session_hello(pipes: Pipes) -> None:
    peer = served(pipes, greeting(), greet=False)
    error = refusal(peer, "rpc.discover")
    assert (error.code, error.message) == (-32600, "A client says session.hello first.")
    assert peer.call("session.hello", HELLO, timeout=5) == "hi"
    error = refusal(peer, "session.hello", HELLO)
    assert (error.code, error.message) == (
        -32600,
        "This session has already said hello.",
    )
    assert peer.call("rpc.discover", timeout=5)["openrpc"] == "1.3.2"


def test_each_session_says_hello_for_itself(pipes: Pipes) -> None:
    dispatcher = greeting()
    served(pipes, dispatcher)
    other = served(pipes, dispatcher, greet=False)
    assert refusal(other, "rpc.discover").code == -32600


def test_a_float_is_not_an_integer(pipes: Pipes) -> None:
    dispatcher = greeting()
    dispatcher.register("files.read", lambda call: "ok")
    peer = served(pipes, dispatcher)
    error = refusal(peer, "files.read", {"handle": "h", "offset": 0.0, "length": 1})
    assert error.message == "files.read takes offset as integer."


def test_calls_naming_one_sub_are_carried_out_in_order(pipes: Pipes) -> None:
    done: list[str] = []
    first_in, release = threading.Event(), threading.Event()

    def held(call: Call) -> str:
        if call.method == "epic.status" and call.params["sub"] == "a":
            first_in.set()
            release.wait(5)
        done.append(f"{call.method} {call.params['sub']}")
        return "ok"

    dispatcher = greeting()
    for method in ("epic.status", "epic.detach", "epic.aside", "env.git.status"):
        dispatcher.register(method, held)
    peer = served(pipes, dispatcher)
    first = peer.request("epic.status", {"sub": "a"})
    assert first_in.wait(5)
    second = peer.request("epic.detach", {"sub": "a"})
    # Another subscription, and `epic.aside` and a call to an environment on this one, wait on
    # none of it.
    assert peer.call("epic.status", {"sub": "b"}, timeout=5) == "ok"
    assert peer.call("epic.aside", {"sub": "a"}, timeout=5) == "ok"
    assert peer.call("env.git.status", {"sub": "a", "env": "1:w"}, timeout=5) == "ok"
    assert "epic.detach a" not in done
    release.set()
    assert first.result(5) == second.result(5) == "ok"
    assert done == [
        "epic.status b",
        "epic.aside a",
        "env.git.status a",
        "epic.status a",
        "epic.detach a",
    ]
