// What humanize remembers, as ChatGPT keeps its settings: a dialog over the page with its pages
// down the side, in two groups. The app's own -- how this page is drawn, which daemons it
// reaches and what it tells you of them -- are this browser's, or this machine's, whichever
// daemon is on screen. The daemon's -- what is true wherever humanize runs, who its agents are
// and what takes over when one fails, where their work goes, where epics are backed up, one
// directory, and last what the runs there spent -- are read from and written to the daemon
// picked above them, the one on screen unless another is, and each page that saves can copy
// what it holds to other daemons at once.

import * as api from '../api.js'
import { hash } from '../api.js'
import { shut, stays } from '../app.js'
import { fill, h, iconButton, problem } from '../dom.js'
import { dragged } from '../shell.js'

/** Every page, by the word in the address that opens it, in its group. */
const PAGES = {
  themes: { group: 'app', label: 'Themes', about: 'Colours and pictures of this browser’s page', load: () => import('./settings/themes.js') },
  daemons: { group: 'app', label: 'Daemons', about: 'Machines this page reaches', load: () => import('./settings/daemons.js') },
  notifications: { group: 'app', label: 'Notifications', about: 'What every daemon tells you', load: () => import('./settings/notifications.js') },
  general: { group: 'daemon', label: 'General', about: 'Display, side questions and reporting', load: () => import('./settings/general.js') },
  accounts: { group: 'daemon', label: 'Accounts', about: 'Credentials agents run as', load: () => import('./settings/accounts.js') },
  fallback: { group: 'daemon', label: 'Fallback', about: 'Where a failed turn goes next', load: () => import('./settings/fallback.js') },
  runtimes: { group: 'daemon', label: 'Runtimes', about: 'Machines environments run on', load: () => import('./settings/runtimes.js') },
  backup: { group: 'daemon', label: 'Backup', about: 'Git repositories epics go to', load: () => import('./settings/backup.js') },
  workspace: { group: 'daemon', label: 'Workspace', about: 'This directory’s saved setup', load: () => import('./settings/workspace.js') },
  usage: { group: 'daemon', label: 'Usage', about: 'Spending by day and flow', load: () => import('./settings/usage.js') },
}

const GROUPS = [
  ['app', 'App'],
  ['daemon', 'Daemon'],
]

/** The daemon the page is on, where the page knows of more than one. */
function current() {
  return (typeof api.daemon === 'function' && api.daemon()) || 'local'
}

/** Where a daemon's API is reached from here: as the page reaches it, or through this server. */
function prefix(name) {
  return name === current() ? '' : `/d/${encodeURIComponent(name)}`
}

/** What a daemon is called on screen. */
function called(one) {
  return one.label || (one.name === 'local' ? 'Local' : one.name)
}

/** Every daemon this page reaches: Local alone where this server keeps no list. */
async function daemons() {
  try {
    const answer = await api.get('/api/daemons')
    const listed = Array.isArray(answer) ? answer : answer.daemons
    if (Array.isArray(listed) && listed.length) return listed
  } catch {
    // An older server, or none of its own: Local is all there is.
  }
  return [{ name: 'local' }]
}

export function mount(root, { parts, query }) {
  const name = parts[1] in PAGES ? parts[1] : 'general'
  const page = PAGES[name]
  let body = h('div', { class: 'settings-body', 'data-hmz': `settings-${name}` }, h('p', { class: 'loading', role: 'status' }, 'Reading the settings…'))
  const links = {}
  let chosen = query.get('daemon') || current()
  const href = (key) => hash(`/settings/${key}${PAGES[key].group === 'daemon' && query.get('daemon') ? `?daemon=${encodeURIComponent(chosen)}` : ''}`)
  const nav = h(
    'nav',
    { class: 'settings-nav', 'aria-label': 'Settings pages' },
    h('h2', {}, 'Settings'),
    GROUPS.map(([group, label]) => [
      h('h4', { class: 'settings-group' }, label),
      Object.entries(PAGES)
        .filter(([, one]) => one.group === group)
        .map(([key, one]) => (links[key] = h('a', { href: href(key), 'aria-current': key === name ? 'page' : null }, one.label))),
    ]),
  )
  const picker = h('select', { 'aria-label': 'Daemon', 'data-hmz': 'settings-daemon' }, h('option', { value: chosen }, called({ name: chosen })))
  const head = h('div', { class: 'settings-head' }, h('div', {}, h('h3', {}, page.label), h('p', { class: 'dim' }, page.about)), iconButton('close', 'Close', { onclick: shut }))
  root.classList.add('dialog-settings')
  root.setAttribute('aria-label', 'Settings')
  fill(
    root,
    // The top row of a narrow window, which it fills.
    dragged(nav),
    h(
      'div',
      { class: 'settings-page' },
      head,
      page.group === 'daemon' ? h('div', { class: 'settings-daemon' }, h('span', { class: 'label' }, 'Daemon'), picker) : null,
      body,
    ),
  )

  let known = [{ name: 'local' }]
  let leaving = null
  let gone = false
  let drawn = 0

  /** What every page on the daemon picked reads, writes and copies with. */
  const scope = () => {
    const base = prefix(chosen)
    return {
      name: chosen,
      base,
      at: (path) => `${base}${path}`,
      // What a page puts in the address beside its own, so the daemon picked stays in it.
      query: query.get('daemon') ? { daemon: chosen } : {},
      batch: (posts, { off = '' } = {}) => batchButton(root, chosen, () => known, posts, off),
    }
  }

  const draw = () => {
    const mine = ++drawn
    if (leaving) leaving()
    leaving = null
    // A body of its own: what the last daemon's page reads late is drawn where nobody sees it.
    const fresh = body.cloneNode(false)
    body.replaceWith(fresh)
    body = fresh
    fill(fresh, h('p', { class: 'loading', role: 'status' }, 'Reading the settings…'))
    page
      .load()
      .then((module) => {
        if (!gone && mine === drawn) leaving = module.draw(fresh, query, parts, scope()) || null
      })
      .catch((error) => fill(fresh, problem(error)))
  }

  if (page.group === 'daemon') {
    daemons().then((listed) => {
      if (gone) return
      known = listed
      if (!known.some((one) => one.name === chosen)) known = [...known, { name: chosen }]
      fill(picker, known.map((one) => h('option', { value: one.name, selected: one.name === chosen }, called(one))))
    })
    picker.addEventListener('change', () => {
      chosen = picker.value
      // Kept in the address, so that this daemon's page is one that can be kept; what the
      // page said of the last daemon's directories says nothing of this one's.
      query = new URLSearchParams({ daemon: chosen })
      stays({ daemon: chosen })
      for (const key of Object.keys(PAGES)) links[key].href = href(key)
      draw()
    })
  }
  draw()
  return () => {
    gone = true
    if (leaving) leaving()
    for (const one of root.querySelectorAll('dialog')) one.close()
  }
}

