// One run: the one going, as it happens, or one written down. What it is, how it is going or
// went, its lanes of turns, what each session said, and -- while it goes -- what the page can
// ask of it. `#/live` is whichever run is going; `#/runs/<name>` is one epic, live where it is
// the one going.

import { asides, board, outworlders, questions, saying } from '../acting.js'
import { get, poll } from '../api.js'
import { ago, badge, confirming, copier, empty, fill, h, lane, lasting, problem, secondsOf, when } from '../dom.js'
import { ask, current, follow } from '../held.js'
import { lanes, turnsOf, turnsOfTrace } from '../lanes.js'
import { saidTraced, sayer } from '../transcript.js'

export function mount(root, { parts }) {
  const named = parts[0] === 'live' ? '' : parts[1]
  const regions = {
    head: h('div', { class: 'head' }),
    tiles: h('section', { class: 'panel', 'aria-label': 'Figures' }),
    lanes: h('section', { class: 'panel', 'aria-label': 'Turns over time' }),
    transcript: h('section', { class: 'panel', 'aria-label': 'Transcript' }),
    side: h('div', { class: 'nodes' }),
  }
  fill(
    root,
    regions.head,
    regions.tiles,
    h('div', { class: 'grid wide' }, h('div', {}, regions.lanes, regions.transcript), regions.side),
  )

  let detail = null
  let detailError = null
  const btw = asides()
  let held = null
  let picked = ''
  let traced = null
  let tracing = false
  const drawn = {}

  const live = () => !named || Boolean(detail && detail.held)

  /** Draws one region again, where what it is drawn from has changed. */
  function region(name, from, draw) {
    const key = JSON.stringify(from)
    if (drawn[name] === key) return
    drawn[name] = key
    draw()
  }

  function draw() {
    if (named && !detail) {
      fill(regions.head, detailError ? problem(detailError) : h('p', { class: 'loading', role: 'status' }, 'Reading the run…'))
      return
    }
    if (live()) drawLive()
    else drawWritten()
  }

  // ------------------------------------------------------------------ the run going

  function drawLive() {
    if (!held) return
    const { number, run, records } = current(held)
    const started = records.find((one) => one.type === 'started') || (run && run.state !== 'idle' ? run : null)
    if (!started && !named) {
      region('head', ['none'], () =>
        fill(
          regions.head,
          empty('No run is going here.', ' Start one, or open a run written down.', h('a', { class: 'btn primary', href: '#/start' }, 'Start a run'), h('a', { class: 'btn', href: '#/runs' }, 'Every run')),
        ),
      )
      for (const one of ['tiles', 'lanes', 'transcript', 'side']) regions[one].hidden = true
      return
    }
    for (const one of ['tiles', 'lanes', 'transcript', 'side']) regions[one].hidden = false
    const offset = started ? started.at - started.began : null
    const state = run && run.run === number ? run.state : 'idle'
    const ended = records.findLast((one) => one.type === 'ended')
    const going = !ended && state !== 'idle'
    region('head', [number, state, Boolean(ended), ended && ended.how, detail && detail.name, started && started.task], () => drawLiveHead(started, state, ended, going))
    drawLiveTiles(started, ended, going)
    drawLiveLanes(records, started, offset, going)
    drawLiveTranscript(records, number)
    drawLiveSide(started, records, going)
  }

  function drawLiveHead(started, state, ended, going) {
    const actions = []
    if (going && state === 'running') {
      actions.push(confirming({ label: 'Stop', ask: 'Stop this run?', yes: 'Stop it', no: 'Keep running', act: () => ask('stop') }))
    } else if (going && state === 'stopping') {
      actions.push(confirming({ label: 'Force', ask: 'Close every session under its turn?', yes: 'Force it', no: 'Let it unwind', act: () => ask('force') }))
    }
    if (detail && !named) actions.push(h('a', { class: 'btn quiet', href: `#/runs/${encodeURIComponent(detail.name)}` }, 'Its epic'))
    actions.push(copier('Copy link', () => location.href))
    fill(
      regions.head,
      h(
        'div',
        { class: 'task' },
        h('div', { class: 'kicker' }, going ? 'live run' : 'the last run here'),
        h('h1', {}, started ? started.flow : detail.flow, ' ', badge(ended ? ended.how : state === 'stopping' ? 'stopping' : 'running')),
        started && started.at ? h('p', { class: 'lede', title: when(started.at) }, `began ${ago(started.at)}`, started.by ? ` · by ${started.by}` : '') : null,
        h('p', { class: 'lede' }, started ? started.task : detail.task),
      ),
      h('div', { class: 'actions' }, actions),
    )
  }

  function drawLiveTiles(started, ended, going) {
    const figures = held.figures
    const usage = held.standing.usage
    const lines = figures && figures.tally && figures.tally.length ? figures.tally : []
    region('tiles', [figures && figures.lasting, lines, usage, going, ended && ended.how], () => {
      const elapsed = figures ? figures.lasting : started && started.at ? lasting(Date.now() / 1000 - started.at) : '—'
      fill(
        regions.tiles,
        h(
          'div',
          { class: 'tiles' },
          tile('time', elapsed, going ? 'and counting' : 'all told'),
          spentTile(lines[1] || ''),
          tile('tokens', lines[0] ? '' : '—', lines[0] || ''),
          budget(usage),
        ),
      )
    })
  }

  function drawLiveLanes(records, started, offset, going) {
    const sessions = turnsOf(records, offset)
    const roles = rolesOf(started, sessions)
    const now = Date.now() / 1000
    const from = started && started.at ? started.at : Math.min(now, ...sessions.flatMap((one) => one.turns.map((turn) => turn.start)))
    const last = records.findLast((one) => one.at)
    const to = going ? now : Math.max(from + 1, last ? last.at : now, ...sessions.flatMap((one) => one.turns.map((turn) => turn.end || 0)))
    region('lanes', [sessions, picked, going ? Math.floor(now) : 0], () => {
      const rows = sessions.map((one) => ({
        key: one.key,
        label: `${one.key}${one.model ? ` · ${one.model}` : ''}`,
        color: lane(roles.indexOf(one.role)),
        turns: one.turns,
      }))
      fill(
        regions.lanes,
        h('header', {}, h('h2', {}, 'Turns'), h('span', { class: 'kicker' }, `${rows.length} session${rows.length === 1 ? '' : 's'}`)),
        rows.length ? lanes({ rows, from, to, live: going, picked, pick }) : h('p', { class: 'dim' }, 'No session has opened yet.'),
      )
    })
  }

  let saying_ = null
  let saidUpTo = -1
  let saidRun = 0
  let saidKey = null
  let box = null

  function drawLiveTranscript(records, number) {
    const keys = [...new Set(records.filter((one) => one.type === 'opened' && !one.person).map((one) => one.key))]
    region('transcript-tabs', [keys, picked], () => {
      box = h('div', { class: 'transcript', 'data-hmz': 'transcript', role: 'log', 'aria-live': 'off' })
      fill(regions.transcript, h('header', {}, h('h2', {}, 'Transcript')), tabs(['', ...keys], picked), box)
      saidKey = null
    })
    if (saidKey !== picked || saidRun !== number) {
      saying_ = sayer(picked)
      saidUpTo = -1
      saidKey = picked
      saidRun = number
      fill(box)
    }
    const stuck = box.scrollHeight - box.scrollTop - box.clientHeight < 40
    let added = false
    for (const record of records) {
      if (record.seq <= saidUpTo) continue
      saidUpTo = record.seq
      for (const line of saying_(record)) {
        box.append(line)
        added = true
      }
    }
    if (added && stuck) box.scrollTop = box.scrollHeight
    if (!box.childElementCount) box.append(h('p', { class: 'dim' }, 'Nothing has been said yet.'))
    else box.querySelector(':scope > p.dim')?.remove()
  }

  function drawLiveSide(started, records, going) {
    const standing = held.standing
    const figures = held.figures
    const pending = (standing.pending && standing.pending.pending) || []
    const sessions = (standing.sessions && standing.sessions.open) || []
    const working = (standing.sessions && standing.sessions.working) || []
    const roles = started ? started.roles || Object.keys(started.agents || {}) : []
    const people = started ? started.outworlders || [] : []
    const items = standing.board ? standing.board.items : null
    const calls = (standing.calls && standing.calls.calls) || []
    const offset = started && started.at ? started.at - started.began : null
    region('side', [going, figures && figures.agents, figures && figures.sessions, figures && figures.handovers, figures && figures.latest, pending, sessions, working, roles, people, standing.claims, standing.away, items, calls, held.me], () => {
      const order = rolesOf(started, turnsOf(records, null))
      btw.sessions([...new Set(records.filter((one) => one.type === 'opened' && !one.person).map((one) => one.key))])
      // What a page asks of a run is asked of the one going: once it ends, there is only what it did.
      fill(
        regions.side,
        going && pending.length ? panel('Waiting for you', questions(pending, held.me, standing.clients && standing.clients.clients)) : null,
        panel('Agents', agentsOf(figures, order)),
        going ? panel('Say a line', saying(roles, sessions, working, people)) : null,
        panel('Ask beside it', h('p', { class: 'dim' }, 'A side question goes to a side conversation, never to the run.'), btw.node),
        going && people.length ? panel('People', outworlders(people, { claims: (standing.claims && standing.claims.claims) || {}, away: standing.away, me: held.me, clients: standing.clients && standing.clients.clients })) : null,
        going && items ? panel('Board', board(items)) : null,
        calls.length ? panel('Flows going', h('ul', { class: 'tree' }, calls.map((call) => h('li', { style: { marginLeft: `${call.depth * 14}px` } }, h('b', {}, call.name), ' ', h('span', { class: 'dim' }, offset === null ? '' : lasting(Date.now() / 1000 - (call.since + offset))))))) : null,
      )
    })
  }

  function agentsOf(figures, order) {
    if (!figures || !figures.agents.length) return h('p', { class: 'dim' }, 'No agent has taken a turn yet.')
    const handed = figures.handovers.length
      ? h(
          'ul',
          { class: 'handovers' },
          figures.handovers.map((one) =>
            h('li', { class: figures.latest && figures.latest[0] === one.from && figures.latest[1] === one.to ? 'latest' : '' }, `${one.from} → ${one.to} ×${one.count}`),
          ),
        )
      : null
    return [
      figures.agents.map((agent) => {
        const index = order.indexOf(agent.name)
        const sessions = figures.sessions.filter((one) => one.name.startsWith(`${agent.name}/`))
        return h(
          'div',
          { class: ['node', agent.working && 'working'], style: { '--lane': lane(index) }, 'data-hmz': 'agent' },
          h('div', { class: 'top' }, agent.working ? '●' : '○', ' ', agent.name, h('span', { class: 'clock' }, agent.working ? agent.lasting : `idle ${agent.lasting}`)),
          h('div', { class: 'meta' }, `${agent.turns} turn${agent.turns === 1 ? '' : 's'} · ${agent.tokens} tokens`),
          sessions.length > 1 ? h('ul', {}, sessions.map((one) => h('li', {}, `${one.name} · ${one.turns} turns${one.working ? ' · working' : ''}`))) : null,
          agent.under.length
            ? h('ul', {}, agent.under.map((one) => h('li', {}, `${one.working ? '◆' : '◇'} ${one.about}`)))
            : null,
        )
      }),
      handed,
    ]
  }

  // ------------------------------------------------------------------ a run written down

  function drawWritten() {
    for (const one of ['tiles', 'lanes', 'transcript', 'side']) regions[one].hidden = false
    region('head', [detail], () => {
      const actions = []
      if (detail.picks_up) actions.push(h('a', { class: 'btn', href: `#/start?flow=${encodeURIComponent(detail.flow)}&resume=${encodeURIComponent(detail.name)}` }, 'Pick it up'))
      actions.push(h('a', { class: 'btn quiet', href: `/api/runs/${encodeURIComponent(detail.name)}/bundle`, download: '' }, 'Export'))
      actions.push(copier('Copy link', () => location.href))
      fill(
        regions.head,
        h(
          'div',
          { class: 'task' },
          h('div', { class: 'kicker name' }, detail.name),
          h('h1', {}, detail.flow, ' ', badge(detail.how)),
          h('p', { class: 'lede', title: when(detail.began) }, `began ${ago(detail.began)}`, detail.ended ? ` · ended ${ago(detail.ended)}` : ''),
          detail.task.length > 400 ? h('details', {}, h('summary', {}, detail.task.slice(0, 240), '…'), h('pre', { class: 'block' }, detail.task)) : h('p', { class: 'lede' }, detail.task),
        ),
        h('div', { class: 'actions' }, actions),
      )
    })
    region('tiles', [detail.spent, detail.ended, detail.sessions.length, detail.agents.length], () => {
      const spent = detail.spent
      fill(
        regions.tiles,
        h(
          'div',
          { class: 'tiles' },
          tile('spent', spent ? spent.money || '—' : '—', spent ? '' : 'nothing said'),
          tile('output tokens', spent ? spent.tokens : '—', ''),
          tile('took', detail.ended ? lasting((Date.parse(detail.ended) - Date.parse(detail.began)) / 1000) : '—', spent && spent.worked ? `${spent.worked} of it working` : ''),
          tile('sessions', String(detail.sessions.length), `${detail.agents.length} agent role${detail.agents.length === 1 ? '' : 's'}`),
        ),
      )
    })
    region('lanes', [Boolean(traced), tracing, picked], drawWrittenLanes)
    region('transcript', [Boolean(traced), tracing, picked], drawWrittenTranscript)
    region('side', [detail.agents, detail.calls, detail.sessions, detail.envs, detail.params, detail.budget], () =>
      fill(
        regions.side,
        panel('Set up', facts(detail)),
        detail.calls.length ? panel('Flows it called', tree(detail.calls)) : null,
        panel('Sessions', detail.sessions.length ? h('ul', { class: 'tree' }, detail.sessions.map((one) => h('li', {}, h('b', {}, one.role), ` · ${one.backend}`, one.provider ? `@${one.provider}` : '', h('div', { class: 'dim mono' }, one.ident)))) : h('p', { class: 'dim' }, 'It opened none.')),
      ),
    )
  }

  function drawWrittenLanes() {
    if (!traced) {
      const reading = h('button', { class: 'btn', type: 'button', disabled: tracing }, tracing ? 'Reading the logs…' : 'Read its turns and transcript')
      reading.addEventListener('click', readTrace)
      fill(regions.lanes, h('header', {}, h('h2', {}, 'Turns')), h('p', { class: 'dim' }, 'What each session did is read back out of the logs it kept, which takes a moment for a long run.'), reading)
      return
    }
    const roles = rolesOfWritten()
    const rows = turnsOfTrace(traced).map((one) => ({ ...one, label: labelOf(one.key), color: lane(roles.indexOf(roleOf(one.key))) }))
    const starts = rows.flatMap((one) => one.turns.map((turn) => turn.start))
    const ends = rows.flatMap((one) => one.turns.map((turn) => turn.end))
    fill(
      regions.lanes,
      h('header', {}, h('h2', {}, 'Turns'), h('span', { class: 'kicker' }, `${rows.length} session${rows.length === 1 ? '' : 's'}`)),
      rows.length && starts.length ? lanes({ rows, from: Math.min(...starts), to: Math.max(...ends), live: false, picked, pick }) : h('p', { class: 'dim' }, 'Its logs held no turn to draw.'),
    )
  }

  function drawWrittenTranscript() {
    if (!traced) {
      fill(regions.transcript, h('header', {}, h('h2', {}, 'Transcript')), h('p', { class: 'dim' }, tracing ? 'Reading the logs…' : 'Read its turns first.'))
      return
    }
    const chosen = traced.find((one) => one.key === picked) || traced[0]
    fill(
      regions.transcript,
      h('header', {}, h('h2', {}, 'Transcript')),
      traced.length ? tabs(traced.map((one) => one.key), chosen ? chosen.key : '', labelOf) : null,
      h('div', { class: 'transcript', 'data-hmz': 'transcript' }, chosen ? saidTraced(chosen) : h('p', { class: 'dim' }, 'Its logs held nothing to read.')),
    )
  }

  async function readTrace() {
    tracing = true
    draw()
    try {
      traced = (await get(`/api/runs/${encodeURIComponent(named)}/trace`)).sessions
    } catch (error) {
      fill(regions.lanes, h('header', {}, h('h2', {}, 'Turns')), problem(error))
      tracing = false
      return
    }
    tracing = false
    drawn.lanes = drawn.transcript = undefined
    draw()
  }

  function rolesOfWritten() {
    return [...new Set(detail.sessions.map((one) => one.role))]
  }

  function roleOf(key) {
    const session = detail.sessions.find((one) => `${one.backend}:${one.ident}` === key)
    return session ? session.role : key.split(':')[0]
  }

  function labelOf(key) {
    if (!key) return 'all'
    if (!detail || !key.includes(':')) return key
    return `${roleOf(key)} · ${key.split(':')[0]}`
  }

  // ------------------------------------------------------------------ shared

  function pick(key) {
    picked = picked === key ? '' : key
    drawn['transcript-tabs'] = drawn.transcript = undefined
    draw()
  }

  function tabs(keys, chosen, label = (key) => key || 'all') {
    const list = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Whose transcript' })
    for (const key of keys) {
      const tab = h('button', { type: 'button', role: 'tab', 'aria-selected': String(key === chosen) }, label(key))
      tab.addEventListener('click', () => {
        picked = key
        drawn['transcript-tabs'] = drawn.transcript = drawn.lanes = undefined
        draw()
      })
      list.append(tab)
    }
    return list
  }

  let stopPolling = () => {}
  if (named) {
    stopPolling = poll(`/api/runs/${encodeURIComponent(named)}`, 4000, (data, error) => {
      detailError = error
      if (data) detail = data
      draw()
    })
  } else {
    // The run going has an epic as soon as it starts; it is named once the list says which.
    stopPolling = poll('/api/runs?status=running&limit=1', 4000, (data) => {
      const one = data && data.runs[0]
      if (one && (!detail || detail.name !== one.name)) {
        get(`/api/runs/${encodeURIComponent(one.name)}`).then((found) => {
          detail = found
          draw()
        })
      }
    })
  }
  const unfollow = follow((state) => {
    held = state
    if (live()) draw()
  })
  // The clocks a run going is drawn with move on their own between records.
  const ticking = setInterval(() => {
    if (live() && held) {
      drawn.lanes = undefined
      draw()
    }
  }, 1000)
  return () => {
    stopPolling()
    unfollow()
    clearInterval(ticking)
  }
}

