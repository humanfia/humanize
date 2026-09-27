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
from hmz.daemon import Link
from hmz.tui.pick import Flows
from hmz.tui.selecting import Transcript

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.coganchor.agents import AgentBase
    from hmz.flows import Budget
    from hmz.runtime.kept import Runs
    from hmz.tui import Humanize

#: How long anything here waits for the interface to catch up before giving up on it.
PATIENCE = 30.0

#: Catching up on fetches, before the suite takes it away again.
_CATCHES = Flows._catches_up

#: And taking what the ones already here say now, likewise.
_FRESHENS = hmz.tui.app.Humanize._freshens_flows

#: And holding runs in this process, before the suite hands every interface a fake instead.
_LINKS = hmz.tui.app.Humanize._links


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


class FakeLink(Link):
    """An interface's end of runs that are not there: every request written down and answered.

    What the interface is told is pushed by the test through `told`, and what it asks is
    kept in `requests`, answered `{"ok": True}` unless `answers` says otherwise for that kind
    of request -- a refusal is an answer with `ok` false and `why`. Steering and routing are
    the host's, and tested against it; what is tested with this is what the interface draws
    and what it asks for.

    Attributes:
      requests: What was asked, in the order it was asked.
      answers: What each kind of request is answered with, where not with `ok`.
    """

    def __init__(self, client: str = "c1") -> None:
        self.requests: list[dict[str, Any]] = []
        self.answers: dict[str, dict[str, Any]] = {}
        super().__init__(self._answering, lambda: None)
        self.client = client

    def heard(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Takes the listener, and tells it nothing: the test does, with `told`."""
        del listener

    def _answering(self, said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        del seconds
        self.requests.append(said)
        return dict(self.answers.get(str(said.get("do")), {"ok": True}))

    def asked_for(self, do: str) -> list[dict[str, Any]]:
        """Every request of one kind, in the order they were asked."""
        return [one for one in self.requests if one.get("do") == do]


@pytest.fixture(autouse=True)
def _linked_to_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opens every interface on a `FakeLink` rather than on runs held in this process.

    Held runs are the host's, and tested against it; an interface opened here is drawn from
    what a test tells it and asks what it asks of nobody, so that nothing a test did not say
    arrives on a thread of its own to race what it did. `hosting` gives the runs back to a
    test that drives a real run through the interface.
    """

    def fake(_self: Humanize, _host: object) -> FakeLink:
        return FakeLink()

    monkeypatch.setattr(hmz.tui.app.Humanize, "_links", fake)


@pytest.fixture
def hosting(_linked_to_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives an interface runs held in this process again, for a test that runs a flow.

    Named after the fixture that took them away, so that it is put back after rather than
    before: two fixtures setting one attribute is the order they run in.
    """
    monkeypatch.setattr(hmz.tui.app.Humanize, "_links", _LINKS)


def link(app: Humanize) -> FakeLink:
    """The fake end of the runs an interface was opened on, which says what it asked."""
    held = app._link
    assert isinstance(held, FakeLink), "opened on runs held here: see `hosting`"
    return held


def started(
    run: int = 0,
    *,
    flow: str = "flow",
    task: str = "",
    roles: Iterable[str] = (),
    outworlders: Iterable[str] = (),
    agents: Mapping[str, str] | None = None,
    by: str = "you@tui",
    client: str = "c1",
) -> dict[str, Any]:
    """A run starting, as the record every frontend is told of it by.

    Args:
      run: Which run it is: 0, as an interface that has started none numbers the first.
      flow: The flow.
      task: What it was started on.
      roles: Its agent roles, in the order the flow declares them.
      outworlders: Its `Outworlder` roles.
      agents: What each agent role runs, as `-a` spells it; `claude/m:high` apiece where
        None.
      by: Who started it.
      client: Which frontend that was: `c1` is the interface a `FakeLink` is.

    Returns:
      The record.
    """
    named = list(roles)
    return {
        "type": "started",
        "run": run,
        "flow": flow,
        "ref": flow,
        "task": task,
        "by": by,
        "client": client,
        "roles": named,
        "outworlders": list(outworlders),
        "agents": dict(agents)
        if agents is not None
        else dict.fromkeys(named, "claude/m:high"),
        "envs": {},
        "params": {},
        "budget": {},
        "resume": "",
        "began": time.monotonic(),
        "at": time.time(),
    }


def snapshot(kind: str, **fields: Any) -> dict[str, Any]:
    """How one thing stands, as the runs say it: `claims`, `pending`, `waiting` and the rest."""
    return {"type": kind, **fields}


def running(
    record: Mapping[str, Any], *, stopping: int | None = None
) -> dict[str, Any]:
    """The `run` snapshot of a run going, as a `started` record said it began."""
    return {**record, "type": "run", "state": "running", "stopping": stopping}


def idle(*, stopping: int | None = None) -> dict[str, Any]:
    """The `run` snapshot with nothing running: stopping, where a run still is."""
    return {
        "type": "run",
        "state": "idle" if stopping is None else "stopping",
        "run": 0,
        "stopping": stopping,
    }


def asked(
    question: str,
    role: str = "human",
    text: str = "",
    *,
    options: Iterable[str] = (),
    mode: str = "ask",
    run: int = 0,
    owner: str | None = None,
) -> dict[str, Any]:
    """A question an `Outworlder` asks, as the `asked` record says it and `pending` lists it.

    Args:
      question: Its id.
      role: The outworlder asking.
      text: What it asks.
      options: The answers it offers.
      mode: `ask`, or `listen` for what to say next.
      run: The run asking.
      owner: The frontend holding the role, or None for anybody's.

    Returns:
      The record; `pending` lists the same fields with `type` taken off.
    """
    return {
        "type": "asked",
        "run": run,
        "question": question,
        "role": role,
        "text": text,
        "options": list(options),
        "mode": mode,
        "owner": owner,
    }


def pending(*questions: Mapping[str, Any]) -> dict[str, Any]:
    """The `pending` snapshot, listing questions as `asked` makes them."""
    return {
        "type": "pending",
        "pending": [
            {key: value for key, value in one.items() if key != "type"}
            for one in questions
        ],
    }


class Holding:
    """A run the runs say is going, as a test puts one in front of the interface.

    What the interface asked of it is read off its `FakeLink`.

    Attributes:
      number: Which run it is.
    """

    def __init__(self, app: Humanize, number: int) -> None:
        self._app = app
        self.number = number

    @property
    def stopped(self) -> bool:
        """Whether the interface asked for it to stop, or to be forced to."""
        return any(
            one.get("do") in ("stop", "force") for one in link(self._app).requests
        )

    @property
    def closed(self) -> bool:
        """Whether the interface asked for it to be forced to a stop."""
        return bool(link(self._app).asked_for("force"))


def holding(
    app: Humanize,
    *agents: AgentBase | str,
    outworlders: Iterable[str] = (),
    task: str = "",
    run: int = 0,
) -> Holding:
    """Puts the interface in the state of reading a running flow, with these agents in it.

    Tells it the run started and is going, then opens every conversation each agent holds,
    numbered for its role in the order given -- or the one key given as a string. A person
    holds none, and is told of as the one the board is kept by.

    Args:
      app: The interface.
      agents: The agents behind the sessions the run has opened, or their keys.
      outworlders: The run's `Outworlder` roles.
      task: What it was started on.
      run: Which run it is.

    Returns:
      The run.
    """
    from hmz.coganchor.agents import HumanAgent

    keys: list[str] = []
    person = False
    counted: dict[str, int] = {}
    for agent in agents:
        if isinstance(agent, str):
            keys.append(agent)
            continue
        if isinstance(agent, HumanAgent):
            person = True
            continue
        for _ in agent.sessions or [None]:
            counted[agent.id] = counted.get(agent.id, 0) + 1
            keys.append(f"{agent.id}/{counted[agent.id]}")
    roles = list(dict.fromkeys(key.partition("/")[0] for key in keys))
    record = started(run, task=task, roles=roles, outworlders=outworlders)
    told(app, record, running(record), *(opened(key, run=run) for key in keys))
    if person:
        told(app, snapshot("board", items=[]))
    return Holding(app, run)


def opened(
    key: str,
    *,
    run: int = 0,
    model: str = "m",
    cli: str = "claude",
    counts: Iterable[str] = (),
    person: bool = False,
) -> dict[str, Any]:
    """A session a run has opened, as the record the interface is told of it by.

    Args:
      key: What it is read under, `<role>/<n>`.
      run: The run it is of: 0 for the one an interface holds before it has started any.
      model: What it runs at.
      cli: What runs it.
      counts: The kinds of token its backend reports.
      person: Whether it is the person, who holds the board rather than a conversation.

    Returns:
      The record, as `hmz.runtime.doing.hosting.Host` says one.
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
        "person": person,
        "kept": "",
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
      The record, as `hmz.runtime.doing.hosting.record` makes one.
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
    """Tells the interface messages about its runs, in order, as the runs tell it them.

    Args:
      app: The interface.
      records: What it is told, as the builders here make them.
    """
    for one in records:
        app._told(one)
