// The workspaces of this machine, as the page offers them: every one an epic ran in, set up or
// opened here, the one `hmz web` was started in first. Picking one is picking where an epic
// runs, whose flows are on offer, and whose settings are read.

import { call, daemon, onDaemon, started } from './api.js'
import { chipNamed } from './desk.js'
import { fill, h, icon } from './dom.js'
import { pathItems, pathParts, typing } from './natives.js'
import { pathPicker } from './paths.js'
import { choice, dragged, follow, menu, section } from './shell.js'

let known = null
// Another daemon's workspaces are others.
onDaemon(() => (known = null))

/** Where `hmz web` started, as `here` offers it first: a workspace of Local's, none elsewhere. */
export async function mine() {
  const here = daemon() === 'local' ? await started() : ''
  return here ? { here } : {}
}

/** Every workspace there is to offer, read again where asked to. */
export async function workspaces(again = false) {
  if (!known || again) known = mine().then((here) => call('workspaces.list', here))
  try {
    return await known
  } catch (error) {
    known = null
    throw error
  }
}

/**
 * The workspace offered first: where `hmz web` started, on Local; else the first there is; else,
 * on a daemon that knows none yet, its user's home, `~` as it expands it there.
 */
export async function firstWorkspace() {
  const offered = await workspaces()
  return offered.here || (offered.workspaces[0] && offered.workspaces[0].path) || '~'
}

/** What picking no workspace is called, as the sidebar calls the group of what has none. */
const NONE = 'No folder'

/** Where an epic of no workspace works. */
const NOWHERE = 'A new directory of its own, in the temporary directory'

/** A choice that says more where it is pointed at, where there is more to say. */
function tipped(item, tip) {
  if (tip) item.dataset.tip = tip
  return item
}

/**
 * What `@` completes in a box typed into before a chat or an epic there is: the paths of the
 * folder picked, read a directory at a time and kept until another folder is picked.
 *
 * @param {() => string} folder The folder picked now, or '' for none.
 * @returns {{complete: (text: string, caret: number) => Promise<object|null>, clear: () => void}}
 */
export function folderFiles(folder) {
  /** What was listed, by the directory listed. */
  const listed = new Map()
  return {
    clear: () => listed.clear(),
    async complete(text, caret) {
      const typed = typing(text, caret)
      const workspace = folder()
      if (!typed || typed.sigil !== '@' || !workspace) return null
      const { dir, base } = pathParts(typed.word)
      const hidden = base.startsWith('.')
      const key = `${workspace}\n${hidden}\n${dir}`
      if (!listed.has(key)) listed.set(key, call('paths.list', { at: `${workspace.replace(/\/+$/, '')}/${dir}`, files: true, hidden }).then((read) => read.entries, () => []))
      const items = pathItems(dir, base, await listed.get(key))
      return { from: typed.from, to: typed.to, groups: items.length ? [{ source: 'path', label: 'Files', items }] : [] }
    },
  }
}

/** A workspace as a list names it: the last part of its path. */
export function nameOf(path) {
  return String(path || '').split('/').filter(Boolean).pop() || path || ''
}

/**
 * A button naming the workspace chosen, whose menu offers every other and opening one by path --
 * and, where asked, no workspace: a directory of its own, made for the epic when it starts.
 *
 * @param {string | null} chosen The workspace chosen to begin with, "" for where `hmz web`
 *   started, or null for no workspace.
 * @param {(path: string | null) => void} changed Told the workspace picked, null for none.
 * @param {{ none?: boolean, plain?: boolean }} [offers] Whether no workspace is on offer, and
 *   whether the menu is a chat app's folder menu: each folder one row, by the last part of its
 *   path alone, under no heading, its whole path said where it is pointed at.
 */
export function workspacePicker(chosen, changed, { none = false, plain = false } = {}) {
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
    said.textContent = to === null ? NONE : nameOf(to)
    button.dataset.tip = to === null ? NOWHERE : to
    // Said with what it picks, as every chip under a box is: its text alone is only a name.
    button.setAttribute('aria-label', chipNamed('Folder', said.textContent))
  }

  menu(
    button,
    (close) => [
      plain ? null : section('Recent'),
      list.map((one) => {
        const item = choice({ label: one.name, about: plain ? '' : one.path, chosen: one.path === path, glyph: 'folder', act: () => pick(one.path), close })
        if (plain) item.dataset.tip = one.path
        return item
      }),
      h('hr'),
      choice({ label: 'Open folder…', glyph: 'plus', act: () => open(), close }),
      none ? tipped(choice({ label: NONE, about: plain ? '' : NOWHERE, chosen: path === null, glyph: 'file', act: () => pick(null), close }), plain ? NOWHERE : '') : null,
    ],
    { label: 'Folders', up: plain },
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
  const openButton = opening.querySelector('[type=submit]')
  opening.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (openButton.disabled) return
    openButton.disabled = true
    openButton.textContent = 'Opening…'
    problem_.textContent = ''
    try {
      const answer = await call('workspaces.add', { workspace: typed.value.trim(), ...(await mine()) })
      known = Promise.resolve(answer)
      list = answer.workspaces
      shut()
      pick(answer.kept)
    } catch (error) {
      problem_.textContent = error.message
    } finally {
      openButton.disabled = false
      openButton.textContent = 'Open'
    }
  })

  workspaces().then(
    (answer) => {
      list = answer.workspaces
      if (path === '') path = answer.here
      set(path)
    },
    // A daemon that cannot be reached: the view it is on says why.
    () => {},
  )
  return { node, set, value: () => path }
}
