"""What the interface's integration tests drive it with: a stand-in `claude`, and a pilot's keys.

The stand-in speaks Claude Code's stream-json closely enough for Humanize's own `claude`
driver to take turns through it, so a test drives the whole chain -- the interface, the runs
it holds, the driver, a process -- with nothing real behind it:

- asked what it runs (the `list_models` control request), it names :data:`MODEL`;
- told something, it answers `heard <its last line>` at once;
- told something starting with `wait`, it says `still on it` and holds the answer until it is
  told something more, then answers with both -- which is what makes steering a turn and
  cutting one off observable;
- told something starting with `ask`, it stops to ask `Which colour?`, offering `red` and
  `blue`, and answers `picked <the answer>`;
- told something starting with `tools`, it starts an agent of its own to `look around` and
  runs `foo bar` in Bash with a backslash before the space, before it answers -- a backslash
  being what a row of markup is likeliest to trip over;
- a word put into a turn under way is acknowledged as Claude acknowledges one;
- every turn costs 1,000 input tokens and 200 output tokens;
- what it is told is kept as a conversation where Claude Code keeps one, under
  `$CLAUDE_CONFIG_DIR/projects/`, and one resumed with `--fork-session` is copied to a new one --
  which is what lets a chat be kept as it stopped and carried on.

Every time it starts it writes its arguments down, and everything it is told, under `.stand-in/`
in the directory it was started in (:func:`started`, :func:`heard`), so that a test can say
what reached the agent.

Everything a test does to the interface is a key or a click; what it reads back is the
screen (:func:`screen`) or a file the interface wrote.
"""

from __future__ import annotations

import asyncio
import datetime
import html
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual.widgets import OptionList

from hmz.coganchor.agents.native import NativeCommand
from hmz.tui import Humanize
from hmz.tui.dropdown import Dropdown
from hmz.tui.flows import Flows
from hmz.tui.pick import Configures, Confirms

if TYPE_CHECKING:
    import threading
    from collections.abc import Callable

    import pytest
    from textual.app import App
    from textual.pilot import Pilot

#: The model the stand-in says it runs.
MODEL = "claude-stand-in"

#: What an interface opened on the stand-in is set up to run, as its status line says it.
RUNS = f"claude/{MODEL}:high"


#: A flow that is a conversation: one agent, and every line said back is its next turn, as a
#: chat's are -- but a flow, which the interface reads as any flow: a monitor, views to step
#: round, a run to stop, a budget to be given.
TALK = """
import contextlib

from hmz.flows import (
    Agent, AgentCollection, AskUserHookAgentMixin, AskUserHookResult, CapabilityNotGranted,
    EnvCollection, FlowContext, FlowParams, LocalEnv, Outworlder, flow,
)


class Assistant(Agent, AskUserHookAgentMixin):
    pass


class Agents(AgentCollection):
    assistant: Assistant
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    pass


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def talk(task, *, agents, envs, params, ctx: FlowContext) -> None:
    assistant, human = agents["assistant"], agents["human"]
    conversation = await assistant.spawn()
    person = await human.spawn()

    async def asked(params):
        offered = f" ({' / '.join(params.options)})" if params.options else ""
        said = await human.run(f"{params.question}{offered}", session=person)
        return AskUserHookResult(answer=said or None)

    with contextlib.suppress(CapabilityNotGranted):
        assistant.on_ask_user(asked)
    said = task
    while said:
        answered = await assistant.run(said, session=conversation, env=envs["workspace"])
        said = await human.run(answered, session=person)
"""


def _talks() -> str:
    """:data:`TALK`, written where a path names it: `talk`, a flow of its own directory."""
    at = Path(tempfile.mkdtemp(prefix="hmz-talk-")) / "talk"
    at.mkdir()
    (at / "__init__.py").write_text(TALK)
    return str(at)


#: :data:`TALK`, named by its path.
TALKS = _talks()


def talks_set_up(workspace: Path) -> None:
    """Remembers :data:`TALKS` set up in the workspace: the stand-in, and a budget to spend."""
    from hmz.runtime.kept import read_back
    from hmz.runtime.settings import Settings

    runs = read_back(RUNS)
    assert runs is not None
    Settings(workspace).remember(TALKS, {"assistant": runs}, budget={"cost": 100.0})


