"""The regression matrix: every feature humanize offers, driven through every CLI it drives.

Each function below is one row -- a feature, as a person or a program reaches it -- and runs
once per CLI in `hmz.coganchor.backends.PROFILES`, as `test_<feature>[<cli>]`. What each row
drives is a real surface on a real CLI: `hmz exec` as a process of its own, read through
`--json`, or `hmz.sdk.Hmz` running a flow a few lines long that the row writes out for itself.
What a run left behind is read back through the SDK's `epics` and nothing else.

`tests/matrix/cells.py` says how a cell ends -- passed, unsupported, environment, failed -- and
`docs/contributing/regression-matrix.md` how to run it, what it costs and how to add a row. A
run with `--run-agents` draws the grid at its foot.

Every prompt is a word or two, every model the cheapest its CLI takes, every run capped.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import fcntl
import json
import os
import queue
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import (
    AskUserHookAgentMixin,
    FlowCancelled,
    GoalCommandAgentMixin,
    PermissionRequestHookAgentMixin,
    SteeringAgentMixin,
    SubagentStartHookAgentMixin,
)
from tests.matrix.cells import (
    _BUDGETED,
    Unsettled,
    feature,
    forks,
    mixin,
    mounts,
    read_only,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from hmz.coganchor.agents import AgentBase, SessionBase
    from hmz.coganchor.agents.event import Event
    from hmz.daemon import Daemon
    from hmz.runtime.epic import Session
    from tests.flows.sshd import Box, Docked
    from tests.matrix.cells import Cell, Exec

#: A turn that goes on long enough to be steered, interrupted or stopped while it runs.
#:
#: A command that takes its time rather than an answer that does: how long a model takes to
#: count to four hundred is the model's speed, and the cheapest of these write it out in four
#: seconds -- over before anything could be done to it. Two minutes of waiting is two minutes
#: on every CLI, and costs a handful of tokens rather than a thousand. Not `sleep` itself:
#: Qwen Code's shell tool refuses a bare `sleep` as a stall, and a model told to annotate it
#: does not always.
SLOW = (
    "Use your shell tool to run exactly this command in the foreground, and wait for it to "
    "finish -- it takes two minutes, which is intended: "
    "python3 -c 'import time; time.sleep(120)' -- then reply with exactly one word: SLEPT"
)

#: How long a slow turn is given to be under way before anything is done to it: long enough
#: for the slowest CLI here to have started and reached for its shell.
SETTLE = 15.0


#: What pi does after a turn is cut off mid-command, seen by driving `session.cut` and then a
#: second turn on the driver itself: the second turn's own reasoning is about the second
#: prompt, and what it answers is the first prompt's reply. Not yet told apart as the driver's
#: or the model's (pi@nvidia's minimax-m3); some runs it does not happen.
_PI_CUT = (
    "after a turn is cut off mid-command, pi's next turn answers with the cut turn's"
    " reply ('SLEPT') instead of its own; reproduced on the driver with `session.cut`"
)


def _word() -> str:
    """A word no model would say unless it was told to, for telling an answer from a guess."""
    return f"KIWI{secrets.randbelow(9000) + 1000}"


def _says(said: object, word: str) -> bool:
    return word.lower() in str(said).lower()


#: One turn of one agent, in the workspace: all that most rows need of a flow.
ONE = '''"""One turn of one agent, in the workspace."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def one(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["workspace"])
    return await worker.run(task, session=session)
'''


def _one(cell: Cell) -> Path:
    return cell.flow("one", ONE)


# ---------------------------------------------------------------------------- one turn


@feature()
def test_plain_turn(cell: Cell) -> None:
    """One turn of `chat` through `hmz exec --json`: the answer, in a stream a program reads."""
    word = _word()

    ran = cell.exec(
        "chat",
        f"Reply with exactly one word, {word}, and nothing else.",
        agents=[cell.agent("assistant")],
        budget="",
    )

    assert _says(ran.answer, word), ran
    assert ran.said("result"), f"no turn ended in a result\n{ran}"
    assert len({frozenset(one) for one in ran.events}) == 1, (
        f"--json wrote objects with different keys\n{ran}"
    )
    assert {one["cli"] for one in ran.events} == {cell.cli}, ran
    assert {one["agent"] for one in ran.events} == {"assistant"}, ran
    (epic,) = cell.hmz.epics.all()
    ran_ = cell.hmz.epics.read(epic)
    assert ran_ is not None
    assert ran_.how == "done", ran_


SHAPED = '''"""One turn, answered in a shape."""

import pydantic

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Tally(pydantic.BaseModel):
    total: int
    colours: list[str]


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def shaped(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["workspace"])
    said = await worker.run(task, session=session, output_schema=Tally)
    return said.model_dump()
