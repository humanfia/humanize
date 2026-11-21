<script setup lang="ts">
// The Humanize page: docs/index.md is this component and nothing else. It is the project's page
// on humanfia.ai (humanfia.ai/humanize/) and the front page of its documentation at once.
//
// It is a page of pictures. Its banner is the repository's description; under it one screen
// plays the real product, a scene at a time (HomeStage.vue), beside the button that gets it,
// the one to the documentation and the command that installs it. Below, the loop itself, drawn
// and moving (HomeLoop.vue); where to get it for each platform; and the doors into the
// documentation. There is no sentence on it: what it has to say, the pictures say, and its few
// words are in copy.ts.
//
// What gets it is handed to the stage, which puts it in the page's source where the reader sees
// it, so that the keyboard walks what is shown in the order it is shown: first, over the tabs,
// on a phone and a tablet (and before the script runs); last, after the screen, on a desk, where
// it stands under the tabs.
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

// The banner is the description as written; its full stop alone is set in the accent.
const SAID = BANNER.replace(/\.$/, '')

const DOORS = [
  { name: 'Tutorials', href: '/tutorials/' },
  { name: 'User Guide', href: '/user/' },
  { name: 'Builder Guide', href: '/builder/' },
  { name: 'Reference', href: '/reference/' },
]
</script>

<template>
  <div class="hm">
    <div class="hm-wrap">
      <h1 class="hm-banner">{{ SAID }}<i>.</i></h1>

      <section class="hm-house">
        <HomeStage v-model:paused="paused">
          <div class="hm-get">
            <a class="hm-btn go" :href="get">
              {{ WORDS.download }}
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1v10M3.5 7 8 11.5 12.5 7M2 15h12" /></svg>
            </a>
            <a class="hm-btn" :href="withBase('/tutorials/')">
              {{ WORDS.docs }}
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 8h11M8.5 3.5 13 8l-4.5 4.5" /></svg>
            </a>
            <div class="hm-cmd">
              <code>{{ INSTALL }}</code>
              <button type="button" aria-live="polite" @click="copy('top')">{{ copied === 'top' ? WORDS.copied : WORDS.copy }}</button>
            </div>
          </div>
        </HomeStage>
      </section>
    </div>

    <section class="hm-band">
      <div class="hm-wrap hm-loop"><HomeLoop :paused="paused" /></div>
    </section>

    <section id="get" class="hm-wrap hm-end">
      <ul class="hm-platforms">
        <li :class="{ mine: os === 'macos' }">
          <b>macOS</b>
          <a class="hm-btn go" :href="mac">
            {{ WORDS.download }}
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1v10M3.5 7 8 11.5 12.5 7M2 15h12" /></svg>
          </a>
        </li>
        <li :class="{ mine: os === 'windows', cmd: !found.windows }">
          <b>Windows <small v-if="!found.windows">{{ WORDS.wsl }}</small></b>
          <a v-if="found.windows" class="hm-btn go" :href="found.windows">
            {{ WORDS.download }}
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1v10M3.5 7 8 11.5 12.5 7M2 15h12" /></svg>
          </a>
          <div v-else class="hm-cmd boxed">
            <code>{{ INSTALL }}</code>
            <button type="button" aria-live="polite" @click="copy('windows')">{{ copied === 'windows' ? WORDS.copied : WORDS.copy }}</button>
          </div>
        </li>
        <li class="cmd" :class="{ mine: os === 'linux' }">
          <b>Linux</b>
          <div class="hm-cmd boxed">
            <code>{{ INSTALL }}</code>
            <button type="button" aria-live="polite" @click="copy('linux')">{{ copied === 'linux' ? WORDS.copied : WORDS.copy }}</button>
          </div>
        </li>
      </ul>

      <ul class="hm-doors">
        <li v-for="door in DOORS" :key="door.name">
          <a :href="withBase(door.href)">
            {{ door.name }}
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 8h11M8.5 3.5 13 8l-4.5 4.5" /></svg>
          </a>
        </li>
      </ul>
      <ul class="hm-out">
        <li>
          <a href="https://humanfia.ai/flows/">Flows <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 12 12 4M5.5 4H12v6.5" /></svg></a>
        </li>
        <li>
          <a :href="REPO">GitHub <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 12 12 4M5.5 4H12v6.5" /></svg></a>
        </li>
      </ul>
    </section>
  </div>
