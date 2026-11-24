"""`hmz chat`, asked of a real daemon, with the stand-in `claude` answering each turn.

Every line here is the command itself (`hmz.cli.main`) reaching this machine's daemon over its
socket: the chat started on a host of its own, its turn followed and its answer printed, and
the chat then written down for `list`, `show`, `rename`, `fork`, `archive` and `delete` to
find by its id. The same is then asked through `hmz.sdk.Client.chats`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli
from hmz.sdk import Client, Refused
from tests.integration.doubles_core import AGENT, MODEL, install, started

if TYPE_CHECKING:
    from pathlib import Path

#: Every chat here is held by a daemon of the test's own, in this process.
pytestmark = [pytest.mark.timeout(180), pytest.mark.usefixtures("daemon")]


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return install(tmp_path, monkeypatch)


def _json(capsys: pytest.CaptureFixture[str], *argv: str, status: int = 0) -> Any:
    """Runs one `hmz chat` line under `--json`, and answers with its one document."""
    assert cli.main(["chat", *argv, "--json"]) == status
    said = capsys.readouterr()
    assert said.err == ""
    return json.loads(said.out)


def _begun(capsys: pytest.CaptureFixture[str], message: str = "hello there") -> str:
    """A chat started with one message, by its id."""
    return str(_json(capsys, "start", "-a", AGENT, message)["chat"])


def test_start_answers_one_turn_on_stdout_and_works_in_the_project(
    tmp_path: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["chat", "start", "-a", f"{AGENT}:high", "hello there"]) == 0

    said = capsys.readouterr()
    assert said.out.strip() == "did: hello there"
    assert said.err.startswith("Chat 2")
    (start,) = started(tmp_path)
    assert start["cwd"] == str(project.resolve())
    assert start["argv"][start["argv"].index("--model") + 1] == MODEL
    assert start["argv"][start["argv"].index("--effort") + 1] == "high"
    assert (project / "landed.txt").read_text() == "hello there\n"
    # Written down as a chat of this directory, by the id it said.
    chat = said.err.splitlines()[0].removeprefix("Chat ")
    assert cli.main(["chat", "list"]) == 0
    assert capsys.readouterr().out == f"{chat}  resting  hello there\n"


def test_say_carries_the_chat_on_in_its_own_conversation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _json(capsys, "start", "-a", AGENT, "hello")
    assert (first["answer"], first["detached"], first["notes"]) == (
        "did: hello",
        False,
        [],
    )

    then = _json(capsys, "say", first["chat"], "and then?")

    assert (then["chat"], then["answer"]) == (first["chat"], "did: and then?")
    # The same conversation, carried on from where the first turn left it.
    first_start, then_start = started(tmp_path)
    assert (
        then_start["argv"][then_start["argv"].index("--resume") + 1]
        == first_start["session"]
    )
    shown = _json(capsys, "show", first["chat"], "--trace")
    assert (shown["id"], shown["task"], shown["state"]) == (
        first["chat"],
        "hello",
        "resting",
    )
    assert any(
        action["name"] == "say: did: and then?"
        for session in shown["trace"]
        for action in session["actions"]
    )


def test_events_are_the_turns_records_and_then_the_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["chat", "start", "--events", "-a", AGENT, "hello"]) == 0

    said = capsys.readouterr()
    assert said.err == ""
    *records, last = (json.loads(line) for line in said.out.splitlines())
    assert [one["seq"] for one in records] == sorted(one["seq"] for one in records)
    assert records[0]["type"] == "started"
    assert any(
        (one["type"], one.get("kind"), one.get("text"))
        == ("event", "result", "did: hello")
        for one in records
    )
    assert (last["answer"], last["detached"]) == ("did: hello", False)


def test_a_shell_line_prints_what_it_printed_and_takes_no_turn(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["chat", "start", "-a", AGENT, "--", "!echo hi-from-bang"]) == 0

    said = capsys.readouterr()
    assert said.out == "hi-from-bang\n"
    assert "echo hi-from-bang" in said.err
    assert started(tmp_path) == []


def test_a_failed_turn_exits_one_with_what_the_harness_said(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["chat", "start", "-a", AGENT, "fail: it broke"]) == 1
    assert "it broke" in capsys.readouterr().err.splitlines()[-1]

    failed = _json(capsys, "start", "-a", AGENT, "fail: it broke", status=1)
    assert "it broke" in failed["error"]["message"]
    assert _json(capsys, "show", failed["chat"])["state"] == "failed"


def test_the_agent_is_the_one_remembered_where_none_is_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["chat", "start", "hello"]) == 1
    assert capsys.readouterr().err == (
        "hmz chat start: No agent is remembered for this folder; name one with `-a`.\n"
    )
    assert not started(tmp_path)

    _json(capsys, "start", "--remember", "-a", AGENT, "hello")

    assert _json(capsys, "start", "hello again")["answer"] == "did: hello again"


def test_a_chat_is_renamed_forked_archived_and_deleted_by_its_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    chat = _begun(capsys)

    assert cli.main(["chat", "rename", chat, "the   parser"]) == 0
    assert capsys.readouterr().out == f"{chat}  resting  the parser\n"
    fork = _json(capsys, "fork", chat)["chat"]
    assert fork != chat
    assert _json(capsys, "show", fork)["forked"] == chat
    assert _json(capsys, "say", fork, "on the fork")["answer"] == "did: on the fork"

    assert _json(capsys, "archive", fork)["archived"] is True
    assert [one["id"] for one in _json(capsys, "list")["chats"]] == [chat]
    assert [one["id"] for one in _json(capsys, "list", "--archived")["chats"]] == [fork]
    assert _json(capsys, "unarchive", fork)["archived"] is False
    assert _json(capsys, "list", "-q", "parser")["total"] == 2

    # Nobody is at a terminal here, so nothing is asked and nothing deleted without a yes.
    assert cli.main(["chat", "delete", fork]) == 1
    assert "`-y`" in capsys.readouterr().err
    assert _json(capsys, "delete", "--yes", fork) == {"deleted": fork}
    assert _json(capsys, "show", fork, status=1) == {
        "error": {"code": 404, "message": f"There is no chat {fork}."}
    }


def test_a_chat_is_set_and_asked_what_its_lines_start_with_where_it_rests(
    capsys: pytest.CaptureFixture[str],
) -> None:
    chat = _begun(capsys)

    said = _json(capsys, "set", chat, "--permission", "read-only", "--prefer", "flow")

    assert said == {
        "chat": chat,
        "permission": "read-only",
        "prefer": "flow",
        "prefer_from": "chat",
    }
    found = _json(capsys, "commands", chat)
    assert {"sigil": "/", "name": "clear", "about": "", "how": "", "source": "hmz"} in (
        found["entries"]
    )
    assert (found["prefer"], found["permission"]) == ("flow", "read-only")
    # Held now, between turns, with no turn to stop.
    assert cli.main(["chat", "stop", chat]) == 1
    assert capsys.readouterr().err == (
        "hmz chat stop: no turn is open, so there is nothing to stop\n"
    )
    agent = _json(capsys, "agent", chat, f"{AGENT}:high")
    assert agent["agent"] == f"{AGENT}:high"
    assert cli.main(["chat", "agent", chat, "codex/gpt-5"]) == 1
    assert "a chat keeps its harness" in capsys.readouterr().err


def test_a_line_hmz_keeps_is_refused_of_a_chat_in_the_daemons_words(
    capsys: pytest.CaptureFixture[str],
) -> None:
    chat = _begun(capsys)

    assert cli.main(["chat", "say", chat, "/clear"]) == 1

    assert capsys.readouterr().err == (
        "hmz chat say: /clear is served by the frontend, not said to the chat\n"
    )


def test_a_chat_of_no_folder_works_in_a_directory_made_for_it(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    said = _json(capsys, "start", "--no-folder", "-a", AGENT, "hello")

    assert said["answer"] == "did: hello"
    assert said["workspace"] != str(project.resolve())
    assert _json(capsys, "show", said["chat"])["folderless"] is True
    # A chat of no folder is no chat of this one.
    assert _json(capsys, "list")["chats"] == []


def test_detached_the_turn_goes_on_and_is_read_afterwards(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["chat", "start", "--detach", "-a", AGENT, "hello"]) == 0
    chat = capsys.readouterr().out.strip()

    # The turn it left going is waited out first: a line said while a turn is open is handed
    # into that turn, and what is answered then is that turn's.
    with Client.local() as client:
        held = client.chats.hold(chat)
        with client.chats.follow(held.workspace, held.slot) as turn:
            assert turn.wait() == "did: hello"

    # Said to the host that still holds it, which the turn before has left between turns.
    assert _json(capsys, "say", chat, "and then?")["answer"] == "did: and then?"
    assert _json(capsys, "show", chat)["state"] == "going"


def test_a_folder_with_no_harness_session_lists_none_and_adopts_none(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _json(capsys, "harness", "list") == {
        "sessions": [],
        "total": 0,
        "offset": 0,
        "limit": 50,
    }
    refused = _json(capsys, "harness", "adopt", "claude", "nope", status=1)
    assert refused["error"]["code"] == 404
    assert cli.main(["chat", "backup", "nope"]) == 1
    assert capsys.readouterr().err == "hmz chat backup: There is no chat nope.\n"


def test_the_same_is_asked_through_the_sdk(project: Path) -> None:
    at = str(project.resolve())
    with Client.local() as client:
        chats = client.chats
        begun = chats.start(at, "hello", agent=AGENT)
        with chats.follow(begun.workspace, begun.slot) as turn:
            heard = [message["type"] for message in turn]
        assert (turn.answer, turn.done, turn.failed) == ("did: hello", True, "")
        assert {"welcome", "started", "event", "run"} <= set(heard)

        with chats.ask(begun.chat, "and then?") as turn:
            assert turn.wait() == "did: and then?"

        held = chats.hold(begun.chat)
        assert (held.workspace, held.slot) == (at, turn.slot)
        chats.set(held.workspace, held.slot, permission="read-only")
        assert chats.commands(held.workspace, held.slot).permission == "read-only"
        with pytest.raises(Refused, match="nothing to stop"):
            chats.stop(held.workspace, held.slot)
        # An empty line ends the chat on its host, which then holds it no longer.
        assert chats.rest(begun.chat)
        assert chats.get(begun.chat).slot == ""

        assert chats.rename(begun.chat, "the parser").title == "the parser"
        (listed,) = chats.list(workspace=at).chats
        assert (listed.id, listed.title) == (begun.chat, "the parser")
        fork = chats.fork(begun.chat)
        assert chats.get(fork).said["forked"] == begun.chat
        assert chats.archive(fork).archived
        assert [one.id for one in chats.list(workspace=at, archived=True).chats] == [
            fork
        ]
        chats.delete(fork)
        with pytest.raises(Refused) as refused:
            chats.get(fork)
        assert refused.value.code == 404
        assert chats.harness.list(at).sessions == ()
        assert chats.remembered(at) == ""
