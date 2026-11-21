// What the runs here have spent, as their epics say: by day, by flow, and how they ended. One
// drawing for two pages of Settings (views/settings.js): `Usage` under `Daemon`, of everything
// the daemon picked ran, whichever folder it was in and where it was in none; and `Usage` under
// `Workspace`, of the folder picked there. The chart is drawn in plain HTML with a table beside
// it, so no figure rests on a colour or on a pointer hovering over it.

import { given, hash, poll } from '../../api.js'
import { stays } from '../../app.js'
import { badge, empty, fill, flowName, h, problem } from '../../dom.js'
import { t } from '../../i18n.js'
import { spentAt } from '../../search-model.js'

/** How far back the page can look, in days. */
const RANGES = [7, 30, 90, 365]

export function draw(holder, query, parts, scope) {
  let days = Number(query.get('days')) || 30
  // The folder picked over the page, under `Workspace`; none under `Daemon`, which is every one's.
  const workspace = scope.workspace
  const range = h('div', { class: 'segmented', role: 'group', 'aria-label': t('How far back') })
  const body = h('div', { class: 'reading', 'data-hmz': 'usage' }, h('p', { class: 'loading', role: 'status' }, t('Reading what the epics spent…')))
  fill(holder, h('div', { class: 'row' }, h('span', { class: 'kicker' }, t('Range')), range), body)

  let stop = () => {}
  const watch = () => {
    stop()
    // What the last range spent stays, plainly on its way out, until this is read.
    if (!body.querySelector('.loading')) body.setAttribute('aria-busy', 'true')
    stays({ ...scope.query, days })
    fill(
      range,
      RANGES.map((one) => {
        const button = h('button', { type: 'button', 'aria-pressed': String(one === days) }, t('{n}d', { n: one }))
        button.addEventListener('click', () => {
          days = one
          watch()
        })
        return button
      }),
    )
    stop = poll('runs.usage', given({ days, workspace }), 30000, (data, error) => draw(data, error), { on: scope.name })
  }

  function draw(data, error) {
    body.removeAttribute('aria-busy')
    if (!data) {
      fill(body, error ? problem(error) : h('p', { class: 'loading' }, t('Reading…')))
      return
    }
    const whole = data.whole
    const top = Math.max(...data.days.map((one) => one.cost), 0)
    const label = t('Cost per day over the last {days} days, the highest {top} dollars', { days: data.days_back, top: top.toFixed(2) })
    fill(
      body,
      error ? problem(error) : null,
      h(
        'section',
        { class: 'panel' },
        h(
          'div',
          { class: 'tiles' },
          tile(t('spent'), whole.money || '$0', t('over {n} epics', { n: whole.runs })),
          tile(t('output tokens'), whole.tokens || '0', ''),
          tile(t('agent time'), whole.worked || '0s', ''),
          h('div', { class: 'tile' }, h('div', { class: 'kicker' }, t('ended')), h('div', { class: 'row' }, Object.entries(data.ended).map(([how, count]) => h('span', {}, badge(how), ' ', count)))),
        ),
      ),
      h(
        'section',
        { class: 'panel' },
        h('header', {}, h('h2', {}, t('Cost by day')), h('span', { class: 'kicker' }, 'UTC')),
        top
          ? [
              h(
                'div',
                { class: 'bars', role: 'img', 'aria-label': label },
                data.days.map((one) =>
                  h('div', {
                    class: ['bar', !one.cost && 'none'],
                    style: { height: `${Math.max(1, (one.cost / top) * 100)}%` },
                    title: t('{day}: {money}, {n} epics, {tokens} output tokens', { day: one.day, money: one.money || '$0', n: one.runs, tokens: one.tokens }),
                  }),
                ),
              ),
              h('div', { class: 'bars-axis', 'aria-hidden': 'true' }, h('span', {}, data.days[0].day), h('span', {}, data.days[data.days.length - 1].day)),
            ]
          : h('p', { class: 'dim' }, t('Nothing spent in this range.')),
        h(
          'details',
          {},
          h('summary', {}, t('Table')),
          h(
            'div',
            { class: 'table-wrap' },
            h(
              'table',
              {},
              h('thead', {}, h('tr', {}, h('th', {}, t('Day')), h('th', { class: 'num' }, t('Epics')), h('th', { class: 'num' }, t('Spent')), h('th', { class: 'num' }, t('Output')))),
              h('tbody', {}, data.days.filter((one) => one.runs).map((one) => h('tr', {}, h('td', { class: 'mono' }, one.day), h('td', { class: 'num' }, one.runs), h('td', { class: 'num' }, one.money), h('td', { class: 'num' }, one.tokens)))),
            ),
          ),
        ),
      ),
      h(
        'section',
        { class: 'panel' },
        h('h2', {}, t('By flow')),
        data.flows.length
          ? h(
              'div',
              { class: 'table-wrap' },
              h(
                'table',
                {},
                h('thead', {}, h('tr', {}, h('th', {}, t('Flow')), h('th', { class: 'num' }, t('Epics')), h('th', { class: 'num' }, t('Spent')), h('th', {}, t('Share')), h('th', { class: 'num' }, t('Output')), h('th', { class: 'num' }, t('Time')))),
                h(
                  'tbody',
                  {},
                  data.flows.map((one) =>
                    h(
                      'tr',
                      {},
                      h('td', {}, // Where Search lists what the row counts: of this folder, where the page is of one.
                      h('a', { href: hash(spentAt(one.flow, workspace)), title: one.flow === 'chat' ? t('chat') : one.flow }, one.flow === 'chat' ? t('chat') : flowName(one.flow))),
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
          : empty(
              t('Nothing ran in this range.'),
              t(' What a chat or an epic spends is counted here as it goes.'),
              h('a', { class: 'btn primary', href: scope.name === 'local' ? '#/new/chat' : `#/@${encodeURIComponent(scope.name)}/new/chat`, 'data-hmz': 'usage-start' }, t('New chat')),
            ),
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
