"""`hmz web`'s Exomyth, driven in a browser: an epic's timeline drawn, moved over, read and timed.

Each test runs chat on the stand-in `claude` from the API, as a page would start it, and opens
the epic's Exomyth in Chromium and in WebKit, which the macOS app's window is. The canvas is
reached through what the view hands `window.__exomyth`: the model drawn, the time shown, where a
span is on the screen, and a frame drawn on demand.
"""

from __future__ import annotations

import datetime
import json
import re
import statistics
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_web import Browser, served, until
from tests.system.web.doubles_browser import ENGINES, go, opened

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from playwright.sync_api import Page

    from hmz.web.site import Site

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: How many tool calls the long epic's session is given: two spans each, a think and a call.
_CALLS = 25_000

#: The longest a frame of the long epic may take to draw, in milliseconds: a generous bound,
#: for a machine running a whole suite, on what is meant to take well under 8.
_FRAME = 50.0

#: The longest the long epic's spans may take to be summed for the Flame, in milliseconds: as
#: generous, on what is meant to take under 100.
_SUM = 500.0


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    return install(tmp_path, monkeypatch)


def _record(of: str) -> Callable[[str, Any], bool]:
    """Whether an event of the stream is a record of that type."""
    return lambda event, data: event == "record" and data.get("type") == of


def _chatted(site: Site, task: str, *, stopped: bool = True) -> str:
    """Runs chat on a task until it asks back, then stops it; answers with the epic's name."""
    browser = Browser(site)
    browser.signs_in()
    with browser.follows() as heard:
        until(heard, lambda event, data: event == "hello", "hello")
        chat = {"flow": "chat", "task": task, "agents": {"assistant": AGENT}}
        assert browser.post("/api/held/start", chat).status == 200
        until(heard, _record("asked"), "chat asking")
        if stopped:
            browser.post("/api/held/stop")
            until(heard, _record("ended"), "the run ending")
    (ran,) = browser.get("/api/runs").json()["runs"]
    return str(ran["name"])


def _lengthened(site: Site, tmp_path: Path, name: str, calls: int) -> None:
    """Writes `calls` more tool calls into the log of the epic's session, a few ms apart."""
    browser = Browser(site)
    browser.signs_in()
    (session,) = browser.get(f"/api/runs/{name}").json()["sessions"]
    logs = list(tmp_path.rglob(f"{session['ident']}.jsonl"))
    assert logs
    at = datetime.datetime.now(datetime.UTC)
    lines: list[str] = []
    for n in range(calls):
        asked = at + datetime.timedelta(milliseconds=3 * n)
        answered = asked + datetime.timedelta(milliseconds=2)
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": asked.isoformat(),
                    "requestId": str(uuid.uuid4()),
                    "message": {
                        "model": "claude-haiku-4-5",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": f"call{n}",
                                "name": "Bash",
                                "input": {"command": f"echo {n}"},
                            }
                        ],
                        "usage": {"input_tokens": 3, "output_tokens": 2},
                    },
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": answered.isoformat(),
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": f"call{n}",
                                "content": "ok",
                            }
                        ],
                    },
                }
            )
        )
    for log in logs:
        with log.open("a") as kept:
            kept.write("\n".join(lines) + "\n")


def _exomyth(page: Page, name: str) -> None:
    """Opens an epic's Exomyth and waits for its timeline to be drawn."""
    go(page, f"/epics/{name}/exomyth")
    page.wait_for_function("() => window.__exomyth && window.__exomyth.model()")


def _span(page: Page, category: str) -> int:
    """The id of the first span of a category."""
    return int(
        page.evaluate(
            """(cat) => {
              const model = window.__exomyth.model()
              for (const track of model.tracks)
                for (let i = 0; i < track.count; i++)
                  if (model.strings[track.cat[i]] === cat) return track.first + i
              return -1
            }""",
            category,
        )
    )


