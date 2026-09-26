<script setup lang="ts">
// A drawing of the `hmz` screen, one moment or a few of them. The words and the marks are the
// interface's own -- `src/hmz/tui/app.py` and `pick.py` -- and the colours are the sixteen a
// terminal has, as the interface draws in nothing else. Several frames get a control each, or
// a pair of keys to step through them, so a page can show what a keypress changes.
//
// A line is written the way the interface writes its own, in a small subset of Rich markup:
// `[g]●[/] text`, with these styles, which may be combined as `[dim i]…[/]`:
//
//   dim m    the grey the interface says quiet things in
//   g y c r b    green, yellow, cyan, red, blue
//   i B      italic, bold
//   sel      the cursor's highlight
//
// A line is a string, or one of:
//   { t: '…', hl: true }        a string, highlighted as what changed
//   { l: '…', r: '…', hl? }     two ends of one row pushed apart: the pin beside what runs
//   { l: '…', keys: 'a · b' }   the status line: what runs, and the keys that work right now.
//                               Where the row is too narrow for all of them the keys at the
//                               front go first, as the interface drops them (`_draw`)
//   { rule: true }              the rule across, above and below the editor; `rule: 'b'`
//                               for the blue one a sheet opens with
//   { prompt: '…' }             the editor, with the caret
import { computed, onMounted, onUnmounted, ref } from 'vue'

type Line =
  | string
  | { t: string; hl?: boolean }
  | { l?: string; r?: string; keys?: string; hl?: boolean }
  | { rule: true | string }
  | { prompt: string }

interface Frame {
  label: string
  lines: Line[]
  caption?: string
  // This frame alone as box drawings, or not, whatever the screen says.
  art?: boolean
}

const props = withDefaults(
  defineProps<{
    frames: Frame[]
    // A pair of keys that step back and forward through the frames, in place of a control
    // per frame: `['shift+tab', 'tab']`. For a screen that a key walks round.
    keys?: string[]
    // Box drawings: kept on one line each and scrolled rather than wrapped.
    art?: boolean
    title?: string
  }>(),
  { keys: () => [], art: false, title: 'hmz' },
)

const at = ref(0)
const frame = computed(() => props.frames[Math.min(at.value, props.frames.length - 1)])

function step(by: number) {
  const n = props.frames.length
  at.value = (at.value + by + n) % n
}

const NAMES = 'dim|m|g|y|c|r|b|i|B|sel'
const MARKUP = new RegExp(`\\[((?:${NAMES})(?: (?:${NAMES}))*)\\]([\\s\\S]*?)\\[/\\]`, 'g')

interface Run {
  text: string
  cls: string
}

function runs(said: string | undefined): Run[] {
  if (!said) return []
  const out: Run[] = []
  let from = 0
  for (const found of said.matchAll(MARKUP)) {
    const start = found.index ?? 0
    if (start > from) out.push({ text: said.slice(from, start), cls: '' })
    out.push({
      text: found[2],
      cls: found[1]
        .split(' ')
        .map((one) => `t-${one}`)
        .join(' '),
    })
    from = start + found[0].length
  }
  if (from < said.length) out.push({ text: said.slice(from), cls: '' })
  return out
}

// How many columns the screen is, once it has been measured: none at all before that, which is
// every key shown and the row left to wrap.
const screen = ref<HTMLElement | null>(null)
const probe = ref<HTMLElement | null>(null)
const cols = ref(0)
let watching: ResizeObserver | undefined

function measure() {
  const el = screen.value
  const one = probe.value
  if (!el || !one) return
  const each = one.getBoundingClientRect().width / 10
  const style = getComputedStyle(el)
  const inner = el.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
  cols.value = each > 0 ? Math.floor(inner / each) : 0
}

onMounted(() => {
  measure()
  document.fonts?.ready.then(measure)
  watching = new ResizeObserver(measure)
  if (screen.value) watching.observe(screen.value)
})

onUnmounted(() => watching?.disconnect())

const DOT = ' · '

