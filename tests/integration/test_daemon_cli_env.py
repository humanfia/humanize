"""`hmz env` and `client.envs`, asked of a real daemon whose host has an epic going in a repository.

A flow that takes a snapshot and then waits is started in a temporary git repository; the
commands then browse, write, search, stage, commit, rewind and open a terminal in the
environment it holds, and what each changed is read back from the directory itself.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli, daemon
from hmz.sdk import Client, Refused
from tests.integration.doubles_daemon import hosting, project, until, written

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(180),
    pytest.mark.skipif(shutil.which("git") is None, reason="needs git"),
]

#: Takes a snapshot of the repository it is started in, and then runs until it is stopped.
SNAPS = """
import asyncio

from hmz.flows import AgentCollection, EnvCollection, FlowParams, GitEnvMixin, LocalEnv, flow


class Repo(LocalEnv, GitEnvMixin): ...


class Envs(EnvCollection):
    code: Repo


@flow(agents=AgentCollection, envs=Envs, params=FlowParams, name="snaps")
async def snaps(task, *, agents, envs, params, ctx):
    await envs["code"].snapshot("before")
    while True:
        await asyncio.sleep(0.05)
"""


def _git(where: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(where), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A repository with one commit, and an epic going in it that has taken one snapshot."""
    at = project(tmp_path, monkeypatch)
    written(at, "snaps", SNAPS)
    _git(at, "init", "-q", "-b", "main")
    _git(at, "config", "user.email", "a@example.com")
    _git(at, "config", "user.name", "Ada")
    _git(at, "config", "commit.gpgsign", "false")
    (at / "README.md").write_text("hello\n")
    _git(at, "add", "-A")
    _git(at, "commit", "-q", "-m", "first")
    with hosting():
        with daemon.host().link(name="starter") as link:
            link.start("./snaps", "forever", budget={"cost": 1})
            assert until(lambda: "refs/hmz/snapshots/before" in _git(at, "show-ref"))
        # The host lists the environment a moment after the flow opened it.
        with Client.local() as client, client.envs.attached(str(at)) as host:
            assert host.envs(wait=30)
        yield at


def _said(capsys: pytest.CaptureFixture[str], *line: str) -> Any:
    """What a command answers under `--json`, having done what it was asked."""
    assert cli.main(["env", *line, "--json"]) == 0
    said = capsys.readouterr()
    assert said.err == ""
    return json.loads(said.out)


def _refused(capsys: pytest.CaptureFixture[str], *line: str) -> str:
    assert cli.main(["env", *line]) == 1
    return capsys.readouterr().err


def test_no_environment_is_reached_where_no_host_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    at = project(tmp_path, monkeypatch)
    with hosting():
        assert _refused(capsys, "list").startswith("hmz env list: no runs are held in ")
        assert cli.main(["env", "ls", "--json"]) == 1
        assert json.loads(capsys.readouterr().out)["error"]["code"] == 404
        with Client.local() as client:
            with pytest.raises(Refused, match="no runs are held in"):
                client.envs.attached(str(at))
            # Nothing was started to answer that.
            assert client.call("hosts.list")["held"] == []


