"""`hmz.tui.envs`: what `/env` works out about environments, apart from drawing them."""

from __future__ import annotations

import base64
import contextlib
import os
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.tui.envs import (
    ACK_EVERY,
    Commit,
    Credit,
    Escape,
    Inbox,
    Reach,
    Viewing,
    bridge,
    default_panel,
    grouped,
    language_of,
    panels_of,
    tree,
    unified,
    used,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


def _env(**said: Any) -> dict[str, Any]:
    return {
        "id": "1:a",
        "role": "a",
        "parent": None,
        "caps": [],
        "declared": [],
        **said,
    }


@pytest.mark.parametrize(
    ("caps", "panels"),
    [
        ([], []),
        (["files", "bash"], ["files"]),
        (
            ["files", "shell", "git_worktree", "rewind"],
            ["files", "changes", "shell", "snapshots"],
        ),
        (["git"], ["changes"]),
    ],
)
def test_an_environment_has_a_panel_per_capability_it_really_has(
    caps: list[str], panels: list[str]
) -> None:
    assert panels_of(_env(caps=caps)) == panels


@pytest.mark.parametrize(
    ("declared", "panel"),
    [
        ([], "files"),
        (["git"], "changes"),
        (["shell", "git"], "changes"),
        (["shell"], "shell"),
        (["rewind"], "snapshots"),
        (["bash"], "files"),
    ],
)
def test_it_opens_on_the_first_panel_the_flow_declared(
    declared: list[str], panel: str
) -> None:
    caps = ["files", "shell", "git", "rewind"]
    assert default_panel(_env(caps=caps, declared=declared)) == panel


def test_a_declared_capability_the_driver_lacks_opens_nothing_it_cannot_show() -> None:
    assert default_panel(_env(caps=["files"], declared=["git"])) == "files"


def test_derived_environments_are_listed_under_the_one_they_came_from() -> None:
    envs = [
        _env(id="r", role="coder"),
        _env(id="t", role="tester"),
        _env(id="r>x", role="coder", parent="r"),
        _env(id="r>x>y", role="coder", parent="r>x"),
        _env(id="r2", role="coder"),
        _env(id="lost", role="tester", parent="gone"),
    ]

    laid = [(depth, one["id"]) for depth, one in tree(envs)]

    assert laid == [
        (0, "r"),
        (1, "r>x"),
        (2, "r>x>y"),
        (0, "r2"),
        (0, "t"),
        (0, "lost"),
    ]


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("/w/a.py", "python"),
        ("src/App.JSX", "javascript"),
        ("Cargo.toml", "toml"),
        ("~/.bashrc", "bash"),
        ("notes.txt", None),
        ("Makefile", None),
    ],
)
def test_a_file_is_coloured_by_its_name(path: str, language: str | None) -> None:
    assert language_of(path) == language


def test_a_language_the_editor_has_not_got_is_none() -> None:
    assert language_of("a.py", ["json"]) is None
    assert language_of("a.py", ["python"]) == "python"


def test_a_change_is_a_unified_diff() -> None:
    said = unified(b"a\nb\n", b"a\nc", "f.txt")

    assert said.splitlines() == [
        "--- a/f.txt",
        "+++ b/f.txt",
        "@@ -1,2 +1,2 @@",
        " a",
        "-b",
        "+c",
    ]


def test_a_file_made_or_taken_away_is_diffed_against_nothing() -> None:
    assert unified(None, b"x\n", "f").startswith("--- /dev/null\n+++ b/f\n")
    assert unified(b"x\n", None, "f").startswith("--- a/f\n+++ /dev/null\n")
    assert unified(b"same\n", b"same\n", "f") == ""


