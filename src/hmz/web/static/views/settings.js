// What Humanize remembers, as ChatGPT keeps its settings: a dialog over the page with its pages
// down the side, in two groups. The app's own -- how this page is drawn, which daemons it
// reaches and which of them it shows, what it tells you of them and the language it is written
// in -- are this browser's, or this machine's, whichever daemon is on screen. The daemon's --
// what is true wherever Humanize runs, who its agents are and what takes over when one fails,
// where their work goes, where epics are backed up, and last what all that ran there spent --
// are read from and written to the daemon the page shows, which is said over them and picked
// nowhere here but under `Daemons`; each page that saves can copy what it holds to other daemons
// at once. What one folder was set up with is no page of this dialog: it is the folder's own,
// opened from the sidebar (views/workspace.js).

import { call, daemon, hash, known } from '../api.js'
import { shut } from '../app.js'
import { fill, h, icon, iconButton, problem } from '../dom.js'
import { t } from '../i18n.js'
import { modal } from '../layers.js'
import { dragged } from '../shell.js'

/** Every page, by the word in the address that opens it, in its group. */
const PAGES = {
  themes: { group: 'app', label: t('Themes'), about: t('Colours and pictures of this browser’s page'), load: () => import('./settings/themes.js') },
  daemons: { group: 'app', label: t('Daemons'), about: t('Machines this page reaches, and the one it shows'), load: () => import('./settings/daemons.js') },
  notifications: { group: 'app', label: t('Notifications'), about: t('What every daemon tells you'), load: () => import('./settings/notifications.js') },
  language: { group: 'app', label: t('Language'), about: t('What this browser’s page is written in'), load: () => import('./settings/language.js') },
  general: { group: 'daemon', label: t('General'), about: t('Display and reporting'), load: () => import('./settings/general.js') },
  accounts: { group: 'daemon', label: t('Accounts'), about: t('Credentials agents run as'), load: () => import('./settings/accounts.js') },
  nous: { group: 'daemon', label: t('Nous'), about: t('Who takes a turn, and where it goes once it fails'), load: () => import('./settings/nous.js') },
  runtimes: { group: 'daemon', label: t('Runtimes'), about: t('Machines environments run on'), load: () => import('./settings/runtimes.js') },
  backup: { group: 'daemon', label: t('Backup'), about: t('Git repositories epics go to'), load: () => import('./settings/backup.js') },
  usage: { group: 'daemon', label: t('Usage'), about: t('What everything on this daemon spent, by day and flow'), load: () => import('./settings/usage.js') },
}

const GROUPS = [
  ['app', t('App')],
  ['daemon', t('Daemon')],
]

/** What a daemon is called on screen. */
export function called(one) {
  return one.label || (one.name === 'local' ? t('Local') : one.name)
}

/**
 * What a page reads, writes and copies with: the daemon the page shows, which is the only one a
 * page is ever of, and the folder it is of where it is of one.
 *
 * @param {HTMLElement} root Where `Batch apply` draws its dialog.
 * @param {string} [workspace] The folder, for a page of one (views/workspace.js).
 */
export function scopeOf(root, workspace = '') {
  const on = daemon()
  return {
    name: on,
    workspace,
    call: (method, params = {}) => call(method, params, { on }),
    batch: (calls, { off = '', small = true } = {}) => batchButton(root, on, calls, off, small),
  }
}

export function mount(root, { parts, query }) {
  const name = parts[1] in PAGES ? parts[1] : 'general'
  const page = PAGES[name]
  const body = h('div', { class: 'settings-body', 'data-hmz': `settings-${name}` }, h('p', { class: 'loading', role: 'status' }, t('Reading the settings…')))
  let current = null
  const nav = h(
    'nav',
    { class: 'settings-nav', 'aria-label': t('Settings pages') },
    h('h2', {}, t('Settings')),
    GROUPS.map(([group, label]) => [
      h('h4', { class: 'settings-group' }, label),
      Object.entries(PAGES)
        .filter(([, one]) => one.group === group)
        // The dialog opens on the page it shows: its link has the focus.
        .map(([key, one]) => {
          const link = h('a', { href: hash(`/settings/${key}`), 'aria-current': key === name ? 'page' : null, autofocus: key === name }, one.label)
          if (key === name) current = link
          return link
        }),
    ]),
  )
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
      // Whose the page is, said and never picked: the daemon the whole page shows.
      page.group === 'daemon' ? h('div', { class: 'settings-of', 'data-hmz': 'settings-of' }, icon('server'), h('span', { class: 'label' }, t('Daemon')), h('b', {}, called({ name: daemon() }))) : null,
      body,
    ),
  )
  // In the middle of the strip the pages are across a narrow window.
  current.scrollIntoView({ block: 'nearest', inline: 'center' })

  let leaving = null
  let gone = false
  page
    .load()
    .then((module) => {
      if (!gone) leaving = module.draw(body, query, parts, scopeOf(root)) || null
    })
    .catch((error) => fill(body, problem(error)))
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
 * @param {(() => Array<[string, object]>) | null} calls What is called: each method and its params.
 * @param {string} off Why nothing can be, where nothing can.
 * @param {boolean} small Whether the button is as small as a card's own are, not a form's.
 */
function batchButton(root, from, calls, off, small) {
  const button = h('button', { class: ['btn quiet', small && 'small'], type: 'button', 'data-hmz': 'batch-apply', disabled: Boolean(off) }, t('Batch apply'))
  const group = h('span', { class: 'row' }, off ? h('span', { class: 'hint', 'data-hmz': 'batch-off' }, off) : null, button)
  if (off) return group
  button.addEventListener('click', async () => {
    // Every other daemon this browser keeps, read as it is asked for: none where none can be read.
    const others = (await known().catch(() => [])).filter((one) => one.name !== from)
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
