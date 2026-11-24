"""The pictures of `docs/user/gateways.md`: endpoints, LiteLLM and CLIs of one's own.

An account of Claude Code made in the app for an endpoint that speaks Anthropic's API, the
same form on a way that goes through the local LiteLLM gateway, the terminal interface's
form for such an account, a CLI that speaks ACP added there, and a chat with it from the
command line.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_gateways.py`.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.pick import Signing
from tests.integration.doubles_tui import on, picks, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from tests.system.docs.conftest import World

_KEY = "not-a-real-key"

_ACP = r"""
import json
import sys


def out(said):
    sys.stdout.write(json.dumps(said) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    if not line.strip():
        continue
    told = json.loads(line)
    method, at = told.get("method"), told.get("id")
    params = told.get("params") or {}
    if method == "initialize":
        out({"jsonrpc": "2.0", "id": at, "result": {
            "protocolVersion": 1, "agentCapabilities": {}, "authMethods": []}})
    elif method == "session/new":
        out({"jsonrpc": "2.0", "id": at, "result": {"sessionId": "ses-1"}})
    elif method == "session/prompt":
        out({"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": params["sessionId"],
            "update": {"sessionUpdate": "agent_message_chunk",
                       "content": {"type": "text", "text": ANSWER}}}})
        out({"jsonrpc": "2.0", "id": at, "result": {"stopReason": "end_turn"}})
    elif at is not None:
        out({"jsonrpc": "2.0", "id": at, "error": {"code": -32601, "message": "no"}})
"""

_ANSWER = "In shop/cart.py: total() sums the price of every line of the cart."


def _my_agent(world: World) -> None:
    """Adds a stand-in CLI that speaks ACP, as `my-agent --acp` typed in the form would.

    It is written down by where it is, since the staged PATH is not this scene's to add to:
    an added CLI is called what its command is called either way.
    """
    from hmz.coganchor import backends

    at = world.home / ".local" / "bin" / "my-agent"
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(f"#!{sys.executable}\nANSWER = {_ANSWER!r}\n{_ACP}")
    at.chmod(0o755)
    backends.remember("", [str(at), "--acp"])


_PAGE = "user-gateways"

#: A window tall enough that the whole form is on it with nothing scrolled.
_TALL = 1040
_URL = "https://gateway.example"
_ASK = "Where is the cart total computed?"


def _method(page: Page, cli: str, way: str, name: str) -> None:
    """Fills the top row of the New account form."""
    page.get_by_label("CLI", exact=True).select_option(cli)
    page.get_by_label("Sign-in method").select_option(way)
    page.locator("#account-name").fill(name)


def test_a_gateway_account_is_made_in_the_app(world: World) -> None:
    with world.page(desktop=True, height=_TALL) as page:
        go(page, "/settings/accounts")
        way = page.get_by_label("Sign-in method")
        expect(way).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-app", window="desktop")
        reel.web(page, hold=1.6, pointer=way, click=True)
        _method(page, "claude", "anthropic-gateway", "router")
        url = page.locator("#answer-ANTHROPIC_BASE_URL")
        expect(url).to_be_visible()
        reel.web(page, hold=1.8, pointer=url, click=True)
        url.fill(_URL)
        page.locator("#answer-ANTHROPIC_AUTH_TOKEN").fill(_KEY)
        create = page.get_by_role("button", name="Create")
        create.scroll_into_view_if_needed()
        reel.web(page, hold=1.8, pointer=create, click=True)
        create.click()
        made = page.get_by_text("made by anthropic-gateway")
        expect(made).to_be_visible()
        page.get_by_text("Secrets stay put").scroll_into_view_if_needed()
        reel.web(page, hold=3.5, poster=True)
        reel.save()


def test_a_litellm_way_is_picked_in_the_app(world: World) -> None:
    with world.page(desktop=True, height=_TALL) as page:
        go(page, "/settings/accounts")
        expect(page.get_by_label("Sign-in method")).to_be_visible()
        _method(page, "claude", "litellm-openai-key", "openai")
        key = page.locator("#answer-OPENAI_API_KEY")
        expect(key).to_be_visible()
        key.fill(_KEY)
        page.locator("#account-name").focus()
        making = page.locator("#account-name").locator("xpath=ancestor::form/..")
        shots.web(page, f"{_PAGE}-litellm", clip=making, pad=16)


async def test_a_gateway_account_is_asked_for_in_the_terminal(world: World) -> None:
    async with world.tui((100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings accounts")
        await shows(pilot, "Add a custom CLI")
        await pilot.press("enter")
        await on(pilot, Signing)
        await picks(pilot, "way", "anthropic-gateway")
        await shows(pilot, "ANTHROPIC_BASE_URL")
        await pilot.pause(0.5)
        shots.tui(app, f"{_PAGE}-terminal-form")


async def test_a_cli_that_speaks_acp_is_added_in_the_terminal(world: World) -> None:
    async with world.tui((100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings accounts")
        await shows(pilot, "Add a custom CLI")
        await pilot.pause(0.5)
        reel = shots.Reel(f"{_PAGE}-custom-cli")
        reel.tui(app, hold=1.4)
        await pilot.press("right")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.0, keys="right")
        await pilot.press("enter")
        await shows(pilot, "Add a CLI that speaks ACP")
        await pilot.pause(0.5)
        reel.tui(app, hold=2.0, keys="enter")
        await pilot.press("enter")
        await pilot.press(*"my-agent --acp")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.6, caption="the command that starts it")
        await pilot.press("enter")
        await shows(pilot, "saves it as a backend")
        reel.tui(app, hold=1.0, keys="enter")
        await pilot.press("enter")
        await shows(pilot, "added as a backend")
        await pilot.pause(0.5)
        reel.tui(app, hold=3.5, keys="enter", poster=True)
        reel.save()


def test_a_chat_with_the_added_cli(world: World) -> None:
    _my_agent(world)
    shots.cli(["hmz", "chat", "start", "-a", "my-agent/default", _ASK], f"{_PAGE}-chat")


def test_the_app_lists_them_as_harnesses(world: World) -> None:
    _my_agent(world)
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        chip = page.get_by_role("button", name="Claude Code").first
        expect(chip).to_be_visible()
        chip.click()
        page.get_by_role("menuitem", name="Harness").click()
        added = page.get_by_role("menuitem", name="my-agent")
        expect(added).to_be_visible()
        added.hover()
        shots.web(
            page, f"{_PAGE}-harness", clip=page.get_by_role("menu", name="Nous"), pad=56
        )
