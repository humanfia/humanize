"""`client.envs`: a host's environments as typed calls, through a client that is mocked."""

from __future__ import annotations

import base64
import threading
from typing import Any
from unittest import mock

import pytest

from hmz.sdk import Refused
from hmz.sdk.families.envs import (
    ACK_EVERY,
    Attached,
    Change,
    Commit,
    Diff,
    Entry,
    Env,
    Envs,
    Found,
    Grepped,
    Line,
    Match,
    Ran,
    Read,
    Role,
    Searched,
    Shell,
    Status,
    Text,
    Wrote,
)

ENV = {
    "id": "1:coder",
    "role": "coder",
    "chain": "coder",
    "parent": None,
    "run": 1,
    "backend": "local",
    "provider": "local",
    "workdir": "/w",
    "available": True,
    "open": True,
    "caps": ["files", "shell", "git"],
    "declared": ["git"],
    "facts": {"cpu": 8},
}
FORK = {**ENV, "id": "1:coder>fork", "chain": "coder>fork", "parent": "1:coder"}
SHUT = {**ENV, "id": "1:tester", "role": "tester", "chain": "tester", "open": False}


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class Daemon:
    """A daemon as far as the family asks one: what each method answers, and what it says."""

    def __init__(self, envs: list[dict[str, Any]] | None = None) -> None:
        self.client = mock.Mock(spec=["call", "heard"])
        self.client.call.side_effect = self._call
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.answers: dict[str, Any] = {}
        self.envs = [ENV, FORK, SHUT] if envs is None else envs
        self.keys: list[str | None] = []

    def _call(
        self,
        method: str,
        params: dict[str, Any],
        *,
        idem: str | None = None,
        seconds: float | None = None,
    ) -> Any:
        self.asked.append((method, params))
        self.keys.append(idem)
        if method == "epic.attach":
            self.says({"type": "welcome"})
            self.says({"type": "envs", "envs": self.envs})
            self.says({"type": "live", "seq": 0})
            return {"sub": "s1", "client": "c1", "workspace": "/w", "slot": ""}
        answer = self.answers.get(method, {})
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, list):
            return answer.pop(0)  # pyright: ignore[reportUnknownVariableType]
        return answer

    def says(self, message: dict[str, Any], sub: str = "s1") -> None:
        """What the host tells the frontend, as the client's listener hears it."""
        (listener,), _ = self.client.heard.call_args
        listener("epic.event", {"sub": sub, "message": message})

    def of(self, method: str) -> list[dict[str, Any]]:
        """What each call of one method was given."""
        return [params for name, params in self.asked if name == method]

    def attached(self, **given: Any) -> Attached:
        return Envs(self.client).attached("/w", **given)


@pytest.fixture
def daemon() -> Daemon:
    return Daemon()


def test_the_family_names_the_methods_of_an_environment_each_once() -> None:
    assert len(set(Envs.METHODS)) == len(Envs.METHODS) == 29
    assert all(one.startswith(("env.", "hosts.env.")) for one in Envs.METHODS)
    assert {"hosts.env.exec", "env.write", "env.term.ack", "env.git.rewind"} <= set(
        Envs.METHODS
    )


def test_the_envs_of_an_epic_are_reached_by_role_without_attaching(
    daemon: Daemon,
) -> None:
    envs = Envs(daemon.client)
    daemon.answers = {
        "hosts.env.list": {
            "envs": [
                {"name": "code", "kind": "local", "workdir": "/w", "can": ["read"]}
            ]
        },
        "hosts.env.read": {"text": "hi", "size": 9, "eof": False},
        "hosts.env.write": {"size": 2},
        "hosts.env.exec": {"code": None, "stdout": "out", "stderr": "err"},
        "hosts.env.grep": {
            "matches": [{"path": "a.py", "line": 3, "text": "x = 1"}],
            "more": True,
        },
    }

    assert envs.list("/w") == [Role("code", "local", "/w", ("read",))]
    assert envs.read("/w", "code", "a.txt", offset=7) == Text("hi", 9, eof=False)
    assert envs.write("/w", "code", "a.txt", "hi", slot="exec:1f", idem="k") == 2
    assert envs.exec("/w", "code", ["make", "test"], seconds=5) == Ran(
        None, "out", "err"
    )
    assert envs.grep("/w", "code", "x", path="src", limit=1) == Grepped(
        (Line("a.py", 3, "x = 1"),), more=True
    )

    assert daemon.asked == [
        ("hosts.env.list", {"workspace": "/w"}),
        (
            "hosts.env.read",
            {"workspace": "/w", "env": "code", "path": "a.txt", "offset": 7},
        ),
        (
            "hosts.env.write",
            {
                "workspace": "/w",
                "slot": "exec:1f",
                "env": "code",
                "path": "a.txt",
                "text": "hi",
            },
        ),
        (
            "hosts.env.exec",
            {"workspace": "/w", "env": "code", "argv": ["make", "test"], "seconds": 5},
        ),
        (
            "hosts.env.grep",
            {
                "workspace": "/w",
                "env": "code",
                "pattern": "x",
                "path": "src",
                "limit": 1,
            },
        ),
    ]
    assert daemon.keys[2] == "k"
    daemon.client.heard.assert_not_called()


