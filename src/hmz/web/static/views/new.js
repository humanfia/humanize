// A new epic, in the frame a new chat opens in: `New epic` in the bar with the flow picked beside
// it as a model is picked, what the flow is for said in the middle, and the task typed into the
// box docked at the foot of the page, with where it runs -- the daemon and the folder -- under
// that box at its left, where a chat app keeps them. The rest a flow is set up with -- an agent
// for each role, where each environment works, its params, its budget, where it is backed up and
// whether its flow and its environment are profiled -- is under Options, by the box, set up as
// this directory last ran that flow, the way `/flow` in the terminal interface sets one up.
// Picking a run up again is the same box, on that run. A new epic is of a flow: a new chat is a
// form of its own (views/newchat.js), which the sidebar opens beside this one (Sections 3.8.17
// and 3.8.24 of protocol/web.md).

import { call, given, hash } from '../api.js'
import { covered, go, stays } from '../app.js'
import { environmentChip } from '../chips/environment.js'
import { composer } from '../composer.js'
import { NO_FOLDER } from '../desk.js'
import { acting, fill, h, icon, permitted, problem, secondsOf } from '../dom.js'
import { ask } from '../held.js'
import { paramsForm } from '../asking/form.js'
import { agentPicker, envPicker, readBackends } from '../pickers.js'
import { firstWorkspace, folderFiles, workspacePicker } from '../places.js'
import { bar, choice, menu, section } from '../shell.js'

