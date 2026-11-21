// What every view builds its page out of: elements, the few shapes the page repeats -- a
// status, a confirmation, an error, nothing yet -- and how a time or a length of time is said.

import { locale, t } from './i18n.js'
import { closed, opened, place } from './layers.js'

/** An element, its properties, and what goes in it. */
export function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag)
  return dress(el, props, kids)
}

/** The same, for a drawing. */
export function svg(tag, props = {}, ...kids) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag)
  return dress(el, props, kids)
}

function dress(el, props, kids) {
  for (const [name, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue
    if (name === 'class') el.setAttribute('class', Array.isArray(value) ? value.filter(Boolean).join(' ') : value)
    // A custom property is only set by name: assigned as a field of the style, it is ignored.
    else if (name === 'style' && typeof value === 'object') {
      for (const [property, set] of Object.entries(value)) {
        if (property.startsWith('--')) el.style.setProperty(property, set)
        else el.style[property] = set
      }
    }
    else if (name === 'dataset') Object.assign(el.dataset, value)
    else if (name.startsWith('on') && typeof value === 'function') el.addEventListener(name.slice(2), value)
    else if (name === 'text') el.textContent = value
    else el.setAttribute(name, value === true ? '' : String(value))
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === undefined || kid === null || kid === false) continue
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)))
  }
  return el
}

/** Puts what is given in place of what an element held. */
export function fill(el, ...kids) {
  el.replaceChildren()
  for (const kid of kids.flat(Infinity)) {
    if (kid === undefined || kid === null || kid === false) continue
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)))
  }
  return el
}

/** What an epic standing each way is drawn with: a glyph, so nothing is said by colour alone. */
export const MARKS = {
  running: '●',
  asking: '●',
  waiting: '●',
  stopping: '◐',
  done: '✔',
  failed: '✕',
  refused: '✕',
  crashed: '✕',
  stopped: '■',
  budget: '■',
  unfinished: '?',
}

/** The colour each way is said in, where it is not its own. */
export function tone(how) {
  return { budget: 'stopped', refused: 'failed', crashed: 'failed' }[how] || how
}

/** What each way is called in the page's language: the daemon's own word, where the page has none for it. */
const STANDS = {
  running: t('running'),
  asking: t('asking'),
  waiting: t('waiting'),
  stopping: t('stopping'),
  done: t('done'),
  failed: t('failed'),
  refused: t('refused'),
  crashed: t('crashed'),
  stopped: t('stopped'),
  budget: t('budget'),
  unfinished: t('unfinished'),
}

/** A status: how a run ended, or that it is going. */
export function badge(how) {
  return h('span', { class: `badge tone-${tone(how)}` }, h('span', { class: 'glyph', 'aria-hidden': 'true' }, MARKS[how] || '·'), STANDS[how] || how || t('unknown'))
}

/** A sentence the server refused with, said where it happened. */
export function problem(error) {
  return h('p', { class: 'error', role: 'alert' }, error instanceof Error ? error.message : String(error))
}

/** Nothing to show yet, and what to do about it. */
export function empty(title, text, ...actions) {
  return h('div', { class: 'empty' }, h('strong', {}, title), text, actions.length ? h('p', { class: 'row' }, actions) : null)
}

/**
 * A button that asks before it does something that cannot be undone, where it stands rather
 * than in a dialog: pressed, it stays as it is and the question opens by it with its two
 * answers, as a menu opens by its button, so that nothing beside it moves. The answer that
 * takes it back has the focus, and whatever closes a menu (layers.js) takes it back as well.
 */
