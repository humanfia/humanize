<script setup lang="ts">
// The Humanize page: docs/index.md is this component and nothing else. It is the project's page
// on humanfia.ai (humanfia.ai/humanize/) and the front page of its documentation at once.
//
// A product page, as an open-source project's home page is one: what it is and the button that
// gets it (the hero), why it is worth it (the ablation), what you get (six cards), which agents
// it runs, what it looks like, how to install it, and the way into each section of the
// documentation. How it works inside is those sections' to say, and which flows there are is
// the Flows pages' on humanfia.ai.
//
// Motion is switched on by one class, after mount, and only when the reader allows it: the
// server-rendered page, and a reader who asked for less motion, see every section at rest.
import { withBase } from 'vitepress'
import { onMounted, ref } from 'vue'
import NumberTicker from './NumberTicker.vue'
import Install from './Install.vue'
import { prefersReducedMotion, vReveal } from './motion'
import DemoVideo from './DemoVideo.vue'
import HzAblation from './HzAblation.vue'
import HzHero from './HzHero.vue'
import { AGENTS, FEATURES, HUMANFIA } from './data'
import './palette.css'
import './humanize.css'

const motion = ref(false)
onMounted(() => (motion.value = !prefersReducedMotion()))

// A path is a page of these docs; anything else is written out in full, and is humanfia.ai's.
const link = (href: string) => (href.startsWith('/') ? withBase(href) : href)

// The way into the documentation, a section each, and the flows, which are humanfia.ai's.
const NEXT = [
  { kicker: 'Docs', title: 'User Guide', body: 'Running flows: the app, the terminal and the browser, agents and accounts, and reading a run back.', href: '/user/' },
  { kicker: 'Docs', title: 'Writing Flows', body: 'Your own flow, in Python: loops, goals, hooks and worktrees, and how to test one.', href: '/weaver/' },
  { kicker: 'Docs', title: 'Features', body: 'How Humanize works, drawn: one diagram per capability.', href: '/features/' },
  { kicker: 'Docs', title: 'Reference', body: 'Every command, key, flag and Python call, spelled out.', href: '/reference/' },
  { kicker: 'Flows', title: 'Browse the flows', body: 'Every loop there is to run, each played step by step.', href: `${HUMANFIA}/flows/` },
  { kicker: 'Source', title: 'Contributing', body: 'Working on Humanize itself: the layers, the checks, and these docs. Apache-2.0.', href: '/contributing/' },
]
</script>

<template>
  <div class="hz-root" :class="{ 'hz-motion': motion }">
    <HzHero :motion="motion" />

    <!-- Why ------------------------------------------------------------------------------- -->
    <section id="what-the-loop-is-worth" class="hz-band hz-ink">
      <div class="hz-wrap">
        <div class="hz-proof">
          <div class="hz-proof-num" v-reveal>
            <p class="hz-num">Same model, better results</p>
            <p class="hz-big"><NumberTicker :value="47" :from="1" :duration="1800" /><small>/50</small></p>
            <p class="hz-lead">
              PutnamBench problems Kimi-K3 solved inside a Humanize flow, against <b>4</b> through
              its own coding CLI alone.
            </p>
          </div>
          <div class="hz-proof-chart" v-reveal="120">
            <HzAblation />
          </div>
        </div>
      </div>
    </section>

    <!-- What you get ------------------------------------------------------------------------ -->
    <section id="what-it-does" class="hz-band">
      <div class="hz-wrap">
        <header class="hz-head" v-reveal>
          <p class="hz-num">What you get</p>
          <h2 class="hz-h2">Hand the agent a task. <span class="hz-accent">Come back to it done.</span></h2>
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
    <section id="every-harness" class="hz-band alt tight">
      <div class="hz-wrap">
        <header class="hz-head" v-reveal>
          <p class="hz-num">Works with</p>
          <h2 class="hz-h2">Thirteen coding agents, <span class="hz-accent">and any that speaks ACP.</span></h2>
        </header>
        <ul class="hz-agents" v-reveal="80">
          <li v-for="a in AGENTS" :key="a">{{ a }}</li>
          <li class="more">any ACP agent</li>
          <li class="more">any model, through litellm</li>
        </ul>
      </div>
    </section>

    <!-- Demos ------------------------------------------------------------------------------- -->
    <section id="the-real-thing-recorded" class="hz-band">
      <div class="hz-wrap">
        <header class="hz-head" v-reveal>
          <p class="hz-num">See it run</p>
          <h2 class="hz-h2">One line from your shell, <span class="hz-accent">or a few keys in the app.</span></h2>
        </header>
        <div class="hz-videos">
          <div v-reveal>
            <DemoVideo
              :src="withBase('/media/ralph-loop-cli.mp4')"
              :poster="withBase('/media/ralph-loop-cli.webp')"
              title="A Ralph loop started with hmz exec: two fresh rounds, each picking up from the repository"
              caption="hmz exec -f ralph_loop: two rounds, each in a fresh session, finish TASK.md."
            />
          </div>
          <div v-reveal="120">
            <DemoVideo
              :src="withBase('/media/ralph-loop-tui.mp4')"
              :poster="withBase('/media/ralph-loop-tui.webp')"
              title="The same Ralph loop from inside hmz: /flow, choose ralph_loop, set up the agent, save, then the task"
              caption="The same loop from inside hmz: pick it with /flow, set up its agent, give it the task."
            />
          </div>
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
          <p class="hz-lead">Free and open source, on macOS, Windows and Linux.</p>
        </header>
        <div v-reveal="80"><Install /></div>
        <aside class="hz-warn" v-reveal>
          <b>Heads up</b>
          <p>
            Agents in a flow work without asking for approval: they edit files and run commands on
            their own. Start in a scratch repository, and read
            <a :href="withBase('/user/security')">Security →</a> before pointing one at work you care
            about.
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
/* ---- why ------------------------------------------------------------------------------- */

.hz-proof {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
  gap: clamp(32px, 6vw, 96px);
  align-items: center;
}
.hz-proof .hz-num {
  margin-bottom: 28px;
}
.hz-big {
  display: flex;
  align-items: baseline;
  margin: 0 0 24px;
  font-size: clamp(120px, 17vw, 260px);
  line-height: 0.8;
  letter-spacing: -0.07em;
  font-weight: 800;
  color: var(--hf-cyan-deep);
  font-variant-numeric: tabular-nums;
}
.hz-big small {
  margin-left: 0.06em;
  font-size: 0.3em;
  letter-spacing: -0.04em;
  color: var(--hz-ink-3);
}
.hz-proof .hz-lead b {
  color: var(--hz-ink);
}

/* ---- what you get ---------------------------------------------------------------------- */

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

/* ---- demos ----------------------------------------------------------------------------- */

.hz-videos {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
}
.hz-videos :deep(.demo) {
  margin: 0;
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
  .hz-proof,
  .hz-videos,
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
