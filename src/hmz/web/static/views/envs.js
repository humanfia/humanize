// The environments of an epic going, or of a chat, as an editor lays out a workspace: every
// environment the run has open, grouped by the role that holds it with each one derived from
// another under it, and beside the list the one picked -- what it runs on and where -- with a
// panel for each thing it can really do: its Files, a Terminal in it, and its Changes. The flow
// only says which of them it opens on.
//
// `#/envs/live?workspace=…&slot=…&env=<id>&tab=<panel>` is the envs of whichever epic a host
// holds, at the address of that host, `#/live`, with `envs/` before it (Section 3.16 of
// protocol/web.md). The same frame, without its list, stands in a chat's side panel (`frame`).
//
// Each panel is a module of its own, loaded when first opened and kept, hidden, while another is
// shown -- an editor's tabs and a terminal's screen stay as they were -- and left once another
// environment is picked. It is given the frame's `ctx` (views/envs/tree.js works out the rest).

import { hash } from '../api.js'
import { stays } from '../app.js'
import { empty, fill, h, headline, pathText, problem } from '../dom.js'
import { watch } from '../epic.js'
import { hearing, hosted } from '../held.js'
import { bar, keep, kept } from '../shell.js'
import { COLOURS } from '../themes.js'
import { clampWidth, factsOf, nameOf, offOf, panelsOf, paramsOf, pick, tabOf, treeOf, usable } from './envs/tree.js'

/** Each panel's module, loaded the first time it is opened. */
const PANELS = {
  files: () => import('./envs/files.js'),
  terminal: () => import('./envs/terminal.js'),
  changes: () => import('./envs/changes.js'),
}

/** How wide the list of environments is until it is dragged, and how far a key moves it. */
const WIDE = 240
const STEP = 16

/** The tokens a theme is told to a panel by: every colour a theme sets, and the fonts. */
const TOKENS = [...COLOURS.flatMap(([, tokens]) => tokens.map(([token]) => token)), 'live', 'live-soft', 'sans', 'mono']

/** Links the frame's stylesheet into the page, once. */
function styled() {
  if (document.querySelector('link[data-hmz=envs-css]')) return
  document.head.append(h('link', { rel: 'stylesheet', href: new URL('./envs/frame.css', import.meta.url).href, 'data-hmz': 'envs-css' }))
}

/** The page's theme now: whether it is dark, and each token's value. */
export function themeNow() {
  const style = getComputedStyle(document.documentElement)
  const tokens = {}
  for (const name of TOKENS) tokens[name] = style.getPropertyValue(`--${name}`).trim()
  return { dark: document.documentElement.dataset.theme === 'dark', tokens }
}

/** Asks a question that is answered yes or no, over the page, until it is answered. */
export function confirmed(text, { yes = 'OK', no = 'Cancel' } = {}) {
  return new Promise((resolve) => {
    const dialog = h(
      'dialog',
      { class: 'envs-confirm', 'data-hmz': 'envs-confirm', 'aria-label': text },
      h('form', { method: 'dialog' }, h('p', {}, text), h('div', { class: 'row envs-confirm-row' }, h('button', { class: 'btn quiet', value: 'no' }, no), h('button', { class: 'btn danger', value: 'yes', autofocus: true }, yes))),
    )
    dialog.addEventListener('close', () => {
      resolve(dialog.returnValue === 'yes')
      dialog.remove()
    })
    document.body.append(dialog)
    dialog.showModal()
  })
}

/** Why there are no environments to show, as what is followed says it; '' where there may be. */
function why(seen, name) {
  if (!name && seen.none) return 'No epic is going here.'
  if (name && seen.error && !seen.detail) return seen.error.message
  if (name && seen.detail && !seen.detail.held && !seen.going) return 'This epic is not running: its environments are open only while it runs.'
  return ''
}

