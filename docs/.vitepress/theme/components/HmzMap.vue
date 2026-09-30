<script setup lang="ts">
// Everything humanize does, by what the reader is trying to do, each item a link to the page
// that does it. The areas and items are the sections and rows of `features/capabilities.md`,
// one for one: add a row there and it is an item here, in the same place. The scene flies each
// area in, in turn, then settles on the whole map and stays there, since it is something to
// click, not to watch. It is on the features index too, so every id in it is its own.
import { computed, nextTick, onMounted, onUnmounted, ref, useId } from 'vue'
import { withBase } from 'vitepress'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, type Fx } from '../motion/fx'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'

interface Item {
  name: string
  link: string
}

interface Area {
  code: string
  name: string
  items: Item[]
}

const AREAS: Area[] = [
  {
    code: 'A',
    name: 'Run it your way',
    items: [
      { name: 'Ready-made loops', link: '/flows/' },
      { name: 'Any coding agent', link: '/user/settings#accounts' },
      { name: 'Model and effort', link: '/user/efforts' },
      { name: 'Two accounts of one CLI', link: '/user/settings#accounts' },
      { name: 'Fall back', link: '/user/settings#fallback' },
      { name: 'Skills', link: '/user/skills' },
      { name: 'From a script', link: '/user/unattended' },
      { name: 'In CI', link: '/user/ci' },
      { name: 'From Python', link: '/reference/sdk' },
    ],
  },
  {
    code: 'B',
    name: 'While it runs',
    items: [
      { name: 'Talk into a turn', link: '/user/steering' },
      { name: 'Side questions', link: '/user/btw' },
      { name: 'Watch every agent', link: '/user/monitor' },
      { name: 'Answer, or step away', link: '/user/questions' },
      { name: 'What it costs', link: '/user/tally' },
      { name: 'A budget on every run', link: '/user/unattended' },
      { name: 'Stop it', link: '/user/stopping' },
      { name: 'Leave it running', link: '/reference/daemon' },
    ],
  },
  {
    code: 'C',
    name: 'Where the work lands',
    items: [
      { name: 'In a container', link: '/user/containers' },
      { name: 'On another machine', link: '/user/remote-execution' },
      { name: 'What an agent may touch', link: '/user/permissions' },
    ],
  },
  {
    code: 'D',
    name: 'After a run',
    items: [
      { name: 'Pick it up', link: '/user/resuming' },
      { name: 'One timeline', link: '/user/tracing' },
      { name: 'Hand it to somebody', link: '/user/export' },
      { name: 'Crash reports', link: '/user/reporting' },
    ],
  },
  {
    code: 'E',
    name: 'Writing a flow',
    items: [
      { name: 'A loop in plain Python', link: '/weaver/writing-a-flow' },
      { name: 'Params of its own', link: '/weaver/flow-settings' },
      { name: 'Many conversations at once', link: '/weaver/async-flows' },
      { name: 'Answers as typed data', link: '/weaver/shapes' },
      { name: 'The agent decides it is done', link: '/weaver/goals' },
      { name: 'React to each moment', link: '/weaver/hooks' },
      { name: 'Tools that call the flow', link: '/weaver/tools' },
      { name: 'Ask the person', link: '/weaver/human-agent' },
      { name: 'Cap a single turn', link: '/reference/flows' },
      { name: 'Call another flow', link: '/weaver/calling-flows' },
      { name: 'Branch a conversation', link: '/weaver/branching' },
      { name: 'Worktrees and copies', link: '/weaver/worktrees' },
      { name: 'Test without a model', link: '/weaver/testing-flows' },
      { name: 'Publish it', link: '/weaver/flowverses' },
    ],
  },
]

const BEATS = [...AREAS.map((area) => area.name), 'Open any one for its page']

const uid = useId()
const areaId = (code: string) => `${uid}-map-${code}`

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
const cam = ref<HTMLElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())

// The screen takes the map's own shape, so the whole of it is legible once it settles.
const ratio = ref('16 / 9')
const mobileRatio = ref('3 / 5')

interface Box {
  x: number
  y: number
  w: number
  h: number
}

