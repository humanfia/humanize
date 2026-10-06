"""A CLI of somebody's own, added to humanize and driven over the Agent Client Protocol.

The stand-in is `my-agent --acp`, written down with `backends.remember` as any CLI a person
adds: it answers the handshake, opens a session, and plays a `session/prompt` as
`session/update` notifications -- asking the client for permission, a file or a terminal where
the prompt says to -- ending on the stop reason the prompt chooses.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import (
    AcpAgent,
    AcpAgentConfig,
    Failed,
    Moment,
    Unhooked,
    driver,
)
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.coganchor.agents import AcpSession

ACP = r"""
asking = [9000]


def answer(at, result):
    out({"jsonrpc": "2.0", "id": at, "result": result})


def update(session, **said):
    out({"jsonrpc": "2.0", "method": "session/update",
         "params": {"sessionId": session, "update": said}})


def say(session, text):
    update(session, sessionUpdate="agent_message_chunk",
           content={"type": "text", "text": text})


def ask(method, params):
    asking[0] += 1
    out({"jsonrpc": "2.0", "id": asking[0], "method": method, "params": params})
    while True:
        back = json.loads(sys.stdin.readline())
        if back.get("id") == asking[0]:
            return back


note()
for line in sys.stdin:
    if not line.strip():
        continue
    told = json.loads(line)
    method, at = told.get("method"), told.get("id")
    params = told.get("params") or {}
    if method != "session/prompt":
        note(method + " " + json.dumps(params, sort_keys=True))
    if method == "initialize":
        answer(at, {"protocolVersion": 1, "agentCapabilities": {"loadSession": False},
                    "authMethods": []})
    elif method == "session/new":
        answer(at, {"sessionId": "ses-acp-1"})
    elif method == "session/prompt":
        said = params["prompt"][0]["text"]
        note(said)
        session = params["sessionId"]
        update(session, sessionUpdate="agent_thought_chunk",
               content={"type": "text", "text": "thinking about " + said})
        if said == "unfinished":
            answer(at, {"stopReason": "refusal"})
        elif said == "crash":
            print("my-agent: something broke", file=sys.stderr, flush=True)
            sys.exit(3)
        elif said == "wait":
            while (back := json.loads(sys.stdin.readline())).get("method") != "session/cancel":
                pass
            note("cancelled")
            answer(at, {"stopReason": "cancelled"})
        elif said.startswith("read "):
            back = ask("fs/read_text_file", {"sessionId": session, "path": said[5:]})
            say(session, json.dumps(back.get("result") or back.get("error")))
            answer(at, {"stopReason": "end_turn"})
        elif said.startswith("run "):
            made = ask("terminal/create", {"sessionId": session, "command": "sh",
                                           "args": ["-c", said[4:]]})
            held = made["result"]["terminalId"]
            ended = ask("terminal/wait_for_exit", {"sessionId": session, "terminalId": held})
            output = ask("terminal/output", {"sessionId": session, "terminalId": held})
            ask("terminal/release", {"sessionId": session, "terminalId": held})
            say(session, output["result"]["output"].strip() + " exit " +
                str(ended["result"]["exitCode"]))
            answer(at, {"stopReason": "end_turn"})
        else:
            update(session, sessionUpdate="tool_call", toolCallId="call_1",
                   title="echo " + said, kind="execute", status="pending",
                   rawInput={"command": "echo " + said})
            back = ask("session/request_permission", {
                "sessionId": session,
                "toolCall": {"toolCallId": "call_1", "title": "echo " + said,
                             "rawInput": {"command": "echo " + said}},
                "options": [{"optionId": "no-thanks", "name": "no", "kind": "reject_once"},
                            {"optionId": "go-on", "name": "yes", "kind": "allow_once"}]})
            chosen = (back.get("result") or {}).get("outcome", {}).get("optionId")
            if chosen != "go-on":
                answer(at, {"stopReason": "refusal"})
                continue
            say(session, said)
            answer(at, {"stopReason": "end_turn",
                        "usage": {"inputTokens": 9, "outputTokens": 4, "totalTokens": 13}})
    elif at is not None:
        out({"jsonrpc": "2.0", "id": at, "error": {"code": -32601, "message": "no"}})