export function mount(root, { query }) {
  const resume = query.get('resume') || ''
  const picker = h('button', { class: 'flow-picker', type: 'button', 'data-hmz': 'flow-picker' }, h('span', {}, 'flow'), h('b', {}, '…'), icon('down'))
  const pickerHolder = h('div', { class: 'menu-holder' }, picker)
  // Where the epic runs: the workspace the address names, or the one an epic picked up ran in --
  // or none, a directory of its own made as it starts, set up as where `hmz web` started is.
  let scratch = query.get('scratch') === '1'
  let workspace = scratch ? '' : query.get('workspace') || ''
  const place = workspacePicker(scratch ? null : workspace, (path) => {
    scratch = path === null
    workspace = path || ''
    files.clear()
    load(query.get('flow') || '')
  }, { none: true, plain: true })
  // A task names a file as a first message does: `@` completes the paths of the folder picked.
  const files = folderFiles(() => workspace)
  const about = h('p', { class: 'greeting-about' })
  const options = h('div', { class: 'options', id: 'options', hidden: true, 'data-hmz': 'options' })
  const optionsChip = h('button', { class: 'chip-btn desk-chip', type: 'button', 'aria-expanded': 'false', 'aria-controls': 'options' }, icon('sliders'), h('span', {}, 'Options'))
  const summary = h('span', { class: 'composer-summary' })
  const resumed = h('div', { class: 'resumed' })
  const box = composer({
    placeholder: 'Describe the task',
    label: 'Task',
    empty: true,
    busy: 'Starting…',
    submit: (task) => start(task),
    complete: files.complete,
    desk: { add: ['files'], able: () => (workspace ? '' : NO_FOLDER), left: [environmentChip('/new').node, place.node], right: [summary, optionsChip] },
  })
  box.node.dataset.hmz = 'start'
  optionsChip.addEventListener('click', () => {
    options.hidden = !options.hidden
    optionsChip.setAttribute('aria-expanded', String(!options.hidden))
    if (!options.hidden) options.scrollIntoView({ block: 'nearest' })
  })
  const top = bar({ title: resume ? 'Resume epic' : 'New epic' })
  // The flow, beside the heading, as a chat's bar keeps what can be done beside its title.
  top.querySelector('.bar-title').append(h('div', { class: 'pickers' }, pickerHolder))
  fill(
    root,
    h(
      'div',
      { class: 'view view-new view-desk', 'data-hmz': 'new-epic' },
      top,
      h('div', { class: 'desk-body' }, h('div', { class: 'desk-column' }, about, resumed, options)),
      h('div', { class: 'dock desk-dock' }, box.node),
    ),
  )

  let flows = []
  let backends = { clis: {}, installable: {}, envs: ['local'] }
  let runtimes = []
  /** The backup targets there are, and those a new epic goes to. */
  let backup = { targets: [], defaults: [] }
  let picked = null
  let run = null
  let setup = null
  /** What lets go of the pickers drawn last. */
  let leaving = []
  /** Which flow was chosen last: one read after another was chosen draws nothing. */
  let choosing = ''

  menu(
    picker,
    (close) => {
      const whose = {}
      for (const one of flows) (whose[one.whose] ||= []).push(one)
      return Object.entries(whose).map(([from, list]) => [
        section(from),
        list.map((one) => choice({ label: one.name, about: one.about, chosen: picked && picked.name === one.name, act: () => choose(one.name, null), close })),
      ])
    },
    { label: 'Flows' },
  )

  /** Which workspace was read last: one read after another was picked draws nothing. */
  let loading = ''

  /** Says the flow drawn is being read again, rather than leave the last one standing as if current. */
  function reading(on) {
    fill(about, on ? h('span', { class: 'loading', role: 'status' }, 'Reading…') : picked ? picked.description || '' : '')
    options.classList.toggle('stale', on)
    options.toggleAttribute('aria-busy', on)
  }

  /** Reads what a workspace offers -- its flows, and the one it last set up -- and opens one. */
  async function load(flow) {
    const mine = (loading = scratch ? 'none' : workspace || 'here')
    fill(box.said)
    reading(true)
    try {
      const ran = resume ? await call('runs.get', { name: resume }) : null
      if (mine !== loading) return
      if (ran && !workspace) {
        scratch = false
        workspace = ran.workspace
        place.set(workspace)
      }
      if (!workspace) workspace = await firstWorkspace()
      const [found, installed, saved, settings] = await Promise.all([call('flows.list', { workspace }), readBackends(workspace), call('runtimes.list'), call('settings.get').catch(() => null)])
      if (mine !== loading) return
      flows = found.flows
      backends = installed
      runtimes = saved.runtimes
      // Unread, nothing is picked and the epic goes where the defaults say.
      backup = settings ? settings.backup : { targets: [], defaults: [] }
      // A flow the address names that is not on offer there opens the one it last set up.
      const asked = flows.some((one) => one.name === flow) ? flow : ''
      const wanted = (ran && ran.flow) || asked || found.flow || (flows[0] && flows[0].name) || ''
      if (!wanted) {
        reading(false)
        fill(options, problem('No flow is on offer here.'))
      } else choose(wanted, ran)
    } catch (error) {
      if (mine !== loading) return
      reading(false)
      fill(box.said, problem(error))
    }
  }
  load(query.get('flow') || '')

  async function choose(name, ran) {
    choosing = name
    const at = workspace
    run = ran
    // The address of a dialog opened over it is the dialog's own.
    if (!covered()) stays({ workspace: scratch ? '' : workspace, scratch: scratch ? '1' : '', flow: name, resume: ran ? ran.name : '' })
    fill(picker.querySelector('b'), name)
    reading(true)
    let read
    try {
      read = await call('flows.get', { name, workspace })
    } catch (error) {
      if (choosing !== name) return
      reading(false)
      fill(box.said, problem(error))
      return
    }
    // Another flow, or another workspace's, was chosen while this one was read.
    if (choosing !== name || at !== workspace) return
    picked = read
    reading(false)
    fill(resumed, ran ? h('p', { class: 'note' }, `Picks up ${ran.name}, carrying on from where it stopped.`) : null)
    // What the page asked in the middle, asked in the box.
    box.text.placeholder = ran ? 'Describe the task' : `What should ${name} do?`
    setup = drawOptions(picked, ran)
    if (ran && !box.text.value) {
      box.text.value = ran.task
      box.text.dispatchEvent(new Event('input'))
    }
    summarise()
    // Typed into next -- but not from under a dialog opened over it, out of what is typed there.
    if (!covered()) box.text.focus()
  }

  function summarise() {
    if (!setup) return
    const said = setup.summary()
    fill(summary, said.map((one) => h('span', { class: 'chip' }, one)))
  }

  function drawOptions(flow, ran) {
    const kept = ran
      ? {
          agents: Object.fromEntries(ran.agents.map((one) => [one.role, one.runs])),
          envs: Object.fromEntries(ran.envs.map((one) => one.split('=')).map(([role, ...spec]) => [role, spec.join('=')])),
          params: ran.params,
          budget: ran.budget || {},
          profile_flow: ran.profile_flow,
          profile_environment: ran.profile_environment,
        }
      : { ...flow.remembered }
    const agents = flow.agents.filter((one) => !one.auto)
    const envs = flow.envs.filter((one) => !one.auto)
    const pickers = {}
    const places = {}
    const roles = agents.map((role) => {
      pickers[role.name] = agentPicker(role, (kept.agents || {})[role.name] || '', summarise)
      return h(
        'div',
        { class: 'role', 'data-hmz': 'role', 'data-role': role.name },
        h('h3', {}, role.name, role.harness ? h('span', { class: 'chip' }, role.harness) : null, role.required ? null : h('span', { class: 'dim' }, 'Optional')),
        pickers[role.name].node,
        h('div', { class: 'hint' }, permitted(role.permission), role.skills.length ? ` · skills: ${role.skills.join(', ')}` : ''),
      )
    })
    const rooms = envs.map((role) => {
      places[role.name] = envPicker(role, (kept.envs || {})[role.name] || '', backends, runtimes)
      const wants = [role.cpu && `${role.cpu} CPU`, role.memory && `${Math.ceil(role.memory / 2 ** 30)} GiB`, role.gpu && `${role.gpu} GPU`, role.image && role.image].filter(Boolean)
      return h('div', { class: 'role', 'data-hmz': 'env', 'data-role': role.name }, h('h3', {}, role.name, h('span', { class: 'dim' }, wants.join(' · '))), places[role.name].node)
    })
    // The same form a person answers a question with: a field for each param, by its type.
    const params = paramsForm(flow.params, kept.params || {})
    const budget = budgetFields(kept.budget || {}, summarise)
    const profileFlow = h('input', { type: 'checkbox', checked: Boolean(kept.profile_flow), 'data-hmz': 'profile-flow' })
    const profileEnvironment = h('input', { type: 'checkbox', checked: Boolean(kept.profile_environment), 'data-hmz': 'profile-environment' })
    // Where the epic is backed up: as the one picked up was, else as saved, else the defaults.
    const goesTo = ran ? ran.backup : (kept.backup ?? backup.defaults)
    const targets = backup.targets.map((one) => h('label', { class: 'check', title: one.url }, h('input', { type: 'checkbox', value: one.name, checked: goesTo.includes(one.name) }), one.name))
    /** What the flow is set up with, as a start sends it. */
    function readAll() {
      const agentsSaid = {}
      for (const [role, one] of Object.entries(pickers)) if (one.value()) agentsSaid[role] = one.value()
      // Neither saved nor started with a role nobody fills, or with nothing bounding what it spends.
      const unfilled = agents.find((role) => role.required && !agentsSaid[role.name])
      if (unfilled) throw new Error(`Pick an agent for ${unfilled.name}.`)
      const budgetSaid = budget.read()
      if (!budgetSaid) throw new Error('Set at least one limit of the budget.')
      const envsSaid = {}
      for (const [role, one] of Object.entries(places)) if (one.value()) envsSaid[role] = one.value()
      const backupSaid = targets.map((one) => one.firstChild).filter((one) => one.checked).map((one) => one.value)
      // The defaults left as they are go on following the defaults, rather than being kept.
      const followed = kept.backup == null && backupSaid.length === backup.defaults.length && backupSaid.every((one) => backup.defaults.includes(one))
      return { agents: agentsSaid, envs: envsSaid, params: params.read(), budget: budgetSaid, profile_flow: profileFlow.checked, profile_environment: profileEnvironment.checked, backup: targets.length && !followed ? backupSaid : undefined }
    }
    for (const one of Object.values(leaving)) one()
    leaving = Object.values(pickers).map((one) => one.leave)
    fill(
      options,
      h('div', { class: 'form' },
        roles.length ? h('section', { class: 'option-group' }, h('h3', {}, 'Agents'), h('div', { class: 'stack' }, roles)) : null,
        rooms.length ? h('section', { class: 'option-group' }, h('h3', {}, 'Environments'), h('div', { class: 'stack' }, rooms)) : null,
        params.fields.length ? h('section', { class: 'option-group' }, h('h3', {}, 'Parameters'), h('div', { class: 'grid' }, params.fields)) : null,
        h('section', { class: 'option-group' }, h('h3', {}, 'Budget'), budget.fields, h('span', { class: 'hint' }, 'At least one limit.')),
        targets.length ? h('section', { class: 'option-group', 'data-hmz': 'backup' }, h('h3', {}, 'Backup'), h('div', { class: 'row' }, targets)) : null,
        h('div', { class: 'row' }, h('label', { class: 'check' }, profileFlow, 'Profile flow'), h('label', { class: 'check' }, profileEnvironment, 'Profile environment')),
        // Set up without starting, as `/flow` saves it: what a new epic here opens on.
        h('div', { class: 'row' }, acting('Save', () => call('flows.setup', { workspace, flow: flow.name, ...readAll() }), { kind: 'btn small', busy: 'Saving…', done: 'Saved' })),
      ),
    )
    return {
      summary() {
        const said = Object.entries(pickers).map(([role, one]) => `${role}: ${one.value() || '—'}`)
        const limit = budget.said()
        if (limit) said.push(limit)
        return said
      },
      read: readAll,
    }
  }

  async function start(task) {
    if (!picked || !setup) throw new Error('Pick a flow first.')
    let read
    try {
      read = setup.read()
    } catch (error) {
      options.hidden = false
      optionsChip.setAttribute('aria-expanded', 'true')
      throw error
    }
    // The answer says which host the epic went to, which the page follows.
    const started = await ask(workspace, 'start', { flow: picked.name, task, ...read, resume: run ? run.at : false, ...(scratch ? { scratch } : {}) })
    go(`/live?${new URLSearchParams(given({ workspace: started.workspace, slot: started.slot }))}`)
  }

  // Back from making an account or a runtime, the pickers offer it.
  const back = () => {
    if (!location.hash.startsWith(hash('/settings'))) readBackends(workspace).catch(() => {})
  }
  window.addEventListener('hashchange', back)
  return () => {
    // Left, what is still being read draws nothing -- above all, it never puts its flow in the
    // address of the view the page went on to.
    loading = null
    choosing = null
    window.removeEventListener('hashchange', back)
    for (const one of leaving) one()
  }
}

