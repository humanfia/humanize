<script setup lang="ts">
// A flow is Python, played out: it declares its roles, each role is filled with an agent, its
// loop sends each turn to a session -- a fresh one each round, or one kept -- with ordinary
// code between the turns, and another flow can call it, handing down only the roles it
// declared. Pick a flow to watch its loop. Each loop is the one the flow really runs:
// `chat`, `ralph_loop`, `stateful_ralph` and `rlar` from the package,
// `src/hmz/flows/builtin/<name>/`. What a
// called flow is handed is `specs/flows.md`. The CLIs in the sockets are only examples.
import { computed, nextTick, ref } from 'vue'
import { withBase } from 'vitepress'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, streak, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

interface Ev {
  lane: number // -1 is the flow's own code, between the turns
  text: string
  fresh?: boolean // a session opened for this turn alone
  field?: string // an answer in a shape: the field the flow reads
}

interface Loop {
  key: string
  link: string
  roles: { name: string; cli: string }[]
  lanes: { role: number; label: string; kept: boolean }[]
  events: Ev[]
  split: number
  words: [string, string]
}

const LOOPS: Loop[] = [
  {
    key: 'chat',
    link: '/flows/chat',
    roles: [
      { name: 'assistant', cli: 'claude' },
      { name: 'human', cli: 'you' },
    ],
    lanes: [
      { role: 0, label: 'assistant · one session', kept: true },
      { role: 1, label: 'human · you', kept: true },
    ],
    events: [
      { lane: 0, text: 'answers' },
      { lane: 1, text: 'replies' },
      { lane: 0, text: 'answers' },
      { lane: 1, text: 'nothing' },
      { lane: -1, text: 'ends' },
    ],
    split: 2,
    words: ['It answers, then asks you', 'One session; silence ends it'],
  },
  {
    key: 'ralph_loop',
    link: '/flows/ralph-loop',
    roles: [{ name: 'agent', cli: 'codex' }],
    lanes: [{ role: 0, label: 'agent · new session each round', kept: false }],
    events: [
      { lane: 0, text: 'task', fresh: true },
      { lane: -1, text: 'pause' },
      { lane: 0, text: 'task', fresh: true },
      { lane: -1, text: 'pause' },
      { lane: 0, text: 'task', fresh: true },
    ],
    split: 2,
    words: ['A fresh session every round', 'Nothing remembered but the repo'],
  },
  {
    key: 'stateful_ralph',
    link: '/flows/stateful-ralph',
    roles: [{ name: 'agent', cli: 'kimi' }],
    lanes: [{ role: 0, label: 'agent · one session, kept', kept: true }],
    events: [
      { lane: -1, text: 'opens' },
      { lane: 0, text: 'task' },
      { lane: -1, text: 'pause' },
      { lane: 0, text: 'task' },
      { lane: -1, text: 'pause' },
      { lane: 0, text: 'task' },
    ],
    split: 3,
    words: ['One session, opened once', 'Every round remembers the last'],
  },
  {
    key: 'rlar',
    link: '/flows/rlar',
    roles: [
      { name: 'actor', cli: 'claude' },
      { name: 'reviewer', cli: 'codex' },
    ],
    lanes: [
      { role: 0, label: 'actor · one session, kept', kept: true },
      { role: 1, label: 'reviewer · new each round', kept: false },
    ],
    events: [
      { lane: 0, text: 'builds' },
      { lane: 1, text: 'reviews', fresh: true, field: 'done: no' },
      { lane: -1, text: 'notes →' },
      { lane: 0, text: 'fixes' },
      { lane: 1, text: 'reviews', fresh: true, field: 'done: yes' },
      { lane: -1, text: 'ends' },
    ],
    split: 3,
    words: ['Builds; a fresh reviewer: no', 'The notes carry; now: yes'],
  },
]

const which = ref(3)
const loop = computed(() => LOOPS[which.value])

const BEATS = computed(() => [
  'It declares its roles',
  loop.value.words[0],
  loop.value.words[1],
  'Another flow can call it',
  'It gets only what it declared',
])

interface Rect {
  x: number
  y: number
  w: number
  h: number
}
interface Pt {
  x: number
  y: number
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())

const BLOCK_H = 30
const CHIP_H = 26

