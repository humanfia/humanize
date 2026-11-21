// What the Changes panel works out without a page: which group each changed file falls in and the
// letter it is marked with, the order files are listed in, the folders of the tree view, the rows
// drawn and picked, what a commit does when nothing is staged, how long ago a commit was made, a
// file's bytes as text or as a binary one, and where a diff's changes are.

import { moment } from '../../dom.js'
import { t } from '../../i18n.js'

/** The groups, in the order they are drawn, each with its title. */
export const GROUPS = [
  { id: 'merge', title: t('Merge Changes') },
  { id: 'staged', title: t('Staged Changes') },
  { id: 'changes', title: t('Changes') },
  { id: 'untracked', title: t('Untracked') },
]

/** How many bytes a side of a diff holds before it is drawn only once asked. */
export const LARGE = 2 * 1024 * 1024

/** What each letter means, said on hover. */
export const MEANING = {
  M: t('Modified'),
  A: t('Added'),
  D: t('Deleted'),
  R: t('Renamed'),
  C: t('Copied'),
  U: t('Conflict'),
  '?': t('Untracked'),
}

/** The letter a porcelain v2 status character is marked with: a type change is a modification. */
export function letterOf(char) {
  if (char === 'T') return 'M'
  return MEANING[char] ? char : 'M'
}

/** The last part of a path, and the folder it is in (`''` at the top). */
export function split(path) {
  const at = path.lastIndexOf('/')
  return at < 0 ? { name: path, dir: '' } : { name: path.slice(at + 1), dir: path.slice(0, at) }
}

/** Two names, as a listing orders them: case aside first, then exactly. */
function compareNames(a, b) {
  const x = a.toLowerCase()
  const y = b.toLowerCase()
  if (x !== y) return x < y ? -1 : 1
  return a < b ? -1 : a > b ? 1 : 0
}

/** Two paths in path order, a folder at a time: `a/z` before `a-b`, as a folder's files are first. */
export function comparePaths(a, b) {
  const x = a.split('/')
  const y = b.split('/')
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const said = compareNames(x[i], y[i])
    if (said) return said
  }
  return x.length - y.length
}

function entry(group, file, char) {
  const renamed = (char === 'R' || char === 'C') && file.orig ? file.orig : undefined
  return { key: `${group}:${file.path}`, group, path: file.path, orig: renamed, letter: char === '?' ? '?' : letterOf(char), ...split(file.path) }
}

/**
 * The files of `env.git.status`, in their groups and in path order. A file changed both in the
 * index and in the worktree is in both Staged Changes and Changes, as Source Control lists it.
 */
export function groupsOf(files = []) {
  const groups = { merge: [], staged: [], changes: [], untracked: [] }
  for (const file of files) {
    if (file.state === 'conflict') groups.merge.push(entry('merge', file, 'U'))
    else if (file.state === 'untracked') groups.untracked.push(entry('untracked', file, '?'))
    else {
      if (file.index && file.index !== '.') groups.staged.push(entry('staged', file, file.index))
      if (file.worktree && file.worktree !== '.') groups.changes.push(entry('changes', file, file.worktree))
    }
  }
  for (const list of Object.values(groups)) list.sort((a, b) => comparePaths(a.path, b.path))
  return groups
}

/** The paths an action on an entry acts on: a rename's old path too, so it is undone whole. */
export function pathsOf(entries) {
  const paths = []
  for (const one of entries) {
    paths.push(one.path)
    if (one.orig) paths.push(one.orig)
  }
  return [...new Set(paths)]
}

/**
 * Where an entry is as a whole path: `env.git.status` names it from the repository's top, which is
 * not the environment's workdir when that is a directory inside the repository.
 */
export function placeOf(root, path) {
  return `${String(root || '').replace(/\/+$/, '')}/${path}`
}

/**
 * The entries of a group as a tree of folders: each folder its folders then its files, both in
 * name order, a folder holding only one folder folded into it as `a/b`, as Source Control's tree
 * view draws them.
 */
export function treeOf(entries) {
  const root = { name: '', path: '', dirs: new Map(), files: [] }
  for (const one of entries) {
    let at = root
    if (one.dir) {
      for (const part of one.dir.split('/')) {
        if (!at.dirs.has(part)) at.dirs.set(part, { name: part, path: at.path ? `${at.path}/${part}` : part, dirs: new Map(), files: [] })
        at = at.dirs.get(part)
      }
    }
    at.files.push(one)
  }
  const shaped = (node) => {
    let dirs = [...node.dirs.values()].map(shaped)
    dirs = dirs.map((dir) => {
      let folded = dir
      while (folded.files.length === 0 && folded.dirs.length === 1) {
        const [only] = folded.dirs
        folded = { ...only, name: `${folded.name}/${only.name}` }
      }
      return folded
    })
    dirs.sort((a, b) => compareNames(a.name, b.name))
    const files = [...node.files].sort((a, b) => compareNames(a.name, b.name))
    return { name: node.name, path: node.path, dirs, files }
  }
  return shaped(root)
}