/**
 * Copies what a page holds to other daemons: a dialog of every daemon but the one it came from,
 * ticked as they are wanted, and what each said once it was sent there.
 *
 * @param {HTMLElement} root Where the dialog is drawn.
 * @param {string} from The daemon the page holds what it holds of.
 * @param {() => {name: string}[]} known Every daemon there is, as last read.
 * @param {(() => Array<[string, object]>) | null} posts What is sent: each address and body.
 * @param {string} off Why nothing can be, where nothing can.
 */
function batchButton(root, from, known, posts, off) {
  const button = h('button', { class: 'btn quiet', type: 'button', 'data-hmz': 'batch-apply', disabled: Boolean(off) }, 'Batch apply')
  if (off) return h('span', { class: 'row' }, button, h('span', { class: 'hint', 'data-hmz': 'batch-off' }, off))
  button.addEventListener('click', () => {
    const others = known().filter((one) => one.name !== from)
    const boxes = others.map((one) => ({ one, box: h('input', { type: 'checkbox', 'data-daemon': one.name }) }))
    const all = h('input', { type: 'checkbox', 'data-hmz': 'batch-all' })
    all.addEventListener('change', () => boxes.forEach(({ box }) => (box.checked = all.checked)))
    for (const { box } of boxes) box.addEventListener('change', () => (all.checked = boxes.every((each) => each.box.checked)))
    const results = h('ul', { class: 'batch-results', 'data-hmz': 'batch-results', 'aria-live': 'polite' })
    const apply = h('button', { class: 'btn primary', type: 'button', 'data-hmz': 'batch-go' }, 'Apply')
    const dialog = h(
      'dialog',
      { class: 'batch-dialog', 'data-hmz': 'batch-dialog', 'aria-label': 'Batch apply' },
      h('h3', {}, 'Batch apply'),
      h('p', { class: 'dim' }, `From ${called({ name: from })}`),
      others.length
        ? h('div', { class: 'form' }, h('label', { class: 'check' }, all, h('b', {}, 'All')), boxes.map(({ one, box }) => h('label', { class: 'check' }, box, called(one))))
        : h('p', { class: 'dim' }, 'No other daemon.'),
      results,
      h('div', { class: 'row' }, others.length ? apply : null, h('button', { class: 'btn quiet', type: 'button', onclick: () => dialog.close() }, 'Close')),
    )
    // Escape closes this dialog, not Settings under it, wherever the focus is.
    const escape = (event) => {
      if (event.key !== 'Escape') return
      event.stopPropagation()
      event.preventDefault()
      dialog.close()
    }
    document.addEventListener('keydown', escape, true)
    dialog.addEventListener('close', () => {
      document.removeEventListener('keydown', escape, true)
      dialog.remove()
    })
    apply.addEventListener('click', async () => {
      const picked = boxes.filter(({ box }) => box.checked).map(({ one }) => one)
      if (!picked.length) return
      apply.disabled = true
      fill(results)
      let sent
      try {
        sent = await posts()
        if (!sent.length) throw new Error('Nothing to apply.')
      } catch (error) {
        fill(results, h('li', {}, problem(error)))
        apply.disabled = false
        return
      }
      await Promise.all(
        picked.map(async (one) => {
          const line = h('li', { 'data-hmz': 'batch-result', 'data-daemon': one.name }, h('b', {}, called(one)), ' ', h('span', { class: 'dim' }, 'Applying…'))
          results.append(line)
          const base = prefix(one.name)
          try {
            for (const [path, said] of sent) await api.post(`${base}${path}`, said)
            fill(line, h('b', {}, called(one)), ' ', h('span', { class: 'ok' }, 'Applied'))
            line.dataset.ok = 'true'
          } catch (error) {
            fill(line, h('b', {}, called(one)), ' ', h('span', { class: 'bad' }, error.message))
            line.dataset.ok = 'false'
          }
        }),
      )
      apply.disabled = false
    })
    root.append(dialog)
    dialog.showModal()
  })
  return button
}
