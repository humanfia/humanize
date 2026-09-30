"""The roles of a flow, each set up on the page the flow's roles are on.

Every agent role is a sheet of rows: the CLI that takes its turns, the account they run as,
and the model at an effort. Which is the point: an agent is one thing rather than three
questions, and changing the effort of one already set up is a row and an arrow rather than a
walk through two sheets that had nothing to say. An environment role is a row of its own,
where the place it works is said the way `-e` says it; the roles the runtime fills -- the
person outside the run, the workspace it was started in -- are nobody's to choose, and are no
row at all.

Driven headlessly, as every test of the interface is, so what is checked is where a keystroke
lands rather than how it is drawn.
"""

from __future__ import annotations

import datetime
import unittest.mock
from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import Label, OptionList

from hmz.coganchor.backends import Model
from hmz.flows import Budget
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import (
    _AGAIN,
    _BUDGET,
    _DONE,
    _HARNESS,
    _SAVE,
    Agent,
    Catalogue,
    Clis,
    Configures,
    Confirms,
    Flows,
    Placing,
)
from tests.integration.tui.test_app import (
    changes,
    drops,
    into_agent,
    keeps,
    onto,
    opens,
    rows,
)
from tests.stubs import written
from tests.tui.fixtures import set_up, transcript, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: What one installed CLI looks like, for every sheet here.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}

#: A flow of one agent role, working in the workspace it was started in -- which is a role the
#: runtime fills, and so no row -- and talking to whoever is outside it, which is another.
HERE = '''
"""One agent, working where the flow is."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    """Just the one, and the person."""

    builder: Agent
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def here(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
               ctx: FlowContext) -> None:
    pass
'''

#: A flow with an environment of its own, which somebody says the place of.
PLACED = '''
"""One agent, working in a place somebody names."""

from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowContext, FlowParams
from hmz.flows import ShellEnvMixin, flow


class Repo(Env, ShellEnvMixin): ...


class Agents(AgentCollection):
    """Just the one."""

    builder: Agent


class Envs(EnvCollection):
    repo: Repo


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def placed(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
                 ctx: FlowContext) -> None:
    pass
'''

#: Two agent roles, which is a sheet apiece.
PAIR = '''
"""Two agents."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, flow


class Agents(AgentCollection):
    """One writes, one reads."""

    builder: Agent
    reviewer: Agent


@flow(agents=Agents, envs=EnvCollection, params=FlowParams)
async def pair(task: str, *, agents: Agents, envs: EnvCollection, params: FlowParams,
               ctx: FlowContext) -> None:
    pass
'''


