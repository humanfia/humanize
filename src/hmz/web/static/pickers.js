// Choosing who fills a role and where an environment works, a step at a time, as the terminal
// interface's flow menu chooses them: an agent is a CLI that can fill the role, the account it
// runs as, a model that account runs and an effort that model takes; an environment is a
// backend, the runtime of it, and a directory there. Each comes to what `-a` or `-e` spells.

import { call, daemon, hash, onDaemon } from './api.js'
import { offering, parted, spelled } from './chips/agent.js'
import { fill, h, iconButton } from './dom.js'
import { pathPicker } from './paths.js'

/** The CLIs here, each with its accounts and the models each runs, shared by every picker. */
let backends = null
const told = new Set()
/** What is being asked of a CLI as an account, so that two roles asking ask once. */
const asking = new Map()
/** Why asking a CLI as an account failed, so that it is said rather than asked again. */
const failed = new Map()

/** Reads the CLIs installed again -- as a workspace runs them -- and tells every picker. */
let reading = ''
/** Whose CLIs they are: '' for the daemon the page is on, else its name, as Settings picks. */
let base = ''

export async function readBackends(workspace = reading, from = '') {
  reading = workspace
  base = from
  const of = daemon()
  const read = await call('flows.backends', {}, { on: from || undefined })
  // Read of a daemon the page has since left: another's CLIs.
  if (of !== daemon()) return read
  backends = read
  for (const one of told) one()
  return backends
}

// Another daemon's CLIs and accounts are others.
onDaemon(() => {
  backends = null
  reading = ''
  asking.clear()
  failed.clear()
})

/** Asks a CLI what it runs as an account, once however many pickers ask. */
function ask(cli, account) {
  const key = `${cli}@${account}`
  if (!asking.has(key)) {
    asking.set(
      key,
      call('accounts.models', { cli, name: account }, { on: base || undefined })
        .then(() => failed.delete(key))
        .catch((error) => failed.set(key, error.message))
        .finally(() => {
          asking.delete(key)
          // Read again for every picker, which says a failure to read where it draws.
          return readBackends(reading, base).catch(() => {})
        }),
    )
  }
  return asking.get(key)
}

/**
 * A nous, typed or picked from those there are: every virtual one by its name, then every
 * concrete one, as `nous.list` answers them.
 *
 * @param {string} value What it holds to begin with.
 * @param {{nous: {name: string, virtual: boolean}[], concrete: string[]} | null} nous
 * @param {{label: string, hmz: string, placeholder?: string}} how
 */
export function nousField(value, nous, { label, hmz, placeholder = 'A nous' }) {
  const id = `nous-${Math.random().toString(36).slice(2, 10)}`
  const named = nous ? [...nous.nous.filter((one) => one.virtual).map((one) => one.name), ...nous.concrete] : []
  const offered = h('datalist', { id }, named.map((one) => h('option', { value: one })))
  const input = h('input', { type: 'text', value, list: id, placeholder, 'aria-label': label, 'data-hmz': hmz, spellcheck: 'false', autocomplete: 'off' })
  return { node: h('span', { class: 'nous-field' }, input, offered), input }
}

export { parted, spelled }

/** Whether a CLI is being asked what it runs as an account, `cli@account`, and why asking failed. */
const asked = { waiting: (key) => asking.has(key), why: (key) => failed.get(key) }

/**
 * What the CLIs read here offer an agent as it stands, changing nothing of it: null while none
 * are read, or where its CLI or its account is not one of them.
 */
export function offeredTo(spec) {
  const chosen = parted(spec)
  const { cli, account } = chosen
  if (!backends || !cli) return null
  const offered = offering(chosen, backends.clis, Object.keys(backends.clis), asked)
  return chosen.cli === cli && chosen.account === account ? offered : null
}

/**
 * Reads the CLIs of the daemon shown again for an agent that stands and, where its CLI was never
 * asked what it runs as its account, asks it.
 */
export async function readFor(spec) {
  await readBackends()
  const offered = offeredTo(spec)
  const { cli, account } = parted(spec)
  if (offered && offered.unasked) await ask(cli, account)
}

/** A role any CLI here could fill: an agent no flow asks for, or a place a turn goes to. */
export function anyCli(name) {
  return { name, get clis() { return backends ? Object.keys(backends.clis) : [] } }
}

/** A place a turn goes to, `CLI[@ACCOUNT]/MODEL`, picked a step at a time from every CLI here. */
export function placePicker(kept, label, changed = () => {}) {
  return agentPicker(anyCli(label), kept, changed, { effort: false })
}

