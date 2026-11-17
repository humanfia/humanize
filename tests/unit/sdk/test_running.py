"""`hmz.sdk.Run`: one epic held by a daemon and followed, the daemon a stand-in."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import BudgetExceeded
from hmz.sdk import Refused, Run
from hmz.sdk.running import Opened, Runner, backed

if TYPE_CHECKING:
    from collections.abc import Callable

#: What the daemon's check answered of the epic.
_CHECKED: dict[str, Any] = {
    "flow": "asks",
    "ref": "asks:asks",
    "declared": {
        "agents": [{"name": "coder", "auto": False}, {"name": "human", "auto": True}]
    },
    "names": {"coder": "NeiKos"},
    "budget": {"cost": 1.0},
    "backup": [],
    "unreadable": "",
}

#: What `epic.start` is called with, but the task.
_STARTED: dict[str, Any] = {
    "flow": "asks",
    "agents": {"coder": "claude/m"},
    "envs": {},
    "params": None,
    "budget": {"cost": 1.0},
    "profile_flow": False,
    "profile_environment": False,
    "resume": False,
    "backup": None,
}


class _Daemon:
    """A daemon's session: each call written down, an epic's messages told when asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.listener: Callable[[str, dict[str, Any]], None] | None = None
        self.closed = False
        self.refusing: dict[str, Refused] = {}
        self.answered = threading.Event()
        #: What `runs.get` says each time it is asked, the last for good.
        self.rows: list[dict[str, Any]] = [{}]
        self.gone = threading.Event()

    def heard(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        self.listener = listener

    def call(
        self, method: str, params: dict[str, Any] | None = None, **said: Any
    ) -> Any:
        self.asked.append((method, dict(params or {})))
        if method in self.refusing:
            raise self.refusing[method]
        if method == "epic.answer":
            self.answered.set()
        if method == "epic.attach":
            return {"sub": "s1", "slot": "exec:ab12", "client": "c1"}
        if method == "runs.get":
            return self.rows.pop(0) if len(self.rows) > 1 else self.rows[0]
        return {}

    def wait(self, timeout: float | None = None) -> bool:
        del timeout
        return self.closed

    def close(self) -> None:
        self.closed = True
        self.gone.set()

    def tells(self, **message: Any) -> None:
        assert self.listener is not None
        self.listener("epic.event", {"sub": "s1", "message": message})

    def methods(self) -> list[str]:
        return [method for method, _ in self.asked]


class _Runner(Runner):
    def __init__(self, daemon: _Daemon) -> None:
        super().__init__("/w", dict(_STARTED), dict(_CHECKED), None)
        self._daemon = daemon

    def client(self) -> Any:
        return self._daemon


@pytest.fixture
def daemon() -> _Daemon:
    return _Daemon()


def test_a_run_is_what_the_check_answered_and_nothing_is_started(
    daemon: _Daemon,
) -> None:
    run = Run(_Runner(daemon), "do it")

    assert (run.flow, run.ref, run.task) == ("asks", "asks:asks", "do it")
    # A chat is not a flow, so no run of one is a chat.
    assert not hasattr(run, "chats")
    assert run.names == {"coder": "NeiKos"}
    assert run.budget.cost == 1.0
    assert (run.epic, run.running, run.raised, run.result) == (None, False, None, None)
    assert daemon.asked == []


def test_starting_attaches_a_new_exec_slot_sets_everyone_away_and_starts(
    daemon: _Daemon,
) -> None:
    run = Run(_Runner(daemon), "do it")
    run.start()

    assert daemon.asked[0] == (
        "epic.attach",
        {"workspace": "/w", "slot": "exec:", "since": None},
    )
    assert daemon.asked[1] == ("epic.afk", {"sub": "s1", "on": True})
    method, params = daemon.asked[2]
    assert (method, params["task"], params["agents"]) == (
        "epic.start",
        "do it",
        {"coder": "claude/m"},
    )
    assert run.running
    with pytest.raises(RuntimeError):
        run.start()


def test_a_start_refused_is_raised_and_the_daemon_let_go(daemon: _Daemon) -> None:
    daemon.refusing["epic.start"] = Refused("a flow is already running", code=409)
    run = Run(_Runner(daemon), "do it")

    with pytest.raises(Refused, match="already running"):
        run.start()
    assert daemon.closed


def test_the_epic_is_told_as_it_happens_and_returns_what_it_ended_with(
    daemon: _Daemon,
) -> None:
    run = Run(_Runner(daemon), "do it")
    watched: list[tuple[str, str | None, str]] = []
    opened: list[tuple[str, Opened]] = []
    noticed: list[str] = []
    run.watch(lambda agent, key, said: watched.append((agent, key, said["kind"])))
    run.opened(lambda role, one: opened.append((role, one)))
    run.noticed(noticed.append)
    run.start()

    daemon.tells(type="welcome", epoch="e1")
    daemon.tells(type="run", seq=1, epic="2026-x")
    daemon.tells(
        type="opened", seq=2, role="coder", key="NeiKos/1", agent="NeiKos", cli="claude"
    )
    daemon.tells(type="sessions", seq=3, open=["NeiKos/1"], working=[])
    daemon.tells(type="event", seq=4, agent="NeiKos", session="NeiKos/1", kind="text")
    daemon.tells(type="event", seq=5, agent="NeiKos", session="", kind="notice")
    daemon.tells(type="notice", seq=6, text="moved to docker")
    daemon.tells(type="ended", seq=7, how="done", why="", result={"ok": 1})

    assert run.wait(5)
    assert run.result == {"ok": 1}
    assert run.raised is None
    assert not run.running
    assert watched == [("NeiKos", "NeiKos/1", "text"), ("NeiKos", None, "notice")]
    ((role, one),) = opened
    assert (role, one.key, one.agent, one.cli) == (
        "coder",
        "NeiKos/1",
        "NeiKos",
        "claude",
    )
    assert run.agents == (one,)
    assert noticed == ["moved to docker"]
    assert run.epic is not None
    assert run.epic.name == "2026-x"
    assert daemon.gone.wait(5)


@pytest.mark.parametrize(
    ("how", "raised"),
    [
        ("stopped", asyncio.CancelledError),
        ("budget", BudgetExceeded),
        ("refused", Refused),
        ("failed", RuntimeError),
        ("crashed", RuntimeError),
    ],
)
def test_an_epic_that_did_not_finish_raises_what_its_end_says(
    daemon: _Daemon, how: str, raised: type[BaseException]
) -> None:
    run = Run(_Runner(daemon), "do it")

    def ends() -> None:
        while "epic.start" not in daemon.methods():
            threading.Event().wait(0.01)
        daemon.tells(type="ended", how=how, why="why it ended", result=None)

    threading.Thread(target=ends, daemon=True).start()
    with pytest.raises(raised):
        run.run()
    assert isinstance(run.raised, raised)


class _Person:
    """Whoever is outside: away for one role, answering the others."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []

    def away_for(self, role: str) -> bool:
        return role == "nobody"

    async def run(self, prompt: str, output_schema: object, role: str) -> str:
        del output_schema
        self.asked.append((prompt, role))
        return f"yes to {prompt}"


def test_an_outworlder_claims_its_roles_and_answers_their_questions(
    daemon: _Daemon,
) -> None:
    person = _Person()
    run = Run(_Runner(daemon), "do it", outworlder=person)
    run.start()

    assert ("epic.claim", {"sub": "s1", "role": "human"}) in [
        (method, {key: value for key, value in params.items() if key != "idem"})
        for method, params in daemon.asked
    ]
    assert "epic.afk" not in daemon.methods()
    daemon.tells(type="asked", question="q1", role="human", text="ship it?")

    assert daemon.answered.wait(5)
    assert person.asked == [("ship it?", "human")]
    method, params = daemon.asked[-1]
    assert (method, params["question"], params["text"]) == (
        "epic.answer",
        "q1",
        "yes to ship it?",
    )


def test_stopping_asks_the_epic_to_stop_and_closing_forces_it(daemon: _Daemon) -> None:
    run = Run(_Runner(daemon), "do it")
    run.start()

    run.stop()
    run.close()

    assert daemon.methods()[-2:] == ["epic.stop", "epic.force"]
    assert daemon.closed
    assert run.wait(0)


def test_an_epic_that_ended_is_followed_until_its_backups_are_done(
    daemon: _Daemon,
) -> None:
    undone: dict[str, Any] = {"backup": ["origin"], "backed": {}}
    done: dict[str, Any] = {"backup": ["origin"], "backed": {"origin": {"ok": True}}}
    daemon.rows = [undone, undone, done]
    run = Run(_Runner(daemon), "do it")
    run.start()
    daemon.tells(type="run", seq=1, epic="2026-x")
    daemon.tells(type="ended", seq=2, how="done", why="", result=None)

    assert run.wait(5)
    assert daemon.gone.wait(5)
    assert daemon.methods().count("runs.get") == 3
    assert ("runs.get", {"name": "2026-x"}) in daemon.asked


def test_closing_an_epic_that_ended_lets_go_without_waiting_for_its_backups(
    daemon: _Daemon,
) -> None:
    daemon.rows = [{"backup": ["origin"], "backed": {}}]
    run = Run(_Runner(daemon), "do it")
    run.start()
    daemon.tells(type="run", seq=1, epic="2026-x")
    daemon.tells(type="ended", seq=2, how="done", why="", result=None)
    assert run.wait(5)
    assert not daemon.gone.wait(0.2)

    run.close()
    assert daemon.closed


def test_a_backup_from_before_the_epic_ended_is_not_the_one_its_end_queued(
    daemon: _Daemon,
) -> None:
    def row(at: str) -> dict[str, Any]:
        return {
            "ended": "2026-11-17T00:00:01.000Z",
            "backup": ["origin"],
            "backed": {"origin": {"at": at, "ok": True}},
        }

    client = cast("Any", daemon)
    daemon.rows = [row("2026-11-17T00:00:00.000Z")]
    assert not backed(client, "e")
    daemon.rows = [row("2026-11-17T00:00:02.000Z")]
    assert backed(client, "e")
    daemon.refusing["runs.get"] = Refused("There is no epic e.", code=404)
    assert backed(client, "e")
