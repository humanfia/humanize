"""A CLI of your own, driven over the Agent Client Protocol.

The protocol is the whole of what is known about such a backend, so what is checked here is
the conversation: the handshake, the session it opens, the turn it takes on that session, and
the tool call it is asked to permit -- against a stand-in agent that speaks the protocol back.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import AcpAgent, AcpAgentConfig, McpServer, driver

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.coganchor.agents.acp import AcpSession

#: An agent that speaks ACP: it answers the handshake, opens a session, and takes a turn --
#: saying a thought, a tool call it asks permission for, and the answer it ends on. Every
#: message it is sent is written down, so that a test can read the handshake it was given.
#:
#: What the turn does is the prompt's to say, so that one stand-in stands in for every agent
#: there is to drive: `boom` ends on a refusal, `read`, `write` and `run` ask the client for
#: the three things a client can offer, `wait` sits until the turn is cancelled, and anything
#: else is echoed back through a tool call it asks permission for.
_AGENT = """
import json, os, sys

log = os.environ.get("ACP_LOG", "")
version = int(os.environ.get("ACP_VERSION", "1"))
able = json.loads(os.environ.get("ACP_ABLE", '{"loadSession": false}'))
asking = 9000


def out(message):
    print(json.dumps(message), flush=True)


def note(told):
    if log:
        with open(log, "a") as held:
            held.write(json.dumps(told) + "\\n")


def answer(at, result):
    out({"jsonrpc": "2.0", "id": at, "result": result})


def update(session, said):
    out({"jsonrpc": "2.0", "method": "session/update",
         "params": {"sessionId": session, "update": said}})


def ask(method, params):
    global asking
    asking += 1
    out({"jsonrpc": "2.0", "id": asking, "method": method, "params": params})
    while True:
        back = json.loads(sys.stdin.readline())
        note(back)
        if back.get("id") == asking:
            return back


def said_by(back, key):
    held = back.get("result")
    if held is None:
        return "REFUSED " + json.dumps(back.get("error"))
    return json.dumps(held.get(key)) if key else json.dumps(held)


for line in sys.stdin:
    if not line.strip():
        continue
    told = json.loads(line)
    note(told)
    method, at = told.get("method"), told.get("id")
    params = told.get("params") or {}
    if method == "initialize":
        answer(at, {"protocolVersion": version, "agentCapabilities": able,
                    "authMethods": []})
    elif method in ("session/new", "session/fork"):
        answer(at, {"sessionId": "ses-acp-1", "_cwd": params.get("cwd")})
    elif method in ("session/load", "session/resume"):
        answer(at, {})
    elif method == "session/prompt":
        said = params["prompt"][0]["text"]
        session = params["sessionId"]
        update(session, {"sessionUpdate": "agent_thought_chunk",
                         "content": {"type": "text", "text": "thinking about " + said}})
        if said == "boom":
            answer(at, {"stopReason": "refusal"})
        elif said == "wait":
            # Until the client says stop, which it says as a notification rather than as
            # something to answer.
            while True:
                back = json.loads(sys.stdin.readline())
                note(back)
                if back.get("method") == "session/cancel":
                    break
            answer(at, {"stopReason": "cancelled"})
        elif said.startswith("read "):
            back = ask("fs/read_text_file",
                       {"sessionId": session, "path": said[len("read "):]})
            update(session, {"sessionUpdate": "agent_message_chunk",
                             "content": {"type": "text", "text": said_by(back, "content")}})
            answer(at, {"stopReason": "end_turn"})
        elif said.startswith("write "):
            _, path, content = said.split(" ", 2)
            back = ask("fs/write_text_file",
                       {"sessionId": session, "path": path, "content": content})
            update(session, {"sessionUpdate": "agent_message_chunk",
                             "content": {"type": "text", "text": said_by(back, "")}})
            answer(at, {"stopReason": "end_turn"})
        elif said.startswith("run "):
            back = ask("terminal/create",
                       {"sessionId": session, "command": "sh",
                        "args": ["-c", said[len("run "):]]})
            held = (back.get("result") or {}).get("terminalId")
            if held is None:
                update(session, {"sessionUpdate": "agent_message_chunk",
                                 "content": {"type": "text", "text": said_by(back, "")}})
                answer(at, {"stopReason": "end_turn"})
                continue
            ended = ask("terminal/wait_for_exit",
                        {"sessionId": session, "terminalId": held})
            out_ = ask("terminal/output", {"sessionId": session, "terminalId": held})
            ask("terminal/release", {"sessionId": session, "terminalId": held})
            update(session, {"sessionUpdate": "agent_message_chunk",
                             "content": {"type": "text",
                                         "text": said_by(out_, "output").strip('"') +
                                                 " exit " + said_by(ended, "exitCode")}})
            answer(at, {"stopReason": "end_turn"})
        else:
            update(session, {"sessionUpdate": "tool_call", "toolCallId": "call_1",
                             "title": "echo " + said, "kind": "execute",
                             "status": "pending"})
            # The client is asked to permit it, and its answer decides what happens next.
            back = ask("session/request_permission",
                       {"sessionId": session, "toolCall": {"toolCallId": "call_1"},
                        "options": [
                            {"optionId": "no-thanks", "name": "no", "kind": "reject_once"},
                            {"optionId": "go-on", "name": "yes", "kind": "allow_once"}]})
            granted = (back.get("result") or {}).get("outcome", {})
            # Only a grant carries the turn on: a client that picked the first option on
            # offer would have refused it, and the turn says so.
            if granted.get("optionId") != "go-on":
                answer(at, {"stopReason": "refusal"})
                continue
            update(session, {"sessionUpdate": "agent_message_chunk",
                             "content": {"type": "text", "text": said}})
            answer(at, {"stopReason": "end_turn"})
    elif at is not None:
        out({"jsonrpc": "2.0", "id": at,
             "error": {"code": -32601, "message": "no"}})
