// Exomyth's Flame: the epic's spans as a flame graph, drawn from the model model.js reads (see
// the comment at its top), over the stretch of time picked on the Timeline or the whole -- and
// under it, every slice name in a table.
//
// A frame's stack is the epic, then an agent (by its name, the role it fills after) -- or a
// flow, or a program -- each of its sessions merged into it, or apart as processes of their
// own, then its spans as they nest: turns, then model calls, tools, messages and events by
// name. A session's own span is its process's frame. Summed once for each stretch of time and
// way of merging, in one pass over the spans in it -- each depth of each track binary searched
// to the stretch and walked beside the depth over it, which holds each span's parent -- into
// typed columns every weight is read from; laid out once for each weight; drawn on the next
// frame after anything changes, a frame narrower than a pixel left out with all it holds.

import { h } from '../../dom.js'
import { clock, counted, firstEnding, lasted } from './model.js'
import { stats } from './stats.js'

/** Heights, in CSS pixels: a frame. */
const ROW = 18
/** Narrower than this, a frame is not drawn, nor anything it holds. */
const THIN = 1
/** How many summings are kept. */
const KEPT = 8

/** Each category's colour, as a theme token; `epic` is the root's. */
const TOKENS = {
  epic: '--line-strong',
  flow: '--primary',
  session: '--lane-3',
  turn: '--lane-1',
  llm: '--lane-2',
  tool: '--lane-4',
  message: '--lane-5',
  event: '--lane-6',
  process: '--lane-3',
}

/** The weights a frame can be sized by, as the page says them. */
const WEIGHTS = [
  ['time', 'Time'],
  ['in', 'Tokens in'],
  ['out', 'Tokens out'],
  ['count', 'Count'],
]

/** How much of a weight, said. */
function said(weight, value) {
  if (weight === 'time') return lasted(value)
  if (weight === 'count') return `${counted(value)} spans`
  return `${counted(value)} tokens`
}

/** A column of numbers that grows as it is written to. */
function grown(column) {
  const next = new column.constructor(column.length * 2)
  next.set(column)
  return next
}

/**
 * Sums the spans of a stretch of time -- the whole epic where `range` is null -- into frames,
 * and by slice name.
 *
 * Each frame has a parent, a name and a category (ids into the model's strings, or past them
 * into `labels`), how deep it is, and what its own spans came to: time inside the stretch, a
 * count, tokens in and out. Each name has the same, its spans' own time, and each span's time.
 */
