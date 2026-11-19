"""A question's face: a flow's own HTML app, run in a sandboxed frame beside the question.

The page mounts each face itself (`faces/host.js` `mountFace`), as the question card does, over
the real server -- whose headers the frame is held to -- and asks its daemon on the wire for
what the card would: `epic.face` for the HTML, `epic.answer` for the value, both faked here.
Each in Chromium and in WebKit, which the macOS app's window is. Pictures of a mounted face, in
light and dark and at a phone's width and a desktop's, are kept under `$HMZ_FACE_SHOTS` where
that is set.
"""

from __future__ import annotations

import ast
import contextlib
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, opened

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Frame, Page

    from hmz.web.site import Site

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: A face for a code review: a verdict of two, notes, and what it is shown as it goes.
_REVIEW = """<!doctype html>
<html lang="en">
<head>
<title>Review</title>
<style>
  .shown { margin: 8px 0 0; padding-left: 18px; color: var(--ink-2); }
  .head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
</style>
</head>
<body>
<script>
  // What the page's colours were before anything of the face but this had run.
  window.early = getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()
</script>
<div class="card stack">
  <div class="head"><h2 id="prompt">…</h2><span class="muted" id="count"></span></div>
  <div class="row">
    <span class="choices" role="group" aria-label="Verdict">
      <button type="button" data-verdict="approve" aria-pressed="true">Approve</button>
      <button type="button" data-verdict="changes" aria-pressed="false">Request changes</button>
    </span>
  </div>
  <div>
    <label for="notes">Notes</label>
    <textarea id="notes" aria-describedby="error" placeholder="What should change?"></textarea>
    <p class="error" id="error" role="alert" hidden></p>
  </div>
  <div class="row">
    <button class="primary" id="send" type="button">Send review</button>
    <span class="muted" id="status"></span>
  </div>
  <ul class="shown" id="shown"></ul>
</div>
<script>
  const $ = (id) => document.getElementById(id)
  let verdict = 'approve'
  window.asks = []
  window.results = []
  for (const button of document.querySelectorAll('[data-verdict]'))
    button.addEventListener('click', () => {
      verdict = button.dataset.verdict
      for (const other of document.querySelectorAll('[data-verdict]'))
        other.setAttribute('aria-pressed', String(other === button))
    })
  hmz.on('ask', (ask) => {
    window.asks.push(ask)
    $('prompt').textContent = ask.prompt
    $('count').textContent = `ask ${window.asks.length}`
    $('status').textContent = ''
  })
  hmz.on('show', (context) => {
    for (const block of context) {
      const item = document.createElement('li')
      item.textContent = block.text
      $('shown').append(item)
    }
  })
  hmz.on('theme', (tokens) => (window.theme = tokens))
  $('send').addEventListener('click', async () => {
    const result = await hmz.submit({ verdict, notes: $('notes').value })
    window.results.push(result)
    $('error').hidden = result.ok
    $('notes').setAttribute('aria-invalid', String(!result.ok))
    if (!result.ok) $('error').textContent = result.errors.map((one) => one.message).join(' ')
    else $('status').textContent = 'Sent ✓'
  })
</script>
</body>
</html>
"""

#: A face that tries every way out of its frame, and says how each went.
_PROBE = """<!doctype html>
<body>
<img id="picture" alt="">
<script>
  window.probes = {}
  const tried = (name, act) => {
    try {
      act()
      probes[name] = 'reached'
    } catch {
      probes[name] = 'blocked'
    }
  }
  fetch(new URL('/here', document.baseURI)).then(
    () => (probes.fetch = 'reached'),
    () => (probes.fetch = 'blocked'),
  )
  tried('parent', () => parent.document.title)
  tried('top', () => top.location.href)
  tried('cookie', () => document.cookie)
  tried('storage', () => localStorage.length)
  tried('socket', () => new WebSocket('ws://' + new URL(document.baseURI).host + '/rpc'))
  // The page's window is posted to as if this were the page's port: it is not listened to.
  parent.postMessage({ type: 'submit', id: 1, value: { forged: true } }, '*')
  const picture = document.getElementById('picture')
  picture.onload = () => (probes.picture = 'reached')
  picture.onerror = () => (probes.picture = 'blocked')
  picture.src = new URL('/mark.svg', document.baseURI).href
  hmz.on('ask', () => {})
</script>
</body>
"""

#: A face that throws before it listens.
_BROKEN = "<!doctype html><script>throw new Error('the face broke')</script>"

