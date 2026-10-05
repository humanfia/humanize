<script setup lang="ts">
// Worktrees, copies and scratch, played out on `parts` and `guarded` from that page. From the
// workspace (`LocalEnv`, the run's own directory, where a turn given no `env=` works) a flow
// derives others on the same machine, each kind granted by a mixin on the role's type
// (src/hmz/flows/envs.py): `derive_subdir` needs none, `derive_worktree` needs
// `GitWorktreeEnvMixin` (detached at `ref`, never removed by humanize),
// `derive_temp_clone(id)` needs `TemporaryClonedDirEnvMixin` (a copy as it is, uncommitted
// changes too) and `derive_scratch(id)` needs `ScratchDirEnvMixin` (empty), both removed when
// the flow ends; `snapshot` and `rewind` need `GitEnvMixin`. A call the role did not declare
// raises `CapabilityNotGranted` (src/hmz/flows/errors.py). A session is only a history: every
// turn says where it works, `agent.run(prompt, session=s, env=tree)`. The files and the failed
// check are the page's own (`check.py` asserting `add(2, 3) == 5`).
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { rig, type Shot } from '../../motion/camera'
import { createFx, type Fx } from '../../motion/fx'
import { motion } from '../../motion/gsap'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'

const BEATS = [
  'Derive more places, each by a mixin',
  'Three worktrees, detached at main',
  'Three turns at once, each with env=tree',
  'Snapshot, then a turn in the workspace',
  'The check fails: rewind puts all of it back',
  'A copy and a scratch dir go with the flow',
]

type Tok = [cls: '' | 'kw' | 'fn' | 'str' | 'dim' | 'env', text: string]
const CODE: Tok[][] = [
  [['dim', '# parts: a worktree per part']],
  [['', 'tree = '], ['kw', 'await '], ['', 'workspace.']],
  [['', '  '], ['fn', 'derive_worktree'], ['', '(ref='], ['str', '"main"'], ['', ')']],
  [['kw', 'await '], ['fn', 'agent.run'], ['', '(ask, session=s,']],
  [['', '  '], ['env', 'env=tree'], ['', ')']],
  [['dim', '# guarded: undo a bad turn']],
  [['', 'before = '], ['kw', 'await '], ['', 'workspace.']],
  [['', '  '], ['fn', 'snapshot'], ['', '('], ['str', '"before-task"'], ['', ')']],
  [['kw', 'await '], ['fn', 'agent.run'], ['', '(task, session=s)']],
  [['', 'code, _, err = '], ['kw', 'await '], ['', 'workspace.']],
  [['', '  '], ['fn', 'exec'], ['', '(CHECK)']],
  [['kw', 'if '], ['', 'code != 0:']],
  [['kw', '  await '], ['', 'workspace.'], ['fn', 'rewind'], ['', '(before)']],
]

/** The environments derived, in the order of `L.cards`. */
const CARDS = [
  { kind: 'worktree', id: 'parser', detail: '@main', mixin: 'GitWorktreeEnvMixin', end: 'kept' },
  { kind: 'worktree', id: 'printer', detail: '@main', mixin: 'GitWorktreeEnvMixin', end: 'kept' },
  { kind: 'worktree', id: 'cli', detail: '@main', mixin: 'GitWorktreeEnvMixin', end: 'kept' },
  { kind: 'subdir', id: 'docs/', detail: '', mixin: 'no mixin needed', end: 'kept' },
  { kind: 'temp clone', id: 'try-1', detail: 'as it is', mixin: 'TemporaryClonedDirEnvMixin', end: 'removed' },
  { kind: 'scratch', id: 'notes', detail: 'empty', mixin: 'ScratchDirEnvMixin', end: 'removed' },
] as const

interface Pt {
  x: number
  y: number
}

