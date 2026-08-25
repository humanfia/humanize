"""A place falling back to a place, once the one taking a turn has nowhere left to run.

An account's chain answers an account going down, inside the conversation that was running,
with the same agent at the same model throughout. This is what is left when that is no answer
at all: a model retired, a CLI that will not start, a whole account rate-limited rather than
one request. Another place then -- another CLI, another account, another model -- and the turn
taken in a session of its own, because no backend can be handed another backend's session id.

A place and not an agent: how hard the agent thinks, what it may reach for and which of a
flow's skills it carries are what that agent *is*, settled where it was made, and they come
across the step unchanged. Written down between the two places rather than on either, because
it is about neither on its own.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, fallbacks, providers
from hmz.coganchor.agents import (
    AcpAgent,
    AcpAgentConfig,
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    Tool,
)
from hmz.coganchor.agents.skills import Loaded
from tests.agents import standins
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A CLI of your own that is a real one. opencode speaks the Agent Client Protocol under
#: `opencode acp`, and a CLI written down by hand is driven over that protocol whatever else
#: humanize knows about the binary. It is added behind a command of its own, because an added
#: CLI answers to what it runs and `opencode` is a backend humanize already drives: what the
#: step is being proved against is the protocol, and a real server behind a name of its own
#: is somebody's own CLI in every way a step can tell.
_REAL = ("opencode", "acp")

#: What that command is called once it is on PATH, which is the name the step names.
_MINE = "acp-of-my-own"

#: A `claude` that answers whatever it was told, so that a turn which reached it says so.
_CLAUDE = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system",
                  "session_id": flags.get("--session-id") or flags["--resume"]}), flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    print(json.dumps({"type": "result", "result": "claude took it: " + said}), flush=True)
"""


@pytest.fixture(autouse=True)
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A home nothing has written to, and `shell` as a backend of your own."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    backends.remember("shell", ["shell"])


def _claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Puts a `claude` that answers on PATH, so a stand-in of one is one that runs."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{standins.refusing('claude')}{_CLAUDE}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")


def test_a_step_is_written_down_between_two_places() -> None:
    """Three things and no more: the CLI, the account it runs as, and the model it runs."""
    fallbacks.points("shell/m", "claude@work/claude-opus-5")

    assert fallbacks.falls() == [
        fallbacks.Falls("shell/m", "claude@work/claude-opus-5")
    ]
    assert fallbacks.chain("shell/m") == [
        "shell/m",
        "claude@work/claude-opus-5",
    ]


def test_the_chain_is_this_agent_and_then_wherever_each_one_goes() -> None:
    """A list rather than a list and a special case: the first is always this agent."""
    fallbacks.points("shell/m", "claude/a")
    fallbacks.points("claude/a", "codex/b")

    assert fallbacks.chain("shell/m") == [
        "shell/m",
        "claude/a",
        "codex/b",
    ]
    # And one nobody said anything about is a chain of one.
    assert fallbacks.chain("codex/b") == ["codex/b"]


def test_a_chain_that_comes_round_on_itself_ends_at_the_second_sight_of_a_place() -> (
    None
):
    """Or it would be a turn that could never run out of places to go."""
    fallbacks.points("shell/m", "claude/a")
    fallbacks.points("claude/a", "shell/m")

    assert fallbacks.chain("shell/m") == ["shell/m", "claude/a"]


def test_a_step_that_points_at_itself_or_at_nothing_is_refused_where_it_is_written() -> (
    None
):
    """Rather than found by the turn that needed it, an hour into a loop."""
    with pytest.raises(ValueError, match="cannot fall back to itself"):
        fallbacks.points("claude/a", "claude/a")
    with pytest.raises(ValueError, match="is not a place"):
        fallbacks.points("nothing-is-called-this/a", "claude/a")
    with pytest.raises(ValueError, match="is not a place"):
        fallbacks.points("claude/a", "nothing-is-called-this/a")


def test_writing_one_again_says_the_new_thing_and_not_both() -> None:
    """One place has one place to go: two would be a chain that forks."""
    fallbacks.points("shell/m", "claude/a")
    fallbacks.points("shell/m", "codex/b")

    assert fallbacks.chain("shell/m") == ["shell/m", "codex/b"]
    assert fallbacks.clear("shell/m")
    assert fallbacks.chain("shell/m") == ["shell/m"]
    assert not fallbacks.clear("shell/m")


