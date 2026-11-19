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
hmz chat [-a <agent>] [--resume <chat> | --worktree] [--] <message>  say one message to an agent here
hmz web [<options>]                    serve every workspace's runs to a browser
hmz daemon serve|connect --stdio|pair|devices|install|uninstall  this machine's daemon
hmz relay serve [--listen <host>:<port>]  relay daemons and the devices that reach them
hmz update                             update hmz to its newest release
hmz backup <epic> [--to <target>]...   back epics up to git repositories, or download them
hmz internal <command> [<args>...]     processes Humanize spawns for itself
```

| Command | Function in `hmz.cli` | Summary as `hmz --help` prints it |
| --- | --- | --- |
| *(none)* | `opens` | Opens the [terminal interface](/reference/tui). |
| [`exec`](#hmz-exec) | `_exec` | `run an agent flow in this directory` |
| [`chat`](#hmz-chat) | `_chat` | `say one message to an agent in this directory` |
| [`web`](#hmz-web) | `_web` | `open this machine's epics in a browser on it` |
| [`daemon`](#hmz-daemon) | `_daemon` | `run, reach, pair and install this machine's daemon` |
| [`relay`](#hmz-relay) | `_relay` | `relay daemons and the devices that reach them` |
| [`update`](#hmz-update) | `_update` | `update hmz to its newest release` |
| [`backup`](#hmz-backup) | `_backup` | `back epics up to git repositories, or download them` |
| [`internal`](#hmz-internal) | `_internal` | `internal commands used by Humanize; do not run directly` |

`python -m hmz` is the same program. The console script is `hmz = "hmz.cli:main"`.

Every `--help` is a summary: no flag's help, command summary, description or epilog runs past
thirty words. This page is the full account of each.

## Routing {#routing}

`hmz.cli.main(argv)` routes the line before any command's own parser sees it:

| `argv` | Result | Exit |
| --- | --- | --- |
| empty | [Opens the interface](#hmz). | `0`, or `1` (see below) |
| exactly `["--version"]` | Prints `hmz <version>` (from the installed distribution's metadata) to stdout. | `0` |
| first word is `exec`, `chat`, `web`, `daemon`, `relay`, `update`, `backup` or `internal` | Hands every later word to that command **unchanged**, `--help` included. No other command's module is imported. | the command's |
| `-h` or `--help` first | Prints the top-level help. | `0` |
| anything else | argparse usage error on stderr (below). | `2` |

```console
$ hmz bogus
usage: hmz [-h] COMMAND ...
hmz: error: argument COMMAND: invalid choice: 'bogus' (choose from exec, web, daemon, relay, update, backup, internal)
```

`hmz --version <anything>` is not the version form and fails the same way.

## `hmz` {#hmz}

```text
hmz
```

Takes no arguments and no options. Opens the terminal interface in the calling process on
the current directory, as it was [last left](/reference/tui#what-it-remembers). Starts no run.

### Where the runs are held {#where-runs-are-held}

The interface is always one frontend of a [host](/reference/daemon#hosting) of this
machine's daemon, reached over its unix socket, whatever the terminal. The runs are never held
in the interface's process. Which host is decided once, at start, in this order:

| # | Condition | The interface |
| --- | --- | --- |
| 1 | this machine's daemon is found and its `protocol` is not `2`, or a host an older Humanize left holds this directory | is not opened. See [Errors](#hmz-errors). |
| 2 | a host for this directory is found through the daemon | links to it as `kind="tui"`. |
| 3 | no host is found | starts one, and the daemon where none is, with [`hmz.daemon.host()`](/reference/daemon#discovery), and links to it. |

Steps 1–3 are tried up to **3** times, **0.5 s** apart, while linking raises `OSError`
(a host found on its way out). After the third failure the interface is not opened and the
last `OSError` is printed (below).

### Terminal preparation

Before Textual is imported, `hmz` sets `TEXTUAL_DISABLE_KITTY_KEY=1` in its own environment
(unless already set) when `TMUX` is unset or empty and either `TERM_PROGRAM=iTerm.app` or
`LC_TERMINAL=iTerm2`. See [TUI › Keyboard protocol](/reference/tui#keyboard-protocol).

### Errors and exit {#hmz-errors}

| Condition | stderr | Exit |
| --- | --- | --- |
| The interface closed normally | — | `0` |
| This machine's runs are held by an older Humanize (daemon `protocol` not `2`), or this directory's by a host one left | `hmz: the runs on this machine are held by an older Humanize (pid <n>); stop it with that version`, or `the runs in <dir> …` | `1` |
| The host let go of the interface ([`gone`](/reference/daemon#gone)) | `hmz: <why>` (or `hmz: disconnected from the epics`), printed as the interface closes | `1` |
| No host could be linked in 3 tries | `hmz: the daemon cannot be reached: <OSError>` | `1` |

## `hmz exec` {#hmz-exec}

Runs one [flow](/reference/flows) in the current directory (the *workspace*) to its return,
with no interface. The run's [outworlder](#nobody-is-at-the-prompt) is always away.

The flow does not run in `hmz exec`'s process. `hmz exec` attaches to a new exec slot
(`exec:<hex>`, see [Daemon › Slots](/reference/daemon#slots)) of the workspace on this machine's
daemon, starting the daemon where none runs, sets every role away, starts the epic there
(`epic.start`), and follows its messages until `ended`, drawing them as below. Killing
`hmz exec` (`SIGKILL`, or the terminal closing under it) does not stop the epic: the daemon's
host runs it to its end. Only the [signals](#signals) it handles stop it.

```text
usage: hmz exec [-h] -f FLOW [-a ROLE=SPEC[,...]] [-e ROLE=SPEC[,...]]
                [-p KEY=VALUE[,...]] [--profile-flow] [--profile-environment]
                [--resume] [--json]
                [--backup NAME]
                task
```

### Options {#exec-options}

| Option | Value | Occurrences | Default | Meaning |
| --- | --- | --- | --- | --- |
| <span id="exec-flow"></span>`-f`, `--flow` | [`<ref>`](#naming-a-flow) | ≥ 1 (**required**; the last wins) | — | The flow. |
| <span id="exec-agents"></span>`-a`, `--agents` | [`<agent>`](#writing-an-agent) list | 0‥n, merged | none | One agent per agent role. |
| <span id="exec-envs"></span>`-e`, `--envs` | [`<env>`](#writing-an-environment) list | 0‥n, merged | none | One environment per environment role. |
| <span id="exec-params"></span>`-p`, `--params` | [`<param>`](#writing-params) list | 0‥n, merged | the flow's defaults | Fields of the flow's `FlowParams`, and, as [`budget.<limit>`](#writing-a-budget), what the run may spend: **required**. |
| <span id="exec-profile"></span>`--profile-flow` | flag | 0‥1 | off | [Profile](/reference/tracing#profiling-a-run) the flow's own Python, as well as tracing the run. |
| `--profile-environment` | flag | 0‥1 | off | [Profile](/reference/tracing#profiling-a-run) the programs the run's agents start, as well as tracing them. |
| <span id="exec-resume"></span>`--resume` | flag | 0‥1 | off | [Pick up](#picking-a-run-up) the newest run of this flow here. |
| <span id="exec-json"></span>`--json` | flag | 0‥1 | off | Write the run as [NDJSON](#ndjson) on stdout. |
| <span id="exec-backup"></span>`--backup` | a [backup target](/reference/settings#backup) name, or `none` | 0‥n, merged | `backup.defaults` | Where the epic is [backed up](/user/backups); `none` anywhere: nowhere. A name settings has none of exits `2`. The host holding the epic backs it up. Once the epic has ended with a backup its end queued not done, as `backed` of `runs.get` says (only a target whose policies hold `end` has one), `hmz exec` says `hmz exec: backing the epic up` on stderr and stays attached, so that the host waits too, for at most 60 s; one still not done then is left, saying ``hmz exec: a backup took longer than 60s and was left; `hmz backup EPIC` sends it again``, and the exit is the epic's. |
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

agent         = identifier , "=" , cli , ( "@" , provider )? , "/" , model , ( ":" , effort )? ;
cli           = ? a CLI name or alias, or an ACP CLI's name; contains no "@", "/" or "," ? ;
provider      = ? an account name; non-empty after "@" ? ;
model         = ? any text, may contain "/" and ":" ; non-empty ? ;
effort        = ? any text without ":" ; "auto" means the CLI's default ? ;

env           = identifier , "=" , backend , ( "@" , ( runtime | "[" , host , "]" ) )? , workdir? ;
backend       = "local" | "ssh" | "docker" | "swarm" | "apple-container" | "slurm" ;
runtime       = ? the name of a runtime saved for that backend ? ;
host          = ? [user@]host[:port], or an ssh config alias; ssh only ? ;
workdir       = "/" , ? any text ? ;                       (* "/~" or "/~/…" is home-relative *)

param         = key , "=" , ? any text ? | limit ;
limit         = "budget." , ( name | "graceful" , ( "." , name )? ) , "=" , ? value ? ;
name          = "duration" | "cost" | "output_tokens" ;
```

#### Items {#items}

- Each occurrence of `-a`, `-e` or `-p` is split into items at every `,` that is followed,
  after optional whitespace, by a `key=`, `budget.key=` or `budget.graceful.key=` (regex
  `,\s*(?=(?:budget\.(?:graceful\.)?)?[A-Za-z_][\w-]*=)`). A comma not followed by one belongs to the value:
  `-p tags=a,b,c` is one item.
- A value therefore cannot contain `,<key>=`.
- Items of every occurrence of one option form one list, in the order written:
  `-a x=…,y=…` and `-a x=… -a y=…` are the same line.
- An item that is empty or only whitespace is refused: `<flag> '<value>': an item is empty`.
- Leading and trailing whitespace around an `-a` or `-e` item, and around a `-p` key, is
  ignored; a `-p` value is kept as written (a `budget.<limit>` value is read stripped).

### Naming a flow (`-f`) {#naming-a-flow}

```text
ref = [ "@" , flowverse , "/" ] , [ user , "/" ] , flow , [ ":" , name ]
    | path
    | "git+" , url , [ "@" , rev ] , [ "#" , subdir ] , [ ":" , name ] ;
path = ( "." | "/" | "~" ) , { character } ;
```

| Form | Resolves to |
| --- | --- |
| `<flow>` | The first flow of that name, looking in `local`, `user`, `official` (what is installed from it), then the flows installed from added flowverses (the order of [`Flowverses.nearest`](/reference/sdk#flowverses)). |
| `<user>/<flow>` | The flow installed from the official flowverse's `flows/<user>/<flow>/`: `alice/kernel`. |
| `@<flowverse>/<flow>`, `@<flowverse>/<user>/<flow>` | The flow installed from that flowverse. `@local/…` is `./.hmz/flows/`, `@user/…` is `~/.hmz/flows/`. |
| `…:<name>` | Another flow defined in the same module. |
| a path (`./x`, `../x`, `/x`, `~/x`, `./x.py`) | That directory or file. Only what starts with `.`, `/` or `~` is a path. |
| `git+<url>[@<rev>][#<subdir>][:<name>]` | The flow in `<subdir>` of a repository (its root without `#`), cloned and pinned at that revision, installing nothing: `git+https://github.com/humanfia/humanize1-flow@v0.1.0#humanize1:rlcr`. |

A flow a flowverse's index lists is not run until it is installed (`hmz exec` installs
nothing): naming one is refused with `<name>: not installed -- install it from /flow
(flowverse <flowverse>)`. A name said as before the `@` is refused saying how it is said now
(`local/x: a flow of local is called @local/x now`), as is a relative path without its `./`
(`flows/x: a path starts with ./, / or ~, as ./flows/x does`). Resolution, module loading and
the several-flows-per-module rule are specified in
[Flows › Where flows live](/reference/flows#where-flows-live) and
[Flows › Refs](/reference/flows#refs).

### Writing an agent (`-a`) {#writing-an-agent}

```text
<role>=<cli>[@<provider>]/<model>[:<effort>]
<role>=<nous>
```

The rest after `=` is a concrete [nous](/user/settings#nous); one with no `/` is the name of a
virtual nous written on the Nous page, and the agent is built at the concrete nous its graph
starts at and walks the graph each turn. The epic's record states that concrete nous as the
role's harness, model and effort, so a run resumed from the record starts there.

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
| `dsh` | `deepseek-harness` | `max` `high` `low` `off` | `pip install 'deepseek-harness-sdk>=0.1.5rc1,<0.1.6' 'python-dotenv>=1.2.3'` | `hmz[dsh]` |
| `grok` | `grok-build`, `grokbuild` | `xhigh` `high` `medium` `low` | `npm i -g @xai-official/grok` | |
| `kimi` | `kimi-code` | `max` `high` `medium` `low` | `npm i -g @moonshot-ai/kimi-code` | `hmz[kimi]` |
| `mcode` | `minimax`, `minimax-code` | `max` `xhigh` `high` `medium` `low` | `npm i -g @minimax-ai/code` | |
| `mimo` | `mimocode`, `mimo-code` | `xhigh` `high` `medium` `low` `minimal` | `npm i -g @mimo-ai/cli` | |
| `omp` | `oh-my-pi` | `max` `xhigh` `high` `medium` `low` `minimal` `off` | `curl -fsSL https://omp.sh/install \| sh` | |
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
| `<backend>` | `local`, `ssh`, `docker`, `swarm`, `apple-container` or `slurm`. |
| `<provider>` | Absent: this machine — a directory here for `local`, docker's default daemon here for `docker`, the swarm this machine manages for `swarm`, this Mac's [Apple containers](/user/containers#apple-containers) with nothing saved for `apple-container`, the Slurm cluster this machine submits to, with its defaults, for `slurm`. `local` takes no provider at all; `ssh` always takes one. `@<name>`: the [runtime](/reference/machines#runtimes) saved under that name for that backend; a name nothing is saved under is refused. `@[<host>]`, for `ssh` only: a host nobody saved, `[user@]host[:port]` or an alias of the ssh config, handed to `ssh` as it is; it never stands for a saved runtime and has no fallback list. |
| `<workdir>` | From the first `/` after the provider. `/~` and `/~/…` are relative to the ssh login's home for `ssh`, and to this user's home for `local` and for `docker`, `swarm`, `apple-container` or `slurm` on this machine. Omitted: the saved runtime's own workdir, refused where no runtime is named or it was saved with none. For `docker`, a directory of the daemon's host, mounted into the container at the same path; for `swarm`, one every node its task may land on has, likewise; for `apple-container`, a directory of this Mac, mounted likewise; for `slurm`, a directory of a shared filesystem, at the same path here and on every node its job may land on. |

`local/home/me/repo`, `docker/srv/repo`, `swarm/srv/repo`, `apple-container/Users/me/repo` and
`slurm/lustre/me/repo` are this machine's; `ssh@gpu-box/~/repo`, `docker@gpubox/srv/repo`,
`swarm@cluster/srv/repo`, `apple-container@mac/Users/me/repo` and `slurm@hpc/lustre/me/repo` are
saved runtimes, and `ssh@gpu-box` alone is the workdir
`gpu-box` was saved with; `ssh@[me@far.host:2222]/srv/repo` is a host nobody saved. A spelling
`-e` refuses with a hint — `local@/x`, `docker@local/x`, `swarm@local/x`,
`apple-container@local/x`, `slurm@local/x`, an unsaved ssh host out of brackets — is read as the one the hint
gives where it was kept in [settings](/reference/settings) or an
[epic](/reference/tracing#epics) (`docker@local`, `swarm@local`, `apple-container@local`, `slurm@local` only
where no runtime is saved as `local`).

Roles the runtime fills — `LocalEnv` roles, which are the workspace — are never given. After
parsing, every environment is opened and probed before the flow is called; an unreachable one,
or one whose machine has fewer CPUs, GPUs or less memory than its role declares, is
[refused](#what-is-refused-before-anything-runs). A `docker` environment's container is started
then, a `swarm` environment's service created and waited for until its task runs, and a `slurm`
environment's job submitted and waited for until it runs -- every environment at once, the
first refusal stopping the rest. Where
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
budget.graceful.duration=<bool> | budget.graceful.cost=<bool> | budget.graceful.output_tokens=<bool>
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
| `graceful.duration`, `graceful.cost`, `graceful.output_tokens` | As `graceful`, for that limit alone, over what `graceful` says: `budget.cost=5,budget.output_tokens=200k,budget.graceful.output_tokens=false` cuts a turn off at its 200 000th token but lets one that reaches $5 finish. | `Graceful` |

With no `budget.*`, every flow is refused, the flows of the official flowverse included. A flow named
`chat` is no exception: it is an ordinary flow. To talk to one agent with no budget, use
[`hmz chat`](#hmz-chat).

A run with a finite `cost` limit first brings the [price list](/reference/files#h-prices-json)
up to date when the copy kept is missing or older than 24 h (at most 20 s; never with
`HUMANIZE_PRICES=off`). A `cost` limit over agents whose model still has no known price cannot
be enforced. The run starts, and stderr first carries:

```text
hmz exec: nobody lists a price for <model>[, <model>…], so cost=<n> cannot stop what it spends
```

A price list that gives any model a price that is not a finite number (`NaN`, an infinity)
refuses the run instead, whatever its budget: `hmz exec: error: the price list …` and exit
status 2, before the first turn.

### Where the harness runs {#choosing-where-the-harness-runs}

The *harness* is an agent's CLI and its supervisor. Nothing on the line says where it runs:
no option of `hmz exec` takes it. Work on this machine (env location `local`) has its
harness here; work on another machine (env location `standalone`) has it where the `harness`
setting of the saved [runtime](/reference/machines#runtimes) it is on says, and nowhere else:
`env` (the default, and the setting of a machine nobody saved) on the environment's machine,
natively; `local` here; `ssh:<name>`, `docker:<name>`, `swarm:<name>`, `apple-container:<name>`
or `slurm:<name>` on another saved runtime.

Once the environments are probed, before the flow is called, every agent's harness is settled
on every machine; a setting that cannot hold it (the CLI missing there, a fence it cannot
hold, a hook gating the agent's tools under `env`, a harness runtime that cannot be reached)
refuses the run (`hmz exec: error: <backend>[@<provider>]: <cli>'s harness cannot run where
its harness setting (<setting>) says: <refusal>`, exit `2`). A runtime a harness setting names
is opened as an environment is, probed before the flow is called and closed with the run. Where
each session's harness went is recorded on the session in the epic as `local`, `env` or
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
| its `resume.jsonl` cannot be copied into the new epic (no epic is left of the request, and the one picked up is left to pick up again) | `<epic> cannot be resumed: its saved progress could not be copied (<reason>)` |

### Processing order {#processing-order}

| Stage | Checks | On failure |
| --- | --- | --- |
| 1. argparse | Options, `-f` and `task` present. | Usage on stderr, `hmz exec: error: <why>`, exit `2`. |
| 2. Spec parsing (`Hmz.read`) | Every `-a`, `-e`, `-p` against its grammar, and every `-e` provider against the runtimes saved; duplicate roles and keys. | Same as 1. |
| 3. Loading (`Hmz.run` → `Runner`, the daemon's `flows.check`) | The daemon reached (else `hmz: the daemon cannot be reached: <why>`, exit `1`); flow resolves and loads; roles, harness kinds, capabilities, effort ladders, params, budget presence, `--resume`. | `hmz exec: error: <why>` (no usage), exit `2`. |
| 4. Opening (`epic.start`, in the host, before the flow is called) | Environments reached and measured; each agent's harness settled where its runtime's harness setting puts it, and the runtimes it goes to reached; skills fetched; with `--resume`, the journal picked up copied into the new epic. | `hmz exec: error: <why>`, exit `2`. |
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
| an `-a` item without `role=` | `-a '<item>': expected <role>=<harness>[@<provider>]/<model>[:<effort>] or <role>=<nous>` |
| an `-a` role that is not an identifier | ``-a '<item>': '<role>' is not a place a flow could declare: what is written before `=` is a field of the tuple of agents the flow declares, so it is a Python identifier`` |
| an `-a` with an empty CLI (`a=/m`) | `-a '<item>': expected [NAME=]CLI[@PROVIDER]/MODEL[:EFFORT]` |
| an `-a` with an unknown CLI | `-a '<item>': unknown CLI '<cli>'; see the CLI reference for supported names` |
| an `-a` with a known CLI but no `/` or no model | `-a '<item>': missing model; expected [NAME=]CLI[@PROVIDER]/MODEL[:EFFORT]` |
| an `-a` naming a virtual nous nobody wrote | `-a '<item>': '<name>' is no nous written down` |
| `@` with no account | `-a '<item>': expected an account after @, as in claude@deepseek/MODEL:EFFORT` |
| a role twice in `-a` | `-a: the role '<role>' is given twice` |
| an `-e` that does not match | `-e '<item>': expected <role>=<backend>[@<provider>][/<workdir>]` |
| no `/<workdir>`, and no runtime saved with one | `-e '<item>': expected <role>=<backend>[@<provider>][/<workdir>]; /<workdir> may be left off only for a runtime saved with one` |
| an `-e` role not an identifier | `-e '<item>': the role '<role>' is not an identifier` |
| unknown backend | `-e '<item>': '<backend>' is not a backend; one of local, ssh, docker, swarm, apple-container, slurm` |
| `ssh` with no host | `-e '<item>': ssh needs a host: ssh@<saved host>/<workdir>, or ssh@[user@host:port]/<workdir> for a host not saved` |
| `ssh` naming a host nobody saved, out of brackets | `-e '<item>': no ssh host is saved as '<name>'; write <role>=ssh@[<name>]/<workdir> for a host not saved` |
| a bracketed host that is not one | `-e '<item>': '<host>' is not an ssh host, as [user@]host[:port]` |
| brackets on `docker`, `swarm`, `apple-container` or `slurm` | `-e '<item>': only ssh takes a host nobody saved; <backend>@<name> names a <backend> runtime saved on the runtimes page of /settings` |
| `docker@local`, `swarm@local`, `apple-container@local`, `slurm@local`, nothing saved as `local` | `-e '<item>': <backend> on this machine names no provider; write <role>=<backend>/<workdir>` |
| `docker`, `swarm`, `apple-container` or `slurm` naming a runtime nobody saved | `-e '<item>': no <backend> runtime is saved as '<name>'; save one on the runtimes page of /settings, or write <role>=<backend>/<workdir> for <backend> on this machine` |
| `docker@`, `swarm@`, `apple-container@` or `slurm@` with nothing after it | `-e '<item>': an @ is written only before a provider; write <role>=<backend>/<workdir>` |
| `local` with an `@` | `-e '<item>': local takes no provider; write <role>=local/<workdir>` |
| a role twice in `-e` | `-e: the role '<role>' is given twice` |
| a `-p` without `key=` | `-p '<item>': expected <key>=<value>` |
| a `-p` key twice | `-p: '<key>' is given twice` |
| `budget` with no limit | `-p '<item>': a budget is given a limit at a time, as budget.cost=5` |
| an unknown `budget.` limit | `-p budget.<limit>: not a limit; one of budget.duration, budget.cost, budget.output_tokens, budget.graceful, budget.graceful.duration, budget.graceful.cost, budget.graceful.output_tokens` |
| a `budget.` value | `-p budget.duration: '<v>' names a unit twice`, `-p budget.duration: '<v>' is negative`, `-p budget.duration: duration '<v>' is too long`, `-p budget.duration: '<v>' is not a valid duration: must be finite and not negative`, `-p budget.duration: '<v>' is not a duration: use seconds, 1h30m, or ISO 8601 like PT1H30M`, `-p budget.cost: '<v>' is not a valid USD cost`, `-p budget.output_tokens: '<v>' must be a whole number of tokens`, `-p budget.output_tokens: '<v>' is not a valid token count: expected a number like 200000 or 200k`, `-p budget.graceful: '<v>' must be true or false` |
| a budget that limits nothing | `-p budget.*: Value error, a budget sets at least one of duration, cost, output_tokens` |
| no such flow | `<ref>: no flow is called '<ref>'` (a path: `<ref>: there is no flow at <ref>`); `<ref>: a flow of local is called @local/<flow> now`; `<ref>: a path starts with ./, / or ~, as ./<ref> does`; `<ref>: not installed -- install it from /flow (flowverse <flowverse>)`; `<ref>: the official flowverse has not been fetched yet -- fetch it from /flow` |
| a role the flow does not declare | `<flow> has no agent role '<role>'; available roles are '<a>', '<b>'` (`… environment role …` for `-e`; `none` where there are none) |
| a role the runtime fills | `<flow>: '<role>' is assigned automatically by the runtime and cannot be set with -a`; `<flow>: '<role>' is the workspace the run started in and cannot be set with -e` |
| a required role unfilled | `<flow> needs an agent for '<role>'; specify each with -a ROLE=CLI/MODEL:EFFORT`; `<flow> needs an environment for '<role>'; specify each with -e ROLE=BACKEND[@PROVIDER]/WORKDIR` |
| a role typed as one CLI given another | `<flow>: '<role>' requires <cli>, but got <cli>` |
| an `@<provider>` naming no account of that CLI | `<flow>: '<role>' names no <cli> account called '<provider>'; make it on the accounts page of /settings` |
| a CLI lacking a capability the role needs | `<flow>: '<role>' needs <Mixin>[, <Mixin>…], which <cli> does not support` |
| an effort off the ladder | `<role>=<spec>: <cli> cannot be asked to think at '<effort>'; expected one of <ladder>` |
| params the flow rejects | `<canonical ref>: <pydantic validation error>` |
| no `budget.*` | `<flow> requires a budget: specify with -p budget.cost=...,budget.duration=...,budget.output_tokens=...` |
| `--resume` | see [Picking a run up](#picking-a-run-up) |
| an environment unreachable or smaller than declared | the reason, naming the role |
| a harness that cannot run where its runtime's harness setting says | see [Where the harness runs](#choosing-where-the-harness-runs) |
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
where it names exactly one (the model a [nous](/user/settings#nous) carried the turn
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
| `agent` | string | The agent's own name, such as `NeiKos496`: never the role it fills. |
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
| `notice` | Humanize about the turn: a rate limit waited out, another account taking over, a turn cut off or ended for silence. |
| `failed` | The turn failed; `text` is why. Closes the turn. |
| `result` | The answer the turn ends on. Closes the turn. |

Lines that are not events (`hmz exec: …` notes, the flow's own prints) go to stderr.

What the flow prints in the host arrives as `printed` records: written to stdout without
`--json`, to stderr with it.

```console
$ hmz exec -f goal -a worker=claude/claude-opus-5:high -p budget.cost=1 --json "say hello" | jq -c 'select(.kind == "result")'
{"at":1789026740.6,"agent":"NeiKos496","cli":"claude","model":"claude-opus-5","session":"1d1ff959","kind":"result","text":"Hello.","whose":"","tokens":{"claude-opus-5":2080},"spent":{"input":2000,"output":80}}
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
| `SIGINT`, `SIGTERM`, `SIGHUP` | The epic is stopped (`epic.stop`, as by `Run.stop()`, from a helper thread). The process waits for its `ended` record, once it has let go of what it made — sessions closed, containers removed. `hmz exec` prints no traceback of its own. A signal already set to `SIG_IGN` (a hangup under `nohup`, an interrupt to a background job of a non-interactive shell) stays ignored. | `128 + signum` of the first: `130`, `143`, `129` |
| a second `SIGTERM` or `SIGHUP` | Ignored while the epic lets go. | as the first |
| a second `SIGINT` | Forces the epic (`epic.force`: every session with a turn open closed), then ends the process at once, by `SIGINT` itself, without waiting for the epic to end. | `130` (killed by `SIGINT`) |
| `SIGKILL`, or anything else that ends the process | The epic is not stopped: the daemon's host runs it to its end. | — |

An interrupt that arrives while the flow is still being loaded, or after the run has ended,
also exits `130` without a traceback.

A run that ends because its budget was reached is not a failure: stderr gets
`hmz exec: stopped -- <why>` naming the limit, and the exit status is `0`.

## `hmz chat` {#hmz-chat}

Takes one turn of a [chat](/user/chat) in the current directory (the *workspace*), with nobody
at a prompt, and ends it. A chat is not a flow and not an epic: it has one agent, no params
and no budget, and is kept under its own id.

```text
usage: hmz chat [-h] [-a SPEC] [--resume CHAT] [--worktree] message
```

`hmz chat` starts the chat on a new chat slot (`chat:`, see
[Daemon › Slots](/reference/daemon#slots)) of the workspace on this machine's daemon, starting
the daemon where none runs (`chat.start`), follows its messages (`epic.attach`) until the turn
is done, and then ends the chat with an empty next message.

| Option | Value | Occurrences | Default | Meaning |
| --- | --- | --- | --- | --- |
| <span id="chat-agent"></span>`-a`, `--agent` | an [`<agent>`](#writing-an-agent) after `<role>=`: `cli[@account]/model[:effort]`, or the name of a virtual nous | 0‥n (the last wins) | the chat agent this workspace remembers ([`workspaces.<path>.chat.agent`](/reference/settings#workspace-settings)); refused where none is, saying to give one with `-a` | The assistant. |
| <span id="chat-resume"></span>`--resume` | a chat's id, as `chat.list` and the chat's page name it | 0‥1 | — | Carry that chat of this workspace on (`chat.start` with `resume`), with `message` as its next turn and its own agent unless `-a` is given. An epic is not carried on, one an earlier hmz recorded for a chat included. |
| <span id="chat-worktree"></span>`--worktree` | flag | 0‥1 | off | Start the chat with its assistant working in a new git worktree of the workspace (`chat.start` with `worktree`). Refused with `--resume` before the daemon is asked: a chat carried on works where it worked. In a directory that is no git repository the daemon refuses the start, exit `2`. |
| `-h`, `--help` | flag | | | Print the help and exit `0`. |
| `message` | positional string | exactly 1 (**required**, not empty) | — | The first message, or the next. Put `--` before one that starts with `-`. |

The message is served as a line said in a chat ([native input](/user/chat#what-a-line-means)),
except that a `$` line naming a flow, and a name hmz keeps (`/clear`, `/resume`, `/exit`,
`/quit`, `/btw`, `/flow`, `/epics`, `/settings`, `/chat`, `/prefer`), are refused, naming it.
`hmz chat` reads `chat.agent` of the workspace only where it is given no `-a`, and changes
nothing any workspace remembers.

The turn is drawn on stderr and the answer written to stdout, as
[`hmz exec`](#watching-a-run) does.

A line the chat serves with no turn ends it the same way, exit `0`: a `!<command>` hmz runs
itself is drawn on stderr as `! <command>`, with what it wrote as errors and `exit <status>`
where that is not `0`, and what it printed is written to stdout; a line the chat refuses is
said why on stderr as `hmz chat: <reason>`.

Where `--resume` cannot carry the chat's conversation on, the turn is answered in a new
conversation in the same chat, and why is said on stderr as `hmz chat: This conversation could
not be carried on (<reason>), so this is a new one.`

| Exit | When |
| --- | --- |
| `0` | The turn is done. |
| `1` | The turn failed: what the harness said, on stderr. Or the daemon could not be reached, as for `hmz exec`. |
| `2` | Refused before the chat started: `hmz chat: error: <reason>` on stderr, a refusal of `chat.start` with its message as `<reason>`. |
| `128 + signum` | `SIGINT`, `SIGTERM` or `SIGHUP`: the chat is left to its host. |

## `hmz web` {#hmz-web}

```text
hmz web [--port <port>] [--no-open] [--attached]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--port <port>` | the port the last `hmz web` of this home listened on (`~/.hmz/web-port`), else `0` | The port to listen on, on `127.0.0.1` and, where this machine has IPv6, on `::1`; `0` picks any free one on both, as does a kept port that is taken now. |
| `--no-open` | off | Print the address and open no browser. |
| `--attached` | off | Stop once standard input closes. |

Serves the page to a browser on this machine until `SIGINT`, `SIGTERM` or `SIGHUP` -- or,
with `--attached`, until standard input closes, which is how a program that started it takes it
down even when that program crashes or is killed. The page is one more frontend of every
daemon it reaches, of `kind` `web`, speaking JSON-RPC to this machine's daemon -- reached, and
started where none runs, before `hmz web` listens -- and to any other the user adds; `hmz web`
holds no epic itself, and this directory is only the one a new epic is offered first. Once
listening it writes the port to `~/.hmz/web-port`, prints
`hmz web: http://127.0.0.1:<port>/?key=<key>` to stdout and opens that address in a browser.
What it serves, refuses and answers is the [Web reference](/reference/web).

| Condition | stderr | Exit |
| --- | --- | --- |
| Interrupted, terminated or hung up on, or, attached, standard input closed | — | `0` |
| This machine's daemon is an older Humanize's | `hmz: <why>` | `1` |
| The daemon could not be reached, or the port listened on | `hmz: the web interface cannot be served: <OSError>` | `1` |

## `hmz daemon` {#hmz-daemon}

```text
hmz daemon serve [--listen <spec>]...
hmz daemon connect --stdio
hmz daemon pair [--route <route>]... [--seconds <seconds>]
hmz daemon devices [revoke <name>]
hmz daemon install
hmz daemon uninstall
```

| Subcommand | Does |
| --- | --- |
| `serve` | Runs this machine's [daemon](/reference/daemon#sessions) in the foreground until `SIGINT` or `SIGTERM`, listening on its socket, on every listener of the setting `listen` and on every `--listen` (`tcp://<address>:<port>`, `ws://<address>:<port>`, `relay:<ws-url>`, `webrtc:<ws-url>`, `easytier:<name>`). Prints `hmz daemon: listening on <route>` as each listener opens. It never goes for want of hosts or sessions. With no controlling terminal -- as the service runs it -- it first takes the [login shell's environment](/reference/daemon#process), which every host it starts runs in. |
| `connect --stdio` | Carries standard input to the daemon's socket and the socket to standard output, starting the daemon where none runs, until either ends; what a `stdio:ssh` or `stdio:wsl` route runs on the far machine. Once it reaches the daemon it first prints the line `hmz-stdio/1`: the client drops everything up to and including it, so whatever a shell profile there printed before is never read as part of the session. A client that sees 64 KiB without that line gives the route up. |
| `pair` | Calls `pair.create` (`--route` any number of times; `--seconds` 60 to 86400, default 600), prints the `hmz-pair:…` code, and on stderr `hmz daemon pair: claim this code on the device to pair before <time>`. |
| `devices` | One line per paired device, oldest first: name, fingerprint, added, last seen, tab-separated. `devices revoke <name>` calls `devices.revoke` and prints `hmz daemon devices: revoked <name>; <n> sessions closed`. |
| `install`, `uninstall` | Writes, enables and starts -- or stops, disables and removes -- the service running `<hmz> daemon serve` at login: the launchd agent `~/Library/LaunchAgents/ai.humanfia.hmz.daemon.plist` (`launchctl bootstrap gui/<uid>`) or the systemd user unit `~/.config/systemd/user/hmz-daemon.service` (`systemctl --user enable --now`). Prints `hmz daemon: installed <path>` or `uninstalled <path>`. |

| Condition | stderr | Exit |
| --- | --- | --- |
| `serve` interrupted or terminated | — | `0` |
| `connect --stdio` interrupted | — | `130` |
| `serve` with a daemon already running | `hmz: a daemon is already running (pid <pid>)` | `1` |
| The daemon cannot be reached or started | `hmz: the daemon cannot be reached: <why>` | `1` |
| The daemon speaks another protocol | `hmz: the runs on this machine are held by an older Humanize (pid <pid>); stop it with that version` | `1` |
| `pair.create` or `devices.revoke` refused | `hmz: <message>` | `1` |
| `install` on another system than macOS or Linux | `hmz: hmz daemon install runs on macOS and Linux alone` | `1` |
| `launchctl` or `systemctl` fails, or `uninstall` with nothing installed | `hmz: <why>` | `1` |
| Another subcommand, `connect` without `--stdio`, a `--listen` that is not a listener spec | argparse usage error (`<spec> is not a listener.`) | `2` |

## `hmz relay` {#hmz-relay}

```text
hmz relay serve [--listen <host>:<port>]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--listen <host>:<port>` | `127.0.0.1:8765` | Where the relay listens. The port is `0` to `65535`, `0` for any free one; an IPv6 host goes in brackets, `[::1]:8765`. |

`serve` serves the [relay](/user/relay) on plain WebSockets, on any path, until `SIGINT` or
`SIGTERM`. Once listening it prints `hmz relay: listening on ws://<host>:<port>`, the port the
one it was given, or the one it got for `0`. It reads no settings, no home and no identity, and
starts or reaches no daemon. TLS, for a `wss://` URL, is a proxy's in front of it.

| Condition | stderr | Exit |
| --- | --- | --- |
| Interrupted or terminated | — | `0` |
| The address could not be listened on | `hmz: the relay cannot listen: <OSError>` | `1` |
| No subcommand or another, or a `--listen` that is not `<host>:<port>` as above | argparse usage error | `2` |

## `hmz update` {#hmz-update}

```text
hmz update
```

Asks PyPI for the newest release of `hmz` (`info.version` of `https://pypi.org/pypi/hmz/json`,
which skips pre-releases) and, where it is newer than the one running, has whatever installed
this `hmz` install it:

| Installed by | Recognised by | Runs |
| --- | --- | --- |
| `uv tool install` | `uv-receipt.toml` in `sys.prefix` | `uv tool upgrade hmz` (keeps the extras) |
| `pipx install` | `pipx_metadata.json` in `sys.prefix` | `pipx upgrade hmz` (keeps the extras) |
| anything else | — | `python -m pip install --upgrade hmz[<extras>]`, or `uv pip install --python <python> --upgrade hmz[<extras>]` where there is no pip; `<extras>` are those whose packages are all installed |

It then asks a fresh interpreter which version is installed, and prints
`Updated hmz to <version>`. A uv tool installed with a pin (`uv tool install hmz==<v>`) is held
to it, as `uv tool upgrade` holds it; uv says how to lift the pin. Epics a [daemon](/reference/daemon) already holds keep running
under the release it started with until it stops; where one is running, `hmz update` says so
and leaves it alone. The interfaces say when a newer release is out: the [terminal
interface](/reference/tui) in a line as it opens, the [web interface](/reference/web) with
`Update` in the daemon picker.

| Condition | Output | Exit |
| --- | --- | --- |
| Already the newest release | stdout `hmz <version> is the newest release`; nothing is run | `0` |
| Updated | stdout `Updating hmz <old> to <new>: <line>`, the installer's own output, `Updated hmz to <new>` | `0` |
| Installed from a checkout or a URL (`direct_url.json`) | stderr `hmz update: hmz was installed from <url>, not PyPI; update it there`, the URL without its user, password, query or fragment | `1` |
| The installer is not on `PATH` | stderr `hmz update: <uv\|pipx> installed hmz but is not on PATH` | `1` |
| PyPI did not answer, or `HUMANIZE_RELEASES=off` | stderr `hmz update: PyPI could not be asked for the newest release` | `1` |
| The installer failed | stderr `hmz update: <installer> exited <status>` | `1` |
| The installer left another version | stderr `hmz update: <installer> left hmz at <version>, not <new>` | `1` |

## `hmz backup` {#hmz-backup}

```text
usage: hmz backup [-h] [--to NAME] [--list | --pull EPIC] [epic]
```

Backs one epic of this directory -- by its name, or by its path -- up to
[git repositories](/user/backups) now, waits for it, and says how each target took it. With
`--list` or `--pull`, reads the targets instead: each is fetched first.

| Option | Value | Occurrences | Default | Meaning |
| --- | --- | --- | --- | --- |
| `epic` | the epic's name or path | exactly 1, without `--list` and `--pull`; 0 with them | — | The epic. |
| `--to` | a [backup target](/reference/settings#backup) name | 0‥n | backing up: the targets the epic was started with, else `backup.defaults`; `--list`, `--pull`: every target | Where it goes, or where to look. |
| `--list` | — | 0‥1 | off | List each target's epics, of every machine. |
| `--pull` | an epic's name, or `<machine>/<workspace>/<epic>` | 0‥1 | — | [Download](/user/backups#downloading-an-epic) it from the first target holding it, as an [import](/user/export#importing-a-run). |

| Condition | Output | Exit |
| --- | --- | --- |
| Every target took it | stdout `<target>: backed up to <url>`, the URL with anything signed into it taken out | `0` |
| A target did not | stderr `<target>: failed: <why>` | `1` |
| No such epic, no such target, or no target at all | argparse usage error on stderr | `2` |
| `--list` | stdout `<target>: <n> epics`, then per epic `  <machine>  <workspace>  <epic>  <how or unfinished>  <task>` | `0` |
| `--pull`, downloaded | stdout the path it now has | `0` |
| A target could not be fetched | stderr `<target>: failed: <why>`, the rest still read | `1` |
| `--pull` of an epic already here | stderr `hmz backup: <epic> is already here, at <path>` | `1` |
| `--pull` of an epic no target holds, or more than one machine's of that name | argparse usage error on stderr | `2` |

## `hmz internal` <Badge type="warning" text="not typed by hand" /> {#hmz-internal}

```text
hmz internal <command> [<args>...]
```

The command lines Humanize starts its own processes with. Each still runs when typed.
`hmz internal -h` prints the help below and exits `0`. `hmz internal` with no command, or an
unknown one, prints the usage and an argparse error (`the following arguments are required:
COMMAND`, `invalid choice: …`) and exits `2`.

| Command | Summary as printed | Spawned by |
| --- | --- | --- |
| [`anchor`](#hmz-internal-anchor) | `run an agent turn on another machine` | every turn whose work lands on another machine |
| [`cli`](#hmz-internal-cli) | `relay agent runs of a flow's command line to the flow` | a script on an agent's `PATH`, once per run of a flow's command line |
| [`cred`](#hmz-internal-cred) | `run a program with credentials from an account` | every turn or login under an account, and every turn whose sessions Humanize keeps |
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
its own arguments. Each runs the program [`coganchor`](#coganchor), which does the work, and
exits with its status. Semantics: [Remote execution](/reference/remote-execution).

| Option | Default | Meaning |
| --- | --- | --- |
| `--target URL` | `$HUMANIZE_TARGET`, else `local` | `ssh://HOST`, `docker://CONTAINER[?OPTIONS][@ENDPOINT]`, `apple-container://CONTAINER`, `slurm://JOBID[?python=PATH]`, `tcp://HOST:PORT`, `peer://TICKET@HOST:PORT`, or `local[:DIR]`. |
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
| `--token TOKEN` | `$HUMANIZE_TOKEN` | Shared secret a `tcp://` target expects, proved inside TLS rather than sent; a `peer://` target's ticket is its secret and this is unused. |
| `--token-file FILE` | — | Read that secret from `FILE` instead. What Humanize itself spawns is always given this, never `--token`: a command line is in every user's `ps`. The file is under `hmz.machine()/tokens/`, mode `0600`, named by the secret's SHA-256. |
| `--force` | off | Use the mirror directory even if it holds unrelated files. |
| `--native` | off | Run the CLI installed on the target instead of supervising one here. |
| `--hush NAME` | — | With `--native`, unset this variable for the CLI on the target. Repeatable. |
| `--project NAME=DIR` | — | With `--native`, put this credentials directory on the target for the session and set `NAME` to it. Repeatable. |
| `--bring NAME/PATH=DIR` | — | With `--native`, copy what the turn wrote at `PATH` (may be a glob) inside the directory `--project` set `NAME` to back into `DIR`, at the same place, before that directory is removed. Repeatable. |
| `--tell DIR` | — | With `--native`, keep a file of `NAME=PATH` lines in `DIR` on this machine while the turn runs, one per `--project` that landed at `PATH` on the target. |
| `--installs LINE` | — | With `--native`, the install line to report where the target lacks the CLI. |
| `--fence JSON` | — | Hold the agent to this [fence](/reference/agents#the-fence) on both machines. |
| `--check` | off | Connect, print what was found, exit. |
| `--log-level {debug,info,warning,error}` | `$HUMANIZE_LOG`, else `warning` | Logging to stderr. |

`--check` prints, on stdout, lines `target`, `hostname`, `python coganchor <version> (pid …)`, one `export <virtual> -> <real>` per export, and `workspace <path> (<n> entries)`.

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
    [--token TOKEN | --token-file FILE] [--log-level {debug,info,warning,error}]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--export VIRTUAL[:REAL]` | — | **Required, repeatable.** A directory: `VIRTUAL` as the agent sees it, `REAL` where it is here. |
| `--stdio` | | Serve one session over stdin/stdout. |
| `--listen [HOST:]PORT` | host `127.0.0.1` | Serve TCP connections. |
| `--peer TICKET@HOST:PORT` | | Serve one session through a rendezvous broker. |
| `--token TOKEN` | `$HUMANIZE_TOKEN`, but not with `--peer` | Shared secret required from clients. |
| `--token-file FILE` | | A file holding that secret, read verbatim. |
| `--log-level` | `$HUMANIZE_LOG`, else `warning` | |

Exactly one of `--stdio`, `--listen`, `--peer`. `--listen` and `--peer` speak only TLS, inside
which a client proves the token, or with `--peer` the ticket, rather than sending it
([Remote execution › The link over a network](/reference/remote-execution#the-link-over-a-network)).

| Exit | When |
| --- | --- |
| `0` | served until the session or the process ended |
| `1` | cannot listen (`hmz: cannot listen on <host>:<port>: <why>`), or cannot dial the peer |
| `2` | a bad `--export`; a malformed address (`hmz: malformed listen address '<a>'; expected [HOST:]PORT`); a non-loopback `--listen` without a token (`hmz: cannot listen on a non-loopback address without --token`); `--token` or `--token-file` with `--peer` (`hmz: --token cannot be given with --peer, whose ticket is the secret`). Loopback is `127.0.0.1`, `::1`, `localhost`. |

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
where Humanize keeps them.

| Option | Meaning |
| --- | --- |
| `--map FROM=TO` | Repeatable. Answer absolute path `FROM` (a file, or everything under a directory) with `TO`; reads may be served from an in-memory copy. |
| `--keep FROM=TO` | Repeatable. As `--map`, never by copying; creates what the program writes. `FROM` may contain a glob in any component. |

| Exit | When |
| --- | --- |
| the program's | it ran |
| `1` | it could not be supervised (`hmz internal cred: <why>`); it is never run unsupervised |

It exits as soon as `COMMAND` does. What `COMMAND` left running after its parent exited is not
killed, and stays supervised until it exits
([Providers › How a credential path is answered](/reference/providers#how-a-credential-path-is-answered)).
| `2` | no program (`no program given; try `hmz internal cred --map FROM=TO -- claude``); no `--map`/`--keep` (`nothing to answer with anything: give at least one --map or --keep`); a malformed mapping |

### `hmz internal fence` {#hmz-internal-fence}

```text
hmz internal fence (--policy JSON [--sandbox BACKEND] | --relay DIR) [--] COMMAND [ARGS...]
```

Runs `COMMAND` inside a [fence](/reference/agents#the-fence): on Linux, Landlock for paths and,
where the network is cut, a seccomp filter admitting only TCP and Unix sockets -- or, where
Landlock cannot hold it or `--sandbox bwrap` says so, `bwrap` mounting what the fence grants
into a root of its own and, where the network is cut, giving it a network namespace of its own;
on macOS, the whole fence as one Seatbelt profile applied by `/usr/bin/sandbox-exec`, whose
carve-outs (`keep`, `deny`) follow its grants, deepest last. Landlock only grants, so on Linux a
granted directory holding a carve-out is granted as its entries as they stand, down to the
carve-out; an entry made there later is out of reach. Under bubblewrap a carve-out is an empty
directory or file mounted over it. Where the network is
cut, a loopback proxy (`HTTPS_PROXY` and related, `NO_PROXY` emptied) passing only the fence's
hosts; `TMPDIR` set to the fence's scratch directory.

| Option | Meaning |
| --- | --- |
| `--policy JSON` | The fence as JSON, or `@PATH` for a file holding it. |
| `--sandbox BACKEND` | On Linux, what puts the fence up: `landlock`, `bwrap`, or `auto` (the default, and any other value): Landlock where it can hold the fence and `bwrap` otherwise. Humanize passes `sandbox.backend` from [`settings.yaml`](/reference/settings#sandbox); a machine reached as a target is passed nothing, and chooses for itself. |
| `--relay DIR` | Instead of `--policy`: run as the program `bwrap` starts in a network namespace of its own, carrying loopback across its edge through the Unix sockets in `DIR` -- each `out-PORT.sock` to the proxy at `PORT`, and `PORT` here for each `in-PORT` -- then run `COMMAND`. |

| Exit | When |
| --- | --- |
| the program's | it ran |
| `2` | neither or both of `--policy` and `--relay`; no program (`no program given; try `hmz internal fence --policy=... -- claude``) |
| `126` | the fence cannot be put up here (no Landlock and no `bwrap` that starts, or no way to cut TCP; on macOS, a process already inside a sandbox; a path it writes leads through a link a fenced program could have made; on Linux, a carve-out beneath a directory that cannot be listed, or beneath a grant that is not a directory, or under `bwrap` one that is not there); the program never ran (`hmz internal fence: <why>`) |

### `coganchor` {#coganchor}

```text
coganchor cog [options] AGENT [ARGS...]           # hmz internal anchor
coganchor anchor --export VIRTUAL[:REAL] …        # hmz internal anchor serve
coganchor broker [--listen [HOST:]PORT] …         # hmz internal anchor rendezvous
coganchor internal fence --policy JSON [--sandbox BACKEND] [--] …  # hmz internal fence
coganchor internal cred --map FROM=TO … [--] …    # hmz internal cred
coganchor internal able [--policy JSON] [--sandbox BACKEND]
coganchor --version
```

`coganchor internal able` writes what this machine can fence with the backend `--sandbox`
chooses, `{"fs": bool, "net": bool}`, and with `--policy` also `"unheld"`: why that backend
cannot hold what that fence carves out of its grants, or `null` where it can (always `null` on
macOS). Humanize asks it before a session is
opened.

The anchor, as one static program in Rust, built from `crates/coganchor/`. The package
carries a build for Linux (static, against musl) and macOS on x86-64 and aarch64, at
`hmz/coganchor/bin/<os>-<arch>/coganchor`, and copies the right one to each machine a session
reaches. Each mode takes the options, defaults, variables, messages and exit statuses of the
`hmz internal` command beside it above, which runs it; `anchor` also takes `--token-file`.
Its messages begin `hmz: ` as theirs do, and `coganchor anchor --listen` prints `hmz internal
anchor serve listening HOST PORT`. `--version` prints `coganchor <version>`. `internal` is
left out of its help. [`HUMANIZE_COGANCHOR`](/reference/environment#humanize-coganchor) names a
`coganchor` for `hmz` to run here instead of the packaged one. Where there is neither, nor a
build in a checkout's `crates/coganchor/target/{release,debug}`, the `hmz internal` command
exits `127` saying `hmz: no coganchor is built for this machine (<system> <machine>)`.

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

### `hmz internal cli` {#hmz-internal-cli}

```text
hmz internal cli --at SOCKET --name NAME [-- WORDS...]
```

Sends `{"name": NAME, "argv": WORDS}` on one line to the Unix socket `SOCKET`, reads one line
`{"code", "out", "err"}` back, writes `out` to stdout and `err` to stderr, and exits `code`.
Everything after the first `--` is passed on untouched, `--help` and later `--` included.
Stdin is not read. See [Agents › Command lines](/reference/agents#command-lines).

| Exit | When |
| --- | --- |
| the flow's | it answered: `0`, `2` for a usage error, `127` for a command line no longer shelved, or what the flow's function exited with |
| `1` | the socket cannot be reached (`NAME: the flow serving it has ended (<why>)`), or no answer came back (`NAME: the flow serving it gave no answer`) |
| `2` | no `--at` or `--name` |

## Exit statuses {#exit-statuses}

| Status | Command | Meaning |
| --- | --- | --- |
| `0` | all | Success. For `hmz exec`, including a run its budget stopped; for `hmz chat`, the turn done. |
| `1` | `hmz` | Runs held by an older Humanize; the daemon could not be reached; or the host let go of the interface. |
| `1` | `hmz web` | This machine's daemon is an older Humanize's; or the daemon or the port could not be had. |
| `1` | `hmz daemon` | A daemon already running on `serve`; the daemon unreachable, of another protocol, or refusing; the service could not be installed. |
| `1` | `hmz relay` | The address could not be listened on. |
| `1` | `hmz update` | Installed from a source, or no installer, PyPI or install that worked. |
| `1` | `hmz exec` | The daemon could not be reached (`hmz: the daemon cannot be reached: <why>`); or the flow failed (the `why` of its `ended` record, the exception or traceback, on stderr; the host reports the crash where reporting is on). |
| `1` | `hmz chat` | The daemon could not be reached; or the turn failed (what the harness said, on stderr). |
| `1` | `internal …` | Could not connect, listen, supervise, or reach a socket. |
| `2` | all | The line was wrong: argparse rejections and everything in [What is refused](#what-is-refused-before-anything-runs). |
| `126` | `internal fence` | The fence could not be put up; the program never ran. |
| `127` | `internal anchor --native` | The target has no such CLI. |
| `130` | `hmz exec`, `hmz chat`, `hmz daemon connect`, `internal anchor` | Interrupted (`SIGINT`); for `hmz exec`, after the epic has let go of what it made; for `hmz chat`, leaving the chat to its host. |
| `129`, `143` | `hmz exec`, `hmz chat` | `SIGHUP`, `SIGTERM`, as `SIGINT` is. |
| *program's* | `internal anchor`, `cred`, `fence` | The wrapped program's own status. |
| *flow's* | `internal cli` | What the flow answered the run with. |

## Environment variables {#environment-variables}

Variables these commands read. The complete list, with every layer's, is
[Environment variables](/reference/environment).

| Variable | Read by | Values | Effect |
| --- | --- | --- | --- |
| `HUMANIZE_HOME` | all | a path | Where Humanize keeps what outlives a run. Default `~/.hmz`, which a `~/.humanize` is moved to. Empty is unset. Not created until written. |
| `HUMANIZE_NAME` | `hmz`, SDK links | a name | The name a frontend attaches under, before `@<kind>`. Default: the login name. |
| `HUMANIZE_SENTRY` | `hmz`, `hmz exec` | `on`, `off` | Answers [reporting](/user/reporting) for this process without writing the answer down. |
| `HUMANIZE_RELEASES` | `hmz`, the daemon, `hmz update` | a URL, a path, or `off`, `0`, `no`, `none`, empty | Where the newest release is read from (PyPI's JSON for `hmz` by default); off, nothing asks. |
| `HUMANIZE_EASYTIER` | the daemon, and every command that reaches a P2P daemon | a path | An `easytier-core` to use in place of the one Humanize downloads; ignored where it does not exist. |
| `HUMANIZE_EASYTIER_NODES` | `hmz web` | a URL | The Uptime Kuma server whose status page `easytier` lists the community's shared EasyTier nodes. |
| `NO_COLOR`, `TERM`, `FORCE_COLOR` | all | see [Colour](#colour) | Escapes. |
| `TEXTUAL_THEME` | `hmz` | a Textual theme name | The interface's theme; unknown names are ignored. |
| `TMUX`, `TERM_PROGRAM`, `LC_TERMINAL` | `hmz` | | Decide `TEXTUAL_DISABLE_KITTY_KEY` ([Terminal preparation](#terminal-preparation)). |
| `HUMANIZE_COGANCHOR` | `internal anchor`, `cred`, `fence` | a path | The [`coganchor`](#coganchor) to run here in place of the packaged build; ignored where it does not exist. |
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
| `settings.yaml` | `hmz` | read and written: [what the interface remembers](/reference/tui#what-it-remembers); its `runtimes`, `nous` and `clis` are read by all when an agent or environment is opened |
| `history.jsonl` | `hmz` | read and written: [prompt history](/reference/tui#history) |
| `epics/<workspace>/<datetime>-<hex>/host.log` | `hmz` | appended: what the [host process](/reference/daemon#files) wrote while it held that run. The daemon's socket, record, lock and log are in the machine's temporary directory, not here |
| `prices.json` | all | model prices, refreshed when older than a day by the interface as it opens and by a run as it starts |
| `releases.json` (in the machine's directory) | `hmz`, the daemon, `hmz update` | the newest release, refreshed when older than a day by the terminal interface as it opens, by the daemon as it starts and each day it runs, and by `hmz update` |
| `web-port` | `hmz web` | read as it starts, for `--port`'s default; written, replaced whole, when the port it listens on changes |
| `easytier/<version>/` | the daemon, and every command that reaches a P2P daemon | written once: the `easytier-core` downloaded and checked, reused after |
| `settings.yaml`, `providers/` | all | read when an agent or environment is opened |
| `flowverses/`; `~/.hmz/flows/` and `./.hmz/flows/` (fixed paths, not moved by `HUMANIZE_HOME`) | all | read when `-f` is resolved |

## Python equivalents {#python-entry-points}

Every command is a shell around [`hmz.sdk.Hmz`](/reference/sdk#hmz):

| Command line | Python |
| --- | --- |
| `hmz exec <argv>` | [`Hmz().exec(argv)`](/reference/sdk#hmz-exec) |
| reading an `hmz exec` line | [`Hmz().read(argv)`](/reference/sdk#hmz-read) → `Line` |
| `hmz exec` without the line | [`Hmz().run(flow, task, agents=…, envs=…, params=…, budget=…, profile_flow=…, profile_environment=…, resume=…)`](/reference/sdk#hmz-run) |
| `hmz` (as a frontend of held runs) | [`Daemons().host().link()`](/reference/sdk#daemons) |

`hmz web` serves a page that is a client of the daemons as `hmz` is; in Python it is
`hmz.web.serve()`, which is not part of the SDK. See [Web › Module](/reference/web#module).
