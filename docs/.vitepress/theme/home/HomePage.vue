<script setup lang="ts">
// The Humanize page: docs/index.md is this component and nothing else. It is the project's page
// on humanfia.ai (humanfia.ai/humanize/) and the front page of its documentation at once.
//
// It opens as a project's page does: its mark and its name, the repository's description under
// them, the button that gets it, the one to the documentation and the command that installs it;
// and under those one window that plays the real product, a scene at a time (HomeStage.vue).
// Below, where Humanize is going, drawn and moving (HomeScale.vue): one flow, a field of
// agents and environments, one month, one task; then the claim, that Humanize is the
// infrastructure a flow runs on, and the four parts that carry it; where to get it for each
// platform; and the doors into the documentation. Its words are in copy.ts.
//
// It is drawn in humanfia.ai's manner, as the organisation's own pages are: ink on a cool paper,
// colour in flat planes, hairlines and square plates, a hard offset where a thing is lifted, and
// nothing blurred, lit or rounded. The green is the mark's, and stands beside cyan, never pink.
import { withBase } from 'vitepress'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import HomeScale from './HomeScale.vue'
import HomeStage from './HomeStage.vue'
import { BANNER, INFRA, PILLARS, WORDS } from './copy'
import { detectOS, INSTALL, installers, RELEASES, REPO, type Installers, type OS } from './release'

// A platform is offered what it can really get (release.ts). macOS downloads its disk image:
// from the release GitHub names, or from the latest release until it does. Windows downloads
// its installer once a release carries one, and until then is shown the command, which there
// runs in WSL. Linux is shown the command. The button under the banner does the same for the
// platform the browser is on, and where that is none of these it goes to the three below.
const os = ref<OS | null>(null)
const found = ref<Installers>({})
onMounted(async () => {
  os.value = detectOS()
  found.value = await installers()
})
const mac = computed(() => found.value.macos ?? RELEASES)
const get = computed(() => (os.value === 'macos' ? mac.value : (os.value === 'windows' && found.value.windows) || '#get'))

/** Which of the page's copies of the command was just copied, so that only its button says so. */
const copied = ref<string | null>(null)
let clear: ReturnType<typeof setTimeout> | undefined
async function copy(from: string) {
  try {
    await navigator.clipboard.writeText(INSTALL)
    copied.value = from
    clearTimeout(clear)
    clear = setTimeout(() => (copied.value = null), 1600)
  } catch {
    // No clipboard (plain http, or no gesture the browser recognises): the line can be selected.
  }
}
onBeforeUnmount(() => clearTimeout(clear))

/** Whether the reader stopped what moves: the stage has the control, and the drawing follows it. */
const paused = ref(false)

