import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'

import { fileURLToPath } from 'node:url'

import { defineConfig, type SiteConfig } from 'vitepress'

import { chromeFor, loadChrome } from './humanfia/chrome'
import { SIDEBAR } from './sidebar'

// Deployed to https://humanfia.ai/humanize/ by .github/workflows/build-docs.yml.
// The domain belongs to the organisation's own Pages site (humanfia/humanfia.github.io, which is
// humanfia.ai), so this repository is a project page served under a subdirectory of it, and
// this site is Humanize's page on humanfia.ai as well as its documentation: the organisation's
// site has no page about Humanize of its own, and links here. `base` is that subdirectory:
// without it every
// stylesheet, script and link would ask for a path at the domain root, where nothing of this
// site is. Internal links are still written from the site's own root -- VitePress prepends
// the base to each of them -- so nothing in a page names the subdirectory.
const BASE = '/humanize/'
const HOST = 'https://humanfia.ai'

// The bar across the top and the footer are humanfia.ai's, read from that site (humanfia/chrome.ts):
// one site to a reader, whichever build drew the page. `HUMANFIA_ORIGIN` points its links at a
// local copy of the organisation's site, for looking at the two builds together.
const CHROME = chromeFor(await loadChrome(), BASE, process.env.HUMANFIA_ORIGIN || undefined)

/** A page of the organisation's build, loaded in the background once a pointer rests on a link
 *  to it, so the click that follows swaps to a page that is already drawn. A browser that does
 *  not know speculation rules ignores the script. */
const PRERENDER_THE_REST = JSON.stringify({
  prerender: [
    { where: { and: [{ href_matches: '/*' }, { not: { href_matches: `${BASE}*` } }] }, eagerness: 'moderate' },
  ],
})

// Where a page used to be, and where it is now: a path on this site, or the full URL of a page
// that left it. Guides were once one flat section serving two audiences at once; then a
// User Guide and a Weaver Guide, with the tutorials beside the audience each one
// taught. GitHub Pages serves files and nothing else, so a page that
// moved is a 404 for every bookmark and search result unless a file is left where it was --
// which is what `buildEnd` below writes, one small redirect apiece.
//
// This table is a record of what the paths once were rather than a second copy of what they
// are: nothing new belongs in it, and an entry only ever comes out if the page it names is
// finally allowed to go cold.
const MOVED_TO_USER = [
  'installation',
  'concepts',
  'security',
  'troubleshooting',
  'steering',
  'btw',
  'conversations',
  'details',
  'status',
  'board',
  'afk',
  'fallback',
  'completion',
  'history',
  'export',
  'settings',
  'stopping',
  'efforts',
  'permissions',
  'skills',
  'questions',
  'tally',
  'reporting',
  'providers',
  'containers',
  'remote-execution',
  'unattended',
  'ci',
  'tracing',
  'resuming',
]

const MOVED_TO_WEAVER = [
  'writing-a-flow',
  'loops',
  'flow-settings',
  'async-flows',
  'calling-flows',
  'goals',
  'shapes',
  'hooks',
  'tools',
  'human-agent',
  'worktrees',
  'testing-flows',
  'flowverses',
]

// And where a page moved a second time, which overrides the table above: `/status` is
// the monitor now, so the page about it is too, and both of the paths it has had send a reader on.
// Likewise `/providers`, `/fallback` and `/details` are pages of `/settings` now, and so are the
// pages that were about them.
const MOVED_AGAIN: Record<string, string> = {
  'guide/status': 'user/monitor',
  'user/status': 'user/monitor',
  'guide/providers': 'user/settings#accounts',
  'user/providers': 'user/settings#accounts',
  'guide/fallback': 'user/settings#nous',
  'user/fallback': 'user/settings#nous',
  'guide/details': 'user/settings#details',
  'user/details': 'user/settings#details',
  // The two app pages are one, Humanize Desktop, and how to install it is on Installation.
  'user/desktop-windows': 'user/install',
}

// Every flow had a page here, and has one at humanfia.ai now, under the same name: the flows
// are humanfia's catalogue rather than this tool's manual, so they left for the site that holds
// the rest of it.
const HUMANFIA_FLOWS = 'https://humanfia.ai/flows/'
const MOVED_TO_HUMANFIA = [
  'ralph-loop',
  'stateful-ralph',
  'continue-loop',
  'goal',
  'flame-chase',
  'ralph-loop-agent-cleanup',
  'flame-chase-agent-cleanup',
  'rlar',
  'humanize1',
  'aot',
  'parallel-flame-chase',
  'parallel-flame-chase-git-pr',
  'recursive-lean-prover',
]

