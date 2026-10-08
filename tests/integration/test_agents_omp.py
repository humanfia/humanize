"""omp, driven through `OhMyPiAgent` against a stand-in `omp --mode rpc` on PATH.

The stand-in holds one process for the whole session and takes its turns as JSON commands on
stdin, as pi's does, in omp's own spelling of that protocol: it says `ready` as it comes up,
answers `get_state` with the id of the session it opened -- there is no `--session-id` to give
it one -- and a `prompt` with the events of one agent run, a tool call arriving in pieces that
name it only on the message so far, the thinking, the words. A run ends on the `agent_end`
that is terminal, never on pi's `agent_settled`; a `steer` mid-run is a word put into it; an
`abort` stops it, and is answered late. It takes only the flags `omp --help` lists, and
`--fork`, which omp parses without listing: anything else -- a flag of pi's -- is refused, as
a turn started with it would be.
"""

from __future__ import annotations

import contextlib
import threading
import time
from typing import TYPE_CHECKING

import psutil
import pytest

from hmz.coganchor.agents import Failed, OhMyPiAgent, OhMyPiAgentConfig
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor.agents import Question

CONFIG = OhMyPiAgentConfig(model="deepseek/stand-in", effort="high")

OMP = r"""
import queue, threading

#: What `omp --help` lists, by whether a value follows, and `--fork`, which omp's own parser
#: takes without the help saying so.
VALUED = {
    "--model", "--smol", "--slow", "--plan", "--prewalk-into", "--plan-yolo-into",
    "--provider", "--api-key", "--system-prompt", "--system-prompt-template",
    "--append-system-prompt", "--profile", "--alias", "--cwd", "--mode", "--config",
    "--add-dir", "--resume", "-r", "--session-dir", "--models", "--tools", "--thinking",
    "--service-tier", "--hook", "--extension", "-e", "--skills", "--export", "--max-time",
    "--approval-mode", "--plugin-dir", "--fork",
}
BARE = {
    "--prewalk", "--no-prewalk", "--plan-yolo", "--allow-home", "--print", "-p",
    "--continue", "-c", "--from-claude", "--from-codex", "--no-session", "--no-tools",
    "--no-lsp", "--no-pty", "--hide-thinking", "--advisor", "--external-thinking",
    "--no-extensions", "--no-skills", "--no-rules", "--no-title", "--print-thoughts",
    "--auto-approve",
}
LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max", "auto")
APPROVING = ("always-ask", "write", "yolo")


def refuse(why, status=2):
    print("omp: " + why, file=sys.stderr, flush=True)
    sys.exit(status)


note()
at = 0
while at < len(argv):
    if argv[at] in VALUED:
        at += 2
    elif argv[at] in BARE or not argv[at].startswith("-"):
        at += 1
    else:
        refuse("unknown flag " + argv[at])
# Stricter than omp, which warns and runs anyway: a turn at a setting it never asked for is
# the failure worth seeing.
if flags.get("--mode") != "rpc":
    refuse("this stand-in speaks --mode rpc and nothing else")
if flags.get("--thinking", "auto") not in LEVELS:
    refuse("no such thinking level " + flags["--thinking"])
if flags.get("--approval-mode", "yolo") not in APPROVING:
    refuse("no such approval mode " + flags["--approval-mode"])

# The sessions this omp has opened, so that one resumed or forked is one that is there.
KEPT = LOG.parent / "omp-sessions"
kept = KEPT.read_text().split() if KEPT.exists() else []
for named in ("--resume", "--fork"):
    if named in flags and flags[named] not in kept:
        refuse('Session "%s" not found.' % flags[named], 1)
if "--resume" in flags:
    SESSION = flags["--resume"]
else:
    SESSION = "01a1c0de-0000-7000-8000-%012d" % (len(kept) + 1)
    with KEPT.open("a") as keeping:
        keeping.write(SESSION + "\n")

lines = queue.Queue()
held = []
SPENT = {"input": 10, "output": 5, "cacheRead": 2, "cacheWrite": 1}


def reading():
    for line in sys.stdin:
        lines.put(line)
    lines.put(None)


def take(waiting=None):
    if held:
        return held.pop(0)
    try:
        line = lines.get(timeout=waiting) if waiting else lines.get()
    except queue.Empty:
        return None
    return None if line is None else json.loads(line)


def until(kind, waiting=30):
    # The next command of one kind, holding every other for after it.
    while (more := take(waiting)) is not None and more["type"] != kind:
        held.append(more)
    return more


def part(event, sofar):
    out({"type": "message_update", "assistantMessageEvent": event,
         "message": {"role": "assistant", "content": sofar}})


def user(said):
    out({"type": "message_start", "message": {"role": "user",
         "content": [{"type": "text", "text": said}]}})


def answers(said):
    words = [{"type": "text", "text": said}]
    part({"type": "text_end", "contentIndex": 0, "content": said}, words)
    out({"type": "message_end", "message": {"role": "assistant", "content": words,
         "usage": SPENT, "stopReason": "stop"}})


def ends(terminal=True):
    out({"type": "agent_end", "messages": [], "isTerminal": terminal})


out({"type": "ready", "protocolVersion": 1, "supportedProtocolVersions": [1, 2]})
# Told rather than asked, as omp tells a client a widget changed: nothing answers it.
out({"type": "extension_ui_request", "id": "w-1", "method": "setWidget",
     "widgetKey": "autoresearch"})
threading.Thread(target=reading, daemon=True).start()
while (told := take()) is not None:
    if told["type"] == "get_state":
        note("get_state " + SESSION)
        out({"type": "response", "command": "get_state", "id": told.get("id"),
             "success": True, "data": {"sessionId": SESSION,
             "sessionFile": str(LOG.parent / (SESSION + ".jsonl"))}})
        continue
    if told["type"] == "steer":
        note("steer " + told["message"])
        user(told["message"])
        continue
    if told["type"] == "set_thinking_level":
        note("set_thinking_level " + told["level"])
        out({"type": "response", "command": told["type"], "success": True})
        continue
    if told["type"] != "prompt":
        note(told["type"])
        out({"type": "response", "command": told["type"], "success": True})
        continue
    said = told["message"]
    note(said)
    if said == "rejected":
        out({"type": "response", "command": "prompt", "success": False,
             "error": "omp would not take it"})
        continue
    if said == "crash":
        print("omp: something broke", file=sys.stderr, flush=True)
        sys.exit(3)
    if said.startswith("/"):
        # A command of omp's own, run where it was said: no agent, so no run to end.
        out({"type": "command_output", "text": "Session: " + SESSION})
        out({"type": "response", "command": "prompt", "success": True,
             "data": {"agentInvoked": False}})
        continue
    out({"type": "response", "command": "prompt", "success": True})
    out({"type": "agent_start"})
    out({"type": "turn_start"})
    user(said)
    thought = {"type": "thinking", "thinking": "thinking about " + said}
    part({"type": "thinking_end", "contentIndex": 0, "content": thought["thinking"]},
         [thought])
    # The call is named only on the message so far: the start itself carries no id and no
    # tool, and the pieces after it carry neither either.
    calling = {"type": "toolCall", "id": "call_1", "name": "bash", "arguments": {}}
    part({"type": "toolcall_start", "contentIndex": 1,
          "partial": {"role": "assistant", "content": [thought, calling]}},
         [thought, calling])
    for piece in ('{"comm', 'and": "echo ', said + '"}'):
        part({"type": "toolcall_delta", "contentIndex": 1, "delta": piece,
              "partial": {"role": "assistant", "content": [thought, calling]}},
             [thought, calling])
    # A call told `write` is one whose arguments are a whole file still arriving: its end is
    # held until the client has said something, which it can only do about a call it has been
    # told of before then.
    steered = until("steer", 5) if said == "write" else None
    called = {**calling, "arguments": {"command": "echo " + said}}
    part({"type": "toolcall_end", "contentIndex": 1, "toolCall": called},
         [thought, called])
    if said == "slow":
        until("abort")
        note("abort")
        out({"type": "message_end", "message": {"role": "assistant",
             "content": [thought, called], "usage": SPENT, "stopReason": "aborted",
             "errorMessage": "Interrupted by user"}})
        ends()
        # The answer to the abort itself comes after the run has ended, and later than any
        # client should wait for it.
        late = threading.Timer(6, out, args=({"type": "response", "command": "abort",
                                              "success": True},))
        late.daemon = True
        late.start()
        continue
    out({"type": "message_end", "message": {"role": "assistant",
         "content": [thought, called], "usage": SPENT, "stopReason": "toolUse"}})
    out({"type": "tool_execution_start", "toolCallId": "call_1", "toolName": "bash"})
    out({"type": "tool_execution_end", "toolCallId": "call_1", "toolName": "bash",
         "isError": False})
    if said == "unfinished":
        out({"type": "message_end", "message": {"role": "assistant", "content": [],
             "usage": SPENT, "stopReason": "error",
             "errorMessage": "it could not finish"}})
        ends()
        continue
    if said == "retried":
        # A request that failed and that omp goes on to try again: the run is not over, and
        # its `agent_end` says so.
        out({"type": "message_end", "message": {"role": "assistant", "content": [],
             "usage": SPENT, "stopReason": "error", "errorMessage": "try again"}})
        ends(terminal=False)
    if said == "start":
        # A run told `start` goes on until a word is steered into it, which it takes before
        # its answer: one run, however many things were said in it.
        steered = until("steer")
    if steered is not None:
        note("steer " + steered["message"])
        user(steered["message"])
    if said == "approve":
        # What omp asks before a tool it is to approve at `--approval-mode always-ask`.
        out({"type": "extension_ui_request", "id": "req-1", "method": "select",
             "title": "Allow tool: write\nPath: hello.txt", "options": ["Approve", "Deny"]})
        more = until("extension_ui_response") or {}
        said = "cancelled" if more.get("cancelled") else str(more.get("value"))
        note("answered " + said)
    answers(said)
    ends()
    if said == "then-exit":
        sys.exit(0)
"""