const scene = useScene({
  still: 'rest',
  loop: false,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const view = cam.value
    const screen = view?.parentElement
    if (!view || !screen) return
    const W = screen.clientWidth
    const H = screen.clientHeight
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, W, H) : undefined
    fx?.clear()

    // Where everything sits in the map, measured flat, before the camera moves.
    const origin = view.getBoundingClientRect()
    const box = (el: Element): Box => {
      const r = el.getBoundingClientRect()
      return { x: r.left - origin.left, y: r.top - origin.top, w: r.width, h: r.height }
    }
    const areas = q('.area')
    const areaBox = areas.map(box)
    const shot = (b: Box | null) => {
      if (!b || narrow.value) return { x: 0, y: 0, scale: 1 }
      const s = Math.min((W * 0.84) / b.w, (H * 0.8) / b.h, 1.45)
      return { x: W / 2 - (b.x + b.w / 2) * s, y: H / 2 - (b.y + b.h / 2) * s, scale: s }
    }
    // A point of the map, on the screen, under a given shot.
    const on = (p: { x: number; y: number }, s: { x: number; y: number; scale: number }) => ({ x: s.x + p.x * s.scale, y: s.y + p.y * s.scale })

    tl.set(view, { transformOrigin: '0 0', ...shot(areaBox[0]) }, 0)
    tl.set(q('.item'), { opacity: 0, z: -420, y: 24, rotationX: -35 }, 0)
    tl.set(q('.code'), { scale: 0 }, 0)
    tl.set(q('.area-name'), { opacity: 0, x: -12 }, 0)
    tl.set(areas, { opacity: 0.18, filter: 'blur(2px)' }, 0)
    tl.set(q('.shine'), { opacity: 0 }, 0)

    let t = 0
    areas.forEach((area, k) => {
      const s = shot(areaBox[k])
      tl.addLabel(`beat-${k}`, t)
      if (k) tl.to(view, { ...s, duration: 1.2, ease: 'cine' }, t)
      // Depth of field: this area sharp and lit, the others soft.
      areas.forEach((other, j) => {
        if (j === k) tl.to(other, { opacity: 1, filter: 'blur(0px)', duration: 0.7, ease: 'power2.out' }, t + 0.2)
        else if (j < k) tl.to(other, { opacity: 0.4, filter: 'blur(1.5px)', duration: 0.7 }, t + 0.1)
      })
      const code = area.querySelector('.code')!
      tl.to(code, { scale: 1, duration: 0.5, ease: 'back.out(3)' }, t + 0.35)
      tl.to(area.querySelector('.area-name'), { opacity: 1, x: 0, duration: 0.5 }, t + 0.45)
      const from = on({ x: box(code).x + box(code).w / 2, y: box(code).y + box(code).h / 2 }, s)
      tl.call(() => fx?.spark(from.x, from.y, palette.lane[k], 18, 90), [], t + 0.45)
      const items = Array.from(area.querySelectorAll('.item'))
      items.forEach((item, i) => {
        const at = t + 0.6 + i * 0.07
        tl.to(item, { opacity: 1, z: 0, y: 0, rotationX: 0, duration: 0.7, ease: 'cine.out' }, at)
        const b = box(item)
        const to = on({ x: b.x + b.w / 2, y: b.y + b.h / 2 }, s)
        // A streak from the area's badge to the item as it lands.
        const p = { t: 0 }
        tl.fromTo(
          p,
          { t: 0 },
          {
            t: 1,
            duration: 0.45,
            ease: 'power2.in',
            onUpdate: () => fx?.trail(from.x + (to.x - from.x) * p.t, from.y + (to.y - from.y) * p.t, palette.lane[k], 2),
            onComplete: () => fx?.spark(to.x, to.y, palette.lane[k], 5, 50),
          },
          at,
        )
      })
      t += 0.6 + items.length * 0.07 + 1.3
    })

    // The whole map, sharp, a light passing over every item, and then it stays.
    tl.addLabel(`beat-${areas.length}`, t)
    tl.to(view, { x: 0, y: 0, scale: 1, duration: 1.5, ease: 'cine' }, t)
    tl.to(areas, { opacity: 1, filter: 'blur(0px)', duration: 0.8 }, t + 0.3)
    const shines = q('.shine')
    tl.to(shines, { opacity: 1, duration: 0.25, stagger: 0.025 }, t + 1.2)
    tl.to(shines, { opacity: 0, duration: 0.5, stagger: 0.025 }, t + 1.45)
    tl.addLabel('rest', t + 1.45 + shines.length * 0.025 + 0.5)
    // Leave no filter behind: a blur of nothing still costs the page a layer.
    tl.set(areas, { clearProps: 'filter' }, 'rest')
  },
})