// The four sections of today: Tutorials, a User Guide, a Builder Guide (which was Writing Flows)
// and Reference. Features became pages of the two guides, and Contributing left the site for
// CONTRIBUTING.md in the repository. Every path of the layout before has a way on here, and the
// tables above, which point into that layout, are followed through this one.
const CONTRIBUTING = 'https://github.com/humanfia/humanize/blob/main/CONTRIBUTING.md'
const ARCHITECTURE = 'https://github.com/humanfia/humanize/blob/main/ARCHITECTURE.md'
const MOVED_NOW: Record<string, string> = {
  'user/installation': 'user/install',
  'user/first-run': 'tutorials/first-task-terminal',
  'user/btw': 'user/side-questions',
  'user/conversations': 'user/chat',
  'user/board': 'user/steering',
  'user/afk': 'user/questions',
  'user/completion': 'user/install',
  'user/monitor': 'user/watch-a-run',
  'user/tally': 'user/usage',
  'user/containers': 'user/runtimes',
  'user/remote-execution': 'user/runtimes',
  'user/unattended': 'user/command-line',
  'user/ci': 'tutorials/nightly-in-ci',
  'user/tutorials/take-home': 'tutorials/',
  'user/tutorials/port-a-project': 'tutorials/',
  'user/tutorials/build-an-agent': 'tutorials/first-flow',
  'weaver/': 'builder/',
  'weaver/writing-a-flow': 'builder/flow',
  'weaver/loops': 'builder/loops',
  'weaver/flow-settings': 'builder/params',
  'weaver/async-flows': 'builder/async',
  'weaver/calling-flows': 'builder/calling-flows',
  'weaver/branching': 'builder/branching',
  'weaver/worktrees': 'builder/worktrees',
  'weaver/goals': 'builder/goals',
  'weaver/shapes': 'builder/shapes',
  'weaver/hooks': 'builder/hooks',
  'weaver/tools': 'builder/tools',
  'weaver/human-agent': 'builder/outworlder',
  'weaver/faces': 'builder/faces',
  'weaver/testing-flows': 'builder/testing',
  'weaver/flowverses': 'builder/publishing',
  'weaver/tutorials/build-under-test': 'tutorials/review-loop',
  'features/': 'user/',
  'features/capabilities': 'user/',
  'features/backends': 'user/agents',
  'features/accounts': 'user/accounts',
  'features/surfaces': 'user/',
  'features/steering': 'user/steering',
  'features/human': 'user/questions',
  'features/allowances': 'user/budgets',
  'features/daemon': 'user/daemon',
  'features/environments': 'user/environments',
  'features/anchor': 'user/runtimes',
  'features/tracing': 'user/tracing',
  'features/resuming': 'user/resuming',
  'features/flows': 'builder/flow',
  'features/concurrency': 'builder/async',
  'features/shapes': 'builder/shapes',
  'features/goals': 'builder/goals',
  'features/hooks': 'builder/hooks',
  'features/budgets': 'builder/budgets',
  'reference/providers': 'reference/agents',
  'reference/machines': 'reference/environments',
  'reference/remote-execution': 'reference/environments',
  'contributing/': CONTRIBUTING,
  'contributing/architecture': ARCHITECTURE,
  'contributing/ci': CONTRIBUTING,
  'contributing/docs': CONTRIBUTING,
  'contributing/releasing': 'https://github.com/humanfia/humanize/blob/main/RELEASING.md',
  'contributing/tutorials/first-patch': CONTRIBUTING,
  'contributing/tutorials/a-page-of-docs': CONTRIBUTING,
}

/** Where a page of an earlier layout is today: each table's answer followed through the next,
 *  dropping a fragment that named a heading of a page that has itself moved. */
