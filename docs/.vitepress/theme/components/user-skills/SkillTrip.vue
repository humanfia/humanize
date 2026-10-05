<script setup lang="ts">
// The two sets of skills an agent carries, and one of the flow's making its trip. Yours are
// where the CLI keeps them, `~/.claude/skills/` and the project's `.claude/skills/`, and every
// agent of that CLI carries them; humanize never changes them. The flow's are in its own
// `skills/` (or fetched from a git repository), for the roles it gives them to: in `rlar` the
// reviewer carries `review-notes` and the actor does not. When the reviewer's session opens,
// the skill is copied into the workspace where Claude Code reads a project's skills; when the
// last session using it ends, the copy goes, with the directories made to hold it. Another
// backend reads another place: `.cursor/skills/`, `.agents/skills/`, or none for `dsh` and
// `pi`. A simulation: the names of "your" two skills are invented.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { createFx, type, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'
import { rig, type Point, type Shot } from '../../motion/camera'
import { brace, braceD, curve, draw, pop, pulse, ring, rise, shake } from '../user-kit/moves'

const BEATS = [
  'Yours: where the CLI keeps skills, carried by every agent of it',
  "The flow's: in its own skills/ or a git repository, for the roles it names",
  "The reviewer's session opens: review-notes is copied into the workspace",
  'The last session using it ends: the copy goes, and what was made to hold it',
  'Another backend reads another place: .cursor, .agents, or none',
]

