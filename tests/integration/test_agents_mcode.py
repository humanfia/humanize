"""MiniMax Code, driven through `MiniMaxCodeAgent` against a stand-in `mcode` on PATH.

The stand-in is an `mcode exec --output-format stream-json`: one run per turn with the prompt
on stdin, answering in sequenced JSON lines -- the turn's tool calls, reasoning and message as
`item.*`, then `turn.completed` with what it spent and `exec.completed` with the result. A turn
that failed says `turn.failed`, and exits non-zero. A session is carried on by `--session`.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import psutil
import pytest

from hmz.coganchor import providers
from hmz.coganchor.agents import (
    SUBAGENTS,
    Budget,
    Failed,
    MiniMaxCodeAgent,
    MiniMaxCodeAgentConfig,
    Moment,
    Occasion,
    base,
)
from hmz.coganchor.agents.watchdog import WATCHDOG
from hmz.coganchor.gateway import gatewayable
from hmz.coganchor.providers import Provider
from tests.integration.doubles_agents import (
    Endpoint,
    Standins,
    kinds,
    serving,
    standins,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.coganchor.agents import Event

MODEL = "custom_provider:gateway/minimax-stand-in"
CONFIG = MiniMaxCodeAgentConfig(model=MODEL, effort="", permission="bypass")

MCODE = r"""
prompt = sys.stdin.read()
note(prompt)
session = flags.get("--session", "mvs_stand_in")
turn = "turn_1"
at = [0]


def say(kind, **rest):
    at[0] += 1
    out({"schemaVersion": 1, "sequence": at[0], "timestampMs": 1, "runId": "exec_" + turn,
         "sessionId": session, "turnId": turn, "type": kind, **rest})


def tool(call, name, status, **rest):
    return {"id": call, "type": "tool_call",
            "toolCall": {"id": call, "name": name, "status": status, **rest}}


model = {"providerId": "custom_provider:gateway", "modelId": "minimax-stand-in"}
say("exec.started")
say("session.resumed" if "--session" in flags else "session.started")
say("turn.started")
say("item.started", item=tool("call_1", "bash", 4))
say("item.completed", item=tool("call_1", "bash", 2, input={"command": "ls src"},
                                 output={"content": [{"type": "text", "text": "x.py"}]}))
if prompt == "fleet":
    ask = {"description": "read the tests", "prompt": "read them", "subagent_type": "explore"}
    say("item.started", item=tool("call_2", "task", 4))
    say("item.updated", item=tool("call_2", "task", 1, input=ask))
    say("item.completed", item=tool("call_2", "task", 2, input=ask,
                                     output={"content": [{"type": "text", "text": "done"}]}))
say("item.completed", item={"id": "m1:reasoning", "type": "reasoning", "content": "hmm"})
say("item.completed", item={"id": "m1:message", "type": "agent_message", "content": prompt})
if prompt == "unfinished":
    error = {"category": "runtime", "message": "it could not finish", "retryable": False}
    say("turn.failed", status="failed", error=error, durationMs=12)
    say("exec.completed", result={"type": "exec.result", "sessionId": session,
                                  "turnId": turn, "status": "failed", "error": error})
    print("mcode exec failed: it could not finish.", file=sys.stderr)
    raise SystemExit(4)
usage = {"inputTokens": 130, "outputTokens": 12, "cacheReadTokens": 90, "totalTokens": 142}
say("turn.completed", model=model, usage=usage, usageIncomplete=False, durationMs=7)
say("exec.completed", result={"type": "exec.result", "sessionId": session, "turnId": turn,
                              "status": "succeeded", "model": model, "usage": usage,
                              "output": prompt})
