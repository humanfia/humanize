<!--
  A terminal demo, played in the reader's browser from the text the terminal was sent:

    <HmzCast name="tui" alt="hmz opens, / lists its commands, and /flow opens a flow's menu" />

  `name` is a recording under `public/demo/`, `<name>.cast`, made from `tapes/<name>.tape` by
  `tapes/render.sh`. The words on it are real text -- they stay sharp at any zoom and can be
  selected -- and `alt` says what happens on it for anyone who cannot watch.

  It powers on like a tube when it is first scrolled into view, leans toward the pointer, and
  plays only while it is on screen. Under `prefers-reduced-motion` none of that moves: it shows
  the recording's last frame, and the play button is there for anyone who wants the motion.

  Its colours are the site's terminal tokens (`--hmz-term-*` in style.css): paper-light in the
  light theme, night in the dark. The player reads its 16 colours once, when it is made, so a
  switch of theme makes it again, at the moment it had got to and playing if it was.
-->
<script setup lang="ts">
import 'asciinema-player/dist/bundle/asciinema-player.css'

import { withBase } from 'vitepress'
import { onMounted, onUnmounted, ref } from 'vue'

import { motion } from '../motion/gsap'

const props = defineProps<{ name: string; alt: string; title?: string }>()

const root = ref<HTMLElement>()
const screen = ref<HTMLElement>()
const progress = ref(0)
const state = ref<'idle' | 'playing' | 'paused' | 'ended'>('idle')

type Player = import('asciinema-player').Player
let player: Player | undefined
let seen: IntersectionObserver | undefined
let frame = 0
let visible = false
let still = false
const undo: (() => void)[] = []

function tick() {
  const duration = player?.getDuration()
  if (player && duration) progress.value = Math.min(1, player.getCurrentTime() / duration)
  frame = requestAnimationFrame(tick)
}

/** Make the player: showing its last frame, or -- made again on a switch of theme -- the
 *  moment `at` it had got to, and playing on from there if `go`. */
async function load(at?: number, go = false) {
  const { create } = await import('asciinema-player')
  player = create(withBase(`/demo/${props.name}.cast`), screen.value!, {
    fit: 'width',
    controls: false,
    autoPlay: go,
    preload: true,
    idleTimeLimit: 2,
    theme: 'hmz',
    poster: at === undefined ? 'npt:9999' : `npt:${at}`,
    ...(at === undefined ? {} : { startAt: at }),
    terminalFontFamily: 'var(--vp-font-family-mono)',
    terminalLineHeight: 1.25,
  })
  player.addEventListener('playing', () => (state.value = 'playing'))
  player.addEventListener('pause', () => (state.value = state.value === 'ended' ? 'ended' : 'paused'))
  player.addEventListener('ended', () => {
    state.value = 'ended'
    progress.value = 1
    if (!still) setTimeout(() => visible && state.value === 'ended' && replay(), 2600)
  })
}

function powerOn() {
  const gsap = motion()
  const el = root.value!
  return gsap
    .timeline()
    .from(el, { y: 48, rotateX: 14, scale: 0.94, opacity: 0, filter: 'blur(10px)', duration: 1.1 })
    .fromTo(
      el.querySelector('.hmz-cast-glass'),
      { scaleY: 0.004, scaleX: 0.6, filter: 'brightness(6)' },
      { scaleY: 1, scaleX: 1, filter: 'brightness(1)', duration: 0.7, ease: 'expo.out' },
      '-=0.55',
    )
    .fromTo(el.querySelector('.hmz-cast-flash'), { opacity: 0.9 }, { opacity: 0, duration: 0.8 }, '<0.1')
}

async function play() {
  if (!player) return
  if (state.value === 'ended') return replay()
  await player.play()
}

