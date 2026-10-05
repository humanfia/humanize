<script setup lang="ts">
// Tabs whose panels are whole pieces of a page -- prose, a GIF, a `::: code-group` of their own
// -- where VitePress's `::: code-group` holds code blocks only. A panel is a named slot, written
// in the page with markdown inside it:
//
//   <HmzTabs :tabs="[{ id: 'prompt', name: 'At the prompt', hint: 'hmz' }, …]">
//   <template #prompt>
//
//   …markdown, with a blank line above and below it…
//
//   </template>
//   </HmzTabs>
//
// Every panel is rendered and the ones not chosen are hidden, so the page reads whole before
// any script runs. A link to an id inside a hidden panel -- a heading, say -- opens that panel.
//
// Choosing a tab moves a red bar under the tab bar across to it, skewed on the way like a
// plane in motion, and the panel coming in is wiped in on the diagonal. Under reduced motion
// the bar jumps and the panel is simply there.
import { computed, nextTick, onMounted, onUnmounted, ref, useId, watch } from 'vue'

interface Tab {
  /** The slot the panel is written in, and the key it is chosen by. */
  id: string
  /** What the tab says. */
  name: string
  /** A short line under the name, set in mono: the command the panel is about, say. */
  hint?: string
}

const props = defineProps<{ tabs: Tab[]; label?: string }>()

const uid = useId()
const chosen = ref(props.tabs[0]?.id ?? '')
const root = ref<HTMLElement>()
const bar = ref<HTMLElement>()

// Where the red bar is: under the chosen tab, measured, since the tabs are as wide as their words.
const ink = ref({ left: 0, width: 0 })
const moving = ref(false)
const entered = ref('')
function place() {
  const at = props.tabs.findIndex((tab) => tab.id === chosen.value)
  const button = bar.value?.querySelectorAll<HTMLElement>('[role=tab]')[at]
  if (!button) return
  ink.value = { left: button.offsetLeft, width: button.offsetWidth }
}
const inkStyle = computed(() => ({ transform: `translateX(${ink.value.left}px)`, width: `${ink.value.width}px` }))

let settling: ReturnType<typeof setTimeout> | undefined
watch(chosen, (now, was) => {
  if (now === was) return
  entered.value = now
  moving.value = true
  clearTimeout(settling)
  settling = setTimeout(() => (moving.value = false), 450)
  void nextTick(place)
})
let sized: ResizeObserver | undefined

// The keys the WAI-ARIA tabs pattern moves by: the arrows step, Home and End jump.
function move(event: KeyboardEvent, at: number) {
  const last = props.tabs.length - 1
  const to =
    event.key === 'ArrowRight'
      ? (at + 1) % props.tabs.length
      : event.key === 'ArrowLeft'
        ? (at + last) % props.tabs.length
        : event.key === 'Home'
          ? 0
          : event.key === 'End'
            ? last
            : -1
  if (to < 0) return
  event.preventDefault()
  chosen.value = props.tabs[to].id
  // The buttons are siblings in the order of `tabs`, which is the order `to` counts in.
  const buttons = (event.currentTarget as HTMLElement).parentElement?.children
  ;(buttons?.[to] as HTMLElement | undefined)?.focus()
}

// Opens the panel holding whatever the address's `#fragment` names, if one of these does.
function follow() {
  const named = decodeURIComponent(location.hash.slice(1))
  if (!named || !root.value) return
  const target = document.getElementById(named)
  if (!target) return
  const panels = root.value.querySelectorAll(':scope > [role=tabpanel]')
  panels.forEach((panel, at) => {
    if (panel.contains(target) && props.tabs[at]) {
      chosen.value = props.tabs[at].id
      requestAnimationFrame(() => target.scrollIntoView())
    }
  })
}

onMounted(() => {
  follow()
  place()
  sized = new ResizeObserver(place)
  if (bar.value) sized.observe(bar.value)
  window.addEventListener('hashchange', follow)
})

onUnmounted(() => {
  sized?.disconnect()
  clearTimeout(settling)
  window.removeEventListener('hashchange', follow)
})
</script>