interface Box extends Pt {
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  code: { x: number; y: number; w: number }
  line: number
  deny: Box
  ws: Box & { head: Pt; sub: Pt; files: Pt[]; tagX: number; snap: Pt; exec: Pt; err: Pt; back: Pt; rightX: number }
  cards: Box[]
  captions: Pt[]
  shots: Record<'open' | 'trees' | 'guard' | 'end' | 'whole', Shot>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  code: { x: 12, y: 14, w: 238 },
  line: 15,
  deny: { x: 12, y: 266, w: 238, h: 46 },
  ws: {
    x: 262,
    y: 34,
    w: 170,
    h: 226,
    head: { x: 274, y: 54 },
    sub: { x: 274, y: 69 },
    files: [
      { x: 286, y: 96 },
      { x: 286, y: 116 },
      { x: 286, y: 136 },
    ],
    tagX: 422,
    snap: { x: 274, y: 168 },
    exec: { x: 274, y: 192 },
    err: { x: 274, y: 208 },
    back: { x: 274, y: 236 },
    rightX: 422,
  },
  cards: [
    { x: 446, y: 34, w: 182, h: 34 },
    { x: 446, y: 72, w: 182, h: 34 },
    { x: 446, y: 110, w: 182, h: 34 },
    { x: 446, y: 156, w: 182, h: 34 },
    { x: 446, y: 202, w: 182, h: 34 },
    { x: 446, y: 240, w: 182, h: 34 },
  ],
  captions: [
    { x: 262, y: 282 },
    { x: 262, y: 298 },
  ],
  shots: {
    open: { x: 220, y: 150, s: 1.3 },
    trees: { x: 400, y: 120, s: 1.3 },
    guard: { x: 270, y: 170, s: 1.2 },
    end: { x: 470, y: 220, s: 1.25 },
    whole: { x: 320, y: 180, s: 1 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 640,
  code: { x: 12, y: 8, w: 336 },
  line: 15,
  deny: { x: 12, y: 254, w: 336, h: 40 },
  ws: {
    x: 12,
    y: 302,
    w: 336,
    h: 126,
    head: { x: 24, y: 322 },
    sub: { x: 24, y: 337 },
    files: [
      { x: 36, y: 362 },
      { x: 36, y: 382 },
      { x: 36, y: 402 },
    ],
    tagX: 168,
    snap: { x: 186, y: 322 },
    exec: { x: 186, y: 352 },
    err: { x: 186, y: 368 },
    back: { x: 186, y: 400 },
    rightX: 338,
  },
  cards: [
    { x: 12, y: 438, w: 164, h: 34 },
    { x: 184, y: 438, w: 164, h: 34 },
    { x: 12, y: 476, w: 164, h: 34 },
    { x: 184, y: 476, w: 164, h: 34 },
    { x: 12, y: 514, w: 336, h: 34 },
    { x: 12, y: 552, w: 164, h: 34 },
  ],
  captions: [
    { x: 12, y: 606 },
    { x: 12, y: 622 },
  ],
  shots: {
    open: { x: 180, y: 300, s: 1.04 },
    trees: { x: 180, y: 320, s: 1 },
    guard: { x: 180, y: 320, s: 1 },
    end: { x: 180, y: 320, s: 1 },
    whole: { x: 180, y: 320, s: 1 },
  },
}

const FILES = ['calc.py', 'check.py', 'NOTES.md']

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

const lineY = (i: number) => L.value.code.y + 36 + i * L.value.line
const codeEnd = (i: number) => ({ x: L.value.code.x + L.value.code.w - 10, y: lineY(i) - 4 })
const codeH = computed(() => 36 + CODE.length * L.value.line + 6)
const mid = (b: Box): Pt => ({ x: b.x + 10, y: b.y + b.h / 2 })

const scene = useScene({
  still: 'rest',
  repeatDelay: 1.2,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const gsap = motion()
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const at = (sel: string) => q(sel)
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), fx: () => fx, start: l.shots.open })

    const lane = (i: number) => () => palette.lane[i]
    const ok = () => palette.accent
    const violet = () => palette.accent2
    const warm = () => palette.warm
    const danger = () => palette.danger
    const wsHead = { x: l.ws.head.x + 30, y: l.ws.head.y - 4 }

