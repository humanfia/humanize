"""`hmz notices`, `hmz btw` and `hmz ai`, asked of a real daemon, and the same through the SDK.

A chat of the stand-in `claude` answers once, which the daemon makes a notice of and which
leaves one session to ask a side question of; Ai-chan is the stand-in too, confined as her
conversation is.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli, config, daemon
from hmz.coganchor.fence import BWRAP, able
from hmz.daemon import where
from hmz.sdk import Client, Refused
from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_daemon import Heard, hosting, until

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [pytest.mark.timeout(240)]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = install(tmp_path, monkeypatch)
    with hosting():
        yield at


def _chatted(workspace: Path) -> tuple[daemon.Link, str, str]:
    """A chat that has answered once: its link, its name and the session it opened."""
    link = daemon.attach("sdk", workspace=workspace, slot=where.chat())
    heard = Heard()
    link.heard(heard)
    started = link.chat(AGENT, "remember papaya")
    assert until(lambda: any(one.get("mode") == "listen" for one in heard.of("asked")))
    (opened, *_) = heard.of("opened")
    return link, str(started["chat"]), str(opened["key"])


def _said(capsys: pytest.CaptureFixture[str], *line: str) -> Any:
    """What a command answers as JSON, having done what it was asked."""
    assert cli.main([*line, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_a_chats_turn_is_a_notice_listed_and_followed(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _said(capsys, "notices", "list") == {"notices": [], "last": 0}
    link, chat, _ = _chatted(workspace)
    try:
        assert until(lambda: _said(capsys, "notices", "list")["notices"], 60)
        listed = _said(capsys, "notices", "list")
        (notice, *_) = listed["notices"]
        assert (notice["kind"], notice["chat"], notice["flow"]) == (
            "done",
            chat,
            "chat",
        )
        assert listed["last"] >= notice["id"]

        assert cli.main(["notices", "list"]) == 0
        line = capsys.readouterr().out.splitlines()[0]
        assert line.startswith(f"{notice['id']}  ")
        assert f"  Done  {chat}  " in line

        # Nothing after the newest, and none of a kind that was not made.
        after = str(listed["last"])
        assert _said(capsys, "notices", "list", "--after", after) == {
            "notices": [],
            "last": listed["last"],
        }
        assert _said(capsys, "notices", "list", "--kind", "failed")["notices"] == []

        # Followed in a process of its own, which a ctrl+c ends.
        following = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "hmz",
                "notices",
                "follow",
                "--after",
                "0",
                "--json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert following.stdout is not None
            assert json.loads(following.stdout.readline()) == notice
            following.send_signal(signal.SIGINT)
            assert following.wait(30) == 130
        finally:
            following.kill()

        with Client.local() as client:
            assert client.notices.last() == listed["last"]
            assert client.notices.list()[0].chat == chat
            followed = client.notices.follow(after=0)
            assert next(followed).id == notice["id"]
            followed.close()
            # Ended as the following closed: the subscription is the session's no longer.
            heard = client.notices.subscribe()
            client.notices.unsubscribe(heard)
            with pytest.raises(Refused) as refused:
                client.notices.unsubscribe(heard.sub)
            assert refused.value.code == 410
    finally:
        link.close()


def test_a_chat_is_asked_a_side_question_which_is_listed_shown_and_left(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    link, chat, key = _chatted(workspace)
    try:
        assert _said(capsys, "btw", "sessions", "--chat", chat)["sessions"] == [
            {"session": key, "agent": key.partition("/")[0], "harness": "claude"}
        ]
        assert _said(capsys, "btw", "list", "--chat", chat) == {"asides": []}

        # Of the chat's newest session, with no `--to`; its side conversation is named.
        assert cli.main(["btw", "ask", "the word?", "--chat", chat]) == 0
        first = capsys.readouterr()
        assert "the word?" in first.out
        (aside,) = _said(capsys, "btw", "list", "--chat", chat)["asides"]
        assert (aside["to"], aside["question"]) == (key, "")
        assert f"Side conversation {aside['aside']}: " in first.err

        again = _said(
            capsys, "btw", "ask", "again?", "--chat", chat, "--aside", aside["aside"]
        )
        assert (again["aside"], again["to"]) == (aside["aside"], key)
        assert "again?" in again["answer"]

        shown = _said(capsys, "btw", "show", aside["aside"], "--chat", chat)
        assert [one["question"] for one in shown["said"]] == ["the word?", "again?"]
        assert cli.main(["btw", "list", "--chat", chat]) == 0
        assert capsys.readouterr().out == f"{aside['aside']}  {key}  2\n"

        # Refused in the daemon's words, and in the command's own.
        assert cli.main(["btw", "ask", "who?", "--to", "nobody", "--chat", chat]) == 1
        assert "<agent>/<n>" in capsys.readouterr().err
        assert cli.main(["btw", "show", "none", "--chat", chat]) == 1
        assert capsys.readouterr().err == (
            "hmz btw show: There is no side conversation none.\n"
        )

        assert _said(capsys, "btw", "leave", aside["aside"]) == {
            "aside": aside["aside"]
        }
        assert _said(capsys, "btw", "list", "--chat", chat) == {"asides": []}

        with Client.local() as client:
            here = str(workspace)
            assert [one.key for one in client.btw.sessions(chat=chat)] == [key]
            answer = client.btw.ask(here, "the word?", to=key, chat=chat, wait=60)
            (held,) = client.btw.list(here, chat=chat)
            assert (held.aside, held.to) == (answer.aside, key)
            assert held.said == (answer,)
            client.btw.leave(here)
            assert client.btw.list(here, chat=chat) == []
    finally:
        link.close()


def _fenced() -> bool:
    """Whether Ai-chan's confinement can be held here: Seatbelt, or a bubblewrap that starts."""
    if sys.platform == "darwin":
        return True
    try:
        return sys.platform == "linux" and able(BWRAP)[0]
    except OSError:
        return False


