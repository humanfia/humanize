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
//   n        a numbered callout, `[n]1[/]`: not the interface's, but the page's, pointing at
//            what the numbered list under the screen explains
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
//
// It moves the way the screen would redraw. The first time it is scrolled to, its lines are
// typed on one after another; after that, a step to another frame types on only what differs
// from the frame before, a highlighted row is swept in, a callout pops, the status line's keys
// slide in from the right, and the frame's control is followed by a pill that glides to it.
// Every line is text the whole time -- clipped while it is typed, never removed -- and under
// reduced motion nothing moves at all.
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { motion } from '../../motion/gsap'

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

const NAMES = 'dim|m|g|y|c|r|b|i|B|sel|n'
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
// How many columns some runs take: a callout is drawn as a pill about three columns wide.
function width(said: Run[]): number {
  return said.reduce((sum, run) => sum + (run.cls.includes('t-n') ? 3 : run.text.length), 0)
}

function fitted(left: Run[], keys: string): Run[] {
  const all = keys.split(DOT)
  if (cols.value) {
    const room = cols.value - width(left)
    while (all.length > 1 && width(runs(all.join(DOT))) > room) all.shift()
  }
  return runs(all.join(DOT)).map((run) => ({ text: run.text, cls: run.cls || 't-m' }))
}

type Drawn =
  | { kind: 'text'; runs: Run[]; hl: boolean }
  | { kind: 'row'; left: Run[]; right: Run[]; hl: boolean }
  | { kind: 'rule'; cls: string }
  | { kind: 'prompt'; runs: Run[] }

function draw(lines: Line[]): Drawn[] {
  return lines.map((line): Drawn => {
    if (typeof line === 'string') return { kind: 'text', runs: runs(line), hl: false }
    if ('rule' in line)
      return { kind: 'rule', cls: typeof line.rule === 'string' ? `t-${line.rule}` : '' }
    if ('prompt' in line) return { kind: 'prompt', runs: runs(line.prompt) }
    if ('t' in line) return { kind: 'text', runs: runs(line.t), hl: !!line.hl }
    const left = runs(line.l)
    const right = line.keys ? fitted(left, line.keys) : runs(line.r)
    return { kind: 'row', left, right, hl: !!line.hl }
  })
}

const drawn = computed<Drawn[]>(() => draw(frame.value.lines))

// ---- motion ----------------------------------------------------------------------------------

const root = ref<HTMLElement | null>(null)
const controls = ref<HTMLElement | null>(null)
const inked = ref(false)
let still = true
let playing: gsap.core.Timeline | undefined
let seen: IntersectionObserver | undefined

const say = (one: unknown) => JSON.stringify(one)
const chars = (said: Run[]) => Math.max(1, width(said))

// The pieces of a drawn line that a change can touch, each with what it says, so a step types
// on only what is different.
interface Piece {
  el: HTMLElement
  said: string
  size: number
  how: 'type' | 'slide' | 'rule'
}

function pieces(line: Drawn, el: HTMLElement): Piece[] {
  if (line.kind === 'row') {
    const left = el.querySelector<HTMLElement>('.left')!
    const right = el.querySelector<HTMLElement>('.right')!
    return [
      { el: left, said: say(line.left), size: chars(line.left), how: 'type' },
      { el: right, said: say(line.right), size: chars(line.right), how: 'slide' },
    ]
  }
  if (line.kind === 'rule') return [{ el, said: say(line), size: 40, how: 'rule' }]
  if (line.kind === 'prompt') {
    const words = el.querySelector<HTMLElement>('.said')!
    return [{ el: words, said: say(line.runs), size: chars(line.runs), how: 'type' }]
  }
  return [{ el, said: say(line.runs), size: chars(line.runs), how: 'type' }]
}

