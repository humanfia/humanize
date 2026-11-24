"""`/env`: the environments of the run in front of you, against a host that answers `env.*`."""

from __future__ import annotations

import base64
import hashlib
import posixpath
import threading
from typing import TYPE_CHECKING, Any

import pytest
from textual.widgets import TextArea

from hmz.daemon import Link
from hmz.tui import Humanize
from hmz.tui.envs import Changes, Conflict, Editing, Envs, Files
from tests.integration.doubles_tui import (
    SIZE,
    nothing_installed,
    on,
    onto,
    opens,
    rows,
    screen,
    shows,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: The interface reaches this machine's daemon for its notices, which is the test's own.
pytestmark = pytest.mark.usefixtures("daemon")

#: Where the environments here work.
WORKDIR = "/w"

#: The environments the host says the run uses: a coder's, one derived from it, a closed one.
ENVS: list[dict[str, Any]] = [
    {
        "id": "1:coder",
        "role": "coder",
        "chain": "coder",
        "parent": None,
        "run": 1,
        "backend": "local",
        "provider": "local",
        "workdir": WORKDIR,
        "available": True,
        "open": True,
        "caps": ["files", "shell", "bash", "git", "rewind"],
        "declared": ["git"],
        "facts": {},
    },
    {
        "id": "1:coder>fork",
        "role": "coder",
        "chain": "coder>fork",
        "parent": "1:coder",
        "run": 1,
        "backend": "local",
        "provider": "local",
        "workdir": "/w2",
        "available": True,
        "open": True,
        "caps": ["files"],
        "declared": [],
        "facts": {},
    },
    {
        "id": "1:tester",
        "role": "tester",
        "chain": "tester",
        "parent": None,
        "run": 1,
        "backend": "docker",
        "provider": "box",
        "workdir": "/src",
        "available": False,
        "open": False,
        "caps": ["files"],
        "declared": [],
        "facts": {},
    },
]


def _etag(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Host:
    """The runs, as far as `/env` asks them: files of their own, a git status, and a record."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {
            f"{WORKDIR}/README.md": b"hello\n",
            f"{WORKDIR}/src/app.py": b"x = 1\n",
            f"{WORKDIR}/logo.png": b"\x89PNG\0\0",
        }
        self.status: dict[str, Any] = {
            "root": WORKDIR,
            "branch": "main",
            "head": "abcdef1234",
            "upstream": "origin/main",
            "ahead": 1,
            "behind": 0,
            "files": [
                {"path": "a.py", "index": "M", "worktree": ".", "state": "changed"},
                {"path": "b.py", "index": ".", "worktree": "M", "state": "changed"},
                {
                    "path": "new.txt",
                    "index": "?",
                    "worktree": "?",
                    "state": "untracked",
                },
            ],
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._lock = threading.Lock()

    def asks(self, said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        del seconds
        do = str(said.pop("do", ""))
        with self._lock:
            self.calls.append((do, dict(said)))
            try:
                return {"ok": True, **self._answers(do, said)}
            except LookupError as why:
                return {"ok": False, "why": str(why.args[0])}

    def called(self, method: str) -> list[dict[str, Any]]:
        with self._lock:
            return [params for do, params in self.calls if do == method]

    def _path(self, path: str) -> str:
        return path if path.startswith("/") else posixpath.join(WORKDIR, path)

    def _answers(self, do: str, said: dict[str, Any]) -> dict[str, Any]:
        if do == "env.list":
            at = (
                self._path(str(said.get("path") or "")) if said.get("path") else WORKDIR
            )
            dirs: set[str] = set()
            files: list[dict[str, Any]] = []
            for path, data in self.files.items():
                if not path.startswith(f"{at.rstrip('/')}/"):
                    continue
                rest = path[len(at.rstrip("/")) + 1 :]
                if "/" in rest:
                    dirs.add(rest.split("/")[0])
                else:
                    files.append(
                        {"name": rest, "kind": "file", "size": len(data), "mtime": 0.0}
                    )
            entries = [
                {"name": one, "kind": "dir", "size": 0, "mtime": 0.0}
                for one in sorted(dirs)
            ] + sorted(files, key=lambda one: one["name"])
            return {"path": at, "entries": entries}
        if do == "env.read":
            path = self._path(str(said["path"]))
            if path not in self.files:
                raise LookupError(f"No such file: {path}")
            data = self.files[path]
            return {
                "data": base64.b64encode(data).decode(),
                "size": len(data),
                "mtime": 0.0,
                "etag": _etag(data),
                "eof": True,
            }
        if do == "env.write":
            path = self._path(str(said["path"]))
            match = said.get("if_match")
            if match is not None and (
                (match == "" and path in self.files)
                or (match and _etag(self.files.get(path, b"")) != match)
            ):
                raise LookupError(f"{path} changed since you read it.")
            data = base64.b64decode(str(said.get("data") or ""))
            self.files[path] = data
            return {"etag": _etag(data), "size": len(data), "mtime": 0.0}
        if do == "env.git.status":
            return self.status
        if do == "env.term.list":
            return {"terms": []}
        return {}


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Host:
    """A host saying the run uses :data:`ENVS`."""
    nothing_installed(tmp_path, monkeypatch)
    return Host()


def _linked(host: Host, *, envs: list[dict[str, Any]] | None = None) -> Link:
    link = Link(host.asks, lambda: None)
    link.client = "c1"
    link.told({"type": "envs", "envs": ENVS if envs is None else envs})
    return link


async def _editing(pilot: Pilot[None], text: str) -> Editing:
    editing = await on(pilot, Editing)
    area = editing.query_one("#code", TextArea)
    await until(pilot, lambda: area.text == text, f"the editor to read {text!r}")
    return editing


async def test_env_lists_every_environment_by_role_and_opens_one_on_its_first_page(
    host: Host,
) -> None:
    app = Humanize(link=_linked(host))
    async with app.run_test(size=SIZE) as pilot:
        await typed(pilot, "/env")
        await on(pilot, Envs)
        drawn = await shows(pilot, "Environments", "coder", "└ coder>fork", "tester")
        assert "docker · box · /src · closed" in drawn
        assert rows(app) == ["1:coder", "1:coder>fork", "1:tester"]

        await opens(pilot, "1:coder")

        # The flow declared git, so it opens on Changes; shift+tab steps back to Files.
        await on(pilot, Changes)
        await pilot.press("shift+tab")
        await on(pilot, Files)
        await shows(pilot, "README.md")


async def _files(pilot: Pilot[None]) -> None:
    await typed(pilot, "/env coder")
    await on(pilot, Changes)
    await pilot.press("shift+tab")
    await on(pilot, Files)
    await shows(pilot, "src/", "README.md")


async def test_env_names_a_role_it_has_not_got(host: Host) -> None:
    async with Humanize(link=_linked(host)).run_test(size=SIZE) as pilot:
        await typed(pilot, "/env nobody")

        await shows(
            pilot, "/env nobody: no such environment here; choose coder, tester."
        )


async def test_env_with_no_environment_is_refused(host: Host) -> None:
    async with Humanize(link=_linked(host, envs=[])).run_test(size=SIZE) as pilot:
        await typed(pilot, "/env")

        await shows(pilot, "hmz: no environment is open here")


async def test_an_edit_is_saved_after_a_second_against_what_was_read(
    host: Host,
) -> None:
    app = Humanize(link=_linked(host))
    async with app.run_test(size=SIZE) as pilot:
        await _files(pilot)
        await opens(pilot, "README.md")
        editing = await _editing(pilot, "hello\n")

        await pilot.press("X")

        await until(pilot, lambda: bool(host.called("env.write")), "the autosave")
        (wrote,) = host.called("env.write")
        assert wrote["path"] == f"{WORKDIR}/README.md"
        assert wrote["if_match"] == _etag(b"hello\n")
        assert base64.b64decode(wrote["data"]) == b"Xhello\n"
        await until(pilot, lambda: editing.state == "Saved", "it to say it saved")

        await pilot.press("escape")
        await on(pilot, Files)


async def test_a_file_changed_on_disk_asks_and_keeping_mine_writes_over_it(
    host: Host,
) -> None:
    app = Humanize(link=_linked(host))
    async with app.run_test(size=SIZE) as pilot:
        await _files(pilot)
        await opens(pilot, "README.md")
        await _editing(pilot, "hello\n")
        host.files[f"{WORKDIR}/README.md"] = b"theirs\n"

        await pilot.press("ctrl+e", "!", "ctrl+s")

        await on(pilot, Conflict)
        await shows(
            pilot,
            "changed in the environment since you opened it.",
            "Keep mine",
            "Reload",
            "Show the diff",
        )
        await pilot.click("#act-keep")
        await until(
            pilot,
            lambda: host.files[f"{WORKDIR}/README.md"] == b"hello!\n",
            "mine written over theirs",
        )
        assert host.called("env.write")[-1]["if_match"] is None


async def test_a_binary_file_is_not_opened_in_the_editor(host: Host) -> None:
    app = Humanize(link=_linked(host))
    async with app.run_test(size=SIZE) as pilot:
        await _files(pilot)

        await opens(pilot, "logo.png")

        why = "logo.png is not text and cannot be opened here."
        await shows(pilot, f"{why} Press e to open it in your own editor.")
        assert isinstance(app.screen, Files)


async def test_changes_are_grouped_and_one_is_staged_from_the_list(host: Host) -> None:
    app = Humanize(link=_linked(host))
    async with app.run_test(size=SIZE) as pilot:
        await typed(pilot, "/env coder")
        await on(pilot, Changes)

        drawn = await shows(pilot, "Staged Changes (1)", "Changes (1)", "Untracked (1)")
        assert "main · ↑1 ↓0 origin/main" in drawn
        await opens(pilot, "Changes\x1fb.py")
        await pilot.press("escape")  # the diff
        await on(pilot, Changes)
        await pilot.press("s")

        await until(pilot, lambda: bool(host.called("env.git.stage")), "the stage")
        assert host.called("env.git.stage") == [{"env": "1:coder", "paths": ["b.py"]}]


async def test_unstaging_a_staged_rename_names_the_path_it_was_renamed_from_too(
    host: Host,
) -> None:
    host.status["files"] = [
        {
            "path": "b.txt",
            "orig": "a.txt",
            "index": "R",
            "worktree": ".",
            "state": "changed",
        },
        {"path": "c.py", "index": "M", "worktree": ".", "state": "changed"},
    ]
    app = Humanize(link=_linked(host))
    async with app.run_test(size=SIZE) as pilot:
        await typed(pilot, "/env coder")
        await on(pilot, Changes)
        await shows(pilot, "Staged Changes (2)", "← a.txt")
        await onto(pilot, "Staged Changes\x1fb.txt")

        await pilot.press("u")

        await until(pilot, lambda: bool(host.called("env.git.unstage")), "the unstage")
        assert host.called("env.git.unstage") == [
            {"env": "1:coder", "paths": ["a.txt", "b.txt"]}
        ]

        app.screen.query_one("#act-unstage-all").focus()
        await pilot.press("enter")

        await until(
            pilot, lambda: len(host.called("env.git.unstage")) == 2, "unstage all"
        )
        assert host.called("env.git.unstage")[-1] == {
            "env": "1:coder",
            "paths": ["a.txt", "b.txt", "c.py"],
        }


async def test_somebody_s_hand_in_an_environment_is_a_dim_line(host: Host) -> None:
    link = _linked(host)
    app = Humanize(link=link)
    async with app.run_test(size=SIZE) as pilot:
        link.told(
            {
                "type": "env_used",
                "run": 1,
                "env": "1:coder",
                "by": "web",
                "what": "wrote",
                "path": "src/app.py",
            }
        )

        await shows(pilot, "web wrote src/app.py in coder")
        assert "web wrote" in screen(app)
