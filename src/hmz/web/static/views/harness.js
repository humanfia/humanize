// A session a harness had of its own, which Humanize did not run (Section 3.5.21 of
// protocol/web.md): what was said in it, read by `chat.harness.get` and only read, with one way
// on -- `Continue in chat`, which copies it into a chat of this workspace by `chat.harness.adopt`
// and opens that chat -- offered only for a session its row says is `continuable`, and otherwise
// said not to be. Nothing is said to the session itself, and nothing of it is changed.

import { call, hash, refresh } from '../api.js'
import { acting, fill, h, headline, problem, when } from '../dom.js'
import { t } from '../i18n.js'
import { harnessName } from '../names.js'
import { nameOf } from '../places.js'
import { bar } from '../shell.js'
import { saidTraced, walked } from '../transcript.js'

export function mount(root, { parts, query }) {
  const [, harness = '', session = ''] = parts
  const workspace = query.get('workspace') || ''
  const named = { workspace, harness, session }
  const head = h('div', {}, bar({ title: t('Harness session') }))
  const box = walked(h('div', { class: 'thread', 'data-hmz': 'thread', role: 'log' }, h('p', { class: 'loading late', role: 'status' }, t('Reading its logs…'))))
  const dock = h('div', { class: 'dock' })
  let gone = false
  fill(root, h('div', { class: 'view view-harness', 'data-hmz': 'harness-session' }, head, h('div', { class: 'harness-main' }, h('div', { class: 'thread-scroll' }, h('div', { class: 'thread-column' }, box))), dock))

  const adopt = acting(
    t('Continue in chat'),
    async () => {
      const made = await call('chat.harness.adopt', named)
      refresh('chat.list')
      // It is a chat now, and no harness session of the sidebar's.
      window.dispatchEvent(new CustomEvent('hmz:harness'))
      location.hash = hash(`/chats/${encodeURIComponent(made.chat)}`)
    },
    { kind: 'btn primary', busy: t('Copying…') },
  )
  adopt.dataset.hmz = 'harness-adopt'

  call('chat.harness.get', { ...named, trace: true }).then(
    (one) => {
      if (gone) return
      const sub = [h('span', { class: 'harness-tag', 'data-hmz': 'harness-name', 'data-harness': one.harness }, harnessName(one.harness)), h('span', {}, nameOf(one.workspace)), h('span', {}, when(one.updated))]
      fill(head, bar({ title: headline(one.title || one.id), sub }))
      const read = one.trace.filter((each) => each.actions.length)
      fill(box, read.length ? saidTraced(...read.map((each) => ({ ...each, label: each.key }))) : h('p', { class: 'dim' }, t('Its logs held nothing said.')))
      const note = one.continuable ? t('Read-only. Continuing copies it into a chat here; the {harness} session stays as it is.', { harness: harnessName(one.harness) }) : t('Read-only. A session of {harness} cannot be continued in a chat.', { harness: harnessName(one.harness) })
      fill(dock, h('p', { class: 'dock-note harness-note', 'data-hmz': 'harness-note' }, h('span', {}, note), one.continuable ? adopt : null))
    },
    (error) => !gone && fill(box, problem(error)),
  )
  return () => {
    gone = true
  }
}
