// What the page last saw of each conversation -- a chat, an epic, one of Ai-chan's -- kept so
// that one opened again is drawn at once, with nothing said of its being read (Section 3.6.12
// of protocol/web.md): in memory for the page's life, and in this browser's IndexedDB for the
// next. What is kept is only ever what is drawn first: the daemon is asked again behind it each
// time, and what it answers is what stands.
//
// One entry per conversation, by the daemon it is of, its kind and its id, so that two daemons'
// never mix: the record read (`detail`), what its logs said (`traced`), the records of the run
// its host last told (`live`), and where its thread was scrolled to (`scroll`). Bounded by how
// many are kept, by what they weigh together and by what one may weigh: the one opened longest
// ago goes first, and one too heavy keeps only its end, marked `cut`. Nothing here touches the
// page, so it is read the same by the views and by their tests.

/** The format of what is kept: another, and everything kept as an earlier one is dropped. */
export const FORMAT = 1

/** The most conversations kept, the most they weigh together, and the most one weighs, in characters. */
export const BOUNDS = { entries: 40, bytes: 24 * 1024 * 1024, each: 4 * 1024 * 1024 }

/** The database, and its one store. */
const BASE = 'hmz-logs'
const STORE = 'logs'

/** What a record weighs besides what it says, as held.js weighs one. */
const FRAME = 256

/**
 * What a conversation is kept by: the daemon it is of, its kind -- `chat`, `epic` or `aichan`
 * -- and its id.
 */
export function keyOf(daemon, kind, id) {
  return JSON.stringify([daemon, kind, id])
}

/** What a value weighs: the characters it is written in. */
export function weigh(value) {
  return value === undefined || value === null ? 0 : JSON.stringify(value).length
}

/** What one record of a run weighs, without writing all of it out. */
function recordWeight(record) {
  return String(record.text ?? '').length + (record.context ? weigh(record.context) : 0) + FRAME
}

/** The end of a list that fits in `room`, by what each of it weighs, and what that end weighs. */
function tail(items, room, weight) {
  let used = 0
  let from = items.length
  while (from > 0) {
    const one = weight(items[from - 1])
    if (used + one > room) break
    used += one
    from -= 1
  }
  return { kept: from ? items.slice(from) : items, used, cut: from > 0 }
}

/**
 * An entry as it is kept: weighed, and where it weighs more than one may, cut to its end -- the
 * latest records of its run, with those that say what the run is, and the latest of what each
 * session's log said -- and marked `cut`, by which of the two. One whose record alone is too heavy
 * is not kept: null.
 *
 * @param {object} entry
 * @param {number} [each] The most one may weigh.
 */
export function fitted(entry, each = BOUNDS.each) {
  const fixed = weigh(entry.detail) + weigh(entry.scroll) + FRAME
  if (fixed > each) return null
  let room = each - fixed
  /** Which of its parts are only their end: one given whole again is whole again. */
  const cut = { live: Boolean(entry.cut && entry.cut.live), traced: Boolean(entry.cut && entry.cut.traced) }
  let bytes = fixed
  let live = entry.live || null
  let traced = entry.traced || null
  if (live) {
    // What says which run it is, and who opened what in it, is kept whatever it weighs.
    const heads = live.records.filter((one) => one.type === 'started' || one.type === 'opened')
    const rest = live.records.filter((one) => one.type !== 'started' && one.type !== 'opened')
    const headed = heads.reduce((sum, one) => sum + weigh(one), 0)
    // Half of the room where its logs are kept beside it, so that neither starves the other.
    const mine = Math.max(0, (traced ? room / 2 : room) - headed)
    const end = tail(rest, mine, recordWeight)
    if (end.cut) {
      cut.live = true
      const kept = new Set(end.kept)
      live = { ...live, records: live.records.filter((one) => kept.has(one) || one.type === 'started' || one.type === 'opened') }
    }
    bytes += headed + end.used
    room -= headed + end.used
  }
  if (traced) {
    const share = Math.max(0, room) / Math.max(1, traced.length)
    traced = traced.map((one) => {
      const { actions = [], ...head } = one
      const end = tail(actions, Math.max(0, share - weigh(head)), weigh)
      if (end.cut) cut.traced = true
      bytes += weigh(head) + end.used
      return end.cut ? { ...one, actions: end.kept } : one
    })
  }
  return { ...entry, live, traced, cut: { live: Boolean(live) && cut.live, traced: Boolean(traced) && cut.traced }, bytes }
}

