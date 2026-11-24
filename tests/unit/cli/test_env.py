"""`hmz env`: an environment's files, git and terminals, asked of a client that is mocked."""

from __future__ import annotations

import io
import json
import os
import pty
import sys
import threading
from types import SimpleNamespace as Said
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

import hmz.sdk
from hmz.cli import main, tree

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

ENV = Said(
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
    caps=("files", "git"),
    declared=("git",),
    facts={"cpu": 8},
)
SHUT = Said(**{**vars(ENV), "id": "1:tester", "chain": "tester", "open": False})
AWAY = Said(**{**vars(ENV), "id": "1:far", "chain": "far", "available": False})


@pytest.fixture
def envs(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The envs family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr("hmz.cli.commands.env._GRACE", 0.5)
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    return client.envs


@pytest.fixture
def host(envs: mock.Mock) -> mock.MagicMock:
    """The host the family attaches to, with one environment open."""
    held = mock.MagicMock()
    held.__enter__.return_value = held
    held.workspace, held.slot = "/w", ""
    held.envs.return_value = [ENV]
    envs.attached.return_value = held
    return held


@pytest.fixture
def env(host: mock.MagicMock) -> mock.Mock:
    """The environment the host answers for whichever is named."""
    return host.env.return_value


def _json(capsys: pytest.CaptureFixture[str]) -> Any:
    said = capsys.readouterr()
    assert said.err == ""
    return json.loads(said.out)


def test_the_environments_of_a_host_are_listed(
    envs: mock.Mock,
    host: mock.MagicMock,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    host.envs.return_value = [ENV, SHUT, AWAY]

    assert main(["env", "list"]) == 0

    assert capsys.readouterr().out == (
        "1:coder   coder   local  /w  files,git\n"
        "1:tester  tester  local  /w  files,git  closed\n"
        "1:far     far     local  /w  files,git  unavailable\n"
    )
    envs.attached.assert_called_once_with(str(os.getcwd()), slot=None)  # noqa: PTH109

    assert main(["env", "list", "-w", "~/p", "--slot", "exec:1f", "--json"]) == 0
    said = _json(capsys)
    assert (said["workspace"], said["slot"]) == ("/w", "")
    assert said["envs"][0] == {
        **vars(ENV),
        "caps": ["files", "git"],
        "declared": ["git"],
    }
    envs.attached.assert_called_with("~/p", slot="exec:1f")

    assert main(["env", "list", "-w", "rel", "--chat", "c1"]) == 0
    envs.attached.assert_called_with(chat="c1")


def test_a_host_with_no_environment_says_so(
    host: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    host.envs.return_value = []

    assert main(["env", "list"]) == 0
    said = capsys.readouterr()
    assert (said.out, said.err) == ("", "No environment is open here yet.\n")

    assert main(["env", "list", "--json"]) == 0
    assert _json(capsys)["envs"] == []

    assert main(["env", "ls"]) == 1
    assert capsys.readouterr().err == "hmz env ls: No environment is open here yet.\n"


def test_a_refusal_is_said_in_the_daemons_words(
    envs: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    envs.attached.side_effect = hmz.sdk.Refused("no runs are held in /w", code=404)

    assert main(["env", "ls"]) == 1
    assert capsys.readouterr().err == "hmz env ls: no runs are held in /w\n"

    assert main(["env", "git", "status", "--json"]) == 1
    assert _json(capsys) == {
        "error": {"code": 404, "message": "no runs are held in /w"}
    }


def test_a_directory_is_listed_and_a_path_described(
    host: mock.MagicMock, env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    src = Said(name="src", kind="dir", size=96, mtime=0.0, path=None, target=None)
    link = Said(name="l", kind="link", size=1, mtime=0.0, path="/w/l", target="src")
    env.files.list.return_value = [src, Said(**{**vars(link), "path": None})]
    env.files.stat.return_value = link

    assert main(["env", "ls", "--env", "coder"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert [(one.split()[0], one.split()[1], one.split()[-1]) for one in out] == [
        ("d", "96", "src/"),
        ("l", "1", "src"),
    ]
    assert out[1].endswith("l -> src")
    host.env.assert_called_once_with("coder")
    env.files.list.assert_called_once_with(".")

    assert main(["env", "ls", "sub", "--json"]) == 0
    assert _json(capsys) == {
        "path": "sub",
        "entries": [
            {"name": "src", "kind": "dir", "size": 96, "mtime": 0.0, "target": None},
            {"name": "l", "kind": "link", "size": 1, "mtime": 0.0, "target": "src"},
        ],
    }

    assert main(["env", "stat", "l"]) == 0
    assert capsys.readouterr().out.rstrip().endswith("/w/l -> src")
    assert main(["env", "stat", "l", "--json"]) == 0
    assert _json(capsys)["path"] == "/w/l"


def test_a_file_is_printed_as_it_is_or_described(
    env: mock.Mock, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    env.files.read.return_value = Said(
        data=b"h\xffi\n", size=4, mtime=1.5, etag="e1", eof=True
    )

    assert main(["env", "cat", "a.bin"]) == 0
    assert capsysbinary.readouterr().out == b"h\xffi\n"
    env.files.read.assert_called_once_with("a.bin", offset=None, length=None)

    assert (
        main(["env", "cat", "a.bin", "--offset", "1", "--length", "2", "--json"]) == 0
    )
    assert json.loads(capsysbinary.readouterr().out) == {
        "path": "a.bin",
        "text": "h\N{REPLACEMENT CHARACTER}i\n",
        "size": 4,
        "mtime": 1.5,
        "etag": "e1",
        "eof": True,
    }
    env.files.read.assert_called_with("a.bin", offset=1, length=2)


def test_files_are_found_by_name_and_searched(
    env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    env.files.find.return_value = Said(
        paths=("src/App.py", "README.md"), truncated=False
    )

    assert main(["env", "find", "app"]) == 0
    assert capsys.readouterr().out == "src/App.py\n"
    assert main(["env", "find", "--limit", "5", "--json"]) == 0
    assert _json(capsys) == {"paths": ["src/App.py", "README.md"], "truncated": False}
    env.files.find.assert_called_with(limit=5)
    assert main(["env", "find", "zzz"]) == 0
    assert capsys.readouterr().err == "No matching files.\n"

    env.files.search.return_value = Said(
        matches=(Said(path="a.py", line=3, column=5, text="x = 1"),), truncated=True
    )
    assert main(["env", "search", "x", "--regex", "--glob", "*.py"]) == 0
    said = capsys.readouterr()
    assert said.out == "a.py:3:5:x = 1\n"
    assert (
        said.err == "There are more results than shown; raise `--limit` to see them.\n"
    )
    env.files.search.assert_called_once_with(
        "x", regex=True, case=None, glob="*.py", limit=None
    )
    assert main(["env", "search", "x", "--case", "--limit", "1", "--json"]) == 0
    assert _json(capsys) == {
        "matches": [{"path": "a.py", "line": 3, "column": 5, "text": "x = 1"}],
        "truncated": True,
    }


def test_a_file_is_written_from_standard_input_or_a_file_against_what_was_read(
    env: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env.files.write.return_value = Said(etag="e2", size=3, mtime=2.5)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"in\xff")))

    assert main(["env", "write", "a.txt"]) == 0
    assert capsys.readouterr().out == "Saved.\n"
    env.files.write.assert_called_once_with("a.txt", b"in\xff", if_match=None)

    (tmp_path / "local").write_bytes(b"file")
    line = ["env", "write", "a.txt", "--from", str(tmp_path / "local")]
    assert main([*line, "--if-match", "e1", "--json"]) == 0
    assert _json(capsys) == {"path": "a.txt", "etag": "e2", "size": 3, "mtime": 2.5}
    env.files.write.assert_called_with("a.txt", b"file", if_match="e1")

    assert main([*line, "--if-match", ""]) == 0
    env.files.write.assert_called_with("a.txt", b"file", if_match="")


def test_directories_are_made_and_paths_moved(
    env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["env", "mkdir", "d/e"]) == 0
    assert capsys.readouterr().out == "Created\n"
    env.files.mkdir.assert_called_once_with("d/e")

    assert main(["env", "mv", "a", "b", "--json"]) == 0
    assert _json(capsys) == {"path": "a", "to": "b"}
    env.files.rename.assert_called_once_with("a", "b")


def test_removing_asks_first_and_does_nothing_unanswered(
    env: mock.Mock, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    unsure = (
        "Nothing was changed: this command asks before it acts, and with no terminal "
        "or `--json` it needs `--yes`."
    )
    # Nobody to ask: standard input is no terminal.
    assert main(["env", "rm", "build"]) == 4
    assert capsys.readouterr().err == f"hmz env rm: {unsure}\n"
    assert main(["env", "rm", "build", "--json"]) == 4
    assert _json(capsys) == {"error": {"code": 400, "message": unsure}}
    env.files.remove.assert_not_called()

    asked = mock.Mock(isatty=lambda: True, readline=mock.Mock(return_value="n\n"))
    monkeypatch.setattr(sys, "stdin", asked)
    assert main(["env", "rm", "build"]) == 4
    assert capsys.readouterr().err.startswith("Delete build? [y/N] ")
    env.files.remove.assert_not_called()

    asked.readline.return_value = "Yes\n"
    assert main(["env", "rm", "build"]) == 0
    assert capsys.readouterr().out == "Deleted\n"
    env.files.remove.assert_called_once_with("build")

    assert main(["env", "rm", "other", "-y", "--json"]) == 0
    assert _json(capsys) == {"path": "other"}
    asked.readline.assert_called_with()
    assert asked.readline.call_count == 2


def test_a_command_is_run_in_the_env_of_a_role(
    envs: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    envs.list.return_value = [Said(name="code"), Said(name="docs")]
    envs.exec.return_value = Said(code=0, stdout="out\n", stderr="err\n")
    at = str(tmp_path)

    assert main(["env", "exec", "-w", at, "--", "git", "log", "--oneline", "-5"]) == 0
    said = capsys.readouterr()
    assert (said.out, said.err) == ("out\n", "err\n")
    envs.exec.assert_called_once_with(
        at, "code", ["git", "log", "--oneline", "-5"], slot=None, seconds=None
    )

    envs.exec.return_value = Said(code=3, stdout="", stderr="no\n")
    line = ["env", "exec", "-w", at, "--env", "docs", "--seconds", "9", "--json"]
    assert main([*line, "--", "false"]) == 5
    assert _json(capsys) == {"code": 3, "stdout": "", "stderr": "no\n"}
    envs.exec.assert_called_with(at, "docs", ["false"], slot=None, seconds=9)
    envs.list.assert_called_once_with(at, slot=None)

    # One stopped at its time limit has no status, and did not succeed either.
    envs.exec.return_value = Said(code=None, stdout="", stderr="")
    assert main([*line, "--", "sleep", "99"]) == 5
    capsys.readouterr()

    envs.list.return_value = []
    assert main(["env", "exec", "-w", at, "--", "true"]) == 1
    assert capsys.readouterr().err == "hmz env exec: No environment is open here yet.\n"


def test_a_command_is_run_on_the_host_a_chat_is_going_on(
    envs: mock.Mock, host: mock.MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    envs.host.return_value = ("/there", "chat:2a")
    envs.exec.return_value = Said(code=0, stdout="", stderr="")

    assert main(["env", "exec", "--chat", "c1", "--env", "workspace", "--", "ls"]) == 0

    envs.host.assert_called_once_with("c1")
    # Nothing is attached to for it.
    envs.attached.assert_not_called()
    host.env.assert_not_called()
    envs.exec.assert_called_once_with(
        "/there", "workspace", ["ls"], slot="chat:2a", seconds=None
    )
    assert capsys.readouterr().out == ""


def _status(**given: Any) -> Said:
    files = (
        Said(path="a.py", index="M", worktree=".", state="changed", orig=None),
        Said(path="b.py", index=".", worktree="M", state="changed", orig=None),
        Said(path="new.txt", index="?", worktree="?", state="untracked", orig=None),
        Said(path="to.py", index="R", worktree=".", state="changed", orig="from.py"),
    )
    said = {
        "root": "/w",
        "branch": "main",
        "head": "abcdef1234",
        "upstream": "origin/main",
        "ahead": 2,
        "behind": 1,
        "files": files,
    }
    return Said(**{**said, **given})


def test_the_status_of_a_repository_is_said_as_the_page_says_it(
    env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    env.git.status.return_value = _status()

    assert main(["env", "git", "status"]) == 0
    assert capsys.readouterr().out == (
        "main\n"
        "2 ahead of and 1 behind origin/main\n"
        "M.  a.py\n"
        ".M  b.py\n"
        "??  new.txt\n"
        "R.  from.py -> to.py\n"
    )

    env.git.status.return_value = _status(branch=None, upstream=None, files=())
    assert main(["env", "git", "status"]) == 0
    said = capsys.readouterr()
    assert said.out == "abcdef1 (detached)\nNo upstream branch\n"
    assert said.err == "No changes.\n"

    env.git.status.return_value = _status(branch=None, head=None, upstream=None)
    assert main(["env", "git", "status", "--json"]) == 0
    said = _json(capsys)
    assert (said["branch"], said["head"], said["ahead"]) == (None, None, 2)
    assert said["files"][0] == {
        "path": "a.py",
        "index": "M",
        "worktree": ".",
        "state": "changed",
    }
    assert said["files"][3]["orig"] == "from.py"
    assert main(["env", "git", "status"]) == 0
    assert capsys.readouterr().out.startswith("No commits yet\n")


def test_changes_are_shown_as_a_unified_diff(
    env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    env.git.status.return_value = _status()
    sides = {
        "b.py": Said(old=b"x = 1\n\x0cy\rz\n", new=b"x = 2", binary=False),
        "new.txt": Said(old=None, new=b"hi\n", binary=False),
        "a.py": Said(old=b"\0" * 1500, new=None, binary=True),
        "to.py": Said(old=b"same\n", new=b"same\n", binary=False),
    }
    env.git.diff.side_effect = lambda path, staged: sides[path]  # pyright: ignore[reportUnknownLambdaType]

    assert main(["env", "git", "diff"]) == 0
    assert capsys.readouterr().out == (
        # A form feed and a lone carriage return end no line.
        "--- a/b.py\n+++ b/b.py\n@@ -1,2 +1 @@\n-x = 1\n-\x0cy\rz\n+x = 2\n"
        "\\ No newline at end of file\n"
        "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+hi\n"
    )
    assert env.git.diff.call_args_list == [
        mock.call("b.py", staged=None),
        mock.call("new.txt", staged=None),
    ]

    assert main(["env", "git", "diff", "--staged", "--json"]) == 0
    assert _json(capsys) == {
        "staged": True,
        "files": [
            {"path": "a.py", "binary": True, "diff": ""},
            {"path": "to.py", "binary": False, "diff": ""},
        ],
    }
    env.git.diff.assert_called_with("to.py", staged=True)

    assert main(["env", "git", "diff", "a.py", "--staged"]) == 0
    assert capsys.readouterr().out == (
        "a.py is a binary file (before 1.5 kB, deleted): there is no text to compare.\n"
    )
    assert main(["env", "git", "diff", "to.py"]) == 0
    assert capsys.readouterr().err == "No changes.\n"


def test_commits_and_snapshots_are_listed(
    env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    env.git.log.return_value = [
        Said(
            hash="abcdef1234",
            parents=("fedcba",),
            author="Ada",
            date="2026-01-01T00:00:00Z",
            subject="first",
        )
    ]
    env.git.snapshots.return_value = ["refs/hmz/snapshots/a"]

    assert main(["env", "git", "log", "--limit", "3"]) == 0
    assert capsys.readouterr().out == "abcdef1  2026-01-01T00:00:00Z  Ada  first\n"
    env.git.log.assert_called_once_with(limit=3)
    assert main(["env", "git", "log", "--json"]) == 0
    assert _json(capsys)["commits"][0]["parents"] == ["fedcba"]

    assert main(["env", "git", "snapshots"]) == 0
    assert capsys.readouterr().out == "refs/hmz/snapshots/a\n"
    assert main(["env", "git", "snapshots", "--json"]) == 0
    assert _json(capsys) == {"snapshots": ["refs/hmz/snapshots/a"]}

    env.git.log.return_value = []
    env.git.snapshots.return_value = []
    assert main(["env", "git", "log"]) == 0
    assert main(["env", "git", "snapshots"]) == 0
    assert capsys.readouterr().err == "No commits yet.\nNo snapshots yet.\n"


def test_paths_are_staged_and_unstaged_by_name_or_all_of_them(
    env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    env.git.status.return_value = _status()

    assert main(["env", "git", "stage", "b.py", "new.txt"]) == 0
    assert capsys.readouterr().out == "b.py\nnew.txt\n"
    env.git.stage.assert_called_once_with(["b.py", "new.txt"])
    env.git.status.assert_not_called()

    assert main(["env", "git", "stage", "--all", "--json"]) == 0
    assert _json(capsys) == {"paths": ["b.py", "new.txt"]}

    assert main(["env", "git", "unstage", "-A"]) == 0
    assert capsys.readouterr().out == "a.py\nto.py\n"
    # A rename is unstaged at the path it was renamed from too.
    env.git.unstage.assert_called_once_with(["a.py", "to.py", "from.py"])

    for line in (["stage"], ["unstage", "a.py", "--all"]):
        assert main(["env", "git", *line]) == 2
        assert capsys.readouterr().err == (
            f"hmz env git {line[0]}: name the paths to act on or pass `--all`, not both\n"
            f"Run `hmz env git {line[0]} --help` for help.\n"
        )

    env.git.status.return_value = _status(files=())
    assert main(["env", "git", "unstage", "--all"]) == 0
    said = capsys.readouterr()
    assert (said.out, said.err) == ("", "No changes.\n")
    env.git.unstage.assert_called_once()


def test_discarding_asks_first(
    env: mock.Mock, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    env.git.status.return_value = _status()

    assert main(["env", "git", "discard", "b.py"]) == 4
    capsys.readouterr()
    env.git.discard.assert_not_called()

    asked = mock.Mock(isatty=lambda: True, readline=mock.Mock(return_value="y\n"))
    monkeypatch.setattr(sys, "stdin", asked)
    assert main(["env", "git", "discard", "b.py"]) == 0
    said = capsys.readouterr()
    assert said.err == "Discard the changes to b.py? This cannot be undone. [y/N] "
    assert said.out == "b.py\n"

    asked.readline.return_value = "\n"
    assert main(["env", "git", "discard", "--all"]) == 4
    assert capsys.readouterr().err.startswith(
        "Discard the changes to 2 files? This cannot be undone. [y/N] "
    )
    env.git.discard.assert_called_once_with(["b.py"])

    assert main(["env", "git", "discard", "--all", "--yes", "--json"]) == 0
    assert _json(capsys) == {"paths": ["b.py", "new.txt"]}


def test_what_is_staged_is_committed(
    env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    env.git.status.return_value = _status()
    env.git.commit.return_value = "fff"

    assert main(["env", "git", "commit", "-m", "say it"]) == 0
    assert capsys.readouterr().out == "fff\n"
    env.git.commit.assert_called_once_with("say it", amend=None)
    env.git.stage.assert_not_called()

    assert main(["env", "git", "commit", "-a", "--amend", "-m", "m", "--json"]) == 0
    assert _json(capsys) == {"head": "fff"}
    env.git.stage.assert_called_once_with(["b.py", "new.txt"])
    env.git.commit.assert_called_with("m", amend=True)

    with pytest.raises(SystemExit) as unread:
        main(["env", "git", "commit"])
    assert unread.value.code == 2
    assert "-m/--message" in capsys.readouterr().err


def test_rewinding_asks_first_in_the_pages_words(
    env: mock.Mock, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert main(["env", "git", "rewind", "refs/s/a"]) == 4
    capsys.readouterr()

    asked = mock.Mock(isatty=lambda: True, readline=mock.Mock(return_value="y\n"))
    monkeypatch.setattr(sys, "stdin", asked)
    assert main(["env", "git", "rewind", "refs/s/a"]) == 0
    said = capsys.readouterr()
    assert said.err == (
        "Rewind this environment to refs/s/a? Its working tree is reset to that "
        "snapshot: every change made since, committed or not, is lost. [y/N] "
    )
    assert said.out == "Rewound the environment to refs/s/a.\n"
    env.git.rewind.assert_called_once_with("refs/s/a")

    assert main(["env", "git", "rewind", "refs/s/a", "-y", "--json"]) == 0
    assert _json(capsys) == {"ref": "refs/s/a"}


def test_terminals_are_listed_and_closed(
    env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    env.terminals.list.return_value = [
        Said(term="t1", env="1:coder", title="shell", cols=80, rows=24, alive=True),
        Said(term="t2", env="1:coder", title="make", cols=120, rows=40, alive=False),
    ]

    assert main(["env", "term", "list"]) == 0
    assert capsys.readouterr().out == (
        "t1  shell  80x24\nt2  make   120x40  [exited]\n"
    )
    assert main(["env", "term", "list", "--json"]) == 0
    assert _json(capsys)["terms"][1] == {
        "term": "t2",
        "env": "1:coder",
        "title": "make",
        "cols": 120,
        "rows": 40,
        "alive": False,
    }

    assert main(["env", "term", "close", "t1"]) == 0
    assert capsys.readouterr().out == "Closed.\n"
    env.terminals.close.assert_called_once_with("t1")

    env.terminals.list.return_value = []
    assert main(["env", "term", "list"]) == 0
    assert capsys.readouterr().err == "No terminal is open here.\n"


class Shell:
    """A terminal as the command is handed one: what it prints, and what was typed into it."""

    id = "t1"
    shell = None

    def __init__(
        self, *printed: bytes, status: int | None = 0, replay: bytes = b""
    ) -> None:
        self.replay = replay
        self.status: int | None = None
        self.typed: list[bytes] = []
        self.sized: list[tuple[int, int]] = []
        self._printed, self._status = printed, status
        self._heard = threading.Event()
        self.left = threading.Event()
        self.handed: Callable[[], object] = lambda: None

    def write(self, data: bytes) -> None:
        self.typed.append(data)
        self._heard.set()

    def resize(self, cols: int, rows: int) -> None:
        self.sized.append((cols, rows))

    def leave(self) -> None:
        self.left.set()

    def __iter__(self) -> Iterator[bytes]:
        yield from self._printed
        self.handed()
        # It ends once it has been typed into, or left.
        while not (self._heard.wait(0.01) or self.left.is_set()):
            pass
        if not self.left.is_set():
            self.status = self._status


def test_a_terminal_started_for_a_program_is_left_running(
    env: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell(replay=b"was\xff")
    env.terminals.open.return_value = shell

    line = ["env", "term", "open", "--term", "t1", "--cols", "100", "--rows", "30"]
    assert main([*line, "--json"]) == 0

    assert _json(capsys) == {
        "term": "t1",
        "shell": None,
        "replay": "was\N{REPLACEMENT CHARACTER}",
    }
    env.terminals.open.assert_called_once_with(cols=100, rows=30, term="t1")
    assert shell.left.is_set()


def test_what_is_piped_in_is_typed_and_what_is_printed_is_written_until_it_ends(
    env: mock.Mock, capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell = Shell(b"$ ", b"done\r\n", status=7, replay=b"before ")
    env.terminals.open.return_value = shell
    reads, writes = os.pipe()
    os.write(writes, b"make\n~.\n")
    os.close(writes)
    with os.fdopen(reads) as piped:
        monkeypatch.setattr(sys, "stdin", piped)

        assert main(["env", "term", "open"]) == 0

    said = capfd.readouterr()
    assert said.out == "before $ done\r\n"
    assert said.err == "\r\n[exited with status 7]\n"
    # Nothing typed down a pipe leaves a terminal: `~.` is two more keys.
    assert b"".join(shell.typed) == b"make\n~.\n"
    assert not shell.left.is_set()


def test_a_terminal_is_left_running_by_the_two_keys_after_a_newline(
    env: mock.Mock, capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell = Shell(b"$ ")
    monkeypatch.setattr(shell, "write", shell.typed.append)  # typed into, still running
    env.terminals.open.return_value = shell
    keys, tty = pty.openpty()
    shell.handed = lambda: os.write(keys, b"a~.b\r~~x\r~y\r~.")
    with os.fdopen(tty) as typed, os.fdopen(keys, "rb", buffering=0):
        monkeypatch.setattr(sys, "stdin", typed)

        assert main(["env", "term", "open"]) == 0

    said = capfd.readouterr()
    assert said.out == "$ "
    assert said.err == (
        "\r\nTerminal t1 is still running; `hmz env term open --term t1` comes "
        "back to it.\n"
    )
    assert b"".join(shell.typed) == b"a~.b\r~x\r~y\r"
    assert shell.left.is_set()


def test_typing_that_is_refused_ends_the_terminal_and_says_why(
    env: mock.Mock, capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell = Shell(b"$ ")
    refusal = hmz.sdk.Refused("Terminals are off for paired devices.", code=409)
    monkeypatch.setattr(shell, "write", mock.Mock(side_effect=refusal))
    env.terminals.open.return_value = shell
    reads, writes = os.pipe()
    os.write(writes, b"ls\n")
    with os.fdopen(reads) as piped, os.fdopen(writes, "wb", buffering=0):
        monkeypatch.setattr(sys, "stdin", piped)

        assert main(["env", "term", "open"]) == 1

    said = capfd.readouterr()
    assert said.out == "$ "
    assert said.err == "hmz env term open: Terminals are off for paired devices.\n"
    assert shell.left.is_set()
