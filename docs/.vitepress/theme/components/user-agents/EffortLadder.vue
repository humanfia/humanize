<script setup lang="ts">
// Pick a backend, see its effort ladder, and check a word against it the way `hmz exec -a`
// does. The ladders are the `efforts` of each profile in `src/hmz/coganchor/backends.py`,
// hardest first; the check is `Profile.takes` there (`auto` and nothing pass everywhere, a
// `swarm` prefix comes off on Kimi only, an added ACP CLI takes any word) and the refusal is
// `AgentBase._thinks` in `src/hmz/coganchor/agents/base.py`, as `hmz exec` prints it.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { motion } from '../../motion/gsap'

interface Backend {
  cli: string
  called: string
  ladder: string[]
  // What a rung means, where the word alone would mislead.
  marks?: Record<string, string>
  swarms?: boolean
  acp?: boolean
  note: string
}

const VARIANTS = ['xhigh', 'high', 'medium', 'low', 'minimal']

const BACKENDS: Backend[] = [
  {
    cli: 'claude',
    called: 'Claude Code',
    ladder: ['ultracode', 'max', 'xhigh', 'high', 'medium', 'low'],
    marks: { ultracode: 'xhigh, free to run a fleet of its own' },
    note: 'Claude Code never lists ultracode itself; humanize offers it anyway.',
  },
  {
    cli: 'codex',
    called: 'Codex',
    ladder: ['ultra', 'max', 'xhigh', 'high', 'medium', 'low'],
    note: 'Each model takes its own subset, and the agent sheet offers only those.',
  },
  {
    cli: 'cursor-agent',
    called: 'Cursor Agent',
    ladder: ['max', 'xhigh', 'extra-high', 'high', 'medium', 'low', 'minimal', 'none'],
    marks: { 'extra-high': 'one model’s spelling of xhigh', none: 'no thinking at all' },
    note: 'The effort becomes part of the model id, so a model has the rungs your account lists for it. composer-2.5 has none: give it auto.',
  },
  {
    cli: 'dsh',
    called: 'DeepSeek Harness',
    ladder: ['max', 'high', 'low', 'off'],
    marks: { off: 'no reasoning at all' },
    note: 'off is a rung: the model is asked not to reason. auto sends nothing.',
  },
  {
    cli: 'grok',
    called: 'Grok Build',
    ladder: ['xhigh', 'high', 'medium', 'low'],
    note: 'Its ladder stops at xhigh: there is no max.',
  },
  {
    cli: 'kimi',
    called: 'Kimi Code',
    ladder: ['max', 'high', 'medium', 'low'],
    swarms: true,
    note: 'Swarm mode runs the same effort as a fleet of subagents: swarmmax is max, run wide.',
  },
  {
    cli: 'mcode',
    called: 'MiniMax Code',
    ladder: ['max', 'xhigh', 'high', 'medium', 'low'],
    note: 'Only MiniMax-M3.1-Flash-Preview takes a rung. Its other models, and any model added to it, take none: give them auto.',
  },
  {
    cli: 'mimo',
    called: 'MiMo Code',
    ladder: VARIANTS,
    note: 'The effort picks the model’s variant. A provider with no variants takes it and ignores it.',
  },
  {
    cli: 'omp',
    called: 'Oh My Pi',
    ladder: ['max', 'xhigh', 'high', 'medium', 'low', 'minimal', 'off'],
    marks: { off: 'no thinking at all' },
    note: 'Each model takes the rungs omp lists for it, and off, which asks it not to think. A model that does not think takes none: give it auto.',
  },
  {
    cli: 'opencode',
    called: 'opencode',
    ladder: VARIANTS,
    note: 'The effort picks the model’s variant. A provider with no variants takes it and ignores it.',
  },
  {
    cli: 'pi',
    called: 'pi',
    ladder: ['max', 'xhigh', 'high', 'medium', 'low', 'minimal', 'off'],
    marks: { off: 'no thinking at all' },
    note: 'off is a rung: the model is asked not to think. auto sends nothing.',
  },
  {
    cli: 'qwen',
    called: 'Qwen Code',
    ladder: ['max', 'xhigh', 'high', 'medium', 'low', 'none'],
    marks: { none: 'no reasoning at all' },
    note: 'none is a rung, and the one a model with no reasoning setting runs at.',
  },
  {
    cli: 'agy',
    called: 'Antigravity',
    ladder: ['high', 'medium', 'low'],
    note: 'A model whose name ends in a rung, like gemini-3.7-flash-low, runs at that rung, and the effort after the colon is not sent.',
  },
  {
    cli: 'my-cli',
    called: 'a CLI added in /settings',
    ladder: [],
    acp: true,
    note: 'It has no ladder. Any word is taken and none is sent: it runs at whatever you configured it at.',
  },
]

