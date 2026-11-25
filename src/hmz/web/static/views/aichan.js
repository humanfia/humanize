// Ai-chan's drawer (Section 3.16 of protocol/web.md): beside every view of the page, opened and
// closed by her avatar on the view's bar, and left as it was from view to view. It lists her
// conversations with the daemon shown as a chat app lists its own -- a face, a title and the
// start of what was last said, the pinned first and then the latest said in --, with a menu on
// each, under the pointer's other button, the menu key or a finger at rest, and under the row
// swiped to the left: pin it, mark it read or unread, delete it. `New` opens a conversation not
// made yet, drawn as one that is: a chat with nothing said in it, whose box has under it her
// nous -- the one she last used unless another is picked -- and what she may do and reach, of
// the scope the page shows, and whose first line makes it. One there is is drawn attached to its
// slot: her answers in bubbles beside the conversation's face, the person's at the right, each
// tool she calls a line to open, a box that says the next line to her, which carries a
// conversation folded away on, and beside its title a pencil that renames it. One opened before
// is drawn at once as the page last saw it (logs.js; Section 3.6.12 of protocol/web.md), and
// what her host then tells is added to it.

import { call, daemon, idOf, onDaemon, poll, refresh } from '../api.js'
import { PRESETS, TITLED, actionsOf, created, earlierOf, faceUrl, marked, marksOf, missing, ordered, previewOf, read, scopeOf, scopeSaid, scopesOf, sessionOf, settled, stateOf, titleOf, told, typingOf, unreadOf } from '../aichan.js'
import { retitling } from '../chat-actions.js'
import { modelChip, nousSaidChip } from '../chips/model.js'
import { permissionChip } from '../chips/permission.js'
import { composer } from '../composer.js'
import { acting, empty, fill, h, icon, iconButton, problem } from '../dom.js'
import { sessionsOf, watch } from '../epic.js'
import { ask, current, follow } from '../held.js'
import { t } from '../i18n.js'
import { logKey, logs } from '../logged.js'
import { readBackends } from '../pickers.js'
import { firstWorkspace } from '../places.js'
import { choice, dragged, keep, kept, section, sidePanel } from '../shell.js'
import { swiped, unswiped } from '../swipe.js'
import { line, saidTraced, sayer } from '../transcript.js'
import { menuOf, menuOn } from '../ui.js'

/** How often her conversations are read again while the drawer is open, in milliseconds. */
const EVERY = 3000

/** How long a line said to a conversation folded away waits for her to be carried on. */
const CARRYING = 30000

/**
 * How long a conversation left with her answer in view stays read whatever the list says of it,
 * in milliseconds: the daemon writes down when she answered a moment after she did.
 */
const SETTLING = 2000

/** What this browser keeps of her conversations, by daemon: the pinned, the unread, those seen failed, and up to when each was read. */
const MARKS = 'hmz-aichan-marks'

/**
 * Mounts the drawer beside the page, once.
 *
 * @param {HTMLElement} app The page's frame, which the drawer stands in.
 * @param {() => {parts: string[], query: URLSearchParams}} where Where the page is.
 */
