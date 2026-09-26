# Working on these docs

The site is [VitePress](https://vitepress.dev/) under `docs/`.
[Add a page to these docs](/contributing/tutorials/a-page-of-docs) walks one page through from
start to pull request. This page is the rules a page is held to.

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
```

## Where a page goes

Each section answers one kind of question. A page that answers two is two pages.

| Section | The reader wants | A page there |
| --- | --- | --- |
| **Features** | to understand | One feature, built around a diagram the reader can push. **No commands and no code**: a guide is one click away |
| **Flows** | to pick a flow | One flow, opening with its `hmz exec` line and the shape of its loop |
| **User Guide** | to do something | One task for the person running flows, opening with a `## Try it` short enough to paste. No Python |
| **Weaver Guide** | to write a flow | The same, for whoever writes the flow. Python throughout |
| **Contributing** | to change humanize | Setup, checks, the layers, and this |
| **Reference** | to look something up | Exact, complete and scannable: every flag, key, argument and return |

The three guide sections open with a **Tutorials** group: taken in order, every command
written out, nothing for the reader to choose.

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
- **390px wide.** It works on a phone, with no horizontal scroll.
- **Honest.** A simulated run says it is simulated, and the demos under `/demo/` are the real
  terminal. A drawing says what it is drawn from and matches it: the layer diagram on
  [Architecture](/contributing/architecture) copies the table in
  `tests/integration/layering/test_layering.py`.
- **Links through `withBase`.** The site is served under `/humanize/`. A path written by hand
  in a component, as an `href` or a `src`, goes through `withBase`. Markdown links, the nav
  and the sidebar get the base added for them.

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