@pytest.fixture
def flows(tmp_path: Path) -> Path:
    """Puts the flows where this project's own would be."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(where, "here", HERE)
    written(where, "placed", PLACED)
    written(where, "pair", PAIR)
    return where


def _asked(app: Humanize) -> str:
    """What the sheet on top is asking, which says which agent it is asking about."""
    return str(app.screen.query_one("#asked", Label).content)


def _value(app: Humanize, held: str) -> str:
    """What one row of the sheet on top is set to, as it is drawn."""
    listing = app.screen.query_one("#choices", OptionList)
    return str(listing.get_option_at_index(rows(app).index(held)).prompt)


def _said(app: Humanize) -> str:
    """What the sheet on top says under its list."""
    return str(app.screen.query_one("#tuning", Label).content)


async def _open(app: Humanize, driver: Pilot[None], flow: str) -> None:
    """Opens the flow menu on one flow -- which is inside it -- and then one of its agents."""
    await driver.press(*f"/flow {flow}")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    await into_agent(app, driver)


async def _budgets(app: Humanize, driver: Pilot[None], duration: str) -> None:
    """Sets what a run may spend from its row on the roles page, as a duration."""
    await onto(app, driver, _BUDGET)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Configures), driver)
    await changes(app, driver, "duration", *duration)
    await onto(app, driver, _DONE)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_one_agent_is_one_sheet_of_rows_in_the_order_they_depend(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """The CLI settles the accounts and the models, so it comes above both of them."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "here")

        assert "builder" in _asked(app)
        # Four rows, and nothing else: what it may do and what it can are the flow's, where
        # it works is the environment's, and the skills it carries are its CLI's -- none of
        # them is the agent's to be asked about here.
        assert rows(app) == ["cli", "provider", "model", "effort", _SAVE]
        # The account nobody chose is always the first row of the list it is chosen from.
        assert "as local" in _value(app, "provider")


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_roles_the_runtime_fills_are_no_rows_of_the_menu(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """The person outside the run and the workspace it starts in are nobody's to choose."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow here")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        await until(lambda: sheet._inside, driver)

        # `builder` and nothing of `human` or `workspace`.
        assert rows(app) == ["0", _BUDGET, _HARNESS, _SAVE]
        assert "builder" in _value(app, "0")


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_two_agents_are_two_rows_and_a_sheet_apiece(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """Opening a flow lists its roles, by the name the flow calls each of them."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow pair")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        # A menu opened already naming a flow opens inside it: the flow has been named, so
        # what is left to answer is what drives it.
        await until(lambda: sheet._inside, driver)
        listing = sheet.query_one("#choices", OptionList)
        await until(lambda: len(listing.options) == 4, driver)

        assert rows(app) == ["0", "1", _BUDGET, _HARNESS, _SAVE]
        assert "builder" in str(listing.get_option_at_index(0).prompt)
        assert "reviewer" in str(listing.get_option_at_index(1).prompt)

        # And each is opened on its own, saying which one it is about.
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        assert "builder" in _asked(app)
        await drops(app, driver)

        await until(lambda: isinstance(app.screen, Flows), driver)
        await onto(app, driver, "1")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        assert "reviewer" in _asked(app)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_explicit_saves_accept_two_agents_then_apply_the_complete_flow(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
    tmp_path: Path,
) -> None:
    """A two-agent flow can be set up and saved without backing through either sheet."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "pair")
        await changes(app, driver, "effort", "left")

        await opens(app, driver, _SAVE)
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert rows(app) == ["0", "1", _BUDGET, _HARNESS, _SAVE]

        await onto(app, driver, "1")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        await opens(app, driver, _SAVE)
        await until(lambda: isinstance(app.screen, Flows), driver)

        await _budgets(app, driver, "1h")
        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    # The builder was stepped round from the effort it opened on, and the reviewer saved as
    # it opened.
    chosen = {
        "builder": Runs("claude/claude-opus-5:max"),
        "reviewer": Runs("claude/claude-opus-5:high"),
    }
    assert app._flow_named == "pair"
    assert app._models == chosen
    assert Settings(tmp_path).agents("pair") == chosen
    assert Settings(tmp_path).budget("pair")["duration"] == "PT1H"


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value={})
async def test_explicit_flow_save_refuses_an_agent_with_no_model(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """The save row uses the same completeness check as saving on the way out."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow here")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        if not sheet._inside:
            await driver.press("enter")
            await until(lambda: sheet._inside, driver)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await driver.pause()

        assert app.screen is sheet
        assert "builder is not configured yet" in _said(app)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_flow_is_not_saved_until_a_run_of_it_is_given_a_budget(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
    tmp_path: Path,
) -> None:
    """Only a flow humanize ships runs with none; every other is refused until it has one.

    And the budget is asked on the sheet a flow's params are asked on: a duration typed as
    `-b` takes one, and one that does not read is refused where it is typed.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow here")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        await until(lambda: sheet._inside, driver)
        assert "none set" in _value(app, _BUDGET)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await driver.pause()
        assert app.screen is sheet
        assert "requires a budget" in _said(app)

        await onto(app, driver, _BUDGET)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Configures), driver)
        assert rows(app) == ["duration", "cost", "output_tokens", "graceful", _DONE]
        await changes(app, driver, "duration", *"soon")
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await driver.pause()
        assert isinstance(app.screen, Configures)  # not a duration, so not taken
        assert "not a duration" in _said(app)
        await changes(app, driver, "duration", *(["backspace"] * 4), *"90m")
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)
        assert "stops at 1h30m" in _value(app, _BUDGET)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    assert app._budget == Budget(duration=datetime.timedelta(minutes=90))
    assert Settings(tmp_path).budget("here") == {
        "duration": "PT1H30M",
        "cost": None,
        "output_tokens": None,
        "graceful": True,
    }


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_an_environment_role_is_a_row_where_its_place_is_said(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
    tmp_path: Path,
) -> None:
    """Placed on its own sheet, read the way `-e` is: one that does not read is refused."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow placed")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        await until(lambda: sheet._inside, driver)
        assert rows(app) == ["0", "@repo", _BUDGET, _HARNESS, _SAVE]
        assert "not set" in _value(app, "@repo")

        # Not said, so not saved: a run of it would be refused before it started.
        await _budgets(app, driver, "1h")
        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await driver.pause()
        assert "repo is not configured yet" in _said(app)

        await onto(app, driver, "@repo")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Placing), driver)
        await changes(app, driver, "spelled", *"nowhere")
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await driver.pause()
        assert isinstance(app.screen, Placing)
        assert "expected <role>=<backend>" in _said(app)

        await changes(
            app,
            driver,
            "spelled",
            *(["backspace"] * len("nowhere")),
            *f"local@{tmp_path}",
        )
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)
        assert f"local@{tmp_path}" in _value(app, "@repo")

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    assert app._envs == {"repo": f"local@{tmp_path}"}
    assert Settings(tmp_path).envs("placed") == {"repo": f"local@{tmp_path}"}


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_nothing_is_applied_until_the_menu_is_saved_on_the_way_out(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """A draft until it is confirmed, and then the whole of it at once.

    Which is what makes the pages one menu rather than two sheets in a row.
    """
    app = Humanize()
    async with app.run_test() as driver:
        was = (app._flow_named, dict(app._models))
        await _open(app, driver, "here")
        await changes(app, driver, "effort", "left")  # round to the other, a change
        assert "max" in _value(app, "effort")

        await drops(app, driver)  # asked about, and thrown away
        await until(lambda: isinstance(app.screen, Flows), driver)
        await drops(app, driver)
        await until(lambda: not isinstance(app.screen, Flows), driver)

        assert (app._flow_named, app._models) == was

        # And the same walk saved lands the lot, flow and agent together.
        await _open(app, driver, "here")
        await changes(app, driver, "effort", "left")
        await keeps(app, driver)
        await until(lambda: isinstance(app.screen, Flows), driver)
        await _budgets(app, driver, "1h")
        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Flows), driver)

    assert app._flow_named == "here"
    assert app._models == {"builder": Runs("claude/claude-opus-5:max")}


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_question_on_the_way_out_is_two_answers_and_esc(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """Going back to the menu is what esc is everywhere else, so it is not a row as well."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "here")
        await changes(app, driver, "effort", "left")

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Confirms), driver)
        sheet = app.screen
        assert isinstance(sheet, Confirms)
        assert sheet.query_one("#choices", OptionList).option_count == 2

        # And esc off it is the sheet again, holding what it was holding.
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Agent), driver)

        assert "max" in _value(app, "effort")


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_walking_out_of_an_unchanged_sheet_asks_nothing(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """A walk in to look and out again is not a question anybody wants asked of them."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "here")
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Flows), driver)
        # Straight back, rather than through a question about a change nobody made.
        assert isinstance(app.screen, Flows)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_flow_given_no_budget_is_refused_where_it_is_started(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
    hosting: None,
) -> None:
    """The refusal is the runtime's, and it is a line at this prompt rather than a traceback."""
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "here", {"builder": Runs("claude/claude-opus-5:max")})
        app._budget = None
        await driver.press(*"go")
        await driver.press("enter")
        await until(lambda: "hmz:" in transcript(app), driver)
        said = transcript(app)

    assert "requires a budget" in said
    assert "Traceback" not in said  # said at the prompt, not raised out of a thread
    assert app._run is None  # and nothing started


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value=CLAUDE | {"opencode": (Model("anthropic/opus", ("high",)),)},
)
async def test_the_flow_may_rule_a_backend_out_of_the_clis_offered(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    tmp_path: Path,
) -> None:
    """A CLI that cannot do what the role declares is one choosing would refuse to start on."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(
        where,
        "goal",
        '''
"""One agent, under a goal of its own."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import GoalCommandAgentMixin, flow


