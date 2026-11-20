// The chip on a chat's box that says which nous answers it: its harness, its model and its
// effort, each by its name (names.js) and told from the next by its colour. On a new chat it
// opens a menu of every nous the harnesses here are known to run, a row a harness and a model,
// with the efforts the model chosen takes beside it and, under More, a typed model and the account
// (Section 3.8.19 of protocol/web.md). A new epic picks the agent of each role of its flow from
// the same chip, in the middle of the page, offering the harnesses that can fill that role alone
// (Section 3.8.8). On a chat begun it says what the chat runs, and changes what the chat's own
// `/model` and `/effort` change (Section 3.6.6.13).

import { hash } from '../api.js'
import { chipNamed } from '../desk.js'
import { fill, h, icon } from '../dom.js'
import { t } from '../i18n.js'
import { effortName, harnessName } from '../names.js'
import { agentChoice, anyCli, offeredTo, readFor } from '../pickers.js'
import { choice, menu, section, submenu } from '../shell.js'
import { agentLabel, modelsNamed, nousSaid, parted, spelled } from './agent.js'

/** How many rows a menu of nous lists before it is searched by typing. */
const MANY = 10

/** The chip itself: what it says, and the mark that it opens. */
function chip(hmz) {
  const said = h('span', { class: 'chip-value nous-said' })
  const button = h('button', { class: 'chip-btn model-chip', type: 'button', 'aria-label': t('Nous'), 'data-hmz': hmz }, said, icon('down'))
  return { said, button }
}

/**
 * Says an agent on its chip: its harness, its model and its effort, a part a span so that each
 * is coloured apart, with a space between so that it reads, and is cut short, as one line; or
 * `none`, what stands there while no agent is picked. `named` is its model as its row of the menu
 * names it, where that says more than the model's name: who routes it.
 */
function say({ said, button }, spec, none = '', named = '') {
  const { harness, model, effort } = nousSaid(spec)
  fill(said, model ? [h('span', { class: 'nous-harness' }, harness), ' ', h('span', { class: 'nous-model' }, named || model), ' ', h('span', { class: 'nous-effort' }, effort)] : none)
  // Said with what it picks, as every chip under a box is: its label alone would hide the nous.
  button.setAttribute('aria-label', chipNamed(t('Nous'), model ? `${harness} ${named || model} ${effort}` : agentLabel(spec)))
  // As `-a` spells it, whole, for whoever points at it.
  button.title = spec
  button.dataset.agent = spec
}

/** A choice of a menu, marked with what it picks. */
function marked(value, made) {
  const el = choice(made)
  el.dataset.value = value
  return el
}

/**
 * A nous as one line of a menu, `Codex - GPT-6.2 Sol`, its model `named` as its row names it
 * (`modelsNamed`): as `-a` spells it where it is pointed at.
 */
function line({ cli, account = '', model, named }, made) {
  const el = marked(model, { label: `${harnessName(cli)} - ${named}`, ...made })
  el.dataset.cli = cli
  el.dataset.tip = spelled({ cli, account, model, effort: '' })
  return el
}

/**
 * Where a model nobody listed is typed, as `-a` takes one: `typing` is told each change of it,
 * and `entered` what it holds as Enter is pressed in it.
 */
function other(hmz, value, { typing = () => {}, entered }) {
  const typed = h('input', { class: 'menu-filter', type: 'text', placeholder: t('Other model'), 'aria-label': t('Model name'), 'data-hmz': hmz, value, spellcheck: 'false', autocomplete: 'off' })
  typed.addEventListener('input', () => typing(typed.value.trim()))
  typed.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || event.isComposing) return
    // The box the chip stands on is not sent by it.
    event.preventDefault()
    entered(typed.value.trim())
  })
  return typed
}

/**
 * Draws a menu's body again under whoever reads it, keeping the keys in it: but not where it is
 * shut, a menu is open beside it, or something is being typed into it.
 */
function redrawn(listed, items) {
  if (!listed || !listed.isConnected || listed.querySelector('.popover.sub') || listed.contains(document.activeElement?.closest('input'))) return
  const held = listed.contains(document.activeElement)
  fill(listed, items())
  if (held) listed.querySelector('button, a')?.focus()
}

/**
 * The rows of a menu that name a nous, in the one part of it that scrolls: what is under them --
 * the effort, and everything else -- stays in reach however many they are.
 */
const rowsOf = (...rows) => h('div', { class: 'nous-list' }, rows)

/**
 * The agent that fills a role, picked from its chip: the one that answers a new chat, or one a
 * flow asks for.
 *
 * @param {string | {name: string, clis: string[]}} role The role it fills: by its name alone, one
 *   any harness here could fill; with `clis`, one only those harnesses can.
 * @param {string} kept What fills it to begin with, as `-a` spells it.
 * @param {() => void} [changed] Told whenever the choice changes.
 * @param {{up?: boolean, align?: 'start' | 'end'}} [where] Where its menu opens: over the chip and
 *   at its end, as under a box, unless said otherwise -- under it, `up: false`, in the middle of a
 *   page.
 * @returns {{node: HTMLElement, value: () => string, open: () => void, leave: () => void}} The
 *   chip; the agent picked, as `-a` spells it, or '' while none is; a way to open its menu; and
 *   what to call once it is left.
 */
