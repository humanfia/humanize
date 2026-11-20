"""An environment's Terminal panel, drawn by xterm in a real browser on a shell faked in the page.

The panel is mounted alone, as the environments frame mounts it, with a `ctx` whose calls a
small shell answers in the page: it echoes what is typed, answers a line with a line, ends on
`exit` with status 3, keeps every terminal's scrollback and records every ack and resize. xterm
and its addons are bundled for the test from npm with esbuild and served at `/vendor/`, as the
vendored bundle is; without node and pnpm the test is skipped. Each in Chromium and WebKit.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Error, expect

from tests.conftest import THEIRS
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, opened

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Page, Route

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: The packages bundled, pinned.
_PACKAGES = {
    "@xterm/xterm": "5.5.0",
    "@xterm/addon-fit": "0.10.0",
    "@xterm/addon-search": "0.15.0",
    "@xterm/addon-unicode11": "0.8.0",
    "@xterm/addon-web-links": "0.11.0",
    "@xterm/addon-webgl": "0.18.0",
    "esbuild": "0.24.0",
}

#: The bundle's entry: the names `/vendor/xterm.js` exports, its Terminal kept where a test
#: reads what it holds -- drawn by WebGL, a terminal's text is not in the page.
_ENTRY = """
import * as X from '@xterm/xterm'
export class Terminal extends X.Terminal {
  constructor(options) {
    super(options)
    ;(globalThis.__terms ||= []).push(this)
  }
}
export { FitAddon } from '@xterm/addon-fit'
export { SearchAddon } from '@xterm/addon-search'
export { Unicode11Addon } from '@xterm/addon-unicode11'
export { WebLinksAddon } from '@xterm/addon-web-links'
export { WebglAddon } from '@xterm/addon-webgl'
"""

#: The fake shell and the `ctx` it answers through, made `window.fake`.
_FAKE = """
(() => {
  const listeners = new Map()
  const calls = []
  const terms = new Map()
  let made = 0
  let sent = 0
  const encoder = new TextEncoder()
  const b64 = (text) => {
    let raw = ''
    for (const byte of encoder.encode(text)) raw += String.fromCharCode(byte)
    return btoa(raw)
  }
  const text = (data) => new TextDecoder().decode(Uint8Array.from(atob(data), (c) => c.charCodeAt(0)))
  const emit = (message) => setTimeout(() => (listeners.get(message.type) || new Set()).forEach((fn) => fn(message)), 0)
  const out = (term, said) => {
    const one = terms.get(term)
    one.scroll += said
    sent += encoder.encode(said).length
    emit({ type: 'term', term, data: b64(said) })
  }
  const typed = (term, said) => {
    const one = terms.get(term)
    for (const char of said) {
      if (char === '\\r') {
        const line = one.line
        one.line = ''
        if (line === 'exit') {
          out(term, '\\r\\nlogout\\r\\n')
          one.alive = false
          emit({ type: 'term_exit', term, status: 3 })
        } else out(term, `\\r\\nyou said: ${line}\\r\\n$ `)
      } else if (char === '\\x7f') {
        one.line = one.line.slice(0, -1)
        out(term, '\\b \\b')
      } else {
        one.line += char
        out(term, char)
      }
    }
  }
  const kept = new Map()
  window.fake = {
    calls,
    terms,
    refuse: null,
    get sent() { return sent },
    acked: (term) => calls.filter(([m, p]) => m === 'env.term.ack' && p.term === term).reduce((sum, [, p]) => sum + p.bytes, 0),
    typed: (term) => calls.filter(([m, p]) => m === 'env.term.input' && p.term === term).map(([, p]) => text(p.data)).join(''),
    flood(term, size) {
      const line = 'x'.repeat(78) + '\\r\\n'
      let left = size
      while (left > 0) {
        const piece = line.repeat(Math.min(800, Math.ceil(left / 80))).slice(0, Math.min(left, 64000))
        out(term, piece)
        left -= piece.length
      }
    },
    emit,
    ctx: {
      env: { id: '1:root', open: true, caps: ['shell', 'files'], declared: ['shell'] },
      async call(method, params) {
        calls.push([method, params])
        if (window.fake.refuse && method === 'env.term.open') throw new Error(window.fake.refuse)
        if (method === 'env.term.list') {
          return { terms: [...terms].map(([term, one]) => ({ term, env: '1:root', title: '', cols: one.cols, rows: one.rows, alive: one.alive })) }
        }
        if (method === 'env.term.open') {
          if (params.term) {
            const one = terms.get(params.term)
            if (!one) throw new Error(`There is no terminal ${params.term}.`)
            Object.assign(one, { cols: params.cols, rows: params.rows })
            return { term: params.term, shell: null, replay: b64(one.scroll) }
          }
          const term = `t${++made}`
          terms.set(term, { scroll: '', line: '', alive: true, cols: params.cols, rows: params.rows })
          setTimeout(() => out(term, '\\x1b[1;32mwelcome\\x1b[0m to \\x1b[36mbash\\x1b[0m \\x1b[31mred\\x1b[33m yellow\\x1b[34m blue\\x1b[35m magenta\\x1b[0m\\r\\n$ '), 10)
          return { term, shell: null, replay: '' }
        }
        const one = terms.get(params.term)
        if (!one) throw new Error(`There is no terminal ${params.term}.`)
        if (method === 'env.term.input') typed(params.term, text(params.data))
        else if (method === 'env.term.resize') Object.assign(one, { cols: params.cols, rows: params.rows })
        else if (method === 'env.term.close') terms.delete(params.term)
        return {}
      },
      on(type, fn) {
        if (!listeners.has(type)) listeners.set(type, new Set())
        listeners.get(type).add(fn)
        return () => listeners.get(type).delete(fn)
      },
      keep(key, value) {
        if (value !== undefined) kept.set(key, value)
        return kept.get(key) ?? null
      },
      open() {},
      confirm: async () => true,
      theme: () => ({ dark: document.documentElement.dataset.theme === 'dark', tokens: {} }),
    },
  }
})()
"""  # noqa: E501

#: Mounts the panel over the page, in a box of the size given; `window.panel` is what it returns.
_MOUNT = """async ([width, height]) => {
  window.panel?.leave()
  document.getElementById('term-box')?.remove()
  const box = document.createElement('div')
  box.id = 'term-box'
  Object.assign(box.style, { position: 'fixed', left: '20px', top: '20px', width: `${width}px`, height: `${height}px`, zIndex: 1000 })
  document.body.append(box)
  const { mount } = await import('/views/envs/terminal.js')
  window.__terms = []
  window.panel = await mount(box, window.fake.ctx)
}"""  # noqa: E501

#: The text a terminal holds, every line of its buffer.
_TEXT = """(at) => {
  const term = window.__terms[at]
  if (!term) return ''
  const buffer = term.buffer.active
  const lines = []
  for (let y = 0; y < buffer.length; y++) lines.push(buffer.getLine(y).translateToString(true))
  return lines.join('\\n')
}"""

#: What a paired device is refused a terminal with.
_PAIRED = "Terminals are off for paired devices; turn on envs.paired_terminals."

#: Where a screenshot of the panel is kept, if anywhere.
_SHOTS = os.environ.get("HMZ_WEB_SHOTS", "")


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The xterm library and its addons, bundled as `/vendor/xterm.js`, with its CSS beside it."""
    # Found as whoever runs the suite finds them: before any test, `PATH` is the suite's.
    pnpm = shutil.which("pnpm", path=THEIRS["PATH"])
    if not shutil.which("node", path=THEIRS["PATH"]) or not pnpm:
        pytest.skip("node and pnpm are needed to bundle xterm")
    at = tmp_path_factory.mktemp("xterm")
    deps = ",".join(f'"{name}":"{version}"' for name, version in _PACKAGES.items())
    (at / "package.json").write_text(
        f'{{"name":"x","private":true,"dependencies":{{{deps}}},'
        '"pnpm":{"onlyBuiltDependencies":["esbuild"]}}'
    )
    # esbuild fetches its binary in a build script, which pnpm runs only for those allowed.
    (at / "pnpm-workspace.yaml").write_text(
        "onlyBuiltDependencies:\n  - esbuild\nallowBuilds:\n  esbuild: true\n"
    )
    (at / "entry.js").write_text(_ENTRY)
    env = {**os.environ, **THEIRS, "CI": "1"}
    try:
        subprocess.run(
            [pnpm, "install", "--reporter=silent"],
            cwd=at,
            check=True,
            env=env,
            timeout=300,
            capture_output=True,
        )
        subprocess.run(
            [
                str(at / "node_modules" / ".bin" / "esbuild"),
                "entry.js",
                "--bundle",
                "--format=esm",
                "--outfile=xterm.js",
            ],
            cwd=at,
            check=True,
            env=env,
            timeout=120,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        said = (error.stderr or error.stdout or b"").decode(errors="replace")[-600:]
        pytest.skip(f"xterm could not be bundled: {error}: {said}")
    except (subprocess.SubprocessError, OSError) as error:
        pytest.skip(f"xterm could not be bundled: {error}")
    shutil.copy(
        at / "node_modules" / "@xterm" / "xterm" / "css" / "xterm.css",
        at / "xterm_css.css",
    )
    return at


def _relaxed(route: Route) -> None:
    """The page, its CSP letting xterm set styles inline, as the vendored bundle's change has it."""
    if route.request.resource_type != "document":
        route.fallback()
        return
    answer = route.fetch()
    headers = {
        name: re.sub(
            r"style-src 'self'(?! 'unsafe-inline')",
            "style-src 'self' 'unsafe-inline'",
            value,
        )
        if name.lower() == "content-security-policy"
        else value
        for name, value in answer.headers.items()
    }
    route.fulfill(response=answer, headers=headers)


def _routes(bundle: Path) -> Callable[[Page], None]:
    def routed(page: Page) -> None:
        # The CSP relaxed: in Chromium as its devtools let a page bypass it -- the page itself
        # answered here would be refused its socket to the daemon, for being no longer local --
        # and elsewhere by answering the page with the header relaxed.
        try:
            page.context.new_cdp_session(page).send(  # pyright: ignore[reportUnknownMemberType]
                "Page.setBypassCSP", {"enabled": True}
            )
        except Error:
            page.route("**/*", _relaxed)
        page.route(
            re.compile(r".*/vendor/xterm\.js$"),
            lambda route: route.fulfill(
                body=(bundle / "xterm.js").read_bytes(), content_type="text/javascript"
            ),
        )
        page.route(
            re.compile(r".*/vendor/xterm_css\.css$"),
            lambda route: route.fulfill(
                body=(bundle / "xterm_css.css").read_bytes(), content_type="text/css"
            ),
        )
        page.add_init_script(_FAKE)

    return routed


def _shows(page: Page, text: str, at: int = 0) -> None:
    """Waits until terminal `at` holds `text`."""
    page.wait_for_function(
        f"([at, text]) => ({_TEXT})(at).includes(text)", arg=[at, text]
    )


def _count(page: Page, text: str, at: int = 0) -> int:
    """How many times terminal `at` holds `text`."""
    return int(
        page.evaluate(
            f"([at, text]) => ({_TEXT})(at).split(text).length - 1", [at, text]
        )
    )


def _calls(page: Page, method: str) -> list[dict[str, Any]]:
    """What each call of `method` the panel made was called with."""
    return page.evaluate(
        "(method) => window.fake.calls.filter(([m]) => m === method).map(([, p]) => p)",
        method,
    )


def _snapshot(page: Page, *, open_: bool) -> None:
    """Tells the panel the `envs` snapshot, as the host sends it on attaching."""
    page.evaluate(
        "(open) => window.fake.emit({ type: 'envs', envs: [{ id: '1:root', open }] })",
        open_,
    )


def test_a_shell_is_typed_into_fitted_acknowledged_and_attached_again(
    bundle: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine, routed=_routes(bundle)) as page:
        page.evaluate(_MOUNT, [900, 420])
        panel = page.locator("[data-hmz=terminal]")
        expect(panel.locator("[data-hmz=term-tab]")).to_have_count(1)
        expect(panel.locator("[data-hmz=term-title]")).to_have_text("shell")
        _shows(page, "welcome to bash")
        # Opened at the size the panel fits, not xterm's 80 by 24.
        first = _calls(page, "env.term.open")[0]
        assert "term" not in first
        assert (first["cols"], first["rows"]) != (80, 24)

        page.locator("[data-hmz=term-host]").click()
        page.keyboard.type("echo hi")
        page.keyboard.press("Enter")
        _shows(page, "you said: echo hi")
        assert page.evaluate("() => window.fake.typed('t1')") == "echo hi\r"
        if _SHOTS:
            shot = Path(_SHOTS) / f"web_envs_terminal_{engine}.png"
            page.locator("#term-box").screenshot(path=str(shot))

        # Narrowed, the panel tells the host its new size.
        was = page.evaluate("() => window.fake.terms.get('t1').cols")
        page.evaluate(
            "() => { document.getElementById('term-box').style.width = '520px' }"
        )
        page.wait_for_function(
            "(was) => window.fake.terms.get('t1').cols < was", arg=was
        )
        assert _calls(page, "env.term.resize")[-1]["cols"] == page.evaluate(
            "() => window.__terms[0].cols"
        )

        # Output is acknowledged once drawn, all of it, the rest once drawing idles.
        page.evaluate("() => window.fake.flood('t1', 300 * 1024)")
        page.wait_for_function("() => window.fake.acked('t1') === window.fake.sent")
        assert max(one["bytes"] for one in _calls(page, "env.term.ack")) >= 64 * 1024

        # Left, the terminal lives on; mounted again, it is attached with its scrollback.
        page.evaluate("() => window.panel.leave()")
        assert not _calls(page, "env.term.close")
        page.evaluate(_MOUNT, [900, 420])
        _shows(page, "you said: echo hi")
        assert [one.get("term") for one in _calls(page, "env.term.open")] == [
            None,
            "t1",
        ]
        expect(panel.locator("[data-hmz=term-tab]")).to_have_count(1)

        # Reached again, as a snapshot says, it is told only what it missed.
        page.evaluate(
            "() => { window.fake.terms.get('t1').scroll += 'you said: missed\\r\\n$ ' }"
        )
        _snapshot(page, open_=True)
        _shows(page, "you said: missed")
        assert _count(page, "you said: echo hi") == 1

        # Ended, it says with what status, and starts another in its place.
        page.locator("[data-hmz=term-host]").click()
        page.keyboard.type("exit")
        page.keyboard.press("Enter")
        expect(panel.locator("[data-hmz=term-status]")).to_have_text(
            "Exited with status 3."
        )
        _shows(page, "[exited with status 3]")
        expect(panel.locator("[data-hmz=term-tab].exited")).to_have_count(1)
        panel.locator("[data-hmz=term-restart]").click()
        expect(panel.locator("[data-hmz=term-tab]")).to_have_attribute(
            "data-term", "t2"
        )
        expect(panel.locator("[data-hmz=term-exit]")).to_be_hidden()


def test_tabs_are_added_found_in_renamed_and_closed(bundle: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, routed=_routes(bundle)) as page:
        page.evaluate(_MOUNT, [900, 420])
        panel = page.locator("[data-hmz=terminal]")
        tabs = panel.locator("[data-hmz=term-tab]")
        active = panel.locator("[data-hmz=term-tab].active")
        expect(tabs).to_have_count(1)
        panel.locator("[data-hmz=term-new]").click()
        expect(tabs).to_have_count(2)
        expect(active).to_have_attribute("data-term", "t2")

        page.locator("[data-hmz=term-host]:visible").click()
        _shows(page, "welcome", 1)
        page.keyboard.type("findme")
        page.keyboard.press("Enter")
        _shows(page, "you said: findme", 1)
        page.keyboard.press("ControlOrMeta+f")
        finder = panel.locator("[data-hmz=term-finder]")
        expect(finder).to_be_visible()
        panel.locator("[data-hmz=term-find]").fill("findme")
        count = panel.locator("[data-hmz=term-find-count]")
        expect(count).to_have_text(re.compile(r"^[12] of 2$"))
        panel.locator("[data-hmz=term-find]").press("Escape")
        expect(finder).to_be_hidden()

        active.dblclick()
        panel.locator("[data-hmz=term-rename]").fill("server")
        panel.locator("[data-hmz=term-rename]").press("Enter")
        expect(active.locator("[data-hmz=term-title]")).to_have_text("server")

        active.locator("[data-hmz=term-close]").click()
        expect(tabs).to_have_count(1)
        assert _calls(page, "env.term.close") == [{"term": "t2"}]
        expect(active).to_have_attribute("data-term", "t1")


def test_a_paired_device_is_told_what_to_turn_on_and_a_closed_env_is_read_only(
    bundle: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine, routed=_routes(bundle)) as page:
        page.evaluate("(why) => { window.fake.refuse = why }", _PAIRED)
        page.evaluate(_MOUNT, [900, 420])
        panel = page.locator("[data-hmz=terminal]")
        notice = panel.locator("[data-hmz=term-notice]")
        expect(notice).to_contain_text("Terminals are off for paired devices.")
        expect(notice.locator("code")).to_have_text("envs.paired_terminals")
        expect(panel.locator("[data-hmz=term-tab]")).to_have_count(0)

        page.evaluate("() => { window.fake.refuse = null }")
        notice.locator("[data-hmz=term-retry]").click()
        expect(panel.locator("[data-hmz=term-tab]")).to_have_count(1)
        expect(notice).to_be_hidden()

        _snapshot(page, open_=False)
        expect(notice).to_contain_text("This environment has closed.")
        expect(panel.locator("[data-hmz=term-new]")).to_be_disabled()
        assert page.evaluate("() => window.__terms.at(-1).options.disableStdin") is True