/** The address of a new epic of a kind, `chat` or `flow`, in a workspace -- or in none, `scratch`. */
export function newOf(kind, { workspace = '', scratch = false } = {}) {
  const query = new URLSearchParams(given(scratch ? { scratch: '1' } : { workspace }))
  const text = query.toString()
  return `/new${kind === 'chat' ? '/chat' : ''}${text ? `?${text}` : ''}`
}

/**
 * The fields of a budget: what it may cost, how long it may take, and how much it may write,
 * and for each whether the turn under way when it is reached may finish.
 */
function budgetFields(kept, changed) {
  const cost = h('input', { type: 'number', min: '0', step: '0.01', value: kept.cost === 'Infinity' ? '' : kept.cost ?? '', placeholder: 'dollars', 'aria-label': 'Most it may cost, in dollars' })
  const minutes = h('input', { type: 'number', min: '0', step: '1', value: minutesOf(kept.duration), placeholder: 'minutes', 'aria-label': 'Longest it may take, in minutes' })
  const tokens = h('input', { type: 'number', min: '0', step: '1000', value: kept.output_tokens ?? '', placeholder: 'output tokens', 'aria-label': 'Most output tokens it may write' })
  // Graceful is one flag for every limit, or one apiece; a box apiece either way.
  const graces = Object.fromEntries(
    ['cost', 'duration', 'output_tokens'].map((limit) => [
      limit,
      h('input', { type: 'checkbox', checked: (kept.graceful && typeof kept.graceful === 'object' ? kept.graceful[limit] : kept.graceful) !== false }),
    ]),
  )
  for (const one of [cost, minutes, tokens]) one.addEventListener('input', changed)
  return {
    fields: h(
      'div',
      { class: 'row' },
      h('label', { class: 'field' }, h('span', { class: 'label' }, 'Cost, $'), cost),
      h('label', { class: 'field' }, h('span', { class: 'label' }, 'Time, min'), minutes),
      h('label', { class: 'field' }, h('span', { class: 'label' }, 'Output tokens'), tokens),
      h('label', { class: 'check' }, graces.cost, 'Cost graceful'),
      h('label', { class: 'check' }, graces.duration, 'Time graceful'),
      h('label', { class: 'check' }, graces.output_tokens, 'Tokens graceful'),
    ),
    said() {
      return [cost.value !== '' && `$${cost.value}`, minutes.value !== '' && `${minutes.value} min`, tokens.value !== '' && `${tokens.value} out`].filter(Boolean).join(' · ')
    },
    read() {
      const said = {}
      if (cost.value !== '') said.cost = Number(cost.value)
      if (minutes.value !== '') said.duration = Number(minutes.value) * 60
      if (tokens.value !== '') said.output_tokens = Number(tokens.value)
      if (!Object.keys(said).length) return null
      const flags = Object.fromEntries(Object.entries(graces).map(([limit, box]) => [limit, box.checked]))
      const every = Object.values(flags)
      said.graceful = every.every((one) => one === every[0]) ? every[0] : flags
      return said
    },
  }
}

/** A duration a budget kept, as seconds or as ISO 8601, in whole minutes. */
function minutesOf(duration) {
  const seconds = secondsOf(duration)
  return seconds === null ? '' : String(Math.round(seconds / 60))
}