"""


@pytest.fixture
def added(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Puts a stand-in ACP agent on PATH and writes it down as a CLI of your own."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "my-agent"
    fake.write_text(f"#!{sys.executable}\n{_AGENT}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("ACP_LOG", str(tmp_path / "said.jsonl"))
    backends.remember("my-agent", ["my-agent", "--acp"])
    return "my-agent"


def _told(tmp_path: Path, method: str) -> list[dict[str, Any]]:
    """What the stand-in was sent under one method, in the order it was sent.

    Args:
      tmp_path: The directory the stand-in writes its record in.
      method: The call to pick out.

    Returns:
      The parameters of each, which for the handshake is what this client offered.
    """
    said = (tmp_path / "said.jsonl").read_text().splitlines()
    return [
        cast("dict[str, Any]", json.loads(one).get("params") or {})
        for one in said
        if json.loads(one).get("method") == method
    ]


def _agent(added: str, **held: Any) -> AcpAgent:
    """An agent configured to run the CLI that was added, and whatever else it is given."""
    return AcpAgent(
        AcpAgentConfig(cli=added, model="as configured", effort="as configured", **held)
    )


@pytest.fixture
def session(added: str) -> Iterator[AcpSession]:
    """One conversation on the stand-in agent, ended however the test ends.

    The process is the session here: ACP opens one and holds the agent up between turns, so
    a test that takes a turn and walks away leaves that process running for as long as the
    suite does. Every test below that actually takes one comes through this.
    """
    held = _agent(added).new()
    try:
        yield held
    finally:
        held.close()


def test_an_added_cli_is_written_down_and_read_back(added: str) -> None:
    """It outlives the run: a CLI is installed on a machine, not in one directory."""
    assert backends.speaking()[added] == ("my-agent", "--acp")
    profile = backends.named(added)
    assert profile is not None
    assert profile.name == added
    assert profile in backends.profiles()


def test_an_added_cli_is_driven_over_the_protocol(added: str) -> None:
    """One class drives every CLI anybody adds, since the protocol is all that is known."""
    assert driver(added)[0] is AcpAgent
    assert _agent(added).backend == added


def test_a_name_a_backend_already_answers_to_is_refused(added: str) -> None:
    """Two backends answering to one name is a name nobody can resolve."""
    with pytest.raises(ValueError, match="already a backend"):
        backends.remember("claude", ["claude", "--acp"])


def test_an_added_cli_can_be_taken_away_again(added: str) -> None:
    assert backends.forget(added) is True
    assert backends.speaking() == {}
    assert backends.named(added) is None
    assert backends.forget(added) is False


def test_a_turn_opens_a_session_and_says_what_the_agent_said(
    session: AcpSession,
) -> None:
    """The handshake, the session, and the turn taken on it, in that order."""
    said = list(session.stream("hi"))

    kinds = [event.kind for event in said]
    assert kinds == ["reasoning", "tool", "text", "result"]
    assert said[1].text == "echo hi"
    assert said[-1].text == "hi"
    assert session.id == "ses-acp-1"


def test_the_session_is_held_open_across_turns(session: AcpSession) -> None:
    """ACP opens a conversation once and prompts it many times."""
    assert session("hi") == "hi"
    assert session("again") == "again"
    assert session.id == "ses-acp-1"


def test_a_tool_call_is_permitted_by_the_kind_of_the_option(
    session: AcpSession,
) -> None:
    """Never by its id: one agent calls it `proceed_once` and another `allow-once`.

    The stand-in offers the refusal first and carries the turn on only for the grant, so a
    client that picked whichever option came first would end this turn on a refusal.
    """
    assert session("hi") == "hi"


def test_ending_a_conversation_ends_the_agent_that_was_holding_it(added: str) -> None:
    """The process is the session, so a conversation let go of is a process left running."""
    held = _agent(added).new()
    assert held("hi") == "hi"
    link = held._link
    assert link is not None
    running = link.proc
    assert running is not None
    assert running.poll() is None

    held.close()

    assert running.wait(timeout=10) is not None
    assert held._link is None


def test_a_conversation_closed_twice_is_not_a_second_thing_to_end(added: str) -> None:
    held = _agent(added).new()
    assert held("hi") == "hi"

    held.close()
    held.close()  # the absence of a raised error is the whole assertion


def test_a_conversation_dropped_without_a_turn_in_it_never_started(added: str) -> None:
    """Nothing is spawned until the first turn, so there is nothing to end either."""
    held = _agent(added).new()

    held.close()

    assert held._link is None


def test_a_turn_that_ended_on_a_refusal_is_a_failed_turn(added: str) -> None:
    """A stop reason that is not an answer must not come back as one."""
    with pytest.raises(subprocess.CalledProcessError) as raised:
        _agent(added).new()("boom")
    assert "refusal" in str(raised.value.stderr)


def test_an_added_cli_cannot_be_steered_mid_turn(added: str) -> None:
    """Steering is an extension each agent spells its own way."""
    with pytest.raises(NotImplementedError):
        _agent(added).new().interject("hello?")


def test_an_agent_with_no_command_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A CLI that was never added is a name nothing knows how to start."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    with pytest.raises(ValueError, match="no command to start it with"):
        _ = AcpAgent(AcpAgentConfig(cli="nobody", model="m", effort="e")).command


def test_an_added_cli_is_called_what_it_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A backend answers to the command that CLI registers, and an added one too.

    Which is the rule everything humanize drives already keeps -- `claude` is `claude` -- and
    the one thing an added CLI could break, since the name was somebody's to choose.
    """
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))

    with pytest.raises(ValueError, match="added as frank rather than as ernie"):
        backends.remember("ernie", ["frank", "--acp"])
    # Blank is the name it would have been given anyway, and a command written as a path is
    # still called what it is installed as.
    assert backends.remember("", ["frank", "--acp"]) == "frank"
    assert backends.remember("thing", ["/opt/thing/bin/thing", "acp"]) == "thing"
    assert backends.speaking() == {
        "frank": ("frank", "--acp"),
        "thing": ("/opt/thing/bin/thing", "acp"),
    }
    with pytest.raises(ValueError, match="a command to start it with"):
        backends.remember("nothing", [])


