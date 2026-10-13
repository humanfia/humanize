// Exomyth's Timeline: every process of an epic -- its flows, each agent session, each program --
// as a row of tracks over time, drawn as Perfetto draws a trace, on one canvas.
//
// Nothing per span is in the page: the canvas is drawn on the next frame after anything
// changes, and only what is on it -- the processes scrolled to, and in each row of each track
// the spans in the time shown, found by a binary search, those narrower than a pixel drawn
// together as one run. Keys: W/S zoom at the pointer, A/D pan, F zooms to what is picked, 0
// shows it all; a wheel scrolls, sideways or with Shift pans, with Ctrl (a pinch) zooms.

import { h } from '../../dom.js'
import { menuOn } from '../../ui.js'
import { clock, firstEnding, lasted, locate } from './model.js'

/** Heights, in CSS pixels: the ruler, a process's head, one depth of a track. */
const RULER = 26
const HEAD = 24
const ROW = 18
const GAP = 4
/** Narrower than this, a span is drawn with its neighbours as one run. */
const THIN = 1.5
/** The pointer moved further than this, a press is a drag. */
const DRAG = 3

/** Each category's colour, as a theme token. */
const TOKENS = {
  flow: '--primary',
  session: '--lane-3',
  turn: '--lane-1',
  llm: '--lane-2',
  tool: '--lane-4',
  message: '--lane-5',
  event: '--lane-6',
  process: '--lane-3',
}

/**
 * The Timeline, drawn from a model once it is shown one.
 *
 * @param {{picked: (it: {span?: number, process?: number}|null) => void, ranged: (range: {from: number, to: number}|null) => void}} told
 *   What is told when a span or a process is picked, and when a stretch of time is.
 */
