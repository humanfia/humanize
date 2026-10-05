<script setup lang="ts">
// The drawing beside the hero's words: the humanize mark, `>_`, put together from its planes
// the way a constructivist poster is -- a ruled sheet, one circle, and one diagonal that every
// other piece is set against -- and then put to work.
//
// It is drawn on a 600 x 600 sheet. The diagonal is the top edge of the red wedge, the `_`,
// carried right across the sheet: everything that moves later moves along it.
//
// - It builds once, on arrival: the sheet is ruled, the circle drawn, the chevron's two arms
//   slide in along their own axes and lock, the wedge rises in on the diagonal, and the drawing
//   labels itself.
// - Then it keeps working, quietly: turns travel up the diagonal into the wedge and the counter
//   under it ticks over; the ring round the circle turns. That loop runs only while the hero
//   is on screen and the tab is showing.
// - Scrolling away takes it apart a little -- the planes drift off along their axes -- and
//   scrolling back puts it together. It follows the scroll; it never holds it.
// - Under reduced motion it is the finished drawing, still.
//
// Every colour is a custom property, so the reader's light/dark switch recolours it as it is.
import { nextTick, onMounted, onUnmounted, ref } from 'vue'

import { motion } from '../../motion/gsap'
import { probe } from '../../motion/probe'

const root = ref<SVGSVGElement | null>(null)
const turn = ref('01')

// The mark in its own 100-unit box, as `public/logo.svg` draws it, and where it sits on the
// sheet: scaled 3.6 and moved to (100, 140).
const UPPER = '12,16 32,16 62,50 42,50'
const LOWER = '42,50 62,50 32,84 12,84'
const WEDGE = '60,84 94,84 94,64 60,74'
const K = 3.6
const AT = { x: 100, y: 140 }
const on = (x: number, y: number) => ({ x: AT.x + x * K, y: AT.y + y * K })

// The diagonal: the wedge's top edge, (60,74) to (94,64), carried across the sheet.
const A = on(60, 74)
const B = on(94, 64)
const SLOPE = (B.y - A.y) / (B.x - A.x)
const lineY = (x: number) => A.y + (x - A.x) * SLOPE
const ANGLE = (Math.atan(-SLOPE) * 180) / Math.PI

/** A point on the arc that measures the diagonal, `r` from where it is measured. */
const arc = (r: number) => {
  const t = (ANGLE * Math.PI) / 180
  return `M ${B.x + r} ${B.y} A ${r} ${r} 0 0 0 ${B.x + r * Math.cos(t)} ${B.y - r * Math.sin(t)}`
}

const RULE = [60, 120, 180, 240, 300, 360, 420, 480, 540]
const TICKS = Array.from({ length: 29 }, (_, i) => 20 + i * 20)
const DISC = { x: 452, y: 150, r: 74 }

let context: gsap.Context | undefined
let watching: IntersectionObserver | undefined
let unprobe: (() => void) | undefined
let sync: (() => void) | undefined