"""


@pytest.fixture
def mcode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("mcode", MCODE)
    return held


def test_a_turn_says_what_it_did_and_what_it_spent(mcode: Standins) -> None:
    said = list(MiniMaxCodeAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["tool", "reasoning", "text", "result"]
    assert "ls src" in said[0].text
    assert said[-1].text == "hello"
    assert said[-1].spent.output == 12


def test_each_turn_is_a_run_of_exec_carrying_the_session_on(mcode: Standins) -> None:
    session = MiniMaxCodeAgent(CONFIG).new()

    assert session("one") == "one"
    assert session("two") == "two"

    first, second = mcode.calls()
    assert first.argv[0] == "exec"
    assert first.flag("--output-format") == "stream-json"
    assert first.flag("--model") == MODEL
    assert first.flag("--session") is None
    assert second.flag("--session") == session.id == "mvs_stand_in"
    assert mcode.said() == ["one", "two"]


def test_an_agent_it_starts_of_its_own_fires_the_subagent_moments(
    mcode: Standins,
) -> None:
    agent = MiniMaxCodeAgent(CONFIG)
    seen: list[Occasion] = []
    for moment in SUBAGENTS:
        agent.hooks.on(moment, seen.append)

    said = list(agent.new().stream("fleet"))

    assert "subagent" in kinds(said)
    assert [one.moment for one in seen] == [Moment.SUBAGENT_START, Moment.SUBAGENT_STOP]


def test_a_failed_turn_is_a_failure_with_what_it_said(mcode: Standins) -> None:
    session = MiniMaxCodeAgent(CONFIG).new()

    with pytest.raises(Failed, match="it could not finish") as failed:
        session("unfinished")

    assert failed.value.returncode == 4
    with pytest.raises(RuntimeError):
        _ = session.id


#: An `mcode exec` that says one thing and goes on without ever reading its input, with a child
#: of its own holding the same pipes, as a tool or a server a CLI starts does.
LINGERING = r"""
import subprocess, time

note()
subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
out({"type": "item.completed", "item": {"type": "agent_message", "content": "partial"}})
time.sleep(600)
"""


def _running(process: psutil.Process) -> bool:
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def test_a_turn_let_go_of_mid_stream_leaves_nothing_running(mcode: Standins) -> None:
    mcode.install("mcode", LINGERING)
    session = MiniMaxCodeAgent(CONFIG).new()
    threads = set(threading.enumerate())
    ours = psutil.Process()
    already = {one.pid for one in ours.children(recursive=True)}
    seen: list[Event] = []
    tree: list[psutil.Process] = []

    def reads() -> None:
        # Both readers are blocked in the command's pipes when the turn is let go of.
        for event in session.stream("x"):
            seen.append(event)
            # Named while all of it is still ours: a child outliving its parent is not.
            tree.extend(
                one for one in ours.children(recursive=True) if one.pid not in already
            )
            break  # and the turn is closed as the loop lets go of it

    reader = threading.Thread(target=reads, daemon=True)
    try:
        reader.start()
        reader.join(timeout=15)

        assert not reader.is_alive(), "letting go of the turn waited on its command"
        assert [one.text for one in seen] == ["partial"]
        assert len(tree) >= 2  # the command and the child it started
        assert [one for one in tree if _running(one)] == []
        assert set(threading.enumerate()) - threads == set()
    finally:
        for one in tree:
            with contextlib.suppress(psutil.Error):
                one.kill()
        reader.join(timeout=15)


#: What an `mcode exec` asked `first` does instead of answering: leaves a daemon of its own, out
#: of its tree and holding its stdout, which says more -- an answer and a failure -- only once the
#: next turn's command lets it, and then waits for the test to have heard it all said; says one
#: thing itself and goes on. Asked `second`, it lets the daemon speak and waits for that first.
ESCAPING = r"""
import time

def waited(name):
    at = pathlib.Path(sys.argv[0]).with_name(name)
    given = time.monotonic() + 60
    while not at.exists() and time.monotonic() < given:
        time.sleep(0.01)

if prompt == "first":
    if os.fork() == 0:
        os.setsid()
        if os.fork() != 0:
            os._exit(0)
        note(json.dumps({"daemon": os.getpid()}))
        waited("let")
        out({"type": "item.completed", "item": {"type": "agent_message", "content": "stale"}})
        out({"type": "turn.failed", "error": {"message": "abandoned command failure"}})
        os._exit(0)
    os.wait()
    out({"type": "item.completed", "item": {"type": "agent_message", "content": "partial"}})
    time.sleep(600)
if prompt == "second":
    pathlib.Path(sys.argv[0]).with_name("let").touch()
    waited("heard")
