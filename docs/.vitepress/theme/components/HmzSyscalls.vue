<script setup lang="ts">
// Where each thing an anchored agent does lands. The routing is `src/hmz/coganchor/policy.py`
// and `supervisor.py`: files in the workspace are read and written through a local mirror of
// the target and pushed to it whole; creating, removing, renaming and mode changes are replayed
// there first; programs the agent spawns, and their connections, run on the target; the
// agent's own runtime, state directory, redirected credentials and connections stay here.
import { computed, onMounted, onUnmounted, ref } from 'vue'

type Where = 'target' | 'here'
type Spot = 'files' | 'commands' | 'network' | 'login' | 'provider'

interface Act {
  does: string
  by: string
  where: Where
  spot: Spot
  note: string
}

const ACTS: Act[] = [
  {
    does: 'reads src/pay.py',
    by: 'the agent',
    where: 'target',
    spot: 'files',
    note: 'Read from a local copy of the target’s workspace that is kept in step with it: the same names, contents, sizes, modes and timestamps, at the same paths. Reads go at local speed.',
  },
  {
    does: 'edits src/pay.py',
    by: 'the agent',
    where: 'target',
    spot: 'files',
    note: 'Written locally, then sent to the target whole: before any command runs there, and again when the session ends. The target never holds half an edit.',
  },
  {
    does: 'deletes build/',
    by: 'the agent',
    where: 'target',
    spot: 'files',
    note: 'Creating, removing, renaming and changing permissions happen on the target first, so any error the agent sees is the target’s own.',
  },
  {
    does: 'runs pytest',
    by: 'the agent',
    where: 'target',
    spot: 'commands',
    note: 'Runs on the target, in its copy of the workspace, and behaves like an ordinary local child: the same output and exit status. Signals travel both ways.',
  },
  {
    does: 'fetches from pypi.org',
    by: 'pytest',
    where: 'target',
    spot: 'network',
    note: 'Everything the agent starts, and everything those start in turn, reaches the network from the target.',
  },
  {
    does: 'calls its model provider',
    by: 'the agent',
    where: 'here',
    spot: 'provider',
    note: 'The agent’s own connections stay on this machine, so it reaches its provider the way it always does.',
  },
  {
    does: 'reads its sign-in',
    by: 'the agent',
    where: 'here',
    spot: 'login',
    note: 'Its state directory and credentials never leave this machine. An agent running as another account reads that account’s credentials here too.',
  },
]

const SPOTS: Record<Where, { spot: Spot; said: string }[]> = {
  target: [
    { spot: 'files', said: 'workspace files' },
    { spot: 'commands', said: 'commands' },
    { spot: 'network', said: 'their network' },
  ],
  here: [
    { spot: 'login', said: 'its sign-in and state' },
    { spot: 'provider', said: 'its model provider' },
  ],
}

const picked = ref(0)
const touring = ref(true)
const act = computed(() => ACTS[picked.value])

let timer: ReturnType<typeof setInterval> | undefined
const seen = ref(true)
const root = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

function pick(i: number) {
  picked.value = i
  touring.value = false
}

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    touring.value = false
    picked.value = 3
    return
  }
  observer = new IntersectionObserver((entries) => (seen.value = entries[0].isIntersecting))
  if (root.value) observer.observe(root.value)
  timer = setInterval(() => {
    if (touring.value && seen.value) picked.value = (picked.value + 1) % ACTS.length
  }, 3200)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  observer?.disconnect()
})
</script>

<template>
  <div ref="root" class="anchor hmz-panel" :class="{ idle: !seen }">
    <div class="bar">
      <span class="what">Pick something the agent does</span>
      <span class="sim">simulation</span>
      <button
        class="toggle"
        type="button"
        :aria-label="touring ? 'stop the tour' : 'tour every action'"
        @click="touring = !touring"
      >
        {{ touring ? '❙❙' : '▶' }}
      </button>
    </div>

    <div class="map" :class="act.where">
      <div class="node agent">
        <strong>the agent</strong>
        <span>runs here, unchanged, and is told none of this</span>
        <code class="doing">{{ act.by === 'the agent' ? act.does : `${act.by} ${act.does}` }}</code>
      </div>
      <div class="wire" aria-hidden="true"><i /></div>
      <div class="node anchor-node">
        <strong>the anchor</strong>
        <span>decides where each thing it does lands</span>
      </div>
      <div class="wire split" aria-hidden="true"><i /></div>
      <div class="dests">
        <div class="dest target" :class="{ lit: act.where === 'target' }">
          <strong>the target</strong>
          <div class="spots">
            <span
              v-for="one in SPOTS.target"
              :key="one.spot"
              :class="{ lit: act.spot === one.spot }"
            >{{ one.said }}</span>
          </div>
        </div>
        <div class="dest here" :class="{ lit: act.where === 'here' }">
          <strong>this machine</strong>
          <div class="spots">
            <span
              v-for="one in SPOTS.here"
              :key="one.spot"
              :class="{ lit: act.spot === one.spot }"
            >{{ one.said }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="picker" role="group" aria-label="what the agent does">
      <button
        v-for="(one, i) in ACTS"
        :key="one.does"
        type="button"
        :aria-pressed="picked === i"
        :class="{ on: picked === i, here: one.where === 'here' }"
        @click="pick(i)"
      >
        <code>{{ one.does }}</code>
        <span>{{ one.by }}</span>
      </button>
    </div>

    <p class="note" aria-live="polite">
      <strong>{{ act.where === 'target' ? 'On the target.' : 'On this machine.' }}</strong>
      {{ act.note }}
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
}

