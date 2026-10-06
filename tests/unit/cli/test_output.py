"""`hmz.cli.output`: who is reading a run, and what each of them is shown."""

from __future__ import annotations

import io
import json
import sys
from typing import Any
from unittest import mock

import pytest

import hmz.coganchor.prices
import hmz.runtime.doing.hosting
from hmz.cli.output import Out, Shown, colours, terminal

_SAID = "⏺" if sys.platform == "darwin" else "●"


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


class _Closed:
    def isatty(self) -> bool:
        raise ValueError("I/O operation on closed file")


@pytest.mark.parametrize(
    ("stream", "expected"),
    [(_Tty(), True), (io.StringIO(), False), (_Closed(), False), (object(), False)],
)
def test_terminal_is_whether_a_terminal_reads_the_stream(
    stream: Any, expected: bool
) -> None:
    assert terminal(stream) is expected


def test_terminal_defaults_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", _Tty())
    assert terminal() is True


@pytest.fixture
def plain_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No variable saying anything about colour."""
    for name in ("NO_COLOR", "FORCE_COLOR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")


@pytest.mark.parametrize(
    ("environ", "tty", "expected"),
    [
        ({}, True, True),
        ({}, False, False),
        ({"NO_COLOR": "1"}, True, False),
        ({"NO_COLOR": "1", "FORCE_COLOR": "1"}, True, False),
        ({"TERM": "dumb"}, True, False),
        ({"TERM": "dumb", "FORCE_COLOR": "1"}, False, False),
        ({"FORCE_COLOR": "1"}, False, True),
        ({"FORCE_COLOR": "0"}, False, False),
        ({"NO_COLOR": ""}, True, True),
    ],
)
def test_colours_follows_the_three_conventions(
    plain_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    environ: dict[str, str],
    tty: bool,
    expected: bool,
) -> None:
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    assert colours(_Tty() if tty else io.StringIO()) is expected


@pytest.fixture
def plain(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run written plainly, wherever it is written."""
    monkeypatch.setenv("NO_COLOR", "1")


def test_record_writes_one_object_a_line(
    plain: None, capsys: pytest.CaptureFixture[str]
) -> None:
    out = Out(as_json=True)
    assert out.as_json
    out.record(kind="text", text="héllo", at=object())
    out.record(n=2)
    lines = capsys.readouterr().out.splitlines()
    assert json.loads(lines[0])["text"] == "héllo"
    assert "héllo" in lines[0]
    assert json.loads(lines[1]) == {"n": 2}


def test_json_sends_whatever_else_is_printed_to_stderr(
    plain: None, capsys: pytest.CaptureFixture[str]
) -> None:
    with Out(as_json=True) as out:
        sys.stdout.write("stray\n")
        out.record(n=1)
    sys.stdout.write("after\n")
    captured = capsys.readouterr()
    assert captured.out == '{"n": 1}\nafter\n'
    assert captured.err == "stray\n"


def test_a_person_reading_keeps_stdout(
    plain: None, capsys: pytest.CaptureFixture[str]
) -> None:
    with Out() as out:
        assert not out.as_json
        sys.stdout.write("printed\n")
        out.answer("the answer")
        out.aside("about the run")
    captured = capsys.readouterr()
    assert captured.out == "printed\nthe answer\n"
    assert captured.err == "about the run\n"


def test_a_plain_line_is_its_pieces_without_their_styles(
    plain: None, capsys: pytest.CaptureFixture[str]
) -> None:
    Out().line(("a ", "dim"), ("b", "bold red"), ("", ""))
    assert capsys.readouterr().err == "a b\n"


def test_a_coloured_line_is_drawn_on_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("FORCE_COLOR", "1")
    Out().line(("hello ", "green"), ("there", ""))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hello" in captured.err
    assert "there" in captured.err
    assert "\x1b[" in captured.err


def test_no_clock_is_drawn_where_no_terminal_reads(
    plain: None, capsys: pytest.CaptureFixture[str]
) -> None:
    with Out() as out:
        out.spins(lambda: "working")
        out.spins(None)
    assert capsys.readouterr() == ("", "")


class _Agent:
    def __init__(self, sessions: list[object] | None = None) -> None:
        self.id = "alice"
        self.sessions = sessions or []


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """What the runtime's record says each event is: the next of these, in order."""
    said: list[dict[str, Any]] = []

    def record(
        agent: object, session: object, event: object, *, key: str = "", run: int = 0
    ) -> dict[str, Any]:
        del agent, session, event, run
        base: dict[str, Any] = {
            "at": "t",
            "agent": "alice",
            "cli": "claude",
            "model": "m1",
            "ident": "s-1",
            "whose": "",
            "tokens": {},
            "spent": {},
            "key": key,
            "text": "",
        }
        return base | said.pop(0)

    monkeypatch.setattr(hmz.runtime.doing.hosting, "record", record)
    return said


