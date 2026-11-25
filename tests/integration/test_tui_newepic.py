"""The New epic page and the epic's context, in the real interface, against the stand-in agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.daemon.link import Link
from hmz.runtime.epic import JOURNAL, epics
from hmz.tui import Humanize
from hmz.tui.monitoring import Entry
from hmz.tui.shell import Zone
from hmz.tui.views import newepic
from hmz.tui.views.newepic import NewEpic
from tests.integration.doubles_tui import (
    MODEL,
    OWN,
    SIZE,
    heard,
    on,
    onto,
    opened,
    own_flow,
    picks,
    rows,
    screen,
    shows,
    stand_in,
    tell,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

pytestmark = [pytest.mark.timeout(180)]

#: A flow of one agent role and one person, which takes a param: a turn on the task, what
#: came of it written down with the param beside it, and then the person asked, so that the
#: epic is still going -- with a board, and a role to hold -- for as long as the test reads it.
ASKS = """
from pathlib import Path

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    coder: Agent
    reviewer: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = 1


@flow(agents=Agents, envs=Envs, params=Params)
async def writes(task: str, *, agents: Agents, envs: Envs, params: Params,
                 ctx: FlowContext) -> None:
    \"\"\"Takes one turn on the task, writes down what came of it, and asks.\"\"\"
    coder, reviewer = agents["coder"], agents["reviewer"]
    session = await coder.spawn()
    said = await coder.run(task, session=session, env=envs["workspace"])
    Path("said.txt").write_text(f"{params.rounds}: {said}\\n")
    await reviewer.run("Is that all?", session=await reviewer.spawn())
"""

#: The rows of the page the test writes, as the page puts them up.
TASK, COST = "\x1etask", "\x1ecost"
CODER, ROUNDS = "\x1eagent\x1ecoder", "\x1eparam\x1erounds"


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None, daemon: object
) -> Path:
    """The stand-in `claude` on `PATH`, and a flow of the workspace's own to start.

    Over a daemon of this process, so that the side question's session outlives no test.
    """
    del asking, daemon
    at = stand_in(tmp_path, monkeypatch)
    own_flow(at, ASKS)
    return at


async def _writes(pilot: Pilot[None], row: str, said: str) -> None:
    await onto(pilot, row)
    await pilot.press(*said, "enter")
    await pilot.pause()


def _boards(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Takes what the interface asks of a board, which no run of this checkout keeps yet."""
    asked: list[dict[str, Any]] = []
    real = Link.asked

    def taken(
        link: Link, said: dict[str, Any], *, seconds: float | None = None
    ) -> dict[str, Any]:
        if said.get("do") != "board":
            return real(link, said, seconds=seconds)
        asked.append(dict(said))
        return {"ok": True}

    monkeypatch.setattr(Link, "asked", taken)
    return asked