def test_changes_are_grouped_as_a_source_control_view_groups_them() -> None:
    files = [
        {"path": "both", "index": "M", "worktree": "M", "state": "changed"},
        {"path": "staged", "index": "A", "worktree": ".", "state": "changed"},
        {"path": "edited", "index": ".", "worktree": "D", "state": "changed"},
        {"path": "new", "index": "?", "worktree": "?", "state": "untracked"},
        {"path": "fight", "index": "U", "worktree": "U", "state": "conflict"},
    ]

    groups = [(name, [one["path"] for one in held]) for name, held in grouped(files)]

    assert groups == [
        ("Merge Changes", ["fight"]),
        ("Staged Changes", ["both", "staged"]),
        ("Changes", ["both", "edited"]),
        ("Untracked", ["new"]),
    ]


def test_no_changes_is_no_groups() -> None:
    assert grouped([]) == []


def test_a_hand_in_an_environment_is_said_by_who_what_and_where() -> None:
    envs = [_env(id="1:a", chain="a>b")]
    record = {
        "type": "env_used",
        "env": "1:a",
        "by": "web",
        "what": "removed",
        "path": "x",
    }

    assert used(record, envs) == "web removed x in a>b"
    assert used({"env": "9:z", "by": "tui", "what": "opened a terminal"}) == (
        "tui opened a terminal in 9:z"
    )


def test_a_tilde_and_a_dot_first_on_a_line_leave() -> None:
    keys = Escape()

    assert keys.typed(b"ls\r") == (b"ls\r", False)
    assert keys.typed(b"~") == (b"", False)
    assert keys.typed(b".rest") == (b"", True)


def test_the_very_first_key_is_first_on_a_line() -> None:
    assert Escape().typed(b"~.") == (b"", True)


def test_a_tilde_anywhere_else_is_a_tilde() -> None:
    keys = Escape()

    assert keys.typed(b"cd ~.") == (b"cd ~.", False)
    assert keys.typed(b"\n~~.") == (b"\n~.", False)
    assert keys.typed(b"\r~x") == (b"\r~x", False)


def test_output_is_acknowledged_every_so_often() -> None:
    credit = Credit(every=10)

    assert credit.took(4) == 0
    assert credit.took(5) == 0
    assert credit.took(3) == 12
    assert credit.took(1) == 0
    assert Credit().took(ACK_EVERY) == ACK_EVERY


@pytest.fixture
def piped() -> Iterator[tuple[int, int, int, int]]:
    """A keyboard and a screen: stdin's two ends, then stdout's."""
    keyboard, typing = os.pipe()
    showing, screen = os.pipe()
    yield keyboard, typing, showing, screen
    for one in (keyboard, typing, showing, screen):
        with contextlib.suppress(OSError):
            os.close(one)


def _all(fd: int) -> bytes:
    got = b""
    while chunk := os.read(fd, 1 << 20):
        got += chunk
    return got


def _out(fd: int) -> bytes:
    os.set_blocking(fd, False)
    got = b""
    try:
        while chunk := os.read(fd, 1 << 20):
            got += chunk
    except BlockingIOError:
        pass
    return got


def test_a_bridge_writes_the_terminal_out_and_sends_what_is_typed_until_left(
    piped: tuple[int, int, int, int],
) -> None:
    keyboard, typing, showing, screen = piped
    asked: list[tuple[str, Mapping[str, Any]]] = []
    inbox = Inbox("t1")
    inbox.put({"type": "term", "term": "t1", "data": base64.b64encode(b"$ ").decode()})
    os.write(typing, b"ls\r~.")

    ended = bridge(
        lambda method, params: asked.append((method, params)),
        inbox,
        stdin=keyboard,
        stdout=screen,
        replay=b"before\n",
    )
    inbox.close()

    assert ended == "left; it keeps running"
    assert _out(showing) == b"before\n$ "
    assert asked == [
        ("env.term.input", {"term": "t1", "data": base64.b64encode(b"ls\r").decode()}),
        # What was written and not yet acknowledged, on the way out.
        ("env.term.ack", {"term": "t1", "bytes": 2}),
    ]


