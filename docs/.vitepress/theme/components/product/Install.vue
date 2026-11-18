<script setup lang="ts">
// Getting Humanize, as an open-source project's download page does it: the app or the command
// line, for the platform the reader is on -- found out for them, and theirs to change. The
// documentation has the rest; this is the one screen from nothing to installed.
import { withBase } from 'vitepress'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { detectOS, installers, PLATFORMS, RELEASES, type Installer, type OS } from './release'

const REPO = 'https://github.com/humanfia/humanize'

type Product = 'desktop' | 'cli'
const PRODUCTS: { key: Product; label: string }[] = [
  { key: 'desktop', label: 'Humanize Desktop' },
  { key: 'cli', label: 'Humanize CLI' },
]

const product = ref<Product>('desktop')
const os = ref<OS>('macos')
const detected = ref<OS | null>(null)
const found = ref<Partial<Record<OS, Installer>>>({})

onMounted(async () => {
  detected.value = detectOS()
  if (detected.value) os.value = detected.value
  if (detected.value === 'linux') product.value = 'cli'
  found.value = await installers()
})

const DESKTOP: Partial<Record<OS, { label: string; meta: string; steps: string[] }>> = {
  macos: {
    label: 'Download for macOS',
    meta: 'Universal · macOS 11 or newer · .dmg',
    steps: [
      'Open the .dmg and drag Humanize Desktop onto Applications.',
      "Install the Humanize CLI too (uv tool install hmz): the app reaches this Mac's epics through it.",
      'Open it.',
    ],
  },
  windows: {
    label: 'Download for Windows',
    meta: 'x64 · Windows 10 or 11 · needs WSL 2',
    steps: [
      'No WSL yet? Run wsl --install in PowerShell and restart.',
      'Run the installer. The first launch installs the Humanize CLI in WSL for you.',
    ],
  },
}

const UV = 'curl -LsSf https://astral.sh/uv/install.sh | sh'
const CLI: Record<OS, { lines: string[]; note: string }> = {
  macos: { lines: [UV, 'uv tool install hmz'], note: 'Skip the first line if you have uv. Or: pip install hmz, with Python 3.12 or newer.' },
  linux: { lines: [UV, 'uv tool install hmz'], note: 'Skip the first line if you have uv. Or: pip install hmz, with Python 3.12 or newer.' },
  windows: {
    lines: ['wsl --install', '# then, in a WSL terminal:', UV, 'uv tool install hmz'],
    note: 'Humanize runs in WSL on Windows. Skip wsl --install if you have it.',
  },
}

const desktop = computed(() => DESKTOP[os.value])
const installer = computed(() => found.value[os.value])
const cli = computed(() => CLI[os.value])

const copied = ref(false)
let clear: ReturnType<typeof setTimeout> | undefined
async function copy() {
  const text = cli.value.lines.filter((l) => !l.startsWith('#')).join('\n')
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    return // No clipboard here (plain http, say): the lines can still be selected.
  }
  copied.value = true
  clearTimeout(clear)
  clear = setTimeout(() => (copied.value = false), 1800)
}
onBeforeUnmount(() => clearTimeout(clear))

const NEXT = [
  { title: 'Sign in to a coding agent', body: 'Claude Code, Codex or any other you use. Humanize runs it under your own login.' },
  { title: 'Pick a flow and give it a task', body: 'In Humanize Desktop, in a browser with hmz web, or in the terminal with hmz.' },
]
</script>

