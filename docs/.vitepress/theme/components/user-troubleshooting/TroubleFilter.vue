<script setup lang="ts">
// Narrows Troubleshooting to the entries a message matches. The entries are the page's own
// `###` sections, read once the page is mounted, so every message is written once -- in the
// markdown -- and this holds no copy of any of them.
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface Group {
  nodes: HTMLElement[]
  entries: Entry[]
}

interface Entry {
  nodes: HTMLElement[]
  // The words of the heading, which for most entries is the message itself.
  head: Set<string>
  // Every word of the entry, heading and body.
  words: string[]
  // Whether the heading quotes a message, rather than naming a symptom.
  message: boolean
}

// Words that say nothing about which message it is, and the prefixes humanize puts in front.
const STOP = new Set([
  'a', 'an', 'and', 'as', 'at', 'be', 'by', 'for', 'in', 'is', 'it', 'its', 'of', 'on', 'or',
  'the', 'this', 'that', 'to', 'with', 'hmz', 'exec', 'error',
])

// How much of a quoted message has to be in what was pasted. Below all of it, because a
// pasted message carries its own flow, role and host where the heading has an example.
const PASTED = 0.6

const EXAMPLES = ['needs an agent', 'throttled', 'not been fetched', 'over ssh']

function wordsOf(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9_]+/)
    .filter((word) => word.length > 1 && !STOP.has(word))
}

// What was typed, less a last word that is still on its way to being one of the dropped ones:
// `erro` is `error` half typed, and narrowing on it would hide every entry for a keystroke.
function askedOf(text: string): string[] {
  const asked = wordsOf(text)
  const last = asked[asked.length - 1]
  const typing = /[a-z0-9_]$/i.test(text)
  if (typing && last && [...STOP].some((word) => word.startsWith(last))) asked.pop()
  return asked
}

const root = ref<HTMLElement | null>(null)
const query = ref('')
const total = ref(0)
const shown = ref(0)
const ready = ref(false)

let groups: Group[] = []

function read(): void {
  const first = root.value?.closest('.vp-doc')?.querySelector('h2')
  const content = first?.parentElement
  if (!content) return
  const found: Group[] = []
  let group: Group | null = null
  let entry: Entry | null = null
  for (const child of Array.from(content.children) as HTMLElement[]) {
    if (child.tagName === 'H2') {
      group = { nodes: [child], entries: [] }
      found.push(group)
      entry = null
    } else if (!group) {
      continue
    } else if (child.tagName === 'H3') {
      entry = {
        nodes: [child],
        head: new Set(wordsOf(child.textContent ?? '')),
        words: [],
        message: child.querySelector('code') !== null,
      }
      group.entries.push(entry)
    } else {
      ;(entry ?? group).nodes.push(child)
    }
  }
  // A section with no entries of its own -- the one at the foot -- is shown whatever is typed.
  groups = found.filter((one) => one.entries.length > 0)
  for (const one of groups) {
    for (const each of one.entries) {
      each.words = each.nodes.flatMap((node) => wordsOf(node.textContent ?? ''))
    }
  }
  total.value = groups.reduce((sum, one) => sum + one.entries.length, 0)
  shown.value = total.value
}

function matches(entry: Entry, asked: string[]): boolean {
  if (asked.length === 0) return true
  // Part of a message typed, or a symptom: every word is somewhere in the entry, and the
  // last one may still be being typed.
  const last = asked[asked.length - 1]
  const has = new Set(entry.words)
  if (asked.slice(0, -1).every((word) => has.has(word)) && entry.words.some((word) => word.startsWith(last))) {
    return true
  }
  // A whole message pasted, with its own names in it: most of the quoted message is there.
  if (!entry.message || entry.head.size < 2) return false
  const pasted = new Set(asked)
  let found = 0
  for (const word of entry.head) if (pasted.has(word)) found += 1
  return found / entry.head.size >= PASTED
}

function apply(): void {
  const asked = askedOf(query.value)
  let count = 0
  for (const group of groups) {
    let any = false
    for (const entry of group.entries) {
      const on = matches(entry, asked)
      if (on) {
        any = true
        count += 1
      }
      for (const node of entry.nodes) node.style.display = on ? '' : 'none'
    }
    for (const node of group.nodes) node.style.display = any ? '' : 'none'
  }
  shown.value = count
}

function restore(): void {
  for (const group of groups) {
    for (const node of group.nodes) node.style.display = ''
    for (const entry of group.entries) for (const node of entry.nodes) node.style.display = ''
  }
}

function tryOne(example: string): void {
  query.value = example
}

onMounted(async () => {
  await nextTick()
  read()
  ready.value = total.value > 0
  if (query.value) apply()
})

onBeforeUnmount(restore)

watch(query, () => {
  if (ready.value) apply()
})
</script>

<template>
  <div ref="root" class="trouble-filter">
    <label class="field">
      <span class="sign" aria-hidden="true">⌕</span>
      <textarea
        v-model="query"
        rows="1"
        spellcheck="false"
        autocomplete="off"
        aria-label="Show only the entries that match a message"
        placeholder="Paste the message, or type part of it"
        :disabled="!ready"
        @keydown.enter.prevent
        @keydown.esc="query = ''"
      />
      <button v-if="query" type="button" class="clear" aria-label="Clear" @click="query = ''">
        ×
      </button>
    </label>
    <p class="status" aria-live="polite">
      <template v-if="!query">
        <span class="try">Try</span>
        <button v-for="one in EXAMPLES" :key="one" type="button" class="example" @click="tryOne(one)">
          {{ one }}
        </button>
      </template>
      <template v-else-if="shown">
        {{ shown }} of {{ total }} entries match. <kbd>esc</kbd> shows them all again.
      </template>
      <template v-else>
        Nothing here matches. Try a shorter piece of the message, or see
        <a href="#still-stuck">Still stuck</a>.
      </template>
    </p>
    <p class="aside">Filters this page as you type. Nothing you paste leaves your browser.</p>
  </div>
</template>

<style scoped>
.trouble-filter {
  margin: 20px 0 28px;
  padding: 14px 16px 12px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
}

.field {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
  transition: border-color 0.2s;
}

.field:focus-within {
  border-color: var(--vp-c-brand-1);
}

.sign {
  font-size: 18px;
  line-height: 24px;
  color: var(--vp-c-text-3);
}

textarea {
  flex: 1;
  min-width: 0;
  min-height: 24px;
  max-height: 120px;
  border: 0;
  outline: none;
  resize: none;
  background: transparent;
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  line-height: 24px;
  color: var(--vp-c-text-1);
  field-sizing: content;
}

textarea::placeholder {
  font-family: var(--vp-font-family-base);
  color: var(--vp-c-text-3);
}

.clear {
  font-size: 20px;
  line-height: 24px;
  color: var(--vp-c-text-3);
}

.clear:hover {
  color: var(--vp-c-text-1);
}

.status {
  margin: 10px 2px 0;
  font-size: 13px;
  line-height: 1.9;
  color: var(--vp-c-text-2);
}

.try {
  margin-right: 4px;
}

.status kbd {
  padding: 0 5px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 4px;
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.4;
}

.example {
  display: inline-block;
  margin: 0 6px 4px 0;
  padding: 1px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--vp-c-brand-1);
  transition: border-color 0.2s;
}

.example:hover {
  border-color: var(--vp-c-brand-1);
}

.status a {
  font-weight: 600;
  color: var(--vp-c-brand-1);
}

.aside {
  margin: 4px 2px 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--vp-c-text-3);
}

@media (prefers-reduced-motion: reduce) {
  .field,
  .example {
    transition: none;
  }
}
</style>