'''


@feature()
def test_schema(cell: Cell) -> None:
    """A turn asked for an `output_schema` answers with an instance of it."""
    got = cell.run(
        cell.flow("shaped", SHAPED),
        "What is 17 plus 25? Set total to that number, and set colours to the two words "
        "red and blue, in that order.",
    )

    assert got["total"] == 42, got
    assert [str(one).strip().lower() for one in got["colours"]] == ["red", "blue"], got


@feature()
def test_tool_use(cell: Cell) -> None:
    """The agent runs a shell command, and what the command wrote is on disk.

    Taken once more where the stream shows the agent reached for no tool at all: the
    cheapest models sometimes answer the word they were told to end on and do nothing else,
    which is the model's. Twice is not, and neither is a tool reached for that wrote nothing:
    a CLI humanize stopped handing its tools would look exactly like that.
    """
    word = _word()
    asked = (
        "Use your shell tool to run exactly this command in your working directory: "
        f"printf %s {word} > tool.txt -- then reply with exactly one word: DONE"
    )

    ran = cell.exec(_one(cell), asked)
    if not ran.said("tool"):
        ran = cell.exec(_one(cell), asked)

    landed = cell.workspace / "tool.txt"
    assert landed.is_file(), f"the turn left no tool.txt behind\n{ran}"
    assert landed.read_text().strip() == word
    assert ran.said("tool"), f"the stream shows no tool being run\n{ran}"


HOOKED = '''"""One turn, with a hook on each moment every harness reaches."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowParams,
    LocalEnv,
    PreToolUseHookResult,
    StopHookResult,
    UserPromptSubmitHookResult,
    flow,
)


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def hooked(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    heard = {"prompt": [], "tool": [], "stop": []}

    async def prompted(params):
        heard["prompt"].append(params.prompt)
        return UserPromptSubmitHookResult()

    async def reached(params):
        heard["tool"].append(params.tool)
        return PreToolUseHookResult()

    async def stopping(params):
        heard["stop"].append(params.said)
        return StopHookResult()

    worker.on_user_prompt_submit(prompted)
    worker.on_pre_tool_use(reached)
    worker.on_stop(stopping)
    session = await worker.spawn(env=envs["workspace"])
    said = await worker.run(task, session=session)
    return {"heard": heard, "said": said}
'''


@feature()
def test_hooks(cell: Cell) -> None:
    """The flow's hooks hear the prompt go out, a tool reached for, and the turn end.

    The answer is a word only a tool can read, so a turn that answered it reached for one:
    an `echo` a model can answer without running it, and some do.
    """
    word = _word()
    (cell.workspace / "hook.txt").write_text(f"{word}\n")

    got = cell.run(
        cell.flow("hooked", HOOKED),
        f"Use your shell tool to run exactly: cat {cell.workspace}/hook.txt -- then reply "
        "with exactly what it printed.",
    )

    heard = cast("dict[str, list[str]]", got["heard"])
    assert _says(got["said"], word), f"the turn never read the file: {got}"
    assert any("hook.txt" in prompt for prompt in heard["prompt"]), heard
    assert heard["tool"], f"no PRE_TOOL_USE was heard: {got}"
    assert heard["stop"], f"no STOP was heard: {got}"


# ------------------------------------------------------------ a turn while it is running


STEERED = '''"""A slow turn, and a word put into it while it runs."""

import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowParams,
    LocalEnv,
    SteeringAgentMixin,
    flow,
)


class Steered(Agent, SteeringAgentMixin): ...


class Agents(AgentCollection):
    worker: Steered


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def steered(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["workspace"])
    turn = asyncio.create_task(worker.run(task, session=session))
    await asyncio.sleep(SETTLE)
    if turn.done():
        return {"early": True, "said": turn.result()}
    await worker.steer(
        "Stop counting now. Reply with exactly one word: STEERED",
        session=session,
        queued=False,
    )
    return {"early": False, "said": await turn}
'''


@feature(mixin(SteeringAgentMixin), xfail={"pi": Unsettled(_PI_CUT)})
def test_steer(cell: Cell) -> None:
    """A word put into a turn that is running is what the turn goes on from."""
    got = cell.run(cell.flow("steered", STEERED.replace("SETTLE", str(SETTLE))), SLOW)

    assert not got["early"], f"the slow turn was over within {SETTLE}s: {got}"
    assert _says(got["said"], "STEERED"), got


INTERRUPTED = '''"""A slow turn cancelled by the flow, and the session going on after it."""

import asyncio
import time

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def interrupted(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["workspace"])
    turn = asyncio.create_task(worker.run(task, session=session))
    await asyncio.sleep(SETTLE)
    early = turn.done() and repr(turn.result())
    began = time.monotonic()
    turn.cancel()
    try:
        await turn
    except asyncio.CancelledError:
        pass
    took = time.monotonic() - began
    after = await worker.run("Reply with exactly one word: AFTER", session=session)
    return {"early": early, "took": took, "after": after}
'''


@feature(
    xfail={
        "dsh": Unsettled(
            "a race, two runs in three: the turn after one the flow cancelled fails -- the"
            " cancelled call, still unwinding, puts down the session's runtime and removes"
            " the cordis.yml the next turn's runtime was started from ('usage:"
            " dsh-jsonrpc-agent <path/to/cordis.yml>')"
        ),
        "pi": Unsettled(_PI_CUT),
    }
)
def test_interrupt(cell: Cell) -> None:
    """A turn the flow cancels stops at once, and its session takes the next turn."""
    got = cell.run(
        cell.flow("interrupted", INTERRUPTED.replace("SETTLE", str(SETTLE))), SLOW
    )

    assert not got["early"], f"the slow turn was over within {SETTLE}s: {got}"
    assert got["took"] < 60, f"the cancelled turn took {got['took']:.0f}s to stop"
    assert _says(got["after"], "AFTER"), got


@feature(
    xfail={
        "kimi": "a stopped run whose kimi turn is in a shell command ends only when the"
        " command does: the cut is said at once and the turn is cut off about 95s later",
    }
)
def test_stop(cell: Cell) -> None:
    """A run stopped from outside, as `/stop` and ctrl-c stop one, ends and says so."""
    running = cell.start(_one(cell), SLOW)
    opened = threading.Event()

    def told(role: str, agent: AgentBase, session: SessionBase) -> None:
        del role, agent, session
        opened.set()

    running.opened(told)
    running.start()
    try:
        assert opened.wait(300), "the run opened no session"
        time.sleep(SETTLE)
        if not running.running:
            with cell.environmental():
                if running.raised is not None:
                    raise running.raised
            pytest.fail(f"the slow turn was over within {SETTLE}s: {running.result!r}")
        began = time.monotonic()
        running.stop()
        assert running.wait(120), "the run was still going two minutes after a stop"
        took = time.monotonic() - began
    finally:
        running.close()

    assert took < 60, f"a stopped run took {took:.0f}s to end"
    assert running.raised is None or isinstance(
        running.raised, asyncio.CancelledError | FlowCancelled
    ), repr(running.raised)
    assert running.epic is not None
    ran = cell.hmz.epics.read(running.epic)
    assert ran is not None
    assert ran.how == "stopped", (
        f"a run stopped {took:.1f}s ago reads {ran.how!r}: it raised {running.raised!r}"
        f" and returned {running.result!r}"
    )


# -------------------------------------------------------------- sessions, and runs again


FORKED = '''"""A conversation, and a second one carried on from it."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def forked(task, *, agents, envs, params, ctx):
    worker, here = agents["worker"], envs["workspace"]
    parent = await worker.spawn(env=here)
    await worker.run(
        f"Remember this code word: {task}. Reply with exactly one word: OK",
        session=parent,
    )
    child = await worker.fork(parent, env=here)
    return await worker.run(
        "What is the code word I asked you to remember? Reply with the code word alone.",
        session=child,
    )
'''


@feature(forks)
def test_fork(cell: Cell) -> None:
    """A forked session carries on from what its parent was told, and the run says whose."""
    word = _word()

    said = cell.run(cell.flow("forked", FORKED), word)

    assert _says(said, word), said
    (epic,) = cell.hmz.epics.all()
    parent, child = cell.hmz.epics.sessions(epic)
    assert child.parent == parent.ident, (parent, child)


RESUMED = '''"""Two turns, and a plug that may be pulled between them."""

import json
import pathlib

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    worker: Agent


