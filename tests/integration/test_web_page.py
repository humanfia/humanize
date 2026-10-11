"""`hmz web`'s page, driven in a browser: starting an epic, reading and steering it, finding it.

Each test opens the page the way somebody does -- the printed address in a browser -- over runs
held in the test's own process, with the stand-in `claude` the only coding agent on PATH, and
does what they would: clicks, types and reads what is drawn.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

import hmz.coganchor.models
from tests.integration.doubles_core import install
from tests.integration.doubles_web import opened, served

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page

#: Every settings page, by the word its address ends in.
_PAGES = ("general", "accounts", "fallback", "runtimes", "workspace", "usage")


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


def test_a_new_epic_offers_each_role_the_models_its_cli_runs(project: Path) -> None:
    with served() as site, opened(site) as page:
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(tmp_path, monkeypatch)

    def refused(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[()]:
        raise OSError(f"{cli} is not answering")

    monkeypatch.setattr(hmz.coganchor.models, "ask", refused)
    with served() as site, opened(site) as page:
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
    project: Path,
) -> None:
    with served() as site, opened(site) as page:
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


def test_an_epic_is_found_by_its_task(project: Path) -> None:
    with served() as site, opened(site) as page:
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
def test_every_settings_page_opens_and_reads(project: Path, name: str) -> None:
    with served() as site, opened(site) as page:
        _go(page, f"/settings/{name}")
        body = page.locator(f"[data-hmz=settings-{name}]")
        expect(body).to_be_visible()
        expect(body.locator(".loading")).to_have_count(0)
        expect(body.locator(".error")).to_have_count(0)
        expect(page.locator(".settings-nav [aria-current=page]")).to_have_count(1)


def test_the_colours_are_light_dark_or_adaptive(project: Path) -> None:
    with served() as site, opened(site) as page:
        page.locator("[data-hmz=machine-menu]").click()
        choices = page.locator("[role=menu] .choice-label")
        expect(choices).to_have_text(["Adaptive", "Light", "Dark", "Settings", "Usage"])
        page.get_by_role("menuitem", name="Dark").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")


def test_a_flow_is_opened_and_started_from_the_flows(project: Path) -> None:
    with served() as site, opened(site) as page:
        page.get_by_role("link", name="Flows").click()
        page.locator(".card[data-flow=chat]").click()
        expect(page.locator(".flow-detail h2")).to_have_text("chat")
        page.get_by_role("link", name="New epic").last.click()
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("chat")


def test_on_a_phone_the_sidebar_is_a_drawer(project: Path) -> None:
    with served() as site, opened(site, width=390, height=844) as page:
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar).not_to_be_in_viewport()
        page.locator("[data-hmz=bar] .bar-side").click()
        expect(sidebar).to_be_in_viewport()
        page.get_by_role("link", name="Flows").click()
        expect(sidebar).not_to_be_in_viewport()


def test_every_label_is_a_word_or_a_phrase(project: Path) -> None:
    """A button, a tab, a menu item or a heading names a thing; it never says a sentence."""
    with served() as site, opened(site) as page:
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


def test_a_setup_is_saved_without_starting_an_epic(project: Path) -> None:
    with served() as site, opened(site) as page:
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


def test_an_epic_is_read_as_its_log_and_its_agents_as_a_list(project: Path) -> None:
    with served() as site, opened(site) as page:
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
