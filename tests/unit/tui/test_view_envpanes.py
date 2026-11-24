"""`hmz.tui.views.envpanes`: an environment's files, changes and terminal beside the log."""

from __future__ import annotations

import base64
import hashlib
import time
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList, Static

from hmz.tui import humanfia, shell
from hmz.tui.envs import (
    ChangesPane,
    Commit,
    FilesPane,
    Reach,
    Sure,
    TerminalPane,
    Tty,
)
from hmz.tui.shell import Hints, Shell, Zone
from hmz.tui.views import envpanes

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.binding import BindingType
    from textual.pilot import Pilot

WORKDIR = "/w"

#: The views this module is about.
OWN = ("files", "changes", "terminal")


@pytest.fixture(autouse=True)
def own_views(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only this module's views: what another view does beside them is its own test's."""
    found = {name: view for name, view in shell.views().items() if name in OWN}
    monkeypatch.setattr(shell, "views", lambda: found)


def _env(ident: str = "1:coder", **said: Any) -> dict[str, Any]:
    return {
        "id": ident,
        "role": ident.partition(":")[2],
        "chain": ident.partition(":")[2],
        "parent": None,
        "workdir": WORKDIR,
        "open": True,
        "caps": ["files", "shell", "git", "rewind"],
        "declared": [],
        **said,
    }


def _coded(data: bytes) -> str:
    return base64.b64encode(data).decode()


class Host:
    """A host as far as the panes ask it: files, a git status, and terminals that echo."""

    def __init__(self) -> None:
        self.envs = [_env()]
        self.files: dict[str, bytes] = {
            f"{WORKDIR}/README.md": b"# hello\n",
            f"{WORKDIR}/src/app.py": b"x = 1\n",
        }
        self.changed: list[dict[str, Any]] = [
            {"path": "a.py", "index": "M", "worktree": ".", "state": "changed"},
            {"path": "b.py", "index": ".", "worktree": "M", "state": "changed"},
        ]
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.terms: list[str] = []
        self.chat = "chat-1"
        self.reach = Reach(self.asks, lambda: self.envs, of=lambda: self.chat)

    def called(self, method: str) -> list[dict[str, Any]]:
        return [said for do, said in self.calls if do == method]

    def asks(self, said: dict[str, Any]) -> dict[str, Any]:
        said = dict(said)
        do = str(said.pop("do"))
        self.calls.append((do, said))
        # A terminal is named by itself alone (Section 4.24.4 of daemon.md).
        alone = ("env.term.input", "env.term.resize", "env.term.ack", "env.term.close")
        if do in alone and "env" in said:
            raise LookupError(f"{do} takes no env.")
        if do == "env.list":
            at = str(said.get("path") or WORKDIR).rstrip("/")
            folders = sorted(
                {
                    path[len(at) + 1 :].split("/")[0]
                    for path in self.files
                    if path.startswith(f"{at}/") and "/" in path[len(at) + 1 :]
                }
            )
            files = sorted(
                path[len(at) + 1 :]
                for path in self.files
                if path.startswith(f"{at}/") and "/" not in path[len(at) + 1 :]
            )
            return {
                "path": at,
                "entries": [
                    *({"name": one, "kind": "dir", "size": 0} for one in folders),
                    *(
                        {
                            "name": one,
                            "kind": "file",
                            "size": len(self.files[f"{at}/{one}"]),
                        }
                        for one in files
                    ),
                ],
            }
        if do == "env.read":
            path = str(said["path"])
            if path not in self.files:
                raise LookupError(f"No such file: {path}")
            data = self.files[path]
            return {
                "data": _coded(data),
                "size": len(data),
                "etag": hashlib.sha256(data).hexdigest(),
                "eof": True,
            }
        if do == "env.remove":
            path = str(said["path"])
            self.files = {
                one: data
                for one, data in self.files.items()
                if one != path and not one.startswith(f"{path}/")
            }
            return {}
        if do == "env.git.status":
            return {"root": WORKDIR, "branch": "main", "files": self.changed}
        if do == "env.git.diff":
            return {"old": _coded(b"x = 1\n"), "new": _coded(b"x = 2\n")}
        if do == "env.git.stage":
            for one in self.changed:
                if one["path"] in said["paths"]:
                    one["index"], one["worktree"] = "M", "."
            return {}
        if do == "env.git.commit":
            self.changed = [one for one in self.changed if one["index"] == "."]
            return {"head": "f00"}
        if do == "env.git.log":
            return {
                "commits": [
                    {
                        "hash": "abcdef123456",
                        "subject": "first",
                        "author": "me",
                        "date": "2026-01-02T03:04:05Z",
                    }
                ]
            }
        if do == "env.git.snapshots":
            return {"snapshots": ["snap-1"]}
        if do == "env.term.list":
            return {
                "terms": [
                    {"term": one, "env": said["env"], "title": "sh", "alive": True}
                    for one in self.terms
                ]
            }
        if do == "env.term.open":
            if said.get("term"):
                return {"term": said["term"], "replay": _coded(b"before$ ")}
            self.terms.append(f"t{len(self.terms) + 1}")
            return {"term": self.terms[-1], "replay": ""}
        if do == "env.term.close":
            self.terms.remove(str(said["term"]))
            return {}
        return {}

    def prints(self, term: str, data: bytes) -> None:
        """Has a terminal print, as the host tells the frontend that views it."""
        self.reach.told({"type": "term", "term": term, "data": _coded(data)})

    def typed(self) -> bytes:
        return b"".join(
            base64.b64decode(said["data"]) for said in self.called("env.term.input")
        )


class _Stands(App[None]):
    """An interface that is the zones and a prompt, reaching a host of the test's own."""

    BINDINGS: ClassVar[list[BindingType]] = [*shell.bindings()]

    def __init__(self, host: Host) -> None:
        super().__init__()
        self.shell = Shell(self)
        self.reach = host.reach

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def compose(self) -> ComposeResult:
        yield Zone(id="navigator")
        yield Input(id="editor")
        yield Zone(id="context")
        yield Hints(id="hints")

    def on_mount(self) -> None:
        self.shell.starts()

    async def action_view(self, name: str) -> None:
        await self.shell.toggles(name)


async def _until(pilot: Pilot[None], ready: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + 10
    while not ready():
        assert time.monotonic() < deadline, f"gave up waiting for {what}"
        await pilot.pause(0.02)


def _rows(pane: FilesPane | ChangesPane) -> list[str]:
    listing = pane.query_one("#pane-list", OptionList)
    return [str(one.id) for one in listing.options if not one.disabled]


async def _onto(pilot: Pilot[None], pane: FilesPane | ChangesPane, row: str) -> None:
    await _until(pilot, lambda: row in _rows(pane), f"the row {row!r}")
    listing = pane.query_one("#pane-list", OptionList)
    listing.highlighted = next(
        at for at, one in enumerate(listing.options) if one.id == row
    )
    await pilot.pause()


def _said(pane: Static | Any, held: str) -> str:
    return str(pane.query_one(held, Static).render())


@pytest.fixture
def host() -> Host:
    return Host()


def test_the_three_panes_open_in_the_context_each_on_a_key_of_its_own() -> None:
    found = {view.name: view for view in envpanes.VIEWS}

    assert {name: (view.zone, view.key) for name, view in found.items()} == {
        "files": ("context", "f5"),
        "changes": ("context", "f6"),
        "terminal": ("context", "f7"),
    }
    assert [view.title for view in found.values()] == ["Files", "Changes", "Terminal"]


async def test_files_is_a_tree_and_a_file_is_read_in_the_pane_beside_the_prompt(
    host: Host,
) -> None:
    app = _Stands(host)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("f5")
        pane = app.query_one(FilesPane)
        await _until(pilot, lambda: len(_rows(pane)) == 2, "the tree")
        assert _rows(pane) == [f"{WORKDIR}/src", f"{WORKDIR}/README.md"]
        assert "enter Open" in _said(pane, "#pane-foot")
        assert "^W Widen" in _said(pane, "#pane-foot")

        await _onto(pilot, pane, f"{WORKDIR}/src")
        await pilot.press("enter")
        await _until(
            pilot, lambda: f"{WORKDIR}/src/app.py" in _rows(pane), "the folder"
        )
        await pilot.press("enter")
        await _until(
            pilot, lambda: f"{WORKDIR}/src/app.py" not in _rows(pane), "it to shut"
        )

        await _onto(pilot, pane, f"{WORKDIR}/README.md")
        await pilot.press("enter")
        await _until(pilot, lambda: bool(pane.reading), "the file")
        assert pane.reading == f"{WORKDIR}/README.md"
        assert _said(pane, "#pane-path") == "README.md"
        assert "backspace Back" in _said(pane, "#pane-foot")
        # Nothing was written to read it.
        assert not host.called("env.write")

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.focused, Input)
        assert app.query_one("#context", Zone).has_class("open")
        assert pane.reading

        await pilot.press("f5", "backspace")
        await pilot.pause()
        assert not pane.reading


async def test_a_file_is_deleted_only_once_a_box_has_asked(host: Host) -> None:
    app = _Stands(host)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("f5")
        pane = app.query_one(FilesPane)
        await _onto(pilot, pane, f"{WORKDIR}/README.md")

        await pilot.press("d")
        await _until(pilot, lambda: isinstance(app.screen, Sure), "the box")
        assert not host.called("env.remove")
        await pilot.click("#act-yes")

        await _until(pilot, lambda: bool(host.called("env.remove")), "the removal")
        assert host.called("env.remove") == [
            {"env": "1:coder", "path": f"{WORKDIR}/README.md"}
        ]
        await _until(pilot, lambda: len(_rows(pane)) == 1, "the tree without it")


async def test_changes_show_the_diff_of_the_row_and_stage_and_commit_from_the_list(
    host: Host,
) -> None:
    app = _Stands(host)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("f6")
        pane = app.query_one(ChangesPane)
        await _onto(pilot, pane, "Changes\x1fb.py")
        assert _said(pane, "#pane-about") == f"main · {WORKDIR}"
        await _until(
            pilot, lambda: "b.py" in _said(pane, "#pane-path"), "the diff of b.py"
        )
        assert host.called("env.git.diff")[-1] == {
            "env": "1:coder",
            "path": "b.py",
            "staged": False,
        }

        await pilot.press("s")
        await _until(pilot, lambda: bool(host.called("env.git.stage")), "the stage")
        assert host.called("env.git.stage") == [{"env": "1:coder", "paths": ["b.py"]}]
        await _until(
            pilot, lambda: "Staged Changes\x1fb.py" in _rows(pane), "it listed staged"
        )

        await pilot.press("c")
        await _until(pilot, lambda: isinstance(app.screen, Commit), "the commit form")
        await pilot.press(*"both", "enter")
        await pilot.press("ctrl+s")
        if isinstance(app.screen, Commit):
            app.screen.action_done()
        await _until(pilot, lambda: bool(host.called("env.git.commit")), "the commit")
        assert host.called("env.git.commit") == [
            {"env": "1:coder", "message": "both", "amend": False}
        ]
        await _until(pilot, lambda: not _rows(pane), "nothing left to list")
        assert _said(pane, "#pane-said") == "No changes"


async def test_changes_list_the_commits_and_rewind_to_a_snapshot_once_asked(
    host: Host,
) -> None:
    app = _Stands(host)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("f6")
        pane = app.query_one(ChangesPane)
        await _until(pilot, lambda: bool(_rows(pane)), "the changes")

        await pilot.press("l")
        await _until(pilot, lambda: _rows(pane) == ["abcdef123456"], "the commits")
        assert pane.mode == "log"
        # The keys of the changes do nothing on the commits.
        await pilot.press("s")
        assert not host.called("env.git.stage")

        await pilot.press("backspace", "p")
        await _until(pilot, lambda: _rows(pane) == ["snap-1"], "the snapshots")
        await pilot.press("enter")
        await _until(pilot, lambda: isinstance(app.screen, Sure), "the box")
        assert not host.called("env.git.rewind")
        await pilot.click("#act-yes")

        await _until(pilot, lambda: bool(host.called("env.git.rewind")), "the rewind")
        assert host.called("env.git.rewind") == [{"env": "1:coder", "ref": "snap-1"}]
        await _until(pilot, lambda: pane.mode == "status", "the changes again")


async def test_the_terminal_takes_every_key_until_tilde_dot_gives_them_back(
    host: Host,
) -> None:
    app = _Stands(host)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("f7")
        pane = app.query_one(TerminalPane)
        await _until(pilot, lambda: isinstance(app.focused, Tty), "a terminal")
        tty = pane.tty
        assert tty is not None
        await _until(pilot, lambda: tty.term == "t1", "it to open")
        (opened,) = host.called("env.term.open")
        assert opened["cols"] == tty.size.width
        assert opened["rows"] == tty.size.height
        assert "~. Leave terminal" in _said(pane, "#pane-foot")

        # Letters that are keys of the pane, and esc, are the terminal's while it has them.
        await pilot.press("n", "x", "escape", "enter")
        await _until(pilot, lambda: host.typed() == b"nx\x1b\r", "what was typed")
        assert isinstance(app.focused, Tty)
        assert host.terms == ["t1"]

        host.prints("t1", b"hello from the shell\r\n$ ")
        await _until(pilot, lambda: "hello from the shell" in tty.text, "its output")

        await pilot.press("~", ".")
        await _until(pilot, lambda: not isinstance(app.focused, Tty), "the keys back")
        assert app.shell.held() is not None
        assert "n New terminal" in _said(pane, "#pane-foot")
        assert host.typed() == b"nx\x1b\r"

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.focused, Input)
        assert app.query_one("#context", Zone).has_class("open")
        # Still drawn, and still printing, with the keys at the prompt.
        host.prints("t1", b"later\r\n")
        await _until(pilot, lambda: "later" in tty.text, "what it printed since")


