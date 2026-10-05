<script setup lang="ts">
// An agent, spelled and taken apart: `claude@work/claude-opus-5:high` is a backend (the CLI),
// an account (who its turns run as), a model (one that account offers) and an effort (a rung
// of that backend's own ladder). The models on offer are asked of the account, once, and kept
// (`src/hmz/coganchor/models.py`); a rung is checked against the backend's ladder before the
// run starts, and one that is not on it is refused. The ladders are the `_CLAUDE`, `_CODEX`, …
// tuples in `src/hmz/coganchor/backends.py`, hardest first; the refused word is always a rung
// of some other backend, never an invented one. Any CLI speaking ACP can be added as a backend
// of its own. The account name and the list around the model are illustrative.
import { computed, nextTick, onMounted, ref } from 'vue'

import HmzStage from '../motion/HmzStage.vue'
import { createFx, streak, type Fx } from '../motion/fx'
import { motion } from '../motion/gsap'
import { useNarrow } from '../motion/layout'
import { usePalette } from '../motion/palette'
import { useScene } from '../motion/useScene'
import ScenePlane from './scene/ScenePlane.vue'
import { drawPlane } from './scene/plane'

const BEATS = [
  'An agent is four parts',
  'The account is asked its models',
  'The effort is a rung of its ladder',
  'A rung off the ladder is refused',
  'Or any CLI speaking ACP',
]

interface Backend {
  name: string
  called: string
  model: string
  efforts: string[]
}

// A model each backend's docs and code name, and its ladder as `backends.py` writes it.
const BACKENDS: Backend[] = [
  { name: 'claude', called: 'Claude Code', model: 'claude-opus-5', efforts: ['ultracode', 'max', 'xhigh', 'high', 'medium', 'low'] },
  { name: 'codex', called: 'Codex', model: 'gpt-5.6-sol', efforts: ['ultra', 'max', 'xhigh', 'high', 'medium', 'low'] },
  { name: 'cursor-agent', called: 'Cursor Agent', model: 'gpt-5.2', efforts: ['max', 'xhigh', 'extra-high', 'high', 'medium', 'low', 'minimal', 'none'] },
  { name: 'dsh', called: 'DeepSeek Harness', model: 'deepseek-v4-pro', efforts: ['max', 'high', 'low', 'off'] },
  { name: 'grok', called: 'Grok Build', model: 'grok-4.6', efforts: ['xhigh', 'high', 'medium', 'low'] },
  { name: 'kimi', called: 'Kimi Code', model: 'kimi-code/k3', efforts: ['max', 'high', 'medium', 'low'] },
  { name: 'pi', called: 'pi', model: 'openai-codex/gpt-5.5', efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'minimal', 'off'] },
  { name: 'qwen', called: 'Qwen Code', model: 'qwen3-coder-plus', efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'none'] },
  { name: 'agy', called: 'Antigravity', model: 'gemini-3.7-flash', efforts: ['high', 'medium', 'low'] },
  { name: 'opencode', called: 'opencode', model: 'anthropic/claude-opus-5', efforts: ['xhigh', 'high', 'medium', 'low', 'minimal'] },
  { name: 'mcode', called: 'MiniMax Code', model: 'minimax/MiniMax-M3.1-Flash-Preview', efforts: ['max', 'xhigh', 'high', 'medium', 'low'] },
  { name: 'mimo', called: 'mimocode', model: 'xiaomi/mimo-v2.5', efforts: ['xhigh', 'high', 'medium', 'low', 'minimal'] },
]

// Every ladder above has it, so the climb always ends somewhere real.
const PICK = 'high'
// Rungs of other backends, tried in turn until one is not on this backend's ladder.
const STRAYS = ['ultra', 'off', 'ultracode', 'minimal']
const ROLES = ['backend', 'account', 'model', 'effort']
const ACCOUNT = 'work'

const chosen = ref('claude')
const B = computed(() => BACKENDS.find((one) => one.name === chosen.value) ?? BACKENDS[0])
const parts = computed(() => [B.value.name, `@${ACCOUNT}`, `/${B.value.model}`, `:${PICK}`])
const stray = computed(() => STRAYS.find((one) => !B.value.efforts.includes(one)) ?? 'ultra')
const picked = computed(() => B.value.efforts.indexOf(PICK))

interface Layout {
  w: number
  h: number
  fs: number
  gap: number
  lineY: number
  rows: number[][]
  rowY: number[]
  list: { x: number; y: number; w: number }
  ladder: { x: number; y: number; w: number; h: number; step: number }
  stray: { x: number; y: number }
  reel: { x: number; y: number }
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  fs: 20,
  gap: 30,
  lineY: 150,
  rows: [[0, 1, 2, 3]],
  rowY: [86],
  list: { x: 150, y: 164, w: 230 },
  ladder: { x: 452, y: 170, w: 150, h: 18, step: 21 },
  stray: { x: 340, y: 250 },
  reel: { x: 320, y: 236 },
}

