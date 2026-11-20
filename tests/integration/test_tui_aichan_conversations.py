"""`/ai`: Ai-chan's conversations, made, followed as a chat, carried on and forgotten.

`aichan.*` is answered by the test's own daemon as any daemon answers it -- a host of its own
slot, `ai:<hex>`, its task the first message -- whose host runs a stand-in for the flow
`ai_chan` that talks to the stand-in agent as a chat does: what is under test is the
interface, which reads her conversation as it reads any chat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from textual.widgets import OptionList

from hmz.daemon import reach
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import Acts, AiChanNew, AiChans, AiForgets
from tests.integration.doubles_tui import (
    MODEL,
    OWN,
    RUNS,
    SIZE,
    heard,
    on,
    onto,
    opened,
    own_flow,
    picks,
    screen,
    set_up_own_flow,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.daemon.private import Private


#: Stands in for the flow `ai_chan`: the stand-in agent talking to the person, every line said
#: back its next turn, as `TALK` of the interface's own tests does.
_AI_CHAN = """
import contextlib

from hmz.flows import (
    Agent, AgentCollection, AskUserHookAgentMixin, AskUserHookResult, CapabilityNotGranted,
    EnvCollection, FlowParams, LocalEnv, Outworlder, flow,
)


class Her(Agent, AskUserHookAgentMixin):
    pass


class Agents(AgentCollection):
    ai_chan: Her
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    id: int = 0
    scope: str = ""
    workspace: str = ""
    epic: str = ""
    preset: str = ""
    network: bool = False


@flow(agents=Agents, envs=Envs, params=Params, name="ai_chan", resumable=True)
async def ai_chan(task, *, agents, envs, params, ctx):
    her, human = agents["ai_chan"], agents["human"]
    talk, person = await her.spawn(), await human.spawn()

    async def asked(params):
        said = await human.run(params.question, session=person)
        return AskUserHookResult(answer=said or None)

    with contextlib.suppress(CapabilityNotGranted):
        her.on_ask_user(asked)
    said = task
    while said:
        answered = await her.run(said, session=talk, env=envs["workspace"])
        said = await human.run(answered, session=person)