async function replay() {
  if (!player) return
  const gsap = motion()
  const glass = root.value!.querySelector('.hmz-cast-glass')
  await gsap.to(glass, { scaleY: 0.004, filter: 'brightness(5)', duration: 0.28, ease: 'cine.in' })
  await player.seek(0)
  gsap.to(glass, { scaleY: 1, filter: 'brightness(1)', duration: 0.5, ease: 'expo.out' })
  await player.play()
}

// The theme changed: the player still has the old one's colours. Make it again where it was.
let theming: MutationObserver | undefined
let dark = false
let remaking = false
async function retheme() {
  const now = document.documentElement.classList.contains('dark')
  if (now === dark) return
  dark = now
  if (!player || remaking) return
  remaking = true
  try {
    const was = state.value
    // Not started, or over: the last frame, as it was made the first time.
    const at = was === 'ended' || was === 'idle' ? undefined : player.getCurrentTime()
    player.dispose()
    player = undefined
    screen.value!.replaceChildren()
    await load(at, was === 'playing')
    state.value = was === 'playing' ? 'playing' : was
  } finally {
    remaking = false
  }
}

function toggle() {
  if (state.value === 'playing') player?.pause()
  else play()
}

// The window leans toward the pointer, and a light follows it across the glass.
function lean(el: HTMLElement) {
  const gsap = motion()
  const rx = gsap.quickTo(el, 'rotateX', { duration: 0.6 })
  const ry = gsap.quickTo(el, 'rotateY', { duration: 0.6 })
  const move = (e: PointerEvent) => {
    const box = el.getBoundingClientRect()
    const x = (e.clientX - box.left) / box.width
    const y = (e.clientY - box.top) / box.height
    ry((x - 0.5) * 6)
    rx((0.5 - y) * 5)
    el.style.setProperty('--hmz-cast-x', `${x * 100}%`)
    el.style.setProperty('--hmz-cast-y', `${y * 100}%`)
  }
  const leave = () => {
    rx(0)
    ry(0)
  }
  el.addEventListener('pointermove', move)
  el.addEventListener('pointerleave', leave)
  undo.push(() => {
    el.removeEventListener('pointermove', move)
    el.removeEventListener('pointerleave', leave)
  })
}

onMounted(() => {
  still = matchMedia('(prefers-reduced-motion: reduce)').matches
  dark = document.documentElement.classList.contains('dark')
  theming = new MutationObserver(retheme)
  theming.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  const el = root.value!
  let started = false
  seen = new IntersectionObserver(
    async ([entry]) => {
      visible = entry.isIntersecting
      if (!visible) {
        if (state.value === 'playing') player?.pause()
        return
      }
      if (!started) {
        started = true
        await load()
        if (still) return
        lean(el)
        powerOn()
        setTimeout(() => visible && play(), 700)
      } else if (!still && state.value === 'paused') {
        play()
      }
    },
    { threshold: 0.35 },
  )
  seen.observe(el)
  const hidden = () => document.hidden && state.value === 'playing' && player?.pause()
  document.addEventListener('visibilitychange', hidden)
  undo.push(() => document.removeEventListener('visibilitychange', hidden))
  frame = requestAnimationFrame(tick)
})

onUnmounted(() => {
  cancelAnimationFrame(frame)
  seen?.disconnect()
  theming?.disconnect()
  undo.forEach((f) => f())
  player?.dispose()
})
</script>

