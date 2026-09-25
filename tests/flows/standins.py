"""Stand-in CLIs the harness drivers are held to their contract against, off the network.

Three of them, one per way coganchor drives a CLI: `claude`, one process held open and spoken
to in stream JSON; `codex`, an app server spoken to in JSON-RPC; and `opencode`, one command
per turn. Each prints what its real CLI prints, opens with what that CLI's own parser refuses
(:func:`tests.agents.standins.refusing`), and answers what the checks in
:mod:`tests.flows.contracts` ask as a model would. A few prompts make it do what a model can be
asked to:

- `Reply with the single word: <word>` answers the word, and a `JSON object whose "answer" is
  "ok"` answers that object.
- A prompt starting `slow` keeps the turn going for half a minute, saying a word every tenth
  of a second, and takes a word put in mid-turn as the end of it.
- `use a tool` reaches for `Bash` -- asking permission where the CLI asks -- and answers
  `allowed` or `denied: <why>`; `ask me` asks its user `Which way?` and answers what it was
  told; `delegate` starts a subagent.
- `fail: <words>` fails the turn saying the words.

Each writes one JSON line per call to `<itself>.log`: its argv and working directory where it
starts, and every thing said to it.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from tests.agents import standins

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["CLAUDE", "CODEX", "OPENCODE", "install"]

#: What every stand-in starts with: its log, its answers, and a reader of its stdin.
_COMMON = r"""
import json, os, pathlib, queue, re, shlex, subprocess, sys, threading, time, uuid

LOG = pathlib.Path(sys.argv[0] + ".log")


def note(entry):
    with LOG.open("a") as stream:
        stream.write(json.dumps(entry) + "\n")


def answered(said, schema=False):
    word = re.search(r"single word: (\w+)", said)
    if schema or 'JSON object whose "answer"' in said:
        return json.dumps({"answer": "ok"})
    if said.startswith("/goal "):
        return "goal met: " + said[len("/goal "):]
    return word.group(1) if word else said


def failing(said):
    return said[len("fail: "):] if said.startswith("fail: ") else None
"""

#: `claude --print --input-format stream-json`, held open for the session. It keeps each
#: conversation where the real one does -- `projects/<the directory as a name>/<id>.jsonl`
#: under `$CLAUDE_CONFIG_DIR` -- and refuses to resume one that is not there.
CLAUDE = (
    _COMMON
    + r"""
argv = sys.argv[1:]
flags = {}
at = 0
while at < len(argv):
    word = argv[at]
    if word.startswith("--") and at + 1 < len(argv) and not argv[at + 1].startswith("--"):
        flags[word] = argv[at + 1]
        at += 2
    else:
        flags[word] = True
        at += 1
home = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
projects = home / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd())
model = flags.get("--model", "m")
schema = flags.get("--json-schema")
settings = json.loads(flags.get("--settings") or "{}")
gate = [
    hook["command"]
    for table in settings.get("hooks", {}).get("PreToolUse", [])
    for hook in table.get("hooks", [])
]


def out(said):
    print(json.dumps(said), flush=True)


if "--resume" in flags:
    was = flags["--resume"]
    if not (projects / f"{was}.jsonl").exists():
        out({"type": "result", "subtype": "error_during_execution", "is_error": True,
             "result": f"No conversation found with session ID: {was}"})
        sys.exit(1)
    session = str(uuid.uuid4()) if flags.get("--fork-session") else was
    if session != was:
        (projects / f"{session}.jsonl").write_text((projects / f"{was}.jsonl").read_text())
else:
    session = flags["--session-id"]
projects.mkdir(parents=True, exist_ok=True)
transcript = projects / f"{session}.jsonl"
note({"argv": argv, "cwd": os.getcwd(), "session": session})
out({"type": "system", "subtype": "init", "session_id": session})

lines = queue.Queue()


def reading():
    for line in sys.stdin:
        lines.put(json.loads(line))
    lines.put(None)


