// The chip that says a nous and picks one, wherever the page does: its harness, its model and its
// effort, each by its name (names.js) and told from the next by its colour. Its menu never lists
// every nous: it offers the virtual nous there are, each by its name, and then a concrete one a
// level at a time (chips/steps.js) -- the harness, the account it runs as, a model that account
// runs and an effort that model takes -- each level offering only what the ones before it allow
// (Section 3.8.19 of protocol/web.md). A new chat picks its agent from it under its box; a new
// epic the agent of each role of its flow, in the middle of the page, from the harnesses that can
// fill that role alone (Section 3.8.8); Ai-chan her nous; and a node of a virtual nous the nous
// it names, as a field of its form (Section 3.11.2.6). On a chat begun it says what the chat
// runs, and carries the chat on with another model or effort of the same harness and account,
// whether or not a host holds it (Section 3.6.6.13).

import { hash } from '../api.js'
import { chipNamed } from '../desk.js'
import { fill, h, icon } from '../dom.js'
import { t } from '../i18n.js'
import { effortName, harnessName, modelName } from '../names.js'
import { agentChoice, anyCli, harnessed, offeredTo, readFor, virtualNous } from '../pickers.js'
import { choice, menu, section } from '../shell.js'
import { agentLabel, modelsNamed, nousSaid, parted, spelled } from './agent.js'
import { stepped } from './steps.js'

/** How many models a level lists before they are searched by typing. */
const MANY = 10

/** The chip itself: what it says, and the mark that it opens; drawn as a field of a form where `field`. */
function chip(hmz, field = false) {
  const said = h('span', { class: 'chip-value nous-said' })
  const button = h('button', { class: ['chip-btn', 'model-chip', field && 'as-field'], type: 'button', 'aria-label': t('Nous'), 'data-hmz': hmz }, said, icon('down'))
  return { said, button }
}

/**
 * Says an agent on its chip: its harness, its model and its effort, a part a span so that each
 * is coloured apart, with a space between so that it reads, and is cut short, as one line; or
 * `none`, what stands there while no agent is picked -- or the name of a virtual nous, which has
 * no parts. `named` is its model as its row of the menu names it, where that says more than the
 * model's name: who routes it.
 */
function say({ said, button }, spec, none = '', named = '') {
  const { harness, model, effort } = nousSaid(spec)
  fill(said, model ? [h('span', { class: 'nous-harness' }, harness), ' ', h('span', { class: 'nous-model' }, named || model), ' ', h('span', { class: 'nous-effort' }, effort)] : none)
  // Said with what it picks, as every chip under a box is: its label alone would hide the nous.
  button.setAttribute('aria-label', chipNamed(t('Nous'), model ? `${harness} ${named || model} ${effort}` : none))
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

/** The rows of a level that scroll: what is under them stays in reach however many they are. */
const rowsOf = (...rows) => h('div', { class: 'nous-list' }, rows)

/**
 * The models of a level, a row each: over more than ten of them, a field that narrows them to
 * what is typed in it, and what is said where nothing is found.
 */
function found(rows, hmz) {
  const none = h('p', { class: 'dim ask-none', role: 'status', hidden: true }, t('No model matches'))
  const drawn = rowsOf(rows, none)
  if (rows.length <= MANY) return [drawn]
  const find = h('input', { class: 'menu-filter', type: 'text', placeholder: t('Find a model'), 'aria-label': t('Find a model'), 'data-hmz': hmz, spellcheck: 'false', autocomplete: 'off' })
  find.addEventListener('input', () => {
    const typed = find.value.trim().toLowerCase()
    for (const el of rows) el.hidden = Boolean(typed) && !`${el.textContent} ${el.dataset.tip || ''}`.toLowerCase().includes(typed)
    none.hidden = rows.some((el) => !el.hidden)
  })
  // The level opens on the model chosen: what is typed there is typed into the field, and the
  // key that goes up from the first row goes to it.
  drawn.addEventListener('keydown', (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.isComposing) return
    if (event.key === 'ArrowUp' ? event.target === rows.find((el) => !el.hidden) : event.key.length === 1 && event.key !== ' ') find.focus()
  })
  return [find, drawn]
}

/**
 * The chip of a nous that is not picked here -- what an Ai-chan conversation was made with --
 * said as one picked is, and opening nothing: `why` is said where it is pointed at.
 *
 * @param {string} spec The nous, as `-a` spells an agent, or by its name.
 * @param {string} why Why it is not picked here.
 * @returns {{node: HTMLElement}}
 */
