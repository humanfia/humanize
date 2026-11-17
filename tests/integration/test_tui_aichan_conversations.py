"""`/ai`: Ai-chan's conversations, made, followed as a chat, carried on and forgotten.

`aichan.*` is answered by the test's own daemon as any daemon answers it -- a host of its own
slot, `ai:<hex>`, its task the first message -- whose host runs a stand-in for the flow
`ai_chan` that talks to the stand-in agent as a chat does: what is under test is the
interface, which reads her conversation as it reads any chat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.daemon import reach
from hmz.runtime import flowing
from hmz.runtime.flowing import finding
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import Acts, AiChanNew, AiChans, AiForgets
from tests.integration.doubles_tui import (
    RUNS,
    SIZE,
    heard,
    on,
    onto,
    opened,
    picks,
    screen,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.daemon.private import Private


#: Stands in for the flow `ai_chan`: a chat with her, as Humanize's `chat` has with its agent.
_AI_CHAN = """
from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, Outworlder, flow,
)


class Agents(AgentCollection):
    ai_chan: Agent
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

    The daemon's `aichan.*` is its own; the flow her host runs is the stand-in above, held
    as a chat is, which is how the interface reads her conversation.
    """
    del asking, daemon
    here = stand_in(tmp_path, monkeypatch)
    Settings().ai_chan = RUNS
    flow = tmp_path / "fakes" / "ai_chan"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_AI_CHAN)
    monkeypatch.setattr(reach, "FLOW", str(flow))
    was = finding.privileged

    def chats(impl: Any) -> bool:
        return was(impl) or impl.name == "ai_chan"

    monkeypatch.setattr(finding, "privileged", chats)
    monkeypatch.setattr(flowing, "privileged", chats)
    return here


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


async def test_the_scope_defaults_to_the_epic_last_on_the_host_and_takes_the_daemon(
    workspace: Path, daemon: Private
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "heard hello")

        form = await _new(pilot)
        # The chat just had is the epic last on the host followed.
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
