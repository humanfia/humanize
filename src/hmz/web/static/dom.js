// What every view builds its page out of: elements, the few shapes the page repeats -- a
// status, a confirmation, an error, nothing yet -- and how a time or a length of time is said.

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

/** What a run ending each way is drawn with: a glyph, so nothing is said by colour alone. */
const ENDINGS = {
  running: ['●', 'running'],
  stopping: ['◐', 'stopping'],
  done: ['✔', 'done'],
  failed: ['✕', 'failed'],
  stopped: ['■', 'stopped'],
  budget: ['■', 'budget'],
  refused: ['✕', 'refused'],
  crashed: ['✕', 'crashed'],
  unfinished: ['○', 'unfinished'],
  idle: ['○', 'idle'],
}

/** A status: how a run ended, or that it is going. */
export function badge(how) {
  const [glyph, said] = ENDINGS[how] || ['·', how || 'unknown']
  const tone = { stopping: 'running', budget: 'stopped', refused: 'failed', crashed: 'failed' }[how] || how
  return h('span', { class: `badge tone-${tone}` }, h('span', { class: 'glyph', 'aria-hidden': 'true' }, glyph), said)
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
 * A button that asks before it does something that cannot be undone, in place rather than in
 * a dialog: pressed, it becomes the question and two answers.
 */
export function confirming({ label, ask, yes, no = 'Cancel', act, danger = true, small = false, busy = `${yes}…`, held = false }) {
  const holder = h('span', { class: 'confirm' })
  const start = () => {
    const doing = h('button', { class: ['btn', danger && 'danger', small && 'small'], type: 'button' }, yes)
    const keep = h('button', { class: ['btn quiet', small && 'small'], type: 'button', onclick: idle }, no)
    doing.addEventListener('click', async () => {
      doing.disabled = keep.disabled = true
      doing.textContent = busy
      try {
        await act()
        // Held, it stays busy until what it did is drawn, which draws it anew -- or, where
        // that never comes, a while.
        if (held) setTimeout(idle, 10000)
        else idle()
      } catch (error) {
        fill(holder, problem(error))
        setTimeout(idle, 4000)
      }
    })
    fill(holder, h('span', {}, ask), doing, keep)
    doing.focus()
  }
  function idle() {
    fill(holder, h('button', { class: ['btn', danger && 'danger', small && 'small'], type: 'button', onclick: start }, label))
  }
  idle()
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

/** Copies text, saying so on the button that did it. */
export function copier(label, text) {
  const button = h('button', { class: 'btn quiet small', type: 'button' }, label)
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(typeof text === 'function' ? text() : text)
      button.textContent = 'Copied'
    } catch {
      button.textContent = 'Copy failed'
    }
    setTimeout(() => (button.textContent = label), 1800)
  })
  return button
}

/** When something happened, as a moment in this browser's own time. */
export function when(stamp) {
  const at = moment(stamp)
  if (!at) return ''
  return at.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** How long ago something happened, as somebody says it. */
export function ago(stamp, now = Date.now()) {
  const at = moment(stamp)
  if (!at) return ''
  const seconds = Math.max(0, (now - at.getTime()) / 1000)
  if (seconds < 45) return 'just now'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return at.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
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

/** The seconds an ISO 8601 duration says, as a budget is written: `PT1H30M`, `P1DT2.5S`. */
export function secondsOf(duration) {
  if (typeof duration === 'number') return duration
  const said = /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?)?$/.exec(duration || '')
  if (!said) return null
  const [, days, hours, minutes, seconds] = said.map((one) => Number(one || 0))
  return days * 86400 + hours * 3600 + minutes * 60 + seconds
}

/** What a role lets the agent filling it touch, scope by scope. */
export function permitted(permission) {
  const touches = { all: 'writes', read: 'reads', none: 'keeps out of' }
  return [
    `${touches[permission.local]} its workdir`,
    `${touches[permission.user]} the rest of your home`,
    `${touches[permission.system]} the rest of the machine`,
    permission.online === 'all' ? 'goes online' : 'stays offline',
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
  down: ['m6 9 6 6 6-6'],
  close: ['M6 6l12 12', 'M18 6 6 18'],
  send: ['M12 19V5', 'm5 12 7-7 7 7'],
  stop: ['M7 7h10v10H7Z'],
  download: ['M12 4v12', 'm6 10 6 6 6-6', 'M4 20h16'],
  link: ['M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1', 'M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1'],
  resume: ['M4 12a8 8 0 1 0 2.3-5.7', 'M4 4v4h4'],
  plus: ['M12 5v14', 'M5 12h14'],
  minus: ['M5 12h14'],
  recenter: ['M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z', 'M12 2v4', 'M12 18v4', 'M2 12h4', 'M18 12h4'],
  sliders: ['M4 6h10', 'M18 6h2', 'M4 12h4', 'M12 12h8', 'M4 18h12', 'M20 18h0', 'M16 4v4', 'M10 10v4', 'M18 16v4'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
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
  return first || '(no task)'
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