// The keys a row of this width has room for, dropped from the front as `_draw` drops them: the
// ones there mean the same thing whenever they are pressed, and the last ones are what changes.
// `_draw` gives them the terminal's width less its 2-column padding each side, less what is on
// the left; the screen's own padding stands in for that padding here, so what is left over is
// the measured columns less the left.
function fitted(left: Run[], keys: string): Run[] {
  const all = keys.split(DOT)
  if (cols.value) {
    const room = cols.value - left.reduce((sum, run) => sum + run.text.length, 0)
    while (all.length > 1 && all.join(DOT).length > room) all.shift()
  }
  return [{ text: all.join(DOT), cls: 't-m' }]
}

type Drawn =
  | { kind: 'text'; runs: Run[]; hl: boolean }
  | { kind: 'row'; left: Run[]; right: Run[]; hl: boolean }
  | { kind: 'rule'; cls: string }
  | { kind: 'prompt'; runs: Run[] }

const drawn = computed<Drawn[]>(() =>
  frame.value.lines.map((line): Drawn => {
    if (typeof line === 'string') return { kind: 'text', runs: runs(line), hl: false }
    if ('rule' in line)
      return { kind: 'rule', cls: typeof line.rule === 'string' ? `t-${line.rule}` : '' }
    if ('prompt' in line) return { kind: 'prompt', runs: runs(line.prompt) }
    if ('t' in line) return { kind: 'text', runs: runs(line.t), hl: !!line.hl }
    const left = runs(line.l)
    const right = line.keys ? fitted(left, line.keys) : runs(line.r)
    return { kind: 'row', left, right, hl: !!line.hl }
  }),
)
</script>

<template>
  <figure class="term hmz-panel">
    <figcaption class="bar">
      <span class="dots" aria-hidden="true"><i /><i /><i /></span>
      <span class="title">{{ title }}</span>
      <span class="drawn">drawn, not recorded</span>
    </figcaption>

    <div v-if="frames.length > 1 && keys.length === 2" class="controls">
      <span class="press">press</span>
      <button type="button" class="key" :aria-label="`press ${keys[0]}`" @click="step(-1)">
        ‹ <kbd>{{ keys[0] }}</kbd>
      </button>
      <button type="button" class="key" :aria-label="`press ${keys[1]}`" @click="step(1)">
        <kbd>{{ keys[1] }}</kbd> ›
      </button>
      <span class="where" aria-live="polite">{{ frame.label }}</span>
    </div>
    <div v-else-if="frames.length > 1" class="controls" role="group">
      <button
        v-for="(one, n) in frames"
        :key="one.label"
        type="button"
        class="pick"
        :class="{ on: n === at }"
        :aria-pressed="n === at"
        @click="at = n"
      >
        {{ one.label }}
      </button>
    </div>

    <div ref="screen" class="screen" :class="{ art: frame.art ?? art }">
      <span ref="probe" class="probe" aria-hidden="true">0000000000</span>
      <template v-for="(line, n) in drawn" :key="`${at}-${n}`">
        <div v-if="line.kind === 'rule'" class="rule" :class="line.cls" />
        <div v-else-if="line.kind === 'prompt'" class="line">
          <span class="t-m">❯ </span
          ><span v-for="(run, k) in line.runs" :key="k" :class="run.cls">{{ run.text }}</span
          ><span class="caret" aria-hidden="true"> </span>
        </div>
        <div v-else-if="line.kind === 'row'" class="row" :class="{ hl: line.hl }">
          <span class="left"
            ><span v-for="(run, k) in line.left" :key="k" :class="run.cls">{{ run.text }}</span></span
          >
          <span class="right"
            ><span v-for="(run, k) in line.right" :key="k" :class="run.cls">{{ run.text }}</span></span
          >
        </div>
        <div v-else class="line" :class="{ hl: line.hl }">
          <span v-for="(run, k) in line.runs" :key="k" :class="run.cls">{{ run.text }}</span>
        </div>
      </template>
    </div>

    <p v-if="frame.caption" class="caption" v-html="frame.caption" />
  </figure>
