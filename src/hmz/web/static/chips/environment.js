// The Environment chip under a new chat's box, as a chat app keeps where a session runs: it
// names the daemon the page shows -- Local, or a remote one this browser keeps -- and its menu
// offers every other, switching the page to it as the daemon bar's menu does, on the same form
// (Section 3.8.22 of protocol/web.md).

import { daemon, hash, known, kindOf, stateOf, toDaemon } from '../api.js'
import { chipNamed } from '../desk.js'
import { h, icon } from '../dom.js'
import { choice, menu } from '../shell.js'

/** What a daemon is called on the page. */
const named = (name) => (name === 'local' ? 'Local' : name)

/**
 * @param {string} path The view the page is switched to on another daemon: the form it is on.
 * @returns {{node: HTMLElement}}
 */
export function environmentChip(path) {
  const button = h('button', { class: 'chip-btn desk-chip', type: 'button', 'aria-label': chipNamed('Environment', named(daemon())), 'data-hmz': 'environment', 'data-tip': 'Where it runs' }, icon('home'), h('span', { class: 'chip-value' }, named(daemon())), icon('down'))
  let daemons = [{ name: 'local', routes: [] }]
  const read = () =>
    known().then(
      (listed) => (daemons = listed),
      () => {},
    )
  menu(
    button,
    (close) => [
      daemons.map((one) => {
        const item = choice({
          label: named(one.name),
          // Local is this computer, in one row; a remote one says how it is reached, under its name.
          about: one.name === 'local' ? '' : [kindOf(one), stateOf(one.name).state].filter(Boolean).join(' · '),
          chosen: one.name === daemon(),
          act: () => one.name !== daemon() && toDaemon(one.name, path),
          close,
        })
        item.dataset.daemon = one.name
        if (one.name === 'local') item.dataset.tip = 'This computer'
        return item
      }),
      h('hr'),
      choice({ label: 'New environment', glyph: 'plus', href: hash('/settings/daemons'), close }),
    ],
    { up: true, label: 'Environment' },
  )
  // Read before the menu is drawn: the daemons kept now, as another tab may have added one.
  button.addEventListener('pointerdown', read)
  read()
  return { node: h('div', { class: 'menu-holder' }, button) }
}
