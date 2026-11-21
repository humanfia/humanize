// Two choices that are easily taken for one another, each drawn by its own control here so that
// neither is: the daemon, and the environment.
//
// A daemon is WHICH hmz serves the page: a machine running hmz that the browser is connected
// to. It is the whole page's -- the sidebar lists that daemon's chats -- so it is picked at the
// foot of the sidebar, and on the form of a new epic in a row named `Daemon` (`daemonChip`).
//
// An environment is WHERE one chat works: where its commands run and its files live -- the
// folder itself on the daemon's machine, a new worktree of it, or a runtime saved there (an SSH
// host, a container, a cluster). It is one chat's, picked under that chat's box
// (`environmentChip`), as it starts and at any time between its turns: a chat going is moved
// there (`chat.move`, Section 4.25.9 of protocol/daemon.md). In a runtime the directory is
// chosen as a folder is on this computer: written, or browsed for where that machine's
// directories can be listed (Sections 3.8.22 and 3.6.6.28 of protocol/web.md).

import { call, daemon, hash, known, kindOf, stateOf, toDaemon } from '../api.js'
import { chipNamed } from '../desk.js'
import { fill, h, icon } from '../dom.js'
import { t } from '../i18n.js'
import { closed, opened } from '../layers.js'
import { pathPicker } from '../paths.js'
import { choice, dragged, follow, menu, section } from '../shell.js'

/** What a daemon is called on the page. */
const named = (name) => (name === 'local' ? t('Local') : name)

/**
 * The daemon the page is of, and every other this browser keeps: picking one switches the page
 * to it, on the same view.
 *
 * @param {string} path The view the page is switched to on another daemon: the form it is on.
 * @param {{up?: boolean}} [made] Whether the menu opens over the chip or under it.
 * @returns {{node: HTMLElement}}
 */
export function daemonChip(path, { up = false } = {}) {
  const button = h(
    'button',
    { class: 'chip-btn desk-chip daemon-chip', type: 'button', 'aria-label': chipNamed(t('Daemon'), named(daemon())), 'data-hmz': 'daemon', 'data-tip': t('Which hmz serves this page') },
    icon('server'),
    h('span', { class: 'chip-value' }, named(daemon())),
    icon('down'),
  )
  let daemons = [{ name: 'local', routes: [] }]
  const read = () =>
    known().then(
      (listed) => (daemons = listed),
      () => {},
    )
  menu(
    button,
    (close) => [
      h('p', { class: 'popover-lede', 'data-hmz': 'daemon-about' }, t('Which hmz serves this page: a machine running hmz that you are connected to.')),
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
        if (one.name === 'local') item.dataset.tip = t('The hmz on this computer')
        return item
      }),
      h('hr'),
      choice({ label: t('Add daemon…'), glyph: 'plus', href: hash('/settings/daemons'), close }),
    ],
    { up, label: t('Daemon') },
  )
  // Read before the menu is drawn: the daemons kept now, as another tab may have added one.
  button.addEventListener('pointerdown', read)
  read()
  return { node: h('div', { class: 'menu-holder' }, button) }
}

/**
 * The folder a new chat is of, on a chip of its own beside where it works: the folders of the
 * daemon shown, opening one by its path, and no folder.
 *
 * @param {ReturnType<typeof import('../places.js').workspacePicker>} place The folders, as
 *   `workspacePicker` keeps them `hosted`.
 * @param {{up?: boolean}} [made] Whether the menu opens over the chip, as under a box.
 * @returns {{node: HTMLElement}}
 */
