// What Exomyth's panel says: of the epic as a whole, of a process, of a span -- its arguments
// read when it is picked -- and of a stretch of time.

import { h, problem } from '../../dom.js'
import { clock, counted, lasted, locate, within } from './model.js'

function section(title, ...kids) {
  return h('section', { class: 'side-section' }, h('h3', {}, title), kids)
}

function facts(pairs) {
  return h(
    'dl',
    { class: 'facts' },
    pairs.filter(([, value]) => value !== '' && value !== null && value !== undefined).map(([name, value]) => [h('dt', {}, name), h('dd', {}, value)]),
  )
}

/** A moment of the epic, as how far into it and as the clock on the wall said it. */
function at(model, t) {
  return `${clock(t, 1000)} · ${new Date((model.origin + t / 1e6) * 1000).toLocaleTimeString()}`
}

function categories(by, model) {
  const order = [...model.categories, ...[...by.keys()].filter((one) => !model.categories.includes(one))].filter((one) => by.has(one))
  return h(
    'div',
    { class: 'table-wrap' },
    h(
      'table',
      { class: 'spending exo-cats', 'data-hmz': 'exomyth-categories' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Category'), h('th', { class: 'num' }, 'Spans'), h('th', { class: 'num' }, 'Time'), h('th', { class: 'num' }, 'In'), h('th', { class: 'num' }, 'Out'))),
      h(
        'tbody',
        {},
        order.map((cat) => {
          const one = by.get(cat)
          return h('tr', {}, h('td', {}, h('i', { class: `exo-key exo-${cat}`, 'aria-hidden': 'true' }), cat), h('td', { class: 'num' }, counted(one.count)), h('td', { class: 'num' }, lasted(one.time)), h('td', { class: 'num' }, counted(one.in)), h('td', { class: 'num' }, counted(one.out)))
        }),
      ),
    ),
  )
}

/** The epic as a whole: its figures, its categories, and every process, each picked by a click. */
export function overview(model, pick) {
  const by = new Map(Object.entries(model.summary.categories))
  return [
    section(
      'Epic',
      facts([
        ['name', h('span', { class: 'mono' }, model.epic || '—')],
        ['state', model.live ? 'running' : 'ended'],
        ['began', new Date(model.origin * 1000).toLocaleString()],
        ['lasted', lasted(model.end)],
        ['spans', counted(model.summary.spans)],
        ['processes', counted(model.summary.processes)],
      ]),
    ),
    section('Categories', categories(by, model)),
    section(
      'Processes',
      h(
        'ul',
        { class: 'links exo-processes', 'data-hmz': 'exomyth-processes' },
        model.order.map((id) => {
          const one = model.processes[id]
          return h(
            'li',
            { style: { paddingLeft: `${Math.min(one.level, 8) * 12}px` } },
            h('button', { type: 'button', class: 'exo-link', 'data-process': String(id), onclick: () => pick({ process: id }) }, one.name),
            h('span', { class: 'dim' }, ` ${one.kind} · ${lasted(one.end - one.start)}`),
          )
        }),
      ),
    ),
  ]
}

/** One process: what it is, and when. */
export function processOf(model, id, act) {
  const one = model.processes[id]
  const parent = model.processes[one.parent]
  return [
    section(
      'Process',
      h('p', { class: 'exo-name selectable' }, one.name),
      facts([
        ['kind', one.kind],
        ['key', one.key ? h('span', { class: 'mono' }, one.key) : ''],
        ['agent', one.agent],
        ['role', one.role],
        ['backend', one.backend],
        ['model', one.model],
        ['label', one.label],
        ['pid', one.pid || ''],
        ['parent', parent ? parent.name : ''],
        ['record', one.record ? h('span', { class: 'mono' }, one.record) : ''],
        ['start', at(model, one.start)],
        ['lasted', lasted(one.end - one.start)],
        ['tracks', String(one.tracks.length)],
        ['spans', counted(one.spans)],
      ]),
      h('p', { class: 'row' }, h('button', { type: 'button', class: 'btn small', onclick: act.zoom }, 'Zoom')),
    ),
  ]
}

/**
 * One span: what the timeline says of it at once, and what it carried once read.
 *
 * @param {{args?: object, error?: Error, reading?: boolean}} read What was read of it.
 */
export function spanOf(model, id, read, act) {
  const where = locate(model, id)
  if (!where) return []
  const track = model.tracks[where.track]
  const i = where.index
  const said = (index) => model.strings[index]
  const process = model.processes[track.process]
  return [
    section(
      'Span',
      h('p', { class: 'exo-name selectable', 'data-hmz': 'exomyth-span-name' }, said(track.name_[i]) || '—'),
      facts([
        ['category', said(track.cat[i])],
        ['start', at(model, track.start[i])],
        ['lasted', lasted(track.dur[i])],
        ['model', said(track.model[i])],
        ['tokens', track.in[i] || track.out[i] ? `${counted(track.in[i])} in · ${counted(track.out[i])} out` : ''],
        ['process', h('button', { type: 'button', class: 'exo-link', onclick: () => act.pick({ process: process.id }) }, process.name)],
        ['track', track.name],
        ['depth', String(track.depth[i])],
        ['id', h('span', { class: 'mono' }, String(id))],
      ]),
      h('p', { class: 'row' }, h('button', { type: 'button', class: 'btn small', onclick: act.zoom }, 'Zoom')),
    ),
    section(
      'Arguments',
      read.error
        ? problem(read.error)
        : read.args
          ? h('pre', { class: 'block exo-args', 'data-hmz': 'exomyth-args' }, JSON.stringify(read.args, null, 2))
          : h('p', { class: 'loading', role: 'status' }, 'Reading…'),
    ),
  ]
}

/** A stretch of time: how long, and what lies in it. */
export function rangeOf(model, range, act) {
  const held = within(model, range.from, range.to)
  return [
    section(
      'Range',
      facts([
        ['from', at(model, range.from)],
        ['to', at(model, range.to)],
        ['lasted', h('span', { 'data-hmz': 'exomyth-range' }, lasted(range.to - range.from))],
        ['spans', counted(held.count)],
        ['tokens', `${counted(held.in)} in · ${counted(held.out)} out`],
      ]),
      h('p', { class: 'row' }, h('button', { type: 'button', class: 'btn small', onclick: act.zoom }, 'Zoom'), h('button', { type: 'button', class: 'btn small quiet', onclick: act.clear }, 'Clear')),
    ),
    section('Categories', categories(held.categories, model)),
  ]
}
