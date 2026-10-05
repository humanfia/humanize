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

// The tracing card's slices: x, y, width, and the agent's row (1-3).
const TRACE = [
  [14, 12, 30, 1],
  [48, 12, 24, 1],
  [86, 12, 40, 1],
  [24, 32, 44, 2],
  [74, 32, 22, 2],
  [104, 32, 30, 2],
  [14, 52, 20, 3],
  [40, 52, 50, 3],
  [96, 52, 36, 3],
] as const

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
              <!-- every CLI in a row; the pick slides from one to the next, and a turn drops from it -->
              <template v-if="card.slug === 'backends'">
                <line class="rail" x1="14" x2="146" y1="60" y2="60" />
                <circle v-for="i in 5" :key="i" class="cli" :cx="20 + (i - 1) * 30" cy="26" r="7" :style="{ fill: `var(--hmz-lane-${i})`, '--i': i - 1 }" />
                <g class="pick">
                  <circle class="ring" cx="20" cy="26" r="12" />
                  <line class="drop" x1="20" x2="20" y1="40" y2="58" />
                </g>
              </template>
              <!-- one account runs out; the same conversation carries on under the other -->
              <template v-else-if="card.slug === 'accounts'">
                <rect class="acct a" x="12" y="12" width="46" height="18" rx="9" />
                <rect class="quota" x="15" y="15" width="40" height="12" rx="6" />
                <rect class="acct b" x="12" y="42" width="46" height="18" rx="9" />
                <path class="talk" d="M 60 21 C 100 21 110 36 140 36 M 60 51 C 100 51 110 36 140 36" />
                <circle class="convo" cx="146" cy="36" r="6" />
                <circle class="said a" cx="0" cy="0" r="3.5" />
                <circle class="said b" cx="0" cy="0" r="3.5" />
              </template>
              <!-- three ways in, one after another reaching the one workspace -->
              <template v-else-if="card.slug === 'surfaces'">
                <rect class="way w1" x="8" y="7" width="38" height="18" rx="4" />
                <rect class="way w2" x="8" y="27" width="38" height="18" rx="4" />
                <rect class="way w3" x="8" y="47" width="38" height="18" rx="4" />
                <text class="way-word" x="27" y="20" text-anchor="middle">tui</text>
                <text class="way-word" x="27" y="40" text-anchor="middle">cli</text>
                <text class="way-word" x="27" y="60" text-anchor="middle">py</text>
                <path class="to" d="M 46 16 C 80 16 90 36 116 36 M 46 36 L 116 36 M 46 56 C 80 56 90 36 116 36" />
                <circle class="mote m1" cx="0" cy="0" r="3" />
                <circle class="mote m2" cx="0" cy="0" r="3" />
                <circle class="mote m3" cx="0" cy="0" r="3" />
                <circle class="one-ping" cx="132" cy="36" r="14" />
                <circle class="one" cx="132" cy="36" r="14" />
              </template>
              <!-- a line said into a turn while it runs: the rest of the turn goes the new way -->
              <template v-else-if="card.slug === 'steering'">
                <rect class="track" x="14" y="44" width="132" height="10" rx="5" />
                <rect class="turn" x="14" y="44" width="72" height="10" rx="5" />
                <rect class="turn-after" x="84" y="44" width="62" height="10" rx="5" />
                <circle class="ripple" cx="85" cy="49" r="6" />
                <path class="line-in" d="M 85 6 l 0 26 m -6 -6 l 6 6 l 6 -6" />
              </template>
              <!-- the flow asks; you answer -->
              <template v-else-if="card.slug === 'human'">
                <circle class="head" cx="30" cy="26" r="9" />
                <path class="body" d="M 14 60 a 16 14 0 0 1 32 0" />
                <g class="ask">
                  <rect class="bubble" x="84" y="8" width="66" height="22" rx="8" />
                  <text class="q" x="117" y="23" text-anchor="middle">done?</text>
                </g>
                <g class="typing">
                  <circle v-for="k in 3" :key="k" class="tdot" :cx="62 + k * 8" cy="51" r="2.2" :style="{ '--k': k }" />
                </g>
                <g class="reply">
                  <rect class="bubble-2" x="54" y="40" width="48" height="22" rx="8" />
                  <text class="a" x="78" y="55" text-anchor="middle">yes</text>
                </g>
              </template>
              <!-- two limits filling at their own pace; the first to its end turns red -->
              <template v-else-if="card.slug === 'allowances'">
                <circle class="gauge-track" cx="80" cy="36" r="26" />
                <circle class="gauge" cx="80" cy="36" r="26" pathLength="100" transform="rotate(-90 80 36)" />
                <circle class="gauge-track thin" cx="80" cy="36" r="19" />
                <circle class="gauge-2" cx="80" cy="36" r="19" pathLength="100" transform="rotate(-90 80 36)" />
                <circle class="gauge-flash" cx="80" cy="36" r="26" />
                <text class="stop" x="80" y="40" text-anchor="middle">$50</text>
              </template>
              <!-- the window closes; the run keeps going; the window comes back to it -->
              <template v-else-if="card.slug === 'daemon'">
                <line class="link" x1="80" x2="106" y1="36" y2="36" />
                <g class="window-g">
                  <rect class="window" x="16" y="12" width="62" height="46" rx="6" />
                  <line class="window-bar" x1="16" x2="78" y1="22" y2="22" />
                  <text class="prompt" x="24" y="42">›_</text>
                </g>
                <circle class="run-ring" cx="120" cy="36" r="10" />
                <circle class="run" cx="120" cy="36" r="10" />
              </template>
              <!-- the work goes over; the result comes back; the key never leaves -->
              <template v-else-if="card.slug === 'anchor'">
                <rect class="box" x="8" y="16" width="46" height="40" rx="7" />
                <rect class="box there" x="106" y="16" width="46" height="40" rx="7" />
                <text class="there-word" x="129" y="41" text-anchor="middle">›_</text>
                <line class="wire" x1="54" x2="106" y1="36" y2="36" />
                <rect class="packet out" x="54" y="27" width="12" height="8" rx="2" />
                <rect class="packet back" x="94" y="37" width="12" height="8" rx="2" />
                <g class="key">
                  <circle cx="24" cy="36" r="5" />
                  <path d="M 29 36 h 12 m -4 0 v 4" />
                </g>
              </template>
              <!-- a playhead crosses the run; each slice is drawn as it is reached -->
              <template v-else-if="card.slug === 'tracing'">
                <g class="slices">
                  <rect
                    v-for="(s, i) in TRACE"
                    :key="i"
                    :class="`row-${s[3]}`"
                    :x="s[0]"
                    :y="s[1]"
                    :width="s[2]"
                    height="10"
                    rx="2"
                    :style="{ '--d': `${((s[0] - 10) / 140) * 4}s` }"
                  />
                </g>
                <line class="head" x1="10" x2="10" y1="6" y2="66" />
              </template>
              <!-- a run stops at round 40; picked up, it carries on at 41 -->
              <template v-else-if="card.slug === 'resuming'">
                <rect class="seg" x="12" y="30" width="62" height="12" rx="4" />
                <rect class="seg late" x="86" y="30" width="62" height="12" rx="4" />
                <path class="plug" d="M 80 18 v 36" />
                <path class="bridge" pathLength="30" d="M 72 30 C 76 18 84 18 88 30" />
                <text class="round" x="44" y="22" text-anchor="middle">40</text>
                <text class="round late-n" x="116" y="22" text-anchor="middle">41</text>
              </template>
              <!-- a loop in plain Python: round and round, a comet's tail behind it -->
              <template v-else-if="card.slug === 'flows'">
                <circle class="loop" cx="80" cy="36" r="22" />
                <circle class="loop-tail" cx="80" cy="36" r="22" pathLength="100" transform="rotate(-90 80 36)" />
                <circle class="loop-head" cx="80" cy="14" r="5" />
                <text class="py" x="80" y="41" text-anchor="middle">def</text>
              </template>
              <!-- five conversations, each at its own pace, all at once -->
              <template v-else-if="card.slug === 'concurrency'">
                <rect v-for="i in 5" :key="`t${i}`" class="lane-track" x="16" :y="6 + (i - 1) * 13" width="128" height="8" rx="4" />
                <rect
                  v-for="i in 5"
                  :key="i"
                  class="lane"
                  x="16"
                  :y="6 + (i - 1) * 13"
                  width="128"
                  height="8"
                  rx="4"
                  :style="{ '--d': `${(i * 0.37) % 1}`, fill: `var(--hmz-lane-${i})` }"
                />
              </template>
              <!-- prose in, typed fields out -->
              <template v-else-if="card.slug === 'shapes'">
                <g class="prose">
                  <rect x="12" y="14" width="66" height="5" rx="2" />
                  <rect x="12" y="26" width="54" height="5" rx="2" />
                  <rect x="12" y="38" width="62" height="5" rx="2" />
                  <rect x="12" y="50" width="40" height="5" rx="2" />
                </g>
                <path class="arrow-to" d="M 80 36 h 10 m -4 -4 l 4 4 l -4 4" />
                <g class="field f1">
                  <rect x="96" y="12" width="56" height="20" rx="5" />
                  <text x="124" y="26" text-anchor="middle">done ✓</text>
                </g>
                <g class="field f2">
                  <rect x="96" y="40" width="56" height="20" rx="5" />
                  <text x="124" y="54" text-anchor="middle">notes</text>
                </g>
              </template>
              <!-- it wanders, then closes on the target, and the target answers -->
              <template v-else-if="card.slug === 'goals'">
                <circle class="ring r1" cx="118" cy="36" r="24" />
                <circle class="ring r2" cx="118" cy="36" r="15" />
                <circle class="ring r3" cx="118" cy="36" r="6" />
                <circle class="hit" cx="118" cy="36" r="24" />
                <path class="seek-path" d="M 20 36 C 40 12 56 12 62 26 S 84 54 96 40 S 108 34 118 36" />
                <circle class="arrow" cx="0" cy="0" r="5" />
              </template>
              <!-- a turn walks past its moments; a hook catches the one it hangs on -->
              <template v-else-if="card.slug === 'hooks'">
                <line class="track-h" x1="14" x2="146" y1="40" y2="40" />
                <circle v-for="i in 5" :key="i" class="moment" :cx="14 + (i - 1) * 33" cy="40" r="4" />
                <path class="hook" d="M 80 4 v 16 a 6 6 0 0 1 -12 0" />
                <circle class="caught" cx="80" cy="40" r="10" />
                <circle class="mover" cx="14" cy="40" r="5" />
              </template>
              <!-- one turn, cut where its limit is -->
              <template v-else-if="card.slug === 'budgets'">
                <rect class="track" x="14" y="26" width="132" height="12" rx="6" />
                <rect class="cut-bar" x="14" y="26" width="132" height="12" rx="6" />
                <line class="limit" x1="104" x2="104" y1="18" y2="46" />
                <line class="cut" x1="104" x2="104" y1="12" y2="52" />
                <text class="cap" x="104" y="66" text-anchor="middle">limit</text>
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
  background: radial-gradient(circle at var(--gx) var(--gy), color-mix(in srgb, var(--vp-c-white) 28%, transparent), transparent 55%);
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

