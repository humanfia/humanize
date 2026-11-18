// The chip on a chat's box that says which model answers it, as a chat app's does: its name, and
// its effort where one is set. On a new chat it opens a menu of the models the CLI chosen runs as
// the account chosen, with the efforts the model takes beside it and, under More, the CLI and the
// account themselves (Section 3.8.19 of protocol/web.md). On a chat begun it says what the chat
// runs, and changes what the chat's own `/model` and `/effort` change (Section 3.6.6.13).

import { hash } from '../api.js'
import { chipNamed } from '../desk.js'
import { fill, h, icon } from '../dom.js'
import { agentChoice, anyCli, offeredTo, readFor } from '../pickers.js'
import { choice, menu, section, submenu } from '../shell.js'
import { agentLabel, effortName, modelName, parted } from './agent.js'

/** The chip itself: what it says, and the mark that it opens. */
function chip(hmz) {
  const said = h('span', { class: 'chip-value' })
  const button = h('button', { class: 'chip-btn model-chip', type: 'button', 'aria-label': 'Model', 'data-hmz': hmz }, said, icon('down'))
  return { said, button }
}

/** A choice of a menu, marked with what it picks. */
function marked(value, made) {
  const el = choice(made)
  el.dataset.value = value
  return el
}

/** A model as one line of a menu: as a person reads it, its own name said where it is pointed at. */
function line(model, made) {
  const label = modelName(model)
  const el = marked(model, { label, ...made })
  if (label !== model) el.dataset.tip = model
  return el
}

/** A model as a menu names it: as a person reads it, over its own name where that is another. */
function named(model) {
  const label = modelName(model)
  return { label, about: label === model ? '' : model }
}

/**
 * Where a model nobody listed is typed, as `-a` takes one: `typing` is told each change of it,
 * and `entered` what it holds as Enter is pressed in it.
 */
