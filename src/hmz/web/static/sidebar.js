// The sidebar, as Claude's desktop app keeps its own: a title row that hides it and steps back and
// forward, a new chat, a new epic, finding one, the flows, and the chats and epics of this machine
// in groups -- by folder, by date or as one, as `Group and sort` says -- each a row of its title
// and how it stands, with a menu at its end; a flow's epic opens out into its agents, and each
// agent into the sessions it opened, and a chat, its one conversation, opens into nothing. The
// chats are read by `chat.list` and the epics by `runs.list`, as one list. Under
// them, in one row, the daemon the page is of, how many epics are going on it and a picker of the
// daemons, and the settings. A splitter on its right edge sizes it.

import { call, daemon, exported, given, hash, hello, known, onState, poll, reconnect, refresh, stateOf, toDaemon } from './api.js'
import { ask } from './held.js'
import { t } from './i18n.js'
import { warm } from './logged.js'
import { harnessName } from './names.js'
import { pick } from './importing.js'
import { chain } from './layers.js'
import { copy, menuButton, menuOn, posted, toast } from './ui.js'
import { ago, fill, flowName, h, headline, icon, iconButton, svg, tone, when } from './dom.js'
import { chatActions, retitling } from './chat-actions.js'
import { chatRow, harnessRow, pathOf } from './chats.js'
import { chatting, markOf, sessionsOf } from './epic.js'
import { notifying } from './notifications.js'
import { missing, nameOf, workspaceAt } from './places.js'
import { CHAT_SAID, chatState, epicHow, epicSaid, rowTitle, shortcut, wording } from './sidebar-rows.js'
import { DEFAULTS, GROUPS, SHOWS, SORTS, WIDTHS, arranged, paged, shownFolders, toggled, viewOf, viewText, widthOf } from './sidebar-view.js'
import { choice, dragged, keep, kept, menu, settleSidebar, submenu, toggleSidebar } from './shell.js'

/** How many chats, and how many epics, a page of the list holds. */
const PAGE = 60

/** How many harness sessions of a workspace are read, and how long what was read stands. */
const HARNESSED = 50
const HARNESSED_FOR = 15000

/** Which entry of the sidebar an address is of: a new chat's own, else the one its first part names. */
const entryOf = (parts) => (parts[0] === 'new' && parts[1] === 'chat' ? 'new/chat' : parts[0] || 'new')

/** What this browser keeps of the list: the rows pinned, those marked unread, and what `Group and sort` chose. */
const PINNED = 'hmz-pinned'
const UNREAD = 'hmz-unread'
const VIEW = 'hmz-list'

/** Whether the device has nothing to point with, so that nothing is said only where it points. */
const touched = matchMedia('(hover: none)')

/** A row by the daemon it is of, as two daemons may name theirs alike. */
const markKey = (name, of = daemon()) => `${of} ${name}`

/** The names kept under a key, of whichever daemon. */
function marks(key) {
  try {
    const said = JSON.parse(kept(key, '[]'))
    return Array.isArray(said) ? said : []
  } catch {
    return []
  }
}

/** The rows of the daemon shown that are kept under a key, by name. */
function marksHere(key) {
  const mine = `${daemon()} `
  return new Set(marks(key).filter((one) => one.startsWith(mine)).map((one) => one.slice(mine.length)))
}

/** Keeps a row under a key, or forgets it there, and says so for the list drawn. */
function mark(key, name, on, of) {
  const now = toggled(marks(key), markKey(name, of), on)
  keep(key, now.length ? JSON.stringify(now) : null)
  window.dispatchEvent(new CustomEvent('hmz:list'))
}

/** Whether a row is unread: marked so here, by its menu or by a notice of it. */
const unreadHere = (name) => marksHere(UNREAD).has(name)

/**
 * The splitter on the sidebar's right edge: dragged, or moved by the arrow keys, it sizes the
 * sidebar, as wide as this browser last left it; double-clicked, it is as wide as it usually is.
 */
