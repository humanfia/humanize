<script setup lang="ts">
// Every feature page, one card each, grouped the way the sidebar groups them. Each card is a
// small loop that acts its feature out, and a title; the page behind it is where the rest is.
//
// The cards rise into place as the grid is scrolled to (ScrollTrigger), tilt towards the
// pointer, and their loops run only while the grid is on screen. Under reduced motion none of
// that happens: every drawing holds a frame that still says its one thing.
import { onMounted, onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'

import { motion, ScrollTrigger } from '../motion/gsap'

interface Card {
  slug: string
  title: string
}

const GROUPS: { name: string; cards: Card[] }[] = [
  {
    name: 'Run it your way',
    cards: [
      { slug: 'backends', title: 'Every coding agent you have' },
      { slug: 'accounts', title: 'Two accounts of one CLI' },
      { slug: 'surfaces', title: 'Prompt, script or Python' },
    ],
  },
  {
    name: 'While it runs',
    cards: [
      { slug: 'steering', title: 'Talk into a running turn' },
      { slug: 'human', title: 'When a flow asks you' },
      { slug: 'allowances', title: 'A budget on every run' },
      { slug: 'daemon', title: 'Close the terminal, keep the run' },
    ],
  },
  {
    name: 'Where the work lands, and after',
    cards: [
      { slug: 'anchor', title: 'Work on another machine' },
      { slug: 'tracing', title: 'Every agent on one timeline' },
      { slug: 'resuming', title: 'Pick up where it stopped' },
    ],
  },
  {
    name: 'Writing a flow',
    cards: [
      { slug: 'flows', title: 'A loop in plain Python' },
      { slug: 'concurrency', title: 'Many conversations at once' },
      { slug: 'shapes', title: 'Answers as typed data' },
      { slug: 'goals', title: 'The agent decides it is done' },
      { slug: 'hooks', title: 'React to each moment of a turn' },
      { slug: 'budgets', title: 'Cap a single turn' },
    ],
  },
]

const root = ref<HTMLElement | null>(null)
const live = ref(false)
let observer: IntersectionObserver | undefined
let triggers: ScrollTrigger[] = []
let reduced = true

onMounted(() => {
  reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduced || !root.value) return
  observer = new IntersectionObserver(([entry]) => (live.value = entry.isIntersecting))
  observer.observe(root.value)
  const gsap = motion()
  const cards = root.value.querySelectorAll('.card')
  gsap.set(cards, { autoAlpha: 0, y: 48, rotateX: -28, transformPerspective: 900, transformOrigin: '50% 100%' })
  triggers = ScrollTrigger.batch(cards, {
    start: 'top 92%',
    once: true,
    onEnter: (batch) =>
      gsap.to(batch, { autoAlpha: 1, y: 0, rotateX: 0, duration: 1.1, ease: 'cine.out', stagger: 0.07, overwrite: true, clearProps: 'transform' }),
  })
})

onUnmounted(() => {
  observer?.disconnect()
  triggers.forEach((t) => t.kill())
})

// The card leans towards the pointer, and a glare follows it across the glass.
function lean(event: PointerEvent) {
  if (reduced || event.pointerType !== 'mouse') return
  const el = event.currentTarget as HTMLElement
  const box = el.getBoundingClientRect()
  const x = (event.clientX - box.left) / box.width
  const y = (event.clientY - box.top) / box.height
  el.style.setProperty('--rx', `${(0.5 - y) * 10}deg`)
  el.style.setProperty('--ry', `${(x - 0.5) * 12}deg`)
  el.style.setProperty('--gx', `${x * 100}%`)
  el.style.setProperty('--gy', `${y * 100}%`)
}

function rest(event: PointerEvent) {
  const el = event.currentTarget as HTMLElement
  el.style.setProperty('--rx', '0deg')
  el.style.setProperty('--ry', '0deg')
}
</script>