export function aggregate(model, range, merge) {
  const from = range ? range.from : -Infinity
  const to = range ? range.to : Infinity
  const { strings } = model
  const base = strings.length
  const labels = []
  const labelled = new Map()
  const label = (text) => {
    let id = labelled.get(text)
    if (id === undefined) labelled.set(text, (id = base + labels.push(text) - 1))
    return id
  }

  let size = 0
  let parent = new Int32Array(1024)
  let name = new Int32Array(1024)
  let cat = new Int32Array(1024)
  let depth = new Int32Array(1024)
  let time = new Float64Array(1024)
  let count = new Float64Array(1024)
  let tin = new Float64Array(1024)
  let tout = new Float64Array(1024)
  let deepest = 0
  const node = (up, called, kind) => {
    if (size === parent.length) {
      parent = grown(parent)
      name = grown(name)
      cat = grown(cat)
      depth = grown(depth)
      time = grown(time)
      count = grown(count)
      tin = grown(tin)
      tout = grown(tout)
    }
    parent[size] = up
    name[size] = called
    cat[size] = kind
    depth[size] = up < 0 ? 0 : depth[up] + 1
    if (depth[size] > deepest) deepest = depth[size]
    return size++
  }
  // A span's frame, by its parent's, its name and its category.
  const kinds = model.categories.length + 1
  const slots = new Map(model.categories.map((one, at) => [strings.indexOf(one), at + 1]))
  const children = new Map()
  const child = (up, called, kind) => {
    const key = (up * base + called) * kinds + (slots.get(kind) || 0)
    let at = children.get(key)
    if (at === undefined) children.set(key, (at = node(up, called, kind)))
    return at
  }

  const root = node(-1, label(model.epic || 'epic'), label('epic'))
  // Each process's frame: its agent's, or its own.
  const groups = new Map()
  const tops = model.processes.map((one) => {
    const kind = one.kind === 'session' ? 'session' : one.kind === 'flow' ? 'flow' : 'process'
    const agent = one.agent || one.name
    const by = one.role || one.label
    const group = one.kind === 'session' ? (by && !agent.includes(by) ? `${agent} (${by})` : agent) : one.name || one.kind
    let top = groups.get(`${kind}\u0000${group}`)
    if (top === undefined) groups.set(`${kind}\u0000${group}`, (top = node(root, label(group), label(kind))))
    if (merge || one.kind === 'flow') return top
    return node(top, label(one.kind === 'os' ? `${one.name} ${one.pid}` : one.name), label(kind))
  })

  const sessionCat = strings.indexOf('session')
  // Each span in the stretch, in the order it was summed: its track, its index, its own time.
  const total = model.summary.spans
  const inTrack = new Int32Array(total)
  const inIndex = new Int32Array(total)
  const inLasting = new Float64Array(total)
  let found = 0
  const selves = []
  for (const track of model.tracks) {
    const { start, end, rows } = track
    const nodeOf = new Int32Array(track.count)
    const self = new Float64Array(track.count)
    selves.push(self)
    const top = tops[track.process]
    const own = model.processes[track.process].name
    let over = null
    let overFrom = 0
    let overTo = 0
    for (let d = 0; d < rows.length; d++) {
      const row = rows[d]
      const first = firstEnding(row, end, from)
      let at = first
      let up = overFrom
      for (; at < row.length; at++) {
        const i = row[at]
        if (start[i] > to) break
        const lasting = Math.max(0, Math.min(to, end[i]) - Math.max(from, start[i]))
        // The span over it is the last one a depth up to start no later than it does.
        let held = -1
        if (over) {
          while (up + 1 < overTo && start[over[up + 1]] <= start[i]) up++
          if (up < overTo && start[over[up]] <= start[i] && end[over[up]] >= start[i]) held = over[up]
        }
        let frame
        if (held >= 0) frame = child(nodeOf[held], track.name_[i], track.cat[i])
        else if (d === 0 && (track.cat[i] === sessionCat || strings[track.name_[i]] === own)) frame = top
        else frame = child(top, track.name_[i], track.cat[i])
        nodeOf[i] = frame
        time[frame] += lasting
        count[frame]++
        tin[frame] += track.in[i]
        tout[frame] += track.out[i]
        self[i] += lasting
        if (held >= 0) self[held] -= lasting
        inTrack[found] = track.id
        inIndex[found] = i
        inLasting[found++] = lasting
      }
      over = row
      overFrom = first
      overTo = at
    }
  }

  // By name: a slot each, summed, then each one's spans' times laid side by side and sorted.
  const names = new Map()
  const slotOf = new Int32Array(found)
  const named = []
  for (let k = 0; k < found; k++) {
    const track = model.tracks[inTrack[k]]
    const i = inIndex[k]
    const key = track.name_[i] * base + track.cat[i]
    let slot = names.get(key)
    if (slot === undefined) {
      names.set(key, (slot = named.length))
      named.push({ name: strings[track.name_[i]], nameId: track.name_[i], cat: strings[track.cat[i]], catId: track.cat[i], count: 0, total: 0, self: 0, max: 0, in: 0, out: 0, p50: 0, p95: 0 })
    }
    slotOf[k] = slot
    const one = named[slot]
    const lasting = inLasting[k]
    one.count++
    one.total += lasting
    one.self += selves[inTrack[k]][i]
    if (lasting > one.max) one.max = lasting
    one.in += track.in[i]
    one.out += track.out[i]
  }
  const offsets = new Int32Array(named.length + 1)
  for (let n = 0; n < named.length; n++) offsets[n + 1] = offsets[n] + named[n].count
  const filled = offsets.slice(0, named.length)
  const lastings = new Float64Array(found)
  for (let k = 0; k < found; k++) lastings[filled[slotOf[k]]++] = inLasting[k]
  for (let n = 0; n < named.length; n++) {
    const these = lastings.subarray(offsets[n], offsets[n + 1]).sort()
    const rank = (q) => these[Math.min(these.length - 1, Math.max(0, Math.ceil(q * these.length) - 1))]
    named[n].p50 = rank(0.5)
    named[n].p95 = rank(0.95)
  }

  return {
    size,
    root,
    base,
    labels,
    parent: parent.subarray(0, size),
    name: name.subarray(0, size),
    cat: cat.subarray(0, size),
    depth: depth.subarray(0, size),
    own: { time: time.subarray(0, size), count: count.subarray(0, size), in: tin.subarray(0, size), out: tout.subarray(0, size) },
    deepest,
    spans: found,
    named,
    laid: {},
  }
}

