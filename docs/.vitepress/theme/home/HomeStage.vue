<script setup lang="ts">
// The stage: one screen that plays the product a scene at a time, and the tabs that name the
// scenes. Each scene is a reel of the real interface (tests/system/docs/test_docs_home_*.py):
// an SVG that plays by itself in an <img>, in four files -- for a desk and for a phone, each in
// the light theme and in the dark one -- of which the one that fits the reader is shown.
//
// A scene plays through once and the next takes the screen, until the reader picks one: then it
// stays, as a reel loops by itself. The scenes also wait while the pointer is over the stage or
// the keyboard is in it, so that what a reader is about to open does not change under them. A
// reel is started from its first frame by giving the <img> a new address for the same file (an
// object URL of its text, which is fetched once).
//
// One control under the screen stops what moves: the scenes wait, the reel is drawn at rest (as
// the file draws itself for a reader who asked for less motion, which the page asks of it by
// rewriting that one condition), and the page stops its own drawing too (`paused`). Nothing here
// moves for a reader who asked for less motion: the reels are drawn at rest in the same way, on
// their telling frame, the tabs still change the scene, and there is nothing for the control to
// stop, so it is not there. Before the script runs, and without it, the screen shows the first
// scene, chosen by the theme's class and the window's width alone.
//
// Two roots, the tabs and the screen: the page lays them out in its own grid. What the page puts
// in the stage (its slot) is laid out by the page too; the stage only says where it stands in
// the page's source, which is the order the keyboard walks: before the tabs where they lie in
// rows and it is shown over them, and after the screen where it is shown under the tabs, beside
// the screen.
import { useData, withBase } from 'vitepress'
import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { SCENES, WORDS } from './copy'
import { data as REELS } from './reels.data'

/** Whether the reader stopped what moves; the page's own drawing follows it. */
const paused = defineModel<boolean>('paused', { default: false })

/** The widest window that plays the reels shot for a phone; the same number is in the styles. */
const PHONE_WIDE = '(max-width: 640px)'
/** The widest window whose tabs lie in rows over the screen; in a wider one they are a column
 *  beside it. The same number is in the styles, here and in the page's. */
const STACKED = '(max-width: 900px)'
/** What `window="desktop"` draws around a frame for its shadow (`_SHADOW` in shots.py): the
 *  screen shows the window to its own edge, and is the frame it stands in. */
const SHADOW = { side: 44, above: 28, below: 60 }
/** The sizes the scenes are shot at (tests/system/docs/home.py), until the files say. */
const DESK = { width: 1040 + 2 * SHADOW.side, height: 680 + SHADOW.above + SHADOW.below, seconds: 8 }
const PHONE = { width: 392, height: 520, seconds: 8 }
/** How long the scenes wait for one that did not load before they go on to the next. */
const AGAIN = 4

const { isDark } = useData()
const narrow = ref(false)
/** Rows until the script runs: the page comes in the order a phone shows it in. */
const stacked = ref(true)
const still = ref(false)
/** Whether the control that stops what moves is there: once the script runs, where things move. */
const stoppable = ref(false)

const name = (at: number, phone: boolean) => `home-${SCENES[at].key}${phone ? '-phone' : ''}`
const address = (at: number, phone: boolean, dark: boolean) => withBase(`/shots/${name(at, phone)}${dark ? '.dark' : ''}.svg`)
const reel = (at: number, phone: boolean) => REELS[name(at, phone)] ?? (phone ? PHONE : DESK)

/** A reel for a desk is a window with its shadow around it, but the terminal's, which is drawn
 *  as a terminal draws itself and is fitted whole. A reel for a phone is the page, edge to edge. */
const windowed = (at: number, phone: boolean) => !phone && SCENES[at].key !== 'terminal'

/** How a window's reel is placed so that the window itself fills the screen. */
function crop(at: number) {
  const { width, height } = reel(at, false)
  const inner = { width: width - 2 * SHADOW.side, height: height - SHADOW.above - SHADOW.below }
  return {
    '--w': `${(100 * width) / inner.width}%`,
    '--l': `${(-100 * SHADOW.side) / inner.width}%`,
    '--t': `${(-100 * SHADOW.above) / inner.height}%`,
  }
}

/** The screen's shape: the window's own, on a desk; the page's, on a phone. The page's styles
 *  size the screen by these. */