export function timeline(told) {
  const canvas = h('canvas', { class: 'exo-canvas', role: 'img', 'aria-label': 'Timeline', 'data-hmz': 'exomyth-canvas' })
  const spacer = h('div', { class: 'exo-spacer' })
  const node = h('div', { class: 'exo-scroll', tabindex: '0', 'data-hmz': 'exomyth-timeline' }, canvas, spacer)
  const tip = h('div', { class: 'tip exo-tip', role: 'tooltip', hidden: true })
  const ctx = canvas.getContext('2d', { alpha: false })

  let model = null
  /** The time shown, µs. */
  let t0 = 0
  let t1 = 1
  let width = 0
  let height = 0
  let ratio = 1
  let gutter = 200
  /** What is laid out: a row per process head and per depth of each open track. */
  let rows = []
  let total = 0
  /** Where each process's head is, and each track's first depth, by id; -1 where folded away. */
  let headAt = []
  let trackAt = []
  const folded = new Set()
  let picked = null
  let range = null
  let hover = null
  let pointer = null
  let found = null
  /** The agents, in the order they first appear: each its lane's colour. */
  let agents = []
  let colours = {}
  let palette = []
  const widths = new Map()
  let dirty = 0

  // ---------------------------------------------------------------- the theme

  function themed() {
    const style = getComputedStyle(document.documentElement)
    const read = (name) => style.getPropertyValue(name).trim()
    colours = {
      paper: read('--paper'),
      surface: read('--surface'),
      ink: read('--ink'),
      ink2: read('--ink-2'),
      ink3: read('--ink-3'),
      line: read('--line'),
      strong: read('--line-strong'),
      hover: read('--hover'),
      onFill: read('--on-fill'),
      onPrimary: read('--on-primary'),
      pink: read('--pink'),
      cyan: read('--cyan'),
      sans: read('--sans') || 'sans-serif',
      mono: read('--mono') || 'monospace',
      lanes: [1, 2, 3, 4, 5, 6].map((n) => read(`--lane-${n}`)),
    }
    for (const [cat, token] of Object.entries(TOKENS)) colours[cat] = read(token)
    paletted()
    widths.clear()
    draw()
  }

  /** Each string that is a category, by its index: the colour it is drawn in. */
  function paletted() {
    if (!model) return
    palette = model.strings.map((said) => colours[TOKENS[said] ? said : 'event'])
  }

  const watching = new MutationObserver(themed)
  watching.observe(document.documentElement, { attributes: true, attributeFilter: ['style', 'data-theme'] })

  // ---------------------------------------------------------------- laying out

  function laid() {
    rows = []
    headAt = new Array(model.processes.length).fill(-1)
    trackAt = new Array(model.tracks.length).fill(-1)
    let y = 0
    for (const id of model.order) {
      const process = model.processes[id]
      headAt[id] = y
      rows.push({ y, h: HEAD, process: id, track: -1, depth: -1 })
      y += HEAD
      if (!folded.has(id)) {
        for (const track of process.tracks) {
          trackAt[track] = y
          for (let depth = 0; depth < model.tracks[track].depths; depth++) {
            rows.push({ y, h: ROW, process: id, track, depth })
            y += ROW
          }
        }
      }
      y += GAP
    }
    total = y
    sized()
  }

  /** The row at a height inside what is laid out, or null. */
  function rowAt(y) {
    let low = 0
    let high = rows.length - 1
    while (low <= high) {
      const mid = (low + high) >> 1
      const row = rows[mid]
      if (y < row.y) high = mid - 1
      else if (y >= row.y + row.h) low = mid + 1
      else return row
    }
    return null
  }

  function sized() {
    width = node.clientWidth
    height = node.clientHeight
    gutter = Math.round(Math.max(120, Math.min(260, width * 0.26)))
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    spacer.style.height = `${Math.max(0, RULER + total - height)}px`
    draw()
  }

  const resizing = new ResizeObserver(sized)
  resizing.observe(node)

  // ---------------------------------------------------------------- where things are

  const plot = () => width - gutter
  const xOf = (t) => gutter + ((t - t0) / (t1 - t0)) * plot()
  const tOf = (x) => t0 + ((x - gutter) / plot()) * (t1 - t0)
  const top = () => node.scrollTop

  /** Keeps the time shown within the epic, and no narrower than ten microseconds. */
  function clamp() {
    const end = model ? model.end : 1
    const most = end * 1.2
    let span = Math.min(most, Math.max(10, t1 - t0))
    let from = t0 + (t1 - t0 - span) / 2
    from = Math.max(-end * 0.1, Math.min(from, end * 1.1 - span))
    t0 = from
    t1 = from + span
  }

  function zoom(factor, at) {
    t0 = at - (at - t0) * factor
    t1 = at + (t1 - at) * factor
    clamp()
    draw()
  }

  function pan(by) {
    t0 += by
    t1 += by
    clamp()
    draw()
  }

  function show(from, to) {
    const pad = Math.max(5, (to - from) * 0.05)
    t0 = from - pad
    t1 = to + pad
    clamp()
    draw()
  }

  function reset() {
    show(0, model ? model.end : 1)
  }

  // ---------------------------------------------------------------- drawing

  function draw() {
    if (!dirty) dirty = requestAnimationFrame(frame)
  }

  let last = 0
  function frame(now) {
    dirty = 0
    if (keys.size) {
      moved(Math.min(64, last ? now - last : 16))
      last = now
      draw()
    } else last = 0
    render()
  }

  /** Draws the canvas now; says how long that took, in milliseconds. */
  function render() {
    const began = performance.now()
    ratio = window.devicePixelRatio || 1
    const wide = Math.round(width * ratio)
    const tall = Math.round(height * ratio)
    if (canvas.width !== wide || canvas.height !== tall) {
      canvas.width = wide
      canvas.height = tall
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    ctx.fillStyle = colours.paper
    ctx.fillRect(0, 0, width, height)
    if (!model || !width || !height) return performance.now() - began
    const scroll = top()
    const step = ticked()
    grid(step)
    ctx.save()
    ctx.beginPath()
    ctx.rect(gutter, RULER, plot(), height - RULER)
    ctx.clip()
    ctx.font = `11px ${colours.sans}`
    ctx.textBaseline = 'middle'
    for (let at = first(scroll); at < rows.length; at++) {
      const row = rows[at]
      const y = RULER + row.y - scroll
      if (y > height) break
      if (row.track < 0) heads(row, y)
      else spans(model.tracks[row.track], row.depth, y + 1, ROW - 2, 1)
    }
    marked(scroll)
    ctx.restore()
    gutters(scroll)
    ruler(step)
    return performance.now() - began
  }

  /** The first row any of which shows, scrolled as far as it is. */
  function first(scroll) {
    let low = 0
    let high = rows.length
    while (low < high) {
      const mid = (low + high) >> 1
      if (rows[mid].y + rows[mid].h < scroll) low = mid + 1
      else high = mid
    }
    return low
  }

  /** The step between the ruler's marks: 1, 2 or 5 of a power of ten, some 100 pixels apart. */
  function ticked() {
    const wanted = ((t1 - t0) / Math.max(1, plot())) * 100
    const power = 10 ** Math.floor(Math.log10(wanted))
    for (const times of [1, 2, 5, 10]) if (power * times >= wanted) return power * times
    return power * 10
  }

  function grid(step) {
    ctx.fillStyle = colours.line
    for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) {
      const x = Math.round(xOf(t))
      if (x >= gutter) ctx.fillRect(x, RULER, 1, height - RULER)
    }
  }

  function ruler(step) {
    ctx.fillStyle = colours.surface
    ctx.fillRect(0, 0, width, RULER)
    ctx.fillStyle = colours.ink
    ctx.fillRect(0, RULER - 2, width, 2)
    ctx.font = `10px ${colours.mono}`
    ctx.textBaseline = 'middle'
    ctx.fillStyle = colours.ink3
    ctx.fillText(lasted(t1 - t0), 8, RULER / 2)
    ctx.save()
    ctx.beginPath()
    ctx.rect(gutter, 0, plot(), RULER)
    ctx.clip()
    for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) {
      const x = Math.round(xOf(t))
      ctx.fillStyle = colours.strong
      ctx.fillRect(x, RULER - 8, 1, 6)
      ctx.fillStyle = colours.ink2
      ctx.fillText(clock(t, step), x + 4, RULER / 2 - 1)
    }
    if (range) {
      const from = xOf(range.from)
      const to = xOf(range.to)
      const said = lasted(range.to - range.from)
      const wide = ctx.measureText(said).width + 10
      const x = Math.max(gutter, Math.min((from + to) / 2 - wide / 2, width - wide))
      ctx.fillStyle = colours.pink
      ctx.fillRect(x, 3, wide, RULER - 8)
      ctx.fillStyle = colours.onFill
      ctx.fillText(said, x + 5, RULER / 2 - 1)
    } else if (pointer && pointer.x > gutter) {
      const said = clock(tOf(pointer.x), step / 100)
      const wide = ctx.measureText(said).width + 10
      const x = Math.min(pointer.x + 1, width - wide)
      ctx.fillStyle = colours.cyan
      ctx.fillRect(x, 3, wide, RULER - 8)
      ctx.fillStyle = colours.onFill
      ctx.fillText(said, x + 5, RULER / 2 - 1)
    }
    ctx.restore()
  }

  /** A process's head: where open, a line over its span of time; folded, its spans in brief. */
  function heads(row, y) {
    const process = model.processes[row.process]
    if (folded.has(row.process)) {
      for (const id of process.tracks) {
        const track = model.tracks[id]
        spans(track, 0, y + 5, HEAD - 10, 0.4)
        if (track.depths > 1) spans(track, 1, y + 7, HEAD - 14, 1)
      }
      return
    }
    const from = Math.max(gutter, xOf(process.start))
    const to = Math.min(width, xOf(process.end))
    if (to < gutter || from > width) return
    ctx.fillStyle = swatch(process)
    ctx.fillRect(from, y + HEAD - 6, Math.max(1, to - from), 3)
  }

  /**
   * One depth of a track, from the first span ending in the time shown to the last starting
   * in it. Spans narrower than THIN within a pixel are one run, drawn in its longest's colour.
   */
  function spans(track, depth, y, tall, alpha) {
    const row = track.rows[depth]
    if (!row || !row.length) return
    const { start, end, cat } = track
    const scale = plot() / (t1 - t0)
    const mask = found && found.masks[track.id]
    ctx.globalAlpha = alpha
    let runFrom = -1
    let runTo = -1
    let runLong = -1
    let runColour = ''
    let runLit = false
    let shade = ''
    const flush = () => {
      if (runFrom < 0) return
      const tone = mask && !runLit ? 0.3 * alpha : alpha
      if (ctx.globalAlpha !== tone) ctx.globalAlpha = tone
      if (shade !== runColour) ctx.fillStyle = shade = runColour
      // On whole pixels, so that runs side by side neither leave seams nor wash each other out.
      const x = Math.floor(runFrom)
      ctx.fillRect(x, y, Math.max(1, Math.ceil(runTo) - x), tall)
      runFrom = -1
    }
    for (let at = firstEnding(row, end, t0); at < row.length; at++) {
      const i = row[at]
      if (start[i] > t1) break
      const x0 = gutter + (start[i] - t0) * scale
      const x1 = gutter + (end[i] - t0) * scale
      const lit = mask ? mask[i] === 1 : false
      if (x1 - x0 < THIN) {
        // One run a pixel at most, so that what fills each pixel shows in its colour.
        if (runFrom >= 0 && x0 < runFrom + 1) {
          runTo = Math.max(runTo, x1)
          if (x1 - x0 > runLong) {
            runLong = x1 - x0
            runColour = palette[cat[i]]
          }
          runLit ||= lit
          continue
        }
        flush()
        runFrom = x0
        runTo = x1
        runLong = x1 - x0
        runColour = palette[cat[i]]
        runLit = lit
        continue
      }
      flush()
      const from = Math.max(x0, gutter - 2)
      const to = Math.min(x1, width + 2)
      const tone = mask && !lit ? 0.3 * alpha : alpha
      if (ctx.globalAlpha !== tone) ctx.globalAlpha = tone
      const fill = palette[cat[i]]
      if (shade !== fill) ctx.fillStyle = shade = fill
      ctx.fillRect(from, y, Math.max(1, to - from - (to - from > 3 ? 1 : 0)), tall)
      if (tall >= 12 && to - from > 24) {
        labelled(track, i, from, to - from, y + tall / 2)
        shade = ''
      }
    }
    flush()
    ctx.globalAlpha = 1
  }

  function labelled(track, i, x, wide, y) {
    const said = model.strings[track.name_[i]]
    if (!said) return
    let size = widths.get(said)
    if (size === undefined) widths.set(said, (size = ctx.measureText(said).width))
    const room = wide - 8
    let text = said
    if (size > room) {
      const fits = Math.floor((room / size) * said.length) - 1
      if (fits < 2) return
      text = `${said.slice(0, fits)}…`
    }
    ctx.fillStyle = model.strings[track.cat[i]] === 'flow' ? colours.onPrimary : colours.onFill
    ctx.fillText(text, x + 4, y)
  }

  /** The middle of a span as drawn, scrolled as far as it is, or null where it is not laid out. */
  function centre(id, scroll) {
    const at = locate(model, id)
    if (!at) return null
    const track = model.tracks[at.track]
    const process = track.process
    const x = xOf(track.start[at.index])
    if (folded.has(process) || trackAt[at.track] < 0) return { x, y: RULER + headAt[process] - scroll + HEAD / 2, at }
    return { x, y: RULER + trackAt[at.track] + track.depth[at.index] * ROW - scroll + ROW / 2, at }
  }

  /** The span picked and the one pointed at, outlined; the stretch picked, washed. */
  function marked(scroll) {
    const outline = (it, colour) => {
      const at = locate(model, it)
      if (!at) return
      const where = centre(it, scroll)
      const track = model.tracks[at.track]
      const x0 = xOf(track.start[at.index])
      const x1 = Math.max(x0 + 2, xOf(track.end[at.index]))
      const tall = folded.has(track.process) ? HEAD - 10 : ROW - 2
      ctx.strokeStyle = colour
      ctx.lineWidth = 2
      ctx.strokeRect(x0, where.y - tall / 2, x1 - x0, tall)
    }
    if (hover && hover.span !== undefined && !(picked && picked.span === hover.span)) outline(hover.span, colours.cyan)
    if (picked && picked.span !== undefined) outline(picked.span, colours.pink)
    if (range) {
      const from = xOf(range.from)
      const to = xOf(range.to)
      ctx.globalAlpha = 0.14
      ctx.fillStyle = colours.pink
      ctx.fillRect(from, RULER, to - from, height - RULER)
      ctx.globalAlpha = 1
      ctx.fillStyle = colours.pink
      ctx.fillRect(Math.round(from), RULER, 1, height - RULER)
      ctx.fillRect(Math.round(to), RULER, 1, height - RULER)
    }
    if (pointer && pointer.x > gutter && !range) {
      ctx.fillStyle = colours.cyan
      ctx.fillRect(Math.round(pointer.x), RULER, 1, height - RULER)
    }
  }

  /** Each agent's colour, as its lane, in the order agents first appear; a flow in ink. */
  function swatch(process) {
    if (process.kind === 'flow') return colours.flow
    if (process.kind === 'os') return colours.process
    return colours.lanes[agents.indexOf(process.agent) % 5]
  }

  function gutters(scroll) {
    ctx.fillStyle = colours.surface
    ctx.fillRect(0, RULER, gutter, height - RULER)
    ctx.fillStyle = colours.strong
    ctx.fillRect(gutter - 1, RULER, 1, height - RULER)
    ctx.save()
    ctx.beginPath()
    ctx.rect(0, RULER, gutter - 1, height - RULER)
    ctx.clip()
    ctx.textBaseline = 'middle'
    for (let at = first(scroll); at < rows.length; at++) {
      const row = rows[at]
      const y = RULER + row.y - scroll
      if (y > height) break
      const process = model.processes[row.process]
      const indent = 8 + Math.min(process.level, 8) * 12
      if (row.track < 0) {
        if (picked && picked.process === row.process && picked.span === undefined) {
          ctx.fillStyle = colours.hover
          ctx.fillRect(0, y, gutter - 1, HEAD)
          ctx.fillStyle = colours.pink
          ctx.fillRect(0, y, 3, HEAD)
        }
        caret(indent, y + HEAD / 2, !folded.has(row.process))
        ctx.fillStyle = swatch(process)
        ctx.fillRect(indent + 12, y + HEAD / 2 - 4, 8, 8)
        ctx.font = `600 12px ${colours.sans}`
        ctx.fillStyle = colours.ink
        clipped(process.name, indent + 26, y + HEAD / 2, gutter - indent - 32)
      } else if (row.depth === 0) {
        ctx.font = `10px ${colours.mono}`
        ctx.fillStyle = colours.ink3
        clipped(model.tracks[row.track].name, indent + 26, y + ROW / 2, gutter - indent - 32)
      }
    }
    ctx.restore()
  }

  function caret(x, y, open) {
    ctx.strokeStyle = colours.ink2
    ctx.lineWidth = 1.5
    ctx.beginPath()
    if (open) {
      ctx.moveTo(x, y - 2)
      ctx.lineTo(x + 4, y + 2)
      ctx.lineTo(x + 8, y - 2)
    } else {
      ctx.moveTo(x + 2, y - 4)
      ctx.lineTo(x + 6, y)
      ctx.lineTo(x + 2, y + 4)
    }
    ctx.stroke()
  }

  function clipped(said, x, y, room) {
    if (room < 10) return
    const key = `${ctx.font}\u0000${said}`
    let size = widths.get(key)
    if (size === undefined) widths.set(key, (size = ctx.measureText(said).width))
    if (size <= room) {
      ctx.fillText(said, x, y)
      return
    }
    const fits = Math.max(1, Math.floor((room / size) * said.length) - 1)
    ctx.fillText(`${said.slice(0, fits)}…`, x, y)
  }

  // ---------------------------------------------------------------- what is under the pointer

  /** The span or process head at a point of the canvas, or null. */
  function hit(x, y) {
    if (!model || y < RULER) return null
    const row = rowAt(y - RULER + top())
    if (!row) return null
    if (x < gutter) return { process: row.process, caret: row.track < 0 && x < 8 + Math.min(model.processes[row.process].level, 8) * 12 + 14, gutter: true }
    const t = tOf(x)
    const slack = ((t1 - t0) / plot()) * 2
    const process = model.processes[row.process]
    const look = (track, depth) => {
      const list = track.rows[depth]
      if (!list) return null
      const at = firstEnding(list, track.end, t - slack)
      if (at < list.length && track.start[list[at]] <= t + slack) return track.first + list[at]
      return null
    }
    if (row.track >= 0) {
      const span = look(model.tracks[row.track], row.depth)
      return span === null ? { process: row.process } : { span, process: row.process }
    }
    if (folded.has(row.process)) {
      for (const depth of [1, 0]) {
        for (const id of process.tracks) {
          const span = look(model.tracks[id], depth)
          if (span !== null) return { span, process: row.process }
        }
      }
    }
    return { process: row.process, head: true }
  }

  function tipped(it, x, y) {
    if (!it || it.span === undefined) {
      tip.hidden = true
      return
    }
    const at = locate(model, it.span)
    const track = model.tracks[at.track]
    const i = at.index
    const said = (index) => model.strings[index]
    const tokens = track.in[i] || track.out[i] ? ` · ${track.in[i]} in · ${track.out[i]} out` : ''
    tip.textContent = `${said(track.name_[i])}\n${said(track.cat[i])} · ${lasted(track.dur[i])} at ${clock(track.start[i], 1000)}${said(track.model[i]) ? ` · ${said(track.model[i])}` : ''}${tokens}`
    tip.hidden = false
    const box = tip.getBoundingClientRect()
    // Kept over the chart, clear of the panel beside it.
    tip.style.left = `${Math.max(4, Math.min(x + 14, canvas.getBoundingClientRect().right - box.width - 4))}px`
    tip.style.top = `${y + 18 + box.height > innerHeight ? y - box.height - 8 : y + 18}px`
  }

  let pressed = null

  function local(event) {
    const box = canvas.getBoundingClientRect()
    return { x: event.clientX - box.left, y: event.clientY - box.top }
  }

  canvas.addEventListener('pointerdown', (event) => {
    if (!model || event.button !== 0) return
    const { x, y } = local(event)
    pressed = { x, y, t: tOf(x), dragging: false, gutter: x < gutter && y >= RULER }
    canvas.setPointerCapture(event.pointerId)
  })

  canvas.addEventListener('pointermove', (event) => {
    if (!model) return
    const { x, y } = local(event)
    pointer = { x, y }
    if (pressed && !pressed.gutter && (pressed.dragging || Math.abs(x - pressed.x) > DRAG)) {
      pressed.dragging = true
      const t = Math.max(0, Math.min(model.end, tOf(x)))
      const from = Math.max(0, Math.min(model.end, pressed.t))
      range = { from: Math.min(from, t), to: Math.max(from, t) }
      tip.hidden = true
      draw()
      return
    }
    const now = hit(x, y)
    hover = now
    tipped(now, event.clientX, event.clientY)
    canvas.style.cursor = now && now.gutter ? 'pointer' : 'default'
    draw()
  })

  canvas.addEventListener('pointerup', (event) => {
    if (!pressed) return
    const was = pressed
    pressed = null
    if (was.dragging) {
      told.ranged(range)
      return
    }
    const { x, y } = local(event)
    const it = hit(x, y)
    if (it && it.caret) {
      fold(it.process)
      return
    }
    if (range) {
      range = null
      told.ranged(null)
    }
    pick(it && it.span !== undefined ? { span: it.span } : it && (it.gutter || it.head) ? { process: it.process } : null)
  })

  // A press the browser took over -- a touch become a scroll -- is no press at all.
  canvas.addEventListener('pointercancel', () => {
    pressed = null
  })

  canvas.addEventListener('pointerleave', () => {
    pointer = null
    hover = null
    tip.hidden = true
    draw()
  })

  canvas.addEventListener('dblclick', (event) => {
    const { x, y } = local(event)
    const it = hit(x, y)
    if (it && it.span !== undefined) zoomTo(it.span)
    else if (it && it.gutter) fold(it.process)
  })

  node.addEventListener(
    'wheel',
    (event) => {
      if (!model) return
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? height : 1
      const dx = event.deltaX * unit
      const dy = event.deltaY * unit
      const { x } = local(event)
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault()
        zoom(Math.exp(dy * 0.01), x > gutter ? tOf(x) : (t0 + t1) / 2)
      } else if (event.shiftKey || Math.abs(dx) > Math.abs(dy)) {
        event.preventDefault()
        pan(((event.shiftKey && !dx ? dy : dx) / plot()) * (t1 - t0))
      }
    },
    { passive: false },
  )

  node.addEventListener('scroll', () => {
    tip.hidden = true
    draw()
  })

  menuOn(canvas, () => {
    const it = hover
    const items = []
    if (it && it.span !== undefined) {
      const at = locate(model, it.span)
      const said = model.strings[model.tracks[at.track].name_[at.index]]
      items.push({ head: said }, { label: 'Zoom', glyph: 'fit', act: () => zoomTo(it.span) }, { label: 'Pick', glyph: 'check', act: () => pick({ span: it.span }) })
    } else if (it && it.process !== undefined) {
      items.push({ head: model.processes[it.process].name }, { label: folded.has(it.process) ? 'Expand' : 'Collapse', glyph: 'down', act: () => fold(it.process) })
    }
    items.push('-', { label: 'Reset', glyph: 'fit', act: reset })
    return items
  })

  // ---------------------------------------------------------------- keys

  const keys = new Set()

  /** Moves the time shown as the keys held say, for `dt` milliseconds. */
  function moved(dt) {
    const at = pointer && pointer.x > gutter ? tOf(pointer.x) : (t0 + t1) / 2
    const span = t1 - t0
    if (keys.has('w')) zoom(Math.exp(-dt * 0.004), at)
    if (keys.has('s')) zoom(Math.exp(dt * 0.004), at)
    if (keys.has('a')) pan(-span * dt * 0.0012)
    if (keys.has('d')) pan(span * dt * 0.0012)
  }

  function typing(event) {
    const target = event.target
    return target instanceof Element && Boolean(target.closest('input, textarea, select, [contenteditable]'))
  }

  function down(event) {
    if (!model || node.hidden || event.metaKey || event.ctrlKey || event.altKey || typing(event) || document.body.classList.contains('dialog-open')) return
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key
    if ('wasd'.includes(key) && key.length === 1) {
      event.preventDefault()
      if (!keys.has(key)) {
        keys.add(key)
        draw()
      }
    } else if (key === 'f' && picked) {
      event.preventDefault()
      if (picked.span !== undefined) zoomTo(picked.span)
      else if (picked.process !== undefined) show(model.processes[picked.process].start, model.processes[picked.process].end)
    } else if (key === '0' || key === 'Home') {
      event.preventDefault()
      reset()
    } else if (key === 'Escape' && (range || picked)) {
      range = null
      told.ranged(null)
      pick(null)
    }
  }

  function up(event) {
    keys.delete(event.key.length === 1 ? event.key.toLowerCase() : event.key)
  }

  function blurred() {
    keys.clear()
  }

  document.addEventListener('keydown', down)
  document.addEventListener('keyup', up)
  window.addEventListener('blur', blurred)
  document.body.append(tip)
  themed()

  // ---------------------------------------------------------------- what the view asks

  function pick(it) {
    picked = it
    told.picked(it)
    draw()
  }

  function zoomTo(id) {
    const at = locate(model, id)
    if (!at) return
    const track = model.tracks[at.track]
    show(track.start[at.index], track.end[at.index])
    reveal(track.process)
  }

  function fold(id) {
    if (folded.has(id)) folded.delete(id)
    else folded.add(id)
    laid()
  }

  /** Scrolls so that a process's head shows, where it does not. */
  function reveal(id) {
    const y = headAt[id]
    if (y < 0) return
    const shown = height - RULER
    if (y < top() || y + HEAD > top() + shown) node.scrollTop = Math.max(0, y - shown / 3)
  }

  return {
    node,
    /** Draws a model: the first, or the same epic read again, kept as it was looked at. */
    shown(next) {
      const before = model
      model = next
      agents = [...new Set(model.processes.filter((one) => one.kind === 'session').map((one) => one.agent))]
      paletted()
      if (!before) {
        t0 = 0
        t1 = model.end
        reset()
      } else if (t1 >= before.end) {
        // Looking at the end of an epic that goes on: the end is followed.
        const span = t1 - t0
        t1 = Math.max(t1, model.end * 1.05)
        if (t0 <= 0) t0 = -model.end * 0.05
        else t0 = t1 - span
        clamp()
      }
      if (before && before.layout !== model.layout) {
        picked = null
        hover = null
        found = null
      }
      for (const id of [...folded]) if (id >= model.processes.length) folded.delete(id)
      laid()
    },
    pick(it) {
      picked = it
      if (it && it.span !== undefined) {
        const at = locate(model, it.span)
        if (at) reveal(model.tracks[at.track].process)
      } else if (it && it.process !== undefined) reveal(it.process)
      draw()
    },
    /** Lights the spans whose name holds the words; says which they are, in order of start. */
    find(words) {
      const said = words.trim().toLowerCase()
      if (!said || !model) {
        found = null
        draw()
        return []
      }
      const matching = new Uint8Array(model.strings.length)
      model.strings.forEach((one, index) => (matching[index] = one.toLowerCase().includes(said) ? 1 : 0))
      const masks = []
      const ids = []
      const starts = []
      for (const track of model.tracks) {
        const mask = new Uint8Array(track.count)
        for (let i = 0; i < track.count; i++) {
          if (matching[track.name_[i]]) {
            mask[i] = 1
            ids.push(track.first + i)
            starts.push(track.start[i])
          }
        }
        masks.push(mask)
      }
      const order = ids.map((_, k) => k).sort((a, b) => starts[a] - starts[b] || ids[a] - ids[b])
      found = { masks }
      draw()
      return order.map((k) => ids[k])
    },
    /** Shows a span, zoomed out to around it where it is out of what is shown. */
    visit(id) {
      const at = locate(model, id)
      if (!at) return
      const track = model.tracks[at.track]
      const from = track.start[at.index]
      const to = track.end[at.index]
      if (from > t1 || to < t0 || to - from > t1 - t0) {
        const span = Math.max(t1 - t0, (to - from) * 1.2)
        t0 = (from + to) / 2 - span / 2
        t1 = t0 + span
        clamp()
      }
      reveal(track.process)
      draw()
    },
    zoomTo,
    show,
    reset,
    /** Folds every process, or none. */
    foldAll(all) {
      folded.clear()
      if (all) for (const one of model.processes) folded.add(one.id)
      laid()
    },
    /** Forgets the stretch of time picked. */
    unrange() {
      range = null
      draw()
    },
    /** For tests and the curious: what is shown, and where a span is drawn on the screen. */
    debug: {
      render,
      view: () => ({ t0, t1 }),
      rows: () => rows.length,
      where(id) {
        const at = centre(id, top())
        if (!at) return null
        const box = canvas.getBoundingClientRect()
        const track = model.tracks[at.at.track]
        const x0 = Math.max(gutter, xOf(track.start[at.at.index]))
        const x1 = Math.min(width, xOf(track.end[at.at.index]))
        return { x: box.left + (x0 + x1) / 2, y: box.top + at.y }
      },
    },
    leave() {
      if (dirty) cancelAnimationFrame(dirty)
      watching.disconnect()
      resizing.disconnect()
      document.removeEventListener('keydown', down)
      document.removeEventListener('keyup', up)
      window.removeEventListener('blur', blurred)
      tip.remove()
    },
    themed,
  }
}
