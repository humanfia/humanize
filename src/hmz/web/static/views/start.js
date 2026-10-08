// Starting a run: which flow, on what, with which agent in each of its roles, its params, and
// what it may spend -- set up as this directory last ran it, the way `/flow` in the terminal
// interface sets one up. Picking a run up again is the same form, on that run.

import { get } from '../api.js'
import { go, stays } from '../app.js'
import { fill, h, permitted, problem, secondsOf } from '../dom.js'
import { ask } from '../held.js'

export function mount(root, { query }) {
  const resume = query.get('resume') || ''
  const picker = h('select', { 'aria-label': 'Flow', id: 'flow' })
  const about = h('p', { class: 'lede' })
  const form = h('form', { class: 'form', 'data-hmz': 'start', novalidate: true })
  fill(
    root,
    h(
      'div',
      { class: 'head' },
      h('div', {}, h('div', { class: 'kicker' }, resume ? 'pick a run up' : 'start a run'), h('h1', {}, resume ? 'Pick it up again' : 'Start a run'), about),
    ),
    h('section', { class: 'panel' }, h('div', { class: 'form' }, h('div', { class: 'field' }, h('label', { for: 'flow' }, 'flow'), picker), form)),
  )

  let backends = { installed: {}, installable: {} }
  let picked = null

  Promise.all([get('/api/flows'), get('/api/backends'), resume ? get(`/api/runs/${encodeURIComponent(resume)}`) : null])
    .then(([flows, found, run]) => {
      backends = found
      const whose = {}
      for (const one of flows.flows) (whose[one.whose] ||= []).push(one)
      const wanted = query.get('flow') || flows.flow || (flows.flows[0] && flows.flows[0].name) || ''
      fill(
        picker,
        Object.entries(whose).map(([from, list]) =>
          h('optgroup', { label: from }, list.map((one) => h('option', { value: one.name, selected: one.name === wanted, title: one.about }, one.name))),
        ),
      )
      picker.addEventListener('change', () => choose(picker.value, null))
      choose(picker.value, run)
    })
    .catch((error) => fill(form, problem(error)))

  async function choose(name, run) {
    if (!name) return
    stays({ flow: name, resume })
    fill(form, h('p', { class: 'loading', role: 'status' }, `Reading ${name}…`))
    try {
      picked = await get(`/api/flow?name=${encodeURIComponent(name)}`)
    } catch (error) {
      fill(form, problem(error))
      return
    }
    fill(about, picked.description || '')
    drawForm(picked, run)
  }

  function drawForm(flow, run) {
    const kept = run
      ? {
          agents: Object.fromEntries(run.agents.map((one) => [one.role, one.runs])),
          envs: Object.fromEntries(run.envs.map((one) => one.split('=')).map(([role, ...spec]) => [role, spec.join('=')])),
          params: run.params,
          budget: run.budget || {},
          profile: run.profile,
          task: run.task,
        }
      : { ...flow.remembered, task: '' }
    const task = h('textarea', { rows: '4', id: 'task', placeholder: 'What the agents are to do', required: true }, kept.task || '')
    const agents = flow.agents.filter((one) => !one.auto)
    const envs = flow.envs.filter((one) => !one.auto)
    const roleInputs = {}
    const envInputs = {}
    const specs = h('datalist', { id: 'specs' }, agentSpecs(backends.installed).map((spec) => h('option', { value: spec })))
    const roles = agents.map((role) => {
      const input = h('input', { type: 'text', list: 'specs', value: kept.agents[role.name] || '', placeholder: 'cli/model:effort', 'aria-label': `Agent for ${role.name}`, required: role.required })
      roleInputs[role.name] = input
      return h(
        'div',
        { class: 'role', 'data-hmz': 'role' },
        h('h3', {}, role.name, role.harness ? h('span', { class: 'chip' }, role.harness) : null, role.required ? null : h('span', { class: 'dim' }, 'optional')),
        input,
        h('div', { class: 'dim' }, permitted(role.permission), role.skills.length ? ` · skills: ${role.skills.join(', ')}` : ''),
      )
    })
    const places = envs.map((role) => {
      const input = h('input', { type: 'text', value: kept.envs[role.name] || '', placeholder: 'local/<dir>, ssh@<host>/<dir>, docker/<dir>…', 'aria-label': `Where ${role.name} works`, required: role.required })
      envInputs[role.name] = input
      const wants = [role.cpu && `${role.cpu} cpu`, role.memory && `${Math.ceil(role.memory / 2 ** 30)} GiB memory`, role.gpu && `${role.gpu} gpu`, role.image && `image ${role.image}`].filter(Boolean)
      return h('div', { class: 'role' }, h('h3', {}, role.name, h('span', { class: 'dim' }, wants.join(' · '))), input)
    })
    const params = schemaForm(flow.params, kept.params || {})
    const budget = budgetFields(kept.budget || {})
    const profile = h('input', { type: 'checkbox', checked: Boolean(kept.profile) })
    const go_ = h('button', { class: 'btn primary', type: 'submit' }, run ? 'Pick it up' : 'Start')
    const said = h('div', { 'aria-live': 'polite' })
    fill(
      form,
      specs,
      h('div', { class: 'field' }, h('label', { for: 'task' }, 'task'), task),
      roles.length ? h('div', { class: 'field' }, h('span', { class: 'label' }, 'agents'), h('div', { class: 'grid' }, roles), h('span', { class: 'hint' }, 'Each as -a spells one: cli, an @account where it runs as one, the model and an effort.')) : null,
      places.length ? h('div', { class: 'field' }, h('span', { class: 'label' }, 'environments'), h('div', { class: 'grid' }, places)) : null,
      params.fields.length ? h('div', { class: 'field' }, h('span', { class: 'label' }, 'params'), h('div', { class: 'grid' }, params.fields)) : null,
      h('div', { class: 'field' }, h('span', { class: 'label' }, 'budget'), budget.fields, h('span', { class: 'hint' }, flow.name === 'chat' ? 'chat runs for as long as you answer it, and needs none.' : 'Every flow but chat needs at least one limit.')),
      h('label', { class: 'check' }, profile, 'Profile the programs its agents start, as well as tracing them'),
      run ? h('p', { class: 'note' }, `Picks up ${run.name}, carrying on from where it stopped.`) : null,
      h('div', { class: 'row' }, go_, said),
    )
    form.onsubmit = async (event) => {
      event.preventDefault()
      fill(said)
      const agentsSaid = {}
      for (const [role, input] of Object.entries(roleInputs)) if (input.value.trim()) agentsSaid[role] = input.value.trim()
      const envsSaid = {}
      for (const [role, input] of Object.entries(envInputs)) if (input.value.trim()) envsSaid[role] = input.value.trim()
      let paramsSaid
      try {
        paramsSaid = params.read()
      } catch (error) {
        fill(said, problem(error))
        return
      }
      const body = {
        flow: flow.name,
        task: task.value,
        agents: agentsSaid,
        envs: envsSaid,
        params: paramsSaid,
        budget: budget.read(),
        profile: profile.checked,
        resume: run ? run.at : false,
      }
      go_.disabled = true
      go_.textContent = run ? 'Picking it up…' : 'Starting…'
      try {
        await ask('start', body)
        go('/live')
      } catch (error) {
        fill(said, problem(error))
      } finally {
        go_.disabled = false
        go_.textContent = run ? 'Pick it up' : 'Start'
      }
    }
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
function budgetFields(kept) {
  const cost = h('input', { type: 'number', min: '0', step: '0.01', value: kept.cost === 'Infinity' ? '' : kept.cost ?? '', placeholder: 'dollars', 'aria-label': 'Most it may cost, in dollars' })
  const minutes = h('input', { type: 'number', min: '0', step: '1', value: minutesOf(kept.duration), placeholder: 'minutes', 'aria-label': 'Longest it may take, in minutes' })
  const tokens = h('input', { type: 'number', min: '0', step: '1000', value: kept.output_tokens ?? '', placeholder: 'output tokens', 'aria-label': 'Most output tokens it may write' })
  const graceful = h('input', { type: 'checkbox', checked: kept.graceful !== false })
  return {
    fields: h('div', { class: 'row' }, h('span', {}, '$'), cost, minutes, h('span', { class: 'dim' }, 'min'), tokens, h('label', { class: 'check' }, graceful, 'let the last turn finish')),
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
