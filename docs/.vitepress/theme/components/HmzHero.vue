<script setup lang="ts">
// The first screenful of the site: what humanize is, the line that installs it, and the three
// people who arrive here. Each button lands on that reader's quickstart further down this same
// page, so nobody has to guess which tab in the nav is theirs.
//
// Beside the words, `HeroScene` builds the mark from its planes. The words come in with it:
// the name letter by letter up the same diagonal the drawing is set on, then the rest in order.
// Under reduced motion all of it is simply there.
//
// It is full-bleed. `VPHomeContent` holds the page in a 1280px column and sets `--vp-offset` to
// the distance from that column's edge to the viewport's, which is the supported way for one
// child to reach past it -- the default theme's own sponsor and team blocks do the same.
import { nextTick, onMounted, onUnmounted, ref } from 'vue'

import { motion, SplitText } from '../motion/gsap'
import HeroScene from './home/HeroScene.vue'

// The same line README.md and the quickstart below install with.
const LINE = "uv tool install hmz"

// Same-page fragments, so no `withBase`: these resolve against whatever the page is served as,
// which under `base: '/humanize/'` is the only spelling that stays right.
const ROLES = [
  { href: '#run-a-flow', n: '01', name: 'Run a flow', under: 'point coding agents at a repository' },
  { href: '#weave-a-flow', n: '02', name: 'Weave a flow', under: 'write your own, in Python' },
  { href: '#work-on-humanize', n: '03', name: 'Contribute', under: 'work on humanize itself' },
]

const copied = ref(false)
let clearing: ReturnType<typeof setTimeout> | undefined

async function copy() {
  try {
    await navigator.clipboard.writeText(LINE)
  } catch {
    return
  }
  copied.value = true
  clearTimeout(clearing)
  clearing = setTimeout(() => (copied.value = false), 1600)
}

const root = ref<HTMLElement | null>(null)
// Held invisible from the server's markup until the build has set its first frame, so the
// finished hero does not flash up and vanish before it builds. A stylesheet fallback shows it
// anyway if no script ever runs.
const pending = ref(true)
let context: gsap.Context | undefined

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    pending.value = false
    return
  }
  void nextTick(() => {
    pending.value = false
    const el = root.value
    if (!el) return
    const gsap = motion()
    context = gsap.context((self) => {
      const q = (s: string) => self.selector!(s) as Element[]
      const name = q('.wordmark .letters')[0]
      const split = SplitText.create(name, { type: 'chars', mask: 'chars' })
      const tl = gsap.timeline({ delay: 0.15 })
      tl.from(split.chars, { yPercent: 110, xPercent: -18, rotate: 10, duration: 0.9, ease: 'cine.out', stagger: 0.045 }, 0)
      tl.from(q('.wordmark .cursor'), { scaleX: 0, transformOrigin: '0% 100%', duration: 0.5, ease: 'back.out(2)' }, 0.55)
      tl.from(q('.kicker'), { autoAlpha: 0, x: -16, duration: 0.6 }, 0.1)
      tl.from(q('.define, .line, .under'), { autoAlpha: 0, y: 14, duration: 0.7, stagger: 0.12, clearProps: 'transform' }, 0.6)
      tl.from(q('.roles a'), { autoAlpha: 0, y: 18, duration: 0.6, stagger: 0.08, clearProps: 'transform' }, 0.95)
    }, el)
  })
})

onUnmounted(() => {
  clearTimeout(clearing)
  context?.revert()
})
</script>

<template>
  <section ref="root" class="hero" :class="{ pending }">
    <div class="inner">
      <div class="words">
        <p class="kicker"><span class="sq" aria-hidden="true"></span>flows for the coding agents you already use</p>

        <h1 class="wordmark">
          <span class="letters">humanize</span><span class="cursor" aria-hidden="true"></span>
        </h1>

        <p class="define">
          humanize runs <strong>flows</strong>: Python programs that drive the coding agents
          you already use — Claude Code, Codex and ten more — turn after turn, and
          record everything they did.
        </p>

        <button class="line" type="button" :aria-label="`Copy: ${LINE}`" @click="copy">
          <span class="prompt">$</span>
          <code>{{ LINE }}</code>
          <span class="copy" :class="{ done: copied }">{{ copied ? 'copied' : 'copy' }}</span>
        </button>

        <nav class="roles" aria-label="Quickstarts">
          <a v-for="role in ROLES" :key="role.href" :href="role.href">
            <span class="n" aria-hidden="true">{{ role.n }}</span>
            <strong>{{ role.name }}</strong>
            <em>{{ role.under }}</em>
          </a>
        </nav>

        <p class="under">
          Python ≥ 3.12 · 13 agent backends, plus any CLI that speaks ACP · reuses your CLI logins
        </p>
      </div>

      <div class="drawing">
        <HeroScene />
      </div>
    </div>

    <a class="cue" href="#how-it-fits-together" aria-label="How it fits together">
      <span class="chev" aria-hidden="true"></span>
    </a>
  </section>
</template>

<style scoped>
.hero {
  position: relative;
  /* Out to both viewport edges, and back in again for the content. */
  margin-left: var(--vp-offset, calc(50% - 50vw));
  margin-right: var(--vp-offset, calc(50% - 50vw));
  /* The nav bar is fixed over the top of the page, so a screenful is what is left under it. */
  min-height: calc(100svh - var(--vp-nav-height));
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 32px 84px;
}

.inner {
  width: 100%;
  max-width: 1200px;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  align-items: center;
  gap: 24px 48px;
}

.drawing {
  width: 100%;
  max-width: 580px;
  justify-self: end;
}