class Workspace(LocalEnv, FilesEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def resumed(task, *, agents, envs, params, ctx):
    worker, here = agents["worker"], envs["workspace"]
    session = await worker.spawn(env=here)
    state = ctx.state
    if "first" not in state:
        state["first"] = await worker.run(
            "Reply with exactly one word: FIRST", session=session
        )
        plug = pathlib.Path(str(here.workdir)) / "plug"
        if plug.exists():
            plug.unlink()
            raise RuntimeError("the plug was pulled")
    second = await worker.run("Reply with exactly one word: SECOND", session=session)
    kept = {"first": state["first"], "second": second, "resumed": ctx.resumed}
    await here.write("resumed.json", json.dumps(kept).encode())
    return second
'''


@feature()
def test_resume(cell: Cell) -> None:
    """`hmz exec --resume` picks a run that died up where its flow stood, not from the top."""
    flow = cell.flow("resumed", RESUMED)
    (cell.workspace / "plug").touch()

    died = cell.exec(flow, "go", check=False)
    again = cell.exec(flow, "go", resume=True)

    assert died.status != 0, died
    assert "the plug was pulled" in died.err, died
    kept = json.loads((cell.workspace / "resumed.json").read_text())
    assert kept["resumed"] is True, kept
    assert _says(kept["first"], "FIRST"), kept
    assert _says(kept["second"], "SECOND"), kept
    assert len(again.said("result")) == 1, f"the first turn was taken again\n{again}"
    before, after = cell.hmz.epics.all()
    picked = cell.hmz.epics.read(after)
    assert picked is not None
    assert picked.picked_up == before.name, picked


# -------------------------------------------------------- what an agent is, and may do


SKILLED = '''"""One turn of an agent the flow gives a skill of its own."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Keeper(Agent):
    _skills = ("matrix-secret",)


class Agents(AgentCollection):
    worker: Keeper


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def skilled(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["workspace"])
    return await worker.run(task, session=session)
'''

SECRET = """---
name: matrix-secret
description: Knows this project's secret password. Use it whenever you are asked for the
  secret password.
---

The secret password of this project is {word}. When you are asked for the secret password,
reply with it alone.
"""


@feature(mounts)
def test_skills(cell: Cell) -> None:
    """A skill the flow brings is one its agent has, and uses."""
    word = _word()
    flow = cell.flow("skilled", SKILLED, {"matrix-secret": SECRET.format(word=word)})

    said = cell.run(
        flow,
        "What is this project's secret password? Use your matrix-secret skill to find "
        "out, and reply with the password alone.",
    )

    assert _says(said, word), said


GUARDED = '''"""The same errand, asked of an agent that may only read and one that may write."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowParams,
    LocalEnv,
    Permission,
    PermissionKind,
    flow,
)


class Reader(Agent):
    _permission = Permission(
        local=PermissionKind.READ,
        user=PermissionKind.READ,
        system=PermissionKind.READ,
    )


class Agents(AgentCollection):
    reader: Reader
    writer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def guarded(task, *, agents, envs, params, ctx):
    said = {}
    for role in ("reader", "writer"):
        agent = agents[role]
        session = await agent.spawn(env=envs["workspace"])
        said[role] = await agent.run(task.replace("ROLE", role), session=session)
    return said
'''


@feature(
    read_only,
    xfail={
        "agy": "READ is not enforced on agy: humanize holds an agent to READ with agy's"
        " `--mode plan`, and agy 1.2 in plan mode writes the file it is asked to"
        " (reproduced with `agy --mode plan --print=...` outside humanize)",
    },
)
def test_permissions(cell: Cell) -> None:
    """An agent held to READ cannot write its workspace; one allowed ALL can.

    The file is named by its whole path: not every CLI tells its model where it is working,
    and one that guesses writes somewhere else entirely.
    """
    spec = cell.place.spec()

    said = cell.run(
        cell.flow("guarded", GUARDED),
        f"Create the file {cell.workspace}/ROLE.txt whose only content is the word ROLE, "
        "with whatever tool you have for writing files or running commands. If you are "
        "not allowed to, reply with exactly one word: REFUSED",
        agents={"reader": spec, "writer": spec},
    )

    wrote = cell.workspace / "writer.txt"
    assert wrote.is_file(), f"an agent allowed ALL wrote nothing: {said}"
    assert wrote.read_text().strip() == "writer"
    assert not (cell.workspace / "reader.txt").exists(), (
        f"an agent held to READ wrote its workspace: {said}"
    )


ASKED = '''"""One turn, with every tool it asks to run refused by the flow."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowParams,
    LocalEnv,
    PermissionRequestHookAgentMixin,
    PermissionRequestHookResult,
    flow,
)


class Asked(Agent, PermissionRequestHookAgentMixin): ...


class Agents(AgentCollection):
    worker: Asked


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def asked(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    heard = []

    async def refused(params):
        heard.append(params.tool)
        return PermissionRequestHookResult(allow=False, reason="not in this test")

    worker.on_permission_request(refused)
    session = await worker.spawn(env=envs["workspace"])
    said = await worker.run(task, session=session)
    return {"heard": heard, "said": said}
'''


@feature(mixin(PermissionRequestHookAgentMixin))
def test_permission_hook(cell: Cell) -> None:
    """A tool the flow's permission hook refuses does not run, over bypassed approvals.

    The command removes a directory outside the workspace, which every CLI here asks about:
    some ask only about what they rate dangerous -- Kimi Code at its asking rung stops for a
    command its parser rates so -- and a file written in the project is not that.
    """
    kept = cell.root / "outside" / "kept"
    kept.mkdir(parents=True)
    (kept / "kept.txt").write_text("kept\n")

    got = cell.run(
        cell.flow("asked", ASKED),
        f"Use your shell tool to run exactly: rm -rf {kept} -- and if you are not "
        "allowed to, reply with exactly one word: REFUSED",
    )

    assert got["heard"], f"the hook was never asked: {got}"
    assert (kept / "kept.txt").is_file(), (
        f"the tool ran although the hook refused it: {got}"
    )


DELEGATED = '''"""One turn, and a hook on the subagents it starts."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowParams,
    LocalEnv,
    SubagentStartHookAgentMixin,
    SubagentStartHookResult,
    flow,
)


class Delegator(Agent, SubagentStartHookAgentMixin): ...


