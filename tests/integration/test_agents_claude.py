"""Claude Code, driven through `ClaudeCodeAgent` against a stand-in `claude` on PATH.

The stand-in speaks `--input-format stream-json --output-format stream-json`: it opens with a
`system/init` naming the session, reads one user message per line on stdin and answers each
with an `assistant` message and a `result`. What it does is chosen by the prompt, so each test
says the turn it wants by what it asks.
"""

from __future__ import annotations

import dataclasses
import json
import shlex
import subprocess
import threading
import time
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel

from hmz.coganchor.agents import (
    Budget,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    Event,
    Failed,
    Moment,
    Occasion,
    Unrecoverable,
    Unserved,
    Verdict,
)
from hmz.coganchor.fence import Fence
from hmz.runtime.chatting import resolve
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = ClaudeCodeAgentConfig(model="claude-stand-in", effort="high")

CLAUDE = r"""
import subprocess, time

note()
session = flags.get("--session-id") or flags.get("--resume") or "s-none"
model = flags.get("--model")
out({"type": "system", "subtype": "init", "session_id": session, "model": model,
     "permissionMode": flags.get("--permission-mode", "default"),
     "slash_commands": ["compact", "config", "clear", "tidy"], "skills": ["tidy"]})


def result(text, error=False, output=3):
    out({"type": "result", "subtype": "success", "is_error": error, "session_id": session,
         "result": text, "usage": {"input_tokens": 5, "output_tokens": output},
         "modelUsage": {model: {"inputTokens": 5, "outputTokens": output}}})


registered = []


def gated(tool, called):
    table = json.loads(flags["--settings"]).get("hooks", {}).get("PreToolUse", [])
    asked = json.dumps({"hook_event_name": "PreToolUse", "session_id": session,
                        "tool_name": tool, "tool_input": called})
    if registered:
        out({"type": "control_request", "request_id": "h1", "request": {
            "subtype": "hook_callback", "callback_id": registered[0],
            "input": json.loads(asked)}})
        return json.dumps(json.loads(sys.stdin.readline())["response"]["response"])
    if not table:
        return "ungated"
    command = table[0]["hooks"][0]["command"]
    ran = subprocess.run(command, shell=True, input=asked, capture_output=True, text=True)
    return ran.stdout.strip() or "{}"


for line in sys.stdin:
    held = json.loads(line)
    if held.get("type") == "control_request":
        request = held["request"]
        note(json.dumps(request))
        if request["subtype"] == "initialize":
            for one in request.get("hooks", {}).get("PreToolUse", []):
                registered.extend(one["hookCallbackIds"])
        if request["subtype"] == "set_model":
            model = request["model"]
            out({"type": "control_response", "response": {
                "subtype": "success", "request_id": held["request_id"],
                "response": {"model": model}}})
        continue
    said = held["message"]["content"][0]["text"]
    note(said)
    if said == "crash":
        print("claude: something broke", file=sys.stderr, flush=True)
        sys.exit(3)
    if said == "garbage":
        print("this is not json", flush=True)
        sys.exit(0)
    if said == "hang":
        out({"type": "assistant", "message": {"content": [{"type": "text", "text": "a"}]}})
        time.sleep(600)
    if said == "spend":
        for at in range(3):
            out({"type": "assistant", "message": {"id": "m%d" % at, "content": [
                {"type": "text", "text": "part %d" % at}],
                "usage": {"input_tokens": 5, "output_tokens": 400}}})
        time.sleep(600)
    if said == "unfinished":
        result("it could not finish", error=True)
        sys.exit(1)
    if said == "refused":
        print("claude: not today", file=sys.stderr, flush=True)
        result("it would not", error=True)
        continue
    if said == "ask":
        out({"type": "control_request", "request_id": "r1", "request": {
            "subtype": "can_use_tool", "tool_name": "Write",
            "input": {"file_path": "notes.txt"}}})
        answer = json.loads(sys.stdin.readline())["response"]["response"]
        result(answer["behavior"] + ":" + answer.get("message", ""))
        continue
    if said == "gate":
        result(gated("Bash", {"command": "rm -rf /"}))
        continue
    if said == "long":
        out({"type": "assistant", "message": {"content": [{"type": "text", "text": "busy"}]}})
        word = json.loads(sys.stdin.readline())
        note(word["message"]["content"][0]["text"])
        out({"type": "command_lifecycle", "state": "started",
             "command_uuid": word["uuid"]})
        result("heard " + word["message"]["content"][0]["text"])
        continue
    if "--json-schema" in argv:
        result(json.dumps({"value": said}))
        continue
    out({"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "thinking about " + said},
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "echo " + said}},
        {"type": "text", "text": "saying " + said}]}})
    result(said)
"""


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("claude", CLAUDE)
    return held