threading.Thread(target=reading, daemon=True).start()
held = []
spent = {"in": 0, "out": 0}


def take(timeout=None):
    if held:
        return held.pop(0)
    try:
        return lines.get(timeout=timeout)
    except queue.Empty:
        return False


def speak(text, tokens=3):
    spent["in"] += 10
    spent["out"] += tokens
    out({"type": "assistant", "message": {"id": str(uuid.uuid4()), "content": [
        {"type": "text", "text": text}], "usage": {"input_tokens": 10, "output_tokens": tokens}}})


def result(text):
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
         "result": text, "modelUsage": {model: {"inputTokens": spent["in"],
                                                 "outputTokens": spent["out"]}}})


def asked(request):
    named = str(uuid.uuid4())
    out({"type": "control_request", "request_id": named, "request": request})
    while True:
        said = take()
        if said is None:
            sys.exit(0)
        if said.get("type") == "control_response" and said["response"]["request_id"] == named:
            return said["response"]["response"]
        held.append(said)


def gated(tool, called):
    for command in gate:
        ran = subprocess.run(shlex.split(command), input=json.dumps({
            "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": called,
            "session_id": session}), capture_output=True, text=True, check=False)
        told = json.loads(ran.stdout or "{}").get("hookSpecificOutput", {})
        if told.get("permissionDecision") == "deny":
            return told.get("permissionDecisionReason", "denied")
    return None


