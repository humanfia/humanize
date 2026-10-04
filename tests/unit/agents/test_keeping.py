"""Where an agent's sessions are kept, and what a turn of it is spawned as to keep them there.

Every session humanize runs is kept in a directory of humanize's own rather than in the CLI's
home -- the run's epic for an agent a run drives, humanize's home for one driven by hand -- and
what does the keeping is the supervisor a turn under an account already runs in, answering the
CLI's session paths and nothing else of its home. What is checked here is the command line that
comes to and the directory an agent says its sessions are in, read off objects in this process:
nothing is spawned, so the supervisor is taken to be one this machine can run, whatever machine
this is. The supervisor itself is `tests/system/providers/test_redirect.py`, and a real CLI kept
in a real epic is `tests/system/runtime/test_sessions.py`.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import pytest

from hmz import home
from hmz.coganchor import providers
from hmz.coganchor.agents import KEEPING, ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.coganchor.agents.claude import _project

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor.agents import AgentBase

CONFIG = ClaudeCodeAgentConfig(model="m", effort="high")


class Run:
    """A run, as far as an agent asks one anything: where it keeps what its agents open."""

    def __init__(self, at: Path) -> None:
        self.keeps = at
        self.said: list[str] = []

    def opened(self, agent: AgentBase, session: str, parent: str = "") -> None:
        self.said.append(session)


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A Claude home of the test's own, on a machine taken to supervise, keeping sessions."""
    monkeypatch.delenv(KEEPING, raising=False)
    monkeypatch.setattr("hmz.coganchor.providers.redirect.supervises", lambda: True)
    at = tmp_path / "claude-home"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(at))
    return at


def _kept(argv: list[str]) -> list[str]:
    """What a rendered command keeps, as the `--keep` words it names."""
    return [one for one in argv if one.startswith("--keep=")]


def test_an_agent_nobody_gave_an_account_is_supervised_for_its_sessions(
    claude: Path,
) -> None:
    """The account this machine is signed into answers no credential, and still keeps."""
    agent = ClaudeCodeAgent(CONFIG)

    argv = agent.spawned(["claude", "--print"])

    assert argv[:5] == [sys.executable, "-Pm", "hmz", "internal", "cred"]
    # And then the CLI's own line, as it would have been run: wherever PATH names it.
    assert argv[argv.index("--") + 2 :] == ["--print"]
    kept = home() / "sessions" / "claude"
    assert f"--keep={claude / 'projects'}={kept / 'projects'}" in _kept(argv)
    assert not [one for one in argv if one.startswith("--map=")]
    assert agent.kept() == kept


def test_an_agent_a_run_drives_keeps_its_sessions_in_that_run(
    claude: Path, tmp_path: Path
) -> None:
    agent = ClaudeCodeAgent(CONFIG)
    agent.epic = Run(tmp_path / "epic" / "sessions")

    argv = agent.spawned(["claude"])

    kept = tmp_path / "epic" / "sessions" / "claude"
    assert f"--keep={claude / 'sessions'}={kept / 'sessions'}" in _kept(argv)
    assert agent.kept() == kept


def test_a_turn_under_an_account_swaps_its_credentials_and_keeps_its_sessions(
    claude: Path,
) -> None:
    """One supervisor, answering both: a process has one tracer."""
    providers.add("claude", "work", "key", {"ANTHROPIC_API_KEY": "sk-nothing"})
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", provider="work")
    )

    argv = agent.spawned(["claude"])

    assert [one for one in argv if one.startswith("--map=")]
    assert _kept(argv)


