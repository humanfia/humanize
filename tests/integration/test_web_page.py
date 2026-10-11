"""`hmz web`'s page, driven in a browser: starting an epic, reading and steering it, finding it.

Each test opens the page the way somebody does -- the printed address in a browser -- over runs
held in the test's own process, with the stand-in `claude` the only coding agent on PATH, and
does what they would: clicks, types and reads what is drawn. Each does so in Chromium and in
WebKit, which the macOS app's window is.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

import hmz.coganchor.models
from tests.integration.doubles_core import install
from tests.integration.doubles_web import ENGINES, opened, served

if TYPE_CHECKING:
    from playwright.sync_api import Page

#: Every settings page, by the word its address ends in.
_PAGES = ("general", "themes", "accounts", "fallback", "runtimes", "workspace", "usage")

#: What the macOS app's window says it is: WKWebView, and the app.
_APP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) humanize-desktop/0.0.0"
)

pytestmark = pytest.mark.parametrize("engine", ENGINES)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    return install(tmp_path, monkeypatch)


def _go(page: Page, address: str) -> None:
    page.evaluate("(to) => { location.hash = to }", address)


def _start_chat(page: Page, task: str) -> None:
    """Starts chat from a new epic's box, on whichever model its agent is offered first."""
    _go(page, "/new?flow=chat")
    expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("chat")
    page.get_by_role("button", name="Options").click()
    expect(page.locator("[data-role=assistant] [data-hmz=pick-model]")).to_have_value(
        "claude-haiku-4-5"
    )
    page.locator("[data-hmz=composer-text]").fill(task)
    page.locator("[data-hmz=composer-text]").press("Enter")
    page.wait_for_url(re.compile(r".*#/epics/[^/]+$"))


def test_a_new_epic_offers_each_role_the_models_its_cli_runs(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        role = page.locator("[data-role=assistant]")
        expect(role.locator("[data-hmz=pick-cli]")).to_have_value("claude")
        expect(role.locator("[data-hmz=pick-account] option").first).to_have_text(
            "Local"
        )
        models = role.locator("[data-hmz=pick-model] option")
        expect(models).to_have_text(["claude-haiku-4-5", "claude-opus-4-1", "Other…"])

        role.locator("[data-hmz=pick-model]").select_option("claude-opus-4-1")
        efforts = role.locator("[data-hmz=pick-effort] option")
        expect(efforts).to_have_text(
            ["Default", "ultracode", "max", "high", "medium", "low"]
        )
        role.locator("[data-hmz=pick-effort]").select_option("max")
        expect(page.locator(".composer-summary")).to_contain_text(
            "assistant: claude/claude-opus-4-1:max"
        )


def test_a_model_no_cli_would_list_is_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    install(tmp_path, monkeypatch)

    def refused(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[()]:
        raise OSError(f"{cli} is not answering")

    monkeypatch.setattr(hmz.coganchor.models, "ask", refused)
    with served() as site, opened(site, engine=engine) as page:
        _go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        role = page.locator("[data-role=assistant]")
        expect(role.locator("[data-hmz=agent-picker] .hint")).to_contain_text(
            "claude is not answering"
        )
        typed = role.locator("[data-hmz=pick-model-typed]")
        typed.fill("claude-sonnet-4-5")
        expect(page.locator(".composer-summary")).to_contain_text(
            "assistant: claude/claude-sonnet-4-5"
        )


def test_an_epic_started_from_the_page_is_drawn_answered_read_and_stopped(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "hello there")

        agent = page.locator("[data-hmz=graph-agent][data-role=assistant]")
        expect(agent).to_be_visible()
        # What the agent said is unread until its session is read.
        expect(agent.locator("[data-hmz=graph-session] .unread")).to_have_count(1)
        expect(page.locator("[data-hmz=epic] .pill-live")).to_be_visible()
        waiting = page.locator("[data-hmz=waiting] [data-hmz=question]")
        expect(waiting).to_be_visible()
        waiting.get_by_role("textbox").fill("and again")
        waiting.get_by_role("button", name="Answer").click()

        page.locator("[data-hmz=session]", has_text="assistant/1").click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: hello there")
        expect(thread).to_contain_text("did: and again")
        expect(page.locator("[data-hmz=say] textarea")).to_have_attribute(
            "placeholder", "Message assistant/1"
        )

        page.locator("[data-hmz=bar] .crumbs a").click()
        expect(agent.locator("[data-hmz=graph-session] .unread")).to_have_count(0)
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("stopped")
        )
        expect(page.locator("[data-hmz=epic] .side-mark").first).to_have_text("■")


def test_an_epic_is_found_by_its_task(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "find me later")
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()

        page.keyboard.press("Control+k")
        search = page.get_by_role("searchbox", name="Find")
        expect(page.locator("[data-hmz=found] .result")).to_have_count(1)
        search.fill("nothing like it")
        expect(page.locator("[data-hmz=found]")).to_contain_text(
            "No epic is like that."
        )
        search.fill("find me")
        expect(page.locator("[data-hmz=found] .result")).to_have_count(1)
        page.keyboard.press("Escape")
        expect(page.locator("[data-hmz=overlay]")).to_be_hidden()


@pytest.mark.parametrize("name", _PAGES)
def test_every_settings_page_opens_and_reads(
    project: Path, name: str, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _go(page, f"/settings/{name}")
        body = page.locator(f"[data-hmz=settings-{name}]")
        expect(body).to_be_visible()
        expect(body.locator(".loading")).to_have_count(0)
        expect(body.locator(".error")).to_have_count(0)
        expect(page.locator(".settings-nav [aria-current=page]")).to_have_count(1)


#: A picture that moves: a disc drawn sliding to and fro, as an SVG animates itself.
_MOVING = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">'
    b'<circle cx="10" cy="20" r="8" fill="#ec6fa3">'
    b'<animate attributeName="cx" values="10;30;10" dur="2s" repeatCount="indefinite"/>'
    b"</circle></svg>"
)


def _paints(page: Page, token: str) -> str:
    return page.evaluate(
        "(token) => getComputedStyle(document.documentElement)"
        ".getPropertyValue(token).trim()",
        token,
    )


def _painted(page: Page, token: str, said: str) -> None:
    """Waits for the page to paint a token with what says `said`: the page lets no string run."""
    for _ in range(100):
        if said in _paints(page, token):
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"{token} is {_paints(page, token)!r}, not {said!r}")


