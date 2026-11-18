// A new chat, as a chat app opens a new session: a plain heading in the bar, the chats that wait
// on their person listed in the middle, and the box the first message is typed into docked at
// the foot of the page, which Enter sends to start it. Under the box, at its left, where the
// chat runs -- the daemon and the folder -- and at its right how -- the model that answers it,
// starting from the chat agent that workspace remembers, and what it may touch (Sections 3.8.18
// and 3.8.21 to 3.8.23 of protocol/web.md). A new epic of a flow is a form of its own
// (views/new.js), which the sidebar opens beside this one.

import { call, daemon, given, hash, poll } from '../api.js'
import { covered, focusing, go, stays } from '../app.js'
import { environmentChip } from '../chips/environment.js'
import { modelChip } from '../chips/model.js'
import { composer } from '../composer.js'
import { NO_FOLDER, dismissing, nextSteps, stepKey } from '../desk.js'
import { fill, h, headline, iconButton, problem } from '../dom.js'
import { chatting, markOf, waitsOn } from '../epic.js'
import { permissionChip } from '../chips/permission.js'
import { chatAsk } from '../held.js'
import { readBackends } from '../pickers.js'
import { firstWorkspace, folderFiles, workspacePicker } from '../places.js'
import { bar, keep, kept } from '../shell.js'
import { glyph } from './chatbar.js'