// Size the screen to the map: its width is the page's, its height the map's at that width.
let observer: ResizeObserver | undefined
let pending = 0
function fit() {
  cancelAnimationFrame(pending)
  pending = requestAnimationFrame(() => {
    const view = cam.value
    const screen = view?.parentElement
    if (!view || !screen) return
    const next = `${Math.round(screen.clientWidth)} / ${Math.ceil(view.offsetHeight)}`
    const was = narrow.value ? mobileRatio.value : ratio.value
    if (next === was) return
    if (narrow.value) mobileRatio.value = next
    else ratio.value = next
    void nextTick(() => scene.rebuild())
  })
}

onMounted(() => {
  void nextTick(fit)
  observer = new ResizeObserver(fit)
  if (cam.value) observer.observe(cam.value)
  if (cam.value?.parentElement) observer.observe(cam.value.parentElement)
})

onUnmounted(() => {
  observer?.disconnect()
  cancelAnimationFrame(pending)
  fx?.destroy()
})

const label = computed(
  () =>
    `Everything humanize does, in ${AREAS.length} areas: ${AREAS.map((area) => `${area.name}, ${area.items.map((item) => item.name).join(', ')}`).join('; ')}. Each item links to the page that does it.`,
)
</script>

<template>
  <HmzStage :scene="scene" :beats="BEATS" :label="label" interactive :ratio="ratio" :mobile-ratio="mobileRatio">
    <div class="layer depth">
      <div ref="cam" class="cam">
        <section
          v-for="(area, a) in AREAS"
          :key="area.code"
          class="area"
          :class="`area-${area.code}`"
          :style="{ '--tone': `var(--hmz-lane-${a + 1})` }"
          :aria-labelledby="areaId(area.code)"
        >
          <header>
            <span class="code" aria-hidden="true">{{ area.code }}</span>
            <strong :id="areaId(area.code)" class="area-name">{{ area.name }}</strong>
          </header>
          <div class="items">
            <a v-for="item in area.items" :key="item.name" class="item" :href="withBase(item.link)">
              <span class="shine" aria-hidden="true" />
              {{ item.name }}
            </a>
          </div>
        </section>
      </div>
    </div>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
.depth {
  perspective: 900px;
  overflow: hidden;
}

.cam {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-template-areas:
    'a b c'
    'a b d'
    'e e e';
  align-content: start;
  gap: 10px;
  padding: 16px 14px 14px;
  transform-style: preserve-3d;
  will-change: transform;
}

.area-A {
  grid-area: a;
}

.area-B {
  grid-area: b;
}

.area-C {
  grid-area: c;
}

.area-D {
  grid-area: d;
}

.area-E {
  grid-area: e;
}

.area {
  padding: 10px 10px 12px;
  border: 1px solid color-mix(in srgb, var(--tone) 32%, transparent);
  border-radius: 12px;
  background: color-mix(in srgb, var(--tone) 7%, transparent);
  /* Its own lens: the blur that softens an area flattens it, so the depth is set here. */
  perspective: 700px;
}

header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.code {
  display: grid;
  place-items: center;
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  background: var(--tone);
  color: var(--hmz-stage-card);
  font-size: 11px;
  font-weight: 800;
  box-shadow: 0 0 calc(16px * var(--hmz-glow)) color-mix(in srgb, var(--tone) 70%, transparent);
}

.area-name {
  font-size: 13.5px;
  line-height: 1.3;
  color: var(--hmz-stage-ink);
}

.items {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.vp-doc .item,
.item {
  position: relative;
  overflow: hidden;
  padding: 3px 10px;
  border: 1px solid var(--hmz-stage-line);
  border-radius: 999px;
  background: var(--hmz-stage-card);
  color: var(--hmz-stage-ink);
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.5;
  text-decoration: none;
  transition: border-color 0.2s, color 0.2s, box-shadow 0.2s;
}

.vp-doc .item:hover,
.item:hover {
  border-color: var(--tone);
  color: var(--hmz-stage-ink);
  box-shadow: 0 0 0 1px var(--tone), 0 0 calc(18px * var(--hmz-glow)) color-mix(in srgb, var(--tone) 55%, transparent);
  text-decoration: none;
}

.item:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.shine {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(100deg, transparent 10%, color-mix(in srgb, var(--tone) 45%, transparent) 50%, transparent 90%);
  pointer-events: none;
}

@media (max-width: 640px) {
  .cam {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'a' 'b' 'c' 'd' 'e';
    padding: 12px 10px 12px;
    gap: 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .item {
    transition: none;
  }
}
</style>