<template>
  <div ref="root" class="features" :class="{ live }">
    <section v-for="group in GROUPS" :key="group.name" class="group">
      <h3 class="group-name">{{ group.name }}</h3>
      <div class="cards">
        <a
          v-for="card in group.cards"
          :key="card.slug"
          class="card"
          :class="card.slug"
          :href="withBase(`/features/${card.slug}`)"
          @pointermove="lean"
          @pointerleave="rest"
        >
          <span class="glass" aria-hidden="true">
            <svg class="viz" viewBox="0 0 160 72">
              <template v-if="card.slug === 'backends'">
                <circle v-for="i in 5" :key="i" class="cli" :cx="20 + (i - 1) * 30" cy="36" r="8" :style="{ fill: `var(--hmz-lane-${i})` }" />
                <circle class="pick" cx="20" cy="36" r="13" />
              </template>
              <template v-else-if="card.slug === 'accounts'">
                <rect class="acct a" x="14" y="14" width="40" height="18" rx="9" />
                <rect class="acct b" x="14" y="40" width="40" height="18" rx="9" />
                <path class="talk" d="M 60 23 C 90 23 90 49 146 49" />
                <path class="talk-left" d="M 60 23 L 100 23" />
                <circle class="said" cx="0" cy="0" r="4" />
              </template>
              <template v-else-if="card.slug === 'surfaces'">
                <rect class="way w1" x="10" y="8" width="36" height="16" rx="4" />
                <rect class="way w2" x="10" y="28" width="36" height="16" rx="4" />
                <rect class="way w3" x="10" y="48" width="36" height="16" rx="4" />
                <path class="to" d="M 46 16 C 80 16 90 36 116 36 M 46 36 L 116 36 M 46 56 C 80 56 90 36 116 36" />
                <circle class="one" cx="132" cy="36" r="14" />
              </template>
              <template v-else-if="card.slug === 'steering'">
                <rect class="track" x="14" y="44" width="132" height="10" rx="5" />
                <rect class="turn" x="14" y="44" width="132" height="10" rx="5" />
                <path class="line-in" d="M 80 6 l 0 26 m -6 -6 l 6 6 l 6 -6" />
              </template>
              <template v-else-if="card.slug === 'human'">
                <circle class="head" cx="40" cy="28" r="9" />
                <path class="body" d="M 24 60 a 16 14 0 0 1 32 0" />
                <rect class="bubble" x="70" y="12" width="74" height="22" rx="8" />
                <text class="q" x="107" y="27" text-anchor="middle">done? yes</text>
                <rect class="bubble-2" x="70" y="40" width="50" height="20" rx="8" />
              </template>
              <template v-else-if="card.slug === 'allowances'">
                <circle class="gauge-track" cx="80" cy="36" r="24" />
                <circle class="gauge" cx="80" cy="36" r="24" pathLength="100" transform="rotate(-90 80 36)" />
                <text class="stop" x="80" y="40" text-anchor="middle">$50</text>
              </template>
              <template v-else-if="card.slug === 'daemon'">
                <rect class="window" x="16" y="10" width="62" height="46" rx="6" />
                <line class="window-bar" x1="16" x2="78" y1="20" y2="20" />
                <circle class="run" cx="118" cy="36" r="10" />
                <circle class="run-ring" cx="118" cy="36" r="10" />
              </template>
              <template v-else-if="card.slug === 'anchor'">
                <rect class="box" x="10" y="16" width="46" height="40" rx="7" />
                <rect class="box there" x="104" y="16" width="46" height="40" rx="7" />
                <line class="wire" x1="56" x2="104" y1="36" y2="36" />
                <rect class="packet" x="54" y="31" width="14" height="10" rx="2" />
                <circle class="key" cx="33" cy="36" r="5" />
              </template>
              <template v-else-if="card.slug === 'tracing'">
                <g class="slices">
                  <rect v-for="(s, i) in [[14, 12, 30], [48, 12, 24], [86, 12, 40], [24, 32, 44], [74, 32, 22], [104, 32, 30], [14, 52, 20], [40, 52, 50], [96, 52, 36]]" :key="i" :x="s[0]" :y="s[1]" :width="s[2]" height="10" rx="2" />
                </g>
                <line class="head" x1="10" x2="10" y1="6" y2="66" />
              </template>
              <template v-else-if="card.slug === 'resuming'">
                <rect class="seg" x="12" y="30" width="62" height="12" rx="4" />
                <rect class="seg late" x="86" y="30" width="62" height="12" rx="4" />
                <path class="plug" d="M 80 18 v 36" />
                <text class="round" x="44" y="22" text-anchor="middle">40</text>
                <text class="round late-n" x="116" y="22" text-anchor="middle">41</text>
              </template>
              <template v-else-if="card.slug === 'flows'">
                <circle class="loop" cx="80" cy="36" r="22" />
                <circle class="loop-head" cx="80" cy="14" r="5" />
                <text class="py" x="80" y="41" text-anchor="middle">def</text>
              </template>
              <template v-else-if="card.slug === 'concurrency'">
                <rect v-for="i in 5" :key="i" class="lane" x="16" :y="6 + (i - 1) * 13" width="128" height="8" rx="4" :style="{ '--d': `${(i * 0.37) % 1}s`, fill: `var(--hmz-lane-${i})` }" />
              </template>
              <template v-else-if="card.slug === 'shapes'">
                <g class="prose">
                  <rect x="14" y="14" width="70" height="5" rx="2" />
                  <rect x="14" y="26" width="58" height="5" rx="2" />
                  <rect x="14" y="38" width="66" height="5" rx="2" />
                  <rect x="14" y="50" width="44" height="5" rx="2" />
                </g>
                <g class="fields">
                  <rect x="96" y="12" width="52" height="20" rx="5" />
                  <text x="122" y="26" text-anchor="middle">done ✓</text>
                  <rect x="96" y="40" width="52" height="20" rx="5" />
                  <text x="122" y="54" text-anchor="middle">notes</text>
                </g>
              </template>
              <template v-else-if="card.slug === 'goals'">
                <circle class="ring r1" cx="112" cy="36" r="24" />
                <circle class="ring r2" cx="112" cy="36" r="15" />
                <circle class="ring r3" cx="112" cy="36" r="6" />
                <circle class="arrow" cx="20" cy="36" r="5" />
              </template>
              <template v-else-if="card.slug === 'hooks'">
                <line class="track-h" x1="14" x2="146" y1="36" y2="36" />
                <circle v-for="i in 5" :key="i" class="moment" :cx="14 + (i - 1) * 33" cy="36" r="4" />
                <circle class="caught" cx="80" cy="36" r="10" />
                <circle class="mover" cx="14" cy="36" r="5" />
              </template>
              <template v-else-if="card.slug === 'budgets'">
                <rect class="track" x="14" y="30" width="132" height="12" rx="6" />
                <rect class="cut-bar" x="14" y="30" width="132" height="12" rx="6" />
                <line class="cut" x1="104" x2="104" y1="16" y2="56" />
              </template>
            </svg>
            <span class="glare" />
          </span>
          <span class="title">{{ card.title }}</span>
        </a>
      </div>
    </section>
    <div class="more">
      <a :href="withBase('/features/capabilities')">Everything it does, mapped →</a>
      <a :href="withBase('/flows/')">Every flow, played →</a>
    </div>
  </div>