/**
 * The frames laid out by a weight: each one's total -- its own and what it holds, which a span
 * that says what its calls came to already does not count twice -- what of that is its own,
 * where it starts from the root's left edge, and what it holds, heaviest first.
 */
export function layout(agg, weight) {
  if (agg.laid[weight]) return agg.laid[weight]
  const { size, parent } = agg
  const own = agg.own[weight]
  const total = new Float64Array(size)
  const held = new Float64Array(size)
  const counts = new Int32Array(size + 1)
  for (let n = size - 1; n >= 0; n--) {
    total[n] = weight === 'count' ? own[n] + held[n] : Math.max(own[n], held[n])
    if (parent[n] >= 0) {
      held[parent[n]] += total[n]
      counts[parent[n] + 1]++
    }
  }
  for (let n = 0; n < size; n++) counts[n + 1] += counts[n]
  const kids = new Int32Array(Math.max(0, size - 1))
  const placed = counts.slice(0, size)
  for (let n = 1; n < size; n++) kids[placed[parent[n]]++] = n
  const x = new Float64Array(size)
  for (let n = 0; n < size; n++) {
    const these = kids.subarray(counts[n], counts[n + 1])
    if (these.length > 1) these.sort((a, b) => total[b] - total[a] || a - b)
    let at = x[n]
    for (const kid of these) {
      x[kid] = at
      at += total[kid]
    }
  }
  const self = new Float64Array(size)
  for (let n = 0; n < size; n++) self[n] = total[n] - held[n]
  return (agg.laid[weight] = { total, self, x, kids, from: counts })
}

/**
 * Draws the Flame into an element.
 *
 * @param {HTMLElement} el Where it is drawn.
 * @param {object} model The model, as model.js reads it.
 * @param {{from: number, to: number}|null} range The stretch of time picked, µs, or null.
 * @param {{timeline?: (name: string) => void, shared?: (share: number|null) => void}} [told]
 *   What is told when a name is to be shown on the Timeline, and what share of the whole the
 *   frames lit hold once they change.
 * @returns {{update: (model: object, range: object|null) => void, find: (words: string) => number|null, leave: () => void, debug: object}}
 *   How it is drawn again, searched, and left, and what tests read of it.
 */
