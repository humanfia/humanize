<script setup lang="ts">
// A terminal screen drawn by hand, for the "at the prompt" pages. The recorded screens are
// the GIFs under /demo/; this one is a drawing, and says so in its corner.
//
// What goes in the slot is a <pre>, with a few span classes for the colours the interface
// uses: `d` dim, `m` muted, `p` the purple of a highlighted row, `a` the teal of the status
// dot, `r` an error, `y` a warning, `b` bold, `hl` a highlighted row.
withDefaults(defineProps<{ title?: string; tag?: string }>(), {
  title: 'hmz',
  tag: 'drawn, not recorded',
})
</script>

<template>
  <figure class="up-term">
    <figcaption>
      <span class="dots" aria-hidden="true"><i /><i /><i /></span>
      <span class="title">{{ title }}</span>
      <span class="tag">{{ tag }}</span>
    </figcaption>
    <div class="screen"><slot /></div>
  </figure>
</template>

<style scoped>
.up-term {
  margin: 20px 0 26px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-code-block-bg);
  overflow: hidden;
}

figcaption {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.dots {
  display: inline-flex;
  gap: 5px;
}

.dots i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--vp-c-divider);
}

.title {
  color: var(--vp-c-text-2);
}

.tag {
  margin-left: auto;
  font-style: italic;
}

.screen {
  overflow-x: auto;
  padding: 12px 16px;
}

.screen :slotted(pre) {
  margin: 0;
  padding: 0;
  background: none;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
  white-space: pre;
}

.screen :slotted(.d) {
  color: var(--vp-c-text-3);
}

.screen :slotted(.m) {
  color: var(--vp-c-text-2);
}

.screen :slotted(.p) {
  color: var(--hmz-accent-2);
}

.screen :slotted(.a) {
  color: var(--hmz-accent);
}

.screen :slotted(.r) {
  color: var(--vp-c-danger-1);
}

.screen :slotted(.y) {
  color: var(--vp-c-warning-1);
}

.screen :slotted(.b) {
  font-weight: 700;
}

.screen :slotted(.hl) {
  background: var(--vp-c-default-soft);
}

@media (max-width: 640px) {
  .screen {
    padding: 10px 12px;
  }

  .screen :slotted(pre) {
    font-size: 11.5px;
  }
}
</style>
