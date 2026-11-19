// One host's runs as a subscription: the records read, how it stands, and the attaching that
// brings them. The page's held.js gives it the daemon's attach, the page's frame to draw in, and
// what a terminal or a face needs of each message; a test gives it a fake attach and reads what
// it does.

/** The most records kept per workspace, and about how many bytes of them, as the daemon keeps. */
const KEPT = 20000
const WEIGHED = 32 * 1024 * 1024

/** What a record weighs besides what it says, as the daemon weighs one. */
const FRAME = 256

/** The snapshots a host sends, each kept by its type (Section 4.9.3 of protocol/daemon.md). */
const STANDING = new Set(['clients', 'claims', 'away', 'run', 'sessions', 'calls', 'waiting', 'pending', 'usage', 'board', 'envs'])

/**
 * One host followed: its state, who is told of it, and the subscription that keeps it.
 *
 * @param {string} workspace The host's workspace.
 * @param {string} slot Its slot, or "" for the workspace's own.
 * @param {{
 *   attach: Function,
 *   schedule?: (draw: () => void) => void,
 *   onMessage?: (message: object, mine: Promise<object>) => void,
 *   onEnd?: () => void,
 * }} given
 * @returns {object} The following: its `state`, its `listeners`, and `connect`, `close` and `refresh`.
 */
export function following(workspace, slot, { attach, schedule = (draw) => draw(), onMessage = () => {}, onEnd = () => {} }) {
  if (typeof attach !== 'function') throw new TypeError('a following needs an attach')
  const state = { workspace, slot, connected: false, gone: '', me: '', epoch: '', seq: 0, standing: {}, records: [], figures: null }
  const listeners = new Set()
  let weights = []
  let weight = 0
  let pending = 0
  /** The attaching that is this one's now: what an earlier one says is said to nobody. */
  let opening = null
  const one = { state, listeners, opening: null, sub: null, refreshing: false, connect, close, refresh }

  function tell() {
    if (pending) return
    pending = 1
    schedule(() => {
      pending = 0
      for (const told of [...listeners]) told(state)
    })
  }

  function hear(mine, message) {
    if (opening !== mine) return
    try {
      onMessage(message, mine)
    } catch (error) {
      console.error(error)
    }
    const type = message.type
    if (type === 'welcome') {
      if (message.epoch !== state.epoch) {
        // Another life of the host's: everything is told again, from the top.
        Object.assign(state, { epoch: message.epoch, seq: 0, standing: {}, records: [], figures: null })
        weights = []
        weight = 0
      }
      Object.assign(state, { me: message.client, connected: true, gone: '' })
    } else if (type === 'live') state.connected = true
    else if (typeof message.seq === 'number') {
      // A host that cannot go on from where this page was sends its history from the top: what
      // the page holds is not what came after its last record, so it starts over.
      if (state.records.length && message.seq <= state.seq) {
        state.records = []
        weights = []
        weight = 0
        state.seq = 0
      }
      state.seq = Math.max(state.seq, message.seq)
      const weighs = String(message.text ?? '').length + (message.context ? JSON.stringify(message.context).length : 0) + FRAME
      state.records.push(message)
      weights.push(weighs)
      weight += weighs
      let dropped = 0
      while (state.records.length - dropped > KEPT || (weight > WEIGHED && state.records.length - dropped > 1)) weight -= weights[dropped++]
      if (dropped) {
        state.records.splice(0, dropped)
        weights.splice(0, dropped)
      }
    } else if (STANDING.has(type)) state.standing = { ...state.standing, [type]: message }
    else if (type === 'figures') state.figures = message
    else return
    tell()
  }

  /** The subscription ended on its own: let go, the host gone, or attaching it again refused. */
  function ended(mine, why) {
    if (opening !== mine) return
    opening = one.opening = null
    one.sub = null
    onEnd()
    state.connected = false
    state.gone = why || 'The host let this page go.'
    tell()
    // A chat's host goes as it folds away, and is not reached again: it is carried on anew. The
    // workspace's own is attached again, after a moment, while a view still follows it.
    if (!slot) {
      setTimeout(() => {
        if (!one.opening && listeners.size) connect()
      }, 500)
    }
  }

  function connect() {
    const since = state.epoch && state.seq ? { epoch: state.epoch, seq: state.seq } : null
    const mine = attach(
      { workspace, slot, figures: true, ...(since ? { since } : {}) },
      (message) => hear(mine, message),
      (why) => ended(mine, why),
    )
    opening = one.opening = mine
    mine.then(
      (sub) => {
        // Let go of before it was attached: nobody hears it.
        if (opening !== mine) sub.close()
        else one.sub = sub
      },
      (error) => {
        if (opening !== mine) return
        opening = one.opening = null
        one.sub = null
        state.connected = false
        state.gone = error.message
        tell()
      },
    )
  }

  /**
   * Attaches again from the last record read, ending the subscription it had: what a connection
   * that went quiet without closing needs. The close is not waited for -- a detach that never
   * answers would hold every later refresh -- and the new attach goes on without it.
   */
  async function refresh() {
    if (one.refreshing) return
    one.refreshing = true
    try {
      const sub = one.sub
      one.sub = null
      // Both, so that a close that calls `ended` finds no attach of its own to tell about.
      opening = one.opening = null
      onEnd()
      if (sub) {
        try {
          Promise.resolve(sub.close()).catch(() => {})
        } catch {
          // A close that throws has still let go of the page.
        }
      }
      connect()
    } finally {
      one.refreshing = false
    }
  }

  function close() {
    const was = opening
    const sub = one.sub
    opening = one.opening = null
    one.sub = null
    onEnd()
    state.connected = false
    if (sub) {
      try {
        Promise.resolve(sub.close()).catch(() => {})
      } catch {
        // A close that throws has still let go of the page.
      }
    }
    was?.then((sub) => sub.close(), () => {})
  }

  return one
}
