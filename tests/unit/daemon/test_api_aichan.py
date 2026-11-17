"""`hmz.daemon.api.aichan`: what a conversation is refused as it is made, and when none is."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from hmz.daemon.api.aichan import METHODS
from hmz.rpc import RpcError


def _refused(method: str, **params: Any) -> tuple[int, str]:
    with pytest.raises(RpcError) as refused:
        METHODS[method](mock.Mock(params=params))
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


def test_nothing_is_served_without_a_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    from hmz.daemon import routing

    monkeypatch.setattr(routing, "serving", None)

    assert _refused("aichan.list") == (503, "No daemon is serving here.")
