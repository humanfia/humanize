<script setup lang="ts">
// The first screen: what Humanize is in one line, the button that downloads it for the reader's
// platform, the one command that installs the CLI, and Humanize Desktop at work: a reel of the
// real window, captured by tests/system/docs/test_docs_home.py. Behind it, twelve faint rules
// across the whole page and one accent plane on the poster's diagonal; as the hero scrolls away
// the plane slides and the copy lifts, driven by where the hero is rather than by a timer.
import { withBase } from 'vitepress'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { clamp, useScrollProgress } from './motion'
import { detectOS, installers, PLATFORMS, type Installer, type OS } from './release'
import { REPO } from './data'

const props = defineProps<{ motion: boolean }>()

// Until the browser says which platform it is on, the button goes to the download section.
const os = ref<OS | null>(null)
const installer = ref<Installer | undefined>()
onMounted(async () => {
  os.value = detectOS()
  if (os.value) installer.value = (await installers())[os.value]
})
// Linux has no app, and a platform whose installer is not out yet has none to link: both go to
// the download section, where the CLI is.
const download = computed(() => {
  const name = PLATFORMS.find((p) => p.key === os.value)?.label
  if (os.value === 'linux') return { href: '#get-started', label: 'Install on Linux' }
  return { href: installer.value?.url ?? '#get-started', label: name ? `Download for ${name}` : 'Download' }
})

const LINE = 'uv tool install hmz'
const copied = ref(false)
let clear: ReturnType<typeof setTimeout> | undefined

async function copy() {
  try {
    await navigator.clipboard.writeText(LINE)
    copied.value = true
    clearTimeout(clear)
    clear = setTimeout(() => (copied.value = false), 1800)
  } catch {
    // No clipboard (plain http, or no gesture the browser recognises): the line is selectable.
  }
}
onBeforeUnmount(() => clearTimeout(clear))

const el = ref<HTMLElement | null>(null)
const p = useScrollProgress(el, (box) => clamp(-box.top / Math.max(1, box.height)))
const plane = computed(() => (props.motion ? { transform: `translate3d(${p.value * 30}%, ${p.value * -40}%, 0) rotate(-24deg)` } : {}))
const copyLift = computed(() =>
  props.motion ? { transform: `translate3d(0, ${p.value * -60}px, 0)`, opacity: 1 - clamp((p.value - 0.15) * 1.6) } : {},
)
</script>

<template>
  <section ref="el" class="hero" aria-labelledby="hz-title">
    <div class="hero-rule" aria-hidden="true">
      <i v-for="n in 12" :key="n" />
    </div>

    <div class="hz-wrap hero-grid">
      <div class="hero-copy" :style="copyLift">
        <p class="hz-kicker hz-load" style="--d: 0.05s">Humanize · open source</p>
        <h1 id="hz-title" class="hero-title hz-load" style="--d: 0.15s">
          Run coding agents in loops, <span>until the task is done.</span>
        </h1>
        <p class="hz-lead hz-load" style="--d: 0.3s">
          Humanize runs Claude Code, Codex and other coding agents in flows. A flow is a Python
          loop: agents work, review and retry until the task is done or the budget is spent. Watch
          every turn, step in when you want, or leave it running.
        </p>

        <div class="hz-actions hz-load" style="--d: 0.45s">
          <a class="hz-btn primary" :href="download.href">{{ download.label }}</a>
          <a class="hz-btn ghost" :href="withBase('/user/')">Documentation <span aria-hidden="true">→</span></a>
        </div>

        <div class="hero-install hz-load" style="--d: 0.58s">
          <p>Or install the CLI</p>
          <div class="hero-line">
            <code><span aria-hidden="true">$</span>{{ LINE }}</code>
            <button type="button" class="hero-copy-btn" :class="{ done: copied }" @click="copy">
              {{ copied ? 'copied' : 'copy' }}
            </button>
          </div>
        </div>

        <p class="hero-meta hz-load" style="--d: 0.7s">
          Free and open source · Apache-2.0 · macOS, Windows and Linux ·
          <a :href="REPO" target="_blank" rel="noreferrer">GitHub ↗</a> ·
          <a href="#get-started">Other platforms</a>
        </p>
      </div>

      <div class="hero-art hz-load" style="--d: 0.35s">
        <div class="hero-plane" aria-hidden="true" :style="plane" />
        <!-- Its size is the file's own, so the picture's place is kept before it loads. -->
        <img
          class="hero-reel"
          :src="withBase('/shots/home-desktop.svg')"
          width="1368"
          height="908"
          loading="eager"
          decoding="async"
          alt="Humanize Desktop starts. You pick a flow for a new epic, type a budget and a task, and the flow's two agents run the task to completion."
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero {
  position: relative;
  min-height: calc(100svh - var(--vp-nav-height));
  display: flex;
  align-items: center;
  padding: clamp(48px, 7vh, 96px) 0 clamp(64px, 9vh, 120px);
  overflow: hidden;
}

