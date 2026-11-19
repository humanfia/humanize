// What the Files panel decides without a page: how well a path matches what was typed into
// quick open, when an edited file is written back and that never two writes of one file are in
// flight, what a file's bytes are (text, its line endings and byte order mark, binary or a
// picture), what a file is called by its language, the tabs open, the explorer's rows, and how
// a search's matches are grouped. Nothing here touches the DOM, so the node tests run it.

/** The most bytes `env.read` hands back at once. */
export const CHUNK = 1048576

/** Past this many bytes a text file opens read-only. */
export const LARGE = 5 * 1048576

/** Past this many bytes a file is never opened. */
export const LARGEST = 20 * 1048576

/** How long after the last edit a file is written back, in milliseconds. */
export const AUTOSAVE = 800

/** What a refusal says when a file was changed by someone else after it was read. */
export const CHANGED = 'changed since you read it'

/** What a refusal says when the environment is gone. */
export const CLOSED = 'That environment has closed.'

// Paths ----------------------------------------------------------------------------------------

/** A path's last part. */
export function baseName(path) {
  const trimmed = String(path).replace(/\/+$/, '')
  return trimmed.slice(trimmed.lastIndexOf('/') + 1) || trimmed
}

/** The directory a path is in: `/` for one at the top. */
export function parentOf(path) {
  const trimmed = String(path).replace(/\/+$/, '')
  const at = trimmed.lastIndexOf('/')
  return at <= 0 ? '/' : trimmed.slice(0, at)
}

/** A path under a directory, or the path itself where it is absolute already. */
export function joinPath(dir, path) {
  if (String(path).startsWith('/')) return normal(path)
  return normal(`${dir.replace(/\/+$/, '')}/${path}`)
}

/** A path with `.`, `..` and doubled slashes taken out. */
export function normal(path) {
  const parts = []
  for (const part of String(path).split('/')) {
    if (!part || part === '.') continue
    if (part === '..') parts.pop()
    else parts.push(part)
  }
  return `/${parts.join('/')}`
}

/** A path as it is shown: under the root, relative to it. */
export function relative(path, root) {
  if (!root || root === '/') return path.replace(/^\/+/, '') || '/'
  if (path === root) return baseName(root)
  return path.startsWith(`${root}/`) ? path.slice(root.length + 1) : path
}

/** Whether `path` is `dir` or lies under it. */
export function within(path, dir) {
  return path === dir || path.startsWith(dir.endsWith('/') ? dir : `${dir}/`)
}

/** Each directory from the root down to the one a path is in. */
export function ancestors(path, root) {
  const out = []
  let at = parentOf(path)
  while (within(at, root) && at !== root) {
    out.unshift(at)
    at = parentOf(at)
  }
  out.unshift(root)
  return out
}

/** A new name refused, with why, or null where it would do. */
export function badName(name, siblings = []) {
  const said = String(name).trim()
  if (!said) return 'A name is needed.'
  if (said === '.' || said === '..') return 'That name is not allowed.'
  if (said.includes('\0')) return 'A name cannot hold a NUL.'
  if (said.split('/').some((part) => part === '..')) return 'A name cannot climb out with `..`.'
  if (!said.includes('/') && siblings.includes(said)) return `${said} is there already.`
  return null
}

// Fuzzy matching --------------------------------------------------------------------------------

const SEPARATOR = 10
const WORD = 8
const CAMEL = 6
const FIRST = 12
const RUN = 6
const CASE = 1
const GAP = 1
const BASENAME = 24

function boundary(target, j) {
  if (j === 0) return FIRST
  const before = target[j - 1]
  if (before === '/' || before === '\\') return SEPARATOR
  if (before === '_' || before === '-' || before === '.' || before === ' ') return WORD
  const here = target[j]
  if (before === before.toLowerCase() && before !== before.toUpperCase() && here !== here.toLowerCase()) return CAMEL
  return 0
}

/**
 * How well `query` matches `target`, as VS Code scores quick open: each letter of the query in
 * order, more for letters in a row, at the start of a word or just after a slash, and for the
 * same case; less for each letter skipped between them. The best alignment wins.
 *
 * @returns {{score: number, hits: number[]} | null} null where the query is not in it in order.
 */
