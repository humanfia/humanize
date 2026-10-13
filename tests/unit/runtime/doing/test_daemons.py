"""`hmz.runtime.doing.daemons`: what a host says it has, and what reaching its interface carries."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.doing.daemons import (
    CARRIED,
    LOCAL,
    UP,
    Daemons,
    Remotes,
    carried,
    headers,
    said,
)

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
def config(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ssh config naming `gpu` and `box.one`."""
    from hmz.coganchor.machines import sshconfig

    def aliases(*_: object) -> list[str]:
        return ["gpu", "box.one", "local"]

    monkeypatch.setattr(sshconfig, "aliases", aliases)


def test_a_daemon_is_written_replaced_only_when_asked_and_removed(
    held: dict[str, Any],
) -> None:
    daemons = Daemons()

    written = daemons.write("gpu", {"host": "a", "options": [["Compression", "yes"]]})
    with pytest.raises(FileExistsError):
        daemons.write("gpu", {"host": "b"})
    daemons.write("gpu", {"host": "b"}, replace=True)

    assert written["options"] == [["Compression", "yes"]]
    assert daemons.find("gpu") == daemons.all()[0]
    assert daemons.all()[0]["host"] == "b"
    assert held["other"] == {"kept": True}
    with pytest.raises(ValueError, match="Local is always there"):
        daemons.remove(LOCAL)
    with pytest.raises(LookupError):
        daemons.remove("nope")
    daemons.remove("gpu")
    assert daemons.all() == []


@pytest.mark.parametrize(
    ("name", "fields"),
    [("Local", {"host": "a"}), ("..", {"host": "a"}), ("gpu", {"workdir": "/w"})],
)
def test_what_cannot_be_a_daemon_is_refused(
    held: dict[str, Any], name: str, fields: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="daemon"):
        Daemons().write(name, fields)

    assert "daemons" not in held


def test_hosts_of_the_ssh_config_are_offered_and_brought_in_once(
    held: dict[str, Any], config: None
) -> None:
    daemons = Daemons()

    assert list(daemons.offered()) == ["gpu", "box.one"]
    assert daemons.imported(["gpu", "gpu"]) == ["gpu"]
    assert list(daemons.offered()) == ["box.one"]
    with pytest.raises(LookupError):
        daemons.imported(["elsewhere"])
    with pytest.raises(ValueError, match="Say aliases"):
        daemons.imported([])


def test_local_stands_up_and_nothing_else_is_reached_unasked() -> None:
    remotes = Remotes(version="1.2.3")
    try:
        assert remotes.state(LOCAL)["state"] == UP
        assert remotes.state("gpu") == {"state": "idle", "detail": "", "version": ""}
    finally:
        remotes.close()


def test_a_probe_is_read_by_what_each_line_says() -> None:
    assert said(
        [
            "Warning: Permanently added 'box' to the list of known hosts.",
            "hmz: 0.5.0rc1",
            "daemon: running",
            "something: else",
        ]
    ) == {"hmz": "0.5.0rc1", "daemon": "running"}
    assert said(["hmz: ", "daemon: none"]) == {"hmz": "", "daemon": "none"}
    assert said([]) == {}


def test_a_request_there_is_its_own_page_s() -> None:
    assert headers(8123, "k3y") == {
        "Host": "127.0.0.1:8123",
        "Origin": "http://127.0.0.1:8123",
        "Sec-Fetch-Site": "same-origin",
        "Cookie": "hmz-8123=k3y",
    }


def _plain(url: str) -> str:
    """A URL with nothing signed into it, as the flowverses strike one."""
    return url.replace("me:secret@", "***@")


def test_a_batch_carries_the_pages_asked_for_as_each_page_saves_them() -> None:
    target = SimpleNamespace(
        name="lab",
        url="https://me:secret@example.com/epics.git",
        branch="main",
        policies=("manual",),
        every=30,
    )
    runtime = SimpleNamespace(
        held=lambda: {"backend": "ssh", "name": "gpu", "made": "typed", "host": "g"}
    )
    step = SimpleNamespace(spec="claude", to=("codex",), tries=2, policy="p", timeout=5)
    hmz = SimpleNamespace(
        settings=SimpleNamespace(btw="", details=True, enable_sentry=None),
        fallbacks=SimpleNamespace(all=lambda: [step]),
        runtimes=SimpleNamespace(all=lambda: [runtime]),
        backups=SimpleNamespace(targets=lambda: [target], defaults=lambda: ["lab"]),
        verses=SimpleNamespace(plain=_plain),
    )

    sent = carried(hmz, CARRIED)

    assert sent == [
        ("/api/settings", {"btw": "", "details": True}),
        (
            "/api/fallbacks",
            {
                "spec": "claude",
                "to": ["codex"],
                "tries": 2,
                "policy": "p",
                "timeout": 5,
            },
        ),
        (
            "/api/runtimes",
            {"backend": "ssh", "name": "gpu", "fields": {"host": "g"}, "replace": True},
        ),
        (
            "/api/settings",
            {
                "backup": {
                    "targets": [
                        {
                            "name": "lab",
                            "url": "https://***@example.com/epics.git",
                            "branch": "main",
                            "policies": ["manual"],
                            "every": 30,
                        }
                    ],
                    "defaults": ["lab"],
                }
            },
        ),
    ]
    assert carried(hmz, ["general"]) == sent[:1]