class Agents(AgentCollection):
    worker: Delegator


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def delegated(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    started = []

    async def heard(params):
        started.append(params.subagent)
        return SubagentStartHookResult()

    worker.on_subagent_start(heard)
    session = await worker.spawn(env=envs["workspace"])
    said = await worker.run(task, session=session)
    return {"started": started, "said": said}
'''


@feature(mixin(SubagentStartHookAgentMixin))
def test_subagents(cell: Cell) -> None:
    """Work the agent hands to a subagent of its own is heard starting, and comes back."""
    word = _word()

    got = cell.run(
        cell.flow("delegated", DELEGATED),
        "Delegate this to a subagent, with your tool for starting subagents, and do not "
        f"answer it yourself: the subagent must reply with exactly the word {word}. When "
        "it is done, reply with what it said.",
    )

    assert got["started"], f"no subagent was heard starting: {got}"
    assert _says(got["said"], word), got


GOALED = '''"""One turn, handed to the harness's own `/goal`."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    flow,
)


class Goaler(Agent, GoalCommandAgentMixin): ...


class Agents(AgentCollection):
    worker: Goaler


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def goaled(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["workspace"])
    return await worker.run(f"/goal {task}", session=session)
'''


@feature(mixin(GoalCommandAgentMixin))
def test_goal(cell: Cell) -> None:
    """`/goal` is the harness's own: it keeps going until the objective is met."""
    done = cell.workspace / "DONE.txt"

    said = cell.run(
        cell.flow("goaled", GOALED),
        f"Create the file {done} whose only content is: done",
    )

    assert done.is_file(), f"the goal was never met; the turn answered {said!r}"
    assert done.read_text().strip() == "done"


def _pi_asks() -> bool:
    """Whether pi has an extension here that could stop a turn to ask anything.

    pi has no question of its own to ask: an extension is what asks, and pi without one
    tells its agent it has no such tool.
    """
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi" / "agent")
    if any((agent / "extensions").glob("*")):
        return True
    said = subprocess.run(
        ["pi", "list"], capture_output=True, text=True, timeout=120, check=False
    )
    return said.returncode == 0 and "No packages installed" not in said.stdout


@feature(mixin(AskUserHookAgentMixin))
def test_ask_user(cell: Cell) -> None:
    """A question the agent stops to ask reaches the run's outworlder, and the answer returns.

    `chat` is the flow: it puts every question its agent asks to the person it is talking
    to, which here is the SDK's own scripted outworlder.
    """
    from hmz.sdk import fakes

    if cell.cli == "pi" and not _pi_asks():
        pytest.skip(
            "environment: pi stops a turn to ask only through an extension, and none is"
            " installed here (`pi list`, ~/.pi/agent/extensions)"
        )
    asks: list[str] = []

    def listening(agent: AgentBase, session: SessionBase | None, event: Event) -> None:
        del agent, session
        if event.kind == "asks":
            asks.append(event.text)

    answered: list[str] = []

    def answering(prompt: str, output_schema: object = None) -> str:
        del output_schema
        answered.append(prompt)
        # The question is answered, and whatever the agent says after it is the end of
        # the conversation.
        return "blue" if len(answered) == 1 else ""

    person = fakes.FakeOutworlder(answering)

    cell.run(
        "chat",
        "Use your tool for asking the user a question to ask me which colour I prefer, "
        "offering exactly the options red and blue. Then reply with just the colour I "
        "picked, one word.",
        agents={"assistant": cell.place.spec()},
        outworlder=person,
        watch=listening,
    )

    assert asks, f"the agent asked nothing through its tool; it was told {answered}"
    assert _says(answered[0], "red"), answered
    assert _says(answered[-1], "blue"), answered


# ---------------------------------------------------------------- what a run may spend


LOOPED = '''"""The same turn, round after round, until the rounds or the budget run out."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = 3


@flow(agents=Agents, envs=Envs, params=Params)
async def looped(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    session = await worker.spawn(env=envs["workspace"])
    return [await worker.run(task, session=session) for _ in range(params.rounds)]
'''


@feature()
def test_budget(cell: Cell) -> None:
    """An output-token cap stops a run cleanly, after the turn that spent it and before the next."""
    ran = cell.exec(
        cell.flow("looped", LOOPED),
        "Reply with exactly one word: AGAIN",
        budget="output_tokens=1",
    )

    assert "hmz exec: stopped --" in ran.err, f"the cap never stopped the run\n{ran}"
    assert "output tokens are spent" in ran.err, ran
    assert len(ran.said("result")) == 1, f"a turn began after the cap was spent\n{ran}"
    (epic,) = cell.hmz.epics.all()
    ran_ = cell.hmz.epics.read(epic)
    assert ran_ is not None
    assert ran_.how == "stopped", ran_


# ------------------------------------------------------------- which account, which place


@feature()
def test_named_account(cell: Cell) -> None:
    """A turn under an account made through the SDK lands, and the run says it was that one."""
    word = _word()
    with cell.named() as place:
        ran = cell.exec(
            _one(cell),
            f"Reply with exactly one word, {word}, and nothing else.",
            agents=[cell.agent(place=place)],
        )
        made = [one.name for one in cell.hmz.accounts.all(cell.cli)]

    assert "matrix" in made, made
    assert _says(ran.answer, word), ran
    (epic,) = cell.hmz.epics.all()
    (session,) = cell.hmz.epics.sessions(epic)
    assert session.provider == "matrix", session
    ran_ = cell.hmz.epics.read(epic)
    assert ran_ is not None
    assert [one.provider for one in ran_.agents] == ["matrix"], ran_


@feature()
def test_fallback(cell: Cell) -> None:
    """A place that cannot take a turn at all hands it to the place written after it.

    The place that fails is a CLI of this machine's own that will not start -- one of the
    failures the fallbacks are for, and the one every column can be handed the same way. A
    model nobody serves is not: Claude Code runs an id it has never heard of on its default
    model rather than refusing it, so there is no failing to fall back from.
    """
    from hmz.coganchor import backends

    word = _word()
    broken = cell.root / "bin" / "hmz-matrix-broken"
    broken.parent.mkdir()
    broken.write_text("#!/bin/sh\necho 'this CLI will not start' >&2\nexit 3\n")
    broken.chmod(0o755)
    added = backends.remember("", [str(broken)])
    fallbacks, place = cell.hmz.fallbacks, cell.place
    good = fallbacks.spec(cell.cli, place.model, place.provider)
    fallbacks.points(fallbacks.spec(added, "m"), good)

    ran = cell.exec(
        _one(cell),
        f"Reply with exactly one word, {word}, and nothing else.",
        agents=[f"worker={added}/m:{backends.written(place.effort)}"],
    )

    assert _says(ran.answer, word), ran
    assert any(f"carrying on as {good}" in one for one in ran.said("notice")), (
        f"nothing said the turn moved to {good}\n{ran}"
    )


# ------------------------------------------------------------ what a run leaves behind


def _ran(cell: Cell) -> tuple[Path, Session]:
    """One run of one turn through `hmz exec`, and the session it opened, read back."""
    word = _word()
    cell.exec(_one(cell), f"Reply with exactly one word, {word}, and nothing else.")
    epics = cell.hmz.epics
    (epic,) = epics.all()
    ran = epics.read(epic)
    assert ran is not None
    assert ran.how == "done", ran
    assert [one.backend for one in ran.agents] == [cell.cli], ran
    (session,) = epics.sessions(epic)
    assert (session.agent, session.backend) == ("worker", cell.cli), session
    assert session.ident, session
    return epic, session


@feature()
def test_epic_export(cell: Cell) -> None:
    """A run is written down, and exported with its session's own log -- or why there is none.

    Some CLIs keep no log file of a conversation to copy; for those the manifest says why,
    which is the export's own promise (`docs/user/export.md`).
    """
    from hmz.coganchor import backends

    epic, session = _ran(cell)

    bundle, manifest = cell.hmz.epics.bundled(epic, output=cell.root / "bundle.tar.gz")
    (entry,) = [
        one
        for one in cast("list[dict[str, Any]]", manifest["sessions"])
        if one["session"] == session.ident
    ]
    with tarfile.open(bundle) as held:
        carried = [one.name for one in held.getmembers() if one.isfile() and one.size]
    profile = backends.named(cell.cli)
    if profile is not None and profile.logs:
        assert entry["logs"], f"the session's log was left out: {entry}"
        missing = [
            log
            for log in cast("list[str]", entry["logs"])
            if not any(name.endswith(f"/{log}") for name in carried)
        ]
        assert not missing, f"the manifest names logs the bundle lacks: {missing}"
    else:
        assert entry.get("because"), f"nothing says why no log went in: {entry}"


@feature(
    limits={
        "cursor-agent": "it keeps no log a trace can read (docs/reference/tracing.md)"
    }
)
def test_trace(cell: Cell) -> None:
    """A run's trace reads its session back out of the CLI's own log."""
    epic, session = _ran(cell)

    _, trace = cell.hmz.epics.traced(epic, output=cell.root / "trace.json")

    spans = [
        one
        for one in cast("list[dict[str, Any]]", trace["traceEvents"])
        if one.get("ph") == "X"
        and session.ident
        in str(cast("dict[str, Any]", one.get("args") or {}).get("session"))
    ]
    assert spans, f"the trace read nothing of session {session.ident} back"


# ------------------------------------------------------------------ another machine


REMOTE = '''"""One turn of an agent whose work is on another machine, read back from there."""

from hmz.flows import (
    Agent,
    AgentCollection,
    Env,
    EnvCollection,
    FilesEnvMixin,
    FlowParams,
    LocalEnv,
    ShellEnvMixin,
    flow,
)


class Box(Env, ShellEnvMixin): ...


class Workspace(LocalEnv, FilesEnvMixin): ...


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    box: Box
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def remote(task, *, agents, envs, params, ctx):
    worker, box = agents["worker"], envs["box"]
    session = await worker.spawn(env=box)
    said = await worker.run(task, session=session)
    status, out, err = await box.exec(["cat", "landed.txt"])
    await envs["workspace"].write("seen.txt", out.encode())
    return said
'''


@feature(
    timeout=900,
    xfail={
        # The docker-envs change fixed the launcher as it fixed codex's, dsh's, mimo's and
        # zcode's, which pass here now; cursor-agent is signed out on the machine this was
        # last run on, so its cell has not been seen to pass.
        "cursor-agent": Unsettled(
            "anchored turn bug: cursor-agent's launcher ran `realpath` on the target and"
            " exited 127; fixed by the docker-envs PR (U8), not yet seen to pass"
        ),
    },
)
def test_ssh_env(cell: Cell, ssh_box: Box) -> None:
    """An agent given an environment on another machine over ssh reads and writes there.

    The machine is a container with an sshd in it: a host of its own, whose directory is not
    this machine's. What the agent is asked to copy exists only there, and where the copy has
    to turn up is there too.
    """
    word = _word()
    there = cell.root / "box"
    ssh_box.run(f"mkdir -p {there} && printf %s {word} > {there}/marker.txt")

    ran = cell.exec(
        cell.flow("remote", REMOTE),
        "Use your shell tool to run exactly this command in your working directory: "
        "cp marker.txt landed.txt -- then reply with exactly one word: DONE",
        envs=[f"box=ssh@{ssh_box.alias}{there}"],
        timeout=600,
    )

    landed = ssh_box.run(f"cat {there}/landed.txt 2>/dev/null || true")
    assert landed.strip() == word, f"the host holds {landed!r} in landed.txt\n{ran}"
    seen = (cell.workspace / "seen.txt").read_text()
    assert seen.strip() == word, f"the flow read {seen!r} back from the host\n{ran}"


@feature(timeout=900)
def test_ssh_provider(
    cell: Cell, ssh_box: Box, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A saved ssh host, imported from an ssh config, is where `-e box=ssh@<name>` works.

    Imported from the config the box is named in, and given a workdir -- then named alone,
    with nothing after it: the workdir is the provider's. And the `ssh` that knows the box is
    taken off `PATH` first, so that the only thing that can reach it is what was saved.
    """
    word = _word()
    there = cell.root / "box"
    ssh_box.run(f"mkdir -p {there} && printf %s {word} > {there}/marker.txt")
    envs = cell.hmz.environments
    (imported,) = envs.import_ssh(config=ssh_box.config, names=[ssh_box.alias])
    envs.write(dataclasses.replace(imported, workdir=str(there)))
    ssh_box.unlisted(monkeypatch)

    ran = cell.exec(
        cell.flow("remote", REMOTE),
        "Use your shell tool to run exactly this command in your working directory: "
        "cp marker.txt landed.txt -- then reply with exactly one word: DONE",
        envs=[f"box=ssh@{imported.name}"],
        timeout=600,
    )

    landed = ssh_box.run(f"cat {there}/landed.txt 2>/dev/null || true")
    assert landed.strip() == word, f"the host holds {landed!r} in landed.txt\n{ran}"
    seen = (cell.workspace / "seen.txt").read_text()
    assert seen.strip() == word, f"the flow read {seen!r} back from the host\n{ran}"


BOXED = '''"""One turn of an agent in a container of its own, and what the container says of it."""

import json

from hmz.flows import (
    Agent,
    AgentCollection,
    Env,
    EnvCollection,
    FilesEnvMixin,
    FlowParams,
    ImageEnvMixin,
    LocalEnv,
    ShellEnvMixin,
    flow,
)


class Box(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"


class Workspace(LocalEnv, FilesEnvMixin): ...


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    box: Box
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def boxed(task, *, agents, envs, params, ctx):
    worker, box = agents["worker"], envs["box"]
    _, name, _ = await box.exec(["hostname"])
    _, sshd, _ = await box.exec(["sh", "-c", "command -v sshd || echo none"])
    session = await worker.spawn(env=box)
    said = await worker.run(task, session=session)
    seen = {"hostname": name.strip(), "sshd": sshd.strip()}
    for one in ("proof.txt", "dockerenv.txt", "os-release.txt", "gpus.txt"):
        status, out, _ = await box.exec(["cat", one])
        seen[one] = out.strip() if status == 0 else None
    await envs["workspace"].write("seen.json", json.dumps(seen).encode())
    return said
'''

#: What the agent in a container is asked to do there: three things only a container answers.
CONTAINED = (
    "Use your shell tool to run exactly this one command in your working directory, then "
    "reply with exactly one word, DONE: hostname > proof.txt; test -f /.dockerenv && echo "
    "inside > dockerenv.txt; cat /etc/os-release > os-release.txt"
)


def _contained(cell: Cell, ran: Exec) -> dict[str, Any]:
    """What the flow read back out of the container, checked to be the container's own."""
    seen = cast(
        "dict[str, Any]", json.loads((cell.workspace / "seen.json").read_text())
    )
    assert seen["sshd"] == "none", (
        f"the image has an sshd, which proves nothing: {seen}"
    )
    assert seen["proof.txt"] == seen["hostname"], (
        f"the agent's hostname is not the container's: {seen}\n{ran}"
    )
    assert seen["hostname"] != os.uname().nodename, seen
    assert seen["dockerenv.txt"] == "inside", f"no /.dockerenv where it ran: {seen}"
    assert "Debian" in str(seen["os-release.txt"]), seen
    return seen


@feature(timeout=900)
def test_docker_env(cell: Cell, daemon: None) -> None:
    """An agent given a container of an image with no sshd works inside it.

    `-e box=docker@local/<dir>`: docker's default here, no provider saved. The command runs in
    the container, and says so three ways only a container can: its hostname, `/.dockerenv`,
    and the image's Debian rather than this machine's Ubuntu.
    """
    del daemon
    there = cell.root / "box"
    there.mkdir()

    ran = cell.exec(
        cell.flow("boxed", BOXED),
        CONTAINED,
        envs=[f"box=docker@local{there}"],
        timeout=600,
    )

    seen = _contained(cell, ran)
    assert (there / "proof.txt").read_text().strip() == seen["hostname"], (
        "the workdir is mounted where it is, and the proof is not in it"
    )


@feature(timeout=900)
def test_docker_env_remote(cell: Cell, docker_box: Docked) -> None:
    """An agent's container on a daemon elsewhere, reached through a saved ssh host.

    A docker provider whose endpoint is `ssh:<saved ssh host>`, and a daemon that is really
    somewhere else: docker's own daemon in a container of this machine's, so its directories
    are not this machine's -- the workdir exists only there, and the proof lands only there.
    """
    there = f"/work/{cell.cli}-{secrets.token_hex(4)}"
    docker_box.run(f"mkdir -p {there}")
    envs = cell.hmz.environments
    envs.add(envs.new("ssh", "farhost", **docker_box.ssh()))
    envs.add(envs.new("docker", "far", endpoint="ssh:farhost", workdir=there))

    ran = cell.exec(
        cell.flow("boxed", BOXED), CONTAINED, envs=["box=docker@far"], timeout=600
    )

    seen = _contained(cell, ran)
    landed = docker_box.run(f"cat {there}/proof.txt 2>/dev/null || true")
    assert landed.strip() == seen["hostname"], f"the far host holds {landed!r}\n{ran}"
    assert not Path(there).exists(), f"{there} is on this machine too: proves nothing"


#: Where the cells asking for a GPU take turns, one lock file per GPU: the daemon here has
#: fewer GPUs than the matrix has CLIs running at once, and a role refused a GPU is refused
#: its run -- which would be a cell failing for the machine's sake.
_GPU_LOCKS = Path(tempfile.gettempdir()) / "hmz-matrix-gpu"


@contextlib.contextmanager
def _a_gpu(gpus: int) -> Generator[None]:
    """Holds one of this machine's GPUs for this cell, waiting for one to come free."""
    _GPU_LOCKS.mkdir(exist_ok=True)
    while True:
        for at in range(gpus):
            with (_GPU_LOCKS / f"{at}.lock").open("a") as held:
                try:
                    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                yield
                return
        time.sleep(1.0)


def _gpus() -> tuple[str, ...]:
    """The NVIDIA GPUs docker's default here hands out, by the names its CDI lists them by."""
    from hmz.coganchor.machines import gpus_listed

    said = subprocess.run(
        ["docker", "info", "--format", "{{json .DiscoveredDevices}}"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    try:
        listed = cast("list[Any]", json.loads(said.stdout or "null") or [])
    except ValueError:
        listed = []
    return gpus_listed(listed)


#: What `BOXED` declares its container as, and what `test_docker_gpu` declares instead.
_BOX = (
    "class Box(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):\n"
    '    _image = "python:3.12-slim"\n'
)
_GPU_BOX = (
    "class Box(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin, GPUEnvMixin):\n"
    '    _image = "python:3.12-slim"\n'
    "    _gpu_count = 1\n"
)


@feature(timeout=1800)
def test_docker_gpu(cell: Cell, daemon: None) -> None:
    """An environment declaring one GPU is a container seeing exactly one, the agent too.

    The GPU is the capability here, and the CLI only the one reaching for it: the agent runs
    `nvidia-smi -L` in its container, and one line comes back. Cells take this machine's GPUs
    in turn, so the cell may wait for one; hence the longer ceiling.
    """
    del daemon
    gpus = _gpus()
    if not gpus:
        pytest.skip(
            "environment: docker's default here lists no NVIDIA GPU by CDI name"
        )
    there = cell.root / "box"
    there.mkdir()
    assert _BOX in BOXED, "BOXED no longer declares its box as this row rewrites it"
    source = BOXED.replace(_BOX, _GPU_BOX).replace(
        "    FlowParams,\n", "    FlowParams,\n    GPUEnvMixin,\n"
    )

    with _a_gpu(len(gpus)):
        ran = cell.exec(
            cell.flow("gpuboxed", source),
            "Use your shell tool to run exactly this one command in your working "
            "directory, then reply with exactly one word, DONE: nvidia-smi -L > gpus.txt",
            envs=[f"box=docker@local{there}"],
            timeout=600,
        )

    listed = (there / "gpus.txt").read_text().strip().splitlines()
    assert len(listed) == 1, f"the agent's container sees {listed}\n{ran}"
    assert listed[0].startswith("GPU "), listed


# ---------------------------------------------------------- where a run keeps its sessions


def _home_of(cell: Cell) -> Path:
    """The home the CLI's turns would have written their sessions to, had none been kept."""
    from hmz.coganchor import backends

    profile = backends.named(cell.cli)
    assert profile is not None
    accounts = cell.hmz.accounts
    held = accounts.find(cell.cli, cell.place.provider) if cell.place.provider else None
    return profile.directory({**os.environ, **accounts.environ(held)})


def _at_home(home: Path, sessions: Sequence[str]) -> dict[Path, float]:
    """Every file under a CLI's own session paths there, and when each was last written."""
    found: dict[Path, float] = {}
    for said in sessions:
        patterned = any(mark in said for mark in "*?[")
        for one in home.glob(said) if patterned else [home / said]:
            inside = one.rglob("*") if one.is_dir() else [one]
            for each in inside:
                with contextlib.suppress(OSError):
                    if each.is_file():
                        found[each] = each.stat().st_mtime
    return found


def _mentions(path: Path, said: bytes) -> bool:
    """Whether a file holds some bytes, read a piece at a time."""
    with contextlib.suppress(OSError), path.open("rb") as stream:
        carried = b""
        while chunk := stream.read(1 << 20):
            if said in carried + chunk:
                return True
            carried = chunk[-len(said) :]
    return False


@feature()
def test_sessions_kept(cell: Cell) -> None:
    """A run's session is kept in its epic, as files rather than links, and nowhere at home.

    Its log is read back through `epic.logs` from `<epic>/sessions/<cli>/`, the epic holds no
    symlink, and what the CLI's own session paths at home gained while the run ran -- listed
    before and after -- names nothing of it. Asked of the session rather than of the whole
    listing: whoever is running this is often in a session of the same CLI, which goes on
    writing there.
    """
    from hmz.coganchor import backends
    from hmz.coganchor.providers.redirect import supervises
    from hmz.runtime import epic as epics

    profile = backends.named(cell.cli)
    assert profile is not None
    if not profile.told and not supervises():
        pytest.skip(
            "environment: this machine cannot supervise a turn (no ptrace), so the"
            " session stays in the CLI's own home and the epic says where"
        )
    home = _home_of(cell)
    before = _at_home(home, profile.sessions)

    epic, session = _ran(cell)

    kept = epic / epics.SESSIONS / cell.cli
    assert session.where == f"{epics.SESSIONS}/{cell.cli}", session
    logs = epics.logs(epic, session)
    if profile.logs:
        assert logs, f"no log of {session.ident} under {kept}"
    assert all(one.is_relative_to(kept) for one in logs.values()), logs
    linked = [str(one) for one in epic.rglob("*") if one.is_symlink()]
    assert not linked, f"the epic holds links: {linked}"
    after = _at_home(home, profile.sessions)
    # Its id, and the workspace -- whole, and as a CLI makes a directory name of it -- which
    # no run but this one has had.
    where = str(cell.workspace)
    named = (session.ident, where, re.sub(r"[^A-Za-z0-9]", "-", where))
    gained = [
        str(one)
        for one, when in after.items()
        if before.get(one) != when
        and (
            any(word in str(one) for word in named)
            or any(_mentions(one, word.encode()) for word in (session.ident, where))
        )
    ]
    assert not gained, f"{cell.cli} wrote this run's session at home too: {gained}"


# -------------------------------------------------------- several frontends on one run


FRONTED = '''"""An agent, and two people outside the run each answering for a part of it."""

import json

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowParams,
    LocalEnv,
    Outworlder,
    flow,
)


class Workspace(LocalEnv, FilesEnvMixin): ...


class Agents(AgentCollection):
    worker: Agent
    planner: Outworlder
    reviewer: Outworlder


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def fronted(task, *, agents, envs, params, ctx):
    here, worker = envs["workspace"], agents["worker"]
    session = await worker.spawn(env=here)
    planner = await agents["planner"].spawn(env=here)
    reviewer = await agents["reviewer"].spawn(env=here)
    word = await agents["planner"].run("Which word?", session=planner)
    colour = await agents["reviewer"].run("Which colour?", session=reviewer)
    said = await worker.run(task.replace("WORD", str(word)), session=session)
    kept = {"word": word, "colour": colour, "said": said}
    await here.write("fronted.json", json.dumps(kept).encode())
    return said
'''


def _hosted(workspace: Path) -> Daemon:
    """A host of the workspace's runs, started from a process of its own as a program would.

    Not from this one: a host is a fork, and this process is a test runner's, with threads.
    """
    from hmz import daemon

    subprocess.run(
        [sys.executable, "-c", "from hmz.sdk import Daemons; Daemons().host()"],
        cwd=workspace,
        check=True,
        timeout=60,
    )
    found = daemon.running(workspace)
    assert found is not None, "no host is holding the workspace's runs"
    return found


class _Attached:
    """`hmz attach --json` as a process of its own: requests a line in, messages a line out."""

    def __init__(self, workspace: Path, name: str, *argv: str) -> None:
        self.heard: list[dict[str, Any]] = []
        self._replies: queue.Queue[dict[str, Any]] = queue.Queue()
        # Its stderr into a file rather than a pipe, so that nothing but the one thread
        # below reads its stdout, and a pipe nobody reads never holds it up.
        self._err = workspace.parent / f"attach-{name}.err"
        with self._err.open("w") as err:
            self.running = subprocess.Popen(
                [sys.executable, "-m", "hmz", "attach", "--json", *argv],
                cwd=workspace,
                env={**os.environ, "HUMANIZE_NAME": name},
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=err,
                text=True,
            )
        self._reading = threading.Thread(target=self._reads, daemon=True)
        self._reading.start()

    def _reads(self) -> None:
        assert self.running.stdout is not None
        with contextlib.suppress(OSError, ValueError):
            for line in self.running.stdout:
                with contextlib.suppress(ValueError):
                    said = cast("dict[str, Any]", json.loads(line))
                    (
                        self._replies.put
                        if said.get("type") == "reply"
                        else self.heard.append
                    )(said)

    def asks(self, **said: Any) -> dict[str, Any]:
        """One request, and its reply."""
        assert self.running.stdin is not None
        self.running.stdin.write(json.dumps({**said, "id": "matrix"}) + "\n")
        self.running.stdin.flush()
        return self._replies.get(timeout=60)

    def close(self) -> str:
        """Lets go, however it stands, having read all it said, and answers its stderr."""
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.running.wait(30)
        if self.running.poll() is None:
            self.running.kill()
            self.running.wait()
        # Its stdout ends with it, so the reader has had the last line once it is done.
        self._reading.join(30)
        if self.running.stdin is not None:
            with contextlib.suppress(OSError):
                self.running.stdin.close()
        return self._err.read_text(errors="replace")


@feature(timeout=900)
def test_frontends(cell: Cell) -> None:
    """One run held by a host, three frontends: each part answered only by who claimed it.

    Started from an SDK link that claims nothing and watches. `hmz attach -c planner` holds
    the planner, a second SDK link the reviewer, and each is refused the other's question. A
    word from the second link reaches the agent: into its turn where the CLI steers, and else
    folded into the turn it starts next.
    """
    from hmz.flows import HarnessKind
    from hmz.runtime import Refused
    from hmz.runtime.flowing.spi import HARNESS_CAPABILITIES

    steers = SteeringAgentMixin in HARNESS_CAPABILITIES[HarnessKind(cell.cli)]
    word, second = _word(), _word()
    if steers:
        task, told = SLOW, "Stop now. Reply with exactly one word: STEERED"
    else:
        task = (
            "Reply with exactly two words separated by a space: first WORD, and then "
            "the word the last line of this message gives you."
        )
        told = f"The second word is {second}."
    flow = cell.flow("fronted", FRONTED)
    host = _hosted(cell.workspace)
    heard: queue.Queue[dict[str, Any]] = queue.Queue()
    alice: _Attached | None = None
    records: list[dict[str, Any]] = []
    refused: dict[str, str] = {}
    try:
        with host.link(name="watcher") as watcher, host.link(name="bob") as bob:
            watcher.heard(heard.put)
            bob.claim("reviewer")
            alice = _Attached(cell.workspace, "alice", "-c", "planner")
            deadline = time.monotonic() + 60
            while True:
                said = heard.get(timeout=max(0.1, deadline - time.monotonic()))
                if said["type"] == "claims" and {"planner", "reviewer"} <= set(
                    said["claims"]
                ):
                    break
            watcher.start(
                flow, task, agents={"worker": cell.place.spec()}, budget=_BUDGETED
            )
            due: float | None = None
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                if due is not None and time.monotonic() >= due:
                    due = None
                    bob.say(told, to="worker")
                try:
                    said = heard.get(timeout=0.5)
                except queue.Empty:
                    continue
                if "seq" in said:
                    records.append(said)
                kind = said["type"]
                if kind == "asked" and said["role"] == "planner":
                    try:
                        bob.answer(said["question"], "not bob's to say")
                    except Refused as why:
                        refused["planner"] = str(why)
                    assert alice.asks(
                        do="answer", question=said["question"], text=word
                    )["ok"]
                elif kind == "asked" and said["role"] == "reviewer":
                    got = alice.asks(do="answer", question=said["question"], text="red")
                    refused["reviewer"] = "" if got["ok"] else str(got.get("why"))
                    if not steers:
                        bob.say(told, to="worker")
                    bob.answer(said["question"], "blue")
                elif (
                    steers
                    and kind == "event"
                    and said["kind"] == "begins"
                    and said["agent"] == "worker"
                    and due is None
                ):
                    due = time.monotonic() + SETTLE
                elif kind == "ended":
                    break
    finally:
        err = alice.close() if alice is not None else ""
        with contextlib.suppress(Exception):
            host.kill()

    (ended,) = [one for one in records if one["type"] == "ended"] or [None]
    assert ended is not None, f"the run never ended: {records[-5:]}"
    if ended["how"] != "done":
        with cell.environmental():
            _raised(ended["why"])
    assert ended["how"] == "done", ended
    assert refused.get("planner", "").startswith("planner is alice@cli's"), refused
    assert refused.get("reviewer", "").startswith("reviewer is bob's"), refused
    answered = [
        (one["role"], one["by"]) for one in records if one["type"] == "answered"
    ]
    assert answered == [("planner", "alice@cli"), ("reviewer", "bob")], answered
    spoken = [(one["text"], one["by"]) for one in records if one["type"] == "said"]
    assert (told, "bob") in spoken, (
        f"nothing says bob's word reached the agent: {records}"
    )
    kept = json.loads((cell.workspace / "fronted.json").read_text())
    assert (kept["word"], kept["colour"]) == (word, "blue"), kept
    if steers:
        assert _says(kept["said"], "STEERED"), kept
    else:
        assert _says(kept["said"], word), kept
        assert _says(kept["said"], second), kept
    # And `hmz attach` read the same answers, said by who gave them.
    assert alice is not None
    theirs = [
        (one["role"], one["by"]) for one in alice.heard if one["type"] == "answered"
    ]
    assert theirs == answered, f"{alice.heard[-5:]}\n{err}"


def _raised(why: str) -> None:
    """Raises what a run the host drove failed of, where it was the machine's to answer for.

    The host says how a run failed as `<Exception>: <message>`; the three a cell skips for
    are raised again here, so that `Cell.environmental` can tell them from anything else.
    """
    from hmz.flows import HarnessRefused, HarnessSandboxed, HarnessThrottled

    kind, _, message = why.partition(": ")
    for one in (HarnessThrottled, HarnessRefused, HarnessSandboxed):
        if kind == one.__name__:
            raise one(message)


def _tui(name: str) -> str:
    """`hmz` as a person types it, named."""
    return f"HUMANIZE_NAME={name} {shlex.join([sys.executable, '-m', 'hmz'])}"


@feature(once=True, group="claude", timeout=900)
def test_frontends_tui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, billed: list[Path]
) -> None:
    """Two interfaces on one run with an agent in it: each person answers their own part.

    `HUMANIZE_NAME=alice hmz` and `HUMANIZE_NAME=bob hmz`, each in a terminal of its own on
    one workspace. Each claims one of the run's outworlders from its view and answers it; the
    other is told whose it is. Bob's word, typed on the view every agent is on, goes into the
    agent's turn under way, and alice reads it as his. The agent is Claude, at the place its
    column runs at: the interface is the same whichever CLI is behind it -- and it runs among
    that column's cells, as every turn of one CLI does.
    """
    from hmz import daemon
    from hmz.runtime import Hmz
    from hmz.runtime.kept import Runs
    from tests.matrix import places
    from tests.stubs import written
    from tests.system.cli.test_frontends import Panes

    if shutil.which("tmux") is None:
        pytest.skip("environment: drives tmux, which is not installed here")
    workspace = tmp_path / "project"
    workspace.mkdir()
    billed.append(workspace)
    # Before the place is settled, which takes a turn: in the workspace, not in whatever
    # directory the test runner was started in.
    monkeypatch.chdir(workspace)
    place = places.settled("claude")
    if isinstance(place, str):
        pytest.skip(
            f"environment: claude takes a turn nowhere on this machine -- {place}"
        )
    written(workspace / ".humanize" / "flows", "fronted", FRONTED)
    # Every pane reads as a pipe would, and holds its runs apart, as a person's would.
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("HUMANIZE_DAEMON", raising=False)
    word = _word()
    with contextlib.ExitStack() as holding:
        if place.provider:
            holding.enter_context(places.borrowed("claude", place.provider))
        # Set up the way saving the flow menu would, so that `$` starts it on the spot.
        Hmz(workspace).settings.remember(
            "local/fronted", {"worker": Runs(place.spec())}, budget=dict(_BUDGETED)
        )
        panes = Panes(workspace)

        def closes() -> None:
            panes.close()
            found = daemon.running(workspace)
            if found is not None:
                found.kill()

        holding.callback(closes)
        alice = panes.opens(_tui("alice"))
        panes.waits(alice, "humanize")
        panes.types(alice, f"$local/fronted {SLOW}")
        panes.waits(alice, "Which word?", 120)
        bob = panes.opens(_tui("bob"))
        panes.waits(bob, "Which word?")

        # Each holds the outworlder they answer for, from its own view.
        panes.presses(alice, "BTab")
        panes.waits(alice, "reading outworlder planner")
        panes.types(alice, "/claim")
        panes.waits(alice, "planner is yours to answer")
        panes.presses(bob, "BTab")
        panes.presses(bob, "BTab")
        panes.waits(bob, "reading outworlder reviewer")
        panes.types(bob, "/claim")
        panes.waits(bob, "reviewer is yours to answer")
        panes.waits(alice, "reviewer · outworlder · bob@tui's")

        panes.types(alice, word)
        panes.waits(bob, "Which colour?")
        # The reviewer's question is bob's: alice is told so rather than asked.
        panes.waits(alice, "waiting for bob@tui")
        # And back a view, to wherever the agent's words are.
        panes.presses(alice, "Tab")
        panes.types(bob, "blue")

        # The agent's turn: bob reads every agent -- round from the last view to the first --
        # and says a word into it.
        panes.presses(bob, "BTab")
        panes.waits(bob, "reading every agent")
        panes.waits(bob, "worker is working", 180)
        time.sleep(SETTLE)
        panes.types(bob, "Stop now. Reply with exactly one word: STEERED")
        panes.waits(alice, "Reply with exactly one word: STEERED · by bob@tui", 300)
        for one in (alice, bob):
            panes.waits(one, "— the flow is done —", 300)
        kept = json.loads((workspace / "fronted.json").read_text())
        assert (kept["word"], kept["colour"]) == (word, "blue"), kept
        assert _says(kept["said"], "STEERED"), kept
        for one in (alice, bob):
            panes.types(one, "/exit")
        deadline = time.monotonic() + 60
        while daemon.running(workspace) is not None:
            assert time.monotonic() < deadline, "the host outlived both interfaces"
            time.sleep(0.2)