/* Twelve faint rules across the page. */
.hero-rule {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  pointer-events: none;
}
.hero-rule i {
  border-left: 1px solid var(--hz-line-2);
}
/* One accent plane on the poster's diagonal, behind the picture. */
.hero-plane {
  position: absolute;
  left: -12%;
  right: -60%;
  top: 46%;
  height: 132px;
  background: var(--hz-mark);
  opacity: 0.12;
  transform: rotate(-24deg);
  pointer-events: none;
}

.hero-grid {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr);
  align-items: center;
  gap: clamp(32px, 5vw, 80px);
  width: 100%;
}

.hero-title {
  margin: 0;
  font-size: clamp(40px, 4.4vw, 68px);
  line-height: 0.98;
  letter-spacing: -0.05em;
  font-weight: 800;
  color: var(--hz-ink);
}
.hero-title span {
  color: var(--hf-cyan-deep);
}
.hero-copy .hz-lead {
  margin-top: 26px;
  max-width: 540px;
}

/* ---- the install line ------------------------------------------------------------------ */

.hero-install {
  margin-top: 28px;
  max-width: 560px;
}
.hero-install p {
  margin: 0 0 8px;
  font: 700 11.5px/1 var(--hz-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--hz-ink-3);
}
.hero-line {
  display: flex;
  align-items: stretch;
  border: 2px solid var(--hz-ink);
  background: var(--hz-card);
}
.hero-line code {
  flex: 1;
  min-width: 0;
  padding: 13px 14px;
  overflow-x: auto;
  white-space: nowrap;
  font-size: 13px;
  color: var(--hz-ink);
  background: none;
  scrollbar-width: none;
}
.hero-line code span {
  margin-right: 10px;
  color: var(--hf-cyan-deep);
  user-select: none;
}
.hero-copy-btn {
  flex: none;
  width: 84px;
  font: 700 11.5px/1 var(--hz-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--hz-on-ink);
  background: var(--hz-ink);
  cursor: pointer;
  transition: background-color 0.2s;
}
.hero-copy-btn:hover,
.hero-copy-btn.done {
  background: var(--hz-mark);
  color: var(--hf-on-fill);
}

.hero-copy .hz-actions {
  margin-top: 32px;
}
.hero-meta {
  margin: 22px 0 0;
  font: 12px/1.6 var(--hz-mono);
  color: var(--hz-ink-3);
}
.hero-meta a {
  color: var(--hz-ink-2);
}
.hero-meta a:hover {
  color: var(--hz-accent);
}

.hero-art {
  position: relative;
  min-width: 0;
}
/* The reel draws the app's window, shadow and all, on nothing: it sits on the page as it is. */
.hero-reel {
  position: relative;
  display: block;
  width: 100%;
  height: auto;
}

@media (max-width: 1080px) {
  .hero-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .hero {
    min-height: 0;
  }
  .hero-art {
    max-width: 720px;
  }
  .hero-rule {
    grid-template-columns: repeat(6, 1fr);
  }
  .hero-rule i:nth-child(n + 7) {
    display: none;
  }
}
</style>
