// Exomyth's slices: every name the spans of the stretch shown go by, with what they came to,
// sorted by any column. A row picked lights its frames in the Flame, and is shown on the
// Timeline on asking.

import { h } from '../../dom.js'
import { counted, lasted } from './model.js'

/** How many rows are drawn, the rest said as a count. */
const ROWS = 200

/** The columns: a key, its heading, how a value of it is said, and whether it is a number. */
const COLUMNS = [
  ['name', 'Name', String, false],
  ['cat', 'Category', String, false],
  ['count', 'Count', counted, true],
  ['total', 'Total', lasted, true],
  ['self', 'Self', lasted, true],
  ['avg', 'Avg', lasted, true],
  ['p50', 'P50', lasted, true],
  ['p95', 'P95', lasted, true],
  ['max', 'Max', lasted, true],
  ['in', 'In', counted, true],
  ['out', 'Out', counted, true],
]

/**
 * The table of slices.
 *
 * @param {{chose: (one: object|null) => void, timeline: (one: object) => void}} told What is
 *   told when a row is picked or let go of, and when one is to be shown on the Timeline.
 */
export function stats(told) {
  let rows = []
  let chosen = null
  let by = 'total'
  let down = true
  const head = h('tr')
  const body = h('tbody')
  const more = h('p', { class: 'dim exo-more' })
  const showing = h('button', { type: 'button', class: 'btn small', 'data-hmz': 'exomyth-show', hidden: true, onclick: () => chosen && told.timeline(chosen) }, 'Show in timeline')
  const node = h(
    'section',
    { class: 'exo-stats', 'data-hmz': 'exomyth-stats' },
    h('div', { class: 'exo-stats-head' }, h('h3', {}, 'Slices'), showing),
    h('div', { class: 'table-wrap' }, h('table', { class: 'spending' }, h('thead', {}, head), body)),
    more,
  )

  function sorted() {
    const sign = down ? -1 : 1
    const numeric = COLUMNS.find(([key]) => key === by)[3]
    const value = (one) => (by === 'avg' ? one.total / one.count : one[by])
    rows.sort((a, b) => sign * (numeric ? value(a) - value(b) : String(value(a)).localeCompare(String(value(b)))) || b.total - a.total)
  }

  function drawn() {
    head.replaceChildren(
      ...COLUMNS.map(([key, heading, , numeric]) =>
        h(
          'th',
          { class: numeric ? 'num' : null, 'aria-sort': key === by ? (down ? 'descending' : 'ascending') : 'none' },
          h(
            'button',
            {
              type: 'button',
              class: 'exo-sort',
              'data-sort': key,
              onclick: () => {
                down = key === by ? !down : numeric
                by = key
                sorted()
                drawn()
              },
            },
            heading,
            key === by ? (down ? ' ↓' : ' ↑') : '',
          ),
        ),
      ),
    )
    body.replaceChildren(
      ...rows.slice(0, ROWS).map((one) =>
        h(
          'tr',
          {
            class: ['exo-row', one === chosen && 'chosen'],
            'aria-selected': String(one === chosen),
            onclick: () => {
              chosen = one === chosen ? null : one
              showing.hidden = !chosen
              told.chose(chosen)
              drawn()
            },
          },
          COLUMNS.map(([key, , say, numeric]) =>
            h('td', { class: numeric ? 'num' : null }, key === 'cat' ? [h('i', { class: `exo-key exo-${one.cat}`, 'aria-hidden': 'true' }), one.cat] : say(key === 'avg' ? one.total / one.count : one[key])),
          ),
        ),
      ),
    )
    more.textContent = rows.length > ROWS ? `${counted(ROWS)} of ${counted(rows.length)}` : ''
  }

  return {
    node,
    /** Shows the slices of what is summed, the one picked kept picked. */
    shown(named, picked) {
      rows = named.slice()
      chosen = picked
      showing.hidden = !chosen
      sorted()
      drawn()
    },
  }
}
