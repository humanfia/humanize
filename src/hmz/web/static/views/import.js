// `#/epics/import?path=<file>`: an epic read back in from a `.hmzepic` already on this machine,
// by its path, and its Exomyth opened in place of this address, or the chat where it is one an
// earlier hmz kept as an epic -- what Humanize Desktop opens a
// file with, the page reading it from the app and sending it to the daemon shown.
// In a browser it is asked first: any page elsewhere can link here, and the page would carry
// its key.

import { call, hash, imported, refresh } from '../api.js'
import { fill, h } from '../dom.js'
import { pieces, t } from '../i18n.js'
import { opened, refusal } from '../importing.js'
import { bar, inApp } from '../shell.js'

export function mount(root, { query }) {
  const path = query.get('path') || ''
  const body = h('div', { class: 'view-pad', 'data-hmz': 'importing' })
  fill(root, h('div', { class: 'view' }, bar({ title: t('Import') }), body))
  let left = false
  const go = () => {
    fill(body, h('p', { class: 'loading', role: 'status' }, t('Importing…')))
    // In the app, read from it with `file_read` (Section 3.8.2 of protocol/desktop.md); in a
    // browser, by Local from its own disk.
    const importing = globalThis.__TAURI_INTERNALS__ ? opened(path).then((file) => imported(file)) : call('runs.import', { path })
    importing.then(
      (answer) => {
        if (left) return
        refresh('runs.list')
        refresh('chat.list')
        const name = encodeURIComponent(answer.name)
        // In place of this address, so that going back never imports it again. A chat an
        // earlier hmz kept as an epic is imported as a chat, which has no Exomyth (Section
        // 3.5.20.3 of protocol/web.md).
        call('chat.get', { chat: answer.name }).then(
          () => left || location.replace(hash(`/chats/${name}`)),
          () => left || location.replace(hash(`/epics/${name}/exomyth`)),
        )
      },
      (error) => {
        if (!left) fill(body, refusal(error))
      },
    )
  }
  // No file named, there is nothing to import: it says what it imports, and how one is picked.
  if (!path) fill(body, h('p', { class: 'dim', 'data-hmz': 'import-none' }, pieces('No file is named: this address imports a {file} already on this machine, by its path. To pick one from the disk, press Import under Actions in Search.', { file: h('code', {}, '.hmzepic') })))
  else if (inApp) go()
  else
    fill(
      body,
      h('p', { class: 'path selectable', title: path }, path),
      h('p', { class: 'row' }, h('button', { class: 'btn primary', type: 'button', autofocus: true, onclick: go }, t('Import')), h('a', { class: 'btn quiet', href: hash('/new') }, t('Cancel'))),
    )
  return () => {
    left = true
  }
}