</template>

<style scoped>
.features {
  margin: 20px 0 34px;
}

.group + .group {
  margin-top: 22px;
}

.vp-doc .group-name {
  margin: 0 0 10px;
  padding: 0;
  border: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 12px;
}

.vp-doc .card,
.vp-doc .card:hover {
  text-decoration: none;
  color: inherit;
}

.card {
  --rx: 0deg;
  --ry: 0deg;
  --gx: 50%;
  --gy: 0%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--vp-c-divider);
  border-radius: 14px;
  overflow: hidden;
  background: var(--vp-c-bg-soft);
  transform: perspective(700px) rotateX(var(--rx)) rotateY(var(--ry));
  transition:
    transform 0.25s ease-out,
    border-color 0.25s,
    box-shadow 0.25s;
  will-change: transform;
}

.card:hover {
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 14px 34px -18px color-mix(in srgb, var(--vp-c-brand-1) 60%, transparent);
}

.glass {
  position: relative;
  display: block;
  height: 84px;
  background: var(--hmz-stage-bg);
}

.glare {
  position: absolute;
  inset: 0;
  opacity: 0;
  background: radial-gradient(circle at var(--gx) var(--gy), rgba(255, 255, 255, 0.28), transparent 55%);
  transition: opacity 0.3s;
}

