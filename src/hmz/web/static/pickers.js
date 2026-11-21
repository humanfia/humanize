// Choosing who fills a role and where an environment works, a step at a time, as the terminal
// interface's flow menu chooses them: an agent is a CLI that can fill the role, the account it
// runs as, a model that account runs and an effort that model takes; an environment is a
// backend, the runtime of it, and a directory there. Each comes to what `-a` or `-e` spells.

import { call, daemon, hash, onDaemon } from './api.js'
import { nousOffered, offering, parted, spelled } from './chips/agent.js'
import { kindSaid } from './chips/environment.js'
import { fill, h, iconButton } from './dom.js'
import { t } from './i18n.js'
import { effortName, harnessName } from './names.js'
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
/** The virtual nous that daemon has, by their names, as `nous.list` answers them. */
let virtual = []

export async function readBackends(workspace = reading, from = '') {
  reading = workspace
  base = from
  const of = daemon()
  const read = await call('flows.backends', {}, { on: from || undefined })
  // Read of a daemon the page has since left: another's CLIs.
  if (of !== daemon()) return read
  backends = read
  for (const one of told) one()
  // Its virtual nous beside them, which no picker waits for: one that cannot be read offers none.
  call('nous.list', {}, { on: from || undefined }).then(
    (answer) => {
      if (of !== daemon() || base !== from) return
      virtual = answer.nous.filter((one) => one.virtual).map((one) => one.name)
      for (const one of told) one()
    },
    () => {},
  )
  return backends
}

/** The virtual nous of the daemon last read, by their names. */
export const virtualNous = () => virtual

// Another daemon's CLIs and accounts are others.
onDaemon(() => {
  backends = null
  reading = ''
  virtual = []
  asking.clear()
  failed.clear()
})

/** Where the account, the model and the effort last picked of each harness are kept, in this browser. */
const LAST = 'hmz.nous.last'
/** What was last picked of each harness, so that picking it again starts from there. */
const last = (() => {
  try {
    return new Map(Object.entries(JSON.parse(localStorage.getItem(LAST)) || {}))
  } catch {
    return new Map()
  }
})()

/** Keeps what is picked of its harness, for the next time that harness is. */
function note({ cli, account, model, effort }) {
  if (!cli || !model) return
  const was = last.get(cli)
  if (was && was.account === account && was.model === model && was.effort === effort) return
  last.set(cli, { account, model, effort })
  try {
    localStorage.setItem(LAST, JSON.stringify(Object.fromEntries(last)))
  } catch {
    // Kept for as long as the page is, where this browser keeps nothing.
  }
}

/**
 * A harness as picking it starts: the account, the model and the effort last picked of it, each
 * where the harness still has it, else its own sign-in -- or the first account that lists a
 * model -- and no model, which settles on the first listed.
 */
export function harnessed(cli) {
  const accounts = (backends && backends.clis[cli] && backends.clis[cli].accounts) || []
  const was = last.get(cli)
  const held = (was && accounts.find((one) => one.name === was.account)) || accounts.find((one) => !one.name && one.models.length) || accounts.find((one) => one.models.length)
  const account = held ? held.name : ''
  const model = was && held && was.account === account && held.models.some((one) => one.name === was.model) ? was.model : ''
  return { cli, account, model, effort: model ? was.effort : '' }
}

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
    note(chosen)
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

  /** Every nous the role's CLIs are known to run, a group a harness (`nousOffered`). */
  const nous = () => (backends ? nousOffered(chosen, backends.clis, role.clis, asked) : [])

  told.add(read)
  return { chosen, again, refresh, value, nous, leave: () => told.delete(read) }
}

/**
 * The agent filling one role, picked a step at a time, each from a select.
 *
 * @param {{name: string, clis: string[]}} role The role, and the CLIs here that could fill it.
 * @param {string} kept What fills it now, as `-a` spells it.
 * @param {() => void} changed Told whenever the choice changes.
 */