/**
 * Which conversations of a list are worth reading ahead: the latest heard of first, those the
 * cache has not got as they now stand, never the one in front, and never one read ahead a
 * moment ago.
 *
 * @param {{name: string, kind: string, ended?: string, began?: string}[]} rows The list's rows.
 * @param {{peek: (key: string) => object|null}} cache
 * @param {string} daemon
 * @param {{most?: number, front?: string, lately?: (key: string) => boolean}} [how]
 * @returns {{key: string, kind: string, name: string, stamp: string}[]}
 */
export function warmable(rows, cache, daemon, { most = 4, front = '', lately = () => false } = {}) {
  const heard = (row) => String(row.ended || row.began || '')
  return rows
    // A chat whose turn is open is read as it goes, by whoever opens it: never ahead.
    .filter((row) => row.kind !== 'harness' && row.turn !== 'running')
    .sort((a, b) => (heard(a) < heard(b) ? 1 : heard(a) > heard(b) ? -1 : 0))
    .slice(0, most)
    .map((row) => ({ key: keyOf(daemon, row.kind === 'chat' ? 'chat' : 'epic', row.name), kind: row.kind === 'chat' ? 'chat' : 'epic', name: row.name, stamp: heard(row) }))
    .filter((one) => one.key !== front && !lately(one.key) && (cache.peek(one.key) || {}).stamp !== one.stamp)
}

/**
 * How lines drawn become the lines now read, by the key of each: which of those drawn are kept,
 * each where it now stands, which are made anew, and which go. A line is kept wherever one of
 * its key was drawn, the earliest drawn first, so that what was only added to keeps every line
 * it had.
 *
 * @param {string[]} was The keys drawn, in order.
 * @param {string[]} next The keys read, in order.
 * @returns {{from: number[], dropped: number[]}} For each line read, the index of the line drawn
 *   it is, or -1 for one made anew; and the indexes of the lines drawn that go.
 */
export function merged(was, next) {
  const drawn = new Map()
  was.forEach((key, at) => {
    if (!drawn.has(key)) drawn.set(key, [])
    drawn.get(key).push(at)
  })
  const taken = new Set()
  const from = next.map((key) => {
    const queue = drawn.get(key)
    if (!queue || !queue.length) return -1
    const at = queue.shift()
    taken.add(at)
    return at
  })
  return { from, dropped: was.map((_, at) => at).filter((at) => !taken.has(at)) }
}

/**
 * The cache: what was last seen of each conversation, in memory and, where the browser lets it,
 * in its IndexedDB. It is asked and told at once, of memory; what the browser keeps is read
 * into it once, as the page opens (`ready`), and written behind it.
 *
 * @param {object} [made]
 * @param {IDBFactory|null} [made.indexedDB] The browser's, or none: kept in memory alone.
 * @param {{entries: number, bytes: number, each: number}} [made.bounds]
 * @param {() => number} [made.now] The time, in milliseconds.
 * @param {(act: () => void) => void} [made.later] What writes behind, a moment later.
 */
