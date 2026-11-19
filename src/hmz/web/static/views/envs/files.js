// The Files panel of an environment: its files as an editor lays them out. On the left the
// explorer -- the tree, listed a directory at a time as it is opened -- or a search through
// every file; on the right the files open, as tabs over one CodeMirror editor, written back a
// moment after each edit stops (`if_match` keeps a write from going over someone else's), with a
// banner where they did; and a status bar under it. Ctrl/Cmd+P opens a file by a few of the
// letters of its path. What can be decided without a page is in files_logic.js.

import { fill, h, icon, iconButton } from '../../dom.js'
import { menuOn } from '../../ui.js'
import * as L from './files_logic.js'

/** How tall a row of the explorer and of the search's results is, in pixels. */
const ROW = 22

/** How often the files open are looked at for changes made elsewhere, in milliseconds. */
const POLL = 5000

/** Links the panel's stylesheet, once. */
function stylesheet() {
  if (document.querySelector('link[data-hmz-sheet="envs-files"]')) return
  document.head.append(h('link', { rel: 'stylesheet', href: '/views/envs/files.css', 'data-hmz-sheet': 'envs-files' }))
}

const said = (error) => (error instanceof Error ? error.message : String(error))

/**
 * A long list drawn only where it is seen: each row placed at its height, kept while it is in
 * view and unchanged (so what has focus in it keeps it), and those scrolled away removed.
 */
function virtual(scroller, { key, sig, draw }) {
  const sizer = h('div', { class: 'files-sizer' })
  scroller.append(sizer)
  const live = new Map()
  let rows = []
  function paint() {
    const top = scroller.scrollTop
    const tall = scroller.clientHeight || 600
    const first = Math.max(0, Math.floor(top / ROW) - 8)
    const last = Math.min(rows.length, Math.ceil((top + tall) / ROW) + 8)
    const keep = new Set()
    for (let i = first; i < last; i++) {
      const row = rows[i]
      const k = key(row)
      const s = sig(row)
      keep.add(k)
      let held = live.get(k)
      if (!held || held.sig !== s) {
        const el = draw(row, i)
        if (held) held.el.replaceWith(el)
        else sizer.append(el)
        held = { el, sig: s }
        live.set(k, held)
      }
      held.el.style.transform = `translateY(${i * ROW}px)`
    }
    for (const [k, held] of live) {
      if (keep.has(k)) continue
      held.el.remove()
      live.delete(k)
    }
  }
  scroller.addEventListener('scroll', () => requestAnimationFrame(paint), { passive: true })
  return {
    set(next) {
      rows = next
      sizer.style.height = `${rows.length * ROW}px`
      paint()
    },
    get rows() {
      return rows
    },
    /** Scrolls a row into view, if it is not. */
    show(index) {
      if (index < 0) return
      const top = index * ROW
      if (top < scroller.scrollTop) scroller.scrollTop = top
      else if (top + ROW > scroller.scrollTop + scroller.clientHeight) scroller.scrollTop = top + ROW - scroller.clientHeight
      paint()
    },
    paint,
    element: (k) => live.get(k)?.el || null,
  }
}

/** A file's badge: a few letters in its language's colour, or a plain page. */
function badge(name, kind) {
  if (kind === 'dir') return h('span', { class: 'files-icon files-folder', 'aria-hidden': 'true' }, icon('folder'))
  if (kind === 'link') return h('span', { class: 'files-icon', 'aria-hidden': 'true' }, icon('link'))
  const { glyph, lane } = L.badgeOf(name)
  if (!glyph) return h('span', { class: 'files-icon', 'aria-hidden': 'true' }, icon('file'))
  return h('span', { class: `files-icon files-badge lane-${lane}`, 'aria-hidden': 'true' }, glyph)
}

/** A name with the letters a match picked out. */
function marked(text, hits, offset = 0) {
  return L.spans(text, hits.map((at) => at - offset)).map((one) => (one.hit ? h('mark', {}, one.text) : one.text))
}

