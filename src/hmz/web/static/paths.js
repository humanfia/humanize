// A path on this machine, picked as an app's own file dialog picks one: the field it is written
// in, completed as it is typed, and beside it a list of what is in a directory -- the way there
// across its top, a step a click -- gone into a directory at a time and picked from.

import { get } from './api.js'
import { fill, h, icon, iconButton } from './dom.js'
import { follow } from './shell.js'

/**
 * @param {object} made
 * @param {string} [made.value] The path to begin with.
 * @param {boolean} [made.files] Whether a file is picked rather than a directory.
 * @param {string} made.label What the field is, to whoever cannot see it.
 * @param {string} [made.placeholder]
 * @param {string} [made.id]
 * @param {(path: string) => void} [made.changed] Told the path whenever it changes.
 * @param {string} [made.from] Whose paths: '' for the daemon the page is on, else `/d/<name>`.
 */
export function pathPicker({ value = '', files = false, label, placeholder = files ? '~/file' : '~/folder', id, changed = () => {}, from = '' }) {
  const list = `paths-${Math.random().toString(36).slice(2, 8)}`
  const input = h('input', { type: 'text', value, placeholder, 'aria-label': label, id, list, autocomplete: 'off', spellcheck: 'false', 'data-hmz': 'path-input' })
  const offered = h('datalist', { id: list })
  const browse = iconButton('folder', `Browse for ${label}`, { class: 'path-browse', 'data-hmz': 'path-browse' })
  const panel = h('div', { class: 'popover path-panel', role: 'dialog', 'aria-label': `Choose ${label}`, hidden: true, 'data-hmz': 'path-panel' })
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
      try {
        const { paths } = await get(`${from}/api/paths?typed=${encodeURIComponent(input.value)}`)
        fill(offered, paths.map((one) => h('option', { value: one })))
      } catch {
        fill(offered)
      }
    }, 150)
  })

  async function show(dir) {
    let read
    try {
      read = await get(`${from}/api/files?at=${encodeURIComponent(dir)}${files ? '&files=1' : ''}${hidden ? '&hidden=1' : ''}`)
    } catch (error) {
      if (dir !== '~') return show('~')
      fill(panel, h('p', { class: 'error' }, error.message))
      return
    }
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
    } }), 'Hidden')
    fill(
      panel,
      h(
        'div',
        { class: 'path-head' },
        iconButton('up', 'Up', { class: 'small', disabled: !read.up, onclick: () => read.up && show(read.up) }),
        iconButton('home', 'Home', { class: 'small', onclick: () => show('~') }),
        h('div', { class: 'crumbs-path' }, crumbs),
      ),
      h('div', { class: 'path-list', role: 'list' }, rows.length ? rows : h('p', { class: 'dim' }, files ? 'Empty' : 'No folders'), read.more ? h('p', { class: 'dim' }, `${read.more} more`) : null),
      h(
        'div',
        { class: 'path-foot' },
        toggle,
        h('span', { class: 'path-at mono', title: read.whole }, read.at),
        files ? null : h('button', { class: 'btn small primary', type: 'button', 'data-hmz': 'path-choose', onclick: () => pick(read.at) }, 'Choose'),
        h('button', { class: 'btn small quiet', type: 'button', onclick: closePanel }, 'Cancel'),
      ),
    )
    panel.querySelector('.path-entry, .crumb:last-child')?.focus()
  }

  /** Stops keeping the list by the field, once it is shut. */
  let unfollow = () => {}

  function pick(path) {
    say(path)
    closePanel()
    input.focus()
  }

  function closePanel() {
    unfollow()
    panel.hidden = true
    browse.setAttribute('aria-expanded', 'false')
    document.removeEventListener('pointerdown', outside, true)
  }

  function outside(event) {
    if (!node.contains(event.target)) closePanel()
  }

  browse.addEventListener('click', () => {
    if (!panel.hidden) return closePanel()
    panel.hidden = false
    // Against the window rather than whatever holds the field, a menu or a dialog that scrolls.
    unfollow = follow(panel, node, { align: 'end' })
    browse.setAttribute('aria-expanded', 'true')
    document.addEventListener('pointerdown', outside, true)
    // Opened where the path written is, or the directory a file written is in.
    const written = input.value.trim()
    show(written ? (files ? written.replace(/\/[^/]*$/, '') || '~' : written) : '~')
  })
  panel.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      closePanel()
      browse.focus()
    }
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