def test_a_process_told_to_keep_none_runs_the_cli_as_it_always_ran(
    claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(KEEPING, "off")
    agent = ClaudeCodeAgent(CONFIG)

    assert agent.spawned(["claude", "--print"])[-1] == "--print"
    assert agent.spawned(["claude", "--print"])[0] != sys.executable
    assert agent.kept() == claude


def test_a_machine_that_cannot_supervise_keeps_sessions_where_the_cli_does(
    claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refusing every turn on a Mac would be refusing humanize; the run says where they are."""
    monkeypatch.setattr("hmz.coganchor.providers.redirect.supervises", lambda: False)
    agent = ClaudeCodeAgent(CONFIG)

    assert not _kept(agent.spawned(["claude"]))
    assert agent.kept() == claude


def test_a_fork_into_another_agent_is_kept_where_the_conversation_is(
    claude: Path, tmp_path: Path
) -> None:
    """A read-only side question forks a run's session into an agent of no run at all."""
    agent, side = ClaudeCodeAgent(CONFIG), ClaudeCodeAgent(CONFIG)
    agent.epic = Run(tmp_path / "epic" / "sessions")
    session = agent.new()
    session._adopt("the-conversation")

    session.fork(into=side)

    assert side.keeps == tmp_path / "epic" / "sessions"
    assert side.epic is None  # kept there, and written down nowhere


def test_where_an_agent_keeps_its_sessions_is_settled_by_its_first_process(
    claude: Path, tmp_path: Path
) -> None:
    """A conversation is carried on from where it was kept, so the place does not move."""
    agent = ClaudeCodeAgent(CONFIG)
    agent.epic = Run(tmp_path / "first" / "sessions")
    agent.spawned(["claude"])

    agent.epic = Run(tmp_path / "second" / "sessions")

    assert agent.keeps == tmp_path / "first" / "sessions"
    with pytest.raises(ValueError, match="cannot be carried on"):
        agent.keeps = tmp_path / "elsewhere"


def test_a_fork_into_an_agent_keeping_its_sessions_elsewhere_is_refused(
    claude: Path, tmp_path: Path
) -> None:
    """It could not carry the conversation on from where that is kept."""
    agent, other = ClaudeCodeAgent(CONFIG), ClaudeCodeAgent(CONFIG)
    agent.epic = Run(tmp_path / "epic" / "sessions")
    other.spawned(["claude"])  # keeping its own in humanize's home from here on
    session = agent.new()
    session._adopt("the-conversation")

    with pytest.raises(ValueError, match="cannot be carried on"):
        session.fork(into=other)


def _conversation(at: Path, ident: str) -> Path:
    """A Claude conversation as an earlier run kept it, beside one of somebody else's."""
    project = at / "projects" / "-the-workspace-it-was-had-in"
    (project / ident / "subagents").mkdir(parents=True)
    (project / f"{ident}.jsonl").write_text('{"said": "the codeword is papaya"}\n')
    (project / ident / "subagents" / "agent-1.jsonl").write_text("{}\n")
    (project / "somebody-else.jsonl").write_text("{}\n")
    return project / f"{ident}.jsonl"


def test_a_conversation_kept_by_another_run_is_brought_in_as_a_fork_of_it_opens(
    claude: Path, tmp_path: Path
) -> None:
    """Copied in where it sat, carried to where the fork works, and left where it was.

    Not before the fork's first turn: the run driving the agent settles where it keeps its
    sessions after the session is made, and a conversation brought in earlier would be
    somewhere the fork's CLI never looks.
    """
    agent = ClaudeCodeAgent(CONFIG)
    source = _conversation(tmp_path / "snapshot", "the-conversation")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    child = agent.recall("the-conversation", tmp_path / "snapshot", workspace).fork()
    agent.epic = Run(
        tmp_path / "epic" / "sessions"
    )  # as a run does, once it has opened
    assert not (tmp_path / "epic").exists()
    child._at_the_boundary()  # where its first turn starts

    kept = agent.kept()
    sat = kept / "projects" / "-the-workspace-it-was-had-in"
    assert (sat / "the-conversation.jsonl").read_text() == source.read_text()
    assert (sat / "the-conversation" / "subagents" / "agent-1.jsonl").is_file()
    assert not (sat / "somebody-else.jsonl").exists()
    carried = kept / "projects" / _project(str(workspace)) / "the-conversation.jsonl"
    assert carried.is_file()
    assert source.is_file()
    assert child._forked_from == "the-conversation"


def test_a_conversation_nothing_kept_is_not_recalled(
    claude: Path, tmp_path: Path
) -> None:
    agent = ClaudeCodeAgent(CONFIG)
    agent.epic = Run(tmp_path / "epic" / "sessions")
    _conversation(tmp_path / "snapshot", "the-conversation")

    with pytest.raises(RuntimeError, match="no conversation another"):
        agent.recall("another", tmp_path / "snapshot", tmp_path)


def test_a_conversation_cut_from_another_is_recalled_with_its_whole_line(
    tmp_path: Path,
) -> None:
    """Codex reads a forked thread back only beside the threads it was cut from."""
    from hmz.coganchor.agents.base import _naming

    day = tmp_path / "sessions" / "2026" / "10" / "03"
    day.mkdir(parents=True)

    def rollout(ident: str, parent: str | None) -> Path:
        meta = {"id": ident, **({"forked_from_id": parent} if parent else {})}
        path = day / f"rollout-2026-10-03T00-00-00-{ident}.jsonl"
        path.write_text(json.dumps({"type": "session_meta", "payload": meta}) + "\n")
        return path

    first = rollout("first-thread", None)
    second = rollout("second-thread", "first-thread")
    third = rollout("third-thread", "second-thread")
    rollout("somebody-else", None)

    assert set(_naming(tmp_path, "third-thread")) == {first, second, third}
    assert _naming(tmp_path, "first-thread") == [first]