export function mount(root, { query }) {
  const name = ''
  const wanted = { workspace: query.get('workspace') || '', slot: query.get('slot') || '' }
  const head = h('div', { class: 'bar-holder' })
  const body = h('div', { class: 'envs-holder' })
  fill(root, h('div', { class: 'view view-envs', 'data-hmz': 'envs-view' }, head, body))
  let titled = ''
  const titling = (detail) => {
    const key = JSON.stringify([detail && detail.name, detail && detail.task])
    if (key === titled) return
    titled = key
    const back = detail ? hash(`/epics/${encodeURIComponent(detail.name)}`) : hash(`/live?${new URLSearchParams(Object.entries(wanted).filter(([, value]) => value))}`)
    const sub = [h('a', { href: back, 'data-hmz': 'envs-epic' }, detail ? headline(detail.task) : 'The epic going')]
    fill(head, bar({ title: 'Environments', sub }))
  }
  titling(null)
  const made = frame(body, {
    follow: (told) =>
      watch(name, wanted, (seen) => {
        titling(seen.detail)
        told(seen.held, why(seen, name))
      }),
    env: query.get('env') || '',
    tab: query.get('tab') || '',
    moved: ({ env, tab }) => stays({ ...wanted, env, tab }),
  })
  return {
    leave: made.leave,
    /** Another environment, or panel, of the same epic: picked without drawing it all again. */
    moved({ parts: next, query: asked }) {
      if (next[0] !== 'envs') return false
      if ((asked.get('workspace') || '') !== wanted.workspace || (asked.get('slot') || '') !== wanted.slot) return false
      made.show(asked.get('env') || '', asked.get('tab') || '')
      return true
    },
  }
}

/**
 * The frame, drawn into `el`: the list of a host's environments and the one picked, with its panels.
 *
 * @param {HTMLElement} el Where it is drawn.
 * @param {object} how
 * @param {(told: (state: object|null, note: string) => void) => () => void} how.follow Follows
 *   the host, telling its state as held.js holds it -- or none, and why -- until what it returns is called.
 * @param {string} [how.env] The environment asked for, by its id.
 * @param {string} [how.tab] The panel asked for.
 * @param {(now: {env: string, tab: string}) => void} [how.moved] Told whenever another is shown.
 * @param {boolean} [how.compact] Drawn in a side panel: a pick of the environment over it, no list.
 * @param {(env: string, tab: string) => string|null} [how.full] The address of the whole view, in a side panel.
 * @returns {{leave: () => void, show: (env: string, tab: string) => void}}
 */