/** Every entry under a folder of the tree. */
function under(node) {
  return [...node.dirs.flatMap(under), ...node.files]
}

/**
 * The rows drawn, top to bottom: each group that has files, its header first, then its files --
 * one row each in the list view, or under their folders in the tree view. `collapsed` holds the
 * keys of the groups (`<group>`) and folders (`<group>:<path>/`) folded away: a file's key, `<group>:<path>`,
 * never ends in a slash.
 */
export function rowsOf(groups, { view = 'list', collapsed = new Set() } = {}) {
  const rows = []
  for (const { id, title } of GROUPS) {
    const entries = groups[id] || []
    if (!entries.length) continue
    const folded = collapsed.has(id)
    rows.push({ kind: 'group', key: id, group: id, title, count: entries.length, entries, open: !folded, depth: 0 })
    if (folded) continue
    if (view !== 'tree') {
      for (const one of entries) rows.push({ kind: 'file', key: one.key, group: id, entry: one, entries: [one], depth: 1 })
      continue
    }
    const walk = (node, depth) => {
      for (const dir of node.dirs) {
        const key = `${id}:${dir.path}/`
        const open = !collapsed.has(key)
        rows.push({ kind: 'dir', key, group: id, name: dir.name, path: dir.path, entries: under(dir), open, depth })
        if (open) walk(dir, depth + 1)
      }
      for (const one of node.files) rows.push({ kind: 'file', key: one.key, group: id, entry: one, entries: [one], depth })
    }
    walk(treeOf(entries), 1)
  }
  return rows
}

/**
 * What picking a row does to what is picked: alone it picks that row; with Ctrl or Cmd (`toggle`)
 * it adds or takes away that row; with Shift (`range`) it picks every row from the last picked
 * alone to this one. `keys` are the rows' keys in the order drawn.
 */
export function picked({ selected, anchor }, keys, key, { range = false, toggle = false } = {}) {
  if (range && anchor && keys.includes(anchor)) {
    const from = keys.indexOf(anchor)
    const to = keys.indexOf(key)
    const [lo, hi] = from < to ? [from, to] : [to, from]
    const next = toggle ? new Set(selected) : new Set()
    for (const one of keys.slice(lo, hi + 1)) next.add(one)
    return { selected: next, anchor }
  }
  if (toggle) {
    const next = new Set(selected)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return { selected: next, anchor: key }
  }
  return { selected: new Set([key]), anchor: key }
}

/** The entries the picked rows stand for, by group, each once. */
export function chosen(rows, selected) {
  const by = {}
  for (const row of rows) {
    if (!selected.has(row.key)) continue
    const list = (by[row.group] ||= new Map())
    for (const one of row.entries) list.set(one.key, one)
  }
  return Object.fromEntries(Object.entries(by).map(([group, list]) => [group, [...list.values()]]))
}

/** The action that moves a group's files across the index: unstaging the staged, staging the rest. */
export function moveOf(group) {
  return group === 'staged' ? 'unstage' : 'stage'
}

/**
 * What pressing Commit does: `refuse` with why, `commit`, or `stage` the files in `paths` first
 * and then commit, which is asked of the person first (Source Control's smart commit). Where
 * nothing is staged it stages the tracked changes, or, where there are none, the untracked files.
 */
export function commitPlan({ groups, message, amend = false }) {
  if (groups.merge.length) return { action: 'refuse', why: t('Resolve the merge conflicts before committing.') }
  if (!String(message || '').trim()) return { action: 'refuse', why: t('Write a commit message first.') }
  if (groups.staged.length || amend) return { action: 'commit' }
  const some = groups.changes.length ? groups.changes : groups.untracked
  if (!some.length) return { action: 'refuse', why: t('There is nothing to commit.') }
  return { action: 'stage', paths: pathsOf(some) }
}

/**
 * How the first line of a commit message stands against the lengths git's tools fold at: `ok`
 * up to 50 characters, `long` up to 72, `over` past it.
 */
export function subjectHint(message) {
  const length = [...String(message || '').split('\n')[0]].length
  return { length, level: length > 72 ? 'over' : length > 50 ? 'long' : 'ok' }
}

/** How long ago something happened, said as Source Control's history says it: `3 hours ago`. */
export function relative(stamp, now = Date.now()) {
  const at = moment(stamp)
  if (!at) return ''
  const seconds = Math.max(0, Math.round((now - at.getTime()) / 1000))
  if (seconds < 45) return t('just now')
  const steps = [
    [(n) => t('{n} minutes ago', { n }), 60, 3600],
    [(n) => t('{n} hours ago', { n }), 3600, 86400],
    [(n) => t('{n} days ago', { n }), 86400, 604800],
    [(n) => t('{n} weeks ago', { n }), 604800, 2592000],
    [(n) => t('{n} months ago', { n }), 2592000, 31536000],
    [(n) => t('{n} years ago', { n }), 31536000, Infinity],
  ]
  for (const [ago, size, upto] of steps) {
    if (seconds < upto - size / 2 || upto === Infinity) return ago(Math.max(1, Math.round(seconds / size)))
  }
  return ''
}