def test_a_place_is_read_by_whichever_spelling_of_its_cli() -> None:
    """And a model with slashes of its own is a model: only the first of them separates."""
    assert fallbacks.reads("claude-code/m") == "claude/m"
    assert fallbacks.reads("claude@work/m") == "claude@work/m"
    assert fallbacks.reads("opencode/opencode/nemotron") == "opencode/opencode/nemotron"
    assert fallbacks.reads("nothing-is-called-this/m") == ""
    assert fallbacks.reads("claude") == ""
    assert fallbacks.reads("claude@/m") == ""


def test_an_effort_written_down_before_it_left_this_spelling_is_read_past() -> None:
    """A step somebody still means, and how hard an agent thinks is not part of a place."""
    assert fallbacks.reads("claude/claude-opus-5:high") == "claude/claude-opus-5"
    # And a colon that is part of a model's own name is left exactly where it is: only a
    # rung that backend actually lists is read as one.
    assert fallbacks.reads("claude/qwen3:8b") == "claude/qwen3:8b"
    # Which is the question here even for a CLI of your own, whose one listed rung is the
    # word for there being no ladder and which therefore refuses no rung at all: read as
    # "would this backend take the word", every such model would lose its own tail.
    assert fallbacks.reads("shell/qwen3:8b") == "shell/qwen3:8b"


def test_an_agent_says_which_place_it_runs_at() -> None:
    """The account it was configured with, which is what somebody wrote the step against."""
    assert ShellAgent(CONFIG).spec == "shell/m"
    assert (
        ShellAgent(AgentConfig(model="m", effort="high", provider="work")).spec
        == "shell@work/m"
    )


def test_an_agent_nobody_wrote_a_step_about_stands_in_nowhere() -> None:
    """Which is a turn failing the way a turn has always failed."""
    assert ShellAgent(CONFIG).stands_in() is None


def test_the_stand_in_is_at_the_place_the_step_names_and_is_made_once(
    tmp_path: Path,
) -> None:
    """Kept for the reason an account that has moved stays moved."""
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert stood_in.backend == "claude"
    assert stood_in.config.model == "claude-opus-5"
    assert agent.stands_in() is stood_in


def test_the_stand_in_is_configured_as_the_agent_that_could_not_run_was() -> None:
    """A step names a place; everything else about an agent is what that agent is."""
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(
        AgentConfig(model="m", effort="high", permission="read-only", goals=False)
    )

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert stood_in.config.effort == "high"  # a rung Claude has too
    assert stood_in.config.permission == "read-only"
    assert not stood_in.config.goals


def test_a_step_to_the_same_backend_carries_what_that_backend_was_told() -> None:
    """The CLI taking over is the CLI that was told it, so it is still told it."""
    fallbacks.points("claude/claude-opus-5", "claude/claude-sonnet-5")
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="claude-opus-5",
            effort="high",
            allowed_tools=("Bash(uv run:*)", "Read"),
        )
    )

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert isinstance(stood_in.config, ClaudeCodeAgentConfig)
    assert stood_in.config.model == "claude-sonnet-5"  # the one thing the step moved
    assert stood_in.config.allowed_tools == ("Bash(uv run:*)", "Read")


def test_a_step_to_the_same_backend_under_another_account_is_still_that_account() -> (
    None
):
    """What the step names is the step's, however much of the config comes across it.

    The same model under another account, so the window measured on it is still the window:
    what changed is whose key pays for the turn, which no model's numbers depend on.
    """
    fallbacks.points("codex@work/gpt-5.6-sol", "codex@key/gpt-5.6-sol")
    agent = CodexAgent(
        CodexAgentConfig(
            model="gpt-5.6-sol",
            effort="high",
            provider="work",
            overrides=(("model_context_window", "200000"),),
        )
    )

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert isinstance(stood_in.config, CodexAgentConfig)
    assert stood_in.config.provider == "key"
    assert stood_in.config.model == "gpt-5.6-sol"
    assert stood_in.config.overrides == (("model_context_window", "200000"),)


