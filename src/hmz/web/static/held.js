// The runs held for each workspace, as streams the views of the page share: per workspace, the
// records of the run in front of it, how everything stands, and the figures the server works
// out -- the same the terminal interface draws. A workspace is followed only while a view of it
// is open. What a view asks of a workspace's runs goes through `ask`.

import { post } from './api.js'

/** The most records kept per workspace, and about how many bytes of them, as the server keeps. */
const KEPT = 20000
const WEIGHED = 32 * 1024 * 1024

/** What a record weighs besides what it says, as the server weighs one. */
const FRAME = 256

/** How long a tab nobody looks at keeps its streams, in milliseconds. */
const RESTS = 30000

/** Every workspace followed, by its path. */
const followed = new Map()

/**
 * Follows one workspace's runs: told the state now and again whenever it changes, until stopped.
 *
 * @param {string} workspace Its path.
 * @param {(state: object) => void} told
 * @returns {() => void} What stops following.
 */
export function follow(workspace, told) {
  let one = followed.get(workspace)
  if (!one) followed.set(workspace, (one = following(workspace)))
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
        followed.delete(workspace)
      }, 5000)
    }
  }
}

/** Asks one workspace's runs one thing: `start`, `say`, `answer`, `stop`, `force`, `afk`, … */
export function ask(workspace, what, body = {}) {
  return post(`/api/held/${what}`, { ...body, workspace })
}

/** The run in front of a workspace's records: its number, and the records of it. */
export function current(state) {
  const run = state.standing.run
  const number = run && run.run ? run.run : Math.max(0, ...state.records.map((one) => one.run || 0))
  return { number, run, records: number ? state.records.filter((one) => one.run === number) : [] }
}

function following(workspace) {
  const state = { workspace, connected: false, gone: '', me: '', epoch: '', standing: {}, records: [], figures: null }
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
    if (lastId && state.epoch) query.set('last', lastId)
    const mine = new EventSource(`/api/held/stream?${query}`)
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
      // The browser reaches for the stream again by itself, from the last record it heard.
      state.connected = false
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
