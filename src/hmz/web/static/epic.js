// What one epic is, whichever way it is read: the flows it ran, its agents and the people it
// had, each agent with the sessions it opened and each session with its turns over time, and
// who handed to whom -- off the records of the run going, as the terminal interface's monitor
// works them out, or off the epic written down and, once read, the logs it kept.
//
// A session is named as the run going names it, `<role>/<n>`, the n-th its role opened; a run
// written down names its sessions the same way, in the order they were opened, so an address
// to a session stays one as its run ends.

import { get, poll } from './api.js'
import { lane, lasting } from './dom.js'
import { current, follow } from './held.js'

/**
 * Follows one epic, or -- named "" -- the one going in a workspace: what it wrote down, read
 * again every so often, and the records of its workspace's runs while it is the one going
 * there -- and after, for as long as they are still of it. An epic written down long ago reaches
 * no runs at all.
 *
 * @param {string} name The epic, or "" for the one going.
 * @param {string} workspace Where to look for the one going, for an epic not named.
 * @param {(seen: {detail: object|null, error: Error|null, held: object|null, going: object|null, none: boolean, workspace: string}) => void} told
 * @returns {() => void} What stops following.
 */
export function watch(name, workspace, told) {
  const seen = { detail: null, error: null, held: null, going: null, none: false, workspace }
  let unfollow = null
  let following = false
  const tell = () => {
    if (seen.detail) seen.workspace = seen.detail.workspace
    // The runs of its workspace are followed once it is the one going there, or not named.
    if (!following && seen.workspace && (!name || (seen.detail && seen.detail.held))) {
      // Marked first: following tells what it holds at once, which comes back through here.
      following = true
      unfollow = follow(seen.workspace, (state) => {
        seen.held = state
        tell()
      })
      return
    }
    const run = seen.held ? going(seen.held) : null
    // The records of the epic going are this one's while it goes, and still once it has ended,
    // for as long as the records held are of it rather than of one started since.
    const ours = Boolean(seen.detail && run && (seen.detail.held || same(seen.detail, run.started)))
    seen.going = !name || ours ? run : null
    told(seen)
  }
  let stop
  if (name) {
    stop = poll(`/api/runs/${encodeURIComponent(name)}`, 4000, (data, error) => {
      seen.error = error
      if (data) seen.detail = data
      tell()
    })
  } else {
    // The epic going has its record as soon as it starts; it is named once the list says which.
    stop = poll(`/api/runs?status=running&limit=1&workspace=${encodeURIComponent(workspace)}`, 2000, (data) => {
      const one = data && data.runs[0]
      seen.none = Boolean(data) && !one
      if (one && (!seen.detail || seen.detail.name !== one.name)) {
        get(`/api/runs/${encodeURIComponent(one.name)}`).then((found) => {
          seen.detail = found
          tell()
        }, () => {})
      }
      tell()
    })
  }
  return () => {
    stop()
    if (unfollow) unfollow()
  }
}

/** Whether the start the records say is the start an epic wrote down, as the server matches them. */
function same(detail, started) {
  return started.flow === detail.flow && started.task === detail.task && Math.abs((started.at || 0) - Date.parse(detail.began) / 1000) <= SAME
}

/** How far apart, in seconds, the host's start and the epic's own may be and be one start. */
const SAME = 120

