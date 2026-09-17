"""Moving how hard an agent thinks while it is already running.

A config is frozen, because a session resumes under the settings it opened with. The effort is
the one of them a flow may move as it goes -- a loop watching what it is costing turns the
whole agent down, and one nursing a conversation through a hard patch turns that session up --
so it is asked of the agent and the session rather than read off the config, and each backend
carries it to the CLI the way that CLI takes it.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import (
    AcpAgent,
    AcpAgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    GrokBuildAgent,
    GrokBuildAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
)
from tests.agents import standins

if TYPE_CHECKING:
    from pathlib import Path

CLAUDE = ClaudeCodeAgentConfig(model="m", effort="high")
PI = PiAgentConfig(model="m", effort="high")
OPENCODE = OpencodeAgentConfig(model="m", effort="high")

#: A `claude` that writes down each launch and answers each thing it is told.
_CLAUDE = """
import json, pathlib, sys

log = pathlib.Path(LOG)


def note(entry):
    with log.open("a") as stream:
        json.dump(entry, stream)
        stream.write("\\n")


note({"argv": sys.argv[1:], "said": None})
flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system",
                  "session_id": flags.get("--session-id") or flags["--resume"]}), flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    note({"argv": None, "said": said})
    print(json.dumps({"type": "result", "result": said}), flush=True)
"""

#: A `pi --mode rpc` that writes down its launch and every command written to it.
_PI = """
import json, pathlib, sys

log = pathlib.Path(LOG)


def note(entry):
    with log.open("a") as stream:
        json.dump(entry, stream)
        stream.write("\\n")


note({"argv": sys.argv[1:], "said": None})
for line in sys.stdin:
    told = json.loads(line)
    note({"argv": None, "said": json.dumps(told)})
    if told["type"] != "prompt":
        print(json.dumps({"type": "response", "command": told["type"],
                          "success": True}), flush=True)
        continue
    print(json.dumps({"type": "message_end", "message": {"role": "assistant",
          "content": [{"type": "text", "text": told["message"]}],
          "usage": {"input": 1, "output": 1}}}), flush=True)
    print(json.dumps({"type": "agent_settled"}), flush=True)
"""

#: An `opencode run` that writes down the run it was and answers with what it was fed.
_OPENCODE = """
import json, pathlib, sys

said = sys.stdin.read()
with pathlib.Path(LOG).open("a") as stream:
    json.dump({"argv": sys.argv[1:], "said": said}, stream)
    stream.write("\\n")

print(json.dumps({"type": "text", "sessionID": "ses_one",
                  "part": {"id": "prt_1", "type": "text", "text": said}}), flush=True)
print(json.dumps({"type": "step_finish", "sessionID": "ses_one",
                  "part": {"id": "prt_2", "type": "step-finish",
                           "tokens": {"input": 1, "output": 1, "reasoning": 0,
                                      "cache": {"read": 0, "write": 0}}}}), flush=True)
