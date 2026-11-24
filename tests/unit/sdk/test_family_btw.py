"""`client.btw`, `client.aichan` and `client.notices`: their calls, through a mocked client."""

from __future__ import annotations

import threading
from typing import Any
from unittest import mock

import pytest

from hmz.sdk import Refused
from hmz.sdk.families import Subscription
from hmz.sdk.families.aichan import AiChan, Conversation, Made, Reply
from hmz.sdk.families.btw import Answer, Aside, Session, SideQuestions
from hmz.sdk.families.notices import KINDS, Notice, Notices

ROW: dict[str, Any] = {
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

NOTICE: dict[str, Any] = {
    "id": 7,
    "kind": "asked",
    "workspace": "/w",
    "slot": "",
    "epic": "e1",
    "chat": "",
    "flow": "asks",
    "task": "plan",
    "role": "planner",
    "text": "which?",
    "at": 12.5,
}


@pytest.fixture
def client() -> mock.Mock:
    made = mock.Mock(spec=["call", "heard", "wait"])
    made.wait.return_value = False
    return made


def _called(client: mock.Mock) -> list[tuple[str, dict[str, Any]]]:
    """Every call made, as its method and parameters."""
    return [(one.args[0], one.args[1]) for one in client.call.call_args_list]


def test_each_family_names_the_methods_it_makes() -> None:
    assert SideQuestions.METHODS == ("btw.list", "btw.ask", "btw.leave")
    assert AiChan.METHODS == (
        "aichan.create",
        "aichan.list",
        "aichan.rename",
        "aichan.forget",
    )
    assert Notices.METHODS == (
        "notices.list",
        "notices.subscribe",
        "notices.unsubscribe",
    )


# ------------------------------------------------------------------------ side questions


def test_a_side_question_is_asked_in_a_side_conversation_named_here(
    client: mock.Mock,
) -> None:
    def answers(_method: str, params: dict[str, Any], **_: Any) -> dict[str, Any]:
        return {**params, "answer": "papaya"}

    client.call.side_effect = answers

    answer = SideQuestions(client).ask("/w", "the word?", to="Ada/1", chat="c1", wait=9)

    ((method, sent),) = _called(client)
    assert method == "btw.ask"
    assert sent == {
        "workspace": "/w",
        "question": "the word?",
        "aside": answer.aside,
        "to": "Ada/1",
        "chat": "c1",
    }
    assert len(answer.aside) == 8
    assert answer == Answer(answer.aside, "Ada/1", "the word?", "papaya")
    assert client.call.call_args.kwargs == {"idem": None, "seconds": 9}


def test_a_later_question_goes_on_in_the_side_conversation_named(
    client: mock.Mock,
) -> None:
    client.call.return_value = {
        "aside": "a1",
        "to": "Ada/1",
        "question": "again?",
        "answer": "yes",
    }

    SideQuestions(client).ask("/w", "again?", to="Ada/1", aside="a1", epic="e1")

    assert _called(client) == [
        (
            "btw.ask",
            {
                "workspace": "/w",
                "question": "again?",
                "aside": "a1",
                "to": "Ada/1",
                "epic": "e1",
            },
        )
    ]


def test_side_conversations_are_listed_with_what_each_answered(
    client: mock.Mock,
) -> None:
    said = {"aside": "a1", "to": "Ada/1", "question": "the word?", "answer": "papaya"}
    client.call.return_value = {
        "asides": [{"aside": "a1", "to": "Ada/1", "question": "", "said": [said]}]
    }

    assert SideQuestions(client).list("/w", chat="c1") == [
        Aside("a1", "Ada/1", "", (Answer("a1", "Ada/1", "the word?", "papaya"),))
    ]
    assert _called(client) == [("btw.list", {"workspace": "/w", "chat": "c1"})]


def test_one_side_conversation_is_left_or_every_one(client: mock.Mock) -> None:
    client.call.return_value = {}

    SideQuestions(client).leave("/w", "a1")
    SideQuestions(client).leave("/w")

    assert _called(client) == [
        ("btw.leave", {"workspace": "/w", "aside": "a1"}),
        ("btw.leave", {"workspace": "/w"}),
    ]


def test_sessions_are_keyed_as_the_epic_going_keyed_them(client: mock.Mock) -> None:
    client.call.return_value = {
        "sessions": [
            {"agent": "Ada", "backend": "claude"},
            {"agent": "Bo", "backend": "codex"},
            {"agent": "Ada", "backend": "claude"},
        ]
    }

    assert SideQuestions(client).sessions(epic="e1") == [
        Session("Ada/1", "Ada", "claude"),
        Session("Bo/1", "Bo", "codex"),
        Session("Ada/2", "Ada", "claude"),
    ]
    SideQuestions(client).sessions(chat="c1")

    assert _called(client) == [
        ("runs.get", {"name": "e1"}),
        ("chat.get", {"chat": "c1"}),
    ]


@pytest.mark.parametrize("named", [{}, {"epic": "e1", "chat": "c1"}])
def test_sessions_are_those_of_an_epic_or_of_a_chat(
    client: mock.Mock, named: dict[str, str]
) -> None:
    with pytest.raises(ValueError, match="an epic or a chat"):
        SideQuestions(client).sessions(**named)

    client.call.assert_not_called()


# ------------------------------------------------------------------------------- Ai-chan


def test_a_conversation_is_made_with_what_was_said_of_it(client: mock.Mock) -> None:
    client.call.return_value = {"id": 3, "workspace": "/ai", "slot": "ai:ab"}

    made = AiChan(client).create(
        "hello", scope="workspace", workspace="/w", preset="read-only", idem="k"
    )

    assert made == Made(3, "/ai", "ai:ab")
    client.call.assert_called_once_with(
        "aichan.create",
        {
            "scope": "workspace",
            "workspace": "/w",
            "preset": "read-only",
            "task": "hello",
        },
        idem="k",
        seconds=None,
    )


def test_conversations_are_listed_renamed_and_forgotten(client: mock.Mock) -> None:
    client.call.return_value = {"conversations": [ROW]}
    family = AiChan(client)

    (one,) = family.list()
    assert one == Conversation(**ROW)
    # What an earlier hmz wrote nothing of is said as nothing.
    client.call.return_value = {"conversations": [{**ROW, "created": None}]}
    assert family.list()[0].created == ""
    client.call.return_value = {"conversations": [ROW]}
    assert family.get(3) == one
    with pytest.raises(Refused, match=r"There is no Ai-chan #4\.") as refused:
        family.get(4)
    assert refused.value.code == 404

    client.call.reset_mock()
    client.call.return_value = {}
    family.rename(3, "another")
    family.forget(3)
    assert _called(client) == [
        ("aichan.rename", {"id": 3, "title": "another"}),
        ("aichan.forget", {"id": 3}),
    ]


class Host:
    """An Ai-chan host as a client's calls find it: what waits, and what a line said does."""

    def __init__(self, *, turn: str = "done", pending: list[dict[str, Any]]) -> None:
        self.status: dict[str, Any] = {"turn": turn, "pending": pending, "ended": None}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.conversations = [ROW]

    def __call__(self, method: str, params: dict[str, Any], **_: Any) -> Any:
        self.calls.append((method, params))
        if method == "aichan.list":
            return {"conversations": self.conversations}
        if method == "epic.attach":
            return {"sub": "s1", "client": "c1"}
        if method == "epic.status":
            return self.status
        if method in ("epic.answer", "epic.say"):
            # She answers at once: her turn is over on another question, her next wait.
            self.status = {
                "turn": "done",
                "pending": [
                    {
                        "question": "q2",
                        "mode": "listen",
                        "text": f"heard {params['text']}",
                    }
                ],
            }
        return {}

    def made(self) -> list[str]:
        """The methods called, without the looks at how the host stands."""
        return [method for method, _ in self.calls if method != "epic.status"]


def test_a_line_answers_what_she_waits_on_and_her_answer_is_heard(
    client: mock.Mock,
) -> None:
    host = Host(pending=[{"question": "q1", "mode": "listen", "text": "hi"}])
    client.call.side_effect = host

    assert AiChan(client).say(3, "and then?") == Reply("heard and then?", "listen")

    assert host.made() == ["aichan.list", "epic.attach", "epic.answer", "epic.detach"]
    assert ("epic.attach", {"workspace": "/ai", "slot": "ai:ab", "replay": False}) in (
        host.calls
    )
    assert ("epic.answer", {"sub": "s1", "question": "q1", "text": "and then?"}) in (
        host.calls
    )


def test_a_line_is_said_into_her_turn_where_she_waits_on_nothing(
    client: mock.Mock,
) -> None:
    host = Host(turn="running", pending=[])
    client.call.side_effect = host

    assert AiChan(client).say(3, "also this", hear=False) is None

    assert host.made() == ["aichan.list", "epic.attach", "epic.say", "epic.detach"]
    assert ("epic.say", {"sub": "s1", "text": "also this"}) in host.calls


def test_her_host_is_let_go_of_however_the_line_went(client: mock.Mock) -> None:
    host = Host(pending=[])
    host.status = {"pending": [], "ended": {"how": "failed", "why": "no key"}}
    client.call.side_effect = host

    with pytest.raises(Refused, match="no key") as refused:
        AiChan(client).say(3, "hello?")

    assert refused.value.code == 409
    assert host.made() == ["aichan.list", "epic.attach", "epic.detach"]


def test_a_conversation_that_is_over_however_it_ended_is_not_waited_on(
    client: mock.Mock,
) -> None:
    host = Host(pending=[])
    host.status = {"turn": "done", "pending": [], "ended": {"how": "crashed"}}
    client.call.side_effect = host

    with pytest.raises(Refused, match="This conversation failed"):
        AiChan(client).heard(3)


def test_an_answer_that_does_not_come_in_time_is_given_up_on(
    client: mock.Mock,
) -> None:
    host = Host(turn="running", pending=[])
    client.call.side_effect = host

    with pytest.raises(TimeoutError):
        AiChan(client).heard(3, wait=0)

    assert host.made()[-1] == "epic.detach"


def test_what_she_waits_on_is_heard_without_saying_anything(client: mock.Mock) -> None:
    host = Host(pending=[{"question": "q1", "mode": "choose", "text": "which one?"}])
    client.call.side_effect = host

    assert AiChan(client).heard(3) == Reply("which one?", "choose")
    assert host.made() == ["aichan.list", "epic.attach", "epic.detach"]


def test_her_open_turn_is_stopped_and_a_folded_one_has_none(client: mock.Mock) -> None:
    host = Host(turn="running", pending=[])
    host.conversations = [{**ROW, "state": "running"}]
    client.call.side_effect = host

    AiChan(client).stop(3)

    assert host.made() == ["aichan.list", "epic.attach", "epic.stop", "epic.detach"]

    host.calls.clear()
    host.conversations = [{**ROW, "state": "folded"}]
    with pytest.raises(Refused, match="nothing to stop"):
        AiChan(client).stop(3)
    assert host.made() == ["aichan.list"]


# ------------------------------------------------------------------------------- notices


def _hears(client: mock.Mock) -> Any:
    """What the client was given to tell notifications to."""
    (listener,), _ = client.heard.call_args
    return listener


def test_notices_are_listed_after_one_and_the_newest_is_numbered(
    client: mock.Mock,
) -> None:
    client.call.return_value = {"notices": [NOTICE], "last": 7}
    family = Notices(client)

    assert family.list(5) == [Notice(**NOTICE)]
    assert family.last() == 7
    assert _called(client) == [("notices.list", {"after": 5}), ("notices.list", {})]
    # Both of one call, so that the newest is the newest of what was listed.
    assert family.kept(5) == ([Notice(**NOTICE)], 7)
    assert Notice(**NOTICE).kind in KINDS


def test_a_subscription_is_told_each_notice_and_ended(client: mock.Mock) -> None:
    client.call.return_value = {"sub": "n1", "last": 7}
    family = Notices(client)

    heard = family.subscribe(after=7)
    _hears(client)("notices.event", {"sub": "n1", "notice": NOTICE})

    assert isinstance(heard, Subscription)
    # Listening before it subscribed: what is kept after `after` is told at once.
    assert [name for name, *_ in client.mock_calls[:2]] == ["heard", "call"]
    assert heard.next(1) == {"sub": "n1", "notice": NOTICE}
    client.call.return_value = {}
    family.unsubscribe(heard)
    assert _called(client) == [
        ("notices.subscribe", {"after": 7}),
        ("notices.unsubscribe", {"sub": "n1"}),
    ]
    # Closed too: nothing more is waited for.
    assert list(heard) == []


def test_following_takes_up_again_after_the_last_heard_where_it_fell_behind(
    client: mock.Mock,
) -> None:
    subs = iter(["n1", "n2"])

    def answers(method: str, _params: dict[str, Any], **_: Any) -> dict[str, Any]:
        return {"sub": next(subs), "last": 6} if method == "notices.subscribe" else {}

    client.call.side_effect = answers
    following = Notices(client).follow()

    # Subscribed by the first step, which then waits: what is said meanwhile is kept.
    def tells() -> None:
        while client.heard.call_args is None:
            pass
        hears = _hears(client)

        def said(sub: str, **what: Any) -> None:
            hears("notices.event", {"sub": sub, **what})

        said("n1", notice=NOTICE)
        said("n1", gone="too far behind; subscribe again")
        said("n2", notice={**NOTICE, "id": 8})

    threading.Thread(target=tells, daemon=True).start()

    assert [next(following).id, next(following).id] == [7, 8]
    following.close()

    assert _called(client) == [
        ("notices.subscribe", {}),
        ("notices.subscribe", {"after": 7}),
        ("notices.unsubscribe", {"sub": "n2"}),
    ]


def test_following_ends_once_the_session_has(client: mock.Mock) -> None:
    client.call.return_value = {"sub": "n1", "last": 0}
    client.wait.return_value = True
    following = Notices(client).follow()

    with pytest.raises(ConnectionError):
        next(following)

    assert _called(client)[-1] == ("notices.unsubscribe", {"sub": "n1"})
