# Architecture

Where a change goes: the parts of the repository, the layers of `src/hmz` and what each may
import, and the files to visit for the two changes that cross many layers, a backend and a
command. [CONTRIBUTING.md](CONTRIBUTING.md) has the setup and the checks.

## The parts

| Path | Holds |
| --- | --- |
| `protocol/` | The contract: everything Humanize shows to the outside, in MUST, MUST NOT and MAY terms, and nothing about how it is built. Code follows it; a protocol document changes only when a maintainer asked for it |
| `src/hmz/` | The Python package `hmz`: the command line, the terminal interface, the web page and its server, the daemon, the flow API, the SDK. Nothing in it runs on a target |
| `crates/coganchor/` | `coganchor`, one static Rust program: `coganchor cog` runs beside the agent on its harness machine, `coganchor anchor` on the machine its work lands on, `coganchor broker` where two halves that cannot dial each other meet; it also holds the fence and the credential helper. `hmz.coganchor` finds the build for a machine and drives it. A release puts a build per platform in the wheel at `src/hmz/coganchor/bin/<os>-<arch>/coganchor` |
| `desktop/` | Humanize Desktop, for macOS and Windows, in Rust with [Tauri](https://tauri.app/): a window on the page of `src/hmz/web/static`, which the build carries into it beside the splash of `desktop/ui/app`, and the pipes that page reaches daemons through (`desktop/src-tauri/`) |
| `docs/` | The documentation site |
| `tests/` | `unit/`, `integration/` and `system/`: [where a test goes](CONTRIBUTING.md#where-a-test-goes) |

Humanize ships no flow. Every flow lives in a repository of its own, listed in
[humanfia/flowverse](https://github.com/humanfia/flowverse); the stand-ins the integration
tests run are in `tests/integration/flows/`.

### The protocol documents

| Document | States |
| --- | --- |
| `protocol/core.md` | the conventions and shared terms; epics, agents, accounts, placements, environments, chats, side questions, monitoring, backups, telemetry, updates |
| `protocol/cli.md` | every command line |
| `protocol/tui.md` | the terminal interface |
| `protocol/web.md` | the web page, and every path `hmz web` serves |
| `protocol/desktop.md` | Humanize Desktop |
| `protocol/daemon.md` | one daemon per machine, remote daemons, and the daemon as a frontend sees it |
| `protocol/wire.md`, `protocol/openrpc.json` | carriers, routes, device identities, pairing, the relay, frames, and the JSON-RPC session and its methods |
| `protocol/python.md` | the flow API, and `hmz.sdk` |
| `protocol/files.md` | every key of `settings.yaml`, every environment variable read, every file left on disk |

## The layers of `src/hmz`

Each top-level package is a layer, and some packages of `runtime` are layers of their own. A
module may import its own layer and only the layers this table gives it.
`tests/integration/test_core_layering.py` holds the same table as `ALLOWED` and fails the run
on an import outside it: to add a layer or an edge, edit `ALLOWED` and this table together.

| Layer | Holds | May import |
| --- | --- | --- |
| `rpc` | frames, and JSON-RPC over any pipe | nothing |
| `rtc` | the WebRTC carrier | nothing |
| `relay` | the relay that joins a client and a daemon that cannot reach each other | nothing |
| `trust` | device keys, pairing, TLS between two devices | `coganchor.atomic`, `coganchor.settings`, `rpc.pipe` |
| `coganchor` | how each coding agent CLI is driven, its accounts, models, nous and prices; machines; finding and driving the `coganchor` program | `runtime.telemetry` |
| `reach` | the carriers between a client and a daemon: routes, dialing, listening, racing | `coganchor`, `daemon.where`, `rpc.pipe` |
| `flows` | the flow API: the types, mixins, hooks and errors a flow imports | `runtime.flowing`, `coganchor.faking` |
| `runtime` | the rest of `runtime/` not named below | nothing |
| `runtime.kept` | | `coganchor.nous`, `coganchor.spelling` |
| `runtime.settings` | `settings.yaml` | `runtime.kept`, `coganchor.machines.store`, `coganchor.settings` |
| `runtime.telemetry` | | `runtime.settings` |
| `runtime.tracing` | a backend's logs read back as a trace | `coganchor` |
| `runtime.watching` | a run as it happens, for every interface: who is working, what it has cost | `coganchor` |
| `runtime.epic` | what a run writes down | `coganchor`, `runtime.tracing` |
| `runtime.exporting` | | `coganchor`, `runtime.epic`, `runtime.telemetry`, `runtime.tracing` |
| `runtime.backing` | an epic backed up to git repositories | `runtime.epic`, `runtime.exporting`, `runtime.settings` |
| `runtime.flowing` | how a flow runs: the engine, budgets, resuming, the harness and environment drivers | `coganchor`, `flows`, `runtime.epic`, `runtime.telemetry` |
| `runtime.runner` | the `hmz exec` line | `coganchor`, `flows`, `runtime.backing`, `.epic`, `.flowing`, `.kept`, `.settings`, `.telemetry` |
| `runtime.chatting` | a chat: one agent, one conversation | what `runtime.runner` may, and `runtime.runner` |
| `runtime.doing` | anything two of `cli`, `tui`, `web` and `daemon` would each need, written once | `coganchor`, `reach`, `rpc`, `trust`, `flows`, and `runtime.backing`, `.chatting`, `.epic`, `.exporting`, `.flowing`, `.kept`, `.runner`, `.settings`, `.telemetry`, `.tracing` |
| `daemon` | runs kept going after the terminal closes, and the one JSON-RPC endpoint every client reaches them through | `coganchor`, `reach`, `rpc`, `rtc`, `runtime`, `trust` |
| `daemon.where` | where this machine's daemon is | nothing |
| `daemon.api` | the methods a daemon serves beyond epics and sessions, a module per family naming its own in `METHODS` | `coganchor`, `daemon`, `reach.routes`, `rpc`, `runtime` |
| `sdk` | the Python API another program calls: a client of a daemon | `daemon`, `flows`, `reach`, `rpc`, `runtime` |
| `tui` | the terminal interface | `coganchor`, `flows`, `daemon`, `reach.routes`, `rpc`, and `runtime.flowing`, `.chatting`, `.epic`, `.exporting`, `.kept`, `.telemetry`, `.watching` |
| `web` | the page under `web/static/`, and its server: `site.py` serves its files, `bridge.py` bridges `/rpc` and `/dial` to daemons | `coganchor`, `daemon`, `reach`, `rpc`, `runtime.doing` |
| `cli` | every command | anything: it is the one package the table leaves out |

Naming a layer covers every module inside it, and a module's layer is the longest one it is
under. The test also holds that:

- **No two layers name each other**, but one pair: `flows` calls into `runtime.flowing` from
  inside `flow`, `load` and `Outworlder.new`, and never at import.
- **Importing `hmz.flows` loads nothing else of Humanize** but `hmz.coganchor.faking`.
- **A layer's front door loads no other layer**, and reading an `hmz exec` line loads neither
  the interface nor the daemon.
- **Every top-level package but `cli` is in the table.**

One rule no test checks: import another layer inside the function that needs it, not at the
top of the module, so that `hmz exec` pays only for what it uses. Ruff's `PLC0415` is off for
this.

Nothing sits at the top of `src/hmz/` but `__init__.py` and `__main__.py`. Name a module for
what it holds, in the words `hmz` and the docs use.

## Where a change goes

| You are changing | Put it in |
| --- | --- |
| how a coding agent CLI is driven, or its accounts, models, nous or prices | `coganchor/` |
| the machine an agent's turns land on | `coganchor/machines/` |
| what runs beside the agent or on its target: mirrors, the supervisor, the fence, the serving half, the broker | `crates/coganchor/` |
| a type, mixin, hook or error a flow imports | `flows/`, then check the flows flowverse lists still work |
| how a flow runs | `runtime/flowing/`, then check those flows too |
| the `hmz exec` line: a flag, a refusal | `runtime/runner.py` |
| a chat: what a typed line means, how its turns go | `runtime/chatting/`; what a CLI takes natively is its driver's `natives()` in `coganchor/agents/` |
| what a run writes down | `runtime/epic.py` |
| who is outside a run: claims, away, questions, lines said to agents, asides | `runtime/doing/hosting.py` |
| what a frontend does in a run's environments: files, terminals, git | `runtime/doing/desk.py`, `runtime/doing/gitdesk.py` |
| a slash command, a key, a menu of the terminal interface | `tui/` |
| a view of the web page, or what its server answers | `web/` |
| a method the daemon serves | `daemon/api/` |
| a carrier between a client and a daemon | `reach/` |
| a command | `cli/` |
| the desktop app's window, pipes, installer or updater | `desktop/src-tauri/` |

## Adding a backend

A backend is one coding agent CLI Humanize drives. A CLI that speaks the Agent Client Protocol
needs no code: it is added from the Accounts page of the settings. Otherwise, in this order:

1. **Describe it, in `coganchor/`.** A `Profile` in `backends.py`, added to `PROFILES`. A
   driver in `agents/<name>.py`, subclassing `CommandSessionBase` when a turn is one run of a
   command or `StreamSessionBase` when it is one long-lived process. A row of `DRIVEN` in
   `agents/__init__.py`. A function in `_READING` in `models.py` that asks which models it
   runs. An `AgentProfile` in `statepaths.py`.
2. **Offer it to flows.** A `HarnessKind`, a protocol carrying exactly the mixins the CLI
   serves, and a row of `HARNESS_AGENTS`, in `flows/agents.py`; export the protocol from
   `flows/__init__.py`.
3. **Read it back.** A trace reader in `runtime/tracing/readers/<name>.py` and its row in
   `runtime/tracing/collector.py`. A row of `_KINDS` and a branch of `_spent` in
   `runtime/watching/tally.py`.
4. **Name it on the page**: a row in `web/static/names.js`.
5. **Test it.** Unit tests of the driver in `tests/unit/coganchor/` with the CLI's process
   mocked. A fake of the CLI, its flags read off the real `--help`, and
   `tests/integration/test_agents_<name>.py` driving it. Its cheapest model in `CHEAPEST` in
   `tests/system/test_harness_task.py`.
6. **Say so** in the docs pages that list the backends. Where the protocol lists them too,
   propose the change.

```sh
uv run pytest tests/unit/coganchor tests/unit/flows tests/unit/runtime \
    tests/integration/test_agents_<name>.py tests/integration/test_core_layering.py
uv run pytest -n0 tests/system/test_harness_task.py -k <name>   # real tokens
```

## Adding a command

1. A module under `cli/` if it takes a parser of its own, and a thin wrapper in
   `cli/__init__.py`.
2. An entry in `COMMANDS` there, or in `INTERNAL` for a line Humanize runs for itself, which
   `hmz internal` routes.
3. Its output through `cli/output.py` where it has a `--json`.
4. A terse help: every flag's help, summary, description and epilog is thirty words or fewer.
   A unit test in `tests/unit/cli/` fails on anything longer.

## The web page

The page under `src/hmz/web/static/` is plain ES modules and hand-written stylesheets, served
as they are, speaking JSON-RPC to daemons (`rpc/`, `api.js`).

- **Look.** The head of `style.css` states the look once, as tokens on `:root` (spacing,
  radii, borders, sizes, type, states, `z-index`, motion). A rule takes its values from them,
  never from a literal. No rule sets a `box-shadow`. A state is a fill, the same everywhere.
  The colours a theme may set are the ones `themes.js` lists.
- **What floats.** A menu, popup or panel is registered with `layers.js`, which holds the
  page's only listeners that close them. A module calls `opened(layer)` and `closed(layer)`
  and adds no listener of its own for an outside press, Escape, scroll, resize or blur; it
  shows a `<dialog>` with `modal(dialog)`. `menu()` and `submenu()` of `shell.js`, `menuOn()`
  and `menuButton()` of `ui.js` and `confirming()` of `dom.js` already do all of it.
- **Names.** A harness, a model and an effort are named by `names.js` alone.
- **Languages.** English, Simplified Chinese (`zh-Hans`) and Traditional Chinese (`zh-Hant`).
  The English text is the key: `t('Cancel')`, `t('New chat in {name}', { name })`, always one
  single-quoted literal, wrapped where it is written. A translation goes in
  `i18n/zh-Hans/<area>.js` and `i18n/zh-Hant/<area>.js`. Names stay in Latin script: Humanize,
  Ai-chan, Nous, Epic, Flow, Flowverse, Harness, Daemon, Exomyth, Agent, Worktree, and every
  harness and model. `tests/unit/web/js/i18n.test.mjs` holds the catalogs to the source.
- **Third-party code.** `src/hmz/web/vendor/` pins it with pnpm and bundles it with esbuild
  into `web/static/vendor/`, which is committed; the page imports it from `/vendor/` only.
  After changing a version, run `pnpm install && pnpm build` there and commit what it wrote.
  CI's `vendor` job fails when the committed files differ.
- **Tests.** `node --test 'tests/unit/web/js/*.test.mjs'` for the modules; `tests/system/web/`
  for the page in real browsers.
