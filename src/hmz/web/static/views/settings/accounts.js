// The accounts an agent can be run as: each a named set of credentials for one CLI, kept apart
// from the CLI's own and from each other, and listed by the names of what it sets -- never by
// a value, since this is drawn where somebody can read it. A page makes one out of a way in
// that is answers alone; a way that runs the CLI's own sign-in needs a terminal.

import { get, post } from '../../api.js'
import { acting, ago, confirming, fill, h, problem } from '../../dom.js'

export function draw(holder) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'accounts' })
  const making = h('section', { class: 'panel', 'data-hmz': 'make-account' })
  fill(
    holder,
    h('p', { class: 'dim' }, 'An agent is given an account where it is set up, as -a spells it: ', h('code', {}, 'cli@account/model'), '. What changes here is what an agent’s next session runs as.'),
    listing,
    making,
  )
  let data = null
  const shown = (answer) => {
    data = answer
    drawListing()
  }

  function drawListing() {
    const rows = data.accounts.map((one) =>
      h(
        'tr',
        { 'data-hmz': 'account' },
        h('td', { class: 'mono' }, one.cli),
        h('td', {}, h('b', {}, one.name || 'this machine’s own'), h('div', { class: 'dim' }, one.name ? `made by ${one.way}` : 'signed in outside humanize')),
        h('td', {}, one.sets.length ? h('div', { class: 'row' }, one.sets.map((name) => h('span', { class: 'chip mono' }, name))) : h('span', { class: 'dim' }, 'nothing')),
        h('td', {}, one.models.length ? h('span', { title: one.models.join('\n') }, `${one.models.length} model${one.models.length === 1 ? '' : 's'}`) : h('span', { class: 'dim' }, 'none known'), one.asked ? h('div', { class: 'dim' }, `asked ${ago(one.asked)}`) : null),
        h(
          'td',
          {},
          h(
            'div',
            { class: 'row' },
            acting('Ask again', async () => shown(await post('/api/accounts/models', { cli: one.cli, name: one.name })), { kind: 'btn small quiet', busy: 'Asking…' }),
            one.serves.length ? copying(one) : null,
            one.name
              ? confirming({
                  label: 'Remove',
                  ask: `Remove ${one.cli}@${one.name}, credentials and all?`,
                  yes: 'Remove it',
                  small: true,
                  act: async () => shown(await post('/api/accounts/remove', { cli: one.cli, name: one.name })),
                })
              : null,
          ),
        ),
      ),
    )
    fill(
      listing,
      h('h2', {}, 'Accounts'),
      rows.length
        ? h(
            'div',
            { class: 'table-wrap' },
            h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'CLI'), h('th', {}, 'Account'), h('th', {}, 'Sets'), h('th', {}, 'Runs'), h('th', {}, ''))), h('tbody', {}, rows)),
          )
        : h('p', { class: 'dim' }, 'Nobody has made an account yet: every agent runs as this machine’s own sign-in.'),
    )
  }

  /** Writes one account down for another CLI its credentials could run. */
  function copying(one) {
    const into = h('select', { 'aria-label': `Copy ${one.cli}@${one.name} to` }, one.serves.map((cli) => h('option', { value: cli }, cli)))
    return h(
      'span',
      { class: 'row' },
      into,
      acting('Copy', async () => shown(await post('/api/accounts/copy', { cli: one.cli, name: one.name, into: into.value })), { kind: 'btn small quiet', busy: 'Copying…' }),
    )
  }

  function drawMaking() {
    const cli = h('select', { 'aria-label': 'CLI', id: 'account-cli' }, data.backends.map((one) => h('option', { value: one.cli }, one.cli)))
    const way = h('select', { 'aria-label': 'Way in', id: 'account-way' })
    const name = h('input', { type: 'text', id: 'account-name', placeholder: 'work', required: true, autocomplete: 'off' })
    const about = h('p', { class: 'hint' })
    const answers = h('div', { class: 'form' })
    const said = h('div', { 'aria-live': 'polite' })
    const make = h('button', { class: 'btn primary', type: 'submit' }, 'Make it')
    const form = h(
      'form',
      { class: 'form' },
      h('div', { class: 'row' }, h('div', { class: 'field' }, h('label', { for: 'account-cli' }, 'cli'), cli), h('div', { class: 'field' }, h('label', { for: 'account-way' }, 'way in'), way), h('div', { class: 'field' }, h('label', { for: 'account-name' }, 'name'), name)),
      about,
      answers,
      h('div', { class: 'row' }, make, said),
    )
    const ways = () => data.backends.find((one) => one.cli === cli.value)?.ways || []
    const picked = () => ways().find((one) => one.name === way.value)
    const drawWays = () => {
      fill(way, ways().map((one) => h('option', { value: one.name }, one.terminal ? `${one.name} (at a terminal)` : one.name)))
      const first = ways().find((one) => !one.terminal)
      if (first) way.value = first.name
      drawAnswers()
    }
    const drawAnswers = () => {
      const chosen = picked()
      fill(said)
      if (!chosen) {
        fill(about)
        fill(answers)
        return
      }
      fill(about, chosen.about)
      make.disabled = chosen.terminal
      if (chosen.terminal) {
        fill(answers, h('p', { class: 'note' }, `${chosen.name} runs ${cli.value}’s own sign-in, which needs a terminal: make it from `, h('code', {}, '/settings'), ' in ', h('code', {}, 'hmz'), '.'))
        return
      }
      fill(
        answers,
        chosen.asks.map((one) =>
          h(
            'div',
            { class: 'field' },
            h('label', { for: `answer-${one.env}` }, one.env),
            h('input', { id: `answer-${one.env}`, 'data-env': one.env, type: one.secret ? 'password' : 'text', placeholder: one.fixed || '', autocomplete: 'off', required: !one.fixed }),
            h('span', { class: 'hint' }, one.about, one.fixed ? ` Left empty, it is ${one.fixed}.` : ''),
          ),
        ),
        chosen.asks.length ? null : h('p', { class: 'dim' }, 'It asks nothing: what it sets is all it is.'),
      )
    }
    cli.addEventListener('change', drawWays)
    way.addEventListener('change', drawAnswers)
    form.addEventListener('submit', async (event) => {
      event.preventDefault()
      fill(said)
      const given = {}
      for (const input of answers.querySelectorAll('input[data-env]')) if (input.value) given[input.dataset.env] = input.value
      make.disabled = true
      try {
        shown(await post('/api/accounts', { cli: cli.value, name: name.value.trim(), way: way.value, answers: given }))
        fill(said, h('span', { class: 'dim', role: 'status' }, `Made ${cli.value}@${name.value.trim()}.`))
        name.value = ''
        for (const input of answers.querySelectorAll('input')) input.value = ''
      } catch (error) {
        fill(said, problem(error))
      } finally {
        make.disabled = Boolean(picked()?.terminal)
      }
    })
    fill(making, h('h2', {}, 'Make an account'), form)
    drawWays()
  }

  get('/api/accounts')
    .then((answer) => {
      shown(answer)
      drawMaking()
    })
    .catch((error) => fill(listing, problem(error)))
}