"""


@pytest.fixture
def acp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("my-agent", ACP)
    backends.remember("my-agent", ["my-agent", "--acp"])
    return held


def _agent(**held: Any) -> AcpAgent:
    return AcpAgent(AcpAgentConfig(cli="my-agent", model="m", effort="e", **held))


@pytest.fixture
def session(acp: Standins) -> Iterator[AcpSession]:
    held = _agent().new()
    try:
        yield held
    finally:
        held.close()


def _told(acp: Standins, method: str) -> list[dict[str, Any]]:
    return [
        json.loads(said.removeprefix(method + " "))
        for said in acp.said()
        if said.startswith(method + " ")
    ]


def test_an_added_cli_is_driven_by_the_protocol_s_own_driver(acp: Standins) -> None:
    assert backends.speaking()["my-agent"] == ("my-agent", "--acp")
    assert driver("my-agent")[0] is AcpAgent
    assert _agent().backend == "my-agent"


def test_a_turn_opens_a_session_and_says_what_the_agent_said(
    acp: Standins, session: AcpSession
) -> None:
    said = list(session.stream("hello"))

    assert kinds(said) == ["reasoning", "tool", "text", "result"]
    assert said[1].text == "echo hello"
    assert said[-1].text == "hello"
    assert session.id == "ses-acp-1"
    (launch,) = (one for one in acp.calls() if not one.stdin)
    assert launch.argv == ["--acp"]
    assert len(_told(acp, "initialize")) == 1


def test_the_session_is_held_open_across_turns(
    acp: Standins, session: AcpSession
) -> None:
    assert session("one") == "one"
    assert session("two") == "two"

    assert len({one.pid for one in acp.calls()}) == 1
    assert len(_told(acp, "session/new")) == 1


def test_a_permission_is_granted_by_the_kind_of_option_not_its_place(
    session: AcpSession,
) -> None:
    # The refusal is offered first: a client taking whichever came first would end on it.
    assert session("hello") == "hello"


def test_a_moment_the_protocol_does_not_run_is_refused_where_it_is_hung(
    acp: Standins,
) -> None:
    with pytest.raises(Unhooked):
        _agent().hooks.on(Moment.PERMISSION_REQUEST, lambda _: None)


def test_a_client_that_was_asked_to_serves_files_and_terminals(
    acp: Standins, tmp_path: Path
) -> None:
    (tmp_path / "notes.txt").write_text("hello from the file")
    session = _agent(reads_files=True, terminals=True).new()
    try:
        read = json.loads(session(f"read {tmp_path / 'notes.txt'}"))
        ran = session("run echo ran; exit 4")
    finally:
        session.close()

    assert read == {"content": "hello from the file"}
    assert ran == "ran exit 4"
    (offered,) = _told(acp, "initialize")
    assert offered["clientCapabilities"]["terminal"] is True


def test_a_client_nobody_asked_to_serves_no_file(
    acp: Standins, session: AcpSession, tmp_path: Path
) -> None:
    (tmp_path / "notes.txt").write_text("hello from the file")

    refused = json.loads(session(f"read {tmp_path / 'notes.txt'}"))

    assert "hello from the file" not in json.dumps(refused)


def test_a_turn_ending_on_a_refusal_is_a_failed_turn(session: AcpSession) -> None:
    with pytest.raises(Failed, match="refusal"):
        session("unfinished")


def test_an_agent_that_exits_mid_turn_fails_it(session: AcpSession) -> None:
    with pytest.raises(Failed):
        session("crash")


def test_a_turn_cut_off_is_cancelled_over_the_protocol(
    acp: Standins, session: AcpSession
) -> None:
    ended: list[BaseException] = []

    def runs() -> None:
        try:
            session("wait")
        except Exception as failed:  # noqa: BLE001 -- however it ended is the answer
            ended.append(failed)

    turn = threading.Thread(target=runs)
    turn.start()
    while "wait" not in acp.said():
        turn.join(0.05)
    session.cut(why="the flow moved on")
    turn.join(30)

    assert not turn.is_alive()
    assert "cancelled" in acp.said()