def test_attaching_asks_only_a_host_that_is_held_and_hears_how_it_stands(
    daemon: Daemon,
) -> None:
    with daemon.attached(slot="chat:1f") as host:
        assert (host.sub, host.workspace, host.slot) == ("s1", "/w", "")
        assert [one.id for one in host.envs()] == [
            "1:coder",
            "1:coder>fork",
            "1:tester",
        ]
        assert host.envs()[0] == Env(
            id="1:coder",
            role="coder",
            chain="coder",
            parent=None,
            run=1,
            backend="local",
            provider="local",
            workdir="/w",
            available=True,
            open=True,
            caps=("files", "shell", "git"),
            declared=("git",),
            facts={"cpu": 8},
        )

    assert daemon.asked == [
        ("hosts.status", {"workspace": "/w", "slot": "chat:1f"}),
        ("epic.attach", {"workspace": "/w", "slot": "chat:1f", "replay": False}),
        ("epic.detach", {"sub": "s1"}),
    ]


def test_a_host_that_is_not_held_is_not_started_unless_asked_to_be(
    daemon: Daemon,
) -> None:
    daemon.answers["hosts.status"] = Refused("no runs are held in /w", code=404)

    with pytest.raises(Refused, match="no runs are held in /w"):
        daemon.attached()
    assert daemon.of("epic.attach") == []

    daemon.attached(start=True).close()
    assert daemon.of("epic.attach") == [{"workspace": "/w", "replay": False}]


def test_a_chat_names_the_host_it_is_going_on(daemon: Daemon) -> None:
    daemon.answers["chat.get"] = [
        {"id": "c", "workspace": "/there", "slot": "chat:2a"},
        {"id": "c", "workspace": "/there", "slot": ""},
    ]

    Envs(daemon.client).attached(chat="c").close()
    assert daemon.of("epic.attach") == [
        {"workspace": "/there", "slot": "chat:2a", "replay": False}
    ]
    assert daemon.of("hosts.status") == []

    with pytest.raises(Refused, match=r"This chat has folded away\."):
        Envs(daemon.client).attached(chat="c")

    daemon.answers["chat.get"] = {"id": "c", "workspace": "/there", "slot": "chat:2a"}
    assert Envs(daemon.client).host("c") == ("/there", "chat:2a")


def test_a_host_that_lets_go_before_it_is_live_is_a_refusal() -> None:
    daemon = Daemon()

    def call(method: str, params: dict[str, Any], **_: Any) -> Any:
        if method == "epic.attach":
            daemon.says({"type": "gone", "why": "the host was closed"})
            return {"sub": "s1", "client": "c1", "workspace": "/w", "slot": ""}
        return {}

    daemon.client.call.side_effect = call

    with pytest.raises(Refused, match="the host was closed") as refused:
        daemon.attached()
    assert refused.value.code == 409


def test_a_host_that_says_nothing_in_time_is_a_timeout() -> None:
    daemon = Daemon()
    daemon.client.call.side_effect = lambda *_, **__: {"sub": "s1"}  # pyright: ignore[reportUnknownLambdaType]

    with pytest.raises(TimeoutError):
        daemon.attached(wait=0.01)


def test_an_environment_is_found_by_id_chain_or_role_and_follows_the_host(
    daemon: Daemon,
) -> None:
    with daemon.attached() as host:
        assert host.env().id == "1:coder"
        assert host.env("1:coder>fork").env.parent == "1:coder"
        assert host.env("coder>fork").id == "1:coder>fork"
        assert host.env("tester").id == "1:tester"
        with pytest.raises(Refused, match=r"There is no environment nope\.") as none:
            host.env("nope")
        assert none.value.code == 404

        daemon.says({"type": "envs", "envs": [SHUT]})
        daemon.says({"type": "live"})  # what comes after the envs has been taken
        assert _until(lambda: [one.id for one in host.envs()] == ["1:tester"])
        # None is open, so the first is the one there is.
        assert host.env().id == "1:tester"

        daemon.says({"type": "envs", "envs": []})
        assert _until(lambda: host.envs() == [])
        with pytest.raises(Refused, match=r"No environment is open here yet\."):
            host.env()