def test_ai_chan_is_talked_to_renamed_and_forgotten(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del workspace
    if not _fenced():
        pytest.skip("Ai-chan is held by Seatbelt or bubblewrap, and neither is here")
    if sys.platform == "linux":
        # Landlock cannot keep her off the daemon's socket (Section 14.5.5 of core.md).
        config().mkdir(parents=True, exist_ok=True)
        (config() / "settings.toml").write_text('sandbox = {backend = "bwrap"}\n')
    assert _said(capsys, "ai", "list") == {"conversations": []}

    made = _said(capsys, "ai", "new", "hello there", "--nous", AGENT, "--wait")
    assert made["id"] == 1
    assert made["slot"].startswith("ai:")
    # Briefed with what she was made with, which the stand-in did, and her turn over.
    assert "You are Ai-chan" in made["answer"]
    assert made["mode"] == "listen"

    (one,) = _said(capsys, "ai", "list")["conversations"]
    assert (one["id"], one["title"], one["scope"]) == (1, "hello there", "daemon")
    assert (one["preset"], one["nous"], one["state"]) == ("read-only", AGENT, "waiting")

    assert cli.main(["ai", "say", "1", "and then?"]) == 0
    assert "and then?" in capsys.readouterr().out
    # Nothing new to hear, so what she waits with is what she said last.
    assert "and then?" in _said(capsys, "ai", "wait", "1")["answer"]

    assert cli.main(["ai", "stop", "1"]) == 1
    assert capsys.readouterr().err == (
        "hmz ai stop: Ai-chan is not answering, so there is nothing to stop\n"
    )

    assert _said(capsys, "ai", "rename", "1", "  another   name ") == {
        "id": 1,
        "title": "  another   name ",
    }
    assert cli.main(["ai", "list"]) == 0
    assert capsys.readouterr().out == (
        f"1  waiting  daemon  read-only  {AGENT}  another name\n"
    )

    # Asked of nobody under `--json`, and so not forgotten until told to.
    assert cli.main(["ai", "forget", "1", "--json"]) == 1
    assert "`-y`" in json.loads(capsys.readouterr().out)["error"]["message"]
    assert _said(capsys, "ai", "forget", "1", "--yes") == {"id": 1}
    assert _said(capsys, "ai", "list") == {"conversations": []}
    assert cli.main(["ai", "say", "1", "anyone?"]) == 1
    assert capsys.readouterr().err == "hmz ai say: There is no Ai-chan #1.\n"

    with Client.local() as client:
        again = client.aichan.create("hello again", nous=AGENT)
        assert client.aichan.heard(again.id, wait=120).mode == "listen"
        reply = client.aichan.say(again.id, "one more", wait=120)
        assert reply is not None
        assert "one more" in reply.text
        client.aichan.rename(again.id, "kept")
        assert client.aichan.get(again.id).title == "kept"
        client.aichan.forget(again.id)
        assert client.aichan.list() == []
