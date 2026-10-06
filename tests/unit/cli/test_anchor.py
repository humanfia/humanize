"""`hmz internal anchor`: an agent run here with its work landing on another machine.

Every part of the session is coganchor's, and mocked: what is here is which of the three
lines was asked for, what each makes of its arguments, and the status each exits with.
"""

from __future__ import annotations

import argparse
import logging
from unittest import mock

import pytest

import hmz.coganchor.anchor
import hmz.coganchor.argv
import hmz.coganchor.rendezvous
import hmz.coganchor.serve.exports
import hmz.coganchor.serve.listener
import hmz.coganchor.serve.server
from hmz.cli.anchor import anchor
from hmz.coganchor.anchor import NotInstalled
from hmz.coganchor.proto import ProtocolError


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`logging.basicConfig`, so that no line here configures the suite's own logging."""
    configures = mock.Mock()
    monkeypatch.setattr(logging, "basicConfig", configures)
    monkeypatch.delenv("HUMANIZE_LOG", raising=False)
    return configures


def _level(logs: mock.Mock) -> str:
    return logs.call_args.kwargs["level"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hmz internal anchor")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--log-level", default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch, logs: mock.Mock) -> mock.Mock:
    """The line and session coganchor reads, mocked: settings read, connect and check."""
    held = mock.Mock()
    held.settings.return_value = "config"
    held.connect.return_value = 0
    monkeypatch.setattr(hmz.coganchor.argv, "parser", _parser)
    monkeypatch.setattr(hmz.coganchor.argv, "settings", held.settings)
    monkeypatch.setattr(hmz.coganchor.anchor, "connect", held.connect)
    monkeypatch.setattr(hmz.coganchor.anchor, "check", held.check)
    del logs
    return held


def test_anchor_runs_the_agent_and_exits_as_it_does(session: mock.Mock) -> None:
    session.connect.return_value = 3
    assert anchor(["claude", "-p", "hi"]) == 3
    session.connect.assert_called_once_with(["claude", "-p", "hi"], "config")
    (args,) = session.settings.call_args.args
    assert args.command == ["claude", "-p", "hi"]