/** The run in front of the held records, where they hold one, and how it stands. */
export function going(held) {
  const { number, run, records } = current(held)
  const started = records.find((one) => one.type === 'started') || (run && run.state !== 'idle' ? run : null)
  if (!started) return null
  const ended = records.findLast((one) => one.type === 'ended') || null
  const state = run && run.run === number ? run.state : 'idle'
  const offset = started.at && started.began !== undefined ? started.at - started.began : null
  return { number, started, ended, state, live: !ended && state !== 'idle', records, offset }
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

/** The last line read of each session of an epic, by epic and then session, in this tab. */
const reads = new Map()

/** Marks a session of an epic read as far as its records go now. */
export function read(epic, key, records) {
  const last = records.reduce((most, one) => (one.type === 'event' && one.session === key ? Math.max(most, one.seq) : most), 0)
  if (!reads.has(epic)) reads.set(epic, new Map())
  reads.get(epic).set(key, last)
}

/** Whether a session of an epic said anything since it was last read here. */
function unread(epic, key, records) {
  const was = (reads.get(epic) && reads.get(epic).get(key)) || 0
  return records.some((one) => one.type === 'event' && one.session === key && one.kind === 'text' && one.seq > was)
}

/** The sessions of a run written down, each named as the run going named it. */
export function sessionsOf(detail) {
  const counted = {}
  return detail.sessions.map((one) => {
    counted[one.role] = (counted[one.role] || 0) + 1
    return { ...one, key: `${one.role}/${counted[one.role]}`, traced: `${one.backend}:${one.ident}` }
  })
}

/** What each agent of the run going is, and the rest of what its graph is drawn from. */
export function live(held, run, detail) {
  const epic = detail ? detail.name : ''
  const { started, records, offset } = run
  const figures = held.figures
  const sessions = turnsOf(records, offset)
  const people = started.outworlders || []
  const roles = [...(started.roles || Object.keys(started.agents || {}))]
  for (const one of sessions) if (one.role && !roles.includes(one.role)) roles.push(one.role)
  for (const one of people) if (!roles.includes(one)) roles.push(one)
  const working = new Set(((figures && figures.sessions) || []).filter((one) => one.working).map((one) => one.name))
  const now = Date.now() / 1000
  const starts = sessions.flatMap((one) => one.turns.map((turn) => turn.start))
  const from = started.at || Math.min(now, ...starts)
  const last = records.findLast((one) => one.at)
  const to = run.live ? now : Math.max(from + 1, last ? last.at : now, ...sessions.flatMap((one) => one.turns.map((turn) => turn.end || 0)))
  const specs = Object.fromEntries(((detail && detail.agents) || []).map((one) => [one.role, one.runs]))
  const agents = roles.map((role, index) => {
    const figure = figures && figures.agents.find((one) => one.name === role)
    const person = people.includes(role)
    const given = started.agents && typeof started.agents[role] === 'string' ? started.agents[role] : ''
    return {
      role,
      person,
      color: lane(person ? -1 : index),
      spec: person ? 'a person' : specs[role] || given,
      working: Boolean(figure && figure.working),
      status: figure ? (figure.working ? `working ${figure.lasting}` : `idle ${figure.lasting}`) : person ? '' : 'not started',
      turns: figure ? figure.turns : sessions.filter((one) => one.role === role).reduce((sum, one) => sum + one.turns.length, 0),
      tokens: figure ? figure.tokens : '',
      under: figure ? figure.under : [],
      sessions: sessions
        .filter((one) => one.role === role)
        .map((one) => ({ key: one.key, about: [one.cli, one.model].filter(Boolean).join(' · '), working: working.has(one.key) || one.turns.some((turn) => turn.end === null), turns: one.turns, unread: unread(epic, one.key, records) })),
    }
  })
  return {
    flow: started.flow,
    frames: [{ flow: started.flow, roles }],
    agents,
    handovers: ((figures && figures.handovers) || []).filter((one) => one.from !== one.to),
    latest: figures && figures.latest,
    from,
    to,
    live: run.live,
  }
}

/** What each agent of a run written down was, from its epic and -- once read -- its logs. */
export function written(detail, traced) {
  const sessions = sessionsOf(detail)
  const roles = [...new Set([...detail.agents.map((one) => one.role), ...sessions.map((one) => one.role)])]
  const turns = new Map((traced || []).map((one) => [one.key, one.actions.filter((action) => action.category === 'turn').map((action) => ({ start: action.start, end: action.start + action.seconds }))]))
  const specs = Object.fromEntries(detail.agents.map((one) => [one.role, one.runs]))
  // The flows it ran, the one it was started with first: an agent is drawn in the flow its
  // first session was opened in.
  const frames = [{ flow: detail.flow, roles: [] }]
  for (const role of roles) {
    const first = sessions.find((one) => one.role === role)
    const flow = first && first.flow ? first.flow : detail.flow
    let frame = frames.find((one) => one.flow === flow)
    if (!frame) frames.push((frame = { flow, roles: [] }))
    frame.roles.push(role)
  }
  const agents = roles.map((role, index) => {
    const mine = sessions.filter((one) => one.role === role)
    const count = mine.reduce((sum, one) => sum + (turns.get(one.traced) || []).length, 0)
    return {
      role,
      person: false,
      color: lane(index),
      spec: specs[role] || '',
      working: false,
      status: traced ? `${count} turn${count === 1 ? '' : 's'}` : `${mine.length} session${mine.length === 1 ? '' : 's'}`,
      turns: traced ? count : null,
      tokens: '',
      under: [],
      sessions: mine.map((one) => ({ key: one.key, about: [one.backend, one.provider].filter(Boolean).join('@'), working: false, turns: turns.get(one.traced) || [] })),
    }
  })
  const all = [...turns.values()].flat()
  const began = Date.parse(detail.began) / 1000
  const from = all.length ? Math.min(...all.map((turn) => turn.start)) : began
  const to = all.length ? Math.max(...all.map((turn) => turn.end)) : detail.ended ? Date.parse(detail.ended) / 1000 : began + 1
  return { flow: detail.flow, frames: frames.filter((one) => one.roles.length || one.flow === detail.flow), agents, handovers: traced ? handed(sessions, traced) : [], latest: null, from, to, live: false }
}

/** Who handed to whom in a run written down: each turn, in the order taken, after another role's. */
function handed(sessions, traced) {
  const roleOf = Object.fromEntries(sessions.map((one) => [one.traced, one.role]))
  const taken = traced
    .flatMap((one) => one.actions.filter((action) => action.category === 'turn').map((action) => ({ start: action.start, role: roleOf[one.key] || one.agent || one.key })))
    .sort((a, b) => a.start - b.start)
  const counts = new Map()
  for (let index = 1; index < taken.length; index++) {
    const [from, to] = [taken[index - 1].role, taken[index].role]
    if (from === to) continue
    counts.set(`${from}\n${to}`, (counts.get(`${from}\n${to}`) || 0) + 1)
  }
  return [...counts].map(([pair, count]) => {
    const [from, to] = pair.split('\n')
    return { from, to, count }
  })
}

/** How long a run took, or has been going. */
export function took(detail, run) {
  if (run && run.started.at) {
    const end = run.ended ? run.ended.at ?? (run.offset !== null ? run.ended.mono + run.offset : null) : Date.now() / 1000
    if (end) return lasting(end - run.started.at)
  }
  if (detail && detail.ended) return lasting((Date.parse(detail.ended) - Date.parse(detail.began)) / 1000)
  return ''
}
