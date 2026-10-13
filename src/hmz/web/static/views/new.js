// A new run, as a new chat opens: the flow picked in the bar as a model is picked, and the task
// typed into the box in the middle. The rest a flow is set up with -- an agent for each role,
// where each environment works, its params, its budget, where it is backed up and whether its flow
// and its environment are profiled -- is under Options on the box, set up as this directory last
// ran that flow, the way `/flow` in the terminal interface sets one up. Picking a run up again is
// the same box, on that run.

import { get, hash, post } from '../api.js'
import { covered, go, stays } from '../app.js'
import { composer } from '../composer.js'
import { acting, fill, h, icon, permitted, problem, secondsOf } from '../dom.js'
import { ask } from '../held.js'
import { agentPicker, envPicker, readBackends } from '../pickers.js'
import { workspacePicker, workspaces } from '../places.js'
import { bar, choice, menu, section } from '../shell.js'

export function mount(root, { query }) {
  const resume = query.get('resume') || ''
  const picker = h('button', { class: 'flow-picker', type: 'button', 'data-hmz': 'flow-picker' }, h('span', {}, 'flow'), h('b', {}, '…'), icon('down'))
  const pickerHolder = h('div', { class: 'menu-holder' }, picker)
  // Where the epic runs: the workspace the address names, or the one an epic picked up ran in.
  let workspace = query.get('workspace') || ''
  const place = workspacePicker(workspace, (path) => {
    workspace = path
    load(query.get('flow') || '')
  })
  const greeting = h('h2', { class: 'greeting' }, resume ? 'Resume epic' : 'What should the agents do?')
  const about = h('p', { class: 'greeting-about' })
  const options = h('div', { class: 'options', id: 'options', hidden: true, 'data-hmz': 'options' })
  const optionsChip = h('button', { class: 'chip-btn', type: 'button', 'aria-expanded': 'false', 'aria-controls': 'options' }, icon('sliders'), h('span', {}, 'Options'))
  const summary = h('span', { class: 'composer-summary' })
  const resumed = h('div', { class: 'resumed' })
  const box = composer({
    placeholder: 'Describe the task',
    label: 'Task',
    tools: [optionsChip, summary],
    empty: true,
    submit: (task) => start(task),
  })
  box.node.dataset.hmz = 'start'
  box.node.classList.add('composer-home')
  optionsChip.addEventListener('click', () => {
    options.hidden = !options.hidden
    optionsChip.setAttribute('aria-expanded', String(!options.hidden))
  })
  fill(
    root,
    h(
      'div',
      { class: 'view view-new' },
      bar({ lead: h('div', { class: 'pickers' }, place.node, pickerHolder) }),
      h('div', { class: 'home' }, h('div', { class: 'home-inner' }, h('div', { class: 'home-mark', 'aria-hidden': 'true' }, h('img', { src: '/mark.svg', alt: '' })), greeting, about, resumed, box.node, options)),
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

  /** Reads what a workspace offers -- its flows, and the one it last set up -- and opens one. */
  async function load(flow) {
    const mine = (loading = workspace || 'here')
    fill(box.said)
    try {
      const ran = resume ? await get(`/api/runs/${encodeURIComponent(resume)}`) : null
      if (mine !== loading) return
      if (ran && !workspace) {
        workspace = ran.workspace
        place.set(workspace)
      }
      if (!workspace) workspace = (await workspaces()).here
      const [found, installed, saved, settings] = await Promise.all([get(`/api/flows?workspace=${encodeURIComponent(workspace)}`), readBackends(workspace), get('/api/runtimes'), get('/api/settings').catch(() => null)])
      if (mine !== loading) return
      flows = found.flows
      backends = installed
      runtimes = saved.runtimes
      // Unread, nothing is picked and the epic goes where the defaults say.
      backup = settings ? settings.backup : { targets: [], defaults: [] }
      // A flow the address names that is not on offer there opens the one it last set up.
      const asked = flows.some((one) => one.name === flow) ? flow : ''
      const wanted = (ran && ran.flow) || asked || found.flow || (flows[0] && flows[0].name) || ''
      if (!wanted) fill(options, problem('No flow is on offer here.'))
      else choose(wanted, ran)
    } catch (error) {
      if (mine === loading) fill(box.said, problem(error))
    }
  }
  load(query.get('flow') || '')

  async function choose(name, ran) {
    choosing = name
    const at = workspace
    run = ran
    // The address of a dialog opened over it is the dialog's own.
    if (!covered()) stays({ workspace, flow: name, resume: ran ? ran.name : '' })
    fill(picker.querySelector('b'), name)
    let read
    try {
      read = await get(`/api/flow?name=${encodeURIComponent(name)}&workspace=${encodeURIComponent(workspace)}`)
    } catch (error) {
      if (choosing === name) fill(box.said, problem(error))
      return
    }
    // Another flow, or another workspace's, was chosen while this one was read.
    if (choosing !== name || at !== workspace) return
    picked = read
    fill(about, picked.description || '')
    fill(resumed, ran ? h('p', { class: 'note' }, `Picks up ${ran.name}, carrying on from where it stopped.`) : null)
    greeting.textContent = ran ? 'Resume epic' : `What should ${name} do?`
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
    const params = schemaForm(flow.params, kept.params || {})
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
      const envsSaid = {}
      for (const [role, one] of Object.entries(places)) if (one.value()) envsSaid[role] = one.value()
      const backupSaid = targets.map((one) => one.firstChild).filter((one) => one.checked).map((one) => one.value)
      // The defaults left as they are go on following the defaults, rather than being kept.
      const followed = kept.backup == null && backupSaid.length === backup.defaults.length && backupSaid.every((one) => backup.defaults.includes(one))
      return { agents: agentsSaid, envs: envsSaid, params: params.read(), budget: budget.read(), profile_flow: profileFlow.checked, profile_environment: profileEnvironment.checked, backup: targets.length && !followed ? backupSaid : undefined }
    }
    for (const one of Object.values(leaving)) one()
    leaving = Object.values(pickers).map((one) => one.leave)
    fill(
      options,
      h('div', { class: 'form' },
        roles.length ? h('section', { class: 'option-group' }, h('h3', {}, 'Agents'), h('div', { class: 'stack' }, roles)) : null,
        rooms.length ? h('section', { class: 'option-group' }, h('h3', {}, 'Environments'), h('div', { class: 'stack' }, rooms)) : null,
        params.fields.length ? h('section', { class: 'option-group' }, h('h3', {}, 'Parameters'), h('div', { class: 'grid' }, params.fields)) : null,
        h('section', { class: 'option-group' }, h('h3', {}, 'Budget'), budget.fields, h('span', { class: 'hint' }, flow.name === 'chat' ? 'Optional for chat.' : 'At least one limit.')),
        targets.length ? h('section', { class: 'option-group', 'data-hmz': 'backup' }, h('h3', {}, 'Backup'), h('div', { class: 'row' }, targets)) : null,
        h('div', { class: 'row' }, h('label', { class: 'check' }, profileFlow, 'Profile flow'), h('label', { class: 'check' }, profileEnvironment, 'Profile environment')),
        // Set up without starting, as `/flow` saves it: what a new epic here opens on.
        h('div', { class: 'row' }, acting('Save', () => post('/api/flows/setup', { workspace, flow: flow.name, ...readAll() }), { kind: 'btn small', busy: 'Saving…', done: 'Saved' })),
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
    await ask(workspace, 'start', { flow: picked.name, task, ...read, resume: run ? run.at : false })
    go(`/live?workspace=${encodeURIComponent(workspace)}`)
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

/** The fields of a budget: what it may cost, how long it may take, and how much it may write. */
function budgetFields(kept, changed) {
  const cost = h('input', { type: 'number', min: '0', step: '0.01', value: kept.cost === 'Infinity' ? '' : kept.cost ?? '', placeholder: 'dollars', 'aria-label': 'Most it may cost, in dollars' })
  const minutes = h('input', { type: 'number', min: '0', step: '1', value: minutesOf(kept.duration), placeholder: 'minutes', 'aria-label': 'Longest it may take, in minutes' })
  const tokens = h('input', { type: 'number', min: '0', step: '1000', value: kept.output_tokens ?? '', placeholder: 'output tokens', 'aria-label': 'Most output tokens it may write' })
  const graceful = h('input', { type: 'checkbox', checked: kept.graceful !== false })
  for (const one of [cost, minutes, tokens]) one.addEventListener('input', changed)
  return {
    fields: h(
      'div',
      { class: 'row' },
      h('label', { class: 'field' }, h('span', { class: 'label' }, 'Cost, $'), cost),
      h('label', { class: 'field' }, h('span', { class: 'label' }, 'Time, min'), minutes),
      h('label', { class: 'field' }, h('span', { class: 'label' }, 'Output tokens'), tokens),
      h('label', { class: 'check' }, graceful, 'Graceful'),
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
      said.graceful = graceful.checked
      return said
    },
  }
}

/** A duration a budget kept, as seconds or as ISO 8601, in whole minutes. */
function minutesOf(duration) {
  const seconds = secondsOf(duration)
  return seconds === null ? '' : String(Math.round(seconds / 60))
}

/**
 * A form for a flow's params, read off the JSON schema its params model gives: a field for
 * each, by its type, and JSON for whatever has no field of its own.
 */
function schemaForm(schema, kept) {
  const fields = []
  const readers = {}
  for (const [name, property] of Object.entries(schema.properties || {})) {
    const value = name in kept ? kept[name] : property.default
    const id = `param-${name}`
    let input
    let read
    const kind = typeOf(property)
    if (property.enum) {
      input = h('select', { id }, property.enum.map((one) => h('option', { value: JSON.stringify(one), selected: one === value }, String(one))))
      read = () => JSON.parse(input.value)
    } else if (kind === 'boolean') {
      input = h('input', { id, type: 'checkbox', checked: Boolean(value) })
      read = () => input.checked
    } else if (kind === 'integer' || kind === 'number') {
      input = h('input', { id, type: 'number', step: kind === 'integer' ? '1' : 'any', value: value ?? '', min: property.minimum, max: property.maximum })
      read = () => (input.value === '' ? null : Number(input.value))
    } else if (kind === 'string') {
      input = (value || '').length > 60 ? h('textarea', { id, rows: '3' }, value || '') : h('input', { id, type: 'text', value: value ?? '' })
      read = () => input.value
    } else {
      input = h('textarea', { id, rows: '3', class: 'mono' }, value === undefined ? '' : JSON.stringify(value, null, 2))
      read = () => {
        if (!input.value.trim()) return null
        try {
          return JSON.parse(input.value)
        } catch {
          throw new Error(`${name} is not JSON.`)
        }
      }
    }
    readers[name] = read
    fields.push(h('div', { class: 'field' }, h('label', { for: id }, name), input, property.description ? h('span', { class: 'hint' }, property.description) : null))
  }
  return {
    fields,
    read() {
      const said = {}
      for (const [name, read] of Object.entries(readers)) {
        const value = read()
        if (value !== null && value !== '') said[name] = value
      }
      return said
    },
  }
}

function typeOf(property) {
  if (property.type) return Array.isArray(property.type) ? property.type.find((one) => one !== 'null') : property.type
  const branches = property.anyOf || property.oneOf || []
  const found = branches.find((one) => one.type && one.type !== 'null')
  return found ? found.type : ''
}