function rolesOf(started, sessions) {
  const roles = started ? [...(started.roles || Object.keys(started.agents || {}))] : []
  for (const one of sessions) if (one.role && !roles.includes(one.role)) roles.push(one.role)
  return roles
}

/** What the run has cost, and how fast: the second line the terminal interface draws. */
function spentTile(said) {
  const parts = said.split(' · ')
  const priced = parts.length > 1 && parts[0].startsWith('$')
  return tile('spent', priced ? parts[0] : '—', priced ? parts.slice(1).join(' · ') : said || 'nothing yet')
}

function tile(label, value, sub) {
  return h('div', { class: 'tile' }, h('div', { class: 'kicker' }, label), value ? h('div', { class: 'value' }, value) : null, sub ? h('div', { class: 'sub' }, sub) : null)
}

/** What the run may spend against what it has: a meter for each limit it has. */
function budget(usage) {
  if (!usage || !usage.budget || !usage.usage) return tile('budget', '—', 'no limit said')
  const limits = []
  const spent = usage.usage
  const allowed = usage.budget
  const meter = (label, have, may, said) => {
    if (typeof have !== 'number' || typeof may !== 'number' || !Number.isFinite(may) || may <= 0) return
    const share = Math.min(1, have / may)
    limits.push(
      h(
        'div',
        {},
        h('div', { class: 'sub' }, `${label} ${said(have)} of ${said(may)}`),
        h('div', { class: ['meter', share >= 1 && 'over'], role: 'meter', 'aria-valuemin': '0', 'aria-valuemax': String(may), 'aria-valuenow': String(have), 'aria-label': label }, h('span', { style: { width: `${share * 100}%` } })),
      ),
    )
  }
  meter('cost', spent.cost, allowed.cost, (dollars) => `$${dollars.toFixed(2)}`)
  meter('output', spent.output_tokens, allowed.output_tokens, (count) => String(Math.round(count)))
  meter('time', secondsOf(spent.duration), secondsOf(allowed.duration), lasting)
  return h('div', { class: 'tile' }, h('div', { class: 'kicker' }, 'budget'), limits.length ? limits : h('div', { class: 'sub' }, 'no limit it can be measured against'))
}