export function score(query, target) {
  const q = String(query)
  const t = String(target)
  const n = q.length
  const m = t.length
  if (!n) return { score: 0, hits: [] }
  if (n > m) return null
  const ql = q.toLowerCase()
  const tl = t.toLowerCase()
  // Cheap first: every letter in order at all.
  let k = 0
  for (let j = 0; j < m && k < n; j++) if (tl[j] === ql[k]) k++
  if (k < n) return null
  // best[i][j]: the best score with query letter i at target letter j; run[i][j]: how long
  // the run ending there is; from[i][j]: where letter i-1 was.
  const NONE = -Infinity
  const best = Array.from({ length: n }, () => new Float64Array(m).fill(NONE))
  const run = Array.from({ length: n }, () => new Int32Array(m))
  const from = Array.from({ length: n }, () => new Int32Array(m).fill(-1))
  for (let i = 0; i < n; i++) {
    // The best of row i-1 so far, less the gap to here.
    let carried = NONE
    let carriedAt = -1
    for (let j = i; j < m; j++) {
      if (i > 0 && j - 2 >= 0 && best[i - 1][j - 2] !== NONE && best[i - 1][j - 2] > carried) {
        carried = best[i - 1][j - 2]
        carriedAt = j - 2
      }
      if (i > 0 && carried !== NONE) carried -= GAP
      if (tl[j] !== ql[i]) continue
      const own = 1 + boundary(t, j) + (t[j] === q[i] ? CASE : 0)
      if (i === 0) {
        best[0][j] = own - Math.min(j, 8) * 0.25
        run[0][j] = 1
        continue
      }
      const adjacent = best[i - 1][j - 1]
      let value = NONE
      if (adjacent !== NONE) {
        value = adjacent + own + RUN * Math.min(run[i - 1][j - 1], 3)
        run[i][j] = run[i - 1][j - 1] + 1
        from[i][j] = j - 1
      }
      if (carried !== NONE && carried + own > value) {
        value = carried + own
        run[i][j] = 1
        from[i][j] = carriedAt
      }
      best[i][j] = value
    }
  }
  let end = -1
  let top = NONE
  for (let j = 0; j < m; j++) {
    if (best[n - 1][j] > top) {
      top = best[n - 1][j]
      end = j
    }
  }
  if (end < 0) return null
  const hits = new Array(n)
  for (let i = n - 1, j = end; i >= 0; i--) {
    hits[i] = j
    j = from[i][j]
  }
  return { score: top, hits }
}

/**
 * How well a path matches quick open's query: its name is tried first and scores higher, as a
 * file is mostly looked for by its name; then the whole path. Spaces in the query are ignored.
 *
 * @returns {{score: number, hits: number[]} | null} The hits index the whole path.
 */
export function fuzzy(query, path) {
  const q = String(query).replace(/\s+/g, '')
  if (!q) return { score: 0, hits: [] }
  const name = baseName(path)
  const offset = path.length - name.length
  const whole = score(q, path)
  if (!whole) return null
  const own = q.includes('/') ? null : score(q, name)
  if (own && own.score + BASENAME >= whole.score) {
    const exact = name.toLowerCase() === q.toLowerCase() ? BASENAME : 0
    return { score: own.score + BASENAME + exact, hits: own.hits.map((at) => at + offset) }
  }
  return whole
}

/**
 * The paths that match, best first: on a tie, the shorter, then by name.
 *
 * @returns {{path: string, score: number, hits: number[]}[]}
 */
export function rank(query, paths, limit = 50) {
  const out = []
  for (const path of paths) {
    const got = fuzzy(query, path)
    if (got) out.push({ path, ...got })
  }
  out.sort((a, b) => b.score - a.score || a.path.length - b.path.length || (a.path < b.path ? -1 : a.path > b.path ? 1 : 0))
  return out.slice(0, limit)
}

/** Quick open's query, and the line and column a `path:line:col` ends in. */
export function quickQuery(said) {
  const text = String(said).trim()
  const found = /^(.*?)(?::(\d+))?(?::(\d+))?$/.exec(text)
  const line = found[2] ? Number(found[2]) : null
  const column = found[3] ? Number(found[3]) : null
  return { query: found[1], line, column }
}