export function logCache({ indexedDB = null, bounds = BOUNDS, now = Date.now, later = (act) => setTimeout(act, 400) } = {}) {
  /** Every entry kept, by its key. */
  const held = new Map()
  /** What is to be written to the browser, or deleted from it (`null`), by its key. */
  const dirty = new Map()
  /** Whether the browser keeps nothing: none to ask, or it refused. */
  let dead = !indexedDB
  let writing = false
  /** @type {Promise<IDBDatabase>|null} */
  let base = null

  /** The database, opened once: an earlier format's entries are dropped as it is. */
  function opened() {
    base ||= new Promise((resolve, reject) => {
      const asked = indexedDB.open(BASE, FORMAT)
      asked.onupgradeneeded = () => {
        const db = asked.result
        for (const name of [...(db.objectStoreNames || [])]) db.deleteObjectStore(name)
        db.createObjectStore(STORE)
      }
      asked.onsuccess = () => resolve(asked.result)
      asked.onerror = () => reject(asked.error || new Error('IndexedDB refused'))
      // Another tab holds an earlier format open: kept in memory alone, here.
      asked.onblocked = () => reject(new Error('IndexedDB blocked'))
    })
    return base
  }

  /** Does `act` on the store in one transaction, resolving once it is done. */
  async function stored(mode, act) {
    const db = await opened()
    return new Promise((resolve, reject) => {
      const doing = db.transaction(STORE, mode)
      const asked = act(doing.objectStore(STORE))
      doing.oncomplete = () => resolve(asked && asked.result)
      doing.onabort = () => reject(doing.error || new Error('IndexedDB aborted'))
      doing.onerror = () => reject(doing.error || new Error('IndexedDB failed'))
    })
  }

  /** Whatever the browser refuses, it keeps nothing from then on: memory alone goes on. */
  async function safely(act) {
    if (dead) return undefined
    try {
      return await act()
    } catch {
      dead = true
      dirty.clear()
      return undefined
    }
  }

  /** Writes behind what changed, once. */
  function write() {
    if (dead || writing || !dirty.size) return
    writing = true
    later(() => {
      writing = false
      flush()
    })
  }

  function flush() {
    if (dead || !dirty.size) return Promise.resolve()
    const batch = [...dirty]
    dirty.clear()
    return safely(() =>
      stored('readwrite', (store) => {
        let last = null
        for (const [key, entry] of batch) last = entry ? store.put(entry, key) : store.delete(key)
        return last
      }),
    )
  }

  /** Lets go of the entries opened longest ago until what is kept is within its bounds. */
  function bound() {
    let bytes = 0
    for (const one of held.values()) bytes += one.bytes
    if (held.size <= bounds.entries && bytes <= bounds.bytes) return
    // Never opened -- read ahead -- before any that was; then by when each was opened, or read.
    const oldest = [...held.values()].sort((a, b) => (a.opened || 0) - (b.opened || 0) || (a.read || 0) - (b.read || 0))
    for (const one of oldest) {
      if (held.size <= bounds.entries && bytes <= bounds.bytes) break
      bytes -= one.bytes
      held.delete(one.key)
      dirty.set(one.key, null)
    }
  }

  const ready = safely(async () => {
    // A browser that throws as it is asked -- a private window's -- keeps nothing.
    const all = await stored('readonly', (store) => store.getAll())
    for (const one of all || []) {
      // What memory has by now is later than what the browser kept.
      if (!one || one.v !== FORMAT || typeof one.key !== 'string' || held.has(one.key)) continue
      held.set(one.key, one)
    }
    bound()
    write()
  }).then(() => undefined)

  return {
    /** Resolves once what the browser kept is read into memory, or could not be. */
    ready,
    /** The entry of a key, or null, as it is: nothing is marked opened. */
    peek: (key) => held.get(key) || null,
    /**
     * The entry of a conversation being opened, or null: marked as opened now. One kept of
     * another daemon than `of`, the id the daemon of that name now answers by, is dropped.
     */
    open(key, { of = '' } = {}) {
      const one = held.get(key)
      if (!one) return null
      if (of && one.of && one.of !== of) {
        this.drop(key)
        return null
      }
      // Written with what is next kept of it, as it is left.
      one.opened = now()
      return one
    },
    /**
     * Keeps what was seen of a conversation, over what was kept of it: what is not given stays
     * as it was. Answers the entry as kept, or null where it is too heavy to keep at all.
     *
     * @param {string} key
     * @param {object} seen `daemon`, `kind`, `id`, and any of `of`, `workspace`, `detail`,
     *   `traced`, `live`, `scroll`, `stamp`, and `opened`, when, by whoever opened it: one
     *   only read ahead has none, and goes before any that was opened.
     */
    put(key, seen) {
      const was = held.get(key) || {}
      // A part given is given whole, whatever was kept of it.
      const cut = { live: !('live' in seen) && Boolean(was.cut && was.cut.live), traced: !('traced' in seen) && Boolean(was.cut && was.cut.traced) }
      const entry = fitted({ ...was, ...seen, cut, v: FORMAT, key, read: now() }, bounds.each)
      if (!entry) {
        this.drop(key)
        return null
      }
      held.set(key, entry)
      dirty.set(key, entry)
      bound()
      write()
      return held.get(key) || null
    },
    /** Forgets one conversation: deleted, or no longer what the daemon says it is. */
    drop(key) {
      held.delete(key)
      if (dead) return
      dirty.set(key, null)
      write()
    },
    /** Forgets every conversation of a daemon: removed, or another now goes by its name. */
    dropOf(daemon) {
      for (const one of [...held.values()]) if (one.daemon === daemon) this.drop(one.key)
    },
    /** Forgets the conversations of one kind of a daemon's that it no longer lists. */
    keep(daemon, kind, ids) {
      const listed = new Set(ids.map(String))
      for (const one of [...held.values()]) if (one.daemon === daemon && one.kind === kind && !listed.has(String(one.id))) this.drop(one.key)
    },
    /** Every key kept. */
    keys: () => [...held.keys()],
    /** What is kept weighs, together. */
    bytes: () => [...held.values()].reduce((sum, one) => sum + one.bytes, 0),
    /** Writes what changed to the browser now, resolving once it has. */
    flush,
  }
}