/** The moment, in full, for a commit's hover. */
export function fullDate(stamp) {
  const at = moment(stamp)
  return at ? at.toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC') : ''
}

/** How many bytes a base64 text holds, without decoding it. */
export function sizeOf(data) {
  if (!data) return 0
  const pad = data.endsWith('==') ? 2 : data.endsWith('=') ? 1 : 0
  return Math.floor((data.length * 3) / 4) - pad
}

/** A count of bytes as a person reads it. */
export function bytesText(bytes) {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KiB', 'MiB', 'GiB']
  let size = bytes
  let unit = -1
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit++
  }
  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[unit]}`
}

/**
 * One side of `env.git.diff`, decoded: its text, or `binary` where it holds a NUL in its first
 * 8000 bytes (git's own test) or is not UTF-8. `absent` is a side that is not there: the old side
 * of an added file, the new of a deleted one.
 */
export function decoded(data) {
  if (data === null || data === undefined) return { text: '', binary: false, absent: true, size: 0 }
  const raw = atob(data)
  const bytes = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
  const size = bytes.length
  if (bytes.subarray(0, 8000).includes(0)) return { text: '', binary: true, absent: false, size }
  try {
    return { text: new TextDecoder('utf-8', { fatal: true }).decode(bytes), binary: false, absent: false, size }
  } catch {
    return { text: '', binary: true, absent: false, size }
  }
}

/**
 * Where a diff's changes are, as runs of lines: each `{fromA, toA, fromB, toB}`, 0-based and
 * half-open, the old side's lines then the new side's, a side's run empty where lines were only
 * added or only taken away. Myers' diff, over what differs once the lines alike at both ends are
 * set aside; past `most` edits, the whole middle is one change, so that what is kept to find them
 * (`most` squared) stays small.
 */
export function hunks(oldText, newText, most = 1500) {
  const a = oldText.split('\n')
  const b = newText.split('\n')
  let start = 0
  while (start < a.length && start < b.length && a[start] === b[start]) start++
  let endA = a.length
  let endB = b.length
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA--
    endB--
  }
  if (start === endA && start === endB) return []
  const changed = myers(a.slice(start, endA), b.slice(start, endB), most)
  if (!changed) return [{ fromA: start, toA: endA, fromB: start, toB: endB }]
  const [inA, inB] = changed
  const runs = []
  let i = 0
  let j = 0
  while (i < inA.length || j < inB.length) {
    if (i < inA.length && j < inB.length && !inA[i] && !inB[j]) {
      i++
      j++
      continue
    }
    const run = { fromA: i, fromB: j }
    while ((i < inA.length && inA[i]) || (j < inB.length && inB[j])) {
      if (i < inA.length && inA[i]) i++
      else j++
    }
    runs.push({ fromA: run.fromA + start, toA: i + start, fromB: run.fromB + start, toB: j + start })
  }
  return runs
}

/** Which lines of each side changed, by Myers' O(ND) diff, or null past `most` edits. */
function myers(a, b, most) {
  const ids = new Map()
  const idOf = (line) => {
    if (!ids.has(line)) ids.set(line, ids.size)
    return ids.get(line)
  }
  const A = Int32Array.from(a, idOf)
  const B = Int32Array.from(b, idOf)
  const n = A.length
  const m = B.length
  const max = n + m
  const V = new Int32Array(2 * max + 2)
  const trace = []
  let found = -1
  for (let d = 0; d <= Math.min(max, most) && found < 0; d++) {
    for (let k = -d; k <= d; k += 2) {
      let x = k === -d || (k !== d && V[max + k - 1] < V[max + k + 1]) ? V[max + k + 1] : V[max + k - 1] + 1
      let y = x - k
      while (x < n && y < m && A[x] === B[y]) {
        x++
        y++
      }
      V[max + k] = x
      if (x >= n && y >= m) {
        found = d
        break
      }
    }
    trace.push(V.slice(max - d, max + d + 1))
  }
  if (found < 0) return null
  const inA = new Uint8Array(n)
  const inB = new Uint8Array(m)
  let x = n
  let y = m
  for (let d = found; d > 0; d--) {
    const prev = trace[d - 1]
    const at = (k) => prev[k + d - 1]
    const k = x - y
    const down = k === -d || (k !== d && at(k - 1) < at(k + 1))
    const prevK = down ? k + 1 : k - 1
    const prevX = at(prevK)
    const prevY = prevX - prevK
    if (down) inB[prevY] = 1
    else inA[prevX] = 1
    x = prevX
    y = prevY
  }
  return [inA, inB]
}