</template>

<style scoped>
.term {
  --t-fg: var(--vp-c-text-1);
  --t-dim: var(--vp-c-text-2);
  --t-g: #1a7f37;
  --t-y: #9a6700;
  --t-c: #0e7490;
  --t-r: #cf222e;
  --t-b: #0969da;
  margin: 20px 0 28px;
}

:global(.dark) .term {
  --t-g: #56d364;
  --t-y: #e3b341;
  --t-c: #39c5cf;
  --t-r: #ff7b72;
  --t-b: #79c0ff;
}

.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  font-size: 12px;
  color: var(--vp-c-text-2);
}

.dots {
  display: inline-flex;
  gap: 5px;
}

.dots i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--vp-c-default-3);
}

.title {
  font-family: var(--vp-font-family-mono);
  font-weight: 600;
}

.drawn {
  margin-left: auto;
  font-size: 11px;
  color: var(--vp-c-text-3);
  white-space: nowrap;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.pick {
  padding: 3px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12.5px;
  cursor: pointer;
  transition:
    color 0.15s,
    border-color 0.15s,
    background 0.15s;
}

.pick:hover {
  color: var(--vp-c-text-1);
  border-color: var(--vp-c-brand-2);
}

.pick.on {
  color: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  font-weight: 600;
}

.press {
  font-size: 12.5px;
  color: var(--vp-c-text-3);
}

.key {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 8px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 13px;
  cursor: pointer;
  transition:
    background 0.15s,
    transform 0.1s;
}

.key:hover {
  background: var(--vp-c-bg-soft);
}

.key:active {
  transform: translateY(1px);
}

.key kbd {
  padding: 0 6px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 4px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
  cursor: pointer;
}

.where {
  margin-left: auto;
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

@media (prefers-reduced-motion: reduce) {
  .key,
  .pick {
    transition: none;
  }

  .key:active {
    transform: none;
  }
}

.screen {
  padding: 12px 16px 14px;
  background: var(--vp-code-block-bg);
  color: var(--t-fg);
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.screen {
  position: relative;
}

.probe {
  position: absolute;
  visibility: hidden;
  white-space: pre;
  pointer-events: none;
}

.screen.art {
  font-size: 12.5px;
  line-height: 1.2;
  white-space: pre;
  overflow-wrap: normal;
  overflow-x: auto;
}

.screen.art .line,
.screen.art .row,
.screen.art .rule {
  min-height: 1.2em;
}

.screen.art .rule {
  height: 1.2em;
}

.line,
.row {
  min-height: 1.55em;
}

.row {
  display: flex;
  flex-wrap: wrap;
  column-gap: 2ch;
}

.row .right {
  margin-left: auto;
  text-align: right;
}

.hl {
  margin: 0 -6px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--vp-c-brand-soft);
}

.rule {
  height: 1.55em;
  color: var(--t-dim);
  background: linear-gradient(currentColor, currentColor) center / 100% 1px no-repeat;
  opacity: 0.6;
}

.rule.t-b {
  color: var(--t-b);
  opacity: 1;
}

.caret {
  display: inline-block;
  width: 0.6em;
  height: 1.15em;
  vertical-align: -0.22em;
  background: var(--t-fg);
  opacity: 0.55;
}

.t-dim,
.t-m {
  color: var(--t-dim);
}

.t-g {
  color: var(--t-g);
}

.t-y {
  color: var(--t-y);
}

.t-c {
  color: var(--t-c);
}

.t-r {
  color: var(--t-r);
}

.t-b {
  color: var(--t-b);
}

.t-i {
  font-style: italic;
}

.t-B {
  font-weight: 700;
}

.t-sel {
  background: var(--t-b);
  color: #fff;
  font-weight: 700;
}

.caption {
  margin: 0;
  padding: 9px 16px 11px;
  border-top: 1px solid var(--hmz-panel-border);
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

@media (max-width: 640px) {
  .screen {
    padding: 10px 12px 12px;
    font-size: 11.5px;
  }
}
</style>
