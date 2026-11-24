<script setup lang="ts">
// The scale, drawn: one flow on the left, one task on the right, and between them a field of
// agents, each a disc in the colour of the nous it thinks with, each in the square of an
// environment of its own; under the field, the rule of one month. It is where Humanize is
// going, as a picture: Humanize is the field and the rails, not the plate on the left.
//
// It is a drawing, not the interface, so it is drawn here, in the page's own colours and in the
// site's manner: ink plates, hairlines, flat colour, nothing blurred. The agents take turns
// working, a few at a time, and the month fills. For a reader who asked for less motion it
// stands still, and it stops where it is while the reader has stopped what moves on the page
// (`paused`).
import { SCALE } from './copy'

defineProps<{ paused?: boolean }>()

const COLS = 19
const ROWS = 5
/** The field's first cell, and the step from one to the next. */
const X = 180
const Y = 72
const DX = 20
const DY = 26
/** How many kinds of nous the drawing has: the site's lane colours. */
const KINDS = 6

/** A cell's kind and its place in the round of turns: fixed, and scattered enough to read as a
 *  schedule and not as a wave. */
const cells = Array.from({ length: COLS * ROWS }, (_, n) => {
  const col = n % COLS
  const row = Math.floor(n / COLS)
  const mix = (col * 7 + row * 13 + ((col * row) % 5) * 3) % 97
  return { x: X + col * DX, y: Y + row * DY, kind: (mix % KINDS) + 1, turn: (mix * 37) % 100 }
})
const rows = Array.from({ length: ROWS }, (_, row) => Y + row * DY)
const LEFT = X - 10
const RIGHT = X + (COLS - 1) * DX + 10
const TOP = rows[0]
const BOTTOM = rows[ROWS - 1]
/** The month's rule, and its four weeks. */
const RULE = 226
const weeks = Array.from({ length: 5 }, (_, n) => LEFT + ((RIGHT - LEFT) * n) / 4)
</script>

<template>
  <svg class="sc" :class="{ paused }" viewBox="0 44 720 212" role="img" :aria-label="SCALE.alt">
    <!-- the rails: out of the flow to every row, and from every row into the task -->
    <path class="sc-rail" :d="`M130 150H150M150 ${TOP}V${BOTTOM}M570 ${TOP}V${BOTTOM}M570 150H590`" />
    <path v-for="y in rows" :key="y" class="sc-stub" :d="`M150 ${y}H${LEFT}M${RIGHT} ${y}H570`" />

    <!-- the field: an environment, and the agent in it -->
    <g v-for="(cell, n) in cells" :key="n" class="sc-cell" :class="`k${cell.kind}`" :style="{ '--turn': cell.turn }">
      <rect :x="cell.x - 7" :y="cell.y - 7" width="14" height="14" />
      <circle :cx="cell.x" :cy="cell.y" r="3.4" />
    </g>
    <text class="sc-label" :x="LEFT" y="58">{{ SCALE.agents }}</text>
    <text class="sc-label end" :x="RIGHT" y="58">{{ SCALE.envs }}</text>

    <!-- the month -->
    <path class="sc-rule" :d="`M${LEFT} ${RULE}H${RIGHT}`" />
    <path class="sc-month" :d="`M${LEFT} ${RULE}H${RIGHT}`" pathLength="100" />
    <path v-for="x in weeks" :key="x" class="sc-tick" :d="`M${x} ${RULE - 5}V${RULE + 5}`" />
    <text class="sc-label mid" x="360" y="250">{{ SCALE.month }}</text>

    <g class="sc-plate">
      <rect x="20" y="126" width="110" height="48" />
      <text x="75" y="156.5">{{ SCALE.flow }}</text>
    </g>
    <g class="sc-plate task">
      <rect x="590" y="126" width="110" height="48" />
      <path d="M678 126h22v22z" />
      <text x="645" y="156.5">{{ SCALE.task }}</text>
    </g>
  </svg>
</template>

<style scoped>
.sc {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}
.sc text {
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.025em;
  text-anchor: middle;
}
.sc .sc-label {
  font-family: var(--hm-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  text-anchor: start;
  fill: var(--hm-fg-2);
}
.sc .sc-label.end {
  text-anchor: end;
}
.sc .sc-label.mid {
  text-anchor: middle;
}
.sc-rail,
.sc-rule {
  fill: none;
  stroke: var(--hm-fg);
  stroke-width: 2;
}
.sc-stub,
.sc-tick {
  fill: none;
  stroke: var(--hm-fg-3);
  stroke-width: 1;
}
/* The month fills in the green, over the ink of its rule. */
.sc-month {
  fill: none;
  stroke: var(--hm-green);
  stroke-width: 6;
  stroke-dasharray: 100;
  stroke-dashoffset: 0;
  animation: sc-month 24s linear infinite;
}
/* The flow is the ink plate, and the task the sheet it is all for: the green is in its corner,
   where the mark keeps it. */
.sc-plate rect {
  fill: var(--hm-fg);
}
.sc-plate text {
  fill: var(--hm-bg);
}
.sc-plate.task rect {
  fill: var(--hm-sheet);
  stroke: var(--hm-fg);
  stroke-width: 2;
}
.sc-plate.task path {
  fill: var(--hm-green);
}
.sc-plate.task text {
  fill: var(--hm-fg);
}
/* An environment is a hairline square; the agent in it is a disc in its nous's colour, dim
   until its turn comes round. */
.sc-cell rect {
  fill: var(--hm-bg);
  stroke: var(--hm-rule);
  stroke-width: 1;
}
.sc-cell circle {
  fill: var(--kind);
  opacity: 0.3;
  animation: sc-turn 8s linear calc(var(--turn) * -0.08s) infinite;
}
.sc-cell.k1 {
  --kind: var(--hmz-lane-1);
}
.sc-cell.k2 {
  --kind: var(--hmz-lane-2);
}
.sc-cell.k3 {
  --kind: var(--hmz-lane-3);
}
.sc-cell.k4 {
  --kind: var(--hmz-lane-4);
}
.sc-cell.k5 {
  --kind: var(--hmz-lane-5);
}
.sc-cell.k6 {
  --kind: var(--hmz-lane-6);
}
.sc.paused .sc-cell circle,
.sc.paused .sc-month {
  animation-play-state: paused;
}

@keyframes sc-turn {
  0%,
  22%,
  100% {
    opacity: 0.3;
  }
  4%,
  18% {
    opacity: 1;
  }
}
@keyframes sc-month {
  from {
    stroke-dashoffset: 100;
  }
  92%,
  to {
    stroke-dashoffset: 0;
  }
}

/* On a phone the drawing is half its size, and its words are set larger to stay legible. */
@media (max-width: 640px) {
  .sc text {
    font-size: 26px;
  }
  .sc .sc-label {
    font-size: 19px;
    letter-spacing: 0.04em;
  }
}
@media (prefers-reduced-motion: reduce) {
  /* At rest every agent is lit and the month is whole. */
  .sc-cell circle,
  .sc-month {
    animation: none;
  }
  .sc-cell circle {
    opacity: 1;
  }
}
</style>
