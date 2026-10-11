// Choosing who fills a role and where an environment works, a step at a time, as the terminal
// interface's flow menu chooses them: an agent is a CLI that can fill the role, the account it
// runs as, a model that account runs and an effort that model takes; an environment is a
// backend, the runtime of it, and a directory there. Each comes to what `-a` or `-e` spells.

import { get, post } from './api.js'
import { fill, h, iconButton } from './dom.js'

/** The CLIs here, each with its accounts and the models each runs, shared by every picker. */
let backends = null
const told = new Set()
/** What is being asked of a CLI as an account, so that two roles asking ask once. */
const asking = new Map()
/** Why asking a CLI as an account failed, so that it is said rather than asked again. */
const failed = new Map()

/** Reads the CLIs installed here again, and tells every picker. */
export async function readBackends() {
  backends = await get('/api/backends')
  for (const one of told) one()
  return backends
}

/** Asks a CLI what it runs as an account, once however many pickers ask. */
function ask(cli, account) {
  const key = `${cli}@${account}`
  if (!asking.has(key)) {
    asking.set(
      key,
      post('/api/accounts/models', { cli, name: account })
        .then(() => failed.delete(key))
        .catch((error) => failed.set(key, error.message))
        .finally(() => {
          asking.delete(key)
          return readBackends()
        }),
    )
  }
  return asking.get(key)
}

/** An agent as `-a` spells it, taken apart: `cli[@account]/model[:effort]`. */
export function parted(spec) {
  const said = /^([^@/]+)(?:@([^/]*))?\/(.*)$/.exec(spec || '')
  if (!said) return { cli: '', account: '', model: '', effort: '' }
  const [, cli, account = '', rest] = said
  const colon = rest.lastIndexOf(':')
  return colon < 0 ? { cli, account, model: rest, effort: '' } : { cli, account, model: rest.slice(0, colon), effort: rest.slice(colon + 1) }
}

/** An agent put back together as `-a` spells it. */
export function spelled({ cli, account, model, effort }) {
  if (!cli || !model) return ''
  return `${cli}${account ? `@${account}` : ''}/${model}${effort && effort !== 'auto' ? `:${effort}` : ''}`
}

/**
 * The agent filling one role.
 *
 * @param {{name: string, clis: string[]}} role The role, and the CLIs here that could fill it.
 * @param {string} kept What fills it now, as `-a` spells it.
 * @param {() => void} changed Told whenever the choice changes.
 */