const shape = computed(() => {
  const desk = reel(0, false)
  const phone = reel(0, true)
  const window = { width: desk.width - 2 * SHADOW.side, height: desk.height - SHADOW.above - SHADOW.below }
  return {
    '--desk': `${window.width} / ${window.height}`,
    '--desk-n': String(window.width / window.height),
    '--phone': `${phone.width} / ${phone.height}`,
    '--phone-n': String(phone.width / phone.height),
    ...crop(0),
  }
})

interface Layer {
  id: number
  /** The scene it shows, and the file it was read from. */
  at: number
  url: string
  src: string
  alt: string
  seconds: number
  windowed: boolean
  style: Record<string, string>
  on: boolean
  /** The first reel takes the place of the same picture, so it does not fade in. */
  cut: boolean
}

/** The scene the tabs name, and the one on the screen, which follows once its reel is drawn. */
const at = ref(0)
const live = ref(0)
const layers = ref<Layer[]>([])
/** Whether a reel of the script's has taken the screen from the picture the page came with,
 *  and whether that picture, which stays under the reel until it is whole, is gone. */
const started = ref(false)
const covered = ref(false)
/** Whether the scenes still follow one another, which ends when the reader picks one. */
const rotating = ref(true)
/** Whether the pointer is over the stage, and whether the keyboard is in it. */
const hovered = ref(false)
const focused = ref(false)
const held = computed(() => hovered.value || focused.value)
const length = ref(8)
/** Counts every showing: the tab's line is drawn anew for each, by a keyframe of another name,
 *  from as far into the reel as the reel is (`skip`, in seconds). */
const showing = ref(0)
const skip = ref(0)

/** A reel's text, fetched once. One that did not come is asked for again the next time. */
const files = new Map<string, Promise<string | null>>()
const fetched = (url: string) => {
  let file = files.get(url)
  if (!file) {
    file = fetch(url)
      .then((answer) => (answer.ok ? answer.text() : null))
      .catch(() => null)
    files.set(url, file)
    void file.then((text) => {
      if (text === null) files.delete(url)
    })
  }
  return file
}

/** A reel as it rests: what it draws for a reader who asked for less motion, for every reader. */
const rest = (text: string) =>
  text.replace(/\(\s*prefers-reduced-motion\s*:\s*no-preference\s*\)/g, 'not all').replace(/\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)/g, 'all')

const gone = (layer: Layer) => {
  if (layer.src.startsWith('blob:')) URL.revokeObjectURL(layer.src)
}

let plays = 0
let onScreen = 0
let began = 0
let misses = 0
let timer: ReturnType<typeof setTimeout> | undefined
/** The scene that is due after one that did not load, until a scene is asked for again. */
let missed: number | null = null
/** Whether the screen is before the reader: in the window, and the window in front. */
const seen = ref(true)

/** Whether the next scene is due when this one's reel ends. */
const moving = () => rotating.value && seen.value && !held.value && !paused.value

async function show(to: number) {
  at.value = to
  missed = null
  const mine = ++plays
  clearTimeout(timer)
  const phone = narrow.value
  const url = address(to, phone, isDark.value)
  const text = await fetched(url)
  if (mine !== plays) return
  layers.value.push({
    id: mine,
    at: to,
    url,
    src: text === null ? url : URL.createObjectURL(new Blob([paused.value || still.value ? rest(text) : text], { type: 'image/svg+xml' })),
    alt: SCENES[to].alt,
    seconds: reel(to, phone).seconds || 8,
    windowed: windowed(to, phone),
    style: windowed(to, phone) ? crop(to) : {},
    on: false,
    cut: !started.value,
  })
}

/** The next scene, when what is left of this one's reel has played. */
function arm(left: number) {
  clearTimeout(timer)
  if (moving()) timer = setTimeout(() => show((live.value + 1) % SCENES.length), left * 1000)
}

