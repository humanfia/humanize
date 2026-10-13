"""Another machine's daemon, reached over ssh, telling this page of its epics.

A chat started on the other machine through this interface waits on its next turn there; the
notice that says so comes back as a notification here, said to be that daemon's, and so does
its stopping.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest

from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_ssh import faked, written
from tests.integration.doubles_web import PATIENCE, Browser, served

if TYPE_CHECKING:
    from pathlib import Path

    from tests.integration.doubles_ssh import Host


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Host:
    """The stand-in `claude` on PATH, and the other machine, written down as `box`."""
    (tmp_path / "here").mkdir()
    install(tmp_path / "here", monkeypatch)
    found = faked(tmp_path, monkeypatch)
    written({"name": "box", "host": "box.example", "user": "me"})
    return found


def _told(browser: Browser, kind: str) -> dict[str, Any]:
    """The first notification of that kind, once there is one."""
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline:
        items = browser.get("/api/notifications").json()["items"]
        found = [one for one in items if one["kind"] == kind]
        if found:
            return found[0]
        time.sleep(0.2)
    raise AssertionError(f"no {kind} notification in {PATIENCE}s")


def test_a_chat_on_another_machine_is_told_here(host: Host) -> None:
    there = host.home / "project"
    there.mkdir()
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        listed = browser.get("/api/daemons").json()["daemons"]
        assert [one["name"] for one in listed] == ["local", "box"]
        # Reached, which starts its interface and what follows its notices.
        assert browser.get("/d/box/api/held").status == 200
        started = browser.post(
            f"/d/box/api/held/start?workspace={there}",
            {"flow": "chat", "task": "hello there", "agents": {"assistant": AGENT}},
        )
        assert started.status == 200, started.body

        listening = _told(browser, "listening")
        assert listening["daemon"] == "box"
        assert listening["workspace"] == str(there)
        assert listening["task"] == "hello there"
        assert not listening["read"]

        read = browser.post("/api/notifications/read", {"all": True}).json()
        assert read["unread"] == 0
        assert (
            browser.post("/d/box/api/held/stop", {"workspace": str(there)}).status
            == 200
        )
        assert _told(browser, "stopped")["daemon"] == "box"
