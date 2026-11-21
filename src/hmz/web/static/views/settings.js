// What Humanize remembers, as ChatGPT keeps its settings: a dialog over the page with its pages
// down the side, in three groups. The app's own -- how this page is drawn, which daemons it
// reaches, what it tells you of them and the language it is written in -- are this browser's,
// or this machine's, whichever daemon is on screen. The daemon's -- what is true wherever Humanize runs, who its agents are
// and what takes over when one fails, where their work goes, where epics are backed up, and
// last what the runs there spent -- are read from and written to the daemon picked above them,
// the one on screen unless another is, and each page that saves can copy what it holds to other
// daemons at once. A workspace's -- what one folder of that daemon was set up with, and the
// chats archived there -- are of the folder picked under the daemon.

import { call, daemon, given, hash, known, started } from '../api.js'
import { shut, stays } from '../app.js'
import { empty, fill, h, iconButton, pathText, problem } from '../dom.js'
import { t } from '../i18n.js'
import { modal } from '../layers.js'
import { firstOf, nameOf, there } from '../places.js'
import { dragged } from '../shell.js'

/** Every page, by the word in the address that opens it, in its group. */
const PAGES = {
  themes: { group: 'app', label: t('Themes'), about: t('Colours and pictures of this browser’s page'), load: () => import('./settings/themes.js') },
  daemons: { group: 'app', label: t('Daemons'), about: t('Machines this page reaches'), load: () => import('./settings/daemons.js') },
  notifications: { group: 'app', label: t('Notifications'), about: t('What every daemon tells you'), load: () => import('./settings/notifications.js') },
  language: { group: 'app', label: t('Language'), about: t('What this browser’s page is written in'), load: () => import('./settings/language.js') },
  general: { group: 'daemon', label: t('General'), about: t('Display and reporting'), load: () => import('./settings/general.js') },
  accounts: { group: 'daemon', label: t('Accounts'), about: t('Credentials agents run as'), load: () => import('./settings/accounts.js') },
  nous: { group: 'daemon', label: t('Nous'), about: t('Who takes a turn, and where it goes once it fails'), load: () => import('./settings/nous.js') },
  runtimes: { group: 'daemon', label: t('Runtimes'), about: t('Machines environments run on'), load: () => import('./settings/runtimes.js') },
  backup: { group: 'daemon', label: t('Backup'), about: t('Git repositories epics go to'), load: () => import('./settings/backup.js') },
  usage: { group: 'daemon', label: t('Usage'), about: t('Spending by day and flow'), load: () => import('./settings/usage.js') },
  workspace: { group: 'workspace', label: t('Setup'), about: t('What this folder was last set up with'), load: () => import('./settings/workspace.js') },
  archived: { group: 'workspace', label: t('Archived chats'), about: t('Chats of this folder that were put away'), load: () => import('./settings/archived.js') },
}

const GROUPS = [
  ['app', t('App')],
  ['daemon', t('Daemon')],
  ['workspace', t('Workspace')],
]

/** What a workspace is picked by: its folder's name, or with the folder it is in where another has the name. */
const shownAs = (one, all) => (all.some((other) => other !== one && other.name === one.name) ? one.path.split('/').slice(-2).join('/') : one.name)

/** What a daemon is called on screen. */
function called(one) {
  return one.label || (one.name === 'local' ? t('Local') : one.name)
}

/** Every daemon this browser keeps: Local alone where none can be read. */
async function daemons() {
  return known().catch(() => [{ name: 'local' }])
}