def test_a_bridge_acknowledges_what_it_wrote_and_ends_with_the_terminal(
    piped: tuple[int, int, int, int],
) -> None:
    keyboard, _, showing, screen = piped
    asked: list[tuple[str, Mapping[str, Any]]] = []
    inbox = Inbox("t1")
    chunk = base64.b64encode(b"x" * 1024).decode()
    for _ in range(ACK_EVERY // 1024 + 1):
        inbox.put({"type": "term", "term": "t1", "data": chunk})
    inbox.put({"type": "term_exit", "term": "t1", "status": 3})
    shown: list[bytes] = []
    # Read as it is written, as a terminal would: more than a pipe holds is written.
    reading = threading.Thread(target=lambda: shown.append(_all(showing)))
    reading.start()

    ended = bridge(
        lambda method, params: asked.append((method, params)),
        inbox,
        stdin=keyboard,
        stdout=screen,
    )
    os.close(screen)
    reading.join()
    inbox.close()

    assert ended == "exited with status 3"
    assert asked == [
        ("env.term.ack", {"term": "t1", "bytes": ACK_EVERY}),
        ("env.term.ack", {"term": "t1", "bytes": 1024}),
    ]
    assert len(shown[0]) == ACK_EVERY + 1024


def test_a_bridge_writes_out_only_its_own_terminal(
    piped: tuple[int, int, int, int],
) -> None:
    keyboard, _, showing, screen = piped
    inbox = Inbox("t1")
    for term, said in (("t0", b"theirs"), ("t1", b"mine")):
        inbox.put(
            {"type": "term", "term": term, "data": base64.b64encode(said).decode()}
        )
    inbox.put({"type": "term_exit", "term": "t0", "status": 1})
    inbox.put({"type": "term_exit", "term": "t1", "status": 0})

    ended = bridge(lambda method, params: None, inbox, stdin=keyboard, stdout=screen)
    inbox.close()

    assert ended == "exited with status 0"
    assert _out(showing) == b"mine"


def test_a_bridge_says_how_the_host_failed_it(piped: tuple[int, int, int, int]) -> None:
    keyboard, typing, _, screen = piped
    inbox = Inbox("t1")
    os.write(typing, b"x")

    def refuses(method: str, params: Mapping[str, Any]) -> None:
        raise ValueError("There is no terminal t1.")

    assert bridge(refuses, inbox, stdin=keyboard, stdout=screen) == (
        "ended: There is no terminal t1."
    )
    inbox.close()


def test_a_terminal_s_messages_go_to_the_bridge_and_nothing_else_does() -> None:
    reach = Reach(lambda said: {"ok": True}, list)
    inbox = Inbox("t1")
    reach.bridging(inbox)

    assert reach.told({"type": "term", "term": "t1", "data": ""})
    assert reach.told({"type": "term_exit", "term": "t1", "status": 0})
    assert not reach.told({"type": "event"})
    assert [one["type"] for one in inbox.taken()] == ["term", "term_exit"]
    inbox.close()


def test_a_terminal_being_opened_takes_whatever_a_terminal_says() -> None:
    reach = Reach(lambda said: {"ok": True}, list)
    inbox = Inbox("")
    reach.bridging(inbox)

    assert reach.told({"type": "term", "term": "new", "data": ""})
    assert [one["term"] for one in inbox.taken()] == ["new"]
    inbox.close()


def test_a_terminal_nobody_reads_is_still_acknowledged() -> None:
    acked: list[dict[str, Any]] = []
    reach = Reach(lambda said: acked.append(said) or {"ok": True}, list)
    data = base64.b64encode(b"y" * ACK_EVERY).decode()

    assert reach.told({"type": "term", "term": "t9", "data": data})

    deadline = time.monotonic() + 5
    while not acked and time.monotonic() < deadline:
        time.sleep(0.01)
    assert acked == [{"do": "env.term.ack", "term": "t9", "bytes": ACK_EVERY}]


def test_a_reach_asks_the_host_and_tells_whoever_watches() -> None:
    asked: list[dict[str, Any]] = []
    reach = Reach(lambda said: asked.append(said) or {"ok": True}, lambda: [_env()])
    seen: list[int] = []
    stops = reach.watching(lambda: seen.append(1))

    reach.ask("env.list", {"env": "1:a", "path": ""})
    reach.moved()
    stops()
    reach.moved()

    assert asked == [{"do": "env.list", "env": "1:a", "path": ""}]
    assert seen == [1]
    assert reach.envs() == [_env()]


@pytest.mark.parametrize("amend", ["off", "on"])
async def test_a_commit_is_not_answered_without_a_message(amend: str) -> None:
    from textual.app import App
    from textual.widgets import Label

    form = Commit()
    answers: list[tuple[str, bool] | None] = []

    class _Host(App[None]):
        def on_mount(self) -> None:
            self.push_screen(form, answers.append)

    async with _Host().run_test() as pilot:
        await pilot.pause()
        form.dropped("amend", amend)
        form.action_done()
        await pilot.pause()
        said = "" if answers else str(form.query_one("#tuning", Label).content)

    assert answers == []
    assert "message is required" in said


def _reach(envs: list[dict[str, Any]], of: list[str]) -> Reach:
    return Reach(lambda _said: {}, lambda: envs, of=lambda: of[0])


def test_a_pane_shows_the_first_open_environment_that_has_its_page() -> None:
    envs = [
        _env(id="1:a", caps=["files"]),
        _env(id="1:b", role="b", caps=["files", "git"], open=False),
        _env(id="1:c", role="c", caps=["files", "git", "shell"]),
    ]
    reach = _reach(envs, [""])

    assert [one.id for one in reach.desks("files")] == ["1:a", "1:c"]
    assert [one.id for one in reach.desks("changes")] == ["1:c"]
    assert [one.id for one in (reach.desk("files"),) if one] == ["1:a"]
    assert reach.desk("snapshots") is None


def test_the_environment_turned_to_is_remembered_for_each_chat() -> None:
    envs = [_env(id="1:a", caps=["files"]), _env(id="1:c", role="c", caps=["files"])]
    of = ["chat-1"]
    reach = _reach(envs, of)

    reach.turns("1:c")
    assert [one.id for one in (reach.desk("files"),) if one] == ["1:c"]

    of[0] = "chat-2"
    assert [one.id for one in (reach.desk("files"),) if one] == ["1:a"]
    of[0] = "chat-1"
    assert [one.id for one in (reach.desk("files"),) if one] == ["1:c"]

    # One that has closed since is not shown: the first is.
    envs.pop()
    assert [one.id for one in (reach.desk("files"),) if one] == ["1:a"]


def test_a_terminal_drawn_in_a_pane_is_handed_its_messages_and_no_other_s() -> None:
    asked: list[dict[str, Any]] = []
    done = threading.Event()

    def ask(said: dict[str, Any]) -> dict[str, Any]:
        asked.append(said)
        done.set()
        return {}

    reach = Reach(ask, list)
    heard: list[tuple[dict[str, Any], bool]] = []
    viewing = Viewing(lambda message, acked: heard.append((message, acked)), "t1")
    stops = reach.views(viewing)
    data = base64.b64encode(b"x" * ACK_EVERY).decode()

    assert reach.told({"type": "term", "term": "t1", "data": data})
    assert reach.told({"type": "term", "term": "t2", "data": data})
    assert reach.told({"type": "term_exit", "term": "t1", "status": 0})

    # Its own, not yet acknowledged; the other's is nobody's, and acknowledged here.
    assert [(one["type"], one["term"], acked) for one, acked in heard] == [
        ("term", "t1", False),
        ("term_exit", "t1", False),
    ]
    assert done.wait(5)
    assert asked == [{"do": "env.term.ack", "term": "t2", "bytes": ACK_EVERY}]

    stops()
    assert reach.told({"type": "term", "term": "t1", "data": ""})
    assert len(heard) == 2


def test_a_terminal_still_opening_is_handed_every_terminal_s_as_acknowledged() -> None:
    reach = Reach(lambda _said: {}, list)
    heard: list[tuple[str, bool]] = []
    reach.views(Viewing(lambda message, acked: heard.append((message["term"], acked))))

    assert reach.told({"type": "term", "term": "t9", "data": ""})

    assert heard == [("t9", True)]
