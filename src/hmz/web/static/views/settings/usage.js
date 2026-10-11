// What the runs here have spent, as their epics say: by day, by flow, and how they ended. The
// chart is drawn in plain HTML with a table beside it, so no figure rests on a colour or on a
// pointer hovering over it.

import { address, poll } from '../../api.js'
import { stays } from '../../app.js'
import { badge, fill, flowName, h, problem } from '../../dom.js'

/** How far back the page can look, in days. */
const RANGES = [7, 30, 90, 365]

export function draw(holder, query) {
  let days = Number(query.get('days')) || 30
  const range = h('div', { class: 'segmented', role: 'group', 'aria-label': 'How far back' })
  const body = h('div', { 'data-hmz': 'usage' }, h('p', { class: 'loading', role: 'status' }, 'Reading what the epics spent…'))
  fill(holder, h('div', { class: 'row' }, h('span', { class: 'dim' }, 'Range'), range), body)

  let stop = () => {}
  const watch = () => {
    stop()
    stays({ days })
    fill(
      range,
      RANGES.map((one) => {
        const button = h('button', { type: 'button', 'aria-pressed': String(one === days) }, `${one}d`)
        button.addEventListener('click', () => {
          days = one
          watch()
        })
        return button
      }),
    )
    stop = poll(address('/api/usage', { days }), 30000, (data, error) => draw(data, error))
  }

  function draw(data, error) {
    if (!data) {
      fill(body, error ? problem(error) : h('p', { class: 'loading' }, 'Reading…'))
      return
    }
    const whole = data.whole
    const top = Math.max(...data.days.map((one) => one.cost), 0)
    const label = `Cost per day over the last ${data.days_back} days, the highest ${top.toFixed(2)} dollars`
    fill(
      body,
      error ? problem(error) : null,
      h(
        'section',
        { class: 'panel' },
        h(
          'div',
          { class: 'tiles' },
          tile('spent', whole.money || '$0', `over ${whole.runs} epic${whole.runs === 1 ? '' : 's'}`),
          tile('output tokens', whole.tokens || '0', ''),
          tile('agent time', whole.worked || '0s', ''),
          h('div', { class: 'tile' }, h('div', { class: 'kicker' }, 'ended'), h('div', { class: 'row' }, Object.entries(data.ended).map(([how, count]) => h('span', {}, badge(how), ' ', count)))),
        ),
      ),
      h(
        'section',
        { class: 'panel' },
        h('header', {}, h('h2', {}, 'Cost by day'), h('span', { class: 'kicker' }, 'UTC')),
        top
          ? [
              h(
                'div',
                { class: 'bars', role: 'img', 'aria-label': label },
                data.days.map((one) =>
                  h('div', {
                    class: ['bar', !one.cost && 'none'],
                    style: { height: `${Math.max(1, (one.cost / top) * 100)}%` },
                    title: `${one.day}: ${one.money || '$0'}, ${one.runs} epic${one.runs === 1 ? '' : 's'}, ${one.tokens} output tokens`,
                  }),
                ),
              ),
              h('div', { class: 'bars-axis', 'aria-hidden': 'true' }, h('span', {}, data.days[0].day), h('span', {}, data.days[data.days.length - 1].day)),
            ]
          : h('p', { class: 'dim' }, 'No epic here spent any money in these days.'),
        h(
          'details',
          {},
          h('summary', {}, 'Table'),
          h(
            'div',
            { class: 'table-wrap' },
            h(
              'table',
              {},
              h('thead', {}, h('tr', {}, h('th', {}, 'Day'), h('th', { class: 'num' }, 'Epics'), h('th', { class: 'num' }, 'Spent'), h('th', { class: 'num' }, 'Output'))),
              h('tbody', {}, data.days.filter((one) => one.runs).map((one) => h('tr', {}, h('td', { class: 'mono' }, one.day), h('td', { class: 'num' }, one.runs), h('td', { class: 'num' }, one.money), h('td', { class: 'num' }, one.tokens)))),
            ),
          ),
        ),
      ),
      h(
        'section',
        { class: 'panel' },
        h('h2', {}, 'By flow'),
        data.flows.length
          ? h(
              'div',
              { class: 'table-wrap' },
              h(
                'table',
                {},
                h('thead', {}, h('tr', {}, h('th', {}, 'Flow'), h('th', { class: 'num' }, 'Epics'), h('th', { class: 'num' }, 'Spent'), h('th', {}, 'Share'), h('th', { class: 'num' }, 'Output'), h('th', { class: 'num' }, 'Time'))),
                h(
                  'tbody',
                  {},
                  data.flows.map((one) =>
                    h(
                      'tr',
                      {},
                      h('td', {}, h('a', { href: `#/search?flow=${encodeURIComponent(one.flow)}`, title: one.flow }, flowName(one.flow))),
                      h('td', { class: 'num' }, one.runs),
                      h('td', { class: 'num' }, one.money),
                      h('td', {}, h('div', { class: 'share', title: share(one.cost, whole.cost) }, h('span', { style: { width: share(one.cost, whole.cost) } }))),
                      h('td', { class: 'num' }, one.tokens),
                      h('td', { class: 'num' }, one.worked),
                    ),
                  ),
                ),
              ),
            )
          : h('p', { class: 'dim' }, 'No epic in this range.'),
      ),
    )
  }

  watch()
  return () => stop()
}

function share(part, whole) {
  return `${whole ? Math.round((part / whole) * 100) : 0}%`
}

function tile(label, value, sub) {
  return h('div', { class: 'tile' }, h('div', { class: 'kicker' }, label), h('div', { class: 'value' }, value), sub ? h('div', { class: 'sub' }, sub) : null)
}
