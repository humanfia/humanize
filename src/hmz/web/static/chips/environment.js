// Environment: where a chat or an epic runs. Under a new chat's box it is one chip, as a chat
// app keeps where a session runs: it names the daemon the page shows -- Local, or a remote one
// this browser keeps -- and the folder picked there, and its menu holds both: `Runs on`, every
// daemon, switching the page to one as the daemon bar's menu does, on the same form; `Folder`,
// the folders of the daemon shown, opening one by its path, and no folder; and after them what
// the form adds, a new chat its `Worktree` (Section 3.8.22 of protocol/web.md). A new epic keeps
// the daemon alone on it, in the middle of the page beside the folder (Section 3.8.24).

import { daemon, hash, known, kindOf, stateOf, toDaemon } from '../api.js'
import { chipNamed } from '../desk.js'
import { h, icon } from '../dom.js'
import { t } from '../i18n.js'
import { choice, menu, section } from '../shell.js'

/** What a daemon is called on the page. */
const named = (name) => (name === 'local' ? t('Local') : name)

/**
 * @param {string} path The view the page is switched to on another daemon: the form it is on.
 * @param {object} [made]
 * @param {ReturnType<typeof import('../places.js').workspacePicker>} [made.place] The folders, as
 *   `workspacePicker` keeps them `hosted`: the chip then names the folder picked after the
 *   daemon, and its menu picks it.
 * @param {(close: () => void) => unknown} [made.rows] What the menu holds after the folders.
 * @param {boolean} [made.up] Whether the menu opens over the chip, as under a box, or under it.
 * @returns {{node: HTMLElement}}
 */
export function environmentChip(path, { place = null, rows = null, up = true } = {}) {
  const runs = h('span', { 'data-part': 'daemon' }, named(daemon()))
  const folder = place ? h('b', { 'data-part': 'folder' }, '…') : null
  const button = h(
    'button',
    { class: 'chip-btn desk-chip environment-chip', type: 'button', 'aria-label': chipNamed(t('Environment'), named(daemon())), 'data-hmz': 'environment', 'data-tip': t('Where it runs') },
    icon('home'),
    h('span', { class: 'chip-value' }, runs, folder ? [h('span', { class: 'chip-part', 'aria-hidden': 'true' }, ' · '), folder] : null),
    icon('down'),
  )
  const holder = h('div', { class: 'menu-holder' }, button)
  // The folder picked, said on the chip after the daemon: missing where its directory went.
  if (place) {
    holder.append(place.node)
    place.bind(button, { align: 'start', up }, ({ name, tip, lost }) => {
      folder.textContent = name
      button.dataset.tip = tip || t('Where it runs')
      button.setAttribute('class', `chip-btn desk-chip environment-chip${lost ? ' gone' : ''}`)
      if (lost) button.setAttribute('aria-invalid', 'true')
      else button.removeAttribute('aria-invalid')
      // Said with what it picks, as every chip under a box is.
      button.setAttribute('aria-label', chipNamed(t('Environment'), t('{daemon}, {folder}', { daemon: named(daemon()), folder: name })))
    })
  }
  let daemons = [{ name: 'local', routes: [] }]
  const read = () =>
    known().then(
      (listed) => (daemons = listed),
      () => {},
    )
  /** The folder in force, as the menu open now draws it: what the menu opens on. */
  let inForce = null
  menu(
    button,
    (close) => {
      const folders = place ? [place.rows(close)].flat(Infinity).filter(Boolean) : []
      inForce = folders.find((one) => 'folder' in one.dataset && one.getAttribute('class').split(' ').includes('chosen')) || null
      return [
        place ? section(t('Runs on')) : null,
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
          if (one.name === 'local') item.dataset.tip = t('This computer')
          return item
        }),
        h('hr'),
        choice({ label: t('New environment'), glyph: 'plus', href: hash('/settings/daemons'), close }),
        place ? [h('hr'), section(t('Folder')), folders] : null,
        rows ? [h('hr'), rows(close)] : null,
      ]
    },
    { up, label: t('Environment') },
  )
  // Two choices are in force in it, the daemon and the folder: it opens on the folder, what is
  // picked there more often than a daemon is. Heard after the menu heard the press and opened.
  if (place) button.addEventListener('click', (event) => inForce && inForce.isConnected && inForce.focus({ focusVisible: !event.detail }))
  // Read before the menu is drawn: the daemons kept now, as another tab may have added one.
  button.addEventListener('pointerdown', read)
  read()
  return { node: holder }
}
