<script setup lang="ts">
// A run of one flow, simulated and filmed: <HmzFlow flow="rlar" />, or several with a strip to
// pick between, <HmzFlow pick="ralph_loop,stateful_ralph" />.
//
// The scene comes from `theme/flows.ts` and is drawn only in the grammar of `grammar.ts`, so
// every flow on the site is filmed the same way. A GSAP timeline runs one number, the time in
// beats, and everything on screen -- the turns, the comets, the budget, the camera -- is a
// function of it (see `stage.ts`); so play, pause, a step to the next moment and dragging the
// scrubber are all just that number moving. It stops while scrolled out of sight. Under
// reduced motion nothing moves: the whole run is drawn at rest, every label showing, and the
// step buttons and the scrubber still move through it, a moment at a time, without a camera.
import { gsap } from 'gsap'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'

import { SCENES } from '../../flows'
import FlowScene from './FlowScene.vue'
import { OUTCOME_SAID, SESSION_SAID } from './grammar'
import { cut, direct, film, heightFor, lay, still, type TurnG } from './stage'

const props = defineProps<{
  /** The scene to play, by its key in SCENES. */
  flow?: string
  /** Several of them, as a comma-separated list, with a strip to pick between. */
  pick?: string
}>()

/** Seconds a beat takes. */
const BEAT = 1.6

const offered = computed(() =>
  (props.pick ?? props.flow ?? '')
    .split(',')
    .map((one) => one.trim())
    .filter((one) => one in SCENES),
)
const at = ref(0)
const key = computed(() => offered.value[at.value] ?? offered.value[0] ?? 'ralph_loop')
const layout = computed(() => lay(SCENES[key.value]))

const width = ref(800)
const view = computed(() => ({ w: width.value, h: heightFor(layout.value, width.value) }))
const keys = computed(() => direct(layout.value, view.value))

/** Whether it moves: never on the server, never under reduced motion. */
const motion = ref(false)
/** Under reduced motion, the moment the buttons stepped to, or null for the whole run. */
const manual = ref<number | null>(null)
const clock = reactive({ t: 0 })
const playing = ref(true)
const onScreen = ref(false)
const progress = ref(1)

/** Under reduced motion, a step shows its moment a little way in, and the finish once it has
 *  landed, so that what the step is for is on screen and nothing is caught half-drawn. */
const shown = (at: number) => {
  const L = layout.value
  if (!L.marks.includes(at)) return at
  return at >= L.firedAt ? L.firedAt + 1 : at + 0.3
}
const t = computed(() =>
  motion.value ? clock.t : manual.value === null ? layout.value.firedAt + 1 : shown(manual.value),
)
const mode = computed(() => (motion.value || manual.value !== null ? 'play' : 'still'))
/** The camera: filmed while it moves; under reduced motion the whole run, or a cut straight to
 *  the shot a step lands on. */
const cam = computed(() =>
  motion.value
    ? film(keys.value, clock.t)
    : manual.value === null
      ? still(layout.value, view.value)
      : cut(keys.value, manual.value + 0.01),
)

let tl: gsap.core.Timeline | null = null
let stepping: gsap.core.Tween | null = null

function build() {
  tl?.kill()
  stepping?.kill()
  const L = layout.value
  clock.t = L.start
  tl = gsap.timeline({
    repeat: -1,
    paused: true,
    onUpdate: () => {
      progress.value = tl!.progress()
    },
  })
  tl.fromTo(clock, { t: L.start }, { t: L.end, duration: (L.end - L.start) * BEAT, ease: 'none' })
  apply()
}

function apply() {
  if (!tl) return
  if (playing.value && onScreen.value) tl.play()
  else tl.pause()
}

function toggle() {
  stepping?.kill()
  playing.value = !playing.value
  apply()
}

function restart() {
  if (!motion.value) {
    manual.value = null
    progress.value = 1
    return
  }
  stepping?.kill()
  playing.value = true
  tl?.restart()
  apply()
}

/** The moment before or after now: the start of a turn, the loop, the finish. */
function go(dir: 1 | -1) {
  const L = layout.value
  const marks = L.marks
  const now = motion.value ? clock.t : manual.value ?? L.firedAt + 1
  const next =
    dir > 0
      ? marks.find((m) => m > now + 0.02) ?? marks[0]
      : [...marks].reverse().find((m) => m < now - 0.05) ?? marks[marks.length - 1]
  if (!motion.value) {
    manual.value = next
    progress.value = (next - L.start) / (L.end - L.start)
    return
  }
  playing.value = false
  stepping?.kill()
  tl?.pause()
  stepping = tl?.tweenTo((next - L.start) * BEAT, { duration: 0.8, ease: 'power2.inOut' }) ?? null
}