const NARROW: Layout = {
  w: 360,
  h: 440,
  fs: 16,
  gap: 26,
  lineY: 150,
  rows: [
    [0, 1],
    [2, 3],
  ],
  rowY: [70, 146],
  list: { x: 14, y: 206, w: 168 },
  ladder: { x: 200, y: 222, w: 144, h: 17, step: 20 },
  stray: { x: 72, y: 396 },
  reel: { x: 180, y: 300 },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))
const ROW_H = 22
const LIST_ROWS = 4
const LIST_AT = 1

// Faint backend names far behind the scene, drifting slower than the camera: depth.
const FAR = computed(() => {
  const l = L.value
  const n = BACKENDS.length
  return BACKENDS.map((one, i) => {
    const a = (i / n) * Math.PI * 2 + 0.35
    const k = 1 + (((i * 7) % 5) - 2) * 0.035
    return {
      name: one.name,
      x: l.w / 2 + Math.cos(a) * l.w * 0.4 * k,
      y: l.h / 2 + Math.sin(a) * l.h * 0.4 * k,
      s: 12 + ((i * 5) % 4) * 2,
    }
  })
})

const label = computed(
  () =>
    `An agent spelled ${parts.value.join('')}: the backend ${B.value.name} (${B.value.called}), the account ${ACCOUNT}, the model ${B.value.model}, the effort ${PICK}. ` +
    `The account is asked which models it offers. ${B.value.called}'s efforts, hardest first: ${B.value.efforts.join(', ')}; ${PICK} is picked. ` +
    `${stray.value}, a rung of another backend, is not on this ladder and is refused before the run starts. Any CLI speaking ACP can be added as a backend too.`,
)