// Everything is placed from the flow picked and the screen's width, so one timeline cuts for
// every flow and both layouts.
const G = computed(() => {
  const n = narrow.value
  const l = loop.value
  const w = n ? 360 : 640
  const h = n ? 400 : 360
  const card: Rect = n ? { x: 16, y: 40, w: 328, h: 84 } : { x: 24, y: 64, w: 150, h: 230 }
  const name: Pt = n ? { x: 30, y: 64 } : { x: 40, y: 98 }
  const roles = l.roles.length
  const slotW = n ? (300 - (roles - 1) * 10) / roles : 126
  const sockets: Rect[] = l.roles.map((_, i) =>
    n ? { x: 30 + i * (slotW + 10), y: 86, w: slotW, h: 28 } : { x: 36, y: 144 + i * 58, w: 126, h: 28 },
  )
  const x0 = n ? 16 : 208
  const x1 = n ? 344 : 620
  const laneYs = n ? (l.lanes.length > 1 ? [166, 230] : [186]) : l.lanes.length > 1 ? [112, 184] : [148]
  const codeY = n ? 300 : 262
  const colW = (x1 - x0) / l.events.length
  const cols = l.events.map((_, i) => ({ x: x0 + i * colW + 3, w: colW - 6 }))
  const blocks: Rect[] = l.events.map((e, i) =>
    e.lane < 0
      ? { x: cols[i].x, y: codeY + 2, w: cols[i].w, h: CHIP_H }
      : { x: cols[i].x, y: laneYs[e.lane], w: cols[i].w, h: BLOCK_H },
  )
  const beams = l.lanes.map((lane, i) => {
    const s = sockets[lane.role]
    const y = laneYs[i] + BLOCK_H / 2
    // On a phone the lanes sit under the sockets, and their colours say which is whose.
    if (n) return ''
    const sx = s.x + s.w
    const sy = s.y + s.h / 2
    return `M${sx} ${sy} C${sx + 22} ${sy} ${x0 - 26} ${y} ${x0 - 3} ${y}`
  })
  // A kept session is one thread through every turn it takes.
  const threads = l.events.map((e, i) => {
    if (e.lane < 0 || !l.lanes[e.lane].kept) return ''
    let j = i - 1
    while (j >= 0 && l.events[j].lane !== e.lane) j -= 1
    if (j < 0) return ''
    const y = laneYs[e.lane] + BLOCK_H / 2
    return `M${blocks[j].x + blocks[j].w} ${y} L${blocks[i].x} ${y}`
  })
  // The act where another flow calls this one: the world shrinks into the caller's frame. On
  // a phone it stays its size, so its words stay readable, and the caller holds its agents
  // under it, over the loop faded back.
  const s = n ? 1 : 0.78
  const o: Pt = n ? { x: 344, y: 392 } : { x: 628, y: 350 }
  const map = (p: Pt): Pt => ({ x: o.x + s * (p.x - o.x), y: o.y + s * (p.y - o.y) })
  const held = [...l.roles.map((r) => r.name), 'planner']
  const chipW = n ? (328 - (held.length - 1) * 8) / held.length : 112
  const caller: Rect[] = held.map((_, i) =>
    n ? { x: 16 + i * (chipW + 8), y: 330, w: chipW, h: 28 } : { x: 22, y: 150 + i * 50, w: chipW, h: 28 },
  )
  const calls = held.map((_, i) => {
    const c = caller[i]
    const declared = i < l.roles.length
    const t = declared ? sockets[i] : null
    if (n) {
      const from = { x: c.x + c.w / 2, y: c.y }
      const to = t ? map({ x: t.x + t.w / 2, y: t.y + t.h }) : map({ x: Math.min(c.x + c.w / 2, 320), y: card.y + card.h })
      return { from, to, d: `M${from.x} ${from.y} C${from.x} ${from.y - 60} ${to.x} ${to.y + 60} ${to.x} ${to.y}` }
    }
    const from = { x: c.x + c.w, y: c.y + c.h / 2 }
    const to = t ? map({ x: t.x, y: t.y + t.h / 2 }) : map({ x: card.x, y: card.y + card.h - 30 })
    return { from, to, d: `M${from.x} ${from.y} C${from.x + 24} ${from.y} ${to.x - 24} ${to.y} ${to.x} ${to.y}` }
  })
  return {
    n,
    w,
    h,
    card,
    name,
    sockets,
    x0,
    x1,
    laneYs,
    codeY,
    blocks,
    beams,
    threads,
    s,
    o,
    held,
    caller,
    calls,
    frame: n ? { x: 8, y: 10, w: 344, h: 380 } : { x: 10, y: 10, w: 620, h: 340 },
  }
})

