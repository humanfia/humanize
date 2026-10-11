// One epic: the run going, as it happens, or one written down. `#/runs/<name>` draws it as a
// graph of its agents and who handed to whom; `/agents/<role>` is the graph with that agent
// picked out; `/sessions/<key>` is one session's thread, as a chat is read. `#/live` is
// whichever run is going. Under the view, while the run goes, are the questions it waits on a
// person for and the box that says a line to it; beside it, a panel of what it is and was --
// its figures, its budget, how it was set up, the flows it called -- with its board, its people
// and the side questions asked beside it.

import { asides, board, outworlders, question, saying } from '../acting.js'
import { get } from '../api.js'
import { go } from '../app.js'
import { ago, badge, flowName, confirming, copier, empty, fill, h, headline, icon, lasting, problem, secondsOf, when } from '../dom.js'
import { ask } from '../held.js'
import { live, sessionsOf, took, watch, written } from '../epic.js'
import { graph } from '../graph.js'
import { bar, sidePanel, tabbed } from '../shell.js'
import { saidTraced, sayer } from '../transcript.js'

/** The most lines of a run going drawn at once: past it, the oldest go. */
const LINES = 3000

export function mount(root, { parts, query }) {
  let name = parts[0] === 'live' ? '' : parts[1]
  /** Where the epic going is looked for, for an epic not named. */
  const wanted = query.get('workspace') || ''
  let mode = modeOf(parts)
  const panel = sidePanel('the epic')
  const head = h('div', { class: 'bar-holder' })
  const main = h('div', { class: 'epic-main' })
  const dock = h('div', { class: 'dock', 'data-hmz': 'dock' })
  fill(root, h('div', { class: 'view view-epic' }, h('div', { class: 'work' }, head, main, dock), panel.node))

  const drawn_ = graph({ open: (role) => go(`/epics/${encodeURIComponent(name)}/agents/${encodeURIComponent(role)}`) })
  // What is said to the epic, and asked beside it, once it is known which workspace it is of.
  let say = null
  let sayTo = null
  let sayToKey = ''
  let btw = null
  const workspace = () => (seen && seen.workspace) || wanted
  /** The card of each question waiting, kept while it waits as it was asked of whom it was. */
  const cards = new Map()
  let seen = null
  let traced = null
  let tracing = false
  let traceError = null
  let tab = 'epic'
  const drawn = {}

  /** Draws one part again, where what it is drawn from has changed. */
  function region(part, from, draw) {
    const key = JSON.stringify(from)
    if (drawn[part] === key) return
    drawn[part] = key
    draw()
  }

  function draw() {
    if (!seen) return
    const { detail, error, going, held, none } = seen
    if (!detail) {
      if (name) {
        region('main', ['reading', String(error)], () => fill(main, h('div', { class: 'view-pad' }, error ? problem(error) : h('p', { class: 'loading', role: 'status' }, 'Reading the epic…'))))
      } else {
        const starting = held && held.standing.run && held.standing.run.state === 'running'
        region('head', ['none'], () => fill(head, bar({ title: starting ? 'Starting the epic…' : 'No epic is going' })))
        region('main', ['none', starting, none], () =>
          fill(
            main,
            h(
              'div',
              { class: 'view-pad' },
              starting || !none
                ? h('p', { class: 'loading', role: 'status' }, 'Waiting for the epic to be written down…')
                : empty('No epic is going here.', ' Start one, or open an epic from the sidebar.', h('a', { class: 'btn primary', href: '#/new' }, 'New epic')),
            ),
          ),
        )
      }
      region('panel-tabs', ['none'], () => fill(panel.body))
      return
    }
    if (!name) {
      // The run going is named now: the address says which, and it is followed by name.
      name = detail.name
      history.replaceState(null, '', `#/epics/${encodeURIComponent(name)}`)
      stop()
      stop = watch(name, detail.workspace, told)
      return
    }
    if (!say) {
      say = saying(detail.workspace)
      btw = asides(detail.workspace)
    }
    const run = going && going.started ? going : null
    const model = run ? live(held, run, detail) : written(detail, traced)
    const roleOfSession = mode.session ? mode.session.split('/')[0] : ''
    drawHead(detail, run)
    if (mode.session) drawThread(detail, run)
    else drawGraph(detail, run, model)
    drawDock(detail, run)
    drawPanel(detail, run, model, mode.focus || roleOfSession)
  }

  // ------------------------------------------------------------------ the bar

  function drawHead(detail, run) {
    const going = Boolean(run && run.live)
    const state = run ? (run.ended ? run.ended.how : run.state === 'stopping' ? 'stopping' : run.live ? 'running' : detail.how) : detail.how
    const spent = run && held().figures && held().figures.tally && held().figures.tally[1] ? held().figures.tally[1].split(' · ')[0] : detail.spent ? detail.spent.money : ''
    region('head', [mode, detail.name, detail.task, detail.flow, detail.picks_up, state, going, run && run.state], () => {
      const actions = []
      if (going && run.state === 'running') actions.push(confirming({ label: 'Stop', ask: 'Stop this epic?', yes: 'Stop', no: 'Cancel', act: () => ask(workspace(), 'stop') }))
      else if (going && run.state === 'stopping') actions.push(confirming({ label: 'Force stop', ask: 'Close every session now?', yes: 'Force stop', no: 'Cancel', act: () => ask(workspace(), 'force') }))
      if (!going && detail.picks_up) actions.push(h('a', { class: 'btn', href: `#/new?flow=${encodeURIComponent(detail.flow)}&resume=${encodeURIComponent(detail.name)}` }, icon('resume'), 'Resume'))
      if (!going) actions.push(h('a', { class: 'icon-btn', href: `/api/runs/${encodeURIComponent(detail.name)}/bundle`, download: '', 'aria-label': 'Export', title: 'Export' }, icon('download')))
      actions.push(copier('Copy link', () => location.href))
      actions.push(panel.toggle)
      const base = `#/epics/${encodeURIComponent(detail.name)}`
      const sub = [
        badge(state),
        h('span', { class: 'mono', title: detail.flow }, flowName(detail.flow)),
        h('span', { title: when(detail.began) }, `began ${ago(detail.began)}`),
        h('span', { class: 'mono', 'data-hmz': 'clock' }),
      ]
      const title = mode.session
        ? h('span', { class: 'crumbs' }, h('a', { href: base }, headline(detail.task)), h('span', { 'aria-hidden': 'true' }, ' / '), h('span', { class: 'mono' }, mode.session))
        : headline(detail.task)
      fill(head, bar({ title, sub, actions }))
    })
    // What moves on its own is said again in place, never drawing over a question being asked.
    const clock = head.querySelector('[data-hmz=clock]')
    if (clock) clock.textContent = [took(detail, run) && `took ${took(detail, run)}`, spent].filter(Boolean).join(' · ')
  }

  // ------------------------------------------------------------------ the graph

  function drawGraph(detail, run, model) {
    region('main-kind', ['graph'], () => {
      fill(main, drawn_.node)
      for (const one of ['thread', 'thread-head']) drawn[one] = undefined
    })
    const asking = !run && !traced
    region('graph-note', [asking, tracing, String(traceError)], () => {
      main.querySelector('.graph-note')?.remove()
      if (!asking) return
      const reading = h('button', { class: 'btn small', type: 'button', disabled: tracing }, tracing ? 'Reading…' : 'Read turns')
      reading.addEventListener('click', readTrace)
      main.append(h('div', { class: 'graph-note', role: 'status' }, traceError ? problem(traceError) : h('span', {}, 'Handovers and turns come from the epic’s logs.'), reading))
    })
    drawn_.draw(model, mode.focus, detail.name)
  }

  async function readTrace() {
    tracing = true
    traceError = null
    draw()
    try {
      traced = (await get(`/api/runs/${encodeURIComponent(name)}/trace`)).sessions
    } catch (error) {
      traceError = error
    }
    tracing = false
    draw()
  }

  // ------------------------------------------------------------------ one session's thread

  let box = null
  let cut = null
  let saidBy = null
  let saidUpTo = -1
  let saidFor = ''

  function drawThread(detail, run) {
    const key = mode.session
    region('main-kind', ['thread'], () => {
      box = h('div', { class: 'thread', 'data-hmz': 'thread', role: 'log', 'aria-live': 'off' })
      cut = h('p', { class: 'dim thread-cut', hidden: true }, `Only its last ${LINES} lines are drawn here; the epic keeps every one.`)
      fill(main, h('div', { class: 'thread-scroll' }, h('div', { class: 'thread-column' }, cut, box)))
      saidFor = ''
      drawn['thread'] = undefined
    })
    const scroller = main.querySelector('.thread-scroll')
    if (run) {
      // Another link's records start their numbers over: what was said is said again from the top.
      const whose = JSON.stringify([key, run.number, held().epoch])
      if (saidFor !== whose) {
        saidFor = whose
        saidBy = sayer(key)
        saidUpTo = -1
        fill(box)
        cut.hidden = true
      }
      const stuck = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 60
      let added = false
      for (const record of run.records) {
        if (record.seq <= saidUpTo) continue
        saidUpTo = record.seq
        for (const line of saidBy(record)) {
          box.append(line)
          added = true
        }
      }
      while (box.childElementCount > LINES) {
        box.firstElementChild.remove()
        cut.hidden = false
      }
      if (!box.childElementCount) box.append(h('p', { class: 'dim thread-empty' }, 'Nothing has been said in this session yet.'))
      else if (added) box.querySelector(':scope > .thread-empty')?.remove()
      if (added && stuck) scroller.scrollTop = scroller.scrollHeight
      return
    }
    // A run written down: what a session said is read out of the logs it kept, once asked for
    // by opening the session.
    if (!traced && !tracing && !traceError) readTrace()
    region('thread', [key, Boolean(traced), tracing, String(traceError)], () => {
      saidFor = ''
      const session = sessionsOf(detail).find((one) => one.key === key)
      const read = traced && session ? traced.find((one) => one.key === session.traced) : null
      fill(
        box,
        traceError
          ? problem(traceError)
          : !traced
            ? h('p', { class: 'loading', role: 'status' }, 'Reading its logs…')
            : !session
              ? empty('There is no such session in this epic.', ' Pick one of its sessions in the sidebar.')
              : read
                ? saidTraced(read)
                : h('p', { class: 'dim' }, 'Its logs held nothing this session said.'),
      )
    })
  }

  // ------------------------------------------------------------------ under the view

  function drawDock(detail, run) {
    const standing = held() ? held().standing : {}
    const going = Boolean(run && run.live)
    const pending = going ? (standing.pending && standing.pending.pending) || [] : []
    const clients = standing.clients && standing.clients.clients
    const me = held() ? held().me : ''
    region('dock-questions', [pending, me, clients], () => {
      const kept = new Set()
      const shown = pending.map((one) => {
        const key = JSON.stringify([one.question, one.owner || '', me, one.text, one.options])
        if (!cards.has(key)) cards.set(key, question(workspace(), one, me, clients))
        kept.add(key)
        return cards.get(key)
      })
      for (const key of [...cards.keys()]) if (!kept.has(key)) cards.delete(key)
      dock.querySelector('.questions')?.remove()
      if (shown.length) dock.prepend(h('div', { class: 'questions', 'data-hmz': 'waiting', role: 'region', 'aria-label': 'Waiting for you' }, shown))
    })
    if (going) {
      const sessions = (standing.sessions && standing.sessions.open) || []
      const working = (standing.sessions && standing.sessions.working) || []
      const roles = run.started.roles || Object.keys(run.started.agents || {})
      const people = run.started.outworlders || []
      region('dock-offers', [roles, sessions, working, people], () => say.offers(roles, sessions, working, people))
      if (mode.session && sayToKey !== mode.session) {
        sayTo = saying(workspace(), mode.session)
        sayToKey = mode.session
      }
    }
    const composer = going ? (mode.session ? sayTo.node : say.node) : null
    region('dock-composer', [going, mode.session, detail.picks_up], () => {
      dock.querySelector('.composer, .dock-note')?.remove()
      if (composer) dock.append(composer)
      else if (detail.picks_up)
        dock.append(h('p', { class: 'dock-note' }, 'Ended · ', h('a', { href: `#/new?flow=${encodeURIComponent(detail.flow)}&resume=${encodeURIComponent(detail.name)}` }, 'Resume')))
    })
  }

  // ------------------------------------------------------------------ the panel beside it

  function drawPanel(detail, run, model, focus) {
    const going = Boolean(run && run.live)
    const standing = held() ? held().standing : {}
    const items = going && standing.board ? standing.board.items : null
    const people = going ? run.started.outworlders || [] : []
    const tabs = [['epic', 'Epic'], ['aside', 'Aside'], items ? ['board', 'Board'] : null, people.length ? ['people', 'People'] : null].filter(Boolean)
    if (!tabs.some(([key]) => key === tab)) tab = 'epic'
    region('panel-tabs', [tabs, tab], () => {
      fill(
        panel.body,
        tabbed(tabs, tab, (key) => {
          tab = key
          for (const one of Object.keys(drawn)) if (one.startsWith('panel')) drawn[one] = undefined
          draw()
        }),
        h('div', { class: 'panel-pane' }),
      )
      for (const one of Object.keys(drawn)) if (one.startsWith('panel-') && one !== 'panel-tabs') drawn[one] = undefined
    })
    const pane = panel.body.querySelector('.panel-pane')
    if (tab === 'epic') {
      const figures = held() && held().figures
      region('panel-run', [model.agents, model.handovers, focus, going, detail, run && run.ended, figures && figures.tally, figures && figures.lasting, standing.usage, standing.calls, run && run.offset, Math.floor(Date.now() / 1000)], () =>
        fill(pane, overview(detail, run, model, focus, going, figures, standing)),
      )
    } else if (tab === 'aside') {
      const opened = model.agents.flatMap((one) => one.sessions.map((session) => session.key))
      region('panel-aside', [run ? opened : []], () => {
        btw.sessions(run ? opened : [])
        fill(pane, h('p', { class: 'dim' }, 'Side questions never reach the epic.'), btw.node)
      })
    } else if (tab === 'board') {
      region('panel-board', [items], () => fill(pane, board(workspace(), items || [])))
    } else if (tab === 'people') {
      const clients = standing.clients && standing.clients.clients
      region('panel-people', [people, standing.claims, standing.away, held().me, clients], () =>
        fill(pane, outworlders(workspace(), people, { claims: (standing.claims && standing.claims.claims) || {}, away: standing.away, me: held().me, clients })),
      )
    }
  }

  function overview(detail, run, model, focus, going, figures, standing) {
    const agent = model.agents.find((one) => one.role === focus)
    const base = `#/epics/${encodeURIComponent(detail.name)}`
    const parts = []
    if (agent) {
      parts.push(
        section(
          agent.role,
          h('div', { class: 'focus', style: { '--lane': agent.color }, 'data-hmz': 'focus' },
            h('div', { class: 'mono dim' }, agent.spec || '—'),
            h('div', {}, [agent.status, agent.turns !== null && agent.turns !== undefined ? `${agent.turns} turn${agent.turns === 1 ? '' : 's'}` : '', agent.tokens ? `${agent.tokens} tokens` : ''].filter(Boolean).join(' · ')),
            agent.sessions.length
              ? h('ul', { class: 'links' }, agent.sessions.map((one) => h('li', {}, h('a', { href: `${base}/sessions/${encodeURIComponent(one.key)}` }, one.working ? '● ' : '○ ', h('span', { class: 'mono' }, one.key)), one.about ? h('span', { class: 'dim' }, ` ${one.about}`) : null)))
              : null,
            agent.under.length ? h('ul', { class: 'links' }, agent.under.map((one) => h('li', {}, `${one.working ? '◆' : '◇'} ${one.about}`))) : null,
          ),
        ),
      )
    }
    if (run) {
      const lines = figures && figures.tally && figures.tally.length ? figures.tally : []
      const elapsed = figures ? figures.lasting : took(detail, run) || '—'
      parts.push(section('Figures', h('div', { class: 'tiles' }, tile('time', elapsed, going ? 'elapsed' : 'total'), spentTile(lines[1] || ''), tile('tokens', lines[0] ? '' : '—', lines[0] || ''), budgetTile(standing.usage))))
    } else {
      const spent = detail.spent
      parts.push(
        section(
          'Figures',
          h(
            'div',
            { class: 'tiles' },
            tile('spent', spent ? spent.money || '—' : '—', ''),
            tile('output tokens', spent ? spent.tokens : '—', ''),
            tile('took', took(detail, null) || '—', spent && spent.worked ? `${spent.worked} of it working` : ''),
            tile('sessions', String(detail.sessions.length), `${detail.agents.length} agent role${detail.agents.length === 1 ? '' : 's'}`),
          ),
        ),
      )
    }
    parts.push(section('Task', detail.task.length > 400 ? h('details', {}, h('summary', {}, detail.task.slice(0, 240), '…'), h('pre', { class: 'block' }, detail.task)) : h('p', { class: 'prose' }, detail.task)))
    parts.push(
      section(
        'Handovers',
        model.handovers.length
          ? h('ul', { class: 'handovers' }, model.handovers.map((one) => h('li', { class: model.latest && model.latest[0] === one.from && model.latest[1] === one.to ? 'latest' : '' }, `${one.from} → ${one.to} ×${one.count}`)))
          : h('p', { class: 'dim' }, run ? 'Nobody has handed over yet.' : !traced ? 'Read its turns to see who handed to whom.' : traced.length ? 'Nobody handed over.' : 'Its logs held no turn to read.'),
      ),
    )
    const calls = (standing.calls && standing.calls.calls) || []
    if (run && calls.length) {
      const offset = run.offset
      parts.push(section('Running flows', h('ul', { class: 'tree' }, calls.map((call) => h('li', { style: { marginLeft: `${call.depth * 14}px` } }, h('b', {}, call.name), ' ', h('span', { class: 'dim' }, offset === null ? '' : lasting(Date.now() / 1000 - (call.since + offset))))))))
    } else if (detail.calls.length) {
      parts.push(section('Called flows', tree(detail.calls)))
    }
    parts.push(section('Setup', facts(detail)))
    return parts
  }

  // ------------------------------------------------------------------ following it

  function held() {
    return seen && seen.held
  }

  function told(now) {
    seen = now
    draw()
  }

  let stop = () => {}
  stop = watch(name, wanted, told)
  // The clocks a run going is drawn with move on their own between records.
  const ticking = setInterval(() => {
    if (seen && seen.going && seen.going.live) draw()
  }, 1000)

  return {
    leave() {
      stop()
      clearInterval(ticking)
    },
    /** Moves to another part of the same run without drawing it all again. */
    moved({ parts: next }) {
      if (next[0] !== 'epics' || !name || next[1] !== name) return false
      mode = modeOf(next)
      for (const one of ['head', 'panel-run', 'dock-composer']) drawn[one] = undefined
      draw()
      return true
    },
  }
}

