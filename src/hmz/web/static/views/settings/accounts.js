// The accounts an agent can be run as: each a named set of credentials for one CLI, kept apart
// from the CLI's own and from each other, and listed by the names of what it sets -- never by
// a value, since this is drawn where somebody can read it. A page makes one out of a way in
// that is answers alone; a way that runs the CLI's own sign-in needs a terminal. The ways in
// through the local LiteLLM gateway are listed last, under a group of their own -- and where the
// extra they need is missing, the group says so and the line that adds it is said under it.

import { ago, empty, fill, h, iconButton, problem } from '../../dom.js'
import { pieces, t } from '../../i18n.js'
import { closed, opened, place } from '../../layers.js'
import { harnessName } from '../../names.js'
import { menuButton, menuOn, toast } from '../../ui.js'
import { signSaid } from './signin.js'

export function draw(holder, query, parts, scope) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'accounts' }, h('p', { class: 'loading', role: 'status' }, t('Reading the accounts…')))
  const making = h('section', { class: 'panel', 'data-hmz': 'make-account' })
  fill(
    holder,
    h('p', { class: 'dim' }, pieces('An agent is given an account where it is set up, as -a spells it: {spec}. What changes here is what an agent’s next session runs as.', { spec: h('code', {}, 'cli@account/model') })),
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
    { label: t('Refresh models'), glyph: 'resume', act: () => doing(t('Asking…'), 'accounts.models', { cli: one.cli, name: one.name }, t('Models refreshed')) },
    ...one.serves.map((cli) => ({ label: t('Copy to {name}', { name: harnessName(cli) }), glyph: 'copy', act: () => doing(t('Copying…'), 'accounts.copy', { cli: one.cli, name: one.name, into: cli }, t('Copied to {name}', { name: harnessName(cli) })) })),
    one.name ? '-' : null,
    one.name ? { label: t('Remove'), glyph: 'trash', danger: true, act: () => removing(one, button) } : null,
  ]

  /**
   * Asks whether an account is removed, by `More options`, as a button that asks before it
   * does what cannot be undone asks by itself (dom.js): the row stays as it is, the answer
   * that takes the question back has the focus, and whatever closes a menu takes it back too.
   */
  function removing(one, button) {
    const ask = t('Remove {cli} · {name}, credentials and all?', { cli: harnessName(one.cli), name: one.name })
    const no = h('button', { class: 'btn quiet small', type: 'button' }, t('Cancel'))
    const yes = h('button', { class: 'btn small danger', type: 'button' }, t('Remove'))
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
      doing(t('Removing…'), 'accounts.remove', { cli: one.cli, name: one.name }, t('Removed'))
    })
    // Before the button, which is laid out as the last of its line.
    button.before(asked)
    opened(layer)
    place(asked, button, { align: 'end' })
    no.focus()
  }

  function drawListing() {
    const rows = data.accounts.map((one) => {
      const button = iconButton('more', t('More options'), { 'data-hmz': 'account-menu' })
      const row = h(
        'tr',
        { 'data-hmz': 'account' },
        h('td', { title: one.cli }, harnessName(one.cli)),
        h('td', {}, h('b', {}, one.name || t('Local')), h('div', { class: 'dim' }, one.name ? t('made by {way}', { way: one.way }) : t('signed in outside Humanize'))),
        h('td', { 'data-label': t('Sets') }, one.sets.length ? h('div', { class: 'row' }, one.sets.map((name) => h('span', { class: 'chip mono' }, name))) : h('span', { class: 'dim' }, t('nothing'))),
        h('td', { 'data-label': t('Models') }, one.models.length ? h('span', { title: one.models.join('\n') }, t('{n} models', { n: one.models.length })) : h('span', { class: 'dim' }, t('None')), one.asked ? h('div', { class: 'dim' }, t('asked {when}', { when: ago(one.asked) })) : null),
        // `Edit`, and the rest behind `More options`.
        h('td', {}, h('div', { class: 'row' }, one.name ? h('button', { class: 'btn small quiet', type: 'button', onclick: () => correcting(one) }, t('Edit')) : null, button)),
      )
      menuOn(row, () => more(one, button))
      menuButton(button, row)
      return row
    })
    fill(
      listing,
      // Nothing an account holds is ever shown, so nothing of it can be copied elsewhere.
      h('header', {}, h('h2', {}, t('Accounts')), scope.batch(null, { off: t('Secrets stay put') })),
      rows.length
        ? h(
            'div',
            { class: 'table-wrap' },
            h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, t('CLI')), h('th', {}, t('Account')), h('th', {}, t('Sets')), h('th', {}, t('Models')), h('th', {}, ''))), h('tbody', {}, rows)),
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
    const close = h('button', { class: 'btn quiet', type: 'button', onclick: () => drawMaking() }, t('Cancel'))
    if (way && way.terminal) {
      fill(making, h('h2', { title: `${one.cli}@${one.name}` }, t('Edit {cli} · {name}', { cli: harnessName(one.cli), name: one.name })), h('p', { class: 'note' }, pieces('{way} runs {cli}’s own sign-in: sign in again from {settings} in {hmz}.', { way: one.way, cli: harnessName(one.cli), settings: h('code', {}, '/settings'), hmz: h('code', {}, 'hmz') })), close)
      return
    }
    const asks = way ? way.asks : one.sets.map((env) => ({ env, about: '', secret: true, fixed: '' }))
    const save = h('button', { class: 'btn primary', type: 'submit' }, t('Save'))
    const form = h(
      'form',
      { class: 'form', 'data-hmz': 'correct-account' },
      asks.map((each) =>
        h(
          'div',
          { class: 'field' },
          h('label', { for: `correct-${each.env}` }, each.env),
          h('input', { id: `correct-${each.env}`, 'data-env': each.env, type: each.secret ? 'password' : 'text', placeholder: t('Unchanged'), autocomplete: 'off' }),
          each.about ? h('span', { class: 'hint' }, signSaid(each.about)) : null,
        ),
      ),
      h('div', { class: 'row' }, save, close, said),
    )
    form.addEventListener('submit', async (event) => {
      event.preventDefault()
      const given = {}
      for (const input of form.querySelectorAll('input[data-env]')) if (input.value) given[input.dataset.env] = input.value
      save.disabled = true
      save.textContent = t('Saving…')
      try {
        shown(await scope.call('accounts.correct', { cli: one.cli, name: one.name, answers: given }))
        fill(said, h('span', { class: 'dim', role: 'status' }, t('Saved.')))
        for (const input of form.querySelectorAll('input')) input.value = ''
      } catch (error) {
        fill(said, problem(error))
      } finally {
        save.disabled = false
        save.textContent = t('Save')
      }
    })
    fill(making, h('h2', { title: `${one.cli}@${one.name}` }, t('Edit {cli} · {name}', { cli: harnessName(one.cli), name: one.name })), form)
    making.scrollIntoView({ block: 'nearest' })
  }

  function drawMaking() {
    const cli = h('select', { 'aria-label': t('CLI'), id: 'account-cli' }, data.backends.map((one) => h('option', { value: one.cli }, harnessName(one.cli))))
    const way = h('select', { 'aria-label': t('Sign-in method'), id: 'account-way' })
    const name = h('input', { type: 'text', id: 'account-name', placeholder: 'work', required: true, autocomplete: 'off' })
    const about = h('p', { class: 'hint' })
    const wants = h('p', { class: 'note', 'data-hmz': 'gateway-wants' })
    const answers = h('div', { class: 'form' })
    const said = h('div', { 'aria-live': 'polite' })
    const make = h('button', { class: 'btn primary', type: 'submit' }, t('Create'))
    const form = h(
      'form',
      { class: 'form' },
      h('div', { class: 'row' }, h('div', { class: 'field' }, h('label', { for: 'account-cli' }, t('CLI')), cli), h('div', { class: 'field' }, h('label', { for: 'account-way' }, t('Sign-in method')), way), h('div', { class: 'field' }, h('label', { for: 'account-name' }, t('Name')), name)),
      about,
      wants,
      answers,
      h('div', { class: 'row' }, make, said),
    )
    const backend = () => data.backends.find((one) => one.cli === cli.value)
    const ways = () => backend()?.ways || []
    const picked = () => ways().find((one) => one.name === way.value)
    const option = (one) => h('option', { value: one.name }, one.terminal ? t('{name} (at a terminal)', { name: one.name }) : one.name)
    const drawWays = () => {
      const groups = [...new Set(ways().map((one) => one.group).filter(Boolean))]
      const missing = backend()?.wants || ''
      fill(
        way,
        ways()
          .filter((one) => !one.group)
          .map(option),
        groups.map((group) => h('optgroup', { label: group }, ways().filter((one) => one.group === group).map(option))),
        missing ? h('optgroup', { label: data.gateway, disabled: true }, h('option', { value: '' }, t('Not installed'))) : null,
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
      fill(about, signSaid(chosen.about))
      make.disabled = chosen.terminal
      if (chosen.terminal) {
        fill(answers, h('p', { class: 'note' }, pieces('{way} runs {cli}’s own sign-in, which needs a terminal: make it from {settings} in {hmz}.', { way: chosen.name, cli: cli.value, settings: h('code', {}, '/settings'), hmz: h('code', {}, 'hmz') })))
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
            h('span', { class: 'hint' }, signSaid(one.about), one.fixed ? t(' Left empty, it is {value}.', { value: one.fixed }) : ''),
          ),
        ),
        chosen.asks.length ? null : h('p', { class: 'dim' }, t('It asks nothing: what it sets is all it is.')),
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
      make.textContent = t('Creating…')
      try {
        shown(await scope.call('accounts.create', { cli: cli.value, name: name.value.trim(), way: way.value, answers: given }))
        fill(said, h('span', { class: 'dim', role: 'status' }, t('Made {account}.', { account: `${cli.value}@${name.value.trim()}` })))
        name.value = ''
        for (const input of answers.querySelectorAll('input')) input.value = ''
      } catch (error) {
        fill(said, problem(error))
      } finally {
        make.disabled = Boolean(picked()?.terminal)
        make.textContent = t('Create')
      }
    })
    fill(making, h('h2', {}, t('New account')), form)
    drawWays()
  }

  scope.call('accounts.list')
    .then((answer) => {
      shown(answer)
      drawMaking()
    })
    .catch((error) => fill(listing, problem(error)))
}