const tone = (lane: number) => (lane < 0 ? 'var(--hmz-stage-dim)' : `var(--hmz-lane-${lane + 1})`)
const hue = (lane: number) => () => (lane < 0 ? palette.accent : palette.lane[lane])
const mid = (r: Rect): Pt => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 })

function pick(i: number) {
  if (i === which.value) return
  which.value = i
  void nextTick(() => scene.rebuild())
}

const EV = 1.05

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const g = G.value
    const l = loop.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, g.w, g.h) : undefined
    fx?.clear()
    const get = () => fx
    const one = (sel: string) => q(sel)[0]
    const cardMid = mid(g.card)

    // Clean slate, every loop.
    tl.set(q('.lp-world'), { autoAlpha: 1 }, 0)
    tl.set(q('.lp-shrink'), { scale: 1, svgOrigin: `${g.o.x} ${g.o.y}` }, 0)
    tl.set(q('.lp-lane, .lp-code, .lp-beam, .lp-ev, .lp-field, .lp-caller, .lp-call, .lp-no'), { autoAlpha: 0 }, 0)
    tl.set(q('.lp-slot-on'), { autoAlpha: 0 }, 0)
    tl.set(q('.lp-cli'), { autoAlpha: 0, x: g.n ? 0 : -210, y: g.n ? -70 : 0 }, 0)
    tl.set(q('.lp-field-in'), { x: 0, y: 0, scale: 1 }, 0)
    tl.set(q('.lp-planner'), { opacity: 1, x: 0 }, 0)

    // 0 · the flow, close up: its name, its roles, and an agent docking in each.
    tl.addLabel('beat-0', 0)
    const push = g.n ? 1.06 : 1.3
    const cam = one('.lp-cam')
    tl.fromTo(
      cam,
      { scale: push * 1.04, x: g.w / 2 - cardMid.x, y: (g.n ? 200 : g.h / 2) - cardMid.y, svgOrigin: `${cardMid.x} ${cardMid.y}` },
      { scale: push, duration: 3, ease: 'none' },
      0,
    )
    tl.fromTo(one('.lp-card-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.1, ease: 'cine' }, 0.1)
    tl.fromTo(one('.lp-card-fill'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.8 }, 0.4)
    tl.fromTo(q('.lp-card-words'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.6, stagger: 0.12 }, 0.5)
    tl.fromTo(q('.lp-slot'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4, stagger: 0.15 }, 0.8)
    l.roles.forEach((_, i) => {
      const t = 1.3 + i * 0.45
      const s = g.sockets[i]
      const to = mid(s)
      const from = g.n ? { x: to.x, y: to.y - 70 } : { x: to.x - 210, y: to.y }
      tl.to(q('.lp-cli')[i], { autoAlpha: 1, x: 0, y: 0, duration: 0.7, ease: 'cine.out' }, t)
      streak(tl, get, from, to, () => palette.lane[i], t, { duration: 0.6, bend: 0, burst: 14 })
      tl.to(q('.lp-slot-on')[i], { autoAlpha: 1, duration: 0.3 }, t + 0.55)
    })

    // 1 · the camera pulls back to the loop: a lane per session, and the flow's own code under them.
    const T1 = 3
    tl.addLabel('beat-1', T1)
    tl.to(cam, { scale: 1, x: 0, y: 0, duration: 1.4, ease: 'cine' }, T1)
    tl.to(q('.lp-lane'), { autoAlpha: 1, duration: 0.5, stagger: 0.12 }, T1 + 0.6)
    tl.fromTo(q('.lp-rail'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, stagger: 0.12, ease: 'cine' }, T1 + 0.6)
    tl.to(q('.lp-beam'), { autoAlpha: 1, duration: 0.1 }, T1 + 0.7)
    tl.fromTo(q('.lp-beam'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.7, stagger: 0.12, ease: 'cine' }, T1 + 0.7)
    tl.to(one('.lp-code'), { autoAlpha: 1, duration: 0.5 }, T1 + 0.9)

    // The turns and the code between them, one moment at a time. A mote of light is the baton:
    // what the flow does next starts where the last thing ended.
    const T = T1 + 1.5
    let last: Pt | null = null
    l.events.forEach((e, i) => {
      const t = T + i * EV
      if (i === l.split) tl.addLabel('beat-2', t - 0.15)
      const b = g.blocks[i]
      const c = mid(b)
      const el = q('.lp-ev')[i]
      const from: Pt = last ?? (e.lane >= 0 ? { x: g.x0 - 4, y: c.y } : { x: g.x0, y: c.y })
      streak(tl, get, from, c, hue(e.lane), t - 0.35, { duration: 0.45, bend: 0.25, burst: e.lane < 0 ? 6 : 10, size: 2.6 })
      last = c
      tl.set(el, { autoAlpha: 1 }, t)
      if (e.lane < 0) {
        tl.fromTo(el.querySelector('.lp-pop')!, { scale: 0.5, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.5, ease: 'back.out(2.2)' }, t)
        return
      }
      tl.fromTo(el.querySelector('.lp-block')!, { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 0.55, ease: 'cine.out' }, t)
      tl.fromTo(el.querySelector('.lp-block-text')!, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3 }, t + 0.3)
      const lane = l.lanes[e.lane]
      if (e.fresh) {
        // A session opened for this turn alone: a flare as it opens, and every earlier one of
        // its lane forgotten.
        const ring = el.querySelector('.lp-ring')!
        tl.fromTo(ring, { scale: 0.2, opacity: 0.9, transformOrigin: '50% 50%' }, { scale: 1.8, opacity: 0, duration: 0.8, ease: 'power2.out' }, t)
        tl.call(() => fx?.spark(b.x, c.y, palette.lane[e.lane], 18, 110), [], t)
        for (let j = 0; j < i; j += 1) {
          if (l.events[j].lane === e.lane) tl.to(q('.lp-ev')[j], { opacity: 0.28, duration: 0.5 }, t + 0.2)
        }
      } else if (lane.kept && g.threads[i]) {
        const thread = el.querySelector('.lp-thread')!
        tl.fromTo(thread, { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.45, ease: 'cine' }, t - 0.2)
      }
      if (e.field) {
        // An answer in a shape: the flow reads one field of it, not a paragraph.
        const f = q('.lp-field')[i]
        const next = g.blocks[i + 1] ? mid(g.blocks[i + 1]) : c
        const at = { x: c.x, y: b.y - 16 }
        tl.fromTo(f, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.2 }, t + 0.45)
        tl.fromTo(f.querySelector('.lp-field-in')!, { scale: 0.4, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.4, ease: 'back.out(2)' }, t + 0.45)
        tl.to(f.querySelector('.lp-field-in')!, { x: next.x - at.x, y: next.y - at.y, duration: 0.5, ease: 'cine' }, t + 0.95)
        tl.to(f, { autoAlpha: 0, duration: 0.2 }, t + 1.35)
      }
    })

    const TE = T + l.events.length * EV
    tl.addLabel('rest', TE + 0.3)

    // 3 · another flow calls this one: the world shrinks into its frame, and the agents this
    // flow held are handed back to be handed down.
    const T3 = TE + 1.2
    tl.addLabel('beat-3', T3)
    tl.to(one('.lp-shrink'), { scale: g.s, duration: 1.5, ease: 'cine' }, T3)
    tl.to(q('.lp-cli'), { autoAlpha: 0, duration: 0.4 }, T3 + 0.2)
    tl.to(q('.lp-slot-on'), { autoAlpha: 0, duration: 0.4 }, T3 + 0.2)
    tl.to(q('.lp-loop'), { opacity: g.n ? 0.1 : 0.3, duration: 1.2 }, T3 + 0.3)
    tl.to(q('.lp-caller'), { autoAlpha: 1, duration: 0.2 }, T3 + 0.6)
    tl.fromTo(one('.lp-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.2, ease: 'cine' }, T3 + 0.6)
    tl.fromTo(q('.lp-held'), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.5, stagger: 0.15, ease: 'back.out(2)' }, T3 + 1)

    // 4 · the call: each declared role gets an agent, and the one it never asked for does not.
    const T4 = T3 + 2.4
    tl.addLabel('beat-4', T4)
    g.calls.forEach((call, i) => {
      const t = T4 + i * 0.35
      const beam = q('.lp-call')[i]
      const declared = i < l.roles.length
      tl.set(beam, { autoAlpha: 1 }, t)
      if (declared) {
        tl.fromTo(beam, { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.6, ease: 'cine' }, t)
        streak(tl, get, call.from, call.to, () => palette.lane[i], t, { duration: 0.6, bend: 0, burst: 16 })
        tl.set(q('.lp-cli')[i], { x: 0, y: 0 }, t + 0.5)
        tl.to(q('.lp-cli')[i], { autoAlpha: 1, duration: 0.3 }, t + 0.55)
        tl.to(q('.lp-slot-on')[i], { autoAlpha: 1, duration: 0.3 }, t + 0.55)
      } else {
        tl.fromTo(beam, { drawSVG: '0%' }, { drawSVG: '0% 88%', duration: 0.5, ease: 'cine' }, t)
        tl.call(() => fx?.spark(call.to.x, call.to.y, palette.danger, 26, 120), [], t + 0.5)
        tl.fromTo(one('.lp-planner'), { x: 0 }, { keyframes: { x: [0, -5, 5, -3, 3, 0] }, duration: 0.45, ease: 'none' }, t + 0.5)
        tl.to(beam, { opacity: 0.25, duration: 0.5 }, t + 0.8)
        tl.to(one('.lp-planner'), { opacity: 0.4, duration: 0.5 }, t + 0.9)
        tl.fromTo(one('.lp-no'), { autoAlpha: 0, y: 4 }, { autoAlpha: 1, y: 0, duration: 0.4 }, t + 0.9)
      }
    })
    const TX = T4 + g.calls.length * 0.35 + 3.2
    tl.to(q('.lp-world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, TX)
    tl.set(q('.lp-caller'), { autoAlpha: 0 }, TX + 0.7)
    tl.set(q('.lp-loop'), { opacity: 1 }, TX + 0.7)
  },
})
</script>