const picked = ref('claude')
const typed = ref('high')
const wide = ref(false)

const backend = computed(() => BACKENDS.find((one) => one.cli === picked.value) ?? BACKENDS[0])

// The word stays as it is when the backend changes, so one word can be tried on each.
function pick(cli: string) {
  picked.value = cli
}

function take(rung: string) {
  typed.value = rung
}

// What goes after the colon: the rung, with `swarm` in front on Kimi when swarm mode is on.
const effort = computed(() => {
  const word = typed.value.trim()
  if (backend.value.swarms && wide.value && word && word !== 'auto' && !word.startsWith('swarm')) {
    return `swarm${word}`
  }
  return word
})

// The rung the ladder is checked for, as `Profile.takes` reads it.
const rung = computed(() => {
  const word = effort.value
  return backend.value.swarms ? word.replace(/^swarm/, '') : word
})

const spec = computed(() => `agent=${backend.value.cli}/MODEL:${effort.value}`)

type Verdict = { ok: boolean; text: string }

const verdict = computed<Verdict>(() => {
  const one = backend.value
  const word = rung.value
  if (!word || word === 'auto') {
    return { ok: true, text: 'no effort: the CLI is told nothing, and the model runs at its own default' }
  }
  if (one.acp) {
    return { ok: true, text: 'taken, and not sent: an added CLI runs as it was configured' }
  }
  if (one.ladder.includes(word)) {
    const said = one.marks?.[word]
    const run = one.swarms && effort.value.startsWith('swarm') ? ', run as a fleet' : ''
    return { ok: true, text: `taken${said ? ` — ${said}` : ''}${run}` }
  }
  return {
    ok: false,
    text: `hmz exec: error: ${spec.value}: ${one.cli} cannot be asked to think at '${effort.value}'; expected one of ${one.ladder.join(', ')}`,
  }
})

// The motion, laid over the check without changing what it says. Picking a backend glides the
// lit pill to it, builds its ladder up from the easiest rung, and sends a marker climbing to
// the word being checked. A word on the ladder lands the marker with a ring, and the verdict is
// typed on; a word off it drops the marker, jolts the terminal and types the refusal out.
// Under reduced motion each of those is its final frame.
const clis = ref<HTMLElement | null>(null)
const glide = ref<HTMLElement | null>(null)
const climb = ref<HTMLElement | null>(null)
const marker = ref<HTMLElement | null>(null)
const term = ref<HTMLElement | null>(null)
const live = ref(false)
// How much of the verdict has been typed; null shows all of it.
const typing = ref<number | null>(null)

const said = computed(() => (typing.value === null ? verdict.value.text : verdict.value.text.slice(0, Math.floor(typing.value))))
const unsaid = computed(() => (typing.value === null ? '' : verdict.value.text.slice(Math.floor(typing.value))))

let tl: gsap.core.Timeline | undefined
let wait: ReturnType<typeof setTimeout> | undefined
let keyed = false
let shown = picked.value
let sizes: ResizeObserver | undefined
let seen: IntersectionObserver | undefined

const still = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