export function mount(app, where) {
  /** What the drawer shows: the list, a conversation not made yet, or one conversation. */
  let showing = { kind: 'list' }
  /** Every conversation, as `aichan.list` last answered, and what refused it. */
  let rows = null
  let refused = null
  let unlist = () => {}
  /** What lets go of what is drawn now: the conversation followed, or the one being made. */
  let leave = () => {}
  /** The rows drawn, by the conversation each is of, and the one whose deleting is asked. */
  const drawn = new Map()
  let asking = null
  /** The conversation just left with her answer in view: read still, until the list says when that was said. */
  let lately = null
  const body = h('div', { class: 'aichan-body' })
  const panel = sidePanel('Ai-chan', { key: 'hmz-aichan', open: false, hmz: 'aichan', kind: 'aichan', told: (open) => opened(open) })
  panel.node.id = 'aichan'
  const fresh = h('button', { class: 'btn small', type: 'button', 'data-hmz': 'aichan-new' }, icon('plus'), t('New'))
  fill(panel.body, dragged(h('header', { class: 'aichan-head' }, h('h2', {}, 'Ai-chan'), fresh), 'deep'), body)
  app.append(panel.node)

  fresh.addEventListener('click', () => show({ kind: 'new' }))

  /** What this browser keeps of the conversations of the daemon shown. */
  function marks() {
    let all = null
    try {
      all = JSON.parse(kept(MARKS, '{}'))
    } catch {
      // Unreadable, it keeps nothing.
    }
    return marksOf(all, daemon())
  }

  /** Keeps it, beside what is kept of every other daemon's. */
  function remember(now) {
    let all = {}
    try {
      all = JSON.parse(kept(MARKS, '{}')) || {}
    } catch {
      // Unreadable, it is written anew.
    }
    if (JSON.stringify(marksOf(all, daemon())) === JSON.stringify(now)) return
    keep(MARKS, JSON.stringify({ ...all, [daemon()]: now }))
  }

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
      if (answer) {
        rows = answer.conversations
        // What is gone is not kept to be drawn by, either.
        logs.keep(daemon(), 'aichan', rows.map((each) => each.id))
        // Read again: what is gone is forgotten here, and the one open is read as it is said in.
        remember(settled(marks(), rows, showing.kind === 'chat' ? showing.id : lately ? lately.id : null))
      }
      if (showing.kind === 'list') list()
      else if (showing.kind === 'chat') titled()
    })
    show(showing)
  }

  /**
   * A conversation left while she rested: what she last said was read in it, though the list may
   * not say yet when that was. It is read up to what the list says once the daemon has written it.
   */
  function left(id) {
    const mine = { id }
    lately = mine
    setTimeout(() => {
      if (lately !== mine) return
      call('aichan.list').then(
        (answer) => {
          if (lately !== mine) return
          lately = null
          const row = answer.conversations.find((each) => each.id === id)
          const now = marks()
          if (!row || !(id in now.seen) || (showing.kind === 'chat' && showing.id === id)) return
          remember({ ...now, seen: { ...now.seen, [id]: row.updated || '' } })
          if (showing.kind === 'list' && !panel.node.hidden) list()
        },
        () => {
          if (lately === mine) lately = null
        },
      )
    }, SETTLING)
  }

  /** Draws what the drawer shows, anew. */
  function show(what) {
    leave()
    leave = () => {}
    unswiped()
    showing = what
    if (what.kind === 'list') list()
    else leave = chat(what)
  }

  /** The list's own frame, kept while the list is shown so that its rows are drawn once and then changed. */
  const refusal = h('div', {})
  const listed = h('ul', { class: 'aichan-list', role: 'list', 'data-hmz': 'aichan-list' })
  const none = empty(
    t('No conversations yet'),
    t('Ask Ai-chan what your epics did, have her steer a session, or run something for you.'),
    h('button', { class: 'btn small', type: 'button', 'data-hmz': 'aichan-first', onclick: () => show({ kind: 'new' }) }, icon('plus'), t('New conversation')),
  )
  none.classList.add('aichan-none')
  none.dataset.hmz = 'aichan-none'
  const listing = h('div', { class: 'aichan-listing' }, refusal, listed, none)

  function list() {
    if (!rows) return fill(body, refused ? problem(refused) : h('p', { class: 'loading late', role: 'status' }, t('Reading her conversations…')))
    if (listing.parentElement !== body) fill(body, listing)
    fill(refusal, refused ? problem(refused) : null)
    const now = marks()
    const sorted = ordered(rows, now)
    none.hidden = sorted.length > 0
    listed.hidden = !sorted.length
    for (const [id, one] of drawn) {
      if (sorted.some((row) => row.id === id)) continue
      one.node.remove()
      drawn.delete(id)
      if (asking === id) asking = null
    }
    for (const row of sorted) {
      if (!drawn.has(row.id)) drawn.set(row.id, rowOf(row.id))
      drawn.get(row.id).draw(row, now)
    }
    // Put in their order only where it changed: a row moved loses the focus and the finger on it,
    // so none is moved while a finger drags one; the list read next puts them in order.
    const order = sorted.map((row) => drawn.get(row.id).node)
    if (!listed.querySelector('.swiping') && order.some((node, at) => listed.children[at] !== node)) {
      const held = document.activeElement
      listed.replaceChildren(...order)
      if (held instanceof HTMLElement && listed.contains(held)) held.focus({ preventScroll: true })
    }
  }

  /** Does what a conversation's menu, or the row under it, offers. */
  function act(key, row, on) {
    if (key === 'delete') {
      asking = row.id
      list()
      drawn.get(row.id)?.node.querySelector('[data-hmz=aichan-keep]')?.focus()
      return
    }
    const now = marks()
    // Marked by hand, it is as it was marked.
    if (key !== 'pin' && lately && lately.id === row.id) lately = null
    if (key === 'pin') remember(marked(now, 'pinned', row.id, on))
    // Marked read, it is read up to what was last said in it; unread, until it is opened.
    else remember(on ? read(now, row) : marked(now, 'unread', row.id, true))
    list()
  }

  /** One conversation's row: drawn once, and changed as the list is read again. */
  function rowOf(id) {
    const title = h('span', { class: 'aichan-title' })
    const latest = h('span', { class: 'aichan-latest', 'data-hmz': 'aichan-latest' })
    const signs = h('span', { class: 'aichan-signs' })
    const pick = h('button', { class: 'aichan-pick', type: 'button' }, h('img', { class: 'aichan-face', src: faceUrl(id), alt: '', width: '40', height: '40', draggable: 'false' }), title, signs, latest)
    const tray = h('div', { class: 'aichan-swipe', 'data-hmz': 'aichan-swipe', inert: true })
    const holder = h('div', {})
    const node = h('li', { class: 'aichan-row', 'data-hmz': 'aichan-conversation', 'data-id': String(id) }, pick, tray, holder)
    let row = null
    let was = ''
    const swipe = swiped(node, tray, { held: () => menuOf(node, pick) })
    pick.addEventListener('click', () => {
      // Open under a finger, a press of it shuts it: the row is opened by the next.
      if (node.classList.contains('swiped')) return swipe.shut()
      show({ kind: 'chat', ...row })
    })
    // The menu key, where a keyboard has one, and Alt and Enter where it has none.
    pick.addEventListener('keydown', (event) => {
      if (!(event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey) || (event.key === 'Enter' && event.altKey))) return
      event.preventDefault()
      menuOf(node, pick)
    })
    menuOn(node, () => (asking === id ? [] : actionsOf(row, marks()).map((one) => ({ label: one.label, glyph: one.glyph, danger: one.danger, act: () => act(one.key, row, one.on) }))))

    /** What asks before the conversation is deleted, over its row. */
    function confirm() {
      const cancel = () => {
        asking = null
        list()
        pick.focus()
      }
      const no = h('button', { class: 'btn quiet small', type: 'button', 'data-hmz': 'aichan-keep', onclick: cancel }, t('Cancel'))
      const yes = h('button', { class: 'btn small danger', type: 'button', 'data-hmz': 'aichan-delete' }, t('Delete'))
      const wrong = h('span', { class: 'aichan-wrong', role: 'alert' })
      yes.addEventListener('click', async () => {
        no.disabled = yes.disabled = true
        yes.textContent = t('Deleting…')
        try {
          await call('aichan.forget', { id })
        } catch (error) {
          no.disabled = yes.disabled = false
          yes.textContent = t('Delete')
          wrong.textContent = error.message
          return
        }
        // Gone at once, here; the list read again says so of the daemon.
        logs.drop(logKey('aichan', id))
        rows = (rows || []).filter((one) => one.id !== id)
        remember(settled(marks(), rows))
        // Over the list alone: a form or a conversation opened meanwhile stays as it is.
        if (showing.kind === 'list') list()
        refresh('aichan.list')
      })
      const question = t('Delete this conversation?')
      const asked = h('div', { class: 'aichan-ask', role: 'alertdialog', 'aria-label': question, 'data-hmz': 'aichan-ask' }, h('span', { class: 'aichan-asked' }, question, wrong), no, yes)
      // Pressed, not rested on as the row is: a finger slow on its buttons opens no menu.
      asked.addEventListener('pointerdown', (event) => event.stopPropagation())
      asked.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return
        // Taken back, and not the drawer's to close.
        event.preventDefault()
        cancel()
      })
      return asked
    }

    return {
      node,
      draw(next, now) {
        row = next
        const unread = unreadOf(row, now)
        const pinned = now.pinned.includes(id)
        const failed = now.failed.includes(id)
        const is = JSON.stringify([titleOf(row), previewOf(row), row.state, unread, pinned, failed, asking === id])
        if (is === was) return
        was = is
        title.textContent = titleOf(row)
        latest.textContent = previewOf(row)
        node.classList.toggle('is-unread', unread)
        node.classList.toggle('is-pinned', pinned)
        node.classList.toggle('is-typing', row.state === 'running')
        fill(
          signs,
          pinned ? h('span', { class: 'aichan-pinned', role: 'img', 'aria-label': t('Pinned'), 'data-hmz': 'aichan-pinned' }, icon('pin')) : null,
          failed ? h('span', { class: 'aichan-failed', role: 'img', 'aria-label': t('Failed'), 'data-hmz': 'aichan-failed' }, icon('close')) : null,
          unread ? h('span', { class: 'aichan-unread', role: 'img', 'aria-label': t('Unread'), 'data-hmz': 'aichan-unread' }) : null,
        )
        // The same three as its menu, under the row for a finger that swipes it.
        fill(
          tray,
          actionsOf(row, now).map((one) =>
            h(
              'button',
              {
                class: ['aichan-act', one.danger && 'danger'],
                type: 'button',
                'data-act': one.key,
                onclick: () => {
                  swipe.shut()
                  act(one.key, row, one.on)
                },
              },
              icon(one.glyph),
              h('span', {}, one.label),
            ),
          ),
        )
        if (asking === id) {
          swipe.shut()
          if (!holder.firstChild) holder.append(confirm())
        } else fill(holder)
        pick.inert = asking === id
      },
    }
  }

  /** Names the conversation drawn as the list names it, once the list has it; one not made yet is a new one. */
  function titled() {
    const shown = body.querySelector('[data-hmz=aichan-title]')
    if (!shown) return
    if (showing.kind !== 'chat') return void (shown.textContent = t('New conversation'))
    const row = (rows || []).find((each) => each.id === showing.id)
    shown.textContent = titleOf(row && row.title ? row : showing)
  }

  /**
   * One conversation, drawn as a chat while its slot is followed -- or one not made yet, which
   * is the same chat with nothing said in it: under its box her nous and what she may do and
   * reach, picked as a new chat's are, and the first line said makes it, in this view.
   */
  function chat(one) {
    /** The conversation, once there is one. */
    let made = one.kind === 'chat' ? one : null
    const host = () => ({ workspace: made.workspace, slot: made.slot })
    // Her words beside the face its row has in the list.
    const log = h('div', { class: 'thread aichan-log', role: 'log', 'aria-live': 'polite', 'data-hmz': 'aichan-log' })
    const earlier = h('div', { class: 'thread thread-before aichan-log' })
    // While her turn is open: three dots in a bubble of hers, at the foot of the conversation.
    const typing = h(
      'div',
      { class: 'aichan-typing', role: 'status', 'aria-label': t('Ai-chan is typing…'), 'data-hmz': 'aichan-typing' },
      h('span', { class: 'g', 'aria-hidden': 'true' }),
      h('div', { class: 'body', 'aria-hidden': 'true' }, h('i', {}), h('i', {}), h('i', {})),
    )
    const options = h('div', { class: 'row aichan-options', 'data-hmz': 'aichan-options' })
    const whole = h('div', { class: 'aichan-chat', 'data-hmz': 'aichan-chat' })
    let held = null
    let saidBy = null
    let saidFor = ''
    let upTo = -1
    /** How many sessions she had opened before she was last carried on, as last read for what they said. */
    let traced = 0
    /** Why her chat ended failed, once it has: said in the log once, and nothing more said to it. */
    let failed = ''
    /** Whether she rests, as last drawn: what she said is all in view. */
    let rested = false
    /** Whether her host has answered this drawing of the conversation. */
    let met = false
    /** Whether the view was left: what is still being read or made draws nothing. */
    let away = false
    let unwatch = () => {}
    /** The daemon it is of, what it is kept by, and whether what was kept of it is what is drawn. */
    const on = daemon()
    let keptKey = ''
    let keptShown = false
    /** What she said before she was last carried on, as read, to be kept with the rest. */
    let before = null

    // What it is made with: the scope the page shows, until another is picked.
    const { parts, query } = where()
    const picked = made ? { scope: made.scope, workspace: made.workspace, epic: made.epic || '' } : scopeOf(parts, query)
    /** The scopes, under the permissions of the chip's menu. */
    const scopes = (close) => [
      section(t('Scope')),
      scopesOf(picked).map((each) => {
        const row = choice({
          label: each.label,
          about: each.about,
          chosen: each.chosen,
          act: () => {
            if (each.why) return
            picked.scope = each.value
            permission.again()
          },
          // One that cannot be picked says why, and leaves the menu as it is.
          close: each.why ? () => {} : close,
        })
        row.dataset.scope = each.value
        if (each.why) {
          row.setAttribute('aria-disabled', 'true')
          row.dataset.tip = each.why
        }
        return row
      }),
    ]
    const permission = permissionChip({ up: true, value: made ? made.preset : null, modes: PRESETS, beside: () => scopeSaid(picked.scope), rows: scopes })
    permission.node.dataset.hmz = 'aichan-permission'
    /** The chip her nous is picked from, once what there is to pick was read. */
    let chip = null

    const box = composer({
      placeholder: t('Say something to Ai-chan'),
      label: t('What to say to Ai-chan'),
      desk: { right: [permission.node] },
      submit: async (text) => {
        if (!made) return makes(text)
        // Her chat failed: no line carries it on (Section 8.4.9 of protocol/core.md).
        if (failed) throw new Error(t('This conversation failed. Start a new one.'))
        // Folded away: attached again, which carries her on, and what she then waits on answered.
        let now = held
        if (!now || !now.connected) now = (await carried(host())) || now
        const pending = now && now.standing.pending ? now.standing.pending.pending : []
        const [what, said] = told(pending, now ? now.me : '', text)
        await ask(host(), what, said)
      },
    })
    box.node.dataset.hmz = 'aichan-say'

    /** Makes the conversation of what is picked, the line its first, and goes on in it here. */
    async function makes(task) {
      const said = { ...picked, nous: chip ? chip.value() : '', preset: permission.value(), task }
      const why = missing(said)
      if (why) {
        // None picked: where one is, is opened.
        if (!said.nous.trim() && task.trim()) chip?.open()
        throw new Error(why)
      }
      const answer = await call('aichan.create', created(said))
      refresh('aichan.list')
      // The daemon wrote her nous down as the one last used, which the next opens on.
      refresh('settings.get')
      if (away) return
      // Titled by the daemon from the line's first, as the list will say it.
      made = { kind: 'chat', ...answer, scope: said.scope, epic: said.scope === 'epic' ? said.epic : '', nous: said.nous, preset: said.preset, title: task.trim().split('\n')[0].trimEnd().slice(0, TITLED) }
      showing = made
      begun()
    }

    const title = h('b', { class: 'aichan-title', 'data-hmz': 'aichan-title' })
    const pencil = iconButton('pencil', t('Rename'), {
      class: 'aichan-rename',
      'data-hmz': 'aichan-rename',
      hidden: !made,
      onclick: () => {
        const row = (rows || []).find((each) => each.id === made.id)
        retitling(title, { title: (row && row.title) || made.title || '' }, {
          back: pencil,
          saves: async (next) => {
            await call('aichan.rename', { id: made.id, title: next })
            // Named so at once, here and in the list; the list read again says so of the daemon.
            made.title = next
            rows = (rows || []).map((each) => (each.id === made.id ? { ...each, title: next } : each))
            titled()
            refresh('aichan.list')
          },
        })
      },
    })
    const back = h('button', { class: 'btn quiet small', type: 'button', 'data-hmz': 'aichan-back', onclick: () => show({ kind: 'list' }) }, t('Back'))
    fill(body, fill(whole, h('div', { class: 'aichan-crumb' }, back, title, pencil), h('div', { class: 'aichan-scroll' }, earlier, log), options, box.node))
    box.text.focus()

    /** What a conversation there is has that one not made yet has not: its face, what it was made with, and its host. */
    function begun() {
      for (const each of [log, earlier]) each.style.setProperty('--aichan-face', `url("${faceUrl(made.id)}")`)
      // Neither changes while it lasts (Section 14.3.1 of protocol/core.md): said, and picked no more.
      const fixed = t('Set when the conversation was made')
      permission.fixed(fixed)
      const nous = nousSaidChip(made.nous || '', fixed).node
      if (chip) {
        chip.leave()
        chip.node.replaceWith(nous)
        chip = null
      } else box.tray.prepend(nous)
      pencil.hidden = false
      titled()
      // Opened, it is read.
      const row = (rows || []).find((each) => each.id === made.id)
      if (row) remember(read(marks(), row))
      // What was last seen of it is drawn at once: her host is asked behind it.
      keptKey = logKey('aichan', made.id, on)
      const had = logs.open(keptKey, { of: idOf(on) })
      if (had && had.live && had.live.records.length) {
        const key = sessionOf(had.live.records)
        saidFor = JSON.stringify([key, had.live.number, had.live.epoch, Boolean(had.cut && had.cut.live)])
        saidBy = sayer(key, { chat: true, folded: true })
        for (const record of had.live.records) {
          upTo = record.seq
          log.append(...saidBy(record))
        }
        before = had.traced && had.traced[0] ? had.traced[0] : null
        if (before) fill(earlier, saidTraced({ ...before, actions: earlierOf(before.actions), chat: true }))
        keptShown = log.childElementCount > 0
        log.parentElement.scrollTop = log.parentElement.scrollHeight
      }
      unwatch = watch('', host(), draw)
    }

    if (made) begun()
    else {
      titled()
      log.append(h('p', { class: 'dim thread-empty', 'data-hmz': 'aichan-hello' }, t('Ask Ai-chan what your epics did, have her steer a session, or run something for you.')))
      // The epic shown is of a workspace its address does not say: read off the epic.
      if (picked.scope === 'epic')
        call('runs.get', { name: picked.epic }).then(
          (found) => (picked.workspace = found.workspace),
          () => {
            // No epic of this daemon's: she is held to nothing narrower than it.
            Object.assign(picked, { scope: 'daemon', epic: '' })
            permission.again()
          },
        )
      else if (!picked.workspace)
        firstWorkspace().then(
          (path) => (picked.workspace = picked.workspace || path),
          () => {},
        )
      // Her nous, picked as a new chat's is: the one she last used until another is.
      Promise.all([call('settings.get'), readBackends()]).then(
        ([settings]) => {
          if (away || made) return
          chip = modelChip('ai_chan', settings.ai_chan || '')
          box.tray.prepend(chip.node)
        },
        (error) => away || fill(box.said, problem(error)),
      )
    }

    function draw(seen) {
      held = seen.held
      if (!held) return
      const { number, records } = current(held)
      const key = sessionOf(records)
      const whose = JSON.stringify([key, number, held.epoch, false])
      const scroller = log.parentElement
      const stuck = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 60
      // What was kept of it stays drawn until her host has told all it holds: it is then added
      // to where it is the same conversation still, and drawn over at once where it is not --
      // never emptied to be filled a record at a time.
      const waits = whose !== saidFor && keptShown && !held.caught && !held.gone
      if (whose !== saidFor && !waits) {
        saidFor = whose
        saidBy = sayer(key, { chat: true, folded: true })
        upTo = -1
        failed = ''
        keptShown = false
        fill(log)
      }
      let added = false
      for (const record of waits ? [] : records) {
        if (record.seq <= upTo) continue
        upTo = record.seq
        for (const said of saidBy(record)) {
          // Over the dots, which stay at the foot while she goes on.
          if (typing.parentElement === log) typing.before(said)
          else log.append(said)
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
          (got) => {
            const opened = sessionsOf(detail)[detail.earlier - 1]
            const found = opened && got.trace.find((each) => each.key === opened.traced)
            if (!found || !found.actions.length) return
            // Drawn again only where it is not what was kept of it, and drawn already.
            if (JSON.stringify(found) !== JSON.stringify(before)) fill(earlier, saidTraced({ ...found, actions: earlierOf(found.actions), chat: true }))
            before = found
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
        // And marked so in the list, which the daemon's own does not say.
        remember(marked(marks(), 'failed', made.id, true))
      }
      failed = stands.why
      // How it stands is said by no word: the dots while she answers, the failure in the log.
      whole.dataset.state = stands.state
      // Her turn open: the box's button stops it at once, without asking (Section 14.8.3 of
      // protocol/core.md), as a chat's does.
      const answering = held.connected && turn === 'running' && !failed
      rested = held.connected && Boolean(turn) && turn !== 'running'
      box.stops(answering ? () => ask(host(), 'stop') : null)
      // What she asks mid-turn, with the answers she offers, answered by a press.
      const pending = (held.standing.pending && held.standing.pending.pending) || []
      const asked = pending.find((each) => each.options && each.options.length && (!each.owner || each.owner === held.me))
      const shown = asked ? JSON.stringify([asked.question, asked.options]) : ''
      if (options.dataset.shown !== shown) {
        options.dataset.shown = shown
        fill(options, asked ? asked.options.map((option, index) => acting(option, () => ask(host(), 'answer', { question: asked.question, text: String(index + 1) }), { kind: 'btn small', busy: t('Answering…') })) : null)
      }
      if (!typingOf(answering, pending, held.me)) typing.remove()
      else if (log.lastElementChild !== typing) log.append(typing)
      // Until her host answers, the log says it is being opened; refused, it says why instead,
      // and once it has answered nothing stands in the place of what is said next.
      met = met || held.connected
      const note = met ? '' : held.gone || t('Opening her conversation…')
      const noted = log.querySelector(':scope > .thread-empty')
      if (noted && (noted.textContent !== note || log.querySelector(':scope > .said, :scope > .aichan-typing'))) noted.remove()
      // Said only once the opening has taken a while: one opened at once never flashes it.
      if (note && !log.childElementCount) log.append(h('p', { class: ['dim thread-empty', !held.gone && 'late'], role: 'status', 'data-hmz': 'aichan-opening' }, note))
      if (stuck) scroller.scrollTop = scroller.scrollHeight
    }

    return () => {
      away = true
      // Kept as her host told it, once it had told all of it, to be drawn by when next opened.
      if (made && held && held.caught && keptKey) {
        const { number, records } = current(held)
        if (records.length) logs.put(keptKey, { daemon: on, of: idOf(on), kind: 'aichan', id: made.id, workspace: made.workspace, opened: Date.now(), detail: null, live: { epoch: held.epoch, number, records }, traced: before ? [before] : null })
      }
      unwatch()
      chip?.leave()
      if (made && rested) left(made.id)
    }
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
    asking = null
    lately = null
    for (const one of drawn.values()) one.node.remove()
    drawn.clear()
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
