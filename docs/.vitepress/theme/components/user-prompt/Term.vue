<script setup lang="ts">
// A terminal screen drawn by hand, for the "at the prompt" pages. The recorded screens are
// the GIFs under /demo/; this one is a drawing, and says so in its corner.
//
// What goes in the slot is a <pre>, with a few span classes for the colours the interface
// uses: `d` dim, `m` muted, `p` the purple of a highlighted row, `a` the teal of the status
// dot, `r` an error, `y` a warning, `b` bold, `hl` a highlighted row -- and `n`, a numbered
// callout the page draws over the screen for the list under it to explain.
//
// The first time it is scrolled to, the screen is typed on: its rows one after another, each
// a character at a time behind a caret, a selected row's bar swept in ahead of its words, and
// a callout popping as the typing reaches it. The words are in the page from the start and
// only clipped while they are typed, so a screen reader or a search reads them all; one
// already on screen when the page opens, and every one under reduced motion, is left as drawn.
import { onMounted, onUnmounted, ref } from 'vue'

import { motion } from '../../motion/gsap'

withDefaults(defineProps<{ title?: string; tag?: string }>(), {
  title: 'hmz',
  tag: 'drawn, not recorded',
})

const root = ref<HTMLElement | null>(null)
const screen = ref<HTMLElement | null>(null)
const caret = ref<HTMLElement | null>(null)
let seen: IntersectionObserver | undefined
let playing: gsap.core.Timeline | undefined

const SPEED = 240 // characters a second
const GAP = 0.07 // seconds between one row starting and the next

interface Row {
  from: number // the first character that is not indentation
  to: number // past the last that is not trailing space
  start: number
  took: number
}

function hide(pre: HTMLElement) {
  pre.style.clipPath = 'polygon(0 0, 0 0, 0 0)'
}

function play(pre: HTMLElement) {
  const gsap = motion()
  const lines = (pre.textContent ?? '').split('\n')
  if (lines.length && !lines[lines.length - 1].trim()) lines.pop()
  const style = getComputedStyle(pre)
  const lh = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.6
  // A character's width, from a probe set in the same font.
  const probe = document.createElement('span')
  probe.textContent = '0'.repeat(20)
  probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre'
  pre.appendChild(probe)
  const ch = probe.getBoundingClientRect().width / 20 || 8
  probe.remove()
  const wide = pre.scrollWidth + 40

  let t = 0.15
  const rows: Row[] = lines.map((line) => {
    const from = line.length - line.trimStart().length
    const to = line.trimEnd().length
    const took = to > from ? Math.max(0.1, (to - from) / SPEED) : 0
    const row = { from, to, start: t, took }
    if (took) t += GAP
    return row
  })
  const end = Math.max(...rows.map((r) => r.start + r.took), 0.2)

  // How far along row `i` is typed at time `at`, in pixels: all of it once it is done.
  const reach = (row: Row, at: number) => {
    if (at <= row.start) return 0
    if (!row.took || at >= row.start + row.took) return wide
    const typed = Math.floor(row.from + ((at - row.start) / row.took) * (row.to - row.from))
    return typed * ch
  }

  const head = caret.value
  const clock = { at: 0 }
  const draw = () => {
    const pts: string[] = ['0 0']
    let live = -1
    rows.forEach((row, i) => {
      const x = reach(row, clock.at)
      pts.push(`${x}px ${i * lh}px`, `${x}px ${(i + 1) * lh}px`)
      if (x > 0 && x < wide) live = i
    })
    pts.push(`0 ${rows.length * lh}px`)
    pre.style.clipPath = `polygon(${pts.join(', ')})`
    if (head) {
      if (live < 0) head.style.opacity = '0'
      else {
        head.style.opacity = '1'
        head.style.transform = `translate(${pre.offsetLeft + reach(rows[live], clock.at)}px, ${pre.offsetTop + live * lh}px)`
        head.style.height = `${lh}px`
        head.style.width = `${ch}px`
      }
    }
  }

  const tl = gsap.timeline({
    onComplete: () => {
      pre.style.removeProperty('clip-path')
      if (head) head.style.opacity = '0'
    },
  })
  draw()
  tl.to(clock, { at: end, duration: end, ease: 'none', onUpdate: draw }, 0)

  // Where a span sits: its row, and how far along it it is.
  const place = (el: HTMLElement) => {
    const box = pre.getBoundingClientRect()
    const r = el.getBoundingClientRect()
    const i = Math.max(0, Math.min(rows.length - 1, Math.floor((r.top - box.top + lh / 2) / lh)))
    const row = rows[i]
    const col = (r.left - box.left) / ch
    const along = row.to > row.from ? Math.min(1, Math.max(0, (col - row.from) / (row.to - row.from))) : 0
    return { row, along }
  }

  // A selected or highlighted row: its bar runs ahead of the typing.
  pre.querySelectorAll<HTMLElement>('.sel, .hl, .btn').forEach((el) => {
    const { row, along } = place(el)
    tl.fromTo(
      el,
      { backgroundSize: '0% 100%' },
      { backgroundSize: '100% 100%', duration: Math.max(0.25, row.took * 0.7), ease: 'cine.out' },
      row.start + row.took * along * 0.6,
    )
  })

  // A callout pops as the typing reaches it, and rings once.
  pre.querySelectorAll<HTMLElement>('.n').forEach((el) => {
    const { row, along } = place(el)
    const when = row.start + row.took * along
    tl.fromTo(el, { scale: 0.2, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.5, ease: 'back.out(2.6)' }, when)
    tl.fromTo(el, { '--ring': 0 }, { '--ring': 1, duration: 0.8, ease: 'power2.out' }, when + 0.12)
  })

  // The hairline under the title bar is drawn across as the screen comes on.
  const line = root.value?.querySelector('.wire')
  if (line) tl.fromTo(line, { scaleX: 0 }, { scaleX: 1, duration: Math.min(1.4, end), ease: 'cine' }, 0)

  playing = tl
}

