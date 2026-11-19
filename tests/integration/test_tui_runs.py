"""A run from the prompt: a line becomes a turn, and the run is steered, cut off and stopped."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Literal, cast

import pytest
from pydantic import BaseModel, Field

from hmz import daemon as daemons
from hmz.runtime import Hmz
from hmz.runtime.epic import JOURNAL, epics
from hmz.runtime.kept import Runs
from hmz.tui import Humanize
from hmz.tui.asking import Asks
from hmz.tui.flows import Flows
from hmz.tui.pick import STOPS, Leaves
from tests.integration.doubles_tui import (
    MODEL,
    OWN,
    RUNS,
    SIZE,
    TALKS,
    Answers,
    gives_a_budget,
    heard,
    leaves,
    on,
    opened,
    own_flow,
    screen,
    set_up_own_flow,
    shows,
    stand_in,
    started,
    talks_set_up,
    tell,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, really asked what it runs as the interface opens."""
    del asking
    workspace = stand_in(tmp_path, monkeypatch)
    talks_set_up(workspace)
    return workspace


#: A flow that asks the person something of its own between two turns of its one agent: a
#: question that is part of no conversation, put as `@local/writes` so that `/flow` sets it up.
ASKS = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    coder: Agent
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def writes(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
                 ctx: FlowContext) -> None:
    coder, human = agents["coder"], agents["human"]
    session = await coder.spawn()
    said = await coder.run(task, session=session, env=envs["workspace"])
    answer = await human.run(f"Ship {said}?", session=await human.spawn())
    await coder.run(answer, session=session, env=envs["workspace"])
"""


def ended(workspace: Path) -> str:
    """How the one run in the workspace ended, as its record says, or "" while it has not."""
    (epic,) = epics(workspace)
    said = [json.loads(one) for one in (epic / JOURNAL).read_text().splitlines()]
    return next((str(one["how"]) for one in said if one.get("event") == "ended"), "")


async def test_a_line_is_the_task_and_the_agent_s_answer_is_drawn(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")

        drawn = await shows(pilot, "heard hello", "◉ done")

    assert "❯ hello" in drawn
    (argv,) = started(workspace)
    assert argv[argv.index("--model") + 1] == MODEL
    assert argv[argv.index("--effort") + 1] == "high"
    assert heard(workspace) == ["hello"]


async def test_every_line_after_the_first_is_a_turn_of_the_same_conversation(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "first")
        await shows(pilot, "heard first")
        await typed(pilot, "second")
        drawn = await shows(pilot, "heard second")

    # Every line said is in the conversation, once.
    assert drawn.count("❯ second") == 1
    assert heard(workspace) == ["first", "second"]
    assert len(started(workspace)) == 1  # one agent process, holding one conversation


async def test_a_line_typed_while_a_turn_runs_is_put_into_that_turn(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for more")
        await shows(pilot, "still on it")

        await typed(pilot, "and this")

        await shows(pilot, "heard wait for more then and this")

    assert heard(workspace) == ["wait for more", "and this"]


async def test_two_ctrl_c_cut_the_turn_off_and_end_the_run_as_stopped(
    workspace: Path,
) -> None:
    app = Humanize(flow=TALKS)
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, f"/flow {TALKS} wait forever")
        await shows(pilot, "still on it")

        await pilot.press("ctrl+c")
        await shows(pilot, "press ctrl+c again to stop the flow")
        assert "stopping the flow" not in screen(app)

        await pilot.press("ctrl+c")
        await shows(pilot, "stopping the flow", "turn cut off")
        await until(pilot, lambda: ended(workspace) == "stopped", "the run to end")
        assert app.is_running  # the interface stays, for the next run


async def test_stop_ends_a_run_waiting_on_you_without_asking(workspace: Path) -> None:
    async with Humanize(flow=TALKS).run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, f"/flow {TALKS} hello")
        await shows(pilot, "waiting for you")

        await typed(pilot, "/stop")

        await shows(pilot, "stopping the flow")
        await until(pilot, lambda: ended(workspace) == "stopped", "the run to end")


async def test_a_flow_that_will_not_load_is_said_and_the_interface_stays(
    workspace: Path,
) -> None:
    flow = workspace / "broken"
    flow.mkdir()
    (flow / "__init__.py").write_text('raise FileNotFoundError("no prompt.md here")\n')

    app = Humanize(flow=str(flow), agents={"coder": Runs(RUNS)})
    async with app.run_test(size=SIZE) as pilot:
        await typed(pilot, f"/flow {flow} do it")

        await shows(pilot, "prompt.md")
        assert app.is_running
    assert started(workspace) == []


async def test_exit_while_a_run_is_going_asks_and_stopping_it_ends_both(
    workspace: Path,
) -> None:
    app = Humanize(flow=TALKS)
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, f"/flow {TALKS} wait a while")
        await shows(pilot, "still on it")

        await typed(pilot, "/exit")
        await on(pilot, Leaves)
        await shows(
            pilot, "A flow is running.", "Stop the flow and exit", "Detach and exit"
        )
        await pilot.click(f"#act-{STOPS}")

        await until(pilot, lambda: not app.is_running, "the interface to close")
    assert ended(workspace) == "stopped"


async def test_a_line_typed_reading_the_conversation_between_turns_is_its_next_turn(
    workspace: Path,
) -> None:
    async with Humanize(flow=TALKS).run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, f"/flow {TALKS} wait first")
        # Read already: a run lands on the agent of the first conversation it opens.
        await shows(pilot, "still on it", "─ reading ")
        await typed(pilot, "more")
        await shows(pilot, "heard wait first then more")

        await typed(pilot, "second")

        await shows(pilot, "heard second")
    assert heard(workspace) == ["wait first", "more", "second"]


async def test_what_the_agent_stops_to_ask_is_shown_and_answered_in_its_conversation(
    workspace: Path,
) -> None:
    async with Humanize(flow=TALKS).run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, f"/flow {TALKS} ask me")
        await shows(pilot, "─ reading ", "Which colour? (red / blue)", "type an answer")

        await typed(pilot, "blue")

        drawn = await shows(pilot, "picked blue")
    assert "❯ blue" in drawn


async def test_a_question_the_flow_asks_of_its_own_is_shown_and_answered_where_you_read(
    workspace: Path,
) -> None:
    own_flow(workspace, ASKS)
    async with Humanize().run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, f"${OWN} make it so")

        # Landed on the agent of the run's first conversation, with no view of every agent,
        # and the question put where it is read rather than on a transcript nobody reads.
        drawn = await shows(
            pilot,
            "─ reading ",
            "❯ make it so",
            "Ship heard make it so?",
            "type an answer",
        )
        assert "all agents" not in drawn
        await typed(pilot, "yes")

        await shows(pilot, "heard yes", "the flow is done")
    assert heard(workspace) == ["make it so", "yes"]


class Review(BaseModel):
    """What a person says of a change, asked as one form."""

    verdict: Literal["approve", "request changes", "reject"] = Field(
        description="what to do with the change"
    )
    notes: str = Field(description="what to change, or why")
    tests: bool = Field(default=True, description="Write tests.")


#: The change the form is about.
PATCH = """\
diff --git a/parse.py b/parse.py
--- a/parse.py
+++ b/parse.py
@@ -1,2 +1,3 @@
-def parse(s): return s
+def parse(s):
+    return s.strip()
 # end