// Adds one piece's entrance at `at`; returns when it is done.
function enter(tl: gsap.core.Timeline, one: Piece, at: number): number {
  let took: number
  if (one.how === 'rule') {
    took = 0.55
    tl.fromTo(one.el, { clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)', duration: took, ease: 'cine' }, at)
  } else if (one.how === 'slide') {
    took = 0.5
    tl.fromTo(
      one.el,
      { clipPath: 'inset(0 0 0 100%)', x: 18 },
      { clipPath: 'inset(0 0 0 0%)', x: 0, duration: took, ease: 'cine.out' },
      at,
    )
  } else {
    // Typed: a character at a time, as fast as a screen redraws but slow enough to follow.
    const n = Math.min(one.size, 90)
    took = Math.min(0.75, 0.14 + n * 0.009)
    tl.fromTo(
      one.el,
      { clipPath: 'inset(0 100% 0 0)' },
      { clipPath: 'inset(0 0% 0 0)', duration: took, ease: `steps(${Math.max(4, n)})` },
      at,
    )
  }
  // A callout pops as the typing reaches it, and rings once.
  const box = one.el.getBoundingClientRect()
  one.el.querySelectorAll<HTMLElement>('.t-n').forEach((pill) => {
    const r = pill.getBoundingClientRect()
    const along = box.width > 0 ? Math.min(1, Math.max(0, (r.left - box.left) / box.width)) : 1
    const when = at + took * along
    tl.fromTo(pill, { scale: 0.2, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.5, ease: 'back.out(2.6)' }, when)
    tl.fromTo(pill, { '--ring': 0 }, { '--ring': 1, duration: 0.8, ease: 'power2.out' }, when + 0.12)
  })
  return at + took
}

// A highlighted row is swept in from the left, and a glint crosses it.
function sweep(tl: gsap.core.Timeline, el: HTMLElement, at: number) {
  tl.fromTo(el, { '--sweep': 0 }, { '--sweep': 1, duration: 0.6, ease: 'cine.out' }, at)
  tl.fromTo(el, { '--glint': -0.6 }, { '--glint': 1.6, duration: 1.1, ease: 'cine' }, at + 0.15)
}

function lineEls(): HTMLElement[] {
  return Array.from(root.value?.querySelectorAll<HTMLElement>('.screen > [data-i]') ?? [])
}

function finish() {
  if (!playing) return
  playing.progress(1)
  playing.kill()
  playing = undefined
}

// The first look: every line typed on in turn.
function intro() {
  if (still) return
  const gsap = motion()
  finish()
  const tl = gsap.timeline({ onComplete: () => clear(tl) })
  let at = 0.05
  lineEls().forEach((el, n) => {
    const line = drawn.value[n]
    if (!line) return
    let end = at
    for (const one of pieces(line, el)) end = Math.max(end, enter(tl, one, at))
    if ('hl' in line && line.hl) sweep(tl, el, at)
    at += Math.min(0.16, Math.max(0.05, (end - at) * 0.45))
  })
  playing = tl
}

// Leaves no clip behind once a timeline is done, so selection and find-in-page see plain text.
function clear(tl: gsap.core.Timeline) {
  for (const target of tl.getChildren(true, true, false).flatMap((t) => (t as gsap.core.Tween).targets())) {
    if (target instanceof HTMLElement) target.style.removeProperty('clip-path')
  }
}

function changed(before: Drawn[]) {
  const gsap = motion()
  finish()
  if (still) return
  const tl = gsap.timeline({ onComplete: () => clear(tl) })
  const els = lineEls()
  // What the frame before said, piece by piece, wherever it was: a line that only moved down
  // because one was put above it is not new.
  const key = (line: Drawn, k: number, said: string) => `${line.kind}:${k}:${said}`
  const had = new Map<string, number>()
  const lit = new Set<string>()
  for (const was of before) {
    const sigs = was.kind === 'row' ? [say(was.left), say(was.right)] : [say(was.kind === 'rule' ? was : was.runs)]
    sigs.forEach((said, k) => had.set(key(was, k, said), (had.get(key(was, k, said)) ?? 0) + 1))
    if ('hl' in was && was.hl) lit.add(say(was))
  }
  const work: { el: HTMLElement; fresh: Piece[]; swept: boolean }[] = []
  drawn.value.forEach((line, n) => {
    const el = els[n]
    if (!el) return
    const fresh = pieces(line, el).filter((one, k) => {
      const count = had.get(key(line, k, one.said)) ?? 0
      if (count) had.set(key(line, k, one.said), count - 1)
      return !count
    })
    const swept = 'hl' in line && !!line.hl && (fresh.length > 0 || !lit.has(say(line)))
    if (fresh.length || swept) work.push({ el, fresh, swept })
  })
  // However much changed, it is all on within about a second.
  const gap = Math.min(0.08, 0.6 / Math.max(1, work.length))
  work.forEach(({ el, fresh, swept }, n) => {
    for (const one of fresh) enter(tl, one, n * gap)
    if (swept) sweep(tl, el, n * gap)
  })
  // The caption under the screen rises in with the frame.
  const caption = root.value?.querySelector('.caption')
  if (caption) tl.fromTo(caption, { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5 }, 0.1)
  // A band of light runs down the screen once, as a redraw would.
  const band = root.value?.querySelector('.redraw')
  if (band) tl.fromTo(band, { top: '-30%', opacity: 1 }, { top: '100%', opacity: 0.2, duration: 0.7, ease: 'cine' }, 0)
  playing = tl
}

// The pill under the frame's control, glided to the one that is on.
function ink(now = false) {
  const box = controls.value
  const pill = box?.querySelector<HTMLElement>('.ink')
  const on = box?.querySelector<HTMLElement>('.pick.on')
  if (!box || !pill || !on) return
  motion().to(pill, {
    x: on.offsetLeft,
    y: on.offsetTop,
    width: on.offsetWidth,
    height: on.offsetHeight,
    autoAlpha: 1,
    duration: now || still ? 0 : 0.5,
    ease: 'cine',
  })
}

// Keys stepping through: the label slides in from the side the step went.
function stepped(by: number) {
  if (still) return
  const where = root.value?.querySelector('.where')
  if (where) motion().fromTo(where, { opacity: 0, x: 10 * by }, { opacity: 1, x: 0, duration: 0.45 })
}

watch(at, async (now, then) => {
  const before = draw(props.frames[Math.min(then, props.frames.length - 1)].lines)
  await nextTick()
  changed(before)
  ink()
  if (props.keys.length === 2) stepped(now === (then + 1) % props.frames.length ? 1 : -1)
})

onMounted(() => {
  still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  void nextTick(() => {
    inked.value = true
    void nextTick(() => ink(true))
  })
  if (still || !root.value) return
  // Typed on only if it has not been seen yet: one already on screen stays as it was drawn.
  if (root.value.getBoundingClientRect().top < window.innerHeight) return
  const gsap = motion()
  gsap.set(lineEls(), { clipPath: 'inset(0 100% 0 0)' })
  seen = new IntersectionObserver(
    ([entry]) => {
      if (!entry.isIntersecting) return
      seen?.disconnect()
      gsap.set(lineEls(), { clearProps: 'clipPath' })
      intro()
    },
    { threshold: 0.3 },
  )
  seen.observe(root.value)
})

onUnmounted(() => {
  seen?.disconnect()
  playing?.kill()
})

watch(cols, () => ink(true))
</script>

<template>
  <figure ref="root" class="term hmz-panel">
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
    <div v-else-if="frames.length > 1" ref="controls" class="controls" :class="{ inked }" role="group">
      <span class="ink" aria-hidden="true" />
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
      <span class="redraw" aria-hidden="true" />
      <template v-for="(line, n) in drawn" :key="`${at}-${n}`">
        <div v-if="line.kind === 'rule'" class="rule" :class="line.cls" :data-i="n" />
        <div v-else-if="line.kind === 'prompt'" class="line" :data-i="n">
          <span class="t-m">❯ </span
          ><span class="said"
            ><span v-for="(run, k) in line.runs" :key="k" :class="run.cls">{{ run.text }}</span></span
          ><span class="caret" aria-hidden="true"> </span>
        </div>
        <div v-else-if="line.kind === 'row'" class="row" :class="{ hl: line.hl }" :data-i="n">
          <span class="left"
            ><span v-for="(run, k) in line.left" :key="k" :class="run.cls">{{ run.text }}</span></span
          >
          <span class="right"
            ><span v-for="(run, k) in line.right" :key="k" :class="run.cls">{{ run.text }}</span></span
          >
        </div>
        <div v-else class="line" :class="{ hl: line.hl }" :data-i="n">
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
  box-shadow: inset 0 -1px 1px color-mix(in srgb, var(--vp-c-text-1) 14%, transparent);
}