export function folderChip(place, { up = true } = {}) {
  const folder = h('b', { 'data-part': 'folder' }, '…')
  const button = h('button', { class: 'chip-btn desk-chip folder-chip', type: 'button', 'aria-label': chipNamed(t('Folder'), '…'), 'data-hmz': 'folder' }, icon('folder'), h('span', { class: 'chip-value' }, folder), icon('down'))
  const holder = h('div', { class: 'menu-holder' }, button, place.node)
  // The folder picked: missing where its directory went.
  place.bind(button, { align: 'start', up }, ({ name, tip, lost }) => {
    folder.textContent = name
    button.dataset.tip = tip || t('The folder this chat is of')
    button.setAttribute('class', `chip-btn desk-chip folder-chip${lost ? ' gone' : ''}`)
    if (lost) button.setAttribute('aria-invalid', 'true')
    else button.removeAttribute('aria-invalid')
    // Said with what it picks, as every chip under a box is.
    button.setAttribute('aria-label', chipNamed(t('Folder'), name))
  })
  /** The folder in force, as the menu open now draws it: what the menu opens on. */
  let inForce = null
  menu(
    button,
    (close) => {
      const folders = [place.rows(close)].flat(Infinity).filter(Boolean)
      inForce = folders.find((one) => 'folder' in one.dataset && one.getAttribute('class').split(' ').includes('chosen')) || null
      return folders
    },
    { up, label: t('Folder') },
  )
  // Opened on the folder picked. Heard after the menu heard the press and opened.
  button.addEventListener('click', (event) => inForce && inForce.isConnected && inForce.focus({ focusVisible: !event.detail }))
  return { node: holder }
}

/** Marks a row for whoever looks for it, switched off and saying why where it cannot be picked. */
function hooked(item, hmz, off = '') {
  item.dataset.hmz = hmz
  if (off) {
    item.setAttribute('aria-disabled', 'true')
    item.dataset.tip = off
  }
  return item
}

/** What each kind of runtime is called, and the icon it is told apart by. */
const KINDS = {
  ssh: () => [t('SSH host'), 'remote'],
  docker: () => [t('Docker container'), 'box'],
  swarm: () => [t('Docker swarm'), 'server'],
  'apple-container': () => [t('Apple container'), 'box'],
  slurm: () => [t('Slurm cluster'), 'server'],
}

/** A kind of runtime as it is said, and its icon: a backend the page does not know by its own name. */
const kindSaid = (backend) => (KINDS[backend] ? KINDS[backend]() : [backend, 'server'])

/** The last part of a directory, which is what a chip has the room to say of one. */
const lastOf = (path) => String(path || '').split('/').filter(Boolean).pop() || String(path || '')

/** Whether two directories are one, however each ends. */
const same = (one, other) => String(one || '').replace(/\/+$/, '') === String(other || '').replace(/\/+$/, '')

/**
 * Where a chat works, as the chip says it: its icon, its name, and the directory there where
 * that says more than the name does.
 *
 * @param {{backend: string, provider: string, workdir: string, worktree?: boolean}} now
 * @param {string} home The chat's folder on the daemon's machine, '' for none.
 * @returns {{glyph: string, name: string, dir: string, tip: string}}
 */
export function envSaid(now, home) {
  if (now.worktree) return { glyph: 'fork', name: t('New worktree'), dir: '', tip: t('A new git worktree of the folder, which the folder itself is left out of') }
  if (now.backend === 'local') {
    const elsewhere = Boolean(now.workdir) && Boolean(home) && !same(now.workdir, home)
    return { glyph: 'computer', name: t('This computer'), dir: elsewhere ? lastOf(now.workdir) : '', tip: elsewhere ? now.workdir : t('In the folder itself, on the computer hmz runs on') }
  }
  const [kind, glyph] = kindSaid(now.backend)
  return { glyph, name: now.provider.replace(/^\[|\]$/g, '') || kind, dir: lastOf(now.workdir), tip: [kind, now.workdir].filter(Boolean).join(' · ') }
}

/**
 * Where a chat works, under its box: this computer, a new worktree where one is on offer, or a
 * runtime, with the directory there.
 *
 * @param {object} made
 * @param {() => {backend: string, provider: string, workdir: string, worktree?: boolean}} made.now
 *   Where it works now, or is to start.
 * @param {() => string} made.home The chat's folder on the daemon's machine, '' for none: where
 *   `This computer` puts it.
 * @param {(to: {backend: string, provider: string, workdir: string, worktree?: boolean}) => unknown} made.pick
 *   Told what is picked; what it throws, or rejects with, is said in the directory's form
 *   where that is open, and is the caller's to say otherwise.
 * @param {(error: Error) => void} [made.failed] Told what a pick made from the menu was refused
 *   with; one made in the directory's form is said there.
 * @param {(() => string) | null} [made.worktree] Where a new worktree may be picked: why it is
 *   not on offer now, or '' where it is.
 * @param {() => string} [made.busy] Why nothing can be picked now, or '' where it can.
 * @param {boolean} [made.folders] Whether a directory of this computer is chosen here too, as
 *   under a chat begun; a new chat's is its folder, chosen beside this chip.
 * @param {boolean} [made.up] Whether the menu opens over the chip, as under a box.
 * @returns {{node: HTMLElement, again: () => void}} `again` says where it works afresh.
 */