export function mount(root, { parts, query }) {
  const name = parts[1] in PAGES ? parts[1] : 'general'
  const page = PAGES[name]
  let body = h('div', { class: 'settings-body', 'data-hmz': `settings-${name}` }, h('p', { class: 'loading', role: 'status' }, t('Reading the settings…')))
  const links = {}
  let chosen = query.get('daemon') || daemon()
  // The folder the `Workspace` pages are of: the one the address names, else the first there is.
  let workspace = query.get('workspace') || ''
  /** What a page's address carries beside its name: the daemon picked, and the folder under `Workspace`. */
  const carried = (group) => ({
    ...(group !== 'app' && query.get('daemon') ? { daemon: chosen } : {}),
    ...(group === 'workspace' && workspace ? { workspace } : {}),
  })
  const href = (key) => {
    const text = new URLSearchParams(carried(PAGES[key].group)).toString()
    return hash(`/settings/${key}${text ? `?${text}` : ''}`)
  }
  const nav = h(
    'nav',
    { class: 'settings-nav', 'aria-label': t('Settings pages') },
    h('h2', {}, t('Settings')),
    GROUPS.map(([group, label]) => [
      h('h4', { class: 'settings-group' }, label),
      Object.entries(PAGES)
        .filter(([, one]) => one.group === group)
        // The dialog opens on the page it shows: its link has the focus.
        .map(([key, one]) => (links[key] = h('a', { href: href(key), 'aria-current': key === name ? 'page' : null, autofocus: key === name }, one.label))),
    ]),
  )
  const picker = h('select', { 'aria-label': t('Daemon'), 'data-hmz': 'settings-daemon' }, h('option', { value: chosen }, called({ name: chosen })))
  // Which folder, under `Workspace`: its name picked, and its whole path said beside it.
  const folder = h('select', { 'aria-label': t('Workspace'), 'data-hmz': 'settings-workdir' })
  const folderAt = h('span', { class: 'settings-path', 'data-hmz': 'settings-workdir-path' })
  const folders = h('div', { class: 'settings-daemon settings-workspace', hidden: true }, h('span', { class: 'label' }, t('Workspace')), folder, folderAt)
  const head = h('div', { class: 'settings-head' }, h('div', {}, h('h3', {}, page.label), h('p', { class: 'dim' }, page.about)), iconButton('close', t('Close'), { onclick: shut }))
  root.classList.add('dialog-settings')
  root.setAttribute('aria-label', t('Settings'))
  fill(
    root,
    // The top row of a narrow window, which it fills; on a wide one, a column inside it.
    dragged(nav, 'deep', 'narrow'),
    h(
      'div',
      { class: 'settings-page' },
      head,
      page.group === 'app' ? null : h('div', { class: 'settings-daemon' }, h('span', { class: 'label' }, t('Daemon')), picker),
      page.group === 'workspace' ? folders : null,
      body,
    ),
  )
  // In the middle of the strip the pages are across a narrow window.
  links[name].scrollIntoView({ block: 'nearest', inline: 'center' })

  let listed = [{ name: 'local' }]
  let leaving = null
  let gone = false
  let drawn = 0

  /** What every page on the daemon picked reads, writes and copies with. */
  const scope = () => {
    const on = chosen
    return {
      name: on,
      // The folder picked, under `Workspace`.
      workspace,
      call: (method, params = {}) => call(method, params, { on }),
      // What a page puts in the address beside its own, so the daemon picked stays in it.
      query: carried(page.group),
      batch: (calls, { off = '', small = true } = {}) => batchButton(root, on, () => listed, calls, off, small),
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
    fill(fresh, h('p', { class: 'loading', role: 'status' }, t('Reading the settings…')))
    page
      .load()
      .then((module) => {
        if (!gone && mine === drawn) leaving = module.draw(fresh, query, parts, scope()) || null
      })
      .catch((error) => fill(fresh, problem(error)))
  }

  /** Puts something else than a page under the head: the last page is left first. */
  const instead = (...told) => {
    drawn += 1
    if (leaving) leaving()
    leaving = null
    fill(body, told)
  }

  /** Every folder the daemon picked serves, and the page of the one picked -- or that there is none. */
  let listing = 0
  let served = []
  const placed = () => {
    const one = served.find((each) => each.path === workspace)
    fill(folderAt, one ? pathText(one.path) : null, one && !there(one) ? h('span', { class: 'chip', 'data-hmz': 'settings-workdir-missing' }, t('Missing')) : null)
  }
  const list = () => {
    const mine = ++listing
    const on = chosen
    started()
      // Where `hmz web` started is a directory of Local's alone.
      .then((here) => call('workspaces.list', given({ here: on === 'local' ? here : '' }), { on }))
      .then(
        (answer) => {
          if (gone || mine !== listing) return
          served = answer.workspaces
          // One whose directory is there first; one that went only where the address names it
          // or no other is listed: its set-up is still read, and forgotten, here.
          if (!workspace) workspace = served.some(there) ? firstOf(answer) : answer.here || served[0]?.path || ''
          if (workspace && !served.some((one) => one.path === workspace)) served = [...served, { path: workspace, name: nameOf(workspace) }]
          folders.hidden = !served.length
          // Each by its folder's name alone, which tells them apart where a path's start does
          // not; what else there is to say of one is said beside the picker, not in it.
          fill(folder, served.map((one) => h('option', { value: one.path, selected: one.path === workspace }, shownAs(one, served))))
          placed()
          for (const key of Object.keys(PAGES)) links[key].href = href(key)
          if (workspace) draw()
          else
            instead(
              empty(
                t('No folder yet.'),
                t(' A folder you open from the sidebar, or start a chat or an epic in, is set up here.'),
                h('a', { class: 'btn primary', href: hash('/new/chat') }, t('New chat')),
              ),
            )
        },
        (error) => !gone && mine === listing && instead(problem(error)),
      )
  }
  folder.addEventListener('change', () => {
    workspace = folder.value
    placed()
    // Kept in the address, as the daemon picked is.
    query = new URLSearchParams(carried('workspace'))
    stays(Object.fromEntries(query))
    for (const key of Object.keys(PAGES)) links[key].href = href(key)
    draw()
  })

  if (page.group !== 'app') {
    daemons().then((read) => {
      if (gone) return
      listed = read
      if (!listed.some((one) => one.name === chosen)) listed = [...listed, { name: chosen }]
      fill(picker, listed.map((one) => h('option', { value: one.name, selected: one.name === chosen }, called(one))))
    })
    picker.addEventListener('change', () => {
      chosen = picker.value
      // Kept in the address, so that this daemon's page is one that can be kept; what the
      // page said of the last daemon's directories says nothing of this one's.
      query = new URLSearchParams({ daemon: chosen })
      stays({ daemon: chosen })
      // A folder of the last daemon is none of this one's.
      workspace = ''
      for (const key of Object.keys(PAGES)) links[key].href = href(key)
      if (page.group === 'workspace') list()
      else draw()
    })
  }
  if (page.group === 'workspace') list()
  else draw()
  return () => {
    gone = true
    if (leaving) leaving()
    for (const one of root.querySelectorAll('dialog')) one.close()
  }
}

/**
 * Copies what a page holds to other daemons: a dialog of every daemon but the one it came from,
 * ticked as they are wanted, and what each said once it was sent there. The button is given in
 * a group of its own, which stands at the end of a card's heading, after why it can do nothing
 * where it cannot.
 *
 * @param {HTMLElement} root Where the dialog is drawn.
 * @param {string} from The daemon the page holds what it holds of.
 * @param {() => {name: string}[]} known Every daemon there is, as last read.
 * @param {(() => Array<[string, object]>) | null} calls What is called: each method and its params.
 * @param {string} off Why nothing can be, where nothing can.
 * @param {boolean} small Whether the button is as small as a card's own are, not a form's.
 */
function batchButton(root, from, known, calls, off, small) {
  const button = h('button', { class: ['btn quiet', small && 'small'], type: 'button', 'data-hmz': 'batch-apply', disabled: Boolean(off) }, t('Batch apply'))
  const group = h('span', { class: 'row' }, off ? h('span', { class: 'hint', 'data-hmz': 'batch-off' }, off) : null, button)
  if (off) return group
  button.addEventListener('click', () => {
    const others = known().filter((one) => one.name !== from)
    const boxes = others.map((one) => ({ one, box: h('input', { type: 'checkbox', 'data-daemon': one.name }) }))
    const all = h('input', { type: 'checkbox', 'data-hmz': 'batch-all' })
    all.addEventListener('change', () => boxes.forEach(({ box }) => (box.checked = all.checked)))
    for (const { box } of boxes) box.addEventListener('change', () => (all.checked = boxes.every((each) => each.box.checked)))
    const results = h('ul', { class: 'batch-results', 'data-hmz': 'batch-results', 'aria-live': 'polite' })
    const apply = h('button', { class: 'btn primary', type: 'button', 'data-hmz': 'batch-go' }, t('Apply'))
    const dialog = h(
      'dialog',
      { class: 'batch-dialog', 'data-hmz': 'batch-dialog', 'aria-label': t('Batch apply') },
      h('h3', {}, t('Batch apply')),
      h('p', { class: 'dim' }, t('From {name}', { name: called({ name: from }) })),
      others.length
        ? h('div', { class: 'form' }, h('label', { class: 'check' }, all, h('b', {}, t('All'))), boxes.map(({ one, box }) => h('label', { class: 'check' }, box, called(one))))
        : h('p', { class: 'dim' }, t('No other daemon.')),
      results,
      h('div', { class: 'row' }, h('button', { class: 'btn quiet', type: 'button', onclick: () => dialog.close() }, t('Close')), others.length ? apply : null),
    )
    // Closed, the button it was opened by has the focus back in every browser.
    dialog.addEventListener('close', () => (dialog.remove(), button.focus()))
    apply.addEventListener('click', async () => {
      const picked = boxes.filter(({ box }) => box.checked).map(({ one }) => one)
      if (!picked.length) return
      apply.disabled = true
      fill(results)
      let sent
      try {
        sent = await calls()
        if (!sent.length) throw new Error(t('Nothing to apply.'))
      } catch (error) {
        fill(results, h('li', {}, problem(error)))
        apply.disabled = false
        return
      }
      await Promise.all(
        picked.map(async (one) => {
          const line = h('li', { 'data-hmz': 'batch-result', 'data-daemon': one.name }, h('b', {}, called(one)), ' ', h('span', { class: 'dim' }, t('Applying…')))
          results.append(line)
          try {
            for (const [method, params] of sent) await call(method, params, { on: one.name })
            fill(line, h('b', {}, called(one)), ' ', h('span', { class: 'ok' }, t('Applied')))
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
    // Over Settings, which Escape and a press beside this one leave open.
    modal(dialog)
  })
  return group
}
