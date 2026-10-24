"""`hmz web`: who is let in, from where, what a page may send, and the files it is made of."""

from __future__ import annotations

import socket
import subprocess
import urllib.parse
from typing import TYPE_CHECKING

import pytest

from hmz import home
from hmz.runtime import backing
from tests.integration.doubles_core import AGENT, hmz_exec, install
from tests.integration.doubles_web import Browser, backed_up_elsewhere, served

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
        assert held.json()["here"] == str(project.resolve())


@pytest.mark.parametrize("distro", ["Debian", ""])
def test_the_page_is_told_the_wsl_distribution_hmz_runs_in(
    project: Path, monkeypatch: pytest.MonkeyPatch, distro: str
) -> None:
    monkeypatch.setenv("WSL_DISTRO_NAME", distro)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        assert browser.get("/api/held").json()["wsl"] == (distro or None)


def test_a_newer_release_is_in_what_the_page_is_told(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    import time

    import hmz.coganchor
    from hmz.coganchor import releases

    pypi = project.parent / "pypi.json"
    pypi.write_text(json.dumps({"info": {"version": "99.0.0"}}))
    monkeypatch.setenv(releases.WHENCE, str(pypi))
    monkeypatch.setattr(hmz.coganchor, "__version__", "0.1.0", raising=False)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        # Asked of PyPI as it starts, on a thread of its own.
        until = time.monotonic() + 10
        while not (newer := browser.get("/api/held").json()["newer"]):
            assert time.monotonic() < until
            time.sleep(0.05)
        assert newer == "99.0.0"


def test_any_name_this_machine_is_reached_by_is_answered_but_only_with_the_key(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        # A page on another site that rebinds its own name to the loopback is handed that
        # name's cookies, never this one: it is a stranger, however it got here.
        rebound = Browser(site, host="evil.example")
        assert rebound.get("/api/held").status == 401
        # A port forwarded or proxied on to this one, from here, names what it likes: a
        # browser let in there carries the key there too, and its page writes as its own.
        proxied = Browser(site, host="hmz.example", cookie=browser.cookie)
        assert proxied.get("/api/held").status == 200
        assert proxied.get("/").status == 200
        said = {"Origin": "https://hmz.example"}
        assert proxied.post("/api/settings", {"details": True}, **said).status == 200
        rewritten = {"Origin": "https://hmz.example", "Sec-Fetch-Site": "same-origin"}
        assert (
            browser.post("/api/settings", {"details": True}, **rewritten).status == 200
        )
        assert (
            browser.post(
                "/api/settings",
                {"details": True},
                **{"Origin": "https://hmz.example", "Sec-Fetch-Site": "same-site"},
            ).status
            == 403
        )

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


def test_a_page_from_another_port_of_this_machine_reaches_nothing(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        # Another port of this machine is the same site to a cookie: the browser sends it, and
        # says where the request came from, which is what refuses it.
        for came in ("same-site", "cross-site"):
            asked = browser.get("/api/held", **{"Sec-Fetch-Site": came})
            assert asked.status == 403
        assert browser.get("/api/held", Origin="http://127.0.0.1:3000").status == 403
        assert (
            browser.get("/api/held", **{"Sec-Fetch-Site": "same-origin"}).status == 200
        )
        assert browser.get("/api/held", **{"Sec-Fetch-Site": "none"}).status == 200

        # And what a page may have set up is only a flow on offer: never one it names by path
        # or by repository, which setting it up would run.
        named = urllib.parse.quote("git+https://example.invalid/flows.git")
        assert browser.get(f"/api/flow?name={named}").status == 404
        assert browser.get("/api/flow?name=chat").json()["name"] == "chat"


def test_what_another_site_left_in_the_cookie_jar_is_not_this_ones_business(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        browser.cookie = f"$Version=1; theirs=a b; {browser.cookie}"

        assert browser.get("/api/held").status == 200
        lying = browser.post("/api/settings", {}, **{"Content-Length": "-1"})
        assert lying.status == 411


@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6 here")
def test_both_loopbacks_are_answered_on_one_port(project: Path) -> None:
    try:
        with socket.create_server(("::1", 0), family=socket.AF_INET6):
            pass
    except OSError:
        pytest.skip("no IPv6 loopback here")
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        there = Browser(
            site, host=f"[::1]:{site.port}", cookie=browser.cookie, at="::1"
        )
        assert there.get("/api/held").status == 200
        assert Browser(site, at="::1").get("/api/held").status == 401


def test_an_account_is_corrected_without_its_values_being_shown(project: Path) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        ways = browser.get("/api/accounts").json()["backends"]
        claude = next(one for one in ways if one["cli"] == "claude")
        way = next(one for one in claude["ways"] if not one["terminal"] and one["asks"])
        asks = {one["env"]: "first" for one in way["asks"] if not one["fixed"]}
        made = browser.post(
            "/api/accounts",
            {"cli": "claude", "name": "work", "way": way["name"], "answers": asks},
        )
        assert made.status == 200, made.body

        key = next(iter(asks))
        corrected = browser.post(
            "/api/accounts/correct",
            {"cli": "claude", "name": "work", "answers": {key: "second"}},
        )
        assert corrected.status == 200, corrected.body
        assert "second" not in corrected.body.decode()
        assert "first" not in corrected.body.decode()
        unknown = browser.post(
            "/api/accounts/correct",
            {"cli": "claude", "name": "work", "answers": {"NOT_ASKED": "x"}},
        )
        assert unknown.status == 400
        missing = browser.post(
            "/api/accounts/correct", {"cli": "claude", "name": "nobody", "answers": {}}
        )
        assert missing.status == 404


def test_backup_targets_are_written_and_read_with_nothing_signed_into_them(
    project: Path,
) -> None:
    secret = "https://me:hunter2@example.com/epics.git"
    lab = {"name": "lab", "url": secret, "policies": ["end", "interval"], "every": 5}
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        written = browser.post(
            "/api/settings", {"backup": {"targets": [lab], "defaults": ["lab"]}}
        )

        assert written.status == 200, written.body
        said = written.json()["backup"]
        assert said == {
            "targets": [
                {
                    "name": "lab",
                    "url": "https://***@example.com/epics.git",
                    "branch": "main",
                    "policies": ["end", "interval"],
                    "every": 5,
                }
            ],
            "defaults": ["lab"],
        }
        assert "hunter2" not in browser.get("/api/settings").body.decode()

        # Sent back as it was shown, the URL is the one written; a bad target writes nothing.
        kept = said["targets"][0] | {"branch": "epics"}
        sent = {"backup": {"targets": [kept], "defaults": []}}
        assert browser.post("/api/settings", sent).status == 200
        bad = browser.post(
            "/api/settings",
            {"backup": {"targets": [kept | {"policies": ["never"]}]}, "details": True},
        )
        assert bad.status == 400
        moved = {"targets": [kept | {"name": "elsewhere"}]}
        assert browser.post("/api/settings", {"backup": moved}).status == 400
        file = (home() / "settings.yaml").read_text()
        assert secret in file
        assert "branch: epics" in file
        assert browser.get("/api/settings").json()["details"] is not True


def test_an_epic_is_uploaded_without_the_page_waiting_on_the_push(
    project: Path,
) -> None:
    bare = project.parent / "epics.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    assert hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", "hi").returncode == 0
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        name = browser.get("/api/runs").json()["runs"][0]["name"]
        assert browser.post(f"/api/runs/{name}/backup").status == 409

        target = {"name": "t", "url": str(bare)}
        browser.post("/api/settings", {"backup": {"targets": [target]}})
        assert browser.post(f"/api/runs/{name}/backup", {"to": ["x"]}).status == 400
        queued = browser.post(f"/api/runs/{name}/backup", {"to": ["t"]})

        assert queued.status == 200, queued.body
        assert queued.json() == {"queued": ["t"]}
        assert backing.wait(60)
        backed = browser.get(f"/api/runs/{name}").json()["backed"]
        assert backed["t"]["ok"] is True
        log = subprocess.run(
            ["git", "--git-dir", str(bare), "log", "--format=%s", "main"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert log.stdout.splitlines() == [f"Back up epic {name} (manual)"]


def test_the_backup_saved_for_a_flow_is_what_it_opens_on(project: Path) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        assert browser.get("/api/flow?name=chat").json()["remembered"]["backup"] is None
        setup = {"flow": "chat", "agents": {"assistant": AGENT}}
        target = {"name": "t", "url": str(project.parent / "epics.git")}
        browser.post("/api/settings", {"backup": {"targets": [target]}})

        assert browser.post("/api/flows/setup", setup | {"backup": "t"}).status == 400
        assert browser.post("/api/flows/setup", setup | {"backup": ["x"]}).status == 400
        saved = browser.post("/api/flows/setup", setup | {"backup": ["t"]})
        assert saved.status == 200, saved.body
        assert saved.json()["remembered"]["backup"] == ["t"]
        browser.post("/api/flows/setup", setup | {"backup": []})
        assert browser.get("/api/flow?name=chat").json()["remembered"]["backup"] == []


def test_what_of_a_flow_is_profiled_is_saved_apart(project: Path) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        setup = {"flow": "chat", "agents": {"assistant": AGENT}}

        browser.post("/api/flows/setup", setup | {"profile_flow": True})
        remembered = browser.get("/api/flow?name=chat").json()["remembered"]
        assert (remembered["profile_flow"], remembered["profile_environment"]) == (
            True,
            False,
        )
        browser.post("/api/flows/setup", setup | {"profile_environment": True})
        remembered = browser.get("/api/flow?name=chat").json()["remembered"]
        assert (remembered["profile_flow"], remembered["profile_environment"]) == (
            False,
            True,
        )


def test_an_epic_backed_up_elsewhere_is_listed_downloaded_and_read(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = backed_up_elsewhere(tmp_path, monkeypatch)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        assert browser.get("/api/runs").json()["runs"] == []

        listed = browser.get("/api/backups/t/epics")

        assert listed.status == 200, listed.body
        (held,) = listed.json()["epics"]
        assert (held["epic"], held["flow"], held["task"], held["how"]) == (
            name,
            "chat",
            "hi",
            "done",
        )
        assert held["here"] is False
        assert held["workspace"] == str(project.resolve())
        pulled = browser.post("/api/backups/t/pull", {"key": held["key"]})
        assert pulled.status == 200, pulled.body
        assert pulled.json() == {"name": name}
        read = browser.get(f"/api/runs/{name}").json()
        assert (read["task"], read["foreign"]) == ("hi", "")
        assert browser.get("/api/backups/t/epics").json()["epics"][0]["here"] is True

        again = browser.post("/api/backups/t/pull", {"key": held["key"]})
        assert again.status == 400
        assert "already here" in again.json()["error"]
        assert browser.get("/api/backups/x/epics").status == 400
        assert browser.post("/api/backups/t/pull", {"key": "../x/y"}).status == 400
        lost = {"name": "lost", "url": str(tmp_path / "nowhere.git")}
        browser.post("/api/settings", {"backup": {"targets": [lost]}})
        assert browser.get("/api/backups/lost/epics").status == 502