function splitter() {
  const el = h('div', { class: 'side-split', role: 'separator', tabindex: '0', 'aria-orientation': 'vertical', 'aria-label': t('Resize sidebar'), title: t('Resize sidebar'), 'aria-controls': 'sidebar', 'aria-valuemin': WIDTHS.least, 'aria-valuemax': WIDTHS.most, 'data-hmz': 'side-split' })
  const set = (wide, keeps) => {
    const now = widthOf(wide)
    // On the frame it sizes, not the root, whose own properties a theme painted takes away.
    document.querySelector('.app').style.setProperty('--side-wide', `${now}px`)
    el.setAttribute('aria-valuenow', String(now))
    if (keeps) keep('hmz-side-wide', now === WIDTHS.usual ? null : String(now))
  }
  set(kept('hmz-side-wide', ''), false)
  el.addEventListener('pointerdown', (event) => {
    if (event.button) return
    event.preventDefault()
    el.setPointerCapture(event.pointerId)
    el.classList.add('dragging')
    // It is moved by as far as the pointer went, from wherever on it the pointer took hold: a
    // press that goes nowhere sizes nothing.
    const from = Number(el.getAttribute('aria-valuenow'))
    let moved = false
    const move = (at) => {
      if (at.clientX === event.clientX && !moved) return
      moved = true
      set(from + at.clientX - event.clientX, false)
    }
    const done = (at) => {
      el.classList.remove('dragging')
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerup', done)
      el.removeEventListener('pointercancel', done)
      if (at.type === 'pointerup') move(at)
      if (moved) set(el.getAttribute('aria-valuenow'), true)
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', done)
    el.addEventListener('pointercancel', done)
  })
  el.addEventListener('keydown', (event) => {
    const now = Number(el.getAttribute('aria-valuenow'))
    const to = { ArrowLeft: now - 16, ArrowRight: now + 16, Home: WIDTHS.least, End: WIDTHS.most }[event.key]
    if (to === undefined) return
    event.preventDefault()
    set(to, true)
  })
  el.addEventListener('dblclick', () => set(WIDTHS.usual, true))
  return el
}

/**
 * The mark, `>_` cut from flat planes, drawn in the page: its chevron in the ink of the side
 * shown -- a picture of it would take the system's, whichever side the page shows -- and its
 * wedge in the mark's green.
 */
function brandMark() {
  return svg(
    'svg',
    { class: 'brand-mark', viewBox: '0 0 100 100', width: '24', height: '24', 'aria-hidden': 'true' },
    svg('polygon', { class: 'ink', points: '12,16 32,16 62,50 32,84 12,84 42,50' }),
    svg('polygon', { class: 'green', points: '60,84 94,84 94,64 60,74' }),
  )
}

/**
 * @param {HTMLElement} root The sidebar.
 * @param {{here: string}} context Where `hmz web` started, which Local offers first.
 * @param {() => {parts: string[], query: URLSearchParams}} where Where the page is.
 */
export function mountSidebar(root, context, where) {
  const list = h('nav', { class: 'side-runs', 'aria-label': t('Chats and epics'), 'data-hmz': 'epics' }, h('p', { class: 'side-quiet', role: 'status' }, t('Loading…')))
  // How many installed flows have a newer release, as the indexes were fetched as it started.
  const updates = h('span', { class: 'side-badge', 'data-hmz': 'updates', hidden: true })
  poll('flowverses.list', {}, 60000, (answer) => {
    const count = answer ? answer.updates.length : 0
    updates.hidden = !count
    updates.textContent = String(count)
    updates.title = count ? t('{n} flows have a newer release', { n: count }) : ''
  })
  const bar = daemonBar()
  // The keys the shortcuts are pressed with, as this system writes them: at a row's end a key
  // apiece, and off a Mac a plus between them. They are drawn for the eye; the row says them to
  // a reader by `aria-keyshortcuts`, and is named by its label alone.
  const mac = /Mac|iPhone|iPad/.test(navigator.platform)
  const keys = (which) =>
    h(
      'kbd',
      { class: 'side-keys', 'data-os': mac ? 'mac' : 'pc', 'aria-hidden': 'true' },
      shortcut(which, mac).map((key, at) => [at && !mac ? '+' : null, h('kbd', {}, key)]),
    )
  const pressed = (which) => [mac ? 'Meta' : 'Control', ...shortcut(which, false).slice(1)].join('+')
  fill(
    root,
    dragged(
      h(
        'div',
        { class: 'side-top' },
        // The mark first, then what a desktop app's title row holds, in its order.
        h('a', { class: 'brand', href: hash('/new/chat'), 'data-nav': 'new/chat', 'aria-label': t('Humanize, a new chat') }, brandMark(), h('strong', {}, 'humanize')),
        iconButton('sidebar', t('Hide sidebar'), { class: 'side-fold', onclick: () => toggleSidebar(false), 'aria-controls': 'sidebar' }),
        iconButton('back', t('Back@@history'), { class: 'side-back', 'data-hmz': 'back', onclick: () => history.back() }),
        iconButton('forward', t('Forward'), { class: 'side-forward', 'data-hmz': 'forward', onclick: () => history.forward() }),
      ),
    ),
    h(
      'div',
      { class: 'side-nav' },
      // A new chat first, as a chat app's sidebar begins; a new epic of a flow apart from it.
      h('a', { href: hash('/new/chat'), 'data-nav': 'new/chat', 'aria-keyshortcuts': pressed('chat') }, icon('compose'), h('span', {}, t('New chat')), keys('chat')),
      h('a', { href: hash('/new'), 'data-nav': 'new' }, icon('epic'), h('span', {}, t('New epic'))),
      h('a', { href: hash('/search'), 'data-nav': 'search', 'aria-keyshortcuts': pressed('search') }, icon('search'), h('span', {}, t('Search')), keys('search')),
      h('a', { href: hash('/flows'), 'data-nav': 'flows' }, icon('flows'), h('span', {}, t('Flows')), updates),
    ),
    h('div', { class: 'side-scroll' }, list),
    h(
      'div',
      { class: 'side-foot' },
      bar.el,
      iconButton('gear', t('Settings'), { class: 'side-gear', 'data-hmz': 'settings-open', onclick: () => (location.hash = hash('/settings/general')) }),
    ),
    splitter(),
  )
  // What is offered between the epics, rather than on one of them.
  menuOn(list, () => [{ label: t('Import'), glyph: 'file', act: pick }])
  root.addEventListener('click', (event) => {
    if (event.target.closest('a[href]')) settleSidebar()
  })

  let limit = PAGE
  /** The rows listed, chats and epics as one, and how many of them the daemon holds. */
  let data = null
  /** What `chat.list` and `runs.list` last answered, and which of them the list still waits on. */
  let read = {}
  let waiting = new Set()
  /** What each host runs, which says what a chat going waits on. */
  let running = []
  let places = null
  /** What `Group and sort` chose, as this browser last left it. */
  let view = viewOf(kept(VIEW, ''))
  /** How many rows each group shows, by its key, where `Show N more` was pressed. */
  const shown = new Map()
  /** The group whose `Show N more` asked for the rows being read, `:list` where the list's `Show more` did, or none. */
  let loading = null
  /** How many rows were listed when more were asked for, and whether asking brought none. */
  let asked = null
  let dry = false
  /** Whether the list is to be drawn again once the menu open in it has closed. */
  let stale = false
  /** Whether a press is on the list: a finger or a button down on it and not yet up. */
  let pressing = false
  /** Which epics are opened out, by name, as this browser last left them. */
  const opened = new Set(JSON.parse(kept('hmz-opened', '[]') || '[]'))
  /** Which epics were folded here, the one in front among them. */
  const folded = new Set()
  /** Which groups are folded away, a workspace by its path, as this browser last left them. */
  const shut = new Set(JSON.parse(kept('hmz-shut', '[]') || '[]'))
  /** Each epic opened out, as its epic says it, with how it stood when read. */
  const details = new Map()
  /** Each row pinned that the list read does not hold, as its epic says it, with when it was read. */
  const strays = new Map()
  /** Whether the sessions each harness had of its own are listed, as the setting says. */
  let outside = false
  /** Those sessions of each workspace, by its path, with when they were read. */
  const harnessed = new Map()

  let stop = () => {}
  /** The list of what was read: the chats and the epics, each as a row of it. */
  const gather = () => {
    if (read.chats && read.runs) data = { runs: [...read.chats.chats.map((one) => chatRow(one, running)), ...read.runs.runs], total: read.chats.total + read.runs.total }
  }
  const watch = () => {
    stop()
    waiting = new Set(['chats', 'runs'])
    const heard = (which) => (answer, error) => {
      if (answer) read[which] = answer
      waiting.delete(which)
      gather()
      // A page more was asked of both: how many it brought is told once both have answered.
      if (!waiting.size) {
        // Asked for more and refused, or brought none: the list asks for no more by itself.
        if (asked !== null) dry = Boolean(error) || !data || data.runs.length <= asked
        asked = null
        loading = null
      }
      if (!data) fill(list, h('p', { class: 'error', role: 'alert' }, error ? error.message : t('Loading…')))
      else draw()
      // The latest of them are read ahead, behind everything else, to open at once.
      if (data && !waiting.size) warm(data.runs)
    }
    const stops = [poll('chat.list', { limit }, 4000, heard('chats')), poll('runs.list', { limit }, 4000, heard('runs'))]
    stop = () => stops.forEach((one) => one())
  }
  /** Reads a page more of the list, for a group or for the list itself. */
  const further = (by) => {
    loading = by
    asked = data.runs.length
    limit += PAGE
    watch()
  }
  let unplace = () => {}
  const watchPlaces = () => {
    unplace()
    // Where `hmz web` started is a directory of Local's alone.
    unplace = poll('workspaces.list', given({ here: daemon() === 'local' ? context.here : '' }), 10000, (answer) => {
      if (!answer) return
      places = answer
      if (data) draw()
    })
  }
  watchPlaces()
  // How many epics are going on the daemon shown, as its hosts say.
  // An Ai-chan conversation is hers, listed in her drawer, and no epic of the sidebar's to count;
  // and a chat is never going, whether or not a host holds it.
  poll('hosts.running', {}, 4000, (answer) => {
    if (!answer) return
    running = answer.running
    bar.going(running.filter((one) => !/^(ai|chat):/.test(String(one.slot || ''))).length)
    gather()
    if (data) draw()
  })

  // Whether each harness's own sessions are listed, as `General` set it.
  poll('settings.get', {}, 30000, (answer) => {
    if (!answer || outside === (answer.harness_sessions === true)) return
    outside = answer.harness_sessions === true
    if (data) draw()
  })

  /** The sessions each harness had of its own in a workspace, as rows, read again where they are old. */
  function outsiders(path) {
    if (!outside) return []
    const read = harnessed.get(path)
    if (!(read && (read.asking || Date.now() - read.at < HARNESSED_FOR))) {
      harnessed.set(path, { ...(read || { rows: [] }), asking: true })
      const of = daemon()
      const told = (rows) => {
        if (of !== daemon()) return
        const changed = JSON.stringify(rows) !== JSON.stringify((harnessed.get(path) || { rows: [] }).rows)
        harnessed.set(path, { rows, at: Date.now() })
        if (data && changed) draw()
      }
      // One that cannot be read lists none, and is asked again later.
      call('chat.harness.list', { workspace: path, limit: HARNESSED }).then((answer) => told(answer.sessions.map(harnessRow)), () => told([]))
    }
    return harnessed.get(path).rows
  }

  /** Keeps what `Group and sort` chose, and draws the list by it. */
  const choose = (next) => {
    view = viewOf(JSON.stringify(next))
    keep(VIEW, viewText(view))
    if (data) draw()
  }

  /**
   * What `Group and sort` holds, as a desktop app's does: how to group, how to sort, what to
   * show -- and, on the heading of a folder or of `No folder`, that workspace's own settings.
   *
   * @param {() => void} close
   * @param {string | null} [folder] The folder whose heading it is opened on, '' for `No folder`, null for any other group.
   */
  function listMenu(close, folder = null) {
    const one = (role, label, on, change) => {
      const el = choice({ label, chosen: on, act: () => choose({ ...view, ...change }), close })
      el.setAttribute('role', role)
      el.setAttribute('aria-checked', String(on))
      return el
    }
    const said = (all, key) => all.find(([name]) => name === key)[1]
    const settings = folder === null ? null : choice({ label: t('Workspace settings'), glyph: 'gear', href: hash(workspaceAt(folder)), close })
    if (settings) settings.dataset.hmz = 'workspace-settings'
    return h(
      'div',
      { class: 'list-menu', 'data-hmz': 'list-menu' },
      submenu({ label: t('Group by'), about: said(GROUPS, view.group), hmz: 'group-by', items: () => GROUPS.map(([key, label]) => one('menuitemradio', label, view.group === key, { group: key })) }),
      submenu({ label: t('Sort by'), about: said(SORTS, view.sort), hmz: 'sort-by', items: () => SORTS.map(([key, label]) => one('menuitemradio', label, view.sort === key, { sort: key })) }),
      submenu({ label: t('Show'), hmz: 'show', items: () => SHOWS.map(([key, label]) => one('menuitemcheckbox', label, view[key], { [key]: !view[key] })) }),
      h('hr'),
      choice({ label: t('Reset to defaults'), act: () => choose(DEFAULTS), close }),
      settings ? [h('hr'), settings] : null,
    )
  }

  /** The rows pinned that the list read does not hold, each read by itself, and again where it is old. */
  function strayed(pins) {
    const listed = new Set(data.runs.map((run) => run.name))
    const rows = []
    for (const name of pins) {
      if (listed.has(name)) continue
      const read = strays.get(name)
      if (read && read.run) rows.push(read.run)
      if (read && (read.asking || Date.now() - read.at < 30000)) continue
      strays.set(name, { ...(read || {}), asking: true })
      const of = daemon()
      const told = (run) => {
        if (of !== daemon()) return
        strays.set(name, { run, at: Date.now() })
        if (data) draw()
      }
      // An epic, else a chat by that id; one that cannot be read is no row.
      call('runs.get', { name })
        // An archived chat is listed nowhere but among its workspace's archived chats.
        .catch(() => call('chat.get', { chat: name }).then((one) => (one.archived ? null : chatRow(one, running))))
        .then(told, () => told(null))
    }
    return rows
  }

  function draw() {
    // A menu open from the list, or at the pointer, acts on the rows it was opened over, as a
    // title's field stands in its row: the list is drawn again once that is closed.
    if (list.querySelector('.title-edit') || chain().some((one) => (one.anchor ? list.contains(one.anchor) : one.kind !== 'panel'))) {
      stale = true
      return
    }
    stale = false
    const held = spot()
    const { parts, query } = where()
    const here = parts[0] === 'epics' || parts[0] === 'chats' ? parts[1] : parts[0] === 'harness' ? `harness:${parts[1]}:${parts[2]}` : ''
    for (const link of root.querySelectorAll('.side-nav a')) {
      if (link.dataset.nav === entryOf(parts)) link.setAttribute('aria-current', 'page')
      else link.removeAttribute('aria-current')
    }
    const pins = marksHere(PINNED)
    const unread = marksHere(UNREAD)
    const unseen = (run) => unread.has(run.name)
    // The rows pinned first, then every group `Group and sort` makes of the rest.
    const groups = arranged({ workspaces: shownFolders(places ? places.workspaces : []), runs: [...data.runs, ...strayed(pins)], view, pinned: pins, chat: chatting })
    const scrolled = list.parentElement.scrollTop
    const chosen = parts[0] === 'new' ? query.get('workspace') || '' : ''
    const more = data.runs.length < data.total && !dry
    let hidden = 0
    fill(
      list,
      groups.map((group, at) => {
        // A folder is a workspace, by its path; the rows of none are a group like any other.
        const folder = group.kind === 'folder' && Boolean(group.path)
        const open = !shut.has(group.key)
        const called = folder ? nameOf(group.path) : group.label
        // A folder whose directory went keeps its rows, which are still read, and starts nothing.
        const lost = folder && gone(group.path)
        // After its chats and epics, the sessions each harness had of its own there, where listed.
        const { rows, more: rest } = paged(folder && open ? [...group.runs, ...outsiders(group.path)] : group.runs, shown.get(group.key), here)
        hidden += rest
        // A heading over its rows, not a row: the group's name, said quietly, which folds them
        // away where it is pressed -- the arrow after it says which way it stands.
        const toggle = h(
          'button',
          { class: 'side-toggle', type: 'button', 'aria-expanded': String(open) },
          h('span', { class: 'side-folder-name', id: `side-group-${at}`, title: folder ? (lost ? goneAt(group.path) : group.path) : null }, h('span', { class: 'side-label' }, called), lost ? h('span', { class: 'side-gone', 'data-hmz': 'folder-missing' }, t('missing')) : null),
          icon('chevron'),
        )
        /** Gives the focus back to something of this group, once the list was drawn again. */
        const focus = (selector) => {
          for (const one of list.querySelectorAll('.side-group')) if (one.dataset.group === group.key) one.querySelector(selector)?.focus()
        }
        toggle.addEventListener('click', () => {
          if (open) shut.add(group.key)
          else shut.delete(group.key)
          keep('hmz-shut', JSON.stringify([...shut].slice(-60)))
          draw()
          focus('.side-toggle')
        })
        const sort = iconButton('sliders', t('Group and sort'), { class: 'side-sort', 'data-hmz': 'list-menu-open' })
        menu(sort, (close) => listMenu(close, group.kind === 'folder' ? group.path : null), { label: t('Group and sort') })
        // The group of no folder starts one in none; any other group names no folder to start in.
        const fresh = folder ? `/new/chat?workspace=${encodeURIComponent(group.path)}` : group.kind === 'folder' ? '/new/chat?scratch=1' : '/new/chat'
        const head = h(
          'div',
          { class: ['side-folder', folder && chosen === group.path && 'current', lost && 'gone'] },
          h('h3', { class: 'side-folder-head' }, toggle),
          !open && group.runs.some(unseen) ? marked() : null,
          sort,
          lost ? null : iconButton('plus', folder ? t('New chat in {name}', { name: called }) : t('New chat'), { class: 'side-add', 'data-hmz': 'group-add', onclick: () => (location.hash = hash(fresh)) }),
        )
        if (folder) menuOn(head, () => folderMenu(group.path, group.runs.length, { label: open ? t('Collapse') : t('Expand'), glyph: 'chevron', act: () => toggle.click() }))
        // What the group does not show, brought by its last row: all of it that was read, and,
        // where the daemon holds more than was, a page more of the list.
        const last = rest
          ? h(
              'button',
              {
                class: 'side-more',
                type: 'button',
                'data-hmz': 'group-more',
                // Described by its group's name, as each of several is told from the others unseen.
                'aria-describedby': `side-group-${at}`,
                onclick: () => {
                  // All of it from now on, whatever comes to be listed in it later.
                  shown.set(group.key, Infinity)
                  if (more && !loading) further(group.key)
                  draw()
                  focus('.side-more')
                },
              },
              t('Show {n} more', { n: rest }),
            )
          : loading === group.key
            ? h('button', { class: 'side-more', type: 'button', 'data-hmz': 'group-more', disabled: true }, t('Loading…'))
            : null
        return h(
          'section',
          { class: 'side-group', 'data-hmz': folder ? 'workspace' : 'group', 'data-group': group.key, 'data-path': folder ? group.path : null },
          head,
          !open
            ? null
            : group.kind === 'folders'
              ? h('ul', { role: 'list' }, group.folders.map(place))
              : [
                  rows.length
                    ? h('ul', { role: 'list' }, rows.map((run) => item(run, here, parts, unseen(run))))
                    : [
                        h('p', { class: 'side-quiet nested' }, t('Nothing here yet')),
                        // What puts something in it, where its rows would be; a folder that went offers nothing.
                        lost ? null : h('button', { class: 'side-more', type: 'button', 'data-hmz': 'group-empty-new', 'aria-describedby': `side-group-${at}`, onclick: () => (location.hash = hash(fresh)) }, t('New chat')),
                      ],
                  last,
                ],
        )
      }),
      // Every row read is shown and the daemon holds more: the list ends with what reads a page
      // more, so that no row waits on something nothing on the page could bring.
      (more && !hidden && loading === null) || loading === ':list'
        ? h(
            'button',
            { class: 'side-more side-more-list', type: 'button', 'data-hmz': 'list-more', disabled: loading !== null, onclick: () => further(':list') },
            loading === null ? t('Show more') : t('Loading…'),
          )
        : null,
    )
    list.parentElement.scrollTop = scrolled
    refocus(held)
  }

  /** What in the list holds the focus, said so that it is found once the list is drawn again. */
  function spot() {
    const el = document.activeElement
    if (!el || !list.contains(el)) return null
    const pick = el.tagName === 'A' ? `a[href="${CSS.escape(el.getAttribute('href') || '')}"]` : `.${[...el.classList].find((one) => one.startsWith('side-'))}`
    return { pick, ...whose(el) }
  }

  /** The group and the row something in the list is of. */
  function whose(el) {
    const row = el.closest('.side-item')
    return { group: el.closest('.side-group')?.dataset.group, row: row ? row.dataset.epic || row.dataset.place : undefined }
  }

  /**
   * Gives the focus back to what held it before the list was drawn again: the same thing of the
   * same row, wherever the row now stands, or of the same group; and what sorts the list, whose
   * group may be gone, to the first there is.
   */
  function refocus(held) {
    if (!held || list.contains(document.activeElement)) return
    const all = [...list.querySelectorAll(held.pick)]
    const same = (el, keys) => keys.every((key) => whose(el)[key] === held[key])
    const found = all.find((el) => same(el, ['group', 'row'])) || (held.row ? all.find((el) => same(el, ['row'])) : held.pick === '.side-sort' ? all[0] : null)
    found?.focus({ preventScroll: true })
  }

  /** What is said of a folder whose directory went, before its path. */
  const goneAt = (path) => t('This folder is no longer on this machine: {path}', { path })
  /** Whether a folder's directory went, as the daemon answered last. */
  const gone = (path) => missing(path, places)

  /**
   * What a folder offers, on its heading or on its row among `Folders`: `fold` folds a heading.
   * One whose directory went offers nothing that starts there -- no chat, no epic.
   */
  function folderMenu(path, count, fold = null) {
    const at = encodeURIComponent(path)
    const lost = gone(path)
    return [
      { head: path, path: true },
      // Under its path, which is cut short from its start: said whole.
      lost ? { head: t('This folder is no longer on this machine.') } : null,
      lost ? null : { label: t('New chat here'), glyph: 'thread', href: hash(`/new/chat?workspace=${at}`) },
      lost ? null : { label: t('New epic here'), glyph: 'new', href: hash(`/new?workspace=${at}`) },
      { label: t('Search here'), glyph: 'search', href: hash(`/search?workspace=${at}`) },
      '-',
      { label: t('Copy path'), glyph: 'copy', act: () => copy(path, t('Path copied')) },
      fold,
      '-',
      // The folder's own settings, a dialog of its own and no page of Settings.
      { label: t('Workspace settings'), glyph: 'gear', href: hash(workspaceAt(path)) },
      { label: t('Usage'), glyph: 'chart', href: hash(workspaceAt(path, 'usage')) },
      count ? null : { label: t('Forget'), danger: true, act: () => forget(path) },
    ]
  }

  /** A folder as a row of `Folders`, where the list is not grouped by them: a new chat in it, and its menu. */
  function place(folder) {
    const more = iconButton('more', t('More options'), { class: 'side-menu', 'data-hmz': 'row-menu' })
    // One whose directory went opens what it still holds, searched, where another opens a new chat.
    const lost = gone(folder.path)
    const row = h(
      'div',
      { class: ['side-run side-place', lost && 'gone'] },
      h(
        'a',
        { href: hash(`/${lost ? 'search' : 'new/chat'}?workspace=${encodeURIComponent(folder.path)}`), title: lost ? goneAt(folder.path) : folder.path, 'data-hmz': 'place' },
        h('span', { class: 'side-label' }, nameOf(folder.path)),
        lost ? h('span', { class: 'side-status side-gone', 'data-hmz': 'folder-missing' }, t('missing')) : null,
      ),
      more,
    )
    menuOn(row, () => folderMenu(folder.path, folder.count))
    menuButton(more, row)
    return h('li', { class: 'side-item', 'data-place': folder.path }, row)
  }

  /** A session a harness had of its own: its first line, quietly, and its harness; only read. */
  function outsider(run, here) {
    const at = run.name === here
    const link = h(
      'a',
      { href: hash(pathOf(run)), 'aria-current': at ? 'page' : null, title: `${run.task}\n${t('{harness} session', { harness: harnessName(run.harness) })} · ${when(run.updated)}`, 'data-hmz': 'harness-session', 'data-harness': run.harness },
      h('span', { class: 'side-label' }, headline(run.task)),
      h('span', { class: 'side-status side-harness-name' }, harnessName(run.harness)),
    )
    const row = h('div', { class: ['side-run', 'side-chat', 'side-harness', at && 'current'] }, link)
    menuOn(row, () => [
      { head: t('{harness} session', { harness: harnessName(run.harness) }) },
      { label: t('Open'), glyph: 'open', href: hash(pathOf(run)) },
      '-',
      { label: t('Copy first message'), glyph: 'copy', act: () => copy(run.task, t('Message copied')) },
      { label: t('Copy session ID'), glyph: 'copy', act: () => copy(run.id, t('Session ID copied')) },
    ])
    return h('li', { class: 'side-item', 'data-epic': run.name }, row)
  }

  function item(run, here, parts, unseen) {
    if (run.kind === 'harness') return outsider(run, here)
    // A chat is only its conversation, running while its agent answers and done otherwise: the
    // row is the chat, with nothing under it, current wherever in it the page is.
    const chat = chatting(run)
    const shown = !chat && (opened.has(run.name) || run.name === here) && !folded.has(run.name)
    const link = hash(pathOf(run))
    const toggle = chat ? null : h('button', { class: 'side-toggle', type: 'button', 'aria-expanded': String(shown), 'aria-label': shown ? t('Collapse') : t('Expand') }, icon('chevron'))
    toggle?.addEventListener('click', () => {
      if (shown) {
        opened.delete(run.name)
        folded.add(run.name)
      } else {
        opened.add(run.name)
        folded.delete(run.name)
      }
      keep('hmz-opened', JSON.stringify([...opened].slice(-40)))
      draw()
      // The list was drawn again: the toggle pressed is the one that keeps the focus.
      for (const one of list.querySelectorAll('.side-item')) if (one.dataset.epic === run.name) one.querySelector('.side-toggle').focus()
    })
    const how = markOf(chat ? run.how : epicHow(run, running), { chat, turn: run.turn, asked: run.asking || [], epic: run.name })
    const at = run.name === here && (chat || !parts[2])
    // A chat's row says how it stands only where there is something to say.
    const state = chat ? chatState(how) : ''
    const title = rowTitle(run, { chat, state, how, flow: flowName(run.flow), began: when(run.began) })
    // What can be done to it, opened by the button at the row's end as by a right click on it.
    const more = iconButton('more', t('More options'), { class: 'side-menu', 'data-hmz': 'row-menu' })
    const row = chat
      ? // A chat, as a chat app lists one: what was asked and, only where it goes or failed, the
        // word for it; one that waits on its person is marked by a dot, as one unread is.
        h(
          'div',
          { class: ['side-run', 'side-chat', at && 'current'] },
          h(
            'a',
            { href: link, 'aria-current': at ? 'page' : null, title, 'data-hmz': 'epic', 'data-kind': 'chat' },
            h('span', { class: 'side-label' }, headline(run.task)),
            state === 'asking' ? awaiting() : unseen ? marked() : null,
            state && state !== 'asking' ? h('span', { class: 'side-status', 'data-hmz': 'chat-state', 'data-state': state }, CHAT_SAID[state]) : null,
            // When it began, drawn where nothing can point at the row to be told.
            touched.matches ? h('span', { class: 'side-meta side-age', 'data-hmz': 'chat-began' }, ago(run.began)) : null,
          ),
          more,
        )
      : // A flow's epic, a row of another kind: what opens it out, its task and how it stands, and under them its flow.
        h(
          'div',
          { class: ['side-run', 'side-flow', at && 'current'] },
          toggle,
          h(
            'a',
            { href: link, 'aria-current': at ? 'page' : null, title, 'data-hmz': 'epic', 'data-kind': 'flow' },
            h(
              'span',
              { class: 'side-line' },
              h('span', { class: 'side-label' }, headline(run.task)),
              unseen ? marked() : null,
              h('span', { class: ['side-status', `tone-${tone(how)}`], 'data-hmz': 'epic-state', 'data-state': how }, epicSaid(how)),
            ),
            h(
              'span',
              { class: 'side-line side-sub' },
              h('span', { class: 'side-tag', 'data-hmz': 'epic-flow' }, icon('flows'), h('span', { class: 'side-label' }, flowName(run.flow) || t('flow'))),
              h('span', { class: 'side-meta' }, run.held ? h('span', { class: 'pill-live' }, t('live')) : ago(run.began)),
            ),
          ),
          more,
        )
    // A chat is renamed in its row, where its title stands.
    menuOn(row, () => epicMenu(run, { rename: () => retitling(row.querySelector('a'), run) }), 'row-menu')
    menuButton(more, row)
    return h('li', { class: 'side-item', 'data-epic': run.name }, row, shown ? [tree(run, here, parts), reading(run)] : null)
  }

  /** What an epic opened out holds: its agents, each with the sessions it opened. */
  function tree(run, here, parts) {
    // Read again while it goes, as its sessions open; once, once it has ended.
    const read = details.get(run.name)
    const stale = !read || read.how !== run.how || (run.held && Date.now() - read.at > 3000)
    if (stale && !(read && read.asking)) {
      details.set(run.name, { ...(read || {}), asking: true })
      const of = daemon()
      call('runs.get', { name: run.name }).then(
        (detail) => {
          if (of !== daemon()) return
          details.set(run.name, { how: run.how, at: Date.now(), detail })
          if (data) draw()
        },
        (error) => {
          if (of !== daemon()) return
          details.set(run.name, { how: run.how, at: Date.now(), detail: null, error })
          if (data) draw()
        },
      )
    }
    const detail = read && read.detail
    const sessions = detail ? sessionsOf(detail) : []
    const agents = run.agents.map((one) => ({ name: one.name, role: one.role, runs: one.runs, sessions: sessions.filter((session) => session.agent === one.name) }))
    if (!agents.length) return h('p', { class: 'side-quiet nested' }, t('No agents'))
    const base = hash(`/epics/${encodeURIComponent(run.name)}`)
    return h(
      'ul',
      { class: 'side-tree', role: 'list' },
      agents.map((agent) => {
        const at = run.name === here && parts[2] === 'agents' && parts[3] === agent.name
        return h(
          'li',
          {},
          menuOn(
            h(
              'a',
              { class: ['side-agent', at && 'current'], href: `${base}/agents/${encodeURIComponent(agent.name)}`, 'aria-current': at ? 'page' : null, title: `${agent.role} · ${agent.runs}`, 'data-hmz': 'agent' },
              icon('agent'),
              h('span', { class: 'side-label' }, agent.name),
              h('span', { class: 'side-meta' }, harnessName(agent.runs.split(/[@/]/)[0])),
            ),
            () => [
              { head: `${agent.role} · ${agent.runs}` },
              { label: t('Show on graph'), glyph: 'flows', href: `${base}/agents/${encodeURIComponent(agent.name)}` },
              { label: t('Open log'), glyph: 'thread', href: `${base}/logs/${encodeURIComponent(agent.name)}` },
              '-',
              { label: t('Copy agent'), glyph: 'copy', act: () => copy(agent.runs, t('Agent copied')) },
            ],
          ),
          agent.sessions.length
            ? h(
                'ul',
                { role: 'list' },
                agent.sessions.map((session) => {
                  const on = run.name === here && parts[2] === 'sessions' && parts[3] === session.key
                  return h(
                    'li',
                    {},
                    menuOn(
                      h(
                        'a',
                        { class: ['side-session', on && 'current'], href: `${base}/sessions/${encodeURIComponent(session.key)}`, 'aria-current': on ? 'page' : null, title: session.ident ? `${session.key} · ${session.backend} ${session.ident}` : session.key, 'data-hmz': 'session' },
                        h('span', { class: 'side-mark', 'aria-hidden': 'true' }, '○'),
                        h('span', { class: 'side-label mono' }, session.key),
                      ),
                      () => [
                        { head: session.ident ? `${session.backend} ${session.ident}` : session.key },
                        { label: t('Open'), glyph: 'open', href: `${base}/sessions/${encodeURIComponent(session.key)}` },
                        { label: t('Copy link'), glyph: 'link', act: () => copy(`${location.origin}/${base}/sessions/${encodeURIComponent(session.key)}`, t('Link copied')) },
                        session.ident ? { label: t('Copy session ID'), glyph: 'copy', act: () => copy(session.ident, t('Session ID copied')) } : null,
                      ],
                    ),
                  )
                }),
              )
            : null,
        )
      }),
    )
  }

  /** Under an epic opened out: that its sessions are read, until they first are, or why they could not be. */
  function reading(run) {
    const read = details.get(run.name)
    if (!run.agents.length) return null
    if (read && read.error && !read.detail) return h('p', { class: 'side-quiet nested', role: 'alert' }, read.error.message)
    return read && 'detail' in read ? null : h('p', { class: 'side-quiet nested', role: 'status', 'data-hmz': 'reading' }, t('Reading…'))
  }

  watch()
  // A notice of a chat or epic the page is not on marks its row, of whichever daemon.
  notifying(where, (of, name, on = true) => name && mark(UNREAD, name, on, of))
  // A row marked unread here is read once the page comes to it: as it is loaded, as its address
  // changes, and as the view drawn takes its address.
  const seen = () => {
    const { parts } = where()
    if ((parts[0] === 'epics' || parts[0] === 'chats') && marksHere(UNREAD).has(parts[1])) mark(UNREAD, parts[1], false)
  }
  seen()
  window.addEventListener('hashchange', () => {
    // The links that stay go on to the daemon the address names, as it names it.
    for (const link of root.querySelectorAll('.side-top .brand, .side-nav a')) link.setAttribute('href', hash(`/${link.dataset.nav || 'new'}`))
    seen()
    if (data) draw()
  })
  // The view drawn took another address -- a chat just started, an epic going, named -- whose
  // row is marked.
  window.addEventListener('hmz:renamed', () => {
    seen()
    if (data) draw()
  })
  window.addEventListener('hmz:seen', () => data && draw())
  // A harness session was continued as a chat: what was read of them is read again.
  window.addEventListener('hmz:harness', () => {
    harnessed.clear()
    if (data) draw()
  })
  // A row pinned or marked, from wherever its menu was opened.
  window.addEventListener('hmz:list', () => data && draw())
  // What held a drawing back is gone: the menu closed, by whatever closed it, or the title's
  // field done with. A press on the list that closed it is still on its way to a click, and the
  // row under it stays until then.
  window.addEventListener('pointerdown', (event) => (pressing = list.contains(event.target)), true)
  for (const over of ['pointerup', 'pointercancel']) window.addEventListener(over, () => (pressing = false), true)
  window.addEventListener('hmz:layers', () => stale && data && !pressing && draw())
  for (const ended of ['click', 'keyup']) document.addEventListener(ended, () => setTimeout(() => stale && data && draw()), true)
  // Another daemon's epics and workspaces: nothing of the last one's is drawn until they are read.
  window.addEventListener('hmz:daemon', () => {
    data = null
    read = {}
    running = []
    places = null
    limit = PAGE
    asked = null
    dry = false
    loading = null
    shown.clear()
    details.clear()
    strays.clear()
    harnessed.clear()
    fill(list, h('p', { class: 'side-quiet', role: 'status' }, t('Loading…')))
    watch()
    watchPlaces()
  })
}

/** The mark of a notice unread, on its chat or epic and on the folded workspace that lists it. */
function marked() {
  return h('span', { class: 'side-unread', 'data-hmz': 'unread', role: 'img', 'aria-label': t('Unread'), title: t('Unread') })
}

/** What marks a chat that waits on its person: the dot of one unread, said as what it is to whoever cannot see it. */
function awaiting() {
  return h('span', { class: 'side-unread', 'data-hmz': 'chat-state', 'data-state': 'asking', role: 'img', 'aria-label': CHAT_SAID.asking, title: CHAT_SAID.asking })
}

/**
 * What can be done to one chat or epic, from wherever it is listed; `rename` renames a chat
 * where the menu is opened, and is offered only where given.
 */
export function epicMenu(run, { rename = null } = {}) {
  const base = hash(pathOf(run))
  // Going, whether a host holds it or another process does -- `hmz exec`, say.
  const going = run.held || run.how === 'running'
  // A chat is its conversation alone: no log of every session, no timeline, no archive to
  // export, and never stopped from here; it is carried on by saying something in it, not resumed
  // from a form, and one like it is a new chat with its agent.
  const chat = chatting(run)
  const resumes = !chat && run.resumable && !going && run.how !== 'done'
  const assistant = chat ? (run.agents[0] || {}).runs || '' : ''
  // A chat's menu says chat things: it never names an epic, a flow or a task.
  const said = wording(chat)
  const pinned = marksHere(PINNED).has(run.name)
  const unseen = unreadHere(run.name)
  // What a chat alone offers: renamed, forked, archived and deleted (chat-actions.js).
  const acts = chat ? chatActions(run, { rename }) : {}
  return [
    { head: run.task.split('\n')[0] },
    { label: t('Open'), glyph: 'open', href: base },
    '-',
    // Kept in this browser, as a desktop app keeps them: pinned, it stands first in the list.
    { label: pinned ? t('Unpin') : t('Pin'), glyph: 'pin', act: () => mark(PINNED, run.name, !pinned) },
    {
      label: unseen ? t('Mark as read') : t('Mark as unread'),
      glyph: 'bell',
      act: () => mark(UNREAD, run.name, !unseen),
    },
    acts.rename,
    '-',
    chat ? null : { label: t('Exomyth'), glyph: 'chart', href: `${base}/exomyth` },
    resumes ? { label: t('Resume'), glyph: 'resume', href: hash(`/new?flow=${encodeURIComponent(run.flow)}&resume=${encodeURIComponent(run.name)}&workspace=${encodeURIComponent(run.workspace)}`) } : null,
    chat
      ? { label: said.like, glyph: 'thread', href: hash(`/new/chat?${new URLSearchParams(given({ workspace: run.workspace, agent: assistant }))}`) }
      : { label: said.like, glyph: 'new', href: hash(`/new?flow=${encodeURIComponent(run.flow)}&workspace=${encodeURIComponent(run.workspace)}`) },
    acts.fork,
    '-',
    { label: t('Copy link'), glyph: 'link', act: () => copy(`${location.origin}/${base}`, t('Link copied')) },
    { label: said.task, glyph: 'copy', act: () => copy(run.task, said.tasked) },
    { label: said.name, glyph: 'copy', act: () => copy(run.name, said.named) },
    going || chat ? null : { label: t('Export'), glyph: 'download', act: () => working(t('Exporting…'), exported(run.name)).catch((error) => toast(error.message)) },
    { label: t('Upload'), glyph: 'up', title: backedSaid(run.backed), act: () => upload(run) },
    run.held && !chat ? '-' : null,
    run.held && !chat ? { label: t('Stop'), glyph: 'stop', danger: true, act: () => working(t('Stopping…'), ask({ workspace: run.workspace, slot: run.slot }, 'stop')).then(() => toast(t('Stopping')), (error) => toast(error.message)) } : null,
    chat ? '-' : null,
    acts.archive,
    acts.delete,
  ]
}

/** What takes away the last thing said to be going. */
let done = () => {}

/**
 * Says what was asked of the server is going, in the words given, in a toast that stays until it answers -- the menu
 * it was asked from is closed by then -- and gives back the answer.
 */
function working(said, asked) {
  done()
  const mine = (done = posted(h('div', { class: 'toast notice working', role: 'status', 'data-hmz': 'working' }, h('span', { class: 'dot live', 'aria-hidden': 'true' }), said)))
  return asked.finally(mine)
}

/**
 * Backs an epic up to its targets now -- or a chat, by `chat.backup` -- behind the page: how it
 * went is read as the epic is. Unnoticed, it is for a button that says it is busy itself.
 */
export function upload(run, { noticed = true } = {}) {
  const asked = chatting(run) ? call('chat.backup', { chat: run.name }) : call('runs.backup', { name: run.name })
  return (noticed ? working(t('Uploading…'), asked) : asked).then((answer) => toast(t('Uploading to {targets}', { targets: answer.queued.join(', ') })), (error) => toast(error.message))
}

/** How an epic's last backup to each target went, each in turn, or '' where it has none. */
export function backedSaid(backed) {
  return Object.entries(backed || {})
    .map(([name, one]) => (one.ok ? t('{name}: uploaded {when}', { name, when: when(one.at) }) : t('{name}: failed, {error} {when}', { name, error: one.error, when: when(one.at) })))
    .join(' · ')
}

/** How a daemon stands, as its dot says it, and the word for it where it is not up. */
const STATES = { up: t('up'), connecting: t('connecting'), installing: t('installing'), failed: t('failed'), idle: t('not connected') }

/** What a daemon is called on the page. */
function named(name) {
  return name === 'local' ? t('Local') : name
}

/** A daemon's host, as it says it: its machine's name, or the WSL distribution hmz runs in. */
function hostOf(said) {
  return said.wsl ? `${said.wsl} (WSL)` : said.machine || ''
}

/**
 * The foot of the sidebar: the daemon the page is of -- its name, its host, how it stands and
 * how many epics are going on it -- opening a menu of every daemon, beside it, and the settings
 * and what the epics spent.
 */
function daemonBar() {
  /** Every daemon this browser keeps, Local first. */
  let daemons = [{ name: 'local', routes: [] }]
  /** Each daemon's host, once it has said hello. */
  const hosts = new Map()
  // How many epics are going, and on which daemon they were counted.
  let live = { of: '', count: 0 }
  /** A newer release of hmz than the one serving the page, as Local last learned it. */
  let newer = ''
  // Each holds one text, written where it changes and never put in place of another: the bar
  // is drawn again between a press and its release, and WebKit makes no click of the two once
  // the text pressed on is gone.
  const avatar = h('span', { class: 'side-avatar', 'aria-hidden': 'true' }, '')
  const title = h('b', { 'data-hmz': 'daemon-name' }, '')
  const host = h('span', { class: 'side-host', 'data-hmz': 'daemon-host' }, '')
  const dot = h('span', { 'aria-hidden': 'true' })
  const state = h('span', { class: 'side-state', 'data-hmz': 'state' }, dot, '')
  const say = (el, text) => el.lastChild.nodeValue === text || (el.lastChild.nodeValue = text)
  const badge = h('span', { class: 'side-badge', 'data-hmz': 'newer', hidden: true }, '↑')
  const el = h(
    'button',
    { class: 'side-account', type: 'button', 'data-hmz': 'daemon-bar' },
    avatar,
    h('span', { class: 'side-account-text' }, h('span', { class: 'side-daemon' }, title, host), state),
    badge,
  )
  /** Learns a daemon's host as it says hello, and Local's news of a newer release. */
  const greet = (name) => {
    if (hosts.has(name)) return
    hosts.set(name, '')
    hello(name).then(
      (said) => {
        hosts.set(name, hostOf(said))
        if (name === 'local' && said.newer) {
          newer = said.newer
          badge.hidden = false
          badge.title = t('hmz {version} is out', { version: newer })
        }
        draw()
      },
      () => hosts.delete(name),
    )
  }
  const draw = () => {
    const name = daemon()
    greet(name)
    const { state: how, detail } = stateOf(name)
    const up = how === 'up'
    say(avatar, named(name).slice(0, 1).toUpperCase())
    say(title, named(name))
    say(host, hosts.get(name) || '')
    el.title = [named(name), hosts.get(name), detail].filter(Boolean).join(' · ')
    el.dataset.state = how
    const going = live.of === name ? live.count : 0
    dot.className = `dot daemon-${how}${up && going ? ' live' : ''}`
    say(state, up ? (going ? t('{n} live', { n: going }) : t('idle')) : STATES[how] || how)
  }
  const read = () =>
    known().then(
      (listed) => {
        daemons = listed
        draw()
      },
      () => {},
    )
  const connect = (name) => {
    working(t('Connecting {name}…', { name: named(name) }), reconnect(name)).then(() => toast(t('Connecting {name}', { name: named(name) })), (error) => toast(error.message))
  }
  menu(
    el,
    (close) => [
      submenu({
        label: t('Daemon'),
        about: named(daemon()),
        glyph: 'home',
        hmz: 'daemons',
        items: () => [
          daemons.flatMap((one) => {
            const how = stateOf(one.name).state
            return [
              choice({
                label: named(one.name),
                about: [hosts.get(one.name), STATES[how] || how].filter(Boolean).join(' · '),
                chosen: one.name === daemon(),
                act: () => {
                  settleSidebar()
                  if (one.name !== daemon()) toDaemon(one.name)
                },
                close,
              }),
              how === 'failed' && one.name !== 'local' ? choice({ label: t('Connect'), about: named(one.name), glyph: 'resume', act: () => connect(one.name), close }) : null,
            ]
          }),
          h('hr'),
          choice({ label: t('Manage'), glyph: 'sliders', href: hash('/settings/daemons'), close }),
        ],
      }),
      newer ? choice({ label: t('Update'), about: `hmz ${newer}`, glyph: 'up', act: () => copy('hmz update', t('Copied hmz update')), close }) : null,
      choice({ label: t('Settings'), glyph: 'gear', href: hash('/settings/general'), close }),
      choice({ label: t('Usage'), glyph: 'chart', href: hash('/settings/usage'), close }),
    ],
    { up: true, label: t('Daemon') },
  )
  // The menu is drawn as it opens: the daemons kept now, as another tab may have added one.
  el.addEventListener('pointerdown', read)
  // The picker is what opened after it, once the menu has put it there.
  el.addEventListener('click', () => {
    const pop = el.nextElementSibling
    if (pop && pop.matches('.popover')) pop.dataset.hmz = 'daemon-picker'
  })
  onState((name) => name === daemon() && draw())
  addEventListener('hashchange', draw)
  addEventListener('hmz:daemon', draw)
  greet('local')
  read()
  return {
    el,
    /** Says how many epics are going on the daemon the page is of. */
    going(count) {
      live = { of: daemon(), count }
      draw()
    },
  }
}

/** Forgets a workspace nothing ran in, which takes it out of the list. */
function forget(path) {
  working(t('Forgetting…'), call('workspaces.forget', { workspace: path })).then(() => {
    refresh('workspaces.list')
    toast(t('Forgotten'))
  }, (error) => toast(error.message))
}
