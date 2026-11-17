<script setup lang="ts">
// A grant, drawn as the rules it is made of, and held. A grant is a preset, a network switch,
// and rules after the preset's own; each rule names a path and everything beneath it, and the
// last rule to match a path decides it. The default, `workspace-write`, is two rules:
// `read_only("/")` (the whole machine) and then `allow(".")` (the workdir), with the network
// on. The agent writes `inside.txt` in its workdir and it lands; it writes `/srv/outside.txt`
// and the write stops at the workdir's edge, the wall Landlock (Linux) or Seatbelt (macOS)
// holds: permission denied. It reads `~/.gitconfig` outside, and that passes, since `/` is
// read. Then a stricter grant, `Permission("read-only", network=False,
// granular=(deny("~/.ssh"),))`: the preset drops `allow(".")`, so the write in the workdir is
// refused too; `deny("~/.ssh")` comes after `read_only("/")`, so it wins under `~/.ssh` and a
// read there is refused; and the network is cut but for the host its model is at.
import { computed, ref } from 'vue'

import HmzStage from '../../motion/HmzStage.vue'
import { createFx, type Fx } from '../../motion/fx'
import { useNarrow } from '../../motion/layout'
import { usePalette } from '../../motion/palette'
import { useScene } from '../../motion/useScene'
import { rig, type Point, type Shot } from '../../motion/camera'
import { curve, draw, pop, pulse, ring, rise, shake } from '../user-kit/moves'

const BEATS = [
  'The default, workspace-write: read_only("/"), then allow("."), and the network on',
  'A write in the workdir lands: allow(".") is the last rule to match it',
  'A write outside hits the wall: only read_only("/") matches it',
  'A read outside passes: read_only("/") covers it',
  'A stricter grant, read-only: allow(".") is gone, so the write is refused',
  'deny("~/.ssh") comes last, so it wins there: the read is refused',
  "network=False: the web is cut, the model's host is not",
]

type Key = 'root' | 'work' | 'ssh'
/**
 * The paths the rules name, widest first, and what the rule naming each grants: `/` and `.`
 * are the default's own two rules; `~/.ssh` is the strict grant's granular rule, drawn only
 * once it is added. Until then the key beneath it is read under `/`, like any other file.
 */
const REGIONS: { key: Key; name: string; value: string; note: string }[] = [
  { key: 'root', name: '/', value: 'READ', note: 'the whole machine' },
  { key: 'work', name: '.', value: 'WRITE', note: 'the workdir' },
  { key: 'ssh', name: '~/.ssh', value: 'NONE', note: 'carved out' },
]
/** The grant card's rows, default then strict. A `to` of null keeps the row as it is. */
const ROWS: { from: [string, string]; to: [string, string] | null }[] = [
  { from: ['network', 'on'], to: ['network', 'off'] },
  { from: ['read_only /', 'READ'], to: null },
  { from: ['allow .', 'WRITE'], to: ['deny ~/.ssh', 'NONE'] },
]
/** The colour of a value's chip. */
const TONE: Record<string, string> = { WRITE: 'write', on: 'write', READ: 'read', NONE: 'none', off: 'none' }

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Layout {
  w: number
  h: number
  regions: Record<Key, Box>
  agent: Point
  files: { inside: Point; gitconfig: Point; outside: Point; key: Point }
  /** Where the write outside stops, and where on the wall it strikes. */
  hit: Point
  strike: Point
  /** The workdir's edge the write strikes. */
  wall: [Point, Point]
  shield: Point
  deny: Point
  written: Point
  read: Point
  /** Where the strict write stops, short of the file, and what it is told. */
  short: Point
  deny2: Point
  /** Where the read under `~/.ssh` stops, at its edge, and what it is told. */
  shortKey: Point
  deny3: Point
  online: Box
  hosts: { web: Point; model: Point; webEnd: Point; modelEnd: Point; bend: [number, number] }
  grant: Box
  rowH: number
  rowTop: number
  shots: Record<'open' | 'write' | 'wall' | 'read' | 'grant' | 'strict' | 'carve' | 'net', Partial<Shot>>
}

