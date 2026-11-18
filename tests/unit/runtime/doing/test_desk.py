"""What a frontend does in the environments a run holds: files, terminals and git."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import posixpath
import threading
import time
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import (
    BashEnvMixin,
    FilesEnvMixin,
    GitEnvMixin,
    ShellEnvMixin,
    TemporaryClonedDirEnvMixin,
)
from hmz.runtime import Host
from hmz.runtime.doing import desk, gitdesk
from tests.unit.runtime.doing.test_hosting import (
    PATIENCE,
    Agent,
    Event,
    FakeRun,
    Session,
    Told,
    Workspace,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from pathlib import Path

    from tests.unit.runtime.doing.test_hosting import Outworlders

#: Every capability a machine has, as a driver lists them: `RewindableEnvMixin` is not
#: among them, being served by the `GitEnvMixin` implementing it.
EVERYTHING = frozenset(
    {
        FilesEnvMixin,
        ShellEnvMixin,
        BashEnvMixin,
        GitEnvMixin,
        TemporaryClonedDirEnvMixin,
    }
)

#: What an env's id is, for the run's root and the copy derived from it.
ROOT = "1:local@/work"
COPY = "1:local@/work#temp_clone(t)"


# ------------------------------------------------------------------ doubles


def _answers(
    out: str, code: int = 0, err: str = ""
) -> Callable[[list[str]], tuple[int, str, str]]:
    """What every command run answers."""

    def answers(argv: list[str]) -> tuple[int, str, str]:
        del argv
        return code, out, err

    return answers


@dataclass(frozen=True)
class Stat:
    name: str
    kind: str
    size: int
    mtime: float
    target: str | None = None


class FakePty:
    """A shell on a terminal: echoes what is typed, prints what a test has it print."""

    def __init__(self, cols: int, rows: int) -> None:
        self.size = (cols, rows)
        self.out: asyncio.Queue[bytes] = asyncio.Queue()
        self.typed: list[bytes] = []
        self.reads = 0
        self.killed = False
        self.status = 0
        self.loop: asyncio.AbstractEventLoop | None = None

    def prints(self, data: bytes) -> None:
        assert self.loop is not None
        self.loop.call_soon_threadsafe(self.out.put_nowait, data)

    async def read(self) -> bytes:
        self.reads += 1
        return await self.out.get()

    async def write(self, data: bytes) -> None:
        self.typed.append(data)
        self.out.put_nowait(data)

    async def resize(self, cols: int, rows: int) -> None:
        self.size = (cols, rows)

    async def wait(self) -> int:
        return self.status

    async def kill(self) -> None:
        self.killed = True
        self.status = 137
        self.out.put_nowait(b"")


class Plain:
    """A driver with no files to browse and no terminal: reading, writing and exec alone."""

    backend = "local"
    provider = ""
    available = True
    cpu_count = 4
    memory = 8 << 30
    gpu_count = 0
    gpu_memory = 0

    def __init__(
        self,
        workdir: str = "/work",
        capabilities: frozenset[type] = EVERYTHING,
        files: dict[str, bytes] | None = None,
        answers: Callable[[list[str]], tuple[int, str, str]] | None = None,
    ) -> None:
        self.workdir = PurePosixPath(workdir)
        self.capabilities = capabilities
        self.files = dict(files or {})
        self.mtimes = dict.fromkeys(self.files, 1.0)
        self.dirs: set[str] = set()
        self.reads = 0
        self.ran: list[list[str]] = []
        self.answers = answers or _answers("/bin/zsh")

    def at(self, path: str) -> str:
        return posixpath.normpath(posixpath.join(str(self.workdir), path))

    async def read(self, path: str) -> bytes:
        self.reads += 1
        try:
            return self.files[self.at(path)]
        except KeyError:
            raise FileNotFoundError(path) from None

    async def write(self, path: str, data: bytes) -> None:
        at = self.at(path)
        self.files[at] = data
        self.mtimes[at] = self.mtimes.get(at, 1.0) + 1

    async def exec(
        self,
        argv: Sequence[str] | str,
        *,
        timeout: float,  # noqa: ASYNC109 -- the driver's
    ) -> tuple[int, str, str]:
        del timeout
        self.ran.append(list(argv))
        return self.answers(list(argv))


class Box(Plain):
    """A driver with every panel's methods: files, a terminal and snapshots."""

    def __init__(self, *args: Any, **said: Any) -> None:
        super().__init__(*args, **said)
        self.ptys: list[FakePty] = []
        self.started: list[list[str] | None] = []
        self.refs = ["refs/hmz/snapshots/a"]
        self.rewound: list[str] = []

    def _kind(self, at: str) -> str | None:
        if at in self.files:
            return "file"
        if at in self.dirs or any(one.startswith(f"{at}/") for one in self.files):
            return "dir"
        return None

    async def list(self, path: str) -> list[Stat]:
        at = self.at(path)
        if self._kind(at) != "dir":
            raise FileNotFoundError(path)
        names = {
            one[len(at) + 1 :].split("/")[0]
            for one in (*self.files, *self.dirs)
            if one.startswith(f"{at}/")
        }
        return [await self.stat(posixpath.join(at, name)) for name in names]

    async def stat(self, path: str) -> Stat:
        at = self.at(path)
        kind = self._kind(at)
        if kind is None:
            raise FileNotFoundError(path)
        data = self.files.get(at, b"")
        return Stat(posixpath.basename(at), kind, len(data), self.mtimes.get(at, 1.0))

    async def mkdir(self, path: str) -> None:
        self.dirs.add(self.at(path))

    async def rename(self, path: str, to: str) -> None:
        at = self.at(path)
        if at not in self.files:
            raise FileNotFoundError(path)
        self.files[self.at(to)] = self.files.pop(at)

    async def remove(self, path: str) -> None:
        at = self.at(path)
        if self._kind(at) is None:
            raise FileNotFoundError(path)
        for one in [one for one in self.files if one == at or one.startswith(f"{at}/")]:
            del self.files[one]

    async def pty(self, argv: Sequence[str] | None, *, cols: int, rows: int) -> FakePty:
        made = FakePty(cols, rows)
        made.loop = asyncio.get_running_loop()
        self.started.append(None if argv is None else list(argv))
        self.ptys.append(made)
        return made

    async def snapshots(self) -> list[str]:
        return list(self.refs)

    async def rewind(self, ref: str) -> None:
        self.rewound.append(ref)


