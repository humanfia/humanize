"""The web interface's server: who it lets in, the page's files, `/here`, and `/rpc`.

Served over this machine's daemon -- the test's own, in this process -- and asked as a browser
asks: its files over HTTP, and JSON-RPC to the daemon over the WebSocket `/rpc`, through the
real bridge.
"""

from __future__ import annotations

import re
import socket
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus

from hmz import home
from hmz.web import kept_port, serve
from tests.integration.doubles_daemon import WAITS, written
from tests.integration.doubles_web import PATIENCE, Browser, served

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon")


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project `hmz web` is started in, with a flow that runs until it is stopped."""
    at = tmp_path / "project"
    at.mkdir()
    written(at, "waits", WAITS)
    monkeypatch.chdir(at)
    return at


def test_a_browser_is_let_in_by_the_key_it_was_printed_and_nothing_else(
    project: Path,
) -> None:
    with served() as site:
        stranger = Browser(site)
        refused = stranger.get("/here")
        assert refused.status == 401
        assert refused.json() == {
            "error": "Open the address hmz web printed to let this browser in."
        }
        assert stranger.get("/?key=a-guess").status == 403
        wrong = Browser(site, cookie=f"{site.cookie}=a-guess")
        assert wrong.get("/here").status == 401
        with pytest.raises(InvalidStatus) as closed:
            wrong.opens("/rpc")
        assert closed.value.response.status_code == 401

        browser = Browser(site)
        signed = browser.signs_in()

        assert signed.status == 303
        assert signed.headers["location"] == "/"
        assert "HttpOnly" in signed.headers["set-cookie"]
        assert "SameSite=Strict" in signed.headers["set-cookie"]
        here = browser.get("/here")
        assert here.status == 200
        assert here.headers["cache-control"] == "no-store"
        assert here.json() == {"here": str(project.resolve())}


def test_any_name_this_machine_is_reached_by_is_answered_but_only_with_the_key(
    project: Path,
) -> None:
    del project
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        # A page on another site that rebinds its own name to the loopback is handed that
        # name's cookies, never this one: it is a stranger, however it got here.
        assert Browser(site, host="evil.example").get("/here").status == 401
        # A port forwarded or proxied on to this one, from here, names what it likes.
        proxied = Browser(site, host="hmz.example", cookie=browser.cookie)
        assert proxied.get("/here").status == 200
        assert proxied.get("/").status == 200
        assert proxied.get("/here", Origin="http://hmz.example").status == 200
        # One that rewrites `Host` is not this server's own page to a browser that says
        # only where its page came from (Section 4.4.6 of web.md).
        assert proxied.get("/here", Origin="http://public.example").status == 403

        # Only this server's own page is admitted, as the browser says it.
        for came in ("same-site", "cross-site", "none"):
            assert browser.get("/here", **{"Sec-Fetch-Site": came}).status == 403
        assert browser.get("/here", Origin="http://127.0.0.1:3000").status == 403
        assert (
            browser.get("/here", Origin=f"https://127.0.0.1:{site.port}").status == 403
        )
        assert browser.get("/here", **{"Sec-Fetch-Site": "same-origin"}).status == 200
        with pytest.raises(InvalidStatus) as elsewhere:
            browser.opens(
                "/rpc", Origin="http://evil.example", **{"Sec-Fetch-Site": "cross-site"}
            )
        assert elsewhere.value.response.status_code == 403


def _policy() -> str:
    """The Content-Security-Policy protocol/web.md (Section 4.5.5) serves a page with."""
    text = " ".join(
        (Path(__file__).parents[2] / "protocol" / "web.md").read_text().split()
    )
    found = re.search(r"\*\*4\.5\.5\*\* .*?`Content-Security-Policy: ([^`]*)`", text)
    assert found is not None
    return found[1]


def test_the_page_is_its_own_files_and_nothing_beside_them(project: Path) -> None:
    del project
    with served() as site:
        browser = Browser(site)

        # Served without the cookie.
        page = browser.get("/")
        assert page.status == 200
        assert page.headers["content-type"].startswith("text/html")
        assert page.headers["content-security-policy"] == _policy()
        assert page.headers["cache-control"] == "no-cache"
        for header, value in (
            ("x-content-type-options", "nosniff"),
            ("referrer-policy", "no-referrer"),
            ("x-frame-options", "DENY"),
        ):
            assert page.headers[header] == value
        script = browser.get("/rpc/client.js")
        assert script.headers["content-type"].startswith("text/javascript")
        assert (
            browser.get("/app.js", **{"If-None-Match": script.headers["etag"]}).status
            == 200
        )
        assert (
            browser.get(
                "/rpc/client.js", **{"If-None-Match": script.headers["etag"]}
            ).status
            == 304
        )

        # The language is set by a script of its own, before the page's: nothing is drawn in
        # another. The catalogs of every language are the page's files, a fragment an area.
        scripts = re.findall(r'<script[^>]*src="([^"]+)"', page.body.decode())
        assert scripts.index("/lang.js") < scripts.index("/app.js")
        for path in (
            "/lang.js",
            "/i18n.js",
            "/i18n/en.js",
            "/i18n/zh-Hans.js",
            "/i18n/zh-Hant.js",
            "/i18n/zh-Hans/core.js",
            "/i18n/zh-Hant/settings.js",
            "/views/settings/language.js",
        ):
            catalog = browser.get(path)
            assert catalog.status == 200, path
            assert catalog.headers["content-type"].startswith("text/javascript"), path
            assert catalog.headers["cache-control"] == "no-cache", path

        for nothing in (
            "/../pyproject.toml",
            "/site.py",
            "/api/held",
            "/app.JS",
            "/.hidden.js",
        ):
            missing = browser.get(nothing)
            assert missing.status == 404, nothing
            assert missing.json() == {"error": "There is nothing here by that name."}
            assert missing.headers["content-type"] == "application/json; charset=utf-8"
        assert browser.get("/" + "a" * 200 + ".js").status == 404

        written_ = browser.asks("POST", "/", b"{}")
        assert written_.status == 405
        assert written_.json() == {"error": "Only the page's own files are here."}
        assert browser.asks("HEAD", "/app.js").status == 405
        # The cookie is asked before the method, of what only a browser let in is answered.
        assert browser.asks("POST", "/here").status == 401
        browser.signs_in()
        assert browser.asks("POST", "/here").status == 405
        for headers in ({}, {"Upgrade": "websocket", "Connection": "Upgrade"}):
            plain = browser.get("/rpc", **headers)
            assert plain.status == 400
            assert plain.json() == {"error": "Open this as a WebSocket."}


def test_the_editor_and_the_terminal_are_served_as_the_pages_own_files(
    project: Path,
) -> None:
    del project
    with served() as site:
        browser = Browser(site)

        for path, kind in (
            ("/vendor/codemirror.js", "text/javascript"),
            ("/vendor/xterm.js", "text/javascript"),
            ("/vendor/xterm_css.css", "text/css"),
        ):
            got = browser.get(path)
            assert got.status == 200, path
            assert got.headers["content-type"].startswith(kind), path
            assert got.headers["cache-control"] == "no-cache", path
            # Only a page is held to the policy; what it loads is held by the page's.
            assert "content-security-policy" not in got.headers, path
            # Each carries the licences of what was bundled into it.
            assert got.body.startswith(b"/*! Third-party code"), path
            assert b"MIT" in got.body[:20_000], path
            again = browser.get(path, **{"If-None-Match": got.headers["etag"]})
            assert again.status == 304, path

        # What builds them is not the page's.
        for nothing in ("/vendor/package.json", "/vendor/codemirror.mjs"):
            assert browser.get(nothing).status == 404, nothing

        # The editor's and the terminal's own scripts style what they draw, and nothing but the
        # page's own files is ever run.
        served_policy = browser.get("/").headers["content-security-policy"]
        policy = {
            name: value
            for name, _, value in (
                part.strip().partition(" ") for part in served_policy.split(";")
            )
        }
        assert policy["style-src"] == "'self' 'unsafe-inline'"
        assert policy["script-src"] == "'self'"


def test_a_picture_of_the_page_is_served_as_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from hmz.web import site as serving

    package = tmp_path / "web"
    (package / "static" / "ai-chan").mkdir(parents=True)
    (package / "static" / "ai-chan" / "avatar.webp").write_bytes(
        b"RIFF\x04\x00\x00\x00WEBP"
    )

    def files(_: str) -> Path:
        return package

    # The page's own files alone are looked for in `package`.
    monkeypatch.setattr(serving, "resources", SimpleNamespace(files=files))
    with served() as site:
        avatar = Browser(site).get("/ai-chan/avatar.webp")
        assert avatar.status == 200
        assert avatar.headers["content-type"] == "image/webp"
        assert avatar.body == b"RIFF\x04\x00\x00\x00WEBP"


def test_a_face_is_framed_by_the_page_alone_and_reaches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from hmz.web import site as serving

    real = serving.resources.files("hmz.web")
    package = tmp_path / "web"
    (package / "static" / "faces").mkdir(parents=True)
    (package / "static" / "vendor").mkdir()
    for name in ("index.html", "app.js"):
        (package / "static" / name).write_bytes(
            real.joinpath("static", name).read_bytes()
        )
    (package / "static" / "faces" / "frame.html").write_bytes(
        real.joinpath("static", "faces", "frame.html").read_bytes()
    )
    (package / "static" / "vendor" / "markdown.js").write_text("export {}\n")

    def files(_: str) -> Path:
        return package

    monkeypatch.setattr(serving, "resources", SimpleNamespace(files=files))
    with served() as site:
        browser = Browser(site)

        # The page may frame its own files, and is framed by nothing.
        page = browser.get("/")
        assert "frame-src 'self'" in page.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        assert page.headers["x-frame-options"] == "DENY"

        # The face's document: its own policy, framed by the page's origin alone.
        frame = browser.get("/faces/frame.html")
        assert frame.status == 200
        assert frame.headers["content-security-policy"] == (
            "default-src 'none'; script-src 'unsafe-inline' 'self'; "
            "style-src 'unsafe-inline' 'self'; img-src data: blob:; font-src data:; "
            "connect-src 'none'; frame-ancestors 'self'"
        )
        assert frame.headers["x-frame-options"] == "SAMEORIGIN"
        assert "access-control-allow-origin" not in frame.headers
        # Said in the file too, for a server that gives every page one policy.
        assert b"connect-src 'none'" in frame.body

        # A library a face imports from its opaque origin is shared with that origin alone;
        # nothing else is.
        library = browser.get("/vendor/markdown.js", Origin="null")
        assert library.headers["access-control-allow-origin"] == "null"
        elsewhere = browser.get("/vendor/markdown.js", Origin="https://example.com")
        assert "access-control-allow-origin" not in elsewhere.headers
        script = browser.get("/app.js", Origin="null")
        assert "access-control-allow-origin" not in script.headers
        assert script.headers["x-frame-options"] == "DENY"

        # A browser that has the library from the page asks a face's copy of it conditionally:
        # told it has it, it is told the face may read it too, and nothing else is.
        had = {"If-None-Match": library.headers["etag"]}
        kept = browser.get("/vendor/markdown.js", Origin="null", **had)
        assert kept.status == 304
        assert kept.headers["access-control-allow-origin"] == "null"
        elsewhere = browser.get(
            "/vendor/markdown.js", Origin="https://example.com", **had
        )
        assert elsewhere.status == 304
        assert "access-control-allow-origin" not in elsewhere.headers
        script = browser.get(
            "/app.js", Origin="null", **{"If-None-Match": script.headers["etag"]}
        )
        assert script.status == 304
        assert "access-control-allow-origin" not in script.headers


def test_what_another_site_left_in_the_cookie_jar_is_not_this_ones_business(
    project: Path,
) -> None:
    del project
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        browser.cookie = f"$Version=1; theirs=a b; {browser.cookie}"

        assert browser.get("/here").status == 200


@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6 here")
def test_both_loopbacks_are_answered_on_one_port(project: Path) -> None:
    del project
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
        assert there.get("/here").status == 200
        assert Browser(site, at="::1").get("/here").status == 401


def test_the_page_speaks_to_this_machines_daemon_over_rpc(project: Path) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        with browser.session() as page:
            assert page.said["device"] == "local"
            assert page.said["paired"] is True
            listed = page.call("workspaces.list", here=str(project))
            assert str(project.resolve()) in str(listed)

            sub = page.call("epic.attach", workspace=str(project), figures=True)["sub"]
            page.until(
                lambda method, said: (
                    method == "epic.event"
                    and said["sub"] == sub
                    and said["message"]["type"] == "live"
                ),
                "live",
            )
            started = page.call(
                "epic.start",
                sub=sub,
                flow="./waits",
                task="t",
                budget={"cost": 1},
                idem="a",
            )
            assert started["run"] == 1
            page.until(
                lambda method, said: (
                    method == "epic.event"
                    and said["message"]["type"] == "started"
                    and said["message"]["task"] == "t"
                ),
                "the epic started",
            )
            running = page.call("hosts.running")["running"]
            assert [(one["workspace"], one["task"]) for one in running] == [
                (str(project.resolve()), "t")
            ]
            page.call("epic.stop", sub=sub, idem="b")
            page.until(
                lambda method, said: (
                    method == "epic.event" and said["message"]["type"] == "ended"
                ),
                "the epic ended",
            )
            page.call("hosts.stop", workspace=str(project))


def test_a_text_message_on_rpc_closes_it(project: Path) -> None:
    del project
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        socket_ = browser.opens("/rpc")
        socket_.send("hello")
        with pytest.raises(ConnectionClosed):
            socket_.recv(timeout=PATIENCE)


def test_the_port_listened_on_is_kept_and_listened_on_again(project: Path) -> None:
    del project
    assert kept_port() == 0
    (home()).mkdir(parents=True, exist_ok=True)
    (home() / "web-port").write_text("70000")
    assert kept_port() == 0

    said: list[str] = []

    def shown(address: str) -> None:
        said.append(address)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        serve(shown=shown)
    port = kept_port()
    assert port > 0
    assert said == [said[0]]
    assert f":{port}/?key=" in said[0]
    assert (home() / "web-port").read_text() == str(port)
    written_at = (home() / "web-port").stat().st_mtime_ns

    with pytest.raises(KeyboardInterrupt):
        serve(shown=shown)
    assert f":{port}/?key=" in said[1]
    assert (home() / "web-port").stat().st_mtime_ns == written_at

    # The port kept taken, any free one is listened on.
    with socket.create_server(("127.0.0.1", port)), pytest.raises(KeyboardInterrupt):
        serve(shown=shown)
    assert f":{port}/?key=" not in said[2]
    assert kept_port() != port