"""


@dataclass(frozen=True)
class _Noted:
    """What the stand-in was launched as, and what was written to it."""

    log: Path

    def rows(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def launches(self) -> list[list[str]]:
        return [row["argv"] for row in self.rows() if row["argv"] is not None]

    def said(self) -> list[str]:
        return [row["said"] for row in self.rows() if row["said"] is not None]


def _install(
    named: str, script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _Noted:
    """Puts one stand-in CLI on PATH and says where it writes down what it was asked.

    It opens with what that CLI refuses, so a driver that drifted onto a flag the real one
    has not got fails here rather than on somebody's machine.
    """
    log = tmp_path / f"{named}.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / named
    refuses = standins.refusing(named)
    fake.write_text(
        f"#!{sys.executable}\n{refuses}{script.replace('LOG', repr(str(log)))}"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return _Noted(log)


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Noted:
    return _install("claude", _CLAUDE, tmp_path, monkeypatch)


@pytest.fixture
def pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Noted:
    return _install("pi", _PI, tmp_path, monkeypatch)


@pytest.fixture
def opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Noted:
    return _install("opencode", _OPENCODE, tmp_path, monkeypatch)


def test_an_agent_runs_at_what_it_was_configured_with_until_it_is_told_otherwise() -> (
    None
):
    agent = ClaudeCodeAgent(CLAUDE)
    session = agent.new()

    assert agent.effort == "high"
    assert session.effort == "high"
    assert agent.config.effort == "high"  # which is not moved by moving the other


def test_moving_an_agents_effort_moves_every_session_of_it() -> None:
    agent = ClaudeCodeAgent(CLAUDE)
    first, second = agent.new(), agent.new()

    agent.effort = "low"

    assert [first.effort, second.effort] == ["low", "low"]
    assert agent.config.effort == "high"  # the config is what it was configured with


def test_a_session_told_something_of_its_own_keeps_it() -> None:
    """A flow nursing one conversation through a hard patch turns that session up."""
    agent = ClaudeCodeAgent(CLAUDE)
    nursed, ordinary = agent.new(), agent.new()

    nursed.effort = "max"
    agent.effort = "low"

    assert nursed.effort == "max"
    assert ordinary.effort == "low"

    nursed.effort = ""  # and giving it back leaves it on the agent's again
    assert nursed.effort == "low"


def test_claude_resumes_the_conversation_in_a_process_that_thinks_at_the_new_one(
    claude: _Noted,
) -> None:
    """`--effort` is an argument of the process, so moving it restarts one.

    The conversation is not restarted with it: the new process resumes the session, which is
    what an anchored session does between every pair of turns anyway.
    """
    agent = ClaudeCodeAgent(CLAUDE)
    session = agent.new()
    assert session("one") == "one"
    assert session("two") == "two"  # nothing moved, so nothing restarted

    agent.effort = "low"
    assert session("three") == "three"
    assert session("four") == "four"  # and it stays there

    opened, again = claude.launches()
    assert opened[opened.index("--effort") + 1] == "high"
    assert again[again.index("--effort") + 1] == "low"
    assert again[again.index("--resume") + 1] == session.id
    assert claude.said() == ["one", "two", "three", "four"]


def test_pi_is_told_the_new_effort_rather_than_started_again(pi: _Noted) -> None:
    """It takes the thinking level on the session it is already holding, so it is told."""
    agent = PiAgent(PI)
    session = agent.new()
    assert session("one") == "one"

    session.effort = "low"
    assert session("two") == "two"

    (launch,) = pi.launches()  # one process throughout
    assert launch[launch.index("--thinking") + 1] == "high"
    told = [json.loads(said) for said in pi.said()]
    assert [one["type"] for one in told] == ["prompt", "set_thinking_level", "prompt"]
    assert told[1]["level"] == "low"


def test_pi_is_told_once_rather_than_before_every_turn(pi: _Noted) -> None:
    agent = PiAgent(PI)
    session = agent.new()
    session("one")
    session.effort = "low"
    session("two")
    session("three")

    told = [json.loads(said)["type"] for said in pi.said()]
    assert told == ["prompt", "set_thinking_level", "prompt", "prompt"]


def test_an_effort_moved_before_the_first_turn_is_what_the_process_starts_at(
    pi: _Noted,
) -> None:
    """There is nothing up to be told, so it goes on the command line like any other."""
    agent = PiAgent(PI)
    agent.effort = "low"
    agent("one")

    (launch,) = pi.launches()
    assert launch[launch.index("--thinking") + 1] == "low"
    assert [json.loads(said)["type"] for said in pi.said()] == ["prompt"]


def test_opencode_runs_the_next_turn_at_the_new_variant(opencode: _Noted) -> None:
    """A run per turn, so the next run is where a new effort shows up."""
    agent = OpencodeAgent(OPENCODE)
    session = agent.new()
    session("one")
    agent.effort = "minimal"
    session("two")

    first, second = opencode.launches()
    assert first[first.index("--variant") + 1] == "high"
    assert second[second.index("--variant") + 1] == "minimal"


def test_what_a_flow_moves_is_read_back_off_the_agent_and_the_session() -> None:
    """Which is the whole of the interface: a property, read and written."""
    agent = OpencodeAgent(OPENCODE)
    session = agent.new()

    agent.effort = "low"
    assert (agent.effort, session.effort) == ("low", "low")

    agent.effort = ""
    assert (agent.effort, session.effort) == ("high", "high")


def test_a_rung_off_the_backends_ladder_is_refused_where_the_agent_is_made() -> None:
    """The ladder is the backend's own, so the word is read against that backend's.

    `grok agent` is the reason this is not left to the first turn. It opens a session at a
    rung it has never heard of and takes ordinary turns at it perfectly well, refusing the
    word only on the command line the shaped, forked and withheld turns go out on -- so an
    agent configured at one runs for an hour and then fails somewhere that says nothing at
    all about how it was configured.
    """
    with pytest.raises(ValueError, match="grok cannot be asked to think at 'bogus'"):
        GrokBuildAgent(GrokBuildAgentConfig(model="grok-5", effort="bogus"))

    # A rung of somebody else's ladder is the same answer: `ultra` is Codex's word.
    with pytest.raises(ValueError, match="grok cannot be asked to think at 'ultra'"):
        GrokBuildAgent(GrokBuildAgentConfig(model="grok-5", effort="ultra"))


def test_the_rung_a_backend_takes_without_listing_is_taken_here_too() -> None:
    """`ultracode` is real and undocumented, which is why it is written down as `beyond`."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="ultracode"))

    assert agent.config.effort == "ultracode"


