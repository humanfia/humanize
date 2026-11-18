// An environment's terminals, as an editor's terminal panel draws them: a row of tabs, one shell
// each, drawn by xterm -- on WebGL where the browser has it, else in the page -- fitted to the
// panel, with find, links that open in a new tab, wide characters measured as Unicode 11 does
// and the page's colours. A terminal lives on the host, not the page: one left open is attached
// again with its scrollback when the panel comes back, or when the daemon is reached again, and
// leaving the panel never closes one. What is typed goes as `env.term.input`, gathered a frame at
// a time and in order; what a shell says comes as `term` messages and is acknowledged once drawn,
// so a page slow to draw slows the shell rather than drowning in its output (protocol/core.md).

import { fill, h, icon, iconButton } from '../../dom.js'
import {
  binary,
  closedRefusal,
  debounced,
  Flow,
  fromBase64,
  goneRefusal,
  joined,
  missed,
  over,
  pairedRefusal,
  palette,
  parseColor,
  Tail,
  tabTitle,
  toBase64,
  Typing,
  unseen,
  utf8,
} from './terminal_flow.js'

/** The stylesheets the panel is drawn with: xterm's own, then the panel's. */
const SHEETS = ['/vendor/xterm_css.css', new URL('./terminal.css', import.meta.url).pathname]

/** The tokens a terminal's colours are taken from. */
const TOKENS = ['paper', 'surface', 'raised', 'ink', 'ink-2', 'ink-3', 'line-strong', 'cyan', 'cyan-ink', 'pink', 'pink-ink', 'gold', 'budget-ink', 'done', 'fail', 'lane-5', 'lavender']

/** How long output for a terminal not yet attached is held for it, and how much of it. */
const ORPHANS_MS = 10000
const ORPHANS_MOST = 1024 * 1024

/** Whether the page runs on a Mac, where Cmd, not Ctrl, is what copies and finds. */
const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '')

const DIM = '\x1b[2m'
const PLAIN = '\x1b[0m'

/** Links a stylesheet into the page, once however many panels ask. */
function linked(href) {
  if ([...document.querySelectorAll('link[rel=stylesheet]')].some((one) => one.getAttribute('href') === href)) return
  document.head.append(h('link', { rel: 'stylesheet', href }))
}

/** Reads what a value is kept as, a JSON object, or nothing. */
function readKept(value) {
  if (value && typeof value === 'object') return value
  try {
    const read = JSON.parse(value || '{}')
    return read && typeof read === 'object' ? read : {}
  } catch {
    return {}
  }
}

const said = (error) => (error instanceof Error ? error.message : String(error))

