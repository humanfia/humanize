"""Chats held apart: each on a host of its own beside the workspace's, folding away when idle.

A chat is no flow and no epic: it is started and said to by `chat.*`, through the daemon, on a
host of its own beside the workspace's, so two conversations and a flow go at once in one
workspace. A chat nobody reads between turns folds away -- its host goes -- and `chat.start`
with `resume` carries it on in the same chat, by its name. It is written down in a record of
its own, which `chat.*` lists, reads, renames, forks, archives, backs up and deletes by that
name, and which `runs.*` knows nothing of.

Where what is tested is the host and the daemon around a chat, the chat itself is stood in
for (`doubles_daemon.CHAT`); where it is the chat's own record, its turns and where it works,
it is the chat itself, driving the stand-in `claude`. Either way over real processes and real
RPC.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from hmz import daemon, home
from hmz.daemon import where
from hmz.daemon.link import dialed, reached
from hmz.rpc import RpcError
from hmz.runtime import Hmz, backing
from hmz.runtime.chatting import STOPPED
from hmz.runtime.epic import (
    CHATTED,
    JOURNAL,
    SESSIONS,
    Drove,
    Epic,
    every,
    going,
    under,
)
from hmz.runtime.epic import chats as written_chats
from tests.integration.doubles_core import AGENT, MODEL, install, started
from tests.integration.doubles_daemon import (
    WAITS,
    Heard,
    chats,
    hosting,
    old_chat,
    until,
    written,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from hmz.rpc import Peer

pytestmark = [
    pytest.mark.timeout(180),
]

#: Every key of a chat row (`#/components/schemas/Chat`).
ROW = {
    "id",
    "title",
    "workspace",
    "workdir",
    "agent",
    "model",
    "began",
    "updated",
    "state",
    "slot",
    "asking",
    "permission",
    "archived",
    "spent",
}

#: A line the stand-in `claude` takes this long a turn over: long enough to be stopped in.
SLOW = 'run: [["sleep", "20"]]'


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = install(tmp_path, monkeypatch)
    # A chat nobody reads folds in a moment.
    chats(1.0, monkeypatch)
    with hosting():
        yield at


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A project whose chats are the chat itself, with the stand-in `claude` as assistant."""
    at = install(tmp_path, monkeypatch)
    with hosting():
        daemon.start()
        yield at


@pytest.fixture
def user(project: Path) -> Iterator[Peer]:
    """A client's session with the daemon, which calls `chat.*` as any client does."""
    del project
    peer, _ = dialed(where.at())
    try:
        yield peer
    finally:
        peer.close()


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
    # The stand-in chat says what it was told; the chat itself what the stand-in CLI did.
    assert until(
        lambda: _asked(heard, f"you said: {said}")() or _asked(heard, f"did: {said}")()
    )
    return link, heard, str(started["slot"]), str(started["chat"])


def _refused(user: Peer, method: str, **params: Any) -> tuple[int, str]:
    with pytest.raises(RpcError) as refused:
        user.call(method, params, timeout=60)
    return refused.value.code, refused.value.message


def _row(user: Peer, name: str) -> dict[str, Any]:
    """One chat as it stands now: its row, and the rest `chat.get` says of it."""
    return user.call("chat.get", {"chat": name}, timeout=30)


def _ended(link: daemon.Link, user: Peer, name: str) -> None:
    """Ends a chat as an empty next message does, and waits for it to rest."""
    link.chat_say("")
    assert until(lambda: _row(user, name)["state"] == "resting")
    link.close()


def _events(at: Path) -> list[dict[str, Any]]:
    return [json.loads(one) for one in (at / CHATTED).read_text().splitlines()]


def _directory(name: str) -> Path:
    (at,) = [one for one in written_chats() if one.name == name]
    return at


# ---------------------------------------------------------------- the host of a chat