def test_an_epic_is_drawn_as_its_processes_moved_over_and_read(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        name = _chatted(site, "draw me")
        go(page, f"/epics/{name}")
        page.locator("[data-hmz=exomyth-open]").click()
        page.wait_for_function("() => window.__exomyth && window.__exomyth.model()")
        assert page.url.endswith(f"#/epics/{name}/exomyth")

        listed = page.locator("[data-hmz=exomyth-processes]")
        expect(listed.locator("button")).to_have_count(2)
        expect(listed).to_contain_text("chat")
        expect(listed).to_contain_text("main")
        assert page.evaluate("window.__exomyth.rows()") >= 4

        # W zooms in where the pointer is, D pans on, 0 shows it all again.
        box = page.locator("[data-hmz=exomyth-canvas]").bounding_box()
        assert box
        page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + 60)
        whole = page.evaluate("window.__exomyth.view()")
        # Held until it has moved, as far as it gets in a frame or a hundred.
        page.keyboard.down("w")
        page.wait_for_function(
            "(half) => { const v = window.__exomyth.view(); return v.t1 - v.t0 < half }",
            arg=(whole["t1"] - whole["t0"]) / 2,
        )
        page.keyboard.up("w")
        zoomed = page.evaluate("window.__exomyth.view()")
        page.keyboard.down("d")
        page.wait_for_function(
            "(from) => window.__exomyth.view().t0 > from", arg=zoomed["t0"]
        )
        page.keyboard.up("d")
        page.keyboard.press("0")
        assert page.evaluate("window.__exomyth.view()") == whole

        # A span clicked says what it is, and what it carried once read.
        turn = _span(page, "turn")
        at = page.evaluate("(id) => window.__exomyth.where(id)", turn)
        page.mouse.click(at["x"], at["y"])
        details = page.locator("[data-hmz=exomyth-details]")
        expect(details.locator("[data-hmz=exomyth-span-name]")).to_have_text(
            "turn: draw me"
        )
        expect(details.locator("[data-hmz=exomyth-args]")).to_contain_text(
            '"prompt": "draw me"'
        )

        # A stretch dragged out is summed.
        page.keyboard.press("Escape")
        page.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + 10)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] - 2, box["y"] + 10, steps=5)
        page.mouse.up()
        expect(details.locator("[data-hmz=exomyth-range]")).to_be_visible()
        expect(details.locator("[data-hmz=exomyth-categories]")).to_contain_text(
            "session"
        )

        # Found by its words, and stepped to.
        page.keyboard.press("/")
        page.keyboard.type("draw me")
        found = page.locator("[data-hmz=exomyth-found]")
        expect(found).to_have_text(re.compile(r"^[1-9]"))
        page.keyboard.press("Enter")
        expect(found).to_have_text(re.compile(r"^1/"))
        expect(details.locator("[data-hmz=exomyth-span-name]")).to_contain_text(
            "draw me"
        )

        page.get_by_role("tab", name="Flame").click()
        expect(page.locator("[data-hmz=exomyth-flame]")).to_be_visible()
        expect(page.locator("[data-hmz=exomyth-timeline]")).to_be_hidden()
        assert page.url.endswith("/exomyth?tab=flame")
        page.get_by_role("tab", name="Timeline").click()
        expect(page.locator("[data-hmz=exomyth-timeline]")).to_be_visible()


def test_an_epic_going_is_read_again_until_it_ends(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _exomyth(page, _chatted(site, "follow me", stopped=False))
        assert page.evaluate("window.__exomyth.model().live") is True
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("running")
        )

        browser = Browser(site)
        browser.signs_in()
        assert browser.post("/api/held/stop").status == 200
        page.wait_for_function("() => window.__exomyth.model().live === false")
        expect(page.locator("[data-hmz=bar] .badge")).not_to_have_text(
            re.compile("running")
        )


