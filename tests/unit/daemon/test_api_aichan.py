"""`hmz.daemon.api.aichan`: what a conversation is refused as it is made, and how it is listed."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from hmz.daemon.api import aichan
from hmz.daemon.api.aichan import served
from hmz.rpc import Code, RpcError


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


def _listed(conversation: dict[str, Any]) -> tuple[dict[str, Any], mock.Mock]:
    router = mock.Mock()
    router.links.kept.all.return_value = [
        {"id": 1, "workspace": "/w", "slot": "ai:1", "created": "then"} | conversation
    ]
    router.hosts.get.return_value = None
    (listed,) = served(router)["aichan.list"](mock.Mock(params={}))["conversations"]
    return listed, router.links.kept.changed


def test_a_conversation_says_what_was_last_said_in_it_and_when() -> None:
    listed, changed = _listed({"latest": "All done.", "updated": "now"})

    assert (listed["latest"], listed["updated"]) == ("All done.", "now")
    changed.assert_not_called()


@pytest.mark.parametrize(
    ("record", "traced", "latest"),
    [
        # Nothing it was written in: nothing to read.
        ("", [], ""),
        # What her chat last said, whichever session said it, cut to one short line.
        (
            "c1",
            [
                {
                    "actions": [
                        {"category": "turn", "start": 1.0, "args": {"prompt": "hi"}},
                        {
                            "category": "message",
                            "start": 5.0,
                            "args": {"text": "b\n b"},
                        },
                    ]
                },
                {
                    "actions": [
                        {"category": "message", "start": 2.0, "args": {"text": "a"}}
                    ]
                },
            ],
            "b b",
        ),
        # She never answered: what it was made with.
        ("c1", [], "the task"),
        # A record that is not there says nothing, and is not read again.
        ("gone", [], ""),
    ],
)
def test_a_conversation_of_an_earlier_hmz_reads_its_latest_once_out_of_its_record(
    monkeypatch: pytest.MonkeyPatch,
    record: str,
    traced: list[dict[str, Any]],
    latest: str,
) -> None:
    chats = mock.Mock()

    def named(name: str) -> Any:
        if name != "c1":
            raise RpcError(Code.NOT_FOUND, f"There is no chat {name}.")
        return mock.Mock(task="the task")

    chats.named.side_effect = named
    chats.traced.return_value = traced
    monkeypatch.setattr("hmz.daemon.api.chats.CHATS", chats)

    listed, changed = _listed({"record": record})

    assert (listed["latest"], listed["updated"]) == (latest, "then")
    changed.assert_called_once_with(1, latest=latest, updated="then")


def _made(
    monkeypatch: pytest.MonkeyPatch, *, was: str, refused: bool = False
) -> tuple[Any, mock.Mock]:
    """Makes a conversation with the nous `fast`, and answers the settings and its entry."""
    settings = mock.Mock(ai_chan=was)
    monkeypatch.setattr(
        "hmz.runtime.Hmz", mock.Mock(return_value=mock.Mock(settings=settings))
    )
    monkeypatch.setattr("hmz.runtime.flowing.parse_agents", mock.Mock())
    monkeypatch.setattr(aichan.where, "workspace", mock.Mock(return_value="/home/ai/m"))
    monkeypatch.setattr(aichan.where, "chat", mock.Mock(return_value="ai:1"))
    router = mock.Mock()
    router.links.tasks = {}
    router.links.kept.made.return_value = {"id": 1}
    if refused:
        router.hosts.opened.side_effect = RpcError(Code.CONFLICT, "no")
    params = {"scope": "daemon", "nous": "fast", "task": " look \n around "}
    create = served(router)["aichan.create"]
    if refused:
        with pytest.raises(RpcError):
            create(mock.Mock(params=params))
    else:
        assert create(mock.Mock(params=params)) == {
            "id": 1,
            "workspace": "/home/ai/m",
            "slot": "ai:1",
        }
    return settings, router.links.kept.made


def test_a_conversation_made_is_listed_by_its_task_and_remembers_its_nous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, made = _made(monkeypatch, was="")

    assert made.call_args.args[0]["latest"] == "look around"
    assert settings.ai_chan == "fast"


def test_a_conversation_refused_remembers_no_nous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, _ = _made(monkeypatch, was="slow", refused=True)

    assert settings.ai_chan == "slow"
