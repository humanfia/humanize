// Where a turn goes when the place it runs at cannot take it. A place is `CLI[@ACCOUNT]/MODEL`,
// and a step written against one says how many times over a failed turn is taken again there,
// how long it waits between, and the places that take the turn after, in order.

import { get, post } from '../../api.js'
import { acting, confirming, fill, h, lasting, problem } from '../../dom.js'

export function draw(holder) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'fallbacks' })
  const writing = h('section', { class: 'panel', 'data-hmz': 'write-fallback' })
  const places = h('datalist', { id: 'places' })
  fill(holder, places, listing, writing)
  let data = null
  let editing = null

  const shown = (answer) => {
    data = answer
    fill(places, data.places.map((one) => h('option', { value: one })))
    drawListing()
    drawWriting()
  }

  function drawListing() {
    const rows = data.steps.map((one) =>
      h(
        'tr',
        { 'data-hmz': 'step' },
        h('td', { class: 'mono' }, one.spec),
        h('td', {}, one.tries ? `${one.tries} more ${one.tries === 1 ? 'go' : 'goes'}, ${one.policy}${one.timeout ? `, for at most ${lasting(one.timeout)}` : ''}` : h('span', { class: 'dim' }, 'once')),
        h('td', { class: 'mono' }, one.to.length ? one.to.map((place, index) => h('div', {}, `${index + 1}. ${place}`)) : h('span', { class: 'dim' }, 'nowhere')),
        h(
          'td',
          {},
          h(
            'div',
            { class: 'row' },
            h('button', { class: 'btn small quiet', type: 'button', onclick: () => edit(one) }, 'Change'),
            confirming({ label: 'Clear', ask: `Let ${one.spec} fall back nowhere again?`, yes: 'Clear it', small: true, act: async () => shown(await post('/api/fallbacks/clear', { spec: one.spec })) }),
          ),
        ),
      ),
    )
    fill(
      listing,
      h('h2', {}, 'Steps'),
      rows.length
        ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Place'), h('th', {}, 'Tried'), h('th', {}, 'Then'), h('th', {}, ''))), h('tbody', {}, rows)))
        : h('p', { class: 'dim' }, 'Nothing is written down: a turn that fails, fails where it ran.'),
    )
  }

  function edit(one) {
    editing = one
    drawWriting()
    writing.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function drawWriting() {
    const was = editing || { spec: '', to: [], tries: 0, policy: data.default, timeout: 0 }
    const spec = h('input', { type: 'text', id: 'step-spec', list: 'places', value: was.spec, placeholder: 'claude@work/opus', required: true, autocomplete: 'off' })
    const chain = h('div', { class: 'form' })
    const add = (value = '') => {
      const input = h('input', { type: 'text', list: 'places', value, placeholder: 'another place', 'aria-label': `Place ${chain.childElementCount + 1} to go to` })
      const drop = h('button', { class: 'btn small quiet', type: 'button', onclick: () => line.remove() }, 'Remove')
      const line = h('div', { class: 'row' }, input, drop)
      chain.append(line)
    }
    for (const one of was.to) add(one)
    if (!was.to.length) add()
    const tries = h('input', { type: 'number', id: 'step-tries', min: '0', step: '1', value: String(was.tries) })
    const policy = h(
      'select',
      { id: 'step-policy' },
      data.policies.map((one) => h('option', { value: one.name, selected: one.name === was.policy, title: one.about }, `${one.name} — ${one.about}`)),
    )
    const timeout = h('input', { type: 'number', id: 'step-timeout', min: '0', step: '1', value: String(was.timeout || 0) })
    const said = h('div', { 'aria-live': 'polite' })
    const form = h(
      'form',
      { class: 'form' },
      h('div', { class: 'field' }, h('label', { for: 'step-spec' }, 'place'), spec, h('span', { class: 'hint' }, 'Where the turn runs: CLI[@ACCOUNT]/MODEL.')),
      h('div', { class: 'row' }, h('div', { class: 'field' }, h('label', { for: 'step-tries' }, 'tries again'), tries), h('div', { class: 'field' }, h('label', { for: 'step-policy' }, 'waiting'), policy), h('div', { class: 'field' }, h('label', { for: 'step-timeout' }, 'for at most, seconds'), timeout)),
      h('div', { class: 'field' }, h('span', { class: 'label' }, 'then goes to'), chain, h('div', {}, h('button', { class: 'btn small quiet', type: 'button', onclick: () => add() }, 'Another place'))),
      h(
        'div',
        { class: 'row' },
        acting(
          editing ? 'Write it over' : 'Write it',
          async () => {
            const to = [...chain.querySelectorAll('input')].map((input) => input.value.trim()).filter(Boolean)
            const answer = await post('/api/fallbacks', { spec: spec.value.trim(), to, tries: Number(tries.value || 0), policy: policy.value, timeout: Number(timeout.value || 0) })
            editing = null
            shown(answer)
          },
          { kind: 'btn primary', busy: 'Writing…' },
        ),
        editing ? h('button', { class: 'btn quiet', type: 'button', onclick: () => ((editing = null), drawWriting()) }, 'Write a new one') : null,
        said,
      ),
    )
    form.addEventListener('submit', (event) => event.preventDefault())
    fill(writing, h('h2', {}, editing ? `Change ${editing.spec}` : 'Write a step'), form)
  }

  get('/api/fallbacks')
    .then(shown)
    .catch((error) => fill(listing, problem(error)))
}