def test_two_chats_and_a_flow_go_at_once_in_one_workspace(workspace: Path) -> None:
    written(workspace, "waits", WAITS)
    with daemon.attach("sdk", workspace=workspace) as flow:
        flow.start("./waits", "forever", budget={"cost": 1})
        first, _, slot_first, chat_first = _chat(workspace, "first")
        second, _, slot_second, chat_second = _chat(workspace, "second")
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
            # Each its own chat, and no epic; the flow's host its epic, and no chat.
            assert {slot: one["chat"] for slot, one in hosts.items()} == {
                "": "",
                slot_first: chat_first,
                slot_second: chat_second,
            }
            assert chat_first != chat_second
            assert (hosts[slot_first]["epic"], hosts[slot_second]["epic"]) == ("", "")
            (epic,) = every()
            assert hosts[""]["epic"] == epic.name
            assert {one.name for one in written_chats()} == {chat_first, chat_second}
            # As `hosts.running` says them to every client.
            peer, _ = dialed(where.at())
            try:
                running = {
                    one["slot"]: one
                    for one in peer.call("hosts.running", {}, timeout=30)["running"]
                }
            finally:
                peer.close()
            assert {
                slot: (one["kind"], one["epic"], one["chat"], one.get("turn"))
                for slot, one in running.items()
            } == {
                "": ("flow", epic.name, "", None),
                slot_first: ("chat", "", chat_first, "done"),
                slot_second: ("chat", "", chat_second, "done"),
            }
            # A second flow is still one too many on the workspace's own host.
            with pytest.raises(daemon.Refused, match="already running"):
                flow.start("./waits", "again", budget={"cost": 1})
        finally:
            first.close()
            second.close()
            flow.stop()