def test_anchor_without_an_agent_is_refused(
    session: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        anchor([])
    assert raised.value.code == 2
    assert "no agent given" in capsys.readouterr().err
    session.connect.assert_not_called()


def test_settings_it_cannot_run_under_are_a_bad_line(
    session: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    session.settings.side_effect = ValueError("target is not a target")
    with pytest.raises(SystemExit) as raised:
        anchor(["claude"])
    assert raised.value.code == 2
    assert "target is not a target" in capsys.readouterr().err


def test_check_says_what_the_target_is(
    session: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    session.check.return_value = {
        "target": "ssh://box",
        "hostname": "box",
        "python": "3.12",
        "pid": 7,
        "exports": [{"virtual": "/w", "real": "/home/w"}],
        "workspace": "/w",
        "entries": 4,
    }
    assert anchor(["--check"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "target      ssh://box",
        "hostname    box",
        "python      3.12 (pid 7)",
        "export      /w -> /home/w",
        "workspace   /w (4 entries)",
    ]
    session.connect.assert_not_called()


@pytest.mark.parametrize(
    ("failure", "status", "said"),
    [
        (
            NotInstalled(2, "claude is not installed there"),
            127,
            "claude is not installed there",
        ),
        (KeyboardInterrupt(), 130, ""),
        (ConnectionError("reset"), 1, "reset"),
        (ProtocolError("garbled"), 1, "garbled"),
        (OSError("no ssh"), 1, "no ssh"),
        (RuntimeError("cannot intercept syscalls"), 1, "cannot intercept syscalls"),
        (ValueError("bad export"), 1, "bad export"),
    ],
)
def test_a_session_that_did_not_run_exits_with_its_own_status(
    session: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    failure: BaseException,
    status: int,
    said: str,
) -> None:
    session.connect.side_effect = failure
    assert anchor(["claude"]) == status
    err = capsys.readouterr().err
    assert (f"hmz: {said}\n" == err) if said else (err == "")


@pytest.mark.parametrize(
    ("argv", "environ", "level"),
    [
        (["--log-level", "debug", "claude"], "", "DEBUG"),
        (["claude"], "info", "INFO"),
        (["claude"], "  Error ", "ERROR"),
        (["claude"], "", "WARNING"),
    ],
)
def test_the_log_level_is_the_lines_then_the_environments_then_warning(
    session: mock.Mock,
    logs: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    environ: str,
    level: str,
) -> None:
    monkeypatch.setenv("HUMANIZE_LOG", environ)
    anchor(argv)
    assert _level(logs) == level
    del session


def test_a_log_level_nobody_has_is_said_to_be_ignored(
    session: mock.Mock,
    logs: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("HUMANIZE_LOG", "loud")
    anchor(["claude"])
    assert _level(logs) == "WARNING"
    assert "ignoring HUMANIZE_LOG='loud'" in capsys.readouterr().err
    del session


@pytest.fixture
def serving(monkeypatch: pytest.MonkeyPatch, logs: mock.Mock) -> mock.Mock:
    """What `serve` reaches in coganchor, mocked."""
    held = mock.Mock()
    held.parse.return_value = "table"
    monkeypatch.setattr(hmz.coganchor.serve.exports.ExportTable, "parse", held.parse)
    monkeypatch.setattr(hmz.coganchor.serve.server, "Server", held.Server)
    monkeypatch.setattr(
        hmz.coganchor.serve.listener, "serve_forever", held.serve_forever
    )
    monkeypatch.setattr(hmz.coganchor.rendezvous, "dial", held.dial)
    monkeypatch.setattr(hmz.coganchor.rendezvous.Meeting, "parse", held.meeting)
    monkeypatch.delenv("HUMANIZE_TOKEN", raising=False)
    del logs
    return held


@pytest.mark.parametrize(
    ("listen", "token", "host", "port"),
    [
        ("8022", None, "127.0.0.1", 8022),
        ("localhost:1", None, "localhost", 1),
        ("[::1]:65535", None, "::1", 65535),
        (":0", None, "127.0.0.1", 0),
        ("0.0.0.0:8022", "secret", "0.0.0.0", 8022),  # noqa: S104
    ],
)
def test_serve_listens_where_it_is_told(
    serving: mock.Mock, listen: str, token: str | None, host: str, port: int
) -> None:
    argv = ["serve", "--export", "/w", "--listen", listen]
    assert anchor(argv + (["--token", token] if token else [])) == 0
    serving.parse.assert_called_once_with(["/w"])
    serving.serve_forever.assert_called_once_with(host, port, "table", token)


def test_serve_takes_its_token_from_the_environment(
    serving: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_TOKEN", "from-env")
    assert anchor(["serve", "--export", "/w", "--listen", "10.0.0.1:1"]) == 0
    serving.serve_forever.assert_called_once_with("10.0.0.1", 1, "table", "from-env")


@pytest.mark.parametrize("listen", ["port", "70000", "host:", "-1", "1.2.3.4:x"])
def test_serve_refuses_an_address_that_is_not_one(
    serving: mock.Mock, listen: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert anchor(["serve", "--export", "/w", f"--listen={listen}"]) == 2
    assert "malformed listen address" in capsys.readouterr().err
    serving.serve_forever.assert_not_called()


def test_serve_refuses_to_listen_off_this_machine_without_a_token(
    serving: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert anchor(["serve", "--export", "/w", "--listen", "0.0.0.0:1"]) == 2
    assert "without --token" in capsys.readouterr().err
    serving.serve_forever.assert_not_called()


def test_serve_that_cannot_listen_says_so(
    serving: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    serving.serve_forever.side_effect = OSError(48, "Address already in use")
    assert anchor(["serve", "--export", "/w", "--listen", "1"]) == 1
    assert capsys.readouterr().err == (
        "hmz: cannot listen on 127.0.0.1:1: Address already in use\n"
    )


def test_serve_refuses_an_export_it_cannot_read(
    serving: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    serving.parse.side_effect = ValueError("not absolute")
    assert anchor(["serve", "--export", "w", "--listen", "1"]) == 2
    assert capsys.readouterr().err == "hmz: not absolute\n"


@pytest.mark.parametrize(
    "argv",
    [
        ["serve", "--listen", "1"],
        ["serve", "--export", "/w"],
        ["serve", "--export", "/w", "--stdio", "--listen", "1"],
        ["serve", "--export", "/w", "--listen", "1", "--log-level", "loud"],
    ],
)
def test_serve_refuses_a_line_missing_or_doubling_a_part(
    serving: mock.Mock, argv: list[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        anchor(argv)
    assert raised.value.code == 2
    serving.serve_forever.assert_not_called()


def test_serve_through_a_rendezvous_serves_the_one_socket_it_dials(
    serving: mock.Mock,
) -> None:
    assert anchor(["serve", "--export", "/w", "--peer", "t@h:1", "--token", "k"]) == 0
    serving.meeting.assert_called_once_with("t@h:1")
    serving.dial.assert_called_once_with(
        serving.meeting.return_value, hmz.coganchor.rendezvous.SERVE
    )
    ((channel, table, token), _) = serving.Server.call_args
    assert (table, token) == ("table", "k")
    assert channel is not None
    serving.Server.return_value.serve.assert_called_once_with()


@pytest.mark.parametrize("failure", [OSError("unreachable"), ValueError("bad ticket")])
def test_serve_through_a_rendezvous_that_cannot_be_dialled_says_so(
    serving: mock.Mock, failure: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    serving.dial.side_effect = failure
    assert anchor(["serve", "--export", "/w", "--peer", "t@h:1"]) == 1
    assert capsys.readouterr().err == f"hmz: {failure}\n"
    serving.Server.assert_not_called()


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch, logs: mock.Mock) -> mock.Mock:
    """`hmz.coganchor.rendezvous.Broker`, mocked to bind where it is asked."""
    made = mock.Mock()
    made.return_value.start.return_value = ("0.0.0.0:4000", "1.2.3.4:4000")
    monkeypatch.setattr(hmz.coganchor.rendezvous, "Broker", made)
    del logs
    return made


def test_rendezvous_listens_everywhere_and_says_where(
    broker: mock.Mock, logs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert anchor(["rendezvous"]) == 0
    broker.assert_called_once_with(
        "0.0.0.0",  # noqa: S104
        0,
        punching=hmz.coganchor.rendezvous.PUNCHING,
    )
    broker.return_value.serve_forever.assert_called_once_with()
    assert capsys.readouterr().err == (
        "hmz internal anchor rendezvous listening 0.0.0.0:4000 1.2.3.4:4000\n"
    )
    assert _level(logs) == "INFO"


def test_rendezvous_takes_its_address_and_patience(broker: mock.Mock) -> None:
    assert anchor(["rendezvous", "--listen", "9000", "--punching", "1.5"]) == 0
    broker.assert_called_once_with("0.0.0.0", 9000, punching=1.5)  # noqa: S104


def test_rendezvous_refuses_an_address_that_is_not_one(
    broker: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert anchor(["rendezvous", "--listen", "nope"]) == 2
    assert "malformed listen address 'nope'" in capsys.readouterr().err
    broker.assert_not_called()


def test_rendezvous_that_cannot_listen_says_so(
    broker: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    broker.return_value.start.side_effect = OSError(13, "Permission denied")
    assert anchor(["rendezvous", "--listen", "h:80"]) == 1
    assert capsys.readouterr().err == "hmz: cannot listen on h:80: Permission denied\n"
    broker.return_value.serve_forever.assert_not_called()
