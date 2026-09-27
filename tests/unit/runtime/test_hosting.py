"""The runs of a workspace as every frontend attached to them shares them, with no run going.

What a frontend is told and in what order, what it may claim and what it may say it is away
for, and what becomes of one that stops taking what it is told -- all of which is the host's
own bookkeeping, and none of which needs a flow. What a run does to it is
`tests/integration/runtime/test_hosting.py`.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import AgentConfig, Event
from hmz.coganchor.agents.event import Usage
from hmz.runtime import Hmz, Host
from hmz.runtime.doing import hosting
from hmz.runtime.doing.hosting import record
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

#: How long a test waits for something another thread is doing.
PATIENCE = 10.0

#: Every key an event record has, as the frontends and `hmz exec --json` read it.
EVENT = {
    "type",
    "run",
    "key",
    "session",
    "agent",
    "cli",
    "model",
    "ident",
    "kind",
    "text",
    "whose",
    "tokens",
    "spent",
    "at",
    "mono",
}


class Told:
    """One frontend's end: everything it has been told, in the order it was told."""

    def __init__(self, host: Host, name: str, *, replay: bool = True) -> None:
        self.seen: list[dict[str, Any]] = []
        self._landed = threading.Condition()
        self.client = host.attach(name, "sdk", self._told, replay=replay)

    def _told(self, message: dict[str, Any]) -> None:
        with self._landed:
            self.seen.append(message)
            self._landed.notify_all()

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


@pytest.fixture
def host() -> Iterator[Host]:
    held = Hmz().host()
    try:
        yield held
    finally:
        held.close()


def _agent() -> ShellAgent:
    return ShellAgent(AgentConfig(model="m", effort="high"), name="builder")


# ------------------------------------------------------------------------ the record


def test_an_event_is_written_down_once_for_every_frontend_and_for_exec() -> None:
    said = record(
        _agent(),
        None,
        Event(kind="result", text="done", tokens={"m": 30}, spent=Usage(input=30)),
        key="builder",
        run=3,
    )

    assert set(said) == EVENT
    assert said["type"] == "event"
    assert (said["run"], said["key"], said["agent"]) == (3, "builder", "builder")
    assert (said["cli"], said["model"]) == ("shell", "m")
    assert (said["kind"], said["text"]) == ("result", "done")
    assert said["tokens"] == {"m": 30}
    assert said["spent"] == {"input": 30}
    # Said by the agent rather than one of its conversations: no session, and no ident.
    assert (said["session"], said["ident"]) == ("", "")


def test_a_conversation_is_named_by_its_key_and_the_backend_by_its_own() -> None:
    agent = _agent()
    conversation = agent.new()

    said = record(agent, conversation, Event(kind="begins", text=""), key="builder/2")

    assert said["session"] == "builder/2"
    # Nothing until the backend has named it, which a first turn does.
    assert said["ident"] == ""


# -------------------------------------------------------------------- what is told


def test_a_frontend_is_told_who_it_is_then_the_run_then_how_things_stand(
    host: Host,
) -> None:
    host.printed("before anybody")
    host.printed("still nobody")

    alice = Told(host, "alice")
    alice.waits(lambda one: one["type"] == "live")

    kinds = [one["type"] for one in alice.seen]
    assert kinds[0] == "welcome"
    assert alice.seen[0]["name"] == "alice"
    assert alice.seen[0]["client"] == alice.client
    assert alice.seen[0]["protocol"] == hosting.PROTOCOL
    # The history first, in the order it happened, then every snapshot, and `live` last.
    assert [one["text"] for one in alice.seen if one["type"] == "printed"] == [
        "before anybody",
        "still nobody",
    ]
    history = [
        one["seq"] for one in alice.seen if "seq" in one and one["type"] != "live"
    ]
    assert history == sorted(history)
    assert kinds.index("printed") < kinds.index("run") < kinds.index("live")
    assert {"clients", "claims", "away", "run", "sessions", "calls"} <= set(kinds)
    assert {"waiting", "pending", "usage", "board"} <= set(kinds)
    assert alice.seen[-1] == {"type": "live", "seq": 2, "elided": 0}