def test_a_step_that_changes_the_model_leaves_that_model_s_own_numbers_behind() -> None:
    """A window is a measurement of one model, and the step is onto another.

    The same-CLI carry is right about everything Codex was told in its own vocabulary -- it
    is the same Codex, and it still speaks it -- except the settings that were facts about
    the model that has just gone. `model_context_window` handed to the next model describes
    something else: nothing refuses it, nothing logs it, and the turns simply overrun a
    window the new model has not got.
    """
    fallbacks.points("codex/gpt-5.6-sol", "codex/gpt-5.6-sol-mini")
    agent = CodexAgent(
        CodexAgentConfig(
            model="gpt-5.6-sol",
            effort="high",
            overrides=(
                ("model_context_window", "400000"),
                ("model_auto_compact_token_limit", "300000"),
            ),
            features=(("unified_exec", True),),
            strict_config=True,
        )
    )

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert isinstance(stood_in.config, CodexAgentConfig)
    assert stood_in.config.model == "gpt-5.6-sol-mini"
    assert stood_in.config.overrides == ()
    # And nothing else goes with them: a feature and a strictness are the app server's own,
    # true of the CLI whichever model it is pointed at.
    assert stood_in.config.features == (("unified_exec", True),)
    assert stood_in.config.strict_config


def test_a_step_to_the_same_cli_of_your_own_still_knows_which_cli_it_is() -> None:
    """The sharpest of them: what a peer answers to is a setting, so losing it is a refusal.

    An ACP peer is named by a setting rather than by its class, and the name is the word its
    server answers to. Dropped across a step, the agent taking over is not less configured
    than the one it replaced -- it is pointed at nothing, and every turn after the step fails
    at the handshake rather than anywhere a reader would look.
    """
    fallbacks.points("shell/m", "shell/other")
    agent = AcpAgent(
        AcpAgentConfig(model="m", effort="high", cli="shell", command=("sh", "-c", ":"))
    )

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert stood_in.backend == "shell"
    assert isinstance(stood_in.config, AcpAgentConfig)
    assert stood_in.config.command == ("sh", "-c", ":")


def test_a_step_to_another_backend_leaves_the_first_one_s_vocabulary_behind() -> None:
    """A rule Claude reads as an allowed tool says nothing to the CLI taking over."""
    fallbacks.points("claude/claude-opus-5", "codex/gpt-5.6-sol")
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="claude-opus-5",
            effort="high",
            permission="read-only",
            allowed_tools=("Bash(uv run:*)",),
        )
    )

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert isinstance(stood_in.config, CodexAgentConfig)
    assert stood_in.config.overrides == ()  # nothing of Claude's was read as one
    assert not hasattr(stood_in.config, "allowed_tools")
    assert stood_in.config.permission == "read-only"  # and the common settings came


def test_a_rung_the_cli_taking_over_has_not_got_is_the_same_rung_of_its_own_ladder() -> (
    None
):
    """Every ladder here is hardest first, so a rung is how far down from the top it was."""
    fallbacks.points("claude/claude-opus-5", "grok/grok-5")
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="ultracode")
    )

    stood_in = agent.stands_in()

    # `ultracode` is the top of Claude's ladder and Grok Build has no such word, so the top
    # of its own is what the turn is taken at.
    assert stood_in is not None
    assert stood_in.config.effort == "xhigh"


def test_a_stand_in_that_cannot_be_told_what_this_agent_was_told_is_no_stand_in() -> (
    None
):
    """A setting a backend quietly ignored would be a setting that lies about the turn."""
    fallbacks.points("claude/claude-opus-5", "kimi/kimi-k3")
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", web_search=False)
    )

    # Kimi Code has no way of being told not to search the web, so it is not a place this
    # agent's turns can go: the turn fails the way it failed before anybody wrote a step.
    assert agent.stands_in() is None


def test_the_stand_in_carries_what_the_flow_gave_the_agent(tmp_path: Path) -> None:
    """The skills are the flow's, and the turn that moved is still the flow's turn."""
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)
    agent.loads([Loaded("reading", tmp_path / "reading", "this flow")])

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert [one.name for one in stood_in.loaded] == ["reading"]


def test_a_stand_in_holds_only_the_steps_after_its_own() -> None:
    """Or a chain read again from the top by each hop would walk the failed ones twice."""
    fallbacks.points("shell/m", "claude/a")
    fallbacks.points("claude/a", "codex/b")
    agent = ShellAgent(CONFIG)

    first = agent.stands_in()

    assert first is not None
    assert first._beyond == ("codex/b",)
    second = first.stands_in()
    assert second is not None
    assert second.spec == "codex/b"
    assert second._beyond == ()
    assert second.stands_in() is None


