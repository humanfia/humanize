"""What a flow says filling one of its places takes, and what happens when it does not.

Most of what a flow builds on, every backend here serves. Some of it only some of them do,
and a flow built on one of those is not a flow any agent can drive. So it writes `Needs`
beside the place, and an agent whose backend serves none of it is refused before the first
turn rather than found out from the call that reached for it, hours into a loop.

What is covered here is the agent half -- what the backend filling the place has to serve --
at the top of a run and again where one flow calls another, those being the two places an
agent is ever handed to a flow. The other half, what the machine an agent's turns land on has
to come to, is covered beside the rest of where agents work in `test_where_agents_work.py`.
Nothing here takes a turn: the whole point is that none of it needs one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    DshAgent,
    DshAgentConfig,
    Needs,
)
from hmz.flows import NotAFlow, load, wanted
from hmz.runtime.runner import Runner
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor.backends import Model

#: A flow that steers the turn it is driving, which only some backends can be asked to do.
STEERS = '''"""One that talks to its agent mid-turn."""

from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, and what filling that place takes."""

    builder: Annotated[AgentBase, Needs("steer")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow that asks for three things at once, one of them a moment.
SEVERAL = '''"""One built on more than a flow usually is."""

from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """Two places, only one of which asks for anything."""

    builder: Annotated[AgentBase, Needs("shape", "tools", "moment:SubagentStop")]
    reviewer: AgentBase


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow built on a fact about the CLI rather than on one about the driver that speaks to it.
RESUMES = '''"""One that picks a conversation back up."""

from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives."""

    builder: Annotated[AgentBase, Needs("resume")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: One built on something every backend here serves, which is still a thing to be able to say.
EVERYONE = '''"""One built on what nobody has to shop for."""

from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, which has only to do what all of them do."""

    builder: Annotated[AgentBase, Needs("schema", "hooks")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow that asks for nothing in particular, which is most flows.
PLAIN = '''"""One that any agent can drive."""

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    pass
'''

#: One that calls the one that steers, handing it the agent it was given.
CALLS = '''"""One that reaches for the flow that steers."""

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow, load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    load("steers")(agents, task)
'''

#: One that asks of the *agent* for something only a machine can answer. Legal Python, a real
#: capability name, and the wrong half of `Needs` -- which used to be satisfied by whatever
#: filled the place, a machine capability carrying no backends and no backends meaning all of
#: them.
MISPLACED = '''"""One that asks for a container of the agent rather than of the machine."""

from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, asked for wrongly."""

    builder: Annotated[AgentBase, Needs("isolated")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: The same slip the other way round: a road humanize only reaches a turn down from inside a
#: process it started, asked of the machine. No machine's settings have ever carried one, so
#: this was refused by every machine there is -- a check nothing could pass.
INSIDE_OUT = '''"""One that asks a machine for the CLI's own hooks."""

from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, asked for wrongly."""

    builder: Annotated[AgentBase, Needs(where=("anchor:hooked",))]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: And the same road asked in the half that can answer it, which is the agent's.
HOOKED = '''"""One built on reaching its turns through the CLI's own hooks."""

from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, and what filling that place takes."""

    builder: Annotated[AgentBase, Needs("anchor:hooked")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: One whose agent may look and may change nothing, said as a capability rather than only as
#: a setting: a backend with no way of being held to that rung is refused before it is chosen.
READ_ONLY = '''"""One whose reviewer must be holdable to read-only."""

from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, and the rung it has to be holdable to."""

    builder: Annotated[AgentBase, Needs("rung:read-only")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''


def _claude() -> ClaudeCodeAgent:
    """An agent of the backend whose turns can be talked to while they run."""
    return ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))


def _dsh() -> DshAgent:
    """An agent of a backend whose turns cannot."""
    return DshAgent(DshAgentConfig(model="m", effort="high"))


@pytest.fixture(autouse=True)
def flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project holding the flows these tests drive, and a home nothing wrote to."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    where = tmp_path / "project"
    kept = where / ".humanize/flows"
    kept.mkdir(parents=True)
    written(kept, "steers", STEERS)
    written(kept, "several", SEVERAL)
    written(kept, "resumes", RESUMES)
    written(kept, "everyone", EVERYONE)
    written(kept, "plain", PLAIN)
    written(kept, "calls", CALLS)
    written(kept, "misplaced", MISPLACED)
    written(kept, "inside_out", INSIDE_OUT)
    written(kept, "hooked", HOOKED)
    written(kept, "read_only", READ_ONLY)
    monkeypatch.chdir(where)
    return where


def test_a_flow_says_what_filling_each_of_its_places_takes() -> None:
    """Read where the agents are chosen, so that only ones that would work are offered."""
    places = wanted("several")

    assert places[0].needs == Needs("shape", "tools", "moment:SubagentStop")
    assert places[1].needs is None  # which is a place any agent may fill


def test_a_place_that_asks_for_nothing_is_a_place_any_backend_may_fill() -> None:
    """Most places: what every backend serves is nothing a flow has to write down."""
    Runner("plain", [_dsh()])  # which is the whole assertion: it is not refused


def test_a_flow_built_on_steering_is_refused_a_backend_that_cannot_be_steered() -> None:
    """Before the first turn, which is the only time refusing it costs nothing."""
    with pytest.raises(
        NotAFlow, match="builder has to serve steer, which dsh does not"
    ):
        Runner("steers", [_dsh()])


def test_a_flow_built_on_steering_takes_a_backend_that_can_be_steered() -> None:
    """The other half of the same check: a fit agent is refused nothing."""
    runner = Runner("steers", [_claude()])

    assert len(runner.agents) == 1


def test_a_flow_is_refused_for_every_one_of_the_things_it_asks_for_at_once() -> None:
    """Named together rather than one at a time, so that one reading says what to choose."""
    with pytest.raises(NotAFlow) as refused:
        Runner("several", [_dsh(), _dsh()])

    assert "builder has to serve moment:SubagentStop, shape, tools" in str(
        refused.value
    )
    assert "which dsh does not" in str(refused.value)


def test_what_the_backend_itself_serves_is_read_where_it_is_written_down() -> None:
    """`resume` is a fact about the CLI rather than about the driver that speaks to it."""
    runner = Runner("resumes", [_dsh()])

    assert len(runner.agents) == 1


def test_a_flow_calling_another_is_refused_the_same_way_the_run_would_be() -> None:
    """The check is duplicated so that a flow cannot pass at the top and fail in the middle."""
    with pytest.raises(
        NotAFlow, match="builder has to serve steer, which dsh does not"
    ):
        load("calls")([_dsh()], "go")


def test_a_flow_calling_another_with_a_fit_agent_is_not_refused() -> None:
    """And the called flow runs, which is what being handed a fit agent comes to."""
    load("calls")([_claude()], "go")  # the whole assertion: nothing is raised


def test_what_every_backend_serves_is_served_by_every_backend() -> None:
    """The catalogue names nobody against those, which must not read as nobody serving them."""
    runner = Runner("everyone", [_dsh()])

    assert len(runner.agents) == 1


def test_a_place_takes_what_it_needs_as_names_rather_than_as_one_name() -> None:
    """`where="remote"` is five capabilities spelled a letter each, so it is refused outright."""
    with pytest.raises(TypeError, match="sequence of names rather than one name"):
        Needs(where="remote")


def test_whoever_is_choosing_an_agent_is_offered_only_the_ones_that_would_do() -> None:
    """Asked by backend before there is an agent, so a place cannot be filled wrong."""
    from hmz.flows.driving import Place
    from hmz.tui.pick import Clis

    offered: dict[str, tuple[Model, ...]] = {"claude": (), "dsh": ()}
    plain = Place(name="builder", person=False, moments=frozenset())

    assert [row[0] for row in Clis(offered, place=plain).rows()] == ["claude", "dsh"]

    steering = plain._replace(needs=Needs("steer"))

    assert [row[0] for row in Clis(offered, place=steering).rows()] == ["claude"]


def test_a_place_that_asks_of_the_agent_for_a_machines_answer_is_refused() -> None:
    """`Needs("isolated")` used to be satisfied by whatever filled the place.

    A machine capability carries no backends, because no backend answers for it, and an empty
    backend set is how the catalogue says "every backend here". So the one slip a type checker
    cannot see -- the ask written in the wrong half of `Needs` -- was answered yes by every
    agent there is, and a flow that meant to be protected was protected by nothing. It is
    refused now, and the refusal says where the ask belongs.
    """
    with pytest.raises(NotAFlow, match=r"Needs\(where=\('isolated',\)\)"):
        Runner("misplaced", [_claude()])


def test_a_place_that_asks_a_machine_for_the_agents_own_road_is_refused() -> None:
    """The same slip the other way, and the one the docstring used to advertise.

    `anchor:hooked` is a hook table humanize writes for one run of a CLI it started here. It
    is the CLI's own to take and no machine's settings have ever carried it, so asking for it
    under `where=` was refused by every machine there is -- always no, which measures nothing.
    """
    with pytest.raises(NotAFlow, match=r"Needs\('anchor:hooked'\)"):
        Runner("inside_out", [_claude()])


def test_the_agents_own_road_is_asked_of_the_agent_and_answered_there() -> None:
    """Which is the half that can answer: the profile is what declares a hook seam."""
    runner = Runner("hooked", [_claude()])

    assert len(runner.agents) == 1

    with pytest.raises(NotAFlow, match="has to serve anchor:hooked"):
        Runner("hooked", [_dsh()])


def test_a_flow_may_ask_for_a_rung_before_its_first_turn() -> None:
    """The rung a backend can be held to is a capability like any other.

    dsh bundles no confining executor and refuses everything below `bypass`, which it has
    always said where the agent is made -- hours after somebody chose it for a flow whose
    reviewer may change nothing. Said as a capability, it is said where the choice is made.
    """
    runner = Runner("read_only", [_claude()])

    assert len(runner.agents) == 1

    with pytest.raises(
        NotAFlow, match="has to serve rung:read-only, which dsh does not"
    ):
        Runner("read_only", [_dsh()])


def test_the_rung_a_backend_refuses_is_the_rung_it_does_not_serve() -> None:
    """One fact, read from the driver class and enforced by it, rather than two."""
    from hmz.coganchor.agents import PERMISSIONS, rung
    from hmz.flows.driving import comes_to

    for permission in PERMISSIONS:
        served = rung(permission) in comes_to("dsh")

        assert served is (permission in DshAgent.rungs), permission
        if not served:
            # And the driver refuses it where the agent is made, which is the fact this
            # capability is a word for rather than a second answer beside it.
            with pytest.raises(ValueError, match="bypass"):
                DshAgent(
                    DshAgentConfig(model="m", effort="high", permission=permission)
                )


def test_the_picker_blames_the_flow_rather_than_the_installation() -> None:
    """A place asking of the agent for a machine's answer rules out every CLI there is.

    Which it should -- no backend comes to `isolated` -- but saying that nothing installed
    here will do sends somebody off to install a thirteenth CLI for a flow no CLI can fill.
    """
    from hmz.flows.driving import Place
    from hmz.tui.pick import Clis

    offered: dict[str, tuple[Model, ...]] = {"claude": (), "dsh": ()}
    wrong = Place(
        name="builder",
        person=False,
        moments=frozenset(),
        needs=Needs("isolated"),
    )
    picking = Clis(offered, place=wrong)

    assert picking.rows() == []
    assert "Needs(where=('isolated',))" in picking.nothing()
    # And a place nothing is wrong with says the other thing, which is still the usual one.
    bare = Place(name="builder", person=False, moments=frozenset())
    picking = Clis({}, place=bare)

    assert picking.rows() == []
    assert "no coding agent installed here" in picking.nothing()