export function confirming({ label, ask, yes, no = t('Cancel'), act, danger = true, small = false, busy = `${yes}…`, held = false }) {
  const button = h('button', { class: ['btn', danger && 'danger', small && 'small'], type: 'button', 'aria-haspopup': 'dialog', 'aria-expanded': 'false' }, label)
  const holder = h('span', { class: 'confirm' }, button)
  let asked = null
  const layer = { node: null, anchor: button, close }
  function close() {
    if (!asked) return
    closed(layer)
    asked.remove()
    asked = null
    button.setAttribute('aria-expanded', 'false')
  }
  const idle = () => {
    button.disabled = false
    button.textContent = label
  }
  const answer = async () => {
    close()
    button.disabled = true
    button.textContent = busy
    try {
      await act()
      // Held, it stays busy until what it did is drawn, which draws it anew -- or, where
      // that never comes, a while.
      if (held) setTimeout(idle, 10000)
      else idle()
    } catch (error) {
      fill(holder, problem(error))
      setTimeout(() => {
        fill(holder, button)
        idle()
      }, 4000)
    }
  }
  button.addEventListener('click', () => {
    if (asked) return close()
    const keep = h('button', { class: 'btn quiet small', type: 'button', onclick: close }, no)
    // Not what Humanize Desktop's window is dragged by, though it may open in a bar that is.
    asked = h('div', { class: 'popover row', role: 'dialog', 'aria-label': ask || label, 'data-tauri-drag-region': 'false' }, ask ? h('span', {}, ask) : null, keep, h('button', { class: ['btn small', danger && 'danger'], type: 'button', onclick: answer }, yes))
    button.after(asked)
    layer.node = asked
    opened(layer)
    // Into the line it ends, where its button stands in the far half of the window.
    const box = button.getBoundingClientRect()
    place(asked, button, { align: box.left + box.right > innerWidth ? 'end' : 'start' })
    button.setAttribute('aria-expanded', 'true')
    keep.focus()
  })
  return holder
}

/** A button that does something once pressed, saying it is busy and how it went. */
export function acting(label, act, { busy = `${label}…`, kind = 'btn', done = '' } = {}) {
  const button = h('button', { class: kind, type: 'button' }, label)
  const holder = h('span', { class: 'confirm' }, button)
  button.addEventListener('click', async () => {
    button.disabled = true
    button.textContent = busy
    holder.querySelector('.error')?.remove()
    try {
      await act()
      button.textContent = done || label
      if (done) setTimeout(() => (button.textContent = label), 1800)
    } catch (error) {
      holder.append(problem(error))
      button.textContent = label
    } finally {
      button.disabled = false
    }
  })
  return holder
}

/** Copies text, saying so on the button that did it, which stays as wide as it was: nothing by it moves. */
export function copier(label, text) {
  const button = h('button', { class: 'btn quiet small', type: 'button' }, label)
  button.addEventListener('click', async () => {
    button.style.minWidth = `${button.getBoundingClientRect().width}px`
    try {
      await navigator.clipboard.writeText(typeof text === 'function' ? text() : text)
      button.textContent = t('Copied')
    } catch {
      button.textContent = t('Copy failed')
    }
    setTimeout(() => (button.textContent = label), 1800)
  })
  return button
}

