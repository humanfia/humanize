<script setup lang="ts">
// The screen every feature scene plays on, and the deck under it.
//
// The screen is the scene's own markup on a stage-coloured backdrop -- faint graph paper that
// slides behind the scene's camera (`camera.ts`) and fades out at the edges -- sunk a little
// into the page, lit along its top edge, with a vignette over it.
// The deck is a play/pause button and the scene's beats, one chapter each: a bar that fills as
// the chapter plays and the line of words that says what it shows. So the words are always on
// the page -- to a screen reader they are the chapters' buttons, and under reduced motion they
// are all shown at once, numbered, beside a still frame -- and the motion only acts them out.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import type { Scene } from './useScene'

const props = withDefaults(
  defineProps<{
    scene: Scene
    /** What the whole scene shows, for a screen reader. */
    label: string
    /** One short line per beat, in order. */
    beats: string[]
    /** Say that what plays is a simulation rather than a recording. */
    sim?: boolean
    /** Shape of the screen: `wide` 16:9, `tall` for a scene that stacks. */
    ratio?: string
    mobileRatio?: string
    /** The screen holds links or controls: a group, not a picture, so they stay reachable. */
    interactive?: boolean
    /** Graph paper behind the scene. Left out, it is there unless the scene draws a grid of
     *  its own (an SVG `<pattern>`), which two grids would fight. */
    paper?: boolean
  }>(),
  { sim: false, ratio: '16 / 9', mobileRatio: '', interactive: false, paper: undefined },
)

// The play button's ring: how far through the loop the scene is.
const RING = 2 * Math.PI * 14
const ring = computed(() => RING * (1 - props.scene.progress.value))

function fill(i: number) {
  const m = props.scene.marks.value
  const p = props.scene.progress.value
  const start = m[i] ?? 0
  const end = m[i + 1] ?? 1
  if (p <= start) return 0
  if (p >= end) return 1
  return (p - start) / Math.max(end - start, 1e-6)
}

// A scene is drawn for a screen at least as wide as its viewBox: 360 on a phone. On a narrower
// one it is scaled down to fit, and its words with it. The small ones are lifted back, each
// about its own anchor, to the size they would be drawn at on that 360 screen -- so no word is
// under 11px on a 320 phone either -- and the drawing around them shrinks alone. A word set
// large enough to stay readable shrinks with the drawing, so it still fits the box it is in.
const screen = ref<HTMLElement | null>(null)
const lift = ref(1)
const ownGrid = ref(false)
const paper = computed(() => props.paper ?? !ownGrid.value)
let sized: ResizeObserver | undefined
// At once rather than on the next frame: a ResizeObserver is told before the frame is painted,
// so no frame is ever drawn with its words unlifted.
function measure() {
  const el = screen.value
  ownGrid.value = !!el?.querySelector('svg pattern')
  const svg = el?.querySelector<SVGSVGElement>('svg[viewBox]')
  const box = svg?.viewBox.baseVal
  if (!el || !box?.width || !box.height) return
  const k = Math.min(el.clientWidth / box.width, el.clientHeight / box.height)
  lift.value = k > 0 && k < 0.995 ? 1 / k : 1
  for (const text of el.querySelectorAll<SVGTextElement>('svg text')) {
    if (lift.value === 1) {
      text.style.removeProperty('--lift')
      continue
    }
    // By its smallest part: a tspan may be set smaller than the line it is in.
    const parts = [text, ...text.querySelectorAll('tspan')]
    const size = Math.min(...parts.map((part) => parseFloat(getComputedStyle(part).fontSize))) * k
    text.style.setProperty('--lift', String(Math.min(lift.value, Math.max(1, ROOM / size))))
  }
}
/** A word drawn this big or bigger is left to shrink with its scene. */
const ROOM = 12.5
// A rebuild may have drawn other words, for another layout or another pick: once they are in.
watch(() => props.scene.timeline.value, measure, { flush: 'post' })
onMounted(() => {
  measure()
  sized = new ResizeObserver(measure)
  if (screen.value) sized.observe(screen.value)
})
onUnmounted(() => sized?.disconnect())

const bind = (el: unknown) => {
  props.scene.root.value = (el as HTMLElement | null) ?? null
}

const style = computed(() => ({
  '--stage-ratio': props.ratio,
  '--stage-ratio-m': props.mobileRatio || props.ratio,
  '--stage-lift': lift.value,
}))
</script>

