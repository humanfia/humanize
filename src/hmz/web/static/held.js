// The runs held for this directory, as one stream every view of the page shares: the records
// of the run in front of it, how everything stands, and the figures the server works out --
// the same the terminal interface draws. What a view asks of the runs goes through `ask`.

import { post } from './api.js'

/** The most records kept, as the server keeps. */
const KEPT = 20000

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
  source = new EventSource('/api/held/stream')
  source.addEventListener('hello', (event) => {
    const said = JSON.parse(event.data)
    if (said.epoch !== state.epoch) {
      // Another link's records: everything is told again, from the top.
      Object.assign(state, { epoch: said.epoch, standing: {}, records: [], figures: null })
    }
    Object.assign(state, { me: said.me, connected: true, gone: '' })
    tell()
  })
  source.addEventListener('record', (event) => {
    state.records.push(JSON.parse(event.data))
    if (state.records.length > KEPT) state.records.splice(0, state.records.length - KEPT)
    tell()
  })
  source.addEventListener('standing', (event) => {
    const said = JSON.parse(event.data)
    state.standing = { ...state.standing, [said.type]: said }
    tell()
  })
  source.addEventListener('figures', (event) => {
    state.figures = JSON.parse(event.data)
    tell()
  })
  source.addEventListener('gone', (event) => {
    state.gone = JSON.parse(event.data).why || 'The runs let this page go.'
    state.connected = false
    tell()
  })
  source.addEventListener('again', () => {
    source.close()
    source = null
    state.epoch = ''
    setTimeout(connect, 500)
  })
  source.addEventListener('error', () => {
    // The browser reaches for the stream again by itself, from the last record it heard.
    state.connected = false
    tell()
  })
}

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