def test_a_rung_off_the_ladder_is_refused_where_a_flow_moves_one_mid_run() -> None:
    """The rung is the one setting that arrives after construction as well as at it.

    A loop that turns its agent down an hour in, a flow nursing one conversation up through
    a hard patch: both say a word the CLI has to have, and a check that only ran where the
    agent was made would be a check that watched the quieter of the two ways in.
    """
    agent = ClaudeCodeAgent(CLAUDE)
    session = agent.new()

    with pytest.raises(ValueError, match="claude cannot be asked to think at 'none'"):
        agent.effort = "none"
    with pytest.raises(ValueError, match="claude cannot be asked to think at 'none'"):
        session.effort = "none"

    assert (agent.effort, session.effort) == ("high", "high")  # left as they were


def test_a_cli_known_only_by_the_protocol_refuses_no_rung(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It lists one, and the one is the word for there being no ladder to read against.

    The Agent Client Protocol says nothing about how hard an agent may be asked to think --
    it runs as whoever installed it configured it -- so there is nothing here to refuse a
    rung with, and refusing every word but `as configured` would leave a CLI somebody added
    unusable at any effort they would actually type.
    """
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    backends.remember("mine", ["mine", "acp"])

    agent = AcpAgent(AcpAgentConfig(model="m", effort="high", cli="mine"))
    agent.effort = "whatever that CLI calls it"

    assert agent.effort == "whatever that CLI calls it"


def test_a_fleet_is_a_width_rather_than_a_rung_off_the_ladder() -> None:
    """`swarmmax` is `max` run wide, which is one word for two answers about one turn."""
    agent = KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="k3", effort="swarmmax"))

    assert agent.config.effort == "swarmmax"
    with pytest.raises(
        ValueError, match="kimi cannot be asked to think at 'swarmultra'"
    ):
        agent.effort = "swarmultra"


def test_auto_is_the_word_for_no_rung_and_every_backend_takes_it() -> None:
    """A model does not always have rungs, and before `auto` there was no way to say so.

    Cursor runs `composer-2.5`, `gemini-3.1-pro` and `auto` at one setting and no other;
    Antigravity has models with no variants; a gateway serves plenty that reason one way.
    An agent is written `CLI/MODEL:EFFORT` wherever a person or a settings file names one,
    so a model with no rung had nothing to write after the colon and could not be named at
    all. `auto` is that nothing, spelled.

    It is not a rung on anybody's ladder, so it is not read against one: it is humanize
    saying nothing to the CLI about how hard to think, which any CLI can be told by not
    being told.
    """
    for profile in backends.PROFILES:
        assert profile.takes(backends.AUTO), profile.name
        assert profile.takes(""), profile.name


def test_auto_and_the_absence_of_a_rung_are_one_value() -> None:
    """Normalised on the way in and written back on the way out, so nothing carries two.

    A driver asks one question -- is there a rung? -- and `effort == ""` is the whole of the
    answer. Were `auto` to reach that far it would be a second thing every one of twelve
    drivers had to know, which is how a value ends up meaning one thing in eleven of them.
    """
    assert ClaudeCodeAgentConfig(model="m", effort=backends.AUTO).effort == ""
    assert backends.written("") == backends.AUTO
    assert backends.written("high") == "high"

    # And a line names it either way: `auto` is what a person writes, and the bare colon is
    # what a spec kept in a settings file comes back as -- the layers that keep a run written
    # down may import nothing, so they cannot be asked to know the word.
    for spec in ("claude/m:auto", "claude/m:"):
        _, _, model, effort, _ = backends.read(spec)
        assert (model, effort) == ("m", "")


def test_an_agent_at_no_rung_says_nothing_about_how_hard_to_think(
    claude: _Noted, opencode: _Noted
) -> None:
    """Which is the point of it: the model is left at whatever its account gives it.

    A flag carrying "" is not the same as no flag. Claude Code warns about an effort it does
    not know and then runs at its default anyway, and opencode reads an empty `--variant` as
    a variant its provider does not serve -- so an agent at no rung that still said something
    would be a turn with a line of noise in front of it at best, and a refused one at worst.
    """
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="auto")).new()
    assert session("one") == "one"
    (launched,) = claude.launches()
    assert "--effort" not in launched

    ran = OpencodeAgent(OpencodeAgentConfig(model="p/m", effort="auto")).new()
    assert ran("two") == "two"
    (called,) = opencode.launches()
    assert "--variant" not in called


def test_moving_an_agent_to_auto_takes_the_rung_back_off_it(claude: _Noted) -> None:
    """A flow that turns an agent down to nothing is asking for the model's own default."""
    agent = ClaudeCodeAgent(CLAUDE)
    session = agent.new()
    assert session("one") == "one"

    agent.effort = backends.AUTO
    assert session("two") == "two"

    opened, again = claude.launches()
    assert opened[opened.index("--effort") + 1] == "high"
    assert "--effort" not in again