<template>
  <div class="dl">
    <div class="dl-bar">
      <div class="dl-tabs" role="tablist" aria-label="What to install">
        <button
          v-for="p in PRODUCTS"
          :key="p.key"
          type="button"
          role="tab"
          :aria-selected="product === p.key"
          :class="{ on: product === p.key }"
          @click="product = p.key"
        >
          {{ p.label }}
        </button>
      </div>
      <div class="dl-tabs small" role="tablist" aria-label="Platform">
        <button
          v-for="p in PLATFORMS"
          :key="p.key"
          type="button"
          role="tab"
          :aria-selected="os === p.key"
          :class="{ on: os === p.key }"
          @click="os = p.key"
        >
          {{ p.label }}<span v-if="detected === p.key" class="dl-you"> · yours</span>
        </button>
      </div>
    </div>

    <div class="dl-body">
      <div class="dl-main">
        <template v-if="product === 'desktop' && desktop">
          <a class="dl-get" :href="installer?.url ?? RELEASES" :download="installer ? '' : undefined">
            <b>{{ desktop.label }}</b>
            <span>{{ desktop.meta }}<template v-if="installer"> · v{{ installer.version }}</template></span>
          </a>
          <ol class="dl-steps">
            <li v-for="s in desktop.steps" :key="s">{{ s }}</li>
          </ol>
        </template>

        <template v-else-if="product === 'desktop'">
          <p class="dl-none">
            Humanize Desktop is for macOS and Windows. On Linux, install the CLI and run
            <code>hmz web</code> for the same interface in your browser.
          </p>
          <button type="button" class="dl-switch" @click="product = 'cli'">Install the CLI →</button>
        </template>

        <template v-else>
          <div class="dl-term">
            <code>
              <span v-for="line in cli.lines" :key="line" :class="{ c: line.startsWith('#') }">
                <i v-if="!line.startsWith('#')" aria-hidden="true">$</i>{{ line }}
              </span>
            </code>
            <button type="button" class="dl-copy" :class="{ done: copied }" @click="copy">
              {{ copied ? 'copied' : 'copy' }}
            </button>
          </div>
          <p class="dl-note">{{ cli.note }}</p>
        </template>

        <p class="dl-links">
          <a :href="withBase('/user/installation')">Installation guide →</a>
          <a :href="RELEASES">All releases ↗</a>
          <a :href="REPO">Source ↗</a>
        </p>
      </div>

      <ol class="dl-next">
        <li v-for="(n, i) in NEXT" :key="n.title">
          <span class="dl-n">{{ String(i + 2).padStart(2, '0') }}</span>
          <div>
            <strong>{{ n.title }}</strong>
            <p>{{ n.body }}</p>
          </div>
        </li>
      </ol>
    </div>
  </div>
</template>

<style scoped>
.dl {
  container-type: inline-size;
  margin-top: 28px;
}

.dl-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 24px;
  margin-bottom: 14px;
}
.dl-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.dl-tabs button {
  padding: 8px 16px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: none;
  font-size: 14px;
  font-weight: 600;
  color: var(--vp-c-text-2);
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s, background-color 0.2s;
}
.dl-tabs.small button {
  padding: 6px 13px;
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  font-weight: 500;
}
.dl-tabs button:hover {
  color: var(--vp-c-text-1);
}
.dl-tabs button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}
.dl-you {
  color: var(--vp-c-text-3);
}

.dl-body {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, 1fr);
  gap: 20px;
}
.dl-main {
  display: flex;
  flex-direction: column;
  padding: 24px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 16px;
  background: var(--vp-c-bg-soft);
}

.dl-get {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-self: flex-start;
  padding: 16px 26px;
  border-radius: 12px;
  background: var(--vp-c-brand-1);
  color: var(--vp-c-bg) !important;
  text-decoration: none !important;
  transition: transform 0.2s, filter 0.2s;
}
.dl-get:hover {
  transform: translateY(-2px);
  filter: brightness(1.08);
}
.dl-get b {
  font-size: 18px;
  letter-spacing: -0.01em;
}
.dl-get span {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  opacity: 0.85;
}

.dl-steps {
  margin: 18px 0 0;
  padding-left: 20px;
  font-size: 14.5px;
  line-height: 1.7;
  color: var(--vp-c-text-2);
}

.dl-none {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}
.dl-switch {
  align-self: flex-start;
  margin-top: 14px;
  padding: 0;
  border: 0;
  background: none;
  font-size: 15px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  cursor: pointer;
}

.dl-term {
  position: relative;
  padding: 16px 84px 16px 18px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
}
.dl-term code {
  display: block;
  padding: 0;
  background: none;
  font-family: var(--vp-font-family-mono);
  font-size: 13.5px;
  line-height: 1.85;
  color: var(--vp-c-text-1);
}
.dl-term code > span {
  display: block;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.dl-term code > span.c {
  color: var(--vp-c-text-3);
}
.dl-term i {
  display: inline-block;
  width: 1.35em;
  font-style: normal;
  color: var(--vp-c-brand-1);
  user-select: none;
}
.dl-copy {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 4px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 7px;
  background: var(--vp-c-bg-soft);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--vp-c-text-3);
  cursor: pointer;
}
.dl-copy:hover,
.dl-copy.done {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}
.dl-note {
  margin: 12px 0 0;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--vp-c-text-3);
}

.dl-links {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  margin: auto 0 0;
  padding-top: 20px;
  font-size: 13.5px;
}
.dl-links a {
  font-weight: 600;
  color: var(--vp-c-brand-1);
  text-decoration: none;
}
.dl-links a:hover {
  text-decoration: underline;
}

.dl-next {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.dl-next li {
  display: flex;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg-soft);
}
.dl-n {
  flex: none;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--vp-c-brand-1);
}
.dl-next strong {
  display: block;
  font-size: 15px;
  color: var(--vp-c-text-1);
}
.dl-next p {
  margin: 5px 0 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--vp-c-text-3);
}

@container (max-width: 760px) {
  .dl-body {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