// Where an element stands in `box`, climbing through any parent a transform has made its
// offset parent.
function within(el: HTMLElement, box: HTMLElement): { x: number; y: number } {
  let x = 0
  let y = 0
  for (let at: HTMLElement | null = el; at && at !== box; at = at.offsetParent as HTMLElement | null) {
    x += at.offsetLeft
    y += at.offsetTop
  }
  return { x, y }
}

// The top of a rung's bar, or of `auto`'s word, which is where the marker stands on it.
function top(button: HTMLElement): { x: number; y: number } {
  const box = climb.value!
  const bar = button.querySelector<HTMLElement>('.bar') ?? button.querySelector<HTMLElement>('code')!
  const at = within(bar, box)
  return { x: at.x + bar.offsetWidth / 2, y: at.y - (bar.classList.contains('bar') ? 0 : 7) }
}

function place(move: boolean) {
  const button = clis.value?.querySelector<HTMLElement>('button.on')
  if (!button || !glide.value) return
  const to = { x: button.offsetLeft, y: button.offsetTop, width: button.offsetWidth, height: button.offsetHeight }
  const gsap = motion()
  if (!move || still()) {
    gsap.set(glide.value, { ...to, autoAlpha: 1 })
    return
  }
  gsap.to(glide.value, { ...to, autoAlpha: 1, duration: 0.55, ease: 'cine', overwrite: 'auto' })
  gsap.fromTo(glide.value, { scaleY: 1 }, { keyframes: { scaleY: [1, 0.8, 1.06, 1] }, duration: 0.55, ease: 'none' })
}

// The marker on the checked rung at once, or gone if the word is on no rung.
function settle() {
  const box = climb.value
  if (!box || !marker.value) return
  const on = box.querySelector<HTMLElement>('button.on')
  if (on) motion().set(marker.value, { ...top(on), autoAlpha: 1 })
  else motion().set(marker.value, { autoAlpha: 0 })
}