def test_the_canvas_is_drawn_in_the_theme_shown(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _exomyth(page, _chatted(site, "colour me"))
        # The gutter's foot, which nothing is drawn over, is the panel colour of the theme.
        for theme in ("light", "dark"):
            drawn, wanted = page.evaluate(
                """async (theme) => {
                  document.documentElement.dataset.theme = theme
                  const framed = () => new Promise((done) => requestAnimationFrame(done))
                  await framed()
                  await framed()
                  const canvas = document.querySelector('[data-hmz=exomyth-canvas]')
                  const at = 4 * (canvas.width / canvas.clientWidth)
                  const pixel = canvas.getContext('2d').getImageData(at, canvas.height - at, 1, 1)
                  const [r, g, b] = pixel.data
                  const probe = document.createElement('i')
                  probe.style.color = 'var(--surface)'
                  document.body.append(probe)
                  const said = getComputedStyle(probe).color
                  probe.remove()
                  return [[r, g, b], said.match(/\\d+/g).slice(0, 3).map(Number)]
                }""",
                theme,
            )
            assert drawn == wanted, theme


def test_fifty_thousand_spans_are_drawn_within_a_frame(
    tmp_path: Path, project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        name = _chatted(site, "lengthen me")
        _lengthened(site, tmp_path, name, _CALLS)
        _exomyth(page, name)
        spans = page.evaluate("window.__exomyth.model().summary.spans")
        assert spans >= 2 * _CALLS

        box = page.locator("[data-hmz=exomyth-canvas]").bounding_box()
        assert box
        page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + 80)
        took: list[float] = []
        for _ in range(3):
            took += page.evaluate(
                "() => Array.from({length: 10}, () => window.__exomyth.render())"
            )
            page.keyboard.down("w")
            page.wait_for_timeout(250)
            page.keyboard.up("w")
        assert statistics.median(took) < _FRAME, took


def _flame(page: Page, name: str) -> None:
    """Opens an epic's Exomyth on its Flame and waits for frames to be drawn."""
    go(page, f"/epics/{name}/exomyth?tab=flame")
    page.wait_for_function(
        "() => window.__exomyth && window.__exomyth.flame()"
        " && window.__exomyth.flame().render() >= 0 && window.__exomyth.flame().drawn() > 0"
    )


def test_an_epic_is_drawn_as_a_flame_weighed_and_zoomed(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        name = _chatted(site, "flame me")
        _flame(page, name)
        flame = "window.__exomyth.flame()"
        assert page.evaluate(f"{flame}.zoomed()") == name
        whole = page.evaluate(f"{flame}.total()")
        assert whole > 0

        # Counted, the whole is every span; merged or not, the same.
        page.locator("[data-hmz=exomyth-weight] button", has_text="Count").click()
        spans = page.evaluate("window.__exomyth.model().summary.spans")
        assert page.evaluate(f"{flame}.total()") == spans
        page.locator("[data-hmz=exomyth-merge]").click()
        expect(page.locator("[data-hmz=exomyth-merge]")).to_have_attribute(
            "aria-pressed", "false"
        )
        assert page.evaluate(f"{flame}.total()") == spans

        # A frame clicked is zoomed to; the crumbs zoom back out.
        at = page.evaluate(f"{flame}.where('turn: flame me')")
        page.mouse.click(at["x"], at["y"])
        assert page.evaluate(f"{flame}.zoomed()") == "turn: flame me"
        crumbs = page.locator("[data-hmz=exomyth-crumbs]")
        expect(crumbs).to_contain_text("turn: flame me")
        crumbs.get_by_role("button", name=name).click()
        assert page.evaluate(f"{flame}.zoomed()") == name

        page.locator("[data-hmz=exomyth-weight] button", has_text="Time").click()
        assert page.evaluate(f"{flame}.total()") == whole

        # Words found light their frames, said as a share of the whole.
        page.keyboard.press("/")
        page.keyboard.type("flame me")
        expect(page.locator("[data-hmz=exomyth-found]")).to_have_text(
            re.compile(r"^\d+\.\d%$")
        )
        page.keyboard.press("Escape")

        # A stretch picked on the Timeline is what the Flame sums.
        page.get_by_role("tab", name="Timeline").click()
        page.wait_for_function(
            "() => document.querySelector('[data-hmz=exomyth-canvas]').clientWidth > 0"
        )
        box = page.locator("[data-hmz=exomyth-canvas]").bounding_box()
        assert box
        page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + 10)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] - 2, box["y"] + 10, steps=5)
        page.mouse.up()
        page.get_by_role("tab", name="Flame").click()
        page.wait_for_function(
            "(whole) => { const f = window.__exomyth.flame(); return f && f.total() < whole }",
            arg=whole,
        )
        expect(page.locator("[data-hmz=exomyth-flame-range]")).not_to_have_text(
            "Whole epic"
        )


