// A new epic, in the frame a new chat opens in: `New epic` in the bar with the flow picked beside
// it as a model is picked, and the task typed into the box docked at the foot of the page, with
// nothing under that box. Everything the epic is set up with is in the middle of the page, always
// in sight, under what the flow is for: first its environment -- the daemon it runs on, the
// folder, and where each environment role works -- then an agent for each role, a row a role
// with its nous picked from a chip, its params, its budget, where it is backed up and whether its
// flow and its environment are profiled, set up as this directory last started that flow, the way
// `/flow` in the terminal interface sets one up. Nothing saves it but starting. Picking a run up
// again is the same box, on that run. A new epic is of a flow: a new chat is a form of its own
// (views/newchat.js), which the sidebar opens beside this one (Sections 3.8.6, 3.8.17 and 3.8.24
// of protocol/web.md).

import { call, given, hash } from '../api.js'
import { covered, focusing, go, stays } from '../app.js'
import { environmentChip } from '../chips/environment.js'
import { composer } from '../composer.js'
import { NO_FOLDER } from '../desk.js'
import { empty, fill, h, icon, permitted, problem, secondsOf } from '../dom.js'
import { ask } from '../held.js'
import { t } from '../i18n.js'
import { harnessName } from '../names.js'
import { paramsForm } from '../asking/form.js'
import { modelChip } from '../chips/model.js'
import { envPicker, readBackends } from '../pickers.js'
import { firstWorkspace, folderFiles, goneNote, goneSaid, missing, unplaced, workspacePicker, workspaces } from '../places.js'
import { bar, choice, menu, section } from '../shell.js'

