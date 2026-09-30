<script setup lang="ts">
// The catalogue on /flows/, and the chooser on top of it: pick what you want done, and the
// cards narrow to the flows that do it, with a line saying which to start with.
//
// The cards are sorted by how the agents in a flow work together (KINDS in `theme/flows.ts`,
// which the sidebar is built from too), and each draws its flow's own scene -- the one its
// page plays -- in the same grammar, small and without words. A card plays while it is
// hovered or focused.
import { withBase } from 'vitepress'
import { computed, ref } from 'vue'

import { FLOWS, JOBS, KINDS, type Job } from '../../flows'
import FlowThumb from './FlowThumb.vue'

const job = ref<Job | 'all'>('all')
const shown = computed(() =>
  KINDS.map((kind) => ({
    kind,
    flows: FLOWS.filter((one) => one.kind === kind.id && (job.value === 'all' || one.jobs.includes(job.value))),
  })).filter((group) => group.flows.length),
)

/** The advice for the picked job, cut at its backticks so the names can be set as code. */
const hint = computed(() => {
  const said = JOBS.find((one) => one.id === job.value)?.hint ?? ''
  return said.split('`').map((text, n) => ({ text, code: n % 2 === 1 }))
})

const thumbs = ref<Record<string, InstanceType<typeof FlowThumb> | null>>({})
</script>

<template>
  <div class="flows hmz-flow">
    <div class="ask" role="group" aria-label="What do you want to do?">
      <span class="q">What do you want to do?</span>
      <button type="button" :class="{ on: job === 'all' }" :aria-pressed="job === 'all'" @click="job = 'all'">
        show every flow
      </button>
      <button
        v-for="one in JOBS"
        :key="one.id"
        type="button"
        :class="{ on: job === one.id }"
        :aria-pressed="job === one.id"
        @click="job = one.id"
      >
        {{ one.said }}
      </button>
    </div>

    <p v-show="job !== 'all'" class="hint" aria-live="polite">
      <template v-for="(part, n) in hint" :key="n">
        <code v-if="part.code">{{ part.text }}</code>
        <template v-else>{{ part.text }}</template>
      </template>
    </p>

    <section v-for="group in shown" :key="group.kind.id" class="kind">
      <h3 :id="`kind-${group.kind.id}`">{{ group.kind.said }}</h3>
      <p class="how">{{ group.kind.how }}</p>
      <div class="grid">
        <a
          v-for="flow in group.flows"
          :key="flow.name"
          class="card"
          :href="withBase(flow.link)"
          @pointerenter="thumbs[flow.name]?.play()"
          @pointerleave="thumbs[flow.name]?.stop()"
          @focus="thumbs[flow.name]?.play()"
          @blur="thumbs[flow.name]?.stop()"
        >
          <div class="pic">
            <FlowThumb :ref="(el) => (thumbs[flow.name] = el as InstanceType<typeof FlowThumb> | null)" :scene="flow.scene" />
          </div>
          <div class="head">
            <code>{{ flow.phases ? `${flow.name}:<phase>` : flow.name }}</code>
            <span v-if="flow.phases" class="runs">{{ flow.phases.join(' · ') }}</span>
          </div>
          <p class="said">{{ flow.said }}</p>
          <dl>
            <div><dt>-a</dt><dd>{{ flow.roles }}</dd></div>
            <div><dt>ends</dt><dd>{{ flow.ends }}</dd></div>
            <div><dt>--resume</dt><dd>{{ flow.keeps || 'starts afresh' }}</dd></div>
          </dl>
        </a>
      </div>
    </section>

    <p class="foot">
      Every run also stops when its budget is spent. Only <code>chat</code> may run without one.
    </p>
  </div>
</template>

<style scoped>
.ask {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.ask .q {
  flex-basis: 100%;
  font-size: 13px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}

.ask button {
  padding: 5px 13px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 20px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12.5px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s, background 0.2s;
}

.ask button:hover {
  color: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

.ask button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.hint {
  margin: 0 0 16px;
  padding: 10px 14px;
  border-left: 3px solid var(--vp-c-brand-1);
  border-radius: 0 10px 10px 0;
  background: var(--vp-c-brand-soft);
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
}

.hint code {
  font-size: 12.5px;
}

.kind {
  margin-top: 22px;
}

.kind h3 {
  margin: 0;
  padding: 0;
  border: none;
  font-size: 15px;
  letter-spacing: 0;
}

.kind .how {
  margin: 2px 0 10px;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 14px;
}

.card {
  display: block;
  padding: 0 0 16px;
  overflow: hidden;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
  color: inherit;
  text-decoration: none;
  transition: transform 0.25s, border-color 0.25s, box-shadow 0.25s;
}

.card:hover,
.card:focus-visible {
  transform: translateY(-3px);
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 12px 32px -20px var(--vp-c-brand-1);
}

.pic {
  border-bottom: 1px solid var(--hmz-panel-border);
  background: radial-gradient(ellipse 80% 100% at 50% 40%, var(--vp-c-bg) 0%, transparent 100%);
}

.pic {
  aspect-ratio: 300 / 130;
}

.pic :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
}

.head,
.said,
dl {
  margin-left: 16px;
  margin-right: 16px;
}

.head {
  margin-top: 12px;
}

/* The name gets a line of its own: `parallel_flame_chase_git_pr` is wider than half a card. */
.head code {
  display: block;
  padding: 0;
  background: none;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--vp-c-brand-1);
  overflow-wrap: anywhere;
}

.head .runs {
  display: block;
  margin-top: 2px;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.said {
  margin-top: 8px;
  margin-bottom: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

dl {
  margin-top: 12px;
  margin-bottom: 0;
  padding-top: 10px;
  border-top: 1px solid var(--vp-c-divider);
  font-size: 11.5px;
  line-height: 1.45;
}

dl div {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

dt {
  flex: none;
  width: 62px;
  font-family: var(--vp-font-family-mono);
  font-size: 10.5px;
  color: var(--vp-c-text-3);
}

dd {
  flex: 1;
  margin: 0;
  color: var(--vp-c-text-2);
}

.foot {
  margin: 16px 0 0;
  font-size: 12.5px;
  color: var(--vp-c-text-3);
}
</style>
