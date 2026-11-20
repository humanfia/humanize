// What this browser keeps of the notices of the daemons the page follows (Section 3.15.2 of
// protocol/web.md): where each daemon's notices are taken up again, and which kinds the user
// wants told of, read afresh for every notice. Kept in a store of values by key -- IndexedDB's,
// on the page -- and never in any daemon's settings; no list of them is kept. What a notice is
// of, where it opens, what the system shows of it, and whether it is shown at all, is said here too.

import { t } from './i18n.js'

/** Every kind the user can switch on or off, by its word, as `Notifications` names it. */
export const KINDS = /** @type {const} */ (['done', 'failed', 'stopped', 'asked', 'listening'])

/** How old a notice may be, in seconds, and still be shown by the system: one older is of an absence, and is marked alone. */
export const STALE = 600

/** What each kind is called. */
const LABELS = { done: t('Done'), failed: t('Failed'), stopped: t('Stopped'), asked: t('Question'), listening: t('Waiting') }

/**
 * Which of the user's kinds a notice is: a chat's turn done is a chat turn, as is a flow waiting
 * for what to say next; every other notice is of its own kind.
 *
 * @param {{kind: string, slot?: string}} notice
 */
export function kindOf(notice) {
  if (notice.kind === 'done' && String(notice.slot || '').startsWith('chat:')) return 'listening'
  return notice.kind
}

/** What a notice is of, by name: its chat, whose `epic` is "", else its epic. */
export const of = (item) => item.chat || item.epic || ''

/** Where a notification opens: the chat it is of; the epic going for what waits on a person, else the epic itself. */
export function addressOf(item) {
  const at = !item.daemon || item.daemon === 'local' ? '#/' : `#/@${encodeURIComponent(item.daemon)}/`
  if (item.chat) return `${at}chats/${encodeURIComponent(item.chat)}`
  if ((item.kind === 'asked' || item.kind === 'listening' || !item.epic) && item.workspace) return `${at}live?${new URLSearchParams({ workspace: item.workspace, ...(item.slot ? { slot: item.slot } : {}) })}`
  return item.epic ? `${at}epics/${encodeURIComponent(item.epic)}` : `${at}live`
}

/**
 * What a notice's text says in one line, as plain words: the first line of it that says anything,
 * without the marks Markdown writes a heading, a quote, a list, emphasis, code and a link with.
 *
 * @param {string} text A notice's text: one line, or a whole reply.
 */
export function lineOf(text) {
  for (const line of String(text || '').split('\n')) {
    const said = line
      .replace(/^\s*(?:(?:```|~~~).*|(?:#{1,6}|>|[-*+]|\d+[.)])(?:\s+|$))+/, '')
      .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/(\*\*|__|~~|`+)(.+?)\1/g, '$2')
      .replace(/(^|[^\w*])([*_])(?=\S)(.*?\S)\2(?![\w*])/g, '$1$3')
      .trim()
    if (/[\p{L}\p{N}]/u.test(said)) return said
  }
  return ''
}

/** What the user wants told: every kind and the system's notifications, until said otherwise. */
export function preferred(said) {
  return { kinds: { ...Object.fromEntries(KINDS.map((one) => [one, true])), ...(said?.kinds || {}) }, system: said?.system !== false }
}

/**
 * What the system shows of a notice: its kind and daemon over its flow -- of a chat, which has
 * none, the first line of its task, which says which chat -- and what it says in one line, else
 * its task's first line, else its name; with where it opens and what it replaces.
 *
 * @returns {{title: string, body: string, address: string, tag: string}}
 */
export function shownAs(item) {
  const daemon = !item.daemon || item.daemon === 'local' ? t('Local') : item.daemon
  const task = String(item.task || '').trim().split('\n')[0]
  const said = lineOf(item.text) || task || of(item)
  const from = item.chat ? task : item.flow
  return { title: `${LABELS[kindOf(item)] || item.kind} · ${daemon}`, body: [from !== said && from, said].filter(Boolean).join(' · '), address: addressOf(item), tag: item.key }
}

/**
 * Whether a notice is of the chat or epic the page is on, while it is looked at.
 *
 * @param {object} item A notice with its daemon.
 * @param {{looked: boolean, daemon: string, parts: string[], query: URLSearchParams}} at Whether the page is visible and focused, the daemon it shows, and where it is.
 */
export function onScreen(item, { looked, daemon, parts, query }) {
  if (!looked || (item.daemon || 'local') !== daemon) return false
  if (parts[0] === 'live') return Boolean(item.workspace) && query.get('workspace') === item.workspace && (query.get('slot') || '') === (item.slot || '')
  if (parts[0] === 'chats') return Boolean(item.chat) && parts[1] === item.chat
  return parts[0] === 'epics' && Boolean(item.epic) && parts[1] === item.epic
}

/** Whether a notice was made lately enough for the system to show it: `at` and `now` in seconds. */
export const fresh = (notice, now = Date.now() / 1000) => now - Number(notice.at || now) <= STALE

/**
 * What is kept of the notices followed, over a store.
 *
 * @param {{get: (key: string) => Promise<any>, put: (key: string, value: any) => Promise<void>}} store
 */
export function followed(store) {
  return {
    /** What the user wants told: `{kinds, system}`. */
    preferences: async () => preferred(await store.get('preferences')),

    /** Keeps what the user wants told. */
    prefer: (said) => store.put('preferences', preferred(said)),

    /** The id of the last notice heard of a daemon, or undefined where none was. */
    after: (daemon) => store.get(`after:${daemon}`),

    /** Keeps where a daemon's notices are taken up again, where nothing is kept yet. */
    async from(daemon, last) {
      if ((await store.get(`after:${daemon}`)) === undefined) await store.put(`after:${daemon}`, last)
    },

    /**
     * Takes a daemon's notices up after this one, and names it by its daemon where its kind is wanted.
     *
     * @returns {Promise<object | null>} The notice with its `daemon` and `key`, or null where its kind is switched off.
     */
    async heard(daemon, notice) {
      await store.put(`after:${daemon}`, notice.id)
      const { kinds } = preferred(await store.get('preferences'))
      return kinds[kindOf(notice)] === false ? null : { ...notice, daemon, key: `${daemon}:${notice.id}` }
    },
  }
}