/** A reel is drawn: it takes the screen, the one before it leaves, and its time starts. */
function drawn(id: number) {
  const layer = layers.value.find((one) => one.id === id)
  if (!layer || id !== plays) return
  layer.on = true
  for (const old of layers.value) if (old.id !== id) old.on = false
  started.value = true
  live.value = layer.at
  onScreen = id
  misses = 0
  setTimeout(() => {
    covered.value = true
    layers.value = layers.value.filter((one) => {
      if (one.id >= id) return true
      gone(one)
      return false
    })
  }, 500)
  length.value = layer.seconds
  began = performance.now()
  skip.value = 0
  showing.value++
  if (rotating.value) void fetched(address((layer.at + 1) % SCENES.length, narrow.value, isDark.value))
  arm(length.value)
}

/** A reel did not load: the screen keeps the scene it has and the tabs name that one again;
 *  the scenes go on to the one after, a little later, and stop when a whole round has failed.
 *  If they are waiting by then, or are made to wait before that, the one after is what they go
 *  on to when the wait is over (`missed`). */
function failed(id: number) {
  const layer = layers.value.find((one) => one.id === id)
  if (!layer) return
  gone(layer)
  layers.value = layers.value.filter((one) => one.id !== id)
  files.delete(layer.url)
  if (id !== plays) return
  at.value = live.value
  const next = (layer.at + 1) % SCENES.length
  missed = next
  if (++misses >= SCENES.length || !moving()) return
  skip.value = Math.max(0, length.value - AGAIN)
  showing.value++
  timer = setTimeout(() => show(next), AGAIN * 1000)
}

function pick(to: number) {
  rotating.value = false
  void show(to)
}

/** Stops what moves, or starts it again: the same scene, at rest or from its first frame. */
function toggle() {
  paused.value = !paused.value
  void show(at.value)
}

const tabs = ref<HTMLElement | null>(null)
function step(event: KeyboardEvent, from: number) {
  const last = SCENES.length - 1
  const to = {
    ArrowDown: (from + 1) % SCENES.length,
    ArrowRight: (from + 1) % SCENES.length,
    ArrowUp: (from + last) % SCENES.length,
    ArrowLeft: (from + last) % SCENES.length,
    Home: 0,
    End: last,
  }[event.key]
  if (to === undefined) return
  event.preventDefault()
  pick(to)
  tabs.value?.querySelectorAll<HTMLElement>('[role=tab]')[to]?.focus()
}

const screen = ref<HTMLElement | null>(null)

/** The pointer comes over the stage or the keyboard into it, and the scenes wait; it leaves,
 *  and they go on: the reel kept looping meanwhile, so the next comes when this loop ends, or
 *  at once if it is one that did not load before. */
function hold(what: Ref<boolean>, now: boolean) {
  const was = held.value
  what.value = now
  if (held.value === was) return
  if (held.value) return clearTimeout(timer)
  if (!moving()) return
  if (missed !== null) return void show(missed)
  if (!started.value || onScreen !== plays) return
  const into = ((performance.now() - began) / 1000) % length.value
  skip.value = into
  showing.value++
  arm(length.value - into)
}
/** Crossing from the tabs to the screen is not leaving the stage. */
let leaving: ReturnType<typeof setTimeout> | undefined
function over(event: PointerEvent, now: boolean) {
  if (event.pointerType === 'touch') return
  clearTimeout(leaving)
  if (now) hold(hovered, true)
  else leaving = setTimeout(() => hold(hovered, false), 150)
}
const within = (node: EventTarget | null) => node instanceof Node && !!(tabs.value?.contains(node) || screen.value?.contains(node))
/** Only the keyboard's focus holds the scenes: a click leaves its focus behind when it is done. */
function entered(event: FocusEvent) {
  if (event.target instanceof Element && event.target.matches(':focus-visible')) hold(focused, true)
}
function left(event: FocusEvent) {
  if (!within(event.relatedTarget)) hold(focused, false)
}

let phone: MediaQueryList | undefined
let rows: MediaQueryList | undefined
let watching: IntersectionObserver | undefined
const resized = () => {
  narrow.value = !!phone?.matches
  stacked.value = !!rows?.matches
}
/** Away from the screen -- another tab, or scrolled off -- the scenes wait where they are, and
 *  the tab's line is whole. Back, the scene plays from its first frame, or the one after it if
 *  that did not load before. */
function looked(now: boolean) {
  if (now === seen.value) return
  seen.value = now
  if (!now) clearTimeout(timer)
  else if (moving() && (started.value || missed !== null)) void show(missed ?? at.value)
}
const hidden = () => looked(!document.hidden)

