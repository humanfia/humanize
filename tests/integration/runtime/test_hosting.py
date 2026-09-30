"""The runs of a workspace, shared by several frontends, with flows really running in them.

Every frontend here is in this process and every flow is a file this test wrote, run by the
runtime for real: a flow whose only agents are `Outworlder` roles spends nothing and needs no
CLI, and one that drives an agent drives a stand-in -- a session that runs its prompt as a
shell script and says it has a word put into it the way a backend does -- behind the real
harness driver, with a `claude` on PATH that is a script, as `tests/integration/tui` drives
one.

What is checked is who may answer what, where a line typed at the run goes, and that a
frontend arriving late reads the run exactly as the first one did.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import AgentBase, AgentConfig, Event
from hmz.runtime import Hmz, Host
from hmz.runtime.flowing.harnesses import HarnessDriver
from hmz.runtime.flowing.specs import parse_agents
from tests.stubs import ShellAgent, ShellSession, written

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from hmz.coganchor.agents import SessionBase

#: How long a test waits for something another thread is doing.
PATIENCE = 20.0

#: Two people outside the run, asked one after the other, and what each said written down.
ASKS = """
import json
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    planner: Outworlder
    reviewer: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="asks")
async def asks(task, *, agents, envs, params, ctx):
    here = envs["workspace"]
    planner = await agents["planner"].spawn(env=here)
    reviewer = await agents["reviewer"].spawn(env=here)
    plan = await agents["planner"].run(f"what is the plan for {task}?", session=planner)
    review = await agents["reviewer"].run(f"is {plan!r} good?", session=reviewer)
    Path("result.json").write_text(json.dumps({"plan": plan, "review": review}))
"""

#: One agent's turn held open until the test lets it go, with the person outside asked
#: something while it is open where the test says so -- which is a question asked mid-turn.
STEERS = """
import asyncio
import json
from pathlib import Path

from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, Outworlder, flow,
)


class Agents(AgentCollection):
    coder: Agent
    planner: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="steers")
async def steers(task, *, agents, envs, params, ctx):
    here = envs["workspace"]
    while not Path("start").exists():
        await asyncio.sleep(0.02)
    session = await agents["coder"].spawn(env=here)
    person = await agents["planner"].spawn(env=here)

    async def asks():
        while not Path("ask").exists():
            if Path("go").exists():
                return ""
            await asyncio.sleep(0.02)
        return await agents["planner"].run("which way?", session=person)

    said, asked = await asyncio.gather(agents["coder"].run(task, session=session), asks())
    Path("result.json").write_text(json.dumps({"said": said, "asked": asked}))
"""

#: A person asked what to do, and then an agent's turn -- the order a flow that plans with
#: somebody before it works goes in.
HANDS = """
import json
from pathlib import Path

from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, Outworlder, flow,
)


class Agents(AgentCollection):
    coder: Agent
    planner: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="hands")
async def hands(task, *, agents, envs, params, ctx):
    here = envs["workspace"]
    session = await agents["coder"].spawn(env=here)
    person = await agents["planner"].spawn(env=here)
    plan = await agents["planner"].run("which way?", session=person)
    said = await agents["coder"].run(task, session=session)
    Path("result.json").write_text(json.dumps({"plan": plan, "said": said}))
