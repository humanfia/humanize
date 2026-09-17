"""Cursor Agent, driven against a stand-in that prints what the real one prints.

What is checked is the call each turn is made of -- the id the rung is written into, the rung
each permission comes to, the chat it resumes -- and the turn read back out of the NDJSON it
answers in, subagents included: Cursor is one of the backends that says on the same stream
when a turn starts an agent of its own and when that one comes back.

The stand-in is written here and put on PATH, so nothing real is installed and nothing is
reached over a network; what this driver settles without running anything at all -- the id it
spells, and the settings it refuses -- is in `tests/unit/agents/test_cursor.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import models, providers
from hmz.coganchor.agents import (
    SUBAGENTS,
    CursorAgent,
    CursorAgentConfig,
    Moment,
    Occasion,
    Verdict,
)
from tests.agents import standins

if TYPE_CHECKING:
    from pathlib import Path

CURSOR = CursorAgentConfig(model="composer-2.5", effort="high")

#: A `cursor-agent --print`: it writes down how it was called, names the chat, says a thing or
#: two, and ends on the result. A prompt of `fleet` sends an agent of its own out and brings it
#: back; one of `boom` is the turn that failed, which Cursor says on the line it ends on.
_CURSOR_STUB = """
import json, pathlib, sys

argv = sys.argv[1:]
log = pathlib.Path(LOG)
with log.open("a") as stream:
    json.dump({"argv": argv}, stream)
    stream.write("\\n")

flags = dict(zip(argv, argv[1:]))
resumed = next((one for one in argv if one.startswith("--resume=")), "")
chat = resumed.partition("=")[2] or "chat-0001"
prompt = argv[-1]


def say(one):
    print(json.dumps(one), flush=True)


say({"type": "system", "subtype": "init", "session_id": chat, "cwd": ".",
     "model": flags.get("--model", ""), "permissionMode": "default"})
say({"type": "user", "message": {"role": "user",
                                 "content": [{"type": "text", "text": prompt}]},
     "session_id": chat})
say({"type": "tool_call", "subtype": "started", "call_id": "call-1",
     "tool_call": {"readToolCall": {"args": {"path": "src/x.py"}}},
     "session_id": chat})
if prompt == "fleet":
    say({"type": "tool_call", "subtype": "started", "call_id": "call-2",
         "tool_call": {"taskToolCall": {"args": {"description": "read the tests"}}},
         "session_id": chat})
    say({"type": "tool_call", "subtype": "completed", "call_id": "call-2",
         "tool_call": {"taskToolCall": {"args": {"description": "read the tests"},
                                        "result": {"success": {"content": "done"}}}},
         "session_id": chat})

def says(text):
    say({"type": "assistant",
         "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
         "session_id": chat})


if "--stream-partial-output" in argv:
    # A line per piece as it is written -- a paragraph break among them, which is a piece
    # like any other -- and then the pieces gathered up: asked for both, that is what it
    # writes, and the gathered one is the pieces rather than more of the turn.
    pieces = [prompt[:1], "\\n\\n", prompt[1:]]
    for piece in pieces:
        says(piece)
    says("".join(pieces))
else:
    says(prompt)
if prompt == "boom":
    say({"type": "result", "subtype": "error", "is_error": True,
         "result": "the model refused", "session_id": chat})
else:
    say({"type": "result", "subtype": "success", "is_error": False, "duration_ms": 12,
         "result": prompt,
         "usage": {"inputTokens": 100, "outputTokens": 20, "cacheReadTokens": 5,
                   "cacheWriteTokens": 3},
         "session_id": chat})
"""

#: What `cursor-agent --list-models` prints, colour and all.
_LISTED = """
import sys