/** A text cut into runs, each picked out where `hits` (indexes into it) say. */
export function spans(text, hits) {
  const marked = new Set(hits)
  const out = []
  for (let i = 0; i < text.length; i++) {
    const on = marked.has(i)
    const last = out[out.length - 1]
    if (last && last.hit === on) last.text += text[i]
    else out.push({ text: text[i], hit: on })
  }
  return out
}

// Autosave -------------------------------------------------------------------------------------

/**
 * Writes a file back after edits stop: `delay` after the last one, or at once when `now` is
 * asked (on blur, a tab switch, the page hidden, Ctrl+S). One write of a file is in flight at a
 * time; edits made meanwhile are written by the next, which waits its delay again unless a write
 * now is asked for. A failed write is not tried again until the next edit or `now`; a paused one
 * is not tried at all.
 *
 * @param {{save: () => Promise<unknown>, delay?: number, told?: (state: string, error?: unknown) => void,
 *   timer?: {set: (fn: () => void, ms: number) => unknown, clear: (handle: unknown) => void}}} options
 */
export function autosaver({ save, delay = AUTOSAVE, told = () => {}, timer = { set: (fn, ms) => setTimeout(fn, ms), clear: (one) => clearTimeout(one) } }) {
  let edits = 0
  let saved = 0
  let running = null
  let waiting = null
  let paused = false
  let state = 'saved'
  const say = (next, error) => {
    state = next
    told(next, error)
  }
  const stopWaiting = () => {
    if (waiting !== null) timer.clear(waiting)
    waiting = null
  }
  const schedule = () => {
    stopWaiting()
    if (!paused) waiting = timer.set(() => ((waiting = null), write()), delay)
  }
  function write() {
    if (running) return running
    if (paused) return Promise.resolve(false)
    if (saved >= edits) return Promise.resolve(true)
    const upto = edits
    say('saving')
    let pending
    try {
      pending = Promise.resolve(save())
    } catch (error) {
      pending = Promise.reject(error)
    }
    running = pending.then(
      () => {
        running = null
        saved = Math.max(saved, upto)
        if (saved < edits) {
          say('dirty')
          schedule()
        } else say('saved')
        return true
      },
      (error) => {
        running = null
        say('error', error)
        return false
      },
    )
    return running
  }
  return {
    /** Says the file was edited: it is written `delay` from now, unless edited again first. */
    edited() {
      edits++
      if (state !== 'saving') say('dirty')
      schedule()
    },
    /** Writes what is not written yet, now, after the write in flight: whether all of it was. */
    async now() {
      stopWaiting()
      for (;;) {
        if (running) {
          if (!(await running)) return false
          stopWaiting()
          continue
        }
        if (paused) return saved >= edits
        if (saved >= edits) return true
        if (!(await write())) return false
      }
    },
    /** Stops writing (while a conflict is open, or the environment closed), or goes on. */
    pause(on) {
      paused = on
      if (on) stopWaiting()
      else if (saved < edits) schedule()
    },
    /** Takes everything edited as written: after a reload, or a write made apart from this. */
    clean() {
      stopWaiting()
      saved = edits
      say('saved')
    },
    /** Stops for good: nothing more is written. */
    dispose() {
      paused = true
      stopWaiting()
    },
    get state() {
      return state
    },
    /** Whether there are edits not on disk yet, or being written. */
    get dirty() {
      return saved < edits || running !== null
    },
    get busy() {
      return running !== null
    },
  }
}

// Bytes ----------------------------------------------------------------------------------------

/** Base64, the way every file's bytes travel. */
export function toBase64(bytes) {
  let said = ''
  for (let i = 0; i < bytes.length; i += 0x8000) said += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000))
  return btoa(said)
}

/** The bytes base64 says. */
export function fromBase64(data) {
  const said = atob(data || '')
  const bytes = new Uint8Array(said.length)
  for (let i = 0; i < said.length; i++) bytes[i] = said.charCodeAt(i)
  return bytes
}

