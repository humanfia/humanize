"""What a run costs, read out of the logs the CLIs keep while they are still writing them.

A backend says what a turn cost once the turn is over, and a turn is minutes long. Its log has
the same numbers a request at a time, so this reads it there -- which is what makes the figure
move while the work is happening rather than in one jump at the end of it.

The rows here are the shapes the real logs have: a Claude transcript's assistant message, a
Codex rollout's `token_count`, a Kimi server event's completed step.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    DshAgent,
    DshAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
)
from hmz.tui.monitor import Monitor
from hmz.tui.tally import Seen, Tally

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hmz.coganchor.agents import AgentBase


def _seen(agent: AgentBase, *idents: str) -> Seen:
    """One session of an agent, as what is told of it says: the backend's names for it.

    Args:
      agent: The agent behind it, which says what runs it, at what, and what it counts.
      idents: What the backend has called the session so far.

    Returns:
      The session, as a tally reads it.
    """
    return Seen(
        agent.id,
        agent.backend,
        agent.config.model,
        type(agent).counts,
        frozenset(idents),
    )


def _rows(path: Path, *rows: Mapping[str, object]) -> None:
    """Appends rows to a log, as the CLI writing it would.

    Args:
      path: The log, whose directory is made if it is not there.
      rows: What to append.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def _said(model: str, output: int) -> dict[str, object]:
    """One assistant message of a Claude transcript, with the usage of the request behind it."""
    return {
        "type": "assistant",
        "message": {
            "model": model,
            "usage": {
                "input_tokens": 2,
                "output_tokens": output,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 0,
            },
        },
    }


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts every backend's home somewhere this test owns."""
    for variable in (
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "DSH_HOME",
        "KIMI_CODE_HOME",
    ):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    return tmp_path


def test_a_claude_turn_is_counted_while_it_is_still_being_written(home: Path) -> None:
    """Read again as it grows, and never twice: a log is appended to, not replaced."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(log, _said("claude-opus-5", 300))
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    monitor = Monitor()
    tally = Tally([_seen(agent, "s1")], monitor)

    tally.read()

    assert monitor.spent == {"claude-opus-5": 1302}  # named as the transcript names it

    tally.read()  # nothing new written, so nothing counted again

    assert monitor.spent == {"claude-opus-5": 1302}

    _rows(
        log, _said("claude-opus-5", 500)
    )  # the turn goes on, still inside the same turn
    tally.read()

    assert monitor.spent == {"claude-opus-5": 2804}


def test_a_sub_agent_is_counted_as_the_model_it_ran_on(home: Path) -> None:
    """A sub-agent writes a transcript of its own, and its tokens are the run's."""
    projects = home / "claude_config_dir" / "projects" / "-tmp-work"
    _rows(projects / "s1.jsonl", _said("claude-opus-5", 300))
    _rows(
        projects / "s1" / "subagents" / "agent-one.jsonl", _said("claude-haiku-4-5", 40)
    )
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    monitor = Monitor()

    Tally([_seen(agent, "s1")], monitor).read()

    assert monitor.spent == {"claude-opus-5": 1302, "claude-haiku-4-5": 1042}


def test_a_codex_thread_is_counted_from_the_rollout_it_writes(home: Path) -> None:
    """`last_token_usage` is the request that just came back, and they add up to the thread."""
    log = (
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl"
    )
    _rows(
        log,
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {"input_tokens": 900, "total_tokens": 1000},
                    "total_token_usage": {"total_tokens": 1000},
                },
            },
        },
    )
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    monitor = Monitor()
    tally = Tally([_seen(agent, "t1")], monitor)

    tally.read()

    assert monitor.spent == {"gpt-5.6-sol": 1000}  # the model the agent runs at

    _rows(
        log,
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {"total_tokens": 500},
                    "total_token_usage": {"total_tokens": 1500},
                },
            },
        },
    )
    tally.read()

    assert monitor.spent == {"gpt-5.6-sol": 1500}


