// What a question shows beside what it asks, and what a flow shows a person with nothing asked:
// blocks of context, each folded behind one line that says what it holds -- "+12 −3 in 2
// files", "table · 40 rows" -- the first open, and every short one. Markdown is read as it is
// written, through the page's own Markdown bundle, and a chart through its Vega bundle; without
// them, as plain text and as the table of what the chart is drawn from.

import { fill, h } from '../dom.js'
import { blockSummary, chartRows, imageSource, kindWord, opened, patchFiles } from './logic.js'

/** The rows of a table drawn before the rest is drawn only once asked for. */
const ROWS = 20

/** The lines of a diff drawn before the rest is drawn only once asked for. */
const LINES = 400

let markdown = null
let vega = null

/** The page's Markdown bundle, loaded once, or null where it is not there. */
function markdownBundle() {
  markdown ??= import('/vendor/markdown.js').catch(() => null)
  return markdown
}

/** The page's Vega bundle, loaded once, or null where it is not there. */
function vegaBundle() {
  vega ??= import('/vendor/vega.js').catch(() => null)
  return vega
}

/**
 * Markdown drawn into `el`: read as written where the bundle is, else as its own text.
 *
 * @param {HTMLElement} el What it is drawn into.
 * @param {unknown} text What was written.
 * @param {{html?: 'markup'|'text'}} [options] Passed to the bundle's `render`: `text` keeps
 *   the HTML a message carries as its text, rather than as markup.
 */
export function markdownInto(el, text, options) {
  el.classList.add('ask-markdown')
  fill(el, h('div', { class: 'ask-plain' }, text))
  markdownBundle().then((bundle) => {
    if (!bundle || typeof bundle.render !== 'function') return
    try {
      // The bundle hands back HTML it has sanitised: nothing in it runs.
      el.innerHTML = bundle.render(String(text), options)
      for (const link of el.querySelectorAll('a[href]')) {
        link.target = '_blank'
        link.rel = 'noopener noreferrer'
      }
    } catch {
      // Said as plain text, as it already is.
    }
  })
  return el
}

/**
 * The blocks of a question's context, or of what a flow showed, each folded behind its summary:
 * the first open, and every short one.
 */
export function blocks(context, { open = null } = {}) {
  const list = Array.isArray(context) ? context.filter((one) => one && typeof one === 'object') : []
  if (!list.length) return null
  const opens = open || opened(list)
  return h('div', { class: 'ask-blocks', 'data-hmz': 'ask-blocks' }, list.map((one, at) => block(one, opens[at])))
}

/** One block, folded behind its kind, its title and what it holds; drawn the first time it is opened. */
export function block(one, open = true) {
  const body = h('div', { class: 'ask-block-body' })
  const folded = h(
    'details',
    { class: ['ask-block', `ask-block-${one.kind}`], 'data-hmz': 'ask-block', 'data-kind': String(one.kind || ''), open: open || undefined },
    h(
      'summary',
      {},
      h('span', { class: 'ask-block-kind' }, kindWord(one.kind)),
      one.title ? h('span', { class: 'ask-block-title' }, one.title) : null,
      h('span', { class: 'ask-block-sum', 'data-hmz': 'ask-block-summary' }, blockSummary(one)),
    ),
    body,
  )
  let drawn = false
  const draw = () => {
    if (drawn || !folded.open) return
    drawn = true
    try {
      fill(body, viewOf(one))
    } catch {
      fill(body, h('pre', { class: 'ask-plain mono' }, JSON.stringify(one, null, 2)))
    }
  }
  folded.addEventListener('toggle', draw)
  draw()
  return folded
}

function viewOf(one) {
  switch (one.kind) {
    case 'markdown':
      return markdownInto(h('div', {}), String(one.text || ''))
    case 'code':
      return h('pre', { class: 'ask-code mono', 'data-language': one.language || undefined }, h('code', {}, String(one.text || '')))
    case 'diff':
      return diffView(String(one.patch || ''))
    case 'table':
      return tableView((one.columns || []).map(String), one.rows || [])
    case 'image': {
      const src = imageSource(one)
      if (!src) return h('p', { class: 'dim' }, `An image this page cannot show (${one.mime || 'no type'}).`)
      const image = h('img', { class: 'ask-image', src, alt: one.alt || one.title || 'An image the flow showed', loading: 'lazy', 'data-hmz': 'ask-image' })
      // Pressed, it is seen at its own size, and pressed again, fitted back.
      const holder = h('button', { type: 'button', class: 'ask-image-hold', 'aria-label': 'Show the image at full size', 'aria-pressed': 'false' }, image)
      holder.addEventListener('click', () => {
        const full = holder.classList.toggle('full')
        holder.setAttribute('aria-pressed', String(full))
      })
      return holder
    }
    case 'json':
      return h('div', { class: 'ask-json mono', 'data-hmz': 'ask-json', role: 'tree' }, tree(one.value, '', 0))
    case 'chart':
      return chartView(one.spec || {})
    default:
      return h('pre', { class: 'ask-plain mono' }, JSON.stringify(one, null, 2))
  }
}

