<script setup lang="ts">
// The loop, drawn: a task goes in, one agent works on it, another reviews it and sends it back
// under, round again, until it comes out done, while tokens run round the track. It is a
// drawing, not the interface, so it is drawn here, in the page's own colours, and follows the
// theme as the page does. For a reader who asked for less motion it stands still, finished, and
// it stops where it is while the reader has stopped what moves on the page (`paused`).
import { LOOP } from './copy'

defineProps<{ paused?: boolean }>()

// The track is a rectangle between the two agents: over the top from work to review, back
// underneath from review to work. The task's marker rides it: in from the left, over, back
// under, over again, and out to the right.
const TRACK = 'M250 150V86a16 16 0 0 1 16-16H454a16 16 0 0 1 16 16V214a16 16 0 0 1-16 16H266a16 16 0 0 1-16-16Z'
const RIDE =
  'M130 150H250V86a16 16 0 0 1 16-16H454a16 16 0 0 1 16 16V214a16 16 0 0 1-16 16H266a16 16 0 0 1-16-16V86a16 16 0 0 1 16-16H454a16 16 0 0 1 16 16V150H590'
const TOKENS = 9
</script>

<template>
  <svg class="lp" :class="{ paused }" viewBox="0 44 720 212" role="img" :aria-label="LOOP.alt">
    <!-- the way in, the track, the way out -->
    <path class="lp-rail" d="M130 150H250M470 150H590" />
    <path class="lp-rail" :d="TRACK" />
    <path class="lp-over" d="M250 118V86a16 16 0 0 1 16-16H454a16 16 0 0 1 16 16V118" />
    <path class="lp-back" d="M470 182V214a16 16 0 0 1-16 16H266a16 16 0 0 1-16-16V182" />
    <path class="lp-head" d="M355 64.5l9 5.5-9 5.5" />
    <path class="lp-head back" d="M365 224.5l-9 5.5 9 5.5" />

    <!-- tokens, round and round -->
    <circle
      v-for="n in TOKENS"
      :key="n"
      class="lp-token"
      r="3"
      :style="{ offsetPath: `path('${TRACK}')`, animationDelay: `${(-6 * n) / TOKENS}s`, offsetDistance: `${(100 * n) / TOKENS}%` }"
    />

    <!-- the task's marker -->
    <circle class="lp-ride" r="8" :style="{ offsetPath: `path('${RIDE}')` }" />

    <g class="lp-chip">
      <rect x="20" y="126" width="110" height="48" rx="24" />
      <text x="75" y="156.5">{{ LOOP.task }}</text>
    </g>
    <g class="lp-node">
      <rect x="180" y="118" width="140" height="64" rx="16" />
      <text x="250" y="157">{{ LOOP.work }}</text>
    </g>
    <g class="lp-node review">
      <rect x="400" y="118" width="140" height="64" rx="16" />
      <text x="470" y="157">{{ LOOP.review }}</text>
    </g>
    <g class="lp-chip done">
      <rect x="590" y="126" width="110" height="48" rx="24" />
      <text x="645" y="156.5">{{ LOOP.done }}</text>
    </g>
  </svg>
</template>

<style scoped>
.lp {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}
.lp text {
  font-size: 19px;
  font-weight: 650;
  letter-spacing: -0.025em;
  text-anchor: middle;
  fill: var(--hm-fg);
}
.lp-rail,
.lp-over,
.lp-back,
.lp-head {
  fill: none;
  stroke: var(--hm-rule-strong);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* The way over is one of the page's colours and the way back the other: what is sent back
   goes round again. */
.lp-over,
.lp-head {
  stroke: var(--hm-cyan);
}
.lp-back,
.lp-head.back {
  stroke: var(--hm-pink);
}
.lp-chip rect,
.lp-node rect {
  fill: var(--hm-bg);
  stroke: var(--hm-rule-strong);
  stroke-width: 1.5;
}
.lp-node rect {
  fill: var(--hm-sheet);
  filter: drop-shadow(0 10px 14px color-mix(in srgb, var(--hm-shade) 14%, transparent));
}
.lp-token {
  fill: var(--hm-fg);
  offset-rotate: 0deg;
  animation: lp-round 6s linear infinite;
}
.lp-ride {
  fill: var(--hm-pink);
  filter: drop-shadow(0 0 7px var(--hm-pink));
  offset-rotate: 0deg;
  offset-distance: 100%;
  animation: lp-ride 9s cubic-bezier(0.45, 0, 0.3, 1) infinite;
}
/* Each agent lights while the task is with it, and the last chip when the task is out. */
.lp-node rect {
  animation: lp-work 9s linear infinite;
}
.lp-node.review rect {
  animation-name: lp-review;
}
.lp-chip.done rect {
  fill: var(--hm-cyan-fill);
  animation: lp-done 9s linear infinite;
}
.lp.paused .lp-token,
.lp.paused .lp-ride,
.lp.paused .lp-node rect,
.lp.paused .lp-chip.done rect {
  animation-play-state: paused;
}

@keyframes lp-round {
  from {
    offset-distance: 0%;
  }
  to {
    offset-distance: 100%;
  }
}
/* The ride is 1338.8 long: 120 in to work, 366.3 over the top to review, 366.3 back under to
   work, 366.3 over again, and 120 out. It rests in each agent, and at the end. */
@keyframes lp-ride {
  0% {
    offset-distance: 0%;
    opacity: 0;
  }
  3% {
    opacity: 1;
  }
  8%,
  18% {
    offset-distance: 8.96%;
  }
  30%,
  40% {
    offset-distance: 36.32%;
  }
  52%,
  62% {
    offset-distance: 63.68%;
  }
  74%,
  82% {
    offset-distance: 91.04%;
  }
  90%,
  97% {
    offset-distance: 100%;
    opacity: 1;
  }
  100% {
    offset-distance: 100%;
    opacity: 0;
  }
}
@keyframes lp-work {
  0%,
  7%,
  19%,
  51%,
  63%,
  100% {
    fill: var(--hm-sheet);
  }
  9%,
  17%,
  53%,
  61% {
    fill: var(--hm-pink-fill);
  }
}
@keyframes lp-review {
  0%,
  29%,
  41%,
  73%,
  83%,
  100% {
    fill: var(--hm-sheet);
  }
  31%,
  39%,
  75%,
  81% {
    fill: var(--hm-pink-fill);
  }
}
@keyframes lp-done {
  0%,
  88% {
    fill: var(--hm-bg);
  }
  91%,
  100% {
    fill: var(--hm-cyan-fill);
  }
}

/* On a phone the drawing is half its size, and its words are set larger to stay legible. */
@media (max-width: 640px) {
  .lp text {
    font-size: 26px;
  }
}
@media (prefers-reduced-motion: reduce) {
  /* At rest the task is out and done: its marker is not left standing at the chip's edge. */
  .lp-ride {
    display: none;
  }
  .lp-token,
  .lp-ride,
  .lp-node rect,
  .lp-chip.done rect {
    animation: none;
  }
}
</style>
