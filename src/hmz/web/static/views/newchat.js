// A new chat, as a chat app opens one: the workspace it works in picked in the bar, the model
// that answers it picked from the chip on the box, starting from the chat agent that workspace
// remembers, and the first message typed into the box in the middle, which Enter sends
// to start it (Section 3.8.18 of protocol/web.md). `Flow` (views/new.js) is a switch away.

import { call, given, hash } from '../api.js'
import { covered, go, stays } from '../app.js'
import { modelChip } from '../chips/model.js'
import { composer } from '../composer.js'
import { fill, h, problem } from '../dom.js'
import { chatAsk } from '../held.js'
import { readBackends } from '../pickers.js'
import { firstWorkspace, workspacePicker } from '../places.js'
import { bar } from '../shell.js'
import { newKinds } from './new.js'

export function mount(root, { query }) {
  // Where the chat works: the workspace the address names, or none -- a directory of its own made
  // as it starts, offered the agent remembered where `hmz web` started.
  let scratch = query.get('scratch') === '1'
  let workspace = scratch ? '' : query.get('workspace') || ''
  const place = workspacePicker(scratch ? null : workspace, (path) => {
    scratch = path === null
    workspace = path || ''
    load('')
  }, { none: true })
  const greeting = h('h2', { class: 'greeting' }, 'What should we talk about?')
  const box = composer({
    placeholder: 'Message',
    label: 'First message',
    busy: 'Starting…',
    submit: (task) => start(task),
  })
  box.node.dataset.hmz = 'start'
  box.node.classList.add('composer-home')
  fill(
    root,
    h(
      'div',
      { class: 'view view-new', 'data-hmz': 'new-chat' },
      bar({ lead: h('div', { class: 'pickers' }, newKinds('chat', () => ({ workspace, scratch })), place.node) }),
      h('div', { class: 'home' }, h('div', { class: 'home-inner' }, h('div', { class: 'home-mark', 'aria-hidden': 'true' }, h('img', { src: '/mark.svg', alt: '' })), greeting, box.node)),
    ),
  )

  /** The chip the assistant's agent is picked from, as drawn last, if any. */
  let picker = null
  /** Which workspace was read last: one read after another was picked draws nothing. */
  let loading = ''

  /** Reads the CLIs here and the chat agent a workspace remembers, and sets the agent up from it. */
  async function load(agent) {
    const mine = (loading = scratch ? 'none' : workspace || 'here')
    fill(box.said)
    picker?.node.classList.add('stale')
    try {
      if (!workspace) workspace = await firstWorkspace()
      if (mine !== loading) return
      // The address of a dialog opened over it is the dialog's own.
      if (!covered()) stays({ workspace: scratch ? '' : workspace, scratch: scratch ? '1' : '' })
      const [, settings] = await Promise.all([readBackends(workspace), call('settings.get', { workspace }).catch(() => null)])
      if (mine !== loading) return
      draw(agent || (settings && settings.chat) || (picker ? picker.value() : ''))
    } catch (error) {
      if (mine !== loading) return
      fill(box.said, problem(error))
    } finally {
      if (mine === loading) picker?.node.classList.remove('stale')
    }
  }
  load(query.get('agent') || '')

  function draw(kept) {
    const was = picker
    was?.leave()
    picker = modelChip('assistant', kept)
    // At the right of the box's bar, by the button that sends.
    if (was) was.node.replaceWith(picker.node)
    else box.tray.append(picker.node)
    // Typed into next -- but not from under a dialog opened over it, out of what is typed there.
    if (!covered()) box.text.focus()
  }

  async function start(task) {
    const agent = picker ? picker.value() : ''
    if (!agent) {
      picker?.open()
      throw new Error('Pick a model for the chat.')
    }
    // A new chat's own host, beside every other epic here; the agent is remembered for the next.
    const started = await chatAsk(workspace, 'start', { agent, task, remember: !scratch, scratch })
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
    window.removeEventListener('hashchange', back)
    picker?.leave()
  }
}
