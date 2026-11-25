"""`hmz chat`: a chat started, said to and managed, through a chats family that is mocked."""

from __future__ import annotations

import io
import json
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self
from unittest import mock

import pytest

import hmz.sdk
from hmz.cli import main, tree

if TYPE_CHECKING:
    from collections.abc import Iterator

ID = "20261117T100000.000Z-ab12cd"


def _chat(**said: Any) -> mock.Mock:
    """A chat as the family returns one: its row, and the row as attributes."""
    row = {"id": ID, "title": "the  parser\nagain", "state": "resting", **said}
    made = mock.Mock(said=row)
    made.configure_mock(**{"slot": "", **row})
    return made


class Turn:
    """A turn as the family hands one out: what it is told, and what it came to."""

    def __init__(self, *messages: dict[str, Any], **came: Any) -> None:
        self.workspace, self.slot = "/w", "chat:ab"
        self.answer: str | None = came.get("answer")
        self.failed: str = came.get("failed", "")
        self.notes: list[str] = came.get("notes", [])
        self.ended: tuple[str, str] | None = came.get("ended")
        self.done: bool = came.get("done", True)
        self.signals: int | None = came.get("signals")
        self.closed = False
        self._messages = messages

    def __iter__(self) -> Iterator[dict[str, Any]]:
        yield from self._messages
        if self.signals is not None:
            signal.raise_signal(self.signals)

    def wait(self) -> str | None:
        for _ in self:
            pass
        return self.answer

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True


