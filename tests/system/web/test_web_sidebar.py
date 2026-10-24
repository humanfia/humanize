"""What the sidebar sends off, said to be going until the daemon answers.

Its epics and workspaces are answered in the page itself, before the page asks, and the answers
to what is sent off are held until the test lets them through: an epic opened out, `Show more`,
`Upload` on an epic and `Forget` on a workspace.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, opened

pytestmark = pytest.mark.parametrize("engine", ENGINES)

_RUN = {
    "name": "e1",
    "workspace": "/w",
    "task": "Fix e1",
    "flow": "ralph",
    "how": "done",
    "held": False,
    "began": "2026-10-12T09:00:00Z",
    "agents": [{"name": "coder", "role": "coder", "runs": "claude/sonnet"}],
}

_ANSWERING = f"""
    window.hmzHeld = {{}}
    window.hmzAnswer = (path) => window.hmzHeld[path]()
    const fetched = window.fetch.bind(window)
    const json = (said) => new Response(JSON.stringify(said), {{
      status: 200, headers: {{ 'Content-Type': 'application/json' }},
    }})
    const held = (path, said) => new Promise((answer) => {{
      window.hmzHeld[path] = () => answer(json(said))
    }})
    window.fetch = (url, how) => {{
      const at = new URL(String(url), location.href)
      // Each daemon's own under `/d/<name>`, as the page scopes them.
      const path = at.pathname.replace(/^\\/d\\/[^/]+/, '')
      if (path === '/api/runs') {{
        const listed = {{ runs: [{json.dumps(_RUN)}], total: 2 }}
        if (at.searchParams.get('limit') === '60') return Promise.resolve(json(listed))
        return held('more', listed)
      }}
      if (path === '/api/runs/e1') return held('e1', {{ name: 'e1', sessions: [] }})
      if (path === '/api/runs/e1/backup') return held('backup', {{ queued: ['s3'] }})
      const places = {{ workspaces: [{{ path: '/w' }}, {{ path: '/empty' }}] }}
      if (path === '/api/workspaces') return Promise.resolve(json(places))
      if (path === '/api/workspaces/forget') return held('forget', {{}})
      return fetched(url, how)
    }}
"""


def test_what_the_sidebar_sends_off_says_it_is_going(engine: str) -> None:
    with served() as site, opened(site, engine=engine, init=_ANSWERING) as page:
        row = page.locator("[data-hmz=epics] .side-item[data-epic=e1]")
        expect(row).to_have_count(1)

        # Opened out: its agents at once, and that its sessions are being read.
        row.locator(".side-toggle").click()
        reading = row.locator("[data-hmz=reading]")
        expect(reading).to_have_text("Reading…")
        expect(row.locator("[data-hmz=agent]")).to_have_count(1)
        page.evaluate("window.hmzAnswer('e1')")
        expect(reading).to_have_count(0)

        more = page.locator(".side-more")
        more.click()
        expect(more).to_have_text("Loading…")
        expect(more).to_be_disabled()
        page.evaluate("window.hmzAnswer('more')")
        expect(more).to_have_text("Show more")
        expect(more).to_be_enabled()

        working = page.locator("[data-hmz=working]")
        row.locator("[data-hmz=epic]").click(button="right")
        page.get_by_role("menuitem", name="Upload").click()
        expect(working).to_have_text("Uploading…")
        page.evaluate("window.hmzAnswer('backup')")
        expect(working).to_have_count(0)
        expect(page.locator(".toast")).to_have_text("Uploading to s3")

        page.locator("[data-hmz=workspace][data-path='/empty'] .side-folder").click(
            button="right"
        )
        page.get_by_role("menuitem", name="Forget").click()
        expect(working).to_have_text("Forgetting…")
        page.evaluate("window.hmzAnswer('forget')")
        expect(working).to_have_count(0)
        expect(page.locator(".toast")).to_have_text("Forgotten")