def test_the_stand_in_at_a_cli_somebody_added_knows_which_cli_it_is() -> None:
    """One class drives every added CLI, so its name is the agent rather than a setting.

    A step onto a CLI nobody wrote a driver for used to arrive without it, and the agent
    built was one that did not know what it was: it answered `acp`, ran at a place nobody
    had written a step about, and ended its first turn on having no command to start.
    """
    fallbacks.points("claude/claude-opus-5", "shell/m")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-5", effort="high"))

    stood_in = agent.stands_in()

    assert isinstance(stood_in, AcpAgent)
    assert stood_in.backend == "shell"
    assert stood_in.spec == "shell/m"
    assert stood_in.command == ("shell",)


def test_the_name_comes_across_and_nothing_else_of_the_backend_that_failed() -> None:
    """Identity is carved out of the narrowing; configuration goes on being narrowed away."""
    fallbacks.points("claude/claude-opus-5", "shell/m")
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="claude-opus-5", effort="high", allowed_tools=("Bash(ls:*)",)
        )
    )

    stood_in = agent.stands_in()

    assert isinstance(stood_in, AcpAgent)
    held = stood_in.config
    assert isinstance(held, AcpAgentConfig)
    # A rule Claude reads as an allowed tool says nothing to a CLI of somebody's own, and
    # there is nowhere on this config for it to have landed.
    assert not hasattr(held, "allowed_tools")
    # And what this class does have of its own beside the name is left at what it says by
    # default: the name is the whole of what the narrowing lets past.
    assert held.command == ()


def test_a_step_between_two_added_clis_arrives_as_the_one_it_stepped_to() -> None:
    """The name is read off the place the step names, never off the agent leaving it."""
    backends.remember("othersh", ["othersh", "-e"])
    fallbacks.points("shell/m", "othersh/m")
    agent = AcpAgent(
        AcpAgentConfig(
            cli="shell",
            model="m",
            effort="as configured",
            command=("sh", "-c", "the one that could not run"),
        )
    )

    stood_in = agent.stands_in()

    assert isinstance(stood_in, AcpAgent)
    assert stood_in.backend == "othersh"
    # And started by its own command rather than by the failed CLI's, which would start the
    # very process the step exists to get away from. It is looked up from the name instead.
    held = stood_in.config
    assert isinstance(held, AcpAgentConfig)
    assert held.command == ()
    assert stood_in.command == ("othersh", "-e")


def test_a_step_off_an_added_cli_onto_one_humanize_drives_carries_no_name() -> None:
    """There the class is the answer, and a name beside it would be a field it has not got."""
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = AcpAgent(AcpAgentConfig(cli="shell", model="m", effort="as configured"))

    stood_in = agent.stands_in()

    assert isinstance(stood_in, ClaudeCodeAgent)
    assert stood_in.backend == "claude"
    assert not hasattr(stood_in.config, "cli")


def test_a_step_naming_a_cli_that_is_not_here_is_a_turn_that_fails_as_it_always_did() -> (
    None
):
    """The answer somebody needs is what went wrong, not what the step said."""
    fallbacks.points("shell/m", "claude/a")
    # Written down while it could be read, and the backend gone by the time it is needed.
    agent = ShellAgent(CONFIG)
    agent._beyond = ("nothing-is-called-this/a",)

    assert agent.stands_in() is None


@pytest.mark.timeout(60)
def test_a_turn_with_nowhere_left_to_run_is_taken_at_the_place_it_falls_back_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is the whole of it: the flow asked one agent and another one answered."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)

    # `exit 3` is a turn that failed, and this agent has no account to fall back to.
    assert agent.new()("exit 3") == "claude took it: exit 3"