<template>
  <figure ref="root" class="hmz-cast" :class="`is-${state}`" :aria-label="alt">
    <div class="hmz-cast-halo" aria-hidden="true" />
    <div class="hmz-cast-window">
      <div class="hmz-cast-bar">
        <span class="hmz-cast-dots" aria-hidden="true"><i /><i /><i /></span>
        <span class="hmz-cast-title">{{ title ?? 'hmz' }}</span>
        <span class="hmz-cast-live" aria-hidden="true">{{ state === 'playing' ? 'LIVE' : '' }}</span>
        <button
          class="hmz-cast-button"
          type="button"
          :aria-label="state === 'playing' ? 'Pause the demo' : 'Play the demo'"
          @click="toggle"
        >
          <svg v-if="state === 'playing'" viewBox="0 0 16 16"><path d="M4 3h3v10H4zM9 3h3v10H9z" /></svg>
          <svg v-else-if="state === 'ended'" viewBox="0 0 16 16">
            <path d="M8 3a5 5 0 1 1-4.6 3H1.5L4.5 2.5 7.5 6H5.6A3.2 3.2 0 1 0 8 4.8z" />
          </svg>
          <svg v-else viewBox="0 0 16 16"><path d="M4 2.5v11l9.5-5.5z" /></svg>
        </button>
      </div>
      <div class="hmz-cast-glass" @click="toggle">
        <div ref="screen" class="hmz-cast-screen" />
        <div class="hmz-cast-scan" aria-hidden="true" />
        <div class="hmz-cast-flash" aria-hidden="true" />
      </div>
      <div class="hmz-cast-progress" aria-hidden="true">
        <span :style="{ transform: `scaleX(${progress})` }" />
      </div>
    </div>
    <figcaption class="hmz-cast-alt">{{ alt }}</figcaption>
  </figure>
</template>

<style>
@property --hmz-cast-angle {
  syntax: '<angle>';
  initial-value: 0deg;
  inherits: false;
}

.vp-doc .hmz-cast,
.hmz-cast {
  --hmz-cast-x: 50%;
  --hmz-cast-y: 0%;
  position: relative;
  max-width: 760px;
  margin: 28px 0 32px;
  perspective: 1200px;
  transform-style: preserve-3d;
  will-change: transform;
}

/* A ring of light turning around the window, blurred into a halo under it. */
.hmz-cast-halo {
  position: absolute;
  inset: -2px;
  border-radius: 14px;
  background: conic-gradient(
    from var(--hmz-cast-angle),
    var(--hmz-accent),
    var(--hmz-lane-1),
    var(--hmz-accent-2),
    var(--hmz-warm),
    var(--hmz-accent)
  );
  filter: blur(18px);
  opacity: calc(0.35 * var(--hmz-glow) + 0.08);
  animation: hmz-cast-turn 8s linear infinite;
  transition: opacity 0.6s;
}

.hmz-cast.is-playing .hmz-cast-halo {
  opacity: calc(0.6 * var(--hmz-glow) + 0.1);
}

.hmz-cast-window {
  position: relative;
  border-radius: 12px;
  padding: 1px;
  background: conic-gradient(
    from var(--hmz-cast-angle),
    color-mix(in srgb, var(--hmz-accent) 90%, transparent),
    color-mix(in srgb, var(--hmz-lane-1) 40%, transparent),
    color-mix(in srgb, var(--hmz-accent-2) 90%, transparent),
    color-mix(in srgb, var(--hmz-warm) 40%, transparent),
    color-mix(in srgb, var(--hmz-accent) 90%, transparent)
  );
  animation: hmz-cast-turn 8s linear infinite;
  overflow: hidden;
}

.hmz-cast-bar,
.hmz-cast-glass,
.hmz-cast-progress {
  background: var(--hmz-term-bg);
}

.hmz-cast-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 34px;
  padding: 0 10px 0 14px;
  border-radius: 11px 11px 0 0;
  border-bottom: 1px solid var(--hmz-term-edge);
  background: var(--hmz-term-bar);
  color: var(--hmz-term-dim);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
}

.hmz-cast-dots {
  display: flex;
  gap: 8px;
}

.hmz-cast-dots i {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--hmz-term-close);
}

.hmz-cast-dots i:nth-child(2) {
  background: var(--hmz-term-min);
}

.hmz-cast-dots i:nth-child(3) {
  background: var(--hmz-term-max);
}

.hmz-cast-title {
  flex: 1;
}

.hmz-cast-live {
  color: var(--hmz-term-1);
  font-size: 11px;
  letter-spacing: 0.12em;
}