/** Several runs of bytes as one. */
export function joined(chunks) {
  const out = new Uint8Array(chunks.reduce((sum, one) => sum + one.length, 0))
  let at = 0
  for (const one of chunks) {
    out.set(one, at)
    at += one.length
  }
  return out
}

const IMAGES = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp', svg: 'image/svg+xml', bmp: 'image/bmp', ico: 'image/x-icon', avif: 'image/avif' }

/** The picture type a file's name says it is, or null. */
export function imageType(name) {
  return IMAGES[extension(name)] || null
}

/** A file's last extension, lower-cased, or ''. */
export function extension(name) {
  const base = baseName(name)
  const at = base.lastIndexOf('.')
  return at > 0 ? base.slice(at + 1).toLowerCase() : ''
}

/**
 * What a file's bytes are: text -- UTF-8, its line ending, whether it starts with a byte order
 * mark -- or binary, by a NUL in its first 8 KiB or bytes that are not UTF-8.
 *
 * @returns {{binary: true} | {binary: false, text: string, eol: '\n'|'\r\n', bom: boolean}}
 */
export function decode(bytes) {
  const head = bytes.subarray(0, 8192)
  if (head.includes(0)) return { binary: true }
  const bom = bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf
  let text
  try {
    text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bom ? bytes.subarray(3) : bytes)
  } catch {
    return { binary: true }
  }
  return { binary: false, text, eol: eolOf(text), bom }
}

/** The line ending a text mostly uses: CRLF where more lines end in it than in a bare LF. */
export function eolOf(text) {
  let crlf = 0
  let lf = 0
  for (let at = text.indexOf('\n'); at >= 0; at = text.indexOf('\n', at + 1)) {
    if (at > 0 && text[at - 1] === '\r') crlf++
    else lf++
  }
  return crlf > lf ? '\r\n' : '\n'
}

/** The bytes an editor's text is written as: its line endings and byte order mark put back. */
export function encode(text, { eol = '\n', bom = false } = {}) {
  const lines = String(text).replace(/\r\n?/g, '\n')
  const body = new TextEncoder().encode(eol === '\r\n' ? lines.replace(/\n/g, '\r\n') : lines)
  return bom ? joined([new Uint8Array([0xef, 0xbb, 0xbf]), body]) : body
}

