// A new chat, as a chat app opens one: the workspace it works in picked in the bar, the agent
// that answers it set up a part at a time under Options, starting from the chat agent that
// workspace remembers, and the first message typed into the box in the middle, which Enter sends
// to start it (Section 3.8.18 of protocol/web.md). `Flow` (views/new.js) is a switch away.

import { call, given, hash } from '../api.js'
import { covered, go, stays } from '../app.js'
import { composer } from '../composer.js'
import { fill, h, icon, problem } from '../dom.js'
import { chatAsk } from '../held.js'
import { freeAgentPicker, readBackends } from '../pickers.js'
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
  const options = h('div', { class: 'options', id: 'options', hidden: true, 'data-hmz': 'options' })
  const optionsChip = h('button', { class: 'chip-btn', type: 'button', 'aria-expanded': 'false', 'aria-controls': 'options' }, icon('sliders'), h('span', {}, 'Options'))
  const summary = h('span', { class: 'composer-summary' })
  const box = composer({
    placeholder: 'Message',
    label: 'First message',
    tools: [optionsChip, summary],
    busy: 'Starting…',
    submit: (task) => start(task),
  })
  box.node.dataset.hmz = 'start'
  box.node.classList.add('composer-home')
  optionsChip.addEventListener('click', () => {
    options.hidden = !options.hidden
    optionsChip.setAttribute('aria-expanded', String(!options.hidden))
  })
  fill(
    root,
    h(
      'div',
      { class: 'view view-new', 'data-hmz': 'new-chat' },
      bar({ lead: h('div', { class: 'pickers' }, newKinds('chat', () => ({ workspace, scratch })), place.node) }),
      h('div', { class: 'home' }, h('div', { class: 'home-inner' }, h('div', { class: 'home-mark', 'aria-hidden': 'true' }, h('img', { src: '/mark.svg', alt: '' })), greeting, box.node, options)),
    ),
  )

  /** The picker of the assistant's agent drawn last, if any. */
  let picker = null
  /** Which workspace was read last: one read after another was picked draws nothing. */
  let loading = ''

  /** Reads the CLIs here and the chat agent a workspace remembers, and sets the agent up from it. */
  async function load(agent) {
    const mine = (loading = scratch ? 'none' : workspace || 'here')
    fill(box.said)
    options.classList.add('stale')
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
      if (mine === loading) options.classList.remove('stale')
    }
  }
  load(query.get('agent') || '')

  function draw(kept) {
    picker?.leave()
    picker = freeAgentPicker('assistant', kept, summarise)
    fill(options, h('div', { class: 'form' }, h('section', { class: 'option-group' }, h('h3', {}, 'Agent'), h('div', { class: 'role', 'data-hmz': 'role', 'data-role': 'assistant' }, picker.node))))
    summarise()
    // Typed into next -- but not from under a dialog opened over it, out of what is typed there.
    if (!covered()) box.text.focus()
  }

  function summarise() {
    fill(summary, picker ? h('span', { class: 'chip' }, `assistant: ${picker.value() || '—'}`) : null)
  }

  async function start(task) {
    const agent = picker ? picker.value() : ''
    if (!agent) {
      options.hidden = false
      optionsChip.setAttribute('aria-expanded', 'true')
      throw new Error('Pick an agent for the chat.')
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