def _until(what: Any) -> bool:
    done = threading.Event()
    for _ in range(200):
        if what():
            return True
        done.wait(0.01)
    return bool(what())


def test_files_are_listed_read_searched_and_changed(daemon: Daemon) -> None:
    entry = {"name": "a.py", "kind": "file", "size": 3, "mtime": 1.5}
    daemon.answers = {
        "env.list": {"path": "/w", "entries": [entry]},
        "env.stat": {**entry, "path": "/w/a.py", "kind": "link", "target": "b.py"},
        "env.read": {
            "data": _b64(b"x=1"),
            "size": 3,
            "mtime": 1.5,
            "etag": "e1",
            "eof": True,
        },
        "env.find": {"paths": ["a.py"], "truncated": True},
        "env.search": {
            "matches": [{"path": "a.py", "line": 1, "column": 2, "text": "x=1"}],
            "truncated": False,
        },
        "env.write": {"etag": "e2", "size": 4, "mtime": 2.5},
    }
    with daemon.attached() as host:
        files = host.env().files

        assert files.list() == [Entry("a.py", "file", 3, 1.5)]
        assert files.stat("a.py") == Entry("a.py", "link", 3, 1.5, "/w/a.py", "b.py")
        assert files.read("a.py", offset=1, length=2) == Read(
            b"x=1", 3, 1.5, "e1", eof=True
        )
        assert files.find(limit=1) == Found(("a.py",), truncated=True)
        assert files.search("x", regex=True, glob="*.py") == Searched(
            (Match("a.py", 1, 2, "x=1"),), truncated=False
        )
        assert files.write("a.py", "x=2\n", if_match="e1", idem="k") == Wrote(
            "e2", 4, 2.5
        )
        files.write("new", b"\xff", if_match="")
        files.write("any", b"")
        files.mkdir("d/e")
        files.rename("a.py", "b.py")
        files.remove("d")

    at = {"sub": "s1", "env": "1:coder"}
    assert daemon.asked[2:-1] == [
        ("env.list", {**at, "path": "."}),
        ("env.stat", {**at, "path": "a.py"}),
        ("env.read", {**at, "path": "a.py", "offset": 1, "length": 2}),
        ("env.find", {**at, "limit": 1}),
        ("env.search", {**at, "query": "x", "regex": True, "glob": "*.py"}),
        (
            "env.write",
            {**at, "path": "a.py", "data": _b64(b"x=2\n"), "if_match": "e1"},
        ),
        ("env.write", {**at, "path": "new", "data": _b64(b"\xff"), "if_match": ""}),
        ("env.write", {**at, "path": "any", "data": ""}),
        ("env.mkdir", {**at, "path": "d/e"}),
        ("env.rename", {**at, "path": "a.py", "to": "b.py"}),
        ("env.remove", {**at, "path": "d"}),
    ]
    assert daemon.keys[7] == "k"


def _piece(data: bytes, etag: str, *, eof: bool) -> dict[str, Any]:
    return {"data": _b64(data), "size": 5, "mtime": 1.0, "etag": etag, "eof": eof}


def test_a_file_is_read_whole_a_piece_at_a_time(daemon: Daemon) -> None:
    daemon.answers["env.read"] = [
        _piece(b"ab", "e1", eof=False),
        _piece(b"cd", "e1", eof=False),
        _piece(b"e", "e1", eof=True),
    ]
    with daemon.attached() as host:
        assert host.env().files.read("big") == Read(b"abcde", 5, 1.0, "e1", eof=True)

    assert [one["offset"] for one in daemon.of("env.read")] == [0, 2, 4]


def test_a_file_that_changes_while_it_is_read_is_read_again(daemon: Daemon) -> None:
    daemon.answers["env.read"] = [
        _piece(b"ab", "e1", eof=False),
        _piece(b"XY", "e2", eof=True),
        _piece(b"abXY", "e2", eof=True),
    ]
    with daemon.attached() as host:
        assert host.env().files.read("big").data == b"abXY"

    daemon.answers["env.read"] = [_piece(b"a", f"e{at}", eof=False) for at in range(6)]
    with (
        daemon.attached() as host,
        pytest.raises(Refused, match="big kept changing while it was read"),
    ):
        host.env().files.read("big")


