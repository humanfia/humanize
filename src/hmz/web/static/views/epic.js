// One epic: the run going, as it happens, or one written down. `#/runs/<name>` draws it as a
// graph of its agents and who handed to whom; `/agents/<agent>` is the graph with that agent
// picked out; `/sessions/<key>` is one session's thread, as a chat is read; `/exomyth` is its
// timeline, drawn by views/exomyth. `#/live` is whichever run is going -- a chat's opened on its
// conversation rather than its graph. Under the view, while the run goes, are the questions it
// waits on a person for and the box that says a line to it; beside it, a panel of what it is
// and was --
// its figures, its budget, how it was set up, the flows it called -- with its board, its people
// and the side questions asked beside it.

import { asides, board, outworlders, question, saying } from '../acting.js'
import { get, hash, scoped } from '../api.js'
import { go } from '../app.js'
import { acting, ago, badge, flowName, pathText, confirming, copier, empty, fill, h, headline, icon, lasting, problem, secondsOf, when } from '../dom.js'
import { ask } from '../held.js'
import { live, read as markRead, sessionsOf, took, watch, written } from '../epic.js'
import { graph } from '../graph.js'
import { bar, dragged, keep, kept, sidePanel, tabbed } from '../shell.js'
import { backedSaid, epicMenu, upload } from '../sidebar.js'
import { copy, menuOn } from '../ui.js'
import { saidTraced, sayer } from '../transcript.js'

/** The most lines of a run going drawn at once: past it, the oldest go. */
const LINES = 3000