onMounted(() => {
  phone = matchMedia(PHONE_WIDE)
  rows = matchMedia(STACKED)
  resized()
  phone.addEventListener('change', resized)
  rows.addEventListener('change', resized)
  still.value = matchMedia('(prefers-reduced-motion: reduce)').matches
  rotating.value = !still.value
  stoppable.value = !still.value
  document.addEventListener('visibilitychange', hidden)
  if (screen.value) {
    watching = new IntersectionObserver(([entry]) => looked(entry.isIntersecting && !document.hidden), { threshold: 0.2 })
    watching.observe(screen.value)
  }
  void show(0)
  // The theme is switched, or the window crosses a phone's width: the same scene, in the file
  // that fits now.
  watch([isDark, narrow], () => void show(at.value))
})
onBeforeUnmount(() => {
  clearTimeout(timer)
  clearTimeout(leaving)
  phone?.removeEventListener('change', resized)
  rows?.removeEventListener('change', resized)
  document.removeEventListener('visibilitychange', hidden)
  watching?.disconnect()
  layers.value.forEach(gone)
})
</script>

<template>
  <slot v-if="stacked" />

  <div
    ref="tabs"
    class="st-tabs"
    :class="{ timed: rotating && started && seen && !held && !paused, again: showing % 2 === 1 }"
    role="tablist"
    :aria-label="WORDS.tabs"
    :aria-orientation="stacked ? 'horizontal' : 'vertical'"
    :style="{ '--length': `${length}s`, '--skip': `${-skip}s` }"
    @pointerenter="over($event, true)"
    @pointerleave="over($event, false)"
    @focusin="entered"
    @focusout="left"
  >
    <button
      v-for="(scene, i) in SCENES"
      :id="`st-tab-${scene.key}`"
      :key="scene.key"
      type="button"
      role="tab"
      aria-controls="st-screen"
      :aria-selected="i === at"
      :tabindex="i === at ? 0 : -1"
      @click="pick(i)"
      @keydown="step($event, i)"
    >
      {{ scene.tab }}
    </button>
  </div>

  <div
    id="st-screen"
    ref="screen"
    class="st-screen"
    role="tabpanel"
    :aria-labelledby="`st-tab-${SCENES[at].key}`"
    :style="shape"
    @pointerenter="over($event, true)"
    @pointerleave="over($event, false)"
    @focusin="entered"
    @focusout="left"
  >
    <!-- The link opens the page about the scene on the screen, and is named by its picture:
         only the picture that is showing says what it is. -->
    <a class="st-link" :href="withBase(SCENES[live].href)">
      <!-- The picture the page comes with: the first scene, in the file the theme and the
           window's width choose, with no script. Only the one that is shown is fetched. -->
      <template v-if="!covered">
        <picture v-for="dark in [false, true]" :key="String(dark)" :class="dark ? 'st-dark' : 'st-light'">
          <source :media="PHONE_WIDE" :srcset="address(0, true, dark)" />
          <img class="st-reel windowed on" :src="address(0, false, dark)" :alt="started ? '' : SCENES[0].alt" loading="lazy" decoding="async" />
        </picture>
      </template>
      <img
        v-for="layer in layers"
        :key="layer.id"
        class="st-reel"
        :class="{ windowed: layer.windowed, on: layer.on, cut: layer.cut }"
        :style="layer.style"
        :src="layer.src"
        :alt="layer.on ? layer.alt : ''"
        decoding="async"
        @load="drawn(layer.id)"
        @error="failed(layer.id)"
      />
    </a>
    <!-- Its word says what it does next, so it carries no pressed state beside it. -->
    <button v-if="stoppable" type="button" class="st-hold" @click="toggle">
      {{ paused ? WORDS.play : WORDS.pause }}
    </button>
  </div>

  <slot v-if="!stacked" />
</template>

<style scoped>
/* ---- the tabs -------------------------------------------------------------------------- */

/* Their size and the room between them are the page's to give (`--tab-size`, `--tab-pad`): on
   a desk they shrink with the screen, so that the column beside it is never the taller. */
