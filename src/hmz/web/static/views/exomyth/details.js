// What Exomyth's panel says: of the epic as a whole, of a process, of a span -- its arguments
// read when it is picked -- and of a stretch of time.

import { h, problem } from '../../dom.js'
import { locale, t } from '../../i18n.js'
import { modelName } from '../../names.js'
import { clock, counted, lasted, locate, within } from './model.js'

/** A model by its name (names.js), its id where it is pointed at; '' for none. */
const named = (id) => (id ? h('span', { title: id }, modelName(id)) : '')

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
function at(model, time) {
  return `${clock(time, 1000)} · ${new Date((model.origin + time / 1e6) * 1000).toLocaleTimeString(locale())}`
}

function categories(by, model) {
  const order = [...model.categories, ...[...by.keys()].filter((one) => !model.categories.includes(one))].filter((one) => by.has(one))
  return h(
    'div',
    { class: 'table-wrap' },
    h(
      'table',
      { class: 'spending exo-cats', 'data-hmz': 'exomyth-categories' },
      h('thead', {}, h('tr', {}, h('th', {}, t('Category')), h('th', { class: 'num' }, t('Spans')), h('th', { class: 'num' }, t('Time')), h('th', { class: 'num' }, t('In@@tokens')), h('th', { class: 'num' }, t('Out@@tokens')))),
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
      t('Epic'),
      facts([
        [t('name'), h('span', { class: 'mono' }, model.epic || '—')],
        [t('state'), model.live ? t('running') : t('ended')],
        [t('began'), new Date(model.origin * 1000).toLocaleString(locale())],
        [t('lasted'), lasted(model.end)],
        [t('spans'), counted(model.summary.spans)],
        [t('processes'), counted(model.summary.processes)],
      ]),
    ),
    section(t('Categories'), categories(by, model)),
    section(
      t('Processes'),
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
      t('Process'),
      h('p', { class: 'exo-name selectable' }, one.name),
      facts([
        [t('kind'), one.kind],
        [t('key'), one.key ? h('span', { class: 'mono' }, one.key) : ''],
        [t('agent'), one.agent],
        [t('role'), one.role],
        [t('backend'), one.backend],
        [t('model'), named(one.model)],
        [t('label'), one.label],
        ['pid', one.pid || ''],
        [t('parent'), parent ? parent.name : ''],
        [t('record'), one.record ? h('span', { class: 'mono' }, one.record) : ''],
        [t('start'), at(model, one.start)],
        [t('lasted'), lasted(one.end - one.start)],
        [t('tracks'), String(one.tracks.length)],
        [t('spans'), counted(one.spans)],
      ]),
      h('p', { class: 'row' }, h('button', { type: 'button', class: 'btn small', onclick: act.zoom }, t('Zoom'))),
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
      t('Span'),
      h('p', { class: 'exo-name selectable', 'data-hmz': 'exomyth-span-name' }, said(track.name_[i]) || '—'),
      facts([
        [t('category'), said(track.cat[i])],
        [t('start'), at(model, track.start[i])],
        [t('lasted'), lasted(track.dur[i])],
        [t('model'), named(said(track.model[i]))],
        [t('tokens'), track.in[i] || track.out[i] ? t('{in} in · {out} out', { in: counted(track.in[i]), out: counted(track.out[i]) }) : ''],
        [t('process'), h('button', { type: 'button', class: 'exo-link', onclick: () => act.pick({ process: process.id }) }, process.name)],
        [t('track'), track.name],
        [t('depth'), String(track.depth[i])],
        ['id', h('span', { class: 'mono' }, String(id))],
      ]),
      h('p', { class: 'row' }, h('button', { type: 'button', class: 'btn small', onclick: act.zoom }, t('Zoom'))),
    ),
    section(
      t('Arguments'),
      read.error
        ? problem(read.error)
        : read.args
          ? h('pre', { class: 'block exo-args', 'data-hmz': 'exomyth-args' }, JSON.stringify(read.args, null, 2))
          : h('p', { class: 'loading', role: 'status' }, t('Reading…')),
    ),
  ]
}

/** A stretch of time: how long, and what lies in it. */
export function rangeOf(model, range, act) {
  const held = within(model, range.from, range.to)
  return [
    section(
      t('Range'),
      facts([
        [t('from@@time'), at(model, range.from)],
        [t('to@@time'), at(model, range.to)],
        [t('lasted'), h('span', { 'data-hmz': 'exomyth-range' }, lasted(range.to - range.from))],
        [t('spans'), counted(held.count)],
        [t('tokens'), t('{in} in · {out} out', { in: counted(held.in), out: counted(held.out) })],
      ]),
      h('p', { class: 'row' }, h('button', { type: 'button', class: 'btn small', onclick: act.zoom }, t('Zoom')), h('button', { type: 'button', class: 'btn small quiet', onclick: act.clear }, t('Clear'))),
    ),
    section(t('Categories'), categories(held.categories, model)),
  ]
}
