// One epic, or one chat: the run going, as it happens, or one written down. `#/epics/<name>`
// draws an epic as a graph of its agents and who handed to whom; `/agents/<agent>` is the graph
// with that agent picked out; `/sessions/<key>` is one session's thread, as a chat is read;
// `/exomyth` is its timeline, drawn by views/exomyth. `#/chats/<id>` is a chat, which is no
// epic, read by `chat.get`. `#/live` is whichever run is going on a host: a workspace's own, or
// a chat's by its `slot`. A chat is only its conversation, as a chat app draws one: never a
// graph or its agents -- its box's button stops the turn open, never the chat -- and one folded
// away is carried on by saying something in it, on a host of its own, with what was said before
// it still above. Every line of a chat goes by `chat.say`; its box completes its harness's
// native input, the names hmz keeps and the flows, and serves those hmz keeps and the flows
// itself. Under
// the view, while the run goes, are the questions it waits on a person for and the box that
// says a line to it; beside it, a panel of what it is and was -- its figures, its budget, how it
// was set up, the flows it called -- with its board, its people and the side questions asked
// beside it.

import { asides, board, outworlders, question, saying } from '../acting.js'
import { settle } from '../asking/card.js'
import { call, exported, given, hash } from '../api.js'
import { go, renamed } from '../app.js'
import { confirming } from '../confirm.js'
import { acting, ago, badge, flowName, pathText, copier, empty, fill, h, headline, icon, lasting, problem, secondsOf, when } from '../dom.js'
import { agentLabel } from '../chips/agent.js'
import { modelFact } from '../chips/model.js'
import { PANES, paneOf, standing as standingSaid, stoppable, thousands, toggled, usageRows } from '../desk.js'
import { ask, chatAsk, follow } from '../held.js'
import { pieces, t } from '../i18n.js'
import { chatPermission } from '../chips/permission.js'
import { usageChip } from '../chips/usage.js'
import { harnessName, modelName } from '../names.js'
import { lostSaid, unplaced } from '../places.js'
import { composer as composed } from '../composer.js'
import { archiving, retitling } from '../chat-actions.js'
import { pathOf, worksIn } from '../chats.js'
import { chatting as isChat, live, lookedAt, markOf, read as markRead, sessionsOf, took, watch, written } from '../epic.js'
import { graph } from '../graph.js'
import { bar, choice, dragged, keep, kept, menu, section as heading, sidePanel, submenu, tabbed } from '../shell.js'
import { backedSaid, epicMenu, upload } from '../sidebar.js'
import { copy, menuOn, toast } from '../ui.js'
import { saidTraced, sayer, walked } from '../transcript.js'
import { completions, pathItems, pathParts, preferSaid, RESERVED, route, typing } from '../natives.js'
import { barButton, paneButtons } from './chatbar.js'
import { panelsOf, usedLine } from './envs/tree.js'

/** The most lines of a run going drawn at once: past it, the oldest go. */
const LINES = 3000

