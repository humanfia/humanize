<script setup lang="ts">
// Eight things humanize gets you, one drawing each. The words say what you get and when you
// would reach for it; the feature page behind each card is where the rest of it lives.
import { onMounted, onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'

// The drawings are CSS animations, held still while the grid is scrolled off screen.
const root = ref<HTMLElement | null>(null)
const seen = ref(true)
let observer: IntersectionObserver | undefined

onMounted(() => {
  observer = new IntersectionObserver((entries) => (seen.value = entries[0].isIntersecting))
  if (root.value) observer.observe(root.value)
})

onUnmounted(() => observer?.disconnect())
</script>

<template>
  <div ref="root" class="grid" :class="{ still: !seen }">
    <a class="card" :href="withBase('/features/backends')">
      <svg class="viz fan" viewBox="0 0 200 88" aria-hidden="true">
        <path d="M 46 44 C 90 44 100 14 152 14" />
        <path d="M 46 44 C 90 44 100 34 152 34" />
        <path d="M 46 44 C 90 44 100 54 152 54" />
        <path d="M 46 44 C 90 44 100 74 152 74" />
        <circle class="hub" cx="38" cy="44" r="9" />
        <g class="ends">
          <circle cx="158" cy="14" r="5.5" />
          <circle cx="158" cy="34" r="5.5" />
          <circle cx="158" cy="54" r="5.5" />
          <circle cx="158" cy="74" r="5.5" />
        </g>
      </svg>
      <h3>Every coding agent you have</h3>
      <p>Claude Code on one role, Codex on the next. Most run under the login you already have.</p>
      <p class="names">
        agy · claude · codex · cursor-agent · dsh · grok · kimi · mimo · opencode · pi · qwen ·
        zcode
      </p>
    </a>

    <a class="card" :href="withBase('/features/accounts')">
      <svg class="viz accounts" viewBox="0 0 200 88" aria-hidden="true">
        <rect class="cli" x="70" y="32" width="60" height="24" rx="7" />
        <text x="100" y="48">claude</text>
        <g class="badge one">
          <rect x="16" y="14" width="66" height="20" rx="10" />
          <text x="49" y="28">@work</text>
        </g>
        <g class="badge two">
          <rect x="118" y="54" width="72" height="20" rx="10" />
          <text x="154" y="68">@gateway</text>
        </g>
      </svg>
      <h3>Two accounts of one CLI</h3>
      <p>Your subscription on one agent and a gateway on the other, in the same run.</p>
    </a>

    <a class="card" :href="withBase('/features/steering')">
      <svg class="viz steer" viewBox="0 0 200 88" aria-hidden="true">
        <rect class="track" x="24" y="26" width="152" height="16" rx="8" />
        <rect class="fill" x="24" y="26" width="14" height="16" rx="8" />
        <rect class="typed" x="24" y="56" width="86" height="14" rx="7" />
        <rect class="caret" x="112" y="56" width="3" height="14" rx="1.5" />
        <path class="into" d="M 100 54 L 100 46" />
      </svg>
      <h3>Talk into a running turn</h3>
      <p>
        Say “use pathlib” four minutes into a refactor, and that turn hears it. On Claude Code,
        Codex, Kimi and pi.
      </p>
    </a>

    <a class="card" :href="withBase('/features/human')">
      <svg class="viz human" viewBox="0 0 200 88" aria-hidden="true">
        <g class="row">
          <rect x="20" y="18" width="120" height="10" rx="5" />
          <rect x="20" y="39" width="88" height="10" rx="5" />
          <rect class="you" x="20" y="60" width="104" height="10" rx="5" />
        </g>
        <g class="face">
          <circle cx="164" cy="58" r="8" />
          <path d="M 150 76 C 152 64 176 64 178 76" />
        </g>
      </svg>
      <h3>When a flow asks you</h3>
      <p>A flow can stop and ask you. When you are away, it is told so rather than left waiting.</p>
    </a>

    <a class="card" :href="withBase('/features/allowances')">
      <svg class="viz budget" viewBox="0 0 200 88" aria-hidden="true">
        <text class="what" x="14" y="23">time</text>
        <text class="what" x="14" y="47">cost</text>
        <text class="what" x="14" y="71">tokens</text>
        <rect class="track" x="56" y="15" width="120" height="10" rx="5" />
        <rect class="track" x="56" y="39" width="120" height="10" rx="5" />
        <rect class="track" x="56" y="63" width="120" height="10" rx="5" />
        <rect class="fill time" x="56" y="15" width="120" height="10" rx="5" />
        <rect class="fill cost" x="56" y="39" width="120" height="10" rx="5" />
        <rect class="fill tokens" x="56" y="63" width="120" height="10" rx="5" />
        <rect class="stop" x="180" y="38" width="12" height="12" rx="2" />
      </svg>
      <h3>A budget on every run</h3>
      <p>Six hours or fifty dollars: whichever runs out first stops the run.</p>
    </a>

    <a class="card" :href="withBase('/features/daemon')">
      <svg class="viz leave" viewBox="0 0 200 88" aria-hidden="true">
        <g class="term">
          <rect class="window" x="14" y="20" width="70" height="48" rx="6" />
          <path class="top" d="M 14 30 L 84 30" />
          <rect class="prompt" x="22" y="40" width="34" height="6" rx="3" />
          <rect class="prompt" x="22" y="52" width="22" height="6" rx="3" />
        </g>
        <path class="link" d="M 86 44 L 112 44" />
        <rect class="track" x="116" y="38" width="70" height="12" rx="6" />
        <rect class="run" x="116" y="38" width="70" height="12" rx="6" />
      </svg>
      <h3>Close the terminal, keep the run</h3>
      <p>Leave a run going, lose the SSH session, and open it again from the same directory.</p>
    </a>

    <a class="card" :href="withBase('/features/tracing')">
      <svg class="viz trace" viewBox="0 0 200 88" aria-hidden="true">
        <g class="slices">
          <rect x="20" y="16" width="42" height="12" rx="3" />
          <rect x="66" y="16" width="28" height="12" rx="3" />
          <rect x="98" y="16" width="56" height="12" rx="3" />
          <rect x="20" y="38" width="30" height="12" rx="3" />
          <rect x="54" y="38" width="64" height="12" rx="3" />
          <rect x="122" y="38" width="36" height="12" rx="3" />
          <rect x="20" y="60" width="58" height="12" rx="3" />
          <rect x="82" y="60" width="24" height="12" rx="3" />
          <rect x="110" y="60" width="70" height="12" rx="3" />
        </g>
        <line class="head" x1="20" y1="10" x2="20" y2="78" />
      </svg>
      <h3>Every agent on one timeline</h3>
      <p>
        Every agent and sub-agent of a run, on one clock, in Perfetto. Profile it and the programs
        they ran are there too.
      </p>
    </a>

    <a class="card" :href="withBase('/features/resuming')">
      <svg class="viz resume" viewBox="0 0 200 88" aria-hidden="true">
        <rect class="seg" x="20" y="38" width="62" height="12" rx="6" />
        <rect class="seg gap" x="90" y="38" width="18" height="12" rx="6" />
        <rect class="seg late" x="116" y="38" width="64" height="12" rx="6" />
        <path class="arc" d="M 100 34 C 100 12 150 12 150 32" />
      </svg>
      <h3>Pick up where it stopped</h3>
      <p>Stop a long loop on Thursday. On Monday it carries on from where it stood.</p>
    </a>
  </div>
</template>

<style scoped>
/* Sized by the room the cards get rather than by the window: beside a sidebar and an outline
   the content column is a good deal narrower than the screen. */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(250px, 100%), 1fr));
  gap: 16px;
}

