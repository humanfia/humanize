"""Codex: every turn on an app server of the agent's own, spoken to in JSON-RPC.

The server is a scripted process answering the calls the driver makes -- `initialize`,
`thread/start`, `turn/start` -- with the notifications a test hands it, so what is checked is
the command a server is started as, the calls a turn is made of, and the turn read back.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, cast

import pytest
from pydantic import BaseModel, Field, Json

from hmz.coganchor import AnchorConfig, fence, gateway, prices, providers
from hmz.coganchor.agents import (
    CodexAgent,
    CodexAgentConfig,
    CodexSession,
    Failed,
    Moment,
    Question,
    Verdict,
)
from hmz.coganchor.agents.base import KEEPING
from hmz.coganchor.agents.codex import sandboxing, strict, turning
from hmz.coganchor.fence import READ, WRITE, Fence
from hmz.coganchor.machines import AnchoredConfig
from hmz.coganchor.providers import Provider
from tests.unit.coganchor.agents.doubles_u4 import Process, Spawner, fenceable

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from hmz.coganchor.agents import Occasion

type _Turn = Callable[[Process, str, str], None]


#: What every agent here is made with unless a test says otherwise.
_DEFAULTS: dict[str, Any] = {"model": "gpt-x", "effort": ""}


def _holding(self: CodexAgent, fence: Fence) -> bool:
    """`CodexAgent.holds` as it answers where Codex's own sandbox holds the fence."""
    del self, fence
    return True


def _item(method: str, thread: str, turn: str, **item: Any) -> dict[str, Any]:
    return {
        "method": f"item/{method}",
        "params": {"threadId": thread, "turnId": turn, "item": item},
    }


def _says(
    *items: dict[str, Any], total: tuple[int, int] = (0, 0), cached: int = 0
) -> _Turn:
    """A turn that says these items, spends `total` on the thread, and falls idle.

    `cached` is how much of that input the server says was read from the cache.
    """

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
                                "cachedInputTokens": cached,
                                "outputTokens": total[1],
                            },
                            "last": {
                                "inputTokens": total[0],
                                "cachedInputTokens": cached,
                                "outputTokens": total[1],
                            },
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
        #: What `skills/list` lists, and what a shell command prints and exits on.
        self.skills: list[dict[str, Any]] = []
        self.output: tuple[str, int] = ("", 0)
        #: Whether an operation's turn is preceded by a stray completion of another turn.
        self.stray = False
        #: What `configRequirements/read` answers with, as codex-cli 0.163.0 shapes it.
        self.requirements: dict[str, Any] | None = None
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
        elif method in ("turn/start", "review/start"):
            self._turned += 1
            turn = f"tu-{self._turned}"
            proc.say({"id": ident, "result": {"turn": {"id": turn}}})
            answer = self.turns.pop(0) if self.turns else _says(_message("done"))
            answer(proc, str(params["threadId"]), turn)
        elif method == "configRequirements/read":
            proc.say({"id": ident, "result": {"requirements": self.requirements}})
        elif method == "skills/list":
            listed = {"cwd": params["cwds"][0], "skills": self.skills, "errors": []}
            proc.say({"id": ident, "result": {"data": [listed]}})
        elif method in ("thread/shellCommand", "thread/compact/start"):
            # Answered with nothing, and done as a turn of the server's own that no answer
            # names, as codex-cli 0.163.0 does both.
            proc.say({"id": ident, "result": {}})
            if self.stray:
                # Said late of a turn already over, before the operation's own turn begins.
                proc.say(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": params["threadId"],
                            "turn": {"id": "tu-old", "status": "completed"},
                        },
                    }
                )
            self._turned += 1
            item = (
                {
                    "type": "commandExecution",
                    "id": "sh",
                    "command": f"/bin/zsh -lc {params['command']!r}",
                    "source": "userShell",
                    "aggregatedOutput": self.output[0],
                    "exitCode": self.output[1],
                }
                if method == "thread/shellCommand"
                else {"type": "contextCompaction", "id": "cc"}
            )
            _says(item)(proc, str(params["threadId"]), f"tu-{self._turned}")
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


def _fence(where: Path, local: str = WRITE, *, online: bool = True) -> Fence:
    """A fence reading everything and giving the workdir `local`."""
    return Fence.of(
        rules=[("/", READ), (".", local)],
        online=online,
        workdir=where,
        home=where / "home",
    )


@pytest.fixture
def fenced(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Fence]:
    """Fences this machine is taken to be able to put up, made as :func:`_fence` makes them."""
    monkeypatch.setattr(fence, "enforceable", fenceable)
    return _fence


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