def test_a_frontend_that_asks_for_no_replay_is_told_only_how_things_stand(
    host: Host,
) -> None:
    host.printed("before anybody")

    bot = Told(host, "bot", replay=False)
    bot.waits(lambda one: one["type"] == "live")

    assert not [one for one in bot.seen if one["type"] == "printed"]


def test_what_is_kept_for_a_late_frontend_is_held_to_its_ceiling(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The oldest whole records go first, and are counted rather than lost without trace."""
    monkeypatch.setattr(hosting, "_KEPT", 400)
    for count in range(20):
        host.printed(f"line {count}")

    late = Told(host, "late")
    live = late.waits(lambda one: one["type"] == "live")

    kept = [one["text"] for one in late.seen if one["type"] == "printed"]
    assert kept
    assert kept[-1] == "line 19"
    assert live["elided"] == 20 - len(kept)
    assert live["seq"] == 20


def test_a_text_too_long_to_carry_is_cut_and_the_rest_counted(host: Host) -> None:
    host.printed("x" * (hosting._LONGEST + 12))

    said = Told(host, "alice").waits(lambda one: one["type"] == "printed")

    assert said["text"].endswith("… (12 more characters)")
    assert len(said["text"]) < hosting._LONGEST + 40


def test_the_same_name_twice_is_told_apart(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_NAME", "alice")

    first, second = Told(host, ""), Told(host, "")

    assert first.waits(lambda one: one["type"] == "welcome")["name"] == "alice@sdk"
    assert second.waits(lambda one: one["type"] == "welcome")["name"] == "alice@sdk#2"
    assert host.attached == 2


def test_a_frontend_that_stops_taking_what_it_is_told_holds_up_nobody(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Told on a thread of its own, and let go of once it is further behind than is kept."""
    monkeypatch.setattr(hosting, "_BEHIND", 1 << 14)
    stuck = threading.Event()
    blocked: list[dict[str, Any]] = []

    def blocks(message: dict[str, Any]) -> None:
        blocked.append(message)
        stuck.wait(PATIENCE)

    host.attach("stuck", "sdk", blocks)
    alice = Told(host, "alice")
    started = time.monotonic()
    for count in range(200):
        host.printed(f"line {count} " + "x" * 200)
        # Taken as it is said, so that only the one that takes nothing falls behind.
        alice.waits(lambda one, at=count: one.get("text", "").startswith(f"line {at} "))

    # Every one of them said without waiting on the frontend that took none of them.
    assert time.monotonic() - started < PATIENCE / 2
    alice.told(
        "clients", clients=[{"client": alice.client, "name": "alice", "kind": "sdk"}]
    )
    assert host.attached == 1
    stuck.set()
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline and blocked[-1]["type"] != "gone":
        time.sleep(0.01)
    assert blocked[-1] == {"type": "gone", "why": "too far behind; attach again"}


# ------------------------------------------------------------------------ claims


def test_a_role_is_held_by_one_frontend_at_a_time(host: Host) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")

    assert host.asked(alice.client, {"do": "claim", "role": "planner"})["ok"]
    refused = host.asked(bob.client, {"do": "claim", "role": "planner"})

    assert refused == {"ok": False, "why": "planner is alice's"}
    alice.told("claims", claims={"planner": alice.client})


def test_a_role_taken_over_is_said_to_the_frontend_it_was_taken_from(
    host: Host,
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    host.asked(alice.client, {"do": "claim", "role": "planner"})

    assert host.asked(bob.client, {"do": "claim", "role": "planner", "take": True})[
        "ok"
    ]

    alice.told("claims", claims={"planner": bob.client})


def test_only_its_claimant_gives_a_role_back(host: Host) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    host.asked(alice.client, {"do": "claim", "role": "planner"})

    assert not host.asked(bob.client, {"do": "release", "role": "planner"})["ok"]
    assert host.asked(alice.client, {"do": "release", "role": "planner"})["ok"]
    assert host.asked(bob.client, {"do": "claim", "role": "planner"})["ok"]


def test_a_frontend_that_goes_gives_its_roles_back(host: Host) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    host.asked(alice.client, {"do": "claim", "role": "planner"})

    host.detach(alice.client)

    assert host.asked(bob.client, {"do": "claim", "role": "planner"})["ok"]
    assert alice.waits(lambda one: one["type"] == "gone")["why"] == "let go"
    # And the others are told so, in the order it happened: held, given back, taken again.
    bob.told("claims", claims={"planner": bob.client})
    held = [one["claims"] for one in bob.seen if one["type"] == "claims"]
    assert held[-3:] == [{"planner": alice.client}, {}, {"planner": bob.client}]


# -------------------------------------------------------------------------- away


def test_away_with_nobody_holding_a_role_is_the_one_switch_it_always_was(
    host: Host,
) -> None:
    alice = Told(host, "alice")
    host.asked(alice.client, {"do": "afk", "on": False, "role": "planner"})

    host.asked(alice.client, {"do": "afk", "on": True})

    assert host.away_for("planner")
    assert host.away_for("reviewer")
    alice.told("away", all=True, of={})


def test_away_for_one_role_is_that_role_alone(host: Host) -> None:
    alice = Told(host, "alice")

    host.asked(alice.client, {"do": "afk", "on": True, "role": "planner"})

    assert host.away_for("planner")
    assert not host.away_for("reviewer")


def test_nobody_says_they_are_away_for_a_role_somebody_else_holds(host: Host) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    host.asked(alice.client, {"do": "claim", "role": "planner"})

    refused = host.asked(bob.client, {"do": "afk", "on": True, "role": "planner"})

    assert refused == {"ok": False, "why": "planner is alice's"}
    assert not host.away_for("planner")


def test_away_for_everything_leaves_the_roles_somebody_else_holds_as_they_were(
    host: Host,
) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")
    host.asked(alice.client, {"do": "claim", "role": "planner"})
    host.asked(bob.client, {"do": "claim", "role": "reviewer"})

    host.asked(bob.client, {"do": "afk", "on": True})

    assert host.away_for("reviewer")  # bob's own
    assert host.away_for("anything else")  # nobody's, so bob may speak for it
    assert not host.away_for("planner")  # alice's, which bob does not answer for


def test_away_outlives_the_frontend_that_said_it(host: Host) -> None:
    """`/afk` and then leaving still means nobody is waited on."""
    alice = Told(host, "alice")
    host.asked(alice.client, {"do": "claim", "role": "planner"})
    host.asked(alice.client, {"do": "afk", "on": True, "role": "planner"})

    host.detach(alice.client)

    assert host.away_for("planner")


# ------------------------------------------------------------------ with no run


def test_a_line_with_no_run_to_say_it_to_is_refused(host: Host) -> None:
    alice = Told(host, "alice")

    assert host.asked(alice.client, {"do": "say", "text": "hello"}) == {
        "ok": False,
        "why": "no flow is running to say it to",
    }


def test_stopping_nothing_says_there_was_nothing_to_stop(host: Host) -> None:
    alice = Told(host, "alice")

    said = host.asked(alice.client, {"do": "stop"})

    assert said == {
        "ok": False,
        "why": "no flow is running, so there is nothing to stop",
    }


def test_a_request_nobody_knows_is_refused_in_words(host: Host) -> None:
    alice = Told(host, "alice")

    assert host.asked(alice.client, {"do": "dance"}) == {
        "ok": False,
        "why": "no such request: 'dance'",
    }
    assert host.asked("c99", {"do": "stop"}) == {
        "ok": False,
        "why": "this frontend is not attached",
    }


def test_a_flow_that_is_not_there_is_refused_before_anything_runs(
    host: Host, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    alice = Told(host, "alice")

    said = host.asked(
        alice.client, {"do": "start", "flow": "./nowhere.py", "task": "x"}
    )

    assert not said["ok"]
    assert "nowhere" in said["why"]
    assert host.status()["state"] == "idle"


def test_closing_lets_every_frontend_go_and_says_why(host: Host) -> None:
    alice, bob = Told(host, "alice"), Told(host, "bob")

    host.close()

    for one in (alice, bob):
        assert one.waits(lambda said: said["type"] == "gone")["why"] == (
            "the host was closed"
        )
    assert host.closed
    with pytest.raises(RuntimeError, match="closed"):
        host.attach("carol", "sdk", lambda _said: None)


def test_a_host_nobody_is_attached_to_and_nothing_running_in_is_idle(
    host: Host,
) -> None:
    assert host.idle
    alice = Told(host, "alice")
    assert not host.idle

    host.detach(alice.client)

    assert host.idle