def test_a_dsh_session_is_counted_from_its_assistant_messages(home: Path) -> None:
    log = (
        home
        / "dsh_home"
        / "sessions"
        / "--tmp-work--"
        / "session-d1"
        / "session.v3.jsonl"
    )
    _rows(
        log,
        {
            "type": "assistant/message",
            "data": {
                "message": {
                    "source": {
                        "kind": "model",
                        "provider": "deepseek-official",
                        "model": "deepseek-v4-pro",
                    }
                },
                "usage": {
                    "inputTokens": 11,
                    "outputTokens": 7,
                    "cacheReadTokens": 3,
                    "cacheWriteTokens": 2,
                    "reasoningTokens": 5,
                },
            },
        },
    )
    agent = DshAgent(DshAgentConfig(model="deepseek-v4-flash", effort="high"))
    monitor = Monitor()

    Tally([_seen(agent, "session-d1")], monitor).read()

    # The log names the actual model, and reasoning is already part of output.
    assert monitor.spent == {"deepseek-v4-pro": 23}


def test_a_kimi_session_is_counted_from_the_steps_its_daemon_writes(home: Path) -> None:
    log = home / "kimi_code_home" / "server" / "events" / "session_k1.jsonl"
    _rows(
        log,
        {
            "kind": "event",
            "envelope": {
                "type": "turn.step.completed",
                "payload": {
                    "type": "turn.step.completed",
                    "usage": {
                        "inputOther": 2847,
                        "output": 39,
                        "inputCacheRead": 19200,
                        "inputCacheCreation": 0,
                    },
                },
            },
        },
    )
    agent = KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="max"))
    monitor = Monitor()

    Tally([_seen(agent, "session_k1")], monitor).read()

    assert monitor.spent == {"kimi-code/k3": 22086}


def test_a_row_that_is_only_half_written_is_left_for_the_next_read(home: Path) -> None:
    """A log is read while it is being written, so the last line of it may not be a line."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(log, _said("claude-opus-5", 300))
    with log.open("a") as stream:
        stream.write(
            json.dumps(_said("claude-opus-5", 500))[:40]
        )  # still being written
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    monitor = Monitor()
    tally = Tally([_seen(agent, "s1")], monitor)

    tally.read()

    assert monitor.spent == {
        "claude-opus-5": 1302
    }  # the whole row, and only the whole row

    with log.open("a") as stream:  # the rest of it lands
        stream.write(json.dumps(_said("claude-opus-5", 500))[40:] + "\n")
    tally.read()

    assert monitor.spent == {"claude-opus-5": 2804}


def test_a_session_with_no_log_to_read_is_left_to_its_backend(home: Path) -> None:
    """An agent working on another machine keeps its log there, and says so itself."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    monitor = Monitor()

    Tally([_seen(agent, "nowhere")], monitor).read()
    monitor.spend(agent.id, 4000, model="opus")  # what the turn itself reported

    assert monitor.spent == {"opus": 4000}


def test_what_was_read_is_reported_kind_by_kind(home: Path) -> None:
    """The count is a lump; the bill is not. Only the kinds can be put a price against."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(log, _said("claude-opus-5", 300))
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    monitor = Monitor()

    Tally([_seen(agent, "s1")], monitor).read()

    assert monitor.kinds[("read", "claude-opus-5")] == {
        "input": 2,
        "output": 300,
        "cache_read": 1000,
    }  # and no cache write, which this request did not make


def test_a_log_that_says_only_a_total_is_counted_and_not_priced(home: Path) -> None:
    """Codex's rollout may name a total and no kinds. That is tokens, and no bill."""
    log = (
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl"
    )
    _rows(
        log,
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {"last_token_usage": {"total_tokens": 1000}},
            },
        },
    )
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    monitor = Monitor()

    Tally([_seen(agent, "t1")], monitor).read()

    assert monitor.spent == {"gpt-5.6-sol": 1000}
    # Counted under no kind at all, which is what cannot be priced -- rather than guessed
    # at as input, which would be a bill nobody can stand behind.
    assert monitor.kinds[("read", "gpt-5.6-sol")] == {"": 1000}
    assert monitor.spending()[0].dollars is None


def test_a_cached_read_codex_counted_inside_the_input_is_not_billed_twice(
    home: Path,
) -> None:
    """Codex's `input_tokens` has the cached reads inside it, at a tenth of the price."""
    log = (
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl"
    )
    _rows(
        log,
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 900,
                        "cached_input_tokens": 800,
                        "output_tokens": 100,
                        "total_tokens": 1000,
                    }
                },
            },
        },
    )
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    monitor = Monitor()

    Tally([_seen(agent, "t1")], monitor).read()

    assert monitor.kinds[("read", "gpt-5.6-sol")] == {
        "input": 100,
        "cache_read": 800,
        "output": 100,
    }