/** A unified diff, a file at a time, each with what it adds and removes. */
function diffView(patch) {
  const files = patchFiles(patch)
  if (!files.length) return h('p', { class: 'dim' }, 'An empty diff.')
  let budget = LINES
  const drawn = files.map((file) => {
    const lines = file.lines.filter((one) => one.kind !== 'meta')
    const shown = lines.slice(0, Math.max(0, budget))
    budget -= shown.length
    const pre = h('pre', { class: 'ask-diff-lines mono' }, shown.map(lineOf))
    const rest = lines.length - shown.length
    const more = rest
      ? h('button', { type: 'button', class: 'btn quiet small', onclick: (event) => {
          pre.append(...lines.slice(shown.length).map(lineOf))
          event.currentTarget.remove()
        } }, `Show ${rest} more lines`)
      : null
    return h(
      'div',
      { class: 'ask-diff-file', 'data-hmz': 'ask-diff-file' },
      h('div', { class: 'ask-diff-head' }, h('span', { class: 'ask-diff-name mono' }, file.name || 'patch'), h('span', { class: 'ask-diff-add' }, `+${file.added}`), h('span', { class: 'ask-diff-del' }, `−${file.removed}`)),
      pre,
      more,
    )
  })
  return h('div', { class: 'ask-diff', 'data-hmz': 'ask-diff' }, drawn)
}

function lineOf(one) {
  // Said by a mark beside the colour, so that nothing is said by colour alone.
  return h('span', { class: ['ask-diff-line', `is-${one.kind}`] }, one.text || ' ')
}

/** A table, its first rows drawn and the rest once asked for. */
function tableView(columns, rows) {
  const cell = (value) => (value === null || value === undefined ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value))
  const numeric = columns.map((_, at) => rows.length > 0 && rows.every((row) => row[at] === null || row[at] === undefined || typeof row[at] === 'number'))
  const rowOf = (row) => h('tr', {}, columns.map((_, at) => h('td', { class: numeric[at] ? 'num' : undefined }, cell(row[at]))))
  const body = h('tbody', {}, rows.slice(0, ROWS).map(rowOf))
  const table = h('table', { class: 'ask-table', 'data-hmz': 'ask-table' }, h('thead', {}, h('tr', {}, columns.map((name, at) => h('th', { scope: 'col', class: numeric[at] ? 'num' : undefined }, name)))), body)
  const more =
    rows.length > ROWS
      ? h('button', { type: 'button', class: 'btn quiet small', onclick: (event) => {
          body.append(...rows.slice(ROWS).map(rowOf))
          event.currentTarget.remove()
        } }, `Show all ${rows.length} rows`)
      : null
  return h('div', { class: 'ask-table-wrap' }, h('div', { class: 'ask-scroll', tabindex: '0', role: 'region', 'aria-label': 'Table' }, table), more)
}

/** A value as a tree, its first levels open. */
function tree(value, key, depth) {
  const named = key === '' ? null : h('span', { class: 'ask-json-key' }, `${key}: `)
  if (value === null || typeof value !== 'object') {
    const kind = value === null ? 'null' : typeof value
    return h('div', { class: 'ask-json-leaf', role: 'treeitem' }, named, h('span', { class: `ask-json-${kind}` }, JSON.stringify(value)))
  }
  const entries = Array.isArray(value) ? value.map((one, at) => [String(at), one]) : Object.entries(value)
  const brackets = Array.isArray(value) ? ['[', ']'] : ['{', '}']
  if (!entries.length) return h('div', { class: 'ask-json-leaf', role: 'treeitem' }, named, brackets.join(''))
  return h(
    'details',
    { class: 'ask-json-node', open: depth < 2 || undefined, role: 'treeitem' },
    h('summary', {}, named, h('span', { class: 'dim' }, `${brackets[0]} ${entries.length} ${Array.isArray(value) ? (entries.length === 1 ? 'item' : 'items') : entries.length === 1 ? 'key' : 'keys'} ${brackets[1]}`)),
    h('div', { class: 'ask-json-kids', role: 'group' }, entries.map(([name, one]) => tree(one, name, depth + 1))),
  )
}

/** A chart, drawn by the page's Vega bundle in the page's colours, or its data as a table. */
function chartView(spec) {
  const holder = h('div', { class: 'ask-chart', 'data-hmz': 'ask-chart' })
  const fallback = () => {
    const { columns, rows } = chartRows(spec)
    fill(holder, rows.length ? [h('p', { class: 'dim ask-chart-note' }, 'The chart’s data, as a table:'), tableView(columns, rows)] : h('p', { class: 'dim' }, 'A chart this page cannot draw.'))
  }
  fallback()
  vegaBundle().then(async (bundle) => {
    if (!bundle || typeof bundle.embed !== 'function') return
    const drawn = h('div', { class: 'ask-chart-drawn' })
    try {
      const theme = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
      fill(holder, drawn)
      await bundle.embed(drawn, spec, { theme })
    } catch {
      fallback()
    }
  })
  return holder
}