onMounted(() => {
  void nextTick(() => {
    const svg = root.value
    if (!svg) return
    const gsap = motion()
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let intro: gsap.core.Timeline | undefined
    let loop: gsap.core.Timeline | undefined
    let spin: gsap.core.Tween | undefined

    context = gsap.context((self) => {
      const q = (s: string) => self.selector!(s) as Element[]
      const one = (s: string) => q(s)[0]

      // --- the build ------------------------------------------------------------------------
      intro = gsap.timeline({ paused: true })
      intro.set(q('.hair, .tick, .guide, .lead, .ring-line'), { drawSVG: '0%' }, 0)
      intro.set(q('.note, .reg, .num'), { autoAlpha: 0 }, 0)

      // The sheet is ruled from the middle out, and the rulers ticked along two edges.
      intro.to(q('.hair'), { drawSVG: '100%', duration: 1.1, ease: 'cine', stagger: { each: 0.05, from: 'center' } }, 0)
      intro.to(q('.tick'), { drawSVG: '100%', duration: 0.3, ease: 'none', stagger: 0.012 }, 0.2)
      intro.to(q('.num'), { autoAlpha: 1, duration: 0.4, stagger: 0.06 }, 0.6)
      intro.fromTo(q('.reg'), { autoAlpha: 0, scale: 0.3, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.6, stagger: 0.08, ease: 'back.out(2)' }, 0.25)

      // The circle: a compass line first, then the disc inside it.
      intro.to(one('.ring-line'), { drawSVG: '100%', duration: 1.3, ease: 'cine' }, 0.35)
      intro.fromTo(one('.disc'), { scale: 0, transformOrigin: '50% 50%' }, { scale: 1, duration: 0.9, ease: 'back.out(1.6)' }, 0.85)

      // The plane under the diagonal slides in along it, from off the sheet.
      intro.fromTo(one('.plane'), { x: -420, y: -420 * SLOPE, autoAlpha: 0 }, { x: 0, y: 0, autoAlpha: 1, duration: 1.3, ease: 'cine.out' }, 0.5)
      intro.fromTo(one('.axis'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.2, ease: 'cine' }, 0.6)

      // The chevron's arms, each along its own axis, meeting at the point and locking there.
      intro.fromTo(one('.upper'), { x: -64, y: -72, autoAlpha: 0 }, { x: 0, y: 0, autoAlpha: 1, duration: 0.9, ease: 'cine.out' }, 1.15)
      intro.fromTo(one('.lower'), { x: -64, y: 72, autoAlpha: 0 }, { x: 0, y: 0, autoAlpha: 1, duration: 0.9, ease: 'cine.out' }, 1.3)
      intro.fromTo(q('.spark'), { drawSVG: '0% 0%', autoAlpha: 1 }, { drawSVG: '60% 100%', autoAlpha: 0, duration: 0.6, ease: 'power2.out', stagger: 0.03 }, 2.0)
      intro.fromTo(one('.lock'), { scale: 0.4, autoAlpha: 0.9, transformOrigin: '50% 50%' }, { scale: 1.8, autoAlpha: 0, duration: 0.7, ease: 'power2.out' }, 2.0)

      // The wedge rises in on the diagonal, overshoots, and settles.
      intro.fromTo(one('.wedge'), { x: 26, y: 26 * SLOPE, autoAlpha: 0 }, { x: 0, y: 0, autoAlpha: 1, duration: 1.0, ease: 'back.out(1.4)' }, 2.05)
      intro.set(one('.wedge'), { transformOrigin: '50% 100%' }, 0)
      intro.set(one('.take'), { transformOrigin: '50% 100%', autoAlpha: 0 }, 0)

      // And the drawing labels itself: the angle, and what each part is.
      intro.to(q('.guide'), { drawSVG: '100%', duration: 0.7, ease: 'cine', stagger: 0.12 }, 2.6)
      intro.to(q('.lead'), { drawSVG: '100%', duration: 0.6, ease: 'cine', stagger: 0.15 }, 2.9)
      intro.fromTo(q('.note'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.15 }, 3.0)

      // --- the work, after ----------------------------------------------------------------
      // A turn rides the diagonal up into the wedge; the wedge takes it with a flash and the
      // counter under it ticks over. Three at a time, one of them red.
      const from = { x: -10, y: lineY(-10) }
      const to = { x: A.x - 4, y: lineY(A.x - 4) }
      loop = gsap.timeline({ paused: true, repeat: -1 })
      q('.packet').forEach((p, i) => {
        const t = i * 1.4
        loop!.fromTo(p, { x: from.x, y: from.y - 9, autoAlpha: 0 }, { x: to.x, y: to.y - 9, autoAlpha: 1, duration: 2.6, ease: 'power1.in' }, t)
        loop!.to(p, { autoAlpha: 0, duration: 0.12, ease: 'none' }, t + 2.6)
        loop!.fromTo(one('.take'), { autoAlpha: 0.9, scale: 1 }, { autoAlpha: 0, scale: 1.35, duration: 0.7, ease: 'power2.out', immediateRender: false }, t + 2.6)
        loop!.fromTo(one('.wedge'), { scaleY: 1.12 }, { scaleY: 1, duration: 0.5, ease: 'back.out(3)', immediateRender: false }, t + 2.6)
        loop!.call(() => {
          turn.value = String((Number(turn.value) % 99) + 1).padStart(2, '0')
        }, [], t + 2.62)
      })
      loop.to({}, { duration: 0.6 }, '>')
      spin = gsap.to(one('.spin'), { rotation: 360, svgOrigin: `${DISC.x} ${DISC.y}`, duration: 48, ease: 'none', repeat: -1, paused: true })

      // --- the scroll ---------------------------------------------------------------------
      // Scrolled past, the planes drift apart along their axes; scrolled back, they meet.
      if (!reduced) {
        const hero = svg.closest('section') ?? svg
        const apart = gsap.timeline({ scrollTrigger: { trigger: hero, start: 'top top', end: 'bottom top', scrub: 0.8 } })
        apart.to(one('.s-disc'), { x: 40, y: -70, ease: 'none' }, 0)
        apart.to(one('.s-upper'), { x: -7, y: -8, ease: 'none' }, 0)
        apart.to(one('.s-lower'), { x: -7, y: 8, ease: 'none' }, 0)
        apart.to(one('.s-wedge'), { x: 16, y: 16 * SLOPE, ease: 'none' }, 0)
        apart.to(one('.s-plane'), { x: -80, y: -80 * SLOPE, ease: 'none' }, 0)
        apart.to(one('.s-sheet'), { autoAlpha: 0.35, ease: 'none' }, 0)
      }
    }, svg)

    if (!intro || !loop || !spin) return
    const tl = intro
    const work = loop
    const ring = spin

    if (reduced) {
      tl.progress(1)
      return
    }

    let visible = true
    sync = () => {
      const go = visible && !document.hidden
      if (go && tl.progress() >= 1) {
        work.resume()
        ring.resume()
      } else {
        work.pause()
        ring.pause()
      }
    }
    const resync = sync
    tl.eventCallback('onComplete', resync)
    tl.play(0)
    watching = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      resync()
    })
    watching.observe(svg)
    document.addEventListener('visibilitychange', resync)
    unprobe = probe({
      root: () => svg,
      duration: () => tl.duration(),
      settled: () => [tl.duration()],
      seek: async (t) => {
        tl.pause()
        tl.time(t, false)
        await nextTick()
      },
    })
  })
})

