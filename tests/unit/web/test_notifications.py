"""`hmz.web.notifications`: every daemon's notices, kept, filtered, read and streamed."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from hmz.web.notifications import KINDS, ROUTES, Notifications, daemons, preferences
from hmz.web.routing import Asked, Refusal

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


class _Notices:
    """A stand-in for this machine's notices: what hears them, told each as it is said."""

    def __init__(self) -> None:
        self.hearing: list[Callable[[Any], object]] = []

    def heard(self, callback: Callable[[Any], object]) -> None:
        self.hearing.append(callback)

    def says(self, said: Any) -> None:
        for one in self.hearing:
            one(said)


def _notice(kind: str = "done", **more: Any) -> dict[str, Any]:
    return {"id": "7", "kind": kind, "workspace": "/w", "epic": "e", "text": ""} | more


@pytest.fixture
def notices() -> _Notices:
    return _Notices()


@pytest.fixture
def wanted() -> dict[str, Any]:
    return preferences({})


@pytest.fixture
def held(notices: _Notices, wanted: dict[str, Any]) -> Generator[Notifications]:
    made = Notifications(
        SimpleNamespace(notices=notices), wanted=lambda: wanted, named=list
    )
    yield made
    made.close()


def test_every_kind_is_told_and_shown_where_nothing_is_set() -> None:
    assert preferences({}) == {
        "kinds": dict.fromkeys(KINDS, True),
        "system": True,
    }


def test_a_kind_turned_off_is_off_and_anything_else_is_on() -> None:
    said = {"notifications": {"kinds": {"done": False, "asked": "no"}, "system": False}}

    assert preferences(said) == {
        "kinds": dict.fromkeys(KINDS, True) | {"done": False},
        "system": False,
    }


def test_settings_not_written_as_notifications_are_every_one_wanted() -> None:
    assert preferences({"notifications": ["done"]}) == preferences({})


def test_ssh_daemons_are_named_as_written_and_local_is_never_one() -> None:
    held = {
        "daemons": [
            {"name": "gpu"},
            {"name": "local"},
            "box",
            {"host": "x"},
            {"name": "b"},
        ]
    }

    assert daemons(held) == ["gpu", "b"]
    assert daemons({}) == []


def test_this_machines_notices_are_kept_as_local_newest_first(
    held: Notifications, notices: _Notices
) -> None:
    notices.says(_notice("done", epic="a"))
    notices.says([_notice("asked", epic="b")])

    listed = held.listed()

    assert [(one["daemon"], one["epic"], one["kind"]) for one in listed["items"]] == [
        ("local", "b", "asked"),
        ("local", "a", "done"),
    ]
    assert [one["id"] for one in listed["items"]] == ["2", "1"]
    assert listed["unread"] == 2
    assert not any(one["read"] for one in listed["items"])


def test_a_kind_not_wanted_is_never_kept(
    held: Notifications, wanted: dict[str, Any]
) -> None:
    wanted["kinds"]["listening"] = False

    assert held.told("gpu", _notice("listening")) is None
    assert held.told("gpu", _notice("failed")) is not None
    assert [one["kind"] for one in held.listed()["items"]] == ["failed"]


def test_only_the_last_few_hundred_are_kept(held: Notifications) -> None:
    for _ in range(250):
        held.told("local", _notice())

    items = held.listed()["items"]

    assert len(items) == 200
    assert items[0]["id"] == "250"


def test_notifications_are_read_by_id_or_all_at_once(held: Notifications) -> None:
    first = held.told("local", _notice())
    held.told("gpu", _notice())
    assert first is not None

    assert held.read([first["id"]])["unread"] == 1
    assert held.read()["unread"] == 0


def test_clearing_forgets_every_one_and_the_next_counts_on(
    held: Notifications,
) -> None:
    held.told("local", _notice())

    assert held.clear() == {"items": [], "unread": 0}
    told = held.told("local", _notice())
    assert told is not None
    assert told["id"] == "2"


def test_the_stream_takes_up_after_the_last_heard_then_tells_each_as_it_comes(
    held: Notifications,
) -> None:
    held.told("local", _notice(epic="a"))
    held.told("gpu", _notice(epic="b"))
    going = threading.Event()
    events = held.stream().events("1", going)

    assert next(events) == ("2", "notification", held.listed()["items"][0])
    threading.Timer(0.05, held.told, args=("gpu", _notice(epic="c"))).start()
    said = next(events)
    assert said is not None
    ident, name, data = said

    assert (ident, name, data["epic"], data["daemon"]) == (
        "3",
        "notification",
        "c",
        "gpu",
    )


def test_a_stream_heard_of_an_earlier_interface_starts_over(
    held: Notifications,
) -> None:
    held.told("local", _notice())

    events = held.stream().events("90", threading.Event())

    said = next(events)
    assert said is not None
    assert said[0] == "1"


def test_a_page_marks_read_by_ids_or_all_and_nothing_else(
    held: Notifications,
) -> None:
    (read,) = [one for one in ROUTES if one.path == "/api/notifications/read"]
    site = SimpleNamespace(notifications=held)
    held.told("local", _notice())
    held.told("local", _notice())

    assert read.answers(Asked(site, body={"ids": [1]}))["unread"] == 1
    assert read.answers(Asked(site, body={"all": True}))["unread"] == 0
    with pytest.raises(Refusal):
        read.answers(Asked(site, body={"ids": "1"}))
    with pytest.raises(Refusal, match="not kept"):
        read.answers(Asked(SimpleNamespace(), body={"all": True}))