function scrub(event: Event) {
  const v = Number((event.target as HTMLInputElement).value) / 1000
  const L = layout.value
  progress.value = v
  if (!motion.value) {
    manual.value = L.start + v * (L.end - L.start)
    return
  }
  playing.value = false
  stepping?.kill()
  tl?.pause()
  tl?.progress(v)
}

watch(key, () => {
  manual.value = null
  progress.value = 1
  if (motion.value) build()
})

/* What is happening now, in words: the line under the picture. */
const running = computed(() => layout.value.turns.filter((g) => g.t0 <= t.value && t.value < g.t1))
const nameOf = (g: TurnG) => g.lane.role.name
const now = computed(() => {
  const L = layout.value
  if (mode.value === 'still') return 'The whole run, at rest. Step through it with the buttons, or drag the bar.'
  if (t.value < 0) return `${L.scene.of}: ${L.scene.roles.length === 1 ? 'one lane' : `${L.scene.roles.length} lanes`}.`
  if (t.value >= L.firedAt) {
    const end = L.scene.ends[0]
    return `It ends: ${end.said}${end.is === 'budget' ? '' : ` — ${OUTCOME_SAID[end.is]}`}.`
  }
  const set = running.value
  if (set.length > 1) return `${set.length} turns at once: ${set.map(nameOf).join(', ')}.`
  if (set.length === 1) {
    const g = set[0]
    const calls = g.turn.calls ? `, running ${g.turn.calls}` : ''
    return `${nameOf(g)} — ${g.turn.label}: ${SESSION_SAID[g.turn.session]}${calls}.`
  }
  if (L.loop?.plays && t.value >= L.loop.t0 && t.value < L.loop.t1) return `And again: ${L.loop.said}.`
  if (L.split && t.value >= L.split.t0 && t.value < L.split.t1) return `A level down: ${L.split.said}.`
  const flying = L.passes.find((p) => p.t0 <= t.value && t.value < p.t1)
  if (flying?.said) return `Handed on ${flying.via === 'tree' ? 'in the tree' : 'as words'}: ${flying.said}.`
  const done = L.turns.filter((g) => g.t1 <= t.value).at(-1)
  return done ? `${nameOf(done)} — ${done.turn.label}: done.` : '…'
})

/** The run as a list, for a screen reader or anyone who would rather read it. */
const words = computed(() =>
  layout.value.turns.map((g) => {
    const passes = (g.turn.pass ?? [])
      .filter((p) => p.said)
      .map((p) => {
        const to = p.to === 'end' ? 'the finish' : layout.value.turns.find((o) => o.turn.id === p.to)?.lane.role.name
        return `hands ${to} ${p.via === 'tree' ? 'in the tree' : 'as words'}: ${p.said}`
      })
    return [
      `${nameOf(g)} — ${g.turn.label}`,
      SESSION_SAID[g.turn.session],
      ...(g.turn.calls ? [`runs ${g.turn.calls}`] : []),
      ...passes,
    ].join('; ')
  }),
)

const root = ref<HTMLElement | null>(null)
const stage = ref<HTMLElement | null>(null)
let seen: IntersectionObserver | undefined
let sized: ResizeObserver | undefined
let frame = 0

onMounted(() => {
  const measure = () => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => {
      const w = Math.round(stage.value?.clientWidth ?? 800)
      if (w > 0 && Math.abs(w - width.value) > 1) width.value = w
    })
  }
  measure()
  sized = new ResizeObserver(measure)
  if (stage.value) sized.observe(stage.value)

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  motion.value = true
  seen = new IntersectionObserver(
    (entries) => {
      onScreen.value = entries[0].isIntersecting
      apply()
    },
    { rootMargin: '80px' },
  )
  if (root.value) seen.observe(root.value)
  build()
})

onUnmounted(() => {
  cancelAnimationFrame(frame)
  seen?.disconnect()
  sized?.disconnect()
  stepping?.kill()
  tl?.kill()
})
</script>

