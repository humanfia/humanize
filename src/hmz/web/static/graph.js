// An epic drawn as a graph: a frame for each flow it ran, a node for each agent -- and each
// person -- in the flow it worked in, the sessions an agent opened listed on its node, each as
// a lane of the turns it took over the run, and an arrow for each way the run handed from one
// agent to another, as many times as it did. While the run goes, the node working is lit, the
// last handover is the red one, and a line on every lane says where now is.

import { hash } from './api.js'
import { flowName, h, iconButton, lasting, svg, when } from './dom.js'
import { copy, menuOn } from './ui.js'

/** The measures the graph is laid out in, in pixels. */
const WIDE = 248
const HEAD = 70
const ROW = 32
const FOOT = 10
const APART = 150
const DOWN = 96
const INSET = 28
const LABEL = 34
const ACROSS = 4
/** The least a graph is shrunk to fit its height as it opens: past it, it is dragged through. */
const SMALLEST = 0.55
/** How far it zooms out and in. */
const LEAST = 0.2
const MOST = 3
/** How far a press moves before it drags the paper rather than clicks what is on it. */
const SLOP = 4
const BOW = 42

/**
 * @param {{open: (name: string) => void}} handlers What picking an agent does.
 * @returns {{node: HTMLElement, draw: (model: object, focus: string, epic: string) => void}}
 */