class Shape(BaseModel):
    value: str


def test_a_turn_says_what_it_did_and_what_it_spent(claude: Standins) -> None:
    session = ClaudeCodeAgent(CONFIG).new()

    said = list(session.stream("hello"))

    assert kinds(said) == ["reasoning", "tool", "text", "result"]
    assert said[1].text == "Bash echo hello"
    assert said[-1].text == "hello"
    assert dict(said[-1].tokens) == {"claude-stand-in": 8}
    assert said[-1].spent.output == 3
    assert session.spent().output == 3
    (launch,) = (one for one in claude.calls() if not one.stdin)
    assert launch.flag("--model") == "claude-stand-in"
    assert launch.flag("--effort") == "high"
    assert launch.flag("--output-format") == "stream-json"
    assert launch.env["HMZ_TEST_INHERITED"] == "from-the-flow"


def test_a_chat_s_native_input_is_served_as_claude_s_own_prompt_would(
    claude: Standins,
) -> None:
    agent = ClaudeCodeAgent(CONFIG)
    session = agent.new()

    assert session("one") == "one"
    natives = {(one.sigil, one.name): one.how for one in session.natives()}
    assert natives[("/", "compact")] == "pass"
    assert natives[("/", "tidy")] == "pass"
    assert natives[("/", "config")] == "refuse"
    assert natives[("/", "model")] == "call"
    assert ("/", "clear") not in natives
    said = list(session.stream("/model claude-other", native=True))
    assert kinds(said) == ["result"]
    assert said[-1].text == "Set model to claude-other"
    assert agent.config.model == "claude-other"
    compacted = list(session.stream("/compact", native=True))
    assert compacted[-1].text == "/compact"
    assert session("two") == "two"

    launches = {one.pid for one in claude.calls()}
    assert len(launches) == 1  # the model moved without the process being started again
    told = [one.stdin for one in claude.calls() if one.stdin]
    assert told == [
        "one",
        json.dumps({"subtype": "set_model", "model": "claude-other"}),
        "/compact",
        "two",
    ]


@pytest.mark.parametrize(
    ("line", "said"),
    [("/model claude-other", "Set model to claude-other"), ("/effort low", None)],
)
def test_a_model_or_effort_typed_as_a_chat_s_first_line_is_called(
    claude: Standins, line: str, said: str | None
) -> None:
    agent = ClaudeCodeAgent(CONFIG)
    session = agent.new()

    # What a chat does with a line: reads it against the catalogue, here before any turn.
    read = resolve(
        line,
        catalog=session.natives(),
        flows=frozenset(),
        prefer="native",
        listed=False,
    )
    assert read.kind == "native"
    assert read.entry is not None
    assert read.entry.how == "call"
    answered = list(session.stream(line, native=read.kind == "native"))

    assert kinds(answered) == ["result"]
    assert said is None or answered[-1].text == said
    assert (
        agent.config != CONFIG
    )  # the agent the chat records is the one it was moved to
    assert not [
        one.stdin for one in claude.calls() if one.stdin
    ]  # nothing was said to it
    # A `/` line naming no entry is still text before the first turn (`core.md` 8.9.13).
    unknown = resolve(
        "/compact",
        catalog=session.natives(),
        flows=frozenset(),
        prefer="native",
        listed=False,
    )
    assert unknown.kind == "prose"


def test_one_process_holds_the_session_across_turns(claude: Standins) -> None:
    agent = ClaudeCodeAgent(CONFIG)
    session = agent.new()

    assert session("one") == "one"
    assert session("two") == "two"

    calls = claude.calls()
    assert len({one.pid for one in calls}) == 1
    assert claude.said() == ["one", "two"]
    assert calls[0].flag("--session-id") == session.id
    assert agent.opened == [session.id]


def test_a_session_restarted_for_another_shape_is_resumed_by_the_new_process(
    claude: Standins,
) -> None:
    session = ClaudeCodeAgent(CONFIG).new()

    assert session("plain") == "plain"
    assert session("shaped", schema=Shape) == Shape(value="shaped")

    first, second = (one for one in claude.calls() if not one.stdin)
    assert first.pid != second.pid
    assert first.flag("--session-id") == session.id
    assert second.flag("--resume") == session.id
    assert second.flag("--session-id") is None


def test_two_sessions_are_two_conversations(claude: Standins) -> None:
    agent = ClaudeCodeAgent(CONFIG)
    first, second = agent.new(), agent.new()

    first("a")
    second("b")

    assert first.id != second.id
    assert set(agent.opened) == {first.id, second.id}


