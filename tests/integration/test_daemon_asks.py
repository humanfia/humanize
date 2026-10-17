"""The Epic asking a conversation of the epic by `hmz-ask`, through a host and a stand-in CLI.

The host opens The Epic as a stand-in on PATH, read-only and carrying the `ask-conversation`
skill, and catches `hmz-ask` where the stand-in runs it: refused by the pre-tool-use hook on a
CLI that waits on its hook (`claude`), run as a command line where the stand-in runs it, and
read off the stream and said when the turn would stop where the CLI did neither (`cursor-agent`
in plan mode). Either way `Btw` carries the ask out, the asking callback hears it once, and the
answer reaches The Epic within the question it was asked.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.daemon.link import linked
from hmz.runtime.doing.hosting import Host
from hmz.runtime.watching.btw import Btw, FlowSnapshot
from tests.integration.doubles_agents import Standins, standins

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.timeout(60)

#: The command The Epic is told to run, as the stand-ins run it.
ASKING = "hmz-ask ask --to builder/1 --question 'what is the fact?'"

#: What the session asked knows, and nobody else does.
FACT = "the fact is 42"

CLAUDE = r"""
import shlex, subprocess

note()
session = flags.get("--session-id") or flags.get("--resume") or "s-none"
out({"type": "system", "subtype": "init", "session_id": session,
     "permissionMode": flags.get("--permission-mode", "default")})


def result(text):
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
         "result": text, "usage": {"input_tokens": 5, "output_tokens": 3}})


def gated(command):
    table = json.loads(flags["--settings"]).get("hooks", {}).get("PreToolUse", [])
    asked = json.dumps({"hook_event_name": "PreToolUse", "session_id": session,
                        "tool_name": "Bash", "tool_input": {"command": command}})
    ran = subprocess.run(table[0]["hooks"][0]["command"], shell=True, input=asked,
                         capture_output=True, text=True)
    said = json.loads(ran.stdout).get("hookSpecificOutput")
    if said is None:
        return "allowed"
    return said["permissionDecision"] + ": " + said["permissionDecisionReason"]


for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    note(said)
    if "by the gate" in said:
        result(gated(ASKING + (" 2>&1 | cat" if "redirected" in said else "")))
    elif "search for it" in said:
        result(gated("rg hmz-ask . && echo 'run hmz-ask later'"))
    elif "by the shell" in said:
        ran = subprocess.run(shlex.split(ASKING), capture_output=True, text=True)
        result("printed: " + ran.stdout.strip())
    elif "the sessions" in said:
        ran = subprocess.run(["hmz-ask", "list"], capture_output=True, text=True)
        result("listed: " + ran.stdout.strip())
    else:
        result("nothing asked")
""".replace("ASKING", repr(ASKING))

CURSOR = r"""
prompt = argv[-1]
note(prompt)
chat = "chat-1"
out({"type": "system", "subtype": "init", "session_id": chat, "cwd": ".",
     "model": flags.get("--model", ""), "permissionMode": "plan"})
if "<answer from=" in prompt:
    said = "heard back: " + prompt
else:
    # Reached for and refused by plan mode: nothing ran, and nothing was printed.
    out({"type": "tool_call", "subtype": "started", "call_id": "call-1", "session_id": chat,
         "tool_call": {"shellToolCall": {"args": {"command": ASKING}}}})
    said = "it would not run"
out({"type": "result", "subtype": "success", "is_error": False, "result": said,
     "session_id": chat})
""".replace("ASKING", repr(ASKING))


@pytest.fixture
def stood(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("claude", CLAUDE)
    held.install("cursor-agent", CURSOR)
    return held


@pytest.fixture
def host(tmp_path: Path, stood: Standins) -> Iterator[Host]:
    del stood
    made = Host(cast("Any", SimpleNamespace(workspace=tmp_path)))
    try:
        yield made
    finally:
        made.close()


def _epic(host: Host, runs: str, told: list[tuple[str, str]]) -> Btw:
    """The Epic as a frontend opens it, whose sessions' side copies answer the fact."""
    link = linked(host, "alice")

    def aside(**said: Any) -> dict[str, Any]:
        if said.get("key") == "builder/1":
            return {"side": "copy", "forked": True}
        if said.get("side") == "copy":
            return {"answer": FACT}
        return link.aside(**said)

    return Btw(
        "",
        aside=aside,
        unaside=lambda side: link.asked({"do": "unaside", "side": side}),
        sessions=lambda: ["builder/1"],
        source=lambda: {"runs": runs},
        asking=lambda key, question: told.append((key, question)),
    )