export function graph({ open }) {
  const stage = h('div', { class: 'stage' })
  const canvas = h('div', { class: 'canvas', 'data-hmz': 'graph', role: 'group', 'aria-label': 'The agents of the epic and who handed to whom' }, stage)
  const zoomed = h('span', { class: 'zoom-said', 'aria-live': 'polite' }, '100%')
  const zoom = h(
    'div',
    { class: 'zoom', role: 'group', 'aria-label': 'Zoom' },
    iconButton('minus', 'Zoom out', { onclick: () => scale(at / 1.2) }),
    zoomed,
    iconButton('plus', 'Zoom in', { onclick: () => scale(at * 1.2) }),
    iconButton('recenter', 'Recenter', { onclick: () => recenter() }),
  )
  const node = h('div', { class: 'graph' }, canvas, zoom)
  menuOn(canvas, () => [
    { label: 'Recenter', glyph: 'recenter', act: () => recenter() },
    { label: 'Actual size', glyph: 'plus', act: () => scale(1) },
  ])
  // The paper has no edge: the view is where on it the canvas's corner is, and how near.
  let at = 1
  let x = 0
  let y = 0
  // Until it is moved, the graph keeps to the middle of a view that grows or shrinks.
  let moved = false
  let size = { width: 0, height: 0 }
  let shape = ''
  let fitted = false
  let placing = []
  let nows = []

  function show() {
    stage.style.transform = `translate(${x}px, ${y}px) scale(${at})`
    canvas.style.setProperty('--grid-at', `${x}px ${y}px`)
    canvas.style.setProperty('--grid-big', `${120 * at}px`)
    canvas.style.setProperty('--grid-small', `${24 * at}px`)
    zoomed.textContent = `${Math.round(at * 100)}%`
  }

  /** Zooms to a scale about a point of the canvas, which stays where it is: its middle unless said. */
  function scale(to, about = { x: canvas.clientWidth / 2, y: canvas.clientHeight / 2 }) {
    const next = Math.min(MOST, Math.max(LEAST, to))
    x = about.x - ((about.x - x) * next) / at
    y = about.y - ((about.y - y) * next) / at
    at = next
    moved = true
    show()
  }

  /** The graph as it opens: as wide as the view, not so small it cannot be read, in its middle. */
  function recenter() {
    if (!canvas.clientWidth || !size.width) return
    const width = canvas.clientWidth
    const height = canvas.clientHeight
    at = Math.min(1, (width - 32) / size.width, Math.max(SMALLEST, (height - 32) / size.height))
    x = (width - size.width * at) / 2
    y = Math.max(16, (height - size.height * at) / 2)
    moved = false
    show()
  }

  /** Where on the canvas a pointer is. */
  const on = (event) => {
    const box = canvas.getBoundingClientRect()
    return { x: event.clientX - box.left, y: event.clientY - box.top }
  }

  // A pinch -- which a browser says as a wheel with Ctrl down -- and a mouse's wheel zoom about
  // the pointer; two fingers sliding over a trackpad move the paper. A trackpad is told from a
  // mouse as a browser lets it be: by its old wheelDelta, three times its delta the other way.
  canvas.addEventListener(
    'wheel',
    (event) => {
      event.preventDefault()
      const step = event.deltaMode === 1 ? 33 : event.deltaMode === 2 ? 400 : 1
      const sliding = !event.ctrlKey && (event.deltaX !== 0 || (event.wheelDeltaY ? event.wheelDeltaY === -3 * event.deltaY : event.deltaMode === 0))
      if (!sliding) {
        scale(at * Math.exp(-event.deltaY * step * (event.ctrlKey ? 0.01 : 0.0015)), on(event))
        return
      }
      x -= event.deltaX * step
      y -= event.deltaY * step
      moved = true
      show()
    },
    { passive: false },
  )
  // Safari, and so the desktop app's window, says a pinch as a gesture of its own.
  let pinched = 1
  canvas.addEventListener('gesturestart', (event) => {
    event.preventDefault()
    pinched = at
  })
  canvas.addEventListener('gesturechange', (event) => {
    event.preventDefault()
    scale(pinched * event.scale, on(event))
  })

  // Dragging anywhere moves the paper, a node and all; a press that hardly moves is a click.
  let dragged = null
  let letGo = false
  canvas.addEventListener('pointerdown', (event) => {
    if (event.button > 1 || event.target.closest('input, textarea, select')) return
    dragged = { id: event.pointerId, from: { x: event.clientX, y: event.clientY }, was: { x, y }, moving: false }
  })
  canvas.addEventListener('pointermove', (event) => {
    if (!dragged || event.pointerId !== dragged.id) return
    const dx = event.clientX - dragged.from.x
    const dy = event.clientY - dragged.from.y
    if (!dragged.moving) {
      if (Math.hypot(dx, dy) < SLOP) return
      dragged.moving = true
      canvas.setPointerCapture(event.pointerId)
      canvas.classList.add('dragging')
      getSelection()?.removeAllRanges()
    }
    x = dragged.was.x + dx
    y = dragged.was.y + dy
    moved = true
    show()
  })
  const drop = (event) => {
    if (!dragged || event.pointerId !== dragged.id) return
    if (dragged.moving) {
      letGo = true
      canvas.classList.remove('dragging')
      setTimeout(() => (letGo = false))
    }
    dragged = null
  }
  // What a drag lets go over is not clicked.
  canvas.addEventListener(
    'click',
    (event) => {
      if (!letGo) return
      event.stopPropagation()
      event.preventDefault()
    },
    { capture: true },
  )
  canvas.addEventListener('pointerup', drop)
  canvas.addEventListener('pointercancel', drop)

  /** Lays every lane's turns out again between the run's first moment and its last. */
  function place(from, to) {
    const span = Math.max(1, to - from)
    const pct = (moment) => `${Math.min(100, Math.max(0, ((moment - from) / span) * 100))}%`
    for (const { capsule, turn, said } of placing) {
      const long = Math.max(0, (turn.end ?? to) - turn.start)
      capsule.style.left = pct(turn.start)
      capsule.style.width = `max(3px, ${(long / span) * 100}%)`
      capsule.title = `${said}: ${when(turn.start)}, ${turn.end === null ? 'still going' : lasting(long)}`
    }
    for (const now of nows) now.style.left = pct(to)
  }

  /** How many agents stand side by side: as many as the view is wide enough for, at most four. */
  const across = () => Math.max(1, Math.min(ACROSS, Math.floor((canvas.clientWidth + APART) / ((WIDE + APART) * 0.75)) || ACROSS))
  let last = null
  new ResizeObserver(() => {
    if (last && across() !== laidAcross) {
      shape = ''
      fitted = false
      draw(...last)
    } else if (!moved) recenter()
  }).observe(canvas)
  let laidAcross = ACROSS

  function draw(model, focus, epic) {
    last = [model, focus, epic]
    // Drawn again only where what it is made of changed; the clocks on it move on their own.
    const made = JSON.stringify([model.frames, model.agents.map(({ name, role, working, status, spec, sessions, turns, tokens, under }) => [name, role, working, status, spec, turns, tokens, under, sessions.map((one) => [one.key, one.working, one.unread, one.turns.length, one.turns.map((turn) => turn.end === null)])]), model.handovers, model.latest, model.live, focus])
    if (made !== shape) {
      shape = made
      build(model, focus, epic)
    }
    place(model.from, model.to)
  }

  function build(model, focus, epic) {
    const byName = Object.fromEntries(model.agents.map((one) => [one.name, one]))
    laidAcross = across()
    const boxes = {}
    const frames = []
    let y = 0
    let widest = 0
    for (const frame of model.frames) {
      const rows = []
      for (let index = 0; index < frame.names.length; index += laidAcross) rows.push(frame.names.slice(index, index + laidAcross))
      if (!rows.length) rows.push([])
      let inner = 0
      let height = LABEL
      for (const row of rows) {
        const tall = Math.max(HEAD + FOOT, ...row.map((name) => heightOf(byName[name])))
        inner = Math.max(inner, row.length * WIDE + Math.max(0, row.length - 1) * APART)
        row.forEach((name, index) => {
          boxes[name] = { x: INSET + index * (WIDE + APART), y: y + height, w: WIDE, h: heightOf(byName[name]) }
        })
        height += tall + DOWN
      }
      height = height - DOWN + INSET
      const width = Math.max(inner, WIDE) + INSET * 2
      frames.push({ flow: frame.flow, x: 0, y, w: width, h: height, names: frame.names })
      widest = Math.max(widest, width)
      y += height + DOWN * 0.6
    }
    // Every frame stands in the middle of the widest.
    for (const frame of frames) {
      const shift = (widest - frame.w) / 2
      frame.x = shift
      for (const name of frame.names) boxes[name].x += shift
    }
    // Room above and below for the widest bows, which reach out as far as the frames are wide.
    // Stacked one over another, they bow out to the sides instead.
    const room = INSET + Math.min(200, widest * 0.16)
    const aside = INSET + (laidAcross === 1 ? WIDE * 0.4 : 0)
    size = { width: widest + 2 * aside, height: Math.max(y - DOWN * 0.6, HEAD) + 2 * room }
    for (const box of Object.values(boxes)) {
      box.x += aside
      box.y += room
    }
    for (const frame of frames) {
      frame.x += aside
      frame.y += room
    }

    placing = []
    nows = []
    const edges = svg(
      'svg',
      { class: 'edges', width: size.width, height: size.height, viewBox: `0 0 ${size.width} ${size.height}`, 'aria-hidden': 'true' },
      svg('defs', {}, arrow('arrow', 'edge-head'), arrow('arrow-latest', 'edge-head latest')),
      model.handovers.map((one) => edge(boxes[one.from], boxes[one.to], one, model.latest)),
    )
    stage.replaceChildren(
      ...frames.map((frame, index) =>
        h('div', { class: ['frame', index === 0 && 'root'], style: { left: `${frame.x}px`, top: `${frame.y}px`, width: `${frame.w}px`, height: `${frame.h}px` } }, h('span', { class: 'frame-label', title: frame.flow }, index === 0 ? 'flow' : 'called', h('b', {}, flowName(frame.flow)))),
      ),
      edges,
      ...model.agents.filter((one) => boxes[one.name]).map((one) => agentNode(one, boxes[one.name], focus === one.name, epic, model.live)),
    )
    stage.style.width = `${size.width}px`
    stage.style.height = `${size.height}px`
    if (!fitted && canvas.isConnected && canvas.clientWidth) {
      fitted = true
      recenter()
    } else show()
    if (focus && boxes[focus]) {
      const box = boxes[focus]
      x = canvas.clientWidth / 2 - (box.x + box.w / 2) * at
      y = canvas.clientHeight / 2 - (box.y + box.h / 2) * at
      moved = true
      show()
    }
  }

  function agentNode(agent, box, focused, epic, going) {
    const base = hash(`/epics/${encodeURIComponent(epic)}`)
    // The role an agent fills is said after its name, beside what it runs as; a person's is its name.
    const about = [agent.role !== agent.name && agent.role, agent.spec].filter(Boolean).join(' · ')
    const head = h(
      'button',
      { class: 'node-head', type: 'button', 'aria-pressed': String(focused) },
      h('span', { class: 'node-name' }, h('i', { class: 'swatch', 'aria-hidden': 'true' }), agent.name, agent.person ? h('span', { class: 'node-tag' }, 'person') : null),
      h('span', { class: 'node-spec mono' }, about || '—'),
      h('span', { class: 'node-state' }, agent.working ? h('span', { class: 'dot live', 'aria-hidden': 'true' }) : null, [agent.status, agent.tokens ? `${agent.tokens} tokens` : ''].filter(Boolean).join(' · ')),
    )
    head.addEventListener('click', () => open(agent.name))
    const sessions = agent.sessions.map((one) => {
      const track = h('span', { class: 'track', 'aria-hidden': 'true' })
      one.turns.forEach((turn, index) => {
        const capsule = h('span', { class: ['capsule', turn.end === null && 'open'] })
        placing.push({ capsule, turn, said: `${one.key}, turn ${index + 1}` })
        track.append(capsule)
      })
      if (going) {
        const now = h('span', { class: 'now' })
        nows.push(now)
        track.append(now)
      }
      return menuOn(h(
        'a',
        { class: ['node-session', one.working && 'working'], href: `${base}/sessions/${encodeURIComponent(one.key)}`, title: [one.key, one.about, `${one.turns.length} turn${one.turns.length === 1 ? '' : 's'}`].filter(Boolean).join(' · '), 'data-hmz': 'graph-session' },
        h('span', { class: 'session-key mono' }, one.working ? '●' : '○', ' ', one.key.split('/').pop(), one.unread ? h('i', { class: 'unread', title: 'Unread' }) : null),
        track,
        h('span', { class: 'sr-only' }, `${one.key}: ${one.turns.length} turns${one.working ? ', working' : ''}`),
      ), () => [
        { head: one.key },
        { label: 'Open', glyph: 'open', href: `${base}/sessions/${encodeURIComponent(one.key)}` },
        { label: 'Copy link', glyph: 'link', act: () => copy(`${location.origin}/${base}/sessions/${encodeURIComponent(one.key)}`, 'Link copied') },
      ])
    })
    const made = h(
      'div',
      {
        class: ['node', agent.working && 'working', agent.person && 'person', focused && 'focused', agent.sessions.some((one) => one.unread) && 'has-unread'],
        style: { left: `${box.x}px`, top: `${box.y}px`, width: `${box.w}px`, height: `${box.h}px`, '--lane': agent.color },
        'data-hmz': 'graph-agent',
        'data-agent': agent.name,
      },
      head,
      h(
        'div',
        { class: 'node-sessions' },
        h('a', { class: 'node-session node-log', href: `${base}/logs/${encodeURIComponent(agent.name)}`, 'data-hmz': 'graph-log' }, h('span', { class: 'session-key mono' }, '≡ log'), h('span', { class: 'dim' }, agent.person ? 'asked and answered' : 'every session')),
        sessions,
      ),
    )
    return menuOn(made, () => [
      { head: [agent.name, about].filter(Boolean).join(' · ') },
      agent.person ? null : { label: focused ? 'Shown' : 'Pick out', glyph: 'agent', act: () => open(agent.name), disabled: focused },
      { label: 'Open log', glyph: 'thread', href: `${base}/logs/${encodeURIComponent(agent.name)}` },
      ...agent.sessions.slice(0, 8).map((one) => ({ label: `Open ${one.key}`, glyph: 'open', href: `${base}/sessions/${encodeURIComponent(one.key)}` })),
      '-',
      agent.spec && !agent.person ? { label: 'Copy agent', glyph: 'copy', act: () => copy(agent.spec, 'Agent copied') } : null,
    ])
  }

  return { node, draw, recenter }
}

