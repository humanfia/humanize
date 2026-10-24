// `#/epics/import?path=<file>`: an epic read back in from a `.hmzepic` already on this machine,
// by its path, and its Exomyth opened in place of this address -- what Humanize Desktop opens a
// file with.
// In a browser it is asked first: any page elsewhere can link here, and the page would carry
// its key.

import { hash, post, refresh } from '../api.js'
import { fill, h } from '../dom.js'
import { refusal } from '../importing.js'
import { bar, inApp } from '../shell.js'

export function mount(root, { query }) {
  const path = query.get('path') || ''
  const body = h('div', { class: 'view-pad', 'data-hmz': 'importing' })
  fill(root, h('div', { class: 'view' }, bar({ title: 'Import' }), body))
  let left = false
  const go = () => {
    fill(body, h('p', { class: 'loading', role: 'status' }, 'Importing…'))
    post('/api/runs/import', { path }).then(
      (answer) => {
        if (left) return
        refresh('/api/runs')
        // In place of this address, so that going back never imports it again.
        location.replace(hash(`/epics/${encodeURIComponent(answer.name)}/exomyth`))
      },
      (error) => {
        if (!left) fill(body, refusal(error))
      },
    )
  }
  if (inApp) go()
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
