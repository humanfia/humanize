// What Search asks for and where its keys go, with no page under it: which tab a search is on,
// what the daemon is asked for it, which result the arrows move to, and what its foot says of
// the keys.

/** The kinds Search lists, as its tabs name them, in their order: a chat is never an epic. */
export const TABS = [
  ['', 'All'],
  ['chat', 'Chats'],
  ['flow', 'Epics'],
]

/**
 * What each key does in Search, as its foot says it: `mac` where the key that opens what can be
 * done with the one moved to is written Option.
 */
export function hints(mac) {
  return [
    ['Close', ['Esc']],
    ['Change type', ['←', '→']],
    ['Filters', ['/']],
    ['Actions', [mac ? 'Option' : 'Alt', 'Enter']],
    ['Move', ['↑', '↓']],
    ['Open', ['Enter']],
  ]
}

/**
 * What a key pressed in Search does, by where it is pressed -- `field` (`empty` while nothing is
 * typed in it), `tabs`, `select` (which keeps its keys to itself) or anywhere `else`: `up` and
 * `down` move along what was found, `open` opens the one moved to, `act` opens what can be done
 * with it (Alt and Enter, or the menu key), `left` and `right` change the tab, `filters` opens
 * and closes the filters, and "" leaves the key to whatever it is pressed on.
 */
export function keyed({ key, altKey, ctrlKey, metaKey, shiftKey }, where, empty = false) {
  if (where === 'select' || ctrlKey || metaKey) return ''
  if (key === 'ContextMenu' || (key === 'F10' && shiftKey && !altKey)) return 'act'
  if (altKey) return key === 'Enter' && !shiftKey ? 'act' : ''
  if (shiftKey) return ''
  if (key === 'ArrowDown') return 'down'
  if (key === 'ArrowUp') return 'up'
  if (where !== 'field' && where !== 'tabs') return ''
  if (key === 'Enter') return 'open'
  if (where === 'field' && !empty) return ''
  if (key === 'ArrowLeft') return 'left'
  if (key === 'ArrowRight') return 'right'
  return key === '/' ? 'filters' : ''
}

/** How many rows a page of the list holds. */
export const PAGE = 50

/**
 * What an address asks Search for: its tab, and the filters under it. An address of before the
 * tabs named chats as the flow `chat`, which is the tab `Chats` now. A flow named with no tab is
 * on `All`, where only that flow's epics are of it; one named with `Chats` is dropped, as the
 * tab pressed drops it.
 */
export function chosenOf(query) {
  const said = (name) => query.get(name) || ''
  const kind = said('flow') === 'chat' ? 'chat' : TABS.some(([kind]) => kind === said('kind')) ? said('kind') : ''
  return {
    kind,
    status: said('status'),
    flow: kind === 'chat' ? '' : said('flow'),
    workspace: said('workspace'),
    q: said('q'),
    offset: Math.max(0, Number(said('offset')) || 0),
  }
}

/** What `runs.list` is asked for one page of what is chosen: a chat is of no flow. */
export function asked(chosen) {
  return {
    kind: chosen.kind,
    status: chosen.status,
    flow: chosen.kind === 'chat' ? '' : chosen.flow,
    workspace: chosen.workspace,
    q: chosen.q,
    offset: chosen.offset,
    limit: PAGE,
  }
}

/** The tab a step left (-1) or right (1) of one, which stops at either end. */
export function turned(kind, step) {
  const at = TABS.findIndex(([one]) => one === kind)
  return TABS[Math.min(TABS.length - 1, Math.max(0, at + step))][0]
}

/** What is chosen once a tab is pressed: `Chats` drops the flow, which no chat has. */
export function onTab(chosen, kind) {
  return { ...chosen, kind, flow: kind === 'chat' ? '' : chosen.flow, offset: 0 }
}

/** What is chosen once a flow is: a flow's are epics, so `Chats` gives way to `Epics`. */
export function onFlow(chosen, flow) {
  return { ...chosen, flow, kind: flow && chosen.kind === 'chat' ? 'flow' : chosen.kind, offset: 0 }
}

/** Whether a filter under the tabs is set, so that the row of them is shown as Search opens. */
export function filtered(chosen) {
  return Boolean(chosen.status || chosen.flow || chosen.workspace)
}

/** Whether anything narrows the list: nothing found then is nothing like that, not nothing yet. */
export function narrowed(chosen) {
  return Boolean(chosen.kind || chosen.q || filtered(chosen))
}

/**
 * What is said where nothing was found, as a headline and what to do about it: nothing like what
 * was typed or filtered for, or none of the tab's kind yet -- a tab is no filter to clear.
 */
export function nothing(chosen) {
  if (chosen.q || filtered(chosen)) return ['Nothing is like that.', ' Clear the filters to see every chat and epic.']
  if (chosen.kind === 'chat') return ['No chats yet.', ' Start a chat, and it is written down here as it goes.']
  if (chosen.kind === 'flow') return ['No epics yet.', ' Start an epic, and it is written down here as it goes.']
  return ['Nothing here yet.', ' Start a chat or an epic, and it is written down here as it goes.']
}

/** What stands over the results: the newest of everything, or what was found. */
export function heading(chosen) {
  return narrowed(chosen) ? 'Results' : 'Recents'
}

/**
 * Which of `count` results a key moves to from the one at `at` (-1 where none is): the arrows
 * go round, Home and End go to either end, and any other key leaves it where it is.
 */
export function moved(at, count, key) {
  if (!count) return -1
  if (key === 'ArrowDown') return at < 0 ? 0 : (at + 1) % count
  if (key === 'ArrowUp') return at < 0 ? count - 1 : (at - 1 + count) % count
  if (key === 'Home') return 0
  if (key === 'End') return count - 1
  return Math.min(at, count - 1)
}

/** Which rows a page shows of how many, as the foot says it. */
export function paged(data) {
  return data.total ? `${data.offset + 1}–${data.offset + data.runs.length} of ${data.total}` : ''
}
