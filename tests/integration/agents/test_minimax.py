"""MiniMax Code, driven against a stand-in that prints what the real one prints.

What is checked is the call each turn is made of -- the permission each rung comes to, the
rung a model is asked for, the session it carries on -- and the turn read back out of the JSON
lines `mcode exec` answers in, the agents it starts of its own included: MiniMax Code says on
the same stream when a turn reaches for its `task` tool and when that one has come back.

The stand-in is written here and put on PATH, so nothing real is installed and nothing is
reached over a network. What it prints is what `mcode 0.5.9` printed for the same turns against
an endpoint on the loopback, field for field.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel

from hmz.coganchor import models
from hmz.coganchor.agents import (
    KEEPING,
    SUBAGENTS,
    MiniMaxCodeAgent,
    MiniMaxCodeAgentConfig,
    Moment,
    Occasion,
    Unfenced,
    Unserved,
    Verdict,
)
from tests.agents import standins

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor.fence import Fence

#: The model every turn here is asked for, as MiniMax Code spells one it was given.
_MODEL = "custom_provider:gateway/minimax-m3"

#: The configuration the tests start from.
_CONFIG = MiniMaxCodeAgentConfig(model=_MODEL, effort="", permission="bypass")

#: An `mcode exec --output-format stream-json`: it writes down how it was called and what it
#: was sent, and answers as the real one answers. A prompt of `fleet` sends an agent of its
#: own out and brings it back; one of `boom` is the turn that failed, which it says on the
#: lines it ends on and in its exit status.
_MCODE_STUB = """
import json, pathlib, sys

argv = sys.argv[1:]
prompt = sys.stdin.read()
with pathlib.Path(LOG).open("a") as stream:
    json.dump({"argv": argv, "stdin": prompt}, stream)
    stream.write("\\n")

flags = dict(zip(argv, argv[1:]))
session = flags.get("--session", "mvs_0123456789abcdef0123456789abcdef")
turn = "turn_munfl4ij_x2gprt"
at = [0]


def say(kind, **rest):
    at[0] += 1
    print(json.dumps({"schemaVersion": 1, "sequence": at[0], "timestampMs": 1790731982134,
                      "runId": "exec_" + turn, "sessionId": session, "turnId": turn,
                      "type": kind, **rest}), flush=True)


def tool(call, name, status, **rest):
    return {"id": call, "type": "tool_call",
            "toolCall": {"id": call, "name": name, "status": status, **rest}}


model = {"providerId": "custom_provider:gateway", "modelId": "minimax-m3",
         "variant": "thinking", "providerSource": "custom_provider",
         "providerKind": "custom", "protocol": "openai-completions"}
say("exec.started")
say("session.resumed" if "--session" in flags else "session.started")
say("turn.started")
say("item.started", item=tool("call_1", "bash", 4))
say("item.updated", item=tool("call_1", "bash", 5))
say("item.updated", item=tool("call_1", "bash", 1, input={"command": "ls src"}))
say("item.completed", item=tool("call_1", "bash", 2, input={"command": "ls src"},
                                 output={"content": [{"type": "text", "text": "x.py"}]}))
if prompt == "fleet":
    ask = {"description": "read the tests", "prompt": "read them",
           "subagent_type": "explore"}
    say("item.started", item=tool("call_2", "task", 4))
    say("item.updated", item=tool("call_2", "task", 1, input=ask))
    say("item.completed", item=tool("call_2", "task", 2, input=ask,
                                     output={"content": [{"type": "text", "text": "done"}]}))
say("item.started", item={"id": "m1:reasoning", "type": "reasoning", "contentDelta": "hm"})
say("item.completed", item={"id": "m1:reasoning", "type": "reasoning", "content": "hmm"})
answer = prompt
if "--output-schema" in flags:
    answer = json.dumps({"answer": prompt})
say("item.started", item={"id": "m1:message", "type": "agent_message",
                          "contentDelta": answer[:1]})
say("item.completed", item={"id": "m1:message", "type": "agent_message",
                            "content": answer})
if prompt == "boom":
    error = {"category": "runtime", "message": "the model refused", "retryable": False}
    say("turn.failed", status="failed", error=error, durationMs=12)
    say("exec.completed", result={"schemaVersion": 1, "type": "exec.result",
                                  "runId": "exec_" + turn, "sessionId": session,
                                  "turnId": turn, "status": "failed", "error": error,
                                  "durationMs": 12})
    print("mcode exec failed: The run failed: the model refused.", file=sys.stderr)
    raise SystemExit(4)
usage = {"inputTokens": 130, "outputTokens": 12, "cacheReadTokens": 90,
         "totalTokens": 142}
say("turn.completed", model=model, usage=usage, usageSource="completed_responses",
    usageIncomplete=False, durationMs=711)