export function environmentChip({ now, home, pick, failed = () => {}, worktree = null, busy = () => '', folders = true, up = true }) {
  const mark = h('span', { class: 'chip-glyph', 'aria-hidden': 'true' })
  const name = h('span', { 'data-part': 'name' }, '')
  const dir = h('b', { 'data-part': 'dir' }, '')
  const dot = h('span', { class: 'chip-part', 'aria-hidden': 'true' }, ' · ')
  const button = h('button', { class: 'chip-btn desk-chip environment-chip', type: 'button', 'data-hmz': 'environment' }, mark, h('span', { class: 'chip-value' }, name, dot, dir), icon('down'))
  /** The runtimes saved on the daemon's machine, as last read. */
  let runtimes = []
  const read = () =>
    call('runtimes.list').then(
      (saved) => (runtimes = saved.runtimes || []),
      () => {},
    )

  /** Says on the worktree's row of the menu open now whether one is on offer, if it is drawn. */
  let offering = () => {}

  function again() {
    offering()
    const at = now()
    const said = envSaid(at, home())
    fill(mark, icon(said.glyph))
    name.textContent = said.name
    dir.textContent = said.dir
    dot.textContent = said.dir ? ' · ' : ''
    dot.hidden = dir.hidden = !said.dir
    button.dataset.env = at.worktree ? 'worktree' : at.backend
    button.dataset.tip = said.tip
    button.setAttribute('aria-label', chipNamed(t('Environment'), said.dir ? t('{name}, {dir}', { name: said.name, dir: said.dir }) : said.name))
  }

  // --- the directory there, chosen as a folder is: written, or browsed for.
  const problem = h('span', { class: 'hint', role: 'status' })
  const heading = h('span', { class: 'label' }, '')
  /** What the form picks a directory of: a runtime, or this computer. */
  let target = { backend: 'local', provider: '' }
  const field = pathPicker({ label: t('Directory'), placeholder: '~/project', env: () => (target.backend === 'local' ? '' : `${target.backend}${target.provider ? `@${target.provider}` : ''}`) })
  field.input.dataset.hmz = 'env-dir'
  const submit = h('button', { class: 'btn small primary', type: 'submit', 'data-hmz': 'env-dir-pick' }, t('Use this directory'))
  const form = dragged(
    h('form', { class: 'popover workdir-open env-dir-open', hidden: true, 'data-hmz': 'env-dir-form' }, h('div', { class: 'field' }, heading, field.node), h('div', { class: 'row' }, submit, h('button', { class: 'btn small quiet', type: 'button', onclick: () => shut() }, t('Cancel'))), problem),
    'false',
  )
  let unfollow = () => {}
  const layer = { node: form, anchor: button, kind: 'panel', close: shut }
  function shut() {
    if (form.hidden) return
    closed(layer)
    unfollow()
    form.hidden = true
    button.setAttribute('aria-expanded', 'false')
  }
  function ask(to) {
    target = { backend: to.backend, provider: to.provider }
    const [kind] = to.backend === 'local' ? [t('This computer')] : kindSaid(to.backend)
    heading.textContent = to.backend === 'local' ? t('Directory on this computer') : t('Directory on {name}', { name: to.provider.replace(/^\[|\]$/g, '') || kind })
    field.set(to.workdir || '')
    problem.textContent = ''
    form.hidden = false
    opened(layer)
    unfollow = follow(form, button, { align: 'start', up })
    button.setAttribute('aria-expanded', 'true')
    field.input.focus()
  }
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (submit.disabled) return
    const workdir = field.value()
    if (!workdir) return void (problem.textContent = t('Write the directory, or browse for it.'))
    submit.disabled = true
    problem.textContent = ''
    try {
      await pick({ ...target, workdir })
      shut()
    } catch (error) {
      problem.textContent = error.message
    } finally {
      submit.disabled = false
      again()
    }
  })
  // Pressed while the form is open, the chip shuts it, as it shuts its menu.
  button.addEventListener('click', (event) => {
    if (form.hidden) return
    event.stopImmediatePropagation()
    shut()
  })

  /** Picks what needs nothing more said: the caller says what it refuses. On its way while a machine is reached. */
  const take = (to) => {
    button.setAttribute('aria-busy', 'true')
    return Promise.resolve()
      .then(() => pick(to))
      .catch(failed)
      .finally(() => {
        button.removeAttribute('aria-busy')
        again()
      })
  }

  menu(
    button,
    (close) => {
      const at = now()
      const why = busy()
      /** A row that is one of the places a chat works, marked where it is the one in force. */
      const place = ({ key, label, about, glyph, chosen, act, off = () => '' }) => {
        // Why it cannot be picked, asked as it is pressed: pressed then, it picks nothing and the menu stays.
        const blocked = () => why || off()
        const item = choice({ label, about, glyph, chosen, close: () => !blocked() && close(), act: () => !blocked() && act() })
        item.setAttribute('role', 'menuitemradio')
        item.setAttribute('aria-checked', String(chosen))
        item.dataset.env = key
        item.said = () => {
          const said = blocked()
          if (said) {
            item.setAttribute('aria-disabled', 'true')
            item.dataset.tip = said
          } else {
            item.removeAttribute('aria-disabled')
            delete item.dataset.tip
          }
        }
        item.said()
        return item
      }
      const here = at.backend === 'local' && !at.worktree
      const folder = home()
      /** A new worktree: one of the places, told whether it is on offer for as long as it is drawn. */
      const tree = () => {
        const item = hooked(place({ key: 'worktree', label: t('New worktree'), about: t('A copy under git, so the folder is left as it is'), glyph: 'fork', chosen: Boolean(at.worktree), off: worktree, act: () => take({ backend: 'local', provider: '', workdir: folder, worktree: true }) }), 'new-worktree')
        offering = item.said
        return item
      }
      return [
        h('p', { class: 'popover-lede', 'data-hmz': 'environment-about' }, why || t('Where this chat’s commands run and its files live.')),
        place({ key: 'local', label: t('This computer'), about: folder ? t('In the folder {name}', { name: lastOf(folder) }) : t('In a directory of its own'), glyph: 'computer', chosen: here && (!folders || !at.workdir || !folder || same(at.workdir, folder)), act: () => take({ backend: 'local', provider: '', workdir: folder }) }),
        worktree ? tree() : null,
        runtimes.length ? [h('hr'), section(t('Runtimes'))] : null,
        runtimes.map((one) => {
          const [kind, glyph] = kindSaid(one.backend)
          const chosen = at.backend === one.backend && at.provider === one.name
          return place({
            key: `${one.backend}@${one.name}`,
            label: one.name,
            about: [kind, chosen ? at.workdir : one.workdir].filter(Boolean).join(' · '),
            glyph,
            chosen,
            // Where it was saved to work; one saved with no directory is asked for one.
            act: () => (chosen ? null : one.workdir ? take({ backend: one.backend, provider: one.name, workdir: one.workdir }) : ask({ backend: one.backend, provider: one.name, workdir: '' })),
          })
        }),
        h('hr'),
        // The directory there, as a folder is chosen on this computer.
        folders || !here
          ? hooked(
              choice({
                label: t('Choose directory…'),
                about: at.backend === 'local' ? '' : at.workdir,
                glyph: 'folder',
                close: why ? () => {} : close,
                act: () => !why && ask({ backend: at.backend, provider: at.provider, workdir: at.workdir || (at.backend === 'local' ? folder : '') }),
              }),
              'env-dir-choose',
              why,
            )
          : null,
        choice({ label: t('Add runtime…'), glyph: 'plus', href: hash('/settings/runtimes'), close }),
      ]
    },
    { up, label: t('Environment') },
  )
  // Read before the menu is drawn: the runtimes saved now, as Settings may have added one.
  button.addEventListener('pointerdown', read)
  read()
  again()
  return { node: h('div', { class: 'menu-holder' }, button, form), again }
}
