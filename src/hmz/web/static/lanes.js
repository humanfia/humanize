// A run drawn over time: a lane for each session, a capsule for each turn it took, and -- while
// the run goes -- a line where now is. The lanes are coloured as the agents are, a turn still
// open is ringed in the colour of what is happening now, and a turn is a button: picking it
// shows that session's transcript.

import { h, lasting, when } from './dom.js'

/**
 * @param {object} drawn
 * @param {{key: string, label: string, color: string, turns: {start: number, end: number|null}[]}[]} drawn.rows
 * @param {number} drawn.from When the run began, in seconds since the epoch.
 * @param {number} drawn.to When it ended, or now.
 * @param {boolean} drawn.live Whether it is going, which draws where now is.
 * @param {string} drawn.picked The lane being read, if any.
 * @param {(key: string) => void} drawn.pick What picking a lane or a turn does.
 */
export function lanes({ rows, from, to, live, picked, pick }) {
  const span = Math.max(1, to - from)
  const at = (moment) => `${Math.min(100, Math.max(0, ((moment - from) / span) * 100))}%`
  const grid = h('div', { class: 'lanes', role: 'group', 'aria-label': 'Each session, and the turns it took over time', 'data-hmz': 'lanes' })
  for (const row of rows) {
    const name = h(
      'button',
      { class: 'name', type: 'button', style: { '--lane': row.color }, 'aria-pressed': String(picked === row.key), title: row.label },
      h('i', { 'aria-hidden': 'true' }),
      row.label,
    )
    name.addEventListener('click', () => pick(row.key))
    const track = h('div', { class: 'track', style: { '--lane': row.color } })
    row.turns.forEach((turn, index) => {
      const end = turn.end ?? to
      const took = Math.max(0, end - turn.start)
      const said = `${row.label}, turn ${index + 1}: ${when(turn.start)}, ${turn.end === null ? 'still going' : lasting(took)}`
      const capsule = h('button', {
        class: ['turn', turn.end === null && 'open'],
        type: 'button',
        title: said,
        'aria-label': said,
        style: { left: at(turn.start), width: `max(8px, ${(took / span) * 100}%)` },
      })
      capsule.addEventListener('click', () => pick(row.key))
      track.append(capsule)
    })
    if (live) track.append(h('span', { class: 'now', style: { left: at(to) }, 'aria-hidden': 'true' }))
    grid.append(name, track)
  }
  grid.append(h('div', { class: 'axis', 'aria-hidden': 'true' }, h('span', {}, '0s'), h('span', {}, lasting(span / 2)), h('span', {}, lasting(span))))
  return grid
}

/** The turns of each session of a run going, read off the records the runs told. */
export function turnsOf(records, offset) {
  const held = new Map()
  for (const record of records) {
    if (record.type === 'opened' && !record.person) held.set(record.key, { key: record.key, role: record.role, cli: record.cli, model: record.model, turns: [] })
    if (record.type !== 'event' || !record.session) continue
    if (!held.has(record.session)) held.set(record.session, { key: record.session, role: record.session.split('/')[0], cli: record.cli, model: record.model, turns: [] })
    const one = held.get(record.session)
    if (record.kind === 'begins') one.turns.push({ start: record.at, end: null })
    else if (record.kind === 'ends') {
      const open = one.turns.findLast((turn) => turn.end === null)
      if (open) open.end = record.at
    }
  }
  // A run that ended closes what its records left open, at the moment it ended.
  const ended = records.findLast((record) => record.type === 'ended')
  if (ended && offset !== null) {
    for (const one of held.values()) for (const turn of one.turns) if (turn.end === null) turn.end = ended.mono + offset
  }
  return [...held.values()]
}

/** The turns of each session of a run written down, read off its trace. */
export function turnsOfTrace(sessions) {
  return sessions.map((one) => ({
    key: one.key,
    turns: one.actions.filter((action) => action.category === 'turn').map((action) => ({ start: action.start, end: action.start + action.seconds })),
  }))
}
