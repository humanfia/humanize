<script setup lang="ts">
// One run, start to finish, for the page at the site's root: what "a flow drives coding agents
// turn after turn" comes to on the screen. The flow is `rlar`, the review loop that ships in
// `hmz/flows/builtin/rlar/`, and the scene holds to what its code does:
//
// - Its two roles, `actor` and `reviewer`, are filled with `-a role=CLI/MODEL:EFFORT`.
// - The actor works in one session, kept for the whole run, in the workspace the run was
//   started in.
// - Each round the reviewer opens a fresh session, reads the repository, and answers in the
//   shape the flow asks for (`Review`: `done`, `notes`).
// - Not done: the notes are the actor's next prompt, in the same session. Done: the run ends
//   on the notes.
// - Every turn is in the run's trace, with what it cost.
//
// A simulation: the edits, the notes and the spend are invented.
//
// Words are only ever faded here, never moved: the stage lifts small words on a narrow screen
// with a CSS `scale`, which a GSAP transform on the same <text> would compound.
import { computed, ref, useId } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { createFx, cssVar, fly, type, type Fx } from '../../motion/fx'
import { rig, type Point, type Shot } from '../../motion/camera'
import { useNarrow } from '../../motion/layout'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'rlar has two roles; -a fills each with an agent',
  'The actor takes a turn in its session, in your directory',
  'A fresh reviewer reads the work and answers: done, and notes',
  'Not done: the notes are the next prompt, same session',
  'Done: the run ends, and every turn is in the trace',
]