// Plays what the check does, from a backend just picked (`built`) or a word just changed.
function show(built: boolean) {
  if (built) place(true)
  if (still()) {
    typing.value = null
    settle()
    return
  }
  const gsap = motion()
  tl?.kill()
  const t = gsap.timeline({ onComplete: () => void (typing.value = null) })
  tl = t
  const box = climb.value
  const buttons = box ? [...box.querySelectorAll<HTMLElement>('.rungs li:not(.apart) button')] : []
  let at = 0
  if (built && box) {
    // The ladder is built from its easiest rung up to its hardest.
    const bars = buttons.map((one) => one.querySelector('.bar')).reverse()
    const words = buttons.map((one) => one.querySelector('code')).reverse()
    t.fromTo(bars, { scaleY: 0, transformOrigin: '50% 100%' }, { scaleY: 1, duration: 0.5, ease: 'back.out(1.8)', stagger: 0.06 }, 0)
    t.fromTo(words, { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.4, stagger: 0.06 }, 0.05)
    t.fromTo(box.querySelector('.apart'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4 }, 0.1 + 0.06 * buttons.length)
    at = 0.2 + 0.06 * buttons.length
  }
  const mark = marker.value
  const on = box?.querySelector<HTMLElement>('button.on')
  if (mark && box && on) {
    // The marker climbs rung by rung, from the easiest on a new ladder, or from where it stood.
    const to = buttons.indexOf(on)
    const was = Number(gsap.getProperty(mark, 'autoAlpha')) > 0.5 && !built ? nearest(buttons, mark) : buttons.length - 1
    const path: number[] = []
    if (to >= 0 && was >= 0) for (let i = was; i !== to; i += to < was ? -1 : 1) path.push(i)
    const stops = [...path.map((i) => top(buttons[i])), top(on)]
    if (built || Number(gsap.getProperty(mark, 'autoAlpha')) < 0.5) {
      if (built) t.to(mark, { autoAlpha: 0, duration: 0.2, ease: 'none' }, 0)
      t.set(mark, { ...stops[0], autoAlpha: 0 }, at)
      t.to(mark, { autoAlpha: 1, duration: 0.15, ease: 'none' }, at)
    }
    const hop = Math.max(0.09, Math.min(0.16, 0.7 / stops.length))
    stops.forEach((one, i) => t.to(mark, { ...one, duration: hop, ease: i === stops.length - 1 ? 'back.out(2.5)' : 'sine.inOut' }, i ? '>' : at))
    at = t.duration()
    t.fromTo(mark.querySelector('.land'), { autoAlpha: 0, scale: 0.5, transformOrigin: '50% 50%' }, { autoAlpha: 0.9, duration: 0.06, ease: 'none' }, at)
    t.to(mark.querySelector('.land'), { autoAlpha: 0, scale: 2.6, duration: 0.8, ease: 'power2.out' }, '>')
    t.fromTo(on.querySelector('code'), { scale: 1 }, { keyframes: { scale: [1, 1.12, 1] }, duration: 0.4, ease: 'sine.inOut' }, at)
  } else if (mark) {
    // Off the ladder: the marker falls away.
    t.to(mark, { y: '+=14', autoAlpha: 0, duration: 0.35, ease: 'cine.in' }, 0)
  }
  const pane = term.value
  if (!pane) return
  const text = verdict.value.text
  typing.value = 0
  const cps = verdict.value.ok ? 70 : 110
  const typed = { n: 0 }
  t.fromTo(pane.querySelector('.mark'), { scale: 0.3, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: 0.4, ease: 'back.out(3)' }, at)
  t.to(typed, { n: text.length, duration: text.length / cps, ease: 'none', onUpdate: () => void (typing.value = typed.n) }, at + 0.05)
  if (verdict.value.ok) {
    t.fromTo(pane.querySelector('.sweep'), { xPercent: -100, autoAlpha: 1 }, { xPercent: 100, duration: 0.9, ease: 'cine' }, at)
  } else {
    t.fromTo(pane, { x: 0 }, { keyframes: { x: [0, -7, 6, -4, 2, 0] }, duration: 0.45, ease: 'none' }, at)
    t.fromTo(pane.querySelector('.flash'), { autoAlpha: 0.9 }, { autoAlpha: 0, duration: 0.7, ease: 'power2.out' }, at)
    t.fromTo(pane.querySelector('.after'), { autoAlpha: 0, y: 4 }, { autoAlpha: 1, y: 0, duration: 0.35 }, '>')
  }
}

function keying() {
  keyed = true
}

// The rung the marker stands over now.
function nearest(buttons: HTMLElement[], mark: HTMLElement): number {
  const gsap = motion()
  const x = Number(gsap.getProperty(mark, 'x'))
  const y = Number(gsap.getProperty(mark, 'y'))
  let best = buttons.length - 1
  let far = Infinity
  buttons.forEach((one, i) => {
    const p = top(one)
    const d = Math.hypot(p.x - x, p.y - y)
    if (d < far) {
      far = d
      best = i
    }
  })
  return best
}

watch(
  () => [picked.value, effort.value],
  () => {
    clearTimeout(wait)
    const built = picked.value !== shown
    shown = picked.value
    // While a word is being typed, the check waits for a pause in the typing.
    if (keyed && !built) wait = setTimeout(() => show(false), 320)
    else show(built)
    keyed = false
  },
  { flush: 'post' },
)

onMounted(() => {
  live.value = true
  sizes = new ResizeObserver(() => {
    place(false)
    if (!tl?.isActive()) settle()
  })
  if (clis.value) sizes.observe(clis.value)
  nextTick(() => {
    place(false)
    settle()
    if (climb.value) sizes?.observe(climb.value)
    if (still()) return
    show(true)
    tl?.pause(0)
    // The first ladder is built the first time the check is scrolled to.
    seen = new IntersectionObserver(
      (entries) => {
        if (!entries.some((one) => one.isIntersecting)) return
        seen?.disconnect()
        tl?.play()
      },
      { threshold: 0.4 },
    )
    if (climb.value) seen.observe(climb.value)
  })
})

