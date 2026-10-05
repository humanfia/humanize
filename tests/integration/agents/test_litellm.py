"""litellm, for real, against the loopback endpoint: a flow's turns as chat completions.

The real litellm package, sending real requests to `tests/llm.py`'s OpenAI-compatible service
through a gateway account -- so what is checked is what litellm actually puts on the wire for
a turn, a second turn, a fork and a shape, and what the run makes of what comes back.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor.agents import LiteLLMAgent, LiteLLMAgentConfig
from hmz.sdk import Hmz
from tests.llm import KEY, MOCKED, SAYS
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

    from tests.llm import Serving

pytest.importorskip("litellm")

#: A flow that takes two turns in one session, forks it, asks for a shape, and is refused an
#: environment -- every way a flow reaches a litellm agent.
FLOW = '''"""Talks to a model, and keeps what it said."""

import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowParams,
    LocalEnv,
    UnsupportedOperation,
    flow,
)


class Agents(AgentCollection):
    r: Agent


class Envs(EnvCollection):
    here: LocalEnv


class Verdict(pydantic.BaseModel):
    ok: bool


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def talks(task, *, agents, envs, params, ctx):
    agent = agents["r"]
    session = await agent.spawn()
    said = [await agent.run(task, session=session)]
    try:
        await agent.run("somewhere", session=session, env=envs["here"])
    except UnsupportedOperation as refused:
        said.append(str(refused))
    said.append(await agent.run("again", session=session))
    forked = await agent.fork(session)
    said.append(await agent.run("aside", session=forked))
    verdict = await agent.run("judge", session=session, output_schema=Verdict)
    said.append(verdict.ok)
    said.append(session.usage.output_tokens)
    return said
'''


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home of the test's own, which is where litellm keeps what no run keeps."""
    held = tmp_path / "home"
    monkeypatch.setenv("HOME", str(held))
    return held


def _messages(llm: Serving) -> list[list[dict[str, Any]]]:
    return [
        cast("list[dict[str, Any]]", took.body["messages"])
        for took in llm.taken
        if took.method == "POST"
    ]


def test_a_turn_is_a_chat_completion_through_the_account(
    llm: Serving, tmp_path: Path, home: Path
) -> None:
    del home
    llm.account("litellm")
    agent = LiteLLMAgent(
        LiteLLMAgentConfig(model="mock/first-model", effort="", provider=MOCKED)
    )
    agent.keeps = tmp_path / "kept"
    session = agent.new()

    assert session("hello") == SAYS
    assert session("and again") == SAYS

    (first, second) = [took for took in llm.taken if took.method == "POST"]
    assert first.path == "/chat/completions"
    assert first.secret == KEY
    assert first.body["model"] == "mock/first-model"
    assert first.body["stream"] is True
    assert _messages(llm)[1] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": SAYS},
        {"role": "user", "content": "and again"},
    ]
    assert second.prompt == "and again"
    spent = session.spent()
    assert spent.output == 2 * len(SAYS.split())
    assert spent.input > 0


def test_a_flow_runs_its_turns_on_litellm(
    llm: Serving, tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del home
    monkeypatch.chdir(tmp_path)
    llm.account("litellm")
    written(tmp_path, "flow", FLOW)
    # One reply for every turn, which is a shape as well as words.
    llm.says = json.dumps({"ok": True})

    said = (
        Hmz()
        .run(
            tmp_path / "flow",
            "hello",
            agents={"r": f"litellm@{MOCKED}/openai/mock/first-model"},
            envs={"here": f"local{tmp_path}"},
            budget={"cost": 1},
        )
        .run()
    )

    assert said[0] == llm.says
    assert "run it with env=None" in said[1]
    assert said[2:4] == [llm.says, llm.says]
    assert said[4] is True
    assert said[5] > 0
    turns = _messages(llm)
    assert len(turns) == 4
    # The fork carried what its session had said, and went its own way from there.
    assert turns[2][:-1] == turns[1][:4]
    assert turns[2][-1] == {"role": "user", "content": "aside"}
    # And the session it was cut from never heard what the fork was asked.
    assert {"role": "user", "content": "aside"} not in turns[3]
    shaped = [took for took in llm.taken if took.method == "POST"][3]
    assert shaped.body["response_format"]["type"] == "json_schema"