def test_strict_leaves_names_and_data_that_look_like_keywords_alone() -> None:
    def example() -> dict[str, Any]:
        return {"$ref": "#/$defs/x", "default": "a", "properties": {}}

    schema = {
        "type": "object",
        "properties": {"default": {"type": "string", "default": "a"}},
        "examples": [example()],
    }
    held = strict(schema)
    assert held["properties"] == {"default": {"type": "string"}}
    assert held["required"] == ["default"]
    assert held["examples"] == [example()]


class _Mood(StrEnum):
    """The type's own words."""

    CALM = "calm"


class _Place(BaseModel):
    path: str


class _Node(BaseModel):
    kids: list[Annotated[_Node, Field(description="a kid")]]


class _Described(BaseModel):
    mood: _Mood = Field(description="the field's words")
    place: _Place = Field(description="where")
    tree: _Node = Field(description="a tree")
    packed: Json[_Place]
    more: list[_Described]


def _crowded(node: object) -> list[dict[str, object]]:
    """Every node of a schema with a keyword beside its `$ref`."""
    if isinstance(node, list):
        return [one for item in cast("list[object]", node) for one in _crowded(item)]
    if not isinstance(node, dict):
        return []
    held = cast("dict[str, object]", node)
    found = [held] if "$ref" in held and len(held) > 1 else []
    return found + [one for value in held.values() for one in _crowded(value)]


def test_strict_writes_a_described_reference_out_with_its_description() -> None:
    held = strict(_Described.model_json_schema())
    assert _crowded(held) == []
    said = held["properties"]
    assert said["mood"]["description"] == "the field's words"
    assert said["mood"]["enum"] == ["calm"]
    assert said["place"]["description"] == "where"
    assert said["place"]["additionalProperties"] is False
    assert said["tree"]["description"] == "a tree"
    # Inside its own definition a reference cannot be written out: it loses its words.
    assert held["$defs"]["_Node"]["properties"]["kids"]["items"] == {
        "$ref": "#/$defs/_Node"
    }


def test_strict_ends_on_a_definition_nested_in_the_one_it_names() -> None:
    leaf = {"$ref": "#/$defs/Leaf", "description": "the root leaf"}
    schema = {
        "type": "object",
        "properties": {"top": {"$ref": "#/$defs/Tree", "description": "a tree"}},
        "$defs": {
            "Leaf": {"type": "object", "properties": {"v": {"type": "string"}}},
            "Tree": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "$defs": {
                    "Leaf": {"type": "object", "properties": {"leaf": leaf}},
                    "Loop": {
                        "type": "object",
                        "properties": {
                            "t": {"$ref": "#/$defs/Tree", "description": "up"}
                        },
                    },
                },
            },
        },
    }
    held = strict(schema)
    assert _crowded(held) == []
    nested = held["$defs"]["Tree"]["$defs"]["Leaf"]["properties"]["leaf"]
    assert nested["description"] == "the root leaf"


@pytest.mark.parametrize(
    ("local", "tier", "expected"),
    [
        (READ, "default", {"approvalPolicy": "never", "sandbox": "read-only"}),
        (
            WRITE,
            "fast",
            {"approvalPolicy": "never", "sandbox": "danger-full-access"},
        ),
        (None, "default", {}),
        (None, "fast", {}),
    ],
)
def test_sandboxing_is_read_off_the_fence_beside_the_tier(
    tmp_path: Path, local: str | None, tier: str, expected: dict[str, str]
) -> None:
    """A fence writing nothing is `read-only`, one that writes is full access, none silence."""
    service = "priority" if tier == "fast" else "default"
    held = sandboxing(None if local is None else _fence(tmp_path, local), tier)
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
    ("local", "sandbox"), [(WRITE, "danger-full-access"), (READ, "read-only")]
)
def test_the_sandbox_goes_with_the_thread_and_the_policy_with_each_turn(
    spawner: Spawner,
    server: _Server,
    fenced: Callable[..., Fence],
    tmp_path: Path,
    local: str,
    sandbox: str,
) -> None:
    _agent(fence=fenced(tmp_path, local), service_tier="fast").new(tmp_path)("hi")
    (opened,) = server.called("thread/start")
    assert (opened["sandbox"], opened["approvalPolicy"]) == (sandbox, "never")
    (turned,) = server.called("turn/start")
    assert "sandbox" not in turned
    assert turned["approvalPolicy"] == "never"
    assert turned["serviceTier"] == "priority"


