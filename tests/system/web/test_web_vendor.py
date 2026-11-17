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


#: Renders Markdown and draws a bar chart on the page, and answers what each drew.
_DRAW = """async (dark) => {
    const refused = []
    document.addEventListener('securitypolicyviolation', (event) =>
        refused.push(`${event.violatedDirective} ${event.blockedURI}`))
    const errors = []
    window.addEventListener('error', (event) => errors.push(String(event.message)))
    const md = await import('/vendor/markdown.js')
    const vega = await import('/vendor/vega.js')

    const stage = document.createElement('div')
    stage.style.cssText = 'position:fixed;inset:40px;z-index:9999;overflow:auto;padding:16px;' +
        'background:var(--paper);color:var(--ink)'
    const prose = document.createElement('div')
    prose.innerHTML = md.render([
        '# Review', '', 'Looks **good**, see [the run](https://example.com/run).', '',
        '| file | + | - |', '| --- | --- | --- |', '| a.py | 12 | 3 |', '',
        '- [x] tests', '- [ ] docs', '',
        '<img src="https://example.com/x.png" alt="a picture"> <script>window.ran = 1</script>',
        '<a href="javascript:window.ran=2">bad</a> <span style="color:red" onclick="x()">s</span>',
        '<a href="#top">up</a> <video src="/no-such-video.mp4"></video>',
        '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" srcset="/no-such-picture.png 1x">',
    ].join('\\n'))
    const chartAt = document.createElement('div')
    stage.append(prose, chartAt)
    document.body.append(stage)
    const drawn = await vega.embed(chartAt, {
        $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
        data: {values: [{k: 'a', v: 3}, {k: 'b', v: 7}, {k: 'c', v: 5}]},
        mark: 'bar',
        encoding: {
            x: {field: 'k', type: 'nominal'},
            y: {field: 'v', type: 'quantitative'},
            color: {field: 'k', type: 'nominal'},
            tooltip: [{field: 'v'}],
        },
        transform: [{calculate: 'datum.v * 2', as: 'w'}, {filter: 'datum.w > 0'}],
    }, {theme: dark ? 'dark' : 'light'})
    try {
        await vega.embed(document.createElement('div'),
            {data: {url: '/no-such-data.json'}, mark: 'point'})
    } catch {}
    await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))
    const link = prose.querySelector('a[href^="https"]')
    const label = chartAt.querySelector('.role-axis-label text')
    return {
        refused,
        errors,
        heading: prose.querySelector('h1')?.textContent,
        strong: prose.querySelector('strong')?.textContent,
        cells: [...prose.querySelectorAll('td')].map((td) => td.textContent),
        ticked: [...prose.querySelectorAll('input')].map((box) => [box.checked, box.disabled]),
        target: link?.getAttribute('target'),
        rel: link?.getAttribute('rel'),
        scripts: prose.querySelectorAll(
            'script, img:not([src^="data:"]), [style], [onclick]').length,
        javascript: prose.querySelectorAll('a[href^="javascript"]').length,
        ran: window.ran ?? null,
        bars: chartAt.querySelectorAll('.mark-rect path').length,
        actions: chartAt.querySelectorAll('.vega-actions').length,
        label: label ? getComputedStyle(label).fill : null,
        ink: getComputedStyle(document.documentElement).getPropertyValue('--ink-2').trim(),
        signal: drawn.view.data('data_0').map((row) => row.w),
        relative: prose.querySelectorAll('a[href^="#"], video, [srcset]').length,
        pictures: prose.querySelectorAll('img[src^="data:"]').length,
        fetched: performance.getEntriesByType('resource')
            .map((entry) => entry.name).filter((name) => name.includes('/no-such-')),
    }
}"""


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_markdown_and_a_chart_draw_under_the_pages_own_policy(
    project: Path, engine: str, *, dark: bool
) -> None:
    del project
    with served() as site, opened(site, engine=engine, dark=dark) as page:
        drawn: dict[str, Any] = page.evaluate(_DRAW, dark)
        _shot(page, f"vendor-prose-{engine}-{'dark' if dark else 'light'}.png")

    assert drawn["refused"] == []
    assert drawn["errors"] == []
    assert drawn["heading"] == "Review"
    assert drawn["strong"] == "good"
    assert drawn["cells"] == ["a.py", "12", "3"]
    assert drawn["ticked"] == [[True, True], [False, True]]
    assert drawn["target"] == "_blank"
    assert drawn["rel"] == "noopener noreferrer"
    # Nothing that runs, restyles or reaches out is kept, and nothing ran.
    assert drawn["scripts"] == 0
    assert drawn["javascript"] == 0
    assert drawn["ran"] is None
    # Three bars, no menu, labelled in the page's own ink, with expressions evaluated.
    assert drawn["bars"] == 3
    assert drawn["actions"] == 0
    assert drawn["label"] is not None
    assert drawn["signal"] == [6, 14, 10]
    # An inline picture stays; a link into the page, media and other pictures go.
    assert drawn["pictures"] == 1
    assert drawn["relative"] == 0
    # Neither the Markdown nor a chart reads an address, even the page's own.
    assert drawn["fetched"] == []
