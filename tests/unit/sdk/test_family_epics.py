"""`Client.epics` and `Client.hosts`: an epic's and a host's methods as typed calls."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from hmz.sdk import Refused
from hmz.sdk.families.epics import Attached, Epics, Face, Started
from hmz.sdk.families.hosts import Host, Hosts, Running

_ATTACHED = {"sub": "s1", "client": "c1", "workspace": "/w", "slot": "exec:ab"}


@pytest.fixture
def client() -> mock.Mock:
    made = mock.Mock(spec=["call", "heard", "wait"])
    made.wait.return_value = False
    return made


def _attached(client: mock.Mock) -> Attached:
    client.call.return_value = _ATTACHED
    attached = Epics(client).attach("/w", slot="exec:", replay=False)
    client.call.reset_mock()
    client.call.return_value = {}
    return attached


def _tells(client: mock.Mock, **message: Any) -> None:
    (listener,), _ = client.heard.call_args
    listener("epic.event", {"sub": "s1", "message": message})


def test_attaching_opens_a_subscription_and_says_where_it_is(client: mock.Mock) -> None:
    client.call.return_value = _ATTACHED

    attached = Epics(client).attach("/w", slot="exec:", replay=False)

    client.call.assert_called_once_with(
        "epic.attach",
        {"workspace": "/w", "slot": "exec:", "replay": False},
        idem=None,
        seconds=None,
    )
    assert (attached.sub, attached.client) == ("s1", "c1")
    assert (attached.workspace, attached.slot) == ("/w", "exec:ab")
    assert attached.events.sub == "s1"


def test_each_call_is_asked_of_the_subscription(client: mock.Mock) -> None:
    attached = _attached(client)

    attached.say("hello", to="NeiKos", idem="k")
    attached.answer("q1", "yes")
    attached.answer("q2", value={"verdict": "approve"})
    attached.stop()
    attached.afk(on=True)
    attached.afk(on=False, role="reviewer")
    attached.claim("reviewer", take=True)
    attached.release("reviewer")
    attached.board("deadline", "Friday")
    attached.board("deadline", "")
    attached.unaside("s1")
    attached.detach()
    attached.quit()

    assert [(one.args[0], one.args[1]) for one in client.call.call_args_list] == [
        ("epic.say", {"sub": "s1", "text": "hello", "to": "NeiKos"}),
        ("epic.answer", {"sub": "s1", "question": "q1", "text": "yes"}),
        (
            "epic.answer",
            {"sub": "s1", "question": "q2", "value": {"verdict": "approve"}},
        ),
        ("epic.stop", {"sub": "s1"}),
        ("epic.afk", {"sub": "s1", "on": True}),
        ("epic.afk", {"sub": "s1", "on": False, "role": "reviewer"}),
        ("epic.claim", {"sub": "s1", "role": "reviewer", "take": True}),
        ("epic.release", {"sub": "s1", "role": "reviewer"}),
        ("epic.board", {"sub": "s1", "key": "deadline", "value": "Friday"}),
        ("epic.board", {"sub": "s1", "key": "deadline", "value": ""}),
        ("epic.unaside", {"sub": "s1", "side": "s1"}),
        ("epic.detach", {"sub": "s1"}),
        ("epic.quit", {"sub": "s1"}),
    ]
    assert client.call.call_args_list[0].kwargs == {"idem": "k", "seconds": None}


def test_starting_says_only_what_was_given_and_answers_the_epic(
    client: mock.Mock,
) -> None:
    attached = _attached(client)
    client.call.return_value = {"run": 3, "slot": "exec:ab", "workspace": "/w"}

    started = attached.start(
        "goal",
        "win",
        agents={"worker": "claude/m"},
        budget={"cost": 1},
        resume=False,
        backup=[],
    )

    assert started == Started(3, "exec:ab", "/w")
    client.call.assert_called_once_with(
        "epic.start",
        {
            "sub": "s1",
            "flow": "goal",
            "task": "win",
            "agents": {"worker": "claude/m"},
            "budget": {"cost": 1},
            "resume": False,
            "backup": [],
        },
        idem=None,
        seconds=None,
    )


def test_what_a_call_answers_is_read(client: mock.Mock) -> None:
    attached = _attached(client)

    client.call.return_value = {"closed": 2}
    assert attached.force() == 2
    client.call.return_value = {"html": "<p>", "title": "plan"}
    assert attached.face("ab" * 32) == Face("<p>", "plan")
    client.call.assert_called_with(
        "epic.face", {"sub": "s1", "hash": "ab" * 32}, idem=None, seconds=None
    )
    client.call.return_value = {"state": "idle", "pending": []}
    assert attached.status() == {"state": "idle", "pending": []}
    client.call.return_value = {"side": "s1", "forked": False}
    assert attached.aside(key="NeiKos/1", fork=False) == {"side": "s1", "forked": False}
    client.call.assert_called_with(
        "epic.aside",
        {"sub": "s1", "key": "NeiKos/1", "fork": False},
        idem=None,
        seconds=None,
    )


def test_a_refusal_is_raised_as_the_host_said_it(client: mock.Mock) -> None:
    attached = _attached(client)
    client.call.side_effect = Refused("no flow is running to say it to", code=409)

    with pytest.raises(Refused, match="no flow is running") as refused:
        attached.say("hello")
    assert refused.value.code == 409


def test_the_messages_are_told_in_order_until_the_host_lets_go(
    client: mock.Mock,
) -> None:
    attached = _attached(client)
    _tells(client, type="welcome", epoch="e1")
    _tells(client, type="live", seq=0)
    _tells(client, type="gone", why="let go")
    _tells(client, type="never")

    assert [one["type"] for one in attached] == ["welcome", "live", "gone"]
    assert attached.over
    assert attached.next(0) is None


def test_nothing_told_in_time_is_none_and_a_session_ended_is_the_end(
    client: mock.Mock,
) -> None:
    attached = _attached(client)

    assert attached.next(0.01) is None
    assert not attached.over

    client.wait.return_value = True
    assert list(attached) == []
    assert attached.over


def test_leaving_the_block_lets_the_frontend_go_even_where_it_has_gone(
    client: mock.Mock,
) -> None:
    with _attached(client) as attached:
        client.call.side_effect = Refused("gone", code=410)

    client.call.assert_called_once_with(
        "epic.detach", {"sub": "s1"}, idem=None, seconds=5.0
    )
    assert attached.over
    assert attached.events.next(0) is None


def test_the_calls_of_a_subscription_opened_elsewhere_hear_nothing(
    client: mock.Mock,
) -> None:
    client.call.return_value = {}

    Epics(client).of("s9").stop(idem="k", wait=3)

    client.call.assert_called_once_with("epic.stop", {"sub": "s9"}, idem="k", seconds=3)
    client.heard.assert_not_called()


def test_the_hosts_are_listed_and_those_running_said(client: mock.Mock) -> None:
    client.call.return_value = {
        "held": [{"pid": 7, "workspace": "/w", "started": "2026-01-01", "slot": ""}]
    }
    assert Hosts(client).list() == [Host(7, "/w", "2026-01-01", "")]

    client.call.return_value = {
        "running": [
            {
                "state": "running",
                "run": 2,
                "kind": "flow",
                "flow": "goal",
                "epic": "e",
                "chat": "",
                "task": "win",
                "workspace": "/w",
                "slot": "exec:ab",
                "asking": ["2:q1"],
            }
        ]
    }
    assert Hosts(client).running() == [
        Running(
            workspace="/w",
            slot="exec:ab",
            state="running",
            run=2,
            kind="flow",
            flow="goal",
            epic="e",
            chat="",
            task="win",
            asking=("2:q1",),
            turn=None,
        )
    ]


def test_a_host_is_named_by_its_workspace_and_slot(client: mock.Mock) -> None:
    hosts = Hosts(client)
    client.call.return_value = {"pid": 7, "slot": "exec:ab"}
    assert hosts.open("/w", "exec:") == {"pid": 7, "slot": "exec:ab"}
    client.call.return_value = {"state": "idle"}
    assert hosts.status("/w") == {"state": "idle"}
    client.call.return_value = {"let_go": 2}
    assert hosts.detach("/w", "exec:ab") == 2
    client.call.return_value = {}
    hosts.stop("/w", "exec:ab", idem="k")

    assert [one.args for one in client.call.call_args_list] == [
        ("hosts.open", {"workspace": "/w", "slot": "exec:"}),
        ("hosts.status", {"workspace": "/w"}),
        ("hosts.detach", {"workspace": "/w", "slot": "exec:ab"}),
        ("hosts.stop", {"workspace": "/w", "slot": "exec:ab"}),
    ]
    assert client.call.call_args.kwargs == {"idem": "k", "seconds": None}


def test_the_two_families_name_every_method_of_theirs() -> None:
    assert len(Epics.METHODS) == 16
    assert all(method.startswith("epic.") for method in Epics.METHODS)
    assert Hosts.METHODS == (
        "hosts.list",
        "hosts.running",
        "hosts.open",
        "hosts.status",
        "hosts.detach",
        "hosts.stop",
    )
