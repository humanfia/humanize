// What one folder keeps, in a dialog of its own, opened from that folder in the sidebar: what it
// was last set up with, what ran there spent, and the chats archived there (Section 3.11.4 of
// protocol/web.md). The folder is the one the address names, said over its pages and never
// picked here; `No folder`, named by `scratch`, has only its archived chats. The daemon is the
// one the page shows.

import { hash } from '../api.js'
import { shut, stays } from '../app.js'
import { fill, h, icon, iconButton, pathText, problem } from '../dom.js'
import { t } from '../i18n.js'
import { firstOf, missing, nameOf, there, workspaceAt, workspaces } from '../places.js'
import { dragged } from '../shell.js'
import { NO_FOLDER } from '../sidebar-view.js'
import { scopeOf } from './settings.js'

/** Every page, by the word in the address that opens it: `folder` where only a folder has it. */
const PAGES = {
  setup: { folder: true, label: t('Setup'), about: t('What this folder was last set up with'), load: () => import('./workspace/setup.js') },
  // The page `Usage` of Settings is, of one folder: the same drawing, asked of this folder.
  usage: { folder: true, label: t('Usage'), about: t('What this folder spent, by day and flow'), load: () => import('./settings/usage.js') },
  archived: { label: t('Archived chats'), about: t('Chats of this folder that were put away'), none: t('Chats of no folder that were put away'), load: () => import('./workspace/archived.js') },
}

export function mount(root, { parts, query }) {
  let leaving = null
  let gone = false
  root.classList.add('dialog-settings', 'dialog-workspace')
  root.setAttribute('aria-label', t('Workspace settings'))

  /** Draws the dialog of a folder, or of none. */
  function draw(workspace, listed) {
    if (gone) return
    const name = parts[1] in PAGES && (workspace || !PAGES[parts[1]].folder) ? parts[1] : workspace ? 'setup' : 'archived'
    const page = PAGES[name]
    const called = workspace ? nameOf(workspace) : NO_FOLDER
    // Named by the folder it is of, which is all it is about.
    root.setAttribute('aria-label', t('Workspace settings: {name}', { name: called }))
    const body = h('div', { class: 'settings-body', 'data-hmz': `workspace-${name}` }, h('p', { class: 'loading', role: 'status' }, t('Reading the settings…')))
    const nav = h(
      'nav',
      { class: 'settings-nav', 'aria-label': t('Workspace settings pages') },
      h('h2', {}, t('Workspace settings')),
      Object.entries(PAGES)
        .filter(([, one]) => workspace || !one.folder)
        // The dialog opens on the page it shows: its link has the focus.
        .map(([key, one]) => h('a', { href: hash(workspaceAt(workspace, key)), 'aria-current': key === name ? 'page' : null, autofocus: key === name }, one.label)),
    )
    fill(
      root,
      // The top row of a narrow window, which it fills; on a wide one, a column inside it.
      dragged(nav, 'deep', 'narrow'),
      h(
        'div',
        { class: 'settings-page' },
        h('div', { class: 'settings-head' }, h('div', {}, h('h3', {}, page.label), h('p', { class: 'dim' }, workspace ? page.about : page.none)), iconButton('close', t('Close'), { onclick: shut })),
        // Which folder it is of, said and never picked: its name, its whole path, and that it is gone where it is.
        h(
          'div',
          { class: 'settings-of', 'data-hmz': 'workspace-of' },
          icon('folder'),
          h('span', { class: 'label' }, t('Workspace')),
          h('b', { 'data-hmz': 'workspace-name' }, called),
          workspace ? h('span', { class: 'settings-path' }, pathText(workspace), missing(workspace, listed) ? h('span', { class: 'chip', 'data-hmz': 'workspace-missing' }, t('Missing')) : null) : null,
        ),
        body,
      ),
    )
    root.querySelector('[autofocus]').focus()
    // Kept in the address, where the address named none.
    if (workspace && !query.get('workspace')) stays({ workspace })
    page
      .load()
      .then((module) => {
        if (!gone) leaving = module.draw(body, query, parts, scopeOf(root, workspace)) || null
      })
      .catch((error) => fill(body, problem(error)))
  }

  const named = query.get('workspace') || ''
  fill(root, h('p', { class: 'loading', role: 'status' }, t('Reading the settings…')))
  // Which folders there are says whether this one's directory is gone; and an address that
  // names neither a folder nor `No folder` -- one of Settings as it was -- is of the folder
  // offered first, where there is one.
  workspaces(true).then(
    (answer) => draw(named || (query.get('scratch') !== '1' && answer.workspaces.some(there) ? firstOf(answer) : ''), answer),
    () => draw(named, null),
  )
  return () => {
    gone = true
    if (leaving) leaving()
  }
}
