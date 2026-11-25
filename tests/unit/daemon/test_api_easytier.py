"""`hmz.daemon.api.easytier`: EasyTier entries, written with a secret that never comes out."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.daemon.api import easytier
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from collections.abc import Callable

_SECRET = "a secret of sixteen bytes or more"


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The settings file, as a dict that reads and changes stand in for."""
    from hmz.coganchor import settings

    file: dict[str, Any] = {}

    def changes(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        change(file)
        return file

    monkeypatch.setattr(settings, "read", lambda: json.loads(json.dumps(file)))
    monkeypatch.setattr(settings, "changes", changes)
    return file


def _refused(code: int, call: Any, *args: Any) -> str:
    with pytest.raises(RpcError) as refused:
        call(*args)
    assert refused.value.code == code, refused.value.message
    return refused.value.message


def test_an_entry_is_listed_as_having_a_secret_and_keeps_it_when_sent_none(
    held: dict[str, Any],
) -> None:
    said = easytier.write("lab", _SECRET, ["tcp://node:11010"])

    assert said == {
        "networks": [{"name": "lab", "nodes": ["tcp://node:11010"], "secret": True}]
    }
    easytier.write("lab", None, ["udp://other:11010"])
    assert held["easytier"]["lab"] == {
        "secret": _SECRET,
        "nodes": ["udp://other:11010"],
    }
    assert _SECRET not in json.dumps(easytier.listed())


def test_what_writing_an_entry_is_refused(held: dict[str, Any]) -> None:
    assert _refused(400, easytier.write, "lab", "short", ["tcp://n:1"]) == (
        "A secret must be at least 16 bytes."
    )
    assert _refused(400, easytier.write, "lab", None, ["tcp://n:1"]) == (
        "A secret must be at least 16 bytes."
    )
    assert _refused(400, easytier.write, "lab", _SECRET, []) == (
        "An EasyTier daemon needs at least one node."
    )
    _refused(400, easytier.write, "lab", _SECRET, ["http://n:1"])
    _refused(400, easytier.write, "-lab", _SECRET, ["tcp://n:1"])
    _refused(400, easytier.write, "Local", _SECRET, ["tcp://n:1"])
    assert held == {}


def test_an_entry_listened_on_is_not_removed(held: dict[str, Any]) -> None:
    easytier.write("lab", _SECRET, ["tcp://n:1"])
    held["listen"] = ["easytier:lab"]

    assert _refused(409, easytier.remove, "lab") == "lab is listened on."
    held["listen"] = []
    assert easytier.remove("lab") == {"networks": []}
    assert _refused(404, easytier.remove, "lab") == "There is no EasyTier entry lab."


def test_the_shared_nodes_are_answered(monkeypatch: pytest.MonkeyPatch) -> None:
    from hmz.coganchor import easytier as tier

    node = tier.Node("tcp://n.lab:11010", "lab", "", None, None)
    monkeypatch.setattr(tier, "shared", lambda timeout=10: [node])

    assert easytier.nodes() == {
        "nodes": [
            {
                "url": "tcp://n.lab:11010",
                "name": "lab",
                "version": "",
                "up": None,
                "uptime": None,
            }
        ]
    }
