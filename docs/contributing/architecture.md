---
pageClass: hmz-feature
---

# Architecture

This page is where you find out where a change goes before you write it: which layer of
`src/hmz/` it belongs in, what that layer may import, and, for the two changes that touch many
layers at once, a backend and a command, every file to visit in order.

::: info Before you start
- A checkout set up as in [Contributing](/contributing/).
- For a first, small change, [Your first patch](/contributing/tutorials/first-patch) is the
  gentler way in.
:::

## How the layers work

`src/hmz/` is a stack of layers, and code in each layer may import only the layers the table
below gives it. Pick a layer to see what it may import and open its protocol document. A test
holds the same table, so an import that breaks it fails the run.

<HmzStack />

## Where a change goes

| You are changing | Put it in |
| --- | --- |
| how a coding agent CLI is driven, or its accounts, models, nous or prices | `coganchor/` |
| the machine an agent's turns land on | `coganchor/machines/`, per [Machines](/reference/machines#writing-a-machine-of-your-own) |
| what runs beside the agent or on its target: mirrors, the supervisor, the fence, the serving half, the broker | `crates/coganchor/`, the `coganchor` program, in Rust; see [`coganchor`](/contributing/#coganchor) |
| a type, mixin, hook or error a flow imports | `flows/`, then check the flows [humanfia/flowverse](https://github.com/humanfia/flowverse) lists still work |
| how a flow runs: the engine, budgets, resuming, the harness and environment drivers | `runtime/flowing/`, then check those flows too |
| the `hmz exec` line: a flag, a refusal | `runtime/runner.py` |
| a chat: what a line typed in one means, how its turns go, its preference | `runtime/chatting/`; what a CLI takes natively is its driver's `natives()` in `coganchor/agents/`, as a list of `NativeCommand` |
| what a run writes down | `runtime/epic.py` |
| reading a backend's logs back as a trace | `runtime/tracing/` |
| what a run looks like as it happens -- who is working, what it has cost, what a side question is told -- for every interface | `runtime/watching/`, once |
| anything two of `cli`, `tui`, `web` and `daemon` would each need | `runtime/doing/`, once |
| who is outside a run: claims, away, questions, lines said to agents, asides | `runtime/doing/hosting.py` |
| what a frontend does in a run's environments (`env.*`): the `envs` list, files, terminals and their flow control | `runtime/doing/desk.py`; git's commands and what they print, `runtime/doing/gitdesk.py` |
| a slash command, a key, a menu; what the interface draws of a message | `tui/` |
| a view of the web interface, or what its server answers | `web/`: the page under `web/static/`, plain ES modules speaking JSON-RPC to daemons (`rpc/`, `api.js`), drawn from the tokens of `style.css`, its menus and popups kept by `layers.js` ([The page's look and what floats](#web-look)); the server in `site.py` -- the page's files, `/here`, admission -- and its bridges `/rpc` and `/dial` in `bridge.py` |
| runs kept going after the terminal closes, and the one JSON-RPC endpoint every client reaches them through, on its socket and its listeners | `daemon/` |
| a method the daemon serves beyond epics and sessions: settings, accounts, nous, runtimes, EasyTier, flows, workspaces, paths, notices, runs, backups, files | `daemon/api/`, a module per family naming its own in `METHODS` |
| a carrier between a client and a daemon: a route, dialing it, listening, racing routes | `reach/` |
| the frames a session carries, and JSON-RPC over them: calls, notifications, errors, `session.hello` | `rpc/` |
| a new command | `cli/` |
| the Python API another tool calls | `sdk/` |
| a flow | not in this repository: Humanize ships none. Every flow, the six loops FlowBench scores included, lives in a repository of its own, listed in [humanfia/flowverse](https://github.com/humanfia/flowverse): see [Flowverses](/weaver/flowverses). The stand-ins the integration tests run are in `tests/integration/flows/` |

Nothing sits at the top of `src/hmz/` but `__init__.py` and `__main__.py`. Name a module for
what it holds, in the words `hmz` and these docs use.

## The rules the test checks

`tests/integration/test_core_layering.py` holds the table the diagram draws. The run fails
when:

- **A module imports what its layer may not.** Relative imports count the same as absolute
  ones. `from hmz.runtime import telemetry` names `telemetry`, not the whole of `runtime`.
- **Two layers name each other.** One pair may: `flows` calls into `runtime/flowing` from inside
  `flow`, `load` and `Outworlder.new`, and never at import. Importing `hmz.flows` must load
  nothing else of Humanize but `hmz.coganchor.faking`, which holds `FakeTool`, `FakeCli` and
  `FakeCommand`, and that is checked too.
- **A top-level package is missing from the table.** `cli` is the one exemption.

Nothing of `src/hmz/` runs on a target. The halves of a session that run beside the agent and on
the machine its work lands on are the Rust program `coganchor`, in `crates/coganchor/`, which
the test does not read; `hmz.coganchor` finds the build for a machine and drives it.

To add a layer or an edge, edit `ALLOWED` in that test. The diagram above copies it, so change
`docs/.vitepress/theme/components/HmzStack.vue` in the same commit.

One rule no test checks: **import another layer inside the function that needs it**, not at
the top of the module, so `hmz exec` pays only for what it uses. Ruff's `PLC0415` is off for
this.

## Adding a backend

A backend is one coding agent CLI Humanize drives. Adding one touches most layers, so do it in
the order below, with a test run after each group. The walk-through follows how MiniMax Code,
`mcode`, was added, in one commit: `git show --stat c3c1e6a` lists every file it touched.

::: tip An ACP CLI needs no code
A CLI that speaks the Agent Client Protocol can be added from the interface, on the Accounts
page of `/settings`.
:::

**You need:** the CLI installed and signed in, so a system test can drive it; its `--help`
and a turn or two of its own logs, since several steps copy what it really writes; and which
kind of driver it needs, which `protocol/core.md` says.

### 1. Describe it, in `coganchor/`

1. **A `Profile` in `coganchor/backends.py`**: its name and `aliases`, its home (`home_var`,
   `home_dir`), the `logs` one session writes as globs taking `{ident}`, its `efforts`, the
   `sessions` paths a turn keeps, `skills`, `creds`, the `ways` in, the `hosts` it must reach,
   and the line that `installs` it. Add it to `PROFILES`.

   ```python
   Profile(
       name="mcode",
       aliases=("mcode", "minimax", "minimax-code"),
       home_var="MINIMAX_DATA_DIR",
       home_dir=".minimax",
       logs=("v2/sessions/*/*/*/*-session_{ident}/messages.jsonl",),
       encodes=True,  # [!code highlight]
       ...
   )
   ```

   Set `encodes=True` when the CLI names a session's files by its id in URL-safe base64
   rather than by the id itself, as MiniMax Code does. Whatever looks for a session's logs
   asks `profile.logged(ident)`, which answers the globs with the id spelled the way the CLI
   spells it, and never formats `logs` itself.
2. **A driver in `coganchor/agents/<name>.py`.** Subclass `CommandSessionBase` when a turn is
   one run of a command (`mcode exec` is), or `StreamSessionBase` when it is one long-lived
   process spoken to a line at a time. Declare on the agent class, as `counts`, the kinds of
   token it reports, named as `KINDS` in `coganchor/agents/event.py` names them.
3. **A row of `DRIVEN` in `coganchor/agents/__init__.py`**, and the driver's classes in its
   `__all__`:

   ```python
   "mcode": (MiniMaxCodeAgent, MiniMaxCodeAgentConfig),
   ```

4. **A way of asking which models it runs**: a function in `_READING` in `coganchor/models.py`.
   `mcode`'s reads `mcode provider list --json`.
5. **Its state paths**: an `AgentProfile` in `coganchor/statepaths.py`.

   ```python
   AgentProfile(
       name="mcode",
       state_paths=("~/.minimax", "~/.mavis"),
   ),
   ```

   Where the way it is driven can carry the CLI's own `/` commands, skills, `!` or `@`, the
   session's `natives()` lists them as `NativeCommand`s (`coganchor/agents/native.py`), each
   saying whether it is passed, called, emulated or refused, and `stream(..., native=True)`
   serves a [chat](/user/chat#native-input-by-cli)'s line so. A CLI that lists none takes
   every line of a chat as text.

### 2. Offer it to flows, in `flows/`

6. **A `HarnessKind`, a protocol and a row of `HARNESS_AGENTS`** in `flows/agents.py`. The
   protocol carries exactly the mixins the CLI serves, and is exported from `flows/agents.py`
   and `flows/__init__.py`:

   ```python
   class HarnessKind(StrEnum):
       ...
       MCODE = "mcode"


   class MiniMaxCodeAgent(
       Agent, SubagentStartHookAgentMixin, SubagentStopHookAgentMixin, Protocol
   ):
       """MiniMax Code, with everything it can do."""
   ```

   Give it a row in the `tests/unit/flows/` tests of `HARNESS_AGENTS`. A change here also
   checks the flows [humanfia/flowverse](https://github.com/humanfia/flowverse) lists still
   work.

### 3. Read it back, in `runtime/tracing/` and `runtime/watching/`

7. **A trace reader** in `runtime/tracing/readers/<name>.py`, and its row in
   `runtime/tracing/collector.py`.
8. **The live tally**: what its log calls each kind of token, as a row of `_KINDS` in
   `runtime/watching/tally.py`, and a branch in `_spent` there, so the tally moves during a
   turn. Cover its kinds in the `tests/unit/runtime/watching/` tests of the tally.

### 4. Test it

9. **Unit tests** of the driver in `tests/unit/coganchor/`, through its public names, with
   the CLI's process mocked.
10. **A stand-in for the integration tests**: a fake of the CLI, its flags read off the real
    CLI's `--help`, and `tests/integration/test_agents_<name>.py` driving it.
11. **A system test**: its cheapest model in `CHEAPEST` in `tests/system/test_harness_task.py`,
    which sets every installed CLI the same real task.

### 5. Say so

12. **The docs pages and components that list or count the backends.** Search for an existing
    backend's name and add yours beside it:

    ```sh
    grep -rln mimo docs --include='*.md' --include='*.vue' --exclude-dir=node_modules
    ```

    Where the protocol lists the backends too, propose the change: do not edit it unless you were
    asked to.

### Check it worked

```sh
uv run pytest tests/unit/coganchor tests/unit/flows tests/unit/runtime/watching \
    tests/integration/test_agents_<name>.py tests/integration/test_core_layering.py
```

`tests/integration/test_core_layering.py` is the one that fails when a step imported across a
layer it may not. Then the real thing, which takes minutes and spends tokens:

```sh
uv run pytest -n0 tests/system/test_harness_task.py -k <name>
```

## Adding a command

1. **A module under `cli/`** if it takes a parser of its own, and a thin wrapper in
   `cli/__init__.py`.
2. **An entry in `COMMANDS`.** A line Humanize runs for itself, rather than one a person types,
   goes in `INTERNAL` instead, which `hmz internal` routes.
3. **Its output through `cli/output.py`** where the command has a `--json`, so a stray `print`
   never lands in the stream a program reads.
4. **A terse help.** Every flag's help, command summary, description and epilog is thirty words
   or fewer; the detail goes in [CLI reference](/reference/cli). A unit test in
   `tests/unit/cli/` reaches every parser through `main` and fails on anything longer. A
   subcommand a command routes by hand needs a line in its `ROUTES`.

Check it with `uv run hmz --help`, which lists every entry of `COMMANDS`, and with
`uv run hmz <command> --help`.

## The page's look and what floats {#web-look}

The page's stylesheets -- `web/static/style.css` and the ones beside it and under `chips/`,
`faces/` and `views/` -- are written by hand and served as they are. Its look is stated once,
at the head of `style.css`, as tokens on `:root`; a rule takes its values from them, never from
a literal:

| What | Tokens |
| --- | --- |
| Padding, margin and gap | `--space-2` to `--space-40`; `--gutter` for a plane's inset, `--indent` for a step of a tree |
| Corners | `--radius-xs`, `-sm`, `-md` (what is pressed), `-lg` (what contains), `-xl` (the composer and a menu), `-full` |
| Lines | `var(--border)` between planes, around cards and as dividers; `var(--border-strong)` around what floats or is typed into; `var(--border-w) solid var(--edge)` around a button. None is thicker than `--border-w`, one pixel |
| Sizes | `--control-h-xs`, `-sm`, `--control-h`, `-lg` for controls, `--row-h` for a list's row, `--bar-h` for a bar; `--icon-sm`, `--icon`, `--icon-lg` |
| Type | `--text-xs` to `--text-xl`, in `--sans` or `--mono` |
| States | `--hover` under the pointer, `--selected` for what is current, chosen or open, `--pressed` while pressed, `--quiet` for a resting fill, `--focus-ring` as the outline of what holds the keys |
| Stacking | `--z-sticky`, `--z-float`, `--z-sheet`, `--z-scrim`, `--z-drawer`, `--z-dialog`, `--z-menu`, `--z-toast`, `--z-tip`, `--z-skip`: the only values a `z-index` takes |
| Motion | `--dur`, `--dur-slow` and `--ease` |

No rule sets a `box-shadow`: what floats is the opaque `--raised` surface inside
`var(--border-strong)`, and a dialog is set off by `--scrim`. A state is a fill, the same one
everywhere; nothing moves, grows or gains a border as its state changes. An accent says one
thing -- green sends, cyan is live or a link or the focus, pink is unread, gold waits on you,
red failed or destroys -- and the colours a [theme](/user/web#themes) may set are the ones
`themes.js` lists; every other colour is worked out from those, so that a theme made before
still draws.

Whatever floats over the page for a moment -- a menu, the list beside one, a menu at the
pointer, a panel that is typed into -- is registered with `web/static/layers.js`, which keeps
them as one chain and holds the page's only listeners that close them: a press elsewhere,
Escape, the focus leaving, a scroll, the window sized or left, the page going elsewhere. A
module that opens one:

- calls `opened(layer)` once its node is in the page and shown, and `closed(layer)` first in
  its own closer; `layer` names its `node`, the `anchor` that opened it, its `close`, and
  `kind: 'panel'` where something is typed in it;
- toggles from its trigger, on which it sets `aria-haspopup` and `aria-expanded`, and adds no
  listener of its own for an outside press, Escape, scroll, resize or blur;
- shows a `<dialog>` with `modal(dialog)` rather than `showModal()`, and calls
  `dismiss('dialog')` before any other dialog of its own is shown;
- puts it with `place()` or `follow()` -- which open a chip's menu from the chip itself, and
  what opens from inside `.composer-box` clear of the whole box -- and says anything for a moment through `posted()` or
  `toast()` of `ui.js`, which keep the one `.toasts` region.

`menu()` and `submenu()` of `shell.js`, `menuOn()` and `menuButton()` of `ui.js` and
`confirming()` of `dom.js` already do all of it. `layers.js` imports nothing and keeps its chain
without a document, so `tests/unit/web/js/layers.test.mjs` tests it under `node --test`.

A harness, a model and an effort are named on the page by `web/static/names.js` alone
(`harnessName`, `modelName`, `effortName`): each harness by its vendor's name, a model by its
family's row, each rung of an effort by the page's own word for it -- a `t('…')` of the table,
so it is said in the page's [language](#web-languages) -- and an id the table does not hold as
it is written. Draw a name
through it and keep the id where it is data -- a `data-` attribute, a tip, an agent as `-a`
spells it. A harness added to `DRIVEN` gets a row there; `tests/unit/web/js/names.test.mjs`
lists the ids.

## The page's languages {#web-languages}

The page is written in English, Simplified Chinese (`zh-Hans`) or Traditional Chinese
(`zh-Hant`). `web/static/lang.js`, a classic script ahead of the page's own, sets `<html lang>`
before anything is drawn, from the choice kept as `hmz-language` or from what the browser asks
for; `web/static/i18n.js` says each text in that language. Changing it keeps the choice and
opens the page again, so a table built as a module loads may call `t` at once.

The English text is the key, written where it is said:

```js
import { pieces, t } from './i18n.js'

h('button', {}, t('Cancel'))
t('New chat in {name}', { name: called })
t('{n} flows have a newer release', { n: count }) // forms in i18n/en/<area>.js: { one, other }
t('Open@@verb') // `@@note` tells two homographs apart; it is never shown
h('p', {}, pieces('From {name}', { name: h('b', {}, called) })) // a sentence holding an element
```

- The first argument is always one single-quoted literal: the test finds the page's texts by
  it. A text chosen by a value comes from a table of `t('…')` calls, never `t(value)`.
- Wrap the text where it is written, never inside `h()`: `h` also carries paths, tasks and what
  agents wrote, which are never looked up.
- A translation goes into the fragment of its area, `web/static/i18n/zh-Hans/<area>.js` and
  `web/static/i18n/zh-Hant/<area>.js` (`core`, `sidebar`, `chat`, `ask`, `settings`, `envs`,
  `themes`); a text two areas say belongs to `core`. Traditional Chinese is written in Taiwan's
  words, not converted from Simplified.
- Names stay in Latin script (Humanize, Ai-chan, Exomyth, EasyTier, and every harness and
  model), and what a daemon, a flow or an agent wrote is never translated. A name out of a closed
  set the daemon gives -- a runtime's backend, a permission's preset -- is said through a table of
  `t('…')` calls keyed by it, and one the table lacks as the daemon names it.
- Every other word of the product is said by the glossary below, the same in every text, and
  never in Latin script: the test fails a Chinese text that says `Daemon` or `Epic`.

| English | zh-Hans | zh-Hant | Note |
| --- | --- | --- | --- |
| Daemon | 守护进程 | 常駐程式 | |
| Nous | 心智 | 心智 | νοῦς, the mind: who takes a turn |
| Virtual / concrete nous | 虚拟心智 / 具体心智 | 虛擬心智 / 具體心智 | |
| Harness, and "CLI" where it means one | 运行框架 | 執行框架 | |
| Agent | 智能体 | 代理程式 | |
| Epic | 史诗 | 史詩 | counted with 部 |
| Flow | 流程 | 流程 | |
| Flowverse | 流程库 | 流程庫 | |
| Environment (env) | 环境 | 環境 | |
| Runtime | 运行时 | 執行環境 | |
| Backend (of a runtime) | 类型 | 類型 | |
| Workspace | 工作区 | 工作區 | |
| Worktree | 工作树 | 工作樹 | |
| Session | 会话 | 工作階段 | |
| Turn | 轮 / 轮次 | 回合 | |
| Chat | 聊天 | 聊天 | |
| Folder / directory | 文件夹 / 目录 | 資料夾 / 目錄 | |
| This machine, this computer, Local | 本机 | 本機 | |
| Wait (policy) | 等待策略 | 等待策略 | |
| Token (of a model) | Token | Token | a unit, as GPU is |

Kept as written: commands and what is typed (`/flow`, `hmz update`, `-a`), ids (a backend's
`ssh`, an account's sign-in method), Shell, SSH, Git, Docker, Slurm, STUN, TURN, WebRTC.

`tests/unit/web/js/i18n.test.mjs` holds the catalogs to the source: every text in both Chinese
catalogs, no entry left over, the same `{names}` in a translation as in its text, no text in two
fragments. Run it with `node --test tests/unit/web/js/i18n.test.mjs`.

## Vendored web code {#vendored-web-code}

The page under `web/static/` has no build step, save its third-party code: the editor
(CodeMirror 6) and the terminal (xterm.js) of the env panels, Markdown (marked and DOMPurify),
and charts (Vega-Lite and vega-embed). `src/hmz/web/vendor/` pins them with pnpm and bundles
them with esbuild into `web/static/vendor/codemirror.js`, `xterm.js`, `xterm_css.css`,
`markdown.js` and `vega.js`, which are committed; a module of the page that uses them imports
them from `/vendor/` and from nothing else. None of them compiles code at run time, as the
page's policy refuses `eval`: `build.mjs` rewrites the few places in Vega and d3-dsv that
would, and fails if an upgrade moves them. After changing a version or what is
bundled:

```sh
cd src/hmz/web/vendor
pnpm install && pnpm build
```

and commit what it wrote. CI's `vendor` job builds it again from the lockfile and fails when
the committed files differ. `src/hmz/web/vendor/README.md` lists what each file exports.

## The protocol {#protocol}

`protocol/` states everything Humanize shows to the outside, in MUST, MUST NOT and MAY terms, and
nothing about how it is built: every interface (the command line, the terminal interface, the web
page and the server that bridges it to daemons, the desktop app, the daemon's wire protocol, the flow API and the SDK),
what Humanize does to the system under it (`settings.yaml`, environment variables, every file it
may leave on disk), and what each feature does as a user sees it. Another team could build a
product that behaves the same from these documents alone. They are written as RFCs are;
`protocol/core.md` holds the conventions every document follows and the terms they share. Pick a
layer in the diagram to open the document that governs what it shows. Change the code to match
the protocol, and do not edit a protocol document unless you were asked to. Propose a protocol
change separately. How the layers are built and may name one another is this page's business,
not the protocol's.

::: details Every document
| | |
| --- | --- |
| `protocol/core.md` | Conventions and shared terms; epics, agents, accounts, placements, environments, chats and their native input, side questions, monitoring, backups, telemetry, updates |
| `protocol/cli.md` | Every command line |
| `protocol/tui.md` | Every behaviour the terminal interface must have |
| `protocol/daemon.md` | One daemon per machine, remote daemons, and the daemon's protocol as a frontend sees it |
| `protocol/web.md` | Every behaviour the web page must have, and every path `hmz web` serves: its files, `/here`, `/rpc` and `/dial` |
| `protocol/desktop.md` | Humanize Desktop, the app in `desktop/`: a window on the page it carries, the pipes that page reaches daemons through, and its files |
| `protocol/python.md` | The flow API, and `hmz.sdk`: how a program that is not Humanize drives it |
| `protocol/files.md` | Every key of `settings.yaml`, every environment variable read, and every file Humanize may leave on disk, here or on another machine |
:::

## Next steps

- [Where a test goes](/contributing/#where-a-test-goes), for which tests a change needs
- [Working on these docs](/contributing/docs), for the pages a change updates
- [Reference › Agents](/reference/agents), for what each backend does, as users read it