def _snapshot() -> FlowSnapshot:
    return FlowSnapshot(
        flow="rlar",
        task="fix it",
        workspace="/w",
        elapsed=1.0,
        finished=False,
        sessions=(("builder/1", "the builder"),),
    )


def test_an_ask_the_hook_refuses_is_answered_by_its_refusal(host: Host) -> None:
    told: list[tuple[str, str]] = []

    answer = _epic(host, "claude/claude-stand-in", told).ask(
        "ask it by the gate", _snapshot()
    )

    assert told == [("builder/1", "what is the fact?")]
    assert answer.startswith("deny: hmz carried `hmz-ask ask --to builder/1")
    assert answer.endswith(f"(exit 0):\n{FACT}")


def test_an_ask_redirected_and_piped_is_still_carried_out(host: Host) -> None:
    told: list[tuple[str, str]] = []

    answer = _epic(host, "claude/claude-stand-in", told).ask(
        "ask it by the gate, redirected", _snapshot()
    )

    assert told == [("builder/1", "what is the fact?")]
    assert answer.endswith(f"(exit 0):\n{FACT}")


def test_a_command_that_only_names_the_ask_command_is_let_run(host: Host) -> None:
    told: list[tuple[str, str]] = []

    answer = _epic(host, "claude/claude-stand-in", told).ask(
        "search for it", _snapshot()
    )

    assert told == []
    assert answer == "allowed"


def test_an_ask_run_as_a_command_prints_the_answer(host: Host) -> None:
    told: list[tuple[str, str]] = []

    answer = _epic(host, "claude/claude-stand-in", told).ask(
        "ask it by the shell", _snapshot()
    )

    assert told == [("builder/1", "what is the fact?")]
    assert answer == f"printed: {FACT}"


def test_the_command_lists_the_sessions_the_frontend_asks_about(host: Host) -> None:
    told: list[tuple[str, str]] = []

    answer = _epic(host, "claude/claude-stand-in", told).ask(
        "list the sessions", _snapshot()
    )

    # The frontend's sessions, though this host holds no run; and listing is no ask.
    assert answer == "listed: builder/1"
    assert told == []


def test_an_ask_nothing_ran_is_said_as_the_turn_would_stop(
    host: Host, stood: Standins
) -> None:
    told: list[tuple[str, str]] = []

    answer = _epic(host, "cursor-agent/composer-2.5", told).ask(
        "what is the fact?", _snapshot()
    )

    assert told == [("builder/1", "what is the fact?")]
    assert answer.startswith("heard back: ")
    assert f'<answer from="builder/1">\n{FACT}\n</answer>' in answer
    (first, _) = [one.argv for one in stood.calls("cursor-agent")]
    assert first[first.index("--mode") + 1] == "plan"


def test_the_epic_is_told_how_to_ask_and_carries_the_skill(
    host: Host, stood: Standins
) -> None:
    _epic(host, "claude/claude-stand-in", []).ask("hello", _snapshot())

    (prompt,) = stood.said("claude")
    assert "hmz-ask ask --to <session>" in prompt
    (launch, *_) = stood.calls("claude")
    assert launch.flag("--permission-mode") == "plan"
    settings = json.loads(launch.flag("--settings") or "{}")
    assert "PreToolUse" in settings.get("hooks", {})


@pytest.mark.parametrize("runs", ["mcode/MiniMax-M2.5", "dsh/deepseek-v4-pro"])
def test_a_harness_with_no_read_only_rung_is_refused_saying_so(
    host: Host, runs: str
) -> None:
    from hmz.runtime import Refused

    with pytest.raises(Refused, match="no read-only rung"):
        _epic(host, runs, []).ask("hello", _snapshot())