export function frame(el, { follow, env: askedEnv = '', tab: askedTab = '', moved = () => {}, compact = false, full = null }) {
  styled()
  /** What the host holds now, and why there is nothing where there is not. */
  let state = null
  let note = ''
  let envs = []
  /** The host followed, as `{workspace, slot}`, and its key. */
  let host = null
  let hostKey = ''
  let unhear = null
  /** What is asked for: the environment by id, and the panel, until it is shown. */
  let wantEnv = askedEnv
  let wantTab = askedTab
  /** The environment shown: its id, its descriptor, its panels and who hears its messages. */
  let current = null
  let said = ''
  let left = false

  const list = h('div', { class: 'envs-tree', role: 'tree', 'aria-label': 'Environments', 'data-hmz': 'envs-tree' })
  const resizer = h('div', { class: 'envs-resizer', role: 'separator', tabindex: '0', 'aria-orientation': 'vertical', 'aria-label': 'Resize the list of environments', 'aria-valuemin': '160', 'data-hmz': 'envs-resizer' })
  const notice = h('div', { class: 'envs-notice', 'data-hmz': 'envs-notice' })
  const head = h('div', { class: 'envs-head', 'data-hmz': 'envs-head' })
  const tabs = h('div', { class: 'tabs envs-tabs', role: 'tablist', 'aria-label': 'Panels', 'data-hmz': 'envs-tabs' })
  const panes = h('div', { class: 'envs-panes', 'data-hmz': 'envs-panes' })
  const main = h('section', { class: 'envs-main', 'aria-label': 'Environment' }, notice, head, tabs, panes)
  const split = h('div', { class: 'envs-split' }, compact ? null : [h('nav', { class: 'envs-side', 'aria-label': 'Environments' }, list), resizer], main)
  fill(el, h('div', { class: ['envs', compact && 'envs-compact'], 'data-hmz': 'envs' }, split))

  // ---------------------------------------------------------------- the list, and its width

  let width = Number(kept('hmz-envs-tree', '')) || WIDE
  const widen = (to, kept_ = false) => {
    width = clampWidth(to, split.clientWidth || innerWidth)
    split.style.setProperty('--envs-tree', `${width}px`)
    resizer.setAttribute('aria-valuenow', String(width))
    if (kept_) keep('hmz-envs-tree', width === WIDE ? null : String(width))
  }
  widen(width)
  resizer.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return
    event.preventDefault()
    const from = event.clientX
    const was = width
    resizer.setPointerCapture(event.pointerId)
    resizer.classList.add('dragging')
    const move = (moving) => widen(was + moving.clientX - from)
    const up = () => {
      resizer.removeEventListener('pointermove', move)
      resizer.classList.remove('dragging')
      widen(width, true)
    }
    resizer.addEventListener('pointermove', move)
    resizer.addEventListener('pointerup', up, { once: true })
    resizer.addEventListener('pointercancel', up, { once: true })
  })
  resizer.addEventListener('dblclick', () => widen(WIDE, true))
  resizer.addEventListener('keydown', (event) => {
    const to = { ArrowLeft: width - STEP, ArrowRight: width + STEP, Home: 0, End: Infinity }[event.key]
    if (to === undefined) return
    event.preventDefault()
    widen(to, true)
  })

  list.addEventListener('click', (event) => {
    const item = event.target.closest('[data-env]')
    if (item) choose(item.dataset.env)
  })
  list.addEventListener('keydown', (event) => {
    const items = [...list.querySelectorAll('[role=treeitem]')]
    const at = items.indexOf(document.activeElement)
    const to = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: items.length - 1 }[event.key]
    if (to !== undefined) {
      event.preventDefault()
      const next = items[Math.max(0, Math.min(items.length - 1, to))]
      if (next) {
        for (const one of items) one.tabIndex = one === next ? 0 : -1
        next.focus()
      }
    } else if ((event.key === 'Enter' || event.key === ' ') && at >= 0) {
      event.preventDefault()
      choose(items[at].dataset.env)
    }
  })

  function drawList() {
    const groups = treeOf(envs)
    const items = []
    for (const group of groups) {
      items.push(h('div', { class: 'envs-role', role: 'presentation' }, group.role || 'environments'))
      const walk = (node) => {
        const one = node.env
        const chosen = current && current.id === one.id
        const state = offOf(one)
        items.push(
          h(
            'div',
            {
              class: ['envs-item', state && 'off', chosen && 'chosen'],
              role: 'treeitem',
              'aria-level': String(node.depth + 1),
              'aria-selected': String(Boolean(chosen)),
              tabindex: chosen ? '0' : '-1',
              title: one.workdir || '',
              style: { '--depth': String(node.depth) },
              'data-env': one.id,
              'data-hmz': 'envs-item',
            },
            h('span', { class: 'envs-glyph', 'aria-hidden': 'true' }, node.depth ? '↳' : '▣'),
            h('span', { class: 'envs-name' }, nameOf(one)),
            h('span', { class: 'envs-item-meta' }, state || one.backend || ''),
          ),
        )
        for (const child of node.children) walk(child)
      }
      for (const node of group.nodes) walk(node)
    }
    // Something in the list can always be reached by Tab, even before one is picked.
    if (!items.some((one) => one.tabIndex === 0)) items.find((one) => one.dataset.env)?.setAttribute('tabindex', '0')
    const focused = list.contains(document.activeElement) ? document.activeElement.dataset.env : ''
    fill(list, items)
    if (focused) list.querySelector(`[data-env="${CSS.escape(focused)}"]`)?.focus()
  }

  // ---------------------------------------------------------------- the environment shown

  function choose(id) {
    if (current && current.id === id) return
    wantEnv = id
    wantTab = ''
    render()
  }

  /** Leaves every panel of the environment shown, which is shown no more. */
  function leaveCurrent() {
    if (!current) return
    leavePanels(current)
    current.left = true
    current.handlers.clear()
    current = null
    said = ''
    fill(panes)
    fill(tabs)
    fill(head)
  }

  function leavePanels(one) {
    for (const slot of one.panes.values()) {
      slot.gone = true
      try {
        slot.made?.leave?.()
      } catch (error) {
        console.error(error)
      }
    }
    one.panes.clear()
    fill(panes)
  }

  function switchTo(env) {
    leaveCurrent()
    const one = { id: env.id, env, tab: '', panes: new Map(), handlers: new Map(), left: false, ctx: null }
    one.ctx = contextOf(one)
    current = one
    one.tab = tabOf(env, wantTab)
    wantTab = ''
    drawTabs()
  }

  function drawHead() {
    const env = current.env
    const facts = factsOf(env)
    const declared = env.declared || []
    const off = offOf(env)
    // In a side panel, the pick of every environment is in the head too.
    const key = JSON.stringify([env, envs.map((one) => [one.id, one.role, one.chain, one.open, one.available])])
    if (said === key) return
    said = key
    fill(
      head,
      h(
        'div',
        { class: 'envs-title' },
        // The tree, folded into a picker: in a side panel, and on a phone.
        envs.length > 1
          ? h(
              'select',
              { class: 'envs-select', 'aria-label': 'Environment', 'data-hmz': 'envs-select', onchange: (event) => choose(event.target.value) },
              envs.map((one) => h('option', { value: one.id, selected: one.id === env.id }, `${one.role} · ${nameOf(one)}${usable(one) ? '' : ` (${offOf(one)})`}`)),
            )
          : null,
        h('b', { class: envs.length > 1 ? 'envs-named' : '', 'data-hmz': 'envs-name' }, nameOf(env)),
        env.chain && env.role && env.chain !== env.role && !compact ? h('span', { class: 'envs-chip' }, env.role) : null,
        off ? h('span', { class: 'envs-chip off', 'data-hmz': 'envs-state' }, off) : null,
        compact && full ? h('a', { class: 'icon-btn envs-full', href: full(env.id, current.tab), 'aria-label': 'Open in its own view', title: 'Open in its own view', 'data-hmz': 'envs-full' }, '⤢') : null,
      ),
      h(
        'div',
        { class: 'envs-meta' },
        env.backend || env.provider ? h('span', { class: 'mono', 'data-hmz': 'envs-backend' }, [env.backend, env.provider].filter(Boolean).join(' · ')) : null,
        env.workdir ? h('span', { class: 'envs-workdir mono' }, pathText(env.workdir)) : null,
        facts.length ? h('span', { 'data-hmz': 'envs-facts' }, facts.join(' · ')) : null,
        declared.length ? h('span', { class: 'envs-uses', 'data-hmz': 'envs-uses', title: 'What the flow says it uses here' }, 'flow uses ', declared.join(', ')) : null,
      ),
    )
  }

  function drawTabs() {
    const env = current.env
    const declared = new Set(env.declared || [])
    fill(
      tabs,
      panelsOf(env).map((panel) =>
        h(
          'button',
          {
            type: 'button',
            role: 'tab',
            id: `envs-tab-${panel.key}`,
            'aria-selected': String(panel.key === current.tab),
            'aria-controls': `envs-pane-${panel.key}`,
            tabindex: panel.key === current.tab ? '0' : '-1',
            'data-tab': panel.key,
            'data-hmz': `envs-tab-${panel.key}`,
            onclick: () => showTab(panel.key),
          },
          panel.label,
          panel.caps.some((cap) => declared.has(cap)) ? h('span', { class: 'envs-used', title: 'The flow uses this', 'aria-label': '(the flow uses this)' }, '•') : null,
        ),
      ),
    )
  }

  tabs.addEventListener('keydown', (event) => {
    const all = [...tabs.querySelectorAll('[role=tab]')]
    const at = all.indexOf(document.activeElement)
    if (at < 0) return
    const to = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: all.length - 1 }[event.key]
    if (to === undefined) return
    event.preventDefault()
    const next = all[(to + all.length) % all.length]
    next.focus()
    showTab(next.dataset.tab)
  })

  /** Shows one panel of the environment shown, loading it the first time. */
  function showTab(key) {
    if (!current || !panelsOf(current.env).some((one) => one.key === key)) return
    current.tab = key
    for (const tab of tabs.querySelectorAll('[role=tab]')) {
      const on = tab.dataset.tab === key
      tab.setAttribute('aria-selected', String(on))
      tab.tabIndex = on ? 0 : -1
    }
    if (usable(current.env) && !current.panes.has(key)) load(current, key)
    for (const [one, slot] of current.panes) slot.el.hidden = one !== key
    tell()
  }

  let told = ''
  function tell() {
    if (!current) return
    const now = JSON.stringify([current.id, current.tab])
    if (now === told) return
    told = now
    moved({ env: current.id, tab: current.tab })
  }

  function load(one, key) {
    const label = panelsOf(one.env).find((panel) => panel.key === key).label
    const el = h('div', { class: 'envs-pane', role: 'tabpanel', id: `envs-pane-${key}`, 'aria-labelledby': `envs-tab-${key}`, 'data-hmz': `envs-pane-${key}` }, h('p', { class: 'loading', role: 'status' }, `Opening ${label}…`))
    panes.append(el)
    const slot = { el, made: null, gone: false, ready: null }
    one.panes.set(key, slot)
    slot.ready = (async () => {
      let module
      try {
        module = await PANELS[key]()
      } catch (error) {
        console.warn(error)
        if (!slot.gone) fill(el, h('div', { class: 'envs-unavailable', 'data-hmz': 'envs-unavailable' }, empty('This panel is unavailable.', ` ${label} could not be loaded here.`)))
        return null
      }
      if (slot.gone) return null
      const inner = h('div', { class: 'envs-pane-body' })
      fill(el, inner)
      try {
        const made = await module.mount(inner, one.ctx)
        if (slot.gone) {
          made?.leave?.()
          return null
        }
        slot.made = made || null
        return slot.made
      } catch (error) {
        console.error(error)
        if (!slot.gone) fill(el, problem(`${label} failed to open: ${error.message}`))
        return null
      }
    })()
  }

  // ---------------------------------------------------------------- what a panel is given

  function contextOf(one) {
    const keyOf = (key) => `hmz-env:${host ? host.workspace : ''}:${one.env.chain || one.env.role || one.id}:${key}`
    return {
      get env() {
        return one.env
      },
      call(method, params = {}) {
        if (one.left) return Promise.reject(new Error('That environment is no longer shown.'))
        if (!host) return Promise.reject(new Error('This host cannot be reached.'))
        return hosted(host, method, paramsOf(method, params, one.id))
      },
      on(type, fn) {
        if (!one.handlers.has(type)) one.handlers.set(type, new Set())
        one.handlers.get(type).add(fn)
        return () => one.handlers.get(type)?.delete(fn)
      },
      keep(key, ...value) {
        if (!value.length) {
          const raw = kept(keyOf(key), null)
          if (raw === null) return undefined
          try {
            return JSON.parse(raw)
          } catch {
            return undefined
          }
        }
        keep(keyOf(key), value[0] === null || value[0] === undefined ? null : JSON.stringify(value[0]))
        return value[0]
      },
      async open(tab, args) {
        if (one.left || one !== current) return undefined
        showTab(tab)
        const slot = one.panes.get(tab)
        if (current !== one || current.tab !== tab || !slot) return undefined
        const made = await slot.ready
        return made && made.reveal ? made.reveal(args) : undefined
      },
      confirm: (text) => confirmed(text),
      theme: themeNow,
    }
  }

  /** Tells the panels of the environment shown a message, by its type: whether one took it as its own. */
  function dispatch(message) {
    if (!current || left) return false
    let taken = false
    for (const fn of [...(current.handlers.get(message.type) || [])]) {
      try {
        if (fn(message) === true) taken = true
      } catch (error) {
        console.error(error)
      }
    }
    return taken
  }

  // A theme painted anew -- picked, or the system's light or dark gone over to -- is told to
  // every panel, as a message of its own, so that an editor or a terminal recolours in place.
  let painting = 0
  const painted = new MutationObserver(() => {
    if (painting) return
    painting = requestAnimationFrame(() => {
      painting = 0
      dispatch({ type: 'theme', ...themeNow() })
    })
  })
  painted.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'style'] })

  // ---------------------------------------------------------------- following the host

  function render() {
    if (left) return
    const next = state ? { workspace: state.workspace, slot: state.slot || '' } : null
    const key = next ? `${next.workspace}\n${next.slot}` : ''
    if (key !== hostKey) {
      if (unhear) unhear()
      unhear = null
      leaveCurrent()
      host = next
      hostKey = key
      if (host) unhear = hearing(host, dispatch)
    }
    envs = (state && state.standing.envs && state.standing.envs.envs) || []
    // What there is is shown, whatever else is said of the epic; and why not, where there is none.
    const nothing = envs.length ? '' : !state ? note || 'Reading the epic…' : note || (state.gone ? '' : 'No environment is open here yet.')
    if (!envs.length) {
      leaveCurrent()
      drawList()
      notice.hidden = false
      const reading = !state && !note
      fill(
        notice,
        state && state.gone && !note
          ? problem(state.gone)
          : reading
            ? h('p', { class: 'loading', role: 'status' }, nothing)
            : empty(nothing, ' Environments are listed here while the epic or chat that opened them runs.'),
      )
      head.hidden = tabs.hidden = panes.hidden = true
      return
    }
    // One asked for that is not listed leaves the one shown as it is.
    const listed = (id) => Boolean(id) && envs.some((one) => one.id === id)
    const env = pick(envs, listed(wantEnv) ? wantEnv : current && current.id)
    if (!current || current.id !== env.id) switchTo(env)
    else if (JSON.stringify(panelsOf(env)) !== JSON.stringify(panelsOf(current.env))) {
      // What it can do changed: the panels it can no longer have go, and its tabs are drawn again.
      current.env = env
      const have = new Set(panelsOf(env).map((one) => one.key))
      for (const [key, slot] of [...current.panes]) {
        if (have.has(key)) continue
        slot.gone = true
        try {
          slot.made?.leave?.()
        } catch (error) {
          console.error(error)
        }
        slot.el.remove()
        current.panes.delete(key)
      }
      if (!have.has(current.tab)) current.tab = tabOf(env, '')
      drawTabs()
      if (current.tab && usable(env)) showTab(current.tab)
    } else current.env = env
    wantEnv = ''
    drawList()
    drawHead()
    head.hidden = false
    panes.inert = !usable(current.env)
    if (usable(current.env)) {
      notice.hidden = true
      fill(notice)
      tabs.hidden = panes.hidden = false
      for (const tab of tabs.querySelectorAll('[role=tab]')) tab.hidden = false
      if (!current.panes.size && current.tab) showTab(current.tab)
      else if (!current.tab) {
        notice.hidden = false
        fill(notice, empty('Nothing can be opened here.', ' This environment has no files, shell or git.'))
      }
    } else {
      // Closed, or out of reach: what was last read of it stays shown, and nothing in it can be
      // changed; one never read shows nothing.
      const read = current.panes.size > 0
      tabs.hidden = panes.hidden = !read
      if (read) for (const tab of tabs.querySelectorAll('[role=tab]')) tab.hidden = !current.panes.has(tab.dataset.tab)
      notice.hidden = false
      const said = offOf(current.env) === 'closed' ? 'This environment has closed.' : 'This environment is unavailable.'
      fill(notice, h('div', { class: 'envs-off', role: 'status', 'data-hmz': 'envs-off' }, read ? h('p', {}, h('strong', {}, said), ' What was last read of it is shown; nothing in it can be changed.') : empty(said, ' Pick another, or open it again by running the flow.')))
    }
    tell()
  }

  const stop = follow((now, why_) => {
    state = now
    note = why_ || ''
    render()
  })

  return {
    leave() {
      if (left) return
      leaveCurrent()
      left = true
      stop()
      if (unhear) unhear()
      painted.disconnect()
      if (painting) cancelAnimationFrame(painting)
    },
    /** Shows the environment and panel asked for, as an address names them. */
    show(env, tab) {
      if (env && (!current || current.id !== env)) {
        wantEnv = env
        wantTab = tab
        render()
      } else if (tab && current) showTab(tab)
    },
  }
}
