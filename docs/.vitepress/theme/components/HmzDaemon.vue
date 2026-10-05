<script setup lang="ts">
// A run held apart from the terminal that started it. `hmz` holds a directory's runs in a host
// of their own, one per directory, and every interface is a frontend of it through the one
// daemon socket of the machine (`src/hmz/daemon/`, and `docs/reference/daemon.md`). Closing a terminal lets go of that
// frontend and the run goes on taking turns; `hmz` in the same directory opens a new one on
// it, read from the top. Any number of frontends read one run: interfaces, and programs on
// the SDK. An outworlder role one of them claims is that frontend's alone to answer; a
// question is shown to every frontend, and its claimant answers it. A stop, from any of them,
// stops the one run for all, and each is told who stopped it. The rounds are drawn.
import { computed, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'
import ScenePlane from './scene/ScenePlane.vue'
import { drawPlane } from './scene/plane'

const BEATS = [
  'The run is held apart',
  'Close the terminal; it goes on',
  'hmz brings you back, from the top',
  'Several frontends, one run',
  'Each answers for its own part',
  'A stop is for everybody',
]

interface P {
  x: number
  y: number
}

interface Layout {
  w: number
  h: number
  host: { x: number; y: number; w: number; h: number }
  core: P
  round: P
  roles: P[]
  wins: P[]
  winW: number
  winH: number
  /** Where the camera looks while one terminal is all there is. */
  focus: { s: number; x: number; y: number }
  side: boolean
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  host: { x: 318, y: 26, w: 304, h: 312 },
  core: { x: 470, y: 192 },
  round: { x: 470, y: 290 },
  roles: [
    { x: 410, y: 76 },
    { x: 530, y: 76 },
  ],
  wins: [
    { x: 24, y: 118 },
    { x: 24, y: 40 },
    { x: 24, y: 196 },
    { x: 24, y: 274 },
  ],
  winW: 170,
  winH: 60,
  focus: { s: 1.12, x: 300, y: 176 },
  side: true,
}

const NARROW: Layout = {
  w: 360,
  h: 470,
  host: { x: 12, y: 50, w: 336, h: 246 },
  core: { x: 180, y: 184 },
  round: { x: 296, y: 190 },
  roles: [
    { x: 96, y: 92 },
    { x: 264, y: 92 },
  ],
  wins: [
    { x: 12, y: 316 },
    { x: 188, y: 316 },
    { x: 12, y: 396 },
    { x: 188, y: 396 },
  ],
  winW: 160,
  winH: 62,
  focus: { s: 1.08, x: 150, y: 240 },
  side: false,
}

const FRONTS = [
  { name: 'alice@tui', hue: 'var(--hmz-lane-1)', lane: 0, sdk: false },
  { name: 'bob@tui', hue: 'var(--hmz-lane-3)', lane: 2, sdk: false },
  { name: 'carol@tui', hue: 'var(--hmz-lane-4)', lane: 3, sdk: false },
  { name: 'bot@sdk', hue: 'var(--hmz-lane-2)', lane: 1, sdk: true },
]

// The outworlder roles, and who claims each.
const ROLES = [
  { name: 'planner', by: 2 },
  { name: 'reviewer', by: 1 },
]

const START = 7

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

// Where a terminal meets its link, and the link itself: out of its right side into the host,
// or, stacked on a phone, out of its top.
function port(i: number): P {
  const l = L.value
  const w = l.wins[i]
  return l.side ? { x: w.x + l.winW, y: w.y + l.winH / 2 } : { x: w.x + l.winW / 2, y: w.y }
}

function link(i: number): string {
  const l = L.value
  const a = port(i)
  if (l.side) {
    const b = { x: l.core.x - 40, y: l.core.y }
    return `M ${a.x} ${a.y} C ${a.x + 90} ${a.y} ${b.x - 110} ${b.y} ${b.x} ${b.y}`
  }
  const b = { x: l.core.x, y: l.core.y + 40 }
  return `M ${a.x} ${a.y} C ${a.x} ${a.y - 50} ${b.x} ${b.y + 60} ${b.x} ${b.y}`
}

function claim(r: number): string {
  const l = L.value
  const a = port(ROLES[r].by)
  const role = l.roles[r]
  const b = { x: role.x, y: role.y + 12 }
  if (l.side) return `M ${a.x} ${a.y} C ${a.x + 60} ${a.y - 10} ${b.x - 40} ${b.y + 70} ${b.x} ${b.y}`
  return `M ${a.x} ${a.y} C ${a.x} ${a.y - 90} ${b.x} ${b.y + 90} ${b.x} ${b.y}`
}

// The camera over the whole picture, applied by hand so a point can be followed onto the canvas.
const cam = { x: 0, y: 0, s: 1 }
let worldEl: SVGGElement | null = null
const applyCam = () => worldEl?.setAttribute('transform', `translate(${cam.x} ${cam.y}) scale(${cam.s})`)
const screen = (p: P): P => ({ x: cam.x + p.x * cam.s, y: cam.y + p.y * cam.s })

const scene = useScene({
  still: 'rest',
  repeatDelay: 0.6,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    worldEl = q('.world')[0] as SVGGElement
    const at = (sel: string) => q(sel)
    const win = (i: number, sel = '') => q(`.win-${i}${sel ? ` ${sel}` : ''}`)
    const links = at('.link') as SVGPathElement[]
    const hue = (i: number) => palette.lane[FRONTS[i].lane]

    // A mote along a drawn path, followed through the camera.
    function along(path: SVGPathElement, color: () => string, when: number, opts: { reverse?: boolean; duration?: number; burst?: number } = {}) {
      const p = { t: 0 }
      tl.fromTo(
        p,
        { t: 0 },
        {
          t: 1,
          duration: opts.duration ?? 0.9,
          ease: 'power1.inOut',
          onUpdate: () => {
            const len = path.getTotalLength()
            const pt = path.getPointAtLength((opts.reverse ? 1 - p.t : p.t) * len)
            const s = screen(pt)
            fx?.trail(s.x, s.y, color(), 2.4)
          },
          onComplete: () => {
            if (!opts.burst) return
            const len = path.getTotalLength()
            const s = screen(path.getPointAtLength(opts.reverse ? 0 : len))
            fx?.spark(s.x, s.y, color(), opts.burst, 60)
          },
        },
        when,
      )
    }

    const focus = l.focus
    const aimed = { s: focus.s, x: l.w / 2 - focus.x * focus.s, y: l.h / 2 - focus.y * focus.s }

    // Clean slate for every loop.
    tl.set(at('.win-1, .win-2, .win-3, .link-1, .link-2, .link-3, .role, .owner, .claim, .stopped, .core-stop, .wave, .ask, .replay, .gone'), { autoAlpha: 0 }, 0)
    tl.set(at('.win-0, .link-0, .body, .core-live'), { autoAlpha: 1 }, 0)
    // A terminal opens and closes like a tube: a line, then a point. Scaled by hand about its
    // own middle, so the scale never fights the position.
    const tube = FRONTS.map(() => ({ sx: 1, sy: 1 }))
    const winIn = at('.win-in')
    const applyTube = (i: number) => () =>
      winIn[i].setAttribute('transform', `translate(${l.winW / 2} ${l.winH / 2}) scale(${tube[i].sx} ${tube[i].sy}) translate(${-l.winW / 2} ${-l.winH / 2})`)
    const shape = (i: number, vars: { sx?: number; sy?: number }, when: number, duration: number, ease: string) =>
      tl.to(tube[i], { ...vars, duration, ease, onUpdate: applyTube(i) }, when)
    FRONTS.forEach((_, i) => tl.fromTo(tube[i], { sx: i ? 0 : 1, sy: i ? 0.04 : 1 }, { sx: i ? 0 : 1, sy: i ? 0.04 : 1, duration: 0.01, onUpdate: applyTube(i) }, 0))
    tl.set(at('.feed'), { y: 0 }, 0)
    tl.set(at('.round'), { text: `round ${START}` }, 0)
    tl.set(at('.stopper'), { autoAlpha: 0 }, 0)
    drawPlane(tl, q, 0, { duration: 2.4 })

    // 0 · one terminal, one run, held apart from it. The camera is close on the pair.
    tl.addLabel('beat-0', 0)
    tl.fromTo(cam, { s: aimed.s * 1.08, x: l.w / 2 - focus.x * aimed.s * 1.08, y: l.h / 2 - focus.y * aimed.s * 1.08 }, { ...aimed, duration: 2.4, ease: 'cine', onUpdate: applyCam }, 0)
    tl.fromTo(at('.host-line'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.6, ease: 'cine' }, 0)
    tl.fromTo(at('.link-0'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1, ease: 'cine' }, 0.4)
    tl.fromTo(at('.core-halo'), { scale: 0.6, autoAlpha: 0, transformOrigin: '50% 50%' }, { scale: 1, autoAlpha: 1, duration: 1.2 }, 0.2)

    // The run's rounds, turning over whoever is reading. It stops at the stop.
    const STOP = 19.6
    const EVERY = 1.35
    tl.fromTo(at('.ring'), { rotation: 0 }, { rotation: 360 * 3, duration: STOP, ease: 'none', transformOrigin: '50% 50%' }, 0)
    tl.to(at('.ring'), { rotation: `+=${40}`, duration: 1.2, ease: 'power3.out' }, STOP)

    // Who is connected when: alice, but not between the close and the return; the rest from
    // the moment they arrive.
    const CLOSE = 3.1
    const OPEN = 6.2
    const ARRIVE = 9.4
    const live = (i: number, t: number) => (i === 0 ? t < CLOSE || t > OPEN + 0.6 : t > ARRIVE + 1)
    let n = START
    for (let t = 0.9; t < STOP - 0.2; t += EVERY) {
      n += 1
      tl.set(at('.round'), { text: `round ${n}` }, t)
      // The count turns over: the new number drops in from above.
      tl.fromTo(at('.round-roll'), { y: -5, autoAlpha: 0.35 }, { y: 0, autoAlpha: 1, duration: 0.35, ease: 'cine.out', immediateRender: false }, t)
      tl.fromTo(at('.core-pulse'), { scale: 1, autoAlpha: 0.8, transformOrigin: '50% 50%' }, { scale: 1.9, autoAlpha: 0, duration: 1, ease: 'power2.out' }, t)
      FRONTS.forEach((_, i) => {
        if (live(i, t)) along(links[i], () => hue(i), t, { reverse: true, duration: 0.9, burst: 4 })
      })
    }

    // 1 · the terminal goes dark and its link lets go. The run does not notice.
    tl.addLabel('beat-1', CLOSE - 0.5)
    shape(0, { sy: 0.04 }, CLOSE, 0.2, 'power2.in')
    shape(0, { sx: 0 }, CLOSE + 0.2, 0.18, 'power2.in')
    tl.call(() => {
      const s = screen({ x: l.wins[0].x + l.winW / 2, y: l.wins[0].y + l.winH / 2 })
      fx?.spark(s.x, s.y, hue(0), 14, 60)
    }, [], CLOSE + 0.35)
    tl.to(at('.link-0'), { drawSVG: '100% 100%', duration: 0.8, ease: 'cine' }, CLOSE + 0.2)
    tl.to(at('.gone'), { autoAlpha: 1, duration: 0.4 }, CLOSE + 0.6)

    // 2 · hmz in the same directory: a new interface, and the run read to it from the top.
    tl.addLabel('beat-2', OPEN - 0.4)
    tl.to(at('.gone'), { autoAlpha: 0, duration: 0.3 }, OPEN - 0.2)
    tl.set(win(0, '.body'), { autoAlpha: 0 }, OPEN - 0.2)
    shape(0, { sx: 1 }, OPEN, 0.2, 'power2.out')
    shape(0, { sy: 1 }, OPEN + 0.2, 0.25, 'power2.out')
    tl.fromTo(at('.link-0'), { drawSVG: '0% 0%' }, { drawSVG: '0% 100%', duration: 0.6, ease: 'cine' }, OPEN + 0.3)
    tl.set(win(0, '.body'), { autoAlpha: 1 }, OPEN + 0.45)
    tl.to(win(0, '.replay'), { autoAlpha: 1, duration: 0.2 }, OPEN + 0.5)
    tl.fromTo(win(0, '.replay-spin'), { rotation: 0 }, { rotation: 720, duration: 1.5, ease: 'power2.inOut', transformOrigin: '50% 50%' }, OPEN + 0.5)
    tl.fromTo(win(0, '.feed'), { y: 0 }, { y: -64, duration: 1.4, ease: 'power2.inOut' }, OPEN + 0.5)
    for (let k = 0; k < 7; k += 1) along(links[0], () => hue(0), OPEN + 0.5 + k * 0.12, { reverse: true, duration: 0.5 })
    tl.to(win(0, '.replay'), { autoAlpha: 0, duration: 0.3 }, OPEN + 2)

    // 3 · the camera pulls back: three more frontends on the same run.
    tl.addLabel('beat-3', ARRIVE - 0.6)
    tl.to(cam, { s: 1, x: 0, y: 0, duration: 1.8, ease: 'cine', onUpdate: applyCam }, ARRIVE - 0.6)
    ;[1, 2, 3].forEach((i, k) => {
      const t = ARRIVE + k * 0.25
      tl.to(win(i), { autoAlpha: 1, duration: 0.01 }, t)
      shape(i, { sx: 1 }, t, 0.2, 'power2.out')
      shape(i, { sy: 1 }, t + 0.2, 0.25, 'power2.out')
      tl.to(at(`.link-${i}`), { autoAlpha: 1, duration: 0.01 }, t + 0.3)
      tl.fromTo(at(`.link-${i}`), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.6, ease: 'cine' }, t + 0.3)
    })

    // 4 · the roles appear; bob and carol claim one each. The reviewer asks: every frontend
    // sees it, and the one who claimed it answers.
    const T4 = 12.6
    tl.addLabel('beat-4', T4)
    tl.fromTo(at('.role'), { autoAlpha: 0, y: -8 }, { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.15 }, T4)
    ROLES.forEach((role, r) => {
      const t = T4 + 0.8 + r * 0.9
      tl.to(at(`.claim-${r}`), { autoAlpha: 1, duration: 0.01 }, t)
      tl.fromTo(at(`.claim-${r}`), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.7, ease: 'cine' }, t)
      tl.fromTo(at(`.owner-${r}`), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, t + 0.6)
      tl.call(() => {
        const s = screen({ x: l.roles[r].x, y: l.roles[r].y })
        fx?.spark(s.x, s.y, hue(role.by), 16, 70)
      }, [], t + 0.65)
    })
    const ASK = T4 + 3
    tl.fromTo(at('.ask'), { autoAlpha: 0, scale: 0.5, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(2.5)' }, ASK)
    FRONTS.forEach((_, i) => along(links[i], () => palette.warm, ASK + 0.3, { reverse: true, duration: 0.8, burst: 6 }))
    along(at('.claim-1')[0] as SVGPathElement, () => hue(1), ASK + 1.3, { duration: 0.8, burst: 18 })
    tl.to(at('.ask'), { autoAlpha: 0, scale: 0.6, duration: 0.3 }, ASK + 2.1)
    tl.addLabel('rest', ASK + 0.9)

    // 5 · alice stops it: the run halts, and every frontend is told who stopped it.
    const T5 = STOP - 1
    tl.addLabel('beat-5', T5)
    tl.fromTo(win(0, '.frame'), { strokeWidth: 1.3 }, { strokeWidth: 3, duration: 0.2, yoyo: true, repeat: 1 }, T5 + 0.2)
    along(links[0], () => palette.danger, T5 + 0.3, { duration: 0.7 })
    // Who stopped it travels with the stop: alice's name goes in to the run, and out from it to
    // every frontend, where it is the line each is told.
    const stoppers = at('.stopper')
    tl.set(stoppers[0], { autoAlpha: 1 }, T5 + 0.3)
    tl.fromTo(stoppers[0], { x: port(0).x, y: port(0).y }, { motionPath: { path: links[0] }, duration: 0.7, ease: 'power1.inOut', immediateRender: false }, T5 + 0.3)
    tl.to(stoppers[0], { autoAlpha: 0, duration: 0.2 }, STOP - 0.05)
    FRONTS.forEach((_, i) => {
      const ghost = stoppers[i + 1]
      const t = STOP + 0.1 + i * 0.06
      tl.set(ghost, { autoAlpha: 1 }, t)
      tl.fromTo(ghost, { x: l.core.x, y: l.core.y }, { motionPath: { path: links[i], start: 1, end: 0 }, duration: 0.55, ease: 'cine', immediateRender: false }, t)
      tl.to(ghost, { autoAlpha: 0, duration: 0.15 }, t + 0.5)
    })
    tl.to(at('.core-stop'), { autoAlpha: 1, duration: 0.5 }, STOP)
    tl.to(at('.core-live'), { autoAlpha: 0, duration: 0.5 }, STOP)
    tl.fromTo(at('.wave'), { autoAlpha: 0.9, scale: 0.3, transformOrigin: '50% 50%' }, { autoAlpha: 0, scale: 1, duration: 1.4, ease: 'power2.out' }, STOP)
    tl.call(() => {
      const s = screen(l.core)
      fx?.spark(s.x, s.y, palette.danger, 40, 160)
    }, [], STOP)
    tl.to(at('.link, .claim'), { opacity: 0.25, duration: 0.8 }, STOP + 0.3)
    tl.to(at('.role, .owner'), { opacity: 0.4, duration: 0.8 }, STOP + 0.3)
    FRONTS.forEach((_, i) => {
      const t = STOP + 0.55 + i * 0.06
      tl.to(win(i, '.body'), { autoAlpha: 0, duration: 0.2 }, t)
      tl.fromTo(win(i, '.stopped'), { autoAlpha: 0, x: -6 }, { autoAlpha: 1, x: 0, duration: 0.35 }, t + 0.1)
    })

    const END = STOP + 3.4
    tl.to(worldEl, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, END)
    tl.set(worldEl, { autoAlpha: 1 }, 0)
    tl.set(at('.link, .claim, .role, .owner'), { opacity: 1 }, END + 0.65)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="36 / 47"
    label="A run held by a host of its own, one per directory, with one terminal reading it. The terminal closes and the run goes on turning rounds. hmz in the same directory opens a new interface, and the run is read to it from the top. Three more frontends attach to the same run: bob and carol at terminals, and a bot on the SDK. Carol claims the planner and bob the reviewer; the reviewer asks a question, every frontend sees it, and bob answers. Then alice stops the run, and every frontend is told she stopped it."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <radialGradient id="daemon-core">
          <stop offset="0" stop-color="var(--hmz-accent)" stop-opacity="0.55" />
          <stop offset="1" stop-color="var(--hmz-accent)" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="daemon-core-fill">
          <stop offset="0" stop-color="var(--hmz-accent)" />
          <stop offset="1" stop-color="var(--hmz-lane-1)" />
        </radialGradient>
        <clipPath v-for="(f, i) in FRONTS" :id="`daemon-body-${i}`" :key="f.name">
          <rect x="8" y="24" :width="L.winW - 16" :height="L.winH - 30" />
        </clipPath>
      </defs>
      <g class="world">
        <ScenePlane :key="`plane-${narrow}`" :w="L.w" :h="L.h" :ox="L.core.x" :oy="L.core.y" :step="narrow ? 28 : 32" />
        <!-- the host, the run in it, and its roles -->
        <rect class="host-bg" :x="L.host.x" :y="L.host.y" :width="L.host.w" :height="L.host.h" rx="18" />
        <rect class="host-line" :x="L.host.x" :y="L.host.y" :width="L.host.w" :height="L.host.h" rx="18" />
        <text class="t-host" :x="L.host.x + 16" :y="L.host.y + 22">host · this directory</text>

        <path v-for="(f, i) in FRONTS" :key="`l${i}`" class="link" :class="`link-${i}`" :d="link(i)" :style="{ stroke: f.hue }" />
        <path v-for="(r, k) in ROLES" :key="`c${k}`" class="claim" :class="`claim-${k}`" :d="claim(k)" :style="{ stroke: FRONTS[r.by].hue }" />

        <g :transform="`translate(${L.core.x} ${L.core.y})`">
          <circle class="core-halo" r="110" fill="url(#daemon-core)" />
          <circle class="core-pulse wave-line" r="40" />
          <g class="ring"><circle class="ring-line" r="52" /></g>
          <circle class="core-live" r="32" fill="url(#daemon-core-fill)" />
          <circle class="core-stop" r="32" />
          <text class="t-core" y="5" text-anchor="middle">run</text>
          <circle class="wave" r="280" />
        </g>
        <g class="round-roll"><text class="t-round round" :x="L.round.x" :y="L.round.y" text-anchor="middle">round {{ START }}</text></g>

        <g v-for="(r, k) in ROLES" :key="r.name" :transform="`translate(${L.roles[k].x} ${L.roles[k].y})`">
          <g class="role">
            <rect x="-44" y="-12" width="88" height="24" rx="12" />
            <text y="4.5" text-anchor="middle">{{ r.name }}</text>
          </g>
          <g class="owner" :class="`owner-${k}`">
            <text y="30" text-anchor="middle" :style="{ fill: FRONTS[r.by].hue }">{{ FRONTS[r.by].name }}'s</text>
          </g>
          <g v-if="k === 1" class="ask"><circle cx="44" cy="-12" r="10" /><text x="44" y="-7.5" text-anchor="middle">?</text></g>
        </g>

        <!-- the frontends -->
        <g v-for="(f, i) in FRONTS" :key="f.name" :transform="`translate(${L.wins[i].x} ${L.wins[i].y})`">
          <text v-if="i === 0" class="gone t-gone" :x="L.winW / 2" :y="L.winH / 2 + 4" text-anchor="middle">terminal closed</text>
          <g class="win" :class="`win-${i}`"><g class="win-in">
            <rect class="win-bg" :width="L.winW" :height="L.winH" rx="9" />
            <rect class="frame" :width="L.winW" :height="L.winH" rx="9" :style="{ stroke: f.hue }" />
            <template v-if="!f.sdk">
              <circle cx="12" cy="12" r="2.6" class="dot" />
              <circle cx="21" cy="12" r="2.6" class="dot" />
              <circle cx="30" cy="12" r="2.6" class="dot" />
            </template>
            <text v-else class="t-brace" x="9" y="16" :style="{ fill: f.hue }">{ }</text>
            <text class="t-name" x="40" y="16" :style="{ fill: f.hue }">{{ f.name }}</text>
            <g v-if="i === 0" class="replay" :transform="`translate(${L.winW - 16} 12)`"><g class="replay-spin">
              <path class="t-replay-arc" d="M 5 0 A 5 5 0 1 1 0 -5" />
              <path class="t-replay-tip" d="M -2.5 -7.5 L 1.5 -5 L -2.5 -2.5 Z" />
            </g></g>
            <g :clip-path="`url(#daemon-body-${i})`">
              <g class="body"><g class="feed">
                <rect
                  v-for="k in 12"
                  :key="k"
                  class="skel"
                  :x="12"
                  :y="28 + (k - 1) * 8"
                  :width="(L.winW - 30) * [0.8, 0.55, 0.7, 0.45, 0.9, 0.6, 0.75, 0.5, 0.85, 0.65, 0.4, 0.7][k - 1]"
                  height="3.5"
                  rx="1.75"
                  :style="{ fill: k % 3 === 0 ? f.hue : undefined }"
                />
              </g></g>
              <text class="stopped t-stopped" x="12" :y="L.winH - 16">stopped by alice@tui</text>
            </g>
          </g></g>
        </g>

        <!-- who stopped it, on its way -->
        <g v-for="k in FRONTS.length + 1" :key="`s${k}`" class="stopper">
          <rect x="-36" y="-10" width="72" height="20" rx="10" />
          <text y="4" text-anchor="middle">alice@tui</text>
        </g>
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.host-bg {
  fill: color-mix(in srgb, var(--hmz-accent) 4%, transparent);
}

.host-line {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.4;
  stroke-dasharray: 5 4;
}

.t-host {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.link,
.claim {
  fill: none;
  stroke-width: 1.6;
  stroke-opacity: 0.7;
}

.claim {
  stroke-dasharray: 4 4;
  stroke-width: 1.4;
}

.core-halo {
  opacity: var(--hmz-glow);
}

.wave-line {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.5;
  opacity: 0;
}

.ring-line {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-dasharray: 3 9;
  stroke-linecap: round;
}

.core-stop {
  fill: var(--hmz-lane-6);
}

.t-core {
  font-size: 14px;
  font-weight: 700;
  fill: var(--vp-c-bg);
}

.wave {
  fill: none;
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
}

.t-round {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.role rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.role text {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.owner text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
}

.ask circle {
  fill: var(--hmz-warm);
}

.ask text {
  font-size: 13px;
  font-weight: 800;
  fill: var(--vp-c-bg);
}

.stopper {
  visibility: hidden;
}

.stopper rect {
  fill: color-mix(in srgb, var(--hmz-lane-5) 18%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-5);
  stroke-width: 1.4;
}

.stopper text {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.win-bg {
  fill: var(--hmz-stage-card);
}

.frame {
  fill: none;
  stroke-width: 1.3;
}

.dot {
  fill: var(--hmz-stage-line);
}

.t-name,
.t-brace {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
}

.t-replay-arc {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.8;
  stroke-linecap: round;
}

.t-replay-tip {
  fill: var(--hmz-accent);
}

.skel {
  fill: var(--hmz-stage-line);
}

.t-stopped {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 600;
  fill: var(--hmz-lane-5);
}

.t-gone {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-dim);
  opacity: 0;
}
</style>