const WIDE: Layout = {
  w: 640,
  h: 360,
  regions: {
    root: { x: 20, y: 28, w: 420, h: 314 },
    work: { x: 48, y: 124, w: 152, h: 190 },
    ssh: { x: 218, y: 52, w: 206, h: 96 },
  },
  agent: { x: 96, y: 214 },
  files: { inside: { x: 110, y: 262 }, gitconfig: { x: 300, y: 196 }, outside: { x: 372, y: 262 }, key: { x: 321, y: 112 } },
  hit: { x: 178, y: 228 },
  strike: { x: 200, y: 232 },
  wall: [
    { x: 200, y: 124 },
    { x: 200, y: 314 },
  ],
  shield: { x: 200, y: 180 },
  deny: { x: 372, y: 290 },
  written: { x: 110, y: 290 },
  read: { x: 300, y: 222 },
  short: { x: 106, y: 241 },
  deny2: { x: 110, y: 304 },
  shortKey: { x: 240, y: 158 },
  deny3: { x: 321, y: 138 },
  online: { x: 456, y: 28, w: 168, h: 124 },
  hosts: { web: { x: 540, y: 86 }, model: { x: 540, y: 120 }, webEnd: { x: 476, y: 86 }, modelEnd: { x: 476, y: 120 }, bend: [0.4, 0.3] },
  grant: { x: 456, y: 168, w: 168, h: 172 },
  rowH: 30,
  rowTop: 52,
  shots: {
    open: { x: 320, y: 180, s: 1 },
    write: { x: 124, y: 226, s: 1.5 },
    wall: { x: 250, y: 238, s: 1.4 },
    read: { x: 200, y: 205, s: 1.4 },
    grant: { x: 540, y: 248, s: 1.5 },
    strict: { x: 170, y: 226, s: 1.3 },
    carve: { x: 290, y: 140, s: 1.4 },
    net: { x: 320, y: 180, s: 1 },
  },
}

const NARROW: Layout = {
  w: 360,
  h: 648,
  regions: {
    root: { x: 12, y: 14, w: 336, h: 362 },
    work: { x: 24, y: 60, w: 312, h: 116 },
    ssh: { x: 160, y: 190, w: 176, h: 84 },
  },
  agent: { x: 110, y: 130 },
  files: { inside: { x: 240, y: 120 }, gitconfig: { x: 90, y: 232 }, outside: { x: 248, y: 318 }, key: { x: 248, y: 244 } },
  hit: { x: 139, y: 168 },
  strike: { x: 143, y: 176 },
  wall: [
    { x: 24, y: 176 },
    { x: 336, y: 176 },
  ],
  shield: { x: 262, y: 176 },
  deny: { x: 248, y: 346 },
  written: { x: 240, y: 146 },
  read: { x: 90, y: 258 },
  short: { x: 196, y: 124 },
  deny2: { x: 240, y: 148 },
  shortKey: { x: 178, y: 184 },
  deny3: { x: 248, y: 268 },
  online: { x: 12, y: 390, w: 336, h: 96 },
  hosts: { web: { x: 96, y: 460 }, model: { x: 264, y: 460 }, webEnd: { x: 96, y: 449 }, modelEnd: { x: 264, y: 449 }, bend: [-0.5, 0.3] },
  grant: { x: 12, y: 500, w: 336, h: 136 },
  rowH: 24,
  rowTop: 48,
  shots: {
    open: { x: 180, y: 324, s: 1 },
    write: { x: 180, y: 150, s: 1.06 },
    wall: { x: 180, y: 240, s: 1.06 },
    read: { x: 180, y: 200, s: 1.06 },
    grant: { x: 180, y: 520, s: 1.08 },
    strict: { x: 180, y: 150, s: 1.06 },
    carve: { x: 180, y: 240, s: 1.06 },
    net: { x: 180, y: 330, s: 1 },
  },
}

const palette = usePalette()
const canvas = ref<HTMLCanvasElement | null>(null)
let fx: Fx | undefined

const narrow = useNarrow(() => scene.rebuild())
const L = computed(() => (narrow.value ? NARROW : WIDE))

/** A mono character's advance at 12px. */
const CW = 7.2
const chipX = (box: Box, name: string) => box.x + 12 + name.length * CW + 8
const FILE_W = { inside: 80, gitconfig: 92, outside: 118, key: 124 }
const FILE_NAME = { inside: 'inside.txt', gitconfig: '~/.gitconfig', outside: '/srv/outside.txt', key: '~/.ssh/id_ed25519' }
const FILES = ['inside', 'gitconfig', 'outside', 'key'] as const

const lineD = (k: 'web' | 'model') => curve(L.value.agent, L.value.hosts[k === 'web' ? 'webEnd' : 'modelEnd'], L.value.hosts.bend[k === 'web' ? 0 : 1])
/** The point halfway along the line to the web, where it is cut. */
const cutAt = computed<Point>(() => {
  const a = L.value.agent
  const b = L.value.hosts.webEnd
  const bend = L.value.hosts.bend[0]
  const cx = (a.x + b.x) / 2 + (b.y - a.y) * bend
  const cy = (a.y + b.y) / 2 - (b.x - a.x) * bend
  return { x: 0.25 * a.x + 0.5 * cx + 0.25 * b.x, y: 0.25 * a.y + 0.5 * cy + 0.25 * b.y }
})
const rowY = (i: number) => L.value.grant.y + L.value.rowTop + i * L.value.rowH

