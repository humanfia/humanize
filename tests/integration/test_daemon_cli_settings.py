"""`hmz settings`, `hmz accounts` and `hmz nous`, asked of a real daemon over its socket.

The accounts here are made of credentials that are nobody's: what is held to is that a value
goes in by the environment or standard input and never comes out again.
"""

from __future__ import annotations

import io
import json
import re
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli
from hmz.sdk import Client, Refused
from tests.integration.doubles_daemon import hosting, project

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [pytest.mark.timeout(120)]

#: A credential of no account anywhere, which nothing may print.
SECRET = "sk-nobodys-key-0123456789"


@pytest.fixture(autouse=True)
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    with hosting():
        yield at


class Line:
    """The command line, run in this process, everything it ever printed kept."""

    def __init__(self, capsys: pytest.CaptureFixture[str]) -> None:
        self._capsys = capsys
        self.printed = ""

    def __call__(self, *words: str, status: int = 0) -> str:
        """Runs one line, holds its exit status to `status`, and returns what it printed."""
        assert cli.main(list(words)) == status, self._capsys.readouterr()
        said = self._capsys.readouterr()
        self.printed += said.out + said.err
        return said.out if status == 0 else said.err

    def json(self, *words: str) -> Any:
        return json.loads(self(*words, "--json"))


@pytest.fixture
def hmz(capsys: pytest.CaptureFixture[str]) -> Line:
    return Line(capsys)


def test_each_setting_written_is_the_setting_read_back(
    hmz: Line, workspace: Path
) -> None:
    assert hmz.json("settings", "get", "details") == {"details": False}
    assert hmz("settings", "get", "reports") == "null\n"

    assert hmz("settings", "set", "details", "on") == "Saved.\n"
    assert hmz("settings", "set", "reports", "off") == "Saved.\n"
    assert hmz("settings", "set", "harness_sessions", "on") == "Saved.\n"
    assert hmz("settings", "set", "prefer", "flow") == "Saved.\n"
    chat = ["settings", "set", "chat", "claude/opus", "-w", str(workspace)]
    assert hmz(*chat) == "Saved.\n"

    said = hmz.json("settings", "get", "-w", str(workspace))
    assert (said["details"], said["reports"], said["harness_sessions"]) == (
        True,
        False,
        True,
    )
    assert said["prefer"] == "flow"
    assert said["chat"].startswith("claude/opus")
    assert said["workspace"] == str(workspace.resolve())
    # The chat agent is the workspace's, and the rest the machine's.
    assert hmz("settings", "get", "chat") == "\n"
    assert hmz("settings", "get", "details") == "true\n"


def test_a_value_the_daemon_refuses_is_refused_in_its_words_and_not_written(
    hmz: Line,
) -> None:
    refused = hmz("settings", "set", "listen", "bogus", status=1)
    assert refused == "hmz settings set listen: bogus is not a listener.\n"
    assert hmz.json("settings", "get", "listen") == {"listen": []}

    assert hmz("settings", "set", "chat", "nobody//x", "--json", status=1) == ""
    assert hmz.json("settings", "get", "chat") == {"chat": ""}


def test_listeners_and_ice_servers_are_written_whole_and_no_credential_comes_back(
    hmz: Line, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert hmz("settings", "set", "listen", "tcp://127.0.0.1:0") == "Saved.\n"
    assert hmz("settings", "get", "listen") == '["tcp://127.0.0.1:0"]\n'
    assert hmz("settings", "set", "listen") == "Saved.\n"
    assert hmz("settings", "get", "listen") == "[]\n"

    turn = {"urls": "turn:turn.example.org:3478", "username": "u"}
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps([turn | {"credential": SECRET}]))
    )
    assert hmz("settings", "set", "ice_servers", "-") == "Saved.\n"
    shown = turn | {"credential": True}
    assert hmz.json("settings", "get", "ice_servers") == {"ice_servers": [shown]}

    # Sent back as it was shown, the credential written is the one kept.
    stun = "stun:stun.example.org:3478"
    assert hmz("settings", "set", "ice_servers", json.dumps(shown), stun)
    assert hmz.json("settings", "get", "ice_servers") == {
        "ice_servers": [shown, {"urls": stun}]
    }
    assert SECRET not in hmz.printed


def test_backup_targets_are_added_changed_and_removed_one_at_a_time(hmz: Line) -> None:
    target = ["settings", "set", "backup.target"]
    url = f"https://me:{SECRET}@example.org/epics.git"
    hmz(*target, "lab", "--url", url, "--policy", "session", "--default")
    hmz(*target, "home", "--url", "git@example.org:me/home.git", "--branch", "epics")

    struck = "https://***@example.org/epics.git"
    lab: dict[str, Any] = {"name": "lab", "url": struck, "branch": "main", "every": 30}
    home: dict[str, Any] = {
        "name": "home",
        "url": "git@example.org:me/home.git",
        "branch": "epics",
        "policies": [],
        "every": 30,
    }
    assert hmz.json("settings", "get", "backup") == {
        "backup": {
            "targets": [lab | {"policies": ["session"]}, home],
            "defaults": ["lab"],
        }
    }

    # The URL goes back struck, as it was shown, and the daemon keeps the one written.
    hmz(*target, "lab", "--policy", "interval", "--policy", "end", "--every", "5")
    hmz("settings", "set", "backup.defaults", "home", "lab")
    hmz(*target, "home", "--remove")
    assert hmz.json("settings", "get", "backup") == {
        "backup": {
            "targets": [lab | {"policies": ["interval", "end"], "every": 5}],
            "defaults": ["lab"],
        }
    }

    hmz("settings", "set", "backup", '{"targets": [], "defaults": []}')
    assert hmz("settings", "get", "backup") == '{"targets": [], "defaults": []}\n'
    assert SECRET not in hmz.printed