def test_git_is_read_and_worked(daemon: Daemon) -> None:
    daemon.answers = {
        "env.git.status": {
            "root": "/w",
            "branch": "main",
            "head": "abc",
            "upstream": None,
            "ahead": 1,
            "behind": 0,
            "files": [
                {"path": "a", "index": "M", "worktree": ".", "state": "changed"},
                {
                    "path": "b",
                    "orig": "c",
                    "index": "R",
                    "worktree": ".",
                    "state": "changed",
                },
            ],
        },
        "env.git.diff": {"old": None, "new": _b64(b"new\n"), "binary": False},
        "env.git.log": {
            "commits": [
                {
                    "hash": "abc",
                    "parents": ["def"],
                    "author": "Ada",
                    "date": "2026-01-01T00:00:00Z",
                    "subject": "first",
                }
            ]
        },
        "env.git.commit": {"head": "fff"},
        "env.git.snapshots": {"snapshots": ["refs/hmz/snapshots/a"]},
    }
    with daemon.attached() as host:
        git = host.env("tester").git

        assert git.status() == Status(
            root="/w",
            branch="main",
            head="abc",
            upstream=None,
            ahead=1,
            behind=0,
            files=(
                Change("a", "M", ".", "changed"),
                Change("b", "R", ".", "changed", "c"),
            ),
        )
        assert git.diff("a", staged=True) == Diff(None, b"new\n", binary=False)
        assert git.log(limit=1) == [
            Commit("abc", ("def",), "Ada", "2026-01-01T00:00:00Z", "first")
        ]
        git.stage(("a", "b"))
        git.unstage(["a"])
        git.discard(["b"], idem="k")
        assert git.commit("say it", amend=True) == "fff"
        assert git.snapshots() == ["refs/hmz/snapshots/a"]
        git.rewind("refs/hmz/snapshots/a")

    at = {"sub": "s1", "env": "1:tester"}
    assert daemon.asked[2:-1] == [
        ("env.git.status", at),
        ("env.git.diff", {**at, "path": "a", "staged": True}),
        ("env.git.log", {**at, "limit": 1}),
        ("env.git.stage", {**at, "paths": ["a", "b"]}),
        ("env.git.unstage", {**at, "paths": ["a"]}),
        ("env.git.discard", {**at, "paths": ["b"]}),
        ("env.git.commit", {**at, "message": "say it", "amend": True}),
        ("env.git.snapshots", at),
        ("env.git.rewind", {**at, "ref": "refs/hmz/snapshots/a"}),
    ]


def test_a_terminal_is_typed_into_read_and_acknowledged(daemon: Daemon) -> None:
    daemon.answers["env.term.open"] = {"term": "t1", "shell": None, "replay": ""}
    daemon.answers["env.term.list"] = {
        "terms": [
            {
                "term": "t1",
                "env": "1:coder",
                "title": "shell",
                "cols": 120,
                "rows": 40,
                "alive": True,
            }
        ]
    }
    with daemon.attached() as host:
        terminals = host.env().terminals
        # A shell's prompt may be told before the answer saying which terminal it is.
        daemon.says({"type": "term", "term": "t1", "data": _b64(b"$ ")})
        daemon.says({"type": "term", "term": "t9", "data": _b64(b"another's")})
        terminal = terminals.open(cols=120, rows=40)

        assert (terminal.id, terminal.shell, terminal.replay) == ("t1", None, b"")
        assert terminal.read(5) == b"$ "
        assert terminal.read(0.01) is None
        terminal.write("ls\n")
        terminal.write(b"\x03")
        terminal.resize(80, 24)
        assert terminals.list() == [
            Shell("t1", "1:coder", "shell", 120, 40, alive=True)
        ]

        big = b"x" * (ACK_EVERY - 2)
        daemon.says({"type": "term", "term": "t1", "data": _b64(big)})
        daemon.says({"type": "term", "term": "t1", "data": _b64(b"tail")})
        daemon.says({"type": "term_exit", "term": "t1", "status": 130})
        assert list(terminal) == [big, b"tail"]
        assert terminal.status == 130
        assert terminal.read() is None

    at = {"sub": "s1", "term": "t1"}
    assert daemon.asked[2:-1] == [
        ("env.term.open", {"sub": "s1", "env": "1:coder", "cols": 120, "rows": 40}),
        ("env.term.input", {**at, "data": _b64(b"ls\n")}),
        ("env.term.input", {**at, "data": _b64(b"\x03")}),
        ("env.term.resize", {**at, "cols": 80, "rows": 24}),
        ("env.term.list", {"sub": "s1", "env": "1:coder"}),
        ("env.term.ack", {**at, "bytes": ACK_EVERY}),
    ]


