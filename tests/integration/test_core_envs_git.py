"""An environment's git, files and search, as its panels use them, against a real repository.

The commands :mod:`hmz.runtime.doing.gitdesk` and :mod:`hmz.runtime.doing.desk` run are run
for real: by `/bin/sh`, against git, in a temporary repository, through a driver that does
what a local one does with an argv.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import FilesEnvMixin, GitEnvMixin, ShellEnvMixin
from hmz.runtime.doing import desk, envs, gitdesk

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


class Local:
    """A driver on this machine, as far as the panels ask one: exec, read and write."""

    backend = "local"
    provider = ""
    available = True
    cpu_count = 1
    memory = 0
    gpu_count = 0
    gpu_memory = 0
    capabilities = frozenset({FilesEnvMixin, ShellEnvMixin, GitEnvMixin})

    def __init__(self, workdir: Path) -> None:
        self.workdir = PurePosixPath(workdir)

    async def exec(
        self,
        argv: Sequence[str] | str,
        *,
        timeout: float = 60,  # noqa: ASYNC109 -- the driver's
    ) -> tuple[int, str, str]:
        assert not isinstance(argv, str)
        made = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self.workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(made.communicate(), timeout or None)
        return (
            made.returncode or 0,
            out.decode(errors="replace"),
            err.decode(errors="replace"),
        )

    async def read(self, path: str) -> bytes:
        return (Path(self.workdir) / path).read_bytes()

    async def write(self, path: str, data: bytes) -> None:
        (Path(self.workdir) / path).write_bytes(data)


@dataclass(frozen=True)
class Entry:
    name: str
    kind: str
    size: int
    mtime: float
    target: str | None = None


class Browsing(Local):
    """A local driver that lists, as the Files panel needs of one."""

    async def list(self, path: str) -> list[Any]:
        raise NotImplementedError(path)

    async def stat(self, path: str) -> Any:
        found = (Path(self.workdir) / path).stat()
        return Entry(Path(path).name, "file", found.st_size, found.st_mtime)

    async def mkdir(self, path: str) -> None:
        raise NotImplementedError(path)

    async def rename(self, path: str, to: str) -> None:
        raise NotImplementedError(path, to)

    async def remove(self, path: str) -> None:
        raise NotImplementedError(path)


def _git(where: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(where), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with one commit, then a change of every kind.

    `changed` modified in the worktree, `staged` modified in the index, `old name` renamed
    and staged, `gone` deleted, `fresh` untracked, and `both` conflicted by a merge.
    """
    where = tmp_path / "repo"
    where.mkdir()
    _git(where, "init", "-q", "-b", "main")
    _git(where, "config", "user.email", "a@example.com")
    _git(where, "config", "user.name", "Ada")
    _git(where, "config", "commit.gpgsign", "false")
    for name in ("changed", "staged", "old name", "gone", "both"):
        (where / name).write_text(f"{name}\n")
    (where / "picture").write_bytes(b"\x89PNG\0\0")
    _git(where, "add", "-A")
    _git(where, "commit", "-q", "-m", "first")
    _git(where, "checkout", "-q", "-b", "other")
    (where / "both").write_text("theirs\n")
    _git(where, "commit", "-q", "-am", "theirs")
    _git(where, "checkout", "-q", "main")
    (where / "both").write_text("ours\n")
    _git(where, "commit", "-q", "-am", "ours")
    subprocess.run(
        ["git", "-C", str(where), "merge", "-q", "other"],
        capture_output=True,
        check=False,
    )
    (where / "changed").write_text("changed again\n")
    (where / "staged").write_text("staged again\n")
    _git(where, "add", "staged")
    _git(where, "mv", "old name", "new name")
    (where / "gone").unlink()
    (where / "fresh").write_text("fresh\n")
    return where