@pytest.mark.timeout(60)
def test_a_model_that_is_gone_walks_no_account_before_it_takes_the_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every account of a CLI is offered the same catalogue, so the step is the whole answer."""
    _claude(tmp_path, monkeypatch)
    providers.add("shell", "main", env={"WHOSE": "main"})
    providers.add("shell", "spare", env={"WHOSE": "spare"})
    providers.points("shell", "main", "spare")
    fallbacks.points("shell@main/m", "claude/claude-opus-5")
    agent = ShellAgent(AgentConfig(model="m", effort="high", provider="main"))
    tally = tmp_path / "took.txt"
    said: list[str] = []
    agent.watch(
        lambda _agent, _session, event: (
            said.append(event.text) if event.kind == "notice" else None
        )
    )

    script = f'echo "$WHOSE" >> {tally}; echo "404 model not found: m" >&2; exit 1'
    assert agent.new()(script) == f"claude took it: {script}"

    # One go, under the account it started on. `spare` would have answered any other failure.
    assert tally.read_text().split() == ["main"]
    # And the step says what sent the turn there rather than only that it went.
    assert any(
        "shell has no such model" in one
        and "carrying on as claude/claude-opus-5" in one
        for one in said
    )


@pytest.mark.timeout(60)
def test_a_turn_that_failed_for_nothing_anybody_named_steps_as_it_always_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure nothing recognises is narrated the way one has always been narrated."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)
    said: list[str] = []
    agent.watch(
        lambda _agent, _session, event: (
            said.append(event.text) if event.kind == "notice" else None
        )
    )

    agent.new()("exit 3")

    assert said == [
        "shell has nowhere left to run; carrying on as claude/claude-opus-5"
    ]


@pytest.mark.timeout(60)
def test_the_turn_that_moved_is_still_the_one_the_flow_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One `begins` and one `ends` on the agent the flow is driving, whoever took the turn."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)
    said: list[str] = []
    agent.watch(lambda _agent, _session, event: said.append(event.kind))

    agent.new()("exit 3")

    assert said.count("begins") == 1
    assert said.count("ends") == 1
    assert said.count("result") == 1


@pytest.mark.timeout(60)
def test_a_turn_that_lands_never_asks_where_it_would_have_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chain of four agents all started when the run was would be three CLIs for nothing."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)

    assert agent.new()("echo fine") == "fine"
    assert agent._stands_in is None


def test_the_agent_that_took_the_turn_is_asked_for_the_shape_its_own_way() -> None:
    """A backend that can be held to a shape is told separately, and one that cannot is asked.

    So the prompt is shaped for whoever is about to be asked rather than once for whoever was
    asked first: a stand-in that can be held to it would otherwise be handed a schema in the
    prompt as well as on the flag.
    """
    assert ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new().shapes
    assert not ShellAgent(CONFIG).new().shapes


@pytest.mark.timeout(60)
def test_an_agent_stopped_stops_whatever_is_standing_in_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run ended by hand ends: a stand-in that went on thinking would be one that did not."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)
    agent.new()("exit 3")  # which is what makes the stand-in

    agent.stop()

    stood_in = agent.stands_in()
    assert stood_in is not None
    assert stood_in.stopped


@pytest.mark.timeout(60)
def test_the_conversation_is_lost_once_rather_than_every_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stateful loop that moved is one conversation on the other side, not one a round."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)
    session = agent.new()

    session("exit 3")
    session("exit 3")

    stood_in = agent.stands_in()
    assert stood_in is not None
    assert len(stood_in.opened) == 1  # one conversation, both of the turns that moved


@pytest.mark.timeout(60)
def test_the_conversation_it_moved_to_ends_when_this_one_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It is this conversation carried on somewhere else, so it goes when this one goes.

    Read off what it was carrying, since that is what a session leaves in the workspace: the
    flow's skills go with the turn, put where the backend that took it reads them, and they
    come down when the conversation they were for is over.
    """
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    brought = tmp_path / "brought" / "reading"
    brought.mkdir(parents=True)
    (brought / "SKILL.md").write_text("---\nname: reading\n---\n")
    agent = ShellAgent(CONFIG)
    agent.loads([Loaded("reading", brought, "this flow")])
    session = agent.new()
    session("exit 3")

    # Where Claude reads a project's own, which is not where the agent it moved from would.
    assert (tmp_path / ".claude/skills/reading").is_dir()

    session.close()

    assert not (tmp_path / ".claude").exists()


#: A `claude` that will not run at all at one model, and writes down how it was started at any
#: other: which is a place with nowhere left to go, and the place the step names.
_CLAUDE_GONE = """
import json, pathlib, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
if flags.get("--model") == "gone":
    sys.exit(3)
with pathlib.Path(LOG).open("a") as wrote:
    wrote.write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({"type": "system",
                  "session_id": flags.get("--session-id") or flags["--resume"]}), flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    print(json.dumps({"type": "result", "result": "claude took it: " + said}), flush=True)
"""


def _gone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts that `claude` on PATH, and answers with the log of every start it wrote."""
    log = tmp_path / "starts.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "claude"
    refuses = standins.refusing("claude")
    fake.write_text(
        f"#!{sys.executable}\n{refuses}{_CLAUDE_GONE.replace('LOG', repr(str(log)))}"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return log


def _delegating() -> Tool:
    """One callback of a flow's own, of the kind a loop offers between two rounds."""
    return Tool(name="delegate", about="hand a task on", call=lambda: "did it")