def test_a_chat_is_said_to_set_and_folds_away_to_be_carried_on_by_its_name(
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
    assert (said["epic_kind"], said["turn"]) == ("chat", "done")
    assert (said["epic"], said["chat"]) == ("", name)
    link.close()

    # Between turns with nobody reading: it folds, and its host goes.
    assert until(lambda: daemon.running(workspace, slot=slot) is None)
    with pytest.raises(OSError, match=r"This chat has folded away\."):
        reached(where.at(), where.workspace(workspace), slot=slot)
    peer, _ = dialed(where.at())
    try:
        for method, more in (("chat.say", {"text": "again"}), ("chat.stop", {})):
            with pytest.raises(RpcError) as folded:
                peer.call(
                    method,
                    {"workspace": str(workspace), "slot": slot, **more},
                    timeout=10,
                )
            assert (folded.value.code, folded.value.message) == (
                409,
                "this chat has folded away; carry it on with chat.start",
            )
    finally:
        peer.close()
    (chat,) = written_chats()
    assert chat.name == name
    assert every() == []

    again, heard_again, _, carried = _chat(
        workspace, "what was it?", agent="", resume=name
    )
    try:
        # The same chat, opened again rather than a new one beside it.
        assert carried == name
        assert written_chats() == [chat]
        assert every() == []
        assert heard_again.of("started")[-1]["resume"] == name
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
        with pytest.raises(daemon.Refused, match="no chat is going here"):
            link.chat_stop()

    assert every() == []
    assert written_chats() == []
    assert Hmz(workspace).settings.chat_agent is None


def test_a_chat_carried_on_while_it_is_going_elsewhere_is_refused_saying_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The chat itself, not its stand-in: it is the chat that looks at what it carries on.
    at = install(tmp_path, monkeypatch)
    backend, _, model = AGENT.partition("/")
    drove = Drove("assistant", backend, model.partition(":")[0], "")
    with hosting(), Epic("", "first", at, kind="chat", agents=[drove]) as chat:
        assert going(chat.path)
        with (
            daemon.attach("sdk", workspace=at, slot=where.chat()) as link,
            pytest.raises(
                daemon.Refused, match=f"{chat.path.name} is going on already"
            ),
        ):
            link.chat(AGENT, "second voice", resume=chat.path.name)
        # Held by this process, which is no host: it is going, and so never deleted.
        peer, _ = dialed(where.at())
        try:
            assert _row(peer, chat.path.name)["state"] == "going"
            assert _refused(peer, "chat.delete", chat=chat.path.name) == (
                409,
                f"Chat {chat.path.name} is going on; delete it once it rests.",
            )
        finally:
            peer.close()
        assert chat.path.is_dir()


# ------------------------------------------------------------- a chat's own record


def test_a_chat_is_written_down_as_a_chat_and_is_no_epic(
    project: Path, user: Peer
) -> None:
    link, _, slot, name = _chat(project, "hello there\nand the rest", f"{AGENT}:high")

    # Under `chats/`, by its name, in a record of its own; nothing under `epics/`.
    at = home() / "chats" / under(project).name / name
    assert (at / CHATTED).is_file()
    assert not (at / JOURNAL).exists()
    assert written_chats() == [at]
    assert every() == []
    assert not (home() / "epics").exists() or not list(
        (home() / "epics").rglob("*.jsonl")
    )
    began = _events(at)[0]
    assert (began["event"], began["task"]) == ("began", "hello there\nand the rest")
    assert "kind" not in began
    assert "flow" not in began

    # `runs.*` knows nothing of it.
    assert user.call("runs.list", {}, timeout=30)["runs"] == []
    assert user.call("runs.list", {"workspace": str(project)}, timeout=30)["total"] == 0
    assert _refused(user, "runs.get", name=name) == (404, f"There is no epic {name}.")

    # `chat.list` and `chat.get` say it, going between turns on its host.
    listed = user.call("chat.list", {"workspace": str(project)}, timeout=30)
    (row,) = listed["chats"]
    assert (listed["total"], listed["offset"], listed["limit"]) == (1, 0, 50)
    assert set(row) == ROW
    assert row | {"updated": "", "spent": None} == {
        "id": name,
        "title": "hello there",
        "workspace": str(project.resolve()),
        "workdir": str(project.resolve()),
        "agent": f"{AGENT}:high",
        "model": MODEL,
        "began": began["at"],
        "updated": "",
        "state": "going",
        "slot": slot,
        "asking": [],
        "permission": "workspace-write",
        "archived": False,
        "spent": None,
    }
    assert row["updated"] >= row["began"]
    whole = user.call("chat.get", {"chat": name}, timeout=30)
    assert set(whole) == ROW | {
        "at",
        "task",
        "prefer",
        "forked",
        "adopted",
        "agents",
        "sessions",
        "earlier",
        "backup",
        "backed",
    }
    assert (whole["at"], whole["task"]) == (str(at), "hello there\nand the rest")
    assert (whole["prefer"], whole["forked"], whole["earlier"]) == ("", "", 0)
    (agent,) = whole["agents"]
    assert (agent["role"], agent["runs"]) == ("assistant", f"{AGENT}:high")
    (session,) = whole["sessions"]
    assert session["ident"] == started(project.parent)[0]["session"]
    assert "trace" not in whole
    (traced,) = user.call("chat.get", {"chat": name, "trace": True}, timeout=30)[
        "trace"
    ]
    assert "hello there" in json.dumps(traced)

    # Its host says the chat, and no epic; the workspace counts it apart from its epics.
    status = user.call(
        "hosts.status", {"workspace": str(project), "slot": slot}, timeout=30
    )
    assert (status["epic_kind"], status["epic"], status["chat"], status["turn"]) == (
        "chat",
        "",
        name,
        "done",
    )
    (running,) = user.call("hosts.running", {}, timeout=30)["running"]
    assert (running["kind"], running["epic"], running["chat"], running["turn"]) == (
        "chat",
        "",
        name,
        "done",
    )
    (place,) = [
        one
        for one in user.call("workspaces.list", {}, timeout=30)["workspaces"]
        if one["path"] == str(project.resolve())
    ]
    assert (place["epics"], place["chats"], place["running"]) == (0, 1, True)

    # Ended by an empty next message, it rests: nothing holds it, and it is there to carry on.
    _ended(link, user, name)
    rested = _row(user, name)
    assert (rested["state"], rested["slot"], rested["asking"]) == ("resting", "", [])
    assert rested["spent"]["output_tokens"] == 7
    assert {"money", "tokens", "worked"} <= set(rested["spent"])
    assert user.call("hosts.running", {}, timeout=30)["running"] == []
    # What it spent is still counted, as of the flow `chat`.
    usage = user.call("runs.usage", {"days": 1}, timeout=30)
    assert [one["flow"] for one in usage["flows"]] == ["chat"]
    assert usage["whole"]["output_tokens"] == 7


def test_a_chat_whose_first_turn_fails_is_listed_failed(
    project: Path, user: Peer
) -> None:
    link = daemon.attach("sdk", workspace=project, slot=where.chat())
    heard = Heard()
    link.heard(heard)
    try:
        # Written down before its first turn is taken, which is what it is named by.
        said = link.chat(AGENT, "fail: it broke")
        name = str(said["chat"])
        assert until(lambda: heard.of("ended"))
        (ended,) = heard.of("ended")
        assert ended["how"] == "failed"
        assert "it broke" in ended["why"]
        # Its host says which chat it was that ended so, and no epic.
        last = user.call(
            "hosts.status",
            {"workspace": str(project), "slot": said["slot"]},
            timeout=30,
        )["ended"]
        assert (last["how"], last["kind"], last["chat"], last["epic"]) == (
            "failed",
            "chat",
            name,
            "",
        )
    finally:
        link.close()

    (row,) = user.call("chat.list", {}, timeout=30)["chats"]
    assert (row["id"], row["state"], row["slot"], row["title"]) == (
        name,
        "failed",
        "",
        "fail: it broke",
    )
    assert user.call("runs.list", {}, timeout=30)["runs"] == []


def test_a_turn_is_stopped_and_the_chat_stays_to_take_the_next_message(
    project: Path, user: Peer
) -> None:
    link, heard, slot, name = _chat(project, "hello")
    host = {"workspace": str(project), "slot": slot}
    no_turn = (409, "no turn is open, so there is nothing to stop")
    try:
        # Between turns there is nothing to stop, by either name for it.
        assert _refused(user, "chat.stop", **host) == no_turn
        with pytest.raises(daemon.Refused, match="no turn is open") as refused:
            link.stop()
        assert refused.value.code == 409
        assert _row(user, name)["state"] == "going"

        for stops in (
            lambda: user.call("chat.stop", host, timeout=30),
            link.chat_stop,
            # `epic.stop` on a chat's host is its turn's, and never the chat's.
            link.stop,
        ):
            stopped = len([one for one in heard.of("asked") if one["text"] == STOPPED])
            link.chat_say(SLOW)
            assert until(lambda: _row(user, name)["state"] == "turn")
            status = user.call("hosts.status", host, timeout=30)
            assert (status["turn"], status["chat"]) == ("running", name)

            stops()

            # Said in the conversation, which waits on the next message.
            assert until(
                lambda stopped=stopped: (
                    len([one for one in heard.of("asked") if one["text"] == STOPPED])
                    == stopped + 1
                )
            )
            assert until(lambda: _row(user, name)["state"] == "going")
            assert _refused(user, "chat.stop", **host) == no_turn
            assert heard.of("ended") == []

        # It takes another message, in the conversation it was having.
        link.chat_say("and after?")
        assert until(_asked(heard, "did: and after?"))
        ran = Hmz(project).epics.read(_directory(name))
        assert ran is not None
        assert (ran.how, ran.ended) == ("", "")
        assert user.call("hosts.status", host, timeout=30)["state"] == "running"
    finally:
        link.close()


def test_a_chat_is_renamed_and_keeps_its_title_as_it_is_carried_on(
    project: Path, user: Peer
) -> None:
    link, _, _, name = _chat(project, "the word is papaya\nand nothing else")
    # Its first line, until it is given another.
    assert _row(user, name)["title"] == "the word is papaya"

    # Renamed while it goes, as its row then says.
    renamed = user.call(
        "chat.rename", {"chat": name, "title": " Fruit\n salad "}, timeout=30
    )
    assert set(renamed) == ROW
    assert (renamed["id"], renamed["title"], renamed["state"]) == (
        name,
        "Fruit salad",
        "going",
    )
    assert _refused(user, "chat.rename", chat=name, title="  ") == (
        400,
        "A chat's title says something.",
    )
    _ended(link, user, name)
    assert _row(user, name)["title"] == "Fruit salad"

    again, _, _, carried = _chat(project, "what was the word?", agent="", resume=name)
    try:
        assert carried == name
        row = _row(user, name)
        assert (row["title"], row["state"]) == ("Fruit salad", "going")
        whole = user.call("chat.get", {"chat": name}, timeout=30)
        assert (whole["task"], whole["earlier"], len(whole["sessions"])) == (
            "the word is papaya\nand nothing else",
            1,
            2,
        )
        # Found by its title, its first message or its name.
        for q in ("fruit", "PAPAYA", name[-6:]):
            found = user.call("chat.list", {"q": q}, timeout=30)
            assert [one["id"] for one in found["chats"]] == [name]
        assert user.call("chat.list", {"q": "durian"}, timeout=30)["total"] == 0
    finally:
        again.close()


def test_a_chat_is_forked_into_a_new_one_that_goes_on_from_a_copy(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    link, heard, slot, name = _chat(project, "the word is papaya")
    at = _directory(name)

    # Never while a turn is open: the conversation is not standing still to copy.
    link.chat_say(SLOW)
    assert until(lambda: _row(user, name)["state"] == "turn")
    assert _refused(user, "chat.fork", chat=name) == (
        409,
        f"Chat {name} has a turn open; fork it once it is done.",
    )
    user.call("chat.stop", {"workspace": str(project), "slot": slot}, timeout=30)
    assert until(_asked(heard, STOPPED))
    _ended(link, user, name)
    before = (at / CHATTED).read_bytes()
    kept = sorted(one.relative_to(at) for one in (at / SESSIONS).rglob("*.jsonl"))

    forked = user.call("chat.fork", {"chat": name}, timeout=30)["chat"]

    assert forked != name
    listed = user.call("chat.list", {"workspace": str(project)}, timeout=30)["chats"]
    assert [one["id"] for one in listed] == [forked, name]
    fork = user.call("chat.get", {"chat": forked}, timeout=30)
    assert (fork["forked"], fork["state"], fork["title"], fork["task"]) == (
        name,
        "resting",
        "the word is papaya",
        "the word is papaya",
    )
    assert user.call("chat.get", {"chat": name}, timeout=30)["forked"] == ""
    copy = _directory(forked)
    assert copy.parent == at.parent
    assert (
        sorted(one.relative_to(copy) for one in (copy / SESSIONS).rglob("*.jsonl"))
        == kept
    )

    # Carried on, the fork goes on from the copy; the chat it was forked from is as it was.
    again, _, _, carried = _chat(project, "what was the word?", agent="", resume=forked)
    try:
        assert carried == forked
        last = started(tmp_path)[-1]
        assert "--resume" in last["argv"]
        whole = user.call("chat.get", {"chat": forked}, timeout=30)
        assert whole["sessions"][-1]["parent"] == whole["sessions"][-2]["ident"]
    finally:
        again.close()
    assert (at / CHATTED).read_bytes() == before
    assert (
        sorted(one.relative_to(at) for one in (at / SESSIONS).rglob("*.jsonl")) == kept
    )


def _harness_session(tmp_path: Path, project: Path, ident: str, said: str) -> Path:
    """A session the stand-in `claude` had of its own in the project, as it logs one."""
    plain = "".join(one if one.isalnum() else "-" for one in str(project))
    log = tmp_path / "claude" / "projects" / plain / f"{ident}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "type": "user",
            "sessionId": ident,
            "cwd": str(project),
            "timestamp": "2026-01-01T00:00:00+00:00",
            "message": {"role": "user", "content": said},
        },
        {
            "type": "assistant",
            "sessionId": ident,
            "cwd": str(project),
            "timestamp": "2026-01-01T00:00:05+00:00",
            "message": {
                "model": MODEL,
                "role": "assistant",
                "content": [{"type": "text", "text": f"did: {said}"}],
            },
        },
    ]
    log.write_text("".join(json.dumps(one) + "\n" for one in rows))
    return log


