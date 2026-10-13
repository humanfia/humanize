// The runs held for each workspace, as streams the views of the page share: per host of a
// workspace -- its own, which runs its flows one at a time, and each chat's beside it, by its
// slot -- the records of the run in front of it, how everything stands, and the figures the
// server works out -- the same the terminal interface draws. A host is followed only while a
// view of it is open. What a view asks of a host's runs goes through `ask`.
//
// A host is named by `where`: a workspace's path alone for the workspace's own, or
// `{workspace, slot}` for a chat's.

import { onDaemon, post, scoped } from './api.js'

/** The most records kept per workspace, and about how many bytes of them, as the server keeps. */
const KEPT = 20000
const WEIGHED = 32 * 1024 * 1024

/** What a record weighs besides what it says, as the server weighs one. */
const FRAME = 256

/** How long a tab nobody looks at keeps its streams, in milliseconds. */
const RESTS = 30000

/** Every host followed, by its workspace's path and its slot. */
const followed = new Map()

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
  if (!one.source) one.connect()
  told(one.state)
  return () => {
    one.listeners.delete(told)
    // Nobody reads it any more: the stream goes after a moment, in case a view comes back.
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
 * Asks one host's runs one thing: `start`, `say`, `answer`, `stop`, `force`, `afk`, … A chat
 * started at a workspace alone is a new chat's, on a host of its own, which the answer names.
 */
export function ask(where, what, body = {}) {
  const { workspace, slot } = placed(where)
  return post(`/api/held/${what}`, { ...body, workspace, ...(slot ? { slot } : {}) })
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
  /** The id of the last record heard, which a stream opened again picks up after. */
  let lastId = ''
  const one = { state, listeners, source: null, connect, close }

  function tell() {
    if (pending) return
    pending = requestAnimationFrame(() => {
      pending = 0
      for (const told of [...listeners]) told(state)
    })
  }

  function connect() {
    const query = new URLSearchParams({ workspace })
    if (slot) query.set('slot', slot)
    if (lastId && state.epoch) query.set('last', lastId)
    const mine = new EventSource(scoped(`/api/held/stream?${query}`))
    one.source = mine
    // A stream let go of, or replaced, says nothing more to the page.
    const on = (name, handle) => mine.addEventListener(name, (event) => one.source === mine && handle(event))
    on('hello', (event) => {
      const said = JSON.parse(event.data)
      if (said.epoch !== state.epoch) {
        // Another link's records: everything is told again, from the top.
        Object.assign(state, { epoch: said.epoch, standing: {}, records: [], figures: null })
        weights = []
        weight = 0
        lastId = ''
      }
      Object.assign(state, { me: said.me, connected: true, gone: '' })
      tell()
    })
    on('record', (event) => {
      lastId = event.lastEventId || lastId
      const record = JSON.parse(event.data)
      const weighs = String(record.text ?? '').length + FRAME
      state.records.push(record)
      weights.push(weighs)
      weight += weighs
      let dropped = 0
      while (state.records.length - dropped > KEPT || (weight > WEIGHED && state.records.length - dropped > 1)) weight -= weights[dropped++]
      if (dropped) {
        state.records.splice(0, dropped)
        weights.splice(0, dropped)
      }
      tell()
    })
    on('standing', (event) => {
      const said = JSON.parse(event.data)
      state.standing = { ...state.standing, [said.type]: said }
      tell()
    })
    on('figures', (event) => {
      state.figures = JSON.parse(event.data)
      tell()
    })
    on('gone', (event) => {
      state.gone = JSON.parse(event.data).why || 'The host let this page go.'
      state.connected = false
      // A chat's host goes as it folds away, and is not reached again: it is carried on anew.
      if (slot) close()
      tell()
    })
    on('again', () => {
      mine.close()
      one.source = null
      state.epoch = ''
      lastId = ''
      setTimeout(() => !one.source && listeners.size && connect(), 500)
    })
    on('error', () => {
      // The browser reaches for the stream again by itself, from the last record it heard --
      // but for one refused outright: a chat's host that has gone, its chat folded away.
      state.connected = false
      if (slot && mine.readyState === EventSource.CLOSED) {
        state.gone = state.gone || 'This chat has folded away.'
        close()
      }
      tell()
    })
  }

  function close() {
    if (one.source) one.source.close()
    one.source = null
    state.connected = false
  }

  return one
}

// Another daemon's workspaces are others: every stream of the last goes, and nobody is told it.
onDaemon(() => {
  for (const one of followed.values()) {
    one.listeners.clear()
    one.close()
  }
  followed.clear()
})

// A browser holds only so many connections to one server: a tab nobody looks at lets its
// streams go after a while, and picks each up from the last record it heard once looked at.
let resting = 0
document.addEventListener('visibilitychange', () => {
  clearTimeout(resting)
  if (document.hidden) {
    resting = setTimeout(() => {
      for (const one of followed.values()) one.close()
    }, RESTS)
  } else {
    for (const one of followed.values()) if (!one.source && one.listeners.size) one.connect()
  }
})