<template>
  <div class="hmz-loops">
    <div class="picker" role="group" aria-label="Which flow to watch">
      <button
        v-for="(one, i) in LOOPS"
        :key="one.key"
        type="button"
        :class="{ on: which === i }"
        :aria-pressed="which === i"
        @click="pick(i)"
      >
        {{ one.key }}
      </button>
      <a class="open" :href="withBase(loop.link)">{{ loop.key }} →</a>
    </div>
    <HmzStage
      :scene="scene"
      :beats="BEATS"
      sim
      mobile-ratio="9 / 10"
      :label="`The flow ${loop.key} declares its roles: ${loop.roles.map((r) => r.name).join(' and ')}, and an agent fills each. Its loop: ${loop.words[0]}; ${loop.words[1]}. Between the turns it runs ordinary Python. Then another flow calls it, holding more agents than it needs; only the roles ${loop.key} declared are handed to it, and the planner it never asked for is refused.`"
    >
      <svg :viewBox="`0 0 ${G.w} ${G.h}`" aria-hidden="true">
        <defs>
          <radialGradient id="hmz-loops-glow">
            <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.5" />
            <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
          </radialGradient>
        </defs>
        <g class="lp-world">
          <!-- The caller, drawn behind the world it will hold. -->
          <g class="lp-caller">
            <rect class="lp-frame" :x="G.frame.x" :y="G.frame.y" :width="G.frame.w" :height="G.frame.h" rx="16" />
            <text class="lp-caller-name" :x="G.frame.x + 16" :y="G.n ? G.frame.y + G.frame.h - 10 : G.frame.y + 26">your flow</text>
            <text v-if="!G.n" class="lp-cap" :x="G.caller[0].x" :y="G.caller[0].y - 12">holds</text>
            <path v-for="(c, i) in G.calls" :key="`c${i}`" class="lp-call" :d="c.d" :style="{ stroke: i < loop.roles.length ? `var(--hmz-lane-${i + 1})` : 'var(--hmz-lane-5)' }" />
            <g v-for="(c, i) in G.caller" :key="`h${i}`" :class="{ 'lp-planner': i === G.held.length - 1 }">
              <g class="lp-held">
                <rect class="lp-held-box" :x="c.x" :y="c.y" :width="c.w" :height="c.h" rx="8" :style="{ stroke: i < loop.roles.length ? `var(--hmz-lane-${i + 1})` : 'var(--hmz-lane-6)' }" />
                <text class="lp-held-name" :x="c.x + c.w / 2" :y="c.y + 18" text-anchor="middle">{{ G.held[i] }}</text>
              </g>
            </g>
            <text class="lp-no" :x="G.caller[G.held.length - 1].x + G.caller[G.held.length - 1].w / 2" :y="G.caller[G.held.length - 1].y + (G.n ? -6 : 46)" text-anchor="middle">not declared</text>
          </g>

          <g class="lp-shrink">
            <g class="lp-cam">
              <!-- The flow: a name, and a socket per role it declares. -->
              <circle class="lp-halo" :cx="G.card.x + G.card.w / 2" :cy="G.card.y + G.card.h / 2" :r="G.n ? 150 : 130" fill="url(#hmz-loops-glow)" />
              <rect class="lp-card-fill" :x="G.card.x" :y="G.card.y" :width="G.card.w" :height="G.card.h" rx="14" />
              <rect class="lp-card-frame" :x="G.card.x" :y="G.card.y" :width="G.card.w" :height="G.card.h" rx="14" />
              <g class="lp-card-words">
                <text class="lp-name" :x="G.name.x" :y="G.name.y">{{ loop.key }}</text>
              </g>
              <g class="lp-card-words">
                <text class="lp-py" :x="G.n ? G.card.x + G.card.w - 14 : G.name.x" :y="G.n ? G.name.y : G.name.y + 20" :text-anchor="G.n ? 'end' : 'start'">python</text>
              </g>
              <g v-for="(s, i) in G.sockets" :key="`s${i}`" class="lp-slot">
                <text class="lp-cap" :x="s.x + 2" :y="s.y - 7">{{ loop.roles[i].name }}</text>
                <rect class="lp-slot-off" :x="s.x" :y="s.y" :width="s.w" :height="s.h" rx="8" />
                <rect class="lp-slot-on" :x="s.x" :y="s.y" :width="s.w" :height="s.h" rx="8" :style="{ stroke: `var(--hmz-lane-${i + 1})` }" />
              </g>
              <g v-for="(s, i) in G.sockets" :key="`k${i}`" :transform="`translate(${s.x} ${s.y})`">
                <g class="lp-cli">
                  <rect :width="s.w" :height="s.h" rx="8" :style="{ fill: `var(--hmz-lane-${i + 1})` }" />
                  <text class="lp-cli-name" :x="s.w / 2" y="18.5" text-anchor="middle">{{ loop.roles[i].cli }}</text>
                </g>
              </g>

              <!-- The loop: a lane per session, and the flow's code under them. -->
              <g class="lp-loop">
              <path v-for="(d, i) in G.beams" v-show="d" :key="`b${i}`" class="lp-beam" :d="d" :style="{ stroke: tone(loop.lanes[i].role) }" />
              <g v-for="(lane, i) in loop.lanes" :key="`l${i}`" class="lp-lane">
                <text class="lp-lane-name" :x="G.x0" :y="G.laneYs[i] - 8" :style="{ fill: tone(i) }">{{ lane.label }}</text>
                <line class="lp-rail" :x1="G.x0" :x2="G.x1" :y1="G.laneYs[i] + BLOCK_H / 2" :y2="G.laneYs[i] + BLOCK_H / 2" />
              </g>
              <g class="lp-code">
                <text class="lp-lane-name lp-code-name" :x="G.x0" :y="G.codeY - 8">python, between the turns</text>
                <line class="lp-rail lp-code-rail" :x1="G.x0" :x2="G.x1" :y1="G.codeY + 2 + CHIP_H / 2" :y2="G.codeY + 2 + CHIP_H / 2" />
              </g>

              <g v-for="(e, i) in loop.events" :key="`e${which}-${i}`" class="lp-ev">
                <template v-if="e.lane < 0">
                  <g class="lp-pop">
                    <rect class="lp-chip" :x="G.blocks[i].x" :y="G.blocks[i].y" :width="G.blocks[i].w" :height="CHIP_H" rx="13" />
                    <text class="lp-chip-text" :x="G.blocks[i].x + G.blocks[i].w / 2" :y="G.blocks[i].y + 17" text-anchor="middle">{{ e.text }}</text>
                  </g>
                </template>
                <template v-else>
                  <path v-if="G.threads[i]" class="lp-thread" :d="G.threads[i]" :style="{ stroke: tone(e.lane) }" />
                  <circle v-if="e.fresh" class="lp-ring" :cx="G.blocks[i].x" :cy="G.blocks[i].y + BLOCK_H / 2" r="18" :style="{ stroke: tone(e.lane) }" />
                  <rect
                    class="lp-block"
                    :class="{ fresh: e.fresh }"
                    :x="G.blocks[i].x"
                    :y="G.blocks[i].y"
                    :width="G.blocks[i].w"
                    :height="BLOCK_H"
                    rx="8"
                    :style="{ '--tone': tone(e.lane) }"
                  />
                  <text class="lp-block-text" :x="G.blocks[i].x + G.blocks[i].w / 2" :y="G.blocks[i].y + 19.5" text-anchor="middle">{{ e.text }}</text>
                </template>
              </g>
              <g v-for="(e, i) in loop.events" :key="`f${which}-${i}`" :transform="`translate(${G.blocks[i].x + G.blocks[i].w / 2} ${G.blocks[i].y - 16})`" class="lp-field">
                <g v-if="e.field" class="lp-field-in">
                  <rect x="-34" y="-11" width="68" height="22" rx="11" />
                  <text y="4" text-anchor="middle">{{ e.field }}</text>
                </g>
              </g>
              </g>
            </g>
          </g>
        </g>
      </svg>
      <canvas ref="canvas" />
    </HmzStage>
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 22px 0 0;
}