/** When something happened, as a moment in this browser's own time, written as the page's language writes one. */
export function when(stamp) {
  const at = moment(stamp)
  if (!at) return ''
  return at.toLocaleString(locale(), { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** How long ago something happened, as somebody says it. */
export function ago(stamp, now = Date.now()) {
  const at = moment(stamp)
  if (!at) return ''
  const seconds = Math.max(0, (now - at.getTime()) / 1000)
  if (seconds < 45) return t('just now')
  if (seconds < 3600) return t('{n}m ago', { n: Math.round(seconds / 60) })
  if (seconds < 86400) return t('{n}h ago', { n: Math.round(seconds / 3600) })
  return at.toLocaleDateString(locale(), { month: 'short', day: 'numeric' })
}

/** A moment an epic wrote down, or a number of seconds since the epoch. */
export function moment(stamp) {
  if (stamp === undefined || stamp === null || stamp === '') return null
  const at = typeof stamp === 'number' ? new Date(stamp * 1000) : new Date(stamp)
  return Number.isNaN(at.getTime()) ? null : at
}

/**
 * How long something has been going, as a box on the monitor says it: seconds under a minute,
 * minutes and seconds under an hour, hours and minutes above. The same rule as the terminal
 * interface's (`hmz.runtime.watching.monitor.lasting`), for clocks the page moves itself.
 */
export function lasting(seconds) {
  const s = Math.max(0, seconds)
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m${String(Math.floor(s % 60)).padStart(2, '0')}s`
  return `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`
}

/** Waits until nothing new has been asked for a moment, then does the last thing asked. */
export function settled(act, ms = 200) {
  let timer
  return (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => act(...args), ms)
  }
}

/**
 * The seconds an ISO 8601 duration says, as a budget is written: `PT1H30M`, `P1DT2.5S`, and from
 * a year on `P1Y2D` -- a year being the 365 days pydantic writes one as.
 */
export function secondsOf(duration) {
  if (typeof duration === 'number') return duration
  const said = /^P(?:(\d+)Y)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?)?$/.exec(duration || '')
  if (!said) return null
  const [, years, days, hours, minutes, seconds] = said.map((one) => Number(one || 0))
  return (years * 365 + days) * 86400 + hours * 3600 + minutes * 60 + seconds
}

/**
 * What a role lets the agent filling it touch: its preset, then each rule of its own in the
 * order said, the last that matches a path deciding it, and whether it goes online.
 */
export function permitted(permission) {
  const touches = {
    write: (path) => t('writes {path}', { path }),
    read: (path) => t('reads {path}', { path }),
    none: (path) => t('keeps out of {path}', { path }),
  }
  return [
    permission.preset,
    ...permission.granular.map((rule) => touches[rule.access](rule.path)),
    permission.network ? t('goes online') : t('stays offline'),
  ].join(' · ')
}

/**
 * The colour an agent is told apart by: the lanes, given out in the order roles appear, and
 * the last of them, grey, for one that is in no order.
 */
export function lane(index) {
  return `var(--lane-${index < 0 ? 6 : (index % 6) + 1})`
}

/** The strokes of every icon the page draws, each on a 24-unit square. */
const ICONS = {
  new: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z'],
  search: ['M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z', 'm20 20-4-4'],
  flows: ['M4 4h6v6H4Z', 'M14 4h6v6h-6Z', 'M4 14h6v6H4Z', 'M14 17h6', 'M17 14v6'],
  sidebar: ['M3 4h18v16H3Z', 'M9 4v16'],
  panel: ['M3 4h18v16H3Z', 'M15 4v16'],
  gear: ['M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z'],
  chart: ['M4 20V10', 'M10 20V4', 'M16 20v-7', 'M22 20H2'],
  chevron: ['m9 6 6 6-6 6'],
  back: ['M19 12H5', 'm11 6-6 6 6 6'],
  forward: ['M5 12h14', 'm13 6 6 6-6 6'],
  pin: ['M9 4h6l-1 6 3 3H7l3-3Z', 'M12 13v7'],
  down: ['m6 9 6 6 6-6'],
  close: ['M6 6l12 12', 'M18 6 6 18'],
  send: ['M12 19V5', 'm5 12 7-7 7 7'],
  stop: ['M7 7h10v10H7Z'],
  download: ['M12 4v12', 'm6 10 6 6 6-6', 'M4 20h16'],
  link: ['M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1', 'M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1'],
  resume: ['M4 12a8 8 0 1 0 2.3-5.7', 'M4 4v4h4'],
  plus: ['M12 5v14', 'M5 12h14'],
  minus: ['M5 12h14'],
  fit: ['M4 9V4h5', 'M15 4h5v5', 'M20 15v5h-5', 'M9 20H4v-5'],
  recenter: ['M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z', 'M12 2v4', 'M12 18v4', 'M2 12h4', 'M18 12h4'],
  sliders: ['M4 6h10', 'M18 6h2', 'M4 12h4', 'M12 12h8', 'M4 18h12', 'M20 18h0', 'M16 4v4', 'M10 10v4', 'M18 16v4'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  more: ['M4 11h2v2H4Z', 'M11 11h2v2h-2Z', 'M18 11h2v2h-2Z'],
  check: ['m5 12 5 5 9-10'],
  sun: ['M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M12 2v2', 'M12 20v2', 'M4.9 4.9l1.4 1.4', 'M17.7 17.7l1.4 1.4', 'M2 12h2', 'M20 12h2', 'M4.9 19.1l1.4-1.4', 'M17.7 6.3l1.4-1.4'],
  agent: ['M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M4 21a8 8 0 0 1 16 0'],
  thread: ['M4 5h16v11H8l-4 4Z'],
  folder: ['M3 6h6l2 2h10v11H3Z'],
  file: ['M6 3h8l4 4v14H6Z', 'M14 3v4h4'],
  up: ['M12 19V5', 'm5 12 7-7 7 7'],
  home: ['M3 11l9-8 9 8', 'M5 10v10h14V10'],
  copy: ['M9 9h11v11H9Z', 'M5 15H4V4h11v1'],
  open: ['M14 4h6v6', 'M20 4l-9 9', 'M18 14v6H4V6h6'],
  bell: ['M6 16v-5a6 6 0 0 1 12 0v5l2 2H4Z', 'M10 21h4'],
  question: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z', 'M9.5 9.5a2.5 2.5 0 0 1 5 0c0 1.7-2.5 2-2.5 4', 'M12 17h0'],
  compose: ['M11 4H4v16h16v-7', 'M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4Z'],
  pencil: ['M4 20h4L19 9l-4-4L4 16Z', 'M13 7l4 4'],
  fork: ['M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M12 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M6 9v3h12V9', 'M12 12v3'],
  archive: ['M3 5h18v4H3Z', 'M5 9v11h14V9', 'M10 13h4'],
  trash: ['M4 7h16', 'M9 7V4h6v3', 'M6 7l1 13h10l1-13'],
  computer: ['M4 5h16v11H4Z', 'M2 20h20'],
  server: ['M4 4h16v7H4Z', 'M4 13h16v7H4Z', 'M8 7.5h0', 'M8 16.5h0'],
  remote: ['M3 5h18v14H3Z', 'm7 10 3 2.5L7 15', 'M13 15h4'],
  box: ['M3 8l9-5 9 5v8l-9 5-9-5Z', 'M3 8l9 5 9-5', 'M12 13v8'],
  epic: ['M6 3v12', 'M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M18 9a9 9 0 0 1-9 9'],
}

/** An icon, drawn in the colour of the text around it and said by nothing: its button says it. */
export function icon(name) {
  return svg(
    'svg',
    { class: `icon icon-${name}`, viewBox: '0 0 24 24', width: '18', height: '18', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'square', 'stroke-linejoin': 'miter', 'aria-hidden': 'true' },
    (ICONS[name] || []).map((d) => svg('path', { d })),
  )
}

/** A button drawn as an icon alone, said by its label to whoever cannot see it. */
export function iconButton(name, label, props = {}) {
  const { class: extra, ...rest } = props
  return h('button', { type: 'button', 'aria-label': label, title: label, ...rest, class: ['icon-btn', extra] }, icon(name))
}

/** The first line of a task, which is what a run is named by in a list. */
export function headline(task) {
  const first = String(task || '').trim().split('\n')[0]
  return first || t('(no task)')
}

/** A flow as a list names it: a flow named by its path, by the last part of it. */
export function flowName(flow) {
  const said = String(flow || '')
  return /^[./~]|^git\+/.test(said) ? said.replace(/[/#]+$/, '').split(/[/#]/).pop() : said
}

/** A path on one line, its end kept and its start cut where there is no room for all of it. */
export function pathText(path) {
  return h('span', { class: 'path', title: path, 'data-path': path }, h('bdi', { dir: 'ltr' }, path))
}