result = {"schemaVersion": 1, "type": "exec.result", "runId": "exec_" + turn,
          "sessionId": session, "turnId": turn, "status": "succeeded", "model": model,
          "usage": usage, "durationMs": 711}
result["output"] = json.loads(answer) if "--output-schema" in flags else answer
say("exec.completed", result=result)
"""

#: What `mcode provider list --json` prints, with a provider added to it and the two MiniMax
#: sources it always lists and never lists a model under.
_LISTED = """
import json

print(json.dumps({"minimaxModelSource": "token_plan", "providers": [
    {"providerId": "minimax_oauth", "name": "MiniMax OAuth", "kind": "minimax-oauth",
     "active": True, "enabled": True, "readOnly": True, "hasApiKey": False, "models": []},
    {"providerId": "minimax_api", "name": "MiniMax API Key", "kind": "minimax-api-key",
     "active": False, "enabled": True, "readOnly": False, "hasApiKey": False, "models": []},
    {"providerId": "custom_provider:gateway", "name": "gateway", "kind": "custom",
     "active": True, "enabled": True, "readOnly": False, "apiFormat": "openai-completions",
     "baseUrl": "http://127.0.0.1:1/v1", "hasApiKey": True,
     "models": [{"modelId": "other", "displayName": "other", "selected": False},
                {"modelId": "minimax-m3", "displayName": "minimax-m3", "selected": True}]},
]}, indent=2))
"""


@dataclass(frozen=True)
class _Calls:
    """The stand-in on PATH, and how it was called."""

    log: Path

    def argv(self) -> list[list[str]]:
        return [json.loads(line)["argv"] for line in self.log.read_text().splitlines()]

    def stdin(self) -> list[str]:
        return [json.loads(line)["stdin"] for line in self.log.read_text().splitlines()]


def _install(binaries: Path, script: str, log: Path) -> None:
    """Puts a stand-in `mcode` on PATH, opening with what the real one refuses."""
    fake = binaries / "mcode"
    refuses = standins.refusing("mcode")
    fake.write_text(
        f"#!{sys.executable}\n{refuses}{script.replace('LOG', repr(str(log)))}"
    )
    fake.chmod(0o755)


@pytest.fixture
def mcode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Calls:
    """A stand-in `mcode` on PATH, printing what the real one prints."""
    log = tmp_path / "calls.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _install(binaries, _MCODE_STUB, log)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)
    return _Calls(log)


def _kept(named: dict[str, tuple[str, ...]]) -> None:
    """Writes a catalogue down as if this account had just been asked what it runs."""
    at = models.where("mcode")
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(
        json.dumps(
            {
                "asked": "2026-09-30T00:00:00Z",
                "models": [
                    {"name": name, "efforts": list(efforts), "swarms": False}
                    for name, efforts in named.items()
                ],
            }
        ),
        encoding="utf-8",
    )


def test_a_turn_is_one_run_of_exec_with_the_prompt_on_its_stdin(
    mcode: _Calls, tmp_path: Path
) -> None:
    """A prompt that opens with a dash is a prompt, and the workspace is said outright."""
    session = MiniMaxCodeAgent(_CONFIG).new()

    assert session("-hello") == "-hello"

    (argv,) = mcode.argv()
    assert argv[:6] == [
        "exec",
        "--output-format",
        "stream-json",
        "--input",
        "-",
        "--cwd",
    ]
    assert argv[6] == str(tmp_path)
    assert argv[argv.index("--model") + 1] == _MODEL
    assert mcode.stdin() == ["-hello"]
    # Nothing it was not asked for: no rung, no session, no shape.
    assert "--effort" not in argv
    assert "--session" not in argv
    assert "--output-schema" not in argv
    assert session.id == "mvs_0123456789abcdef0123456789abcdef"


def test_the_second_turn_carries_on_the_session_the_first_one_opened(
    mcode: _Calls,
) -> None:
    session = MiniMaxCodeAgent(_CONFIG).new()
    session("hello")

    session("again")

    first, second = mcode.argv()
    assert "--session" not in first
    assert second[second.index("--session") + 1] == session.id


#: What each rung it takes comes to on its own command line.
_RUNGS = (
    ("workspace-write", ["--permission", "full"]),
    ("auto", ["--permission", "smart"]),
    ("bypass", ["--permission", "full"]),
)


def test_a_rung_is_the_permission_policy_it_has_for_it(mcode: _Calls) -> None:
    for rung, _expected in _RUNGS:
        MiniMaxCodeAgent(replace(_CONFIG, permission=rung)).new()("hello")

    for argv, (rung, expected) in zip(mcode.argv(), _RUNGS, strict=True):
        at = argv.index("--permission")
        assert argv[at : at + 2] == expected, rung


def test_a_turn_nobody_said_a_rung_for_is_left_where_mcode_leaves_it(
    mcode: _Calls,
) -> None:
    MiniMaxCodeAgent(replace(_CONFIG, permission="")).new()("hello")

    (argv,) = mcode.argv()
    assert "--permission" not in argv


def test_read_only_is_a_rung_it_will_not_take() -> None:
    """It has none that changes nothing: a fence around it is the read-only it can have."""
    with pytest.raises(Unserved, match="read-only"):
        MiniMaxCodeAgent(replace(_CONFIG, permission="read-only"))


def test_a_turn_says_what_it_did_once_and_whole(mcode: _Calls) -> None:
    """A tool call once, when what it was called with is known; words once they are done."""
    session = MiniMaxCodeAgent(_CONFIG).new()

    said = list(session.stream("hello"))

    assert [event.kind for event in said] == ["tool", "reasoning", "text", "result"]
    assert said[0].text == "bash ls src"
    assert said[1].text == "hmm"
    assert said[-1].text == "hello"


def test_an_agent_of_its_own_is_said_as_one_rather_than_as_a_tool(
    mcode: _Calls,
) -> None:
    session = MiniMaxCodeAgent(_CONFIG).new()

    said = list(session.stream("fleet"))

    fleet = [event for event in said if event.kind.startswith("subagent")]
    assert [event.kind for event in fleet] == ["subagent", "subagent-ends"]
    assert {event.whose for event in fleet} == {"call_2"}
    assert fleet[0].text == "task read the tests"


def test_the_moments_about_a_fleet_are_fired_where_one_runs(mcode: _Calls) -> None:
    agent = MiniMaxCodeAgent(_CONFIG)
    seen: list[Occasion] = []

    def note(occasion: Occasion) -> Verdict | None:
        seen.append(occasion)
        return None

    assert MiniMaxCodeAgent.moments >= SUBAGENTS
    agent.hooks.on(Moment.SUBAGENT_START, note)
    agent.hooks.on(Moment.SUBAGENT_STOP, note)

    agent.new()("fleet")

    assert [one.moment for one in seen] == [Moment.SUBAGENT_START, Moment.SUBAGENT_STOP]
    assert {one.under for one in seen} == {"call_2"}


def test_a_turn_that_failed_says_so_rather_than_answering_with_it(
    mcode: _Calls,
) -> None:
    session = MiniMaxCodeAgent(_CONFIG).new()

    with pytest.raises(subprocess.CalledProcessError) as raised:
        session("boom")

    assert "the model refused" in str(raised.value)


def test_what_the_turn_cost_is_read_off_the_line_it_ends_on(mcode: _Calls) -> None:
    """Counted against the model the turn says it ran on, the input net of the cache."""
    agent = MiniMaxCodeAgent(_CONFIG)

    (answer,) = (one for one in agent.new().stream("hello") if one.kind == "result")

    assert dict(answer.spent) == {"input": 130, "output": 12, "cache_read": 90}
    assert answer.tokens == {_MODEL: 232}
    assert dict(agent.spent()) == dict(answer.spent)


def test_a_rung_is_asked_for_only_where_the_model_takes_one(mcode: _Calls) -> None:
    """Its catalogue says which of its models take a rung, and most of them take none."""
    _kept({_MODEL: (), "minimax/MiniMax-M3.1-Flash-Preview": ("max", "high")})

    MiniMaxCodeAgent(
        replace(_CONFIG, model="minimax/MiniMax-M3.1-Flash-Preview", effort="high")
    ).new()("hello")
    with pytest.raises(Unserved, match="at no rung at all"):
        MiniMaxCodeAgent(replace(_CONFIG, effort="high"))
    # And `auto`, which is the word for no rung, is what such a model is written at.
    MiniMaxCodeAgent(replace(_CONFIG, effort="auto")).new()("hello")

    high, unsaid = mcode.argv()
    assert high[high.index("--effort") + 1] == "high"
    assert "--effort" not in unsaid


def test_the_session_is_named_while_its_first_turn_is_still_running(
    mcode: _Calls,
) -> None:
    """Which is what a tally reads a turn's log by before the turn has landed."""
    session = MiniMaxCodeAgent(_CONFIG).new()
    named = [session.named for event in session.stream("hello") if event.kind == "tool"]

    assert named == ["mvs_0123456789abcdef0123456789abcdef"]


