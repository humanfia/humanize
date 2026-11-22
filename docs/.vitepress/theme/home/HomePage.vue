<script setup lang="ts">
// The Humanize page: docs/index.md is this component and nothing else. It is the project's page
// on humanfia.ai (humanfia.ai/humanize/) and the front page of its documentation at once.
//
// It opens as a project's page does: its mark and its name, the repository's description under
// them, the button that gets it, the one to the documentation and the command that installs it;
// and under those one window that plays the real product, a scene at a time (HomeStage.vue).
// Below, the loop itself, drawn and moving (HomeLoop.vue); where to get it for each platform;
// and the doors into the documentation. There is no sentence on it but the description: what it
// has to say, the pictures say, and its few words are in copy.ts.
import { withBase } from 'vitepress'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import HomeLoop from './HomeLoop.vue'
import HomeStage from './HomeStage.vue'
import { BANNER, WORDS } from './copy'
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

/** Whether the reader stopped what moves: the stage has the control, and the loop follows it. */
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

    <section class="hm-wrap hm-loop"><HomeLoop :paused="paused" /></section>

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
/* The page's own colours: humanfia.ai's ink, paper, pink and cyan, and the green of Humanize's
   mark, by the names this page draws with, set once for the light theme and once for the dark.
   They are scoped to the page's root, so no other page can come to depend on them. */
.hm {
  --hm-ink: #0f1519;
  --hm-paper: #eef4f6;
  --hm-bg: #f5f8f9;
  --hm-sheet: #ffffff;
  --hm-fg: var(--hm-ink);
  --hm-fg-2: #46545c;
  --hm-fg-3: #65747c;
  --hm-ring: var(--hm-fg);
  --hm-pink: #ec6fa3;
  --hm-pink-text: #b83a72;
  --hm-cyan: #1fb3c7;
  --hm-green: #76b900;
  --hm-green-text: #4c7a00;
  --hm-rule: color-mix(in srgb, var(--hm-ink) 11%, transparent);
  --hm-rule-strong: color-mix(in srgb, var(--hm-ink) 24%, transparent);
  --hm-pink-fill: color-mix(in srgb, var(--hm-pink) 30%, var(--hm-sheet));
  --hm-cyan-fill: color-mix(in srgb, var(--hm-cyan) 26%, var(--hm-sheet));
  /* The window's ground and edge, what its shadow is made of, and how bright it is lit. */
  --hm-house: #ffffff;
  --hm-edge: color-mix(in srgb, var(--hm-ink) 14%, transparent);
  --hm-shade: #1c3640;
  --hm-glow: 0.42;
  --hm-grid: color-mix(in srgb, var(--hm-ink) 7%, transparent);
  --hm-mono: var(--vp-font-family-mono);
}
.dark .hm {
  --hm-bg: #0a0f12;
  --hm-sheet: #121a1f;
  --hm-fg: var(--hm-paper);
  --hm-fg-2: #aebdc3;
  --hm-fg-3: #82939a;
  --hm-pink: #ff94c2;
  --hm-pink-text: #ffa8cf;
  --hm-cyan: #4fd8ea;
  --hm-green: #8fd400;
  --hm-green-text: #a5e03a;
  --hm-rule: color-mix(in srgb, var(--hm-paper) 11%, transparent);
  --hm-rule-strong: color-mix(in srgb, var(--hm-paper) 24%, transparent);
  --hm-pink-fill: color-mix(in srgb, var(--hm-pink) 30%, var(--hm-sheet));
  --hm-cyan-fill: color-mix(in srgb, var(--hm-cyan) 26%, var(--hm-sheet));
  --hm-house: #10181d;
  --hm-edge: color-mix(in srgb, var(--hm-paper) 22%, transparent);
  --hm-shade: #000000;
  --hm-glow: 0.6;
  --hm-grid: color-mix(in srgb, var(--hm-paper) 6%, transparent);
}

