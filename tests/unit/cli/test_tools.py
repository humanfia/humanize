"""`hmz internal tools`: a CLI's tool protocol, relayed line by line to a flow."""

from __future__ import annotations

import pytest

from hmz.cli.tools import tools
from tests.unit.cli.sockets_u1 import Socket, sockets, stdin


def test_tools_relays_both_ways_until_an_end_goes(
    monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    made = Socket()
    made.answer = b'{"id":1,"result":{}}\n{"id":2,"result":{}}\n'
    sockets(monkeypatch, made)
    stdin(monkeypatch, b'{"id":1,"method":"a"}\n{"id":2,"method":"b"}\n')
    assert tools(["--at", "/flow.sock"]) == 0
    assert made.at == "/flow.sock"
    assert capsysbinary.readouterr().out == made.answer
    assert made.shut.wait(5)
    assert made.written.getvalue() == b'{"id":1,"method":"a"}\n{"id":2,"method":"b"}\n'
    assert made.closed


def test_tools_with_no_flow_there_says_the_tools_are_gone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    made = Socket()
    made.refuses = ConnectionRefusedError(61, "Connection refused")
    sockets(monkeypatch, made)
    assert tools(["--at", "/gone.sock"]) == 1
    assert capsys.readouterr().err.startswith("hmz internal tools: /gone.sock: ")
    assert made.closed


@pytest.mark.parametrize("argv", [[], ["--bogus"]])
def test_tools_needs_the_socket(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        tools(argv)
    assert raised.value.code == 2
    assert "usage: hmz internal tools" in capsys.readouterr().err
