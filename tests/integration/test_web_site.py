"""`hmz web`: who is let in, from where, what a page may send, and the files it is made of."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.doubles_core import install
from tests.integration.doubles_web import Browser, served

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The stand-in `claude` alone on PATH, and a project to serve the runs of."""
    return install(tmp_path, monkeypatch)


def test_a_browser_is_let_in_by_the_key_it_was_printed_and_nothing_else(
    project: Path,
) -> None:
    with served() as site:
        stranger = Browser(site)
        assert stranger.get("/api/held").status == 401
        assert stranger.get("/?key=a-guess").status == 403
        assert (
            Browser(site, cookie=f"{site.cookie}=a-guess").get("/api/held").status
            == 401
        )

        browser = Browser(site)
        signed = browser.signs_in()

        assert signed.status == 303
        assert signed.headers["location"] == "/"
        assert "HttpOnly" in signed.headers["set-cookie"]
        assert "SameSite=Strict" in signed.headers["set-cookie"]
        held = browser.get("/api/held")
        assert held.status == 200
        assert held.json()["workspace"] == str(project)


def test_a_page_elsewhere_cannot_reach_the_interface_through_this_machine(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        # A name that resolves here is still not this machine's: a page on another site
        # that rebinds its own name to the loopback is refused before anything is read.
        rebound = Browser(site, host="evil.example", cookie=browser.cookie)
        assert rebound.get("/api/held").status == 403
        assert rebound.get("/").status == 403
        # Any port, though: an address forwarded from another machine names its own.
        forwarded = Browser(site, host="localhost:9000", cookie=browser.cookie)
        assert forwarded.get("/api/held").status == 200

        assert browser.post("/api/settings", {"details": True}).status == 200
        elsewhere = browser.post(
            "/api/settings", {"details": False}, Origin="http://evil.example"
        )
        assert elsewhere.status == 403
        assert (
            browser.post("/api/settings", {"details": False}, Origin="").status == 403
        )
        plain = browser.post(
            "/api/settings", {"details": False}, **{"Content-Type": "text/plain"}
        )
        assert plain.status == 415
        assert browser.get("/api/settings").json()["details"] is True


def test_the_page_is_its_own_files_and_nothing_beside_them(project: Path) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        page = browser.get("/")
        assert page.status == 200
        assert page.headers["content-type"].startswith("text/html")
        assert "default-src 'self'" in page.headers["content-security-policy"]
        assert (
            browser.get("/app.js").headers["content-type"].startswith("text/javascript")
        )
        again = browser.get("/app.js", **{"If-None-Match": page.headers["etag"]})
        assert again.status == 200  # another file's tag is not this one's
        same = browser.get("/app.js")
        assert (
            browser.get("/app.js", **{"If-None-Match": same.headers["etag"]}).status
            == 304
        )

        assert browser.get("/../pyproject.toml").status == 404
        assert browser.get("/held.py").status == 404
        missing = browser.get("/api/nothing")
        assert missing.status == 404
        assert missing.json()["error"]
        assert browser.post("/api/held").status == 405
