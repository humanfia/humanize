"""An added CLI that speaks the Agent Client Protocol: the handshake, the turn, the asking.

The agent is a scripted process answering the JSON-RPC the driver writes -- `initialize`,
`session/new`, `session/prompt` -- with what a test hands it, and asking the client things on
the way, so what is checked is what the client says, serves and refuses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import backends, fence
from hmz.coganchor.agents import (
    AcpAgent,
    AcpAgentConfig,
    AcpSession,
    Failed,
    McpServer,
    Unfenced,
    Unserved,
)
from hmz.coganchor.agents.acp import UNSAID, AcpConnection
from hmz.coganchor.fence import Fence
from tests.unit.coganchor.agents.doubles_u4 import Process, Spawner, fenceable

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

type _Answer = Callable[[Process, int, dict[str, Any]], None]


#: What every agent here is made with unless a test says otherwise.
_DEFAULTS: dict[str, Any] = {
    "model": UNSAID,
    "effort": "",
    "cli": "mine",
    "command": ("my-acp", "--stdio"),
}


def _update(session: str, **update: Any) -> dict[str, Any]:
    return {
        "method": "session/update",
        "params": {"sessionId": session, "update": update},
    }


def _chunk(
    session: str, text: str, kind: str = "agent_message_chunk"
) -> dict[str, Any]:
    return _update(session, sessionUpdate=kind, content={"type": "text", "text": text})


def _ends(why: str = "end_turn") -> _Answer:
    """A turn that answers at once."""

    def answer(proc: Process, ident: int, params: dict[str, Any]) -> None:
        proc.say(
            _chunk(params["sessionId"], "done"),
            {"id": ident, "result": {"stopReason": why}},
        )

    return answer


class _Agent:
    """What the scripted ACP agent answers, and every request it was sent."""

    def __init__(self, spawner: Spawner) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.replies: list[dict[str, Any]] = []
        self.hello: dict[str, Any] = {"protocolVersion": 1, "agentCapabilities": {}}
        self.turns: list[_Answer] = []
        self.refusing: dict[str, dict[str, Any]] = {}
        self._opened = 0
        spawner.replying(self._heard)

    def _heard(self, proc: Process, said: Any) -> None:
        method, ident = said.get("method"), said.get("id")
        if method is None:
            self.replies.append(said)
            return
        params: dict[str, Any] = said.get("params") or {}
        self.calls.append((method, params))
        if ident is None:
            return
        if (refused := self.refusing.pop(method, None)) is not None:
            proc.say({"id": ident, "error": refused})
        elif method == "initialize":
            proc.say({"id": ident, "result": self.hello})
        elif method in ("session/new", "session/fork"):
            self._opened += 1
            proc.say({"id": ident, "result": {"sessionId": f"s-{self._opened}"}})
        elif method == "session/prompt":
            (self.turns.pop(0) if self.turns else _ends())(proc, ident, params)
        else:
            proc.say({"id": ident, "result": {}})

    def called(self, method: str) -> list[dict[str, Any]]:
        return [params for named, params in self.calls if named == method]

    def replied(self, ident: int) -> dict[str, Any]:
        (reply,) = [one for one in self.replies if one.get("id") == ident]
        return reply


@pytest.fixture
def spawner(monkeypatch: pytest.MonkeyPatch) -> Spawner:
    """Every process a turn asks for, scripted rather than started."""
    return Spawner(monkeypatch)


@pytest.fixture
def acp(spawner: Spawner) -> _Agent:
    """The scripted agent."""
    return _Agent(spawner)


def _agent(**given: Any) -> AcpAgent:
    return AcpAgent(AcpAgentConfig(**_DEFAULTS | given))


def _asks(method: str, params: dict[str, Any], then: _Answer | None = None) -> _Answer:
    """A turn that asks the client something under id 50 first."""

    def answer(proc: Process, ident: int, prompt: dict[str, Any]) -> None:
        proc.say(
            {
                "id": 50,
                "method": method,
                "params": {"sessionId": prompt["sessionId"]} | params,
            }
        )
        (then or _ends())(proc, ident, prompt)

    return answer


def test_the_connection_writes_one_message_a_line(
    spawner: Spawner, tmp_path: Path
) -> None:
    spawner.script = lambda proc: proc.say(
        "", "not json", "[1]", {"id": 1, "result": {}}
    )
    link = AcpConnection(argv=["agent", "--acp"], environ={"A": "1"}, cwd=str(tmp_path))
    link.start()
    link.start()
    (proc,) = spawner.started
    assert (proc.args, proc.env, proc.cwd) == (
        ["agent", "--acp"],
        {"A": "1"},
        str(tmp_path),
    )
    assert link.send("go", {"x": 1}) == 1
    assert link.send("go", {}) == 2
    link.notify("note", {})
    link.reply(7)
    link.reply(8, {"ok": True})
    link.refuse(9, "no", -32603)
    assert proc.stdin is not None
    assert proc.stdin.said == [
        {"jsonrpc": "2.0", "id": 1, "method": "go", "params": {"x": 1}},
        {"jsonrpc": "2.0", "id": 2, "method": "go", "params": {}},
        {"jsonrpc": "2.0", "method": "note", "params": {}},
        {"jsonrpc": "2.0", "id": 7, "result": None},
        {"jsonrpc": "2.0", "id": 8, "result": {"ok": True}},
        {"jsonrpc": "2.0", "id": 9, "error": {"code": -32603, "message": "no"}},
    ]
    assert link.read() == {"id": 1, "result": {}}
    link.stop()
    assert link.proc is None
    assert proc.stdin.closed
    assert link.read() is None


def test_the_handshake_offers_nothing_unasked_and_opens_a_session(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    server = McpServer(name="tools", command="serve", args=("-v",), env=(("K", "V"),))
    session = _agent(mcp_servers=(server,)).new(tmp_path)
    assert isinstance(session, AcpSession)
    assert session("hi") == "done"
    proc = spawner.last
    assert proc.args == ["my-acp", "--stdio"]
    assert proc.cwd == str(tmp_path)
    (hello,) = acp.called("initialize")
    assert hello["protocolVersion"] == 1
    assert hello["clientCapabilities"] == {
        "fs": {"readTextFile": False, "writeTextFile": False},
        "terminal": False,
    }
    (opened,) = acp.called("session/new")
    assert opened == {
        "cwd": str(tmp_path),
        "mcpServers": [
            {
                "name": "tools",
                "command": "serve",
                "args": ["-v"],
                "env": [{"name": "K", "value": "V"}],
            }
        ],
    }
    (prompt,) = acp.called("session/prompt")
    assert prompt == {"sessionId": "s-1", "prompt": [{"type": "text", "text": "hi"}]}
    assert session.id == "s-1"


def test_a_second_turn_is_the_same_process_and_session(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    session = _agent().new(tmp_path)
    session("one")
    session("two")
    assert len(spawner.started) == 1
    assert len(acp.called("session/new")) == 1
    assert [one["sessionId"] for one in acp.called("session/prompt")] == ["s-1", "s-1"]


def test_what_the_agent_offers_is_what_a_client_asked_for(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    _agent(reads_files=True, writes_files=True, terminals=True).new(tmp_path)("hi")
    (hello,) = acp.called("initialize")
    assert hello["clientCapabilities"] == {
        "fs": {"readTextFile": True, "writeTextFile": True},
        "terminal": True,
    }


def test_chunks_are_gathered_into_what_was_said(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    def turn(proc: Process, ident: int, params: dict[str, Any]) -> None:
        held = params["sessionId"]
        proc.say(
            _chunk(held, "let me ", "agent_thought_chunk"),
            _chunk(held, "look", "agent_thought_chunk"),
            _chunk(held, "Reading "),
            _chunk(held, "it."),
            _update(held, sessionUpdate="tool_call", title="Read a.py", kind="read"),
            _update(held, sessionUpdate="plan", entries=[]),
            _chunk(held, "Found it."),
            {"method": "something/else", "params": {}},
            {"id": ident, "result": {"stopReason": "max_tokens"}},
        )

    acp.turns = [turn]
    events = list(_agent().new(tmp_path).stream("hi"))
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "let me look"),
        ("text", "Reading it."),
        ("tool", "Read a.py"),
        ("text", "Found it."),
        ("result", "Reading it.\nFound it."),
    ]


@pytest.mark.parametrize("why", ["refusal", "cancelled", ""])
def test_a_turn_ending_on_anything_but_an_answer_fails(
    spawner: Spawner, acp: _Agent, tmp_path: Path, why: str
) -> None:
    acp.turns = [_ends(why)]
    with pytest.raises(Failed, match=f"the turn ended on {why}"):
        _agent().new(tmp_path)("hi")


def test_a_refused_prompt_fails_the_turn(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    acp.refusing["session/prompt"] = {"code": -1, "message": "the model refused"}
    with pytest.raises(Failed, match="the model refused"):
        _agent().new(tmp_path)("hi")


@pytest.mark.parametrize("method", ["initialize", "session/new"])
def test_a_refused_handshake_fails_the_turn_and_stops_the_agent(
    spawner: Spawner, acp: _Agent, tmp_path: Path, method: str
) -> None:
    acp.refusing[method] = {"code": -1, "message": "not today"}
    with pytest.raises(Failed, match="not today"):
        _agent().new(tmp_path)("hi")
    assert spawner.last.stdin is not None
    assert spawner.last.stdin.closed


def test_an_agent_speaking_a_later_protocol_is_refused(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    acp.hello = {"protocolVersion": 2}
    with pytest.raises(Failed, match="speaks version 2"):
        _agent().new(tmp_path)("hi")


def test_an_agent_that_goes_away_fails_the_turn_with_what_it_had_said(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    def leaves(proc: Process, ident: int, params: dict[str, Any]) -> None:
        del ident
        proc.say(_chunk(params["sessionId"], "half"))
        proc.exit(1)

    acp.turns = [leaves]
    with pytest.raises(Failed, match="stopped before it answered") as failed:
        _agent().new(tmp_path)("hi")
    assert failed.value.output == "half"


@pytest.mark.parametrize(
    ("options", "outcome"),
    [
        (
            [
                {"optionId": "once", "kind": "allow_once"},
                {"optionId": "always", "kind": "allow_always"},
                {"optionId": "no", "kind": "reject_once"},
            ],
            {"outcome": "selected", "optionId": "always"},
        ),
        (
            [{"optionId": "only", "kind": "other"}],
            {"outcome": "selected", "optionId": "only"},
        ),
        ([], {"outcome": "cancelled"}),
    ],
)
def test_a_permission_is_granted_by_the_kind_of_its_option(
    spawner: Spawner,
    acp: _Agent,
    tmp_path: Path,
    options: list[dict[str, str]],
    outcome: dict[str, str],
) -> None:
    acp.turns = [
        _asks(
            "session/request_permission",
            {"toolCall": {"title": "Edit a.py"}, "options": options},
        )
    ]
    _agent().new(tmp_path)("hi")
    assert acp.replied(50)["result"] == {"outcome": outcome}


def test_a_file_read_is_served_only_where_offered(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    held = tmp_path / "notes.txt"
    held.write_text("one\ntwo\nthree\nfour\n")
    asked = {"path": str(held), "line": 2, "limit": 2}
    acp.turns = [_asks("fs/read_text_file", asked)]
    _agent().new(tmp_path)("hi")
    assert acp.replied(50)["error"]["code"] == -32601
    acp.replies.clear()
    acp.turns = [_asks("fs/read_text_file", asked)]
    _agent(reads_files=True).new(tmp_path)("hi")
    assert acp.replied(50)["result"] == {"content": "two\nthree\n"}


def test_a_file_that_cannot_be_read_is_an_error_not_a_failed_turn(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    acp.turns = [_asks("fs/read_text_file", {"path": str(tmp_path / "missing")})]
    assert _agent(reads_files=True).new(tmp_path)("hi") == "done"
    assert acp.replied(50)["error"]["code"] == -32603


def test_a_file_write_makes_its_directories(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    target = tmp_path / "deep" / "er" / "out.txt"
    acp.turns = [
        _asks("fs/write_text_file", {"path": str(target), "content": "written"})
    ]
    _agent(writes_files=True).new(tmp_path)("hi")
    assert target.read_text() == "written"
    assert acp.replied(50) == {"jsonrpc": "2.0", "id": 50, "result": None}


def test_a_terminal_nobody_offered_is_refused(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    acp.turns = [_asks("terminal/create", {"command": "ls"})]
    _agent().new(tmp_path)("hi")
    assert acp.replied(50)["error"]["message"] == "terminal/create is not offered"


def test_a_terminal_it_is_not_holding_is_refused(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    acp.turns = [_asks("terminal/output", {"terminalId": "term-9"})]
    _agent(terminals=True).new(tmp_path)("hi")
    assert acp.replied(50)["error"]["code"] == -32602


@pytest.mark.parametrize(
    ("capabilities", "method"),
    [
        (
            {"sessionCapabilities": {"resume": {}}, "loadSession": True},
            "session/resume",
        ),
        ({"loadSession": True}, "session/load"),
    ],
)
def test_a_session_picked_back_up_on_a_new_process_resumes_it(
    spawner: Spawner,
    acp: _Agent,
    tmp_path: Path,
    capabilities: dict[str, Any],
    method: str,
) -> None:
    acp.hello = {"protocolVersion": 1, "agentCapabilities": capabilities}
    session = _agent().new(tmp_path)
    session("one")
    session.close()
    session("two")
    assert len(spawner.started) == 2
    (picked,) = acp.called(method)
    assert picked["sessionId"] == "s-1"
    assert [one["sessionId"] for one in acp.called("session/prompt")] == ["s-1", "s-1"]


def test_a_session_that_cannot_be_picked_back_up_is_refused(
    spawner: Spawner, acp: _Agent, tmp_path: Path
) -> None:
    session = _agent().new(tmp_path)
    session("one")
    session.close()
    with pytest.raises(Failed, match="offers neither session/resume nor session/load"):
        session("two")


def test_a_word_put_in_mid_turn_is_refused(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="no way to steer"):
        _agent().new(tmp_path).interject("hello")


def test_the_backend_is_the_name_it_was_added_under() -> None:
    assert _agent().backend == "mine"
    assert _agent(cli="").backend == "acp"
    assert _agent().command == ("my-acp", "--stdio")


def _speaking() -> dict[str, tuple[str, ...]]:
    return {"mine": ("found", "--acp")}


def _declaring(
    hosts: tuple[str, ...], state: tuple[str, ...]
) -> Callable[[str], tuple[tuple[str, ...], tuple[str, ...]]]:
    """`hmz.coganchor.backends.declared`, for a CLI added with these."""

    def declared(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        del name
        return hosts, state

    return declared


def test_a_command_not_given_is_looked_up_where_it_was_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backends, "speaking", _speaking)
    assert _agent(command=()).command == ("found", "--acp")
    monkeypatch.setattr(backends, "speaking", dict)
    with pytest.raises(ValueError, match="no command to start it with"):
        _ = _agent(command=()).command


@pytest.mark.parametrize("permission", ["read-only", "workspace-write", "auto"])
def test_only_bypass_or_no_rung_is_taken(permission: str) -> None:
    with pytest.raises(Unserved, match="cannot be held to"):
        _agent(permission=permission)
    assert isinstance(_agent(permission="bypass"), AcpAgent)


@pytest.mark.parametrize(("name", "command"), [("", "serve"), ("tools", " ")])
def test_an_mcp_server_needs_a_name_and_a_command(name: str, command: str) -> None:
    with pytest.raises(ValueError, match="needs a name and a command"):
        AcpAgentConfig(
            model=UNSAID,
            effort="",
            mcp_servers=(McpServer(name=name, command=command),),
        )


def test_a_cut_network_needs_the_hosts_the_cli_was_declared_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fence, "enforceable", fenceable)
    offline = Fence(read=("/",), write=("/tmp",), online=False)
    monkeypatch.setattr(backends, "declared", _declaring((), ()))
    with pytest.raises(Unfenced, match="nothing says which hosts mine's model is at"):
        _agent(fence=offline)
    monkeypatch.setattr(backends, "declared", _declaring(("api.example.com",), ()))
    assert isinstance(_agent(fence=offline), AcpAgent)


def test_fenced_lets_the_declared_state_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(fence, "enforceable", fenceable)
    state = tmp_path / "state"
    monkeypatch.setattr(backends, "declared", _declaring((), (str(state),)))
    held = _agent(fence=Fence(read=("/",), write=(str(tmp_path / "work"),))).fenced()
    assert held is not None
    assert str(state) in held.write
    assert _agent().fenced() is None
