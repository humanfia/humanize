"""`hmz chat`: one turn of a chat from the command line, the daemon a stand-in.

The workspace (`hmz.sdk.Hmz`), the session with the daemon (`hmz.sdk.client.Client`) and the
reading of a chat line (`hmz.runtime.chatting.resolve`) are mocked: what is here is what `hmz
chat` reads off its line, what it asks the daemon, and what it makes of what the chat's
subscription tells it.
"""

from __future__ import annotations

import errno
import os
import signal
import threading
from typing import TYPE_CHECKING, Any, Self
from unittest import mock

import pytest

import hmz.daemon.where
import hmz.runtime.chatting
import hmz.runtime.kept
import hmz.sdk
import hmz.sdk.client
from hmz.cli import main
from hmz.runtime import Refused
from hmz.runtime.chatting import Resolved

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

#: What the turn's subscription says when nothing in a test says otherwise: the turn opening,
#: the assistant answering, and the chat between turns.
_TURN: list[dict[str, Any]] = [
    {"type": "welcome", "epoch": "e1"},
    {"type": "run", "seq": 1, "state": "running", "turn": "running"},
    {"type": "opened", "seq": 2, "role": "assistant", "key": "NeiKos/1",
     "agent": "NeiKos", "cli": "claude", "model": "m"},
    {"type": "event", "seq": 3, "agent": "NeiKos", "session": "NeiKos/1",
     "kind": "begins", "key": "NeiKos/1", "text": ""},
    {"type": "event", "seq": 4, "agent": "NeiKos", "session": "NeiKos/1",
     "kind": "result", "key": "NeiKos/1", "text": "answered", "spent": {},
     "tokens": {}, "model": "m"},
    {"type": "run", "seq": 5, "state": "running", "turn": "done"},
]  # fmt: skip


class _Client:
    """A session with the daemon: what it was asked, and the chat's subscription, scripted.

    Attributes:
      said: What the subscription says on each attach, in turn; the last for every later one.
    """

    def __init__(self) -> None:
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.said: list[list[dict[str, Any]]] = [list(_TURN)]
        self.refuses: dict[str, BaseException] = {}
        self.attached: Callable[[], None] = lambda: None
        self.listener: Callable[[str, dict[str, Any]], None] | None = None
        self.ended = False
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def heard(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        self.listener = listener

    def wait(self, timeout: float | None = None) -> bool:
        del timeout
        return self.ended

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        idem: str | None = None,
        seconds: float | None = None,
    ) -> dict[str, Any]:
        del idem, seconds
        self.asked.append((method, dict(params or {})))
        if method in self.refuses:
            raise self.refuses[method]
        if method == "chat.start":
            return {"slot": "chat:ab12", "chat": "E"}
        if method == "epic.attach":
            assert self.listener is not None
            said = self.said.pop(0) if len(self.said) > 1 else self.said[0]
            for one in said:
                self.listener("epic.event", {"sub": "s1", "message": one})
            self.attached()
            return {"sub": "s1"}
        return {}

    def methods(self) -> list[str]:
        return [method for method, _ in self.asked]

    def params(self, method: str, nth: int = 0) -> dict[str, Any]:
        return [params for named, params in self.asked if named == method][nth]


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> mock.Mock:
    """`hmz.sdk.Hmz`, mocked: a workspace remembering an agent, with one flow `goal`."""

    def find(name: str) -> str:
        return "/flows/goal" if name == "goal" else ""

    def written(runs: object) -> str:
        del runs
        return "claude/m:high"

    held = mock.Mock()
    held.workspace = tmp_path
    held.flows.find.side_effect = find
    monkeypatch.setattr(hmz.sdk, "Hmz", mock.Mock(return_value=held), raising=False)
    monkeypatch.setattr(hmz.daemon.where, "workspace", str)
    # The remembered agent, as a file writes it.
    monkeypatch.setattr(hmz.runtime.kept, "written", written)
    return held