def test_a_harness_session_is_listed_read_and_continued_as_a_chat_from_a_copy(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    ident = "0a0a0a0a-1111-4222-8333-444444444444"
    log = _harness_session(tmp_path, project, ident, "the word is guava")
    before = log.read_bytes()
    # A chat Humanize had here keeps its sessions itself: none of them is a harness session.
    link, _, _, mine = _chat(project, "a chat of humanize's own")
    _ended(link, user, mine)
    named = {"workspace": str(project), "harness": "claude", "session": ident}

    listed = user.call("chat.harness.list", {"workspace": str(project)}, timeout=30)

    assert (listed["total"], listed["offset"], listed["limit"]) == (1, 0, 50)
    (row,) = listed["sessions"]
    assert set(row) == {
        "id",
        "harness",
        "title",
        "workspace",
        "model",
        "began",
        "updated",
    }
    assert (row["id"], row["harness"], row["title"], row["model"]) == (
        ident,
        "claude",
        "the word is guava",
        MODEL,
    )
    assert row["workspace"] == str(project.resolve())
    read = user.call("chat.harness.get", {**named, "trace": True}, timeout=30)
    (session,) = read["trace"]
    assert session["key"] == f"claude:{ident}"
    assert sorted(one["category"] for one in session["actions"]) == ["message", "turn"]
    assert _refused(user, "chat.harness.get", **named | {"session": "none"}) == (
        404,
        f"There is no claude session none of {project}.",
    )
    assert _refused(user, "chat.harness.adopt", **named | {"harness": "opencode"}) == (
        409,
        "A session of opencode cannot be continued in a chat.",
    )

    adopted = user.call("chat.harness.adopt", named, timeout=30)["chat"]

    whole = user.call("chat.get", {"chat": adopted, "trace": True}, timeout=30)
    assert (whole["adopted"], whole["state"], whole["title"], whole["agent"]) == (
        f"claude:{ident}",
        "resting",
        "the word is guava",
        f"{AGENT}:auto",
    )
    # Read once, though its harness still has the session the chat holds a copy of.
    assert [one["key"] for one in whole["trace"]] == [f"claude:{ident}"]
    copy = _directory(adopted)
    assert [
        one.relative_to(copy / SESSIONS).parts[0] for one in copy.rglob(log.name)
    ] == ["claude"]
    assert next(copy.rglob(log.name)).read_bytes() == before
    began = _events(copy)[0]
    assert (began["event"], began["adopted"]) == ("began", f"claude:{ident}")
    ids = [
        one["id"]
        for one in user.call("chat.list", {"workspace": str(project)}, timeout=30)[
            "chats"
        ]
    ]
    assert ids == [adopted, mine]
    # A chat's now, and so no harness session; refused as none from here on.
    again = user.call("chat.harness.list", {"workspace": str(project)}, timeout=30)
    assert again["sessions"] == []
    assert _refused(user, "chat.harness.adopt", **named)[0] == 404

    # Carried on, the chat goes on from the copy; the harness's own session is as it was.
    carried, _, _, name = _chat(project, "what was the word?", agent="", resume=adopted)
    try:
        assert name == adopted
        last = started(tmp_path)[-1]
        assert "--resume" in last["argv"]
        went = user.call("chat.get", {"chat": adopted}, timeout=30)["sessions"]
        assert (went[0]["ident"], went[-1]["parent"]) == (ident, ident)
    except BaseException:
        carried.close()
        raise
    assert log.read_bytes() == before
    assert sorted(one.name for one in log.parent.iterdir()) == [log.name]

    # Deleted, the chat gives the session back to the list it came from.
    _ended(carried, user, adopted)
    user.call("chat.delete", {"chat": adopted}, timeout=30)
    back = user.call("chat.harness.list", {"workspace": str(project)}, timeout=30)
    assert [one["id"] for one in back["sessions"]] == [ident]


def test_a_chat_with_no_conversation_kept_in_it_is_not_forked(
    project: Path, user: Peer
) -> None:
    with Epic("", "nothing said yet", project, kind="chat") as chat:
        chat.stopped()
    name = chat.path.name

    assert _refused(user, "chat.fork", chat=name) == (
        409,
        f"{name} cannot be forked: its conversation is not kept in the chat.",
    )
    assert _refused(user, "chat.fork", chat="20200101-none") == (
        404,
        "There is no chat 20200101-none.",
    )
    assert written_chats() == [chat.path]


def test_a_chat_is_archived_off_the_list_and_back_onto_it(
    project: Path, user: Peer
) -> None:
    link, _, _, name = _chat(project, "hello")
    _ended(link, user, name)
    with Epic("", "another", project, kind="chat") as other:
        other.stopped()

    def listed(**said: Any) -> list[str]:
        return [one["id"] for one in user.call("chat.list", said, timeout=30)["chats"]]

    assert listed() == [other.path.name, name]
    assert listed(archived=True) == []

    archived = user.call("chat.archive", {"chat": name}, timeout=30)

    assert set(archived) == ROW
    assert (archived["id"], archived["archived"]) == (name, True)
    assert listed() == [other.path.name]
    assert listed(archived=False) == [other.path.name]
    assert listed(archived=True) == [name]
    assert listed(archived=True, workspace=str(project)) == [name]
    assert user.call("chat.get", {"chat": name}, timeout=30)["archived"] is True
    # Once is enough: archiving it again writes nothing more.
    events = _events(_directory(name))
    assert user.call("chat.archive", {"chat": name}, timeout=30)["archived"] is True
    assert _events(_directory(name)) == events
    assert events[-1]["event"] == "set"
    assert events[-1]["archived"] is True

    # Archived, it is still a chat to carry on, and stays archived until it is said not to be.
    again, _, _, _ = _chat(project, "more", agent="", resume=name)
    _ended(again, user, name)
    assert listed(archived=True) == [name]

    assert user.call("chat.unarchive", {"chat": name}, timeout=30)["archived"] is False
    assert listed() == [other.path.name, name]
    assert listed(archived=True) == []
    for method in ("chat.archive", "chat.unarchive"):
        assert _refused(user, method, chat="20200101-none") == (
            404,
            "There is no chat 20200101-none.",
        )


def test_a_chat_is_backed_up_as_a_run_is(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    bare = tmp_path / "chats.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    link, _, _, name = _chat(project, "hello")
    _ended(link, user, name)

    assert _refused(user, "chat.backup", chat=name) == (
        409,
        "There is no backup target: add one in Settings.",
    )
    (home() / "settings.yaml").write_text(
        yaml.safe_dump({"backup": {"targets": [{"name": "t", "url": str(bare)}]}})
    )
    code, why = _refused(user, "chat.backup", chat=name, to=["nowhere"])
    assert (code, "nowhere" in why) == (400, True)

    assert user.call("chat.backup", {"chat": name, "to": ["t"]}, timeout=30) == {
        "queued": ["t"]
    }

    # Queued and never waited on: how it went is read back off the chat.
    assert until(
        lambda: "t" in user.call("chat.get", {"chat": name}, timeout=30)["backed"], 60
    )
    backed = user.call("chat.get", {"chat": name}, timeout=30)["backed"]["t"]
    assert (backed["ok"], backed["error"], backed["why"]) == (True, "", "manual")
    held = subprocess.run(
        ["git", "--git-dir", str(bare), "ls-tree", "-r", "--name-only", "main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    key = backing.where(_directory(name))
    assert f"{key}/{CHATTED}" in held
    assert any(one.startswith(f"{key}/{SESSIONS}/") for one in held)
    assert _refused(user, "chat.backup", chat="20200101-none") == (
        404,
        "There is no chat 20200101-none.",
    )


def test_a_chat_is_deleted_with_what_it_kept_and_never_while_it_goes(
    project: Path, user: Peer
) -> None:
    link, _, _, name = _chat(project, "hello")
    at = _directory(name)
    with Epic("ralph", "a run", project) as ran:
        pass

    # Going, on its host: refused, and all of it still there.
    assert _refused(user, "chat.delete", chat=name) == (
        409,
        f"Chat {name} is going on; delete it once it rests.",
    )
    assert (at / CHATTED).is_file()
    # An epic is no chat, and is never removed by this.
    assert _refused(user, "chat.delete", chat=ran.path.name) == (
        404,
        f"There is no chat {ran.path.name}.",
    )
    for sly in ("../epics", f"../../epics/{under(project).name}/{ran.path.name}", "."):
        assert _refused(user, "chat.delete", chat=sly)[0] == 404
    _ended(link, user, name)
    assert list((at / SESSIONS).rglob("*.jsonl"))

    assert user.call("chat.delete", {"chat": name}, timeout=30) == {}

    # Its record and the sessions kept beside it, gone for good.
    assert not at.exists()
    assert written_chats() == []
    assert user.call("chat.list", {}, timeout=30) == {
        "chats": [],
        "total": 0,
        "offset": 0,
        "limit": 50,
    }
    gone = (404, f"There is no chat {name}.")
    assert _refused(user, "chat.get", chat=name) == gone
    assert _refused(user, "chat.delete", chat=name) == gone
    assert _refused(
        user, "chat.start", workspace=str(project), task="more", resume=name
    ) == (404, f"{name} is not a chat of {project.resolve()}.")
    assert ran.path.is_dir()
    assert (ran.path / JOURNAL).is_file()
    assert [one["name"] for one in user.call("runs.list", {}, timeout=30)["runs"]] == [
        ran.path.name
    ]


# ------------------------------------------------------------- where a chat works


def _git(at: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(at), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_a_chat_started_in_a_worktree_works_there_and_returns_there(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    _git(project, "init", "-q", "-b", "main")
    _git(project, "config", "user.email", "a@example.com")
    _git(project, "config", "user.name", "Ada")
    _git(project, "config", "commit.gpgsign", "false")
    (project / "kept").write_text("kept\n")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "one")

    link, _, _, name = _chat(project, "hello there", worktree=True)

    row = _row(user, name)
    worktree = Path(row["workdir"])
    # The chat is the workspace's still; its assistant works in a detached worktree of it.
    assert row["workspace"] == str(project.resolve())
    assert worktree.resolve() != project.resolve()
    assert worktree.is_relative_to(home() / "envs")
    assert _events(_directory(name))[0]["workdir"] == row["workdir"]
    assert _git(worktree, "rev-parse", "HEAD") == _git(project, "rev-parse", "HEAD")
    assert _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert Path(started(tmp_path)[-1]["cwd"]).resolve() == worktree.resolve()
    assert (worktree / "landed.txt").read_text() == "hello there\n"
    assert not (project / "landed.txt").exists()
    _ended(link, user, name)

    # A chat carried on works where it worked, and is never given another worktree.
    assert _refused(
        user,
        "chat.start",
        workspace=str(project),
        task="more",
        resume=name,
        worktree=True,
    ) == (400, "a chat carried on works where it worked")
    again, _, _, carried = _chat(project, "and then?", agent="", resume=name)
    assert carried == name
    assert Path(started(tmp_path)[-1]["cwd"]).resolve() == worktree.resolve()
    assert (worktree / "landed.txt").read_text() == "hello there\nand then?\n"
    assert not (project / "landed.txt").exists()
    assert _row(user, name)["workdir"] == row["workdir"]
    assert len(_git(project, "worktree", "list", "--porcelain").split("\n\n")) == 2
    _ended(again, user, name)

    # Deleted, the chat goes and its worktree stays: what was done there is the person's.
    assert user.call("chat.delete", {"chat": name}, timeout=30) == {}
    assert not _directory_or_none(name)
    assert (worktree / "landed.txt").is_file()
    assert str(worktree.resolve()) in _git(project, "worktree", "list", "--porcelain")


def _directory_or_none(name: str) -> Path | None:
    return next((one for one in written_chats() if one.name == name), None)


def test_a_worktree_is_refused_where_the_workspace_is_no_repository(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    code, why = _refused(
        user,
        "chat.start",
        workspace=str(project),
        slot="chat:",
        agent=AGENT,
        task="hello there",
        worktree=True,
    )

    assert code == 400
    assert "git" in why
    # Nothing was written down, started or left going.
    assert written_chats() == []
    assert started(tmp_path) == []
    assert user.call("chat.list", {}, timeout=30)["total"] == 0
    assert until(lambda: user.call("hosts.running", {}, timeout=30)["running"] == [])


# --------------------------------------------- what an earlier hmz wrote for a chat


def test_an_epic_an_earlier_hmz_recorded_for_a_chat_is_an_epic_and_no_chat(
    project: Path, user: Peer
) -> None:
    old = old_chat(project, "old words")
    older = old_chat(project, "still older words", flow="chat", resumable=True)

    # Read by `runs.*` as the epics they are, of kind `chat` and no flow.
    listed = user.call("runs.list", {"workspace": str(project)}, timeout=30)
    assert {
        one["name"]: (one["kind"], one["flow"], one["how"]) for one in listed["runs"]
    } == {
        old.name: ("chat", "", "stopped"),
        older.name: ("chat", "", "stopped"),
    }
    assert listed["flows"] == ["chat"]
    for at, task in ((old, "old words"), (older, "still older words")):
        whole = user.call("runs.get", {"name": at.name}, timeout=30)
        assert (whole["kind"], whole["flow"], whole["task"]) == ("chat", "", task)
        # Nothing of a chat's is said of an epic any more.
        for absent in ("earlier", "permission", "prefer", "turn"):
            assert absent not in whole

    # And they are no chats: not listed, not read, not changed, and not carried on.
    assert user.call("chat.list", {}, timeout=30)["total"] == 0
    assert user.call("chat.list", {"archived": True}, timeout=30)["total"] == 0
    for at in (old, older):
        gone = (404, f"There is no chat {at.name}.")
        assert _refused(user, "chat.get", chat=at.name) == gone
        assert _refused(user, "chat.rename", chat=at.name, title="mine") == gone
        assert _refused(user, "chat.fork", chat=at.name) == gone
        assert _refused(user, "chat.archive", chat=at.name) == gone
        assert _refused(user, "chat.delete", chat=at.name) == gone
        for resume in (at.name, str(at)):
            assert _refused(
                user, "chat.start", workspace=str(project), task="more", resume=resume
            ) == (404, f"{resume} is not a chat of {project.resolve()}.")
        assert (at / JOURNAL).is_file()
    assert written_chats() == []
    assert user.call("hosts.running", {}, timeout=30)["running"] == []


def test_a_chat_carried_on_is_named_by_its_name_alone(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    link, _, _, name = _chat(project, "the word is papaya")
    _ended(link, user, name)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    # Neither its directory, nor from another workspace, nor a name there is no chat of.
    for workspace, resume in (
        (project, str(_directory(name))),
        (elsewhere, name),
        (project, "20200101T000000.000Z-000000"),
    ):
        assert _refused(
            user, "chat.start", workspace=str(workspace), task="more", resume=resume
        ) == (404, f"{resume} is not a chat of {workspace.resolve()}.")

    said = user.call(
        "chat.start",
        {"workspace": str(project), "task": "what was the word?", "resume": name},
        timeout=60,
    )

    # On a new slot of its own, with the agent and the conversation it had.
    assert said["chat"] == name
    assert said["slot"].startswith("chat:")
    assert until(lambda: _row(user, name)["state"] == "going")
    assert _row(user, name)["slot"] == said["slot"]
    first, then = started(tmp_path)
    assert then["argv"][then["argv"].index("--resume") + 1] == first["session"]
    assert written_chats() == [_directory(name)]
    # Going there, it is carried on nowhere else.
    code, why = _refused(
        user, "chat.start", workspace=str(project), task="twice", resume=name
    )
    assert (code, f"{name} is going on already" in why) == (400, True)


def test_a_chats_turn_done_is_a_notice_that_names_the_chat(
    project: Path, user: Peer
) -> None:
    last = user.call("notices.list", {}, timeout=30)["last"]
    link, _, slot, name = _chat(project, "hello")
    try:

        def told() -> list[dict[str, Any]]:
            return [
                one
                for one in user.call("notices.list", {"after": last}, timeout=30)[
                    "notices"
                ]
                if one["slot"] == slot
            ]

        assert until(told, 60)
        notice = told()[0]
        assert (notice["kind"], notice["flow"]) == ("done", "chat")
        assert (notice["chat"], notice["epic"]) == (name, "")
        # A side question about it is asked by its name too.
        assert user.call(
            "btw.list", {"workspace": str(project), "chat": name}, timeout=30
        ) == {"asides": []}
    finally:
        link.close()