def _nothing(*_: object) -> None:
    """What a frontend is told, or a guard says, where the test does not look."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def test_the_status_says_every_kind_of_change(repo: Path) -> None:
    run = Local(repo).exec
    top = await gitdesk.root(run)

    said = await gitdesk.status(run, top)

    assert said["root"] == _git(repo, "rev-parse", "--show-toplevel").strip()
    assert said["branch"] == "main"
    assert said["head"] == _git(repo, "rev-parse", "HEAD").strip()
    assert (said["upstream"], said["ahead"], said["behind"]) == (None, 0, 0)
    files = {one["path"]: one for one in said["files"]}
    assert (files["changed"]["index"], files["changed"]["worktree"]) == (".", "M")
    assert (files["staged"]["index"], files["staged"]["worktree"]) == ("M", ".")
    assert files["new name"]["orig"] == "old name"
    assert files["new name"]["index"] == "R"
    assert files["gone"]["worktree"] == "D"
    assert files["fresh"]["state"] == "untracked"
    assert files["both"]["state"] == "conflict"


async def test_a_diff_has_both_sides(repo: Path) -> None:
    run = Local(repo).exec
    top = await gitdesk.root(run)

    unstaged = await gitdesk.diff(run, top, "changed", staged=False)
    assert unstaged == {
        "old": _b64(b"changed\n"),
        "new": _b64(b"changed again\n"),
        "binary": False,
    }
    staged = await gitdesk.diff(run, top, "staged", staged=True)
    assert (staged["old"], staged["new"]) == (
        _b64(b"staged\n"),
        _b64(b"staged again\n"),
    )
    renamed = await gitdesk.diff(run, top, "new name", staged=True)
    assert (renamed["old"], renamed["new"]) == (
        _b64(b"old name\n"),
        _b64(b"old name\n"),
    )
    assert (await gitdesk.diff(run, top, "fresh", staged=False))["old"] is None
    assert (await gitdesk.diff(run, top, "gone", staged=False))["new"] is None
    conflicted = await gitdesk.diff(run, top, "both", staged=False)
    assert conflicted["old"] == _b64(b"ours\n")
    assert b"<<<<<<<" in base64.b64decode(conflicted["new"] or "")
    (repo / "picture").write_bytes(b"\x89PNG\0\1")
    assert (await gitdesk.diff(run, top, "picture", staged=False))["binary"] is True


async def test_changes_are_staged_unstaged_discarded_and_committed(repo: Path) -> None:
    run = Local(repo).exec
    top = await gitdesk.root(run)
    _git(repo, "checkout", "-q", "--theirs", "both")
    _git(repo, "add", "both")

    await gitdesk.stage(run, top, ["changed", "gone"])
    files = {one["path"]: one for one in (await gitdesk.status(run, top))["files"]}
    assert (files["changed"]["index"], files["gone"]["index"]) == ("M", "D")

    await gitdesk.unstage(run, top, ["changed"])
    files = {one["path"]: one for one in (await gitdesk.status(run, top))["files"]}
    assert (files["changed"]["index"], files["changed"]["worktree"]) == (".", "M")

    await gitdesk.discard(run, top, ["changed", "fresh"])
    files = {one["path"]: one for one in (await gitdesk.status(run, top))["files"]}
    assert "changed" not in files
    assert "fresh" not in files
    assert not (repo / "fresh").exists()

    head = await gitdesk.commit(run, top, "second", amend=False)
    assert head == _git(repo, "rev-parse", "HEAD").strip()
    amended = await gitdesk.commit(run, top, "second, said better", amend=True)
    assert amended != head
    await gitdesk.commit(run, top, "", amend=True)
    commits = await gitdesk.log(run, top, 10)
    assert [one["subject"] for one in commits[:2]] == ["second, said better", "ours"]
    assert commits[0]["author"] == "Ada"
    assert len(commits[0]["parents"]) == 2
    with pytest.raises(gitdesk.GitError):
        await gitdesk.commit(run, top, "nothing", amend=False)


async def test_a_repository_with_no_commits_is_read(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q", "-b", "trunk")
    (tmp_path / "a").write_text("a\n")
    _git(tmp_path, "add", "a")
    run = Local(tmp_path).exec
    top = await gitdesk.root(run)

    said = await gitdesk.status(run, top)
    assert (said["branch"], said["head"]) == ("trunk", None)
    assert await gitdesk.log(run, top, 5) == []
    await gitdesk.unstage(run, top, ["a"])
    assert (await gitdesk.status(run, top))["files"][0]["state"] == "untracked"
    with pytest.raises(gitdesk.GitError, match="not a git repository"):
        await gitdesk.root(Local(tmp_path.parent).exec)


@dataclass(frozen=True)
class Held:
    role: str
    chain: str
    parent: str | None
    driver: Any
    declared: frozenset[type] = frozenset()


@dataclass
class Holding:
    loop: asyncio.AbstractEventLoop
    envs: list[Held]

    def held_envs(self) -> tuple[Held, ...]:
        return tuple(self.envs)


@pytest.fixture
def loop() -> Iterator[asyncio.AbstractEventLoop]:
    made = asyncio.new_event_loop()
    thread = threading.Thread(target=made.run_forever, daemon=True)
    thread.start()
    try:
        yield made
    finally:
        made.call_soon_threadsafe(made.stop)
        thread.join(10)
        made.close()


def test_quick_open_search_and_git_through_the_desk(
    repo: Path, loop: asyncio.AbstractEventLoop
) -> None:
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "skip").write_text("needle\n")
    (repo / ".gitignore").write_text("ignored\nnode_modules/\n")
    (repo / "ignored").write_text("needle\n")
    (repo / "fresh").write_text("a Needle here\n")
    used: list[dict[str, Any]] = []
    made = desk.Desk(post=_nothing, record=used.append, guard=_nothing)
    (env,) = made.refresh(
        1, Holding(loop, [Held("repo", "here", None, Browsing(repo))]), going=True
    )

    found = made.asked("c1", "ada", "env.find", {"env": env["id"]})
    assert "fresh" in found["paths"]
    assert "new name" in found["paths"]
    assert "ignored" not in found["paths"]
    searched = made.asked(
        "c1", "ada", "env.search", {"env": env["id"], "query": "needle"}
    )
    assert {one["path"] for one in searched["matches"]} == {"fresh"}
    assert searched["matches"][0]["column"] == 3
    exact = made.asked(
        "c1", "ada", "env.search", {"env": env["id"], "query": "needle", "case": True}
    )
    assert exact["matches"] == []

    status = made.asked("c1", "ada", "env.git.status", {"env": env["id"]})
    assert status["branch"] == "main"
    made.asked("c1", "ada", "env.git.stage", {"env": env["id"], "paths": ["fresh"]})
    assert used[-1] == {
        "type": "env_used",
        "run": 1,
        "env": env["id"],
        "by": "ada",
        "what": "staged",
        "path": "fresh",
    }


def _searched_and_listed(
    where: Path, loop: asyncio.AbstractEventLoop
) -> tuple[set[str], set[str]]:
    for name in (".env", ".github/ci.yml", "plain", "node_modules/dep.js"):
        (where / name).parent.mkdir(exist_ok=True)
        (where / name).write_text("needle\n")
    (where / ".ignore").write_text("plain\n")
    made = desk.Desk(post=_nothing, record=_nothing, guard=_nothing)
    (env,) = made.refresh(
        1, Holding(loop, [Held("repo", "here", None, Browsing(where))]), going=True
    )
    found = made.asked("c1", "ada", "env.find", {"env": env["id"]})
    searched = made.asked(
        "c1", "ada", "env.search", {"env": env["id"], "query": "needle"}
    )
    return {one["path"] for one in searched["matches"]}, set(found["paths"])


_RG = shutil.which("rg")


@pytest.mark.skipif(_RG is None, reason="needs rg")
def test_rg_searches_the_files_quick_open_lists(
    repo: Path,
    tmp_path: Path,
    loop: asyncio.AbstractEventLoop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _RG is not None
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "rg").symlink_to(_RG)
    monkeypatch.setenv("PATH", f"{tmp_path / 'tools'}:{os.environ['PATH']}")

    searched, listed = _searched_and_listed(repo, loop)
    assert {".env", ".github/ci.yml", "plain", "node_modules/dep.js"} <= searched
    assert searched <= listed

    (tmp_path / "bare").mkdir()
    searched, listed = _searched_and_listed(tmp_path / "bare", loop)
    assert searched == {".env", ".github/ci.yml", "plain"} == listed - {".ignore"}


def test_rg_is_told_which_files_quick_open_lists(
    repo: Path,
    tmp_path: Path,
    loop: asyncio.AbstractEventLoop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "tools").mkdir()
    told = tmp_path / "tools" / "told"
    (tmp_path / "tools" / "rg").write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > "{told}"\n'
    )
    (tmp_path / "tools" / "rg").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path / 'tools'}:{os.environ['PATH']}")

    _searched_and_listed(repo, loop)
    inside = told.read_text().splitlines()
    assert {"--hidden", "--no-ignore-dot", "!.git"} <= set(inside)
    assert not {"--no-ignore", "!node_modules"} & set(inside)

    (tmp_path / "bare").mkdir()
    _searched_and_listed(tmp_path / "bare", loop)
    outside = told.read_text().splitlines()
    assert {"--hidden", "!.git", "--no-ignore", "!node_modules"} <= set(outside)


#: A grep that knows no long option and skips no binary file for `-I`, as BusyBox's does.
_SHORT = """#!/bin/sh
known=
for one do
  if [ -z "$known" ]; then
    case $one in
      -e|--) known=1 ;;
      --*) echo "grep: unrecognized option: ${one#--}" >&2; exit 2 ;;
      -*) one=$(printf %s "$one" | tr I a) ;;
    esac
  fi
  set -- "$@" "$one"; shift