@dataclass(frozen=True)
class Held:
    role: str
    chain: str
    parent: str | None
    driver: Any
    declared: frozenset[type] = frozenset()


@dataclass
class Holding:
    """A run's engine, as far as its environments go."""

    loop: asyncio.AbstractEventLoop
    envs: list[Held] = field(default_factory=list[Held])

    def held_envs(self) -> tuple[Held, ...]:
        return tuple(self.envs)


@pytest.fixture
def loop() -> Iterator[asyncio.AbstractEventLoop]:
    """The run's loop, on a thread of its own as a run's is."""
    made = asyncio.new_event_loop()
    thread = threading.Thread(target=made.run_forever, daemon=True)
    thread.start()
    try:
        yield made
    finally:

        async def ends() -> None:
            mine = asyncio.current_task()
            going = [one for one in asyncio.all_tasks() if one is not mine]
            for one in going:
                one.cancel()
            await asyncio.gather(*going, return_exceptions=True)

        asyncio.run_coroutine_threadsafe(ends(), made).result(PATIENCE)
        made.call_soon_threadsafe(made.stop)
        thread.join(PATIENCE)
        made.close()


@pytest.fixture
def box() -> Box:
    return Box(
        files={
            "/work/a.txt": b"hello\n",
            "/work/src/main.py": b"print(1)\n",
            "/work/z.bin": bytes(range(256)),
        }
    )


@pytest.fixture
def holding(loop: asyncio.AbstractEventLoop, box: Box) -> Holding:
    return Holding(
        loop, [Held("repo", "local@/work", None, box, frozenset({GitEnvMixin}))]
    )


@pytest.fixture
def host(
    tmp_path: Path, outworlders: Outworlders, holding: Holding
) -> Iterator[tuple[Host, Workspace]]:
    del outworlders
    where = Workspace(tmp_path)
    where.next_run = FakeRun(envs=holding)
    made = Host(cast("Any", where))
    try:
        yield made, where
    finally:
        made.close()
        for one in where.runs:
            one.released.set()


@pytest.fixture
def outworlders(monkeypatch: pytest.MonkeyPatch) -> Any:
    from hmz.runtime import flowing
    from tests.unit.runtime.doing.test_hosting import Outworlders

    made = Outworlders()
    monkeypatch.setattr(flowing, "open_outworlder", made, raising=False)
    return made