def test_a_turn_held_to_a_shape_answers_with_the_object(claude: Standins) -> None:
    session = ClaudeCodeAgent(CONFIG).new()

    answered = session("shaped", schema=Shape)

    assert answered == Shape(value="shaped")
    launch = claude.calls()[0]
    assert json.loads(launch.flag("--json-schema") or "")["title"] == "Shape"


def test_a_result_marked_as_an_error_is_a_failed_turn(claude: Standins) -> None:
    session = ClaudeCodeAgent(CONFIG).new()

    with pytest.raises(subprocess.CalledProcessError, match="it could not finish"):
        session("unfinished")
    assert session("unfinished", suppress=True) == ""


def test_a_failure_from_a_claude_still_up_is_said_without_waiting_on_it(
    claude: Standins,
) -> None:
    session = ClaudeCodeAgent(CONFIG).new()

    began = time.monotonic()
    with pytest.raises(Failed, match="it would not") as failed:
        session("refused")

    assert time.monotonic() - began < 4
    assert "not today" in str(failed.value.stderr)


def test_a_claude_that_exits_mid_turn_fails_it_with_what_it_said(
    claude: Standins,
) -> None:
    session = ClaudeCodeAgent(CONFIG).new()

    with pytest.raises(Failed) as failed:
        session("crash")

    assert failed.value.returncode == 3
    assert "something broke" in str(failed.value.stderr)
    with pytest.raises(RuntimeError):
        _ = session.id


def test_output_that_is_not_the_protocol_is_skipped_and_the_exit_fails_the_turn(
    claude: Standins,
) -> None:
    with pytest.raises(Failed):
        ClaudeCodeAgent(CONFIG).new()("garbage")


def test_a_turn_that_has_gone_silent_is_ended_by_the_watchdog(
    claude: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        ClaudeCodeAgent(CONFIG).new()("hang")


def test_a_turn_over_its_time_budget_fails_when_told_to(claude: Standins) -> None:
    session = ClaudeCodeAgent(CONFIG).new()
    session.budget = Budget(seconds=1, when="immediately", then="fail")

    with pytest.raises(Unrecoverable):
        session("hang")


def test_a_turn_over_its_time_budget_ends_with_what_it_said(claude: Standins) -> None:
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="claude-stand-in",
            effort="high",
            budget=Budget(seconds=1, when="immediately"),
        )
    )

    said = list(agent.new().stream("hang"))

    assert said[-1].kind == "result"


@pytest.mark.timeout(60)
def test_a_turn_over_its_output_budget_is_cut_off_at_the_next_response(
    claude: Standins,
) -> None:
    session = ClaudeCodeAgent(CONFIG).new()
    session.budget = Budget(output=500)

    said = list(session.stream("spend"))

    assert said[-1].kind == "result"
    assert [event.text for event in said if event.kind == "text"][:2] == [
        "part 0",
        "part 1",
    ]


def test_hooks_watch_the_prompt_and_a_refused_stop_sends_the_agent_on(
    claude: Standins,
) -> None:
    agent = ClaudeCodeAgent(CONFIG)
    prompts: list[str] = []
    agent.hooks.on(
        Moment.USER_PROMPT_SUBMIT, lambda occasion: prompts.append(occasion.prompt)
    )

    def again(occasion: Occasion) -> Verdict | None:
        if occasion.again == 0:
            return Verdict(refused=True, because="once more")
        return None

    agent.hooks.on(Moment.STOP, again)

    assert agent.new()("first") == "once more"
    assert prompts == ["first"]
    assert claude.said() == ["first", "once more"]


@pytest.fixture
def fenced(monkeypatch: pytest.MonkeyPatch) -> ClaudeCodeAgentConfig:
    """The stand-in's config with a fence that writes somewhere, the wall itself not put up.

    A fence is what makes the driver route requests over the stream at all, and what is
    checked here is how they are answered, not what the wall refuses -- which would also keep
    the stand-in from writing down its calls.
    """

    def enforceable(*, net: bool) -> bool:
        del net
        return True

    def wrapper(fence: Fence) -> list[str]:
        del fence
        return []

    monkeypatch.setattr("hmz.coganchor.fence.enforceable", enforceable)
    monkeypatch.setattr("hmz.coganchor.fence.wrapper", wrapper)
    return dataclasses.replace(CONFIG, fence=Fence(write=("/w",), online=True))


