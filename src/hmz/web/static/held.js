// The runs held for each workspace, as subscriptions the views of the page share: per host of a
// workspace -- its own, which runs its flows one at a time, and each chat's beside it, by its
// slot -- the records of the run in front of it, how everything stands, and the figures the
// daemon works out -- the same the terminal interface draws (`epic.attach` with `figures`,
// Section 4.7 of protocol/daemon.md). A host is followed only while a view of it is open. What a
// view asks of a host's runs goes through `ask`, as a call to the epic on its subscription.
//
// A host is named by `where`: a workspace's path alone for the workspace's own, or
// `{workspace, slot}` for a chat's.

import { attach, call, onDaemon } from './api.js'

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

/** Whether a flow named to start is the built-in chat, however it was named. */
function chats(flow) {
  return typeof flow === 'string' && flow.replace(/[/#]+$/, '').split(/[/#:]/).pop() === 'chat'
}

/**
 * Asks one host's runs one thing: `start`, `say`, `answer`, `stop`, `force`, `afk`, … -- the call
 * `epic.<what>` on the subscription that follows the host, attached first where none does. A
 * chat started at a workspace alone is a new chat's, on a host of its own, which the answer
 * names; and an epic started with `scratch` is started in a directory made for it alone.
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
  const chat = !slot && chats(said.flow) ? 'chat:' : slot
  const sub = await attach({ ...(scratch ? { scratch: true } : { workspace }), slot: chat, replay: false }, () => {})
  try {
    const started = await call('epic.start', { ...said, remember: true, sub: sub.sub })
    // Followed a moment longer, as the view gone to next follows it.
    follow({ workspace: started.workspace, slot: started.slot }, () => {})()
    return started
  } finally {
    sub.close()
  }
}

/** The run in front of a workspace's records: its number, and the records of it. */
export function current(state) {
  const run = state.standing.run
  const number = run && run.run ? run.run : Math.max(0, ...state.records.map((one) => one.run || 0))
  return { number, run, records: number ? state.records.filter((one) => one.run === number) : [] }
}

function following(workspace, slot) {
  const state = { workspace, slot, connected: false, gone: '', me: '', epoch: '', standing: {}, records: [], figures: null }
  const listeners = new Set()
  let weights = []
  let weight = 0
  let pending = 0
  /** The attaching that is this one's now: what an earlier one says is said to nobody. */
  let opening = null
  const one = { state, listeners, opening: null, connect, close }

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
    for (const fn of [...(heard.get(`${workspace}\n${slot}`) || [])]) {
      try {
        fn(message)
      } catch (error) {
        console.error(error)
      }
    }
    const type = message.type
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
      const weighs = String(message.text ?? '').length + FRAME
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