def _going(host: tuple[Host, Workspace], name: str = "alice") -> tuple[Told, FakeRun]:
    made, where = host
    told = Told(made, name)
    assert told.asks("start", flow="ralph", task="fix it")["ok"]
    run = where.runs[-1]
    assert run.going.wait(PATIENCE)
    told.waits(lambda one: one["type"] == "envs" and bool(one["envs"]))
    return told, run


def _ok(said: dict[str, Any]) -> dict[str, Any]:
    assert said.get("ok") is True, said
    return said


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _envs(told: Told, what: Callable[[list[dict[str, Any]]], bool]) -> list[Any]:
    """The environments as last said, once they are as `what` wants them."""

    def latest() -> list[Any]:
        said = [one["envs"] for one in told.snapshot() if one["type"] == "envs"]
        return said[-1] if said else []

    _until(lambda: what(latest()))
    return latest()


def _until(what: Callable[[], bool]) -> None:
    deadline = time.monotonic() + PATIENCE
    while not what():
        assert time.monotonic() < deadline, "it never happened"
        time.sleep(0.01)


# ------------------------------------------------------------------ the catalog


def test_the_envs_a_run_holds_are_listed_as_they_come_and_go(
    host: tuple[Host, Workspace], holding: Holding, box: Box
) -> None:
    alice = Told(host[0], "alice")
    kinds = [one["type"] for one in alice.snapshot() if one["type"] != "live"]
    assert kinds.index("envs") == kinds.index("board") + 1
    assert alice.told("envs")["envs"] == []
    alice, run = _going(host, "bob")

    (env,) = _envs(alice, bool)
    assert env == {
        "id": ROOT,
        "role": "repo",
        "chain": "local@/work",
        "parent": None,
        "run": 1,
        "backend": "local",
        "provider": "",
        "workdir": "/work",
        "available": True,
        "open": True,
        "caps": ["files", "shell", "bash", "git", "rewind", "temp_clone"],
        "declared": ["git", "rewind"],
        "facts": {"cpu": 4, "memory": 8 << 30, "gpu_count": 0, "gpu_memory": 0},
    }

    copy = Box(workdir="/tmp/t")
    holding.envs.append(Held("repo", "local@/work#temp_clone(t)", "local@/work", copy))
    derived = _envs(alice, lambda envs: len(envs) == 2)[1]
    assert (derived["id"], derived["parent"]) == (COPY, ROOT)

    # Destroyed under the run: no longer listed, and nothing more is done in it.
    del holding.envs[1]
    _envs(alice, lambda envs: len(envs) == 1)
    assert alice.asks("env.list", env=COPY, path="") == {
        "ok": False,
        "why": f"There is no environment {COPY}.",
    }

    run.released.set()
    (closed,) = _envs(alice, lambda envs: bool(envs) and not envs[0]["open"])
    assert (closed["id"], closed["available"]) == (ROOT, False)
    assert alice.asks("env.list", env=ROOT, path="") == {
        "ok": False,
        "why": "That environment has closed.",
    }
    del box


def test_an_env_nobody_listed_is_refused(host: tuple[Host, Workspace]) -> None:
    alice, _ = _going(host)

    assert alice.asks("env.read", env="9:nowhere", path="a") == {
        "ok": False,
        "why": "There is no environment 9:nowhere.",
    }


# ------------------------------------------------------------------ files


def test_a_directory_is_listed_dirs_first_and_a_file_stated(
    host: tuple[Host, Workspace],
) -> None:
    alice, _ = _going(host)

    listed = _ok(alice.asks("env.list", env=ROOT, path=""))
    assert listed["path"] == "/work"
    assert [(one["name"], one["kind"]) for one in listed["entries"]] == [
        ("src", "dir"),
        ("a.txt", "file"),
        ("z.bin", "file"),
    ]
    stated = _ok(alice.asks("env.stat", env=ROOT, path="src/main.py"))
    assert (stated["path"], stated["name"], stated["kind"], stated["size"]) == (
        "/work/src/main.py",
        "main.py",
        "file",
        9,
    )
    assert alice.asks("env.stat", env=ROOT, path="nope") == {
        "ok": False,
        "why": "No such file: nope",
    }


