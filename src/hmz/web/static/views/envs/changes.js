// An environment's Changes panel, as Source Control draws a repository's: the branch and how far it
// is from its upstream, the changed files in their groups (Merge Changes, Staged Changes, Changes,
// Untracked) to stage, unstage, discard or open, a box to commit with, a diff of the file picked,
// side by side or inline, the recent commits and, where the environment can rewind, its
// snapshots. It reads the environment again on its own: when something is done in it, when a turn
// ends, when the window comes back, and every few seconds while it is seen.

import { empty, fill, h, icon, problem, svg } from '../../dom.js'
import { menuOf, menuOn } from '../../ui.js'
import { bytesText, chosen, commitPlan, decoded, fullDate, groupsOf, hunks, LARGE, MEANING, moveOf, pathsOf, picked, placeOf, relative, rowsOf, sizeOf, subjectHint } from './changes_logic.js'
import { splitter } from './split.js'
import { menuKey } from './tree.js'

/** How tall a row of the list stands, as changes.css draws it. */
const ROW = 24
/** The narrowest a diff is drawn side by side unasked: under it each side is too narrow to read. */
const TIGHT = 560
/** How often the panel reads the environment again while it is seen. */
const POLL = 5000
/** The refusal of an environment that is no more. */
const CLOSED = 'That environment has closed.'
/** How the diff folds away what did not change: three lines kept around each change. */
const FOLD = { margin: 3, minSize: 4 }
/** The most bytes a side of the diff open holds to be read again every few seconds regardless. */
const SMALL = 256 * 1024

/** The editor, loaded once, the first time a diff is drawn. */
let editor = null
const codemirror = () => (editor ||= import('/vendor/codemirror.js').catch((error) => {
  editor = null
  throw error
}))

/** The panel's own stylesheet, linked once. */
function linked() {
  if (document.querySelector('link[data-hmz="changes-css"]')) return
  document.head.append(h('link', { rel: 'stylesheet', href: new URL('./changes.css', import.meta.url).href, 'data-hmz': 'changes-css' }))
}

/** The icons the page has, by the names the panel calls them. */
const PAGE = { plus: 'plus', minus: 'minus', open: 'file', refresh: 'resume', chevron: 'chevron', up: 'up', close: 'close' }

/** The strokes of the icons the page has not, each on a 24-unit square, drawn as the page draws its own. */
const GLYPHS = {
  discard: ['M9 14 4 9l5-5', 'M4 9h11a5 5 0 0 1 0 10h-4'],
  trash: ['M4 7h16', 'M9 7V4h6v3', 'M6 7l1 13h10l1-13'],
  list: ['M8 6h12', 'M8 12h12', 'M8 18h12', 'M4 6h1', 'M4 12h1', 'M4 18h1'],
  tree: ['M4 4h6v5H4Z', 'M7 9v9h4', 'M7 13h4', 'M11 11h9v4h-9Z', 'M11 16h9v4h-9Z'],
  branch: ['M6 3v12', 'M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M18 9a9 9 0 0 1-9 9'],
  down: ['M12 5v14', 'm19 12-7 7-7-7'],
  side: ['M3 4h18v16H3Z', 'M12 4v16'],
  inline: ['M3 4h18v16H3Z', 'M3 12h18'],
}

function glyph(name) {
  if (PAGE[name]) return icon(PAGE[name])
  return svg(
    'svg',
    { class: `icon icon-${name}`, viewBox: '0 0 24 24', width: '18', height: '18', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'square', 'stroke-linejoin': 'miter', 'aria-hidden': 'true' },
    GLYPHS[name].map((d) => svg('path', { d })),
  )
}

/** A small icon button; `act` names what it does where a row's buttons are told apart by it. */
function tool(name, label, props = {}) {
  return h('button', { type: 'button', class: 'ch-tool', title: label, 'aria-label': label, ...props }, glyph(name))
}

/** What asking to discard these entries says. */
function discardText(entries) {
  const loose = entries.filter((one) => one.group === 'untracked').length
  if (entries.length === 1) {
    const [one] = entries
    return one.group === 'untracked'
      ? `Delete the untracked file ${one.name}? It is removed from the disk, and this cannot be undone.`
      : `Discard the changes to ${one.name}? This cannot be undone.`
  }
  const deleted = loose ? ` ${loose} untracked ${loose === 1 ? 'file is' : 'files are'} deleted from the disk.` : ''
  return `Discard the changes to ${entries.length} files?${deleted} This cannot be undone.`
}