export function mount(el, model, range, told = {}) {
  let weight = 'time'
  let merge = true
  let upward = false
  let agg = null
  let laid = null
  /** The frame zoomed to, and the names down to it, which find it again once summed again. */
  let zoomed = 0
  let path = []
  let words = ''
  let mask = null
  let share = null
  let chosen = null
  let hover = -1
  let drawn = 0
  const cache = new Map()

  const canvas = h('canvas', { class: 'exo-flame-canvas', role: 'img', 'aria-label': 'Flame', 'data-hmz': 'exomyth-flame-canvas' })
  const box = h('div', { class: 'exo-flame-box' }, canvas)
  const tip = h('div', { class: 'tip exo-tip', role: 'tooltip', hidden: true })
  const crumbs = h('nav', { class: 'exo-crumbs', 'aria-label': 'Zoom', 'data-hmz': 'exomyth-crumbs' })
  const stretch = h('span', { class: 'dim mono', 'data-hmz': 'exomyth-flame-range' })
  const weights = h(
    'div',
    { class: 'segmented', role: 'group', 'aria-label': 'Weight', 'data-hmz': 'exomyth-weight' },
    WEIGHTS.map(([key, text]) => h('button', { type: 'button', 'aria-pressed': String(key === weight), 'data-weight': key, onclick: () => weighed(key) }, text)),
  )
  const merging = h('button', { type: 'button', class: 'btn small', 'aria-pressed': 'true', 'data-hmz': 'exomyth-merge', onclick: () => merged(!merge) }, 'Merge sessions')
  const flipping = h('button', { type: 'button', class: 'btn small', 'aria-pressed': 'false', 'data-hmz': 'exomyth-upward', onclick: () => flipped(!upward) }, 'Bottom up')
  const table = stats({ chose: (one) => highlit(one), timeline: (one) => told.timeline?.(one.name) })
  el.replaceChildren(h('div', { class: 'exo-flame-bar' }, weights, merging, flipping, stretch), crumbs, box, table.node)
  document.body.append(tip)
  const ctx = canvas.getContext('2d')

  // ---------------------------------------------------------------- the theme

  let colours = {}
  let palette = []
  function themed() {
    const style = getComputedStyle(document.documentElement)
    const read = (token) => style.getPropertyValue(token).trim()
    colours = { paper: read('--paper'), ink: read('--ink'), onFill: read('--on-fill'), onPrimary: read('--on-primary'), pink: read('--pink'), cyan: read('--cyan'), sans: read('--sans') || 'sans-serif' }
    for (const [cat, token] of Object.entries(TOKENS)) colours[cat] = read(token)
    paletted()
    widths.clear()
    draw()
  }
  /** Each category, by its id, the colour it is drawn in. */
  function paletted() {
    if (!agg) return
    const of = (text) => colours[TOKENS[text] ? text : 'event']
    palette = [...model.strings.map(of), ...agg.labels.map(of)]
  }
  const watching = new MutationObserver(themed)
  watching.observe(document.documentElement, { attributes: true, attributeFilter: ['style', 'data-theme'] })

  // ---------------------------------------------------------------- summing

  const text = (id) => (id < agg.base ? model.strings[id] : agg.labels[id - agg.base])

  function summed() {
    const key = range ? `${range.from}:${range.to}:${merge}` : `all:${merge}`
    agg = cache.get(key)
    if (!agg) {
      agg = aggregate(model, range, merge)
      cache.set(key, agg)
      if (cache.size > KEPT) cache.delete(cache.keys().next().value)
    }
    laid = layout(agg, weight)
    paletted()
    if (chosen) chosen = agg.named.find((one) => one.name === chosen.name && one.cat === chosen.cat) || null
    zoomed = refound(path)
    if (!laid.total[zoomed]) zoomed = agg.root
    masked()
    told.shared?.(share)
    crumbed()
    table.shown(agg.named, chosen)
    stretch.textContent = range ? `${clock(range.from, 1000)} – ${clock(range.to, 1000)}` : 'Whole epic'
    draw()
  }

  /** The frame the names lead to from the root, as far as they still do. */
  function refound(names) {
    let at = agg.root
    for (const one of names) {
      const next = kidsOf(at).find((kid) => text(agg.name[kid]) === one.name && text(agg.cat[kid]) === one.cat)
      if (next === undefined) break
      at = next
    }
    return at
  }

  function kidsOf(n) {
    return Array.from(laid.kids.subarray(laid.from[n], laid.from[n + 1]))
  }

  function weighed(key) {
    weight = key
    for (const one of weights.children) one.setAttribute('aria-pressed', String(one.dataset.weight === key))
    laid = layout(agg, weight)
    if (!laid.total[zoomed]) zoom(agg.root)
    masked()
    told.shared?.(share)
    draw()
  }

  function merged(on) {
    merge = on
    merging.setAttribute('aria-pressed', String(on))
    path = []
    summed()
  }

  function flipped(on) {
    upward = on
    flipping.setAttribute('aria-pressed', String(on))
    draw()
  }

  function zoom(n) {
    zoomed = n
    path = []
    for (let at = n; at !== agg.root; at = agg.parent[at]) path.unshift({ name: text(agg.name[at]), cat: text(agg.cat[at]) })
    crumbed()
    draw()
  }

  function crumbed() {
    const chain = []
    for (let at = zoomed; at >= 0; at = agg.parent[at]) chain.unshift(at)
    crumbs.replaceChildren(
      ...chain.flatMap((n, k) => [
        k ? h('span', { class: 'dim', 'aria-hidden': 'true' }, ' / ') : null,
        n === zoomed ? h('span', { 'aria-current': 'true' }, text(agg.name[n])) : h('button', { type: 'button', class: 'exo-link', onclick: () => zoom(n) }, text(agg.name[n])),
      ]).filter(Boolean),
    )
  }

  /** Lights the frames named by a slice picked in the table, else by the words searched. */
  function masked() {
    mask = null
    share = null
    const ids = agg.base + agg.labels.length
    if (chosen) {
      mask = new Uint8Array(ids)
      mask[chosen.nameId] = 1
    } else if (words) {
      mask = new Uint8Array(ids)
      for (let id = 0; id < ids; id++) if (text(id).toLowerCase().includes(words)) mask[id] = 1
    }
    if (!mask) return
    // What the frames lit hold, none counted inside another lit: a share of the whole.
    share = 0
    const stack = [agg.root]
    while (stack.length) {
      const n = stack.pop()
      if (lit(n)) share += laid.total[n]
      else for (let k = laid.from[n]; k < laid.from[n + 1]; k++) stack.push(laid.kids[k])
    }
    share = laid.total[agg.root] ? share / laid.total[agg.root] : 0
  }

  /** Whether a frame is lit: by its name, and its category where a slice is picked. */
  const lit = (n) => mask[agg.name[n]] === 1 && (!chosen || agg.cat[n] === chosen.catId)

  function highlit(one) {
    chosen = one
    masked()
    told.shared?.(share)
    draw()
  }

  // ---------------------------------------------------------------- drawing

  let width = 0
  let ratio = 1
  const widths = new Map()
  let dirty = 0

  function draw() {
    if (!dirty) dirty = requestAnimationFrame(() => {
      dirty = 0
      render()
    })
  }

  const rowY = (d) => (upward ? (agg.deepest - d) * ROW : d * ROW)

  /** Draws the canvas now; says how long that took, in milliseconds. */
  function render() {
    const began = performance.now()
    if (!agg) return 0
    width = box.clientWidth
    const height = (agg.deepest + 1) * ROW
    ratio = window.devicePixelRatio || 1
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    const wide = Math.round(width * ratio)
    const tall = Math.round(height * ratio)
    if (canvas.width !== wide || canvas.height !== tall) {
      canvas.width = wide
      canvas.height = tall
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    ctx.fillStyle = colours.paper
    ctx.fillRect(0, 0, width, height)
    drawn = 0
    const { total, x } = laid
    const whole = total[zoomed]
    if (!width || !whole) return performance.now() - began
    // Only the rows scrolled to.
    const shown = el.getBoundingClientRect()
    const at = canvas.getBoundingClientRect()
    const top = Math.max(0, shown.top - at.top) - ROW
    const bottom = shown.bottom - at.top
    ctx.font = `11px ${colours.sans}`
    ctx.textBaseline = 'middle'
    const scale = width / whole
    const left = x[zoomed]
    const frame = (n, x0, w) => {
      const y = rowY(agg.depth[n])
      if (y < top || y > bottom) return
      drawn++
      ctx.globalAlpha = mask && !lit(n) ? 0.3 : 1
      ctx.fillStyle = palette[agg.cat[n]]
      ctx.fillRect(x0, y + 1, Math.max(1, w - (w > 3 ? 1 : 0)), ROW - 2)
      if (w > 24) {
        ctx.fillStyle = text(agg.cat[n]) === 'flow' ? colours.onPrimary : text(agg.cat[n]) === 'epic' ? colours.ink : colours.onFill
        clipped(text(agg.name[n]), x0 + 4, y + ROW / 2, w - 8)
      }
      ctx.globalAlpha = 1
      if (n === hover) {
        ctx.strokeStyle = colours.cyan
        ctx.lineWidth = 2
        ctx.strokeRect(x0 + 1, y + 1, Math.max(1, w - 2), ROW - 2)
      }
    }
    // What it is zoomed inside of, the whole width.
    for (let n = agg.parent[zoomed]; n >= 0; n = agg.parent[n]) frame(n, 0, width)
    const stack = [zoomed]
    while (stack.length) {
      const n = stack.pop()
      const w = total[n] * scale
      if (w < THIN) continue
      frame(n, (x[n] - left) * scale, w)
      for (let k = laid.from[n]; k < laid.from[n + 1]; k++) stack.push(laid.kids[k])
    }
    return performance.now() - began
  }

  function clipped(said, x, y, room) {
    let size = widths.get(said)
    if (size === undefined) widths.set(said, (size = ctx.measureText(said).width))
    if (size <= room) return ctx.fillText(said, x, y)
    const fits = Math.floor((room / size) * said.length) - 1
    if (fits >= 2) ctx.fillText(`${said.slice(0, fits)}…`, x, y)
  }

  // ---------------------------------------------------------------- the pointer

  /** The frame at a point of the canvas, or -1. */
  function hit(px, py) {
    if (!agg || !laid.total[zoomed]) return -1
    const d = upward ? agg.deepest - Math.floor(py / ROW) : Math.floor(py / ROW)
    if (d < 0) return -1
    if (d < agg.depth[zoomed]) {
      let n = zoomed
      while (agg.depth[n] > d) n = agg.parent[n]
      return n
    }
    const scale = width / laid.total[zoomed]
    const t = laid.x[zoomed] + px / scale
    let n = zoomed
    while (agg.depth[n] < d) {
      let next = -1
      for (let k = laid.from[n]; k < laid.from[n + 1]; k++) {
        const kid = laid.kids[k]
        if (t >= laid.x[kid] && t < laid.x[kid] + laid.total[kid]) {
          next = kid
          break
        }
      }
      if (next < 0) return -1
      n = next
    }
    return laid.total[n] * scale >= THIN ? n : -1
  }

  function tipped(n, cx, cy) {
    if (n < 0) {
      tip.hidden = true
      return
    }
    const whole = laid.total[agg.root]
    const part = whole ? (laid.total[n] / whole) * 100 : 0
    tip.textContent = `${text(agg.name[n])}\n${said(weight, laid.total[n])} total · ${said(weight, laid.self[n])} self · ${part.toFixed(part < 10 ? 2 : 1)}%\n${counted(agg.own.count[n])} ${agg.own.count[n] === 1 ? 'span' : 'spans'}`
    tip.hidden = false
    const shape = tip.getBoundingClientRect()
    // Kept over the chart, clear of the panel beside it.
    tip.style.left = `${Math.max(4, Math.min(cx + 14, canvas.getBoundingClientRect().right - shape.width - 4))}px`
    tip.style.top = `${cy + 18 + shape.height > innerHeight ? cy - shape.height - 8 : cy + 18}px`
  }

  function local(event) {
    const shape = canvas.getBoundingClientRect()
    return [event.clientX - shape.left, event.clientY - shape.top]
  }

  canvas.addEventListener('pointermove', (event) => {
    const n = hit(...local(event))
    tipped(n, event.clientX, event.clientY)
    canvas.style.cursor = n >= 0 ? 'pointer' : 'default'
    if (n !== hover) {
      hover = n
      draw()
    }
  })
  canvas.addEventListener('pointerleave', () => {
    hover = -1
    tip.hidden = true
    draw()
  })
  canvas.addEventListener('click', (event) => {
    const n = hit(...local(event))
    if (n >= 0) zoom(n)
  })

  function keyed(event) {
    if (event.key !== 'Escape' || el.hidden || zoomed === agg?.root || event.metaKey || event.ctrlKey || event.altKey || document.body.classList.contains('dialog-open')) return
    if (event.target instanceof Element && event.target.closest('input, textarea, select, [contenteditable]')) return
    event.preventDefault()
    zoom(agg.parent[zoomed])
  }
  document.addEventListener('keydown', keyed)

  const resizing = new ResizeObserver(draw)
  resizing.observe(box)
  el.addEventListener('scroll', draw)

  themed()
  summed()

  return {
    update(next, picked) {
      if (next !== model) cache.clear()
      model = next
      range = picked
      summed()
    },
    /** Lights the frames whose name holds the words; says what share of the whole they hold. */
    find(said) {
      words = said.trim().toLowerCase()
      if (words && chosen) {
        chosen = null
        table.shown(agg.named, chosen)
      }
      masked()
      draw()
      return share
    },
    leave() {
      if (dirty) cancelAnimationFrame(dirty)
      watching.disconnect()
      resizing.disconnect()
      document.removeEventListener('keydown', keyed)
      el.removeEventListener('scroll', draw)
      tip.remove()
    },
    /** For tests and the curious: how long summing and drawing take, and what is drawn where. */
    debug: {
      render,
      aggregate: () => {
        const began = performance.now()
        aggregate(model, range, merge)
        return performance.now() - began
      },
      drawn: () => drawn,
      zoomed: () => text(agg.name[zoomed]),
      share: () => share,
      total: () => laid.total[agg.root],
      /** The middle of the widest frame drawn by that name, on the screen, or null. */
      where(name) {
        let best = -1
        for (let n = 0; n < agg.size; n++) if (text(agg.name[n]) === name && (best < 0 || laid.total[n] > laid.total[best])) best = n
        if (best < 0 || !laid.total[zoomed]) return null
        const scale = width / laid.total[zoomed]
        const shape = canvas.getBoundingClientRect()
        const x0 = Math.max(0, (laid.x[best] - laid.x[zoomed]) * scale)
        const x1 = Math.min(width, (laid.x[best] + laid.total[best] - laid.x[zoomed]) * scale)
        return { x: shape.left + (x0 + x1) / 2, y: shape.top + rowY(agg.depth[best]) + ROW / 2 }
      },
    },
  }
}