"""

#: The turn the stand-in takes: open until `go` is there, then answering `done`.
TURN = "while [ ! -f go ]; do sleep 0.05; done; echo done"


class Steerable(ShellSession):
    """A session a word can be put into, which says it has it the way a backend says so.

    `refuse ...` is refused as a backend refuses one, and `hold ...` is taken and never said
    to have been had, which is a turn ending on a word it was holding.
    """

    def interject(self, text: str) -> None:
        if text.startswith("refuse"):
            raise RuntimeError("not now")
        if text.startswith("hold"):
            return
        self._heard(Event(kind="took", text=text))


class Forking(Steerable):
    """One that forks, which a shell has no way to: into a fresh one of the agent asked."""

    @property
    def forks(self) -> bool:
        return True

    def fork(
        self,
        *,
        into: AgentBase | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> SessionBase:
        del cwd
        assert into is not None
        return into.new(self.cwd)


class SteerableAgent(ShellAgent):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> Steerable:
        return Steerable(self, cwd)


class ForkingAgent(ShellAgent):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> Forking:
        return Forking(self, cwd)


class Told:
    """One frontend's end: everything it has been told, in the order it was told."""

    def __init__(self, host: Host, name: str, *, replay: bool = True) -> None:
        self.host = host
        self.seen: list[dict[str, Any]] = []
        self._landed = threading.Condition()
        self.client = host.attach(name, "sdk", self._told, replay=replay)

    def _told(self, message: dict[str, Any]) -> None:
        with self._landed:
            self.seen.append(message)
            self._landed.notify_all()

    def asks(self, **said: Any) -> dict[str, Any]:
        return self.host.asked(self.client, said)

    def waits(self, what: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        """The first message it was told that `what` says yes to, waited for."""
        with self._landed:
            found = self._landed.wait_for(
                lambda: next((one for one in self.seen if what(one)), None),
                timeout=PATIENCE,
            )
        assert found is not None, f"never told: {[one['type'] for one in self.seen]}"
        return found

    def told(self, kind: str, /, **fields: Any) -> dict[str, Any]:
        """The first message of a kind saying all of `fields`, waited for."""
        return self.waits(
            lambda one: (
                one["type"] == kind
                and all(one.get(key) == value for key, value in fields.items())
            )
        )

    def asked(self, role: str) -> dict[str, Any]:
        """The question a role is waiting on, as the frontends are shown it."""
        return self.waits(
            lambda one: (
                one["type"] == "pending"
                and any(asked["role"] == role for asked in one["pending"])
            )
        )["pending"][-1]

    def records(self) -> list[dict[str, Any]]:
        return [one for one in self.seen if "seq" in one and one["type"] != "live"]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Both flows, and a `claude` on PATH the stand-in is checked for and never runs."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    where = tmp_path / "workspace"
    where.mkdir()
    written(where, "asks", ASKS)
    written(where, "steers", STEERS)
    written(where, "hands", HANDS)
    monkeypatch.chdir(where)
    return where


@pytest.fixture
def host(workspace: Path) -> Iterator[Host]:
    held = Hmz().host()
    try:
        yield held
    finally:
        # Whatever a test left open finishes, rather than waiting on a file nobody writes --
        # and has finished before the next test runs in this process, which would otherwise
        # find its flow still unwinding and say so in a report of its own.
        for name in ("start", "go"):
            (workspace / name).write_text("")
        held.close()
        for thread in threading.enumerate():
            if thread.name == "humanize-run":
                thread.join(PATIENCE)


def _driver(kind: type[AgentBase] = SteerableAgent) -> HarnessDriver:
    """The stand-in behind the real driver a `-a coder=claude/m:high` is made into."""
    return HarnessDriver(
        parse_agents(["coder=claude/m:high"])[0],
        kind,
        AgentConfig(model="m", effort="high"),
        None,
    )


def _asks(one: Told) -> None:
    said = one.asks(do="start", flow="asks", task="the parser", budget={"cost": 1})
    assert said["ok"], said


def _steers(one: Told, kind: type[AgentBase] = SteerableAgent) -> None:
    said = one.asks(
        do="start",
        flow="steers",
        task=TURN,
        agents={"coder": _driver(kind)},
        budget={"cost": 1},
    )
    assert said["ok"], said


def _result(workspace: Path) -> dict[str, Any]:
    deadline = time.monotonic() + PATIENCE
    landed = workspace / "result.json"
    while time.monotonic() < deadline and not landed.exists():
        time.sleep(0.02)
    return json.loads(landed.read_text())


# ------------------------------------------------------------------ who answers


@pytest.mark.timeout(60)
def test_each_frontend_answers_only_for_the_role_it_claimed(
    host: Host, workspace: Path
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    alice.asks(do="claim", role="planner")
    bob.asks(do="claim", role="reviewer")
    _asks(alice)

    planning = bob.asked("planner")
    assert planning["owner"] == alice.client
    assert bob.asks(do="answer", question=planning["question"], text="mine") == {
        "ok": False,
        "why": "planner is alice's",
    }
    assert alice.asks(do="answer", question=planning["question"], text="a plan")["ok"]
    reviewing = alice.asked("reviewer")
    assert not alice.asks(do="answer", question=reviewing["question"], text="no")["ok"]
    assert bob.asks(do="answer", question=reviewing["question"], text="fine")["ok"]

    assert _result(workspace) == {"plan": "a plan", "review": "fine"}
    answered = [one for one in bob.records() if one["type"] == "answered"]
    assert [(one["role"], one["by"], one["text"]) for one in answered] == [
        ("planner", "alice", "a plan"),
        ("reviewer", "bob", "fine"),
    ]
    alice.told("ended", how="done")


@pytest.mark.timeout(60)
def test_a_question_nobody_claimed_is_the_first_answers(
    host: Host, workspace: Path
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    _asks(alice)

    planning = bob.asked("planner")
    assert planning["owner"] is None
    # Nothing is what nobody being there answers, so it is not an answer anybody gives.
    assert bob.asks(do="answer", question=planning["question"], text="") == {
        "ok": False,
        "why": "an answer says something",
    }
    assert bob.asks(do="answer", question=planning["question"], text="bob's")["ok"]
    assert alice.asks(do="answer", question=planning["question"], text="alice's") == {
        "ok": False,
        "why": "already answered by bob",
    }
    reviewing = alice.asked("reviewer")
    alice.asks(do="answer", question=reviewing["question"], text="ok")

    assert _result(workspace) == {"plan": "bob's", "review": "ok"}


@pytest.mark.timeout(60)
def test_a_claimant_that_leaves_leaves_its_question_to_the_others(
    host: Host, workspace: Path
) -> None:
    """Nothing is asked again: the question stays up, and is anybody's now."""
    alice, bob = Told(host, "alice"), Told(host, "bob")
    alice.asks(do="claim", role="planner")
    _asks(bob)
    planning = bob.asked("planner")
    assert not bob.asks(do="answer", question=planning["question"], text="x")["ok"]

    host.detach(alice.client)

    bob.waits(
        lambda one: (
            one["type"] == "pending"
            and [asked["owner"] for asked in one["pending"]] == [None]
        )
    )
    assert bob.asks(do="answer", question=planning["question"], text="taken over")["ok"]
    asked = [one for one in bob.records() if one["type"] == "asked"]
    assert len(asked) == 1
    reviewing = bob.asked("reviewer")
    bob.asks(do="answer", question=reviewing["question"], text="fine")
    assert _result(workspace)["plan"] == "taken over"


@pytest.mark.timeout(60)
def test_a_role_left_away_is_not_waited_on_after_its_frontend_has_gone(
    host: Host, workspace: Path
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    alice.asks(do="claim", role="planner")
    alice.asks(do="afk", on=True, role="planner")
    host.detach(alice.client)

    _asks(bob)
    reviewing = bob.asked("reviewer")
    bob.asks(do="answer", question=reviewing["question"], text="fine")

    # Answered for at once, as an away outworlder is: with nothing.
    assert _result(workspace) == {"plan": "", "review": "fine"}
    assert [one["role"] for one in bob.records() if one["type"] == "asked"] == [
        "reviewer"
    ]


@pytest.mark.timeout(60)
def test_a_line_waiting_when_the_question_comes_is_its_answer(
    host: Host, workspace: Path
) -> None:
    """What to say next is the next line said, one said before it was asked included."""
    alice = Told(host, "alice")
    alice.asks(do="afk", on=True, role="reviewer")
    alice.asks(do="claim", role="planner")
    _asks(alice)
    planning = alice.asked("planner")
    assert planning["mode"] == "listen"

    assert alice.asks(do="say", text="the typed plan")["ok"]

    assert _result(workspace)["plan"] == "the typed plan"
    answered = alice.told("answered", role="planner")
    assert (answered["by"], answered["client"]) == ("alice", alice.client)


# ------------------------------------------------------------------ what opened


@pytest.mark.timeout(60)
def test_a_session_opened_says_which_environment_it_works_in(
    host: Host, workspace: Path
) -> None:
    """What the monitor hangs a session's environment under it by: the role, and where."""
    alice = Told(host, "alice")
    _steers(alice)
    (workspace / "start").write_text("")

    opened = alice.told("opened", key="coder/1")
    assert opened["env"] == {
        "role": "workspace",
        "kind": "local",
        "target": "",
        "workdir": str(workspace),
        "anchored": False,
    }


# ------------------------------------------------------------------------ lines


@pytest.mark.timeout(60)
def test_a_line_said_before_any_turn_is_folded_into_the_turn_that_starts(
    host: Host, workspace: Path
) -> None:
    alice = Told(host, "alice")
    _steers(alice)
    alice.told("started")

    assert alice.asks(do="say", text="# and keep going")["ok"]
    (workspace / "start").write_text("")

    begins = alice.told("event", kind="begins")
    assert begins["text"].endswith("\n\n# and keep going")
    assert begins["key"] == begins["session"] == "coder/1"
    said = alice.told("said", text="# and keep going")
    assert (said["key"], said["by"]) == ("coder/1", "alice")
    alice.told("waiting", queued=[], given=[])


@pytest.mark.timeout(60)
def test_a_line_said_to_an_agent_while_a_person_is_asked_goes_into_its_next_turn(
    host: Host, workspace: Path
) -> None:
    """Answering what the person was asked does not take the agent's next turn from it.

    The answer is what to say next, and a line said to the run at large waits for a turn of
    its own after it. One said to the agent by name is for the next turn it takes.
    """
    alice, bob = Told(host, "alice"), Told(host, "bob")
    alice.asks(do="claim", role="planner")
    said = alice.asks(
        do="start",
        flow="hands",
        task="echo done",
        agents={"coder": _driver()},
        budget={"cost": 1},
    )
    assert said["ok"], said
    planning = alice.asked("planner")
    assert planning["mode"] == "listen"

    assert bob.asks(do="say", text="# and keep going", to="coder")["ok"]
    assert alice.asks(do="answer", question=planning["question"], text="left")["ok"]

    begins = alice.told("event", kind="begins")
    assert begins["text"] == "echo done\n\n# and keep going"
    folded = alice.told("said", text="# and keep going")
    assert (folded["key"], folded["by"]) == ("coder/1", "bob")
    assert _result(workspace) == {"plan": "left", "said": "done"}
    alice.told("ended", how="done")
    assert not [one for one in alice.records() if one["type"] == "dropped"]


@pytest.mark.timeout(60)
def test_a_line_said_into_an_open_turn_is_said_once_the_agent_has_it(
    host: Host, workspace: Path
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    _steers(alice)
    (workspace / "start").write_text("")
    alice.told("event", kind="begins")

    assert bob.asks(do="say", text="look at the tests", to="coder/1")["ok"]

    said = alice.told("said", text="look at the tests")
    assert (said["key"], said["by"], said["client"]) == ("coder/1", "bob", bob.client)
    took = alice.told("event", kind="took")
    assert took["seq"] < said["seq"]


@pytest.mark.timeout(60)
def test_a_line_the_agent_refused_goes_back_to_the_head_of_the_queue(
    host: Host, workspace: Path
) -> None:
    alice = Told(host, "alice")
    _steers(alice)
    (workspace / "start").write_text("")
    alice.told("event", kind="begins")

    alice.asks(do="say", text="refuse this")

    refused = alice.told("refused", text="refuse this")
    assert (refused["agent"], refused["because"]) == ("coder", "not now")
    alice.waits(
        lambda one: (
            one["type"] == "waiting"
            and [line["text"] for line in one["queued"]] == ["refuse this"]
            and not one["given"]
        )
    )


@pytest.mark.timeout(60)
def test_a_line_a_turn_ended_holding_is_said_to_have_been_held(
    host: Host, workspace: Path
) -> None:
    alice = Told(host, "alice")
    _steers(alice)
    (workspace / "start").write_text("")
    alice.told("event", kind="begins")
    alice.asks(do="say", text="hold this")
    alice.waits(
        lambda one: (
            one["type"] == "waiting"
            and [line["text"] for line in one["given"]] == ["hold this"]
        )
    )

    (workspace / "go").write_text("")

    unheld = alice.told("unheld")
    assert unheld["texts"] == ["hold this"]
    alice.told("ended", how="done")


@pytest.mark.timeout(60)
def test_stopping_drops_what_was_waiting_and_takes_the_question_back(
    host: Host, workspace: Path
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    _steers(alice)
    (workspace / "start").write_text("")
    alice.told("event", kind="begins")
    (workspace / "ask").write_text("")
    asked = alice.told("asked", role="planner")
    # Asked while a turn is open, so a line typed now would be the turn's: it is answered.
    assert asked["mode"] == "ask"
    alice.asks(do="say", text="hold this")
    alice.asks(do="say", text="and this")
    alice.waits(lambda one: one["type"] == "waiting" and one["given"] and one["queued"])

    assert bob.asks(do="stop")["ok"]

    assert alice.told("stopping")["by"] == "bob"
    assert alice.told("withdrawn", question=asked["question"])["why"] == "over"
    dropped = alice.told("dropped")
    assert dropped["because"] == "stopped"
    assert [one["text"] for one in dropped["given"]] == ["hold this"]
    assert [one["text"] for one in dropped["queued"]] == ["and this"]
    assert alice.told("ended")["how"] == "stopped"
    assert bob.asks(do="stop")["ok"] is False


@pytest.mark.timeout(60)
def test_forcing_closes_the_conversations_still_working(
    host: Host, workspace: Path
) -> None:
    alice = Told(host, "alice")
    _steers(alice)
    (workspace / "start").write_text("")
    alice.told("event", kind="begins")

    said = alice.asks(do="force")

    assert said == {"ok": True, "closed": 1}
    assert alice.told("ended")["how"] == "stopped"


# ---------------------------------------------------------------- arriving late


@pytest.mark.timeout(60)
def test_a_late_frontend_reads_the_run_exactly_as_the_first_did(
    host: Host, workspace: Path
) -> None:
    alice = Told(host, "alice")
    _asks(alice)
    for role, text in (("planner", "a plan"), ("reviewer", "fine")):
        alice.asks(do="answer", question=alice.asked(role)["question"], text=text)
    alice.told("ended")

    late = Told(host, "late")
    live = late.told("live")

    assert late.records() == alice.records()
    assert live["seq"] == alice.records()[-1]["seq"]
    assert late.records()[0]["type"] == "started"
    assert late.records()[0]["by"] == "alice"


@pytest.mark.timeout(60)
def test_a_frontend_whose_listener_blocks_holds_up_neither_the_run_nor_the_others(
    host: Host, workspace: Path
) -> None:
    stuck = threading.Event()

    def blocks(_said: dict[str, Any]) -> None:
        stuck.wait(PATIENCE)

    host.attach("stuck", "sdk", blocks)
    alice = Told(host, "alice")
    _asks(alice)
    for role, text in (("planner", "a plan"), ("reviewer", "fine")):
        alice.asks(do="answer", question=alice.asked(role)["question"], text=text)

    assert _result(workspace) == {"plan": "a plan", "review": "fine"}
    alice.told("ended", how="done")
    stuck.set()


# ------------------------------------------------------------------------ asides


@pytest.mark.timeout(60)
def test_an_aside_is_a_read_only_copy_the_run_never_hears_from(
    host: Host, workspace: Path
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    _steers(alice)
    (workspace / "start").write_text("")
    alice.told("event", kind="begins")

    opened = alice.asks(do="aside", key="coder/1", fork=True)

    # A shell cannot fork, so it is a copy of the agent, told what it is about by whoever
    # asked -- and not one that may write.
    assert opened["forked"] is False
    side = host._asides[opened["side"]]
    assert side.session._agent.config.permission == "read-only"
    assert side.session._agent.config.goals is False
    answered = alice.asks(do="aside", side=opened["side"], prompt="echo from the side")
    assert answered == {"ok": True, "answer": "from the side"}
    assert bob.asks(do="aside", side=opened["side"], prompt="echo x") == {
        "ok": False,
        "why": f"no aside {opened['side']} is open",
    }
    assert not [one for one in alice.records() if "from the side" in str(one)]
    assert alice.asks(do="unaside", side=opened["side"])["ok"]
    assert opened["side"] not in host._asides


@pytest.mark.timeout(60)
def test_an_aside_on_a_conversation_that_forks_carries_its_history(
    host: Host, workspace: Path
) -> None:
    alice = Told(host, "alice")
    _steers(alice, ForkingAgent)
    (workspace / "start").write_text("")
    alice.told("event", kind="begins")

    opened = alice.asks(do="aside", key="coder/1", fork=True)

    assert opened["forked"] is True
    assert host._asides[opened["side"]].session._agent.config.permission == "read-only"
    assert alice.asks(do="aside", key="coder/9") == {
        "ok": False,
        "why": "coder/9 has no conversation to ask",
    }


@pytest.mark.timeout(60)
def test_the_asides_of_a_frontend_that_goes_are_closed_with_it(
    host: Host, workspace: Path
) -> None:
    alice = Told(host, "alice")
    _steers(alice)
    (workspace / "start").write_text("")
    alice.told("event", kind="begins")
    opened = alice.asks(do="aside", key="coder/1")

    host.detach(alice.client)

    assert opened["side"] not in host._asides