.card {
  display: block;
  padding: 6px 18px 18px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
  color: inherit;
  text-decoration: none;
  transition: transform 0.25s, border-color 0.25s, box-shadow 0.25s;
}

.vp-doc .card,
.vp-doc .card:hover {
  font-weight: inherit;
  text-decoration: none;
}

.card:hover {
  transform: translateY(-3px);
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 10px 30px -18px var(--vp-c-brand-1);
}

.card:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.viz {
  display: block;
  width: 100%;
  height: auto;
}

h3 {
  margin: 6px 0 0;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--vp-c-text-1);
}

p {
  margin: 6px 0 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

p.names {
  font-family: var(--vp-font-family-mono);
  font-size: 10.5px;
  color: var(--vp-c-text-3);
}

svg text {
  fill: var(--vp-c-text-2);
  font-size: 9px;
  font-family: var(--vp-font-family-mono);
  text-anchor: middle;
}

@keyframes crawl {
  to {
    stroke-dashoffset: -16;
  }
}

/* every coding agent you have */
.fan path {
  fill: none;
  stroke: var(--vp-c-divider);
  stroke-width: 1.4;
  stroke-dasharray: 3 5;
  animation: crawl 2.4s linear infinite;
}

.fan .hub {
  fill: var(--vp-c-brand-1);
}

.fan .ends circle {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-brand-1);
  stroke-width: 1.6;
  animation: blip 3.2s ease-in-out infinite;
}