/**
 * What is picked to fill one role, with nothing drawn: `chosen` is changed by whoever draws it,
 * who then has it drawn `again`.
 *
 * @param {{name: string, clis: string[]}} role The role, and the CLIs here that could fill it.
 * @param {string} kept What fills it now, as `-a` spells it.
 * @param {(offered: ReturnType<typeof offering>) => void} draw Draws what picking it offers now:
 *   as it is made, whenever the CLIs here are read, and whenever asked `again`.
 * @param {{effort?: boolean, changed?: () => void}} [how] Whether an effort is part of it, and
 *   who is told a choice that reading the CLIs here changed with nobody picking: the first model
 *   an account turned out to run.
 */
export function agentChoice(role, kept, draw, { effort: withEffort = true, changed = () => {} } = {}) {
  const chosen = parted(kept)
  const value = () => spelled(withEffort ? chosen : { ...chosen, effort: '' })

  function again() {
    if (!backends) return
    const offered = offering(chosen, backends.clis, role.clis, asked)
    draw(offered)
    if (offered.unasked) refresh()
  }

  /** Asks the CLI chosen what it runs as the account chosen, again where it was asked before. */
  function refresh() {
    failed.delete(`${chosen.cli}@${chosen.account}`)
    ask(chosen.cli, chosen.account)
    again()
  }

  /** Drawn again as the CLIs here are read, which may settle what nobody picked. */
  function read() {
    const was = value()
    again()
    if (value() !== was) changed()
  }

  told.add(read)
  return { chosen, again, refresh, value, leave: () => told.delete(read) }
}

/**
 * The agent filling one role, picked a step at a time, each from a select.
 *
 * @param {{name: string, clis: string[]}} role The role, and the CLIs here that could fill it.
 * @param {string} kept What fills it now, as `-a` spells it.
 * @param {() => void} changed Told whenever the choice changes.
 */
export function agentPicker(role, kept, changed, { effort: withEffort = true } = {}) {
  const cli = h('select', { 'aria-label': `CLI for ${role.name}`, 'data-hmz': 'pick-cli' })
  const account = h('select', { 'aria-label': `Account for ${role.name}`, 'data-hmz': 'pick-account' })
  const model = h('select', { 'aria-label': `Model for ${role.name}`, 'data-hmz': 'pick-model' })
  const effort = h('select', { 'aria-label': `Effort for ${role.name}`, 'data-hmz': 'pick-effort' })
  // A model nobody could list is typed instead, as `-a` takes one.
  const typed = h('input', { type: 'text', placeholder: 'Model', 'aria-label': `Model name for ${role.name}`, 'data-hmz': 'pick-model-typed', hidden: true })
  const again = iconButton('resume', 'Refresh models', { class: 'small' })
  const said = h('span', { class: 'hint', 'aria-live': 'polite' })
  // A place a turn goes to is a CLI, an account and a model: no effort is part of it.
  const node = h('div', { class: 'picker', 'data-hmz': 'agent-picker' }, field('CLI', cli), field('Account', account), field('Model', model, typed), withEffort ? field('Effort', effort) : null, again, said)
  let typing = false

  const picked = agentChoice(role, kept, draw, { effort: withEffort, changed })
  const { chosen } = picked
  const options = (offered, value) => offered.map((one) => h('option', { value: one.value, selected: one.value === value }, one.label))

  function draw(offered) {
    fill(cli, options(offered.clis, chosen.cli))
    fill(account, options(offered.accounts, chosen.account), h('option', { value: '+' }, 'Add account…'))
    const none = offered.asking && !offered.models.length
    fill(
      model,
      none ? h('option', { value: chosen.model }, 'Asking…') : null,
      options(offered.models, chosen.model),
      offered.unlisted && !none ? h('option', { value: chosen.model, selected: true }, `${chosen.model} (not listed)`) : null,
      !offered.asking ? h('option', { value: '…', selected: typing }, 'Other…') : null,
    )
    model.disabled = none
    if (offered.typed) typing = true
    model.hidden = typing && !offered.models.length
    typed.hidden = !typing
    if (typing && typed.value !== chosen.model) typed.value = chosen.model
    fill(effort, h('option', { value: '' }, 'Default'), offered.efforts.map((one) => h('option', { value: one, selected: one === chosen.effort }, one)))
    effort.disabled = !offered.efforts.length
    again.disabled = !chosen.cli || offered.asking
    said.textContent = offered.asking ? `Asking ${chosen.cli} for models…` : offered.failed ? `No models: ${offered.failed}` : ''
  }

  cli.addEventListener('change', () => {
    Object.assign(chosen, { cli: cli.value, account: '', model: '', effort: '' })
    typing = false
    picked.again()
    changed()
  })
  account.addEventListener('change', () => {
    if (account.value === '+') {
      account.value = chosen.account
      location.hash = hash('/settings/accounts')
      return
    }
    Object.assign(chosen, { account: account.value, model: '', effort: '' })
    typing = false
    picked.again()
    changed()
  })
  model.addEventListener('change', () => {
    typing = model.value === '…'
    Object.assign(chosen, { model: typing ? '' : model.value, effort: '' })
    picked.again()
    if (typing) typed.focus()
    changed()
  })
  typed.addEventListener('input', () => {
    chosen.model = typed.value.trim()
    changed()
  })
  effort.addEventListener('change', () => {
    chosen.effort = effort.value
    changed()
  })
  again.addEventListener('click', picked.refresh)
  picked.again()
  return { node, value: picked.value, leave: picked.leave }
}