/* --- the drawings ---
   Each one a loop of a few seconds, cut in beats like the scenes: something is drawn in, moves,
   lands, and the drawing says what landing means. The beats of one drawing share a period, so
   they stay in step loop after loop. */

/* backends: the pick slides from CLI to CLI, the one picked swells, and a turn drops from it. */
.backends .rail {
  stroke: var(--hmz-stage-line);
  stroke-width: 2;
  stroke-linecap: round;
}

.backends .cli {
  transform-origin: center;
  animation: picked 5s calc(var(--i) * 1s) cubic-bezier(0.16, 1, 0.3, 1) infinite both;
}

@keyframes picked {
  0%, 4% { transform: scale(1); }
  9% { transform: scale(1.3); }
  18%, 100% { transform: scale(1); }
}

.backends .pick {
  animation: hop 5s infinite;
}

@keyframes hop {
  0%, 14% { transform: translateX(0); animation-timing-function: cubic-bezier(0.7, 0, 0.2, 1); }
  20%, 34% { transform: translateX(30px); animation-timing-function: cubic-bezier(0.7, 0, 0.2, 1); }
  40%, 54% { transform: translateX(60px); animation-timing-function: cubic-bezier(0.7, 0, 0.2, 1); }
  60%, 74% { transform: translateX(90px); animation-timing-function: cubic-bezier(0.7, 0, 0.2, 1); }
  80%, 94% { transform: translateX(120px); animation-timing-function: cubic-bezier(0.7, 0, 0.2, 1); }
  100% { transform: translateX(0); }
}