#: A face that never listens for an ask.
_DEAF = "<!doctype html><p>Nothing here listens.</p>"

#: Each face by the hash a question names it by.
_FACES = {"review": _REVIEW, "probe": _PROBE, "broken": _BROKEN, "deaf": _DEAF}

#: The refusal of a first answer, as `epic.answer` refuses a misfit.
_MISFIT = {
    "error": {
        "code": 400,
        "message": "the answer does not fit: notes: say what should change",
        "data": {"errors": [{"path": ["notes"], "message": "Say what should change."}]},
    }
}

#: What mounts a face as the question card would: in a box of its own on the page.
_MOUNT = """async (question) => {
  const { mountFace } = await import('/faces/host.js')
  const api = await import('/api.js')
  window.plains ||= []
  let box = document.querySelector('[data-hmz=face-box]')
  if (!box) {
    box = document.createElement('div')
    box.dataset.hmz = 'face-box'
    Object.assign(box.style, {
      position: 'fixed', inset: '0', zIndex: '100', overflow: 'auto', padding: '16px',
      background: 'var(--paper)', maxWidth: '100%',
    })
    document.body.append(box)
  }
  const el = mountFace(question, {
    fetchFace: (hash) => api.call('epic.face', { sub: 's-face', hash }),
    submit: (value) => api.call('epic.answer', { sub: 's-face', question: question.key, value }),
    plain: (on, reason) => window.plains.push([on, reason]),
  })
  if (el.parentElement !== box) box.replaceChildren(el)
}"""

#: What is drawn with a shadow: nothing floats by one, a hairline edge parts it from the page.
_SHADOWED = """() => [...document.querySelectorAll('*')]
  .filter((one) => getComputedStyle(one).boxShadow !== 'none')
  .map((one) => `${one.tagName.toLowerCase()}.${one.className}`)"""


#: What a browser says as it refuses a face a way out: its frame's policy holding.
_HELD = re.compile(r"Content Security Policy|connect-src|img-src")


@contextlib.contextmanager
def _faced(
    site: Site, engine: str, wire: Wire, *said: re.Pattern[str]
) -> Generator[Page]:
    """The page, as `opened` gives it, which may say only what `said` matches beside its own.

    A face failing, or refused a way out, says so in the console as the page's own errors do;
    what each test expects of its face is let be, and anything else still fails it.
    """
    try:
        with opened(site, engine=engine, routed=wire.routes) as page:
            yield page
    except AssertionError as why:
        prefix = "the page went wrong: "
        if not str(why).startswith(prefix):
            raise
        errors: list[str] = ast.literal_eval(str(why).removeprefix(prefix))
        if not all(any(one.search(error) for one in said) for error in errors):
            raise


def _question(key: str, face: str, **more: Any) -> dict[str, Any]:
    return {
        "key": key,
        "role": "reviewer",
        "text": f"Review change {key}",
        "options": [],
        "schema": {
            "type": "object",
            "properties": {
                "verdict": {"enum": ["approve", "changes"]},
                "notes": {"type": "string"},
            },
            "required": ["verdict"],
        },
        "context": [{"kind": "markdown", "text": "Adds a cache."}],
        "face": {"hash": face, "title": "Review"},
        "session": "reviewer/1",
        **more,
    }


def _wire() -> Wire:
    answers: list[dict[str, Any]] = [_MISFIT]

    def answered(_: Any) -> dict[str, Any]:
        return answers.pop() if answers else {"result": {}}

    def face(params: dict[str, Any]) -> dict[str, Any]:
        html = _FACES.get(params["hash"])
        if html is None:
            return {"error": {"code": 404, "message": f"no face {params['hash']}"}}
        return {"result": {"html": html, "title": "Review"}}

    return Wire(faked={"epic.face": face, "epic.answer": answered})


def _frame(page: Page) -> Frame:
    handle = page.locator("[data-hmz=face-frame]").element_handle()
    assert handle is not None
    frame = handle.content_frame()
    assert frame is not None
    return frame


def _until(frame: Frame | Page, check: str) -> Any:
    """What `check` says of the frame, once it says anything."""
    for _ in range(300):
        said = frame.evaluate(f"() => {check}")
        if said:
            return said
        frame.wait_for_timeout(50)
    raise AssertionError(check)


