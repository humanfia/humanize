// The runs held for each workspace, as subscriptions the views of the page share: per host of a
// workspace -- its own, which runs its flows one at a time, and each chat's beside it, by its
// slot -- the records of the run in front of it, how everything stands, and the figures the
// daemon works out -- the same the terminal interface draws (`epic.attach` with `figures`,
// Section 4.7 of protocol/daemon.md). A host is followed only while a view of it is open. What a
// view asks of a host's runs goes through `ask`, as a call to the epic on its subscription; what
// it asks of a chat -- starting one, saying its next line, its catalogue, stopping its turn --
// through `chatAsk`.
//
// A host is named by `where`: a workspace's path alone for the workspace's own, or
// `{workspace, slot}` for a chat's.

import { attach, call, onDaemon } from './api.js'
import { Flow } from './views/envs/terminal_flow.js'

/** The most records kept per workspace, and about how many bytes of them, as the daemon keeps. */
const KEPT = 20000
const WEIGHED = 32 * 1024 * 1024

/** What a record weighs besides what it says, as the daemon weighs one. */
const FRAME = 256

/** The snapshots a host sends, each kept by its type (Section 4.9.3 of protocol/daemon.md). */
const STANDING = new Set(['clients', 'claims', 'away', 'run', 'sessions', 'calls', 'waiting', 'pending', 'usage', 'board', 'envs'])

/** Every host followed, by its workspace's path and its slot. */
const followed = new Map()

/** Who hears every message of a host as it comes, by the host's key: kept apart from following it. */
const heard = new Map()

/** A host, named either way, as `{workspace, slot}`: slot '' for the workspace's own. */
export function placed(where) {
  return typeof where === 'string' ? { workspace: where, slot: '' } : { workspace: where.workspace, slot: where.slot || '' }
}

/**
 * Follows one host's runs: told the state now and again whenever it changes, until stopped.
 *
 * @param {string|{workspace: string, slot: string}} where The host.
 * @param {(state: object) => void} told
 * @returns {() => void} What stops following.
 */
export function follow(where, told) {
  const { workspace, slot } = placed(where)
  const key = `${workspace}\n${slot}`
  let one = followed.get(key)
  if (!one) followed.set(key, (one = following(workspace, slot)))
  one.listeners.add(told)
  if (!one.opening) one.connect()
  told(one.state)
  return () => {
    one.listeners.delete(told)
    // Nobody reads it any more: the subscription goes after a moment, in case a view comes back.
    if (!one.listeners.size) {
      setTimeout(() => {
        if (one.listeners.size) return
        one.close()
        if (followed.get(key) === one) followed.delete(key)
      }, 5000)
    }
  }
}

/**
 * Asks one host's runs one thing: `start`, `say`, `answer`, `stop`, `force`, `afk`, … -- the call
 * `epic.<what>` on the subscription that follows the host, attached first where none does. An
 * epic started with `scratch` is started in a directory made for it alone. A chat is started
 * with `chatAsk`, never here.
 */
export async function ask(where, what, body = {}) {
  const { workspace, slot } = placed(where)
  if (what === 'start') return starts(workspace, slot, body)
  return hosted({ workspace, slot }, `epic.${what}`, body)
}

/**
 * Calls a method on the subscription that follows a host, as `sub`: one of `epic.*`, or one of
 * an environment's (`env.*`), attached first where none does.
 */
export async function hosted(where, method, params = {}) {
  const { workspace, slot } = placed(where)
  const stop = follow({ workspace, slot }, () => {})
  try {
    const opening = followed.get(`${workspace}\n${slot}`).opening
    if (!opening) throw new Error('This host cannot be reached.')
    const sub = await opening
    return await call(method, { ...params, sub: sub.sub })
  } finally {
    stop()
  }
}

/**
 * Tells `fn` every message of a host's subscription as it comes -- those it keeps and those it
 * does not, such as a terminal's output sent to this page alone -- while something follows it.
 * A terminal's output (`term`) is `fn`'s to acknowledge only where it answers `true`, as one that
 * draws it does: what nobody takes is acknowledged here, since a terminal left running is still
 * one this page views, and its host stops reading it once its output goes unacknowledged
 * (Section 4.24.4.6 of protocol/daemon.md).
 *
 * @returns {() => void} What stops telling it.
 */