export function nousSaidChip(spec, why) {
  const made = chip('nous-said')
  say(made, spec, spec)
  made.button.disabled = true
  made.button.removeAttribute('title')
  made.button.dataset.tip = why
  return { node: h('span', { class: 'model-pick' }, made.button) }
}

/**
 * A nous picked from its chip, wherever the page picks one: the agent that answers a new chat,
 * one a flow asks for, Ai-chan's, a node's of a virtual nous. Its menu offers the virtual nous
 * there are, each by its name, and then a concrete one a level at a time: its harness, the
 * account that runs as, a model that account runs and an effort that model takes, a level
 * having no row where it has one choice. A harness picked again starts from what was last
 * picked of it.
 *
 * @param {string | {name: string, clis: string[]}} role The role it fills: by its name alone, one
 *   any harness here could fill; with `clis`, one only those harnesses can.
 * @param {string} kept What fills it to begin with, as `-a` spells it, or a virtual nous's name.
 * @param {() => void} [changed] Told whenever the choice changes.
 * @param {{up?: boolean, align?: 'start' | 'end', field?: boolean, virtual?: () => string[]}} [where]
 *   Where its menu opens: over the chip and at its end, as under a box, unless said otherwise --
 *   under it, `up: false`, in the middle of a page. `field`, for one drawn as a field of a form,
 *   which holds what it was given as it is written until another is picked. `virtual`, the
 *   virtual nous it offers: those of the daemon read, unless said.
 * @returns {{node: HTMLElement, value: () => string, open: () => void, leave: () => void}} The
 *   chip; the nous picked, as `-a` spells it or by its name, or '' while none is; a way to open
 *   its menu; and what to call once it is left.
 */