def test_the_slices_are_sorted_and_shown_on_the_timeline(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _flame(page, _chatted(site, "list me"))
        table = page.locator("[data-hmz=exomyth-stats]")
        table.locator("[data-sort=count]").click()
        expect(table.locator("th[aria-sort=descending]")).to_contain_text("Count")
        counts = [
            int(said.replace(",", ""))
            for said in table.locator("tbody tr td:nth-child(3)").all_inner_texts()
        ]
        assert counts == sorted(counts, reverse=True)
        table.locator("[data-sort=count]").click()
        expect(table.locator("th[aria-sort=ascending]")).to_contain_text("Count")

        table.locator("tbody tr", has_text="turn: list me").click()
        flame = "window.__exomyth.flame()"
        assert page.evaluate(f"{flame}.share()") > 0
        table.locator("[data-hmz=exomyth-show]").click()
        expect(page.locator("[data-hmz=exomyth-timeline]")).to_be_visible()
        expect(page.locator("[data-hmz=exomyth-find]")).to_have_value("turn: list me")
        expect(page.locator("[data-hmz=exomyth-found]")).to_have_text(
            re.compile(r"^[1-9]")
        )
        assert not page.url.endswith("?tab=flame")


def test_fifty_thousand_spans_are_summed_and_drawn_as_a_flame_in_time(
    tmp_path: Path, project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        name = _chatted(site, "flame me long")
        _lengthened(site, tmp_path, name, _CALLS)
        _flame(page, name)
        assert page.evaluate("window.__exomyth.model().summary.spans") >= 2 * _CALLS
        summed = page.evaluate(
            "() => Array.from({length: 5}, () => window.__exomyth.flame().aggregate())"
        )
        drawn = page.evaluate(
            "() => Array.from({length: 10}, () => window.__exomyth.flame().render())"
        )
        assert statistics.median(summed) < _SUM, summed
        assert statistics.median(drawn) < _FRAME, drawn


#: What overlaps in the panel, as a list of what with what: each piece of its text against the
#: panel's close button, the panel's edges and every other piece of text, and the chart's
#: tooltip against the panel.
_OVERLAPS = """() => {
  const panel = document.querySelector('[data-hmz=inspector]')
  const edge = panel.getBoundingClientRect()
  const shut = panel.querySelector('.panel-close').getBoundingClientRect()
  const pieces = []
  const walker = document.createTreeWalker(panel.querySelector('.panel-body'), NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.data.trim()) continue
    const range = document.createRange()
    range.selectNodeContents(node)
    for (const box of range.getClientRects())
      if (box.width > 0 && box.height > 0) pieces.push({ text: node.data.trim().slice(0, 24), box })
  }
  const meet = (a, b) =>
    Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5 &&
    Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5
  const found = []
  const tip = document.querySelector('.exo-tip:not([hidden])')
  if (tip && meet(tip.getBoundingClientRect(), edge)) found.push('the tooltip / the panel')
  for (const [i, one] of pieces.entries()) {
    if (meet(one.box, shut)) found.push(`${one.text} / the close button`)
    if (one.box.left < edge.left || one.box.right > edge.right - 1)
      found.push(`${one.text} / the edge`)
    for (const other of pieces.slice(i + 1))
      if (meet(one.box, other.box)) found.push(`${one.text} / ${other.text}`)
  }
  return found
}"""


@pytest.mark.parametrize("width", [1280, 1000])
def test_the_panel_says_a_span_a_process_and_a_range_without_overlapping(
    project: Path, engine: str, width: int
) -> None:
    # At 1280 the panel is 360 pixels wide, and at 1000 it is 320.
    with served() as site, opened(site, engine=engine, width=width) as page:
        _exomyth(
            page, _chatted(site, "a span whose name runs on and on past the panel")
        )
        details = page.locator("[data-hmz=exomyth-details]")
        expect(details).to_contain_text("Processes")
        assert page.evaluate(_OVERLAPS) == []

        turn = _span(page, "turn")
        at = page.evaluate("(id) => window.__exomyth.where(id)", turn)
        page.mouse.click(at["x"], at["y"])
        expect(details.locator("[data-hmz=exomyth-args]")).to_be_visible()
        assert page.evaluate(_OVERLAPS) == []

        details.locator(".exo-link").first.click()
        expect(details).to_contain_text("Process")
        assert page.evaluate(_OVERLAPS) == []

        page.keyboard.press("Escape")
        box = page.locator("[data-hmz=exomyth-canvas]").bounding_box()
        assert box
        page.mouse.move(box["x"] + box["width"] * 0.1, box["y"] + 10)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] - 2, box["y"] + 10, steps=5)
        page.mouse.up()
        expect(details.locator("[data-hmz=exomyth-range]")).to_be_visible()
        assert page.evaluate(_OVERLAPS) == []
