"""`hmz.daemon.api.aichan`: what a conversation is refused as it is made."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from hmz.daemon.api.aichan import served
from hmz.rpc import RpcError


def _refused(method: str, **params: Any) -> tuple[int, str]:
    with pytest.raises(RpcError) as refused:
        served(mock.Mock())[method](mock.Mock(params=params))
    return refused.value.code, refused.value.message


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"scope": "room"}, "An Ai-chan's scope is daemon, workspace or epic."),
        ({"scope": "workspace"}, "A workspace scope names its workspace."),
        ({"scope": "epic"}, "A epic scope names its workspace."),
        (
            {"scope": "daemon", "epic": "e"},
            "A daemon scope names no workspace and no epic.",
        ),
        (
            {"scope": "workspace", "workspace": "/w", "epic": "e"},
            "A workspace scope names no epic.",
        ),
        ({"scope": "epic", "workspace": "/w"}, "An epic scope names its epic."),
        (
            {"scope": "daemon", "preset": "workspace-write"},
            "An Ai-chan's preset is read-only or danger-full-access.",
        ),
    ],
)
def test_a_conversation_said_wrongly_is_refused_400(
    params: dict[str, Any], message: str
) -> None:
    assert _refused("aichan.create", task="hi", **params) == (400, message)


@pytest.mark.parametrize(
    ("status", "state"),
    [
        (None, "folded"),
        ({"state": "running", "turn": "running"}, "running"),
        ({"state": "running", "turn": "done"}, "waiting"),
        ({"state": "running", "pending": []}, "running"),
        ({"state": "running", "pending": [{"mode": "listen"}]}, "waiting"),
        ({"state": "idle"}, "waiting"),
    ],
)
def test_a_conversation_says_whether_her_turn_is_open(
    status: dict[str, Any] | None, state: str
) -> None:
    router = mock.Mock()
    router.links.kept.all.return_value = [
        {"id": 1, "workspace": "/w", "slot": "ai:1", "created": "now"}
    ]
    hosted = None
    if status is not None:
        hosted = mock.Mock()
        hosted.status.return_value = status
    router.hosts.get.return_value = hosted

    (listed,) = served(router)["aichan.list"](mock.Mock(params={}))["conversations"]

    assert listed["state"] == state