    const caret = one('.caret')
    const pc = (i: number, when: number) => {
      tl.to(caret, { attr: { y: lineY(i) - 12 }, duration: 0.4, ease: 'cine' }, when)
      tl.fromTo(at('.code-line')[i], { opacity: 0.55 }, { opacity: 1, duration: 0.3 }, when + 0.1)
    }
    const pop = (el: Element, when: number) =>
      tl.fromTo(el, { opacity: 0, scale: 0.4, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.45, ease: 'back.out(2.4)' }, when)
    const card = (i: number, when: number) => {
      tl.fromTo(at('.card-box')[i], { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.7, ease: 'cine' }, when)
      tl.fromTo(at('.env-card')[i], { opacity: 0, x: -10 }, { opacity: 1, x: 0, duration: 0.5 }, when + 0.2)
    }

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(at('.code-line'), { opacity: 0 }, 0)
    tl.set(at('.env-card, .ws, .deny, .tag, .file-new, .snap, .exec, .err, .back, .caption, .end-tag, .turn-bar, .wipe, .strike'), { opacity: 0 }, 0)
    tl.set(at('.card-box, .ws-box'), { drawSVG: '0%' }, 0)
    tl.set(caret, { opacity: 0, attr: { y: lineY(0) - 12 } }, 0)