export async function mount(el, ctx) {
  for (const href of SHEETS) linked(href)
  const envId = ctx.env && ctx.env.id
  const state = { closed: false, left: false, started: false, active: null }
  /** @type {object[]} Each terminal's tab, in the order they are drawn. */
  const tabs = []
  /** Output for terminals being attached, until it is known what their replay holds. */
  const orphans = new Map()
  const offs = []

  const add = iconButton('plus', 'New terminal', { class: 'term-new', 'data-hmz': 'term-new' })
  const bar = h('div', { class: 'term-tabs', role: 'tablist', 'aria-label': 'Terminals', 'data-hmz': 'term-tabs' })
  const notice = h('div', { class: 'term-notice', 'data-hmz': 'term-notice', role: 'status', hidden: true })
  const stack = h('div', { class: 'term-stack', 'data-hmz': 'term-stack' })
  const finder = findBar()
  const root = h(
    'div',
    { class: 'term-panel', 'data-hmz': 'terminal' },
    h('div', { class: 'term-head' }, bar, add),
    notice,
    h('div', { class: 'term-body' }, stack, finder.node),
  )
  fill(el, root)

  const leave = () => {
    if (state.left) return
    state.left = true
    for (const off of offs.splice(0)) {
      try {
        off()
      } catch {
        // Gone already.
      }
    }
    for (const tab of tabs.splice(0)) {
      // What is typed and what it was sent are settled with the host before the page lets go,
      // drawn or not, since nobody draws it now; the terminal itself lives on, to be attached again.
      tab.typing.now()
      tab.flow.wrote(tab.flow.drawing)
      tab.flow.flush()
      tab.flow.stop()
      tab.resize.cancel()
      letGo(tab.xterm)
    }
    strays()
    root.remove()
  }

  let lib
  try {
    lib = await import('/vendor/xterm.js')
  } catch (error) {
    tell('error', h('strong', {}, 'The terminal could not be loaded.'), ' ', said(error))
    add.disabled = true
    return { leave }
  }
  if (state.left) return { leave }

  // The page's colours and font, read again whenever the theme changes.
  let looks = looked()
  finder.decorate()
  const restyle = debounced(() => {
    looks = looked()
    for (const tab of tabs) {
      tab.xterm.options.theme = looks.theme
      if (tab.xterm.options.fontFamily !== looks.font) {
        tab.xterm.options.fontFamily = looks.font
        fit(tab)
      }
    }
    finder.decorate()
  }, 30)
  const watching = new MutationObserver(restyle)
  watching.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'style', 'class'] })
  const scheme = matchMedia('(prefers-color-scheme: dark)')
  scheme.addEventListener('change', restyle)
  offs.push(() => watching.disconnect(), () => scheme.removeEventListener('change', restyle), () => restyle.cancel())

  const sizing = new ResizeObserver(() => requestAnimationFrame(() => state.active && fit(state.active)))
  sizing.observe(stack)
  offs.push(() => sizing.disconnect())

  add.addEventListener('click', () => create())
  bar.addEventListener('keydown', (event) => {
    if (event.target.closest('input')) return
    const at = tabs.indexOf(state.active)
    const to = event.key === 'ArrowRight' ? at + 1 : event.key === 'ArrowLeft' ? at - 1 : null
    if (to === null || !tabs.length) return
    event.preventDefault()
    const next = tabs[(to + tabs.length) % tabs.length]
    select(next)
    next.tabEl.focus()
  })

  offs.push(
    // Output taken, to be drawn and acknowledged here, answers `true`; that of a terminal of
    // another environment, left running there, is left to the page to acknowledge.
    ctx.on('term', (message) => {
      if (state.left || !message || !message.term) return false
      const tab = tabs.find((one) => one.term === message.term)
      if (!tab && !tabs.some(unplaced)) return false
      const bytes = fromBase64(message.data)
      if (!tab || tab.opening) held(message.term, bytes)
      else draw(tab, bytes)
      return true
    }),
    ctx.on('term_exit', (message) => {
      if (state.left || !message) return
      const tab = tabs.find((one) => one.term === message.term)
      // One not yet known -- its terminal still being opened -- is held with its output.
      if (!tab) return held(message.term, new Uint8Array(0), message.status ?? null)
      if (tab.opening) tab.ending = message.status ?? null
      else exited(tab, message.status)
    }),
    // Snapshots come again whenever the daemon is reached again: a terminal is then attached
    // again, and told only what it missed. One saying the environment closed leaves it to read.
    ctx.on('envs', (message) => {
      const envs = (message && message.envs) || []
      const mine = envs.find((one) => one.id === envId)
      if (mine ? mine.open === false : envId && envs.length) return shut()
      if (state.started) again()
    }),
    ctx.on('reconnect', () => state.started && again()),
  )
  const again = debounced(reattach, 300)
  offs.push(() => again.cancel())

  start()
  return { leave }

  async function start() {
    if (ctx.env && ctx.env.open === false) shut()
    const names = readKept(ctx.keep('term.names'))
    let listed = []
    try {
      listed = ((await ctx.call('env.term.list', {})) || {}).terms || []
    } catch (error) {
      refused(null, error)
    }
    if (state.left) return
    const live = listed.filter((one) => one.alive !== false && (!one.env || one.env === envId))
    for (const one of live) {
      const tab = made({ term: one.term, titled: one.title || '', named: names[one.term] || '' })
      tab.opening = true
    }
    const kept = ctx.keep('term.active')
    const first = tabs.find((one) => one.term === kept) || tabs[0]
    if (first) select(first)
    await Promise.all(tabs.slice().map((tab) => open(tab, tab.term)))
    if (state.left) return
    if (!tabs.length && !state.closed && notice.hidden) await create()
    state.started = true
  }

  /** A new terminal, in a tab of its own. */
  async function create() {
    if (state.closed || state.left) return
    clear()
    const tab = made({})
    select(tab)
    if (!(await open(tab, null)) && !tab.term) drop(tab)
    strays()
  }

  /** A tab, its terminal drawn and its addons loaded, not yet attached to a shell. */
  function made({ term = null, titled = '', named = '' }) {
    const xterm = new lib.Terminal({
      allowProposedApi: true,
      cursorBlink: true,
      fontFamily: looks.font,
      fontSize: 13,
      lineHeight: 1.15,
      scrollback: 10000,
      theme: looks.theme,
      macOptionIsMeta: false,
      rightClickSelectsWord: MAC,
      disableStdin: state.closed,
    })
    const host = h('div', { class: 'term-host', 'data-hmz': 'term-host', hidden: true })
    stack.append(host)
    const fitter = new lib.FitAddon()
    const search = new lib.SearchAddon()
    xterm.loadAddon(fitter)
    xterm.loadAddon(search)
    xterm.loadAddon(new lib.WebLinksAddon((event, uri) => {
      event.preventDefault()
      const opened = window.open(uri, '_blank', 'noopener,noreferrer')
      if (opened) opened.opener = null
    }))
    try {
      xterm.loadAddon(new lib.Unicode11Addon())
      xterm.unicode.activeVersion = '11'
    } catch {
      // Measured as xterm measures by default.
    }
    xterm.open(host)
    // WebGL draws fastest; where it cannot start, or its context is lost, xterm draws in the page.
    try {
      const gl = new lib.WebglAddon()
      gl.onContextLoss(() => gl.dispose())
      xterm.loadAddon(gl)
    } catch {
      // Drawn in the page.
    }
    const title = h('span', { class: 'term-title', 'data-hmz': 'term-title' })
    const dot = h('span', { class: 'term-dot', 'aria-hidden': 'true' })
    const shut_ = iconButton('close', 'Close terminal', { class: 'term-close', 'data-hmz': 'term-close', tabindex: '-1' })
    const tabEl = h('div', { class: 'term-tab', role: 'tab', 'data-hmz': 'term-tab', tabindex: '-1', 'aria-selected': 'false' }, dot, title, shut_)
    const exit = h('div', { class: 'term-exit', 'data-hmz': 'term-exit', hidden: true })
    host.append(exit)
    bar.append(tabEl)
    const tab = {
      term,
      shell: null,
      named,
      titled,
      alive: true,
      opening: false,
      ending: undefined,
      sent: null,
      xterm,
      fitter,
      search,
      host,
      tabEl,
      title,
      exit,
      tail: new Tail(),
    }
    tab.flow = flowFor(tab)
    tab.typing = new Typing({
      send: (bytes) => ctx.call('env.term.input', { term: tab.term, data: toBase64(bytes) }),
      failed: (error) => refused(tab, error),
    })
    tab.resize = debounced(() => {
      if (!tab.term || !tab.alive || state.closed || tab.opening) return
      const { cols, rows } = xterm
      if (tab.sent && tab.sent.cols === cols && tab.sent.rows === rows) return
      tab.sent = { cols, rows }
      ctx.call('env.term.resize', { term: tab.term, cols, rows }).catch((error) => refused(tab, error))
    }, 80)
    tab.retitle = () => {
      const text = tabTitle(tab)
      title.textContent = text
      tabEl.title = `${text}${tab.alive ? '' : ' (exited)'} — double-click to rename`
      shut_.setAttribute('aria-label', `Close ${text}`)
    }
    tab.retitle()
    xterm.onData((data) => type(tab, utf8(data)))
    xterm.onBinary((data) => type(tab, binary(data)))
    xterm.onTitleChange((text) => {
      tab.titled = text
      tab.retitle()
    })
    xterm.attachCustomKeyEventHandler((event) => keyed(tab, event))
    tabEl.addEventListener('click', (event) => {
      if (!event.target.closest('.term-close, input')) select(tab)
    })
    tabEl.addEventListener('auxclick', (event) => {
      if (event.button === 1) closeTab(tab)
    })
    tabEl.addEventListener('dblclick', (event) => {
      if (!event.target.closest('.term-close')) rename(tab)
    })
    tabEl.addEventListener('keydown', (event) => {
      if (event.key === 'F2') rename(tab)
      else if (event.key === 'Enter' || event.key === ' ') select(tab)
    })
    shut_.addEventListener('click', () => closeTab(tab))
    tabs.push(tab)
    return tab
  }

  /** Attaches a tab to its terminal -- or, without one, to a new one -- drawing what it holds. */
  async function open(tab, term) {
    tab.opening = true
    fit(tab, false)
    const { cols, rows } = tab.xterm
    let answer
    try {
      answer = (await ctx.call('env.term.open', term ? { term, cols, rows } : { cols, rows })) || {}
    } catch (error) {
      tab.opening = false
      refused(tab, error)
      return false
    }
    if (state.left || !tabs.includes(tab)) {
      // Closed while it was being opened: the shell the host started for it is ended too.
      if (!term && answer.term && !state.left) ctx.call('env.term.close', { term: answer.term }).catch(() => {})
      return false
    }
    const replay = fromBase64(answer.replay)
    const drawn = tab.tail.bytes.length > 0
    const was = tab.term
    tab.term = answer.term || term
    if (tab.named && was && was !== tab.term) {
      // A tab started again keeps the name it was given, under its new terminal.
      const names = readKept(ctx.keep('term.names'))
      delete names[was]
      names[tab.term] = tab.named
      ctx.keep('term.names', JSON.stringify(names))
    }
    tab.shell = answer.shell ?? tab.shell
    tab.sent = { cols, rows }
    tab.alive = true
    tab.tabEl.dataset.term = tab.term
    tab.tabEl.classList.remove('exited')
    tab.exit.hidden = true
    if (drawn) {
      // Attached again: only what it missed is drawn, or, where its scrollback no longer holds
      // what it drew last, all of it anew.
      const rest = missed(tab.tail.bytes, replay)
      if (rest === null) {
        tab.flow.flush()
        tab.xterm.reset()
        tab.xterm.write(replay)
        tab.tail.set(replay)
      } else if (rest.length) {
        tab.xterm.write(rest)
        tab.tail.push(rest)
      }
    } else {
      if (replay.length) tab.xterm.write(replay)
      tab.tail.set(replay)
    }
    // What came while it was being attached, less what the replay already held; acknowledged
    // whole, as the host counted it whole.
    const early = orphans.get(tab.term)
    orphans.delete(tab.term)
    if (early) {
      const all = joined(early.chunks)
      const rest = unseen(replay, all)
      const flow = tab.flow
      flow.got(all.length + early.lost)
      tab.tail.push(rest)
      tab.xterm.write(rest, () => flow.wrote(all.length + early.lost))
      if (early.ending !== undefined && tab.ending === undefined) tab.ending = early.ending
    }
    tab.opening = false
    tab.retitle()
    if (state.active === tab) keepActive()
    if (state.closed) tab.xterm.options.disableStdin = true
    if (tab.ending !== undefined) {
      const status = tab.ending
      tab.ending = undefined
      exited(tab, status)
    }
    // Fitted while it was being attached, it is told the size it is now.
    tab.resize()
    return true
  }

  /** Output for a terminal being attached, held until it is. */
  function held(term, bytes, ending = undefined) {
    const now = Date.now()
    for (const [id, one] of orphans) if (now - one.at > ORPHANS_MS) orphans.delete(id)
    const one = orphans.get(term) || { at: now, chunks: [], size: 0, lost: 0, ending: undefined }
    // Past what is held, output is not drawn but still acknowledged, as the host counted it.
    if (one.size + bytes.length > ORPHANS_MOST) one.lost += bytes.length
    else {
      one.chunks.push(bytes)
      one.size += bytes.length
    }
    if (ending !== undefined) one.ending = ending
    orphans.set(term, one)
  }

  /** Whether a tab is being given a terminal not yet known: output of one unknown may be its. */
  function unplaced(tab) {
    return tab.opening && !tab.term
  }

  /**
   * Acknowledges what was held and is no tab's, once no tab is still being given a terminal:
   * output of a terminal of another environment, taken while it could not be told whose it was.
   */
  function strays() {
    if (tabs.some(unplaced)) return
    for (const [term, one] of orphans) {
      if (tabs.some((tab) => tab.term === term)) continue
      orphans.delete(term)
      if (one.size + one.lost) ctx.call('env.term.ack', { term, bytes: one.size + one.lost }).catch(() => {})
    }
  }

  /**
   * What counts a tab's output for one attachment: attached again, it gets another, and what
   * the last one has yet to draw is never acknowledged to the host's new count.
   */
  function flowFor(tab) {
    return new Flow({ ack: (bytes) => tab.term && ctx.call('env.term.ack', { term: tab.term, bytes }).catch((error) => refused(tab, error)) })
  }

  /** Output drawn, and acknowledged once xterm has drawn it. */
  function draw(tab, bytes) {
    const flow = tab.flow
    tab.tail.push(bytes)
    flow.got(bytes.length)
    tab.xterm.write(bytes, () => flow.wrote(bytes.length))
  }

  /** What is typed: queued, in order, even while a terminal is attached again. */
  function type(tab, bytes) {
    if (state.closed || state.left || !tab.alive || !tab.term) return
    tab.typing.push(bytes)
  }

  /** A terminal whose shell ended: said in it, with a way to start another in its place. */
  function exited(tab, status) {
    if (!tab.alive) return
    tab.alive = false
    tab.typing.now()
    tab.flow.flush()
    const code = status === null || status === undefined ? '' : ` with status ${status}`
    tab.xterm.write(`\r\n${DIM}[exited${code}]${PLAIN}\r\n`)
    tab.tabEl.classList.add('exited')
    const restart = h('button', { class: 'btn small', type: 'button', 'data-hmz': 'term-restart', disabled: state.closed }, icon('resume'), 'Restart')
    restart.addEventListener('click', () => relaunch(tab))
    fill(tab.exit, h('span', { 'data-hmz': 'term-status' }, `Exited${code}.`), restart)
    tab.exit.hidden = false
    tab.retitle()
  }

  /** A new shell in a tab whose shell ended. */
  async function relaunch(tab) {
    if (state.closed) return
    tab.flow.stop()
    tab.xterm.reset()
    tab.tail.set(new Uint8Array(0))
    tab.titled = ''
    tab.shell = null
    const old = tab.term
    tab.term = null
    tab.flow = flowFor(tab)
    tab.exit.hidden = true
    if (old) ctx.call('env.term.close', { term: old }).catch(() => {})
    select(tab)
    if (!(await open(tab, null)) && tabs.includes(tab) && !tab.term) {
      tab.alive = true
      exited(tab, null)
    }
    strays()
  }

  async function closeTab(tab) {
    if (tab.alive && tab.term && !state.closed) {
      const sure = await ctx.confirm(`Close ${tabTitle(tab)}? What runs in it is ended.`)
      if (!sure || state.left) return
    }
    if (tab.term && !state.closed) {
      try {
        await ctx.call('env.term.close', { term: tab.term })
      } catch (error) {
        if (!goneRefusal(said(error)) && !closedRefusal(said(error))) return refused(null, error)
      }
    }
    const names = readKept(ctx.keep('term.names'))
    if (tab.term && names[tab.term]) {
      delete names[tab.term]
      ctx.keep('term.names', JSON.stringify(names))
    }
    drop(tab)
  }

  /** A tab taken away, its terminal's drawing let go; another picked in its place. */
  function drop(tab) {
    const at = tabs.indexOf(tab)
    if (at < 0) return
    tabs.splice(at, 1)
    tab.typing.stop()
    tab.flow.stop()
    tab.resize.cancel()
    letGo(tab.xterm)
    tab.host.remove()
    tab.tabEl.remove()
    if (state.active === tab) {
      state.active = null
      const next = tabs[Math.min(at, tabs.length - 1)]
      if (next) select(next)
      else finder.close()
    }
    if (!tabs.length && notice.hidden) idle()
  }

  /** No terminals: said so, with a way to open one. */
  function idle() {
    if (state.closed) return
    const button = h('button', { class: 'btn small', type: 'button', 'data-hmz': 'term-open' }, icon('plus'), 'New terminal')
    button.addEventListener('click', () => create())
    tell('quiet', 'No terminal is open here.', ' ', button)
  }

  function select(tab) {
    state.active = tab
    for (const one of tabs) {
      const on = one === tab
      one.tabEl.setAttribute('aria-selected', String(on))
      one.tabEl.tabIndex = on ? 0 : -1
      one.tabEl.classList.toggle('active', on)
      one.host.hidden = !on
    }
    keepActive()
    if (notice.dataset.kind === 'quiet') clear()
    requestAnimationFrame(() => {
      if (state.active !== tab || state.left) return
      fit(tab)
      // A name being typed on a tab, or a search, keeps the keys.
      if (!root.contains(document.activeElement) || !document.activeElement.matches('input')) tab.xterm.focus()
    })
  }

  function keepActive() {
    if (state.active && state.active.term) ctx.keep('term.active', state.active.term)
  }

  /** Fits a terminal shown to its panel, telling the host its new size a moment after. */
  function fit(tab, tell_ = true) {
    if (tab.host.hidden || !tab.host.clientWidth || !tab.host.clientHeight) return
    try {
      const size = tab.fitter.proposeDimensions()
      if (size && Number.isFinite(size.cols) && Number.isFinite(size.rows) && (size.cols !== tab.xterm.cols || size.rows !== tab.xterm.rows)) {
        tab.xterm.resize(Math.max(2, size.cols), Math.max(1, size.rows))
      }
    } catch {
      // Not measurable yet.
    }
    if (tell_) tab.resize()
  }

  function rename(tab) {
    if (tab.tabEl.querySelector('input')) return
    const input = h('input', { class: 'term-rename', 'data-hmz': 'term-rename', value: tabTitle(tab), 'aria-label': 'Terminal name', spellcheck: 'false' })
    let done = false
    const finish = (keep) => {
      if (done) return
      done = true
      if (keep) {
        tab.named = input.value.trim()
        if (tab.term) {
          const names = readKept(ctx.keep('term.names'))
          if (tab.named) names[tab.term] = tab.named
          else delete names[tab.term]
          ctx.keep('term.names', JSON.stringify(names))
        }
      }
      input.replaceWith(tab.title)
      tab.retitle()
      if (state.active === tab) tab.xterm.focus()
    }
    input.addEventListener('keydown', (event) => {
      event.stopPropagation()
      if (event.key === 'Enter') finish(true)
      else if (event.key === 'Escape') finish(false)
    })
    input.addEventListener('blur', () => finish(true))
    tab.title.replaceWith(input)
    input.focus()
    input.select()
  }

  /** The keys the panel takes before the shell does: find, copy and paste. */
  function keyed(tab, event) {
    if (event.type !== 'keydown') return true
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key
    const mod = MAC ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey
    if (mod && !event.altKey && !event.shiftKey && key === 'f') {
      event.preventDefault()
      finder.open()
      return false
    }
    if (event.ctrlKey && event.shiftKey && !event.altKey && key === 'c') {
      event.preventDefault()
      copied(tab)
      return false
    }
    if (event.ctrlKey && event.shiftKey && !event.altKey && key === 'v') {
      event.preventDefault()
      pasted(tab)
      return false
    }
    // With text selected, Ctrl+C copies it rather than interrupting, as an editor's terminal does.
    if (mod && !event.altKey && !event.shiftKey && key === 'c' && tab.xterm.hasSelection()) {
      event.preventDefault()
      copied(tab)
      return false
    }
    // Pasting is left to the browser, which xterm reads, bracketed where the shell asks.
    if (mod && !event.altKey && !event.shiftKey && key === 'v') return false
    return true
  }

  function copied(tab) {
    const text = tab.xterm.getSelection()
    if (!text) return
    navigator.clipboard?.writeText(text).catch(() => {})
  }

  function pasted(tab) {
    navigator.clipboard
      ?.readText()
      .then((text) => text && tab.xterm.paste(text))
      .catch(() => {})
  }

  /** Every terminal attached again, as when the daemon was reached again. */
  async function reattach() {
    if (state.left || state.closed) return
    await Promise.all(
      tabs
        .filter((tab) => tab.term && tab.alive && !tab.opening)
        .map((tab) => {
          tab.flow.flush()
          tab.flow.stop()
          tab.flow = flowFor(tab)
          return open(tab, tab.term)
        }),
    )
  }

  /** The environment closed: its terminals stay, to read, and nothing more is typed or opened. */
  function shut() {
    if (state.closed) return
    state.closed = true
    root.classList.add('closed')
    add.disabled = true
    for (const tab of tabs) {
      tab.xterm.options.disableStdin = true
      tab.typing.stop()
      tab.flow.stop()
      tab.exit.querySelector('[data-hmz=term-restart]')?.setAttribute('disabled', '')
    }
    tell('closed', h('strong', {}, 'This environment has closed.'), ' Its terminals are kept to read; nothing more can be typed into them.')
  }

  /** What a refusal means for a tab, or for the panel. */
  function refused(tab, error) {
    const text = said(error)
    if (closedRefusal(text)) return shut()
    if (pairedRefusal(text)) {
      if (tab && !tab.term) drop(tab)
      const retry = h('button', { class: 'btn small', type: 'button', 'data-hmz': 'term-retry' }, 'Try again')
      retry.addEventListener('click', () => create())
      return tell(
        'paired',
        h('strong', {}, 'Terminals are off for paired devices.'),
        ' This page reaches its daemon as a paired device, which may not open a shell unless the daemon allows it. On the machine the daemon runs on, turn on ',
        h('code', {}, 'envs.paired_terminals'),
        ' in its settings, then try again.',
        ' ',
        retry,
      )
    }
    if (tab && goneRefusal(text)) {
      if (tab.alive) exited(tab, null)
      return
    }
    tell('error', text)
  }

  function tell(kind, ...kids) {
    notice.dataset.kind = kind
    fill(notice, kids)
    notice.hidden = false
  }

  function clear() {
    if (state.closed) return
    notice.hidden = true
    delete notice.dataset.kind
    notice.replaceChildren()
  }

  /** The find bar over the terminal shown: Ctrl/Cmd+F, Enter for the next, Shift+Enter back. */
  function findBar() {
    const input = h('input', { class: 'term-find-input', 'data-hmz': 'term-find', type: 'search', placeholder: 'Find', 'aria-label': 'Find in terminal', spellcheck: 'false' })
    const count = h('span', { class: 'term-find-count', 'data-hmz': 'term-find-count', 'aria-live': 'polite' })
    const cased = iconButton('check', 'Match case', { class: 'term-find-case', 'aria-pressed': 'false' })
    cased.replaceChildren('Aa')
    const back = iconButton('up', 'Previous match')
    const next = iconButton('down', 'Next match')
    const shut_ = iconButton('close', 'Close find')
    const node = h('div', { class: 'term-find', 'data-hmz': 'term-finder', role: 'search', hidden: true }, input, count, cased, back, next, shut_)
    let decorations = null
    let listening = null
    const options = () => ({ caseSensitive: cased.getAttribute('aria-pressed') === 'true', incremental: false, decorations })
    const find = (forward, incremental = false) => {
      const tab = state.active
      if (!tab || !input.value) {
        tab?.search.clearDecorations()
        count.textContent = ''
        return
      }
      if (listening !== tab) {
        listening = tab
        tab.search.onDidChangeResults?.(({ resultIndex, resultCount }) => {
          if (state.active !== tab) return
          count.textContent = resultCount ? `${resultIndex + 1} of ${resultCount}` : 'No results'
        })
      }
      const found = forward ? tab.search.findNext(input.value, { ...options(), incremental }) : tab.search.findPrevious(input.value, options())
      if (!found && !decorations) count.textContent = 'No results'
    }
    input.addEventListener('input', () => find(true, true))
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault()
        find(!event.shiftKey)
      } else if (event.key === 'Escape') {
        event.preventDefault()
        close()
      }
    })
    cased.addEventListener('click', () => {
      cased.setAttribute('aria-pressed', String(cased.getAttribute('aria-pressed') !== 'true'))
      find(true, true)
    })
    back.addEventListener('click', () => find(false))
    next.addEventListener('click', () => find(true))
    shut_.addEventListener('click', () => close())
    function close() {
      node.hidden = true
      count.textContent = ''
      state.active?.search.clearDecorations()
      state.active?.xterm.focus()
    }
    return {
      node,
      open() {
        node.hidden = false
        const selected = state.active?.xterm.getSelection()
        if (selected && !selected.includes('\n')) input.value = selected
        input.focus()
        input.select()
        if (input.value) find(true, true)
      },
      close,
      decorate() {
        const theme = looks.theme
        const tint = (token, alpha) => {
          const colour = parseColor(token)
          return colour ? over(`rgba(${colour.slice(0, 3).join(', ')}, ${alpha})`, theme.background) : theme.selectionBackground
        }
        decorations = {
          matchBackground: tint(theme.yellow, 0.35),
          matchBorder: theme.yellow,
          matchOverviewRuler: theme.yellow,
          activeMatchBackground: tint(theme.cyan, 0.5),
          activeMatchBorder: theme.cyan,
          activeMatchColorOverviewRuler: theme.cyan,
        }
      },
    }
  }

  /** The page's colours as the terminal takes them, and its monospace font. */
  function looked() {
    const shown = (ctx.theme && ctx.theme()) || {}
    const page = getComputedStyle(document.documentElement)
    const dark = typeof shown.dark === 'boolean' ? shown.dark : document.documentElement.dataset.theme === 'dark'
    const given = shown.tokens || {}
    const tokens = {}
    for (const name of TOKENS) {
      let value = given[name] ?? given[`--${name}`]
      if (typeof value !== 'string' || !value.trim() || value.includes('var(')) value = page.getPropertyValue(`--${name}`)
      const colour = resolved(value)
      if (colour) tokens[name] = colour
    }
    const font = (typeof given.mono === 'string' && given.mono.trim()) || page.getPropertyValue('--mono').trim() || 'ui-monospace, Menlo, Consolas, monospace'
    const theme = palette({ dark, tokens })
    return { theme, font }
  }
}

/** A CSS colour as `#rrggbb` or `rgba(…)`, as a canvas reads any colour the browser knows. */
let painter = null
function resolved(value) {
  const text = String(value || '').trim()
  if (!text) return null
  if (parseColor(text)) return text
  painter ||= document.createElement('canvas').getContext('2d')
  if (!painter) return null
  painter.fillStyle = '#010203'
  painter.fillStyle = text
  const read = String(painter.fillStyle)
  return read === '#010203' ? null : read
}

/**
 * Lets a terminal go once what it has queued to draw is drawn: disposed at once, a terminal just
 * opened throws from the frame it had asked for.
 */
function letGo(xterm) {
  requestAnimationFrame(() =>
    setTimeout(() => {
      try {
        xterm.dispose()
      } catch {
        // Gone already.
      }
    }, 0),
  )
}