/** A size as people say it. */
export function sizeOf(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

/** How a file opens: as text, read-only for its size, refused for its size, a picture, or binary. */
export function opening({ name, size }) {
  if (imageType(name)) return size > LARGEST ? 'too-large' : 'image'
  if (size > LARGEST) return 'too-large'
  if (size > LARGE) return 'large'
  return 'text'
}

// Languages and icons --------------------------------------------------------------------------

const LANGUAGES = {
  js: 'JavaScript', mjs: 'JavaScript', cjs: 'JavaScript', jsx: 'JavaScript JSX', ts: 'TypeScript', mts: 'TypeScript', cts: 'TypeScript', tsx: 'TypeScript JSX',
  py: 'Python', pyi: 'Python', rs: 'Rust', go: 'Go', java: 'Java', kt: 'Kotlin', c: 'C', h: 'C', cc: 'C++', cpp: 'C++', cxx: 'C++', hpp: 'C++', hh: 'C++',
  json: 'JSON', jsonc: 'JSON with Comments', jsonl: 'JSON Lines', md: 'Markdown', markdown: 'Markdown', html: 'HTML', htm: 'HTML', css: 'CSS', scss: 'SCSS',
  yaml: 'YAML', yml: 'YAML', toml: 'TOML', xml: 'XML', svg: 'SVG', sql: 'SQL', php: 'PHP', sh: 'Shell', bash: 'Shell', zsh: 'Shell', rb: 'Ruby',
  txt: 'Plain Text', lock: 'Plain Text', ini: 'INI', cfg: 'INI', csv: 'CSV', swift: 'Swift', lua: 'Lua', r: 'R', vue: 'Vue', svelte: 'Svelte',
}

const NAMED = { dockerfile: 'Dockerfile', makefile: 'Makefile', 'cmakelists.txt': 'CMake', '.gitignore': 'Ignore', '.dockerignore': 'Ignore', '.bashrc': 'Shell', '.zshrc': 'Shell', 'cargo.lock': 'TOML', '.env': 'Environment' }

/** What a file is written in, as the status bar says it. */
export function languageOf(name) {
  const base = baseName(name).toLowerCase()
  return NAMED[base] || LANGUAGES[extension(base)] || (base.startsWith('dockerfile') ? 'Dockerfile' : 'Plain Text')
}

const BADGES = {
  JavaScript: ['JS', 4], 'JavaScript JSX': ['JSX', 1], TypeScript: ['TS', 5], 'TypeScript JSX': ['TSX', 5], Python: ['PY', 5], Rust: ['RS', 2], Go: ['GO', 1],
  Java: ['JV', 2], Kotlin: ['KT', 3], C: ['C', 5], 'C++': ['C++', 5], JSON: ['{}', 4], 'JSON with Comments': ['{}', 4], 'JSON Lines': ['{}', 4],
  Markdown: ['MD', 1], HTML: ['<>', 2], CSS: ['#', 3], SCSS: ['#', 2], YAML: ['YML', 3], TOML: ['TML', 6], XML: ['<>', 6], SVG: ['SVG', 4], SQL: ['SQL', 1],
  PHP: ['PHP', 3], Shell: ['$', 6], Ruby: ['RB', 2], Dockerfile: ['DK', 5], Makefile: ['MK', 6], CSV: ['CSV', 1], Ignore: ['IG', 6], Swift: ['SW', 2], Lua: ['LUA', 5],
}

/** The badge a file is drawn with in the explorer and its tab: a few letters and a lane colour. */
export function badgeOf(name) {
  if (imageType(name) && extension(name) !== 'svg') return { glyph: 'IMG', lane: 3 }
  const [glyph, lane] = BADGES[languageOf(name)] || ['', 6]
  return { glyph, lane }
}

// Tabs -----------------------------------------------------------------------------------------

/**
 * Opens a file in the tabs: in the preview tab, which the next file opened replaces, or pinned,
 * which stays. A file open already is only made the active one -- and pinned, if asked. A new
 * tab goes next to the active one.
 *
 * @param {{tabs: {path: string, pinned: boolean}[], active: string|null}} state
 */
export function openTab(state, path, { pin = false } = {}) {
  const tabs = state.tabs.slice()
  const at = tabs.findIndex((one) => one.path === path)
  if (at >= 0) {
    if (pin && !tabs[at].pinned) tabs[at] = { ...tabs[at], pinned: true }
    return { tabs, active: path, replaced: null }
  }
  const preview = tabs.findIndex((one) => !one.pinned)
  if (!pin && preview >= 0) {
    const replaced = tabs[preview].path
    tabs[preview] = { path, pinned: false }
    return { tabs, active: path, replaced }
  }
  const after = tabs.findIndex((one) => one.path === state.active)
  tabs.splice(after >= 0 ? after + 1 : tabs.length, 0, { path, pinned: pin })
  return { tabs, active: path, replaced: null }
}

/** Pins a tab, as an edit or a double click does. */
export function pinTab(state, path) {
  return { ...state, tabs: state.tabs.map((one) => (one.path === path ? { ...one, pinned: true } : one)) }
}

/** Closes a tab; where it was the active one, the one to its right is, else to its left. */
export function closeTab(state, path) {
  const at = state.tabs.findIndex((one) => one.path === path)
  if (at < 0) return state
  const tabs = state.tabs.filter((one) => one.path !== path)
  let active = state.active
  if (active === path) active = tabs.length ? tabs[Math.min(at, tabs.length - 1)].path : null
  return { tabs, active }
}

/** Closes every tab but one, which is made the active one. */
export function closeOthers(state, path) {
  return { tabs: state.tabs.filter((one) => one.path === path), active: path }
}

/** Moves a tab to where another stands. */
export function moveTab(state, path, before) {
  if (path === before) return state
  const moving = state.tabs.find((one) => one.path === path)
  if (!moving) return state
  const tabs = state.tabs.filter((one) => one.path !== path)
  const at = before === null ? tabs.length : tabs.findIndex((one) => one.path === before)
  tabs.splice(at < 0 ? tabs.length : at, 0, moving)
  return { ...state, tabs }
}

/** How far a pressed tab is moved before it is being dragged, in pixels. */
export const DRAG = 4

/**
 * Where a tab let go at `x` goes: the path of the first tab whose middle is past it, to stand
 * before that one, or null for the end. `boxes` are the tabs' `{path, left, right}`, in order.
 */
export function dropBefore(boxes, x) {
  return boxes.find((box) => x < (box.left + box.right) / 2)?.path ?? null
}

/**
 * Lets a tab be dragged along its strip by the pointer, `drop` called with where it was let go,
 * as `moveTab` takes it. By pointer events and not the browser's drag and drop: a desktop web
 * view takes every drag over its window for the files dropped on it, and the page hears of none.
 */
export function dragTab(tab, drop) {
  tab.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || event.target.closest('.files-tab-close')) return
    const from = event.clientX
    let dragging = false
    tab.setPointerCapture(event.pointerId)
    const move = (moving) => {
      if (!dragging && Math.abs(moving.clientX - from) < DRAG) return
      dragging = true
      tab.classList.add('dragging')
    }
    const end = (ending) => {
      tab.removeEventListener('pointermove', move)
      tab.removeEventListener('pointerup', end)
      tab.removeEventListener('pointercancel', end)
      tab.classList.remove('dragging')
      if (!dragging || ending.type !== 'pointerup') return
      const boxes = [...tab.parentElement.children].map((one) => {
        const { left, right } = one.getBoundingClientRect()
        return { path: one.dataset.path, left, right }
      })
      drop(dropBefore(boxes, ending.clientX))
    }
    tab.addEventListener('pointermove', move)
    tab.addEventListener('pointerup', end)
    tab.addEventListener('pointercancel', end)
  })
}