<template>
  <div ref="root" class="hmz-flow-player hmz-panel">
    <div class="bar">
      <div v-if="offered.length > 1" class="tabs" role="group" aria-label="which flow">
        <button
          v-for="(one, i) in offered"
          :key="one"
          type="button"
          :class="{ on: i === at }"
          :aria-pressed="i === at"
          @click="at = i"
        >
          {{ SCENES[one].of }}
        </button>
      </div>
      <code v-else class="only">{{ layout.scene.of }}</code>
      <span class="sim" title="drawn from the flow's code, not recorded from a run">simulated</span>
    </div>

    <div
      ref="stage"
      class="stage"
      role="img"
      :aria-label="`A simulated run of ${layout.scene.of}. ${layout.scene.caption}`"
    >
      <FlowScene :lay="layout" :view="view" :cam="cam" :t="t" :mode="mode" :fades="motion && playing" />
    </div>

    <div class="deck">
      <div class="buttons">
        <button type="button" class="ctl" aria-label="from the start" title="from the start" @click="restart">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8a4.5 4.5 0 1 0 1.4-3.3M4.6 1.8v3.1h3.1" /></svg>
        </button>
        <button type="button" class="ctl" aria-label="the moment before" title="the moment before" @click="go(-1)">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3v10M13 3 6.5 8l6.5 5z" class="solid" /></svg>
        </button>
        <button
          v-if="motion"
          type="button"
          class="ctl main"
          :aria-label="playing ? 'pause' : 'play'"
          :title="playing ? 'pause' : 'play'"
          @click="toggle"
        >
          <svg v-if="playing" viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3v10M11 3v10" /></svg>
          <svg v-else viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3l8 5-8 5z" class="solid" /></svg>
        </button>
        <button type="button" class="ctl" aria-label="the moment after" title="the moment after" @click="go(1)">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M12 3v10M3 3l6.5 5L3 13z" class="solid" /></svg>
        </button>
      </div>
      <input
        class="scrub"
        type="range"
        min="0"
        max="1000"
        step="1"
        :value="Math.round(progress * 1000)"
        aria-label="where in the run"
        @input="scrub"
      />
    </div>

    <p class="now" :aria-live="motion && playing ? 'off' : 'polite'">{{ now }}</p>
    <p class="caption">{{ layout.scene.caption }}</p>
    <details class="words">
      <summary>The run, turn by turn</summary>
      <ol>
        <li v-for="(line, n) in words" :key="n">{{ line }}</li>
      </ol>
      <p v-if="layout.scene.loop">Then round again: {{ layout.scene.loop.said }}.</p>
      <p>
        It ends when
        <template v-for="(end, n) in layout.scene.ends" :key="n">
          {{ n === 0 ? '' : n === layout.scene.ends.length - 1 ? ', or ' : ', ' }}{{ end.said }}</template
        >.
      </p>
    </details>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tabs button {
  padding: 4px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 20px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s, background 0.2s;
}

.tabs button:hover {
  color: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

.tabs button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.only {
  font-size: 12px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
}

.sim {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-3);
  font-size: 10.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  white-space: nowrap;
}

.stage {
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(ellipse 70% 90% at 50% 45%, var(--vp-c-bg) 0%, transparent 100%),
    var(--hmz-panel-bg);
}

.stage :deep(svg) {
  display: block;
  width: 100%;
  height: auto;
}

.deck {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-top: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.buttons {
  display: flex;
  gap: 4px;
}

.ctl {
  display: grid;
  place-items: center;
  width: 30px;
  height: 28px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: transparent;
  color: var(--vp-c-text-2);
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}

.ctl.main {
  width: 36px;
  color: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

.ctl:hover {
  color: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

.ctl svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.ctl svg .solid {
  fill: currentColor;
}

.scrub {
  flex: 1;
  min-width: 0;
  accent-color: var(--hmz-accent);
  cursor: pointer;
}

.now {
  margin: 0;
  padding: 8px 16px 0;
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.55;
  color: var(--vp-c-text-1);
  min-height: 28px;
}

.caption {
  margin: 0;
  padding: 4px 16px 10px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.words {
  margin: 0;
  padding: 0 16px 12px;
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

.words summary {
  cursor: pointer;
  color: var(--vp-c-text-3);
}

.words ol {
  margin: 6px 0;
  padding-left: 20px;
}

.words p {
  margin: 4px 0;
}
</style>