.backends .ring {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 2;
}

.backends .drop {
  stroke: var(--hmz-accent);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-dasharray: 6 30;
  animation: drop-turn 1s infinite;
}

@keyframes drop-turn {
  0%, 12% { stroke-dashoffset: 6; }
  65%, 100% { stroke-dashoffset: -18; }
}

/* accounts: the first account's quota fills and it is spent; the conversation goes on under the
   second, to the same place. */
.accounts .acct {
  fill: none;
  stroke-width: 2;
}

.accounts .acct.a {
  stroke: var(--hmz-lane-1);
  animation: spent 4s infinite;
}

.accounts .acct.b {
  stroke: var(--hmz-lane-2);
  animation: wake 4s infinite;
}

@keyframes spent {
  0%, 44% { opacity: 1; }
  52%, 94% { opacity: 0.3; }
  100% { opacity: 1; }
}

@keyframes wake {
  0%, 44% { opacity: 0.4; }
  52%, 94% { opacity: 1; }
  100% { opacity: 0.4; }
}

.accounts .quota {
  fill: color-mix(in srgb, var(--hmz-lane-1) 45%, transparent);
  transform-origin: left center;
  animation: quota 4s infinite;
}

@keyframes quota {
  0% { transform: scaleX(0); fill: color-mix(in srgb, var(--hmz-lane-1) 45%, transparent); }
  42% { transform: scaleX(1); fill: color-mix(in srgb, var(--hmz-lane-1) 45%, transparent); }
  48%, 94% { transform: scaleX(1); fill: color-mix(in srgb, var(--hmz-lane-5) 55%, transparent); opacity: 0.6; }
  100% { transform: scaleX(0); opacity: 0; }
}