onUnmounted(() => {
  if (sync) document.removeEventListener('visibilitychange', sync)
  unprobe?.()
  watching?.disconnect()
  context?.revert()
})
</script>

<template>
  <svg ref="root" class="scene" viewBox="0 0 600 600" aria-hidden="true">
    <!-- The sheet: ruled, ticked along two edges, marked at its corners. -->
    <g class="s-sheet">
      <line v-for="x in RULE" :key="`v${x}`" class="hair" :x1="x" :x2="x" y1="20" y2="580" />
      <line v-for="y in RULE" :key="`h${y}`" class="hair" :y1="y" :y2="y" x1="20" x2="580" />
      <line v-for="x in TICKS" :key="`tx${x}`" class="tick" :x1="x" :x2="x" y1="592" :y2="x % 120 === 0 ? 578 : 586" />
      <line v-for="y in TICKS" :key="`ty${y}`" class="tick" :y1="y" :y2="y" x1="8" :x2="y % 120 === 0 ? 22 : 14" />
      <text v-for="x in [120, 240, 360, 480]" :key="`n${x}`" class="num" :x="x + 4" y="574">{{ x }}</text>
      <g v-for="[x, y] in [[60, 60], [540, 60], [60, 540], [540, 540]]" :key="`r${x}${y}`" class="reg">
        <circle :cx="x" :cy="y" r="7" />
        <line :x1="x - 12" :x2="x + 12" :y1="y" :y2="y" />
        <line :x1="x" :x2="x" :y1="y - 12" :y2="y + 12" />
      </g>
    </g>

    <!-- The circle, and the ring a red square turns on round it. -->
    <g class="s-disc">
      <circle class="ring-line" :cx="DISC.x" :cy="DISC.y" :r="DISC.r + 26" />
      <g class="spin">
        <rect class="orbit" :x="DISC.x - 5" :y="DISC.y - DISC.r - 31" width="10" height="10" />
        <circle class="ring-dash" :cx="DISC.x" :cy="DISC.y" :r="DISC.r + 14" />
      </g>
      <circle class="disc" :cx="DISC.x" :cy="DISC.y" :r="DISC.r" />
    </g>

    <!-- The diagonal: a plane under it, and the line itself, right across the sheet. -->
    <g class="s-plane">
      <polygon class="plane" :points="`-40,${lineY(-40)} 640,${lineY(640)} 640,${lineY(640) + 64} -40,${lineY(-40) + 64}`" />
    </g>
    <line class="axis" x1="0" :y1="lineY(0)" x2="600" :y2="lineY(600)" />

    <!-- The turns that ride it, and the flash where the wedge takes one. -->
    <rect v-for="i in 3" :key="`p${i}`" class="packet" :class="{ hot: i === 2 }" x="-6" y="-6" width="12" height="12" />

    <!-- The mark. -->
    <g :transform="`translate(${AT.x} ${AT.y}) scale(${K})`">
      <g class="s-upper"><polygon class="upper ink" :points="UPPER" /></g>
      <g class="s-lower"><polygon class="lower ink" :points="LOWER" /></g>
      <g class="s-wedge">
        <polygon class="wedge red" :points="WEDGE" />
        <polygon class="take" :points="WEDGE" />
      </g>
    </g>
    <g :transform="`translate(${on(62, 50).x} ${on(62, 50).y})`">
      <circle class="lock" r="22" />
      <line v-for="a in [-50, -20, 10, 40]" :key="`s${a}`" class="spark" x1="14" y1="0" x2="44" y2="0" :transform="`rotate(${a})`" />
    </g>

    <!-- What the drawing says about itself. -->
    <line class="guide" :x1="B.x" :y1="B.y" :x2="B.x + 110" :y2="B.y" />
    <path class="guide" :d="arc(84)" />
    <text class="note angle" :x="B.x + 92" :y="B.y - 8">{{ ANGLE.toFixed(1) }}°</text>

    <line class="lead" :x1="on(62, 50).x + 6" :y1="on(62, 50).y" :x2="on(62, 50).x + 58" :y2="on(62, 50).y" />
    <text class="note" :x="on(62, 50).x + 64" :y="on(62, 50).y + 4">a prompt goes in</text>

    <line class="lead" :x1="on(77, 84).x" :y1="on(77, 84).y + 6" :x2="on(77, 84).x" :y2="on(77, 84).y + 40" />
    <text class="note" :x="on(77, 84).x - 4" :y="on(77, 84).y + 56" text-anchor="end">the work lands</text>
    <text class="note count" :x="on(77, 84).x + 6" :y="on(77, 84).y + 56">turn {{ turn }}</text>
  </svg>