@pytest.fixture
def resolving(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`hmz.runtime.chatting.resolve`, reading every line as prose unless a test says not."""
    held = mock.Mock(return_value=Resolved("prose"))
    monkeypatch.setattr(hmz.runtime.chatting, "resolve", held)
    return held


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, resolving: mock.Mock) -> _Client:
    """`Client.local`, answering with one stand-in session."""
    del resolving
    held = _Client()
    monkeypatch.setattr(
        hmz.sdk.client.Client, "local", mock.Mock(return_value=held), raising=False
    )
    return held


def test_one_turn_is_taken_answered_on_stdout_and_ended_with_nothing_said(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["chat", "-a", "codex/o3", "hello"]) == 0

    assert client.methods() == ["chat.start", "epic.attach", "chat.say"]
    at = {"workspace": str(workspace.workspace), "slot": "chat:ab12"}
    assert client.params("chat.start") == {
        "workspace": str(workspace.workspace),
        "slot": "chat:",
        "agent": "codex/o3",
        "task": "hello",
        "remember": False,
    }
    assert client.params("epic.attach") == {**at, "since": None}
    assert client.params("chat.say") == {**at, "text": ""}
    assert client.closed
    assert capsys.readouterr().out == "answered\n"


def test_without_an_agent_the_one_remembered_here_is_talked_to(
    workspace: mock.Mock, client: _Client
) -> None:
    del workspace
    assert main(["chat", "hello"]) == 0
    assert client.params("chat.start")["agent"] == "claude/m:high"


def test_the_last_agent_given_is_the_one_used(
    workspace: mock.Mock, client: _Client
) -> None:
    del workspace
    assert main(["chat", "-a", "codex/o3", "--agent", "pi/x", "hello"]) == 0
    assert client.params("chat.start")["agent"] == "pi/x"


def test_without_an_agent_or_one_remembered_the_chat_is_refused(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace.settings.chat_agent = None
    with pytest.raises(SystemExit) as raised:
        main(["chat", "hello"])
    assert raised.value.code == 2
    assert capsys.readouterr().err == (
        "hmz chat: error: no chat agent is remembered here; give one with -a\n"
    )
    assert client.asked == []


def test_resume_carries_the_chat_of_that_id_on_with_its_own_agent(
    workspace: mock.Mock, client: _Client
) -> None:
    workspace.settings.chat_agent = None
    assert main(["chat", "--resume", "20261117T000000-ab12cd", "and then?"]) == 0
    started = client.params("chat.start")
    assert "agent" not in started
    assert started["resume"] == "20261117T000000-ab12cd"
    assert started["task"] == "and then?"
    assert "worktree" not in started


def test_worktree_starts_the_chat_in_a_new_worktree(
    workspace: mock.Mock, client: _Client
) -> None:
    del workspace
    assert main(["chat", "--worktree", "-a", "codex/o3", "hello"]) == 0
    started = client.params("chat.start")
    assert started["worktree"] is True
    assert "resume" not in started


def test_a_chat_started_without_worktree_does_not_ask_for_one(
    workspace: mock.Mock, client: _Client
) -> None:
    del workspace
    assert main(["chat", "hello"]) == 0
    assert "worktree" not in client.params("chat.start")


def test_worktree_is_refused_with_resume(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    with pytest.raises(SystemExit) as raised:
        main(["chat", "--worktree", "--resume", "E", "and then?"])
    assert raised.value.code == 2
    assert "one carried on works where it worked" in capsys.readouterr().err
    assert client.asked == []


def test_a_worktree_the_daemon_refuses_is_said_as_it_says_it(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.refuses["chat.start"] = Refused("this is no git repository", code=400)
    with pytest.raises(SystemExit) as raised:
        main(["chat", "--worktree", "hello"])
    assert raised.value.code == 2
    assert capsys.readouterr().err == ("hmz chat: error: this is no git repository\n")


def test_resume_with_an_agent_carries_the_chat_on_with_that_one(
    workspace: mock.Mock, client: _Client
) -> None:
    del workspace
    assert main(["chat", "--resume", "E", "-a", "codex/o3", "and then?"]) == 0
    assert client.params("chat.start")["agent"] == "codex/o3"


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        ([], "the following arguments are required: message"),
        ([""], "the message is empty"),
        (["-x"], "the following arguments are required: message"),
        (["one", "two"], "unrecognized arguments"),
    ],
)
def test_a_line_that_is_not_one_is_a_usage_error(
    workspace: mock.Mock,
    client: _Client,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    says: str,
) -> None:
    del workspace
    with pytest.raises(SystemExit) as raised:
        main(["chat", *argv])
    assert raised.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith("usage: hmz chat")
    assert f"hmz chat: error: {says}" in err
    assert client.asked == []


def test_a_message_that_starts_with_a_dash_is_said_after_two(
    workspace: mock.Mock, client: _Client
) -> None:
    del workspace
    assert main(["chat", "--", "--force is not a flag here"]) == 0
    assert client.params("chat.start")["task"] == "--force is not a flag here"


def test_help_is_written_to_stdout(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    with pytest.raises(SystemExit) as raised:
        main(["chat", "--help"])
    assert raised.value.code == 0
    assert capsys.readouterr().out.startswith("usage: hmz chat")
    assert client.asked == []


@pytest.mark.parametrize(
    ("message", "read", "says"),
    [
        ("/clear", Resolved("reserved", "clear"), "/clear is kept"),
        ("/flow goal win", Resolved("reserved", "flow", "goal win"), "/flow is kept"),
        ("$goal win", Resolved("flow", "goal", "win"), "$goal names a flow"),
    ],
)
def test_a_name_kept_for_hmz_or_a_flow_is_refused_naming_it(
    workspace: mock.Mock,
    client: _Client,
    resolving: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    message: str,
    read: Resolved,
    says: str,
) -> None:
    del workspace
    resolving.return_value = read
    with pytest.raises(SystemExit) as raised:
        main(["chat", message])
    assert raised.value.code == 2
    assert capsys.readouterr().err.startswith(f"hmz chat: error: {says}")
    assert client.asked == []


@pytest.mark.parametrize(
    ("message", "flows"),
    [("$goal win", {"goal"}), ("$nothing here", set[str]()), ("/compact", set[str]())],
)
def test_a_line_is_read_with_no_catalogue_and_the_flow_its_dollar_names(
    workspace: mock.Mock,
    client: _Client,
    resolving: mock.Mock,
    message: str,
    flows: set[str],
) -> None:
    del workspace
    assert main(["chat", message]) == 0
    resolving.assert_called_once_with(message, catalog=(), flows=flows, prefer="flow")
    assert client.params("chat.start")["task"] == message


def test_a_start_the_daemon_refuses_is_said_as_it_refused(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.refuses["chat.start"] = Refused("no-such-cli is no harness", code=400)
    with pytest.raises(SystemExit) as raised:
        main(["chat", "-a", "no-such-cli/m", "hello"])
    assert raised.value.code == 2
    assert capsys.readouterr().err == "hmz chat: error: no-such-cli is no harness\n"
    assert client.methods() == ["chat.start"]


@pytest.mark.parametrize(
    ("raised", "says"),
    [
        (OSError("no socket"), "hmz: the daemon cannot be reached: no socket\n"),
        (
            OSError(errno.EADDRINUSE, "held by an older Humanize"),
            "hmz: held by an older Humanize\n",
        ),
    ],
)
def test_a_daemon_that_cannot_be_reached_is_said_and_exits_one(
    workspace: mock.Mock,
    resolving: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raised: OSError,
    says: str,
) -> None:
    del workspace, resolving
    monkeypatch.setattr(
        hmz.sdk.client.Client, "local", mock.Mock(side_effect=raised), raising=False
    )
    assert main(["chat", "hello"]) == 1
    assert capsys.readouterr().err == says


def test_a_first_turn_that_fails_says_what_the_harness_said_and_exits_one(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.said = [
        [
            {"type": "run", "state": "running", "turn": "running"},
            {"type": "ended", "how": "failed", "why": "HarnessError: it broke"},
        ]
    ]
    assert main(["chat", "hello"]) == 1
    assert "HarnessError: it broke" in capsys.readouterr().err
    assert "chat.say" not in client.methods()


def test_a_later_turn_that_fails_is_said_and_exits_one(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.said = [
        [
            {"type": "run", "state": "running", "turn": "running"},
            {"type": "event", "agent": "NeiKos", "session": "NeiKos/1",
             "kind": "failed", "key": "NeiKos/1", "text": "the turn broke"},
            {"type": "run", "state": "running", "turn": "done"},
        ]
    ]  # fmt: skip
    assert main(["chat", "--resume", "E", "and then?"]) == 1
    assert capsys.readouterr().err.endswith("the turn broke\n")
    # Between turns all the same, so it is ended as a turn that answered is.
    assert client.methods()[-1] == "chat.say"


def test_a_turn_replayed_after_the_snapshot_saying_it_is_done_is_done(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.said = [[_TURN[-1], *_TURN[2:-1]]]
    assert main(["chat", "hello"]) == 0
    assert capsys.readouterr().out == "answered\n"
    assert client.methods()[-1] == "chat.say"


def test_a_frontend_let_go_of_for_falling_behind_attaches_again_from_there(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.said = [
        [*_TURN[:3], {"type": "gone", "why": "too far behind; attach again"}],
        _TURN[3:],
    ]
    assert main(["chat", "hello"]) == 0
    assert client.methods() == ["chat.start", "epic.attach", "epic.attach", "chat.say"]
    assert client.params("epic.attach", 1)["since"] == {"epoch": "e1", "seq": 2}
    assert capsys.readouterr().out == "answered\n"


def test_a_host_that_goes_mid_turn_fails_the_chat(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.said = [[*_TURN[:3], {"type": "gone", "why": "the host went away"}]]
    assert main(["chat", "hello"]) == 1
    assert "hmz chat: the host went away" in capsys.readouterr().err
    assert "chat.say" not in client.methods()


def test_a_daemon_that_goes_without_a_word_ends_the_wait(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.said = [_TURN[:3]]

    def goes() -> None:
        client.ended = True

    client.attached = goes
    assert main(["chat", "hello"]) == 1
    assert "hmz chat: the daemon went away" in capsys.readouterr().err


def test_a_turn_done_is_done_however_the_chat_takes_its_end(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.refuses["chat.say"] = Refused(
        "this chat has folded away; carry it on with chat.start", code=409
    )
    assert main(["chat", "hello"]) == 0
    assert capsys.readouterr().out == "answered\n"


def test_what_the_host_printed_and_noticed_is_said_where_exec_says_it(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.said = [
        [
            {"type": "printed", "text": "a line"},
            {"type": "notice", "text": "moved to docker"},
            *_TURN,
        ]
    ]
    assert main(["chat", "hello"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "a line\nanswered\n"
    assert "hmz chat: moved to docker\n" in captured.err


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT])
def test_a_signal_leaves_the_chat_to_its_host_and_exits_as_the_signal_would(
    workspace: mock.Mock, client: _Client, signum: int
) -> None:
    del workspace
    was = signal.getsignal(signum)
    client.said = [_TURN[:-1]]
    client.attached = lambda: threading.Timer(
        0.1, os.kill, (os.getpid(), signum)
    ).start()
    with pytest.raises(SystemExit) as raised:
        main(["chat", "hello"])
    assert raised.value.code == 128 + signum
    # Left to its host: nothing ends it, and the session is let go of.
    assert client.methods() == ["chat.start", "epic.attach"]
    assert client.closed
    assert signal.getsignal(signum) == was


#: What the subscription says of a first line served with no turn, after the chat is opened:
#: the chat asks for its next line, and the snapshot never said its turn was running.
_OPENED: list[dict[str, Any]] = [_TURN[0], {**_TURN[2], "seq": 1}]


def _listens(text: str, seq: int) -> list[dict[str, Any]]:
    """The chat asking for its next line, `text` what it says back, and so between turns."""
    return [
        {"type": "asked", "seq": seq, "run": 1, "question": "q1", "role": "person",
         "text": text, "options": [], "mode": "listen", "key": ""},
        {"type": "run", "seq": seq + 1, "state": "running", "turn": "done"},
    ]  # fmt: skip


@pytest.fixture
def leaving(client: _Client) -> Generator[None]:
    """The daemon going away after a while, which ends a wait that nothing else would."""
    timer = threading.Timer(5, lambda: setattr(client, "ended", True))
    timer.start()
    yield
    timer.cancel()


@pytest.mark.usefixtures("leaving")
def test_a_command_run_with_no_turn_is_shown_with_what_it_printed_and_the_chat_ended(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    shell = {"type": "shell", "seq": 2, "run": 1, "key": "NeiKos/1", "command": "ls nope",
             "out": "hi\n", "err": "no nope\n", "status": 2}  # fmt: skip
    client.said = [[*_OPENED, shell, *_listens("", 3)]]

    assert main(["chat", "--", "!ls nope"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "hi\n"
    assert "ls nope" in captured.err
    assert "no nope" in captured.err
    assert "exit 2" in captured.err
    assert client.methods() == ["chat.start", "epic.attach", "chat.say"]


@pytest.mark.usefixtures("leaving")
def test_a_line_the_chat_refuses_is_said_why_and_the_chat_ended(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.said = [[*_OPENED, *_listens("no such command: /nope", 2)]]

    assert main(["chat", "/nope"]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hmz chat: no such command: /nope\n" in captured.err
    assert client.methods() == ["chat.start", "epic.attach", "chat.say"]


def test_what_a_turn_answered_is_not_said_again_where_the_chat_asks_for_its_next_line(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    client.said = [[*_TURN[:-1], *_listens("answered", 5)]]

    assert main(["chat", "hello"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "answered\n"
    assert "hmz chat: answered" not in captured.err


def test_what_the_chat_says_ahead_of_a_turns_answer_is_said_and_the_answer_once(
    workspace: mock.Mock, client: _Client, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    unkept = "This conversation could not be carried on (no conversation), so this is a new one."
    client.said = [[*_TURN[:-1], *_listens(f"{unkept}\n\nanswered", 5)]]

    assert main(["chat", "--resume", "E", "and then?"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "answered\n"
    assert f"hmz chat: {unkept}\n" in captured.err
    assert "hmz chat: answered" not in captured.err
