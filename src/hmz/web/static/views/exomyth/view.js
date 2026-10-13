// Exomyth: one epic's timeline, `#/epics/<name>/exomyth[?tab=flame]`. Its flows, each agent
// session and each program it ran as processes over time -- the Timeline -- or as a flame graph
// -- the Flame -- with a panel beside them of what is picked: the epic, a process, a span and
// what it carried, or a stretch of time. An epic still going is read again every few seconds,
// for as long as it is looked at.

import { get, hash, poll, refresh } from '../../api.js'
import { stays } from '../../app.js'
import { badge, copier, fill, h, headline, icon, iconButton, problem } from '../../dom.js'
import { bar, sidePanel, tabbed } from '../../shell.js'
import { overview, processOf, rangeOf, spanOf } from './details.js'
import { counted, lasted, load } from './model.js'
import { timeline } from './timeline.js'

/** How often an epic still going is read again, in milliseconds. */
const EVERY = 2000

export function mount(root, name, query) {
  const base = `/api/runs/${encodeURIComponent(name)}`
  const url = `${base}/timeline`
  let tab = query.get('tab') === 'flame' ? 'flame' : 'timeline'
  let model = null
  let detail = null
  let picked = null
  let range = null
  /** What was read of the span picked, and of every span read, by layout and id. */
  let read = {}
  const spans = new Map()
  let matches = []
  let match = -1
  let flame = null
  /** What share of the Flame the words found hold, or null. */
  let share = null
  let flaming = 0
  let left = false

  const panel = sidePanel('Exomyth')
  const head = h('div', { class: 'bar-holder' })
  const tools = h('div', { class: 'exo-tools', 'data-hmz': 'exomyth-tools' })
  const flameHost = h('div', { class: 'exo-flame', 'data-hmz': 'exomyth-flame' })
  const chart = timeline({
    picked: (it) => chose(it, false),
    ranged: (it) => {
      range = it
      if (it) chose(null)
      else details()
      flamed()
    },
  })
  const main = h('div', { class: 'exo-main' }, chart.node, flameHost)
  fill(root, h('div', { class: 'view view-epic view-exomyth', 'data-hmz': 'exomyth' }, h('div', { class: 'work' }, head, tools, main), panel.node))

  // ---------------------------------------------------------------- the bar and the tools

  function drawHead() {
    const link = hash(`/epics/${encodeURIComponent(name)}`)
    const title = h('span', { class: 'crumbs' }, h('a', { href: link }, detail ? headline(detail.task) : name), h('span', { 'aria-hidden': 'true' }, ' / '), h('span', {}, 'Exomyth'))
    const sub = model
      ? [badge(model.live ? 'running' : (detail && detail.how) || 'done'), h('span', {}, `${counted(model.summary.processes)} processes`), h('span', {}, `${counted(model.summary.spans)} spans`), h('span', { class: 'mono' }, lasted(model.end))]
      : []
    fill(head, bar({ title, sub, actions: [copier('Copy link', () => location.href), panel.toggle] }))
  }

  const finding = h('input', { type: 'search', class: 'exo-find', placeholder: 'Find', 'aria-label': 'Find', 'data-hmz': 'exomyth-find', spellcheck: 'false' })
  const counter = h('span', { class: 'exo-found mono', 'data-hmz': 'exomyth-found', 'aria-live': 'polite' })

  function drawTools() {
    fill(
      tools,
      tabbed(
        [
          ['timeline', 'Timeline'],
          ['flame', 'Flame'],
        ],
        tab,
        shownAs,
      ),
      h(
        'div',
        { class: 'exo-actions' },
        h('div', { class: 'exo-search' }, icon('search'), finding, counter, iconButton('up', 'Previous', { onclick: () => step(-1) }), iconButton('down', 'Next', { onclick: () => step(1) })),
        tab === 'timeline'
          ? [
              h('button', { type: 'button', class: 'btn small', onclick: () => chart.foldAll(false) }, 'Expand'),
              h('button', { type: 'button', class: 'btn small', onclick: () => chart.foldAll(true) }, 'Collapse'),
              h('button', { type: 'button', class: 'btn small', onclick: () => chart.reset() }, icon('fit'), 'Reset'),
            ]
          : null,
      ),
    )
  }

  /** Shows a tab. */
  function shownAs(key) {
    tab = key
    stays(tab === 'flame' ? { tab } : {})
    drawTools()
    shownTab()
    tally()
  }

  /** Finds again what is asked for, keeping the place among what is found at the span picked. */
  function refind() {
    matches = chart.find(finding.value)
    share = flame && flame.find ? flame.find(finding.value) : null
    match = picked && picked.span !== undefined ? matches.indexOf(picked.span) : -1
    tally()
  }
  finding.addEventListener('input', refind)
  // What clears a search box -- its own button, or Escape -- says so as `search` alone.
  finding.addEventListener('search', refind)
  finding.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      step(event.shiftKey ? -1 : 1)
    } else if (event.key === 'Escape') {
      // Cleared first, then let go of.
      event.preventDefault()
      if (finding.value) {
        finding.value = ''
        refind()
      } else finding.blur()
    }
  })

  function tally() {
    if (tab === 'flame') counter.textContent = share === null ? '' : `${(share * 100).toFixed(1)}%`
    else counter.textContent = finding.value.trim() ? (match >= 0 ? `${match + 1}/${matches.length}` : String(matches.length)) : ''
  }

  /** Picks the next span found, or the one before. */
  function step(by) {
    if (tab !== 'timeline' || !matches.length) return
    match = (match + by + matches.length) % matches.length
    tally()
    chose({ span: matches[match] })
    chart.visit(matches[match])
  }

  function keyed(event) {
    if (event.metaKey || event.ctrlKey || event.altKey || document.body.classList.contains('dialog-open')) return
    if (event.target instanceof Element && event.target.closest('input, textarea, select, [contenteditable]')) return
    if (event.key === '/') {
      event.preventDefault()
      finding.focus()
      finding.select()
    } else if (event.key === 'n' || event.key === 'N') {
      event.preventDefault()
      step(event.key === 'N' ? -1 : 1)
    }
  }
  document.addEventListener('keydown', keyed)

  // ---------------------------------------------------------------- what is picked

  /** Picks a span or a process, or nothing; reads what a span carried. */
  function chose(it, tell = true) {
    picked = it
    read = {}
    if (tell) chart.pick(it)
    if (it && it.span !== undefined) carried(it.span)
    details()
  }

  async function carried(id) {
    const key = `${model.layout}:${id}`
    if (spans.has(key)) {
      read = spans.get(key)
      return
    }
    read = { reading: true }
    let said
    try {
      const answer = await get(`${base}/timeline/span/${id}?layout=${encodeURIComponent(model.layout)}`)
      said = { args: answer.args }
      spans.set(key, said)
    } catch (error) {
      said = { error }
      // Laid out again since it was read: read again, which leaves nothing picked.
      if (error.status === 409) refresh(url)
    }
    if (picked && picked.span === id && key === `${model.layout}:${id}`) {
      read = said
      details()
    }
  }

  function details() {
    if (!model) return
    let parts
    if (picked && picked.span !== undefined) parts = spanOf(model, picked.span, read, { pick: chose, zoom: () => chart.zoomTo(picked.span) })
    else if (picked && picked.process !== undefined) {
      const one = model.processes[picked.process]
      parts = processOf(model, picked.process, { zoom: () => chart.show(one.start, one.end) })
    } else if (range) {
      const shown = range
      parts = rangeOf(model, range, {
        zoom: () => chart.show(shown.from, shown.to),
        clear: () => {
          chart.unrange()
          range = null
          details()
          flamed()
        },
      })
    } else parts = overview(model, chose)
    fill(panel.body, h('div', { class: 'panel-pane', 'data-hmz': 'exomyth-details' }, parts))
  }

  // ---------------------------------------------------------------- the tabs

  function shownTab() {
    chart.node.hidden = tab !== 'timeline'
    flameHost.hidden = tab !== 'flame'
    flamed()
  }

  /** Draws the Flame where it is the tab picked: loaded once, then told what changed. */
  async function flamed() {
    if (tab !== 'flame' || !model) {
      if (tab !== 'flame' && flame) {
        flame.leave?.()
        flame = null
        share = null
      }
      return
    }
    if (flame && flame.update) {
      flame.update(model, range)
      return
    }
    const mine = ++flaming
    try {
      const module = await import('./flame.js')
      if (mine !== flaming || left || tab !== 'flame') return
      flame?.leave?.()
      flame = module.mount(flameHost, model, range, {
        timeline: (said) => {
          finding.value = said
          shownAs('timeline')
          refind()
        },
        shared: (said) => {
          share = said
          tally()
        },
      }) || {}
      if (finding.value.trim()) refind()
    } catch (error) {
      fill(flameHost, problem(error))
    }
  }

  // ---------------------------------------------------------------- reading it

  /** The document the model was read out of, and how often it is read again: never, once ended. */
  let doc = null
  let every = null
  let unwatch = () => {}

  /**
   * Reads the timeline as `api.poll` reads anything: again while the epic goes, and not while
   * the page is hidden. The browser asks again with the tag it was given, and is answered that
   * it has it already; an answer the same as the last is told nobody.
   */
  function watch(often) {
    const was = unwatch
    every = often
    unwatch = poll(url, often, told)
    was()
  }

  function told(data, error) {
    if (left) return
    if (error) {
      // Said where it happened: in place of a timeline never read; one read before is kept.
      if (!model) {
        fill(main, h('div', { class: 'view-pad' }, problem(error)))
        fill(panel.body)
      }
      return
    }
    if (data === doc) return
    doc = data
    try {
      took(load(data))
    } catch (failed) {
      fill(main, h('div', { class: 'view-pad' }, problem(failed)))
      return
    }
    if (!main.contains(chart.node)) fill(main, chart.node, flameHost)
    const often = model.live ? EVERY : null
    if (often !== every) watch(often)
  }

  function took(next) {
    const moved = model && model.layout !== next.layout
    // An epic seen going that has ended: how it ended is read again.
    if (model && model.live && !next.live) described()
    model = next
    chart.shown(model)
    if (moved) {
      picked = null
      read = {}
      spans.clear()
    }
    drawHead()
    details()
    flamed()
    if (finding.value.trim()) refind()
  }

  /** Reads what the epic is -- its task, how it ended -- which the bar says. */
  function described() {
    get(base).then(
      (said) => {
        detail = said
        if (!left) drawHead()
      },
      () => {},
    )
  }
  described()

  drawHead()
  drawTools()
  shownTab()
  fill(panel.body, h('div', { class: 'panel-pane' }, h('p', { class: 'loading', role: 'status' }, 'Reading the timeline…')))
  watch(null)

  window.__exomyth = {
    model: () => model,
    render: () => chart.debug.render(),
    view: () => chart.debug.view(),
    where: (id) => chart.debug.where(id),
    rows: () => chart.debug.rows(),
    flame: () => flame && flame.debug,
  }

  return () => {
    left = true
    unwatch()
    document.removeEventListener('keydown', keyed)
    chart.leave()
    flame?.leave?.()
    delete window.__exomyth
  }
}
