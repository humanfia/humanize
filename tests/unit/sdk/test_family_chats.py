"""`hmz.sdk.families.chats`: `chat.*` as typed calls, and a turn heard out, a client mocked."""

from __future__ import annotations

from typing import Any, cast
from unittest import mock

import pytest

from hmz.sdk import Refused
from hmz.sdk.families.chats import (
    Catalogue,
    Chats,
    Entry,
    Harness,
    HarnessSession,
    Held,
    Started,
    Turn,
)

ROW: dict[str, Any] = {
    "id": "c1",
    "title": "the parser",
    "workspace": "/w",
    "folderless": False,
    "workdir": "/w",
    "env": "local/w",
    "agent": "claude/m:high",
    "model": "m",
    "began": "2026-01-01T00:00:00Z",
    "updated": "2026-01-01T00:00:01Z",
    "state": "resting",
    "slot": "",
    "asking": [],
    "permission": "workspace-write",
    "archived": False,
    "spent": {"tokens": "7"},
}

SESSION: dict[str, Any] = {
    "id": "s9",
    "harness": "claude",
    "title": "hello",
    "workspace": "/w",
    "model": "m",
    "began": "2026-01-01T00:00:00Z",
    "updated": "2026-01-01T00:00:01Z",
    "continuable": True,
}