@pytest.mark.timeout(60)
def test_the_stand_in_is_offered_the_callbacks_the_conversation_was_offering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flow's own callbacks go with the turn, the way the flow's skills do.

    They are the conversation's rather than the agent's -- said between two turns, long after
    the step was written down -- so a turn that moved without them would be the flow losing
    what it offered by being moved, and nothing about it would look wrong.
    """
    log = _gone(tmp_path, monkeypatch)
    fallbacks.points("claude/gone", "claude/claude-opus-5")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="gone", effort="high"))
    session = agent.new()
    session.offers([_delegating()])

    assert session("hello") == "claude took it: hello"

    # One start written down: the model that is gone never got as far as writing one.
    (argv,) = [json.loads(line) for line in log.read_text().splitlines()]
    held = json.loads(argv[argv.index("--mcp-config") + 1])
    assert list(held["mcpServers"]) == ["humanize"]


@pytest.mark.timeout(60)
def test_a_stand_in_that_cannot_be_given_the_callbacks_is_no_stand_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A callback quietly never offered is a flow that quietly does not do what it says.

    Which is the rule about a setting the CLI taking over cannot be told, applied to the one
    thing a conversation says after the step was read: the turn fails the way it failed before
    anybody wrote a step down.
    """
    _gone(tmp_path, monkeypatch)
    fallbacks.points("claude/gone", "grok/grok-5")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="gone", effort="high"))
    said: list[str] = []
    agent.watch(lambda _agent, _session, event: said.append(event.text))
    session = agent.new()
    session.offers([_delegating()])

    with pytest.raises(subprocess.CalledProcessError):
        session("hello")

    # The step is there and the agent for it was made; what stopped the turn going is that
    # Grok Build has no way of being given a tool of a flow's own.
    assert agent.stands_in() is not None
    assert not [one for one in said if "grok" in one]


@pytest.mark.timeout(60)
def test_the_stand_in_is_offered_what_the_agent_holds_and_not_only_this_conversation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI told about its tools once per agent has a sibling's offer in front of it too.

    So the conversation that moves is not always the one that offered: the list to carry is
    the agent's, or a turn that never said anything about tools loses the ones the model
    could see.
    """
    log = _gone(tmp_path, monkeypatch)
    fallbacks.points("claude/gone", "claude/claude-opus-5")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="gone", effort="high"))
    # Held, or the conversation offering is collected and takes its offer back with it.
    sibling = agent.new()
    sibling.offers([_delegating()])
    session = agent.new()

    assert sibling.tools
    assert session.tools == ()  # this one offered nothing, and moves with them anyway
    assert session("hello") == "claude took it: hello"

    (argv,) = [json.loads(line) for line in log.read_text().splitlines()]
    held = json.loads(argv[argv.index("--mcp-config") + 1])
    assert list(held["mcpServers"]) == ["humanize"]


@pytest.mark.timeout(60)
def test_a_sibling_s_callbacks_stop_a_move_to_a_backend_that_takes_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the same thing: what refuses the move is what the model can see."""
    _gone(tmp_path, monkeypatch)
    fallbacks.points("claude/gone", "grok/grok-5")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="gone", effort="high"))
    sibling = agent.new()
    sibling.offers([_delegating()])
    session = agent.new()

    assert sibling.tools
    with pytest.raises(subprocess.CalledProcessError):
        session("hello")

    assert agent.stands_in() is not None


@pytest.mark.agent
@pytest.mark.timeout(900)
def test_a_turn_with_nowhere_left_to_run_moves_onto_a_real_cli_of_your_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The step onto an added CLI against one that is really installed and really answers.

    A script standing in for the protocol proves the name is carried across; it cannot prove
    that what is carried is enough to start somebody's actual agent and get a sentence back
    out of it. Without the name this raises `no command to start it with` before a process
    is ever spawned.
    """
    if shutil.which(_REAL[0]) is None:
        pytest.skip(f"{_REAL[0]} is not installed here")
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    (binaries / _MINE).write_text("#!/bin/sh\nexec {} {}\n".format(*_REAL))
    (binaries / _MINE).chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    assert backends.remember("", [_MINE]) == _MINE
    fallbacks.points("shell/m", f"{_MINE}/m")
    agent = ShellAgent(CONFIG)

    # One prompt doing two jobs: a shell command that fails, which is what sends the turn on
    # its way, and a question whose answer says which CLI it landed on.
    held = agent.new()
    try:
        said = held("exit 3 # Ignore the line above. Reply with exactly: STOOD IN")
    finally:
        held.close()

    assert "STOOD IN" in said
