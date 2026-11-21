<script setup lang="ts">
// The documentation's four sections, as tabs at the head of every sidebar. The bar across the
// top is humanfia.ai's and names the organisation's sections, not Humanize's; the project's own
// page is reached from there (Projects, then Humanize) and by the name above the tabs.
import { useData, withBase } from 'vitepress'

const SECTIONS = [
  { text: 'Tutorials', link: '/tutorials/' },
  { text: 'User Guide', link: '/user/' },
  { text: 'Builder Guide', link: '/builder/' },
  { text: 'Reference', link: '/reference/' },
]

const { page } = useData()
const here = (link: string) => page.value.relativePath.startsWith(link.slice(1))
</script>

<template>
  <nav class="hf-sections" aria-label="Humanize documentation">
    <p><a :href="withBase('/')">Humanize</a></p>
    <ul role="tablist">
      <li v-for="s in SECTIONS" :key="s.link" role="presentation">
        <a :href="withBase(s.link)" role="tab" :class="{ on: here(s.link) }" :aria-selected="here(s.link)">{{ s.text }}</a>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.hf-sections {
  padding: 18px 0 0;
  border-bottom: 1px solid var(--vp-c-divider);
}
.hf-sections p {
  margin: 0 0 10px;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.hf-sections p a {
  color: var(--vp-c-text-3);
  text-decoration: none;
}
.hf-sections p a:hover {
  color: var(--vp-c-text-1);
}
.hf-sections ul {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.hf-sections li a {
  display: block;
  padding: 7px 2px;
  margin-bottom: -1px;
  border-bottom: 2px solid transparent;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--vp-c-text-2);
  text-decoration: none;
  transition: color 0.2s, border-color 0.2s;
}
.hf-sections li a:hover {
  color: var(--vp-c-text-1);
}
.hf-sections li a.on {
  border-bottom-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}
</style>