export function agentPicker(role, kept, changed, { effort: withEffort = true } = {}) {
  const cli = h('select', { 'aria-label': t('CLI for {role}', { role: role.name }), 'data-hmz': 'pick-cli' })
  const account = h('select', { 'aria-label': t('Account for {role}', { role: role.name }), 'data-hmz': 'pick-account' })
  const model = h('select', { 'aria-label': t('Model for {role}', { role: role.name }), 'data-hmz': 'pick-model' })
  const effort = h('select', { 'aria-label': t('Effort for {role}', { role: role.name }), 'data-hmz': 'pick-effort' })
  // A model nobody could list is typed instead, as `-a` takes one.
  const typed = h('input', { type: 'text', placeholder: t('Model'), 'aria-label': t('Model name for {role}', { role: role.name }), 'data-hmz': 'pick-model-typed', hidden: true })
  const again = iconButton('resume', t('Refresh models'), { class: 'small' })
  const said = h('span', { class: 'hint', 'aria-live': 'polite' })
  // A place a turn goes to is a CLI, an account and a model: no effort is part of it.
  const node = h('div', { class: 'picker', 'data-hmz': 'agent-picker' }, field(t('CLI'), cli), field(t('Account'), account), field(t('Model'), model, typed), withEffort ? field(t('Effort'), effort) : null, again, said)
  let typing = false

  const picked = agentChoice(role, kept, draw, { effort: withEffort, changed })
  const { chosen } = picked
  const options = (offered, value) => offered.map((one) => h('option', { value: one.value, selected: one.value === value }, one.label))

  function draw(offered) {
    fill(cli, options(offered.clis, chosen.cli))
    fill(account, options(offered.accounts, chosen.account), h('option', { value: '+' }, t('Add account…')))
    const none = offered.asking && !offered.models.length
    fill(
      model,
      none ? h('option', { value: chosen.model }, t('Asking…')) : null,
      options(offered.models, chosen.model),
      offered.unlisted && !none ? h('option', { value: chosen.model, selected: true }, t('{model} (not listed)', { model: chosen.model })) : null,
      !offered.asking ? h('option', { value: '…', selected: typing }, t('Other…')) : null,
    )
    model.disabled = none
    if (offered.typed) typing = true
    model.hidden = typing && !offered.models.length
    typed.hidden = !typing
    if (typing && typed.value !== chosen.model) typed.value = chosen.model
    fill(effort, h('option', { value: '' }, t('Default')), offered.efforts.map((one) => h('option', { value: one, selected: one === chosen.effort }, effortName(one))))
    effort.disabled = !offered.efforts.length
    again.disabled = !chosen.cli || offered.asking
    // One line, cut short where it is long: its tip says the whole of it.
    said.textContent = said.dataset.tip = offered.asking ? t('Asking {harness} for models…', { harness: harnessName(chosen.cli) }) : offered.failed ? t('No models: {why}', { why: offered.failed }) : ''
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
 * @param {{folder?: string}} [how] The folder the epic is started in, which a directory on this
 *   machine left blank comes to: said in that field while nothing is typed in it.
 */
export function envPicker(role, kept, offered, runtimes, { folder = '' } = {}) {
  const chosen = placed(kept)
  const backend = h('select', { 'aria-label': t('Backend for {role}', { role: role.name }), 'data-hmz': 'pick-backend' })
  const machine = h('select', { 'aria-label': t('Runtime for {role}', { role: role.name }), 'data-hmz': 'pick-runtime' })
  const host = h('input', { type: 'text', placeholder: 'user@host', 'aria-label': t('Host for {role}', { role: role.name }), hidden: true })
  // A directory on this machine is browsed for; one on another machine is written.
  const here = pathPicker({ value: chosen.workdir, label: t('Directory for {role}', { role: role.name }), placeholder: folder || '~/project', changed: (to) => (chosen.workdir = to) })
  here.input.dataset.hmz = 'pick-dir'
  const there = h('input', { type: 'text', value: chosen.workdir, placeholder: '/srv/project', 'aria-label': t('Directory for {role} there', { role: role.name }), 'data-hmz': 'pick-dir-there' })
  there.addEventListener('input', () => (chosen.workdir = there.value.trim()))
  const dir = h('span', { class: 'dir-holder' }, here.node, there)
  const node = h('div', { class: 'picker', 'data-hmz': 'env-picker' }, field(t('Backend'), backend), field(t('Runtime'), machine, host), h('div', { class: 'field' }, h('span', { class: 'label' }, t('Directory')), dir))

  function draw() {
    fill(backend, offered.envs.map((one) => h('option', { value: one, selected: one === chosen.backend }, kindSaid(one)[0])))
    const mine = runtimes.filter((one) => one.backend === chosen.backend)
    const local = chosen.backend === 'local'
    machine.closest('.field').hidden = local
    const typedHost = chosen.provider.startsWith('[')
    fill(
      machine,
      mine.map((one) => h('option', { value: one.name, selected: one.name === chosen.provider }, one.name)),
      chosen.backend === 'ssh' ? h('option', { value: '[', selected: typedHost }, t('Other host…')) : null,
      chosen.backend !== 'ssh' ? h('option', { value: '', selected: !chosen.provider }, t('This machine')) : null,
      h('option', { value: '+' }, t('Add runtime…')),
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