onMounted(() => {
  const pre = screen.value?.querySelector('pre')
  if (!pre || !root.value) return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  // Already in view as the page opens: left as it was drawn, rather than blinked out and in.
  if (root.value.getBoundingClientRect().top < window.innerHeight) return
  hide(pre)
  seen = new IntersectionObserver(
    ([entry]) => {
      if (!entry.isIntersecting) return
      seen?.disconnect()
      play(pre)
    },
    { threshold: 0.25 },
  )
  seen.observe(root.value)
})

onUnmounted(() => {
  seen?.disconnect()
  playing?.kill()
})
</script>

<template>
  <figure ref="root" class="up-term">
    <figcaption>
      <span class="dots" aria-hidden="true"><i /><i /><i /></span>
      <span class="title">{{ title }}</span>
      <span class="tag">{{ tag }}</span>
      <span class="wire" aria-hidden="true" />
    </figcaption>
    <div ref="screen" class="screen">
      <span ref="caret" class="head" aria-hidden="true" />
      <slot />
    </div>
  </figure>
</template>

<style scoped>
.up-term {
  margin: 20px 0 26px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-code-block-bg);
  overflow: hidden;
  box-shadow:
    inset 0 1px 0 color-mix(in srgb, var(--vp-c-white) 6%, transparent),
    0 14px 34px -26px color-mix(in srgb, var(--hmz-accent-2) 70%, transparent);
}

figcaption {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: linear-gradient(to bottom, var(--vp-c-bg-soft), transparent);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

/* A hairline in the guide's two accents along the foot of the title bar. */
.wire {
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--hmz-accent) 25%, var(--hmz-accent-2) 75%, transparent);
  opacity: 0.55;
  transform-origin: left;
}

.dots {
  display: inline-flex;
  gap: 5px;
}

.dots i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--vp-c-divider);
  box-shadow: inset 0 -1px 1px color-mix(in srgb, var(--vp-c-text-1) 14%, transparent);
}

.dots i:nth-child(1) {
  background: color-mix(in srgb, var(--hmz-lane-5) 65%, var(--vp-c-divider));
}

.dots i:nth-child(2) {
  background: color-mix(in srgb, var(--hmz-warm) 65%, var(--vp-c-divider));
}

.dots i:nth-child(3) {
  background: color-mix(in srgb, var(--hmz-accent) 65%, var(--vp-c-divider));
}

.title {
  color: var(--vp-c-text-2);
}

.tag {
  margin-left: auto;
  font-style: italic;
}

.screen {
  position: relative;
  overflow-x: auto;
  padding: 12px 16px;
  /* A glow from the top and a screen's scanlines, in the theme's own ink. */
  background:
    radial-gradient(120% 80% at 50% -20%, color-mix(in srgb, var(--hmz-accent) 7%, transparent), transparent 62%),
    repeating-linear-gradient(to bottom, color-mix(in srgb, var(--vp-c-text-1) 3%, transparent) 0 1px, transparent 1px 3px);
}

/* The caret the typing is done behind. */
.head {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
  width: 0.62em;
  background: var(--hmz-accent);
  box-shadow: 0 0 10px color-mix(in srgb, var(--hmz-accent) 70%, transparent);
  font-size: 13px;
  opacity: 0;
  pointer-events: none;
}

.screen :slotted(pre) {
  margin: 0;
  padding: 0;
  background: none;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
  white-space: pre;
}

.screen :slotted(.d) {
  color: var(--vp-c-text-3);
}

.screen :slotted(.m) {
  color: var(--vp-c-text-2);
}

.screen :slotted(.p) {
  color: var(--hmz-accent-2);
}

.screen :slotted(.a) {
  color: var(--hmz-accent);
}

.screen :slotted(.r) {
  color: var(--vp-c-danger-1);
}

.screen :slotted(.y) {
  color: var(--vp-c-warning-1);
}

.screen :slotted(.b) {
  font-weight: 700;
}

/* The bars below are painted as an image, so the typing can sweep them in from the left. */
.screen :slotted(.hl) {
  background: linear-gradient(var(--vp-c-default-soft), var(--vp-c-default-soft)) no-repeat 0 0 / 100% 100%;
}

.screen :slotted(.g) {
  color: var(--vp-c-success-1);
}

/* The row under the cursor on a list that has the focus, as the terminal's own blue. */
.screen :slotted(.sel) {
  background: linear-gradient(var(--hmz-accent-2), var(--hmz-accent-2)) no-repeat 0 0 / 100% 100%;
  color: var(--vp-c-white);
}

/* A numbered callout: the page's, not the interface's. */
.screen :slotted(.n) {
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
  line-height: 1.45em;
  text-align: center;
  vertical-align: 0.08em;
}

/* The ring a callout sends out as it pops. */
.screen :slotted(.n)::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 2px solid var(--vp-c-brand-1);
  border-radius: inherit;
  opacity: calc(1 - var(--ring));
  transform: scale(calc(1 + var(--ring) * 0.9));
  pointer-events: none;
}

/* A button under a list of `/settings`. */
.screen :slotted(.btn) {
  background: linear-gradient(var(--vp-c-default-soft), var(--vp-c-default-soft)) no-repeat 0 0 / 100% 100%;
}

@media (max-width: 640px) {
  .screen {
    padding: 10px 12px;
  }

  .screen :slotted(pre) {
    font-size: 11.5px;
  }
}
</style>