.kicker {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 0 0 18px;
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.sq {
  flex: none;
  width: 10px;
  height: 10px;
  margin-top: 0.38em;
  background: var(--hmz-red);
}

.wordmark {
  display: flex;
  align-items: flex-end;
  margin: 0;
  border: 0;
  padding: 0;
  color: var(--hmz-ink);
  font-size: clamp(54px, 9vw, 112px);
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.045em;
}

/* The `_` of the mark, after the name: the red wedge, blinking like the cursor it is. */
.cursor {
  flex: none;
  width: 0.62em;
  height: 0.2em;
  margin: 0 0 0.1em 0.08em;
  background: var(--hmz-red);
  clip-path: polygon(0 50%, 100% 0, 100% 100%, 0 100%);
  animation: hmz-blink 1.1s steps(1, end) 2s infinite;
}

@keyframes hmz-blink {
  50% {
    opacity: 0;
  }
}

.define {
  margin: 26px 0 0;
  max-width: 36rem;
  font-size: clamp(15px, 1.5vw, 18px);
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.define strong {
  color: var(--vp-c-text-1);
  font-weight: 650;
  box-shadow: inset 0 -0.32em 0 var(--hmz-red-soft);
}

.line {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  max-width: 100%;
  margin-top: 28px;
  padding: 12px 14px 12px 18px;
  border: 1px solid var(--hmz-ink);
  border-radius: 0;
  background: var(--vp-c-bg);
  box-shadow: 5px 5px 0 var(--hmz-ink);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  cursor: pointer;
  transition:
    box-shadow 0.2s,
    transform 0.2s;
}

.line:hover {
  box-shadow: 8px 8px 0 var(--hmz-red);
  transform: translate(-2px, -2px);
}

.line:active {
  box-shadow: 2px 2px 0 var(--hmz-red);
  transform: translate(2px, 2px);
}

.prompt {
  color: var(--hmz-red);
  font-weight: 700;
}

.line code {
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: inherit;
  font-size: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.copy {
  flex: none;
  padding: 4px 9px;
  background: var(--hmz-ink);
  color: var(--vp-c-bg);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.copy.done {
  background: var(--hmz-red);
  color: #fff;
}

/* Three doors, one per reader. Equal width, because none of them is the main one. */
.roles {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 34px;
  max-width: 40rem;
}

.roles a {
  position: relative;
  display: block;
  padding: 14px 16px 15px;
  border: 1px solid var(--hmz-panel-border);
  border-top: 3px solid var(--hmz-ink);
  background: var(--hmz-panel-bg);
  text-decoration: none;
  overflow: hidden;
  isolation: isolate;
  transition:
    border-color 0.25s,
    transform 0.25s;
}

/* On hover a red plane slides in on the diagonal behind the words. */
.roles a::before {
  content: '';
  position: absolute;
  inset: -2px;
  z-index: -1;
  background: var(--hmz-red-soft);
  clip-path: polygon(0 100%, 0 100%, 0 100%);
  transition: clip-path 0.45s cubic-bezier(0.16, 1, 0.3, 1);
}

.roles a:hover {
  border-top-color: var(--hmz-red);
  transform: translateY(-2px);
}

.roles a:hover::before {
  clip-path: polygon(0 100%, 0 30%, 100% 0, 100% 100%);
}

.roles .n {
  display: block;
  color: var(--hmz-red);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.roles strong {
  display: block;
  margin-top: 2px;
  color: var(--vp-c-text-1);
  font-size: 15px;
  font-weight: 700;
}

.roles strong::after {
  content: ' →';
  font-weight: 400;
}

.roles em {
  display: block;
  margin-top: 4px;
  color: var(--vp-c-text-3);
  font-size: 12.5px;
  font-style: normal;
  line-height: 1.5;
}

.under {
  margin: 26px 0 0;
  color: var(--vp-c-text-3);
  font-size: 12.5px;
}

/* The scroll cue: a chevron that says there is a page under this, and takes you to it. */
.cue {
  position: absolute;
  bottom: 22px;
  left: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  margin-left: -19px;
  color: var(--vp-c-text-3);
  animation: hmz-cue 2.4s ease-in-out infinite;
}

.cue:hover {
  color: var(--hmz-red);
}

.chev {
  width: 11px;
  height: 11px;
  border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: translateY(-2px) rotate(45deg);
}

@keyframes hmz-cue {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(5px);
  }
}

@media (prefers-reduced-motion: no-preference) {
  .pending .words,
  .pending .drawing {
    opacity: 0;
    animation: hmz-show 0.3s 2.5s forwards;
  }
}

@keyframes hmz-show {
  to {
    opacity: 1;
  }
}

@media (max-width: 959px) {
  .inner {
    grid-template-columns: minmax(0, 1fr);
  }

  /* The drawing goes over the words, smaller, and the words take the width. */
  .drawing {
    order: -1;
    max-width: 380px;
    justify-self: center;
  }
}

@media (max-width: 720px) {
  .hero {
    /* A phone screen is not tall enough to centre this and still show the cue. */
    min-height: 0;
    padding: 20px 20px 44px;
  }

  .drawing {
    max-width: 300px;
  }

  .line {
    padding-left: 12px;
    font-size: 11.5px;
  }

  .roles {
    grid-template-columns: minmax(0, 1fr);
  }

  .cue {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cursor,
  .line,
  .roles a,
  .roles a::before,
  .cue {
    animation: none;
    transition: none;
  }

  .line:hover,
  .roles a:hover {
    transform: none;
  }
}
</style>
