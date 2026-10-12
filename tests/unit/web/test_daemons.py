"""`hmz.web.daemons`: the daemons a page may switch between, written down and brought in."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from hmz.web.daemons import LOCAL, ROUTES, found, listed, saved
from hmz.web.routing import Asked, Refusal

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The settings file, as a dict that `read` and `changes` read and write."""
    from hmz.coganchor import settings

    file: dict[str, Any] = {"other": {"kept": True}}

    def changes(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        working = copy.deepcopy(file)
        change(working)
        file.clear()
        file.update(working)
        return file

    monkeypatch.setattr(settings, "read", lambda: copy.deepcopy(file))
    monkeypatch.setattr(settings, "changes", changes)
    return file


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The hosts the ssh config names, each resolving to `<alias>.example`."""
    from hmz.coganchor.machines import sshconfig

    named = ["gpu", "box.one", "local", "a+b", "a-b", "__", "x$y"]

    def resolve(alias: str, *_: object, **__: object) -> sshconfig.SSHHost:
        return sshconfig.SSHHost(
            alias=alias, host=f"{alias}.example", user="me", port=22
        )

    def aliases(*_: object) -> list[str]:
        return list(named)

    monkeypatch.setattr(sshconfig, "aliases", aliases)
    monkeypatch.setattr(sshconfig, "resolve", resolve)
    return named


def _asks(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    route = next(one for one in ROUTES if one.match(method, path) is not None)
    return route.answers(Asked(site=SimpleNamespace(), body=body or {}))


def test_local_is_first_and_up_with_nothing_written_down(held: dict[str, Any]) -> None:
    daemons = listed(SimpleNamespace())["daemons"]

    assert [(one["name"], one["label"], one["state"]) for one in daemons] == [
        (LOCAL, "Local", "up")
    ]


def test_a_daemon_is_written_with_its_options_as_pairs(held: dict[str, Any]) -> None:
    said = _asks(
        "POST",
        "/api/daemons",
        {
            "name": "gpu",
            "fields": {
                "host": "gpu.example",
                "port": 2222,
                "options": [["Compression", "yes"]],
            },
        },
    )

    assert [one["name"] for one in said["daemons"]] == [LOCAL, "gpu"]
    assert said["daemons"][1]["state"] == "idle"
    assert held["other"] == {"kept": True}
    assert held["daemons"] == [
        {
            "name": "gpu",
            "host": "gpu.example",
            "user": "",
            "port": 2222,
            "identity_file": "",
            "proxy_jump": "",
            "alias": "",
            "config": "",
            "options": [["Compression", "yes"]],
        }
    ]
    assert found("gpu") == held["daemons"][0]
    assert found("nope") is None


def test_one_there_already_is_replaced_only_when_asked(held: dict[str, Any]) -> None:
    _asks("POST", "/api/daemons", {"name": "gpu", "fields": {"host": "a"}})

    with pytest.raises(Refusal) as refused:
        _asks("POST", "/api/daemons", {"name": "gpu", "fields": {"host": "b"}})
    assert refused.value.status == 409
    _asks(
        "POST",
        "/api/daemons",
        {"name": "gpu", "fields": {"host": "b"}, "replace": True},
    )

    assert [one["host"] for one in saved()] == ["b"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "local", "fields": {"host": "a"}},
        {"name": "Local", "fields": {"host": "a"}},
        {"name": "a b", "fields": {"host": "a"}},
        {"name": "..", "fields": {"host": "a"}},
        {"name": "gpu", "fields": {}},
        {"name": "gpu", "fields": {"host": "a", "workdir": "/w"}},
        {"name": "gpu", "fields": {"host": "a"}, "secret": "x"},
        {"name": "gpu", "fields": {"host": "a", "port": "22"}},
        {"name": "gpu", "fields": {"host": "a", "options": [["Port", "22"]]}},
    ],
)
def test_what_cannot_be_a_daemon_is_refused(
    held: dict[str, Any], body: dict[str, Any]
) -> None:
    with pytest.raises(Refusal):
        _asks("POST", "/api/daemons", body)

    assert "daemons" not in held


def test_a_daemon_is_removed_and_local_never_is(held: dict[str, Any]) -> None:
    _asks("POST", "/api/daemons", {"name": "gpu", "fields": {"host": "a"}})

    with pytest.raises(Refusal):
        _asks("POST", "/api/daemons/remove", {"name": "local"})
    with pytest.raises(Refusal) as missing:
        _asks("POST", "/api/daemons/remove", {"name": "nope"})
    assert missing.value.status == 404
    said = _asks("POST", "/api/daemons/remove", {"name": "gpu"})

    assert [one["name"] for one in said["daemons"]] == [LOCAL]
    assert held["daemons"] == []


def test_one_written_wrong_by_hand_is_left_out(held: dict[str, Any]) -> None:
    held["daemons"] = [
        "nonsense",
        {"name": "local", "host": "a"},
        {"name": "ok", "host": "a"},
        {"name": "ok", "host": "b"},
        {"host": "nameless"},
    ]

    assert [(one["name"], one["host"]) for one in saved()] == [("ok", "a")]


def test_each_stands_as_the_remote_reach_says(held: dict[str, Any]) -> None:
    held["daemons"] = [{"name": "gpu", "host": "a"}]

    def state(name: str) -> dict[str, str]:
        return {"state": "failed", "detail": f"{name} down", "version": ""}

    remotes = SimpleNamespace(state=state)

    daemons = listed(SimpleNamespace(remotes=remotes))["daemons"]

    assert daemons[0]["state"] == "up"
    assert (daemons[1]["state"], daemons[1]["detail"]) == ("failed", "gpu down")


def test_hosts_not_yet_added_are_offered(
    held: dict[str, Any], config: list[str]
) -> None:
    held["daemons"] = [{"name": "g", "alias": "gpu"}]

    hosts = _asks("GET", "/api/daemons/hosts")["hosts"]

    # Of two called the same, the first; never one no daemon could be.
    assert [(one["alias"], one["name"], one["host"]) for one in hosts] == [
        ("box.one", "box.one", "box.one.example"),
        ("a+b", "a-b", "a+b.example"),
    ]


def test_hosts_are_imported_by_alias_skipping_any_already_there(
    held: dict[str, Any], config: list[str]
) -> None:
    held["daemons"] = [{"name": "gpu", "host": "a"}]

    said = _asks("POST", "/api/daemons/import", {"aliases": ["gpu", "box.one"]})

    assert said["added"] == ["box.one"]
    assert [(one["name"], one["alias"], one["host"]) for one in saved()] == [
        ("gpu", "", "a"),
        ("box.one", "box.one", ""),
    ]


@pytest.mark.parametrize(
    "body", [{"aliases": []}, {"aliases": ["elsewhere"]}, {"aliases": ["local"]}]
)
def test_an_import_of_nothing_or_of_a_host_it_cannot_be_is_refused(
    held: dict[str, Any], config: list[str], body: dict[str, Any]
) -> None:
    with pytest.raises(Refusal):
        _asks("POST", "/api/daemons/import", body)

    assert "daemons" not in held
