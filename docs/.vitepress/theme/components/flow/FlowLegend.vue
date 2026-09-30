<script setup lang="ts">
// The legend on /flows/: every mark the flow diagrams are drawn with, drawn by the very
// components the diagrams use, and what each one means. Nothing in a diagram is drawn any
// other way, so this is the whole of what there is to learn.
import FlowGate from './FlowGate.vue'
import FlowGlyph from './FlowGlyph.vue'
import FlowHead from './FlowHead.vue'
import FlowLoop from './FlowLoop.vue'
import FlowMeter from './FlowMeter.vue'
import FlowPlate from './FlowPlate.vue'
import FlowTurn from './FlowTurn.vue'
import FlowWire from './FlowWire.vue'
import './grammar.css'

const dots = (y: number, from: number, to: number) =>
  Array.from({ length: 6 }, (_, k) => ({ x: to - (k + 1) * 6, y, r: 3.6 * (1 - (k + 1) / 7), o: 0.5 * (1 - (k + 1) / 7) })).filter(
    (d) => d.x > from,
  )
</script>

<template>
  <div class="legend hmz-flow">
    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <g transform="translate(30 32)"><FlowHead kind="maker" bare /></g>
        <g transform="translate(90 32)"><FlowHead kind="partner" bare /></g>
        <g transform="translate(150 32)"><FlowHead kind="checker" bare /></g>
        <g transform="translate(210 32)"><FlowHead kind="steward" bare /></g>
      </svg>
      <figcaption>
        <b>An agent</b>, one lane per role. Its colour says what the role is: does the work
        <span class="sw k-maker" />, takes turns with it <span class="sw k-partner" />, reads and
        judges <span class="sw k-checker" />, plans or cleans <span class="sw k-steward" />.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <g transform="translate(70 32)"><FlowHead kind="human" bare /></g>
        <g transform="translate(170 32)"><FlowHead kind="program" bare /></g>
      </svg>
      <figcaption>
        <b>You</b>, a ring with a person, and <b>a program</b>, a square: humanize or your own
        script, with no model in it.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <g transform="translate(50 32)">
          <FlowTurn kind="maker" :w="140" session="new" does="work" :lines="['a new session']" />
        </g>
      </svg>
      <figcaption>
        <b>A new session</b>: the spark on the left edge. The flow opened a session for this turn,
        so it knows only its prompt and what is on disk.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <path class="f-thread on k-maker" d="M 34 32 L 206 32" stroke-width="5.2" />
        <g transform="translate(16 32)"><FlowTurn kind="maker" :w="92" session="new" does="work" :lines="['a turn']" /></g>
        <g transform="translate(132 32)"><FlowTurn kind="maker" :w="92" session="held" does="work" :lines="['held']" /></g>
      </svg>
      <figcaption>
        <b>A held session</b>: a thread from the turn before. The same session takes another turn
        and remembers; the thread thickens as its context grows.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <g transform="translate(6 32)"><FlowTurn kind="maker" :w="54" session="held" does="work" /></g>
        <g transform="translate(66 32)"><FlowTurn kind="checker" :w="54" session="held" does="read" /></g>
        <g transform="translate(126 32)"><FlowTurn kind="steward" :w="54" session="held" does="plan" /></g>
        <g transform="translate(186 32)"><FlowTurn kind="program" :w="48" session="none" does="run" /></g>
      </svg>
      <figcaption>
        <b>What a turn does</b>: works, reads, plans, or runs. An agent's turn is a capsule, yours
        is a bubble, a program's is a box.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <FlowWire
          kind="maker"
          via="text"
          d="M 16 22 L 224 22"
          lit="M 16 22 L 150 22"
          :trail="dots(22, 16, 150)"
          :head="{ x: 150, y: 22, s: 1 }"
        />
        <FlowWire kind="maker" via="tree" d="M 16 46 L 224 46" lit="M 16 46 L 110 46" :trail="dots(46, 16, 110)" :head="{ x: 110, y: 46, s: 1 }" />
      </svg>
      <figcaption>
        <b>A pass</b> from one turn to the next. Solid, with a round comet: words, in the next
        prompt. Dotted, with a square one: files, left in the tree, and nothing said.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <FlowPlate points="8,6 232,6 232,58 8,58" m="translate(8 58)" name="your repository" />
      </svg>
      <figcaption>
        <b>A workspace</b>: the plate under the lanes that work in it, named: your repository, a
        copy, a clone, a worktree.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <polygon class="stack" points="70,4 226,4 214,22 58,22" />
        <polygon class="stack" points="52,22 208,22 196,40 40,40" />
        <polygon class="stack" points="34,40 190,40 178,58 22,58" />
      </svg>
      <figcaption>
        <b>Lanes at once</b>: workspaces fanned out in depth, the camera craning up to show them
        running side by side.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <g transform="translate(40 26)">
          <FlowTurn kind="maker" :w="160" session="new" does="work" calls="humanize1:rlcr" :lines="['Lean, on a branch']" />
        </g>
      </svg>
      <figcaption>
        <b>Another flow, called</b>: a turn drawn twice, one outline inside the other, with the
        flow it runs.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <FlowLoop
          d="M 200 14 C 210 54, 40 54, 40 14"
          :tip="{ x: 40, y: 14, a: -90, s: 1 }"
          said="and round again"
          :at="{ x: 120, y: 44, s: 1 }"
        />
      </svg>
      <figcaption>
        <b>The loop</b>: a dashed arc back under the lanes, to where the next round starts, and
        what repeats.
      </figcaption>
    </figure>

    <figure>
      <svg viewBox="0 0 240 64" aria-hidden="true">
        <g transform="translate(46 26)"><FlowMeter :w="180" :fill="0.62" bare /></g>
        <g transform="translate(24 26)" class="o-budget glyph"><FlowGlyph name="budget" :size="14" /></g>
      </svg>
      <figcaption>
        <b>The budget</b>: a bar that fills only while a model works. Every flow but
        <code>chat</code> runs under one.
      </figcaption>
    </figure>

    <figure class="wide">
      <svg viewBox="0 0 240 128" aria-hidden="true">
        <g transform="translate(14 4)">
          <FlowGate
            :ends="[
              { is: 'done', said: 'done: the flow’s own finish' },
              { is: 'fail', said: 'the flow gives up' },
              { is: 'budget', said: 'the budget runs out' },
              { is: 'you', said: 'you end it' },
            ]"
            :h="120"
            :fired="1"
          />
        </g>
      </svg>
      <figcaption>
        <b>The finish</b>: a post at the right with every way the run ends. The one the run
        reaches lights up in its own colour.
      </figcaption>
    </figure>
  </div>
</template>

<style scoped>
.legend {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
  margin: 16px 0;
}

figure {
  margin: 0;
  padding: 10px 12px 12px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 12px;
  background: var(--hmz-panel-bg);
}

svg {
  display: block;
  width: 100%;
  height: auto;
  max-height: 72px;
}

.wide svg {
  max-height: 140px;
}

figcaption {
  margin-top: 8px;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

figcaption b {
  color: var(--vp-c-text-1);
}

.sw {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--hue);
  vertical-align: 0;
}

.glyph {
  color: var(--hue);
}

.stack {
  fill: var(--flow-plate);
  stroke: var(--flow-plate-edge);
  stroke-dasharray: 5 4;
}
</style>