def test_a_permission_request_is_put_to_the_hook_and_refused(
    claude: Standins, fenced: ClaudeCodeAgentConfig
) -> None:
    agent = ClaudeCodeAgent(fenced)
    seen: list[Occasion] = []

    def gate(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="not that file")

    agent.hooks.on(Moment.PERMISSION_REQUEST, gate)

    assert agent.new()("ask") == "deny:not that file"
    assert [(one.tool, one.input) for one in seen] == [
        ("Write", {"file_path": "notes.txt"})
    ]
    assert claude.calls()[0].flag("--permission-prompt-tool") == "stdio"


def test_a_permission_nobody_refused_is_allowed(
    claude: Standins, fenced: ClaudeCodeAgentConfig
) -> None:
    agent = ClaudeCodeAgent(fenced)

    assert agent.new()("ask") == "allow:"


def test_a_pre_tool_use_hook_is_served_to_claude_s_own_hook_table(
    claude: Standins,
) -> None:
    agent = ClaudeCodeAgent(CONFIG)
    seen: list[str] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion.about)
        return Verdict(refused=True, because="never that")

    agent.hooks.on(Moment.PRE_TOOL_USE, refuse, tool="Bash")

    answered = json.loads(agent.new()("gate"))

    decided = answered["hookSpecificOutput"]
    assert decided["permissionDecision"] == "deny"
    assert decided["permissionDecisionReason"] == "never that"
    assert seen == ["rm -rf /"]
    settings = json.loads(claude.calls()[0].flag("--settings") or "{}")
    assert shlex.split(settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"])[
        2:5
    ] == [
        "hmz",
        "internal",
        "hook",
    ]


@pytest.fixture
def managed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This machine's `managed-settings.json`, in a folder of the test's."""
    folder = tmp_path / "managed"
    folder.mkdir()
    monkeypatch.setattr("hmz.coganchor.agents.claude.MANAGED", (folder,))
    return folder / "managed-settings.json"


def test_bypass_the_managed_settings_forbid_is_never_launched(
    claude: Standins, fenced: ClaudeCodeAgentConfig, managed: Path
) -> None:
    managed.write_text(
        json.dumps({"permissions": {"disableBypassPermissionsMode": "disable"}})
    )
    agent = ClaudeCodeAgent(fenced)

    events = list(agent.new().stream("first"))
    agent.new()("second")

    notices = [one.text for one in events if one.kind == "notice"]
    assert len(notices) == 1
    assert str(managed) in notices[0]
    launched = claude.calls("claude")
    assert {one.flag("--permission-mode") for one in launched} == {"acceptEdits"}
    assert not any("set_permission_mode" in one for one in claude.said("claude"))


def test_a_pre_tool_use_hook_the_managed_settings_keep_off_a_table_still_refuses(
    claude: Standins, managed: Path
) -> None:
    managed.write_text(json.dumps({"allowManagedHooksOnly": True}))
    agent = ClaudeCodeAgent(CONFIG)
    seen: list[str] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion.about)
        return Verdict(refused=True, because="never that")

    agent.hooks.on(Moment.PRE_TOOL_USE, refuse, tool="Bash")

    answered = json.loads(agent.new()("gate"))

    assert answered["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert seen == ["rm -rf /"]
    settings = json.loads(claude.calls()[0].flag("--settings") or "{}")
    assert "hooks" not in settings


def test_allow_rules_the_managed_settings_drop_are_refused_before_claude_starts(
    claude: Standins, managed: Path
) -> None:
    managed.write_text(json.dumps({"allowManagedPermissionRulesOnly": True}))
    agent = ClaudeCodeAgent(dataclasses.replace(CONFIG, allowed_tools=("Read",)))

    with pytest.raises(Unserved, match="allowManagedPermissionRulesOnly"):
        agent.new()("hello")

    assert claude.calls("claude") == []


def test_a_word_put_in_mid_turn_reaches_the_running_turn(claude: Standins) -> None:
    session = ClaudeCodeAgent(CONFIG).new()
    said: list[Event] = []

    for event in session.stream("long"):
        if event.kind == "text":
            session.interject("also this")
        said.append(event)

    assert kinds(said) == ["text", "took", "result"]
    assert said[-1].text == "heard also this"
    assert claude.said() == ["long", "also this"]


def test_a_turn_cut_off_from_another_thread_ends(claude: Standins) -> None:
    session = ClaudeCodeAgent(CONFIG).new()
    ended: list[BaseException | None] = []

    def runs() -> None:
        try:
            session("hang")
        except BaseException as failed:  # noqa: BLE001 -- whatever ended it is the answer
            ended.append(failed)
        else:
            ended.append(None)

    turn = threading.Thread(target=runs)
    turn.start()
    while not claude.said():
        turn.join(0.05)
    session.cut(why="the flow moved on")
    turn.join(30)

    assert not turn.is_alive()
    assert ended