const ACTOR = 'claude/claude-opus-5:high'
const REVIEWER = 'codex/gpt-5.6-sol:high'
const COMMAND = `hmz exec -f rlar -a actor=${ACTOR} -a reviewer=${REVIEWER}`

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  /** The command line typed at the top, or none where there is no room for it. */
  command?: Point
  flow: Box
  /** Where each role's name and slot are, inside the flow card. */
  roles: { label: Point; slot: Box }[]
  /** The actor's session: its label, and its turns along a rail. */
  session: { label: Point; y: number; x0: number; x1: number; tile: (i: number) => Box }
  env: Box
  reviewer: Box
  /** The notes, carried back up to the next turn: one cubic, from the reviewer to the tile. */
  loop: string
  trace: { label: Point; y: number; x0: number; x1: number; tally: Point }
  shots: Record<'open' | 'work' | 'read' | 'again' | 'home', Partial<Shot>>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  command: { x: 24, y: 24 },
  flow: { x: 24, y: 44, w: 200, h: 150 },
  roles: [
    { label: { x: 38, y: 92 }, slot: { x: 36, y: 99, w: 176, h: 24 } },
    { label: { x: 38, y: 146 }, slot: { x: 36, y: 153, w: 176, h: 24 } },
  ],
  session: {
    label: { x: 240, y: 60 },
    y: 86,
    x0: 240,
    x1: 616,
    tile: (i) => ({ x: 240 + i * 96, y: 70, w: 88, h: 32 }),
  },
  env: { x: 240, y: 136, w: 224, h: 142 },
  reviewer: { x: 484, y: 136, w: 132, h: 142 },
  loop: 'M 600 136 C 600 104, 420 122, 384 104',
  trace: { label: { x: 24, y: 317 }, y: 306, x0: 86, x1: 616, tally: { x: 616, y: 293 } },
  shots: {
    open: { x: 220, y: 110, s: 1.45 },
    work: { x: 360, y: 170, s: 1.3 },
    read: { x: 450, y: 196, s: 1.4 },
    again: { x: 410, y: 186, s: 1.15 },
    home: { x: 320, y: 176, s: 1 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 520,
  flow: { x: 16, y: 16, w: 328, h: 112 },
  roles: [
    { label: { x: 28, y: 76 }, slot: { x: 106, y: 61, w: 226, h: 22 } },
    { label: { x: 28, y: 110 }, slot: { x: 106, y: 95, w: 226, h: 22 } },
  ],
  session: {
    label: { x: 16, y: 160 },
    y: 186,
    x0: 16,
    x1: 344,
    tile: (i) => ({ x: 16 + i * 112, y: 170, w: 104, h: 32 }),
  },
  env: { x: 16, y: 252, w: 200, h: 142 },
  reviewer: { x: 226, y: 252, w: 118, h: 142 },
  loop: 'M 330 252 C 330 226, 220 232, 184 202',
  trace: { label: { x: 16, y: 424 }, y: 432, x0: 16, x1: 344, tally: { x: 344, y: 494 } },
  shots: {
    open: { x: 180, y: 80, s: 1.1 },
    work: { x: 180, y: 250, s: 1.05 },
    read: { x: 250, y: 300, s: 1.25 },
    again: { x: 180, y: 260, s: 1 },
    home: { x: 180, y: 260, s: 1 },
  },
}

/** The run's turns, in order, as the trace draws them: whose, and how long, as fractions. */
const TURNS = [
  { who: 'actor', from: 0, to: 0.3 },
  { who: 'reviewer', from: 0.32, to: 0.52 },
  { who: 'actor', from: 0.54, to: 0.78 },
  { who: 'reviewer', from: 0.8, to: 0.98 },
]

const id = useId()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const centre = (b: Box): Point => ({ x: b.x + b.w / 2, y: b.y + b.h / 2 })

/** The same cubic run the other way, so the words set along it read left to right. */
const backwards = (d: string) => {
  const [a, b, c, e] = d.replace(/[MC,]/g, ' ').trim().split(/\s+/).reduce<string[][]>((all, n, i) => (i % 2 ? all[all.length - 1].push(n) : all.push([n]), all), [])
  return `M ${e.join(' ')} C ${c.join(' ')}, ${b.join(' ')}, ${a.join(' ')}`
}

const scene = useScene({
  still: 'rest',
  repeatDelay: 1.2,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const one = (sel: string) => q(sel)[0]
    const root = one('.world')
    const ink = () => cssVar(root, '--hmz-ink')
    const red = () => cssVar(root, '--hmz-red')
    const cam = rig(tl, { w: l.w, h: l.h, world: root, far: one('.far'), fx: () => fx, start: l.shots.open })
    const tile = (i: number) => l.session.tile(i)
    const slot = (i: number) => l.roles[i].slot

    // A clean slate every loop.
    tl.set(at('.chip, .tile, .packet, .diff, .card, .stamp, .fresh, .loop-label, .bar, .bar-word, .tally, .glow, .cmd-done'), { autoAlpha: 0 }, 0)
    tl.set(at('.rail, .loop-line, .read-line, .read-line-2, .axis'), { drawSVG: '0%' }, 0)
    tl.set(at('.flow, .env, .reviewer, .session-label'), { autoAlpha: 1 }, 0)
    tl.set(at('.bar'), { scaleX: 0, transformOrigin: '0% 50%' }, 0)
    if (l.command) tl.set(one('.cmd'), { text: '' }, 0)

    // 0 · the roles, and the agents -a fills them with.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.flow'), { autoAlpha: 0, x: -14 }, { autoAlpha: 1, x: 0, duration: 0.6 }, 0.1)
    if (l.command) type(tl, one('.cmd'), COMMAND, 0.4, 70)
    const T0 = l.command ? 0.4 + COMMAND.length / 70 : 0.6
    ;[0, 1].forEach((i) => {
      const t = T0 + 0.1 + i * 0.7
      const s = slot(i)
      const from = l.command ? { x: l.command.x + (i ? 360 : 140) - s.x, y: l.command.y - s.y - 4 } : { x: 60, y: -40 }
      tl.fromTo(one(`.chip-${i}`), { autoAlpha: 0, x: from.x, y: from.y, scale: 0.9 }, { autoAlpha: 1, x: 0, y: 0, scale: 1, duration: 0.7, ease: 'cine' }, t)
      cam.flare(centre(s), i ? red : ink, t + 0.7, 16, 70)
      tl.fromTo(one(`.slot-${i}`), { autoAlpha: 1 }, { autoAlpha: 0, duration: 0.2 }, t + 0.65)
    })

    // 1 · the actor's turn: one session, its first prompt the task, worked in your directory.
    const T1 = T0 + 1.8
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.work, T1, 1.4)
    tl.to(one('.rail'), { drawSVG: '100%', duration: 0.9, ease: 'cine' }, T1 + 0.2)
    tl.fromTo(one('.tile-0'), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(2.5)' }, T1 + 0.7)
    cam.beam(centre(slot(0)), centre(tile(0)), ink, T1 + 0.3, { duration: 0.6, bend: 0.18, burst: 10 })
    fly(tl, one('.packet'), one('.drop') as SVGPathElement, T1 + 1.2, { duration: 0.8, fx: () => fx, color: ink() })
    tl.fromTo(one('.env .glow'), { autoAlpha: 0.9 }, { autoAlpha: 0, duration: 0.9, ease: 'power2.out' }, T1 + 2.0)
    tl.fromTo(at('.diff-0'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.35, stagger: 0.35 }, T1 + 2.1)

    // 2 · a fresh reviewer reads what is there, and answers in the flow's shape.
    const T2 = T1 + 3.2
    tl.addLabel('beat-2', T2)
    cam.shot(l.shots.read, T2, 1.3)
    tl.fromTo(one('.fresh-0'), { autoAlpha: 0, scale: 1.4, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, T2 + 0.4)
    tl.to(one('.read-line'), { drawSVG: '100%', duration: 0.7, ease: 'cine' }, T2 + 0.7)
    cam.beam(centre(l.env), centre(l.reviewer), red, T2 + 0.8, { duration: 0.8, bend: -0.25, burst: 12 })
    tl.fromTo(one('.card-0'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.5 }, T2 + 1.5)
    tl.fromTo(at('.card-0 .field'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3, stagger: 0.3 }, T2 + 1.7)

    // 3 · not done: the notes go back up as the actor's next prompt, in the same session; it
    // works again, and another fresh reviewer reads again.
    const T3 = T2 + 3.0
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.again, T3, 1.3)
    tl.to(one('.loop-line'), { drawSVG: '100%', duration: 0.9, ease: 'cine' }, T3 + 0.2)
    tl.fromTo(one('.loop-label'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4 }, T3 + 0.6)
    fly(tl, one('.note-packet'), one('.loop-line') as SVGPathElement, T3 + 0.3, { duration: 0.9, fx: () => fx, color: red() })
    tl.fromTo(one('.tile-1'), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(2.5)' }, T3 + 1.15)
    tl.fromTo(one('.rail-pulse'), { autoAlpha: 0.9, scaleX: 0, transformOrigin: '0% 50%' }, { autoAlpha: 0, scaleX: 1, duration: 0.9, ease: 'power2.out' }, T3 + 1.2)
    fly(tl, one('.packet-2'), one('.drop-2') as SVGPathElement, T3 + 1.5, { duration: 0.7, fx: () => fx, color: ink() })
    tl.fromTo(one('.env .glow'), { autoAlpha: 0.9 }, { autoAlpha: 0, duration: 0.9, ease: 'power2.out' }, T3 + 2.2)
    tl.fromTo(at('.diff-1'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.35, stagger: 0.3 }, T3 + 2.3)
    tl.to(one('.card-0'), { autoAlpha: 0, x: 18, duration: 0.4, ease: 'cine.in' }, T3 + 2.6)
    tl.to(one('.fresh-0'), { autoAlpha: 0, duration: 0.2 }, T3 + 2.6)
    tl.fromTo(one('.fresh-1'), { autoAlpha: 0, scale: 1.4, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, T3 + 2.9)
    cam.beam(centre(l.env), centre(l.reviewer), red, T3 + 3.1, { duration: 0.7, bend: -0.25, burst: 12 })

    // 4 · done: the stamp, the end, and the run's trace drawn turn by turn.
    const T4 = T3 + 3.9
    tl.addLabel('beat-4', T4)
    tl.fromTo(one('.card-1'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.5 }, T4)
    tl.fromTo(at('.card-1 .field'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3, stagger: 0.25 }, T4 + 0.2)
    tl.fromTo(one('.stamp'), { autoAlpha: 0, scale: 2.2, rotation: -24, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, rotation: -12, duration: 0.45, ease: 'back.out(1.6)' }, T4 + 0.8)
    cam.flare(centre(l.reviewer), red, T4 + 1.05, 30, 130)
    cam.shot(l.shots.home, T4 + 1.2, 1.5)
    tl.to(one('.axis'), { drawSVG: '100%', duration: 0.8, ease: 'cine' }, T4 + 1.6)
    at('.bar').forEach((bar, i) => {
      const t = T4 + 1.9 + i * 0.35
      tl.to(bar, { autoAlpha: 1, scaleX: 1, duration: 0.5, ease: 'cine' }, t)
      tl.to(at('.bar-word')[i] ?? [], { autoAlpha: 1, duration: 0.3 }, t + 0.25)
    })
    tl.fromTo(one('.tally'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4 }, T4 + 3.4)
    tl.addLabel('rest', T4 + 3.9)
    tl.to(root, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T4 + 6.6)
    tl.set(root, { autoAlpha: 1 }, T4 + 7.3)
  },
})

/** Where a turn of the trace starts and how wide it is. */
const span = (t: (typeof TURNS)[number]) => {
  const { x0, x1 } = L.value.trace
  return { x: x0 + t.from * (x1 - x0), w: (t.to - t.from) * (x1 - x0) }
}
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="2 / 3"
    label="One run of rlar, the review loop that ships with humanize. Its two roles, actor and reviewer, are filled with -a: Claude Code for the actor, Codex for the reviewer. The actor takes its first turn in one session, with the task as its prompt, and edits calc.py in your directory. A reviewer, in a fresh session, reads the repository and answers in the flow's shape: done false, with notes asking for a test. The notes are the actor's next prompt, in the same session; it adds the test. Another fresh reviewer reads it and answers done true, and the run ends. The run's trace shows its four turns, two by each agent, and what they cost."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="far">
        <line v-for="k in 30" :key="`g${k}`" class="rule" :x1="-300 + k * 48" :x2="-300 + k * 48" y1="-300" :y2="L.h + 300" />
        <line v-for="k in 24" :key="`h${k}`" class="rule" :y1="-300 + k * 48" :y2="-300 + k * 48" x1="-300" :x2="L.w + 300" />
      </g>

      <g class="world">
        <!-- The command that fills the roles. -->
        <text v-if="L.command" class="cmd" :x="L.command.x" :y="L.command.y">{{ COMMAND }}</text>

        <!-- The flow: its name, and its two roles with a slot each. -->
        <g class="flow">
          <rect class="card-box flow-box" :x="L.flow.x" :y="L.flow.y" :width="L.flow.w" :height="L.flow.h" />
          <rect class="flow-bar" :x="L.flow.x" :y="L.flow.y" :width="L.flow.w" height="4" />
          <text class="kicker" :x="L.flow.x + 14" :y="L.flow.y + 26">flow</text>
          <text class="flow-name" :x="L.flow.x + 54" :y="L.flow.y + 27">rlar</text>
          <g v-for="(role, i) in L.roles" :key="i">
            <text class="role" :x="role.label.x" :y="role.label.y">{{ i ? 'reviewer' : 'actor' }}</text>
            <rect class="slot" :class="`slot-${i}`" :x="role.slot.x" :y="role.slot.y" :width="role.slot.w" :height="role.slot.h" />
            <g class="chip" :class="[`chip-${i}`, i ? 'hot' : '']">
              <rect :x="role.slot.x" :y="role.slot.y" :width="role.slot.w" :height="role.slot.h" />
              <text :x="role.slot.x + 8" :y="role.slot.y + role.slot.h / 2 + 4">{{ i ? REVIEWER : ACTOR }}</text>
            </g>
          </g>
        </g>

        <!-- The actor's session: one conversation, turn after turn along a rail. -->
        <text class="kicker session-label" :x="L.session.label.x" :y="L.session.label.y">actor · one session</text>
        <line class="rail" :x1="L.session.x0" :x2="L.session.x1" :y1="L.session.y" :y2="L.session.y" />
        <rect class="rail-pulse" :x="L.session.x0" :y="L.session.y - 2" :width="L.session.x1 - L.session.x0" height="4" />
        <g v-for="i in 2" :key="`t${i}`" class="tile" :class="`tile-${i - 1}`">
          <rect :x="L.session.tile(i - 1).x" :y="L.session.tile(i - 1).y" :width="L.session.tile(i - 1).w" :height="L.session.tile(i - 1).h" />
          <text class="tile-n" :x="L.session.tile(i - 1).x + 8" :y="L.session.tile(i - 1).y + 13">turn {{ i }}</text>
          <text class="tile-p" :x="L.session.tile(i - 1).x + 8" :y="L.session.tile(i - 1).y + 26">{{ i === 1 ? 'the task' : 'the notes' }}</text>
        </g>

        <!-- Where the work lands: the workspace, and what the actor changes there. -->
        <g class="env">
          <rect class="card-box" :x="L.env.x" :y="L.env.y" :width="L.env.w" :height="L.env.h" />
          <rect class="glow" :x="L.env.x" :y="L.env.y" :width="L.env.w" :height="L.env.h" />
          <text class="kicker" :x="L.env.x + 12" :y="L.env.y + 20">{{ narrow ? 'workspace' : 'workspace · this directory' }}</text>
          <text class="file" :x="L.env.x + 12" :y="L.env.y + 42">calc.py</text>
          <text class="diff diff-0 del" :x="L.env.x + 12" :y="L.env.y + 60">-   return a - b</text>
          <text class="diff diff-0 add" :x="L.env.x + 12" :y="L.env.y + 76">+   return a + b</text>
          <text class="file diff diff-1" :x="L.env.x + 12" :y="L.env.y + 100">test_calc.py</text>
          <text class="diff diff-1 add" :x="L.env.x + 12" :y="L.env.y + 116">+ def test_add():</text>
          <text class="diff diff-1 add" :x="L.env.x + 12" :y="L.env.y + 132">+   assert add(2, 3) == 5</text>
        </g>

        <!-- The reviewer: a fresh session every round, and the shape it answers in. -->
        <g class="reviewer">
          <rect class="card-box rev-box" :x="L.reviewer.x" :y="L.reviewer.y" :width="L.reviewer.w" :height="L.reviewer.h" />
          <rect class="rev-bar" :x="L.reviewer.x" :y="L.reviewer.y" :width="L.reviewer.w" height="4" />
          <text class="kicker" :x="L.reviewer.x + 12" :y="L.reviewer.y + 22">reviewer</text>
          <g v-for="k in 2" :key="`f${k}`" class="fresh" :class="`fresh-${k - 1}`">
            <rect :x="L.reviewer.x + 12" :y="L.reviewer.y + 32" :width="L.reviewer.w - 24" height="18" />
            <text :x="L.reviewer.x + L.reviewer.w / 2" :y="L.reviewer.y + 45" text-anchor="middle">fresh session</text>
          </g>
          <g class="card card-0">
            <text class="field" :x="L.reviewer.x + 12" :y="L.reviewer.y + 74">done: <tspan class="no">false</tspan></text>
            <text class="field" :x="L.reviewer.x + 12" :y="L.reviewer.y + 94">notes:</text>
            <text class="field note-text" :x="L.reviewer.x + 12" :y="L.reviewer.y + 110">add a test</text>
          </g>
          <g class="card card-1">
            <text class="field" :x="L.reviewer.x + 12" :y="L.reviewer.y + 74">done: <tspan class="yes">true</tspan></text>
            <text class="field" :x="L.reviewer.x + 12" :y="L.reviewer.y + 94">notes:</text>
            <text class="field note-text" :x="L.reviewer.x + 12" :y="L.reviewer.y + 110">all good</text>
          </g>
          <g :transform="`translate(${L.reviewer.x + L.reviewer.w / 2} ${L.reviewer.y + L.reviewer.h - 16})`">
            <g class="stamp">
              <rect x="-34" y="-13" width="68" height="26" />
              <text y="5" text-anchor="middle">DONE</text>
            </g>
          </g>
        </g>

        <!-- The reviewer reading the workspace. -->
        <line class="read-line" :x1="L.env.x + L.env.w" :x2="L.reviewer.x" :y1="L.env.y + L.env.h / 2" :y2="L.env.y + L.env.h / 2" />

        <!-- The notes, carried back up as the next prompt. -->
        <path :id="`${id}-loop`" class="loop-line" :d="L.loop" />
        <path :id="`${id}-words`" class="words-path" :d="backwards(L.loop)" />
        <text class="loop-label" dy="-7"><textPath :href="`#${id}-words`" :startOffset="narrow ? '64%' : '50%'" text-anchor="middle">{{ narrow ? 'next prompt' : 'notes → next prompt' }}</textPath></text>

        <!-- What the turns travel on. -->
        <path class="drop" :d="`M ${centre(L.session.tile(0)).x} ${centre(L.session.tile(0)).y} L ${centre(L.env).x - 40} ${L.env.y + 40}`" />
        <path class="drop-2" :d="`M ${centre(L.session.tile(1)).x} ${centre(L.session.tile(1)).y} L ${centre(L.env).x} ${L.env.y + 104}`" />
        <rect class="packet" x="0" y="0" width="10" height="10" />
        <rect class="packet packet-2" x="0" y="0" width="10" height="10" />
        <rect class="packet note-packet" x="0" y="0" width="10" height="10" />

        <!-- The trace: the run's turns on one axis, and what they came to. -->
        <text class="kicker" :x="L.trace.label.x" :y="L.trace.label.y">trace</text>
        <line class="axis" :x1="L.trace.x0" :x2="L.trace.x1" :y1="L.trace.y + 22" :y2="L.trace.y + 22" />
        <g v-for="(t, i) in TURNS" :key="`b${i}`">
          <rect class="bar" :class="t.who" :x="span(t).x" :y="L.trace.y" :width="span(t).w" height="14" />
          <text class="bar-word" :x="span(t).x" :y="L.trace.y + 38">{{ t.who }}</text>
        </g>
        <text class="tally" :x="L.trace.tally.x" :y="L.trace.tally.y" text-anchor="end">4 turns · $1.84 of the budget</text>
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.rule {
  stroke: var(--hmz-con-line);
  stroke-width: 1;
}

.cmd {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.card-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.flow-bar {
  fill: var(--hmz-ink);
}

.rev-bar {
  fill: var(--hmz-red);
}

.kicker {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  fill: var(--hmz-stage-dim);
}

.flow-name {
  font-family: var(--vp-font-family-mono);
  font-size: 16px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.role {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.slot {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-dasharray: 3 3;
}

.chip rect {
  fill: var(--hmz-ink);
}

.chip.hot rect {
  fill: var(--hmz-red);
}

.chip text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-paper);
}

.chip.hot text {
  fill: #fff;
}

.rail {
  stroke: var(--hmz-ink);
  stroke-width: 2;
}

.rail-pulse {
  fill: var(--hmz-red);
  opacity: 0;
}

.tile rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-ink);
  stroke-width: 1.5;
}

.tile-n {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.tile-p {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.tile-1 rect {
  stroke: var(--hmz-red);
}

.glow {
  fill: var(--hmz-red-soft);
  opacity: 0;
}

.file {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.diff {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
}

.diff.del {
  fill: var(--hmz-red);
}

.diff.add {
  fill: var(--hmz-lane-2);
}

.fresh rect {
  fill: none;
  stroke: var(--hmz-red);
  stroke-dasharray: 3 2;
}

.fresh text {
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-red);
}

.field {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  fill: var(--hmz-stage-ink);
}

.note-text {
  fill: var(--hmz-stage-dim);
}

.no {
  fill: var(--hmz-red);
  font-weight: 700;
}

.yes {
  fill: var(--hmz-lane-2);
  font-weight: 700;
}

.stamp rect {
  fill: none;
  stroke: var(--hmz-red);
  stroke-width: 2.5;
}

.stamp text {
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0.18em;
  fill: var(--hmz-red);
}

.read-line {
  stroke: var(--hmz-red);
  stroke-width: 1.5;
  stroke-dasharray: 4 3;
}

.loop-line {
  fill: none;
  stroke: var(--hmz-red);
  stroke-width: 2;
}

.loop-label {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-red);
}

.drop,
.drop-2,
.words-path {
  fill: none;
  stroke: none;
}

.packet {
  fill: var(--hmz-ink);
  opacity: 0;
}

.note-packet {
  fill: var(--hmz-red);
}

.axis {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1;
}

.bar.actor {
  fill: var(--hmz-ink);
}

.bar.reviewer {
  fill: var(--hmz-red);
}

.bar-word {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.tally {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}
</style>
