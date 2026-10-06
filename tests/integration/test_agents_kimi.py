"""Kimi Code, driven through `KimiCodeCLIAgent` against a stand-in `kimi web` on PATH.

The stand-in is the daemon a Kimi agent drives: it prints the line saying where it listens,
then serves the session REST routes on the loopback -- sessions, profiles, prompts, the status
a turn is polled on, the history it is read back from, and the questions a turn stops on. It
serves no `/ws`, so the driver reads every turn by polling, as it does against a daemon whose
notifications it cannot reach.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import (
    Failed,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    Question,
)
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = KimiCodeCLIAgentConfig(model="kimi-code/stand-in", effort="high")

KIMI = r"""
import itertools, socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer

note()
SESSIONS = itertools.count(1)
PROMPTS = {}
ASKED = {}


def question(session):
    return {"question_id": "q-" + session, "questions": [{
        "id": "which", "header": "Which", "question": "Which way?",
        "options": [{"id": "o-l", "label": "left"}, {"id": "o-r", "label": "right"}]}]}


class Handler(BaseHTTPRequestHandler):
    def reply(self, data, status=200):
        body = json.dumps({"code": 0, "msg": "ok", "data": data}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        sent = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))
                          or b"null")
        path = self.path.removeprefix("/api/v1")
        if path == "/sessions":
            self.reply({"id": "session-%d" % next(SESSIONS)})
            return
        session = path.split("/")[2]
        if path.endswith("/prompts"):
            said = sent["content"][0]["text"]
            note(json.dumps({"session": session, "prompt": said,
                             "thinking": sent.get("thinking")}))
            if said == "refused":
                self.reply(None, status=400)
                return
            PROMPTS[session] = said
            if said == "ask":
                ASKED[session] = question(session)
            self.reply({"prompt_id": "p-1", "user_message_id": "u-1", "status": "running"})
        elif "/questions/" in path:
            note(json.dumps({"session": session, "answered": sent["answers"]}))
            ASKED.pop(session, None)
            PROMPTS[session] = "answered " + json.dumps(sent["answers"], sort_keys=True)
            self.reply({"resolved": True})
        else:
            self.reply({})

    def do_GET(self):
        path, _, query = self.path.removeprefix("/api/v1").partition("?")
        parts = path.split("/")
        if path == "/ws" or len(parts) < 3:
            self.send_error(404, "Not Found")
            return
        session = parts[2]
        said = PROMPTS.get(session, "")
        if path.endswith("/status"):
            self.reply({"busy": session in ASKED})
        elif path.endswith("/questions"):
            self.reply({"items": [ASKED[session]] if session in ASKED else []})
        elif path.endswith("/approvals"):
            self.reply({"items": []})
        elif path.endswith("/messages"):
            if session in ASKED or not said:
                self.reply({"items": []})
                return
            self.reply({"items": [{"id": "m-1", "role": "assistant", "content": [
                {"type": "thinking", "thinking": "thinking about " + said},
                {"type": "tool_use", "tool_name": "Shell"},
                {"type": "text", "text": said}]}]})
        else:
            self.reply({"id": session, "usage": {"input_tokens": 30, "output_tokens": 10,
                                                 "cache_read_tokens": 0,
                                                 "cache_creation_tokens": 0}})

    def log_message(self, *ignored):
        pass


class Server(HTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


server = Server(("127.0.0.1", 0), Handler)
print(f"Kimi server: http://127.0.0.1:{server.server_port}/#token=secret", flush=True)
server.serve_forever()
"""


@pytest.fixture
def kimi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("kimi", KIMI)
    return held


def _prompts(kimi: Standins) -> list[dict[str, Any]]:
    return [
        json.loads(said)
        for said in kimi.said()
        if said.startswith("{") and "prompt" in json.loads(said)
    ]


def test_a_turn_says_what_it_did_and_what_it_spent(kimi: Standins) -> None:
    said = list(KimiCodeCLIAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["reasoning", "tool", "text", "result"]
    assert said[-1].text == "hello"
    assert said[-1].spent.output == 10
    assert dict(said[-1].tokens) == {"kimi-code/stand-in": 40}


def test_one_daemon_holds_the_session_across_turns(kimi: Standins) -> None:
    agent = KimiCodeCLIAgent(CONFIG)
    session = agent.new()

    assert session("one") == "one"
    assert session("two") == "two"

    launch = kimi.calls()[0]
    assert launch.argv[0] == "web"
    assert len({one.pid for one in kimi.calls()}) == 1
    assert [(one["session"], one["prompt"]) for one in _prompts(kimi)] == [
        ("session-1", "one"),
        ("session-1", "two"),
    ]
    assert agent.opened == ["session-1"]


def test_a_question_the_turn_stopped_on_is_put_to_whoever_drives_it(
    kimi: Standins,
) -> None:
    agent = KimiCodeCLIAgent(CONFIG)
    asked: list[Question] = []

    def answers(question: Question) -> str:
        asked.append(question)
        return "right"

    agent.ask = answers

    answered = agent.new()("ask")

    assert [(one.text, one.options) for one in asked] == [
        ("Which way?", ("left", "right"))
    ]
    assert json.loads(answered.removeprefix("answered ")) == {
        "which": {"kind": "single", "option_id": "o-r"}
    }


def test_a_prompt_the_daemon_refuses_is_a_failed_turn_leaving_nothing_open(
    kimi: Standins,
) -> None:
    agent = KimiCodeCLIAgent(CONFIG)
    session = agent.new()

    with pytest.raises(Failed):
        session("refused")
    with pytest.raises(RuntimeError):
        _ = session.id
    assert agent.opened == []
