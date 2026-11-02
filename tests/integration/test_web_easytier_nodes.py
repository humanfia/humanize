"""`hmz web`'s shared EasyTier nodes: read from a stand-in status page, or said to be unreadable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.integration.doubles_easytier import kuma
from tests.integration.doubles_web import Browser, served

if TYPE_CHECKING:
    import pytest

_PAGE = {
    "publicGroupList": [
        {
            "name": "Shared",
            "monitorList": [
                {"id": 7, "name": "Here/Alice/2.6.4/TCP/node.example:11010"},
                {"id": 8, "name": "There/Bob/2.6.0/udp://1.2.3.4:11010"},
                {"id": 9, "name": "a monitor of no node"},
            ],
        }
    ]
}
_BEATS = {
    "heartbeatList": {"7": [{"status": 1}], "8": [{"status": 0}]},
    "uptimeList": {"7_24": 0.995, "8_24": 0.2},
}


def test_the_community_nodes_are_listed_until_they_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        with kuma(_PAGE, _BEATS, monkeypatch):
            answered = browser.get("/api/daemons/easytier/nodes")
            assert answered.status == 200, answered.body
            assert answered.json() == {
                "nodes": [
                    {
                        "url": "tcp://node.example:11010",
                        "name": "Here/Alice/2.6.4/TCP/node.example:11010",
                        "version": "2.6.4",
                        "up": True,
                        "uptime": 0.995,
                    },
                    {
                        "url": "udp://1.2.3.4:11010",
                        "name": "There/Bob/2.6.0/udp://1.2.3.4:11010",
                        "version": "2.6.0",
                        "up": False,
                        "uptime": 0.2,
                    },
                ]
            }

        gone = browser.get("/api/daemons/easytier/nodes")
        assert gone.status == 503
        assert gone.json()["error"].startswith(
            "The community nodes could not be read: cannot read http://127.0.0.1:"
        )
