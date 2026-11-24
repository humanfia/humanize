"""`hmz epic`: an epic started, followed and steered through a client that is mocked."""

from __future__ import annotations

import io
import json
from typing import Any
from unittest import mock

import pytest

import hmz.sdk
from hmz.cli import main, tree


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> mock.MagicMock:
    """The client the command reaches."""
    made = mock.MagicMock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=made))
    return made


@pytest.fixture
def attached(client: mock.MagicMock) -> mock.MagicMock:
    """The frontend `epic.attach` answers, which is the block's own."""
    held = client.epics.attach.return_value
    held.__enter__.return_value = held
    held.over = False
    held.client = "c1"
    return held


def _told(attached: mock.MagicMock, *messages: dict[str, Any]) -> None:
    """Has the host tell the frontend these, and then nothing for good."""
    left = list(messages)

    def tells(_seconds: float | None = None) -> dict[str, Any] | None:
        if left:
            return left.pop(0)
        attached.over = True
        return None

    attached.next.side_effect = tells
    attached.__iter__.side_effect = lambda: iter(messages)


def test_starting_says_what_the_line_gave_and_returns_at_once(
    client: mock.MagicMock,
    attached: mock.MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    attached.start.return_value = mock.Mock(run=2, slot="exec:ab", workspace="/w")
    _told(attached, {"type": "away", "all": False}, {"type": "live", "seq": 0})

    assert (
        main(
            [
                "epic", "start", "goal", "win", "-w", "/w", "--slot", "exec:",
                "-a", "worker=claude/m:low,reviewer=codex/gpt-5", "-e", "repo=local",
                "-p", "rounds=3,budget.cost=2", "--resume-from", "e1", "--no-backup",
                "--profile-flow", "--remember", "--away",
            ]
        )
        == 0
    )  # fmt: skip

    assert capsys.readouterr().out == "Epic 2 started in /w, slot exec:ab.\n"
    client.epics.attach.assert_called_once_with(
        "/w", slot="exec:", replay=False, scratch=None
    )
    attached.afk.assert_called_once_with(on=True)
    (flow, task), said = attached.start.call_args
    assert (flow, task) == ("goal", "win")
    assert said["agents"] == {"worker": "claude/m:low", "reviewer": "codex/gpt-5"}
    assert said["envs"] == {"repo": "local"}
    assert said["params"] == {"rounds": "3"}
    assert said["budget"]["cost"] == 2.0
    assert (said["resume"], said["backup"]) == ("e1", [])
    assert (said["profile_flow"], said["profile_environment"]) == (True, None)
    assert said["remember"] is True
    attached.next.assert_not_called()


def test_a_start_in_no_folder_names_no_workspace(
    client: mock.MagicMock,
    attached: mock.MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    attached.start.return_value = mock.Mock(run=1, slot="", workspace="/tmp/n")

    assert main(["epic", "start", "goal", "--scratch", "--resume", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "run": 1,
        "slot": "",
        "workspace": "/tmp/n",
    }
    client.epics.attach.assert_called_once_with(
        None, slot="", replay=False, scratch=True
    )
    _, said = attached.start.call_args
    assert (said["resume"], said["backup"], said["budget"]) == (True, None, None)
    attached.afk.assert_not_called()


@pytest.mark.parametrize(
    "wrong",
    [
        ["-a", "claude/m"],
        ["-a", "worker=claude/m", "-a", "worker=codex/m"],
        ["-p", "budget.nope=1"],
        ["-p", "rounds"],
    ],
)
def test_a_line_that_cannot_be_read_starts_nothing(
    client: mock.MagicMock, capsys: pytest.CaptureFixture[str], wrong: list[str]
) -> None:
    assert main(["epic", "start", "goal", *wrong]) == 2

    said = capsys.readouterr()
    assert said.err.startswith("hmz epic start: ")
    assert said.err.endswith("Run `hmz epic start --help` for help.\n")
    client.epics.attach.assert_not_called()

    assert main(["epic", "start", "goal", *wrong, "--json"]) == 2
    said = capsys.readouterr()
    assert json.loads(said.out)["error"]["code"] == 400
    assert said.err == ""


def test_a_start_refused_leaves_the_roles_as_they_were(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    attached.start.side_effect = hmz.sdk.Refused("a flow is already running", code=409)
    _told(attached, {"type": "away", "all": False}, {"type": "live", "seq": 0})

    assert main(["epic", "start", "goal", "--away"]) == 1

    assert capsys.readouterr().err == "hmz epic start: a flow is already running\n"
    assert attached.afk.call_args_list == [mock.call(on=True), mock.call(on=False)]

    # Roles that were away already are not set, and so not set back.
    attached.afk.reset_mock()
    _told(attached, {"type": "away", "all": True}, {"type": "live", "seq": 0})
    assert main(["epic", "start", "goal", "--away"]) == 1
    attached.afk.assert_not_called()


def test_a_command_but_start_attaches_only_to_a_host_that_is_held(
    client: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.hosts.status.side_effect = hmz.sdk.Refused(
        "no runs are held in /w", code=404
    )

    for line in (["say", "hello"], ["stop"], ["attach"], ["board"], ["afk"]):
        assert main(["epic", *line, "-w", "/w"]) == 1
        assert capsys.readouterr().err == (
            f"hmz epic {line[0]}: no runs are held in /w\n"
        )
    client.epics.attach.assert_not_called()


def test_a_board_not_told_before_the_host_lets_go_is_not_an_empty_one(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    _told(attached, {"type": "gone", "why": "the host was closed"})

    assert main(["epic", "board"]) == 1

    assert capsys.readouterr().err == "hmz epic board: This host cannot be reached.\n"


def test_a_start_followed_is_written_until_the_epic_ends(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    attached.start.return_value = mock.Mock(run=1, slot="", workspace="/w")
    _told(
        attached,
        {"type": "run", "state": "idle"},
        {"type": "live", "seq": 0},
        {"type": "started", "by": "me", "flow": "goal", "task": "win"},
        {"type": "asked", "question": "q1", "role": "human", "text": "which?",
         "options": ["a", "b"], "schema": None},
        {"type": "answered", "question": "q1", "by": "you", "text": "a"},
        {"type": "said", "by": "you", "text": "go on"},
        {"type": "withdrawn", "question": "q2", "why": "away"},
        {"type": "notice", "text": "a notice"},
        {"type": "printed", "text": "printed by the flow"},
        {"type": "stopping", "by": "you"},
        {"type": "ended", "how": "failed", "why": "ValueError: no"},
        {"type": "never"},
    )  # fmt: skip

    assert main(["epic", "start", "goal", "-w", "/w", "--follow"]) == 1

    said = capsys.readouterr()
    assert said.out == "printed by the flow\n"
    assert said.err.splitlines() == [
        "Epic 1 started in /w.",
        "me started goal: win",
        "human asks (q1): which?",
        "  1. a",
        "  2. b",
        "you answered: a",
        "you said: go on",
        "Question q2 was withdrawn (away).",
        "a notice",
        "you is stopping the epic.",
        "The epic ended: failed.",
        "ValueError: no",
    ]


def test_attaching_to_a_host_with_no_epic_going_says_so_and_ends(
    client: mock.MagicMock,
    attached: mock.MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _told(
        attached,
        {"type": "ended", "seq": 4, "how": "failed", "why": "then"},
        {"type": "run", "state": "idle"},
        {"type": "live", "seq": 4},
    )

    assert main(["epic", "attach", "-w", "/w"]) == 0

    assert capsys.readouterr().err.splitlines()[-1] == "No epic is going here."
    client.epics.attach.assert_called_once_with("/w", slot="", replay=True)
    attached.__exit__.assert_called_once()


def test_attaching_as_json_writes_each_message_a_line_until_the_end(
    client: mock.MagicMock,
    attached: mock.MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    told: list[dict[str, Any]] = [
        {"type": "run", "state": "running"},
        {"type": "live", "seq": 1},
        {"type": "ended", "seq": 2, "how": "done", "why": ""},
    ]
    _told(attached, *told, {"type": "never"})

    assert main(["epic", "attach", "-w", "/w", "--no-replay", "--json"]) == 0

    said = capsys.readouterr()
    assert [json.loads(line) for line in said.out.splitlines()] == told
    assert said.err == ""
    client.epics.attach.assert_called_once_with("/w", slot="", replay=False)


def test_a_host_that_lets_go_and_an_interrupt_end_the_following(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    _told(
        attached,
        {"type": "run", "state": "running"},
        {"type": "live", "seq": 1},
        {"type": "gone", "why": "the host was closed"},
    )
    assert main(["epic", "attach"]) == 1
    assert capsys.readouterr().err == "the host was closed\n"

    attached.next.side_effect = KeyboardInterrupt
    assert main(["epic", "attach"]) == 130
    attached.__exit__.assert_called()

    attached.start.side_effect = KeyboardInterrupt
    assert main(["epic", "start", "goal"]) == 130


def test_claiming_answers_the_roles_questions_with_what_is_typed(
    attached: mock.MagicMock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("first\n\nsecond\n"))
    asked = {"question": "q1", "role": "human"}
    theirs = {"question": "q7", "role": "other"}
    misfit = hmz.sdk.Refused("the answer does not fit: no", code=400)
    attached.answer.side_effect = [misfit, None]

    def tells(_seconds: float | None = None) -> dict[str, Any] | None:
        # Nothing more is told until both lines typed have been said.
        if attached.next.call_count == 1:
            return {"type": "pending", "pending": [asked, theirs]}
        if attached.answer.call_count < 2:
            return None
        if not any(one.args[0].get("type") == "live" for one in told):
            told.append(mock.call({"type": "live"}))
            return {"type": "live", "seq": 1}
        return {"type": "ended", "how": "done", "why": ""}

    told: list[Any] = []
    attached.next.side_effect = tells

    assert main(["epic", "claim", "human", "--take", "--no-replay"]) == 0

    attached.claim.assert_called_once_with("human", take=True)
    assert attached.answer.call_args_list == [
        mock.call("q1", "first", wait=30.0),
        mock.call("q1", "second", wait=30.0),
    ]
    assert capsys.readouterr().err.splitlines() == [
        "Claimed.",
        "the answer does not fit: no",
        "The epic ended: done.",
    ]


def test_a_line_is_said_to_whoever_is_named(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["epic", "say", "hello"]) == 0
    assert capsys.readouterr().out == "Sent.\n"
    attached.say.assert_called_once_with("hello", to=None)

    assert main(["epic", "say", "hello", "--to", "NeiKos", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"text": "hello", "to": "NeiKos"}
    attached.say.assert_called_with("hello", to="NeiKos")


def test_the_only_question_waiting_is_answered_where_none_is_named(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    attached.status.return_value = {"pending": [{"question": "q4"}]}

    assert main(["epic", "answer", "yes"]) == 0
    assert capsys.readouterr().out == "Answered\n"
    attached.answer.assert_called_once_with("q4", "yes", value=None)

    assert main(["epic", "answer", "-q", "q2", "--value", '{"a": 1}', "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"question": "q2"}
    attached.answer.assert_called_with("q2", None, value={"a": 1})


def test_an_answer_with_no_one_question_to_take_it_is_refused(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    attached.status.return_value = {"pending": []}
    assert main(["epic", "answer", "yes"]) == 1
    assert capsys.readouterr().err == "hmz epic answer: No question is waiting.\n"

    attached.status.return_value = {"pending": [{"question": "q1"}, {"question": "q2"}]}
    assert main(["epic", "answer", "yes", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": {
            "code": 409,
            "message": "2 questions are waiting: name one with `--question` (q1, q2).",
        }
    }

    assert main(["epic", "answer", "--value", "{bad"]) == 2
    assert capsys.readouterr().err.startswith("hmz epic answer: `--value` takes JSON.")
    attached.answer.assert_not_called()


def test_an_epic_is_stopped_or_forced(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["epic", "stop"]) == 0
    assert capsys.readouterr().out == "Stopping…\n"
    attached.stop.assert_called_once_with()

    attached.force.return_value = 1
    assert main(["epic", "stop", "--force"]) == 0
    assert capsys.readouterr().out == "Force stopped (1 session closed).\n"

    attached.force.return_value = 2
    assert main(["epic", "stop", "--force", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"forced": True, "closed": 2}


def test_the_board_is_read_written_and_a_line_removed(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    items = [
        {"key": "deadline", "value": "Friday", "whose": "user", "by": "me", "at": 1},
        {"key": "plan", "value": "a", "whose": "flow", "by": "NeiKos", "at": 2},
    ]
    _told(attached, {"type": "board", "items": items}, {"type": "live", "seq": 0})

    assert main(["epic", "board"]) == 0
    assert capsys.readouterr().out == (
        "deadline  Friday  user  me\nplan      a       flow  NeiKos\n"
    )
    assert main(["epic", "board", "plan", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"items": [items[1]]}

    assert main(["epic", "board", "deadline", "Monday"]) == 0
    assert capsys.readouterr().out == "Wrote deadline on the board.\n"
    attached.board.assert_called_with("deadline", "Monday")

    assert main(["epic", "board", "deadline", "--remove", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"key": "deadline", "value": ""}
    attached.board.assert_called_with("deadline", "")

    assert main(["epic", "board", "--remove"]) == 2
    assert "`--remove` takes the key of a line." in capsys.readouterr().err


def test_an_epic_with_no_board_has_nothing_on_it(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    _told(attached, {"type": "board", "items": None}, {"type": "live", "seq": 0})

    assert main(["epic", "board"]) == 0
    assert capsys.readouterr().out == "Nothing is on the board yet.\n"

    assert main(["epic", "board", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"items": None}


def test_a_role_is_taken_and_released_and_set_away_or_back(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["epic", "release", "reviewer"]) == 0
    assert capsys.readouterr().out == "Released reviewer.\n"
    assert attached.mock_calls[1:3] == [
        mock.call.claim("reviewer", take=True),
        mock.call.release("reviewer"),
    ]

    assert main(["epic", "afk"]) == 0
    assert capsys.readouterr().out == "Away\n"
    attached.afk.assert_called_with(on=True, role=None)

    assert main(["epic", "afk", "reviewer", "--back", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"away": False, "role": "reviewer"}
    attached.afk.assert_called_with(on=False, role="reviewer")


def test_the_status_is_read_without_attaching(
    client: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.hosts.status.return_value = {
        "state": "running",
        "flow": "goal",
        "epic": "e1",
        "task": "win",
        "pending": [{"question": "q1", "role": "human", "text": "which?"}],
        "turn": "left out",
    }

    assert main(["epic", "status", "-w", "/w", "--slot", "exec:ab"]) == 0
    assert capsys.readouterr().out == "running  goal  e1  win\nq1  human  which?\n"
    client.hosts.status.assert_called_with("/w", "exec:ab")

    assert main(["epic", "status", "-w", "/w", "--json"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert (said["state"], said["budget"], "turn" in said) == ("running", None, False)
    client.epics.attach.assert_not_called()


def test_a_refusal_is_said_in_the_hosts_words(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    attached.say.side_effect = hmz.sdk.Refused("no flow is running to say it to")

    assert main(["epic", "say", "hello"]) == 1

    assert capsys.readouterr().err == "hmz epic say: no flow is running to say it to\n"
    attached.__exit__.assert_called_once()


def test_the_face_of_a_waiting_question_is_printed_as_the_flow_wrote_it(
    attached: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    _told(
        attached,
        {"type": "welcome"},
        {
            "type": "pending",
            "pending": [
                {"question": "q1", "face": None},
                {"question": "q3", "face": {"hash": "abc", "title": "Review"}},
            ],
        },
        {"type": "live", "seq": 4},
    )
    attached.face.return_value = mock.Mock(html="<p>pick</p>", title="Review")

    assert main(["epic", "face", "q3"]) == 0
    # To the last byte, with no line feed of this command's added.
    assert capsys.readouterr().out == "<p>pick</p>"
    attached.face.assert_called_once_with("abc")

    assert main(["epic", "face", "q3", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "question": "q3",
        "title": "Review",
        "html": "<p>pick</p>",
    }


@pytest.mark.parametrize(
    ("question", "why"),
    [("q1", "Question q1 has no face."), ("q9", "Question q9 is not waiting.")],
)
def test_a_question_with_no_face_to_print_is_refused(
    question: str,
    why: str,
    attached: mock.MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _told(
        attached,
        {"type": "pending", "pending": [{"question": "q1", "face": None}]},
        {"type": "live", "seq": 4},
    )

    assert main(["epic", "face", question, "--json"]) == 1

    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": 404, "message": why}
    }
    attached.face.assert_not_called()


def test_quitting_closes_the_host_the_frontend_is_attached_to(
    client: mock.MagicMock,
    attached: mock.MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    attached.workspace, attached.slot = "/w", "exec:ab"

    assert main(["epic", "quit", "-w", "/w", "--slot", "exec:ab"]) == 0
    assert capsys.readouterr().out == "Host closed.\n"
    client.hosts.status.assert_called_once_with("/w", "exec:ab")
    attached.quit.assert_called_once_with()

    assert main(["epic", "quit", "-w", "/w", "--slot", "exec:ab", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"workspace": "/w", "slot": "exec:ab"}
