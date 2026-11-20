// The accounts an agent can be run as: each a named set of credentials for one CLI, kept apart
// from the CLI's own and from each other, and listed by the names of what it sets -- never by
// a value, since this is drawn where somebody can read it. A page makes one out of a way in
// that is answers alone; a way that runs the CLI's own sign-in needs a terminal. The ways in
// through the local LiteLLM gateway are listed last, under a group of their own -- and where the
// extra they need is missing, the group says so and the line that adds it is said under it.

import { ago, empty, fill, h, iconButton, problem } from '../../dom.js'
import { t } from '../../i18n.js'
import { closed, opened, place } from '../../layers.js'
import { harnessName } from '../../names.js'
import { menuButton, menuOn, toast } from '../../ui.js'

export function draw(holder, query, parts, scope) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'accounts' }, h('p', { class: 'loading', role: 'status' }, 'Reading the accounts…'))
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

  /** Does what a menu picked of an account, saying so in a toast until it is done, then how it went. */
  const doing = (said, method, params, done) => {
    toast(said, 0)
    scope.call(method, params).then(
      (answer) => {
        shown(answer)
        toast(done)
      },
      (error) => toast(error.message, 4000),
    )
  }

  /**
   * What is done with an account less often than it is corrected, behind `More options` and on
   * a right click: what its CLI runs asked again, it written down for another CLI its
   * credentials could run, and it removed.
   */
  const more = (one, button) => [
    { label: 'Refresh models', glyph: 'resume', act: () => doing('Asking…', 'accounts.models', { cli: one.cli, name: one.name }, 'Models refreshed') },
    ...one.serves.map((cli) => ({ label: `Copy to ${harnessName(cli)}`, glyph: 'copy', act: () => doing('Copying…', 'accounts.copy', { cli: one.cli, name: one.name, into: cli }, `Copied to ${harnessName(cli)}`) })),
    one.name ? '-' : null,
    one.name ? { label: 'Remove', glyph: 'trash', danger: true, act: () => removing(one, button) } : null,
  ]

  /**
   * Asks whether an account is removed, by `More options`, as a button that asks before it
   * does what cannot be undone asks by itself (dom.js): the row stays as it is, the answer
   * that takes the question back has the focus, and whatever closes a menu takes it back too.
   */
  function removing(one, button) {
    const ask = `Remove ${harnessName(one.cli)} · ${one.name}, credentials and all?`
    const no = h('button', { class: 'btn quiet small', type: 'button' }, 'Cancel')
    const yes = h('button', { class: 'btn small danger', type: 'button' }, 'Remove')
    const asked = h('div', { class: 'popover row', role: 'dialog', 'aria-label': ask, 'data-hmz': 'account-removing' }, h('span', {}, ask), no, yes)
    const layer = {
      node: asked,
      anchor: button,
      close() {
        if (!asked.isConnected) return
        closed(layer)
        asked.remove()
      },
    }
    no.addEventListener('click', layer.close)
    yes.addEventListener('click', () => {
      layer.close()
      doing('Removing…', 'accounts.remove', { cli: one.cli, name: one.name }, 'Removed')
    })
    // Before the button, which is laid out as the last of its line.
    button.before(asked)
    opened(layer)
    place(asked, button, { align: 'end' })
    no.focus()
  }

  function drawListing() {
    const rows = data.accounts.map((one) => {
      const button = iconButton('more', 'More options', { 'data-hmz': 'account-menu' })
      const row = h(
        'tr',
        { 'data-hmz': 'account' },
        h('td', { title: one.cli }, harnessName(one.cli)),
        h('td', {}, h('b', {}, one.name || 'Local'), h('div', { class: 'dim' }, one.name ? `made by ${one.way}` : 'signed in outside Humanize')),
        h('td', { 'data-label': 'Sets' }, one.sets.length ? h('div', { class: 'row' }, one.sets.map((name) => h('span', { class: 'chip mono' }, name))) : h('span', { class: 'dim' }, 'nothing')),
        h('td', { 'data-label': 'Models' }, one.models.length ? h('span', { title: one.models.join('\n') }, `${one.models.length} model${one.models.length === 1 ? '' : 's'}`) : h('span', { class: 'dim' }, 'None'), one.asked ? h('div', { class: 'dim' }, `asked ${ago(one.asked)}`) : null),
        // `Edit`, and the rest behind `More options`.
        h('td', {}, h('div', { class: 'row' }, one.name ? h('button', { class: 'btn small quiet', type: 'button', onclick: () => correcting(one) }, 'Edit') : null, button)),
      )
      menuOn(row, () => more(one, button))
      menuButton(button, row)
      return row
    })
    fill(
      listing,
      // Nothing an account holds is ever shown, so nothing of it can be copied elsewhere.
      h('header', {}, h('h2', {}, 'Accounts'), scope.batch(null, { off: 'Secrets stay put' })),
      rows.length
        ? h(
            'div',
            { class: 'table-wrap' },
            h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'CLI'), h('th', {}, 'Account'), h('th', {}, 'Sets'), h('th', {}, 'Models'), h('th', {}, ''))), h('tbody', {}, rows)),
          )
        : empty(
            t('No account yet.'),
            t(' Every agent runs as this machine’s own sign-in until you add one.'),
            h('button', { class: 'btn primary', type: 'button', 'data-hmz': 'account-add', onclick: () => {
              making.scrollIntoView({ behavior: 'smooth', block: 'start' })
              making.querySelector('#account-name')?.focus({ preventScroll: true })
            } }, t('Add account')),
          ),
    )
  }

  /**
   * Corrects one account, as its way in asks it: every answer left blank keeps what it was,
   * since nothing it holds is ever shown back. A way in that runs the CLI's own sign-in is
   * corrected at a terminal, by signing in again.
   */
  function correcting(one) {
    const way = (data.backends.find((each) => each.cli === one.cli)?.ways || []).find((each) => each.name === one.way)
    const said = h('div', { 'aria-live': 'polite' })
    const close = h('button', { class: 'btn quiet', type: 'button', onclick: () => drawMaking() }, 'Cancel')
    if (way && way.terminal) {
      fill(making, h('h2', { title: `${one.cli}@${one.name}` }, `Edit ${harnessName(one.cli)} · ${one.name}`), h('p', { class: 'note' }, `${one.way} runs ${harnessName(one.cli)}’s own sign-in: sign in again from `, h('code', {}, '/settings'), ' in ', h('code', {}, 'hmz'), '.'), close)
      return
    }
    const asks = way ? way.asks : one.sets.map((env) => ({ env, about: '', secret: true, fixed: '' }))
    const save = h('button', { class: 'btn primary', type: 'submit' }, 'Save')
    const form = h(
      'form',
      { class: 'form', 'data-hmz': 'correct-account' },
      asks.map((each) =>
        h(
          'div',
          { class: 'field' },
          h('label', { for: `correct-${each.env}` }, each.env),
          h('input', { id: `correct-${each.env}`, 'data-env': each.env, type: each.secret ? 'password' : 'text', placeholder: 'Unchanged', autocomplete: 'off' }),
          each.about ? h('span', { class: 'hint' }, each.about) : null,
        ),
      ),
      h('div', { class: 'row' }, save, close, said),
    )
    form.addEventListener('submit', async (event) => {
      event.preventDefault()
      const given = {}
      for (const input of form.querySelectorAll('input[data-env]')) if (input.value) given[input.dataset.env] = input.value
      save.disabled = true
      save.textContent = 'Saving…'
      try {
        shown(await scope.call('accounts.correct', { cli: one.cli, name: one.name, answers: given }))
        fill(said, h('span', { class: 'dim', role: 'status' }, 'Saved.'))
        for (const input of form.querySelectorAll('input')) input.value = ''
      } catch (error) {
        fill(said, problem(error))
      } finally {
        save.disabled = false
        save.textContent = 'Save'
      }
    })
    fill(making, h('h2', { title: `${one.cli}@${one.name}` }, `Edit ${harnessName(one.cli)} · ${one.name}`), form)
    making.scrollIntoView({ block: 'nearest' })
  }

  function drawMaking() {
    const cli = h('select', { 'aria-label': 'CLI', id: 'account-cli' }, data.backends.map((one) => h('option', { value: one.cli }, harnessName(one.cli))))
    const way = h('select', { 'aria-label': 'Sign-in method', id: 'account-way' })
    const name = h('input', { type: 'text', id: 'account-name', placeholder: 'work', required: true, autocomplete: 'off' })
    const about = h('p', { class: 'hint' })
    const wants = h('p', { class: 'note', 'data-hmz': 'gateway-wants' })
    const answers = h('div', { class: 'form' })
    const said = h('div', { 'aria-live': 'polite' })
    const make = h('button', { class: 'btn primary', type: 'submit' }, 'Create')
    const form = h(
      'form',
      { class: 'form' },
      h('div', { class: 'row' }, h('div', { class: 'field' }, h('label', { for: 'account-cli' }, 'CLI'), cli), h('div', { class: 'field' }, h('label', { for: 'account-way' }, 'Sign-in method'), way), h('div', { class: 'field' }, h('label', { for: 'account-name' }, 'Name'), name)),
      about,
      wants,
      answers,
      h('div', { class: 'row' }, make, said),
    )
    const backend = () => data.backends.find((one) => one.cli === cli.value)
    const ways = () => backend()?.ways || []
    const picked = () => ways().find((one) => one.name === way.value)
    const option = (one) => h('option', { value: one.name }, one.terminal ? `${one.name} (at a terminal)` : one.name)
    const drawWays = () => {
      const groups = [...new Set(ways().map((one) => one.group).filter(Boolean))]
      const missing = backend()?.wants || ''
      fill(
        way,
        ways()
          .filter((one) => !one.group)
          .map(option),
        groups.map((group) => h('optgroup', { label: group }, ways().filter((one) => one.group === group).map(option))),
        missing ? h('optgroup', { label: data.gateway, disabled: true }, h('option', { value: '' }, 'Not installed')) : null,
      )
      if (missing) fill(wants, `${data.gateway}: `, h('code', {}, missing))
      else fill(wants)
      wants.hidden = !missing
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
      make.textContent = 'Creating…'
      try {
        shown(await scope.call('accounts.create', { cli: cli.value, name: name.value.trim(), way: way.value, answers: given }))
        fill(said, h('span', { class: 'dim', role: 'status' }, `Made ${cli.value}@${name.value.trim()}.`))
        name.value = ''
        for (const input of answers.querySelectorAll('input')) input.value = ''
      } catch (error) {
        fill(said, problem(error))
      } finally {
        make.disabled = Boolean(picked()?.terminal)
        make.textContent = 'Create'
      }
    })
    fill(making, h('h2', {}, 'New account'), form)
    drawWays()
  }

  scope.call('accounts.list')
    .then((answer) => {
      shown(answer)
      drawMaking()
    })
    .catch((error) => fill(listing, problem(error)))
}