def test_an_agent_with_no_fence_is_told_nothing_of_what_it_may_do(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    """Driven by hand: Codex is left at its own defaults, an approval policy said or not."""
    _agent(approvals="untrusted").new(tmp_path)("hi")
    (opened,) = server.called("thread/start")
    (turned,) = server.called("turn/start")
    for said in (opened, turned):
        assert not {"sandbox", "sandboxPolicy", "approvalPolicy"} & set(said)


def test_an_approval_policy_of_its_own_replaces_never(
    spawner: Spawner, server: _Server, fenced: Callable[..., Fence], tmp_path: Path
) -> None:
    _agent(fence=fenced(tmp_path), approvals="untrusted").new(tmp_path)("hi")
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


def test_cached_input_is_counted_beside_the_input_not_inside_it(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    # The server counts cached reads inside `inputTokens`; priced as plain input they put an
    # agent's bill several times over the truth, so they are reported as `cache_read`.
    server.turns = [_says(_message("done"), total=(1000, 30), cached=900)]
    session = _agent().new(tmp_path)
    result = list(session.stream("hi"))[-1]
    assert result.tokens == {"gpt-x": 1030}
    assert dict(result.spent) == {"input": 100, "cache_read": 900, "output": 30}
    assert session.spent().total == 1030
    assert "cache_read" in CodexAgent.counts


def test_a_request_past_a_long_context_line_is_counted_beside_the_kinds(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[dict[str, float], str]] = []

    def tiered(request: Mapping[str, float], model: str) -> dict[str, float]:
        asked.append((dict(request), model))
        return {f"{kind}>500": tokens for kind, tokens in request.items()}

    monkeypatch.setattr(prices, "tiered", tiered)
    server.turns = [_says(_message("done"), total=(1000, 30), cached=900)]
    session = _agent().new(tmp_path)
    result = list(session.stream("hi"))[-1]
    # Read off the one request the server says came back, for the model the turn ran on.
    assert asked == [({"input": 100.0, "cache_read": 900.0, "output": 30.0}, "gpt-x")]
    marked = {"input>500": 100.0, "cache_read>500": 900.0, "output>500": 30.0}
    assert dict(result.spent) == {"input": 100, "cache_read": 900, "output": 30}
    assert result.spent.tiered == marked
    assert session.spent().tiered == marked


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


#: What codex-cli 0.163.0 refuses a call with, word for word, where its requirements forbid
#: the sandbox or the approval policy the call names.
_FORBIDS = {
    "code": -32600,
    "message": '`approval_policy = "never"` cannot be used because requirements do not'
    ' allow `sandbox_mode = "danger-full-access"`; choose a different approval policy',
}
_NEVER_FORBIDDEN = {
    "code": -32600,
    "message": "invalid value for `approval_policy`: `never` is not in the allowed set"
    " [OnRequest, UnlessTrusted] (set by /etc/codex/requirements.toml)",
}
_READ_ONLY_FORBIDDEN = {
    "code": -32600,
    "message": "invalid value for `sandbox_mode`: `read-only` is not in the allowed set"
    " [workspace-write] (set by MDM com.openai.codex:requirements_toml_base64)",
}


def test_full_access_the_installation_forbids_is_stepped_down_and_remembered(
    spawner: Spawner, server: _Server, fenced: Callable[..., Fence], tmp_path: Path
) -> None:
    server.refusing["thread/start"] = dict(_FORBIDS)
    agent = _agent(fence=fenced(tmp_path))
    agent.new(tmp_path)("hi")
    refused, stepped = server.called("thread/start")
    assert refused["sandbox"] == "danger-full-access"
    assert (
        stepped["sandbox"],
        stepped["approvalPolicy"],
        stepped["approvalsReviewer"],
    ) == ("workspace-write", "on-request", "user")
    agent.new(tmp_path)("again")
    assert server.called("thread/start")[-1]["sandbox"] == "workspace-write"


def test_forbidden_full_access_is_stepped_down_under_an_approval_policy_of_its_own(
    spawner: Spawner, server: _Server, fenced: Callable[..., Fence], tmp_path: Path
) -> None:
    """`untrusted`, as while a permission-request hook is hung, goes down with the sandbox."""
    server.refusing["thread/start"] = dict(_FORBIDS)
    agent = _agent(fence=fenced(tmp_path), approvals="untrusted")
    agent.new(tmp_path)("hi")
    agent.new(tmp_path)("again")
    refused, stepped, again = server.called("thread/start")
    assert (refused["sandbox"], refused["approvalPolicy"]) == (
        "danger-full-access",
        "untrusted",
    )
    for one in (stepped, again):
        assert (one["sandbox"], one["approvalPolicy"]) == (
            "workspace-write",
            "untrusted",
        )
    assert {one["approvalPolicy"] for one in server.called("turn/start")} == {
        "untrusted"
    }


def test_never_said_as_its_own_asks_alike_on_every_turn_once_stepped_down(
    spawner: Spawner, server: _Server, fenced: Callable[..., Fence], tmp_path: Path
) -> None:
    """`never` is what the fence is told already, so a step down asks on every turn."""
    server.refusing["thread/start"] = dict(_FORBIDS)
    agent = _agent(fence=fenced(tmp_path), approvals="never")
    agent.new(tmp_path)("hi")
    agent.new(tmp_path)("again")
    _, *stepped = server.called("thread/start")
    assert {one["approvalPolicy"] for one in stepped} == {"on-request"}
    assert {one["approvalPolicy"] for one in server.called("turn/start")} == {
        "on-request"
    }


def test_requirements_read_as_the_server_starts_choose_before_any_thread_is_refused(
    spawner: Spawner, server: _Server, fenced: Callable[..., Fence], tmp_path: Path
) -> None:
    """`never` forbidden: full access asking, where this client grants what it asks."""
    server.requirements = {"allowedApprovalPolicies": ["on-request", "untrusted"]}
    _agent(fence=fenced(tmp_path)).new(tmp_path)("hi")
    assert [method for method, _ in server.calls][:3] == [
        "initialize",
        "initialized",
        "configRequirements/read",
    ]
    (opened,) = server.called("thread/start")
    assert (
        opened["sandbox"],
        opened["approvalPolicy"],
        opened["approvalsReviewer"],
    ) == ("danger-full-access", "on-request", "user")
    (turned,) = server.called("turn/start")
    assert turned["approvalPolicy"] == "on-request"


def test_permission_profiles_the_requirements_name_are_read_as_the_sandboxes(
    spawner: Spawner, server: _Server, fenced: Callable[..., Fence], tmp_path: Path
) -> None:
    server.requirements = {
        "allowedSandboxModes": ["danger-full-access"],
        "allowedPermissionProfiles": {":workspace": True, ":danger-full-access": False},
    }
    _agent(fence=fenced(tmp_path)).new(tmp_path)("hi")
    (opened,) = server.called("thread/start")
    assert (opened["sandbox"], opened["approvalPolicy"]) == (
        "workspace-write",
        "on-request",
    )


@pytest.mark.parametrize(
    ("requirements", "approvals"),
    [
        ({"allowedSandboxModes": []}, ""),
        ({"allowedApprovalPolicies": ["never"]}, "untrusted"),
        (
            {
                "allowedApprovalPolicies": ["on-request"],
                "allowedApprovalsReviewers": ["auto_review"],
            },
            "",
        ),
    ],
)
def test_requirements_nothing_will_do_under_fail_before_a_thread_is_opened(
    spawner: Spawner,
    server: _Server,
    fenced: Callable[..., Fence],
    tmp_path: Path,
    requirements: dict[str, Any],
    approvals: str,
) -> None:
    """No sandbox at all, a hook never asked, or a model reviewing: none is run at all."""
    server.requirements = requirements
    agent = _agent(fence=fenced(tmp_path), approvals=approvals)
    with pytest.raises(Failed, match="configRequirements/read") as failed:
        agent.new(tmp_path)("hi")
    assert "allow approval policies" in str(failed.value)
    assert not server.called("thread/start")
    assert not server.called("turn/start")


def test_a_refused_read_only_sandbox_is_widened_where_the_fence_holds_it(
    spawner: Spawner,
    server: _Server,
    fenced: Callable[..., Fence],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Around Codex here, the fence holds the writes the wider sandbox would allow."""
    monkeypatch.setattr("sys.platform", "linux")
    server.refusing["thread/start"] = dict(_READ_ONLY_FORBIDDEN)
    _agent(fence=fenced(tmp_path, READ)).new(tmp_path)("hi")
    refused, widened = server.called("thread/start")
    assert refused["sandbox"] == "read-only"
    assert (widened["sandbox"], widened["approvalPolicy"]) == (
        "workspace-write",
        "never",
    )


def test_a_turn_refused_for_requirements_picks_its_thread_up_under_what_they_leave(
    spawner: Spawner, server: _Server, fenced: Callable[..., Fence], tmp_path: Path
) -> None:
    """Requirements that changed under a running server, or one too old to be asked."""
    session = _agent(fence=fenced(tmp_path)).new(tmp_path)
    session("hi")
    server.refusing["turn/start"] = dict(_NEVER_FORBIDDEN)
    assert session("again") == "done"
    (resumed,) = server.called("thread/resume")
    assert (resumed["sandbox"], resumed["approvalPolicy"]) == (
        "danger-full-access",
        "on-request",
    )
    *_, refused, taken = server.called("turn/start")
    assert (refused["approvalPolicy"], taken["approvalPolicy"]) == (
        "never",
        "on-request",
    )


def test_a_refusal_that_leaves_nothing_fails_naming_where_it_was_set(
    spawner: Spawner, server: _Server, fenced: Callable[..., Fence], tmp_path: Path
) -> None:
    """Requirements that changed after they were read, said as Codex's own code names them."""
    server.requirements = {"allowedApprovalPolicies": ["never", "untrusted"]}
    server.refusing["thread/start"] = {
        "code": -32600,
        "message": "invalid value for `approval_policy`: `UnlessTrusted` is not in the"
        " allowed set [Never] (set by /etc/codex/requirements.toml)",
    }
    with pytest.raises(Failed, match=r"/etc/codex/requirements\.toml") as failed:
        _agent(fence=fenced(tmp_path), approvals="untrusted").new(tmp_path)("hi")
    assert "refused: untrusted" in str(failed.value)
    assert len(server.called("thread/start")) == 1


def test_a_thread_codex_s_sandbox_holds_asks_where_never_is_forbidden_and_is_refused(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A yes is a command run outside the one sandbox that holds the fence."""
    monkeypatch.setattr(CodexAgent, "holds", _holding)
    server.requirements = {"allowedApprovalPolicies": ["on-request"]}

    def asks(proc: Process, thread: str, turn: str) -> None:
        proc.say(
            {
                "id": 901,
                "method": "item/commandExecution/requestApproval",
                "params": {"threadId": thread, "turnId": turn, "command": "curl x"},
            }
        )
        server.after[901] = lambda: _says(_message("done"))(proc, thread, turn)

    server.turns = [asks]
    held = Fence.of(
        rules=[(".", WRITE)], online=False, workdir=tmp_path, home=tmp_path / "home"
    )
    _agent(fence=held).new(tmp_path)("hi")
    (opened,) = server.called("thread/start")
    assert (opened["sandbox"], opened["approvalPolicy"]) == (
        "workspace-write",
        "on-request",
    )
    (reply,) = [one for one in server.replies if one.get("id") == 901]
    assert reply["result"] == {"decision": "decline"}


def test_a_thread_codex_s_sandbox_holds_is_never_opened_wider_or_writing_less(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full access steps outside the one sandbox; `read-only` refuses what the fence writes."""
    monkeypatch.setattr(CodexAgent, "holds", _holding)
    server.requirements = {"allowedSandboxModes": ["read-only", "danger-full-access"]}
    held = Fence.of(
        rules=[(".", WRITE)], online=False, workdir=tmp_path, home=tmp_path / "home"
    )
    with pytest.raises(Failed, match="sandbox workspace-write"):
        _agent(fence=held).new(tmp_path)("hi")
    assert not server.called("thread/start")


def test_a_step_down_is_told_once_to_each_agent_watching(
    spawner: Spawner, server: _Server, fenced: Callable[..., Fence], tmp_path: Path
) -> None:
    told: dict[str, list[str]] = {}
    agents = [_agent(fence=fenced(tmp_path)) for _ in range(2)]
    for agent in agents:
        agent.watch(
            lambda who, _session, event: (
                told.setdefault(who.id, []).append(event.text)
                if event.kind == "notice"
                else None
            )
        )
        server.refusing["thread/start"] = dict(_FORBIDS)
        agent.new(tmp_path)("hi")
        agent.new(tmp_path)("again")
    said = (
        "codex: this machine's requirements will not run an agent at sandbox"
        " danger-full-access with approval never, so it runs at sandbox workspace-write"
        " with approval on-request, where what it asks for is granted"
    )
    assert told == {agent.id: [said] for agent in agents}


def test_a_native_codex_cut_off_the_network_is_not_configured_from_this_machines(
    spawner: Spawner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The target's Codex runs the command, so this machine's features say nothing of it."""
    monkeypatch.setattr(fence, "enforceable", fenceable)
    # The target is never reached here: only what was started on the way to it matters.
    spawner.script = lambda proc: proc.exit(255)
    anchor = AnchorConfig(target="ssh://box", workspace=str(tmp_path), native=True)
    offline = Fence.of(
        rules=[("/", READ), (".", WRITE)],
        online=False,
        workdir=tmp_path,
        home=tmp_path / "home",
    )
    agent = _agent(machine=AnchoredConfig(anchor=anchor), fence=offline)
    with contextlib.suppress(Exception):
        agent.new(tmp_path)("hi")
    assert spawner.started
    assert not [one for one in spawner.started if "features" in one.args]


def test_a_server_that_goes_away_fails_the_turn(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.turns = [lambda proc, thread, turn: proc.exit(1)]
    with pytest.raises(Failed, match="stopped mid-turn"):
        _agent().new(tmp_path)("hi")


@pytest.mark.parametrize(
    ("local", "refuse", "decision"),
    [
        (WRITE, False, "accept"),
        (READ, False, "accept"),
        (WRITE, True, "decline"),
        (None, False, "decline"),
    ],
)
def test_an_approval_is_granted_under_a_fence_unless_a_hook_refuses(
    spawner: Spawner,
    server: _Server,
    fenced: Callable[..., Fence],
    tmp_path: Path,
    local: str | None,
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
                "params": {
                    "threadId": thread,
                    "turnId": turn,
                    "command": "rm -rf build",
                },
            }
        )
        server.after[900] = lambda: _says(_message("done"))(proc, thread, turn)

    server.turns = [asks]
    agent = _agent(fence=None if local is None else fenced(tmp_path, local))
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
                    "turnId": turn,
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


# --------------------------------------------------------------- through a LiteLLM gateway


class _Gateway:
    """A gateway that starts nothing: where it would be, and whether it was taken down."""

    started: ClassVar[list[_Gateway]] = []

    def __init__(self, provider: Provider) -> None:
        self.account = provider
        self.port = 4321
        self.url = "http://127.0.0.1:4321"
        self.key = "sk-master"
        self.running = True
        _Gateway.started.append(self)

    def stop(self) -> None:
        self.running = False


_ROUTED = Provider(
    cli="codex",
    name="gw",
    way="litellm-anthropic-key",
    env={"ANTHROPIC_API_KEY": "upstream-secret"},
)


def _unswapped(_self: Provider) -> tuple[tuple[str, str], ...]:
    """No credential path answered by another, which the supervisor's tests are about."""
    return ()


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch) -> list[_Gateway]:
    """An account litellm holds, and a gateway that is only pretended."""

    def find(cli: str, name: str) -> Provider | None:
        return _ROUTED if name == "gw" else Provider(cli, name, way="")

    monkeypatch.setattr(providers, "find", find)
    monkeypatch.setattr(Provider, "swaps", _unswapped)
    monkeypatch.setattr(gateway, "Gateway", _Gateway)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "lying-about")
    _Gateway.started = []
    return _Gateway.started


def test_codex_through_a_gateway_speaks_the_responses_api_to_it(
    routed: list[_Gateway], spawner: Spawner, server: _Server
) -> None:
    agent = _agent(provider="gw", model="claude-x")

    agent.new()("hi")

    started = _servers(spawner)[0]
    argv = " ".join(started.args)
    assert "model_provider=humanize" in argv
    assert "model_providers.humanize.base_url=http://127.0.0.1:4321" in argv
    assert "model_providers.humanize.env_key=CODEX_PROVIDER_KEY" in argv
    assert "model_providers.humanize.wire_api=responses" in argv
    assert "sk-master" not in argv
    env = started.environ
    assert env["CODEX_PROVIDER_KEY"] == "sk-master"
    assert "ANTHROPIC_API_KEY" not in env
    assert "upstream-secret" not in env.values()
    # The model as it was named, which the gateway sends on to the account's provider.
    assert server.called("thread/start")[0]["model"] == "claude-x"
    agent.stop()
    assert not routed[0].running


def test_a_thread_whose_gateway_went_away_is_picked_up_on_a_server_at_the_next(
    routed: list[_Gateway], spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    agent = _agent(provider="gw")
    session = agent.new(tmp_path)
    session("one")
    routed[0].running = False

    session("two")

    first, _ = _servers(spawner)
    assert first.returncode is not None
    assert len(routed) == 2
    assert routed[1].running
    assert server.called("thread/resume")[0]["threadId"] == "th-1"


def test_a_recalled_thread_is_forked_by_a_codex_run_here_for_another_machine(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Brought in where this Codex keeps its threads, which it finds by id: no copy per place.

    Its work is on another machine, at `/far/desk` as that machine names it, and it runs here
    in this machine's mirror of that work -- where the fork is cut.
    """
    home = tmp_path / "home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv(KEEPING, "off")
    mirror = tmp_path / "mirror"
    (mirror / "desk").mkdir(parents=True)
    rollout = Path("sessions", "2026", "10", "13", "rollout-2026-10-13-told.jsonl")
    kept = tmp_path / "snapshot"
    (kept / rollout).parent.mkdir(parents=True)
    (kept / rollout).write_text('{"payload": {"id": "told"}}\n')
    anchor = AnchorConfig(target="ssh://box", workspace="/far", shadow=str(mirror))
    agent = _agent(machine=AnchoredConfig(anchor=anchor))

    agent.recall("told", kept, "/far/desk").fork()("go on")

    (forked,) = server.called("thread/fork")
    assert (forked["threadId"], forked["cwd"]) == ("told", str(mirror / "desk"))
    assert (home / rollout).read_text() == (kept / rollout).read_text()


def _native(session: CodexSession, line: str) -> str:
    """What a native turn of `line` answered with."""
    *_, result = session.stream(line, native=True)
    assert result.kind == "result"
    return result.text


def test_the_catalogue_is_the_skills_the_sigils_and_the_commands_codex_serves(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.skills = [
        {"name": "lint", "path": "/s/lint/SKILL.md", "description": "lints"},
        {
            "name": "off",
            "path": "/s/off/SKILL.md",
            "description": "x",
            "enabled": False,
        },
    ]
    listed = {
        (one.sigil, one.name): one.how for one in _agent().new(tmp_path).natives()
    }
    assert listed[("$", "lint")] == "call"
    assert ("$", "off") not in listed
    assert listed[("@", "")] == listed[("!", "")] == "call"
    for name in ("compact", "review", "rename", "model", "effort"):
        assert listed[("/", name)] == "call"
    for name in ("permissions", "mcp", "logout", "status"):
        assert listed[("/", name)] == "refuse"
    for name in ("clear", "resume", "exit", "quit", "btw"):
        assert ("/", name) not in listed
    (asked,) = server.called("skills/list")
    assert asked["cwds"] == [str(tmp_path)]


def test_the_skills_are_listed_again_once_a_conversation_opens(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    session = _agent().new(tmp_path)
    session.natives()
    session.natives()
    assert len(server.called("skills/list")) == 1
    server.skills = [{"name": "new", "path": "/s/new/SKILL.md", "description": "x"}]
    session("hi")
    assert ("$", "new") in {(one.sigil, one.name) for one in session.natives()}


def test_a_shell_command_is_the_servers_own_and_answers_with_its_output(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.output = ("hi\nerr\n", 3)
    session = _agent().new(tmp_path)
    assert _native(session, "!echo hi; exit 3") == "hi\nerr\n(exit 3)"
    (ran,) = server.called("thread/shellCommand")
    assert ran == {"threadId": "th-1", "command": "echo hi; exit 3"}
    assert not server.called("turn/start")
    assert session.id == "th-1"


def test_a_shell_command_is_left_to_the_chat_where_codex_s_sandbox_holds_the_fence(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The server's shell command runs unsandboxed, and nothing else is around Codex."""
    monkeypatch.setattr(CodexAgent, "holds", _holding)
    held = Fence.of(
        rules=[(".", WRITE)], online=True, workdir=tmp_path, home=tmp_path / "home"
    )
    session = _agent(fence=held).new(tmp_path)
    shell = [one for one in session.natives() if one.sigil == "!"]
    assert [one.how for one in shell] == ["emulate"]
    _native(session, "!rm -rf /")
    assert not server.called("thread/shellCommand")
    (turned,) = server.called("turn/start")
    assert turned["input"] == [{"type": "text", "text": "!rm -rf /"}]


def test_a_thread_codex_s_sandbox_holds_is_opened_in_it_and_asks_nothing(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full access may be forbidden and stepped down to asking, and a yes leaves the sandbox."""
    monkeypatch.setattr(CodexAgent, "holds", _holding)
    held = Fence.of(
        rules=[(".", WRITE)], online=False, workdir=tmp_path, home=tmp_path / "home"
    )
    _agent(fence=held).new(tmp_path)("hi")
    (opened,) = server.called("thread/start")
    assert (opened["sandbox"], opened["approvalPolicy"]) == ("workspace-write", "never")
    (turned,) = server.called("turn/start")
    assert turned["approvalPolicy"] == "never"
    assert turned["sandboxPolicy"]["type"] == "workspaceWrite"


def test_a_skill_and_a_file_named_in_a_line_go_as_items_beside_it(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.skills = [{"name": "lint", "path": "/s/lint/SKILL.md", "description": "x"}]
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "shot.png").write_bytes(b"\x89PNG")
    line = "$lint @a.py, @shot.png and @nowhere $unknown"
    _native(_agent().new(tmp_path), line)
    (turned,) = server.called("turn/start")
    assert turned["input"] == [
        {"type": "localImage", "path": str(tmp_path / "shot.png")},
        {"type": "text", "text": line},
        {"type": "skill", "name": "lint", "path": "/s/lint/SKILL.md"},
        {"type": "mention", "name": "a.py", "path": str(tmp_path / "a.py")},
    ]


def test_a_line_that_is_not_native_is_text_whatever_it_starts_with(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text("")
    session = _agent().new(tmp_path)
    lines = ("/compact", "!ls", "@a.py", "$lint")
    for line in lines:
        session(line)
    assert [one["input"] for one in server.called("turn/start")] == [
        [{"type": "text", "text": line}] for line in lines
    ]
    assert not server.called("skills/list")


def test_compact_is_the_servers_own_and_waits_for_it_to_finish(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    session = _agent().new(tmp_path)
    session("hi")
    events = list(session.stream("/compact", native=True))
    assert server.called("thread/compact/start") == [{"threadId": "th-1"}]
    assert events[-1].kind == "result"
    assert any(one.text.startswith("contextCompaction") for one in events)
    assert len(server.called("turn/start")) == 1


@pytest.mark.parametrize(
    ("line", "target"),
    [
        ("/review", {"type": "uncommittedChanges"}),
        ("/review base main", {"type": "baseBranch", "branch": "main"}),
        ("/review commit abc123", {"type": "commit", "sha": "abc123"}),
        ("/review look at auth", {"type": "custom", "instructions": "look at auth"}),
    ],
)
def test_review_is_a_turn_of_the_servers_own_review(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    line: str,
    target: dict[str, str],
) -> None:
    server.turns = [_says(_message("no findings"))]
    assert _native(_agent().new(tmp_path), line) == "no findings"
    (asked,) = server.called("review/start")
    assert asked == {"threadId": "th-1", "target": target, "delivery": "inline"}


def test_a_review_answers_with_its_findings_and_is_priced_at_the_model(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.turns = [
        _says(
            {"type": "exitedReviewMode", "id": "x", "review": "one finding"},
            total=(10, 5),
        )
    ]
    *_, result = _agent().new(tmp_path).stream("/review", native=True)
    assert result.text == "one finding"
    assert dict(result.tokens) == {"gpt-x": 15}


def test_a_review_waits_for_a_turn_held_to_a_fence_codex_s_sandbox_holds(
    spawner: Spawner,
    server: _Server,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`review/start` takes no sandbox: it runs at what the thread's last turn was sent."""
    monkeypatch.setattr(CodexAgent, "holds", _holding)
    held = Fence.of(
        rules=[(".", WRITE)], online=False, workdir=tmp_path, home=tmp_path / "home"
    )
    session = _agent(fence=held).new(tmp_path)
    assert "held to its fence yet" in _native(session, "/review")
    assert not server.called("review/start")
    session("hi")
    _native(session, "/review")
    assert len(server.called("review/start")) == 1


def test_an_operation_ends_on_its_own_turn_not_on_one_said_late(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    server.output, server.stray = ("hi\n", 0), True
    assert _native(_agent().new(tmp_path), "!echo hi") == "hi\n"


def test_a_fork_runs_on_the_model_a_chat_moved_its_parent_to(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    session = _agent().new(tmp_path)
    session("hi")
    _native(session, "/model gpt-z")
    session.fork()("go on")
    assert server.called("thread/fork")[0]["model"] == "gpt-z"
    assert server.called("turn/start")[-1]["model"] == "gpt-z"


def test_rename_names_the_thread(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    session = _agent().new(tmp_path)
    assert "auth work" in _native(session, "/rename auth work")
    assert server.called("thread/name/set") == [
        {"threadId": "th-1", "name": "auth work"}
    ]


def test_model_and_effort_move_the_next_turns(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    session = _agent(effort="low").new(tmp_path)
    assert "gpt-y" in _native(session, "/model gpt-y high")
    assert "medium" in _native(session, "/effort medium")
    assert not spawner.started  # nothing of Codex's was asked
    session("hi")
    (turned,) = server.called("turn/start")
    assert (turned["model"], turned["effort"]) == ("gpt-y", "medium")
    assert session.model == "gpt-y"
    assert _native(session, "/model") == "model gpt-y, effort medium"


def test_an_effort_codex_has_no_word_for_is_refused_and_left(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    session = _agent(effort="low").new(tmp_path)
    assert "ultracode" in _native(session, "/effort ultracode")
    assert session.effort == "low"


@pytest.mark.parametrize(
    ("line", "said"),
    [
        ("/permissions", "/permissions is served only by Codex's own interactive"),
        ("/nope now", "Unrecognized command '/nope'"),
        ("/rename", "/rename needs"),
    ],
)
def test_a_command_codex_would_not_send_is_answered_without_a_turn(
    spawner: Spawner, server: _Server, tmp_path: Path, line: str, said: str
) -> None:
    assert _native(_agent().new(tmp_path), line).startswith(said)
    assert not server.called("turn/start")


def test_a_path_is_not_a_command(
    spawner: Spawner, server: _Server, tmp_path: Path
) -> None:
    _native(_agent().new(tmp_path), "/usr/bin/env is odd")
    (turned,) = server.called("turn/start")
    assert turned["input"] == [{"type": "text", "text": "/usr/bin/env is odd"}]