.fan .ends circle:nth-child(2) {
  animation-delay: 0.35s;
}

.fan .ends circle:nth-child(3) {
  animation-delay: 0.7s;
}

.fan .ends circle:nth-child(4) {
  animation-delay: 1.05s;
}

@keyframes blip {
  0%,
  60%,
  100% {
    fill: var(--vp-c-bg);
  }
  20%,
  40% {
    fill: var(--hmz-accent);
  }
}

/* two accounts of one CLI */
.accounts .cli {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-divider);
}

.accounts .badge rect {
  fill: var(--vp-c-default-soft);
  stroke: none;
}

.accounts .badge text {
  fill: var(--vp-c-text-2);
}

.accounts .badge.one {
  animation: takeover 4.4s ease-in-out infinite;
}

.accounts .badge.two {
  animation: takeover 4.4s ease-in-out infinite 2.2s;
}

@keyframes takeover {
  0%,
  45%,
  100% {
    opacity: 0.45;
  }
  10%,
  35% {
    opacity: 1;
  }
}

/* talk into a running turn */
.steer .track {
  fill: var(--vp-c-default-soft);
}

.steer .fill {
  fill: var(--vp-c-brand-1);
  opacity: 0.75;
  animation: grow 4.5s ease-in-out infinite;
}

@keyframes grow {
  0% {
    width: 14px;
  }
  100% {
    width: 152px;
  }
}

.steer .typed {
  fill: var(--vp-c-default-soft);
}

.steer .caret {
  fill: var(--hmz-accent);
  animation: blink 1s steps(2) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.steer .into {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-linecap: round;
  animation: rise 4.5s ease-in-out infinite;
}

@keyframes rise {
  0%,
  55% {
    opacity: 0;
    transform: translateY(6px);
  }
  70%,
  90% {
    opacity: 1;
    transform: translateY(0);
  }
  100% {
    opacity: 0;
  }
}

/* when a flow asks you */
.human .row rect {
  fill: var(--vp-c-default-soft);
}

.human .row .you {
  fill: var(--hmz-lane-6);
  opacity: 0.55;
  animation: attend 3.6s ease-in-out infinite;
}

@keyframes attend {
  0%,
  100% {
    opacity: 0.35;
  }
  50% {
    opacity: 0.9;
  }
}

.human .face circle {
  fill: var(--vp-c-brand-1);
}

.human .face path {
  fill: none;
  stroke: var(--vp-c-brand-1);
  stroke-width: 2.4;
  stroke-linecap: round;
}

/* a budget on every run: three meters, and the first to fill is the one that stops it */
.budget text.what {
  text-anchor: start;
  fill: var(--vp-c-text-3);
}

.budget .track {
  fill: var(--vp-c-default-soft);
}

.budget .fill {
  transform-origin: left center;
  transform-box: fill-box;
  opacity: 0.8;
  animation: 5s ease-in infinite;
}

.budget .fill.time {
  fill: var(--hmz-lane-1);
  animation-name: meter-time;
}

.budget .fill.cost {
  fill: var(--hmz-warm);
  animation-name: meter-cost;
}

.budget .fill.tokens {
  fill: var(--hmz-lane-2);
  animation-name: meter-tokens;
}

@keyframes meter-time {
  0% {
    transform: scaleX(0.04);
  }
  60%,
  96% {
    transform: scaleX(0.58);
  }
  100% {
    transform: scaleX(0.04);
  }
}

@keyframes meter-cost {
  0% {
    transform: scaleX(0.04);
  }
  60%,
  96% {
    transform: scaleX(1);
  }
  100% {
    transform: scaleX(0.04);
  }
}

@keyframes meter-tokens {
  0% {
    transform: scaleX(0.04);
  }
  60%,
  96% {
    transform: scaleX(0.4);
  }
  100% {
    transform: scaleX(0.04);
  }
}

.budget .stop {
  fill: var(--hmz-warm);
  animation: halt 5s ease-in infinite;
}

@keyframes halt {
  0%,
  58% {
    opacity: 0;
  }
  62%,
  96% {
    opacity: 1;
  }
  100% {
    opacity: 0;
  }
}

/* close the terminal, keep the run */
.leave .window {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-divider);
}