def test_a_workspace_with_nothing_set_up_has_nothing_to_forget(
    hmz: Line, workspace: Path
) -> None:
    assert hmz("settings", "forget", "-w", str(workspace)) == "Nothing to forget.\n"

    said = hmz.json("settings", "forget", "-w", "elsewhere")
    assert said["forgot"] is False
    assert said["workspace"] == str((workspace / "elsewhere").resolve())


def test_an_account_goes_in_by_the_environment_and_its_credential_never_comes_out(
    hmz: Line, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert hmz("accounts", "list") == ""
    assert "    ANTHROPIC_API_KEY  the API key\n" in hmz("accounts", "ways", "claude")
    ways = hmz.json("accounts", "ways", "claude")["backends"]
    assert [one["cli"] for one in ways] == ["claude"]
    key = next(one for one in ways[0]["ways"] if one["name"] == "key")
    assert key["asks"][0] == {
        "env": "ANTHROPIC_API_KEY",
        "about": "the API key",
        "secret": True,
        "fixed": "",
    }

    add = ["accounts", "add", "claude", "work", "--way", "key"]
    on_the_line = hmz(*add, "--set", f"ANTHROPIC_API_KEY={SECRET}", status=2)
    assert "ANTHROPIC_API_KEY is a credential" in on_the_line
    assert hmz("accounts", "list") == ""

    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    assert hmz(*add, "--env", "ANTHROPIC_API_KEY") == "Made claude@work.\n"
    taken = hmz(*add, "--env", "ANTHROPIC_API_KEY", status=1)
    assert taken == "hmz accounts add: claude has an account called work already.\n"
    assert "which needs a terminal" in hmz(
        "accounts", "add", "claude", "mine", "--way", "login", status=1
    )

    listed = hmz("accounts", "list").splitlines()
    assert " ".join(listed[0].split()) == "claude work key ANTHROPIC_API_KEY 0 models"
    assert listed[1].split()[:2] == ["claude", "Local"]
    work = hmz.json("accounts", "list")["accounts"][0]
    assert (work["cli"], work["name"], work["way"]) == ("claude", "work", "key")
    assert work["sets"] == ["ANTHROPIC_API_KEY"]
    assert SECRET not in hmz.printed


def test_an_account_is_corrected_copied_and_removed(
    hmz: Line, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = ["accounts", "add", "claude", "proxy", "--way", "anthropic-gateway"]
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{SECRET}\n"))
    url = "ANTHROPIC_BASE_URL=https://llm.example.org"
    hmz(*gateway, "--set", url, "--stdin", "ANTHROPIC_AUTH_TOKEN")

    correct = ["accounts", "correct", "claude", "proxy"]
    moved = "ANTHROPIC_BASE_URL=https://llm2.example.org"
    assert hmz(*correct, "--set", moved) == "Saved.\n"
    hmz(*correct, "--set", f"ANTHROPIC_AUTH_TOKEN={SECRET}", status=2)
    unasked = hmz(*correct, "--set", "ELSE=1", status=1)
    assert unasked == (
        "hmz accounts correct: anthropic-gateway asks nothing called ELSE.\n"
    )
    nobody = hmz("accounts", "correct", "claude", "nobody", status=1)
    assert nobody == (
        "hmz accounts correct: claude has no account called nobody to correct.\n"
    )

    proxy = hmz.json("accounts", "list")["accounts"][0]
    assert proxy["sets"] == ["ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"]

    # An API key is the vendor's, and so an account another harness could be run as.
    monkeypatch.setenv("NOBODYS_KEY", SECRET)
    key = ["--way", "key", "--env", "ANTHROPIC_API_KEY=NOBODYS_KEY"]
    hmz("accounts", "add", "claude", "work", *key)
    work = hmz.json("accounts", "list")["accounts"][1]
    into = work["serves"][0]
    assert hmz("accounts", "copy", "claude", "work", into) == f"Copied to {into}\n"
    held = hmz.json("accounts", "list")["accounts"]
    assert (into, "work") in {(one["cli"], one["name"]) for one in held}

    assert hmz("accounts", "remove", into, "work") == "Removed\n"
    assert hmz("accounts", "remove", "claude", "work") == "Removed\n"
    assert hmz("accounts", "remove", "claude", "proxy") == "Removed\n"
    gone = hmz("accounts", "remove", "claude", "proxy", status=1)
    assert gone == "hmz accounts remove: claude has no account called proxy.\n"
    unknown = hmz("accounts", "models", "claude", "nobody", status=1)
    assert unknown == "hmz accounts models: claude has no account called nobody.\n"
    assert hmz("accounts", "list") == ""
    assert SECRET not in hmz.printed


def test_a_nous_is_written_listed_renamed_and_cleared(hmz: Line) -> None:
    assert hmz("nous", "list") == ""
    # No coding agent is installed here: only what Humanize brings with it answers, or fails.
    assert re.fullmatch(r"\d+ concrete nous of \d+ harnesses\.\n", hmz("nous", "scan"))
    assert isinstance(hmz.json("nous", "scan")["failed"], list)

    opus, sol = "claude/claude-opus-4-1", "codex/gpt-6-sol"
    haiku = "claude/claude-haiku-4-5"
    assert hmz("nous", "set", opus, "--tries", "3", "--timeout", "600") == "Saved.\n"
    hmz("nous", "set", "careful", "--graph", opus, "--graph", sol, "--tries", "1")
    hmz("nous", "set", "claude/claude-haiku-4-5", "--then", "careful")
    # What is not said again stays: the graph is still the chain it was written as.
    hmz("nous", "set", "careful", "--policy", "constant")

    # In the order they were last written, which is not what is held to here.
    listed = sorted(" ".join(line.split()) for line in hmz("nous", "list").splitlines())
    assert listed == [
        f"careful Virtual 1 more go, constant no limit {opus},{sol} nowhere",
        f"{haiku} Concrete 0 more goes, exponential-jitter no limit - careful",
        f"{opus} Concrete 3 more goes, exponential-jitter at most 600s - nowhere",
    ]

    looped = hmz("nous", "set", opus, "--then", "careful", status=1)
    assert looped.startswith("hmz nous set: ")
    unknown = hmz("nous", "set", opus, "--policy", "nonsense", status=1)
    assert unknown == "hmz nous set: nonsense is no way of waiting.\n"

    assert hmz("nous", "rename", "careful", "slow") == "Renamed\n"
    names = [one["name"] for one in hmz.json("nous", "list")["nous"]]
    assert sorted(names) == sorted([opus, "slow", "claude/claude-haiku-4-5"])
    named = hmz("nous", "clear", "slow", status=1)
    assert named.startswith("hmz nous clear: ")
    hmz("nous", "set", "claude/claude-haiku-4-5", "--no-then")
    assert hmz("nous", "clear", "slow") == "Removed\n"
    nothing = hmz("nous", "clear", "slow", status=1)
    assert nothing == "hmz nous clear: Nothing is written down against slow.\n"


def test_the_same_is_asked_through_the_sdk(workspace: Path) -> None:
    with Client.local() as client:
        kept = client.settings.set(details=True, listen=[])
        assert kept.details is True
        assert kept.reports is None
        assert client.settings.get(str(workspace)).workspace == str(workspace.resolve())
        assert client.settings.forget(str(workspace)).forgot is False
        with pytest.raises(Refused, match="bogus is not a listener") as refused:
            client.settings.set(listen=["bogus"])
        assert refused.value.code == 400

        made = client.accounts.create(
            "claude", "work", "key", {"ANTHROPIC_API_KEY": SECRET}
        )
        work = made.account("claude", "work")
        assert work is not None
        assert work.sets == ("ANTHROPIC_API_KEY",)
        assert SECRET not in json.dumps(made.said)
        backend = made.backend("claude")
        assert backend is not None
        key = backend.way("key")
        assert key is not None
        assert [(ask.env, ask.secret) for ask in key.asks] == [
            ("ANTHROPIC_API_KEY", True)
        ]
        with pytest.raises(Refused) as taken:
            client.accounts.create("claude", "work", "key", {"ANTHROPIC_API_KEY": "x"})
        assert taken.value.code == 409
        assert client.accounts.correct("claude", "work").account("claude", "work")
        copied = client.accounts.copy("claude", "work", work.serves[0])
        assert copied.account(work.serves[0], "work") is not None
        client.accounts.remove(work.serves[0], "work")
        assert client.accounts.remove("claude", "work").accounts == ()

        book = client.nous.set(
            "careful", tries=2, graph=["claude/opus", "codex/sol"], then="pi/any"
        )
        careful = book.entry("careful")
        assert careful is not None
        assert careful.graph is not None
        assert careful.then is not None
        assert (careful.virtual, careful.tries) == (True, 2)
        assert [node.use for node in careful.graph.nodes] == [
            "claude/opus",
            "codex/sol",
        ]
        # A graph read is a graph that can be written back.
        again = client.nous.set("careful", graph=careful.graph, then=careful.then)
        kept_as = again.entry("careful")
        assert kept_as is not None
        assert kept_as.graph == careful.graph
        assert kept_as.tries == 0
        assert client.nous.rename("careful", "slow").entry("slow") is not None
        assert client.nous.scan().scanning is False
        assert client.nous.clear("slow").nous == ()
        with pytest.raises(Refused) as nothing:
            client.nous.clear("slow")
        assert nothing.value.code == 404