class Homely(Box):
    """A driver whose workdir is under a home that only its machine knows."""

    def at(self, path: str) -> str:
        at = posixpath.join(str(self.workdir), path)
        return posixpath.normpath(f"/home/me{at[1:]}" if at.startswith("~") else at)

    async def absolute(self, path: str) -> str:
        return self.at(path)


def test_a_path_under_a_home_is_answered_as_an_absolute_one(
    host: tuple[Host, Workspace], holding: Holding
) -> None:
    homely = Homely("~/proj", files={"/home/me/proj/src/a.py": b"x = 1\n"})
    holding.envs[0] = Held("repo", "ssh@box/~/proj", None, homely)
    alice, _ = _going(host)
    (env,) = _envs(alice, bool)
    assert env["workdir"] == "~/proj"

    listed = _ok(alice.asks("env.list", env=env["id"], path=env["workdir"]))
    assert listed["path"] == "/home/me/proj"
    assert [one["name"] for one in listed["entries"]] == ["src"]
    stated = _ok(alice.asks("env.stat", env=env["id"], path="src/a.py"))
    assert stated["path"] == "/home/me/proj/src/a.py"
    above = _ok(alice.asks("env.stat", env=env["id"], path="~/../me/proj/src"))
    assert above["path"] == "/home/me/proj/src"
    assert _ok(alice.asks("env.list", env=env["id"], path="../.."))["path"] == "/home"
    under = posixpath.join(listed["path"], "src")
    assert _ok(alice.asks("env.list", env=env["id"], path=under))["path"] == under


def test_a_file_is_read_in_chunks_reading_it_once(
    host: tuple[Host, Workspace], box: Box
) -> None:
    alice, _ = _going(host)
    whole = bytes(range(256))

    first = _ok(alice.asks("env.read", env=ROOT, path="z.bin", length=100))
    rest = _ok(alice.asks("env.read", env=ROOT, path="z.bin", offset=100))

    assert base64.b64decode(first["data"]) + base64.b64decode(rest["data"]) == whole
    assert (first["eof"], rest["eof"]) == (False, True)
    assert first["etag"] == rest["etag"] == hashlib.sha256(whole).hexdigest()
    assert first["size"] == 256
    assert box.reads == 1


def test_a_write_goes_only_where_the_file_is_as_it_was_read(
    host: tuple[Host, Workspace], box: Box
) -> None:
    alice, _ = _going(host)
    etag = _ok(alice.asks("env.read", env=ROOT, path="a.txt"))["etag"]

    wrote = _ok(
        alice.asks("env.write", env=ROOT, path="a.txt", data=_b64(b"hi"), if_match=etag)
    )
    assert wrote["etag"] == hashlib.sha256(b"hi").hexdigest()
    assert wrote["size"] == 2
    assert box.files["/work/a.txt"] == b"hi"
    # The etag read before is stale now.
    assert alice.asks(
        "env.write", env=ROOT, path="a.txt", data=_b64(b"x"), if_match=etag
    ) == {"ok": False, "why": "a.txt changed since you read it."}
    # "" makes a file only where there is none.
    assert not alice.asks(
        "env.write", env=ROOT, path="a.txt", data=_b64(b"x"), if_match=""
    )["ok"]
    _ok(alice.asks("env.write", env=ROOT, path="new.txt", data=_b64(b"n"), if_match=""))
    # None writes whatever is there.
    _ok(alice.asks("env.write", env=ROOT, path="a.txt", data=_b64(b"y"), if_match=None))
    assert box.files["/work/a.txt"] == b"y"
    used = alice.told("env_used", what="wrote", path="new.txt")
    assert (used["run"], used["env"], used["by"]) == (1, ROOT, "alice")
    # And what is read after is the file as it is now, not as it was kept.
    assert base64.b64decode(
        _ok(alice.asks("env.read", env=ROOT, path="a.txt"))["data"]
    ) == (b"y")