.leave .top {
  stroke: var(--vp-c-divider);
}

.leave .prompt {
  fill: var(--vp-c-default-soft);
}

.leave .term {
  animation: away 6s ease-in-out infinite;
}

.leave .link {
  stroke: var(--hmz-accent);
  stroke-width: 1.6;
  stroke-dasharray: 3 4;
  animation: crawl 1.6s linear infinite, away 6s ease-in-out infinite;
}

@keyframes away {
  0%,
  25% {
    opacity: 1;
  }
  32%,
  68% {
    opacity: 0.12;
  }
  75%,
  100% {
    opacity: 1;
  }
}

.leave .track {
  fill: var(--vp-c-default-soft);
}

.leave .run {
  fill: var(--vp-c-brand-1);
  opacity: 0.8;
  transform-origin: left center;
  transform-box: fill-box;
  animation: carry 6s linear infinite;
}

@keyframes carry {
  from {
    transform: scaleX(0.08);
  }
  to {
    transform: scaleX(1);
  }
}

/* every agent on one timeline */
.trace .slices rect {
  fill: var(--hmz-lane-1);
  opacity: 0.85;
  transform-origin: left center;
  transform-box: fill-box;
  animation: slide 3.6s ease-out infinite;
}

.trace .slices rect:nth-child(n + 4) {
  fill: var(--hmz-lane-2);
}

.trace .slices rect:nth-child(n + 7) {
  fill: var(--hmz-lane-3);
}

.trace .slices rect:nth-child(2),
.trace .slices rect:nth-child(5),
.trace .slices rect:nth-child(8) {
  animation-delay: 0.5s;
}

.trace .slices rect:nth-child(3),
.trace .slices rect:nth-child(6),
.trace .slices rect:nth-child(9) {
  animation-delay: 1s;
}

@keyframes slide {
  0% {
    transform: scaleX(0);
    opacity: 0;
  }
  20%,
  92% {
    transform: scaleX(1);
    opacity: 0.85;
  }
  100% {
    transform: scaleX(1);
    opacity: 0;
  }
}

.trace .head {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  animation: sweep 3.6s linear infinite;
}

@keyframes sweep {
  to {
    transform: translateX(160px);
  }
}

/* pick up where it stopped */
.resume .seg {
  fill: var(--vp-c-brand-1);
  opacity: 0.8;
}

.resume .seg.gap {
  fill: var(--vp-c-default-soft);
}

.resume .seg.late {
  fill: var(--hmz-accent);
  transform-origin: left center;
  transform-box: fill-box;
  animation: pickup 3.4s ease-in-out infinite;
}

@keyframes pickup {
  0%,
  20% {
    transform: scaleX(0);
  }
  70%,
  100% {
    transform: scaleX(1);
  }
}

.resume .arc {
  fill: none;
  stroke: var(--vp-c-text-3);
  stroke-width: 1.4;
  stroke-dasharray: 3 4;
  animation: crawl 2s linear infinite;
}

.still .viz,
.still .viz * {
  animation-play-state: paused !important;
}

/* Held still, each drawing is left at a frame that still says its one thing: the cost meter
   full and the stop showing, the terminal there and the run bar drawn. */
@media (prefers-reduced-motion: reduce) {
  .viz *,
  .viz {
    animation: none !important;
  }

  .budget .fill.time {
    transform: scaleX(0.58);
  }

  .budget .fill.tokens {
    transform: scaleX(0.4);
  }

  .leave .run {
    transform: scaleX(0.7);
  }
}
</style>