    // 0 · the workspace, and a place derived from it: a subdirectory needs no mixin; anything
    //     the role's type did not declare is refused.
    tl.addLabel('beat-0', 0)
    tl.fromTo(one('.card'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.7 }, 0.1)
    tl.fromTo(at('.code-line'), { opacity: 0, x: -10 }, { opacity: 0.55, x: 0, duration: 0.45, stagger: 0.06 }, 0.3)
    tl.to(one('.ws-box'), { drawSVG: '100%', duration: 1, ease: 'cine' }, 1)
    tl.to(one('.ws'), { opacity: 1, duration: 0.5 }, 1.4)
    tl.fromTo(at('.file'), { opacity: 0, x: -6 }, { opacity: 1, x: 0, duration: 0.4, stagger: 0.12 }, 1.6)
    cam.shot(l.shots.whole, 1.6, 1.8)
    cam.beam(wsHead, mid(l.cards[3]), lane(5), 2.6, { duration: 0.8, bend: -0.2, burst: 10 })
    card(3, 3.2)
    tl.fromTo(one('.deny'), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5 }, 3.8)
    tl.to(one('.deny-shake'), { x: -4, duration: 0.07, repeat: 5, yoyo: true, ease: 'none' }, 4.1)
    cam.flare({ x: l.deny.x + 30, y: l.deny.y + l.deny.h - 14 }, danger, 4.1, 18, 70)

    // 1 · three worktrees of the repository, each detached at main.
    const T1 = 5.4
    tl.addLabel('beat-1', T1)
    tl.to(caret, { opacity: 1, duration: 0.3 }, T1)
    pc(1, T1)
    pc(2, T1 + 0.4)
    cam.shot(l.shots.trees, T1 + 0.2, 1.6)
    for (let i = 0; i < 3; i += 1) {
      cam.beam(wsHead, mid(l.cards[i]), lane(0), T1 + 0.8 + i * 0.3, { duration: 0.8, bend: -0.15, burst: 10 })
      card(i, T1 + 1.4 + i * 0.3)
    }

    // 2 · a turn in each, all at once: every run says where it works.
    const T2 = T1 + 3.4
    tl.addLabel('beat-2', T2)
    pc(3, T2)
    pc(4, T2 + 0.4)
    for (let i = 0; i < 3; i += 1) {
      const c = l.cards[i]
      cam.beam(codeEnd(4), { x: c.x + 8, y: c.y + c.h - 4 }, lane(i === 1 ? 2 : i === 2 ? 3 : 0), T2 + 0.8, { duration: 0.9, bend: 0.1 + i * 0.05 })
      tl.to(at('.turn-bar')[i], { opacity: 1, duration: 0.2 }, T2 + 1.6)
      tl.fromTo(at('.turn-bar')[i], { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 2 + i * 0.3, ease: 'power1.inOut' }, T2 + 1.6)
      cam.flare({ x: c.x + c.w - 8, y: c.y + c.h - 3 }, ok, T2 + 3.6 + i * 0.3, 12, 60)
    }

    // 3 · back in the workspace: a snapshot first, then a turn with no env= -- it works here.
    const T3 = T2 + 4.6
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.guard, T3, 1.6)
    pc(6, T3)
    pc(7, T3 + 0.4)
    cam.beam(codeEnd(7), { x: l.ws.snap.x + 6, y: l.ws.snap.y - 4 }, violet, T3 + 0.7, { duration: 0.8, bend: -0.15 })
    pop(one('.snap'), T3 + 1.4)
    cam.flare({ x: l.ws.snap.x + 6, y: l.ws.snap.y - 4 }, violet, T3 + 1.4, 16, 70)
    pc(8, T3 + 1.9)
    cam.beam(codeEnd(8), wsHead, lane(0), T3 + 2.2, { duration: 0.9, bend: -0.2, burst: 12 })
    tl.fromTo(one('.ws-sub'), { opacity: 1 }, { opacity: 0.4, duration: 0.2, repeat: 3, yoyo: true }, T3 + 3)
    pop(at('.tag-edit')[0], T3 + 3.4)
    tl.fromTo(one('.file-new'), { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.5 }, T3 + 3.8)
    pop(one('.tag-new'), T3 + 4)

    // 4 · the check fails, and the rewind puts every file back as the snapshot has it.
    const T4 = T3 + 5
    tl.addLabel('beat-4', T4)
    pc(9, T4)
    pc(10, T4 + 0.4)
    cam.beam(codeEnd(10), { x: l.ws.exec.x + 6, y: l.ws.exec.y - 4 }, warm, T4 + 0.6, { duration: 0.8, bend: -0.15 })
    tl.to(one('.exec'), { opacity: 1, duration: 0.4 }, T4 + 1.3)
    pop(one('.exit'), T4 + 1.7)
    tl.to(one('.err'), { opacity: 1, duration: 0.4 }, T4 + 1.9)
    cam.flare({ x: l.ws.rightX - 16, y: l.ws.exec.y - 4 }, danger, T4 + 1.7, 22, 80)
    pc(11, T4 + 2.4)
    pc(12, T4 + 2.8)
    cam.beam(codeEnd(12), { x: l.ws.back.x + 6, y: l.ws.back.y - 4 }, violet, T4 + 3, { duration: 0.8, bend: -0.15 })
    tl.to(one('.back'), { opacity: 1, duration: 0.4 }, T4 + 3.7)
    // A wipe down the files, from the snapshot: the edit undone, the new file gone.
    tl.fromTo(one('.wipe'), { opacity: 0, scaleY: 0, transformOrigin: '50% 0%' }, { opacity: 0.9, scaleY: 1, duration: 0.7, ease: 'cine' }, T4 + 3.9)
    tl.to(one('.wipe'), { opacity: 0, duration: 0.5 }, T4 + 4.7)
    tl.to(at('.tag-edit')[0], { opacity: 0, duration: 0.3 }, T4 + 4.1)
    pop(one('.tag-back'), T4 + 4.3)
    tl.to(one('.strike'), { opacity: 1, duration: 0.3 }, T4 + 4.3)
    tl.to(at('.file-new, .tag-new, .strike'), { opacity: 0.25, duration: 0.6 }, T4 + 4.8)
    cam.flare({ x: l.ws.files[2].x + 20, y: l.ws.files[2].y - 4 }, violet, T4 + 4.5, 18, 70)
    pop(one('.as-was'), T4 + 4.6)

    // 5 · a copy as it is, and a scratch dir; both go when the flow ends. Worktrees stay.
    const T5 = T4 + 5.8
    tl.addLabel('beat-5', T5)
    tl.to(caret, { opacity: 0.3, duration: 0.4 }, T5)
    cam.shot(l.shots.end, T5, 1.6)
    cam.beam(wsHead, mid(l.cards[4]), lane(3), T5 + 0.5, { duration: 0.8, bend: -0.2, burst: 10 })
    card(4, T5 + 1.1)
    cam.beam(wsHead, mid(l.cards[5]), lane(4), T5 + 1.4, { duration: 0.8, bend: -0.2, burst: 10 })
    card(5, T5 + 2)
    // The flow ends.
    const E = T5 + 3.4
    tl.to(at('.env-card')[4], { opacity: 0.35, duration: 0.6 }, E)
    tl.to(at('.env-card')[5], { opacity: 0.35, duration: 0.6 }, E + 0.1)
    tl.to(at('.card-box')[4], { opacity: 0.35, duration: 0.6 }, E)
    tl.to(at('.card-box')[5], { opacity: 0.35, duration: 0.6 }, E + 0.1)
    tl.to(at('.detail'), { opacity: 0, duration: 0.3 }, E)
    CARDS.forEach((c, i) => {
      if (c.kind === 'subdir') return
      pop(at('.end-tag')[i], E + 0.3 + i * 0.08)
    })
    cam.flare(mid(l.cards[4]), danger, E + 0.2, 14, 60)
    cam.flare(mid(l.cards[5]), danger, E + 0.3, 14, 60)
    tl.to(at('.caption'), { opacity: 1, duration: 0.5, stagger: 0.2 }, E + 0.8)

    tl.addLabel('rest', E + 2.4)
    cam.shot(l.shots.whole, E + 0.6, 1.6)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, E + 5)

    tl.fromTo(at('.hum'), { strokeDashoffset: 0 }, { strokeDashoffset: -80, duration: tl.duration(), ease: 'none' }, 0)
    gsap.set(caret, { opacity: 0 })
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 16"
    label="Worktrees, copies and scratch. From the workspace, the run's own directory, a flow derives other environments on the same machine, each kind granted by a mixin on the role's type: derive_subdir needs none; a call the role did not declare raises CapabilityNotGranted. parts derives three worktrees with derive_worktree(ref='main'), which needs GitWorktreeEnvMixin, each detached at main, and takes a turn in each at once, every run saying where it works with env=tree. guarded takes snapshot('before-task'), which needs GitEnvMixin, then a turn with no env=, which works in the workspace: it edits calc.py and adds NOTES.md. exec of the check exits 1 with an AssertionError, and rewind(before) puts the workspace back exactly: the edit undone, NOTES.md gone. A temporary clone, a copy of the workdir as it is, with TemporaryClonedDirEnvMixin, and an empty scratch directory, with ScratchDirEnvMixin, are removed when the flow ends; worktrees and snapshots are never removed by humanize."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <g class="world">
        <!-- the two flows' code -->
        <g class="card">
          <rect class="code-box" :x="L.code.x" :y="L.code.y" :width="L.code.w" :height="codeH" rx="10" />
          <text class="code-head" :x="L.code.x + 12" :y="L.code.y + 17">@flow · parts, and guarded</text>
          <rect class="caret" :x="L.code.x + 4" :y="lineY(0) - 12" width="3" height="15" rx="1.5" />
          <g v-for="(line, i) in CODE" :key="i" class="code-line">
            <text :x="L.code.x + 13" :y="lineY(i)"><tspan v-for="(tok, j) in line" :key="j" :class="tok[0]">{{ tok[1] }}</tspan></text>
          </g>
        </g>

        <!-- what a role did not declare -->
        <g class="deny">
          <g class="deny-shake">
            <rect class="deny-box" :x="L.deny.x" :y="L.deny.y" :width="L.deny.w" :height="L.deny.h" rx="8" />
            <text class="deny-words" :x="L.deny.x + 12" :y="L.deny.y + (L.deny.h > 42 ? 19 : 16)">a call its role did not declare</text>
            <text class="deny-err" :x="L.deny.x + 12" :y="L.deny.y + (L.deny.h > 42 ? 36 : 32)">raises CapabilityNotGranted</text>
          </g>
        </g>

        <!-- the workspace -->
        <rect class="ws-box" :x="L.ws.x" :y="L.ws.y" :width="L.ws.w" :height="L.ws.h" rx="10" />
        <g class="ws">
          <rect class="ws-fill" :x="L.ws.x" :y="L.ws.y" :width="L.ws.w" :height="L.ws.h" rx="10" />
          <text class="ws-name" :x="L.ws.head.x" :y="L.ws.head.y">workspace</text>
          <text class="ws-sub" :x="L.ws.sub.x" :y="L.ws.sub.y">LocalEnv · where env=None</text>
        </g>
        <rect class="wipe" :x="L.ws.files[0].x - 12" :y="L.ws.files[0].y - 14" :width="L.ws.tagX - L.ws.files[0].x + 18" :height="L.ws.files[2].y - L.ws.files[0].y + 22" rx="5" />
        <g v-for="(f, i) in FILES" :key="f" :class="i === 2 ? 'file-new' : 'file'">
          <rect class="file-icon" :x="L.ws.files[i].x - 10" :y="L.ws.files[i].y - 9" width="7" height="10" rx="1.5" />
          <text class="file-name" :x="L.ws.files[i].x + 2" :y="L.ws.files[i].y">{{ f }}</text>
        </g>
        <line class="strike" :x1="L.ws.files[2].x - 12" :x2="L.ws.files[2].x + 56" :y1="L.ws.files[2].y - 4" :y2="L.ws.files[2].y - 4" />
        <g class="tag tag-edit"><text :x="L.ws.tagX" :y="L.ws.files[0].y" text-anchor="end">edited</text></g>
        <g class="tag tag-back"><text :x="L.ws.tagX" :y="L.ws.files[0].y" text-anchor="end">as it was</text></g>
        <g class="tag tag-new"><text :x="L.ws.tagX" :y="L.ws.files[2].y" text-anchor="end">new</text></g>
        <g class="snap">
          <path class="flag" :d="`M${L.ws.snap.x + 2} ${L.ws.snap.y + 2} V${L.ws.snap.y - 11} l9 3.5 l-9 3.5`" />
          <text class="row-words" :x="L.ws.snap.x + 16" :y="L.ws.snap.y">snapshot <tspan class="mono violet">before-task</tspan></text>
        </g>
        <g class="exec">
          <text class="row-words" :x="L.ws.exec.x" :y="L.ws.exec.y"><tspan class="mono">exec</tspan> check.py</text>
          <g class="exit"><text class="bad mono" :x="L.ws.rightX" :y="L.ws.exec.y" text-anchor="end">exit 1</text></g>
        </g>
        <g class="err"><text class="mono bad" :x="L.ws.err.x" :y="L.ws.err.y">AssertionError</text></g>
        <g class="back">
          <text class="row-words" :x="L.ws.back.x" :y="L.ws.back.y"><tspan class="mono">rewind</tspan>(before)</text>
          <g class="as-was"><text class="good" :x="L.ws.rightX" :y="L.ws.back.y" text-anchor="end">restored</text></g>
        </g>

        <!-- what is derived from it -->
        <rect v-for="(c, i) in L.cards" :key="`b${i}`" class="card-box hum" :class="`k-${CARDS[i].kind.replace(' ', '-')}`" :x="c.x" :y="c.y" :width="c.w" :height="c.h" rx="7" />
        <g v-for="(c, i) in L.cards" :key="`c${i}`" class="env-card">
          <text class="env-name" :x="c.x + 10" :y="c.y + 14">{{ CARDS[i].kind }} · <tspan class="mono">{{ CARDS[i].id }}</tspan></text>
          <text class="env-mixin" :x="c.x + 10" :y="c.y + 28">{{ CARDS[i].mixin }}</text>
          <text v-if="CARDS[i].detail" class="detail" :x="c.x + c.w - 9" :y="c.y + 14" text-anchor="end">{{ CARDS[i].detail }}</text>
          <rect v-if="i < 3" class="turn-bar" :class="`turn-${i}`" :x="c.x + 6" :y="c.y + c.h - 4" :width="c.w - 12" height="3" rx="1.5" />
        </g>
        <g v-for="(c, i) in L.cards" :key="`e${i}`" class="end-tag" :class="CARDS[i].end">
          <text :x="c.x + c.w - 9" :y="c.y + 14" text-anchor="end">{{ CARDS[i].end }}</text>
        </g>
        <text class="caption" :x="L.captions[0].x" :y="L.captions[0].y">worktrees stay: git’s, and yours</text>
        <text class="caption" :x="L.captions[1].x" :y="L.captions[1].y">a temp clone and a scratch dir: removed when the flow ends</text>
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.mono {
  font-family: var(--vp-font-family-mono);
}

