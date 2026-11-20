"""`hmz.daemon.hosts`: the hosts a daemon holds, and the epic subscriptions attached to them."""

from __future__ import annotations

import threading
from typing import Any
from unittest import mock

import pytest

from hmz.daemon.hosts import Hosted, Hosts, Subscription
from hmz.rpc import Closed, RpcError


class _Session:
    """A session as a subscription sees one: what it was told."""

    def __init__(self, reach: Any = None) -> None:
        self.name, self.kind = "ana", "tui"
        self.reach = reach
        self.lock = threading.Lock()
        self.subs: dict[str, Any] = {}
        self.told: list[dict[str, Any]] = []

    def tell(self, method: str, params: dict[str, Any]) -> None:
        assert method == "epic.event"
        self.told.append(params)


def _subscribed(hosted: Hosted | None = None) -> tuple[Subscription, _Session]:
    session = _Session()
    sub = Subscription(session, "s1", hosted or mock.Mock(), figures=False)  # pyright: ignore[reportArgumentType]
    session.subs["s1"] = sub
    return sub, session


def test_what_the_host_tells_waits_until_the_sub_is_answered() -> None:
    sub, session = _subscribed()
    sub.told({"type": "welcome"})
    assert session.told == []

    sub.opened()
    sub.told({"type": "live"})

    assert session.told == [
        {"sub": "s1", "message": {"type": "welcome"}},
        {"sub": "s1", "message": {"type": "live"}},
    ]


def test_gone_ends_the_subscription_and_nothing_follows_it() -> None:
    sub, session = _subscribed()
    sub.opened()
    sub.told({"type": "gone", "why": "let go"})
    sub.told({"type": "printed"})

    assert sub.gone
    assert session.subs == {}
    assert [one["message"]["type"] for one in session.told] == ["gone"]


def test_ending_a_subscription_says_why_and_lets_its_frontend_go() -> None:
    hosted = mock.Mock()
    sub, session = _subscribed(hosted)
    sub.client = "c4"
    sub.opened()

    sub.end("too far behind; attach again")
    sub.end("again")

    assert session.told == [
        {
            "sub": "s1",
            "message": {"type": "gone", "why": "too far behind; attach again"},
        }
    ]
    hosted.detach.assert_called_once_with("c4")


def test_a_subscription_whose_session_went_is_let_go_quietly() -> None:
    hosted = mock.Mock()
    sub, session = _subscribed(hosted)
    sub.client = "c4"

    sub.dropped()

    assert session.told == []
    hosted.detach.assert_called_once_with("c4")


def _hosted(peer: Any) -> Hosted:
    hosted = Hosted("/w", "")
    hosted.peer = peer
    hosted.said = {"pid": 3, "workspace": "/w", "started": "t", "slot": ""}
    hosted.said |= {"kind": "host", "protocol": "3.0.0"}
    return hosted


def test_a_hosts_message_goes_to_the_subscription_it_names() -> None:
    hosted = _hosted(mock.Mock(call=mock.Mock(return_value={"client": "c1"})))
    sub, session = _subscribed(hosted)

    assert hosted.attach(sub, replay=True, since=None) == "c1"
    sub.opened()
    hosted.told(
        mock.Mock(method="told", params={"tag": sub.tag, "message": {"type": "x"}})
    )
    hosted.told(
        mock.Mock(method="told", params={"tag": "else", "message": {"type": "y"}})
    )

    assert session.told == [{"sub": "s1", "message": {"type": "x"}}]


@pytest.mark.parametrize(
    ("failure", "said"),
    [
        (Closed("gone"), "this host has closed"),
        (
            RpcError(-32603, "Something went wrong here: this host has closed"),
            "this host has closed",
        ),
    ],
)
def test_a_host_that_cannot_attach_is_refused_409(
    failure: Exception, said: str
) -> None:
    hosted = _hosted(mock.Mock(call=mock.Mock(side_effect=failure)))
    sub, _ = _subscribed(hosted)

    with pytest.raises(RpcError) as refused:
        hosted.attach(sub, replay=True, since=None)

    assert (refused.value.code, refused.value.message) == (409, said)


def test_an_env_call_is_asked_down_the_link_as_it_was_said() -> None:
    peer = mock.Mock(
        call=mock.Mock(return_value={"ok": False, "why": "no", "code": 404})
    )

    assert _hosted(peer).env({"do": "hosts.env.read"}) == {
        "ok": False,
        "why": "no",
        "code": 404,
    }
    peer.call.assert_called_once_with(
        "env", {"said": {"do": "hosts.env.read"}}, timeout=None
    )


def test_a_host_that_will_not_say_is_answered_for() -> None:
    hosted = _hosted(mock.Mock(call=mock.Mock(side_effect=TimeoutError)))

    assert hosted.status() == {
        "pid": 3,
        "workspace": "/w",
        "started": "t",
        "kind": "host",
        "protocol": "3.0.0",
        "slot": "",
        "attached": 0,
        "flows": [],
        "calls": [],
    }


def test_a_host_going_ends_every_subscription_on_it() -> None:
    hosted = _hosted(mock.Mock(call=mock.Mock(return_value={"client": "c1"})))
    sub, session = _subscribed(hosted)
    hosted.attach(sub, replay=True, since=None)
    sub.opened()

    hosted.went()

    assert session.told == [
        {"sub": "s1", "message": {"type": "gone", "why": "the host went away"}}
    ]


def test_no_host_is_held_before_one_is_opened() -> None:
    hosts = Hosts(mock.Mock())

    assert len(hosts) == 0
    assert hosts.listed() == []
    assert hosts.get("/w", "") is None


def test_an_ai_slot_of_no_conversation_is_refused_404() -> None:
    with pytest.raises(RpcError) as refused:
        Hosts(mock.Mock()).opened("/w", "ai:ab")
    assert (refused.value.code, refused.value.message) == (
        404,
        "There is no Ai-chan conversation ai:ab.",
    )


def test_an_epic_scoped_ai_chan_is_let_go_once_another_epic_starts() -> None:
    from hmz.daemon.reach import Reach

    session = _Session(Reach(1, "epic", "/w", "mine", "read-only"))
    sub = Subscription(session, "s1", mock.Mock(), figures=False)  # pyright: ignore[reportArgumentType]
    session.subs["s1"] = sub
    # Replayed before the sub is answered: the host's history is no epic starting.
    sub.told({"type": "run", "epic": "older"})
    sub.opened()
    sub.told({"type": "run", "epic": "mine"})
    assert not sub.gone
    sub.told({"type": "run", "epic": "theirs"})
    assert sub.gone
    assert session.told[-1]["message"] == {
        "type": "gone",
        "why": "out of Ai-chan's scope",
    }