.picker button {
  padding: 4px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}

.picker button:hover {
  color: var(--vp-c-text-1);
}

.picker button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.picker .open {
  margin-left: auto;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  text-decoration: none;
}

.picker .open:hover {
  text-decoration: underline;
}

.hmz-loops > .hmz-stage {
  margin-top: 10px;
}

svg {
  font-family: var(--vp-font-family-base);
}

.lp-halo {
  opacity: calc(var(--hmz-glow) * 0.5);
}

.lp-card-fill {
  fill: var(--hmz-stage-card);
}

.lp-card-frame {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
}

.lp-name {
  font-family: var(--vp-font-family-mono);
  font-size: 15px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.lp-py {
  font-family: var(--vp-font-family-mono);
  font-size: 13.5px;
  fill: var(--hmz-accent);
}

.lp-cap {
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  fill: var(--hmz-stage-dim);
}

.lp-slot-off {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.5;
  stroke-dasharray: 4 3;
}

.lp-slot-on {
  fill: none;
  stroke-width: 2;
}

.lp-cli-name {
  font-family: var(--vp-font-family-mono);
  font-size: 13.5px;
  font-weight: 700;
  fill: #fff;
}

.lp-beam {
  fill: none;
  stroke-width: 1.5;
  stroke-linecap: round;
  opacity: 0.7;
}

.lp-lane-name {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.lp-code-name {
  fill: var(--hmz-stage-dim);
  font-family: var(--vp-font-family-mono);
  letter-spacing: 0;
}

.lp-rail {
  stroke: var(--hmz-stage-line);
  stroke-width: 1.5;
}

.lp-code-rail {
  stroke-dasharray: 2 4;
}

.lp-block {
  fill: color-mix(in srgb, var(--tone) 22%, var(--hmz-stage-card));
  stroke: var(--tone);
  stroke-width: 1.5;
}

.lp-block.fresh {
  stroke-dasharray: 5 3;
}

.lp-block-text {
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.lp-thread {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
}

.lp-ring {
  fill: none;
  stroke-width: 2;
}

.lp-chip {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-accent);
  stroke-width: 1.2;
}

.lp-chip-text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-accent);
}

.lp-field rect {
  fill: var(--hmz-accent);
}

.lp-field text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.lp-frame {
  fill: color-mix(in srgb, var(--hmz-accent-2) 5%, transparent);
  stroke: var(--hmz-accent-2);
  stroke-width: 1.5;
  stroke-dasharray: 6 4;
}

.lp-caller-name {
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  font-weight: 700;
  fill: var(--hmz-accent-2);
}

.lp-call {
  fill: none;
  stroke-width: 2;
  stroke-linecap: round;
}

.lp-held-box {
  fill: var(--hmz-stage-card);
  stroke-width: 1.5;
}

.lp-held-name {
  font-size: 12px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.lp-no {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-lane-5);
}
</style>