def test_files_are_made_renamed_and_removed_and_each_is_written_down(
    host: tuple[Host, Workspace], box: Box
) -> None:
    alice, _ = _going(host)

    _ok(alice.asks("env.mkdir", env=ROOT, path="docs/deep"))
    _ok(alice.asks("env.rename", env=ROOT, path="a.txt", to="b.txt"))
    _ok(alice.asks("env.remove", env=ROOT, path="src"))

    assert "/work/docs/deep" in box.dirs
    assert set(box.files) == {"/work/b.txt", "/work/z.bin"}
    for what, path in (("made", "docs/deep"), ("renamed", "a.txt"), ("removed", "src")):
        alice.told("env_used", what=what, path=path)
    assert alice.asks("env.remove", env=ROOT, path="gone") == {
        "ok": False,
        "why": "No such file: gone",
    }


@pytest.mark.parametrize(
    ("capabilities", "plain", "why"),
    [
        (EVERYTHING - {FilesEnvMixin}, False, "repo: this environment has no files."),
        (EVERYTHING, True, "repo: this environment has no files."),
    ],
)
def test_an_env_without_files_is_refused_them(
    host: tuple[Host, Workspace],
    holding: Holding,
    capabilities: frozenset[type],
    plain: bool,
    why: str,
) -> None:
    holding.envs[0] = Held(
        "repo",
        "local@/work",
        None,
        (Plain if plain else Box)(capabilities=capabilities),
    )
    alice, _ = _going(host)

    assert alice.asks("env.list", env=ROOT, path="") == {"ok": False, "why": why}


def test_quick_open_lists_what_find_printed(
    host: tuple[Host, Workspace], box: Box
) -> None:
    box.answers = _answers("a.txt\0src/main.py\0./c\0a.txt\0")
    alice, _ = _going(host)

    found = _ok(alice.asks("env.find", env=ROOT))
    assert found == {
        "ok": True,
        "paths": ["a.txt", "src/main.py", "c"],
        "truncated": False,
    }
    assert _ok(alice.asks("env.find", env=ROOT, limit=2))["truncated"] is True
    assert box.ran[-1][:2] == ["/bin/sh", "-c"]


def test_quick_open_walks_an_env_with_no_shell(
    host: tuple[Host, Workspace], holding: Holding
) -> None:
    holding.envs[0] = Held(
        "repo",
        "local@/work",
        None,
        Box(
            capabilities=frozenset({FilesEnvMixin}),
            files={"/work/a": b"", "/work/d/b": b"", "/work/.git/x": b""},
        ),
    )
    alice, _ = _going(host)

    assert sorted(_ok(alice.asks("env.find", env=ROOT))["paths"]) == ["a", "d/b"]


def test_a_search_reads_what_rg_said(host: tuple[Host, Workspace], box: Box) -> None:
    lines = [
        {"type": "begin", "data": {"path": {"text": "./src/main.py"}}},
        {
            "type": "match",
            "data": {
                "path": {"text": "./src/main.py"},
                "lines": {"text": "é print(1)\n"},
                "line_number": 3,
                "submatches": [{"start": 3, "end": 8}],
            },
        },
        {
            "type": "match",
            "data": {
                "path": {"bytes": _b64(b"odd\xff")},
                "lines": {"bytes": _b64(b"print\xff\n")},
                "line_number": 1,
                "submatches": [{"start": 0, "end": 5}],
            },
        },
    ]
    box.answers = _answers("rg\n" + "\n".join(json.dumps(one) for one in lines))
    alice, _ = _going(host)

    said = _ok(alice.asks("env.search", env=ROOT, query="print", glob="*.py"))
    assert said["matches"][0] == {
        "path": "src/main.py",
        "line": 3,
        "column": 3,
        "text": "é print(1)",
    }
    assert said["matches"][1]["path"] == "odd�"
    assert said["truncated"] is False
    assert box.ran[-1][4:8] == ["print", "F", "i", "*.py"]
    assert _ok(alice.asks("env.search", env=ROOT, query="print", limit=1))["truncated"]


def test_a_search_reads_what_grep_said(host: tuple[Host, Workspace], box: Box) -> None:
    box.answers = _answers("grep\n./a.txt:2:say Hello\nnoise\n")
    alice, _ = _going(host)

    said = _ok(alice.asks("env.search", env=ROOT, query="hel+o", regex=True))
    assert said["matches"] == [
        {"path": "a.txt", "line": 2, "column": 5, "text": "say Hello"}
    ]
    assert box.ran[-1][5:7] == ["E", "i"]


# ------------------------------------------------------------------ terminals


def _term(said: list[dict[str, Any]], term: str) -> bytes:
    return b"".join(
        base64.b64decode(one["data"])
        for one in said
        if one["type"] == "term" and one["term"] == term
    )