function pick(name: string) {
  if (name === chosen.value) return
  chosen.value = name
  void nextTick(() => {
    scene.rebuild()
    if (!(scene.reduced.value && !scene.playing.value)) scene.seek(2)
  })
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

    // Camera: centre the world point (fx, fy) at scale s. It moves the SVG and the canvas of
    // light together, so sparks land where they are drawn.
    const shot = (s: number, px: number, py: number) => ({
      scale: s,
      xPercent: ((W / 2 - s * px) / W) * 100,
      yPercent: ((H / 2 - s * py) / H) * 100,
      transformOrigin: '0% 0%',
    })
    const cam = one('.cam')
    const far = one('.far')

    // Where the four parts sit, measured rather than guessed: typed as one line first, then
    // pulled apart into chips.
    const toks = q('.tok') as SVGTextElement[]
    const texts = parts.value
    toks.forEach((t, i) => (t.textContent = texts[i]))
    const widths = toks.map((t) => t.getComputedTextLength() || texts[toks.indexOf(t)].length * l.fs * 0.6)
    const total = widths.reduce((a, b) => a + b, 0)
    const fit = Math.min(1, (W - 36) / total)
    const line: { x: number; y: number }[] = []
    let run = W / 2 - total / 2
    widths.forEach((w) => {
      line.push({ x: run, y: l.lineY })
      run += w
    })
    const spread: { x: number; y: number }[] = []
    l.rows.forEach((row, r) => {
      const rw = row.reduce((a, i) => a + widths[i], 0) + l.gap * (row.length - 1)
      let x = W / 2 - rw / 2
      row.forEach((i) => {
        spread[i] = { x, y: l.rowY[r] }
        x += widths[i] + l.gap
      })
    })
    const part = q('.part')
    const focus = (on: number[], at: number) =>
      part.forEach((p, i) => tl.to(p, { opacity: on.includes(i) ? 1 : 0.35, duration: 0.5 }, at))
    const centre = (i: number) => ({ x: spread[i].x + widths[i] / 2, y: spread[i].y - l.fs * 0.3 })

    const bg = q('.chip-bg')
    const under = q('.under')
    const role = q('.role')
    part.forEach((p, i) => {
      tl.set(bg[i], { attr: { width: widths[i] + 18 } }, 0)
      tl.set(under[i], { attr: { x2: widths[i] } }, 0)
      tl.set(role[i], { attr: { x: widths[i] / 2 } }, 0)
    })

    // ---------------------------------------------------------------- 0 · four parts
    tl.addLabel('beat-0', 0)
    tl.set(cam, { autoAlpha: 1, ...shot(1.25, W / 2, l.lineY) }, 0)
    tl.set(far, { scale: 1.08, x: 0, y: 0, transformOrigin: '50% 50%' }, 0)
    tl.set(one('.spell'), { scale: fit, svgOrigin: `${W / 2} ${l.lineY}` }, 0)
    part.forEach((p, i) => tl.set(p, { x: line[i].x, y: line[i].y, autoAlpha: 1, scale: 1, opacity: 1 }, 0))
    tl.set(toks, { text: '' }, 0)
    tl.set(bg, { autoAlpha: 0 }, 0)
    tl.set(under, { drawSVG: '0%' }, 0)
    tl.set(q('.role-in'), { autoAlpha: 0, y: -6 }, 0)
    tl.set(q('.list, .ladder, .stray, .reel-card, .reel-acp, .stray-word, .refused, .ghost'), { autoAlpha: 0 }, 0)
    drawPlane(tl, q, 0, { duration: 2.4 })

    // A word that becomes a part: it lifts off where it is written -- the account's list, the
    // ladder -- and flies to its place in the spelling, growing to the spelling's size, while
    // the part it lands in takes it up. The copy is two groups, one moved and one scaled about
    // the word's own baseline, so the one never drags the other.
    function become(ghost: Element, from: { x: number; y: number }, to: { x: number; y: number }, size: number, at: number) {
      const scale = ghost.querySelector('.ghost-scale')!
      const k = l.fs / size
      tl.set(ghost, { x: from.x, y: from.y }, 0)
      tl.set(scale, { scale: 1, svgOrigin: '0 0' }, 0)
      tl.to(ghost, { autoAlpha: 1, duration: 0.15 }, at)
      tl.to(ghost, { x: to.x, y: to.y, duration: 0.8, ease: 'cine' }, at)
      tl.to(scale, { scale: k, duration: 0.8, ease: 'cine' }, at)
      tl.to(ghost, { autoAlpha: 0, duration: 0.25 }, at + 0.75)
    }
    tl.set(one('.caret'), { autoAlpha: 1, x: line[0].x }, 0)

    tl.to(cam, { ...shot(1.12, W / 2, l.lineY), duration: 2.2, ease: 'none' }, 0)
    let t = 0.35
    toks.forEach((tok, i) => {
      const d = texts[i].length / 26
      tl.to(tok, { text: { value: texts[i] }, duration: d, ease: 'none' }, t)
      tl.fromTo(one('.caret'), { x: line[i].x }, { x: line[i].x + widths[i], duration: d, ease: 'none' }, t)
      t += d + 0.06
    })
    tl.to(one('.caret'), { autoAlpha: 0, duration: 0.15, repeat: 3, yoyo: true, ease: 'none' }, t)
    tl.set(one('.caret'), { autoAlpha: 0 }, t + 0.6)

    // The split: anticipation (a squeeze), then the parts fly to their places.
    const S = t + 0.5
    tl.to(part, { scale: 0.94, duration: 0.25, ease: 'power2.in', transformOrigin: '50% 50%' }, S)
    tl.to(cam, { ...shot(1, W / 2, H / 2), duration: 1.3, ease: 'cine' }, S)
    tl.to(one('.spell'), { scale: 1, duration: 1.1, ease: 'cine' }, S + 0.2)
    part.forEach((p, i) => {
      tl.to(p, { x: spread[i].x, y: spread[i].y, scale: 1, duration: 1.1, ease: 'cine' }, S + 0.2 + i * 0.07)
    })
    tl.to(bg, { autoAlpha: 1, duration: 0.5, stagger: 0.08 }, S + 0.9)
    tl.to(under, { drawSVG: '100%', duration: 0.6, stagger: 0.08, ease: 'cine' }, S + 0.95)
    tl.to(q('.role-in'), { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.08 }, S + 1.05)
    ;[0, 1, 2, 3].forEach((i) => {
      tl.call(() => fx?.spark(centre(i).x, centre(i).y, palette.lane[i], 12, 70), [], S + 1.1 + i * 0.08)
    })

    // ---------------------------------------------------------------- 1 · the account's models
    const T1 = S + 2.3
    tl.addLabel('beat-1', T1)
    const L1 = { x: (centre(1).x + l.list.x + l.list.w / 2) / 2, y: (l.rowY[0] + l.list.y + 70) / 2 + 10 }
    tl.to(cam, { ...shot(narrow.value ? 1.08 : 1.18, L1.x, L1.y), duration: 1.4, ease: 'cine' }, T1)
    tl.to(far, { x: -12, y: -6, duration: 1.8, ease: 'cine' }, T1)
    focus([1, 2], T1)
    tl.set(one('.list'), { autoAlpha: 1 }, T1 + 0.3)
    tl.fromTo(one('.list-frame'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, ease: 'cine' }, T1 + 0.4)
    tl.fromTo(one('.list-head'), { autoAlpha: 0, x: -8 }, { autoAlpha: 1, x: 0, duration: 0.5 }, T1 + 0.6)
    streak(tl, get, centre(1), { x: l.list.x + 20, y: l.list.y + 16 }, () => palette.lane[1], T1 + 0.2, { duration: 0.8, bend: 0.3, burst: 10 })
    tl.fromTo(q('.list-row'), { scaleX: 0, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 0.5, stagger: 0.12, ease: 'cine.out' }, T1 + 0.8)
    tl.fromTo(one('.list-hit'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4 }, T1 + 1.5)
    tl.fromTo(one('.list-model'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3 }, T1 + 1.4)
    const hitY = l.list.y + 34 + LIST_AT * (ROW_H + 6) + ROW_H / 2
    streak(tl, get, { x: l.list.x + l.list.w - 24, y: hitY }, centre(2), () => palette.lane[2], T1 + 1.8, { duration: 0.8, bend: -0.35, burst: 14 })
    const slash = widths[2] / texts[2].length
    become(one('.ghost-model'), { x: l.list.x + 22, y: l.list.y + 34 + LIST_AT * (ROW_H + 6) + 15 }, { x: spread[2].x + slash, y: spread[2].y }, 12, T1 + 1.75)
    tl.to(part[2], { scale: 1.1, duration: 0.2, ease: 'power2.out' }, T1 + 2.55)
    tl.to(part[2], { scale: 1, duration: 0.6, ease: 'elastic.out(1, 0.5)' }, T1 + 2.75)

    // ---------------------------------------------------------------- 2 · the ladder
    const T2 = T1 + 3.2
    tl.addLabel('beat-2', T2)
    const lad = l.ladder
    const n = B.value.efforts.length
    const ladH = n * lad.step
    const L2 = narrow.value ? { x: W / 2, y: H / 2 } : { x: (centre(3).x + lad.x + lad.w / 2) / 2 - 30, y: (l.rowY[0] + lad.y + ladH) / 2 + 6 }
    tl.to(cam, { ...shot(narrow.value ? 1 : 1.12, L2.x, L2.y), duration: 1.4, ease: 'cine' }, T2)
    tl.to(far, { x: -24, y: -14, duration: 1.8, ease: 'cine' }, T2)
    tl.to(one('.list'), { autoAlpha: 0.3, duration: 0.6 }, T2)
    focus([3], T2)
    tl.set(one('.ladder'), { autoAlpha: 1 }, T2 + 0.3)
    tl.fromTo(one('.ladder-head'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.5 }, T2 + 0.3)
    const rungs = q('.rung')
    tl.fromTo(
      [...rungs].reverse(),
      { autoAlpha: 0, x: 26 },
      { autoAlpha: 1, x: 0, duration: 0.45, stagger: 0.07, ease: 'cine.out' },
      T2 + 0.45,
    )
    tl.set(q('.rung-lit'), { autoAlpha: 0 }, 0)
    // A light climbs from the lowest rung to the one picked.
    const climber = one('.climber')
    const from = (n - 1) * lad.step
    const to = picked.value * lad.step
    const C0 = T2 + 0.6 + n * 0.07
    tl.fromTo(climber, { autoAlpha: 0, y: from }, { autoAlpha: 1, duration: 0.2 }, C0)
    tl.to(
      climber,
      {
        y: to,
        duration: 0.35 + (n - 1 - picked.value) * 0.18,
        ease: 'power2.inOut',
        onUpdate() {
          const y = Number(gsap.getProperty(climber, 'y'))
          fx?.trail(lad.x + 6, lad.y + y + lad.h / 2, palette.lane[3], 2.6)
          fx?.trail(lad.x + lad.w - 6, lad.y + y + lad.h / 2, palette.lane[3], 2.6)
        },
      },
      C0 + 0.15,
    )
    const lock = C0 + 0.6 + (n - 1 - picked.value) * 0.18
    tl.to(q('.rung-lit')[picked.value], { autoAlpha: 1, duration: 0.25 }, lock)
    tl.to(climber, { autoAlpha: 0, duration: 0.4 }, lock + 0.1)
    tl.fromTo(rungs[picked.value], { scale: 1 }, { scale: 1.08, duration: 0.18, yoyo: true, repeat: 1, transformOrigin: '50% 50%', ease: 'power2.out' }, lock)
    const rungC = { x: lad.x + lad.w / 2, y: lad.y + picked.value * lad.step + lad.h / 2 }
    tl.call(() => fx?.spark(rungC.x, rungC.y, palette.lane[3], 22, 110), [], lock)
    streak(tl, get, { x: lad.x + lad.w / 2, y: rungC.y - 4 }, centre(3), () => palette.lane[3], lock + 0.35, { duration: 0.8, bend: 0.3, burst: 14 })
    const rungWord = (q('.ghost-effort text')[0] as SVGTextElement).getComputedTextLength() || PICK.length * 7
    const colon = widths[3] / texts[3].length
    become(one('.ghost-effort'), { x: rungC.x - rungWord / 2, y: rungC.y + 4 }, { x: spread[3].x + colon, y: spread[3].y }, 11.5, lock + 0.3)
    tl.to(part[3], { scale: 1.12, duration: 0.2, ease: 'power2.out' }, lock + 1.1)
    tl.to(part[3], { scale: 1, duration: 0.6, ease: 'elastic.out(1, 0.5)' }, lock + 1.3)

    // ---------------------------------------------------------------- 3 · off the ladder
    const T3 = lock + 1.9
    tl.addLabel('beat-3', T3)
    const s0 = l.stray
    const hitX = lad.x - 6
    tl.to(one('.list'), { autoAlpha: 0, duration: 0.4 }, T3)
    tl.set(one('.stray'), { autoAlpha: 1, x: s0.x, y: s0.y, rotation: 0, scale: 1 }, T3)
    tl.fromTo(one('.stray-word'), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(2)' }, T3 + 0.1)
    const strayW = narrow.value ? 0 : 1
    // Wide: it rushes the ladder from the side. Narrow: it rises at it from below.
    const hit = narrow.value ? { x: lad.x - 40, y: lad.y + ladH - 4 } : { x: hitX - 40, y: s0.y }
    tl.to(one('.stray'), { x: hit.x, y: hit.y, duration: 0.55, ease: 'power3.in' }, T3 + 0.7)
    tl.to(one('.ladder-alarm'), { autoAlpha: 1, duration: 0.12 }, T3 + 1.25)
    tl.to(one('.ladder-alarm'), { autoAlpha: 0, duration: 0.9 }, T3 + 1.5)
    tl.call(() => fx?.spark(hit.x + 38, hit.y, palette.danger, 30, 150), [], T3 + 1.25)
    tl.to(one('.stray'), { x: hit.x - 50 - strayW * 20, y: hit.y + 16, rotation: -10, duration: 0.7, ease: 'power3.out' }, T3 + 1.25)
    tl.fromTo(one('.ladder'), { x: 0 }, { keyframes: { x: [0, 5, -4, 3, -2, 0] }, duration: 0.4, ease: 'none' }, T3 + 1.25)
    tl.fromTo(q('.stray-cross'), { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.2, stagger: 0.08 }, T3 + 1.45)
    tl.fromTo(one('.refused'), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.4 }, T3 + 1.6)
    tl.addLabel('rest', T3 + 2.4)

    // ---------------------------------------------------------------- 4 · any ACP CLI
    const T4 = T3 + 3
    tl.addLabel('beat-4', T4)
    tl.to(cam, { ...shot(1, W / 2, H / 2), duration: 1.3, ease: 'cine' }, T4)
    tl.to(far, { x: 0, y: 0, scale: 1, duration: 2.4, ease: 'cine' }, T4)
    tl.to(q('.ladder, .stray'), { autoAlpha: 0, duration: 0.5 }, T4)
    focus([0], T4)
    const reel = one('.reel')
    const farText = q('.far text')
    // Wide: straight down from the backend chip. Narrow: round the left of the chips below it.
    const cardTop = narrow.value ? { x: l.reel.x - 110, y: l.reel.y - 9 } : { x: l.reel.x, y: l.reel.y - 36 }
    const from0 = narrow.value ? { x: spread[0].x - 9, y: spread[0].y - 6 } : { x: centre(0).x, y: spread[0].y + l.fs + 28 }
    const midY = (from0.y + cardTop.y) / 2
    const wire = narrow.value
      ? `M${from0.x} ${from0.y} C${from0.x - 70} ${from0.y} ${cardTop.x - 50} ${cardTop.y} ${cardTop.x} ${cardTop.y}`
      : `M${from0.x} ${from0.y} C${from0.x} ${midY} ${cardTop.x} ${midY} ${cardTop.x} ${cardTop.y}`
    tl.set(one('.reel-wire'), { attr: { d: wire }, drawSVG: '0%' }, 0)
    tl.set(farText, { opacity: 0.06 }, 0)
    tl.to(one('.reel-wire'), { drawSVG: '100%', duration: 0.8, ease: 'cine' }, T4 + 0.3)
    tl.fromTo(one('.reel-card'), { autoAlpha: 0, scale: 0.8, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.5, ease: 'back.out(1.6)' }, T4 + 0.8)
    const names = BACKENDS.map((b) => b.name)
    const start = names.indexOf(B.value.name)
    const order = [...names.slice(start), ...names.slice(0, start), B.value.name]
    streak(tl, get, from0, cardTop, () => palette.lane[0], T4 + 0.3, { duration: 0.8, bend: narrow.value ? 0.35 : 0.1, burst: 12 })
    tl.set(reel, { text: order[0] }, T4 + 0.8)
    let rt = T4 + 1.2
    order.slice(1).forEach((name, i) => {
      const gapT = 0.09 + Math.abs(i - order.length / 2) * 0.012
      rt += gapT
      tl.set(reel, { text: name }, rt)
      tl.fromTo(reel, { y: -6, opacity: 0.5 }, { y: 0, opacity: 1, duration: gapT, ease: 'none' }, rt)
      const star = farText[BACKENDS.findIndex((b) => b.name === name)]
      if (star) tl.fromTo(star, { opacity: 0.35 }, { opacity: 0.06, duration: 1.2, ease: 'power2.out', immediateRender: false }, rt)
    })
    const A = rt + 0.35
    tl.to(one('.reel-card'), { autoAlpha: 0, scale: 0.9, duration: 0.3, ease: 'power2.in' }, A)
    tl.to(farText, { opacity: 0.3, duration: 0.25, stagger: 0.03, yoyo: true, repeat: 1, ease: 'power1.inOut' }, A)
    tl.fromTo(one('.reel-acp'), { autoAlpha: 0, scale: 1.4, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.6, ease: 'back.out(1.8)' }, A + 0.2)
    tl.call(() => fx?.spark(l.reel.x, l.reel.y - 8, palette.accent2, 40, 150), [], A + 0.3)

    // Out: the world falls away so the loop's seam is not seen.
    tl.to(cam, { autoAlpha: 0, ...shot(0.94, W / 2, H / 2), duration: 0.8, ease: 'power2.in' }, A + 2.6)
  },
})