/** An environment as `-e` spells it, taken apart: `backend[@provider][/workdir]`. */
export function placed(spec) {
  const said = /^([a-z-]+)(?:@(\[[^\]]*\]|[^/]*))?(?:\/(.*))?$/.exec(spec || '')
  if (!said) return { backend: 'local', provider: '', workdir: '' }
  const [, backend, provider = '', workdir = ''] = said
  return { backend, provider, workdir: workdir && !workdir.startsWith('~') ? `/${workdir}` : workdir }
}

/** An environment put back together as `-e` spells it. */
export function where({ backend, provider, workdir }) {
  if (!backend) return ''
  const at = provider ? `@${provider}` : ''
  const dir = String(workdir || '').replace(/^\/+/, '')
  return workdir ? `${backend}${at}/${dir}` : backend === 'local' ? '' : `${backend}${at}`
}

/**
 * Where one environment works.
 *
 * @param {{name: string}} role The role.
 * @param {string} kept Where it works now, as `-e` spells it.
 * @param {{envs: string[]}} offered The backends there are.
 * @param {{backend: string, name: string, workdir?: string}[]} runtimes The runtimes saved.
 */
export function envPicker(role, kept, offered, runtimes) {
  const chosen = placed(kept)
  const backend = h('select', { 'aria-label': `Backend for ${role.name}`, 'data-hmz': 'pick-backend' })
  const machine = h('select', { 'aria-label': `Runtime for ${role.name}`, 'data-hmz': 'pick-runtime' })
  const host = h('input', { type: 'text', placeholder: 'user@host', 'aria-label': `Host for ${role.name}`, hidden: true })
  // A directory on this machine is browsed for; one on another machine is written.
  const here = pathPicker({ value: chosen.workdir, label: `Directory for ${role.name}`, placeholder: '~/project', changed: (to) => (chosen.workdir = to) })
  here.input.dataset.hmz = 'pick-dir'
  const there = h('input', { type: 'text', value: chosen.workdir, placeholder: '/srv/project', 'aria-label': `Directory for ${role.name} there`, 'data-hmz': 'pick-dir-there' })
  there.addEventListener('input', () => (chosen.workdir = there.value.trim()))
  const dir = h('span', { class: 'dir-holder' }, here.node, there)
  const node = h('div', { class: 'picker', 'data-hmz': 'env-picker' }, field('Backend', backend), field('Runtime', machine, host), h('div', { class: 'field' }, h('span', { class: 'label' }, 'Directory'), dir))

  function draw() {
    fill(backend, offered.envs.map((one) => h('option', { value: one, selected: one === chosen.backend }, one)))
    const mine = runtimes.filter((one) => one.backend === chosen.backend)
    const local = chosen.backend === 'local'
    machine.closest('.field').hidden = local
    const typedHost = chosen.provider.startsWith('[')
    fill(
      machine,
      mine.map((one) => h('option', { value: one.name, selected: one.name === chosen.provider }, one.name)),
      chosen.backend === 'ssh' ? h('option', { value: '[', selected: typedHost }, 'Other host…') : null,
      chosen.backend !== 'ssh' ? h('option', { value: '', selected: !chosen.provider }, 'This machine') : null,
      h('option', { value: '+' }, 'Add runtime…'),
    )
    if (!chosen.provider && mine.length && chosen.backend === 'ssh') chosen.provider = mine[0].name
    host.hidden = !typedHost
    host.value = typedHost ? chosen.provider.slice(1, -1) : ''
    const saved = mine.find((one) => one.name === chosen.provider)
    here.node.hidden = !local
    there.hidden = local
    there.placeholder = saved && saved.workdir ? saved.workdir : '/srv/project'
  }

  backend.addEventListener('change', () => {
    Object.assign(chosen, { backend: backend.value, provider: '' })
    draw()
  })
  machine.addEventListener('change', () => {
    if (machine.value === '+') {
      location.hash = hash('/settings/runtimes')
      draw()
      return
    }
    chosen.provider = machine.value === '[' ? '[]' : machine.value
    draw()
    if (machine.value === '[') host.focus()
  })
  host.addEventListener('input', () => {
    chosen.provider = `[${host.value.trim()}]`
  })
  draw()
  return { node, value: () => where(chosen) }
}

function field(label, ...input) {
  return h('label', { class: 'field' }, h('span', { class: 'label' }, label), input)
}