<template>
  <figure :ref="bind" class="hmz-stage hmz-panel" :class="{ still: scene.reduced.value && !scene.playing.value, simulated: sim }" :style="style">
    <div ref="screen" class="screen" :class="{ running: scene.running.value, lifted: lift > 1 }" :role="interactive ? 'group' : 'img'" :aria-label="label">
      <div class="ambient" aria-hidden="true"><i /><i /></div>
      <div v-if="paper" class="paper" aria-hidden="true" />
      <slot :beat="scene.beat.value" />
      <span v-if="sim" class="sim on-screen" aria-hidden="true">simulated</span>
    </div>
    <div class="deck">
      <button
        class="play"
        type="button"
        :aria-label="scene.playing.value ? 'Pause the animation' : 'Play the animation'"
        :aria-pressed="scene.playing.value"
        @click="scene.toggle()"
      >
        <svg class="ring" viewBox="0 0 32 32" aria-hidden="true">
          <circle class="track" cx="16" cy="16" r="14" />
          <circle class="done" cx="16" cy="16" r="14" :stroke-dasharray="RING" :stroke-dashoffset="ring" />
        </svg>
        <svg v-if="scene.playing.value" viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="3" width="3" height="10" rx="1" /><rect x="9.5" y="3" width="3" height="10" rx="1" /></svg>
        <svg v-else viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.8v10.4a.6.6 0 0 0 .9.5l8.3-5.2a.6.6 0 0 0 0-1L5.4 2.3a.6.6 0 0 0-.9.5z" /></svg>
      </button>
      <ol class="chapters">
        <li v-for="(text, i) in beats" :key="i" :class="{ on: scene.beat.value === i, past: scene.beat.value > i }">
          <button type="button" :aria-current="scene.beat.value === i ? 'step' : undefined" @click="scene.seek(i)">
            <span class="bar" aria-hidden="true"><span class="fill" :style="{ transform: `scaleX(${fill(i)})` }" /></span>
            <span class="words"><b aria-hidden="true">{{ i + 1 }}</b>{{ text }}</span>
          </button>
        </li>
      </ol>
      <span v-if="sim" class="sim in-deck" aria-hidden="true">simulated</span>
    </div>
  </figure>
</template>

<style scoped>
.hmz-stage {
  position: relative;
  margin: 22px 0 30px;
  background: var(--hmz-stage-deck);
}

.screen {
  position: relative;
  aspect-ratio: var(--stage-ratio);
  overflow: hidden;
  background: var(--hmz-stage-bg);
  color: var(--hmz-stage-ink);
  isolation: isolate;
}

/* Two slow lights drifting behind the scene, so the stage has depth before anything is on it.
   They move only while the scene does. */
.ambient {
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  opacity: var(--hmz-glow);
}

.ambient i {
  position: absolute;
  width: 60%;
  height: 90%;
  opacity: 0.3;
  will-change: transform;
  animation: stage-drift 18s ease-in-out infinite alternate paused;
}

.ambient i:first-child {
  left: -12%;
  top: -30%;
  /* A gradient rather than a blurred disc: the same glow, at no cost to the compositor. */
  background: radial-gradient(closest-side, var(--hmz-lane-1), transparent);
}

.ambient i:last-child {
  right: -14%;
  bottom: -40%;
  background: radial-gradient(closest-side, var(--hmz-accent-2), transparent);
  animation-duration: 23s;
  animation-direction: alternate-reverse;
}

.screen.running .ambient i {
  animation-play-state: running;
}

@keyframes stage-drift {
  to {
    transform: translate3d(18%, 14%, 0) scale(1.15);
  }
}

/* Graph paper: a fine grid and every fifth line heavier, as a 3Blue1Brown scene is drawn on
   its number plane, so the stage reads as a space before anything is in it. It is drawn larger
   than the screen and slides, a fifth as far as the world, wherever a scene's camera goes
   (`--hmz-cam-*`, set by `camera.ts`), and fades out toward the edges. */
.paper {
  position: absolute;
  inset: -12%;
  z-index: -1;
  pointer-events: none;
  background-image:
    linear-gradient(var(--hmz-stage-grid-major) 1px, transparent 1px),
    linear-gradient(90deg, var(--hmz-stage-grid-major) 1px, transparent 1px),
    linear-gradient(var(--hmz-stage-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--hmz-stage-grid) 1px, transparent 1px);
  background-size:
    120px 120px,
    120px 120px,
    24px 24px,
    24px 24px;
  background-position: center;
  transform: translate3d(calc(var(--hmz-cam-x, 0) * 100%), calc(var(--hmz-cam-y, 0) * 100%), 0) scale(var(--hmz-cam-s, 1));
  -webkit-mask-image: radial-gradient(75% 70% at 50% 45%, #000 30%, transparent 100%);
  mask-image: radial-gradient(75% 70% at 50% 45%, #000 30%, transparent 100%);
}

/* The lens: the edges of the frame fall off, so the eye goes to the middle. */
.screen::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 5;
  background: radial-gradient(130% 105% at 50% 42%, transparent 62%, var(--hmz-stage-vignette) 100%);
}

/* The screen sits a little into the page: light catches its top edge and its sides fall into
   shade, so the picture has a frame without a border drawn round it. */
.screen::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 5;
  box-shadow:
    inset 0 1px 0 var(--hmz-stage-highlight),
    inset 0 0 28px var(--hmz-stage-depth);
}

.screen :slotted(svg),
.screen :slotted(canvas),
.screen :slotted(.layer) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.screen :slotted(canvas) {
  pointer-events: none;
}