function heightOf(agent) {
  // The log's row, then a row per session.
  return HEAD + ((agent ? agent.sessions.length : 0) + 1) * ROW + FOOT
}

function arrow(id, kind) {
  return svg('marker', { id, viewBox: '0 0 10 10', refX: '8.5', refY: '5', markerWidth: '7', markerHeight: '7', orient: 'auto-start-reverse' }, svg('path', { d: 'M0 0 10 5 0 10Z', class: kind }))
}

/**
 * One handover, bowed to one side so its way back is bowed to the other, from the edge of one
 * node to the edge of the next, with how many times it happened at its middle.
 */
function edge(from, to, one, latest) {
  if (!from || !to) return null
  const a = { x: from.x + from.w / 2, y: from.y + from.h / 2 }
  const b = { x: to.x + to.w / 2, y: to.y + to.h / 2 }
  const length = Math.hypot(b.x - a.x, b.y - a.y) || 1
  const normal = { x: -(b.y - a.y) / length, y: (b.x - a.x) / length }
  // A handover past the nodes between bows wide enough to go round them.
  const bow = length > WIDE + APART + 10 ? Math.max(length * 0.3, WIDE * 0.75) : BOW
  const control = { x: (a.x + b.x) / 2 + normal.x * bow, y: (a.y + b.y) / 2 + normal.y * bow }
  const start = rim(from, a, control, 6)
  const end = rim(to, b, control, 10)
  const mid = { x: 0.25 * start.x + 0.5 * control.x + 0.25 * end.x, y: 0.25 * start.y + 0.5 * control.y + 0.25 * end.y }
  const last = Boolean(latest && latest[0] === one.from && latest[1] === one.to)
  const said = `×${one.count}`
  const wide = 14 + said.length * 7
  return svg(
    'g',
    { class: ['edge', last && 'latest'].filter(Boolean).join(' ') },
    svg('title', {}, `${one.from} handed to ${one.to} ${one.count} time${one.count === 1 ? '' : 's'}`),
    svg('path', { d: `M${start.x} ${start.y} Q${control.x} ${control.y} ${end.x} ${end.y}`, 'marker-end': `url(#${last ? 'arrow-latest' : 'arrow'})` }),
    svg('rect', { x: mid.x - wide / 2, y: mid.y - 10, width: wide, height: 20 }),
    svg('text', { x: mid.x, y: mid.y + 4, 'text-anchor': 'middle' }, said),
  )
}

/** Where a line from a node's middle towards a point leaves the node, and a little beyond. */
function rim(box, middle, toward, beyond) {
  const dx = toward.x - middle.x
  const dy = toward.y - middle.y
  const reach = Math.min(dx ? box.w / 2 / Math.abs(dx) : Infinity, dy ? box.h / 2 / Math.abs(dy) : Infinity)
  const length = Math.hypot(dx, dy) || 1
  return { x: middle.x + dx * reach + (dx / length) * beyond, y: middle.y + dy * reach + (dy / length) * beyond }
}