onMounted(() => {
  // The parts are measured in the page's own mono font: measure again once it has loaded.
  void document.fonts?.ready.then(() => scene.rebuild())
})
</script>

<template>
  <div class="hmz-backends">
    <div class="pick" role="group" aria-label="Pick a backend to see its ladder of efforts">
      <button
        v-for="one in BACKENDS"
        :key="one.name"
        type="button"
        :title="one.called"
        :aria-pressed="chosen === one.name"
        :class="{ on: chosen === one.name }"
        @click="pick(one.name)"
      >
        {{ one.name }}
      </button>
    </div>
    <HmzStage :scene="scene" :beats="BEATS" :label="label" sim mobile-ratio="9 / 11">
      <div class="layer far" aria-hidden="true">
        <svg :viewBox="`0 0 ${L.w} ${L.h}`">
          <text v-for="f in FAR" :key="f.name" :x="f.x" :y="f.y" :font-size="f.s" text-anchor="middle">{{ f.name }}</text>
        </svg>
      </div>
      <div class="layer cam">
        <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
          <ScenePlane :key="`plane-${narrow}`" :w="L.w" :h="L.h" :step="narrow ? 28 : 32" />
          <defs>
            <radialGradient id="hmz-backends-glow">
              <stop offset="0" stop-color="var(--hmz-accent-2)" stop-opacity="0.6" />
              <stop offset="1" stop-color="var(--hmz-accent-2)" stop-opacity="0" />
            </radialGradient>
            <linearGradient id="hmz-backends-climb" x1="0" x2="1">
              <stop offset="0" stop-color="var(--hmz-lane-4)" stop-opacity="0" />
              <stop offset="0.5" stop-color="var(--hmz-lane-4)" stop-opacity="0.6" />
              <stop offset="1" stop-color="var(--hmz-lane-4)" stop-opacity="0" />
            </linearGradient>
          </defs>

          <g class="list" :transform="`translate(${L.list.x} ${L.list.y})`">
            <rect class="list-frame" x="0" y="0" :width="L.list.w" :height="34 + LIST_ROWS * (ROW_H + 6) + 4" rx="12" />
            <g class="list-head">
              <text class="head" x="14" y="22">@{{ ACCOUNT }}</text>
              <text class="head dim" :x="L.list.w - 14" y="22" text-anchor="end">models</text>
            </g>
            <g v-for="r in LIST_ROWS" :key="r">
              <rect
                class="list-row"
                :class="{ hit: r - 1 === LIST_AT }"
                x="12"
                :y="34 + (r - 1) * (ROW_H + 6)"
                :width="r - 1 === LIST_AT ? L.list.w - 24 : (L.list.w - 24) * [0.62, 1, 0.78, 0.5][r - 1]"
                :height="ROW_H"
                rx="6"
              />
            </g>
            <rect class="list-hit" x="12" :y="34 + LIST_AT * (ROW_H + 6)" :width="L.list.w - 24" :height="ROW_H" rx="6" />
            <text
              class="list-model"
              x="22"
              :y="34 + LIST_AT * (ROW_H + 6) + 15"
              :textLength="B.model.length * 7.3 > L.list.w - 46 ? L.list.w - 46 : undefined"
              lengthAdjust="spacingAndGlyphs"
            >{{ B.model }}</text>
          </g>

          <g class="ladder">
            <rect class="ladder-alarm" :x="L.ladder.x - 6" :y="L.ladder.y - 6" :width="L.ladder.w + 12" :height="B.efforts.length * L.ladder.step + 9" rx="10" />
            <text class="head ladder-head" :x="L.ladder.x + 2" :y="L.ladder.y - 12">{{ B.name }} · efforts</text>
            <g v-for="(e, i) in B.efforts" :key="`${B.name}-${e}`" class="rung">
              <rect class="rung-bg" :x="L.ladder.x" :y="L.ladder.y + i * L.ladder.step" :width="L.ladder.w" :height="L.ladder.h" rx="5" />
              <text class="rung-word" :x="L.ladder.x + L.ladder.w / 2" :y="L.ladder.y + i * L.ladder.step + L.ladder.h / 2 + 4" text-anchor="middle">{{ e }}</text>
              <g class="rung-lit">
                <rect :x="L.ladder.x" :y="L.ladder.y + i * L.ladder.step" :width="L.ladder.w" :height="L.ladder.h" rx="5" />
                <text class="rung-word" :x="L.ladder.x + L.ladder.w / 2" :y="L.ladder.y + i * L.ladder.step + L.ladder.h / 2 + 4" text-anchor="middle">{{ e }}</text>
              </g>
            </g>
            <rect class="climber" :x="L.ladder.x - 10" :y="L.ladder.y - 3" :width="L.ladder.w + 20" :height="L.ladder.h + 6" rx="7" fill="url(#hmz-backends-climb)" />
          </g>

          <g class="stray">
            <g class="stray-word">
              <rect x="-38" y="-14" width="76" height="28" rx="8" />
              <text y="5" text-anchor="middle">{{ stray }}</text>
              <line class="stray-cross" x1="-30" y1="0" x2="30" y2="0" />
            </g>
            <g class="refused"><text y="32" text-anchor="middle">refused</text></g>
          </g>

          <path class="reel-wire" d="M0 0" />
          <g class="reel-card">
            <rect :x="L.reel.x - 110" :y="L.reel.y - 36" width="220" height="54" rx="14" />
            <text class="reel" :x="L.reel.x" :y="L.reel.y" text-anchor="middle">{{ B.name }}</text>
          </g>
          <g class="reel-acp">
            <circle :cx="L.reel.x" :cy="L.reel.y - 9" :r="narrow ? 90 : 120" fill="url(#hmz-backends-glow)" class="halo" />
            <rect :x="L.reel.x - 110" :y="L.reel.y - 36" width="220" height="54" rx="14" />
            <text class="reel-word" :x="L.reel.x" :y="L.reel.y" text-anchor="middle">any ACP CLI</text>
          </g>

          <g class="ghost ghost-model"><g class="ghost-scale"><text class="ghost-word model">{{ B.model }}</text></g></g>
          <g class="ghost ghost-effort"><g class="ghost-scale"><text class="ghost-word effort">{{ PICK }}</text></g></g>

          <g class="spell">
            <g v-for="(p, i) in parts" :key="i" class="part" :class="`lane-${i + 1}`">
              <rect class="chip-bg" x="-9" :y="-L.fs - 5" width="10" :height="L.fs + 16" rx="9" />
              <text class="tok" :font-size="L.fs">{{ p }}</text>
              <line class="under" x1="0" :y1="L.fs * 0.35 + 4" x2="10" :y2="L.fs * 0.35 + 4" />
              <g class="role-in"><text class="role" x="0" :y="L.fs + 20" text-anchor="middle">{{ ROLES[i] }}</text></g>
            </g>
            <rect class="caret" x="1" :y="L.lineY - L.fs + 1" width="2" :height="L.fs + 3" />
          </g>
        </svg>
        <canvas ref="canvas" />
      </div>
    </HmzStage>
  </div>