.hmz-cast-live:not(:empty)::before {
  content: '';
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 6px;
  border-radius: 50%;
  background: var(--hmz-term-1);
  box-shadow: 0 0 8px var(--hmz-term-1);
  vertical-align: 1px;
  animation: hmz-cast-pulse 1.2s ease-in-out infinite;
}

.hmz-cast-button {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  color: var(--hmz-term-text);
  transition: background 0.2s;
}

.hmz-cast-button:hover {
  background: color-mix(in srgb, var(--hmz-term-text) 9%, transparent);
}

.hmz-cast-button svg {
  width: 14px;
  height: 14px;
  fill: currentColor;
}

.hmz-cast-glass {
  position: relative;
  padding: 10px 12px;
  overflow: hidden;
  cursor: pointer;
  transform-origin: 50% 50%;
}

/* A light under the pointer, and a slow band sweeping down the glass like a tube's refresh. */
.hmz-cast-glass::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(
    420px circle at var(--hmz-cast-x) var(--hmz-cast-y),
    color-mix(in srgb, var(--hmz-accent) 9%, transparent),
    transparent 60%
  );
}

.hmz-cast-scan {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(to bottom, transparent 0, color-mix(in srgb, var(--hmz-accent) 6%, transparent) 50%, transparent 100%) 0
      -30% / 100% 30% no-repeat,
    repeating-linear-gradient(to bottom, color-mix(in srgb, var(--hmz-term-text) 3%, transparent) 0 1px, transparent 1px 3px);
  animation: hmz-cast-sweep 6s linear infinite;
}

.hmz-cast-flash {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(
    ellipse at center,
    var(--vp-c-white) 0,
    color-mix(in srgb, var(--hmz-accent) 60%, transparent) 30%,
    transparent 70%
  );
  opacity: 0;
}

.hmz-cast-progress {
  height: 3px;
  border-radius: 0 0 11px 11px;
}

.hmz-cast-progress span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--hmz-accent), var(--hmz-lane-1), var(--hmz-accent-2));
  box-shadow: 0 0 calc(10px * var(--hmz-glow)) color-mix(in srgb, var(--hmz-accent) 80%, transparent);
  transform-origin: left;
}

/* What happens on it, for a screen reader: the picture says it to everyone else. */
.hmz-cast-alt {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* The player itself: no frame of its own, and the colours of the site's terminal. */
.hmz-cast .ap-wrapper {
  justify-content: flex-start;
}

.hmz-cast .ap-player,
.asciinema-player-theme-hmz {
  --term-color-foreground: var(--hmz-term-text);
  --term-color-background: var(--hmz-term-bg);
  --term-color-0: var(--hmz-term-0);
  --term-color-1: var(--hmz-term-1);
  --term-color-2: var(--hmz-term-2);
  --term-color-3: var(--hmz-term-3);
  --term-color-4: var(--hmz-term-4);
  --term-color-5: var(--hmz-term-5);
  --term-color-6: var(--hmz-term-6);
  --term-color-7: var(--hmz-term-7);
  --term-color-8: var(--hmz-term-8);
  --term-color-9: var(--hmz-term-9);
  --term-color-10: var(--hmz-term-10);
  --term-color-11: var(--hmz-term-11);
  --term-color-12: var(--hmz-term-12);
  --term-color-13: var(--hmz-term-13);
  --term-color-14: var(--hmz-term-14);
  --term-color-15: var(--hmz-term-15);
  border-radius: 0;
  background: transparent;
}

@keyframes hmz-cast-turn {
  to {
    --hmz-cast-angle: 360deg;
  }
}

@keyframes hmz-cast-sweep {
  to {
    background-position:
      0 130%,
      0 0;
  }
}

@keyframes hmz-cast-pulse {
  50% {
    opacity: 0.3;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hmz-cast-halo,
  .hmz-cast-window,
  .hmz-cast-scan,
  .hmz-cast-live::before {
    animation: none;
  }
}
</style>