def test_a_prompt_that_was_wholly_cached_has_no_plain_input_rather_than_none_of_it(
    home: Path,
) -> None:
    """Taking the cached reads back out can leave nothing, and nothing is not a kind."""
    log = (
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl"
    )
    _rows(
        log,
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 800,
                        "cached_input_tokens": 800,
                        "output_tokens": 100,
                        "total_tokens": 900,
                    }
                },
            },
        },
    )
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    monitor = Monitor()

    Tally([_seen(agent, "t1")], monitor).read()

    assert monitor.kinds[("read", "gpt-5.6-sol")] == {"cache_read": 800, "output": 100}


def test_a_backend_reports_what_its_log_says_once_that_log_has_been_read(
    home: Path,
) -> None:
    """Not before: a rollout written on another machine is one nothing here reads.

    Codex's own server counts its cached reads inside the input and never names one, while
    the rollout it writes does name them. So what the interface can show of a Codex run is
    wider than what its driver reports -- but only where the rollout is in fact on this
    machine, and a kind claimed off a log nobody read would be a nought drawn as a fact.
    """
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    monitor = Monitor()
    tally = Tally([_seen(agent, "t1")], monitor)

    tally.read()  # nothing written yet, so nothing claimed

    assert monitor.reports == {}

    _rows(
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl",
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 900,
                        "output_tokens": 40,
                        "cached_input_tokens": 400,
                        "total_tokens": 940,
                    },
                    "total_token_usage": {"total_tokens": 940},
                },
            },
        },
    )
    tally.read()

    # The driver's two, and the cached read only the rollout names.
    assert monitor.reports[agent.id] == frozenset({"input", "output", "cache_read"})


def _block(ident: str, kind: str, output: int) -> dict[str, object]:
    """One block of a Claude message, written as a row of its own as Claude Code writes it.

    Every block of one message is its own row under the one message id, and every one of them
    carries the whole of the usage of the request that produced the message.
    """
    row = _said("claude-haiku-4-5", output)
    message = row["message"]
    assert isinstance(message, dict)
    message["id"] = ident
    message["content"] = [{"type": kind}]
    return row


def _counted(total: int, last: int) -> dict[str, object]:
    """One `token_count` of a Codex rollout: the request that just came back, and the thread."""
    return {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "last_token_usage": {"output_tokens": last, "total_tokens": last},
                "total_token_usage": {"output_tokens": total, "total_tokens": total},
            },
        },
    }


def test_a_claude_message_written_a_block_at_a_time_is_counted_once(
    home: Path,
) -> None:
    """Its thinking, its words and its tool call are three rows of one request, not three."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(log, _block("msg_1", "thinking", 300), _block("msg_1", "text", 300))
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()
    tally = Tally([_seen(agent, "s1")], monitor)

    tally.read()

    assert monitor.spent == {"claude-haiku-4-5": 1302}

    # Its tool call lands on the next read, and is still the same request.
    _rows(log, _block("msg_1", "tool_use", 300), _block("msg_2", "text", 40))
    tally.read()

    assert monitor.spent == {"claude-haiku-4-5": 1302 + 1042}
    assert monitor.kinds[("read", "claude-haiku-4-5")] == {
        "input": 4,
        "output": 340,
        "cache_read": 2000,
    }


def test_a_claude_message_carried_into_another_session_is_counted_once(
    home: Path,
) -> None:
    """A session picked up under a new name writes the messages it carried over again."""
    projects = home / "claude_config_dir" / "projects" / "-tmp-work"
    _rows(projects / "s1.jsonl", _block("msg_1", "text", 300))
    _rows(
        projects / "s2.jsonl",
        _block("msg_1", "text", 300),
        _block("msg_2", "text", 40),
    )
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()

    Tally([_seen(agent, "s1", "s2")], monitor).read()

    assert monitor.spent == {"claude-haiku-4-5": 1302 + 1042}


def test_a_codex_count_said_again_unmoved_is_counted_once(home: Path) -> None:
    """Codex writes a `token_count` again where nothing was spent, the thread's total unmoved."""
    log = (
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl"
    )
    _rows(log, _counted(1000, 1000), _counted(1000, 1000), _counted(1500, 500))
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    monitor = Monitor()
    tally = Tally([_seen(agent, "t1")], monitor)

    tally.read()

    assert monitor.spent == {"gpt-5.6-sol": 1500}

    _rows(log, _counted(1500, 500))  # said again on the next read, still unmoved
    tally.read()

    assert monitor.spent == {"gpt-5.6-sol": 1500}

    # A thread cut back can come to a total it has come to before, over a request it has not
    # made before: only the row just before is the one said again.
    _rows(log, _counted(1000, 700))
    tally.read()

    assert monitor.spent == {"gpt-5.6-sol": 2200}


