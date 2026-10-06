"""`hmz internal hook`: one call of a CLI's hook table, carried to a flow and back."""

from __future__ import annotations

import pytest

from hmz.cli.hook import hook
from tests.unit.cli.sockets_u1 import Socket, sockets, stdin


@pytest.mark.parametrize(
    ("said", "carried"),
    [
        (
            b'{\n  "tool": "Bash",\n  "input": {"cmd": "ls"}\n}\n',
            b'{"tool":"Bash","input":{"cmd":"ls"}}\n',
        ),
        (b"", b"{}\n"),
        (b"not\n  json  at\nall", b"not json at all\n"),
    ],
)
def test_hook_carries_what_the_cli_said_as_one_line(
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
    said: bytes,
    carried: bytes,
) -> None:
    made = Socket()
    made.answer = b'{"decision":"block"}\n'
    sockets(monkeypatch, made)
    stdin(monkeypatch, said)
    assert hook(["--at", "/flow.sock"]) == 0
    assert made.at == "/flow.sock"
    assert made.written.getvalue() == carried
    assert capsysbinary.readouterr().out == b'{"decision":"block"}\n'
    assert made.closed


def test_hook_with_a_flow_that_says_nothing_says_nothing(
    monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    sockets(monkeypatch, Socket())
    stdin(monkeypatch, b"{}")
    assert hook(["--at", "/flow.sock"]) == 0
    assert capsysbinary.readouterr().out == b""


def test_hook_with_no_flow_there_lets_the_tool_go_ahead(
    monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    made = Socket()
    made.refuses = FileNotFoundError(2, "No such file or directory")
    sockets(monkeypatch, made)
    stdin(monkeypatch, b"{}")
    assert hook(["--at", "/gone.sock"]) == 0
    captured = capsysbinary.readouterr()
    assert captured.out == b""
    assert captured.err.startswith(b"hmz internal hook: /gone.sock: ")
    assert made.closed


@pytest.mark.parametrize("argv", [[], ["--at"], ["--at", "/s", "--bogus"]])
def test_hook_with_a_line_it_cannot_read_never_exits_two(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert hook(argv) == 1
    assert "usage: hmz internal hook" in capsys.readouterr().err


def test_hook_help_exits_as_help_does(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        hook(["--help"])
    assert raised.value.code == 0
    assert "--at SOCKET" in capsys.readouterr().out