export function mount(root, { query }) {
  // Where the chat works: the workspace the address names, or none -- a directory of its own made
  // as it starts, offered the agent remembered where `hmz web` started.
  let scratch = query.get('scratch') === '1'
  let workspace = scratch ? '' : query.get('workspace') || ''
  const place = workspacePicker(scratch ? null : workspace, (path) => {
    scratch = path === null
    workspace = path || ''
    load('')
  }, { none: true, plain: true })
  const permission = permissionChip({ up: true })
  // Before a chat there is no catalogue to complete from: `@` names a file of the folder.
  // A chat of no folder works in a directory made as it starts, which holds nothing to name yet.
  const files = folderFiles(() => (scratch ? '' : workspace))
  // What the folder has used, where a chat begun says what it has (Section 3.8.22 of protocol/web.md).
  const usage = h('a', { class: 'chip-btn desk-chip usage-chip', 'aria-label': 'Usage', 'data-hmz': 'new-usage', 'data-tip': 'What this folder has used' }, glyph('usage'))
  const used = () => usage.setAttribute('href', hash(`/settings/usage${!scratch && workspace ? `?workspace=${encodeURIComponent(workspace)}` : ''}`))
  used()
  const box = composer({
    placeholder: 'Message',
    label: 'First message',
    busy: 'Starting…',
    submit: (task) => start(task),
    complete: files.complete,
    // So Add offers the files alone: what `/`, `$` and `!` start is the chat's host's to say.
    desk: { add: ['files'], able: () => (scratch || !workspace ? NO_FOLDER : ''), left: [environmentChip('/new/chat').node, place.node], right: [permission.node, usage] },
  })
  box.node.dataset.hmz = 'start'
  const steps = h('section', { class: 'next-steps', 'aria-label': 'Next steps', 'data-hmz': 'next-steps', hidden: true })
  fill(
    root,
    h('div', { class: 'view view-new view-desk', 'data-hmz': 'new-chat' }, bar({ title: 'New chat' }), h('div', { class: 'desk-body' }, steps), h('div', { class: 'dock desk-dock' }, box.node)),
  )

  // The chats of this daemon that wait on their person, each opened by its row, and dismissed
  // from the list in this browser until it asks again.
  let runs = []
  const DISMISSED = 'hmz-next-dismissed'
  const dismissed = () => {
    try {
      return JSON.parse(kept(DISMISSED, '[]')) || []
    } catch {
      return []
    }
  }
  // What a chat waits on: what its host lists, or what this browser holds it owing once it lists none.
  const waits = (run) => waitsOn(run.name, run.asking || [])
  const keyOf = (run) => `${daemon()} ${stepKey(run, waits(run))}`
  function drawSteps() {
    const waiting = nextSteps(
      runs,
      chatting,
      (run) => markOf(run.how, { chat: true, turn: run.turn, asked: run.asking || [], epic: run.name }),
      dismissed().filter((one) => one.startsWith(`${daemon()} `)).map((one) => one.slice(daemon().length + 1)),
      waits,
    )
    steps.hidden = !waiting.length
    // The list alone, as a chat app draws it: what it is is said to whoever cannot see it.
    fill(
      steps,
      h(
        'ul',
        {},
        waiting.map((run) =>
          h(
            'li',
            { class: 'next-step', 'data-hmz': 'next-step', 'data-epic': run.name },
            h('a', { href: hash(`/epics/${encodeURIComponent(run.name)}`), title: run.task }, h('span', { class: 'dot waiting', role: 'img', 'aria-label': 'Waiting' }), h('span', { class: 'next-title' }, headline(run.task)), h('span', { class: 'next-state' }, 'Asked a question')),
            iconButton('close', 'Dismiss', {
              'data-hmz': 'next-dismiss',
              onclick: () => {
                keep(DISMISSED, JSON.stringify(dismissing(dismissed(), keyOf(run))))
                drawSteps()
              },
            }),
          ),
        ),
      ),
    )
  }
  // As many as `runs.list` answers at once: a chat waits while a host holds it, or was left lately.
  const unlisted = poll('runs.list', { limit: 200 }, 4000, (answer) => {
    if (!answer) return
    runs = answer.runs || []
    drawSteps()
  })
  // Looked at in its own view, a chat waits on nobody any more.
  window.addEventListener('hmz:seen', drawSteps)

  /** The chip the assistant's agent is picked from, as drawn last, if any. */
  let picker = null
  /** Which workspace was read last: one read after another was picked draws nothing. */
  let loading = ''

  /** Reads the CLIs here and the chat agent a workspace remembers, and sets the agent up from it. */
  async function load(agent) {
    const mine = (loading = scratch ? 'none' : workspace || 'here')
    // Asked for now: what takes the focus while this is read keeps it.
    const focus = focusing()
    fill(box.said)
    files.clear()
    picker?.node.classList.add('stale')
    try {
      if (!workspace) workspace = await firstWorkspace()
      if (mine !== loading) return
      used()
      // The address of a dialog opened over it is the dialog's own.
      if (!covered()) stays({ workspace: scratch ? '' : workspace, scratch: scratch ? '1' : '' })
      const [, settings] = await Promise.all([readBackends(workspace), call('settings.get', { workspace }).catch(() => null)])
      if (mine !== loading) return
      draw(agent || (settings && settings.chat) || (picker ? picker.value() : ''), focus)
    } catch (error) {
      if (mine !== loading) return
      fill(box.said, problem(error))
    } finally {
      if (mine === loading) picker?.node.classList.remove('stale')
    }
  }
  load(query.get('agent') || '')

  function draw(kept, focus) {
    const was = picker
    was?.leave()
    picker = modelChip('assistant', kept)
    // Under the box, at its right, before what it may touch.
    if (was) was.node.replaceWith(picker.node)
    else box.tray.prepend(picker.node)
    // Typed into next -- but not from under a dialog opened over it, out of what is typed there,
    // nor out of what took the focus while this was read.
    focus(box.text)
  }

  async function start(task) {
    const agent = picker ? picker.value() : ''
    if (!agent) {
      picker?.open()
      throw new Error('Pick a model for the chat.')
    }
    // A new chat's own host, beside every other epic here; the agent is remembered for the next.
    const started = await chatAsk(workspace, 'start', { agent, task, permission: permission.value(), remember: !scratch, scratch })
    go(`/live?${new URLSearchParams(given({ workspace: started.workspace, slot: started.slot }))}`)
  }

  // Back from making an account, the picker offers it.
  const back = () => {
    if (!location.hash.startsWith(hash('/settings'))) readBackends(workspace).catch(() => {})
  }
  window.addEventListener('hashchange', back)
  return () => {
    // Left, what is still being read draws nothing.
    loading = null
    unlisted()
    window.removeEventListener('hmz:seen', drawSteps)
    window.removeEventListener('hashchange', back)
    picker?.leave()
  }
}