def test_a_claude_row_naming_no_message_is_named_by_its_request(
    home: Path,
) -> None:
    """A row with no message id is still one of a request, and its request says which."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    rows: list[dict[str, object]] = []
    for kind in ("thinking", "text"):
        row = _block("", kind, 300)
        row["requestId"] = "req_1"
        rows.append(row)
    _rows(log, *rows)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()

    Tally([_seen(agent, "s1")], monitor).read()

    assert monitor.spent == {"claude-haiku-4-5": 1302}


def test_what_is_read_and_what_the_backend_said_come_to_the_same_bill(
    home: Path,
) -> None:
    """The readout, an agent's box and its session's row are one count of the same tokens.

    The log is read beside what the backend reports at the end of each request, and what was
    spent is the higher of the two. A log counted a row at a time read as twice the run, and
    the readout said twice what every box under it added up to.
    """
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(
        log,
        _block("msg_1", "thinking", 300),
        _block("msg_1", "text", 300),
        _block("msg_2", "text", 40),
        _block("msg_2", "tool_use", 40),
    )
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()
    monitor.begins(agent.id, "claude-haiku-4-5", session="coder/1")
    for output in (300, 40):  # what the backend said of the same two requests
        monitor.spend(
            agent.id,
            1002 + output,
            model="claude-haiku-4-5",
            kinds={"input": 2, "output": output, "cache_read": 1000},
            session="coder/1",
        )

    Tally([_seen(agent, "s1")], monitor).read()

    (spending,) = monitor.spending()
    assert spending.tokens == 2344
    assert sum(monitor.shape().used.values()) == 2344
    assert sum(monitor.shape(sessions=True).used.values()) == 2344
    assert sum(one.tokens for one in monitor.reckoning()) == 2344


#: When the run under test opened its session, and a moment either side of it: a row of the
#: conversation it carried on, and a row of its own.
OPENED = 1_790_000_000.0
BEFORE, AFTER = OPENED - 3600, OPENED + 5


def _iso(moment: float) -> str:
    """A moment as Claude, Codex and Kimi write one: ISO 8601, in UTC, to the millisecond."""
    from datetime import UTC, datetime

    return (
        datetime.fromtimestamp(moment, UTC).isoformat(timespec="milliseconds")[:-6]
        + "Z"
    )


def _at(row: dict[str, object], moment: float) -> dict[str, object]:
    """A row of a Claude transcript or a Codex rollout, written down at a moment."""
    return {**row, "timestamp": _iso(moment)}


def test_a_resumed_claude_session_counts_only_what_this_run_spent(
    home: Path,
) -> None:
    """Its log has the turns an earlier run took in it, and those were that run's to pay."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(
        log,
        _at(_block("msg_old", "thinking", 300), BEFORE),
        _at(_block("msg_old", "text", 300), BEFORE),
        _at(_block("msg_new", "text", 40), AFTER),
    )
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "s1"), since=OPENED)], monitor).read()

    assert monitor.spent == {"claude-haiku-4-5": 1042}


def test_a_forked_claude_session_does_not_count_the_turns_it_was_cut_from(
    home: Path,
) -> None:
    """A fork writes its parent's messages out again, each at the time it was first written.

    And the parent is no session of this run: it was an earlier run's, and the fork the
    first this run opened.
    """
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "child.jsonl"
    _rows(
        log,
        _at(_block("msg_parent", "text", 300), BEFORE),
        _at(_block("msg_child", "text", 40), AFTER),
    )
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "child"), since=OPENED)], monitor).read()

    assert monitor.spent == {"claude-haiku-4-5": 1042}


def test_a_resumed_codex_thread_counts_only_what_this_run_spent(home: Path) -> None:
    log = (
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl"
    )
    _rows(log, _at(_counted(1000, 1000), BEFORE), _at(_counted(1500, 500), AFTER))
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "t1"), since=OPENED)], monitor).read()

    assert monitor.spent == {"gpt-5.6-sol": 500}