export function modelChip(role, kept, changed = () => {}, { up = true, align = 'end' } = {}) {
  const who = typeof role === 'string' ? anyCli(role) : role
  const made = chip('pick-model')
  const { button } = made
  const node = h('span', { class: 'model-pick', 'data-hmz': 'role', 'data-role': who.name }, button)
  /** What picking offers now, the menu's body while it is open, and what its rows are searched for. */
  let offered = null
  let listed = null
  let sought = ''
  const picked = agentChoice(who, kept, (now) => {
    offered = now
    const row = picked.nous().flatMap((group) => group.rows).find((one) => one.chosen)
    say(made, picked.value(), now.asking ? t('Asking…') : t('Pick a nous'), row ? row.named : '')
    button.dataset.value = picked.chosen.model
    redrawn(listed, () => items(shut))
  }, { changed })
  const { chosen } = picked
  const pick = (part) => {
    Object.assign(chosen, part)
    picked.again()
    changed()
  }

  /** Every nous there is to pick, a group a harness; a harness with none known is one row that asks it. */
  function nous(close) {
    // Of the harness chosen, what is being asked and why it failed is said under the list.
    const why = { asking: '', unasked: t('Not asked yet'), empty: t('No models listed') }
    const groups = picked.nous().map((group) => {
      if (group.rows.length) {
        return group.rows.map((one) => {
          const el = line(one, { chosen: one.chosen, act: () => !one.chosen && pick({ cli: one.cli, account: one.account, model: one.model, effort: '' }), close })
          if (one.unlisted) el.dataset.tip = t('{spec} · not listed', { spec: el.dataset.tip })
          return el
        })
      }
      const mine = group.cli === chosen.cli
      // Picking it asks it, and the menu stays to list what it answers.
      const el = marked('', { label: group.name, about: group.state === 'failed' ? (mine ? '' : t('No models: {why}', { why: group.why })) : why[group.state], chosen: mine, act: () => !mine && pick({ cli: group.cli, account: group.account, model: '', effort: '' }), close: () => {} })
      el.dataset.cli = group.cli
      return [el]
    })
    const rows = groups.flat()
    const parts = []
    const none = h('p', { class: 'dim ask-none', role: 'status', hidden: true }, t('No nous matches'))
    const sift = () => {
      const typed = sought.trim().toLowerCase()
      for (const el of rows) el.hidden = Boolean(typed) && !`${el.textContent} ${el.dataset.tip || ''}`.toLowerCase().includes(typed)
      // What parts one harness from the next parts nothing of what is found.
      for (const el of parts) el.hidden = Boolean(typed)
      none.hidden = rows.some((el) => !el.hidden)
    }
    const find = h('input', { class: 'menu-filter', type: 'text', placeholder: t('Find a nous'), 'aria-label': t('Find a nous'), 'data-hmz': 'pick-nous-find', value: sought, spellcheck: 'false', autocomplete: 'off' })
    find.addEventListener('input', () => {
      sought = find.value
      sift()
    })
    const drawn = rowsOf(
      groups.flatMap((group, at) => {
        if (!at) return group
        parts.push(h('hr'))
        return [parts.at(-1), ...group]
      }),
      none,
    )
    if (rows.length <= MANY) {
      sought = ''
      return [drawn]
    }
    sift()
    // The menu opens on the nous chosen, as every menu of a chip does: what is typed there is
    // typed into the field, and the key that goes up from the first row goes to it.
    drawn.addEventListener('keydown', (event) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.isComposing) return
      if (event.key === 'ArrowUp' ? event.target === rows.find((el) => !el.hidden) : event.key.length === 1 && event.key !== ' ') find.focus()
    })
    return [find, drawn]
  }

  function items(close) {
    if (!offered) return [h('p', { class: 'hint', role: 'status' }, t('Reading the nous…'))]
    const typed = other('pick-model-typed', offered.unlisted ? chosen.model : '', {
      typing: (model) => pick({ model, effort: '' }),
      entered: close,
    })
    const account = offered.accounts.find((one) => one.value === chosen.account)
    const refresh = choice({ label: t('Refresh models'), glyph: 'resume', act: picked.refresh, close })
    refresh.disabled = !chosen.cli || offered.asking
    refresh.dataset.hmz = 'pick-refresh'
    // As a chat app's menu of models: a nous a row, then the effort, then everything else of the
    // agent behind one row, `More`.
    return [
      // None installed that could fill it: said, with where an account of one is made under More.
      picked.nous().length ? nous(close) : h('p', { class: 'hint', role: 'status', 'data-hmz': 'pick-none' }, t('No harness installed here can fill it.')),
      offered.asking ? h('p', { class: 'hint', role: 'status' }, t('Asking {name} for models…', { name: harnessName(chosen.cli) })) : offered.failed ? h('p', { class: 'hint' }, t('No models: {why}', { why: offered.failed })) : null,
      offered.efforts.length
        ? [
            h('hr'),
            submenu({
              label: t('Effort'),
              about: effortName(chosen.effort),
              hmz: 'pick-effort',
              items: () => ['', ...offered.efforts].map((one) => marked(one, { label: effortName(one), chosen: one === chosen.effort, act: () => pick({ effort: one }), close })),
            }),
          ]
        : null,
      h('hr'),
      submenu({
        label: t('More'),
        hmz: 'pick-more',
        items: () => [
          typed,
          submenu({
            label: t('Account'),
            about: account ? account.label : t('Local'),
            hmz: 'pick-account',
            items: () => [
              offered.accounts.map((one) => marked(one.value, { label: one.label, chosen: one.value === chosen.account, act: () => one.value !== chosen.account && pick({ account: one.value, model: '', effort: '' }), close })),
              h('hr'),
              choice({ label: t('Add account…'), glyph: 'plus', href: hash('/settings/accounts'), close }),
            ],
          }),
          refresh,
        ],
      }),
    ]
  }

  const shut = menu(
    button,
    (close) => {
      // What was looked for the last time it was open is not looked for still.
      sought = ''
      listed = h('div', { class: 'model-menu' }, items(close))
      return [listed]
    },
    { align, up, label: t('Nous') },
  )
  picked.again()
  return {
    node,
    value: picked.value,
    open: () => button.getAttribute('aria-expanded') === 'true' || button.click(),
    leave: () => {
      shut()
      picked.leave()
    },
  }
}