class _Answer(BaseModel):
    answer: str


def test_a_shape_is_held_by_its_own_structured_output(mcode: _Calls) -> None:
    session = MiniMaxCodeAgent(_CONFIG).new()

    shaped = session("hello", schema=_Answer)

    assert shaped == _Answer(answer="hello")
    (argv,) = mcode.argv()
    schema = json.loads(argv[argv.index("--output-schema") + 1])
    assert schema["required"] == ["answer"]
    assert schema["additionalProperties"] is False


def test_a_fence_that_cuts_the_network_is_refused(tmp_path: Path) -> None:
    """Its web search runs on MiniMax's own service, past any proxy that lets its model in."""
    from hmz.coganchor.fence import Fence

    fence = Fence.of(
        local="all",
        user="read",
        system="none",
        online=False,
        workdir=tmp_path,
        home=tmp_path,
    )
    with pytest.raises(Unfenced, match="online ALL"):
        MiniMaxCodeAgent(replace(_CONFIG, fence=fence))


def test_a_fenced_turn_takes_the_lock_beside_its_home_where_its_sessions_are_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one path it writes that a fence around the home cannot grant alone."""
    from hmz.coganchor.fence import Fence
    from hmz.coganchor.providers import redirect

    monkeypatch.setattr(redirect, "supervises", lambda: True)
    monkeypatch.delenv(KEEPING)
    home = tmp_path / "minimax"
    monkeypatch.setenv("MINIMAX_DATA_DIR", str(home))
    fence = Fence.of(
        local="all",
        user="read",
        system="none",
        online=True,
        workdir=tmp_path,
        home=tmp_path,
    )

    agents = MiniMaxCodeAgent(replace(_CONFIG, fence=fence)), MiniMaxCodeAgent(_CONFIG)
    for one in agents:
        one.keeps = tmp_path / "kept"
    fenced, unfenced = (dict(one._keeping_swaps()) for one in agents)

    lock = f"{home}.lock"
    assert fenced[lock] == f"{tmp_path}/kept/mcode/minimax.lock"
    assert lock not in unfenced
    assert f"{home}/v2/sqlite" in unfenced


def _fence(at: Path) -> Fence:
    """The recipe every CLI is put to, less the network cut `mcode` refuses."""
    from hmz.coganchor.fence import Fence

    return Fence.of(
        local="all", user="read", system="none", online=True, workdir=at, home=at
    )


def test_a_fenced_turn_keeping_no_session_takes_the_lock_in_this_machine_s_own_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent no run drives keeps no session, and the lock is answered all the same."""
    from hmz import machine
    from hmz.coganchor.providers import redirect

    monkeypatch.setattr(redirect, "supervises", lambda: True)
    home = tmp_path / "minimax"
    monkeypatch.setenv("MINIMAX_DATA_DIR", str(home))
    agent = MiniMaxCodeAgent(replace(_CONFIG, fence=_fence(tmp_path)))
    other = MiniMaxCodeAgent(replace(_CONFIG, fence=_fence(tmp_path)))

    argv = agent.spawned(["mcode", "exec"])

    lock = f"{home}.lock"
    instead = str(machine() / "mcode" / "minimax.lock")
    assert dict(agent._keeping_swaps()) == {lock: instead}
    # One lock for every agent of the machine, since they share the one home it guards.
    assert dict(other._keeping_swaps()) == {lock: instead}
    # Made before the turn is spawned, which is what lets the lock be made in it.
    assert os.path.isdir(os.path.dirname(instead))  # noqa: PTH112, PTH120
    assert f"--keep={lock}={instead}" in argv
    assert argv[-1] == "exec"
    assert MiniMaxCodeAgent(_CONFIG)._keeping_swaps() == ()


