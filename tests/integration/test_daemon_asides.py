"""Side questions about one session of an epic or a chat, `btw.*`, through a private daemon.

The daemon asks a session side copy on the host that holds the session -- a chat's own slot for
a chat, named by `chat` -- attaching to that host with what it ran so far replayed, which is
not an epic starting. A chat no host holds any longer is asked on the workspace's own host,
each session carried on from where the chat kept it, and an epic starting there does not end
that aside.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.runtime.epic import chats, every, read
from hmz.sdk import Client, Refused
from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_daemon import (
    WAITS,
    Heard,
    folds,
    hosting,
    until,
    written,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [pytest.mark.timeout(180)]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = install(tmp_path, monkeypatch)
    # A chat nobody reads folds in a moment, and is then held by no host.
    folds(1.0, monkeypatch)
    with hosting():
        yield at


def _chatted(workspace: Path) -> tuple[daemon.Link, str, str, str]:
    """A chat that has answered once: its link, slot, name and the session it opened."""
    slot = where.chat()
    link = daemon.attach("sdk", workspace=workspace, slot=slot)
    heard = Heard()
    link.heard(heard)
    started = link.chat(AGENT, "remember papaya")
    assert until(lambda: any(one.get("mode") == "listen" for one in heard.of("asked")))
    chat = str(started["chat"])
    (opened, *_) = heard.of("opened")
    return link, slot, chat, str(opened["key"])


def _asked(client: Client, workspace: Path, **said: Any) -> dict[str, Any]:
    return client.call("btw.ask", {"workspace": str(workspace), **said}, seconds=60)


def _kinds(slot: str) -> list[str]:
    """The kinds of frontend attached to one slot's host, or [] where none is held."""
    for one in daemon.daemons():
        if one.slot == slot:
            return [str(each["kind"]) for each in one.status()["clients"]]
    return []


def _state(slot: str) -> str:
    """How one slot's host stands, or "" where none is held."""
    for one in daemon.daemons():
        if one.slot == slot:
            return str(one.status()["state"])
    return ""


def test_a_live_chat_is_asked_on_its_own_slot_and_the_replay_closes_nothing(
    workspace: Path,
) -> None:
    link, slot, chat, key = _chatted(workspace)
    try:
        with Client.local() as client:
            first = _asked(
                client, workspace, aside="a1", to=key, chat=chat, question="the word?"
            )
            # Asked again after the replay of the chat's `started`: still open, still its.
            second = _asked(
                client, workspace, aside="a1", to=key, chat=chat, question="again?"
            )
            listed = client.call(
                "btw.list", {"workspace": str(workspace), "chat": chat}
            )
            # About the chat, and about no epic: the workspace's own has none open.
            assert client.call("btw.list", {"workspace": str(workspace)}) == {
                "asides": []
            }

        assert (first["aside"], first["to"], first["question"]) == (
            "a1",
            key,
            "the word?",
        )
        assert "the word?" in first["answer"]
        assert "again?" in second["answer"]
        (held,) = listed["asides"]
        assert [one["question"] for one in held["said"]] == ["the word?", "again?"]
        # On the chat's own host, and no host of the workspace's own was taken on for it.
        assert "btw" in _kinds(slot)
        assert _kinds("") == []
    finally:
        link.close()


def test_a_session_is_asked_of_as_agent_and_number(workspace: Path) -> None:
    with Client.local() as client, pytest.raises(Refused) as refused:
        _asked(client, workspace, aside="a1", to="", question="anyone?")

    assert refused.value.code == 400
    assert "<agent>/<n>" in str(refused.value)


def test_a_resting_chat_is_asked_on_the_workspace_host_and_outlives_a_new_epic(
    workspace: Path,
) -> None:
    link, slot, chat, key = _chatted(workspace)
    link.close()
    # Folded: no host holds the chat any longer, and it is no epic of the workspace's.
    assert until(lambda: daemon.running(workspace, slot=slot) is None)
    assert ([one.name for one in chats()], every()) == ([chat], [])

    written(workspace, "waits", WAITS)
    with Client.local() as client:
        first = _asked(
            client, workspace, aside="a2", to=key, chat=chat, question="the word?"
        )
        assert "the word?" in first["answer"]
        assert "btw" in _kinds("")

        # An epic starting on the host the aside is asked on does not end it.
        with daemon.attach("sdk", workspace=workspace) as flow:
            flow.start("./waits", "forever", budget={"cost": 1})
            try:
                assert until(lambda: _state("") == "running")
                second = _asked(
                    client, workspace, aside="a2", to=key, chat=chat, question="still?"
                )
            finally:
                flow.stop()

        assert "still?" in second["answer"]
        listed = client.call("btw.list", {"workspace": str(workspace), "chat": chat})
        (held,) = listed["asides"]
        assert [one["question"] for one in held["said"]] == ["the word?", "still?"]


def test_a_chat_carried_on_is_asked_of_every_session_it_opened(workspace: Path) -> None:
    link, slot, chat, _ = _chatted(workspace)
    link.close()
    assert until(lambda: daemon.running(workspace, slot=slot) is None)
    (at,) = [one for one in chats() if one.name == chat]

    # Carried on as the agent it was, then folded again.
    again = where.chat()
    link = daemon.attach("sdk", workspace=workspace, slot=again)
    heard = Heard()
    link.heard(heard)
    assert link.chat("", "what was it?", resume=chat)["chat"] == chat
    assert until(lambda: any(one.get("mode") == "listen" for one in heard.of("asked")))
    link.close()
    assert until(lambda: daemon.running(workspace, slot=again) is None)

    ran = read(at)
    assert ran is not None
    (agent,) = ran.agents
    assert len(ran.sessions) == 2
    assert {one.agent for one in ran.sessions} == {agent.name}
    with Client.local() as client:
        for number in (1, 2):
            answered = _asked(
                client,
                workspace,
                aside=f"a{number}",
                to=f"{agent.name}/{number}",
                chat=chat,
                question="the word?",
            )
            assert "the word?" in answered["answer"]