"""


def test_what_a_turn_let_go_of_leaves_saying_is_not_the_next_turns(
    mcode: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not waited on longer than it takes to see the turn's pumps are still sitting in its pipes.
    monkeypatch.setattr(base, "DRAIN_SECONDS", 0.5)
    read = "prompt = sys.stdin.read()\nnote(prompt)\n"
    mcode.install("mcode", MCODE.replace(read, read + ESCAPING, 1))
    session = MiniMaxCodeAgent(CONFIG).new()
    before = set(threading.enumerate())
    said: list[str] = []

    def first() -> None:
        for event in session.stream("first"):
            said.append(event.text)
            break  # and the turn is closed as the loop lets go of it

    try:
        first()
        assert said == ["partial"]
        # What still reads the first turn's pipes, which the daemon holds open past it.
        left = set(threading.enumerate()) - before
        assert left

        def heard() -> None:
            # Once the second turn has let the daemon say its piece, and the first turn's
            # pumps have read every word of it.
            given = time.monotonic() + 60
            while any(one.is_alive() for one in left) and time.monotonic() < given:
                time.sleep(0.01)
            (mcode.bin / "heard").touch()

        hearing = threading.Thread(target=heard, daemon=True)
        hearing.start()
        # Said to a session whose last turn's leftovers spoke while this one ran: not heard.
        assert session("second") == "second"
        hearing.join(timeout=60)
        assert not any(one.is_alive() for one in left)
    finally:
        for one in mcode.said():
            if '"daemon"' in one:
                with contextlib.suppress(psutil.Error):
                    psutil.Process(json.loads(one)["daemon"]).kill()


#: What an `mcode exec` asked `first` does instead of answering: says one thing and then nothing,
#: which is what a watchdog and a budget's clock cut off; and once the one cutting it off has
#: begun telling whoever watches, one thing more to let go of the turn at. Asked `second`, it
#: says it is running and answers only once the test lets it.
STALLING = r"""
import time

def waited(name):
    at = pathlib.Path(sys.argv[0]).with_name(name)
    given = time.monotonic() + 60
    while not at.exists() and time.monotonic() < given:
        time.sleep(0.01)

if prompt == "first":
    out({"type": "item.completed", "item": {"type": "agent_message", "content": "partial"}})
    waited("told")
    out({"type": "item.completed", "item": {"type": "agent_message", "content": "closing"}})
    time.sleep(600)
if prompt == "second":
    pathlib.Path(sys.argv[0]).with_name("running").touch()
    waited("go")
"""


@pytest.mark.parametrize("by", ["watchdog", "budget"])
def test_a_cut_off_held_up_past_its_turn_does_not_reach_the_next(
    mcode: Standins, monkeypatch: pytest.MonkeyPatch, by: str
) -> None:
    # A cut-off raised from a thread of its own -- the watchdog's, a budget's clock -- tells
    # whoever watches the agent before it ends anything; one told who takes their time can
    # hold it until its turn is over and the next is running. It ends nothing of the next.
    read = "prompt = sys.stdin.read()\nnote(prompt)\n"
    mcode.install("mcode", MCODE.replace(read, read + STALLING, 1))
    monkeypatch.setenv(WATCHDOG, "0.05" if by == "watchdog" else "0")
    agent = MiniMaxCodeAgent(CONFIG)
    told, holding, spoke = threading.Event(), threading.Event(), threading.Event()

    def listener(_: object, __: object, event: Event) -> None:
        if event.text.startswith("cutting the turn off") and not told.is_set():
            told.set()
            (mcode.bin / "told").touch()
            holding.wait(60)

    agent.watch(listener)
    session = agent.new()
    if by == "budget":
        session.budget = Budget(seconds=0.2, when="immediately")

        class Clock(threading.Timer):
            # The budget's clock, counting from the turn's first word rather than from its
            # start: a command slow to start would spend the budget before saying anything.
            def run(self) -> None:
                spoke.wait(60)
                super().run()

        monkeypatch.setattr(threading, "Timer", Clock)
    before = set(threading.enumerate())
    said: list[str] = []
    started = len(mcode.calls())

    def first() -> None:
        for event in session.stream("first"):
            said.append(event.text)
            spoke.set()
            if event.text == "closing":
                break  # and the turn is closed as the loop lets go of it

    try:
        first()
        assert said == ["partial", "closing"]
        assert told.is_set()
        # Still telling the watcher, its turn closed under it.
        held = set(threading.enumerate()) - before
        assert held
        monkeypatch.setenv(WATCHDOG, "0")
        session.budget = Budget()

        def lets_it_go() -> None:
            # Once the next turn's command is running: the held cut-off goes on, and is done
            # with before that command answers.
            given = time.monotonic() + 60
            while not (mcode.bin / "running").exists() and time.monotonic() < given:
                time.sleep(0.01)
            holding.set()
            for one in held:
                one.join(timeout=60)
            (mcode.bin / "go").touch()

        letting = threading.Thread(target=lets_it_go, daemon=True)
        letting.start()
        assert session("second") == "second"
        letting.join(timeout=60)
        # One command for each turn: none cut off and tried again.
        assert len(mcode.calls()) - started == 2
    finally:
        holding.set()


#: An `mcode` keeping the providers added to it in its home, as `provider add` and `provider
#: remove` say, and running a turn of `exec` on one of them: chat completions at its base URL
#: under the key it was added with, streamed -- refusing a model it was not added with.
ROUTED = r"""
import urllib.request