"""


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None, daemon: Private
) -> Path:
    """The stand-in `claude` on `PATH`, the `ai_chan` setting naming it, and her flow.

    The daemon's `aichan.*` is its own; the flow her host runs is the stand-in above.
    """
    del asking, daemon
    here = stand_in(tmp_path, monkeypatch)
    Settings().ai_chan = RUNS
    flow = tmp_path / "fakes" / "ai_chan"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_AI_CHAN)
    monkeypatch.setattr(reach, "FLOW", str(flow))
    return here


#: What the interface marks a line the person said with.
_YOURS = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"

#: What a conversation is kept with that the interface chose.
_KEPT = ("id", "title", "scope", "workspace", "epic", "nous", "preset", "network")


def _made(daemon: Private) -> list[dict[str, Any]]:
    """Each conversation the daemon keeps, as it keeps it."""
    return daemon.links.kept.all()


async def _new(pilot: Pilot[None]) -> AiChanNew:
    """Opens `/ai` and its New form."""
    await typed(pilot, "/ai")
    await on(pilot, AiChans)
    await shows(pilot, "New")
    await onto(pilot, "new")
    await pilot.press("enter")
    return await on(pilot, AiChanNew)


async def _done(pilot: Pilot[None]) -> None:
    """Answers the form on the screen, leaving the log screen waiting on the conversation."""
    app = pilot.app
    await pilot.click("#act-done")
    await until(pilot, lambda: len(app.screen_stack) == 1, "the log screen")


async def test_new_asks_the_scope_nous_and_permission_and_the_first_line_makes_it(
    workspace: Path, daemon: Private
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await _new(pilot)
        # Nothing has been run here, so the scope is this directory; the nous the setting.
        await shows(pilot, "scope", "workspace", "nous", RUNS, "read-only", "off")
        await _done(pilot)
        await shows(pilot, "Ai-chan · new · workspace", "Ai-chan: the next line")
        assert _made(daemon) == []

        await typed(pilot, "hello there")

        await shows(pilot, "heard hello there", "Ai-chan#1 · workspace")
        await typed(pilot, "go on")
        await shows(pilot, "heard go on", "◉ done")

    (made,) = _made(daemon)
    assert {key: made[key] for key in _KEPT} == {
        "id": 1,
        "title": "hello there",
        "scope": "workspace",
        "workspace": str(app.hmz.workspace),
        "epic": "",
        "nous": RUNS,
        "preset": "read-only",
        "network": False,
    }
    assert heard(workspace) == ["hello there", "go on"]


async def test_every_line_said_to_her_is_drawn_before_what_she_answers_it(
    workspace: Path,
) -> None:
    del workspace
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await _new(pilot)
        await _done(pilot)
        await typed(pilot, "hello there")
        await shows(pilot, "heard hello there")

        # Her next turn, which answers what her flow waits on.
        await typed(pilot, "go on")
        drawn = await shows(pilot, f"{_YOURS} go on", "heard go on")
        assert drawn.index(f"{_YOURS} go on") < drawn.index("heard go on")

        # And a word put into the turn she is taking.
        await typed(pilot, "wait here")
        await shows(pilot, "still on it")
        await typed(pilot, "more words")
        drawn = await shows(
            pilot, f"{_YOURS} more words", "heard wait here then more words"
        )
        # Each of them once: the first line is drawn as it is typed, the rest as her host
        # says them.
        for line in ("hello there", "go on", "wait here", "more words"):
            assert drawn.count(f"{_YOURS} {line}") == 1

        # And as it is told from its start, to an interface that reads it again.
        await typed(pilot, "/clear")
        await until(pilot, lambda: "Ai-chan#1" not in screen(app), "her to be left")
        await typed(pilot, "/ai")
        await on(pilot, AiChans)
        await onto(pilot, "1")
        await pilot.press("enter")
        drawn = await shows(pilot, "heard go on", "Ai-chan#1 \N{MIDDLE DOT} workspace")
        assert drawn.index(f"{_YOURS} go on") < drawn.index("heard go on")


async def test_the_scope_defaults_to_the_epic_last_on_the_host_and_takes_the_daemon(
    workspace: Path, daemon: Private
) -> None:
    own_flow(workspace)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        # A chat is no epic, and a conversation made over one is the workspace's.
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "heard hello")
        form = await _new(pilot)
        assert form.shown(form.asked()[0]) == "workspace"
        await pilot.press("escape")

        await set_up_own_flow(pilot)
        await typed(pilot, f"${OWN} make it so")
        await shows(pilot, "the flow is done")

        form = await _new(pilot)
        # The flow just run is the epic last on the host followed.
        assert form.shown(form.asked()[0]) == "epic"
        await shows(pilot, "the epic ")
        await picks(pilot, "scope", "daemon")
        await picks(pilot, "preset", "danger-full-access")
        await picks(pilot, "network", "on")
        await shows(pilot, "every workspace and epic of this daemon")
        await _done(pilot)
        await typed(pilot, "look around")
        await shows(pilot, "heard look around", "Ai-chan#1 · daemon")

    (made,) = _made(daemon)
    assert {key: made[key] for key in _KEPT} == {
        "id": 1,
        "title": "look around",
        "scope": "daemon",
        "workspace": str(daemon.links.kept.at.resolve()),
        "epic": "",
        "nous": RUNS,
        "preset": "danger-full-access",
        "network": True,
    }


async def test_her_tools_are_shown_and_btw_and_stop_are_hers(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await _new(pilot)
        await _done(pilot)
        # Details are off, and every tool she calls is still shown.
        await typed(pilot, "tools")
        await shows(pilot, "Bash(foo\\ bar)", "heard tools", "◉ done")

        await typed(pilot, "/btw what is she doing")
        await shows(pilot, "not on Ai-chan's", "/ai asks Ai-chan")
        await typed(pilot, "/stop")
        await shows(pilot, "Ai-chan is not answering, so there is nothing to stop")

        # And /clear leaves her to her host, for this directory's own.
        await typed(pilot, "/clear")
        await until(pilot, lambda: "Ai-chan#1" not in screen(app), "her to be left")


async def test_a_conversation_is_carried_on_from_the_list_and_forgotten_there(
    workspace: Path, daemon: Private
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await _new(pilot)
        await _done(pilot)
        await typed(pilot, "hello there")
        await shows(pilot, "heard hello there")
        await typed(pilot, "/clear")
        await until(pilot, lambda: "Ai-chan#1" not in screen(app), "her to be left")

        await typed(pilot, "/ai")
        await on(pilot, AiChans)
        await shows(pilot, "Ai-chan#1 · hello there", "between turns")
        await onto(pilot, "1")
        await pilot.press("enter")
        await shows(pilot, "heard hello there", "Ai-chan#1 · workspace")
        await typed(pilot, "and again")
        await shows(pilot, "heard and again")

        await typed(pilot, "/ai")
        await on(pilot, AiChans)
        await onto(pilot, "1")
        await pilot.press("m")
        await on(pilot, Acts)
        await pilot.press("enter")
        await on(pilot, AiForgets)
        await shows(pilot, "Forget Ai-chan#1?")
        await pilot.press("enter")
        await on(pilot, AiChans)
        await shows(pilot, "no conversation yet")
    assert _made(daemon) == []
    assert heard(workspace)[-1] == "and again"



async def _names(pilot: Pilot[None], nous: str) -> None:
    """Writes the nous of the New form on the screen, which asks for one where none was used."""
    pilot.app.screen.query_one("#choices", OptionList).focus()
    await onto(pilot, "nous")
    await pilot.press("enter", *nous, "enter")
    await pilot.pause()


async def test_the_next_form_opens_on_the_nous_the_last_conversation_was_made_with(
    workspace: Path, daemon: Private
) -> None:
    del workspace
    # No conversation was made yet: the setting names no nous, and the form asks for one.
    Settings().ai_chan = ""
    other = f"claude/{MODEL}:low"
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        form = await _new(pilot)
        assert form.asked()[1].needed
        await _names(pilot, other)
        assert form.shown(form.asked()[1]) == other
        await _done(pilot)
        await typed(pilot, "hello there")
        await shows(pilot, "heard hello there", "Ai-chan#1")
        await typed(pilot, "/clear")
        await until(pilot, lambda: "Ai-chan#1" not in screen(app), "her to be left")

        # Made with it, it is the nous last used: the next form opens on it.
        form = await _new(pilot)
        assert form.shown(form.asked()[1]) == other
        assert not form.asked()[1].needed

    assert [one["nous"] for one in _made(daemon)] == [other]
    assert Settings().ai_chan == other


async def test_a_nous_the_daemon_refused_is_not_the_one_the_next_form_opens_on(
    workspace: Path, daemon: Private
) -> None:
    del workspace
    Settings().ai_chan = ""
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await _new(pilot)
        await _names(pilot, "no/such nous")
        await _done(pilot)
        await typed(pilot, "hello there")
        await shows(pilot, "no/such nous is not a nous or an agent spec.")
        await typed(pilot, "/clear")

        # Nothing was made with it: the form still asks which nous she thinks with.
        form = await _new(pilot)
        assert form.shown(form.asked()[1]) == ""
        assert form.asked()[1].needed

    assert _made(daemon) == []
    assert Settings().ai_chan == ""