/**
 * What answers a chat begun, said on its chip. Its menu says the parts of its agent and offers a
 * new chat, where every part is picked. Where the chat's CLI takes `/model` or `/effort` as a line
 * of its own (Section 8.9.5 of protocol/core.md), the menu offers the models its account runs, or
 * the efforts its model takes, and picking one says that line to the chat; nothing else of a chat
 * begun is changed.
 *
 * @param {object} made
 * @param {() => string} made.of The chat's agent now, as `-a` spells it, or '' where none is known.
 * @param {() => string} made.fresh Where a new chat is started beside this one.
 * @param {(name: 'model'|'effort') => boolean} [made.takes] Whether the chat takes that line now.
 * @param {(line: string) => unknown} [made.say] Says a line to the chat.
 * @returns {{node: HTMLElement, again: () => void}} The chip, hidden while no agent is known, and
 *   a way to have it read the agent again.
 */
export function modelFact({ of, fresh, takes = () => false, say: tell = () => {} }) {
  const made = chip('chat-model')
  const { button } = made
  const node = h('span', { class: 'model-pick' }, button)
  const again = () => {
    const spec = of()
    if (button.dataset.agent === spec) return
    node.hidden = !agentLabel(spec)
    say(made, spec)
  }
  const fact = (label, value, mono = false) => h('div', { class: 'model-fact' }, h('span', { class: 'label' }, label), h('span', { class: ['fact-value', mono && 'mono'] }, value))

  function items(close) {
    const spec = of()
    const { cli, account, model, effort } = parted(spec)
    const offered = offeredTo(spec)
    const models = takes('model')
    const typed = other('chat-model-typed', '', {
      entered: (named) => {
        if (named) tell(`/model ${named}`)
        close()
      },
    })
    const others = models && offered ? offered.models.filter((one) => one.value !== model) : []
    const efforts = takes('effort') && offered ? offered.efforts : []
    const [named, ...rest] = modelsNamed([model, ...others.map((one) => one.value)])
    return [
      section(t('Nous')),
      rowsOf(
        line({ cli, account, model, named }, { chosen: true, close }),
        others.map((one, at) => line({ cli, account, model: one.value, named: rest[at] }, { act: () => tell(`/model ${one.value}`), close })),
      ),
      models ? typed : null,
      efforts.length
        ? submenu({
            label: t('Effort'),
            about: effortName(effort),
            hmz: 'chat-effort',
            items: () => efforts.map((one) => marked(one, { label: effortName(one), chosen: one === effort, act: () => one !== effort && tell(`/effort ${one}`), close })),
          })
        : fact(t('Effort'), effortName(effort)),
      fact(t('Account'), account || t('Local'), Boolean(account)),
      h('hr'),
      choice({ label: t('New chat'), about: t('Every part of its agent is picked as a chat starts'), glyph: 'new', href: fresh(), close }),
    ]
  }

  menu(
    button,
    (close) => {
      const listed = h('div', { class: 'model-menu' }, items(close))
      // Read each time it opens, of the daemon shown, and drawn again with what its CLI runs.
      const read = () => redrawn(listed, () => items(close))
      readFor(of()).then(read, read)
      return [listed]
    },
    { align: 'end', up: true, label: t('Nous') },
  )
  again()
  return { node, again }
}