export function modelChip(role, kept, changed = () => {}, { up = true, align = 'end', field = false, virtual = virtualNous } = {}) {
  const who = typeof role === 'string' ? anyCli(role) : role
  const made = chip('pick-model', field)
  const { button } = made
  const node = h('span', { class: ['model-pick', field && 'as-field'], 'data-hmz': 'role', 'data-role': who.name }, button)
  /** What picking offers now, and the menu's body while it is open. */
  let offered = null
  let body = null
  /** The nous held as it is written, not as its parts are picked: a virtual one, or what a field was given. */
  let named = kept && (field || !kept.includes('/')) ? kept : ''
  const picked = agentChoice(
    who,
    kept.includes('/') ? kept : '',
    (now) => {
      offered = now
      said()
      body?.again()
    },
    { changed: () => named || changed() },
  )
  const { chosen } = picked

  function said() {
    if (named) {
      say(made, named, named)
      button.dataset.value = named
      return
    }
    const row = picked.nous().flatMap((group) => group.rows).find((one) => one.chosen)
    say(made, picked.value(), offered && offered.asking ? t('Asking…') : t('Pick a nous'), row ? row.named : '')
    button.dataset.value = chosen.model
  }

  const pick = (part) => {
    named = ''
    Object.assign(chosen, part)
    picked.again()
    changed()
  }

  /** What a harness with no model listed says of itself. */
  const why = { listed: '', asking: t('Asking…'), unasked: t('Not asked yet'), empty: t('No models listed'), failed: t('No models listed') }

  function levels(close) {
    const groups = picked.nous()
    if (!offered || !groups.length) return []
    const mine = groups.find((one) => one.cli === chosen.cli)
    const row = mine && mine.rows.find((one) => one.chosen)
    const account = offered.accounts.find((one) => one.value === chosen.account)
    return [
      {
        key: 'harness',
        title: t('Harness'),
        said: harnessName(chosen.cli),
        skip: groups.length < 2,
        rows: (to) =>
          groups.map((group) => {
            const held = group.cli === chosen.cli
            const el = marked(group.cli, {
              label: group.name,
              about: group.state === 'failed' ? t('No models: {why}', { why: group.why }) : why[group.state],
              chosen: held,
              act: () => held || pick(harnessed(group.cli)),
              // Its model is picked next: the first it lists stands until one is.
              close: () => to.go('model'),
            })
            el.dataset.cli = group.cli
            return el
          }),
      },
      {
        key: 'account',
        title: t('Account'),
        said: account ? account.label : t('Local'),
        skip: offered.accounts.length < 2,
        rows: (to) => [
          offered.accounts.map((one) => marked(one.value, { label: one.label, chosen: one.value === chosen.account, act: () => one.value !== chosen.account && pick({ account: one.value, model: '', effort: '' }), close: () => to.go('model') })),
          h('hr'),
          choice({ label: t('Add account…'), glyph: 'plus', href: hash('/settings/accounts'), close }),
        ],
      },
      {
        key: 'model',
        title: t('Model'),
        said: row ? row.named : why[mine ? mine.state : 'empty'] || modelName(chosen.model),
        rows: () => {
          const rows = (mine ? mine.rows : []).map((one) => {
            const el = marked(one.model, { label: one.named, chosen: one.chosen, act: () => (named || !one.chosen) && pick({ model: one.model }), close })
            el.dataset.cli = one.cli
            el.dataset.tip = one.unlisted ? t('{spec} · not listed', { spec: one.spec }) : one.spec
            return el
          })
          // Asked again, the level stays to list what it answers.
          const refresh = choice({ label: t('Refresh models'), glyph: 'resume', act: picked.refresh, close: () => {} })
          refresh.disabled = offered.asking
          refresh.dataset.hmz = 'pick-refresh'
          return [
            found(rows, 'pick-model-find'),
            state(),
            other('pick-model-typed', offered.unlisted ? chosen.model : '', { typing: (model) => pick({ model, effort: '' }), entered: close }),
            refresh,
          ]
        },
      },
      {
        key: 'effort',
        title: t('Effort'),
        said: effortName(chosen.effort),
        skip: !offered.efforts.length,
        rows: () => ['', ...offered.efforts].map((one) => marked(one, { label: effortName(one), chosen: one === chosen.effort, act: () => pick({ effort: one }), close })),
      },
    ]
  }

  /** What is said of the harness chosen while it lists no model: that it is being asked, or why it would not say. */
  const state = () =>
    offered.asking ? h('p', { class: 'hint', role: 'status' }, t('Asking {name} for models…', { name: harnessName(chosen.cli) })) : offered.failed ? h('p', { class: 'hint' }, t('No models: {why}', { why: offered.failed })) : null

  /** Over the levels: the virtual nous there are, and what is said while there is nothing to pick from. */
  function head(close) {
    if (!offered) return h('p', { class: 'hint', role: 'status' }, t('Reading the nous…'))
    const names = virtual()
    const some = picked.nous().length > 0
    return [
      names.length
        ? [
            section(t('Virtual')),
            names.map((name) => {
              const el = marked(name, { label: name, chosen: named === name, act: () => ((named = name), said(), changed()), close })
              el.dataset.hmz = 'pick-virtual'
              return el
            }),
            some ? [h('hr'), section(t('Concrete'))] : null,
          ]
        : null,
      // None installed that could fill it: said in the place of its levels.
      some ? null : h('p', { class: 'hint', role: 'status', 'data-hmz': 'pick-none' }, t('No harness installed here can fill it.')),
    ]
  }

  const shut = menu(
    button,
    (close) => {
      body = stepped({ levels: () => levels(close), head: () => head(close), foot: () => (offered && picked.nous().length ? state() : null) })
      return [body.node]
    },
    { align, up, label: t('Nous') },
  )
  if (named) said()
  picked.again()
  return {
    node,
    value: () => named || picked.value(),
    open: () => button.getAttribute('aria-expanded') === 'true' || button.click(),
    leave: () => {
      shut()
      picked.leave()
    },
  }
}

/**
 * What answers a chat begun, said on its chip. Its menu says the parts of its agent, a level a
 * line as a new chat's picks them, and offers a new chat, where every part is picked. Its
 * harness and its account are said and not picked: a chat is carried on by the harness that had
 * it, as the account it ran as. Its model and its effort are picked, whether or not a host holds
 * the chat, from the models that account runs and the efforts the model takes (Section 8.3.18 of
 * protocol/core.md): one picked is said on the chip at once and asked of the daemon, and where
 * the daemon refuses it the chip says what the chat runs again, and why is told.
 *
 * @param {object} made
 * @param {() => string} made.of The chat's agent now, as `-a` spells it, or '' where none is known.
 * @param {() => string} made.fresh Where a new chat is started beside this one.
 * @param {(agent: string) => unknown} [made.set] Carries the chat on with that agent, of its own
 *   harness and account; without it, nothing of the chat is picked.
 * @param {(error: Error) => void} [made.failed] Told why an agent picked was refused.
 * @param {() => boolean} [made.sure] Whether what `of` says is the daemon's word: while it is
 *   only what the page kept of the chat (Section 3.6.12.4 of protocol/web.md), its parts are
 *   said and none is picked, so that nothing is carried on from an agent it no longer runs.
 * @returns {{node: HTMLElement, again: () => void}} The chip, hidden while no agent is known, and
 *   a way to have it read the agent again.
 */