.accounts .talk {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.6;
  stroke-dasharray: 3 4;
}

.accounts .convo {
  fill: var(--hmz-accent);
  transform-origin: center;
  animation: arrive 2s 1.6s infinite;
}

@keyframes arrive {
  0%, 100% { transform: scale(1); }
  10% { transform: scale(1.35); }
  30% { transform: scale(1); }
}

.accounts .said.a {
  fill: var(--hmz-lane-1);
  offset-path: path('M 60 21 C 100 21 110 36 140 36');
  animation: said-a 4s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

.accounts .said.b {
  fill: var(--hmz-lane-2);
  offset-path: path('M 60 51 C 100 51 110 36 140 36');
  animation: said-b 4s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

@keyframes said-a {
  0% { offset-distance: 0%; opacity: 0; }
  4% { opacity: 1; }
  40% { offset-distance: 100%; opacity: 1; }
  43%, 100% { offset-distance: 100%; opacity: 0; }
}

@keyframes said-b {
  0%, 50% { offset-distance: 0%; opacity: 0; }
  54% { opacity: 1; }
  90% { offset-distance: 100%; opacity: 1; }
  93%, 100% { offset-distance: 100%; opacity: 0; }
}

/* surfaces: one mote down each way in, in turn, and the workspace answers each arrival. */
.surfaces .way {
  fill: var(--hmz-stage-card);
  stroke-width: 1.6;
}

.surfaces .w1 { stroke: var(--hmz-lane-1); }
.surfaces .w2 { stroke: var(--hmz-lane-2); }
.surfaces .w3 { stroke: var(--hmz-lane-3); }

.surfaces .way-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.surfaces .to {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.4;
}

.surfaces .mote {
  animation: travel 2.4s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

.surfaces .m1 { fill: var(--hmz-lane-1); offset-path: path('M 46 16 C 80 16 90 36 116 36'); }
.surfaces .m2 { fill: var(--hmz-lane-2); offset-path: path('M 46 36 L 116 36'); animation-delay: 0.8s; }
.surfaces .m3 { fill: var(--hmz-lane-3); offset-path: path('M 46 56 C 80 56 90 36 116 36'); animation-delay: 1.6s; }

@keyframes travel {
  0% { offset-distance: 0%; opacity: 0; }
  4% { opacity: 1; }
  33% { offset-distance: 100%; opacity: 1; }
  36%, 100% { offset-distance: 100%; opacity: 0; }
}

.surfaces .one {
  fill: var(--hmz-accent);
}

.surfaces .one-ping {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  transform-origin: center;
  animation: ping 0.8s ease-out infinite;
}

/* steering: a line is said into the turn as it runs, and the rest of the turn goes the new way. */
.track {
  fill: var(--hmz-stage-line);
}

.steering .turn {
  fill: var(--hmz-lane-1);
  transform-origin: left center;
  animation: steer-before 4s infinite;
}

@keyframes steer-before {
  0% { transform: scaleX(0); opacity: 1; }
  46%, 94% { transform: scaleX(1); opacity: 1; }
  100% { transform: scaleX(1); opacity: 0; }
}

.steering .turn-after {
  fill: var(--hmz-warm);
  transform-origin: left center;
  animation: steer-after 4s infinite;
}

@keyframes steer-after {
  0%, 52% { transform: scaleX(0); opacity: 1; }
  92%, 94% { transform: scaleX(1); opacity: 1; }
  100% { transform: scaleX(1); opacity: 0; }
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
  0%, 26% { transform: translateY(-12px); opacity: 0; }
  34% { opacity: 1; }
  48% { transform: translateY(6px); opacity: 1; }
  60%, 100% { transform: translateY(6px); opacity: 0; }
}

.steering .ripple {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2;
  transform-origin: center;
  animation: ripple 4s ease-out infinite;
}

@keyframes ripple {
  0%, 47% { transform: scale(0.4); opacity: 0; }
  50% { transform: scale(0.6); opacity: 1; }
  70%, 100% { transform: scale(2.2); opacity: 0; }
}

/* human: the flow asks, you type, you answer. */
.human .head,
.human .body {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 2;
}

.human .ask {
  transform-origin: 100% 100%;
  animation: pop 4s cubic-bezier(0.16, 1, 0.3, 1) infinite;
}

.human .bubble {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-3);
  stroke-width: 1.5;
}

.human .q {
  font-size: 11.5px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-ink);
}

.human .typing {
  animation: typing 4s infinite;
}

@keyframes typing {
  0%, 24% { opacity: 0; }
  28%, 42% { opacity: 1; }
  46%, 100% { opacity: 0; }
}

.human .tdot {
  fill: var(--hmz-stage-dim);
  animation: bob 0.6s calc(var(--k) * 0.15s) ease-in-out infinite alternate;
}

@keyframes bob {
  to { transform: translateY(-3px); }
}

.human .reply {
  transform-origin: 0% 100%;
  animation: reply 4s cubic-bezier(0.16, 1, 0.3, 1) infinite;
}

.human .bubble-2 {
  fill: var(--hmz-lane-3);
}

.human .a {
  font-size: 11.5px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--vp-c-bg);
}

