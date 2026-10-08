"""Codex: every turn on an app server of the agent's own, spoken to in JSON-RPC.

The server is a scripted process answering the calls the driver makes -- `initialize`,
`thread/start`, `turn/start` -- with the notifications a test hands it, so what is checked is
the command a server is started as, the calls a turn is made of, and the turn read back.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from hmz.coganchor.agents import (
    CodexAgent,
    CodexAgentConfig,
    CodexSession,
    Failed,
    Moment,
    Question,
    Verdict,
)
from hmz.coganchor.agents.codex import strict, turning, unattended
from tests.unit.coganchor.agents.doubles_u4 import Process, Spawner

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hmz.coganchor.agents import Occasion

type _Turn = Callable[[Process, str, str], None]


#: What every agent here is made with unless a test says otherwise.
_DEFAULTS: dict[str, Any] = {"model": "gpt-x", "effort": ""}


def _item(method: str, thread: str, turn: str, **item: Any) -> dict[str, Any]:
    return {
        "method": f"item/{method}",
        "params": {"threadId": thread, "turnId": turn, "item": item},
    }


def _says(*items: dict[str, Any], total: tuple[int, int] = (0, 0)) -> _Turn:
    """A turn that says these items, spends `total` on the thread, and falls idle."""

    def turn(proc: Process, thread: str, turn: str) -> None:
        proc.say(
            {
                "method": "turn/started",
                "params": {"threadId": thread, "turn": {"id": turn}},
            }
        )
        for one in items:
            kind = "completed" if one.pop("done", True) else "started"
            proc.say(_item(kind, thread, turn, **one))
        if any(total):
            proc.say(
                {
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": thread,
                        "tokenUsage": {
                            "total": {
                                "inputTokens": total[0],
                                "outputTokens": total[1],
                            },
                            "last": {"inputTokens": total[0], "outputTokens": total[1]},
                        },
                    },
                }
            )
        proc.say(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": thread,
                    "turn": {"id": turn, "status": "completed"},
                },
            },
            {
                "method": "thread/status/changed",
                "params": {"threadId": thread, "status": {"type": "idle"}},
            },
        )

    return turn


class _Server:
    """What the scripted `codex app-server` answers, and every call it was made."""

    def __init__(self, spawner: Spawner) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.turns: list[_Turn] = []
        self.refusing: dict[str, dict[str, Any]] = {}
        self.replies: list[dict[str, Any]] = []
        #: What to do once the driver has answered something the server asked, by its id.
        self.after: dict[int, Callable[[], None]] = {}
        self._threads = 0
        self._turned = 0
        spawner.replying(self._heard)

    def _heard(self, proc: Process, said: Any) -> None:
        method, ident = said.get("method"), said.get("id")
        if method is None:
            self.replies.append(said)  # an answer to something the server asked
            if (then := self.after.pop(int(ident or 0), None)) is not None:
                then()
            return
        params: dict[str, Any] = said.get("params") or {}
        self.calls.append((method, params))
        if ident is None:
            return
        if (refused := self.refusing.pop(method, None)) is not None:
            proc.say({"id": ident, "error": refused})
            return
        if method in ("thread/start", "thread/fork"):
            self._threads += 1
            proc.say({"id": ident, "result": {"thread": {"id": f"th-{self._threads}"}}})
        elif method == "turn/start":
            self._turned += 1
            turn = f"tu-{self._turned}"
            proc.say({"id": ident, "result": {"turn": {"id": turn}}})
            answer = self.turns.pop(0) if self.turns else _says(_message("done"))
            answer(proc, str(params["threadId"]), turn)
        else:
            proc.say({"id": ident, "result": {}})

    def called(self, method: str) -> list[dict[str, Any]]:
        return [params for named, params in self.calls if named == method]


def _message(text: str, ident: str = "m1") -> dict[str, Any]:
    return {"type": "agentMessage", "id": ident, "text": text}


@pytest.fixture
def spawner(monkeypatch: pytest.MonkeyPatch) -> Spawner:
    """Every process a turn asks for, scripted rather than started."""
    return Spawner(monkeypatch)


@pytest.fixture
def server(spawner: Spawner) -> _Server:
    """The scripted app server."""
    return _Server(spawner)


def _servers(spawner: Spawner) -> list[Process]:
    return [one for one in spawner.started if one.args[1:2] == ["app-server"]]


def _agent(**given: Any) -> CodexAgent:
    return CodexAgent(CodexAgentConfig(**_DEFAULTS | given))


class _Shape(BaseModel):
    ok: bool
    why: str = "x"
    inner: dict[str, int] = {}


def test_strict_requires_every_property_and_closes_every_object() -> None:
    held = strict(_Shape.model_json_schema())
    assert held["required"] == ["ok", "why", "inner"]
    assert held["additionalProperties"] is False
    assert "default" not in held["properties"]["why"]
    assert held["properties"]["inner"]["additionalProperties"] == {"type": "integer"}
    assert "required" not in held["properties"]["inner"]


def test_strict_leaves_a_property_named_like_a_keyword_alone() -> None:
    schema = {
        "type": "object",
        "properties": {"default": {"type": "string", "default": "a"}},
    }
    held = strict(schema)
    assert held["properties"] == {"default": {"type": "string"}}
    assert held["required"] == ["default"]


@pytest.mark.parametrize(
    ("permission", "tier", "expected"),
    [
        ("read-only", "default", {"approvalPolicy": "never", "sandbox": "read-only"}),
        (
            "auto",
            "default",
            {"approvalPolicy": "on-request", "sandbox": "workspace-write"},
        ),
        (
            "bypass",
            "fast",
            {"approvalPolicy": "never", "sandbox": "danger-full-access"},
        ),
        ("", "default", {}),
        ("no such rung", "default", {}),
    ],
)
def test_unattended_is_the_rung_and_the_tier(
    permission: str, tier: str, expected: dict[str, str]
) -> None:
    service = "priority" if tier == "fast" else "default"
    held = unattended(permission, tier)
    assert held == {"serviceTier": service} | expected
    assert "sandbox" not in turning(held)
    assert turning(held) == {
        key: value for key, value in held.items() if key != "sandbox"
    }


@pytest.mark.parametrize(
    ("given", "match"),
    [
        ({"overrides": (("nope", "1"),)}, "not a Codex override"),
        ({"overrides": (("model_context_window", "0"),)}, "positive integer"),
        (
            {
                "overrides": (
                    ("model_context_window", "1"),
                    ("model_context_window", "2"),
                )
            },
            "given twice",
        ),
        (
            {
                "overrides": (
                    ("model_context_window", "100"),
                    ("model_auto_compact_token_limit", "100"),
                )
            },
            "below model_context_window",
        ),
        ({"features": (("Bad-Name", True),)}, "not a Codex feature name"),
        ({"features": (("goals", True),)}, "flow's to say"),
        ({"features": (("web_search_request", True),)}, "web_search"),
        ({"features": (("x", True), ("x", False))}, "given twice"),
        ({"approvals": "sometimes"}, "approvals must be one of"),
    ],
)
def test_the_config_refuses_what_it_cannot_take(
    given: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        CodexAgentConfig(model="m", effort="", **given)


def test_overrides_are_stripped_and_kept_in_order() -> None:
    config = CodexAgentConfig(
        model="m",
        effort="",
        overrides=((" model_context_window ", " 200 "),),
        features=((" fast_mode ", True),),
    )
    assert config.overrides == (("model_context_window", "200"),)
    assert config.features == (("fast_mode", True),)


def test_a_turn_starts_a_thread_and_a_turn_on_one_server(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    agent = _agent(effort="high")
    session = agent.new(tmp_path)
    assert isinstance(session, CodexSession)
    assert session("hi") == "done"
    assert session("again") == "done"
    (proc,) = _servers(spawner)
    assert proc.args == ["codex", "app-server", "--stdio"]
    assert [method for method, _ in server.calls][:2] == ["initialize", "initialized"]
    (opened,) = server.called("thread/start")
    assert opened["cwd"] == str(tmp_path)
    assert opened["model"] == "gpt-x"
    first, second = server.called("turn/start")
    assert first["threadId"] == second["threadId"] == "th-1"
    assert first["input"] == [{"type": "text", "text": "hi"}]
    assert first["effort"] == "high"
    assert first["serviceTier"] == "default"
    assert session.id == "th-1"


def test_the_server_command_says_what_the_config_says(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    agent = _agent(
        web_search=True,
        strict_config=True,
        features=(("fast_mode", False),),
        overrides=(("model_context_window", "1000"),),
    )
    agent.disable_goals()
    agent.new(tmp_path)("hi")
    (proc,) = _servers(spawner)
    assert proc.args == [
        "codex",
        "app-server",
        "--strict-config",
        "--disable",
        "goals",
        "--disable",
        "fast_mode",
        "-c",
        'web_search="live"',
        "--stdio",
        "-c",
        "model_context_window=1000",
    ]


def test_no_web_search_is_said_as_disabled(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    _agent(web_search=False).new(tmp_path)("hi")
    assert 'web_search="disabled"' in _servers(spawner)[0].args


def test_goals_cannot_be_disabled_once_a_server_ran_with_them(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    agent = _agent()
    agent.new(tmp_path)("hi")
    with pytest.raises(RuntimeError, match="before its first turn"):
        agent.disable_goals()


@pytest.mark.parametrize(
    ("permission", "sandbox", "policy"),
    [
        ("bypass", "danger-full-access", "never"),
        ("auto", "workspace-write", "on-request"),
    ],
)
def test_the_rung_goes_with_the_thread_and_the_policy_with_each_turn(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    permission: str,
    sandbox: str,
    policy: str,
) -> None:
    _agent(permission=permission, service_tier="fast").new(tmp_path)("hi")
    (opened,) = server.called("thread/start")
    assert (opened["sandbox"], opened["approvalPolicy"]) == (sandbox, policy)
    (turned,) = server.called("turn/start")
    assert "sandbox" not in turned
    assert turned["approvalPolicy"] == policy
    assert turned["serviceTier"] == "priority"


def test_an_approval_policy_of_its_own_replaces_the_rungs(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    _agent(permission="bypass", approvals="untrusted").new(tmp_path)("hi")
    (opened,) = server.called("thread/start")
    assert opened["approvalPolicy"] == "untrusted"
    assert opened["sandbox"] == "danger-full-access"


def test_a_turn_says_what_the_agent_did_and_what_it_cost(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.turns = [
        _says(
            {"type": "userMessage", "id": "u", "content": []},
            {"type": "reasoning", "id": "r", "summary": ["thinking", "hard"]},
            {"type": "commandExecution", "id": "c", "command": "ls -la", "done": False},
            {"type": "commandExecution", "id": "c", "command": "ls -la"},
            {
                "type": "fileChange",
                "id": "f",
                "changes": [{"path": "a.py"}, {"path": "b.py"}],
            },
            {
                "type": "collabAgentToolCall",
                "id": "s",
                "tool": "explore",
                "done": False,
            },
            {"type": "collabAgentToolCall", "id": "s", "tool": "explore"},
            {"type": "somethingNew", "id": "n", "detail": "a new kind"},
            _message("the answer"),
            total=(120, 30),
        )
    ]
    session = _agent().new(tmp_path)
    events = list(session.stream("hi"))
    assert [(one.kind, one.text, one.whose) for one in events[:-1]] == [
        ("reasoning", "thinking hard", ""),
        ("tool", "Bash ls -la", ""),
        ("tool", "Edit a.py b.py", ""),
        ("subagent", "Task explore", "s"),
        ("subagent-ends", "Task explore", "s"),
        ("tool", "somethingNew a new kind", ""),
        ("text", "the answer", ""),
    ]
    result = events[-1]
    assert (result.kind, result.text) == ("result", "the answer")
    assert result.tokens == {"gpt-x": 150}
    assert dict(result.spent) == {"input": 120, "output": 30}
    assert session.spent().total == 150


@pytest.mark.parametrize(
    "ending",
    [
        [
            {"method": "error", "params": {"error": {"message": "the model refused"}}},
            {
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "status": "failed",
                        "error": {"message": "the model refused"},
                    }
                },
            },
        ],
        [
            {
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "status": "failed",
                        "error": {"message": "the model refused"},
                    }
                },
            }
        ],
    ],
)
def test_a_turn_the_server_says_failed_fails(
    spawner: Spawner, server: _Server, tmp_path: Path, ending: list[dict[str, Any]]
) -> None:
    def fails(proc: Process, thread: str, turn: str) -> None:
        proc.say(
            {
                "method": "turn/started",
                "params": {"threadId": thread, "turn": {"id": turn}},
            }
        )
        for one in ending:
            one["params"]["threadId"] = thread
            proc.say(one)
        proc.say(
            {
                "method": "thread/status/changed",
                "params": {"threadId": thread, "status": {"type": "idle"}},
            }
        )

    server.turns = [fails]
    session = _agent().new(tmp_path)
    with pytest.raises(Failed, match="the model refused"):
        session("hi")
    with pytest.raises(RuntimeError):
        _ = session.id


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_an_idle_thread_does_not_hide_its_turn_s_completion_error(
    spawner: Spawner, server: _Server, tmp_path: Path, status: str
) -> None:
    def fails(proc: Process, thread: str, turn: str) -> None:
        proc.say(
            {
                "method": "turn/started",
                "params": {"threadId": thread, "turn": {"id": turn}},
            },
            {
                "method": "thread/status/changed",
                "params": {"threadId": thread, "status": {"type": "idle"}},
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": thread,
                    "turn": {
                        "id": turn,
                        "status": status,
                        "error": {"message": "workspace routing discovery failed"},
                    },
                },
            },
        )

    server.turns = [fails]
    with pytest.raises(Failed, match="workspace routing discovery failed"):
        _agent().new(tmp_path)("hi")


def test_a_reconnecting_turn_waits_for_its_successful_completion_after_idle(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    def recovers(proc: Process, thread: str, turn: str) -> None:
        proc.say(
            {
                "method": "turn/started",
                "params": {"threadId": thread, "turn": {"id": turn}},
            },
            {
                "method": "error",
                "params": {
                    "threadId": thread,
                    "error": {"message": "reconnecting"},
                    "willRetry": True,
                },
            },
            {
                "method": "thread/status/changed",
                "params": {"threadId": thread, "status": {"type": "idle"}},
            },
            _item("completed", thread, turn, **_message("recovered")),
            {
                "method": "turn/completed",
                "params": {
                    "threadId": thread,
                    "turn": {"id": turn, "status": "completed", "error": None},
                },
            },
        )

    server.turns = [recovers]
    assert _agent().new(tmp_path)("hi") == "recovered"


def test_a_refused_call_is_a_failed_turn(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.refusing["thread/start"] = {"code": -1, "message": "no such model"}
    with pytest.raises(Failed, match="no such model"):
        _agent().new(tmp_path)("hi")


def test_a_rung_the_installation_forbids_is_stepped_down_and_remembered(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.refusing["thread/start"] = {
        "code": -1,
        "message": "approval_policy cannot be used because requirements do not allow it",
    }
    agent = _agent(permission="bypass")
    agent.new(tmp_path)("hi")
    refused, stepped = server.called("thread/start")
    assert refused["sandbox"] == "danger-full-access"
    assert (stepped["sandbox"], stepped["approvalPolicy"]) == (
        "workspace-write",
        "on-request",
    )
    agent.new(tmp_path)("again")
    assert server.called("thread/start")[-1]["sandbox"] == "workspace-write"


def test_a_server_that_goes_away_fails_the_turn(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.turns = [lambda proc, thread, turn: proc.exit(1)]
    with pytest.raises(Failed, match="stopped mid-turn"):
        _agent().new(tmp_path)("hi")


@pytest.mark.parametrize(
    ("permission", "refuse", "decision"),
    [("bypass", False, "accept"), ("bypass", True, "decline"), ("", False, "decline")],
)
def test_an_approval_is_granted_at_a_named_rung_unless_a_hook_refuses(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    permission: str,
    refuse: bool,
    decision: str,
) -> None:
    seen: list[Occasion] = []

    def hook(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=refuse, because="no")

    def asks(proc: Process, thread: str, turn: str) -> None:
        proc.say(
            {
                "id": 900,
                "method": "item/commandExecution/requestApproval",
                "params": {"threadId": thread, "command": "rm -rf build"},
            }
        )
        server.after[900] = lambda: _says(_message("done"))(proc, thread, turn)

    server.turns = [asks]
    agent = _agent(permission=permission)
    agent.hooks.on(Moment.PERMISSION_REQUEST, hook)
    agent.new(tmp_path)("hi")
    (reply,) = [one for one in server.replies if one.get("id") == 900]
    assert reply["result"] == {"decision": decision}
    assert [(one.tool, one.about) for one in seen] == [
        ("commandExecution", "rm -rf build")
    ]


def test_a_question_is_put_to_whoever_is_driving(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    asked: list[Question] = []

    def asks(proc: Process, thread: str, turn: str) -> None:
        proc.say(
            {
                "id": 901,
                "method": "item/tool/requestUserInput",
                "params": {
                    "threadId": thread,
                    "questions": [
                        {
                            "id": "q1",
                            "question": "Which?",
                            "options": [{"label": "blue"}],
                        }
                    ],
                },
            }
        )
        server.after[901] = lambda: _says(_message("done"))(proc, thread, turn)

    def ask(question: Question) -> str:
        asked.append(question)
        return "blue"

    agent = _agent()
    agent.ask = ask
    server.turns = [asks]
    agent.new(tmp_path)("hi")
    (reply,) = [one for one in server.replies if one.get("id") == 901]
    assert reply["result"] == {"answers": {"q1": {"answers": ["blue"]}}}
    assert [(one.text, one.options) for one in asked] == [("Which?", ("blue",))]


def test_anything_else_the_server_asks_is_answered_with_an_error(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    def asks(proc: Process, thread: str, turn: str) -> None:
        proc.say({"id": 902, "method": "something/else", "params": {}})
        server.after[902] = lambda: _says(_message("done"))(proc, thread, turn)

    server.turns = [asks]
    _agent().new(tmp_path)("hi")
    (reply,) = [one for one in server.replies if one.get("id") == 902]
    assert reply["error"]["code"] == -32601


def test_a_shaped_turn_sends_a_strict_output_schema(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.turns = [_says(_message(json.dumps({"ok": True, "why": "y", "inner": {}})))]
    answered = _agent().new(tmp_path)("judge", schema=_Shape)
    assert answered == _Shape(ok=True, why="y")
    (turned,) = server.called("turn/start")
    assert turned["outputSchema"]["additionalProperties"] is False


def test_a_word_put_in_mid_turn_steers_the_turn(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    def working(proc: Process, thread: str, turn: str) -> None:
        proc.say(
            {
                "method": "turn/started",
                "params": {"threadId": thread, "turn": {"id": turn}},
            }
        )
        proc.say(_item("completed", thread, turn, **_message("working", "w")))

    server.turns = [working]
    session = _agent().new(tmp_path)
    stream = session.stream("hi")
    assert next(stream).text == "working"
    session.interject("also this")
    (steer,) = server.called("turn/steer")
    assert steer["threadId"] == "th-1"
    assert steer["expectedTurnId"] == "tu-1"
    assert steer["input"] == [{"type": "text", "text": "also this"}]
    proc = _servers(spawner)[0]
    proc.say(
        _item(
            "started",
            "th-1",
            "tu-1",
            type="userMessage",
            id="u2",
            clientId=steer["clientUserMessageId"],
        )
    )
    _says(_message("both"))(proc, "th-1", "tu-1")
    rest = [(one.kind, one.text) for one in stream]
    assert rest[0] == ("took", "also this")
    assert rest[-1] == ("result", "both")


def test_interjecting_with_no_turn_running_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no turn is running"):
        _agent().new(tmp_path).interject("hello")


def test_a_reconfigured_agent_picks_its_thread_up_on_a_new_server(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    agent = _agent()
    session = agent.new(tmp_path)
    session("one")
    agent.reconfigure(replace(agent.config, web_search=False))
    session("two")
    first, second = _servers(spawner)
    assert first.returncode is not None
    assert 'web_search="disabled"' in second.args
    assert server.called("thread/resume")[0]["threadId"] == "th-1"
    assert session.id == "th-1"


def test_stopping_the_agent_takes_its_server_down(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    agent = _agent()
    agent.new(tmp_path)("one")
    agent.stop()
    assert _servers(spawner)[0].returncode is not None


def test_a_goal_is_set_on_the_thread_and_pursued_until_met(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    def pursued(proc: Process, thread: str, turn: str) -> None:
        proc.say(
            _item("completed", thread, turn, **_message("met it")),
            {
                "method": "thread/goal/updated",
                "params": {"threadId": thread, "goal": {"status": "complete"}},
            },
            {
                "method": "thread/status/changed",
                "params": {"threadId": thread, "status": {"type": "idle"}},
            },
        )

    server.turns = [pursued]
    session = _agent().new(tmp_path)
    assert session.pursue("ship it") == "met it"
    (goal,) = server.called("thread/goal/set")
    assert goal == {"threadId": "th-1", "objective": "ship it"}
    assert session.id == "th-1"
