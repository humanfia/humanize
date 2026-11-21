<script setup lang="ts">
// The Humanize page: docs/index.md is this component and nothing else. It is the project's page
// on humanfia.ai (humanfia.ai/humanize/) and the front page of its documentation at once.
//
// A product page, as an open-source project's home page is one: what it is and the button that
// gets it (the hero), what it does (six cards), which agents it runs, what it looks like, how to
// install it, and the way into each section of the documentation. How it works is those
// sections' to say, and which flows there are is the Flows pages' on humanfia.ai.
//
// Its pictures are reels of the real interfaces, written by tests/system/docs/test_docs_home.py:
// SVG files that play by themselves in an <img>, and stand still for a reader who asked for less
// motion. Each is given the size of its file, so the page keeps its place before it loads.
//
// The page's own motion is switched on by one class, after mount, and only when the reader
// allows it: the server-rendered page, and a reader who asked for less motion, see every section
// at rest.
import { withBase } from 'vitepress'
import { onMounted, ref } from 'vue'
import Install from './Install.vue'
import { prefersReducedMotion, vReveal } from './motion'
import HzHero from './HzHero.vue'
import { AGENTS, FEATURES, HUMANFIA, REPO } from './data'
import './palette.css'
import './humanize.css'

const motion = ref(false)
onMounted(() => (motion.value = !prefersReducedMotion()))

// A path is a page of these docs; anything else is written out in full, and is humanfia.ai's
// or GitHub's.
const link = (href: string) => (href.startsWith('/') ? withBase(href) : href)

// The way into the documentation, a section each; the flows, which are humanfia.ai's; and the
// source, which is where contributing is written.
const NEXT = [
  { kicker: 'Docs', title: 'Tutorials', body: 'Walk through one complete job per tutorial, starting with your first task.', href: '/tutorials/' },
  { kicker: 'Docs', title: 'User Guide', body: 'Learn one feature per page across the app, browser, terminal and CLI.', href: '/user/' },
  { kicker: 'Docs', title: 'Builder Guide', body: 'Write your own flows in Python with loops, budgets, hooks, worktrees and tests.', href: '/builder/' },
  { kicker: 'Docs', title: 'Reference', body: 'Look up every command, key, setting and Python call.', href: '/reference/' },
  { kicker: 'Flows', title: 'Browse the flows', body: 'Read how each official flow works.', href: `${HUMANFIA}/flows/` },
  { kicker: 'Source', title: 'Source and contributing', body: 'Find the code and contributing guide on GitHub. Apache-2.0.', href: `${REPO}/blob/main/CONTRIBUTING.md` },
]
</script>

<template>
  <div class="hz-root" :class="{ 'hz-motion': motion }">
    <HzHero :motion="motion" />

    <!-- What it does ------------------------------------------------------------------------ -->
    <section id="what-it-does" class="hz-band alt">
      <div class="hz-wrap">
        <header class="hz-head" v-reveal>
          <p class="hz-num">What it does</p>
          <h2 class="hz-h2">Hand a flow a task. <span class="hz-accent">It runs the agents until the task is done.</span></h2>
        </header>
        <ul class="hz-feats">
          <li v-for="(f, i) in FEATURES" :key="f.title" v-reveal="(i % 3) * 60">
            <a :href="link(f.href)" class="hz-feat">
              <h3>{{ f.title }}</h3>
              <p>{{ f.body }}</p>
              <span class="go" aria-hidden="true">→</span>
            </a>
          </li>
        </ul>
      </div>
    </section>

    <!-- Agents ------------------------------------------------------------------------------ -->
    <section id="every-harness" class="hz-band tight">
      <div class="hz-wrap">
        <header class="hz-head" v-reveal>
          <p class="hz-num">Works with</p>
          <h2 class="hz-h2">Thirteen coding agents, <span class="hz-accent">and any agent that speaks ACP.</span></h2>
        </header>
        <ul class="hz-agents" v-reveal="80">
          <li v-for="a in AGENTS" :key="a">{{ a }}</li>
          <li class="more">any ACP agent</li>
          <li class="more">any model, through LiteLLM</li>
        </ul>
      </div>
    </section>

    <!-- See it run -------------------------------------------------------------------------- -->
    <section id="see-it-run" class="hz-band alt">
      <div class="hz-wrap">
        <header class="hz-head" v-reveal>
          <p class="hz-num">See it run</p>
          <h2 class="hz-h2">In the terminal, <span class="hz-accent">or as one command.</span></h2>
        </header>
        <div class="hz-reels">
          <figure v-reveal>
            <img
              :src="withBase('/shots/home-terminal.svg')"
              width="1190"
              height="786"
              loading="lazy"
              decoding="async"
              alt="The terminal interface: pick a flow with /flow, set a budget, and enter a task to run its agents to the end."
            />
            <figcaption>In <code>hmz</code>: pick a flow with <code>/flow</code>, set its budget, then give it the task.</figcaption>
          </figure>
          <figure v-reveal="120">
            <img
              :src="withBase('/shots/home-cli.svg')"
              width="1092"
              height="368"
              loading="lazy"
              decoding="async"
              alt="A terminal running hmz exec with a flow and a task, printing each agent step and the final answer."
            />
            <figcaption><code>hmz exec -f goal</code> runs a flow on one task and prints each step.</figcaption>
          </figure>
        </div>
      </div>
    </section>

    <!-- Get started ------------------------------------------------------------------------- -->
    <section id="get-started" class="hz-band hz-ink hz-start">
      <span id="where-to-go-next" class="hz-alias" aria-hidden="true" />
      <div class="hz-wrap">
        <header class="hz-head" v-reveal>
          <p class="hz-num">Get started</p>
          <h2 class="hz-h2">Download the app, <span class="hz-accent">or install the CLI.</span></h2>
          <p class="hz-lead">Free and open source on macOS, Windows and Linux.</p>
        </header>
        <div v-reveal="80"><Install /></div>
        <aside class="hz-warn" v-reveal>
          <b>Heads up</b>
          <p>
            Agents in a flow edit files and run commands without asking for approval. Start in a
            scratch repository, and read <a :href="withBase('/user/security')">Security →</a> before
            you run a flow on important work.
          </p>
        </aside>
        <ul class="hz-next">
          <li v-for="(n, i) in NEXT" :key="n.title" v-reveal="i * 80">
            <a :href="link(n.href)">
              <span class="k">{{ n.kicker }}</span>
              <b>{{ n.title }}</b>
              <span class="t">{{ n.body }}</span>
              <span class="go" aria-hidden="true">→</span>
            </a>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* ---- what it does ---------------------------------------------------------------------- */

