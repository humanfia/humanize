// Downloading an epic out of a backup target: a dialog over the page that lists every epic the
// target holds, of every machine and every workspace -- each machine's, then each workspace's
// under it, newest first -- marks those already here, and downloads one into this machine's
// epics, as an import would, opening it. What the target holds is fetched afresh as it opens,
// which can take a while.

import { get, post, refresh } from '../api.js'
import { go, shut, stays } from '../app.js'
import { ago, badge, empty, fill, flowName, h, headline, icon, iconButton, problem, when } from '../dom.js'
import { nameOf } from '../places.js'
import { dragged } from '../shell.js'

export function mount(root, { query }) {
  const picker = h('select', { 'aria-label': 'Target', 'data-hmz': 'download-target', hidden: true })
  const body = h('div', { class: 'dialog-body', 'data-hmz': 'stored' }, h('p', { class: 'loading', role: 'status' }, 'Reading the targets…'))
  root.setAttribute('aria-label', 'Download')
  fill(root, dragged(h('div', { class: 'dialog-head' }, icon('download'), h('h2', { class: 'dialog-title' }, 'Download'), picker, iconButton('close', 'Close', { onclick: shut }))), body)
  /** Which target was asked of last: one answering after another was picked draws nothing. */
  let asking = ''
  let gone = false

  get('/api/settings').then((settings) => {
    const names = settings.backup.targets.map((one) => one.name)
    if (!names.length) {
      fill(body, empty('No backup target.', ' Add one, and the epics it holds are downloaded from here.', h('a', { class: 'btn primary', href: '#/settings/backup' }, 'Backup')))
      return
    }
    const chosen = names.includes(query.get('target')) ? query.get('target') : names[0]
    fill(picker, names.map((one) => h('option', { value: one, selected: one === chosen }, one)))
    // One target is the only one there is to pick.
    picker.hidden = names.length < 2
    picker.addEventListener('change', () => read(picker.value))
    read(chosen)
  }, (error) => fill(body, problem(error)))

  async function read(target) {
    asking = target
    stays({ target })
    fill(body, h('p', { class: 'loading', role: 'status' }, `Fetching ${target}…`))
    let answer
    try {
      answer = await get(`/api/backups/${encodeURIComponent(target)}/epics`)
    } catch (error) {
      if (!gone && asking === target) fill(body, problem(error))
      return
    }
    if (gone || asking !== target) return
    if (!answer.epics.length) {
      fill(body, empty('No epic here yet.', ` ${target} holds none: an epic is backed up to it as its policies say, or by Upload.`))
      return
    }
    // Each machine, then each workspace on it, in the order their newest epic came.
    const machines = new Map()
    for (const one of answer.epics) {
      if (!machines.has(one.machine)) machines.set(one.machine, new Map())
      const places = machines.get(one.machine)
      if (!places.has(one.workspace)) places.set(one.workspace, [])
      places.get(one.workspace).push(one)
    }
    fill(
      body,
      [...machines].map(([machine, places]) =>
        h(
          'section',
          { class: 'stored-machine', 'data-hmz': 'stored-machine', 'data-machine': machine },
          h('h3', { class: 'stored-head' }, icon('home'), machine),
          [...places].map(([workspace, epics]) =>
            h(
              'div',
              { class: 'stored-workspace' },
              h('h4', { class: 'stored-head', title: workspace }, icon('folder'), nameOf(workspace)),
              h('ul', { class: 'results', role: 'list' }, epics.map((one) => h('li', {}, row(target, one)))),
            ),
          ),
        ),
      ),
    )
  }

  function row(target, one) {
    const action = one.here
      ? h('a', { class: 'btn small quiet', href: `#/epics/${encodeURIComponent(one.epic)}` }, 'Open')
      : h('button', { class: 'btn small', type: 'button', onclick: (event) => pull(target, one, event.currentTarget) }, 'Download')
    return h(
      'div',
      { class: 'result', title: one.task, 'data-hmz': 'stored-epic', 'data-epic': one.epic },
      h('span', { class: 'result-top' }, badge(one.how || 'unfinished'), h('span', { class: 'result-task' }, headline(one.task)), h('span', { class: 'result-when', title: when(one.began) }, ago(one.began)), action),
      h('span', { class: 'result-meta' }, h('span', { class: 'mono', title: one.flow }, flowName(one.flow)), h('span', { class: 'mono' }, one.epic), one.here ? h('span', { class: 'node-tag' }, 'Here') : null),
    )
  }

  async function pull(target, one, button) {
    button.disabled = true
    button.textContent = 'Downloading…'
    const row = button.closest('[data-hmz=stored-epic]')
    row.querySelector('.error')?.remove()
    try {
      const answer = await post(`/api/backups/${encodeURIComponent(target)}/pull`, { key: one.key })
      refresh('/api/runs')
      refresh('/api/workspaces')
      // Opened unless the dialog was left while it came.
      if (!gone) go(`/epics/${encodeURIComponent(answer.name)}`)
    } catch (error) {
      // Said on the epic it was refused for.
      row.append(problem(error))
      button.disabled = false
      button.textContent = 'Download'
    }
  }

  return () => {
    gone = true
  }
}