def test_a_cli_written_down_under_another_name_is_still_read_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A list written before the rule is a list of CLIs that work.

    A machine where every added backend stopped resolving would be a worse thing than one
    name being wrong, so what is already written is read as it stands, and corrected by being
    written again.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HUMANIZE_HOME", str(home))
    (home / "acp.json").write_text(json.dumps({"ernie": ["frank", "--acp"]}))

    assert backends.speaking() == {"ernie": ("frank", "--acp")}
    assert backends.named("ernie") is not None
    assert backends.forget("ernie") is True


def test_the_handshake_offers_nothing_until_something_asks(
    added: str, tmp_path: Path
) -> None:
    """The agent has a machine of its own to read files and run commands on."""
    _agent(added).new()("hi")

    (hello,) = _told(tmp_path, "initialize")
    assert hello["protocolVersion"] == 1
    assert hello["clientCapabilities"] == {
        "fs": {"readTextFile": False, "writeTextFile": False},
        "terminal": False,
    }
    # And nothing is handed to the agent that the CLI is not already configured with.
    (opened,) = _told(tmp_path, "session/new")
    assert opened["mcpServers"] == []


def test_what_the_client_offers_is_what_it_was_asked_for(
    added: str, tmp_path: Path
) -> None:
    """Each of the three the protocol names, said in the handshake rather than assumed."""
    _agent(added, reads_files=True, writes_files=True, terminals=True).new()("hi")

    (hello,) = _told(tmp_path, "initialize")
    assert hello["clientCapabilities"] == {
        "fs": {"readTextFile": True, "writeTextFile": True},
        "terminal": True,
    }