.st-tabs {
  display: flex;
  flex-direction: column;
}
.st-tabs button {
  position: relative;
  display: block;
  width: 100%;
  padding: var(--tab-pad, 13px) 0 calc(var(--tab-pad, 13px) + 1px);
  border-bottom: 2px solid var(--hm-rule);
  font-size: var(--tab-size, clamp(26px, 2.75vw, 40px));
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.035em;
  text-align: left;
  color: var(--hm-fg-dim);
  transition: color 0.2s;
}
.st-tabs button:hover {
  color: var(--hm-fg-2);
}
.st-tabs button[aria-selected='true'] {
  color: var(--hm-fg);
}
/* The line under the scene that is on: whole when the reader picked it, holds the scenes or is
   away from the screen, and drawn across in the time its reel runs while they follow one
   another. */
.st-tabs button::after {
  content: '';
  position: absolute;
  left: 0;
  bottom: -2px;
  width: 100%;
  height: 2px;
  background: var(--hm-pink);
  transform: scaleX(0);
  transform-origin: left;
}
.st-tabs button[aria-selected='true']::after {
  transform: scaleX(1);
}
.st-tabs.timed button[aria-selected='true']::after {
  animation: st-run var(--length) linear var(--skip, 0s) both;
}
.st-tabs.timed.again button[aria-selected='true']::after {
  animation-name: st-run-again;
}
@keyframes st-run {
  from {
    transform: scaleX(0);
  }
}
@keyframes st-run-again {
  from {
    transform: scaleX(0);
  }
}

/* ---- the screen ------------------------------------------------------------------------ */

/* A flat ink block with a hard shadow, square, as a poster frames a picture. The window in it
   reaches its edges. The block is the link itself, so the ring of its focus is not cut off. */
.st-screen {
  position: relative;
  aspect-ratio: var(--desk);
}
.st-link {
  position: absolute;
  inset: 0;
  display: block;
  overflow: hidden;
  border: 2px solid var(--hm-edge);
  background: var(--hm-house);
  box-shadow: var(--hm-cast) var(--hm-cast) 0 var(--hm-pink);
}
/* The ring stands clear of the block, and the shadow it would cross takes its colour. */
.st-link:focus-visible {
  box-shadow: var(--hm-cast) var(--hm-cast) 0 var(--hm-ring);
}
.st-reel {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  max-width: none;
  object-fit: contain;
  opacity: 0;
  transition: opacity 0.45s ease;
}
.st-reel.on {
  opacity: 1;
}
.st-reel.cut {
  transition: none;
}
/* A terminal is fitted whole, with a little of the block around it. */
.st-reel:not(.windowed) {
  padding: 2.5%;
}
/* A window is laid over the screen so that its shadow falls outside. */
.st-reel.windowed {
  inset: auto;
  left: var(--l);
  top: var(--t);
  width: var(--w);
  height: auto;
}
/* The picture the page comes with, of the theme that is on. (`:global()` takes the whole
   selector: what follows it outside the brackets is dropped.) */
.st-dark {
  display: none;
}
:global(.dark .st-light) {
  display: none;
}
:global(.dark .st-dark) {
  display: block;
}

/* The one control, under the screen where its shadow ends: a word, as the command's is. */
.st-hold {
  position: absolute;
  top: calc(100% + var(--hm-cast) + 4px);
  right: calc(-1 * var(--hm-cast));
  min-width: 5ch;
  height: 28px;
  font-family: var(--hm-mono);
  font-size: 13px;
  line-height: 1;
  text-align: right;
  color: var(--hm-pink-text);
}
.st-hold:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* ---- rows over the screen: a tablet, and a phone ---------------------------------------- */

@media (max-width: 900px) {
  .st-tabs {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    column-gap: 12px;
  }
  .st-tabs button {
    padding: 12px 0;
    font-size: clamp(19px, 2.7vw, 21px);
  }
  /* A finger's width. */
  .st-hold {
    min-width: 44px;
    height: 44px;
  }
}
@media (max-width: 640px) {
  .st-tabs {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    column-gap: 14px;
  }
  .st-tabs button {
    font-size: clamp(19px, 5.6vw, 21px);
  }
  .st-screen {
    aspect-ratio: var(--phone);
  }
  /* A phone's reel is the page itself, edge to edge. */
  .st-reel,
  .st-reel.windowed,
  .st-reel:not(.windowed) {
    inset: 0;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    padding: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .st-reel {
    transition: none;
  }
  .st-tabs.timed button[aria-selected='true']::after {
    animation: none;
  }
}
</style>