export function modelFact({ of, fresh, set = null, failed = () => {}, sure = () => true }) {
  const made = chip('chat-model')
  const { button } = made
  const node = h('span', { class: 'model-pick' }, button)
  /** The agent picked and not yet read back of the chat, and what the chat said it ran as it was picked. */
  let picked = ''
  let from = ''
  /** The menu's body while it is open. */
  let body = null
  /** Whether its parts were picked of as it was last drawn. */
  let pickable = null
  const now = () => picked || of()
  const again = () => {
    // Read again since it was picked: what the chat says now is what it runs.
    if (picked && of() !== from) picked = ''
    const spec = now()
    const may = Boolean(set) && sure()
    if (button.dataset.agent === spec && pickable === may) return
    pickable = may
    node.hidden = !agentLabel(spec)
    say(made, spec)
    body?.again()
  }

  /** Carries the chat on with what is picked of it: said at once, and unsaid where it is refused. */
  function pick(part) {
    const was = parted(now())
    const next = { ...was, ...part }
    // An effort the model picked does not take is not carried to it.
    const takes = part.model !== undefined && next.effort && next.effort !== 'auto' ? offeredTo(spelled({ ...next, effort: '' })) : null
    if (takes && !takes.efforts.includes(next.effort)) next.effort = ''
    const agent = spelled(next)
    if (!agent || agent === spelled(was)) return
    from = of()
    picked = agent
    again()
    new Promise((done) => done(set(agent))).catch((error) => {
      if (picked !== agent) return
      picked = ''
      again()
      failed(error)
    })
  }

  function levels(close) {
    const spec = now()
    const { cli, account, model } = parted(spec)
    // No rung at all is written `auto`, and picked as the first of its efforts.
    const effort = parted(spec).effort === 'auto' ? '' : parted(spec).effort
    const may = Boolean(set) && sure()
    const offered = may ? offeredTo(spec) : null
    const ids = [model, ...(offered ? offered.models.map((one) => one.value).filter((one) => one !== model) : [])]
    const names = modelsNamed(ids)
    const efforts = offered ? offered.efforts : []
    return [
      { key: 'harness', title: t('Harness'), said: harnessName(cli), fixed: true },
      { key: 'account', title: t('Account'), said: account || t('Local'), fixed: true },
      {
        key: 'model',
        title: t('Model'),
        said: names[0],
        fixed: !may,
        rows: () => [
          found(
            ids.map((id, at) => {
              const el = marked(id, { label: names[at], chosen: !at, act: () => at && pick({ model: id }), close })
              el.dataset.cli = cli
              el.dataset.tip = spelled({ cli, account, model: id, effort: '' })
              return el
            }),
            'chat-model-find',
          ),
          other('chat-model-typed', '', {
            entered: (named) => {
              if (named) pick({ model: named })
              close()
            },
          }),
        ],
      },
      {
        key: 'effort',
        title: t('Effort'),
        said: effortName(effort),
        fixed: !efforts.length,
        rows: () => ['', ...efforts].map((one) => marked(one, { label: effortName(one), chosen: one === effort, act: () => one !== effort && pick({ effort: one }), close })),
      },
    ]
  }

  menu(
    button,
    (close) => {
      body = stepped({
        levels: () => levels(close),
        foot: () => [h('hr'), choice({ label: t('New chat'), about: t('Every part of its agent is picked as a chat starts'), glyph: 'new', href: fresh(), close })],
      })
      // Read each time it opens, of the daemon shown, and drawn again with what its CLI runs.
      const opened = body
      readFor(of()).then(opened.again, opened.again)
      return [body.node]
    },
    { align: 'end', up: true, label: t('Nous') },
  )
  again()
  return { node, again }
}
