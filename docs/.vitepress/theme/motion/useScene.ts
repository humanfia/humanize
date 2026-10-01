// A scene is one GSAP timeline, cut into beats, that plays while it is on screen.
//
// Every feature scene is built the same way, so the rules the docs hold a moving diagram to are
// kept here once rather than in each of them:
//
// - It starts when it is first scrolled into view, and pauses whenever it leaves the screen or
//   the tab is hidden. Nothing animates that nobody can see.
// - Under `prefers-reduced-motion` it does not play. The timeline is built anyway and seeked to
//   `still`, a frame chosen to be worth reading, and the play button stays there for anyone who
//   wants the motion after all.
// - Its beats are the labels `beat-0`, `beat-1`... on the timeline. `HmzStage` draws them as
//   chapters under the picture, each one a line of words, so nothing is said only by a moving
//   thing, and a chapter can be clicked to jump to it.
// - Anything drawn per frame outside the timeline (sparks on a canvas) goes in `tick`, which
//   runs only while the timeline does.
// - It lists itself in `probe.ts`, so the check that every word can be read holds it still at
//   moment after moment of its timeline rather than playing it on a clock.
//
// A rebuild reverts every tween, so an SVG attribute that only a tween ever set (an `attr`
// tween on a `cx` the template leaves out) comes back empty: give it a value in the markup.
//
// Only `onMounted` touches the DOM, so a scene renders on the server as its markup and nothing
// else.
import { nextTick, onMounted, onUnmounted, ref, shallowRef, type Ref } from 'vue'

import { hush } from './fx'
import { motion } from './gsap'
import { probe } from './probe'

type Timeline = gsap.core.Timeline

export interface SceneOptions {
  /** Fill the timeline. Selectors in it are scoped to the scene's root. */
  build: (tl: Timeline, q: (selector: string) => Element[]) => void
  /** Where to hold still under reduced motion: a label, or a fraction of the timeline. */
  still?: string | number
  /** Loop, with a breath between loops. On by default. */
  loop?: boolean
  repeatDelay?: number
  /** Run every frame while the timeline plays: dt in seconds. */
  tick?: (dt: number) => void
  /** Called after each (re)build, and before the first frame is drawn. */
  ready?: (tl: Timeline) => void
}

export interface Scene {
  root: Ref<HTMLElement | null>
  timeline: Ref<Timeline | null>
  /** The viewer's intent: true unless they pressed pause (or asked for reduced motion). */
  playing: Ref<boolean>
  reduced: Ref<boolean>
  /** Whether it is moving right now: wanted, on screen, and the tab showing. */
  running: Ref<boolean>
  /** 0..1 through the current loop. */
  progress: Ref<number>
  /** The index of the beat under way, and where each beat starts, as fractions. */
  beat: Ref<number>
  marks: Ref<number[]>
  toggle: () => void
  seek: (beat: number) => void
  rebuild: () => void
}

export function useScene(options: SceneOptions): Scene {
  const root = ref<HTMLElement | null>(null)
  const timeline = shallowRef<Timeline | null>(null)
  const playing = ref(true)
  const reduced = ref(false)
  const running = ref(false)
  const progress = ref(0)
  const beat = ref(0)
  const marks = ref<number[]>([])

  let context: gsap.Context | undefined
  let observer: IntersectionObserver | undefined
  let media: MediaQueryList | undefined
  let visible = false
  let started = false
  let ticking: ((time: number, delta: number) => void) | undefined
  let unprobe: (() => void) | undefined

  function update() {
    const tl = timeline.value
    if (!tl) return
    const p = tl.progress()
    progress.value = p
    let at = 0
    for (let i = 0; i < marks.value.length; i += 1) if (p + 1e-6 >= marks.value[i]) at = i
    beat.value = at
  }

  function sync() {
    const tl = timeline.value
    if (!tl) return
    const go = playing.value && visible && !document.hidden
    running.value = go
    if (go) {
      started = true
      tl.resume()
    } else tl.pause()
  }

  function rest() {
    const tl = timeline.value
    if (!tl) return
    const still = options.still ?? 1
    hush(() => {
      if (typeof still === 'number') tl.progress(Math.min(still, 0.9999))
      else tl.seek(still, false)
    })
    tl.pause()
    update()
  }

  function build() {
    const gsap = motion()
    const el = root.value
    if (!el) return
    context?.revert()
    context = gsap.context((self) => {
      const tl = gsap.timeline({
        paused: true,
        repeat: options.loop === false ? 0 : -1,
        repeatDelay: options.repeatDelay ?? 1.4,
        onUpdate: update,
        onRepeat: update,
        // A scene that plays once is over when it ends: nothing is left moving.
        onComplete: () => {
          if (options.loop !== false) return
          playing.value = false
          sync()
        },
      })
      options.build(tl, (selector: string) => (self.selector ? self.selector(selector) : []))
      timeline.value = tl
    }, el)
    const tl = timeline.value!
    const d = tl.duration() || 1
    marks.value = Object.entries(tl.labels)
      .filter(([name]) => name.startsWith('beat-'))
      .sort((a, b) => Number(a[0].slice(5)) - Number(b[0].slice(5)))
      .map(([, time]) => time / d)
    options.ready?.(tl)
    if (reduced.value && !started) rest()
    else {
      tl.progress(0)
      update()
      sync()
    }
  }

  function toggle() {
    playing.value = !playing.value
    if (playing.value && timeline.value && timeline.value.progress() >= 0.9999) timeline.value.progress(0)
    sync()
  }

  function seek(i: number) {
    const tl = timeline.value
    if (!tl) return
    hush(() => tl.seek(`beat-${i}`, false))
    update()
    if (!playing.value) return
    sync()
  }

  onMounted(() => {
    const gsap = motion()
    media = window.matchMedia('(prefers-reduced-motion: reduce)')
    reduced.value = media.matches
    if (reduced.value) playing.value = false
    // A tick later, so a layout chosen in another `onMounted` (useNarrow) is already drawn.
    void nextTick(build)
    observer = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting
        sync()
      },
      { threshold: 0.2 },
    )
    if (root.value) observer.observe(root.value)
    document.addEventListener('visibilitychange', sync)
    unprobe = probe({
      root: () => root.value,
      duration: () => timeline.value?.duration() ?? 0,
      // Where each chapter ends, which is where the next one starts; the end of the last; and
      // the frame held still under reduced motion.
      settled: () => {
        const tl = timeline.value
        if (!tl) return []
        const d = tl.duration()
        const still = options.still ?? 1
        const at = typeof still === 'number' ? Math.min(still, 0.9999) * d : tl.labels[still]
        return [...marks.value.slice(1).map((m) => m * d - 1e-3), d, ...(at === undefined ? [] : [at])]
      },
      seek: async (t) => {
        const tl = timeline.value
        if (!tl) return
        tl.pause()
        tl.time(t, false)
        update()
        await nextTick()
      },
    })
    if (options.tick) {
      const tick = options.tick
      ticking = (_time, delta) => {
        const tl = timeline.value
        if (tl && !tl.paused()) tick(Math.min(delta / 1000, 0.1))
      }
      gsap.ticker.add(ticking)
    }
  })

  onUnmounted(() => {
    unprobe?.()
    observer?.disconnect()
    document.removeEventListener('visibilitychange', sync)
    if (ticking) motion().ticker.remove(ticking)
    context?.revert()
  })

  return { root, timeline, playing, reduced, running, progress, beat, marks, toggle, seek, rebuild: build }
}