.sim {
  padding: 2px 8px;
  border: 1px solid var(--hmz-stage-line);
  border-radius: 999px;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--hmz-stage-dim);
  background: var(--hmz-stage-card);
}

.sim.on-screen {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 6;
}

/* On a phone the picture has no corner to spare: the word goes under it, by the controls. */
.sim.in-deck {
  display: none;
  flex: none;
  align-self: center;
}

.deck {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px 12px;
  border-top: 1px solid var(--hmz-panel-border);
}

.play {
  flex: none;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 50%;
  color: var(--vp-c-text-1);
  background: var(--vp-c-bg);
  transition: border-color 0.2s, color 0.2s;
}

.play:hover,
.play:focus-visible {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}

.play {
  position: relative;
}

.play svg {
  width: 12px;
  height: 12px;
  fill: currentColor;
}

/* How far through its loop the scene is, round the button: a clock face that fills. */
.play svg.ring {
  position: absolute;
  inset: -1px;
  width: calc(100% + 2px);
  height: calc(100% + 2px);
  fill: none;
  transform: rotate(-90deg);
  pointer-events: none;
}

.ring circle {
  fill: none;
  stroke-width: 2;
}

.ring .track {
  stroke: transparent;
}

.ring .done {
  stroke: var(--hmz-accent);
  stroke-linecap: round;
  transition: stroke 0.2s;
}

.still .ring .done {
  stroke: transparent;
}

.chapters {
  flex: 1;
  display: flex;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
  min-width: 0;
}

.chapters li {
  flex: 1 1 0;
  min-width: 0;
  margin: 0;
}

.chapters button {
  display: block;
  width: 100%;
  padding: 4px 0 0;
  text-align: left;
  color: var(--vp-c-text-3);
  transition: color 0.3s;
}

.chapters li.on button,
.chapters button:hover {
  color: var(--vp-c-text-1);
}

.chapters li.past button {
  color: var(--vp-c-text-2);
}

.bar {
  display: block;
  height: 3px;
  border-radius: 2px;
  background: var(--vp-c-divider);
  overflow: hidden;
}

.fill {
  display: block;
  height: 100%;
  transform-origin: left center;
  background: linear-gradient(90deg, var(--hmz-lane-1), var(--hmz-accent));
}

/* The chapter under way glows, so the eye finds it among the rest. */
.bar {
  transition: box-shadow 0.4s;
}

.chapters li.on .bar {
  box-shadow: 0 0 calc(10px * var(--hmz-glow)) color-mix(in srgb, var(--hmz-accent) 55%, transparent);
}

.chapters li.on .words b {
  text-shadow: 0 0 calc(8px * var(--hmz-glow)) color-mix(in srgb, var(--hmz-accent) 60%, transparent);
}

.words {
  display: block;
  margin-top: 6px;
  font-size: 12.5px;
  line-height: 1.4;
}

.words b {
  margin-right: 6px;
  font-family: var(--vp-font-family-mono);
  font-weight: 600;
  font-size: 11px;
  color: var(--hmz-accent);
}

/* Held still: every chapter's words at once, since none of them is going to play. */
.still .chapters {
  flex-wrap: wrap;
}

.still .chapters li {
  flex: 1 1 180px;
}

.still .bar {
  display: none;
}

.still .chapters button {
  color: var(--vp-c-text-2);
}

@media (max-width: 640px) {
  .screen {
    aspect-ratio: var(--stage-ratio-m);
  }

  .sim.on-screen {
    display: none;
  }

  .sim.in-deck {
    display: block;
    align-self: flex-start;
    margin-top: 2px;
  }

  /* The words of the chapter playing run under the bars, and stop short of the word. */
  .hmz-stage.simulated:not(.still) .chapters li.on .words {
    right: 108px;
  }

  .deck {
    padding: 10px 10px 12px;
  }

  .chapters {
    gap: 4px;
  }

  /* Too narrow for every chapter's words: the bars stay, and only the one playing speaks. */
  .hmz-stage:not(.still) .chapters .words {
    display: none;
  }

  .hmz-stage:not(.still) .chapters li.on .words {
    display: block;
    position: absolute;
    left: 54px;
    right: 12px;
    /* Each new chapter's words wipe on from the left as it starts: the one line on a phone
       says which chapter it is by changing visibly. */
    animation: caption-wipe 0.55s cubic-bezier(0.16, 1, 0.3, 1) both;
  }

  .hmz-stage:not(.still) .deck {
    padding-bottom: 40px;
    position: relative;
  }

  .still .chapters {
    flex-direction: column;
  }

  .still .chapters li {
    flex: none;
  }
}

@keyframes caption-wipe {
  from {
    clip-path: inset(0 100% 0 0);
    opacity: 0.2;
  }
  to {
    clip-path: inset(0 0 0 0);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hmz-stage .chapters li.on .words {
    animation: none !important;
  }

  .bar,
  .ring .done {
    transition: none;
  }
}
</style>