export function mount(root, { parts, query }) {
  if (parts[0] === 'epics' && parts[2] === 'exomyth') return exomyth(root, parts[1], query)
  let name = parts[0] === 'live' ? '' : parts[1]
  /** Which host the epic going is looked for on, for an epic not named. */
  const wanted = { workspace: query.get('workspace') || '', slot: query.get('slot') || '' }
  let mode = modeOf(parts)
  /** The buttons of the panes beside a chat, once its bar is drawn. */
  let panes = null
  // A chat's bar says which pane is open, each time its panel opens or shuts.
  const panel = sidePanel(t('the epic'), { told: () => panes && sayPanes() })
  // Not drawn until what is in front is known: a chat's is shut where an epic's is open, and
  // neither is opened only to be shut, nor with nothing in it where nothing is going.
  panel.node.classList.add('unsettled')
  const head = h('div', { class: 'bar-holder' })
  const main = h('div', { class: 'epic-main' })
  const dock = h('div', { class: 'dock', 'data-hmz': 'dock' })
  const view = h('div', { class: 'view view-epic' }, h('div', { class: 'work' }, head, main, dock), panel.node)
  fill(root, view)

  // A person is read by their log, as the terminal interface's monitor reads one; an agent is
  // picked out on the graph.
  const drawn_ = graph({ open: (who) => go(`/epics/${encodeURIComponent(name)}/${persons.has(who) ? 'logs' : 'agents'}/${encodeURIComponent(who)}`) })
  // What is said to the epic, and asked beside it, once it is known which workspace it is of.
  let say = null
  let sayTo = null
  let sayToKey = ''
  let btw = null
  const workspace = () => (seen && seen.workspace) || wanted.workspace
  /** The host the page follows, as what is asked of the epic going is asked of it. */
  const here = {
    get workspace() {
      return workspace()
    },
    get slot() {
      return (held() && held().slot) || ''
    },
  }
  /** The box that carries a chat folded away on, once there is one to carry on. */
  let carry = null
  /** Whether a line said in that box is carrying the chat on, until it is followed going. */
  let carryingOn = false
  /** The card of each question waiting, kept while it waits as it was asked of whom it was. */
  const cards = new Map()
  /** The cards of questions no longer waiting, each folded into what became of it until dismissed. */
  const settling = []
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
        // Its bar stands before anything is read of it, and where nothing could be: with the
        // sidebar's button and Ai-chan's, as every view's.
        region('head', ['reading'], () => fill(head, bar()))
        region('main', ['reading', String(error)], () => fill(main, h('div', { class: 'view-pad' }, error ? problem(error) : h('p', { class: 'loading', role: 'status' }, t('Opening…')))))
      } else {
        const starting = held && held.standing.run && held.standing.run.state === 'running'
        // A chat's host is on a slot of its own, which says it is one before it is written down.
        const chat = wanted.slot.startsWith('chat:')
        region('head', ['none', starting], () => fill(head, bar({ title: starting ? (chat ? t('Starting the chat…') : t('Starting the epic…')) : chat ? t('No chat is going') : t('No epic is going') })))
        region('main', ['none', starting, none], () =>
          fill(
            main,
            h(
              'div',
              { class: 'view-pad' },
              starting || !none
                ? h('p', { class: 'loading', role: 'status' }, chat ? t('Waiting for the chat to start…') : t('Waiting for the epic to be written down…'))
                : chat
                  ? empty(t('No chat is going here.'), t(' Start one, or open a chat from the sidebar.'), h('a', { class: 'btn primary', href: hash('/new/chat') }, t('New chat')))
                  : empty(t('No epic is going here.'), t(' Start one, or open an epic from the sidebar.'), h('a', { class: 'btn primary', href: hash('/new') }, t('New epic'))),
            ),
          ),
        )
      }
      region('panel-tabs', ['none'], () => {
        leaveEnv()
        fill(panel.body)
      })
      return
    }
    if (!name) {
      // The run going is named now: the address says which, and it is followed by name.
      name = detail.name
      renamed(pathOf(detail))
      stop()
      stop = watch(name, { workspace: detail.workspace, slot: wanted.slot }, told, { chat: isChat(detail) })
      return
    }
    const run = going && going.started ? going : null
    const chat = isChat(detail)
    if (!say) {
      say = saying(here)
      btw = asides(detail.workspace, detail.name, { chat })
    }
    // A chat is its one conversation, and is opened on it wherever it is opened, as a chat app
    // opens on one: the one going, or the last it opened, which a chat carried on goes on from.
    // Its address is the chat's alone: a chat has no session to name in it.
    const conversation = chat && (run ? run.records.find((one) => one.type === 'opened' && !one.person) : sessionsOf(detail).at(-1))
    if (conversation && mode.session !== conversation.key) mode = { session: conversation.key, focus: '', log: '' }
    const model = run ? live(held, run, detail) : written(detail, traced)
    const agentOfSession = mode.session ? mode.session.split('/')[0] : mode.log || ''
    persons = new Set(model.agents.filter((one) => one.person).map((one) => one.name))
    // A chat's panel is its own, shut until a pane of it is asked for, as a chat app's session opens.
    if (chat && !chatPanel) {
      chatPanel = true
      panel.keptAs('hmz-chat-panel', false)
    }
    panel.node.classList.remove('unsettled')
    // A chat's bar runs over its panel too, so a pane's button stays where it was pressed.
    view.classList.toggle('chat-view', chat)
    if (chat) followCatalogue(detail, run)
    drawHead(detail, run, chat)
    if (chat || reading(mode)) drawThread(detail, run)
    else drawGraph(detail, run, model)
    drawDock(detail, run)
    drawPanel(detail, run, model, chat ? '' : mode.focus || agentOfSession, chat)
  }

  // ------------------------------------------------------------------ the bar

  function drawHead(detail, run, chat) {
    const going = Boolean(run && run.live)
    const turn = going && held().standing.run ? held().standing.run.turn : ''
    const pending = going ? (held().standing.pending && held().standing.pending.pending) || [] : []
    const asked = pending.map((one) => `${one.run}:${one.question}`)
    // A question is looked at once it is waiting while this page is looked at.
    if (!document.hidden && document.hasFocus()) lookedAt(detail.name, asked)
    const how = chat ? (going ? 'running' : detail.how) : run ? (run.ended ? run.ended.how : run.state === 'stopping' ? 'stopping' : run.live ? 'running' : detail.how) : detail.how
    const state = markOf(how, { chat, turn, asked, epic: detail.name })
    const spent = run && held().figures && held().figures.tally && held().figures.tally[1] ? held().figures.tally[1].split(' · ')[0] : detail.spent ? detail.spent.money : ''
    const stopWaits = Date.now() - (stopsAsked.get(detail.name) || 0) < STOP_WAITS
    if (chat) return drawChatHead(detail, going)
    region('head', [mode, detail.name, detail.task, detail.flow, detail.picks_up, state, going, run && run.state, detail.backed, stopWaits], () => {
      const actions = []
      if (!chat && going && run.state === 'running') actions.push(stopWaits ? h('button', { class: 'btn danger', type: 'button', disabled: true }, t('Stopping…')) : confirming({ label: t('Stop'), ask: t('Stop this epic?'), yes: t('Stop'), no: t('Cancel'), busy: t('Stopping…'), held: true, act: () => stopping(detail.name) }))
      else if (!chat && going && run.state === 'stopping') actions.push(confirming({ label: t('Force stop'), ask: t('Close every session now?'), yes: t('Force stop'), no: t('Cancel'), busy: t('Stopping…'), act: () => ask(here, 'force') }))
      if (!going && detail.picks_up && !chat) actions.push(h('a', { class: 'btn primary', href: hash(`/new?flow=${encodeURIComponent(detail.flow)}&resume=${encodeURIComponent(detail.name)}`) }, icon('resume'), t('Resume')))
      if (!chat) actions.push(h('a', { class: 'icon-btn', href: hash(`/epics/${encodeURIComponent(detail.name)}/exomyth`), 'aria-label': t('Exomyth'), title: t('Exomyth'), 'data-hmz': 'exomyth-open' }, icon('chart')))
      if (!going) actions.push(h('button', { class: 'icon-btn', type: 'button', 'aria-label': t('Export'), title: t('Export'), onclick: () => exported(detail.name).catch((error) => toast(error.message)) }, icon('download')))
      // How each target last took it, said on hover; read again as the epic is.
      actions.push(h('button', { class: 'icon-btn', type: 'button', 'aria-label': t('Upload'), title: backedSaid(detail.backed) || t('Upload'), 'data-hmz': 'upload', onclick: uploading }, icon('up')))
      actions.push(copier(t('Copy link'), () => location.href))
      actions.push(panel.toggle)
      const base = hash(`/epics/${encodeURIComponent(detail.name)}`)
      const sub = [
        badge(state),
        h('span', { class: 'mono', title: detail.flow }, flowName(detail.flow)),
        h('span', { title: when(detail.began) }, t('began {ago}', { ago: ago(detail.began) })),
        h('span', { class: 'mono', 'data-hmz': 'clock' }),
      ]
      const where = mode.session || t('{name} log', { name: mode.log })
      const title = reading(mode) && !chat
        ? h('span', { class: 'crumbs' }, h('a', { href: base }, headline(detail.task)), h('span', { 'aria-hidden': 'true' }, ' / '), h('span', { class: 'mono' }, where))
        : headline(detail.task)
      fill(head, bar({ title, sub, actions }))
      const named = head.querySelector('.bar-title')
      named.title = detail.task
      menuOn(named, () => epicMenu({ ...detail, task: detail.task, held: going }))
    })
    // What moves on its own is said again in place, never drawing over a question being asked.
    const clock = head.querySelector('[data-hmz=clock]')
    if (clock) clock.textContent = [took(detail, run) && t('took {time}', { time: took(detail, run) }), spent].filter(Boolean).join(' · ')
  }

  /** Whether the panel is kept as a chat's, once the epic in front is known to be one. */
  let chatPanel = false
  /** The chat in front and whether it is going, as its bar's menus read them when they open. */
  let chatNow = null

  /** The panel of the chat's environment shown, or asked for: the one it opens on where never picked. */
  let envTab = ''

  /** Says, on the chat's bar, which pane is open and which the chat has now. */
  function sayPanes() {
    const env = chatNow && chatNow.going ? chatEnv() : null
    const has = new Set(env ? panelsOf(env).map((one) => one.key) : [])
    panes.said(paneOf({ open: !panel.node.hidden, tab, env: envTab }), (key) => key === 'details' || has.has(key), Boolean(chatNow && chatNow.going))
    const title = panel.body.querySelector('.pane-title')
    if (title) title.textContent = paneTitle()
  }

  /** Opens the panel beside the chat on one of its tabs, and for the environment on one of its panels. */
  function showPane(key, env = '') {
    tab = key
    if (env) envTab = env
    for (const one of Object.keys(drawn)) if (one.startsWith('panel')) drawn[one] = undefined
    panel.open()
    draw()
    if (key === 'env' && envFrame && envFrame.made) envFrame.made.show(envFrame.env, envTab)
  }

  /** What pressing a pane's button does: opens that pane, or shuts the panel where it is the one open. */
  function pressPane(key) {
    const then = toggled({ open: !panel.node.hidden, tab, env: envTab }, key)
    if (!then.open) return panel.set(false)
    showPane(then.tab, then.env)
  }

  /**
   * A chat's bar, as a chat app's session keeps its toolbar: its title as a button with its one
   * menu right after it, and at the far right a button for each pane beside the conversation,
   * then what else can be shown. Made once for the chat and said again in place, so that a menu
   * open on it stays open while the chat goes on; how the chat stands is said over its box.
   */
  function drawChatHead(detail, going) {
    chatNow = { detail, going }
    region('head', ['chat', detail.name], () => {
      const more = barButton('more', t('More options'), { 'data-hmz': 'chat-menu' })
      menu(more, chatMenu, { label: t('Chat menu') })
      const view = barButton('view', t('View options'), { 'data-hmz': 'chat-view' })
      menu(view, viewMenu, { align: 'end', label: t('View options') })
      panes = paneButtons(pressPane)
      // The bar ends as every view's does, with Ai-chan's button, after `View options`.
      const top = bar({ title: headline(detail.title), sub: [], actions: [panes.nodes, h('div', { class: 'menu-holder' }, view)] })
      top.classList.add('chat-bar')
      // The title is a button, as a session's is: pressed, it is edited where it stands.
      const named = top.querySelector('.bar-title')
      const title = h('button', { class: 'chat-title', type: 'button', 'data-hmz': 'chat-title', onclick: retitle })
      named.querySelector('h1').replaceChildren(title)
      named.querySelector('.bar-sub').replaceWith(h('div', { class: 'menu-holder' }, more))
      fill(head, top)
      menuOn(named, () => epicMenu({ ...chatNow.detail, held: chatNow.going }, { rename: retitle }))
      drawn['head-chat'] = undefined
    })
    region('head-chat', [detail.title, Boolean(detail.archived)], () => {
      const title = head.querySelector('.chat-title')
      // Said whole where pointed at, and as what pressing it does to whoever cannot see it.
      title.dataset.tip = detail.title
      title.setAttribute('aria-label', t('{title}, rename', { title: detail.title }))
      title.textContent = headline(detail.title)
      // An archived chat is still read, and is put back among the others from its bar.
      head.querySelector('[data-hmz=chat-unarchive]')?.remove()
      if (detail.archived) head.querySelector('.bar-actions').prepend(h('button', { class: 'btn small', type: 'button', 'data-hmz': 'chat-unarchive', onclick: () => archiving(chatNow.detail, false).catch((error) => toast(error.message, 6000)) }, t('Unarchive')))
    })
    sayPanes()
  }

  /** Renames the chat in front where its title stands on its bar. */
  function retitle() {
    retitling(head.querySelector('.chat-title'), chatNow.detail)
  }

  /**
   * What else a chat can show beside it: the side questions asked of it, which never reach it,
   * and its board while it keeps one.
   */
  function viewMenu(close) {
    const pane = (key, label, glyph) => {
      const shown = !panel.node.hidden && tab === key
      const item = choice({ label, glyph, chosen: shown, close, act: () => (shown ? panel.set(false) : showPane(key)) })
      item.dataset.hmz = `view-${key}`
      return item
    }
    const standing = held() ? held().standing : {}
    return [pane('aside', t('Side questions'), 'thread'), chatNow && chatNow.going && standing.board ? pane('board', t('Board'), 'menu') : null]
  }

  /** What the pane open beside a chat is headed by: the tab it is on, and for its environment the panel shown. */
  function paneTitle() {
    if (tab === 'env') return (PANES.find((one) => one.env === envTab) || { label: t('Environment') }).label
    return { epic: t('Details'), aside: t('Side questions'), board: t('Board') }[tab] || ''
  }

  /**
   * Asks the epic to stop, held asked until it says it is stopping, or a while: the bar of an
   * epic going is drawn again every second, so it gives Stop back once that while is up.
   */
  async function stopping(epic) {
    stopsAsked.set(epic, Date.now())
    try {
      await ask(here, 'stop')
    } catch (error) {
      stopsAsked.delete(epic)
      throw error
    }
  }

  /** Uploads the epic, the button busy until the daemon takes it. */
  async function uploading(event) {
    const button = event.currentTarget
    button.disabled = true
    button.setAttribute('aria-busy', 'true')
    try {
      await upload(seen.detail, { noticed: false })
    } finally {
      button.disabled = false
      button.removeAttribute('aria-busy')
    }
  }

  // ------------------------------------------------------------------ the graph

  function drawGraph(detail, run, model) {
    region('main-kind', ['graph', shape], () => {
      const switching = h('div', { class: 'segmented shape-switch', role: 'group', 'aria-label': t('Shape') }, [['graph', t('Graph')], ['list', t('List')]].map(([key, label]) => h('button', { type: 'button', 'aria-pressed': String(shape === key), onclick: () => {
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
      if (!traceError) return void main.append(h('div', { class: 'graph-note', role: 'status' }, h('span', {}, t('Reading handovers and turns from the epic’s logs…'))))
      const reading = h('button', { class: 'btn small', type: 'button' }, t('Read turns'))
      reading.addEventListener('click', readTrace)
      main.append(h('div', { class: 'graph-note', role: 'status' }, problem(traceError), reading))
    })
    drawn_.draw(model, mode.focus, detail.name)
    if (asking && !tracing && !traceError) readTrace()
  }

  async function readTrace() {
    tracing = true
    traceError = null
    draw()
    try {
      // What a chat said is read with the chat itself; an epic's, off its logs.
      traced = isChat(seen.detail) ? (await call('chat.get', { chat: name, trace: true })).trace : (await call('runs.trace', { name })).sessions
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
    return persons.has(mode.log) ? `person:${mode.log}` : `agent:${mode.log}`
  }

  function drawThread(detail, run) {
    const key = threadKey()
    region('main-kind', ['thread'], () => {
      box = walked(h('div', { class: 'thread', 'data-hmz': 'thread', role: 'log', 'aria-live': 'off' }))
      cut = h('p', { class: 'dim thread-cut', hidden: true }, isChat(detail) ? t('Only the last {count} lines are shown here; the chat keeps them all.', { count: LINES }) : t('Only its last {count} lines are drawn here; the epic keeps every one.', { count: LINES }))
      fill(main, h('div', { class: 'thread-scroll' }, h('div', { class: 'thread-column' }, cut, box)))
      saidFor = ''
      drawn['thread'] = undefined
      drawn['thread-ask'] = undefined
    })
    const scroller = main.querySelector('.thread-scroll')
    if (run) {
      // Another link's records start their numbers over: what was said is said again from the top.
      const chat = isChat(detail)
      const whose = JSON.stringify([key, run.number, held().epoch, chat])
      if (saidFor !== whose) {
        saidFor = whose
        saidBy = sayer(key, { chat })
        saidUpTo = -1
        fill(box)
        cut.hidden = true
      }
      // A chat carried on: what was said before, read out of the last session it opened then,
      // above what is said now.
      const before = chat && detail.earlier ? sessionsOf(detail)[detail.earlier - 1] : null
      if (before && !traced && !tracing && !traceError) readTrace()
      // A thread read at its end stays at its end as it grows, over it as under it.
      const stuck = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 60
      let added = false
      region('thread-before', [saidFor, before && before.key, Boolean(traced)], () => {
        box.querySelector(':scope > .thread-before')?.remove()
        const read = before && traced && traced.find((each) => each.key === before.traced)
        if (!read || !read.actions.length) return
        box.prepend(h('div', { class: 'thread-before', 'data-hmz': 'thread-before' }, saidTraced({ ...read, label: before.key, chat: true })))
        added = true
      })
      for (const record of run.records) {
        if (record.seq <= saidUpTo) continue
        saidUpTo = record.seq
        for (const line of saidBy(record)) {
          box.append(line)
          added = true
        }
        // What a person did in one of the run's environments, said dimly where it happened.
        if (record.type === 'env_used') {
          box.append(h('div', { class: 'said env-used', 'data-hmz': 'env-used' }, h('span', { class: 'g', 'aria-hidden': 'true' }, '·'), h('div', { class: 'body dim' }, usedLine(record, envsOf()))))
          added = true
        }
      }
      while (box.childElementCount > LINES) {
        box.firstElementChild.remove()
        cut.hidden = false
      }
      // Read here is read: a session's thread drawn is its lines seen.
      if (mode.session) markRead(detail.name, mode.session, run.records)
      if (!box.childElementCount) box.append(h('p', { class: 'dim thread-empty' }, t('Nothing said yet.')))
      else if (added) box.querySelector(':scope > .thread-empty')?.remove()
      // What a chat's agent stops to ask in a turn is asked at the end of its conversation,
      // its answers offered under the line that asks it and anything typed below answering it.
      const asking = chat && mode.session && run.live ? askedIn(mode.session) : null
      const asks = asking ? box.querySelector(`:scope > [data-question="${CSS.escape(String(asking.question))}"]`) : null
      region('thread-ask', [saidFor, asking, Boolean(asks)], () => {
        main.querySelector('.thread-ask')?.remove()
        if (!asking || !asking.options.length) return
        ;(asks || box).after(
          h(
            'div',
            { class: 'thread-ask row', 'data-hmz': 'thread-ask' },
            asking.options.map((option) =>
              acting(option, () => chatAsk(here, 'say', { text: option }), { kind: 'btn small', busy: t('Answering…') }),
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
      // The sessions the thread is of: one, or every one of an agent's.
      const sessions = sessionsOf(detail).filter((one) => (mode.session ? one.key === key : one.agent === mode.log))
      const read = traced ? sessions.map((one) => ({ ...(traced.find((each) => each.key === one.traced) || { actions: [] }), label: one.key, chat: isChat(detail) })).filter((one) => one.actions.length) : []
      fill(
        box,
        traceError
          ? problem(traceError)
          : !traced
            ? h('p', { class: 'loading', role: 'status' }, t('Reading its logs…'))
            : mode.session && !sessions.length
              ? empty(t('There is no such session in this epic.'), t(' Pick one of its sessions in the sidebar.'))
              : read.length
                ? saidTraced(...read)
                : h('p', { class: 'dim' }, persons.has(mode.log) ? t('A person’s log is kept while the epic is.') : t('Its logs held nothing said.')),
      )
      // Opened on what was said last, as one going is; read from there as far back as wanted.
      scroller.scrollTop = scroller.scrollHeight
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
    // asks is asked in its conversation, and answered by `chat.say` there, never on a card.
    const chat = isChat(detail)
    const carded = chat ? [] : pending
    region('dock-questions', [carded, me, clients], () => {
      const kept = new Set()
      const waiting = new Set(carded.map((one) => one.question))
      const shown = carded.map((one) => {
        const key = JSON.stringify([one.question, one.owner || '', me, one.text, one.options, Boolean(one.schema), (one.context || []).length, one.face ? one.face.hash || one.face : ''])
        if (!cards.has(key)) cards.set(key, question(here, one, me, clients))
        kept.add(key)
        return cards.get(key)
      })
      for (const [key, card] of [...cards]) {
        if (kept.has(key)) continue
        cards.delete(key)
        // A question no longer waiting folds into what became of it, and stays until dismissed;
        // one drawn anew, as another took it, is only drawn anew.
        const id = JSON.parse(key)[0]
        if (!waiting.has(id) && card.isConnected) settling.push({ card, question: id })
      }
      while (settling.length > SETTLED_KEPT) settling.shift()
      dock.querySelector('[data-hmz=waiting]')?.remove()
      if (shown.length) dock.prepend(h('div', { class: 'questions', 'data-hmz': 'waiting', role: 'region', 'aria-label': t('Waiting for you') }, shown))
    })
    // What became of each question gone is read off the records as they come.
    for (const one of settling) {
      if (one.done) continue
      const record = run ? run.records.findLast((each) => each.question === one.question && (each.type === 'answered' || each.type === 'withdrawn')) : null
      if (record && record.type === 'answered') settle(one.card, { answered: record, mine: record.client === me })
      else if (record) settle(one.card, { withdrawn: record.why })
      else if (!going) settle(one.card, { withdrawn: 'over' })
      else {
        // Gone, and what became of it not yet heard: it is answerable no more meanwhile.
        settle(one.card, { leaving: true })
        continue
      }
      one.done = true
    }
    const gone = settling.filter((one) => one.card.isConnected || !one.drawn)
    settling.splice(0, settling.length, ...gone)
    region('dock-settled', [settling.map((one) => one.question)], () => {
      dock.querySelector('[data-hmz=asked-settled]')?.remove()
      for (const one of settling) one.drawn = true
      if (!settling.length) return
      const list = h('div', { class: 'questions questions-settled', 'data-hmz': 'asked-settled', role: 'region', 'aria-label': t('Answered') }, settling.map((one) => one.card))
      const live = dock.querySelector('[data-hmz=waiting]')
      if (live) live.after(list)
      else dock.prepend(list)
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
        sayTo = saying(here, to, { asked: () => askedIn(to) })
        sayToKey = to
      }
    }
    // A chat folded away is carried on by saying something in it, as one going is.
    // Until the host carrying it on is followed, what was said is on its way: no second box.
    if (going) carryingOn = false
    const carried = !going && chat && detail.picks_up && !detail.held && !carryingOn
    if (carried && !carry) carry = carrying(detail)
    // Every line of a chat going is said to it, an answer to what it asks included.
    if (chat && going && !talk) talk = chatBox(detail, (text) => chatAsk(here, 'say', { text }), permits, true)
    talk?.model.again()
    // While a turn is open, the button of the box stops it: the chat stays, between turns.
    talk?.stops(going && stoppable(standing.run && standing.run.turn) ? () => chatAsk(here, 'stop') : null)
    const composer = going ? (chat ? talk.node : reading(mode) && sayToKey ? sayTo.node : say.node) : carried ? carry : null
    region('dock-composer', [going, carried, mode.session, mode.log, detail.picks_up, detail.foreign], () => {
      dock.querySelector('.composer, .dock-note')?.remove()
      drawn['dock-standing'] = undefined
      if (composer) dock.append(composer)
      // A chat is carried on by saying something in it, never by resuming it.
      else if (detail.picks_up && !chat)
        dock.append(h('p', { class: 'dock-note' }, pieces('Ended · {resume}', { resume: h('a', { href: hash(`/new?flow=${encodeURIComponent(detail.flow)}&resume=${encodeURIComponent(detail.name)}`) }, t('Resume')) })))
      // Imported from a workspace this machine has not got as it was: why it is not picked up here.
      else if (detail.foreign) dock.append(h('p', { class: 'dock-note', 'data-hmz': 'foreign' }, chat ? t('Imported · cannot be continued here: {why}', { why: detail.foreign }) : t('Imported · not resumable here: {why}', { why: detail.foreign })))
      // A chat that kept nothing to carry on from, as the terminal interface says it.
      else if (chat && !going && !detail.picks_up) dock.append(h('p', { class: 'dock-note', 'data-hmz': 'not-carried' }, t('This chat cannot be continued here.')))
    })
    if (chat) drawStanding(detail, going)
  }

  /**
   * That a chat failed, said in a quiet line over its box, and nothing of how it stands
   * otherwise; and what it has used, in the popup of the chip under its box while that is open.
   */
  function drawStanding(detail, going) {
    const state = markOf(going ? 'running' : detail.how, { chat: true, turn: going && held().standing.run ? held().standing.run.turn : '', asked: [], epic: detail.name })
    const said = standingSaid(state)
    region('dock-standing', [said, state], () => {
      dock.querySelector('[data-hmz=chat-status]')?.remove()
      if (!said) return
      const line = h('p', { class: ['chat-status', `chat-${state}`], role: 'status', 'data-hmz': 'chat-status', 'data-state': state }, said)
      const box = dock.querySelector('.composer, .dock-note')
      if (box) box.before(line)
      else dock.append(line)
    })
    for (const chip of usages) chip.read()
  }

  // ------------------------------------------------------------------ the panel beside it

  function drawPanel(detail, run, model, focus, chat) {
    const going = Boolean(run && run.live)
    const standing = held() ? held().standing : {}
    const items = going && standing.board ? standing.board.items : null
    // A chat's person is whoever is typing to it: nobody else to hand it to.
    const people = going && !chat ? run.started.outworlders || [] : []
    const env = chat && going ? chatEnv() : null
    // A chat's panel says what it is in a chat's words: nothing in it is called an epic.
    const tabs = [['epic', chat ? t('Details') : t('Epic')], ['aside', chat ? t('Side questions') : t('Aside')], items ? ['board', t('Board')] : null, people.length ? ['people', t('People')] : null, env ? ['env', t('Environment')] : null].filter(Boolean)
    if (!tabs.some(([key]) => key === tab)) tab = 'epic'
    panel.node.setAttribute('aria-label', chat ? t('the chat') : t('the epic'))
    // The environment is worked in, which wants the room an editor does.
    panel.node.classList.toggle('envs-wide', tab === 'env')
    panel.node.classList.toggle('chat-pane', chat)
    // Left once another tab is picked; kept, and put back, while only the row of tabs is drawn again.
    if (tab !== 'env') leaveEnv()
    region('panel-tabs', [tabs, tab], () => {
      fill(
        panel.body,
        // The top row of a wide window, beside the view; on a narrow one, a sheet's head inside it.
        // A chat's pane is picked on its bar, as a session's is: it is headed by its name alone.
        dragged(
          chat
            ? h('h2', { class: 'pane-title', 'data-hmz': 'pane-title' }, paneTitle())
            : tabbed(tabs, tab, (key) => {
                tab = key
                for (const one of Object.keys(drawn)) if (one.startsWith('panel')) drawn[one] = undefined
                draw()
              }),
          'deep',
          'wide',
        ),
        h('div', { class: 'panel-pane' }),
      )
      for (const one of Object.keys(drawn)) if (one.startsWith('panel-') && one !== 'panel-tabs') drawn[one] = undefined
    })
    const pane = panel.body.querySelector('.panel-pane')
    if (tab === 'epic') {
      const figures = held() && held().figures
      region('panel-run', [model.agents, model.handovers, focus, going, detail, run && run.ended, figures && figures.tally, figures && figures.lasting, standing.usage, standing.calls, run && run.offset, Math.floor(Date.now() / 1000)], () =>
        fill(pane, overview(detail, run, model, focus, going, figures, standing, chat)),
      )
    } else if (tab === 'aside') {
      // Every session of the epic, under the agent that opened it: one the runs still hold asked
      // as it is, an earlier epic's carried on from where that epic kept it.
      const opened = model.agents.filter((one) => !one.person && one.sessions.length).map((one) => ({ name: one.name, role: one.role, sessions: one.sessions.map((session) => ({ key: session.key, about: session.about || '' })) }))
      region('panel-aside', [opened], () => {
        btw.sessions(opened)
        fill(pane, h('p', { class: 'dim' }, chat ? t('Ask something on the side. Side questions never reach this chat.') : t('Side questions never reach the epic.')), btw.node)
      })
    } else if (tab === 'board') {
      region('panel-board', [items], () => fill(pane, board(here, items || [])))
    } else if (tab === 'env') {
      const host = { workspace: here.workspace, slot: here.slot }
      region('panel-env', [host], () => {
        if (envFrame && envFrame.key === JSON.stringify(host)) {
          fill(pane, envFrame.node)
          return
        }
        leaveEnv()
        const into = h('div', { class: 'envs-holder' })
        fill(pane, into)
        const mine = envMounting
        import('./envs.js').then(
          (module) => {
            if (mine !== envMounting) return
            envFrame = { key: JSON.stringify(host), node: into, env: env.id }
            envFrame.made = module.frame(into, {
              follow: (told) => follow(host, (state) => told(state, '')),
              env: env.id,
              tab: envTab,
              // The bar says which of its panels is shown, wherever it was picked.
              moved: (now) => {
                if (envFrame) envFrame.env = now.env
                envTab = now.tab || envTab
                if (panes) sayPanes()
              },
              compact: true,
              full: (id, panel) => envsAddress(host, { env: id, tab: panel }),
            })
          },
          (error) => {
            console.error(error)
            if (mine === envMounting) fill(pane, problem(t('The environment failed to open: {why}', { why: error.message })))
          },
        )
      })
    } else if (tab === 'people') {
      const clients = standing.clients && standing.clients.clients
      region('panel-people', [people, standing.claims, standing.away, held().me, clients], () =>
        fill(pane, outworlders(here, people, { claims: (standing.claims && standing.claims.claims) || {}, away: standing.away, me: held().me, clients })),
      )
    }
  }

  function overview(detail, run, model, focus, going, figures, standing, chat) {
    const agent = model.agents.find((one) => one.name === focus)
    const base = hash(`/epics/${encodeURIComponent(detail.name)}`)
    const parts = []
    if (agent) {
      parts.push(
        section(
          agent.name,
          h('div', { class: 'focus', style: { '--lane': agent.color }, 'data-hmz': 'focus' },
            h('div', { class: 'dim', title: agent.spec || null }, [agent.role !== agent.name && agent.role, agent.said].filter(Boolean).join(' · ') || '—'),
            h('div', {}, [agent.status, agent.turns !== null && agent.turns !== undefined ? t('{n} turns', { n: agent.turns }) : '', agent.tokens ? t('{tokens} tokens', { tokens: agent.tokens }) : ''].filter(Boolean).join(' · ')),
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
      parts.push(section(chat ? t('Usage') : t('Figures'), h('div', { class: 'tiles' }, tile(t('time'), elapsed, going ? t('elapsed') : t('total')), spentTile(lines[1] || ''), tile(t('tokens'), lines[0] ? '' : '—', lines[0] || ''), budgetTile(standing.usage))))
    } else {
      const spent = detail.spent
      parts.push(
        section(
          chat ? t('Usage') : t('Figures'),
          h(
            'div',
            { class: 'tiles' },
            tile(t('spent'), spent ? spent.money || '—' : '—', ''),
            tile(t('output tokens'), spent ? spent.tokens : '—', ''),
            tile(t('took'), took(detail, null) || '—', spent && spent.worked ? t('{time} of it working', { time: spent.worked }) : ''),
            // A chat is one conversation: it counts no sessions and no agents.
            chat ? null : tile(t('sessions'), String(detail.sessions.length), t('{n} agents', { n: detail.agents.length })),
          ),
        ),
      )
    }
    parts.push(section(chat ? t('First message') : t('Task'), detail.task.length > 400 ? h('details', {}, h('summary', {}, detail.task.slice(0, 240), '…'), h('pre', { class: 'block' }, detail.task)) : h('p', { class: 'prose' }, detail.task)))
    // One agent, in one session, hands to nobody and calls no flow.
    if (!chat) parts.push(
      section(
        t('Handovers'),
        model.handovers.length
          ? h('ul', { class: 'handovers' }, model.handovers.map((one) => h('li', { class: model.latest && model.latest[0] === one.from && model.latest[1] === one.to ? 'latest' : '' }, `${one.from} → ${one.to} ×${one.count}`)))
          : h('p', { class: 'dim' }, run ? t('Nobody has handed over yet.') : !traced ? traceError ? t('Its turns could not be read.') : t('Reading its turns…') : traced.length ? t('Nobody handed over.') : t('Its logs held no turn to read.')),
      ),
    )
    if (figures && figures.spending && figures.spending.length) parts.push(section(t('Spending'), spendingOf(figures)))
    const places = placesOf(detail, run, chat)
    // While it goes, where each session works opens that environment, and every one is a click away.
    const envs = going ? envsOf() : []
    const envsAt = (query) => envsAddress({ workspace: here.workspace, slot: here.slot }, query || {})
    const placeOf = (key, where, harness, role, workdir) => {
      // Its role's environment that works where it does, else its role's latest at the top.
      const roles = role ? envs.filter((one) => one.role === role).sort((a, b) => (b.run || 0) - (a.run || 0)) : []
      const env = (workdir && roles.find((one) => one.workdir === workdir)) || roles.find((one) => !one.parent) || null
      // What it is called and runs on is said whole, and is the link; its path stands under
      // them on a line of its own, the only thing cut short.
      return h(
        'li',
        {},
        // A chat's is the chat's own: no session is named before it.
        key ? [h('span', { class: 'mono' }, key), ' '] : null,
        env ? h('a', { href: envsAt({ env: env.id }), 'data-hmz': 'env-link', title: t('Open this environment') }, where) : where,
        workdir ? h('div', {}, pathed(workdir)) : null,
        harness ? h('div', { class: 'dim' }, t('harness on {where}', { where: harness })) : null,
      )
    }
    if (places.length || envs.length) {
      parts.push(
        section(
          t('Environments'),
          places.length ? h('ul', { class: 'links', 'data-hmz': 'environments' }, places.map(([key, where, harness, role, workdir]) => placeOf(key, where, harness, role, workdir))) : null,
          envs.length ? h('p', {}, h('a', { href: envsAt(null), 'data-hmz': 'envs-open' }, envs.length === 1 ? t('Open its environment') : t('Open its {n} environments', { n: envs.length }))) : null,
        ),
      )
    }
    const used = run ? run.records.filter((one) => one.type === 'env_used').slice(-8) : []
    if (used.length) parts.push(section(t('Done in its environments'), h('ul', { class: 'links dim', 'data-hmz': 'env-used-list' }, used.map((one) => h('li', {}, usedLine(one, envs.length ? envs : envsOf()))))))
    const clients = (standing.clients && standing.clients.clients) || []
    if (going && clients.length) {
      const me = held() ? held().me : ''
      parts.push(section(chat ? t('Open in') : t('Frontends'), h('ul', { class: 'links', 'data-hmz': 'frontends' }, clients.map((one) => h('li', {}, h('b', {}, one.name || one.client), h('span', { class: 'dim' }, ` ${one.client === me ? t('{kind} · this page', { kind: one.kind }) : one.kind}`))))))
    }
    const calls = (standing.calls && standing.calls.calls) || []
    if (!chat && run && calls.length) {
      const offset = run.offset
      // The flow the epic was started with is the first deep: on the text's edge, what it called a step in.
      parts.push(section(t('Running flows'), h('ul', { class: 'tree' }, calls.map((call) => h('li', { style: { marginLeft: `calc(${call.depth - 1} * var(--indent))` } }, h('b', {}, call.name), ' ', h('span', { class: 'dim' }, offset === null ? '' : lasting(Date.now() / 1000 - (call.since + offset))))))))
    } else if (!chat && detail.calls.length) {
      parts.push(section(t('Called flows'), tree(detail.calls)))
    }
    parts.push(section(chat ? t('About this chat') : t('Setup'), facts(detail, chat)))
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
        return key ? key === session : isChat(run.started)
      }) || null
    )
  }

  function held() {
    return seen && seen.held
  }

  /** The environments the host has open, as its `envs` snapshot lists them. */
  function envsOf() {
    const standing = held() ? held().standing : {}
    return (standing.envs && standing.envs.envs) || []
  }

  /** A chat's own environment, its workspace -- or the first it has -- to open beside it. */
  function chatEnv() {
    const envs = envsOf()
    return envs.find((one) => one.role === 'workspace' && !one.parent && one.open !== false) || envs.find((one) => !one.parent && one.open !== false) || null
  }

  /** The environment opened in the panel, and which opening of it is the latest. */
  let envFrame = null
  let envMounting = 0

  function leaveEnv() {
    envMounting++
    if (envFrame && envFrame.made) envFrame.made.leave()
    envFrame = null
  }

  /**
   * The box a chat folded away is carried on in: what is said in it starts the chat again on a
   * host of its own, going on in the same chat, named by its id, with the agent it had and the
   * preference set for it, and the page follows that host.
   */
  function carrying(detail) {
    const box = chatBox(detail, async (text) => {
      // A folder that went is said as the forms that start in one say it, with no other to pick.
      const started = await call('chat.start', { workspace: detail.workspace, slot: 'chat:', task: text, resume: detail.name, prefer: preferring, permission: box.permission.picked() }).catch((error) => {
        throw unplaced(error, detail.workspace, lostSaid)
      })
      carry = null
      // Its box is drawn no more: its chip is told nothing more of what the chat spends.
      usages.delete(box.usage)
      carryingOn = true
      stop()
      stop = watch(name, { workspace: detail.workspace, slot: started.slot }, told, { chat: true })
      // No host holds it: the permission picked is kept for the chat to be carried on with.
    }, () => null)
    return box.node
  }

  // ------------------------------------------------------------------ a chat's native input

  /** The chat's catalogue, as its host last said it, and the host it was read off. */
  let catalogue = null
  let catalogueOf = ''
  /** How many turns of the chat had ended when its catalogue was read: read again after each. */
  let catalogueAt = -1
  /** The flows on offer in the workspace, where no host holds the chat to say its catalogue. */
  let flowsHere = null
  /** The preference the workspace's settings give, which a chat no host holds has with none of its own. */
  let preferHere = 'native'
  /** The preference a chat folded away is carried on with, picked before it is carried on. */
  let preferring = null
  /** The box a chat going is talked to in. */
  let talk = null
  /** What `@` listed, by the directory listed, until the catalogue is read again. */
  const pathsListed = new Map()

  /**
   * Reads the catalogue again where the host changed or a turn ended since it was read; the
   * workspace's flows and its preference are read once besides, for a chat no host holds or one
   * not yet answered.
   */
  function followCatalogue(detail, run) {
    if (!flowsHere) {
      flowsHere = []
      call('flows.list', { workspace: detail.workspace }).then(
        (found) => {
          flowsHere = found.flows.map((one) => ({ sigil: '$', name: one.name, about: one.about || '', how: '', source: 'flow' }))
        },
        () => {},
      )
      call('settings.get', { workspace: detail.workspace }).then(
        (settings) => {
          preferHere = settings.prefer
          draw()
        },
        () => {},
      )
    }
    const slot = here.slot
    if (!slot || !run || !run.live) return
    // The last turn ended, by its record, found from the end where it is near.
    const ended = run.records.findLast((one) => one.type === 'event' && one.kind === 'ends')
    const ends = ended ? ended.seq : 0
    if (catalogueOf === slot && catalogueAt === ends) return
    catalogueOf = slot
    catalogueAt = ends
    readCatalogue().catch(() => {})
  }

  /** Reads the chat's catalogue off its host, the preference it says taking over one picked here. */
  async function readCatalogue() {
    const slot = here.slot
    const read = await chatAsk(here, 'commands')
    if (here.slot !== slot) return
    catalogue = { ...read, slot }
    preferring = null
    talk?.permission.host(read)
    pathsListed.clear()
    draw()
  }

  /** What a chat's lines are read against: its catalogue, or, with none, what hmz and the workspace offer. */
  function entries() {
    if (catalogue && catalogue.slot === here.slot) return catalogue.entries
    return [...RESERVED.map((name) => ({ sigil: '/', name, about: '', how: '', source: 'hmz' })), ...(flowsHere || [])]
  }

  /** The chat's preference, and where it comes from. */
  function preference(detail) {
    if (preferring) return { prefer: preferring, from: 'chat' }
    if (catalogue && catalogue.slot === here.slot) return { prefer: catalogue.prefer, from: catalogue.prefer_from }
    return detail.prefer ? { prefer: detail.prefer, from: 'chat' } : { prefer: preferHere, from: 'settings' }
  }

  /** Sets the chat's preference: on its host while it goes, else for when it is carried on. */
  async function prefers(detail, prefer) {
    if (seen && seen.going && seen.going.live && here.slot) {
      await chatAsk(here, 'set', { prefer })
      catalogueAt = -1
      followCatalogue(detail, seen.going)
    } else preferring = prefer
    draw()
  }

  /** Sets the permission of the chat going on its host, which is then asked what it holds. */
  async function permits(permission) {
    await chatAsk(here, 'set', { permission })
    readCatalogue().catch(() => {})
  }

  /**
   * What a chat's menu holds: what its right click offers, save opening the chat that is open;
   * its environment, where its host has one; and what a `$` name that is both a skill and a flow
   * does, with a mark on the one in force and where that comes from.
   */
  function chatMenu(close) {
    const { detail, going } = chatNow
    const env = going ? chatEnv() : null
    const base = hash(pathOf(detail))
    const made = []
    for (const one of epicMenu({ ...detail, held: going }, { rename: retitle })) {
      if (!one || one.head || one.href === base) continue
      if (one === '-') {
        if (made.length && made.at(-1).tagName !== 'HR') made.push(h('hr'))
        continue
      }
      const item = choice({ ...one, close })
      if (one.title) item.title = one.title
      if (one.danger) item.classList.add('danger')
      made.push(item)
    }
    if (made.length && made.at(-1).tagName !== 'HR') made.push(h('hr'))
    // A chat's workspace, opened beside it: its files, a terminal in it and its changes.
    if (env) {
      const opens = choice({ label: t('Environment'), glyph: 'folder', close, act: () => showPane('env') })
      opens.dataset.hmz = 'env-open'
      made.push(opens)
    }
    const { prefer, from } = preference(detail)
    const picks = (key, label, about) => {
      const item = choice({ label, about, chosen: prefer === key, close, act: () => prefer !== key && prefers(detail, key).catch((error) => toast(error.message)) })
      item.dataset.prefer = key
      item.setAttribute('role', 'menuitemradio')
      item.setAttribute('aria-checked', String(prefer === key))
      return item
    }
    made.push(
      submenu({
        label: t('Skill or flow'),
        about: preferSaid(prefer, from),
        glyph: 'flows',
        hmz: 'prefer',
        items: () => [
          heading(t('When a $ name is both')),
          picks('native', t('Use the skill'), t('The skill your CLI has by that name')),
          picks('flow', t('Start the flow'), t('The flow by that name')),
          h('p', { class: 'popover-note', 'data-hmz': 'prefer-from' }, from === 'chat' ? t('Set for this chat') : t('From settings')),
        ],
      }),
    )
    return made
  }

  /** What the word at the caret could become: the catalogue's entries, and for `@` the workspace's paths. */
  async function completing(detail, text, caret) {
    const typed = typing(text, caret)
    if (!typed) return null
    const groups = completions(entries(), typed, preference(detail).prefer)
    // Where the chat works: its folder, or the worktree made for it there.
    const root = detail.workdir || detail.workspace
    if (typed.sigil === '@' && root) {
      const { dir, base } = pathParts(typed.word)
      // Names starting with `.` are listed only once a `.` is typed, as a shell completes them.
      const hidden = base.startsWith('.')
      const key = `${hidden}\n${dir}`
      if (!pathsListed.has(key)) pathsListed.set(key, call('paths.list', { at: `${root.replace(/\/+$/, '')}/${dir}`, files: true, hidden }).then((read) => read.entries, () => []))
      const items = pathItems(dir, base, await pathsListed.get(key))
      if (items.length) groups.unshift({ source: 'path', label: t('Files'), items })
    }
    return { from: typed.from, to: typed.to, groups }
  }

  /** The Usage chips of the chat's boxes, each told what the chat has spent as it is read. */
  const usages = new Set()

  /**
   * The box under a chat: it completes the chat's native input, serves the names hmz keeps and
   * starts the flows a line names, and says every other line as `say` does.
   */
  function chatBox(first, say, sets, going = false) {
    // The chat as it was read last, which the box outlives a reading of.
    const now = () => (seen && seen.detail) || first
    const model = modelFact({
      of: () => now().agents?.[0]?.runs || '',
      fresh: () => hash(`/new/chat?${new URLSearchParams(given({ workspace: now().workspace }))}`),
      // A chat going takes its CLI's own `/model` and `/effort`; one folded away is said only what carries it on.
      takes: (name) => going && entries().some((one) => one.source === 'native' && one.sigil === '/' && one.name === name && one.how === 'call'),
      say: (line) => say(line).catch((error) => toast(error.message)),
    })
    const permission = chatPermission(first, sets)
    if (catalogue && catalogue.slot === here.slot) permission.host(catalogue)
    // What the chat has used, as a chat app keeps a ring there: the ring alone, and its popup
    // says what was used (Section 3.6.6.17 of protocol/web.md).
    const usage = usageChip({
      hmz: 'chat-usage',
      tip: t('What this chat has used'),
      chat: () => usageRows(seen && seen.going ? held().figures : null, now().spent),
      workspace: () => now().workspace || '',
    })
    usages.add(usage)
    const box = composed({
      // Under the box, at its right: how the chat runs. Where it runs is settled once it has begun.
      desk: { add: true, right: [model.node, permission.node, usage.node] },
      placeholder: t('Reply…'),
      label: t('What to say'),
      complete: (text, caret) => completing(now(), text, caret),
      submit: async (text) => {
        const detail = now()
        // A `$` line is read against the catalogue, which a chat going is asked for where it
        // has not answered yet: said unread, a flow it names would be refused.
        const live = seen && seen.going && seen.going.live && here.slot
        if (live && !(catalogue && catalogue.slot === here.slot) && /^\s*\$/.test(text)) await readCatalogue().catch(() => {})
        const line = route(text, entries(), preference(detail).prefer)
        if (line.kind === 'reserved') return hmzServes(detail, line.name, line.rest)
        if (line.kind === 'flow') return startFlow(detail.workspace, line.name, line.rest)
        return say(text)
      },
    })
    // What the box takes besides a message is offered by its Add menu; said, besides, to
    // whoever cannot see that menu.
    box.text.setAttribute('aria-description', INPUT_HINT)
    box.node.dataset.hmz = 'say'
    return Object.assign(box, { model, permission, usage })
  }

  /** What the page does for a name hmz keeps, as Section 8.9.8 of protocol/core.md has it done. */
  async function hmzServes(detail, named, rest) {
    const at = given({ workspace: detail.workspace })
    switch (named) {
      case 'clear':
      case 'chat':
        return go(`/new/chat?${new URLSearchParams(at)}`)
      case 'exit':
      case 'quit':
        return go('/new')
      case 'resume':
      case 'epics':
        return go(`/search?${new URLSearchParams(at)}`)
      case 'settings':
        return go('/settings')
      case 'prefer': {
        const wanted = rest || (preference(detail).prefer === 'flow' ? 'native' : 'flow')
        if (wanted !== 'native' && wanted !== 'flow') throw new Error(t('/prefer takes native or flow, not {value}', { value: wanted }))
        return prefers(detail, wanted)
      }
      case 'btw': {
        // A side question is asked beside the chat, in its panel, never in it.
        showPane('aside')
        const asking = panel.body.querySelector('.aside textarea')
        if (asking) {
          asking.value = rest
          asking.dispatchEvent(new Event('input'))
          asking.focus()
          if (rest) asking.form.requestSubmit()
        }
        return
      }
      default:
        throw new Error(t('/{name} is not served here', { name: named }))
    }
  }

  /**
   * Starts a flow a chat's line names, as New › Flow starts it, set up as this workspace last
   * set that flow up; with no task, New › Flow is opened on it to be told one.
   */
  async function startFlow(workspace, flow, task) {
    if (!flow || !task) return go(`/new?${new URLSearchParams({ ...given({ workspace }), ...(flow ? { flow } : {}) })}`)
    const { remembered } = await call('flows.get', { name: flow, workspace })
    const started = await ask(workspace, 'start', { ...remembered, flow, task })
    go(`/live?${new URLSearchParams(given({ workspace: started.workspace, slot: started.slot }))}`)
  }

  /** Whether the chat of this name was looked for, for an address of an epic that names none. */
  let looked = false

  function told(now) {
    seen = now
    // A chat an earlier hmz kept as an epic is a chat now, by the name it had: an address
    // kept of that epic -- a pin, a notice, a bookmark -- opens the chat (Section 3.5.20.3).
    if (parts[0] === 'epics' && name && !now.detail && now.error && !looked) {
      looked = true
      call('chat.get', { chat: name }).then(
        () => location.replace(hash(`/chats/${encodeURIComponent(name)}`)),
        () => {},
      )
    }
    draw()
  }

  let stop = () => {}
  stop = watch(name, wanted, told, { chat: parts[0] === 'chats' })
  // The clocks a run going is drawn with move on their own between records.
  const ticking = setInterval(() => {
    if (seen && seen.going && seen.going.live) draw()
  }, 1000)
  // Looked at again, the questions waiting are looked at.
  addEventListener('focus', draw)
  document.addEventListener('visibilitychange', draw)

  return {
    leave() {
      stop()
      leaveEnv()
      clearInterval(ticking)
      removeEventListener('focus', draw)
      document.removeEventListener('visibilitychange', draw)
    },
    /** Moves to another part of the same run without drawing it all again. */
    moved({ parts: next }) {
      const at = seen && seen.detail && isChat(seen.detail) ? 'chats' : 'epics'
      if (next[0] !== at || !name || next[1] !== name || next[2] === 'exomyth') return false
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
      if (!left) fill(root, h('div', { class: 'view' }, problem(t('This view failed to open: {why}', { why: error.message }))))
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

/** The address of the Environments view of a host's envs, `#/envs/live?workspace=…&slot=…&env=…&tab=…`. */
function envsAddress(host, { env = '', tab = '' } = {}) {
  const query = new URLSearchParams(Object.entries({ workspace: host.workspace, slot: host.slot, env, tab }).filter(([, value]) => value))
  return hash(`/envs/live?${query}`)
}

/** The kinds of token a backend counts, as the head of a column says each. */
const SPENT = {
  input: t('input'),
  output: t('output'),
  cache_read: t('cache read'),
  cache_write: t('cache write'),
  reasoning: t('reasoning'),
}

/** What a chat's box takes besides a message, as its tip says it. */
const INPUT_HINT = t('/ for commands · $ for skills and flows · @ for files · ! for shell')

/** How long Stop stays asked, waiting for the epic to say it is stopping. */
const STOP_WAITS = 10000

/** How many questions gone are kept folded under those waiting, the latest last. */
const SETTLED_KEPT = 3

/**
 * When Stop was last asked of each epic, by its name: kept beyond one drawing of its page, so
 * that the bar drawn again for another view of it before it says it is stopping asks no more.
 */
const stopsAsked = new Map()

function modeOf(parts) {
  return {
    session: parts[2] === 'sessions' ? parts[3] || '' : '',
    focus: parts[2] === 'agents' ? parts[3] || '' : '',
    // A log: one agent's lines, by its name, or one person's, by the role they answer.
    log: parts[2] === 'logs' ? parts[3] || '' : '',
  }
}

/** Whether a view of an epic is a thread to read rather than its graph. */
function reading(mode) {
  return Boolean(mode.session || mode.log)
}

/**
 * What the run has spent, model by model and kind by kind -- never one lump over the kinds -- in
 * an order that does not change, money beside the tokens where it is known, and a figure that is
 * only a floor marked as one, as the terminal interface's monitor says it. A column for each
 * kind is all a panel has the room for: a model's name stands whole on a row of its own over
 * its figures, and a count is cut short as the figures over the panel are, said exactly where
 * it is pointed at.
 */
function spendingOf(figures) {
  const reckoned = figures.reckoning || []
  const named = (kind) => (kind ? SPENT[kind] || kind.replace(/_/g, ' ') : t('unsorted'))
  const over = (name) => h('tr', { class: 'spending-of' }, h('td', { colspan: reckoned.length + 2, title: name }, modelName(name)))
  const count = (tokens, floor = false) => h('td', { class: 'num', title: floor ? t('at least {count}: a backend here does not count this kind', { count: Math.round(tokens) }) : String(Math.round(tokens)) }, `${floor ? '≥' : ''}${thousands(tokens)}`)
  return [
    h(
      'div',
      { class: 'table-wrap' },
      h(
        'table',
        { class: 'spending', 'data-hmz': 'spending' },
        h('thead', {}, h('tr', {}, reckoned.map((one) => h('th', { class: 'num' }, named(one.kind))), h('th', { class: 'num' }, t('Cost')), h('th', { class: 'num' }, t('Out/s')))),
        h(
          'tbody',
          {},
          figures.spending.map((one) => [
            over(one.model),
            h('tr', {}, reckoned.map(({ kind }) => (one.kinds[kind] ? count(one.kinds[kind]) : h('td', { class: 'num' }, '—'))), h('td', { class: 'num' }, one.money || '—'), h('td', { class: 'num' }, one.rate)),
          ]),
          h('tr', { class: 'whole spending-of' }, h('td', { colspan: reckoned.length + 2 }, t('All'))),
          h('tr', {}, reckoned.map((one) => count(one.tokens, !one.whole)), h('td'), h('td')),
        ),
      ),
    ),
  ]
}

/**
 * Where each session of an epic works, and where its harness was put, as each opened. A chat's
 * are said by where it works alone, each once: it names no session and no role.
 */
function placesOf(detail, run, chat = false) {
  const places = run
    ? run.records.filter((one) => one.type === 'opened' && !one.person && (one.env || one.harness)).map((one) => [one.key, placed(one.env, chat), one.harness || '', (one.env && one.env.role) || '', (one.env && one.env.workdir) || ''])
    : sessionsOf(detail).filter((one) => one.harness).map((one) => [one.key, '', one.harness]).concat(detail.used.map((one) => [one.split('=')[0], one.split('=').slice(1).join('='), '']))
  if (!chat) return places
  const said = new Set()
  return places.map(([, ...place]) => ['', ...place]).filter((place) => !said.has(JSON.stringify(place)) && said.add(JSON.stringify(place)))
}

/** Where a session works, as the terminal interface's monitor says it under the session: its role, then its kind and target; a chat's by its kind and target alone. Its workdir is said after them, as a path is. */
function placed(env, chat = false) {
  return env ? [!chat && env.role, env.kind, env.target].filter(Boolean).join(' · ') : ''
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
        h('span', { class: 'dim', title: agent.spec || null }, [agent.role !== agent.name && agent.role, agent.said].filter(Boolean).join(' · ') || '—'),
        h('span', { class: 'list-state' }, agent.working ? h('span', { class: 'dot live', 'aria-hidden': 'true' }) : null, [agent.status, agent.tokens ? t('{tokens} tokens', { tokens: agent.tokens }) : ''].filter(Boolean).join(' · ')),
      ),
      h(
        'ul',
        { class: 'links' },
        h('li', {}, h('a', { href: `${base}/logs/${encodeURIComponent(agent.name)}` }, t('≡ log'))),
        agent.sessions.map((one) => h('li', {}, h('a', { href: `${base}/sessions/${encodeURIComponent(one.key)}` }, one.working ? '● ' : '○ ', h('span', { class: 'mono' }, one.key)), h('span', { class: 'dim' }, ` ${t('{n} turns', { n: one.turns.length })}${one.about ? ` · ${one.about}` : ''}`))),
      ),
    ),
  )
}

/** A path, cut to one line, said in full on hover and copied from its menu. */
function pathed(path) {
  return menuOn(pathText(path), () => [{ head: path }, { label: t('Copy path'), glyph: 'copy', act: () => copy(path, t('Path copied')) }])
}

function section(title, ...kids) {
  return h('section', { class: 'side-section' }, h('h3', {}, title), kids)
}

/** What the run has cost, and how fast: the second line the terminal interface draws. */
function spentTile(said) {
  const parts = said.split(' · ')
  const priced = parts.length > 1 && parts[0].startsWith('$')
  return tile(t('spent'), priced ? parts[0] : '—', priced ? parts.slice(1).join(' · ') : said)
}

function tile(label, value, sub) {
  return h('div', { class: 'tile' }, h('div', { class: 'kicker' }, label), value ? h('div', { class: 'value' }, value) : null, sub ? h('div', { class: 'sub' }, sub) : null)
}

/** What the run may spend against what it has: a meter for each limit it has. */
function budgetTile(usage) {
  if (!usage || !usage.budget || !usage.usage) return tile(t('budget@@limit'), '—', t('No limit'))
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
        h('div', { class: 'sub' }, t('{label} {have} of {may}', { label, have: said(have), may: said(may) })),
        h('div', { class: ['meter', share >= 1 && 'over'], role: 'meter', 'aria-valuemin': '0', 'aria-valuemax': String(may), 'aria-valuenow': String(have), 'aria-label': label }, h('span', { style: { width: `${share * 100}%` } })),
      ),
    )
  }
  meter(t('cost'), spent.cost, allowed.cost, (dollars) => `$${dollars.toFixed(2)}`)
  meter(t('output'), spent.output_tokens, allowed.output_tokens, (count) => String(Math.round(count)))
  meter(t('time'), secondsOf(spent.duration), secondsOf(allowed.duration), lasting)
  return h('div', { class: 'tile' }, h('div', { class: 'kicker' }, t('budget@@limit')), limits.length ? limits : h('div', { class: 'sub' }, t('No measurable limit')))
}

/** What each fact of an epic or a chat is called: as hmz names it, and, for a chat, in plain words. */
const FACTS = {
  name: [t('epic'), t('Chat ID')],
  at: [t('written to'), t('Saved at')],
  workspace: [t('workdir'), t('Folder')],
  workdir: ['', t('Works in')],
  began: ['', t('Started')],
  agents: [t('agents'), t('Nous')],
  used: [t('envs'), t('Environment')],
  params: [t('params'), t('Options')],
  budget: [t('budget@@limit'), t('Limits')],
  sessions: [t('sessions'), ''],
  picked_up: [t('resumed from'), t('Continued from')],
  profiled: [t('profiled'), t('Profiled')],
}

function facts(detail, chat = false) {
  const said = (fact) => FACTS[fact][chat ? 1 : 0]
  return h(
    'dl',
    { class: 'facts' },
    h('dt', {}, said('name')),
    h('dd', { class: 'mono' }, detail.name),
    h('dt', {}, said('at')),
    h('dd', {}, pathed(detail.at)),
    h('dt', {}, said('workspace')),
    h('dd', {}, pathed(detail.workspace)),
    // A chat started in a worktree works there, in place of its folder.
    chat && worksIn(detail) ? [h('dt', {}, said('workdir')), h('dd', { 'data-hmz': 'chat-workdir' }, pathed(worksIn(detail)))] : null,
    // When a chat began is said here: its bar says its title alone.
    chat && detail.began ? [h('dt', {}, said('began')), h('dd', { title: when(detail.began) }, ago(detail.began))] : null,
    h('dt', {}, said('agents')),
    // A chat has one agent, in the one role every chat has: what it runs says which it is.
    h('dd', {}, detail.agents.length ? detail.agents.map((one) => h('div', { title: one.runs }, [!chat && one.name !== one.role && one.name, !chat && one.role, agentLabel(one.runs) || one.runs].filter(Boolean).join(' · '))) : '—'),
    h('dt', {}, said('used')),
    h('dd', {}, detail.used.length ? detail.used.map((one) => h('div', { class: 'mono' }, one)) : '—'),
    h('dt', {}, said('params')),
    h('dd', {}, Object.keys(detail.params || {}).length ? h('pre', { class: 'block' }, JSON.stringify(detail.params, null, 2)) : '—'),
    h('dt', {}, said('budget')),
    h('dd', {}, budgeted(detail.budget)),
    // A chat is one conversation, and says nothing of the sessions kept under it.
    chat ? null : [h('dt', {}, said('sessions')), h('dd', {}, detail.sessions.length ? sessionsOf(detail).map((one) => h('div', {}, h('span', { class: 'mono' }, one.key), ` · ${harnessName(one.backend)}`, one.provider ? `@${one.provider}` : '', h('div', { class: 'dim mono' }, one.ident))) : t('none'))],
    detail.picked_up ? [h('dt', {}, said('picked_up')), h('dd', {}, h('a', { href: hash(`/epics/${encodeURIComponent(detail.picked_up)}`) }, detail.picked_up))] : null,
    detail.profile_flow || detail.profile_environment
      ? [h('dt', {}, said('profiled')), h('dd', {}, [detail.profile_flow && t('flow'), detail.profile_environment && t('environment')].filter(Boolean).join(' · '))]
      : null,
  )
}

/**
 * A budget in words: each limit it set, and whether the last turn could finish over it --
 * said once where every limit agrees, and after each limit that cuts off where they do not.
 */
function budgeted(budget) {
  if (!budget) return '—'
  const seconds = secondsOf(budget.duration)
  const graceful = (limit) => (budget.graceful && typeof budget.graceful === 'object' ? budget.graceful[limit] : budget.graceful) !== false
  const limits = [
    typeof budget.cost === 'number' && Number.isFinite(budget.cost) ? [`$${budget.cost.toFixed(2)}`, graceful('cost')] : null,
    seconds ? [lasting(seconds), graceful('duration')] : null,
    typeof budget.output_tokens === 'number' ? [t('{tokens} output tokens', { tokens: budget.output_tokens }), graceful('output_tokens')] : null,
  ].filter(Boolean)
  if (!limits.length) return t('no limit')
  if (limits.every(([, soft]) => soft)) return t('{limits}, letting the last turn finish', { limits: limits.map(([said]) => said).join(' · ') })
  if (limits.every(([, soft]) => !soft)) return t('{limits}, cut off at once', { limits: limits.map(([said]) => said).join(' · ') })
  return t('{limits}, else letting the last turn finish', { limits: limits.map(([said, soft]) => (soft ? said : t('{limit} cut off at once', { limit: said }))).join(' · ') })
}

function tree(calls) {
  return h(
    'ul',
    { class: 'tree' },
    calls.map((call) => h('li', {}, h('b', {}, call.flow), ' ', call.how ? badge(call.how) : null, call.task ? h('div', { class: 'dim' }, call.task.slice(0, 160)) : null, call.calls.length ? tree(call.calls) : null)),
  )
}