function other(hmz, value, { typing = () => {}, entered }) {
  const typed = h('input', { class: 'menu-filter', type: 'text', placeholder: 'Other model', 'aria-label': 'Model name', 'data-hmz': hmz, value, spellcheck: 'false', autocomplete: 'off' })
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
 * The agent that answers a new chat, picked from its chip.
 *
 * @param {string} name The role it fills.
 * @param {string} kept What fills it to begin with, as `-a` spells it.
 * @param {() => void} [changed] Told whenever the choice changes.
 * @returns {{node: HTMLElement, value: () => string, open: () => void, leave: () => void}} The
 *   chip; the agent picked, as `-a` spells it, or '' while none is; a way to open its menu; and
 *   what to call once it is left.
 */
export function modelChip(name, kept, changed = () => {}) {
  const { said, button } = chip('pick-model')
  const node = h('span', { class: 'model-pick', 'data-hmz': 'role', 'data-role': name }, button)
  /** What picking offers now, and the menu's body while it is open. */
  let offered = null
  let listed = null
  const picked = agentChoice(anyCli(name), kept, (now) => {
    offered = now
    const spec = picked.value()
    said.textContent = agentLabel(spec) || (now.asking ? 'Asking…' : 'Pick a model')
    // Said with what it picks, as every chip under a box is: its label alone would hide the model.
    button.setAttribute('aria-label', chipNamed('Model', agentLabel(spec)))
    button.title = spec
    button.dataset.value = picked.chosen.model
    button.dataset.agent = spec
    redrawn(listed, () => items(shut))
  })
  const { chosen } = picked
  const pick = (part) => {
    Object.assign(chosen, part)
    picked.again()
    changed()
  }

  function items(close) {
    if (!offered) return [h('p', { class: 'hint', role: 'status' }, 'Reading the models…')]
    const none = offered.asking && !offered.models.length
    const typed = other('pick-model-typed', offered.unlisted ? chosen.model : '', {
      typing: (model) => pick({ model, effort: '' }),
      entered: () => {
        close()
        button.focus()
      },
    })
    const account = offered.accounts.find((one) => one.value === chosen.account)
    const refresh = choice({ label: 'Refresh models', glyph: 'resume', act: picked.refresh, close })
    refresh.disabled = !chosen.cli || offered.asking
    refresh.dataset.hmz = 'pick-refresh'
    // As a chat app's menu of models: a model a row, then the effort, then everything else of
    // the agent behind one row, `More`.
    const unlisted = offered.unlisted && !none ? marked(chosen.model, { label: chosen.model, chosen: true, close }) : null
    if (unlisted) unlisted.dataset.tip = 'Not listed'
    return [
      offered.models.map((one) => line(one.value, { chosen: one.value === chosen.model, act: () => pick({ model: one.value, effort: '' }), close })),
      unlisted,
      offered.asking ? h('p', { class: 'hint', role: 'status' }, `Asking ${chosen.cli} for models…`) : offered.failed ? h('p', { class: 'hint' }, `No models: ${offered.failed}`) : null,
      offered.efforts.length
        ? [
            h('hr'),
            submenu({
              label: 'Effort',
              about: effortName(chosen.effort),
              hmz: 'pick-effort',
              items: () => ['', ...offered.efforts].map((one) => marked(one, { label: effortName(one), chosen: one === chosen.effort, act: () => pick({ effort: one }), close })),
            }),
          ]
        : null,
      h('hr'),
      submenu({
        label: 'More',
        hmz: 'pick-more',
        items: () => [
          typed,
          submenu({
            label: 'CLI',
            about: chosen.cli || 'None installed',
            hmz: 'pick-cli',
            items: () => offered.clis.map((one) => marked(one.value, { label: one.label, chosen: one.value === chosen.cli, act: () => one.value !== chosen.cli && pick({ cli: one.value, account: '', model: '', effort: '' }), close })),
          }),
          submenu({
            label: 'Account',
            about: account ? account.label : 'Local',
            hmz: 'pick-account',
            items: () => [
              offered.accounts.map((one) => marked(one.value, { label: one.label, chosen: one.value === chosen.account, act: () => one.value !== chosen.account && pick({ account: one.value, model: '', effort: '' }), close })),
              h('hr'),
              choice({ label: 'Add account…', glyph: 'plus', href: hash('/settings/accounts'), close }),
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
      listed = h('div', { class: 'model-menu' }, items(close))
      return [listed]
    },
    { align: 'end', up: true, label: 'Model' },
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
export function modelFact({ of, fresh, takes = () => false, say = () => {} }) {
  const { said, button } = chip('chat-model')
  const node = h('span', { class: 'model-pick' }, button)
  const again = () => {
    const spec = of()
    if (button.dataset.agent === spec) return
    node.hidden = !agentLabel(spec)
    said.textContent = agentLabel(spec)
    button.title = spec
    button.dataset.agent = spec
  }
  const fact = (label, value) => h('div', { class: 'model-fact' }, h('span', { class: 'label' }, label), h('span', { class: 'mono' }, value))

  function items(close) {
    const spec = of()
    const { cli, account, model, effort } = parted(spec)
    const offered = offeredTo(spec)
    const models = takes('model')
    const typed = other('chat-model-typed', '', {
      entered: (named) => {
        if (named) say(`/model ${named}`)
        close()
      },
    })
    const others = models && offered ? offered.models.filter((one) => one.value !== model) : []
    const efforts = takes('effort') && offered ? offered.efforts : []
    return [
      section('Model'),
      marked(model, { ...named(model), chosen: true, close }),
      others.map((one) => marked(one.value, { ...named(one.value), act: () => say(`/model ${one.value}`), close })),
      models ? typed : null,
      efforts.length
        ? submenu({
            label: 'Effort',
            about: effortName(effort),
            hmz: 'chat-effort',
            items: () => efforts.map((one) => marked(one, { label: effortName(one), chosen: one === effort, act: () => one !== effort && say(`/effort ${one}`), close })),
          })
        : fact('Effort', effortName(effort)),
      fact('CLI', cli),
      fact('Account', account || 'Local'),
      h('hr'),
      choice({ label: 'New chat', about: 'Every part of its agent is picked as a chat starts', glyph: 'new', href: fresh(), close }),
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
    { align: 'end', up: true, label: 'Model' },
  )
  again()
  return { node, again }
}