/** A mono character's advance at 11px. */
const CW = 6.6
const chipW = (text: string) => text.length * CW + 14
const CHIP_H = 19

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  yours: Box
  flows: Box
  actor: Box
  reviewer: Box
  ws: Box
  track: Box & { label: number }
  shots: Record<'yours' | 'flows' | 'mount' | 'ws', Partial<Shot>>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  yours: { x: 16, y: 14, w: 176, h: 116 },
  flows: { x: 16, y: 138, w: 176, h: 116 },
  actor: { x: 218, y: 14, w: 176, h: 116 },
  reviewer: { x: 218, y: 138, w: 176, h: 116 },
  ws: { x: 420, y: 40, w: 204, h: 214 },
  track: { x: 16, y: 264, w: 608, h: 86, label: 96 },
  shots: {
    yours: { x: 221, y: 124, s: 1.45 },
    flows: { x: 221, y: 196, s: 1.45 },
    mount: { x: 320, y: 180, s: 1 },
    ws: { x: 403, y: 150, s: 1.35 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 576,
  yours: { x: 10, y: 12, w: 166, h: 116 },
  flows: { x: 184, y: 12, w: 166, h: 116 },
  actor: { x: 10, y: 136, w: 166, h: 116 },
  reviewer: { x: 184, y: 136, w: 166, h: 116 },
  ws: { x: 10, y: 262, w: 340, h: 208 },
  track: { x: 10, y: 480, w: 340, h: 90, label: 78 },
  shots: {
    yours: { x: 180, y: 130, s: 1.05 },
    flows: { x: 180, y: 130, s: 1.05 },
    mount: { x: 180, y: 288, s: 1 },
    ws: { x: 180, y: 358, s: 1.1 },
  },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

/** Your two skills, and the flow's one. */
const MINE = ['commits', 'pytest']
const FLOWS = 'review-notes'

/** Where a set's chips sit inside a panel or a card: row 0 for yours, row 1 for the flow's. */
const chipAt = (b: Box, row: number, i = 0, top = 50): Point => {
  let x = b.x + 12
  for (let k = 0; k < i; k += 1) x += chipW(MINE[k]) + 6
  return { x, y: b.y + top + row * 26 }
}
const chipMid = (b: Box, row: number, i: number, text: string, top = 50): Point => {
  const p = chipAt(b, row, i, top)
  return { x: p.x + chipW(text) / 2, y: p.y + CHIP_H / 2 }
}

/** The workspace's lines: two of the project's, then the copy and the directories made for it. */
const TREE = [
  { text: 'calc.py', depth: 0, made: false },
  { text: 'TASK.md', depth: 0, made: false },
  { text: '.claude/', depth: 0, made: true },
  { text: 'skills/', depth: 1, made: true },
  { text: 'review-notes/', depth: 2, made: true },
  { text: 'SKILL.md', depth: 3, made: true },
]
const treeX = (depth: number) => L.value.ws.x + 16 + depth * 14
const treeY = (i: number) => L.value.ws.y + 60 + i * 20
/** The brace naming what was made, to the right of the made lines. */
const madeBrace = computed(() => {
  const x = L.value.ws.x + 138
  const top = treeY(2) - 12
  const bottom = treeY(5) + 4
  return { d: braceD({ x, y: bottom }, { x, y: top }, 10), x: x + 14, y: (top + bottom) / 2 + 4 }
})

/** Where each backend's copy lands, and the reviewer's backend chip for it. */
const DEST = [
  { backend: 'claude', who: 'claude', dest: '.claude/skills/' },
  { backend: 'cursor-agent', who: 'cursor-agent', dest: '.cursor/skills/' },
  { backend: 'codex', who: 'codex, agy, …', dest: '.agents/skills/' },
  { backend: 'dsh', who: 'dsh, pi', dest: 'none' },
]
/** From the flow's skill to the reviewer's slot for it: across the gap, or down on a phone. */
const givePath = computed(() => {
  const l = L.value
  if (narrow.value) return `M${l.flows.x + l.flows.w / 2} ${l.flows.y + l.flows.h + 2} V${l.reviewer.y - 2}`
  const from = chipMid(l.flows, 1, 0, FLOWS)
  return curve({ x: from.x + chipW(FLOWS) / 2 + 4, y: from.y - 26 }, { x: chipAt(l.reviewer, 1).x - 4, y: chipMid(l.reviewer, 1, 0, FLOWS).y }, -0.25)
})
const destY = (i: number) => L.value.ws.y + 128 + i * 24
const destTop = computed(() => destY(0) - 30)

/** The sessions on one clock: the actor's kept all run, the reviewer's open for a round. */
const OPEN = 0.36
const CLOSE = 0.74
const trackX = computed(() => L.value.track.x + L.value.track.label)
const trackW = computed(() => L.value.track.w - L.value.track.label - 12)
const rowY = (k: number) => L.value.track.y + (narrow.value ? 30 : 26) + k * (narrow.value ? 22 : 21)

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), far: one('.far'), fx: () => fx, start: l.shots.yours })
    const c = {
      mine: () => palette.lane[0],
      flows: () => palette.accent2,
      ws: () => palette.warm,
    }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(
      q('.panel, .chip, .note, .slot, .no-mark, .card, .git-path, .git-word, .give-path, .tree-line, .strike, .brace-made .brace-path, .brace-made .brace-label, .brace-gone, .track-box, .bar, .guide, .head, .dest-head, .dest-row, .dest-hl, .back, .read-path, .read-word, .lock'),
      { autoAlpha: 0 },
      0,
    )
    tl.set(q('.back-0'), { autoAlpha: 1 }, 0)
    tl.set(q('.bar'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(q('.strike'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    tl.set(one('.dest-hl'), { y: 0 }, 0)

    // 0 · yours: where the CLI keeps them, and every agent of that CLI carries them.
    tl.addLabel('beat-0', 0)
    rise(tl, one('.panel-yours'), 0.1)
    type(tl, one('.yours-path'), '~/.claude/skills/', 0.5)
    pop(tl, q('.panel-yours .chip'), 1.1, { stagger: 0.15 })
    rise(tl, q('.card'), 1.6, { x: -10, y: 0, stagger: 0.15 })
    MINE.forEach((name, i) => {
      const from = chipMid(l.yours, 0, i, name, 60)
      cam.beam(from, chipMid(l.actor, 0, i, name), c.mine, 2.2 + i * 0.2, { duration: 0.7, bend: 0.2, burst: 6 })
      cam.beam(from, chipMid(l.reviewer, 0, i, name), c.mine, 2.3 + i * 0.2, { duration: 0.8, bend: -0.2, burst: 6 })
      pop(tl, one(`.card-actor .mine-${i}`), 2.85 + i * 0.2)
      pop(tl, one(`.card-reviewer .mine-${i}`), 3.0 + i * 0.2)
    })
    rise(tl, one('.note-yours'), 3.6, { y: 6 })
    pop(tl, one('.lock'), 3.8, { from: 0.6 })

    // 1 · the flow's: in its own skills/, or fetched from a git repository, for one role.
    const T1 = 4.8
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.flows, T1, 1.4)
    rise(tl, one('.panel-flows'), T1 + 0.4)
    type(tl, one('.flows-path'), 'rlar/skills/', T1 + 0.8)
    pop(tl, one('.panel-flows .chip'), T1 + 1.3)
    draw(tl, one('.git-path'), T1 + 1.7, { duration: 0.6 })
    rise(tl, one('.git-word'), T1 + 2.0, { y: 6 })
    draw(tl, one('.give-path'), T1 + 2.4, { duration: 0.8 })
    rise(tl, one('.note-give'), T1 + 2.8, { y: 6 })
    tl.to(one('.slot'), { autoAlpha: 1, duration: 0.4 }, T1 + 2.9)
    tl.to(one('.no-mark'), { autoAlpha: 1, duration: 0.4 }, T1 + 3.2)
    shake(tl, one('.no-mark'), T1 + 3.3, 4)

    // 2 · the reviewer's session opens, and the skill is copied into the workspace.
    const T2 = T1 + 4.4
    tl.addLabel('beat-2', T2)
    cam.shot(l.shots.mount, T2, 1.4)
    rise(tl, one('.panel-ws'), T2 + 0.2)
    rise(tl, q('.tree-0, .tree-1'), T2 + 0.5, { y: 6, stagger: 0.1 })
    rise(tl, one('.track-box'), T2 + 0.4, { y: 10 })
    const SW = 6.4
    const sweepAt = T2 + 1.0
    const open = sweepAt + OPEN * SW
    const close = sweepAt + CLOSE * SW
    tl.fromTo(one('.head'), { autoAlpha: 1, x: 0 }, { x: trackW.value, duration: SW, ease: 'none' }, sweepAt)
    tl.set(one('.bar-actor'), { autoAlpha: 1 }, sweepAt)
    tl.to(one('.bar-actor'), { scaleX: 1, duration: SW, ease: 'none' }, sweepAt)
    tl.set(q('.bar-reviewer, .bar-copy'), { autoAlpha: 1 }, open)
    tl.to(q('.bar-reviewer, .bar-copy'), { scaleX: 1, duration: close - open, ease: 'none' }, open)
    ring(tl, one('.reviewer-ring'), open)
    const chipFrom = chipMid(l.flows, 0, 0, FLOWS)
    cam.beam(chipFrom, { x: treeX(2) + 20, y: treeY(2) - 4 }, c.flows, open + 0.05, { duration: 0.8, bend: -0.18, burst: 10 })
    TREE.forEach((line, i) => {
      if (!line.made) return
      rise(tl, one(`.tree-${i}`), open + 0.55 + (i - 2) * 0.16, { x: -8, y: 0 })
    })
    brace(tl, q, '.brace-made', open + 1.2)
    cam.beam({ x: treeX(3) + 30, y: treeY(5) - 4 }, chipMid(l.reviewer, 1, 0, FLOWS), c.flows, open + 1.4, { duration: 0.7, bend: 0.2, burst: 8 })
    pop(tl, one('.flows-carried'), open + 2.0)
    draw(tl, one('.read-path'), open + 2.05, { duration: 0.5 })
    rise(tl, one('.read-word'), open + 2.2, { y: 4 })

    // 3 · the session ends: the copy goes, deepest first, and the directories made for it.
    const T3 = close - 0.25
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.ws, T3, 1.2)
    tl.to(q('.read-path, .read-word'), { autoAlpha: 0, duration: 0.3 }, close)
    ;[5, 4, 3, 2].forEach((i, k) => {
      const at = close + 0.2 + k * 0.28
      tl.set(one(`.strike-${i}`), { autoAlpha: 1 }, at)
      tl.to(one(`.strike-${i}`), { scaleX: 1, duration: 0.25, ease: 'cine.out' }, at)
      tl.to(q(`.tree-${i}, .strike-${i}`), { autoAlpha: 0, x: 8, duration: 0.35, ease: 'cine.in' }, at + 0.3)
    })
    tl.to(q('.brace-made .brace-label'), { autoAlpha: 0, duration: 0.25 }, close + 0.5)
    rise(tl, one('.brace-gone'), close + 0.6, { y: 4 })
    tl.to(q('.brace-made .brace-path, .brace-gone'), { autoAlpha: 0, duration: 0.4 }, close + 1.9)
    tl.to(one('.flows-carried'), { autoAlpha: 0, scale: 0.6, duration: 0.4, ease: 'cine.in' }, close + 0.3)
    pulse(tl, q('.tree-0, .tree-1'), close + 1.5)
    draw(tl, q('.guide'), close + 0.4, { duration: 0.5, stagger: 0.12 })
    tl.to(one('.head'), { autoAlpha: 0, duration: 0.3 }, sweepAt + SW)

    // 4 · another backend in the reviewer's role reads its skills from another place.
    const T4 = Math.max(close + 2.3, sweepAt + SW + 0.2)
    tl.addLabel('beat-4', T4)
    rise(tl, one('.dest-head'), T4 + 0.2, { y: 6 })
    rise(tl, q('.dest-row'), T4 + 0.4, { y: 6, stagger: 0.12 })
    tl.to(one('.dest-hl'), { autoAlpha: 1, duration: 0.3 }, T4 + 1.0)
    DEST.forEach((d, i) => {
      const at = T4 + 1.0 + i * 1.1
      if (i > 0) {
        tl.to(q(`.back-${i - 1}`), { autoAlpha: 0, duration: 0.25 }, at)
        tl.to(one(`.back-${i}`), { autoAlpha: 1, duration: 0.25 }, at + 0.1)
        tl.to(one('.dest-hl'), { y: destY(i) - destY(0), duration: 0.5, ease: 'cine' }, at)
      }
      if (d.dest === 'none') shake(tl, one(`.dest-row-${i} .dest-place`), at + 0.4, 5)
      else cam.beam(chipFrom, { x: l.ws.x + (narrow.value ? 160 : 140), y: destY(i) - 4 }, c.flows, at + 0.15, { duration: 0.6, bend: 0.15, burst: 6 })
    })
    const back = T4 + 1.0 + DEST.length * 1.1
    tl.to(q(`.back-${DEST.length - 1}`), { autoAlpha: 0, duration: 0.25 }, back)
    tl.to(one('.back-0'), { autoAlpha: 1, duration: 0.25 }, back + 0.1)
    tl.to(one('.dest-hl'), { y: 0, duration: 0.5, ease: 'cine' }, back)
    cam.shot({ x: l.w / 2, y: l.h / 2, s: 1 }, back, 1.4)
    tl.addLabel('rest', back + 1.5)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, back + 5)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="5 / 8"
    label="The two sets of skills an agent carries. Yours are where the CLI keeps them, such as ~/.claude/skills/ and the project's .claude/skills/ for Claude Code, and every agent of that CLI carries them; humanize never changes them. The flow's are in the flow's own skills/ directory or fetched from a git repository, for the roles the flow gives them to: in rlar the reviewer carries review-notes and the actor does not. When the reviewer's session opens, review-notes/SKILL.md is copied into the workspace at .claude/skills/, making the .claude and skills directories to hold it. When the last session using it ends, the copy goes, and so do the directories that were made for it; the project's own files stay. Another backend in the role gets the copy elsewhere: cursor-agent in .cursor/skills/, codex, agy and the rest in .agents/skills/, and dsh and pi get none, carrying only what you installed."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern id="st-dots" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" class="grid-dot" />
        </pattern>
      </defs>
      <g class="far"><rect x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" fill="url(#st-dots)" /></g>

      <g class="world">
        <!-- Yours: where the CLI keeps them. -->
        <g class="panel panel-yours">
          <rect class="box box-mine" :x="L.yours.x" :y="L.yours.y" :width="L.yours.w" :height="L.yours.h" rx="10" />
          <text class="title" :x="L.yours.x + 12" :y="L.yours.y + 20">yours</text>
          <text class="path yours-path" :x="L.yours.x + 12" :y="L.yours.y + 37">~/.claude/skills/</text>
          <text class="path" :x="L.yours.x + 12" :y="L.yours.y + 52">.claude/skills/</text>
          <text class="carries" :x="L.yours.x + 12 + 16 * CW" :y="L.yours.y + 52">(none)</text>
          <g v-for="(name, i) in MINE" :key="name" class="chip chip-mine">
            <rect :x="chipAt(L.yours, 0, i, 60).x" :y="chipAt(L.yours, 0, i, 60).y" :width="chipW(name)" :height="CHIP_H" rx="5" />
            <text :x="chipAt(L.yours, 0, i, 60).x + 7" :y="chipAt(L.yours, 0, i, 60).y + 13">{{ name }}</text>
          </g>
          <g class="note note-yours">
            <text class="note-text" :x="L.yours.x + 26" :y="L.yours.y + 101">untouched by humanize</text>
          </g>
          <g class="lock">
            <rect class="lock-body" :x="L.yours.x + 12" :y="L.yours.y + 96" width="8" height="7" rx="1.5" />
            <path class="lock-loop" :d="`M${L.yours.x + 13.5} ${L.yours.y + 96} v-2.5 a2.5 2.5 0 0 1 5 0 v2.5`" />
          </g>
        </g>

        <!-- The flow's: in its own skills/, or fetched from a git repository. -->
        <g class="panel panel-flows">
          <rect class="box box-flows" :x="L.flows.x" :y="L.flows.y" :width="L.flows.w" :height="L.flows.h" rx="10" />
          <text class="title" :x="L.flows.x + 12" :y="L.flows.y + 20">the flow's</text>
          <text class="path flows-path" :x="L.flows.x + 12" :y="L.flows.y + 38">rlar/skills/</text>
          <g class="chip chip-flows">
            <rect :x="chipAt(L.flows, 1).x" :y="chipAt(L.flows, 1).y - 26" :width="chipW(FLOWS)" :height="CHIP_H" rx="5" />
            <text :x="chipAt(L.flows, 1).x + 7" :y="chipAt(L.flows, 1).y - 13">{{ FLOWS }}</text>
          </g>
        </g>
        <path class="git-path" :d="`M${L.flows.x + 16} ${L.flows.y + 104} V${L.flows.y + 84} M${L.flows.x + 16} ${L.flows.y + 98} q0 -6 7 -8`" />
        <g class="git-word">
          <circle class="git-dot" :cx="L.flows.x + 16" :cy="L.flows.y + 84" r="2.4" />
          <circle class="git-dot" :cx="L.flows.x + 16" :cy="L.flows.y + 104" r="2.4" />
          <circle class="git-dot" :cx="L.flows.x + 24" :cy="L.flows.y + 89" r="2.4" />
          <text class="note-text" :x="L.flows.x + 34" :y="L.flows.y + 92">or fetched</text>
          <text class="note-text" :x="L.flows.x + 34" :y="L.flows.y + 106">from a git repo</text>
        </g>

        <!-- The two agents, both Claude Code, and what each carries. -->
        <g v-for="who in ['actor', 'reviewer']" :key="who" class="card" :class="`card-${who}`">
          <rect class="box box-card" :x="(who === 'actor' ? L.actor : L.reviewer).x" :y="(who === 'actor' ? L.actor : L.reviewer).y" :width="(who === 'actor' ? L.actor : L.reviewer).w" :height="(who === 'actor' ? L.actor : L.reviewer).h" rx="10" />
          <text class="title" :x="(who === 'actor' ? L.actor : L.reviewer).x + 12" :y="(who === 'actor' ? L.actor : L.reviewer).y + 20">{{ who }}</text>
          <text class="carries" :x="(who === 'actor' ? L.actor : L.reviewer).x + 12" :y="(who === 'actor' ? L.actor : L.reviewer).y + 40">carries</text>
          <g v-for="(name, i) in MINE" :key="name" class="chip chip-mine" :class="`mine-${i}`">
            <rect :x="chipAt(who === 'actor' ? L.actor : L.reviewer, 0, i).x" :y="chipAt(who === 'actor' ? L.actor : L.reviewer, 0, i).y" :width="chipW(name)" :height="CHIP_H" rx="5" />
            <text :x="chipAt(who === 'actor' ? L.actor : L.reviewer, 0, i).x + 7" :y="chipAt(who === 'actor' ? L.actor : L.reviewer, 0, i).y + 13">{{ name }}</text>
          </g>
        </g>
        <!-- The actor's backend, and the reviewer's, which beat 4 changes. -->
        <g class="card card-actor-back">
          <rect class="back-bg" :x="L.actor.x + L.actor.w - 12 - chipW('claude')" :y="L.actor.y + 7" :width="chipW('claude')" height="18" rx="9" />
          <text class="back-text" :x="L.actor.x + L.actor.w - 12 - chipW('claude') / 2" :y="L.actor.y + 20" text-anchor="middle">claude</text>
        </g>
        <g v-for="(d, i) in DEST" :key="d.backend" class="back" :class="`back-${i}`">
          <g class="card">
            <rect class="back-bg" :x="L.reviewer.x + L.reviewer.w - 12 - chipW(d.backend)" :y="L.reviewer.y + 7" :width="chipW(d.backend)" height="18" rx="9" />
            <text class="back-text" :x="L.reviewer.x + L.reviewer.w - 12 - chipW(d.backend) / 2" :y="L.reviewer.y + 20" text-anchor="middle">{{ d.backend }}</text>
          </g>
        </g>
        <g :transform="`translate(${L.reviewer.x + L.reviewer.w / 2} ${L.reviewer.y + L.reviewer.h / 2})`">
          <rect class="reviewer-ring" :x="-L.reviewer.w / 2" :y="-L.reviewer.h / 2" :width="L.reviewer.w" :height="L.reviewer.h" rx="10" />
        </g>
        <!-- The flow's skill: given to the reviewer, not to the actor. -->
        <path class="give-path" :d="givePath" />
        <g class="slot">
          <rect class="slot-box" :x="chipAt(L.reviewer, 1).x" :y="chipAt(L.reviewer, 1).y" :width="chipW(FLOWS)" :height="CHIP_H" rx="5" />
          <text class="slot-text" :x="chipAt(L.reviewer, 1).x + 7" :y="chipAt(L.reviewer, 1).y + 13">{{ FLOWS }}</text>
        </g>
        <g class="reviewer-flows">
          <g class="chip chip-flows flows-carried">
            <rect :x="chipAt(L.reviewer, 1).x" :y="chipAt(L.reviewer, 1).y" :width="chipW(FLOWS)" :height="CHIP_H" rx="5" />
            <text :x="chipAt(L.reviewer, 1).x + 7" :y="chipAt(L.reviewer, 1).y + 13">{{ FLOWS }}</text>
          </g>
        </g>
        <g class="note note-give">
          <text class="note-text" :x="L.reviewer.x + 12" :y="L.reviewer.y + L.reviewer.h - 6">the flow gives it to this role</text>
        </g>
        <g class="no-mark">
          <rect class="no-box" :x="chipAt(L.actor, 1).x" :y="chipAt(L.actor, 1).y" :width="chipW(FLOWS)" :height="CHIP_H" rx="5" />
          <text class="no-text" :x="chipAt(L.actor, 1).x + 7" :y="chipAt(L.actor, 1).y + 13">{{ FLOWS }}</text>
          <line class="no-line" :x1="chipAt(L.actor, 1).x + 4" :x2="chipAt(L.actor, 1).x + chipW(FLOWS) - 4" :y1="chipAt(L.actor, 1).y + CHIP_H / 2" :y2="chipAt(L.actor, 1).y + CHIP_H / 2" />
          <text class="note-text" :x="L.actor.x + 12" :y="L.actor.y + L.actor.h - 6">not given to the actor</text>
        </g>

        <!-- The workspace, where Claude Code reads a project's own skills. -->
        <g class="panel panel-ws">
          <path class="box box-ws" :d="`M${L.ws.x} ${L.ws.y + 6} q0 -6 6 -6 h70 l8 6 h${L.ws.w - 90} q6 0 6 6 v${L.ws.h - 12} q0 6 -6 6 h${-(L.ws.w - 12)} q-6 0 -6 -6 z`" />
          <text class="title" :x="L.ws.x + 12" :y="L.ws.y + 24">workspace</text>
          <text class="path" :x="L.ws.x + 12" :y="L.ws.y + 40">/tmp/skills-demo</text>
        </g>
        <g v-for="(line, i) in TREE" :key="line.text" class="tree-line" :class="[`tree-${i}`, { made: line.made }]">
          <text class="tree-text" :x="treeX(line.depth)" :y="treeY(i)">{{ line.text }}</text>
        </g>
        <line
          v-for="i in [2, 3, 4, 5]"
          :key="`s${i}`"
          class="strike"
          :class="`strike-${i}`"
          :x1="treeX(TREE[i].depth) - 2"
          :x2="treeX(TREE[i].depth) + TREE[i].text.length * CW + 2"
          :y1="treeY(i) - 4"
          :y2="treeY(i) - 4"
        />
        <g class="brace-made">
          <path class="brace-path" :d="madeBrace.d" />
          <g class="brace-label">
            <text class="brace-word" :x="madeBrace.x" :y="madeBrace.y - 7">made</text>
            <text class="brace-word" :x="madeBrace.x" :y="madeBrace.y + 8">for it</text>
          </g>
        </g>
        <g class="brace-gone">
          <text class="brace-word gone" :x="madeBrace.x" :y="madeBrace.y - 7">gone,</text>
          <text class="brace-word gone" :x="madeBrace.x" :y="madeBrace.y + 8">all of it</text>
        </g>
        <path class="read-path" :d="curve({ x: treeX(3) + 4, y: treeY(5) + 6 }, { x: chipAt(L.reviewer, 1).x + chipW(FLOWS) + 2, y: chipMid(L.reviewer, 1, 0, FLOWS).y }, narrow ? -0.2 : 0.2)" />
        <g class="read-word">
          <text class="read-text" :x="narrow ? treeX(0) + 170 : L.ws.x + 16" :y="narrow ? treeY(5) : L.ws.y + L.ws.h - 12">the reviewer reads it</text>
        </g>

        <!-- Where each backend's copy goes. -->
        <g class="dest-head"><text class="carries" :x="L.ws.x + 16" :y="destTop">the copy goes into</text></g>
        <rect class="dest-hl" :x="L.ws.x + 8" :y="destY(0) - 16" :width="L.ws.w - 16" height="22" rx="5" />
        <g v-for="(d, i) in DEST" :key="d.backend" class="dest-row" :class="`dest-row-${i}`">
          <text class="dest-who" :x="L.ws.x + 16" :y="destY(i)">{{ d.who }}</text>
          <g class="dest-place">
            <text class="dest-text" :class="{ none: d.dest === 'none' }" :x="L.ws.x + (narrow ? 150 : 92)" :y="destY(i)">{{ d.dest }}</text>
          </g>
        </g>

        <!-- One clock: the sessions, and how long the copy lives. -->
        <g class="track-box">
          <rect class="box box-track" :x="L.track.x" :y="L.track.y" :width="L.track.w" :height="L.track.h" rx="10" />
          <text class="carries" :x="L.track.x + 12" :y="L.track.y + 14">sessions, on one clock</text>
          <g v-for="(name, k) in ['actor', 'reviewer', 'the copy']" :key="name">
            <text class="row-name" :x="L.track.x + 12" :y="rowY(k) + 10">{{ name }}</text>
            <rect class="lane" :x="trackX" :y="rowY(k)" :width="trackW" height="12" rx="3" />
          </g>
        </g>
        <rect class="bar bar-actor" :x="trackX" :y="rowY(0)" :width="trackW" height="12" rx="3" />
        <rect class="bar bar-reviewer" :x="trackX + OPEN * trackW" :y="rowY(1)" :width="(CLOSE - OPEN) * trackW" height="12" rx="3" />
        <rect class="bar bar-copy" :x="trackX + OPEN * trackW" :y="rowY(2)" :width="(CLOSE - OPEN) * trackW" height="12" rx="3" />
        <path v-for="f in [OPEN, CLOSE]" :key="f" class="guide" :d="`M${trackX + f * trackW} ${rowY(1) - 2} V${rowY(2) + 14}`" />
        <line class="head" :x1="trackX" :x2="trackX" :y1="rowY(0) - 4" :y2="rowY(2) + 16" />
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.grid-dot {
  fill: var(--hmz-stage-line);
}

.box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.box-mine {
  stroke: color-mix(in srgb, var(--hmz-lane-1) 55%, transparent);
}

.box-flows {
  stroke: color-mix(in srgb, var(--hmz-accent-2) 55%, transparent);
}

.box-ws {
  fill: color-mix(in srgb, var(--hmz-warm) 7%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
  stroke-width: 1.4;
}

.title {
  font-size: 13px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.path,
.tree-text,
.dest-text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.tree-line.made .tree-text {
  fill: var(--hmz-accent-2);
  font-weight: 700;
}

.carries,
.row-name,
.dest-who {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.dest-text {
  fill: var(--hmz-stage-ink);
}

.dest-text.none {
  font-family: var(--vp-font-family-base);
  font-weight: 700;
  fill: var(--hmz-lane-5);
}

.dest-hl {
  fill: color-mix(in srgb, var(--hmz-accent-2) 14%, transparent);
  stroke: var(--hmz-accent-2);
  stroke-width: 1;
}

.note-text {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.chip rect {
  stroke-width: 1.3;
}

.chip text,
.slot-text,
.no-text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
}

.chip-mine rect {
  fill: color-mix(in srgb, var(--hmz-lane-1) 14%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-1);
}

.chip-mine text {
  fill: var(--hmz-stage-ink);
}

.chip-flows rect {
  fill: var(--hmz-accent-2);
  stroke: var(--hmz-accent-2);
}

.chip-flows text {
  font-weight: 700;
  fill: #fff;
}

.slot-box,
.no-box {
  fill: none;
  stroke: var(--hmz-accent-2);
  stroke-width: 1.2;
  stroke-dasharray: 3 3;
}

.slot-text {
  fill: var(--hmz-accent-2);
}

.no-box {
  stroke: var(--hmz-stage-dim);
}

.no-text {
  fill: var(--hmz-stage-dim);
}

.no-line {
  stroke: var(--hmz-lane-5);
  stroke-width: 1.6;
}

.back-bg {
  fill: color-mix(in srgb, var(--hmz-stage-ink) 8%, transparent);
  stroke: var(--hmz-stage-line);
}

.back-text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.reviewer-ring {
  fill: none;
  stroke: var(--hmz-accent-2);
  stroke-width: 2;
}

.lock-body {
  fill: var(--hmz-lane-1);
}

.lock-loop {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.4;
}

.git-path,
.give-path,
.read-path,
.guide {
  fill: none;
  stroke: var(--hmz-accent-2);
  stroke-width: 1.3;
  stroke-dasharray: 4 4;
}

.git-path {
  stroke-dasharray: none;
  stroke-width: 1.6;
  stroke-linecap: round;
}

.git-dot {
  fill: var(--hmz-accent-2);
}

.guide {
  stroke: var(--hmz-stage-dim);
  stroke-dasharray: 2 3;
}

.strike {
  stroke: var(--hmz-lane-5);
  stroke-width: 1.6;
}

.brace-path {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.4;
  stroke-linecap: round;
}

.brace-word,
.read-text {
  font-size: 12px;
  font-style: italic;
  fill: var(--hmz-accent-2);
}

.brace-word.gone {
  fill: var(--hmz-lane-5);
}

.lane {
  fill: var(--hmz-stage-line);
  opacity: 0.6;
}

.bar-actor {
  fill: var(--hmz-lane-1);
}

.bar-reviewer {
  fill: var(--hmz-accent-2);
}

.bar-copy {
  fill: var(--hmz-warm);
}

.head {
  stroke: var(--hmz-warm);
  stroke-width: 2;
}
</style>
