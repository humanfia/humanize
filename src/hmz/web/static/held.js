// The runs held for this directory, as one stream every view of the page shares: the records
// of the run in front of it, how everything stands, and the figures the server works out --
// the same the terminal interface draws. What a view asks of the runs goes through `ask`.

import { post } from './api.js'

/** The most records kept, and about how many bytes of them, as the server keeps. */
const KEPT = 20000
const WEIGHED = 32 * 1024 * 1024

/** What a record weighs besides what it says, as the server weighs one. */
const FRAME = 256

/** What each record kept weighs, in the order kept, and all of them together. */
let weights = []
let weight = 0

const state = {
  connected: false,
  gone: '',
  me: '',
  epoch: '',
  standing: {},
  records: [],
  figures: null,
}

const listeners = new Set()
let source = null
let pending = 0
/** The id of the last record heard, which a stream opened again picks up after. */
let lastId = ''
let resting = 0

/** How long a tab nobody looks at keeps its stream, in milliseconds. */
const RESTS = 30000

/**
 * Follows the runs: told the state now and again whenever it changes, until stopped.
 *
 * @param {(state: object) => void} told
 * @returns {() => void} What stops following.
 */
export function follow(told) {
  listeners.add(told)
  if (!source) connect()
  told(state)
  return () => listeners.delete(told)
}

/** Asks the runs one thing: `start`, `say`, `answer`, `stop`, `force`, `afk`, `claim`, … */
export function ask(what, body = {}) {
  return post(`/api/held/${what}`, body)
}

function connect() {
  const mine = new EventSource(lastId && state.epoch ? `/api/held/stream?last=${encodeURIComponent(lastId)}` : '/api/held/stream')
  source = mine
  // A stream let go of, or replaced, says nothing more to the page.
  const on = (name, handle) => mine.addEventListener(name, (event) => source === mine && handle(event))
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
    state.gone = JSON.parse(event.data).why || 'The runs let this page go.'
    state.connected = false
    tell()
  })
  on('again', () => {
    mine.close()
    source = null
    state.epoch = ''
    lastId = ''
    setTimeout(() => !source && connect(), 500)
  })
  on('error', () => {
    // The browser reaches for the stream again by itself, from the last record it heard.
    state.connected = false
    tell()
  })
}

// A browser holds only so many connections to one server: a tab nobody looks at lets its
// stream go after a while, and picks it up from the last record it heard once looked at again.
document.addEventListener('visibilitychange', () => {
  clearTimeout(resting)
  if (document.hidden) {
    resting = setTimeout(() => {
      if (!source) return
      source.close()
      source = null
      state.connected = false
    }, RESTS)
  } else if (!source && listeners.size) connect()
})

/** Tells every listener, once a frame however many things changed in it. */
function tell() {
  if (pending) return
  pending = requestAnimationFrame(() => {
    pending = 0
    for (const told of [...listeners]) told(state)
  })
}

/** The run in front of the page: its number, and the records of it. */
export function current(state) {
  const run = state.standing.run
  const number = run && run.run ? run.run : Math.max(0, ...state.records.map((one) => one.run || 0))
  return { number, run, records: number ? state.records.filter((one) => one.run === number) : [] }
}