def test_a_resumed_dsh_session_counts_only_what_this_run_spent(home: Path) -> None:
    """Dsh writes its time down in milliseconds."""
    log = (
        home
        / "dsh_home"
        / "sessions"
        / "--tmp-work--"
        / "session-d1"
        / "session.v3.jsonl"
    )
    _rows(
        log,
        *(
            {
                "type": "assistant/message",
                "time": int(moment * 1000),
                "data": {"message": {}, "usage": {"inputTokens": tokens}},
            }
            for moment, tokens in ((BEFORE, 1000), (AFTER, 30))
        ),
    )
    agent = DshAgent(DshAgentConfig(model="deepseek-v4-flash", effort="high"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "session-d1"), since=OPENED)], monitor).read()

    assert monitor.spent == {"deepseek-v4-flash": 30}


def test_a_resumed_kimi_session_counts_only_what_this_run_spent(home: Path) -> None:
    """Kimi writes its time on the envelope of the event."""
    log = home / "kimi_code_home" / "server" / "events" / "session_k1.jsonl"
    _rows(
        log,
        *(
            {
                "kind": "event",
                "envelope": {
                    "type": "turn.step.completed",
                    "timestamp": _iso(moment),
                    "payload": {"usage": {"inputOther": tokens}},
                },
            }
            for moment, tokens in ((BEFORE, 1000), (AFTER, 30))
        ),
    )
    agent = KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="max"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "session_k1"), since=OPENED)], monitor).read()

    assert monitor.spent == {"kimi-code/k3": 30}


def test_a_row_that_says_no_time_is_counted(home: Path) -> None:
    """A row nobody can place is more likely this run's than not."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(log, _block("msg_1", "text", 300))
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "s1"), since=OPENED)], monitor).read()

    assert monitor.spent == {"claude-haiku-4-5": 1302}


def test_an_earlier_runs_last_codex_count_said_again_is_not_this_runs(
    home: Path,
) -> None:
    """Codex says the thread's last count again on picking it up, with the total unmoved."""
    log = (
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl"
    )
    _rows(
        log,
        _at(_counted(1000, 1000), BEFORE),
        _at(_counted(1000, 1000), AFTER),
        _at(_counted(1500, 500), AFTER),
    )
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "t1"), since=OPENED)], monitor).read()

    assert monitor.spent == {"gpt-5.6-sol": 500}


def test_an_earlier_runs_claude_message_written_again_is_not_this_runs(
    home: Path,
) -> None:
    """A message of the earlier run, said again as this one begins, is still that run's."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(
        log,
        _at(_block("msg_old", "text", 300), BEFORE),
        _at(_block("msg_old", "tool_use", 300), AFTER),
        _at(_block("msg_new", "text", 40), AFTER),
    )
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "s1"), since=OPENED)], monitor).read()

    assert monitor.spent == {"claude-haiku-4-5": 1042}


@pytest.mark.parametrize(
    "said",
    [
        pytest.param(10**400, id="a number past any float"),
        pytest.param("9999-12-31T23:59:59.999+14:00", id="a date past any clock"),
        pytest.param("yesterday", id="not a date"),
    ],
)
def test_a_row_whose_time_cannot_be_read_is_counted_and_reading_goes_on(
    home: Path, said: object
) -> None:
    """A time nobody could have meant is no reason to stop reading the log."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    log.parent.mkdir(parents=True)
    # Written out by hand, since no float holds the first of them for `json` to write.
    row = json.dumps({**_block("msg_1", "text", 300), "timestamp": "@"})
    log.write_text(row.replace('"@"', json.dumps(said)) + "\n")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "s1"), since=OPENED)], monitor).read()

    assert monitor.spent == {"claude-haiku-4-5": 1302}


def test_a_time_that_names_no_zone_is_read_as_utc(home: Path) -> None:
    """Which is what every one of these logs writes, whatever zone this machine is in."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(
        log,
        {**_block("msg_old", "text", 300), "timestamp": _iso(BEFORE)[:-1]},
        {**_block("msg_new", "text", 40), "timestamp": _iso(AFTER)[:-1]},
    )
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="haiku", effort="high"))
    monitor = Monitor()

    Tally([replace(_seen(agent, "s1"), since=OPENED)], monitor).read()

    assert monitor.spent == {"claude-haiku-4-5": 1042}