</template>

<style>
/* The page's own colours: humanfia.ai's ink, paper, pink and cyan, by the names this page draws
   with, set once for the light theme and once for the dark. They are scoped to the page's root,
   so no other page can come to depend on them. */
.hm {
  --hm-ink: #141a1f;
  --hm-paper: #e8f0f2;
  --hm-bg: var(--hm-paper);
  --hm-sheet: #ffffff;
  --hm-fg: var(--hm-ink);
  --hm-fg-2: #435058;
  --hm-fg-3: #5d6a72;
  /* A tab that is not on: dimmer than the one under the pointer, and still legible. */
  --hm-fg-dim: color-mix(in srgb, var(--hm-ink) 56%, var(--hm-paper));
  /* The ring of the keyboard's focus: the text's own colour, which stands out on every ground. */
  --hm-ring: var(--hm-fg);
  --hm-pink: #ec6fa3;
  --hm-pink-text: #b83a72;
  --hm-cyan: #1fb3c7;
  --hm-rule: color-mix(in srgb, var(--hm-ink) 16%, transparent);
  --hm-rule-strong: color-mix(in srgb, var(--hm-ink) 38%, transparent);
  --hm-pink-fill: color-mix(in srgb, var(--hm-pink) 42%, var(--hm-sheet));
  --hm-cyan-fill: color-mix(in srgb, var(--hm-cyan) 38%, var(--hm-sheet));
  /* The screen's block, its edge and how far its shadow is cast. */
  --hm-house: var(--hm-ink);
  --hm-edge: var(--hm-ink);
  --hm-cast: 10px;
  --hm-band: #dde8eb;
  --hm-mono: var(--vp-font-family-mono);
}
.dark .hm {
  --hm-bg: #10161a;
  --hm-sheet: #19232a;
  --hm-fg: var(--hm-paper);
  --hm-fg-2: #b3c3c8;
  --hm-fg-3: #82939a;
  --hm-fg-dim: color-mix(in srgb, var(--hm-paper) 46%, #10161a);
  --hm-pink: #ff94c2;
  --hm-pink-text: #ffa8cf;
  --hm-cyan: #4fd8ea;
  --hm-rule: color-mix(in srgb, var(--hm-paper) 16%, transparent);
  --hm-rule-strong: color-mix(in srgb, var(--hm-paper) 40%, transparent);
  --hm-pink-fill: color-mix(in srgb, var(--hm-pink) 34%, var(--hm-sheet));
  --hm-cyan-fill: color-mix(in srgb, var(--hm-cyan) 30%, var(--hm-sheet));
  --hm-house: #0a0e11;
  --hm-edge: color-mix(in srgb, var(--hm-paper) 24%, transparent);
  --hm-band: #0a0e11;
}

/* The page is its own layout: the theme's content column and its prose styles are not used. */
.hm-page .VPContent {
  background: var(--hm-bg, #e8f0f2);
}
.dark .hm-page .VPContent {
  background: #10161a;
}
.hm {
  color: var(--hm-fg);
  background: var(--hm-bg);
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
  width: min(100% - 64px, 1360px);
  margin: 0 auto;
}

/* ---- the banner: one line, as wide as the page ----------------------------------------- */

.hm-banner {
  margin: 0;
  padding: 30px 0 26px;
  font-size: min(4.72vw, 70px);
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.035em;
  white-space: nowrap;
  color: var(--hm-fg);
}
.hm-banner i {
  font-style: normal;
  color: var(--hm-pink);
}

/* ---- the house: the tabs and what gets it, beside the screen ---------------------------- */

.hm-house {
  /* What is left of the first screen under the site's bar and the banner is the screen's. */
  --room: calc(100svh - var(--vp-nav-height, 64px) - min(4.72vw, 70px) - 56px - 44px);
  /* How tall the screen comes out, near enough: its width is what the window leaves beside the
     column (about 222px of it, the command's line, and the 40px between), or what the room's
     height allows, and its shape is the window's. */
  --tall: calc(min(min(100vw - 80px, 1360px) - 262px - var(--hm-cast), max(620px, var(--room) * 1.5294)) / 1.5294);
  /* The column shrinks with the screen, so that it is never the taller of the two and what gets
     it ends level with the screen: whole from a screen 597px tall, smallest at one of 369px,
     which is the least a desk's window leaves. */
  --tab-size: clamp(20px, min(2.75vw, var(--tall) * 0.08772 - 12.37px), 40px);
  --tab-pad: clamp(5px, var(--tall) * 0.035088 - 7.947px, 13px);
  --get-pad: clamp(10px, var(--tall) * 0.078947 - 19.13px, 28px);
  display: grid;
  /* The column is as wide as what is in it, so it has one right edge; the screen takes what it
     wants of the rest, and the column whatever is left over. */
  grid-template-columns: minmax(max-content, 1fr) minmax(0, calc(max(620px, var(--room) * 1.5294) + var(--hm-cast)));
  grid-template-rows: auto 1fr;
  gap: 0 40px;
  padding-bottom: 44px;
}
.hm-house > .st-tabs {
  grid-area: 1 / 1;
  margin-top: calc(-1 * var(--tab-pad));
}
.hm-house > .st-screen {
  grid-area: 1 / 2 / 3 / 3;
  margin: 0 var(--hm-cast) var(--hm-cast) 0;
  align-self: start;
}
.hm-get {
  grid-area: 2 / 1;
  align-self: end;
  display: grid;
  gap: 10px;
  padding: var(--get-pad) 0 var(--hm-cast);
}

.hm-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  height: 48px;
  padding: 0 16px;
  border: 2px solid var(--hm-fg);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
  transition:
    background-color 0.2s,
    color 0.2s,
    border-color 0.2s;
}
.hm-btn svg,
.hm-doors svg,
.hm-out svg {
  flex: none;
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
}
.hm .hm-btn.go {
  border-color: var(--hm-pink);
  color: var(--hm-ink);
  background: var(--hm-pink);
}
.hm .hm-btn:hover {
  border-color: var(--hm-fg);
  color: var(--hm-bg);
  background: var(--hm-fg);
}

.hm-cmd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  height: 42px;
  border-top: 2px solid var(--hm-rule);
  font-family: var(--hm-mono);
  font-size: 13px;
  color: var(--hm-fg-2);
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
/* As wide as its longer word, so the line beside it does not move when it is copied. */
.hm-cmd button {
  flex: none;
  min-width: 6ch;
  padding: 4px 0;
  font-family: var(--hm-mono);
  font-size: 13px;
  text-align: right;
  color: var(--hm-pink-text);
}
.hm-cmd button:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* ---- the loop, drawn, on a band of its own ---------------------------------------------- */

.hm-band {
  background: var(--hm-band);
}
.hm-loop {
  max-width: 1040px;
  padding: clamp(36px, 6vw, 84px) 0;
}

/* ---- where to get it, and the doors ----------------------------------------------------- */

.hm-end {
  padding: clamp(40px, 6vw, 88px) 0 clamp(48px, 6vw, 96px);
}
.hm-platforms {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border: 2px solid var(--hm-fg);
}
.hm-platforms li {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: space-between;
  gap: 40px;
  min-width: 0;
  padding: 28px;
}
.hm-platforms li + li {
  border-left: 2px solid var(--hm-fg);
}
.hm-platforms li.mine {
  background: var(--hm-sheet);
}
.hm-platforms b {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: clamp(26px, 2.6vw, 36px);
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.035em;
}
/* Where on Windows the command runs. */
.hm-platforms small {
  align-self: flex-end;
  font-family: var(--hm-mono);
  font-size: 13px;
  line-height: 1.4;
  font-weight: 400;
  letter-spacing: 0;
  color: var(--hm-fg-3);
}
/* The reader's own platform is marked, without a word. */
.hm-platforms li.mine b::after {
  content: '';
  width: 12px;
  height: 12px;
  background: var(--hm-pink);
}
.hm-platforms .hm-btn {
  min-width: 168px;
}
.hm-cmd.boxed {
  align-self: stretch;
  height: 48px;
  padding: 0 14px;
  border: 2px solid var(--hm-fg);
  color: var(--hm-fg);
}

.hm .hm-doors {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: clamp(36px, 5vw, 72px);
  border-top: 2px solid var(--hm-fg);
  border-bottom: 2px solid var(--hm-fg);
}
.hm-doors li + li {
  border-left: 2px solid var(--hm-fg);
}
.hm-doors a {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  min-height: 132px;
  padding: 22px;
  font-size: clamp(22px, 2.3vw, 32px);
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.035em;
  transition:
    background-color 0.2s,
    color 0.2s;
}
.hm-doors li:first-child a {
  padding-left: 0;
}
.hm-doors svg {
  width: 26px;
  height: 26px;
  transition: transform 0.25s;
}
.hm-doors a:hover {
  color: var(--hm-pink-text);
}
.hm-doors a:hover svg {
  transform: translateX(5px);
}
.hm .hm-out {
  display: flex;
  gap: 36px;
  margin-top: 22px;
  font-size: 17px;
  font-weight: 700;
}
.hm-out a {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.hm-out a:hover {
  color: var(--hm-pink-text);
}

/* ---- narrower windows -------------------------------------------------------------------- */

/* The platforms are a list until three of them fit side by side with the command in two. */
@media (max-width: 1040px) {
  .hm-platforms {
    grid-template-columns: minmax(0, 1fr);
  }
  .hm-platforms li {
    flex-direction: row;
    align-items: center;
    gap: 16px;
    padding: 18px;
  }
  .hm-platforms li + li {
    border-top: 2px solid var(--hm-fg);
    border-left: 0;
  }
  .hm-platforms .hm-btn {
    min-width: 150px;
  }
  .hm-platforms .hm-cmd.boxed {
    flex: 0 1 300px;
    align-self: auto;
  }
}
@media (max-width: 560px) {
  .hm-platforms li {
    padding: 16px 14px;
  }
  .hm-platforms li.cmd {
    flex-direction: column;
    align-items: flex-start;
  }
  .hm-platforms .hm-btn {
    min-width: 132px;
  }
  .hm-platforms .hm-cmd.boxed {
    flex: none;
    align-self: stretch;
    padding: 0 10px;
  }
}

/* A tablet and a phone: what gets it comes first, under the banner; then the tabs, in rows, and
   the screen under them, as wide as the page. HomeStage.vue has the same two widths: to 900px
   the stage is stacked, and to 640px it plays the reels shot for a phone. */
@media (max-width: 900px) {
  .hm-wrap {
    width: calc(100% - 32px);
  }
  .hm {
    --hm-cast: 6px;
  }
  .hm-banner {
    padding: 22px 0 18px;
    font-size: clamp(34px, 10.4vw, 60px);
    line-height: 0.98;
    white-space: normal;
    text-wrap: balance;
  }
  .hm-house {
    display: flex;
    flex-direction: column;
    /* Room for the stage's control under the screen. */
    padding-bottom: 52px;
  }
  .hm-get {
    grid-template-columns: 1fr 1fr;
    align-self: stretch;
    padding: 0 0 10px;
  }
  .hm-get .hm-cmd {
    grid-column: 1 / -1;
  }
  .hm-house > .st-tabs {
    margin: 0 0 16px;
  }
  /* The screen is as wide as the page, but no taller than lets the whole scene and its tabs be
     seen together under the site's bar, where the window is tall enough for that at all. */
  .hm-house > .st-screen {
    align-self: center;
    width: min(100% - var(--hm-cast), max(380px, (100svh - var(--vp-nav-height, 64px) - 76px) * var(--desk-n, 1.5294)));
    margin: 0 var(--hm-cast) var(--hm-cast) 0;
  }
  .hm .hm-doors {
    grid-template-columns: minmax(0, 1fr);
    border-bottom: 0;
  }
  .hm-doors li {
    border-bottom: 2px solid var(--hm-fg);
  }
  .hm-doors li + li {
    border-left: 0;
  }
  .hm-doors a,
  .hm-doors li:first-child a {
    align-items: center;
    min-height: 0;
    padding: 20px 0;
    font-size: 28px;
  }
}
@media (max-width: 640px) {
  .hm-house > .st-screen {
    width: min(100% - var(--hm-cast), max(240px, (100svh - var(--vp-nav-height, 64px) - 124px) * var(--phone-n, 0.7538)));
  }
}
@media (prefers-reduced-motion: reduce) {
  .hm-btn,
  .hm-doors a,
  .hm-doors svg {
    transition: none;
  }
}
</style>
