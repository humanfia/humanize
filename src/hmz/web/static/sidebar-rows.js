// What the sidebar's list says, apart from how it is drawn: how a chat stands as a chat app says
// it, how a flow's epic stands, and the words a chat and a flow's epic each go by. Nothing here
// touches the page, so it is read the same by the sidebar and by its tests. How the list is
// grouped and sorted is sidebar-view.js.

import { t } from './i18n.js'

/**
 * How a chat's row stands, from its mark: `working` while its agent answers, `asking` while it
 * waits on its person, `failed` where it failed, and '' once it only rests.
 *
 * @param {string} how The chat's mark.
 * @returns {'working' | 'asking' | 'failed' | ''}
 */
export function chatState(how) {
  if (how === 'running') return 'working'
  if (how === 'asking') return 'asking'
  return ['failed', 'refused', 'crashed'].includes(how) ? 'failed' : ''
}

/**
 * A chat's state in words, as a chat app's says it. The sidebar's row writes `Running` and
 * `Failed`; one that waits on its person it marks with a dot, which says `Awaiting input` only
 * to whoever cannot see it or points at it.
 */
export const CHAT_SAID = { working: t('Running'), asking: t('Awaiting input'), failed: t('Failed') }

/**
 * How a flow's epic stands in the words its row says it in: its mark, as a word.
 *
 * @param {string} how The epic's mark.
 */
export function epicSaid(how) {
  return EPIC_SAID[how] || (how ? how[0].toUpperCase() + how.slice(1) : '')
}

/** Each mark an epic stands by, as its row says it; one that is none of them is said as it is. */
const EPIC_SAID = {
  running: t('Running'),
  asking: t('Asking'),
  waiting: t('Waiting'),
  stopping: t('Stopping'),
  done: t('Done'),
  failed: t('Failed'),
  refused: t('Refused'),
  crashed: t('Crashed'),
  stopped: t('Stopped'),
  budget: t('Budget spent'),
  unfinished: t('Unfinished'),
  unknown: t('Unknown'),
}

/** The same marks as a row says them when pointed at, as a badge does (dom.js). */
const STOOD = {
  running: t('running'),
  asking: t('asking'),
  waiting: t('waiting'),
  stopping: t('stopping'),
  done: t('done'),
  failed: t('failed'),
  refused: t('refused'),
  crashed: t('crashed'),
  stopped: t('stopped'),
  budget: t('budget'),
  unfinished: t('unfinished'),
  unknown: t('unknown'),
}

/**
 * How a row stands in the words every list of the page says it in, the sidebar's and Search's
 * alike: a chat's state, only where there is something to say, and a flow's epic's mark.
 *
 * @param {string} how The row's mark.
 * @param {boolean} chat Whether the row is a chat.
 */
export function rowSaid(how, chat) {
  return chat ? CHAT_SAID[chatState(how)] || '' : epicSaid(how)
}

/**
 * What a row says when pointed at: all of what was asked, then, for a chat, how it stands and
 * when it began, and for a flow's epic its flow as well.
 *
 * @param {{task: string}} run The row.
 * @param {{chat: boolean, state?: string, how?: string, flow?: string, began: string}} of A chat's state, or an epic's mark and its flow's name, and when it began in words.
 */
export function rowTitle(run, { chat, state = '', how = '', flow = '', began }) {
  const said = chat ? [CHAT_SAID[state], began] : [flow, STOOD[how] || how, began]
  return `${run.task}\n${said.filter(Boolean).join(' · ')}`
}

/**
 * The keys a shortcut of the sidebar is pressed with, one apiece, as the system writes them.
 *
 * @param {'chat' | 'search'} which Whose: a new chat's, or `Search`'s.
 * @param {boolean} mac Whether the system is Apple's.
 * @returns {string[]}
 */
export function shortcut(which, mac) {
  if (which === 'chat') return mac ? ['⇧', '⌘', 'O'] : ['Ctrl', 'Shift', 'O']
  return mac ? ['⌘', 'K'] : ['Ctrl', 'K']
}

/**
 * The words a row's menu goes by: a chat's never name an epic, a flow or a task.
 *
 * @param {boolean} chat Whether the row is a chat.
 */
export function wording(chat) {
  return chat
    ? { like: t('New chat like it'), task: t('Copy first message'), tasked: t('Message copied'), name: t('Copy ID'), named: t('ID copied') }
    : { like: t('New epic like it'), task: t('Copy task'), tasked: t('Task copied'), name: t('Copy name'), named: t('Name copied') }
}