function modeOf(parts) {
  return { session: parts[2] === 'sessions' ? parts[3] || '' : '', focus: parts[2] === 'agents' ? parts[3] || '' : '' }
}

function section(title, ...kids) {
  return h('section', { class: 'side-section' }, h('h3', {}, title), kids)
}

/** What the run has cost, and how fast: the second line the terminal interface draws. */
function spentTile(said) {
  const parts = said.split(' · ')
  const priced = parts.length > 1 && parts[0].startsWith('$')
  return tile('spent', priced ? parts[0] : '—', priced ? parts.slice(1).join(' · ') : said)
}

function tile(label, value, sub) {
  return h('div', { class: 'tile' }, h('div', { class: 'kicker' }, label), value ? h('div', { class: 'value' }, value) : null, sub ? h('div', { class: 'sub' }, sub) : null)
}

/** What the run may spend against what it has: a meter for each limit it has. */
function budgetTile(usage) {
  if (!usage || !usage.budget || !usage.usage) return tile('budget', '—', 'No limit')
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
  return h('div', { class: 'tile' }, h('div', { class: 'kicker' }, 'budget'), limits.length ? limits : h('div', { class: 'sub' }, 'No measurable limit'))
}

function facts(detail) {
  return h(
    'dl',
    { class: 'facts' },
    h('dt', {}, 'epic'),
    h('dd', { class: 'mono' }, detail.name),
    h('dt', {}, 'agents'),
    h('dd', {}, detail.agents.length ? detail.agents.map((one) => h('div', { class: 'mono' }, `${one.role}=${one.runs}`)) : '—'),
    h('dt', {}, 'envs'),
    h('dd', {}, detail.used.length ? detail.used.map((one) => h('div', { class: 'mono' }, one)) : '—'),
    h('dt', {}, 'params'),
    h('dd', {}, Object.keys(detail.params || {}).length ? h('pre', { class: 'block' }, JSON.stringify(detail.params, null, 2)) : '—'),
    h('dt', {}, 'budget'),
    h('dd', {}, budgeted(detail.budget)),
    h('dt', {}, 'sessions'),
    h('dd', {}, detail.sessions.length ? sessionsOf(detail).map((one) => h('div', {}, h('span', { class: 'mono' }, one.key), ` · ${one.backend}`, one.provider ? `@${one.provider}` : '', h('div', { class: 'dim mono' }, one.ident))) : 'none'),
    detail.picked_up ? [h('dt', {}, 'resumed from'), h('dd', {}, h('a', { href: `#/epics/${encodeURIComponent(detail.picked_up)}` }, detail.picked_up))] : null,
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