async def test_ctrl_e_sets_an_epic_up_on_one_page_and_ctrl_o_reads_it_beside_its_log(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boarded = _boards(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await until(pilot, lambda: "^E New epic" in screen(app), "the hint line")

        await pilot.press("ctrl+e")
        await until(pilot, lambda: isinstance(app.screen, NewEpic), "the page")
        await until(pilot, lambda: CODER in rows(app), "the flow's rows")
        said = await shows(pilot, "New epic", OWN, "ENVIRONMENT", "AGENTS", "BUDGET")
        assert "PARAMETERS" in said
        assert "Pick a nous" in said

        # Nothing starts on half an answer: what is missing is said on its row.
        await pilot.press("ctrl+s")
        await shows(pilot, "Describe the task", "Pick an agent for coder.")

        await _writes(pilot, TASK, "say hello")
        await picks(pilot, CODER, f"claude/{MODEL}:auto")
        await _writes(pilot, ROUNDS, "3")
        await _writes(pilot, COST, "1")
        await pilot.press("ctrl+s")

        await until(pilot, lambda: not isinstance(app.screen, NewEpic), "it to start")
        await until(pilot, (workspace / "said.txt").exists, "the turn")
        assert (workspace / "said.txt").read_text().startswith("3: ")
        await shows(pilot, "Is that all?")

        # Beside the log, the epic that is open: how it stands, on the first tab.
        context = app.query_one("#context", Zone)
        await pilot.press("ctrl+o")
        await until(pilot, lambda: context.has_class("open"), "the epic's context")
        said = await shows(pilot, "EPIC", "1 DETAILS", "Running", OWN, "say hello")
        assert "esc Back" in said

        # The board: a line written on it is a line the runs then say.
        await pilot.press("2")
        await shows(pilot, "This flow keeps no board.")
        tell(app, {"type": "board", "items": []})
        await shows(pilot, "Nothing is on the board yet.", "A Add")
        await pilot.press("a")
        await on(pilot, Entry)
        await pilot.press(*"plan", "enter", *"ship", "enter")
        await until(pilot, lambda: len(boarded) > 0, "the runs to be asked")
        assert boarded == [{"do": "board", "key": "plan", "value": "ship"}]
        tell(app, {"type": "board", "items": [{"key": "plan", "value": "ship"}]})
        await shows(pilot, "plan", "ship", "enter Edit", "D Remove")

        # The people: the role is anybody's, then this interface's, then anybody's again.
        await pilot.press("3")
        await shows(pilot, "reviewer", "Anyone", "enter Claim", "shift+W Away for all")
        await pilot.press("enter")
        await shows(pilot, "You", "enter Release")
        await pilot.press("enter")
        await shows(pilot, "Anyone", "enter Claim")

        # A side question is asked of the coder's session, beside the epic and not of it.
        await pilot.press("4")
        await shows(pilot, "No side question yet", "A New aside")
        await pilot.press("a")
        await until(pilot, lambda: len(app.screen_stack) == 2, "the question")
        await pilot.press("enter")
        await until(pilot, lambda: len(app.screen_stack) == 3, "the sessions")
        await pilot.press("enter")
        await until(pilot, lambda: len(app.screen_stack) == 2, "one picked")
        await pilot.press(*"how far", "enter", "enter")
        await until(pilot, lambda: len(app.screen_stack) == 1, "it asked")
        await shows(pilot, "btw ·", "heard how far", "D Close")
        assert heard(workspace).count("say hello") == 1
        # Closed, it is gone from the list, and its session with it.
        await pilot.press("d")
        await shows(pilot, "Close the side question with")
        await pilot.press("enter")
        await shows(pilot, "No side question yet")
        await pilot.press("3")
        await shows(pilot, "reviewer", "enter Claim")

        # Left and come back to, it is where it was left.
        await pilot.press("ctrl+o")
        await until(pilot, lambda: not context.has_class("open"), "it to close")
        await pilot.press("ctrl+o")
        await shows(pilot, "reviewer", "enter Claim")
        await pilot.press("escape")
        await until(
            pilot, lambda: getattr(app.focused, "id", "") == "editor", "the prompt"
        )

        # The folder remembers the set-up: the page opens holding it, but for the task.
        await pilot.press("ctrl+e")
        await until(pilot, lambda: isinstance(app.screen, NewEpic), "the page")
        await until(pilot, lambda: CODER in rows(app), "the flow's rows")
        await shows(pilot, f"claude/{MODEL}:auto")
        await pilot.press("ctrl+s")
        await shows(pilot, "Describe the task")
        await _writes(pilot, TASK, "again")
        await pilot.press("ctrl+s")
        await shows(pilot, "An epic is already running here")
        # The key that opened the page closes it, and over the monitor the key is the monitor's.
        await pilot.press("ctrl+e")
        await until(pilot, lambda: not isinstance(app.screen, NewEpic), "it to close")
        assert len(app.screen_stack) == 1

        # Stopped, so that no host of it outlives the test waiting to be answered.
        await typed(pilot, "/stop")
        await shows(pilot, "topping the flow")
        await until(
            pilot,
            lambda: any(
                '"ended"' in (epic / JOURNAL).read_text() for epic in epics(workspace)
            ),
            "the run to end",
        )


async def test_the_page_opens_on_the_folder_it_is_asked_for(
    workspace: Path, tmp_path: Path
) -> None:
    del workspace
    other = tmp_path / "elsewhere"
    other.mkdir()
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)

        await newepic.opens(app, folder=str(other))

        # On that folder, which has no flow of its own as the interface's has.
        await on(pilot, NewEpic)
        await shows(pilot, "New epic", "No flow installed yet.")
        assert OWN not in screen(app)