</template>

<style scoped>
.scene {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
  font-family: var(--vp-font-family-mono);
}

.hair {
  stroke: var(--hmz-con-line);
  stroke-width: 1;
}

.tick,
.reg circle,
.reg line {
  fill: none;
  stroke: var(--hmz-con-mark);
  stroke-width: 1;
}

.num {
  font-size: 11px;
  fill: var(--hmz-con-mark);
}

.ring-line {
  fill: none;
  stroke: var(--hmz-ink);
  stroke-width: 1.2;
}

.ring-dash {
  fill: none;
  stroke: var(--hmz-ink);
  stroke-width: 1;
  stroke-dasharray: 2 7;
  opacity: 0.55;
}

.orbit {
  fill: var(--hmz-red);
}

.disc {
  fill: var(--hmz-red);
}

.plane {
  fill: var(--hmz-con-plane);
}

.axis {
  stroke: var(--hmz-ink);
  stroke-width: 1.2;
  stroke-dasharray: 10 6;
  opacity: 0.5;
}

.packet {
  fill: var(--hmz-ink);
  opacity: 0;
}

.packet.hot {
  fill: var(--hmz-red);
}

.ink {
  fill: var(--hmz-ink);
}

.red {
  fill: var(--hmz-red);
}

.take {
  fill: none;
  stroke: var(--hmz-red);
  stroke-width: 0.6;
  opacity: 0;
}

.lock {
  fill: none;
  stroke: var(--hmz-red);
  stroke-width: 2;
  opacity: 0;
}

.spark {
  stroke: var(--hmz-red);
  stroke-width: 3;
}

.guide,
.lead {
  fill: none;
  stroke: var(--hmz-ink);
  stroke-width: 1;
}

.guide {
  stroke-dasharray: 4 4;
}

.note {
  font-size: 15px;
  fill: var(--hmz-ink);
  letter-spacing: 0.01em;
}

.note.angle,
.note.count {
  fill: var(--hmz-red);
  font-weight: 700;
}

/* Drawn smaller over the words on a narrow screen, where its labels would be too small to
   read: the drawing alone, then. */
@media (max-width: 959px) {
  .note,
  .num,
  .lead {
    display: none;
  }
}
</style>
