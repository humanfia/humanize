---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# CLI reference

The command line of the `hmz` package: its commands, their arguments and grammars, what each
writes to stdout and stderr, the environment variables they read, and their exit statuses.
Notation is defined in [Conventions](/reference/#conventions).

## Synopsis

```text
hmz                                    open the terminal interface
hmz -h | --help                        list the commands
hmz --version                          print the version
hmz exec <exec-options> [--] <task>    run one flow to its end
hmz internal <command> [<args>...]     processes humanize spawns for itself
```

| Command | Function in `hmz.cli` | Summary as `hmz --help` prints it |
| --- | --- | --- |
| *(none)* | `opens` | Opens the [terminal interface](/reference/tui). |
| [`exec`](#hmz-exec) | `_exec` | `run an agent flow in this directory` |
| [`internal`](#hmz-internal) | `_internal` | `internal commands used by humanize; do not run directly` |

`python -m hmz` is the same program. The console script is `hmz = "hmz.cli:main"`.

Every `--help` is a summary: no flag's help, command summary, description or epilog runs past
thirty words. This page is the full account of each.

## Routing {#routing}

`hmz.cli.main(argv)` routes the line before any command's own parser sees it:

| `argv` | Result | Exit |
| --- | --- | --- |
| empty | [Opens the interface](#hmz). | `0`, or `1` (see below) |
| exactly `["--version"]` | Prints `hmz <version>` (from the installed distribution's metadata) to stdout. | `0` |
| first word is `exec` or `internal` | Hands every later word to that command **unchanged**, `--help` included. No other command's module is imported. | the command's |
| `-h` or `--help` first | Prints the top-level help. | `0` |
| anything else | argparse usage error on stderr (below). | `2` |

```console
$ hmz bogus
usage: hmz [-h] COMMAND ...
hmz: error: argument COMMAND: invalid choice: 'bogus' (choose from exec, internal)
```

`hmz --version <anything>` is not the version form and fails the same way.

## `hmz` {#hmz}

```text
hmz
```

Takes no arguments and no options. Opens the terminal interface in the calling process on
the current directory, as it was [last left](/reference/tui#what-it-remembers). Starts no run.

### Where the runs are held {#where-runs-are-held}

The interface is one frontend of a [host](/reference/daemon#hosting). Which host is decided
once, at start, in this order:

| # | Condition | The interface |
| --- | --- | --- |
| 1 | `HUMANIZE_DAEMON` stripped and lower-cased is `off`, `0` or `no` | holds the runs in this process. Nothing is said. |
| 2 | stdin or stdout is not a TTY | holds the runs in this process. Nothing is said. |
| 3 | this machine's daemon is found and its `protocol` is not `2`, or a host an older humanize left holds this directory | is not opened. See [Errors](#hmz-errors). |
| 4 | a host for this directory is found through the daemon | links to it as `kind="tui"`. |
| 5 | no host is found | starts one, and the daemon where none is, with [`hmz.daemon.host()`](/reference/daemon#discovery), and links to it. |

Steps 3–5 are tried up to **3** times, **0.5 s** apart, while linking raises `OSError`
(a host found on its way out). After the third failure the interface holds the runs in this
process and prints the last `OSError` (below).

Holding the runs in this process changes one thing a person sees: `/exit` with a flow running
offers **Cancel** instead of **Detach and exit**. See
[TUI › `/exit`](/reference/tui#leaving-and-letting-go).

### Terminal preparation

Before Textual is imported, `hmz` sets `TEXTUAL_DISABLE_KITTY_KEY=1` in its own environment
(unless already set) when `TMUX` is unset or empty and either `TERM_PROGRAM=iTerm.app` or
`LC_TERMINAL=iTerm2`. See [TUI › Keyboard protocol](/reference/tui#keyboard-protocol).

### Errors and exit {#hmz-errors}

| Condition | stderr | Exit |
| --- | --- | --- |
| The interface closed normally | — | `0` |
| This machine's runs are held by an older humanize (daemon `protocol` not `2`), or this directory's by a host one left | `hmz: the runs on this machine are held by an older humanize (pid <n>); stop it with that version`, or `the runs in <dir> …` | `1` |
| The host let go of the interface ([`gone`](/reference/daemon#gone)) | `hmz: <why>` (or `hmz: disconnected from the runs`), printed as the interface closes | `1` |
| No host could be linked in 3 tries | `hmz: runs cannot be detached from the terminal (<OSError>), so they will run in this process instead` | the interface's |

## `hmz exec` {#hmz-exec}

Runs one [flow](/reference/flows) in the current directory (the *workspace*) to its return,
with no interface. The run's [outworlder](#nobody-is-at-the-prompt) is always away.

```text
usage: hmz exec [-h] -f FLOW [-a ROLE=SPEC[,...]] [-e ROLE=SPEC[,...]]
                [-p KEY=VALUE[,...]] [--profile] [--resume] [--json]
                task
```

### Options {#exec-options}

| Option | Value | Occurrences | Default | Meaning |
| --- | --- | --- | --- | --- |
| <span id="exec-flow"></span>`-f`, `--flow` | [`<ref>`](#naming-a-flow) | ≥ 1 (**required**; the last wins) | — | The flow. |
| <span id="exec-agents"></span>`-a`, `--agents` | [`<agent>`](#writing-an-agent) list | 0‥n, merged | none | One agent per agent role. |
| <span id="exec-envs"></span>`-e`, `--envs` | [`<env>`](#writing-an-environment) list | 0‥n, merged | none | One environment per environment role. |
| <span id="exec-params"></span>`-p`, `--params` | [`<param>`](#writing-params) list | 0‥n, merged | the flow's defaults | Fields of the flow's `FlowParams`, and, as [`budget.<limit>`](#writing-a-budget), what the run may spend: **required** except for `chat`. |
| <span id="exec-profile"></span>`--profile` | flag | 0‥1 | off | [Profile](/reference/tracing#profiling-a-run) the programs the run's agents start, as well as tracing them. |
| <span id="exec-resume"></span>`--resume` | flag | 0‥1 | off | [Pick up](#picking-a-run-up) the newest run of this flow here. |
| <span id="exec-json"></span>`--json` | flag | 0‥1 | off | Write the run as [NDJSON](#ndjson) on stdout. |
| `-h`, `--help` | flag | | | Print the help and exit `0`. |
| <span id="exec-task"></span>`task` | positional string | exactly 1 (**required**) | — | What the flow is to do. Put `--` before a task that starts with `-`. |

Options may appear in any order and before or after `task`. No option has an environment
variable equivalent.

### Grammar {#grammar}

Every list-valued option is read by one grammar. Terminals are quoted; `?` is optional, `*`
zero or more.

```text
option-value  = item , { "," , spaces , item } ;          (* split: see Items *)
key           = ( letter | "_" ) , { letter | digit | "_" | "-" } ;
identifier    = ? a Python identifier (str.isidentifier) ? ;

agent         = identifier , "=" , cli , ( "@" , provider )? , "/" , model , ":" , effort ;
cli           = ? a CLI name or alias, or an ACP CLI's name; contains no "@", "/" or "," ? ;
provider      = ? an account name; non-empty after "@" ? ;
model         = ? any text, may contain "/" and ":" ; non-empty ? ;
effort        = ? any text without ":" ; "auto" means the CLI's default ? ;

env           = identifier , "=" , backend , ( "@" , ( runtime | "[" , host , "]" ) )? , workdir? ;
backend       = "local" | "ssh" | "docker" | "swarm" | "apple-container" ;
runtime       = ? the name of a runtime saved for that backend ? ;
host          = ? [user@]host[:port], or an ssh config alias; ssh only ? ;
workdir       = "/" , ? any text ? ;                       (* "/~" or "/~/…" is home-relative *)

param         = key , "=" , ? any text ? | limit ;
limit         = "budget." , ( "duration" | "cost" | "output_tokens" | "graceful" ) , "=" , ? value ? ;
```

#### Items {#items}

- Each occurrence of `-a`, `-e` or `-p` is split into items at every `,` that is followed,
  after optional whitespace, by a `key=` or `budget.key=` (regex
  `,\s*(?=(?:budget\.)?[A-Za-z_][\w-]*=)`). A comma not followed by one belongs to the value:
  `-p tags=a,b,c` is one item.
- A value therefore cannot contain `,<key>=`.
- Items of every occurrence of one option form one list, in the order written:
  `-a x=…,y=…` and `-a x=… -a y=…` are the same line.
- An item that is empty or only whitespace is refused: `<flag> '<value>': an item is empty`.
- Leading and trailing whitespace around an `-a` or `-e` item, and around a `-p` key, is
  ignored; a `-p` value is kept as written (a `budget.<limit>` value is read stripped).

### Naming a flow (`-f`) {#naming-a-flow}

```text
ref = [ flowverse , "/" ] , flow , [ ":" , name ]
    | path
    | "git+" , url , [ "@" , rev ] , [ "#" , subdir ] , [ ":" , name ] ;
```

| Form | Resolves to |
| --- | --- |
| `<flow>` | The first flow of that name, looking in `local`, `user`, `official` (built in, then installed), then the flows installed from added flowverses (the order of [`Flowverses.nearest`](/reference/sdk#flowverses)). |
| `<flowverse>/<flow>` | The flow installed from that flowverse. `local/…` is `./.hmz/flows/`, `user/…` is `~/.hmz/flows/`. |
| `…:<name>` | Another flow defined in the same module. |
| a path (`./x`, `/x`, `x.py`) | That directory or file. |
| `git+<url>[@<rev>][#<subdir>][:<name>]` | The flow in `<subdir>` of a repository (its root without `#`), cloned and pinned at that revision, installing nothing: `git+https://github.com/humanfia/humanize1-flow@v0.1.0#humanize1:rlcr`. |

A flow a flowverse's index lists is not run until it is installed (`hmz exec` installs
nothing): naming one is refused with `<name>: not installed -- install it from /flow
(flowverse <flowverse>)`. Resolution, module loading and the several-flows-per-module rule are
specified in [Flows › Where flows live](/reference/flows#where-flows-live) and
[Flows › Refs](/reference/flows#refs).

### Writing an agent (`-a`) {#writing-an-agent}

```text
<role>=<cli>[@<provider>]/<model>[:<effort>]
```

| Part | Rule |
| --- | --- |
| `<role>` | A Python identifier: a field of the flow's agents declaration. Required on the command line. |
| `<cli>` | Read from the front up to the first `/`, then split at the first `@`. A CLI name or alias below, or the name of an [ACP CLI](/reference/agents#a-cli-of-your-own). |
| `@<provider>` | An [account](/reference/providers) of that CLI. `@` followed by nothing is refused. Absent: the CLI runs as this machine's own login (*as local*). |
| `<model>` | Everything after the first `/`, less a trailing `:<effort>`. Passed to the CLI unchecked. May contain `/` and `:`. |
| `<effort>` | After the last `:`, where what follows it is spelled as an effort: words of letters joined by `-`, `_` or a space (`high`, `extra-high`, `as configured`), or nothing. Otherwise -- `custom_provider:gateway/m`, `qwen3:8b` -- the `:` is the model's, and so is everything after it. Left off, or `auto`, or empty: no rung, stored as `""`. A model whose own name ends in `:<word>` is written with its effort after it: `qwen3:latest:auto`. Any other word must be on the CLI's ladder ([Agents](/reference/agents)); an ACP CLI takes any word. |

| `<cli>` | Aliases | Ladder, hardest first | Installed by | Extra |
| --- | --- | --- | --- | --- |
| `agy` | `antigravity` | `high` `medium` `low` | — | |
| `claude` | `claude-code` | `ultracode` `max` `xhigh` `high` `medium` `low` | `npm i -g @anthropic-ai/claude-code` | |
| `codex` | | `ultra` `max` `xhigh` `high` `medium` `low` | `npm i -g @openai/codex` | |
| `cursor-agent` | `cursor-cli` | `max` `xhigh` `extra-high` `high` `medium` `low` `minimal` `none` | `curl https://cursor.com/install -fsS \| bash` | |
| `dsh` | `deepseek-harness` | `max` `high` `low` `off` | `pip install 'deepseek-harness-sdk>=0.1.1rc1,<0.1.2' 'python-dotenv>=1.2.3'` | `hmz[dsh]` |
| `grok` | `grok-build`, `grokbuild` | `xhigh` `high` `medium` `low` | `npm i -g @xai-official/grok` | |
| `kimi` | `kimi-code` | `max` `high` `medium` `low` | `npm i -g @moonshot-ai/kimi-code` | `hmz[kimi]` |
| `mcode` | `minimax`, `minimax-code` | `max` `xhigh` `high` `medium` `low` | `npm i -g @minimax-ai/code` | |
| `mimo` | `mimocode`, `mimo-code` | `xhigh` `high` `medium` `low` `minimal` | `npm i -g @mimo-ai/cli` | |
| `opencode` | | `xhigh` `high` `medium` `low` `minimal` | `npm i -g opencode-ai` | |
| `pi` | | `max` `xhigh` `high` `medium` `low` `minimal` `off` | `npm i -g @earendil-works/pi-coding-agent` | |
| `qwen` | `qwen-code` | `max` `xhigh` `high` `medium` `low` `none` | `npm i -g @qwen-code/qwen-code` | |

Rungs a CLI takes beyond its listed ladder (such as Kimi Code's `swarm…` rungs) are in
[Agents](/reference/agents). A role's permission, skills and required capabilities are declared
by the flow and are not part of `-a`.

### Writing an environment (`-e`) {#writing-an-environment}

```text
<role>=<backend>[@<provider>][/<workdir>]
```

Parsed by the regex
`(?P<role>[^=]*)=(?P<backend>[^@/\[\]]*)(?:@(?P<provider>\[[^\]/]*\]|[^/]*))?(?P<at>/.*)?`. An
`@` is written only before a provider.

| Part | Rule |
| --- | --- |
| `<role>` | A Python identifier. |
| `<backend>` | `local`, `ssh`, `docker`, `swarm` or `apple-container`. |
| `<provider>` | Absent: this machine — a directory here for `local`, docker's default daemon here for `docker`, the swarm this machine manages for `swarm`, this Mac's [Apple containers](/user/containers#apple-containers) with nothing saved for `apple-container`. `local` takes no provider at all; `ssh` always takes one. `@<name>`: the [runtime](/reference/machines#runtimes) saved under that name for that backend; a name nothing is saved under is refused. `@[<host>]`, for `ssh` only: a host nobody saved, `[user@]host[:port]` or an alias of the ssh config, handed to `ssh` as it is; it never stands for a saved runtime and has no fallback list. |
| `<workdir>` | From the first `/` after the provider. `/~` and `/~/…` are relative to the ssh login's home. Omitted: the saved runtime's own workdir, refused where no runtime is named or it was saved with none. For `docker`, a directory of the daemon's host, mounted into the container at the same path; for `swarm`, one every node its task may land on has, likewise; for `apple-container`, a directory of this Mac, mounted likewise. |

`local/home/me/repo`, `docker/srv/repo`, `swarm/srv/repo` and `apple-container/Users/me/repo`
are this machine; `ssh@gpu-box/~/repo`, `docker@gpubox/srv/repo`, `swarm@cluster/srv/repo` and
`apple-container@mac/Users/me/repo` are saved runtimes, and `ssh@gpu-box` alone is the workdir
`gpu-box` was saved with; `ssh@[me@far.host:2222]/srv/repo` is a host nobody saved. A spelling
`-e` refuses with a hint — `local@/x`, `docker@local/x`, `swarm@local/x`,
`apple-container@local/x`, an unsaved ssh host out of brackets — is read as the one the hint
gives where it was kept in [settings](/reference/settings) or an
[epic](/reference/tracing#epics) (`docker@local`, `swarm@local`, `apple-container@local` only
where no runtime is saved as `local`).

Roles the runtime fills — `LocalEnv` roles, which are the workspace — are never given. After
parsing, every environment is opened and probed before the flow is called; an unreachable one,
or one whose machine has fewer CPUs, GPUs or less memory than its role declares, is
[refused](#what-is-refused-before-anything-runs). A `docker` environment's container is started
then, and a `swarm` environment's service created and waited for until its task runs. Where
the provider is a saved runtime with a
[fallback list](/reference/machines#falling-back), such an environment moves down that list
first, saying so on stderr:

```text
hmz exec: docker:a cannot hold 'box': <why>; using docker:b
```

### Writing params (`-p`) {#writing-params}

```text
<key>=<value> | budget.<limit>=<value>
```

- `<key>` matches `[A-Za-z_][\w-]*`; each key at most once across every `-p`.
- `<value>` is everything after the first `=`, unstripped. It is validated by the flow's
  `FlowParams` model: read as the field's type (`3`, `false`), otherwise as JSON.
- Keys not given keep the field's default. Unknown keys and values the model rejects are
  refused with the model's validation error, prefixed `<canonical ref>:`.
- `budget` is the run's, never a flow's: `budget.<limit>` sets one limit of the run's
  [budget](#writing-a-budget), `budget` alone is refused, and a flow whose `FlowParams` has a
  field or alias `budget` is refused when it is defined.

#### The budget (`budget.*`) {#writing-a-budget}

```text
budget.duration=<duration> | budget.cost=<usd> | budget.output_tokens=<count> | budget.graceful=<bool>
```

Each limit at most once across every `-p`, among the flow's params or apart from them:
`-p rounds=3,budget.cost=5 -p budget.duration=1h`. At least one of `duration`, `cost`,
`output_tokens` must be set. The first limit reached stops the run. See
[Flows › What a run may spend](/reference/flows#what-a-run-may-spend).

| Limit | Accepted | Type |
| --- | --- | --- |
| `duration` | Seconds as a number (`90`, `1.5`); units `w` `d` `h` `m` `s` concatenated, each at most once, decimals allowed (`1h30m`, `1.5h`, `2d`); ISO 8601 (`PT1H30M`); `HH:MM:SS`. Finite, ≥ 0. | `timedelta` |
| `cost` | USD, optional leading `$`; `inf` for no limit. ≥ 0, not NaN. | `float` |
| `output_tokens` | Integer with optional `_`, or a decimal with `k` (×1 000) or `m` (×1 000 000) that comes to a whole number (`200k`, `1.5m`). | `int` |
| `graceful` | `1` `true` `yes` `on` / `0` `false` `no` `off`, case-insensitive. Default `true`: the turn under way when a limit is reached is let finish. | `bool` |

With no `budget.*`, `chat` runs under `Budget(cost=inf)`; any other flow is refused, the other
flows humanize ships included.

A run with a finite `cost` limit first brings the [price list](/reference/files#h-prices-json)
up to date when the copy kept is missing or older than 24 h (at most 20 s; never with
`HUMANIZE_PRICES=off`). A `cost` limit over agents whose model still has no known price cannot
be enforced. The run starts, and stderr first carries:

```text
hmz exec: nobody lists a price for <model>[, <model>…], so cost=<n> cannot stop what it spends
```

### Where the harness runs {#choosing-where-the-harness-runs}

The *harness* is an agent's CLI and its supervisor. Nothing on the line says where it runs:
no option of `hmz exec` takes it. Work on this machine has its harness here; work
on a saved [runtime](/reference/machines#runtimes) has it where that runtime's `affinity` says,
in order (`self` on the runtime's own machine, `local` here, `ssh:<name>` / `docker:<name>` on
another saved runtime); work on a machine nobody saved, or on a runtime with no affinity, has it
on the environment's machine where the agent's CLI is installed there and can be fenced to the
role's permission and no hook gating its tools is hung, and here otherwise.

Once the environments are probed, before the flow is called, every agent's harness is settled
on every machine whose runtime has an affinity; an affinity with no room for it refuses the run
(`hmz exec: error: <backend>[@<provider>]: nowhere its affinity (<entries>) names has room
for <cli>'s harness; the last: <refusal>`, exit `2`). A runtime an affinity sends a harness to is
opened as an environment is, probed before the flow is called and closed with the run. Where
each session's harness went is recorded on the session in the epic as `local`, `self` or
`<backend>:<name>` ([Tracing › Epics](/reference/tracing#epics)), and in the daemon's
[`opened`](/reference/daemon#history-records) record. Detail:
[Remote execution › Where the harness runs](/reference/remote-execution#where-the-harness-runs).

### Picking a run up (`--resume`) {#picking-a-run-up}

`--resume` picks up the newest epic of the same flow (matched by canonical ref) in this
workspace whose journal (`resume.jsonl`) holds at least one entry and whose run is not still
going (in another terminal, or held by `hmz`; see [`.held`](/reference/files)). The flow must be
[resumable](/reference/flows#a-flow-that-can-be-picked-up). `-a`, `-e` and `-p` are still
read from the line; the budget counts from zero. The new run is a new epic and records
the epic it `picked_up`. Without `--resume` every run starts from the top.

| Refused | Message |
| --- | --- |
| the flow is not resumable | `<flow> does not support resuming, so there is no run to resume` |
| no epic of it here has a journal entry | `<flow> has no run to resume here: none saved any progress` |

### Processing order {#processing-order}

| Stage | Checks | On failure |
| --- | --- | --- |
| 1. argparse | Options, `-f` and `task` present. | Usage on stderr, `hmz exec: error: <why>`, exit `2`. |
| 2. Spec parsing (`Hmz.read`) | Every `-a`, `-e`, `-p` against its grammar, and every `-e` provider against the runtimes saved; duplicate roles and keys. | Same as 1. |
| 3. Loading (`Hmz.run` → `Runner`) | Flow resolves and loads; roles, harness kinds, capabilities, effort ladders, params, budget presence, `--resume`. | `hmz exec: error: <why>` (no usage), exit `2`. |
| 4. Opening (`Run.run`, before the flow is called) | Environments reached and measured; each agent's harness settled where its runtime's affinity puts it, and the runtimes it goes to reached; skills fetched. | `hmz exec: error: <why>`, exit `2`. |
| 5. The flow | — | See [Exit statuses](#exit-statuses). |

Nothing of an agent has started before stage 5. What a flow module does when imported (stage
3) is the module's own.

### What is refused before anything runs {#what-is-refused-before-anything-runs}

Every message below is printed after `hmz exec: error: ` on stderr, with exit status `2`.
Stage 1–2 messages are preceded by the usage block.

| Refused | Message |
| --- | --- |
| no `-f`, no task | `the following arguments are required: -f/--flow` / `…: task` |
| unknown option | `unrecognized arguments: <args>` |
| an `-a` item without `role=` | `-a '<item>': expected <role>=<harness>[@<provider>]/<model>[:<effort>]` |
| an `-a` role that is not an identifier | ``-a '<item>': '<role>' is not a place a flow could declare: what is written before `=` is a field of the tuple of agents the flow declares, so it is a Python identifier`` |
| an `-a` with an unknown CLI, no `/` or no model | `-a '<item>': expected [NAME=]CLI[@PROVIDER]/MODEL[:EFFORT]` |
| `@` with no account | `-a '<item>': expected an account after @, as in claude@deepseek/MODEL:EFFORT` |
| a role twice in `-a` | `-a: the role '<role>' is given twice` |
| an `-e` that does not match | `-e '<item>': expected <role>=<backend>[@<provider>][/<workdir>]` |
| no `/<workdir>`, and no runtime saved with one | `-e '<item>': expected <role>=<backend>[@<provider>][/<workdir>]; /<workdir> may be left off only for a runtime saved with one` |
| an `-e` role not an identifier | `-e '<item>': the role '<role>' is not an identifier` |
| unknown backend | `-e '<item>': '<backend>' is not a backend; one of local, ssh, docker, swarm, apple-container` |
| `ssh` with no host | `-e '<item>': ssh needs a host: ssh@<saved host>/<workdir>, or ssh@[user@host:port]/<workdir> for a host not saved` |
| `ssh` naming a host nobody saved, out of brackets | `-e '<item>': no ssh host is saved as '<name>'; write <role>=ssh@[<name>]/<workdir> for a host not saved` |
| a bracketed host that is not one | `-e '<item>': '<host>' is not an ssh host, as [user@]host[:port]` |
| brackets on `docker`, `swarm` or `apple-container` | `-e '<item>': only ssh takes a host nobody saved; <backend>@<name> names a <backend> runtime saved on the runtimes page of /settings` |
| `docker@local`, `swarm@local`, `apple-container@local`, nothing saved as `local` | `-e '<item>': <backend> on this machine names no provider; write <role>=<backend>/<workdir>` |
| `docker`, `swarm` or `apple-container` naming a runtime nobody saved | `-e '<item>': no <backend> runtime is saved as '<name>'; save one on the runtimes page of /settings, or write <role>=<backend>/<workdir> for <backend> on this machine` |
| `docker@`, `swarm@` or `apple-container@` with nothing after it | `-e '<item>': an @ is written only before a provider; write <role>=<backend>/<workdir>` |
| `local` with an `@` | `-e '<item>': local takes no provider; write <role>=local/<workdir>` |
| a role twice in `-e` | `-e: the role '<role>' is given twice` |
| a `-p` without `key=` | `-p '<item>': expected <key>=<value>` |
| a `-p` key twice | `-p: '<key>' is given twice` |
| `budget` with no limit | `-p '<item>': a budget is given a limit at a time, as budget.cost=5` |
| an unknown `budget.` limit | `-p budget.<limit>: not a limit; one of budget.duration, budget.cost, budget.output_tokens, budget.graceful` |
| a `budget.` value | `-p budget.duration: '<v>' names a unit twice`, `-p budget.duration: '<v>' is not a valid duration: must be finite and not negative`, `-p budget.duration: '<v>' is not a duration: use seconds, 1h30m, or ISO 8601 like PT1H30M`, `-p budget.cost: '<v>' is not a valid USD cost`, `-p budget.output_tokens: '<v>' must be a whole number of tokens`, `-p budget.output_tokens: '<v>' is not a valid token count: expected a number like 200000 or 200k`, `-p budget.graceful: '<v>' must be true or false` |
| a budget that limits nothing | `-p budget.*: Value error, a budget sets at least one of duration, cost, output_tokens` |
| no such flow | `<ref>: no flow is called '<ref>', and it is not a path`; `<ref>: not installed -- install it from /flow (flowverse <flowverse>)`; `<ref>: the official flowverse has not been fetched yet -- fetch it from /flow` |
| a role the flow does not declare | `<flow> has no agent role '<role>'; available roles are '<a>', '<b>'` (`… environment role …` for `-e`; `none` where there are none) |
| a role the runtime fills | `<flow>: '<role>' is assigned automatically by the runtime and cannot be set with -a`; `<flow>: '<role>' is the workspace the run started in and cannot be set with -e` |
| a required role unfilled | `<flow> needs an agent for '<role>'; specify each with -a ROLE=CLI/MODEL:EFFORT`; `<flow> needs an environment for '<role>'; specify each with -e ROLE=BACKEND[@PROVIDER]/WORKDIR` |
| a role typed as one CLI given another | `<flow>: '<role>' requires <cli>, but got <cli>` |
| an `@<provider>` naming no account of that CLI | `<flow>: '<role>' names no <cli> account called '<provider>'; make it on the accounts page of /settings` |
| a CLI lacking a capability the role needs | `<flow>: '<role>' needs <Mixin>[, <Mixin>…], which <cli> does not support` |
| an effort off the ladder | `<role>=<spec>: <cli> cannot be asked to think at '<effort>'; expected one of <ladder>` |
| params the flow rejects | `<canonical ref>: <pydantic validation error>` |
| no `budget.*`, any flow but `chat` | `<flow> requires a budget: specify with -p budget.cost=...,budget.duration=...,budget.output_tokens=...` |
| `--resume` | see [Picking a run up](#picking-a-run-up) |
| an environment unreachable or smaller than declared | the reason, naming the role |
| a harness with no room anywhere its runtime's affinity names | see [Where the harness runs](#choosing-where-the-harness-runs) |
| a skill a role names that cannot be found or fetched | the reason, naming the skill |

### Output {#watching-a-run}

<span id="output-streams"></span>

| Stream | Terminal (`--json` off) | Piped or redirected (`--json` off) | `--json` |
| --- | --- | --- | --- |
| stdout | each `result`'s text, only where stdout and stderr are **not** both terminals | each `result`'s text, one write per turn, followed by `\n` | NDJSON objects only; `sys.stdout` is redirected to stderr for the run |
| stderr | the run, styled, with a live clock | the run, same lines, no escapes, no clock | lines printed by the flow; `hmz exec: …` notes |

Escapes are written to a stream only where [`colours`](#colour) says so; the clock is drawn
only where stderr is a terminal **and** escapes are allowed.

#### Human-readable lines {#human-lines}

One line (or block) per event, in order. `●` is `⏺` on macOS.

| Event `kind` | Drawn as | Style |
| --- | --- | --- |
| `begins` | `● <agent> is working[ · conversation <i> of <n>]` (suffix only where the agent holds ≥ 2 sessions) | dim |
| `text` | `● <first line>`, further lines indented two spaces | bullet green |
| `reasoning` | each line as is | dim italic |
| `tool` | `● <name>(<rest of text>)` | bullet green, arguments dim |
| `subagent`, `subagent-ends` | `● <name>(<about>) started` / `… done` | bullet cyan |
| `notice` | `● <text>` | bullet yellow, text dim |
| `asks` | `● <text>` | yellow |
| `failed` | `hmz: <text>` | red |
| `result` | cost footer (below), then the answer on stdout as above | dim |
| `ends` | `✻ Worked for <s>s · <agent>` | dim |
| `took` | nothing | |

Cost footer: `✻ <kind> <count>[ · <kind> <count>…] · [<money> · ]<model> · <agent>`, drawn
only for a `result` carrying `spent`. `<model>` is the one model the result's `tokens` names,
where it names exactly one (the model a [fallback](/user/settings#fallback) carried the turn
to, or the one an alias resolved to), else the agent's configured model; it is also what the
money is priced at. Kinds in the order `input`, `output`, `cache_read`,
`cache_write`, `reasoning`, then any other alphabetically. Counts: `< 1000` as an integer,
`< 1 000 000` as `<n.n>k`, else `<n.nn>M`. Money is omitted for a model with no known price;
otherwise `$<n>` with no decimals from $100, two decimals from $0.01, four below, `$0.00` for
zero.

Clock (terminal only, 10 frames/s, spinner `dots`, removed when the run ends):
`<agent> is working · <s>s` for one open turn; `<n> turns working · <s>s` for several, timed
from the oldest.

#### `--json` {#ndjson}

One JSON object per event, UTF-8, one per line, flushed as written. Every object carries every
key:

| Key | Type | Value |
| --- | --- | --- |
| `at` | number | Unix time the record was made. |
| `agent` | string | The agent's id: the role it fills. |
| `cli` | string | The backend (`claude`, `codex`, …, or an ACP CLI's name). |
| `model` | string | The model it was configured with. |
| `session` | string | The backend's own id for the conversation; `""` before it has named one, and for events not about one conversation. |
| `kind` | string | One of the kinds below. |
| `text` | string | The words. |
| `whose` | string | For `subagent` and `subagent-ends`, the backend's id for that sub-agent; else `""`. |
| `tokens` | object | On `result`: `{model: tokens}` from a backend that reports it; else `{}`. |
| `spent` | object | On `result`: tokens by kind (`input`, `output`, `cache_read`, `cache_write`, `reasoning`), only the kinds the backend reports; else `{}`. |

| `kind` | Meaning |
| --- | --- |
| `begins`, `ends` | A turn starts; a turn is over. |
| `text` | The agent's words. |
| `reasoning` | The agent thinking aloud. |
| `tool` | A tool call. |
| `subagent`, `subagent-ends` | A sub-agent the agent started, and its end. |
| `asks` | The agent asking its user a question. |
| `took` | A line put into the running turn is now in front of the model; `text` is that line. |
| `notice` | humanize about the turn: a rate limit waited out, another account taking over, a turn cut off or ended for silence. |
| `failed` | The turn failed; `text` is why. Closes the turn. |
| `result` | The answer the turn ends on. Closes the turn. |

Lines that are not events (`hmz exec: …` notes, the flow's own prints) go to stderr.

```console
$ hmz exec -f chat -a assistant=claude/claude-opus-5:high --json "say hello" | jq -c 'select(.kind == "result")'
{"at":1789026740.6,"agent":"assistant","cli":"claude","model":"claude-opus-5","session":"1d1ff959","kind":"result","text":"Hello.","whose":"","tokens":{"claude-opus-5":2080},"spent":{"input":2000,"output":80}}
```

#### Colour {#colour}

Whether escapes are written to a stream is settled once, in this order; the first that
applies wins:

| # | Condition | Escapes |
| --- | --- | --- |
| 1 | `NO_COLOR` set and non-empty | no |
| 2 | `TERM=dumb` | no |
| 3 | `FORCE_COLOR` set, non-empty and not `0` | yes |
| 4 | the stream is a TTY | yes |
| 5 | otherwise | no |

`FORCE_COLOR` does not make a stream count as a terminal: the layout stays the piped one and
no clock is drawn. `rich` is imported only where escapes are written.

### Nobody is at the prompt {#nobody-is-at-the-prompt}

The run's [outworlder](/reference/flows#the-person-at-the-prompt) is away for the whole run. A
flow's question is answered at once: `""` for text, the schema's defaults for a model, or
`OutworlderAway` where a field has no default. An agent's own question is answered with
nobody. `asks` events still appear in the output.

### Signals {#signals}

| Signal | Effect | Exit |
| --- | --- | --- |
| `SIGINT`, `SIGTERM`, `SIGHUP` | The run is stopped as by `Run.stop()` (from a helper thread). The process waits until the run has let go of what it made — sessions closed, containers removed. `hmz exec` prints no traceback of its own. A signal already set to `SIG_IGN` (a hangup under `nohup`, an interrupt to a background job of a non-interactive shell) stays ignored. | `128 + signum` of the first: `130`, `143`, `129` |
| a second `SIGTERM` or `SIGHUP` | Ignored while the run lets go. | as the first |
| a second `SIGINT` | Ends the process at once, by `SIGINT` itself, without waiting for the run to let go: what it made may be left behind. | `130` (killed by `SIGINT`) |

An interrupt that arrives while the flow is still being loaded, or after the run has ended,
also exits `130` without a traceback.

A run that ends because its budget was reached is not a failure: stderr gets
`hmz exec: stopped -- <why>` naming the limit, and the exit status is `0`.

## `hmz internal` <Badge type="warning" text="not typed by hand" /> {#hmz-internal}

```text
hmz internal <command> [<args>...]
```

The command lines humanize starts its own processes with. Each still runs when typed.
`hmz internal -h` prints the help below and exits `0`. `hmz internal` with no command, or an
unknown one, prints the usage and an argparse error (`the following arguments are required:
COMMAND`, `invalid choice: …`) and exits `2`.

| Command | Summary as printed | Spawned by |
| --- | --- | --- |
| [`anchor`](#hmz-internal-anchor) | `run an agent turn on another machine` | every turn whose work lands on another machine |
| [`cred`](#hmz-internal-cred) | `run a program with credentials from an account` | every turn or login under an account, and every turn whose sessions humanize keeps |
| [`fence`](#hmz-internal-fence) | `run a program held to what its flow permits` | every turn of an agent whose permission fences anything |
| [`hook`](#hmz-internal-hook) | `relay agent hooks to a flow` | a CLI's hook table, once per hook call |
| [`tools`](#hmz-internal-tools) | `relay agent tool calls to a flow` | a CLI's MCP configuration |

### `hmz internal anchor` {#hmz-internal-anchor}

```text
hmz internal anchor [options] AGENT [ARGS...]
hmz internal anchor serve …
hmz internal anchor rendezvous …
```

Runs a coding agent here whose work lands on another machine. A first word of `serve` or
`rendezvous` selects the subcommand; otherwise every word after the options is the agent and
its own arguments. Loads `coganchor` and nothing else of humanize. Semantics:
[Remote execution](/reference/remote-execution).

| Option | Default | Meaning |
| --- | --- | --- |
| `--target URL` | `$HUMANIZE_TARGET`, else `local` | `ssh://HOST`, `docker://CONTAINER[@ENDPOINT]`, `apple-container://CONTAINER`, `tcp://HOST:PORT`, `peer://TICKET@HOST:PORT`, or `local[:DIR]`. |
| `--harness WHERE` | `$HUMANIZE_HARNESS`, else `local` | Where the agent process and its supervisor run: `local`, `same` (wherever `--target` is), or a target spelling. |
| `--broker HOST` | `$HUMANIZE_RENDEZVOUS`, else this machine's outward-facing address | Where the two halves dial to be introduced, when harness and target differ. |
| `--workspace PATH` | the current directory | The project directory as it exists on the target. |
| `--chdir PATH` | `--workspace` | Where inside the workspace the agent starts. |
| `--remote-path PATH` | `--workspace` | Where the workspace really lives on the target. |
| `--shadow PATH` | `$HUMANIZE_SHADOW`, else `--workspace` | The mirror directory on the harness's machine. |
| `--local-path PATH` | — | Keep this path on this machine even inside the workspace. Repeatable. |
| `--local-exec PATH` | — | Run programs under this path here. Repeatable. |
| `--redirect FROM=TO` | — | Answer this path (file, or directory subtree) with that one, kept local. Repeatable. |
| `--private NAME` | — | Keep this variable out of the agent's commands on the target. Repeatable. |
| `--net {local,remote}` | `local` | Where the agent's own TCP connections go. Commands always use the target's network. |
| `--net-allow HOST[:PORT]` | — | With `--net remote`, keep connections to this host local. Repeatable. |
| `--token TOKEN` | `$HUMANIZE_TOKEN` | Shared secret a `tcp://` target expects. |
| `--force` | off | Use the mirror directory even if it holds unrelated files. |
| `--native` | off | Run the CLI installed on the target instead of supervising one here. |
| `--hush NAME` | — | With `--native`, unset this variable for the CLI on the target. Repeatable. |
| `--project NAME=DIR` | — | With `--native`, put this credentials directory on the target for the session and set `NAME` to it. Repeatable. |
| `--carry DIR=PATH` | — | With `--native`, put this directory into the target's workspace at `PATH` for the turn. Repeatable. |
| `--installs LINE` | — | With `--native`, the install line to report where the target lacks the CLI. |
| `--fence JSON` | — | Hold the agent to this [fence](/reference/agents#the-fence) on both machines. |
| `--check` | off | Connect, print what was found, exit. |
| `--log-level {debug,info,warning,error}` | `$HUMANIZE_LOG`, else `warning` | Logging to stderr. |

`--check` prints, on stdout, lines `target`, `hostname`, `python … (pid …)`, one `export <virtual> -> <real>` per export, and `workspace <path> (<n> entries)`.

| Exit | When |
| --- | --- |
| agent's own | the agent ran |
| `0` | `--check` succeeded |
| `1` | connection, protocol, OS or value error (`hmz: <why>` on stderr) |
| `2` | no agent and no `--check` (``no agent given; try `hmz internal anchor claude` ``), or settings no session can run under |
| `127` | `--native` and the target has no such CLI |
| `130` | interrupted |

#### `hmz internal anchor serve` {#hmz-internal-anchor-serve}

```text
hmz internal anchor serve --export VIRTUAL[:REAL] [--export …]
    (--stdio | --listen [HOST:]PORT | --peer TICKET@HOST:PORT)
    [--token TOKEN] [--log-level {debug,info,warning,error}]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--export VIRTUAL[:REAL]` | — | **Required, repeatable.** A directory: `VIRTUAL` as the agent sees it, `REAL` where it is here. |
| `--stdio` | | Serve one session over stdin/stdout. |
| `--listen [HOST:]PORT` | host `127.0.0.1` | Serve TCP connections. |
| `--peer TICKET@HOST:PORT` | | Serve one session through a rendezvous broker. |
| `--token TOKEN` | `$HUMANIZE_TOKEN` | Shared secret required from clients. |
| `--log-level` | `$HUMANIZE_LOG`, else `warning` | |

Exactly one of `--stdio`, `--listen`, `--peer`.

| Exit | When |
| --- | --- |
| `0` | served until the session or the process ended |
| `1` | cannot listen (`hmz: cannot listen on <host>:<port>: <why>`), or cannot dial the peer |
| `2` | a bad `--export`; a malformed address (`hmz: malformed listen address '<a>'; expected [HOST:]PORT`); a non-loopback `--listen` without a token (`hmz: cannot listen on a non-loopback address without --token`). Loopback is `127.0.0.1`, `::1`, `localhost`. |

::: danger
A listener reachable from other machines runs commands for whoever holds its token. See
[Security](/user/security).
:::

#### `hmz internal anchor rendezvous` {#hmz-internal-anchor-rendezvous}

```text
hmz internal anchor rendezvous [--listen [HOST:]PORT] [--punching SECONDS]
    [--log-level {debug,info,warning,error}]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--listen [HOST:]PORT` | `0.0.0.0:0` (every interface, any free port) | Where to listen. A bare port listens on `0.0.0.0`. |
| `--punching SECONDS` | `4.0` | How long two halves may try to reach each other before the broker relays their bytes. |
| `--log-level` | `$HUMANIZE_LOG`, else `info` | |

Prints `hmz internal anchor rendezvous listening <bound> <landed>` on stderr once listening.
Pairing is by 128-bit ticket; there is no token. Exits `2` on a malformed address, `1` when it
cannot listen, `0` otherwise.

### `hmz internal cred` {#hmz-internal-cred}

```text
hmz internal cred (--map FROM=TO | --keep FROM=TO)... [--] COMMAND [ARGS...]
```

Runs `COMMAND` here with the syscalls naming certain paths answered from others: an account's
credential files from its [provider directory](/reference/providers), and kept sessions from
where humanize keeps them.

| Option | Meaning |
| --- | --- |
| `--map FROM=TO` | Repeatable. Answer absolute path `FROM` (a file, or everything under a directory) with `TO`; reads may be served from an in-memory copy. |
| `--keep FROM=TO` | Repeatable. As `--map`, never by copying; creates what the program writes. `FROM` may contain a glob in any component. |

| Exit | When |
| --- | --- |
| the program's | it ran |
| `1` | it could not be supervised (`hmz internal cred: <why>`); it is never run unsupervised |
| `2` | no program (`no program given; try `hmz internal cred --map FROM=TO -- claude``); no `--map`/`--keep` (`nothing to answer with anything: give at least one --map or --keep`); a malformed mapping |

### `hmz internal fence` {#hmz-internal-fence}

```text
hmz internal fence --policy JSON [--] COMMAND [ARGS...]
```

Runs `COMMAND` inside a [fence](/reference/agents#the-fence): on Linux, Landlock for paths and,
where the network is cut, a seccomp filter admitting only TCP and Unix sockets; on macOS, the
whole fence as one Seatbelt profile applied by `/usr/bin/sandbox-exec`. Where the network is
cut, a loopback proxy (`HTTPS_PROXY` and related, `NO_PROXY` emptied) passing only the fence's
hosts; `TMPDIR` set to the fence's scratch directory.

| Option | Meaning |
| --- | --- |
| `--policy JSON` | **Required.** The fence as JSON, or `@PATH` for a file holding it. |

| Exit | When |
| --- | --- |
| the program's | it ran |
| `2` | no `--policy`; no program (`no program given; try `hmz internal fence --policy=... -- claude``) |
| `126` | the fence cannot be put up here (no Landlock, or no way to cut TCP; on macOS, a process already inside a sandbox); the program never ran (`hmz internal fence: <why>`) |

### `hmz internal hook` {#hmz-internal-hook}

```text
hmz internal hook --at SOCKET
```

Reads one hook call on stdin (JSON, re-serialised onto one line), sends it followed by `\n` to
the Unix socket `SOCKET`, and writes the one line answered to stdout. See
[Agents › Hooks](/reference/agents#hooks).

| Exit | When |
| --- | --- |
| `0` | always after reading the line: whatever the flow answered; when the socket cannot be connected (`hmz internal hook: <socket>: <why>` on stderr); and when it closes before answering (silently). Empty stdout lets the tool through. |
| `1` | an unreadable command line. Never `2`, which the CLIs read as the hook refusing the tool. |

### `hmz internal tools` {#hmz-internal-tools}

```text
hmz internal tools --at SOCKET
```

Carries the tool protocol both ways at once between stdin/stdout and the Unix socket
`SOCKET`; the end of either direction ends the other.

| Exit | When |
| --- | --- |
| `0` | either end closed |
| `1` | the socket cannot be reached (`hmz internal tools: <socket>: <why>`) |
| `2` | no `--at` |

## Exit statuses {#exit-statuses}

| Status | Command | Meaning |
| --- | --- | --- |
| `0` | all | Success. For `hmz exec`, including a run its budget stopped. |
| `1` | `hmz` | Runs held by an older humanize; or the host let go of the interface. |
| `1` | `hmz exec` | The flow raised (traceback on stderr; the crash is reported where reporting is on). |
| `1` | `internal …` | Could not connect, listen, supervise, or reach a socket. |
| `2` | all | The line was wrong: argparse rejections and everything in [What is refused](#what-is-refused-before-anything-runs). |
| `126` | `internal fence` | The fence could not be put up; the program never ran. |
| `127` | `internal anchor --native` | The target has no such CLI. |
| `130` | `hmz exec`, `internal anchor` | Interrupted (`SIGINT`); for `hmz exec`, after the run has let go of what it made. |
| `129`, `143` | `hmz exec` | `SIGHUP`, `SIGTERM`, after the run has let go of what it made. |
| *program's* | `internal anchor`, `cred`, `fence` | The wrapped program's own status. |

## Environment variables {#environment-variables}

Variables these commands read. The complete list, with every layer's, is
[Environment variables](/reference/environment).

| Variable | Read by | Values | Effect |
| --- | --- | --- | --- |
| `HUMANIZE_HOME` | all | a path | Where humanize keeps what outlives a run. Default `~/.hmz`, which a `~/.humanize` is moved to. Empty is unset. Not created until written. |
| `HUMANIZE_DAEMON` | `hmz` | `off`, `0`, `no` (case-insensitive, stripped) | Hold runs in the interface's process. Anything else, empty included, holds them apart. |
| `HUMANIZE_NAME` | `hmz`, SDK links | a name | The name a frontend attaches under, before `@<kind>`. Default: the login name. |
| `HUMANIZE_SENTRY` | `hmz`, `hmz exec` | `on`, `off` | Answers [reporting](/user/reporting) for this process without writing the answer down. |
| `NO_COLOR`, `TERM`, `FORCE_COLOR` | all | see [Colour](#colour) | Escapes. |
| `TEXTUAL_THEME` | `hmz` | a Textual theme name | The interface's theme; unknown names are ignored. |
| `TMUX`, `TERM_PROGRAM`, `LC_TERMINAL` | `hmz` | | Decide `TEXTUAL_DISABLE_KITTY_KEY` ([Terminal preparation](#terminal-preparation)). |
| `HUMANIZE_TARGET` | `internal anchor` | a target URL | Default `--target`. |
| `HUMANIZE_HARNESS` | `internal anchor` | a harness spelling | Default `--harness`. |
| `HUMANIZE_SHADOW` | `internal anchor` | a path | Default `--shadow`. |
| `HUMANIZE_RENDEZVOUS` | `internal anchor` | a host | Default `--broker`. |
| `HUMANIZE_TOKEN` | `internal anchor`, `anchor serve` | a secret | Default `--token`. |
| `HUMANIZE_LOG` | `internal anchor`, `serve`, `rendezvous` | `debug` `info` `warning` `error` (case-insensitive, stripped) | Default `--log-level`. Any other value is ignored with `hmz: ignoring HUMANIZE_LOG='<value>', which is not one of debug, info, warning, error` on stderr. |

Set by `hmz internal anchor` inside the agent it runs: `HUMANIZE` (the launching half's
version), `HUMANIZE_TARGET`, `HUMANIZE_WORKSPACE`.

## Files {#files}

Paths these commands read or write, under `$HUMANIZE_HOME` (`~/.hmz`). The whole layout
is [Files](/reference/files).

| Path | Command | Access |
| --- | --- | --- |
| `epics/<workspace>/<datetime>-<hex>/` | `hmz exec`, runs started from `hmz` | written: one [epic](/reference/tracing#epics) per run |
| `settings.yaml` | `hmz` | read and written: [what the interface remembers](/reference/tui#what-it-remembers); its `runtimes`, `fallbacks` and `clis` are read by all when an agent or environment is opened |
| `history.jsonl` | `hmz` | read and written: [prompt history](/reference/tui#history) |
| `epics/<workspace>/<datetime>-<hex>/host.log` | `hmz` | appended: what the [host process](/reference/daemon#files) wrote while it held that run. The daemon's socket, record, lock and log are in the machine's temporary directory, not here |
| `prices.json` | all | model prices, refreshed when older than a day by the interface as it opens and by a run as it starts |
| `providers/`, `models/` | all | read when an agent or environment is opened |
| `installed/`, `flowverses/`; `~/.hmz/flows/` and `./.hmz/flows/` (fixed paths, not moved by `HUMANIZE_HOME`) | all | read when `-f` is resolved |

## Python equivalents {#python-entry-points}

Every command is a shell around [`hmz.sdk.Hmz`](/reference/sdk#hmz):

| Command line | Python |
| --- | --- |
| `hmz exec <argv>` | [`Hmz().exec(argv)`](/reference/sdk#hmz-exec) |
| reading an `hmz exec` line | [`Hmz().read(argv)`](/reference/sdk#hmz-read) → `Line` |
| `hmz exec` without the line | [`Hmz().run(flow, task, agents=…, envs=…, params=…, budget=…, profile=…, resume=…, harness=…)`](/reference/sdk#hmz-run) |
| `hmz` (as a frontend of held runs) | [`Daemons().host().link()`](/reference/sdk#daemons) |