.code-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.code-head {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-stage-dim);
}

.code-line text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  white-space: pre;
  fill: var(--hmz-stage-ink);
}

.code-line .kw {
  fill: var(--hmz-lane-3);
  font-weight: 600;
}

.code-line .fn {
  fill: var(--hmz-lane-1);
}

.code-line .str {
  fill: var(--hmz-lane-4);
}

.code-line .dim {
  fill: var(--hmz-stage-dim);
  font-style: italic;
}

.code-line .env {
  fill: var(--hmz-warm);
  font-weight: 700;
}

.caret {
  fill: var(--hmz-lane-1);
}

.deny-box {
  fill: var(--hmz-stage-card);
  stroke: var(--vp-c-danger-1);
  stroke-width: 1.2;
  stroke-dasharray: 4 3;
}

.deny-words {
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.deny-err {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-danger-1);
}

.ws-box {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 1.4;
}

.ws-fill {
  fill: var(--hmz-warm);
  fill-opacity: 0.07;
}

.ws-name {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--hmz-warm);
}

.ws-sub {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.file-icon {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.1;
}

.file-name {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.wipe {
  fill: var(--hmz-accent-2);
  fill-opacity: 0.18;
  stroke: var(--hmz-accent-2);
  stroke-width: 1.2;
}

.strike {
  stroke: var(--vp-c-danger-1);
  stroke-width: 1.4;
}

.tag text {
  font-size: 11px;
  font-weight: 700;
}

.tag-edit text,
.tag-new text {
  fill: var(--hmz-warm);
}

.tag-back text {
  fill: var(--hmz-accent-2);
}

.flag {
  fill: var(--hmz-accent-2);
  stroke: var(--hmz-accent-2);
  stroke-width: 1.4;
  stroke-linejoin: round;
}

.row-words {
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.row-words .mono {
  font-weight: 600;
}

.violet {
  fill: var(--hmz-accent-2);
}

.bad {
  font-size: 11px;
  font-weight: 700;
  fill: var(--vp-c-danger-1);
}

.good {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.card-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.3;
}

.card-box.k-subdir {
  stroke: var(--hmz-lane-6);
}

.card-box.k-temp-clone {
  stroke: var(--hmz-lane-4);
  stroke-dasharray: 5 3;
}

.card-box.k-scratch {
  stroke: var(--hmz-lane-5);
  stroke-dasharray: 5 3;
}

.env-name {
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.env-name .mono {
  font-weight: 600;
}

.env-mixin {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.detail {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}

.turn-0 {
  fill: var(--hmz-lane-1);
}

.turn-1 {
  fill: var(--hmz-lane-3);
}

.turn-2 {
  fill: var(--hmz-lane-4);
}

.end-tag text {
  font-size: 11px;
  font-weight: 700;
}

.end-tag.kept text {
  fill: var(--hmz-accent);
}

.end-tag.removed text {
  fill: var(--vp-c-danger-1);
}

.caption {
  font-size: 11px;
  font-style: italic;
  fill: var(--hmz-stage-dim);
}
</style>