#: The terminal every pilot runs in.
SIZE = (100, 40)

#: How long anything here waits for the interface before failing the test. A ceiling only:
#: on a loaded machine the stand-in CLI the interface first asks can take 20s to answer.
PATIENCE = 60.0

#: One run of text in a screenshot: where it starts, on which row, and what it says.
_TEXT = re.compile(r'<text[^>]*? x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]*)</text>')

#: How wide one terminal cell is drawn in a screenshot.
_CELL = 12.2

_STAND_IN = """
import json, os, re, shutil, sys, uuid

def log(name, said):
    try:
        os.makedirs(".stand-in", exist_ok=True)
        with open(os.path.join(".stand-in", name), "a") as kept:
            kept.write(json.dumps(said) + "\\n")
    except OSError:
        pass  # somewhere a turn may not write, which is anywhere but its workspace

def say(**said):
    print(json.dumps(said), flush=True)

log("started.jsonl", sys.argv[1:])
flags = dict(zip(sys.argv, sys.argv[1:]))
said = flags.get("--session-id") or flags.get("--resume") or "stand-in"
home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
projects = os.path.join(home, "projects", re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd()))
if "--resume" in flags and "--fork-session" in sys.argv:
    said = str(uuid.uuid4())
    shutil.copy(os.path.join(projects, flags["--resume"] + ".jsonl"),
                os.path.join(projects, said + ".jsonl"))
say(type="system", subtype="init", session_id=said, model=flags.get("--model", ""))
held, turns = [], 0
for line in sys.stdin:
    message = json.loads(line)
    if message.get("type") == "control_request":
        answer = {"subtype": "success", "request_id": message["request_id"], "response": {}}
        if message["request"].get("subtype") == "list_models":
            answer["response"] = {"models": [{
                "value": "stand-in", "resolvedModel": "MODEL",
                "supportedEffortLevels": ["low", "high"],
            }]}
        say(type="control_response", response=answer)
        continue
    if message.get("type") == "control_response":
        given = message["response"]["response"].get("updatedInput") or {}
        answer = "picked " + " ".join((given.get("answers") or {}).values())
        say(type="assistant", message={"content": [{"type": "text", "text": answer}]})
        turns += 1
        say(type="result", subtype="success", result=answer, modelUsage={
            "MODEL": {"inputTokens": 1000 * turns, "outputTokens": 200 * turns},
        })
        held = []
        continue
    if message.get("type") != "user":
        continue
    text = message["message"]["content"][0]["text"]
    log("heard.jsonl", text)
    os.makedirs(projects, exist_ok=True)
    with open(os.path.join(projects, said + ".jsonl"), "a") as kept:
        kept.write(json.dumps({"type": "user", "sessionId": said,
                               "message": {"role": "user", "content": text}}) + "\\n")
    if message.get("uuid"):
        say(type="command_lifecycle", state="started", command_uuid=message["uuid"])
    lines = [one.strip() for one in text.splitlines() if one.strip()]
    held.append(next((one for one in reversed(lines) if not one.startswith("<")), ""))
    if held[0].startswith("ask") and len(held) == 1:
        say(type="control_request", request_id="asks", request={
            "subtype": "can_use_tool", "tool_name": "AskUserQuestion", "input": {
                "questions": [{"question": "Which colour?",
                               "options": [{"label": "red"}, {"label": "blue"}]}],
            },
        })
        continue
    if held[0].startswith("wait") and len(held) == 1:
        say(type="assistant", message={"content": [{"type": "text", "text": "still on it"}]})
        continue
    if held[0].startswith("tools"):
        say(type="assistant", message={"content": [
            {"type": "tool_use", "id": "a1", "name": "Agent",
             "input": {"description": "look around"}},
            {"type": "tool_use", "id": "b1", "name": "Bash",
             "input": {"command": "foo\\\\ bar"}},
        ]})
    answer = "heard " + " then ".join(held)
    say(type="assistant", message={"content": [{"type": "text", "text": answer}]})
    turns += 1
    say(type="result", subtype="success", result=answer, modelUsage={
        "MODEL": {"inputTokens": 1000 * turns, "outputTokens": 200 * turns},
    })
    held = []
""".replace("MODEL", MODEL)


