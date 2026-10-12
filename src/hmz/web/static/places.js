// The workspaces of this machine, as the page offers them: every one an epic ran in, set up or
// opened here, the one `hmz web` was started in first. Picking one is picking where an epic
// runs, whose flows are on offer, and whose settings are read.

import { get, onDaemon, post } from './api.js'
import { fill, h, icon } from './dom.js'
import { pathPicker } from './paths.js'
import { choice, dragged, follow, menu, section } from './shell.js'

let known = null
// Another daemon's workspaces are others.
onDaemon(() => (known = null))

/** Every workspace there is to offer, read again where asked to. */
export async function workspaces(again = false) {
  if (!known || again) known = get('/api/workspaces')
  try {
    return await known
  } catch (error) {
    known = null
    throw error
  }
}

/** A workspace as a list names it: the last part of its path. */
export function nameOf(path) {
  return String(path || '').split('/').filter(Boolean).pop() || path || ''
}

/**
 * A button naming the workspace chosen, whose menu offers every other and opening one by path.
 *
 * @param {string} chosen The workspace chosen to begin with, or "" for where `hmz web` started.
 * @param {(path: string) => void} changed Told the workspace picked.
 */
export function workspacePicker(chosen, changed) {
  const said = h('b', {}, '…')
  const button = h('button', { class: 'flow-picker', type: 'button', 'data-hmz': 'workspace-picker', 'data-tip': chosen }, icon('folder'), said, icon('down'))
  const folder = pathPicker({ label: 'Folder', placeholder: '~/project' })
  const typed = folder.input
  typed.dataset.hmz = 'workspace-path'
  const problem_ = h('span', { class: 'hint' })
  const opening = dragged(h('form', { class: 'popover workdir-open', hidden: true }, h('div', { class: 'field' }, h('span', { class: 'label' }, 'Folder'), folder.node), h('div', { class: 'row' }, h('button', { class: 'btn small primary', type: 'submit' }, 'Open'), h('button', { class: 'btn small quiet', type: 'button', onclick: () => shut() }, 'Cancel')), problem_), 'false')
  const node = h('div', { class: 'menu-holder' }, button, opening)
  let list = []
  let path = chosen

  function set(to) {
    path = to
    said.textContent = nameOf(to)
    button.dataset.tip = to
  }

  menu(
    button,
    (close) => [
      section('Workdirs'),
      list.map((one) => choice({ label: one.name, about: one.path, chosen: one.path === path, glyph: 'folder', act: () => pick(one.path), close })),
      h('hr'),
      choice({ label: 'Open folder…', glyph: 'plus', act: () => open(), close }),
    ],
    { label: 'Workdirs' },
  )

  function pick(to) {
    if (to === path) return
    set(to)
    changed(to)
  }

  // Kept by the button while it is open, as a menu is.
  let unfollow = () => {}
  function shut() {
    unfollow()
    opening.hidden = true
  }

  function open() {
    opening.hidden = false
    unfollow = follow(opening, button, {})
    problem_.textContent = ''
    typed.value = ''
    typed.focus()
  }

  typed.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') shut()
  })
  opening.addEventListener('submit', async (event) => {
    event.preventDefault()
    try {
      const answer = await post('/api/workspaces', { workspace: typed.value.trim() })
      known = Promise.resolve(answer)
      list = answer.workspaces
      shut()
      pick(answer.kept)
    } catch (error) {
      problem_.textContent = error.message
    }
  })

  workspaces().then(
    (answer) => {
      list = answer.workspaces
      if (!path) path = answer.here
      set(path)
    },
    // A daemon that cannot be reached: the view it is on says why.
    () => {},
  )
  return { node, set, value: () => path }
}