def test_a_terminal_is_shown_to_whoever_opened_it_and_whoever_reattaches(
    host: tuple[Host, Workspace], box: Box
) -> None:
    alice, _ = _going(host)
    bob = Told(host[0], "bob")

    opened = _ok(alice.asks("env.term.open", env=ROOT, cols=100, rows=30))
    term = opened["term"]
    assert (opened["shell"], opened["replay"]) == (None, "")
    assert box.started == [None]
    assert box.ptys[0].size == (100, 30)
    alice.told("env_used", what="opened a terminal", env=ROOT)

    _ok(alice.asks("env.term.input", term=term, data=_b64(b"ls\r")))
    _until(lambda: _term(alice.snapshot(), term) == b"ls\r")
    assert _term(bob.snapshot(), term) == b""

    again = _ok(bob.asks("env.term.open", env=ROOT, cols=80, rows=24, term=term))
    assert base64.b64decode(again["replay"]) == b"ls\r"
    assert box.ptys[0].size == (80, 24)
    box.ptys[0].prints(b"both")
    _until(lambda: _term(bob.snapshot(), term) == b"both")
    _until(lambda: _term(alice.snapshot(), term) == b"ls\rboth")

    _ok(alice.asks("env.term.resize", term=term, cols=120, rows=40))
    assert box.ptys[0].size == (120, 40)
    assert _ok(alice.asks("env.term.list", env=ROOT))["terms"] == [
        {
            "term": term,
            "env": ROOT,
            "title": "shell",
            "cols": 120,
            "rows": 40,
            "alive": True,
        }
    ]

    _ok(alice.asks("env.term.close", term=term))
    assert box.ptys[0].killed
    alice.told("term_exit", term=term, status=137)
    bob.told("term_exit", term=term, status=137)
    assert alice.asks("env.term.input", term=term, data="") == {
        "ok": False,
        "why": f"There is no terminal {term}.",
    }


def test_a_terminal_is_not_read_while_nobody_has_room_for_more(
    host: tuple[Host, Workspace], box: Box
) -> None:
    alice, _ = _going(host)
    term = _ok(alice.asks("env.term.open", env=ROOT, cols=80, rows=24))["term"]
    pty = box.ptys[0]
    piece = b"x" * (128 << 10)
    total = 24 * len(piece)
    for _ in range(24):
        pty.prints(piece)

    _until(lambda: len(_term(alice.snapshot(), term)) >= desk.CREDIT)
    time.sleep(0.2)
    reads = pty.reads
    got = len(_term(alice.snapshot(), term))
    assert got <= desk.CREDIT + len(piece)
    assert all(
        len(base64.b64decode(one["data"])) <= desk.CHUNK
        for one in alice.snapshot()
        if one["type"] == "term"
    )
    time.sleep(0.2)
    assert pty.reads == reads, "the pty was read with nobody to send it to"

    acked = 0
    while acked < total:
        _ok(alice.asks("env.term.ack", term=term, bytes=got - acked))
        acked = got
        _until(
            lambda acked=acked: (
                len(_term(alice.snapshot(), term)) > acked or acked == total
            )
        )
        time.sleep(0.05)
        got = len(_term(alice.snapshot(), term))
        assert got - acked <= desk.CREDIT + len(piece)
    assert got == total


def test_a_terminal_outlives_its_viewer_keeping_what_it_printed(
    host: tuple[Host, Workspace], box: Box
) -> None:
    alice, _ = _going(host)
    term = _ok(alice.asks("env.term.open", env=ROOT, cols=80, rows=24))["term"]
    _ok(alice.asks("detach"))

    box.ptys[0].prints(b"x" * (desk.SCROLLBACK + 10))
    box.ptys[0].prints(b"end")
    bob = Told(host[0], "bob")
    _until(lambda: _ok(bob.asks("env.term.list", env=ROOT))["terms"] != [])

    def replayed() -> bytes:
        said = _ok(bob.asks("env.term.open", env=ROOT, cols=80, rows=24, term=term))
        return base64.b64decode(said["replay"])

    _until(lambda: replayed().endswith(b"end"))
    assert len(replayed()) == desk.SCROLLBACK