export function mount(root, { query }) {
  const resume = query.get('resume') || ''
  const picker = h('button', { class: 'flow-picker', type: 'button', 'data-hmz': 'flow-picker' }, h('span', {}, t('flow')), h('b', {}, '…'), icon('down'))
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
    // Gone since, or back: the form says so, or reads what the folder offers again.
  }, { none: true, went: (lost) => !scratch && lost !== gone && load(picked ? picked.name : query.get('flow') || '') })
  // A task names a file as a first message does: `@` completes the paths of the folder picked.
  // An epic of no folder works in a directory made as it starts, which holds nothing to name yet.
  const files = folderFiles(() => (scratch ? '' : workspace))
  const about = h('p', { class: 'greeting-about' })
  // Where each environment role of the flow picked works, under the daemon and the folder.
  const rooms = h('div', { class: 'setup-rows setup-envs' })
  // Where it runs, first of what it is set up with, and there whatever flow is picked -- or none.
  const environment = h(
    'section',
    { class: 'option-group', 'data-hmz': 'setup-environment' },
    h('h3', {}, t('Environment')),
    h(
      'div',
      { class: 'setup-rows' },
      h('div', { class: 'setup-row', 'data-hmz': 'setup-daemon' }, h('span', { class: 'setup-name' }, t('Runs on')), environmentChip('/new', { up: false }).node),
      h('div', { class: 'setup-row', 'data-hmz': 'setup-folder' }, h('span', { class: 'setup-name' }, t('Folder')), place.node),
    ),
    rooms,
  )
  // The rest of what the flow picked is set up with: drawn for each flow, and of none, nothing.
  const rest = h('div', { class: 'form' })
  const options = h('div', { class: 'options', 'data-hmz': 'options' }, environment, rest)
  const resumed = h('div', { class: 'resumed' })
  // Said in the middle of the page where no flow is on offer: hmz ships none.
  const lacking = h('div', { 'data-hmz': 'no-flow', hidden: true })
  /** Where a flow is installed from: Flows, which is of no folder, on its flowverses. */
  const flowsAt = () => hash('/flows?tab=verses')
  const box = composer({
    placeholder: t('Describe the task'),
    label: t('Task'),
    empty: true,
    busy: t('Starting…'),
    submit: (task) => start(task),
    complete: files.complete,
    desk: { add: ['files'], able: () => (scratch || !workspace ? NO_FOLDER : '') },
  })
  box.node.dataset.hmz = 'start'
  const top = bar({ title: resume ? t('Resume epic') : t('New epic') })
  // The flow, beside the heading, as a chat's bar keeps what can be done beside its title.
  top.querySelector('.bar-title').append(h('div', { class: 'pickers' }, pickerHolder))
  fill(
    root,
    h(
      'div',
      { class: 'view view-new view-desk', 'data-hmz': 'new-epic' },
      top,
      h('div', { class: 'desk-body' }, h('div', { class: 'desk-column' }, lacking, about, resumed, options)),
      h('div', { class: 'dock desk-dock' }, box.node),
    ),
  )

  /** Whether the directory of the folder picked is gone: nothing is read of it, and nothing started in it. */
  let gone = false
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
      // None to pick: where one is installed.
      if (!flows.length) return [choice({ label: t('Open Flows'), glyph: 'flows', href: flowsAt(), close })]
      const whose = {}
      for (const one of flows) (whose[one.whose] ||= []).push(one)
      return Object.entries(whose).map(([from, list]) => [
        section(from),
        list.map((one) => choice({ label: one.name, about: one.about, chosen: picked && picked.name === one.name, act: () => choose(one.name, null), close })),
      ])
    },
    { label: t('Flows') },
  )

  /** Which workspace was read last: one read after another was picked draws nothing. */
  let loading = ''

  /** Says the flow drawn is being read again, rather than leave the last one standing as if current. */
  function reading(on) {
    fill(about, on ? h('span', { class: 'loading', role: 'status' }, t('Reading…')) : picked ? picked.description || '' : '')
    options.classList.toggle('stale', on)
    options.toggleAttribute('aria-busy', on)
  }

  /** Reads what a workspace offers -- its flows, and the one it last set up -- and opens one. */
  async function load(flow) {
    const mine = (loading = scratch ? 'none' : workspace || 'here')
    // Asked for now: what takes the focus while this is read keeps it.
    const focus = focusing()
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
      // Never one that went: the first that is there, which the control then names.
      if (!workspace) {
        workspace = await firstWorkspace()
        if (!scratch) place.set(workspace)
      }
      // One the address named, or picked and gone since, stays picked and is said to be gone,
      // rather than swapped for a folder nobody asked for. Unread, the daemon says so itself.
      gone = !scratch && missing(workspace, await workspaces().catch(() => null))
      if (mine !== loading) return
      if (gone) {
        choosing = ''
        picked = null
        setup = null
        flows = []
        reading(false)
        lacking.hidden = true
        fill(picker.querySelector('b'), t('None'))
        fill(resumed)
        undrawn()
        fill(box.said, goneNote(workspace))
        return
      }
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
      lacking.hidden = Boolean(wanted)
      if (!wanted) {
        // Nothing is picked, and nothing drawn of what was: the page says so where it is read,
        // and where a flow is installed.
        choosing = ''
        picked = null
        setup = null
        reading(false)
        fill(picker.querySelector('b'), t('None'))
        fill(resumed)
        undrawn()
        fill(lacking, empty(t('No flow installed yet.'), t(' A new epic runs a flow. Install one from Flows, then start it here.'), h('a', { class: 'btn primary', href: flowsAt(), 'data-hmz': 'no-flow-open' }, t('Open Flows'))))
      } else choose(wanted, ran, focus)
    } catch (error) {
      if (mine !== loading) return
      reading(false)
      fill(box.said, problem(error))
    }
  }
  load(query.get('flow') || '')

  async function choose(name, ran, focus = focusing()) {
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
    fill(resumed, ran ? h('p', { class: 'note' }, t('Picks up {name}, carrying on from where it stopped.', { name: ran.name })) : null)
    // What the page asked in the middle, asked in the box.
    box.text.placeholder = ran ? t('Describe the task') : t('What should {name} do?', { name })
    setup = drawOptions(picked, ran)
    if (ran && !box.text.value) {
      box.text.value = ran.task
      box.text.dispatchEvent(new Event('input'))
    }
    // Typed into next -- but not from under a dialog opened over it, out of what is typed there,
    // nor out of Ai-chan's drawer beside it, nor out of what took the focus while this was read.
    focus(box.text)
  }

  /** Draws nothing of a flow's set-up: with none picked there is the environment alone. */
  function undrawn() {
    for (const one of leaving) one()
    leaving = []
    fill(rooms)
    fill(rest)
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
    // A role a row: its name, and the nous that fills it on a chip whose menu opens under it.
    const roles = agents.map((role) => {
      pickers[role.name] = modelChip({ name: role.name, clis: role.clis }, (kept.agents || {})[role.name] || '', () => {}, { up: false, align: 'start' })
      // Its name whole, and what the role is held to -- its harness, what it may touch, its skills -- where its name is pointed at.
      const about = [role.name, role.harness ? harnessName(role.harness) : '', permitted(role.permission), role.skills.length ? t('skills: {names}', { names: role.skills.join(', ') }) : ''].filter(Boolean).join(' · ')
      return h(
        'div',
        { class: 'setup-row', 'data-hmz': 'role-row', 'data-role': role.name },
        h('span', { class: 'setup-name', 'data-tip': about }, h('span', { class: 'setup-role' }, role.name), role.required ? null : h('span', { class: 'dim' }, t('Optional'))),
        pickers[role.name].node,
      )
    })
    // An environment role a row, under the daemon and the folder: left blank, it works in the folder.
    const places_ = envs.map((role) => {
      places[role.name] = envPicker(role, (kept.envs || {})[role.name] || '', backends, runtimes, { folder: scratch ? '' : workspace })
      const wants = [role.cpu && `${role.cpu} CPU`, role.memory && `${Math.ceil(role.memory / 2 ** 30)} GiB`, role.gpu && `${role.gpu} GPU`, role.image && role.image].filter(Boolean)
      return h('div', { class: 'setup-row', 'data-hmz': 'env', 'data-role': role.name }, h('span', { class: 'setup-name' }, h('span', { class: 'setup-role' }, role.name), wants.length ? h('span', { class: 'dim' }, wants.join(' · ')) : null), places[role.name].node)
    })
    // The same form a person answers a question with: a field for each param, by its type.
    const params = paramsForm(flow.params, kept.params || {})
    const budget = budgetFields(kept.budget || {})
    const profileFlow = h('input', { type: 'checkbox', checked: Boolean(kept.profile_flow), 'data-hmz': 'profile-flow' })
    const profileEnvironment = h('input', { type: 'checkbox', checked: Boolean(kept.profile_environment), 'data-hmz': 'profile-environment' })
    // Where the epic is backed up: as the one picked up was, else as saved, else the defaults.
    const goesTo = ran ? ran.backup : (kept.backup ?? backup.defaults)
    const targets = backup.targets.map((one) => h('label', { class: 'check', title: one.url }, h('input', { type: 'checkbox', value: one.name, checked: goesTo.includes(one.name) }), one.name))
    /** What the flow is set up with, as a start sends it. */
    function readAll() {
      const agentsSaid = {}
      for (const [role, one] of Object.entries(pickers)) if (one.value()) agentsSaid[role] = one.value()
      // Not started with a role nobody fills, or with nothing bounding what it spends: said, and
      // what is missing is where the keys are.
      const unfilled = agents.find((role) => role.required && !agentsSaid[role.name])
      if (unfilled) throw Object.assign(new Error(t('Pick an agent for {role}.', { role: unfilled.name })), { mend: () => pickers[unfilled.name].open() })
      const budgetSaid = budget.read()
      if (!budgetSaid) throw Object.assign(new Error(t('Set at least one limit of the budget.')), { mend: () => budget.fields.querySelector('input').focus() })
      const envsSaid = {}
      for (const [role, one] of Object.entries(places)) if (one.value()) envsSaid[role] = one.value()
      const backupSaid = targets.map((one) => one.firstChild).filter((one) => one.checked).map((one) => one.value)
      // The defaults left as they are go on following the defaults, rather than being kept.
      const followed = kept.backup == null && backupSaid.length === backup.defaults.length && backupSaid.every((one) => backup.defaults.includes(one))
      return { agents: agentsSaid, envs: envsSaid, params: params.read(), budget: budgetSaid, profile_flow: profileFlow.checked, profile_environment: profileEnvironment.checked, backup: targets.length && !followed ? backupSaid : undefined }
    }
    for (const one of leaving) one()
    leaving = Object.values(pickers).map((one) => one.leave)
    fill(rooms, places_)
    fill(
      rest,
      roles.length ? h('section', { class: 'option-group', 'data-hmz': 'setup-agents' }, h('h3', {}, t('Agents')), h('div', { class: 'setup-rows' }, roles)) : null,
      params.fields.length ? h('section', { class: 'option-group' }, h('h3', {}, t('Parameters')), h('div', { class: 'grid' }, params.fields)) : null,
      h('section', { class: 'option-group' }, h('h3', {}, t('Budget')), budget.fields, h('span', { class: 'hint' }, t('At least one limit.'))),
      targets.length ? h('section', { class: 'option-group', 'data-hmz': 'backup' }, h('h3', {}, t('Backup')), h('div', { class: 'row' }, targets)) : null,
      h('div', { class: 'row' }, h('label', { class: 'check' }, profileFlow, t('Profile flow')), h('label', { class: 'check' }, profileEnvironment, t('Profile environment'))),
    )
    return { read: readAll }
  }

  async function start(task) {
    if (gone) throw new Error(goneSaid(workspace))
    if (!flows.length) throw new Error(t('Install a flow first, from Flows.'))
    if (!picked || !setup) throw new Error(t('Pick a flow first.'))
    let read
    try {
      read = setup.read()
    } catch (error) {
      error.mend?.()
      throw error
    }
    // The answer says which host the epic went to, which the page follows.
    const started = await ask(workspace, 'start', { flow: picked.name, task, ...read, resume: run ? run.at : false, ...(scratch ? { scratch } : {}) }).catch((error) => {
      throw unplaced(error, workspace)
    })
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
    place.leave()
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
function budgetFields(kept) {
  const cost = h('input', { type: 'number', min: '0', step: '0.01', value: kept.cost === 'Infinity' ? '' : kept.cost ?? '', placeholder: t('dollars'), 'aria-label': t('Most it may cost, in dollars') })
  const minutes = h('input', { type: 'number', min: '0', step: '1', value: minutesOf(kept.duration), placeholder: t('minutes'), 'aria-label': t('Longest it may take, in minutes') })
  const tokens = h('input', { type: 'number', min: '0', step: '1000', value: kept.output_tokens ?? '', placeholder: t('output tokens'), 'aria-label': t('Most output tokens it may write') })
  // Graceful is one flag for every limit, or one apiece; a box apiece either way.
  const graces = Object.fromEntries(
    ['cost', 'duration', 'output_tokens'].map((limit) => [
      limit,
      h('input', { type: 'checkbox', checked: (kept.graceful && typeof kept.graceful === 'object' ? kept.graceful[limit] : kept.graceful) !== false }),
    ]),
  )
  return {
    fields: h(
      'div',
      { class: 'row' },
      h('label', { class: 'field' }, h('span', { class: 'label' }, t('Cost, $')), cost),
      h('label', { class: 'field' }, h('span', { class: 'label' }, t('Time, min')), minutes),
      h('label', { class: 'field' }, h('span', { class: 'label' }, t('Output tokens')), tokens),
      h('label', { class: 'check' }, graces.cost, t('Cost graceful')),
      h('label', { class: 'check' }, graces.duration, t('Time graceful')),
      h('label', { class: 'check' }, graces.output_tokens, t('Tokens graceful')),
    ),
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