.card:hover .glare {
  opacity: 1;
}

.viz {
  display: block;
  width: 100%;
  height: 100%;
}

.title {
  padding: 10px 12px 12px;
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--vp-c-text-1);
}

.more {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-top: 16px;
  font-size: 14px;
  font-weight: 600;
}

/* Every loop is paused unless the grid is on screen. */
.viz * {
  animation-play-state: paused;
  transform-box: fill-box;
}

.live .viz * {
  animation-play-state: running;
}

/* --- the drawings --- */
.backends .pick {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 2;
  animation: hop 5s steps(1) infinite;
}

@keyframes hop {
  0% { transform: translateX(0); }
  20% { transform: translateX(30px); }
  40% { transform: translateX(60px); }
  60% { transform: translateX(90px); }
  80% { transform: translateX(120px); }
}

.accounts .acct {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 2;
}

.accounts .acct.a {
  stroke: var(--hmz-lane-1);
  animation: spent 4s infinite;
}

.accounts .acct.b {
  stroke: var(--hmz-lane-2);
}

@keyframes spent {
  0%, 45% { opacity: 1; }
  55%, 100% { opacity: 0.25; }
}

.accounts .talk,
.accounts .talk-left {
  fill: none;
  stroke: var(--hmz-lane-2);
  stroke-width: 2;
  stroke-dasharray: 4 4;
}

.accounts .talk-left {
  stroke: var(--hmz-lane-1);
}

.accounts .said {
  fill: var(--hmz-accent);
  offset-path: path('M 60 23 L 96 23 C 110 23 110 49 146 49');
  animation: along 4s ease-in-out infinite;
}

@keyframes along {
  from { offset-distance: 0%; }
  to { offset-distance: 100%; }
}

.surfaces .way {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 1.6;
}

.surfaces .w1 { stroke: var(--hmz-lane-1); }
.surfaces .w2 { stroke: var(--hmz-lane-2); }
.surfaces .w3 { stroke: var(--hmz-lane-3); }

.surfaces .to {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.4;
  stroke-dasharray: 3 5;
  animation: crawl 1.2s linear infinite;
}

.surfaces .one {
  fill: var(--hmz-accent);
  animation: breathe 2.4s ease-in-out infinite;
  transform-origin: center;
}

@keyframes crawl {
  to { stroke-dashoffset: -16; }
}

@keyframes breathe {
  0%, 100% { transform: scale(1); opacity: 0.85; }
  50% { transform: scale(1.12); opacity: 1; }
}

.track {
  fill: var(--hmz-stage-line);
}

.steering .turn {
  fill: var(--hmz-lane-1);
  transform-origin: left center;
  animation: grow 4s linear infinite;
}

@keyframes grow {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}

.steering .line-in {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  animation: drop 4s ease-in infinite;
}

@keyframes drop {
  0%, 35% { transform: translateY(-12px); opacity: 0; }
  45% { opacity: 1; }
  60% { transform: translateY(6px); opacity: 1; }
  70%, 100% { transform: translateY(6px); opacity: 0; }
}

.human .head,
.human .body {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 2;
}

.human .bubble {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-3);
  stroke-width: 1.5;
  animation: pop 3.6s infinite;
  transform-origin: left center;
}

.human .q {
  font-size: 11.5px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-ink);
  animation: pop 3.6s infinite;
}

.human .bubble-2 {
  fill: var(--hmz-lane-3);
  opacity: 0.4;
  animation: pop 3.6s 0.5s infinite;
  transform-origin: left center;
}

@keyframes pop {
  0%, 10% { transform: scale(0.4); opacity: 0; }
  20%, 85% { transform: scale(1); opacity: 1; }
  100% { transform: scale(1); opacity: 0; }
}

.allowances .gauge-track {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 6;
}