#: A flow of one agent role, `coder`, which can be picked up where it left off: one turn on the
#: task, and a line saying what it answered -- and whether the run was resumed -- added to
#: `said.txt`.
WRITES = """
from pathlib import Path

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, flow


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def writes(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
                 ctx: FlowContext) -> None:
    \"\"\"Takes one turn on the task, and writes down what came of it.\"\"\"
    coder = agents["coder"]
    session = await coder.spawn()
    said = await coder.run(task, session=session, env=envs["workspace"])
    with Path("said.txt").open("a") as kept:
        kept.write(f"{'resumed' if ctx.resumed else 'started'}: {said}\\n")
"""

#: :data:`WRITES`, as `/flow` offers it from the workspace's own `.hmz/flows`.
OWN = "@local/writes"


def claude_logged(home: Path, workspace: Path, ident: str, began: float) -> None:
    """Writes one session as Claude Code logs one: a prompt, a thought, a tool, an answer.

    Args:
      home: Claude Code's home, which the stand-in is given as `CLAUDE_CONFIG_DIR`.
      workspace: Where the session worked.
      ident: The session's id.
      began: When it began, in seconds since the epoch.
    """

    def at(offset: float) -> str:
        return datetime.datetime.fromtimestamp(began + offset, datetime.UTC).isoformat()

    def assistant(
        offset: float, request: str, *blocks: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "type": "assistant",
            "timestamp": at(offset),
            "requestId": request,
            "message": {
                "model": "claude-x",
                "usage": {"input_tokens": 1000, "output_tokens": 200},
                "content": list(blocks),
            },
        }

    folder = "".join(one if one.isalnum() else "-" for one in str(workspace))
    rows = [
        {
            "type": "user",
            "timestamp": at(0),
            "promptId": "p1",
            "cwd": str(workspace),
            "sessionId": ident,
            "message": {"content": "fix the bug"},
        },
        assistant(2, "r1", {"type": "thinking", "thinking": "hmm"}),
        assistant(
            3,
            "r1",
            {
                "type": "tool_use",
                "id": "t1",
                "name": "Bash",
                "input": {"command": "pytest"},
            },
        ),
        {
            "type": "user",
            "timestamp": at(6),
            "promptId": "p1",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
                ]
            },
        },
        assistant(8, "r2", {"type": "text", "text": "fixed"}),
    ]
    log = home / "projects" / folder / f"{ident}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(json.dumps(one) + "\n" for one in rows))


def stand_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts the stand-in `claude` alone on `PATH`, and works in a directory of the test's own.

    Args:
      tmp_path: The test's own directory.
      monkeypatch: What puts everything back afterwards.

    Returns:
      The workspace, which is the working directory from here on.
    """
    binaries = tmp_path / "bin"
    binaries.mkdir()
    program = binaries / "claude"
    program.write_text(f"#!{sys.executable}\n{_STAND_IN}")
    program.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.defpath}")
    # And the daemon's chats, stood in for until it serves them.
    Chats().install(monkeypatch)
    return _workspace(tmp_path, monkeypatch)


def folds_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Folds a chat nobody reads away half a second after its turn, rather than a minute."""
    from tests.integration.doubles_daemon import folds

    folds(0.5, monkeypatch)


def own_flow(workspace: Path, source: str = WRITES) -> None:
    """Puts :data:`WRITES`, or another flow under its name, among the workspace's own flows."""
    flow = workspace / ".hmz" / "flows" / "writes"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(source)


async def set_up_own_flow(pilot: Pilot[None]) -> None:
    """Picks :data:`OWN` from `/flow`, gives it a dollar to spend, and saves it."""
    await opened(pilot)
    await typed(pilot, "/flow")
    await on(pilot, Flows)
    await opens(pilot, OWN)
    await shows(pilot, trail("Installed", OWN), "an epic needs one")
    await gives_a_budget(pilot)
    await leaves(pilot)
    await shows(pilot, f"set up: /flow {OWN} <task> starts it")


