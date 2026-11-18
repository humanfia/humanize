"""`hmz.sdk.Run`: one epic held by a daemon and followed, the daemon a stand-in."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import TYPE_CHECKING, Any, cast

import pydantic
import pytest

from hmz.flows import BudgetExceeded
from hmz.sdk import Ask, Refused, Run
from hmz.sdk.running import Opened, Runner, backed

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

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
        #: Refusals said once each, in turn, before the call is taken.
        self.refusing_once: dict[str, list[Refused]] = {}
        self.answered = threading.Event()
        self.called = threading.Condition()
        #: What `runs.get` says each time it is asked, the last for good.
        self.rows: list[dict[str, Any]] = [{}]
        #: The policies of each backup target `settings.get` says.
        self.policies: dict[str, list[str]] = {"origin": ["end"]}
        self.gone = threading.Event()

    def heard(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        self.listener = listener

    def call(
        self, method: str, params: dict[str, Any] | None = None, **said: Any
    ) -> Any:
        with self.called:
            self.asked.append((method, dict(params or {})))
            self.called.notify_all()
        if method in self.refusing:
            raise self.refusing[method]
        if self.refusing_once.get(method):
            raise self.refusing_once[method].pop(0)
        if method == "epic.answer":
            self.answered.set()
        if method == "epic.attach":
            return {"sub": "s1", "slot": "exec:ab12", "client": "c1"}
        if method == "runs.get":
            return self.rows.pop(0) if len(self.rows) > 1 else self.rows[0]
        if method == "settings.get":
            targets = [
                {"name": name, "policies": policies}
                for name, policies in self.policies.items()
            ]
            return {"backup": {"targets": targets, "defaults": []}}
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

    def calls(self, method: str, count: int) -> list[dict[str, Any]]:
        """The params of the first `count` calls of `method`, once that many were made."""
        with self.called:
            assert self.called.wait_for(
                lambda: self.methods().count(method) >= count, timeout=5
            )
            return [params for one, params in self.asked if one == method][:count]


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
    """Whoever is outside: away for one role, answering the others with what it is given."""

    def __init__(
        self, *replies: str | pydantic.BaseModel | Mapping[str, Any] | None
    ) -> None:
        self.asked: list[tuple[Ask, str]] = []
        self.shown: list[tuple[tuple[dict[str, Any], ...], str, str]] = []
        self._replies = list(replies)

    def away_for(self, role: str) -> bool:
        return role == "nobody"

    async def run(
        self, ask: Ask, role: str
    ) -> str | pydantic.BaseModel | Mapping[str, Any]:
        self.asked.append((ask, role))
        if self._replies:
            reply = self._replies.pop(0)
            if reply is None:
                raise RuntimeError("nothing to say")
            return reply
        return f"yes to {ask.prompt}"

    def show(
        self, context: tuple[dict[str, Any], ...], session: str, role: str
    ) -> None:
        self.shown.append((context, session, role))


class _Review(pydantic.BaseModel):
    verdict: str
    notes: str = ""


_SCHEMA: dict[str, Any] = _Review.model_json_schema()

_DIFF: dict[str, Any] = {
    "kind": "diff",
    "patch": "--- a\n+++ b\n",
    "title": "the change",
}


def _misfit(message: str) -> Refused:
    return Refused(
        f"the answer does not fit: {message}",
        code=400,
        data={"errors": [{"path": ["verdict"], "message": message}]},
    )


def _started(daemon: _Daemon, person: _Person) -> Run:
    run = Run(_Runner(daemon), "do it", outworlder=person)
    run.start()
    return run


@pytest.mark.parametrize("why", ["the host went away", "let go", ""])
def test_a_host_that_lets_go_before_the_end_ends_the_run_with_why(
    daemon: _Daemon, why: str
) -> None:
    run = Run(_Runner(daemon), "do it")
    run.start()
    daemon.tells(type="welcome", epoch="e1")
    daemon.tells(type="run", seq=1, epic="2026-x")

    daemon.tells(type="gone", why=why)

    assert run.wait(5)
    assert isinstance(run.raised, RuntimeError)
    assert str(run.raised) == (why or "the host went away")
    assert run.result is None


def test_a_host_that_lets_go_after_the_end_leaves_what_the_epic_ended_with(
    daemon: _Daemon,
) -> None:
    run = Run(_Runner(daemon), "do it")
    run.start()
    daemon.tells(type="ended", seq=1, how="done", why="", result={"ok": 1})

    daemon.tells(type="gone", why="the host was closed")

    assert run.wait(5)
    assert run.raised is None
    assert run.result == {"ok": 1}


class _Sessions(Runner):
    """A runner whose every session with the daemon is another stand-in, in turn."""

    def __init__(self, *daemons: _Daemon) -> None:
        super().__init__("/w", dict(_STARTED), dict(_CHECKED), None)
        self._daemons = list(daemons)

    def client(self) -> Any:
        return self._daemons.pop(0)


def test_a_run_let_go_of_for_falling_behind_attaches_again_and_claims_again() -> None:
    first, second = _Daemon(), _Daemon()
    run = Run(_Sessions(first, second), "do it", outworlder=_Person())
    run.start()
    first.tells(type="welcome", epoch="e1")
    first.tells(type="run", seq=4, epic="2026-x")

    first.tells(type="gone", why="too far behind; attach again")

    (claimed,) = second.calls("epic.claim", 1)
    assert claimed["role"] == "human"
    (attached,) = second.calls("epic.attach", 1)
    assert attached["since"] == {"epoch": "e1", "seq": 4}
    assert first.gone.wait(5)
    assert not run.wait(0)
    second.tells(type="ended", seq=5, how="done", why="", result=7)
    assert run.wait(5)
    assert run.result == 7
    assert run.raised is None


def test_a_run_attached_again_to_another_life_of_its_host_ends_as_the_daemon_gone() -> (
    None
):
    first, second = _Daemon(), _Daemon()
    run = Run(_Sessions(first, second), "do it")
    run.start()
    first.tells(type="welcome", epoch="e1")
    first.tells(type="run", seq=4, epic="2026-x")

    first.close()
    (attached,) = second.calls("epic.attach", 1)
    assert attached["since"] == {"epoch": "e1", "seq": 4}
    # A daemon started since holds no such epic: the slot's host is a new one, and idle.
    second.tells(type="welcome", epoch="e2")
    second.tells(type="live", seq=0, elided=0)

    assert run.wait(5)
    assert isinstance(run.raised, RuntimeError)
    assert str(run.raised) == "the daemon went away"
    assert run.result is None
    assert second.gone.wait(5)


def test_an_outworlder_claims_its_roles_and_answers_their_questions(
    daemon: _Daemon,
) -> None:
    person = _Person()
    _started(daemon, person)

    assert ("epic.claim", {"sub": "s1", "role": "human"}) in [
        (method, {key: value for key, value in params.items() if key != "idem"})
        for method, params in daemon.asked
    ]
    assert "epic.afk" not in daemon.methods()
    daemon.tells(type="asked", question="q1", role="human", text="ship it?")

    assert daemon.answered.wait(5)
    ((ask, role),) = person.asked
    assert (ask.prompt, ask.schema, ask.model, ask.context, role) == (
        "ship it?",
        None,
        None,
        (),
        "human",
    )
    assert (ask.face, ask.session, ask.errors) == ("", "", ())
    method, params = daemon.asked[-1]
    assert (method, params["question"], params["text"]) == (
        "epic.answer",
        "q1",
        "yes to ship it?",
    )
    assert "value" not in params


def test_a_schema_question_is_asked_whole_with_its_context_and_answered_with_a_value(
    daemon: _Daemon,
) -> None:
    person = _Person({"verdict": "approve", "notes": "LGTM"})
    _started(daemon, person)

    daemon.tells(
        type="asked",
        question="q1",
        role="human",
        text="review this",
        options=[],
        schema=_SCHEMA,
        context=[_DIFF],
        face={"hash": "ab12", "title": "review"},
        session="human/1",
    )

    (params,) = daemon.calls("epic.answer", 1)
    ((ask, _),) = person.asked
    assert (ask.prompt, ask.schema, ask.model) == ("review this", _SCHEMA, None)
    assert (ask.context, ask.face, ask.session) == ((_DIFF,), "ab12", "human/1")
    assert params["value"] == {"verdict": "approve", "notes": "LGTM"}
    assert "text" not in params


def test_a_model_answer_is_sent_as_its_json_value(daemon: _Daemon) -> None:
    person = _Person(_Review(verdict="reject"))
    _started(daemon, person)

    daemon.tells(type="asked", question="q1", role="human", text="?", schema=_SCHEMA)

    (params,) = daemon.calls("epic.answer", 1)
    assert params["value"] == {"verdict": "reject", "notes": ""}


def test_a_mapping_answering_a_text_question_is_sent_as_its_json_text(
    daemon: _Daemon,
) -> None:
    person = _Person({"pick": 2})
    _started(daemon, person)

    daemon.tells(type="asked", question="q1", role="human", text="which?")

    (params,) = daemon.calls("epic.answer", 1)
    assert json.loads(params["text"]) == {"pick": 2}
    assert "value" not in params


def test_an_answer_that_does_not_fit_is_asked_again_with_what_did_not_fit(
    daemon: _Daemon,
) -> None:
    daemon.refusing_once["epic.answer"] = [_misfit("must be approve or reject")]
    person = _Person({"verdict": "maybe"}, {"verdict": "approve"})
    _started(daemon, person)

    daemon.tells(type="asked", question="q1", role="human", text="?", schema=_SCHEMA)

    first, second = daemon.calls("epic.answer", 2)
    assert first["value"] == {"verdict": "maybe"}
    assert second["value"] == {"verdict": "approve"}
    (_, retried) = [ask for ask, _ in person.asked]
    assert retried.errors == (
        {"path": ["verdict"], "message": "must be approve or reject"},
    )
    assert retried.prompt == "?"
    assert "epic.afk" not in daemon.methods()


def test_three_answers_that_do_not_fit_answer_the_question_as_away(
    daemon: _Daemon,
) -> None:
    daemon.refusing_once["epic.answer"] = [_misfit("no")] * 3
    person = _Person({"verdict": 1}, {"verdict": 2}, {"verdict": 3})
    _started(daemon, person)

    daemon.tells(type="asked", question="q1", role="human", text="?", schema=_SCHEMA)

    on, off = daemon.calls("epic.afk", 2)
    assert (on["on"], on["role"], off["on"], off["role"]) == (
        True,
        "human",
        False,
        "human",
    )
    assert daemon.methods().count("epic.answer") == 3
    assert len(person.asked) == 3


def test_an_answer_refused_for_another_reason_is_not_asked_again(
    daemon: _Daemon,
) -> None:
    daemon.refusing_once["epic.answer"] = [Refused("no question q1", code=404)]
    person = _Person({"verdict": "approve"})
    _started(daemon, person)

    daemon.tells(type="asked", question="q1", role="human", text="?", schema=_SCHEMA)

    daemon.calls("epic.answer", 1)
    with daemon.called:
        assert not daemon.called.wait_for(
            lambda: len(daemon.asked) > daemon.methods().index("epic.answer") + 1,
            timeout=0.3,
        )
    assert len(person.asked) == 1


def test_an_outworlder_with_nothing_to_say_answers_as_away(daemon: _Daemon) -> None:
    person = _Person(None)
    _started(daemon, person)

    daemon.tells(type="asked", question="q1", role="human", text="?")

    on, off = daemon.calls("epic.afk", 2)
    assert (on["on"], off["on"]) == (True, False)
    assert "epic.answer" not in daemon.methods()


def test_a_value_that_is_not_json_is_not_sent_and_answers_as_away(
    daemon: _Daemon,
) -> None:
    person = _Person({"verdict": {"a", "set"}})
    _started(daemon, person)

    daemon.tells(type="asked", question="q1", role="human", text="?", schema=_SCHEMA)

    on, _ = daemon.calls("epic.afk", 2)
    assert on["on"] is True
    assert "epic.answer" not in daemon.methods()


def test_context_shown_to_a_claimed_role_is_handed_to_show(daemon: _Daemon) -> None:
    person = _Person()
    _started(daemon, person)

    daemon.tells(
        type="shown", run="r", role="human", session="human/1", context=[_DIFF]
    )
    daemon.tells(type="shown", run="r", role="coder", session="NeiKos/1", context=[])

    assert person.shown == [((_DIFF,), "human/1", "human")]


def test_context_shown_to_an_outworlder_without_show_is_let_be(
    daemon: _Daemon,
) -> None:
    class _Plain:
        def away_for(self, role: str) -> bool:
            del role
            return False

        async def run(self, ask: Ask, role: str) -> str:
            del ask, role
            return "ok"

    run = Run(_Runner(daemon), "do it", outworlder=_Plain())
    run.start()

    daemon.tells(
        type="shown", run="r", role="human", session="human/1", context=[_DIFF]
    )
    daemon.tells(type="asked", question="q1", role="human", text="?")

    (params,) = daemon.calls("epic.answer", 1)
    assert params["text"] == "ok"


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


@pytest.mark.parametrize("policies", [[], ["interval"], ["session"], None])
def test_a_target_the_end_of_an_epic_queues_no_backup_to_is_not_waited_on(
    daemon: _Daemon, policies: list[str] | None
) -> None:
    daemon.rows = [
        {
            "workspace": "/w",
            "ended": "2026-11-17T00:00:01.000Z",
            "backup": ["origin", "aside"],
            "backed": {"origin": {"at": "2026-11-17T00:00:02.000Z", "ok": True}},
        }
    ]
    # Backed up to by hand only, or as it runs, or one settings holds no longer.
    daemon.policies = {"origin": ["end"]} | (
        {} if policies is None else {"aside": policies}
    )
    assert backed(cast("Any", daemon), "e")
    assert ("settings.get", {"workspace": "/w"}) in daemon.asked

    daemon.policies["aside"] = ["session", "end"]
    assert not backed(cast("Any", daemon), "e")