<template>
  <div ref="root" class="hmz-tabs">
    <div ref="bar" class="bar" role="tablist" :aria-label="label">
      <button
        v-for="(tab, at) in tabs"
        :id="`${uid}-tab-${tab.id}`"
        :key="tab.id"
        type="button"
        role="tab"
        :aria-selected="chosen === tab.id"
        :aria-controls="`${uid}-panel-${tab.id}`"
        :tabindex="chosen === tab.id ? 0 : -1"
        @click="chosen = tab.id"
        @keydown="move($event, at)"
      >
        <span class="name">{{ tab.name }}</span>
        <span v-if="tab.hint" class="hint">{{ tab.hint }}</span>
      </button>
      <span class="ink" :class="{ moving }" :style="inkStyle" aria-hidden="true"></span>
    </div>
    <div
      v-for="tab in tabs"
      v-show="chosen === tab.id"
      :id="`${uid}-panel-${tab.id}`"
      :key="tab.id"
      class="panel"
      :class="{ entering: entered === tab.id }"
      role="tabpanel"
      :aria-labelledby="`${uid}-tab-${tab.id}`"
    >
      <slot :name="tab.id" />
    </div>
  </div>
</template>

<style scoped>
.hmz-tabs {
  margin: 20px 0 28px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--vp-c-bg);
  overflow: hidden;
}

.bar {
  position: relative;
  display: flex;
  gap: 6px;
  padding: 6px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--hmz-panel-bg);
}

.bar button {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 9px 14px;
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--vp-c-text-2);
  text-align: left;
  cursor: pointer;
  transition:
    background 0.2s,
    border-color 0.2s,
    color 0.2s;
}

.bar button:hover {
  color: var(--vp-c-text-1);
}

.bar button[aria-selected='true'] {
  border-color: var(--hmz-panel-border);
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
}

/* The chosen tab's mark: a red bar along the foot of the tab bar, which slides to the tab
   chosen next and leans into the move while it travels. */
.ink {
  position: absolute;
  left: 0;
  bottom: -2px;
  height: 4px;
  background: var(--hmz-red);
  transition:
    transform 0.45s cubic-bezier(0.7, 0, 0.2, 1),
    width 0.45s cubic-bezier(0.7, 0, 0.2, 1);
}

.ink.moving {
  animation: hmz-lean 0.45s cubic-bezier(0.7, 0, 0.2, 1);
}

@keyframes hmz-lean {
  50% {
    clip-path: polygon(6% 0, 100% 0, 94% 100%, 0 100%);
    scale: 1 1.6;
  }
}

/* The panel coming in: wiped in on the diagonal, its contents rising a little behind it. */
.panel.entering {
  animation: hmz-wipe 0.55s cubic-bezier(0.16, 1, 0.3, 1);
}

.panel.entering > :deep(*) {
  animation: hmz-rise 0.6s cubic-bezier(0.16, 1, 0.3, 1) backwards;
}

.panel.entering > :deep(*:nth-child(2)) {
  animation-delay: 0.04s;
}

.panel.entering > :deep(*:nth-child(3)) {
  animation-delay: 0.08s;
}

.panel.entering > :deep(*:nth-child(n + 4)) {
  animation-delay: 0.12s;
}

@keyframes hmz-wipe {
  from {
    clip-path: polygon(0 0, 0 0, 0 100%, 0 100%);
  }
  to {
    clip-path: polygon(0 0, 200% 0, 100% 100%, 0 100%);
  }
}

@keyframes hmz-rise {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
}

.bar button:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 1px;
}

.name {
  font-size: 14.5px;
  font-weight: 650;
  line-height: 1.4;
}

.hint {
  max-width: 100%;
  overflow: hidden;
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel {
  padding: 2px 22px 8px;
}

/* A panel is a page in miniature, so it keeps the page's measure for prose. */
.panel > :deep(p),
.panel > :deep(ul),
.panel > :deep(ol) {
  max-width: 46rem;
}

@media (max-width: 639px) {
  .panel {
    padding: 2px 16px 6px;
  }

  /* The theme bleeds a code block to the screen's edge at this width, which inside a panel
     is past its border: out to the panel's edge instead. */
  .panel :deep(div[class*='language-']),
  .panel :deep(.vp-code-group .tabs) {
    margin-left: -16px;
    margin-right: -16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .bar button,
  .ink {
    transition: none;
  }

  .ink.moving,
  .panel.entering,
  .panel.entering > :deep(*) {
    animation: none;
  }
}
</style>
