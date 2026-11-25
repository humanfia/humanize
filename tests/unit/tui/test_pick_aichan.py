"""`/ai`'s sheets: Ai-chan's conversations, and the form a new one is asked on."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from hmz.tui.pick import (
    AI_NEW,
    AiAsked,
    AiChanNew,
    AiChans,
    AiForgets,
    AiMarks,
    AiRenames,
    ai_chan,
    ai_scope,
    nous_named,
)

_ONE: dict[str, Any] = {
    "id": 3,
    "title": "what is going on",
    "scope": "epic",
    "workspace": "/w",
    "epic": "Ab_1",
    "nous": "claude/m:low",
    "preset": "read-only",
    "slot": "ai:abc",
    "state": "folded",
    "created": "2026-11-17T00:00:00Z",
}


def test_the_list_offers_new_first_and_says_each_conversation() -> None:
    sheet = AiChans([_ONE], AiMarks())

    assert sheet.rows() == [
        (
            AI_NEW,
            "New conversation",
            "a conversation with a scope, nous and permissions of its own",
        ),
        (
            "3",
            "Ai-chan#3 · what is going on",
            "epic Ab_1 · claude/m:low · read-only · folded away",
        ),
    ]
    assert sheet.conversation("3") == _ONE
    assert sheet.conversation(AI_NEW) is None
    assert sheet.nothing() == ""


def test_an_empty_list_says_so() -> None:
    assert AiChans([], AiMarks()).nothing() == "No conversations yet"


def _said(number: int, updated: str) -> dict[str, Any]:
    return {**_ONE, "id": number, "updated": updated}


def test_the_pinned_are_listed_first_then_the_latest_said_in() -> None:
    marks = AiMarks()
    marks.pinned.add(1)
    old, mid, new = (
        _said(1, "2026-01-01"),
        _said(2, "2026-01-02"),
        _said(3, "2026-01-03"),
    )

    sheet = AiChans([old, mid, new], marks)

    assert [answer for answer, _, _ in sheet.rows()] == [AI_NEW, "1", "3", "2"]
    # The pinned one wears the square; nothing else does.
    assert [label[:1] for _, label, _ in sheet.rows()[1:]] == ["■", "A", "A"]


def test_a_conversation_is_unread_once_marked_or_said_in_since_it_was_read() -> None:
    marks = AiMarks()
    one = _said(3, "2026-01-01")
    sheet = AiChans([one], marks)

    assert not sheet.unread("3")
    marks.unread.add(3)
    assert sheet.unread("3")
    marks.reads(one)
    assert not sheet.unread("3")
    # Said in after it was read: unread again, with nothing marked.
    assert marks.is_unread(_said(3, "2026-01-02"))
    assert not sheet.unread(AI_NEW)


def test_the_menu_offers_what_the_drawers_does() -> None:
    marks = AiMarks()
    sheet = AiChans([_ONE], marks)
    sheet.under = lambda: "3"  # type: ignore[method-assign]

    named, acts = sheet.menu() or ("", [])
    assert named == "Ai-chan#3"
    assert [(one.key, one.label) for one in acts] == [
        ("rename", "Rename"),
        ("pin", "Pin"),
        ("read", "Mark as unread"),
        ("forget", "Delete"),
    ]

    marks.pinned.add(3)
    marks.unread.add(3)
    _, acts = sheet.menu() or ("", [])
    assert [one.label for one in acts][1:3] == ["Unpin", "Mark as read"]


def test_deleting_asks_in_the_pages_words_and_keeping_is_the_first_answer() -> None:
    box = AiForgets(3)

    assert box.asked == "Ai-chan#3 · Delete this conversation?"
    assert "cannot be carried on" in box.about
    assert [(answer, label) for answer, label, _ in box.rows()] == [
        ("no", "Cancel"),
        ("yes", "Delete"),
    ]
    assert box.PRIMARY == "yes"


def test_a_conversation_is_renamed_on_one_row_opening_on_its_title() -> None:
    form = AiRenames("what is going on")

    (asked,) = form.asked()
    assert (asked.held, asked.named, asked.needed) == ("title", "New name", False)
    assert form.done_about() == "renames the conversation"


@pytest.mark.parametrize(
    ("one", "said"),
    [
        ({"scope": "daemon"}, "daemon"),
        ({"scope": "workspace", "workspace": "/w"}, "workspace /w"),
        ({"scope": "epic", "workspace": "/w", "epic": "Ab_1"}, "epic Ab_1"),
    ],
)
def test_a_scope_is_said_by_what_it_reaches(one: dict[str, Any], said: str) -> None:
    assert ai_scope(one) == said


def test_a_new_conversation_defaults_to_the_epic_shown_and_the_setting() -> None:
    form = AiChanNew(["fast"], workspace="/w", epic="Ab_1", nous="claude/m:low")

    assert [(one.held, form.shown(one)) for one in form.asked()] == [
        ("scope", "epic"),
        ("nous", "claude/m:low"),
        ("preset", "read-only"),
    ]
    assert form.choices("scope") == ("daemon", "workspace", "epic")
    # The setting first where it names no nous written down, then every nous.
    assert form.choices("nous") == ["claude/m:low", "fast"]
    assert form.choices("preset") == ("read-only", "danger-full-access")


def test_with_no_epic_the_scope_is_the_workspace_and_offers_no_epic() -> None:
    form = AiChanNew([], workspace="/w", epic="", nous="")

    assert form.shown(form.asked()[0]) == "workspace"
    assert form.choices("scope") == ("daemon", "workspace")
    # Nobody named, so the nous is still to be answered, and with no nous it is written.
    nous = form.asked()[1]
    assert nous.needed
    assert form.editable(nous.held)


@pytest.mark.parametrize(
    ("scope", "named"),
    [
        ("daemon", {}),
        ("workspace", {"workspace": "/w"}),
        ("epic", {"workspace": "/w", "epic": "Ab_1"}),
    ],
)
def test_a_conversation_is_made_with_only_what_its_scope_takes(
    scope: str, named: dict[str, str]
) -> None:
    asked = AiAsked(
        scope=scope,
        workspace=named.get("workspace", ""),
        epic=named.get("epic", ""),
        nous="fast",
        preset="read-only",
    )

    assert asked.made("look") == {
        "scope": scope,
        **named,
        "nous": "fast",
        "preset": "read-only",
        "task": "look",
    }


def test_aichan_calls_reach_this_machine_s_daemon_and_writes_carry_an_idem() -> None:
    peer = mock.MagicMock()
    peer.call.return_value = {"conversations": []}
    with (
        mock.patch("hmz.daemon.start"),
        mock.patch("hmz.daemon.link.dialed", return_value=(peer, None)),
    ):
        assert ai_chan("list") == {"conversations": []}
        ai_chan("forget", id=3)
        peer.call.return_value = {"nous": [{"name": "fast"}, {"name": "slow"}]}
        assert nous_named() == ["fast", "slow"]

    listed, forgot, nous = peer.call.call_args_list
    assert nous.args[:2] == ("nous.list", {})
    assert listed.args[:2] == ("aichan.list", {})
    assert forgot.args[0] == "aichan.forget"
    assert forgot.args[1]["id"] == 3
    assert forgot.args[1]["idem"]