const scene = useScene({
  still: 'rest',
  repeatDelay: 1,
  tick: (dt) => fx?.step(dt),
  build(tl, q) {
    const l = L.value
    fx?.destroy()
    fx = canvas.value ? createFx(canvas.value, l.w, l.h) : undefined
    fx?.clear()
    const one = (sel: string) => q(sel)[0]
    const cam = rig(tl, { w: l.w, h: l.h, world: one('.world'), far: one('.far'), fx: () => fx, start: { ...l.shots.open, s: 1.12 } })
    const c = {
      all: () => palette.accent,
      read: () => palette.warm,
      none: () => palette.danger,
      write: () => palette.lane[0],
    }
    const to = (p: Point) => ({ x: p.x - l.agent.x, y: p.y - l.agent.y })

    tl.set(one('.world'), { autoAlpha: 1 }, 0)
    tl.set(
      q(
        '.region-fill, .region-edge, .region-label, .val, .work-read, .file, .file-solid-inside, .agent, .net, .online, .grant, .pkt, .wall-hit, .shield, .deny, .deny2, .deny3, .mark, .strict, .cut-mark, .web-cut, .reached',
      ),
      { autoAlpha: 0 },
      0,
    )
    tl.set(q('.default, .file-ghost, .web-ok'), { autoAlpha: 1 }, 0)
    tl.set(q('.web-off'), { autoAlpha: 0 }, 0)
    tl.set(q('.pkt'), { x: 0, y: 0 }, 0)

    // 0 · the default's two rules, drawn widest first; the network beside them.
    tl.addLabel('beat-0', 0)
    cam.shot(l.shots.open, 0.2, 3.8, 'cine.out')
    const region = (k: Key, at: number) => {
      draw(tl, one(`.region-${k} .region-edge`), at, { duration: 1.1 })
      tl.to(one(`.region-${k} .region-fill`), { autoAlpha: 1, duration: 0.8 }, at + 0.4)
      rise(tl, one(`.region-${k} .region-label`), at + 0.5, { y: 8 })
      pop(tl, one(`.region-${k} .val`), at + 0.8)
    }
    region('root', 0.2)
    region('work', 0.9)
    pop(tl, one('.agent'), 2.1, { from: 0.3 })
    ring(tl, one('.agent-ring'), 2.4)
    rise(tl, q('.file'), 2.5, { y: 8, stagger: 0.15 })
    rise(tl, one('.online'), 2.9, { x: 12, y: 0 })
    draw(tl, q('.net-line'), 3.3, { duration: 0.9, stagger: 0.15 })
    tl.to(q('.net'), { autoAlpha: 1, duration: 0.01 }, 3.3)
    rise(tl, one('.grant'), 3.6, { y: 10 })
    rise(tl, q('.row'), 3.8, { x: 8, y: 0, stagger: 0.1 })

    // 1 · a write in the workdir lands.
    const T1 = 5.2
    tl.addLabel('beat-1', T1)
    cam.shot(l.shots.write, T1, 1.3)
    const w1 = one('.pkt-w1')
    pop(tl, w1, T1 + 0.9, { from: 0.5 })
    tl.to(w1, { ...to(l.files.inside), duration: 0.8, ease: 'cine' }, T1 + 1.3)
    cam.beam(l.agent, l.files.inside, c.write, T1 + 1.3, { duration: 0.8, bend: 0, burst: 10 })
    tl.to(w1, { autoAlpha: 0, scale: 0.6, duration: 0.25 }, T1 + 2.1)
    tl.to(one('.file-inside .file-ghost'), { autoAlpha: 0, duration: 0.3 }, T1 + 2.1)
    pop(tl, one('.file-solid-inside'), T1 + 2.1, { from: 0.7 })
    ring(tl, one('.file-inside .file-ring'), T1 + 2.15)
    pop(tl, one('.mark-written'), T1 + 2.4)

    // 2 · a write outside: it stops at the workdir's edge.
    const T2 = T1 + 3.4
    tl.addLabel('beat-2', T2)
    cam.shot(l.shots.wall, T2, 1.4)
    const w2 = one('.pkt-w2')
    pop(tl, w2, T2 + 0.9, { from: 0.5 })
    tl.to(w2, { ...to(l.hit), duration: 0.7, ease: 'cine.in' }, T2 + 1.3)
    cam.beam(l.agent, l.hit, c.write, T2 + 1.3, { duration: 0.7, bend: 0, ease: 'cine.in' })
    const HIT = T2 + 2.0
    tl.fromTo(one('.wall-hit'), { autoAlpha: 1, drawSVG: '50% 50%' }, { drawSVG: '0% 100%', duration: 0.45, ease: 'cine.out' }, HIT)
    tl.to(one('.wall-hit'), { autoAlpha: 0.35, duration: 1.2 }, HIT + 0.6)
    cam.flare(l.strike, c.none, HIT, 26, 120)
    tl.to(w2, { x: (l.hit.x - l.agent.x) * 0.55, y: (l.hit.y - l.agent.y) * 0.55, duration: 0.6, ease: 'back.out(2)' }, HIT)
    shake(tl, w2, HIT + 0.6, 4)
    tl.to(w2, { autoAlpha: 0, duration: 0.3 }, HIT + 1.1)
    pop(tl, one('.shield'), HIT + 0.2)
    pop(tl, one('.deny'), HIT + 0.5)
    shake(tl, one('.deny-in'), HIT + 0.95)
    shake(tl, one('.file-outside'), HIT + 0.5, 3)

    // 3 · a read outside passes.
    const T3 = HIT + 2.4
    tl.addLabel('beat-3', T3)
    cam.shot(l.shots.read, T3, 1.3)
    const r = one('.pkt-r')
    pop(tl, r, T3 + 0.9, { from: 0.5 })
    tl.to(r, { ...to(l.files.gitconfig), duration: 0.9, ease: 'cine' }, T3 + 1.3)
    cam.beam(l.agent, l.files.gitconfig, c.read, T3 + 1.3, { duration: 0.9, bend: 0, burst: 8 })
    ring(tl, one('.file-gitconfig .file-ring'), T3 + 2.2)
    tl.to(r, { x: 0, y: 0, duration: 0.9, ease: 'cine' }, T3 + 2.4)
    cam.beam(l.files.gitconfig, l.agent, c.read, T3 + 2.4, { duration: 0.9, bend: 0 })
    tl.to(r, { autoAlpha: 0, duration: 0.25 }, T3 + 3.3)
    pop(tl, one('.mark-read'), T3 + 2.3)
    ring(tl, one('.agent-ring'), T3 + 3.3)

    // 4 · a stricter grant: read-only. allow(".") goes, the workdir falls back to "/", READ.
    const T4 = T3 + 4.2
    tl.addLabel('beat-4', T4)
    cam.shot(l.shots.grant, T4, 1.4)
    const swap = (k: string, at: number) => {
      tl.to(q(`${k} .default`), { autoAlpha: 0, duration: 0.35 }, at)
      tl.fromTo(q(`${k} .strict`), { autoAlpha: 0, scale: 0.6, transformOrigin: '50% 50%' }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(2.4)' }, at + 0.15)
    }
    swap('.mode', T4 + 1.0)
    shake(tl, one('.row-2 .default'), T4 + 1.5, 4)
    tl.to(one('.row-2 .default'), { autoAlpha: 0, duration: 0.4 }, T4 + 1.9)
    ring(tl, one('.row-2 .row-ring'), T4 + 1.6)
    cam.shot(l.shots.strict, T4 + 2.8, 1.5)
    tl.to(one('.work-read'), { autoAlpha: 1, duration: 0.8 }, T4 + 3.3)
    swap('.val-work', T4 + 3.3)
    swap('.agent-name', T4 + 3.5)
    tl.to(q('.mark-written'), { autoAlpha: 0, duration: 0.3 }, T4 + 3.5)
    const w3 = one('.pkt-w3')
    pop(tl, w3, T4 + 4.0, { from: 0.5 })
    tl.to(w3, { ...to(l.short), duration: 0.6, ease: 'cine.in' }, T4 + 4.4)
    cam.flare(l.files.inside, c.none, T4 + 5.0, 20, 100)
    tl.to(w3, { x: (l.short.x - l.agent.x) * 0.4, y: (l.short.y - l.agent.y) * 0.4, duration: 0.55, ease: 'back.out(2)' }, T4 + 5.0)
    shake(tl, one('.file-inside'), T4 + 5.0, 4)
    tl.to(w3, { autoAlpha: 0, duration: 0.3 }, T4 + 5.6)
    pop(tl, one('.deny2'), T4 + 5.2)

    // 5 · a granular rule after the preset's: deny("~/.ssh") is the last to match there.
    const T5 = T4 + 6.6
    tl.addLabel('beat-5', T5)
    cam.shot(l.shots.grant, T5, 1.2)
    tl.fromTo(one('.row-2 .strict'), { autoAlpha: 0, x: 8 }, { autoAlpha: 1, x: 0, duration: 0.5, ease: 'cine.out' }, T5 + 0.9)
    ring(tl, one('.row-2 .row-ring'), T5 + 1.0)
    cam.shot(l.shots.carve, T5 + 1.9, 1.4)
    region('ssh', T5 + 2.2)
    const r2 = one('.pkt-r2')
    pop(tl, r2, T5 + 3.6, { from: 0.5 })
    tl.to(r2, { ...to(l.shortKey), duration: 0.6, ease: 'cine.in' }, T5 + 4.0)
    cam.flare(l.shortKey, c.none, T5 + 4.6, 20, 100)
    tl.to(r2, { x: (l.shortKey.x - l.agent.x) * 0.4, y: (l.shortKey.y - l.agent.y) * 0.4, duration: 0.55, ease: 'back.out(2)' }, T5 + 4.6)
    shake(tl, one('.file-key'), T5 + 4.6, 4)
    tl.to(r2, { autoAlpha: 0, duration: 0.3 }, T5 + 5.2)
    pop(tl, one('.deny3'), T5 + 4.8)

    // 6 · network=False: the web is cut, the model's host is not.
    const T6 = T5 + 6.2
    tl.addLabel('beat-6', T6)
    cam.shot(l.shots.net, T6, 1.5)
    swap('.row-0', T6 + 0.7)
    ring(tl, one('.row-0 .row-ring'), T6 + 0.8)
    swap('.val-online', T6 + 0.9)
    pulse(tl, one('.online'), T6 + 1.0, 1.04)
    pop(tl, one('.cut-mark'), T6 + 1.5, { from: 0.2 })
    cam.flare(cutAt.value, c.none, T6 + 1.5, 18, 90)
    tl.to(one('.net-web'), { autoAlpha: 0, duration: 0.4 }, T6 + 1.6)
    tl.to(one('.web-cut'), { autoAlpha: 1, duration: 0.4 }, T6 + 1.6)
    tl.to(one('.web-ok'), { autoAlpha: 0, duration: 0.3 }, T6 + 1.8)
    tl.to(one('.web-off'), { autoAlpha: 1, duration: 0.3 }, T6 + 1.8)
    shake(tl, one('.host-web'), T6 + 1.8, 4)
    cam.beam(l.agent, l.hosts.modelEnd, c.all, T6 + 2.5, { duration: 1.0, bend: -l.hosts.bend[1], burst: 12 })
    ring(tl, one('.host-model .host-ring'), T6 + 3.5)
    pop(tl, one('.reached'), T6 + 3.6)
    cam.beam(l.hosts.modelEnd, l.agent, c.all, T6 + 3.9, { duration: 1.0, bend: l.hosts.bend[1] })
    ring(tl, one('.agent-ring'), T6 + 4.9)
    tl.addLabel('rest', T6 + 5.2)
    tl.to(one('.world'), { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, T6 + 9)
  },
})
</script>

<template>
  <HmzStage
    :scene="scene"
    :beats="BEATS"
    mobile-ratio="5 / 9"
    label="The default grant, workspace-write, drawn as its rules: read_only of /, the whole machine, then allow of dot, the workdir, with the network on. The last rule to match a path decides it. The agent writes inside.txt in its workdir and the write lands, since allow dot matches it last. It writes /srv/outside.txt and the write stops at the workdir's edge, the wall Landlock or Seatbelt holds: permission denied, and the file is never made. It reads ~/.gitconfig outside the workdir and the read passes, because / is read. Then a stricter grant: the read-only preset, network off, and one granular rule, deny ~/.ssh. The preset drops allow dot, so a write to inside.txt is refused too. deny ~/.ssh comes after read_only of /, so it wins beneath ~/.ssh, and a read of the key there is refused. And the network is cut: web search no longer reaches anything, while the host its model is at is still reached."
  >
    <svg :viewBox="`0 0 ${L.w} ${L.h}`" aria-hidden="true">
      <defs>
        <pattern id="gs-dots" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" class="grid-dot" />
        </pattern>
      </defs>
      <g class="far"><rect x="-400" y="-400" :width="L.w + 800" :height="L.h + 800" fill="url(#gs-dots)" /></g>

      <g class="world">
        <!-- The paths the rules name, each holding everything beneath it. -->
        <g v-for="s in REGIONS" :key="s.key" class="region" :class="`region-${s.key}`">
          <rect class="region-fill" :x="L.regions[s.key].x" :y="L.regions[s.key].y" :width="L.regions[s.key].w" :height="L.regions[s.key].h" rx="14" />
          <rect class="region-edge" :x="L.regions[s.key].x" :y="L.regions[s.key].y" :width="L.regions[s.key].w" :height="L.regions[s.key].h" rx="14" />
          <rect v-if="s.key === 'work'" class="work-read" :x="L.regions.work.x" :y="L.regions.work.y" :width="L.regions.work.w" :height="L.regions.work.h" rx="14" />
          <g class="region-label">
            <text class="region-name" :x="L.regions[s.key].x + 12" :y="L.regions[s.key].y + 20">{{ s.name }}</text>
            <text class="region-note" :x="L.regions[s.key].x + 12" :y="L.regions[s.key].y + 36">{{ s.note }}</text>
          </g>
          <g class="val" :class="`val-${s.key}`">
            <g class="default" :class="`v-${TONE[s.value]}`">
              <rect class="chip" :x="chipX(L.regions[s.key], s.name)" :y="L.regions[s.key].y + 8" width="42" height="16" rx="5" />
              <text class="chip-word" :x="chipX(L.regions[s.key], s.name) + 21" :y="L.regions[s.key].y + 20" text-anchor="middle">{{ s.value }}</text>
            </g>
            <g v-if="s.key === 'work'" class="strict v-read">
              <rect class="chip" :x="chipX(L.regions.work, s.name)" :y="L.regions.work.y + 8" width="42" height="16" rx="5" />
              <text class="chip-word" :x="chipX(L.regions.work, s.name) + 21" :y="L.regions.work.y + 20" text-anchor="middle">READ</text>
            </g>
          </g>
        </g>

        <!-- The workdir's edge, where the write outside strikes. -->
        <line class="wall-hit" :x1="L.wall[0].x" :y1="L.wall[0].y" :x2="L.wall[1].x" :y2="L.wall[1].y" />

        <!-- The network, from the agent to the two kinds of host. -->
        <g class="net">
          <path class="net-line net-web" :d="lineD('web')" />
          <path class="net-line net-model" :d="lineD('model')" />
          <path class="web-cut" :d="lineD('web')" />
          <g :transform="`translate(${cutAt.x} ${cutAt.y})`">
            <g class="cut-mark">
              <circle r="10" class="cut-bg" />
              <path class="cut-x" d="M-4 -4 L4 4 M4 -4 L-4 4" />
            </g>
          </g>
        </g>

        <!-- The files: one to be written in, one outside to be refused, two outside to read. -->
        <g v-for="f in FILES" :key="f" class="file" :class="`file-${f}`">
          <g :transform="`translate(${L.files[f].x} ${L.files[f].y})`">
            <rect v-if="f === 'inside' || f === 'outside'" class="file-ghost" :x="-FILE_W[f] / 2" y="-10" :width="FILE_W[f]" height="20" rx="5" />
            <rect v-if="f !== 'outside'" class="file-solid" :class="`file-solid-${f}`" :x="-FILE_W[f] / 2" y="-10" :width="FILE_W[f]" height="20" rx="5" />
            <text class="file-name" y="4" text-anchor="middle">{{ FILE_NAME[f] }}</text>
            <rect class="file-ring" :x="-FILE_W[f] / 2" y="-10" :width="FILE_W[f]" height="20" rx="5" />
          </g>
        </g>

        <g class="mark mark-written"><text class="mark-word ok" :x="L.written.x" :y="L.written.y" text-anchor="middle">written ✓</text></g>
        <g class="mark mark-read"><text class="mark-word rd" :x="L.read.x" :y="L.read.y" text-anchor="middle">read ✓</text></g>

        <!-- What holds the wall, and what each refused try is told. -->
        <g class="shield">
          <g :transform="`translate(${L.shield.x} ${L.shield.y})`">
            <rect class="shield-bg" x="-54" y="-10" width="108" height="20" rx="10" />
            <text class="shield-word" y="4" text-anchor="middle">Landlock · Seatbelt</text>
          </g>
        </g>
        <g class="deny">
          <g class="deny-in"><text class="deny-word" :x="L.deny.x" :y="L.deny.y" text-anchor="middle">permission denied</text></g>
        </g>
        <g class="deny2"><text class="deny-word" :x="L.deny2.x" :y="L.deny2.y" text-anchor="middle">write refused</text></g>
        <g class="deny3"><text class="deny-word" :x="L.deny3.x" :y="L.deny3.y" text-anchor="middle">read refused</text></g>

        <!-- The agent, and what it sends. -->
        <g :transform="`translate(${L.agent.x} ${L.agent.y})`"><g class="agent">
          <circle r="15" class="agent-body" />
          <circle r="5" class="agent-core" />
          <circle r="15" class="agent-ring" />
          <g class="agent-name">
            <text class="default agent-word" y="30" text-anchor="middle">agent</text>
            <text class="strict agent-word" y="30" text-anchor="middle">reviewer</text>
          </g>
        </g></g>
        <g :transform="`translate(${L.agent.x} ${L.agent.y})`">
          <g v-for="p in ['w1', 'w2', 'w3', 'r', 'r2']" :key="p" class="pkt" :class="[`pkt-${p}`, p.startsWith('r') ? 'pkt-read' : 'pkt-write']">
            <rect x="-22" y="-9" width="44" height="18" rx="9" />
            <text y="4" text-anchor="middle">{{ p.startsWith('r') ? 'read' : 'write' }}</text>
          </g>
        </g>

        <!-- network, beside the rest. -->
        <g class="online">
          <rect class="online-box" :x="L.online.x" :y="L.online.y" :width="L.online.w" :height="L.online.h" rx="14" />
          <text class="region-name" :x="L.online.x + 12" :y="L.online.y + 20">network</text>
          <text class="region-note" :x="L.online.x + 12" :y="L.online.y + 36">web search and fetching</text>
          <g class="val-online">
            <g class="default v-write">
              <rect class="chip" :x="chipX(L.online, 'network')" :y="L.online.y + 8" width="42" height="16" rx="5" />
              <text class="chip-word" :x="chipX(L.online, 'network') + 21" :y="L.online.y + 20" text-anchor="middle">on</text>
            </g>
            <g class="strict v-none">
              <rect class="chip" :x="chipX(L.online, 'network')" :y="L.online.y + 8" width="42" height="16" rx="5" />
              <text class="chip-word" :x="chipX(L.online, 'network') + 21" :y="L.online.y + 20" text-anchor="middle">off</text>
            </g>
          </g>
          <g class="host host-web">
            <g :transform="`translate(${L.hosts.web.x} ${L.hosts.web.y})`">
              <rect class="host-bg" x="-62" y="-11" width="124" height="22" rx="6" />
              <text class="host-word web-ok" y="4" text-anchor="middle">web search</text>
              <text class="host-word web-off" y="4" text-anchor="middle">web search · cut</text>
            </g>
          </g>
          <g class="host host-model">
            <g :transform="`translate(${L.hosts.model.x} ${L.hosts.model.y})`">
              <rect class="host-bg" x="-62" y="-11" width="124" height="22" rx="6" />
              <text class="host-word" y="4" text-anchor="middle">its model's host</text>
              <rect class="host-ring" x="-62" y="-11" width="124" height="22" rx="6" />
            </g>
          </g>
          <g class="reached">
            <text class="mark-word ok" :x="L.hosts.model.x" :y="L.hosts.model.y + (narrow ? 26 : 25)" text-anchor="middle">still reached ✓</text>
          </g>
        </g>

        <!-- The grant, as the flow declares it: its preset, the network, and its rules in order. -->
        <g class="grant">
          <rect class="grant-box" :x="L.grant.x" :y="L.grant.y" :width="L.grant.w" :height="L.grant.h" rx="12" />
          <text class="grant-head" :x="L.grant.x + 12" :y="L.grant.y + 22">preset</text>
          <g class="mode">
            <text class="default mode-word" :x="L.grant.x + L.grant.w - 12" :y="L.grant.y + 22" text-anchor="end">workspace-write</text>
            <text class="strict mode-word strict-mode" :x="L.grant.x + L.grant.w - 12" :y="L.grant.y + 22" text-anchor="end">read-only</text>
          </g>
          <line class="grant-rule" :x1="L.grant.x + 12" :x2="L.grant.x + L.grant.w - 12" :y1="L.grant.y + 32" :y2="L.grant.y + 32" />
          <g v-for="(row, i) in ROWS" :key="row.from[0]" class="row" :class="`row-${i}`">
            <text v-if="!row.to || row.to[0] === row.from[0]" class="row-name" :x="L.grant.x + 14" :y="rowY(i) + 4">{{ row.from[0] }}</text>
            <g class="default">
              <text v-if="row.to && row.to[0] !== row.from[0]" class="row-name" :x="L.grant.x + 14" :y="rowY(i) + 4">{{ row.from[0] }}</text>
              <g :class="`v-${TONE[row.from[1]]}`">
                <rect class="chip" :x="L.grant.x + L.grant.w - 56" :y="rowY(i) - 8" width="42" height="16" rx="5" />
                <text class="chip-word" :x="L.grant.x + L.grant.w - 35" :y="rowY(i) + 4" text-anchor="middle">{{ row.from[1] }}</text>
              </g>
            </g>
            <g v-if="row.to" class="strict">
              <text v-if="row.to[0] !== row.from[0]" class="row-name" :x="L.grant.x + 14" :y="rowY(i) + 4">{{ row.to[0] }}</text>
              <g :class="`v-${TONE[row.to[1]]}`">
                <rect class="chip" :x="L.grant.x + L.grant.w - 56" :y="rowY(i) - 8" width="42" height="16" rx="5" />
                <text class="chip-word" :x="L.grant.x + L.grant.w - 35" :y="rowY(i) + 4" text-anchor="middle">{{ row.to[1] }}</text>
              </g>
            </g>
            <g :transform="`translate(${L.grant.x + L.grant.w / 2} ${rowY(i)})`">
              <rect class="row-ring" :x="-L.grant.w / 2 + 6" :y="-L.rowH / 2 + 2" :width="L.grant.w - 12" :height="L.rowH - 4" rx="6" />
            </g>
          </g>
          <text class="grant-foot" :x="L.grant.x + 14" :y="L.grant.y + L.grant.h - 12">the last rule to match wins</text>
        </g>
      </g>
    </svg>
    <canvas ref="canvas" />
  </HmzStage>
</template>

<style scoped>
svg {
  font-family: var(--vp-font-family-base);
}

.grid-dot {
  fill: var(--hmz-stage-line);
}

.region-fill {
  fill: var(--hmz-stage-card);
}

.region-work .region-fill {
  fill: color-mix(in srgb, var(--hmz-accent) 9%, var(--hmz-stage-card));
}

.region-ssh .region-fill {
  fill: color-mix(in srgb, var(--hmz-lane-5) 9%, var(--hmz-stage-card));
}

.region-edge {
  fill: none;
  stroke: var(--hmz-warm);
  stroke-width: 1.4;
}

.region-work .region-edge {
  stroke: var(--hmz-accent);
  stroke-width: 2;
}

.region-ssh .region-edge {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
  stroke-dasharray: 5 4;
}

.work-read {
  fill: color-mix(in srgb, var(--hmz-warm) 12%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
  stroke-width: 2;
}

.region-name,
.row-name,
.grant-head {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-stage-ink);
}

.region-note,
.mode-word,
.grant-foot {
  font-size: 11px;
  fill: var(--hmz-stage-dim);
}

.strict-mode {
  font-weight: 700;
  fill: var(--hmz-lane-5);
}

.chip-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.03em;
}

.v-write .chip {
  fill: color-mix(in srgb, var(--hmz-accent) 18%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
}

.v-write .chip-word {
  fill: var(--hmz-accent);
}

.v-read .chip {
  fill: color-mix(in srgb, var(--hmz-warm) 18%, var(--hmz-stage-card));
  stroke: var(--hmz-warm);
}

.v-read .chip-word {
  fill: var(--hmz-warm);
}

.v-none .chip {
  fill: color-mix(in srgb, var(--hmz-lane-5) 18%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-5);
}

.v-none .chip-word {
  fill: var(--hmz-lane-5);
}

.wall-hit {
  stroke: var(--hmz-lane-5);
  stroke-width: 4;
  stroke-linecap: round;
}

.net-line,
.web-cut {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 1.3;
  opacity: 0.55;
}

.web-cut {
  stroke: var(--hmz-lane-5);
  stroke-dasharray: 3 5;
}

.cut-bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-lane-5);
  stroke-width: 1.6;
}

