// The workspaces of this machine, as the page offers them: every one an epic ran in, set up or
// opened here, the one `hmz web` was started in first. Picking one is picking where an epic
// runs, whose flows are on offer, and whose settings are read. A directory can go while the
// page is open: the daemon looks on every `workspaces.list` (`there`), and nothing here offers,
// or opens on, one that went.

import { call, daemon, given, onDaemon, poll, refresh, started } from './api.js'
import { chipNamed } from './desk.js'
import { h, icon } from './dom.js'
import { closed, opened } from './layers.js'
import { pathItems, pathParts, typing } from './natives.js'
import { pathPicker } from './paths.js'
import { choice, dragged, follow, menu, section } from './shell.js'

let known = null
/** When `known` was asked for: a directory can go, so an answer is trusted only for `FRESH`. */
let asked = 0
const FRESH = 5000
// Another daemon's workspaces are others.
onDaemon(() => (known = null))

/** Where `hmz web` started, as `here` offers it first: a workspace of Local's, none elsewhere. */
export async function mine() {
  const here = daemon() === 'local' ? await started() : ''
  return here ? { here } : {}
}

/** Every workspace there is to offer, read again where asked to or where what was read is old. */
export async function workspaces(again = false) {
  if (!known || again || Date.now() - asked > FRESH) {
    asked = Date.now()
    known = mine().then((here) => call('workspaces.list', here))
  }
  try {
    return await known
  } catch (error) {
    known = null
    throw error
  }
}

/** Whether a workspace's directory is on its machine: a daemon that does not say is taken to mean it is. */
export const there = (one) => one.there !== false

/** Whether `workspaces.list` answered that the directory at a path is gone. */
export function missing(path, answer) {
  return Boolean(path) && ((answer && answer.workspaces) || []).some((one) => one.path === path && !there(one))
}

/**
 * The workspace an answer of `workspaces.list` offers first: where `hmz web` started, on Local,
 * while that directory is there; else the first listed that is there -- one going, then the one
 * worked in last; else the user's home, `~` as the daemon expands it. Never one that is gone.
 */
export function firstOf(answer) {
  if (answer.here && !missing(answer.here, answer)) return answer.here
  const first = (answer.workspaces || []).find(there)
  return first ? first.path : '~'
}

/** The workspace offered first, as `firstOf` picks it from what the daemon lists now. */
export async function firstWorkspace() {
  return firstOf(await workspaces())
}

/** What is said of a folder whose directory is gone, where there is no other to pick: of a chat carried on there. */
export function lostSaid(path) {
  return `The folder ${nameOf(path)} is no longer on this machine.`
}

/** What is said of a folder picked whose directory is gone, on the form and where starting is refused. */
export function goneSaid(path) {
  return `${lostSaid(path)} Pick another folder.`
}

/** That sentence as a form says it over its box, in place of the daemon's refusal. */
export function goneNote(path) {
  return h('p', { class: 'note folder-gone', role: 'status', 'data-hmz': 'folder-gone', title: path }, goneSaid(path))
}

