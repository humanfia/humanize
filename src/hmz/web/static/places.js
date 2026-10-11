// The workspaces of this machine, as the page offers them: every one an epic ran in, set up or
// opened here, the one `hmz web` was started in first. Picking one is picking where an epic
// runs, whose flows are on offer, and whose settings are read.

import { get, post } from './api.js'
import { fill, h, icon } from './dom.js'
import { choice, menu, section } from './shell.js'

let known = null

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
  const button = h('button', { class: 'flow-picker', type: 'button', 'data-hmz': 'workspace-picker', title: chosen }, icon('folder'), said, icon('down'))
  const typed = h('input', { type: 'text', list: 'workdirs', placeholder: '~/project', 'aria-label': 'Folder', 'data-hmz': 'workspace-path' })
  const dirs = h('datalist', { id: 'workdirs' })
  const problem_ = h('span', { class: 'hint' })
  const opening = h('form', { class: 'popover workdir-open', hidden: true }, h('label', { class: 'field' }, h('span', { class: 'label' }, 'Folder'), typed, dirs), h('div', { class: 'row' }, h('button', { class: 'btn small primary', type: 'submit' }, 'Open'), h('button', { class: 'btn small quiet', type: 'button', onclick: () => (opening.hidden = true) }, 'Cancel')), problem_)
  const node = h('div', { class: 'menu-holder' }, button, opening)
  let list = []
  let path = chosen

  function set(to) {
    path = to
    said.textContent = nameOf(to)
    button.title = to
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

  function open() {
    opening.hidden = false
    problem_.textContent = ''
    typed.value = ''
    typed.focus()
  }

  let completing = 0
  typed.addEventListener('input', () => {
    clearTimeout(completing)
    completing = setTimeout(async () => {
      try {
        const { paths } = await get(`/api/paths?typed=${encodeURIComponent(typed.value)}`)
        fill(dirs, paths.map((one) => h('option', { value: one })))
      } catch {
        fill(dirs)
      }
    }, 150)
  })
  typed.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') opening.hidden = true
  })
  opening.addEventListener('submit', async (event) => {
    event.preventDefault()
    try {
      const answer = await post('/api/workspaces', { workspace: typed.value.trim() })
      known = Promise.resolve(answer)
      list = answer.workspaces
      opening.hidden = true
      pick(answer.kept)
    } catch (error) {
      problem_.textContent = error.message
    }
  })

  workspaces().then((answer) => {
    list = answer.workspaces
    if (!path) path = answer.here
    set(path)
  })
  return { node, set, value: () => path }
}
