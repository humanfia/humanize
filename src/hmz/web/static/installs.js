// Asking before hmz is installed on a remote daemon's machine (Section 3.13.22 of
// protocol/web.md): while a daemon is `asking`, a dialog over whatever the page shows, one daemon
// at a time. `Install` answers yes; `Not now`, Escape and a press beside it answer no; and it
// goes, unanswered, once the daemon is no longer asking.

import { answer, onState } from './api.js'
import { h } from './dom.js'
import { t } from './i18n.js'
import { modal } from './layers.js'

/** The daemons asking, in the order they began to. */
const asking = new Set()
/** The dialog shown, and the daemon it asks about. */
let shown = null

/** Asks about the daemon that has waited longest, where nothing is asked yet. */
function ask() {
  const [name] = asking
  if (shown || name === undefined) return
  const text = t('hmz is not installed on {name}. Install it?', { name })
  const dialog = h(
    'dialog',
    { class: 'install-dialog', 'data-hmz': 'install-dialog', 'data-daemon': name, 'aria-label': text },
    h('p', {}, text),
    h(
      'div',
      { class: 'row' },
      h('button', { class: 'btn quiet', type: 'button', autofocus: true, 'data-hmz': 'install-no', onclick: () => dialog.close('no') }, t('Not now')),
      h('button', { class: 'btn primary', type: 'button', 'data-hmz': 'install-yes', onclick: () => dialog.close('yes') }, t('Install')),
    ),
  )
  shown = { name, dialog }
  dialog.addEventListener('close', () => {
    dialog.remove()
    shown = null
    // The page gone elsewhere under it, the daemon still asks; no longer asking, nobody is answered.
    if (dialog.returnValue !== 'away' && asking.delete(name)) answer(name, dialog.returnValue === 'yes')
    ask()
  })
  document.body.append(dialog)
  modal(dialog, 'away')
}

onState((name, { state }) => {
  if (state === 'asking') asking.add(name)
  else if (asking.delete(name) && shown?.name === name) shown.dialog.close('away')
  ask()
})