/** The tabs with a path renamed, or every path under a directory renamed. */
export function renameTabs(state, from, to) {
  const moved = (path) => (within(path, from) ? to + path.slice(from.length) : path)
  return { tabs: state.tabs.map((one) => ({ ...one, path: moved(one.path) })), active: state.active && moved(state.active) }
}

// The explorer ---------------------------------------------------------------------------------

/**
 * The rows the explorer draws, top to bottom: each directory open and listed shows what is in it,
 * a directory first. With a filter, only names that hold it show, and the directories they are
 * in, open, whatever was open before.
 *
 * @param {{root: string, open: Set<string>, listed: Map<string, {name: string, kind: string}[]>,
 *   failed?: Map<string, string>}} tree
 * @returns {{path: string, name: string, kind: string, depth: number, open: boolean, loading?: boolean, error?: string}[]}
 */
export function treeRows(tree, filter = '') {
  const rows = []
  const needle = String(filter).trim().toLowerCase()
  const keeps = needle ? kept(tree, tree.root, needle) : null
  const walk = (dir, depth) => {
    const entries = tree.listed.get(dir)
    if (!entries) {
      if (tree.failed?.has(dir)) rows.push({ path: `${dir}/\0error`, name: tree.failed.get(dir), kind: 'error', depth, open: false })
      else rows.push({ path: `${dir}/\0loading`, name: 'Loading…', kind: 'loading', depth, open: false })
      return
    }
    for (const entry of entries) {
      const path = joinPath(dir, entry.name)
      if (keeps && !keeps.has(path)) continue
      // A link opens as a directory once it was listed as one.
      const isDir = entry.kind === 'dir' || (entry.kind === 'link' && tree.listed.has(path))
      const open = isDir && (keeps ? tree.listed.has(path) : tree.open.has(path))
      rows.push({ path, name: entry.name, kind: entry.kind, depth, open, size: entry.size, target: entry.target })
      if (open) walk(path, depth + 1)
    }
  }
  walk(tree.root, 0)
  return rows
}

function kept(tree, root, needle) {
  const keeps = new Set()
  const visit = (dir) => {
    let any = false
    for (const entry of tree.listed.get(dir) || []) {
      const path = joinPath(dir, entry.name)
      const own = entry.name.toLowerCase().includes(needle)
      const under = entry.kind === 'dir' && tree.listed.has(path) && visit(path)
      if (own || under) {
        keeps.add(path)
        any = true
      }
    }
    return any
  }
  visit(root)
  return keeps
}

