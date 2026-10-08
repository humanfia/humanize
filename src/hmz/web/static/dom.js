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
export function confirming({ label, ask, yes, no = 'Keep it', act, danger = true, small = false }) {
  const holder = h('span', { class: 'confirm' })
  const start = () => {
    const doing = h('button', { class: ['btn', danger && 'danger', small && 'small'], type: 'button' }, yes)
    const keep = h('button', { class: ['btn quiet', small && 'small'], type: 'button', onclick: idle }, no)
    doing.addEventListener('click', async () => {
      doing.disabled = keep.disabled = true
      doing.textContent = `${yes}…`
      try {
        await act()
        idle()
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
      button.textContent = 'Select it to copy'
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