@pytest.fixture
def omp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("omp", OMP)
    return held


def _launches(omp: Standins) -> list[list[str]]:
    """The command line of each omp started, oldest first."""
    return [one.argv for one in omp.calls() if not one.stdin]


def test_a_turn_says_what_it_did_and_what_it_spent(omp: Standins) -> None:
    said = list(OhMyPiAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["reasoning", "tool", "text", "result"]
    assert said[1].text == "bash echo hello"
    assert said[-1].text == "hello"
    # Two requests, the tool call's and the answer's, at 18 tokens apiece.
    assert dict(said[-1].tokens) == {"deepseek/stand-in": 36}
    assert said[-1].spent.output == 10


def test_one_process_holds_the_session_across_turns(omp: Standins) -> None:
    session = OhMyPiAgent(CONFIG).new()

    assert session("one") == "one"
    assert session("two") == "two"

    (launch,) = _launches(omp)
    assert len({one.pid for one in omp.calls()}) == 1
    assert launch[:2] == ["--mode", "rpc"]
    assert omp.calls()[0].flag("--model") == "deepseek/stand-in"
    assert omp.calls()[0].flag("--thinking") == "high"
    # Asked once, ahead of the first prompt, and what it answered is the session's id.
    assert omp.said() == [f"get_state {session.id}", "one", "two"]


def test_a_word_put_in_mid_run_reaches_it(omp: Standins) -> None:
    session = OhMyPiAgent(CONFIG).new()
    said: list[str] = []

    for event in session.stream("start"):
        if event.kind == "reasoning":
            session.interject("actually, stop")
        said.append(event.kind)

    assert said.count("result") == 1
    assert "took" in said
    assert omp.said()[1:] == ["start", "steer actually, stop"]
    assert session("after") == "after"


def test_a_tool_call_is_said_while_its_arguments_are_still_arriving(
    omp: Standins,
) -> None:
    session = OhMyPiAgent(CONFIG).new()
    said: list[str] = []

    for event in session.stream("write"):
        if event.kind == "tool":
            session.interject("seen")
        said.append(event.kind)

    assert said == ["reasoning", "tool", "took", "text", "result"]


def test_an_agent_end_that_is_not_terminal_does_not_end_the_turn(
    omp: Standins,
) -> None:
    assert OhMyPiAgent(CONFIG).new()("retried") == "retried"


def test_a_turn_cut_off_is_aborted_and_the_session_goes_on(omp: Standins) -> None:
    session = OhMyPiAgent(CONFIG).new()
    assert session("before") == "before"
    took: list[float] = []
    cutters: list[threading.Thread] = []

    def cutting() -> None:
        started = time.monotonic()
        session.cut(why="stopped")
        took.append(time.monotonic() - started)

    def cuts() -> None:
        for event in session.stream("slow"):
            if event.kind == "tool":
                cutters.append(threading.Thread(target=cutting))
                cutters[-1].start()

    held = threading.Thread(target=cuts)
    held.start()
    held.join(30)
    for one in cutters:
        one.join(30)

    assert not held.is_alive()
    # Over once omp has ended the run, rather than once the 5 s an abort is given are out:
    # omp's answer to the abort itself comes later still.
    (cut,) = took
    assert cut < 2.5
    assert session("after") == "after"
    assert omp.said()[1:] == ["before", "slow", "abort", "after"]
    first, second = _launches(omp)
    assert "--resume" not in first
    assert second[second.index("--resume") + 1] == session.id


def test_a_refused_prompt_and_an_errored_message_are_failed_turns(
    omp: Standins,
) -> None:
    session = OhMyPiAgent(CONFIG).new()

    with pytest.raises(Failed, match="omp would not take it"):
        session("rejected")
    with pytest.raises(Failed, match="it could not finish"):
        OhMyPiAgent(CONFIG).new()("unfinished")


def test_an_omp_that_exits_mid_session_fails_the_turn(omp: Standins) -> None:
    with pytest.raises(Failed) as failed:
        OhMyPiAgent(CONFIG).new()("crash")

    assert failed.value.returncode == 3
    assert "something broke" in str(failed.value.stderr)


def test_a_command_omp_runs_itself_is_a_turn_that_ends(omp: Standins) -> None:
    session = OhMyPiAgent(CONFIG).new()

    assert session("/session") == ""
    assert session("after") == "after"


def test_an_effort_moved_mid_session_is_told_to_the_process_holding_it(
    omp: Standins,
) -> None:
    session = OhMyPiAgent(CONFIG).new()
    session("one")

    session.effort = "low"
    session("two")

    assert len(_launches(omp)) == 1
    assert omp.said()[1:] == ["one", "set_thinking_level low", "two"]


def test_a_session_whose_process_went_down_is_resumed_by_the_next(
    omp: Standins,
) -> None:
    session = OhMyPiAgent(CONFIG).new()

    assert session("then-exit") == "then-exit"
    # Exited, as a process gone between turns is: not still on its way out as the next starts.
    (first,) = {one.pid for one in omp.calls()}
    with contextlib.suppress(psutil.NoSuchProcess):
        psutil.Process(first).wait(timeout=10)
    assert session("after") == "after"

    opened, resumed = _launches(omp)
    assert "--resume" not in opened
    assert resumed[resumed.index("--resume") + 1] == session.id
    # Asked by the first process alone: the second was told which session it holds.
    assert omp.said() == [f"get_state {session.id}", "then-exit", "after"]


def test_a_forked_session_carries_on_from_its_parent(omp: Standins) -> None:
    session = OhMyPiAgent(CONFIG).new()
    session("one")

    child = session.fork()
    assert child("two") == "two"

    _, forked = _launches(omp)
    assert forked[forked.index("--fork") + 1] == session.id
    assert child.id not in ("", session.id)
    assert f"get_state {child.id}" in omp.said()


def test_an_agent_that_may_change_nothing_has_every_approval_refused(
    omp: Standins,
) -> None:
    agent = OhMyPiAgent(
        OhMyPiAgentConfig(
            model="deepseek/stand-in", effort="high", permission="read-only"
        )
    )
    asked: list[Question] = []

    def answers(question: Question) -> str:
        asked.append(question)
        return "Approve"

    agent.ask = answers

    assert agent.new()("approve") == "Deny"
    assert omp.calls()[0].flag("--approval-mode") == "always-ask"
    assert asked == []


def test_an_approval_at_no_rung_is_put_to_whoever_drives_the_agent(
    omp: Standins,
) -> None:
    agent = OhMyPiAgent(CONFIG)
    asked: list[Question] = []

    def answers(question: Question) -> str:
        asked.append(question)
        return "Approve"

    agent.ask = answers

    assert agent.new()("approve") == "Approve"
    assert omp.calls()[0].flag("--approval-mode") is None
    assert [(one.text, one.options) for one in asked] == [
        ("Allow tool: write\nPath: hello.txt", ("Approve", "Deny"))
    ]
