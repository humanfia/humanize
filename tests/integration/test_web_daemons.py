"""`hmz web`'s daemons: written down, brought in from the ssh config, and removed."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from hmz import home
from tests.integration.doubles_web import Browser, served

pytestmark = pytest.mark.skipif(shutil.which("ssh") is None, reason="needs ssh -G")


@pytest.fixture
def ssh_config() -> Path:
    """An ssh config, in the test's own home, naming two hosts."""
    at = Path.home() / ".ssh" / "config"
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(
        "Host gpu\n  HostName gpu.example\n  User me\n  Port 2222\n"
        "Host box\n  HostName box.example\n"
    )
    return at


def _settings() -> dict[str, Any]:
    return yaml.safe_load((home() / "settings.yaml").read_text())


def test_a_daemon_is_added_edited_and_removed(ssh_config: Path) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        assert [
            one["label"] for one in browser.get("/api/daemons").json()["daemons"]
        ] == ["Local"]
        added = browser.post(
            "/api/daemons",
            {
                "name": "lab",
                "fields": {"host": "lab.example", "options": [["Compression", "yes"]]},
            },
        )
        assert added.status == 200, added.body
        assert [(one["name"], one["state"]) for one in added.json()["daemons"]] == [
            ("local", "up"),
            ("lab", "idle"),
        ]
        assert (
            browser.post(
                "/api/daemons", {"name": "lab", "fields": {"host": "b"}}
            ).status
            == 409
        )
        assert (
            browser.post(
                "/api/daemons",
                {"name": "lab", "fields": {"host": "b"}, "replace": True},
            ).status
            == 200
        )
        refused = browser.post(
            "/api/daemons", {"name": "local", "fields": {"host": "b"}}
        )
        assert refused.status == 400
        assert refused.json()["error"]
        assert browser.post("/api/daemons", {"name": "x", "nope": 1}).status == 400

        assert _settings()["daemons"] == [
            {
                "name": "lab",
                "host": "b",
                "user": "",
                "port": 0,
                "identity_file": "",
                "proxy_jump": "",
                "alias": "",
                "config": "",
                "options": [],
            }
        ]

        removed = browser.post("/api/daemons/remove", {"name": "lab"})
        assert [one["name"] for one in removed.json()["daemons"]] == ["local"]
        assert browser.post("/api/daemons/remove", {"name": "local"}).status == 400


def test_hosts_of_the_ssh_config_are_offered_and_imported(ssh_config: Path) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        hosts = browser.get("/api/daemons/hosts").json()["hosts"]
        # Which hosts are named is read off the config in this home; what each comes to
        # is `ssh -G`'s, which reads the config of the account's own home instead.
        assert [(one["alias"], one["name"]) for one in hosts] == [
            ("gpu", "gpu"),
            ("box", "box"),
        ]
        imported = browser.post("/api/daemons/import", {"aliases": ["gpu"]})
        assert imported.json()["added"] == ["gpu"]
        again = browser.post("/api/daemons/import", {"aliases": ["gpu", "box"]})
        assert again.json()["added"] == ["box"]
        assert [one["name"] for one in again.json()["daemons"]] == [
            "local",
            "gpu",
            "box",
        ]
        assert browser.get("/api/daemons/hosts").json()["hosts"] == []
        assert (
            browser.post("/api/daemons/import", {"aliases": ["elsewhere"]}).status
            == 404
        )
        assert [one["alias"] for one in _settings()["daemons"]] == ["gpu", "box"]


def test_a_stranger_is_told_nothing_of_the_daemons(ssh_config: Path) -> None:
    with served() as site:
        assert Browser(site).get("/api/daemons").status == 401