done
exec {grep} "$@"
"""


@pytest.fixture
def short(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A machine with a grep of short options only and neither rg nor git; a workdir on it."""
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("sh", "head", "find", "tr", "cmp"):
        found = shutil.which(name)
        assert found is not None
        (tools / name).symlink_to(found)
    (tools / "grep").write_text(_SHORT.replace("{grep}", str(shutil.which("grep"))))
    (tools / "grep").chmod(0o755)
    monkeypatch.setenv("PATH", str(tools))
    where = tmp_path / "bare"
    where.mkdir()
    return where


def test_a_grep_of_short_options_only_searches_for_the_panel(
    short: Path, loop: asyncio.AbstractEventLoop
) -> None:
    for name in (".env", "plain", "node_modules/dep.js", ".git/config"):
        (short / name).parent.mkdir(exist_ok=True)
        (short / name).write_text("needle\n")
    (short / "sub").mkdir()
    (short / "sub" / "deep.txt").write_text("a Needle here\n")
    (short / "picture").write_bytes(b"\0needle\n")
    made = desk.Desk(post=_nothing, record=_nothing, guard=_nothing)
    (env,) = made.refresh(
        1, Holding(loop, [Held("bare", "here", None, Browsing(short))]), going=True
    )

    def searched(**said: Any) -> set[str]:
        found = made.asked("c1", "ada", "env.search", {"env": env["id"], **said})
        return {one["path"] for one in found["matches"]}

    assert searched(query="needle") == {".env", "plain", "sub/deep.txt"}
    assert searched(query="needle", glob="*.txt") == {"sub/deep.txt"}
    assert searched(query="ne+dle", regex=True, case=True) == {".env", "plain"}