def test_a_file_is_read_for_the_agent_that_asked_for_it(
    added: str, tmp_path: Path
) -> None:
    """A capability declared and then refused where it was asked would be worse than none."""
    at = tmp_path / "read-me.txt"
    at.write_text("one\ntwo\nthree\n")

    assert "two" in _agent(added, reads_files=True).new()(f"read {at}")
    # And not by an agent this client offered nothing to, which is told so instead.
    assert "REFUSED" in _agent(added).new()(f"read {at}")


def test_a_file_is_written_for_the_agent_that_asked_for_it(
    added: str, tmp_path: Path
) -> None:
    at = tmp_path / "made" / "written.txt"

    _agent(added, writes_files=True).new()(f"write {at} hello")

    assert at.read_text() == "hello"  # directories and all


def test_a_file_that_is_not_text_is_refused_rather_than_ending_the_turn(
    added: str, tmp_path: Path
) -> None:
    """This call is for text, and one bad path is not a turn to throw away."""
    at = tmp_path / "picture.bin"
    at.write_bytes(b"\xff\xfe\x00not text at all")

    assert "REFUSED" in _agent(added, reads_files=True).new()(f"read {at}")


def test_a_command_is_run_and_held_for_the_agent_that_asked_for_one(added: str) -> None:
    """Started, read while it runs, waited for, and let go of."""
    said = _agent(added, terminals=True).new()("run echo 4711; exit 3")

    assert "4711" in said
    assert "exit 3" in said


def test_a_command_that_says_a_lot_is_read_to_the_end_before_it_is_said_to_have_ended(
    added: str,
) -> None:
    """The exit status is what tells the agent the log is whole, so it waits for the log."""
    said = _agent(added, terminals=True).new()("run seq 1 20000")

    assert "20000" in said
    assert "exit 0" in said