.what {
  flex: 1;
  font-weight: 650;
  color: var(--vp-c-text-1);
}

.sim {
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.toggle {
  min-width: 34px;
  padding: 3px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  cursor: pointer;
}

.map {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 44px minmax(0, 0.9fr) 44px minmax(0, 1.3fr);
  align-items: center;
  padding: 22px 16px 16px;
  background: radial-gradient(60% 90% at 12% 50%, var(--vp-c-brand-soft), transparent 70%);
}

.node,
.dest {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
}

.node strong,
.dest strong {
  font-size: 13.5px;
  color: var(--vp-c-text-1);
}

.node span {
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--vp-c-text-3);
}

.anchor-node {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-bg-elv);
}

.doing {
  align-self: flex-start;
  margin-top: 6px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  color: var(--vp-c-bg);
  background: var(--vp-c-text-1);
}

.wire {
  position: relative;
  height: 2px;
  margin: 0 4px;
  background: var(--vp-c-divider);
  overflow: hidden;
}

.wire i {
  position: absolute;
  inset: 0 0 0 -12px;
  background: repeating-linear-gradient(
    90deg,
    var(--hmz-accent) 0 6px,
    transparent 6px 12px
  );
  animation: crawl 0.8s linear infinite;
}

.map.here .wire i {
  background: repeating-linear-gradient(90deg, var(--hmz-warm) 0 6px, transparent 6px 12px);
}

@keyframes crawl {
  from {
    transform: translateX(-12px);
  }
  to {
    transform: translateX(0);
  }
}

.dests {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dest {
  opacity: 0.55;
  transition: opacity 0.3s, border-color 0.3s, box-shadow 0.3s;
}

.dest.lit {
  opacity: 1;
}

.dest.target.lit {
  border-color: var(--hmz-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--hmz-accent) 18%, transparent);
}

.dest.here.lit {
  border-color: var(--hmz-warm);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--hmz-warm) 18%, transparent);
}

.spots {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.spots span {
  padding: 2px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  font-size: 11.5px;
  color: var(--vp-c-text-2);
  transition: background 0.3s, color 0.3s, border-color 0.3s;
}

.target .spots span.lit {
  border-color: var(--hmz-accent);
  background: color-mix(in srgb, var(--hmz-accent) 16%, transparent);
  color: var(--vp-c-text-1);
}

.here .spots span.lit {
  border-color: var(--hmz-warm);
  background: color-mix(in srgb, var(--hmz-warm) 16%, transparent);
  color: var(--vp-c-text-1);
}

.picker {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 4px 16px 0;
}

.picker button {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 9px;
  background: var(--vp-c-bg);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.picker button:hover {
  border-color: var(--vp-c-brand-1);
}

.picker button code {
  font-size: 11.5px;
  color: var(--vp-c-text-1);
  background: none;
  padding: 0;
}

.picker button span {
  font-size: 10.5px;
  color: var(--vp-c-text-3);
}

.picker button.on {
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.picker button.on.here {
  border-color: var(--hmz-warm);
}

.note {
  margin: 0;
  padding: 12px 16px 15px;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.note strong {
  margin-right: 4px;
  color: var(--vp-c-text-1);
}

@media (max-width: 900px) {
  .picker {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .map {
    grid-template-columns: minmax(0, 1fr);
    padding: 16px 12px 12px;
  }

  .wire {
    width: 2px;
    height: 22px;
    margin: 0 auto;
  }

  .wire i {
    inset: -12px 0 0 0;
    background: repeating-linear-gradient(
      180deg,
      var(--hmz-accent) 0 6px,
      transparent 6px 12px
    );
    animation-name: fall;
  }

  .map.here .wire i {
    background: repeating-linear-gradient(180deg, var(--hmz-warm) 0 6px, transparent 6px 12px);
  }

  .picker {
    padding: 4px 12px 0;
  }
}

@keyframes fall {
  from {
    transform: translateY(-12px);
  }
  to {
    transform: translateY(0);
  }
}

.idle .wire i {
  animation-play-state: paused;
}

@media (prefers-reduced-motion: reduce) {
  .wire i {
    animation: none;
  }
}
</style>