"""


def asked_as_form(question: str = "q1") -> dict[str, Any]:
    """A question asked as a form, with a diff and a table, as the host says it."""
    return {
        "type": "asked",
        "run": 1,
        "question": question,
        "role": "human",
        "mode": "ask",
        "options": [],
        "key": "",
        "text": "Ship the parser change?\nIt changes how **every** line is read.",
        "schema": Review.model_json_schema(),
        "context": [
            {"kind": "diff", "title": "the change", "patch": PATCH},
            {
                "kind": "table",
                "columns": ["test", "result"],
                "rows": [["parses", "pass"], ["strips", "fail"]],
            },
        ],
        "face": None,
        "session": "human/1",
    }


def pending(*asked: dict[str, Any]) -> dict[str, Any]:
    """The `pending` snapshot of some questions, nobody holding their role."""
    return {
        "type": "pending",
        "pending": [
            {**{key: said for key, said in one.items() if key != "type"}, "owner": None}
            for one in asked
        ],
    }


def running(app: Humanize) -> None:
    """Tells the interface a flow is running, with one outworlder, `human`."""
    tell(
        app,
        {
            "type": "run",
            "state": "running",
            "run": 1,
            "kind": "flow",
            "flow": "review",
            "task": "review the parser",
            "began": 0.0,
            "outworlders": ["human"],
            "epic": "",
        },
    )


def short_notes(sent: dict[str, Any]) -> list[dict[str, Any]]:
    """Refuses notes of fewer than three letters, as a schema's own check would."""
    notes = str(cast("dict[str, Any]", sent.get("value") or {}).get("notes") or "")
    if len(notes) < 3:
        return [{"path": ["notes"], "message": "say what to change"}]
    return []


