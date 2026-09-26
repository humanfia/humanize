<script setup lang="ts">
// The catalogue on /flows/, and the chooser on top of it: pick what you want done, and the
// cards narrow to the flows that do it, with a line saying which to start with.
//
// The list is `theme/flows.ts`, the same one the diagrams on each flow's page are played from,
// and the small drawing on each card is that flow's own loop. The drawings are CSS animations:
// they hold still under reduced motion, and pause while the grid is scrolled off screen.
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'

import { FLOWS, JOBS, type Job } from '../flows'

const job = ref<Job | 'all'>('all')
const shown = computed(() =>
  job.value === 'all' ? FLOWS : FLOWS.filter((one) => one.jobs.includes(job.value as Job)),
)

/** The advice for the picked job, cut at its backticks so the names can be set as code. */
const hint = computed(() => {
  const said = JOBS.find((one) => one.id === job.value)?.hint ?? ''
  return said.split('`').map((text, n) => ({ text, code: n % 2 === 1 }))
})

const root = ref<HTMLElement | null>(null)
const idle = ref(false)
let watcher: IntersectionObserver | undefined

onMounted(() => {
  watcher = new IntersectionObserver((seen) => (idle.value = !seen[0].isIntersecting))
  if (root.value) watcher.observe(root.value)
})

onUnmounted(() => watcher?.disconnect())
</script>

<template>
  <div ref="root" class="flows" :class="{ idle }">
    <div class="ask" role="group" aria-label="What do you want to do?">
      <span class="q">What do you want to do?</span>
      <button type="button" :class="{ on: job === 'all' }" :aria-pressed="job === 'all'" @click="job = 'all'">
        show every flow
      </button>
      <button
        v-for="one in JOBS"
        :key="one.id"
        type="button"
        :class="{ on: job === one.id }"
        :aria-pressed="job === one.id"
        @click="job = one.id"
      >
        {{ one.said }}
      </button>
    </div>

    <p v-show="job !== 'all'" class="hint" aria-live="polite">
      <template v-for="(part, n) in hint" :key="n">
        <code v-if="part.code">{{ part.text }}</code>
        <template v-else>{{ part.text }}</template>
      </template>
    </p>

    <div class="grid">
      <a v-for="flow in shown" :key="flow.name" class="card" :href="withBase(flow.link)">
        <svg class="glyph" :class="flow.family" viewBox="0 0 132 40" aria-hidden="true">
          <!-- one agent, one session, and you at the other end of it -->
          <template v-if="flow.family === 'talk'">
            <rect class="them a" x="8" y="6" width="58" height="9" rx="4.5" />
            <rect class="you a" x="58" y="21" width="46" height="9" rx="4.5" />
            <circle class="caret" cx="112" cy="25.5" r="3" />
          </template>

          <!-- a session of its own each round -->
          <template v-else-if="flow.family === 'fresh'">
            <rect v-for="n in 4" :key="n" class="round" :style="{ '--n': n }" :x="4 + (n - 1) * 32" y="12" width="24" height="16" rx="5" />
          </template>

          <!-- one session, getting longer -->
          <template v-else-if="flow.family === 'held'">
            <rect class="rail" x="6" y="17" width="120" height="6" rx="3" />
            <rect class="grow" x="6" y="17" width="120" height="6" rx="3" />
            <circle v-for="n in 4" :key="n" class="beat" :style="{ '--n': n }" :cx="18 + (n - 1) * 32" cy="20" r="3.5" />
          </template>

          <!-- the task once, then a nudge a round -->
          <template v-else-if="flow.family === 'nudge'">
            <rect class="rail" x="6" y="17" width="120" height="6" rx="3" />
            <rect class="task" x="6" y="13" width="28" height="14" rx="5" />
            <rect v-for="n in 3" :key="n" class="tap" :style="{ '--n': n }" :x="44 + (n - 1) * 28" y="15" width="20" height="10" rx="4" />
          </template>

          <!-- the model deciding a turn is not over -->
          <template v-else-if="flow.family === 'goal'">
            <circle class="ring" cx="66" cy="20" r="13" />
            <circle class="sweep" cx="66" cy="20" r="13" />
            <circle class="core" cx="66" cy="20" r="3.5" />
          </template>

          <!-- two agents, alternating -->
          <template v-else-if="flow.family === 'pair'">
            <line class="rail" x1="6" y1="12" x2="126" y2="12" />
            <line class="rail" x1="6" y1="28" x2="126" y2="28" />
            <circle class="one" cx="24" cy="12" r="5" />
            <circle class="two" cx="24" cy="28" r="5" />
          </template>

          <!-- one that remembers, one that must not -->
          <template v-else-if="flow.family === 'review'">
            <rect class="actor" x="6" y="8" width="86" height="9" rx="4.5" />
            <rect v-for="n in 3" :key="n" class="look" :style="{ '--n': n }" :x="30 + (n - 1) * 32" y="24" width="22" height="8" rx="4" />
            <path class="back" d="M 108 28 C 122 28 122 12 100 12" />
          </template>

          <!-- an idea, a plan, and a build under review -->
          <template v-else-if="flow.family === 'phases'">
            <rect v-for="n in 3" :key="n" class="phase" :style="{ '--n': n }" :x="6 + (n - 1) * 44" y="11" width="34" height="18" rx="5" />
            <circle class="token" cy="20" r="3.5" />
          </template>

          <!-- three lanes at once, and one of them owns the tree -->
          <template v-else>
            <line v-for="n in 3" :key="n" class="rail" x1="6" :y1="8 + (n - 1) * 12" x2="126" :y2="8 + (n - 1) * 12" />
            <circle v-for="n in 3" :key="`d${n}`" class="runner" :style="{ '--n': n }" cx="6" :cy="8 + (n - 1) * 12" r="4" />
          </template>
        </svg>

        <div class="head">
          <code>{{ flow.phases ? `${flow.name}:<phase>` : flow.name }}</code>
          <span v-if="flow.phases" class="runs">{{ flow.phases.join(' · ') }}</span>
        </div>
        <p class="said">{{ flow.said }}</p>
        <dl>
          <div><dt>-a</dt><dd>{{ flow.roles }}</dd></div>
          <div><dt>ends</dt><dd>{{ flow.ends }}</dd></div>
          <div><dt>--resume</dt><dd>{{ flow.keeps || 'starts afresh' }}</dd></div>
        </dl>
      </a>
    </div>

    <p class="foot">
      Every run also stops when its budget is spent. Only <code>chat</code> may run without one.
    </p>
  </div>
