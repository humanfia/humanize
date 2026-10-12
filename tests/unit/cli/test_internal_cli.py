"""`hmz internal cli`: one run of a flow's command line, relayed to the flow and answered."""

from __future__ import annotations

import json

import pytest

from hmz.cli.cli import cli
from tests.unit.cli.sockets_u1 import Socket, sockets


def test_cli_asks_the_flow_and_prints_and_exits_as_it_says(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    made = Socket()
    made.answer = b'{"code": 3, "out": "said\\n", "err": "warned\\n"}\n'
    sockets(monkeypatch, made)
    argv = ["--at", "/flow.sock", "--name", "tix", "--", "file", "--", "--help"]
    assert cli(argv) == 3
    assert made.at == "/flow.sock"
    assert json.loads(made.written.getvalue()) == {
        "name": "tix",
        "argv": ["file", "--", "--help"],
    }
    assert made.shut.is_set()
    assert made.closed
    assert capsys.readouterr() == ("said\n", "warned\n")


def test_cli_with_no_flow_there_is_a_program_that_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    made = Socket()
    made.refuses = ConnectionRefusedError(61, "Connection refused")
    sockets(monkeypatch, made)
    assert cli(["--at", "/gone.sock", "--name", "tix", "--", "file"]) == 1
    assert capsys.readouterr().err.startswith("tix: the flow serving it has ended")
    assert made.closed


def test_cli_with_no_answer_is_a_program_that_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sockets(monkeypatch, Socket())
    assert cli(["--at", "/flow.sock", "--name", "tix"]) == 1
    assert "gave no answer" in capsys.readouterr().err


def test_cli_needs_the_socket_and_the_name(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli(["--", "--help"])
    assert raised.value.code == 2
    assert "usage: hmz internal cli" in capsys.readouterr().err
