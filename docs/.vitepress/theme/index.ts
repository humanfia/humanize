// The page at the site's root is the product page (components/product/, which index.md imports
// itself), the features landing is a
// set of diagrams rather than a page of prose, each feature page is one diagram of its own, and
// a tutorial plays the loop of the flow it runs -- so the theme exists to register them.
// Everything else is VitePress's default theme untouched: the two role guides, contributing
// and reference render exactly as they did.
import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import { h } from 'vue'

import HmzAccounts from './components/HmzAccounts.vue'
import HmzAnchor from './components/HmzAnchor.vue'
import HmzBackends from './components/HmzBackends.vue'
import HmzCast from './components/HmzCast.vue'
import HmzDaemon from './components/HmzDaemon.vue'
import HmzFeatures from './components/HmzFeatures.vue'
import HmzFlow from './components/flow/FlowPlayer.vue'
import HmzGoal from './components/HmzGoal.vue'
import HmzLoops from './components/HmzLoops.vue'
import HmzMap from './components/HmzMap.vue'
import HmzMoments from './components/HmzMoments.vue'
import HmzOrchestra from './components/HmzOrchestra.vue'
import HmzPerson from './components/HmzPerson.vue'
import HmzResume from './components/HmzResume.vue'
import HmzShape from './components/HmzShape.vue'
import HmzStack from './components/HmzStack.vue'
import HmzSteer from './components/HmzSteer.vue'
import HmzSyscalls from './components/HmzSyscalls.vue'
import HmzSurfaces from './components/HmzSurfaces.vue'
import HmzTimeline from './components/HmzTimeline.vue'
import HmzTurns from './components/HmzTurns.vue'
import SectionNav from './humanfia/SectionNav.vue'
import Wordmark from './humanfia/Wordmark.vue'
import './style.css'
import './humanfia/chrome.css'

export default {
  extends: DefaultTheme,
  // humanfia.ai's chrome (humanfia/): its wordmark in the bar's title link, where the config
  // sets no logo and no title; and this site's own sections at the head of every sidebar, since
  // the bar names the organisation's.
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      'nav-bar-title-after': () => h(Wordmark),
      'sidebar-nav-before': () => h(SectionNav),
    }),
  enhanceApp({ app, router, siteData }) {
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
    app.component('HmzAccounts', HmzAccounts)
    app.component('HmzAnchor', HmzAnchor)
    app.component('HmzBackends', HmzBackends)
    app.component('HmzCast', HmzCast)
    app.component('HmzDaemon', HmzDaemon)
    app.component('HmzFeatures', HmzFeatures)
    app.component('HmzFlow', HmzFlow)
    app.component('HmzGoal', HmzGoal)
    app.component('HmzLoops', HmzLoops)
    app.component('HmzMap', HmzMap)
    app.component('HmzMoments', HmzMoments)
    app.component('HmzOrchestra', HmzOrchestra)
    app.component('HmzPerson', HmzPerson)
    app.component('HmzResume', HmzResume)
    app.component('HmzShape', HmzShape)
    app.component('HmzStack', HmzStack)
    app.component('HmzSteer', HmzSteer)
    app.component('HmzSyscalls', HmzSyscalls)
    app.component('HmzSurfaces', HmzSurfaces)
    app.component('HmzTimeline', HmzTimeline)
    app.component('HmzTurns', HmzTurns)
  },
} satisfies Theme