async def gives_a_budget(pilot: Pilot[None]) -> None:
    """Gives the flow open in `/flow` a dollar to spend, every flow needing a budget."""
    await opens(pilot, "\x1ebudget")
    await on(pilot, Configures)
    await opens(pilot, "cost")
    await pilot.press(
        "1", "enter", "tab", "enter"
    )  # a dollar, then the button that sets it
    await on(pilot, Flows)


def nothing_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `PATH` with no coding agent on it, and a directory of the test's own to work in.

    Args:
      tmp_path: The test's own directory.
      monkeypatch: What puts everything back afterwards.

    Returns:
      The workspace, which is the working directory from here on.
    """
    monkeypatch.setenv("PATH", os.defpath)
    Chats().install(monkeypatch)
    return _workspace(tmp_path, monkeypatch)


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    monkeypatch.chdir(workspace)
    return workspace


def _logged(workspace: Path, name: str) -> list[Any]:
    kept = workspace / ".stand-in" / name
    if not kept.exists():
        return []
    return [json.loads(line) for line in kept.read_text().splitlines()]


def started(workspace: Path) -> list[list[str]]:
    """The arguments of every stand-in started for a turn, oldest first.

    Not those started to be asked what they run, which is a question rather than a turn.
    """
    return [
        [str(one) for one in argv]
        for argv in _logged(workspace, "started.jsonl")
        if "--model" in argv
    ]


def heard(workspace: Path) -> list[str]:
    """Everything the stand-ins were told, oldest first."""
    return [str(one) for one in _logged(workspace, "heard.jsonl")]


def trail(*steps: str) -> str:
    """Where a sheet says it is, as the line across the top of it spells that."""
    return " \N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK} ".join(steps)


def screen(app: App[Any]) -> str:
    """Everything on the screen now, as plain text, one terminal row per line."""
    lines: dict[float, dict[int, str]] = {}
    for x, y, said in _TEXT.findall(app.export_screenshot()):
        if said.strip("\n"):
            lines.setdefault(float(y), {})[round(float(x) / _CELL)] = html.unescape(
                said
            )
    drawn: list[str] = []
    for _, parts in sorted(lines.items()):
        line = ""
        for column, said in sorted(parts.items()):
            line = line.ljust(column) + said
        drawn.append(line.replace("\xa0", " ").rstrip())
    return "\n".join(one for one in drawn if one)


async def until(pilot: Pilot[None], ready: Callable[[], bool], what: str) -> None:
    """Pumps the interface until `ready` holds, and fails the test if it never does.

    Args:
      pilot: What drives the interface.
      ready: What is being waited for.
      what: What it is, for the failure.
    """
    deadline = time.monotonic() + PATIENCE
    while not ready():
        if time.monotonic() > deadline:
            raise AssertionError(f"gave up waiting for {what}")
        await pilot.pause()
        await asyncio.sleep(0.02)


async def shows(pilot: Pilot[None], *texts: str) -> str:
    """Waits until the screen shows every one of `texts`, and answers what it shows.

    Args:
      pilot: What drives the interface.
      texts: What has to be on the screen.

    Returns:
      The screen, as :func:`screen` reads it.
    """
    app = _app(pilot)
    try:
        await until(pilot, lambda: all(one in screen(app) for one in texts), "it")
    except AssertionError:
        raise AssertionError(
            f"gave up waiting for {texts!r} on a screen showing:\n{screen(app)}"
        ) from None
    return screen(app)


async def wrapped(pilot: Pilot[None], *texts: str) -> None:
    """Waits until the screen shows every one of `texts`, however a row wraps them.

    A row of a list that names an agent is as long as that name, which is random, so words
    said together may be drawn a line apart, the list's edge between them.

    Args:
      pilot: What drives the interface.
      texts: What has to be on the screen, read with every run of white space as one space.
    """
    app = _app(pilot)

    def flat() -> str:
        return " ".join(screen(app).replace("│", " ").split())

    try:
        await until(pilot, lambda: all(one in flat() for one in texts), "it")
    except AssertionError:
        raise AssertionError(
            f"gave up waiting for {texts!r} on a screen showing:\n{screen(app)}"
        ) from None


async def opened(pilot: Pilot[None]) -> None:
    """Waits until the interface has asked the stand-in what it runs, and is set up on it."""
    await shows(pilot, RUNS)


async def typed(pilot: Pilot[None], line: str) -> None:
    """Types one line at whatever has the focus, and presses enter.

    Args:
      pilot: What drives the interface.
      line: What to type.
    """
    await pilot.press(*line, "enter")
    await pilot.pause()


async def on[T](pilot: Pilot[None], sheet: type[T]) -> T:
    """Waits until the screen on top is a `sheet`, and answers it."""
    app = _app(pilot)
    await until(pilot, lambda: isinstance(app.screen, sheet), sheet.__name__)
    await pilot.pause()
    held = app.screen
    assert isinstance(held, sheet)
    return held


def rows(app: Humanize) -> list[str]:
    """The ids of the rows the sheet on top lists, in order: the flows, the pages, the fields."""
    listing = app.screen.query_one("#choices", OptionList)
    return [str(one.id).removeprefix("=") for one in listing.options]


async def onto(pilot: Pilot[None], row: str, listing: str = "#choices") -> None:
    """Walks the cursor of a list on the screen on top on to one row, with the arrow keys.

    Args:
      pilot: What drives the interface.
      row: The row, by its id.
      listing: The list, as a selector: the rows of a sheet unless it says otherwise.
    """
    app = _app(pilot)
    listed = app.screen.query_one(listing, OptionList)
    ids = [str(one.id).removeprefix("=") for one in listed.options]
    at = ids.index(row)
    for _ in range(len(ids) + 1):
        if listed.highlighted == at:
            return
        await pilot.press("down" if (listed.highlighted or 0) < at else "up")
    assert listed.highlighted == at, f"the cursor never reached {row!r}"


async def opens(pilot: Pilot[None], row: str) -> None:
    """Walks on to one row of the sheet on top, and presses enter on it."""
    await onto(pilot, row)
    await pilot.press("enter")
    await pilot.pause()


async def picks(pilot: Pilot[None], row: str, value: str) -> None:
    """Drops the values of one row under it, and picks one of them with the keys.

    Args:
      pilot: What drives the interface.
      row: The row, by its id.
      value: The value, by what picking it answers with.
    """
    app = _app(pilot)
    await opens(pilot, row)
    dropped = await on(pilot, Dropdown)
    listing = dropped.query_one(OptionList)
    at = [str(one.id) for one in listing.options].index(f"={value}")
    for _ in range(len(listing.options) + 1):
        if listing.highlighted == at:
            break
        await pilot.press("down" if (listing.highlighted or 0) < at else "up")
    assert listing.highlighted == at, f"the cursor never reached {value!r}"
    await pilot.press("enter")
    await until(pilot, lambda: app.screen is not dropped, "the list to close")


async def leaves(pilot: Pilot[None], *, saving: bool = True) -> None:
    """Presses esc until every sheet is closed, saving or dropping what they hold when asked.

    Args:
      pilot: What drives the interface.
      saving: Whether to answer the question about unsaved changes with save.
    """
    app = _app(pilot)
    for _ in range(12):
        if len(app.screen_stack) == 1:
            return
        if isinstance(app.screen, Confirms):
            await pilot.press(*(("enter",) if saving else ("down", "enter")))
        else:
            await pilot.press("escape")
        await pilot.pause()
    raise AssertionError(f"could not leave a screen showing:\n{screen(app)}")


def _app(pilot: Pilot[None]) -> Humanize:
    app = pilot.app
    assert isinstance(app, Humanize)
    return app


#: What a stand-in chat's harness takes at its own prompt: a command and a skill, a command only
#: its own interface serves, a skill named as a flow is, a shell and files.
CATALOG = (
    NativeCommand("/", "compact", "Compact the conversation", "pass"),
    NativeCommand("/", "config", "Open the settings", "refuse"),
    NativeCommand("$", "review", "Review the change", "call"),
    NativeCommand("$", "rlar", "A skill of the flow's name", "call"),
    NativeCommand("!", "", "Run a shell command", "emulate"),
    NativeCommand("@", "", "Mention a file", "pass"),
)

#: What a `!` command run for a stand-in chat prints.
PRINTED = "file.txt"


class Chats:
    """The daemon's chats (`chat.*`, Section 4.21 of daemon.md), as the interface asks them.

    Every call goes on to the daemon of the test, whose hosts are held in this process, as it
    would have; this keeps what was asked, can hold a `chat.start` back (and refuse it once
    let go), and has every chat's harness list a catalogue of its own -- the stand-in lists no
    skills, and a test about what a `$` line names needs one that does.

    Attributes:
      asked: Every call made, as `(method, params)`, oldest first.
      starting: Set to hold a `chat.start` until it is set, where it is not None.
      refusing: Whether a held start is refused once let go.
    """

    def __init__(self, catalog: tuple[NativeCommand, ...] = CATALOG) -> None:
        self.catalog = catalog
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.starting: threading.Event | None = None
        self.refusing = False

    def install(self, monkeypatch: pytest.MonkeyPatch) -> Chats:
        """Watches every `chat.*` the interface asks from here on."""
        from hmz.runtime.chatting import Chat

        # The interface's one way to the daemon's chats, named rather than reached into.
        real = vars(Humanize)["_chat_asked"]
        catalog = list(self.catalog)

        # A function rather than this bound method, so that the interface is handed to it.
        def asked(app: Humanize, request: dict[str, Any]) -> dict[str, Any]:
            said = dict(request)
            method = str(said.pop("do"))
            self.asked.append((method, said))
            if method == "chat.start" and self.starting is not None:
                self.starting.wait(10)
                if self.refusing:
                    raise RuntimeError("no room to start")
            return real(app, request)

        def natives(chat: Chat) -> list[NativeCommand]:
            del chat
            return catalog

        monkeypatch.setattr(Humanize, "_chat_asked", asked)
        monkeypatch.setattr(Chat, "natives", natives)
        return self

    def started(self) -> list[dict[str, Any]]:
        """What each `chat.start` was asked with, oldest first."""
        return [said for method, said in self.asked if method == "chat.start"]


def tell(app: Humanize, message: dict[str, Any]) -> None:
    """Tells the interface one record of the runs, as its link would have handed it over.

    For a record the host of this checkout does not say yet, or a moment a test needs exactly:
    a question asked as a form, pending, answered.
    """
    # The interface's one way in for what the runs say, named rather than reached into.
    vars(Humanize)["_told"](app, message)


class Answers:
    """The answers the interface sends (`epic.answer`), kept, and refused where a test says.

    Every other call goes on to the daemon of the test as it would have.

    Attributes:
      sent: What each answer was sent with -- `question`, and `value` or `text` -- oldest
        first.
      refusing: What the host refuses an answer with: `{path, message}` apiece, or none to
        take it.
    """

    def __init__(
        self, refusing: Callable[[dict[str, Any]], list[dict[str, Any]]]
    ) -> None:
        self.sent: list[dict[str, Any]] = []
        self.refusing = refusing

    def install(self, monkeypatch: pytest.MonkeyPatch) -> Answers:
        """Watches every answer the interface sends from here on."""
        from hmz.daemon.link import Link
        from hmz.runtime import Refused

        real = Link.asked

        def asked(
            link: Link, said: dict[str, Any], *, seconds: float | None = None
        ) -> dict[str, Any]:
            if said.get("do") != "answer":
                return real(link, said, seconds=seconds)
            sent = {key: value for key, value in said.items() if key != "do"}
            self.sent.append(sent)
            if errors := self.refusing(sent):
                raise Refused(
                    f"the answer does not fit: {errors[0]['message']}",
                    code=400,
                    data={"errors": errors},
                )
            return {"ok": True}

        monkeypatch.setattr(Link, "asked", asked)
        return self