class Daemon:
    """A client whose calls are answered out of a table, and which can be told things."""

    def __init__(self, **answers: Any) -> None:
        self.answers = {name.replace("_", "."): said for name, said in answers.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.gone = False
        self._listener: Any = None

    def call(
        self, method: str, params: dict[str, Any], *, idem: Any = None, seconds: Any = 0
    ) -> Any:
        del seconds
        self.calls.append((method, {**params, **({"idem": idem} if idem else {})}))
        said: Any = self.answers.get(method, {})
        if isinstance(said, list):
            said = cast("list[Any]", said).pop(0)
        if isinstance(said, Exception):
            raise said
        return said

    def heard(self, listener: Any) -> None:
        self._listener = listener

    def wait(self, timeout: float | None = None) -> bool:
        del timeout
        return self.gone

    def tells(self, sub: str, *messages: dict[str, Any]) -> None:
        for message in messages:
            self._listener("epic.event", {"sub": sub, "message": message})

    def made(self, method: str) -> list[dict[str, Any]]:
        return [params for name, params in self.calls if name == method]


def _chats(daemon: Daemon) -> Chats:
    return Chats(daemon)  # pyright: ignore[reportArgumentType]


def test_the_family_names_every_method_of_chat() -> None:
    assert set(Chats.METHODS) == {
        "chat.start", "chat.say", "chat.commands", "chat.set", "chat.move", "chat.stop",
        "chat.list", "chat.get", "chat.rename", "chat.agent", "chat.fork", "chat.archive",
        "chat.unarchive", "chat.backup", "chat.delete",
    }  # fmt: skip
    # The sessions a harness ran on its own are `client.chats.harness`'s to name.
    assert Harness.METHODS == (
        "chat.harness.list",
        "chat.harness.get",
        "chat.harness.adopt",
    )


def test_a_chat_is_started_with_what_was_said_of_it_and_nothing_else() -> None:
    daemon = Daemon(chat_start={"chat": "c1", "slot": "chat:ab"})

    started = _chats(daemon).start(
        "/w", "hello", agent="claude/m", worktree=True, permission="read-only", idem="k"
    )

    assert started == Started("c1", "/w", "chat:ab")
    assert daemon.calls == [
        (
            "chat.start",
            {
                "workspace": "/w",
                "slot": "chat:",
                "agent": "claude/m",
                "task": "hello",
                "permission": "read-only",
                "worktree": True,
                "idem": "k",
            },
        )
    ]


def test_a_chat_of_no_folder_starts_on_a_host_made_for_it_alone() -> None:
    daemon = Daemon(
        epic_attach={"sub": "s1", "workspace": "/made", "slot": "chat:cd"},
        chat_start={"chat": "c2", "slot": "chat:cd"},
    )

    started = _chats(daemon).start(None, "hello", agent="claude/m")

    assert started == Started("c2", "/made", "chat:cd")
    assert [name for name, _ in daemon.calls] == [
        "epic.attach",
        "chat.start",
        "epic.detach",
    ]
    assert daemon.made("epic.attach") == [
        {"slot": "chat:", "scratch": True, "replay": False}
    ]
    assert daemon.made("chat.start")[0]["workspace"] == "/made"
    assert daemon.made("epic.detach") == [{"sub": "s1"}]


def test_the_chats_are_listed_a_page_at_a_time() -> None:
    daemon = Daemon(chat_list={"chats": [ROW], "total": 3, "offset": 1, "limit": 1})

    listed = _chats(daemon).list(workspace="/w", archived=True, q="pars", offset=1)

    assert (listed.total, listed.offset, listed.limit) == (3, 1, 1)
    (chat,) = listed.chats
    assert (chat.id, chat.title, chat.state, chat.asking) == (
        "c1",
        "the parser",
        "resting",
        (),
    )
    assert chat.said == ROW
    assert daemon.calls == [
        ("chat.list", {"workspace": "/w", "archived": True, "q": "pars", "offset": 1})
    ]


@pytest.mark.parametrize(
    ("does", "given", "method", "params"),
    [
        ("get", {"trace": True}, "chat.get", {"chat": "c1", "trace": True}),
        ("archive", {}, "chat.archive", {"chat": "c1"}),
        ("unarchive", {"idem": "k"}, "chat.unarchive", {"chat": "c1", "idem": "k"}),
    ],
)
def test_what_is_done_to_a_chat_by_its_name_answers_the_chat(
    does: str, given: dict[str, Any], method: str, params: dict[str, Any]
) -> None:
    daemon = Daemon(**{method.replace(".", "_"): ROW})

    assert getattr(_chats(daemon), does)("c1", **given).id == "c1"
    assert daemon.calls == [(method, params)]


def test_a_chat_is_renamed_given_an_agent_forked_backed_up_and_deleted() -> None:
    daemon = Daemon(
        chat_rename={**ROW, "title": "new"},
        chat_agent={**ROW, "agent": "claude/m:low"},
        chat_fork={"chat": "c2"},
        chat_backup={"queued": ["lab"]},
    )
    chats = _chats(daemon)

    assert chats.rename("c1", "new").title == "new"
    assert chats.agent("c1", "claude/m:low").agent == "claude/m:low"
    assert chats.fork("c1") == "c2"
    assert chats.backup("c1", to=("lab",)) == ["lab"]
    chats.delete("c1")

    assert daemon.calls == [
        ("chat.rename", {"chat": "c1", "title": "new"}),
        ("chat.agent", {"chat": "c1", "agent": "claude/m:low"}),
        ("chat.fork", {"chat": "c1"}),
        ("chat.backup", {"chat": "c1", "to": ["lab"]}),
        ("chat.delete", {"chat": "c1"}),
    ]


def test_what_is_done_to_a_chat_where_it_is_held_names_its_workspace_and_slot() -> None:
    daemon = Daemon(
        chat_move={"env": "ssh@box/srv"},
        chat_commands={
            "entries": [
                {"sigil": "/", "name": "clear", "about": "", "how": "", "source": "hmz"}
            ],
            "prefer": "flow",
            "prefer_from": "chat",
            "permission": None,
            "listed": False,
        },
    )
    chats = _chats(daemon)
    at = {"workspace": "/w", "slot": "chat:ab"}

    chats.say("/w", "chat:ab", "next", idem="k")
    chats.stop("/w", "chat:ab")
    chats.set("/w", "chat:ab", permission="read-only")
    assert chats.move("/w", "chat:ab", "ssh@box/srv") == "ssh@box/srv"
    assert chats.commands("/w", "chat:ab") == Catalogue(
        (Entry("/", "clear", "", "", "hmz"),), "flow", "chat", None, listed=False
    )

    assert daemon.calls == [
        ("chat.say", {**at, "text": "next", "idem": "k"}),
        ("chat.stop", at),
        ("chat.set", {**at, "permission": "read-only"}),
        ("chat.move", {**at, "env": "ssh@box/srv"}),
        ("chat.commands", at),
    ]


def test_a_chat_a_host_holds_is_held_where_it_is() -> None:
    daemon = Daemon(chat_get={**ROW, "slot": "chat:ab"})

    assert _chats(daemon).hold("c1") == Held("/w", "chat:ab")
    assert [name for name, _ in daemon.calls] == ["chat.get"]


def test_a_chat_no_host_holds_is_carried_on_with_nothing_said_to_be_held() -> None:
    daemon = Daemon(chat_get=ROW, chat_start={"chat": "c1", "slot": "chat:ef"})

    assert _chats(daemon).hold("c1") == Held("/w", "chat:ef")
    assert daemon.made("chat.start") == [
        {"workspace": "/w", "slot": "chat:", "task": "", "resume": "c1"}
    ]


def test_the_agent_a_workspace_remembers_is_read_from_its_settings() -> None:
    daemon = Daemon(settings_get=[{"chat": "claude/m"}, {"chat": ""}])
    chats = _chats(daemon)

    assert chats.remembered("/w") == "claude/m"
    assert chats.remembered("/w") == ""
    assert daemon.calls[0] == ("settings.get", {"workspace": "/w"})


def test_harness_sessions_are_listed_read_and_adopted() -> None:
    daemon = Daemon(
        chat_harness_list={"sessions": [SESSION], "total": 1, "offset": 0, "limit": 50},
        chat_harness_get={**SESSION, "trace": [{"actions": []}]},
        chat_harness_adopt={"chat": "c3"},
    )
    harness = _chats(daemon).harness

    listed = harness.list("/w", limit=50)
    assert listed.sessions == (
        HarnessSession(
            "s9", "claude", "hello", "/w", "m", SESSION["began"], SESSION["updated"],
            continuable=True,
        ),
    )  # fmt: skip
    assert harness.get("/w", "claude", "s9", trace=True).trace == [{"actions": []}]
    assert harness.adopt("/w", "claude", "s9", agent="claude/m") == "c3"

    named = {"workspace": "/w", "harness": "claude", "session": "s9"}
    assert daemon.calls == [
        ("chat.harness.list", {"workspace": "/w", "limit": 50}),
        ("chat.harness.get", {**named, "trace": True}),
        ("chat.harness.adopt", {**named, "agent": "claude/m"}),
    ]


def _event(kind: str, text: str, seq: int) -> dict[str, Any]:
    return {"type": "event", "seq": seq, "kind": kind, "text": text}


def test_a_turn_is_heard_until_the_chat_is_between_turns_again() -> None:
    daemon = Daemon(epic_attach={"sub": "s1"})

    with _chats(daemon).follow("/w", "chat:ab") as turn:
        daemon.tells(
            "s1",
            {"type": "welcome", "epoch": "e1"},
            # Before any turn was seen going: a chat whose turn has not opened yet.
            {"type": "run", "turn": "done"},
            {"type": "run", "turn": "running"},
            _event("result", " the answer ", 4),
            {"type": "asked", "seq": 5, "mode": "listen", "text": "the answer"},
            {"type": "run", "turn": "done"},
            _event("result", "never heard", 6),
        )
        heard = [message["type"] for message in turn]

    assert heard == ["welcome", "run", "run", "event", "asked", "run"]
    assert (turn.done, turn.answer, turn.failed, turn.notes, turn.ended) == (
        True,
        "the answer",
        "",
        [],
        None,
    )
    assert daemon.made("epic.attach") == [{"workspace": "/w", "slot": "chat:ab"}]
    assert daemon.made("epic.detach") == [{"sub": "s1"}]


def test_a_line_served_by_no_turn_is_done_once_the_chat_asks_for_the_next() -> None:
    daemon = Daemon(epic_attach={"sub": "s1"})
    turn = _chats(daemon).follow("/w", "chat:ab", replay=False)
    daemon.tells(
        "s1",
        {"type": "run", "turn": "done"},
        {"type": "shell", "seq": 2, "command": "echo hi", "out": "hi\n"},
        {"type": "asked", "seq": 3, "mode": "listen", "text": "$x names no skill"},
    )

    assert turn.wait() is None
    assert (turn.done, turn.notes) == (True, ["$x names no skill"])
    assert daemon.made("epic.attach") == [
        {"workspace": "/w", "slot": "chat:ab", "replay": False}
    ]


def test_a_turn_that_failed_says_what_the_harness_said() -> None:
    daemon = Daemon(epic_attach={"sub": "s1"})
    turn = _chats(daemon).follow("/w", "chat:ab")
    daemon.tells(
        "s1",
        {"type": "run", "turn": "running"},
        _event("failed", "it broke", 2),
        {"type": "ended", "seq": 3, "how": "failed", "why": "Boom: it broke"},
    )

    assert turn.wait() is None
    assert (turn.done, turn.failed, turn.ended) == (
        False,
        "it broke",
        ("failed", "Boom: it broke"),
    )


def test_a_frontend_that_fell_behind_attaches_again_from_where_it_got_to() -> None:
    daemon = Daemon(epic_attach=[{"sub": "s1"}, {"sub": "s2"}])
    turn = _chats(daemon).follow("/w", "chat:ab")
    daemon.tells(
        "s1",
        {"type": "welcome", "epoch": "e1"},
        {"type": "run", "turn": "running", "seq": 7},
        {"type": "gone", "why": "too far behind; attach again"},
    )
    daemon.tells("s2", _event("result", "late", 9), {"type": "run", "turn": "done"})

    assert turn.wait() == "late"
    assert daemon.made("epic.attach")[1] == {
        "workspace": "/w",
        "slot": "chat:ab",
        "since": {"epoch": "e1", "seq": 7},
    }


def test_a_host_that_went_ends_the_turn_and_a_session_that_ended_is_an_error() -> None:
    daemon = Daemon(epic_attach=[{"sub": "s1"}, {"sub": "s2"}])
    turn = _chats(daemon).follow("/w", "chat:ab")
    daemon.tells("s1", {"type": "gone", "why": "the host went away"})

    assert turn.wait() is None
    assert turn.ended == ("gone", "the host went away")

    left = _chats(daemon).follow("/w", "chat:ab")
    daemon.gone = True
    with pytest.raises(ConnectionError):
        left.wait()


def test_asking_holds_the_chat_follows_its_host_and_then_says_the_line() -> None:
    daemon = Daemon(
        chat_get=ROW,
        chat_start={"chat": "c1", "slot": "chat:ef"},
        epic_attach={"sub": "s1"},
    )

    turn = _chats(daemon).ask("c1", "and then?", idem="k")

    assert (turn.workspace, turn.slot) == ("/w", "chat:ef")
    assert [name for name, _ in daemon.calls] == [
        "chat.get",
        "chat.start",
        "epic.attach",
        "chat.say",
    ]
    assert daemon.made("epic.attach")[0]["replay"] is False
    assert daemon.made("chat.say") == [
        {"workspace": "/w", "slot": "chat:ef", "text": "and then?", "idem": "k"}
    ]


def test_a_turn_open_before_the_line_was_said_is_not_heard_as_its_answer() -> None:
    daemon = Daemon(chat_get={**ROW, "slot": "chat:ab"}, epic_attach={"sub": "s1"})
    turn = _chats(daemon).ask("c1", "and then? ")
    daemon.tells(
        "s1",
        {"type": "run", "turn": "running"},
        _event("result", "the turn before", 4),
        {"type": "asked", "seq": 5, "mode": "listen", "text": "the turn before"},
        {"type": "run", "turn": "done"},
        {"type": "said", "seq": 6, "text": "and then?"},
        {"type": "run", "turn": "running"},
        _event("result", "this turn", 8),
        {"type": "run", "turn": "done"},
    )

    assert turn.wait() == "this turn"
    assert turn.notes == []


def test_a_line_given_to_a_turn_that_is_open_is_answered_by_that_turn() -> None:
    daemon = Daemon(chat_get={**ROW, "slot": "chat:ab"}, epic_attach={"sub": "s1"})
    turn = _chats(daemon).ask("c1", "and then?")
    daemon.tells(
        "s1",
        {"type": "run", "turn": "running"},
        {"type": "waiting", "queued": [{"text": "and then?"}], "given": []},
        {"type": "run", "turn": "done"},
        {"type": "waiting", "queued": [], "given": [{"text": "and then?"}]},
        _event("result", "both", 6),
        {"type": "run", "turn": "done"},
    )

    assert turn.wait() == "both"


def test_a_chat_is_put_to_rest_by_an_empty_line_and_waited_on() -> None:
    held = {**ROW, "slot": "chat:ab"}
    daemon = Daemon(chat_get=[held, held, ROW])

    assert _chats(daemon).rest("c1") is True
    assert daemon.made("chat.say") == [
        {"workspace": "/w", "slot": "chat:ab", "text": ""}
    ]

    resting = Daemon(chat_get=ROW)
    assert _chats(resting).rest("c1") is True
    assert resting.made("chat.say") == []


def test_asking_a_chat_that_folded_meanwhile_holds_it_again_once() -> None:
    folded = Refused("this chat has folded away", code=409)
    daemon = Daemon(
        chat_get={**ROW, "slot": "chat:ab"},
        epic_attach={"sub": "s1"},
        chat_say=[folded, {}],
    )

    _chats(daemon).ask("c1", "and then?")

    assert [name for name, _ in daemon.calls] == [
        "chat.get", "epic.attach", "chat.say", "epic.detach",
        "chat.get", "epic.attach", "chat.say",
    ]  # fmt: skip


def test_a_line_the_daemon_refuses_is_refused_and_the_host_let_go() -> None:
    daemon = Daemon(
        chat_get={**ROW, "slot": "chat:ab"},
        epic_attach={"sub": "s1"},
        chat_say=Refused("/clear is served by the frontend", code=400),
    )

    with pytest.raises(Refused, match="served by the frontend"):
        _chats(daemon).ask("c1", "/clear")

    assert daemon.made("epic.detach") == [{"sub": "s1"}]


def test_a_turn_is_a_family_of_no_method_of_its_own() -> None:
    assert Turn.METHODS == ()
    assert mock.sentinel  # the client is never a real one here