@keyframes pop {
  0%, 6% { transform: scale(0.4); opacity: 0; }
  16%, 90% { transform: scale(1); opacity: 1; }
  100% { transform: scale(1); opacity: 0; }
}

@keyframes reply {
  0%, 44% { transform: scale(0.4); opacity: 0; }
  54%, 90% { transform: scale(1); opacity: 1; }
  100% { transform: scale(1); opacity: 0; }
}

/* allowances: cost and tokens fill at their own pace; cost reaches its end first, and flashes. */
.allowances .gauge-track {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 6;
}

.allowances .gauge-track.thin {
  stroke-width: 4;
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
  74%, 94% { stroke-dashoffset: 0; stroke: var(--hmz-lane-5); }
  100% { stroke-dashoffset: 100; stroke: var(--hmz-lane-5); }
}

.allowances .gauge-2 {
  fill: none;
  stroke: var(--hmz-lane-3);
  stroke-width: 4;
  stroke-linecap: round;
  stroke-dasharray: 100;
  animation: spend-2 4s ease-in-out infinite;
}

@keyframes spend-2 {
  0% { stroke-dashoffset: 100; }
  70%, 94% { stroke-dashoffset: 52; }
  100% { stroke-dashoffset: 100; }
}

.allowances .gauge-flash {
  fill: none;
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
  transform-origin: center;
  animation: flash 4s ease-out infinite;
}