@pytest.fixture
def prices(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`hmz.coganchor.prices`, mocked: priced at fifty cents unless told otherwise."""
    held = mock.Mock()
    held.cost.return_value = 0.5
    held.money.return_value = "$0.50"
    monkeypatch.setattr(hmz.coganchor.prices, "cost", held.cost)
    monkeypatch.setattr(hmz.coganchor.prices, "money", held.money)
    return held


def _shown(
    said: list[dict[str, Any]], *events: dict[str, Any], session: object = None
) -> None:
    agent = _Agent()
    with Out() as out, Shown(out) as shown:
        for event in events:
            said.append(event)
            shown.heard(agent, session, mock.Mock())  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    ("event", "lines"),
    [
        ({"kind": "text", "text": "one"}, [f"{_SAID} one"]),
        ({"kind": "text", "text": "one\ntwo"}, [f"{_SAID} one", "  two"]),
        ({"kind": "text", "text": ""}, [f"{_SAID} "]),
        ({"kind": "reasoning", "text": "hm\nso"}, ["hm", "so"]),
        ({"kind": "tool", "text": "Bash ls -la"}, [f"{_SAID} Bash(ls -la)"]),
        ({"kind": "tool", "text": "Read"}, [f"{_SAID} Read()"]),
        ({"kind": "notice", "text": "rate limited"}, [f"{_SAID} rate limited"]),
        ({"kind": "subagent", "text": "x explore"}, [f"{_SAID} x(explore) started"]),
        ({"kind": "subagent-ends", "text": "x explore"}, [f"{_SAID} x(explore) done"]),
        ({"kind": "asks", "text": "which?"}, [f"{_SAID} which?"]),
        ({"kind": "failed", "text": "it broke"}, ["hmz: it broke"]),
        ({"kind": "something new", "text": "x"}, []),
    ],
)
def test_each_kind_of_event_is_a_line_of_its_own(
    plain: None,
    recorded: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    event: dict[str, Any],
    lines: list[str],
) -> None:
    _shown(recorded, event)
    assert capsys.readouterr().err.splitlines() == lines


def test_a_turn_is_timed_from_its_beginning_to_its_end(
    plain: None, recorded: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    _shown(recorded, {"kind": "begins"}, {"kind": "ends"}, {"kind": "ends"})
    assert capsys.readouterr().err.splitlines() == [
        f"{_SAID} alice is working",
        "✻ Worked for 0s · alice",
        "✻ Worked for 0s · alice",
    ]


def test_a_turn_says_which_conversation_it_is_in_where_there_are_several(
    plain: None, recorded: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    sessions = [object(), object(), object()]
    agent = _Agent(sessions)
    with Out() as out, Shown(out) as shown:
        for session in (sessions[1], None, object()):
            recorded.append({"kind": "begins"})
            shown.heard(agent, session, mock.Mock())  # pyright: ignore[reportArgumentType]
    assert capsys.readouterr().err.splitlines() == [
        f"{_SAID} alice is working · conversation 2 of 3",
        f"{_SAID} alice is working",
        f"{_SAID} alice is working",
    ]


def test_a_result_is_priced_and_its_answer_put_on_stdout(
    plain: None,
    recorded: list[dict[str, Any]],
    prices: mock.Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spent = {"reasoning": 3, "zeta": 1, "output": 2_500_000, "input": 1500}
    _shown(
        recorded,
        {"kind": "result", "text": "done", "spent": spent, "tokens": {"m2": spent}},
    )
    captured = capsys.readouterr()
    assert captured.err.splitlines() == [
        "✻ input 1.5k · output 2.50M · reasoning 3 · zeta 1 · $0.50 · m2 · alice"
    ]
    assert captured.out == "done\n"
    prices.cost.assert_called_once_with(spent, "m2")
    prices.money.assert_called_once_with(0.5)


def test_a_result_on_a_model_nobody_prices_has_no_price(
    plain: None,
    recorded: list[dict[str, Any]],
    prices: mock.Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prices.cost.return_value = None
    _shown(
        recorded,
        {"kind": "result", "text": "", "spent": {"input": 999}, "tokens": {}},
    )
    captured = capsys.readouterr()
    assert captured.err.splitlines() == ["✻ input 999 · m1 · alice"]
    assert captured.out == ""
    prices.money.assert_not_called()


def test_a_result_that_spent_nothing_has_no_footer(
    plain: None,
    recorded: list[dict[str, Any]],
    prices: mock.Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _shown(recorded, {"kind": "result", "text": "answer"})
    assert capsys.readouterr() == ("answer\n", "")
    prices.cost.assert_not_called()


def test_the_answer_is_not_said_twice_on_one_terminal(
    plain: None,
    recorded: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout, stderr = _Tty(), _Tty()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    _shown(recorded, {"kind": "result", "text": "answer"})
    assert stdout.getvalue() == ""


def test_json_puts_each_event_out_as_one_object(
    plain: None, recorded: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    recorded.append({"kind": "text", "text": "hi", "tokens": {"m": {}}, "spent": {}})
    with Out(as_json=True) as out, Shown(out) as shown:
        shown.heard(_Agent(), None, mock.Mock())  # pyright: ignore[reportArgumentType]
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "at": "t",
        "agent": "alice",
        "cli": "claude",
        "model": "m1",
        "session": "s-1",
        "kind": "text",
        "text": "hi",
        "whose": "",
        "tokens": {"m": {}},
        "spent": {},
    }
    assert captured.err == ""