export async function mount(el, ctx) {
  stylesheet()
  const cm = await import('/vendor/codemirror.js')

  // State ---------------------------------------------------------------------------------------

  const kept = ctx.keep('files') || {}
  const tree = { root: ctx.env.workdir || '/', open: new Set(kept.open || []), listed: new Map(), failed: new Map() }
  let filter = ''
  let selected = null
  /** The new file or directory being named in the tree, or the entry being renamed. */
  let naming = null
  let tabs = { tabs: (kept.tabs || []).filter((one) => one && one.path), active: kept.active || null }
  /** Each file opened, by its path: see `blank`. */
  const docs = new Map()
  /** The file whose state is the editor's now. */
  let inView = null
  let wrap = Boolean(kept.wrap)
  let side = kept.side === 'search' ? 'search' : 'explorer'
  let closed = ctx.env.open === false
  let visible = true
  let quiet = false
  let found = null
  let finding = null
  let merge = null
  let left = false

  // The page --------------------------------------------------------------------------------------

  const treeBox = h('div', { class: 'files-tree', role: 'tree', tabindex: '0', 'aria-label': 'Files', 'data-hmz': 'files-tree' })
  const filterBox = h('input', { class: 'files-filter', type: 'search', placeholder: 'Filter', 'aria-label': 'Filter files', 'data-hmz': 'files-filter' })
  const explorer = h(
    'div',
    { class: 'files-explorer' },
    h(
      'div',
      { class: 'files-pane-head' },
      h('span', { class: 'files-root', title: tree.root }, L.baseName(tree.root) || '/'),
      iconButton('file', 'New file', { class: 'small', 'data-hmz': 'files-new-file', onclick: () => startNew('file') }),
      iconButton('folder', 'New folder', { class: 'small', 'data-hmz': 'files-new-dir', onclick: () => startNew('dir') }),
      iconButton('resume', 'Refresh', { class: 'small', 'data-hmz': 'files-refresh', onclick: () => refresh() }),
      iconButton('minus', 'Collapse all', { class: 'small', onclick: () => collapseAll() }),
    ),
    filterBox,
    treeBox,
  )
  const queryBox = h('input', { class: 'files-input', type: 'search', placeholder: 'Search', 'aria-label': 'Search in files', 'data-hmz': 'files-search-query' })
  const caseBox = h('button', { class: 'files-toggle', type: 'button', 'aria-pressed': 'false', title: 'Match case', 'data-hmz': 'files-search-case' }, 'Aa')
  const regexBox = h('button', { class: 'files-toggle', type: 'button', 'aria-pressed': 'false', title: 'Use regular expression', 'data-hmz': 'files-search-regex' }, '.*')
  const globBox = h('input', { class: 'files-input', type: 'text', placeholder: 'Files to include, e.g. *.py', 'aria-label': 'Files to include', 'data-hmz': 'files-search-glob' })
  const summary = h('div', { class: 'files-summary', role: 'status', 'data-hmz': 'files-search-summary' })
  const resultsBox = h('div', { class: 'files-results', role: 'list', 'data-hmz': 'files-results' })
  const searcher = h(
    'div',
    { class: 'files-search' },
    h('div', { class: 'files-pane-head' }, h('span', { class: 'files-root' }, 'Search')),
    h('div', { class: 'files-query' }, queryBox, caseBox, regexBox),
    globBox,
    summary,
    resultsBox,
  )
  const explorerTab = h('button', { class: 'files-side-tab', type: 'button', role: 'tab', 'data-hmz': 'files-side-explorer', onclick: () => sideTo('explorer') }, 'Explorer')
  const searchTab = h('button', { class: 'files-side-tab', type: 'button', role: 'tab', 'data-hmz': 'files-side-search', onclick: () => sideTo('search') }, 'Search')
  const sideBox = h('aside', { class: 'files-side' }, h('div', { class: 'files-side-tabs', role: 'tablist' }, explorerTab, searchTab), explorer, searcher)

  const tabsBox = h('div', { class: 'files-tabs', role: 'tablist', 'data-hmz': 'files-tabs' })
  const bannerBox = h('div', { class: 'files-banners', 'data-hmz': 'files-banner' })
  const editorBox = h('div', { class: 'files-editor', 'data-hmz': 'files-editor' })
  const otherBox = h('div', { class: 'files-other', 'data-hmz': 'files-other' })
  const statusBox = h('footer', { class: 'files-status', 'data-hmz': 'files-status' })
  const main = h('section', { class: 'files-main' }, tabsBox, bannerBox, h('div', { class: 'files-body' }, editorBox, otherBox), statusBox)
  const quickInput = h('input', { class: 'files-input', type: 'text', placeholder: 'Go to file by name, path:line', 'aria-label': 'Go to file', 'data-hmz': 'files-quick-input', autocomplete: 'off', spellcheck: 'false' })
  const quickList = h('div', { class: 'files-quick-list', role: 'listbox', 'data-hmz': 'files-quick-list' })
  const quickNote = h('div', { class: 'files-quick-note' })
  const quick = h('div', { class: 'files-quick', role: 'dialog', 'aria-label': 'Go to file', hidden: true, 'data-hmz': 'files-quick' }, quickInput, quickNote, quickList)
  const panel = h('div', { class: 'files', 'data-hmz': 'files' }, sideBox, main, quick)
  fill(el, panel)

  // The editor ------------------------------------------------------------------------------------

  const themeC = new cm.Compartment()
  const langC = new cm.Compartment()
  const wrapC = new cm.Compartment()
  const lockC = new cm.Compartment()
  const lockOf = (doc) => (closed || doc.readOnly ? [cm.EditorState.readOnly.of(true)] : [])
  const listener = cm.EditorView.updateListener.of((update) => {
    const doc = inView
    if (!doc) return
    if (update.docChanged && !quiet) {
      if (!pinned(doc.path)) pin(doc.path)
      doc.saver.edited()
    }
    if (update.docChanged || update.selectionSet) status()
  })
  const blurred = cm.EditorView.domEventHandlers({
    blur: () => {
      inView?.saver?.now()
    },
  })
  const view = new cm.EditorView({ parent: editorBox, state: cm.EditorState.create({ doc: '' }) })

  function editorState(doc, text) {
    return cm.EditorState.create({
      doc: text,
      extensions: [
        cm.keymap.of([cm.indentWithTab]),
        cm.basicSetup,
        themeC.of(cm.themeFor(ctx.theme())),
        langC.of(cm.languageFor(L.baseName(doc.path)) || []),
        wrapC.of(wrap ? cm.EditorView.lineWrapping : []),
        lockC.of(lockOf(doc)),
        listener,
        blurred,
      ],
    })
  }

  /** What a file holds now: the editor's, where it is the one in it. */
  const stateOf = (doc) => (inView === doc ? view.state : doc.state)

  /** Brings what the editor shows of the theme, wrapping and locks up to now. */
  function synced(doc) {
    return [themeC.reconfigure(cm.themeFor(ctx.theme())), wrapC.reconfigure(wrap ? cm.EditorView.lineWrapping : []), lockC.reconfigure(lockOf(doc)), langC.reconfigure(cm.languageFor(L.baseName(doc.path)) || [])]
  }

  function reconfigure(doc) {
    if (doc.kind !== 'text') return
    if (inView === doc) view.dispatch({ effects: synced(doc) })
    else doc.state = doc.state.update({ effects: synced(doc) }).state
  }

  // Files -----------------------------------------------------------------------------------------

  /** A file, opened or being: what it is, where its bytes stood on disk, and its edits. */
  function blank(path) {
    const doc = {
      path,
      kind: 'loading',
      state: null,
      scroll: null,
      etag: null,
      mtime: null,
      size: 0,
      eol: '\n',
      bom: false,
      readOnly: false,
      why: null,
      looked: 0,
      image: null,
      error: null,
      conflict: false,
      gone: false,
      checking: false,
      loaded: null,
      saver: null,
    }
    doc.saver = L.autosaver({
      save: () => write(doc),
      told: (state, error) => {
        if (state === 'error') failed(doc, error)
        drawTab(doc)
        if (doc === current()) status()
      },
    })
    return doc
  }

  function docOf(path) {
    let doc = docs.get(path)
    if (!doc) {
      doc = blank(path)
      docs.set(path, doc)
      doc.loaded = load(doc)
    }
    return doc
  }

  /** The whole of a file, a chunk at a time, read again from the start if it changed meanwhile. */
  async function readAll(path, first = null) {
    for (let tries = 0; ; tries++) {
      const head = first || (await call('env.read', { path, offset: 0, length: L.CHUNK }))
      first = null
      const chunks = [L.fromBase64(head.data)]
      let offset = chunks[0].length
      let last = head
      while (!last.eof && offset < head.size) {
        last = await call('env.read', { path, offset, length: L.CHUNK })
        const bytes = L.fromBase64(last.data)
        if (!bytes.length) break
        chunks.push(bytes)
        offset += bytes.length
        if (last.etag !== head.etag) break
      }
      if (last.etag === head.etag || tries >= 2) return { bytes: L.joined(chunks), etag: last.etag, mtime: last.mtime, size: last.size }
    }
  }

  async function load(doc) {
    doc.kind = 'loading'
    doc.error = null
    try {
      const head = await call('env.read', { path: doc.path, offset: 0, length: L.CHUNK })
      doc.size = head.size
      doc.mtime = head.mtime
      const how = L.opening({ name: doc.path, size: head.size })
      if (how === 'too-large') {
        doc.kind = 'too-large'
        return
      }
      const whole = await readAll(doc.path, head)
      Object.assign(doc, { etag: whole.etag, mtime: whole.mtime, size: whole.size })
      if (how === 'image') {
        doc.kind = 'image'
        doc.image = `data:${L.imageType(doc.path)};base64,${L.toBase64(whole.bytes)}`
        return
      }
      // A binary file, and a large one, open read-only, saying why (web.md 3.16.2.9).
      const text = L.decode(whole.bytes)
      const shown = text.binary ? { text: new TextDecoder().decode(whole.bytes), eol: '\n', bom: false } : text
      Object.assign(doc, { eol: shown.eol, bom: shown.bom, readOnly: text.binary || how === 'large', why: text.binary ? 'binary' : how === 'large' ? 'large' : null })
      doc.state = editorState(doc, shown.text)
      doc.kind = 'text'
    } catch (error) {
      doc.kind = 'error'
      doc.error = said(error)
    }
  }

  /** Writes a file's text back, over what was read only: what the autosaver calls. */
  async function write(doc) {
    const text = stateOf(doc).doc.toString()
    const done = await call('env.write', { path: doc.path, data: L.toBase64(L.encode(text, doc)), if_match: doc.etag ?? null })
    Object.assign(doc, { etag: done.etag, mtime: done.mtime, size: done.size, error: null, gone: false })
    if (doc === current()) drawBanner()
  }

  function failed(doc, error) {
    const why = said(error)
    // The banner says the environment closed; the edits wait, read-only.
    if (why === L.CLOSED) return
    if (why.includes(L.CHANGED)) {
      conflicted(doc)
      return
    }
    doc.error = why
    if (doc === current()) drawBanner()
  }

  function conflicted(doc) {
    doc.conflict = true
    doc.saver.pause(true)
    drawTab(doc)
    if (doc === current()) drawBanner()
  }

  /** Every call of the panel, the environment's closing heard in any of them. */
  async function call(method, params) {
    try {
      return await ctx.call(method, params)
    } catch (error) {
      if (said(error) === L.CLOSED) shut()
      throw error
    }
  }

  /** The environment closed: what was not written is kept, read-only, and nothing is polled. */
  function shut() {
    if (closed) return
    closed = true
    for (const doc of docs.values()) {
      doc.saver.pause(true)
      reconfigure(doc)
    }
    drawBanner()
    status()
  }

  /** Saves every file with edits, now: on the page hidden, or leaving. */
  function flushAll() {
    for (const doc of docs.values()) if (doc.saver.dirty) doc.saver.now()
  }

  // Tabs ------------------------------------------------------------------------------------------

  const current = () => (tabs.active ? docs.get(tabs.active) || null : null)
  const pinned = (path) => Boolean(tabs.tabs.find((one) => one.path === path)?.pinned)

  let persisting = null
  function persist() {
    clearTimeout(persisting)
    persisting = setTimeout(() => {
      if (left) return
      ctx.keep('files', { tabs: tabs.tabs, active: tabs.active, open: [...tree.open], wrap, side })
    }, 200)
  }

  function pin(path) {
    tabs = L.pinTab(tabs, path)
    drawTabs()
    persist()
  }

  /**
   * Opens a file: in the preview tab, or pinned; at a line and column, from 1, where given.
   */
  async function open(path, { pin: pinning = false, line = null, column = null, focus = true } = {}) {
    let next = L.openTab(tabs, path, { pin: pinning })
    const kept_ = next.replaced && docs.get(next.replaced)
    // A preview tab whose edits are not written, or are in conflict, is kept rather than replaced.
    if (kept_ && (kept_.conflict || (kept_.saver.dirty && kept_.saver.state === 'error'))) {
      next = L.openTab(L.pinTab(tabs, next.replaced), path, { pin: pinning })
    } else if (next.replaced && next.replaced !== path) forget(next.replaced)
    tabs = { tabs: next.tabs, active: next.active }
    await show(path, { line, column, focus })
  }

  /** Lets go of a file no tab holds any more, after writing what it has not. */
  function forget(path) {
    const doc = docs.get(path)
    if (!doc) return
    if (doc.saver.dirty && !doc.conflict) {
      doc.saver.now().then((ok) => {
        if (tabs.tabs.some((one) => one.path === path)) return
        if (ok) drop(doc)
        else {
          // Not written: its tab comes back, kept, so the edits are not lost.
          tabs = { ...tabs, tabs: [...tabs.tabs, { path, pinned: true }] }
          drawTabs()
          persist()
        }
      })
      return
    }
    drop(doc)
  }

  function drop(doc) {
    doc.saver.dispose()
    if (inView === doc) inView = null
    docs.delete(doc.path)
  }

  /** Puts the editor's state back in the file it is of, before another is shown. */
  function stash() {
    if (!inView) return
    inView.state = view.state
    inView.scroll = { top: view.scrollDOM.scrollTop, left: view.scrollDOM.scrollLeft }
  }

  async function show(path, { line = null, column = null, focus = true } = {}) {
    const was = current()
    if (was && was.path !== path) was.saver.now()
    tabs = { ...tabs, active: path }
    persist()
    const doc = docOf(path)
    drawTabs()
    drawBody()
    await doc.loaded
    if (left || current() !== doc) return
    drawBody()
    if (doc.kind === 'text' && line) goTo(line, column || 1)
    if (doc.kind === 'text' && focus) view.focus()
    revealInTree(path)
  }

  async function close(path) {
    const doc = docs.get(path)
    if (doc && doc.saver.dirty) {
      const ok = !doc.conflict && !closed && (await doc.saver.now())
      if (!ok && !(await ctx.confirm(`${L.baseName(path)} has edits not written to the environment. Close it and lose them?`))) return
    }
    if (doc) drop(doc)
    tabs = L.closeTab(tabs, path)
    persist()
    if (tabs.active) await show(tabs.active, { focus: false })
    else {
      drawTabs()
      drawBody()
    }
  }

  /** Closes every tab but one (or all), each written first, asking before edits are lost. */
  async function closeAllBut(path) {
    const closing = tabs.tabs.filter((one) => one.path !== path)
    await Promise.all(closing.map((one) => docs.get(one.path)).filter((doc) => doc && doc.saver.dirty && !doc.conflict && !closed).map((doc) => doc.saver.now()))
    const unsaved = closing.map((one) => docs.get(one.path)).filter((doc) => doc && doc.saver.dirty)
    if (unsaved.length && !(await ctx.confirm(`${unsaved.map((doc) => L.baseName(doc.path)).join(', ')} ${unsaved.length === 1 ? 'has' : 'have'} edits not written to the environment. Close and lose them?`))) return
    for (const one of closing) {
      const doc = docs.get(one.path)
      if (doc) drop(doc)
    }
    tabs = path ? L.closeOthers(tabs, path) : { tabs: [], active: null }
    persist()
    if (tabs.active) await show(tabs.active, { focus: false })
    else {
      drawTabs()
      drawBody()
    }
  }

  // Drawing ---------------------------------------------------------------------------------------

  function tabOf(one) {
    const doc = docs.get(one.path)
    const name = L.baseName(one.path)
    const twin = tabs.tabs.some((other) => other.path !== one.path && L.baseName(other.path) === name)
    const dirty = doc && (doc.saver.dirty || doc.conflict)
    const active = one.path === tabs.active
    const tab = h(
      'div',
      {
        class: ['files-tab', active && 'active', !one.pinned && 'preview', dirty && 'dirty', doc?.conflict && 'conflict'],
        role: 'tab',
        'aria-selected': active ? 'true' : 'false',
        title: L.relative(one.path, tree.root),
        tabindex: active ? '0' : '-1',
        'data-hmz': 'files-tab',
        'data-path': one.path,
      },
      badge(name, 'file'),
      h('span', { class: 'files-tab-name' }, name),
      twin ? h('span', { class: 'files-tab-dir' }, L.relative(L.parentOf(one.path), tree.root)) : null,
      h(
        'button',
        { class: 'files-tab-close', type: 'button', 'aria-label': `Close ${name}`, 'data-hmz': 'files-tab-close', tabindex: '-1' },
        h('span', { class: 'files-dot', 'aria-hidden': 'true' }),
        icon('close'),
      ),
    )
    tab.addEventListener('click', (event) => {
      if (event.target.closest('.files-tab-close')) close(one.path)
      else show(one.path)
    })
    tab.addEventListener('dblclick', () => pin(one.path))
    tab.addEventListener('auxclick', (event) => {
      if (event.button === 1) {
        event.preventDefault()
        close(one.path)
      }
    })
    tab.addEventListener('mousedown', (event) => {
      if (event.button === 1) event.preventDefault()
    })
    L.dragTab(tab, (before) => {
      tabs = L.moveTab(tabs, one.path, before)
      drawTabs()
      persist()
    })
    menuOn(tab, () => [
      { label: 'Close', glyph: 'close', act: () => close(one.path) },
      { label: 'Close others', act: () => closeAllBut(one.path) },
      { label: 'Close all', act: () => closeAllBut(null) },
      '-',
      !one.pinned && { label: 'Keep open', act: () => pin(one.path) },
      { label: 'Reveal in explorer', act: () => (sideTo('explorer'), revealInTree(one.path, true)) },
      { label: 'Copy path', glyph: 'copy', act: () => navigator.clipboard?.writeText(one.path) },
    ])
    return tab
  }

  function drawTabs() {
    fill(tabsBox, tabs.tabs.map(tabOf))
    tabsBox.querySelector('.files-tab.active')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }

  function drawTab(doc) {
    const one = tabs.tabs.find((tab) => tab.path === doc.path)
    const old = tabsBox.querySelector(`.files-tab[data-path="${CSS.escape(doc.path)}"]`)
    if (one && old) old.replaceWith(tabOf(one))
  }

  function notice(title, text, ...actions) {
    return h('div', { class: 'files-notice', 'data-hmz': 'files-notice' }, h('strong', {}, title), h('p', {}, text), actions.length ? h('p', { class: 'row' }, actions) : null)
  }

  function button(label, act, extra = {}) {
    return h('button', { class: ['btn', 'small', extra.quiet && 'quiet'], type: 'button', 'data-hmz': extra.hmz || null, onclick: act }, label)
  }

  function drawBody() {
    if (merge) {
      merge.destroy()
      merge = null
    }
    const doc = current()
    if (!doc || doc.kind !== 'text') {
      stash()
      inView = null
    }
    editorBox.hidden = !doc || doc.kind !== 'text'
    otherBox.hidden = !editorBox.hidden
    if (!doc) {
      fill(otherBox, h('div', { class: 'files-welcome' }, h('strong', {}, 'No file open'), h('p', {}, 'Pick one in the explorer, or press ', h('kbd', {}, mod, '+P'), ' to open one by name.')))
    } else if (doc.kind === 'loading') {
      fill(otherBox, h('div', { class: 'files-welcome' }, 'Reading…'))
    } else if (doc.kind === 'error') {
      fill(otherBox, notice('Could not open this file', doc.error, button('Try again', () => reopen(doc))))
    } else if (doc.kind === 'too-large') {
      fill(otherBox, notice('Too large to open', `${L.baseName(doc.path)} is ${L.sizeOf(doc.size)}; files over ${L.sizeOf(L.LARGEST)} are not opened here.`))
    } else if (doc.kind === 'image') {
      fill(otherBox, h('div', { class: 'files-image' }, h('img', { src: doc.image, alt: L.baseName(doc.path), 'data-hmz': 'files-image' }), h('p', { class: 'files-caption' }, L.sizeOf(doc.size))))
    } else if (inView !== doc) {
      stash()
      view.setState(doc.state)
      inView = doc
      view.dispatch({ effects: synced(doc) })
      const scroll = doc.scroll
      if (scroll) requestAnimationFrame(() => view.scrollDOM.scrollTo(scroll.left, scroll.top))
    }
    drawBanner()
    status()
  }

  async function reopen(doc) {
    if (inView === doc) inView = null
    doc.loaded = load(doc)
    if (current() === doc) drawBody()
    await doc.loaded
    if (current() === doc) drawBody()
  }

  function drawBanner() {
    const doc = current()
    const banners = []
    if (closed) banners.push(h('div', { class: 'files-banner warn', role: 'alert', 'data-hmz': 'files-closed' }, h('span', {}, `${L.CLOSED} Edits not written are kept here, read-only.`)))
    if (doc?.conflict) {
      banners.push(
        h(
          'div',
          { class: 'files-banner danger', role: 'alert', 'data-hmz': 'files-conflict' },
          h('span', {}, `${L.baseName(doc.path)} changed in the environment since you opened it.`),
          button(merge ? 'Back to editing' : 'Compare', () => (merge ? drawBody() : compare(doc)), { hmz: 'files-compare' }),
          button('Keep mine', () => keepMine(doc), { hmz: 'files-keep-mine' }),
          button('Reload', () => reload(doc), { hmz: 'files-reload', quiet: true }),
        ),
      )
    } else if (doc?.error && doc.kind === 'text') {
      banners.push(
        h(
          'div',
          { class: 'files-banner danger', role: 'alert', 'data-hmz': 'files-save-error' },
          h('span', {}, `Not saved: ${doc.error}`),
          closed ? null : button('Try again', () => ((doc.error = null), doc.saver.now(), drawBanner())),
        ),
      )
    }
    if (doc?.gone && !doc.conflict) banners.push(h('div', { class: 'files-banner warn', role: 'status', 'data-hmz': 'files-gone' }, h('span', {}, `${L.baseName(doc.path)} is no longer in the environment; saving writes it again.`)))
    if (doc?.readOnly && doc.kind === 'text') {
      const why = doc.why === 'binary' ? 'is not UTF-8 text' : `is ${L.sizeOf(doc.size)}, over ${L.sizeOf(L.LARGE)}`
      banners.push(h('div', { class: 'files-banner', role: 'status', 'data-hmz': 'files-read-only' }, h('span', {}, `${L.baseName(doc.path)} ${why}, so it is open read-only.`)))
    }
    fill(bannerBox, banners)
  }

  const mod = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? '⌘' : 'Ctrl'

  function status() {
    const doc = current()
    if (!doc || doc.kind !== 'text' || inView !== doc) {
      fill(statusBox, doc ? h('span', { class: 'files-state' }, doc.kind === 'image' ? 'Image' : '') : null)
      return
    }
    const state = view.state
    const head = state.selection.main.head
    const line = state.doc.lineAt(head)
    const chosen = state.selection.ranges.reduce((sum, range) => sum + (range.to - range.from), 0)
    const saving = doc.conflict ? 'Conflict' : closed ? 'Read-only' : doc.readOnly ? 'Read-only' : { saving: 'Saving…', saved: 'Saved', dirty: 'Unsaved', error: 'Not saved' }[doc.saver.state]
    fill(
      statusBox,
      h('span', { class: ['files-state', `is-${doc.conflict ? 'error' : doc.saver.state}`], 'data-hmz': 'files-saved' }, saving),
      h('span', { class: 'files-gap' }),
      h('button', { class: 'files-status-item', type: 'button', title: 'Go to line', 'data-hmz': 'files-position', onclick: () => cm.gotoLine(view) }, `Ln ${line.number}, Col ${head - line.from + 1}`, chosen ? ` (${chosen} selected)` : '', state.selection.ranges.length > 1 ? ` · ${state.selection.ranges.length} cursors` : ''),
      h('span', { class: 'files-status-item' }, doc.bom ? 'UTF-8 with BOM' : 'UTF-8'),
      h('button', { class: 'files-status-item', type: 'button', title: 'Change the line endings', 'data-hmz': 'files-eol', onclick: () => toggleEol(doc) }, doc.eol === '\r\n' ? 'CRLF' : 'LF'),
      h('span', { class: 'files-status-item', 'data-hmz': 'files-language' }, L.languageOf(doc.path)),
      h('button', { class: ['files-status-item', wrap && 'on'], type: 'button', title: 'Wrap lines (Alt+Z)', 'aria-pressed': wrap ? 'true' : 'false', 'data-hmz': 'files-wrap', onclick: () => toggleWrap() }, 'Wrap'),
    )
  }

  function toggleEol(doc) {
    if (closed || doc.readOnly) return
    doc.eol = doc.eol === '\r\n' ? '\n' : '\r\n'
    if (!pinned(doc.path)) pin(doc.path)
    doc.saver.edited()
    status()
  }

  function toggleWrap() {
    wrap = !wrap
    if (inView) view.dispatch({ effects: wrapC.reconfigure(wrap ? cm.EditorView.lineWrapping : []) })
    persist()
    status()
  }

  function goTo(line, column = 1) {
    const doc = view.state.doc
    const at = doc.line(Math.max(1, Math.min(doc.lines, line)))
    const pos = at.from + Math.max(0, Math.min(at.length, column - 1))
    view.dispatch({ selection: { anchor: pos }, effects: cm.EditorView.scrollIntoView(pos, { y: 'center' }) })
  }

  // Conflicts and changes elsewhere --------------------------------------------------------------

  /** Replaces a file's text with what is on disk, keeping the cursor and scroll where they can. */
  function replaced(doc, text) {
    const change = L.delta(stateOf(doc).doc.toString(), text)
    if (!change) return
    if (inView === doc) {
      quiet = true
      try {
        view.dispatch({ changes: change })
      } finally {
        quiet = false
      }
    } else doc.state = doc.state.update({ changes: change }).state
  }

  async function reload(doc) {
    try {
      const whole = await readAll(doc.path)
      const text = L.decode(whole.bytes)
      if (text.binary) throw new Error('It is not UTF-8 text any more.')
      replaced(doc, text.text)
      Object.assign(doc, { etag: whole.etag, mtime: whole.mtime, size: whole.size, eol: text.eol, bom: text.bom, conflict: false, error: null, gone: false })
      doc.saver.clean()
      doc.saver.pause(closed)
    } catch (error) {
      doc.error = said(error)
    }
    drawTab(doc)
    if (doc === current()) drawBody()
  }

  async function keepMine(doc) {
    try {
      const disk = await call('env.read', { path: doc.path, offset: 0, length: 1 })
      doc.etag = disk.etag
    } catch (error) {
      // Gone from disk: written again as it is here.
      if (!/^No such file/.test(said(error))) {
        doc.error = said(error)
        drawBanner()
        return
      }
      doc.etag = null
    }
    doc.conflict = false
    doc.error = null
    doc.saver.pause(closed)
    doc.saver.edited()
    await doc.saver.now()
    if (doc === current()) drawBody()
  }

  async function compare(doc) {
    let disk
    try {
      disk = L.decode((await readAll(doc.path)).bytes)
    } catch (error) {
      doc.error = said(error)
      drawBanner()
      return
    }
    stash()
    inView = null
    editorBox.hidden = true
    otherBox.hidden = false
    const extensions = [cm.EditorState.readOnly.of(true), cm.EditorView.editable.of(false), cm.themeFor(ctx.theme()), cm.languageFor(L.baseName(doc.path)) || [], wrap ? cm.EditorView.lineWrapping : []]
    const holder = h('div', { class: 'files-merge', 'data-hmz': 'files-merge' })
    fill(otherBox, h('div', { class: 'files-merge-head' }, h('span', {}, 'Yours'), h('span', {}, 'In the environment')), holder)
    merge = new cm.MergeView({ a: { doc: doc.state.doc.toString(), extensions }, b: { doc: disk.binary ? '' : disk.text, extensions }, parent: holder })
    drawBanner()
  }

  /** Looks at whether an open file changed on disk, and takes it in where it has no edits. */
  async function check(doc) {
    // Each file is looked at no more than every 5 seconds (web.md 3.16.2.6).
    if (doc.checking || doc.kind === 'loading' || doc.kind === 'error' || doc.saver.busy || closed || Date.now() - doc.looked < POLL) return
    doc.checking = true
    doc.looked = Date.now()
    try {
      let stat
      try {
        stat = await call('env.stat', { path: doc.path })
        // A link is open as the file it leads to, whose size and time a read answers.
        if (stat.kind === 'link') stat = await call('env.read', { path: doc.path, offset: 0, length: 0 })
      } catch (error) {
        if (/^No such file/.test(said(error)) && !doc.gone) {
          doc.gone = true
          if (doc === current()) drawBanner()
        }
        return
      }
      if (doc.gone) {
        doc.gone = false
        if (doc === current()) drawBanner()
      }
      if (stat.mtime === doc.mtime && stat.size === doc.size) return
      // A picture, and a file open read-only, are read again whole.
      if (doc.kind !== 'text' || doc.readOnly) {
        if (doc.kind === 'image' || doc.kind === 'text') await reopen(doc)
        return
      }
      const had = doc.etag
      const whole = await readAll(doc.path)
      // A write of ours made while it was read is newer than what was read.
      if (doc.saver.busy || doc.etag !== had) return
      if (whole.etag === doc.etag) {
        Object.assign(doc, { mtime: whole.mtime, size: whole.size })
        return
      }
      if (doc.saver.dirty || doc.conflict) {
        conflicted(doc)
        return
      }
      const text = L.decode(whole.bytes)
      if (text.binary) return
      replaced(doc, text.text)
      Object.assign(doc, { etag: whole.etag, mtime: whole.mtime, size: whole.size, eol: text.eol, bom: text.bom })
      doc.saver.clean()
      if (doc === current()) status()
    } catch {
      // Looked at again next time.
    } finally {
      doc.checking = false
    }
  }

  function poll() {
    if (left || closed || !visible || document.visibilityState !== 'visible') return
    for (const one of tabs.tabs) {
      const doc = docs.get(one.path)
      if (doc) check(doc)
    }
  }

  // The explorer ----------------------------------------------------------------------------------

  async function list(dir) {
    try {
      const got = await call('env.list', { path: dir })
      tree.listed.set(dir, L.sorted(got.entries || []))
      tree.failed.delete(dir)
    } catch (error) {
      tree.listed.delete(dir)
      tree.failed.set(dir, said(error))
      if (dir !== tree.root) tree.open.delete(dir)
    }
    drawTree()
  }

  let rows = []
  function drawTree() {
    rows = L.treeRows(tree, filter)
    if (naming && naming.kind !== 'rename') {
      const at = naming.dir === tree.root ? -1 : rows.findIndex((one) => one.path === naming.dir)
      const depth = at < 0 ? 0 : rows[at].depth + 1
      rows.splice(at + 1, 0, { path: `${naming.dir}/\0new`, name: '', kind: 'new', depth, open: false })
    }
    tree.view.set(rows)
  }

  const nameInput = () => {
    const input = h('input', { class: 'files-rename', type: 'text', spellcheck: 'false', 'aria-label': naming.kind === 'rename' ? 'New name' : naming.kind === 'dir' ? 'Folder name' : 'File name', 'data-hmz': 'files-name' })
    input.value = naming.kind === 'rename' ? L.baseName(naming.path) : ''
    let done = false
    const finish = async (keep) => {
      if (done) return
      done = true
      const what = naming
      naming = null
      if (keep) await named(what, input.value.trim())
      drawTree()
      treeBox.focus()
    }
    input.addEventListener('keydown', (event) => {
      event.stopPropagation()
      if (event.key === 'Enter') finish(true)
      else if (event.key === 'Escape') finish(false)
    })
    input.addEventListener('blur', () => finish(Boolean(input.value.trim())))
    requestAnimationFrame(() => {
      input.focus()
      const dot = input.value.lastIndexOf('.')
      input.setSelectionRange(0, dot > 0 && naming?.kind === 'rename' ? dot : input.value.length)
    })
    return input
  }

  function rowOf(row) {
    const props = { class: ['files-row', `is-${row.kind}`, row.path === selected && 'selected', row.path === tabs.active && 'current'], 'data-path': row.path, 'data-hmz': 'files-row' }
    if (row.kind === 'loading' || row.kind === 'error') {
      const made = h('div', { ...props, class: [...props.class, row.kind === 'error' && 'error'] }, h('span', { class: 'files-name' }, row.name))
      made.style.setProperty('--depth', row.depth)
      return made
    }
    if (row.kind === 'new') {
      const made = h('div', { ...props, role: 'treeitem' }, h('span', { class: 'files-twisty' }), badge('', naming.kind), nameInput())
      made.style.setProperty('--depth', row.depth)
      return made
    }
    const renaming = naming?.kind === 'rename' && naming.path === row.path
    const made = h(
      'div',
      { ...props, role: 'treeitem', 'aria-level': String(row.depth + 1), 'aria-selected': row.path === selected ? 'true' : 'false', 'aria-expanded': row.kind === 'dir' ? String(row.open) : null, title: L.relative(row.path, tree.root), 'data-kind': row.kind },
      h('span', { class: ['files-twisty', row.open && 'open'] }, row.kind === 'dir' ? icon('chevron') : null),
      badge(row.name, row.kind),
      renaming ? nameInput() : h('span', { class: 'files-name' }, row.name),
    )
    made.style.setProperty('--depth', row.depth)
    menuOn(made, () => entryMenu(row))
    return made
  }

  function entryMenu(row) {
    const dir = row.kind === 'dir' ? row.path : L.parentOf(row.path)
    return [
      { head: L.relative(row.path, tree.root) },
      row.kind !== 'dir' && { label: 'Open', glyph: 'open', act: () => open(row.path, { pin: true }) },
      { label: 'New file…', glyph: 'file', act: () => startNew('file', dir) },
      { label: 'New folder…', glyph: 'folder', act: () => startNew('dir', dir) },
      '-',
      !closed && { label: 'Rename…', act: () => startRename(row.path) },
      !closed && { label: 'Delete', danger: true, act: () => remove(row.path) },
      '-',
      { label: 'Copy path', glyph: 'copy', act: () => navigator.clipboard?.writeText(row.path) },
      { label: 'Copy relative path', act: () => navigator.clipboard?.writeText(L.relative(row.path, tree.root)) },
    ]
  }

  tree.view = virtual(treeBox, {
    key: (row) => row.path,
    sig: (row) => [row.kind, row.name, row.depth, row.open, row.path === selected, row.path === tabs.active, naming?.path === row.path].join('|'),
    draw: rowOf,
  })

  async function toggle(path, open_) {
    if (open_ ?? !tree.open.has(path)) {
      tree.open.add(path)
      if (!tree.listed.has(path)) {
        drawTree()
        await list(path)
      }
    } else tree.open.delete(path)
    persist()
    drawTree()
  }

  function select(path) {
    selected = path
    drawTree()
    tree.view.show(rows.findIndex((one) => one.path === path))
  }

  async function activateRow(row, { pin: pinning = false } = {}) {
    if (row.kind === 'dir') return toggle(row.path)
    if (row.kind === 'link' && tree.listed.has(row.path)) return toggle(row.path)
    if (row.kind === 'link') {
      // A link to a directory opens as one; to a file, as that file.
      try {
        const stat = await call('env.list', { path: row.path })
        tree.listed.set(row.path, L.sorted(stat.entries || []))
        tree.open.add(row.path)
        drawTree()
        return
      } catch {
        // Not a directory.
      }
    }
    if (row.kind === 'file' || row.kind === 'link') await open(row.path, { pin: pinning, focus: pinning })
  }

  treeBox.addEventListener('click', (event) => {
    const at = event.target.closest('.files-row')
    if (!at || event.target.closest('input')) return
    const row = rows.find((one) => one.path === at.dataset.path)
    if (!row || row.kind === 'loading' || row.kind === 'error' || row.kind === 'new') return
    select(row.path)
    activateRow(row)
  })
  treeBox.addEventListener('dblclick', (event) => {
    const at = event.target.closest('.files-row')
    const row = at && rows.find((one) => one.path === at.dataset.path)
    if (row && row.kind !== 'dir' && row.kind !== 'new') open(row.path, { pin: true })
  })
  treeBox.addEventListener('keydown', (event) => {
    if (event.target !== treeBox) return
    const row = rows.find((one) => one.path === selected)
    const keys = {
      ArrowDown: () => select(L.step(rows, selected, 1)),
      ArrowUp: () => select(L.step(rows, selected, -1)),
      Home: () => select(L.step(rows, null, 0)),
      End: () => select(L.step(rows, rows.findLast((one) => one.kind !== 'loading' && one.kind !== 'error')?.path ?? null, 0)),
      ArrowRight: () => row?.kind === 'dir' && (row.open ? select(L.step(rows, selected, 1)) : toggle(row.path, true)),
      ArrowLeft: () => {
        if (row?.kind === 'dir' && row.open) toggle(row.path, false)
        else if (row && L.parentOf(row.path) !== tree.root && within(row.path)) select(L.parentOf(row.path))
      },
      Enter: () => row && activateRow(row, { pin: true }),
      ' ': () => row && activateRow(row),
      F2: () => row && !closed && startRename(row.path),
      Delete: () => row && !closed && remove(row.path),
      Backspace: () => (event.metaKey || event.ctrlKey) && row && !closed && remove(row.path),
    }
    const act = keys[event.key]
    if (!act) return
    event.preventDefault()
    act()
  })
  const within = (path) => L.within(path, tree.root)

  filterBox.addEventListener('input', () => {
    filter = filterBox.value
    drawTree()
  })
  filterBox.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      filterBox.value = filter = ''
      drawTree()
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      treeBox.focus()
      select(L.step(rows, null, 0))
    }
  })

  /** Where a new file or directory goes: the directory picked, or the one the file picked is in. */
  function targetDir() {
    const row = rows.find((one) => one.path === selected)
    if (!row) return tree.root
    return row.kind === 'dir' ? row.path : L.parentOf(row.path)
  }

  async function startNew(kind, dir = targetDir()) {
    if (closed) return
    sideTo('explorer')
    if (dir !== tree.root) await toggle(dir, true)
    naming = { kind, dir }
    drawTree()
    tree.view.show(rows.findIndex((one) => one.kind === 'new'))
  }

  function startRename(path) {
    naming = { kind: 'rename', path }
    drawTree()
  }

  async function named(what, name) {
    const dir = what.kind === 'rename' ? L.parentOf(what.path) : what.dir
    const siblings = (tree.listed.get(dir) || []).map((one) => one.name).filter((one) => what.kind !== 'rename' || one !== L.baseName(what.path))
    if (what.kind === 'rename' && name === L.baseName(what.path)) return
    const bad = L.badName(name, siblings)
    if (bad) return problem(bad)
    const path = L.joinPath(dir, name)
    try {
      if (what.kind === 'file') {
        await call('env.write', { path, data: '', if_match: '' })
        await list(L.parentOf(path))
        selected = path
        await open(path, { pin: true })
      } else if (what.kind === 'dir') {
        await call('env.mkdir', { path })
        await list(L.parentOf(path))
        selected = path
        await toggle(path, true)
      } else {
        await renamed(what.path, path)
      }
    } catch (error) {
      problem(said(error))
    }
  }

  async function renamed(from, to) {
    // What is not written yet is written first, under the name it was read by.
    for (const doc of docs.values()) if (L.within(doc.path, from) && doc.saver.dirty) await doc.saver.now()
    await call('env.rename', { path: from, to })
    for (const [path, doc] of [...docs]) {
      if (!L.within(path, from)) continue
      docs.delete(path)
      doc.path = to + path.slice(from.length)
      docs.set(doc.path, doc)
      reconfigure(doc)
    }
    tabs = L.renameTabs(tabs, from, to)
    tree.open = new Set([...tree.open].map((one) => (L.within(one, from) ? to + one.slice(from.length) : one)))
    for (const dir of [...tree.listed.keys()]) if (L.within(dir, from)) tree.listed.delete(dir)
    selected = to
    persist()
    await list(L.parentOf(from))
    if (L.parentOf(to) !== L.parentOf(from)) await list(L.parentOf(to))
    for (const dir of tree.open) if (L.within(dir, to)) await list(dir)
    drawTabs()
    if (tabs.active) drawBody()
  }

  async function remove(path) {
    const name = L.baseName(path)
    const isDir = tree.listed.has(path) || rows.find((one) => one.path === path)?.kind === 'dir'
    if (!(await ctx.confirm(isDir ? `Delete the folder ${name} and everything in it?` : `Delete ${name}?`))) return
    try {
      await call('env.remove', { path })
    } catch (error) {
      problem(said(error))
      return
    }
    for (const doc of [...docs.values()]) if (L.within(doc.path, path)) drop(doc)
    const left_ = tabs.tabs.filter((one) => !L.within(one.path, path))
    if (left_.length !== tabs.tabs.length) {
      tabs = { tabs: left_, active: left_.some((one) => one.path === tabs.active) ? tabs.active : left_[0]?.path || null }
      if (tabs.active) show(tabs.active, { focus: false })
      else {
        drawTabs()
        drawBody()
      }
    }
    for (const dir of [...tree.listed.keys()]) if (L.within(dir, path)) tree.listed.delete(dir)
    tree.open = new Set([...tree.open].filter((one) => !L.within(one, path)))
    if (selected && L.within(selected, path)) selected = L.parentOf(path)
    persist()
    await list(L.parentOf(path))
  }

  /** Says what went wrong in the explorer, at its top, for a moment. */
  function problem(text) {
    explorer.querySelector('.files-tree-error')?.remove()
    const said_ = h('p', { class: 'error files-tree-error', role: 'alert', 'data-hmz': 'files-tree-error' }, text)
    filterBox.after(said_)
    setTimeout(() => said_.remove(), 5000)
  }

  async function refresh() {
    await Promise.all([...tree.listed.keys()].filter((dir) => dir === tree.root || tree.open.has(dir)).map(list))
    poll()
  }

  function collapseAll() {
    tree.open.clear()
    persist()
    drawTree()
  }

  /** Opens the directories down to a file and picks it out in the explorer. */
  async function revealInTree(path, focus = false) {
    if (!within(path)) return
    for (const dir of L.ancestors(path, tree.root)) {
      if (dir === tree.root) continue
      tree.open.add(dir)
      if (!tree.listed.has(dir)) await list(dir)
    }
    selected = path
    drawTree()
    tree.view.show(rows.findIndex((one) => one.path === path))
    if (focus) treeBox.focus()
  }

  // Search ----------------------------------------------------------------------------------------

  const searching = { query: '', regex: false, caseSensitive: false, glob: '', groups: [], folded: new Set(), asked: 0 }
  const results = virtual(resultsBox, {
    key: (row) => (row.kind === 'file' ? `f:${row.path}` : `m:${row.path}:${row.line}:${row.column}`),
    sig: (row) => (row.kind === 'file' ? `${row.count}|${row.folded}` : `${row.text}|${searching.query}|${searching.regex}|${searching.caseSensitive}`),
    draw: (row) => {
      if (row.kind === 'file') {
        const made = h(
          'div',
          { class: 'files-result-file', role: 'listitem', 'data-hmz': 'files-result-file', 'data-path': row.path, title: L.relative(row.path, tree.root) },
          h('span', { class: ['files-twisty', !row.folded && 'open'] }, icon('chevron')),
          badge(L.baseName(row.path), 'file'),
          h('span', { class: 'files-name' }, L.baseName(row.path)),
          h('span', { class: 'files-dir' }, L.relative(L.parentOf(row.path), tree.root)),
          h('span', { class: 'files-count' }, String(row.count)),
        )
        made.addEventListener('click', () => {
          if (searching.folded.has(row.path)) searching.folded.delete(row.path)
          else searching.folded.add(row.path)
          results.set(L.resultRows(searching.groups, searching.folded))
        })
        return made
      }
      const span = L.matchOn(row.text, searching.query, searching, row.column || 1)
      let text = row.text
      let at = span
      // A match far along a long line is shown with what is just before it.
      const cut = span && span[0] > 40 ? span[0] - 24 : 0
      if (cut) {
        text = `…${text.slice(cut)}`
        at = [span[0] - cut + 1, span[1] - cut + 1]
      }
      const said_ = at ? [text.slice(0, at[0]), h('mark', {}, text.slice(at[0], at[1])), text.slice(at[1])] : [text]
      const made = h('div', { class: 'files-result', role: 'listitem', tabindex: '0', 'data-hmz': 'files-result', 'data-path': row.path, 'data-line': String(row.line), title: `${L.relative(row.path, tree.root)}:${row.line}` }, h('span', { class: 'files-line' }, String(row.line)), h('span', { class: 'files-text' }, said_))
      const go = () => open(row.path, { line: row.line, column: (span ? span[0] : (row.column || 1) - 1) + 1 })
      made.addEventListener('click', go)
      made.addEventListener('keydown', (event) => event.key === 'Enter' && go())
      return made
    },
  })

  async function search() {
    const asked = ++searching.asked
    Object.assign(searching, { query: queryBox.value, glob: globBox.value.trim() })
    if (!searching.query) {
      searching.groups = []
      results.set([])
      fill(summary)
      return
    }
    fill(summary, 'Searching…')
    try {
      const got = await call('env.search', { query: searching.query, regex: searching.regex, case: searching.caseSensitive, glob: searching.glob, limit: 2000 })
      if (asked !== searching.asked) return
      searching.groups = L.grouped(got.matches || [], tree.root)
      searching.folded = new Set()
      const count = (got.matches || []).length
      fill(summary, count ? `${count} result${count === 1 ? '' : 's'} in ${searching.groups.length} file${searching.groups.length === 1 ? '' : 's'}${got.truncated ? ', and more not shown' : ''}` : 'No results.')
      results.set(L.resultRows(searching.groups, searching.folded))
    } catch (error) {
      if (asked !== searching.asked) return
      fill(summary, h('span', { class: 'error' }, said(error)))
      results.set([])
    }
  }
  let typing = null
  const soon = () => {
    clearTimeout(typing)
    typing = setTimeout(search, 350)
  }
  queryBox.addEventListener('input', soon)
  globBox.addEventListener('input', soon)
  for (const box of [queryBox, globBox]) {
    box.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        clearTimeout(typing)
        search()
      }
    })
  }
  for (const [box, key] of [[caseBox, 'caseSensitive'], [regexBox, 'regex']]) {
    box.addEventListener('click', () => {
      searching[key] = !searching[key]
      box.setAttribute('aria-pressed', String(searching[key]))
      search()
    })
  }

  function sideTo(which) {
    side = which
    explorer.hidden = which !== 'explorer'
    searcher.hidden = which !== 'search'
    explorerTab.setAttribute('aria-selected', String(which === 'explorer'))
    searchTab.setAttribute('aria-selected', String(which === 'search'))
    persist()
    // A list drawn while hidden had no height to fill: drawn again now it has.
    if (which === 'explorer') tree.view.paint()
    else results.paint()
  }

  function searchFor() {
    sideTo('search')
    const chosen = inView && view.state.sliceDoc(view.state.selection.main.from, view.state.selection.main.to)
    if (chosen && !chosen.includes('\n')) {
      queryBox.value = chosen
      search()
    }
    queryBox.focus()
    queryBox.select()
  }

  // Quick open ------------------------------------------------------------------------------------

  let picks = []
  let picked = 0

  async function quickOpen() {
    quick.hidden = false
    quickInput.value = ''
    quickInput.focus()
    drawQuick()
    // What is listed is shown at once, and listed afresh each time.
    const asking = (finding = call('env.find', { limit: 20000 }))
    try {
      const got = await asking
      if (finding !== asking) return
      found = { paths: got.paths || [], truncated: Boolean(got.truncated) }
      fill(quickNote, found.truncated ? `Only the first ${found.paths.length} files are searched.` : '')
    } catch (error) {
      if (finding === asking) fill(quickNote, h('span', { class: 'error' }, said(error)))
    }
    if (!quick.hidden) drawQuick()
  }

  function drawQuick() {
    const { query } = L.quickQuery(quickInput.value)
    if (!query) {
      picks = tabs.tabs.map((one) => ({ path: L.relative(one.path, tree.root), hits: [] }))
      if (!picks.length && found) picks = found.paths.slice(0, 50).map((path) => ({ path, hits: [] }))
    } else picks = found ? L.rank(query, found.paths, 50) : []
    picked = Math.min(picked, Math.max(0, picks.length - 1))
    if (!found && !picks.length) {
      fill(quickList, h('div', { class: 'files-quick-empty' }, 'Listing files…'))
      return
    }
    if (!picks.length) {
      fill(quickList, h('div', { class: 'files-quick-empty' }, 'No matching files.'))
      return
    }
    fill(
      quickList,
      picks.map((one, i) => {
        const name = L.baseName(one.path)
        const offset = one.path.length - name.length
        const item = h(
          'div',
          { class: ['files-pick', i === picked && 'active'], role: 'option', 'aria-selected': String(i === picked), 'data-hmz': 'files-pick', 'data-path': one.path },
          badge(name, 'file'),
          h('span', { class: 'files-name' }, marked(name, one.hits.filter((at) => at >= offset), offset)),
          h('span', { class: 'files-dir' }, marked(one.path.slice(0, Math.max(0, offset - 1)), one.hits.filter((at) => at < offset - 1))),
        )
        item.addEventListener('mousedown', (event) => event.preventDefault())
        item.addEventListener('click', () => {
          picked = i
          choose()
        })
        return item
      }),
    )
    quickList.querySelector('.active')?.scrollIntoView?.({ block: 'nearest' })
  }

  function quickClose() {
    quick.hidden = true
    if (inView) view.focus()
  }

  function choose() {
    const one = picks[picked]
    const { line, column } = L.quickQuery(quickInput.value)
    quickClose()
    if (one) open(L.joinPath(tree.root, one.path), { pin: true, line, column })
    else if (line && inView) goTo(line, column || 1)
  }

  quickInput.addEventListener('input', () => {
    picked = 0
    drawQuick()
  })
  quickInput.addEventListener('keydown', (event) => {
    const keys = {
      ArrowDown: () => ((picked = Math.min(picks.length - 1, picked + 1)), drawQuick()),
      ArrowUp: () => ((picked = Math.max(0, picked - 1)), drawQuick()),
      Enter: () => choose(),
      Escape: () => quickClose(),
    }
    const act = keys[event.key]
    if (!act) return
    event.preventDefault()
    event.stopPropagation()
    act()
  })
  quickInput.addEventListener('blur', () => setTimeout(() => !quick.contains(document.activeElement) && (quick.hidden = true), 0))

  // Keys, the page and what is heard ---------------------------------------------------------------

  function keyed(event) {
    if (left || !visible) return
    const inside = panel.contains(document.activeElement) || document.activeElement === document.body
    if (!inside) return
    const mod_ = event.metaKey || event.ctrlKey
    const key = event.key.toLowerCase()
    let act = null
    if (mod_ && !event.shiftKey && key === 'p') act = () => quickOpen()
    else if (mod_ && event.shiftKey && key === 'f') act = () => searchFor()
    else if (mod_ && event.shiftKey && key === 'e') act = () => (sideTo('explorer'), tabs.active ? revealInTree(tabs.active, true) : treeBox.focus())
    else if (mod_ && !event.shiftKey && key === 's') act = () => current()?.saver.now()
    else if (mod_ && !event.shiftKey && key === 'g' && inView) act = () => cm.gotoLine(view)
    else if (mod_ && !event.shiftKey && key === 'w' && tabs.active) act = () => close(tabs.active)
    else if (event.altKey && !mod_ && event.code === 'KeyZ') act = () => toggleWrap()
    if (!act) return
    event.preventDefault()
    event.stopPropagation()
    act()
  }
  document.addEventListener('keydown', keyed, true)

  const hidden = () => {
    if (document.visibilityState === 'hidden') flushAll()
    else poll()
  }
  document.addEventListener('visibilitychange', hidden)
  window.addEventListener('pagehide', flushAll)
  window.addEventListener('focus', poll)
  const polling = setInterval(poll, 1000)
  const seeing = new IntersectionObserver((entries) => {
    const was = visible
    visible = entries.some((one) => one.isIntersecting)
    if (visible && !was) {
      tree.view.paint()
      results.paint()
      poll()
    }
    if (!visible && was) flushAll()
  })
  seeing.observe(panel)

  const retheme = () => {
    if (inView) view.dispatch({ effects: themeC.reconfigure(cm.themeFor(ctx.theme())) })
    for (const doc of docs.values()) if (doc !== inView && doc.kind === 'text') doc.state = doc.state.update({ effects: themeC.reconfigure(cm.themeFor(ctx.theme())) }).state
  }
  const theming = new MutationObserver(retheme)
  theming.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'style'] })
  const scheme = matchMedia('(prefers-color-scheme: dark)')
  scheme.addEventListener('change', retheme)

  // What someone else did in the environment: its directory listed again, a file open looked at.
  const relist = new Set()
  let relisting = null
  const off = ctx.on('env_used', (message) => {
    if (message.env && message.env !== ctx.env.id) return
    if (!message.path) {
      refresh()
      return
    }
    const path = L.joinPath(tree.root, message.path)
    for (const dir of [L.parentOf(path), path]) if (tree.listed.has(dir)) relist.add(dir)
    clearTimeout(relisting)
    relisting = setTimeout(() => {
      const dirs = [...relist]
      relist.clear()
      for (const dir of dirs) list(dir)
    }, 150)
    for (const doc of docs.values()) if (L.within(doc.path, path)) check(doc)
  })

  // Started -------------------------------------------------------------------------------------

  sideTo(side)
  drawTree()
  drawTabs()
  drawBody()
  const top = await call('env.list', { path: tree.root }).catch((error) => ({ error }))
  if (top.error) {
    tree.failed.set(tree.root, said(top.error))
  } else {
    tree.root = top.path || tree.root
    tree.listed.set(tree.root, L.sorted(top.entries || []))
  }
  explorer.querySelector('.files-root').textContent = L.baseName(tree.root) || '/'
  explorer.querySelector('.files-root').title = tree.root
  drawTree()
  for (const dir of [...tree.open]) if (L.within(dir, tree.root) && dir !== tree.root) list(dir)
  if (tabs.active && !tabs.tabs.some((one) => one.path === tabs.active)) tabs.active = tabs.tabs[0]?.path || null
  if (tabs.active) show(tabs.active, { focus: false })
  if (closed) drawBanner()

  return {
    leave() {
      if (left) return
      // What the editor holds is put back in its file before the editor goes, then written.
      stash()
      inView = null
      flushAll()
      left = true
      clearInterval(polling)
      clearTimeout(persisting)
      ctx.keep('files', { tabs: tabs.tabs, active: tabs.active, open: [...tree.open], wrap, side })
      document.removeEventListener('keydown', keyed, true)
      document.removeEventListener('visibilitychange', hidden)
      window.removeEventListener('pagehide', flushAll)
      window.removeEventListener('focus', poll)
      seeing.disconnect()
      theming.disconnect()
      scheme.removeEventListener('change', retheme)
      off?.()
      merge?.destroy()
      view.destroy()
    },
    /** Opens a file, kept open, with the cursor on a line of it. */
    async reveal({ path, line = null, column = null } = {}) {
      if (!path) return
      await open(L.joinPath(tree.root, path), { pin: true, line, column })
    },
  }
}
