<script setup lang="ts">
// The way between this site's sections, at the head of every sidebar. The bar across the top
// is humanfia.ai's and names the organisation's sections, not Humanize's, so the sections of
// the documentation are named here: Humanize's own page first, then each guide.
import { useData, withBase } from 'vitepress'

const SECTIONS = [
  { text: 'Overview', link: '/' },
  { text: 'User Guide', link: '/user/' },
  { text: 'Writing Flows', link: '/weaver/' },
  { text: 'Features', link: '/features/' },
  { text: 'Reference', link: '/reference/' },
  { text: 'Contributing', link: '/contributing/' },
]

const { page } = useData()
const here = (link: string) => (link === '/' ? page.value.relativePath === 'index.md' : page.value.relativePath.startsWith(link.slice(1)))
</script>

<template>
  <nav class="hf-sections" aria-label="Humanize sections">
    <p>Humanize</p>
    <ul>
      <li v-for="s in SECTIONS" :key="s.link">
        <a :href="withBase(s.link)" :class="{ on: here(s.link) }" :aria-current="here(s.link) ? 'true' : undefined">{{ s.text }}</a>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.hf-sections {
  padding: 18px 0 16px;
  border-bottom: 1px solid var(--vp-c-divider);
  font-family: var(--vp-font-family-mono);
}
.hf-sections p {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}
.hf-sections ul {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.hf-sections a {
  display: block;
  padding: 3px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 2px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
  text-decoration: none;
  transition: color 0.2s, border-color 0.2s, background-color 0.2s;
}
.hf-sections a:hover {
  color: var(--vp-c-text-1);
  border-color: var(--vp-c-text-3);
}
.hf-sections a.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}
</style>
