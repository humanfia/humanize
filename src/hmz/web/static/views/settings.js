// What humanize remembers, as ChatGPT keeps its settings: a dialog over the page with its pages
// down the side, in the order the terminal interface's `/settings` lists them -- what is true
// wherever humanize runs, who its agents are and what takes over when one fails, where their
// work goes, this one directory -- and last what the runs here spent.

import { shut } from '../app.js'
import { fill, h, iconButton, problem } from '../dom.js'

/** Every page, by the word in the address that opens it. */
const PAGES = {
  general: { label: 'General', about: 'How humanize shows an epic, who a side question goes to, and what it reports.', load: () => import('./settings/general.js') },
  accounts: { label: 'Accounts', about: 'The named sets of credentials an agent can be run as.', load: () => import('./settings/accounts.js') },
  fallback: { label: 'Fallback', about: 'Where a turn goes when the place it runs at cannot take it.', load: () => import('./settings/fallback.js') },
  runtimes: { label: 'Runtimes', about: 'The machines a flow’s environments can be put on.', load: () => import('./settings/runtimes.js') },
  workspace: { label: 'Workspace', about: 'What this directory was last set up with.', load: () => import('./settings/workspace.js') },
  usage: { label: 'Usage', about: 'What the epics here spent, as each counted it against its budget.', load: () => import('./settings/usage.js') },
}

export function mount(root, { parts, query }) {
  const name = parts[1] in PAGES ? parts[1] : 'general'
  const page = PAGES[name]
  const body = h('div', { class: 'settings-body', 'data-hmz': `settings-${name}` }, h('p', { class: 'loading', role: 'status' }, 'Reading the settings…'))
  root.classList.add('dialog-settings')
  root.setAttribute('aria-label', 'Settings')
  fill(
    root,
    h(
      'nav',
      { class: 'settings-nav', 'aria-label': 'Settings pages' },
      h('h2', {}, 'Settings'),
      Object.entries(PAGES).map(([key, one]) => h('a', { href: `#/settings/${key}`, 'aria-current': key === name ? 'page' : null }, one.label)),
    ),
    h(
      'div',
      { class: 'settings-page' },
      h('div', { class: 'settings-head' }, h('div', {}, h('h3', {}, page.label), h('p', { class: 'dim' }, page.about)), iconButton('close', 'Close', { onclick: shut })),
      body,
    ),
  )
  let leaving = null
  let gone = false
  page
    .load()
    .then((module) => {
      if (!gone) leaving = module.draw(body, query) || null
    })
    .catch((error) => fill(body, problem(error)))
  return () => {
    gone = true
    if (leaving) leaving()
  }
}
