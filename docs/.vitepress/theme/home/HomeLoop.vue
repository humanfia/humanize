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
const TRACK = 'M250 150V70H470V150V230H250Z'
const RIDE = 'M130 150H250V70H470V230H250V70H470V150H590'
const TOKENS = 9
</script>

<template>
  <svg class="lp" :class="{ paused }" viewBox="0 0 720 300" role="img" :aria-label="LOOP.alt">
    <!-- the way in, the track, the way out -->
    <path class="lp-rail" d="M130 150H250M470 150H590" />
    <path class="lp-rail" :d="TRACK" />
    <path class="lp-back" d="M470 230H250" />
    <path class="lp-head" d="M356 64l10 6-10 6z" />
    <path class="lp-head back" d="M364 224l-10 6 10 6z" />

    <!-- tokens, round and round -->
    <rect
      v-for="n in TOKENS"
      :key="n"
      class="lp-token"
      x="-3.5"
      y="-3.5"
      width="7"
      height="7"
      :style="{ offsetPath: `path('${TRACK}')`, animationDelay: `${(-6 * n) / TOKENS}s`, offsetDistance: `${(100 * n) / TOKENS}%` }"
    />

    <!-- the task's marker -->
    <rect class="lp-ride" x="-9" y="-9" width="18" height="18" :style="{ offsetPath: `path('${RIDE}')` }" />

    <g class="lp-chip">
      <rect x="20" y="124" width="110" height="52" />
      <text x="75" y="158">{{ LOOP.task }}</text>
    </g>
    <g class="lp-node">
      <rect x="180" y="118" width="140" height="64" />
      <text x="250" y="159">{{ LOOP.work }}</text>
    </g>
    <g class="lp-node review">
      <rect x="400" y="118" width="140" height="64" />
      <text x="470" y="159">{{ LOOP.review }}</text>
    </g>
    <g class="lp-chip done">
      <rect x="590" y="124" width="110" height="52" />
      <text x="645" y="158">{{ LOOP.done }}</text>
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
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
  text-anchor: middle;
  fill: var(--hm-fg);
}
.lp-rail,
.lp-back {
  fill: none;
  stroke: var(--hm-rule-strong);
  stroke-width: 2;
}
/* The way back is the loop's own colour: what is sent back goes round again. */
.lp-back {
  stroke: var(--hm-pink);
  stroke-width: 3;
}
.lp-head {
  fill: var(--hm-fg-3);
}
.lp-head.back {
  fill: var(--hm-pink);
}
.lp-chip rect,
.lp-node rect {
  fill: var(--hm-bg);
  stroke: var(--hm-fg);
  stroke-width: 2;
}
.lp-node rect {
  fill: var(--hm-sheet);
}
.lp-token {
  fill: var(--hm-cyan);
  offset-rotate: 0deg;
  animation: lp-round 6s linear infinite;
}
.lp-ride {
  fill: var(--hm-pink);
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
/* The ride is 1180 long: 120 in, 300 over to review, 380 back under to work, 300 over again,
   80 down and 120 out. It rests at each agent, and at the end. */
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
    offset-distance: 10.2%;
  }
  30%,
  40% {
    offset-distance: 42.4%;
  }
  52%,
  62% {
    offset-distance: 67.8%;
  }
  74%,
  82% {
    offset-distance: 89.8%;
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

@media (prefers-reduced-motion: reduce) {
  .lp-token,
  .lp-ride,
  .lp-node rect,
  .lp-chip.done rect {
    animation: none;
  }
}
</style>