export function mount(root, { parts, query }) {
  if (parts[0] === 'epics' && parts[2] === 'exomyth') return exomyth(root, parts[1], query)
  let name = parts[0] === 'live' ? '' : parts[1]
  /** Where the epic going is looked for, for an epic not named. */
  const wanted = query.get('workspace') || ''
  let mode = modeOf(parts)
  const panel = sidePanel('the epic')
  const head = h('div', { class: 'bar-holder' })
  const main = h('div', { class: 'epic-main' })
  const dock = h('div', { class: 'dock', 'data-hmz': 'dock' })
  fill(root, h('div', { class: 'view view-epic' }, h('div', { class: 'work' }, head, main, dock), panel.node))

  // A person is read by their log, as the terminal interface's monitor reads one; an agent is
  // picked out on the graph.
  const drawn_ = graph({ open: (who) => go(`/epics/${encodeURIComponent(name)}/${persons.has(who) ? 'logs' : 'agents'}/${encodeURIComponent(who)}`) })
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
  /** Whether the epic going was a chat not named when this was opened, to be opened on its conversation once it has one. */
  let landing = false
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
                : empty('No epic is going here.', ' Start one, or open an epic from the sidebar.', h('a', { class: 'btn primary', href: hash('/new') }, 'New epic')),
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
      history.replaceState(null, '', hash(`/epics/${encodeURIComponent(name)}`))
      landing = chatting(detail)
      stop()
      stop = watch(name, detail.workspace, told)
      return
    }
    if (!say) {
      say = saying(detail.workspace)
      btw = asides(detail.workspace, detail.name)
    }
    const run = going && going.started ? going : null
    const opened = landing && run && run.records.find((one) => one.type === 'opened' && !one.person)
    if (opened) {
      // A chat is a conversation, and is opened on it, as a chat app opens on one.
      landing = false
      history.replaceState(null, '', hash(`/epics/${encodeURIComponent(name)}/sessions/${encodeURIComponent(opened.key)}`))
      mode = modeOf(['epics', name, 'sessions', opened.key])
    }
    const model = run ? live(held, run, detail) : written(detail, traced)
    const agentOfSession = mode.session ? mode.session.split('/')[0] : mode.log || ''
    persons = new Set(model.agents.filter((one) => one.person).map((one) => one.name))
    drawHead(detail, run)
    if (reading(mode)) drawThread(detail, run)
    else drawGraph(detail, run, model)
    drawDock(detail, run)
    drawPanel(detail, run, model, mode.focus || agentOfSession)
  }

  // ------------------------------------------------------------------ the bar

  function drawHead(detail, run) {
    const going = Boolean(run && run.live)
    const state = run ? (run.ended ? run.ended.how : run.state === 'stopping' ? 'stopping' : run.live ? 'running' : detail.how) : detail.how
    const spent = run && held().figures && held().figures.tally && held().figures.tally[1] ? held().figures.tally[1].split(' · ')[0] : detail.spent ? detail.spent.money : ''
    region('head', [mode, detail.name, detail.task, detail.flow, detail.picks_up, state, going, run && run.state, detail.backed], () => {
      const actions = []
      if (going && run.state === 'running') actions.push(confirming({ label: 'Stop', ask: 'Stop this epic?', yes: 'Stop', no: 'Cancel', act: () => ask(workspace(), 'stop') }))
      else if (going && run.state === 'stopping') actions.push(confirming({ label: 'Force stop', ask: 'Close every session now?', yes: 'Force stop', no: 'Cancel', act: () => ask(workspace(), 'force') }))
      if (!going && detail.picks_up) actions.push(h('a', { class: 'btn', href: hash(`/new?flow=${encodeURIComponent(detail.flow)}&resume=${encodeURIComponent(detail.name)}`) }, icon('resume'), 'Resume'))
      actions.push(h('a', { class: 'icon-btn', href: hash(`/epics/${encodeURIComponent(detail.name)}/exomyth`), 'aria-label': 'Exomyth', title: 'Exomyth', 'data-hmz': 'exomyth-open' }, icon('chart')))
      if (!going) actions.push(h('a', { class: 'icon-btn', href: scoped(`/api/runs/${encodeURIComponent(detail.name)}/bundle`), download: '', 'aria-label': 'Export', title: 'Export' }, icon('download')))
      // How each target last took it, said on hover; read again as the epic is.
      actions.push(h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Upload', title: backedSaid(detail.backed) || 'Upload', 'data-hmz': 'upload', onclick: () => upload(detail.name) }, icon('up')))
      actions.push(copier('Copy link', () => location.href))
      actions.push(panel.toggle)
      const base = hash(`/epics/${encodeURIComponent(detail.name)}`)
      const sub = [
        badge(state),
        h('span', { class: 'mono', title: detail.flow }, flowName(detail.flow)),
        h('span', { title: when(detail.began) }, `began ${ago(detail.began)}`),
        h('span', { class: 'mono', 'data-hmz': 'clock' }),
      ]
      const where = mode.session || (mode.log ? `${mode.log} log` : 'Log')
      const title = reading(mode)
        ? h('span', { class: 'crumbs' }, h('a', { href: base }, headline(detail.task)), h('span', { 'aria-hidden': 'true' }, ' / '), h('span', { class: 'mono' }, where))
        : headline(detail.task)
      fill(head, bar({ title, sub, actions }))
      const named = head.querySelector('.bar-title')
      named.title = detail.task
      menuOn(named, () => epicMenu({ ...detail, task: detail.task, held: going }))
    })
    // What moves on its own is said again in place, never drawing over a question being asked.
    const clock = head.querySelector('[data-hmz=clock]')
    if (clock) clock.textContent = [took(detail, run) && `took ${took(detail, run)}`, spent].filter(Boolean).join(' · ')
  }

  // ------------------------------------------------------------------ the graph

  function drawGraph(detail, run, model) {
    region('main-kind', ['graph', shape], () => {
      const switching = h('div', { class: 'segmented shape-switch', role: 'group', 'aria-label': 'Shape' }, [['graph', 'Graph'], ['list', 'List']].map(([key, label]) => h('button', { type: 'button', 'aria-pressed': String(shape === key), onclick: () => {
        shape = key
        keep('hmz-shape', key === 'graph' ? null : key)
        draw()
      } }, label)))
      listed = h('div', { class: 'shape-list', 'data-hmz': 'agent-list' })
      fill(main, shape === 'graph' ? drawn_.node : h('div', { class: 'list-scroll' }, listed), switching)
      for (const one of ['thread', 'thread-head', 'thread-ask', 'agent-list', 'graph-note']) drawn[one] = undefined
    })
    if (shape === 'list') {
      region('agent-list', [model.agents.map(({ name, role, working, status, spec, sessions, tokens }) => [name, role, working, status, spec, tokens, sessions.map((one) => [one.key, one.working, one.turns.length])]), mode.focus], () => fill(listed, listOf(model, detail.name, mode.focus)))
      return
    }
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

  /** Whether the agents are drawn as a graph or as a list, as this browser last chose. */
  let shape = kept('hmz-shape', 'graph') === 'list' ? 'list' : 'graph'
  let listed = null

  /** Who is a person in the epic in front, whose log is what is asked of them. */
  let persons = new Set()

  /** What the thread in front is the transcript of, as `sayer` takes it. */
  function threadKey() {
    if (mode.session) return mode.session
    if (!mode.log) return ''
    return persons.has(mode.log) ? `person:${mode.log}` : `agent:${mode.log}`
  }

  function drawThread(detail, run) {
    const key = threadKey()
    region('main-kind', ['thread'], () => {
      box = h('div', { class: 'thread', 'data-hmz': 'thread', role: 'log', 'aria-live': 'off' })
      cut = h('p', { class: 'dim thread-cut', hidden: true }, `Only its last ${LINES} lines are drawn here; the epic keeps every one.`)
      fill(main, h('div', { class: 'thread-scroll' }, h('div', { class: 'thread-column' }, cut, box)))
      saidFor = ''
      drawn['thread'] = undefined
      drawn['thread-ask'] = undefined
    })
    const scroller = main.querySelector('.thread-scroll')
    if (run) {
      // Another link's records start their numbers over: what was said is said again from the top.
      const chat = chatting(detail)
      const whose = JSON.stringify([key, run.number, held().epoch, chat])
      if (saidFor !== whose) {
        saidFor = whose
        saidBy = sayer(key, { chat })
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
      // Read here is read: a session's thread drawn is its lines seen.
      if (mode.session) markRead(detail.name, mode.session, run.records)
      if (!box.childElementCount) box.append(h('p', { class: 'dim thread-empty' }, 'Nothing said yet.'))
      else if (added) box.querySelector(':scope > .thread-empty')?.remove()
      // What a chat's agent stops to ask in a turn is asked at the end of its conversation,
      // its answers offered there to pick and anything typed below answering it.
      const asking = chat && mode.session && run.live ? askedIn(mode.session) : null
      region('thread-ask', [saidFor, asking], () => {
        main.querySelector('.thread-ask')?.remove()
        if (!asking || !asking.options.length) return
        box.after(
          h(
            'div',
            { class: 'thread-ask row', 'data-hmz': 'thread-ask' },
            asking.options.map((option, index) =>
              acting(option, () => ask(workspace(), 'answer', { question: asking.question, text: String(index + 1) }), { kind: 'btn small', busy: 'Answering…' }),
            ),
          ),
        )
        added = true
      })
      if (added && stuck) scroller.scrollTop = scroller.scrollHeight
      return
    }
    // A run written down: what a session said is read out of the logs it kept, once asked for
    // by opening the session.
    if (!traced && !tracing && !traceError) readTrace()
    region('thread', [key, Boolean(traced), tracing, String(traceError)], () => {
      saidFor = ''
      // The sessions the thread is of: one, every one of an agent's, or every one.
      const sessions = sessionsOf(detail).filter((one) => (mode.session ? one.key === key : !mode.log || one.agent === mode.log))
      const read = traced ? sessions.map((one) => ({ ...(traced.find((each) => each.key === one.traced) || { actions: [] }), label: one.key })).filter((one) => one.actions.length) : []
      fill(
        box,
        traceError
          ? problem(traceError)
          : !traced
            ? h('p', { class: 'loading', role: 'status' }, 'Reading its logs…')
            : mode.session && !sessions.length
              ? empty('There is no such session in this epic.', ' Pick one of its sessions in the sidebar.')
              : read.length
                ? saidTraced(...read)
                : h('p', { class: 'dim' }, persons.has(mode.log) ? 'A person’s log is kept while the epic is.' : 'Its logs held nothing said.'),
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
    // A chat waiting to be told what next is waiting on its composer, which says it; what it
    // asks in its conversation's thread is asked there.
    const chat = chatting(detail)
    const threaded = chat && mode.session ? askedIn(mode.session) : null
    const carded = pending.filter((one) => !(chat && (one.mode === 'listen' || (threaded && one.question === threaded.question))))
    region('dock-questions', [carded, me, clients], () => {
      const kept = new Set()
      const shown = carded.map((one) => {
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
      const names = run.started.names || {}
      const agents = (run.started.roles || Object.keys(run.started.agents || {})).map((role) => names[role] || role)
      const people = run.started.outworlders || []
      region('dock-offers', [agents, sessions, working, people], () => say.offers(agents, sessions, working, people))
      // In a thread, a line goes to whose thread it is: a session, an agent, or a person.
      const to = mode.session || (mode.log ? (persons.has(mode.log) ? `outworlder:${mode.log}` : mode.log) : '')
      if (to && sayToKey !== to) {
        // A chat's line is said to its next turn, which is its one conversation's: the turn
        // open, or the next the person is asked to start.
        sayTo = saying(workspace(), to, { asked: () => askedIn(to), to: chatting(detail) && mode.session ? '' : to })
        sayToKey = to
      }
    }
    const composer = going ? (reading(mode) && sayToKey && (mode.session || mode.log) ? sayTo.node : say.node) : null
    region('dock-composer', [going, mode.session, mode.log, detail.picks_up, detail.foreign], () => {
      dock.querySelector('.composer, .dock-note')?.remove()
      if (composer) dock.append(composer)
      else if (detail.picks_up)
        dock.append(h('p', { class: 'dock-note' }, 'Ended · ', h('a', { href: hash(`/new?flow=${encodeURIComponent(detail.flow)}&resume=${encodeURIComponent(detail.name)}`) }, 'Resume')))
      // Imported from a workspace this machine has not got as it was: why it is not picked up here.
      else if (detail.foreign) dock.append(h('p', { class: 'dock-note', 'data-hmz': 'foreign' }, `Imported · not resumable here: ${detail.foreign}`))
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
        dragged(
          tabbed(tabs, tab, (key) => {
            tab = key
            for (const one of Object.keys(drawn)) if (one.startsWith('panel')) drawn[one] = undefined
            draw()
          }),
        ),
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
      // Every session of the epic: one the runs still hold asked as it is, an earlier epic's
      // carried on from where that epic kept it.
      region('panel-aside', [opened], () => {
        btw.sessions(opened)
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
    const agent = model.agents.find((one) => one.name === focus)
    const base = hash(`/epics/${encodeURIComponent(detail.name)}`)
    const parts = []
    if (agent) {
      parts.push(
        section(
          agent.name,
          h('div', { class: 'focus', style: { '--lane': agent.color }, 'data-hmz': 'focus' },
            h('div', { class: 'mono dim' }, [agent.role !== agent.name && agent.role, agent.spec].filter(Boolean).join(' · ') || '—'),
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
            tile('sessions', String(detail.sessions.length), `${detail.agents.length} agent${detail.agents.length === 1 ? '' : 's'}`),
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
    if (figures && figures.spending && figures.spending.length) parts.push(section('Spending', spendingOf(figures)))
    const places = placesOf(detail, run)
    if (places.length) parts.push(section('Environments', h('ul', { class: 'links', 'data-hmz': 'environments' }, places.map(([key, where, harness]) => h('li', {}, h('span', { class: 'mono' }, key), ` ${where}`, harness ? h('div', { class: 'dim' }, `harness on ${harness}`) : null)))))
    const clients = (standing.clients && standing.clients.clients) || []
    if (going && clients.length) {
      const me = held() ? held().me : ''
      parts.push(section('Frontends', h('ul', { class: 'links', 'data-hmz': 'frontends' }, clients.map((one) => h('li', {}, h('b', {}, one.name || one.client), h('span', { class: 'dim' }, ` ${one.kind}${one.client === me ? ' · this page' : ''}`))))))
    }
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

  /**
   * What a session is asked now that this page may answer: a question asked while its turn is
   * open, which says whose turn it is -- or, in a chat, whatever its person is asked, a
   * conversation having one session for it to be.
   */
  function askedIn(session) {
    const run = seen && seen.going && seen.going.live ? seen.going : null
    if (!run || !run.started || !session.includes('/') || session.startsWith('outworlder:')) return null
    const pending = (held().standing.pending && held().standing.pending.pending) || []
    return (
      pending.find((one) => {
        if (one.owner && one.owner !== held().me) return false
        const key = one.key || (run.records.findLast((record) => record.type === 'asked' && record.question === one.question) || {}).key
        return key ? key === session : chatting(run.started)
      }) || null
    )
  }

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
      if (next[0] !== 'epics' || !name || next[1] !== name || next[2] === 'exomyth') return false
      landing = false
      mode = modeOf(next)
      for (const one of ['head', 'panel-run', 'dock-composer']) drawn[one] = undefined
      draw()
      return true
    },
  }
}

/**
 * An epic's Exomyth, loaded once it is first opened: what leaves it, and never moving within
 * it to another view of the epic.
 */
function exomyth(root, name, query) {
  let leave = null
  let left = false
  import('./exomyth/view.js').then(
    (module) => {
      if (!left) leave = module.mount(root, name, query)
    },
    (error) => {
      console.error(error)
      if (!left) fill(root, h('div', { class: 'view' }, problem(`This view failed to open: ${error.message}`)))
    },
  )
  return {
    leave() {
      left = true
      if (leave) leave()
    },
    moved: () => false,
  }
}

/** Whether an epic is the built-in chat, read as a conversation rather than as a flow. */
function chatting(epic) {
  return flowName(epic.flow) === 'chat'
}

function modeOf(parts) {
  return {
    session: parts[2] === 'sessions' ? parts[3] || '' : '',
    focus: parts[2] === 'agents' ? parts[3] || '' : '',
    // A log: every agent's and person's lines, "" -- or one agent's, by its name, or one
    // person's, by the role they answer.
    log: parts[2] === 'logs' ? parts[3] || '' : null,
  }
}

/** Whether a view of an epic is a thread to read rather than its graph. */
function reading(mode) {
  return Boolean(mode.session) || mode.log !== null
}

/**
 * What the run has spent, model by model and kind by kind -- never one lump over the kinds -- in
 * an order that does not change, money beside the tokens where it is known, and a figure that is
 * only a floor marked as one, as the terminal interface's monitor says it.
 */
function spendingOf(figures) {
  const kinds = (figures.reckoning || []).map((one) => one.kind)
  const named = (kind) => (kind ? kind.replace(/_/g, ' ') : 'unsorted')
  return [
    h(
      'div',
      { class: 'table-wrap' },
      h(
        'table',
        { class: 'spending', 'data-hmz': 'spending' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Model'), kinds.map((kind) => h('th', { class: 'num' }, named(kind))), h('th', { class: 'num' }, 'Cost'), h('th', { class: 'num' }, 'Out/s'))),
        h(
          'tbody',
          {},
          figures.spending.map((one) =>
            h('tr', {}, h('td', { class: 'mono' }, one.model), kinds.map((kind) => h('td', { class: 'num' }, one.kinds[kind] ? Math.round(one.kinds[kind]) : '—')), h('td', { class: 'num' }, one.money || '—'), h('td', { class: 'num' }, one.rate)),
          ),
          h('tr', { class: 'whole' }, h('td', {}, 'All'), (figures.reckoning || []).map((one) => h('td', { class: 'num', title: one.whole ? '' : 'at least: a backend here does not count this kind' }, `${one.whole ? '' : '≥'}${Math.round(one.tokens)}`)), h('td'), h('td')),
        ),
      ),
    ),
  ]
}

/** Where each session of an epic works, and where its harness was put, as each opened. */
function placesOf(detail, run) {
  if (run) {
    return run.records.filter((one) => one.type === 'opened' && !one.person && (one.env || one.harness)).map((one) => [one.key, placed(one.env), one.harness || ''])
  }
  return sessionsOf(detail).filter((one) => one.harness).map((one) => [one.key, '', one.harness]).concat(detail.used.map((one) => [one.split('=')[0], one.split('=').slice(1).join('='), '']))
}

/** Where a session works, on one line as the terminal interface's monitor says it under the session: its role, then its kind, target and workdir. */
function placed(env) {
  return env ? [env.role, env.kind, env.target, env.workdir].filter(Boolean).join(' · ') : ''
}

/** The agents as a list rather than a graph: the working first, then in the flow's order. */
function listOf(model, epic, focus) {
  const base = hash(`/epics/${encodeURIComponent(epic)}`)
  const order = [...model.agents].sort((a, b) => Number(b.working) - Number(a.working))
  return order.map((agent) =>
    h(
      'section',
      { class: ['list-agent', agent.working && 'working', agent.name === focus && 'focused'], style: { '--lane': agent.color }, 'data-agent': agent.name },
      h(
        'a',
        { class: 'list-head', href: agent.person ? `${base}/logs/${encodeURIComponent(agent.name)}` : `${base}/agents/${encodeURIComponent(agent.name)}` },
        h('i', { class: 'swatch', 'aria-hidden': 'true' }),
        h('b', {}, agent.name),
        h('span', { class: 'mono dim' }, [agent.role !== agent.name && agent.role, agent.spec].filter(Boolean).join(' · ') || '—'),
        h('span', { class: 'list-state' }, agent.working ? h('span', { class: 'dot live', 'aria-hidden': 'true' }) : null, [agent.status, agent.tokens ? `${agent.tokens} tokens` : ''].filter(Boolean).join(' · ')),
      ),
      h(
        'ul',
        { class: 'links' },
        h('li', {}, h('a', { href: `${base}/logs/${encodeURIComponent(agent.name)}` }, '≡ log')),
        agent.sessions.map((one) => h('li', {}, h('a', { href: `${base}/sessions/${encodeURIComponent(one.key)}` }, one.working ? '● ' : '○ ', h('span', { class: 'mono' }, one.key)), h('span', { class: 'dim' }, ` ${one.turns.length} turn${one.turns.length === 1 ? '' : 's'}${one.about ? ` · ${one.about}` : ''}`))),
      ),
    ),
  )
}

/** A path, cut to one line, said in full on hover and copied from its menu. */
function pathed(path) {
  return menuOn(pathText(path), () => [{ head: path }, { label: 'Copy path', glyph: 'copy', act: () => copy(path, 'Path copied') }])
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
    h('dt', {}, 'written to'),
    h('dd', {}, pathed(detail.at)),
    h('dt', {}, 'workdir'),
    h('dd', {}, pathed(detail.workspace)),
    h('dt', {}, 'agents'),
    h('dd', {}, detail.agents.length ? detail.agents.map((one) => h('div', { class: 'mono' }, [one.name !== one.role && one.name, `${one.role}=${one.runs}`].filter(Boolean).join(' · '))) : '—'),
    h('dt', {}, 'envs'),
    h('dd', {}, detail.used.length ? detail.used.map((one) => h('div', { class: 'mono' }, one)) : '—'),
    h('dt', {}, 'params'),
    h('dd', {}, Object.keys(detail.params || {}).length ? h('pre', { class: 'block' }, JSON.stringify(detail.params, null, 2)) : '—'),
    h('dt', {}, 'budget'),
    h('dd', {}, budgeted(detail.budget)),
    h('dt', {}, 'sessions'),
    h('dd', {}, detail.sessions.length ? sessionsOf(detail).map((one) => h('div', {}, h('span', { class: 'mono' }, one.key), ` · ${one.backend}`, one.provider ? `@${one.provider}` : '', h('div', { class: 'dim mono' }, one.ident))) : 'none'),
    detail.picked_up ? [h('dt', {}, 'resumed from'), h('dd', {}, h('a', { href: hash(`/epics/${encodeURIComponent(detail.picked_up)}`) }, detail.picked_up))] : null,
    detail.profile_flow || detail.profile_environment
      ? [h('dt', {}, 'profiled'), h('dd', {}, [detail.profile_flow && 'flow', detail.profile_environment && 'environment'].filter(Boolean).join(' · '))]
      : null,
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