function panel(title, ...kids) {
  return h('section', { class: 'panel' }, h('h2', {}, title), kids)
}

function facts(detail) {
  return h(
    'dl',
    { class: 'facts' },
    h('dt', {}, 'agents'),
    h('dd', {}, detail.agents.length ? detail.agents.map((one) => h('div', { class: 'mono' }, `${one.role}=${one.runs}`)) : '—'),
    h('dt', {}, 'envs'),
    h('dd', {}, detail.used.length ? detail.used.map((one) => h('div', { class: 'mono' }, one)) : '—'),
    h('dt', {}, 'params'),
    h('dd', {}, Object.keys(detail.params || {}).length ? h('pre', { class: 'block' }, JSON.stringify(detail.params, null, 2)) : '—'),
    h('dt', {}, 'budget'),
    h('dd', {}, budgeted(detail.budget)),
    detail.picked_up ? [h('dt', {}, 'picked up'), h('dd', {}, h('a', { href: `#/runs/${encodeURIComponent(detail.picked_up)}` }, detail.picked_up))] : null,
    detail.profile ? [h('dt', {}, 'profiled'), h('dd', {}, 'yes')] : null,
  )
}

/** A budget in words: each limit it set, and whether the last turn could finish over it. */
function budgeted(budget) {
  if (!budget) return '—'
  const seconds = secondsOf(budget.duration)
  const limits = [
    typeof budget.cost === 'number' && Number.isFinite(budget.cost) ? `$${budget.cost.toFixed(2)}` : '',
    seconds ? lasting(seconds) : '',
    typeof budget.output_tokens === 'number' ? `${budget.output_tokens} output tokens` : '',
  ].filter(Boolean)
  if (!limits.length) return 'no limit'
  return `${limits.join(' · ')}${budget.graceful === false ? ', cut off at once' : ', letting the last turn finish'}`
}

function tree(calls) {
  return h(
    'ul',
    { class: 'tree' },
    calls.map((call) => h('li', {}, h('b', {}, call.flow), ' ', call.how ? badge(call.how) : null, call.task ? h('div', { class: 'dim' }, call.task.slice(0, 160)) : null, call.calls.length ? tree(call.calls) : null)),
  )
}
