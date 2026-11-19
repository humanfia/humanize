// The notifications list, as this browser keeps it (Section 3.15.2 of protocol/web.md): the
// notices of every daemon the page follows gathered into one list, the newest 200, each naming
// its daemon and whether it is read; where each daemon's notices are taken up again; and which
// kinds the user wants told of, read afresh for every notice. Kept in a store of values by key --
// IndexedDB's, on the page -- and never in any daemon's settings. What a notice is of, and where
// it opens, is said here too.

/** Every kind the user can switch on or off, by its word, as `Notifications` names it. */
export const KINDS = /** @type {const} */ (['done', 'failed', 'stopped', 'asked', 'listening'])

/** How many notifications are kept. */
export const KEPT = 200

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

/** What the user wants told: every kind and the system's notifications, until said otherwise. */
export function preferred(said) {
  return { kinds: { ...Object.fromEntries(KINDS.map((one) => [one, true])), ...(said?.kinds || {}) }, system: said?.system !== false }
}

/**
 * The notifications list over a store.
 *
 * @param {{get: (key: string) => Promise<any>, put: (key: string, value: any) => Promise<void>}} store
 */
export function gathered(store) {
  /** Each change after the last, so that two notices heard at once both stay. */
  let queue = Promise.resolve()
  const changes = (change) => {
    const done = queue.then(async () => {
      const items = (await store.get('items')) || []
      const [now, answer] = await change(items)
      if (now !== items) await store.put('items', now)
      return answer
    })
    queue = done.catch(() => {})
    return done
  }
  return {
    /** Every notification kept, newest first. */
    items: async () => (await store.get('items')) || [],

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
     * Keeps a notice of a daemon as a notification, where its kind is wanted.
     *
     * @returns {Promise<object | null>} The notification, or null where it is not kept.
     */
    async heard(daemon, notice) {
      await store.put(`after:${daemon}`, notice.id)
      const { kinds } = preferred(await store.get('preferences'))
      if (kinds[kindOf(notice)] === false) return null
      const key = `${daemon}:${notice.id}`
      return changes((items) => {
        if (items.some((one) => one.key === key)) return [items, null]
        const made = { ...notice, key, daemon, read: false }
        return [[made, ...items].slice(0, KEPT), made]
      })
    },

    /** Marks those of `keys` read, or every one where `keys` is null. */
    read: (keys) => changes((items) => [items.map((one) => (!keys || keys.includes(one.key) ? { ...one, read: true } : one)), null]),

    /** Forgets every notification. */
    clear: () => changes(() => [[], null]),
  }
}