onBeforeUnmount(() => {
  tl?.kill()
  clearTimeout(wait)
  sizes?.disconnect()
  seen?.disconnect()
})
</script>

<template>
  <div class="ladder hmz-panel" :class="{ live }">
    <div ref="clis" class="clis" role="group" aria-label="backend">
      <span ref="glide" class="glide" aria-hidden="true" />
      <button
        v-for="one in BACKENDS"
        :key="one.cli"
        type="button"
        :class="{ on: one.cli === picked, acp: one.acp }"
        :aria-pressed="one.cli === picked"
        @click="pick(one.cli)"
      >
        {{ one.acp ? 'added CLI' : one.cli }}
      </button>
    </div>

    <div class="body">
      <p class="called">
        <strong>{{ backend.called }}</strong>
        <span v-if="!backend.acp">hardest first · click a rung</span>
      </p>

      <div v-if="backend.ladder.length" ref="climb" class="climb">
        <ol class="rungs">
          <li v-for="(one, at) in backend.ladder" :key="`${backend.cli}/${one}`">
            <button
              type="button"
              :class="{ on: one === rung, soft: Boolean(backend.marks?.[one]) }"
              :aria-pressed="one === rung"
              :title="backend.marks?.[one]"
              :style="{ '--depth': 1 - at / Math.max(backend.ladder.length - 1, 1) }"
              @click="take(one)"
            >
              <span class="bar" />
              <code>{{ one }}</code>
            </button>
          </li>
          <li class="apart">
            <button type="button" :class="{ on: rung === 'auto' }" :aria-pressed="rung === 'auto'" @click="take('auto')">
              <code>auto</code>
            </button>
          </li>
        </ol>
        <span ref="marker" class="marker" aria-hidden="true"><span class="halo" /><span class="land" /><span class="dot" /></span>
      </div>
      <p v-else class="none">no ladder · <code>auto</code> or any word</p>

      <label v-if="backend.swarms" class="swarm">
        <input v-model="wide" type="checkbox" />
        swarm mode
      </label>

      <label class="word">
        <span>or type a word</span>
        <input
          v-model="typed"
          type="text"
          spellcheck="false"
          autocomplete="off"
          aria-label="effort"
          @input="keying"
        />
      </label>

      <div ref="term" class="term" :class="{ bad: !verdict.ok }">
        <span class="sweep" aria-hidden="true" />
        <span class="flash" aria-hidden="true" />
        <p><span class="dim">$ hmz exec … -a</span> {{ spec }}</p>
        <p class="said">
          <span class="mark">{{ verdict.ok ? '✓' : '✗' }}</span> <span aria-hidden="true">{{ said }}</span><span class="ghost" aria-hidden="true">{{ unsaid }}</span
          ><span class="sr">{{ verdict.text }}</span>
        </p>
        <p v-if="!verdict.ok" class="dim after">exit status 2 · nothing ran</p>
      </div>

      <p class="note">{{ backend.note }}</p>
    </div>

    <p class="caption">
      A simulation of the check <code>hmz exec -a</code> makes, drawn from humanize’s own table
      of backends. Nothing here runs a CLI.
    </p>
  </div>
</template>

<style scoped>
.clis {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.clis button {
  padding: 3px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
  position: relative;
}

/* The lit pill behind the picked backend, which glides from one to the next. It shows only once
   the page has its script; until then the picked button lights itself. */
.glide {
  position: absolute;
  top: 0;
  left: 0;
  visibility: hidden;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--vp-c-brand-1) 12%, transparent);
  pointer-events: none;
}

.live .clis button.on {
  border-color: transparent;
  background: transparent;
}

.clis button:hover {
  border-color: var(--vp-c-brand-1);
}

.clis button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.clis button.acp {
  font-family: var(--vp-font-family-base);
  font-style: italic;
}

.body {
  padding: 14px 16px 4px;
}

.called {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  margin: 0 0 10px;
  font-size: 14px;
}