def test_the_files_of_an_environment_are_browsed_written_and_removed(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (env,) = _said(capsys, "list")["envs"]
    assert (env["role"], env["workdir"], env["open"]) == ("code", str(workspace), True)
    assert {"files", "shell", "git", "rewind"} <= set(env["caps"])

    names = [one["name"] for one in _said(capsys, "ls")["entries"]]
    assert names == [".git", "snaps", "README.md"]
    assert _said(capsys, "stat", "README.md", "--env", "code")["path"] == str(
        workspace / "README.md"
    )
    assert _refused(capsys, "stat", "nope") == "hmz env stat: No such file: nope\n"

    read = _said(capsys, "cat", "README.md")
    assert (read["text"], read["size"], read["eof"]) == ("hello\n", 6, True)
    assert cli.main(["env", "cat", "README.md"]) == 0
    assert capsys.readouterr().out == "hello\n"

    # Written against what was read: once, and not again over what the first left.
    local = workspace.parent / "local.txt"
    local.write_text("hello again\n")
    line = ("write", "README.md", "--from", str(local), "--if-match", read["etag"])
    wrote = _said(capsys, *line)
    assert (workspace / "README.md").read_text() == "hello again\n"
    assert wrote["etag"] == _said(capsys, "cat", "README.md")["etag"] != read["etag"]
    assert _refused(capsys, *line) == (
        "hmz env write: README.md changed since you read it.\n"
    )
    # A new file only: made where there is none, refused where there is one.
    fresh = ("write", "notes/new.txt", "--from", str(local), "--if-match", "")
    assert cli.main(["env", *fresh]) == 0
    assert capsys.readouterr().out == "Saved.\n"
    assert _refused(capsys, *fresh).endswith("changed since you read it.\n")

    assert _said(capsys, "mkdir", "docs/guides") == {"path": "docs/guides"}
    assert _said(capsys, "mv", "notes/new.txt", "docs/guides/new.md")["to"] == (
        "docs/guides/new.md"
    )
    assert (workspace / "docs/guides/new.md").read_text() == "hello again\n"
    assert _said(capsys, "find", "new") == {
        "paths": ["docs/guides/new.md"],
        "truncated": False,
    }
    found = _said(capsys, "search", "HELLO", "--glob", "*.md")
    assert [(one["path"], one["line"]) for one in found["matches"]] == [
        ("docs/guides/new.md", 1),
        ("README.md", 1),
    ] or sorted(one["path"] for one in found["matches"]) == [
        "README.md",
        "docs/guides/new.md",
    ]
    assert _said(capsys, "search", "HELLO", "--case")["matches"] == []

    # Nobody is there to say yes, so nothing is removed until the line says it.
    assert cli.main(["env", "rm", "docs"]) == 1
    capsys.readouterr()
    assert (workspace / "docs").is_dir()
    assert _said(capsys, "rm", "docs", "--yes") == {"path": "docs"}
    assert not (workspace / "docs").exists()


def test_a_command_is_run_in_the_env_of_the_epic(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["env", "exec", "--", "sh", "-c", "pwd; echo no >&2; exit 3"]) == 5
    said = capsys.readouterr()
    assert (said.out, said.err) == (f"{workspace}\n", "no\n")

    line = ["env", "exec", "--env", "code", "--json", "--", "git", "log", "--format=%s"]
    assert cli.main(line) == 0
    assert json.loads(capsys.readouterr().out) == {
        "code": 0,
        "stdout": "first\n",
        "stderr": "",
    }
    assert _refused(capsys, "exec", "--env", "nope", "--", "true") == (
        "hmz env exec: The epic has no env nope.\n"
    )


def test_changes_are_staged_committed_and_rewound(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (workspace / "README.md").write_text("hello again\n")
    (workspace / "new.txt").write_text("new\n")

    status = _said(capsys, "git", "status")
    assert (status["branch"], status["upstream"]) == ("main", None)
    changed = {one["path"]: one["index"] + one["worktree"] for one in status["files"]}
    assert (changed["README.md"], changed["new.txt"]) == (".M", "??")

    assert cli.main(["env", "git", "diff", "README.md"]) == 0
    assert capsys.readouterr().out == (
        "--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-hello\n+hello again\n"
    )
    assert _said(capsys, "git", "stage", "README.md") == {"paths": ["README.md"]}
    staged = _said(capsys, "git", "diff", "--staged")
    assert [one["path"] for one in staged["files"]] == ["README.md"]
    assert _said(capsys, "git", "unstage", "--all") == {"paths": ["README.md"]}
    assert _said(capsys, "git", "diff", "--staged")["files"] == []

    # Thrown away only once the line says yes.
    assert cli.main(["env", "git", "discard", "new.txt"]) == 1
    capsys.readouterr()
    assert _said(capsys, "git", "discard", "new.txt", "--yes") == {"paths": ["new.txt"]}
    assert not (workspace / "new.txt").exists()

    head = _said(capsys, "git", "commit", "--all", "-m", "docs: say it again")["head"]
    assert _git(workspace, "rev-parse", "HEAD").strip() == head
    assert "README.md" in _git(workspace, "show", "--stat", "--format=", head)
    amended = _said(capsys, "git", "commit", "--amend", "-m", "docs: again")["head"]
    log = _said(capsys, "git", "log", "--limit", "2")["commits"]
    assert (log[0]["hash"], log[0]["subject"]) == (amended, "docs: again")
    assert log[1]["subject"] == "first"
    assert cli.main(["env", "git", "status"]) == 0
    assert capsys.readouterr().err == "No changes.\n"

    assert _said(capsys, "git", "snapshots") == {
        "snapshots": ["refs/hmz/snapshots/before"]
    }
    assert cli.main(["env", "git", "rewind", "refs/hmz/snapshots/before"]) == 1
    capsys.readouterr()
    assert (workspace / "README.md").read_text() == "hello again\n"
    assert _said(capsys, "git", "rewind", "refs/hmz/snapshots/before", "-y") == {
        "ref": "refs/hmz/snapshots/before"
    }
    assert (workspace / "README.md").read_text() == "hello\n"


def test_a_terminal_is_started_listed_come_back_to_and_closed(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _said(capsys, "term", "list") == {"terms": []}
    term = _said(capsys, "term", "open", "--cols", "100", "--rows", "30")["term"]
    (listed,) = _said(capsys, "term", "list")["terms"]
    assert (listed["term"], listed["cols"], listed["rows"], listed["alive"]) == (
        term,
        100,
        30,
        True,
    )

    with Client.local() as client, client.envs.attached(str(workspace)) as host:
        env = host.env("code")
        assert [one.term for one in env.terminals.list()] == [term]
        terminal = env.terminals.open(term=term, cols=90, rows=20)
        terminal.write("echo answer-$((6 * 7)); exit 3\n")
        printed = b"".join(terminal)
        assert b"answer-42" in printed
        assert terminal.status == 3

        # One of its own, killed on leaving the block.
        with env.terminals.open() as other:
            assert other.id != term
            assert until(lambda: len(env.terminals.list()) >= 1)
        assert until(lambda: not [one for one in env.terminals.list() if one.alive])

    again = _said(capsys, "term", "open")["term"]
    assert _said(capsys, "term", "close", again) == {"term": again}
    assert until(
        lambda: (
            not [one for one in _said(capsys, "term", "list")["terms"] if one["alive"]]
        )
    )
    assert _refused(capsys, "term", "close", "nope") == (
        "hmz env term close: There is no terminal nope.\n"
    )


def test_the_family_names_every_method_of_an_environment_the_daemon_serves() -> None:
    from hmz.sdk.families.envs import Envs

    with hosting(), Client.local() as client:
        served = [one["name"] for one in client.call("rpc.discover")["methods"]]

    assert sorted(Envs.METHODS) == sorted(
        one for one in served if one.startswith(("env.", "hosts.env."))
    )


def test_the_same_is_asked_through_the_sdk(workspace: Path) -> None:
    with Client.local() as client:
        (role,) = client.envs.list(str(workspace))
        assert (role.name, role.kind, role.workdir) == ("code", "local", str(workspace))
        assert client.envs.write(str(workspace), "code", "a/b.txt", "héllo\n") == 7
        assert client.envs.read(str(workspace), "code", "a/b.txt").text == "héllo\n"
        assert client.envs.exec(str(workspace), "code", ["cat", "a/b.txt"]).stdout == (
            "héllo\n"
        )
        found = client.envs.grep(str(workspace), "code", "h.llo", path="a")
        assert [(one.path, one.line) for one in found.matches] == [("a/b.txt", 1)]

        with client.envs.attached(str(workspace)) as host:
            (env,) = host.envs()
            assert host.env().id == host.env("code").id == env.id
            files, git = host.env().files, host.env().git

            read = files.read("README.md")
            assert (read.data, read.eof) == (b"hello\n", True)
            wrote = files.write("README.md", b"hello\nmore\n", if_match=read.etag)
            assert files.read("README.md", offset=6).data == b"more\n"
            with pytest.raises(Refused, match=r"README.md changed since you read it\."):
                files.write("README.md", b"stale", if_match=read.etag)
            assert files.stat("README.md").size == wrote.size == 11
            assert "a/b.txt" in files.find().paths
            assert [one.path for one in files.search("more").matches] == ["README.md"]
            files.mkdir("d")
            files.rename("a/b.txt", "d/b.txt")
            files.remove("a")
            assert sorted(one.name for one in files.list(".") if one.kind == "dir") == [
                ".git",
                "d",
                "snaps",
            ]

            assert git.diff("README.md").new == b"hello\nmore\n"
            git.stage(["README.md", "d/b.txt"])
            assert git.diff("README.md", staged=True).old == b"hello\n"
            head = git.commit("docs: more")
            assert [one.hash for one in git.log(limit=1)] == [head]
            # Nothing left to commit but what running the flow compiled, where Python writes it.
            assert [
                one.path for one in git.status().files if "__pycache__" not in one.path
            ] == []
            assert git.snapshots() == ["refs/hmz/snapshots/before"]
            git.rewind("refs/hmz/snapshots/before")
            assert (workspace / "README.md").read_text() == "hello\n"

            with pytest.raises(Refused, match=r"There is no environment nope\."):
                host.env("nope")