.allowances .gauge {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 6;
  stroke-linecap: round;
  stroke-dasharray: 100;
  animation: spend 4s ease-in infinite;
}

@keyframes spend {
  0% { stroke-dashoffset: 100; stroke: var(--hmz-warm); }
  70% { stroke-dashoffset: 0; stroke: var(--hmz-warm); }
  75%, 100% { stroke-dashoffset: 0; stroke: var(--hmz-lane-5); }
}

.allowances .stop {
  font-size: 12px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-ink);
}

.daemon .window,
.daemon .window-bar {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 1.6;
  animation: leave 5s infinite;
}

@keyframes leave {
  0%, 30% { opacity: 1; }
  40%, 70% { opacity: 0.08; }
  80%, 100% { opacity: 1; }
}

.daemon .run {
  fill: var(--hmz-accent);
}

.daemon .run-ring {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  transform-origin: center;
  animation: ping 1.6s ease-out infinite;
}

@keyframes ping {
  from { transform: scale(1); opacity: 0.9; }
  to { transform: scale(2.4); opacity: 0; }
}

.anchor .box {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 1.6;
}

.anchor .box.there {
  stroke: var(--hmz-lane-2);
}

.anchor .wire {
  stroke: var(--hmz-stage-dim);
  stroke-dasharray: 3 3;
}

.anchor .packet {
  fill: var(--hmz-lane-1);
  animation: cross 2.6s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

@keyframes cross {
  0% { transform: translateX(0); opacity: 0; }
  10% { opacity: 1; }
  80% { transform: translateX(38px); opacity: 1; }
  100% { transform: translateX(38px); opacity: 0; }
}

.anchor .key {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2;
}

.tracing .slices rect {
  fill: var(--hmz-lane-1);
  transform-origin: left center;
  animation: slide 4s ease-out infinite;
}

.tracing .slices rect:nth-child(n + 4) { fill: var(--hmz-lane-2); }
.tracing .slices rect:nth-child(n + 7) { fill: var(--hmz-lane-3); }
.tracing .slices rect:nth-child(3n + 2) { animation-delay: 0.6s; }
.tracing .slices rect:nth-child(3n) { animation-delay: 1.2s; }

@keyframes slide {
  0% { transform: scaleX(0); opacity: 0; }
  25%, 90% { transform: scaleX(1); opacity: 0.9; }
  100% { transform: scaleX(1); opacity: 0; }
}

.tracing .head {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  animation: sweep 4s linear infinite;
}

@keyframes sweep {
  to { transform: translateX(140px); }
}

.resuming .seg {
  fill: var(--hmz-lane-1);
}

.resuming .seg.late {
  fill: var(--hmz-accent);
  transform-origin: left center;
  animation: pickup 4s ease-in-out infinite;
}

@keyframes pickup {
  0%, 35% { transform: scaleX(0); }
  80%, 100% { transform: scaleX(1); }
}

.resuming .plug {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
  stroke-dasharray: 3 3;
}

.resuming .round {
  font-size: 11.5px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-dim);
}

.resuming .late-n {
  fill: var(--hmz-accent);
  animation: spent 4s reverse infinite;
}

.flows .loop {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 4;
}

.flows .loop-head {
  fill: var(--hmz-accent);
  offset-path: path('M 80 14 A 22 22 0 1 1 79.99 14');
  animation: along 2.4s linear infinite;
}

.flows .py {
  font-size: 12px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-ink);
}

.concurrency .lane {
  transform-origin: left center;
  opacity: 0.9;
  animation: grow 2.6s ease-in-out infinite;
  animation-delay: calc(var(--d) * -2.6);
}

.shapes .prose rect {
  fill: var(--hmz-stage-dim);
  animation: fade-out 4s infinite;
}

.shapes .fields rect {
  fill: none;
  stroke: var(--hmz-lane-2);
  stroke-width: 1.6;
}

.shapes .fields text {
  font-size: 11.5px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-ink);
}

.shapes .fields {
  animation: fade-in 4s infinite;
}

@keyframes fade-out {
  0%, 35% { opacity: 0.7; }
  55%, 90% { opacity: 0.15; }
  100% { opacity: 0.7; }
}