export function agentPicker(role, kept, changed) {
  const chosen = parted(kept)
  const cli = h('select', { 'aria-label': `CLI for ${role.name}`, 'data-hmz': 'pick-cli' })
  const account = h('select', { 'aria-label': `Account for ${role.name}`, 'data-hmz': 'pick-account' })
  const model = h('select', { 'aria-label': `Model for ${role.name}`, 'data-hmz': 'pick-model' })
  const effort = h('select', { 'aria-label': `Effort for ${role.name}`, 'data-hmz': 'pick-effort' })
  // A model nobody could list is typed instead, as `-a` takes one.
  const typed = h('input', { type: 'text', placeholder: 'Model', 'aria-label': `Model name for ${role.name}`, 'data-hmz': 'pick-model-typed', hidden: true })
  const again = iconButton('resume', 'Refresh models', { class: 'small' })
  const said = h('span', { class: 'hint', 'aria-live': 'polite' })
  const node = h('div', { class: 'picker', 'data-hmz': 'agent-picker' }, field('CLI', cli), field('Account', account), field('Model', model, typed), field('Effort', effort), again, said)

  const accountsOf = (name) => (backends && backends.clis[name] ? backends.clis[name].accounts : [])
  let typing = false
  const modelsOf = () => (accountsOf(chosen.cli).find((one) => one.name === chosen.account) || { models: [] }).models

  function draw() {
    if (!backends) return
    const offered = role.clis.length ? role.clis : []
    if (!chosen.cli || (!offered.includes(chosen.cli) && !backends.clis[chosen.cli])) chosen.cli = offered[0] || chosen.cli
    fill(
      cli,
      offered.map((one) => h('option', { value: one, selected: one === chosen.cli }, one)),
      chosen.cli && !offered.includes(chosen.cli) ? h('option', { value: chosen.cli, selected: true }, `${chosen.cli} (not installed)`) : null,
    )
    if (!offered.length && !chosen.cli) fill(cli, h('option', { value: '' }, 'None installed'))
    const accounts = accountsOf(chosen.cli)
    if (!accounts.some((one) => one.name === chosen.account)) chosen.account = ''
    fill(
      account,
      accounts.length ? accounts.map((one) => h('option', { value: one.name, selected: one.name === chosen.account }, one.name || 'Local')) : h('option', { value: '' }, 'Local'),
      h('option', { value: '+' }, 'Add account…'),
    )
    const models = modelsOf()
    const key = `${chosen.cli}@${chosen.account}`
    const waiting = asking.has(key)
    const why = failed.get(key)
    if (!chosen.model && models.length) chosen.model = models[0].name
    fill(
      model,
      waiting && !models.length ? h('option', { value: chosen.model }, 'Asking…') : null,
      models.map((one) => h('option', { value: one.name, selected: one.name === chosen.model }, one.name)),
      chosen.model && !models.some((one) => one.name === chosen.model) && !(waiting && !models.length) ? h('option', { value: chosen.model, selected: true }, `${chosen.model} (not listed)`) : null,
      !waiting ? h('option', { value: '…', selected: typing }, 'Other…') : null,
    )
    model.disabled = waiting && !models.length
    // Typed where nothing could be listed: once asked and told nothing, or refused.
    const asked = (accounts.find((one) => one.name === chosen.account) || {}).asked
    if (!models.length && !waiting && (why || asked)) typing = true
    model.hidden = typing && !models.length
    typed.hidden = !typing
    if (typing && typed.value !== chosen.model) typed.value = chosen.model
    const found = models.find((one) => one.name === chosen.model)
    const efforts = found ? found.efforts : []
    if (chosen.effort && !efforts.includes(chosen.effort)) chosen.effort = ''
    fill(effort, h('option', { value: '' }, 'Default'), efforts.map((one) => h('option', { value: one, selected: one === chosen.effort }, one)))
    effort.disabled = !efforts.length
    again.disabled = !chosen.cli || waiting
    said.textContent = waiting ? `Asking ${chosen.cli} for models…` : why ? `No models: ${why}` : ''
    // A CLI nobody has asked as this account yet is asked now, as the terminal interface asks.
    const held = accounts.find((one) => one.name === chosen.account)
    if (chosen.cli && held && !held.asked && !held.models.length && !waiting && !why) refresh()
  }

  function refresh() {
    failed.delete(`${chosen.cli}@${chosen.account}`)
    ask(chosen.cli, chosen.account)
    draw()
  }

  cli.addEventListener('change', () => {
    Object.assign(chosen, { cli: cli.value, account: '', model: '', effort: '' })
    typing = false
    draw()
    changed()
  })
  account.addEventListener('change', () => {
    if (account.value === '+') {
      account.value = chosen.account
      location.hash = '/settings/accounts'
      return
    }
    Object.assign(chosen, { account: account.value, model: '', effort: '' })
    typing = false
    draw()
    changed()
  })
  model.addEventListener('change', () => {
    typing = model.value === '…'
    Object.assign(chosen, { model: typing ? '' : model.value, effort: '' })
    draw()
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
  again.addEventListener('click', refresh)
  told.add(draw)
  draw()
  return {
    node,
    value: () => spelled(chosen),
    leave: () => told.delete(draw),
  }
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
  const dirs = h('datalist', { id: `dirs-${role.name}` })
  const dir = h('input', { type: 'text', list: dirs.id, value: chosen.workdir, placeholder: '~/project', 'aria-label': `Directory for ${role.name}`, 'data-hmz': 'pick-dir' })
  const node = h('div', { class: 'picker', 'data-hmz': 'env-picker' }, field('Backend', backend), field('Runtime', machine, host), field('Directory', dir), dirs)

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
    dir.placeholder = saved && saved.workdir ? saved.workdir : local ? '~/project' : '/srv/project'
  }

  backend.addEventListener('change', () => {
    Object.assign(chosen, { backend: backend.value, provider: '' })
    draw()
  })
  machine.addEventListener('change', () => {
    if (machine.value === '+') {
      location.hash = '/settings/runtimes'
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
  // A directory on this machine is completed as it is typed, as a shell completes one.
  let typed = null
  dir.addEventListener('input', () => {
    chosen.workdir = dir.value.trim()
    if (chosen.backend !== 'local') return
    clearTimeout(typed)
    typed = setTimeout(async () => {
      try {
        const { paths } = await get(`/api/paths?typed=${encodeURIComponent(dir.value)}`)
        fill(dirs, paths.map((one) => h('option', { value: one })))
      } catch {
        fill(dirs)
      }
    }, 150)
  })
  draw()
  return { node, value: () => where(chosen) }
}

function field(label, ...input) {
  return h('label', { class: 'field' }, h('span', { class: 'label' }, label), input)
}
