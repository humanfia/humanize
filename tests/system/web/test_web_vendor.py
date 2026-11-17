"""The page's third-party code in a real browser, under the policy the page is served with.

The editor (CodeMirror) and the terminal (xterm.js) are imported from `/vendor/` as the env
panels import them, each mounted and written to, and neither may be refused anything by the
page's Content-Security-Policy, nor throw. Each in Chromium and WebKit.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, opened

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: Mounts an editor and a terminal on the page, and answers what each drew.
_MOUNT = """async (dark) => {
    const refused = []
    document.addEventListener('securitypolicyviolation', (event) =>
        refused.push(`${event.violatedDirective} ${event.blockedURI}`))
    const cm = await import('/vendor/codemirror.js')
    const xt = await import('/vendor/xterm.js')
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = '/vendor/xterm_css.css'
    const linked = new Promise((done, failed) => { link.onload = done; link.onerror = failed })
    document.head.append(link)
    await linked

    const stage = document.createElement('div')
    stage.style.cssText = 'position:fixed;inset:40px;z-index:9999;display:grid;gap:8px;' +
        'grid-template-rows:1fr 1fr;background:var(--paper)'
    const editorAt = document.createElement('div')
    const terminalAt = document.createElement('div')
    editorAt.style.cssText = terminalAt.style.cssText = 'min-height:0;overflow:hidden'
    stage.append(editorAt, terminalAt)
    document.body.append(stage)

    const style = getComputedStyle(document.documentElement)
    const tokens = {}
    for (const name of ['paper', 'surface', 'raised', 'ink', 'ink-2', 'ink-3', 'line',
                        'line-strong', 'cyan', 'pink', 'green', 'mono', 'sans'])
        tokens[name] = style.getPropertyValue(`--${name}`)
    const view = new cm.EditorView({
        parent: editorAt,
        state: cm.EditorState.create({
            doc: 'def greet(name: str) -> str:\\n    # Say hello.\\n    return f"hi {name}"\\n',
            extensions: [cm.basicSetup, cm.languageFor('a.py'), cm.themeFor({dark, tokens})],
        }),
    })
    cm.openSearchPanel(view)

    const term = new xt.Terminal({fontFamily: tokens.mono, allowProposedApi: true})
    const fit = new xt.FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new xt.SearchAddon())
    term.loadAddon(new xt.WebLinksAddon())
    term.loadAddon(new xt.Unicode11Addon())
    term.unicode.activeVersion = '11'
    term.open(terminalAt)
    let renderer = 'dom'
    try {
        const webgl = new xt.WebglAddon()
        webgl.onContextLoss(() => webgl.dispose())
        term.loadAddon(webgl)
        renderer = 'webgl'
    } catch {}
    fit.fit()
    await new Promise((done) => term.write('\\x1b[1;36mhello\\x1b[0m from xterm\\r\\n$ ', done))
    await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))

    const keyword = [...editorAt.querySelectorAll('.cm-line span')]
        .find((span) => span.textContent === 'def')
    return {
        refused,
        lines: view.state.doc.lines,
        search: !!editorAt.querySelector('.cm-search'),
        keyword: keyword ? getComputedStyle(keyword).color : null,
        plain: getComputedStyle(editorAt.querySelector('.cm-line')).color,
        rows: term.rows,
        cols: term.cols,
        line: term.buffer.active.getLine(0).translateToString(true),
        renderer,
    }
}"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, and a project."""
    del asking
    return install(tmp_path, monkeypatch)


def _shot(page: Page, name: str) -> None:
    """Keeps what was drawn where `HMZ_SHOTS` says, if it says anywhere."""
    if to := os.environ.get("HMZ_SHOTS"):
        page.screenshot(path=str(Path(to) / name))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_an_editor_and_a_terminal_draw_under_the_pages_own_policy(
    project: Path, engine: str, *, dark: bool
) -> None:
    del project
    with served() as site, opened(site, engine=engine, dark=dark) as page:
        drawn: dict[str, Any] = page.evaluate(_MOUNT, dark)
        _shot(page, f"vendor-{engine}-{'dark' if dark else 'light'}.png")

    assert drawn["refused"] == []
    assert drawn["lines"] == 4
    assert drawn["search"]
    # Python is highlighted: its keyword is not drawn in the plain text's colour.
    assert drawn["keyword"] is not None
    assert drawn["keyword"] != drawn["plain"]
    assert drawn["rows"] > 2
    assert drawn["cols"] > 20
    assert drawn["line"] == "hello from xterm"
    assert drawn["renderer"] in {"webgl", "dom"}
