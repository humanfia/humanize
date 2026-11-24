"""`hmz ai`: conversations with Ai-chan made, talked in, listed, renamed and deleted."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

from hmz.cli import main, tree


@pytest.fixture
def ai(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> mock.Mock:
    """The Ai-chan family of the client the command reaches, asked from a folder."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    monkeypatch.chdir(tmp_path)
    client.aichan.create.return_value = mock.Mock(id=3, workspace="/ai", slot="ai:ab")
    return client.aichan


def _conversation(**said: str) -> mock.Mock:
    one = mock.Mock(
        id=3,
        title="hello",
        scope="daemon",
        workspace="/ai",
        epic="",
        nous="claude/haiku",
        preset="read-only",
        slot="ai:ab",
        state="waiting",
        created="2026-01-01T00:00:00Z",
        latest="hi",
        updated="2026-01-01T00:00:01Z",
    )
    one.configure_mock(**said)
    return one


def _typed(
    monkeypatch: pytest.MonkeyPatch, line: str, *, terminal: bool = True
) -> None:
    """Has standard input be a terminal, or not, with one line typed at it."""
    typed = io.StringIO(line)
    typed.isatty = lambda: terminal  # type: ignore[method-assign]
    monkeypatch.setattr(sys, "stdin", typed)


def test_a_conversation_is_scoped_to_the_daemon_until_something_narrower_is_named(
    ai: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ai", "new", "hello"]) == 0
    assert capsys.readouterr().out == "3\n"
    ai.create.assert_called_with(
        "hello", scope="daemon", workspace=None, epic=None, nous=None, preset=None
    )

    assert main(["ai", "new", "hello", "-w", "/w", "--nous", "claude/haiku"]) == 0
    ai.create.assert_called_with(
        "hello",
        scope="workspace",
        workspace="/w",
        epic=None,
        nous="claude/haiku",
        preset=None,
    )

    # An epic of the folder this is typed in, where no workspace is named.
    assert main(["ai", "new", "hello", "--epic", "e1", "--preset", "read-only"]) == 0
    ai.create.assert_called_with(
        "hello",
        scope="epic",
        workspace=str(Path.cwd()),
        epic="e1",
        nous=None,
        preset="read-only",
    )

    # A scope said is the scope asked for, and what it does not take is the daemon's to refuse.
    assert main(["ai", "new", "hello", "--scope", "daemon", "-w", "~/w"]) == 0
    ai.create.assert_called_with(
        "hello", scope="daemon", workspace="~/w", epic=None, nous=None, preset=None
    )
    ai.heard.assert_not_called()


def test_a_new_conversation_is_waited_on_where_asked(
    ai: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    ai.heard.return_value = mock.Mock(text="hi there", mode="listen")

    assert main(["ai", "new", "hello", "--wait", "--timeout", "5"]) == 0
    assert capsys.readouterr().out == "3\nhi there\n"
    ai.heard.assert_called_once_with(3, wait=5.0)

    assert main(["ai", "new", "hello", "--wait", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": 3,
        "workspace": "/ai",
        "slot": "ai:ab",
        "answer": "hi there",
        "mode": "listen",
    }

    assert main(["ai", "new", "hello", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["answer"] is None


def test_conversations_are_listed_in_columns(
    ai: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    ai.list.return_value = [_conversation()]

    assert main(["ai", "list"]) == 0
    assert capsys.readouterr().out == (
        "3  waiting  daemon  read-only  claude/haiku  hello\n"
    )

    assert main(["ai", "list", "--json"]) == 0
    (one,) = json.loads(capsys.readouterr().out)["conversations"]
    assert one == {
        "id": 3,
        "title": "hello",
        "scope": "daemon",
        "workspace": "/ai",
        "epic": "",
        "nous": "claude/haiku",
        "preset": "read-only",
        "slot": "ai:ab",
        "state": "waiting",
        "created": "2026-01-01T00:00:00Z",
        "latest": "hi",
        "updated": "2026-01-01T00:00:01Z",
    }


def test_a_conversation_is_renamed(
    ai: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ai", "rename", "3", "another"]) == 0
    assert capsys.readouterr().out == "Renamed\n"
    ai.rename.assert_called_once_with(3, "another")

    assert main(["ai", "rename", "3", "another", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"id": 3, "title": "another"}

    with pytest.raises(SystemExit) as unread:
        main(["ai", "rename", "three", "another"])
    assert unread.value.code == 2


def test_forgetting_asks_first_and_takes_only_a_yes(
    ai: mock.Mock, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ai.get.return_value = _conversation()
    _typed(monkeypatch, "n\n")

    assert main(["ai", "forget", "3"]) == 1

    said = capsys.readouterr()
    assert said.err == (
        "Delete conversation 3 (hello) with Ai-chan? It cannot be brought back. [y/N] "
        "hmz ai forget: The conversation was not deleted.\n"
    )
    assert said.out == ""
    ai.forget.assert_not_called()

    _typed(monkeypatch, "Yes\n")
    assert main(["ai", "forget", "3"]) == 0
    assert capsys.readouterr().out == "Deleted\n"
    ai.forget.assert_called_once_with(3)


def test_forgetting_asks_nobody_who_is_not_there(
    ai: mock.Mock, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ai.get.return_value = _conversation()
    _typed(monkeypatch, "y\n", terminal=False)

    assert main(["ai", "forget", "3"]) == 1
    assert capsys.readouterr().err == (
        "hmz ai forget: Nobody can be asked here; give `--yes` to delete.\n"
    )

    # Nor under `--json`, which says nothing on standard error.
    _typed(monkeypatch, "y\n")
    assert main(["ai", "forget", "3", "--json"]) == 1
    said = capsys.readouterr()
    assert said.err == ""
    assert json.loads(said.out)["error"]["message"] == (
        "Nobody can be asked here; give `--yes` to delete."
    )
    ai.forget.assert_not_called()

    assert main(["ai", "forget", "3", "-y", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"id": 3}
    ai.forget.assert_called_once_with(3)


def test_a_line_is_said_and_her_answer_printed(
    ai: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    ai.say.return_value = mock.Mock(text="heard", mode="listen")

    assert main(["ai", "say", "3", "and then?"]) == 0
    assert capsys.readouterr().out == "heard\n"
    ai.say.assert_called_once_with(3, "and then?", hear=True, wait=600)

    assert main(["ai", "say", "3", "and then?", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": 3,
        "answer": "heard",
        "mode": "listen",
    }

    ai.say.return_value = None
    assert main(["ai", "say", "3", "go on", "--no-wait", "--timeout", "2"]) == 0
    assert capsys.readouterr().out == ""
    ai.say.assert_called_with(3, "go on", hear=False, wait=2.0)

    assert main(["ai", "say", "3", "go on", "--no-wait", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": 3,
        "answer": None,
        "mode": None,
    }


def test_her_answer_is_waited_for_and_her_turn_stopped(
    ai: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    ai.heard.return_value = mock.Mock(text="which one?", mode="choose")

    assert main(["ai", "wait", "3", "--timeout", "60"]) == 0
    assert capsys.readouterr().out == "which one?\n"
    ai.heard.assert_called_once_with(3, wait=60.0)

    assert main(["ai", "wait", "3", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": 3,
        "answer": "which one?",
        "mode": "choose",
    }

    assert main(["ai", "stop", "3"]) == 0
    assert capsys.readouterr().out == "Stopped\n"
    ai.stop.assert_called_once_with(3)


def test_an_answer_that_does_not_come_in_time_ends_as_a_daemon_unreached(
    ai: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    ai.heard.side_effect = TimeoutError("Ai-chan did not answer in time")

    assert main(["ai", "wait", "3", "--json"]) == 3

    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": 504, "message": "Ai-chan did not answer in time"}
    }
