<script setup lang="ts">
// The same model with and without a flow: four models, three levels of scaffolding, fifty problems.
// A switch between the two benchmarks; each model is three bars on a scale of 50, the flow's in
// accent, with what it gained over the coding CLI beside it. The bars grow in the first time the
// figure is seen, and re-grow from where they were when the benchmark changes.
import { computed, onMounted, ref } from 'vue'
import { useInView } from './shared'
import { ABLATION, LEVELS } from './data'

const MAX = 50
const at = ref(0)
const set = computed(() => ABLATION[at.value])
const root = ref<HTMLElement | null>(null)
const seen = useInView(root, 0.3)
// The server draws the bars grown, so the page reads without script; once mounted they wait
// to be seen.
const mounted = ref(false)
onMounted(() => (mounted.value = true))
const w = (v: number) => (!mounted.value || seen.value ? `${(v / MAX) * 100}%` : '0%')
const label = computed(() =>
  `${set.value.label}, problems solved of ${MAX}: ` +
  set.value.rows.map((r) => `${r.label} ${r.api} through the model API, ${r.cli} through a coding CLI, ${r.flow} inside a Humanize flow`).join('; '),
)
</script>

<template>
  <figure ref="root" class="ab" :aria-label="label">
    <div class="ab-top">
      <div class="ab-tabs" role="tablist" aria-label="Benchmark">
        <button
          v-for="(d, i) in ABLATION"
          :key="d.key"
          type="button"
          role="tab"
          :aria-selected="at === i"
          :class="{ on: at === i }"
          @click="at = i"
        >
          {{ d.label }}
        </button>
      </div>
      <div class="ab-key" aria-hidden="true">
        <span v-for="l in LEVELS" :key="l.key" :class="l.key"><i />{{ l.label }}</span>
      </div>
    </div>

    <div class="ab-grid" aria-hidden="true">
      <div class="ab-scale">
        <span v-for="t in [0, 10, 20, 30, 40, 50]" :key="t" :style="{ left: `${(t / MAX) * 100}%` }">{{ t }}</span>
      </div>
      <div v-for="(row, r) in set.rows" :key="row.label" class="ab-row">
        <p class="ab-name">{{ row.label }}</p>
        <div class="ab-bars">
          <div v-for="(l, k) in LEVELS" :key="l.key" class="ab-bar" :class="l.key">
            <i :style="{ width: w(row[l.key]), transitionDelay: `${r * 90 + k * 60}ms` }" />
            <b>{{ row[l.key] }}</b>
          </div>
        </div>
        <p class="ab-gain">
          <span>+{{ row.flow - row.cli }}</span>
          <small>over the CLI</small>
        </p>
      </div>
    </div>

    <figcaption>
      Problems solved of 50, by base model and setup. From the ablation in the <a href="https://humanfia.ai/blog/2026-09-27-kda-for-kda">KDA² post</a>.
    </figcaption>
  </figure>
</template>

<style scoped>
.ab {
  margin: 0;
}
.ab-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 28px;
}
.ab-tabs {
  display: inline-flex;
  border: 2px solid var(--hz-ink);
}
.ab-tabs button {
  padding: 10px 18px;
  font: 700 12px/1 var(--hz-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--hz-ink-2);
  background: transparent;
  cursor: pointer;
  transition: color 0.2s, background-color 0.2s;
}
.ab-tabs button.on {
  color: var(--hz-on-ink);
  background: var(--hz-ink);
}
.ab-key {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  font: 11.5px/1 var(--hz-mono);
  color: var(--hz-ink-3);
}
.ab-key span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.ab-key i {
  width: 16px;
  height: 10px;
  background: var(--c);
}

.api {
  --c: repeating-linear-gradient(135deg, var(--hz-ink-3) 0 2px, transparent 2px 5px);
}
.cli {
  --c: var(--hz-ink-2);
}
.flow {
  --c: var(--hz-mark);
}

.ab-grid {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding-top: 26px;
  --name: 150px;
  --gain: 104px;
}
.ab-scale {
  position: absolute;
  top: 0;
  bottom: 0;
  left: calc(var(--name) + 20px);
  right: calc(var(--gain) + 20px + 28px);
  pointer-events: none;
}
.ab-scale span {
  position: absolute;
  top: 0;
  bottom: 0;
  transform: translateX(-50%);
  font: 11px/1 var(--hz-mono);
  color: var(--hz-ink-3);
}
.ab-scale span::after {
  content: '';
  position: absolute;
  top: 18px;
  bottom: 0;
  left: 50%;
  border-left: 1px dashed var(--hz-line);
}
.ab-row {
  display: grid;
  grid-template-columns: var(--name) minmax(0, 1fr) var(--gain);
  align-items: center;
  gap: 20px;
}
.ab-name {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--hz-ink);
}
.ab-bars {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-right: 28px;
}
.ab-bar {
  position: relative;
  display: flex;
  align-items: center;
  height: 14px;
}
.ab-bar.flow {
  height: 22px;
}
.ab-bar i {
  display: block;
  height: 100%;
  background: var(--c);
  transition: width 1.1s var(--hz-ease);
}
.ab-bar b {
  margin-left: 8px;
  font: 600 11px/1 var(--hz-mono);
  font-variant-numeric: tabular-nums;
  color: var(--hz-ink-3);
}
.ab-bar.flow b {
  font-size: 13px;
  font-weight: 700;
  color: var(--hz-ink);
}
.ab-gain {
  margin: 0;
  display: flex;
  flex-direction: column;
}
.ab-gain span {
  font-size: clamp(24px, 2.4vw, 34px);
  font-weight: 800;
  letter-spacing: -0.04em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--hf-cyan-deep);
}
.ab-gain small {
  margin-top: 4px;
  font: 11px/1.2 var(--hz-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--hz-ink-3);
}

figcaption {
  margin-top: 30px;
  padding-top: 16px;
  border-top: 1px solid var(--hz-line);
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--hz-ink-3);
}
figcaption a {
  font-weight: 600;
  color: var(--hz-accent);
}
figcaption a:hover {
  text-decoration: underline;
}

@media (max-width: 640px) {
  .ab-grid {
    --name: 0px;
    --gain: 64px;
  }
  .ab-row {
    grid-template-columns: minmax(0, 1fr) var(--gain);
    gap: 6px 14px;
  }
  .ab-name {
    grid-column: 1 / -1;
  }
  .ab-scale {
    left: 0;
    right: calc(var(--gain) + 14px + 28px);
  }
}
</style>