.dots i:nth-child(1) {
  background: color-mix(in srgb, var(--hmz-lane-5) 70%, var(--vp-c-default-3));
}

.dots i:nth-child(2) {
  background: color-mix(in srgb, var(--hmz-warm) 70%, var(--vp-c-default-3));
}

.dots i:nth-child(3) {
  background: color-mix(in srgb, var(--hmz-accent) 70%, var(--vp-c-default-3));
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
  position: relative;
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

/* Once mounted, the pill under the frame that is on is one piece that glides between them. */
.pick {
  position: relative;
  z-index: 1;
}

.ink {
  position: absolute;
  top: 0;
  left: 0;
  width: 0;
  height: 0;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  box-shadow: 0 0 14px -4px var(--vp-c-brand-1);
  visibility: hidden;
  pointer-events: none;
}

.inked .pick.on {
  border-color: transparent;
  background: transparent;
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
  display: inline-block;
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
  /* A faint glow from the top and the scanlines of a screen, in the theme's own ink. */
  background:
    radial-gradient(120% 80% at 50% -20%, color-mix(in srgb, var(--hmz-accent) 8%, transparent), transparent 62%),
    repeating-linear-gradient(to bottom, color-mix(in srgb, var(--vp-c-text-1) 3%, transparent) 0 1px, transparent 1px 3px),
    var(--vp-code-block-bg);
  color: var(--t-fg);
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.screen {
  position: relative;
  overflow: hidden;
}

/* The band a redraw runs down the screen; and, slowly, all the time, a fainter one. */
.redraw,
.screen::after {
  position: absolute;
  left: 0;
  right: 0;
  top: -30%;
  height: 30%;
  min-height: 40px;
  background: linear-gradient(to bottom, transparent, color-mix(in srgb, var(--hmz-accent) 9%, transparent), transparent);
  pointer-events: none;
  opacity: 0;
}

.screen::after {
  content: '';
  opacity: 0.5;
  animation: raster 9s linear infinite;
}

@keyframes raster {
  from {
    top: -30%;
  }
  to {
    top: 100%;
  }
}

.said {
  display: inline-block;
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
  --sweep: 1;
  --glint: 2;
  position: relative;
  isolation: isolate;
  overflow: hidden;
  margin: 0 -6px;
  padding: 0 6px;
  border-radius: 4px;
}

/* The highlight, swept in from the left, and a glint that crosses it once. */
.hl::before,
.hl::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
}

.hl::before {
  background: var(--vp-c-brand-soft);
  box-shadow: inset 2px 0 0 var(--vp-c-brand-1);
  transform: scaleX(var(--sweep));
  transform-origin: left;
}

.hl::after {
  width: 35%;
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--vp-c-brand-1) 22%, transparent), transparent);
  transform: translateX(calc(var(--glint) * 300%));
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
  animation: blink 1.1s steps(1) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
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

/* A numbered callout: drawn over the screen by the page, not by the interface. */
.t-n {
  --ring: 1;
  position: relative;
  display: inline-block;
  min-width: 1.45em;
  margin: 0 0.3em;
  padding: 0 0.3em;
  border-radius: 999px;
  background: var(--vp-c-brand-1);
  color: var(--vp-c-white);
  font-family: var(--vp-font-family-base);
  font-size: max(11px, 0.78em);
  font-weight: 700;
  font-style: normal;
  line-height: 1.45em;
  text-align: center;
  vertical-align: 0.08em;
  white-space: nowrap;
}

/* The ring a callout sends out as it pops. */
.t-n::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 2px solid var(--vp-c-brand-1);
  border-radius: inherit;
  opacity: calc(1 - var(--ring));
  transform: scale(calc(1 + var(--ring) * 0.9));
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .screen::after,
  .caret {
    animation: none;
  }

  .screen::after {
    opacity: 0;
  }
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
