// Ai-chan's drawer (Section 3.16 of protocol/web.md): beside every view of the page, opened and
// closed by her avatar on the view's bar, and left as it was from view to view. It lists her
// conversations with the daemon shown, newest first, makes one with `New` -- of the scope the
// page shows, with the nous Settings name for her -- and draws one as a chat, attached to its
// slot: her answers beside her avatar, each tool she calls a line to open, and a box that says
// the next line to her, which carries a conversation folded away on.

import { call, onDaemon, poll, refresh } from '../api.js'
import { PRESETS, SCOPES, created, missing, permissionSaid, scopeOf, scopeSaid, sessionOf, stateOf, stateSaid, told } from '../aichan.js'
import { composer } from '../composer.js'
import { confirming } from '../confirm.js'
import { acting, fill, h, icon, problem } from '../dom.js'
import { sessionsOf, watch } from '../epic.js'
import { ask, current, follow } from '../held.js'
import { nousField } from '../pickers.js'
import { firstWorkspace, goneSaid, workspacePicker } from '../places.js'
import { dragged, sidePanel } from '../shell.js'
import { line, saidTraced, sayer } from '../transcript.js'

/** Her avatar, as drawn beside what she says and over her drawer. */
const AVATAR = '/ai-chan/avatar.webp'

/** How often her conversations are read again while the drawer is open, in milliseconds. */
const EVERY = 3000

/** How long a line said to a conversation folded away waits for her to be carried on. */
const CARRYING = 30000

/**
 * Mounts the drawer beside the page, once.
 *
 * @param {HTMLElement} app The page's frame, which the drawer stands in.
 * @param {() => {parts: string[], query: URLSearchParams}} where Where the page is.
 */