.hz-feats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  margin: 0;
  padding: 1px;
  list-style: none;
  background: var(--hz-line);
}
.hz-feats li {
  margin: 0;
}
.hz-feat {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 28px 26px 30px;
  color: inherit;
  background: var(--hz-bg);
  transition: background-color 0.3s;
}
.hz-feat::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 4px;
  background: var(--hz-mark);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.5s var(--hz-ease);
}
.hz-feat:hover {
  background: var(--hz-card);
}
.hz-feat:hover::before {
  transform: scaleX(1);
}
.hz-feat h3 {
  margin: 0;
  padding-right: 28px;
  font-size: 22px;
  line-height: 1.18;
  letter-spacing: -0.025em;
  font-weight: 800;
  color: var(--hz-ink);
}
.hz-feat p {
  margin: 12px 0 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--hz-ink-2);
}
.hz-feat .go {
  position: absolute;
  top: 26px;
  right: 22px;
  font-size: 18px;
  color: var(--hz-ink-3);
  transition: transform 0.35s var(--hz-ease), color 0.3s;
}
.hz-feat:hover .go {
  transform: translateX(4px);
  color: var(--hf-cyan-deep);
}

/* ---- agents ---------------------------------------------------------------------------- */

.hz-agents {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.hz-agents li {
  margin: 0;
  padding: 10px 18px;
  border: 1px solid var(--hz-line);
  background: var(--hz-card);
  font-size: 16px;
  font-weight: 700;
  color: var(--hz-ink);
}
.hz-agents li.more {
  border-style: dashed;
  background: none;
  font-weight: 500;
  color: var(--hz-ink-2);
}

/* ---- see it run ------------------------------------------------------------------------ */

/* Two reels side by side, each at its own height: the terminal's screen and a command's output
   are not one shape, and neither is stretched to the other. */
.hz-reels {
  display: grid;
  grid-template-columns: minmax(0, 1.09fr) minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}
.hz-reels figure {
  margin: 0;
}
.hz-reels img {
  display: block;
  width: 100%;
  height: auto;
}
.hz-reels figcaption {
  margin-top: 12px;
  font-size: 14.5px;
  line-height: 1.55;
  color: var(--hz-ink-2);
}
.hz-reels code {
  padding: 1px 6px;
  font-size: 0.88em;
  color: var(--hz-ink);
  background: var(--hz-line-2);
}

/* ---- get started ----------------------------------------------------------------------- */

.hz-warn {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 12px 28px;
  margin-top: clamp(28px, 3vw, 40px);
  padding: 20px 24px;
  border-left: 8px solid var(--hz-mark);
  background: var(--hz-card);
}
.hz-warn b {
  font: 700 12px/1.6 var(--hz-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--hz-accent);
}
.hz-warn p {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--hz-ink);
}
.hz-warn a {
  font-weight: 700;
  color: var(--hz-accent);
}
.hz-warn a:hover {
  text-decoration: underline;
}
.hz-next {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  margin: clamp(40px, 5vw, 64px) 0 0;
  padding: 1px;
  list-style: none;
  background: var(--hz-line);
}
.hz-next li {
  margin: 0;
}
.hz-next a {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px 26px 26px;
  color: inherit;
  background: var(--hz-bg);
  transition: background-color 0.3s;
}
.hz-next a:hover {
  background: var(--hz-card);
}
.hz-next .k {
  font: 700 11px/1.3 var(--hz-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--hz-accent);
}
.hz-next b {
  margin-top: 14px;
  font-size: clamp(22px, 2vw, 28px);
  letter-spacing: -0.03em;
  font-weight: 800;
  color: var(--hz-ink);
}
.hz-next .t {
  margin-top: 8px;
  font-size: 14.5px;
  line-height: 1.55;
  color: var(--hz-ink-2);
}
.hz-next .go {
  position: absolute;
  top: 22px;
  right: 24px;
  font-size: 20px;
  color: var(--hz-ink-3);
  transition: transform 0.35s var(--hz-ease), color 0.3s;
}
.hz-next a:hover .go {
  transform: translate(3px, -3px);
  color: var(--hf-cyan-deep);
}

/* ---- narrow ---------------------------------------------------------------------------- */

@media (max-width: 1000px) {
  .hz-feats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 960px) {
  .hz-reels,
  .hz-next {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 600px) {
  .hz-feats,
  .hz-warn {
    grid-template-columns: minmax(0, 1fr);
  }
  .hz-agents li {
    padding: 8px 14px;
    font-size: 14.5px;
  }
}
</style>