/* The page is its own layout: the theme's content column and its prose styles are not used. */
.hm-page .VPContent {
  background: #f5f8f9;
}
.dark .hm-page .VPContent {
  background: #0a0f12;
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

/* ---- the sky: a fine grid that fades out, lit in two colours from above ------------------ */

.hm-sky {
  position: absolute;
  inset: 0 0 auto;
  height: 880px;
  pointer-events: none;
  /* It comes in under the site's bar, so there is no seam where the bar ends. */
  mask-image: linear-gradient(transparent, #000 200px);
}
.hm-sky::before,
.hm-sky::after {
  content: '';
  position: absolute;
  inset: 0;
}
.hm-sky::before {
  background:
    linear-gradient(var(--hm-grid) 1px, transparent 1px) 50% 0 / 56px 56px,
    linear-gradient(90deg, var(--hm-grid) 1px, transparent 1px) 50% 0 / 56px 56px;
  mask-image: radial-gradient(ellipse 62% 70% at 50% 0%, #000 20%, transparent 78%);
}
.hm-sky::after {
  background:
    radial-gradient(38% 46% at 28% 0%, color-mix(in srgb, var(--hm-cyan) 22%, transparent), transparent 70%),
    radial-gradient(38% 46% at 72% 0%, color-mix(in srgb, var(--hm-pink) 20%, transparent), transparent 70%);
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

.hm-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  height: 46px;
  padding: 0 20px;
  border-radius: 12px;
  font-size: 15px;
  line-height: 1;
  font-weight: 600;
  letter-spacing: -0.01em;
  background: var(--hm-sheet);
  box-shadow:
    inset 0 0 0 1px var(--hm-rule-strong),
    0 1px 2px color-mix(in srgb, var(--hm-shade) 8%, transparent);
  transition:
    transform 0.2s,
    box-shadow 0.2s,
    background-color 0.2s;
}
.hm-btn svg,
.hm-out svg,
.hm-cmd svg,
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
  box-shadow:
    0 1px 2px color-mix(in srgb, var(--hm-shade) 20%, transparent),
    0 8px 20px -8px color-mix(in srgb, var(--hm-shade) 45%, transparent);
}
.hm-btn:hover {
  transform: translateY(-1px);
  box-shadow:
    inset 0 0 0 1px var(--hm-fg-3),
    0 6px 14px -6px color-mix(in srgb, var(--hm-shade) 24%, transparent);
}
.hm .hm-btn.go:hover {
  box-shadow:
    0 2px 4px color-mix(in srgb, var(--hm-shade) 20%, transparent),
    0 14px 28px -10px color-mix(in srgb, var(--hm-pink) 70%, transparent);
}
.hm-btn:active {
  transform: none;
}

.hm-cmd {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  height: 46px;
  padding: 0 6px 0 16px;
  border-radius: 12px;
  font-family: var(--hm-mono);
  font-size: 13.5px;
  color: var(--hm-fg);
  background: color-mix(in srgb, var(--hm-sheet) 60%, transparent);
  box-shadow: inset 0 0 0 1px var(--hm-rule);
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
  border-radius: 8px;
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

/* ---- the loop, drawn ------------------------------------------------------------------- */

.hm-loop {
  max-width: 880px;
  padding: clamp(32px, 5vw, 72px) 0;
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
.hm-platforms li,
.hm-doors a {
  border-radius: 16px;
  background: var(--hm-sheet);
  box-shadow:
    inset 0 0 0 1px var(--hm-rule),
    0 1px 2px color-mix(in srgb, var(--hm-shade) 5%, transparent);
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
/* The reader's own platform is lit, without a word. */
.hm-platforms li.mine {
  box-shadow:
    inset 0 0 0 1.5px color-mix(in srgb, var(--hm-cyan) 70%, transparent),
    0 18px 40px -22px color-mix(in srgb, var(--hm-cyan) 80%, transparent);
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
  border-radius: 6px;
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
  background: color-mix(in srgb, var(--hm-fg) 4%, transparent);
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
  border-radius: 12px;
  font-size: 16px;
  line-height: 1.15;
  font-weight: 650;
  letter-spacing: -0.02em;
  transition:
    transform 0.25s,
    box-shadow 0.25s;
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
.hm-doors a:hover {
  transform: translateY(-2px);
  box-shadow:
    inset 0 0 0 1px var(--hm-rule-strong),
    0 16px 32px -18px color-mix(in srgb, var(--hm-shade) 40%, transparent);
}
.hm-doors a:hover .hm-door-icon {
  stroke: var(--hm-pink-text);
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
  font-size: 15px;
  font-weight: 500;
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
  .hm-door-icon {
    transition: none;
  }
}
</style>