@keyframes fade-in {
  0%, 35% { opacity: 0.15; transform: translateX(-8px); }
  55%, 90% { opacity: 1; transform: none; }
  100% { opacity: 0.15; }
}

.goals .ring {
  fill: none;
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
}

.goals .r2 { stroke: var(--hmz-warm); }
.goals .r3 { fill: var(--hmz-lane-5); }

.goals .arrow {
  fill: var(--hmz-accent);
  animation: seek 4s cubic-bezier(0.5, 0, 0.2, 1) infinite;
}

@keyframes seek {
  0% { transform: translate(0, 0); opacity: 0; }
  10% { opacity: 1; }
  30% { transform: translate(40px, -18px); }
  55% { transform: translate(70px, 12px); }
  80%, 100% { transform: translate(92px, 0); opacity: 1; }
}

.hooks .track-h {
  stroke: var(--hmz-stage-line);
  stroke-width: 3;
}

.hooks .moment {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.5;
}

.hooks .caught {
  fill: none;
  stroke: var(--hmz-lane-3);
  stroke-width: 2;
  transform-origin: center;
  animation: catch 4s infinite;
}

@keyframes catch {
  0%, 44% { transform: scale(0.5); opacity: 0; }
  50%, 70% { transform: scale(1); opacity: 1; }
  80%, 100% { transform: scale(1.4); opacity: 0; }
}

.hooks .mover {
  fill: var(--hmz-accent);
  animation: walk 4s linear infinite;
}

@keyframes walk {
  0% { transform: translateX(0); }
  45%, 70% { transform: translateX(66px); }
  100% { transform: translateX(132px); }
}

.budgets .cut-bar {
  fill: var(--hmz-lane-1);
  transform-origin: left center;
  animation: cutoff 4s linear infinite;
}

@keyframes cutoff {
  0% { transform: scaleX(0); fill: var(--hmz-lane-1); }
  60% { transform: scaleX(0.68); fill: var(--hmz-lane-1); }
  64%, 100% { transform: scaleX(0.68); fill: var(--hmz-lane-5); }
}

.budgets .cut {
  stroke: var(--hmz-lane-5);
  stroke-width: 2.4;
  stroke-linecap: round;
  animation: fade-in-late 4s infinite;
}

@keyframes fade-in-late {
  0%, 58% { opacity: 0; }
  62%, 100% { opacity: 1; }
}

/* Held still, each drawing is left at a frame that still says its one thing. */
@media (prefers-reduced-motion: reduce) {
  .card {
    transform: none;
    transition: none;
  }

  .viz * {
    animation: none !important;
  }

  .backends .pick { transform: translateX(60px); }
  .steering .turn { transform: scaleX(0.6); }
  .steering .line-in { transform: translateY(6px); }
  .allowances .gauge { stroke-dashoffset: 0; stroke: var(--hmz-lane-5); }
  .daemon .window,
  .daemon .window-bar { opacity: 0.15; }
  .anchor .packet { transform: translateX(20px); }
  .tracing .head { transform: translateX(120px); }
  .resuming .seg.late { transform: scaleX(0.6); }
  .flows .loop-head { offset-distance: 30%; }
  .concurrency .lane { transform: scaleX(0.7); }
  .concurrency .lane:nth-child(2n) { transform: scaleX(0.45); }
  .shapes .prose rect { opacity: 0.15; }
  .goals .arrow { transform: translate(92px, 0); }
  .hooks .mover { transform: translateX(66px); }
  .budgets .cut-bar { transform: scaleX(0.68); fill: var(--hmz-lane-5); }
  .accounts .said { offset-distance: 70%; }
  .accounts .acct.a { opacity: 0.25; }
}

@media (max-width: 640px) {
  .cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  /* Tall enough that a drawing's words, set at 11px in its 160 × 72 box, are drawn at 11px. */
  .glass {
    height: 76px;
  }

  .title {
    font-size: 12.5px;
  }
}

/* Below 380px two cards side by side would draw their words under 11px: one to a row. */
@media (max-width: 379px) {
  .cards {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
