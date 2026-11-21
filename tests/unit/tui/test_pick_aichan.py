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
    sheet = AiChans([_ONE])

    assert sheet.rows() == [
        (AI_NEW, "New", "a conversation of its own scope, nous and permission"),
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
    assert AiChans([]).nothing() == "no conversation yet"


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
