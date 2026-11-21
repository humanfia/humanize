// How the sidebar's list is arranged, apart from how it is drawn: what `Group and sort` chose,
// the groups that makes of the rows listed, how many of a group are shown, which rows are pinned
// or marked unread in this browser, and how wide the sidebar may be dragged. Nothing here touches
// the page, so it is read the same by the sidebar and by its tests.

import { t } from './i18n.js'

/** What `Group and sort` offers, the first of each the default. */
export const GROUPS = /** @type {const} */ ([['folder', t('Folder')], ['date', t('Date')], ['none', t('None@@group')]])
export const SORTS = /** @type {const} */ ([['updated', t('Last updated')], ['created', t('Created')]])
export const SHOWS = /** @type {const} */ ([['chats', t('Chats')], ['epics', t('Epics')]])

/** The list as it is until `Group and sort` says otherwise. */
export const DEFAULTS = Object.freeze({ group: 'folder', sort: 'updated', chats: true, epics: true })

/** How many rows a group shows before `Show N more`. */
export const GROUP_ROWS = 20

/** How narrow and how wide the sidebar may be dragged, and how wide it is until it is. */
export const WIDTHS = Object.freeze({ least: 200, most: 480, usual: 275 })

/**
 * What `Group and sort` chose, read from what this browser keeps: anything it does not offer is
 * the default.
 *
 * @param {string | null | undefined} text
 * @returns {{group: string, sort: string, chats: boolean, epics: boolean}}
 */
export function viewOf(text) {
  let said = {}
  try {
    said = JSON.parse(text || '{}') || {}
  } catch {
    // Kept wrong, it is the defaults.
  }
  return {
    group: GROUPS.some(([key]) => key === said.group) ? said.group : DEFAULTS.group,
    sort: SORTS.some(([key]) => key === said.sort) ? said.sort : DEFAULTS.sort,
    chats: said.chats !== false,
    epics: said.epics !== false,
  }
}

/** What a browser keeps of a view: nothing where it is the defaults. */
export function viewText(view) {
  const now = viewOf(JSON.stringify(view))
  return Object.keys(DEFAULTS).every((key) => now[key] === DEFAULTS[key]) ? null : JSON.stringify(now)
}

/** Whether a row is a chat, as its row says it. */
const byKind = (run) => run.kind === 'chat'

/** Whether a row is going, by a host or by another process: an epic's alone, a chat never is. */
const going = (run) => !byKind(run) && (Boolean(run.held) || run.how === 'running')

/** When a row was last heard of: when it ended, else when it began. */
const last = (run) => Date.parse(run.ended) || Date.parse(run.began) || 0

/** Where a row stands under a sort: one going is the last updated of all. */
function stamp(run, sort, now) {
  if (sort === 'created') return Date.parse(run.began) || 0
  return going(run) ? now : last(run)
}

/**
 * The rows `Show` leaves, in the order `Sort by` gives them: newest first, as they came where alike.
 *
 * @param {object[]} runs The rows listed.
 * @param {{sort: string, chats: boolean, epics: boolean}} view What `Group and sort` chose.
 * @param {number} [now] The moment one going was last updated.
 * @param {(run: object) => boolean} [chat] Which rows are chats.
 */
export function sorted(runs, view, now = Date.now(), chat = byKind) {
  return (runs || [])
    .filter((run) => (chat(run) ? view.chats : view.epics))
    .map((run, at) => ({ run, at, stamp: stamp(run, view.sort, now) }))
    .sort((a, b) => b.stamp - a.stamp || a.at - b.at)
    .map((one) => one.run)
}

/** The groups `Date` makes, by how many days ago a row stands. */
const DAYS = [
  [0, 'today', t('Today')],
  [1, 'yesterday', t('Yesterday')],
  [7, 'week', t('Last 7 days')],
  [30, 'month', t('Last 30 days')],
  [Infinity, 'older', t('Older')],
]

/** How many midnights of this place lie between a moment and now. */
function daysAgo(at, now) {
  const day = (stamp) => {
    const date = new Date(stamp)
    return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())
  }
  return Math.max(0, Math.round((day(now) - day(at)) / 86400000))
}

/**
 * The workspaces the list gives a heading: every one `workspaces.list` answers but those whose
 * directory is gone (`there` false) and that hold nothing -- no epic, no chat, nothing going --
 * which have nothing to show and nowhere to start anything.
 *
 * @param {{path: string, there?: boolean, epics?: number, chats?: number, running?: boolean}[]} [workspaces]
 */
export function shownFolders(workspaces = []) {
  return (workspaces || []).filter((one) => one.there !== false || one.epics || one.chats || one.running)
}