def test_a_terminal_is_come_back_to_left_running_and_closed(daemon: Daemon) -> None:
    daemon.answers["env.term.open"] = {
        "term": "t2",
        "shell": ["bash", "-l"],
        "replay": _b64(b"before"),
    }
    with daemon.attached() as host:
        terminals = host.env().terminals
        terminal = terminals.open(term="t2")
        assert (terminal.shell, terminal.replay) == (("bash", "-l"), b"before")

        daemon.says({"type": "term", "term": "t2", "data": _b64(b"abc")})
        assert terminal.read(5) == b"abc"
        threading.Timer(0.05, terminal.leave).start()
        assert list(terminal) == []
        assert terminal.status is None

        with terminals.open(term="t2") as again:
            assert again.id == "t2"
        terminals.close("t7")

    at = {"sub": "s1", "term": "t2"}
    opened = (
        "env.term.open",
        {"sub": "s1", "env": "1:coder", "cols": 80, "rows": 24, "term": "t2"},
    )
    assert daemon.asked[2:-1] == [
        opened,
        # What was read and never acknowledged is, on leaving.
        ("env.term.ack", {**at, "bytes": 3}),
        opened,
        # Leaving the block with the terminal still running kills it.
        ("env.term.close", at),
        ("env.term.close", {"sub": "s1", "term": "t7"}),
    ]


def test_everything_waiting_ends_once_the_host_lets_go(daemon: Daemon) -> None:
    daemon.answers["env.term.open"] = {"term": "t1", "shell": None, "replay": ""}
    host = daemon.attached()
    terminal = host.env().terminals.open()

    daemon.says({"type": "gone", "why": "let go"})

    assert list(terminal) == []
    assert _until(lambda: host.gone == "let go")
    assert host.live(0) is False
    host.close()


def test_a_host_that_lists_nothing_yet_is_waited_on_for_its_first_environment() -> None:
    daemon = Daemon(envs=[])
    with daemon.attached() as host:
        assert host.envs() == []
        assert host.envs(wait=0.01) == []

        threading.Timer(0.05, daemon.says, [{"type": "envs", "envs": [ENV]}]).start()
        assert [one.id for one in host.envs(wait=5)] == ["1:coder"]


def test_a_terminal_left_running_is_acknowledged_for_and_not_killed(
    daemon: Daemon,
) -> None:
    daemon.answers["env.term.open"] = {"term": "t1", "shell": None, "replay": ""}
    with daemon.attached() as host:
        terminals = host.env().terminals
        with terminals.open() as terminal:
            terminal.leave()
        # Still viewed at the host, so what it prints is said to have been read: it would
        # be held up otherwise.
        daemon.says({"type": "term", "term": "t1", "data": _b64(b"x" * ACK_EVERY)})
        assert _until(lambda: daemon.of("env.term.ack"))
        assert terminal.read(0.01) is None

        # Come back to, it starts from its replay: nothing from before is read twice.
        again = terminals.open(term="t1")
        daemon.says({"type": "term", "term": "t1", "data": _b64(b"new")})
        assert again.read(5) == b"new"
        daemon.says({"type": "term_exit", "term": "t1", "status": 0})
        assert again.read(5) is None
        assert again.status == 0

    assert daemon.of("env.term.ack") == [
        {"sub": "s1", "term": "t1", "bytes": ACK_EVERY}
    ]
    assert daemon.of("env.term.close") == []


def test_an_acknowledgement_a_terminal_refuses_loses_nothing(daemon: Daemon) -> None:
    daemon.answers["env.term.open"] = {"term": "t1", "shell": None, "replay": ""}
    daemon.answers["env.term.ack"] = Refused("There is no terminal t1.", code=409)
    with daemon.attached() as host:
        terminal = host.env().terminals.open()
        big = b"x" * ACK_EVERY
        daemon.says({"type": "term", "term": "t1", "data": _b64(big)})
        daemon.says({"type": "term_exit", "term": "t1", "status": 143})

        assert list(terminal) == [big]
        assert terminal.status == 143
