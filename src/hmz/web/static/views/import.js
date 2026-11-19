// `#/epics/import?path=<file>`: an epic read back in from a `.hmzepic` already on this machine,
// by its path, and its Exomyth opened in place of this address -- what Humanize Desktop opens a
// file with, the page reading it from the app and sending it to the daemon shown.
// In a browser it is asked first: any page elsewhere can link here, and the page would carry
// its key.

import { call, hash, imported, refresh } from '../api.js'
import { fill, h } from '../dom.js'
import { opened, refusal } from '../importing.js'
import { bar, inApp } from '../shell.js'

export function mount(root, { query }) {
  const path = query.get('path') || ''
  const body = h('div', { class: 'view-pad', 'data-hmz': 'importing' })
  fill(root, h('div', { class: 'view' }, bar({ title: 'Import' }), body))
  let left = false
  const go = () => {
    fill(body, h('p', { class: 'loading', role: 'status' }, 'Importing…'))
    // In the app, read from it with `file_read` (Section 3.8.2 of protocol/desktop.md); in a
    // browser, by Local from its own disk.
    const importing = globalThis.__TAURI_INTERNALS__ ? opened(path).then((file) => imported(file)) : call('runs.import', { path })
    importing.then(
      (answer) => {
        if (left) return
        refresh('runs.list')
        // In place of this address, so that going back never imports it again.
        location.replace(hash(`/epics/${encodeURIComponent(answer.name)}/exomyth`))
      },
      (error) => {
        if (!left) fill(body, refusal(error))
      },
    )
  }
  // No file named, there is nothing to import: it says what it imports, and how one is picked.
  if (!path) fill(body, h('p', { class: 'dim', 'data-hmz': 'import-none' }, 'No file is named: this address imports a ', h('code', {}, '.hmzepic'), ' already on this machine, by its path. To pick one from the disk, press Import under Actions in Search.'))
  else if (inApp) go()
  else
    fill(
      body,
      h('p', { class: 'path selectable', title: path }, path),
      h('p', { class: 'row' }, h('button', { class: 'btn primary', type: 'button', autofocus: true, onclick: go }, 'Import'), h('a', { class: 'btn quiet', href: hash('/new') }, 'Cancel')),
    )
  return () => {
    left = true
  }
}
