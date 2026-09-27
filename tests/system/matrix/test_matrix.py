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
import json
import os
import secrets
import subprocess
import tarfile
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
from tests.matrix.cells import Unsettled, feature, forks, mixin, mounts, read_only

if TYPE_CHECKING:
    from hmz.coganchor.agents import AgentBase, SessionBase
    from hmz.coganchor.agents.event import Event
    from hmz.runtime.epic import Session
    from tests.flows.sshd import Box
    from tests.matrix.cells import Cell

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


@feature(mixin(SteeringAgentMixin))
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


@feature()
def test_interrupt(cell: Cell) -> None:
    """A turn the flow cancels stops at once, and its session takes the next turn."""
    got = cell.run(
        cell.flow("interrupted", INTERRUPTED.replace("SETTLE", str(SETTLE))), SLOW
    )

    assert not got["early"], f"the slow turn was over within {SETTLE}s: {got}"
    assert got["took"] < 60, f"the cancelled turn took {got['took']:.0f}s to stop"
    assert _says(got["after"], "AFTER"), got


@feature()
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


@feature(read_only)
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


#: What every anchored turn whose host does not share this machine's paths runs into, and
#: which the docker environments change fixes in the anchor.
_U8 = "fixed by the docker-envs PR (U8)"


@feature(
    timeout=900,
    xfail={
        "codex": Unsettled(
            "anchored turn bug: `codex app-server` hangs when anchored, whatever the host;"
            f" {_U8}"
        ),
        "cursor-agent": Unsettled(
            "anchored turn bug: cursor-agent's launcher runs `realpath` on the target and"
            f" exits 127; {_U8}"
        ),
        "dsh": Unsettled(
            "anchored turn bug: the SDK spawns its runtime with cwd set to the anchor's"
            f" mirror before that mirror exists (ENOENT); {_U8}"
        ),
        "mimo": Unsettled(
            "anchored turn bug: mimo's node launcher spawns `.mimocode` on the target and"
            f" exits 127; {_U8}"
        ),
        "zcode": Unsettled(
            "anchored turn bug: zcode's launcher execs `/opt/ZCode/zcode` on the target and"
            " exits 127 -- the class of mimo's and cursor-agent's, handed to the"
            " docker-envs PR (U8)"
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