def test_a_face_answers_its_ask_and_is_told_what_does_not_fit(engine: str) -> None:
    wire = _wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        page.evaluate(_MOUNT, _question("q1", "review"))
        face = page.locator("[data-hmz=face]")
        expect(face).to_have_attribute("data-state", "ready")
        expect(face.locator("[data-hmz=face-title]")).to_have_text("Review")
        inside = page.frame_locator("[data-hmz=face-frame]")
        expect(inside.locator("#prompt")).to_have_text("Review change q1")
        frame = _frame(page)

        # The page's colours were on :root before the face ran, and told it again as tokens.
        paper = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()"
        )
        assert frame.evaluate("window.early") == paper
        ask = frame.evaluate("window.asks[0]")
        assert ask["schema"]["required"] == ["verdict"]
        assert ask["context"] == [{"kind": "markdown", "text": "Adds a cache."}]
        assert ask["errors"] == []

        # It fits itself to what it draws, once it has said how tall that is.
        def tall() -> float:
            box = page.locator("[data-hmz=face-frame]").bounding_box()
            return box["height"] if box else 0.0

        for _ in range(50):
            if tall() > 200:
                break
            page.wait_for_timeout(100)
        assert tall() > 200

        # A misfit comes back with where and why, and the face says it beside the field.
        inside.locator("[data-verdict=changes]").click()
        inside.locator("#send").click()
        expect(inside.locator("#error")).to_have_text("Say what should change.")
        assert frame.evaluate("window.results[0]") == {
            "ok": False,
            "errors": [{"path": ["notes"], "message": "Say what should change."}],
        }
        inside.locator("#notes").fill("Bound the cache.")
        inside.locator("#send").click()
        expect(inside.locator("#status")).to_have_text("Sent ✓")
        assert frame.evaluate("window.results[1]") == {"ok": True}
        assert [one["value"] for one in wire.params("epic.answer")] == [
            {"verdict": "changes", "notes": ""},
            {"verdict": "changes", "notes": "Bound the cache."},
        ]
        assert wire.params("epic.answer")[0]["question"] == "q1"

        # The session's next ask reaches the same face, its state as the person left it,
        # and its HTML is not fetched again.
        page.evaluate(_MOUNT, _question("q2", "review"))
        expect(inside.locator("#prompt")).to_have_text("Review change q2")
        expect(inside.locator("#count")).to_have_text("ask 2")
        expect(inside.locator("#notes")).to_have_value("Bound the cache.")
        assert len(wire.params("epic.face")) == 1
        inside.locator("#send").click()
        expect(inside.locator("#status")).to_have_text("Sent ✓")
        assert wire.params("epic.answer")[-1]["question"] == "q2"

        # Context pushed with nothing to answer.
        page.evaluate(
            """async () => {
              const { showFace } = await import('/faces/host.js')
              showFace('reviewer/1', [{ kind: 'markdown', text: 'Tests pass.' }])
            }"""
        )
        expect(inside.locator("#shown li")).to_have_text(["Tests pass."])

        # The page going dark is told the face, which repaints.
        page.evaluate("window.hmzPaint({ id: 'dark', base: 'dark', colors: {} })")
        _until(frame, "window.theme && window.theme['--scheme'] === 'dark'")
        dark = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()"
        )
        assert dark != paper
        assert (
            frame.evaluate(
                "getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()"
            )
            == dark
        )


def test_a_face_reaches_nothing_but_its_bridge(engine: str) -> None:
    wire = _wire()
    with served() as site, _faced(site, engine, wire, _HELD) as page:
        page.evaluate(_MOUNT, _question("q1", "probe"))
        expect(page.locator("[data-hmz=face]")).to_have_attribute("data-state", "ready")
        frame = _frame(page)
        probes = _until(
            frame,
            "window.probes && 'fetch' in probes && 'picture' in probes && window.probes",
        )
        assert probes == {
            "fetch": "blocked",
            "parent": "blocked",
            "top": "blocked",
            "cookie": "blocked",
            "storage": "blocked",
            "socket": probes["socket"],
            "picture": "blocked",
        }
        page.wait_for_timeout(300)
        # Nothing it posted to the page's window was taken for an answer.
        assert wire.params("epic.answer") == []