export async function mount(el, ctx) {
  linked()
  const id = `ch-${Math.random().toString(36).slice(2, 8)}`
  const keep = (key, value) => (value === undefined ? ctx.keep(`changes.${key}`) : ctx.keep(`changes.${key}`, value))
  const caps = ctx.env?.caps || []

  let status = null
  let groups = groupsOf([])
  let rows = []
  let seen = ''
  let view = keep('view') === 'tree' ? 'tree' : 'list'
  /** How a diff is drawn, once chosen: `side` or `inline`. */
  let mode = ['side', 'inline'].find((one) => one === keep('diff')) || ''
  /** Whether the diff has no room for two sides. */
  let tight = false
  /** How a diff is drawn: as chosen, and until then side by side where both sides have room. */
  const drawnAs = () => mode || (tight ? 'inline' : 'side')
  const collapsed = new Set()
  let pick = { selected: new Set(), anchor: null }
  let cursor = null
  let closed = false
  let busy = false
  let commits = null
  let logHead
  let snapshots = null
  let diff = null
  let left = false

  // The header: the branch, how far it is from its upstream, and what is done to the whole.
  const branch = h('span', { class: 'ch-branch', 'data-hmz': 'changes-branch' })
  const sync = h('span', { class: 'ch-sync', 'data-hmz': 'changes-sync' })
  const viewButton = tool('list', '', { 'data-hmz': 'changes-view', onclick: () => setView(view === 'list' ? 'tree' : 'list') })
  const refreshButton = tool('refresh', 'Refresh', { 'data-hmz': 'changes-refresh', onclick: () => refresh({ hard: true }) })
  const head = h('div', { class: 'ch-head' }, glyph('branch'), branch, sync, h('span', { class: 'ch-grow' }), viewButton, refreshButton)
  const banner = h('p', { class: 'ch-banner', role: 'status', 'data-hmz': 'changes-closed', hidden: true }, 'This environment has closed: what is shown is as it was, and nothing more can be done to it.')
  // What reading the environment was refused with, cleared once it is read; and what doing
  // something in it was, kept until something else is done.
  const readError = h('div')
  const actError = h('div')
  const errors = h('div', { class: 'ch-errors', 'data-hmz': 'changes-error' }, readError, actError)

  // The box a commit is written in.
  const message = h('textarea', {
    class: 'ch-message',
    rows: 3,
    placeholder: `Message (${/Mac|iPhone|iPad/.test(navigator.platform) ? 'Cmd' : 'Ctrl'}+Enter to commit)`,
    'aria-label': 'Commit message',
    'data-hmz': 'commit-message',
  })
  message.value = keep('draft') || ''
  const hint = h('span', { class: 'ch-hint', 'aria-live': 'polite' })
  const amend = h('input', { type: 'checkbox', 'data-hmz': 'commit-amend' })
  const commitButton = h('button', { type: 'button', class: 'btn primary small ch-commit', 'data-hmz': 'changes-commit', onclick: () => commit() }, 'Commit')
  const reason = h('p', { class: 'ch-reason', 'data-hmz': 'commit-reason' })
  const box = h(
    'div',
    { class: 'ch-box' },
    message,
    h('div', { class: 'ch-box-row' }, h('label', { class: 'ch-amend' }, amend, 'Amend'), hint, h('span', { class: 'ch-grow' }), commitButton),
    reason,
  )

  // The list, drawn a window at a time: only the rows in sight are made.
  const spacer = h('div', { class: 'ch-spacer', role: 'presentation' })
  const list = h('div', { class: 'ch-list', tabindex: '0', role: 'tree', 'aria-label': 'Changes', 'aria-multiselectable': 'true', 'data-hmz': 'changes-list' }, spacer)
  const none = h('p', { class: 'ch-none', 'data-hmz': 'changes-none', hidden: true }, 'No changes.')

  // The recent commits and the snapshots, each folded away until opened.
  const commitList = h('div', { class: 'ch-commits' })
  const commitsCount = h('span', { class: 'ch-count' })
  const commitSection = h('details', { class: 'ch-section', 'data-hmz': 'commits' }, h('summary', {}, 'Commits', commitsCount), commitList)
  commitSection.open = keep('commits') === 'open'
  commitSection.addEventListener('toggle', () => keep('commits', commitSection.open ? 'open' : ''))
  const snapList = h('div', { class: 'ch-snapshots' })
  const snapSection = caps.includes('rewind') ? h('details', { class: 'ch-section', 'data-hmz': 'snapshots' }, h('summary', {}, 'Snapshots'), snapList) : null
  snapSection?.addEventListener('toggle', () => snapSection.open && loadSnapshots())

  const side = h('div', { class: 'ch-side' }, head, banner, errors, box, list, none, commitSection, snapSection)

  // The diff of the file picked.
  const diffTitle = h('span', { class: 'ch-diff-title' })
  const counter = h('span', { class: 'ch-counter', 'data-hmz': 'diff-counter' })
  const modeButton = tool('side', '', { 'data-hmz': 'diff-mode', onclick: () => setMode(drawnAs() === 'side' ? 'inline' : 'side') })
  const diffMove = tool('plus', 'Stage Changes', { 'data-hmz': 'diff-move', onclick: () => diff && move([diff.entry]) })
  const diffHead = h(
    'div',
    { class: 'ch-diff-head' },
    diffTitle,
    h('span', { class: 'ch-grow' }),
    tool('up', 'Previous change (Shift+F7)', { 'data-hmz': 'diff-prev', onclick: () => step(-1) }),
    counter,
    tool('down', 'Next change (F7)', { 'data-hmz': 'diff-next', onclick: () => step(1) }),
    modeButton,
    diffMove,
    tool('open', 'Open File', { 'data-hmz': 'diff-open', onclick: () => diff && openFile(diff.entry) }),
    tool('close', 'Close the diff', { 'data-hmz': 'diff-close', onclick: () => closeDiff() }),
  )
  const diffBody = h('div', { class: 'ch-diff-body', 'data-hmz': 'diff-body' })
  const pane = h('div', { class: 'ch-diff', 'data-hmz': 'changes-diff', hidden: true }, diffHead, diffBody)
  // What stands in the diff's place while none is open.
  const blank = h('div', { class: 'ch-diff', 'data-hmz': 'changes-blank', hidden: true }, h('div', { class: 'ch-notice' }, empty('No change open', 'Pick a file in the list to see its diff.')))

  const root = h('div', { class: 'changes', 'data-hmz': 'changes' }, side, pane, blank)
  // The line that sizes the list: it takes two fifths of the panel at most and 200px at least, as changes.css lays it out.
  const line = splitter(root, { name: '--ch-side', key: 'hmz-changes-side', label: 'Resize the list of changes', least: 200, most: (whole) => whole * 0.4, hmz: 'changes-split' })
  side.after(line)
  fill(el, root)

  // ---- What is said where something went wrong.

  function failed(error, where = readError) {
    const said = error instanceof Error ? error.message : String(error)
    if (said === CLOSED) return close()
    fill(where, problem(said))
  }

  function close() {
    if (closed) return
    closed = true
    root.classList.add('closed')
    banner.hidden = false
    message.disabled = amend.disabled = commitButton.disabled = refreshButton.disabled = true
    fill(readError)
    fill(actError)
    clearInterval(poll)
    drawCommit()
    if (snapshots) drawSnapshots()
  }

  // ---- Reading the environment.

  let running = null
  let queued = null
  let wanted = null

  /** Reads the environment again; asked while it reads, it reads once more once it is done. */
  function refresh(how = {}) {
    if (closed || left) return Promise.resolve()
    if (running) {
      wanted = { hard: Boolean(wanted?.hard || how.hard) }
      return (queued ||= running.then(() => {
        queued = null
        const again = wanted
        wanted = null
        return refresh(again)
      }))
    }
    running = load(how).finally(() => (running = null))
    return running
  }

  /** Reads, never failing: what goes wrong is said, and the next read goes ahead. */
  async function load(how) {
    try {
      await read(how)
    } catch (error) {
      failed(error)
    }
  }

  async function read({ hard = false } = {}) {
    let said
    try {
      said = await ctx.call('env.git.status', {})
    } catch (error) {
      failed(error)
      return
    }
    if (left) return
    fill(readError)
    const changed = JSON.stringify(said) !== seen
    if (changed) {
      seen = JSON.stringify(said)
      status = said
      groups = groupsOf(said.files || [])
      rebuild()
      drawHead()
      drawCommit()
    }
    const moved = said.head !== logHead
    await Promise.all([
      moved || hard || commits === null ? loadLog() : null,
      snapSection && snapSection.open && (moved || hard) ? loadSnapshots() : null,
      diff ? reloadDiff({ hard, changed }) : null,
    ])
  }

  async function loadLog() {
    try {
      const said = await ctx.call('env.git.log', { limit: 50 })
      commits = said.commits || []
      logHead = status?.head
      drawCommits()
    } catch (error) {
      if (String(error?.message) === CLOSED) close()
      else fill(commitList, problem(error))
    }
  }

  async function loadSnapshots() {
    try {
      const said = await ctx.call('env.git.snapshots', {})
      snapshots = said.snapshots || []
      drawSnapshots()
    } catch (error) {
      failed(error, snapList)
    }
  }

  // ---- The header.

  function drawHead() {
    if (!status) return
    const short = status.head ? status.head.slice(0, 7) : ''
    branch.textContent = status.branch || (short ? `${short} (detached)` : 'No commits yet')
    branch.title = status.root || ''
    if (status.upstream) {
      fill(sync, h('span', {}, `↑${status.ahead || 0}`), h('span', {}, `↓${status.behind || 0}`))
      sync.title = `${status.ahead || 0} ahead of and ${status.behind || 0} behind ${status.upstream}`
    } else {
      fill(sync)
      sync.title = 'No upstream branch'
    }
  }

  function setView(to) {
    view = to
    keep('view', to)
    drawViewButton()
    rebuild()
  }

  function drawViewButton() {
    const label = view === 'list' ? 'View as Tree' : 'View as List'
    fill(viewButton, glyph(view === 'list' ? 'tree' : 'list'))
    viewButton.title = label
    viewButton.setAttribute('aria-label', label)
  }

  // ---- The list.

  /** Lays the rows out anew from the groups, keeping what is picked and where the list is scrolled. */
  function rebuild() {
    const before = rows.findIndex((row) => row.key === cursor)
    rows = rowsOf(groups, { view, collapsed })
    const keys = new Set(rows.map((row) => row.key))
    pick = { selected: new Set([...pick.selected].filter((key) => keys.has(key))), anchor: keys.has(pick.anchor) ? pick.anchor : null }
    if (cursor && !keys.has(cursor)) cursor = rows.length ? rows[Math.min(Math.max(before, 0), rows.length - 1)].key : null
    none.hidden = !status || rows.length > 0
    list.hidden = rows.length === 0
    draw()
  }

  let framed = 0
  function draw() {
    spacer.style.height = `${rows.length * ROW}px`
    const top = list.scrollTop
    const tall = list.clientHeight || 600
    const first = Math.max(0, Math.floor(top / ROW) - 10)
    const last = Math.min(rows.length, Math.ceil((top + tall) / ROW) + 10)
    fill(spacer, rows.slice(first, last).map((row, i) => rowOf(row, first + i)))
    const at = rows.findIndex((row) => row.key === cursor)
    if (at >= first && at < last) list.setAttribute('aria-activedescendant', `${id}-${at}`)
    else list.removeAttribute('aria-activedescendant')
  }

  list.addEventListener('scroll', () => {
    cancelAnimationFrame(framed)
    framed = requestAnimationFrame(draw)
  })

  /** What can be done to a row, in the order it is offered: each as its icon, its name and what `act` does by it. */
  function actionsOf(row) {
    const all = row.kind === 'file' ? '' : ' All'
    return [
      row.kind === 'file' && row.entry.letter !== 'D' && ['open', 'Open File', 'open'],
      row.group === 'changes' && ['discard', row.kind === 'file' ? 'Discard Changes' : 'Discard All Changes', 'discard'],
      row.group === 'untracked' && ['trash', row.kind === 'file' ? 'Delete File' : 'Delete All Untracked Files', 'discard'],
      row.group === 'staged' ? ['minus', `Unstage${all} Changes`, 'unstage'] : ['plus', `Stage${all} Changes`, 'stage'],
    ].filter(Boolean)
  }

  /** A row's buttons, shown as it is pointed at. */
  function toolsOf(row) {
    return h('span', { class: 'ch-acts' }, actionsOf(row).map(([name, label, what]) => tool(name, label, { 'data-act': what, tabindex: '-1' })))
  }

  function rowOf(row, index) {
    const props = {
      id: `${id}-${index}`,
      class: ['ch-row', `ch-kind-${row.kind}`, pick.selected.has(row.key) && 'picked', row.key === cursor && 'cursor'],
      role: 'treeitem',
      'aria-selected': String(pick.selected.has(row.key)),
      'aria-level': String(row.depth + 1),
      'data-key': row.key,
      'data-index': String(index),
      'data-group': row.group,
    }
    let el
    if (row.kind === 'group') {
      el = h(
        'div',
        { ...props, 'aria-expanded': String(row.open), 'data-hmz': 'changes-group' },
        h('span', { class: ['ch-twist', row.open && 'open'] }, glyph('chevron')),
        h('span', { class: 'ch-title' }, row.title),
        toolsOf(row),
        h('span', { class: 'ch-count', 'data-hmz': 'changes-count' }, String(row.count)),
      )
    } else if (row.kind === 'dir') {
      el = h(
        'div',
        { ...props, 'aria-expanded': String(row.open), 'data-path': row.path, title: row.path },
        h('span', { class: ['ch-twist', row.open && 'open'] }, glyph('chevron')),
        h('span', { class: 'ch-name' }, row.name),
        toolsOf(row),
      )
    } else {
      const one = row.entry
      el = h(
        'div',
        { ...props, 'data-hmz': 'change', 'data-path': one.path, title: `${one.orig ? `${one.orig} → ` : ''}${one.path} • ${MEANING[one.letter]}` },
        one.orig ? h('span', { class: 'ch-orig' }, `${one.orig} → `) : null,
        h('span', { class: ['ch-name', one.letter === 'D' && 'gone'] }, one.name),
        view === 'list' && one.dir ? h('span', { class: 'ch-dir' }, one.dir) : null,
        h('span', { class: 'ch-grow' }),
        toolsOf(row),
        h('span', { class: `ch-letter st-${one.letter === '?' ? 'Q' : one.letter}`, 'data-hmz': 'change-letter' }, one.letter),
      )
    }
    el.style.setProperty('--depth', String(row.depth))
    el.style.top = `${index * ROW}px`
    // The same in its menu, which a right click and the menu key open, what cannot be undone
    // last: nothing where it has closed.
    menuOn(el, () => {
      if (closed) return []
      const items = actionsOf(row).map(([name, label, what]) => ({ label, glyph: PAGE[name], danger: what === 'discard', act: () => act(what, row) }))
      return [...items.filter((one) => !one.danger), '-', ...items.filter((one) => one.danger)]
    })
    return el
  }

  /** The entries an action on a row acts on: every picked row of its group where it is picked. */
  function targets(row) {
    if (pick.selected.has(row.key) && pick.selected.size > 1) return chosen(rows, pick.selected)[row.group] || row.entries
    return row.entries
  }

  spacer.addEventListener('click', (event) => {
    const at = event.target.closest('[data-key]')
    if (!at) return
    const row = rows[Number(at.dataset.index)]
    if (!row) return
    const button = event.target.closest('[data-act]')
    if (button) {
      event.stopPropagation()
      act(button.dataset.act, row)
      return
    }
    list.focus({ preventScroll: true })
    const toggle = event.ctrlKey || event.metaKey
    const range = event.shiftKey
    cursor = row.key
    if (row.kind === 'group') {
      fold(row)
      return
    }
    pick = picked(pick, rows.map((one) => one.key), row.key, { range, toggle })
    if (row.kind === 'dir' && !toggle && !range) fold(row)
    else draw()
    if (row.kind === 'file' && !toggle && !range) openDiff(row.entry)
  })

  spacer.addEventListener('dblclick', (event) => {
    const at = event.target.closest('[data-hmz=change]')
    if (at && !event.target.closest('[data-act]')) {
      const row = rows[Number(at.dataset.index)]
      if (row && row.entry.letter !== 'D') openFile(row.entry)
    }
  })

  function fold(row, open = !row.open) {
    if (open) collapsed.delete(row.key)
    else collapsed.add(row.key)
    rebuild()
  }

  function reveal(at) {
    if (at < 0) return
    if (at * ROW < list.scrollTop) list.scrollTop = at * ROW
    else if ((at + 1) * ROW > list.scrollTop + list.clientHeight) list.scrollTop = (at + 1) * ROW - list.clientHeight
  }

  list.addEventListener('keydown', (event) => {
    if (!rows.length) return
    const keys = rows.map((row) => row.key)
    let at = keys.indexOf(cursor)
    const row = rows[at]
    const go = (to) => {
      to = Math.max(0, Math.min(rows.length - 1, to))
      cursor = keys[to]
      pick = picked(pick, keys, cursor, { range: event.shiftKey })
      reveal(to)
      draw()
    }
    const mod = event.ctrlKey || event.metaKey
    if (event.key === 'ArrowDown') go(at < 0 ? 0 : at + 1)
    else if (event.key === 'ArrowUp') go(at < 0 ? 0 : at - 1)
    else if (event.key === 'Home') go(0)
    else if (event.key === 'End') go(rows.length - 1)
    else if (event.key === 'PageDown') go(at + Math.floor(list.clientHeight / ROW))
    else if (event.key === 'PageUp') go(at - Math.floor(list.clientHeight / ROW))
    else if (event.key === 'ArrowRight' && row && row.kind !== 'file') {
      if (row.open) go(at + 1)
      else fold(row, true)
    } else if (event.key === 'ArrowLeft' && row) {
      if (row.kind !== 'file' && row.open) fold(row, false)
      else {
        while (at > 0 && rows[at].depth >= row.depth) at--
        if (rows[at].depth < row.depth) go(at)
      }
    } else if (event.key === 'a' && mod) {
      pick = { selected: new Set(rows.filter((one) => one.kind !== 'group').map((one) => one.key)), anchor: pick.anchor }
      draw()
    } else if (event.key === ' ') {
      const by = pick.selected.size ? chosen(rows, pick.selected) : row ? { [row.group]: row.entries } : {}
      for (const [group, entries] of Object.entries(by)) run(moveOf(group), entries)
    } else if (event.key === 'Enter' && row) {
      if (row.kind === 'file') openDiff(row.entry)
      else fold(row)
    } else if ((event.key === 'Delete' || (event.key === 'Backspace' && mod)) && row) {
      if (actionsOf(row).some(([, , what]) => what === 'discard')) act('discard', row)
    } else if (menuKey(event) && row) {
      // The menu of the row the keys are on, under it: the list has the focus back as it closes.
      reveal(at)
      draw()
      menuOf(spacer.querySelector(`[data-index="${at}"]`), list)
    } else return
    event.preventDefault()
  })

  // ---- What is done to files.

  function act(what, row) {
    const entries = targets(row)
    if (what === 'open') return openFile(row.entry)
    if (what === 'discard') return discard(entries)
    return run(what, entries)
  }

  function openFile(one) {
    ctx.open('files', { path: placeOf(status.root, one.path) })
  }

  function move(entries) {
    if (!entries.length) return
    return run(moveOf(entries[0].group), entries)
  }

  async function run(what, entries, { quiet = false } = {}) {
    if (closed || !entries.length) return false
    fill(actError)
    try {
      await ctx.call(`env.git.${what}`, { paths: pathsOf(entries) })
      return true
    } catch (error) {
      failed(error, actError)
      return false
    } finally {
      if (!quiet) refresh({ hard: true })
    }
  }

  async function discard(entries) {
    if (closed || !entries.length) return
    if (!(await ctx.confirm(discardText(entries)))) return
    await run('discard', entries)
  }

  // ---- Committing.

  function drawHint() {
    const { length, level } = subjectHint(message.value)
    hint.textContent = length ? `${length}` : ''
    hint.className = `ch-hint ${level}`
    hint.title = level === 'over' ? 'The first line is past 72 characters.' : level === 'long' ? 'The first line is past 50 characters.' : ''
  }

  /** Why the last commit was refused or failed, said until the message is changed or another is tried. */
  let commitNote = null

  function drawCommit() {
    const conflicts = groups.merge.length > 0
    commitButton.disabled = closed || busy || conflicts
    commitButton.textContent = amend.checked ? 'Commit (Amend)' : 'Commit'
    reason.textContent = closed ? '' : conflicts ? 'Resolve the merge conflicts before committing.' : commitNote?.text || ''
    reason.classList.toggle('error', Boolean(!conflicts && commitNote?.failed))
  }

  async function commit() {
    if (closed || busy) return
    const plan = commitPlan({ groups, message: message.value, amend: amend.checked })
    commitNote = plan.action === 'refuse' ? { text: plan.why, failed: false } : null
    if (commitNote) return drawCommit()
    busy = true
    drawCommit()
    try {
      if (plan.action === 'stage') {
        const asked = `There are no staged changes. Stage all ${plan.paths.length} ${plan.paths.length === 1 ? 'change' : 'changes'} and commit ${plan.paths.length === 1 ? 'it' : 'them'} directly?`
        if (!(await ctx.confirm(asked))) return
        await ctx.call('env.git.stage', { paths: plan.paths })
      }
      await ctx.call('env.git.commit', { message: message.value, amend: amend.checked })
      message.value = ''
      keep('draft', '')
      amend.checked = false
      stash = null
      drawHint()
    } catch (error) {
      if (String(error?.message) === CLOSED) close()
      else commitNote = { text: error instanceof Error ? error.message : String(error), failed: true }
    } finally {
      busy = false
      drawCommit()
      refresh({ hard: true })
    }
  }

  /** What was written before amend filled the box with the last commit's, put back if amend is let go. */
  let stash = null
  amend.addEventListener('change', async () => {
    drawCommit()
    if (amend.checked) {
      if (commits === null) await loadLog()
      const last = commits?.[0]?.subject
      if (last && !message.value.trim()) {
        stash = message.value
        message.value = last
      }
    } else if (stash !== null && message.value === commits?.[0]?.subject) {
      message.value = stash
      stash = null
    }
    drawHint()
  })
  message.addEventListener('input', () => {
    keep('draft', message.value)
    drawHint()
    if (commitNote) {
      commitNote = null
      drawCommit()
    }
  })
  message.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault()
      commit()
    }
  })

  // ---- The commits and the snapshots.

  function drawCommits() {
    commitsCount.textContent = commits.length ? String(commits.length) : ''
    if (!commits.length) return fill(commitList, h('p', { class: 'ch-quiet' }, 'No commits yet.'))
    const now = Date.now()
    fill(
      commitList,
      commits.map((one) =>
        h(
          'div',
          { class: 'ch-commit-row', 'data-hmz': 'commit-row', title: `${one.hash}\n${one.author} • ${fullDate(one.date)}\n\n${one.subject}` },
          h('span', { class: 'ch-hash' }, String(one.hash).slice(0, 7)),
          h('span', { class: 'ch-subject' }, one.subject),
          h('span', { class: 'ch-author' }, one.author),
          h('span', { class: 'ch-when' }, relative(one.date, now)),
        ),
      ),
    )
  }

  /** What the last rewind was refused with, said until another is tried. */
  let snapNote = null

  function drawSnapshots() {
    const note = snapNote ? problem(snapNote) : null
    if (!snapshots.length) return fill(snapList, h('p', { class: 'ch-quiet' }, 'No snapshots yet.'), note)
    fill(
      snapList,
      note,
      snapshots.map((ref) =>
        h(
          'div',
          { class: 'ch-snapshot', 'data-hmz': 'snapshot' },
          h('span', { class: 'ch-ref', title: ref }, ref),
          h('button', { type: 'button', class: 'btn danger small', disabled: closed, onclick: () => rewind(ref) }, 'Rewind'),
        ),
      ),
    )
  }

  async function rewind(ref) {
    if (closed) return
    const asked = `Rewind this environment to ${ref}? Its working tree is reset to that snapshot: every change made since, committed or not, is lost.`
    if (!(await ctx.confirm(asked))) return
    snapNote = null
    try {
      await ctx.call('env.git.rewind', { ref })
    } catch (error) {
      if (String(error?.message) === CLOSED) return close()
      snapNote = error
    }
    drawSnapshots()
    refresh({ hard: true })
  }

  // ---- The diff.

  function closeDiff() {
    diff?.view?.destroy()
    diff = null
    pane.hidden = true
    root.classList.remove('diffing')
    fill(diffBody)
    drawBlank()
  }

  /**
   * Says that no diff is open, in the room one would have: none where the list has the panel
   * to itself, which is where the line that sizes it is not drawn.
   */
  function drawBlank() {
    blank.hidden = Boolean(diff) || !line.getClientRects().length
  }

  function drawDiffHead() {
    const one = diff.entry
    fill(
      diffTitle,
      h('span', { class: `ch-letter st-${one.letter === '?' ? 'Q' : one.letter}` }, one.letter),
      h('span', { class: 'ch-name' }, one.name),
      one.dir ? h('span', { class: 'ch-dir' }, one.dir) : null,
      h('span', { class: 'ch-side-label' }, diff.staged ? 'Index' : 'Working Tree'),
    )
    diffTitle.title = one.path
    const label = drawnAs() === 'side' ? 'Show the diff inline' : 'Show the diff side by side'
    fill(modeButton, glyph(drawnAs() === 'side' ? 'inline' : 'side'))
    modeButton.title = label
    modeButton.setAttribute('aria-label', label)
    const staging = diff.group !== 'staged'
    fill(diffMove, glyph(staging ? 'plus' : 'minus'))
    diffMove.title = staging ? 'Stage Changes' : 'Unstage Changes'
    diffMove.setAttribute('aria-label', diffMove.title)
    diffMove.hidden = closed
    drawCounter()
  }

  function drawCounter() {
    if (!diff || !diff.hunks) return (counter.textContent = '')
    const n = diff.hunks.length
    counter.textContent = n ? `${diff.at < 0 ? '–' : diff.at + 1} of ${n}` : 'No changes'
  }

  async function openDiff(one) {
    if (diff && diff.entry.key === one.key) return
    diff?.view?.destroy()
    diff = { entry: one, group: one.group, path: one.path, staged: one.group === 'staged', raw: null, view: null, hunks: null, at: -1, sides: null, allowed: false, big: false, size: 0 }
    pane.hidden = false
    root.classList.add('diffing')
    drawBlank()
    drawDiffHead()
    fill(diffBody, h('p', { class: 'loading', role: 'status' }, 'Reading the diff…'))
    await fetchDiff(diff, true)
  }

  /** Reads the diff again as the list is read again: a large one only when asked. */
  async function reloadDiff({ hard, changed }) {
    const d = diff
    const now = groups[d.group]?.find((one) => one.path === d.path)
    if (!now) {
      d.view?.destroy()
      d.view = null
      d.raw = null
      d.hunks = []
      drawCounter()
      fill(diffBody, h('p', { class: 'ch-notice', 'data-hmz': 'diff-notice' }, `${d.entry.name} has no changes here any more.`))
      return
    }
    d.entry = now
    // Read again as the list is, but a large one only when asked, and a middling one only once
    // the list says something changed.
    if (!hard && (d.big || (!changed && d.size > SMALL))) return
    await fetchDiff(d, false)
  }

  async function fetchDiff(d, first) {
    let said
    try {
      said = await ctx.call('env.git.diff', { path: d.path, staged: d.staged })
    } catch (error) {
      if (diff !== d) return
      if (String(error?.message) === CLOSED) return close()
      fill(diffBody, problem(error))
      return
    }
    if (diff !== d) return
    const raw = JSON.stringify([said.old, said.new, Boolean(said.binary)])
    if (raw === d.raw) return
    d.raw = raw
    drawDiffHead()
    const largest = Math.max(sizeOf(said.old), sizeOf(said.new))
    d.size = largest
    d.big = largest > LARGE
    if (said.binary) return binary(d, said)
    if (d.big && !d.allowed) {
      if (first) d.allowed = await ctx.confirm(`${d.entry.name} is ${bytesText(largest)}. A diff this large may be slow to draw. Draw it anyway?`)
      if (diff !== d) return
      if (!d.allowed) {
        d.hunks = []
        drawCounter()
        const show = h('button', { type: 'button', class: 'btn small', onclick: () => ((d.allowed = true), (d.raw = null), fetchDiff(d, false)) }, 'Show the diff')
        fill(diffBody, h('div', { class: 'ch-notice', 'data-hmz': 'diff-notice' }, h('p', {}, `${d.entry.name} is ${bytesText(largest)}: its diff is not drawn unless asked.`), show))
        return
      }
    }
    const old = decoded(said.old)
    const now = decoded(said.new)
    if (old.binary || now.binary) return binary(d, { old: said.old, new: said.new })
    d.sides = { old: old.text, now: now.text }
    d.hunks = hunks(old.text, now.text)
    if (d.at >= d.hunks.length) d.at = -1
    drawCounter()
    await drawEditor(d)
  }

  function binary(d, said) {
    d.view?.destroy()
    d.view = null
    d.hunks = []
    drawCounter()
    const sizes = [said.old !== null && said.old !== undefined ? `before ${bytesText(sizeOf(said.old))}` : 'added', said.new !== null && said.new !== undefined ? `after ${bytesText(sizeOf(said.new))}` : 'deleted']
    fill(diffBody, h('p', { class: 'ch-notice', 'data-hmz': 'diff-notice' }, `${d.entry.name} is a binary file (${sizes.join(', ')}): there is no text to compare.`))
  }

  async function drawEditor(d) {
    let cm
    try {
      cm = await codemirror()
    } catch {
      if (diff === d) fill(diffBody, problem('The editor could not be loaded.'))
      return
    }
    if (diff !== d || left) return
    const kept = scroller(d)?.scrollTop || 0
    d.view?.destroy()
    d.view = null
    fill(diffBody)
    colours = JSON.stringify(ctx.theme())
    const base = [cm.basicSetup, cm.EditorView.editable.of(false), cm.EditorState.readOnly.of(true), cm.themeFor(ctx.theme()), cm.languageFor(d.path)].filter(Boolean)
    if (drawnAs() === 'side') {
      d.view = new cm.MergeView({ a: { doc: d.sides.old, extensions: base }, b: { doc: d.sides.now, extensions: base }, parent: diffBody, collapseUnchanged: FOLD, gutter: true })
      d.view.dom.dataset.hmz = 'diff-side'
    } else {
      d.view = new cm.EditorView({ doc: d.sides.now, extensions: [...base, cm.unifiedMergeView({ original: d.sides.old, mergeControls: false, gutter: true, collapseUnchanged: FOLD })], parent: diffBody })
      d.view.dom.dataset.hmz = 'diff-inline'
    }
    d.cm = cm
    const at = scroller(d)
    if (at) at.scrollTop = kept
  }

  /** The editor showing the new side, and what scrolls the diff. */
  const newer = (d) => (d.view ? (d.view.b ? d.view.b : d.view) : null)
  const scroller = (d) => (d.view ? (d.view.b ? d.view.dom : d.view.scrollDOM) : null)

  function step(by) {
    const d = diff
    if (!d || !d.hunks || !d.hunks.length || !newer(d)) return
    const n = d.hunks.length
    d.at = d.at < 0 ? (by > 0 ? 0 : n - 1) : (d.at + by + n) % n
    const view = newer(d)
    const doc = view.state.doc
    const line = Math.min(d.hunks[d.at].fromB + 1, doc.lines)
    const pos = doc.line(line).from
    view.dispatch({ selection: { anchor: pos }, effects: d.cm.EditorView.scrollIntoView(pos, { y: 'center' }) })
    drawCounter()
  }

  function setMode(to) {
    mode = to
    keep('diff', to)
    if (!diff) return
    drawDiffHead()
    if (diff.sides) drawEditor(diff)
  }

  // The diff's own width, not the window's, says whether two sides fit: one drawn as nobody
  // chose is drawn again as that changes.
  const sized = new ResizeObserver(() => {
    drawBlank()
    const now = diffBody.clientWidth > 0 && diffBody.clientWidth < TIGHT
    if (now === tight) return
    tight = now
    if (mode || !diff) return
    drawDiffHead()
    if (diff.sides) drawEditor(diff)
  })
  sized.observe(diffBody)
  sized.observe(root)

  /** The diff drawn again in the page's colours, once they change. */
  let colours = JSON.stringify(ctx.theme())
  function rethemed() {
    const now = JSON.stringify(ctx.theme())
    if (now === colours) return
    colours = now
    if (diff?.sides) drawEditor(diff)
  }
  const themed = new MutationObserver(rethemed)
  themed.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'style', 'class'] })
  const scheme = matchMedia('(prefers-color-scheme: dark)')
  scheme.addEventListener('change', rethemed)

  /**
   * F7 steps through the changes of the diff open, pressed in the panel -- or nowhere, while the
   * panel is seen: a browser that gives a button pressed no focus leaves the keys on the page.
   */
  function keyed(event) {
    if (event.key !== 'F7' || !diff) return
    const at = document.activeElement
    if (!root.contains(at) && !(at === document.body && seenNow())) return
    event.preventDefault()
    step(event.shiftKey ? -1 : 1)
  }
  document.addEventListener('keydown', keyed)

  // ---- When it reads again.

  const seenNow = () => !document.hidden && el.isConnected && el.getClientRects().length > 0
  const poll = setInterval(() => seenNow() && refresh(), POLL)
  const focused = () => refresh({ hard: true })
  const shown = () => !document.hidden && refresh({ hard: true })
  addEventListener('focus', focused)
  document.addEventListener('visibilitychange', shown)
  let working = 0
  let turn = null
  const offs = [
    ctx.on('env_used', (said) => said.env === ctx.env?.id && refresh({ hard: true })),
    // A turn ended: one of the sessions working is no longer, or a chat's turn is done.
    ctx.on('sessions', (said) => {
      const now = (said.working || []).length
      if (now < working) refresh({ hard: true })
      working = now
    }),
    ctx.on('run', (said) => {
      if (said.turn === 'done' && turn === 'running') refresh({ hard: true })
      turn = said.turn
    }),
    ctx.on('ended', () => refresh({ hard: true })),
  ]

  drawViewButton()
  drawHint()
  drawCommit()
  await refresh({ hard: true })

  return {
    leave() {
      left = true
      clearInterval(poll)
      cancelAnimationFrame(framed)
      removeEventListener('focus', focused)
      document.removeEventListener('visibilitychange', shown)
      document.removeEventListener('keydown', keyed)
      themed.disconnect()
      sized.disconnect()
      scheme.removeEventListener('change', rethemed)
      for (const off of offs) if (typeof off === 'function') off()
      diff?.view?.destroy()
      diff = null
    },
    /** Opens the diff of a file, the first group holding it, as `{path}` names it. */
    reveal({ path } = {}) {
      for (const group of ['merge', 'changes', 'untracked', 'staged']) {
        const one = groups[group].find((entry) => entry.path === path)
        if (one) return openDiff(one)
      }
    },
  }
}