async def test_a_terminal_left_running_is_come_back_to_and_another_is_a_tab(
    host: Host,
) -> None:
    host.terms = ["t1"]
    app = _Stands(host)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("f7")
        pane = app.query_one(TerminalPane)
        await _until(pilot, lambda: pane.tty is not None, "the terminal")
        first = pane.tty
        assert first is not None
        await _until(pilot, lambda: "before$" in first.text, "what it kept")
        assert host.called("env.term.open")[0]["term"] == "t1"

        await pilot.press("~", ".", "n")
        await _until(pilot, lambda: host.terms == ["t1", "t2"], "another terminal")
        await _until(pilot, lambda: pane.tty is not first, "its tab")
        assert "2 sh" in _said(pane, "#pane-tabs") or "2 Terminal" in _said(
            pane, "#pane-tabs"
        )

        await pilot.press("~", ".", "left")
        await _until(pilot, lambda: pane.tty is first, "the first tab again")


async def test_ctrl_w_widens_the_context_and_tab_turns_to_the_next_environment(
    host: Host,
) -> None:
    host.envs = [_env(), _env("1:tester", workdir="/t")]
    host.files["/t/notes.txt"] = b"n\n"
    app = _Stands(host)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("f5")
        pane = app.query_one(FilesPane)
        context = app.query_one("#context", Zone)
        await _until(pilot, lambda: len(_rows(pane)) == 2, "the coder's files")
        assert "Environment coder  1/2" in _said(pane, "#pane-env")
        assert context.outer_size.width == 48

        await pilot.press("ctrl+w")
        await pilot.pause()
        assert context.has_class("wide")

        await pilot.press("tab")
        await _until(pilot, lambda: _rows(pane) == ["/t/notes.txt"], "the tester's")
        assert "Environment tester  2/2" in _said(pane, "#pane-env")

        # Every pane of this chat is turned to it, and another chat's is not.
        assert [one.id for one in (host.reach.desk("changes"),) if one] == ["1:tester"]
        host.chat = "chat-2"
        assert [one.id for one in (host.reach.desk("changes"),) if one] == ["1:coder"]


async def test_a_pane_says_so_where_no_environment_is_open(host: Host) -> None:
    host.envs = []
    app = _Stands(host)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("f6")
        pane = app.query_one(ChangesPane)
        await pilot.pause()

        assert _said(pane, "#pane-said") == "No environment is open here yet."
        assert not host.calls

        host.envs = [_env(caps=["files"])]
        host.reach.moved()
        await _until(
            pilot,
            lambda: _said(pane, "#pane-said") == "No changes in this environment",
            "it to say this one has no git",
        )