#: Every pair of themes humanize comes with: its own, then one for each Chrysos Heir, named
#: for their Primum Mobile and their colour.
_PAIRS = [
    "Humanize Green",
    "Temperate Gold",
    "Concordant Scarlet",
    "Restrained Crimson",
    "Critical Teal",
    "Desirous Indigo",
    "Peaceful Lilac",
    "Hateful Silver",
    "Devoted Pink",
    "Self-Negating Plum",
    "Dominant Azure",
    "Surviving Jade",
    "Lamenting Orchid",
]


def test_the_colours_are_a_pair_under_auto_or_a_theme(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        page.locator("[data-hmz=machine-menu]").click()
        choices = page.locator("[role=menu] .choice-label")
        expect(choices).to_have_text(["Auto", "Themes", *_PAIRS, "Settings", "Usage"])
        expect(page.locator("[role=menu] .choice-about")).to_have_text("Humanize Green")
        page.get_by_role("menuitem", name="Peaceful Lilac").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        _painted(page, "--paper", "#f7f2f7")
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        _painted(page, "--paper", "#151019")
        # Opened again, the pair is painted before the page is drawn.
        again = page.context.new_page()
        again.emulate_media(color_scheme="dark")
        again.goto(site.address)
        assert _paints(again, "--paper") == "#151019"
        again.close()

        # One theme of a pair, chosen outright, holds whatever the system is.
        _go(page, "/settings/themes")
        expect(page.locator("[data-hmz=pair]")).to_have_count(len(_PAIRS))
        expect(page.locator("[data-hmz=auto-pair]")).to_have_value("peaceful-lilac")
        page.get_by_role("button", name="Use Devoted Pink · Light").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        _painted(page, "--paper", "#fdf6f5")
        page.locator("[data-hmz=auto-pair]").select_option(label="Critical Teal")
        _painted(page, "--paper", "#0f1518")
        page.locator("[data-hmz=auto-light]").select_option(
            label="Hateful Silver · Light"
        )
        expect(page.locator("[data-hmz=auto-pair]")).to_have_value("")


def test_a_theme_is_made_written_out_read_back_and_paired_under_auto(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _go(page, "/settings/themes")
        expect(page.locator("[data-hmz=theme]")).to_have_count(0)
        page.get_by_role("button", name="New", exact=True).click()
        editor = page.locator("[data-hmz=theme-editor]")
        expect(editor).to_be_visible()
        page.locator("[data-hmz=theme-name]").fill("Night")
        page.locator("[data-hmz=theme-base]").select_option("dark")
        # Shown on the page as it is changed, while it is edited.
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.locator("[data-hmz=colour-paper]").fill("#102030")
        page.locator("[data-hmz=colour-control]").fill("not a colour")
        expect(page.locator("[data-hmz=colour-control]")).to_have_attribute(
            "aria-invalid", "true"
        )
        assert _paints(page, "--paper") == "#102030"
        page.locator("[data-hmz=picture-page]").set_input_files(
            {"name": "moving.svg", "mimeType": "image/svg+xml", "buffer": _MOVING}
        )
        expect(page.locator("[data-hmz=plane-page] .theme-thumb")).not_to_have_class(
            re.compile("none")
        )
        assert _paints(page, "--page-image").startswith('url("data:image/svg+xml')

        # Left, the page is drawn in the theme chosen again.
        page.get_by_role("link", name="Done").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        night = page.locator("[data-hmz=theme]", has_text="Night")
        with page.expect_download() as saving:
            night.get_by_role("button", name="Export").click()
        saved = saving.value
        assert saved.suggested_filename == "Night.hmztheme"
        written = Path(saved.path()).read_text()
        night.get_by_role("button", name="Delete").click()
        night.get_by_role("button", name="Delete").click()
        expect(night).to_have_count(0)

        page.locator("[data-hmz=theme-file]").set_input_files(
            {
                "name": "Night.hmztheme",
                "mimeType": "application/json",
                "buffer": written.encode(),
            }
        )
        expect(night).to_have_count(1)
        page.locator("[data-hmz=auto-dark]").select_option(label="Night · Dark")
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        _painted(page, "--paper", "#102030")
        _painted(page, "--page-image", "data:image/svg+xml")
        # Where motion is asked to be reduced, the picture is held as it is first drawn.
        page.emulate_media(reduced_motion="reduce")
        _painted(page, "--page-image", "data:image/png")
        page.emulate_media(color_scheme="light")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        # Opened again, it is painted before the page is drawn.
        again = page.context.new_page()
        again.emulate_media(color_scheme="dark")
        again.goto(site.address)
        assert again.evaluate("document.documentElement.dataset.theme") == "dark"
        assert _paints(again, "--paper") == "#102030"
        again.close()


def test_a_file_that_is_not_a_theme_is_refused(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _go(page, "/settings/themes")
        page.locator("[data-hmz=theme-file]").set_input_files(
            {"name": "x.hmztheme", "mimeType": "application/json", "buffer": b"{}"}
        )
        expect(page.locator(".toast")).to_have_text("This is not a theme file")
        expect(page.locator("[data-hmz=theme]")).to_have_count(0)


def test_a_newer_release_is_offered_under_the_machine(
    project: Path, engine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    import hmz.coganchor
    from hmz.coganchor import releases

    pypi = project.parent / "pypi.json"
    pypi.write_text(json.dumps({"info": {"version": "99.0.0"}}))
    monkeypatch.setenv(releases.WHENCE, str(pypi))
    monkeypatch.setattr(hmz.coganchor, "__version__", "0.1.0", raising=False)
    releases.fetch()
    with served() as site, opened(site, engine=engine) as page:
        expect(page.locator("[data-hmz=newer]")).to_be_visible()
        page.locator("[data-hmz=machine-menu]").click()
        expect(page.locator("[role=menu] .choice-label")).to_have_text(
            ["Auto", "Themes", *_PAIRS, "Update", "Settings", "Usage"]
        )
        expect(page.locator("[role=menu] .choice-about")).to_have_text(
            ["Humanize Green", "hmz 99.0.0"]
        )


def test_a_flow_is_opened_and_started_from_the_flows(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        page.get_by_role("link", name="Flows").click()
        page.locator(".card[data-flow=chat]").click()
        expect(page.locator(".flow-detail h2")).to_have_text("chat")
        page.get_by_role("link", name="New epic").last.click()
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("chat")


def test_on_a_phone_the_sidebar_is_a_drawer(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, width=390, height=844) as page:
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar).not_to_be_in_viewport()
        page.locator("[data-hmz=bar] .bar-side").click()
        expect(sidebar).to_be_in_viewport()
        page.get_by_role("link", name="Flows").click()
        expect(sidebar).not_to_be_in_viewport()


def test_in_the_macos_app_the_top_row_is_drawn_around_the_traffic_lights(
    project: Path, engine: str
) -> None:
    """The app's window draws the page to its top edge, its traffic lights over the top left."""
    # How far across they reach, at most.
    lights = 76
    clicked = "a, button, input, select, textarea, summary, [role=tab]"

    def left(page: Page, selector: str) -> float:
        box = page.locator(selector).first.bounding_box()
        assert box
        return box["x"]

    with served() as site, opened(site, engine=engine) as page:
        assert page.evaluate("document.documentElement.dataset.shell") is None
        expect(page.locator("[data-tauri-drag-region]")).to_have_count(0)
        assert left(page, ".brand") < lights

    # Said before the page is drawn: by the time its body is, so it never moves.
    at_body = (
        "new MutationObserver((_, seen) => { if (document.body) {"
        " window.shellAtBody = document.documentElement.dataset.shell; seen.disconnect() }"
        " }).observe(document, { childList: true, subtree: true })"
    )
    with (
        served() as site,
        opened(site, engine=engine, user_agent=_APP, init=at_body) as page,
    ):
        assert page.evaluate("window.shellAtBody") == "macos"
        assert left(page, ".brand") >= lights
        for row in ("[data-hmz=sidebar] .side-top", "[data-hmz=bar]"):
            expect(page.locator(row)).to_have_attribute(
                "data-tauri-drag-region", "deep"
            )
        expect(page.locator(f":is({clicked})[data-tauri-drag-region]")).to_have_count(0)
        # A menu opened in a row is not what the window is dragged by.
        page.locator("[data-hmz=machine-menu]").click()
        expect(page.locator("[role=menu]")).to_have_attribute(
            "data-tauri-drag-region", "false"
        )
        page.keyboard.press("Escape")

        page.locator(".side-fold").click()
        assert left(page, "[data-hmz=bar] .bar-side") >= lights
        # Full screen, where they are gone, it is drawn as in a browser.
        page.evaluate(
            "document.documentElement.toggleAttribute('data-fullscreen', true)"
        )
        assert left(page, "[data-hmz=bar] .bar-side") < lights

        page.set_viewport_size({"width": 700, "height": 800})
        page.evaluate(
            "document.documentElement.toggleAttribute('data-fullscreen', false)"
        )
        assert left(page, "[data-hmz=bar] .bar-side") >= lights


def test_every_label_is_a_word_or_a_phrase(project: Path, engine: str) -> None:
    """A button, a tab, a menu item or a heading names a thing; it never says a sentence."""
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "label me")
        said: list[str] = []
        settings = (f"/settings/{one}" for one in _PAGES)
        for address in ("/new?flow=chat", "/flows", "/search", *settings):
            _go(page, address)
            page.wait_for_timeout(300)
            if address.startswith("/new"):
                page.get_by_role("button", name="Options").click()
            said += page.locator(
                "button:visible, [role=tab]:visible, [role=menuitem]:visible, "
                "h2:visible:not(.greeting), h3:visible, .field > .label:visible, "
                ".field > label:visible"
            ).all_inner_texts()
        page.go_back()
        # A card or a row drawn as one button -- a flow, the workspace -- says several
        # things a line apiece; each of those lines is what is held to it.
        long = [
            one
            for one in (text.strip() for text in said)
            if one
            and "\n" not in one
            and (len(one.split()) > 4 or re.search(r"[.?!]$", one))
        ]
        assert not long, f"labels said as sentences: {long}"


def test_a_setup_is_saved_without_starting_an_epic(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        role = page.locator("[data-role=assistant]")
        expect(role.locator("[data-hmz=pick-model] option").first).to_have_text(
            "claude-haiku-4-5"
        )
        role.locator("[data-hmz=pick-model]").select_option("claude-opus-4-1")
        page.locator("[data-hmz=options]").get_by_role("button", name="Save").click()
        expect(
            page.locator("[data-hmz=options]").get_by_role("button", name="Saved")
        ).to_be_visible()

        page.reload()
        _go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        expect(role.locator("[data-hmz=pick-model]")).to_have_value("claude-opus-4-1")


def test_an_epic_is_read_as_its_log_and_its_agents_as_a_list(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "log me")
        expect(page.locator("[data-hmz=waiting] [data-hmz=question]")).to_be_visible()

        inspector = page.locator("[data-hmz=inspector]")
        expect(inspector.locator("[data-hmz=spending]")).to_contain_text(
            "claude-haiku-4-5"
        )
        expect(inspector.locator("[data-hmz=frontends]")).to_contain_text("this page")

        page.locator("[data-hmz=sidebar] [data-hmz=log]").click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: log me")
        expect(thread).to_contain_text("human asks")
        expect(page.locator("[data-hmz=bar] .crumbs")).to_contain_text("Log")

        page.locator("[data-hmz=bar] .crumbs a").click()
        page.locator(".shape-switch").get_by_role("button", name="List").click()
        listed = page.locator("[data-hmz=agent-list] [data-role=assistant]")
        expect(listed).to_contain_text("assistant/1")
        listed.get_by_role("link", name="≡ log").click()
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: log me")
        page.locator("[data-hmz=bar] .crumbs a").click()
        page.locator(".shape-switch").get_by_role("button", name="Graph").click()
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()


def test_an_ended_epic_is_exported_and_its_address_copied(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "keep me")
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("stopped")
        )

        with page.expect_download() as saving:
            page.get_by_role("link", name="Export").click()
        saved = saving.value
        assert saved.suggested_filename.endswith(".tar.gz")
        assert Path(saved.path()).read_bytes()[:2] == b"\x1f\x8b"

        # WebKit lets a click write unasked, and knows no permission to write by.
        writes = ["clipboard-write"] if engine == "chromium" else []
        page.context.grant_permissions(["clipboard-read", *writes])
        page.get_by_role("button", name="Copy link").click()
        expect(page.get_by_role("button", name="Copied")).to_be_visible()
        assert page.evaluate("navigator.clipboard.readText()") == page.url


@pytest.mark.parametrize(("width", "dark"), [(1280, False), (390, True)])
def test_the_panel_says_every_figure_in_words_and_within_its_edges(
    project: Path, engine: str, width: int, dark: bool
) -> None:
    with served() as site, opened(site, engine=engine, width=width, dark=dark) as page:
        _start_chat(page, "fit me")
        expect(page.locator("[data-hmz=waiting] [data-hmz=question]")).to_be_visible()
        if width < 860:
            page.locator("[data-hmz=bar] .panel-toggle").click()
        inspector = page.locator("[data-hmz=inspector]")
        expect(inspector.locator("[data-hmz=environments]")).to_contain_text(
            "assistant/1 workspace · local"
        )
        expect(inspector.locator("[data-hmz=spending]")).to_contain_text("cache write")
        assert not re.search(
            r"\[object |\bundefined\b|\bNaN\b|\bnull\b", inspector.inner_text()
        )
        # Its last column inside the panel, as drawn or once scrolled to.
        outside = page.evaluate(
            """() => {
              const wrap = document.querySelector('[data-hmz=spending]').parentElement
              wrap.scrollLeft = wrap.scrollWidth
              const last = wrap.querySelector('th:last-child').getBoundingClientRect()
              const panel = document.querySelector('[data-hmz=inspector]').getBoundingClientRect()
              return last.right - Math.min(wrap.getBoundingClientRect().right, panel.right)
            }"""
        )
        assert outside <= 1


def test_an_earlier_epic_is_read_out_of_its_logs_and_asked_beside(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember papaya")
        expect(page.locator("[data-hmz=waiting] [data-hmz=question]")).to_be_visible()
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        _start_chat(page, "and then this")
        expect(page.locator("[data-hmz=waiting] [data-hmz=question]")).to_be_visible()
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()

        page.locator("[data-hmz=epic]", has_text="remember papaya").click()
        page.locator(".graph-note").get_by_role("button", name="Read turns").click()
        agent = page.locator("[data-hmz=graph-agent][data-role=assistant]")
        expect(agent.locator(".capsule")).to_have_count(1)

        agent.locator("[data-hmz=graph-session]").click()
        expect(page.locator("[data-hmz=thread]")).to_contain_text(
            "did: remember papaya"
        )

        page.get_by_role("tab", name="Aside").click()
        aside = page.locator("[data-hmz=btw]")
        aside.get_by_role("combobox").select_option("assistant/1")
        aside.locator("textarea").fill("what was the word")
        aside.locator("textarea").press("Enter")
        expect(page.locator("[data-hmz=btw-log]")).to_contain_text(
            "read-only side copy of the flow session"
        )
