"""`hmz.coganchor.agents.tools`: a flow's own callbacks, offered to its agents over MCP."""

from __future__ import annotations

import json
from typing import Any, NoReturn

import pytest
from pydantic import BaseModel, Field

from hmz.coganchor import __version__
from hmz.coganchor.agents.tools import PROTOCOL, Tool, Toolbox, serve


class _Task(BaseModel):
    name: str = Field(description="what to do")
    times: int = 1


def _nothing() -> None:
    return None


def _named(task: _Task) -> str:
    return task.name * task.times


def _listed() -> dict[str, Any]:
    return {"a": [1, 2]}


def _broken() -> NoReturn:
    raise KeyError("task")


def _plain_broken() -> NoReturn:
    raise ValueError


_TOOLS = (
    Tool(name="noop", about="does nothing", call=_nothing),
    Tool(name="echo", about="says it", call=_named, takes=_Task),
    Tool(name="data", about="answers data", call=_listed),
    Tool(name="broken", about="fails", call=_broken),
    Tool(name="plain", about="fails plainly", call=_plain_broken),
)


def _offered() -> tuple[Tool, ...]:
    return _TOOLS


def test_schema_of_a_tool_that_takes_nothing() -> None:
    assert _TOOLS[0].schema() == {"type": "object", "properties": {}}


def test_schema_of_a_tool_is_its_models() -> None:
    assert _TOOLS[1].schema() == _Task.model_json_schema()


@pytest.mark.parametrize(
    ("tool", "given", "said"),
    [
        (_TOOLS[0], {}, "done"),
        (_TOOLS[1], {"name": "ab", "times": 2}, "abab"),
        (_TOOLS[2], {}, '{"a": [1, 2]}'),
    ],
)
def test_called_says_what_the_callback_answered(
    tool: Tool, given: dict[str, Any], said: str
) -> None:
    assert tool.called(given) == said


def test_called_lets_the_callbacks_failure_through() -> None:
    with pytest.raises(KeyError):
        _TOOLS[3].called({})


def _call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": 7, "method": method}
    if params is not None:
        message["params"] = params
    return serve(json.dumps(message), _offered)


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        "[]",
        '{"jsonrpc": "2.0", "id": 1}',
        '{"jsonrpc": "2.0", "method": "notifications/initialized"}',
    ],
)
def test_serve_answers_nothing_to_what_is_not_a_request(line: str) -> None:
    assert serve(line, _offered) is None


def test_serve_initialize() -> None:
    assert _call("initialize") == {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "humanize", "version": __version__},
        },
    }


def test_serve_ping() -> None:
    assert _call("ping") == {"jsonrpc": "2.0", "id": 7, "result": {}}


def test_serve_lists_the_tools_as_offered_now() -> None:
    said = _call("tools/list")
    assert said is not None
    listed = said["result"]["tools"]
    assert [one["name"] for one in listed] == [one.name for one in _TOOLS]
    assert listed[1] == {
        "name": "echo",
        "description": "says it",
        "inputSchema": _Task.model_json_schema(),
    }


@pytest.mark.parametrize(
    ("params", "text", "error"),
    [
        ({"name": "echo", "arguments": {"name": "x"}}, "x", False),
        ({"name": "noop"}, "done", False),
        ({"name": "broken"}, "KeyError: 'task'", True),
        ({"name": "plain"}, "ValueError", True),
        ({"name": "echo", "arguments": {}}, "ValidationError", True),
    ],
)
def test_serve_calls_a_tool(params: dict[str, Any], text: str, error: bool) -> None:
    said = _call("tools/call", params)
    assert said is not None
    result = said["result"]
    assert result["isError"] is error
    assert result["content"][0]["type"] == "text"
    assert text in result["content"][0]["text"]


@pytest.mark.parametrize(
    ("method", "params", "code"),
    [
        ("resources/list", None, -32601),
        ("tools/call", {"name": "missing"}, -32602),
        ("tools/call", None, -32602),
    ],
)
def test_serve_refuses(method: str, params: dict[str, Any] | None, code: int) -> None:
    said = _call(method, params)
    assert said is not None
    assert said["id"] == 7
    assert said["error"]["code"] == code
    assert said["error"]["message"]


def test_a_toolbox_holds_one_tool_per_name_in_the_order_offered() -> None:
    box = Toolbox()
    assert box.empty()
    assert box.offered() == ()
    other = Tool(name="noop", about="another noop", call=_nothing)
    box.offers(1, _TOOLS[:2])
    box.offers(2, [other, _TOOLS[2]])
    assert not box.empty()
    assert box.offered() == (_TOOLS[0], _TOOLS[1], _TOOLS[2])
    box.offers(1, ())
    assert box.offered() == (other, _TOOLS[2])
    box.offers(2, [])
    box.offers(3, [])
    assert box.empty()


def test_closing_a_toolbox_that_never_served_is_harmless() -> None:
    box = Toolbox()
    box.close()
    box.close()
