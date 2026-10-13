"""`hmz.web.notices`: what is news in how the runs stand, against how they stood."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from hmz.web.notices import Notices
from hmz.web.routing import Refusal


class Statuses:
    """How the runs stand, as each look is told: changed by the test between looks."""

    def __init__(self) -> None:
        self.now: dict[str, dict[str, Any]] = {}

    def __call__(self) -> dict[str, dict[str, Any]]:
        return {where: dict(status) for where, status in self.now.items()}

    def stands(
        self,
        workspace: str = "/w",
        *,
        pending: list[dict[str, Any]] | None = None,
        ended: dict[str, Any] | None = None,
    ) -> None:
        self.now[workspace] = {
            "state": "running",
            "flow": "ralph",
            "epic": "e1",
            "task": "fix it",
            "pending": pending or [],
            "ended": ended,
        }


def _ended(how: str, at: float | None = None, why: str = "") -> dict[str, Any]:
    """An epic that ended as `how`, at `at` -- or now."""
    return {
        "how": how,
        "why": why,
        "epic": "e1",
        "at": time.time() if at is None else at,
        "flow": "ralph",
        "task": "t",
    }


def _asked(question: str, mode: str = "ask") -> dict[str, Any]:
    return {"question": question, "role": "outworlder", "text": "which?", "mode": mode}


@pytest.fixture
def statuses() -> Statuses:
    return Statuses()


@pytest.fixture
def notices(statuses: Statuses) -> Notices:
    return Notices(statuses)


def test_what_stood_at_the_start_is_no_news(
    statuses: Statuses, notices: Notices
) -> None:
    statuses.stands(pending=[_asked("q1")], ended=_ended("done"))

    assert notices.look() == []
    assert notices.look() == []
    assert notices.since() == []
    assert notices.last == 0


@pytest.mark.parametrize(
    ("how", "kind"),
    [
        ("done", "done"),
        ("stopped", "stopped"),
        ("failed", "failed"),
        ("crashed", "failed"),
        ("budget", "failed"),
        ("refused", "failed"),
    ],
)
def test_an_epic_ending_is_a_notice_of_how(
    how: str, kind: str, statuses: Statuses, notices: Notices
) -> None:
    statuses.stands()
    notices.look()
    statuses.stands(ended=_ended(how, at=time.time() + 1, why="because"))

    (made,) = notices.look()

    assert made["kind"] == kind
    assert (made["workspace"], made["epic"], made["flow"], made["task"]) == (
        "/w",
        "e1",
        "ralph",
        "t",
    )
    assert (made["role"], made["text"]) == ("", "because")
    assert made["at"] > time.time()
    assert made["id"] == notices.last
    assert notices.look() == []


def test_another_epic_ending_after_is_another_notice(
    statuses: Statuses, notices: Notices
) -> None:
    statuses.stands(ended=_ended("done"))
    notices.look()
    statuses.stands(ended=_ended("failed", at=time.time() + 1))

    assert [one["kind"] for one in notices.look()] == ["failed"]


def test_a_question_is_asked_and_a_chat_waiting_is_listening(
    statuses: Statuses, notices: Notices
) -> None:
    statuses.stands(pending=[_asked("q1")])
    notices.look()
    statuses.stands(
        pending=[_asked("q1"), _asked("q2"), _asked("q3", "listen"), _asked("q4", "x")]
    )

    made = notices.look()

    assert [one["kind"] for one in made] == ["asked", "listening"]
    assert (made[0]["role"], made[0]["text"], made[0]["epic"]) == (
        "outworlder",
        "which?",
        "e1",
    )


def _chat(statuses: Statuses, turn: str, **said: Any) -> None:
    """The chat standing at a turn, as a host says one."""
    statuses.stands(**said)
    statuses.now["/w"] |= {"flow": "chat", "turn": turn}


def test_each_chat_turn_done_is_a_done_notice(
    statuses: Statuses, notices: Notices
) -> None:
    _chat(statuses, "running")
    notices.look()
    _chat(statuses, "done", pending=[_asked("q1", "listen")])
    (first,) = notices.look()
    _chat(statuses, "running")
    assert notices.look() == []
    # What the agent asks mid-turn is asked, not its turn done.
    _chat(statuses, "running", pending=[_asked("q2")])
    assert [one["kind"] for one in notices.look()] == ["asked"]
    _chat(statuses, "done", pending=[_asked("q3", "listen")])
    (second,) = notices.look()

    assert (first["kind"], first["flow"], first["text"]) == ("done", "chat", "which?")
    assert second["kind"] == "done"


@pytest.mark.parametrize(
    ("turn", "how", "kinds"),
    [
        # Left, between turns or mid-turn, it is no news.
        ("done", "stopped", []),
        ("running", "stopped", []),
        # Its last turn told done already, its end is told nothing again.
        ("done", "done", []),
        # Ended on a turn nothing had told done, that turn is.
        ("running", "done", ["done"]),
        ("done", "failed", ["failed"]),
        ("running", "crashed", ["failed"]),
    ],
)
def test_a_chat_ending_is_news_only_where_it_failed_or_ended_a_turn(
    turn: str, how: str, kinds: list[str], statuses: Statuses, notices: Notices
) -> None:
    _chat(statuses, turn)
    notices.look()
    ended = _ended(how, at=time.time() + 1) | {"flow": "chat"}
    _chat(statuses, "done", ended=ended)

    assert [one["kind"] for one in notices.look()] == kinds


def test_a_workspace_first_seen_later_is_news(
    statuses: Statuses, notices: Notices
) -> None:
    notices.look()
    statuses.stands("/v", ended=_ended("done"))

    assert [one["workspace"] for one in notices.look()] == ["/v"]


def test_an_epic_that_ended_before_the_start_is_no_news_wherever_it_is_seen(
    statuses: Statuses, notices: Notices
) -> None:
    notices.look()
    statuses.stands("/v", ended=_ended("done", at=1.0))

    assert notices.look() == []


def test_a_crash_is_said_in_the_last_line_of_why(
    statuses: Statuses, notices: Notices
) -> None:
    notices.look()
    statuses.stands(ended=_ended("crashed", why="Traceback:\n  here\nValueError: no\n"))

    assert notices.look()[0]["text"] == "ValueError: no"


def test_another_host_asking_a_question_of_the_same_id_is_news(
    statuses: Statuses, notices: Notices
) -> None:
    statuses.stands(pending=[_asked("q1")])
    statuses.now["/w"] |= {"pid": 1, "started": "then"}
    notices.look()
    statuses.stands(pending=[_asked("q1")])
    statuses.now["/w"] |= {"pid": 2, "started": "now"}

    assert [one["kind"] for one in notices.look()] == ["asked"]


def test_a_host_that_would_not_answer_is_not_taken_for_one_that_went(
    statuses: Statuses, notices: Notices
) -> None:
    ended = _ended("done", at=time.time() + 1)
    statuses.stands()
    notices.look()
    statuses.stands(ended=ended)
    notices.look()
    statuses.now["/w"] = {"attached": 0, "flows": [], "calls": []}
    notices.look()
    statuses.stands(ended=ended)

    assert notices.look() == []


def test_notices_are_numbered_and_read_after_the_last_heard(
    statuses: Statuses, notices: Notices
) -> None:
    statuses.stands()
    notices.look()
    statuses.stands(pending=[_asked("q1")])
    (first,) = notices.look()
    statuses.stands(pending=[_asked("q2")])
    (second,) = notices.look()

    assert second["id"] > first["id"]
    assert [one["id"] for one in notices.since()] == [first["id"], second["id"]]
    assert notices.since(str(first["id"])) == [second]
    assert notices.since(second["id"]) == []
    with pytest.raises(Refusal):
        notices.since("soon")


def _fails(_one: dict[str, Any]) -> None:
    raise RuntimeError


def test_a_listener_hears_each_notice_until_it_stops(
    statuses: Statuses, notices: Notices
) -> None:
    heard: list[dict[str, Any]] = []
    statuses.stands()
    notices.look()
    unheard = notices.heard(heard.append)
    notices.heard(_fails)
    statuses.stands(pending=[_asked("q1")])
    notices.look()
    unheard()
    statuses.stands(pending=[_asked("q2")])
    notices.look()

    assert [one["kind"] for one in heard] == ["asked"]


def test_only_the_last_two_hundred_are_kept(
    statuses: Statuses, notices: Notices
) -> None:
    statuses.stands()
    notices.look()
    for one in range(205):
        statuses.stands(pending=[_asked(f"q{one}")])
        notices.look()

    assert len(notices.since()) == 200


def test_a_stream_carries_on_after_the_last_heard(
    statuses: Statuses, notices: Notices
) -> None:
    statuses.stands()
    notices.look()
    statuses.stands(pending=[_asked("q1")])
    (first,) = notices.look()
    going = threading.Event()
    events = notices.stream().events("0", going)

    assert next(events) == (str(first["id"]), "notice", first)
    statuses.stands(pending=[_asked("q2")])
    (second,) = notices.look()
    assert next(events) == (str(second["id"]), "notice", second)
    notices.close()
    assert list(events) == []


def test_a_stream_heard_from_nothing_starts_from_now(
    statuses: Statuses, notices: Notices
) -> None:
    statuses.stands()
    notices.look()
    statuses.stands(pending=[_asked("q1")])
    notices.look()
    events = notices.stream().events("", threading.Event())
    statuses.stands(pending=[_asked("q2")])
    (second,) = notices.look()

    assert next(events) == (str(second["id"]), "notice", second)
