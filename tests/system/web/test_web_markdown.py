"""A thread's Markdown drawn in a real browser, and copied as it was written.

The line is a transcript's, built by `line()` as the page builds one, over the page's own
Markdown bundle. What it draws is read off the page, and what Copy and Copy thread give is read
back from the clipboard the page writes to. Each in Chromium and WebKit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, opened

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: What a line said: raw HTML, a break, a table, a file path and a link that is not one.
TEXT = """List<int> and <placeholder> stay text.

line one
line two

| step | what |
| --- | --: |
| 1 | first |

A [file](file:///tmp/agent.log) and [bad](javascript:window.ran = 1)."""

#: Puts one line of a thread on the page, with Copy writing where the test can read it.
_DRAW = """async (text) => {
    const { line } = await import('/transcript.js')
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: async (said) => { window.copied = said } },
    })
    const thread = document.createElement('div')
    thread.className = 'thread'
    thread.id = 'md-thread'
    const one = line('text', text, { who: 'agent' })
    one.id = 'md-line'
    thread.append(one)
    document.body.append(thread)
}"""

#: What the line drew.
_READ = """() => {
    const md = document.querySelector('#md-line .ask-markdown')
    return {
        text: md.textContent,
        html: md.innerHTML,
        intTag: md.querySelector('int') !== null,
        file: md.querySelector('code[title^="file:"]')?.textContent ?? null,
        breaks: md.querySelectorAll('br').length,
        javascript: md.querySelectorAll('a[href^="javascript"]').length,
        table: md.querySelector('table') !== null,
        right: md.querySelector('td[align="right"]')?.textContent ?? null,
        ran: window.ran ?? null,
    }
}"""


def _copies(page: Page, name: str) -> str:
    """Right-clicks the line, picks one of its copies, and answers what it gave."""
    page.evaluate(
        """(name) => {
            window.copied = undefined
            const body = document.querySelector('#md-line .body')
            body.dispatchEvent(
                new MouseEvent('contextmenu', { bubbles: true, clientX: 20, clientY: 20 }),
            )
            const item = [...document.querySelectorAll('.popover.context [role=menuitem]')]
                .find((one) => one.textContent.trim() === name)
            if (!item) throw new Error(`no menu item ${name}`)
            item.click()
        }""",
        name,
    )
    page.wait_for_function("() => window.copied !== undefined", timeout=5000)
    return page.evaluate("() => window.copied")


def test_a_line_draws_markdown_and_copies_what_was_written(engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        page.evaluate(_DRAW, TEXT)
        page.wait_for_selector("#md-line .ask-markdown table", timeout=5000)
        drawn: dict[str, Any] = page.evaluate(_READ)

        assert drawn["intTag"] is False
        assert "List<int> and <placeholder> stay text." in drawn["text"]
        assert drawn["breaks"] == 1
        assert drawn["table"] is True
        assert drawn["right"] == "first"
        assert drawn["file"] == "file:///tmp/agent.log"
        assert drawn["javascript"] == 0
        assert drawn["ran"] is None

        copied = _copies(page, "Copy")
        assert copied == TEXT
        thread = _copies(page, "Copy thread")
        assert thread == TEXT