print("\\x1b[1mAvailable models\\x1b[0m")
print()
print("\\x1b[36mcomposer-2.5\\x1b[0m \\x1b[2m- Composer 2.5\\x1b[0m \\x1b[2m(default)\\x1b[0m")
print("gpt-5 - GPT-5")
print("gpt-5-high - GPT-5 (high)")
print("gpt-5-fast - GPT-5 (fast)")
print("gpt-5-low-fast - GPT-5 (low, fast)")
print("gpt-5-high-fast - GPT-5 (high, fast)")
print("gpt-5.2 - GPT-5.2")
print("gpt-5.2-low - GPT-5.2 Low")
print("gpt-5.2-xhigh - GPT-5.2 Extra High")
print("gpt-5.5-extra-high - GPT-5.5 Extra High")
print("claude-opus-4-8 (current)")
print("sonnet-4.5-thinking - Claude Sonnet 4.5 (thinking)")
print("grok-code-fast-1")
print("cheetah")
print("auto")
print()
print("Tip: use $ agent --model <id>")
"""


@dataclass(frozen=True)
class _Calls:
    """The stand-in on PATH, and how it was called."""

    log: Path

    def argv(self) -> list[list[str]]:
        return [json.loads(line)["argv"] for line in self.log.read_text().splitlines()]


def _install(binaries: Path, script: str, log: Path) -> None:
    """Puts a stand-in `cursor-agent` on PATH.

    It opens with what that CLI refuses, so a driver that drifted onto a flag the real one
    has not got fails here rather than on somebody's machine.
    """
    fake = binaries / "cursor-agent"
    refuses = standins.refusing("cursor-agent")
    fake.write_text(
        f"#!{sys.executable}\n{refuses}{script.replace('LOG', repr(str(log)))}"
    )
    fake.chmod(0o755)


@pytest.fixture
def cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Calls:
    """A stand-in `cursor-agent` on PATH, printing what the real one prints."""
    log = tmp_path / "calls.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _install(binaries, _CURSOR_STUB, log)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)
    return _Calls(log)


#: What a signed-in account lists, as `cursor-agent models` prints it: a bare id beside the
#: variants that carry a rung, one that is listed with no variant at all, and the same model
#: again with the service it can be served on written behind it.
_ACCOUNT = (
    "gpt-5.2",
    "gpt-5.2-low",
    "gpt-5.2-high",
    "gpt-5.2-xhigh",
    "composer-2.5",
    "composer-2.5-fast",
    "auto",
)


def _kept(named: tuple[str, ...]) -> None:
    """Writes a catalogue down as if this account had just been asked what it runs.

    Args:
      named: The ids, as the account lists them.
    """
    at = models.where("cursor-agent")
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(
        json.dumps(
            {
                "asked": "2026-09-17T00:00:00Z",
                "models": [
                    {"name": one, "efforts": [], "swarms": False} for one in named
                ],
            }
        ),
        encoding="utf-8",
    )


def test_a_rung_moved_mid_run_is_refused_as_the_turn_is_built(cursor: _Calls) -> None:
    """The rung is the one setting a flow moves after the agent was made.

    So the turn checks it too: an agent turned up an hour into a loop, onto a rung this model
    has no id for, must not go out as an id nobody lists.
    """
    _kept(_ACCOUNT)
    session = CursorAgent(CursorAgentConfig(model="gpt-5.2", effort="low")).new()
    session("hello")

    session.effort = "medium"

    with pytest.raises(ValueError, match=r"lists no gpt-5.2-medium"):
        session("again")
    (argv,) = cursor.argv()
    assert argv[argv.index("--model") + 1] == "gpt-5.2-low"


def test_a_turn_is_one_run_of_its_command_line(cursor: _Calls) -> None:
    """The model with its bracket, the workspace, and the prompt after a `--`."""
    session = CursorAgent(CURSOR).new()

    assert session("hello") == "hello"

    (argv,) = cursor.argv()
    assert argv[argv.index("--model") + 1] == "composer-2.5-high"
    assert argv[:4] == ["--print", "--output-format", "stream-json", "--model"]
    assert argv[-2:] == ["--", "hello"]
    assert "--trust" in argv
    # And nothing else: every other flag of its own is where Cursor leaves it, so a turn
    # nobody has configured is the turn its own command line would have taken.
    assert "--stream-partial-output" not in argv
    assert "--approve-mcps" not in argv
    assert "--add-dir" not in argv
    assert session.id == "chat-0001"


def test_the_second_turn_resumes_the_chat_the_first_one_opened(cursor: _Calls) -> None:
    """Written onto the flag: its own argument is optional, so a separate one is the prompt."""
    session = CursorAgent(CURSOR).new()
    session("hello")

    session("again")

    _first, second = cursor.argv()
    assert "--resume=chat-0001" in second


#: What each rung comes to on Cursor's own command line.
_RUNGS = (
    ("read-only", ["--mode", "plan"]),
    ("workspace-write", ["--force", "--sandbox", "enabled"]),
    ("auto", ["--auto-review"]),
    ("bypass", ["--force", "--sandbox", "disabled"]),
)


def test_a_rung_is_the_mode_or_the_sandbox_cursor_has_for_it(cursor: _Calls) -> None:
    """Each of the four does something of its own rather than reading as the same turn."""
    from dataclasses import replace

    for rung, _expected in _RUNGS:
        CursorAgent(replace(CURSOR, permission=rung)).new()("hello")

    for argv, (_rung, expected) in zip(cursor.argv(), _RUNGS, strict=True):
        for one in expected:
            assert one in argv


def test_asking_for_the_faster_service_is_the_same_suffix(cursor: _Calls) -> None:
    """Which is why this backend can express a tier at all: the rung, then the service."""
    from dataclasses import replace

    CursorAgent(replace(CURSOR, service_tier="fast")).new()("hello")

    (argv,) = cursor.argv()
    assert argv[argv.index("--model") + 1] == "composer-2.5-high-fast"


def test_a_turn_says_what_it_did_as_it_does_it(cursor: _Calls) -> None:
    """A tool call once, as it starts: a row per status is a transcript of statuses."""
    session = CursorAgent(CURSOR).new()

    said = list(session.stream("hello"))

    assert [event.kind for event in said] == ["tool", "text", "result"]
    assert said[0].text == "read src/x.py"
    assert said[-1].text == "hello"


def test_an_agent_of_its_own_is_said_as_one_rather_than_as_a_tool(
    cursor: _Calls,
) -> None:
    """A fleet under a turn is agents, and whatever is watching draws them as agents."""
    session = CursorAgent(CURSOR).new()

    said = list(session.stream("fleet"))

    fleet = [event for event in said if event.kind.startswith("subagent")]
    assert [event.kind for event in fleet] == ["subagent", "subagent-ends"]
    # One agent rather than two lines: the id the call was made under is what pairs them.
    assert {event.whose for event in fleet} == {"call-2"}
    assert fleet[0].text == "task read the tests"


def test_the_moments_about_a_fleet_are_fired_where_one_runs(cursor: _Calls) -> None:
    """Which is what makes a hook a thing a flow can hang on the agents under its agent."""
    agent = CursorAgent(CURSOR)
    seen: list[Occasion] = []

    def note(occasion: Occasion) -> Verdict | None:
        seen.append(occasion)
        return None

    assert CursorAgent.moments >= SUBAGENTS
    agent.hooks.on(Moment.SUBAGENT_START, note)
    agent.hooks.on(Moment.SUBAGENT_STOP, note)

    agent.new()("fleet")

    assert [one.moment for one in seen] == [
        Moment.SUBAGENT_START,
        Moment.SUBAGENT_STOP,
    ]
    assert seen[0].tool == "task"
    assert seen[0].about == "read the tests"
    assert {one.under for one in seen} == {"call-2"}


def test_a_turn_that_failed_says_so_rather_than_answering_with_it(
    cursor: _Calls,
) -> None:
    """A loop fed that as an answer would be running on it as the work of the turn."""
    session = CursorAgent(CURSOR).new()

    with pytest.raises(subprocess.CalledProcessError) as raised:
        session("boom")

    assert "the model refused" in str(raised.value)


@pytest.fixture
def listing(asking: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stand-in `cursor-agent` with a catalogue on it, and a home to keep the answer in."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _install(binaries, _LISTED, tmp_path / "listed.jsonl")
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))


def test_what_it_runs_is_read_off_its_own_listing(listing: None) -> None:
    """The heading above the list and the tip below it are sentences, not models."""
    found = models.ask("cursor-agent")

    assert [one.name for one in found] == [
        "composer-2.5",
        "gpt-5",
        "gpt-5-high",
        "gpt-5-fast",
        "gpt-5-low-fast",
        "gpt-5-high-fast",
        "gpt-5.2",
        "gpt-5.2-low",
        "gpt-5.2-xhigh",
        "gpt-5.5-extra-high",
        "claude-opus-4-8",
        "sonnet-4.5-thinking",
        "grok-code-fast-1",
        "cheetah",
        "auto",
    ]


#: What each model in that listing is offered at, and why it is that rather than the other.
#: A rung is no parameter of a Cursor model: it is part of the id, so what a model is offered
#: at is the ids this account listed for it and nothing wider. Wider is what put
#: `gpt-5.2-medium` on a command line, which is a rung Cursor refuses the whole turn for.
_OFFERED = {
    # Listed alone, so it runs at whatever Cursor gives it and is offered at no rung at all.
    "composer-2.5": (),
    # Listed with one variant beside it, so that rung and no other: there is no `gpt-5-low`
    # here, whatever `gpt-5-low-fast` says about the same model on the faster service.
    "gpt-5": ("high",),
    "gpt-5-high": ("high",),
    # `fast` is the service a turn runs on and not a rung, so the first of these three carries
    # none and the other two carry the rung written in front of it.
    "gpt-5-fast": (),
    "gpt-5-low-fast": ("low",),
    "gpt-5-high-fast": ("high",),
    # The shape the live account actually lists: the bare id, and the rungs it has variants
    # for -- hardest first, and not the ones it has no variant for.
    "gpt-5.2": ("xhigh", "low"),
    "gpt-5.2-low": ("low",),
    "gpt-5.2-xhigh": ("xhigh",),
    # One model spells `xhigh` as two words, and reading it as the `high` inside it would name
    # a model one rung under what it runs.
    "gpt-5.5-extra-high": ("extra-high",),
    "claude-opus-4-8": (),
    # `thinking` is what the model is, `1` is which one it is, and `auto` is Cursor choosing:
    # a name is only pinned by a word that is one of Cursor's own rungs.
    "sonnet-4.5-thinking": (),
    "grok-code-fast-1": (),
    "cheetah": (),
    "auto": (),
}


def test_a_model_is_offered_at_the_rungs_this_account_lists_ids_for(
    listing: None,
) -> None:
    """A rung is a word of the name wherever it falls in it: `gpt-5-low-fast` runs at `low`."""
    found = models.ask("cursor-agent")

    assert {one.name: one.efforts for one in found} == _OFFERED


def test_the_workspace_it_is_trusted_with_can_be_handed_back(cursor: _Calls) -> None:
    """The one thing this driver overrules the bare command line about, and it is sayable.

    Trusted by default because a headless turn has nobody to answer the question; a flow
    somebody is watching says so and gets Cursor's own behaviour back -- and asks beforehand
    for the backend whose config has somewhere to say it as `settings:trust`, the name the
    catalogue derives from the field rather than a second word minted beside it.
    """
    from dataclasses import replace

    from hmz.flows.checking import catalogue

    told = {one.name: one.backends for one in catalogue()}
    assert told["settings:trust"] == frozenset({"cursor-agent"})

    CursorAgent(replace(CURSOR, trust=False)).new()("hello")

    (argv,) = cursor.argv()
    assert "--trust" not in argv


def test_the_other_three_say_themselves_on_the_line_when_they_are_asked_for(
    cursor: _Calls, tmp_path: Path
) -> None:
    """Each of them is Cursor's own flag under Cursor's own spelling, and each is off first."""
    from dataclasses import replace

    beside = tmp_path / "beside"
    beside.mkdir()
    CursorAgent(replace(CURSOR, approve_mcps=True, add_dirs=(str(beside),))).new()(
        "hello"
    )

    (argv,) = cursor.argv()
    assert "--approve-mcps" in argv
    assert argv[argv.index("--add-dir") + 1] == str(beside)


def test_words_streamed_as_they_are_written_are_not_said_again_whole(
    cursor: _Calls,
) -> None:
    """Cursor writes both: a line per piece, and the pieces gathered up at the end."""
    from dataclasses import replace

    session = CursorAgent(replace(CURSOR, partial_output=True)).new()

    said = list(session.stream("hello"))

    (argv,) = cursor.argv()
    assert "--stream-partial-output" in argv
    # The pieces that are words, and not the gathering of them behind: a turn said twice is
    # no transcript. The paragraph break between them is counted and shown to nobody, which
    # is what lets the gathering still be recognised as the pieces it is made of.
    assert [one.text for one in said if one.kind == "text"] == ["h", "ello"]
    assert said[-1].kind == "result"
    assert said[-1].text == "hello"


def test_what_the_turn_cost_is_read_off_the_line_it_ends_on(cursor: _Calls) -> None:
    """Cursor counts now, and its input is already net of what the cache answered."""
    agent = CursorAgent(CURSOR)

    (answer,) = (one for one in agent.new().stream("hello") if one.kind == "result")

    assert dict(answer.spent) == {
        "input": 100,
        "output": 20,
        "cache_read": 5,
        "cache_write": 3,
    }
    assert answer.tokens == {"composer-2.5": 128}
    assert dict(agent.spent()) == dict(answer.spent)
    assert CursorAgent.counts == frozenset(
        {"input", "output", "cache_read", "cache_write"}
    )


def test_a_local_runtime_key_left_about_does_not_outrank_the_provider(
    cursor: _Calls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI takes the key its own local runtime is served under from the environment too."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "humanize"))
    monkeypatch.setenv("CURSOR_LOCAL_AGENT_BASE_URL", "http://somebody-else/v1")
    monkeypatch.setenv("CURSOR_LOCAL_AGENT_API_KEY", "somebody-elses-key")
    providers.add("cursor-agent", "account", env={"CURSOR_API_KEY": "the-provider-key"})
    agent = CursorAgent(
        CursorAgentConfig(model="composer-2.5", effort="", provider="account")
    )
    environment = agent.new()._environ()

    assert environment is not None
    assert environment["CURSOR_API_KEY"] == "the-provider-key"
    assert "CURSOR_LOCAL_AGENT_API_KEY" not in environment
    # Which runtime, rather than whose account: taken away, the model spelling this turn
    # was built with would describe a turn that no longer happens.
    assert environment["CURSOR_LOCAL_AGENT_BASE_URL"] == "http://somebody-else/v1"


def test_a_provider_that_is_the_local_runtime_keeps_what_it_set(
    cursor: _Calls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hushed is every name the provider did not set: its own key stands."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "humanize"))
    providers.add(
        "cursor-agent",
        "local",
        env={
            "CURSOR_LOCAL_AGENT_BASE_URL": "http://127.0.0.1:1/v1",
            "CURSOR_LOCAL_AGENT_API_KEY": "the-provider-key",
        },
    )
    agent = CursorAgent(
        CursorAgentConfig(model="composer-2.5", effort="", provider="local")
    )
    environment = agent.new()._environ()

    assert environment is not None
    assert environment["CURSOR_LOCAL_AGENT_BASE_URL"] == "http://127.0.0.1:1/v1"
    assert environment["CURSOR_LOCAL_AGENT_API_KEY"] == "the-provider-key"