async def test_a_question_asked_as_a_form_is_read_then_answered_on_its_sheet(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del workspace
    answers = Answers(short_notes).install(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        running(app)
        record = asked_as_form()
        tell(app, record)
        tell(app, pending(record))
        await pilot.pause()

        # Read first: the prompt, the change and the table, then the form -- not opened.
        drawn = await shows(
            pilot,
            "Ship the parser change?",
            "the change · diff · +2 \N{MINUS SIGN}1 in 1 file",
            "table · 2 rows",
            "form · 3 fields \N{EM DASH} press Enter to open",
        )
        assert "return s.strip()" in drawn
        assert not isinstance(app.screen, Asks)

        await pilot.press("enter")
        sheet = await on(pilot, Asks)
        await shows(
            pilot,
            "Verdict",
            "1 approve",
            "3 reject",
            "More options (1)",
            "Answer · 2 required left",
        )
        await pilot.press("2", "enter", "x", "enter", "enter")

        # Refused beside the field it is about, and the sheet stays up with what was typed.
        await shows(pilot, "✗ say what to change")
        assert app.screen is sheet

        await pilot.press("backspace", *"needs tests", "enter", "enter")
        await until(
            pilot, lambda: not isinstance(app.screen, Asks), "the sheet to close"
        )
        value = answers.sent[-1]["value"]
        tell(
            app,
            {
                "type": "answered",
                "question": "q1",
                "role": "human",
                "text": json.dumps(value),
                "value": value,
            },
        )
        tell(app, pending())
        await shows(pilot, "❯ request changes · 'needs tests' · Yes, write tests")

    assert answers.sent == [
        {
            "question": "q1",
            "value": {"verdict": "request changes", "notes": "x", "tests": True},
        },
        {
            "question": "q1",
            "value": {
                "verdict": "request changes",
                "notes": "needs tests",
                "tests": True,
            },
        },
    ]


async def test_esc_keeps_the_form_s_draft_and_words_typed_go_into_it(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del workspace
    answers = Answers(lambda _: []).install(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        running(app)
        record = asked_as_form()
        tell(app, record)
        tell(app, pending(record))
        await shows(pilot, "press Enter to open")

        # Words typed at the prompt open the form with them in the field they answer.
        await typed(pilot, "looks fine")
        await on(pilot, Asks)
        await shows(pilot, "looks fine", "Answer · 1 required left")
        await pilot.press("1", "escape")
        await until(
            pilot, lambda: not isinstance(app.screen, Asks), "the sheet to close"
        )

        await pilot.press("enter")
        await on(pilot, Asks)
        drawn = await shows(pilot, "looks fine", "Answer")
        assert "required left" not in drawn
    assert answers.sent == []


async def test_json_typed_at_a_form_is_its_answer_and_a_choice_s_number_opens_it(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del workspace
    answers = Answers(lambda _: []).install(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        running(app)
        record = asked_as_form()
        tell(app, record)
        tell(app, pending(record))
        await shows(pilot, "press Enter to open")

        await typed(pilot, "1")
        await on(pilot, Asks)
        await shows(pilot, "Answer · 1 required left")
        await pilot.press("escape")
        await until(
            pilot, lambda: not isinstance(app.screen, Asks), "the sheet to close"
        )

        await typed(pilot, '{"verdict": "approve", "notes": "ok"}')
        await until(pilot, lambda: bool(answers.sent), "the answer to be sent")
    assert answers.sent == [
        {"question": "q1", "value": {"verdict": "approve", "notes": "ok"}}
    ]


async def test_a_form_withdrawn_while_open_comes_down_saying_why(
    workspace: Path,
) -> None:
    del workspace
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        running(app)
        record = asked_as_form()
        tell(app, record)
        tell(app, pending(record))
        await shows(pilot, "press Enter to open")
        await pilot.press("enter")
        await on(pilot, Asks)

        tell(app, {"type": "withdrawn", "question": "q1", "why": "the run ended"})
        tell(app, pending())

        await until(
            pilot, lambda: not isinstance(app.screen, Asks), "the sheet to close"
        )
        await shows(pilot, "withdrawn: the run ended")


async def test_a_form_held_by_another_frontend_waits_for_it(workspace: Path) -> None:
    del workspace
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        tell(app, {"type": "clients", "clients": [{"client": "c9", "name": "web"}]})
        tell(app, {"type": "claims", "claims": {"human": "c9"}})
        tell(app, {**asked_as_form(), "face": {"hash": "ab12", "title": "review"}})

        drawn = await shows(
            pilot,
            "Waiting for web",
            "a richer view of this question is in the web page",
        )
        assert "press Enter to open" not in drawn


async def test_what_an_outworlder_is_shown_is_on_its_own_transcript(
    workspace: Path,
) -> None:
    own_flow(workspace, ASKS)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, f"${OWN} make it so")
        await shows(pilot, "Ship heard make it so?")
        tell(
            app,
            {
                "type": "shown",
                "run": 1,
                "role": "human",
                "session": "human/1",
                "context": [{"kind": "markdown", "text": "**3 of 5** tests pass"}],
            },
        )
        await pilot.pause()
        assert "3 of 5" not in screen(app)  # not on the transcript being read

        await pilot.press("tab")
        await shows(pilot, "human was shown", "3 of 5 tests pass")


async def test_flow_opens_on_the_roles_of_an_epic_another_frontend_started(
    workspace: Path,
) -> None:
    own_flow(workspace, ASKS)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        # Started elsewhere: this interface is set up on no flow, and follows the epic.
        link = daemons.attach("sdk", "other", workspace=workspace)
        try:
            await asyncio.to_thread(
                link.start,
                OWN,
                "make it so",
                agents={"coder": RUNS},
                budget={"cost": 1.0},
            )
            await shows(pilot, "Ship heard make it so?")

            await typed(pilot, "/flow")
            await on(pilot, Flows)
            drawn = await shows(pilot, OWN, "coder")
            assert "failed to load" not in drawn

            # Saved under that flow's name, for the next epic of it.
            await gives_a_budget(pilot)
            await leaves(pilot)
            await shows(pilot, "changes will apply to the next epic")
        finally:
            link.close()
    assert Hmz(workspace).settings.flow == OWN