export function hearing(where, fn) {
  const { workspace, slot } = placed(where)
  const key = `${workspace}\n${slot}`
  if (!heard.has(key)) heard.set(key, new Set())
  const fns = heard.get(key)
  fns.add(fn)
  return () => {
    fns.delete(fn)
    if (!fns.size && heard.get(key) === fns) heard.delete(key)
  }
}

/** Starts an epic as it is set up, writing that down as the workspace's set-up of its flow. */
async function starts(workspace, slot, { scratch = false, ...said }) {
  const sub = await attach({ ...(scratch ? { scratch: true } : { workspace }), slot, replay: false }, () => {})
  try {
    const started = await call('epic.start', { ...said, remember: true, sub: sub.sub })
    // Followed a moment longer, as the view gone to next follows it.
    follow({ workspace: started.workspace, slot: started.slot }, () => {})()
    return started
  } finally {
    sub.close()
  }
}

/**
 * Asks a chat going one thing: `start`, `say`, `commands`, `set`, `stop` -- the call
 * `chat.<what>` (Section 4.25 of protocol/daemon.md), which names the chat by its workspace and
 * slot rather than by a subscription. A chat started at a workspace alone is a new chat's, on a
 * host of its own beside every epic there, which the answer names; one started with `scratch`
 * is started in a directory made for it alone; one carried on is started with `resume`, its id.
 *
 * @param {string|{workspace: string, slot: string}} where The chat, or the workspace a new one starts in.
 * @param {string} what The method of `chat.*`.
 * @param {object} [params] Its parameters but `workspace` and `slot`; `scratch` for `start`.
 */
export async function chatAsk(where, what, params = {}) {
  const { workspace, slot } = placed(where)
  if (what === 'start') return chatStarts(workspace, slot, params)
  return call(`chat.${what}`, { ...params, workspace, slot })
}

/** Starts a chat, or carries one on, answering `{workspace, slot, chat}`. */
async function chatStarts(workspace, slot, { scratch = false, ...said }) {
  // No workspace: a directory made for the chat alone, as `scratch` makes one for an epic, with
  // a chat's host of its own there, which the chat then starts on.
  const made = scratch ? await scratchChat() : null
  try {
    const at = made ? made.workspace : workspace
    const started = await call('chat.start', { ...said, workspace: at, slot: made ? made.slot : slot || 'chat:' })
    // Followed a moment longer, as the view gone to next follows it.
    follow({ workspace: at, slot: started.slot }, () => {})()
    return { ...started, workspace: at }
  } finally {
    made?.sub.close()
  }
}

/** A new chat's host in a directory made for it alone: where it is, as its welcome says. */
async function scratchChat() {
  let welcomed = (_message) => {}
  let gone = (_error) => {}
  const where = new Promise((resolve, reject) => {
    welcomed = resolve
    gone = reject
  })
  // Settled however the attaching goes, so that no refusal of it is left unheard.
  where.catch(() => {})
  const sub = await attach(
    { scratch: true, slot: 'chat:', replay: false },
    (message) => message.type === 'welcome' && welcomed(message),
    (why) => gone(new Error(why || 'The host let this page go.')),
  )
  // A host that never welcomes the page leaves nobody waiting on it.
  const waited = setTimeout(() => gone(new Error('The chat’s host did not answer.')), WELCOMED)
  try {
    const { workspace, slot } = await where
    return { sub, workspace, slot }
  } catch (error) {
    sub.close()
    throw error
  } finally {
    clearTimeout(waited)
  }
}

/** How long, in milliseconds, a chat's host made for it alone has to welcome the page. */
const WELCOMED = 30000

/** The run in front of a workspace's records: its number, and the records of it. */
export function current(state) {
  const run = state.standing.run
  const number = run && run.run ? run.run : Math.max(0, ...state.records.map((one) => one.run || 0))
  return { number, run, records: number ? state.records.filter((one) => one.run === number) : [] }
}

/**
 * What a session of a host's run in front was shown so far, oldest first: the context of each
 * of its `shown` records held, for a face mounted after they came.
 */
