// A new run, as a new chat opens: the flow picked in the bar as a model is picked, and the task
// typed into the box in the middle. The rest a flow is set up with -- an agent for each role,
// where each environment works, its params, its budget and whether it is profiled -- is under
// Options on the box, set up as this directory last ran that flow, the way `/flow` in the
// terminal interface sets one up. Picking a run up again is the same box, on that run.

import { get } from '../api.js'
import { go, stays } from '../app.js'
import { composer } from '../composer.js'
import { fill, h, icon, permitted, problem, secondsOf } from '../dom.js'
import { ask } from '../held.js'
import { bar, choice, menu, section } from '../shell.js'

export function mount(root, { query }) {
  const resume = query.get('resume') || ''
  const picker = h('button', { class: 'flow-picker', type: 'button', 'data-hmz': 'flow-picker' }, h('span', {}, 'flow'), h('b', {}, '…'), icon('down'))
  const pickerHolder = h('div', { class: 'menu-holder' }, picker)
  const greeting = h('h2', { class: 'greeting' }, resume ? 'Pick it up again' : 'What should the agents do?')
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
      bar({ lead: pickerHolder }),
      h('div', { class: 'home' }, h('div', { class: 'home-inner' }, h('div', { class: 'home-mark', 'aria-hidden': 'true' }, h('img', { src: '/mark.svg', alt: '' })), greeting, about, resumed, box.node, options)),
    ),
  )

  let flows = []
  let backends = { installed: {}, installable: {} }
  let picked = null
  let run = null
  let setup = null
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

  Promise.all([get('/api/flows'), get('/api/backends'), resume ? get(`/api/runs/${encodeURIComponent(resume)}`) : null])
    .then(([found, installed, ran]) => {
      flows = found.flows
      backends = installed
      run = ran
      // A flow the address names that is not on offer here opens the one this directory last set up.
      const asked = flows.some((one) => one.name === query.get('flow')) ? query.get('flow') : ''
      const wanted = (ran && ran.flow) || asked || found.flow || (flows[0] && flows[0].name) || ''
      if (!wanted) fill(options, problem('No flow is on offer here.'))
      else choose(wanted, ran)
    })
    .catch((error) => fill(box.said, problem(error)))

  async function choose(name, ran) {
    choosing = name
    run = ran
    stays({ flow: name, resume: ran ? ran.name : '' })
    fill(picker.querySelector('b'), name)
    let read
    try {
      read = await get(`/api/flow?name=${encodeURIComponent(name)}`)
    } catch (error) {
      if (choosing === name) fill(box.said, problem(error))
      return
    }
    if (choosing !== name) return
    picked = read
    fill(about, picked.description || '')
    fill(resumed, ran ? h('p', { class: 'note' }, `Picks up ${ran.name}, carrying on from where it stopped.`) : null)
    greeting.textContent = ran ? 'Pick it up again' : `What should ${name} do?`
    setup = drawOptions(picked, ran)
    if (ran && !box.text.value) {
      box.text.value = ran.task
      box.text.dispatchEvent(new Event('input'))
    }
    summarise()
    box.text.focus()
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
          profile: ran.profile,
        }
      : { ...flow.remembered }
    const agents = flow.agents.filter((one) => !one.auto)
    const envs = flow.envs.filter((one) => !one.auto)
    const roleInputs = {}
    const envInputs = {}
    const specs = h('datalist', { id: 'specs' }, agentSpecs(backends.installed).map((spec) => h('option', { value: spec })))
    const roles = agents.map((role) => {
      const input = h('input', { type: 'text', list: 'specs', value: (kept.agents || {})[role.name] || '', placeholder: 'cli/model:effort', 'aria-label': `Agent for ${role.name}`, required: role.required })
      roleInputs[role.name] = input
      input.addEventListener('input', summarise)
      return h(
        'div',
        { class: 'role', 'data-hmz': 'role' },
        h('h3', {}, role.name, role.harness ? h('span', { class: 'chip' }, role.harness) : null, role.required ? null : h('span', { class: 'dim' }, 'optional')),
        input,
        h('div', { class: 'dim' }, permitted(role.permission), role.skills.length ? ` · skills: ${role.skills.join(', ')}` : ''),
      )
    })
    const places = envs.map((role) => {
      const input = h('input', { type: 'text', value: (kept.envs || {})[role.name] || '', placeholder: 'local/<dir>, ssh@<host>/<dir>, docker/<dir>…', 'aria-label': `Where ${role.name} works`, required: role.required })
      envInputs[role.name] = input
      const wants = [role.cpu && `${role.cpu} cpu`, role.memory && `${Math.ceil(role.memory / 2 ** 30)} GiB memory`, role.gpu && `${role.gpu} gpu`, role.image && `image ${role.image}`].filter(Boolean)
      return h('div', { class: 'role' }, h('h3', {}, role.name, h('span', { class: 'dim' }, wants.join(' · '))), input)
    })
    const params = schemaForm(flow.params, kept.params || {})
    const budget = budgetFields(kept.budget || {}, summarise)
    const profile = h('input', { type: 'checkbox', checked: Boolean(kept.profile) })
    fill(
      options,
      specs,
      h('div', { class: 'form' },
        roles.length ? h('div', { class: 'field' }, h('span', { class: 'label' }, 'agents'), h('div', { class: 'grid' }, roles), h('span', { class: 'hint' }, 'Each as -a spells one: cli, an @account where it runs as one, the model and an effort.')) : null,
        places.length ? h('div', { class: 'field' }, h('span', { class: 'label' }, 'environments'), h('div', { class: 'grid' }, places)) : null,
        params.fields.length ? h('div', { class: 'field' }, h('span', { class: 'label' }, 'params'), h('div', { class: 'grid' }, params.fields)) : null,
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'budget'), budget.fields, h('span', { class: 'hint' }, flow.name === 'chat' ? 'chat runs for as long as you answer it, and needs none.' : 'Every flow but chat needs at least one limit.')),
        h('label', { class: 'check' }, profile, 'Profile the programs its agents start, as well as tracing them'),
      ),
    )
    return {
      summary() {
        const said = Object.entries(roleInputs).map(([role, input]) => `${role}: ${input.value.trim() || '—'}`)
        const limit = budget.said()
        if (limit) said.push(limit)
        return said
      },
      read() {
        const agentsSaid = {}
        for (const [role, input] of Object.entries(roleInputs)) if (input.value.trim()) agentsSaid[role] = input.value.trim()
        const envsSaid = {}
        for (const [role, input] of Object.entries(envInputs)) if (input.value.trim()) envsSaid[role] = input.value.trim()
        return { agents: agentsSaid, envs: envsSaid, params: params.read(), budget: budget.read(), profile: profile.checked }
      },
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
    await ask('start', { flow: picked.name, task, ...read, resume: run ? run.at : false })
    go('/live')
  }
}

