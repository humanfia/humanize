// What the sidebar's list says, apart from how it is drawn: how a chat stands as a chat app says
// it, how a flow's epic stands, and the words a chat and a flow's epic each go by. Nothing here
// touches the page, so it is read the same by the sidebar and by its tests. How the list is
// grouped and sorted is sidebar-view.js.

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

/** A chat's state in the words its row says it in, as a chat app's does. */
export const CHAT_SAID = { working: 'Running', asking: 'Awaiting input', failed: 'Failed' }

/**
 * How a flow's epic stands in the words its row says it in: its mark, as a word.
 *
 * @param {string} how The epic's mark.
 */
export function epicSaid(how) {
  if (how === 'budget') return 'Budget spent'
  return how ? how[0].toUpperCase() + how.slice(1) : ''
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
  const said = chat ? [CHAT_SAID[state], began] : [flow, how, began]
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
    ? { like: 'New chat like it', task: 'Copy first message', tasked: 'Message copied', name: 'Copy ID', named: 'ID copied' }
    : { like: 'New epic like it', task: 'Copy task', tasked: 'Task copied', name: 'Copy name', named: 'Name copied' }
}
