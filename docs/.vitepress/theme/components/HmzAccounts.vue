<script setup lang="ts">
// One agent's turn, carried down a fallback chain of places. A turn runs as an account, with
// every key the backend would read from the environment unset unless the account set it
// (`Profile.hushes` and `Profile.creds` in `src/hmz/coganchor/backends.py`). When the place
// fails, it is tried again inside the session that was running, and then the turn moves to the
// next place of the chain in a new conversation (`_falling_back` and `stands_in` in
// `src/hmz/coganchor/agents/base.py`): a rate limit gets at least one more try after at least
// 30 seconds, refused credentials move on at once and leave that account needing a new sign-in
// (`ANSWERS` in `src/hmz/coganchor/fallbacks.py`). The agent's next turn starts at the first
// place again, and carries on in the conversation the place that worked holds if it has to. The
// waits drawn are compressed.
import { computed, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { count, createFx, streak, type Fx } from '../motion/fx'
import { motion } from '../motion/gsap'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'
import ScenePlane from './scene/ScenePlane.vue'
import { drawPlane } from './scene/plane'

const BEATS = [
  'Each turn runs as an account',
  'Keys in your shell stay out',
  'Rate-limited: wait, retry, move on',
  'Key refused: next place at once',
  'A new conversation lands, and is kept',
]

const ACCOUNTS = [
  { name: 'claude@work/opus', kind: 'subscription', lane: 2 },
  { name: 'claude@key/opus', kind: 'API key', lane: 4 },
  { name: 'codex/gpt-5.6', kind: 'another CLI', lane: 3 },
]

interface Layout {
  w: number
  h: number
  card: { w: number; h: number }
  cards: { x: number; y: number }[]
  thread: { w: number; h: number }
  // Where the thread sits beside each card, top-left.
  seats: { x: number; y: number }[]
  shell: { x: number; y: number; w: number }
  vertical: boolean
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  card: { w: 150, h: 62 },
  cards: [
    { x: 55, y: 244 },
    { x: 245, y: 244 },
    { x: 435, y: 244 },
  ],
  thread: { w: 150, h: 128 },
  seats: [
    { x: 55, y: 84 },
    { x: 245, y: 84 },
    { x: 435, y: 84 },
  ],
  shell: { x: 432, y: 24, w: 186 },
  vertical: false,
}

const NARROW: Layout = {
  w: 360,
  h: 440,
  card: { w: 160, h: 60 },
  cards: [
    { x: 14, y: 128 },
    { x: 14, y: 226 },
    { x: 14, y: 324 },
  ],
  thread: { w: 150, h: 128 },
  seats: [
    { x: 196, y: 94 },
    { x: 196, y: 192 },
    { x: 196, y: 290 },
  ],
  shell: { x: 14, y: 22, w: 186 },
  vertical: true,
}

// The conversation: who said it, and under which account's lane an answer was made.
const ROW = 23
const BUBBLES = [
  { side: 'in', w: 0.62, lane: 0 },
  { side: 'out', w: 0.74, lane: 2 },
  { side: 'in', w: 0.48, lane: 0 },
  { side: 'out', w: 0.66, lane: 3 },
  { side: 'in', w: 0.54, lane: 0 },
]

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

// A link between two cards of the chain, and the tether from the thread to the card it runs as.
const links = computed(() => {
  const l = L.value
  return l.cards.slice(1).map((c, i) => {
    const a = l.cards[i]
    if (l.vertical) {
      const x = a.x + l.card.w / 2
      return `M${x} ${a.y + l.card.h + 5} L${x} ${c.y - 5}`
    }
    const y = a.y + l.card.h / 2
    return `M${a.x + l.card.w + 5} ${y} L${c.x - 5} ${y}`
  })
})
const tether = computed(() => {
  const l = L.value
  if (l.vertical) return `M0 ${l.thread.h / 2} L${l.cards[0].x + l.card.w - l.seats[0].x + 2} ${l.thread.h / 2}`
  return `M${l.thread.w / 2} ${l.thread.h} L${l.thread.w / 2} ${l.cards[0].y - l.seats[0].y - 2}`
})

const bubble = (i: number) => {
  const l = L.value
  const b = BUBBLES[i]
  const w = (l.thread.w - 28) * b.w
  return { x: b.side === 'in' ? 12 : l.thread.w - 12 - w, y: 32 + i * ROW, w, h: 15 }
}

const scene = useScene({
  still: 'rest',
  repeatDelay: 0.8,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const gsap = motion()
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const get = () => fx
    const one = (sel: string) => q(sel)[0]
    const W = l.w
    const H = l.h
    const shot = (s: number, px: number, py: number) => ({
      scale: s,
      xPercent: ((W / 2 - s * px) / W) * 100,
      yPercent: ((H / 2 - s * py) / H) * 100,
      transformOrigin: '0% 0%',
    })
    const cam = one('.cam')
    const card = q('.card')
    const halo = q('.card-halo')
    const thread = one('.thread')
    const bubbles = q('.bubble')
    const scroll = one('.scroll')
    const lit = q('.link-lit')
    const cc = (i: number) => ({ x: l.cards[i].x + l.card.w / 2, y: l.cards[i].y + l.card.h / 2 })
    const badgeAt = (i: number) => ({ x: l.cards[i].x + l.card.w - 26, y: l.cards[i].y })
    const move = (i: number) => ({ x: l.seats[i].x - l.seats[0].x, y: l.seats[i].y - l.seats[0].y })
    const threadC = (i: number) => ({ x: l.seats[i].x + l.thread.w / 2, y: l.seats[i].y + l.thread.h / 2 })
    const lane = (n: number) => () => palette.lane[n - 1]

    // Everything back to the first frame, so each loop starts clean.
    tl.set(cam, { autoAlpha: 1, ...shot(1.3, (cc(0).x + threadC(0).x) / 2, (cc(0).y + threadC(0).y) / 2) }, 0)
    tl.set(card, { autoAlpha: 0, y: 14 }, 0)
    tl.set(halo, { autoAlpha: 0 }, 0)
    tl.set(q('.link, .link-lit'), { drawSVG: '0%' }, 0)
    tl.set(thread, { autoAlpha: 0, x: 0, y: -18 }, 0)
    tl.set(one('.tether'), { drawSVG: '0%' }, 0)
    tl.set(bubbles, { autoAlpha: 0, scale: 0.4, transformOrigin: (i: number) => (BUBBLES[i].side === 'in' ? '0% 50%' : '100% 50%') }, 0)
    tl.set(scroll, { y: 0 }, 0)
    tl.set(q('.dots, .shell, .shield, .unset, .badge, .timer, .again, .next'), { autoAlpha: 0 }, 0)
    tl.set(q('.kind'), { autoAlpha: 1 }, 0)
    tl.set(one('.strike'), { drawSVG: '0%' }, 0)
    tl.set(one('.timer-fill'), { drawSVG: '0%' }, 0)
    tl.set(q('.b-times'), { autoAlpha: 0 }, 0)
    drawPlane(tl, q, 0, { duration: 2.2 })

    // ---------------------------------------------------------------- 0 · runs as an account
    tl.addLabel('beat-0', 0)
    tl.to(cam, { ...shot(1, W / 2, H / 2), duration: 2.8, ease: 'cine' }, 0.2)
    tl.to(card, { autoAlpha: 1, y: 0, duration: 0.7, stagger: 0.14, ease: 'cine.out' }, 0.2)
    tl.to(q('.link'), { drawSVG: '100%', duration: 0.5, stagger: 0.15, ease: 'cine' }, 0.8)
    tl.to(thread, { autoAlpha: 1, y: 0, duration: 0.8, ease: 'cine.out' }, 0.9)
    tl.to(one('.tether'), { drawSVG: '100%', duration: 0.5, ease: 'cine' }, 1.4)
    tl.to(halo[0], { autoAlpha: 1, duration: 0.6 }, 1.5)
    tl.call(() => fx?.spark(cc(0).x, l.vertical ? cc(0).y : l.cards[0].y, palette.lane[1], 16, 80), [], 1.8)
    tl.to(bubbles.slice(0, 2), { autoAlpha: 1, scale: 1, duration: 0.45, stagger: 0.3, ease: 'back.out(1.7)' }, 1.8)

    // ---------------------------------------------------------------- 1 · shell keys stay out
    const T1 = 3.3
    tl.addLabel('beat-1', T1)
    const key = one('.key')
    const keyFrom = { x: l.shell.x + 12, y: l.shell.y + 34 }
    const box = l.seats[0]
    // The point of the thread's frame nearest the shell, where the key is turned away.
    const hit = l.vertical ? { x: box.x - 20, y: box.y - 16 } : { x: box.x + l.thread.w + 8, y: box.y + 30 }
    tl.to(one('.shell'), { autoAlpha: 1, duration: 0.5 }, T1 + 0.1)
    tl.fromTo(key, { x: keyFrom.x, y: keyFrom.y, rotation: 0, autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3 }, T1 + 0.3)
    tl.to(key, { x: hit.x, y: hit.y, duration: 0.65, ease: 'power3.in' }, T1 + 0.9)
    tl.fromTo(one('.shield'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.08 }, T1 + 1.55)
    tl.to(one('.shield'), { autoAlpha: 0, duration: 0.9 }, T1 + 1.7)
    tl.call(() => fx?.spark(hit.x + (l.vertical ? 100 : 0), hit.y + 12, palette.lane[1], 26, 130), [], T1 + 1.55)
    const back = l.vertical ? { x: hit.x - 36, y: hit.y - 20 } : { x: hit.x + 44, y: hit.y - 22 }
    tl.to(key, { x: back.x, y: back.y, rotation: l.vertical ? -6 : 8, duration: 0.6, ease: 'power3.out' }, T1 + 1.55)
    tl.fromTo(thread, { x: 0 }, { keyframes: { x: [0, l.vertical ? 0 : -4, 0], y: [0, l.vertical ? 3 : 0, 0] }, duration: 0.3, ease: 'none', immediateRender: false }, T1 + 1.55)
    tl.to(one('.strike'), { drawSVG: '100%', duration: 0.25 }, T1 + 1.8)
    tl.fromTo(one('.unset'), { autoAlpha: 0, y: 4 }, { autoAlpha: 1, y: 0, duration: 0.35 }, T1 + 1.95)
    tl.to(q('.shell, .key'), { autoAlpha: 0, duration: 0.5 }, T1 + 2.9)
    tl.to(bubbles[2], { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(1.7)' }, T1 + 2.8)

    // ---------------------------------------------------------------- 2 · rate-limited
    const T2 = T1 + 3.5
    tl.addLabel('beat-2', T2)
    const f0 = { x: (cc(0).x + threadC(0).x) / 2, y: (cc(0).y + threadC(0).y) / 2 }
    tl.to(cam, { ...shot(l.vertical ? 1.12 : 1.4, f0.x, f0.y), duration: 1.3, ease: 'cine' }, T2)
    tl.fromTo(one('.dots'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3 }, T2 + 0.2)
    tl.fromTo(q('.dots circle'), { opacity: 0.25 }, { opacity: 1, duration: 0.35, stagger: 0.12, repeat: 11, yoyo: true, ease: 'sine.inOut' }, T2 + 0.2)
    const badge = q('.badge')
    const b429 = badge[0]
    tl.fromTo(b429, { autoAlpha: 0, scale: 1.8, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(2)' }, T2 + 0.9)
    tl.call(() => fx?.spark(badgeAt(0).x, badgeAt(0).y, palette.danger, 22, 110), [], T2 + 0.95)
    tl.fromTo(card[0], { x: 0 }, { keyframes: { x: [0, -4, 4, -2, 0] }, duration: 0.35, ease: 'none', immediateRender: false }, T2 + 0.95)
    // The wait: at least 30 seconds, drawn as a ring filling (compressed).
    const timer = one('.timer')
    tl.fromTo(timer, { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35 }, T2 + 1.3)
    tl.to(one('.timer-fill'), { drawSVG: '100%', duration: 1.6, ease: 'none' }, T2 + 1.5)
    count(tl, one('.timer-count'), 0, 30, T2 + 1.5, { duration: 1.6, ease: 'none', format: (n) => `${Math.round(n)}s` })
    // Try two: rate-limited again.
    tl.to(timer, { autoAlpha: 0, scale: 0.8, duration: 0.3 }, T2 + 3.2)
    // The same answer twice: the badge widens, the code steps aside, and the count arrives.
    tl.fromTo(one('.badge-pill'), { attr: { x: -24, width: 48 } }, { attr: { x: -31, width: 62 }, duration: 0.4, ease: 'cine' }, T2 + 3.3)
    tl.fromTo(one('.b-code'), { x: 0 }, { x: -9, duration: 0.4, ease: 'cine' }, T2 + 3.3)
    tl.fromTo(one('.b-times'), { autoAlpha: 0, x: 8 }, { autoAlpha: 1, x: 0, duration: 0.4, ease: 'cine' }, T2 + 3.35)
    tl.fromTo(b429, { scale: 1.3 }, { scale: 1, duration: 0.35, ease: 'back.out(2)', immediateRender: false }, T2 + 3.3)
    tl.call(() => fx?.spark(badgeAt(0).x, badgeAt(0).y, palette.danger, 22, 110), [], T2 + 3.35)
    // And on to the next place, in a conversation of its own: what was said is left behind.
    const M1 = T2 + 3.9
    const glide = (to: number, at: number, d: number) => {
      tl.to(
        thread,
        {
          x: move(to).x,
          y: move(to).y,
          duration: d,
          ease: 'cine',
          onUpdate() {
            const x = Number(gsap.getProperty(thread, 'x')) + threadC(0).x
            const y = Number(gsap.getProperty(thread, 'y')) + threadC(0).y
            fx?.trail(x, y + (l.vertical ? 0 : l.thread.h / 2), palette.lane[ACCOUNTS[to].lane - 1], 2.8)
          },
        },
        at,
      )
      tl.to(lit[to - 1], { drawSVG: '100%', duration: d * 0.8, ease: 'cine' }, at + 0.1)
      if (to === 1) tl.to(bubbles.slice(0, 3), { autoAlpha: 0.2, duration: 0.5 }, at + 0.2)
      tl.to(halo[to - 1], { autoAlpha: 0, duration: 0.4 }, at)
      tl.to(card[to - 1], { opacity: 0.45, duration: 0.6 }, at + 0.2)
      tl.to(halo[to], { autoAlpha: 1, duration: 0.6 }, at + d * 0.6)
      tl.call(() => fx?.spark(cc(to).x, l.vertical ? cc(to).y : l.cards[to].y, palette.lane[ACCOUNTS[to].lane - 1], 20, 100), [], at + d * 0.9)
    }
    tl.to(cam, { ...shot(l.vertical ? 1.1 : 1.3, (cc(1).x + threadC(1).x) / 2 - (l.vertical ? 0 : 40), (cc(1).y + threadC(1).y) / 2), duration: 1.2, ease: 'cine' }, M1)
    glide(1, M1, 1.1)

    // ---------------------------------------------------------------- 3 · key refused
    const T3 = M1 + 1.3
    tl.addLabel('beat-3', T3)
    const b401 = badge[1]
    tl.fromTo(b401, { autoAlpha: 0, scale: 1.8, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: 'back.out(2)' }, T3 + 0.35)
    tl.call(() => fx?.spark(badgeAt(1).x, badgeAt(1).y, palette.danger, 26, 120), [], T3 + 0.4)
    tl.fromTo(card[1], { x: 0 }, { keyframes: { x: [0, -4, 4, -2, 0] }, duration: 0.35, ease: 'none', immediateRender: false }, T3 + 0.4)
    tl.to(q('.kind')[1], { autoAlpha: 0, duration: 0.2 }, T3 + 0.6)
    tl.fromTo(one('.again'), { autoAlpha: 0, x: -6 }, { autoAlpha: 1, x: 0, duration: 0.35 }, T3 + 0.7)
    const M2 = T3 + 1.0
    tl.to(cam, { ...shot(l.vertical ? 1.08 : 1.22, (cc(2).x + threadC(2).x) / 2 - (l.vertical ? 0 : 60), (cc(2).y + threadC(2).y) / 2), duration: 1.0, ease: 'cine' }, M2)
    glide(2, M2, 0.8)

    // ---------------------------------------------------------------- 4 · lands, and stays
    const T4 = M2 + 1.1
    tl.addLabel('beat-4', T4)
    tl.to(one('.dots'), { autoAlpha: 0, duration: 0.2 }, T4 + 0.2)
    tl.to(bubbles[3], { autoAlpha: 1, scale: 1, duration: 0.5, ease: 'back.out(1.7)' }, T4 + 0.3)
    const bOk = badge[2]
    tl.fromTo(bOk, { autoAlpha: 0, scale: 1.8, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, T4 + 0.5)
    tl.call(() => fx?.spark(badgeAt(2).x, badgeAt(2).y, palette.accent, 34, 140), [], T4 + 0.55)
    tl.to(cam, { ...shot(1, W / 2, H / 2), duration: 1.4, ease: 'cine' }, T4 + 1.5)
    // The next turn, failing where it starts, carries on in the conversation that worked.
    const N = T4 + 2.4
    const next = one('.next')
    const nFrom = l.vertical ? { x: cc(0).x - 30, y: l.cards[0].y - 22 } : { x: l.cards[0].x - 6, y: l.cards[0].y + l.card.h + 26 }
    const nTo = l.vertical ? { x: cc(2).x - 30, y: l.cards[2].y + l.card.h + 20 } : { x: cc(2).x - 26, y: l.cards[2].y + l.card.h + 26 }
    tl.fromTo(next, { autoAlpha: 0, x: nFrom.x, y: nFrom.y, scale: 0.7 }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, N)
    if (l.vertical) {
      tl.to(next, { x: nFrom.x - 20, duration: 0.3, ease: 'power2.out' }, N + 0.5)
      tl.to(next, { y: nTo.y, duration: 1, ease: 'cine' }, N + 0.7)
      tl.to(next, { x: nTo.x, duration: 0.4, ease: 'power2.inOut' }, N + 1.5)
    } else {
      tl.to(next, { x: nTo.x, y: nTo.y, duration: 1.1, ease: 'cine' }, N + 0.5)
    }
    streak(tl, get, { x: nFrom.x + 26, y: nFrom.y }, { x: nTo.x + 26, y: nTo.y }, lane(3), N + 0.5, { duration: 1.1, bend: l.vertical ? 0.3 : -0.08, burst: 16 })
    tl.to(scroll, { y: -ROW, duration: 0.5, ease: 'cine' }, N + 1.7)
    tl.to(bubbles[4], { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(1.7)' }, N + 1.9)
    tl.addLabel('rest', N + 2.6)

    tl.to(cam, { autoAlpha: 0, ...shot(0.95, W / 2, H / 2), duration: 0.8, ease: 'power2.in' }, N + 4.4)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    sim
    mobile-ratio="9 / 11"
    label="One agent's turn and a fallback chain of three places: claude@work/opus, a subscription; claude@key/opus, an API key; codex/gpt-5.6, another CLI. The turn runs as claude@work, and the ANTHROPIC_API_KEY in your shell is unset for it. claude@work/opus is rate-limited, waits at least 30 seconds, is rate-limited again, and the turn moves to claude@key/opus in a new conversation. That key is refused, so it moves at once to codex/gpt-5.6, and claude@key needs signing in again. The turn lands on codex/gpt-5.6 in a new conversation, which is kept for the agent's next turn should it need it."
  >
    <div class="layer cam">
      <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
        <defs>
          <radialGradient v-for="n in [2, 3, 4]" :id="`hmz-accounts-halo-${n}`" :key="n">
            <stop offset="0" :stop-color="`var(--hmz-lane-${n})`" stop-opacity="0.5" />
            <stop offset="1" :stop-color="`var(--hmz-lane-${n})`" stop-opacity="0" />
          </radialGradient>
          <clipPath id="hmz-accounts-clip">
            <rect x="0" y="26" :width="L.thread.w" :height="L.thread.h - 30" />
          </clipPath>
        </defs>

        <ScenePlane :key="`plane-${narrow}`" :w="L.w" :h="L.h" :step="narrow ? 28 : 32" />

        <path v-for="(d, i) in links" :key="`l${i}`" class="link" :d="d" />
        <path v-for="(d, i) in links" :key="`k${i}`" class="link-lit" :class="`lane-${ACCOUNTS[i + 1].lane}`" :d="d" />

        <g v-for="(a, i) in ACCOUNTS" :key="a.name" :transform="`translate(${L.cards[i].x} ${L.cards[i].y})`">
          <ellipse class="card-halo" :cx="L.card.w / 2" :cy="L.card.h / 2" :rx="L.card.w * 0.9" :ry="L.card.h * 1.3" :fill="`url(#hmz-accounts-halo-${a.lane})`" />
          <g class="card" :class="`lane-${a.lane}`">
            <rect class="card-bg" :width="L.card.w" :height="L.card.h" rx="12" />
            <rect class="card-edge" x="0" y="10" width="3" :height="L.card.h - 20" rx="1.5" />
            <text class="name" x="14" y="26">{{ a.name }}</text>
            <text class="kind" x="14" y="45">{{ a.kind }}</text>
            <text v-if="i === 1" class="again" x="14" y="45">sign in again</text>
            <g v-if="i === 0" :transform="`translate(${L.card.w - 26} ${L.card.h / 2 + 6})`">
              <g class="timer">
                <circle class="timer-track" r="15" />
                <circle class="timer-fill" r="15" transform="rotate(-90)" />
                <text class="timer-count" y="4" text-anchor="middle">0s</text>
              </g>
            </g>
            <g :transform="`translate(${L.card.w - 26} 0)`">
              <g class="badge" :class="i === 2 ? 'ok' : 'bad'">
                <rect :class="{ 'badge-pill': i === 0 }" x="-24" y="-10" width="48" height="20" rx="10" />
                <g class="b-code"><text y="4" text-anchor="middle">{{ ['429', '401', '✓'][i] }}</text></g>
                <g v-if="i === 0" class="b-times"><text x="17" y="4" text-anchor="middle">×2</text></g>
              </g>
            </g>
          </g>
        </g>

        <g class="shell" :transform="`translate(${L.shell.x} ${L.shell.y})`">
          <rect class="shell-bg" :width="L.shell.w" height="54" rx="10" />
          <text class="shell-name" x="12" y="18">your shell</text>
        </g>

        <g :transform="`translate(${L.seats[0].x} ${L.seats[0].y})`">
          <g class="thread">
            <path class="tether" :d="tether" />
            <rect class="shield" x="-7" y="-7" :width="L.thread.w + 14" :height="L.thread.h + 14" rx="16" />
            <rect class="thread-bg" :width="L.thread.w" :height="L.thread.h" rx="12" />
            <text class="thread-name" x="12" y="18">conversation</text>
            <g clip-path="url(#hmz-accounts-clip)">
              <g class="scroll">
                <g v-for="(b, i) in BUBBLES" :key="i">
                  <rect class="bubble" :class="b.lane ? `lane-${b.lane}` : 'in'" :x="bubble(i).x" :y="bubble(i).y" :width="bubble(i).w" :height="bubble(i).h" rx="7.5" />
                </g>
                <g class="dots" :transform="`translate(${L.thread.w - 40} ${32 + 3 * ROW + 7.5})`">
                  <circle cx="0" r="3" />
                  <circle cx="10" r="3" />
                  <circle cx="20" r="3" />
                </g>
              </g>
            </g>
          </g>
        </g>

        <g class="key">
          <rect class="key-bg" x="0" y="-12" width="162" height="24" rx="7" />
          <text class="key-name" x="81" y="4" text-anchor="middle">ANTHROPIC_API_KEY</text>
          <line class="strike" x1="8" y1="0" x2="154" y2="0" />
          <text class="unset" x="81" y="30" text-anchor="middle">unset</text>
        </g>

        <g class="next">
          <rect x="0" y="-11" width="60" height="22" rx="11" />
          <text x="30" y="4" text-anchor="middle">turn 2</text>
        </g>
      </svg>
      <canvas ref="canvas" />
    </div>
  </HmzStage>
</template>

<style scoped>
.cam svg,
.cam canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.cam canvas {
  pointer-events: none;
}

svg {
  font-family: var(--vp-font-family-base);
}

.link {
  fill: none;
  stroke: var(--hmz-stage-line);
  stroke-width: 2;
  stroke-dasharray: 3 4;
}

.link-lit {
  fill: none;
  stroke-width: 2.5;
  stroke-linecap: round;
}

.link-lit.lane-4 { stroke: var(--hmz-lane-4); }
.link-lit.lane-3 { stroke: var(--hmz-lane-3); }

.card-halo {
  opacity: var(--hmz-glow);
}

.card-bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.card.lane-2 .card-edge { fill: var(--hmz-lane-2); }
.card.lane-4 .card-edge { fill: var(--hmz-lane-4); }
.card.lane-3 .card-edge { fill: var(--hmz-lane-3); }

.name {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.kind {
  font-size: 11.5px;
  fill: var(--hmz-stage-dim);
}

.again {
  font-size: 11.5px;
  font-weight: 650;
  fill: var(--hmz-lane-5);
}

.timer-track {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 3;
}

.timer-fill {
  fill: none;
  stroke: var(--hmz-lane-5);
  stroke-width: 3;
  stroke-linecap: round;
}

.timer-count {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.badge rect {
  stroke: none;
}

.badge.bad rect {
  fill: var(--hmz-lane-5);
}

.badge.ok rect {
  fill: var(--hmz-accent);
}

.badge text {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  font-weight: 700;
  fill: var(--vp-c-bg);
}

.shell-bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-dasharray: 3 3;
}

.shell-name,
.thread-name {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--hmz-stage-dim);
}

.thread-bg {
  fill: var(--hmz-stage-card);
  stroke: color-mix(in srgb, var(--hmz-lane-1) 50%, transparent);
  stroke-width: 1.4;
}

.tether {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
  stroke-dasharray: 2 4;
  stroke-linecap: round;
}

.shield {
  fill: color-mix(in srgb, var(--hmz-lane-2) 10%, transparent);
  stroke: var(--hmz-lane-2);
  stroke-width: 2.5;
}

.bubble.in {
  fill: color-mix(in srgb, var(--hmz-stage-dim) 30%, transparent);
}

.bubble.lane-2 { fill: var(--hmz-lane-2); }
.bubble.lane-3 { fill: var(--hmz-lane-3); }
.bubble.lane-4 { fill: var(--hmz-lane-4); }

.dots circle {
  fill: var(--hmz-stage-dim);
}

.key-bg {
  fill: color-mix(in srgb, var(--hmz-lane-5) 10%, var(--hmz-stage-card));
  stroke: color-mix(in srgb, var(--hmz-lane-5) 60%, transparent);
}

.key-name {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.strike {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
}

.unset {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  fill: var(--hmz-lane-5);
}

.next rect {
  fill: color-mix(in srgb, var(--hmz-lane-3) 18%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-3);
  stroke-width: 1.4;
}

.next text {
  font-size: 11.5px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}
</style>
