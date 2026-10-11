// An epic drawn as a graph: a frame for each flow it ran, a node for each agent -- and each
// person -- in the flow it worked in, the sessions an agent opened listed on its node, each as
// a lane of the turns it took over the run, and an arrow for each way the run handed from one
// role to another, as many times as it did. While the run goes, the node working is lit, the
// last handover is the red one, and a line on every lane says where now is.

import { flowName, h, iconButton, lasting, svg, when } from './dom.js'

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
/** The least a graph is shrunk to fit its height: past it, it is scrolled through. */
const SMALLEST = 0.55
const BOW = 42

/**
 * @param {{open: (role: string) => void}} handlers What picking an agent does.
 * @returns {{node: HTMLElement, draw: (model: object, focus: string, epic: string) => void}}
 */
export function graph({ open }) {
  const stage = h('div', { class: 'stage' })
  const sizer = h('div', { class: 'sizer' }, stage)
  const canvas = h('div', { class: 'canvas', 'data-hmz': 'graph', role: 'group', 'aria-label': 'The agents of the epic and who handed to whom' }, sizer)
  const zoomed = h('span', { class: 'zoom-said', 'aria-live': 'polite' }, '100%')
  const zoom = h(
    'div',
    { class: 'zoom', role: 'group', 'aria-label': 'Zoom' },
    iconButton('minus', 'Zoom out', { onclick: () => scale(at / 1.2) }),
    zoomed,
    iconButton('plus', 'Zoom in', { onclick: () => scale(at * 1.2) }),
    iconButton('fit', 'Fit the graph', { onclick: () => fit() }),
  )
  const node = h('div', { class: 'graph' }, canvas, zoom)
  let at = 1
  let size = { width: 0, height: 0 }
  let shape = ''
  let fitted = false
  let placing = []
  let nows = []

  function scale(to) {
    at = Math.min(2, Math.max(0.3, to))
    stage.style.transform = `scale(${at})`
    sizer.style.width = `${size.width * at}px`
    sizer.style.height = `${size.height * at}px`
    zoomed.textContent = `${Math.round(at * 100)}%`
  }

  function fit() {
    if (!canvas.clientWidth || !size.width) return
    scale(Math.min(1, (canvas.clientWidth - 32) / size.width, Math.max(SMALLEST, (canvas.clientHeight - 32) / size.height)))
  }

  // Dragging the paper moves the view over it, as a canvas does.
  let dragged = null
  canvas.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || event.target.closest('a, button')) return
    dragged = { x: event.clientX, y: event.clientY, left: canvas.scrollLeft, top: canvas.scrollTop }
    canvas.setPointerCapture(event.pointerId)
    canvas.classList.add('dragging')
  })
  canvas.addEventListener('pointermove', (event) => {
    if (!dragged) return
    canvas.scrollLeft = dragged.left - (event.clientX - dragged.x)
    canvas.scrollTop = dragged.top - (event.clientY - dragged.y)
  })
  const drop = () => {
    dragged = null
    canvas.classList.remove('dragging')
  }
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
    }
  }).observe(canvas)
  let laidAcross = ACROSS

  function draw(model, focus, epic) {
    last = [model, focus, epic]
    // Drawn again only where what it is made of changed; the clocks on it move on their own.
    const made = JSON.stringify([model.frames, model.agents.map(({ role, working, status, spec, sessions, turns, tokens, under }) => [role, working, status, spec, turns, tokens, under, sessions.map((one) => [one.key, one.working, one.turns.length, one.turns.map((turn) => turn.end === null)])]), model.handovers, model.latest, model.live, focus])
    if (made !== shape) {
      shape = made
      build(model, focus, epic)
    }
    place(model.from, model.to)
  }

  function build(model, focus, epic) {
    const byRole = Object.fromEntries(model.agents.map((one) => [one.role, one]))
    laidAcross = across()
    const boxes = {}
    const frames = []
    let y = 0
    let widest = 0
    for (const frame of model.frames) {
      const rows = []
      for (let index = 0; index < frame.roles.length; index += laidAcross) rows.push(frame.roles.slice(index, index + laidAcross))
      if (!rows.length) rows.push([])
      let inner = 0
      let height = LABEL
      for (const row of rows) {
        const tall = Math.max(HEAD + FOOT, ...row.map((role) => heightOf(byRole[role])))
        inner = Math.max(inner, row.length * WIDE + Math.max(0, row.length - 1) * APART)
        row.forEach((role, index) => {
          boxes[role] = { x: INSET + index * (WIDE + APART), y: y + height, w: WIDE, h: heightOf(byRole[role]) }
        })
        height += tall + DOWN
      }
      height = height - DOWN + INSET
      const width = Math.max(inner, WIDE) + INSET * 2
      frames.push({ flow: frame.flow, x: 0, y, w: width, h: height, roles: frame.roles })
      widest = Math.max(widest, width)
      y += height + DOWN * 0.6
    }
    // Every frame stands in the middle of the widest.
    for (const frame of frames) {
      const shift = (widest - frame.w) / 2
      frame.x = shift
      for (const role of frame.roles) boxes[role].x += shift
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
      ...model.agents.filter((one) => boxes[one.role]).map((one) => agentNode(one, boxes[one.role], focus === one.role, epic, model.live)),
    )
    stage.style.width = `${size.width}px`
    stage.style.height = `${size.height}px`
    if (!fitted && canvas.isConnected && canvas.clientWidth) {
      fitted = true
      fit()
    } else scale(at)
    if (focus && boxes[focus]) {
      const box = boxes[focus]
      canvas.scrollTo({ left: Math.max(0, (box.x + box.w / 2) * at - canvas.clientWidth / 2), top: Math.max(0, (box.y + box.h / 2) * at - canvas.clientHeight / 2) })
    }
  }

  function agentNode(agent, box, focused, epic, going) {
    const base = `#/epics/${encodeURIComponent(epic)}`
    const head = h(
      'button',
      { class: 'node-head', type: 'button', 'aria-pressed': String(focused) },
      h('span', { class: 'node-name' }, h('i', { class: 'swatch', 'aria-hidden': 'true' }), agent.role, agent.person ? h('span', { class: 'node-tag' }, 'person') : null),
      h('span', { class: 'node-spec mono' }, agent.spec || '—'),
      h('span', { class: 'node-state' }, agent.working ? h('span', { class: 'dot live', 'aria-hidden': 'true' }) : null, [agent.status, agent.tokens ? `${agent.tokens} tokens` : ''].filter(Boolean).join(' · ')),
    )
    head.addEventListener('click', () => open(agent.role))
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
      return h(
        'a',
        { class: ['node-session', one.working && 'working'], href: `${base}/sessions/${encodeURIComponent(one.key)}`, title: one.about, 'data-hmz': 'graph-session' },
        h('span', { class: 'session-key mono' }, one.working ? '●' : '○', ' ', one.key.split('/').pop()),
        track,
        h('span', { class: 'sr-only' }, `${one.key}: ${one.turns.length} turns${one.working ? ', working' : ''}`),
      )
    })
    return h(
      'div',
      {
        class: ['node', agent.working && 'working', agent.person && 'person', focused && 'focused'],
        style: { left: `${box.x}px`, top: `${box.y}px`, width: `${box.w}px`, height: `${box.h}px`, '--lane': agent.color },
        'data-hmz': 'graph-agent',
        'data-role': agent.role,
      },
      head,
      sessions.length ? h('div', { class: 'node-sessions' }, sessions) : null,
    )
  }

  return { node, draw, fit }
}

function heightOf(agent) {
  return HEAD + (agent ? agent.sessions.length : 0) * ROW + FOOT
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