def test_an_agent_that_speaks_a_newer_protocol_is_not_spoken_to(
    added: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent answers with the version it will speak, which is the lower of the two."""
    monkeypatch.setenv("ACP_VERSION", "99")

    with pytest.raises(subprocess.CalledProcessError) as raised:
        _agent(added).new()("hi")

    assert "version 99" in str(raised.value.stderr)


def test_the_mcp_servers_a_flow_names_are_handed_over(
    added: str, tmp_path: Path
) -> None:
    """On top of whatever the CLI is already configured with, which is untouched."""
    _agent(
        added,
        mcp_servers=(
            McpServer(
                name="tools",
                command="serve-me",
                args=("--at", "here"),
                env=(("A", "1"),),
            ),
        ),
    ).new()("hi")

    (opened,) = _told(tmp_path, "session/new")
    assert opened["mcpServers"] == [
        {
            "name": "tools",
            "command": "serve-me",
            "args": ["--at", "here"],
            "env": [{"name": "A", "value": "1"}],
        }
    ]


def test_a_server_that_could_not_be_started_is_refused_where_it_is_written(
    added: str,
) -> None:
    """Rather than by an agent refusing a session hours later."""
    with pytest.raises(ValueError, match="needs a name and a command"):
        _agent(added, mcp_servers=(McpServer(name="tools", command=" "),))


def test_an_added_cli_cannot_be_allowed_less_than_everything(added: str) -> None:
    """The protocol's only word about permission is a question nobody here is at.

    So every tool call is granted, and a rung that says otherwise is said where the agent is
    made rather than quietly run as the rung above it.
    """
    with pytest.raises(ValueError, match="permission must be 'bypass'"):
        _agent(added, permission="read-only")


def test_a_conversation_is_picked_back_up_on_the_next_process(
    added: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ACP session outlives the process that opened it, where the agent says it does."""
    monkeypatch.setenv(
        "ACP_ABLE",
        json.dumps({"loadSession": True, "sessionCapabilities": {"resume": {}}}),
    )
    held = _agent(added).new()
    assert held("hi") == "hi"
    held._shut()  # the agent put down, as a watchdog puts one down

    assert held("again") == "again"

    (asked,) = _told(tmp_path, "session/resume")
    assert asked["sessionId"] == "ses-acp-1"
    assert held.id == "ses-acp-1"


def test_an_agent_that_cannot_pick_one_back_up_says_so_rather_than_starting_again(
    added: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn taken from nothing is a flow going round on a conversation that forgot it."""
    monkeypatch.setenv("ACP_ABLE", json.dumps({"loadSession": False}))
    held = _agent(added).new()
    assert held("hi") == "hi"
    held._shut()

    with pytest.raises(subprocess.CalledProcessError) as raised:
        held("again")

    assert "session/resume" in str(raised.value.stderr)


def test_a_turn_is_cut_off_by_the_protocols_own_word_for_it(added: str) -> None:
    """`session/cancel`, so that the conversation is still there to take the next turn."""
    held = _agent(added).new()
    assert held("hi") == "hi"
    answered: list[str] = []

    turn = threading.Thread(target=lambda: answered.append(held("wait")))
    turn.start()
    while not held._working:  # it has to have started to be cut off
        time.sleep(0.01)
    held.interrupt(why="the watchdog says so")
    turn.join(timeout=30)

    assert not turn.is_alive()
    assert answered == [""]
    assert held._link is not None  # cancelled rather than thrown away


@pytest.mark.agent
@pytest.mark.timeout(900)
def test_a_real_acp_server_is_added_and_driven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One real ACP server, added as a CLI of your own and taken a turn on.

    The stand-in above prints the protocol; this is the protocol. What only the real thing can
    confirm is what the handshake actually negotiates, that a turn lands through the catch-all
    driver, and that the conversation is still there for the turn after it -- which for this
    backend means the session was picked back up rather than opened again.
    """
    if shutil.which("opencode") is None:
        pytest.skip("opencode is not installed here")
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    # Under a command of its own, because `opencode` is a backend humanize drives and an
    # added CLI answers to what it runs: what is being driven here is the protocol, and a
    # real server behind a name of its own is a CLI of your own in every way that matters.
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "zen-acp").write_text("#!/bin/sh\nexec opencode acp\n")
    (binaries / "zen-acp").chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    assert backends.remember("", ["zen-acp"]) == "zen-acp"

    session = _agent("zen-acp").new()
    said = list(session.stream("Remember the number 4711. Reply with exactly: OK"))

    assert said[-1].kind == "result"
    assert "OK" in said[-1].text
    assert session.id  # and names the session the turn landed in
    assert "4711" in session("What number did I ask you to remember? Digits only.")
    # And it outlives the process that held it: the agent is put down as a watchdog puts one
    # down, and the next turn picks the same conversation back up rather than starting one.
    session._shut()
    assert "4711" in session("Say that number again. Digits only.")
