"""What every test of the interface needs: somewhere of its own to be running in.

No test lives here any more. They are in `tests/unit/tui`, `tests/integration/tui` and
`tests/system/tui`, and a fixture is visible only under the conftest that declares it, so each
of those directories takes back by name the ones it needs. Two of the fixtures below are
autouse, which is the pair that has to travel: a test asking for one by name says so when it is
missing, and an autouse one that nobody re-exported goes missing in silence -- the test passes,
having run the interface in the home directory of whoever ran the suite. Add a fixture here and
it reaches nothing until those conftests are told about it; `tests/test_tiers.py` is what reads
the re-exports back and fails the run for one that was left out.

The interface writes down what is typed at it, in the project it is running in. A test types
things, and the project it would be writing them into is this one.

It also opens set up to run: a flow, and the first agent installed to run it on. What is
installed is whatever is on the developer's own PATH, so a test that did not say would pass
here and fail on a machine with nothing installed, or start a real coding agent on a line
typed as a no-op. Every test therefore starts with nothing installed until it says otherwise.

And two things here fetch from a remote on a machine that only asked for the suite to pass: the
flow menu clones what has never been fetched as it opens, and the interface takes what
everything already fetched says now as it starts. Both are taken away here, and each is given
back by name to the test that is about it -- `catching_up` for the menu's first fetch and
`freshening` for the interface's.

Taken away for the time and the determinism, though, rather than as the promise that nothing
here reaches anybody's network. That promise is `tests/conftest.py`'s, which refuses for the
whole session any clone whose address names another machine: a road off the machine is a road
off the machine wherever the test that takes it is filed, and while it was shut in this file it
covered the interface's own tests and nothing else. So a test that asks for one of these back
has not opened that road. It says which flowverse it fetches from, and the guard at the root is
still standing behind it to refuse one that names somebody else's.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import pytest

import hmz.tui.app
import hmz.tui.pick
from hmz.tui.pick import Flows
from hmz.tui.selecting import Transcript

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.coganchor.agents import AgentBase, Event, SessionBase
    from hmz.flows import Budget
    from hmz.runtime.kept import Runs
    from hmz.tui import Humanize

#: How long anything here waits for the interface to catch up before giving up on it.
PATIENCE = 30.0

#: Catching up on fetches, before the suite takes it away again.
_CATCHES = Flows._catches_up

#: And taking what the ones already here say now, likewise.
_FRESHENS = hmz.tui.app.Humanize._freshens_flows


@pytest.fixture(autouse=True)
def _elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs the interface somewhere temporary, with no backend, unless the test says."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hmz.tui.app, "installed", dict)
    monkeypatch.setattr(hmz.tui.app, "installable", dict)
    # The sheets ask too -- which of the backends an account could also be run as are worth
    # ticking is which of them are here -- and a suite that read the developer's own PATH
    # would pass on their machine and fail on the next one.
    monkeypatch.setattr(hmz.tui.pick, "installed", dict)


@pytest.fixture(autouse=True)
def _fetches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Takes both fetches off the interface: the menu's first one, and the interface's own.

    Both, rather than the one the test being written is about: a suite that left either in
    would clone or fetch humanize's own flowverse on every interface it opens, which is a
    suite that is slow on a network and fails without one.

    Not the guard against reaching one, which is `_clones_nothing_elsewhere` in
    `tests/conftest.py` and is over the whole session rather than over this directory. This is
    the other half of it: a clone that is refused still costs the interface the seconds it
    spends being refused, and a menu waiting on one is a pilot waiting on the menu. So the work
    is taken away rather than left to fail, and what these tests drive is an interface whose
    flows are already there.
    """

    def nothing(_self: Flows) -> None:
        """What catching up on fetches comes to here, which is nothing at all."""

    def nor_again(_self: Humanize) -> None:
        """Nor does taking what the ones already here say now."""

    monkeypatch.setattr(Flows, "_catches_up", nothing)
    monkeypatch.setattr(hmz.tui.app.Humanize, "_freshens_flows", nor_again)


