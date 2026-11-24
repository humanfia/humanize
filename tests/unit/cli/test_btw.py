"""`hmz btw`: side questions asked, and the side conversations listed, shown and closed."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from hmz.cli import main, tree


@pytest.fixture
def btw(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> mock.Mock:
    """The side questions family of the client the command reaches, asked from a folder."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    monkeypatch.chdir(tmp_path)
    return client.btw


def _answer(aside: str = "a1", question: str = "the word?") -> mock.Mock:
    return mock.Mock(aside=aside, to="Ada/1", question=question, answer="papaya")


def _aside() -> mock.Mock:
    return mock.Mock(aside="a1", to="Ada/1", question="", said=[_answer()])


def test_a_question_is_asked_from_this_folder_and_its_side_conversation_named(
    btw: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    btw.ask.return_value = _answer()

    assert main(["btw", "ask", "the word?", "--to", "Ada/1"]) == 0

    said = capsys.readouterr()
    assert said.out == "papaya\n"
    assert said.err == (
        "Side conversation a1: pass `--aside a1` to ask the next question in it.\n"
    )
    btw.ask.assert_called_once_with(
        str(Path.cwd()), "the word?", to="Ada/1", aside=None, epic=None, chat=None
    )


def test_a_later_question_names_its_side_conversation_and_is_told_nothing_more(
    btw: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    btw.ask.return_value = _answer()

    line = ["btw", "ask", "again?", "--to", "Ada/1", "--aside", "a1", "-w", "/w"]
    assert main([*line, "--epic", "e1", "--json"]) == 0

    said = capsys.readouterr()
    assert json.loads(said.out) == {
        "aside": "a1",
        "to": "Ada/1",
        "question": "the word?",
        "answer": "papaya",
    }
    assert said.err == ""
    btw.ask.assert_called_once_with(
        "/w", "again?", to="Ada/1", aside="a1", epic="e1", chat=None
    )


def test_a_side_conversation_named_alone_goes_on_with_the_session_it_asks(
    btw: mock.Mock,
) -> None:
    btw.list.return_value = [_aside()]
    btw.ask.return_value = _answer()

    assert main(["btw", "ask", "and then?", "--aside", "a1"]) == 0

    btw.list.assert_called_once_with(str(Path.cwd()), epic=None, chat=None)
    btw.ask.assert_called_once_with(
        str(Path.cwd()), "and then?", to="Ada/1", aside="a1", epic=None, chat=None
    )


def test_a_chat_is_asked_of_the_last_session_it_opened(btw: mock.Mock) -> None:
    btw.sessions.return_value = [mock.Mock(key="Ada/1"), mock.Mock(key="Ada/2")]
    btw.ask.return_value = _answer()

    assert main(["btw", "ask", "why?", "--chat", "c1", "-w", "~/project"]) == 0

    btw.sessions.assert_called_once_with(chat="c1")
    # `~` is the daemon's to expand.
    btw.ask.assert_called_once_with(
        "~/project", "why?", to="Ada/2", aside=None, epic=None, chat="c1"
    )


def test_a_question_with_nobody_to_ask_is_refused_in_the_pages_words(
    btw: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    btw.sessions.return_value = []

    assert main(["btw", "ask", "why?"]) == 1
    assert main(["btw", "ask", "why?", "--chat", "c1"]) == 1
    assert main(["btw", "ask", "why?", "--chat", "c1", "--epic", "e1"]) == 1

    assert capsys.readouterr().err == (
        "hmz btw ask: Pick the conversation to ask first.\n"
        "hmz btw ask: This chat has said nothing to ask about yet.\n"
        "hmz btw ask: Give `--epic` or `--chat`, not both.\n"
    )
    btw.ask.assert_not_called()


def test_the_sessions_of_an_epic_or_a_chat_are_listed_as_they_are_asked(
    btw: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    btw.sessions.return_value = [
        mock.Mock(key="Ada/1", agent="Ada", harness="claude"),
        mock.Mock(key="Bo/1", agent="Bo", harness="codex"),
    ]

    assert main(["btw", "sessions", "--epic", "e1"]) == 0
    assert capsys.readouterr().out == "Ada/1  claude\nBo/1   codex\n"
    btw.sessions.assert_called_once_with(epic="e1", chat=None)

    assert main(["btw", "sessions", "--chat", "c1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["sessions"][1] == {
        "session": "Bo/1",
        "agent": "Bo",
        "harness": "codex",
    }

    assert main(["btw", "sessions"]) == 1
    assert capsys.readouterr().err == (
        "hmz btw sessions: Name an epic with `--epic` or a chat with `--chat`.\n"
    )


def test_side_conversations_are_listed_and_one_is_shown(
    btw: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    btw.list.return_value = [_aside()]

    assert main(["btw", "list", "--chat", "c1"]) == 0
    assert capsys.readouterr().out == "a1  Ada/1  1\n"
    btw.list.assert_called_with(str(Path.cwd()), epic=None, chat="c1")

    assert main(["btw", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "asides": [
            {
                "aside": "a1",
                "to": "Ada/1",
                "question": "",
                "said": [{"question": "the word?", "answer": "papaya"}],
            }
        ]
    }

    assert main(["btw", "show", "a1"]) == 0
    assert capsys.readouterr().out == "> the word?\npapaya\n"

    assert main(["btw", "show", "a1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["said"] == [
        {"question": "the word?", "answer": "papaya"}
    ]

    assert main(["btw", "show", "a2"]) == 1
    assert (
        capsys.readouterr().err == "hmz btw show: There is no side conversation a2.\n"
    )


def test_one_side_conversation_is_closed_or_every_one_and_never_by_default(
    btw: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["btw", "leave", "a1"]) == 0
    assert capsys.readouterr().out == "Closed.\n"
    btw.leave.assert_called_once_with(str(Path.cwd()), "a1")

    assert main(["btw", "leave", "--all", "-w", "/w", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"aside": None}
    btw.leave.assert_called_with("/w", None)

    btw.leave.reset_mock()
    assert main(["btw", "leave"]) == 1
    assert main(["btw", "leave", "a1", "--all"]) == 1
    assert capsys.readouterr().err == (
        "hmz btw leave: Name one side conversation or give `--all`.\n" * 2
    )
    btw.leave.assert_not_called()
