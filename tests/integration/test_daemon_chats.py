"""Chats held apart: each on a host of its own beside the workspace's, folding away when idle.

A chat is no flow: it is started and said to by `chat.*`, through the daemon, on a host of its
own beside the workspace's, so two conversations and a flow go at once in one workspace. A chat
nobody reads between turns folds away -- its host goes -- and `chat.start` with `resume` carries
it on in the same epic. The chat itself is stood in for (`doubles_daemon.CHAT`): what is tested
here is the host and the daemon around it, over real processes and real RPC.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.daemon.link import dialed, reached
from hmz.rpc import RpcError
from hmz.runtime import Hmz
from hmz.runtime.epic import Drove, Epic, every, going
from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_daemon import (
    WAITS,
    Heard,
    chats,
    hosting,
    until,
    written,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(120),
]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = install(tmp_path, monkeypatch)
    # A chat nobody reads folds in a moment.
    chats(1.0, monkeypatch)
    with hosting():
        yield at


def _asked(heard: Heard, text: str) -> Callable[[], bool]:
    """Whether a chat has answered `text` and waits on what to say next."""
    return lambda: any(
        one.get("mode") == "listen" and one.get("text") == text
        for one in heard.of("asked")
    )


def _chat(
    workspace: Path, said: str, agent: str = AGENT, **given: object
) -> tuple[daemon.Link, Heard, str, str]:
    """A chat started on a new slot of its own, with a frontend following it."""
    link = daemon.attach("sdk", workspace=workspace, slot=where.chat())
    heard = Heard()
    link.heard(heard)
    started = link.chat(agent, said, **given)  # pyright: ignore[reportArgumentType]
    assert until(_asked(heard, f"you said: {said}"))
    return link, heard, str(started["slot"]), str(started["epic"])


def test_two_chats_and_a_flow_go_at_once_in_one_workspace(workspace: Path) -> None:
    written(workspace, "waits", WAITS)
    with daemon.attach("sdk", workspace=workspace) as flow:
        flow.start("./waits", "forever", budget={"cost": 1})
        first, _, slot_first, epic_first = _chat(workspace, "first")
        second, _, slot_second, epic_second = _chat(workspace, "second")
        try:
            hosts = {one.slot: one.status() for one in daemon.daemons()}
            assert set(hosts) == {"", slot_first, slot_second}
            assert {one["state"] for one in hosts.values()} == {"running"}
            assert {slot: one["epic_kind"] for slot, one in hosts.items()} == {
                "": "flow",
                slot_first: "chat",
                slot_second: "chat",
            }
            assert (hosts[slot_first]["turn"], hosts[slot_second]["turn"]) == (
                "done",
                "done",
            )
            assert hosts[slot_first]["flow"] == ""
            # Each its own epic, and the flow's another.
            assert {hosts[slot_first]["epic"], hosts[slot_second]["epic"]} == {
                epic_first,
                epic_second,
            }
            assert len({one["epic"] for one in hosts.values()}) == 3
            # A second flow is still one too many on the workspace's own host.
            with pytest.raises(daemon.Refused, match="already running"):
                flow.start("./waits", "again", budget={"cost": 1})
        finally:
            first.close()
            second.close()
            flow.stop()


def test_a_chat_is_said_to_set_and_folds_away_to_be_carried_on_in_its_epic(
    workspace: Path,
) -> None:
    link, heard, slot, name = _chat(workspace, "remember teal")
    assert name

    link.chat_say("and blue")
    assert until(_asked(heard, "you said: and blue"))
    # A native line is said to the chat as it is, for its harness to serve.
    link.chat_say("/compact")
    assert until(_asked(heard, "you said: /compact"))
    # What the frontend serves is not said to the chat.
    with pytest.raises(daemon.Refused, match=r"/clear is served by the frontend"):
        link.chat_say("/clear")
    with pytest.raises(daemon.Refused, match=r"say it to the chat with chat\.say"):
        link.say("hello")
    with pytest.raises(daemon.Refused, match=r"a chat is started with chat\.start"):
        link.start("chat", "hello", agents={"assistant": AGENT})

    commands = link.chat_commands()
    entries = commands["entries"]
    assert [(one["sigil"], one["name"], one["source"]) for one in entries[:2]] == [
        ("/", "compact", "native"),
        ("!", "", "native"),
    ]
    assert {"clear", "resume", "prefer"} <= {
        one["name"] for one in entries if one["source"] == "hmz"
    }
    assert all(one["sigil"] == "$" for one in entries if one["source"] == "flow")
    assert (commands["prefer"], commands["prefer_from"]) == ("native", "settings")
    link.chat_set("flow")
    commands = link.chat_commands()
    assert (commands["prefer"], commands["prefer_from"]) == ("flow", "chat")

    status = daemon.running(workspace, slot=slot)
    assert status is not None
    said = status.status()
    assert (said["epic_kind"], said["turn"], said["epic"]) == ("chat", "done", name)
    link.close()

    # Between turns with nobody reading: it folds, and its host goes.
    assert until(lambda: daemon.running(workspace, slot=slot) is None)
    with pytest.raises(OSError, match=r"This chat has folded away\."):
        reached(where.at(), where.workspace(workspace), slot=slot)
    peer, _ = dialed(where.at())
    try:
        with pytest.raises(RpcError) as folded:
            peer.call(
                "chat.say",
                {"workspace": str(workspace), "slot": slot, "text": "again"},
                timeout=10,
            )
    finally:
        peer.close()
    assert (folded.value.code, folded.value.message) == (
        409,
        "this chat has folded away; carry it on from its epic",
    )
    (epic,) = [one for one in every() if one.name == name]

    again, heard_again, _, carried = _chat(
        workspace, "what was it?", agent="", resume=str(epic)
    )
    try:
        # The same epic, opened again rather than a new one beside it.
        assert carried == name
        assert [one.name for one in every()] == [name]
        assert heard_again.of("started")[-1]["resume"] == str(epic)
    finally:
        again.close()


def test_a_chat_is_started_with_a_permission_and_set_to_another(
    workspace: Path,
) -> None:
    link, _, _, _ = _chat(workspace, "look around", permission="read-only")
    plain, _, _, _ = _chat(workspace, "hello")
    try:
        assert link.chat_commands()["permission"] == "read-only"
        # One started with none named is held as a chat always was.
        assert plain.chat_commands()["permission"] == "workspace-write"

        link.chat_set(permission="danger-full-access")
        assert link.chat_commands()["permission"] == "danger-full-access"
        link.chat_set("flow", permission="workspace-write")
        commands = link.chat_commands()
        assert (commands["prefer"], commands["permission"]) == (
            "flow",
            "workspace-write",
        )
        unpermitted = r"permission is read-only, workspace-write or danger-full-access"
        with pytest.raises(daemon.Refused, match=unpermitted):
            link.chat_set(permission="ask")
        with pytest.raises(daemon.Refused, match=unpermitted):
            link.chat(AGENT, "again", permission="plan")
    finally:
        link.close()
        plain.close()


def test_a_chat_started_remembering_its_agent_is_offered_it_next_time(
    workspace: Path,
) -> None:
    link, _, _, _ = _chat(workspace, "hello", remember=True)
    try:
        remembered = Hmz(workspace).settings.chat_agent
        assert remembered is not None
        assert remembered.spec.startswith("claude/")
    finally:
        link.close()


def test_a_chat_that_cannot_be_started_is_refused_before_anything_starts(
    workspace: Path,
) -> None:
    with daemon.attach("sdk", workspace=workspace, slot=where.chat()) as link:
        with pytest.raises(daemon.Refused, match="a chat starts with something said"):
            link.chat(AGENT, "")
        with pytest.raises(daemon.Refused, match="an agent for the chat is named"):
            link.chat("", "hello")
        with pytest.raises(daemon.Refused, match="is not a chat of"):
            link.chat(AGENT, "hello", resume="20200101-nothing")
        with pytest.raises(daemon.Refused, match="no chat is going here"):
            link.chat_say("hello")

    assert every() == []
    assert Hmz(workspace).settings.chat_agent is None


def test_a_chat_carried_on_while_it_is_going_elsewhere_is_refused_saying_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The chat itself, not its stand-in: it is the chat that looks at what it carries on.
    at = install(tmp_path, monkeypatch)
    backend, _, model = AGENT.partition("/")
    drove = Drove("assistant", backend, model.partition(":")[0], "")
    with hosting(), Epic("", "first", at, kind="chat", agents=[drove]) as epic:
        assert going(epic.path)
        with (
            daemon.attach("sdk", workspace=at, slot=where.chat()) as link,
            pytest.raises(
                daemon.Refused, match=f"{epic.path.name} is going on already"
            ),
        ):
            link.chat(AGENT, "second voice", resume=str(epic.path))
