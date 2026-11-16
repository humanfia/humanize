"""`session.hello` and the protocol versions a daemon admits (Section 6.5 of wire.md)."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from hmz.rpc import PROTOCOL, Call, Code, Dispatcher, Peer, Pipe, RpcError, admit, hello


@pytest.mark.parametrize("theirs", [PROTOCOL, "3.0.9", "3.0.0-rc.1"])
def test_a_client_of_the_same_major_and_no_newer_minor_is_admitted(theirs: str) -> None:
    admit(theirs)


def test_an_older_minor_is_admitted() -> None:
    admit("3.1.0", ours="3.2.0")


def test_an_older_client_is_told_a_newer_humanize_reads_it() -> None:
    with pytest.raises(RpcError) as refused:
        admit("2.9.0")
    assert refused.value.code == Code.PROTOCOL_MISMATCH == 426
    assert refused.value.message == (
        "held for frontends by a newer Humanize; `hmz` of it reads it"
    )
    assert refused.value.data == {"protocol": PROTOCOL}


@pytest.mark.parametrize("theirs", ["3.1.0", "4.0.0"])
def test_a_newer_client_is_told_to_stop_the_older_daemon(theirs: str) -> None:
    with pytest.raises(RpcError) as refused:
        admit(theirs, pid=4242)
    assert refused.value.code == 426
    assert refused.value.message == (
        "the runs on this machine are held by an older Humanize (pid 4242); "
        "stop it with that version"
    )
    assert refused.value.data == {"protocol": PROTOCOL}


def test_what_is_not_a_version_is_not_a_parameter_the_method_takes() -> None:
    with pytest.raises(RpcError) as refused:
        admit("three")
    assert refused.value.code == Code.INVALID_PARAMS


@pytest.fixture
def daemon(pipes: Callable[[], tuple[Pipe, Pipe]]) -> Iterator[tuple[Peer, list[Any]]]:
    seen: list[Any] = []

    def said_hello(call: Call) -> dict[str, Any]:
        seen.append(call.params)
        admit(call.params["protocol"])
        return {"daemon_id": "d", "protocol": PROTOCOL}

    dispatcher = Dispatcher()
    dispatcher.register("session.hello", said_hello)
    near, far = pipes()
    Peer(far, dispatcher)
    client = Peer(near)
    yield client, seen
    client.close()


def test_hello_says_the_protocol_and_the_client(
    daemon: tuple[Peer, list[Any]],
) -> None:
    client, seen = daemon
    answer = hello(client, "laptop", "tui", timeout=5)
    assert answer == {"daemon_id": "d", "protocol": PROTOCOL}
    assert seen == [{"protocol": PROTOCOL, "client": {"name": "laptop", "kind": "tui"}}]


def test_hello_from_another_major_is_refused_426(
    daemon: tuple[Peer, list[Any]],
) -> None:
    client, _ = daemon
    with pytest.raises(RpcError) as refused:
        hello(client, "laptop", "cli", protocol="4.0.0", timeout=5)
    assert refused.value.code == 426
    assert refused.value.data == {"protocol": PROTOCOL}