export function mount(app, where) {
  /** What the drawer shows: the list, the form that makes one, or one conversation. */
  let showing = { kind: 'list' }
  /** Every conversation, as `aichan.list` last answered, and what refused it. */
  let rows = null
  let refused = null
  let unlist = () => {}
  /** What lets go of what is drawn now: the conversation followed, or the form. */
  let leave = () => {}
  const body = h('div', { class: 'aichan-body' })
  const panel = sidePanel('Ai-chan', { key: 'hmz-aichan', open: false, hmz: 'aichan', kind: 'aichan', told: (open) => opened(open) })
  panel.node.id = 'aichan'
  const fresh = h('button', { class: 'btn small', type: 'button', 'data-hmz': 'aichan-new' }, icon('plus'), 'New')
  fill(
    panel.body,
    dragged(h('header', { class: 'aichan-head' }, h('img', { class: 'aichan-avatar', src: AVATAR, alt: '', width: '32', height: '32' }), h('h2', {}, 'Ai-chan'), fresh), 'deep', 'wide'),
    body,
  )
  app.append(panel.node)

  fresh.addEventListener('click', () => show({ kind: 'new' }))

  function opened(open) {
    app.classList.toggle('aichan-open', open)
    for (const button of document.querySelectorAll('[data-hmz=aichan-toggle]')) button.setAttribute('aria-pressed', String(open))
    unlist()
    unlist = () => {}
    if (!open) {
      leave()
      leave = () => {}
      return
    }
    unlist = poll('aichan.list', {}, EVERY, (answer, error) => {
      refused = error
      if (answer) rows = answer.conversations
      if (showing.kind === 'list') list()
      else if (showing.kind === 'chat') titled()
    })
    show(showing)
  }

  /** Draws what the drawer shows, anew. */
  function show(what) {
    leave()
    leave = () => {}
    showing = what
    if (what.kind === 'new') leave = form()
    else if (what.kind === 'chat') leave = chat(what)
    else list()
  }

  function list() {
    if (!rows) return fill(body, refused ? problem(refused) : h('p', { class: 'loading', role: 'status' }, 'Reading her conversations…'))
    fill(
      body,
      refused ? problem(refused) : null,
      rows.length
        ? h(
            'ul',
            { class: 'aichan-list', role: 'list', 'data-hmz': 'aichan-list' },
            rows.map((one) =>
              h(
                'li',
                { class: 'aichan-row', 'data-hmz': 'aichan-conversation' },
                h(
                  'button',
                  { class: 'aichan-pick', type: 'button', onclick: () => show({ kind: 'chat', ...one }) },
                  h('span', { class: 'aichan-title' }, one.title || `Ai-chan #${one.id}`),
                  h('span', { class: 'aichan-about' }, scopeSaid(one)),
                  h('span', { class: 'aichan-about mono' }, [one.nous, permissionSaid(one)].filter(Boolean).join(' · ')),
                  h('span', { class: ['aichan-state', one.state], 'data-hmz': 'aichan-state' }, stateSaid(one.state)),
                ),
                confirming({
                  label: 'Forget',
                  ask: 'Forget her conversation?',
                  yes: 'Forget',
                  small: true,
                  act: async () => {
                    await call('aichan.forget', { id: one.id })
                    refresh('aichan.list')
                  },
                }),
              ),
            ),
          )
        : h('p', { class: 'dim aichan-none' }, 'No conversation with Ai-chan yet. Start one with New.'),
    )
  }

  /** The form that makes a conversation, of the scope the page shows. */
  function form() {
    const { parts, query } = where()
    const at = scopeOf(parts, query)
    const scope = h('select', { 'aria-label': 'Scope', 'data-hmz': 'aichan-scope' }, SCOPES.map(([value, label]) => h('option', { value, selected: value === at.scope }, label)))
    const place = workspacePicker(at.workspace || '', () => epics())
    const epic = h('input', { type: 'text', value: at.epic, placeholder: 'Epic name', 'aria-label': 'Epic', 'data-hmz': 'aichan-epic', list: 'aichan-epics', spellcheck: 'false', autocomplete: 'off' })
    const named = h('datalist', { id: 'aichan-epics' })
    const preset = h('select', { 'aria-label': 'Preset', 'data-hmz': 'aichan-preset' }, PRESETS.map((one) => h('option', { value: one }, one)))
    const network = h('input', { type: 'checkbox', 'data-hmz': 'aichan-network' })
    const title = h('input', { type: 'text', placeholder: 'From the task', 'aria-label': 'Title', 'data-hmz': 'aichan-title' })
    const nousHolder = h('span', {}, h('span', { class: 'hint' }, 'Reading the nous…'))
    let nous = null
    let setting = ''
    const box = composer({
      placeholder: 'Tell Ai-chan what to do',
      label: 'Task',
      busy: 'Starting…',
      submit: async (task) => {
        const said = { scope: scope.value, workspace: place.value() || '', epic: epic.value, nous: nous ? nous.input.value : '', preset: preset.value, network: network.checked, title: title.value, task }
        const why = missing(said, setting)
        if (why) throw new Error(why)
        // Nothing is made in a folder that went; the daemon's scope names none (`created`).
        if (said.scope === 'workspace' && place.gone()) throw new Error(goneSaid(said.workspace))
        const made = await call('aichan.create', created(said))
        refresh('aichan.list')
        show({ kind: 'chat', ...made })
      },
    })
    box.node.dataset.hmz = 'aichan-task'
    const where_ = h('div', { class: 'field', 'data-hmz': 'aichan-workspace' }, h('span', { class: 'label' }, 'Workspace'), place.node)
    const which = h('div', { class: 'field' }, h('span', { class: 'label' }, 'Epic'), epic, named)
    const scoped = () => {
      where_.hidden = scope.value === 'daemon'
      which.hidden = scope.value !== 'epic'
    }
    scope.addEventListener('change', scoped)
    scoped()
    /** The epics of the workspace picked, offered to name. */
    function epics() {
      const workspace = place.value()
      if (!workspace) return
      call('runs.list', { workspace, limit: 50 }).then(
        (answer) => fill(named, answer.runs.map((one) => h('option', { value: one.name }, one.task.split('\n')[0]))),
        () => {},
      )
    }
    // The epic shown is of a workspace its address does not say: read off the epic.
    if (at.scope === 'epic')
      call('runs.get', { name: at.epic }).then(
        (found) => {
          place.set(found.workspace)
          epics()
        },
        () => {},
      )
    else if (!at.workspace)
      firstWorkspace().then(
        (path) => {
          if (!place.value()) place.set(path)
          epics()
        },
        () => {},
      )
    else epics()
    Promise.all([call('settings.get'), call('nous.list').catch(() => null)]).then(
      ([settings, offered]) => {
        setting = settings.ai_chan || ''
        nous = nousField(setting, offered, { label: 'Nous', hmz: 'aichan-nous', placeholder: 'Pick her nous' })
        fill(nousHolder, nous.node)
      },
      (error) => fill(nousHolder, problem(error)),
    )
    const back = h('button', { class: 'btn quiet small', type: 'button', onclick: () => show({ kind: 'list' }) }, 'Back')
    fill(
      body,
      h(
        'div',
        { class: 'form aichan-form', 'data-hmz': 'aichan-form' },
        h('div', { class: 'aichan-crumb' }, back, h('b', {}, 'New conversation')),
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'Scope'), scope),
        where_,
        which,
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'Nous'), nousHolder),
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'Preset'), preset),
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'Network'), h('label', { class: 'check' }, network, 'Her harness may reach the network')),
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'Title'), title),
        box.node,
      ),
    )
    box.text.focus()
    return () => place.leave()
  }

  /** Names the conversation drawn as the list names it, once the list has it. */
  function titled() {
    const shown = body.querySelector('[data-hmz=aichan-title]')
    if (!shown) return
    const row = (rows || []).find((each) => each.id === showing.id)
    shown.textContent = (row && row.title) || showing.title || `Ai-chan #${showing.id}`
  }

  /** One conversation, drawn as a chat while its slot is followed. */
  function chat(one) {
    const host = { workspace: one.workspace, slot: one.slot }
    const log = h('div', { class: 'thread aichan-log', role: 'log', 'aria-live': 'polite', 'data-hmz': 'aichan-log' })
    const earlier = h('div', { class: 'thread-before' })
    const note = h('p', { class: 'dim aichan-note', 'data-hmz': 'aichan-folded', hidden: true }, 'Folded away. What you say next carries her on.')
    const options = h('div', { class: 'row aichan-options', 'data-hmz': 'aichan-options' })
    const stopHolder = h('span', {})
    const state = h('span', { class: 'aichan-state', 'data-hmz': 'aichan-state' })
    let held = null
    let saidBy = null
    let saidFor = ''
    let upTo = -1
    /** How many sessions she had opened before she was last carried on, as last read for what they said. */
    let traced = 0
    /** Why her chat ended failed, once it has: said in the log once, and nothing more said to it. */
    let failed = ''
    const box = composer({
      placeholder: 'Say something to Ai-chan',
      label: 'What to say to Ai-chan',
      submit: async (text) => {
        // Her chat failed: no line carries it on (Section 8.4.9 of protocol/core.md).
        if (failed) throw new Error('This conversation failed. Start a new one.')
        // Folded away: attached again, which carries her on, and what she then waits on answered.
        let now = held
        if (!now || !now.connected) now = (await carried(host)) || now
        const pending = now && now.standing.pending ? now.standing.pending.pending : []
        const [what, said] = told(pending, now ? now.me : '', text)
        await ask(host, what, said)
      },
    })
    box.node.dataset.hmz = 'aichan-say'
    const back = h('button', { class: 'btn quiet small', type: 'button', 'data-hmz': 'aichan-back', onclick: () => show({ kind: 'list' }) }, 'Back')
    fill(
      body,
      h(
        'div',
        { class: 'aichan-chat', 'data-hmz': 'aichan-chat' },
        h('div', { class: 'aichan-crumb' }, back, h('b', { class: 'aichan-title', 'data-hmz': 'aichan-title' }), state, stopHolder),
        h('div', { class: 'aichan-scroll' }, earlier, log, note),
        options,
        box.node,
      ),
    )
    box.text.focus()
    titled()

    function draw(seen) {
      held = seen.held
      if (!held) return
      const { number, records } = current(held)
      const key = sessionOf(records)
      const whose = JSON.stringify([key, number, held.epoch])
      if (whose !== saidFor) {
        saidFor = whose
        saidBy = sayer(key, { chat: true, folded: true })
        upTo = -1
        failed = ''
        fill(log)
      }
      const scroller = log.parentElement
      const stuck = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 60
      let added = false
      for (const record of records) {
        if (record.seq <= upTo) continue
        upTo = record.seq
        for (const line of saidBy(record)) {
          log.append(line)
          added = true
        }
      }
      if (added) log.querySelector(':scope > .thread-empty')?.remove()
      // Carried on: what was said before, read out of the session it carried on from.
      const detail = seen.detail
      if (detail && detail.earlier && traced !== detail.earlier) {
        traced = detail.earlier
        // Her conversation is a chat's record, read by the id her host says (`chat.get`).
        call('chat.get', { chat: detail.name, trace: true }).then(
          (read) => {
            const before = sessionsOf(detail)[detail.earlier - 1]
            const found = before && read.trace.find((each) => each.key === before.traced)
            if (found && found.actions.length) fill(earlier, saidTraced({ ...found, label: before.key, chat: true }))
          },
          () => {},
        )
      }
      const run = held.standing.run
      const turn = run ? run.turn : ''
      // A chat that ended failed is said failed, with what the harness said (Section 8.5.3).
      const stands = stateOf({ connected: held.connected, turn, records })
      if (stands.why && !failed) {
        log.querySelector(':scope > .thread-empty')?.remove()
        log.append(line('failed', stands.why))
      }
      failed = stands.why
      state.className = `aichan-state ${stands.state}`
      fill(state, stateSaid(stands.state))
      note.hidden = held.connected || !held.gone || Boolean(failed)
      // Her turn open: stopped at once, without asking (Section 14.8.3 of protocol/core.md).
      const answering = held.connected && turn === 'running'
      if (answering !== Boolean(stopHolder.firstChild)) fill(stopHolder, answering ? acting('Stop', () => ask(host, 'stop'), { kind: 'btn small danger', busy: 'Stopping…' }) : null)
      // What she asks mid-turn, with the answers she offers, answered by a press.
      const pending = (held.standing.pending && held.standing.pending.pending) || []
      const asking = pending.find((each) => each.options && each.options.length && (!each.owner || each.owner === held.me))
      const shown = asking ? JSON.stringify([asking.question, asking.options]) : ''
      if (options.dataset.shown !== shown) {
        options.dataset.shown = shown
        fill(options, asking ? asking.options.map((option, index) => acting(option, () => ask(host, 'answer', { question: asking.question, text: String(index + 1) }), { kind: 'btn small', busy: 'Answering…' })) : null)
      }
      if (!log.childElementCount) log.append(h('p', { class: 'dim thread-empty' }, held.connected ? 'Ai-chan is reading…' : 'Opening her conversation…'))
      if (stuck) scroller.scrollTop = scroller.scrollHeight
    }

    return watch('', host, draw)
  }

  // Opened and closed by her avatar on any view's bar, and closed by Escape from inside it:
  // the last thing the key closes, after whatever floats and whatever a box of hers took it
  // for. On a phone, where it covers the view, the page closes it by Escape from anywhere.
  addEventListener('hmz:aichan', () => panel.set(panel.node.hidden))
  panel.node.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || event.defaultPrevented) return
    event.preventDefault()
    panel.set(false)
  })
  // Another daemon's conversations are others: the drawer goes back to the list of them.
  onDaemon(() => {
    rows = null
    refused = null
    showing = { kind: 'list' }
    if (!panel.node.hidden) opened(true)
  })
}

/**
 * Follows a conversation's slot until her host holds it and waits on a person, attaching it
 * again where it has gone -- which carries a conversation folded away on --, or a while.
 *
 * @returns {Promise<object|null>} The host as it then stands, or null where it never did.
 */
function carried(host) {
  return new Promise((resolve) => {
    let done = false
    let stop = null
    /** Why it had gone before, which attaching it again says anew where it is refused. */
    let was = null
    const end = (state) => {
      if (done) return
      done = true
      clearTimeout(timer)
      queueMicrotask(() => stop && stop())
      resolve(state)
    }
    const timer = setTimeout(() => end(null), CARRYING)
    stop = follow(host, (state) => {
      if (was === null) was = state.gone
      if (state.connected && state.standing.pending && state.standing.pending.pending.length) end(state)
      else if (!state.connected && state.gone && state.gone !== was) end(state)
    })
  })
}