@keyframes flash {
  0%, 70% { transform: scale(1); opacity: 0; }
  72% { transform: scale(1); opacity: 0.9; }
  90%, 100% { transform: scale(1.45); opacity: 0; }
}

.allowances .stop {
  font-size: 12px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-ink);
  animation: stop-word 4s infinite;
}

@keyframes stop-word {
  0%, 71% { fill: var(--hmz-stage-ink); }
  73%, 96% { fill: var(--hmz-lane-5); }
  100% { fill: var(--hmz-stage-ink); }
}

/* daemon: the terminal closes, the run goes on pinging, the terminal comes back and re-attaches. */
.daemon .window-g {
  transform-origin: center;
  animation: leave 5s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

@keyframes leave {
  0%, 30% { opacity: 1; transform: scale(1); }
  40%, 68% { opacity: 0.08; transform: scale(0.86); }
  80%, 100% { opacity: 1; transform: scale(1); }
}

.daemon .window,
.daemon .window-bar {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 1.6;
}

.daemon .prompt {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-accent);
}

.daemon .link {
  stroke: var(--hmz-accent);
  stroke-width: 1.6;
  stroke-dasharray: 3 3;
  animation:
    link 5s infinite,
    crawl 0.8s linear infinite;
}

@keyframes link {
  0%, 30% { opacity: 1; }
  36%, 74% { opacity: 0; }
  82%, 100% { opacity: 1; }
}

@keyframes crawl {
  to { stroke-dashoffset: -12; }
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

/* anchor: the work crosses to the other machine, the result crosses back, the key stays home. */
.anchor .box {
  fill: none;
  stroke: var(--hmz-stage-ink);
  stroke-width: 1.6;
}

.anchor .box.there {
  stroke: var(--hmz-lane-2);
}

.anchor .there-word {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-lane-2);
}

.anchor .wire {
  stroke: var(--hmz-stage-dim);
  stroke-dasharray: 3 3;
}