def test_a_grep_of_short_options_only_searches_for_a_host(short: Path) -> None:
    (short / "notes").mkdir()
    (short / "notes" / "a.txt").write_text("hello\nworld: 1:2\n")
    (short / "notes" / "b:c").write_text("world\n")
    box = {"box": cast("Any", Local(short))}

    def grep(**said: Any) -> dict[str, Any]:
        return asyncio.run(envs.carried("hosts.env.grep", box, {"env": "box", **said}))

    found = grep(pattern="w.r+ld")
    assert sorted(found["matches"], key=lambda one: one["path"]) == [
        {"path": "notes/a.txt", "line": 2, "text": "world: 1:2"},
        {"path": "notes/b:c", "line": 1, "text": "world"},
    ]
    assert grep(pattern="hel+o", path="notes/a.txt")["matches"] == [
        {"path": "notes/a.txt", "line": 1, "text": "hello"}
    ]
    with pytest.raises(envs.EnvRefusal) as refused:
        grep(pattern="(")
    assert refused.value.code == 400


def test_quick_open_outside_a_repository_prunes_what_nobody_opens(
    tmp_path: Path, loop: asyncio.AbstractEventLoop
) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "y").write_text("")
    made = desk.Desk(post=_nothing, record=_nothing, guard=_nothing)
    (env,) = made.refresh(
        1, Holding(loop, [Held("box", "box", None, Browsing(tmp_path))]), going=True
    )

    assert made.asked("c1", "ada", "env.find", {"env": env["id"]})["paths"] == ["src/y"]


