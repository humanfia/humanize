"""`hmz.trust.pins`: the daemon ids `settings.toml` keeps under `daemons`."""

from __future__ import annotations

from typing import Any

import pytest

from hmz.trust import pins

A, B = "a" * 52, "b" * 52


@pytest.fixture
def daemons(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """What `daemons` holds, in place of the settings file."""
    from hmz.coganchor import settings

    held: list[Any] = []
    monkeypatch.setattr(settings, "read", lambda: {"daemons": held})
    return held


def test_the_id_of_a_daemon_is_read(daemons: list[Any]) -> None:
    daemons += [
        {"name": "box", "id": A, "routes": ["tcp://box:1"]},
        {"name": "lab", "id": "", "routes": ["stdio:ssh://lab"]},
    ]
    assert pins.pinned("box") == A
    assert pins.pinned("lab") == ""
    assert pins.pinned("nobody") is None


def test_an_earlier_releases_entry_pins_nothing_yet(daemons: list[Any]) -> None:
    daemons.append({"name": "old", "via": "ssh", "host": "old"})
    assert pins.pinned("old") == ""


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "box", "id": A, "routes": ["tcp://box:1"], "extra": 1},
        {"name": "box", "id": "nope", "routes": ["tcp://box:1"]},
        {"name": "box", "id": A, "routes": []},
        {"name": "box", "id": A, "routes": "tcp://box:1"},
        {"name": "Local", "id": A, "routes": ["tcp://box:1"]},
        "box",
    ],
)
def test_an_entry_that_cannot_be_read_pins_nothing(
    daemons: list[Any], entry: object
) -> None:
    daemons.append(entry)
    assert pins.pinned("box") is None
    assert pins.pinned("Local") is None


def test_the_first_entry_of_a_name_is_the_one(daemons: list[Any]) -> None:
    daemons += [
        {"name": "box", "id": A, "routes": ["tcp://box:1"]},
        {"name": "box", "id": B, "routes": ["tcp://box:2"]},
    ]
    assert pins.pinned("box") == A


def test_no_daemons_pins_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from hmz.coganchor import settings

    monkeypatch.setattr(settings, "read", dict)
    assert pins.pinned("box") is None


def test_a_key_matches_its_pin_alone() -> None:
    assert pins.matches(A, A)
    assert not pins.matches(A, B)
    assert not pins.matches(A, "")
    assert not pins.matches("", "")
