"""What the sidebar sends off, said to be going until the daemon answers.

Its epics and workspaces are answered on the wire, before Local is asked, and the answers to
what is sent off are held until the test gives them: an epic opened out, `Show more`, `Upload`
on an epic and `Forget` on a workspace.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, opened

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

#: Two epics there are, of which one is listed: the first page is answered at once.
_LISTED: dict[str, Any] = {
    "runs": [_RUN],
    "total": 2,
    "offset": 0,
    "limit": 60,
    "counts": {},
    "flows": [],
}


def _listed(params: Any) -> dict[str, Any] | None:
    return {"result": _LISTED} if params.get("limit") == 60 else None


def test_what_the_sidebar_sends_off_says_it_is_going(engine: str) -> None:
    wire = Wire(
        faked={
            "runs.list": _listed,
            "runs.get": lambda _: None,
            "runs.backup": lambda _: None,
            "workspaces.list": lambda _: {
                "result": {"workspaces": [{"path": "/w"}, {"path": "/empty"}]}
            },
            "workspaces.forget": lambda _: None,
        }
    )
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        row = page.locator("[data-hmz=epics] .side-item[data-epic=e1]")
        expect(row).to_have_count(1)

        # Opened out: its agents at once, and that its sessions are being read.
        row.locator(".side-toggle").click()
        reading = row.locator("[data-hmz=reading]")
        expect(reading).to_have_text("Reading…")
        expect(row.locator("[data-hmz=agent]")).to_have_count(1)
        wire.answer(page, "runs.get", {"name": "e1", "sessions": []})
        expect(reading).to_have_count(0)

        more = page.locator(".side-more")
        more.click()
        expect(more).to_have_text("Loading…")
        expect(more).to_be_disabled()
        wire.answer(page, "runs.list", _LISTED)
        expect(more).to_have_text("Show more")
        expect(more).to_be_enabled()

        working = page.locator("[data-hmz=working]")
        row.locator("[data-hmz=epic]").click(button="right")
        page.get_by_role("menuitem", name="Upload").click()
        expect(working).to_have_text("Uploading…")
        wire.answer(page, "runs.backup", {"queued": ["s3"]})
        expect(working).to_have_count(0)
        expect(page.locator(".toast")).to_have_text("Uploading to s3")

        page.locator("[data-hmz=workspace][data-path='/empty'] .side-folder").click(
            button="right"
        )
        page.get_by_role("menuitem", name="Forget").click()
        expect(working).to_have_text("Forgetting…")
        wire.answer(page, "workspaces.forget", {})
        expect(working).to_have_count(0)
        expect(page.locator(".toast")).to_have_text("Forgotten")