def test_a_file_too_large_to_hold_is_read_a_chunk_at_a_time_where_it_is(
    tmp_path: Path, loop: asyncio.AbstractEventLoop, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(desk, "_CACHED", 100)
    whole = bytes(range(256)) * 4
    (tmp_path / "big").write_bytes(whole)
    made = desk.Desk(post=_nothing, record=_nothing, guard=_nothing)
    (env,) = made.refresh(
        1, Holding(loop, [Held("box", "box", None, Browsing(tmp_path))]), going=True
    )

    first = made.asked(
        "c1", "ada", "env.read", {"env": env["id"], "path": "big", "length": 600}
    )
    rest = made.asked(
        "c1", "ada", "env.read", {"env": env["id"], "path": "big", "offset": 600}
    )

    assert base64.b64decode(first["data"]) + base64.b64decode(rest["data"]) == whole
    assert first["etag"] == rest["etag"] == hashlib.sha256(whole).hexdigest()
    assert (first["eof"], rest["eof"], rest["size"]) == (False, True, len(whole))


async def test_discarding_a_directory_restores_and_removes_alike(
    tmp_path: Path,
) -> None:
    repo = tmp_path
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "a@example.com")
    _git(repo, "config", "user.name", "Ada")
    _git(repo, "config", "commit.gpgsign", "false")
    run = Local(repo).exec
    top = await gitdesk.root(run)
    (repo / "dir").mkdir()
    (repo / "dir" / "kept").write_text("kept\n")
    _git(repo, "add", "dir/kept")
    _git(repo, "commit", "-q", "-m", "dir")
    (repo / "dir" / "kept").write_text("changed\n")
    (repo / "dir" / "new").mkdir()
    (repo / "dir" / "new" / "file").write_text("new\n")

    await gitdesk.discard(run, top, ["dir"])

    assert (repo / "dir" / "kept").read_text() == "kept\n"
    assert not (repo / "dir" / "new").exists()


async def test_a_path_is_a_file_name_and_not_a_pattern(tmp_path: Path) -> None:
    repo = tmp_path
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "a@example.com")
    _git(repo, "config", "user.name", "Ada")
    _git(repo, "config", "commit.gpgsign", "false")
    run = Local(repo).exec
    top = await gitdesk.root(run)
    names = ("[id].tsx", "i.tsx", "d.tsx")
    for name in names:
        (repo / name).write_text("first\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "first")
    for name in names:
        (repo / name).write_text("second\n")
    (repo / "*").write_text("fresh\n")
    (repo / "fresh").write_text("fresh\n")

    async def changes() -> dict[str, str]:
        files = (await gitdesk.status(run, top))["files"]
        return {one["path"]: one["index"] + one["worktree"] for one in files}

    await gitdesk.stage(run, top, ["[id].tsx"])
    assert await changes() == {
        "[id].tsx": "M.",
        "i.tsx": ".M",
        "d.tsx": ".M",
        "*": "??",
        "fresh": "??",
    }

    await gitdesk.stage(run, top, ["i.tsx"])
    await gitdesk.unstage(run, top, ["[id].tsx"])
    assert (await changes())["i.tsx"] == "M."

    await gitdesk.discard(run, top, ["[id].tsx", "*"])
    assert await changes() == {"i.tsx": "M.", "d.tsx": ".M", "fresh": "??"}
    assert (repo / "d.tsx").read_text() == "second\n"