.anchor .packet.out {
  fill: var(--hmz-lane-1);
  animation: go-out 4s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

.anchor .packet.back {
  fill: var(--hmz-lane-2);
  animation: come-back 4s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

@keyframes go-out {
  0% { transform: translateX(0); opacity: 0; }
  8% { opacity: 1; }
  42% { transform: translateX(40px); opacity: 1; }
  48%, 100% { transform: translateX(40px); opacity: 0; }
}

@keyframes come-back {
  0%, 50% { transform: translateX(0); opacity: 0; }
  56% { opacity: 1; }
  90% { transform: translateX(-40px); opacity: 1; }
  96%, 100% { transform: translateX(-40px); opacity: 0; }
}

.anchor .key circle,
.anchor .key path {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 2;
  stroke-linecap: round;
}

/* tracing: the playhead crosses, and each slice is drawn the moment it is reached, then fades
   like a trace on a scope. */
.tracing .slices rect {
  transform-origin: left center;
  animation: slide 4s var(--d) cubic-bezier(0.16, 1, 0.3, 1) infinite both;
}

.tracing .slices .row-1 { fill: var(--hmz-lane-1); }
.tracing .slices .row-2 { fill: var(--hmz-lane-2); }
.tracing .slices .row-3 { fill: var(--hmz-lane-3); }

@keyframes slide {
  0% { transform: scaleX(0); opacity: 0.9; }
  12% { transform: scaleX(1); opacity: 0.9; }
  70% { transform: scaleX(1); opacity: 0.9; }
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

/* resuming: round 40 runs and stops; a bridge is drawn across the break; round 41 carries on. */
.resuming .seg {
  fill: var(--hmz-lane-1);
  transform-origin: left center;
  animation: early 4s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

@keyframes early {
  0% { transform: scaleX(0); opacity: 1; }
  30%, 92% { transform: scaleX(1); opacity: 1; }
  100% { transform: scaleX(1); opacity: 0; }
}

.resuming .seg.late {
  fill: var(--hmz-accent);
  animation: pickup 4s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

@keyframes pickup {
  0%, 50% { transform: scaleX(0); opacity: 1; }
  86%, 92% { transform: scaleX(1); opacity: 1; }
  100% { transform: scaleX(1); opacity: 0; }
}

.resuming .plug {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
  stroke-dasharray: 3 3;
  animation: plug 4s infinite;
}

@keyframes plug {
  0%, 29% { opacity: 0; }
  33%, 92% { opacity: 1; }
  100% { opacity: 0; }
}

.resuming .bridge {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-dasharray: 30 30;
  animation: bridge 4s cubic-bezier(0.7, 0, 0.2, 1) infinite;
}

@keyframes bridge {
  0%, 40% { stroke-dashoffset: 30; opacity: 1; }
  50%, 92% { stroke-dashoffset: 0; opacity: 1; }
  100% { stroke-dashoffset: 0; opacity: 0; }
}

.resuming .round {
  font-size: 11.5px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-dim);
}

.resuming .late-n {
  fill: var(--hmz-accent);
  animation: late-n 4s infinite;
}

@keyframes late-n {
  0%, 44% { opacity: 0.15; }
  52%, 92% { opacity: 1; }
  100% { opacity: 0.15; }
}

/* flows: the loop goes round, a comet's tail behind its head. */
.flows .loop {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 4;
}

.flows .loop-tail {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 4;
  stroke-linecap: round;
  stroke-dasharray: 22 78;
  opacity: 0.55;
  animation: tail 2.4s linear infinite;
}

@keyframes tail {
  from { stroke-dashoffset: 22; }
  to { stroke-dashoffset: -78; }
}

.flows .loop-head {
  fill: var(--hmz-accent);
  offset-path: path('M 80 14 A 22 22 0 1 1 79.99 14');
  animation: along 2.4s linear infinite;
}

@keyframes along {
  from { offset-distance: 0%; }
  to { offset-distance: 100%; }
}

.flows .py {
  font-size: 12px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-ink);
}

/* concurrency: five conversations, each at its own pace, all at once. */
.concurrency .lane-track {
  fill: var(--hmz-stage-line);
}

.concurrency .lane {
  transform-origin: left center;
  animation: conc 2.6s cubic-bezier(0.45, 0, 0.2, 1) infinite;
  animation-delay: calc(var(--d) * -2.6s);
}

@keyframes conc {
  0% { transform: scaleX(0); opacity: 0.9; }
  72% { transform: scaleX(1); opacity: 0.9; }
  100% { transform: scaleX(1); opacity: 0; }
}

/* shapes: the prose fades as the answer settles into its typed fields, one after the other. */
.shapes .prose rect {
  fill: var(--hmz-stage-dim);
  animation: fade-out 4s infinite;
}

.shapes .arrow-to {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
  animation: nudge 4s cubic-bezier(0.16, 1, 0.3, 1) infinite;
}

@keyframes nudge {
  0%, 28% { transform: translateX(-6px); opacity: 0; }
  42%, 90% { transform: none; opacity: 1; }
  100% { opacity: 0; }
}

.shapes .field rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-2);
  stroke-width: 1.6;
}

.shapes .field text {
  font-size: 11.5px;
  font-weight: 700;
  font-family: var(--vp-font-family-mono);
  fill: var(--hmz-stage-ink);
}

.shapes .field {
  animation: fade-in 4s cubic-bezier(0.16, 1, 0.3, 1) infinite;
}

.shapes .f2 {
  animation-delay: 0.3s;
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

/* goals: the arrow wanders, closes on the target, and the target answers with a ring. */
.goals .ring {
  fill: none;
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
}

.goals .r2 { stroke: var(--hmz-warm); }
.goals .r3 { fill: var(--hmz-lane-5); }

.goals .seek-path {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 1.4;
  stroke-dasharray: 2 4;
}

.goals .arrow {
  fill: var(--hmz-accent);
  offset-path: path('M 20 36 C 40 12 56 12 62 26 S 84 54 96 40 S 108 34 118 36');
  animation: seek 4s cubic-bezier(0.5, 0, 0.2, 1) infinite;
}

@keyframes seek {
  0% { offset-distance: 0%; opacity: 0; }
  8% { opacity: 1; }
  78%, 94% { offset-distance: 100%; opacity: 1; }
  100% { offset-distance: 100%; opacity: 0; }
}

.goals .hit {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  transform-origin: center;
  animation: hit 4s ease-out infinite;
}

@keyframes hit {
  0%, 77% { transform: scale(0.5); opacity: 0; }
  80% { transform: scale(0.9); opacity: 1; }
  100% { transform: scale(1.5); opacity: 0; }
}

/* hooks: the turn walks past its moments; the hook drops onto the one it hangs on and catches it. */
.hooks .track-h {
  stroke: var(--hmz-stage-line);
  stroke-width: 3;
}

.hooks .moment {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.5;
}

.hooks .hook {
  fill: none;
  stroke: var(--hmz-lane-3);
  stroke-width: 2.2;
  stroke-linecap: round;
  animation: hook 4s cubic-bezier(0.16, 1, 0.3, 1) infinite;
}

@keyframes hook {
  0%, 28% { transform: translateY(-14px); opacity: 0; }
  42%, 70% { transform: none; opacity: 1; }
  82%, 100% { transform: translateY(-14px); opacity: 0; }
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

/* budgets: the turn runs up to its limit, and the blade comes down there. */
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

.budgets .limit {
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.4;
  stroke-dasharray: 2 3;
}

.budgets .cut {
  stroke: var(--hmz-lane-5);
  stroke-width: 2.4;
  stroke-linecap: round;
  transform-origin: center;
  animation: blade 4s cubic-bezier(0.16, 1, 0.3, 1) infinite;
}

@keyframes blade {
  0%, 59% { transform: scaleY(0); opacity: 0; }
  63% { transform: scaleY(1.15); opacity: 1; }
  68%, 100% { transform: scaleY(1); opacity: 1; }
}

.budgets .cap {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.06em;
  fill: var(--hmz-stage-dim);
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
  .backends .cli:nth-child(4) { transform: scale(1.3); }
  .backends .drop { stroke-dashoffset: -6; }
  .accounts .acct.a { opacity: 0.3; }
  .accounts .quota { fill: color-mix(in srgb, var(--hmz-lane-5) 55%, transparent); opacity: 0.6; }
  .accounts .said.a { opacity: 0; }
  .accounts .said.b { offset-distance: 70%; }
  .surfaces .m1 { offset-distance: 75%; }
  .surfaces .m2 { offset-distance: 45%; }
  .surfaces .m3 { offset-distance: 15%; }
  .steering .turn-after { transform: scaleX(0.5); }
  .steering .line-in { transform: translateY(6px); }
  .steering .ripple { opacity: 0; }
  .human .typing { opacity: 0; }
  .allowances .gauge { stroke-dashoffset: 0; stroke: var(--hmz-lane-5); }
  .allowances .gauge-2 { stroke-dashoffset: 52; }
  .allowances .gauge-flash { opacity: 0; }
  .allowances .stop { fill: var(--hmz-lane-5); }
  .daemon .window-g { opacity: 0.12; }
  .daemon .link { opacity: 0; }
  .daemon .run-ring { opacity: 0; }
  .anchor .packet.out { transform: translateX(20px); }
  .anchor .packet.back { opacity: 0; }
  .tracing .head { transform: translateX(120px); }
  .resuming .seg.late { transform: scaleX(0.6); }
  .flows .loop-head { offset-distance: 30%; }
  .flows .loop-tail { stroke-dashoffset: -8; }
  .concurrency .lane { transform: scaleX(0.7); }
  .concurrency .lane:nth-child(2n) { transform: scaleX(0.45); }
  .shapes .prose rect { opacity: 0.15; }
  .goals .arrow { offset-distance: 100%; }
  .goals .hit { opacity: 0; }
  .hooks .mover { transform: translateX(66px); }
  .budgets .cut-bar { transform: scaleX(0.68); fill: var(--hmz-lane-5); }
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