/** What the group of the rows that have no folder is called, and what it is kept by. */
export const NO_FOLDER = t('No folder')
const NOWHERE = ':nowhere'

/**
 * The list's groups, in their order: the rows pinned first, under `Pinned`, then the rest by
 * folder -- every workspace offered, those with a row a host goes with first, then by their
 * latest, and last the rows of no folder, those of every folderless workspace together -- by date, or as one group. Grouped by date, a list with
 * nothing to show keeps `Today`, and grouped by folder, with no folder either, `No folder`, so
 * that a heading is always there; grouped by anything but
 * folder, the folders stand last as a group of their own, `Folders`, each with how many rows it has.
 *
 * @param {{workspaces?: {path: string}[], runs?: object[], view: object, pinned?: Set<string>, now?: number, chat?: (run: object) => boolean}} of
 * @returns {{key: string, kind: 'pinned'|'folder'|'date'|'all'|'folders', label: string, path: string, runs: object[], folders?: {path: string, count: number}[]}[]}
 */
export function arranged({ workspaces = [], runs = [], view, pinned = new Set(), now = Date.now(), chat = byKind }) {
  const rows = sorted(runs, view, now, chat)
  const kept = rows.filter((run) => pinned.has(run.name))
  const rest = rows.filter((run) => !pinned.has(run.name))
  const groups = kept.length ? [{ key: ':pinned', kind: 'pinned', label: t('Pinned'), path: '', runs: kept }] : []
  const folders = new Map()
  for (const one of workspaces || []) if (one.path) folders.set(one.path, { key: one.path, kind: 'folder', label: '', path: one.path, runs: [] })
  for (const run of rest) {
    // What was started in no folder stands together, whatever directory was made for each.
    const path = run.folderless ? '' : run.workspace || ''
    if (!folders.has(path)) folders.set(path, { key: path || NOWHERE, kind: 'folder', label: path ? '' : NO_FOLDER, path, runs: [] })
    folders.get(path).runs.push(run)
  }
  const rank = (group) => (group.runs.some((one) => one.held && !byKind(one)) ? 1e14 : 0) + Math.max(0, ...group.runs.map((run) => (view.sort === 'created' ? Date.parse(run.began) || 0 : last(run))))
  const ordered = [...folders.values()].sort((a, b) => Number(!a.path) - Number(!b.path) || rank(b) - rank(a))
  // A list with no folder and nothing to show keeps the group of none, so that a heading, and
  // `Group and sort` on it, is always there.
  if (view.group === 'folder') return groups.length || ordered.length ? [...groups, ...ordered] : [{ key: NOWHERE, kind: 'folder', label: NO_FOLDER, path: '', runs: [] }]
  // Every folder, reachable though the list is not grouped by them.
  const named = ordered.filter((one) => one.path).map((one) => ({ path: one.path, count: one.runs.length }))
  const places = named.length ? [{ key: ':folders', kind: 'folders', label: t('Folders'), path: '', runs: [], folders: named }] : []
  if (view.group === 'none') return [...groups, { key: ':all', kind: 'all', label: t('All'), path: '', runs: rest }, ...places]
  const days = DAYS.map(([, key, label]) => ({ key: `:date:${key}`, kind: 'date', label, path: '', runs: [] }))
  for (const run of rest) days[DAYS.findIndex(([most]) => daysAgo(stamp(run, view.sort, now), now) <= most)].runs.push(run)
  const full = days.filter((one) => one.runs.length)
  return [...groups, ...(full.length || groups.length ? full : [days[0]]), ...places]
}

/**
 * The rows of a group that are shown, and how many `Show N more` would bring: the first `shown`
 * of them, and with them the one the page is on, wherever in the group it stands.
 *
 * @param {object[]} runs The group's rows.
 * @param {number} [shown] How many it shows.
 * @param {string} [here] The row the page is on.
 */
export function paged(runs, shown = GROUP_ROWS, here = '') {
  const rows = runs.filter((run, at) => at < shown || run.name === here)
  return { rows, more: runs.length - rows.length }
}

/**
 * A list of names this browser keeps -- the rows pinned, or marked unread -- with one put in or
 * taken out: the newest last, and no more than `most` of them.
 */
export function toggled(list, name, on, most = 200) {
  const rest = (list || []).filter((one) => one !== name)
  return (on ? [...rest, name] : rest).slice(-most)
}

/** How wide the sidebar is, from what was dragged or kept: within its bounds, the usual where it says nothing. */
export function widthOf(value) {
  const wide = Math.round(Number(value))
  if (!Number.isFinite(wide) || wide <= 0) return WIDTHS.usual
  return Math.min(WIDTHS.most, Math.max(WIDTHS.least, wide))
}
