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
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import tomlkit

from hmz import daemon, home
from hmz.daemon import where
from hmz.daemon.link import dialed, reached
from hmz.rpc import RpcError
from hmz.runtime import Hmz, backing
from hmz.runtime.chatting import STOPPED, TURN_OPEN
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
    "folderless",
    "workdir",
    "env",
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
                f"Chat {chat.path.name} has a turn open; delete it once it is done.",
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
        "folderless": False,
        "workdir": str(project.resolve()),
        "env": _spelled(project),
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
        "continuable",
    }
    assert (row["id"], row["harness"], row["title"], row["model"]) == (
        ident,
        "claude",
        "the word is guava",
        MODEL,
    )
    assert row["continuable"] is True
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
    (home() / "settings.toml").write_text(
        tomlkit.dumps({"backup": {"targets": [{"name": "t", "url": str(bare)}]}})
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

    # The target lists it, as a chat this machine holds, and will not download it over itself.
    def stored() -> list[tuple[str, str, bool, bool]]:
        said = user.call("backups.epics", {"target": "t"}, timeout=60)["epics"]
        return [(one["key"], one["epic"], one["chat"], one["here"]) for one in said]

    assert stored() == [(key, name, True, True)]
    code, why = _refused(user, "backups.pull", target="t", key=key)
    assert (code, "already here" in why) == (400, True)

    # Deleted here, it is downloaded back among the chats, and is no epic.
    user.call("chat.delete", {"chat": name}, timeout=30)
    assert stored() == [(key, name, True, False)]
    assert user.call("backups.pull", {"target": "t", "key": key}, timeout=60) == {
        "name": name
    }
    assert stored() == [(key, name, True, True)]
    back = user.call("chat.get", {"chat": name}, timeout=30)
    assert (back["task"], back["state"], back["backup"]) == ("hello", "resting", [])
    listed = user.call("chat.list", {"workspace": str(project)}, timeout=30)["chats"]
    assert [one["id"] for one in listed] == [name]
    assert user.call("runs.list", {}, timeout=30)["runs"] == []


def test_a_chat_is_deleted_with_what_it_kept_and_never_while_its_turn_is_open(
    project: Path, user: Peer
) -> None:
    link, heard, slot, name = _chat(project, "hello")
    at = _directory(name)
    with Epic("ralph", "a run", project) as ran:
        pass

    # A turn open, on its host: refused, and all of it still there.
    link.chat_say(SLOW)
    assert until(lambda: _row(user, name)["state"] == "turn")
    assert _refused(user, "chat.delete", chat=name) == (
        409,
        f"Chat {name} has a turn open; delete it once it is done.",
    )
    assert (at / CHATTED).is_file()
    user.call("chat.stop", {"workspace": str(project), "slot": slot}, timeout=30)
    assert until(_asked(heard, STOPPED))
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


def test_a_chat_started_in_no_folder_works_in_a_directory_kept_as_long_as_it_is(
    project: Path, user: Peer
) -> None:
    # Section 2.3.6.1 of core.md, Section 4.7.1.3 of daemon.md, Section 7.7.8 of files.md.
    def listed() -> list[str]:
        return [
            one["path"]
            for one in user.call("workspaces.list", {}, timeout=30)["workspaces"]
        ]

    # The stand-in's own home, which nothing makes for an assistant held to no permission.
    (project.parent / "claude").mkdir(exist_ok=True)
    # Started as a frontend starts one: a host of its own in a directory made for it.
    made = user.call(
        "epic.attach", {"scratch": True, "slot": "chat:", "replay": False}, timeout=60
    )
    at, host = Path(made["workspace"]), {"workspace": made["workspace"]}
    assert at.parent == where.at().resolve() / "nofolder"
    assert at.is_dir()
    started = user.call(
        "chat.start",
        {
            **host,
            "slot": made["slot"],
            "agent": AGENT,
            "task": "hello",
            # Where it works is what is tested, not what holds it there.
            "permission": "danger-full-access",
        },
        timeout=60,
    )
    name, host["slot"] = started["chat"], started["slot"]
    user.call("epic.detach", {"sub": made["sub"]}, timeout=30)
    assert until(lambda: _row(user, name)["state"] == "going")

    # Told apart from a chat of somebody's folder by its row, and no folder to offer.
    with Epic("ralph", "a run", project):
        pass
    row = _row(user, name)
    assert (row["workspace"], row["folderless"], row["workdir"]) == (
        str(at),
        True,
        str(at),
    )
    (epic,) = user.call("runs.list", {}, timeout=30)["runs"]
    assert (epic["workspace"], epic["folderless"]) == (str(project.resolve()), False)
    assert listed() == [str(project.resolve())]

    # Kept while the chat is, whether or not a host stands in it.
    (at / "notes.md").write_text("kept")
    user.call("chat.say", {**host, "text": ""}, timeout=30)
    assert until(lambda: _row(user, name)["state"] == "resting")
    assert until(lambda: daemon.running(at, slot=host["slot"]) is None)
    assert (at / "notes.md").read_text() == "kept"

    # Cleaned away by the machine, it is made again for the chat carried on.
    shutil.rmtree(at)
    carried = user.call(
        "chat.start",
        {"workspace": str(at), "task": "more", "resume": name},
        timeout=60,
    )
    assert carried["chat"] == name
    assert at.is_dir()
    assert until(lambda: _row(user, name)["state"] == "going")
    (at / "notes.md").write_text("again")
    user.call(
        "chat.say",
        {"workspace": str(at), "slot": carried["slot"], "text": ""},
        timeout=30,
    )
    assert until(lambda: _row(user, name)["state"] == "resting")
    assert (at / "notes.md").read_text() == "again"

    # And it goes with the chat deleted: at once, or as the host still standing in it goes.
    assert user.call("chat.delete", {"chat": name}, timeout=30) == {}
    for held in user.call("hosts.list", {}, timeout=30)["held"]:
        user.call(
            "hosts.stop",
            {"workspace": held["workspace"], "slot": held["slot"]},
            timeout=30,
        )
    assert until(lambda: not at.exists())
    assert listed() == [str(project.resolve())]


def test_a_directory_made_for_no_folder_goes_where_nothing_was_started_in_it(
    project: Path, user: Peer
) -> None:
    del project
    made = user.call("epic.attach", {"scratch": True, "replay": False}, timeout=60)
    at = Path(made["workspace"])
    assert (at.is_dir(), made["slot"]) == (True, "")
    assert where.folderless(at)

    user.call("hosts.stop", {"workspace": str(at)}, timeout=30)

    assert until(lambda: not at.exists())


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


def _spelled(at: Path) -> str:
    """A directory of this machine as `-e` spells the env that is it."""
    return f"local/{str(at.resolve()).lstrip('/')}"


def test_a_chat_is_moved_to_another_env_between_turns_and_goes_on_there(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    link, heard, slot, name = _chat(project, "hello there")
    host = {"workspace": str(project), "slot": slot}
    try:
        # Until it is moved it works in its workspace, which its record says nothing of.
        row = _row(user, name)
        assert (row["env"], row["workdir"]) == (
            _spelled(project),
            str(project.resolve()),
        )
        assert "env" not in _events(_directory(name))[0]

        # What is no env is refused as -e refuses it; one that cannot take the chat leaves
        # it where it was, saying why.
        code, why = _refused(user, "chat.move", **host, env="nowhere/else")
        assert code == 400
        assert "nowhere" in why
        code, why = _refused(
            user, "chat.move", **host, env=_spelled(tmp_path / "missing")
        )
        assert code == 409
        assert why.startswith("The chat stays where it was: ")
        assert _row(user, name)["env"] == _spelled(project)

        # Not while its turn is open.
        link.chat_say(SLOW)
        assert until(lambda: _row(user, name)["state"] == "turn")
        assert _refused(user, "chat.move", **host, env=_spelled(other)) == (
            409,
            TURN_OPEN,
        )
        link.chat_stop()
        assert until(lambda: _row(user, name)["state"] == "going")

        moved = user.call("chat.move", {**host, "env": _spelled(other)}, timeout=60)
        assert moved == {"env": _spelled(other)}
        row = _row(user, name)
        # The chat is its workspace's still; its assistant works where it was moved to.
        assert (row["workspace"], row["env"], row["workdir"]) == (
            str(project.resolve()),
            _spelled(other),
            str(other.resolve()),
        )
        assert _events(_directory(name))[-1]["env"] == _spelled(other)

        link.chat_say("and here?")
        assert until(
            lambda: any(
                one.get("mode") == "listen"
                and str(one.get("text") or "").endswith("did: and here?")
                for one in heard.of("asked")
            )
        )
        assert Path(started(tmp_path)[-1]["cwd"]).resolve() == other.resolve()
        assert (other / "landed.txt").read_text() == "and here?\n"
        assert (project / "landed.txt").read_text() == "hello there\n"
        assert heard.of("ended") == []
    finally:
        link.close()


def test_a_chat_carried_on_goes_on_where_it_was_moved_and_moves_as_it_is_carried_on(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    there, back = tmp_path / "there", tmp_path / "back"
    there.mkdir()
    back.mkdir()
    # Started in an env, as one moved there would be.
    link, _, _, name = _chat(project, "hello there", env=_spelled(there))
    assert _events(_directory(name))[0]["env"] == _spelled(there)
    assert (there / "landed.txt").read_text() == "hello there\n"
    assert not (project / "landed.txt").exists()
    _ended(link, user, name)

    again, _, _, carried = _chat(project, "and then?", agent="", resume=name)
    assert carried == name
    assert (there / "landed.txt").read_text() == "hello there\nand then?\n"
    _ended(again, user, name)

    # Carried on with another env, it works there from then on.
    code, _ = _refused(
        user, "chat.start", workspace=str(project), task="x", resume=name, env="?"
    )
    assert code == 400
    moved, _, _, _ = _chat(
        project, "and back?", agent="", resume=name, env=_spelled(back)
    )
    assert (back / "landed.txt").read_text() == "and back?\n"
    assert _row(user, name)["env"] == _spelled(back)
    assert [one["env"] for one in _events(_directory(name)) if "env" in one] == [
        _spelled(there),
        _spelled(back),
    ]
    _ended(moved, user, name)

    # A fork stands where the chat stands.
    fork = user.call("chat.fork", {"chat": name}, timeout=30)["chat"]
    assert _row(user, fork)["env"] == _spelled(back)


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


@pytest.fixture
def legacy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A project of a home an earlier hmz left, which no daemon has started on yet."""
    at = install(tmp_path, monkeypatch)
    with hosting():
        yield at


def _dialed() -> Peer:
    peer, _ = dialed(where.at())
    return peer


def _moved(old: Path) -> Path:
    """Where the daemon moves a chat an earlier hmz kept as an epic."""
    return home() / "chats" / old.parent.name / old.name


def test_the_chats_an_earlier_hmz_kept_as_epics_are_chats_once_the_daemon_starts(
    legacy: Path, tmp_path: Path
) -> None:
    from hmz.daemon import reach

    old = old_chat(legacy, "old words")
    older = old_chat(legacy, "still older words", flow="chat", resumable=True)
    # One a daemon was killed halfway through moving: its record renamed, and no more.
    half = old_chat(legacy, "half moved")
    (half / JOURNAL).rename(half / CHATTED)
    # Her conversation an earlier hmz began, which her list names by its record.
    hers = old_chat(legacy, "what is going on here?")
    kept = reach.Conversations()
    made = kept.made(
        {
            "title": "what is going on here?",
            "scope": "workspace",
            "workspace": str(legacy.resolve()),
            "epic": "",
            "nous": AGENT,
            "preset": "read-only",
            "network": False,
            "slot": "ai:0ld",
        }
    )
    kept.changed(made["id"], record=hers.name)
    with Epic("ralph", "a run", legacy) as flow:
        pass
    (old / SESSIONS / "claude" / "kept.txt").write_text("kept")
    wrote = {
        one.name: (one / (CHATTED if one == half else JOURNAL)).read_bytes()
        for one in (old, older, half, hers)
    }
    mine = sorted(one.name for one in (old, older, half))

    daemon.start()
    user = _dialed()
    try:
        # Each is the directory it was, among the chats, its record the bytes it was.
        for name, written_down in wrote.items():
            at = _moved(old.parent / name)
            assert (at / CHATTED).read_bytes() == written_down
            assert not (at / JOURNAL).exists()
            assert not (old.parent / name).exists()
        assert (_moved(old) / SESSIONS / "claude" / "kept.txt").read_text() == "kept"
        assert every() == [flow.path]

        # Listed, read and found as the chats they are; hers is hers, and left out.
        listed = user.call("chat.list", {"workspace": str(legacy)}, timeout=30)
        assert sorted(one["id"] for one in listed["chats"]) == mine
        for one in listed["chats"]:
            assert set(one) == ROW
            assert (one["state"], one["slot"], one["model"]) == (
                "resting",
                "",
                "claude-haiku-4-5",
            )
        whole = user.call("chat.get", {"chat": old.name, "trace": True}, timeout=30)
        assert (whole["id"], whole["task"], whole["title"], len(whole["sessions"])) == (
            old.name,
            "old words",
            "old words",
            1,
        )
        # The session it says it opened kept no log an earlier hmz could have left here.
        assert whole["trace"] == []
        assert user.call("chat.get", {"chat": hers.name}, timeout=30)["task"] == (
            "what is going on here?"
        )
        assert _refused(user, "chat.rename", chat=hers.name, title="mine") == (
            404,
            f"There is no chat {hers.name}.",
        )

        # And none of them is an epic any more: the runs are the one run of a flow.
        runs = user.call("runs.list", {"workspace": str(legacy)}, timeout=30)
        assert [(one["name"], one["kind"]) for one in runs["runs"]] == [
            (flow.path.name, "flow")
        ]
        assert runs["flows"] == ["ralph"]
        for name in wrote:
            assert _refused(user, "runs.get", name=name) == (
                404,
                f"There is no epic {name}.",
            )

        # Changed as any chat is, in the record it has.
        renamed = user.call(
            "chat.rename", {"chat": older.name, "title": "Older"}, timeout=30
        )
        assert (renamed["id"], renamed["title"]) == (older.name, "Older")
        forked = user.call("chat.fork", {"chat": old.name}, timeout=30)["chat"]
        assert (_moved(old).parent / forked / CHATTED).is_file()

        # Carried on by its name, in the same chat.
        said = user.call(
            "chat.start",
            {"workspace": str(legacy), "task": "and now?", "resume": old.name},
            timeout=60,
        )
        assert said["chat"] == old.name
        assert until(lambda: _row(user, old.name)["state"] == "going")
        assert until(lambda: len(started(tmp_path)) == 1)
        # What it says and does from here on is read back as any chat's is.
        assert until(
            lambda: any(
                one["actions"]
                for one in user.call(
                    "chat.get", {"chat": old.name, "trace": True}, timeout=30
                )["trace"]
            )
        )
    finally:
        user.close()

    record = (_moved(old) / CHATTED).read_bytes()
    # Appended to, and never rewritten: what the earlier hmz wrote is what it begins with.
    assert record.startswith(wrote[old.name])
    events = [json.loads(one)["event"] for one in record.splitlines()]
    assert events[:3] == ["began", "opened", "ended"]
    assert "reopened" in events[3:]


def test_a_daemon_started_again_moves_nothing_and_leaves_one_going_for_later(
    legacy: Path,
) -> None:
    import fcntl
    import os

    old = old_chat(legacy, "old words")
    going_on = old_chat(legacy, "going on elsewhere")
    wrote = (going_on / JOURNAL).read_bytes()
    # Held, as the process going with it holds it.
    lock = os.open(going_on / ".held", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with hosting():
            daemon.start()
            first = int(where.held(where.at())["pid"])
            user = _dialed()
            try:
                listed = user.call("chat.list", {}, timeout=30)
                assert [one["id"] for one in listed["chats"]] == [old.name]
                # The one going is where it was, as it was, and neither chat nor epic yet.
                assert (going_on / JOURNAL).read_bytes() == wrote
                assert not (going_on / CHATTED).exists()
                assert user.call("runs.list", {}, timeout=30)["total"] == 0
                assert _refused(user, "chat.get", chat=going_on.name) == (
                    404,
                    f"There is no chat {going_on.name}.",
                )
            finally:
                user.close()
        log = (where.at() / where.LOG).read_text()
        assert f"moved 1 chat(s) kept as epics: {old.name}" in log
        assert f"left the chat {going_on.name} among the epics: it is going" in log
    finally:
        os.close(lock)
    moved = (_moved(old) / CHATTED).read_bytes()

    # Started again once that one has ended, it moves it, and touches nothing it moved.
    assert until(lambda: not where.alive(first))
    daemon.start()
    user = _dialed()
    try:
        listed = user.call("chat.list", {}, timeout=30)
        assert sorted(one["id"] for one in listed["chats"]) == sorted(
            [old.name, going_on.name]
        )
        assert (_moved(going_on) / CHATTED).read_bytes() == wrote
        assert (_moved(old) / CHATTED).read_bytes() == moved
        assert every() == []
    finally:
        user.close()


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


def test_a_chat_carried_on_with_nothing_said_holds_its_workspace_and_writes_nothing(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    link, _, _, name = _chat(project, "the word is papaya")
    _ended(link, user, name)
    at = _directory(name)
    wrote = (at / CHATTED).read_bytes()
    (project / "kept.txt").write_text("kept")
    carried = {"workspace": str(project), "task": "", "resume": name}

    # A new chat still starts with something said.
    assert _refused(
        user, "chat.start", workspace=str(project), agent=AGENT, task=""
    ) == (400, "a chat starts with something said")
    woke = user.call("chat.start", carried, timeout=60)
    assert woke["chat"] == name
    assert woke["slot"].startswith("chat:")
    # Asked again, it is the one host.
    assert user.call("chat.start", carried, timeout=60) == woke
    row = _row(user, name)
    assert (row["state"], row["slot"]) == ("going", woke["slot"])
    # Nothing is written into it, and no conversation is opened for it.
    assert (at / CHATTED).read_bytes() == wrote
    assert len(started(tmp_path)) == 1

    # Its workspace is open there, before anything is said.
    again = daemon.attach("sdk", workspace=project, slot=woke["slot"])
    heard = Heard()
    again.heard(heard)
    try:
        assert until(lambda: any(one["envs"] for one in heard.of("envs")))
        (env,) = heard.of("envs")[-1]["envs"]
        assert (env["role"], env["open"]) == ("workspace", True)
        listed = again.asked({"do": "env.list", "env": env["id"], "path": ""})
        assert "kept.txt" in [one["name"] for one in listed["entries"]]
        assert heard.of("started")[-1]["task"] == ""
        assert (at / CHATTED).read_bytes() == wrote

        # What is said then carries it on: the same chat, in the conversation it had. Said
        # by chat.start, as one who follows no host says it, it is said to the host standing by.
        said = {**carried, "task": "what was the word?"}
        assert user.call("chat.start", said, timeout=60) == woke
        assert until(_asked(heard, "did: what was the word?"))
        # Once something is said there, it is going there already.
        code, why = _refused(user, "chat.start", **{**carried, "task": "twice"})
        assert (code, why) == (400, f"{name} is going on already")
        first, then = started(tmp_path)
        assert then["argv"][then["argv"].index("--resume") + 1] == first["session"]
        events = [one["event"] for one in _events(at)]
        assert events.count("reopened") == 1
        assert written_chats() == [at]
    finally:
        again.close()


def test_a_chat_moved_with_nothing_said_reads_as_where_it_now_works(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    there, on = tmp_path / "there", tmp_path / "on"
    there.mkdir()
    on.mkdir()
    link, _, _, name = _chat(project, "hello there")
    _ended(link, user, name)
    at = _directory(name)
    wrote = (at / CHATTED).read_bytes()
    carried = {"workspace": str(project), "task": "", "resume": name}

    # Moved on the host that stands by with it, its row says so, its record nothing yet.
    woke = user.call("chat.start", carried, timeout=60)
    named = {"workspace": str(project), "slot": woke["slot"]}
    assert _row(user, name)["env"] == _spelled(project)
    moved = user.call("chat.move", {**named, "env": _spelled(there)}, timeout=60)
    assert moved["env"] == _spelled(there)
    row = _row(user, name)
    assert (row["env"], row["workdir"]) == (_spelled(there), str(there))
    (listed,) = [
        one
        for one in user.call("chat.list", {}, timeout=30)["chats"]
        if one["id"] == name
    ]
    assert listed["env"] == _spelled(there)
    assert (at / CHATTED).read_bytes() == wrote

    # Carried on there with an env and nothing to say, it is moved, not only answered; an
    # env it is in already moves nothing, and one that cannot take it refuses the call.
    assert user.call("chat.start", {**carried, "env": _spelled(on)}, timeout=60) == woke
    assert _row(user, name)["env"] == _spelled(on)
    assert user.call("chat.start", {**carried, "env": _spelled(on)}, timeout=60) == woke
    code, why = _refused(
        user, "chat.start", **carried, env=_spelled(tmp_path / "missing")
    )
    assert code == 409
    assert why.startswith("The chat stays where it was: ")
    assert _row(user, name)["env"] == _spelled(on)

    # What is said then is said there, and its record says where from then on.
    again = daemon.attach("sdk", workspace=project, slot=woke["slot"])
    heard = Heard()
    again.heard(heard)
    try:
        again.chat_say("and here?")
        assert until(_asked(heard, "did: and here?"))
        assert (on / "landed.txt").read_text() == "and here?\n"
        assert [one["env"] for one in _events(at) if "env" in one] == [_spelled(on)]
        assert _row(user, name)["env"] == _spelled(on)
    finally:
        _ended(again, user, name)


def test_a_chat_standing_by_gives_way_to_another_agent_and_is_one_host_to_two_at_once(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    link, _, _, name = _chat(project, "the word is papaya")
    _ended(link, user, name)
    carried = {"workspace": str(project), "task": "", "resume": name}

    # One who brings it up and one who says something, at once, are answered the one host.
    with ThreadPoolExecutor(2) as both:
        asked = [
            both.submit(user.call, "chat.start", one, timeout=60)
            for one in (carried, {**carried, "task": "what was the word?"})
        ]
        woke, said = (one.result() for one in asked)
    assert woke == said
    assert until(lambda: len(started(tmp_path)) == 2)
    assert user.call("chat.start", carried, timeout=60) == woke
    named = {"workspace": str(project), "slot": woke["slot"]}
    assert until(lambda: _row(user, name)["state"] == "going")
    assert user.call("chat.say", {**named, "text": ""}, timeout=30) == {}
    assert until(lambda: _row(user, name)["state"] == "resting")

    # Carried on with another agent while a host stands by with it, that host ends as it
    # was and the chat goes on with the agent named, on a host of its own.
    woke = user.call("chat.start", carried, timeout=60)
    other = "claude/claude-sonnet-4-5"
    went = user.call(
        "chat.start", {**carried, "task": "and now?", "agent": other}, timeout=60
    )
    assert (went["chat"], went["slot"] != woke["slot"]) == (name, True)
    assert until(lambda: _row(user, name)["slot"] == went["slot"])


def _flag(start: dict[str, Any], name: str) -> str:
    """What one start of the stand-in `claude` was given for a flag."""
    argv = start["argv"]
    return str(argv[argv.index(name) + 1]) if name in argv else ""


def test_an_old_chat_is_carried_on_with_another_model_and_effort_across_a_restart(
    legacy: Path, tmp_path: Path
) -> None:
    with hosting():
        daemon.start()
        earlier = int(where.held(where.at())["pid"])
        user = _dialed()
        try:
            link, _, _, name = _chat(legacy, "the word is papaya")
            _ended(link, user, name)
            at = _directory(name)
            (first,) = started(tmp_path)
            before = _row(user, name)
            assert (before["agent"], before["slot"]) == (f"{AGENT}:auto", "")

            # No host holds it: its record says so, and nothing is brought up for it.
            row = user.call(
                "chat.agent", {"chat": name, "agent": "claude/opus:high"}, timeout=30
            )
            assert set(row) == ROW
            assert (row["agent"], row["model"]) == ("claude/opus:high", "opus")
            assert (row["state"], row["slot"]) == ("resting", "")
            assert len(started(tmp_path)) == 1
            said = _events(at)[-1]
            assert said["event"] == "set"
            assert (said["agents"][0]["model"], said["agents"][0]["effort"]) == (
                "opus",
                "high",
            )
            # Under the name its sessions were written down by.
            assert said["agents"][0]["name"] == _events(at)[0]["agents"][0]["name"]

            # Another harness is a new chat's to talk to; what is no agent is refused so.
            wrote = (at / CHATTED).read_bytes()
            code, why = _refused(user, "chat.agent", chat=name, agent="codex/gpt-5")
            assert code == 409
            assert why == (
                "a chat keeps its harness, and this one is had with claude; "
                "start a new chat to talk to codex"
            )
            code, why = _refused(user, "chat.agent", chat=name, agent="nonsense")
            assert code == 400
            assert "nonsense" in why
            assert _refused(user, "chat.agent", chat="nothing", agent=AGENT) == (
                404,
                "There is no chat nothing.",
            )
            assert (at / CHATTED).read_bytes() == wrote
        finally:
            user.close()

    # A daemon started again reads it so, and carries it on at them in its conversation.
    assert until(lambda: not where.alive(earlier))
    daemon.start()
    user = _dialed()
    try:
        got = _row(user, name)
        assert (got["agent"], got["state"]) == ("claude/opus:high", "resting")
        assert got["agents"][0]["runs"] == "claude/opus:high"
        went = user.call(
            "chat.start",
            {"workspace": str(legacy), "task": "what was the word?", "resume": name},
            timeout=60,
        )
        assert went["chat"] == name
        assert until(lambda: len(started(tmp_path)) == 2)
        then = started(tmp_path)[-1]
        assert _flag(then, "--resume") == first["session"]
        assert (_flag(then, "--model"), _flag(then, "--effort")) == ("opus", "high")
        assert until(lambda: _row(user, name)["state"] == "going")
        # The one chat still, in the one record, its sessions both its own.
        assert written_chats() == [at]
        assert len(_row(user, name)["sessions"]) == 2
        assert _row(user, name)["agent"] == "claude/opus:high"
        user.call(
            "chat.say",
            {"workspace": str(legacy), "slot": went["slot"], "text": ""},
            timeout=30,
        )
        assert until(lambda: _row(user, name)["state"] == "resting")
    finally:
        user.close()


def test_a_chat_a_host_holds_is_given_another_model_and_runs_at_it_from_its_next_turn(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    link, heard, slot, name = _chat(project, "hello there")
    try:
        (first,) = started(tmp_path)

        # Mid-turn it is recorded at once and waits for the turn after, as a line would.
        link.chat_say(SLOW)
        assert until(lambda: _row(user, name)["state"] == "turn")
        row = user.call(
            "chat.agent", {"chat": name, "agent": "claude/opus:low"}, timeout=30
        )
        assert (row["agent"], row["slot"], row["state"]) == (
            "claude/opus:low",
            slot,
            "turn",
        )
        link.chat_stop()
        assert until(lambda: _row(user, name)["state"] == "going")
        assert _flag(started(tmp_path)[-1], "--model") == MODEL

        # Its harness keeps it; so does its host, which nothing was started beside.
        code, why = _refused(user, "chat.agent", chat=name, agent="codex/gpt-5")
        assert (code, "start a new chat to talk to codex" in why) == (409, True)
        assert _row(user, name)["slot"] == slot

        link.chat_say("and now?")
        assert until(
            lambda: any(
                one.get("mode") == "listen"
                and str(one.get("text") or "").endswith("did: and now?")
                for one in heard.of("asked")
            )
        )
        then = started(tmp_path)[-1]
        assert (_flag(then, "--model"), _flag(then, "--effort")) == ("opus", "low")
        # Moved by its harness's own `/model` and `/effort`: the conversation it had goes
        # on as it is, never forked into another, and never a new one.
        assert "--fork-session" not in then["argv"]
        assert not any(
            "could not be carried on" in str(one.get("text") or "")
            for one in heard.of("asked")
        )
        assert _row(user, name)["agent"] == "claude/opus:low"
        assert _row(user, name)["slot"] == slot
        assert first["session"]
        assert heard.of("ended") == []
    finally:
        link.close()


def test_a_chat_standing_by_is_given_another_model_and_stays_on_its_host(
    project: Path, user: Peer, tmp_path: Path
) -> None:
    link, _, _, name = _chat(project, "the word is papaya")
    _ended(link, user, name)
    (first,) = started(tmp_path)
    wrote = (_directory(name) / CHATTED).read_bytes()
    carried = {"workspace": str(project), "task": "", "resume": name}
    woke = user.call("chat.start", carried, timeout=60)
    assert until(lambda: _row(user, name)["slot"] == woke["slot"])
    assert (_directory(name) / CHATTED).read_bytes() == wrote

    row = user.call(
        "chat.agent", {"chat": name, "agent": "claude/opus:medium"}, timeout=30
    )

    # Its record says so, and the host that stands by with it is the one it goes on with.
    assert (row["agent"], row["slot"]) == ("claude/opus:medium", woke["slot"])
    assert len(started(tmp_path)) == 1
    went = user.call(
        "chat.start", {**carried, "task": "what was the word?"}, timeout=60
    )
    assert went == woke
    assert until(lambda: len(started(tmp_path)) == 2)
    then = started(tmp_path)[-1]
    assert _flag(then, "--resume") == first["session"]
    assert (_flag(then, "--model"), _flag(then, "--effort")) == ("opus", "medium")
    assert until(lambda: _row(user, name)["state"] == "going")
    user.call(
        "chat.say",
        {"workspace": str(project), "slot": woke["slot"], "text": ""},
        timeout=30,
    )
    assert until(lambda: _row(user, name)["state"] == "resting")
    assert _row(user, name)["agent"] == "claude/opus:medium"


def test_a_chat_carried_on_with_nothing_said_ends_as_it_was_and_is_deleted_between_turns(
    project: Path, user: Peer
) -> None:
    link, _, _, name = _chat(project, "hello")
    _ended(link, user, name)
    at = _directory(name)
    wrote = (at / CHATTED).read_bytes()
    carried = {"workspace": str(project), "task": "", "resume": name}

    # Ended with nothing said, it is as it was.
    woke = user.call("chat.start", carried, timeout=60)
    named = {"workspace": str(project), "slot": woke["slot"]}
    assert user.call("chat.say", {**named, "text": ""}, timeout=30) == {}
    assert until(lambda: _row(user, name)["state"] == "resting")
    assert (at / CHATTED).read_bytes() == wrote

    # Held between turns, it is ended and deleted: only an open turn keeps it.
    woke = user.call("chat.start", carried, timeout=60)
    assert _row(user, name)["slot"] == woke["slot"]
    assert user.call("chat.delete", {"chat": name}, timeout=60) == {}
    assert not at.exists()
    assert _refused(user, "chat.get", chat=name)[0] == 404

    # One whose folder has gone says so, and nothing is started for it.
    import shutil

    gone = project.parent / "vanish"
    gone.mkdir()
    link, _, _, lost = _chat(gone, "hello")
    _ended(link, user, lost)
    shutil.rmtree(gone)
    assert _refused(user, "chat.start", workspace=str(gone), task="", resume=lost) == (
        404,
        f"There is no directory {gone}.",
    )


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


def test_a_chat_is_still_reached_once_its_directory_is_removed(
    project: Path, user: Peer
) -> None:
    # Section 4.5.2 of daemon.md: a host held already is named, not its directory.
    import shutil

    gone = project.parent / "vanish"
    gone.mkdir()
    link, _, slot, _ = _chat(gone, "hello")
    link.close()
    shutil.rmtree(gone)
    named = {"workspace": str(gone), "slot": slot}

    listed = user.call("chat.commands", named, timeout=30)
    assert listed["prefer"] in ("native", "flow")
    assert any(one["source"] == "hmz" for one in listed["entries"])
    assert user.call("chat.set", {**named, "prefer": "flow"}, timeout=30) == {}
    assert user.call("chat.commands", named, timeout=30)["prefer"] == "flow"
    assert user.call("btw.leave", {"workspace": str(gone)}, timeout=30) == {}
    # A frontend follows it as before, and is told the workspace it had.
    attached = user.call("epic.attach", {**named, "replay": False}, timeout=30)
    assert (attached["workspace"], attached["slot"]) == (where.workspace(gone), slot)
    # Between turns there is nothing to stop, which is the host's own answer.
    assert _refused(user, "chat.stop", **named)[0] == 409
    assert user.call("chat.say", {**named, "text": "more"}, timeout=30) == {}
    # One to start a host in must be there.
    assert _refused(user, "epic.attach", workspace=str(gone)) == (
        404,
        f"There is no directory {gone}.",
    )


def test_the_daemon_answers_once_the_directory_it_was_started_in_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    at = install(tmp_path, monkeypatch)
    ghost = tmp_path / "ghost"
    ghost.mkdir()
    monkeypatch.chdir(ghost)
    with hosting():
        daemon.start()
        monkeypatch.chdir(at)
        shutil.rmtree(ghost)
        peer, _ = dialed(where.at())
        try:
            assert "listen" in peer.call("settings.get", {}, timeout=30)
            # A CLI is asked what it runs from a directory that is there.
            asked = peer.call(
                "accounts.models", {"cli": "claude", "name": ""}, timeout=60
            )
            assert "accounts" in asked
            held = peer.call("flows.backends", {}, timeout=60)["clis"]["claude"]
            assert held["accounts"][0]["models"]
        finally:
            peer.close()
