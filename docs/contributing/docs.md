# Working on these docs

This page is the rules a page of these docs is held to, and how to check a page meets them
before a reader does: where it goes, the shape a guide takes, how it is written, what a
component on it must do, and how to look at it. [Add a page to these
docs](/contributing/tutorials/a-page-of-docs) walks one page through from start to pull
request.

::: info Before you start
Node and [pnpm](https://pnpm.io/). The site is [VitePress](https://vitepress.dev/) under
`docs/`, and builds without humanize installed.
:::

## Run it

```sh
cd docs
corepack enable    # once: gives you the pnpm that package.json pins
pnpm install
pnpm dev           # http://localhost:5173/humanize/
```

Before you push, run what CI runs:

```sh
pnpm build           # fails on a dead internal link
pnpm check:anchors   # fails on a dead #fragment
pnpm check:legible   # fails on a diagram's word drawn under 11px on a phone
```

`check:legible` takes every scene on the Flows and Features pages, and on any other page,
through in Chromium, at phone and tablet widths, moving and held still, and measures every word
it draws. A moving scene is not played on a clock but held at one moment of its timeline after
another, so a busy machine gets the same answer as an idle one. A word may be drawn small while
it pops in, for under 0.3s of the scene's time, but never where the scene comes to rest: where a
chapter ends or a step lands. The first run wants the browser:
`pnpm exec playwright install chromium`. `--page flows/rlar --width 390` looks at one page, and
`--overlap` also lists words drawn over each other, for you to look at.

## Where a page goes

Each section answers one kind of question. A page that answers two is two pages.

| Section | The reader wants | A page there |
| --- | --- | --- |
| **Features** | to understand | One feature, built around a diagram the reader can push. **No commands and no code**: a guide is one click away |
| **Flows** | to pick a flow | One flow, opening with its `hmz exec` line and the shape of its loop |
| **User Guide** | to do something | One task for the person running flows, as a [guide page](#the-shape-of-a-guide-page). No Python |
| **Weaver Guide** | to write a flow | The same, for whoever writes the flow. Every example a complete flow that runs |
| **Contributing** | to change humanize | Setup, checks, the layers, and this, as guide pages too |
| **Reference** | to look something up | Exact, complete and scannable: every flag, key, argument and return |

The three guide sections open with a **Tutorials** group: taken in order, every command
written out, nothing for the reader to choose.

### The shape of a guide page

Every page in the User Guide, the Weaver Guide and Contributing is a guide: it gets one reader
to one result. It has these parts, in this order, and drops the ones it has nothing for:

````md
# Hooks

In this guide you hang your own code on the moments of an agent's sessions. You build
`watched`, which prints every tool its agent reaches for. <!-- ① -->

Reach for a hook to watch an agent, or to refuse something it reaches for.

::: info Before you start <!-- ② -->
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
:::

## How it works <!-- ③ -->

## Example: watch the agent <!-- ④ -->

```python
# .hmz/flows/watched/__init__.py
async def seen(params: PreToolUseHookParams) -> PreToolUseHookResult:  # ①
```

### What each part does <!-- ⑤ -->

1. **`seen`** is a hook for the moment a tool is about to run.

### Run it <!-- ⑥ -->

### Check it worked <!-- ⑦ -->

## Variations <!-- ⑧ -->

## Pitfalls

## Next steps <!-- ⑨ -->
````

1. **The goal.** What the reader will have done or built by the end, then when to reach for
   it. The first screen answers "is this the page I need?".
2. **Before you start.** What the reader needs already, each with a link to where they get it.
3. **How it works.** The idea, with its terms introduced where they are used: enough to read
   the example, and no more. A table of options goes here.
4. **A worked example.** Complete: a flow, a test, a command, never a fragment the reader has
   to finish. A file's path is its first line, as a comment. Mark each line worth explaining
   with a circled number, `# ①`, in a comment at its end.
5. **What each part does.** A numbered list, one item per circled number, in the same order:
   what that decorator, mixin, argument or return is, and why it is there.
6. **Run it.** The command, and what it really printed, copied from a real run. Cut long agent
   prose with `…` and put scratch paths under `/home/you/`, and change nothing else. Then say
   how to read the output.
7. **Check it worked.** How the reader proves it: a file to look at, a command whose output
   says so, and, in the Weaver Guide, a test on the fake kit with its own callouts and its real
   pytest output.
8. **Variations and pitfalls.** The other ways to do it, and what goes wrong, each with the
   error it prints where there is one.
9. **Next steps.** Where to go from here, ending with the Reference page that has every
   argument.

A tutorial is the same, with the example cut into numbered steps (`## Step 1: …`) the reader
takes in order.

**Every example runs.** Before you push, write each file on the page into a scratch project,
run it the way the page says, and run its tests. A flow's example runs on a real agent, on a
small budget, and on the fake kit.

## The writing rules

**1. Match the code.** Check every command, flag, key, slash command, path, name and error
string you write against `src/hmz`. Where the code and `specs/` disagree, the docs follow the
code, and the pull request says so.

**2. Stay at the reader's altitude.** Outside Reference:

- Show no internal module paths. The only imports shown are the stable ones: `hmz.flows` for
  writing flows, and `hmz.sdk` for driving humanize.
- Describe no processes, protocols, file formats or storage layouts. Include a mechanism only
  when the reader needs it to decide something or to avoid a pitfall, as one sentence of
  consequence and a link to Reference.
- Write no history: not "used to", "now" or "no longer". Say what is.
- Contributing pages may name the layers and modules a contributor must touch, but do not
  narrate how they work.

**3. Follow the reader's order.** Before you write, decide who arrives, from where, and what
they want right now.

- Lead with doing. The first screen gives a result or the answer the reader came for.
- Introduce a term where it is first used, in a phrase, linking the
  [Glossary](/user/concepts) if needed. Never make the next step wait on a definition.
- Do not pre-empt objections, justify design decisions, or stack caveats. Keep genuine safety
  warnings, short.
- Put edge cases, per-backend exceptions, Python, testing and CI at the end of the page, in a
  `::: details`, or on a later page.

**4. Show, don't only tell.** Every page carries at least one thing beyond prose that carries
meaning. Most need no component:

| Want | Write |
| --- | --- |
| point at a line | `// [!code highlight]`, `// [!code focus]`, or `{1,3-4}` after the language |
| show a change | `// [!code ++]` and `// [!code --]` |
| the same thing several ways | `::: code-group`: one tab per backend, or the prompt against `hmz exec` |
| support per backend | `<Badge type="tip" text="claude" />` |
| a key | `<kbd>esc</kbd>` |
| a choice | a comparison table |
| what the terminal shows | a `text` block, or a demo from `/demo/` |
| an aside | `::: tip`, `::: warning`, `::: danger`, `::: details`, sparingly |

The same rule, before and after:

```diff
- The anchor runs a seccomp-filtered ptrace supervisor on the target.
+ Your agent's edits land on the remote machine. [How](/reference/remote-execution)
```

Wrap prose at 95 columns. The first `#` heading is the page title. Do not write a table of
contents: the outline on the right is built from `##` and `###`. A page whose `###`s are
dozens of error messages sets `outline: 2` in its frontmatter.

## Components

Add a Vue component only where a control settles a real question, not as decoration.

- **Put it beside its page.** A new component goes in
  `docs/.vitepress/theme/components/<slug>/Name.vue`, where `<slug>` names the area it
  belongs to. Import it in the page that uses it rather than registering it in
  `theme/index.ts`, with the path adjusted to the page's depth:

  ```md
  <script setup>
  import Name from '../.vitepress/theme/components/<slug>/Name.vue'
  </script>
  ```

- **SSR-safe.** The build renders every page on the server. Touch `window`, `document` and
  `matchMedia` only in `onMounted`.
- **Motion is optional.** Honour `prefers-reduced-motion` and hold still at something worth
  looking at. Stop animating while scrolled offscreen. Nothing is said only by a moving thing.
- **Light and dark.** Take colours from the `--vp-c-*` and `--hmz-*` variables. `.hmz-panel`
  is the shell every diagram sits in.
- **390px wide.** It works on a phone, with no horizontal scroll, and no word on it is drawn
  smaller than 11px: a font size times every scale between it and the screen, the viewBox and
  the camera too. On a phone a scene runs the full width of the screen, past the page's gutters,
  and is drawn for 360px; on a narrower one `HmzStage` lifts its small words back to the size
  they have at 360, so leave a word some room in its box. `pnpm check:legible` measures it, down
  to 320px.
- **Honest.** A simulated run says it is simulated, and the demos under `/demo/` are the real
  terminal. A drawing says what it is drawn from and matches it: the layer diagram on
  [Architecture](/contributing/architecture) copies the table in
  `tests/integration/layering/test_layering.py`.
- **A feature scene plays on the motion toolkit.** Every scene on a Features page is one GSAP
  timeline built with `useScene` from `docs/.vitepress/theme/motion/`, and drawn inside
  `HmzStage`. The toolkit starts a scene when it is scrolled into view, pauses it off screen,
  holds it at its `still` frame under reduced motion, and turns the timeline's `beat-0`,
  `beat-1`… labels into the chapters under the picture: one short line each, so the words are
  always on the page. Move the world with the camera from `camera.ts`, put sparks and light
  trails on the canvas from `fx.ts`, keep a second layout for phone width with `useNarrow`,
  and take GSAP from `motion()` rather than importing it bare. The toolkit also lists the scene
  for `check:legible` (`probe.ts`), which fails a scene it cannot hold still. A screen that
  holds links or controls sets `interactive`, so it is a group rather than a picture to a
  screen reader. Never tween the `x`, `y` or `scale` of an SVG element placed by a `transform`
  attribute: GSAP replaces the attribute. Place it with an outer `<g>`, and move an inner one.
- **A feature page is short.** A title, one `hmz-tagline` line, the scene, three to five
  `hmz-facts` the motion cannot say, the per-backend badges, and three `hmz-paths` cards on to
  the guides. Whatever the scene shows is not written out again.
- **Links through `withBase`.** The site is served under `/humanize/`. A path written by hand
  in a component, as an `href` or a `src`, goes through `withBase`. Markdown links, the nav
  and the sidebar get the base added for them.

### Flow diagrams

Every flow's diagram, the cards on `/flows/` and the legend there are one grammar, drawn by the
components in `docs/.vitepress/theme/components/flow/`. `<HmzFlow flow="rlar" />` plays a
flow's scene on a page, `pick="a,b"` several with a strip to choose between them. To draw a
flow, add or change its scene in `theme/flows.ts` (roles, turns, passes, the loop and the ends,
read off the flow's own code) and nothing else:

- **One mark per idea.** A role's colour says what it is (`maker`, `partner`, `checker`,
  `steward`), you are a ring with a person, a program with no model is a square. A spark is a
  new session, a thread a held one; a solid pass is words, a dotted one files. The full list is
  in `grammar.ts`, and the legend on `/flows/` draws it. A new idea gets a new mark there, in
  the legend too, before any scene uses it.
- **No drawing in a scene.** A scene says what happens, never where or how it looks. Layout,
  camera and motion are worked out from it by `stage.ts`, the same way for every flow.
- **Every flow has its own page and scene**, and its card, its sidebar entry and its category
  come from the same entry in `FLOWS`. A flow belongs to one kind in `KINDS`.
- **Every word can be read.** No word in the grammar is set smaller than 11.5px, the camera
  closes in no further out than a zoom of 1, and a word it would draw under 11px fades out, so
  a wide shot on a phone is the marks alone. Where the whole run at rest does not fit the
  screen at that size, it is drawn full size in a frame that scrolls, under a map of the run.
- **The run is a function of time.** Whatever moves is computed from the playhead, so the
  scrubber, the step buttons and reduced motion show the same frames the animation does.

## Look at it

The build catches dead links, not a broken page. Screenshot every page you changed in light,
dark and at 390px wide, then open each image:

```sh
pnpm build && pnpm preview    # http://localhost:4173/humanize/
```

```sh
docker run --rm --network host -v /tmp/shots:/shots mcr.microsoft.com/playwright:v1.60.0-noble \
  npx -y playwright@1.60.0 screenshot --full-page --color-scheme=dark --wait-for-timeout=2000 \
  http://localhost:4173/humanize/contributing/docs /shots/docs-dark.png
```

Repeat with `--color-scheme=light`, and with `--viewport-size=390,844`. Look for:

- a component that does not render;
- raw markdown or `:::` showing on the page;
- anything wider than the screen at 390px;
- text you cannot read in dark mode;
- a code group or table that came apart;
- a large empty area.

For a component with a control, write a few lines of Playwright that click it and screenshot
again, to prove the state changes.

## Terminal demos

The GIFs under `docs/public/demo/` are rendered by [VHS](https://github.com/charmbracelet/vhs)
from the `.tape` scripts in `docs/tapes/`, inside a container built for the purpose. You need
`docker` and nothing else.

```sh
docs/tapes/render.sh              # every tape
docs/tapes/render.sh tui.tape     # one of them
```

::: danger A demo must not record anything private
Every tape runs in the container, in a scratch home and a throwaway project, against stand-in
coding agent CLIs. No tape takes a real turn, and nothing signs in to anything: every secret
on screen is an obvious fake, such as `not-a-real-key`.
:::

Keep each GIF under 450 KB: `render.sh` fails on anything larger. Look at every frame before
you commit. [`docs/tapes/README.md`](https://github.com/humanfia/humanize/blob/main/docs/tapes/README.md)
has the rest.

## Other documentation

- **`README.md`** follows [standard-readme](https://github.com/RichardLitt/standard-readme),
  says what humanize does and how to use it, and links here.
- **`specs/`** holds each package's contract. Do not edit one unless you were asked to.
- **Docstrings** are Google style, and `ruff` checks them.

The site deploys to [docs.humanfia.ai/humanize](https://docs.humanfia.ai/humanize/) from
`main`, through `.github/workflows/build-docs.yml`.

## Next steps

- [Add a page to these docs](/contributing/tutorials/a-page-of-docs), the tutorial
- [Your first flow](/weaver/writing-a-flow), a guide page in the shape above
- [Contributing](/contributing/), for the checks the rest of the repository is held to