/** The documentation's sections, each with a small drawing: a flag, a person, a wrench, a book. */
const DOORS = [
  { name: 'Tutorials', href: '/tutorials/', icon: 'M5 21V4M5 4h11l-2 4 2 4H5' },
  { name: 'User Guide', href: '/user/', icon: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 20.5a7.5 7.5 0 0 1 15 0' },
  { name: 'Builder Guide', href: '/builder/', icon: 'M14.5 6.5a4 4 0 0 0 5 5L11 20a2.1 2.1 0 0 1-3-3l8.5-8.5M14.5 6.5l3-3' },
  { name: 'Reference', href: '/reference/', icon: 'M5 4.5h10a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3ZM5 17a3 3 0 0 1 3-3h10M9 8.5h5' },
]

const APPLE =
  'M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701'
const WINDOWS = 'M2 3h9.5v9.5H2zM12.5 3H22v9.5h-9.5zM2 13.5h9.5V23H2zM12.5 13.5H22V23h-9.5z'
const DOWN = 'M8 1.5v9M4 7l4 4 4-4M2.5 14.5h11'
const ARROW = 'M2.5 8h10M8.5 4l4 4-4 4'
const OUT = 'M4.5 11.5l7-7M6 4.5h5.5V10'
const COPY = 'M5.5 5.5v-2a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-2M3.5 5.5h6a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-6a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1Z'
const CHECK = 'M3 8.5l3.2 3.2L13 4.8'
</script>

<template>
  <div class="hm">
    <section class="hm-hero">
      <div class="hm-sky" aria-hidden="true" />
      <div class="hm-wrap">
        <h1 class="hm-name">
          <svg viewBox="0 0 100 100" aria-hidden="true">
            <polygon class="ink" points="12,16 32,16 62,50 32,84 12,84 42,50" />
            <polygon class="green" points="60,84 94,84 94,64 60,74" />
          </svg>
          Humanize
        </h1>
        <p class="hm-banner">{{ BANNER }}</p>

        <div class="hm-get">
          <a class="hm-btn go" :href="get">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="DOWN" /></svg>
            {{ WORDS.download }}
          </a>
          <a class="hm-btn" :href="withBase('/tutorials/')">
            {{ WORDS.docs }}
            <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="ARROW" /></svg>
          </a>
          <div class="hm-cmd">
            <code>{{ INSTALL }}</code>
            <button type="button" :class="{ done: copied === 'top' }" @click="copy('top')">
              <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="copied === 'top' ? CHECK : COPY" /></svg>
              <span>{{ WORDS.copy }}</span>
            </button>
          </div>
        </div>

        <HomeStage v-model:paused="paused" />
      </div>
    </section>

    <section class="hm-wrap hm-scale"><HomeScale :paused="paused" /></section>

    <section class="hm-wrap hm-infra">
      <p class="hm-kicker">{{ INFRA.kicker }}</p>
      <h2>{{ INFRA.head }}</h2>
      <p class="hm-lead">{{ INFRA.lead }}</p>
      <ul class="hm-pillars">
        <li v-for="pillar in PILLARS" :key="pillar.label">
          <a :href="withBase(pillar.href)">
            <span class="hm-pillar-label">{{ pillar.label }}</span>
            <h3>{{ pillar.head }}</h3>
            <p>{{ pillar.text }}</p>
            <span class="hm-pillar-go">
              {{ INFRA.more }}
              <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="ARROW" /></svg>
            </span>
          </a>
        </li>
      </ul>
    </section>

    <section id="get" class="hm-wrap hm-end">
      <ul class="hm-platforms">
        <li :class="{ mine: os === 'macos' }">
          <b>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="APPLE" /></svg>
            macOS
          </b>
          <a class="hm-btn go" :href="mac">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="DOWN" /></svg>
            {{ WORDS.download }}
          </a>
        </li>
        <li :class="{ mine: os === 'windows' }">
          <b>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="WINDOWS" /></svg>
            Windows <small v-if="!found.windows">{{ WORDS.wsl }}</small>
          </b>
          <a v-if="found.windows" class="hm-btn go" :href="found.windows">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="DOWN" /></svg>
            {{ WORDS.download }}
          </a>
          <div v-else class="hm-cmd">
            <code>{{ INSTALL }}</code>
            <button type="button" :class="{ done: copied === 'windows' }" @click="copy('windows')">
              <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="copied === 'windows' ? CHECK : COPY" /></svg>
              <span>{{ WORDS.copy }}</span>
            </button>
          </div>
        </li>
        <li :class="{ mine: os === 'linux' }">
          <b>
            <svg class="line" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5.5h18v13H3zM7 10l3 2.5L7 15M12.5 15H17" /></svg>
            Linux
          </b>
          <div class="hm-cmd">
            <code>{{ INSTALL }}</code>
            <button type="button" :class="{ done: copied === 'linux' }" @click="copy('linux')">
              <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="copied === 'linux' ? CHECK : COPY" /></svg>
              <span>{{ WORDS.copy }}</span>
            </button>
          </div>
        </li>
      </ul>

      <ul class="hm-doors">
        <li v-for="door in DOORS" :key="door.name">
          <a :href="withBase(door.href)">
            <svg class="hm-door-icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="door.icon" /></svg>
            <span>{{ door.name }}</span>
            <svg class="hm-door-go" viewBox="0 0 16 16" aria-hidden="true"><path :d="ARROW" /></svg>
          </a>
        </li>
      </ul>
      <ul class="hm-out">
        <li>
          <a href="https://humanfia.ai/flows/">Flows <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="OUT" /></svg></a>
        </li>
        <li>
          <a :href="REPO">GitHub <svg viewBox="0 0 16 16" aria-hidden="true"><path :d="OUT" /></svg></a>
        </li>
      </ul>
    </section>
    <!-- What a copy did, said once to a reader who cannot see the drawing change. -->
    <span class="hm-sr" role="status">{{ copied ? WORDS.copied : '' }}</span>
  </div>
</template>

<style>
/* The page's own colours, by the names this page draws with: they are humanfia.ai's, the ink,
   the paper and its sheet, the two greys between, the hairline, Hyacine's pink and cyan and the
   green of the mark, each taken from the site's own token (theme/style.css, humanfia/chrome.css)
   so that the page follows the theme as every other page does. They are scoped to the page's
   root, so no other page can come to depend on them. */
.hm {
  --hm-ink: #141a1f;
  --hm-paper: #e8f0f2;
  --hm-bg: var(--vp-c-bg);
  --hm-sheet: var(--vp-c-bg-elv);
  --hm-fg: var(--vp-c-text-1);
  --hm-fg-2: var(--vp-c-text-2);
  --hm-fg-3: var(--vp-c-text-3);
  --hm-ring: var(--hm-fg);
  --hm-pink: var(--hmz-accent-2);
  --hm-cyan: var(--hmz-accent);
  --hm-cyan-text: var(--hmz-cyan-ink);
  --hm-green: var(--hmz-green);
  --hm-green-text: var(--hmz-green-ink);
  --hm-rule: var(--vp-c-divider);
  /* The construction lines under the hero, and the plane behind it: cyan at a whisper. */
  --hm-grid: var(--hmz-con-line);
  --hm-plane: color-mix(in srgb, var(--hm-cyan) 16%, var(--hm-bg));
  /* A plate's corner is cut, not moulded. */
  --hm-radius: 2px;
  --hm-ease: cubic-bezier(0.22, 1, 0.36, 1);
  --hm-mono: var(--vp-font-family-mono);
}

/* The page is its own layout: the theme's content column and its prose styles are not used. */
.hm-page .VPContent {
  background: var(--vp-c-bg);
}
.hm {
  position: relative;
  overflow: hidden;
  color: var(--hm-fg);
  background: var(--hm-bg);
  font-feature-settings: 'ss01', 'cv11';
}
.hm a {
  color: inherit;
  text-decoration: none;
}
.hm button {
  font: inherit;
  color: inherit;
  cursor: pointer;
}
.hm ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.hm :focus-visible {
  outline: 2px solid var(--hm-ring);
  outline-offset: 3px;
}
.hm-wrap {
  position: relative;
  width: min(100% - 48px, 1200px);
  margin: 0 auto;
}

/* ---- the ground: construction lines, and one flat plane ---------------------------------- */

.hm-sky {
  position: absolute;
  inset: 0 0 auto;
  height: 880px;
  pointer-events: none;
}
.hm-sky::before,
.hm-sky::after {
  content: '';
  position: absolute;
}
/* The lines a poster is set out on. They come in under the site's bar, so there is no seam
   where the bar ends, and run out before the page's sections begin. */
.hm-sky::before {
  inset: 0;
  background:
    linear-gradient(var(--hm-grid) 1px, transparent 1px) 50% 0 / 56px 56px,
    linear-gradient(90deg, var(--hm-grid) 1px, transparent 1px) 50% 0 / 56px 56px;
  mask-image: linear-gradient(transparent, #000 200px, #000 62%, transparent);
}
/* The disc: a plane behind the name, loud enough to be a shape and no louder. */
.hm-sky::after {
  top: -150px;
  left: calc(50% + min(22vw, 300px));
  width: 520px;
  height: 520px;
  border-radius: 50%;
  background: var(--hm-plane);
}

/* ---- the hero: the mark and the name, the description, and what gets it ------------------ */

.hm-hero {
  position: relative;
  /* What stands over the window gives way in a short window, so the window is still seen. */
  padding: clamp(24px, 14svh - 60px, 96px) 0 0;
  text-align: center;
}
.hm-name {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.2em;
  margin: 0;
  font-size: clamp(52px, min(8.4vw, 14svh), 104px);
  line-height: 1;
  font-weight: 700;
  letter-spacing: -0.055em;
  color: var(--hm-fg);
}
.hm-name svg {
  flex: none;
  width: 0.86em;
  height: 0.86em;
}
.hm-name .ink {
  fill: currentColor;
}
.hm-name .green {
  fill: var(--hm-green);
}
.hm-banner {
  max-width: 24em;
  margin: clamp(16px, 2vw, 24px) auto 0;
  font-size: clamp(19px, 2.1vw, 27px);
  line-height: 1.3;
  font-weight: 450;
  letter-spacing: -0.02em;
  text-wrap: balance;
  color: var(--hm-fg-2);
}
.hm-get {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin: min(clamp(26px, 3.2vw, 38px), 4.5svh) 0 min(clamp(40px, 5.4vw, 68px), 6svh);
}

/* Square plates. The first is the ink, and a green edge slides out from under it at the
   pointer: the mark's own relation between the large plane and the small green thing beside it.
   The other is drawn in outline. */
.hm-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  height: 46px;
  padding: 0 20px;
  border-radius: var(--hm-radius);
  font-size: 15px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: -0.01em;
  background: var(--hm-bg);
  box-shadow: inset 0 0 0 2px var(--hm-fg);
  transition:
    transform 0.35s var(--hm-ease),
    box-shadow 0.35s var(--hm-ease),
    background-color 0.25s;
}
.hm-btn svg,
.hm-out svg,
.hm-cmd svg,
.hm-pillar-go svg,
.hm-door-go {
  flex: none;
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.hm .hm-btn.go {
  color: var(--hm-bg);
  background: var(--hm-fg);
  box-shadow: 0 0 0 0 var(--hm-green);
}
.hm-btn:hover {
  background: color-mix(in srgb, var(--hm-fg) 8%, var(--hm-bg));
}
.hm .hm-btn.go:hover {
  background: var(--hm-fg);
  transform: translate(-3px, -3px);
  box-shadow: 6px 6px 0 0 var(--hm-green);
}
.hm .hm-btn:active {
  transform: none;
}
.hm .hm-btn.go:active {
  box-shadow: 0 0 0 0 var(--hm-green);
}

.hm-cmd {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  height: 46px;
  padding: 0 6px 0 16px;
  border-radius: var(--hm-radius);
  font-family: var(--hm-mono);
  font-size: 13.5px;
  color: var(--hm-fg);
  background: var(--hm-sheet);
  box-shadow: inset 0 0 0 1px var(--hm-fg);
}
.hm-cmd code {
  min-width: 0;
  overflow: hidden;
  padding: 0;
  font: inherit;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: inherit;
  background: none;
}
.hm-cmd code::before {
  content: '$ ';
  color: var(--hm-fg-3);
}
.hm-cmd button {
  flex: none;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  margin-left: auto;
  border-radius: var(--hm-radius);
  color: var(--hm-fg-3);
  transition:
    color 0.2s,
    background-color 0.2s;
}
.hm-cmd button:hover {
  color: var(--hm-fg);
  background: color-mix(in srgb, var(--hm-fg) 8%, transparent);
}
.hm-cmd button.done {
  color: var(--hm-green-text);
}
/* Its word is for a reader who cannot see the drawing. */
.hm-cmd button span,
.hm-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* What the hero holds comes up into place, one after another, when the page opens. */
@media (prefers-reduced-motion: no-preference) {
  .hm-name,
  .hm-banner,
  .hm-get,
  .hm-hero .st {
    animation: hm-rise 0.7s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  }
  .hm-banner {
    animation-delay: 0.06s;
  }
  .hm-get {
    animation-delay: 0.12s;
  }
  .hm-hero .st {
    animation-delay: 0.2s;
    animation-duration: 0.9s;
  }
}
@keyframes hm-rise {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
}

/* ---- the scale, drawn ------------------------------------------------------------------- */

.hm-scale {
  max-width: 880px;
  padding: clamp(32px, 5vw, 72px) 0;
}

/* ---- the claim, and the four parts that carry it ---------------------------------------- */

.hm-infra {
  padding: clamp(24px, 4vw, 56px) 0 clamp(56px, 7vw, 104px);
}
/* A kicker is a label on a plate: mono capitals, and a short green bar in front of it. */
.hm-kicker {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 18px;
  font-family: var(--hm-mono);
  font-size: 13px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.hm-kicker::before {
  content: '';
  flex: none;
  width: 28px;
  height: 6px;
  background: var(--hm-green);
}
.hm-infra h2 {
  max-width: 18em;
  margin: 0;
  padding: 0;
  border: 0;
  font-size: clamp(30px, 4.2vw, 54px);
  line-height: 1.02;
  font-weight: 800;
  letter-spacing: -0.04em;
  text-wrap: balance;
  color: var(--hm-fg);
}
.hm-lead {
  max-width: 44em;
  margin: 20px 0 0;
  font-size: clamp(17px, 1.5vw, 20px);
  line-height: 1.5;
  font-weight: 450;
  letter-spacing: -0.01em;
  text-wrap: pretty;
  color: var(--hm-fg-2);
}
/* Four columns under one rule of ink, with a hairline between each and the next. */
.hm .hm-pillars {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: clamp(36px, 4.5vw, 60px);
  border-top: 2px solid var(--hm-fg);
}
.hm-pillars li + li {
  border-left: 1px solid var(--hm-rule);
}
.hm-pillars a {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 22px 22px 20px;
  transition: background-color 0.2s;
}
.hm-pillars li:first-child a {
  padding-left: 0;
}
.hm-pillars a:hover {
  background: var(--hm-sheet);
}
.hm-pillars li:first-child a:hover {
  margin-left: -22px;
  padding-left: 22px;
}
.hm-pillar-label {
  font-family: var(--hm-mono);
  font-size: 12px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--hm-fg-2);
}
.hm-pillars h3 {
  margin: 14px 0 0;
  font-size: 20px;
  line-height: 1.15;
  font-weight: 800;
  letter-spacing: -0.025em;
  color: var(--hm-fg);
}
.hm-pillars p {
  margin: 10px 0 18px;
  font-size: 15px;
  line-height: 1.55;
  color: var(--hm-fg-2);
}
.hm-pillar-go {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: auto;
  font-family: var(--hm-mono);
  font-size: 12.5px;
  font-weight: 700;
  color: var(--hm-cyan-text);
}
.hm-pillar-go svg {
  transition: transform 0.35s var(--hm-ease);
}
.hm-pillars a:hover .hm-pillar-go svg {
  transform: translateX(3px);
}

/* ---- where to get it, and the doors ----------------------------------------------------- */

.hm-end {
  padding: 0 0 clamp(56px, 7vw, 104px);
}
.hm-platforms {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
/* Sheets on the paper, with a hairline round each. */
.hm-platforms li,
.hm-doors a {
  border-radius: var(--hm-radius);
  background: var(--hm-sheet);
  box-shadow: inset 0 0 0 1px var(--hm-rule);
}
.hm-platforms li {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: space-between;
  gap: 36px;
  min-width: 0;
  padding: 24px;
}
/* The reader's own platform is inked in, under a heavier rule, without a word. */
.hm-platforms li.mine {
  box-shadow:
    inset 0 0 0 1px var(--hm-fg),
    inset 0 4px 0 0 var(--hm-fg);
}
.hm-platforms b {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 22px;
  line-height: 1;
  font-weight: 650;
  letter-spacing: -0.03em;
}
.hm-platforms b svg {
  flex: none;
  width: 26px;
  height: 26px;
  fill: currentColor;
}
.hm-platforms b svg.line {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* Where on Windows the command runs. */
.hm-platforms small {
  padding: 3px 7px;
  border-radius: var(--hm-radius);
  font-family: var(--hm-mono);
  font-size: 11.5px;
  line-height: 1.2;
  font-weight: 500;
  letter-spacing: 0;
  color: var(--hm-fg-2);
  background: color-mix(in srgb, var(--hm-fg) 7%, transparent);
}
.hm-platforms .hm-cmd {
  display: flex;
  background: var(--hm-bg);
}

.hm .hm-doors {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: clamp(40px, 5vw, 72px);
}
.hm-doors a {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  column-gap: 12px;
  height: 100%;
  padding: 18px 20px;
  font-size: 16px;
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.02em;
  transition:
    transform 0.35s var(--hm-ease),
    box-shadow 0.35s var(--hm-ease);
}
.hm-door-icon {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: var(--hm-fg-2);
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: stroke 0.25s;
}
.hm-door-go {
  color: var(--hm-fg-3);
  transition:
    transform 0.25s,
    color 0.25s;
}
/* Under the pointer a door lifts off along the diagonal and casts a hard shadow: the print's
   offset, not a blur. */
.hm-doors a:hover {
  transform: translate(-3px, -3px);
  box-shadow:
    inset 0 0 0 1px var(--hm-fg),
    6px 6px 0 0 var(--hm-fg);
}
.hm-doors a:hover .hm-door-icon {
  stroke: var(--hm-cyan-text);
}
.hm-doors a:hover .hm-door-go {
  color: var(--hm-fg);
  transform: translateX(3px);
}
.hm .hm-out {
  display: flex;
  justify-content: center;
  gap: 28px;
  margin-top: clamp(32px, 4vw, 52px);
  font-family: var(--hm-mono);
  font-size: 13.5px;
  font-weight: 700;
  color: var(--hm-fg-2);
}
.hm-out a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 2px;
  transition: color 0.2s;
}
.hm-out a:hover {
  color: var(--hm-fg);
}

/* ---- narrower windows -------------------------------------------------------------------- */

@media (max-width: 960px) {
  .hm-platforms {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
  }
  .hm-platforms li {
    flex-direction: row;
    align-items: center;
    gap: 16px;
    padding: 16px 18px;
  }
  .hm-platforms .hm-btn {
    min-width: 150px;
  }
  .hm-platforms .hm-cmd {
    flex: 0 1 280px;
  }
  .hm .hm-doors {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin-top: 32px;
  }
  .hm .hm-pillars {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .hm-pillars li:nth-child(odd) {
    border-left: 0;
  }
  .hm-pillars li:nth-child(odd) a,
  .hm-pillars li:nth-child(odd) a:hover {
    margin-left: 0;
    padding-left: 0;
  }
  .hm-pillars li:nth-child(n + 3) {
    border-top: 1px solid var(--hm-rule);
  }
}
@media (max-width: 640px) {
  .hm-wrap {
    width: calc(100% - 32px);
  }
  .hm-sky {
    height: 620px;
  }
  .hm-sky::before {
    background-size: 40px 40px;
  }
  .hm-sky::after {
    top: -120px;
    left: 58%;
    width: 300px;
    height: 300px;
  }
  .hm .hm-pillars {
    grid-template-columns: minmax(0, 1fr);
  }
  .hm-pillars li + li {
    border-left: 0;
    border-top: 1px solid var(--hm-rule);
  }
  .hm-pillars a,
  .hm-pillars li:first-child a,
  .hm-pillars a:hover,
  .hm-pillars li:first-child a:hover {
    margin-left: 0;
    padding: 20px 0;
  }
  .hm .hm-get {
    gap: 10px;
    max-width: 392px;
    margin-inline: auto;
  }
  .hm-get .hm-btn {
    flex: 1 1 0;
  }
  .hm-get .hm-cmd {
    display: flex;
    flex: 1 1 100%;
  }
  .hm-platforms .hm-cmd {
    flex: 0 1 260px;
  }
  .hm-platforms li.mine,
  .hm-platforms li {
    padding: 16px;
  }
}
@media (max-width: 520px) {
  .hm-platforms li {
    flex-wrap: wrap;
  }
  .hm-platforms .hm-btn {
    min-width: 132px;
  }
  .hm-platforms .hm-cmd {
    flex: 1 1 100%;
  }
}
@media (max-width: 400px) {
  .hm .hm-doors {
    grid-auto-rows: 1fr;
  }
  .hm-doors a {
    column-gap: 8px;
    padding: 16px 12px;
    font-size: 15px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .hm-btn,
  .hm-doors a,
  .hm-door-go,
  .hm-door-icon,
  .hm-pillars a,
  .hm-pillar-go svg {
    transition: none;
  }
}
</style>