.cut-x {
  stroke: var(--hmz-lane-5);
  stroke-width: 2;
  stroke-linecap: round;
}

.file-ghost {
  fill: none;
  stroke: var(--hmz-stage-dim);
  stroke-width: 1.2;
  stroke-dasharray: 4 3;
}

.file-solid {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-ink);
  stroke-width: 1.2;
}

.file-solid-inside {
  fill: color-mix(in srgb, var(--hmz-accent) 16%, var(--hmz-stage-card));
  stroke: var(--hmz-accent);
}

.file-name {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.file-ring,
.host-ring,
.row-ring {
  fill: none;
  stroke: var(--hmz-accent);
  stroke-width: 2;
  opacity: 0;
}

.file-gitconfig .file-ring {
  stroke: var(--hmz-warm);
}

.row-ring {
  stroke: var(--hmz-lane-5);
}

.mark-word {
  font-size: 11px;
  font-weight: 700;
}

.ok {
  fill: var(--hmz-accent);
}

.rd {
  fill: var(--hmz-warm);
}

.shield-bg {
  fill: var(--hmz-lane-5);
}

.shield-word {
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.deny-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  fill: var(--hmz-lane-5);
}

.agent-body {
  fill: color-mix(in srgb, var(--hmz-lane-1) 22%, var(--hmz-stage-card));
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
}

.agent-core {
  fill: var(--hmz-lane-1);
}

.agent-ring {
  fill: none;
  stroke: var(--hmz-lane-1);
  stroke-width: 2;
  opacity: 0;
}

.agent-word {
  font-size: 12px;
  font-weight: 700;
  fill: var(--hmz-lane-1);
}

.pkt rect {
  fill: var(--hmz-lane-1);
}

.pkt-read rect {
  fill: var(--hmz-warm);
}

.pkt text {
  font-size: 11px;
  font-weight: 700;
  fill: #fff;
}

.online-box,
.grant-box {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
  stroke-width: 1.2;
}

.online-box {
  stroke: var(--hmz-accent);
  stroke-dasharray: 5 4;
}

.host-bg {
  fill: var(--hmz-stage-card);
  stroke: var(--hmz-stage-line);
}

.host-word {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  fill: var(--hmz-stage-ink);
}

.web-off {
  fill: var(--hmz-lane-5);
  opacity: 0;
}

.grant-rule {
  stroke: var(--hmz-stage-line);
}
</style>