.called span {
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.climb {
  position: relative;
  padding-top: 8px;
}

/* The marker that climbs the ladder to the checked word: a dot with a breathing halo, and a
   ring that goes out from it when it lands. */
.marker {
  position: absolute;
  top: 0;
  left: 0;
  width: 0;
  height: 0;
  visibility: hidden;
  pointer-events: none;
  z-index: 1;
}

.marker > span {
  position: absolute;
  border-radius: 50%;
}

.marker .dot {
  left: -5px;
  top: -5px;
  width: 10px;
  height: 10px;
  border: 2px solid var(--hmz-accent);
  background: var(--vp-c-bg);
  box-shadow: 0 0 6px color-mix(in srgb, var(--hmz-accent) 60%, transparent);
}

.marker .halo,
.marker .land {
  left: -11px;
  top: -11px;
  width: 22px;
  height: 22px;
  border: 1.5px solid var(--hmz-accent);
}

.marker .halo {
  opacity: 0.35;
}

.marker .land {
  visibility: hidden;
  border-width: 2px;
}

.rungs {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.rungs li {
  margin: 0;
}

.rungs button {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.rungs .bar {
  display: block;
  height: calc(6px + var(--depth, 0) * 26px);
  border-radius: 4px 4px 0 0;
  background: var(--vp-c-default-soft);
  transition: background 0.2s;
}

.rungs code {
  padding: 3px 8px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 7px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 12.5px;
  transition: border-color 0.2s, background 0.2s;
}

.rungs button.soft code {
  border-style: dashed;
}

.rungs button:hover code {
  border-color: var(--vp-c-brand-1);
}

.rungs button.on .bar {
  background: linear-gradient(180deg, var(--hmz-accent), var(--vp-c-brand-1));
}

.rungs button.on code {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.rungs .apart {
  margin-left: 10px;
  padding-left: 12px;
  border-left: 1px dashed var(--vp-c-divider);
}

.none {
  margin: 0;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.swarm {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  font-size: 13px;
  color: var(--vp-c-text-2);
  cursor: pointer;
}

.word {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  margin-top: 14px;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.word input {
  width: 12em;
  max-width: 100%;
  padding: 4px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 7px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
}

.word input:focus {
  outline: none;
  border-color: var(--vp-c-brand-1);
}

.term {
  position: relative;
  overflow: hidden;
  margin-top: 14px;
  padding: 10px 12px;
  border: 1px solid var(--vp-c-divider);
  border-left: 3px solid var(--hmz-accent);
  border-radius: 8px;
  background: var(--vp-code-block-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.term.bad {
  border-left-color: var(--vp-c-danger-1);
}

.term p {
  margin: 0;
  color: var(--vp-c-text-1);
}

.term .said {
  color: var(--hmz-accent);
}

.term.bad .said {
  color: var(--vp-c-danger-1);
}

.term .mark {
  display: inline-block;
  font-weight: 700;
}

.term .ghost {
  color: transparent;
}

.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

/* A band of light across the terminal when a word is taken, and a red wash when it is not. */
.term .sweep,
.term .flash {
  position: absolute;
  inset: 0;
  visibility: hidden;
  pointer-events: none;
}

.term .sweep {
  background: linear-gradient(100deg, transparent 20%, color-mix(in srgb, var(--hmz-accent) 22%, transparent) 50%, transparent 80%);
}

.term .flash {
  background: color-mix(in srgb, var(--vp-c-danger-1) 14%, transparent);
}

.term .dim {
  color: var(--vp-c-text-3);
}

.note {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.caption {
  margin: 12px 0 0;
  padding: 8px 16px 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--vp-c-text-3);
}

@media (prefers-reduced-motion: no-preference) {
  .marker .halo {
    animation: breathe 2.4s ease-in-out infinite;
  }
}

@keyframes breathe {
  50% {
    opacity: 0.08;
    transform: scale(1.5);
  }
}

@media (prefers-reduced-motion: reduce) {
  .clis button,
  .rungs .bar,
  .rungs code {
    transition: none;
  }
}
</style>