/** A start refused because its directory is gone (404, Section 4.5.2 of protocol/daemon.md), said as `goneSaid` says it, or as `said` does. */
export function unplaced(error, path, said = goneSaid) {
  return error && error.status === 404 && /^There is no directory /.test(error.message) ? new Error(said(path)) : error
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
 * @param {{ none?: boolean, plain?: boolean, went?: (gone: boolean) => void }} [offers]
 *   Whether no workspace is on offer; whether the menu is a chat app's folder menu: each folder
 *   one row, by the last part of its path alone, under no heading, its whole path said where it
 *   is pointed at; and what is told when the directory of the one chosen goes, or comes back.
 * @returns {{node: Element, set: (path: string | null) => void, value: () => string | null, gone: () => boolean, leave: () => void}}
 *   `gone` says whether the one chosen is known to be gone; `leave` stops watching the directories.
 */
export function workspacePicker(chosen, changed, { none = false, plain = false, went = () => {} } = {}) {
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
  /** Whether the directory of the one chosen is gone, as the daemon answered last. */
  let lost = false
  // Where the menu opens, and the form that takes its place.
  const where = { align: 'start', up: plain }

  function set(to) {
    path = to
    const was = lost
    lost = missing(to, { workspaces: list })
    said.textContent = to === null ? NONE : lost ? `${nameOf(to)} (missing)` : nameOf(to)
    button.dataset.tip = to === null ? NOWHERE : lost ? `This folder is no longer on this machine: ${to}` : to
    button.setAttribute('class', lost ? 'flow-picker gone' : 'flow-picker')
    if (lost) button.setAttribute('aria-invalid', 'true')
    else button.removeAttribute('aria-invalid')
    // Said with what it picks, as every chip under a box is: its text alone is only a name.
    button.setAttribute('aria-label', chipNamed('Folder', said.textContent))
    if (lost !== was) went(lost)
  }

  // Pressed while the form is open, the button shuts it, as it shuts its menu: heard before the
  // menu hears of it, which then opens nothing.
  button.addEventListener('click', (event) => {
    if (opening.hidden) return
    event.stopImmediatePropagation()
    shut()
  })
  menu(
    button,
    (close) => [
      plain ? null : section('Recent'),
      // Only what is there to work in -- and the one chosen, said to be missing, so that the
      // menu still shows what the button names.
      list.filter((one) => there(one) || one.path === path).map((one) => {
        const gone = !there(one)
        const item = choice({ label: one.name, about: gone ? 'Missing' : plain ? '' : one.path, chosen: one.path === path, glyph: 'folder', act: () => pick(one.path), close })
        if (gone) item.dataset.missing = ''
        if (plain || gone) item.dataset.tip = gone ? `This folder is no longer on this machine: ${one.path}` : one.path
        return item
      }),
      h('hr'),
      choice({ label: 'Open folder…', glyph: 'plus', act: () => open(), close }),
      none ? tipped(choice({ label: NONE, about: plain ? '' : NOWHERE, chosen: path === null, glyph: 'file', act: () => pick(null), close }), plain ? NOWHERE : '') : null,
    ],
    { label: 'Folders', ...where },
  )

  function pick(to) {
    if (to === path) return
    set(to)
    changed(to)
  }

  // Kept by the button while it is open, as a menu is, and closed by what closes one (layers.js):
  // a panel, which keeps what is typed into it while the window is sized or left.
  let unfollow = () => {}
  const layer = { node: opening, anchor: button, kind: 'panel', close: shut }
  function shut() {
    if (opening.hidden) return
    closed(layer)
    unfollow()
    opening.hidden = true
    button.setAttribute('aria-expanded', 'false')
  }

  function open() {
    opening.hidden = false
    opened(layer)
    unfollow = follow(opening, button, where)
    button.setAttribute('aria-expanded', 'true')
    problem_.textContent = ''
    typed.value = ''
    typed.focus()
  }

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
      asked = Date.now()
      list = answer.workspaces
      // Whoever lists the folders -- the sidebar, another picker -- lists this one too.
      refresh('workspaces.list')
      shut()
      pick(answer.kept)
    } catch (error) {
      problem_.textContent = error.message
    } finally {
      openButton.disabled = false
      openButton.textContent = 'Open'
    }
  })

  // Watched for as long as the picker stands, in the read the sidebar keeps: a directory that
  // goes leaves the menu, and the one chosen says so. A daemon that cannot be reached answers
  // nothing, and the view the picker is on says why.
  let unwatch = () => {}
  let left = false
  mine().then((here) => {
    if (left) return
    unwatch = poll('workspaces.list', given(here), 10000, (answer) => {
      if (!answer) return
      list = answer.workspaces
      // What `workspaces` answers is no older than this: whoever is told the folder went, or
      // came back, and reads them again reads what said so, not what was read before it.
      known = Promise.resolve(answer)
      asked = Date.now()
      set(path === '' ? firstOf(answer) : path)
    })
  })
  return {
    node,
    set,
    value: () => path,
    gone: () => lost,
    leave() {
      left = true
      unwatch()
    },
  }
}
