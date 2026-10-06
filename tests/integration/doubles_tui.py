"""What the interface's integration tests drive it with: a stand-in `claude`, and a pilot's keys.

The stand-in speaks Claude Code's stream-json closely enough for humanize's own `claude`
driver to take turns through it, so a test drives the whole chain -- the interface, the runs
it holds, the driver, a process -- with nothing real behind it:

- asked what it runs (the `list_models` control request), it names :data:`MODEL`;
- told something, it answers `heard <its last line>` at once;
- told something starting with `wait`, it says `still on it` and holds the answer until it is
  told something more, then answers with both -- which is what makes steering a turn and
  cutting one off observable;
- a word put into a turn under way is acknowledged as Claude acknowledges one;
- every turn costs 1,000 input tokens and 200 output tokens.

Every time it starts it writes its arguments down, and everything it is told, under `.stand-in/`
in the directory it was started in (:func:`started`, :func:`heard`), so that a test can say
what reached the agent.

Everything a test does to the interface is a key or a click; what it reads back is the
screen (:func:`screen`) or a file the interface wrote.
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
import sys
import time
from typing import TYPE_CHECKING, Any

from textual.widgets import OptionList

from hmz.tui import Humanize
from hmz.tui.dropdown import Dropdown
from hmz.tui.flows import Flows
from hmz.tui.pick import Configures, Confirms

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest
    from textual.pilot import Pilot

#: The model the stand-in says it runs.
MODEL = "claude-stand-in"

#: What an interface opened on the stand-in is set up to run, as its status line says it.
RUNS = f"claude/{MODEL}:high"

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
import json, os, sys

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
    if message.get("type") != "user":
        continue
    text = message["message"]["content"][0]["text"]
    log("heard.jsonl", text)
    if message.get("uuid"):
        say(type="command_lifecycle", state="started", command_uuid=message["uuid"])
    lines = [one.strip() for one in text.splitlines() if one.strip()]
    held.append(next((one for one in reversed(lines) if not one.startswith("<")), ""))
    if held[0].startswith("wait") and len(held) == 1:
        say(type="assistant", message={"content": [{"type": "text", "text": "still on it"}]})
        continue
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
    return _workspace(tmp_path, monkeypatch)


def own_flow(workspace: Path) -> None:
    """Puts :data:`WRITES` among the workspace's own flows."""
    flow = workspace / ".hmz" / "flows" / "writes"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(WRITES)


async def set_up_own_flow(pilot: Pilot[None]) -> None:
    """Picks :data:`OWN` from `/flow`, gives it a dollar to spend, and saves it."""
    await opened(pilot)
    await typed(pilot, "/flow")
    await on(pilot, Flows)
    await opens(pilot, OWN)
    await shows(pilot, trail("Installed", OWN), "a run needs one")
    await opens(pilot, "\x1ebudget")
    await on(pilot, Configures)
    await opens(pilot, "cost")
    await pilot.press(
        "1", "enter", "tab", "enter"
    )  # a dollar, then the button that sets it
    await on(pilot, Flows)
    await leaves(pilot)
    await shows(pilot, f"◉ {OWN}")


def nothing_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `PATH` with no coding agent on it, and a directory of the test's own to work in.

    Args:
      tmp_path: The test's own directory.
      monkeypatch: What puts everything back afterwards.

    Returns:
      The workspace, which is the working directory from here on.
    """
    monkeypatch.setenv("PATH", os.defpath)
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


def screen(app: Humanize) -> str:
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