def test_a_terminal_nobody_watches_is_taken_away(
    host: tuple[Host, Workspace], box: Box, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(desk, "IDLE", 0.0)
    alice, _ = _going(host)
    _ok(alice.asks("env.term.open", env=ROOT, cols=80, rows=24))
    bob = Told(host[0], "bob")

    alice.host.detach(alice.client)

    _until(lambda: box.ptys[0].killed)
    assert _ok(bob.asks("env.term.list", env=ROOT))["terms"] == []


def test_a_terminal_dies_with_its_env(host: tuple[Host, Workspace], box: Box) -> None:
    alice, run = _going(host)
    term = _ok(alice.asks("env.term.open", env=ROOT, cols=80, rows=24))["term"]

    run.released.set()

    alice.told("term_exit", term=term)
    _until(lambda: box.ptys[0].killed)
    assert not alice.asks("env.term.list", env=ROOT)["ok"]


def test_a_terminal_needs_a_shell(
    host: tuple[Host, Workspace], holding: Holding
) -> None:
    holding.envs[0] = Held(
        "repo",
        "local@/work",
        None,
        Box(capabilities=EVERYTHING - {ShellEnvMixin, BashEnvMixin}),
    )
    alice, _ = _going(host)

    assert alice.asks("env.term.open", env=ROOT, cols=80, rows=24) == {
        "ok": False,
        "why": "repo: this environment has no shell.",
    }
    assert alice.asks("env.term.open", env=ROOT, cols=80, rows=24, term="t9") == {
        "ok": False,
        "why": "repo: this environment has no shell.",
    }


# ------------------------------------------------------------------ git


STATUS = (
    "# branch.oid 1234\0"
    "# branch.head main\0"
    "# branch.upstream origin/main\0"
    "# branch.ab +2 -1\0"
    "1 .M N... 100644 100644 100644 aa bb a file.txt\0"
    "2 R. N... 100644 100644 100644 aa bb R100 new name.txt\0"
    "old name.txt\0"
    "u UU N... 100644 100644 100644 100644 aa bb cc both.txt\0"
    "? fresh.txt\0"
    "! ignored.txt\0"
)


def test_porcelain_v2_is_read_whole() -> None:
    said = gitdesk.parse_status(STATUS, "/work")

    assert {key: said[key] for key in said if key != "files"} == {
        "root": "/work",
        "branch": "main",
        "head": "1234",
        "upstream": "origin/main",
        "ahead": 2,
        "behind": 1,
    }
    assert said["files"] == [
        {"path": "a file.txt", "index": ".", "worktree": "M", "state": "changed"},
        {
            "path": "new name.txt",
            "orig": "old name.txt",
            "index": "R",
            "worktree": ".",
            "state": "changed",
        },
        {"path": "both.txt", "index": "U", "worktree": "U", "state": "conflict"},
        {"path": "fresh.txt", "index": "?", "worktree": "?", "state": "untracked"},
    ]
    fresh = gitdesk.parse_status(
        "# branch.oid (initial)\0# branch.head (detached)\0", "/w"
    )
    assert (fresh["head"], fresh["branch"], fresh["upstream"]) == (None, None, None)


def test_a_log_and_renames_are_read() -> None:
    assert gitdesk.parse_log(
        "abc\x1fp1 p2\x1fAda\x1f2026-01-01T00:00:00Z\x1ffix\0"
    ) == [
        {
            "hash": "abc",
            "parents": ["p1", "p2"],
            "author": "Ada",
            "date": "2026-01-01T00:00:00Z",
            "subject": "fix",
        }
    ]
    assert gitdesk.parse_renames("M\0a\0R090\0old\0new\0") == {"new": "old"}


def _git(box: Box, status: str = STATUS) -> None:
    def answers(argv: list[str]) -> tuple[int, str, str]:
        script = argv[2]
        if "rev-parse --show-toplevel" in script:
            return 0, "/work\n", ""
        if "status --porcelain=v2" in script:
            return 0, status, ""
        if "commit" in script:
            return 0, "cafe\n", ""
        if "side()" in script:
            return 0, f"y\n{_b64(b'old')}\n.\nn\n.\n", ""
        return 0, "", ""

    box.answers = answers


def test_git_is_read_and_changed_through_the_env(
    host: tuple[Host, Workspace], box: Box
) -> None:
    _git(box)
    alice, _ = _going(host)

    status = _ok(alice.asks("env.git.status", env=ROOT))
    assert (status["root"], status["branch"], len(status["files"])) == (
        "/work",
        "main",
        4,
    )
    assert box.ran[0][4] == "."  # where the root is looked for: the workdir
    assert box.ran[1][4] == "/work"
    assert "GIT_OPTIONAL_LOCKS=0" in box.ran[1][2]
    assert "--no-optional-locks" in box.ran[1][2]
    assert "core.quotepath=off" in box.ran[1][2]

    diff = _ok(alice.asks("env.git.diff", env=ROOT, path="a file.txt"))
    assert (diff["old"], diff["new"], diff["binary"]) == (_b64(b"old"), None, False)
    assert box.ran[-1][5:] == ["=a file.txt", "@a file.txt"]

    _ok(alice.asks("env.git.stage", env=ROOT, paths=["a file.txt"]))
    assert box.ran[-1][5:] == ["a file.txt"]
    alice.told("env_used", what="staged", path="a file.txt")
    _ok(alice.asks("env.git.unstage", env=ROOT, paths=["a", "b"]))
    used = alice.told("env_used", what="unstaged")
    assert "path" not in used
    _ok(alice.asks("env.git.discard", env=ROOT, paths=["a file.txt", "fresh.txt"]))
    assert "restore --worktree" in box.ran[-1][2]
    assert "clean -f -d" in box.ran[-1][2]
    assert box.ran[-1][5:] == ["a file.txt", "fresh.txt"]

    assert _ok(alice.asks("env.git.commit", env=ROOT, message="fix"))["head"] == "cafe"
    assert box.ran[-1][5:] == ["-m", "fix"]
    alice.told("env_used", what="committed")
    assert alice.asks("env.git.commit", env=ROOT, message=" ") == {
        "ok": False,
        "why": "a commit needs a message",
    }
    _ok(alice.asks("env.git.commit", env=ROOT, message="fix it", amend=True))
    assert box.ran[-1][5:] == ["--amend", "-m", "fix it"]


def test_git_refusals_are_said_as_git_said_them(
    host: tuple[Host, Workspace], box: Box
) -> None:
    box.answers = _answers("", 128, "fatal: not a git repository")
    alice, _ = _going(host)

    assert alice.asks("env.git.status", env=ROOT) == {
        "ok": False,
        "why": "repo: this environment has no git.",
    }


def test_an_env_serving_git_serves_rewinding() -> None:
    assert desk.caps_of(frozenset({GitEnvMixin})) == ["git", "rewind"]
    assert desk.caps_of(frozenset({BashEnvMixin})) == ["shell", "bash"]
    assert desk.caps_of(frozenset({FilesEnvMixin})) == ["files"]


def test_an_env_without_git_is_refused_it(
    host: tuple[Host, Workspace], holding: Holding
) -> None:
    holding.envs[0] = Held(
        "repo",
        "local@/work",
        None,
        Box(capabilities=EVERYTHING - {GitEnvMixin}),
    )
    alice, _ = _going(host)

    for method in ("env.git.status", "env.git.snapshots"):
        assert alice.asks(method, env=ROOT) == {
            "ok": False,
            "why": "repo: this environment has no git.",
        }


@dataclass(frozen=True)
class Placement:
    backend: str = "local"
    provider: str = ""
    workdir: PurePosixPath = field(default_factory=lambda: PurePosixPath("/work"))
    machine: None = None
    env: str = "repo"


def test_a_rewind_waits_for_whoever_is_working_here(
    host: tuple[Host, Workspace], box: Box
) -> None:
    alice, run = _going(host)
    assert _ok(alice.asks("env.git.snapshots", env=ROOT))["snapshots"] == box.refs
    agent, session = Agent(), Session()
    agent.sessions.append(session)
    run.agents.append(agent)
    assert run.opener is not None
    run.opener("builder", agent, session, Placement())
    assert run.listener is not None
    run.listener(agent, session, Event("begins"))

    assert alice.asks("env.git.rewind", env=ROOT, ref="refs/hmz/snapshots/a") == {
        "ok": False,
        "why": "builder is working here; stop it first",
    }

    run.listener(agent, session, Event("ends"))
    _ok(alice.asks("env.git.rewind", env=ROOT, ref="refs/hmz/snapshots/a"))
    assert box.rewound == ["refs/hmz/snapshots/a"]
    alice.told("env_used", what="rewound")