/** Every agent there is to pick here, as -a spells one: each model of each CLI, at each effort. */
function agentSpecs(installed) {
  const specs = []
  for (const [cli, models] of Object.entries(installed)) {
    if (!models.length) specs.push(`${cli}/`)
    for (const model of models) {
      if (!model.efforts.length) specs.push(`${cli}/${model.name}`)
      for (const effort of model.efforts) specs.push(`${cli}/${model.name}:${effort}`)
    }
  }
  return specs
}

/** The fields of a budget: what it may cost, how long it may take, and how much it may write. */
function budgetFields(kept, changed) {
  const cost = h('input', { type: 'number', min: '0', step: '0.01', value: kept.cost === 'Infinity' ? '' : kept.cost ?? '', placeholder: 'dollars', 'aria-label': 'Most it may cost, in dollars' })
  const minutes = h('input', { type: 'number', min: '0', step: '1', value: minutesOf(kept.duration), placeholder: 'minutes', 'aria-label': 'Longest it may take, in minutes' })
  const tokens = h('input', { type: 'number', min: '0', step: '1000', value: kept.output_tokens ?? '', placeholder: 'output tokens', 'aria-label': 'Most output tokens it may write' })
  const graceful = h('input', { type: 'checkbox', checked: kept.graceful !== false })
  for (const one of [cost, minutes, tokens]) one.addEventListener('input', changed)
  return {
    fields: h('div', { class: 'row' }, h('span', {}, '$'), cost, minutes, h('span', { class: 'dim' }, 'min'), tokens, h('label', { class: 'check' }, graceful, 'let the last turn finish')),
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
