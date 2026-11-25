// A path on this machine, picked as an app's own file dialog picks one: the field it is written
// in, completed as it is typed, and beside it a list of what is in a directory -- the way there
// across its top, a step a click -- gone into a directory at a time and picked from.

import { call } from './api.js'
import { fill, h, icon, iconButton } from './dom.js'
import { t } from './i18n.js'
import { closed, opened } from './layers.js'
import { follow } from './shell.js'

/**
 * @param {object} made
 * @param {string} [made.value] The path to begin with.
 * @param {boolean} [made.files] Whether a file is picked rather than a directory.
 * @param {string} made.label What the field is, to whoever cannot see it.
 * @param {string} [made.placeholder]
 * @param {string} [made.id]
 * @param {(path: string) => void} [made.changed] Told the path whenever it changes.
 * @param {string} [made.from] Whose paths: '' for the daemon the page is on, else its name.
 * @param {() => string} [made.env] The runtime whose machine the path is on, as `-e` spells one
 *   with no directory, read each time a directory is listed: '' for the daemon's own machine.
 *   A path there is listed where that machine can be (`paths.list` with `env`), and is not
 *   completed as it is typed.
 */
export function pathPicker({ value = '', files = false, label, placeholder = files ? '~/file' : '~/folder', id, changed = () => {}, from = '', env = () => '' }) {
  const list = `paths-${Math.random().toString(36).slice(2, 8)}`
  const input = h('input', { type: 'text', value, placeholder, 'aria-label': label, id, list, autocomplete: 'off', spellcheck: 'false', 'data-hmz': 'path-input' })
  const offered = h('datalist', { id: list })
  const browse = iconButton('folder', t('Browse for {what}', { what: label }), { class: 'path-browse', 'data-hmz': 'path-browse', 'aria-haspopup': 'dialog', 'aria-expanded': 'false' })
  const panel = h('div', { class: 'popover path-panel', role: 'dialog', 'aria-label': t('Choose {what}', { what: label }), hidden: true, 'data-hmz': 'path-panel' })
  const node = h('div', { class: 'path-picker menu-holder' }, input, browse, offered, panel)
  let hidden = false
  let at = ''

  const say = (to) => {
    input.value = to
    changed(to)
  }

  // Completed as it is typed, as a shell completes a path.
  let typed = 0
  input.addEventListener('input', () => {
    changed(input.value.trim())
    clearTimeout(typed)
    typed = setTimeout(async () => {
      // Another machine's directories are browsed for, never completed.
      if (env()) return fill(offered)
      try {
        const { paths } = await call('paths.complete', { typed: input.value }, { on: from || undefined })
        fill(offered, paths.map((one) => h('option', { value: one })))
      } catch {
        fill(offered)
      }
    }, 150)
  })

  // Which listing was asked for last: only it is drawn, whatever order the answers come in.
  let asked = 0
  async function show(dir) {
    const mine = ++asked
    // While a directory is read -- over SSH, for a daemon elsewhere -- the listing shown stays,
    // plainly on its way out, or the panel says it is reading where it has none yet.
    if (panel.querySelector('.path-list')) panel.setAttribute('aria-busy', 'true')
    else draw(h('p', { class: 'loading', role: 'status' }, t('Reading…')))
    let read
    try {
      const there = env()
      read = await call('paths.list', { at: dir, files, hidden, ...(there ? { env: there } : {}) }, { on: from || undefined })
    } catch (error) {
      if (mine !== asked) return
      // A machine that cannot be listed says so, rather than being asked again for its home.
      if (dir !== '~' && (!env() || error.status === 404)) return show('~')
      panel.removeAttribute('aria-busy')
      draw(h('p', { class: 'error' }, error.message))
      return
    }
    if (mine !== asked) return
    panel.removeAttribute('aria-busy')
    at = read.at
    // The way there, a step a click: `~`, then each directory under it.
    const steps = read.at === '~' || read.at.startsWith('~/') ? ['~', ...read.at.slice(2).split('/').filter(Boolean)] : ['/', ...read.at.split('/').filter(Boolean)]
    const crumbs = steps.map((step, index) => {
      const to = steps[0] === '~' ? ['~', ...steps.slice(1, index + 1)].join('/') : `/${steps.slice(1, index + 1).join('/')}`
      return h('button', { class: 'crumb', type: 'button', onclick: () => show(to) }, step)
    })
    const rows = read.entries.map((one) =>
      h(
        'button',
        { class: ['path-entry', one.dir ? 'dir' : 'file'], type: 'button', 'data-name': one.name, onclick: () => (one.dir ? show(join(read.at, one.name)) : pick(join(read.at, one.name))) },
        icon(one.dir ? 'folder' : 'file'),
        h('span', {}, one.name),
        one.dir ? icon('chevron') : null,
      ),
    )
    const toggle = h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: hidden, onchange: (event) => {
      hidden = event.target.checked
      show(at)
    } }), t('Hidden'))
    draw(
      h(
        'div',
        { class: 'path-head' },
        iconButton('up', t('Up'), { class: 'small', disabled: !read.up, onclick: () => read.up && show(read.up) }),
        iconButton('home', t('Home'), { class: 'small', onclick: () => show('~') }),
        h('div', { class: 'crumbs-path' }, crumbs),
      ),
      h('div', { class: 'path-list', role: 'list' }, rows.length ? rows : h('p', { class: 'dim' }, files ? t('Empty') : t('No folders')), read.more ? h('p', { class: 'dim' }, t('{count} more', { count: read.more })) : null),
      h(
        'div',
        { class: 'path-foot' },
        toggle,
        h('span', { class: 'path-at mono', title: read.whole }, read.at),
        files ? null : h('button', { class: 'btn small primary', type: 'button', 'data-hmz': 'path-choose', onclick: () => pick(read.at) }, t('Choose')),
        h('button', { class: 'btn small quiet', type: 'button', onclick: closePanel }, t('Cancel')),
      ),
    )
    panel.querySelector('.path-entry, .crumb:last-child')?.focus()
  }

  /** Stops keeping the list by the field, once it is shut. */
  let unfollow = () => {}

  /**
   * Draws the list and puts it by the field, at once rather than a frame after it has grown:
   * against the window rather than whatever holds the field, a dialog that scrolls; clear of
   * the field's own label, or of the whole form where one that floats holds it; and on the
   * side with the more room, so that a directory read, which makes it taller, does not send
   * it to the other.
   */
  function draw(...kids) {
    fill(panel, kids)
    unfollow()
    const by = node.closest('.popover') ?? node.closest('.field') ?? node
    const box = by.getBoundingClientRect()
    unfollow = follow(panel, by, { align: 'end', up: box.top > innerHeight - box.bottom })
  }

  // Closed by what closes a menu (layers.js), alone where a form that floats holds the field. It
  // stands by the field as much as by the button: the field pressed or typed into, it stays.
  const layer = { node: panel, anchor: node, kind: 'panel', back: browse, close: closePanel }

  function pick(path) {
    say(path)
    closePanel()
    input.focus()
  }

  function closePanel() {
    if (panel.hidden) return
    closed(layer)
    unfollow()
    // What is still being read is drawn no more.
    asked++
    panel.hidden = true
    browse.setAttribute('aria-expanded', 'false')
  }

  browse.addEventListener('click', () => {
    if (!panel.hidden) return closePanel()
    fill(panel)
    panel.removeAttribute('aria-busy')
    panel.hidden = false
    opened(layer)
    browse.setAttribute('aria-expanded', 'true')
    // Opened where the path written is, or the directory a file written is in.
    const written = input.value.trim()
    show(written ? (files ? written.replace(/\/[^/]*$/, '') || '~' : written) : '~')
  })

  return {
    node,
    input,
    value: () => input.value.trim(),
    set(to) {
      input.value = to
    },
  }
}

function join(dir, name) {
  return dir === '/' ? `/${name}` : `${dir.replace(/\/$/, '')}/${name}`
}
