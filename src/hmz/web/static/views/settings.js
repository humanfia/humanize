// What humanize remembers, a page at a time, in the order the terminal interface's `/settings`
// lists them: what is true wherever humanize runs, who its agents are and what takes over
// when one fails, where their work goes, and last this one directory.

import { fill, h, problem } from '../dom.js'

/** Every page, by the word in the address that opens it. */
const PAGES = {
  general: { label: 'General', about: 'How humanize shows a run, who a side question goes to, and what it reports.', load: () => import('./settings/general.js') },
  accounts: { label: 'Accounts', about: 'The named sets of credentials an agent can be run as.', load: () => import('./settings/accounts.js') },
  fallback: { label: 'Fallback', about: 'Where a turn goes when the place it runs at cannot take it.', load: () => import('./settings/fallback.js') },
  runtimes: { label: 'Runtimes', about: 'The machines a flow’s environments can be put on.', load: () => import('./settings/runtimes.js') },
  workspace: { label: 'Workspace', about: 'What this directory was last set up with.', load: () => import('./settings/workspace.js') },
}

export function mount(root, { parts }) {
  const name = parts[1] in PAGES ? parts[1] : 'general'
  const page = PAGES[name]
  const body = h('div', { 'data-hmz': `settings-${name}` }, h('p', { class: 'loading', role: 'status' }, 'Reading the settings…'))
  fill(
    root,
    h('div', { class: 'head' }, h('div', {}, h('div', { class: 'kicker' }, 'what humanize remembers'), h('h1', {}, 'Settings'), h('p', { class: 'lede' }, page.about))),
    h(
      'nav',
      { class: 'tabs', 'aria-label': 'Settings pages' },
      Object.entries(PAGES).map(([key, one]) => h('a', { href: `#/settings/${key}`, 'aria-current': key === name ? 'page' : null }, one.label)),
    ),
    body,
  )
  let leaving = null
  let gone = false
  page
    .load()
    .then((module) => {
      if (!gone) leaving = module.draw(body) || null
    })
    .catch((error) => fill(body, problem(error)))
  return () => {
    gone = true
    if (leaving) leaving()
  }
}