@pytest.fixture
def catching_up(_fetches_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives it back, for a test that is about what the menu fetches as it opens.

    Named after the fixture that took it away, so that it is put back after rather than
    before: two fixtures setting one attribute is the order they run in.
    """
    monkeypatch.setattr(Flows, "_catches_up", _CATCHES)


@pytest.fixture
def freshening(_fetches_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same, for a test about what the interface fetches again as it starts."""
    monkeypatch.setattr(hmz.tui.app.Humanize, "_freshens_flows", _FRESHENS)


async def until(ready: Callable[[], bool], driver: Pilot[None]) -> None:
    """Pumps the interface until something is true, or gives up after a while.

    Waited on the clock rather than counted in pumps: a pump can pass in microseconds,
    so counting them is a spin that finishes before the worker thread has done anything.

    Args:
      ready: What is being waited for.
      driver: The interface to keep pumping while waiting.
    """
    deadline = time.monotonic() + PATIENCE
    while not ready() and time.monotonic() < deadline:
        await driver.pause()
        await asyncio.sleep(0.02)


def transcript(app: Humanize) -> str:
    """Everything the interface has shown, as one searchable string.

    Read while the interface is still up: its widgets go with it when it exits.
    """
    return app.query_one("#transcript", Transcript).text


#: A flow of one agent role, `coder`, working in the workspace it was started in: one turn on
#: the task, and what that turn answered written beside it to `said.txt`. Written against the
#: flow API, as every flow a test here runs is, and run through the runtime on whatever `-a`
#: the interface is set up with.
ONE = """
from pathlib import Path

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, flow


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    pass


@flow(agents=Agents, envs=Envs, params=Params, name="flow")
async def run(task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext):
    coder = agents["coder"]
    session = await coder.spawn(env=envs["workspace"])
    Path("said.txt").write_text(await coder.run(task, session=session) + "\\n")
"""


def set_up(
    app: Humanize,
    flow: str,
    agents: Mapping[str, Runs] | None = None,
    *,
    budget: Budget | None = None,
) -> None:
    """Sets the interface up to run one flow, as saving the flow menu would.

    Args:
      app: The interface.
      flow: The flow, by the name it is offered under or a path.
      agents: What each agent role runs, by role; `claude/m:high` for `coder` where None.
      budget: What a run of it may spend; a dollar where None.
    """
    from hmz.flows import Budget
    from hmz.runtime.kept import Runs
    from hmz.tui.pick import declared_of

    app._flow_named = flow
    app._declared = declared_of(flow)
    app._models = (
        dict(agents) if agents is not None else {"coder": Runs("claude/m:high")}
    )
    app._budget = budget if budget is not None else Budget(cost=1)


class Holding:
    """A run the interface is holding that runs nothing: for a test about that state alone.

    It opens a session and says something in one only where a test says so, through `opens`
    and `says`, and then tells whoever is following it just as a run does.

    Attributes:
      stopped: Whether it was told to stop.
      closed: Whether it was closed.
    """

    flow = "flow"
    ref = "flow"

    def __init__(self) -> None:
        from hmz.flows import Budget, Usage

        self.budget = Budget(cost=1)
        self.usage = Usage()
        self.stopped = False
        self.closed = False
        self._listeners: list[Callable[..., None]] = []
        self._callbacks: list[Callable[..., None]] = []

    def watch(self, listener: Callable[..., None]) -> None:
        """Keeps who hears what its turns say, which is nothing until a test says it."""
        self._listeners.append(listener)

    def opened(self, callback: Callable[..., None]) -> None:
        """Keeps who is told of each session it opens."""
        self._callbacks.append(callback)

    def opens(self, agent: AgentBase, session: SessionBase | None = None) -> None:
        """Opens one session for the role the agent is named for, as a run tells of one.

        Args:
          agent: The agent behind it.
          session: Its conversation, or None for a person, who holds none.
        """
        for callback in list(self._callbacks):
            callback(agent.id, agent, session)

    def says(self, agent: AgentBase, session: SessionBase | None, event: Event) -> None:
        """Has a turn say something, as a run's own sessions do.

        Args:
          agent: Whose turn.
          session: Which of its conversations, or None for the agent's own.
          event: What it says.
        """
        for listener in list(self._listeners):
            listener(agent, session, event)

    def run(self) -> None:
        """Runs nothing."""

    def stop(self) -> None:
        """Writes down that it was told to."""
        self.stopped = True

    def close(self) -> None:
        """Likewise."""
        self.closed = True


def holding(app: Humanize, *agents: AgentBase) -> Holding:
    """Puts the interface in the state of holding a running flow, with these agents in it.

    Every conversation each of them holds is opened in it, as a run tells the interface of
    one: numbered for its role in the order given, which is the key its records name it by,
    and kept as what a word typed at it reaches. A person holds none, and is told of as the
    one the board is kept by.

    Args:
      app: The interface.
      agents: The agents behind the sessions the run has opened.

    Returns:
      The run it is holding.
    """
    from hmz.coganchor.agents import HumanAgent

    run = Holding()
    app._run = run
    app._follow(run)
    for agent in agents:
        for session in [None] if isinstance(agent, HumanAgent) else agent.sessions:
            run.opens(agent, session)
    return run


def opened(
    key: str,
    *,
    run: int = 0,
    model: str = "m",
    cli: str = "claude",
    counts: Iterable[str] = (),
) -> dict[str, Any]:
    """A session a run has opened, as the record the interface is told of it by.

    Args:
      key: What it is read under, `<role>/<n>`.
      run: The run it is of: 0 for the one an interface holds before it has started any.
      model: What it runs at.
      cli: What runs it.
      counts: The kinds of token its backend reports.

    Returns:
      The record, as `hmz.tui.records.opened` makes one.
    """
    role = key.partition("/")[0]
    return {
        "type": "opened",
        "run": run,
        "role": role,
        "key": key,
        "agent": role,
        "cli": cli,
        "model": model,
        "counts": sorted(counts),
        "forks": False,
        "person": False,
        "mono": time.monotonic(),
    }


def event(
    key: str,
    kind: str,
    text: str = "",
    *,
    run: int = 0,
    session: bool = True,
    whose: str = "",
    tokens: Mapping[str, int] | None = None,
    spent: Mapping[str, float] | None = None,
    ident: str = "",
    model: str = "m",
    cli: str = "claude",
) -> dict[str, Any]:
    """Something a turn said, as the record the interface is told of it by.

    Args:
      key: The transcript it goes on, `<role>/<n>` -- whose role is the agent that said it.
      kind: What kind of thing, as `Event.kind` says it.
      text: What was said.
      run: The run it is of: 0 for the one an interface holds before it has started any.
      session: Whether it was said in that conversation, rather than by the agent for all of
        its conversations and put on that one.
      whose: Which of a turn's several things it is about.
      tokens: What it cost, by model.
      spent: The same, by kind of token.
      ident: What the backend calls the conversation.
      model: What the agent runs at.
      cli: What runs it.

    Returns:
      The record, as `hmz.tui.records.record` makes one.
    """
    return {
        "type": "event",
        "run": run,
        "key": key,
        "session": key if session else "",
        "agent": key.partition("/")[0],
        "cli": cli,
        "model": model,
        "ident": ident,
        "kind": kind,
        "text": text,
        "whose": whose,
        "tokens": dict(tokens or {}),
        "spent": dict(spent or {}),
        "at": time.time(),
        "mono": time.monotonic(),
    }


def told(app: Humanize, *records: dict[str, Any]) -> None:
    """Tells the interface records of a run, in order, as a run it follows tells it them.

    Args:
      app: The interface.
      records: What it is told, as `opened` and `event` make them.
    """
    for one in records:
        app._told(one)
