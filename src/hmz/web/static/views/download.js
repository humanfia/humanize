// Downloading an epic out of a backup target: a dialog over the page that lists every epic the
// target holds, of every machine and every workspace -- each machine's, then each workspace's
// under it, newest first -- marks those already here, and downloads one into this machine's
// epics, as an import would, opening it. What the target holds is fetched afresh as it opens,
// which can take a while.

import { call, hash, refresh } from '../api.js'
import { go, shut, stays } from '../app.js'
import { ago, badge, empty, fill, flowName, h, headline, icon, iconButton, problem, when } from '../dom.js'
import { t } from '../i18n.js'
import { nameOf } from '../places.js'
import { dragged } from '../shell.js'

export function mount(root, { query }) {
  const picker = h('select', { 'aria-label': t('Target'), 'data-hmz': 'download-target', hidden: true })
  const body = h('div', { class: 'dialog-body', 'data-hmz': 'stored' }, h('p', { class: 'loading', role: 'status' }, t('Reading the targets…')))
  root.setAttribute('aria-label', t('Download'))
  fill(root, dragged(h('div', { class: 'dialog-head' }, icon('download'), h('h2', { class: 'dialog-title' }, t('Download')), picker, iconButton('close', t('Close'), { onclick: shut })), 'deep', 'narrow'), body)
  /** Which target was asked of last: one answering after another was picked draws nothing. */
  let asking = ''
  let gone = false

  call('settings.get').then((settings) => {
    const names = settings.backup.targets.map((one) => one.name)
    if (!names.length) {
      fill(body, empty(t('No backup target.'), t(' Add one, and the epics it holds are downloaded from here.'), h('a', { class: 'btn primary', href: hash('/settings/backup') }, t('Backup'))))
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
    fill(body, h('p', { class: 'loading', role: 'status' }, t('Fetching {target}…', { target })))
    let answer
    try {
      answer = await call('backups.epics', { target })
    } catch (error) {
      if (!gone && asking === target) fill(body, problem(error))
      return
    }
    if (gone || asking !== target) return
    if (!answer.epics.length) {
      fill(
        body,
        empty(
          t('No epic here yet.'),
          t(' {target} holds none: an epic is backed up to it as its policies say, or by Upload.', { target }),
          h('a', { class: 'btn', href: hash('/settings/backup'), 'data-hmz': 'download-settings' }, t('Backup settings')),
        ),
      )
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

  // Where one of them is read here: a chat among the chats, an epic among the epics.
  const at = (one, name) => `/${one.chat ? 'chats' : 'epics'}/${encodeURIComponent(name)}`

  function row(target, one) {
    const action = one.here
      ? h('a', { class: 'btn small quiet', href: hash(at(one, one.epic)) }, t('Open'))
      : h('button', { class: 'btn small', type: 'button', onclick: (event) => pull(target, one, event.currentTarget) }, t('Download'))
    return h(
      'div',
      { class: 'result', title: one.task, 'data-hmz': 'stored-epic', 'data-epic': one.epic },
      h('span', { class: 'result-top' }, badge(one.how || 'unfinished'), h('span', { class: 'result-task' }, headline(one.task)), h('span', { class: 'result-when', title: when(one.began) }, ago(one.began)), action),
      h('span', { class: 'result-meta' }, one.chat ? h('span', { class: 'mono' }, t('chat')) : h('span', { class: 'mono', title: one.flow }, flowName(one.flow)), h('span', { class: 'mono' }, one.epic), one.here ? h('span', { class: 'node-tag' }, t('Here')) : null),
    )
  }

  async function pull(target, one, button) {
    button.disabled = true
    button.textContent = t('Downloading…')
    const row = button.closest('[data-hmz=stored-epic]')
    row.querySelector('.error')?.remove()
    try {
      const answer = await call('backups.pull', { target, key: one.key })
      refresh(one.chat ? 'chat.list' : 'runs.list')
      refresh('workspaces.list')
      // Opened unless the dialog was left while it came.
      if (!gone) go(at(one, answer.name))
    } catch (error) {
      // Said on the epic it was refused for.
      row.append(problem(error))
      button.disabled = false
      button.textContent = t('Download')
    }
  }

  return () => {
    gone = true
  }
}