/** Sorts a listing as the explorer shows it: directories first, then by name as people sort. */
export function sorted(entries) {
  const order = (kind) => (kind === 'dir' ? 0 : 1)
  return entries.slice().sort((a, b) => order(a.kind) - order(b.kind) || a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }))
}

/** The row next to one in the explorer, for the arrow keys. */
export function step(rows, path, by) {
  const real = rows.filter((one) => one.kind !== 'loading' && one.kind !== 'error')
  if (!real.length) return null
  const at = real.findIndex((one) => one.path === path)
  if (at < 0) return real[0].path
  return real[Math.max(0, Math.min(real.length - 1, at + by))].path
}

// Search ---------------------------------------------------------------------------------------

/**
 * A search's matches grouped by file, in the order the files first came, as rows the results
 * list draws: a file, then each of its matches.
 */
export function grouped(matches, root) {
  const files = new Map()
  for (const one of matches) {
    const path = joinPath(root, one.path)
    if (!files.has(path)) files.set(path, [])
    files.get(path).push({ ...one, path })
  }
  return [...files].map(([path, found]) => ({ path, matches: found }))
}

/** The rows of grouped matches, a file's own hidden where it is folded. */
export function resultRows(groups, folded = new Set()) {
  const rows = []
  for (const group of groups) {
    rows.push({ kind: 'file', path: group.path, count: group.matches.length, folded: folded.has(group.path) })
    if (!folded.has(group.path)) for (const one of group.matches) rows.push({ kind: 'match', ...one })
  }
  return rows
}

/** A JavaScript expression for what was searched for, or null where it is not one. */
export function pattern(query, { regex = false, caseSensitive = false } = {}) {
  try {
    return new RegExp(regex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), caseSensitive ? 'g' : 'gi')
  } catch {
    return null
  }
}

/**
 * Where on a line of a result the match is, to pick it out: the one at or after `column` (from 1),
 * else the first. Null where it cannot be found again, as when the search's regular expression
 * is one JavaScript's does not read.
 */
export function matchOn(text, query, options = {}, column = 1) {
  const re = pattern(query, options)
  if (!re || !query) return null
  let first = null
  for (const found of String(text).matchAll(re)) {
    if (!found[0].length) continue
    const span = [found.index, found.index + found[0].length]
    if (!first) first = span
    if (found.index >= column - 1) return span
  }
  return first
}

/** How much of a line is said before a match, at most, in characters. */
export const LEAD = 16

/**
 * A line of a result as a narrow list says it, the match in sight: its indentation gone, and
 * where more than `lead` characters stand before the match, an ellipsis in place of all but the
 * last of them.
 *
 * @param {string} text The line.
 * @param {[number, number] | null} span Where the match is on it, as `matchOn` found it.
 * @returns {{text: string, span: [number, number] | null}} What is said, and where the match is in that.
 */
export function snippet(text, span, lead = LEAD) {
  const line = String(text)
  const indent = line.length - line.trimStart().length
  if (!span) return { text: line.slice(indent), span: null }
  // A match in the indentation keeps what it matched.
  const start = Math.min(indent, span[0])
  const from = span[0] - start > lead ? span[0] - lead : start
  const mark = from > start ? '…' : ''
  const moved = from - mark.length
  return { text: mark + line.slice(from), span: [span[0] - moved, span[1] - moved] }
}

/**
 * The one change that turns `before` into `after`: what they share at either end is left be, so
 * a file reloaded from disk keeps where its cursor and scroll were.
 *
 * @returns {{from: number, to: number, insert: string} | null} null where they are the same.
 */
export function delta(before, after) {
  if (before === after) return null
  let start = 0
  const shorter = Math.min(before.length, after.length)
  while (start < shorter && before.charCodeAt(start) === after.charCodeAt(start)) start++
  let end = 0
  while (end < shorter - start && before.charCodeAt(before.length - 1 - end) === after.charCodeAt(after.length - 1 - end)) end++
  return { from: start, to: before.length - end, insert: after.slice(start, after.length - end) }
}
