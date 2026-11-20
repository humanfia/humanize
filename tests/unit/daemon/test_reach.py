"""`hmz.daemon.reach`: what Ai-chan's session may call and see, and her conversations."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from hmz.daemon import reach as reaching
from hmz.daemon.reach import Conversations, Held, Links, Reach
from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from pathlib import Path


class _Session:
    def __init__(self, subs: dict[str, Any] | None = None) -> None:
        self.lock = threading.Lock()
        self.subs = subs or {}


class _Hosts:
    """Hosts by workspace and slot, each saying the epic it holds."""

    def __init__(self, held: dict[tuple[str, str], str]) -> None:
        self._held = held

    def get(self, workspace: str, slot: str) -> Any:
        if (workspace, slot) not in self._held:
            return None
        hosted = mock.Mock(workspace=workspace, slot=slot)
        hosted.status.return_value = {"epic": self._held[workspace, slot]}
        return hosted


@pytest.fixture
def kept(tmp_path: Path) -> Conversations:
    conversations = Conversations()
    conversations.at = tmp_path / "ai" / "m"
    return conversations


def _held(
    kept: Conversations,
    scope: str = "workspace",
    *,
    preset: str = "read-only",
    epic: str = "",
    subs: dict[str, Any] | None = None,
) -> Held:
    hosts = _Hosts({("/w", ""): "e1", ("/x", ""): "e2", ("/w", "ai:1"): "her"})
    reach = Reach(1, scope, "/w", epic, preset, network=False)
    return Held(reach, _Session(subs), hosts, kept)  # pyright: ignore[reportArgumentType]


def test_refusals_come_in_their_order(kept: Conversations) -> None:
    held = _held(kept)

    assert held.refusal("aichan.list", {}) == "Ai-chan cannot call aichan.list."
    assert held.refusal("pair.create", {}) == "Ai-chan cannot call pair.create."
    assert (
        held.refusal("hosts.stop", {"workspace": "/x", "slot": "ai:1"})
        == "Ai-chan cannot reach an Ai-chan conversation."
    )
    assert (
        held.refusal("hosts.stop", {"workspace": "/x"})
        == "hosts.stop is out of Ai-chan's scope: the host of /x."
    )
    assert (
        held.refusal("flows.list", {"workspace": "/x"})
        == "flows.list is out of Ai-chan's scope: the workspace /x."
    )
    assert (
        held.refusal("nous.set", {"name": "n"})
        == "nous.set is out of Ai-chan's scope: the daemon."
    )
    assert (
        held.refusal("hosts.stop", {"workspace": "/w"})
        == "Ai-chan is read-only, and hosts.stop changes things."
    )
    assert held.refusal("hosts.status", {"workspace": "/w"}) is None
    assert held.refusal("hosts.list", {}) is None


def test_a_call_naming_no_workspace_is_held_as_the_daemons(
    kept: Conversations,
) -> None:
    held = _held(kept, preset="danger-full-access")

    assert held.refusal("runs.usage", {}) == (
        "runs.usage is out of Ai-chan's scope: the daemon."
    )
    assert held.refusal("runs.usage", {"workspace": "/w"}) is None
    assert held.refusal("epic.attach", {"scratch": True}) == (
        "epic.attach is out of Ai-chan's scope: the daemon."
    )


@pytest.mark.parametrize("scope", ["daemon", "workspace", "epic"])
@pytest.mark.parametrize("chosen", ["runs", "recall", "kept", "cwd"])
def test_an_aside_of_an_agent_the_call_chooses_is_never_hers(
    kept: Conversations, scope: str, chosen: str
) -> None:
    hosted = mock.Mock(workspace="/w", slot="")
    hosted.status.return_value = {"epic": "e1"}
    held = _held(
        kept,
        scope,
        preset="danger-full-access",
        epic="e1",
        subs={"u1": mock.Mock(hosted=hosted)},
    )

    assert held.refusal("epic.aside", {"sub": "u1", chosen: "/x"}) == (
        "Ai-chan cannot call epic.aside."
    )
    # A session of the last epic, and a turn of a side conversation open, stay hers to ask.
    assert held.refusal("epic.aside", {"sub": "u1", "key": "a/1", "fork": True}) is None
    assert (
        held.refusal("epic.aside", {"sub": "u1", "side": "s1", "prompt": "?"}) is None
    )


def test_a_new_chat_is_a_write(kept: Conversations) -> None:
    held = _held(kept)

    assert held.refusal("epic.attach", {"workspace": "/w"}) is None
    assert held.refusal("epic.attach", {"workspace": "/w", "slot": "chat:"}) == (
        "Ai-chan is read-only, and epic.attach changes things."
    )


def test_an_epic_scope_reaches_its_epic_and_no_workspace(
    kept: Conversations,
) -> None:
    hosted = mock.Mock(workspace="/w", slot="")
    held = _held(
        kept,
        "epic",
        epic="e1",
        preset="danger-full-access",
        subs={
            "s1": mock.Mock(hosted=hosted),
            "s2": mock.Mock(hosted=mock.Mock(workspace="/x", slot="")),
        },
    )

    assert held.refusal("hosts.status", {"workspace": "/w"}) is None
    assert held.refusal("hosts.status", {"workspace": "/x"}) == (
        "hosts.status is out of Ai-chan's scope: the host of /x."
    )
    assert held.refusal("runs.get", {"name": "e1"}) is None
    assert held.refusal("runs.get", {"name": "e2"}) == (
        "runs.get is out of Ai-chan's scope: the epic e2."
    )
    assert held.refusal("flows.list", {"workspace": "/w"}) == (
        "flows.list is out of Ai-chan's scope: the workspace /w."
    )
    assert held.refusal("epic.start", {"sub": "s1"}) == (
        "epic.start is out of Ai-chan's scope: the workspace /w."
    )
    assert held.refusal("epic.say", {"sub": "s1"}) is None
    assert held.refusal("epic.say", {"sub": "s2"}) == (
        "epic.say is out of Ai-chan's scope: the host of /x."
    )


def test_no_reach_reaches_an_ai_chan_conversations_epic(
    kept: Conversations,
) -> None:
    made = kept.made({"slot": "ai:1", "workspace": "/w"})
    kept.changed(made["id"], record="her")
    held = _held(kept, "daemon")

    assert held.refusal("runs.get", {"name": "her"}) == (
        "runs.get is out of Ai-chan's scope: the epic her."
    )
    assert held.refusal("runs.get", {"name": "e2"}) is None


def test_answers_are_cut_to_the_reach(kept: Conversations) -> None:
    held = _held(kept)
    hosts = {
        "held": [
            {"workspace": "/w", "slot": ""},
            {"workspace": "/x", "slot": ""},
            {"workspace": "/w", "slot": "ai:1"},
        ]
    }
    notices = {
        "notices": [
            {"workspace": "/w", "slot": "", "epic": "e1"},
            {"workspace": "/x", "slot": "", "epic": "e2"},
        ],
        "last": 2,
    }

    assert held.answered("hosts.list", hosts) == {
        "held": [{"workspace": "/w", "slot": ""}]
    }
    assert held.answered(
        "workspaces.list", {"here": "", "workspaces": [{"path": "/w"}, {"path": "/x"}]}
    ) == {"here": "", "workspaces": [{"path": "/w"}]}
    assert held.answered("notices.list", notices) == {
        "notices": [{"workspace": "/w", "slot": "", "epic": "e1"}],
        "last": 2,
    }
    assert held.answered(
        "hosts.running", {"running": [{"workspace": "/x", "slot": "", "epic": "e2"}]}
    ) == {"running": []}


def test_a_chat_a_host_holds_is_reached_as_the_epic_of_one_is(
    kept: Conversations,
) -> None:
    class Chatting(_Hosts):
        """Hosts of chats, each naming its chat and no epic."""

        def get(self, workspace: str, slot: str) -> Any:
            hosted = super().get(workspace, slot)
            if hosted is not None:
                hosted.status.return_value = {
                    "epic": "",
                    "chat": self._held[workspace, slot],
                }
            return hosted

    hosts = Chatting({("/w", "chat:1"): "c1", ("/w", "chat:2"): "c2"})
    reach = Reach(1, "epic", "/w", "c1", "danger-full-access", network=False)
    held = Held(reach, _Session(), hosts, kept)  # pyright: ignore[reportArgumentType]

    # Scoped to a chat by its name, she reaches the host that holds it, and no other's.
    assert held.host("/w", "chat:1")
    assert not held.host("/w", "chat:2")
    assert held.refusal("chat.say", {"workspace": "/w", "slot": "chat:1"}) is None
    assert held.refusal("chat.stop", {"workspace": "/w", "slot": "chat:2"}) == (
        "chat.stop is out of Ai-chan's scope: the host chat:2 of /w."
    )
    assert held.notice({"workspace": "/w", "slot": "chat:1", "epic": "", "chat": "c1"})
    assert not held.notice(
        {"workspace": "/w", "slot": "chat:2", "epic": "", "chat": "c2"}
    )
    running = [
        {"workspace": "/w", "slot": "chat:1", "epic": "", "chat": "c1"},
        {"workspace": "/w", "slot": "chat:2", "epic": "", "chat": "c2"},
    ]
    assert held.answered("hosts.running", {"running": running}) == {
        "running": running[:1]
    }


def test_a_chat_was_had_where_its_record_says_as_an_epic_was_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import hmz.runtime.epic

    def none() -> list[Path]:
        return []

    def chats() -> list[Path]:
        return [tmp_path / "c1"]

    def read(at: Path) -> Any:
        return mock.Mock(workspace=str(tmp_path)) if at.name == "c1" else None

    monkeypatch.setattr(hmz.runtime.epic, "every", none)
    monkeypatch.setattr(hmz.runtime.epic, "chats", chats)
    monkeypatch.setattr(hmz.runtime.epic, "read", read)

    assert reaching.ran_in("c1") == str(tmp_path.resolve())
    assert reaching.ran_in("none") == ""


def test_the_reach_of_a_call_is_what_lists_are_cut_by(kept: Conversations) -> None:
    held = _held(kept)

    assert reaching.epics() is None
    token = reaching.holding.set(held)
    try:
        kept_epic = reaching.epics()
        assert kept_epic is not None
        assert kept_epic("e1", "/w")
        assert not kept_epic("e2", "/x")
        told = reaching.notices()
        assert told is not None
        assert not told({"workspace": "/x", "slot": "", "epic": "e2"})
    finally:
        reaching.holding.reset(token)


def test_conversations_are_numbered_kept_and_forgotten(kept: Conversations) -> None:
    first = kept.made({"slot": "ai:1"})
    second = kept.made({"slot": "ai:2"})

    assert (first["id"], second["id"]) == (1, 2)
    assert first["record"] == ""
    assert first["created"].endswith("Z")
    # Made is the last that was said in it, until something is.
    assert first["updated"] == first["created"]
    assert kept.scratch(1).is_dir()
    assert (kept.at / "conversations.yaml").stat().st_mode & 0o777 == 0o600
    assert kept.of("ai:2") == second
    kept.changed(2, record="e")
    assert kept.epics() == {"e"}
    assert kept.forgot(1) == first
    assert not kept.scratch(1).exists()
    assert kept.forgot(1) is None
    assert [one["id"] for one in kept.all()] == [2]
    assert kept.made({"slot": "ai:3"})["id"] == 3


def test_the_epic_of_a_conversation_forgotten_stays_an_ai_chan_epic(
    kept: Conversations,
) -> None:
    kept.made({"slot": "ai:1"})
    kept.made({"slot": "ai:2"})
    kept.made({"slot": "ai:3"})
    kept.changed(1, record="e1")
    kept.changed(3, record="e3")

    # One written down, one its host alone has named yet, and one of no conversation.
    assert kept.forgot(1) is not None
    assert kept.forgot(2, "e2") is not None
    assert kept.forgot(2, "e4") is None

    assert kept.epics() == {"e1", "e2", "e3"}
    assert (kept.at / "forgotten.yaml").stat().st_mode & 0o777 == 0o600
    assert kept.forgot(3) is not None
    again = Conversations()
    again.at = kept.at
    assert again.epics() == {"e1", "e2", "e3"}


def test_conversations_that_cannot_be_read_are_none(kept: Conversations) -> None:
    kept.at.mkdir(parents=True)
    (kept.at / "conversations.yaml").write_text("{not: a list}")

    assert kept.all() == []


def test_her_host_has_her_chat_anew_then_carried_on(
    kept: Conversations, monkeypatch: pytest.MonkeyPatch
) -> None:
    links = Links(mock.Mock(), mock.Mock())
    links.kept = kept
    made = kept.made(
        {
            "slot": "ai:1",
            "title": "hi",
            "scope": "daemon",
            "workspace": "/w",
            "epic": "",
            "nous": "claude/opus",
            "preset": "read-only",
            "network": False,
        }
    )
    links.tasks["ai:1"] = "hi"
    hosted = mock.Mock(slot="ai:1", peer=None)
    hosted.chat.return_value = {"ok": True}
    reach = {
        "id": made["id"],
        "scope": "daemon",
        "workspace": "/w",
        "epic": "",
        "preset": "read-only",
        "network": False,
    }

    links.after(hosted)

    hosted.chat.assert_called_once_with(
        {
            "do": "start",
            "by": "hmz",
            "agent": "claude/opus",
            "task": "hi",
            "resume": None,
            "ai": reach,
            "scratch": str(kept.scratch(made["id"])),
        }
    )
    hosted.started.assert_not_called()
    kept.changed(made["id"], record="20260101-chat")
    monkeypatch.setattr(reaching, "epic_at", "/e/{}".format)

    links.after(hosted)

    said = hosted.chat.call_args.args[0]
    assert (said["task"], said["resume"]) == ("", "/e/20260101-chat")


def _followed(kept: Conversations, statuses: list[dict[str, Any]]) -> dict[str, Any]:
    """A conversation as its entry stands once its host said each of `statuses` and went."""
    links = Links(mock.Mock(), mock.Mock())
    links.kept = kept
    if kept.of("ai:1") is None:
        kept.made(
            {
                "slot": "ai:1",
                "scope": "daemon",
                "workspace": "/w",
                "epic": "",
                "nous": "claude/opus",
                "preset": "read-only",
                "network": False,
                "latest": "hi",
            }
        )
        links.tasks["ai:1"] = "hi"
    hosted = mock.Mock(slot="ai:1")
    hosted.peer.closed = False
    hosted.chat.return_value = {"ok": True}
    left = list(statuses)

    def status() -> dict[str, Any]:
        said = left.pop(0)
        # Its host goes once it has said the last of them.
        hosted.peer.closed = not left
        return said

    hosted.status.side_effect = status

    links.after(hosted)

    for one in threading.enumerate():
        if one.name == "hmz-ai-epic":
            one.join(10)
    assert not left
    conversation = kept.of("ai:1")
    assert conversation is not None
    return conversation


def test_her_conversation_is_named_by_the_chat_its_host_writes(
    kept: Conversations,
) -> None:
    # Her host names no epic: she is kept as a chat is, and says which by `chat`.
    conversation = _followed(
        kept, [{"epic": "", "chat": ""}, {"epic": "", "chat": "20260101-hers"}]
    )

    assert conversation["record"] == "20260101-hers"
    assert kept.epics() == {"20260101-hers"}


def test_what_she_last_answered_is_written_down_as_she_answers_it(
    kept: Conversations, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.sleep", mock.Mock())
    monkeypatch.setattr(reaching, "epic_at", "/e/{}".format)
    stamps = iter(["t0", "t1", "t2", "t3"])
    monkeypatch.setattr(reaching.where, "now", lambda: next(stamps))
    listening = {"mode": "listen", "text": "All  three epics\nare done. " + "x" * 200}

    conversation = _followed(
        kept,
        [
            # Her turn open: nothing she said yet, and what it was made with stays.
            {"chat": "c", "pending": []},
            # What she asks mid-turn is no answer of hers.
            {"chat": "c", "pending": [{"mode": "ask", "text": "Which one?"}]},
            {"chat": "c", "pending": [listening]},
            # Said again, it is written once.
            {"chat": "c", "pending": [listening]},
        ],
    )

    assert conversation["record"] == "c"
    assert (conversation["created"], conversation["updated"]) == ("t0", "t1")
    assert conversation["latest"] == ("All three epics are done. " + "x" * 200)[:120]

    # Carried on, her host waits on what she answered last: nothing new was said.
    again = _followed(kept, [{"chat": "c", "pending": [listening]}])
    assert again["updated"] == "t1"
    # Nor is why it could not be carried on, which its host waits on as it comes up: no
    # turn of hers ended on it.
    notice = {
        "mode": "listen",
        "question": "q0",
        "text": "This could not be carried on.",
    }
    again = _followed(kept, [{"chat": "c", "turn": "done", "pending": [notice]}])
    assert (again["latest"], again["updated"]) == (conversation["latest"], "t1")
    # And her next answer, a turn of hers since open, is the latest from then on.
    after = _followed(
        kept,
        [
            {"chat": "c", "turn": "done", "pending": [notice]},
            {"chat": "c", "turn": "running", "pending": []},
            {
                "chat": "c",
                "turn": "done",
                "pending": [{"mode": "listen", "question": "q1", "text": "Done."}],
            },
        ],
    )
    assert (after["latest"], after["updated"]) == ("Done.", "t2")


def test_what_a_reach_names_is_a_chat_or_an_epic_by_its_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import hmz.runtime.epic

    chat, epic = tmp_path / "chats" / "w" / "c1", tmp_path / "epics" / "w" / "e1"
    old = tmp_path / "epics" / "w" / "old"

    def chats() -> list[Path]:
        return [chat]

    def every() -> list[Path]:
        return [epic, old]

    def chatted(at: Path) -> bool:
        return at == old

    monkeypatch.setattr(hmz.runtime.epic, "chats", chats)
    monkeypatch.setattr(hmz.runtime.epic, "every", every)
    monkeypatch.setattr(hmz.runtime.epic, "chatted", chatted)

    assert reaching.epic_at("c1") == chat
    # An epic is found as a chat is: where it was run is what a reach asks of either.
    assert reaching.epic_at("e1") == epic
    assert reaching.epic_at("none") is None
    # A chat an earlier hmz kept as an epic is neither until the daemon has moved it.
    assert reaching.epic_at("old") is None
    assert reaching.ran_in("old") == ""


def test_a_conversation_kept_as_an_epic_is_not_carried_on_or_begun_anew(
    kept: Conversations, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import hmz.runtime.epic

    old = tmp_path / "epics" / "w" / "old"

    def every() -> list[Path]:
        return [old]

    def chatted(at: Path) -> bool:
        return at == old

    monkeypatch.setattr(hmz.runtime.epic, "chats", list)
    monkeypatch.setattr(hmz.runtime.epic, "every", every)
    monkeypatch.setattr(hmz.runtime.epic, "chatted", chatted)
    links = Links(mock.Mock(), mock.Mock())
    links.kept = kept
    made = kept.made({"slot": "ai:1", "nous": "claude/opus"})
    kept.changed(made["id"], record="old")
    hosted = mock.Mock(slot="ai:1")

    with pytest.raises(RpcError, match="There is no chat old") as refused:
        links.after(hosted)

    assert refused.value.code == Code.NOT_FOUND
    # Nothing was started: a chat begun anew would be written down in its place.
    hosted.chat.assert_not_called()
    conversation = kept.of("ai:1")
    assert conversation is not None
    assert conversation["record"] == "old"