def test_a_face_that_cannot_open_gives_way_to_the_plain_form(engine: str) -> None:
    wire = _wire()
    broke = re.compile(r"the face broke")
    with served() as site, _faced(site, engine, wire, broke) as page:
        face = page.locator("[data-hmz=face]")

        # One that throws before it listens.
        page.evaluate(_MOUNT, _question("q1", "broken", session="broken/1"))
        expect(face).to_have_attribute("data-state", "failed")
        expect(face).to_have_attribute("data-plain", "true")
        expect(face.locator("[data-hmz=face-note]")).to_contain_text(
            "The plain form is below."
        )
        expect(face.locator("[data-hmz=face-retry]")).to_be_visible()
        assert page.evaluate("window.plains") == [[True, "failed"]]

        # One that is not there.
        page.evaluate(_MOUNT, _question("q2", "missing", session="missing/1"))
        expect(face).to_have_attribute("data-state", "failed")
        expect(face.locator("[data-hmz=face-note]")).to_contain_text("no face missing")

        # One that never listens, given up on after five seconds.
        page.evaluate(_MOUNT, _question("q3", "deaf", session="deaf/1"))
        expect(face).to_have_attribute("data-state", "loading")
        expect(face.locator("[data-hmz=face-skeleton]")).to_be_visible()
        expect(face).to_have_attribute("data-state", "failed", timeout=8000)
        expect(face.locator("[data-hmz=face-note]")).to_contain_text("too long")
        assert page.evaluate("window.plains.at(-1)") == [True, "timeout"]


def test_the_plain_form_is_a_click_away_and_the_face_waits_behind_it(
    engine: str,
) -> None:
    wire = _wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        # A menu of the page's, open as the face arrives.
        bell = page.locator("[data-hmz=notifications]")
        bell.click()
        expect(bell).to_have_attribute("aria-expanded", "true")
        page.evaluate(_MOUNT, _question("q1", "review"))
        face = page.locator("[data-hmz=face]")
        expect(face).to_have_attribute("data-state", "ready")
        expect(bell).to_have_attribute("aria-expanded", "true")
        inside = page.frame_locator("[data-hmz=face-frame]")
        inside.locator("#notes").fill("Half a thought")
        # The window left for the face's frame is a press outside the menu: it shuts.
        expect(bell).to_have_attribute("aria-expanded", "false")
        expect(page.locator(".popover:visible")).to_have_count(0)

        switch = face.locator("[data-hmz=face-plain]")
        expect(switch).to_have_text("Plain form")
        switch.click()
        expect(face).to_have_attribute("data-plain", "true")
        expect(face.locator("[data-hmz=face-stage]")).to_be_hidden()
        expect(switch).to_have_text("Back to Review")
        expect(switch).to_have_attribute("aria-pressed", "true")
        switch.click()
        expect(face).to_have_attribute("data-plain", "false")
        expect(inside.locator("#notes")).to_have_value("Half a thought")
        assert page.evaluate("window.plains") == [[True, "chosen"], [False, "chosen"]]


@pytest.mark.parametrize(
    ("width", "dark"), [(1280, False), (1280, True), (375, False), (375, True)]
)
def test_a_face_is_drawn_in_the_pages_colours(
    engine: str, width: int, dark: bool
) -> None:
    wire = _wire()
    with (
        served() as site,
        opened(site, engine=engine, routed=wire.routes, width=width, dark=dark) as page,
    ):
        page.evaluate(_MOUNT, _question("q1", "review"))
        face = page.locator("[data-hmz=face]")
        expect(face).to_have_attribute("data-state", "ready")
        inside = page.frame_locator("[data-hmz=face-frame]")
        expect(inside.locator("#prompt")).to_have_text("Review change q1")
        frame = _frame(page)
        ink = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--ink').trim()"
        )
        drawn = frame.evaluate("getComputedStyle(document.body).color")
        # The face's text is the page's ink, whichever way it is said.
        assert drawn == page.evaluate(
            "(ink) => { const probe = document.createElement('i'); probe.style.color = ink;"
            " document.body.append(probe); const said = getComputedStyle(probe).color;"
            " probe.remove(); return said }",
            ink,
        )
        # Flat, as the page is: nothing of the face's kit, nor of its box, casts a shadow.
        assert frame.evaluate(_SHADOWED) == []
        assert page.evaluate(_SHADOWED) == []
        # Nothing of it runs past the frame at a phone's width.
        width_ = frame.evaluate("document.documentElement.scrollWidth")
        assert width_ <= frame.evaluate("innerWidth")
        shots = os.environ.get("HMZ_FACE_SHOTS")
        if shots:
            Path(shots).mkdir(parents=True, exist_ok=True)
            name = f"face-{engine}-{width}-{'dark' if dark else 'light'}.png"
            page.wait_for_timeout(250)
            face.screenshot(path=str(Path(shots) / name))