function today(to: string): string {
  for (let hops = 0; hops < 8; hops++) {
    if (/^https?:\/\//.test(to)) return to
    const [path] = to.split('#')
    const next = MOVED_NOW[path]
    if (next === undefined) return to
    to = next
  }
  return to
}

const MOVED_BEFORE: Record<string, string> = {
  ...Object.fromEntries(MOVED_TO_USER.map((page) => [`guide/${page}`, `user/${page}`])),
  ...Object.fromEntries(MOVED_TO_WEAVER.map((page) => [`guide/${page}`, `weaver/${page}`])),
  'guide/': 'user/',
  'tutorials/': 'user/',
  // The quickstart is Your first run.
  'tutorials/quickstart': 'user/first-run',
  'tutorials/take-home': 'user/tutorials/take-home',
  'tutorials/port-a-project': 'user/tutorials/port-a-project',
  'tutorials/build-an-agent': 'user/tutorials/build-an-agent',
  ...Object.fromEntries(MOVED_TO_HUMANFIA.map((page) => [`flows/${page}`, `${HUMANFIA_FLOWS}${page}`])),
  'flows/': HUMANFIA_FLOWS,
  // `chat` was a flow, and is a session of its own now, no epic, with a page in the User Guide.
  'flows/chat': 'user/chat',
  // One page here once held both cleanup flows; each has its own now, and the first is where
  // it went.
  'flows/agent-cleanup': `${HUMANFIA_FLOWS}ralph-loop-agent-cleanup`,
  // The regression matrix is gone; the system tests, run a file at a time, took its place.
  'contributing/regression-matrix': 'contributing/',
  ...MOVED_AGAIN,
}

/** The paths that are pages today (`tutorials/` was once a redirect, and is a section again):
 *  a redirect is never written over one. */
const PAGES = new Set(
  Object.values(SIDEBAR)
    .flat()
    .flatMap((entry) => [entry, ...(entry.items ?? [])])
    .flatMap((entry) => (entry.link ? [entry.link.slice(1)] : [])),
)

const MOVED: Record<string, string> = Object.fromEntries(
  Object.entries({
    ...Object.fromEntries(Object.entries(MOVED_BEFORE).map(([from, to]) => [from, today(to)])),
    ...MOVED_NOW,
  }).filter(([from]) => !PAGES.has(from)),
)

/** Where a moved page is now: a path on this site, or a full URL on another. */
const wayTo = (to: string) => (/^https?:\/\//.test(to) ? to : `${BASE}${to}`)

export default defineConfig({
  base: BASE,
  title: 'Humanize',
  description: 'Orchestrate, execute, and observe agent flows',
  lang: 'en-US',
  cleanUrls: true,
  lastUpdated: true,

  // Listed in humanfia.ai's robots.txt beside the organisation site's own.
  sitemap: { hostname: `${HOST}${BASE}` },

  head: [
    // humanfia.ai's own icon and browser tint, from the domain's root: this is a page of that
    // site. `head` goes to the template as it is, so no base is prepended to these.
    ['link', { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' }],
    ['meta', { name: 'theme-color', content: '#141a1f' }],
    ['script', { type: 'speculationrules' }, PRERENDER_THE_REST],
  ],

  themeConfig: {
    // humanfia.ai's bar: no logo and no title, because the brand is the animated wordmark the
    // theme puts in the title link (theme/index.ts), and it goes to the organisation's front
    // page. The links are the organisation's sections. This site's own four -- Tutorials, User
    // Guide, Builder Guide, Reference -- are tabs at the head of every sidebar
    // (theme/humanfia/SectionNav.vue) and on the front page.
    siteTitle: false,
    logoLink: { link: CHROME.home, target: '_self', rel: 'home' },
    nav: CHROME.nav,

    // One sidebar per section, each opening with the section itself (sidebar.ts).
    sidebar: SIDEBAR,

    socialLinks: CHROME.socialLinks,

    editLink: {
      pattern: 'https://github.com/humanfia/humanize/edit/main/docs/:path',
      text: 'Edit this page on GitHub',
    },

    search: { provider: 'local' },

    outline: { level: [2, 3] },

    // The organisation's footer, and under it this project's own licence and copyright.
    footer: {
      message: CHROME.footer.message,
      copyright: 'Humanize is released under the Apache-2.0 licence · Copyright © 2026 Zijian Zhang',
    },
  },

  // One file per moved page, written after the build so no page has to pretend to be a
  // redirect. `cleanUrls` means GitHub Pages answers /humanize/guide/afk with guide/afk.html,
  // so that is the name each one is written under, and a path that ended in a slash is the
  // index.html of its directory.
  async buildEnd(site: SiteConfig) {
    await Promise.all(
      Object.entries(MOVED).map(async ([from, to]) => {
        const at = join(site.outDir, from.endsWith('/') ? `${from}index.html` : `${from}.html`)
        const way = wayTo(to)
        await mkdir(dirname(at), { recursive: true })
        await writeFile(
          at,
          [
            '<!doctype html>',
            '<html lang="en-US">',
            '<head>',
            '<meta charset="utf-8">',
            '<meta name="robots" content="noindex">',
            `<meta http-equiv="refresh" content="0; url=${way}">`,
            `<link rel="canonical" href="${new URL(way, HOST).href}">`,
            '<title>Humanize</title>',
            '</head>',
            `<body>This page moved to <a href="${way}">${way}</a>.</body>`,
            '</html>',
            '',
          ].join('\n'),
        )
      }),
    )
  },

  vite: {
    // The footer has no slot, so humanfia.ai's replaces the theme's outright.
    resolve: {
      alias: [
        {
          find: /^.*\/VPFooter\.vue$/,
          replacement: fileURLToPath(new URL('./theme/humanfia/SiteFooter.vue', import.meta.url)),
        },
      ],
    },
    plugins: [
      {
        // The same redirects while `pnpm dev` is running, where nothing has been built yet and
        // there is no file to serve. Without it an old path is a 404 in development and a
        // redirect in production, which is the sort of difference nobody finds until it is
        // deployed.
        name: 'hmz-moved',
        configureServer(server) {
          server.middlewares.use((req, res, next) => {
            const asked = (req.url ?? '').split('?')[0]
            if (!asked.startsWith(BASE)) return next()
            const to = MOVED[asked.slice(BASE.length)]
            if (to === undefined) return next()
            res.statusCode = 302
            res.setHeader('location', wayTo(to))
            res.end()
          })
        },
      },
    ],
  },
})
