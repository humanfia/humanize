// The page at the site's root is the project's page (home/, which index.md imports
// itself). Everything else is VitePress's default theme: four sections of Markdown whose pictures
// are SVG files under public/ -- the real interface, captured (tests/system/docs/), and diagrams.
import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import { h } from 'vue'

import SectionNav from './humanfia/SectionNav.vue'
import Wordmark from './humanfia/Wordmark.vue'
import './style.css'
import './humanfia/chrome.css'

export default {
  extends: DefaultTheme,
  // humanfia.ai's chrome (humanfia/): its wordmark in the bar's title link, where the config
  // sets no logo and no title; and this site's own sections as tabs at the head of every sidebar,
  // since the bar names the organisation's.
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      'nav-bar-title-after': () => h(Wordmark),
      'sidebar-nav-before': () => h(SectionNav),
    }),
  enhanceApp({ router, siteData }) {
    // This site is served under humanfia.ai, at its base (/humanize/), beside the organisation's
    // own site and every other project's: the same origin, and none of them this build. The
    // router takes a click on any same-origin link for a page of its own and answers one it has
    // not got with its 404, so a link that leaves the base -- humanfia.ai/flows/ -- is handed to
    // the browser instead.
    router.onBeforeRouteChange = (to) => {
      if (typeof window === 'undefined') return
      const url = new URL(to, window.location.origin)
      if (url.origin !== window.location.origin || url.pathname.startsWith(siteData.value.base)) return
      window.location.assign(url.href)
      return false
    }
  },
} satisfies Theme