class Pursues(Agent, GoalCommandAgentMixin): ...


class Agents(AgentCollection):
    """The one that pursues."""

    worker: Pursues


@flow(agents=Agents, envs=EnvCollection, params=FlowParams)
async def goal(task: str, *, agents: Agents, envs: EnvCollection, params: FlowParams,
               ctx: FlowContext) -> None:
    pass
''',
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "goal")
        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)

        # Only the ones with a goal feature of their own, which opencode has not.
        assert "opencode" not in rows(app)
        assert "claude" in rows(app)


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value=CLAUDE
    | {
        "codex": (Model("gpt-5.5", ("high",)),),
        "opencode": (Model("anthropic/opus", ("high",)),),
    },
)
async def test_a_role_typed_as_one_harness_is_offered_that_harness_alone(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    tmp_path: Path,
) -> None:
    """A role declared a `CodexAgent` is Codex: every other CLI would be refused at the run."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(
        where,
        "codex_only",
        '''
"""One agent, and it is Codex."""

from hmz.flows import AgentCollection, CodexAgent, EnvCollection, FlowContext, FlowParams
from hmz.flows import flow


class Agents(AgentCollection):
    reviewer: CodexAgent


@flow(agents=Agents, envs=EnvCollection, params=FlowParams)
async def codex_only(task: str, *, agents: Agents, envs: EnvCollection,
                     params: FlowParams, ctx: FlowContext) -> None:
    pass
''',
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "codex_only")
        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)

        assert rows(app) == ["codex"]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_models_are_what_that_cli_last_said_and_are_asked_again_from_a_row(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """A CLI ships a model without asking anybody, so the list is asked for rather than kept."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "here")
        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        keys = str(app.screen.query_one("#keys", Label).content)

        # Asking again is a row below the models rather than a key.
        assert rows(app)[-1] == _AGAIN
        listing = app.screen.query_one("#choices", OptionList)
        last = listing.get_option_at_index(listing.option_count - 1)
        assert "check again" in str(last.prompt)
        assert "ctrl" not in keys.lower()