export function shownTo(where, session) {
  const { workspace, slot } = placed(where)
  const one = followed.get(`${workspace}\n${slot}`)
  if (!one || !session) return []
  return current(one.state)
    .records.filter((record) => record.type === 'shown' && String(record.session) === String(session))
    .map((record) => record.context || [])
}

function following(workspace, slot) {
  const state = { workspace, slot, connected: false, gone: '', me: '', epoch: '', standing: {}, records: [], figures: null }
  const listeners = new Set()
  let weights = []
  let weight = 0
  let pending = 0
  /** The attaching that is this one's now: what an earlier one says is said to nobody. */
  let opening = null
  /** What counts the output of each terminal nobody on the page draws, by the terminal. */
  const undrawn = new Map()
  const one = { state, listeners, opening: null, connect, close }

  /** Acknowledges a terminal's output nobody took, as often as one drawn is acknowledged. */
  function unread(mine, message) {
    const term = message.term
    if (message.type === 'term_exit') {
      undrawn.get(term)?.stop()
      undrawn.delete(term)
      return
    }
    if (!undrawn.has(term)) {
      const ack = (bytes) => mine.then((sub) => opening === mine && call('env.term.ack', { term, bytes, sub: sub.sub })).catch(() => {})
      undrawn.set(term, new Flow({ ack }))
    }
    const bytes = atob(message.data || '').length
    undrawn.get(term).got(bytes)
    undrawn.get(term).wrote(bytes)
  }

  /** The subscription is over: what it counted was counted for it alone. */
  function uncount() {
    for (const flow of undrawn.values()) flow.stop()
    undrawn.clear()
  }

  function tell() {
    if (pending) return
    pending = requestAnimationFrame(() => {
      pending = 0
      for (const told of [...listeners]) told(state)
    })
  }

  function hear(mine, message) {
    if (opening !== mine) return
    // Whoever hears it going wrong is not what the rest of the page follows the host by.
    let taken = false
    for (const fn of [...(heard.get(`${workspace}\n${slot}`) || [])]) {
      try {
        if (fn(message) === true) taken = true
      } catch (error) {
        console.error(error)
      }
    }
    const type = message.type
    if ((type === 'term' && !taken) || type === 'term_exit') unread(mine, message)
    if (type === 'welcome') {
      if (message.epoch !== state.epoch) {
        // Another life of the host's: everything is told again, from the top.
        Object.assign(state, { epoch: message.epoch, standing: {}, records: [], figures: null })
        weights = []
        weight = 0
      }
      Object.assign(state, { me: message.client, connected: true, gone: '' })
    } else if (type === 'live') state.connected = true
    else if (typeof message.seq === 'number') {
      // Context beside a question, an image's above all, weighs what it is written as.
      const weighs = String(message.text ?? '').length + (message.context ? JSON.stringify(message.context).length : 0) + FRAME
      state.records.push(message)
      // Context shown to a person goes to the face their session has open, where it has one:
      // one mounted later is handed it as it is mounted (`shownTo`).
      if (type === 'shown' && message.session) {
        import('./faces/host.js')
          .then(({ showFace }) => showFace(message.session, message.context || [], { where: { workspace, slot }, run: message.run }))
          .catch(() => {})
      }
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
    uncount()
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
    const mine = attach(
      { workspace, slot, figures: true },
      (message) => hear(mine, message),
      (why) => ended(mine, why),
    )
    opening = one.opening = mine
    mine.then(
      (sub) => {
        // Let go of before it was attached: nobody hears it.
        if (opening !== mine) sub.close()
      },
      (error) => {
        if (opening !== mine) return
        opening = one.opening = null
        state.connected = false
        state.gone = error.message
        tell()
      },
    )
  }

  function close() {
    const was = opening
    opening = one.opening = null
    uncount()
    state.connected = false
    was?.then((sub) => sub.close(), () => {})
  }

  return one
}

// Another daemon's workspaces are others: every subscription of the last goes, and nobody is told it.
onDaemon(() => {
  for (const one of followed.values()) {
    one.listeners.clear()
    one.close()
  }
  followed.clear()
})