kept = pathlib.Path(os.environ["HOME"]) / ".minimax" / "providers.json"
added = json.loads(kept.read_text()) if kept.exists() else {}
if argv[:1] == ["provider"]:
    note(" ".join(argv))
    if argv[1] == "remove":
        if added.pop(argv[2].removeprefix("custom_provider:"), None) is None:
            raise SystemExit(1)
    else:
        added[flags["--name"]] = {"base": flags["--base-url"], "model": flags["--model"],
                                  "format": flags["--api-format"],
                                  "key": os.environ[flags["--api-key-env"]]}
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(json.dumps(added))
    raise SystemExit(0)

prompt = sys.stdin.read()
note(prompt)
named, _, model = flags["--model"].removeprefix("custom_provider:").partition("/")
provider = added[named]
assert provider["model"] == model, model
request = urllib.request.Request(
    provider["base"] + "/chat/completions",
    data=json.dumps({"model": model, "stream": True,
                     "messages": [{"role": "user", "content": prompt}]}).encode(),
    headers={"Authorization": "Bearer " + provider["key"],
             "Content-Type": "application/json"})
with urllib.request.urlopen(request, timeout=60) as answer:
    chunks = [json.loads(one[5:]) for one in answer.read().decode().splitlines()
              if one.startswith("data:") and one[5:].strip() != "[DONE]"]
body = "".join(one["choices"][0]["delta"].get("content") or ""
               for one in chunks if one.get("choices"))
session = flags.get("--session", "mvs_stand_in")
out({"type": "exec.started", "sessionId": session})
out({"type": "item.completed", "sessionId": session,
     "item": {"type": "agent_message", "content": body}})
out({"type": "turn.completed", "sessionId": session, "usage": {"outputTokens": 7},
     "model": {"providerId": "custom_provider:" + named, "modelId": model}})
out({"type": "exec.completed", "sessionId": session, "result": {"status": "succeeded"}})
"""


def _unswapped(self: Provider) -> tuple[tuple[str, str], ...]:
    """No credential path answered by another, which is the supervisor's to test."""
    del self
    return ()


@pytest.fixture
def endpoint() -> Iterator[Endpoint]:
    # Driven to its end after the test, which is what shuts it.
    yield from serving()


@pytest.mark.skipif(not gatewayable(), reason="the [litellm] extra is not installed")
@pytest.mark.timeout(240)
def test_mcode_under_an_account_a_gateway_holds_runs_the_model_through_it(
    endpoint: Endpoint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = standins(tmp_path, monkeypatch, "LITELLM_GATEWAY_KEY", "MINIMAX_DATA_DIR")
    held.install("mcode", ROUTED)
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "hmz"))
    monkeypatch.setenv("LITELLM_GATEWAY_KEY", "lying-about")
    # A credential path answered by another is the supervisor's, tested where it is written.
    monkeypatch.setattr(Provider, "swaps", _unswapped)
    providers.add(
        "mcode",
        "gw",
        way="litellm-openai-gateway",
        env={
            "LITELLM_GATEWAY_URL": endpoint.url,
            "LITELLM_GATEWAY_KEY": "upstream-secret",
            "LITELLM_GATEWAY_API": "openai",
        },
    )
    agent = MiniMaxCodeAgent(
        MiniMaxCodeAgentConfig(model="stand-in", effort="", provider="gw")
    )
    try:
        session = agent.new(tmp_path)
        said = [session("say hi"), session("say more")]
        through = agent.gateway
        assert through is not None
    finally:
        agent.stop()

    assert said == ["say hi", "say more"]
    assert [one["model"] for one in endpoint.asked] == ["stand-in", "stand-in"]
    added, turn, again, _ = held.calls("mcode")
    named = added.flag("--name") or ""
    assert named.startswith(f"hmz-{through.port}-")
    assert added.stdin == (
        f"provider add --name {named} --base-url {through.url} --api-format "
        "openai-completions --model stand-in --api-key-env MCODE_PROVIDER_API_KEY"
    )
    # Added once a turn, into the copy of `config.yaml` in the virtual home that turn starts
    # in -- never the account's own -- and so with nothing to take out afterwards.
    assert again.stdin == added.stdin
    home = added.env["MINIMAX_DATA_DIR"]
    assert home == turn.env["MINIMAX_DATA_DIR"]
    assert home != again.env["MINIMAX_DATA_DIR"]
    assert home is not None
    assert not Path(home).exists()
    assert turn.flag("--model") == f"custom_provider:{named}/stand-in"
    assert turn.env["LITELLM_GATEWAY_KEY"] is None
    assert not through.running