@pytest.fixture
def chats(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The chats family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    client.chats.start.return_value = mock.Mock(chat=ID, workspace="/w", slot="chat:ab")
    client.chats.hold.return_value = mock.Mock(workspace="/w", slot="chat:ab")
    return client.chats


def _event(kind: str, text: str) -> dict[str, Any]:
    return {
        "type": "event", "seq": 3, "agent": "Pan", "session": "Pan/1", "kind": kind,
        "text": text, "at": 0.0, "cli": "claude", "model": "m", "ident": "i",
        "whose": "", "tokens": {}, "spent": None, "key": "Pan/1", "mono": 0.0,
    }  # fmt: skip


def test_help_says_every_command_of_the_group(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["chat"]) == 0

    out = capsys.readouterr().out
    for name in (
        "start", "say", "list", "show", "rename", "fork", "archive", "unarchive",
        "delete", "stop", "set", "move", "agent", "commands", "backup", "harness",
    ):  # fmt: skip
        assert f"\n  {name} " in out


def test_every_text_of_help_is_thirty_words_at_most() -> None:
    (chat,) = (one for name, one in tree.commands().items() if name == "chat")

    assert [text for text in chat.texts() if len(text.split()) > 30] == []


def test_starting_draws_the_turn_and_prints_the_answer_and_ends_the_host(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    turn = Turn(_event("result", "it parses"), answer="it parses", notes=["a new one"])
    chats.follow.return_value = turn

    assert main(["chat", "start", "-a", "claude/m", "-w", "/w", "what is here?"]) == 0

    said = capsys.readouterr()
    assert said.out == "it parses\n"
    assert said.err.startswith(f"Chat {ID}\n")
    assert "a new one\n" in said.err
    chats.start.assert_called_once_with(
        "/w",
        "what is here?",
        agent="claude/m",
        env=None,
        permission=None,
        prefer=None,
        worktree=None,
        remember=None,
    )
    chats.follow.assert_called_once_with("/w", "chat:ab")
    # Nobody is here to say the next line, so the host this started is ended.
    chats.rest.assert_called_once_with(ID)
    assert turn.closed


def test_starting_takes_the_current_directory_and_the_agent_it_remembers(
    chats: mock.Mock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    chats.remembered.return_value = "codex/gpt"
    chats.follow.return_value = Turn(answer="ok")

    code = main(
        ["chat", "start", "--json", "--worktree", "--remember", "--permission",
         "read-only", "--prefer", "flow", "-e", "ssh@box/srv", "hello"]
    )  # fmt: skip

    assert code == 0
    here = str(Path.cwd().resolve())
    chats.remembered.assert_called_once_with(here)
    chats.start.assert_called_once_with(
        here,
        "hello",
        agent="codex/gpt",
        env="ssh@box/srv",
        permission="read-only",
        prefer="flow",
        worktree=True,
        remember=True,
    )


def test_starting_with_no_agent_given_or_remembered_is_refused(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.remembered.return_value = ""

    assert main(["chat", "start", "hello"]) == 1

    assert "name one with `-a`" in capsys.readouterr().err
    chats.start.assert_not_called()


def test_a_chat_of_no_folder_names_no_workspace_and_takes_no_worktree(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.follow.return_value = Turn(answer="ok")

    assert main(["chat", "start", "--no-folder", "-a", "claude/m", "hello"]) == 0
    assert chats.start.call_args.args == (None, "hello")
    chats.remembered.assert_not_called()
    capsys.readouterr()

    assert main(["chat", "start", "--no-folder", "--worktree", "-a", "x/y", "hi"]) == 1
    assert capsys.readouterr().err == "hmz chat start: A worktree needs a folder\n"


def test_json_is_one_document_and_nothing_is_drawn(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.follow.return_value = Turn(
        _event("result", "it parses"), answer="it parses", notes=["a new one"]
    )

    assert main(["chat", "start", "--json", "-a", "claude/m", "what?"]) == 0

    said = capsys.readouterr()
    assert json.loads(said.out) == {
        "chat": ID,
        "workspace": "/w",
        "slot": "chat:ab",
        "answer": "it parses",
        "notes": ["a new one"],
        "detached": False,
    }
    assert said.err == ""


def test_events_are_the_records_of_the_turn_a_line_apiece_then_the_document(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.follow.return_value = Turn(
        {"type": "welcome", "epoch": "e"},
        {"type": "run", "turn": "running"},
        _event("result", "it parses"),
        {"type": "live", "seq": 3, "elided": 0},
        answer="it parses",
    )

    assert main(["chat", "start", "--events", "-a", "claude/m", "what?"]) == 0

    said = capsys.readouterr()
    first, last = (json.loads(line) for line in said.out.splitlines())
    assert (first["type"], first["text"]) == ("event", "it parses")
    assert (last["chat"], last["answer"]) == (ID, "it parses")
    assert said.err == ""


def test_detached_the_id_is_printed_and_nothing_is_followed(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["chat", "start", "--detach", "-a", "claude/m", "go"]) == 0
    assert capsys.readouterr().out == f"{ID}\n"
    chats.follow.assert_not_called()
    chats.rest.assert_not_called()

    assert main(["chat", "start", "--detach", "--json", "-a", "claude/m", "go"]) == 0
    assert json.loads(capsys.readouterr().out)["detached"] is True


@pytest.mark.parametrize(
    ("came", "message"),
    [
        ({"failed": "it broke"}, "it broke"),
        ({"ended": ("crashed", "Traceback"), "done": False}, "Traceback"),
        (
            {"ended": ("gone", "the host went away"), "done": False},
            "the host went away",
        ),
        ({"ended": ("failed", ""), "done": False}, "The turn failed."),
    ],
)
def test_a_turn_that_failed_exits_one_with_what_was_said(
    chats: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    came: dict[str, Any],
    message: str,
) -> None:
    chats.follow.return_value = Turn(**came)

    assert main(["chat", "start", "-a", "claude/m", "go"]) == 1
    assert capsys.readouterr().err.endswith(f"hmz chat start: {message}\n")

    assert main(["chat", "start", "--json", "-a", "claude/m", "go"]) == 1
    said = capsys.readouterr()
    assert json.loads(said.out) == {
        "error": {"code": 0, "message": message},
        "chat": ID,
        "workspace": "/w",
        "slot": "chat:ab",
    }
    assert said.err == ""


def test_a_chat_that_ended_under_the_turn_is_not_ended_again(chats: mock.Mock) -> None:
    chats.follow.return_value = Turn(ended=("stopped", ""), done=False)

    assert main(["chat", "start", "--json", "-a", "claude/m", "go"]) == 0
    chats.rest.assert_not_called()


@pytest.mark.parametrize(
    ("signum", "status"),
    [(signal.SIGINT, 130), (signal.SIGTERM, 143), (signal.SIGHUP, 129)],
)
def test_a_signal_leaves_the_chat_to_its_host_and_exits_as_the_signal_says(
    chats: mock.Mock, signum: int, status: int
) -> None:
    turn = Turn(signals=signum)
    chats.follow.return_value = turn
    before = signal.getsignal(signum)

    assert main(["chat", "start", "--json", "-a", "claude/m", "go"]) == status

    # Left, not stopped: the host is let go of and the chat is said nothing.
    assert turn.closed
    chats.rest.assert_not_called()
    chats.stop.assert_not_called()
    assert signal.getsignal(signum) == before


def test_saying_asks_the_chat_and_ends_a_host_only_this_started(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.get.return_value = _chat()
    chats.ask.return_value = Turn(_event("result", "tested"), answer="tested")

    assert main(["chat", "say", ID, "and how is it tested?"]) == 0

    assert capsys.readouterr().out == "tested\n"
    chats.ask.assert_called_once_with(ID, "and how is it tested?")
    chats.rest.assert_called_once_with(ID)

    chats.rest.reset_mock()
    chats.get.return_value = _chat(slot="chat:ab", state="going")
    chats.ask.return_value = Turn(answer="again")
    assert main(["chat", "say", "--json", ID, "again"]) == 0
    assert json.loads(capsys.readouterr().out)["answer"] == "again"
    # Somebody else's host, which stays for them.
    chats.rest.assert_not_called()


def test_saying_nothing_is_refused_and_detached_nothing_is_waited_for(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["chat", "say", ID, "  "]) == 1
    assert "The message is empty" in capsys.readouterr().err
    chats.ask.assert_not_called()

    assert main(["chat", "say", "--detach", ID, "go on"]) == 0
    assert capsys.readouterr().out == f"{ID}\n"
    chats.say.assert_called_once_with("/w", "chat:ab", "go on")
    chats.ask.assert_not_called()
    chats.rest.assert_not_called()


def test_the_chats_of_this_directory_are_listed_a_line_apiece(
    chats: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    long = _chat(id="c2", state="turn", title="x" * 80)
    chats.list.return_value = mock.Mock(
        chats=(_chat(), long), total=2, offset=0, limit=50
    )

    assert main(["chat", "list"]) == 0

    assert capsys.readouterr().out == (
        f"{ID}  resting  the parser again\nc2{' ' * 27}turn     {'x' * 59}…\n"
    )
    chats.list.assert_called_once_with(
        workspace=str(Path.cwd().resolve()),
        archived=None,
        q=None,
        offset=None,
        limit=None,
    )

    assert main(
        ["chat", "list", "--all", "--archived", "-q", "pars", "--limit", "5", "--json"]
    ) == 0  # fmt: skip
    said = json.loads(capsys.readouterr().out)
    assert [one["id"] for one in said["chats"]] == [ID, "c2"]
    assert (said["total"], said["offset"], said["limit"]) == (2, 0, 50)
    assert chats.list.call_args.kwargs == {
        "workspace": None, "archived": True, "q": "pars", "offset": None, "limit": 5,
    }  # fmt: skip


def test_a_chat_is_shown_a_field_a_line_and_its_trace_after(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    trace = [{"key": "claude:1", "agent": "Pan", "actions": [{"name": "say: hi\nyou"}]}]
    chats.get.return_value = _chat(agent="claude/m", archived=False, trace=trace)

    assert main(["chat", "show", ID, "--trace"]) == 0

    assert capsys.readouterr().out == (
        f"id        {ID}\n"
        "title     the parser again\n"
        "state     resting\n"
        "agent     claude/m\n"
        "archived  false\n"
        "\n"
        "Pan  claude:1\n"
        "  say: hi you\n"
    )
    chats.get.assert_called_once_with(ID, trace=True)

    assert main(["chat", "show", ID, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == ID


@pytest.mark.parametrize(
    ("argv", "method", "given"),
    [
        (["rename", ID, "new"], "rename", (ID, "new")),
        (["archive", ID], "archive", (ID,)),
        (["unarchive", ID], "unarchive", (ID,)),
        (["agent", ID, "claude/m:high"], "agent", (ID, "claude/m:high")),
    ],
)
def test_what_changes_a_chat_prints_its_line_as_it_then_is(
    chats: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    method: str,
    given: tuple[str, ...],
) -> None:
    getattr(chats, method).return_value = _chat(title="new")

    assert main(["chat", *argv]) == 0
    assert capsys.readouterr().out == f"{ID}  resting  new\n"
    getattr(chats, method).assert_called_once_with(*given)

    assert main(["chat", *argv, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["title"] == "new"


def test_a_fork_prints_the_new_chats_id(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.fork.return_value = "c2"

    assert main(["chat", "fork", ID]) == 0
    assert capsys.readouterr().out == "c2\n"
    assert main(["chat", "fork", ID, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"chat": "c2"}


def _stdin(monkeypatch: pytest.MonkeyPatch, typed: str, *, terminal: bool) -> None:
    held = io.StringIO(typed)
    held.isatty = lambda: terminal  # type: ignore[method-assign]
    monkeypatch.setattr("sys.stdin", held)


def test_deleting_asks_first_and_deletes_on_a_yes(
    chats: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chats.get.return_value = _chat()
    _stdin(monkeypatch, "Yes\n", terminal=True)

    assert main(["chat", "delete", ID]) == 0

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == (
        f"Delete {ID}  resting  the parser again? It cannot be brought back. [y/N] "
    )
    chats.delete.assert_called_once_with(ID)


def test_a_chat_is_not_deleted_for_want_of_a_yes(
    chats: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chats.get.return_value = _chat()
    _stdin(monkeypatch, "\n", terminal=True)

    assert main(["chat", "delete", ID]) == 1
    assert capsys.readouterr().err.endswith("hmz chat delete: Nothing was changed.\n")

    # Nobody at a terminal is nobody to ask, and neither is a program reading a document.
    _stdin(monkeypatch, "yes\n", terminal=False)
    assert main(["chat", "delete", ID]) == 1
    assert "run it again with `-y`" in capsys.readouterr().err
    _stdin(monkeypatch, "yes\n", terminal=True)
    assert main(["chat", "delete", ID, "--json"]) == 1
    assert "`-y`" in json.loads(capsys.readouterr().out)["error"]["message"]
    chats.delete.assert_not_called()


def test_yes_deletes_without_asking(
    chats: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stdin(monkeypatch, "", terminal=False)

    assert main(["chat", "delete", "-y", ID, "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {"deleted": ID}
    chats.get.assert_not_called()
    chats.delete.assert_called_once_with(ID)


def test_stop_set_move_and_commands_reach_the_chat_where_it_is_held(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = mock.Mock(sigil="/", about="clears  it", how="", source="hmz")
    entry.name = "clear"
    chats.commands.return_value = mock.Mock(
        entries=(entry,),
        prefer="flow",
        prefer_from="chat",
        permission="read-only",
        listed=True,
    )
    chats.move.return_value = "ssh@box/srv"

    assert main(["chat", "stop", ID]) == 0
    assert capsys.readouterr().out == "Stopped\n"
    chats.stop.assert_called_once_with("/w", "chat:ab")

    assert (
        main(["chat", "set", ID, "--permission", "read-only", "--prefer", "flow"]) == 0
    )
    assert capsys.readouterr().out == (
        "permission   read-only\nprefer       flow\nprefer_from  chat\n"
    )
    chats.set.assert_called_once_with(
        "/w", "chat:ab", prefer="flow", permission="read-only"
    )

    chats.get.return_value = _chat(workspace="/w", slot="chat:ab")
    assert main(["chat", "move", ID, "ssh@box/srv", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"chat": ID, "env": "ssh@box/srv"}
    chats.move.assert_called_once_with("/w", "chat:ab", "ssh@box/srv")
    # At rest, it is carried on where it is moved to: where it worked may be out of reach.
    chats.get.return_value = _chat(workspace="/w", env="local/w2")
    assert main(["chat", "move", ID, "local/w2"]) == 0
    assert capsys.readouterr().out == "local/w2\n"
    chats.start.assert_called_once_with("/w", "", resume=ID, env="local/w2")
    chats.move.assert_called_once()

    assert main(["chat", "commands", ID]) == 0
    assert capsys.readouterr().out == "/clear  hmz  clears it\n"
    assert main(["chat", "commands", ID, "--json"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["entries"] == [
        {
            "sigil": "/",
            "name": "clear",
            "about": "clears  it",
            "how": "",
            "source": "hmz",
        }
    ]
    assert (said["prefer"], said["listed"]) == ("flow", True)
    assert chats.hold.call_args_list == [mock.call(ID)] * 4


def test_a_backup_is_queued_for_the_targets_named(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.backup.return_value = ["lab", "home"]

    assert main(["chat", "backup", ID, "--to", "lab", "--to", "home"]) == 0
    assert capsys.readouterr().out == "lab\nhome\n"
    chats.backup.assert_called_once_with(ID, to=["lab", "home"])

    assert main(["chat", "backup", ID, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"queued": ["lab", "home"]}
    assert chats.backup.call_args == mock.call(ID, to=None)


def _session(**said: Any) -> mock.Mock:
    row = {
        "id": "s9", "harness": "claude", "title": "hello  there", "workspace": "/w",
        "model": "m", "began": "b", "updated": "u", "continuable": True, "trace": None,
    }  # fmt: skip
    made = mock.Mock()
    made.configure_mock(**{**row, **said})
    return made


def test_harness_sessions_are_listed_shown_and_adopted(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.harness.list.return_value = mock.Mock(
        sessions=(_session(),), total=1, offset=0, limit=50
    )
    chats.harness.get.return_value = _session(trace=[])
    chats.harness.adopt.return_value = "c3"

    assert main(["chat", "harness", "list", "-w", "/w", "--limit", "9"]) == 0
    assert capsys.readouterr().out == "claude  s9  u  hello there\n"
    chats.harness.list.assert_called_once_with("/w", offset=None, limit=9)

    assert main(["chat", "harness", "list", "-w", "/w", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["sessions"][0]["continuable"] is True
    assert "trace" not in listed["sessions"][0]

    assert main(["chat", "harness", "show", "claude", "s9", "-w", "/w", "--trace"]) == 0
    assert capsys.readouterr().out.startswith("id           s9\nharness      claude\n")
    chats.harness.get.assert_called_once_with("/w", "claude", "s9", trace=True)

    code = main(
        ["chat", "harness", "adopt", "claude", "s9", "-w", "/w", "-a", "claude/m"]
    )
    assert code == 0
    assert capsys.readouterr().out == "c3\n"
    chats.harness.adopt.assert_called_once_with("/w", "claude", "s9", agent="claude/m")


def test_a_session_that_ended_under_a_turn_is_a_daemon_not_reached(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.start.side_effect = hmz.sdk.Refused("the daemon went away", code=503)
    # The session has ended, as the client says it of one whose daemon went.
    tree.reach.return_value.wait.return_value = True  # pyright: ignore[reportFunctionMemberAccess]

    assert main(["chat", "start", "-a", "claude/m", "go"]) == 3
    assert "the daemon went away" in capsys.readouterr().err


def test_what_the_daemon_refuses_is_said_in_its_words_and_exits_one(
    chats: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    chats.get.side_effect = hmz.sdk.Refused("There is no chat nope.", code=404)

    assert main(["chat", "show", "nope"]) == 1
    assert capsys.readouterr().err == "hmz chat show: There is no chat nope.\n"


def test_a_line_that_cannot_be_read_exits_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for argv in (
        ["start"],
        ["say", ID],
        ["set", ID, "--permission", "all"],
        ["--list"],
    ):
        with pytest.raises(SystemExit) as stopped:
            main(["chat", *argv])
        assert stopped.value.code == 2
    assert "Run `hmz chat" in capsys.readouterr().err