def turn(said):
    with transcript.open("a") as stream:
        stream.write(json.dumps({"user": said}) + "\n")
    if (why := failing(said)) is not None:
        out({"type": "result", "subtype": "error_during_execution", "is_error": True,
             "session_id": session, "result": why})
        print(why, file=sys.stderr, flush=True)
        sys.exit(1)
    if said.startswith("slow"):
        for step in range(300):
            more = take(0.1)
            if more is None:
                sys.exit(0)
            if more:
                words = more["message"]["content"][0]["text"]
                out({"type": "command_lifecycle", "state": "started",
                     "command_uuid": more.get("uuid", "")})
                result("put aside")
                speak("heard " + words)
                result(answered(words))
                return
            speak(f"step {step}", 1)
        result("slow done")
        return
    if said == "use a tool":
        called = {"command": "echo hi"}
        out({"type": "assistant", "message": {"id": str(uuid.uuid4()), "content": [
            {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": called}],
            "usage": {"input_tokens": 10, "output_tokens": 2}}})
        if (why := gated("Bash", called)) is not None:
            result("blocked: " + why)
            return
        told = asked({"subtype": "can_use_tool", "tool_name": "Bash", "input": called})
        if told.get("behavior") == "allow":
            result("allowed")
        else:
            result("denied: " + told.get("message", ""))
        return
    if said == "ask me":
        told = asked({"subtype": "can_use_tool", "tool_name": "AskUserQuestion", "input": {
            "questions": [{"question": "Which way?", "header": "Way",
                           "options": [{"label": "left"}, {"label": "right"}]}]}})
        answers = told.get("updatedInput", {}).get("answers", {})
        result(answers.get("Which way?", "nobody"))
        return
    if said == "delegate":
        out({"type": "assistant", "message": {"id": str(uuid.uuid4()), "content": [
            {"type": "tool_use", "id": "toolu_2", "name": "Task",
             "input": {"description": "look around"}}],
            "usage": {"input_tokens": 10, "output_tokens": 2}}})
        out({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_2", "content": "looked"}]}})
        result("delegated")
        return
    speak("working")
    result(answered(said, schema=bool(schema)))


while True:
    said = take()
    if said is None:
        break
    if said.get("type") != "user":
        continue
    text = said["message"]["content"][0]["text"]
    note({"said": text, "session": session})
    turn(text)
"""
)

#: `codex app-server`, spoken to in JSON-RPC. A turn runs on a thread of its own so that a
#: steer, an interrupt and the answers to what it asks can arrive while it does.
CODEX = (
    _COMMON
    + r"""
ASKS = "default_mode_request_user_input"
writing = threading.Lock()
answers = {}
arrived = threading.Condition()
turns = {}
goals = {}


def send(message):
    with writing:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()


def reply(ident, result):
    send({"jsonrpc": "2.0", "id": ident, "result": result})


def request(ident, method, params):
    send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
    with arrived:
        arrived.wait_for(lambda: ident in answers)
        return answers.pop(ident)


def notify(method, params):
    send({"jsonrpc": "2.0", "method": method, "params": params})


TOTALS = pathlib.Path(sys.argv[0] + ".totals.json")


def usage(thread, named, step):
    # What the thread has spent all told, kept where a server started after this one finds
    # it: a real one restores a thread's totals from its rollout when it picks it back up.
    with writing:
        totals = json.loads(TOTALS.read_text()) if TOTALS.exists() else {}
        total = totals[thread] = totals.get(thread, 0) + step
        TOTALS.write_text(json.dumps(totals))
    notify("thread/tokenUsage/updated", {"threadId": thread, "turnId": named, "tokenUsage": {
        "last": {"inputTokens": 10 * step, "outputTokens": step},
        "total": {"inputTokens": 10 * total, "outputTokens": total}}})


def run(thread, params, named):
    said = params["input"][0]["text"]
    state = turns[named]
    notify("turn/started", {"threadId": thread, "turnId": named})
    if (why := failing(said)) is not None:
        notify("turn/completed", {"threadId": thread, "turn": {
            "id": named, "status": "failed", "error": {"message": why}}})
        return
    if said.startswith("slow"):
        for step in range(300):
            if state["interrupted"]:
                notify("turn/completed", {"threadId": thread, "turn": {
                    "id": named, "status": "interrupted"}})
                return
            if state["steers"]:
                words, client = state["steers"].pop(0)
                notify("item/started", {"threadId": thread, "turnId": named, "item": {
                    "type": "userMessage", "clientId": client, "content": words}})
                said = words
                break
            usage(thread, named, 1)
            time.sleep(0.1)
    if said == "use a tool" and params.get("approvalPolicy") in (None, "never"):
        said = "ran without asking"
    elif said == "use a tool":
        told = request("ok_" + named, "item/commandExecution/requestApproval", {
            "itemId": "i", "threadId": thread, "turnId": named, "command": "echo hi"})
        said = "allowed" if told.get("decision") == "accept" else "denied"
    elif said == "ask me" and ASKS not in sys.argv:
        said = "nobody"
    elif said == "ask me":
        told = request("ask_" + named, "item/tool/requestUserInput", {
            "itemId": "i", "threadId": thread, "turnId": named, "questions": [
                {"id": "way", "header": "Way", "question": "Which way?",
                 "options": [{"label": "left"}, {"label": "right"}]}]})
        picked = told.get("answers", {}).get("way", {}).get("answers", [])
        said = picked[0] if picked else "nobody"
    elif said == "delegate":
        notify("item/started", {"threadId": thread, "turnId": named, "item": {
            "id": "sub", "type": "collabAgentToolCall", "tool": "look around"}})
        notify("item/completed", {"threadId": thread, "turnId": named, "item": {
            "id": "sub", "type": "collabAgentToolCall", "tool": "look around"}})
        said = "delegated"
    else:
        said = answered(said, schema="outputSchema" in params)
    usage(thread, named, 2)
    notify("item/completed", {"threadId": thread, "turnId": named, "item": {
        "id": "msg", "type": "agentMessage", "text": said}})
    if thread in goals:
        notify("thread/goal/updated", {"threadId": thread, "goal": {"status": "complete"}})
        del goals[thread]
    notify("turn/completed", {"threadId": thread, "turn": {"id": named, "status": "completed"}})
    notify("thread/status/changed", {"threadId": thread, "status": {"type": "idle"}})


note({"argv": sys.argv[1:], "cwd": os.getcwd()})
for line in sys.stdin:
    call = json.loads(line)
    if "method" not in call:
        with arrived:
            answers[call["id"]] = call.get("result") or {}
            arrived.notify_all()
        continue
    note({"method": call["method"], "params": call.get("params", {})})
    params = call.get("params", {})
    method = call["method"]
    if method in ("thread/start", "thread/fork"):
        thread = "thread_" + uuid.uuid4().hex[:8]
        reply(call["id"], {"thread": {"id": thread}})
        notify("thread/status/changed", {"threadId": thread, "status": {"type": "idle"}})
    elif method == "turn/start":
        named = "turn_" + uuid.uuid4().hex[:8]
        turns[named] = {"interrupted": False, "steers": []}
        reply(call["id"], {"turn": {"id": named}})
        threading.Thread(target=run, args=(params["threadId"], params, named),
                         daemon=True).start()
    elif method == "turn/steer":
        state = turns.get(params.get("expectedTurnId"), {"steers": []})
        state["steers"].append((params["input"][0]["text"],
                                params.get("clientUserMessageId", "")))
        reply(call["id"], {})
    elif method == "turn/interrupt":
        turns.get(params.get("turnId"), {})["interrupted"] = True
        reply(call["id"], {})
    elif method == "thread/goal/set":
        goals[params["threadId"]] = params["objective"]
        reply(call["id"], {})
    elif "id" in call:
        reply(call["id"], {})
"""
)

#: `opencode run`, one process per turn, taking the prompt on stdin and answering in events.
OPENCODE = (
    _COMMON
    + r"""
said = sys.stdin.read()
flags = dict(zip(sys.argv, sys.argv[1:]))
forked = "--fork" in sys.argv
session = ("ses_" + uuid.uuid4().hex[:8]) if forked or "--session" not in flags else (
    flags["--session"])
note({"argv": sys.argv[1:], "cwd": os.getcwd(), "said": said, "session": session})


def out(kind, part):
    print(json.dumps({"type": kind, "sessionID": session, "part": part}), flush=True)


if (why := failing(said)) is not None:
    print(json.dumps({"type": "error", "sessionID": session,
                      "error": {"name": "APIError", "data": {"message": why}}}), flush=True)
    sys.exit(0)
out("step_start", {"id": "prt_start", "type": "step-start"})
if said.startswith("slow"):
    for step in range(300):
        out("step_finish", {"id": f"prt_{step}", "type": "step-finish", "reason": "tool-calls",
                            "tokens": {"total": 2, "input": 1, "output": 1, "reasoning": 0,
                                       "cache": {"read": 0, "write": 0}}})
        time.sleep(0.1)
out("text", {"id": "prt_text", "type": "text", "text": answered(said)})
out("step_finish", {"id": "prt_two", "type": "step-finish", "reason": "stop",
                    "tokens": {"total": 7, "input": 5, "output": 2, "reasoning": 0,
                               "cache": {"read": 0, "write": 0}}})
"""
)


def install(binaries: Path, named: str, script: str) -> Path:
    """Puts one stand-in on PATH's first directory under the name its CLI is installed as.

    Args:
      binaries: The directory, which the caller puts at the front of PATH.
      named: The command.
      script: What it runs: :data:`CLAUDE`, :data:`CODEX` or :data:`OPENCODE`.

    Returns:
      The log it writes, one JSON object a line.
    """
    binaries.mkdir(parents=True, exist_ok=True)
    fake = binaries / named
    fake.write_text(f"#!{sys.executable}\n{standins.refusing(named)}{script}")
    fake.chmod(0o755)
    return binaries / f"{named}.log"


def path_with(binaries: Path) -> str:
    """PATH with a directory of stand-ins in front of it."""
    return f"{binaries}{os.pathsep}{os.environ.get('PATH', '')}"