</template>

<style scoped>
.ask {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.ask .q {
  flex-basis: 100%;
  font-size: 13px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}

.ask button {
  padding: 5px 13px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 20px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12.5px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s, background 0.2s;
}

.ask button:hover {
  color: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

.ask button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.hint {
  margin: 0 0 16px;
  padding: 10px 14px;
  border-left: 3px solid var(--vp-c-brand-1);
  border-radius: 0 10px 10px 0;
  background: var(--vp-c-brand-soft);
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
}

.hint code {
  font-size: 12.5px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 14px;
}

.card {
  display: block;
  padding: 12px 16px 16px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
  color: inherit;
  text-decoration: none;
  transition: transform 0.25s, border-color 0.25s, box-shadow 0.25s;
}

.card:hover {
  transform: translateY(-3px);
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 12px 32px -20px var(--vp-c-brand-1);
}

.glyph {
  display: block;
  width: 100%;
  height: 40px;
  margin-bottom: 10px;
}

/* The name gets a line of its own: `parallel_flame_chase_git_pr` is wider than half a card. */
.head code {
  display: block;
  padding: 0;
  background: none;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--vp-c-brand-1);
  overflow-wrap: anywhere;
}

.head .runs {
  display: block;
  margin-top: 2px;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.said {
  margin: 8px 0 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

dl {
  margin: 12px 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--vp-c-divider);
  font-size: 11.5px;
  line-height: 1.45;
}

dl div {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

dt {
  flex: none;
  width: 62px;
  font-family: var(--vp-font-family-mono);
  font-size: 10.5px;
  color: var(--vp-c-text-3);
}

dd {
  flex: 1;
  margin: 0;
  color: var(--vp-c-text-2);
}

.foot {
  margin: 12px 0 0;
  font-size: 12.5px;
  color: var(--vp-c-text-3);
}

/* --------------------------------------------------------------------------------------
   The small drawings. Each is the loop the flow is, at the size of a thumbnail.
   -------------------------------------------------------------------------------------- */

.glyph line.rail,
.glyph rect.rail {
  stroke: var(--hmz-grid);
  fill: var(--vp-c-default-soft);
  stroke-width: 1.4;
}

/* talk */
.talk .them {
  fill: var(--hmz-lane-1);
  opacity: 0.75;
  animation: say 3.2s ease-in-out infinite;
}

.talk .you {
  fill: var(--hmz-lane-6);
  opacity: 0.6;
  animation: say 3.2s ease-in-out infinite 1.6s;
}

.talk .caret {
  fill: var(--hmz-accent);
  animation: wink 1s steps(2) infinite;
}

@keyframes say {
  0%,
  100% {
    opacity: 0.25;
  }
  20%,
  45% {
    opacity: 0.9;
  }
}

@keyframes wink {
  50% {
    opacity: 0;
  }
}

/* fresh */
.fresh .round {
  fill: var(--vp-c-bg);
  stroke: var(--hmz-lane-1);
  stroke-width: 1.4;
  animation: pop 3.2s ease-in-out infinite;
  animation-delay: calc((var(--n) - 1) * 0.6s);
  transform-origin: center;
  transform-box: fill-box;
}

@keyframes pop {
  0%,
  100% {
    opacity: 0.2;
    transform: scale(0.82);
  }
  12%,
  30% {
    opacity: 1;
    transform: scale(1);
  }
}

/* held */
.held .grow {
  fill: var(--hmz-lane-2);
  opacity: 0.55;
  transform-origin: left center;
  transform-box: fill-box;
  animation: stretch 3.6s ease-in-out infinite;
}

.held .beat {
  fill: var(--hmz-lane-2);
  animation: pop 3.6s ease-in-out infinite;
  animation-delay: calc((var(--n) - 1) * 0.75s);
  transform-origin: center;
  transform-box: fill-box;
}

@keyframes stretch {
  0% {
    transform: scaleX(0.06);
  }
  85%,
  100% {
    transform: scaleX(1);
  }
}

/* nudge */
.nudge .task {
  fill: var(--hmz-lane-1);
  opacity: 0.85;
}

.nudge .tap {
  fill: var(--hmz-lane-4);
  opacity: 0.2;
  animation: pop 3s ease-in-out infinite;
  animation-delay: calc((var(--n) - 1) * 0.7s);
  transform-origin: center;
  transform-box: fill-box;
}

/* goal */
.goal .ring {
  fill: none;
  stroke: var(--vp-c-divider);
  stroke-width: 3;
}

.goal .sweep {
  fill: none;
  stroke: var(--hmz-lane-3);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-dasharray: 82;
  transform: rotate(-90deg);
  transform-origin: 66px 20px;
  animation: pursue 3.4s ease-in-out infinite;
}

.goal .core {
  fill: var(--hmz-lane-3);
  animation: say 3.4s ease-in-out infinite;
}

@keyframes pursue {
  0% {
    stroke-dashoffset: 82;
  }
  70%,
  100% {
    stroke-dashoffset: 0;
  }
}

/* pair */
.pair .one {
  fill: var(--hmz-lane-1);
  animation: across 3.6s ease-in-out infinite;
}

.pair .two {
  fill: var(--hmz-lane-2);
  animation: across 3.6s ease-in-out infinite 1.8s;
}

@keyframes across {
  0%,
  100% {
    transform: translateX(0);
    opacity: 0.25;
  }
  10%,
  40% {
    opacity: 1;
  }
  50% {
    transform: translateX(84px);
    opacity: 0.25;
  }
}

/* review */
.review .actor {
  fill: var(--hmz-lane-1);
  opacity: 0.6;
  transform-origin: left center;
  transform-box: fill-box;
  animation: stretch 3.8s ease-in-out infinite;
}

.review .look {
  fill: none;
  stroke: var(--hmz-lane-2);
  stroke-width: 1.6;
  stroke-dasharray: 4 3;
  animation: pop 3.8s ease-in-out infinite;
  animation-delay: calc((var(--n) - 1) * 0.9s);
  transform-origin: center;
  transform-box: fill-box;
}

.review .back {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.4;
  stroke-dasharray: 3 4;
  animation: crawl 1.8s linear infinite;
}

@keyframes crawl {
  to {
    stroke-dashoffset: -14;
  }
}

/* phases */
.phases .phase {
  fill: var(--vp-c-bg);
  stroke: var(--hmz-lane-3);
  stroke-width: 1.4;
  animation: pop 4.2s ease-in-out infinite;
  animation-delay: calc((var(--n) - 1) * 1.4s);
  transform-origin: center;
  transform-box: fill-box;
}

.phases .token {
  fill: var(--hmz-accent);
  animation: hand 4.2s ease-in-out infinite;
}

@keyframes hand {
  0%,
  22% {
    cx: 23px;
    opacity: 0;
  }
  26% {
    opacity: 1;
  }
  34%,
  56% {
    cx: 67px;
  }
  62% {
    opacity: 1;
  }
  70%,
  100% {
    cx: 111px;
    opacity: 0;
  }
}

/* lanes */
.lanes .runner {
  fill: var(--hmz-lane-1);
  animation: lane 3.6s linear infinite;
  animation-delay: calc((var(--n) - 1) * 0.45s);
}

.lanes .runner:nth-of-type(2) {
  fill: var(--hmz-lane-2);
}

.lanes .runner:nth-of-type(3) {
  fill: var(--hmz-lane-3);
}

@keyframes lane {
  0% {
    transform: translateX(0);
    opacity: 0.2;
  }
  12%,
  88% {
    opacity: 1;
  }
  100% {
    transform: translateX(120px);
    opacity: 0.2;
  }
}

/* Off screen, the drawings wait where they are rather than play to nobody. */
.idle .glyph * {
  animation-play-state: paused !important;
}

@media (prefers-reduced-motion: reduce) {
  .glyph * {
    animation: none !important;
  }
}
</style>