def test_a_machine_that_cannot_supervise_leaves_the_lock_to_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing to answer the path with, so it is not asked for: the turn is spawned bare."""
    from hmz.coganchor.providers import redirect

    monkeypatch.setattr(redirect, "supervises", lambda: False)
    agent = MiniMaxCodeAgent(replace(_CONFIG, fence=_fence(tmp_path)))

    assert agent._keeping_swaps() == ()
    assert "cred" not in agent.spawned(["mcode", "exec"])


@pytest.fixture
def listing(asking: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stand-in `mcode` with a provider added to it, and a home to keep the answer in."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _install(binaries, _LISTED, tmp_path / "listed.jsonl")
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))


def test_what_it_runs_is_what_was_added_to_it_and_minimax_s_own(listing: None) -> None:
    """The default first, each at no rung; then its own, the one that takes rungs at them."""
    found = models.ask("mcode")

    assert [(one.name, one.efforts) for one in found] == [
        ("custom_provider:gateway/minimax-m3", ()),
        ("custom_provider:gateway/other", ()),
        ("minimax/MiniMax-M3", ()),
        (
            "minimax/MiniMax-M3.1-Flash-Preview",
            ("max", "xhigh", "high", "medium", "low"),
        ),
        ("minimax/MiniMax-M2.7", ()),
        ("minimax/MiniMax-M2.7-highspeed", ()),
    ]