</template>

<style scoped>
.pick {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 22px 0 0;
}

.pick button {
  padding: 3px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--vp-c-text-2);
  background: transparent;
  transition: color 0.2s, border-color 0.2s, background 0.2s;
}

.pick button:hover,
.pick button:focus-visible {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-text-1);
}

.pick button.on {
  border-color: var(--hmz-lane-1);
  color: var(--vp-c-text-1);
  background: color-mix(in srgb, var(--hmz-lane-1) 16%, transparent);
}

.hmz-backends :deep(.hmz-stage) {
  margin-top: 12px;
}

/* Past its edges, so the paper under it is still there when the camera pulls back. */
.cam svg {
  overflow: visible;
}

.cam svg,
.cam canvas,
.far svg {
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

.far text {
  font-family: var(--vp-font-family-mono);
  font-weight: 600;
  fill: var(--hmz-stage-ink);
  opacity: 0.06;
}

.far {
  filter: blur(1.2px);
}

.reel-wire {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 1.5;
  stroke-dasharray: 4 4;
}

.reel-card rect {
  fill: color-mix(in srgb, var(--hmz-lane-1) 12%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-1);
  stroke-width: 1.5;
}

.reel-acp rect {
  fill: color-mix(in srgb, var(--hmz-accent-2) 16%, var(--hmz-stage-card));
  stroke: var(--hmz-accent-2);
  stroke-width: 2;
}

.tok {
  font-family: var(--vp-font-family-mono);
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.chip-bg {
  stroke-width: 1.2;
}

.under {
  stroke-width: 2.5;
  stroke-linecap: round;
}

/* Above 11px: the world falls away at the end of the loop, and they shrink with it while it fades. */
.role {
  font-size: 11.5px;
  font-weight: 650;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.lane-1 .chip-bg { fill: color-mix(in srgb, var(--hmz-lane-1) 14%, var(--hmz-stage-card)); stroke: color-mix(in srgb, var(--hmz-lane-1) 55%, transparent); }
.lane-2 .chip-bg { fill: color-mix(in srgb, var(--hmz-lane-2) 14%, var(--hmz-stage-card)); stroke: color-mix(in srgb, var(--hmz-lane-2) 55%, transparent); }
.lane-3 .chip-bg { fill: color-mix(in srgb, var(--hmz-lane-3) 14%, var(--hmz-stage-card)); stroke: color-mix(in srgb, var(--hmz-lane-3) 55%, transparent); }
.lane-4 .chip-bg { fill: color-mix(in srgb, var(--hmz-lane-4) 14%, var(--hmz-stage-card)); stroke: color-mix(in srgb, var(--hmz-lane-4) 55%, transparent); }
.lane-1 .under { stroke: var(--hmz-lane-1); }
.lane-2 .under { stroke: var(--hmz-lane-2); }
.lane-3 .under { stroke: var(--hmz-lane-3); }
.lane-4 .under { stroke: var(--hmz-lane-4); }
.lane-1 .role { fill: var(--hmz-lane-1); }
.lane-2 .role { fill: var(--hmz-lane-2); }
.lane-3 .role { fill: var(--hmz-lane-3); }
.lane-4 .role { fill: var(--hmz-lane-4); }

.caret {
  fill: var(--hmz-accent);
}

.head {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 650;
  fill: var(--hmz-lane-2);
}

.head.dim,
.ladder-head {
  fill: var(--hmz-stage-dim);
  letter-spacing: 0.04em;
}

.list-frame {
  fill: var(--hmz-stage-card);
  stroke: color-mix(in srgb, var(--hmz-lane-2) 55%, transparent);
  stroke-width: 1.2;
}

.list-row {
  fill: var(--hmz-stage-line);
}

.list-hit {
  fill: color-mix(in srgb, var(--hmz-lane-3) 22%, transparent);
  stroke: var(--hmz-lane-3);
  stroke-width: 1.2;
}

.list-model {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 650;
  fill: var(--hmz-stage-ink);
}

.rung-bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
}

.rung-lit rect {
  fill: var(--hmz-lane-4);
}

.rung-lit .rung-word {
  fill: var(--vp-c-bg);
}

.ghost-word {
  font-family: var(--vp-font-family-mono);
  font-weight: 650;
}

.ghost-word.model {
  font-size: 12px;
  fill: var(--hmz-lane-3);
}

.ghost-word.effort {
  font-size: 11.5px;
  fill: var(--hmz-lane-4);
}

.rung-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--hmz-stage-ink);
}

.ladder-alarm {
  fill: color-mix(in srgb, var(--hmz-lane-5) 12%, transparent);
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
  opacity: 0;
}

.stray-word rect {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-5);
  stroke-width: 1.4;
}

.stray-word text {
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  font-weight: 650;
  fill: var(--hmz-lane-5);
}

.stray-cross {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
}

.refused text {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  fill: var(--hmz-lane-5);
}

.reel {
  font-family: var(--vp-font-family-mono);
  font-size: 26px;
  font-weight: 700;
  fill: var(--hmz-lane-1);
}

.reel-word {
  font-family: var(--vp-font-family-mono);
  font-size: 24px;
  font-weight: 700;
  fill: var(--hmz-accent-2);
}

.halo {
  opacity: var(--hmz-glow);
}
</style>
